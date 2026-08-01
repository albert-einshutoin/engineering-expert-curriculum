from __future__ import annotations

from dataclasses import FrozenInstanceError
from html.parser import HTMLParser
from unittest.mock import patch
from urllib.parse import urljoin
import unittest

from curriculum_builder.errors import CurriculumValidationError
from curriculum_builder.html_safety import (
    ALLOWED_TAGS,
    GLOBAL_ATTRIBUTES,
    HtmlProvenance,
    MAX_ATTRIBUTES_PER_ELEMENT,
    MAX_ATTRIBUTE_VALUE_CHARS,
    MAX_FRAGMENT_BYTES,
    MAX_FRAGMENT_CHARS,
    MAX_NESTING_DEPTH,
    TAG_ATTRIBUTES,
    SafeHtml,
    validate_generated_document,
    validate_generated_fragment,
    validate_fragment,
)


class ExactString(str):
    pass


class HtmlSafetyTests(unittest.TestCase):
    def assert_rejected(self, fragment: object, message: str) -> None:
        with self.assertRaisesRegex(CurriculumValidationError, f"^{message}$"):
            validate_fragment(fragment)  # type: ignore[arg-type]

    def test_accepts_semantic_textbook_fragment_without_rewriting_it(self) -> None:
        fragment = (
            '<section id="decision" class="reading textbook">'
            "<h2>判断基準</h2><p>証拠を<em>比較</em>する。</p>"
            "<aside><strong>注意</strong></aside>"
            "<details><summary>例</summary><pre><code>x = 1</code></pre></details>"
            "<table><thead><tr><th scope=\"col\">項目</th></tr></thead>"
            "<tbody><tr><td colspan=\"2\" rowspan=\"1\">値</td></tr></tbody></table>"
            '<a href="../next.html#proof" rel="external noreferrer">次へ</a>'
            "</section>"
        )

        safe = validate_fragment(fragment)

        self.assertEqual(safe.value, fragment)
        self.assertIs(safe.provenance, HtmlProvenance.AUTHORED)
        self.assertEqual(safe, validate_fragment(fragment))
        self.assertEqual(hash(safe), hash(validate_fragment(fragment)))

    def test_authored_grammar_rejects_native_interactive_elements(self) -> None:
        for fragment in (
            '<button type="button" disabled>実行</button>',
            '<select disabled><option value="one">一つ</option></select>',
            '<label><input type="radio" name="choice" value="one" disabled>一つ</label>',
        ):
            with self.subTest(fragment=fragment):
                with self.assertRaises(CurriculumValidationError):
                    validate_fragment(fragment)

    def test_generated_grammar_accepts_only_closed_native_controls(self) -> None:
        fragment = (
            '<figure id="lesson-visual"><figcaption>図</figcaption>'
            '<p>静的説明</p><div class="visualization__controls" hidden>'
            '<label for="choice">選択</label><select id="choice" disabled>'
            '<option value="one" selected>一つ</option></select>'
            '<fieldset disabled><legend>方式</legend><label>'
            '<input type="radio" name="mode" value="safe" disabled checked>'
            '安全</label></fieldset><button type="button" disabled>適用</button>'
            '</div></figure>'
        )

        generated = validate_generated_fragment(fragment)
        self.assertEqual(generated.value, fragment)
        self.assertIs(generated.provenance, HtmlProvenance.GENERATED)

        for mutation in (
            fragment.replace("<button", "<marquee", 1).replace("</button>", "</marquee>", 1),
            fragment.replace(" disabled>適用", ' onclick="run()" disabled>適用'),
            fragment.replace(" disabled>適用", ' style="color:red" disabled>適用'),
            fragment.replace(" disabled>適用", ' data-action="run" disabled>適用'),
            fragment.replace(" disabled>適用", ' disabled="disabled">適用'),
        ):
            with self.subTest(mutation=mutation[-80:]):
                with self.assertRaises(CurriculumValidationError):
                    validate_generated_fragment(mutation)

    def test_generated_controls_require_resolved_labels_and_one_default(self) -> None:
        valid = (
            '<div class="visualization__controls" hidden>'
            '<label for="choice">選択</label><select id="choice" disabled>'
            '<option value="one" selected>一つ</option>'
            '<option value="two">二つ</option></select>'
            '<label for="mode-one"><input id="mode-one" type="radio" '
            'name="mode" value="one" disabled checked>一つ</label>'
            '<label for="mode-two"><input id="mode-two" type="radio" '
            'name="mode" value="two" disabled>二つ</label>'
            '</div>'
        )
        invalid = (
            valid.replace('for="choice"', 'for="missing"', 1),
            valid.replace('value="two">二つ', 'value="two" selected>二つ', 1),
            valid.replace(" selected>一つ", ">一つ", 1),
            valid.replace(" disabled>二つ", " disabled checked>二つ", 1),
            valid.replace(" disabled checked>一つ", " disabled>一つ", 1),
        )

        validate_generated_fragment(valid)
        for fragment in invalid:
            with self.subTest(fragment=fragment[-120:]):
                with self.assertRaises(CurriculumValidationError):
                    validate_generated_fragment(fragment)

        document = '<!doctype html><html lang="ja"><body>' + valid + '</body></html>'
        validate_generated_document(document)
        for fragment in invalid:
            with self.subTest(document=fragment[-120:]):
                with self.assertRaises(CurriculumValidationError):
                    validate_generated_document(
                        '<!doctype html><html lang="ja"><body>'
                        + fragment
                        + '</body></html>'
                    )

    def test_accepts_mixed_case_markup_and_safe_character_references(self) -> None:
        fragment = (
            "<SECTION CLASS='reading'><H2>A &amp; B</H2>"
            "<P>1 &lt; 2</P><A HREF='https://example.com/a?x=1&amp;y=2'>"
            "出典</A></SECTION>"
        )

        self.assertEqual(validate_fragment(fragment).value, fragment)

    def test_accepts_safe_textbook_fragment_landmarks(self) -> None:
        fragment = (
            '<article><header class="reading"><h1>全カタログ</h1>'
            "</header><section><h2>領域</h2><p>本文</p></section></article>"
        )

        self.assertEqual(validate_fragment(fragment).value, fragment)

    def test_accepts_representative_stable_semantic_content_models(self) -> None:
        fragment = (
            "<article><h1>設計</h1>"
            "<ul><li><p>親</p><ol><li>子</li></ol></li></ul>"
            "<dl><dt><dfn>証拠</dfn></dt><dd><p>観測可能な結果</p></dd></dl>"
            "<figure><figcaption>比較</figcaption>"
            "<blockquote><p>引用</p></blockquote></figure>"
            "<details><summary>補足</summary><div><p>本文</p></div></details>"
            "<table><thead><tr><th scope=\"col\">項目</th></tr></thead>"
            "<tbody><tr><td><p>値</p></td></tr></tbody></table>"
            "</article>"
        )

        self.assertEqual(validate_fragment(fragment).value, fragment)

    def test_safe_html_cannot_be_constructed_without_validation(self) -> None:
        for args in ((), ("<p>unvalidated</p>",)):
            with self.subTest(args=args):
                with self.assertRaisesRegex(
                    TypeError,
                    r"^SafeHtml values must be created by HTML validators$",
                ):
                    SafeHtml(*args)  # type: ignore[call-arg]

    def test_safe_html_is_frozen_and_has_no_instance_dictionary(self) -> None:
        safe = validate_fragment("<p>validated</p>")

        with self.assertRaises(FrozenInstanceError):
            safe.value = "changed"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            safe.provenance = HtmlProvenance.GENERATED  # type: ignore[misc]
        self.assertFalse(hasattr(safe, "__dict__"))

    def test_allowlists_are_immutable(self) -> None:
        self.assertIsInstance(ALLOWED_TAGS, frozenset)
        self.assertIsInstance(GLOBAL_ATTRIBUTES, frozenset)
        self.assertIsInstance(TAG_ATTRIBUTES["a"], frozenset)
        with self.assertRaises(TypeError):
            TAG_ATTRIBUTES["a"] = frozenset()  # type: ignore[index]

    def test_requires_an_exact_non_empty_string(self) -> None:
        cases = (
            (None, "fragment must be an exact string"),
            (b"<p>x</p>", "fragment must be an exact string"),
            (ExactString("<p>x</p>"), "fragment must be an exact string"),
            ("", "fragment must not be empty"),
            (" \t\r\n ", "fragment must not be empty"),
        )
        for fragment, message in cases:
            with self.subTest(fragment_type=type(fragment).__name__):
                self.assert_rejected(fragment, message)

    def test_allows_only_tab_line_feed_and_carriage_return_from_c0_controls(
        self,
    ) -> None:
        self.assertEqual(
            validate_fragment("<p>a\tb\nc\rd</p>").value,
            "<p>a\tb\nc\rd</p>",
        )
        for codepoint in tuple(range(0x20)):
            if codepoint in (0x09, 0x0A, 0x0D):
                continue
            with self.subTest(codepoint=codepoint):
                self.assert_rejected(
                    f"<p>a{chr(codepoint)}b</p>",
                    "fragment contains a disallowed control character",
                )

    def test_rejects_disallowed_scriptable_or_remote_asset_elements(self) -> None:
        fragments = (
            "<script>alert(1)</script>",
            "<iframe src='https://example.com'></iframe>",
            "<form><input></form>",
            "<img src='https://tracker.example/x.png'>",
            "<style>body { color: red }</style>",
            "<svg><a></a></svg>",
            "<math><mi>x</mi></math>",
            "<object data='x'></object>",
            "<embed src='x'>",
            "<link rel='stylesheet' href='x'>",
            "<meta http-equiv='refresh' content='0'>",
            "<template><p>x</p></template>",
        )
        for fragment in fragments:
            with self.subTest(fragment=fragment):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    r"^disallowed HTML element$",
                ):
                    validate_fragment(fragment)

    def test_rejects_event_handlers_style_and_unknown_attributes(self) -> None:
        cases = (
            ("<p onclick='run()'>x</p>", "disallowed HTML attribute on p"),
            ("<p OnLoad='run()'>x</p>", "disallowed HTML attribute on p"),
            ("<p style='color:red'>x</p>", "disallowed HTML attribute on p"),
            ("<p title='tooltip'>x</p>", "disallowed HTML attribute on p"),
            ("<a target='_blank'>x</a>", "disallowed HTML attribute on a"),
        )
        for fragment, message in cases:
            with self.subTest(fragment=fragment):
                self.assert_rejected(fragment, message)

    def test_disallowed_names_cannot_amplify_or_leak_through_errors(self) -> None:
        marker = "sensitiveleakmarker"
        oversized_name = marker * 1_300
        cases = (
            (
                f"<{oversized_name}>x</{oversized_name}>",
                "disallowed HTML element",
            ),
            (
                f'<p data-{oversized_name}="x">x</p>',
                "disallowed HTML attribute on p",
            ),
        )
        for fragment, message in cases:
            with self.subTest(message=message):
                with self.assertRaises(CurriculumValidationError) as caught:
                    validate_fragment(fragment)
                rendered = str(caught.exception)
                self.assertEqual(rendered, message)
                self.assertLess(len(rendered), 128)
                self.assertNotIn(marker, rendered)

    def test_rejects_duplicate_attributes_after_case_normalization(self) -> None:
        for fragment in (
            "<p id='one' ID='two'>x</p>",
            "<a href='a' HREF='b'>x</a>",
        ):
            with self.subTest(fragment=fragment):
                self.assert_rejected(fragment, "duplicate HTML attribute")

    def test_rejects_attributes_without_quoted_values(self) -> None:
        for fragment in (
            "<p class>text</p>",
            "<p class=reading>text</p>",
            '<p class="reading" id=test>text</p>',
        ):
            with self.subTest(fragment=fragment):
                self.assert_rejected(fragment, "malformed HTML start tag")

    def test_validates_class_and_id_tokens_and_rejects_duplicate_ids(self) -> None:
        valid = '<div class="alpha beta-2 gamma_value" id="proof-1">x</div>'
        self.assertEqual(validate_fragment(valid).value, valid)

        cases = (
            ('<p class=" leading">x</p>', "invalid class attribute"),
            ('<p class="two  spaces">x</p>', "invalid class attribute"),
            ('<p class="日本語">x</p>', "invalid class attribute"),
            ('<p id="1bad">x</p>', "invalid id attribute"),
            ('<p id="two ids">x</p>', "invalid id attribute"),
            (
                '<section id="same"><p id="same">x</p></section>',
                "duplicate HTML id",
            ),
        )
        for fragment, message in cases:
            with self.subTest(fragment=fragment):
                self.assert_rejected(fragment, message)

    def test_validates_rel_scope_and_table_spans(self) -> None:
        self.assertEqual(
            validate_fragment(
                '<a rel="external nofollow noreferrer noopener">x</a>'
            ).value,
            '<a rel="external nofollow noreferrer noopener">x</a>',
        )
        cases = (
            ('<a rel="opener">x</a>', "invalid rel attribute"),
            ('<a rel="external external">x</a>', "invalid rel attribute"),
            ('<th scope="invalid">x</th>', "invalid scope attribute"),
            ('<td colspan="0">x</td>', "invalid colspan attribute"),
            ('<td rowspan="-1">x</td>', "invalid rowspan attribute"),
            ('<td colspan="101">x</td>', "invalid colspan attribute"),
            ('<td rowspan="1.5">x</td>', "invalid rowspan attribute"),
        )
        for fragment, message in cases:
            with self.subTest(fragment=fragment):
                self.assert_rejected(fragment, message)

    def test_accepts_safe_relative_fragment_and_https_urls(self) -> None:
        values = (
            "",
            "#evidence",
            "?mode=review",
            "next.html",
            "./next.html",
            "../lesson/index.html?mode=review#rubric",
            "https://example.com",
            "HTTPS://docs.example.com:443/a?q=1#part",
            "https://[2001:db8::1]/reference",
            "https://例え.テスト/reference",
        )
        for value in values:
            with self.subTest(value=value):
                fragment = f'<a href="{value}">source</a>'
                self.assertEqual(validate_fragment(fragment).value, fragment)

    def test_rejects_root_relative_urls_that_escape_file_site_layout(self) -> None:
        base = "file:///tmp/site/lessons/example/index.html"
        cases = (
            ("/curriculum/index.html", "file:///curriculum/index.html"),
            ("/x", "file:///x"),
            ("//example.com/x", "file://example.com/x"),
            ("///x", "file:///x"),
        )
        for value, resolved in cases:
            with self.subTest(value=value):
                self.assertEqual(urljoin(base, value), resolved)
                self.assert_rejected(
                    f'<a href="{value}">x</a>',
                    "root-relative URLs are not file-compatible",
                )

    def test_rejects_unsafe_url_schemes_after_character_reference_decoding(
        self,
    ) -> None:
        values = (
            "javascript:alert(1)",
            "java&#x73;cript:alert(1)",
            "javascript&#58;alert(1)",
            "data:text/html,x",
            "vbscript:run()",
            "file:///etc/passwd",
            "http://example.com",
            "mailto:test@example.com",
        )
        for value in values:
            with self.subTest(value=value):
                self.assert_rejected(
                    f'<a href="{value}">x</a>',
                    "unsafe URL scheme",
                )

    def test_rejects_ambiguous_or_privileged_urls(self) -> None:
        cases = (
            (r"\example.com\x", "backslashes are not allowed in URLs"),
            (
                "https://example.com\\@evil.example/x",
                "backslashes are not allowed in URLs",
            ),
            (
                "%0Ajavascript:alert(1)",
                "encoded controls are not allowed in URLs",
            ),
            ("%5Cexample.com/x", "encoded controls are not allowed in URLs"),
            (" https://example.com", "whitespace is not allowed in URLs"),
            ("https://example.com/a b", "whitespace is not allowed in URLs"),
            (
                "&#x09;https://example.com",
                "whitespace is not allowed in URLs",
            ),
            (
                "\u200bjavascript:alert(1)",
                "control characters are not allowed in URLs",
            ),
            (
                "https://user:pass@example.com/x",
                "URL credentials are not allowed",
            ),
            ("https:///missing-host", "HTTPS URLs require a valid host"),
            ("https://example.com:bad/x", "HTTPS URLs require a valid port"),
            ("https://bad_host.example/x", "HTTPS URLs require a valid host"),
        )
        for value, message in cases:
            with self.subTest(value=value):
                self.assert_rejected(f'<a href="{value}">x</a>', message)

    def test_rejects_declarations_comments_and_processing_instructions(self) -> None:
        cases = (
            ("<!doctype html><p>x</p>", "HTML declarations are not allowed"),
            ("<!-- hidden --><p>x</p>", "HTML comments are not allowed"),
            (
                "<?xml version='1.0'?><p>x</p>",
                "HTML processing instructions are not allowed",
            ),
            ("<![CDATA[x]]><p>x</p>", "HTML declarations are not allowed"),
        )
        for fragment, message in cases:
            with self.subTest(fragment=fragment):
                self.assert_rejected(fragment, message)

    def test_rejects_unbalanced_mismatched_and_stray_closing_tags(self) -> None:
        cases = (
            ("<section><p>x</section>", "mismatched closing tag: section"),
            ("<p>x", "unclosed HTML element: p"),
            ("</p>", "stray closing tag: p"),
            ("<p>x</p></p>", "stray closing tag: p"),
        )
        for fragment, message in cases:
            with self.subTest(fragment=fragment):
                self.assert_rejected(fragment, message)

    def test_rejects_browser_tree_mutating_content_models(self) -> None:
        cases = (
            (
                "<p><div>x</div></p>",
                "invalid HTML content model: div cannot be a child of p",
            ),
            (
                '<a href="./one"><a href="./two">x</a></a>',
                "invalid HTML content model: nested a",
            ),
            (
                "<table><td>x</td></table>",
                "invalid HTML content model: td requires parent tr",
            ),
            (
                "<ul><p>x</p></ul>",
                "invalid HTML content model: ul only allows li children",
            ),
            (
                "<h1><h2>x</h2></h1>",
                "invalid HTML content model: h2 cannot be a child of h1",
            ),
        )
        for fragment, message in cases:
            with self.subTest(fragment=fragment):
                self.assert_rejected(fragment, message)

    def test_rejects_misplaced_structural_elements_and_fostered_text(self) -> None:
        cases = (
            (
                "<li>x</li>",
                "invalid HTML content model: li requires parent ul or ol",
            ),
            (
                "<dl><p>x</p></dl>",
                "invalid HTML content model: dl only allows dt or dd children",
            ),
            (
                "<table>x<tbody></tbody></table>",
                "invalid HTML content model: table cannot contain text",
            ),
            (
                "<thead><tr></tr></thead>",
                "invalid HTML content model: thead requires parent table",
            ),
            (
                "<table><thead>x</thead></table>",
                "invalid HTML content model: thead cannot contain text",
            ),
            (
                "<table><thead><td>x</td></thead></table>",
                "invalid HTML content model: td requires parent tr",
            ),
            (
                "<table><thead><tr>x</tr></thead></table>",
                "invalid HTML content model: tr cannot contain text",
            ),
        )
        for fragment, message in cases:
            with self.subTest(fragment=fragment):
                self.assert_rejected(fragment, message)

    def test_details_requires_exactly_one_leading_summary(self) -> None:
        cases = (
            (
                "<details></details>",
                "invalid HTML content model: details requires a leading summary",
            ),
            (
                "<details><p>x</p></details>",
                "invalid HTML content model: details requires summary as first child",
            ),
            (
                "<details>x<summary>s</summary></details>",
                "invalid HTML content model: details requires summary as first child",
            ),
            (
                "<details><summary>one</summary><summary>two</summary></details>",
                "invalid HTML content model: details allows one summary",
            ),
            (
                "<summary>x</summary>",
                "invalid HTML content model: summary requires parent details",
            ),
        )
        for fragment, message in cases:
            with self.subTest(fragment=fragment):
                self.assert_rejected(fragment, message)

    def test_figcaption_must_be_the_first_direct_child_and_unique(self) -> None:
        cases = (
            (
                "<figcaption>x</figcaption>",
                "invalid HTML content model: figcaption requires parent figure",
            ),
            (
                "<figure><p>x</p><figcaption>late</figcaption></figure>",
                "invalid HTML content model: figcaption must be the first figure child",
            ),
            (
                "<figure>text<figcaption>late</figcaption></figure>",
                "invalid HTML content model: figcaption must be the first figure child",
            ),
            (
                "<figure><figcaption>one</figcaption>"
                "<figcaption>two</figcaption></figure>",
                "invalid HTML content model: figure allows one figcaption",
            ),
        )
        for fragment, message in cases:
            with self.subTest(fragment=fragment):
                self.assert_rejected(fragment, message)

    def test_table_caption_must_be_the_first_direct_child_and_unique(
        self,
    ) -> None:
        valid = (
            "<table><caption>評価</caption>"
            "<thead><tr><th>観点</th></tr></thead>"
            "<tbody><tr><td>証拠</td></tr></tbody></table>"
        )
        self.assertEqual(validate_fragment(valid).value, valid)

        cases = (
            (
                "<table><thead><tr><th>観点</th></tr></thead>"
                "<caption>評価</caption></table>",
                "invalid HTML content model: "
                "caption must be the first table child",
            ),
            (
                "<table><caption>評価</caption><caption>重複</caption>"
                "<tbody><tr><td>証拠</td></tr></tbody></table>",
                "invalid HTML content model: table allows one caption",
            ),
            (
                "<section><caption>評価</caption></section>",
                "invalid HTML content model: caption requires parent table",
            ),
        )
        for fragment, message in cases:
            with self.subTest(fragment=fragment):
                self.assert_rejected(fragment, message)

    def test_rejects_self_closing_and_malformed_markup(self) -> None:
        cases = (
            ("<p/>", "self-closing HTML elements are not allowed"),
            ("<p />", "self-closing HTML elements are not allowed"),
            ("<p", "malformed HTML markup"),
            ("< p>x", "malformed HTML markup"),
            ("text < value", "malformed HTML markup"),
            ("<p>x</p extra>", "malformed HTML closing tag"),
            ('<p class="x>y">z</p>', "malformed HTML start tag"),
        )
        for fragment, message in cases:
            with self.subTest(fragment=fragment):
                self.assert_rejected(fragment, message)

    def test_rejects_fragments_over_character_and_utf8_byte_bounds(self) -> None:
        self.assert_rejected(
            "x" * (MAX_FRAGMENT_CHARS + 1),
            "fragment exceeds maximum character count",
        )
        multibyte_count = (MAX_FRAGMENT_BYTES // len("界".encode("utf-8"))) + 1
        self.assertLess(multibyte_count, MAX_FRAGMENT_CHARS)
        self.assert_rejected(
            "界" * multibyte_count,
            "fragment exceeds maximum UTF-8 byte count",
        )

    def test_rejects_excessive_nesting_attributes_and_attribute_values(
        self,
    ) -> None:
        too_deep = "<div>" * (MAX_NESTING_DEPTH + 1)
        self.assert_rejected(too_deep, "fragment exceeds maximum nesting depth")

        attributes = " ".join(
            f'id="id-{index}"' for index in range(MAX_ATTRIBUTES_PER_ELEMENT + 1)
        )
        self.assert_rejected(
            f"<p {attributes}>x</p>",
            "HTML element exceeds maximum attribute count",
        )

        value = "a" * (MAX_ATTRIBUTE_VALUE_CHARS + 1)
        self.assert_rejected(
            f'<a href="{value}">x</a>',
            "HTML attribute value exceeds maximum character count",
        )

    def test_wraps_unicode_and_parser_failures_without_leaking_raw_errors(
        self,
    ) -> None:
        self.assert_rejected(
            "<p>\ud800</p>",
            "fragment is not valid UTF-8 text",
        )

        with patch.object(
            HTMLParser,
            "feed",
            side_effect=RuntimeError("parser leaked secret-body-marker"),
        ):
            with self.assertRaisesRegex(
                CurriculumValidationError,
                r"^could not parse HTML fragment$",
            ) as caught:
                validate_fragment("<p>secret-body-marker</p>")
        self.assertNotIn("secret-body-marker", str(caught.exception))

    def test_errors_do_not_echo_the_fragment(self) -> None:
        marker = "sensitive-full-fragment-marker"
        with self.assertRaises(CurriculumValidationError) as caught:
            validate_fragment(f"<script>{marker}</script>")

        self.assertNotIn(marker, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
