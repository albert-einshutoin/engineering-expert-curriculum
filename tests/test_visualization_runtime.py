from __future__ import annotations

from pathlib import Path
import json
import subprocess
from tempfile import TemporaryDirectory
import unittest

from curriculum_builder.build import build_site
from curriculum_builder.javascript_safety import validate_javascript_bytes


ROOT = Path(__file__).resolve().parents[1]


class VisualizationRuntimeContractTests(unittest.TestCase):
    def test_task9_build_has_exactly_five_simulation_script_pages(self) -> None:
        expected = {
            "core-02-algorithms-measurement",
            "core-03-architecture-memory-caches",
            "core-04-os-processes-concurrency",
            "core-05-networks-latency-failure",
            "core-07-api-contract-design",
        }
        with TemporaryDirectory(prefix=".task9-runtime-", dir=ROOT.parent) as temporary:
            output = Path(temporary) / "site"
            build_site(
                ROOT / "content", ROOT / "templates", ROOT / "static", output,
                require_complete_curriculum=True,
            )
            actual = {
                path.parent.name
                for path in (output / "lessons").glob("*/index.html")
                if b'<script src="../../static/visualization.js" defer></script>'
                in path.read_bytes()
            }

        self.assertEqual(actual, expected)

    def test_real_hybrid_lessons_render_reselect_next_and_reset_edges(self) -> None:
        expected_edges = {
            "core-03-architecture-memory-caches": (
                ("apply-large-random", "parameter-change", "tlb-lookup", "tlb-lookup"),
                ("next-large-random", "next", "tlb-lookup", "memory-return"),
                ("reset-memory-return", "reset", "memory-return", "tlb-lookup"),
            ),
            "core-05-networks-latency-failure": (
                ("apply-response", "parameter-change", "dns-lookup", "dns-lookup"),
                ("next-response", "next", "dns-lookup", "deadline-exceeded"),
                ("reset-response", "reset", "deadline-exceeded", "dns-lookup"),
            ),
        }
        with TemporaryDirectory(prefix=".task9-real-dom-", dir=ROOT.parent) as temporary:
            output = Path(temporary) / "site"
            build_site(
                ROOT / "content", ROOT / "templates", ROOT / "static", output,
                require_complete_curriculum=True,
            )
            for lesson_id, edges in expected_edges.items():
                generated = (
                    output / "lessons" / lesson_id / "index.html"
                ).read_text(encoding="utf-8")
                for transition_id, event, from_id, to_id in edges:
                    self.assertIn(
                        f'data-transition-id="{transition_id}" '
                        f'data-transition-event="{event}" '
                        f'data-from-state-id="{from_id}" '
                        f'data-to-state-id="{to_id}"',
                        generated,
                    )
                self.assertIn('data-action="apply"', generated)
                self.assertIn('data-action="next"', generated)
                self.assertIn('data-action="reset"', generated)

            core02 = (
                output / "lessons/core-02-algorithms-measurement/index.html"
            ).read_text(encoding="utf-8")
            for atom in (
                "n=1000: 線形1000・二分10・hash期待1",
                "n=10000: 線形10000・二分14・hash期待1",
                "n=100000: 線形100000・二分17・hash期待1",
                "median_ns/range_ns",
            ):
                self.assertIn(atom, core02)

            core04 = (
                output / "lessons/core-04-os-processes-concurrency/index.html"
            ).read_text(encoding="utf-8")
            self.assertLess(core04.index("A read"), core04.index("B read"))
            self.assertLess(core04.index("B read"), core04.index("A compute"))
            self.assertLess(core04.index("期待値x=8、actual x=9"), core04.index("期待値x=8、actual x=8"))

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
        self.assertTrue(report["hybridReselection"])
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
