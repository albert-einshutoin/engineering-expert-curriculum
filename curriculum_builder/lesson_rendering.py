"""Pinned lesson discovery and semantic textbook rendering."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Final
from urllib.parse import urlsplit

from .errors import CurriculumValidationError
from .graph import topological_stages
from .html_safety import MAX_FRAGMENT_BYTES, SafeHtml, validate_fragment
from .lessons import Lesson, MAX_LESSON_BYTES, load_lesson_bytes
from .render import Renderer


_LESSON_ID: Final = re.compile(
    r"core-(?:0[1-9]|[12][0-9]|30)-[a-z0-9]+(?:-[a-z0-9]+)*\Z",
    re.ASCII,
)
_READ_CHUNK_BYTES: Final = 64 * 1024
_DIRECTORY_FLAGS: Final = (
    os.O_RDONLY
    | os.O_DIRECTORY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_FILE_FLAGS: Final = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NONBLOCK", 0)
)
_PAIR = frozenset({"lesson.json", "body.html"})


@dataclass(frozen=True, slots=True)
class LoadedLesson:
    """One immutable metadata/body snapshot bound to a lesson directory."""

    lesson: Lesson
    body: SafeHtml
    metadata_bytes: bytes
    body_bytes: bytes


def load_lessons_from_root(content_descriptor: int) -> tuple[LoadedLesson, ...]:
    """Load a complete collection through the caller's pinned content dirfd.

    A build requires exclusive control of the workspace namespace. Descriptor
    pinning and before/after signatures detect persistent and ordinary TOCTOU
    changes, while that exclusivity closes the portable same-writer ABA gap.
    """
    if type(content_descriptor) is not int or content_descriptor < 0:
        raise CurriculumValidationError(
            "content descriptor must be a valid integer"
        )
    if not hasattr(os, "O_NOFOLLOW"):
        raise CurriculumValidationError(
            "safe lesson descriptors are not supported"
        )

    lessons_fd: int | None = None
    try:
        try:
            before = os.stat(
                "lessons",
                dir_fd=content_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return ()
        _require_safe_node(before, "lessons", directory=True)
        lessons_fd = os.open(
            "lessons",
            _DIRECTORY_FLAGS,
            dir_fd=content_descriptor,
        )
        opened = os.fstat(lessons_fd)
        _require_safe_node(opened, "lessons", directory=True)
        if _directory_signature(opened) != _directory_signature(before):
            raise CurriculumValidationError(
                "lessons directory changed while opening"
            )

        names = _discover_lesson_names(lessons_fd)
        loaded = tuple(
            _load_lesson_directory(lessons_fd, name)
            for name in names
        )
        current = os.stat(
            "lessons",
            dir_fd=content_descriptor,
            follow_symlinks=False,
        )
        if (
            _directory_signature(os.fstat(lessons_fd))
            != _directory_signature(opened)
            or _directory_signature(current)
            != _directory_signature(opened)
        ):
            raise CurriculumValidationError(
                "lessons directory changed during read"
            )
    except CurriculumValidationError:
        raise
    except OSError:
        raise CurriculumValidationError(
            "lessons cannot be read safely"
        ) from None
    finally:
        if lessons_fd is not None:
            _close_descriptor(lessons_fd, "lessons directory")

    ids = tuple(item.lesson.id for item in loaded)
    if len(set(ids)) != len(ids):
        raise CurriculumValidationError("duplicate lesson id")
    for item, directory_name in zip(loaded, names, strict=True):
        if item.lesson.id != directory_name:
            raise CurriculumValidationError(
                "lesson directory name must equal lesson id"
            )
        if item.lesson.status != "complete":
            raise CurriculumValidationError(
                "draft lessons cannot be published"
            )

    prerequisites = {
        item.lesson.id: item.lesson.prerequisite_ids
        for item in loaded
    }
    stages = topological_stages(ids, prerequisites)
    by_id = {item.lesson.id: item for item in loaded}
    return tuple(
        by_id[lesson_id]
        for stage in stages
        for lesson_id in stage
    )


def _discover_lesson_names(directory_fd: int) -> tuple[str, ...]:
    try:
        with os.scandir(directory_fd) as entries:
            observed = tuple(entries)
    except OSError:
        raise CurriculumValidationError(
            "lessons cannot be discovered safely"
        ) from None

    names: list[str] = []
    for entry in observed:
        name = entry.name
        if type(name) is not str or _LESSON_ID.fullmatch(name) is None:
            raise CurriculumValidationError(
                "lesson directory name is unsafe"
            )
        try:
            node = entry.stat(follow_symlinks=False)
        except OSError:
            raise CurriculumValidationError(
                "lesson directory cannot be inspected"
            ) from None
        _require_safe_node(node, f"lesson {name}", directory=True)
        names.append(name)
    if len(set(names)) != len(names):
        raise CurriculumValidationError("duplicate lesson directory")
    return tuple(sorted(names))


def _load_lesson_directory(
    lessons_fd: int,
    name: str,
) -> LoadedLesson:
    descriptor: int | None = None
    try:
        before = os.stat(
            name,
            dir_fd=lessons_fd,
            follow_symlinks=False,
        )
        _require_safe_node(before, f"lesson {name}", directory=True)
        descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=lessons_fd)
        opened = os.fstat(descriptor)
        _require_safe_node(opened, f"lesson {name}", directory=True)
        if _directory_signature(opened) != _directory_signature(before):
            raise CurriculumValidationError(
                f"lesson {name} changed while opening"
            )
        try:
            with os.scandir(descriptor) as entries:
                entry_names = tuple(entry.name for entry in entries)
        except OSError:
            raise CurriculumValidationError(
                f"lesson {name} cannot be discovered safely"
            ) from None
        if frozenset(entry_names) != _PAIR or len(entry_names) != len(_PAIR):
            raise CurriculumValidationError(
                f"lesson {name} must contain the lesson.json/body.html pair"
            )

        metadata, metadata_signature = _read_regular_file_at(
            descriptor,
            "lesson.json",
            MAX_LESSON_BYTES,
            f"lesson {name}/lesson.json",
        )
        body_raw, body_signature = _read_regular_file_at(
            descriptor,
            "body.html",
            MAX_FRAGMENT_BYTES,
            f"lesson {name}/body.html",
        )
        _revalidate_file(
            descriptor,
            "lesson.json",
            metadata_signature,
            f"lesson {name}/lesson.json",
        )
        _revalidate_file(
            descriptor,
            "body.html",
            body_signature,
            f"lesson {name}/body.html",
        )
        current = os.stat(
            name,
            dir_fd=lessons_fd,
            follow_symlinks=False,
        )
        if (
            _directory_signature(os.fstat(descriptor))
            != _directory_signature(opened)
            or _directory_signature(current)
            != _directory_signature(opened)
        ):
            raise CurriculumValidationError(
                f"lesson {name} directory changed during read"
            )

        try:
            body_text = body_raw.decode("utf-8")
        except UnicodeDecodeError:
            raise CurriculumValidationError(
                f"lesson {name}/body.html is not valid UTF-8"
            ) from None
        lesson = load_lesson_bytes(metadata, "lesson.json")
        body = validate_fragment(body_text)
        _reject_authored_external_links(body_text)
        return LoadedLesson(
            lesson=lesson,
            body=body,
            metadata_bytes=metadata,
            body_bytes=body_raw,
        )
    except CurriculumValidationError:
        raise
    except OSError:
        raise CurriculumValidationError(
            f"lesson {name} cannot be read safely"
        ) from None
    finally:
        if descriptor is not None:
            _close_descriptor(descriptor, f"lesson {name} directory")


def _read_regular_file_at(
    directory_fd: int,
    name: str,
    maximum_bytes: int,
    label: str,
) -> tuple[bytes, tuple[int, int, int, int, int, int]]:
    descriptor: int | None = None
    try:
        before = os.stat(
            name,
            dir_fd=directory_fd,
            follow_symlinks=False,
        )
        _require_safe_node(before, label, directory=False)
        if before.st_size > maximum_bytes:
            raise CurriculumValidationError(
                f"{label} exceeds maximum byte count"
            )
        descriptor = os.open(
            name,
            _FILE_FLAGS,
            dir_fd=directory_fd,
        )
        opened = os.fstat(descriptor)
        _require_safe_node(opened, label, directory=False)
        signature = _file_signature(opened)
        if signature != _file_signature(before):
            raise CurriculumValidationError(f"{label} changed during read")

        remaining = opened.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(
                descriptor,
                min(_READ_CHUNK_BYTES, remaining),
            )
            if not chunk or len(chunk) > remaining:
                raise CurriculumValidationError(
                    f"{label} changed during read"
                )
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise CurriculumValidationError(f"{label} changed during read")
        if _file_signature(os.fstat(descriptor)) != signature:
            raise CurriculumValidationError(f"{label} changed during read")
        _revalidate_file(directory_fd, name, signature, label)
        return b"".join(chunks), signature
    finally:
        if descriptor is not None:
            _close_descriptor(descriptor, label)


def _revalidate_file(
    directory_fd: int,
    name: str,
    expected: tuple[int, int, int, int, int, int],
    label: str,
) -> None:
    current = os.stat(
        name,
        dir_fd=directory_fd,
        follow_symlinks=False,
    )
    if _file_signature(current) != expected:
        raise CurriculumValidationError(f"{label} changed during read")


def _require_safe_node(
    node: os.stat_result,
    label: str,
    *,
    directory: bool,
) -> None:
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    kind = "directory" if directory else "regular file"
    if not expected(node.st_mode):
        raise CurriculumValidationError(f"{label} must be a {kind}")
    if hasattr(os, "geteuid") and node.st_uid != os.geteuid():
        raise CurriculumValidationError(
            f"{label} must be owned by the current user"
        )
    if node.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise CurriculumValidationError(
            f"{label} must not be group/world writable"
        )


def _directory_signature(
    node: os.stat_result,
) -> tuple[int, int, int, int, int]:
    return (
        node.st_dev,
        node.st_ino,
        stat.S_IFMT(node.st_mode),
        node.st_mtime_ns,
        node.st_ctime_ns,
    )


def _file_signature(
    node: os.stat_result,
) -> tuple[int, int, int, int, int, int]:
    return (
        node.st_dev,
        node.st_ino,
        stat.S_IFMT(node.st_mode),
        node.st_size,
        node.st_mtime_ns,
        node.st_ctime_ns,
    )


def _close_descriptor(descriptor: int, label: str) -> None:
    try:
        os.close(descriptor)
    except OSError as close_error:
        active = sys.exception()
        if active is None:
            raise RuntimeError(
                f"{label} descriptor close failed: {close_error}"
            ) from close_error
        raise RuntimeError(
            f"{label} descriptor close failed: {close_error}"
        ) from active


class _AuthoredBodyLinkParser(HTMLParser):
    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() != "a":
            return
        for name, value in attrs:
            if name.casefold() != "href" or value is None:
                continue
            try:
                parsed = urlsplit(value)
            except ValueError:
                raise CurriculumValidationError(
                    "authored body contains a malformed link"
                ) from None
            if parsed.scheme or parsed.netloc:
                raise CurriculumValidationError(
                    "authored body external links are not allowed"
                )

    handle_startendtag = handle_starttag


def _reject_authored_external_links(body: str) -> None:
    parser = _AuthoredBodyLinkParser(convert_charrefs=True)
    try:
        parser.feed(body)
        parser.close()
    except CurriculumValidationError:
        raise
    except Exception:
        raise CurriculumValidationError(
            "authored body links cannot be validated"
        ) from None


def render_lesson_artifacts(
    renderer: Renderer,
    loaded: tuple[LoadedLesson, ...],
) -> dict[PurePosixPath, bytes]:
    """Render a validated lesson collection and its topological index."""
    if type(loaded) is not tuple or any(
        type(item) is not LoadedLesson for item in loaded
    ):
        raise CurriculumValidationError(
            "loaded lessons must be an exact immutable tuple"
        )

    index_entries = (
        validate_fragment(
            '<p class="empty-state">'
            "公開済みのコアレッスンはまだありません。"
            "</p>"
        )
        if not loaded
        else _lesson_index_entries(loaded)
    )
    index_content = renderer.fragment(
        "lessons-index.html",
        text_values={},
        html_values={"lessons": index_entries},
    )
    artifacts = {
        PurePosixPath("lessons/index.html"): renderer.page(
            output_path=Path("lessons/index.html"),
            title="コアレッスン",
            description="前提順に学ぶエビデンス中心のコアレッスン索引",
            content=index_content,
        ).encode("utf-8")
    }
    for item in loaded:
        lesson = item.lesson
        fragment = renderer.fragment(
            "lesson.html",
            text_values={
                "track": lesson.track,
                "stage": str(lesson.stage),
                "title": lesson.title,
                "summary": lesson.summary,
                "difficulty": lesson.difficulty,
                "estimated_minutes": str(lesson.estimated_minutes),
                "updated_at": lesson.updated_at,
            },
            html_values={
                "objectives": _render_objectives(lesson),
                "capabilities": _render_capabilities(lesson),
                "body": item.body,
                "lab": _render_lab(lesson),
                "assessment": _render_assessment(lesson),
                "teach_back": _paragraph(lesson.teach_back),
                "transfer_task": _paragraph(lesson.transfer_task),
                "review_schedule": _render_review(lesson),
                "rubric_table": _render_rubric(lesson),
                "sources": _render_sources(lesson),
            },
        )
        output_path = Path("lessons") / lesson.id / "index.html"
        artifacts[PurePosixPath(output_path.as_posix())] = renderer.page(
            output_path=output_path,
            title=lesson.title,
            description=lesson.summary,
            content=fragment,
        ).encode("utf-8")
    return artifacts


def _lesson_index_entries(loaded: tuple[LoadedLesson, ...]) -> SafeHtml:
    entries = "".join(
        '<li class="lesson-index-item">'
        f'<a href="{item.lesson.id}/index.html">'
        f"{escape(item.lesson.title, quote=False)}</a>"
        f"<p>{escape(item.lesson.summary, quote=False)}</p>"
        "</li>"
        for item in loaded
    )
    return validate_fragment(
        f'<ol class="lesson-index-list">{entries}</ol>'
    )


def _render_objectives(lesson: Lesson) -> SafeHtml:
    evidence = {item.id: item.description for item in lesson.evidence}
    entries = "".join(
        "<li>"
        f"<p>{escape(objective.statement, quote=False)}</p>"
        '<ul class="evidence-list">'
        + "".join(
            f"<li>{escape(evidence[evidence_id], quote=False)}</li>"
            for evidence_id in objective.evidence_ids
        )
        + "</ul></li>"
        for objective in lesson.objectives
    )
    return validate_fragment(f"<ol>{entries}</ol>")


def _render_capabilities(lesson: Lesson) -> SafeHtml:
    evidence = {item.id: item.description for item in lesson.evidence}
    entries = "".join(
        '<li class="capability-level">'
        f"<h3>{escape(item.level, quote=False)}</h3>"
        f"<p>{escape(item.criterion, quote=False)}</p>"
        '<p class="evidence-label"><strong>証拠:</strong> '
        + "、".join(
            escape(evidence[evidence_id], quote=False)
            for evidence_id in item.evidence_ids
        )
        + "</p></li>"
        for item in lesson.capability_progression
    )
    return validate_fragment(
        f'<ol class="capability-list">{entries}</ol>'
    )


def _render_lab(lesson: Lesson) -> SafeHtml:
    if lesson.lab is None:
        raise CurriculumValidationError(
            "complete lesson is missing its lab"
        )
    steps = "".join(
        f"<li>{escape(step, quote=False)}</li>"
        for step in lesson.lab.steps
    )
    return validate_fragment(
        f"<h3>{escape(lesson.lab.title, quote=False)}</h3>"
        '<p class="artifact-label"><strong>提出成果物:</strong> '
        f"{escape(lesson.lab.artifact, quote=False)}</p>"
        f"<ol>{steps}</ol>"
    )


def _render_assessment(lesson: Lesson) -> SafeHtml:
    entries = "".join(
        "<li>"
        '<p><strong>問い:</strong> '
        f"{escape(item.prompt, quote=False)}</p>"
        '<p><strong>期待する証拠:</strong> '
        f"{escape(item.expected_evidence, quote=False)}</p>"
        "</li>"
        for item in lesson.assessment
    )
    return validate_fragment(f"<ol>{entries}</ol>")


def _paragraph(value: str | None) -> SafeHtml:
    if value is None:
        raise CurriculumValidationError(
            "complete lesson is missing required text"
        )
    return validate_fragment(f"<p>{escape(value, quote=False)}</p>")


def _render_review(lesson: Lesson) -> SafeHtml:
    if lesson.review is None:
        raise CurriculumValidationError(
            "complete lesson is missing its review schedule"
        )
    entries = "".join(
        "<li>"
        f"<strong>{interval}日後</strong>"
        f"<p>{escape(lesson.review.prompts[index % len(lesson.review.prompts)], quote=False)}</p>"
        "</li>"
        for index, interval in enumerate(lesson.review.interval_days)
    )
    return validate_fragment(
        f'<ol class="review-list">{entries}</ol>'
    )


def _render_rubric(lesson: Lesson) -> SafeHtml:
    rows = "".join(
        "<tr>"
        f'<th scope="row">{escape(item.dimension, quote=False)}</th>'
        f"<td>{escape(item.levels.incomplete, quote=False)}</td>"
        f"<td>{escape(item.levels.developing, quote=False)}</td>"
        f"<td>{escape(item.levels.proficient, quote=False)}</td>"
        f"<td>{escape(item.levels.exemplary, quote=False)}</td>"
        "</tr>"
        for item in lesson.rubric
    )
    return validate_fragment(
        '<table class="rubric-table">'
        "<caption>4段階の評価基準</caption>"
        "<thead><tr>"
        '<th scope="col">観点</th>'
        '<th scope="col">未達</th>'
        '<th scope="col">発展途上</th>'
        '<th scope="col">熟達</th>'
        '<th scope="col">卓越</th>'
        "</tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _render_sources(lesson: Lesson) -> SafeHtml:
    entries = "".join(
        "<li>"
        f'<a href="{escape(item.url, quote=True)}" rel="noreferrer">'
        f"{escape(item.title, quote=False)}</a>"
        f" <small>({escape(item.kind, quote=False)})</small>"
        "</li>"
        for item in lesson.sources
    )
    return validate_fragment(f'<ul class="source-list">{entries}</ul>')
