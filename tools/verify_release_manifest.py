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
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
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


def _read_regular(path: Path, max_bytes: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ReleaseManifestError("release artifact could not be opened safely") from error
    close_error: OSError | None = None
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > max_bytes:
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


def scan_release_files(root: Path) -> dict[PurePosixPath, bytes]:
    if not isinstance(root, Path) or root.is_symlink() or not root.is_dir():
        raise ReleaseManifestError("release root must be a real directory")
    files: dict[PurePosixPath, bytes] = {}
    total = 0
    stack = [(root, PurePosixPath("."), 0)]
    while stack:
        directory, relative_directory, depth = stack.pop()
        if depth > MAX_DEPTH:
            raise ReleaseManifestError("release tree exceeds its depth budget")
        try:
            children = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as error:
            raise ReleaseManifestError("release directory cannot be scanned safely") from error
        for child in children:
            relative = (
                PurePosixPath(child.name)
                if relative_directory == PurePosixPath(".")
                else relative_directory / child.name
            )
            if child.is_symlink():
                raise ReleaseManifestError("release tree contains a symbolic link")
            if child.is_dir(follow_symlinks=False):
                stack.append((Path(child.path), relative, depth + 1))
                continue
            if child.name == MANIFEST_NAME and relative.parent == PurePosixPath("."):
                continue
            if (
                not child.is_file(follow_symlinks=False)
                or relative.suffix.casefold() not in _ALLOWED_SUFFIXES
            ):
                raise ReleaseManifestError("release tree contains an unexpected artifact")
            if len(files) >= MAX_FILES:
                raise ReleaseManifestError("release tree exceeds its file budget")
            source = _read_regular(Path(child.path), MAX_FILE_BYTES)
            total += len(source)
            if total > MAX_TOTAL_BYTES:
                raise ReleaseManifestError("release tree exceeds its aggregate byte budget")
            files[relative] = source
    if not files:
        raise ReleaseManifestError("release tree contains no static artifacts")
    return files


def verify_release_manifest(
    root: Path, manifest: Path, *, expected_commit: str | None = None
) -> ReleaseManifest:
    if not isinstance(manifest, Path) or manifest.parent != root or manifest.name != MANIFEST_NAME:
        raise ReleaseManifestError("manifest must be the exact release-root manifest")
    parsed = parse_manifest_bytes(
        _read_regular(manifest, MAX_MANIFEST_BYTES), expected_commit=expected_commit
    )
    files = scan_release_files(root)
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
