"""Import the legacy prototype curriculum into its canonical catalog."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

# Allow the documented ``python tools/import_catalog.py`` invocation without installation.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from curriculum_builder.catalog import canonicalize
from curriculum_builder.errors import CurriculumValidationError


def _read_source(path: Path) -> object:
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise CurriculumValidationError(f"{path}: cannot read source: {error}") from error


def _write_atomic(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".catalog-", suffix=".tmp", delete=False
        ) as temporary:
            temporary_name = temporary.name
            json.dump(document, temporary, ensure_ascii=False, indent=2, sort_keys=False)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--generated-from", default="prototype-v1")
    arguments = parser.parse_args(argv)
    if arguments.input.resolve(strict=False) == arguments.output.resolve(strict=False):
        parser.error("--input and --output must be different paths")
    try:
        source = _read_source(arguments.input)
        if not isinstance(source, dict):
            raise CurriculumValidationError("source root must be an object")
        _write_atomic(arguments.output, canonicalize(source, arguments.generated_from))
    except (CurriculumValidationError, OSError) as error:
        print(f"import failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
