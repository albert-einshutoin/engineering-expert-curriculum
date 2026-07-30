"""Atomically preserve the legacy generated prototype without deleting its source."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import TypedDict


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


def _validate_path_node(path: Path, label: str, *, directory: bool = False) -> None:
    """Inspect an existing node with lstat, never following a final symlink."""
    if not _lexists(path):
        return
    mode = os.lstat(path).st_mode
    if stat.S_ISLNK(mode):
        raise ValueError(f"{label} contains a symbolic link: {path}")
    if directory and not stat.S_ISDIR(mode):
        raise ValueError(f"{label} is not a directory: {path}")


def _validate_descendant_components(root: Path, path: Path, label: str) -> None:
    """Reject symlinks below a trusted source root before resolving an archive path."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return
    current = root
    for part in relative.parts:
        current /= part
        _validate_path_node(current, label, directory=current != path)


def _source_directory(source: Path) -> Path:
    candidate = source.absolute()
    _validate_path_node(candidate, "source", directory=True)
    if not _lexists(candidate):
        raise FileNotFoundError(f"source does not exist: {candidate}")
    return candidate


def _archive_path(source: Path, archive: Path) -> Path:
    candidate = archive.absolute()
    if _lexists(candidate):
        # lstat is intentionally used before rejection so dangling symlinks count as existing.
        os.lstat(candidate)
        raise FileExistsError(f"archive already exists: {candidate}")

    try:
        relative_to_source = candidate.relative_to(source)
    except ValueError:
        _validate_path_node(candidate.parent, "archive", directory=True)
        return candidate
    _validate_descendant_components(source, candidate, "archive")
    if relative_to_source.parts and relative_to_source.parts[0] in LEGACY_PATHS:
        raise ValueError(f"archive is inside an allowlisted subtree: {candidate}")
    return candidate


def _reserve_archive(archive: Path) -> None:
    """Atomically reserve the archive name without replacing any existing entry."""
    try:
        archive.mkdir(mode=0o700, exist_ok=False)
    except FileExistsError as error:
        raise FileExistsError(f"archive already exists: {archive}") from error


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


def _copy_allowlisted_tree(source: Path, staging: Path) -> None:
    def copy_node(origin: Path, destination: Path) -> None:
        mode = os.lstat(origin).st_mode
        if stat.S_ISREG(mode):
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, destination)
            return
        if not stat.S_ISDIR(mode):
            raise _unsupported(origin, mode)
        destination.mkdir()
        with os.scandir(origin) as entries:
            for entry in entries:
                copy_node(Path(entry.path), destination / entry.name)

    for relative_path in LEGACY_PATHS:
        origin = source / relative_path
        if _lexists(origin):
            copy_node(origin, staging / relative_path)


def _write_manifest(archive: Path, snapshot: dict[str, FileSnapshot]) -> PrototypeManifest:
    checksums = {path: record["sha256"] for path, record in snapshot.items()}
    manifest: PrototypeManifest = {
        "algorithm": "sha256",
        "fileCount": len(snapshot),
        "byteCount": sum(record["byteCount"] for record in snapshot.values()),
        "files": checksums,
    }
    temporary_manifest = archive / ".manifest.json.tmp"
    descriptor = os.open(
        temporary_manifest,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
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
    # Publish the manifest only after its complete durable temp-file write succeeds.
    os.replace(temporary_manifest, archive / "manifest.json")
    directory_descriptor = os.open(archive, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)
    return manifest


def preserve_prototype(source: Path, archive: Path) -> PrototypeManifest:
    """Copy, verify, and atomically publish the approved legacy prototype files."""
    source_path = _source_directory(source)
    archive_path = _archive_path(source_path, archive)

    initial = _snapshot(source_path)
    if not initial:
        raise FileNotFoundError("no allowlisted prototype files found")

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    _validate_path_node(archive_path.parent, "archive", directory=True)
    _reserve_archive(archive_path)
    try:
        staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=archive_path))
        _copy_allowlisted_tree(source_path, staging)
        staged = _snapshot(staging)
        current = _snapshot(source_path)
        if initial != staged or initial != current:
            raise RuntimeError("prototype checksum verification failed")
        for relative_path in LEGACY_PATHS:
            staged_path = staging / relative_path
            if _lexists(staged_path):
                os.replace(staged_path, archive_path / relative_path)
        staging.rmdir()
        archived = _snapshot(archive_path)
        if initial != archived:
            raise RuntimeError("prototype checksum verification failed")
        manifest = _write_manifest(archive_path, initial)
    except BaseException:
        try:
            shutil.rmtree(archive_path)
        except OSError as cleanup_error:
            raise RuntimeError(
                f"incomplete archive without manifest: cleanup failed for {archive_path}"
            ) from cleanup_error
        raise

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
