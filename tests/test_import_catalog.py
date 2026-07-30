from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from curriculum_builder.catalog import canonicalize, load_catalog
from curriculum_builder.errors import CurriculumValidationError
from tools.import_catalog import main


def lesson(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "D01-M01-L1", "title": " Intro ", "domainId": 1,
        "domainTitle": " Domain ", "domainSlug": "domain", "moduleIndex": 1,
        "moduleTitle": " Module ", "level": 1, "levelLabel": " Basic ",
        "concepts": [" one ", "two"], "outcome": " Outcome ", "path": "legacy.html",
    }
    value.update(overrides)
    return value


class CatalogImportTests(unittest.TestCase):
    def test_canonicalize_removes_only_path_adds_core_link_and_sorts(self) -> None:
        second = lesson(id="D01-M01-L2", level=2, title="Second")
        result = canonicalize({"version": 1, "lessons": [second, lesson()]}, " prototype-v1 ")

        self.assertEqual(result["version"], 1)
        self.assertEqual(result["generatedFrom"], "prototype-v1")
        self.assertEqual([item["id"] for item in result["items"]], ["D01-M01-L1", "D01-M01-L2"])
        self.assertNotIn("path", result["items"][0])
        self.assertIsNone(result["items"][0]["coreLessonId"])
        self.assertEqual(result["items"][0]["title"], "Intro")

    def test_canonicalize_rejects_unknown_legacy_field_and_duplicate_ids(self) -> None:
        with self.assertRaisesRegex(CurriculumValidationError, "unknown fields: extra"):
            canonicalize({"version": 1, "lessons": [lesson(extra=True)]}, "source")
        with self.assertRaisesRegex(CurriculumValidationError, "duplicate item id"):
            canonicalize({"version": 1, "lessons": [lesson(), lesson()]}, "source")

    def test_canonicalize_rejects_invalid_root_and_types(self) -> None:
        for source in ({"version": 2, "lessons": []}, {"version": 1, "lessons": {}}, {"version": 1, "lessons": ["no"]}):
            with self.subTest(source=source):
                with self.assertRaises(CurriculumValidationError):
                    canonicalize(source, "source")
        with self.assertRaises(CurriculumValidationError):
            canonicalize({"version": 1, "lessons": [lesson()]}, "  ")

    def test_load_catalog_rejects_invalid_json_empty_unknown_duplicate_and_unsorted(self) -> None:
        cases = {
            "invalid.json": "{",
            "empty.json": json.dumps({"version": 1, "generatedFrom": "s", "items": []}),
            "unknown.json": json.dumps({"version": 1, "generatedFrom": "s", "items": [lesson()], "other": 1}),
            "duplicate.json": json.dumps({"version": 1, "generatedFrom": "s", "items": [lesson(coreLessonId=None), lesson(coreLessonId=None)]}),
            "unsorted.json": json.dumps({"version": 1, "generatedFrom": "s", "items": [lesson(id="D01-M01-L2", level=2, coreLessonId=None), lesson(coreLessonId=None)]}),
        }
        with TemporaryDirectory() as directory:
            for name, content in cases.items():
                path = Path(directory) / name
                path.write_text(content, encoding="utf-8")
                with self.subTest(name=name):
                    with self.assertRaisesRegex(CurriculumValidationError, name):
                        load_catalog(path)

    def test_cli_is_deterministic_and_leaves_old_output_on_replace_failure(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "input.json", root / "catalog.json"
            source.write_text(json.dumps({"version": 1, "lessons": [lesson()]}), encoding="utf-8")
            self.assertEqual(main(["--input", str(source), "--output", str(output)]), 0)
            first = output.read_bytes()
            self.assertEqual(main(["--input", str(source), "--output", str(output)]), 0)
            self.assertEqual(first, output.read_bytes())
            with patch("tools.import_catalog.os.replace", side_effect=OSError("replace failed")):
                self.assertEqual(main(["--input", str(source), "--output", str(output)]), 1)
            self.assertEqual(output.read_bytes(), first)
            self.assertEqual(list(root.glob(".catalog-*.tmp")), [])

    def test_repository_catalog_has_complete_sorted_model_consistent_import(self) -> None:
        source = Path("$REPO_ROOT/data/curriculum.json")
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        items = load_catalog(Path("content/catalog.json"))
        self.assertEqual(len(items), 1140)
        self.assertEqual(len({item.id for item in items}), 1140)
        self.assertEqual(len({item.domain_id for item in items}), 38)
        self.assertEqual(tuple(item.id for item in items), tuple(sorted(item.id for item in items)))
        self.assertEqual(before, hashlib.sha256(source.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
