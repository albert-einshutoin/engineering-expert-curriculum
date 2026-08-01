from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
import unittest

from curriculum_builder.visualizations import (
    VisualizationType,
    render_visualization,
)
import tests.test_visualization_rendering as visualization_rendering_tests


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CSS_PATH = REPOSITORY_ROOT / "static" / "visualizations.css"

_SEMANTIC_CONTAINERS = {
    VisualizationType.FLOW: ("visualization__ordered-model",),
    VisualizationType.HIERARCHY: ("visualization__hierarchy",),
    VisualizationType.COMPARISON: ("visualization__table",),
    VisualizationType.STATE_LOOP: ("visualization__nodes",),
    VisualizationType.CAUSAL: ("visualization__causal-model",),
    VisualizationType.TIMELINE: ("visualization__timeline-phases",),
    VisualizationType.NETWORK: (
        "visualization__components",
        "visualization__nodes",
    ),
    VisualizationType.MEMORY: ("visualization__nodes",),
    VisualizationType.MATRIX: ("visualization__table",),
    VisualizationType.STATE_MACHINE: ("visualization__states",),
}

_MULTI_COLUMN_CONTAINERS = frozenset(
    (kind, container)
    for kind, containers in _SEMANTIC_CONTAINERS.items()
    if kind not in {
        VisualizationType.COMPARISON,
        VisualizationType.HIERARCHY,
        VisualizationType.MATRIX,
    }
    for container in containers
)


def _css_blocks(source: str) -> tuple[tuple[str, str, int], ...]:
    blocks: list[tuple[str, str, int]] = []
    depth = 0
    opening = -1
    prelude_start = 0
    for index, character in enumerate(source):
        if character == "{":
            if depth == 0:
                opening = index
            depth += 1
        elif character == "}":
            depth -= 1
            if depth < 0:
                raise AssertionError("CSS has an unmatched closing brace")
            if depth == 0:
                prelude = source[prelude_start:opening].strip()
                blocks.append((prelude, source[opening + 1:index], opening))
                prelude_start = index + 1
    if depth:
        raise AssertionError("CSS has an unmatched opening brace")
    return tuple(blocks)


def _selector_list(source: str) -> tuple[str, ...]:
    selectors: list[str] = []
    start = 0
    depth = 0
    for index, character in enumerate(source):
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        elif character == "," and depth == 0:
            selectors.append(" ".join(source[start:index].split()))
            start = index + 1
    selectors.append(" ".join(source[start:].split()))
    return tuple(selectors)


def _css_value_tokens(source: str) -> tuple[str, ...]:
    tokens: list[str] = []
    start = 0
    depth = 0
    for index, character in enumerate(source):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                raise AssertionError(
                    "CSS value has an unmatched closing parenthesis"
                )
        elif character.isspace() and depth == 0:
            if source[start:index].strip():
                tokens.append(source[start:index].strip())
            start = index + 1
    if source[start:].strip():
        tokens.append(source[start:].strip())
    if depth:
        raise AssertionError("CSS value has an unmatched opening parenthesis")
    return tuple(tokens)


def _rules(source: str) -> tuple[tuple[str, dict[str, str], int], ...]:
    rules: list[tuple[str, dict[str, str], int]] = []
    for prelude, body, position in _css_blocks(source):
        if prelude.startswith("@media"):
            for selector, nested_body, nested_position in _css_blocks(body):
                declarations = {
                    name.strip(): value.strip()
                    for declaration in nested_body.split(";")
                    if ":" in declaration
                    for name, value in (declaration.split(":", 1),)
                }
                for item in _selector_list(selector):
                    rules.append(
                        (item, declarations, position + nested_position)
                    )
        elif not prelude.startswith("@"):
            declarations = {
                name.strip(): value.strip()
                for declaration in body.split(";")
                if ":" in declaration
                for name, value in (declaration.split(":", 1),)
            }
            for item in _selector_list(prelude):
                rules.append((item, declarations, position))
    return tuple(rules)


def _specificity(selector: str) -> tuple[int, int, int]:
    ids = len(re.findall(r"#[a-zA-Z0-9_-]+", selector))
    classes = len(
        re.findall(
            r"\.[a-zA-Z0-9_-]+|\[[^]]+\]|:(?!:)[a-zA-Z-]+",
            selector,
        )
    )
    elements = len(
        re.findall(
            r"(?:^|[ >+~])(?:[a-zA-Z][a-zA-Z0-9-]*|\*)",
            selector,
        )
    )
    return ids, classes, elements


def _selector_classes(selector: str) -> frozenset[str]:
    return frozenset(re.findall(r"\.([a-zA-Z0-9_-]+)", selector))


def _media_rules(
    source: str,
    media_prelude: str,
) -> dict[str, dict[str, str]]:
    blocks = tuple(
        body
        for prelude, body, _ in _css_blocks(source)
        if " ".join(prelude.split()) == media_prelude
    )
    if len(blocks) != 1:
        raise AssertionError(f"expected one {media_prelude} block")
    return {
        selector: declarations
        for selector, declarations, _ in _rules(
            f"{media_prelude} {{{blocks[0]}}}"
        )
    }


class _HierarchyStructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, frozenset[str]]] = []
        self.list_depths: list[int] = []
        self.item_depths: list[int] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = dict(attrs)
        classes = frozenset((values.get("class") or "").split())
        in_hierarchy = any(
            "visualization__hierarchy" in ancestor_classes
            for _, ancestor_classes in self.stack
        )
        if in_hierarchy and tag in {"ul", "li"}:
            list_depth = sum(
                ancestor_tag == "ul"
                for ancestor_tag, _ in self.stack
            )
            if tag == "ul":
                self.list_depths.append(list_depth + 1)
            else:
                self.item_depths.append(list_depth)
        self.stack.append((tag, classes))

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1][0] != tag:
            raise AssertionError("rendered hierarchy has malformed nesting")
        self.stack.pop()


class _CausalStructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, frozenset[str]]] = []
        self.direct_children: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = dict(attrs)
        classes = frozenset((values.get("class") or "").split())
        if (
            self.stack
            and "visualization__causal-model" in self.stack[-1][1]
        ):
            self.direct_children.append(tag)
        self.stack.append((tag, classes))

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1][0] != tag:
            raise AssertionError("rendered causal model has malformed nesting")
        self.stack.pop()


class VisualizationAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.css = CSS_PATH.read_text(encoding="utf-8")
        cls.payloads = (
            visualization_rendering_tests.VisualizationRenderingTests().payloads()
        )

    def test_meaning_specific_selectors_match_real_renderer_containers(self) -> None:
        selectors = {selector for selector, _, _ in _rules(self.css)}
        for kind, containers in _SEMANTIC_CONTAINERS.items():
            with self.subTest(kind=kind.value):
                html = render_visualization(
                    "core-01-systems-tradeoffs",
                    visualization_rendering_tests._visual(
                        kind, self.payloads[kind]
                    ),
                ).value
                self.assertIn(f"visualization--{kind.value}", html)
                for container in containers:
                    self.assertIn(container, html)
                    self.assertIn(
                        f".visualization--{kind.value} .{container}",
                        selectors,
                    )

    def test_hierarchy_groups_real_nested_lists_with_non_color_boundaries(self) -> None:
        html = render_visualization(
            "core-01-systems-tradeoffs",
            visualization_rendering_tests._visual(
                VisualizationType.HIERARCHY,
                self.payloads[VisualizationType.HIERARCHY],
            ),
        ).value
        parser = _HierarchyStructureParser()
        parser.feed(html)
        parser.close()
        self.assertEqual(parser.stack, [])
        self.assertEqual(parser.list_depths, [1, 2])
        self.assertEqual(parser.item_depths, [1, 2])

        first_media = min(
            position
            for prelude, _, position in _css_blocks(self.css)
            if prelude.startswith("@media")
        )
        rules = {
            selector: declarations
            for selector, declarations, _ in _rules(self.css[:first_media])
        }
        container = ".visualization--hierarchy .visualization__hierarchy"
        root_list = f"{container} > ul"
        direct_item = f"{container} > ul > li"
        nested_list = f"{container} li > ul"
        nested_item = f"{container} li > ul > li"
        hierarchy_selectors = (
            container,
            root_list,
            direct_item,
            nested_list,
            nested_item,
        )
        for selector in hierarchy_selectors:
            self.assertIn(selector, rules)

        self.assertFalse(
            {
                "grid-template-columns",
                "grid-auto-flow",
                "grid-auto-columns",
            }
            & rules[container].keys()
        )
        self.assertEqual(rules[root_list].get("list-style-type"), "disc")
        self.assertEqual(rules[nested_list].get("list-style-type"), "circle")
        for selector in (root_list, direct_item, nested_list, nested_item):
            with self.subTest(selector=selector):
                declarations = rules[selector]
                border = declarations.get("border-inline-start", "")
                self.assertRegex(border, r"^[1-9][0-9]*px\s+solid\s+currentColor$")
                self.assertIn("padding-inline-start", declarations)
                self.assertTrue(
                    {"margin-block", "margin-block-start"}
                    & declarations.keys()
                )

        mobile = _media_rules(self.css, "@media (max-width: 20rem)")
        self.assertEqual(
            mobile[nested_list].get("margin-inline-start"),
            "0",
        )
        self.assertIn("padding-inline-start", mobile[nested_list])
        for selector in (direct_item, nested_item):
            self.assertIn("padding-inline-start", mobile[selector])

        forced_colors = _media_rules(
            self.css,
            "@media (forced-colors: active)",
        )
        for selector in (root_list, direct_item, nested_list, nested_item):
            self.assertEqual(
                forced_colors[selector].get("border-color"),
                "currentColor",
            )

        print_rules = _media_rules(self.css, "@media print")
        for selector in (direct_item, nested_item):
            self.assertEqual(
                print_rules[selector].get("break-inside"),
                "avoid",
            )

    def test_causal_pairs_fill_two_columns_by_row(self) -> None:
        html = render_visualization(
            "core-01-systems-tradeoffs",
            visualization_rendering_tests._visual(
                VisualizationType.CAUSAL,
                self.payloads[VisualizationType.CAUSAL],
            ),
        ).value
        parser = _CausalStructureParser()
        parser.feed(html)
        parser.close()
        self.assertEqual(parser.stack, [])
        self.assertEqual(parser.direct_children, ["dt", "dd"] * 4)

        first_media = min(
            position
            for prelude, _, position in _css_blocks(self.css)
            if prelude.startswith("@media")
        )
        desktop_rules = {
            selector: declarations
            for selector, declarations, _ in _rules(self.css[:first_media])
        }
        selector = ".visualization--causal .visualization__causal-model"
        self.assertIn(selector, desktop_rules)
        declarations = desktop_rules[selector]
        self.assertEqual(declarations.get("display"), "grid")
        self.assertEqual(
            _css_value_tokens(declarations.get("grid-template-columns", "")),
            ("max-content", "minmax(0, 1fr)"),
        )
        self.assertIn(declarations.get("grid-auto-flow"), {None, "row"})
        self.assertNotIn("grid-auto-columns", declarations)

        mobile = _media_rules(self.css, "@media (max-width: 20rem)")
        self.assertEqual(mobile[selector].get("grid-template-columns"), "1fr")
        self.assertEqual(mobile[selector].get("grid-auto-flow"), "row")

    def test_mobile_overrides_win_the_cascade_for_real_multicolumn_containers(self) -> None:
        top_level = _css_blocks(self.css)
        mobile_blocks = tuple(
            (body, position)
            for prelude, body, position in top_level
            if "@media (max-width: 20rem)" == " ".join(prelude.split())
        )
        self.assertEqual(len(mobile_blocks), 1)
        mobile_body, mobile_position = mobile_blocks[0]
        mobile_rules = {
            selector: (declarations, position)
            for selector, declarations, position in _rules(
                f"@media (max-width: 20rem) {{{mobile_body}}}"
            )
        }
        desktop_rules = {
            selector: (declarations, position)
            for selector, declarations, position in _rules(
                self.css[:mobile_position]
            )
        }
        expected_mobile = {
            "grid-template-columns": "1fr",
            "grid-auto-flow": "row",
            "grid-auto-columns": "minmax(0, 1fr)",
        }
        for kind, container in _MULTI_COLUMN_CONTAINERS:
            selector = f".visualization--{kind.value} .{container}"
            with self.subTest(selector=selector):
                self.assertIn(selector, desktop_rules)
                self.assertIn(selector, mobile_rules)
                desktop_declarations, _ = desktop_rules[selector]
                mobile_declarations, _ = mobile_rules[selector]
                self.assertTrue(
                    {
                        "grid-template-columns",
                        "grid-auto-flow",
                        "grid-auto-columns",
                    }
                    & desktop_declarations.keys()
                )
                node_classes = {
                    f"visualization--{kind.value}",
                    container,
                }
                competing_desktop_rules = [
                    (candidate, position)
                    for candidate, (declarations, position) in desktop_rules.items()
                    if _selector_classes(candidate)
                    and _selector_classes(candidate) <= node_classes
                    and {
                        "grid-template-columns",
                        "grid-auto-flow",
                        "grid-auto-columns",
                    }
                    & declarations.keys()
                ]
                self.assertTrue(competing_desktop_rules)
                self.assertLessEqual(
                    max(
                        _specificity(candidate)
                        for candidate, _ in competing_desktop_rules
                    ),
                    _specificity(selector),
                )
                self.assertLess(
                    max(position for _, position in competing_desktop_rules),
                    mobile_position,
                )
                self.assertEqual(
                    {
                        name: mobile_declarations.get(name)
                        for name in expected_mobile
                    },
                    expected_mobile,
                )
        connector_rules = [
            (selector, declarations)
            for selector, declarations, _ in _rules(self.css[:mobile_position])
            if "::after" in selector and declarations.get("content") == '""'
        ]
        self.assertTrue(connector_rules)
        for selector, _ in connector_rules:
            with self.subTest(connector=selector):
                self.assertIn(selector, mobile_rules)
                declarations, _ = mobile_rules[selector]
                self.assertEqual(declarations.get("content"), "none")
                self.assertEqual(declarations.get("display"), "none")

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
