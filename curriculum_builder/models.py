"""Immutable models for the version-controlled curriculum catalog."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from .errors import CurriculumValidationError


CATALOG_FIELDS = (
    "id",
    "title",
    "domainId",
    "domainTitle",
    "domainSlug",
    "moduleIndex",
    "moduleTitle",
    "level",
    "levelLabel",
    "concepts",
    "outcome",
    "coreLessonId",
)

_REQUIRED_CATALOG_FIELDS = frozenset(CATALOG_FIELDS) - {"coreLessonId"}
_CATALOG_ID_PATTERN = re.compile(r"^D[0-9]{2}-M[0-9]{2}-L[1-3]$")
_DOMAIN_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class CatalogItem:
    """A strict catalog row; frozen fields and tuple concepts prevent accidental drift."""

    id: str
    title: str
    domain_id: int
    domain_title: str
    domain_slug: str
    module_index: int
    module_title: str
    level: int
    level_label: str
    concepts: tuple[str, ...]
    outcome: str
    core_lesson_id: str | None

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> CatalogItem:
        """Build a catalog item only when every canonical value is well-formed."""
        unknown_fields = sorted(set(raw) - set(CATALOG_FIELDS))
        if unknown_fields:
            raise CurriculumValidationError(f"unknown fields: {', '.join(unknown_fields)}")

        missing_fields = sorted(_REQUIRED_CATALOG_FIELDS - set(raw))
        if missing_fields:
            raise CurriculumValidationError(
                f"missing required fields: {', '.join(missing_fields)}"
            )

        item_id = _require_text(raw["id"], "id")
        if not _CATALOG_ID_PATTERN.fullmatch(item_id):
            raise CurriculumValidationError("id must match DNN-MNN-LN")

        domain_slug = _require_text(raw["domainSlug"], "domainSlug")
        if not _DOMAIN_SLUG_PATTERN.fullmatch(domain_slug):
            raise CurriculumValidationError("domainSlug must be lowercase ASCII kebab-case")

        level = _require_level(raw["level"])
        return cls(
            id=item_id,
            title=_require_text(raw["title"], "title"),
            domain_id=_require_positive_int(raw["domainId"], "domainId"),
            domain_title=_require_text(raw["domainTitle"], "domainTitle"),
            domain_slug=domain_slug,
            module_index=_require_positive_int(raw["moduleIndex"], "moduleIndex"),
            module_title=_require_text(raw["moduleTitle"], "moduleTitle"),
            level=level,
            level_label=_require_text(raw["levelLabel"], "levelLabel"),
            concepts=_require_concepts(raw["concepts"]),
            outcome=_require_text(raw["outcome"], "outcome"),
            core_lesson_id=_require_optional_text(raw.get("coreLessonId"), "coreLessonId"),
        )


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CurriculumValidationError(f"{field} must be a non-empty string")
    return value


def _require_optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field)


def _require_positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CurriculumValidationError(f"{field} must be a positive integer")
    return value


def _require_level(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value not in (1, 2, 3):
        raise CurriculumValidationError("level must be one of 1, 2, or 3")
    return value


def _require_concepts(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise CurriculumValidationError("concepts must be a non-empty list or tuple")

    concepts = tuple(_require_text(concept, "concepts item") for concept in value)
    if len(set(concepts)) != len(concepts):
        raise CurriculumValidationError("concepts must not contain duplicates")
    return concepts
