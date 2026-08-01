from __future__ import annotations

import unittest

from curriculum_builder.errors import CurriculumValidationError
from curriculum_builder.javascript_safety import (
    MAX_JAVASCRIPT_BYTES,
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
        )
        for payload in payloads:
            with self.subTest(payload=payload), self.assertRaises(CurriculumValidationError):
                validate_javascript_bytes(payload)

    def test_navigation_words_in_ordinary_text_do_not_create_false_positives(self) -> None:
        source = b"var explanation = 'open navigation sendBeacon'; // ordinary prose\n"
        self.assertEqual(validate_javascript_bytes(source), source.decode())


if __name__ == "__main__":
    unittest.main()
