"""Conservative source validation for the one handwritten browser runtime."""

from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata
from typing import Final

from .errors import CurriculumValidationError


MAX_JAVASCRIPT_BYTES: Final = 40 * 1024
# Version 1 pins the exact bytes reviewed in static/visualization.js. Updating
# this value is a deliberate security review operation: review the runtime diff,
# run the DOM/security suites, calculate SHA-256 independently, then update this
# constant in its own reviewable commit. Tests must never derive or rewrite it.
VISUALIZATION_RUNTIME_SHA256_V1: Final = (
    "3dd0446b98f019ccb830b6ceff8b3adcf62949872a94349edba28d989fd5b07b"
)
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
        r"(?<![A-Za-z0-9_$])(?:Reflect|getOwnPropertyDescriptor|slice)(?![A-Za-z0-9_$])",
        r"(?<![A-Za-z0-9_$])(?:join|fromCharCode)(?![A-Za-z0-9_$])",
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
_BROWSER_AUTHORITY: Final = re.compile(
    r"(?<![A-Za-z0-9_$])"
    r"(window|document|globalThis|navigator|self|top|parent)"
    r"(?![A-Za-z0-9_$])",
    re.ASCII,
)
_DOCUMENT_DEFAULT_VIEW: Final = re.compile(
    r"(?<![A-Za-z0-9_$])document\s*\.\s*defaultView(?![A-Za-z0-9_$])",
    re.ASCII,
)
_DIRECT_WINDOW_CALL: Final = re.compile(
    r"\s*\.\s*([A-Za-z_$][A-Za-z0-9_$]*)(?![A-Za-z0-9_$])\s*\(",
    re.ASCII,
)
_ALLOWED_AUTHORITY_CALLS: Final = {
    "window": frozenset(
        {"addEventListener", "clearTimeout", "matchMedia", "setTimeout"}
    ),
    "document": frozenset({"querySelectorAll"}),
}
_FORBIDDEN_META_MEMBER: Final = re.compile(
    r"(?<![A-Za-z0-9_$])(?:constructor|prototype|__proto__)(?![A-Za-z0-9_$])",
    re.ASCII,
)
_QUOTED_IDENTIFIER: Final = re.compile(
    r"(['\"])([A-Za-z_$][A-Za-z0-9_$]*)\1",
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


def _direct_call_end(code: str, opening: int) -> int | None:
    depth = 1
    for index in range(opening + 1, len(code)):
        if code[index] == "(":
            depth += 1
        elif code[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _has_forbidden_browser_authority(code: str) -> bool:
    """Accept only measured, complete direct ``window`` call expressions.

    This is intentionally an allowlist over the closed first-party artifact,
    not open-ended regex data-flow. Rejecting every bare authority value also
    closes aliases hidden in containers, expressions, and function returns;
    requiring the call terminator closes extraction and constructor chains.
    """
    if _DOCUMENT_DEFAULT_VIEW.search(code):
        return True
    for authority in _BROWSER_AUTHORITY.finditer(code):
        root = authority.group(1)
        allowed = _ALLOWED_AUTHORITY_CALLS.get(root)
        if allowed is None:
            return True
        call = _DIRECT_WINDOW_CALL.match(code, authority.end())
        if call is None or call.group(1) not in allowed:
            return True
        opening = call.end() - 1
        closing = _direct_call_end(code, opening)
        if closing is None:
            return True
        following = closing + 1
        while following < len(code) and code[following].isspace():
            following += 1
        if following >= len(code) or code[following] != ";":
            return True
    return False


def _has_forbidden_meta_member(members: str) -> bool:
    if _FORBIDDEN_META_MEMBER.search(members):
        return True
    for opening in (index for index, char in enumerate(members) if char == "["):
        closing = members.find("]", opening + 1)
        if closing < 0:
            continue
        expression = members[opening + 1:closing]
        parts = [match.group(2) for match in _QUOTED_IDENTIFIER.finditer(expression)]
        if not parts:
            continue
        residual = _QUOTED_IDENTIFIER.sub("", expression)
        if re.fullmatch(r"\s*(?:\+\s*)*", residual) and "".join(parts) in {
            "constructor", "prototype", "__proto__",
        }:
            return True
    return False


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
        or _has_forbidden_browser_authority(code_view)
        or _has_forbidden_meta_member(member_view)
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


def validate_reviewed_visualization_runtime(source: object) -> str:
    """Validate and bind the runtime to the versioned reviewed byte digest.

    The bounded lexer is defense in depth. This exact digest comparison is the
    primary trust boundary used by both the builder and release-site checker.
    """
    text = validate_javascript_bytes(source)
    if type(source) is not bytes:
        raise _error("visualization.js must be exact bytes")
    digest = hashlib.sha256(source).hexdigest()
    if not hmac.compare_digest(digest, VISUALIZATION_RUNTIME_SHA256_V1):
        raise _error("visualization.js does not match reviewed SHA-256 v1")
    return text
