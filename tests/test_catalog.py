from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from curriculum_builder.catalog import LEGACY_SOURCE_SHA256, load_catalog, serialize_catalog_document
from curriculum_builder.errors import CurriculumValidationError


def item(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "D01-M01-L1", "title": "Intro", "domainId": 1,
        "domainTitle": "Domain", "domainSlug": "domain", "moduleIndex": 1,
        "moduleTitle": "Module", "level": 1, "levelLabel": "Basic",
        "concepts": ["one", "two"], "outcome": "Outcome", "coreLessonId": None,
    }
    value.update(overrides)
    return value


class CatalogLoaderTests(unittest.TestCase):
    def test_load_catalog_rejects_invalid_json_empty_unknown_duplicate_and_unsorted(self) -> None:
        cases = {
            "invalid.json": "{",
            "empty.json": json.dumps({"version": 1, "generatedFrom": "s", "items": []}),
            "unknown.json": json.dumps({"version": 1, "generatedFrom": "s", "items": [item()], "other": 1}),
            "duplicate.json": json.dumps({"version": 1, "generatedFrom": "s", "items": [item(), item()]}),
            "unsorted.json": json.dumps({"version": 1, "generatedFrom": "s", "items": [item(id="D01-M01-L2", level=2), item()]}),
        }
        with TemporaryDirectory() as directory:
            for name, content in cases.items():
                path = Path(directory) / name
                path.write_text(content, encoding="utf-8")
                with self.subTest(name=name):
                    with self.assertRaisesRegex(CurriculumValidationError, name):
                        load_catalog(path)

    def test_load_catalog_rejects_duplicate_keys_and_noncanonical_bytes(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            duplicate = root / "duplicate.json"
            duplicate.write_text('{"version":1,"version":1,"generatedFrom":"s","items":[]}', encoding="utf-8")
            with self.assertRaisesRegex(CurriculumValidationError, "duplicate JSON key: version"):
                load_catalog(duplicate)

            canonical = root / "canonical.json"
            canonical.write_bytes(serialize_catalog_document([item()], "source"))
            self.assertEqual(load_catalog(canonical)[0].id, "D01-M01-L1")
            canonical.write_text(canonical.read_text(encoding="utf-8").replace('"source"', '" source "'), encoding="utf-8")
            with self.assertRaisesRegex(CurriculumValidationError, "canonical"):
                load_catalog(canonical)

    def test_repository_catalog_has_complete_sorted_model_consistent_import(self) -> None:
        items = load_catalog(Path("content/catalog.json"))
        self.assertEqual(len(items), 1140)
        self.assertEqual(len({item.id for item in items}), 1140)
        self.assertEqual(len({item.domain_id for item in items}), 38)
        self.assertEqual(tuple(item.id for item in items), tuple(sorted(item.id for item in items)))
        self.assertEqual(LEGACY_SOURCE_SHA256, "a55a0d0b1cfa3773031e787c2ce7ca0df34534e16a70b65ed1baa91975c82da8")
        self.assertEqual(
            Path("content/catalog.json").read_bytes(),
            serialize_catalog_document(
                [
                    {
                        "id": entry.id, "title": entry.title, "domainId": entry.domain_id,
                        "domainTitle": entry.domain_title, "domainSlug": entry.domain_slug,
                        "moduleIndex": entry.module_index, "moduleTitle": entry.module_title,
                        "level": entry.level, "levelLabel": entry.level_label,
                        "concepts": list(entry.concepts), "outcome": entry.outcome,
                        "coreLessonId": entry.core_lesson_id,
                    }
                    for entry in items
                ],
                "prototype-v1",
            ),
        )


if __name__ == "__main__":
    unittest.main()
