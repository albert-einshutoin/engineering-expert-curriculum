from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from curriculum_builder.catalog import canonicalize
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

if __name__ == "__main__":
    unittest.main()
