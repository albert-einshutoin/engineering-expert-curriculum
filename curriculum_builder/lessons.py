"""Strict, immutable domain model for evidence-based curriculum lessons."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import os
from pathlib import Path
import re
import stat
import sys
import unicodedata
from urllib.parse import urlsplit

from .catalog import strict_json_loads
from .errors import CurriculumValidationError


MAX_LESSON_BYTES = 512 * 1024
_READ_CHUNK_BYTES = 64 * 1024
_NATIVE_PATH_TYPE = type(Path())

LESSON_TRACKS = frozenset(
    {
        "foundations",
        "build",
        "data-scale",
        "human-product",
        "sustain",
        "lead",
    }
)
LESSON_STAGES = frozenset(range(1, 7))
LESSON_DIFFICULTIES = frozenset({"foundation", "intermediate", "advanced"})
LESSON_STATUSES = frozenset({"draft", "complete"})
EVIDENCE_KINDS = frozenset(
    {"artifact", "explanation", "reasoning", "transfer"}
)
RUBRIC_DIMENSIONS = frozenset(
    {"technical-correctness", "judgment", "evidence", "communication"}
)
RUBRIC_LEVEL_NAMES = frozenset(
    {"incomplete", "developing", "proficient", "exemplary"}
)
SOURCE_KINDS = frozenset(
    {"primary", "standard", "official", "peer-reviewed"}
)
REVIEW_INTERVALS = (1, 7, 30, 90)

_LESSON_ID_PATTERN = re.compile(
    r"^core-(?:0[1-9]|[12][0-9]|30)-[a-z0-9]+(?:-[a-z0-9]+)*$"
)
_OBJECTIVE_ID_PATTERN = re.compile(
    r"^obj-[a-z0-9]+(?:-[a-z0-9]+)*$"
)
_EVIDENCE_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
)

_ROOT_REQUIRED_FIELDS = frozenset(
    {
        "version",
        "id",
        "title",
        "summary",
        "track",
        "stage",
        "difficulty",
        "estimatedMinutes",
        "prerequisiteIds",
        "objectives",
        "evidence",
        "updatedAt",
        "status",
    }
)
_COMPLETE_FIELDS = (
    "lab",
    "teachBack",
    "assessment",
    "transferTask",
    "rubric",
    "sources",
    "review",
)
_ROOT_FIELDS = _ROOT_REQUIRED_FIELDS | frozenset(_COMPLETE_FIELDS)


@dataclass(frozen=True, slots=True)
class Objective:
    id: str
    statement: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Evidence:
    id: str
    kind: str
    description: str


@dataclass(frozen=True, slots=True)
class Lab:
    title: str
    artifact: str
    steps: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Assessment:
    prompt: str
    expected_evidence: str


@dataclass(frozen=True, slots=True)
class RubricLevels:
    incomplete: str
    developing: str
    proficient: str
    exemplary: str


@dataclass(frozen=True, slots=True)
class Rubric:
    dimension: str
    levels: RubricLevels


@dataclass(frozen=True, slots=True)
class Source:
    title: str
    url: str
    kind: str


@dataclass(frozen=True, slots=True)
class Review:
    interval_days: tuple[int, ...]
    prompts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Lesson:
    version: int
    id: str
    title: str
    summary: str
    track: str
    stage: int
    difficulty: str
    estimated_minutes: int
    prerequisite_ids: tuple[str, ...]
    objectives: tuple[Objective, ...]
    evidence: tuple[Evidence, ...]
    lab: Lab | None
    teach_back: str | None
    assessment: tuple[Assessment, ...]
    transfer_task: str | None
    rubric: tuple[Rubric, ...]
    sources: tuple[Source, ...]
    review: Review | None
    updated_at: str
    status: str

    @property
    def review_intervals(self) -> tuple[int, ...]:
        return () if self.review is None else self.review.interval_days


def load_lesson(path: Path) -> Lesson:
    """Load one stable regular-file snapshot into deeply immutable values."""
    if type(path) is not _NATIVE_PATH_TYPE:
        raise CurriculumValidationError("lesson path must be an exact Path")

    raw = _read_stable_regular_file(path)
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        raise CurriculumValidationError(
            f"{path.name}: lesson is not valid UTF-8"
        ) from None
    document = strict_json_loads(raw, path.name)
    if type(document) is not dict:
        raise CurriculumValidationError(
            f"{path.name}: lesson root must be an object"
        )

    context = path.name
    possible_id = document.get("id")
    if (
        type(possible_id) is str
        and len(possible_id) <= 96
        and _LESSON_ID_PATTERN.fullmatch(possible_id)
    ):
        context = f"{path.name} [{possible_id}]"
    try:
        return _parse_lesson(document)
    except CurriculumValidationError as error:
        raise CurriculumValidationError(f"{context}: {error}") from None


def _parse_lesson(raw: dict[str, object]) -> Lesson:
    _require_exact_object(
        raw,
        _ROOT_REQUIRED_FIELDS,
        _ROOT_FIELDS,
        "lesson root",
    )
    status = _require_choice(raw["status"], LESSON_STATUSES, "status")
    if status == "complete":
        missing = tuple(field for field in _COMPLETE_FIELDS if field not in raw)
        if missing:
            raise CurriculumValidationError(
                f"complete lesson missing: {', '.join(missing)}"
            )

    version = _require_int(raw["version"], "version", minimum=1, maximum=1)
    lesson_id = _require_identifier(
        raw["id"],
        "lesson id",
        _LESSON_ID_PATTERN,
        maximum=96,
    )
    prerequisite_ids = _parse_prerequisites(
        raw["prerequisiteIds"], lesson_id
    )
    objectives = _parse_objectives(
        raw["objectives"], complete=status == "complete"
    )
    evidence = _parse_evidence(raw["evidence"])
    _validate_objective_evidence(
        lesson_id,
        objectives,
        evidence,
        complete=status == "complete",
    )

    lab = _parse_optional_lab(raw.get("lab"), complete=status == "complete")
    teach_back = _parse_optional_text(
        raw.get("teachBack"),
        "teachBack",
        maximum=10_000,
    )
    assessment = _parse_assessment(
        raw.get("assessment"), complete=status == "complete"
    )
    transfer_task = _parse_optional_text(
        raw.get("transferTask"),
        "transferTask",
        maximum=10_000,
    )
    rubric = _parse_rubric(
        raw.get("rubric"), complete=status == "complete"
    )
    sources = _parse_sources(
        raw.get("sources"), complete=status == "complete"
    )
    review = _parse_review(
        raw.get("review"), complete=status == "complete"
    )

    if status == "complete":
        if teach_back is None:
            raise CurriculumValidationError("teachBack must be non-empty")
        if transfer_task is None:
            raise CurriculumValidationError("transferTask must be non-empty")

    return Lesson(
        version=version,
        id=lesson_id,
        title=_require_text(raw["title"], "title", maximum=160),
        summary=_require_text(raw["summary"], "summary", maximum=1_000),
        track=_require_choice(raw["track"], LESSON_TRACKS, "track"),
        stage=_require_allowed_int(raw["stage"], LESSON_STAGES, "stage"),
        difficulty=_require_choice(
            raw["difficulty"], LESSON_DIFFICULTIES, "difficulty"
        ),
        estimated_minutes=_require_int(
            raw["estimatedMinutes"],
            "estimatedMinutes",
            minimum=15,
            maximum=1_440,
        ),
        prerequisite_ids=prerequisite_ids,
        objectives=objectives,
        evidence=evidence,
        lab=lab,
        teach_back=teach_back,
        assessment=assessment,
        transfer_task=transfer_task,
        rubric=rubric,
        sources=sources,
        review=review,
        updated_at=_require_date(raw["updatedAt"]),
        status=status,
    )


def _read_stable_regular_file(path: Path) -> bytes:
    label = path.name or "lesson"
    descriptor: int | None = None
    try:
        before = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise CurriculumValidationError(
                f"{label}: lesson must be a regular file"
            )
        if before.st_size > MAX_LESSON_BYTES:
            raise CurriculumValidationError(
                f"{label}: lesson exceeds maximum byte count"
            )

        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _stat_signature(opened) != _stat_signature(before)
        ):
            raise CurriculumValidationError(
                f"{label}: lesson changed during read"
            )

        remaining = opened.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(_READ_CHUNK_BYTES, remaining))
            if not chunk or len(chunk) > remaining:
                raise CurriculumValidationError(
                    f"{label}: lesson changed during read"
                )
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise CurriculumValidationError(
                f"{label}: lesson changed during read"
            )

        after = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
        if (
            _stat_signature(after) != _stat_signature(opened)
            or _stat_signature(current) != _stat_signature(opened)
        ):
            raise CurriculumValidationError(
                f"{label}: lesson changed during read"
            )
        return b"".join(chunks)
    except CurriculumValidationError:
        raise
    except OSError:
        raise CurriculumValidationError(
            f"{label}: lesson cannot be read safely"
        ) from None
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                active = sys.exception()
                if active is None:
                    raise CurriculumValidationError(
                        f"{label}: lesson cannot be read safely"
                    ) from None
                active.add_note("lesson descriptor could not be closed")


def _stat_signature(
    value: os.stat_result,
) -> tuple[int, int, int, int, int, int]:
    # Identity plus content-relevant metadata detects replacement and writes
    # around the bounded descriptor read without retaining mutable file state.
    return (
        value.st_dev,
        value.st_ino,
        stat.S_IFMT(value.st_mode),
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _require_exact_object(
    value: object,
    required: frozenset[str],
    allowed: frozenset[str],
    label: str,
) -> dict[str, object]:
    if type(value) is not dict:
        raise CurriculumValidationError(f"{label} must be an object")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise CurriculumValidationError(
            f"{label} unknown fields: {', '.join(unknown)}"
        )
    missing = sorted(required - set(value))
    if missing:
        raise CurriculumValidationError(
            f"{label} missing required fields: {', '.join(missing)}"
        )
    return value


def _require_text(
    value: object,
    label: str,
    *,
    maximum: int,
    minimum: int = 1,
) -> str:
    if type(value) is not str:
        raise CurriculumValidationError(f"{label} must be exact text")
    if value != value.strip():
        raise CurriculumValidationError(f"{label} must be trimmed")
    if len(value) < minimum:
        raise CurriculumValidationError(f"{label} must be non-empty")
    if len(value) > maximum:
        raise CurriculumValidationError(f"{label} exceeds maximum length")
    if any(
        unicodedata.category(character) in {"Cc", "Cf", "Cs"}
        for character in value
    ):
        raise CurriculumValidationError(
            f"{label} contains control characters"
        )
    return value


def _parse_optional_text(
    value: object | None,
    label: str,
    *,
    maximum: int,
) -> str | None:
    if value is None:
        return None
    return _require_text(value, label, maximum=maximum)


def _require_identifier(
    value: object,
    label: str,
    pattern: re.Pattern[str],
    *,
    maximum: int,
) -> str:
    identifier = _require_text(value, label, maximum=maximum)
    if pattern.fullmatch(identifier) is None:
        raise CurriculumValidationError(f"invalid {label}")
    return identifier


def _require_int(
    value: object,
    label: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    if type(value) is not int:
        raise CurriculumValidationError(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        raise CurriculumValidationError(
            f"{label} must be between {minimum} and {maximum}"
        )
    return value


def _require_allowed_int(
    value: object,
    allowed: frozenset[int],
    label: str,
) -> int:
    if type(value) is not int or value not in allowed:
        choices = ", ".join(str(choice) for choice in sorted(allowed))
        raise CurriculumValidationError(f"{label} must be one of {choices}")
    return value


def _require_choice(
    value: object,
    choices: frozenset[str],
    label: str,
) -> str:
    text = _require_text(value, label, maximum=64)
    if text not in choices:
        raise CurriculumValidationError(
            f"{label} must be one of {', '.join(sorted(choices))}"
        )
    return text


def _require_list(
    value: object,
    label: str,
    *,
    maximum: int,
    minimum: int = 0,
) -> list[object]:
    if type(value) is not list:
        raise CurriculumValidationError(f"{label} must be a list")
    if len(value) < minimum:
        raise CurriculumValidationError(
            f"{label} must contain at least {minimum}"
        )
    if len(value) > maximum:
        raise CurriculumValidationError(
            f"{label} must contain at most {maximum}"
        )
    return value


def _require_unique(
    values: tuple[str, ...],
    label: str,
) -> tuple[str, ...]:
    if len(set(values)) != len(values):
        raise CurriculumValidationError(f"duplicate {label}")
    return values


def _parse_prerequisites(
    value: object,
    lesson_id: str,
) -> tuple[str, ...]:
    items = _require_list(value, "prerequisiteIds", maximum=10)
    prerequisite_ids = _require_unique(
        tuple(
            _require_identifier(
                item,
                "prerequisite id",
                _LESSON_ID_PATTERN,
                maximum=96,
            )
            for item in items
        ),
        "prerequisite id",
    )
    if lesson_id in prerequisite_ids:
        raise CurriculumValidationError("self prerequisite is not allowed")
    return prerequisite_ids


def _parse_objectives(
    value: object,
    *,
    complete: bool,
) -> tuple[Objective, ...]:
    items = _require_list(value, "objectives", maximum=6)
    if complete and len(items) < 3:
        raise CurriculumValidationError(
            "complete lessons need 3 to 6 objectives"
        )
    objectives: list[Objective] = []
    for index, item in enumerate(items):
        raw = _require_exact_object(
            item,
            frozenset({"id", "statement", "evidenceIds"}),
            frozenset({"id", "statement", "evidenceIds"}),
            f"objective {index + 1}",
        )
        evidence_values = _require_list(
            raw["evidenceIds"],
            f"objective {index + 1} evidenceIds",
            minimum=1 if complete else 0,
            maximum=12,
        )
        if complete and not evidence_values:
            raise CurriculumValidationError(
                f"objective {index + 1} must connect to evidence"
            )
        evidence_ids = _require_unique(
            tuple(
                _require_identifier(
                    evidence_id,
                    "evidence id",
                    _EVIDENCE_ID_PATTERN,
                    maximum=80,
                )
                for evidence_id in evidence_values
            ),
            f"objective {index + 1} evidence id",
        )
        objectives.append(
            Objective(
                id=_require_identifier(
                    raw["id"],
                    "objective id",
                    _OBJECTIVE_ID_PATTERN,
                    maximum=80,
                ),
                statement=_require_text(
                    raw["statement"],
                    f"objective {index + 1} statement",
                    maximum=500,
                ),
                evidence_ids=evidence_ids,
            )
        )
    _require_unique(tuple(item.id for item in objectives), "objective id")
    return tuple(objectives)


def _parse_evidence(value: object) -> tuple[Evidence, ...]:
    items = _require_list(value, "evidence", maximum=20)
    evidence: list[Evidence] = []
    fields = frozenset({"id", "kind", "description"})
    for index, item in enumerate(items):
        raw = _require_exact_object(
            item, fields, fields, f"evidence {index + 1}"
        )
        evidence.append(
            Evidence(
                id=_require_identifier(
                    raw["id"],
                    "evidence id",
                    _EVIDENCE_ID_PATTERN,
                    maximum=80,
                ),
                kind=_require_choice(
                    raw["kind"], EVIDENCE_KINDS, "evidence kind"
                ),
                description=_require_text(
                    raw["description"],
                    f"evidence {index + 1} description",
                    maximum=500,
                ),
            )
        )
    _require_unique(tuple(item.id for item in evidence), "evidence id")
    return tuple(evidence)


def _validate_objective_evidence(
    lesson_id: str,
    objectives: tuple[Objective, ...],
    evidence: tuple[Evidence, ...],
    *,
    complete: bool,
) -> None:
    known_ids = {item.id for item in evidence}
    for objective in objectives:
        unknown = sorted(set(objective.evidence_ids) - known_ids)
        if unknown:
            raise CurriculumValidationError(
                f"{lesson_id}: unknown evidence {', '.join(unknown)}"
            )
    if complete:
        missing_kinds = sorted(
            EVIDENCE_KINDS - {item.kind for item in evidence}
        )
        if missing_kinds:
            raise CurriculumValidationError(
                f"complete lesson evidence kinds missing: "
                f"{', '.join(missing_kinds)}"
            )


def _parse_optional_lab(value: object | None, *, complete: bool) -> Lab | None:
    if value is None:
        return None
    fields = frozenset({"title", "artifact", "steps"})
    raw = _require_exact_object(value, fields, fields, "lab")
    steps = _require_list(
        raw["steps"],
        "lab steps",
        minimum=3 if complete else 0,
        maximum=12,
    )
    return Lab(
        title=_require_text(raw["title"], "lab title", maximum=200),
        artifact=_require_text(
            raw["artifact"], "lab artifact", maximum=240
        ),
        steps=tuple(
            _require_text(
                step,
                f"lab step {index + 1}",
                maximum=1_000,
            )
            for index, step in enumerate(steps)
        ),
    )


def _parse_assessment(
    value: object | None,
    *,
    complete: bool,
) -> tuple[Assessment, ...]:
    if value is None:
        return ()
    items = _require_list(
        value,
        "assessment",
        minimum=1 if complete else 0,
        maximum=12,
    )
    fields = frozenset({"prompt", "expectedEvidence"})
    return tuple(
        _parse_assessment_item(item, index, fields)
        for index, item in enumerate(items)
    )


def _parse_assessment_item(
    value: object,
    index: int,
    fields: frozenset[str],
) -> Assessment:
    raw = _require_exact_object(
        value, fields, fields, f"assessment {index + 1}"
    )
    return Assessment(
        prompt=_require_text(
            raw["prompt"],
            f"assessment prompt {index + 1}",
            maximum=2_000,
        ),
        expected_evidence=_require_text(
            raw["expectedEvidence"],
            f"assessment {index + 1} expectedEvidence",
            maximum=2_000,
        ),
    )


def _parse_rubric(
    value: object | None,
    *,
    complete: bool,
) -> tuple[Rubric, ...]:
    if value is None:
        return ()
    items = _require_list(
        value,
        "rubric",
        minimum=4 if complete else 0,
        maximum=4,
    )
    rubric: list[Rubric] = []
    rubric_fields = frozenset({"dimension", "levels"})
    for index, item in enumerate(items):
        raw = _require_exact_object(
            item, rubric_fields, rubric_fields, f"rubric {index + 1}"
        )
        levels = _require_exact_object(
            raw["levels"],
            RUBRIC_LEVEL_NAMES,
            RUBRIC_LEVEL_NAMES,
            f"rubric levels {index + 1}",
        )
        rubric.append(
            Rubric(
                dimension=_require_choice(
                    raw["dimension"],
                    RUBRIC_DIMENSIONS,
                    "rubric dimension",
                ),
                levels=RubricLevels(
                    incomplete=_require_text(
                        levels["incomplete"],
                        "rubric incomplete",
                        maximum=1_000,
                    ),
                    developing=_require_text(
                        levels["developing"],
                        "rubric developing",
                        maximum=1_000,
                    ),
                    proficient=_require_text(
                        levels["proficient"],
                        "rubric proficient",
                        maximum=1_000,
                    ),
                    exemplary=_require_text(
                        levels["exemplary"],
                        "rubric exemplary",
                        maximum=1_000,
                    ),
                ),
            )
        )
    dimensions = tuple(item.dimension for item in rubric)
    if len(set(dimensions)) != len(dimensions):
        raise CurriculumValidationError("rubric dimensions must be distinct")
    if complete and set(dimensions) != RUBRIC_DIMENSIONS:
        raise CurriculumValidationError(
            "complete lesson rubric dimensions are invalid"
        )
    return tuple(rubric)


def _parse_sources(
    value: object | None,
    *,
    complete: bool,
) -> tuple[Source, ...]:
    if value is None:
        return ()
    items = _require_list(value, "sources", maximum=20)
    if complete and len(items) < 2:
        raise CurriculumValidationError(
            "complete lessons need at least two sources"
        )
    fields = frozenset({"title", "url", "kind"})
    sources: list[Source] = []
    for index, item in enumerate(items):
        raw = _require_exact_object(
            item, fields, fields, f"source {index + 1}"
        )
        sources.append(
            Source(
                title=_require_text(
                    raw["title"],
                    f"source {index + 1} title",
                    maximum=300,
                ),
                url=_require_https_url(raw["url"]),
                kind=_require_choice(
                    raw["kind"], SOURCE_KINDS, "source kind"
                ),
            )
        )
    _require_unique(tuple(item.url for item in sources), "source URL")
    return tuple(sources)


def _require_https_url(value: object) -> str:
    url = _require_text(value, "source URL", maximum=2_048)
    if any(character.isspace() for character in url):
        raise CurriculumValidationError("source URL must not contain whitespace")
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        raise CurriculumValidationError("source URL is malformed") from None
    if parsed.scheme != "https":
        raise CurriculumValidationError("source URL must use HTTPS")
    if hostname is None:
        raise CurriculumValidationError("source URL must have a host")
    if parsed.username is not None or parsed.password is not None:
        raise CurriculumValidationError(
            "source URL credentials are not allowed"
        )
    return url


def _parse_review(
    value: object | None,
    *,
    complete: bool,
) -> Review | None:
    if value is None:
        return None
    fields = frozenset({"intervalDays", "prompts"})
    raw = _require_exact_object(value, fields, fields, "review")
    interval_values = _require_list(
        raw["intervalDays"], "review intervals", maximum=8
    )
    intervals = tuple(
        _require_int(
            item,
            f"review interval {index + 1}",
            minimum=1,
            maximum=3_650,
        )
        for index, item in enumerate(interval_values)
    )
    prompts = _require_list(
        raw["prompts"],
        "review prompts",
        minimum=2 if complete else 0,
        maximum=12,
    )
    if complete and intervals != REVIEW_INTERVALS:
        raise CurriculumValidationError(
            "review intervals must be exactly 1, 7, 30, 90"
        )
    if not complete and (
        len(set(intervals)) != len(intervals)
        or tuple(sorted(intervals)) != intervals
    ):
        raise CurriculumValidationError(
            "review intervals must be distinct and increasing"
        )
    return Review(
        interval_days=intervals,
        prompts=tuple(
            _require_text(
                prompt,
                f"review prompt {index + 1}",
                maximum=1_000,
            )
            for index, prompt in enumerate(prompts)
        ),
    )


def _require_date(value: object) -> str:
    text = _require_text(value, "updatedAt", maximum=10, minimum=10)
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        raise CurriculumValidationError(
            "updatedAt must be a real YYYY-MM-DD date"
        ) from None
    if parsed.isoformat() != text:
        raise CurriculumValidationError(
            "updatedAt must be a real YYYY-MM-DD date"
        )
    return text
