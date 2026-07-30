"""Atomically preserve the legacy generated prototype without deleting its source."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
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


class PrototypePublicationDurabilityError(RuntimeError):
    """The final archive was published, but parent-directory durability is unknown."""


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


def _existing_archive_parent(raw_parent: Path) -> Path:
    """Return a canonical operator-prepared archive parent without mutating the filesystem."""
    _validate_existing_components(raw_parent, "archive")
    if not _lexists(raw_parent):
        raise FileNotFoundError(f"archive parent must already exist: {raw_parent}")
    recorded = os.lstat(raw_parent)
    if not stat.S_ISDIR(recorded.st_mode):
        raise ValueError(f"archive parent is not a directory: {raw_parent}")
    canonical = raw_parent.resolve(strict=True)
    effective = os.stat(canonical, follow_symlinks=False)
    if (recorded.st_dev, recorded.st_ino) != (effective.st_dev, effective.st_ino):
        raise RuntimeError(f"archive parent changed while validating: {raw_parent}")
    # The tool must not infer ownership by creating parents; it pins an operator-prepared trusted boundary.
    if hasattr(os, "geteuid") and effective.st_uid != os.geteuid():
        raise PermissionError(f"archive parent must be owned by the current user: {canonical}")
    if effective.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise PermissionError(f"archive parent must not be group/world writable: {canonical}")
    return canonical


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
    except BaseException as operation_error:
        close_failures = _close_all((descriptor,))
        rollback_failure: OSError | None = None
        if recorded is not None:
            try:
                current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if (current.st_dev, current.st_ino) == recorded:
                    os.rmdir(name, dir_fd=parent_fd)
            except OSError as error:
                rollback_failure = error
        if close_failures and rollback_failure:
            raise RuntimeError(
                "private staging cleanup failed: "
                f"descriptor close failed: {close_failures[0]}; rollback failed: {rollback_failure}"
            ) from operation_error
        if close_failures:
            raise RuntimeError(
                f"private staging descriptor close failed: {close_failures[0]}"
            ) from operation_error
        if rollback_failure:
            raise RuntimeError(f"private staging rollback failed: {rollback_failure}") from operation_error
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
        mismatch_error = RuntimeError(f"archive parent changed while opening: {path}")
        close_failures = _close_all((descriptor,))
        if close_failures:
            raise RuntimeError(
                f"directory descriptor cleanup failed after identity mismatch: {close_failures[0]}"
            ) from mismatch_error
        raise mismatch_error
    return descriptor


def _clear_directory_fd(descriptor: int) -> None:
    """Delete entries through a pinned descriptor, never through a replaceable pathname."""
    with os.scandir(descriptor) as entries:
        for entry in entries:
            mode = entry.stat(follow_symlinks=False).st_mode
            if stat.S_ISDIR(mode):
                child = os.open(
                    entry.name,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
                with _managed_descriptor(child, f"directory cleanup: {entry.name}"):
                    _clear_directory_fd(child)
                os.rmdir(entry.name, dir_fd=descriptor)
            else:
                os.unlink(entry.name, dir_fd=descriptor)


def _remove_owned_directory(parent_fd: int, name: str, directory_fd: int) -> None:
    """Remove only the directory whose inode is still the one created by this process."""
    expected = os.fstat(directory_fd)
    current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino):
        raise RuntimeError("owned directory entry was replaced; refusing cleanup")
    _clear_directory_fd(directory_fd)
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


@contextmanager
def _managed_descriptor(descriptor: int, context: str) -> Iterator[int]:
    """Close a descriptor exactly once while retaining any operation error as the cause."""
    try:
        yield descriptor
    except BaseException as operation_error:
        close_failures = _close_all((descriptor,))
        if close_failures:
            raise RuntimeError(
                f"{context} descriptor close failed: {close_failures[0]}"
            ) from operation_error
        raise
    else:
        close_failures = _close_all((descriptor,))
        if close_failures:
            raise RuntimeError(f"{context} descriptor close failed: {close_failures[0]}")


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
                output_file = os.fdopen(output, "wb")
            except BaseException as operation_error:
                close_failures = _close_all((output,))
                if close_failures:
                    raise RuntimeError(
                        f"destination regular file descriptor close failed: {close_failures[0]}"
                    ) from operation_error
                raise
            try:
                with origin.open("rb") as input_file:
                    while chunk := input_file.read(_CHUNK_SIZE):
                        output_file.write(chunk)
                    output_file.flush()
                    _fsync_fd(output_file.fileno(), "destination regular file")
            except BaseException as operation_error:
                try:
                    output_file.close()
                except OSError as close_error:
                    raise RuntimeError(
                        f"destination regular file close failed: {close_error}"
                    ) from operation_error
                raise
            try:
                output_file.close()
            except OSError as close_error:
                raise RuntimeError(f"destination regular file close failed: {close_error}")
            return
        if not stat.S_ISDIR(mode):
            raise _unsupported(origin, mode)
        os.mkdir(name, mode=0o700, dir_fd=destination_fd)
        child_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=destination_fd)
        with _managed_descriptor(child_fd, f"destination directory: {logical_path}"):
            with os.scandir(origin) as entries:
                for entry in entries:
                    copy_node(Path(entry.path), child_fd, entry.name, f"{logical_path}/{entry.name}")
            _fsync_fd(child_fd, f"destination directory: {logical_path}")

    for relative_path in LEGACY_PATHS:
        origin = source / relative_path
        if _lexists(origin):
            copy_node(origin, staging_fd, relative_path, relative_path)


def _snapshot_regular_file_at(directory_fd: int, name: str) -> FileSnapshot:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    with _managed_descriptor(descriptor, f"snapshot regular file: {name}"):
        digest = hashlib.sha256()
        byte_count = 0
        while chunk := os.read(descriptor, _CHUNK_SIZE):
            digest.update(chunk)
            byte_count += len(chunk)
    return {"sha256": digest.hexdigest(), "byteCount": byte_count}


def _snapshot_fd(root_fd: int) -> dict[str, FileSnapshot]:
    result: dict[str, FileSnapshot] = {}

    def walk(directory_fd: int, prefix: str) -> None:
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                relative = f"{prefix}/{entry.name}" if prefix else entry.name
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISREG(mode):
                    result[relative] = _snapshot_regular_file_at(directory_fd, entry.name)
                elif stat.S_ISDIR(mode):
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
                    with _managed_descriptor(child, f"snapshot directory: {relative}"):
                        walk(child, relative)
                else:
                    raise _unsupported(Path(relative), mode)

    for name in LEGACY_PATHS:
        try:
            node = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            continue
        if stat.S_ISREG(node.st_mode):
            result[name] = _snapshot_regular_file_at(root_fd, name)
        elif stat.S_ISDIR(node.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            with _managed_descriptor(child, f"snapshot directory: {name}"):
                walk(child, name)
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
        file = os.fdopen(descriptor, "w", encoding="utf-8")
    except BaseException as operation_error:
        close_failures = _close_all((descriptor,))
        if close_failures:
            raise RuntimeError(
                f"manifest temp descriptor close failed: {close_failures[0]}"
            ) from operation_error
        raise
    try:
        json.dump(manifest, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")
        file.flush()
        _fsync_fd(file.fileno(), "manifest temp")
    except BaseException as operation_error:
        try:
            file.close()
        except OSError as close_error:
            raise RuntimeError(f"manifest temp close failed: {close_error}") from operation_error
        raise
    try:
        file.close()
    except OSError as close_error:
        raise RuntimeError(f"manifest temp close failed: {close_error}")
    # Make archive entries and the temp manifest durable before rename. The rename is the
    # completion marker: if power loss loses it, no manifest means safely incomplete.
    _fsync_fd(archive_fd, "staging root before manifest rename")
    os.replace(".manifest.json.tmp", "manifest.json", src_dir_fd=archive_fd, dst_dir_fd=archive_fd)
    _fsync_fd(archive_fd, "staging root after manifest rename")
    return manifest


def _build_verified_archive(
    source_path: Path,
    destination_fd: int,
    initial: dict[str, FileSnapshot],
) -> PrototypeManifest:
    """Populate an already-pinned empty destination and verify it before manifest commit."""
    _copy_allowlisted_tree(source_path, destination_fd)
    _fsync_fd(destination_fd, "staging root")
    staged = _snapshot_fd(destination_fd)
    current = _snapshot(source_path)
    if initial != staged or initial != current:
        raise RuntimeError("prototype checksum verification failed")
    manifest = _write_manifest(destination_fd, initial)
    if _snapshot_fd(destination_fd) != initial:
        raise RuntimeError("prototype checksum verification failed")
    return manifest


def _publish_verified_archive(
    source_path: Path,
    parent_fd: int,
    target_name: str,
    initial: dict[str, FileSnapshot],
) -> PrototypeManifest:
    """Build a private verified archive and atomically publish it without clobbering target."""
    staging_name, staging_fd, identity = _create_private_staging(parent_fd)
    published = False
    try:
        manifest = _build_verified_archive(source_path, staging_fd, initial)
        _rename_directory_noreplace(parent_fd, staging_name, target_name)
        published = True
        try:
            _fsync_fd(parent_fd, "archive parent after native publish")
        except OSError as error:
            raise PrototypePublicationDurabilityError(
                "archive published but parent-directory fsync failed"
            ) from error
        return manifest
    except BaseException as operation_error:
        if not published:
            try:
                current = os.stat(staging_name, dir_fd=parent_fd, follow_symlinks=False)
                opened = os.fstat(staging_fd)
                if (current.st_dev, current.st_ino) == identity == (opened.st_dev, opened.st_ino):
                    _remove_owned_directory(parent_fd, staging_name, staging_fd)
            except (OSError, RuntimeError) as cleanup_error:
                raise RuntimeError(f"private staging cleanup failed: {cleanup_error}") from operation_error
        raise
    finally:
        # Once rename succeeds the final archive is committed; close failures cannot reverse it.
        close_failures = _close_all((staging_fd,))
        if close_failures and not published:
            close_error = RuntimeError(
                f"private staging descriptor close failed: {close_failures[0]}"
            )
            active_error = sys.exception()
            if active_error is None:
                raise close_error
            raise close_error from active_error


def preserve_prototype(source: Path, archive: Path) -> PrototypeManifest:
    """Copy, verify, and atomically publish the approved legacy prototype files."""
    source_path = _source_directory(source)
    initial = _snapshot(source_path)
    if not initial:
        raise FileNotFoundError("no allowlisted prototype files found")

    raw_archive = _archive_path(source_path, archive)
    canonical_parent = _existing_archive_parent(raw_archive.parent)
    parent_fd = _open_directory_fd(canonical_parent)
    completed = False
    try:
        manifest = _publish_verified_archive(source_path, parent_fd, raw_archive.name, initial)
        completed = True
    except PrototypePublicationDurabilityError:
        # The final archive already exists; parent close failures cannot replace this durability signal.
        completed = True
        raise
    finally:
        # Native publish is the commit point; later parent-descriptor close errors cannot reverse it.
        close_failures = _close_all((parent_fd,))
        if close_failures and not completed:
            close_error = RuntimeError(
                f"archive parent descriptor close failed: {close_failures[0]}"
            )
            active_error = sys.exception()
            if active_error is None:
                raise close_error
            raise close_error from active_error

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
