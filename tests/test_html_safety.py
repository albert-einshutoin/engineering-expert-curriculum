from __future__ import annotations

from dataclasses import FrozenInstanceError
from html.parser import HTMLParser
from unittest.mock import patch
import unittest

from curriculum_builder.errors import CurriculumValidationError
from curriculum_builder.html_safety import (
    ALLOWED_TAGS,
    GLOBAL_ATTRIBUTES,
    MAX_ATTRIBUTES_PER_ELEMENT,
    MAX_ATTRIBUTE_VALUE_CHARS,
    MAX_FRAGMENT_BYTES,
    MAX_FRAGMENT_CHARS,
    MAX_NESTING_DEPTH,
    TAG_ATTRIBUTES,
    SafeHtml,
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
        self.assertEqual(safe, validate_fragment(fragment))
        self.assertEqual(hash(safe), hash(validate_fragment(fragment)))

    def test_accepts_mixed_case_markup_and_safe_character_references(self) -> None:
        fragment = (
            "<SECTION CLASS='reading'><H2>A &amp; B</H2>"
            "<P>1 &lt; 2</P><A HREF='https://example.com/a?x=1&amp;y=2'>"
            "出典</A></SECTION>"
        )

        self.assertEqual(validate_fragment(fragment).value, fragment)

    def test_safe_html_cannot_be_constructed_without_validation(self) -> None:
        for args in ((), ("<p>unvalidated</p>",)):
            with self.subTest(args=args):
                with self.assertRaisesRegex(
                    TypeError,
                    r"^SafeHtml values must be created by validate_fragment$",
                ):
                    SafeHtml(*args)  # type: ignore[call-arg]

    def test_safe_html_is_frozen_and_has_no_instance_dictionary(self) -> None:
        safe = validate_fragment("<p>validated</p>")

        with self.assertRaises(FrozenInstanceError):
            safe.value = "changed"  # type: ignore[misc]
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
                    r"^disallowed HTML element: [a-z0-9-]+$",
                ):
                    validate_fragment(fragment)

    def test_rejects_event_handlers_style_and_unknown_attributes(self) -> None:
        cases = (
            ("<p onclick='run()'>x</p>", "disallowed attribute: p.onclick"),
            ("<p OnLoad='run()'>x</p>", "disallowed attribute: p.onload"),
            ("<p style='color:red'>x</p>", "disallowed attribute: p.style"),
            ("<p title='tooltip'>x</p>", "disallowed attribute: p.title"),
            ("<a target='_blank'>x</a>", "disallowed attribute: a.target"),
        )
        for fragment, message in cases:
            with self.subTest(fragment=fragment):
                self.assert_rejected(fragment, message)

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
            "next.html",
            "../lesson/index.html?mode=review#rubric",
            "/curriculum/index.html",
            "https://example.com",
            "HTTPS://docs.example.com:443/a?q=1#part",
            "https://[2001:db8::1]/reference",
            "https://例え.テスト/reference",
        )
        for value in values:
            with self.subTest(value=value):
                fragment = f'<a href="{value}">source</a>'
                self.assertEqual(validate_fragment(fragment).value, fragment)

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
            ("//example.com/x", "scheme-relative URLs are not allowed"),
            ("///example.com/x", "scheme-relative URLs are not allowed"),
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
