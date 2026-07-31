#!/usr/bin/env python3
"""Build the complete static curriculum from any working directory."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from curriculum_builder.build import build_site  # noqa: E402


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="repository root containing content, templates, and static",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="output directory (defaults to ROOT/site)",
    )
    options = parser.parse_args(arguments)
    root = options.root
    if not root.is_absolute():
        root = Path.cwd() / root
    output = options.output if options.output is not None else root / "site"
    if not output.is_absolute():
        output = root / output
    build_site(
        root / "content",
        root / "templates",
        root / "static",
        output,
        require_complete_curriculum=True,
    )
    print(f"built {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
