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

    def test_canonicalizes_whitespace_and_detaches_concepts_from_input_list(self) -> None:
        concepts = [" retry ", " idempotency "]
        item = CatalogItem.from_dict(
            valid_raw(
                id=" D01-M02-L3 ",
                title=" Design reliable systems ",
                domainTitle=" Architecture ",
                domainSlug=" architecture ",
                moduleTitle=" Reliability ",
                levelLabel=" Advanced ",
                concepts=concepts,
                outcome=" Design a resilient service. ",
                coreLessonId=" lesson-001 ",
            )
        )
        concepts.append("mutation")

        self.assertEqual(item.id, "D01-M02-L3")
        self.assertEqual(item.title, "Design reliable systems")
        self.assertEqual(item.domain_title, "Architecture")
        self.assertEqual(item.domain_slug, "architecture")
        self.assertEqual(item.module_title, "Reliability")
        self.assertEqual(item.level_label, "Advanced")
        self.assertEqual(item.concepts, ("retry", "idempotency"))
        self.assertEqual(item.outcome, "Design a resilient service.")
        self.assertEqual(item.core_lesson_id, "lesson-001")

    def test_rejects_concepts_duplicated_after_whitespace_canonicalization(self) -> None:
        with self.assertRaisesRegex(
            CurriculumValidationError, r"^concepts must not contain duplicates$"
        ):
            CatalogItem.from_dict(valid_raw(concepts=["retry", " retry "]))

    def test_rejects_non_string_mapping_keys_deterministically(self) -> None:
        raw: dict[object, object] = valid_raw()
        raw[None] = "invalid"
        raw[1] = "also-invalid"

        with self.assertRaisesRegex(
            CurriculumValidationError, r"^field names must be strings: 1, None$"
        ):
            CatalogItem.from_dict(raw)

    def test_unknown_fields_take_precedence_over_missing_fields(self) -> None:
        with self.assertRaisesRegex(CurriculumValidationError, r"^unknown fields: path$"):
            CatalogItem.from_dict({"path": "legacy/path"})

    def test_rejects_id_components_that_do_not_match_structured_fields(self) -> None:
        cases = (
            ("domainId", 2, "id D01-M02-L3 does not match domainId: expected 1, actual 2"),
            ("moduleIndex", 3, "id D01-M02-L3 does not match moduleIndex: expected 2, actual 3"),
            ("level", 2, "id D01-M02-L3 does not match level: expected 3, actual 2"),
        )
        for field, value, message in cases:
            with self.subTest(field=field):
                with self.assertRaisesRegex(CurriculumValidationError, f"^{message}$"):
                    CatalogItem.from_dict(valid_raw(**{field: value}))


if __name__ == "__main__":
    unittest.main()
