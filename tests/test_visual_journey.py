from __future__ import annotations

from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest

from curriculum_builder.build import build_site
from curriculum_builder.html_safety import validate_generated_fragment
from curriculum_builder.render import Renderer


ROOT = Path(__file__).resolve().parents[1]


class VisualJourneyTests(unittest.TestCase):
    def test_every_page_gets_a_static_mermaid_learning_map(self) -> None:
        renderer = Renderer(ROOT / "templates")
        content = renderer.fragment(
            "index.html",
            text_values={},
            html_values={},
        )

        document = renderer.page(
            output_path=Path("catalog/index.html"),
            title="カタログ",
            description="学習カタログ",
            content=content,
        )

        self.assertIn('class="visual-journey"', document)
        self.assertIn('class="mermaid-source"', document)
        self.assertIn("flowchart LR", document)
        self.assertIn('src="../static/diagram.js"', document)
        self.assertIn("読む", document)
        self.assertIn("転用", document)

    def test_three_js_map_keeps_its_dedicated_full_screen_visual_contract(self) -> None:
        renderer = Renderer(ROOT / "templates")
        content = renderer.fragment(
            "map3d.html",
            text_values={
                "hint_text": "ドラッグで回転 / スクロールでズーム / クリックで関係を表示",
            },
            html_values={},
            interactive=True,
        )

        document = renderer.page(
            output_path=Path("map3d.html"),
            title="3Dマップ",
            description="3Dマップ",
            content=content,
        )

        self.assertNotIn('class="visual-journey"', document)
        self.assertNotIn('src="static/diagram.js"', document)
        self.assertIn('id="canvas-container"', document)
        self.assertIn('src="static/map3d.js"', document)

    def test_mermaid_source_fallback_is_safe_generated_html(self) -> None:
        fragment = validate_generated_fragment(
            '<section class="visual-journey">'
            '<h2>学習の見取り図</h2>'
            '<pre class="mermaid-source">flowchart LR\nA[読む] --&gt; B[試す]</pre>'
            '<div class="diagram-stage"></div>'
            '</section>'
        )

        self.assertRegex(fragment.value, re.compile(r"mermaid-source"))

    def test_diagram_runtime_is_local_and_dom_only(self) -> None:
        runtime = (ROOT / "static" / "diagram.js").read_text(encoding="utf-8")

        self.assertNotIn("fetch", runtime)
        self.assertNotIn("XMLHttpRequest", runtime)
        self.assertNotIn("innerHTML", runtime)
        self.assertNotIn("eval(", runtime)
        self.assertNotIn("https://", runtime)

    def test_complete_build_injects_the_visual_contract_into_every_page(self) -> None:
        with TemporaryDirectory(
            prefix="visual-journey-build-",
            dir=ROOT.parent,
        ) as directory:
            output = Path(directory) / "site"
            build_site(
                ROOT / "content",
                ROOT / "templates",
                ROOT / "static",
                output,
                require_complete_curriculum=True,
            )
            pages = tuple(sorted(output.rglob("*.html")))
            self.assertEqual(len(pages), 43)
            for page in pages:
                document = page.read_text(encoding="utf-8")
                with self.subTest(page=page.relative_to(output)):
                    if page.name == "map3d.html":
                        self.assertIn('id="canvas-container"', document)
                        self.assertIn('static/map3d.js"', document)
                    else:
                        self.assertIn('class="visual-journey"', document)
                        self.assertIn('class="mermaid-source"', document)
                        self.assertIn('static/diagram.js" defer', document)


if __name__ == "__main__":
    unittest.main()
