"""Canonical catalog conversion and strict on-disk catalog loading."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from .errors import CurriculumValidationError
from .models import CatalogItem


def _item_dict(item: CatalogItem) -> dict[str, object]:
    return {
        "id": item.id,
        "title": item.title,
        "domainId": item.domain_id,
        "domainTitle": item.domain_title,
        "domainSlug": item.domain_slug,
        "moduleIndex": item.module_index,
        "moduleTitle": item.module_title,
        "level": item.level,
        "levelLabel": item.level_label,
        "concepts": list(item.concepts),
        "outcome": item.outcome,
        "coreLessonId": item.core_lesson_id,
    }


def _require_generated_from(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CurriculumValidationError("generatedFrom must be a non-empty string")
    return value.strip()


def canonicalize(source: Mapping[object, object], generated_from: str) -> dict[str, object]:
    """Convert legacy version-one lessons into normalized, sorted catalog rows."""
    if not isinstance(source, Mapping):
        raise CurriculumValidationError("legacy root must be an object")
    if source.get("version") != 1 or isinstance(source.get("version"), bool):
        raise CurriculumValidationError("legacy version must be 1")
    lessons = source.get("lessons")
    if not isinstance(lessons, list):
        raise CurriculumValidationError("legacy lessons must be a list")

    items: list[CatalogItem] = []
    for index, raw_lesson in enumerate(lessons):
        if not isinstance(raw_lesson, Mapping):
            raise CurriculumValidationError(f"legacy lesson {index} must be an object")
        raw = dict(raw_lesson)
        raw.pop("path", None)
        raw.setdefault("coreLessonId", None)
        try:
            items.append(CatalogItem.from_dict(raw))
        except CurriculumValidationError as error:
            raise CurriculumValidationError(f"legacy lesson {index}: {error}") from error
    return _catalog_document(items, _require_generated_from(generated_from), require_nonempty=False)


def _catalog_document(
    items: list[CatalogItem], generated_from: str, *, require_nonempty: bool
) -> dict[str, object]:
    if require_nonempty and not items:
        raise CurriculumValidationError("items must not be empty")
    ids = [item.id for item in items]
    if len(set(ids)) != len(ids):
        raise CurriculumValidationError("duplicate item id")
    return {
        "version": 1,
        "generatedFrom": generated_from,
        "items": [_item_dict(item) for item in sorted(items, key=lambda item: item.id)],
    }


def load_catalog(path: str | Path) -> tuple[CatalogItem, ...]:
    """Load a complete canonical catalog, rejecting any malformed or drifting shape."""
    catalog_path = Path(path)
    try:
        with catalog_path.open(encoding="utf-8") as file:
            document = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise CurriculumValidationError(f"{catalog_path}: cannot read catalog: {error}") from error
    if not isinstance(document, Mapping):
        raise CurriculumValidationError(f"{catalog_path}: catalog root must be an object")
    expected = {"version", "generatedFrom", "items"}
    if set(document) != expected:
        raise CurriculumValidationError(f"{catalog_path}: catalog root fields must be exactly version, generatedFrom, items")
    if document["version"] != 1 or isinstance(document["version"], bool):
        raise CurriculumValidationError(f"{catalog_path}: catalog version must be 1")
    try:
        _require_generated_from(document["generatedFrom"])
    except CurriculumValidationError as error:
        raise CurriculumValidationError(f"{catalog_path}: {error}") from error
    raw_items = document["items"]
    if not isinstance(raw_items, list):
        raise CurriculumValidationError(f"{catalog_path}: items must be a list")
    items: list[CatalogItem] = []
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, Mapping):
            raise CurriculumValidationError(f"{catalog_path}: item {index} must be an object")
        try:
            items.append(CatalogItem.from_dict(cast(Mapping[object, object], raw)))
        except CurriculumValidationError as error:
            raise CurriculumValidationError(f"{catalog_path}: item {index}: {error}") from error
    try:
        _catalog_document(
            items, _require_generated_from(document["generatedFrom"]), require_nonempty=True
        )
    except CurriculumValidationError as error:
        raise CurriculumValidationError(f"{catalog_path}: {error}") from error
    ids = [item.id for item in items]
    if ids != sorted(ids):
        raise CurriculumValidationError(f"{catalog_path}: items must be sorted by id")
    return tuple(items)
