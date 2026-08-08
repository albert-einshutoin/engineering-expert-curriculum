from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

from tools.run_browser_contract import (
    browser_evidence_inventory,
    browser_run_plan,
    interactive_page_url,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = REPOSITORY_ROOT / "static"


class InteractivePageRuntimeTests(unittest.TestCase):
    def test_map3d_exposes_the_graph_meaning_and_keyboard_navigation(self) -> None:
        template = (REPOSITORY_ROOT / "templates" / "map3d.html").read_text(
            encoding="utf-8"
        )

        self.assertIn('id="graph-explanation"', template)
        self.assertIn('aria-describedby="graph-explanation"', template)
        self.assertIn('<label for="domain-select">', template)
        self.assertIn('<select id="domain-select">', template)
        self.assertIn('id="reset-focus"', template)
        self.assertIn('id="map-status" role="status" aria-live="polite"', template)
        self.assertIn('id="relationship-prerequisites"', template)
        self.assertIn('id="relationship-next"', template)

    def test_map3d_runtime_supports_direction_focus_and_reduced_motion(self) -> None:
        source = (STATIC_ROOT / "map3d.js").read_text(encoding="utf-8")

        self.assertIn("new THREE.ArrowHelper", source)
        self.assertIn("function focusDomain(domainId)", source)
        self.assertIn("prefers-reduced-motion", source)
        self.assertIn("domainSelect.addEventListener('change'", source)
        self.assertIn("resetFocus.addEventListener('click'", source)
        self.assertIn(
            "`domains/${String(domain.id).padStart(2,'0')}-${domain.slug}/index.html`",
            source,
        )

    def test_interactive_browser_urls_preserve_the_pages_project_prefix(self) -> None:
        self.assertEqual(
            interactive_page_url(49153, "map3d"),
            "http://127.0.0.1:49153/engineering-expert-curriculum/map3d.html",
        )

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

    def test_daily_selection_uses_local_dates_and_fresh_first_ordering(self) -> None:
        source = (STATIC_ROOT / "daily.js").read_text(encoding="utf-8")
        self.assertNotIn("toISOString().slice(0, 10)", source)
        for accessor in ("getFullYear()", "getMonth()", "getDate()"):
            self.assertIn(accessor, source)
        self.assertIn(
            "[...orderedFresh, ...orderedPreviouslyServed].slice(0, count)",
            source,
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
