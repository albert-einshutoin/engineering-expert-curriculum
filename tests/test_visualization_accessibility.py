from __future__ import annotations

from pathlib import Path
import re
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CSS_PATH = REPOSITORY_ROOT / "static" / "visualizations.css"


class VisualizationAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.css = CSS_PATH.read_text(encoding="utf-8")

    def test_uses_shared_base_and_exact_closed_modifier_set(self) -> None:
        modifiers = set(
            re.findall(r"\.visualization--([a-z-]+)\b", self.css)
        )
        self.assertEqual(
            modifiers,
            {
                "flow",
                "hierarchy",
                "comparison",
                "state-loop",
                "causal",
                "timeline",
                "network",
                "memory",
                "matrix",
                "state-machine",
            },
        )
        self.assertRegex(self.css, r"(?s)\.visualization\s*\{[^}]+\}")

    def test_reflows_at_320px_and_removes_layout_connectors(self) -> None:
        mobile = re.search(
            r"@media\s*\(max-width:\s*20rem\)\s*\{(?P<body>.*?)(?=\n@media|\Z)",
            self.css,
            re.DOTALL,
        )
        self.assertIsNotNone(mobile)
        assert mobile is not None
        self.assertIn("grid-template-columns: 1fr", mobile.group("body"))
        self.assertRegex(
            mobile.group("body"),
            r"(?s)::(?:before|after).*?display:\s*none",
        )

    def test_supports_focus_state_and_logical_layout_without_color_only_state(self) -> None:
        self.assertIn(":focus-visible", self.css)
        self.assertRegex(self.css, r"outline:\s*(?!none)")
        self.assertRegex(
            self.css,
            r"\b(?:margin|padding|border)-(?:inline|block)(?:-(?:start|end))?:",
        )
        self.assertRegex(
            self.css,
            r"(?s)\[aria-current=[\"']step[\"']\].*?(?:border|outline|font-weight)",
        )

    def test_supports_forced_colors_reduced_motion_and_print(self) -> None:
        self.assertIn("@media (forced-colors: active)", self.css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.css)
        self.assertIn("@media print", self.css)
        self.assertNotIn("forced-color-adjust: none", self.css.casefold())
        self.assertRegex(
            self.css,
            r"(?s)@media print.*?\.visualization__simulation-oracle.*?display:\s*block",
        )
        self.assertRegex(
            self.css,
            r"(?s)@media print.*?\.visualization__controls.*?display:\s*none",
        )

    def test_generated_content_is_connector_only_and_never_essential_text(self) -> None:
        values = re.findall(r"\bcontent\s*:\s*([^;]+);", self.css)
        self.assertTrue(values)
        self.assertTrue(
            all(value.strip() in {'""', "''", "none"} for value in values),
            values,
        )

    def test_layout_uses_only_css_grid_flex_and_pseudo_connectors(self) -> None:
        self.assertRegex(self.css, r"display:\s*(?:grid|flex)")
        self.assertNotRegex(self.css, r"\b(?:svg|canvas)\b")


if __name__ == "__main__":
    unittest.main()
