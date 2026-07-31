"""Immutable, version-pinned mappings to official competency frameworks."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import re
from types import MappingProxyType
from typing import Final
import unicodedata

from .catalog import strict_json_loads
from .errors import CurriculumValidationError
from .lesson_io import read_stable_lesson_file


MAX_COMPETENCIES_BYTES: Final = 256 * 1024
MAX_RATIONALE_CHARS: Final = 1_000
MAX_SOURCE_NAME_CHARS: Final = 255
_MAX_TEXT_CHARS: Final = 256
_EXPECTED_MAPPING_COUNT: Final = 90
_FRAMEWORK_ORDER: Final = ("CS2023", "SWEBOK", "SFIA")
_ALIGNMENTS: Final = frozenset({"direct", "foundational", "partial"})
_FRAMEWORK_VERSIONS: Final = MappingProxyType(
    {
        "CS2023": "Final Report",
        "SWEBOK": "V4.0a",
        "SFIA": "9",
    }
)
_FRAMEWORK_SOURCES: Final = MappingProxyType(
    {
        "CS2023": (
            "Final Report",
            "https://csed.acm.org/final-report/",
            "2026-07-31",
        ),
        "SWEBOK": (
            "V4.0a",
            "https://www.computer.org/education/bodies-of-knowledge/"
            "software-engineering",
            "2026-07-31",
        ),
        "SFIA": (
            "9",
            "https://sfia-online.org/en/sfia-9/skills/"
            "all-skills-a-z?set_language=en",
            "2026-07-31",
        ),
    }
)
_ROOT_FIELDS: Final = frozenset(
    {
        "version",
        "frameworkVersions",
        "frameworkSources",
        "mappings",
    }
)
_SOURCE_FIELDS: Final = frozenset(
    {"version", "officialUrl", "verifiedAt"}
)
_MAPPING_FIELDS: Final = frozenset(
    {
        "targetId",
        "framework",
        "competencyId",
        "competencyName",
        "rationale",
        "alignment",
    }
)
_CORE_LESSON_ID: Final = re.compile(
    r"core-(0[1-9]|[12][0-9]|30)-[a-z0-9]+(?:-[a-z0-9]+)*\Z",
    re.ASCII,
)
_UNSAFE_TEXT_CATEGORIES: Final = frozenset(
    {"Cc", "Cf", "Cs", "Zl", "Zp"}
)

# These pairs are copied from the versioned primary sources named by the
# matrix. Pair validation matters: accepting a real code with a forged label
# would make the public table look authoritative while changing its meaning.
_CS2023_COMPETENCIES: Final = MappingProxyType(
    {
        "AI": "Artificial Intelligence",
        "AL": "Algorithmic Foundations",
        "AR": "Architecture and Organization",
        "DM": "Data Management",
        "FPL": "Foundations of Programming Languages",
        "GIT": "Graphics and Interactive Techniques",
        "HCI": "Human-Computer Interaction",
        "MSF": "Mathematical and Statistical Foundations",
        "NC": "Networking and Communication",
        "OS": "Operating Systems",
        "PDC": "Parallel and Distributed Computing",
        "SDF": "Software Development Fundamentals",
        "SE": "Software Engineering",
        "SEC": "Security",
        "SEP": "Society, Ethics, and the Profession",
        "SF": "Systems Fundamentals",
        "SPD": "Specialized Platform Development",
    }
)
_SWEBOK_COMPETENCIES: Final = MappingProxyType(
    {
        "CHAPTER 01": "Software Requirements",
        "CHAPTER 02": "Software Architecture",
        "CHAPTER 03": "Software Design",
        "CHAPTER 04": "Software Construction",
        "CHAPTER 05": "Software Testing",
        "CHAPTER 06": "Software Engineering Operations",
        "CHAPTER 07": "Software Maintenance",
        "CHAPTER 08": "Software Configuration Management",
        "CHAPTER 09": "Software Engineering Management",
        "CHAPTER 10": "Software Engineering Process",
        "CHAPTER 11": "Software Engineering Models and Methods",
        "CHAPTER 12": "Software Quality",
        "CHAPTER 13": "Software Security",
        "CHAPTER 14": "Software Engineering Professional Practice",
        "CHAPTER 15": "Software Engineering Economics",
        "CHAPTER 16": "Computing Foundations",
        "CHAPTER 17": "Mathematical Foundations",
        "CHAPTER 18": "Engineering Foundations",
    }
)
_SFIA_COMPETENCIES: Final = MappingProxyType(
    {
        "ACIN": "Accessibility and inclusion",
        "ARCH": "Solution architecture",
        "ASUP": "Application support",
        "CHMG": "Change control",
        "CPMG": "Capacity management",
        "DBDS": "Database design",
        "DESN": "Systems design",
        "DTAN": "Data modelling and design",
        "GOVN": "Governance",
        "IFDN": "Infrastructure design",
        "INCA": "Content design and authoring",
        "INVA": "Investment appraisal",
        "ITSP": "Strategic planning",
        "NTDS": "Network design",
        "OFCL": "Organisational facilitation",
        "ORDI": "Organisation design and implementation",
        "PEDP": "Information and data compliance",
        "PROG": "Programming/software development",
        "QUAS": "Quality assurance",
        "RELM": "Release management",
        "REQM": "Requirements definition and management",
        "SCTY": "Information security",
        "SLMO": "Service level management",
        "SWDN": "Software design",
        "TEST": "Functional testing",
        "URCH": "User research",
        "USUP": "Incident management",
        "VISL": "Data visualisation",
    }
)
_OFFICIAL_COMPETENCIES: Final = MappingProxyType(
    {
        "CS2023": _CS2023_COMPETENCIES,
        "SWEBOK": _SWEBOK_COMPETENCIES,
        "SFIA": _SFIA_COMPETENCIES,
    }
)
_CANONICAL_TARGET_IDS: Final = frozenset(
    {
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
    }
)


@dataclass(frozen=True, slots=True)
class CompetencyMapping:
    target_id: str
    framework: str
    competency_id: str
    competency_name: str
    rationale: str
    alignment: str


@dataclass(frozen=True, slots=True)
class FrameworkSource:
    version: str
    official_url: str
    verified_at: str


@dataclass(frozen=True, slots=True)
class CompetencyMatrix:
    framework_versions: Mapping[str, str]
    framework_sources: Mapping[str, FrameworkSource]
    mappings: tuple[CompetencyMapping, ...]


def _validation(message: str) -> CurriculumValidationError:
    return CurriculumValidationError(message)


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
    maximum_chars: int = _MAX_TEXT_CHARS,
) -> str:
    if type(value) is not str:
        raise _validation(f"{label} must be a string")
    if (
        not value
        or value != value.strip()
        or len(value) > maximum_chars
        or any(
            unicodedata.category(character) in _UNSAFE_TEXT_CATEGORIES
            for character in value
        )
    ):
        raise _validation(
            f"{label} must be non-empty, unpadded, bounded, and safe"
        )
    return value


def _expected_targets(
    value: object,
) -> frozenset[str]:
    if type(value) is not frozenset:
        raise _validation("expected_target_ids must be a frozenset")
    if (
        len(value) != 30
        or any(
            type(target_id) is not str
            or _CORE_LESSON_ID.fullmatch(target_id) is None
            for target_id in value
        )
    ):
        raise _validation(
            "expected_target_ids must contain exactly 30 canonical lesson IDs"
        )
    return value


def parse_competencies_bytes(
    raw: bytes,
    *,
    expected_target_ids: frozenset[str],
    source_name: str,
) -> CompetencyMatrix:
    """Parse one exact matrix snapshot and reject incomplete authority claims."""
    if type(raw) is not bytes:
        raise _validation("competency snapshot must be exact bytes")
    if len(raw) > MAX_COMPETENCIES_BYTES:
        raise _validation("competencies exceed maximum byte count")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        raise _validation("competencies must be valid UTF-8") from None
    source = _text(
        source_name,
        "competency source name",
        maximum_chars=MAX_SOURCE_NAME_CHARS,
    )
    expected_targets = _expected_targets(expected_target_ids)
    document = strict_json_loads(raw, source)
    if not isinstance(document, Mapping):
        raise _validation("competency root must be an object")
    _exact_fields(document, _ROOT_FIELDS, "competency root")
    if type(document["version"]) is not int or document["version"] != 1:
        raise _validation("competency version must be integer 1")

    raw_versions = document["frameworkVersions"]
    if not isinstance(raw_versions, Mapping):
        raise _validation("frameworkVersions must be an object")
    _exact_fields(
        raw_versions,
        frozenset(_FRAMEWORK_VERSIONS),
        "frameworkVersions",
    )
    if dict(raw_versions) != dict(_FRAMEWORK_VERSIONS):
        raise _validation(
            "framework versions must be exactly CS2023 Final Report, "
            "SWEBOK V4.0a, and SFIA 9"
        )

    raw_sources = document["frameworkSources"]
    if not isinstance(raw_sources, Mapping):
        raise _validation("frameworkSources must be an object")
    _exact_fields(
        raw_sources,
        frozenset(_FRAMEWORK_SOURCES),
        "frameworkSources",
    )
    sources: dict[str, FrameworkSource] = {}
    for framework in _FRAMEWORK_ORDER:
        raw_source = raw_sources[framework]
        if not isinstance(raw_source, Mapping):
            raise _validation(
                f"frameworkSources {framework} must be an object"
            )
        _exact_fields(
            raw_source,
            _SOURCE_FIELDS,
            f"frameworkSources {framework}",
        )
        version = _text(
            raw_source["version"],
            f"frameworkSources {framework} version",
        )
        official_url = _text(
            raw_source["officialUrl"],
            f"frameworkSources {framework} officialUrl",
        )
        verified_at = _text(
            raw_source["verifiedAt"],
            f"frameworkSources {framework} verifiedAt",
        )
        if (
            version,
            official_url,
            verified_at,
        ) != _FRAMEWORK_SOURCES[framework]:
            raise _validation(
                f"frameworkSources {framework} must match the verified source"
            )
        if version != raw_versions[framework]:
            raise _validation(
                f"frameworkSources {framework} version must match "
                "frameworkVersions"
            )
        sources[framework] = FrameworkSource(
            version=version,
            official_url=official_url,
            verified_at=verified_at,
        )

    raw_mappings = document["mappings"]
    if type(raw_mappings) is not list:
        raise _validation("competency mappings must be a list")
    if len(raw_mappings) != _EXPECTED_MAPPING_COUNT:
        raise _validation("competency matrix must contain exactly 90 mappings")

    mappings: list[CompetencyMapping] = []
    for index, value in enumerate(raw_mappings):
        if not isinstance(value, Mapping):
            raise _validation(f"competency mapping {index} must be an object")
        _exact_fields(
            value,
            _MAPPING_FIELDS,
            f"competency mapping {index}",
        )
        target_id = _text(
            value["targetId"],
            f"competency mapping {index} targetId",
        )
        framework = _text(
            value["framework"],
            f"competency mapping {index} framework",
        )
        competency_id = _text(
            value["competencyId"],
            f"competency mapping {index} competencyId",
        )
        competency_name = _text(
            value["competencyName"],
            f"competency mapping {index} competencyName",
        )
        rationale = _text(
            value["rationale"],
            f"competency mapping {index} rationale",
            maximum_chars=MAX_RATIONALE_CHARS,
        )
        alignment = _text(
            value["alignment"],
            f"competency mapping {index} alignment",
        )
        if alignment not in _ALIGNMENTS:
            raise _validation(
                f"competency mapping {index} alignment must be direct, "
                "foundational, or partial"
            )
        if target_id not in expected_targets:
            raise _validation(
                f"competency mapping {index} targetId is not a loaded lesson"
            )
        official = _OFFICIAL_COMPETENCIES.get(framework)
        if (
            official is None
            or official.get(competency_id) != competency_name
        ):
            raise _validation(
                f"competency mapping {index} is not an official competency pair"
            )
        mappings.append(
            CompetencyMapping(
                target_id=target_id,
                framework=framework,
                competency_id=competency_id,
                competency_name=competency_name,
                rationale=rationale,
                alignment=alignment,
            )
        )

    pair_counts = Counter(
        (mapping.target_id, mapping.framework)
        for mapping in mappings
    )
    if any(count != 1 for count in pair_counts.values()):
        raise _validation(
            "each lesson and framework pair must occur exactly once"
        )
    if frozenset(pair_counts) != frozenset(
        (target_id, framework)
        for target_id in expected_targets
        for framework in _FRAMEWORK_ORDER
    ):
        raise _validation(
            "every loaded lesson must map to all three frameworks exactly once"
        )

    framework_rank = {
        framework: index
        for index, framework in enumerate(_FRAMEWORK_ORDER)
    }
    # The checked-in JSON may be reorganized for review, but generated output
    # must remain stable so an identical curriculum produces identical bytes.
    ordered = tuple(
        sorted(
            mappings,
            key=lambda mapping: (
                mapping.target_id,
                framework_rank[mapping.framework],
            ),
        )
    )
    return CompetencyMatrix(
        framework_versions=MappingProxyType(dict(_FRAMEWORK_VERSIONS)),
        framework_sources=MappingProxyType(sources),
        mappings=ordered,
    )


def load_competencies(
    path: Path,
    *,
    expected_target_ids: frozenset[str] = _CANONICAL_TARGET_IDS,
) -> CompetencyMatrix:
    """Load through the shared descriptor-pinned, symlink-free file boundary."""
    if not isinstance(path, Path):
        raise _validation("competency path must be a Path")
    raw = read_stable_lesson_file(path, MAX_COMPETENCIES_BYTES)
    return parse_competencies_bytes(
        raw,
        expected_target_ids=expected_target_ids,
        source_name=path.name or "competencies.json",
    )
