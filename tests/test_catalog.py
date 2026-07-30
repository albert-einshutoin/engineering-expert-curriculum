from __future__ import annotations

import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from curriculum_builder.catalog import (
    CANONICAL_CATALOG_SHA256,
    LEGACY_SOURCE_SHA256,
    load_catalog,
    load_catalog_bytes,
    load_repository_catalog,
    load_repository_catalog_bytes,
    serialize_catalog_document,
    strict_json_loads,
)
from curriculum_builder.errors import CurriculumValidationError


class BytesSubclass(bytes):
    pass


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
    def test_strict_json_sanitizes_unsafe_duplicate_key_labels(self) -> None:
        unsafe_keys = (
            "secret\nforged-log",
            "secret\0forged-log",
            "secret\u2066forged-log",
            "secret\u2028forged-log",
            "secret\u2029forged-log",
            "x" * 300,
        )
        for key in unsafe_keys:
            with self.subTest(key=repr(key)):
                encoded = json.dumps(key, ensure_ascii=False).encode("utf-8")
                raw = b"{" + encoded + b":1," + encoded + b":2}"
                with self.assertRaises(CurriculumValidationError) as caught:
                    strict_json_loads(raw, Path("fixture.json"))
                self.assertEqual(
                    str(caught.exception),
                    "fixture.json: duplicate JSON key: <unsafe>",
                )

    def test_strict_json_preserves_safe_duplicate_key_details(self) -> None:
        with self.assertRaises(CurriculumValidationError) as caught:
            strict_json_loads(
                b'{"version":1,"version":2}',
                Path("fixture.json"),
            )

        self.assertEqual(
            str(caught.exception),
            "fixture.json: duplicate JSON key: version",
        )
        self.assertIsInstance(
            caught.exception.__cause__,
            CurriculumValidationError,
        )

    def test_strict_json_rejects_float_overflow_without_leaking_tokens(
        self,
    ) -> None:
        for token in (b"1e999", b"-1e999"):
            with self.subTest(token=token):
                with self.assertRaises(CurriculumValidationError) as caught:
                    strict_json_loads(
                        b'{"value":' + token + b"}",
                        Path("fixture.json"),
                    )
                self.assertEqual(
                    str(caught.exception),
                    "fixture.json: invalid JSON floating-point value",
                )
                self.assertNotIn(token.decode("ascii"), str(caught.exception))

    def test_strict_json_rejects_overlong_decimal_without_leaking_it(
        self,
    ) -> None:
        token = b"0." + (b"1" * 5_000)
        with self.assertRaises(CurriculumValidationError) as caught:
            strict_json_loads(
                b'{"value":' + token + b"}",
                Path("fixture.json"),
            )

        self.assertEqual(
            str(caught.exception),
            "fixture.json: invalid JSON floating-point value",
        )
        self.assertNotIn("1111111111", str(caught.exception))

    def test_strict_json_keeps_ordinary_floats_as_finite_float_values(
        self,
    ) -> None:
        parsed = strict_json_loads(
            b'{"positive":1.25,"negative":-2.5e2}',
            Path("fixture.json"),
        )

        self.assertEqual(parsed, {"positive": 1.25, "negative": -250.0})
        self.assertIs(type(parsed["positive"]), float)  # type: ignore[index]
        self.assertIs(type(parsed["negative"]), float)  # type: ignore[index]

    def test_strict_json_rejects_non_finite_numbers(self) -> None:
        for constant in (b"NaN", b"Infinity", b"-Infinity"):
            with self.subTest(constant=constant):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    r"fixture\.json: non-finite JSON number",
                ) as caught:
                    strict_json_loads(
                        b'{"value":' + constant + b"}",
                        Path("fixture.json"),
                    )
                self.assertIsInstance(
                    caught.exception.__cause__,
                    CurriculumValidationError,
                )

    def test_strict_json_normalizes_huge_integer_errors_without_leaking_details(
        self,
    ) -> None:
        digits = b"9" * 10_000
        try:
            strict_json_loads(
                b'{"value":' + digits + b"}",
                Path("fixture.json"),
            )
        except BaseException as error:
            caught = error
        else:
            self.fail("huge JSON integer was accepted")

        self.assertIsInstance(caught, CurriculumValidationError)
        self.assertEqual(
            str(caught),
            "fixture.json: invalid JSON numeric value",
        )
        self.assertIsInstance(caught.__cause__, ValueError)
        self.assertNotIn("10000", str(caught))
        self.assertNotIn("digit", str(caught))

    def test_strict_json_normalizes_excessive_nesting_without_leaking_input(
        self,
    ) -> None:
        try:
            with patch(
                "curriculum_builder.catalog.json.loads",
                side_effect=RecursionError("private-nesting-detail"),
            ):
                strict_json_loads(b"[]", Path("fixture.json"))
        except BaseException as error:
            caught = error
        else:
            self.fail("recursive JSON parser failure was accepted")

        self.assertIsInstance(caught, CurriculumValidationError)
        self.assertEqual(str(caught), "fixture.json: JSON nesting is too deep")
        self.assertIsInstance(caught.__cause__, RecursionError)
        self.assertNotIn("private-nesting-detail", str(caught))

    def test_bytes_loaders_reject_mutable_views_and_subclasses(self) -> None:
        official_path = Path("content/catalog.json")
        official = official_path.read_bytes()
        for candidate in (
            bytearray(official),
            memoryview(official),
            BytesSubclass(official),
        ):
            with self.subTest(type=type(candidate).__name__):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    "catalog snapshot must be exact bytes",
                ):
                    load_catalog_bytes(  # type: ignore[arg-type]
                        candidate,
                        official_path,
                    )
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    "catalog snapshot must be exact bytes",
                ):
                    load_repository_catalog_bytes(  # type: ignore[arg-type]
                        candidate,
                        official_path,
                    )

    def test_bytes_loaders_parse_the_supplied_snapshot_and_fix_provenance(
        self,
    ) -> None:
        official_path = Path("content/catalog.json")
        official = official_path.read_bytes()
        self.assertEqual(
            load_repository_catalog_bytes(official, official_path),
            load_repository_catalog(official_path),
        )

        tampered = official.replace(
            b'"title": "',
            b'"title": "Changed ',
            1,
        )
        with self.assertRaisesRegex(
            CurriculumValidationError,
            "catalog SHA-256 mismatch",
        ):
            load_repository_catalog_bytes(tampered, official_path)

        fixture = serialize_catalog_document(
            [item(title="Pinned")],
            "fixture",
            source_sha256="0" * 64,
        )
        self.assertEqual(
            load_catalog_bytes(fixture, Path("fixture.json"))[0].title,
            "Pinned",
        )

    def test_repository_loader_parses_the_same_bytes_it_hashes(self) -> None:
        official = Path("content/catalog.json").read_bytes()
        altered = official.replace(b'"title": "', b'"title": "Changed ', 1)
        with patch("curriculum_builder.catalog.Path.read_bytes", side_effect=[official, altered]) as read:
            items = load_repository_catalog(Path("content/catalog.json"))
        self.assertEqual(read.call_count, 1)
        self.assertEqual(len(items), 1140)

    def test_provenance_is_required_for_canonicalization_and_serialization(self) -> None:
        with self.assertRaises(TypeError):
            serialize_catalog_document([item()], "source")

    def test_repository_loader_rejects_tampered_first_read(self) -> None:
        raw = Path("content/catalog.json").read_bytes().replace(b'"title": "', b'"title": "Changed ', 1)
        with patch("curriculum_builder.catalog.Path.read_bytes", return_value=raw):
            with self.assertRaisesRegex(CurriculumValidationError, "catalog SHA-256 mismatch"):
                load_repository_catalog(Path("content/catalog.json"))

    def test_repository_loader_rejects_source_provenance_even_with_matching_artifact_hash(self) -> None:
        raw = serialize_catalog_document([item()], "source", source_sha256="0" * 64)
        with patch("curriculum_builder.catalog.Path.read_bytes", return_value=raw), patch("curriculum_builder.catalog.CANONICAL_CATALOG_SHA256", hashlib.sha256(raw).hexdigest()):
            with self.assertRaisesRegex(CurriculumValidationError, "source SHA-256 mismatch"):
                load_repository_catalog(Path("content/catalog.json"))
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
            canonical.write_bytes(serialize_catalog_document([item()], "source", source_sha256="0" * 64))
            self.assertEqual(load_catalog(canonical)[0].id, "D01-M01-L1")
            canonical.write_text(canonical.read_text(encoding="utf-8").replace('"source"', '" source "'), encoding="utf-8")
            with self.assertRaisesRegex(CurriculumValidationError, "canonical"):
                load_catalog(canonical)

    def test_repository_catalog_has_complete_sorted_model_consistent_import(self) -> None:
        items = load_repository_catalog(Path("content/catalog.json"))
        self.assertEqual(len(items), 1140)
        self.assertEqual(len({item.id for item in items}), 1140)
        self.assertEqual(len({item.domain_id for item in items}), 38)
        self.assertEqual(tuple(item.id for item in items), tuple(sorted(item.id for item in items)))
        self.assertEqual(LEGACY_SOURCE_SHA256, "a55a0d0b1cfa3773031e787c2ce7ca0df34534e16a70b65ed1baa91975c82da8")
        self.assertEqual(CANONICAL_CATALOG_SHA256, "4f38b5f63931a7f06e13f90f5d9ef90a0a435f30dae5d4fe70720d730a057473")
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
                source_sha256=LEGACY_SOURCE_SHA256,
            ),
        )


if __name__ == "__main__":
    unittest.main()
