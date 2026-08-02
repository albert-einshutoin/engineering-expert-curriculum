#!/usr/bin/env python3
"""Create the canonical release manifest for a generated site."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from tools.verify_release_manifest import (
    MANIFEST_NAME,
    ReleaseManifestError,
    parse_manifest_bytes,
    scan_release_files,
)


def create_manifest_bytes(root: Path, *, commit: str) -> bytes:
    files = scan_release_files(root)
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


def write_release_manifest(root: Path, output: Path, *, commit: str) -> None:
    if (
        not isinstance(root, Path)
        or not isinstance(output, Path)
        or output.parent != root
        or output.name != MANIFEST_NAME
    ):
        raise ReleaseManifestError("output must be the exact release-root manifest")
    if output.exists() and (
        output.is_symlink()
        or not output.is_file()
        or output.stat().st_nlink != 1
    ):
        raise ReleaseManifestError("existing manifest output is unsafe")
    raw = create_manifest_bytes(root, commit=commit)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".release-manifest-", dir=root)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, output)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


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
