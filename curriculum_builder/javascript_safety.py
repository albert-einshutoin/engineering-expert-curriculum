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
_FORBIDDEN_NAVIGATION_CODE: Final = re.compile(
    r"(?<![A-Za-z0-9_$])(?:navigation|sendBeacon)(?![A-Za-z0-9_$])"
    r"|(?<![A-Za-z0-9_$])open(?![A-Za-z0-9_$])"
    r"|(?<![A-Za-z0-9_$])navigator\s*\.\s*sendBeacon(?![A-Za-z0-9_$])",
    re.ASCII,
)
_FORBIDDEN_NAVIGATION_MEMBER: Final = re.compile(
    r"(?<![A-Za-z0-9_$])(?:window|globalThis|self|top|parent|navigator|document|defaultView)\s*\[",
    re.ASCII,
)
_ALIAS_ASSIGNMENT: Final = re.compile(
    r"(?<![A-Za-z0-9_$])(?:var|let|const)?\s*"
    r"([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*"
    r"([A-Za-z_$][A-Za-z0-9_$]*)\s*(?:;|,|\n)",
    re.ASCII,
)


def _error(message: str) -> CurriculumValidationError:
    return CurriculumValidationError(message)


def _navigation_views(text: str) -> tuple[str, str]:
    """Return code-only and comment-free views for exact member checks.

    Ordinary prose in comments and strings is ignored. Quoted member names are
    retained only in the comment-free view so bracket notation remains visible
    to the conservative closed-runtime policy.
    """
    code = list(text)
    without_comments = list(text)
    index = 0
    state = "code"
    quote = ""
    while index < len(text):
        char = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if state == "code":
            if char in {"'", '"'}:
                state, quote = "string", char
                code[index] = " "
            elif char == "/" and following == "*":
                state = "block-comment"
                code[index] = code[index + 1] = " "
                without_comments[index] = without_comments[index + 1] = " "
                index += 1
            elif char == "/" and following == "/":
                state = "line-comment"
                code[index] = code[index + 1] = " "
                without_comments[index] = without_comments[index + 1] = " "
                index += 1
        elif state == "string":
            code[index] = " "
            if char == quote:
                state = "code"
        elif state == "block-comment":
            code[index] = without_comments[index] = " "
            if char == "*" and following == "/":
                code[index + 1] = without_comments[index + 1] = " "
                state = "code"
                index += 1
        else:
            code[index] = without_comments[index] = " "
            if char in "\n\r":
                state = "code"
        index += 1
    return "".join(code), "".join(without_comments)


def _has_forbidden_navigation_alias(code: str, members: str) -> bool:
    """Track simple global aliases, then reject every computed member access.

    The handwritten runtime does not need aliases for browser authority. This
    closed rule intentionally rejects all bracket access through such aliases,
    including concatenated property names that a token blacklist could miss.
    """
    aliases = {"window", "globalThis", "navigator"}
    assignments = tuple(_ALIAS_ASSIGNMENT.findall(code))
    changed = True
    while changed:
        changed = False
        for target, source in assignments:
            if source in aliases and target not in aliases:
                aliases.add(target)
                changed = True
    return any(
        re.search(
            rf"(?<![A-Za-z0-9_$]){re.escape(alias)}\s*\[",
            members,
            re.ASCII,
        )
        for alias in aliases
    )


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
    code_view, member_view = _navigation_views(text)
    if (
        _FORBIDDEN_NAVIGATION_CODE.search(code_view)
        or _FORBIDDEN_NAVIGATION_MEMBER.search(member_view)
        or _has_forbidden_navigation_alias(code_view, member_view)
    ):
        raise _error("visualization.js contains a forbidden navigation capability")

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
