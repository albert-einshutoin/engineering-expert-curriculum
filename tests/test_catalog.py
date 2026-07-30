from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from curriculum_builder.catalog import load_catalog
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

    def test_repository_catalog_has_complete_sorted_model_consistent_import(self) -> None:
        source = Path("$REPO_ROOT/data/curriculum.json")
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        self.assertEqual(before, "a55a0d0b1cfa3773031e787c2ce7ca0df34534e16a70b65ed1baa91975c82da8")
        items = load_catalog(Path("content/catalog.json"))
        self.assertEqual(len(items), 1140)
        self.assertEqual(len({item.id for item in items}), 1140)
        self.assertEqual(len({item.domain_id for item in items}), 38)
        self.assertEqual(tuple(item.id for item in items), tuple(sorted(item.id for item in items)))
        self.assertEqual(before, hashlib.sha256(source.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
