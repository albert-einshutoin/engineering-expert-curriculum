from __future__ import annotations

import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from curriculum_builder.catalog import canonicalize
from curriculum_builder.errors import CurriculumValidationError
from tools.import_catalog import _read_source, main


def lesson(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "D01-M01-L1", "title": " Intro ", "domainId": 1,
        "domainTitle": " Domain ", "domainSlug": "domain", "moduleIndex": 1,
        "moduleTitle": " Module ", "level": 1, "levelLabel": " Basic ",
        "concepts": [" one ", "two"], "outcome": " Outcome ", "path": "legacy.html",
    }
    value.update(overrides)
    return value


def legacy_source(lessons: list[dict[str, object]]) -> dict[str, object]:
    first = lessons[0]
    return {
        "version": 1, "title": "Legacy", "generated": "now", "domainCount": 1,
        "moduleCount": 1, "lessonCount": len(lessons), "tracks": {},
        "domains": [{"id": 1, "slug": "domain", "title": "Domain", "description": "Description", "prerequisites": [], "modules": [{"index": 1, "title": "Module", "concepts": ["one", "two"], "outcome": "Outcome"}]}],
        "lessons": lessons,
    }


class CatalogImportTests(unittest.TestCase):
    def test_canonicalize_removes_only_path_adds_core_link_and_sorts(self) -> None:
        second = lesson(id="D01-M01-L2", level=2, title="Second")
        result = canonicalize(legacy_source([second, lesson()]), " prototype-v1 ")

        self.assertEqual(result["version"], 1)
        self.assertEqual(result["generatedFrom"], "prototype-v1")
        self.assertEqual([item["id"] for item in result["items"]], ["D01-M01-L1", "D01-M01-L2"])
        self.assertNotIn("path", result["items"][0])
        self.assertIsNone(result["items"][0]["coreLessonId"])
        self.assertEqual(result["items"][0]["title"], "Intro")

    def test_canonicalize_rejects_unknown_legacy_field_and_duplicate_ids(self) -> None:
        with self.assertRaisesRegex(CurriculumValidationError, "unknown fields: extra"):
            canonicalize(legacy_source([lesson(extra=True)]), "source")
        with self.assertRaisesRegex(CurriculumValidationError, "duplicate item id"):
            canonicalize(legacy_source([lesson(), lesson()]), "source")

    def test_canonicalize_rejects_invalid_root_and_types(self) -> None:
        for source in ({"version": 2, "lessons": []}, {"version": 1, "lessons": {}}, {"version": 1, "lessons": ["no"]}):
            with self.subTest(source=source):
                with self.assertRaises(CurriculumValidationError):
                    canonicalize(source, "source")
        with self.assertRaises(CurriculumValidationError):
            canonicalize(legacy_source([lesson()]), "  ")

    def test_cli_is_deterministic_and_leaves_old_output_on_replace_failure(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "input.json", root / "catalog.json"
            source.write_text('{"version":1,"version":1}', encoding="utf-8")
            with self.assertRaisesRegex(CurriculumValidationError, "duplicate JSON key: version"):
                _read_source(source)
            output.write_bytes(b"old")
            source.write_text(json.dumps({"version": 1, "lessons": [lesson()]}), encoding="utf-8")
            self.assertEqual(main(["--input", str(source), "--output", str(output), "--expected-source-sha256", "0" * 64]), 1)
            self.assertEqual(output.read_bytes(), b"old")
            self.assertEqual(list(root.glob(".catalog-*.tmp")), [])

if __name__ == "__main__":
    unittest.main()
