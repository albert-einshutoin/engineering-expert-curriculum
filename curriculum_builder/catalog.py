"""Strict conversion and loading for the version-controlled curriculum catalog."""

from __future__ import annotations

import json
import hashlib
import hmac
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .errors import CurriculumValidationError
from .models import CatalogItem

LEGACY_SOURCE_SHA256 = "a55a0d0b1cfa3773031e787c2ce7ca0df34534e16a70b65ed1baa91975c82da8"
CANONICAL_CATALOG_SHA256 = "4f38b5f63931a7f06e13f90f5d9ef90a0a435f30dae5d4fe70720d730a057473"
_LEGACY_ROOT_FIELDS = {"version", "title", "generated", "domainCount", "moduleCount", "lessonCount", "tracks", "domains", "lessons"}
_DOMAIN_FIELDS = {"id", "slug", "title", "description", "prerequisites", "modules"}
_MODULE_FIELDS = {"index", "title", "concepts", "outcome"}
_LEGACY_LESSON_FIELDS = set(("id", "title", "domainId", "domainTitle", "domainSlug", "moduleIndex", "moduleTitle", "level", "levelLabel", "concepts", "outcome", "path"))


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CurriculumValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json_loads(raw: bytes, path: str | Path) -> object:
    """Decode UTF-8 JSON while rejecting duplicate keys at every object depth."""
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, CurriculumValidationError) as error:
        raise CurriculumValidationError(f"{path}: {error}") from error


def _item_dict(item: CatalogItem) -> dict[str, object]:
    return {"id": item.id, "title": item.title, "domainId": item.domain_id, "domainTitle": item.domain_title, "domainSlug": item.domain_slug, "moduleIndex": item.module_index, "moduleTitle": item.module_title, "level": item.level, "levelLabel": item.level_label, "concepts": list(item.concepts), "outcome": item.outcome, "coreLessonId": item.core_lesson_id}


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CurriculumValidationError(f"{label} must be a non-empty string")
    return value.strip()


def _require_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CurriculumValidationError(f"{label} must be an integer")
    return value


def _exact(value: Mapping[object, object], expected: set[str], label: str) -> None:
    invalid = sorted((key for key in value if not isinstance(key, str)), key=lambda key: (type(key).__name__, repr(key)))
    if invalid:
        raise CurriculumValidationError(f"{label} field names must be strings: {', '.join(repr(key) for key in invalid)}")
    if set(value) != expected:
        unknown = sorted(set(value) - expected)
        if unknown:
            raise CurriculumValidationError(f"unknown fields: {', '.join(unknown)}")
        raise CurriculumValidationError(f"{label} fields are invalid")


def _validate_legacy(source: Mapping[object, object], expected_lesson_count: int | None, expected_domain_count: int | None, expected_module_count: int | None) -> list[CatalogItem]:
    _exact(source, _LEGACY_ROOT_FIELDS, "legacy root")
    if source["version"] != 1 or isinstance(source["version"], bool):
        raise CurriculumValidationError("legacy version must be 1")
    _require_text(source["title"], "legacy title")
    _require_text(source["generated"], "legacy generated")
    domains, lessons, tracks = source["domains"], source["lessons"], source["tracks"]
    if not isinstance(domains, list) or not isinstance(lessons, list) or not isinstance(tracks, Mapping):
        raise CurriculumValidationError("legacy domains, lessons, and tracks have invalid types")
    domain_count, module_count, lesson_count = (_require_int(source[k], k) for k in ("domainCount", "moduleCount", "lessonCount"))
    if domain_count != len(domains) or lesson_count != len(lessons):
        raise CurriculumValidationError("legacy declared counts do not match data")
    if expected_lesson_count is not None and lesson_count != expected_lesson_count:
        raise CurriculumValidationError(f"legacy lessonCount must be {expected_lesson_count}")
    if expected_domain_count is not None and domain_count != expected_domain_count:
        raise CurriculumValidationError(f"legacy domainCount must be {expected_domain_count}")
    declarations: dict[tuple[int, int], Mapping[object, object]] = {}
    for domain in domains:
        if not isinstance(domain, Mapping):
            raise CurriculumValidationError("legacy domain must be an object")
        _exact(domain, _DOMAIN_FIELDS, "legacy domain")
        domain_id = _require_int(domain["id"], "domain id")
        _require_text(domain["slug"], "domain slug"); _require_text(domain["title"], "domain title")
        _require_text(domain["description"], "domain description")
        if not isinstance(domain["prerequisites"], list) or not isinstance(domain["modules"], list):
            raise CurriculumValidationError("legacy domain declarations have invalid types")
        for module in domain["modules"]:
            if not isinstance(module, Mapping): raise CurriculumValidationError("legacy module must be an object")
            _exact(module, _MODULE_FIELDS, "legacy module")
            module_index = _require_int(module["index"], "module index")
            if (domain_id, module_index) in declarations: raise CurriculumValidationError("duplicate legacy module declaration")
            _require_text(module["title"], "module title"); _require_text(module["outcome"], "module outcome")
            if not isinstance(module["concepts"], list): raise CurriculumValidationError("module concepts must be a list")
            declarations[(domain_id, module_index)] = module
    if module_count != len(declarations): raise CurriculumValidationError("legacy moduleCount does not match modules")
    if expected_module_count is not None and module_count != expected_module_count:
        raise CurriculumValidationError(f"legacy moduleCount must be {expected_module_count}")
    if not all(isinstance(key, str) and isinstance(value, list) for key, value in tracks.items()):
        raise CurriculumValidationError("legacy tracks must map names to lists")
    items: list[CatalogItem] = []
    for index, lesson in enumerate(lessons):
        if not isinstance(lesson, Mapping): raise CurriculumValidationError(f"legacy lesson {index} must be an object")
        _exact(lesson, _LEGACY_LESSON_FIELDS, "legacy lesson")
        _require_text(lesson["path"], "legacy path")
        raw = dict(lesson); raw.pop("path")
        try: item = CatalogItem.from_dict({**raw, "coreLessonId": None})
        except CurriculumValidationError as error: raise CurriculumValidationError(f"legacy lesson {index}: {error}") from error
        module = declarations.get((item.domain_id, item.module_index))
        if module is None or (item.domain_title, item.domain_slug, item.module_title, list(item.concepts), item.outcome) != (next(d for d in domains if d["id"] == item.domain_id)["title"], next(d for d in domains if d["id"] == item.domain_id)["slug"], module["title"], module["concepts"], module["outcome"]):
            raise CurriculumValidationError(f"legacy lesson {index} does not match declarations")
        items.append(item)
    return items


def canonicalize(source: Mapping[object, object], generated_from: str, *, source_sha256: str = LEGACY_SOURCE_SHA256, expected_lesson_count: int | None = None, expected_domain_count: int | None = None, expected_module_count: int | None = None) -> dict[str, object]:
    if not isinstance(source, Mapping): raise CurriculumValidationError("legacy root must be an object")
    return _catalog_document(_validate_legacy(source, expected_lesson_count, expected_domain_count, expected_module_count), _require_text(generated_from, "generatedFrom"), _require_sha(source_sha256), require_nonempty=False)

def _require_sha(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value): raise CurriculumValidationError("sourceSha256 must be a lowercase SHA-256 hex digest")
    return value


def _catalog_document(items: Sequence[CatalogItem], generated_from: str, source_sha256: str, *, require_nonempty: bool) -> dict[str, object]:
    if require_nonempty and not items: raise CurriculumValidationError("items must not be empty")
    if len({item.id for item in items}) != len(items): raise CurriculumValidationError("duplicate item id")
    return {"version": 1, "generatedFrom": generated_from, "sourceSha256": source_sha256, "items": [_item_dict(item) for item in sorted(items, key=lambda item: item.id)]}


def serialize_catalog_document(items: Sequence[CatalogItem | Mapping[str, object]], generated_from: str, source_sha256: str = LEGACY_SOURCE_SHA256) -> bytes:
    normalized = [item if isinstance(item, CatalogItem) else CatalogItem.from_dict(item) for item in items]
    document = _catalog_document(normalized, _require_text(generated_from, "generatedFrom"), _require_sha(source_sha256), require_nonempty=False)
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=False) + "\n").encode("utf-8")


def load_catalog(path: str | Path) -> tuple[CatalogItem, ...]:
    catalog_path = Path(path)
    try: raw = catalog_path.read_bytes()
    except OSError as error: raise CurriculumValidationError(f"{catalog_path}: cannot read catalog: {error}") from error
    document = strict_json_loads(raw, catalog_path)
    if not isinstance(document, Mapping): raise CurriculumValidationError(f"{catalog_path}: catalog root must be an object")
    if set(document) != {"version", "generatedFrom", "sourceSha256", "items"}: raise CurriculumValidationError(f"{catalog_path}: catalog root fields must be exactly version, generatedFrom, sourceSha256, items")
    if document["version"] != 1 or isinstance(document["version"], bool): raise CurriculumValidationError(f"{catalog_path}: catalog version must be 1")
    generated_from = _require_text(document["generatedFrom"], "generatedFrom")
    source_sha256 = _require_sha(document["sourceSha256"])
    if source_sha256 != LEGACY_SOURCE_SHA256: raise CurriculumValidationError(f"{catalog_path}: sourceSha256 does not match checked-in provenance")
    if not isinstance(document["items"], list): raise CurriculumValidationError(f"{catalog_path}: items must be a list")
    try: items = tuple(CatalogItem.from_dict(value) if isinstance(value, Mapping) else (_ for _ in ()).throw(CurriculumValidationError("item must be an object")) for value in document["items"])
    except CurriculumValidationError as error: raise CurriculumValidationError(f"{catalog_path}: {error}") from error
    try:
        _catalog_document(items, generated_from, source_sha256, require_nonempty=True)
    except CurriculumValidationError as error:
        raise CurriculumValidationError(f"{catalog_path}: {error}") from error
    if tuple(item.id for item in items) != tuple(sorted(item.id for item in items)): raise CurriculumValidationError(f"{catalog_path}: items must be sorted by id")
    if raw != serialize_catalog_document(items, generated_from, source_sha256): raise CurriculumValidationError(f"{catalog_path}: catalog bytes are not canonical")
    return items


def load_repository_catalog(path: str | Path = Path("content/catalog.json")) -> tuple[CatalogItem, ...]:
    """Load the checked-in artifact only when its fixed provenance pair matches."""
    catalog_path = Path(path)
    try: actual = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
    except OSError as error: raise CurriculumValidationError(f"{catalog_path}: cannot read catalog: {error}") from error
    if not hmac.compare_digest(actual, CANONICAL_CATALOG_SHA256):
        raise CurriculumValidationError(f"{catalog_path}: catalog SHA-256 mismatch: expected {CANONICAL_CATALOG_SHA256}, actual {actual}")
    return load_catalog(catalog_path)
