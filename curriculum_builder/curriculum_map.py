"""Deterministically render the reviewable cross-artifact curriculum map."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Final

from .build import (
    MAX_ROADMAP_BYTES,
    parse_roadmap_bytes,
    validate_release_curriculum,
)
from .capstones import load_capstones
from .catalog import CANONICAL_CATALOG_SHA256, load_catalog
from .competencies import load_competencies
from .errors import CurriculumValidationError
from .lesson_io import read_stable_lesson_file
from .lessons import Lesson, load_lesson


BEGIN_GENERATED_MAP: Final = "<!-- BEGIN GENERATED CURRICULUM MAP -->"
END_GENERATED_MAP: Final = "<!-- END GENERATED CURRICULUM MAP -->"
_FRAMEWORK_ORDER: Final = ("CS2023", "SWEBOK", "SFIA")
_NATIVE_PATH_TYPE: Final = type(Path())


def _markdown_cell(value: str) -> str:
    """Keep generated tables stable even if reviewed source text uses pipes."""
    return " ".join(value.split()).replace("|", "\\|")


def _release_lessons(root: Path) -> tuple[Lesson, ...]:
    lessons_root = root / "content/lessons"
    lessons = tuple(
        load_lesson(path)
        for path in sorted(lessons_root.glob("*/lesson.json"))
    )
    return tuple(
        sorted(
            lessons,
            key=lambda lesson: int(lesson.id.removeprefix("core-")[:2]),
        )
    )


def render_generated_curriculum_map(repository_root: Path) -> str:
    """Return the complete sentinel block from validated release sources."""
    if type(repository_root) is not _NATIVE_PATH_TYPE:
        raise CurriculumValidationError("repository root must be an exact Path")

    lessons = _release_lessons(repository_root)
    roadmap_path = repository_root / "content/roadmap.json"
    roadmap = parse_roadmap_bytes(
        read_stable_lesson_file(roadmap_path, MAX_ROADMAP_BYTES),
        roadmap_path.name,
        require_complete=True,
    )
    validate_release_curriculum(roadmap, lessons)
    lesson_ids = frozenset(lesson.id for lesson in lessons)
    matrix = load_competencies(
        repository_root / "content/competencies.json",
        expected_target_ids=lesson_ids,
    )
    capstones = load_capstones(repository_root / "content/capstones")
    catalog = load_catalog(repository_root / "content/catalog.json")

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
        f"| カタログ SHA-256 | `{CANONICAL_CATALOG_SHA256}` |",
        f"| コアレッスン | {len(lessons)} complete lessons |",
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
