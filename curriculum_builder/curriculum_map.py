"""Deterministically render the reviewable cross-artifact curriculum map."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
from pathlib import Path
import string
from typing import Final
import unicodedata

from .build import (
    MAX_CATALOG_BYTES,
    MAX_ROADMAP_BYTES,
    _DirectoryHandle,
    _open_trusted_directory,
    _read_stable_regular_file,
    _verify_directory_identity,
    parse_roadmap_bytes,
    validate_release_curriculum,
)
from .capstones import Capstone, load_capstones_from_content_fd
from .catalog import load_repository_catalog_bytes
from .competencies import (
    MAX_COMPETENCIES_BYTES,
    parse_competencies_bytes,
)
from .errors import CurriculumValidationError
from .lesson_rendering import LessonCollection, load_lessons_from_root
from .lessons import Lesson


BEGIN_GENERATED_MAP: Final = "<!-- BEGIN GENERATED CURRICULUM MAP -->"
END_GENERATED_MAP: Final = "<!-- END GENERATED CURRICULUM MAP -->"
_FRAMEWORK_ORDER: Final = ("CS2023", "SWEBOK", "SFIA")
_NATIVE_PATH_TYPE: Final = type(Path())
MAX_MARKDOWN_CELL_CHARACTERS: Final = 4_096
MAX_MARKDOWN_CELL_BYTES: Final = 16 * 1_024
_ASCII_PUNCTUATION: Final = frozenset(string.punctuation)
_UNSAFE_TEXT_CATEGORIES: Final = frozenset({"Cc", "Cf", "Cs", "Zl", "Zp"})


@dataclass(frozen=True, slots=True)
class _ReleaseInputs:
    """One comparable capture of every source that contributes to the map."""

    catalog_bytes: bytes
    roadmap_bytes: bytes
    lesson_snapshot: LessonCollection
    competency_bytes: bytes
    capstones: tuple[Capstone, ...]


def _markdown_cell(value: str) -> str:
    """Render reviewed source as bounded plain text inside a Markdown cell."""
    if type(value) is not str:
        raise CurriculumValidationError("markdown cell must be an exact string")
    if any(
        unicodedata.category(character) in _UNSAFE_TEXT_CATEGORIES
        for character in value
    ):
        raise CurriculumValidationError("markdown cell contains a control character")
    if len(value) > MAX_MARKDOWN_CELL_CHARACTERS or len(
        value.encode("utf-8")
    ) > MAX_MARKDOWN_CELL_BYTES:
        raise CurriculumValidationError("markdown cell exceeds maximum size")

    normalized = " ".join(value.split())
    # Numeric references keep punctuation visually intact without leaving GFM
    # syntax for raw HTML, autolinks, mentions, or issue references to activate.
    # Pipes and backslashes retain conventional Markdown escapes so table
    # parsers can distinguish cell boundaries without decoding HTML first.
    rendered: list[str] = []
    for character in normalized:
        if character == "\\":
            rendered.append("\\\\")
        elif character == "|":
            rendered.append("\\|")
        elif character in _ASCII_PUNCTUATION:
            rendered.append(f"&#{ord(character)};")
        else:
            rendered.append(character)
    return "".join(rendered)


def _capture_release_inputs(content: _DirectoryHandle) -> _ReleaseInputs:
    """Capture all map inputs through one pinned content directory."""
    lesson_snapshot = load_lessons_from_root(content.descriptor)
    lesson_ids = frozenset(
        item.lesson.id for item in lesson_snapshot.lessons
    )
    return _ReleaseInputs(
        catalog_bytes=_read_stable_regular_file(
            content,
            "catalog.json",
            MAX_CATALOG_BYTES,
        ),
        roadmap_bytes=_read_stable_regular_file(
            content,
            "roadmap.json",
            MAX_ROADMAP_BYTES,
        ),
        lesson_snapshot=lesson_snapshot,
        competency_bytes=_read_stable_regular_file(
            content,
            "competencies.json",
            MAX_COMPETENCIES_BYTES,
        ),
        capstones=load_capstones_from_content_fd(
            content.descriptor,
            expected_lesson_ids=lesson_ids,
        ),
    )


def render_generated_curriculum_map(repository_root: Path) -> str:
    """Return the complete sentinel block from validated release sources."""
    if type(repository_root) is not _NATIVE_PATH_TYPE:
        raise CurriculumValidationError("repository root must be an exact Path")

    with _open_trusted_directory(
        repository_root / "content",
        "repository content",
    ) as content:
        before = _capture_release_inputs(content)
        lessons = tuple(
            sorted(
                (item.lesson for item in before.lesson_snapshot.lessons),
                key=lambda lesson: int(
                    lesson.id.removeprefix("core-")[:2]
                ),
            )
        )
        lesson_ids = frozenset(lesson.id for lesson in lessons)
        catalog = load_repository_catalog_bytes(
            before.catalog_bytes,
            "catalog.json",
        )
        roadmap = parse_roadmap_bytes(
            before.roadmap_bytes,
            "roadmap.json",
            require_complete=True,
        )
        validate_release_curriculum(roadmap, lessons)
        matrix = parse_competencies_bytes(
            before.competency_bytes,
            expected_target_ids=lesson_ids,
            source_name="competencies.json",
        )
        capstones = before.capstones

        # A second complete capture prevents a valid but mixed old/new graph
        # from being documented when an authoring process writes concurrently.
        # As with the build, the same-euid ABA gap requires an exclusive workspace.
        if before != _capture_release_inputs(content):
            raise CurriculumValidationError(
                "release inputs changed during map generation"
            )
        _verify_directory_identity(content)

    catalog_sha256 = hashlib.sha256(before.catalog_bytes).hexdigest()

    mappings_by_lesson = defaultdict(dict)
    for mapping in matrix.mappings:
        mappings_by_lesson[mapping.target_id][mapping.framework] = mapping

    primary_owner: dict[str, str] = {}
    for capstone in capstones:
        for lesson_id in capstone.primary_exercises:
            if lesson_id in primary_owner:
                raise CurriculumValidationError(
                    f"duplicate primary capstone owner: {lesson_id}"
                )
            primary_owner[lesson_id] = capstone.id
    if set(primary_owner) != lesson_ids:
        raise CurriculumValidationError(
            "every release lesson needs one primary capstone owner"
        )

    lines = [
        BEGIN_GENERATED_MAP,
        "### リリース集計",
        "",
        "| 項目 | 件数・固定値 |",
        "|---|---|",
        f"| 保存カタログ | {len(catalog):,} items |",
        f"| カタログ SHA-256 | `{catalog_sha256}` |",
        f"| コアレッスン | {len(lessons)} structurally complete lessons |",
        f"| コンピテンシー対応 | {len(matrix.mappings)} mappings |",
        f"| 統合 Capstone | {len(capstones)} projects |",
        f"| Primary exercise coverage | {len(primary_owner)}/{len(lessons)} |",
        "",
        "### Framework baseline",
        "",
        "| Framework | Version | Official source | Verified |",
        "|---|---|---|---|",
    ]
    for framework in _FRAMEWORK_ORDER:
        source = matrix.framework_sources[framework]
        lines.append(
            "| "
            f"{framework} | {_markdown_cell(source.version)} | "
            f"[{framework}]({source.official_url}) | {source.verified_at} |"
        )

    lines.extend(
        [
            "",
            "### Mastery gates",
            "",
            "| Order | Gate | After | Artifact | Review evidence |",
            "|---:|---|---:|---|---|",
        ]
    )
    for order, gate in enumerate(roadmap.mastery_gates, start=1):
        lines.append(
            "| "
            f"{order} | `{gate.id}` | {gate.after} | "
            f"{_markdown_cell(gate.artifact)} | {_markdown_cell(gate.review)} |"
        )

    lines.extend(
        [
            "",
            "### 30-lesson release map",
            "",
            "| # | Lesson | Track / Stage | Prerequisites | Mastery gate | "
            "CS2023 | SWEBOK | SFIA | Primary / Supporting Capstone |",
            "|---:|---|---|---|---|---|---|---|---|",
        ]
    )
    nodes_by_id = {node.id: node for node in roadmap.nodes}
    for ordinal, lesson in enumerate(lessons, start=1):
        node = nodes_by_id[lesson.id]
        gate = next(
            gate for gate in roadmap.mastery_gates if ordinal <= gate.after
        )
        prerequisites = "<br>".join(
            f"`{value}`" for value in node.prerequisite_ids
        ) or "—"
        framework_cells = []
        for framework in _FRAMEWORK_ORDER:
            mapping = mappings_by_lesson[lesson.id][framework]
            framework_cells.append(
                f"`{_markdown_cell(mapping.competency_id)}` "
                f"{_markdown_cell(mapping.competency_name)} "
                f"({_markdown_cell(mapping.alignment)})"
            )
        owner = primary_owner[lesson.id]
        supporting = tuple(
            capstone.id
            for capstone in capstones
            if lesson.id in capstone.lesson_ids and capstone.id != owner
        )
        capstone_cell = f"Primary: `{owner}`"
        if supporting:
            capstone_cell += "<br>Supporting: " + ", ".join(
                f"`{value}`" for value in supporting
            )
        lines.append(
            "| "
            f"{ordinal} | `{lesson.id}`<br>{_markdown_cell(lesson.title)} | "
            f"{_markdown_cell(lesson.track)} / {lesson.stage} | "
            f"{prerequisites} | `{gate.id}` | "
            f"{framework_cells[0]} | {framework_cells[1]} | "
            f"{framework_cells[2]} | {capstone_cell} |"
        )

    lines.extend(
        [
            "",
            "### Capstone coverage",
            "",
            "| Capstone | Lessons | Primary exercises | Evidence kinds |",
            "|---|---:|---:|---|",
        ]
    )
    for capstone in capstones:
        lines.append(
            "| "
            f"`{capstone.id}` — {_markdown_cell(capstone.title)} | "
            f"{len(capstone.lesson_ids)} | {len(capstone.primary_exercises)} | "
            f"{', '.join(f'`{value}`' for value in capstone.evidence_kinds)} |"
        )
    lines.extend([END_GENERATED_MAP])
    return "\n".join(lines)


def replace_generated_curriculum_map(document: str, generated: str) -> str:
    """Replace exactly one generated block while preserving reviewed prose."""
    if document.count(BEGIN_GENERATED_MAP) != 1:
        raise CurriculumValidationError(
            "curriculum map must contain one generated-map start marker"
        )
    if document.count(END_GENERATED_MAP) != 1:
        raise CurriculumValidationError(
            "curriculum map must contain one generated-map end marker"
        )
    start = document.index(BEGIN_GENERATED_MAP)
    end = document.index(END_GENERATED_MAP) + len(END_GENERATED_MAP)
    if start >= end:
        raise CurriculumValidationError(
            "curriculum map generated markers are out of order"
        )
    return document[:start] + generated + document[end:]
