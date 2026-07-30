"""Fail-closed validation for repository-authored HTML fragments."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import ipaddress
import re
from types import MappingProxyType
from urllib.parse import urlsplit

from .errors import CurriculumValidationError


MAX_FRAGMENT_CHARS = 100_000
MAX_FRAGMENT_BYTES = 262_144
MAX_NESTING_DEPTH = 64
MAX_ATTRIBUTES_PER_ELEMENT = 16
MAX_ATTRIBUTE_VALUE_CHARS = 4_096
MAX_TABLE_SPAN = 100

ALLOWED_TAGS = frozenset(
    {
        "a",
        "article",
        "aside",
        "blockquote",
        "code",
        "dd",
        "details",
        "dfn",
        "div",
        "dl",
        "dt",
        "em",
        "figcaption",
        "figure",
        "h1",
        "h2",
        "h3",
        "h4",
        "header",
        "kbd",
        "li",
        "mark",
        "ol",
        "p",
        "pre",
        "section",
        "small",
        "strong",
        "summary",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "tr",
        "ul",
    }
)
GLOBAL_ATTRIBUTES = frozenset({"class", "id"})
TAG_ATTRIBUTES = MappingProxyType(
    {
        "a": frozenset({"href", "rel"}),
        "td": frozenset({"colspan", "rowspan"}),
        "th": frozenset({"scope"}),
    }
)

_EMPTY_ATTRIBUTES = frozenset()
_CLASS_TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}", re.ASCII)
_ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}", re.ASCII)
_HOST_LABEL_PATTERN = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?",
    re.ASCII,
)
_START_TAG_PATTERN = re.compile(
    r"""
    <
    (?P<tag>[A-Za-z][A-Za-z0-9-]*)
    (?P<attributes>
        (?:
            [\t\n\r ]+
            [A-Za-z_:][A-Za-z0-9_.:-]*
            [\t\n\r ]*=[\t\n\r ]*
            (?:"[^"<>]*"|'[^'<>]*')
        )*
    )
    [\t\n\r ]*
    >
    """,
    re.ASCII | re.VERBOSE,
)
_END_TAG_PATTERN = re.compile(
    r"</[A-Za-z][A-Za-z0-9-]*[\t\n\r ]*>",
    re.ASCII,
)
_REL_VALUES = frozenset({"external", "nofollow", "noopener", "noreferrer"})
_SCOPE_VALUES = frozenset({"col", "colgroup", "row", "rowgroup"})
_ENCODED_URL_CONTROL_PATTERN = re.compile(
    r"%(?:0[0-9A-Fa-f]|1[0-9A-Fa-f]|5[Cc]|7[Ff])"
)


@dataclass(frozen=True, slots=True, init=False)
class SafeHtml:
    """An immutable fragment that can only be issued by ``validate_fragment``."""

    value: str

    def __new__(cls, *_args: object, **_kwargs: object) -> SafeHtml:
        raise TypeError("SafeHtml values must be created by validate_fragment")


def _issue_safe_html(fragment: str) -> SafeHtml:
    safe = object.__new__(SafeHtml)
    object.__setattr__(safe, "value", fragment)
    return safe


def _scan_markup_syntax(fragment: str) -> None:
    """Reject syntax outside the small subset interpreted identically by browsers."""
    cursor = 0
    while True:
        opening = fragment.find("<", cursor)
        if opening < 0:
            return

        if fragment.startswith("<!--", opening):
            comment_end = fragment.find("-->", opening + 4)
            if comment_end < 0:
                raise CurriculumValidationError("malformed HTML markup")
            cursor = comment_end + 3
            continue
        if opening + 1 == len(fragment):
            raise CurriculumValidationError("malformed HTML markup")
        first = fragment[opening + 1]
        if first not in "!?/" and not (first.isascii() and first.isalpha()):
            raise CurriculumValidationError("malformed HTML markup")

        quote: str | None = None
        closing = opening + 1
        while closing < len(fragment):
            character = fragment[closing]
            if quote is None:
                if character in {'"', "'"}:
                    quote = character
                elif character == ">":
                    break
            elif character == quote:
                quote = None
            closing += 1
        if closing == len(fragment):
            raise CurriculumValidationError("malformed HTML markup")

        token = fragment[opening : closing + 1]
        if token.startswith("</"):
            if _END_TAG_PATTERN.fullmatch(token) is None:
                raise CurriculumValidationError("malformed HTML closing tag")
        elif token.startswith("<!") or token.startswith("<?"):
            pass
        elif token.endswith("/>"):
            ordinary_token = f"{token[:-2]}>"
            if _START_TAG_PATTERN.fullmatch(ordinary_token) is None:
                raise CurriculumValidationError("malformed HTML start tag")
        elif _START_TAG_PATTERN.fullmatch(token) is None:
            raise CurriculumValidationError("malformed HTML start tag")
        cursor = closing + 1


class _FragmentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._open_tags: list[str] = []
        self._ids: set[str] = set()

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        raw_tag = self.get_starttag_text()
        if raw_tag is None or _START_TAG_PATTERN.fullmatch(raw_tag) is None:
            raise CurriculumValidationError("malformed HTML start tag")
        if tag not in ALLOWED_TAGS:
            raise CurriculumValidationError(f"disallowed HTML element: {tag}")
        if len(attrs) > MAX_ATTRIBUTES_PER_ELEMENT:
            raise CurriculumValidationError(
                "HTML element exceeds maximum attribute count"
            )

        names = tuple(name.casefold() for name, _ in attrs)
        if len(set(names)) != len(names):
            raise CurriculumValidationError("duplicate HTML attribute")

        allowed = GLOBAL_ATTRIBUTES | TAG_ATTRIBUTES.get(tag, _EMPTY_ATTRIBUTES)
        for name, value in attrs:
            normalized_name = name.casefold()
            if normalized_name.startswith("on") or normalized_name not in allowed:
                raise CurriculumValidationError(
                    f"disallowed attribute: {tag}.{normalized_name}"
                )
            if value is None:
                raise CurriculumValidationError("HTML attributes require values")
            if len(value) > MAX_ATTRIBUTE_VALUE_CHARS:
                raise CurriculumValidationError(
                    "HTML attribute value exceeds maximum character count"
                )
            self._validate_attribute(tag, normalized_name, value)

        if len(self._open_tags) >= MAX_NESTING_DEPTH:
            raise CurriculumValidationError(
                "fragment exceeds maximum nesting depth"
            )
        self._open_tags.append(tag)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del tag, attrs
        raise CurriculumValidationError(
            "self-closing HTML elements are not allowed"
        )

    def handle_endtag(self, tag: str) -> None:
        if tag not in ALLOWED_TAGS:
            raise CurriculumValidationError(f"disallowed HTML element: {tag}")
        if not self._open_tags:
            raise CurriculumValidationError(f"stray closing tag: {tag}")
        if self._open_tags[-1] != tag:
            raise CurriculumValidationError(f"mismatched closing tag: {tag}")
        self._open_tags.pop()

    def handle_comment(self, data: str) -> None:
        del data
        raise CurriculumValidationError("HTML comments are not allowed")

    def handle_decl(self, decl: str) -> None:
        del decl
        raise CurriculumValidationError("HTML declarations are not allowed")

    def unknown_decl(self, data: str) -> None:
        del data
        raise CurriculumValidationError("HTML declarations are not allowed")

    def handle_pi(self, data: str) -> None:
        del data
        raise CurriculumValidationError(
            "HTML processing instructions are not allowed"
        )

    def finish(self) -> None:
        if self._open_tags:
            raise CurriculumValidationError(
                f"unclosed HTML element: {self._open_tags[-1]}"
            )

    def _validate_attribute(self, tag: str, name: str, value: str) -> None:
        del tag
        if name == "class":
            tokens = value.split(" ")
            if (
                not tokens
                or len(tokens) > MAX_ATTRIBUTES_PER_ELEMENT
                or any(
                    _CLASS_TOKEN_PATTERN.fullmatch(token) is None
                    for token in tokens
                )
                or len(set(tokens)) != len(tokens)
            ):
                raise CurriculumValidationError("invalid class attribute")
        elif name == "id":
            if _ID_PATTERN.fullmatch(value) is None:
                raise CurriculumValidationError("invalid id attribute")
            if value in self._ids:
                raise CurriculumValidationError("duplicate HTML id")
            self._ids.add(value)
        elif name == "rel":
            tokens = value.split(" ")
            if (
                not tokens
                or any(token not in _REL_VALUES for token in tokens)
                or len(set(tokens)) != len(tokens)
            ):
                raise CurriculumValidationError("invalid rel attribute")
        elif name == "scope":
            if value not in _SCOPE_VALUES:
                raise CurriculumValidationError("invalid scope attribute")
        elif name in {"colspan", "rowspan"}:
            if (
                not value.isascii()
                or not value.isdecimal()
                or not 1 <= int(value) <= MAX_TABLE_SPAN
            ):
                raise CurriculumValidationError(f"invalid {name} attribute")
        elif name == "href":
            _validate_url(value)


def _validate_url(value: str) -> None:
    # URL validation is deliberately stricter than browser parsing. Returning the
    # original fragment is safe only when obfuscated schemes cannot be reinterpreted.
    if any(character.isspace() for character in value):
        raise CurriculumValidationError("whitespace is not allowed in URLs")
    if "\\" in value:
        raise CurriculumValidationError("backslashes are not allowed in URLs")
    if _ENCODED_URL_CONTROL_PATTERN.search(value):
        raise CurriculumValidationError("encoded controls are not allowed in URLs")
    if value.startswith("//"):
        raise CurriculumValidationError("scheme-relative URLs are not allowed")

    try:
        parsed = urlsplit(value)
    except ValueError:
        raise CurriculumValidationError("malformed URL") from None

    if parsed.username is not None or parsed.password is not None:
        raise CurriculumValidationError("URL credentials are not allowed")
    if parsed.scheme and parsed.scheme.casefold() != "https":
        raise CurriculumValidationError("unsafe URL scheme")
    if not parsed.scheme:
        if parsed.netloc:
            raise CurriculumValidationError("scheme-relative URLs are not allowed")
        return

    hostname = parsed.hostname
    if hostname is None or not _is_valid_hostname(hostname):
        raise CurriculumValidationError("HTTPS URLs require a valid host")
    try:
        parsed.port
    except ValueError:
        raise CurriculumValidationError("HTTPS URLs require a valid port") from None


def _is_valid_hostname(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        try:
            ascii_hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError:
            return False
        if len(ascii_hostname) > 253:
            return False
        labels = ascii_hostname.removesuffix(".").split(".")
        return bool(labels) and all(
            _HOST_LABEL_PATTERN.fullmatch(label) is not None for label in labels
        )
    return True


def validate_fragment(fragment: str) -> SafeHtml:
    """Validate an authored fragment and return an immutable trusted value."""
    if type(fragment) is not str:
        raise CurriculumValidationError("fragment must be an exact string")
    if not fragment.strip():
        raise CurriculumValidationError("fragment must not be empty")
    if len(fragment) > MAX_FRAGMENT_CHARS:
        raise CurriculumValidationError(
            "fragment exceeds maximum character count"
        )
    try:
        encoded = fragment.encode("utf-8")
    except UnicodeError:
        raise CurriculumValidationError("fragment is not valid UTF-8 text") from None
    if len(encoded) > MAX_FRAGMENT_BYTES:
        raise CurriculumValidationError(
            "fragment exceeds maximum UTF-8 byte count"
        )
    if any(
        ord(character) < 0x20 and character not in "\t\n\r"
        for character in fragment
    ):
        raise CurriculumValidationError(
            "fragment contains a disallowed control character"
        )

    _scan_markup_syntax(fragment)
    parser = _FragmentParser()
    try:
        parser.feed(fragment)
        parser.close()
        parser.finish()
    except CurriculumValidationError:
        raise
    except Exception:
        raise CurriculumValidationError("could not parse HTML fragment") from None
    return _issue_safe_html(fragment)
