"""Fail-closed orchestration for the dependency-free static curriculum site."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
import ctypes
from dataclasses import dataclass
import errno
from enum import Enum, auto
from html import escape
from html.parser import HTMLParser
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import sys
from typing import Final
import uuid

from .catalog import (
    load_catalog_bytes,
    load_repository_catalog_bytes,
    strict_json_loads,
)
from .errors import CurriculumValidationError
from .graph import topological_stages
from .html_safety import SafeHtml, validate_fragment
from .models import CatalogItem
from .render import MAX_TEMPLATE_BYTES, Renderer


MAX_CATALOG_BYTES: Final = 8 * 1024 * 1024
MAX_ROADMAP_BYTES: Final = 256 * 1024
MAX_STYLESHEET_BYTES: Final = 1024 * 1024
MAX_ROADMAP_NODES: Final = 4096
MAX_ROADMAP_EDGES: Final = 65_536
MAX_ROADMAP_TEXT_CHARS: Final = 4096
MAX_OUTPUT_BASENAME_CHARS: Final = 128
_READ_CHUNK_SIZE: Final = 64 * 1024
_DETERMINISTIC_MTIME_NS: Final = 0
_STAGING_ATTEMPTS: Final = 16
_HTML_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}", re.ASCII)
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_REPOSITORY_CONTENT_ROOT = (_REPOSITORY_ROOT / "content").resolve(strict=True)
_TEMPLATE_NAMES = (
    "base.html",
    "index.html",
    "catalog.html",
    "roadmap.html",
    "lessons.html",
)
_EXPECTED_ARTIFACTS = frozenset(
    {
        PurePosixPath("index.html"),
        PurePosixPath("styles.css"),
        PurePosixPath("catalog/index.html"),
        PurePosixPath("roadmap/index.html"),
        PurePosixPath("lessons/index.html"),
    }
)


class BuildPostCommitError(RuntimeError):
    """A native rename committed the new site before a later operation failed."""


class BuildPublicationDurabilityError(BuildPostCommitError):
    """The new site is visible, but its parent-directory fsync failed."""


class BuildCleanupError(BuildPostCommitError):
    """The new site is visible, but the replaced output could not be removed."""


class BuildPublicationStateError(BuildPostCommitError):
    """The new site is visible, but post-commit state could not be verified."""


class BuildStagingCleanupError(RuntimeError):
    """Publication did not commit and private staging could not be removed."""


class _PublishInputError(ValueError):
    """Publication was rejected before invoking the native rename."""


class _PublishConflictError(FileExistsError):
    """The native rename reported a conflict without committing."""


class _PublishRuntimeError(RuntimeError):
    """Publication capability or syscall state failed without committing."""


class _PublishOSError(OSError):
    """The native rename returned an operating-system failure."""


_DEFINITELY_NOT_PUBLISHED = (
    _PublishInputError,
    _PublishConflictError,
    _PublishRuntimeError,
    _PublishOSError,
)


class _BuildPhase(Enum):
    PREPARING = auto()
    PUBLISHED = auto()
    PUBLICATION_UNKNOWN = auto()


class _PublicationEvidence(Enum):
    NOT_PUBLISHED = auto()
    PUBLISHED = auto()
    UNKNOWN = auto()


@dataclass(slots=True)
class _BuildTransaction:
    """Share the native publication commit state through root-FD teardown."""

    phase: _BuildPhase = _BuildPhase.PREPARING

    @property
    def publication_may_have_committed(self) -> bool:
        return self.phase is not _BuildPhase.PREPARING

    def mark_published(self) -> None:
        self.phase = _BuildPhase.PUBLISHED

    def mark_publication_unknown(self) -> None:
        self.phase = _BuildPhase.PUBLICATION_UNKNOWN

    def mark_not_published(self) -> None:
        self.phase = _BuildPhase.PREPARING


@dataclass(frozen=True, slots=True)
class _DirectoryHandle:
    path: Path
    descriptor: int
    identity: tuple[int, int]
    label: str


@dataclass(frozen=True, slots=True)
class _RoadmapNode:
    id: str
    title: str
    prerequisites: tuple[str, ...]


@dataclass(slots=True)
class _StagingReservation:
    name: str
    descriptor: int | None = None
    identity: tuple[int, int] | None = None
    descriptor_verified: bool = False


@dataclass(frozen=True, slots=True)
class _EntryObservation:
    inspected: bool
    identity: tuple[int, int] | None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class _PublicationReconciliation:
    evidence: _PublicationEvidence
    notes: tuple[str, ...] = ()


def _validation(message: str) -> CurriculumValidationError:
    return CurriculumValidationError(message)


def _path_argument(path: object, label: str) -> Path:
    if not isinstance(path, Path):
        raise _validation(f"{label} must be a Path")
    if "\0" in os.fspath(path):
        raise _validation(f"{label} contains a NUL byte")
    if ".." in path.parts:
        # Resolving a/b/../content can cross a symlink before `..` is applied.
        # Rejecting the spelling also prevents the official catalog from being
        # misclassified as an injected fixture through ambiguous comparison.
        raise _validation(f"{label} contains ambiguous parent traversal")
    return path if path.is_absolute() else Path.cwd() / path


def _validate_existing_components(path: Path, label: str) -> None:
    current = Path(path.anchor)
    parts = path.parts[1:]
    for index, part in enumerate(parts):
        current /= part
        try:
            node = os.lstat(current)
        except FileNotFoundError:
            raise _validation(f"{label} does not exist") from None
        except OSError:
            raise _validation(f"{label} cannot be inspected") from None
        if stat.S_ISLNK(node.st_mode):
            raise _validation(f"{label} contains a symbolic link")
        if index != len(parts) - 1 and not stat.S_ISDIR(node.st_mode):
            raise _validation(f"{label} parent is not a directory")


def _identity(value: os.stat_result) -> tuple[int, int]:
    return value.st_dev, value.st_ino


def _stat_signature(
    value: os.stat_result,
) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        stat.S_IFMT(value.st_mode),
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _require_owned_safe_node(
    value: os.stat_result,
    label: str,
    *,
    directory: bool,
) -> None:
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    kind = "directory" if directory else "regular file"
    if not expected(value.st_mode):
        raise _validation(f"{label} must be a {kind}")
    if hasattr(os, "geteuid") and value.st_uid != os.geteuid():
        raise _validation(f"{label} must be owned by the current user")
    if value.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise _validation(f"{label} must not be group/world writable")


@contextmanager
def _open_trusted_directory(
    path: Path,
    label: str,
    transaction: _BuildTransaction | None = None,
) -> Iterator[_DirectoryHandle]:
    raw = _path_argument(path, label)
    _validate_existing_components(raw, label)
    try:
        recorded = os.lstat(raw)
    except OSError:
        raise _validation(f"{label} cannot be inspected") from None
    _require_owned_safe_node(recorded, label, directory=True)
    try:
        canonical = raw.resolve(strict=True)
    except OSError:
        raise _validation(f"{label} cannot be resolved") from None
    if not hasattr(os, "O_NOFOLLOW"):
        raise _validation("safe directory descriptors are not supported")
    flags = (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(canonical, flags)
    except OSError:
        raise _validation(f"{label} cannot be opened safely") from None
    handle: _DirectoryHandle | None = None
    try:
        opened = os.fstat(descriptor)
        _require_owned_safe_node(opened, label, directory=True)
        if _identity(recorded) != _identity(opened):
            raise _validation(f"{label} changed while opening")
        handle = _DirectoryHandle(
            path=canonical,
            descriptor=descriptor,
            identity=_identity(opened),
            label=label,
        )
        yield handle
    except BaseException as operation_error:
        if handle is not None:
            try:
                _verify_directory_identity(handle)
            except BaseException as binding_error:
                operation_error.add_note(
                    f"{label} pathname binding also changed: "
                    f"{binding_error}"
                )
        try:
            os.close(descriptor)
        except OSError as close_error:
            operation_error.add_note(
                f"{label} descriptor also failed to close: {close_error}"
            )
        if (
            transaction is not None
            and transaction.publication_may_have_committed
            and not isinstance(operation_error, BuildPostCommitError)
        ):
            normalized = BuildPublicationStateError(
                "site is visible but build root teardown failed"
            )
            for note in getattr(operation_error, "__notes__", ()):
                normalized.add_note(note)
            raise normalized from operation_error
        raise
    else:
        teardown_error: BaseException | None = None
        assert handle is not None
        try:
            _verify_directory_identity(handle)
        except BaseException as error:
            teardown_error = error
        try:
            os.close(descriptor)
        except OSError as close_error:
            if teardown_error is not None:
                teardown_error.add_note(
                    f"{label} descriptor also failed to close: "
                    f"{close_error}"
                )
            elif (
                transaction is not None
                and transaction.publication_may_have_committed
            ):
                raise BuildPublicationStateError(
                    "site is visible but "
                    f"{label} descriptor close failed"
                ) from close_error
            else:
                raise RuntimeError(
                    f"{label} descriptor close failed: {close_error}"
                ) from close_error
        if teardown_error is not None:
            if (
                transaction is not None
                and transaction.publication_may_have_committed
            ):
                normalized = BuildPublicationStateError(
                    "publication may have committed but "
                    "build root pathname binding changed"
                )
                for note in getattr(teardown_error, "__notes__", ()):
                    normalized.add_note(note)
                raise normalized from teardown_error
            raise teardown_error


def _verify_directory_identity(handle: _DirectoryHandle) -> None:
    try:
        current = os.fstat(handle.descriptor)
        _validate_existing_components(handle.path, handle.label)
        path_node = os.lstat(handle.path)
        resolved = handle.path.resolve(strict=True)
        resolved_node = os.lstat(resolved)
    except (OSError, CurriculumValidationError):
        raise _validation(f"{handle.label} cannot be revalidated") from None
    for node in (current, path_node, resolved_node):
        try:
            _require_owned_safe_node(
                node,
                handle.label,
                directory=True,
            )
        except CurriculumValidationError:
            raise _validation(
                f"{handle.label} changed during build"
            ) from None
    # Persistent pathname rebinding is detectable, but a same-euid writer can
    # move and restore a namespace between checks. Builds therefore require an
    # exclusive workspace/namespace; the pathname checks are detection, not a
    # portable atomic rename predicate.
    if (
        resolved != handle.path
        or _identity(current) != handle.identity
        or _identity(path_node) != handle.identity
        or _identity(resolved_node) != handle.identity
    ):
        raise _validation(f"{handle.label} changed during build")


def _read_stable_regular_file(
    directory: _DirectoryHandle,
    name: str,
    maximum_bytes: int,
) -> bytes:
    if (
        not name
        or name in {".", ".."}
        or "/" in name
        or "\0" in name
    ):
        raise _validation("input file name must be a basename")
    label = f"{directory.label}/{name}"
    flags = (
        os.O_RDONLY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor: int | None = None
    try:
        before = os.stat(
            name,
            dir_fd=directory.descriptor,
            follow_symlinks=False,
        )
        _require_owned_safe_node(before, label, directory=False)
        if before.st_size > maximum_bytes:
            raise _validation(f"{name} exceeds maximum byte count")
        descriptor = os.open(
            name,
            flags,
            dir_fd=directory.descriptor,
        )
        opened = os.fstat(descriptor)
        _require_owned_safe_node(opened, label, directory=False)
        if _stat_signature(opened) != _stat_signature(before):
            raise _validation(f"{name} changed during read")
        remaining = opened.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(
                descriptor,
                min(_READ_CHUNK_SIZE, remaining),
            )
            if not chunk or len(chunk) > remaining:
                raise _validation(f"{name} changed during read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise _validation(f"{name} changed during read")
        after = os.fstat(descriptor)
        if _stat_signature(after) != _stat_signature(opened):
            raise _validation(f"{name} changed during read")
        current = os.stat(
            name,
            dir_fd=directory.descriptor,
            follow_symlinks=False,
        )
        if _stat_signature(current) != _stat_signature(opened):
            raise _validation(f"{name} changed during read")
        return b"".join(chunks)
    except CurriculumValidationError:
        raise
    except OSError:
        raise _validation(f"{name} cannot be read safely") from None
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as close_error:
                active = sys.exception()
                if active is None:
                    raise RuntimeError(
                        f"{name} descriptor close failed: {close_error}"
                    ) from close_error
                raise RuntimeError(
                    f"{name} descriptor close failed: {close_error}"
                ) from active


def _load_catalog_from_root(
    content: _DirectoryHandle,
) -> tuple[CatalogItem, ...]:
    before = _read_stable_regular_file(
        content,
        "catalog.json",
        MAX_CATALOG_BYTES,
    )
    catalog_path = content.path / "catalog.json"
    if content.path == _REPOSITORY_CONTENT_ROOT:
        items = load_repository_catalog_bytes(before, catalog_path)
    else:
        items = load_catalog_bytes(before, catalog_path)
    after = _read_stable_regular_file(
        content,
        "catalog.json",
        MAX_CATALOG_BYTES,
    )
    if before != after:
        raise _validation("catalog.json changed during build")
    return items


def _exact_fields(
    value: Mapping[object, object],
    expected: frozenset[str],
    label: str,
) -> None:
    if any(type(key) is not str for key in value):
        raise _validation(f"{label} field names must be strings")
    if frozenset(value) != expected:
        raise _validation(
            f"{label} fields must be exactly {', '.join(sorted(expected))}"
        )


def _load_roadmap(content: _DirectoryHandle) -> tuple[_RoadmapNode, ...]:
    raw = _read_stable_regular_file(
        content,
        "roadmap.json",
        MAX_ROADMAP_BYTES,
    )
    document = strict_json_loads(raw, content.path / "roadmap.json")
    if not isinstance(document, Mapping):
        raise _validation("roadmap root must be an object")
    _exact_fields(
        document,
        frozenset({"version", "nodes"}),
        "roadmap root",
    )
    if type(document["version"]) is not int or document["version"] != 1:
        raise _validation("roadmap version must be integer 1")
    raw_nodes = document["nodes"]
    if type(raw_nodes) is not list:
        raise _validation("roadmap nodes must be a list")
    if not raw_nodes:
        raise _validation("roadmap nodes must not be empty")
    if len(raw_nodes) > MAX_ROADMAP_NODES:
        raise _validation("roadmap exceeds maximum node count")

    nodes: list[_RoadmapNode] = []
    edge_count = 0
    for index, value in enumerate(raw_nodes):
        if not isinstance(value, Mapping):
            raise _validation(f"roadmap node {index} must be an object")
        _exact_fields(
            value,
            frozenset({"id", "title", "prerequisites"}),
            f"roadmap node {index}",
        )
        node_id = value["id"]
        title = value["title"]
        raw_prerequisites = value["prerequisites"]
        if type(node_id) is not str:
            raise _validation(f"roadmap node {index} id must be a string")
        if type(title) is not str:
            raise _validation(f"roadmap node {index} title must be a string")
        if (
            not title
            or title != title.strip()
            or len(title) > MAX_ROADMAP_TEXT_CHARS
        ):
            raise _validation(
                f"roadmap node {index} title must be non-empty, unpadded, "
                "and bounded"
            )
        if type(raw_prerequisites) is not list:
            raise _validation(
                f"roadmap node {index} prerequisites must be a list"
            )
        edge_count += len(raw_prerequisites)
        if edge_count > MAX_ROADMAP_EDGES:
            raise _validation("roadmap exceeds maximum prerequisite count")
        nodes.append(
            _RoadmapNode(
                id=node_id,
                title=title,
                prerequisites=tuple(raw_prerequisites),
            )
        )

    ids = tuple(node.id for node in nodes)
    prerequisites = {
        node.id: node.prerequisites
        for node in nodes
    }
    stages = topological_stages(ids, prerequisites)
    by_id = {node.id: node for node in nodes}
    ordered = tuple(by_id[node_id] for stage in stages for node_id in stage)
    if len(ordered) != len(nodes):
        raise _validation("roadmap topological ordering is incomplete")
    return ordered


def _safe_id(value: str) -> str:
    candidate = value.lower()
    if _HTML_ID.fullmatch(candidate) is None:
        raise _validation("catalog item cannot form a safe HTML id")
    return candidate


def _catalog_content(items: Sequence[CatalogItem]) -> SafeHtml:
    grouped: dict[tuple[int, str], list[CatalogItem]] = defaultdict(list)
    used_ids: set[str] = set()
    for item in items:
        identifier = _safe_id(item.id)
        if identifier == "main" or identifier in used_ids:
            raise _validation("catalog HTML ids must be unique")
        used_ids.add(identifier)
        grouped[(item.domain_id, item.domain_title)].append(item)

    sections: list[str] = []
    for (_, domain_title), domain_items in sorted(grouped.items()):
        entries = "".join(
            f'<li id="{_safe_id(item.id)}">'
            f"<strong>{escape(item.title, quote=False)}</strong>"
            f"{escape(item.outcome, quote=False)}</li>"
            for item in domain_items
        )
        sections.append(
            '<section class="catalog-card">'
            '<h2 class="catalog-card__title">'
            f"{escape(domain_title, quote=False)}</h2>"
            '<ol class="catalog-card__list">'
            f"{entries}</ol></section>"
        )
    # Dynamic values are escaped first, then the complete fragment is checked
    # against the structural HTML allowlist before it becomes a capability.
    return validate_fragment("".join(sections))


def _roadmap_content(
    renderer: Renderer,
    nodes: Sequence[_RoadmapNode],
) -> SafeHtml:
    title_by_id = {node.id: node.title for node in nodes}
    rendered: list[str] = []
    for node in nodes:
        prerequisite_text = (
            "、".join(
                title_by_id[prerequisite]
                for prerequisite in node.prerequisites
            )
            or "なし"
        )
        rendered.append(
            '<li class="learning-stage">'
            f"<h2>{escape(node.title, quote=False)}</h2>"
            '<p class="prerequisite-text"><strong>前提:</strong> '
            f"{escape(prerequisite_text, quote=False)}</p></li>"
        )
    stages = validate_fragment(
        '<ol class="learning-path">' + "".join(rendered) + "</ol>"
    )
    return renderer.fragment(
        "roadmap.html",
        text_values={},
        html_values={"stages": stages},
    )


class _SiteDocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.has_csp = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        lowered_tag = tag.casefold()
        if lowered_tag == "script":
            raise _validation("generated site must not contain scripts")
        normalized: dict[str, str | None] = {}
        for name, value in attrs:
            lowered_name = name.casefold()
            if lowered_name.startswith("on"):
                raise _validation(
                    "generated site must not contain event attributes"
                )
            normalized[lowered_name] = value
            if lowered_name == "id" and value is not None:
                if value in self.ids:
                    raise _validation("generated page contains duplicate ids")
                self.ids.add(value)
            if lowered_name == "href" and value is not None:
                self.links.append(value)
            if lowered_name in {"href", "src", "action", "formaction"}:
                candidate = value or ""
                lowered_value = candidate.casefold()
                if (
                    "://" in candidate
                    or candidate.startswith(("/", "\\", "//"))
                    or lowered_value.startswith(
                        (
                            "data:",
                            "javascript:",
                            "vbscript:",
                            "file:",
                        )
                    )
                ):
                    raise _validation(
                        "generated site URLs must be relative and local"
                    )
        if (
            lowered_tag == "meta"
            and (normalized.get("http-equiv") or "").casefold()
            == "content-security-policy"
        ):
            self.has_csp = True

    handle_startendtag = handle_starttag


def _validate_site_artifacts(
    artifacts: Mapping[PurePosixPath, bytes],
) -> None:
    if frozenset(artifacts) != _EXPECTED_ARTIFACTS:
        raise _validation("generated site artifact set is incomplete")
    ids_by_page: dict[PurePosixPath, set[str]] = {}
    links_by_page: dict[PurePosixPath, list[str]] = {}
    for path, raw in sorted(artifacts.items()):
        if path.suffix != ".html":
            continue
        try:
            document = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise _validation("generated HTML must be UTF-8") from None
        parser = _SiteDocumentParser()
        try:
            parser.feed(document)
            parser.close()
        except CurriculumValidationError:
            raise
        except Exception:
            raise _validation("generated HTML cannot be parsed") from None
        if not parser.has_csp:
            raise _validation("generated page is missing CSP")
        ids_by_page[path] = parser.ids
        links_by_page[path] = parser.links

    for page, links in links_by_page.items():
        for link in links:
            path_part, separator, fragment = link.partition("#")
            if not path_part:
                target = page
            else:
                normalized = posixpath.normpath(
                    posixpath.join(str(page.parent), path_part)
                )
                target = PurePosixPath(normalized)
            if (
                target.is_absolute()
                or ".." in target.parts
                or target not in artifacts
            ):
                raise _validation(
                    "generated page contains a missing internal link"
                )
            if separator and (
                not fragment or fragment not in ids_by_page.get(target, set())
            ):
                raise _validation(
                    "generated page contains a missing fragment link"
                )


def _render_artifacts(
    items: tuple[CatalogItem, ...],
    roadmap: tuple[_RoadmapNode, ...],
    template_sources: Mapping[str, bytes],
    stylesheet: bytes,
) -> dict[PurePosixPath, bytes]:
    renderer = Renderer.from_template_bytes(
        template_sources,
        expected_names=frozenset(_TEMPLATE_NAMES),
    )
    home = renderer.fragment(
        "index.html",
        text_values={},
        html_values={},
    )
    catalog = renderer.fragment(
        "catalog.html",
        text_values={"count": f"{len(items):,}"},
        html_values={"sections": _catalog_content(items)},
    )
    lessons = renderer.fragment(
        "lessons.html",
        text_values={},
        html_values={},
    )
    pages = {
        PurePosixPath("index.html"): renderer.page(
            output_path=Path("index.html"),
            title="世界で通用するエンジニアリングを学ぶ",
            description=(
                "学び、実践し、説明し、成果で証明する静的OSS教科書"
            ),
            content=home,
        ),
        PurePosixPath("catalog/index.html"): renderer.page(
            output_path=Path("catalog/index.html"),
            title="全カタログ",
            description=f"{len(items):,}項目のエンジニアリング知識地図",
            content=catalog,
        ),
        PurePosixPath("roadmap/index.html"): renderer.page(
            output_path=Path("roadmap/index.html"),
            title="学習ロードマップ",
            description=(
                "前提から実践、運用、リーダーシップへ進む学習経路"
            ),
            content=_roadmap_content(renderer, roadmap),
        ),
        PurePosixPath("lessons/index.html"): renderer.page(
            output_path=Path("lessons/index.html"),
            title="コアレッスン",
            description="実践教材へつながるコアレッスン索引",
            content=lessons,
        ),
    }
    artifacts = {
        path: document.encode("utf-8")
        for path, document in pages.items()
    }
    artifacts[PurePosixPath("styles.css")] = stylesheet
    _validate_site_artifacts(artifacts)
    return artifacts


def _output_basename(output_root: Path) -> tuple[Path, str]:
    raw = _path_argument(output_root, "output_root")
    name = raw.name
    if (
        not name
        or name in {".", ".."}
        or "/" in name
        or "\0" in name
        or len(name) > MAX_OUTPUT_BASENAME_CHARS
    ):
        raise _validation("output_root must end in a bounded basename")
    return raw.parent, name


def _is_relative_to(path: Path, ancestor: Path) -> bool:
    try:
        path.relative_to(ancestor)
    except ValueError:
        return False
    return True


def _validate_no_source_overlap(
    candidate: Path,
    sources: Sequence[Path],
) -> None:
    for source in sources:
        if _is_relative_to(candidate, source) or _is_relative_to(
            source,
            candidate,
        ):
            raise _validation("output_root overlaps source roots")


def _output_state(
    parent: _DirectoryHandle,
    name: str,
) -> os.stat_result | None:
    try:
        current = os.stat(
            name,
            dir_fd=parent.descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return None
    except OSError:
        raise _validation(
            "output_root must be a real directory or absent"
        ) from None
    if stat.S_ISLNK(current.st_mode) or not stat.S_ISDIR(current.st_mode):
        raise _validation(
            "output_root must be a real directory or absent"
        )
    _require_owned_safe_node(current, "output_root", directory=True)
    return current


def _reject_stale_backup(
    parent: _DirectoryHandle,
    output_name: str,
) -> None:
    backup_name = f"{output_name}.previous"
    try:
        os.stat(
            backup_name,
            dir_fd=parent.descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    except OSError:
        raise _validation("stale build backup cannot be inspected") from None
    raise _validation(f"stale build backup exists: {backup_name}")


def _open_directory_at(parent_fd: int, name: str) -> int:
    return os.open(
        name,
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0),
        dir_fd=parent_fd,
    )


def _create_private_staging(
    parent: _DirectoryHandle,
    output_name: str,
) -> _StagingReservation:
    for _ in range(_STAGING_ATTEMPTS):
        name = f".{output_name}.staging-{uuid.uuid4().hex}"
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent.descriptor)
        except FileExistsError:
            continue
        except OSError:
            raise _validation("private staging cannot be created") from None
        return _StagingReservation(name=name)
    raise _validation("private staging name collisions exceeded retry limit")


def _initialize_private_staging(
    parent: _DirectoryHandle,
    reservation: _StagingReservation,
) -> None:
    recorded = os.stat(
        reservation.name,
        dir_fd=parent.descriptor,
        follow_symlinks=False,
    )
    reservation.identity = _identity(recorded)
    reservation.descriptor = _open_directory_at(
        parent.descriptor,
        reservation.name,
    )
    opened = os.fstat(reservation.descriptor)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or _identity(opened) != reservation.identity
    ):
        raise RuntimeError("private staging changed while opening")
    reservation.descriptor_verified = True
    with os.scandir(reservation.descriptor) as entries:
        if next(entries, None) is not None:
            raise RuntimeError("private staging is not empty")


def _cleanup_staging_before_publish(
    parent: _DirectoryHandle,
    reservation: _StagingReservation,
    primary_error: BaseException,
) -> BuildStagingCleanupError | None:
    """Try removal and close independently; never follow an unverified entry."""
    cleanup_failures: list[str] = []
    removal_failure: BaseException | None = None
    try:
        if reservation.identity is None:
            raise RuntimeError("private staging identity was not recorded")
        current = os.stat(
            reservation.name,
            dir_fd=parent.descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(current.st_mode)
            or _identity(current) != reservation.identity
        ):
            raise RuntimeError(
                "private staging entry was replaced; refusing cleanup"
            )
        if (
            reservation.descriptor is not None
            and reservation.descriptor_verified
        ):
            _clear_directory_fd(reservation.descriptor)
        os.rmdir(reservation.name, dir_fd=parent.descriptor)
    except BaseException as error:
        removal_failure = error
        cleanup_failures.append(f"staging removal failed: {error}")

    descriptor = reservation.descriptor
    reservation.descriptor = None
    if descriptor is not None:
        try:
            os.close(descriptor)
        except OSError as error:
            cleanup_failures.append(f"staging close failed: {error}")

    residual = True
    try:
        current = os.stat(
            reservation.name,
            dir_fd=parent.descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        residual = False
    except OSError as error:
        cleanup_failures.append(
            f"staging residual inspection failed: {error}"
        )
    else:
        if (
            reservation.identity is not None
            and _identity(current) != reservation.identity
        ):
            cleanup_failures.append(
                "staging residual has an unexpected identity"
            )

    for failure in cleanup_failures:
        primary_error.add_note(failure)
    if not residual:
        return None
    cleanup_error = BuildStagingCleanupError(
        "private staging remains after failed initialization or build"
    )
    for failure in cleanup_failures:
        cleanup_error.add_note(failure)
    if removal_failure is None:
        cleanup_error.add_note("private staging could not be proven absent")
    return cleanup_error


def _write_all(descriptor: int, raw: bytes) -> None:
    view = memoryview(raw)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]


def _write_file_at(
    directory_fd: int,
    name: str,
    raw: bytes,
) -> None:
    descriptor = os.open(
        name,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0),
        0o600,
        dir_fd=directory_fd,
    )
    operation_error: BaseException | None = None
    try:
        _write_all(descriptor, raw)
        os.fchmod(descriptor, 0o644)
        os.utime(
            descriptor,
            ns=(
                _DETERMINISTIC_MTIME_NS,
                _DETERMINISTIC_MTIME_NS,
            ),
        )
        os.fsync(descriptor)
    except BaseException as error:
        operation_error = error
        raise
    finally:
        try:
            os.close(descriptor)
        except OSError as close_error:
            if operation_error is None:
                raise
            raise RuntimeError(
                f"generated file descriptor close failed: {close_error}"
            ) from operation_error


def _finish_directory(descriptor: int) -> None:
    os.fchmod(descriptor, 0o755)
    os.utime(
        descriptor,
        ns=(
            _DETERMINISTIC_MTIME_NS,
            _DETERMINISTIC_MTIME_NS,
        ),
    )
    os.fsync(descriptor)


def _populate_staging(
    staging_fd: int,
    artifacts: Mapping[PurePosixPath, bytes],
) -> None:
    child_descriptors: dict[str, int] = {}
    try:
        for directory in ("catalog", "lessons", "roadmap"):
            os.mkdir(directory, mode=0o700, dir_fd=staging_fd)
            child_descriptors[directory] = _open_directory_at(
                staging_fd,
                directory,
            )
        for path, raw in sorted(artifacts.items()):
            if len(path.parts) == 1:
                destination = staging_fd
            else:
                destination = child_descriptors[path.parts[0]]
            _write_file_at(destination, path.name, raw)
        for descriptor in child_descriptors.values():
            _finish_directory(descriptor)
        _finish_directory(staging_fd)
    finally:
        failures: list[OSError] = []
        for descriptor in reversed(tuple(child_descriptors.values())):
            try:
                os.close(descriptor)
            except OSError as error:
                failures.append(error)
        if failures:
            active = sys.exception()
            if active is None:
                raise RuntimeError(
                    f"generated directory close failed: {failures[0]}"
                )
            raise RuntimeError(
                f"generated directory close failed: {failures[0]}"
            ) from active


def _snapshot_generated_directory(
    directory_fd: int,
    prefix: PurePosixPath = PurePosixPath(),
) -> tuple[dict[PurePosixPath, bytes], dict[PurePosixPath, tuple[int, int]]]:
    files: dict[PurePosixPath, bytes] = {}
    metadata: dict[PurePosixPath, tuple[int, int]] = {}
    root = os.fstat(directory_fd)
    metadata[prefix] = (stat.S_IMODE(root.st_mode), root.st_mtime_ns)
    with os.scandir(directory_fd) as entries:
        ordered = sorted(entries, key=lambda entry: entry.name)
    for entry in ordered:
        current_path = prefix / entry.name
        node = entry.stat(follow_symlinks=False)
        if stat.S_ISDIR(node.st_mode):
            child = _open_directory_at(directory_fd, entry.name)
            try:
                nested_files, nested_metadata = (
                    _snapshot_generated_directory(child, current_path)
                )
            finally:
                os.close(child)
            files.update(nested_files)
            metadata.update(nested_metadata)
            continue
        if not stat.S_ISREG(node.st_mode):
            raise _validation("staging contains an unsupported file type")
        descriptor = os.open(
            entry.name,
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=directory_fd,
        )
        try:
            chunks: list[bytes] = []
            while chunk := os.read(descriptor, _READ_CHUNK_SIZE):
                chunks.append(chunk)
            opened = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        files[current_path] = b"".join(chunks)
        metadata[current_path] = (
            stat.S_IMODE(opened.st_mode),
            opened.st_mtime_ns,
        )
    return files, metadata


def _verify_staging(
    staging_fd: int,
    artifacts: Mapping[PurePosixPath, bytes],
) -> None:
    current, metadata = _snapshot_generated_directory(staging_fd)
    if current != dict(artifacts):
        raise _validation("staged site does not match rendered artifacts")
    for path, (mode, mtime_ns) in metadata.items():
        expected_mode = 0o755 if path in {
            PurePosixPath(),
            PurePosixPath("catalog"),
            PurePosixPath("lessons"),
            PurePosixPath("roadmap"),
        } else 0o644
        if mode != expected_mode or mtime_ns != _DETERMINISTIC_MTIME_NS:
            raise _validation("staged site metadata is not deterministic")
    os.fsync(staging_fd)


def _native_rename_function() -> tuple[object, int, int]:
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        try:
            function = library.renameatx_np
        except AttributeError as error:
            raise RuntimeError(
                "native atomic directory rename is not supported"
            ) from error
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        return function, 0x4, 0x2  # RENAME_EXCL, RENAME_SWAP
    if sys.platform.startswith("linux"):
        try:
            function = library.renameat2
        except AttributeError as error:
            raise RuntimeError(
                "native atomic directory rename is not supported"
            ) from error
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        return function, 1, 2  # RENAME_NOREPLACE, RENAME_EXCHANGE
    raise RuntimeError("native atomic directory rename is not supported")


def _publish_directory(
    parent_fd: int,
    source_name: str,
    target_name: str,
    *,
    replace_existing: bool,
) -> None:
    for name in (source_name, target_name):
        if (
            not name
            or name in {".", ".."}
            or "/" in name
            or "\0" in name
        ):
            raise _PublishInputError(
                "publish entry name must be a basename"
            )
    try:
        function, no_replace, exchange = _native_rename_function()
    except RuntimeError as error:
        # This happens before the syscall, so callers can safely retain
        # pre-publication cleanup even if later identity inspection is blocked.
        raise _PublishRuntimeError(str(error)) from error
    flag = exchange if replace_existing else no_replace
    # A portable os.replace fallback can clobber a racing target. Native flags
    # are therefore a required safety capability, not an optimization.
    ctypes.set_errno(0)
    result = function(
        parent_fd,
        os.fsencode(source_name),
        parent_fd,
        os.fsencode(target_name),
        flag,
    )
    if result == 0:
        return
    code = ctypes.get_errno()
    if code == 0:
        raise _PublishRuntimeError(
            "native atomic directory rename failed without errno"
        )
    if code in {errno.EEXIST, errno.ENOTEMPTY}:
        raise _PublishConflictError(
            f"publish target already exists: {target_name}"
        )
    if code in {errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EINVAL}:
        raise _PublishRuntimeError(
            "native atomic directory rename is not supported"
        ) from OSError(code, os.strerror(code), target_name)
    raise _PublishOSError(code, os.strerror(code), target_name)


def _observe_publish_entry(
    parent_fd: int,
    name: str,
    label: str,
) -> _EntryObservation:
    try:
        current = os.stat(
            name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return _EntryObservation(inspected=True, identity=None)
    except BaseException as error:
        return _EntryObservation(
            inspected=False,
            identity=None,
            note=f"{label} reconciliation failed: {error}",
        )
    return _EntryObservation(
        inspected=True,
        identity=_identity(current),
    )


def _reconcile_failed_publication(
    parent_fd: int,
    output_name: str,
    staging_name: str,
    staging_identity: tuple[int, int],
    previous_identity: tuple[int, int] | None,
) -> _PublicationReconciliation:
    output = _observe_publish_entry(
        parent_fd,
        output_name,
        "output",
    )
    staging = _observe_publish_entry(
        parent_fd,
        staging_name,
        "staging",
    )
    notes = tuple(
        note
        for note in (output.note, staging.note)
        if note is not None
    )

    if output.inspected and output.identity == staging_identity:
        if previous_identity is None:
            return _PublicationReconciliation(
                _PublicationEvidence.PUBLISHED,
                notes,
            )
        if (
            staging.inspected
            and staging.identity == previous_identity
        ):
            return _PublicationReconciliation(
                _PublicationEvidence.PUBLISHED,
                notes,
            )

    if output.inspected and staging.inspected:
        expected_output = previous_identity
        if (
            output.identity == expected_output
            and staging.identity == staging_identity
        ):
            return _PublicationReconciliation(
                _PublicationEvidence.NOT_PUBLISHED,
                notes,
            )

    return _PublicationReconciliation(
        _PublicationEvidence.UNKNOWN,
        notes,
    )


def _require_safe_cleanup_directory(
    node: os.stat_result,
    root_device: int,
    label: str,
) -> None:
    if not stat.S_ISDIR(node.st_mode):
        raise RuntimeError(f"{label} is not a directory")
    if node.st_dev != root_device:
        # st_dev blocks ordinary mount crossings. Portable dirfd APIs cannot
        # distinguish a same-device bind mount, so generated/recovery trees are
        # required to be mount-free inside the exclusive workspace namespace.
        raise RuntimeError(f"{label} crosses a filesystem boundary")
    if hasattr(os, "geteuid") and node.st_uid != os.geteuid():
        raise RuntimeError(f"{label} is not owned by the current user")
    if node.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise RuntimeError(f"{label} is group/world writable")


def _clear_directory_fd(
    directory_fd: int,
    root_device: int | None = None,
) -> None:
    root = os.fstat(directory_fd)
    if root_device is None:
        root_device = root.st_dev
    _require_safe_cleanup_directory(
        root,
        root_device,
        "cleanup directory",
    )
    with os.scandir(directory_fd) as entries:
        ordered = sorted(entries, key=lambda entry: entry.name)
    for entry in ordered:
        node = entry.stat(follow_symlinks=False)
        if stat.S_ISDIR(node.st_mode):
            _require_safe_cleanup_directory(
                node,
                root_device,
                "nested cleanup directory",
            )
            child = _open_directory_at(directory_fd, entry.name)
            child_error: BaseException | None = None
            try:
                opened = os.fstat(child)
                _require_safe_cleanup_directory(
                    opened,
                    root_device,
                    "opened nested cleanup directory",
                )
                if _identity(opened) != _identity(node):
                    raise RuntimeError(
                        "nested cleanup directory changed while opening"
                    )
                _clear_directory_fd(child, root_device)
                current = os.stat(
                    entry.name,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                _require_safe_cleanup_directory(
                    current,
                    root_device,
                    "nested cleanup directory before removal",
                )
                if _identity(current) != _identity(opened):
                    raise RuntimeError(
                        "nested cleanup directory changed before removal"
                    )
            except BaseException as error:
                child_error = error
                raise
            finally:
                try:
                    os.close(child)
                except OSError as close_error:
                    if child_error is None:
                        raise
                    child_error.add_note(
                        "nested cleanup descriptor also failed to close: "
                        f"{close_error}"
                    )
            os.rmdir(entry.name, dir_fd=directory_fd)
        else:
            # Symlinks and special files are unlinked as directory entries;
            # cleanup never follows a replaced path.
            os.unlink(entry.name, dir_fd=directory_fd)


def _remove_owned_directory(
    parent_fd: int,
    name: str,
    directory_fd: int,
) -> None:
    expected = os.fstat(directory_fd)
    _require_safe_cleanup_directory(
        expected,
        expected.st_dev,
        "owned cleanup root",
    )
    current = os.stat(
        name,
        dir_fd=parent_fd,
        follow_symlinks=False,
    )
    _require_safe_cleanup_directory(
        current,
        expected.st_dev,
        "owned cleanup entry",
    )
    if (
        _identity(current) != _identity(expected)
    ):
        raise RuntimeError(
            "owned directory entry was replaced; refusing cleanup"
        )
    _clear_directory_fd(directory_fd, expected.st_dev)
    os.rmdir(name, dir_fd=parent_fd)


def _fsync_parent_after_publish(parent_fd: int) -> None:
    os.fsync(parent_fd)


def _publish_staged_site(
    parent: _DirectoryHandle,
    output_name: str,
    staging_name: str,
    staging_fd: int,
    staging_identity: tuple[int, int],
    previous: os.stat_result | None,
    transaction: _BuildTransaction,
) -> None:
    replace_existing = previous is not None
    previous_identity = (
        None if previous is None else _identity(previous)
    )
    previous_fd: int | None = None
    try:
        if replace_existing:
            previous_fd = _open_directory_at(
                parent.descriptor,
                output_name,
            )
            pinned = os.fstat(previous_fd)
            current = os.stat(
                output_name,
                dir_fd=parent.descriptor,
                follow_symlinks=False,
            )
            assert previous_identity is not None
            if _identity(pinned) != previous_identity or _identity(
                current
            ) != previous_identity:
                raise _validation(
                    "output_root changed before publication"
                )
        _verify_directory_identity(parent)
        try:
            _publish_directory(
                parent.descriptor,
                staging_name,
                output_name,
                replace_existing=replace_existing,
            )
            transaction.mark_published()
        except _DEFINITELY_NOT_PUBLISHED:
            raise
        except BaseException as publisher_error:
            # Once the publisher has been invoked, an arbitrary exception can
            # arrive after the native rename. Mark UNKNOWN before inspection so
            # a second failure can never authorize pre-publication deletion.
            transaction.mark_publication_unknown()
            try:
                reconciliation = _reconcile_failed_publication(
                    parent.descriptor,
                    output_name,
                    staging_name,
                    staging_identity,
                    previous_identity,
                )
            except BaseException as reconciliation_error:
                reconciliation = _PublicationReconciliation(
                    _PublicationEvidence.UNKNOWN,
                    (
                        "publication reconciliation also failed: "
                        f"{reconciliation_error}",
                    ),
                )
            if (
                reconciliation.evidence
                is _PublicationEvidence.NOT_PUBLISHED
            ):
                transaction.mark_not_published()
                raise
            if (
                reconciliation.evidence
                is _PublicationEvidence.PUBLISHED
            ):
                transaction.mark_published()
                message = (
                    "site is visible but publisher failed after "
                    "native publication"
                )
            else:
                message = (
                    "native publication outcome is unknown after "
                    "publisher failure"
                )
            state_error = BuildPublicationStateError(message)
            for note in reconciliation.notes:
                state_error.add_note(note)
            raise state_error from publisher_error
    except BaseException as operation_error:
        if previous_fd is not None:
            descriptor = previous_fd
            previous_fd = None
            try:
                os.close(descriptor)
            except OSError as close_error:
                operation_error.add_note(
                    "previous output descriptor also failed to close "
                    f"before publication: {close_error}"
                )
        raise

    # Returning from the native rename is the sole commit point. Every later
    # failure is normalized below so callers never attempt pre-publish cleanup
    # against a staging descriptor that now points at the visible new output.
    post_error: BuildPostCommitError | None = None
    post_cause: BaseException | None = None
    recovery_fd: int | None = None
    try:
        _verify_directory_identity(parent)
        published = os.stat(
            output_name,
            dir_fd=parent.descriptor,
            follow_symlinks=False,
        )
        if _identity(published) != staging_identity:
            raise BuildPublicationStateError(
                "site is visible but publication identity is unknown"
            )
        if previous_fd is not None:
            pinned_previous_identity = _identity(os.fstat(previous_fd))
            recovery = os.stat(
                staging_name,
                dir_fd=parent.descriptor,
                follow_symlinks=False,
            )
            if _identity(recovery) != pinned_previous_identity:
                # Native exchange is atomic but not an inode-conditional CAS.
                # If a same-owner competitor replaces the target after pinning,
                # its directory is preserved at the recovery name for audit.
                raise BuildPublicationStateError(
                    "site is visible but replaced output recovery "
                    "identity is unknown"
                )
        try:
            _fsync_parent_after_publish(parent.descriptor)
        except OSError as error:
            raise BuildPublicationDurabilityError(
                "site published but parent-directory fsync failed"
            ) from error

        if previous_fd is not None:
            descriptor = previous_fd
            previous_fd = None
            # Close the pre-rename pin before deleting recovery. If this close
            # fails, the old output remains inspectable at the staging name.
            os.close(descriptor)
            recovery_fd = _open_directory_at(
                parent.descriptor,
                staging_name,
            )
            assert previous_identity is not None
            if _identity(os.fstat(recovery_fd)) != previous_identity:
                raise BuildPublicationStateError(
                    "site is visible but recovery changed before cleanup"
                )
            try:
                _remove_owned_directory(
                    parent.descriptor,
                    staging_name,
                    recovery_fd,
                )
            except OSError as error:
                raise BuildCleanupError(
                    "site published but replaced output cleanup failed"
                ) from error
            except RuntimeError as error:
                raise BuildCleanupError(
                    "site published but replaced output cleanup was unsafe"
                ) from error
            descriptor = recovery_fd
            recovery_fd = None
            os.close(descriptor)
            try:
                os.fsync(parent.descriptor)
            except OSError as error:
                raise BuildPublicationDurabilityError(
                    "site published but cleanup durability is unknown"
                ) from error
    except BuildPostCommitError as error:
        post_error = error
    except BaseException as error:
        post_error = BuildPublicationStateError(
            "site is visible but post-commit verification failed"
        )
        post_cause = error

    for descriptor, label in (
        (recovery_fd, "recovery"),
        (previous_fd, "previous output"),
    ):
        if descriptor is None:
            continue
        try:
            os.close(descriptor)
        except OSError as close_error:
            if post_error is None:
                post_error = BuildPublicationStateError(
                    f"site is visible but {label} descriptor close failed"
                )
                post_cause = close_error
            else:
                post_error.add_note(
                    f"{label} descriptor also failed to close: {close_error}"
                )
    if post_error is not None:
        if post_cause is not None:
            raise post_error from post_cause
        raise post_error


def _stage_and_publish(
    parent: _DirectoryHandle,
    output_name: str,
    artifacts: Mapping[PurePosixPath, bytes],
    transaction: _BuildTransaction,
) -> None:
    previous = _output_state(parent, output_name)
    _reject_stale_backup(parent, output_name)
    reservation: _StagingReservation | None = None
    operation_error: BaseException | None = None
    try:
        reservation = _create_private_staging(parent, output_name)
        _initialize_private_staging(parent, reservation)
        assert reservation.descriptor is not None
        assert reservation.identity is not None
        staging_fd = reservation.descriptor
        _populate_staging(staging_fd, artifacts)
        _verify_staging(staging_fd, artifacts)
        current = os.stat(
            reservation.name,
            dir_fd=parent.descriptor,
            follow_symlinks=False,
        )
        if _identity(current) != reservation.identity:
            raise RuntimeError("private staging changed before publication")
        _publish_staged_site(
            parent,
            output_name,
            reservation.name,
            staging_fd,
            reservation.identity,
            previous,
            transaction,
        )
    except BuildPostCommitError as error:
        operation_error = error
        raise
    except BaseException as error:
        if transaction.publication_may_have_committed:
            state_error = BuildPublicationStateError(
                "native publication may have committed; "
                "pre-publication cleanup was skipped"
            )
            operation_error = state_error
            raise state_error from error
        operation_error = error
        if reservation is not None:
            cleanup_error = _cleanup_staging_before_publish(
                parent,
                reservation,
                error,
            )
            if cleanup_error is not None:
                operation_error = cleanup_error
                raise cleanup_error from error
        raise
    finally:
        descriptor = (
            None if reservation is None else reservation.descriptor
        )
        if descriptor is not None:
            reservation.descriptor = None
        try:
            if descriptor is not None:
                os.close(descriptor)
        except OSError as close_error:
            if operation_error is not None:
                operation_error.add_note(
                    "private staging descriptor also failed to close: "
                    f"{close_error}"
                )
            elif transaction.publication_may_have_committed:
                raise BuildPublicationStateError(
                    "site is visible but private staging descriptor "
                    "close failed"
                ) from close_error
            else:
                raise RuntimeError(
                    f"private staging close failed: {close_error}"
                ) from close_error


def build_site(
    content_root: Path,
    template_root: Path,
    static_root: Path,
    output_root: Path,
) -> None:
    """Validate, stage, durably publish, and atomically replace the static site."""
    output_parent_path, output_name = _output_basename(output_root)
    transaction = _BuildTransaction()
    with (
        _open_trusted_directory(
            content_root,
            "content_root",
            transaction,
        ) as content,
        _open_trusted_directory(
            template_root,
            "template_root",
            transaction,
        ) as templates,
        _open_trusted_directory(
            static_root,
            "static_root",
            transaction,
        ) as static_files,
        _open_trusted_directory(
            output_parent_path,
            "output_root parent",
            transaction,
        ) as output_parent,
    ):
        _validate_no_source_overlap(
            output_parent.path / output_name,
            (content.path, templates.path, static_files.path),
        )
        items = _load_catalog_from_root(content)
        roadmap = _load_roadmap(content)
        stylesheet = _read_stable_regular_file(
            static_files,
            "styles.css",
            MAX_STYLESHEET_BYTES,
        )
        before_templates = {
            name: _read_stable_regular_file(
                templates,
                name,
                MAX_TEMPLATE_BYTES,
            )
            for name in _TEMPLATE_NAMES
        }
        artifacts = _render_artifacts(
            items,
            roadmap,
            before_templates,
            stylesheet,
        )
        after_templates = {
            name: _read_stable_regular_file(
                templates,
                name,
                MAX_TEMPLATE_BYTES,
            )
            for name in _TEMPLATE_NAMES
        }
        if before_templates != after_templates:
            raise _validation("templates changed during build")
        if stylesheet != _read_stable_regular_file(
            static_files,
            "styles.css",
            MAX_STYLESHEET_BYTES,
        ):
            raise _validation("styles.css changed during build")
        for handle in (content, templates, static_files, output_parent):
            _verify_directory_identity(handle)
        _stage_and_publish(
            output_parent,
            output_name,
            artifacts,
            transaction,
        )
