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

from tools.migrate_prototype import (
    LEGACY_PATHS,
    PrototypePublicationDurabilityError,
    _build_verified_archive,
    _clear_directory_fd,
    _copy_allowlisted_tree,
    _create_private_staging,
    _existing_archive_parent,
    _open_directory_fd,
    _publish_verified_archive,
    _rename_directory_noreplace,
    _snapshot,
    _snapshot_fd,
    _write_manifest,
    main,
    preserve_prototype,
)


class PrototypeMigrationTests(unittest.TestCase):
    def test_existing_archive_parent_rejects_missing_parent_without_creating_it(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            parent = root / "missing" / "archive"

            with self.assertRaisesRegex(FileNotFoundError, "archive parent must already exist"):
                _existing_archive_parent(parent)

            self.assertFalse((root / "missing").exists())

    def test_existing_archive_parent_rejects_symlink(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / "target"
            target.mkdir(mode=0o700)
            parent = root / "archive-link"
            parent.symlink_to(target, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "archive contains a symbolic link"):
                _existing_archive_parent(parent)

    def test_existing_archive_parent_requires_owned_private_directory_and_returns_canonical_path(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            parent = root / "archive"
            parent.mkdir(mode=0o700)
            parent.chmod(0o700)

            self.assertEqual(_existing_archive_parent(parent), parent.resolve(strict=True))

            parent.chmod(0o777)
            with self.assertRaisesRegex(PermissionError, "group/world writable"):
                _existing_archive_parent(parent)

    def test_publish_verified_archive_natively_publishes_private_staging(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "source"
            (source / "assets").mkdir(parents=True)
            (source / "assets" / "style.css").write_text("body{}", encoding="utf-8")
            (source / "index.html").write_text("legacy", encoding="utf-8")
            parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                manifest = _publish_verified_archive(source, parent_fd, "published", _snapshot(source))
            finally:
                os.close(parent_fd)
            final = root / "published"
            self.assertEqual(json.loads((final / "manifest.json").read_text(encoding="utf-8")), manifest)
            self.assertTrue((source / "index.html").exists())
            self.assertEqual(list(root.glob(".prototype-staging-*")), [])

    def test_publish_verified_archive_preserves_competing_target(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "source"
            source.mkdir()
            (source / "index.html").write_text("legacy", encoding="utf-8")
            target = root / "published"
            sentinel = target / "sentinel.txt"

            def create_target_before_publish(parent_fd: int, staging_name: str, target_name: str) -> None:
                target.mkdir()
                sentinel.write_text("keep", encoding="utf-8")
                _rename_directory_noreplace(parent_fd, staging_name, target_name)

            parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with patch(
                    "tools.migrate_prototype._rename_directory_noreplace",
                    side_effect=create_target_before_publish,
                ):
                    with self.assertRaises(FileExistsError):
                        _publish_verified_archive(source, parent_fd, "published", _snapshot(source))
            finally:
                os.close(parent_fd)

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            self.assertFalse((target / "manifest.json").exists())
            self.assertEqual(list(root.glob(".prototype-staging-*")), [])
            self.assertTrue((source / "index.html").exists())

    def test_publish_verified_archive_cleans_staging_after_builder_failure(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "source"
            source.mkdir()
            (source / "index.html").write_text("legacy", encoding="utf-8")
            parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with patch("tools.migrate_prototype._build_verified_archive", side_effect=OSError("build failed")):
                    with self.assertRaisesRegex(OSError, "build failed"):
                        _publish_verified_archive(source, parent_fd, "published", _snapshot(source))
            finally:
                os.close(parent_fd)

            self.assertFalse((root / "published").exists())
            self.assertEqual(list(root.glob(".prototype-staging-*")), [])
            self.assertTrue((source / "index.html").exists())

    def test_builder_failure_reports_private_staging_close_failure_with_builder_as_cause(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "source"
            source.mkdir()
            (source / "index.html").write_text("legacy", encoding="utf-8")
            parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)

            def close_staging(descriptors: tuple[int | None, ...]) -> list[OSError]:
                for descriptor in descriptors:
                    if descriptor is not None:
                        os.close(descriptor)
                return [OSError("staging close failed")]

            try:
                with patch("tools.migrate_prototype._build_verified_archive", side_effect=OSError("builder failed")):
                    with patch("tools.migrate_prototype._close_all", side_effect=close_staging):
                        with self.assertRaisesRegex(RuntimeError, "staging close failed") as error:
                            _publish_verified_archive(source, parent_fd, "published", _snapshot(source))
                self.assertIsInstance(error.exception.__cause__, OSError)
                self.assertEqual(str(error.exception.__cause__), "builder failed")
            finally:
                os.close(parent_fd)

            self.assertFalse((root / "published").exists())
            self.assertEqual(list(root.glob(".prototype-staging-*")), [])
            self.assertTrue((source / "index.html").exists())

    def test_build_verified_archive_copies_and_manifests_without_changing_source(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "source"
            destination = root / "destination"
            (source / "assets").mkdir(parents=True)
            (source / "assets" / "style.css").write_text("body{}", encoding="utf-8")
            (source / "index.html").write_text("legacy", encoding="utf-8")
            destination.mkdir()
            initial = _snapshot(source)
            descriptor = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
            try:
                manifest = _build_verified_archive(source, descriptor, initial)
            finally:
                os.close(descriptor)
            self.assertEqual(_snapshot(destination), initial)
            self.assertTrue((source / "index.html").exists())
            self.assertEqual(json.loads((destination / "manifest.json").read_text(encoding="utf-8")), manifest)

    def test_build_verified_archive_propagates_manifest_failure_without_completion_marker(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            destination.mkdir()
            (source / "index.html").write_text("legacy", encoding="utf-8")
            descriptor = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with patch("tools.migrate_prototype._write_manifest", side_effect=OSError("manifest failed")):
                    with self.assertRaisesRegex(OSError, "manifest failed"):
                        _build_verified_archive(source, descriptor, _snapshot(source))
            finally:
                os.close(descriptor)
            self.assertFalse((destination / "manifest.json").exists())
            self.assertTrue((source / "index.html").exists())
    def test_create_private_staging_returns_a_pinned_empty_directory(self) -> None:
        with TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            name, staging_fd, identity = _create_private_staging(parent_fd)
            try:
                node = os.fstat(staging_fd)
                self.assertTrue(name.startswith(".prototype-staging-"))
                self.assertEqual((node.st_dev, node.st_ino), identity)
                self.assertEqual(node.st_mode & 0o777, 0o700)
                self.assertEqual(list(os.scandir(staging_fd)), [])
            finally:
                os.close(staging_fd)
                os.rmdir(name, dir_fd=parent_fd)
                os.close(parent_fd)

    def test_nested_snapshot_read_failure_reports_close_failure_with_read_cause(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "assets" / "nested").mkdir(parents=True)
            (root / "assets" / "nested" / "payload.txt").write_text("payload", encoding="utf-8")
            root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            attempted: list[int] = []
            close_calls = 0

            def fail_read(descriptor: int, size: int) -> bytes:
                raise OSError("read failed")

            def close_descriptors(descriptors: tuple[int | None, ...]) -> list[OSError]:
                nonlocal close_calls
                close_calls += 1
                for descriptor in descriptors:
                    if descriptor is not None:
                        attempted.append(descriptor)
                        os.close(descriptor)
                return [OSError("read descriptor close failed")] if close_calls == 1 else []

            try:
                with patch("tools.migrate_prototype.os.read", side_effect=fail_read):
                    with patch("tools.migrate_prototype._close_all", side_effect=close_descriptors):
                        with self.assertRaisesRegex(RuntimeError, "read descriptor close failed") as error:
                            _snapshot_fd(root_fd)
                self.assertIsInstance(error.exception.__cause__, OSError)
                self.assertEqual(str(error.exception.__cause__), "read failed")
                self.assertEqual(len(attempted), 3)
            finally:
                os.close(root_fd)

    def test_recursive_clear_failure_reports_child_close_failure_without_parent_deletion(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            child = root / "child"
            child.mkdir()
            payload = child / "payload.txt"
            payload.write_text("keep", encoding="utf-8")
            root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            real_unlink = os.unlink

            def fail_child_unlink(name: str, *args: object, **kwargs: object) -> None:
                if name == "payload.txt":
                    raise OSError("clear failed")
                real_unlink(name, *args, **kwargs)

            def close_child(descriptors: tuple[int | None, ...]) -> list[OSError]:
                for descriptor in descriptors:
                    if descriptor is not None:
                        os.close(descriptor)
                return [OSError("child close failed")]

            try:
                with patch("tools.migrate_prototype.os.unlink", side_effect=fail_child_unlink):
                    with patch("tools.migrate_prototype._close_all", side_effect=close_child):
                        with patch("tools.migrate_prototype.os.rmdir", wraps=os.rmdir) as rmdir:
                            with self.assertRaisesRegex(RuntimeError, "child close failed") as error:
                                _clear_directory_fd(root_fd)
                self.assertIsInstance(error.exception.__cause__, OSError)
                self.assertEqual(str(error.exception.__cause__), "clear failed")
                rmdir.assert_not_called()
                self.assertTrue(payload.exists())
                self.assertTrue(child.exists())
            finally:
                os.close(root_fd)

    def test_private_staging_stat_race_preserves_foreign_sentinel(self) -> None:
        with TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            real_mkdir = os.mkdir
            sentinel_name = "sentinel.txt"
            foreign_name = ""

            def replace_after_mkdir(name: str, *args: object, **kwargs: object) -> None:
                nonlocal foreign_name
                real_mkdir(name, *args, **kwargs)
                os.rename(name, "owned", src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
                real_mkdir(name, dir_fd=parent_fd)
                foreign_name = name
                foreign_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY, dir_fd=parent_fd)
                try:
                    file_fd = os.open(sentinel_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=foreign_fd)
                    try:
                        os.write(file_fd, b"foreign")
                    finally:
                        os.close(file_fd)
                finally:
                    os.close(foreign_fd)

            try:
                with patch("tools.migrate_prototype.os.mkdir", side_effect=replace_after_mkdir):
                    with patch("tools.migrate_prototype._clear_directory_fd") as clear:
                        with self.assertRaises(RuntimeError):
                            _create_private_staging(parent_fd)
                self.assertTrue(foreign_name.startswith(".prototype-staging-"))
                foreign_fd = os.open(foreign_name, os.O_RDONLY | os.O_DIRECTORY, dir_fd=parent_fd)
                try:
                    file_fd = os.open(sentinel_name, os.O_RDONLY, dir_fd=foreign_fd)
                    try:
                        self.assertEqual(os.read(file_fd, 16), b"foreign")
                    finally:
                        os.close(file_fd)
                finally:
                    os.close(foreign_fd)
                clear.assert_not_called()
            finally:
                os.close(parent_fd)

    def test_private_staging_nonempty_failure_reports_close_failure_and_preserves_foreign_sentinel(self) -> None:
        with TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            real_fstat = os.fstat
            created_descriptor: int | None = None
            staging_name = ""
            foreign_sentinel: Path | None = None

            def replace_and_fill_staging(descriptor: int) -> os.stat_result:
                nonlocal created_descriptor, staging_name, foreign_sentinel
                node = real_fstat(descriptor)
                if created_descriptor is None:
                    created_descriptor = descriptor
                    staging_name = next(parent.glob(".prototype-staging-*")).name
                    os.rename(staging_name, "owned", src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
                    os.mkdir(staging_name, dir_fd=parent_fd)
                    foreign_sentinel = parent / staging_name / "sentinel.txt"
                    foreign_sentinel.write_text("foreign", encoding="utf-8")
                    file_fd = os.open("unexpected.txt", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=descriptor)
                    os.close(file_fd)
                return node

            try:
                with patch("tools.migrate_prototype.os.fstat", side_effect=replace_and_fill_staging):
                    with patch("tools.migrate_prototype._close_all", return_value=[OSError("close failed")]) as close_all:
                        with self.assertRaisesRegex(RuntimeError, "close failed") as error:
                            _create_private_staging(parent_fd)
                self.assertIsInstance(error.exception.__cause__, RuntimeError)
                self.assertEqual(str(error.exception.__cause__), "private staging is not empty")
                close_all.assert_called_once_with((created_descriptor,))
                self.assertIsNotNone(foreign_sentinel)
                self.assertEqual(foreign_sentinel.read_text(encoding="utf-8"), "foreign")
            finally:
                if created_descriptor is not None:
                    os.close(created_descriptor)
                if staging_name:
                    owned = parent / "owned"
                    if owned.exists():
                        for child in owned.iterdir():
                            child.unlink()
                        owned.rmdir()
                os.close(parent_fd)

    def test_private_staging_fstat_failure_reports_descriptor_close_failure(self) -> None:
        with TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            opened: list[int] = []
            real_open = os.open

            def record_open(*args: object, **kwargs: object) -> int:
                descriptor = real_open(*args, **kwargs)
                opened.append(descriptor)
                return descriptor

            try:
                with patch("tools.migrate_prototype.os.open", side_effect=record_open):
                    with patch("tools.migrate_prototype.os.fstat", side_effect=OSError("fstat failed")):
                        with patch("tools.migrate_prototype._close_all", return_value=[OSError("close failed")]) as close_all:
                            with self.assertRaisesRegex(RuntimeError, "close failed") as error:
                                _create_private_staging(parent_fd)
                self.assertIsInstance(error.exception.__cause__, OSError)
                self.assertEqual(str(error.exception.__cause__), "fstat failed")
                close_all.assert_called_once_with((opened[0],))
                self.assertEqual(list(parent.glob(".prototype-staging-*")), [])
            finally:
                if opened:
                    os.close(opened[0])
                os.close(parent_fd)
    def test_native_noreplace_rename_publishes_a_missing_target(self) -> None:
        with TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            (parent / "staging").mkdir()
            (parent / "staging" / "payload.txt").write_text("ok", encoding="utf-8")
            descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                _rename_directory_noreplace(descriptor, "staging", "published")
            finally:
                os.close(descriptor)
            self.assertFalse((parent / "staging").exists())
            self.assertEqual((parent / "published" / "payload.txt").read_text(encoding="utf-8"), "ok")

    def test_native_noreplace_rename_preserves_existing_target(self) -> None:
        with TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            (parent / "staging").mkdir()
            (parent / "published").mkdir()
            (parent / "published" / "sentinel.txt").write_text("keep", encoding="utf-8")
            descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with self.assertRaises(FileExistsError):
                    _rename_directory_noreplace(descriptor, "staging", "published")
            finally:
                os.close(descriptor)
            self.assertTrue((parent / "staging").exists())
            self.assertEqual((parent / "published" / "sentinel.txt").read_text(encoding="utf-8"), "keep")

    def test_native_noreplace_rename_rejects_invalid_basenames_without_resolving_native_call(self) -> None:
        invalid_names = ("", ".", "..", "nested/name", "bad\0name")
        for invalid_name in invalid_names:
            for source_name, target_name in ((invalid_name, "published"), ("staging", invalid_name)):
                with self.subTest(source_name=source_name, target_name=target_name):
                    with TemporaryDirectory() as directory:
                        parent = Path(directory).resolve()
                        staging = parent / "staging"
                        staging.mkdir()
                        payload = staging / "payload.txt"
                        payload.write_text("keep", encoding="utf-8")
                        descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
                        try:
                            with patch("tools.migrate_prototype._native_rename_noreplace") as native:
                                with self.assertRaises(ValueError):
                                    _rename_directory_noreplace(descriptor, source_name, target_name)
                                native.assert_not_called()
                        finally:
                            os.close(descriptor)
                        self.assertEqual(payload.read_text(encoding="utf-8"), "keep")
                        self.assertFalse((parent / "published").exists())

    def test_native_noreplace_rename_fails_closed_when_native_failure_has_no_errno(self) -> None:
        with TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            (parent / "staging").mkdir()
            descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with patch("tools.migrate_prototype._native_rename_noreplace", return_value=(lambda *args: -1, 1)):
                    with patch("tools.migrate_prototype.ctypes.get_errno", return_value=0):
                        with self.assertRaisesRegex(RuntimeError, "without errno"):
                            _rename_directory_noreplace(descriptor, "staging", "published")
            finally:
                os.close(descriptor)
            self.assertTrue((parent / "staging").exists())
            self.assertFalse((parent / "published").exists())
    def _write_fixture(self, root: Path) -> None:
        self._prepare_archive_parent(root)
        (root / "assets").mkdir()
        (root / "assets" / "styles.css").write_text("body{}", encoding="utf-8")
        (root / "index.html").write_text("<main>legacy</main>", encoding="utf-8")

    def _prepare_archive_parent(self, root: Path) -> Path:
        parent = root / ".archive"
        parent.mkdir(mode=0o700)
        parent.chmod(0o700)
        return parent

    def _assert_prepared_archive_parent_empty(self, root: Path) -> None:
        parent = root / ".archive"
        self.assertTrue(parent.exists())
        self.assertEqual(list(parent.iterdir()), [])

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

    def test_preserve_rejects_missing_archive_parent_without_creating_it(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "index.html").write_text("legacy", encoding="utf-8")
            archive_parent = root / ".archive"

            with self.assertRaisesRegex(FileNotFoundError, "archive parent must already exist"):
                preserve_prototype(root, archive_parent / "prototype-v1")

            self.assertFalse(archive_parent.exists())
            self.assertTrue((root / "index.html").exists())

    def test_preserve_fails_closed_when_native_publish_is_unsupported(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive = root / ".archive" / "prototype-v1"

            with patch("tools.migrate_prototype.sys.platform", "unsupported-test"):
                with self.assertRaisesRegex(RuntimeError, "native no-replace rename is not supported"):
                    preserve_prototype(root, archive)

            self.assertTrue((root / "index.html").exists())
            self.assertFalse(archive.exists())
            self.assertEqual(list((root / ".archive").glob(".prototype-staging-*")), [])
            self._assert_prepared_archive_parent_empty(root)

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

    def test_durability_events_precede_native_publish_in_order(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._prepare_archive_parent(root)
            (root / "assets" / "nested").mkdir(parents=True)
            (root / "assets" / "nested" / "app.css").write_text("body{}", encoding="utf-8")
            archive = root / ".archive" / "prototype-v1"
            events: list[str] = []
            real_replace = os.replace
            real_publish = _rename_directory_noreplace

            def record_replace(source: str, target: str, *args: object, **kwargs: object) -> None:
                if target == "manifest.json":
                    events.append("manifest rename")
                real_replace(source, target, *args, **kwargs)

            def record_publish(parent_fd: int, source_name: str, target_name: str) -> None:
                events.append("native publish")
                real_publish(parent_fd, source_name, target_name)

            with patch("tools.migrate_prototype._fsync_fd", side_effect=lambda fd, purpose: events.append(purpose)):
                with patch("tools.migrate_prototype.os.replace", side_effect=record_replace):
                    with patch("tools.migrate_prototype._rename_directory_noreplace", side_effect=record_publish):
                        preserve_prototype(root, archive)

            self.assertEqual(
                events,
                [
                    "destination regular file",
                    "destination directory: assets/nested",
                    "destination directory: assets",
                    "staging root",
                    "manifest temp",
                    "staging root before manifest rename",
                    "manifest rename",
                    "staging root after manifest rename",
                    "native publish",
                    "archive parent after native publish",
                ],
            )

    def test_parent_fsync_failure_after_native_publish_reports_durability_unknown_without_rollback(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive = root / ".archive" / "prototype-v1"

            def fail_parent_fsync(descriptor: int, purpose: str) -> None:
                if purpose == "archive parent after native publish":
                    raise OSError("parent fsync failed")

            with patch("tools.migrate_prototype._fsync_fd", side_effect=fail_parent_fsync):
                with patch("tools.migrate_prototype._remove_owned_directory") as remove_owned:
                    with self.assertRaises(PrototypePublicationDurabilityError) as error:
                        preserve_prototype(root, archive)

            self.assertIsInstance(error.exception.__cause__, OSError)
            self.assertEqual(str(error.exception.__cause__), "parent fsync failed")
            remove_owned.assert_not_called()
            self.assertTrue((archive / "manifest.json").exists())
            self.assertTrue((archive / "index.html").exists())
            self.assertEqual(list((root / ".archive").glob(".prototype-staging-*")), [])
            self.assertTrue((root / "index.html").exists())
            self.assertTrue((root / ".archive").exists())

    def test_post_manifest_rename_fsync_failure_cleans_private_staging_without_final_archive(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive = root / ".archive" / "prototype-v1"

            def fail_post_manifest_rename_fsync(descriptor: int, purpose: str) -> None:
                if purpose == "staging root after manifest rename":
                    raise OSError("post-manifest fsync failed")

            with patch("tools.migrate_prototype._fsync_fd", side_effect=fail_post_manifest_rename_fsync):
                with self.assertRaisesRegex(OSError, "post-manifest fsync failed"):
                    preserve_prototype(root, archive)

            self.assertFalse(archive.exists())
            self._assert_prepared_archive_parent_empty(root)
            self.assertEqual(list(root.glob(".prototype-staging-*")), [])
            self.assertTrue((root / "index.html").exists())

    def test_manifest_write_failure_does_not_double_close_fdopen_descriptor(self) -> None:
        with TemporaryDirectory() as directory:
            archive = Path(directory).resolve()
            archive_fd = os.open(archive, os.O_RDONLY | os.O_DIRECTORY)
            real_close = os.close
            close_attempts: list[int] = []

            class FailingOutput:
                def __init__(self, descriptor: int) -> None:
                    self.descriptor = descriptor
                    self.close_calls = 0

                def __enter__(self) -> "FailingOutput":
                    return self

                def __exit__(self, *args: object) -> bool:
                    self.close()
                    return False

                def write(self, text: str) -> None:
                    raise OSError("manifest write failed")

                def close(self) -> None:
                    self.close_calls += 1
                    os.close(self.descriptor)

            output: FailingOutput | None = None

            def failing_fdopen(descriptor: int, mode: str, **kwargs: object) -> FailingOutput:
                nonlocal output
                output = FailingOutput(descriptor)
                return output

            def record_close(descriptor: int) -> None:
                close_attempts.append(descriptor)
                real_close(descriptor)

            try:
                with patch("tools.migrate_prototype.os.fdopen", side_effect=failing_fdopen):
                    with patch("tools.migrate_prototype.os.close", side_effect=record_close):
                        with self.assertRaisesRegex(OSError, "manifest write failed"):
                            _write_manifest(archive_fd, {"index.html": {"sha256": "a", "byteCount": 1}})
                self.assertIsNotNone(output)
                self.assertEqual(output.close_calls, 1)
                self.assertEqual(close_attempts, [output.descriptor])
            finally:
                os.close(archive_fd)

    def test_nested_copy_failure_reports_child_close_failure_and_closes_every_child(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "source"
            destination = root / "destination"
            (source / "assets" / "nested").mkdir(parents=True)
            destination.mkdir()
            destination_fd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
            attempted: list[int] = []
            close_calls = 0

            def fail_nested_directory_fsync(descriptor: int, purpose: str) -> None:
                if purpose == "destination directory: assets/nested":
                    raise OSError("copy failed")

            def close_children(descriptors: tuple[int | None, ...]) -> list[OSError]:
                nonlocal close_calls
                close_calls += 1
                for descriptor in descriptors:
                    if descriptor is not None:
                        attempted.append(descriptor)
                        os.close(descriptor)
                return [OSError("child close failed")] if close_calls == 1 else []

            try:
                with patch("tools.migrate_prototype._fsync_fd", side_effect=fail_nested_directory_fsync):
                    with patch("tools.migrate_prototype._close_all", side_effect=close_children):
                        with self.assertRaisesRegex(RuntimeError, "child close failed") as error:
                            _copy_allowlisted_tree(source, destination_fd)
                self.assertIsInstance(error.exception.__cause__, OSError)
                self.assertEqual(str(error.exception.__cause__), "copy failed")
                self.assertEqual(len(attempted), 2)
            finally:
                os.close(destination_fd)

    def test_copy_write_failure_does_not_double_close_fdopen_descriptor(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            destination.mkdir()
            (source / "index.html").write_text("legacy", encoding="utf-8")
            destination_fd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
            real_close = os.close
            close_attempts: list[int] = []

            class FailingOutput:
                def __init__(self, descriptor: int) -> None:
                    self.descriptor = descriptor
                    self.close_calls = 0

                def __enter__(self) -> "FailingOutput":
                    return self

                def __exit__(self, *args: object) -> bool:
                    self.close()
                    return False

                def write(self, chunk: bytes) -> None:
                    raise OSError("write failed")

                def close(self) -> None:
                    self.close_calls += 1
                    os.close(self.descriptor)

            output: FailingOutput | None = None

            def failing_fdopen(descriptor: int, mode: str) -> FailingOutput:
                nonlocal output
                output = FailingOutput(descriptor)
                return output

            def record_close(descriptor: int) -> None:
                close_attempts.append(descriptor)
                real_close(descriptor)

            try:
                with patch("tools.migrate_prototype.os.fdopen", side_effect=failing_fdopen):
                    with patch("tools.migrate_prototype.os.close", side_effect=record_close):
                        with self.assertRaisesRegex(OSError, "write failed"):
                            _copy_allowlisted_tree(source, destination_fd)
                self.assertIsNotNone(output)
                self.assertEqual(output.close_calls, 1)
                self.assertEqual(close_attempts, [output.descriptor])
            finally:
                os.close(destination_fd)

    def test_copy_fdopen_failure_closes_unowned_output_descriptor_once(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            destination.mkdir()
            (source / "index.html").write_text("legacy", encoding="utf-8")
            destination_fd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
            closed: list[int] = []

            def close_output(descriptors: tuple[int | None, ...]) -> list[OSError]:
                for descriptor in descriptors:
                    if descriptor is not None:
                        closed.append(descriptor)
                        os.close(descriptor)
                return []

            try:
                with patch("tools.migrate_prototype.os.fdopen", side_effect=OSError("fdopen failed")):
                    with patch("tools.migrate_prototype._close_all", side_effect=close_output):
                        with self.assertRaisesRegex(OSError, "fdopen failed"):
                            _copy_allowlisted_tree(source, destination_fd)
                self.assertEqual(len(closed), 1)
                with self.assertRaises(OSError):
                    os.fstat(closed[0])
            finally:
                os.close(destination_fd)

    def test_regular_file_fsync_failure_rolls_back_archive(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive = root / ".archive" / "prototype-v1"
            with patch("tools.migrate_prototype._fsync_fd", side_effect=OSError("file fsync failed")):
                with self.assertRaisesRegex(OSError, "file fsync failed"):
                    preserve_prototype(root, archive)
            self.assertTrue((root / "index.html").exists())
            self.assertFalse(archive.exists())
            self._assert_prepared_archive_parent_empty(root)

    def test_directory_fsync_failure_rolls_back_archive(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive = root / ".archive" / "prototype-v1"

            def fail_directory_fsync(fd: int, purpose: str) -> None:
                if purpose.startswith("destination directory:"):
                    raise OSError("directory fsync failed")

            with patch("tools.migrate_prototype._fsync_fd", side_effect=fail_directory_fsync):
                with self.assertRaisesRegex(OSError, "directory fsync failed"):
                    preserve_prototype(root, archive)
            self.assertTrue((root / "index.html").exists())
            self.assertFalse(archive.exists())
            self._assert_prepared_archive_parent_empty(root)

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
            self._assert_prepared_archive_parent_empty(root)

    def test_publish_conflict_preserves_foreign_archive_and_original_error(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive = root / ".archive" / "prototype-v1"

            def publish_into_competing_archive(
                source: Path, parent_fd: int, name: str, initial: object
            ) -> None:
                os.mkdir(name, dir_fd=parent_fd)
                (archive / "sentinel.txt").write_text("keep", encoding="utf-8")
                raise FileExistsError("archive already exists: prototype-v1")

            with patch("tools.migrate_prototype._publish_verified_archive", side_effect=publish_into_competing_archive):
                with self.assertRaisesRegex(FileExistsError, "archive already exists"):
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
            self._assert_prepared_archive_parent_empty(root)

    def test_publish_failure_reports_parent_close_failure_with_publish_as_cause(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive = root / ".archive" / "prototype-v1"

            def close_parent(descriptors: tuple[int | None, ...]) -> list[OSError]:
                for descriptor in descriptors:
                    if descriptor is not None:
                        os.close(descriptor)
                return [OSError("parent close failed")]

            with patch("tools.migrate_prototype._publish_verified_archive", side_effect=OSError("publish failed")):
                with patch("tools.migrate_prototype._close_all", side_effect=close_parent):
                    with self.assertRaisesRegex(RuntimeError, "parent close failed") as error:
                        preserve_prototype(root, archive)

            self.assertIsInstance(error.exception.__cause__, OSError)
            self.assertEqual(str(error.exception.__cause__), "publish failed")
            self.assertFalse(archive.exists())
            self._assert_prepared_archive_parent_empty(root)
            self.assertTrue((root / "index.html").exists())

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
            received: list[tuple[int | None, ...]] = []
            post_publish_closes: list[tuple[int | None, ...]] = []
            parent_descriptor: int | None = None
            native_published = False
            real_publish = _rename_directory_noreplace

            def record_parent_descriptor(path: Path) -> int:
                nonlocal parent_descriptor
                parent_descriptor = _open_directory_fd(path)
                return parent_descriptor

            def record_publish(parent_fd: int, source_name: str, target_name: str) -> None:
                nonlocal native_published
                real_publish(parent_fd, source_name, target_name)
                native_published = True

            def close_with_reported_failure(descriptors: tuple[int | None, ...]) -> list[OSError]:
                received.append(descriptors)
                for descriptor in descriptors:
                    if descriptor is not None:
                        attempted.append(descriptor)
                        os.close(descriptor)
                if native_published:
                    post_publish_closes.append(descriptors)
                    return [OSError("post-publish close failed")]
                return []

            with patch("tools.migrate_prototype._open_directory_fd", side_effect=record_parent_descriptor):
                with patch("tools.migrate_prototype._rename_directory_noreplace", side_effect=record_publish):
                    with patch("tools.migrate_prototype._close_all", side_effect=close_with_reported_failure):
                        manifest = preserve_prototype(root, archive)

            self.assertEqual(manifest["fileCount"], 2)
            self.assertTrue((archive / "manifest.json").exists())
            self.assertEqual(Path.cwd(), original_cwd)
            self.assertGreater(len(received), 3)
            expected = [
                descriptor
                for descriptors in received
                for descriptor in descriptors
                if descriptor is not None
            ]
            self.assertEqual(attempted, expected)
            self.assertEqual(received[-1], (parent_descriptor,))
            self.assertEqual(len(post_publish_closes), 2)

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

    def test_copy_failure_keeps_prepared_archive_parent_empty(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive_parent = root / ".archive"
            archive = archive_parent / "prototype-v1"

            with patch("tools.migrate_prototype._copy_allowlisted_tree", side_effect=OSError("copy failed")):
                with self.assertRaisesRegex(OSError, "copy failed"):
                    preserve_prototype(root, archive)

            self._assert_prepared_archive_parent_empty(root)

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

    def test_rejects_casefolded_allowlist_archive_boundary_before_parent_creation(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "index.html").write_text("legacy", encoding="utf-8")
            archive = root / "ASSETS" / "archive"

            with self.assertRaisesRegex(ValueError, "archive.*allowlisted"):
                preserve_prototype(root, archive)

            self.assertFalse((root / "ASSETS").exists())

    def test_parent_fd_open_failure_keeps_prepared_parent(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._write_fixture(root)
            archive_parent = root / ".archive"
            archive = archive_parent / "prototype-v1"

            with patch("tools.migrate_prototype._open_directory_fd", side_effect=OSError("open failed")):
                with self.assertRaisesRegex(OSError, "open failed"):
                    preserve_prototype(root, archive)

            self._assert_prepared_archive_parent_empty(root)

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

    def test_directory_fd_identity_mismatch_reports_close_failure_with_mismatch_cause(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory).resolve()
            real_fstat = os.fstat
            opened: list[int] = []

            def mismatched_fstat(descriptor: int) -> os.stat_result:
                node = real_fstat(descriptor)
                values = list(node)
                values[1] += 1
                return os.stat_result(values)

            def report_close_failure(descriptors: tuple[int | None, ...]) -> list[OSError]:
                opened.extend(descriptor for descriptor in descriptors if descriptor is not None)
                return [OSError("close failed")]

            with patch("tools.migrate_prototype.os.fstat", side_effect=mismatched_fstat):
                with patch("tools.migrate_prototype._close_all", side_effect=report_close_failure):
                    with self.assertRaisesRegex(RuntimeError, "close failed") as error:
                        _open_directory_fd(path)

            self.assertIsInstance(error.exception.__cause__, RuntimeError)
            self.assertIn("archive parent changed while opening", str(error.exception.__cause__))
            self.assertEqual(len(opened), 1)
            os.close(opened[0])

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
