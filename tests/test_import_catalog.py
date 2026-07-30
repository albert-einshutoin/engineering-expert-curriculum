from __future__ import annotations

import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from curriculum_builder.catalog import canonicalize
from curriculum_builder.errors import CurriculumValidationError
from tools.import_catalog import CatalogPublicationDurabilityError, CatalogPublicationIntegrityError, _close_all, _open_parent, _read_source, _write_atomic, main


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
    def test_writer_fchmod_and_file_fsync_fail_before_publish(self) -> None:
        document = {"version": 1, "generatedFrom": "source", "sourceSha256": "a55a0d0b1cfa3773031e787c2ce7ca0df34534e16a70b65ed1baa91975c82da8", "items": [{**lesson(), "coreLessonId": None}]}; document["items"][0].pop("path")
        for target in ("fchmod", "fsync"):
            with self.subTest(target=target), TemporaryDirectory(dir=Path.cwd()) as directory:
                output = Path(directory) / "catalog.json"; output.write_bytes(b"old")
                patch_target = f"tools.import_catalog.os.{target}"
                with patch(patch_target, side_effect=OSError(f"{target} failed")), patch("tools.import_catalog.os.replace") as replace:
                    with self.assertRaisesRegex(OSError, f"{target} failed"): _write_atomic(output, document)
                self.assertEqual(replace.call_count, 0); self.assertEqual(output.read_bytes(), b"old"); self.assertEqual(list(output.parent.glob(".catalog-*.tmp")), [])

    def test_writer_reports_cleanup_failure_with_write_failure_as_cause(self) -> None:
        document = {"version": 1, "generatedFrom": "source", "sourceSha256": "a55a0d0b1cfa3773031e787c2ce7ca0df34534e16a70b65ed1baa91975c82da8", "items": [{**lesson(), "coreLessonId": None}]}; document["items"][0].pop("path")
        with TemporaryDirectory(dir=Path.cwd()) as directory:
            output = Path(directory) / "catalog.json"; output.write_bytes(b"old")
            with patch("tools.import_catalog._write_all", side_effect=OSError("write failed")), patch("tools.import_catalog._cleanup_temp", side_effect=OSError("cleanup failed")):
                with self.assertRaisesRegex(RuntimeError, "catalog temporary cleanup failed") as raised: _write_atomic(output, document)
            self.assertEqual(str(raised.exception.__cause__), "write failed"); self.assertEqual(output.read_bytes(), b"old")
    def test_writer_durability_events_are_ordered_before_publish(self) -> None:
        document = {"version": 1, "generatedFrom": "source", "sourceSha256": "a55a0d0b1cfa3773031e787c2ce7ca0df34534e16a70b65ed1baa91975c82da8", "items": [{**lesson(), "coreLessonId": None}]}; document["items"][0].pop("path")
        with TemporaryDirectory(dir=Path.cwd()) as directory:
            output = Path(directory) / "catalog.json"; events: list[str] = []; real_fsync = __import__("os").fsync; real_fchmod = __import__("os").fchmod; real_replace = __import__("os").replace
            def fsync(fd: int) -> None:
                events.append("parent-fsync" if __import__("stat").S_ISDIR(__import__("os").fstat(fd).st_mode) else "file-fsync"); real_fsync(fd)
            with patch("tools.import_catalog._write_all", side_effect=lambda fd, data: (events.append("write"), __import__("os").write(fd, data))[1]), patch("tools.import_catalog.os.fchmod", side_effect=lambda fd, mode: (events.append("chmod"), real_fchmod(fd, mode))[1]), patch("tools.import_catalog.os.fsync", side_effect=fsync), patch("tools.import_catalog.os.replace", side_effect=lambda *a, **k: (events.append("replace"), real_replace(*a, **k))[1]):
                _write_atomic(output, document)
            self.assertEqual(events, ["write", "chmod", "file-fsync", "replace", "parent-fsync"])
            self.assertEqual(output.stat().st_mode & 0o777, 0o644)

    def test_writer_reports_parent_fsync_failure_after_publish_without_rollback(self) -> None:
        document = {"version": 1, "generatedFrom": "source", "sourceSha256": "a55a0d0b1cfa3773031e787c2ce7ca0df34534e16a70b65ed1baa91975c82da8", "items": [{**lesson(), "coreLessonId": None}]}; document["items"][0].pop("path")
        with TemporaryDirectory(dir=Path.cwd()) as directory:
            output = Path(directory) / "catalog.json"; real_fsync = __import__("os").fsync; real_replace = __import__("os").replace; replaces = 0
            def fsync(fd: int) -> None:
                if __import__("stat").S_ISDIR(__import__("os").fstat(fd).st_mode): raise OSError("parent fsync")
                real_fsync(fd)
            def replace(*args: object, **kwargs: object) -> None:
                nonlocal replaces
                replaces += 1; real_replace(*args, **kwargs)
            with patch("tools.import_catalog.os.fsync", side_effect=fsync), patch("tools.import_catalog.os.replace", side_effect=replace):
                with self.assertRaises(CatalogPublicationDurabilityError) as raised: _write_atomic(output, document)
            self.assertEqual(str(raised.exception.__cause__), "parent fsync"); self.assertEqual(replaces, 1)
            self.assertTrue(output.exists()); self.assertEqual(output.stat().st_mode & 0o777, 0o644); self.assertEqual(list(output.parent.glob(".catalog-*.tmp")), [])
    def test_writer_rejects_hardlinked_input_identity_before_temp_creation(self) -> None:
        document = {"version": 1, "generatedFrom": "source", "sourceSha256": "a55a0d0b1cfa3773031e787c2ce7ca0df34534e16a70b65ed1baa91975c82da8", "items": [{**lesson(), "coreLessonId": None}]}; document["items"][0].pop("path")
        with TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory); source = root / "source"; source.write_bytes(b"source"); output = root / "output"; output.hardlink_to(source)
            identity = (source.stat().st_dev, source.stat().st_ino)
            with self.assertRaisesRegex(ValueError, "must not alias input"): _write_atomic(output, document, forbidden_identity=identity)
            self.assertEqual(source.read_bytes(), b"source"); self.assertEqual(list(root.glob(".catalog-*.tmp")), [])

    def test_writer_rejects_final_symlink_without_touching_target(self) -> None:
        document = {"version": 1, "generatedFrom": "source", "sourceSha256": "a55a0d0b1cfa3773031e787c2ce7ca0df34534e16a70b65ed1baa91975c82da8", "items": [{**lesson(), "coreLessonId": None}]}; document["items"][0].pop("path")
        with TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory); target = root / "target"; target.write_bytes(b"keep"); output = root / "catalog.json"; output.symlink_to(target)
            with self.assertRaises(ValueError): _write_atomic(output, document)
            self.assertTrue(output.is_symlink()); self.assertEqual(target.read_bytes(), b"keep"); self.assertEqual(list(root.glob(".catalog-*.tmp")), [])

    def test_writer_stops_when_pinned_parent_path_is_replaced(self) -> None:
        document = {"version": 1, "generatedFrom": "source", "sourceSha256": "a55a0d0b1cfa3773031e787c2ce7ca0df34534e16a70b65ed1baa91975c82da8", "items": [{**lesson(), "coreLessonId": None}]}; document["items"][0].pop("path")
        with TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory); output = root / "catalog.json"
            with patch("tools.import_catalog._same_parent", return_value=False):
                with self.assertRaisesRegex(RuntimeError, "output parent changed"): _write_atomic(output, document)
            self.assertFalse(output.exists()); self.assertEqual(list(root.glob(".catalog-*.tmp")), [])

    def test_writer_rejects_prepublication_temporary_name_substitution(self) -> None:
        document = {"version": 1, "generatedFrom": "source", "sourceSha256": "a55a0d0b1cfa3773031e787c2ce7ca0df34534e16a70b65ed1baa91975c82da8", "items": [{**lesson(), "coreLessonId": None}]}; document["items"][0].pop("path")
        with TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory); output = root / "catalog.json"; output.write_bytes(b"old")
            def replace_temp(*args: object) -> bool:
                temporary = next(root.glob(".catalog-*.tmp")); backup = root / "owned-backup.tmp"
                temporary.rename(backup); temporary.write_bytes(b"foreign")
                return True
            with patch("tools.import_catalog._same_parent", side_effect=replace_temp), patch("tools.import_catalog.os.replace") as publish:
                with self.assertRaisesRegex(RuntimeError, "catalog temporary changed before publish"): _write_atomic(output, document)
            self.assertEqual(publish.call_count, 0); self.assertEqual(output.read_bytes(), b"old")
            self.assertEqual(next(root.glob(".catalog-*.tmp")).read_bytes(), b"foreign")
            self.assertTrue((root / "owned-backup.tmp").exists())
    def test_close_all_attempts_every_descriptor_once_in_reverse_order(self) -> None:
        closed: list[int] = []
        def close(descriptor: int) -> None:
            closed.append(descriptor)
            if descriptor == 2: raise OSError("close two")
        owned = [1, 2, 3]
        with patch("tools.import_catalog.os.close", side_effect=close):
            failures = _close_all(owned)
        self.assertEqual(closed, [3, 2, 1])
        self.assertEqual(owned, [])
        self.assertEqual(len(failures), 1)

    def test_open_parent_closes_all_traversed_descriptors_after_failure(self) -> None:
        opened = iter([10, 11, 12])
        closed: list[int] = []
        def open_fd(*args: object, **kwargs: object) -> int:
            return next(opened)
        def close(fd: int) -> None:
            closed.append(fd)
            if fd == 11: raise OSError("injected close")
        with patch("tools.import_catalog.os.open", side_effect=open_fd), patch("tools.import_catalog.os.fstat", side_effect=OSError("fstat")), patch("tools.import_catalog.os.close", side_effect=close):
            with self.assertRaises(RuntimeError): _open_parent(Path("/one/two/catalog.json"))
        self.assertEqual(closed, [12, 11, 10])

    def test_read_source_preserves_read_cause_when_all_descriptor_closes_fail(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as directory:
            source = Path(directory) / "source.json"; source.write_text("{}", encoding="utf-8")
            real_close = __import__("os").close; closed: list[int] = []
            def close(fd: int) -> None:
                closed.append(fd); real_close(fd); raise OSError(f"close {fd}")
            with patch("tools.import_catalog.os.read", side_effect=OSError("read failed")), patch("tools.import_catalog.os.close", side_effect=close):
                with self.assertRaisesRegex(RuntimeError, "source descriptor close failed") as raised:
                    _read_source(source)
            self.assertIsInstance(raised.exception.__cause__, OSError)
            self.assertEqual(str(raised.exception.__cause__), "read failed")
            self.assertGreaterEqual(len(closed), 2)
            self.assertGreaterEqual(len(closed), 2)

    def test_writer_keeps_write_cause_through_temp_and_parent_close_failures(self) -> None:
        document = {"version": 1, "generatedFrom": "source", "sourceSha256": "a55a0d0b1cfa3773031e787c2ce7ca0df34534e16a70b65ed1baa91975c82da8", "items": [{**lesson(), "coreLessonId": None}]}
        document["items"][0].pop("path")
        with TemporaryDirectory(dir=Path.cwd()) as directory:
            output = Path(directory) / "catalog.json"; output.write_bytes(b"old")
            real_close = __import__("os").close; closed: list[int] = []
            def close(fd: int) -> None:
                closed.append(fd); real_close(fd); raise OSError(f"close {fd}")
            with patch("tools.import_catalog._write_all", side_effect=OSError("write failed")), patch("tools.import_catalog.os.close", side_effect=close), patch("tools.import_catalog.os.replace") as replace:
                with self.assertRaisesRegex(RuntimeError, "output parent close failed") as raised: _write_atomic(output, document)
            self.assertEqual(replace.call_count, 0)
            self.assertEqual(output.read_bytes(), b"old")
            self.assertEqual(len(closed), len(set(closed)))
            self.assertIsNotNone(raised.exception.__cause__)
            self.assertIn("catalog temporary close failed", str(raised.exception.__cause__))
            self.assertEqual(str(raised.exception.__cause__.__cause__), "write failed")

    def test_writer_keeps_success_after_published_parent_close_failures(self) -> None:
        document = {"version": 1, "generatedFrom": "source", "sourceSha256": "a55a0d0b1cfa3773031e787c2ce7ca0df34534e16a70b65ed1baa91975c82da8", "items": [{**lesson(), "coreLessonId": None}]}
        document["items"][0].pop("path")
        with TemporaryDirectory(dir=Path.cwd()) as directory:
            output = Path(directory) / "catalog.json"; real_close = __import__("os").close; real_replace = __import__("os").replace
            published = False; closed: list[int] = []
            def replace(*args: object, **kwargs: object) -> None:
                nonlocal published
                real_replace(*args, **kwargs); published = True
            def close(fd: int) -> None:
                closed.append(fd); real_close(fd)
                if published: raise OSError(f"postcommit close {fd}")
            with patch("tools.import_catalog.os.replace", side_effect=replace), patch("tools.import_catalog.os.close", side_effect=close):
                _write_atomic(output, document)
            self.assertEqual(output.stat().st_mode & 0o777, 0o644)
            self.assertTrue(output.read_bytes().endswith(b"\n"))
            self.assertGreaterEqual(len(closed), 2)
    def test_writer_rejects_missing_parent_symlink_and_non_regular_target(self) -> None:
        document = {"version": 1, "generatedFrom": "source", "sourceSha256": "a55a0d0b1cfa3773031e787c2ce7ca0df34534e16a70b65ed1baa91975c82da8", "items": [{**lesson(), "coreLessonId": None}]}
        # The writer receives canonical rows, so remove only the legacy path here.
        document["items"][0].pop("path")
        with TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                _write_atomic(root / "missing" / "catalog.json", document)
            target = root / "target"; target.mkdir(mode=0o700)
            link = root / "link"; link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(OSError): _write_atomic(link / "catalog.json", document)
            with self.assertRaises(ValueError): _write_atomic(target, document)

    def test_writer_publishes_mode_and_keeps_old_output_when_replace_fails(self) -> None:
        document = {"version": 1, "generatedFrom": "source", "sourceSha256": "a55a0d0b1cfa3773031e787c2ce7ca0df34534e16a70b65ed1baa91975c82da8", "items": [{**lesson(), "coreLessonId": None}]}
        document["items"][0].pop("path")
        with TemporaryDirectory(dir=Path.cwd()) as directory:
            output = Path(directory) / "catalog.json"
            _write_atomic(output, document)
            self.assertEqual(output.stat().st_mode & 0o777, 0o644)
            before = output.read_bytes()
            with patch("tools.import_catalog.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"): _write_atomic(output, document)
            self.assertEqual(output.read_bytes(), before)
            self.assertEqual(list(output.parent.glob(".catalog-*.tmp")), [])

    def test_writer_reports_post_replace_same_uid_substitution_without_rollback(self) -> None:
        document = {"version": 1, "generatedFrom": "source", "sourceSha256": "a55a0d0b1cfa3773031e787c2ce7ca0df34534e16a70b65ed1baa91975c82da8", "items": [{**lesson(), "coreLessonId": None}]}
        document["items"][0].pop("path")
        with TemporaryDirectory(dir=Path.cwd()) as directory:
            output = Path(directory) / "catalog.json"; output.write_bytes(b"old")
            real_replace = __import__("os").replace
            def substitute(source: str, target: str, **kwargs: object) -> None:
                real_replace(source, target, **kwargs)
                Path(directory, "foreign").write_bytes(b"foreign")
                real_replace("foreign", target, **kwargs)
            with patch("tools.import_catalog.os.replace", side_effect=substitute):
                with self.assertRaises(CatalogPublicationIntegrityError): _write_atomic(output, document)
            self.assertEqual(output.read_bytes(), b"foreign")
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
        with TemporaryDirectory(dir=Path.cwd()) as directory:
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
