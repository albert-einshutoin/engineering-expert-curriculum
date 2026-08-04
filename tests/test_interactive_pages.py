from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

from tools.run_browser_contract import (
    browser_evidence_inventory,
    browser_run_plan,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = REPOSITORY_ROOT / "static"


class InteractivePageRuntimeTests(unittest.TestCase):
    def test_three_addons_resolve_the_pinned_offline_module_relatively(self) -> None:
        for name in ("OrbitControls.js", "CSS2DRenderer.js"):
            source = (STATIC_ROOT / "three" / name).read_text(encoding="utf-8")
            self.assertIn("from '../three.module.js';", source)
            self.assertNotRegex(source, r"from\s+['\"]three['\"]")

    def test_runtime_data_module_is_an_exact_projection_of_the_pinned_source(self) -> None:
        source = (STATIC_ROOT / "curriculum-data.js").read_text(encoding="utf-8")
        prefix = "export const CURRICULUM = "
        self.assertTrue(source.startswith(prefix))
        self.assertTrue(source.endswith(";\n"))
        actual = json.loads(source[len(prefix) : -2])
        expected_bytes = (REPOSITORY_ROOT / "data" / "curriculum.json").read_bytes()
        expected = json.loads(expected_bytes)
        self.assertEqual(actual, expected)

        canonical = json.loads(
            (REPOSITORY_ROOT / "content" / "catalog.json").read_bytes()
        )
        self.assertEqual(
            canonical["sourceSha256"],
            hashlib.sha256(expected_bytes).hexdigest(),
        )

    def test_each_interactive_runtime_imports_the_canonical_data_module(self) -> None:
        for name in ("map3d.js", "progress.js", "daily.js"):
            source = (STATIC_ROOT / name).read_text(encoding="utf-8")
            self.assertIn(
                "import { CURRICULUM } from './curriculum-data.js';",
                source,
            )
            self.assertNotIn("window.CURRICULUM", source)
        self.assertNotRegex(
            (STATIC_ROOT / "progress.js").read_text(encoding="utf-8"),
            r"(?m)^if\s*\([^\n]+\)\s*return\s*;",
        )

    def test_browser_plan_executes_each_interactive_page_smoke(self) -> None:
        inventory = browser_evidence_inventory(
            (REPOSITORY_ROOT / "content/visualization-catalog.json").read_bytes()
        )
        plan = browser_run_plan(inventory, include_safari=False)
        interactive = [
            run for run in plan if str(run["label"]).startswith("interactive-")
        ]
        self.assertEqual(
            interactive,
            [
                {
                    "browser": "chromium",
                    "label": "interactive-map3d",
                    "profile": "desktop",
                    "requestedState": None,
                },
                {
                    "browser": "chromium",
                    "label": "interactive-progress",
                    "profile": "desktop",
                    "requestedState": None,
                },
                {
                    "browser": "chromium",
                    "label": "interactive-daily",
                    "profile": "desktop",
                    "requestedState": None,
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
