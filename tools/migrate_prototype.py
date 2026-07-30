"""Atomically preserve the legacy generated prototype without deleting its source."""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
from typing import TypedDict
import uuid


LEGACY_PATHS = (
    "README.txt",
    "assets",
    "daily.html",
    "data",
    "domains",
    "guide.html",
    "index.html",
    "progress.html",
    "roadmap.html",
    "scheduled",
    "source",
)

_CHUNK_SIZE = 1024 * 1024


def _native_rename_noreplace() -> tuple[object, int]:
    """Return the platform rename primitive and its no-clobber flag, or fail closed."""
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        try:
            function = library.renameatx_np
        except AttributeError as error:
            raise RuntimeError("native no-replace rename is not supported") from error
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        return function, 0x4  # RENAME_EXCL
    if sys.platform.startswith("linux"):
        try:
            function = library.renameat2
        except AttributeError as error:
            raise RuntimeError("native no-replace rename is not supported") from error
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        return function, 1  # RENAME_NOREPLACE
    raise RuntimeError("native no-replace rename is not supported")


def _rename_directory_noreplace(parent_fd: int, source_name: str, target_name: str) -> None:
    """Atomically publish a directory without overwriting an existing target."""
    for name in (source_name, target_name):
        if not name or name in {".", ".."} or "/" in name:
            raise ValueError(f"directory entry name must be a basename: {name!r}")
    function, flag = _native_rename_noreplace()
    # os.rename can overwrite the target; native no-replace is required for the publish commit point.
    if function(parent_fd, os.fsencode(source_name), parent_fd, os.fsencode(target_name), flag) == 0:
        return
    code = ctypes.get_errno()
    if code in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(f"archive already exists: {target_name}")
    raise OSError(code, os.strerror(code), target_name)


class FileSnapshot(TypedDict):
    sha256: str
    byteCount: int


class PrototypeManifest(TypedDict):
    algorithm: str
    fileCount: int
    byteCount: int
    files: dict[str, str]


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _raw_absolute(path: Path, label: str) -> Path:
    """Make a lexical absolute path without normalizing parent traversal."""
    candidate = path if path.is_absolute() else Path.cwd() / path
    if ".." in candidate.parts:
        raise ValueError(f"{label} path contains parent traversal: {path}")
    return candidate


def _validate_existing_components(
    path: Path, label: str, *, permit_final_symlink: bool = False
) -> None:
    """lstat every extant lexical component so no resolution can cross a symlink."""
    current = Path(path.anchor)
    parts = path.parts[1:]
    for index, part in enumerate(parts):
        current /= part
        if not _lexists(current):
            return
        mode = os.lstat(current).st_mode
        is_final = index == len(parts) - 1
        if stat.S_ISLNK(mode) and not (is_final and permit_final_symlink):
            raise ValueError(f"{label} contains a symbolic link: {current}")
        if not is_final and not stat.S_ISDIR(mode):
            raise ValueError(f"{label} parent is not a directory: {current}")


def _create_archive_parent(raw_parent: Path) -> tuple[Path, list[tuple[Path, tuple[int, int]]]]:
    """Create missing parents from a validated ancestor and report only owned directories."""
    missing: list[str] = []
    current = raw_parent
    while not _lexists(current):
        missing.append(current.name)
        current = current.parent
    _validate_existing_components(current, "archive")
    canonical = current.resolve(strict=True)
    if not canonical.is_dir():
        raise ValueError(f"archive parent is not a directory: {canonical}")
    created: list[tuple[Path, tuple[int, int]]] = []
    try:
        for name in reversed(missing):
            next_parent = canonical / name
            next_parent.mkdir(mode=0o700, exist_ok=False)
            node = os.lstat(next_parent)
            created.append((next_parent, (node.st_dev, node.st_ino)))
            _validate_existing_components(next_parent, "archive")
            canonical = next_parent.resolve(strict=True)
    except BaseException as creation_error:
        try:
            _cleanup_created_parents(created)
        except RuntimeError as cleanup_error:
            raise RuntimeError(
                f"archive parent cleanup failed after creation error: {cleanup_error}"
            ) from creation_error
        raise
    return canonical, created


def _cleanup_created_parents(
    created: list[tuple[Path, tuple[int, int]]], *, report_failures: bool = True
) -> None:
    """Remove only empty directories created by this invocation, deepest first."""
    failures: list[OSError] = []
    for directory, identity in reversed(created):
        try:
            node = os.lstat(directory)
            if (node.st_dev, node.st_ino) != identity:
                continue
            directory.rmdir()
        except OSError as error:
            failures.append(error)
    if failures and report_failures:
        details = "; ".join(str(error) for error in failures)
        raise RuntimeError(f"archive parent cleanup failed: {details}") from failures[0]


def _source_directory(source: Path) -> Path:
    raw_source = _raw_absolute(source, "source")
    _validate_existing_components(raw_source, "source")
    if not _lexists(raw_source):
        raise FileNotFoundError(f"source does not exist: {raw_source}")
    canonical = raw_source.resolve(strict=True)
    if not canonical.is_dir():
        raise ValueError(f"source is not a directory: {canonical}")
    return canonical


def _archive_path(source: Path, archive: Path) -> Path:
    raw_archive = _raw_absolute(archive, "archive")
    _validate_existing_components(raw_archive, "archive", permit_final_symlink=True)
    if _lexists(raw_archive):
        # lstat is intentionally used before rejection so dangling symlinks count as existing.
        os.lstat(raw_archive)
        raise FileExistsError(f"archive already exists: {raw_archive}")

    # strict=False is read-only: it computes the canonical boundary without creating parents.
    candidate = raw_archive.resolve(strict=False)
    try:
        relative_to_source = candidate.relative_to(source)
    except ValueError:
        return candidate
    if relative_to_source.parts and relative_to_source.parts[0].casefold() in {
        path.casefold() for path in LEGACY_PATHS
    }:
        raise ValueError(f"archive is inside an allowlisted subtree: {candidate}")
    return raw_archive


def _reserve_archive(archive: Path) -> None:
    """Atomically reserve the archive name without replacing any existing entry."""
    try:
        archive.mkdir(mode=0o700, exist_ok=False)
    except FileExistsError as error:
        raise FileExistsError(f"archive already exists: {archive}") from error


def _reserve_archive_at(parent_fd: int, name: str) -> tuple[int, tuple[int, int]]:
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
    except FileExistsError as error:
        raise FileExistsError(f"archive already exists: {name}") from error
    try:
        reserved = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except BaseException as identity_error:
        try:
            os.rmdir(name, dir_fd=parent_fd)
        except OSError as rollback_error:
            raise RuntimeError(
                f"archive reservation rollback failed for {name}: {rollback_error}"
            ) from identity_error
        raise
    identity = (reserved.st_dev, reserved.st_ino)
    descriptor: int | None = None
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        node = os.fstat(descriptor)
        if (node.st_dev, node.st_ino) != identity:
            raise RuntimeError("reserved archive changed before opening")
        with os.scandir(descriptor) as entries:
            if next(entries, None) is not None:
                raise RuntimeError("reserved archive is not empty")
        return descriptor, identity
    except BaseException as identity_error:
        failures = _close_all((descriptor,))
        try:
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) == identity:
                os.rmdir(name, dir_fd=parent_fd)
        except OSError as rollback_error:
            raise RuntimeError(
                f"archive reservation rollback failed for {name}: {rollback_error}"
            ) from identity_error
        if failures:
            raise RuntimeError(
                f"archive reservation descriptor close failed: {failures[0]}"
            ) from identity_error
        raise
    # Ownership transfers to the caller; it pins the reservation through commit/rollback.


def _create_private_staging(parent_fd: int) -> tuple[str, int, tuple[int, int]]:
    """Create a private, pinned empty staging directory without trusting its pathname."""
    name = f".prototype-staging-{uuid.uuid4().hex}"
    os.mkdir(name, mode=0o700, dir_fd=parent_fd)
    recorded: tuple[int, int] | None = None
    descriptor: int | None = None
    try:
        node = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        recorded = (node.st_dev, node.st_ino)
        descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != recorded:
            raise RuntimeError("private staging changed before opening")
        with os.scandir(descriptor) as entries:
            if next(entries, None) is not None:
                raise RuntimeError("private staging is not empty")
        return name, descriptor, recorded
    except BaseException as error:
        _close_all((descriptor,))
        if recorded is not None:
            try:
                current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if (current.st_dev, current.st_ino) == recorded:
                    os.rmdir(name, dir_fd=parent_fd)
            except OSError as rollback_error:
                raise RuntimeError(f"private staging rollback failed: {rollback_error}") from error
        raise


def _open_directory_fd(path: Path) -> int:
    """Pin a directory identity so later pathname replacement cannot redirect writes."""
    flags = os.O_RDONLY | os.O_DIRECTORY
    if not hasattr(os, "O_NOFOLLOW"):
        raise RuntimeError("safe directory file descriptors are not supported")
    expected = os.stat(path, follow_symlinks=False)
    descriptor = os.open(path, flags | os.O_NOFOLLOW)
    try:
        actual = os.fstat(descriptor)
    except BaseException as operation_error:
        close_failures = _close_all((descriptor,))
        if close_failures:
            raise RuntimeError(
                f"directory descriptor cleanup failed after fstat error: {close_failures[0]}"
            ) from operation_error
        raise
    if (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino):
        os.close(descriptor)
        raise RuntimeError(f"archive parent changed while opening: {path}")
    return descriptor


def _clear_directory_fd(descriptor: int) -> None:
    """Delete entries through a pinned descriptor, never through a replaceable pathname."""
    for entry in os.scandir(descriptor):
        mode = entry.stat(follow_symlinks=False).st_mode
        if stat.S_ISDIR(mode):
            child = os.open(
                entry.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            try:
                _clear_directory_fd(child)
            finally:
                os.close(child)
            os.rmdir(entry.name, dir_fd=descriptor)
        else:
            os.unlink(entry.name, dir_fd=descriptor)


def _remove_owned_archive(parent_fd: int, name: str, archive_fd: int) -> None:
    """Remove only the directory whose inode is still the reservation we created."""
    expected = os.fstat(archive_fd)
    current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino):
        raise RuntimeError("reserved archive entry was replaced; refusing cleanup")
    _clear_directory_fd(archive_fd)
    os.rmdir(name, dir_fd=parent_fd)


def _close_all(descriptors: tuple[int | None, ...]) -> list[OSError]:
    """Attempt every close so one failed descriptor cannot leak the remaining handles."""
    failures: list[OSError] = []
    for descriptor in descriptors:
        if descriptor is None:
            continue
        try:
            os.close(descriptor)
        except OSError as error:
            failures.append(error)
    return failures


def _fsync_fd(descriptor: int, purpose: str) -> None:
    """Durably finish an individual destination file before its descriptor closes."""
    os.fsync(descriptor)


def _unsupported(path: Path, mode: int) -> ValueError:
    if stat.S_ISLNK(mode):
        return ValueError(f"symbolic links are not supported: {path}")
    return ValueError(f"unsupported file type in allowlisted prototype: {path}")


def _allowlisted_files(root: Path) -> list[Path]:
    """Walk every existing allowlist tree and reject non-file, non-directory nodes."""
    files: list[Path] = []

    def walk(path: Path) -> None:
        mode = os.lstat(path).st_mode
        if stat.S_ISREG(mode):
            files.append(path)
            return
        if not stat.S_ISDIR(mode):
            raise _unsupported(path, mode)
        with os.scandir(path) as entries:
            for entry in entries:
                walk(Path(entry.path))

    for relative_path in LEGACY_PATHS:
        candidate = root / relative_path
        if not _lexists(candidate):
            continue
        walk(candidate)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def _file_snapshot(path: Path) -> FileSnapshot:
    digest = hashlib.sha256()
    byte_count = 0
    # Chunked reads bound memory use while deriving the digest and byte count from identical data.
    with path.open("rb") as file:
        while chunk := file.read(_CHUNK_SIZE):
            digest.update(chunk)
            byte_count += len(chunk)
    return {"sha256": digest.hexdigest(), "byteCount": byte_count}


def _snapshot(root: Path) -> dict[str, FileSnapshot]:
    return {
        path.relative_to(root).as_posix(): _file_snapshot(path)
        for path in _allowlisted_files(root)
    }


def _copy_allowlisted_tree(source: Path, staging_fd: int) -> None:
    def copy_node(origin: Path, destination_fd: int, name: str, logical_path: str) -> None:
        mode = os.lstat(origin).st_mode
        if stat.S_ISREG(mode):
            output = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=destination_fd)
            try:
                with origin.open("rb") as input_file, os.fdopen(output, "wb") as output_file:
                    while chunk := input_file.read(_CHUNK_SIZE):
                        output_file.write(chunk)
                    output_file.flush()
                    _fsync_fd(output_file.fileno(), "destination regular file")
            except BaseException:
                try:
                    os.close(output)
                except OSError:
                    pass
                raise
            return
        if not stat.S_ISDIR(mode):
            raise _unsupported(origin, mode)
        os.mkdir(name, mode=0o700, dir_fd=destination_fd)
        child_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=destination_fd)
        try:
            with os.scandir(origin) as entries:
                for entry in entries:
                    copy_node(Path(entry.path), child_fd, entry.name, f"{logical_path}/{entry.name}")
            _fsync_fd(child_fd, f"destination directory: {logical_path}")
        finally:
            os.close(child_fd)

    for relative_path in LEGACY_PATHS:
        origin = source / relative_path
        if _lexists(origin):
            copy_node(origin, staging_fd, relative_path, relative_path)


def _snapshot_fd(root_fd: int) -> dict[str, FileSnapshot]:
    result: dict[str, FileSnapshot] = {}

    def walk(directory_fd: int, prefix: str) -> None:
        for entry in os.scandir(directory_fd):
            relative = f"{prefix}/{entry.name}" if prefix else entry.name
            mode = entry.stat(follow_symlinks=False).st_mode
            if stat.S_ISREG(mode):
                descriptor = os.open(entry.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
                try:
                    digest = hashlib.sha256()
                    count = 0
                    while chunk := os.read(descriptor, _CHUNK_SIZE):
                        digest.update(chunk)
                        count += len(chunk)
                finally:
                    os.close(descriptor)
                result[relative] = {"sha256": digest.hexdigest(), "byteCount": count}
            elif stat.S_ISDIR(mode):
                child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
                try:
                    walk(child, relative)
                finally:
                    os.close(child)
            else:
                raise _unsupported(Path(relative), mode)

    for name in LEGACY_PATHS:
        try:
            node = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            continue
        if stat.S_ISREG(node.st_mode):
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
            try:
                digest = hashlib.sha256(); count = 0
                while chunk := os.read(descriptor, _CHUNK_SIZE):
                    digest.update(chunk); count += len(chunk)
            finally:
                os.close(descriptor)
            result[name] = {"sha256": digest.hexdigest(), "byteCount": count}
        elif stat.S_ISDIR(node.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            try:
                walk(child, name)
            finally:
                os.close(child)
        else:
            raise _unsupported(Path(name), node.st_mode)
    return dict(sorted(result.items()))


def _write_manifest(archive_fd: int, snapshot: dict[str, FileSnapshot]) -> PrototypeManifest:
    checksums = {path: record["sha256"] for path, record in snapshot.items()}
    manifest: PrototypeManifest = {
        "algorithm": "sha256",
        "fileCount": len(snapshot),
        "byteCount": sum(record["byteCount"] for record in snapshot.values()),
        "files": checksums,
    }
    descriptor = os.open(
        ".manifest.json.tmp",
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
        dir_fd=archive_fd,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(manifest, file, ensure_ascii=False, indent=2, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    # Make archive entries and the temp manifest durable before rename. The rename is the
    # completion marker: if power loss loses it, no manifest means safely incomplete.
    os.fsync(archive_fd)
    os.replace(".manifest.json.tmp", "manifest.json", src_dir_fd=archive_fd, dst_dir_fd=archive_fd)
    return manifest


def _build_verified_archive(
    source_path: Path,
    destination_fd: int,
    initial: dict[str, FileSnapshot],
) -> PrototypeManifest:
    """Populate an already-pinned empty destination and verify it before manifest commit."""
    _copy_allowlisted_tree(source_path, destination_fd)
    staged = _snapshot_fd(destination_fd)
    current = _snapshot(source_path)
    if initial != staged or initial != current:
        raise RuntimeError("prototype checksum verification failed")
    manifest = _write_manifest(destination_fd, initial)
    if _snapshot_fd(destination_fd) != initial:
        raise RuntimeError("prototype checksum verification failed")
    return manifest


def preserve_prototype(source: Path, archive: Path) -> PrototypeManifest:
    """Copy, verify, and atomically publish the approved legacy prototype files."""
    source_path = _source_directory(source)
    initial = _snapshot(source_path)
    if not initial:
        raise FileNotFoundError("no allowlisted prototype files found")

    raw_archive = _archive_path(source_path, archive)
    canonical_parent, created_parents = _create_archive_parent(raw_archive.parent)
    archive_path = canonical_parent / raw_archive.name
    try:
        parent_fd = _open_directory_fd(canonical_parent)
    except BaseException as open_error:
        try:
            _cleanup_created_parents(created_parents)
        except RuntimeError as cleanup_error:
            raise RuntimeError(
                f"archive parent cleanup failed after open error: {cleanup_error}"
            ) from open_error
        raise
    try:
        archive_fd, reservation_identity = _reserve_archive_at(parent_fd, raw_archive.name)
    except BaseException:
        # A racing process may have populated an otherwise newly created parent.
        # It is not ours to remove, so preserve the reservation failure instead.
        _cleanup_created_parents(created_parents, report_failures=False)
        os.close(parent_fd)
        raise
    archive_owned_entry = True
    staging_fd: int | None = None
    committed = False
    try:
        current_entry = os.stat(raw_archive.name, dir_fd=parent_fd, follow_symlinks=False)
        if (current_entry.st_dev, current_entry.st_ino) != reservation_identity:
            archive_owned_entry = False
            close_failures = _close_all((archive_fd,))
            if not close_failures:
                archive_fd = None
            if close_failures:
                raise RuntimeError(
                    f"reserved archive changed before opening; descriptor close failed: {close_failures[0]}"
                ) from RuntimeError("reserved archive changed before opening")
            raise RuntimeError("reserved archive changed before opening")
        staging_name = f".staging-{uuid.uuid4().hex}"
        os.mkdir(staging_name, mode=0o700, dir_fd=archive_fd)
        staging_fd = os.open(staging_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=archive_fd)
        _copy_allowlisted_tree(source_path, staging_fd)
        _fsync_fd(staging_fd, "staging root")
        staged = _snapshot_fd(staging_fd)
        current = _snapshot(source_path)
        if initial != staged or initial != current:
            raise RuntimeError("prototype checksum verification failed")
        for relative_path in LEGACY_PATHS:
            try:
                os.stat(relative_path, dir_fd=staging_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            os.replace(relative_path, relative_path, src_dir_fd=staging_fd, dst_dir_fd=archive_fd)
        os.close(staging_fd)
        staging_fd = None
        os.rmdir(staging_name, dir_fd=archive_fd)
        if initial != _snapshot_fd(archive_fd):
            raise RuntimeError("prototype checksum verification failed")
        manifest = _write_manifest(archive_fd, initial)
        committed = True
    except BaseException as operation_error:
        if archive_fd is None or not archive_owned_entry:
            _cleanup_created_parents(created_parents, report_failures=False)
            raise
        try:
            _remove_owned_archive(parent_fd, raw_archive.name, archive_fd)
        except (OSError, RuntimeError) as cleanup_error:
            raise RuntimeError(
                f"incomplete archive without manifest: cleanup failed for {archive_path}: "
                f"{cleanup_error}"
            ) from operation_error
        try:
            _cleanup_created_parents(created_parents)
        except RuntimeError as cleanup_error:
            raise RuntimeError(
                f"incomplete archive without manifest: parent cleanup failed for "
                f"{archive_path}: {cleanup_error}"
            ) from operation_error
        raise
    finally:
        # Manifest rename is the durable commit point; later close errors cannot reverse success.
        _close_all((staging_fd, archive_fd, parent_fd))

    # The original is deliberately retained: a later, separately reviewed retirement task can clean it safely.
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    arguments = parser.parse_args()
    manifest = preserve_prototype(arguments.source, arguments.archive)
    print(json.dumps({"fileCount": manifest["fileCount"], "status": "preserved"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
