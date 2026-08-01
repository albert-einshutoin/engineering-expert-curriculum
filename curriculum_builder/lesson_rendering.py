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

from .errors import CurriculumValidationError, IncompleteLessonReleaseError
from .graph import topological_stages
from .html_safety import (
    HtmlProvenance,
    MAX_FRAGMENT_BYTES,
    SafeHtml,
    revalidate_safe_html,
    validate_fragment,
    validate_generated_fragment,
)
from .lessons import Lesson, MAX_LESSON_BYTES, load_lesson_bytes
from .render import Renderer
from .visualizations import LessonSectionRole, Visualization, render_visualization


_LESSON_ID: Final = re.compile(
    r"core-(0[1-9]|[12][0-9]|30)-[a-z0-9]+(?:-[a-z0-9]+)*\Z",
    re.ASCII,
)
MAX_LESSONS: Final = 30
# Thirty full textbook lessons fit comfortably in these budgets, while a
# malformed authoring tree cannot make CI read or render an unbounded corpus.
MAX_LESSON_COLLECTION_INPUT_BYTES: Final = 16 * 1024 * 1024
MAX_LESSON_ARTIFACT_BYTES: Final = 32 * 1024 * 1024
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
_CLOSE_FAILURE_NOTE: Final = "lesson descriptor also failed to close"


@dataclass(frozen=True, slots=True)
class LessonSection:
    """One validated authored section assigned to a logical production role."""

    role: LessonSectionRole
    html: SafeHtml


@dataclass(frozen=True, slots=True)
class LessonBody:
    """The exact six-section authored body snapshot."""

    sections: tuple[LessonSection, ...]


@dataclass(frozen=True, slots=True)
class LoadedLesson:
    """One immutable metadata/body snapshot bound to a lesson directory."""

    lesson: Lesson
    body: LessonBody
    metadata_bytes: bytes
    body_bytes: bytes


@dataclass(frozen=True, slots=True)
class LessonCollection:
    """Distinguish an absent lesson root from an intentionally empty one."""

    lessons: tuple[LoadedLesson, ...]
    directory_present: bool


def load_lessons_from_root(content_descriptor: int) -> LessonCollection:
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
            return LessonCollection(lessons=(), directory_present=False)
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
        loaded_items: list[LoadedLesson] = []
        remaining_input_bytes = MAX_LESSON_COLLECTION_INPUT_BYTES
        for name in names:
            item = _load_lesson_directory(
                lessons_fd,
                name,
                remaining_input_bytes,
            )
            consumed = len(item.metadata_bytes) + len(item.body_bytes)
            if consumed > remaining_input_bytes:
                raise CurriculumValidationError(
                    "lesson collection exceeds maximum input byte count"
                )
            remaining_input_bytes -= consumed
            loaded_items.append(item)
        loaded = tuple(loaded_items)
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
    except OSError as error:
        validation_error = CurriculumValidationError(
            "lessons cannot be read safely"
        )
        _retain_close_failure_note(error, validation_error)
        raise validation_error from None
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
            raise IncompleteLessonReleaseError(
                "draft lessons cannot form a structurally complete "
                "curriculum release"
            )

    prerequisites = {
        item.lesson.id: item.lesson.prerequisite_ids
        for item in loaded
    }
    stages = topological_stages(ids, prerequisites)
    by_id = {item.lesson.id: item for item in loaded}
    return LessonCollection(
        lessons=tuple(
            by_id[lesson_id]
            for stage in stages
            for lesson_id in stage
        ),
        directory_present=True,
    )


def _discover_lesson_names(directory_fd: int) -> tuple[str, ...]:
    names: list[str] = []
    ordinals: set[int] = set()
    try:
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                # Reject as soon as entry 31 is observed; exhausting scandir
                # first would make the count guard itself vulnerable to DoS.
                if len(names) >= MAX_LESSONS:
                    raise CurriculumValidationError(
                        "lesson collection exceeds maximum lesson count"
                    )
                name = entry.name
                match = (
                    _LESSON_ID.fullmatch(name)
                    if type(name) is str
                    else None
                )
                if match is None:
                    raise CurriculumValidationError(
                        "lesson directory name is unsafe"
                    )
                ordinal = int(match.group(1))
                if not 1 <= ordinal <= MAX_LESSONS:
                    raise CurriculumValidationError(
                        "lesson ordinal must be between 1 and 30"
                    )
                if ordinal in ordinals:
                    raise CurriculumValidationError(
                        "duplicate lesson ordinal"
                    )
                try:
                    node = entry.stat(follow_symlinks=False)
                except OSError:
                    raise CurriculumValidationError(
                        "lesson directory cannot be inspected"
                    ) from None
                _require_safe_node(
                    node,
                    f"lesson {name}",
                    directory=True,
                )
                ordinals.add(ordinal)
                names.append(name)
    except CurriculumValidationError:
        raise
    except OSError:
        raise CurriculumValidationError(
            "lessons cannot be discovered safely"
        ) from None

    return tuple(sorted(names))


def _load_lesson_directory(
    lessons_fd: int,
    name: str,
    remaining_input_bytes: int,
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
        entry_names: list[str] = []
        try:
            with os.scandir(descriptor) as entries:
                for entry in entries:
                    # Only the exact two-file pair is valid. Rejecting the
                    # third observed entry before reading its name bounds both
                    # enumeration and retained attacker-controlled data.
                    if len(entry_names) >= len(_PAIR):
                        raise CurriculumValidationError(
                            f"lesson {name} must contain the "
                            "lesson.json/body.html pair"
                        )
                    entry_name = entry.name
                    if type(entry_name) is not str:
                        raise CurriculumValidationError(
                            f"lesson {name} cannot be discovered safely"
                        )
                    entry_names.append(entry_name)
        except CurriculumValidationError:
            raise
        except OSError:
            raise CurriculumValidationError(
                f"lesson {name} cannot be discovered safely"
            ) from None
        if frozenset(entry_names) != _PAIR or len(entry_names) != len(_PAIR):
            raise CurriculumValidationError(
                f"lesson {name} must contain the lesson.json/body.html pair"
            )

        metadata, metadata_signature = _read_collection_file_at(
            descriptor,
            "lesson.json",
            MAX_LESSON_BYTES,
            remaining_input_bytes,
            f"lesson {name}/lesson.json",
        )
        remaining_input_bytes -= len(metadata)
        body_raw, body_signature = _read_collection_file_at(
            descriptor,
            "body.html",
            MAX_FRAGMENT_BYTES,
            remaining_input_bytes,
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
        body = parse_lesson_body(body_text)
        return LoadedLesson(
            lesson=lesson,
            body=body,
            metadata_bytes=metadata,
            body_bytes=body_raw,
        )
    except CurriculumValidationError:
        raise
    except OSError as error:
        validation_error = CurriculumValidationError(
            f"lesson {name} cannot be read safely"
        )
        _retain_close_failure_note(error, validation_error)
        raise validation_error from None
    finally:
        if descriptor is not None:
            _close_descriptor(descriptor, f"lesson {name} directory")


def _read_collection_file_at(
    directory_fd: int,
    name: str,
    per_file_maximum_bytes: int,
    remaining_collection_bytes: int,
    label: str,
) -> tuple[bytes, tuple[int, int, int, int, int, int]]:
    # Applying the smaller remaining budget before opening the file prevents a
    # late aggregate check from reading one otherwise-valid oversized lesson.
    maximum_bytes = min(
        per_file_maximum_bytes,
        remaining_collection_bytes,
    )
    if maximum_bytes < per_file_maximum_bytes:
        return _read_regular_file_at(
            directory_fd,
            name,
            maximum_bytes,
            label,
            maximum_error=(
                "lesson collection exceeds maximum input byte count"
            ),
        )
    return _read_regular_file_at(
        directory_fd,
        name,
        maximum_bytes,
        label,
    )


def _read_regular_file_at(
    directory_fd: int,
    name: str,
    maximum_bytes: int,
    label: str,
    *,
    maximum_error: str | None = None,
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
                maximum_error or f"{label} exceeds maximum byte count"
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
    active = sys.exception()
    try:
        os.close(descriptor)
    except OSError:
        if active is None:
            raise CurriculumValidationError(
                f"{label} descriptor close failed"
            ) from None
        # A cleanup fault is secondary to an in-flight validation/read error.
        # Preserve that primary error and attach only a content-free note.
        active.add_note(_CLOSE_FAILURE_NOTE)


def _retain_close_failure_note(
    source: BaseException,
    target: BaseException,
) -> None:
    if _CLOSE_FAILURE_NOTE in getattr(source, "__notes__", ()):
        target.add_note(_CLOSE_FAILURE_NOTE)


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


_SECTION_ID_PATTERNS: Final = (
    re.compile(r"(?:[a-z][a-z0-9-]*-)?why\Z", re.ASCII),
    re.compile(r"(?:[a-z][a-z0-9-]*-)?mental-model\Z", re.ASCII),
    re.compile(r"(?:[a-z][a-z0-9-]*-)?worked-example\Z", re.ASCII),
    re.compile(r"(?:[a-z][a-z0-9-]*-)?tradeoffs\Z", re.ASCII),
    re.compile(r"(?:knowledge-|[a-z][a-z0-9-]*-)?check\Z", re.ASCII),
    re.compile(r"(?:sources-next|[a-z][a-z0-9-]*-sources(?:-next)?)\Z", re.ASCII),
)


class _LessonBodyParser(_AuthoredBodyLinkParser):
    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self._source = source
        self._line_offsets: list[int] = [0]
        self._line_offsets.extend(
            index + 1 for index, character in enumerate(source) if character == "\n"
        )
        self._stack: list[str] = []
        self._section_start: int | None = None
        self.sections: list[str] = []

    def _offset(self) -> int:
        line, column = self.getpos()
        return self._line_offsets[line - 1] + column

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        super().handle_starttag(tag, attrs)
        normalized = tag.casefold()
        if normalized == "section":
            if self._stack:
                nested_id = {
                    name.casefold(): value for name, value in attrs
                }.get("id")
                if nested_id is not None and any(
                    pattern.fullmatch(nested_id)
                    for pattern in _SECTION_ID_PATTERNS
                ):
                    raise CurriculumValidationError(
                        "lesson body contains nested-section impersonation"
                    )
            else:
                if len(self.sections) >= len(LessonSectionRole):
                    raise CurriculumValidationError(
                        "lesson body must contain exactly six top-level sections"
                    )
                values = {name.casefold(): value for name, value in attrs}
                section_id = values.get("id")
                if (
                    section_id is None
                    or _SECTION_ID_PATTERNS[len(self.sections)].fullmatch(section_id)
                    is None
                ):
                    raise CurriculumValidationError(
                        "lesson body sections are not in the required order"
                    )
                self._section_start = self._offset()
        elif not self._stack:
            raise CurriculumValidationError(
                "lesson body may contain only top-level sections"
            )
        self._stack.append(normalized)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.casefold() == "section" or not self._stack:
            raise CurriculumValidationError(
                "lesson body may contain only complete top-level sections"
            )
        super().handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if not self._stack or self._stack[-1] != normalized:
            raise CurriculumValidationError("lesson body has unbalanced markup")
        self._stack.pop()
        if normalized == "section" and not self._stack:
            assert self._section_start is not None
            closing = self._source.find(">", self._offset())
            if closing < 0:
                raise CurriculumValidationError("lesson body has malformed markup")
            self.sections.append(self._source[self._section_start : closing + 1])
            self._section_start = None

    def handle_data(self, data: str) -> None:
        if not self._stack and data.strip():
            raise CurriculumValidationError(
                "lesson body contains text outside a section"
            )

    def handle_comment(self, data: str) -> None:
        if not self._stack:
            raise CurriculumValidationError(
                "lesson body contains a top-level comment"
            )


def parse_lesson_body(fragment: str) -> LessonBody:
    """Validate and split a body once, assigning roles only by fixed order."""
    if type(fragment) is not str:
        raise CurriculumValidationError("lesson body must be exact text")
    validate_fragment(fragment)
    parser = _LessonBodyParser(fragment)
    try:
        parser.feed(fragment)
        parser.close()
    except CurriculumValidationError:
        raise
    except Exception:
        raise CurriculumValidationError("lesson body cannot be parsed") from None
    if parser._stack or len(parser.sections) != len(LessonSectionRole):
        raise CurriculumValidationError(
            "lesson body must contain exactly six complete top-level sections"
        )
    return LessonBody(
        tuple(
            LessonSection(role, validate_fragment(section))
            for role, section in zip(
                LessonSectionRole, parser.sections, strict=True
            )
        )
    )


def render_lesson_body(
    lesson_id: str,
    body: LessonBody,
    visualizations: tuple[Visualization, ...],
) -> SafeHtml:
    """Interleave visuals after complete typed sections, never by DOM ID."""
    if type(body) is not LessonBody or type(visualizations) is not tuple:
        raise CurriculumValidationError("lesson body rendering input is invalid")
    if (
        type(body.sections) is not tuple
        or len(body.sections) != len(LessonSectionRole)
    ):
        raise CurriculumValidationError("lesson body sections are invalid")
    safe_sections: list[tuple[LessonSectionRole, SafeHtml]] = []
    for expected_role, section in zip(
        LessonSectionRole,
        body.sections,
        strict=True,
    ):
        if type(section) is not LessonSection or section.role is not expected_role:
            raise CurriculumValidationError("lesson body sections are invalid")
        safe_section = revalidate_safe_html(section.html)
        if safe_section.provenance is not HtmlProvenance.AUTHORED:
            raise CurriculumValidationError(
                "lesson body sections require authored HTML provenance"
            )
        safe_sections.append((section.role, safe_section))
    by_role: dict[LessonSectionRole, list[Visualization]] = {
        role: [] for role in LessonSectionRole
    }
    for visual in visualizations:
        if type(visual) is not Visualization:
            raise CurriculumValidationError("visualizations must be immutable models")
        by_role[visual.after_section].append(visual)
    rendered = "".join(
        section_html.value
        + "".join(
            render_visualization(lesson_id, visual).value
            for visual in by_role[role]
        )
        for role, section_html in safe_sections
    )
    # Authored sections were strict-validated during parsing; this second,
    # generated-grammar pass validates their typed interleaving with controls.
    return validate_generated_fragment(rendered)


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
    if len(loaded) > MAX_LESSONS:
        raise CurriculumValidationError(
            "lesson collection exceeds maximum lesson count"
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
    index_path = PurePosixPath("lessons/index.html")
    index_artifact = renderer.page(
        output_path=Path(index_path.as_posix()),
        title="コアレッスン",
        description="前提順に学ぶエビデンス中心のコアレッスン索引",
        content=index_content,
    ).encode("utf-8")
    artifacts = {index_path: index_artifact}
    artifact_bytes = len(index_artifact)
    if artifact_bytes > MAX_LESSON_ARTIFACT_BYTES:
        raise CurriculumValidationError(
            "lesson artifacts exceed maximum byte count"
        )
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
                "body": render_lesson_body(
                    lesson.id, item.body, lesson.visualizations
                ),
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
        artifact = renderer.page(
            output_path=output_path,
            title=lesson.title,
            description=lesson.summary,
            content=fragment,
        ).encode("utf-8")
        artifact_bytes += len(artifact)
        if artifact_bytes > MAX_LESSON_ARTIFACT_BYTES:
            raise CurriculumValidationError(
                "lesson artifacts exceed maximum byte count"
            )
        artifacts[PurePosixPath(output_path.as_posix())] = artifact
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
