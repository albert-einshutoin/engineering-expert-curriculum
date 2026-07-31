#!/usr/bin/env python3
"""Regenerate or verify the deterministic curriculum-map data block."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from curriculum_builder.curriculum_map import (  # noqa: E402
    render_generated_curriculum_map,
    replace_generated_curriculum_map,
)


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the checked-in generated block is stale",
    )
    options = parser.parse_args(arguments)
    target = REPOSITORY_ROOT / "docs/curriculum-map.md"
    before = target.read_text(encoding="utf-8")
    after = replace_generated_curriculum_map(
        before,
        render_generated_curriculum_map(REPOSITORY_ROOT),
    )
    if options.check:
        if before != after:
            print("docs/curriculum-map.md generated block is stale", file=sys.stderr)
            return 1
        print("docs/curriculum-map.md generated block is current")
        return 0
    if before != after:
        target.write_text(after, encoding="utf-8")
        print("updated docs/curriculum-map.md")
    else:
        print("docs/curriculum-map.md is already current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
