from __future__ import annotations

from pathlib import Path
import json
import subprocess
import unittest

from curriculum_builder.javascript_safety import validate_javascript_bytes


ROOT = Path(__file__).resolve().parents[1]


class VisualizationRuntimeContractTests(unittest.TestCase):
    def test_actual_runtime_passes_dependency_free_dom_contract(self) -> None:
        completed = subprocess.run(
            [
                "node",
                str(ROOT / "tests" / "fixtures" / "visualization-runtime-dom-harness.js"),
                str(ROOT / "static" / "visualization.js"),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["modes"], [
            "scenario", "stepper", "playback", "hybrid", "explorer",
        ])
        self.assertTrue(report["faultMatrix"])
        self.assertEqual(report["listenerLeaks"], 0)
        self.assertEqual(report["timerLeaks"], 0)
        self.assertEqual(report["resetCycles"], 100)

    def test_runtime_is_one_safe_dependency_free_strict_classic_iife(self) -> None:
        source = (ROOT / "static" / "visualization.js").read_bytes()
        text = validate_javascript_bytes(source)
        self.assertTrue(text.startswith("(function () {\n  'use strict';"))
        self.assertIn("new Map", text)
        self.assertIn("new Set", text)
        self.assertNotIn("export ", text)

    def test_runtime_owns_transactional_restore_and_timer_cleanup(self) -> None:
        text = (ROOT / "static" / "visualization.js").read_text(encoding="utf-8")
        for marker in (
            "snapshot", "restore", "clearTimeout", "prefers-reduced-motion",
            "pagehide", "textContent", "aria-current", "aria-pressed",
            "is-enhanced", "is-active", "is-complete", "has-runtime-error",
        ):
            self.assertIn(marker, text)


if __name__ == "__main__":
    unittest.main()
