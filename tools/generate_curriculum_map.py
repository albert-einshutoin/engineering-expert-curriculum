#!/usr/bin/env python3
"""Regenerate or verify the deterministic curriculum-map data block."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import sys
from typing import Final
import uuid


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from curriculum_builder.curriculum_map import (  # noqa: E402
    render_generated_curriculum_map,
    replace_generated_curriculum_map,
)
from curriculum_builder.build import (  # noqa: E402
    _DirectoryHandle,
    _open_trusted_directory,
    _read_stable_regular_file,
    _require_owned_safe_node,
    _stat_signature,
    _verify_directory_identity,
)
from curriculum_builder.errors import CurriculumValidationError  # noqa: E402


MAX_CURRICULUM_MAP_BYTES: Final = 512 * 1024
_TARGET_NAME: Final = "curriculum-map.md"


class CurriculumMapPublicationDurabilityError(RuntimeError):
    """The new map is visible but its parent fsync did not complete."""


class CurriculumMapPostCommitError(RuntimeError):
    """The new map is durable, but its parent handle teardown failed."""


def _read_document(
    parent: _DirectoryHandle,
) -> tuple[bytes, str, tuple[int, int, int, int, int, int], int]:
    """Return UTF-8 text bound to one stable regular-file identity."""
    try:
        before = os.stat(
            _TARGET_NAME,
            dir_fd=parent.descriptor,
            follow_symlinks=False,
        )
        raw = _read_stable_regular_file(
            parent,
            _TARGET_NAME,
            MAX_CURRICULUM_MAP_BYTES,
        )
        after = os.stat(
            _TARGET_NAME,
            dir_fd=parent.descriptor,
            follow_symlinks=False,
        )
    except CurriculumValidationError:
        raise
    except OSError:
        raise CurriculumValidationError(
            "curriculum map cannot be read safely"
        ) from None
    if _stat_signature(before) != _stat_signature(after):
        raise CurriculumValidationError("curriculum map changed during read")
    try:
        document = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise CurriculumValidationError(
            "curriculum map must be valid UTF-8"
        ) from None
    return raw, document, _stat_signature(after), stat.S_IMODE(after.st_mode)


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short write to curriculum map temporary file")
        view = view[written:]


def _cleanup_temporary(
    parent: _DirectoryHandle,
    name: str,
    identity: tuple[int, int],
) -> None:
    try:
        current = os.stat(
            name,
            dir_fd=parent.descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    if (current.st_dev, current.st_ino) == identity:
        os.unlink(name, dir_fd=parent.descriptor)


def _write_document_atomic(
    parent: _DirectoryHandle,
    payload: bytes,
    *,
    expected_signature: tuple[int, int, int, int, int, int],
    target_mode: int,
) -> None:
    """Durably replace the reviewed document without reopening its pathname.

    The temporary file is private and fsynced before rename. Persistent target
    replacement is rejected immediately before the atomic commit. POSIX has no
    portable compare-and-swap rename, so the final same-euid syscall gap and an
    ABA rename require the same exclusive-workspace contract as the site build.
    """
    if type(payload) is not bytes or len(payload) > MAX_CURRICULUM_MAP_BYTES:
        raise CurriculumValidationError(
            "generated curriculum map exceeds maximum byte count"
        )
    temporary_name = f".curriculum-map-{uuid.uuid4().hex}.tmp"
    temporary_descriptor: int | None = None
    temporary_identity: tuple[int, int] | None = None
    published = False
    operation_error: BaseException | None = None
    try:
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0)
        )
        temporary_descriptor = os.open(
            temporary_name,
            flags,
            0o600,
            dir_fd=parent.descriptor,
        )
        opened = os.fstat(temporary_descriptor)
        _require_owned_safe_node(
            opened,
            "curriculum map temporary",
            directory=False,
        )
        temporary_identity = (opened.st_dev, opened.st_ino)
        _write_all(temporary_descriptor, payload)
        os.fchmod(temporary_descriptor, target_mode)
        os.fsync(temporary_descriptor)
        descriptor_to_close = temporary_descriptor
        # close(2) failure has platform-dependent ownership semantics. Transfer
        # ownership before the call so an ambiguous result is never retried on
        # a descriptor number that another thread may already have reused.
        temporary_descriptor = None
        os.close(descriptor_to_close)

        _verify_directory_identity(parent)
        current_temporary = os.stat(
            temporary_name,
            dir_fd=parent.descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(current_temporary.st_mode)
            or (current_temporary.st_dev, current_temporary.st_ino)
            != temporary_identity
        ):
            raise CurriculumValidationError(
                "curriculum map temporary changed before publish"
            )
        current = os.stat(
            _TARGET_NAME,
            dir_fd=parent.descriptor,
            follow_symlinks=False,
        )
        _require_owned_safe_node(
            current,
            "curriculum map",
            directory=False,
        )
        if _stat_signature(current) != expected_signature:
            raise CurriculumValidationError(
                "curriculum map changed before publish"
            )

        os.replace(
            temporary_name,
            _TARGET_NAME,
            src_dir_fd=parent.descriptor,
            dst_dir_fd=parent.descriptor,
        )
        published = True
        temporary_name = ""
        final = os.stat(
            _TARGET_NAME,
            dir_fd=parent.descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(final.st_mode)
            or (final.st_dev, final.st_ino) != temporary_identity
        ):
            raise RuntimeError("published curriculum map integrity is unknown")
        try:
            os.fsync(parent.descriptor)
        except OSError as error:
            raise CurriculumMapPublicationDurabilityError(
                "curriculum map is visible but parent durability is unknown"
            ) from error
    except BaseException as error:
        operation_error = error
        if (
            not published
            and temporary_name
            and temporary_identity is not None
        ):
            try:
                _cleanup_temporary(
                    parent,
                    temporary_name,
                    temporary_identity,
                )
            except OSError as cleanup_error:
                # Cleanup evidence is secondary: callers need the write/fsync
                # failure that prevented publication as the primary diagnosis.
                error.add_note(
                    "curriculum map temporary cleanup also failed: "
                    f"{cleanup_error}"
                )
        raise
    finally:
        if temporary_descriptor is not None:
            descriptor_to_close = temporary_descriptor
            temporary_descriptor = None
            try:
                os.close(descriptor_to_close)
            except OSError as close_error:
                if operation_error is not None:
                    operation_error.add_note(
                        "curriculum map temporary also failed to close"
                    )
                else:
                    raise RuntimeError(
                        "curriculum map temporary close failed"
                    ) from close_error


def main(
    arguments: list[str] | None = None,
    *,
    repository_root: Path | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the checked-in generated block is stale",
    )
    options = parser.parse_args(arguments)
    root = REPOSITORY_ROOT if repository_root is None else repository_root
    if type(root) is not type(Path()):
        print(
            "curriculum map failed: repository root must be an exact Path",
            file=sys.stderr,
        )
        return 1
    published = False
    success_message: str | None = None
    failure_message: str | None = None
    try:
        try:
            with _open_trusted_directory(
                root / "docs",
                "curriculum map parent",
            ) as parent:
                before_raw, before, signature, mode = _read_document(parent)
                after = replace_generated_curriculum_map(
                    before,
                    render_generated_curriculum_map(root),
                )
                after_raw = after.encode("utf-8")
                if len(after_raw) > MAX_CURRICULUM_MAP_BYTES:
                    raise CurriculumValidationError(
                        "generated curriculum map exceeds maximum byte count"
                    )

                # Rendering may be long enough for another author to save the
                # document. Re-read before deciding current/stale or publishing.
                current_raw, _current, current_signature, _current_mode = (
                    _read_document(parent)
                )
                if current_raw != before_raw or current_signature != signature:
                    raise CurriculumValidationError(
                        "curriculum map changed during generation"
                    )
                if options.check:
                    if before_raw != after_raw:
                        failure_message = (
                            "docs/curriculum-map.md generated block is stale"
                        )
                    else:
                        success_message = (
                            "docs/curriculum-map.md generated block is current"
                        )
                elif before_raw != after_raw:
                    _write_document_atomic(
                        parent,
                        after_raw,
                        expected_signature=signature,
                        target_mode=mode,
                    )
                    # The write helper returned only after file and parent fsync.
                    # Record this before context teardown so a later close error
                    # cannot be misreported as a pre-publication failure.
                    published = True
                    success_message = "updated docs/curriculum-map.md"
                else:
                    success_message = (
                        "docs/curriculum-map.md is already current"
                    )
        except (CurriculumValidationError, OSError, RuntimeError) as error:
            if published:
                raise CurriculumMapPostCommitError(
                    "curriculum map is published and is visible, but parent "
                    f"handle teardown failed: {error}"
                ) from error
            raise

        # User-facing success is emitted only after descriptor identity checks
        # and close have completed, so stdout never contradicts the exit code.
        if failure_message is not None:
            print(failure_message, file=sys.stderr)
            return 1
        if success_message is None:
            raise RuntimeError("curriculum map outcome was not determined")
        print(success_message)
        return 0
    except (CurriculumValidationError, OSError, RuntimeError) as error:
        print(f"curriculum map failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
