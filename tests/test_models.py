from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from curriculum_builder.errors import CurriculumValidationError
from curriculum_builder.models import CATALOG_FIELDS, CatalogItem


def valid_raw(**overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "id": "D01-M02-L3",
        "title": "Design reliable systems",
        "domainId": 1,
        "domainTitle": "Architecture",
        "domainSlug": "architecture",
        "moduleIndex": 2,
        "moduleTitle": "Reliability",
        "level": 3,
        "levelLabel": "Advanced",
        "concepts": ["retries", "idempotency"],
        "outcome": "Design a resilient service.",
        "coreLessonId": "lesson-001",
    }
    raw.update(overrides)
    return raw


class CatalogItemTests(unittest.TestCase):
    def test_valid_item_maps_canonical_fields_and_is_immutable(self) -> None:
        item = CatalogItem.from_dict(valid_raw())

        self.assertEqual(
            CATALOG_FIELDS,
            (
                "id", "title", "domainId", "domainTitle", "domainSlug",
                "moduleIndex", "moduleTitle", "level", "levelLabel", "concepts",
                "outcome", "coreLessonId",
            ),
        )
        self.assertEqual(item.domain_id, 1)
        self.assertEqual(item.core_lesson_id, "lesson-001")
        self.assertEqual(item.concepts, ("retries", "idempotency"))
        with self.assertRaises(FrozenInstanceError):
            item.title = "Changed"  # type: ignore[misc]

    def test_rejects_invalid_id(self) -> None:
        with self.assertRaises(CurriculumValidationError):
            CatalogItem.from_dict(valid_raw(id="D1-M02-L3"))

    def test_rejects_unknown_legacy_path_field(self) -> None:
        with self.assertRaisesRegex(CurriculumValidationError, r"^unknown fields: path$"):
            CatalogItem.from_dict(valid_raw(path="legacy/path"))

    def test_rejects_missing_required_fields_in_sorted_error(self) -> None:
        raw = valid_raw()
        del raw["title"]
        del raw["outcome"]

        with self.assertRaisesRegex(
            CurriculumValidationError, r"^missing required fields: outcome, title$"
        ):
            CatalogItem.from_dict(raw)

    def test_rejects_blank_text_and_invalid_slug(self) -> None:
        for field, value in (("title", "  "), ("domainSlug", "Architecture")):
            with self.subTest(field=field):
                with self.assertRaises(CurriculumValidationError):
                    CatalogItem.from_dict(valid_raw(**{field: value}))

    def test_rejects_boolean_numbers_and_invalid_level_boundaries(self) -> None:
        for field, value in (("domainId", True), ("moduleIndex", False), ("level", True), ("level", 0), ("level", 4)):
            with self.subTest(field=field, value=value):
                with self.assertRaises(CurriculumValidationError):
                    CatalogItem.from_dict(valid_raw(**{field: value}))

    def test_rejects_empty_blank_or_duplicate_concepts(self) -> None:
        for concepts in ([], ["  "], ["retries", "retries"]):
            with self.subTest(concepts=concepts):
                with self.assertRaises(CurriculumValidationError):
                    CatalogItem.from_dict(valid_raw(concepts=concepts))

    def test_rejects_invalid_core_lesson_id_type_or_blank_value(self) -> None:
        for core_lesson_id in (1, "  "):
            with self.subTest(core_lesson_id=core_lesson_id):
                with self.assertRaises(CurriculumValidationError):
                    CatalogItem.from_dict(valid_raw(coreLessonId=core_lesson_id))


if __name__ == "__main__":
    unittest.main()
