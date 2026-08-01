from __future__ import annotations

from pathlib import Path
import unittest

from curriculum_builder.errors import CurriculumValidationError
from curriculum_builder.javascript_safety import (
    MAX_JAVASCRIPT_BYTES,
    validate_reviewed_visualization_runtime,
    validate_javascript_bytes,
)


class JavaScriptSafetyTests(unittest.TestCase):
    def test_accepts_a_small_closed_classic_script(self) -> None:
        source = b"(function () { 'use strict'; var value = 1; }());\n"
        self.assertIn("use strict", validate_javascript_bytes(source))

    def test_rejects_invalid_input_encoding_size_and_ambiguous_lexing(self) -> None:
        payloads = (
            object(), b"", b"\xff", b"x" * (MAX_JAVASCRIPT_BYTES + 1),
            b"'unterminated", b"/* unterminated", b"`template`", b"(function () {",
            b"'\\u0066etch'", b"//# sourceMappingURL=x\n",
            "var x = 1;\u202e".encode(),
        )
        for payload in payloads:
            with self.subTest(payload=repr(payload)[:40]):
                with self.assertRaises(CurriculumValidationError):
                    validate_javascript_bytes(payload)

    def test_rejects_every_forbidden_runtime_capability_even_in_comments(self) -> None:
        tokens = (
            "eval", "Function", "import(", "fetch", "XMLHttpRequest",
            "WebSocket", "EventSource", "Worker", "ServiceWorker",
            "localStorage", "sessionStorage", "indexedDB", "caches", "cookie",
            "clipboard", "location", "history", "innerHTML", "outerHTML",
            "DOMParser", "insertAdjacentHTML", "requestAnimationFrame",
            "MutationObserver", "createElement", "style", "https://example.com",
            "URLSearchParams", "//# sourceURL=x",
        )
        for token in tokens:
            with self.subTest(token=token), self.assertRaises(CurriculumValidationError):
                validate_javascript_bytes(f"/* {token} */\nvar safe = 1;".encode())

    def test_rejects_obfuscated_navigation_and_beacon_member_forms(self) -> None:
        payloads = (
            b"window [ 'open' ] ('x');",
            b"window [ 'o' + 'pen' ] ('x');",
            b"navigator [ \"sendBeacon\" ] ('x');",
            b"navigator [ 'send' + 'Beacon' ] ('x');",
            b"globalThis.navigation.navigate('x');",
            b"var x = navigation['currentEntry'];",
            b"open('x');",
            b"globalThis.open('x');",
            b"self.open('x');",
            b"top.open('x');",
            b"parent.open('x');",
            b"document.defaultView.open('x');",
            b"document['defaultView']['open']('x');",
            b"document.defaultView['o' + 'pen']('x');",
            b"var opener = globalThis.open; opener('x');",
            b"var w = window; w['op' + 'en']('x');",
            b"var g = globalThis; g['open']('x');",
            b"var n = navigator; n['send' + 'Beacon']('x');",
        )
        for payload in payloads:
            with self.subTest(payload=payload), self.assertRaises(CurriculumValidationError):
                validate_javascript_bytes(payload)

    def test_browser_authority_is_limited_to_direct_first_party_members(self) -> None:
        allowed = (
            b"window.matchMedia('print');",
            b"window.setTimeout(callback, 250);",
            b"window.clearTimeout(timer);",
            b"window.addEventListener('pagehide', callback);",
        )
        for source in allowed:
            with self.subTest(source=source):
                self.assertEqual(validate_javascript_bytes(source), source.decode())

        forbidden = (
            b"var w = (window);",
            b"var w = [window][0];",
            b"var w = { value: window }.value;",
            b"var w = ready ? window : model;",
            b"function authority() { return window; }",
            b"var w = (model, window);",
            b"var w = model; w = window;",
            b"window['setTimeout'](callback, 250);",
            b"window.document;",
            b"globalThis.setTimeout(callback, 250);",
            b"navigator.language;",
            b"var authority = self; authority['open']('x');",
            b"var authority = top; authority['open']('x');",
            b"var authority = parent; authority['open']('x');",
            b"var authority = document.defaultView; authority['open']('x');",
            b"window.setTimeout['con' + 'structor']('return 1')();",
            b"window.matchMedia.constructor('return 1')();",
            b"var timer = window.setTimeout; timer(callback, 250);",
            b"window.matchMedia('print').constructor('return 1')();",
        )
        for source in forbidden:
            with self.subTest(source=source):
                with self.assertRaises(CurriculumValidationError):
                    validate_javascript_bytes(source)

    def test_rejects_constructor_and_prototype_escape_members(self) -> None:
        payloads = (
            b"[].filter.constructor('return 1')();",
            b"[]['filter']['con' + 'structor']('return 1')();",
            b"value.prototype;",
            b"value['proto' + 'type'];",
            b"value.__proto__;",
            b"value['__pro' + 'to__'];",
        )
        for source in payloads:
            with self.subTest(source=source):
                with self.assertRaises(CurriculumValidationError):
                    validate_javascript_bytes(source)

    def test_rejects_reflection_and_string_derived_meta_member_escapes(self) -> None:
        payloads = (
            b"Reflect.get([], 'con' + 'structor')('return 1')();",
            b"[]['filter']['constructor'.slice(0)]('return 1')();",
            b"Object.getOwnPropertyDescriptor([], 'filter').value['con' + 'structor']('return 1')();",
        )
        for source in payloads:
            with self.subTest(source=source):
                with self.assertRaises(CurriculumValidationError):
                    validate_javascript_bytes(source)

    def test_reviewed_runtime_requires_the_versioned_exact_digest(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "static/visualization.js").read_bytes()
        self.assertIn("use strict", validate_reviewed_visualization_runtime(source))
        mutation = source.replace(b"use strict", b"use  strict", 1)
        with self.assertRaises(CurriculumValidationError):
            validate_reviewed_visualization_runtime(mutation)

    def test_navigation_words_in_ordinary_text_do_not_create_false_positives(self) -> None:
        source = b"var explanation = 'open navigation sendBeacon'; // ordinary prose\n"
        self.assertEqual(validate_javascript_bytes(source), source.decode())

    def test_open_as_non_call_identifier_is_not_a_false_positive(self) -> None:
        payloads = (
            b"var openState = 'open'; // open is ordinary prose\n",
            b"var w = model; w['open']; // non-browser object\n",
        )
        for source in payloads:
            with self.subTest(source=source):
                self.assertEqual(validate_javascript_bytes(source), source.decode())


if __name__ == "__main__":
    unittest.main()
