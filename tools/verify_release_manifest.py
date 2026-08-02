#!/usr/bin/env python3
"""Verify the canonical release manifest for a generated site."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Final


MAX_MANIFEST_BYTES: Final = 128 * 1024
MAX_FILES: Final = 4_096
MAX_FILE_BYTES: Final = 4 * 1024 * 1024
MAX_TOTAL_BYTES: Final = 64 * 1024 * 1024
MAX_DEPTH: Final = 32
MANIFEST_NAME: Final = "release-manifest.json"
_COMMIT = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
_DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_SAFE_SEGMENT = re.compile(r"[A-Za-z0-9._-]+\Z", re.ASCII)
_ALLOWED_SUFFIXES = frozenset({".html", ".css", ".js"})


class ReleaseManifestError(ValueError):
    """The release manifest or covered artifact tree is invalid."""


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    path: PurePosixPath
    bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ReleaseManifest:
    schema_version: int
    commit: str
    files: tuple[ManifestEntry, ...]


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseManifestError("release manifest contains a duplicate key")
        result[key] = value
    return result


def _exact_object(value: object, keys: frozenset[str], field: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise ReleaseManifestError(f"{field} must contain the exact schema keys")
    return value


def _safe_path(raw: object) -> PurePosixPath:
    if type(raw) is not str or not raw or len(raw) > 512 or "%" in raw or "\\" in raw:
        raise ReleaseManifestError("manifest path is not a safe relative path")
    path = PurePosixPath(raw)
    if path.is_absolute() or path.as_posix() != raw or len(path.parts) > MAX_DEPTH:
        raise ReleaseManifestError("manifest path is not normalized")
    if any(part in {"", ".", ".."} or _SAFE_SEGMENT.fullmatch(part) is None for part in path.parts):
        raise ReleaseManifestError("manifest path contains an unsafe segment")
    if path.name == MANIFEST_NAME or path.suffix.casefold() not in _ALLOWED_SUFFIXES:
        raise ReleaseManifestError("manifest path is not a covered static artifact")
    return path


def parse_manifest_bytes(raw: bytes, *, expected_commit: str | None = None) -> ReleaseManifest:
    if type(raw) is not bytes or not raw or len(raw) > MAX_MANIFEST_BYTES:
        raise ReleaseManifestError("release manifest is empty or over budget")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ReleaseManifestError("release manifest is not canonical JSON") from error
    root = _exact_object(value, frozenset({"schemaVersion", "commit", "files"}), "manifest")
    if type(root["schemaVersion"]) is not int or root["schemaVersion"] != 1:
        raise ReleaseManifestError("unsupported release manifest schema")
    commit = root["commit"]
    if type(commit) is not str or _COMMIT.fullmatch(commit) is None:
        raise ReleaseManifestError("manifest commit must be 40 lowercase hexadecimal characters")
    if expected_commit is not None:
        if type(expected_commit) is not str or _COMMIT.fullmatch(expected_commit) is None:
            raise ReleaseManifestError("expected commit is invalid")
        if commit != expected_commit:
            raise ReleaseManifestError("manifest commit does not match the expected commit")
    files = root["files"]
    if type(files) is not list or not files or len(files) > MAX_FILES:
        raise ReleaseManifestError("manifest files must be a bounded non-empty list")
    parsed: list[ManifestEntry] = []
    for index, raw_entry in enumerate(files):
        entry = _exact_object(
            raw_entry, frozenset({"path", "bytes", "sha256"}), f"files[{index}]"
        )
        path = _safe_path(entry["path"])
        byte_count = entry["bytes"]
        digest = entry["sha256"]
        if type(byte_count) is not int or not 0 <= byte_count <= MAX_FILE_BYTES:
            raise ReleaseManifestError("manifest file size is invalid")
        if type(digest) is not str or _DIGEST.fullmatch(digest) is None:
            raise ReleaseManifestError("manifest file digest is invalid")
        parsed.append(ManifestEntry(path, byte_count, digest))
    ordered = tuple(entry.path.as_posix() for entry in parsed)
    if ordered != tuple(sorted(ordered)) or len(set(ordered)) != len(ordered):
        raise ReleaseManifestError("manifest paths must be unique and sorted")
    if sum(entry.bytes for entry in parsed) > MAX_TOTAL_BYTES:
        raise ReleaseManifestError("manifest aggregate bytes exceed the release budget")
    canonical = (
        json.dumps(
            {
                "schemaVersion": 1,
                "commit": commit,
                "files": [
                    {
                        "path": entry.path.as_posix(),
                        "bytes": entry.bytes,
                        "sha256": entry.sha256,
                    }
                    for entry in parsed
                ],
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    if raw != canonical:
        raise ReleaseManifestError("release manifest JSON is not canonical")
    return ReleaseManifest(1, commit, tuple(parsed))


def _fd_flags(*, directory: bool = False) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if (
        type(nofollow) is not int
        or nofollow == 0
        or type(directory_flag) is not int
        or directory_flag == 0
        or os.open not in os.supports_dir_fd
        or os.stat not in os.supports_dir_fd
        or os.scandir not in os.supports_fd
    ):
        raise ReleaseManifestError("descriptor-relative no-follow traversal is unavailable")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | nofollow
    return flags | directory_flag if directory else flags


def _open_descriptor(path, flags: int, *args, **kwargs) -> int:
    return os.open(path, flags, *args, **kwargs)


def _binding_identity(status: os.stat_result) -> tuple[int, int, int]:
    return (status.st_dev, status.st_ino, stat.S_IFMT(status.st_mode))


def _directory_snapshot_identity(
    status: os.stat_result,
) -> tuple[int, int, int, int, int, int]:
    return (
        status.st_dev,
        status.st_ino,
        stat.S_IFMT(status.st_mode),
        status.st_nlink,
        status.st_mtime_ns,
        status.st_ctime_ns,
    )


def _assert_same_identity(
    actual: os.stat_result,
    expected: os.stat_result,
    message: str,
) -> None:
    if _binding_identity(actual) != _binding_identity(expected):
        raise ReleaseManifestError(message)


def _close_descriptor(descriptor: int) -> None:
    active_error = sys.exc_info()[0]
    try:
        os.close(descriptor)
    except OSError as error:
        if active_error is None:
            raise ReleaseManifestError(
                "release descriptor could not be closed safely"
            ) from error


def _read_regular_at(
    parent_descriptor: int,
    name: str,
    expected: os.stat_result,
    max_bytes: int,
) -> bytes:
    try:
        descriptor = _open_descriptor(
            name,
            _fd_flags(),
            dir_fd=parent_descriptor,
        )
    except OSError as error:
        raise ReleaseManifestError("release artifact could not be opened safely") from error
    close_error: OSError | None = None
    try:
        before = os.fstat(descriptor)
        _assert_same_identity(
            before,
            expected,
            "release artifact binding changed before it was opened",
        )
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > max_bytes
        ):
            raise ReleaseManifestError("release artifact is not a bounded single-link regular file")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        source = b"".join(chunks)
        after = os.fstat(descriptor)
        if len(source) > max_bytes or len(source) != before.st_size:
            raise ReleaseManifestError("release artifact changed or exceeded its byte budget")
        identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_nlink,
        )
        final_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_nlink,
        )
        if identity != final_identity:
            raise ReleaseManifestError("release artifact changed while it was read")
        try:
            bound = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        except OSError as error:
            raise ReleaseManifestError(
                "release artifact binding changed while it was read"
            ) from error
        _assert_same_identity(
            bound,
            before,
            "release artifact binding changed while it was read",
        )
        return source
    except OSError as error:
        raise ReleaseManifestError("release artifact could not be read safely") from error
    finally:
        try:
            os.close(descriptor)
        except OSError as error:
            close_error = error
        if close_error is not None and sys.exc_info()[0] is None:
            raise ReleaseManifestError(
                "release artifact could not be closed safely"
            ) from close_error


def _scan_release_tree(
    root: Path,
    *,
    read_manifest: bool,
) -> tuple[dict[PurePosixPath, bytes], bytes | None]:
    if not isinstance(root, Path):
        raise ReleaseManifestError("release root must be a real directory")
    _fd_flags(directory=True)
    try:
        root_binding = os.lstat(root)
    except OSError as error:
        raise ReleaseManifestError("release root could not be inspected safely") from error
    if not stat.S_ISDIR(root_binding.st_mode):
        raise ReleaseManifestError("release root must be a real directory")
    try:
        root_descriptor = _open_descriptor(root, _fd_flags(directory=True))
    except OSError as error:
        raise ReleaseManifestError("release root could not be opened safely") from error
    files: dict[PurePosixPath, bytes] = {}
    manifest_bytes: bytes | None = None
    total = 0

    def revalidate_directory(
        descriptor: int,
        expected: os.stat_result,
        parent: tuple[int, str, os.stat_result] | None,
    ) -> None:
        if _directory_snapshot_identity(os.fstat(descriptor)) != (
            _directory_snapshot_identity(expected)
        ):
            raise ReleaseManifestError("release directory contents changed")
        if parent is not None:
            parent_descriptor, name, binding = parent
            try:
                current = os.stat(
                    name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except OSError as error:
                raise ReleaseManifestError("release directory binding changed") from error
            _assert_same_identity(
                current,
                binding,
                "release directory binding changed",
            )

    def walk(
        descriptor: int,
        relative_directory: PurePosixPath,
        depth: int,
        expected_directory: os.stat_result,
        parent: tuple[int, str, os.stat_result] | None,
    ) -> None:
        nonlocal total, manifest_bytes
        if depth > MAX_DEPTH:
            raise ReleaseManifestError("release tree exceeds its depth budget")
        revalidate_directory(descriptor, expected_directory, parent)
        try:
            with os.scandir(descriptor) as iterator:
                children = sorted(iterator, key=lambda item: item.name)
        except OSError as error:
            raise ReleaseManifestError("release directory cannot be scanned safely") from error
        for child in children:
            revalidate_directory(descriptor, expected_directory, parent)
            relative = (
                PurePosixPath(child.name)
                if relative_directory == PurePosixPath(".")
                else relative_directory / child.name
            )
            try:
                binding = os.stat(
                    child.name,
                    dir_fd=descriptor,
                    follow_symlinks=False,
                )
            except OSError as error:
                raise ReleaseManifestError("release entry binding changed") from error
            if stat.S_ISLNK(binding.st_mode):
                raise ReleaseManifestError("release tree contains a symbolic link")
            if stat.S_ISDIR(binding.st_mode):
                try:
                    child_descriptor = _open_descriptor(
                        child.name,
                        _fd_flags(directory=True),
                        dir_fd=descriptor,
                    )
                except OSError as error:
                    raise ReleaseManifestError(
                        "release directory could not be opened safely"
                    ) from error
                try:
                    opened = os.fstat(child_descriptor)
                    _assert_same_identity(
                        opened,
                        binding,
                        "release directory binding changed before it was opened",
                    )
                    walk(
                        child_descriptor,
                        relative,
                        depth + 1,
                        opened,
                        (descriptor, child.name, binding),
                    )
                    revalidate_directory(descriptor, expected_directory, parent)
                    revalidate_directory(
                        child_descriptor,
                        opened,
                        (descriptor, child.name, binding),
                    )
                finally:
                    _close_descriptor(child_descriptor)
                continue
            if child.name == MANIFEST_NAME and relative.parent == PurePosixPath("."):
                if not stat.S_ISREG(binding.st_mode) or binding.st_nlink != 1:
                    raise ReleaseManifestError("release manifest output is unsafe")
                if read_manifest:
                    manifest_bytes = _read_regular_at(
                        descriptor,
                        child.name,
                        binding,
                        MAX_MANIFEST_BYTES,
                    )
                continue
            if (
                not stat.S_ISREG(binding.st_mode)
                or relative.suffix.casefold() not in _ALLOWED_SUFFIXES
            ):
                raise ReleaseManifestError("release tree contains an unexpected artifact")
            if len(files) >= MAX_FILES:
                raise ReleaseManifestError("release tree exceeds its file budget")
            source = _read_regular_at(
                descriptor,
                child.name,
                binding,
                MAX_FILE_BYTES,
            )
            total += len(source)
            if total > MAX_TOTAL_BYTES:
                raise ReleaseManifestError("release tree exceeds its aggregate byte budget")
            files[relative] = source
        revalidate_directory(descriptor, expected_directory, parent)

    try:
        opened_root = os.fstat(root_descriptor)
        _assert_same_identity(
            opened_root,
            root_binding,
            "release root binding changed before it was opened",
        )
        walk(
            root_descriptor,
            PurePosixPath("."),
            0,
            opened_root,
            None,
        )
        try:
            final_root = os.lstat(root)
        except OSError as error:
            raise ReleaseManifestError("release root binding changed") from error
        _assert_same_identity(
            final_root,
            root_binding,
            "release root binding changed",
        )
        if not files:
            raise ReleaseManifestError("release tree contains no static artifacts")
        return files, manifest_bytes
    finally:
        _close_descriptor(root_descriptor)


def scan_release_files(root: Path) -> dict[PurePosixPath, bytes]:
    files, _manifest = _scan_release_tree(root, read_manifest=False)
    return files


def verify_release_manifest(
    root: Path, manifest: Path, *, expected_commit: str | None = None
) -> ReleaseManifest:
    if not isinstance(manifest, Path) or manifest.parent != root or manifest.name != MANIFEST_NAME:
        raise ReleaseManifestError("manifest must be the exact release-root manifest")
    files, manifest_bytes = _scan_release_tree(root, read_manifest=True)
    if manifest_bytes is None:
        raise ReleaseManifestError("release manifest is missing")
    parsed = parse_manifest_bytes(manifest_bytes, expected_commit=expected_commit)
    expected = {entry.path: entry for entry in parsed.files}
    if set(files) != set(expected):
        raise ReleaseManifestError("manifest coverage does not match the release tree")
    for path, source in files.items():
        entry = expected[path]
        if entry.bytes != len(source) or entry.sha256 != hashlib.sha256(source).hexdigest():
            raise ReleaseManifestError("release artifact does not match its manifest entry")
    return parsed


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--expected-commit")
    options = parser.parse_args(arguments)
    try:
        verify_release_manifest(
            Path(options.root), Path(options.manifest), expected_commit=options.expected_commit
        )
    except ReleaseManifestError as error:
        print(f"release manifest verification failed: {error}", file=sys.stderr)
        return 1
    except Exception:
        print("release manifest verification failed safely", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
