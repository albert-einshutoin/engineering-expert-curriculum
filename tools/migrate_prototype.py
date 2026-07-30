"""Preserve the legacy generated prototype with checksum verification."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from typing import Iterable


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


def _validate_allowed_path(root: Path, allowed_path: str) -> Path:
    candidate = Path(allowed_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"allowlisted path must be relative: {allowed_path}")

    resolved_root = root.resolve()
    resolved_candidate = (root / candidate).resolve(strict=False)
    if resolved_candidate != resolved_root and resolved_root not in resolved_candidate.parents:
        raise ValueError(f"allowlisted path escapes root: {allowed_path}")
    return root / candidate


def _iter_regular_files(root: Path, paths: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    for allowed_path in paths:
        candidate = _validate_allowed_path(root, allowed_path)
        if not candidate.exists() and not candidate.is_symlink():
            continue
        if candidate.is_symlink():
            raise ValueError(f"symbolic links are not supported: {candidate}")
        if candidate.is_file():
            files.append(candidate)
            continue
        if not candidate.is_dir():
            continue
        for descendant in candidate.rglob("*"):
            if descendant.is_symlink():
                raise ValueError(f"symbolic links are not supported: {descendant}")
            if descendant.is_file():
                files.append(descendant)
    return files


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    # Stream file data so arbitrarily large generated assets are never loaded at once.
    with path.open("rb") as file:
        while chunk := file.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _checksums(root: Path, paths: Iterable[str]) -> dict[str, str]:
    """Return SHA-256 values for regular files below existing allowlisted paths."""
    files = _iter_regular_files(root, paths)
    return {
        file.relative_to(root).as_posix(): _sha256(file)
        for file in sorted(files, key=lambda item: item.relative_to(root).as_posix())
    }


def preserve_prototype(
    source: Path,
    archive: Path,
    allowed_paths: Iterable[str] = LEGACY_PATHS,
) -> dict[str, object]:
    """Move allowed legacy files to *archive* and write a verified manifest."""
    source = source.resolve()
    archive = archive.resolve(strict=False)
    allowed_paths = tuple(allowed_paths)

    if archive.exists() or archive.is_symlink():
        raise FileExistsError(f"archive already exists: {archive}")

    before = _checksums(source, allowed_paths)
    if not before:
        raise FileNotFoundError("no allowlisted prototype files found")

    archive.mkdir(parents=True)
    for allowed_path in allowed_paths:
        source_path = _validate_allowed_path(source, allowed_path)
        if not source_path.exists() and not source_path.is_symlink():
            continue
        destination = archive / allowed_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(destination))

    after = _checksums(archive, allowed_paths)
    if before != after:
        raise RuntimeError("prototype checksum verification failed")

    manifest: dict[str, object] = {
        "algorithm": "sha256",
        "fileCount": len(after),
        "byteCount": sum(
            (archive / relative_path).stat().st_size for relative_path in after
        ),
        "files": after,
    }
    # A manifest is evidence of a complete preservation, so only publish it after verification.
    (archive / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
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
