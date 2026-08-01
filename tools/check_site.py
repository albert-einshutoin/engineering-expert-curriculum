#!/usr/bin/env python3
"""Fail closed when a generated static curriculum site is unsafe or incomplete."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from html.parser import HTMLParser
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Final, Iterable
from urllib.parse import unquote_to_bytes, urlsplit


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    # The checker is both imported by tests and executed as ``python tools/...``.
    # Normalize the import root so both entry paths share the production CSS
    # validator instead of maintaining a security-sensitive duplicate.
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from curriculum_builder.css_safety import validate_stylesheet_bytes  # noqa: E402
from curriculum_builder.errors import CurriculumValidationError  # noqa: E402


MAX_ISSUES: Final = 64
MAX_FILES: Final = 4_096
MAX_DEPTH: Final = 32
MAX_HTML_BYTES: Final = 4 * 1024 * 1024
MAX_CSS_BYTES: Final = 1024 * 1024
MAX_VISUALIZATION_CSS_BYTES: Final = 80 * 1024
MAX_DIAGNOSTIC_VALUE_CHARS: Final = 160

REQUIRED_CSP: Final = (
    "default-src 'none'; script-src 'none'; style-src 'self'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'none'; "
    "base-uri 'none'; form-action 'none'; object-src 'none'; "
    "frame-src 'none'"
)

_LESSON_IDS: Final = (
    "core-01-systems-tradeoffs",
    "core-02-algorithms-measurement",
    "core-03-architecture-memory-caches",
    "core-04-os-processes-concurrency",
    "core-05-networks-latency-failure",
    "core-06-requirements-domain-modeling",
    "core-07-api-contract-design",
    "core-08-modularity-evolutionary-architecture",
    "core-09-test-strategy-tdd",
    "core-10-threat-modeling-secure-design",
    "core-11-data-modeling-storage",
    "core-12-transactions-isolation-consistency",
    "core-13-distributed-coordination-failure",
    "core-14-performance-capacity",
    "core-15-reliability-observability-slo",
    "core-16-hci-usability-accessibility",
    "core-17-graphics-visual-information",
    "core-18-product-discovery-experiments",
    "core-19-technical-communication-design-docs",
    "core-20-ethics-privacy-societal-impact",
    "core-21-maintenance-legacy-comprehension",
    "core-22-evolution-safe-migrations",
    "core-23-incident-response-learning",
    "core-24-delivery-ci-release-safety",
    "core-25-engineering-economics-capacity",
    "core-26-code-review-collaborative-quality",
    "core-27-team-interfaces-sociotechnical-architecture",
    "core-28-oss-governance-stewardship",
    "core-29-cross-cultural-async-collaboration",
    "core-30-evidence-based-technical-leadership",
)
_CAPSTONE_IDS: Final = (
    "global-service",
    "legacy-evolution",
    "oss-launch",
)
_BASE_INVENTORY: Final = frozenset(
    {
        "index.html",
        "styles.css",
        "static/visualizations.css",
        "catalog/index.html",
        "competencies/index.html",
        "capstones/index.html",
        "roadmap/index.html",
        "lessons/index.html",
    }
)
CURRENT_RELEASE_INVENTORY: Final = frozenset(
    _BASE_INVENTORY
    | {f"lessons/{lesson_id}/index.html" for lesson_id in _LESSON_IDS}
    | {f"capstones/{capstone_id}/index.html" for capstone_id in _CAPSTONE_IDS}
)

_ALLOWED_SUFFIXES: Final = frozenset({".html", ".css"})
_VOID_ELEMENTS: Final = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)
_FORBIDDEN_ELEMENTS: Final = frozenset(
    {"base", "embed", "form", "iframe", "object", "script", "style"}
)
_RESOURCE_ELEMENTS: Final = frozenset(
    {"audio", "img", "source", "track", "video"}
)
_START_TAG = re.compile(
    r"<\s*[A-Za-z][A-Za-z0-9:-]*"
    r"(?:\s+[A-Za-z_:][A-Za-z0-9_.:-]*"
    r"(?:\s*=\s*(?:\"[^\"<>]*\"|'[^'<>]*'))?)*\s*/?>\Z",
    re.ASCII | re.DOTALL,
)
_END_TAG = re.compile(
    r"</\s*[A-Za-z][A-Za-z0-9:-]*\s*>\Z",
    re.ASCII,
)
_DOCTYPE = re.compile(r"<!doctype\s+html\s*>\Z", re.ASCII | re.IGNORECASE)
_PERCENT_ESCAPE = re.compile(r"%(?:[0-9A-Fa-f]{2})")


class SiteValidationError(ValueError):
    """The checker API received an invalid or contradictory contract."""


def _safe_value(value: object) -> str:
    raw = str(value)
    visible = raw.encode("unicode_escape", "backslashreplace").decode("ascii")
    if len(visible) <= MAX_DIAGNOSTIC_VALUE_CHARS:
        return visible
    return visible[: MAX_DIAGNOSTIC_VALUE_CHARS - 3] + "..."


class _Issues:
    def __init__(self) -> None:
        self._items: list[str] = []
        self._omitted = 0

    def add(self, relative: PurePosixPath | None, message: str) -> None:
        prefix = "site root" if relative is None else _safe_value(relative.as_posix())
        issue = f"{prefix}: {message}"
        if len(self._items) < MAX_ISSUES:
            self._items.append(issue)
        else:
            self._omitted += 1

    def result(self) -> list[str]:
        result = list(self._items)
        if self._omitted:
            result.append(f"site: {self._omitted} additional issues omitted")
        return result


@dataclass(frozen=True, slots=True)
class _LocalReference:
    source: PurePosixPath
    raw: str
    fragment: str | None
    role: str


@dataclass(slots=True)
class _Page:
    ids: set[str]
    references: list[_LocalReference]


@dataclass(slots=True)
class _Tree:
    files: dict[PurePosixPath, bytes]
    directories: set[PurePosixPath]
    discovered: set[PurePosixPath]


@dataclass(frozen=True, slots=True)
class _FileRead:
    source: bytes | None
    close_failed: bool


def _scan_markup_syntax(document: str) -> None:
    cursor = 0
    while True:
        opening = document.find("<", cursor)
        if opening < 0:
            return
        if document.startswith("<!--", opening):
            closing = document.find("-->", opening + 4)
            if closing < 0 or "--" in document[opening + 4 : closing]:
                raise SiteValidationError("malformed HTML comment")
            cursor = closing + 3
            continue

        quote: str | None = None
        closing = opening + 1
        while closing < len(document):
            character = document[closing]
            if quote is None:
                if character in {'"', "'"}:
                    quote = character
                elif character == ">":
                    break
            elif character == quote:
                quote = None
            closing += 1
        if closing == len(document):
            raise SiteValidationError("malformed HTML markup")
        token = document[opening : closing + 1]
        if token.startswith("</"):
            valid = _END_TAG.fullmatch(token) is not None
        elif token.lower().startswith("<!doctype"):
            valid = _DOCTYPE.fullmatch(token) is not None
        elif token.startswith("<!") or token.startswith("<?"):
            valid = False
        else:
            valid = _START_TAG.fullmatch(token) is not None
        if not valid:
            raise SiteValidationError("malformed HTML markup")
        cursor = closing + 1


class _PageParser(HTMLParser):
    def __init__(
        self,
        relative: PurePosixPath,
        issues: _Issues,
        document: str,
    ) -> None:
        super().__init__(convert_charrefs=True)
        self.relative = relative
        self.issues = issues
        self.document = document
        # HTMLParser increments its line counter only for LF.  Generic
        # splitlines() also treats lone CR as a newline, which would make byte
        # security boundaries disagree with the parser's reported position.
        self.line_start_offsets = [0]
        self.line_start_offsets.extend(
            index + 1 for index, character in enumerate(document) if character == "\n"
        )
        self.stack: list[str] = []
        self.ids: set[str] = set()
        self.references: list[_LocalReference] = []
        self.html_langs: list[str] = []
        self.title_count = 0
        self.title_parts: list[str] = []
        self.title_depth = 0
        self.main_count = 0
        self.main_ids: list[str | None] = []
        self.heading_levels: list[int] = []
        self.heading_parts: list[list[str]] = []
        self.open_heading: int | None = None
        self.skip_targets: list[str | None] = []
        self.charset_values: list[str] = []
        self.charset_locations: list[bool] = []
        self.head_count = 0
        self.head_depth = 0
        self.csp_values: list[str] = []
        self.stylesheet_count = 0
        self.stylesheet_hrefs: list[str] = []
        self.doctype_count = 0
        self.malformed = False

    def _malformed(self) -> None:
        if not self.malformed:
            self.issues.add(self.relative, "malformed HTML")
        self.malformed = True

    def _current_tag_end_byte(self) -> int:
        line_number, column = self.getpos()
        tag_start = self.line_start_offsets[line_number - 1] + column
        raw_tag = self.get_starttag_text() or ""
        return len(self.document[:tag_start].encode("utf-8")) + len(
            raw_tag.encode("utf-8")
        )

    def handle_decl(self, decl: str) -> None:
        if decl.casefold().strip() != "doctype html":
            self._malformed()
        self.doctype_count += 1

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)
        if tag.casefold() not in _VOID_ELEMENTS:
            self.handle_endtag(tag)

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        tag = tag.casefold()
        names = [name.casefold() for name, _ in attrs]
        if len(names) != len(set(names)):
            self._malformed()
        values: dict[str, str | None] = {}
        for name, value in attrs:
            values.setdefault(name.casefold(), value)
        if tag in _FORBIDDEN_ELEMENTS:
            self.issues.add(self.relative, f"{tag} is forbidden")
        aria_hidden = (
            (values.get("aria-hidden") or "").strip().casefold() == "true"
        )
        closed_disclosure = tag in {"details", "dialog"} and "open" not in values
        if (
            tag == "template"
            or "hidden" in values
            or "inert" in values
            or aria_hidden
            or closed_disclosure
        ):
            # The release contract must describe the rendered accessibility
            # tree. Counting required landmarks inside inert DOM would turn a
            # visually empty document into a false success.
            self.issues.add(self.relative, "inert content is forbidden")
        for name in names:
            if name == "style" or name.startswith("on"):
                self.issues.add(
                    self.relative,
                    f"inline {name} attribute is forbidden",
                )
        if "ping" in values:
            self.issues.add(self.relative, "ping contains an unsafe URL")
        if "background" in values:
            self._record_url(values.get("background"), "resource", set())
        if tag not in _RESOURCE_ELEMENTS:
            if "src" in values:
                self._record_url(values.get("src"), "resource", set())
            if "poster" in values:
                self._record_url(values.get("poster"), "resource", set())
            if "srcset" in values:
                self.issues.add(self.relative, "srcset contains an unsafe URL")
        if tag not in {"a", "link"} and "href" in values:
            self._record_url(values.get("href"), "resource", set())
        for attribute in ("action", "formaction", "manifest", "xlink:href"):
            if attribute in values:
                self._record_url(values.get(attribute), "resource", set())

        identifier = values.get("id")
        if identifier is not None:
            if not identifier or identifier in self.ids:
                self.issues.add(self.relative, "duplicate id or empty id")
            else:
                self.ids.add(identifier)

        if tag == "head":
            self.head_count += 1
            self.head_depth += 1

        if tag == "html":
            self.html_langs.append(values.get("lang") or "")
        elif tag == "title":
            self.title_count += 1
            self.title_depth += 1
        elif tag == "main":
            self.main_count += 1
            self.main_ids.append(identifier)
        elif len(tag) == 2 and tag[0] == "h" and tag[1] in "123456":
            if self.open_heading is not None:
                self._malformed()
            self.heading_levels.append(int(tag[1]))
            self.heading_parts.append([])
            self.open_heading = len(self.heading_parts) - 1
        elif tag == "meta":
            if "charset" in values:
                self.charset_values.append(
                    (values.get("charset") or "").casefold()
                )
                # HTML encoding declarations are effective only inside head and
                # when their complete tag occurs within the first 1024 bytes.
                self.charset_locations.append(
                    self.head_depth == 1
                    and self._current_tag_end_byte() <= 1024
                )
            http_equiv = (values.get("http-equiv") or "").strip().casefold()
            if http_equiv == "refresh":
                self.issues.add(self.relative, "meta refresh is forbidden")
            elif http_equiv == "content-security-policy":
                self.csp_values.append(values.get("content") or "")
        elif tag == "link":
            rel = _rel_tokens(values.get("rel"))
            if rel != {"stylesheet"}:
                self.issues.add(
                    self.relative,
                    "only a local stylesheet link is allowed",
                )
            else:
                if (
                    self.head_depth != 1
                    or not self.stack
                    or self.stack[-1] != "head"
                ):
                    self.issues.add(
                        self.relative,
                        "stylesheet must be a direct child of head",
                    )
                self.stylesheet_count += 1
                self.stylesheet_hrefs.append(values.get("href") or "")
            self._record_url(values.get("href"), "stylesheet", rel)
        elif tag == "a":
            href = values.get("href")
            classes = set((values.get("class") or "").split())
            if "skip-link" in classes:
                self.skip_targets.append(href)
            self._record_url(href, "anchor", _rel_tokens(values.get("rel")))
        elif tag in _RESOURCE_ELEMENTS:
            self._record_url(values.get("src"), "resource", set())
            if values.get("poster") is not None:
                self._record_url(values.get("poster"), "resource", set())
            if values.get("srcset") is not None:
                self.issues.add(self.relative, "srcset contains an unsafe URL")

        if tag not in _VOID_ELEMENTS:
            self.stack.append(tag)

    def _record_url(
        self,
        raw: str | None,
        role: str,
        rel: set[str],
    ) -> None:
        if raw is None or not raw:
            self.issues.add(self.relative, f"{role} URL is missing")
            return
        if raw != raw.strip() or any(ord(character) < 0x20 for character in raw):
            self.issues.add(self.relative, f"{role} contains an unsafe URL")
            return
        try:
            parsed = urlsplit(raw)
            port = parsed.port
        except ValueError:
            self.issues.add(self.relative, f"{role} contains an unsafe URL")
            return
        scheme = parsed.scheme.casefold()
        if scheme == "file":
            self.issues.add(self.relative, "file URL creates a root escape")
            return
        if scheme in {"data", "javascript"}:
            self.issues.add(self.relative, f"{role} contains an unsafe URL")
            return
        if scheme or parsed.netloc:
            if role != "anchor":
                self.issues.add(self.relative, f"{role} uses a remote resource")
                return
            if scheme != "https" or not parsed.hostname:
                self.issues.add(self.relative, "external link must use HTTPS")
                return
            if parsed.username is not None or parsed.password is not None:
                self.issues.add(self.relative, "external link contains credentials")
            if parsed.netloc.endswith(":") or (
                port is not None and not 1 <= port <= 65_535
            ):
                self.issues.add(self.relative, "external link contains an unsafe port")
            if "noreferrer" not in rel:
                self.issues.add(self.relative, "external link requires rel noreferrer")
            return
        try:
            decoded_path = _decode_url_component(parsed.path)
            decoded_fragment = (
                _decode_url_component(parsed.fragment)
                if parsed.fragment or raw.endswith("#")
                else None
            )
        except SiteValidationError:
            self.issues.add(self.relative, f"{role} contains an unsafe URL")
            return
        if "\\" in decoded_path or "\x00" in decoded_path:
            self.issues.add(self.relative, f"{role} contains an unsafe URL")
            return
        self.references.append(
            _LocalReference(
                source=self.relative,
                raw=raw,
                fragment=decoded_fragment,
                role=role,
            )
        )

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in _VOID_ELEMENTS or not self.stack or self.stack[-1] != tag:
            self._malformed()
            return
        self.stack.pop()
        if tag == "title":
            self.title_depth -= 1
        elif tag == "head":
            self.head_depth -= 1
        elif len(tag) == 2 and tag[0] == "h" and tag[1] in "123456":
            self.open_heading = None

    def handle_data(self, data: str) -> None:
        if self.title_depth:
            self.title_parts.append(data)
        if self.open_heading is not None:
            self.heading_parts[self.open_heading].append(data)

    def finish(self) -> _Page:
        if self.stack or self.doctype_count != 1:
            self._malformed()
        if self.html_langs != ["ja"]:
            self.issues.add(self.relative, "html lang must be ja")
        if self.title_count != 1 or not "".join(self.title_parts).strip():
            self.issues.add(self.relative, "title must be present exactly once")
        if self.main_count != 1:
            self.issues.add(self.relative, "page must contain exactly one main")
        if self.heading_levels.count(1) != 1:
            self.issues.add(self.relative, "page must contain exactly one h1")
        if any(not "".join(parts).strip() for parts in self.heading_parts):
            self.issues.add(self.relative, "heading text must not be empty")
        if self.heading_levels and self.heading_levels[0] != 1:
            self.issues.add(self.relative, "heading hierarchy must begin with h1")
        if any(
            current > previous + 1
            for previous, current in zip(
                self.heading_levels,
                self.heading_levels[1:],
            )
        ):
            self.issues.add(self.relative, "heading hierarchy must not skip levels")
        if len(self.skip_targets) != 1:
            self.issues.add(self.relative, "page must contain exactly one skip link")
        elif self.main_count == 1:
            main_id = self.main_ids[0]
            expected_target = f"#{main_id}" if main_id else None
            if self.skip_targets[0] != expected_target:
                self.issues.add(
                    self.relative,
                    "skip link target must be the main element id",
                )
        if (
            self.head_count != 1
            or self.charset_values != ["utf-8"]
            or self.charset_locations != [True]
        ):
            self.issues.add(
                self.relative,
                "charset must be declared exactly once as utf-8",
            )
        if self.csp_values != [REQUIRED_CSP]:
            self.issues.add(self.relative, "CSP must match the exact safe contract")
        root = "../" * len(self.relative.parent.parts)
        expected_stylesheets = [
            f"{root}styles.css",
            f"{root}static/visualizations.css",
        ]
        if self.stylesheet_hrefs != expected_stylesheets:
            self.issues.add(
                self.relative,
                "page must contain exactly two ordered local stylesheets",
            )
        return _Page(ids=self.ids, references=self.references)


def _rel_tokens(value: str | None) -> set[str]:
    return {token.casefold() for token in (value or "").split() if token}


def _decode_url_component(value: str) -> str:
    without_escapes = _PERCENT_ESCAPE.sub("", value)
    if "%" in without_escapes:
        raise SiteValidationError("invalid URL escape")
    try:
        return unquote_to_bytes(value).decode("utf-8")
    except UnicodeDecodeError:
        raise SiteValidationError("invalid URL encoding") from None


def _read_regular_file(
    directory_fd: int,
    name: str,
    expected: os.stat_result,
    maximum: int,
) -> _FileRead:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError:
        return _FileRead(source=None, close_failed=False)

    source: bytes | None = None
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_dev != expected.st_dev
            or before.st_ino != expected.st_ino
            or before.st_nlink != 1
        ):
            source = None
        else:
            chunks: list[bytes] = []
            consumed = 0
            while True:
                chunk = os.read(
                    descriptor,
                    min(64 * 1024, maximum + 1 - consumed),
                )
                if not chunk:
                    break
                chunks.append(chunk)
                consumed += len(chunk)
                if consumed > maximum:
                    break
            after = os.fstat(descriptor)
            if consumed <= maximum and (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            ) == (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                source = b"".join(chunks)
    except OSError:
        source = None

    close_failed = False
    try:
        # close(2) has an ambiguous error contract, so never retry it. The
        # separate flag lets the caller report teardown failure without hiding
        # an earlier read or identity failure.
        os.close(descriptor)
    except OSError:
        close_failed = True
    return _FileRead(source=source, close_failed=close_failed)


def _scan_tree(root: Path, issues: _Issues) -> _Tree | None:
    try:
        root_status = os.lstat(root)
    except (OSError, ValueError):
        issues.add(None, "does not exist or cannot be inspected")
        return None
    if stat.S_ISLNK(root_status.st_mode):
        issues.add(None, "must not be a symbolic link")
        return None
    if not stat.S_ISDIR(root_status.st_mode):
        issues.add(None, "must be a directory")
        return None
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        root_fd = os.open(root, flags)
    except OSError:
        issues.add(None, "cannot be opened safely")
        return None
    try:
        opened_root = os.fstat(root_fd)
    except OSError:
        try:
            os.close(root_fd)
        except OSError:
            pass
        issues.add(None, "cannot be inspected safely")
        return None
    if (
        opened_root.st_dev != root_status.st_dev
        or opened_root.st_ino != root_status.st_ino
    ):
        try:
            os.close(root_fd)
        except OSError:
            pass
        issues.add(None, "changed while being opened")
        return None

    tree = _Tree(files={}, directories={PurePosixPath(".")}, discovered=set())
    entry_count = 0

    def visit(directory_fd: int, relative: PurePosixPath, depth: int) -> None:
        nonlocal entry_count
        if depth > MAX_DEPTH:
            issues.add(relative, "directory nesting exceeds the safe limit")
            return
        try:
            entries = sorted(os.scandir(directory_fd), key=lambda item: item.name)
        except OSError:
            issues.add(relative, "directory cannot be inspected safely")
            return
        for entry in entries:
            entry_count += 1
            child = (
                relative / entry.name
                if relative.parts
                else PurePosixPath(entry.name)
            )
            if entry_count > MAX_FILES:
                issues.add(None, "entry count exceeds the safe limit")
                return
            try:
                status = entry.stat(follow_symlinks=False)
            except OSError:
                issues.add(child, "entry cannot be inspected safely")
                continue
            tree.discovered.add(child)
            if stat.S_ISLNK(status.st_mode):
                issues.add(child, "symbolic links are forbidden")
                continue
            if stat.S_ISDIR(status.st_mode):
                tree.directories.add(child)
                try:
                    child_fd = os.open(entry.name, flags, dir_fd=directory_fd)
                except OSError:
                    issues.add(child, "directory cannot be opened safely")
                    continue
                try:
                    try:
                        opened_child = os.fstat(child_fd)
                    except OSError:
                        issues.add(child, "directory cannot be inspected safely")
                        continue
                    if (
                        opened_child.st_dev != status.st_dev
                        or opened_child.st_ino != status.st_ino
                    ):
                        issues.add(child, "directory changed while being opened")
                        continue
                    # Holding every ancestor fd and opening each child with
                    # O_NOFOLLOW keeps traversal confined even if names race.
                    visit(child_fd, child, depth + 1)
                finally:
                    try:
                        os.close(child_fd)
                    except OSError:
                        issues.add(child, "directory could not be closed safely")
                continue
            if not stat.S_ISREG(status.st_mode):
                issues.add(child, "static artifacts must be regular files")
                continue
            if status.st_nlink != 1:
                # A hard link lets bytes be mutated through a pathname outside
                # the reviewed tree, so immutable release evidence needs nlink 1.
                issues.add(child, "hard links are forbidden")
                continue
            suffix = child.suffix.casefold()
            if suffix not in _ALLOWED_SUFFIXES:
                issues.add(child, "disallowed static file type")
                continue
            if suffix == ".html":
                maximum = MAX_HTML_BYTES
            elif child == PurePosixPath("static/visualizations.css"):
                maximum = MAX_VISUALIZATION_CSS_BYTES
            else:
                maximum = MAX_CSS_BYTES
            result = _read_regular_file(directory_fd, entry.name, status, maximum)
            if result.source is None:
                issues.add(child, "file is too large, unstable, or unreadable")
            if result.close_failed:
                issues.add(child, "file could not be closed safely")
            if result.source is None or result.close_failed:
                continue
            tree.files[child] = result.source

    try:
        visit(root_fd, PurePosixPath(), 0)
    finally:
        try:
            os.close(root_fd)
        except OSError:
            issues.add(None, "root directory could not be closed safely")
    if not tree.discovered:
        issues.add(None, "site is empty")
    return tree


def _validate_css(relative: PurePosixPath, source: bytes, issues: _Issues) -> None:
    # The generated artifact and its source stylesheet need one byte-level
    # policy. Sharing the validator prevents comment-obfuscation rules from
    # drifting between build time and publication time.
    try:
        validate_stylesheet_bytes(source)
    except CurriculumValidationError:
        issues.add(relative, "CSS violates the local-only stylesheet contract")


def _validate_html(
    relative: PurePosixPath,
    source: bytes,
    issues: _Issues,
) -> _Page | None:
    if not source:
        issues.add(relative, "HTML must not be empty")
        return None
    try:
        document = source.decode("utf-8")
    except UnicodeDecodeError:
        issues.add(relative, "HTML must be valid UTF-8")
        return None
    try:
        _scan_markup_syntax(document)
    except SiteValidationError:
        issues.add(relative, "malformed HTML")
        return None
    parser = _PageParser(relative, issues, document)
    try:
        parser.feed(document)
        parser.close()
    except Exception:
        issues.add(relative, "malformed HTML")
        return None
    return parser.finish()


def _resolve_reference(
    reference: _LocalReference,
    files: set[PurePosixPath],
    directories: set[PurePosixPath],
    pages: dict[PurePosixPath, _Page],
    issues: _Issues,
) -> None:
    parsed = urlsplit(reference.raw)
    try:
        decoded_path = _decode_url_component(parsed.path)
    except SiteValidationError:
        return

    # Resolve lexically instead of Path.resolve(): the latter could accept an
    # existing target outside root before the checker notices the escape.
    parts = list(reference.source.parent.parts)
    escaped = decoded_path.startswith("/")
    for part in decoded_path.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            else:
                escaped = True
        else:
            parts.append(part)
    if escaped:
        issues.add(reference.source, f"root escape in URL {_safe_value(reference.raw)}")
        return
    target = PurePosixPath(*parts) if parts else reference.source
    if not decoded_path:
        target = reference.source
    if target in directories:
        target /= "index.html"
    elif target not in files and target / "index.html" in files:
        target /= "index.html"
    if target not in files:
        issues.add(
            reference.source,
            f"missing local target {_safe_value(reference.raw)}",
        )
        return
    if reference.role == "stylesheet" and target.suffix.casefold() != ".css":
        issues.add(reference.source, "stylesheet target must be local CSS")
    fragment = reference.fragment
    if fragment is not None:
        if not fragment:
            issues.add(reference.source, "empty fragment is forbidden")
        elif target not in pages or fragment not in pages[target].ids:
            issues.add(
                reference.source,
                f"missing fragment {_safe_value(fragment)}",
            )


def _normalize_inventory(values: Iterable[str | PurePosixPath]) -> frozenset[str]:
    if isinstance(values, (str, bytes)):
        raise SiteValidationError(
            "expected_entrypoints must be an iterable of paths"
        )
    normalized: set[str] = set()
    try:
        candidates = tuple(values)
    except TypeError:
        raise SiteValidationError(
            "expected_entrypoints must be an iterable of paths"
        ) from None
    for candidate in candidates:
        if not isinstance(candidate, (str, PurePosixPath)):
            raise SiteValidationError(
                "expected entrypoint must be a relative POSIX path"
            )
        raw = str(candidate)
        path = PurePosixPath(raw)
        if (
            not raw
            or "\\" in raw
            or path.is_absolute()
            or raw != path.as_posix()
            or any(part in {"", ".", ".."} for part in path.parts)
            or "?" in raw
            or "#" in raw
            or path.suffix.casefold() not in _ALLOWED_SUFFIXES
        ):
            raise SiteValidationError(
                "expected entrypoint must be a safe relative artifact path"
            )
        normalized.add(path.as_posix())
    if not normalized:
        raise SiteValidationError("expected_entrypoints must not be empty")
    return frozenset(normalized)


def check_site(
    root: Path,
    *,
    expected_entrypoints: Iterable[str | PurePosixPath] | None = None,
    require_current_release: bool = False,
) -> list[str]:
    """Return bounded release issues, or raise for an invalid API contract."""
    if not isinstance(root, Path):
        raise SiteValidationError("root must be a pathlib.Path")
    if expected_entrypoints is not None and require_current_release:
        raise SiteValidationError("choose one exact inventory contract")
    expected = (
        CURRENT_RELEASE_INVENTORY
        if require_current_release
        else (
            _normalize_inventory(expected_entrypoints)
            if expected_entrypoints is not None
            else None
        )
    )
    issues = _Issues()
    tree = _scan_tree(root, issues)
    if tree is None:
        return issues.result()

    pages: dict[PurePosixPath, _Page] = {}
    for relative, source in sorted(tree.files.items()):
        if relative.suffix.casefold() == ".css":
            _validate_css(relative, source, issues)
        else:
            page = _validate_html(relative, source, issues)
            if page is not None:
                pages[relative] = page

    files = set(tree.files)
    for page in pages.values():
        for reference in page.references:
            _resolve_reference(reference, files, tree.directories, pages, issues)

    if expected is not None:
        actual = {path.as_posix() for path in tree.discovered if path in tree.files}
        for missing in sorted(expected - actual):
            issues.add(PurePosixPath(missing), "missing expected entrypoint")
        for unexpected in sorted(actual - expected):
            issues.add(PurePosixPath(unexpected), "unexpected entrypoint")
    return issues.result()


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="generated site root")
    inventory = parser.add_mutually_exclusive_group()
    inventory.add_argument(
        "--require-current-release",
        action="store_true",
        help="require the exact current 41-artifact release inventory",
    )
    inventory.add_argument(
        "--expected-entrypoint",
        action="append",
        default=None,
        help="require this exact artifact path (repeat for the complete inventory)",
    )
    return parser


def main(arguments: list[str] | None = None) -> int:
    options = _argument_parser().parse_args(arguments)
    try:
        issues = check_site(
            Path(options.root),
            expected_entrypoints=options.expected_entrypoint,
            require_current_release=options.require_current_release,
        )
    except SiteValidationError as error:
        print(f"site check configuration error: {_safe_value(error)}", file=sys.stderr)
        return 2
    except Exception:
        print("site check failed safely", file=sys.stderr)
        return 2
    for issue in issues:
        print(issue, file=sys.stderr)
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
