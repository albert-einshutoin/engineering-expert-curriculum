"""Strict, immutable capstone briefs bound to the complete lesson release."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
import sys
from types import MappingProxyType
from typing import Final
import unicodedata

from .catalog import strict_json_loads
from .errors import CurriculumValidationError


MAX_CAPSTONE_BYTES: Final = 256 * 1024
MAX_CAPSTONE_COLLECTION_BYTES: Final = 768 * 1024
CAPSTONE_IDS: Final = (
    "global-service",
    "legacy-evolution",
    "oss-launch",
)
EVIDENCE_KINDS: Final = ("build", "operate", "explain", "review")
RUBRIC_LEVELS: Final = (
    "incomplete",
    "developing",
    "proficient",
    "exemplary",
)
_CAPSTONE_FILES: Final = tuple(f"{value}.json" for value in CAPSTONE_IDS)
_ROOT_FIELDS: Final = frozenset(
    {
        "version",
        "id",
        "title",
        "scenario",
        "constraints",
        "lessonIds",
        "primaryExercises",
        "evidence",
        "milestones",
        "reviewQuestions",
        "rubric",
    }
)
_EVIDENCE_FIELDS: Final = frozenset(EVIDENCE_KINDS)
_RUBRIC_FIELDS: Final = frozenset(RUBRIC_LEVELS)
_UNSAFE_TEXT_CATEGORIES: Final = frozenset(
    {"Cc", "Cf", "Cs", "Zl", "Zp"}
)
_LESSON_ID: Final = re.compile(
    r"core-(0[1-9]|[12][0-9]|30)-[a-z0-9]+(?:-[a-z0-9]+)*\Z",
    re.ASCII,
)
_MAX_LESSON_ID_CHARS: Final = 96
_EXERCISE_VERBS: Final = (
    "検証",
    "再現",
    "測定",
    "追跡",
    "再評価",
    "更新",
    "監査",
    "実行",
    "導く",
    "比較",
)
# One accountable capstone per lesson prevents a long ID list from being
# mistaken for integrated practice. Other capstones may reinforce the lesson.
_PRIMARY_OWNER: Final = MappingProxyType(
    {
        "core-01-systems-tradeoffs": "global-service",
        "core-02-algorithms-measurement": "global-service",
        "core-03-architecture-memory-caches": "global-service",
        "core-04-os-processes-concurrency": "global-service",
        "core-05-networks-latency-failure": "global-service",
        "core-06-requirements-domain-modeling": "global-service",
        "core-07-api-contract-design": "global-service",
        "core-08-modularity-evolutionary-architecture": "legacy-evolution",
        "core-09-test-strategy-tdd": "legacy-evolution",
        "core-10-threat-modeling-secure-design": "oss-launch",
        "core-11-data-modeling-storage": "global-service",
        "core-12-transactions-isolation-consistency": "global-service",
        "core-13-distributed-coordination-failure": "global-service",
        "core-14-performance-capacity": "global-service",
        "core-15-reliability-observability-slo": "global-service",
        "core-16-hci-usability-accessibility": "oss-launch",
        "core-17-graphics-visual-information": "oss-launch",
        "core-18-product-discovery-experiments": "oss-launch",
        "core-19-technical-communication-design-docs": "legacy-evolution",
        "core-20-ethics-privacy-societal-impact": "global-service",
        "core-21-maintenance-legacy-comprehension": "legacy-evolution",
        "core-22-evolution-safe-migrations": "legacy-evolution",
        "core-23-incident-response-learning": "legacy-evolution",
        "core-24-delivery-ci-release-safety": "oss-launch",
        "core-25-engineering-economics-capacity": "legacy-evolution",
        "core-26-code-review-collaborative-quality": "oss-launch",
        "core-27-team-interfaces-sociotechnical-architecture": "legacy-evolution",
        "core-28-oss-governance-stewardship": "oss-launch",
        "core-29-cross-cultural-async-collaboration": "oss-launch",
        "core-30-evidence-based-technical-leadership": "global-service",
    }
)
# Each primary exercise must retain the domain vocabulary that makes its
# evidence attributable to one lesson. Length and action verbs alone allow a
# generic sentence to masquerade as thirty different exercises.
_PRIMARY_EXERCISE_ANCHORS: Final = MappingProxyType(
    {
        "core-01-systems-tradeoffs": ("反証条件", "adr"),
        "core-02-algorithms-measurement": ("反復測定", "交差点"),
        "core-03-architecture-memory-caches": ("memory", "locality"),
        "core-04-os-processes-concurrency": ("interleaving", "不変条件"),
        "core-05-networks-latency-failure": ("dns", "deadline"),
        "core-06-requirements-domain-modeling": ("用語衝突", "domain"),
        "core-07-api-contract-design": ("冪等", "contract"),
        "core-08-modularity-evolutionary-architecture": (
            "dependency direction",
            "adr",
        ),
        "core-09-test-strategy-tdd": ("red", "mutation"),
        "core-10-threat-modeling-secure-design": ("攻撃経路", "残余risk"),
        "core-11-data-modeling-storage": ("storage adr", "access pattern"),
        "core-12-transactions-isolation-consistency": (
            "transaction schedule",
            "分離異常",
        ),
        "core-13-distributed-coordination-failure": (
            "partition",
            "reconciliation",
        ),
        "core-14-performance-capacity": ("安全容量", "headroom"),
        "core-15-reliability-observability-slo": ("sli", "burn alert"),
        "core-16-hci-usability-accessibility": ("keyboard", "読み上げ"),
        "core-17-graphics-visual-information": ("css-only", "同等"),
        "core-18-product-discovery-experiments": ("利用者仮説", "guardrail"),
        "core-19-technical-communication-design-docs": ("経営", "operations"),
        "core-20-ethics-privacy-societal-impact": (
            "affected population",
            "残余risk",
        ),
        "core-21-maintenance-legacy-comprehension": (
            "未知領域",
            "characterization",
        ),
        "core-22-evolution-safe-migrations": ("backfill", "rollback"),
        "core-23-incident-response-learning": ("timeline", "寄与要因"),
        "core-24-delivery-ci-release-safety": ("provenance", "artifact"),
        "core-25-engineering-economics-capacity": ("機会費用", "投資"),
        "core-26-code-review-collaborative-quality": (
            "author snapshot",
            "別contributor",
        ),
        "core-27-team-interfaces-sociotechnical-architecture": (
            "cognitive load",
            "team interface",
        ),
        "core-28-oss-governance-stewardship": (
            "maintainer boundary",
            "contribution",
        ),
        "core-29-cross-cultural-async-collaboration": ("utc", "dissent"),
        "core-30-evidence-based-technical-leadership": (
            "withdrawal conditions",
            "不確実性",
        ),
    }
)
_NATIVE_PATH = type(Path())
_DIRECTORY_FLAGS: Final = (
    os.O_RDONLY
    | os.O_DIRECTORY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_FILE_FLAGS: Final = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NONBLOCK", 0)
)


@dataclass(frozen=True, slots=True)
class Capstone:
    version: int
    id: str
    title: str
    scenario: str
    constraints: tuple[str, ...]
    lesson_ids: tuple[str, ...]
    primary_exercises: Mapping[str, str]
    evidence: Mapping[str, str]
    milestones: tuple[str, ...]
    review_questions: tuple[str, ...]
    rubric: Mapping[str, str]

    @property
    def evidence_kinds(self) -> tuple[str, ...]:
        return tuple(self.evidence)


def _validation(message: str) -> CurriculumValidationError:
    return CurriculumValidationError(message)


def _require_descriptor_support() -> None:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if (
        type(nofollow) is not int
        or nofollow == 0
        or type(directory) is not int
        or directory == 0
    ):
        raise _validation("safe capstone descriptors are not supported")


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


def _text(
    value: object,
    label: str,
    *,
    minimum: int = 1,
    maximum: int = 4_096,
) -> str:
    if type(value) is not str:
        raise _validation(f"{label} must be a string")
    if (
        len(value) < minimum
        or len(value) > maximum
        or value != value.strip()
        or any(
            unicodedata.category(character) in _UNSAFE_TEXT_CATEGORIES
            for character in value
        )
    ):
        raise _validation(
            f"{label} must be non-empty, unpadded, bounded safe text"
        )
    return value


def _text_list(
    value: object,
    label: str,
    *,
    minimum_items: int,
    maximum_items: int,
    minimum_chars: int = 8,
) -> tuple[str, ...]:
    if type(value) is not list:
        raise _validation(f"{label} must be a list")
    if not minimum_items <= len(value) <= maximum_items:
        raise _validation(f"{label} has an invalid item count")
    result = tuple(
        _text(
            item,
            f"{label} item {index}",
            minimum=minimum_chars,
        )
        for index, item in enumerate(value)
    )
    duplicates = sorted(
        item for item, count in Counter(result).items() if count > 1
    )
    if duplicates:
        raise _validation(f"{label} must not contain duplicates")
    return result


def _string_mapping(
    value: object,
    expected: frozenset[str],
    label: str,
    *,
    minimum_chars: int,
) -> Mapping[str, str]:
    if type(value) is not dict:
        raise _validation(f"{label} must be an object")
    _exact_fields(value, expected, label)
    order = (
        EVIDENCE_KINDS
        if expected == _EVIDENCE_FIELDS
        else RUBRIC_LEVELS
        if expected == _RUBRIC_FIELDS
        else tuple(sorted(expected))
    )
    parsed = {
        key: _text(
            value[key],
            f"{label} {key}",
            minimum=minimum_chars,
        )
        for key in order
    }
    if len(set(parsed.values())) != len(parsed):
        raise _validation(f"{label} values must be distinct")
    return MappingProxyType(parsed)


def _lesson_ids(
    value: object,
    expected_lesson_ids: frozenset[str],
    capstone_id: str,
) -> tuple[str, ...]:
    if type(value) is not list:
        raise _validation(f"{capstone_id} lessonIds must be a list")
    if not value:
        raise _validation(f"{capstone_id} lessonIds must not be empty")
    result: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if (
            type(item) is not str
            or len(item) > _MAX_LESSON_ID_CHARS
            or _LESSON_ID.fullmatch(item) is None
        ):
            raise _validation(
                f"{capstone_id} lessonIds item {index} is invalid"
            )
        if item in seen:
            raise _validation(
                f"{capstone_id} lessonIds item {index} "
                "duplicates an earlier lesson; duplicate lesson entries "
                "are forbidden"
            )
        if item not in expected_lesson_ids:
            raise _validation(
                f"{capstone_id} lessonIds item {index} "
                "references an unknown lesson"
            )
        seen.add(item)
        result.append(item)
    if result != sorted(result):
        raise _validation(
            f"{capstone_id} lessonIds must be in canonical order"
        )
    return tuple(result)


def _normalized_exercise(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _primary_exercises(
    value: object,
    capstone_id: str,
    lesson_ids: tuple[str, ...],
) -> Mapping[str, str]:
    if type(value) is not dict:
        raise _validation(f"{capstone_id} primaryExercises must be an object")
    if any(type(key) is not str for key in value):
        raise _validation(
            f"{capstone_id} primaryExercises field names must be strings"
        )
    expected = frozenset(
        lesson_id
        for lesson_id, owner in _PRIMARY_OWNER.items()
        if owner == capstone_id
    )
    _exact_fields(
        value,
        expected,
        f"{capstone_id} primaryExercises",
    )
    if not expected.issubset(lesson_ids):
        raise _validation(
            f"{capstone_id} primary exercise must reference lessonIds"
        )
    parsed = {
        lesson_id: _text(
            value[lesson_id],
            f"{capstone_id} primary exercise {lesson_id}",
            minimum=24,
            maximum=1_000,
        )
        for lesson_id in sorted(expected)
    }
    normalized = tuple(_normalized_exercise(item) for item in parsed.values())
    if len(set(normalized)) != len(normalized):
        raise _validation("primary exercises must be unique after normalization")
    for lesson_id in sorted(expected):
        exercise = parsed[lesson_id]
        if lesson_id in exercise or not any(
            verb in exercise for verb in _EXERCISE_VERBS
        ):
            raise _validation(
                f"{capstone_id} primary exercise must describe "
                "an observable action"
            )
        normalized_exercise = _normalized_exercise(exercise)
        if any(
            _normalized_exercise(anchor) not in normalized_exercise
            for anchor in _PRIMARY_EXERCISE_ANCHORS[lesson_id]
        ):
            raise _validation(
                f"{capstone_id} primary exercise must be lesson-specific"
            )
    return MappingProxyType(parsed)


def _parse_document(
    raw: bytes,
    *,
    source_name: str,
    expected_id: str,
    expected_lesson_ids: frozenset[str],
) -> Capstone:
    if type(raw) is not bytes:
        raise _validation(f"{source_name}: capstone snapshot must be exact bytes")
    if len(raw) > MAX_CAPSTONE_BYTES:
        raise _validation(f"{source_name}: capstone exceeds maximum byte count")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        raise _validation(f"{source_name}: capstone is not valid UTF-8") from None
    try:
        document = strict_json_loads(raw, source_name)
    except CurriculumValidationError as error:
        if "duplicate JSON key:" in str(error):
            raise _validation(f"{source_name}: duplicate JSON key") from None
        raise
    if type(document) is not dict:
        raise _validation(f"{source_name}: capstone root must be an object")
    _exact_fields(document, _ROOT_FIELDS, f"{source_name} capstone root")
    if type(document["version"]) is not int or document["version"] != 1:
        raise _validation(f"{source_name}: version must be integer 1")
    capstone_id = _text(document["id"], f"{source_name} id", maximum=64)
    if capstone_id != expected_id:
        raise _validation(f"{source_name}: filename stem must equal capstone id")
    lesson_ids = _lesson_ids(
        document["lessonIds"],
        expected_lesson_ids,
        capstone_id,
    )
    primary_exercises = _primary_exercises(
        document["primaryExercises"],
        capstone_id,
        lesson_ids,
    )
    evidence = _string_mapping(
        document["evidence"],
        _EVIDENCE_FIELDS,
        f"{capstone_id} evidence",
        minimum_chars=40,
    )
    review = evidence["review"]
    required_review_terms = (
        "第三者",
        "finding",
        "author fix",
        "独立再評価",
        "単一制約",
    )
    if any(term not in review for term in required_review_terms):
        raise _validation(
            f"{capstone_id} review evidence must require the complete "
            "independent review cycle"
        )
    return Capstone(
        version=1,
        id=capstone_id,
        title=_text(document["title"], f"{capstone_id} title", maximum=160),
        scenario=_text(
            document["scenario"],
            f"{capstone_id} scenario",
            minimum=80,
            maximum=4_096,
        ),
        constraints=_text_list(
            document["constraints"],
            f"{capstone_id} constraints",
            minimum_items=6,
            maximum_items=16,
        ),
        lesson_ids=lesson_ids,
        primary_exercises=primary_exercises,
        evidence=evidence,
        milestones=_text_list(
            document["milestones"],
            f"{capstone_id} milestones",
            minimum_items=4,
            maximum_items=8,
            minimum_chars=32,
        ),
        review_questions=_text_list(
            document["reviewQuestions"],
            f"{capstone_id} reviewQuestions",
            minimum_items=4,
            maximum_items=10,
            minimum_chars=24,
        ),
        rubric=_string_mapping(
            document["rubric"],
            _RUBRIC_FIELDS,
            f"{capstone_id} rubric",
            minimum_chars=40,
        ),
    )


def parse_capstone_documents(
    documents: Mapping[str, bytes],
    *,
    expected_lesson_ids: frozenset[str],
) -> tuple[Capstone, ...]:
    """Parse one immutable three-document release snapshot."""
    if type(documents) is not dict:
        raise _validation("capstone documents must be an exact mapping")
    if type(expected_lesson_ids) is not frozenset or any(
        type(value) is not str for value in expected_lesson_ids
    ):
        raise _validation("expected lesson ids must be an exact frozenset")
    if frozenset(expected_lesson_ids) != frozenset(_PRIMARY_OWNER):
        raise _validation("expected lesson ids must be the complete core")
    if any(
        type(name) is not str or type(raw) is not bytes
        for name, raw in documents.items()
    ):
        raise _validation(
            "capstone document names and snapshots have invalid types"
        )
    if tuple(sorted(documents)) != _CAPSTONE_FILES:
        raise _validation(
            "capstone files must be exactly "
            + ", ".join(_CAPSTONE_FILES)
        )
    total = sum(len(value) for value in documents.values())
    if total > MAX_CAPSTONE_COLLECTION_BYTES:
        raise _validation("capstone collection exceeds maximum byte count")

    capstones = tuple(
        _parse_document(
            documents[f"{capstone_id}.json"],
            source_name=f"{capstone_id}.json",
            expected_id=capstone_id,
            expected_lesson_ids=expected_lesson_ids,
        )
        for capstone_id in CAPSTONE_IDS
    )
    normalized_exercises = tuple(
        _normalized_exercise(exercise)
        for capstone in capstones
        for exercise in capstone.primary_exercises.values()
    )
    if len(set(normalized_exercises)) != len(normalized_exercises):
        raise _validation("primary exercises must be unique after normalization")
    covered = frozenset(
        lesson_id
        for capstone in capstones
        for lesson_id in capstone.lesson_ids
    )
    missing = sorted(expected_lesson_ids - covered)
    if missing:
        raise _validation(
            "missing capstone lesson coverage: " + ", ".join(missing)
        )
    primary = {
        lesson_id: capstone.id
        for capstone in capstones
        for lesson_id in capstone.primary_exercises
    }
    if primary != dict(_PRIMARY_OWNER):
        raise _validation("primary exercise owner does not match release contract")
    return capstones


def _signature(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        stat.S_IFMT(value.st_mode),
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _directory_signature(value: os.stat_result) -> tuple[int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        stat.S_IFMT(value.st_mode),
        value.st_mtime_ns,
    )


def _read_at(directory_fd: int, name: str) -> bytes:
    descriptor: int | None = None
    try:
        before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise _validation(f"{name}: capstone must be a regular file")
        if before.st_size > MAX_CAPSTONE_BYTES:
            raise _validation(f"{name}: capstone exceeds maximum byte count")
        descriptor = os.open(name, _FILE_FLAGS, dir_fd=directory_fd)
        opened = os.fstat(descriptor)
        if _signature(opened) != _signature(before):
            raise _validation(f"{name}: capstone changed while opening")
        remaining = opened.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk or len(chunk) > remaining:
                raise _validation(f"{name}: capstone changed during read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise _validation(f"{name}: capstone changed during read")
        after = os.fstat(descriptor)
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if _signature(after) != _signature(opened) or _signature(current) != _signature(opened):
            raise _validation(f"{name}: capstone changed during read")
        return b"".join(chunks)
    except CurriculumValidationError:
        raise
    except OSError:
        raise _validation(f"{name}: capstone cannot be read safely") from None
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as close_error:
                active = sys.exception()
                if active is None:
                    raise RuntimeError(
                        f"{name}: capstone descriptor close failed"
                    ) from close_error
                active.add_note(f"{name}: capstone descriptor also failed to close")


def _documents_from_directory_fd(directory_fd: int) -> dict[str, bytes]:
    try:
        names = tuple(sorted(entry.name for entry in os.scandir(directory_fd)))
    except OSError:
        raise _validation("capstones cannot be discovered safely") from None
    if names != _CAPSTONE_FILES:
        raise _validation(
            "capstone files must be exactly " + ", ".join(_CAPSTONE_FILES)
        )
    return {name: _read_at(directory_fd, name) for name in names}


def load_capstones_from_content_fd(
    content_descriptor: int,
    *,
    expected_lesson_ids: frozenset[str],
) -> tuple[Capstone, ...]:
    """Load capstones through a caller-pinned content directory."""
    _require_descriptor_support()
    if type(content_descriptor) is not int or content_descriptor < 0:
        raise _validation("content descriptor must be a valid integer")
    descriptor: int | None = None
    try:
        before = os.stat(
            "capstones",
            dir_fd=content_descriptor,
            follow_symlinks=False,
        )
        if not stat.S_ISDIR(before.st_mode):
            if stat.S_ISLNK(before.st_mode):
                raise _validation("capstones path contains a symbolic link")
            raise _validation("capstones must be a directory")
        descriptor = os.open(
            "capstones",
            _DIRECTORY_FLAGS,
            dir_fd=content_descriptor,
        )
        opened = os.fstat(descriptor)
        if _directory_signature(opened) != _directory_signature(before):
            raise _validation("capstones changed while opening")
        documents = _documents_from_directory_fd(descriptor)
        current = os.stat(
            "capstones",
            dir_fd=content_descriptor,
            follow_symlinks=False,
        )
        if (
            _directory_signature(os.fstat(descriptor))
            != _directory_signature(opened)
            or _directory_signature(current)
            != _directory_signature(opened)
        ):
            raise _validation("capstones changed during read")
        return parse_capstone_documents(
            documents,
            expected_lesson_ids=expected_lesson_ids,
        )
    except CurriculumValidationError:
        raise
    except (FileNotFoundError, OSError):
        raise _validation("capstones cannot be read safely") from None
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as close_error:
                active = sys.exception()
                if active is None:
                    raise RuntimeError(
                        "capstones directory descriptor close failed"
                    ) from close_error
                active.add_note(
                    "capstones directory descriptor also failed to close"
                )


def _validate_lexical_path(path: Path) -> Path:
    if type(path) is not _NATIVE_PATH:
        raise _validation("capstone path must be an exact Path")
    if ".." in path.parts:
        raise _validation("capstone path contains parent traversal")
    absolute = path if path.is_absolute() else Path.cwd() / path
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            node = os.lstat(current)
        except OSError:
            raise _validation("capstone path cannot be inspected") from None
        if stat.S_ISLNK(node.st_mode):
            raise _validation("capstone path contains a symbolic link")
    return absolute


def load_capstones(path: Path) -> tuple[Capstone, ...]:
    """Load repository capstones and bind references to complete lessons."""
    _require_descriptor_support()
    absolute = _validate_lexical_path(path)
    if absolute.name != "capstones":
        raise _validation("capstone path must name the capstones directory")
    try:
        recorded_parent = os.lstat(absolute.parent)
        recorded_leaf = os.lstat(absolute)
    except OSError:
        raise _validation("capstone path cannot be inspected") from None
    if not stat.S_ISDIR(recorded_parent.st_mode):
        raise _validation("capstone parent must be a directory")
    if not stat.S_ISDIR(recorded_leaf.st_mode):
        raise _validation("capstones must be a directory")

    parent = absolute.parent
    parent_fd: int | None = None
    try:
        parent_fd = os.open(parent, _DIRECTORY_FLAGS)
        opened_parent = os.fstat(parent_fd)
        if _directory_signature(opened_parent) != _directory_signature(
            recorded_parent
        ):
            raise _validation("capstone parent changed while opening")
        opened_leaf = os.stat(
            "capstones",
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        if _directory_signature(opened_leaf) != _directory_signature(
            recorded_leaf
        ):
            raise _validation("capstones directory changed while opening")

        # Reuse the release lesson loader through the same pinned content
        # descriptor. This binds draft/reference validation to the snapshot
        # used for capstones instead of reopening sibling pathnames.
        from .lesson_rendering import load_lessons_from_root

        try:
            lesson_snapshot = load_lessons_from_root(parent_fd)
        except CurriculumValidationError as error:
            if "draft lessons cannot be published" in str(error):
                raise _validation(
                    "draft lessons cannot be referenced by capstones"
                ) from None
            raise
        expected = frozenset(
            item.lesson.id for item in lesson_snapshot.lessons
        )
        if expected != frozenset(_PRIMARY_OWNER):
            raise _validation("capstones require the complete lesson release")
        current_leaf = os.stat(
            "capstones",
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        if _directory_signature(current_leaf) != _directory_signature(
            opened_leaf
        ):
            raise _validation("capstones directory changed before read")
        result = load_capstones_from_content_fd(
            parent_fd,
            expected_lesson_ids=expected,
        )
        if lesson_snapshot != load_lessons_from_root(parent_fd):
            raise _validation("lessons changed while loading capstones")
        current_parent = os.lstat(parent)
        current_leaf = os.stat(
            "capstones",
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        if (
            _directory_signature(os.fstat(parent_fd))
            != _directory_signature(opened_parent)
            or _directory_signature(current_parent)
            != _directory_signature(opened_parent)
        ):
            raise _validation("capstone parent changed during read")
        if _directory_signature(current_leaf) != _directory_signature(
            opened_leaf
        ):
            raise _validation("capstones directory changed during read")
        return result
    except CurriculumValidationError:
        raise
    except OSError:
        raise _validation("capstone path cannot be opened safely") from None
    finally:
        primary_error = sys.exception()
        if parent_fd is not None:
            try:
                os.close(parent_fd)
            except OSError as close_error:
                if primary_error is None:
                    raise RuntimeError(
                        "capstone parent descriptor close failed"
                    ) from close_error
                primary_error.add_note(
                    "capstone parent descriptor also failed to close"
                )
