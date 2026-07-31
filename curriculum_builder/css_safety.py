"""Fail-closed validation for the local-only generated stylesheet."""

from __future__ import annotations

import re
import unicodedata
from typing import Final

from .errors import CurriculumValidationError


MAX_STYLESHEET_BYTES: Final = 1024 * 1024
_ALLOWED_CONTROL_CHARACTERS: Final = frozenset("\t\n\r")
_CSS_COMMENT: Final = re.compile(r"/\*.*?\*/", re.DOTALL)
_FORBIDDEN_RESOURCE_SYNTAX: Final = (
    re.compile(r"(?i)@import(?:[^a-z0-9_-]|\Z)", re.ASCII),
    re.compile(r"(?i)(?<![a-z0-9_-])url\s*\(", re.ASCII),
    re.compile(r"(?i)@font-face(?:[^a-z0-9_-]|\Z)", re.ASCII),
    re.compile(r"(?i)javascript\s*:", re.ASCII),
    re.compile(
        r"(?i)(?<![a-z0-9_-])"
        r"(?:(?:-webkit-)?image(?:-set)?|src)\s*\(",
        re.ASCII,
    ),
)


def _validation(message: str) -> CurriculumValidationError:
    return CurriculumValidationError(message)


def validate_stylesheet_bytes(source: object) -> str:
    """Validate exact immutable CSS bytes and return their decoded snapshot."""
    if type(source) is not bytes:
        raise _validation("styles.css must be exact bytes")
    if not source:
        raise _validation("styles.css must not be empty")
    if len(source) > MAX_STYLESHEET_BYTES:
        raise _validation("styles.css exceeds maximum byte count")
    try:
        stylesheet = source.decode("utf-8")
    except UnicodeDecodeError:
        raise _validation("styles.css must be valid UTF-8") from None
    if any(
        character not in _ALLOWED_CONTROL_CHARACTERS
        and unicodedata.category(character) in {"Cc", "Cf"}
        for character in stylesheet
    ):
        raise _validation("styles.css contains a forbidden control character")
    if "\\" in stylesheet:
        # CSS escapes can reconstruct every resource-bearing token below.
        # Rejecting all escapes keeps the raw-byte policy reviewable and makes
        # comments and quoted strings unable to hide a future active mutation.
        raise _validation("styles.css contains a forbidden escape")
    scan_candidates = (
        stylesheet,
        _CSS_COMMENT.sub("", stylesheet),
    )
    if any(
        pattern.search(candidate) is not None
        for candidate in scan_candidates
        for pattern in _FORBIDDEN_RESOURCE_SYNTAX
    ):
        # Scan the complete source, including inert comments and strings. This
        # deliberately trades expressiveness for a stable local-only contract.
        raise _validation(
            "styles.css contains forbidden external resource syntax"
        )
    return stylesheet
