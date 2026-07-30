from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.migrate_prototype import LEGACY_PATHS, main, preserve_prototype


class PrototypeMigrationTests(unittest.TestCase):
    def _write_fixture(self, root: Path) -> None:
        (root / "assets").mkdir()
        (root / "assets" / "styles.css").write_text("body{}", encoding="utf-8")
        (root / "index.html").write_text("<main>legacy</main>", encoding="utf-8")

    def test_preserves_only_allowlisted_files_and_writes_verified_manifest(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            (root / ".git").mkdir()
            archive = root / ".archive" / "prototype-v1"

            manifest = preserve_prototype(root, archive)

            self.assertTrue((root / "index.html").exists())
            self.assertTrue((archive / "index.html").exists())
            self.assertTrue((root / ".git").exists())
            expected_files = {
                "assets/styles.css": hashlib.sha256(b"body{}").hexdigest(),
                "index.html": hashlib.sha256(b"<main>legacy</main>").hexdigest(),
            }
            self.assertEqual(manifest["algorithm"], "sha256")
            self.assertEqual(manifest["fileCount"], 2)
            self.assertEqual(manifest["byteCount"], len(b"body{}") + len(b"<main>legacy</main>"))
            self.assertEqual(manifest["files"], expected_files)
            saved = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, manifest)

    def test_allowlist_exactly_matches_the_legacy_paths(self) -> None:
        self.assertEqual(
            LEGACY_PATHS,
            (
                "README.txt", "assets", "daily.html", "data", "domains", "guide.html",
                "index.html", "progress.html", "roadmap.html", "scheduled", "source",
            ),
        )

    def test_refuses_to_overwrite_an_existing_archive(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "index.html").write_text("legacy", encoding="utf-8")
            archive = root / ".archive" / "prototype-v1"
            archive.mkdir(parents=True)

            with self.assertRaisesRegex(FileExistsError, "archive already exists"):
                preserve_prototype(root, archive)

    def test_refuses_an_empty_allowlisted_source(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            archive_parent = root / ".archive"
            with self.assertRaisesRegex(FileNotFoundError, "no allowlisted prototype files found"):
                preserve_prototype(root, archive_parent / "prototype-v1")
            self.assertFalse(archive_parent.exists())

    def test_copy_failure_leaves_source_and_archive_untouched(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive = root / ".archive" / "prototype-v1"

            with patch("tools.migrate_prototype._copy_allowlisted_tree", side_effect=OSError("copy failed")):
                with self.assertRaisesRegex(OSError, "copy failed"):
                    preserve_prototype(root, archive)

            self.assertEqual((root / "index.html").read_text(encoding="utf-8"), "<main>legacy</main>")
            self.assertFalse(os.path.lexists(archive))

    def test_checksum_failure_leaves_source_and_archive_untouched(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive = root / ".archive" / "prototype-v1"

            with patch(
                "tools.migrate_prototype._snapshot",
                side_effect=[
                    {"index.html": {"sha256": "a", "byteCount": 1}},
                    {"index.html": {"sha256": "a", "byteCount": 1}},
                    {"index.html": {"sha256": "different", "byteCount": 1}},
                ],
            ):
                with self.assertRaisesRegex(RuntimeError, "prototype checksum verification failed"):
                    preserve_prototype(root, archive)

            self.assertTrue((root / "index.html").exists())
            self.assertFalse(os.path.lexists(archive))
            self.assertFalse((root / ".archive").exists())

    def test_reservation_refuses_a_competing_archive_without_overwriting_it(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive = root / ".archive" / "prototype-v1"

            def create_competing_archive(parent_fd: int, name: str) -> None:
                os.mkdir(name, dir_fd=parent_fd)
                (archive / "sentinel.txt").write_text("keep", encoding="utf-8")
                os.mkdir(name, dir_fd=parent_fd)

            with patch("tools.migrate_prototype._reserve_archive_at", side_effect=create_competing_archive):
                with self.assertRaises(FileExistsError):
                    preserve_prototype(root, archive)

            self.assertTrue((root / "index.html").exists())
            self.assertEqual((archive / "sentinel.txt").read_text(encoding="utf-8"), "keep")
            self.assertFalse((archive / "manifest.json").exists())

    def test_manifest_failure_cleans_reserved_archive_and_retains_source(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive = root / ".archive" / "prototype-v1"

            with patch("tools.migrate_prototype._write_manifest", side_effect=OSError("manifest failed")):
                with self.assertRaisesRegex(OSError, "manifest failed"):
                    preserve_prototype(root, archive)

            self.assertTrue((root / "index.html").exists())
            self.assertFalse(os.path.lexists(archive))
            self.assertFalse((root / ".archive").exists())

    def test_pre_commit_directory_fsync_failure_never_renames_manifest(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive = root / ".archive" / "prototype-v1"
            real_replace = os.replace

            with patch("tools.migrate_prototype.os.fsync", side_effect=[None, OSError("directory fsync failed")]):
                with patch("tools.migrate_prototype.os.replace", wraps=real_replace) as replace:
                    with self.assertRaisesRegex(OSError, "directory fsync failed"):
                        preserve_prototype(root, archive)

            self.assertTrue((root / "index.html").exists())
            self.assertFalse(os.path.lexists(archive))
            self.assertFalse(
                any(Path(call.args[1]).name == "manifest.json" for call in replace.call_args_list)
            )

    def test_post_commit_close_failure_keeps_manifest_and_closes_all_descriptors(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive = root / ".archive" / "prototype-v1"
            original_cwd = Path.cwd()
            attempted: list[int] = []

            def close_with_reported_failure(descriptors: tuple[int | None, ...]) -> list[OSError]:
                for descriptor in descriptors:
                    if descriptor is not None:
                        attempted.append(descriptor)
                        os.close(descriptor)
                return [OSError("first close failed")]

            with patch("tools.migrate_prototype._close_all", side_effect=close_with_reported_failure):
                manifest = preserve_prototype(root, archive)

            self.assertEqual(manifest["fileCount"], 2)
            self.assertTrue((archive / "manifest.json").exists())
            self.assertEqual(Path.cwd(), original_cwd)
            self.assertEqual(len(attempted), 2)

    def test_rejects_a_symlinked_source(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            actual = root / "actual"
            actual.mkdir()
            source_link = root / "source-link"
            source_link.symlink_to(actual, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "source.*symbolic link"):
                preserve_prototype(source_link, root / "archive")

    def test_rejects_a_dangling_archive_symlink(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive = root / "archive"
            archive.symlink_to(root / "missing")

            with self.assertRaisesRegex(FileExistsError, "archive already exists"):
                preserve_prototype(root, archive)

    def test_rejects_a_nested_symlink(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "assets").mkdir()
            (root / "outside").write_text("outside", encoding="utf-8")
            (root / "assets" / "link").symlink_to(root / "outside")

            with self.assertRaisesRegex(ValueError, "symbolic links are not supported"):
                preserve_prototype(root, root / ".archive" / "prototype-v1")

    def test_rejects_special_files_when_supported(self) -> None:
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO is not supported on this platform")
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "assets").mkdir()
            os.mkfifo(root / "assets" / "stream")

            with self.assertRaisesRegex(ValueError, "unsupported file type"):
                preserve_prototype(root, root / ".archive" / "prototype-v1")

    def test_rejects_archive_inside_an_allowlisted_subtree(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)

            with self.assertRaisesRegex(ValueError, "archive.*allowlisted"):
                preserve_prototype(root, root / "assets" / "archive")

    def test_rejects_missing_allowlisted_archive_subtree_without_creating_it(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "index.html").write_text("legacy", encoding="utf-8")
            assets = root / "assets"

            with self.assertRaisesRegex(ValueError, "archive.*allowlisted"):
                preserve_prototype(root, assets / "archive")

            self.assertFalse(assets.exists())

    def test_copy_failure_removes_new_archive_parent(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive_parent = root / ".archive"
            archive = archive_parent / "prototype-v1"

            with patch("tools.migrate_prototype._copy_allowlisted_tree", side_effect=OSError("copy failed")):
                with self.assertRaisesRegex(OSError, "copy failed"):
                    preserve_prototype(root, archive)

            self.assertFalse(archive_parent.exists())

    def test_copy_failure_remains_the_cause_when_parent_cleanup_fails(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive_parent = root / ".archive"
            archive = archive_parent / "prototype-v1"
            real_rmdir = Path.rmdir

            def fail_parent_cleanup(path: Path) -> None:
                if path == archive_parent:
                    raise OSError("parent cleanup failed")
                real_rmdir(path)

            with patch("tools.migrate_prototype._copy_allowlisted_tree", side_effect=OSError("copy failed")):
                with patch.object(Path, "rmdir", autospec=True, side_effect=fail_parent_cleanup):
                    with self.assertRaisesRegex(RuntimeError, "parent cleanup failed") as error:
                        preserve_prototype(root, archive)

            self.assertIsInstance(error.exception.__cause__, OSError)
            self.assertEqual(str(error.exception.__cause__), "copy failed")
            self.assertTrue((root / "index.html").exists())
            self.assertFalse(archive.exists())

    def test_parent_replacement_after_reservation_never_deletes_foreign_archive(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive_parent = root / ".archive"
            archive = archive_parent / "prototype-v1"
            moved_parent = root / ".archive-owned"
            foreign_sentinel = archive / "sentinel.txt"

            def replace_parent_then_fail(source: Path, staging: Path) -> None:
                archive_parent.rename(moved_parent)
                archive_parent.mkdir()
                archive.mkdir()
                foreign_sentinel.write_text("foreign", encoding="utf-8")
                raise OSError("copy failed after parent replacement")

            with patch(
                "tools.migrate_prototype._copy_allowlisted_tree",
                side_effect=replace_parent_then_fail,
            ):
                with self.assertRaisesRegex(OSError, "copy failed after parent replacement"):
                    preserve_prototype(root, archive)

            self.assertEqual(foreign_sentinel.read_text(encoding="utf-8"), "foreign")
            self.assertTrue((root / "index.html").exists())

    def test_archive_replacement_before_open_preserves_foreign_sentinel(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive_parent = root / ".archive"
            archive = archive_parent / "prototype-v1"
            moved_archive = archive_parent / "reserved-original"
            sentinel = archive / "sentinel.txt"
            real_open = os.open
            replaced = False

            def replace_before_archive_open(path: str, flags: int, *args: object, **kwargs: object) -> int:
                nonlocal replaced
                if not replaced and path == "prototype-v1" and "dir_fd" in kwargs:
                    replaced = True
                    archive.rename(moved_archive)
                    archive.mkdir()
                    sentinel.write_text("foreign", encoding="utf-8")
                return real_open(path, flags, *args, **kwargs)

            with patch("tools.migrate_prototype.os.open", side_effect=replace_before_archive_open):
                with self.assertRaisesRegex(RuntimeError, "reserved archive changed before opening"):
                    preserve_prototype(root, archive)

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "foreign")
            self.assertTrue(archive.exists())
            self.assertTrue((root / "index.html").exists())
            self.assertFalse((archive / "manifest.json").exists())

    def test_rejects_casefolded_allowlist_archive_boundary_before_parent_creation(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "index.html").write_text("legacy", encoding="utf-8")
            archive = root / "ASSETS" / "archive"

            with self.assertRaisesRegex(ValueError, "archive.*allowlisted"):
                preserve_prototype(root, archive)

            self.assertFalse((root / "ASSETS").exists())

    def test_parent_creation_rolls_back_when_a_later_mkdir_fails(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive_parent = root / ".archive"
            archive = archive_parent / "level-one" / "level-two" / "prototype-v1"
            real_mkdir = Path.mkdir

            def fail_second_level(path: Path, *args: object, **kwargs: object) -> None:
                if path.name == "level-two":
                    raise OSError("second parent mkdir failed")
                real_mkdir(path, *args, **kwargs)

            with patch.object(Path, "mkdir", autospec=True, side_effect=fail_second_level):
                with self.assertRaisesRegex(OSError, "second parent mkdir failed"):
                    preserve_prototype(root, archive)

            self.assertFalse(archive_parent.exists())

    def test_parent_fd_open_failure_rolls_back_new_parents(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive_parent = root / ".archive"
            archive = archive_parent / "nested" / "prototype-v1"

            with patch("tools.migrate_prototype._open_directory_fd", side_effect=OSError("open failed")):
                with self.assertRaisesRegex(OSError, "open failed"):
                    preserve_prototype(root, archive)

            self.assertFalse(archive_parent.exists())

    def test_directory_fd_fstat_failure_closes_the_opened_descriptor(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory).resolve()
            opened: list[int] = []
            real_open = os.open

            def record_open(*args: object, **kwargs: object) -> int:
                descriptor = real_open(*args, **kwargs)
                opened.append(descriptor)
                return descriptor

            with patch("tools.migrate_prototype.os.open", side_effect=record_open):
                with patch("tools.migrate_prototype.os.fstat", side_effect=OSError("fstat failed")):
                    with self.assertRaisesRegex(OSError, "fstat failed"):
                        __import__("tools.migrate_prototype", fromlist=["_open_directory_fd"])._open_directory_fd(path)

            self.assertEqual(len(opened), 1)
            with self.assertRaises(OSError):
                os.fstat(opened[0])

    def test_parent_fd_open_failure_preserves_open_error_when_cleanup_fails(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive_parent = root / ".archive"
            archive = archive_parent / "prototype-v1"
            real_rmdir = Path.rmdir

            def fail_parent_cleanup(path: Path) -> None:
                if path == archive_parent:
                    raise OSError("parent cleanup failed")
                real_rmdir(path)

            with patch("tools.migrate_prototype._open_directory_fd", side_effect=OSError("open failed")):
                with patch.object(Path, "rmdir", autospec=True, side_effect=fail_parent_cleanup):
                    with self.assertRaisesRegex(RuntimeError, "parent cleanup failed") as error:
                        preserve_prototype(root, archive)

            self.assertIsInstance(error.exception.__cause__, OSError)
            self.assertEqual(str(error.exception.__cause__), "open failed")

    def test_parent_creation_reports_cleanup_failure_with_original_cause(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive_parent = root / ".archive"
            archive = archive_parent / "level-one" / "level-two" / "prototype-v1"
            real_mkdir = Path.mkdir
            real_rmdir = Path.rmdir

            def fail_second_level(path: Path, *args: object, **kwargs: object) -> None:
                if path.name == "level-two":
                    raise OSError("second parent mkdir failed")
                real_mkdir(path, *args, **kwargs)

            def fail_cleanup(path: Path) -> None:
                if path == archive_parent:
                    raise OSError("parent cleanup failed")
                real_rmdir(path)

            with patch.object(Path, "mkdir", autospec=True, side_effect=fail_second_level):
                with patch.object(Path, "rmdir", autospec=True, side_effect=fail_cleanup):
                    with self.assertRaisesRegex(RuntimeError, "parent cleanup failed") as error:
                        preserve_prototype(root, archive)

            self.assertIsInstance(error.exception.__cause__, OSError)
            self.assertEqual(str(error.exception.__cause__), "second parent mkdir failed")

    def test_rejects_archive_path_with_parent_traversal_before_reservation(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive = root / ".archive" / ".." / "assets" / "archive"

            with self.assertRaisesRegex(ValueError, "parent traversal"):
                preserve_prototype(root, archive)

            self.assertTrue((root / "index.html").exists())
            self.assertFalse((root / "assets" / "archive").exists())

    def test_rejects_source_with_an_intermediate_symlink(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            actual = root / "actual"
            actual.mkdir()
            nested = actual / "nested"
            nested.mkdir()
            (nested / "index.html").write_text("legacy", encoding="utf-8")
            (root / "source-link").symlink_to(actual, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "source contains a symbolic link"):
                preserve_prototype(root / "source-link" / "nested", root / "archive")

    def test_rejects_archive_with_an_intermediate_symlink(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            (root / "archive-link").symlink_to(root / ".archive", target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "archive contains a symbolic link"):
                preserve_prototype(root, root / "archive-link" / "prototype-v1")

    def test_rejects_archive_reaching_allowlist_through_a_symlink(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            (root / "to-assets").symlink_to(root / "assets", target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "archive contains a symbolic link"):
                preserve_prototype(root, root / "to-assets" / "archive")

    def test_cli_requires_paths_and_prints_success_json(self) -> None:
        with patch.object(sys, "argv", ["migrate_prototype.py"]):
            with self.assertRaises(SystemExit) as missing_arguments:
                main()
        self.assertEqual(missing_arguments.exception.code, 2)

        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive = root / ".archive" / "prototype-v1"
            output = io.StringIO()
            with patch.object(sys, "argv", ["migrate_prototype.py", "--source", str(root), "--archive", str(archive)]):
                with patch("sys.stdout", output):
                    self.assertEqual(main(), 0)
            self.assertEqual(json.loads(output.getvalue()), {"fileCount": 2, "status": "preserved"})
