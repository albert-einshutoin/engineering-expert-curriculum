"""Import the legacy prototype curriculum into its canonical catalog."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import stat
import sys
import uuid

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from curriculum_builder.catalog import LEGACY_SOURCE_SHA256, canonicalize, serialize_catalog_document, strict_json_loads
from curriculum_builder.errors import CurriculumValidationError


class CatalogPublicationDurabilityError(RuntimeError):
    """The catalog was published, but the parent-directory fsync did not complete."""


class CatalogPublicationIntegrityError(RuntimeError):
    """A same-UID rename race made the published catalog entry untrustworthy."""


def _read_source(path: Path) -> tuple[object, str, tuple[int, int]]:
    raw_path = _absolute_lexical(path, "input")
    parent_path, name, parent_fd = _open_parent(raw_path)
    file_fd: int | None = None
    try:
        file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode):
            raise CurriculumValidationError(f"{path}: source must be a regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(file_fd, 1024 * 1024)
            if not chunk: break
            chunks.append(chunk)
        raw = b"".join(chunks)
        return strict_json_loads(raw, path), hashlib.sha256(raw).hexdigest(), (info.st_dev, info.st_ino)
    except OSError as error:
        raise CurriculumValidationError(f"{path}: cannot read source: {error}") from error
    finally:
        if file_fd is not None: os.close(file_fd)
        os.close(parent_fd)


def _absolute_lexical(path: Path, label: str) -> Path:
    candidate = path if path.is_absolute() else Path.cwd() / path
    if ".." in candidate.parts: raise ValueError(f"{label} path contains parent traversal")
    return candidate


def _open_parent(path: Path) -> tuple[Path, str, int]:
    raw = _absolute_lexical(path, "output")
    name = raw.name
    if not name or name in {".", ".."} or "\0" in name:
        raise ValueError("output name must be a safe basename")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(raw.anchor, flags)
    try:
        for part in raw.parent.parts[1:]:
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd); fd = next_fd
        info = os.fstat(fd)
        if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
            raise PermissionError("output parent must be owned by the current user")
        if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise PermissionError("output parent must not be group/world writable")
        return raw.parent, name, fd
    except BaseException:
        os.close(fd)
        raise


def _same_parent(raw_parent: Path, parent_fd: int) -> bool:
    try:
        _, _, current_fd = _open_parent(raw_parent / "probe")
    except OSError:
        return False
    try:
        return os.fstat(current_fd).st_dev == os.fstat(parent_fd).st_dev and os.fstat(current_fd).st_ino == os.fstat(parent_fd).st_ino
    finally:
        os.close(current_fd)


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0: raise OSError("short write to catalog temporary file")
        view = view[written:]


def _target_is_regular_or_missing(parent_fd: int, name: str, forbidden_identity: tuple[int, int] | None) -> None:
    try: info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError: return
    if not stat.S_ISREG(info.st_mode): raise ValueError("existing output must be a regular file")
    if forbidden_identity == (info.st_dev, info.st_ino): raise ValueError("output must not alias input")


def _cleanup_temp(parent_fd: int, name: str, owned: tuple[int, int]) -> None:
    try: current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError: return
    if (current.st_dev, current.st_ino) == owned: os.unlink(name, dir_fd=parent_fd)


def _write_atomic(path: Path, document: dict[str, object], *, forbidden_identity: tuple[int, int] | None = None) -> None:
    """Publish through a pinned, current-euid-owned private parent.

    This rejects symlinked/untrusted parents and pathname replacement outside the
    pinned directory. POSIX rename cannot predicate on a source inode: a malicious
    same-euid writer racing the final syscall is out of scope; callers run alone.
    Post-replace verification detects that race but intentionally never rolls back.
    """
    parent_path, final_name, parent_fd = _open_parent(path)
    temporary_name: str | None = None
    temporary_identity: tuple[int, int] | None = None
    published = False
    operation_error: BaseException | None = None
    try:
        _target_is_regular_or_missing(parent_fd, final_name, forbidden_identity)
        payload = serialize_catalog_document(document["items"], str(document["generatedFrom"]), str(document["sourceSha256"]))
        temporary_name = f".catalog-{uuid.uuid4().hex}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        temporary_fd = os.open(temporary_name, flags, 0o600, dir_fd=parent_fd)
        try:
            info = os.fstat(temporary_fd); temporary_identity = (info.st_dev, info.st_ino)
            _write_all(temporary_fd, payload)
            os.fchmod(temporary_fd, 0o644)
            os.fsync(temporary_fd)
        finally:
            os.close(temporary_fd)
        if not _same_parent(parent_path, parent_fd): raise RuntimeError("output parent changed before publish")
        current_temp = os.stat(temporary_name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(current_temp.st_mode) or (current_temp.st_dev, current_temp.st_ino) != temporary_identity:
            raise RuntimeError("catalog temporary changed before publish")
        os.replace(temporary_name, final_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        temporary_name = None; published = True
        final_info = os.stat(final_name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(final_info.st_mode) or (final_info.st_dev, final_info.st_ino) != temporary_identity:
            raise CatalogPublicationIntegrityError("catalog published entry integrity is unknown or compromised")
        try: os.fsync(parent_fd)
        except OSError as error: raise CatalogPublicationDurabilityError("catalog published but parent durability is unknown") from error
    except BaseException as error:
        operation_error = error
        if not published and temporary_name is not None and temporary_identity is not None:
            try: _cleanup_temp(parent_fd, temporary_name, temporary_identity)
            except OSError as cleanup_error: raise RuntimeError(f"catalog temporary cleanup failed: {cleanup_error}") from error
        raise
    finally:
        try: os.close(parent_fd)
        except OSError as close_error:
            if operation_error is not None: raise RuntimeError(f"output parent close failed: {close_error}") from operation_error
            if not published: raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path); parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--generated-from", default="prototype-v1"); parser.add_argument("--expected-source-sha256", default=LEGACY_SOURCE_SHA256)
    arguments = parser.parse_args(argv)
    if _absolute_lexical(arguments.input, "input") == _absolute_lexical(arguments.output, "output"):
        parser.error("--input and --output must be different paths")
    try:
        source, source_hash, source_identity = _read_source(arguments.input)
        if source_hash != arguments.expected_source_sha256: raise CurriculumValidationError("source SHA-256 does not match expected value")
        if not isinstance(source, dict): raise CurriculumValidationError("source root must be an object")
        _write_atomic(arguments.output, canonicalize(source, arguments.generated_from, source_sha256=source_hash, expected_lesson_count=1140, expected_domain_count=38, expected_module_count=380), forbidden_identity=source_identity)
    except (CurriculumValidationError, OSError, RuntimeError, ValueError) as error:
        print(f"import failed: {error}", file=sys.stderr); return 1
    return 0


if __name__ == "__main__": raise SystemExit(main())
