from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest

from curriculum_builder.build import build_site
from tools.check_site import check_site


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TASK9_SCRIPTED_LESSONS = frozenset(
    {
        "core-02-algorithms-measurement",
        "core-03-architecture-memory-caches",
        "core-04-os-processes-concurrency",
        "core-05-networks-latency-failure",
        "core-07-api-contract-design",
    }
)
TASK10_SCRIPTED_LESSONS = frozenset(
    {
        "core-02-algorithms-measurement",
        "core-03-architecture-memory-caches",
        "core-04-os-processes-concurrency",
        "core-05-networks-latency-failure",
        "core-07-api-contract-design",
        "core-12-transactions-isolation-consistency",
        "core-13-distributed-coordination-failure",
        "core-14-performance-capacity",
        "core-15-reliability-observability-slo",
    }
)
TASK11_SCRIPTED_LESSONS = TASK10_SCRIPTED_LESSONS | frozenset(
    {
        "core-16-hci-usability-accessibility",
        "core-22-evolution-safe-migrations",
        "core-24-delivery-ci-release-safety",
    }
)
_ACTIVE_CONTENT = frozenset(
    {
        "audio",
        "button",
        "embed",
        "form",
        "iframe",
        "input",
        "object",
        "script",
        "select",
        "textarea",
        "video",
    }
)


class _LandmarkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.landmarks = {name: 0 for name in ("header", "nav", "main", "footer")}
        self.html_languages: list[str] = []
        self.h1_count = 0
        self.skip_links = 0
        self.active_content: list[str] = []
        self.event_attributes: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        tag = tag.casefold()
        values = {name.casefold(): value for name, value in attrs}
        if tag in self.landmarks:
            self.landmarks[tag] += 1
        if tag == "html":
            self.html_languages.append(values.get("lang") or "")
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "a":
            classes = set((values.get("class") or "").split())
            if values.get("href") == "#main" and "skip-link" in classes:
                self.skip_links += 1
        if tag in _ACTIVE_CONTENT:
            self.active_content.append(tag)
        self.event_attributes.extend(
            name for name in values if name == "style" or name.startswith("on")
        )


def _balanced_block(source: str, marker: str) -> str:
    start = source.find(marker)
    if start < 0:
        raise AssertionError(f"missing CSS marker: {marker}")
    opening = source.find("{", start + len(marker))
    if opening < 0:
        raise AssertionError(f"missing CSS block: {marker}")
    depth = 1
    cursor = opening + 1
    while cursor < len(source) and depth:
        if source[cursor] == "{":
            depth += 1
        elif source[cursor] == "}":
            depth -= 1
        cursor += 1
    if depth:
        raise AssertionError(f"unterminated CSS block: {marker}")
    return source[opening + 1 : cursor - 1]


class AccessibilityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = TemporaryDirectory(
            prefix=".accessibility-contract-",
            dir=REPOSITORY_ROOT.parent,
        )
        cls.site = Path(cls.temporary.name) / "site"
        build_site(
            REPOSITORY_ROOT / "content",
            REPOSITORY_ROOT / "templates",
            REPOSITORY_ROOT / "static",
            cls.site,
            require_complete_curriculum=True,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_all_39_generated_pages_pass_the_release_site_checker(self) -> None:
        pages = tuple(sorted(self.site.rglob("*.html")))
        self.assertEqual(len(pages), 39)
        self.assertEqual(
            check_site(self.site, require_current_release=True),
            [],
        )

    def test_every_page_has_one_complete_landmark_and_skip_link_contract(
        self,
    ) -> None:
        for page in sorted(self.site.rglob("*.html")):
            relative = page.relative_to(self.site)
            with self.subTest(page=relative):
                parser = _LandmarkParser()
                parser.feed(page.read_text(encoding="utf-8"))
                parser.close()
                self.assertEqual(parser.html_languages, ["ja"])
                # Content cards can use contextual header elements, while the
                # unique navigation/main/footer landmarks define page routing.
                self.assertGreaterEqual(parser.landmarks["header"], 1)
                self.assertEqual(parser.landmarks["nav"], 1)
                self.assertEqual(parser.landmarks["main"], 1)
                self.assertEqual(parser.landmarks["footer"], 1)
                self.assertEqual(parser.h1_count, 1)
                self.assertEqual(parser.skip_links, 1)

    def test_task10_has_exactly_nine_scripted_lesson_pages_and_preserves_task9(
        self,
    ) -> None:
        self.assertEqual(
            tuple(
                path.relative_to(self.site).as_posix()
                for path in self.site.rglob("*.js")
            ),
            ("static/visualization.js",),
        )
        scripted_lessons: set[str] = set()
        for page in sorted(self.site.rglob("*.html")):
            relative = page.relative_to(self.site)
            with self.subTest(page=relative):
                parser = _LandmarkParser()
                parser.feed(page.read_text(encoding="utf-8"))
                parser.close()
                scripts = parser.active_content.count("script")
                if scripts:
                    self.assertEqual(relative.parts[:1], ("lessons",))
                    self.assertEqual(len(relative.parts), 3)
                    scripted_lessons.add(relative.parts[1])
                    self.assertEqual(scripts, 1)
                    self.assertTrue(
                        set(parser.active_content)
                        <= {"button", "input", "script", "select"}
                    )
                else:
                    self.assertEqual(parser.active_content, [])
                self.assertEqual(parser.event_attributes, [])
        self.assertEqual(
            scripted_lessons & TASK9_SCRIPTED_LESSONS,
            TASK9_SCRIPTED_LESSONS,
        )
        self.assertEqual(
            scripted_lessons & TASK10_SCRIPTED_LESSONS,
            TASK10_SCRIPTED_LESSONS,
        )
        self.assertEqual(scripted_lessons, TASK11_SCRIPTED_LESSONS)

    def test_release_checker_rejects_semantics_hidden_in_template(self) -> None:
        page = next(iter(sorted(self.site.rglob("*.html"))))
        original = page.read_text(encoding="utf-8")
        mutated = original.replace(
            '<a class="skip-link" href="#main">',
            '<template><a class="skip-link" href="#main">',
            1,
        ).replace("</main>", "</main></template>", 1)
        page.write_text(mutated, encoding="utf-8")
        try:
            self.assertTrue(
                any("inert" in issue for issue in check_site(self.site))
            )
        finally:
            page.write_text(original, encoding="utf-8")

    def test_print_css_preserves_content_and_hides_only_navigation_helpers(
        self,
    ) -> None:
        stylesheet = (self.site / "styles.css").read_text(encoding="utf-8")
        print_rules = _balanced_block(stylesheet, "@media print")
        self.assertIn('a[href^="https://"]::after', print_rules)
        self.assertIn('content: " (" attr(href) ")"', print_rules)
        self.assertIn("white-space: pre-wrap", print_rules)
        self.assertRegex(
            print_rules,
            r"\.site-header nav,\s*\.skip-link\s*\{\s*display:\s*none",
        )
        for content_selector in ("main", "article", "section", "pre", "table"):
            self.assertNotRegex(
                print_rules,
                rf"(?m)^\s*{content_selector}\s*\{{[^}}]*display:\s*none",
            )

    def test_runtime_states_have_non_color_css_markers_and_keep_static_oracle(self) -> None:
        stylesheet = (self.site / "static/visualizations.css").read_text(
            encoding="utf-8"
        )
        for selector in (
            ".visualization.is-enhanced",
            ".visualization__model-node.is-active",
            ".visualization__model-edge.is-active",
            ".visualization.is-complete",
            ".visualization.has-runtime-error",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, stylesheet)
        self.assertNotRegex(
            stylesheet,
            r"(?s)\.visualization[^{}]*::(?:before|after)\s*\{[^}]*content:\s*['\"][^'\"]",
        )


if __name__ == "__main__":
    unittest.main()
