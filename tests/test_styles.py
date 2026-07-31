from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
import unittest

from curriculum_builder.css_safety import (
    MAX_STYLESHEET_BYTES,
    validate_stylesheet_bytes,
)
from curriculum_builder.errors import CurriculumValidationError


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
STYLESHEET_PATH = REPOSITORY_ROOT / "static" / "styles.css"
TEMPLATE_ROOT = REPOSITORY_ROOT / "templates"
FOUNDATION_PLAN_PATH = (
    REPOSITORY_ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-07-30-static-curriculum-foundation.md"
)

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")
_CUSTOM_PROPERTY = re.compile(
    r"(?m)^\s*(--[a-z0-9-]+)\s*:\s*([^;]+);"
)


def _consume_css_escape(css: str, index: int) -> int:
    next_index = index + 1
    if next_index >= len(css):
        raise AssertionError("CSS structure has a trailing escape")
    if css[next_index] in "\n\r\f":
        if (
            css[next_index] == "\r"
            and next_index + 1 < len(css)
            and css[next_index + 1] == "\n"
        ):
            return next_index + 2
        return next_index + 1
    if css[next_index] in "0123456789abcdefABCDEF":
        end = next_index
        while (
            end < len(css)
            and end - next_index < 6
            and css[end] in "0123456789abcdefABCDEF"
        ):
            end += 1
        if end < len(css) and css[end].isspace():
            end += 1
        return end
    return next_index + 1


def _scan_css_structure(
    css: str,
) -> tuple[dict[int, int], tuple[bool, ...]]:
    pairs: dict[int, int] = {}
    openings: list[int] = []
    data_positions = [False] * len(css)
    state = "data"
    index = 0
    while index < len(css):
        character = css[index]
        if state == "comment":
            if css.startswith("*/", index):
                state = "data"
                index += 2
            else:
                index += 1
            continue
        if state in {"single-quoted", "double-quoted"}:
            expected_quote = "'" if state == "single-quoted" else '"'
            if character == "\\":
                index = _consume_css_escape(css, index)
            elif character == expected_quote:
                state = "data"
                index += 1
            elif character in "\n\r\f":
                raise AssertionError("CSS structure has an unclosed string")
            else:
                index += 1
            continue

        if css.startswith("/*", index):
            state = "comment"
            index += 2
            continue
        if css.startswith("*/", index):
            raise AssertionError("CSS structure has a stray comment close")
        if character == "\\":
            index = _consume_css_escape(css, index)
            continue
        if character == "'":
            state = "single-quoted"
            index += 1
            continue
        if character == '"':
            state = "double-quoted"
            index += 1
            continue

        data_positions[index] = True
        if character == "{":
            openings.append(index)
        elif character == "}":
            if not openings:
                raise AssertionError("CSS structure has a stray block close")
            pairs[openings.pop()] = index
        index += 1

    if state == "comment":
        raise AssertionError("CSS structure has an unclosed comment")
    if state != "data":
        raise AssertionError("CSS structure has an unclosed string")
    if openings:
        raise AssertionError("CSS structure has an unclosed block")
    return pairs, tuple(data_positions)


def _top_level_css_blocks(css: str) -> tuple[tuple[str, str], ...]:
    pairs, data_positions = _scan_css_structure(css)
    blocks: list[tuple[str, str]] = []
    cursor = 0
    for opening in sorted(pairs):
        if opening < cursor:
            continue
        closing = pairs[opening]
        raw_prelude = "".join(
            css[position] if data_positions[position] else " "
            for position in range(cursor, opening)
        )
        prelude = raw_prelude.strip()
        if not prelude:
            raise AssertionError("CSS structure has a block without a prelude")
        blocks.append((prelude, css[opening + 1 : closing]))
        cursor = closing + 1
    trailing_data = "".join(
        css[position] if data_positions[position] else " "
        for position in range(cursor, len(css))
    )
    if trailing_data.strip():
        raise AssertionError("CSS structure has trailing data outside a block")
    return tuple(blocks)


def _normalize_css_prelude(prelude: str) -> str:
    return " ".join(prelude.split())


def _css_block(css: str, prelude: str) -> str:
    expected = _normalize_css_prelude(prelude)
    matches = tuple(
        body
        for candidate, body in _top_level_css_blocks(css)
        if _normalize_css_prelude(candidate) == expected
    )
    if len(matches) != 1:
        raise AssertionError(
            f"CSS structure expected one {prelude!r} block, found {len(matches)}"
        )
    return matches[0]


def _assert_connector_hidden_in_media(css: str, media_prelude: str) -> None:
    try:
        media_body = _css_block(css, media_prelude)
        connector = _css_block(
            media_body,
            ".learning-stage:not(:last-child)::after",
        )
    except AssertionError:
        raise AssertionError("connector must be hidden in its media block") from None
    if re.search(r"(?m)^\s*display\s*:\s*none\s*;", connector) is None:
        raise AssertionError("connector must be hidden in its media block")


def _bounded_plan_section(text: str, start: str, end: str) -> str:
    if text.count(start) != 1 or text.count(end) != 1:
        raise AssertionError(
            f"plan section markers must occur once: {start!r}, {end!r}"
        )
    before, remainder = text.split(start, 1)
    del before
    section, after = remainder.split(end, 1)
    del after
    if not section.strip():
        raise AssertionError(f"plan section is empty: {start!r}")
    return section


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
        cls.css = validate_stylesheet_bytes(cls.raw_css)
        cls.properties = {
            name: value.strip()
            for name, value in _CUSTOM_PROPERTY.findall(cls.css)
        }

    def test_is_local_dependency_free_utf8_css(self) -> None:
        # The print-only href prefix selector intentionally contains "https://";
        # the production validator rejects resource-bearing syntax instead of
        # banning inert HTTPS text.
        self.assertIn('a[href^="https://"]::after', self.css)
        self.assertLess(len(self.raw_css), 32_768)
        self.assertEqual(
            validate_stylesheet_bytes(self.raw_css),
            self.css,
        )

    def test_production_validator_rejects_resource_and_encoding_mutations(
        self,
    ) -> None:
        malicious_sources = (
            b'@import "https://evil.example/a.css";',
            b'a { background: url("https://evil.example/a.png"); }',
            b"@font-face { font-family: evil; src: local(evil); }",
            b'a { color: javascript:alert(1); }',
            b'a { background: image-set("https://evil.example/a.png" 1x); }',
            b'a { background: -webkit-image-set("evil.png" 1x); }',
            b'a { background: image("evil.png"); }',
            b"a { background: src(var(--remote)); }",
            b'/* @import "https://evil.example/a.css"; */',
            b'a::after { content: "url(https://evil.example/a.png)"; }',
            b'a { background: u/**/rl("https://evil.example/a.png"); }',
            b'@im/**/port "https://evil.example/a.css";',
            b'a { color: java/**/script:alert(1); }',
            b'a { background: ima/**/ge("evil.png"); }',
            rb'@\69mport "https://evil.example/a.css";',
            rb'a { background: u\72l("https://evil.example/a.png"); }',
            rb'a { background: i\6d age-set("evil.png" 1x); }',
            b"a { color: red; }\x00",
            b"a { color: red; }\x01",
            b"a { color: red; }\xe2\x80\xae",
            b"\xff",
        )
        for malicious_source in malicious_sources:
            with self.subTest(source=malicious_source):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    "styles.css",
                ):
                    validate_stylesheet_bytes(malicious_source)

        class BytesSubclass(bytes):
            pass

        for invalid_type in (
            bytearray(b"a {}"),
            memoryview(b"a {}"),
            BytesSubclass(b"a {}"),
        ):
            with self.subTest(invalid_type=type(invalid_type).__name__):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    "exact bytes",
                ):
                    validate_stylesheet_bytes(invalid_type)  # type: ignore[arg-type]

        with self.assertRaisesRegex(
            CurriculumValidationError,
            "maximum byte count",
        ):
            validate_stylesheet_bytes(
                b"a" * (MAX_STYLESHEET_BYTES + 1)
            )

    def test_has_balanced_comments_and_braces(self) -> None:
        _scan_css_structure(self.css)
        for malformed in (
            "/* unclosed",
            '.a { content: "unclosed; }',
            "}",
            '.a { content: "}";',
        ):
            with self.subTest(malformed=malformed):
                with self.assertRaisesRegex(AssertionError, "CSS structure"):
                    _scan_css_structure(malformed)
        # Structural scanning recognizes escaped string characters even though
        # the production local-only policy rejects every backslash.
        _scan_css_structure(r'.a { content: "\}"; }')

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
            "--color-warning",
            "--color-focus",
            "--color-print-ink",
            "--color-print-muted",
            "--space-1",
            "--space-2",
            "--space-3",
            "--space-4",
            "--space-5",
            "--measure-reading",
            "--measure-wide",
            "--border-strong",
            "--shadow-card",
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
            "border on paper": ("--color-border", "--color-paper", 3.0),
            "success on paper": ("--color-success", "--color-paper", 4.5),
            "warning on paper": ("--color-warning", "--color-paper", 4.5),
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
            "h4",
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
        h4_body = _css_block(self.css, "h4")
        self.assertRegex(
            h4_body,
            r"(?m)^\s*margin-block:\s*1\.25em\s+0\.45em\s*;",
        )
        self.assertRegex(
            h4_body,
            r"(?m)^\s*font-size:\s*clamp\("
            r"1\.05rem,\s*1rem\s*\+\s*0\.25vw,\s*1\.25rem\)\s*;",
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
            ".prerequisite-text > strong",
            "footer",
        ):
            self.assertIn(selector, self.css)
        self.assertNotRegex(
            self.css,
            r"\.prerequisite-text::before\s*\{[^}]*content:\s*[\"']前提",
        )
        full_plan = FOUNDATION_PLAN_PATH.read_text(encoding="utf-8")
        task_9_plan = _bounded_plan_section(
            full_plan,
            "### Task 9:",
            "### Task 10:",
        )
        step_1_test_contract = _bounded_plan_section(
            task_9_plan,
            "- [ ] **Step 1:",
            "- [ ] **Step 2:",
        )
        step_3_implementation = _bounded_plan_section(
            task_9_plan,
            "- [ ] **Step 3:",
            "- [ ] **Step 4:",
        )
        self.assertIn(
            '<p class="prerequisite-text"><strong>前提:</strong> ',
            step_3_implementation,
        )
        for class_name in (
            "catalog-card",
            "catalog-card__title",
            "catalog-card__list",
        ):
            self.assertIn(f'class="{class_name}"', step_3_implementation)
        for counted_markup in (
            '<section class="catalog-card">',
            '<h2 class="catalog-card__title">',
            '<ol class="catalog-card__list">',
        ):
            self.assertRegex(
                step_1_test_contract,
                rf"catalog_html\.count\({re.escape(repr(counted_markup))}\)"
                rf"\s*,\s*38",
            )
        self.assertRegex(
            step_1_test_contract,
            r"catalog_html\.count\([\"']<li id=[\"']\)\s*,\s*1_140",
        )
        self.assertIn("roadmap_html", step_1_test_contract)
        self.assertIn("<strong>前提:</strong>", step_1_test_contract)
        for title, prerequisite in (
            ("Think", "なし"),
            ("Build", "Think"),
            ("Run", "Build"),
            ("Lead", "Run"),
        ):
            self.assertIn(
                f'("{title}", "{prerequisite}"),',
                step_1_test_contract,
            )
        self.assertIn("title_by_id", step_3_implementation)
        self.assertIn('node["prerequisites"]', step_3_implementation)
        self.assertIn(
            '<li class="learning-stage">',
            step_3_implementation,
        )
        self.assertIn(
            '<p class="prerequisite-text"><strong>前提:</strong> ',
            step_3_implementation,
        )
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
        connector_body = _css_block(
            self.css,
            ".learning-stage:not(:last-child)::after",
        )
        self.assertRegex(connector_body, r'content:\s*""')
        self.assertRegex(connector_body, r"pointer-events:\s*none")
        self.assertRegex(connector_body, r"clip-path:\s*polygon\(")
        self.assertRegex(connector_body, r"background:\s*var\(--color-warm\)")
        forced_colors = _css_block(
            self.css,
            "@media (forced-colors: active)",
        )
        forced_connector = _css_block(
            forced_colors,
            ".learning-stage:not(:last-child)::after",
        )
        self.assertRegex(forced_connector, r"background:\s*CanvasText")
        self.assertNotRegex(self.css, r"(?i)@keyframes\b|animation\s*:|transition\s*:")

    def test_quantitative_chart_has_color_and_monochrome_scale(
        self,
    ) -> None:
        chart = _css_block(self.css, ".quantitative-chart-artifact")
        self.assertRegex(chart, r"display:\s*grid")
        self.assertRegex(chart, r"max-inline-size:\s*var\(--measure-reading\)")
        scale = _css_block(self.css, ".chart-scale")
        self.assertRegex(scale, r"display:\s*flex")
        self.assertRegex(scale, r"justify-content:\s*space-between")
        for percentage in (40, 60, 100):
            body = _css_block(self.css, f".chart-bar--{percentage}")
            self.assertRegex(body, rf"inline-size:\s*{percentage}%")
        color = _css_block(
            self.css,
            ".chart-display--color .chart-bar",
        )
        self.assertRegex(color, r"background:\s*#245d63")
        self.assertRegex(color, r"color:\s*#ffffff")
        monochrome = _css_block(
            self.css,
            ".chart-display--monochrome .chart-bar",
        )
        self.assertIn("repeating-linear-gradient(", monochrome)
        self.assertRegex(monochrome, r"border-style:\s*double")
        self.assertRegex(monochrome, r"color:\s*CanvasText")
        print_rules = _css_block(self.css, "@media print")
        print_bar = _css_block(
            print_rules,
            ".chart-display--color .chart-bar",
        )
        self.assertRegex(print_bar, r"background:\s*transparent")
        self.assertRegex(print_bar, r"border:\s*2px solid currentColor")

    def test_mobile_layout_is_single_column_and_hides_graph_connector(self) -> None:
        mobile = _css_block(self.css, "@media (max-width: 48rem)")
        self.assertRegex(
            mobile,
            r"\.learning-path\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)",
        )
        _assert_connector_hidden_in_media(self.css, "@media (max-width: 48rem)")
        mobile_without_hidden_connector = self.css.replace(
            """  .learning-stage:not(:last-child)::after {
    display: none;
  }
""",
            "",
            1,
        )
        with self.assertRaisesRegex(AssertionError, "connector must be hidden"):
            _assert_connector_hidden_in_media(
                mobile_without_hidden_connector,
                "@media (max-width: 48rem)",
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
        brand_body = _css_block(self.css, ".brand")
        self.assertRegex(brand_body, r"display:\s*inline-flex")
        self.assertRegex(brand_body, r"align-items:\s*center")
        self.assertRegex(brand_body, r"min-block-size:\s*2\.75rem")

    def test_supports_forced_colors_and_reduced_motion_preferences(self) -> None:
        self.assertIn("@media (forced-colors: active)", self.css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.css)
        forced_colors = _css_block(
            self.css,
            "@media (forced-colors: active)",
        )
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

    def test_lesson_components_reflow_at_320px_and_keep_visible_evidence(
        self,
    ) -> None:
        for selector in (
            ".lesson",
            ".lede",
            ".lesson-meta",
            ".lessons-index",
            ".lesson-index-list",
            ".lesson-index-item",
            ".capability-list",
            ".capability-level",
            ".evidence-label",
            ".artifact-label",
            ".review-list",
            ".rubric-table",
            ".source-list",
        ):
            self.assertIn(selector, self.css)
        narrow = _css_block(self.css, "@media (max-width: 22rem)")
        lesson_meta = _css_block(narrow, ".lesson-meta")
        self.assertRegex(
            lesson_meta,
            r"grid-template-columns:\s*minmax\(0,\s*1fr\)",
        )
        forced = _css_block(self.css, "@media (forced-colors: active)")
        for selector in (
            ".lesson-meta",
            ".lesson-index-item",
            ".capability-level",
            ".review-list > li",
            ".evidence-label",
        ):
            self.assertIn(selector, forced)

    def test_print_keeps_reading_order_and_expands_https_urls(self) -> None:
        print_rules = _css_block(self.css, "@media print")
        self.assertIn('a[href^="https://"]::after', print_rules)
        self.assertIn('content: " (" attr(href) ")"', print_rules)
        self.assertIn("break-inside: avoid", print_rules)
        self.assertRegex(
            print_rules,
            r"\.learning-path\s*\{[^}]*grid-template-columns:\s*1fr",
        )
        self.assertIn(".prerequisite-text", print_rules)
        print_blocks = _top_level_css_blocks(print_rules)
        break_inside_avoid = {
            selector
            for prelude, body in print_blocks
            if re.search(r"break-inside\s*:\s*avoid", body)
            for selector in (part.strip() for part in prelude.split(","))
        }
        self.assertTrue(
            {"li", "tr", ".learning-stage", ".prerequisite-text"}
            <= break_inside_avoid
        )
        self.assertTrue(
            {
                "article",
                "section",
                ".lesson",
                "table",
                ".catalog-card",
                "details",
                "pre",
                "blockquote",
            }.isdisjoint(break_inside_avoid)
        )
        break_after_avoid = {
            selector
            for prelude, body in print_blocks
            if re.search(r"break-after\s*:\s*avoid", body)
            for selector in (part.strip() for part in prelude.split(","))
        }
        self.assertTrue(
            {"h1", "h2", "h3", "h4", ".catalog-card__title"}
            <= break_after_avoid
        )
        table_body = _css_block(print_rules, "table")
        self.assertRegex(table_body, r"display:\s*table")
        self.assertRegex(table_body, r"overflow:\s*visible")
        thead_body = _css_block(print_rules, "thead")
        self.assertRegex(thead_body, r"display:\s*table-header-group")

    def test_print_preserves_complete_preformatted_text(self) -> None:
        print_rules = _css_block(self.css, "@media print")
        pre_rules = _css_block(print_rules, "pre")

        self.assertRegex(pre_rules, r"white-space:\s*pre-wrap")
        self.assertRegex(pre_rules, r"overflow-wrap:\s*anywhere")
        self.assertRegex(pre_rules, r"overflow(?:-x)?:\s*visible")
        self.assertNotRegex(pre_rules, r"white-space:\s*pre(?:;|$)")

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
