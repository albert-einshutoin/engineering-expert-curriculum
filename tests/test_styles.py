from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
STYLESHEET_PATH = REPOSITORY_ROOT / "static" / "styles.css"
TEMPLATE_ROOT = REPOSITORY_ROOT / "templates"

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")
_CUSTOM_PROPERTY = re.compile(
    r"(?m)^\s*(--[a-z0-9-]+)\s*:\s*([^;]+);"
)


def _relative_luminance(channel: int) -> float:
    normalized = channel / 255
    if normalized <= 0.04045:
        return normalized / 12.92
    return ((normalized + 0.055) / 1.055) ** 2.4


def _contrast_ratio(foreground: str, background: str) -> float:
    if _HEX_COLOR.fullmatch(foreground) is None:
        raise AssertionError(f"foreground must be a six-digit hex color: {foreground}")
    if _HEX_COLOR.fullmatch(background) is None:
        raise AssertionError(f"background must be a six-digit hex color: {background}")

    def luminance(color: str) -> float:
        channels = tuple(
            int(color[index : index + 2], 16) for index in (1, 3, 5)
        )
        return (
            0.2126 * _relative_luminance(channels[0])
            + 0.7152 * _relative_luminance(channels[1])
            + 0.0722 * _relative_luminance(channels[2])
        )

    lighter, darker = sorted(
        (luminance(foreground), luminance(background)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


class _TemplateContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.classes: set[str] = set()
        self.ids: set[str] = set()

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del tag
        for name, value in attrs:
            if name == "class" and value is not None:
                self.classes.update(value.split())
            elif name == "id" and value is not None:
                self.ids.add(value)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)


class StyleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw_css = STYLESHEET_PATH.read_bytes()
        cls.css = cls.raw_css.decode("utf-8")
        cls.properties = {
            name: value.strip()
            for name, value in _CUSTOM_PROPERTY.findall(cls.css)
        }

    def test_is_local_dependency_free_utf8_css(self) -> None:
        self.assertEqual(self.raw_css.decode("utf-8").encode("utf-8"), self.raw_css)
        self.assertNotIn("\x00", self.css)
        self.assertFalse(
            any(
                ord(character) < 0x20 and character not in "\n\r\t"
                for character in self.css
            )
        )
        self.assertNotRegex(self.css, r"(?i)@import\b")
        self.assertNotRegex(self.css, r"(?i)\burl\s*\(")
        self.assertNotRegex(self.css, r"(?i)https?://|javascript:")
        self.assertLess(len(self.raw_css), 32_768)

    def test_has_balanced_comments_and_braces(self) -> None:
        self.assertEqual(self.css.count("/*"), self.css.count("*/"))
        without_comments = re.sub(r"/\*.*?\*/", "", self.css, flags=re.DOTALL)
        self.assertNotIn("/*", without_comments)
        self.assertNotIn("*/", without_comments)
        depth = 0
        for character in without_comments:
            if character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                self.assertGreaterEqual(depth, 0)
        self.assertEqual(depth, 0)

    def test_defines_each_required_design_token_once(self) -> None:
        required_tokens = {
            "--color-paper",
            "--color-surface",
            "--color-ink",
            "--color-muted",
            "--color-border",
            "--color-accent",
            "--color-warm",
            "--color-success",
            "--color-focus",
            "--space-1",
            "--space-2",
            "--space-3",
            "--space-4",
            "--space-5",
            "--measure-reading",
            "--measure-wide",
            "--focus-ring",
        }
        self.assertTrue(required_tokens <= self.properties.keys())
        for token in required_tokens:
            self.assertEqual(
                len(re.findall(rf"(?m)^\s*{re.escape(token)}\s*:", self.css)),
                1,
                token,
            )
        self.assertEqual(self.properties["--measure-reading"], "70ch")

    def test_uses_local_japanese_and_latin_system_font_stacks(self) -> None:
        for font in (
            "ui-sans-serif",
            "system-ui",
            '"Hiragino Kaku Gothic ProN"',
            '"Yu Gothic"',
            "sans-serif",
            "ui-serif",
            '"Hiragino Mincho ProN"',
            '"Yu Mincho"',
            "serif",
            "ui-monospace",
            "monospace",
        ):
            self.assertIn(font, self.css)
        self.assertNotRegex(self.css, r"(?i)@font-face\b")

    def test_primary_colors_meet_wcag_aa_on_their_surfaces(self) -> None:
        pairs = {
            "ink on paper": ("--color-ink", "--color-paper", 4.5),
            "muted on paper": ("--color-muted", "--color-paper", 4.5),
            "link on paper": ("--color-accent", "--color-paper", 4.5),
            "ink on surface": ("--color-ink", "--color-surface", 4.5),
            "muted on surface": ("--color-muted", "--color-surface", 4.5),
            "focus on paper": ("--color-focus", "--color-paper", 3.0),
            "connector on paper": ("--color-warm", "--color-paper", 3.0),
        }
        for label, (foreground, background, minimum) in pairs.items():
            with self.subTest(label=label):
                ratio = _contrast_ratio(
                    self.properties[foreground],
                    self.properties[background],
                )
                self.assertGreaterEqual(ratio, minimum, f"{label}: {ratio:.2f}:1")

    def test_styles_semantic_textbook_elements(self) -> None:
        for selector in (
            "html",
            "body",
            "h1",
            "h2",
            "h3",
            "a",
            "nav",
            "main",
            "section",
            "article",
            "ul",
            "ol",
            "details",
            "summary",
            "blockquote",
            "figure",
            "figcaption",
            "table",
            "th",
            "td",
            "pre",
            "code",
            "kbd",
            "mark",
            "footer",
        ):
            self.assertRegex(
                self.css,
                rf"(?m)(?:^|,)\s*{re.escape(selector)}(?:\s|,|\{{|:)",
                selector,
            )

    def test_covers_every_class_and_id_in_current_templates(self) -> None:
        parser = _TemplateContractParser()
        for template_path in sorted(TEMPLATE_ROOT.glob("*.html")):
            parser.feed(template_path.read_text(encoding="utf-8"))
        parser.close()

        for class_name in sorted(parser.classes):
            self.assertRegex(
                self.css,
                rf"(?<![a-zA-Z0-9_-])\.{re.escape(class_name)}(?![a-zA-Z0-9_-])",
                class_name,
            )
        for identifier in sorted(parser.ids):
            self.assertRegex(
                self.css,
                rf"(?<![a-zA-Z0-9_-])#{re.escape(identifier)}(?![a-zA-Z0-9_-])",
                identifier,
            )

    def test_has_readable_editorial_layout_and_catalog_components(self) -> None:
        for selector in (
            ".site-header",
            ".site-header nav",
            ".brand",
            ".hero",
            ".eyebrow",
            ".reading",
            ".catalog-grid",
            ".catalog-card",
            ".catalog-card__title",
            ".catalog-card__list",
            ".prerequisite-text",
            "footer",
        ):
            self.assertIn(selector, self.css)
        self.assertIn("max-inline-size: var(--measure-reading)", self.css)
        self.assertIn("overflow-wrap: anywhere", self.css)
        self.assertRegex(self.css, r"font-size:\s*clamp\(")
        self.assertRegex(self.css, r"padding(?:-block|-inline)?:\s*clamp\(")

    def test_learning_path_is_a_four_stage_css_graph(self) -> None:
        self.assertIn(".learning-path", self.css)
        self.assertRegex(
            self.css,
            r"\.learning-path\s*\{[^}]*display:\s*grid",
        )
        self.assertRegex(
            self.css,
            r"grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)",
        )
        self.assertIn("counter-reset: learning-stage", self.css)
        self.assertIn(".learning-stage::before", self.css)
        self.assertIn("counter-increment: learning-stage", self.css)
        self.assertIn('content: counter(learning-stage)', self.css)
        self.assertIn(".learning-stage:not(:last-child)::after", self.css)
        self.assertIn("pointer-events: none", self.css)
        self.assertRegex(
            self.css,
            r"\.learning-stage:not\(:last-child\)::after\s*\{[^}]*"
            r"border(?:-block-start|-top):",
        )
        self.assertIn("linear-gradient(", self.css)
        self.assertNotRegex(self.css, r"(?i)@keyframes\b|animation\s*:|transition\s*:")

    def test_mobile_layout_is_single_column_and_hides_graph_connector(self) -> None:
        self.assertIn("@media (max-width: 48rem)", self.css)
        mobile = self.css.split("@media (max-width: 48rem)", 1)[1]
        self.assertRegex(
            mobile,
            r"\.learning-path\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)",
        )
        self.assertRegex(
            mobile,
            r"\.learning-stage:not\(:last-child\)::after\s*\{[^}]*display:\s*none",
        )
        self.assertRegex(
            self.css,
            r"\.catalog-grid\s*\{[^}]*"
            r"grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(min\(100%,",
        )
        self.assertIn("min-inline-size: 0", self.css)

    def test_focus_target_and_skip_link_are_visible_without_color_alone(self) -> None:
        self.assertIn(":focus-visible", self.css)
        self.assertIn(":target", self.css)
        self.assertIn(".skip-link:focus", self.css)
        self.assertIn("outline: var(--focus-ring)", self.css)
        self.assertIn("text-decoration-line: underline", self.css)
        self.assertIn("min-block-size: 2.75rem", self.css)
        self.assertIn("border", self.css)

    def test_supports_forced_colors_and_reduced_motion_preferences(self) -> None:
        self.assertIn("@media (forced-colors: active)", self.css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.css)
        forced_colors = self.css.split("@media (forced-colors: active)", 1)[1]
        self.assertIn("CanvasText", forced_colors)
        self.assertIn("LinkText", forced_colors)
        self.assertNotIn("!important", self.css)

    def test_code_and_tables_handle_narrow_viewports(self) -> None:
        self.assertRegex(
            self.css,
            r"(?:pre|table)[^{]*\{[^}]*overflow",
        )
        self.assertIn("overflow-x: auto", self.css)
        self.assertIn("max-inline-size: 100%", self.css)
        self.assertIn("word-break: break-word", self.css)

    def test_print_keeps_reading_order_and_expands_https_urls(self) -> None:
        self.assertIn("@media print", self.css)
        print_rules = self.css.split("@media print", 1)[1]
        self.assertIn('a[href^="https://"]::after', print_rules)
        self.assertIn('content: " (" attr(href) ")"', print_rules)
        self.assertIn("break-inside: avoid", print_rules)
        self.assertRegex(
            print_rules,
            r"\.learning-path\s*\{[^}]*grid-template-columns:\s*1fr",
        )
        self.assertIn(".prerequisite-text", print_rules)

    def test_uses_logical_properties_for_core_layout(self) -> None:
        for property_name in (
            "inline-size",
            "max-inline-size",
            "min-inline-size",
            "block-size",
            "margin-inline",
            "padding-inline",
            "padding-block",
            "border-block",
            "inset-inline",
        ):
            self.assertIn(property_name, self.css)


if __name__ == "__main__":
    unittest.main()
