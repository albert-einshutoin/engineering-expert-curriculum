from __future__ import annotations

from pathlib import Path
import json
import subprocess
import unittest

from curriculum_builder.javascript_safety import validate_javascript_bytes


ROOT = Path(__file__).resolve().parents[1]


class VisualizationRuntimeContractTests(unittest.TestCase):
    def _run_harness(self, harness: Path, *, timeout: float = 5.0):
        try:
            return subprocess.run(
                [
                "node",
                str(harness),
                str(ROOT / "static" / "visualization.js"),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as error:
            self.fail(f"visualization runtime harness timed out after {error.timeout}s")

    def test_actual_runtime_passes_dependency_free_dom_contract(self) -> None:
        completed = self._run_harness(
            ROOT / "tests" / "fixtures" / "visualization-runtime-dom-harness.js"
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
        self.assertTrue(report["loadAbsence"])

    def test_hanging_runtime_harness_fails_with_a_bounded_assertion(self) -> None:
        with self.assertRaisesRegex(AssertionError, "timed out"):
            self._run_harness(
                ROOT / "tests" / "fixtures" / "visualization-runtime-hang.js",
                timeout=0.1,
            )

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
