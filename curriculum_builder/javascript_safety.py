"""Conservative source validation for the one handwritten browser runtime."""

from __future__ import annotations

import re
import unicodedata
from typing import Final

from .errors import CurriculumValidationError


MAX_JAVASCRIPT_BYTES: Final = 40 * 1024
_ALLOWED_CONTROLS: Final = frozenset("\t\n\r")
_FORBIDDEN = tuple(
    re.compile(pattern, re.ASCII)
    for pattern in (
        r"(?<![A-Za-z0-9_$])eval(?![A-Za-z0-9_$])",
        r"(?<![A-Za-z0-9_$])Function(?![A-Za-z0-9_$])",
        r"(?<![A-Za-z0-9_$])import\s*\(",
        r"(?<![A-Za-z0-9_$])(?:fetch|XMLHttpRequest|WebSocket|EventSource)(?![A-Za-z0-9_$])",
        r"(?<![A-Za-z0-9_$])(?:SharedWorker|Worker|ServiceWorker)(?![A-Za-z0-9_$])",
        r"(?<![A-Za-z0-9_$])"
        r"(?:localStorage|sessionStorage|indexedDB|caches|cookie|clipboard)"
        r"(?![A-Za-z0-9_$])",
        r"(?<![A-Za-z0-9_$])(?:location|history|URLSearchParams)(?![A-Za-z0-9_$])|document\.URL",
        r"(?<![A-Za-z0-9_$])(?:innerHTML|outerHTML|DOMParser|insertAdjacentHTML)(?![A-Za-z0-9_$])",
        r"(?<![A-Za-z0-9_$])(?:requestAnimationFrame|MutationObserver)(?![A-Za-z0-9_$])",
        r"(?<![A-Za-z0-9_$])createElement(?![A-Za-z0-9_$])",
        r"(?<![A-Za-z0-9_$])style(?![A-Za-z0-9_$])",
        r"[A-Za-z][A-Za-z0-9+.-]*://[^\s'\"]+|['\"]//[^'\"]+",
        r"[#@]\s*source(?:Mapping)?URL\s*=",
    )
)


def _error(message: str) -> CurriculumValidationError:
    return CurriculumValidationError(message)


def validate_javascript_bytes(source: object) -> str:
    """Return a pinned UTF-8 snapshot after enforcing the closed source policy.

    This bounded lexer is defense in depth, not a JavaScript AST or sandbox.
    The accepted artifact therefore remains a small reviewed handwritten file,
    and browser tests still instrument the forbidden capabilities at runtime.
    """
    if type(source) is not bytes:
        raise _error("visualization.js must be exact bytes")
    if not source:
        raise _error("visualization.js must not be empty")
    if len(source) > MAX_JAVASCRIPT_BYTES:
        raise _error("visualization.js exceeds maximum byte count")
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError:
        raise _error("visualization.js must be valid UTF-8") from None
    if any(
        character not in _ALLOWED_CONTROLS
        and unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
        for character in text
    ):
        raise _error("visualization.js contains forbidden Unicode")
    if any(
        0xFDD0 <= ord(character) <= 0xFDEF
        or ord(character) & 0xFFFF in {0xFFFE, 0xFFFF}
        for character in text
    ):
        raise _error("visualization.js contains forbidden Unicode")
    if "`" in text or "\\" in text:
        raise _error("visualization.js contains forbidden escape syntax")
    if any(pattern.search(text) for pattern in _FORBIDDEN):
        raise _error("visualization.js contains a forbidden runtime capability")

    # Reject unfinished strings/comments. Regex literals are intentionally not
    # used by the runtime, avoiding a lexer ambiguity at this security boundary.
    index = 0
    state = "code"
    quote = ""
    delimiters: list[str] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    while index < len(text):
        char = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if state == "code":
            if char in {"'", '"'}:
                state, quote = "string", char
            elif char == "/" and following == "*":
                state, index = "block-comment", index + 1
            elif char == "/" and following == "/":
                state, index = "line-comment", index + 1
            elif char == "/":
                raise _error("visualization.js contains ambiguous slash syntax")
            elif char in "([{":
                delimiters.append(char)
            elif char in ")]}":
                if not delimiters or delimiters.pop() != pairs[char]:
                    raise _error("visualization.js contains malformed syntax")
        elif state == "string":
            if char == "\\":
                index += 1
                if index >= len(text):
                    raise _error("visualization.js contains malformed syntax")
            elif char == quote:
                state = "code"
            elif char in "\n\r":
                raise _error("visualization.js contains malformed syntax")
        elif state == "block-comment" and char == "*" and following == "/":
            state, index = "code", index + 1
        elif state == "line-comment" and char in "\n\r":
            state = "code"
        index += 1
    if state not in {"code", "line-comment"} or delimiters:
        raise _error("visualization.js contains malformed syntax")
    return text
