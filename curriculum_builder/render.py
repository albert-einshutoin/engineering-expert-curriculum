"""Strict, file-compatible rendering for repository-authored templates."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
import os
from pathlib import Path
import re
import stat
from string import Template
from types import MappingProxyType

from .errors import CurriculumValidationError
from .html_safety import SafeHtml, validate_fragment


MAX_TEMPLATE_BYTES = 262_144
MAX_PLACEHOLDERS = 128
MAX_STRUCTURED_TEXT_CHARS = 4_096
MAX_STRUCTURED_TEXT_BYTES = 16_384
MAX_VALUE_ENTRIES = 128
MAX_OUTPUT_DEPTH = 32
MAX_OUTPUT_PATH_CHARS = 1_024

_SAFE_TEMPLATE_NAME = re.compile(
    r"[A-Za-z][A-Za-z0-9_-]{0,63}\.html",
    re.ASCII,
)
_SAFE_OUTPUT_PART = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",
    re.ASCII,
)
_SAFE_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}", re.ASCII)
_URL_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:", re.ASCII)
_VOID_ELEMENTS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta"}
)
_BASE_ATTRIBUTES = MappingProxyType(
    {
        "a": frozenset({"class", "href"}),
        "body": frozenset(),
        "footer": frozenset(),
        "head": frozenset(),
        "header": frozenset({"class"}),
        "html": frozenset({"lang"}),
        "link": frozenset({"href", "rel"}),
        "main": frozenset({"id"}),
        "meta": frozenset({"charset", "content", "http-equiv", "name"}),
        "nav": frozenset({"aria-label"}),
        "p": frozenset(),
        "title": frozenset(),
    }
)
_BASE_PLACEHOLDER_COUNTS = MappingProxyType(
    {
        "title": 1,
        "description": 1,
        "root": 5,
        "content": 1,
    }
)
_REQUIRED_CSP = MappingProxyType(
    {
        "default-src": ("'none'",),
        "script-src": ("'none'",),
        "style-src": ("'self'",),
        "img-src": ("'self'", "data:"),
        "font-src": ("'self'",),
        "connect-src": ("'none'",),
        "base-uri": ("'none'",),
        "form-action": ("'none'",),
        "object-src": ("'none'",),
        "frame-src": ("'none'",),
        "frame-ancestors": ("'none'",),
    }
)


@dataclass(frozen=True, slots=True)
class _Placeholder:
    name: str
    position: int
    context: str


def _template_identifiers(source: str) -> tuple[tuple[str, int], ...]:
    identifiers: list[tuple[str, int]] = []
    template = Template(source)
    for match in template.pattern.finditer(source):
        if match.group("escaped") is not None:
            continue
        name = match.group("named") or match.group("braced")
        if match.group("invalid") is not None or name is None:
            raise CurriculumValidationError(
                "invalid template placeholder syntax"
            )
        identifiers.append((name, match.start()))
        if len(identifiers) > MAX_PLACEHOLDERS:
            raise CurriculumValidationError(
                "template exceeds maximum placeholder count"
            )
    return tuple(identifiers)


def _tag_details(token: str) -> tuple[str | None, bool, bool]:
    match = re.match(
        r"<\s*(?P<closing>/)?\s*(?P<name>[A-Za-z][A-Za-z0-9-]*)",
        token,
        re.ASCII,
    )
    if match is None:
        return None, False, False
    return (
        match.group("name").casefold(),
        match.group("closing") is not None,
        token.rstrip().endswith("/>"),
    )


def _placeholder_contexts(
    source: str,
    identifiers: tuple[tuple[str, int], ...],
) -> tuple[_Placeholder, ...]:
    positions: dict[int, list[str]] = {}
    for name, position in identifiers:
        positions.setdefault(position, []).append(name)

    results: list[_Placeholder] = []
    state = "data"
    tag_start = -1
    open_elements: list[str] = []
    index = 0

    while index < len(source):
        for name in positions.get(index, ()):
            context = state
            if state == "data":
                context = "element-body" if open_elements else "top-level"
            results.append(
                _Placeholder(name=name, position=index, context=context)
            )

        if state == "data":
            if source.startswith("<!--", index):
                state = "comment"
                index += 4
                continue
            if source[index] == "<":
                state = "tag"
                tag_start = index
            index += 1
            continue

        if state == "comment":
            if source.startswith("-->", index):
                state = "data"
                index += 3
            else:
                index += 1
            continue

        if state in {"script", "style"}:
            closing = f"</{state}"
            if source[index : index + len(closing)].casefold() == closing:
                state = "tag"
                tag_start = index
            index += 1
            continue

        if state == "double-quoted-attribute":
            if source[index] == '"':
                state = "tag"
            index += 1
            continue

        if state == "single-quoted-attribute":
            if source[index] == "'":
                state = "tag"
            index += 1
            continue

        if source[index] == '"':
            state = "double-quoted-attribute"
            index += 1
            continue
        if source[index] == "'":
            state = "single-quoted-attribute"
            index += 1
            continue
        if source[index] != ">":
            index += 1
            continue

        token = source[tag_start : index + 1]
        name, closing, self_closing = _tag_details(token)
        if name is not None:
            if closing:
                # Requiring the stack top makes every tag a single push/pop.
                # Searching deeper would both accept browser-mutating markup and
                # reintroduce quadratic behavior for adversarial close sequences.
                if not open_elements or open_elements[-1] != name:
                    raise CurriculumValidationError(
                        "template markup is invalid"
                    )
                open_elements.pop()
            elif not self_closing and name not in _VOID_ELEMENTS:
                open_elements.append(name)
        if not closing and not self_closing and name in {"script", "style"}:
            state = name
        else:
            state = "data"
        index += 1

    if state != "data" or open_elements:
        raise CurriculumValidationError("template markup is invalid")
    return tuple(results)


def _analyze_template(source: str) -> tuple[_Placeholder, ...]:
    identifiers = _template_identifiers(source)
    return _placeholder_contexts(source, identifiers)


def _snapshot_mapping(
    value: object,
    *,
    parameter: str,
    label: str,
) -> tuple[tuple[str, object], ...]:
    if not isinstance(value, Mapping):
        raise CurriculumValidationError(f"{parameter} must be a mapping")
    try:
        raw_items = value.items()
        item_iterator = iter(raw_items)
    except Exception:
        raise CurriculumValidationError(
            f"cannot snapshot {label} values"
        ) from None

    entries: list[tuple[object, object]] = []
    for index in range(MAX_VALUE_ENTRIES + 1):
        try:
            raw_entry = next(item_iterator)
        except StopIteration:
            break
        except Exception:
            raise CurriculumValidationError(
                f"cannot snapshot {label} values"
            ) from None
        if index == MAX_VALUE_ENTRIES:
            raise CurriculumValidationError(
                f"{label} values exceed maximum entry count"
            )
        try:
            entry_iterator = iter(raw_entry)
            key = next(entry_iterator)
            entry_value = next(entry_iterator)
            try:
                next(entry_iterator)
            except StopIteration:
                pass
            else:
                raise ValueError
        except Exception:
            raise CurriculumValidationError(
                f"cannot snapshot {label} values"
            ) from None
        entries.append((key, entry_value))

    if any(type(key) is not str for key, _ in entries):
        raise CurriculumValidationError(
            f"{label} value keys must be exact strings"
        )
    keys = tuple(key for key, _ in entries if type(key) is str)
    if any(_SAFE_KEY.fullmatch(key) is None for key in keys):
        raise CurriculumValidationError(f"{label} value key is unsafe")
    duplicates = tuple(
        key for key, count in Counter(keys).items() if count > 1
    )
    if duplicates:
        raise CurriculumValidationError(f"duplicate {label} value keys")
    return tuple(
        (key, entry_value)
        for key, entry_value in entries
        if type(key) is str
    )


def _validate_structured_text(value: object, *, label: str) -> str:
    if type(value) is not str:
        raise CurriculumValidationError(f"{label} must be an exact string")
    if len(value) > MAX_STRUCTURED_TEXT_CHARS:
        raise CurriculumValidationError(
            f"{label} exceeds maximum character count"
        )
    if any(
        ord(character) < 0x20 and character not in "\t\n\r"
        for character in value
    ):
        raise CurriculumValidationError(
            f"{label} contains a disallowed control character"
        )
    try:
        encoded = value.encode("utf-8")
    except UnicodeError:
        raise CurriculumValidationError(
            f"{label} is not valid UTF-8 text"
        ) from None
    if len(encoded) > MAX_STRUCTURED_TEXT_BYTES:
        raise CurriculumValidationError(
            f"{label} exceeds maximum UTF-8 byte count"
        )
    return value


def _require_exact_safe_html(value: object) -> SafeHtml:
    if type(value) is not SafeHtml:
        raise CurriculumValidationError("raw HTML requires exact SafeHtml")
    # A frozen capability can still be forged with low-level Python APIs. Issue
    # a fresh capability so the inserted bytes are exactly those just validated.
    try:
        fragment = value.value
    except Exception:
        raise CurriculumValidationError(
            "raw HTML could not be revalidated"
        ) from None
    return validate_fragment(fragment)


def _validate_output_path(output_path: object) -> tuple[Path, int]:
    if not isinstance(output_path, Path):
        raise CurriculumValidationError(
            "output_path must be a safe relative HTML file"
        )
    rendered = str(output_path)
    if len(rendered) > MAX_OUTPUT_PATH_CHARS:
        raise CurriculumValidationError(
            "output_path must be a safe relative HTML file"
        )
    parts = output_path.parts
    if (
        output_path.is_absolute()
        or rendered in {"", "."}
        or "\x00" in rendered
        or "\\" in rendered
        or not parts
        or any(part in {"", ".", ".."} for part in parts)
        or any(_SAFE_OUTPUT_PART.fullmatch(part) is None for part in parts)
        or output_path.suffix != ".html"
        or len(parts) - 1 > MAX_OUTPUT_DEPTH
    ):
        raise CurriculumValidationError(
            "output_path must be a safe relative HTML file"
        )
    return output_path, len(parts) - 1


def _validate_fragment_name(name: object) -> str:
    if type(name) is not str or _SAFE_TEMPLATE_NAME.fullmatch(name) is None:
        raise CurriculumValidationError("fragment template name is unsafe")
    return name


def _file_stat_signature(file_stat: os.stat_result) -> tuple[int, ...]:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_mode,
        file_stat.st_size,
        file_stat.st_mtime_ns,
        file_stat.st_ctime_ns,
    )


def _validate_placeholder_contract(
    placeholders: tuple[_Placeholder, ...],
    *,
    text_keys: frozenset[str],
    html_keys: frozenset[str],
    base: bool = False,
) -> None:
    counts = Counter(placeholder.name for placeholder in placeholders)
    if base:
        if dict(counts) != _BASE_PLACEHOLDER_COUNTS:
            raise CurriculumValidationError(
                "base template placeholders do not match required counts"
            )
    else:
        if frozenset(counts) != text_keys | html_keys:
            raise CurriculumValidationError(
                "template placeholders do not match provided values"
            )

    for placeholder in placeholders:
        if base:
            if (
                placeholder.name in {"description", "root"}
                and placeholder.context
                not in {
                    "double-quoted-attribute",
                    "single-quoted-attribute",
                }
            ):
                raise CurriculumValidationError(
                    "base template placeholder context is invalid"
                )
            if (
                placeholder.name == "title"
                and placeholder.context != "element-body"
            ):
                raise CurriculumValidationError(
                    "base template placeholder context is invalid"
                )
        if placeholder.name in html_keys:
            if placeholder.context != "element-body":
                raise CurriculumValidationError(
                    "raw HTML placeholder requires element-body context"
                )
        elif placeholder.name in text_keys:
            if placeholder.context not in {
                "element-body",
                "double-quoted-attribute",
                "single-quoted-attribute",
            }:
                raise CurriculumValidationError(
                    "text placeholder requires element-text or "
                    "quoted-attribute context"
                )
    if not base and any(count != 1 for count in counts.values()):
        raise CurriculumValidationError(
            "fragment placeholders must each occur exactly once"
        )


class _BasePolicyParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.doctype_count = 0
        self.html_ja_count = 0
        self.main_count = 0
        self.skip_link_count = 0
        self.nav_count = 0
        self.csp_values: list[str] = []
        self.ids: set[str] = set()
        self.open_tags: list[str] = []
        self.head_count = 0
        self.body_count = 0
        self.head_closed = False
        self.description_placeholder_count = 0
        self.title_placeholder_count = 0
        self.hrefs: Counter[str] = Counter()
        self.stylesheet_count = 0
        self.meta_counts: Counter[str] = Counter()

    def handle_decl(self, decl: str) -> None:
        if decl.strip().casefold() != "doctype html":
            raise CurriculumValidationError("base template markup is invalid")
        self.doctype_count += 1

    def handle_comment(self, data: str) -> None:
        del data
        raise CurriculumValidationError("base template markup is invalid")

    def handle_pi(self, data: str) -> None:
        del data
        raise CurriculumValidationError("base template markup is invalid")

    def unknown_decl(self, data: str) -> None:
        del data
        raise CurriculumValidationError("base template markup is invalid")

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag not in _BASE_ATTRIBUTES:
            raise CurriculumValidationError("base template markup is invalid")
        if normalized_tag == "html":
            if self.open_tags or self.doctype_count != 1:
                raise CurriculumValidationError("base template markup is invalid")
        elif normalized_tag == "head":
            if self.open_tags != ["html"] or self.head_count:
                raise CurriculumValidationError("base template markup is invalid")
            self.head_count += 1
        elif normalized_tag == "body":
            if (
                self.open_tags != ["html"]
                or not self.head_closed
                or self.body_count
            ):
                raise CurriculumValidationError("base template markup is invalid")
            self.body_count += 1
        elif not self.open_tags:
            raise CurriculumValidationError("base template markup is invalid")
        if (
            normalized_tag in {"link", "meta", "title"}
            and self.open_tags != ["html", "head"]
        ):
            raise CurriculumValidationError("base template markup is invalid")
        if (
            normalized_tag
            in {"a", "footer", "header", "main", "nav"}
            and "body" not in self.open_tags
        ):
            raise CurriculumValidationError("base template markup is invalid")

        names = tuple(name.casefold() for name, _ in attrs)
        if len(names) != len(set(names)):
            raise CurriculumValidationError("base template markup is invalid")
        if any(value is None for _, value in attrs):
            raise CurriculumValidationError("base template markup is invalid")
        if any(name not in _BASE_ATTRIBUTES[normalized_tag] for name in names):
            raise CurriculumValidationError("base template markup is invalid")
        if any(name.startswith("on") or name in {"style", "srcdoc"} for name in names):
            raise CurriculumValidationError("base template markup is invalid")
        attributes = {
            name.casefold(): value
            for name, value in attrs
            if value is not None
        }
        if normalized_tag == "meta":
            if attributes == {"charset": "utf-8"}:
                meta_kind = "charset"
            elif attributes == {
                "name": "viewport",
                "content": "width=device-width, initial-scale=1",
            }:
                meta_kind = "viewport"
            elif attributes == {
                "name": "description",
                "content": "$description",
            }:
                meta_kind = "description"
            elif (
                frozenset(attributes) == {"http-equiv", "content"}
                and attributes["http-equiv"] == "Content-Security-Policy"
            ):
                meta_kind = "csp"
            else:
                raise CurriculumValidationError(
                    "base template markup is invalid"
                )
            self.meta_counts[meta_kind] += 1
            if self.meta_counts[meta_kind] > 1:
                raise CurriculumValidationError(
                    "base template markup is invalid"
                )

        if normalized_tag == "html" and attributes.get("lang") == "ja":
            self.html_ja_count += 1
        if normalized_tag == "main" and attributes.get("id") == "main":
            self.main_count += 1
        if normalized_tag == "nav" and attributes.get("aria-label"):
            self.nav_count += 1
        if (
            normalized_tag == "a"
            and "skip-link" in attributes.get("class", "").split()
            and attributes.get("href") == "#main"
        ):
            self.skip_link_count += 1

        identifier = attributes.get("id")
        if identifier is not None:
            if identifier in self.ids:
                raise CurriculumValidationError("base template markup is invalid")
            self.ids.add(identifier)

        if (
            normalized_tag == "meta"
            and attributes.get("http-equiv", "").casefold()
            == "content-security-policy"
        ):
            content = attributes.get("content")
            if content is None:
                raise CurriculumValidationError("base template CSP is incomplete")
            self.csp_values.append(content)
        if (
            normalized_tag == "meta"
            and attributes.get("name", "").casefold() == "description"
            and attributes.get("content") == "$description"
        ):
            self.description_placeholder_count += 1
        if (
            normalized_tag == "link"
            and attributes.get("rel") == "stylesheet"
            and attributes.get("href") == "${root}styles.css"
        ):
            self.stylesheet_count += 1

        for attribute_name in ("href", "src"):
            target = attributes.get(attribute_name)
            if target is None or target.startswith("#"):
                if attribute_name == "href" and target is not None:
                    self.hrefs[target] += 1
                continue
            lowered = target.casefold()
            if (
                target.startswith("/")
                or "\\" in target
                or "://" in lowered
                or _URL_SCHEME.match(target) is not None
            ):
                raise CurriculumValidationError(
                    "base template contains an external or absolute asset URL"
                )
            if attribute_name == "href":
                self.hrefs[target] += 1
        if normalized_tag not in _VOID_ELEMENTS:
            self.open_tags.append(normalized_tag)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() not in _VOID_ELEMENTS:
            raise CurriculumValidationError("base template markup is invalid")
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        if not self.open_tags or self.open_tags[-1] != normalized_tag:
            raise CurriculumValidationError("base template markup is invalid")
        self.open_tags.pop()
        if normalized_tag == "head":
            self.head_closed = True

    def handle_data(self, data: str) -> None:
        if not self.open_tags and data.strip():
            raise CurriculumValidationError("base template markup is invalid")
        if self.open_tags and self.open_tags[-1] == "title":
            self.title_placeholder_count += data.count("$title")


def _parse_csp(value: str) -> dict[str, tuple[str, ...]]:
    directives: dict[str, tuple[str, ...]] = {}
    for raw_directive in value.split(";"):
        parts = raw_directive.split()
        if not parts:
            continue
        name = parts[0].casefold()
        if name in directives:
            raise CurriculumValidationError("base template CSP is incomplete")
        directives[name] = tuple(parts[1:])
    return directives


def _validate_base_policy(source: str) -> None:
    if source.count('<main id="main">$content</main>') != 1:
        raise CurriculumValidationError("base template markup is invalid")
    parser = _BasePolicyParser()
    try:
        parser.feed(source)
        parser.close()
    except CurriculumValidationError:
        raise
    except Exception:
        raise CurriculumValidationError(
            "could not validate base template"
        ) from None

    if (
        parser.doctype_count != 1
        or parser.html_ja_count != 1
        or parser.main_count != 1
        or parser.skip_link_count != 1
        or parser.nav_count != 1
        or parser.head_count != 1
        or parser.body_count != 1
        or parser.open_tags
        or parser.description_placeholder_count != 1
        or parser.title_placeholder_count != 1
        or parser.stylesheet_count != 1
        or parser.meta_counts
        != Counter(
            {
                "charset": 1,
                "viewport": 1,
                "description": 1,
                "csp": 1,
            }
        )
    ):
        raise CurriculumValidationError("base template markup is invalid")
    required_hrefs = Counter(
        {
            "#main": 1,
            "${root}styles.css": 1,
            "${root}index.html": 1,
            "${root}roadmap/index.html": 1,
            "${root}lessons/index.html": 1,
            "${root}catalog/index.html": 1,
        }
    )
    if parser.hrefs != required_hrefs:
        raise CurriculumValidationError("base template markup is invalid")
    if len(parser.csp_values) != 1:
        raise CurriculumValidationError("base template CSP is incomplete")
    directives = _parse_csp(parser.csp_values[0])
    if directives != _REQUIRED_CSP:
        raise CurriculumValidationError("base template CSP is incomplete")


class _DocumentIdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ids: set[str] = set()

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del tag
        for name, value in attrs:
            if name.casefold() != "id" or value is None:
                continue
            if value in self._ids:
                raise CurriculumValidationError("duplicate rendered HTML id")
            self._ids.add(value)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)


def _reject_duplicate_document_ids(document: str) -> None:
    parser = _DocumentIdParser()
    try:
        parser.feed(document)
        parser.close()
    except CurriculumValidationError:
        raise
    except Exception:
        raise CurriculumValidationError(
            "could not parse rendered HTML document"
        ) from None


class Renderer:
    """Render validated fragments into deterministic static HTML documents."""

    def __init__(self, template_root: Path) -> None:
        if not isinstance(template_root, Path):
            raise CurriculumValidationError(
                "template_root must be a real directory"
            )
        try:
            root_stat = template_root.lstat()
        except OSError:
            raise CurriculumValidationError(
                "template_root must be a real directory"
            ) from None
        if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
            raise CurriculumValidationError(
                "template_root must be a real directory"
            )
        try:
            self._template_root = template_root.resolve(strict=True)
        except OSError:
            raise CurriculumValidationError(
                "template_root must be a real directory"
            ) from None
        self._template_root_identity = (root_stat.st_dev, root_stat.st_ino)

        base_source = self._read_template("base.html")
        base_placeholders = _analyze_template(base_source)
        _validate_placeholder_contract(
            base_placeholders,
            text_keys=frozenset({"title", "description", "root"}),
            html_keys=frozenset({"content"}),
            base=True,
        )
        _validate_base_policy(base_source)
        self._base = Template(base_source)

    def page(
        self,
        *,
        output_path: Path,
        title: str,
        description: str,
        content: SafeHtml,
    ) -> str:
        _, depth = _validate_output_path(output_path)
        validated_title = _validate_structured_text(title, label="title")
        validated_description = _validate_structured_text(
            description,
            label="description",
        )
        root = "../" * depth
        safe_content = _require_exact_safe_html(content)
        try:
            document = self._base.substitute(
                title=escape(validated_title, quote=True),
                description=escape(validated_description, quote=True),
                root=root,
                content=safe_content.value,
            )
        except (KeyError, ValueError):
            raise CurriculumValidationError(
                "base template substitution failed"
            ) from None
        _reject_duplicate_document_ids(document)
        return document

    def fragment(
        self,
        name: str,
        *,
        text_values: Mapping[str, str],
        html_values: Mapping[str, SafeHtml],
    ) -> SafeHtml:
        validated_name = _validate_fragment_name(name)
        source = self._read_template(validated_name)
        placeholders = _analyze_template(source)
        text_entries = _snapshot_mapping(
            text_values,
            parameter="text_values",
            label="text",
        )
        html_entries = _snapshot_mapping(
            html_values,
            parameter="html_values",
            label="raw HTML",
        )
        text_keys = frozenset(key for key, _ in text_entries)
        html_keys = frozenset(key for key, _ in html_entries)
        if text_keys & html_keys:
            raise CurriculumValidationError(
                "text and raw HTML keys must be disjoint"
            )

        validated_text: dict[str, str] = {}
        for key, value in text_entries:
            validated_text[key] = _validate_structured_text(
                value,
                label="text value",
            )
        for _, value in html_entries:
            if type(value) is not SafeHtml:
                raise CurriculumValidationError(
                    "raw HTML requires exact SafeHtml"
                )

        _validate_placeholder_contract(
            placeholders,
            text_keys=text_keys,
            html_keys=html_keys,
        )

        values = {
            key: escape(value, quote=True)
            for key, value in validated_text.items()
        }
        # Revalidation happens after template analysis and immediately before
        # substitution, minimizing the stale-capability window.
        values.update(
            {
                key: _require_exact_safe_html(value).value
                for key, value in html_entries
            }
        )
        try:
            rendered = Template(source).substitute(values)
        except (KeyError, ValueError):
            raise CurriculumValidationError(
                "template substitution failed"
            ) from None
        return validate_fragment(rendered)

    def _read_template(self, name: str) -> str:
        common_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        no_follow = getattr(os, "O_NOFOLLOW", 0)
        root_flags = common_flags | no_follow | getattr(os, "O_DIRECTORY", 0)
        file_flags = common_flags | no_follow | getattr(os, "O_NONBLOCK", 0)
        root_descriptor: int | None = None
        file_descriptor: int | None = None
        read_failed = False
        chunks: list[bytes] = []
        try:
            root_descriptor = os.open(self._template_root, root_flags)
            opened_root = os.fstat(root_descriptor)
            if (
                not stat.S_ISDIR(opened_root.st_mode)
                or (opened_root.st_dev, opened_root.st_ino)
                != self._template_root_identity
            ):
                raise CurriculumValidationError(
                    "template_root changed during rendering"
                )
            before = os.stat(
                name,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
            if stat.S_ISLNK(before.st_mode):
                raise CurriculumValidationError(
                    "template symlinks are not allowed"
                )
            if not stat.S_ISREG(before.st_mode):
                raise CurriculumValidationError(
                    "template must be a regular file"
                )
            if before.st_size > MAX_TEMPLATE_BYTES:
                raise CurriculumValidationError(
                    "template exceeds maximum byte count"
                )

            file_descriptor = os.open(
                name,
                file_flags,
                dir_fd=root_descriptor,
            )
            opened = os.fstat(file_descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or _file_stat_signature(opened)
                != _file_stat_signature(before)
            ):
                raise CurriculumValidationError(
                    "template changed during read"
                )
            remaining = opened.st_size
            while remaining:
                chunk = os.read(
                    file_descriptor,
                    min(65_536, remaining),
                )
                if not chunk:
                    raise CurriculumValidationError(
                        "template changed during read"
                    )
                if len(chunk) > remaining:
                    raise CurriculumValidationError(
                        "template changed during read"
                    )
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(file_descriptor, 1):
                raise CurriculumValidationError(
                    "template changed during read"
                )
            after = os.fstat(file_descriptor)
            if (
                not stat.S_ISREG(after.st_mode)
                or _file_stat_signature(after)
                != _file_stat_signature(opened)
            ):
                raise CurriculumValidationError(
                    "template changed during read"
                )
        except CurriculumValidationError:
            raise
        except OSError:
            read_failed = True
        finally:
            if file_descriptor is not None:
                try:
                    os.close(file_descriptor)
                except OSError:
                    read_failed = True
            if root_descriptor is not None:
                try:
                    os.close(root_descriptor)
                except OSError:
                    read_failed = True
        if read_failed:
            raise CurriculumValidationError("could not read template")

        try:
            return b"".join(chunks).decode("utf-8")
        except UnicodeError:
            raise CurriculumValidationError(
                "template is not valid UTF-8 text"
            ) from None
