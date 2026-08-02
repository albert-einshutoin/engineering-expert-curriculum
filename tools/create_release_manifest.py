#!/usr/bin/env python3
"""Create the canonical release manifest for a generated site."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import stat
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.verify_release_manifest import (  # noqa: E402
    MANIFEST_NAME,
    ReleaseManifestError,
    parse_manifest_bytes,
    scan_release_files,
    scan_release_files_at,
)


class ReleaseManifestPostCommitError(ReleaseManifestError):
    """The manifest was replaced, but publication durability is uncertain."""

    published = True


def _encode_manifest_bytes(
    files: dict[PurePosixPath, bytes],
    *,
    commit: str,
) -> bytes:
    value = {
        "schemaVersion": 1,
        "commit": commit,
        "files": [
            {
                "path": path.as_posix(),
                "bytes": len(source),
                "sha256": hashlib.sha256(source).hexdigest(),
            }
            for path, source in sorted(files.items(), key=lambda item: item[0].as_posix())
        ],
    }
    raw = json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8") + b"\n"
    parse_manifest_bytes(raw, expected_commit=commit)
    return raw


def create_manifest_bytes(root: Path, *, commit: str) -> bytes:
    return _encode_manifest_bytes(scan_release_files(root), commit=commit)


def write_release_manifest(root: Path, output: Path, *, commit: str) -> None:
    if (
        not isinstance(root, Path)
        or not isinstance(output, Path)
        or output.parent != root
        or output.name != MANIFEST_NAME
    ):
        raise ReleaseManifestError("output must be the exact release-root manifest")
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if type(nofollow) is not int or type(directory_flag) is not int:
        raise ReleaseManifestError("safe manifest publication is unavailable")
    try:
        root_binding = os.lstat(root)
        root_descriptor = os.open(
            root,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | nofollow | directory_flag,
        )
    except OSError as error:
        raise ReleaseManifestError("manifest root could not be opened safely") from error
    try:
        opened_root = os.fstat(root_descriptor)
    except OSError as error:
        try:
            os.close(root_descriptor)
        except OSError:
            pass
        raise ReleaseManifestError("manifest root could not be inspected safely") from error
    if (
        not stat.S_ISDIR(opened_root.st_mode)
        or (opened_root.st_dev, opened_root.st_ino)
        != (root_binding.st_dev, root_binding.st_ino)
    ):
        os.close(root_descriptor)
        raise ReleaseManifestError("manifest root binding changed before publication")
    try:
        # Scan and publish through the same descriptor so a path swap cannot make
        # the manifest describe one tree while it is written into another tree.
        raw = _encode_manifest_bytes(
            scan_release_files_at(root_descriptor, opened_root),
            commit=commit,
        )
        try:
            scanned_root = os.lstat(root)
        except OSError as error:
            raise ReleaseManifestError(
                "manifest root binding changed during its release scan"
            ) from error
        if (scanned_root.st_dev, scanned_root.st_ino) != (
            root_binding.st_dev,
            root_binding.st_ino,
        ):
            raise ReleaseManifestError(
                "manifest root binding changed during its release scan"
            )
    except BaseException:
        try:
            os.close(root_descriptor)
        except OSError:
            pass
        raise
    try:
        existing = os.stat(
            MANIFEST_NAME,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        existing = None
    except OSError as error:
        os.close(root_descriptor)
        raise ReleaseManifestError("existing manifest could not be inspected safely") from error
    if existing is not None and (
        not stat.S_ISREG(existing.st_mode) or existing.st_nlink != 1
    ):
        os.close(root_descriptor)
        raise ReleaseManifestError("existing manifest output is unsafe")
    temporary_name: str | None = None
    temporary_descriptor: int | None = None
    published = False
    try:
        for _attempt in range(32):
            candidate = f".release-manifest-{secrets.token_hex(12)}"
            try:
                temporary_descriptor = os.open(
                    candidate,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_CLOEXEC", 0)
                    | nofollow,
                    0o600,
                    dir_fd=root_descriptor,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        if temporary_descriptor is None or temporary_name is None:
            raise ReleaseManifestError("manifest temporary name budget was exhausted")
        with os.fdopen(temporary_descriptor, "wb", closefd=True) as stream:
            temporary_descriptor = None
            if stream.write(raw) != len(raw):
                raise ReleaseManifestError("manifest write was incomplete")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(
            temporary_name,
            MANIFEST_NAME,
            src_dir_fd=root_descriptor,
            dst_dir_fd=root_descriptor,
        )
        published = True
        try:
            current_root = os.lstat(root)
        except OSError as error:
            raise ReleaseManifestPostCommitError(
                "release manifest was replaced but its root metadata was unavailable"
            ) from error
        if (current_root.st_dev, current_root.st_ino) != (
            root_binding.st_dev,
            root_binding.st_ino,
        ):
            raise ReleaseManifestPostCommitError(
                "release manifest was replaced after its root binding changed"
            )
        try:
            os.fsync(root_descriptor)
        except OSError as error:
            raise ReleaseManifestPostCommitError(
                "release manifest was replaced but its directory sync failed"
            ) from error
        try:
            final_root = os.lstat(root)
        except OSError as error:
            raise ReleaseManifestPostCommitError(
                "release manifest was replaced but its final root metadata was unavailable"
            ) from error
        if (final_root.st_dev, final_root.st_ino) != (
            root_binding.st_dev,
            root_binding.st_ino,
        ):
            raise ReleaseManifestPostCommitError(
                "release manifest root changed during its directory sync"
            )
    except Exception:
        if not published and temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=root_descriptor)
            except OSError:
                pass
        raise
    finally:
        if temporary_descriptor is not None:
            try:
                os.close(temporary_descriptor)
            except OSError:
                pass
        active_error = sys.exc_info()[0]
        try:
            os.close(root_descriptor)
        except OSError as error:
            if active_error is None:
                if published:
                    raise ReleaseManifestPostCommitError(
                        "release manifest was replaced but its root close failed"
                    ) from error
                raise ReleaseManifestError(
                    "manifest root could not be closed safely"
                ) from error


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", required=True)
    options = parser.parse_args(arguments)
    try:
        write_release_manifest(Path(options.root), Path(options.output), commit=options.commit)
    except ReleaseManifestError as error:
        print(f"release manifest creation failed: {error}", file=sys.stderr)
        return 1
    except Exception:
        print("release manifest creation failed safely", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
