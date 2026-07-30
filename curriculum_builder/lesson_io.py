"""Descriptor-pinned, bounded reads for lesson metadata."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
import unicodedata

from .errors import CurriculumValidationError


_READ_CHUNK_BYTES = 64 * 1024
_MAX_LESSON_LABEL_CHARACTERS = 255
_LOG_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Zl", "Zp"})


@dataclass(frozen=True, slots=True)
class _DirectoryBinding:
    descriptor: int
    parent_descriptor: int | None
    name: str
    signature: tuple[int, int, int, int, int]


def read_stable_lesson_file(path: Path, maximum_bytes: int) -> bytes:
    """Read a lesson through a symlink-free, revalidated descriptor chain."""
    label = _validated_lesson_label(path)
    descriptors: list[int] = []
    primary: BaseException | None = None
    result: bytes | None = None
    try:
        result = _read_with_pinned_ancestors(
            path,
            maximum_bytes,
            label,
            descriptors,
        )
    except CurriculumValidationError as error:
        primary = error
    except OSError:
        primary = CurriculumValidationError(
            f"{label}: lesson cannot be read safely"
        )
    except BaseException as error:
        primary = error

    close_failures = _close_once_in_reverse(descriptors)
    if primary is not None:
        for _failure in close_failures:
            primary.add_note("lesson descriptor also failed to close")
        raise primary from None
    if close_failures:
        close_error = CurriculumValidationError(
            f"{label}: lesson descriptor close failed"
        )
        for _failure in close_failures[1:]:
            close_error.add_note("another lesson descriptor failed to close")
        raise close_error from None
    assert result is not None
    return result


def _validated_lesson_label(path: Path) -> str:
    label = path.name or "lesson"
    # The filename is retained for useful diagnostics only after bounding it
    # and rejecting characters that can alter log structure or display order.
    if any(
        unicodedata.category(character) in _LOG_UNSAFE_CATEGORIES
        for character in str(path)
    ) or len(label) > _MAX_LESSON_LABEL_CHARACTERS:
        raise CurriculumValidationError("lesson path is invalid")
    return label


def _read_with_pinned_ancestors(
    path: Path,
    maximum_bytes: int,
    label: str,
    descriptors: list[int],
) -> bytes:
    absolute = _lexical_absolute(path, label)
    directory_flags = _directory_open_flags(label)
    root_before = os.stat(absolute.anchor, follow_symlinks=False)
    if not stat.S_ISDIR(root_before.st_mode):
        raise CurriculumValidationError(
            f"{label}: lesson root must be a directory"
        )
    root_descriptor = os.open(absolute.anchor, directory_flags)
    descriptors.append(root_descriptor)
    root_opened = os.fstat(root_descriptor)
    if (
        not stat.S_ISDIR(root_opened.st_mode)
        or _directory_signature(root_opened)
        != _directory_signature(root_before)
    ):
        raise CurriculumValidationError(
            f"{label}: lesson ancestor changed while opening"
        )

    bindings = [
        _DirectoryBinding(
            descriptor=root_descriptor,
            parent_descriptor=None,
            name=absolute.anchor,
            signature=_directory_signature(root_opened),
        )
    ]
    parent_descriptor = root_descriptor
    parts = absolute.parts[1:]
    for component in parts[:-1]:
        before = os.stat(
            component,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if stat.S_ISLNK(before.st_mode):
            raise CurriculumValidationError(
                f"{label}: lesson path contains a symbolic link"
            )
        if not stat.S_ISDIR(before.st_mode):
            raise CurriculumValidationError(
                f"{label}: lesson ancestor must be a directory"
            )
        descriptor = os.open(
            component,
            directory_flags,
            dir_fd=parent_descriptor,
        )
        descriptors.append(descriptor)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or _directory_signature(opened) != _directory_signature(before)
        ):
            raise CurriculumValidationError(
                f"{label}: lesson ancestor changed while opening"
            )
        bindings.append(
            _DirectoryBinding(
                descriptor=descriptor,
                parent_descriptor=parent_descriptor,
                name=component,
                signature=_directory_signature(opened),
            )
        )
        parent_descriptor = descriptor

    leaf = parts[-1]
    file_descriptor, opened = _open_regular_file(
        leaf,
        parent_descriptor,
        maximum_bytes,
        label,
        descriptors,
    )
    contents = _read_exact_file(file_descriptor, opened, label)
    current = os.stat(
        leaf,
        dir_fd=parent_descriptor,
        follow_symlinks=False,
    )
    if _file_signature(current) != _file_signature(opened):
        raise CurriculumValidationError(
            f"{label}: lesson changed during read"
        )
    _revalidate_ancestor_bindings(bindings, label)
    return contents


def _lexical_absolute(path: Path, label: str) -> Path:
    if ".." in path.parts:
        raise CurriculumValidationError(
            f"{label}: lesson path contains parent traversal"
        )
    absolute = path if path.is_absolute() else Path.cwd() / path
    if not absolute.is_absolute() or len(absolute.parts) < 2:
        raise CurriculumValidationError(f"{label}: lesson path is invalid")
    return absolute


def _directory_open_flags(label: str) -> int:
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise CurriculumValidationError(
            f"{label}: safe lesson descriptors are not supported"
        )
    return (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )


def _open_regular_file(
    leaf: str,
    parent_descriptor: int,
    maximum_bytes: int,
    label: str,
    descriptors: list[int],
) -> tuple[int, os.stat_result]:
    before = os.stat(
        leaf,
        dir_fd=parent_descriptor,
        follow_symlinks=False,
    )
    if not stat.S_ISREG(before.st_mode):
        raise CurriculumValidationError(
            f"{label}: lesson must be a regular file"
        )
    if before.st_size > maximum_bytes:
        raise CurriculumValidationError(
            f"{label}: lesson exceeds maximum byte count"
        )
    flags = (
        os.O_RDONLY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor = os.open(leaf, flags, dir_fd=parent_descriptor)
    descriptors.append(descriptor)
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISREG(opened.st_mode)
        or _file_signature(opened) != _file_signature(before)
    ):
        raise CurriculumValidationError(
            f"{label}: lesson changed during read"
        )
    return descriptor, opened


def _read_exact_file(
    descriptor: int,
    opened: os.stat_result,
    label: str,
) -> bytes:
    remaining = opened.st_size
    chunks: list[bytes] = []
    while remaining:
        chunk = os.read(descriptor, min(_READ_CHUNK_BYTES, remaining))
        if not chunk or len(chunk) > remaining:
            raise CurriculumValidationError(
                f"{label}: lesson changed during read"
            )
        chunks.append(chunk)
        remaining -= len(chunk)
    if os.read(descriptor, 1):
        raise CurriculumValidationError(
            f"{label}: lesson changed during read"
        )
    after = os.fstat(descriptor)
    if _file_signature(after) != _file_signature(opened):
        raise CurriculumValidationError(
            f"{label}: lesson changed during read"
        )
    return b"".join(chunks)


def _revalidate_ancestor_bindings(
    bindings: list[_DirectoryBinding],
    label: str,
) -> None:
    for binding in bindings:
        opened = os.fstat(binding.descriptor)
        if _directory_signature(opened) != binding.signature:
            raise CurriculumValidationError(
                f"{label}: lesson ancestor changed during read"
            )
        if binding.parent_descriptor is None:
            current = os.stat(binding.name, follow_symlinks=False)
        else:
            current = os.stat(
                binding.name,
                dir_fd=binding.parent_descriptor,
                follow_symlinks=False,
            )
        if _directory_signature(current) != binding.signature:
            raise CurriculumValidationError(
                f"{label}: lesson ancestor changed during read"
            )


def _directory_signature(
    value: os.stat_result,
) -> tuple[int, int, int, int, int]:
    # Directory timestamps detect a rename-away/restore ABA attack even when
    # the descriptor and lexical binding end on the original inode.
    return (
        value.st_dev,
        value.st_ino,
        stat.S_IFMT(value.st_mode),
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _file_signature(
    value: os.stat_result,
) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        stat.S_IFMT(value.st_mode),
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _close_once_in_reverse(descriptors: list[int]) -> tuple[OSError, ...]:
    failures: list[OSError] = []
    for descriptor in reversed(descriptors):
        try:
            os.close(descriptor)
        except OSError as error:
            failures.append(error)
    return tuple(failures)
