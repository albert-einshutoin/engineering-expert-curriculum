"""Fail-closed validation for repository-authored HTML fragments."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from html.parser import HTMLParser
import ipaddress
import re
from types import MappingProxyType
import unicodedata
from urllib.parse import urlsplit

from .errors import CurriculumValidationError


MAX_FRAGMENT_CHARS = 100_000
MAX_FRAGMENT_BYTES = 262_144
MAX_GENERATED_DOCUMENT_CHARS = 4_000_000
MAX_GENERATED_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_NESTING_DEPTH = 64
MAX_ATTRIBUTES_PER_ELEMENT = 16
MAX_ATTRIBUTE_VALUE_CHARS = 4_096
MAX_GENERATED_CONTROL_REFERENCES = 4_096
MAX_TABLE_SPAN = 100

ALLOWED_TAGS = frozenset(
    {
        "a",
        "article",
        "aside",
        "blockquote",
        "caption",
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
_GENERATED_START_TAG_PATTERN = re.compile(
    r"""
    <
    (?P<tag>[A-Za-z][A-Za-z0-9-]*)
    (?P<attributes>
        (?:
            [\t\n\r ]+
            [A-Za-z_:][A-Za-z0-9_.:-]*
            (?:
                [\t\n\r ]*=[\t\n\r ]*
                (?:"[^"<>]*"|'[^'<>]*')
            )?
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
_PHRASING_ELEMENTS = frozenset(
    {"a", "code", "dfn", "em", "kbd", "mark", "small", "strong"}
)
_PHRASING_ONLY_CONTAINERS = _PHRASING_ELEMENTS | frozenset(
    {"caption", "h1", "h2", "h3", "h4", "p", "pre", "summary"}
)
_STRUCTURAL_CHILDREN = MappingProxyType(
    {
        "dl": frozenset({"dd", "dt"}),
        "ol": frozenset({"li"}),
        "table": frozenset({"caption", "tbody", "thead"}),
        "tbody": frozenset({"tr"}),
        "thead": frozenset({"tr"}),
        "tr": frozenset({"td", "th"}),
        "ul": frozenset({"li"}),
    }
)
_STRUCTURAL_CHILD_LABELS = MappingProxyType(
    {
        "dl": "dt or dd",
        "ol": "li",
        "table": "caption, thead, or tbody",
        "tbody": "tr",
        "thead": "tr",
        "tr": "th or td",
        "ul": "li",
    }
)
_REQUIRED_PARENTS = MappingProxyType(
    {
        "dd": (frozenset({"dl"}), "dd requires parent dl"),
        "dt": (frozenset({"dl"}), "dt requires parent dl"),
        "figcaption": (
            frozenset({"figure"}),
            "figcaption requires parent figure",
        ),
        "li": (frozenset({"ol", "ul"}), "li requires parent ul or ol"),
        "summary": (
            frozenset({"details"}),
            "summary requires parent details",
        ),
        "caption": (
            frozenset({"table"}),
            "caption requires parent table",
        ),
        "tbody": (frozenset({"table"}), "tbody requires parent table"),
        "td": (frozenset({"tr"}), "td requires parent tr"),
        "th": (frozenset({"tr"}), "th requires parent tr"),
        "thead": (frozenset({"table"}), "thead requires parent table"),
        "tr": (
            frozenset({"tbody", "thead"}),
            "tr requires parent thead or tbody",
        ),
    }
)

_GENERATED_CONTROL_TAGS = frozenset(
    {"button", "fieldset", "input", "label", "legend", "option", "select"}
)
_GENERATED_RENDERER_TAGS = frozenset({"br", "nav", "span"})
_GENERATED_INTERACTIVE_TAGS = frozenset({"form"})
_GENERATED_DOCUMENT_TAGS = frozenset(
    {"body", "footer", "head", "html", "link", "main", "meta", "nav", "script", "title"}
)
_GENERATED_FRAGMENT_TAGS = (
    ALLOWED_TAGS
    | _GENERATED_CONTROL_TAGS
    | _GENERATED_RENDERER_TAGS
    | _GENERATED_INTERACTIVE_TAGS
)
_GENERATED_ATTRIBUTES = MappingProxyType(
    {
        "button": frozenset(
            {
                "aria-controls",
                "aria-expanded",
                "aria-pressed",
                "data-action",
                "data-complete-lesson",
                "data-daily-regenerate",
                "data-export-progress",
                "data-filter",
                "data-reset-progress",
                "data-tab",
                "disabled",
                "type",
            }
        ),
        "code": frozenset({"data-edge-id", "data-node-id", "data-option-id", "data-parameter-id"}),
        "dd": frozenset({"data-node-id"}),
        "div": frozenset(
            {
                "aria-label",
                "data-curriculum-search",
                "data-daily-output",
                "data-search-results",
                "hidden",
                "role",
            }
        ),
        "dt": frozenset({"data-node-id"}),
        "fieldset": frozenset({"disabled"}),
        "html": frozenset({"lang"}),
        "figure": frozenset(
            {
                "data-default-interval-ms",
                "data-interaction-mode",
                "data-initial-state-id",
                "data-simulation-kind",
                "data-visualization-id",
            }
        ),
        "form": frozenset({"data-daily-form"}),
        "input": frozenset(
            {
                "accept",
                "checked",
                "data-curriculum-search",
                "data-import-progress",
                "data-parameter-id",
                "disabled",
                "hidden",
                "name",
                "type",
                "value",
            }
        ),
        "label": frozenset({"for"}),
        "li": frozenset({"data-edge-id", "data-node-id", "data-state-id", "data-step-index"}),
        "link": frozenset({"href", "rel"}),
        "main": frozenset({"id"}),
        "meta": frozenset({"charset", "content", "http-equiv", "name"}),
        "nav": frozenset({"aria-label"}),
        "option": frozenset({"selected", "value"}),
        "p": frozenset({"aria-atomic", "aria-live", "role"}),
        "section": frozenset({"aria-describedby"}),
        "script": frozenset({"defer", "src", "type"}),
        "select": frozenset(
            {"data-action", "data-parameter-id", "disabled", "id", "name"}
        ),
        "strong": frozenset({"data-node-id"}),
        "td": frozenset({"data-edge-id"}),
        "th": frozenset({"data-node-id", "scope"}),
        "tr": frozenset({"data-edge-id", "data-from-state-id", "data-outcome-id", "data-state-id", "data-to-state-id", "data-transition-event", "data-transition-id"}),
    }
)
_BOOLEAN_ATTRIBUTES = frozenset({"checked", "defer", "disabled", "hidden", "selected"})
_GENERATED_VOID_TAGS = frozenset({"input", "link", "meta"})


class HtmlProvenance(StrEnum):
    AUTHORED = "authored"
    GENERATED = "generated"
    GENERATED_INTERACTIVE = "generated-interactive"


@dataclass(slots=True)
class _ElementFrame:
    tag: str
    has_direct_content: bool = False
    summary_seen: bool = False
    figcaption_seen: bool = False
    caption_seen: bool = False
    selected_options: int = 0


@dataclass(frozen=True, slots=True, init=False)
class SafeHtml:
    """Immutable HTML issued only by the matching closed grammar validator."""

    value: str
    provenance: HtmlProvenance

    def __new__(cls, *_args: object, **_kwargs: object) -> SafeHtml:
        raise TypeError("SafeHtml values must be created by HTML validators")


def _issue_safe_html(
    fragment: str,
    provenance: HtmlProvenance,
) -> SafeHtml:
    safe = object.__new__(SafeHtml)
    object.__setattr__(safe, "value", fragment)
    object.__setattr__(safe, "provenance", provenance)
    return safe


def _scan_markup_syntax(
    fragment: str,
    *,
    generated: bool = False,
) -> None:
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
            pattern = (
                _GENERATED_START_TAG_PATTERN if generated else _START_TAG_PATTERN
            )
            if pattern.fullmatch(ordinary_token) is None:
                raise CurriculumValidationError("malformed HTML start tag")
        elif (
            _GENERATED_START_TAG_PATTERN if generated else _START_TAG_PATTERN
        ).fullmatch(token) is None:
            raise CurriculumValidationError("malformed HTML start tag")
        cursor = closing + 1


class _FragmentParser(HTMLParser):
    def __init__(
        self,
        *,
        generated: bool = False,
        document: bool = False,
        generated_controls: bool = True,
    ) -> None:
        super().__init__(convert_charrefs=True)
        self._generated = generated
        self._document = document
        self._generated_controls = generated_controls
        self._doctype_seen = False
        self._open_tags: list[_ElementFrame] = []
        self._ids: set[str] = set()
        self._labelable_ids: set[str] = set()
        self._label_references: list[str] = []
        self._select_default_counts: list[int] = []
        self._radio_group_defaults: dict[str, tuple[int, int]] = {}
        self._generated_control_references = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        raw_tag = self.get_starttag_text()
        pattern = (
            _GENERATED_START_TAG_PATTERN
            if self._generated
            else _START_TAG_PATTERN
        )
        if raw_tag is None or pattern.fullmatch(raw_tag) is None:
            raise CurriculumValidationError("malformed HTML start tag")
        allowed_tags = ALLOWED_TAGS
        if self._generated:
            allowed_tags = _GENERATED_FRAGMENT_TAGS
            if self._document:
                allowed_tags |= _GENERATED_DOCUMENT_TAGS
            if self._generated_controls and tag in _GENERATED_INTERACTIVE_TAGS:
                raise CurriculumValidationError(
                    "active forms require generated interactive provenance"
                )
        if tag not in allowed_tags:
            raise CurriculumValidationError("disallowed HTML element")
        if len(attrs) > MAX_ATTRIBUTES_PER_ELEMENT:
            raise CurriculumValidationError(
                "HTML element exceeds maximum attribute count"
            )

        names = tuple(name.casefold() for name, _ in attrs)
        if len(set(names)) != len(names):
            raise CurriculumValidationError("duplicate HTML attribute")

        allowed = GLOBAL_ATTRIBUTES | TAG_ATTRIBUTES.get(tag, _EMPTY_ATTRIBUTES)
        if self._generated:
            allowed |= _GENERATED_ATTRIBUTES.get(tag, _EMPTY_ATTRIBUTES)
        for name, value in attrs:
            normalized_name = name.casefold()
            if normalized_name.startswith("on") or normalized_name not in allowed:
                raise CurriculumValidationError(
                    f"disallowed HTML attribute on {tag}"
                )
            if normalized_name in _BOOLEAN_ATTRIBUTES:
                if not self._generated or value is not None:
                    raise CurriculumValidationError(
                        "boolean HTML attributes must not have values"
                    )
                continue
            if value is None:
                raise CurriculumValidationError("HTML attributes require values")
            if len(value) > MAX_ATTRIBUTE_VALUE_CHARS:
                raise CurriculumValidationError(
                    "HTML attribute value exceeds maximum character count"
                )
            self._validate_attribute(tag, normalized_name, value)

        if self._generated and self._generated_controls:
            self._validate_generated_control(tag, attrs)

        if (
            self._generated
            and self._document
            and tag == "script"
            and (not self._open_tags or self._open_tags[-1].tag != "body")
        ):
            raise CurriculumValidationError(
                "generated script must be a direct child of body"
            )

        if len(self._open_tags) >= MAX_NESTING_DEPTH:
            raise CurriculumValidationError(
                "fragment exceeds maximum nesting depth"
            )
        self._validate_content_model(tag)
        if self._generated and self._generated_controls:
            self._track_generated_control(tag, attrs)
        if self._generated and tag in _GENERATED_VOID_TAGS:
            return
        self._open_tags.append(_ElementFrame(tag=tag))

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if not self._generated:
            raise CurriculumValidationError(
                "self-closing HTML elements are not allowed"
            )
        if tag not in _GENERATED_VOID_TAGS:
            raise CurriculumValidationError(
                "non-void self-closing HTML elements are not allowed"
            )
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        allowed_tags = ALLOWED_TAGS
        if self._generated:
            allowed_tags = _GENERATED_FRAGMENT_TAGS
            if self._document:
                allowed_tags |= _GENERATED_DOCUMENT_TAGS
        if tag not in allowed_tags:
            raise CurriculumValidationError("disallowed HTML element")
        if self._generated and tag in _GENERATED_VOID_TAGS:
            raise CurriculumValidationError(f"stray closing tag: {tag}")
        if not self._open_tags:
            raise CurriculumValidationError(f"stray closing tag: {tag}")
        frame = self._open_tags[-1]
        if frame.tag != tag:
            raise CurriculumValidationError(f"mismatched closing tag: {tag}")
        if tag == "details" and not frame.summary_seen:
            raise CurriculumValidationError(
                "invalid HTML content model: details requires a leading summary"
            )
        if self._generated and tag == "select":
            self._select_default_counts.append(frame.selected_options)
        self._open_tags.pop()

    def handle_data(self, data: str) -> None:
        if not self._open_tags or not data:
            return
        frame = self._open_tags[-1]
        if not data.strip(" \t\n\r"):
            return
        if self._generated and frame.tag == "script":
            raise CurriculumValidationError("inline generated script is forbidden")
        if frame.tag in _STRUCTURAL_CHILDREN:
            raise CurriculumValidationError(
                f"invalid HTML content model: {frame.tag} cannot contain text"
            )
        if frame.tag == "details" and not frame.summary_seen:
            raise CurriculumValidationError(
                "invalid HTML content model: details requires summary as first child"
            )
        if frame.tag == "figure":
            frame.has_direct_content = True

    def handle_comment(self, data: str) -> None:
        del data
        raise CurriculumValidationError("HTML comments are not allowed")

    def handle_decl(self, decl: str) -> None:
        if (
            not self._generated
            or not self._document
            or self._doctype_seen
            or decl.casefold() != "doctype html"
            or self._open_tags
        ):
            raise CurriculumValidationError("HTML declarations are not allowed")
        self._doctype_seen = True

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
                f"unclosed HTML element: {self._open_tags[-1].tag}"
            )
        if self._document and not self._doctype_seen:
            raise CurriculumValidationError(
                "generated document requires an HTML doctype"
            )
        if self._generated and self._generated_controls:
            dangling = [
                target
                for target in self._label_references
                if target not in self._labelable_ids
            ]
            if dangling:
                raise CurriculumValidationError(
                    "generated label for must resolve to a labelable control"
                )
            if any(count != 1 for count in self._select_default_counts):
                raise CurriculumValidationError(
                    "generated select requires exactly one selected option"
                )
            if any(
                checked != 1
                for _, checked in self._radio_group_defaults.values()
            ):
                raise CurriculumValidationError(
                    "generated radio group requires exactly one checked input"
                )

    def _validate_content_model(self, tag: str) -> None:
        parent = self._open_tags[-1] if self._open_tags else None
        parent_tag = parent.tag if parent is not None else None

        if self._generated:
            if tag == "option" and parent_tag != "select":
                raise CurriculumValidationError(
                    "invalid HTML content model: option requires parent select"
                )
            if tag == "legend" and parent_tag != "fieldset":
                raise CurriculumValidationError(
                    "invalid HTML content model: legend requires parent fieldset"
                )
            if parent_tag == "select" and tag != "option":
                raise CurriculumValidationError(
                    "invalid HTML content model: select only allows option children"
                )
            if parent_tag in {"button", "option"}:
                raise CurriculumValidationError(
                    f"invalid HTML content model: {parent_tag} cannot contain elements"
                )

        required = _REQUIRED_PARENTS.get(tag)
        if required is not None:
            allowed_parents, message = required
            if parent_tag not in allowed_parents:
                raise CurriculumValidationError(
                    f"invalid HTML content model: {message}"
                )

        if tag == "a" and any(frame.tag == "a" for frame in self._open_tags):
            raise CurriculumValidationError(
                "invalid HTML content model: nested a"
            )

        if parent is None:
            return
        if parent.tag in _PHRASING_ONLY_CONTAINERS and tag not in _PHRASING_ELEMENTS:
            raise CurriculumValidationError(
                f"invalid HTML content model: {tag} cannot be a child of {parent.tag}"
            )
        expected_children = _STRUCTURAL_CHILDREN.get(parent.tag)
        if expected_children is not None and tag not in expected_children:
            label = _STRUCTURAL_CHILD_LABELS[parent.tag]
            raise CurriculumValidationError(
                f"invalid HTML content model: {parent.tag} only allows "
                f"{label} children"
            )

        if parent.tag == "details":
            if tag == "summary":
                if parent.summary_seen:
                    raise CurriculumValidationError(
                        "invalid HTML content model: details allows one summary"
                    )
                if parent.has_direct_content:
                    raise CurriculumValidationError(
                        "invalid HTML content model: summary must be the first "
                        "details child"
                    )
                parent.summary_seen = True
            elif not parent.summary_seen:
                raise CurriculumValidationError(
                    "invalid HTML content model: details requires summary "
                    "as first child"
                )

        if tag == "figcaption":
            if parent.figcaption_seen:
                raise CurriculumValidationError(
                    "invalid HTML content model: figure allows one figcaption"
                )
            if parent.has_direct_content:
                raise CurriculumValidationError(
                    "invalid HTML content model: figcaption must be the first "
                    "figure child"
                )
            parent.figcaption_seen = True

        if tag == "caption":
            if parent.caption_seen:
                raise CurriculumValidationError(
                    "invalid HTML content model: table allows one caption"
                )
            if parent.has_direct_content:
                raise CurriculumValidationError(
                    "invalid HTML content model: caption must be the first table child"
                )
            parent.caption_seen = True

        # The browser must build the same tree that was validated. Tracking direct
        # content prevents HTML's auto-closing/foster-parenting rules from moving it.
        parent.has_direct_content = True

    def _validate_attribute(self, tag: str, name: str, value: str) -> None:
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
            if self._generated and tag == "link":
                if value != "stylesheet":
                    raise CurriculumValidationError("invalid rel attribute")
                return
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
        elif self._generated:
            self._validate_generated_attribute(tag, name, value)

    def _validate_generated_control(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        names = {name.casefold() for name, _ in attrs}
        if tag in {"button", "fieldset", "input", "select"} and "disabled" not in names:
            raise CurriculumValidationError(
                f"generated {tag} must be disabled before enhancement"
            )
        required = {
            "button": {"type"},
            "input": {"name", "type", "value"},
            "option": {"value"},
            "select": {"id"},
        }.get(tag, set())
        if not required <= names:
            raise CurriculumValidationError(
                f"generated {tag} is missing required attributes"
            )

    def _track_generated_control(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = {name.casefold(): value for name, value in attrs}
        if tag in {"button", "input", "label", "option", "select"}:
            self._generated_control_references += 1
        if tag in {"button", "input", "select"} and values.get("id") is not None:
            self._labelable_ids.add(values["id"] or "")
        if tag == "label" and values.get("for") is not None:
            self._label_references.append(values["for"] or "")
        elif tag == "option":
            if "selected" in values:
                assert self._open_tags and self._open_tags[-1].tag == "select"
                self._open_tags[-1].selected_options += 1
        elif tag == "input":
            name = values.get("name") or ""
            total, checked = self._radio_group_defaults.get(name, (0, 0))
            self._radio_group_defaults[name] = (
                total + 1,
                checked + int("checked" in values),
            )
        if self._generated_control_references > MAX_GENERATED_CONTROL_REFERENCES:
            raise CurriculumValidationError(
                "generated controls exceed maximum reference count"
            )

    def _validate_generated_attribute(
        self,
        tag: str,
        name: str,
        value: str,
    ) -> None:
        if name == "type":
            expected = (
                {"button"}
                if tag == "button" and self._generated_controls
                else {"button", "submit"}
                if tag == "button"
                else {"radio"}
                if tag == "input" and self._generated_controls
                else {"file", "radio"}
                if tag == "input"
                else {"module"}
            )
            if value not in expected:
                raise CurriculumValidationError(f"invalid type attribute on {tag}")
        elif name == "for":
            if _ID_PATTERN.fullmatch(value) is None:
                raise CurriculumValidationError(f"invalid {name} attribute")
        elif name == "name":
            if tag == "meta":
                if value not in {"description", "viewport"}:
                    raise CurriculumValidationError("invalid name attribute")
            elif _ID_PATTERN.fullmatch(value) is None:
                raise CurriculumValidationError("invalid name attribute")
        elif name == "value":
            if (
                _ID_PATTERN.fullmatch(value) is None
                and value not in {"0.5", "1", "2", "3", "4", "5"}
            ):
                raise CurriculumValidationError("invalid value attribute")
        elif name == "lang":
            if value != "ja":
                raise CurriculumValidationError("invalid lang attribute")
        elif name == "charset":
            if value.casefold() != "utf-8":
                raise CurriculumValidationError("invalid charset attribute")
        elif name == "http-equiv":
            if value.casefold() != "content-security-policy":
                raise CurriculumValidationError("invalid http-equiv attribute")
        elif name == "aria-live":
            if value != "polite":
                raise CurriculumValidationError("invalid aria-live attribute")
        elif name == "aria-atomic":
            if value != "true":
                raise CurriculumValidationError("invalid aria-atomic attribute")
        elif name in {"aria-expanded", "aria-pressed"}:
            if value not in {"false", "true"}:
                raise CurriculumValidationError(f"invalid {name} attribute")
        elif name in {"aria-controls", "aria-describedby"}:
            if _ID_PATTERN.fullmatch(value) is None:
                raise CurriculumValidationError(f"invalid {name} attribute")
        elif name == "role":
            if value not in {"group", "img", "status"}:
                raise CurriculumValidationError("invalid role attribute")
        elif name in {"aria-label", "content"}:
            if len(value) > MAX_ATTRIBUTE_VALUE_CHARS:
                raise CurriculumValidationError(
                    "HTML attribute value exceeds maximum character count"
                )
        elif name == "src":
            _validate_url(value)
        elif name == "accept":
            if value != "application/json":
                raise CurriculumValidationError("invalid accept attribute")
        elif name.startswith("data-"):
            if name == "data-action":
                if value not in {"apply", "play", "pause", "previous", "next", "reset", "speed"}:
                    raise CurriculumValidationError("invalid generated action")
            elif name == "data-step-index" or name == "data-default-interval-ms":
                if not value.isascii() or not value.isdecimal() or not 0 <= int(value) <= 10_000:
                    raise CurriculumValidationError("invalid generated numeric data attribute")
            elif name == "data-interaction-mode":
                if value not in {"scenario", "stepper", "playback", "hybrid", "explorer"}:
                    raise CurriculumValidationError("invalid generated interaction mode")
            elif name == "data-transition-event":
                if value not in {"next", "previous", "timer", "parameter-change", "reset"}:
                    raise CurriculumValidationError("invalid generated transition event")
            elif _ID_PATTERN.fullmatch(value) is None:
                raise CurriculumValidationError("invalid generated identifier data attribute")


def _validate_url(value: str) -> None:
    # URL validation is deliberately stricter than browser parsing. Returning the
    # original fragment is safe only when obfuscated schemes cannot be reinterpreted.
    if any(character.isspace() for character in value):
        raise CurriculumValidationError("whitespace is not allowed in URLs")
    if any(unicodedata.category(character) in {"Cc", "Cf"} for character in value):
        raise CurriculumValidationError(
            "control characters are not allowed in URLs"
        )
    if "\\" in value:
        raise CurriculumValidationError("backslashes are not allowed in URLs")
    if _ENCODED_URL_CONTROL_PATTERN.search(value):
        raise CurriculumValidationError("encoded controls are not allowed in URLs")
    if value.startswith("/"):
        raise CurriculumValidationError(
            "root-relative URLs are not file-compatible"
        )

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


def _validate_html_input(
    fragment: str,
    *,
    generated: bool = False,
    document: bool = False,
    generated_controls: bool = True,
) -> None:
    if type(fragment) is not str:
        raise CurriculumValidationError("fragment must be an exact string")
    if not fragment.strip():
        raise CurriculumValidationError("fragment must not be empty")
    maximum_chars = (
        MAX_GENERATED_DOCUMENT_CHARS if document else MAX_FRAGMENT_CHARS
    )
    maximum_bytes = (
        MAX_GENERATED_DOCUMENT_BYTES if document else MAX_FRAGMENT_BYTES
    )
    if len(fragment) > maximum_chars:
        raise CurriculumValidationError(
            "fragment exceeds maximum character count"
        )
    try:
        encoded = fragment.encode("utf-8")
    except UnicodeError:
        raise CurriculumValidationError("fragment is not valid UTF-8 text") from None
    if len(encoded) > maximum_bytes:
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

    _scan_markup_syntax(fragment, generated=generated)
    parser = _FragmentParser(
        generated=generated,
        document=document,
        generated_controls=generated_controls,
    )
    try:
        parser.feed(fragment)
        parser.close()
        parser.finish()
    except CurriculumValidationError:
        raise
    except Exception:
        raise CurriculumValidationError("could not parse HTML fragment") from None


def validate_fragment(fragment: str) -> SafeHtml:
    """Validate repository-authored HTML with the strict non-interactive grammar."""
    _validate_html_input(fragment, generated=False, document=False)
    return _issue_safe_html(fragment, HtmlProvenance.AUTHORED)


def validate_generated_fragment(fragment: str) -> SafeHtml:
    """Validate renderer-owned HTML with closed, disabled native controls."""
    _validate_html_input(fragment, generated=True, document=False)
    return _issue_safe_html(fragment, HtmlProvenance.GENERATED)


def validate_generated_interactive_fragment(fragment: str) -> SafeHtml:
    """Validate renderer-owned interactive HTML without weakening authored HTML."""
    _validate_html_input(
        fragment,
        generated=True,
        document=False,
        generated_controls=False,
    )
    return _issue_safe_html(fragment, HtmlProvenance.GENERATED_INTERACTIVE)


def validate_generated_document(document: str) -> SafeHtml:
    """Validate the complete renderer output using the generated grammar."""
    _validate_html_input(document, generated=True, document=True)
    return _issue_safe_html(document, HtmlProvenance.GENERATED)


def validate_generated_interactive_document(document: str) -> SafeHtml:
    """Validate a complete renderer-owned document with active controls."""
    _validate_html_input(
        document,
        generated=True,
        document=True,
        generated_controls=False,
    )
    return _issue_safe_html(document, HtmlProvenance.GENERATED_INTERACTIVE)


def revalidate_safe_html(value: object) -> SafeHtml:
    """Revalidate exact bytes against the provenance-bearing issuing grammar."""
    if type(value) is not SafeHtml:
        raise CurriculumValidationError("raw HTML requires exact SafeHtml")
    try:
        fragment = value.value
        provenance = value.provenance
    except Exception:
        raise CurriculumValidationError(
            "raw HTML could not be revalidated"
        ) from None
    if provenance is HtmlProvenance.AUTHORED:
        return validate_fragment(fragment)
    if provenance is HtmlProvenance.GENERATED:
        return validate_generated_fragment(fragment)
    if provenance is HtmlProvenance.GENERATED_INTERACTIVE:
        return validate_generated_interactive_fragment(fragment)
    raise CurriculumValidationError("raw HTML has invalid provenance")
