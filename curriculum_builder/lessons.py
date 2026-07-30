"""Strict, immutable domain model for evidence-based curriculum lessons."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import ipaddress
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit

from .catalog import strict_json_loads
from .errors import CurriculumValidationError
from .lesson_io import read_stable_lesson_file


MAX_LESSON_BYTES = 512 * 1024
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
CAPABILITY_LEVELS = ("recognize", "explain", "apply", "diagnose", "lead")
_CAPABILITY_LEVEL_SET = frozenset(CAPABILITY_LEVELS)

_LESSON_ID_PATTERN = re.compile(
    r"^core-(?:0[1-9]|[12][0-9]|30)-[a-z0-9]+(?:-[a-z0-9]+)*$"
)
_OBJECTIVE_ID_PATTERN = re.compile(
    r"^obj-[a-z0-9]+(?:-[a-z0-9]+)*$"
)
_EVIDENCE_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
)
_ENCODED_CONTROL_PATTERN = re.compile(
    r"%(?:[01][0-9a-f]|7f|[89][0-9a-f])", re.IGNORECASE
)
_DNS_LABEL_PATTERN = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
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
    "capabilityProgression",
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
class CapabilityProgression:
    level: str
    criterion: str
    evidence_ids: tuple[str, ...]


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
    capability_progression: tuple[CapabilityProgression, ...]
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

    raw = read_stable_lesson_file(path, MAX_LESSON_BYTES)
    return load_lesson_bytes(raw, path.name)


def load_lesson_bytes(raw: bytes, source_name: str) -> Lesson:
    """Parse one caller-pinned byte snapshot without reopening its pathname."""
    if type(raw) is not bytes:
        raise CurriculumValidationError("lesson input must be exact bytes")
    if len(raw) > MAX_LESSON_BYTES:
        raise CurriculumValidationError("lesson exceeds maximum byte count")
    if (
        type(source_name) is not str
        or not source_name
        or len(source_name) > 255
        or source_name != Path(source_name).name
        or any(
            unicodedata.category(character)
            in {"Cc", "Cf", "Cs", "Zl", "Zp"}
            for character in source_name
        )
    ):
        raise CurriculumValidationError("lesson source name is invalid")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        raise CurriculumValidationError(
            f"{source_name}: lesson is not valid UTF-8"
        ) from None
    try:
        document = strict_json_loads(raw, source_name)
    except CurriculumValidationError as error:
        if "duplicate JSON key:" in str(error):
            raise CurriculumValidationError(
                f"{source_name}: duplicate JSON key"
            ) from None
        raise
    if type(document) is not dict:
        raise CurriculumValidationError(
            f"{source_name}: lesson root must be an object"
        )

    context = source_name
    possible_id = document.get("id")
    if (
        type(possible_id) is str
        and len(possible_id) <= 96
        and _LESSON_ID_PATTERN.fullmatch(possible_id)
    ):
        context = f"{source_name} [{possible_id}]"
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
    capability_progression = (
        _parse_capability_progression(
            raw["capabilityProgression"],
            evidence,
            complete=status == "complete",
        )
        if "capabilityProgression" in raw
        else ()
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
        if lab is None:
            raise CurriculumValidationError(
                "lab is required for complete lessons"
            )
        if teach_back is None:
            raise CurriculumValidationError("teachBack must be non-empty")
        if not assessment:
            raise CurriculumValidationError(
                "assessment is required for complete lessons"
            )
        if transfer_task is None:
            raise CurriculumValidationError("transferTask must be non-empty")
        if not rubric:
            raise CurriculumValidationError(
                "rubric is required for complete lessons"
            )
        if not sources:
            raise CurriculumValidationError(
                "sources are required for complete lessons"
            )
        if review is None:
            raise CurriculumValidationError(
                "review is required for complete lessons"
            )

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
        capability_progression=capability_progression,
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
        raise CurriculumValidationError(f"{label} has unknown fields")
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
    if type(value) is list and complete and not 3 <= len(value) <= 6:
        raise CurriculumValidationError(
            "complete lessons need 3 to 6 objectives"
        )
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


def _parse_capability_progression(
    value: object,
    evidence: tuple[Evidence, ...],
    *,
    complete: bool,
) -> tuple[CapabilityProgression, ...]:
    items = _require_list(
        value,
        "capabilityProgression",
        minimum=1,
        maximum=len(CAPABILITY_LEVELS),
    )
    fields = frozenset({"level", "criterion", "evidenceIds"})
    known_evidence = {item.id for item in evidence}
    progression: list[CapabilityProgression] = []
    for index, item in enumerate(items):
        raw = _require_exact_object(
            item,
            fields,
            fields,
            f"capability progression {index + 1}",
        )
        evidence_values = _require_list(
            raw["evidenceIds"],
            f"capability progression {index + 1} evidenceIds",
            minimum=1,
            maximum=12,
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
            "evidence id in capability progression",
        )
        unknown = sorted(set(evidence_ids) - known_evidence)
        if unknown:
            raise CurriculumValidationError(
                "capability progression has unknown evidence "
                f"{', '.join(unknown)}"
            )
        progression.append(
            CapabilityProgression(
                level=_require_choice(
                    raw["level"],
                    _CAPABILITY_LEVEL_SET,
                    "capability level",
                ),
                criterion=_require_text(
                    raw["criterion"],
                    f"capability progression {index + 1} criterion",
                    maximum=1_000,
                ),
                evidence_ids=evidence_ids,
            )
        )

    levels = tuple(item.level for item in progression)
    if len(set(levels)) != len(levels):
        raise CurriculumValidationError("duplicate capability level")
    if levels != CAPABILITY_LEVELS[: len(levels)]:
        raise CurriculumValidationError(
            "capability levels must be an ordered prefix"
        )
    if complete and len(levels) != len(CAPABILITY_LEVELS):
        raise CurriculumValidationError(
            "complete lessons need five capability levels"
        )
    return tuple(progression)


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
    identities: list[tuple[str, str, int | None, str, str]] = []
    for index, item in enumerate(items):
        raw = _require_exact_object(
            item, fields, fields, f"source {index + 1}"
        )
        url, identity = _require_https_url(raw["url"])
        identities.append(identity)
        sources.append(
            Source(
                title=_require_text(
                    raw["title"],
                    f"source {index + 1} title",
                    maximum=300,
                ),
                url=url,
                kind=_require_choice(
                    raw["kind"], SOURCE_KINDS, "source kind"
                ),
            )
        )
    if len(set(identities)) != len(identities):
        raise CurriculumValidationError("duplicate source URL")
    return tuple(sources)


def _require_https_url(
    value: object,
) -> tuple[str, tuple[str, str, int | None, str, str]]:
    url = _require_text(value, "source URL", maximum=2_048)
    if any(character.isspace() for character in url):
        raise CurriculumValidationError("source URL must not contain whitespace")
    if "\\" in url:
        raise CurriculumValidationError(
            "source URL backslashes are not allowed"
        )
    if _ENCODED_CONTROL_PATTERN.search(url):
        raise CurriculumValidationError(
            "source URL encoded controls are not allowed"
        )
    try:
        parsed = urlsplit(url)
    except ValueError:
        raise CurriculumValidationError("source URL is malformed") from None
    if parsed.scheme != "https":
        raise CurriculumValidationError("source URL must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise CurriculumValidationError(
            "source URL credentials are not allowed"
        )
    try:
        hostname = parsed.hostname
    except ValueError:
        raise CurriculumValidationError("source URL host is invalid") from None
    if hostname is None:
        raise CurriculumValidationError("source URL must have a host")
    if parsed.netloc.endswith(":"):
        raise CurriculumValidationError("source URL port is invalid")
    try:
        port = parsed.port
    except ValueError:
        raise CurriculumValidationError("source URL port is invalid") from None
    if port is not None and not 1 <= port <= 65_535:
        raise CurriculumValidationError("source URL port is invalid")

    normalized_host = _normalize_source_host(hostname)
    normalized_port = None if port in (None, 443) else port
    identity = (
        "https",
        normalized_host,
        normalized_port,
        parsed.path or "/",
        parsed.query,
    )
    return url, identity


def _normalize_source_host(hostname: str) -> str:
    without_root_dot = hostname[:-1] if hostname.endswith(".") else hostname
    if not without_root_dot or without_root_dot.endswith("."):
        raise CurriculumValidationError("source URL host is invalid")
    try:
        address = ipaddress.ip_address(without_root_dot)
    except ValueError:
        try:
            ascii_host = (
                without_root_dot.encode("idna").decode("ascii").lower()
            )
        except UnicodeError:
            raise CurriculumValidationError(
                "source URL host is invalid"
            ) from None
        if len(ascii_host) > 253:
            raise CurriculumValidationError("source URL host is invalid")
        labels = ascii_host.split(".")
        if not labels or any(
            _DNS_LABEL_PATTERN.fullmatch(label) is None for label in labels
        ):
            raise CurriculumValidationError("source URL host is invalid")
        return ascii_host
    return address.compressed.lower()


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
