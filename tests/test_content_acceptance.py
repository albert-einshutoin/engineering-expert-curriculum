from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import re
import stat
import string
from tempfile import TemporaryDirectory
import unicodedata
import unittest

from curriculum_builder.build import build_site
from curriculum_builder.capstones import parse_capstone_documents
from curriculum_builder.competencies import parse_competencies_bytes
from curriculum_builder.errors import CurriculumValidationError


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTENT_STANDARD = REPOSITORY_ROOT / "docs/content-standard.md"
CURRICULUM_MAP = REPOSITORY_ROOT / "docs/curriculum-map.md"
BEGIN_GENERATED_MAP = "<!-- BEGIN GENERATED CURRICULUM MAP -->"
END_GENERATED_MAP = "<!-- END GENERATED CURRICULUM MAP -->"
LESSON_IDS = (
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
CAPSTONE_IDS = ("global-service", "legacy-evolution", "oss-launch")
CATALOG_SHA256 = (
    "4f38b5f63931a7f06e13f90f5d9ef90a0a435f30dae5d4fe70720d730a057473"
)
FRAMEWORKS = ("CS2023", "SWEBOK", "SFIA")
FRAMEWORK_VERSIONS = {
    "CS2023": "Final Report",
    "SWEBOK": "V4.0a",
    "SFIA": "9",
}
FRAMEWORK_SOURCES = {
    "CS2023": {
        "version": "Final Report",
        "officialUrl": "https://csed.acm.org/final-report/",
        "verifiedAt": "2026-07-31",
    },
    "SWEBOK": {
        "version": "V4.0a",
        "officialUrl": (
            "https://www.computer.org/education/bodies-of-knowledge/"
            "software-engineering"
        ),
        "verifiedAt": "2026-07-31",
    },
    "SFIA": {
        "version": "9",
        "officialUrl": (
            "https://sfia-online.org/en/sfia-9/skills/"
            "all-skills-a-z?set_language=en"
        ),
        "verifiedAt": "2026-07-31",
    },
}
EXPECTED_PREREQUISITES = {
    "core-01-systems-tradeoffs": (),
    "core-02-algorithms-measurement": ("core-01-systems-tradeoffs",),
    "core-03-architecture-memory-caches": ("core-01-systems-tradeoffs",),
    "core-04-os-processes-concurrency": (
        "core-02-algorithms-measurement",
        "core-03-architecture-memory-caches",
    ),
    "core-05-networks-latency-failure": (
        "core-04-os-processes-concurrency",
    ),
    "core-06-requirements-domain-modeling": (
        "core-01-systems-tradeoffs",
    ),
    "core-07-api-contract-design": (
        "core-06-requirements-domain-modeling",
    ),
    "core-08-modularity-evolutionary-architecture": (
        "core-06-requirements-domain-modeling",
        "core-07-api-contract-design",
    ),
    "core-09-test-strategy-tdd": (
        "core-02-algorithms-measurement",
        "core-08-modularity-evolutionary-architecture",
    ),
    "core-10-threat-modeling-secure-design": (
        "core-07-api-contract-design",
        "core-09-test-strategy-tdd",
    ),
    "core-11-data-modeling-storage": (
        "core-06-requirements-domain-modeling",
    ),
    "core-12-transactions-isolation-consistency": (
        "core-11-data-modeling-storage",
    ),
    "core-13-distributed-coordination-failure": (
        "core-05-networks-latency-failure",
        "core-12-transactions-isolation-consistency",
    ),
    "core-14-performance-capacity": (
        "core-02-algorithms-measurement",
        "core-03-architecture-memory-caches",
        "core-11-data-modeling-storage",
    ),
    "core-15-reliability-observability-slo": (
        "core-05-networks-latency-failure",
        "core-13-distributed-coordination-failure",
        "core-14-performance-capacity",
    ),
    "core-16-hci-usability-accessibility": (
        "core-06-requirements-domain-modeling",
    ),
    "core-17-graphics-visual-information": (
        "core-03-architecture-memory-caches",
        "core-16-hci-usability-accessibility",
    ),
    "core-18-product-discovery-experiments": (
        "core-06-requirements-domain-modeling",
        "core-16-hci-usability-accessibility",
    ),
    "core-19-technical-communication-design-docs": (
        "core-01-systems-tradeoffs",
        "core-06-requirements-domain-modeling",
    ),
    "core-20-ethics-privacy-societal-impact": (
        "core-10-threat-modeling-secure-design",
        "core-16-hci-usability-accessibility",
        "core-19-technical-communication-design-docs",
    ),
    "core-21-maintenance-legacy-comprehension": (
        "core-08-modularity-evolutionary-architecture",
        "core-09-test-strategy-tdd",
    ),
    "core-22-evolution-safe-migrations": (
        "core-08-modularity-evolutionary-architecture",
        "core-12-transactions-isolation-consistency",
        "core-21-maintenance-legacy-comprehension",
    ),
    "core-23-incident-response-learning": (
        "core-15-reliability-observability-slo",
        "core-21-maintenance-legacy-comprehension",
    ),
    "core-24-delivery-ci-release-safety": (
        "core-09-test-strategy-tdd",
        "core-15-reliability-observability-slo",
    ),
    "core-25-engineering-economics-capacity": (
        "core-14-performance-capacity",
        "core-15-reliability-observability-slo",
        "core-24-delivery-ci-release-safety",
    ),
    "core-26-code-review-collaborative-quality": (
        "core-09-test-strategy-tdd",
        "core-19-technical-communication-design-docs",
    ),
    "core-27-team-interfaces-sociotechnical-architecture": (
        "core-08-modularity-evolutionary-architecture",
        "core-19-technical-communication-design-docs",
        "core-26-code-review-collaborative-quality",
    ),
    "core-28-oss-governance-stewardship": (
        "core-10-threat-modeling-secure-design",
        "core-19-technical-communication-design-docs",
        "core-26-code-review-collaborative-quality",
    ),
    "core-29-cross-cultural-async-collaboration": (
        "core-19-technical-communication-design-docs",
        "core-27-team-interfaces-sociotechnical-architecture",
    ),
    "core-30-evidence-based-technical-leadership": (
        "core-20-ethics-privacy-societal-impact",
        "core-25-engineering-economics-capacity",
        "core-27-team-interfaces-sociotechnical-architecture",
        "core-28-oss-governance-stewardship",
        "core-29-cross-cultural-async-collaboration",
    ),
}
EXPECTED_MASTERY_GATES = (
    {
        "id": "foundation",
        "after": 5,
        "artifact": "未知システムの診断記録",
        "review": "機構と証拠を説明できる",
    },
    {
        "id": "builder",
        "after": 10,
        "artifact": "契約・テスト・脅威モデル付きサービス",
        "review": "信頼性を設計へ埋め込める",
    },
    {
        "id": "scaler",
        "after": 15,
        "artifact": "負荷・障害・SLO実験",
        "review": "分散失敗を測定し判断できる",
    },
    {
        "id": "human",
        "after": 20,
        "artifact": "アクセシブルな検証済み改善",
        "review": "人と社会への影響を説明できる",
    },
    {
        "id": "operator",
        "after": 25,
        "artifact": "移行・運用・費用計画",
        "review": "変更を安全かつ経済的に進められる",
    },
    {
        "id": "leader",
        "after": 30,
        "artifact": "他者が実行可能な技術方針",
        "review": "不確実性の中で組織を前進させられる",
    },
)
EXPECTED_PRIMARY_OWNER = {
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
CAPSTONE_EVIDENCE_KINDS = ("build", "operate", "explain", "review")
_LESSON_MAP_ROW = re.compile(
    r"^\| (?P<ordinal>[1-9]|[12][0-9]|30) \| "
    r"`(?P<lesson>core-(?:0[1-9]|[12][0-9]|30)-[a-z0-9-]+)`<br>"
)
REVIEW_ROLES = (
    "技術的正確性",
    "学習設計・証拠",
    "アクセシビリティ",
    "編集・出典",
)
EVIDENCE_LOOP = ("Learn", "Practice", "Explain", "Prove", "Transfer", "Review")
AUTHORED_HEADINGS = (
    "なぜ重要か",
    "メンタルモデル",
    "動く例で考える",
    "トレードオフと失敗モード",
    "知識チェック",
    "出典と次の学習",
)
EVIDENCE_KINDS = frozenset(
    {"artifact", "explanation", "reasoning", "transfer"}
)
CAPABILITY_LEVELS = ("recognize", "explain", "apply", "diagnose", "lead")
RUBRIC_DIMENSIONS = (
    "technical-correctness",
    "judgment",
    "evidence",
    "communication",
)
RUBRIC_LEVELS = frozenset(
    {"incomplete", "developing", "proficient", "exemplary"}
)


@dataclass(frozen=True, slots=True)
class _ParsedSection:
    heading: str
    body: str


@dataclass(frozen=True, slots=True)
class _EvidenceItem:
    id: str
    kind: str


@dataclass(frozen=True, slots=True)
class _EvidenceContract:
    lesson_id: str
    evidence: tuple[_EvidenceItem, ...]
    objective_references: frozenset[str]
    capability_references: frozenset[str]


class _AuthoredBodyParser(HTMLParser):
    """Read authored semantics without sharing the production HTML validator."""

    _HIDDEN_ELEMENTS = frozenset({"script", "style", "template", "noscript"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: list[_ParsedSection] = []
        self.visible_parts: list[str] = []
        self._hidden_depth = 0
        self._heading_depth = 0
        self._heading_seen = False
        self._heading_parts: list[str] = []
        self._body_parts: list[str] = []
        self._section_depth = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del attrs
        tag = tag.casefold()
        if tag in self._HIDDEN_ELEMENTS:
            self._hidden_depth += 1
            return
        if self._hidden_depth:
            return
        if tag == "section":
            if self._section_depth == 0:
                self._heading_seen = False
                self._heading_parts = []
                self._body_parts = []
            self._section_depth += 1
        elif tag == "h2" and self._section_depth == 1:
            if self._heading_depth:
                raise AssertionError("authored h2 elements must not be nested")
            if self._heading_seen:
                raise AssertionError("each authored section must contain one h2")
            self._heading_seen = True
            self._heading_depth = 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in self._HIDDEN_ELEMENTS:
            if self._hidden_depth:
                self._hidden_depth -= 1
            return
        if self._hidden_depth:
            return
        if tag == "h2" and self._heading_depth:
            self._heading_depth = 0
        elif tag == "section":
            if not self._section_depth:
                raise AssertionError("unexpected authored section close")
            self._section_depth -= 1
            if self._section_depth == 0:
                self.sections.append(
                    _ParsedSection(
                        heading=_normalize_visible_text(self._heading_parts),
                        body=_normalize_visible_text(self._body_parts),
                    )
                )

    def handle_data(self, data: str) -> None:
        if self._hidden_depth:
            return
        self.visible_parts.append(data)
        if not self._section_depth:
            return
        if self._heading_depth:
            self._heading_parts.append(data)
        else:
            self._body_parts.append(data)

    def finish(self) -> tuple[tuple[_ParsedSection, ...], str]:
        self.close()
        if self._section_depth or self._heading_depth:
            raise AssertionError("authored section markup is incomplete")
        return tuple(self.sections), _normalize_visible_text(self.visible_parts)


def _normalize_visible_text(parts: list[str] | tuple[str, ...]) -> str:
    joined = " ".join(parts)
    return " ".join(unicodedata.normalize("NFKC", joined).casefold().split())


def _parse_authored_body(source: str) -> tuple[tuple[_ParsedSection, ...], str]:
    parser = _AuthoredBodyParser()
    parser.feed(source)
    return parser.finish()


def _assert_unique_visible_bodies(bodies: dict[str, str]) -> set[str]:
    owners: dict[str, str] = {}
    for lesson_id, body in bodies.items():
        normalized = _normalize_visible_text([body])
        if not normalized:
            raise AssertionError(f"{lesson_id}: visible body must not be empty")
        if normalized in owners:
            raise AssertionError(
                f"duplicate visible body: {owners[normalized]} and {lesson_id}"
            )
        owners[normalized] = lesson_id
    return set(owners)


def _evidence_contract(document: dict[str, object]) -> _EvidenceContract:
    evidence = tuple(
        _EvidenceItem(item["id"], item["kind"])
        for item in document["evidence"]  # type: ignore[index,union-attr]
    )
    objective_references = frozenset(
        evidence_id
        for objective in document["objectives"]  # type: ignore[union-attr]
        for evidence_id in objective["evidenceIds"]
    )
    capability_references = frozenset(
        evidence_id
        for level in document["capabilityProgression"]  # type: ignore[union-attr]
        for evidence_id in level["evidenceIds"]
    )
    return _EvidenceContract(
        lesson_id=document["id"],  # type: ignore[arg-type]
        evidence=evidence,
        objective_references=objective_references,
        capability_references=capability_references,
    )


def _assert_evidence_references(contract: _EvidenceContract) -> None:
    evidence_ids = [item.id for item in contract.evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise AssertionError(f"{contract.lesson_id}: evidence IDs must be unique")
    if {item.kind for item in contract.evidence} != EVIDENCE_KINDS:
        raise AssertionError(
            f"{contract.lesson_id}: evidence kinds must match the contract"
        )
    expected = frozenset(evidence_ids)
    if contract.objective_references != expected:
        raise AssertionError(
            f"{contract.lesson_id}: orphan or unknown objective evidence"
        )
    if contract.capability_references != expected:
        raise AssertionError(
            f"{contract.lesson_id}: orphan or unknown capability evidence"
        )


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _expected_artifacts() -> frozenset[PurePosixPath]:
    paths = {
        PurePosixPath("index.html"),
        PurePosixPath("styles.css"),
        PurePosixPath("catalog/index.html"),
        PurePosixPath("roadmap/index.html"),
        PurePosixPath("competencies/index.html"),
        PurePosixPath("lessons/index.html"),
        PurePosixPath("capstones/index.html"),
    }
    paths.update(
        PurePosixPath("lessons") / lesson_id / "index.html"
        for lesson_id in LESSON_IDS
    )
    paths.update(
        PurePosixPath("capstones") / capstone_id / "index.html"
        for capstone_id in CAPSTONE_IDS
    )
    return frozenset(paths)


def _snapshot(root: Path) -> dict[PurePosixPath, bytes]:
    return {
        PurePosixPath(path.relative_to(root).as_posix()): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _json_bytes(document: object) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _extract_generated_map(document: str) -> str:
    if document.count(BEGIN_GENERATED_MAP) != 1:
        raise AssertionError("curriculum map needs exactly one start marker")
    if document.count(END_GENERATED_MAP) != 1:
        raise AssertionError("curriculum map needs exactly one end marker")
    start = document.index(BEGIN_GENERATED_MAP)
    end = document.index(END_GENERATED_MAP)
    if start >= end:
        raise AssertionError("curriculum map markers are out of order")
    return document[start : end + len(END_GENERATED_MAP)]


_CANONICAL_DECIMAL_ENTITY = re.compile(r"&#([0-9]{1,3});")
_ENTITY_PUNCTUATION = frozenset(string.punctuation) - {"\\", "|"}


def _split_markdown_table_row(line: str) -> tuple[str, ...]:
    """Split only the two backslash escapes production can generate."""
    if not line.startswith("|") or not line.endswith("|"):
        raise AssertionError("generated map row must start and end with a pipe")
    cells: list[str] = []
    current: list[str] = []
    index = 1
    while index < len(line) - 1:
        character = line[index]
        if character == "\\":
            if index + 1 >= len(line) - 1:
                raise AssertionError("generated map row has a dangling escape")
            escaped = line[index + 1]
            if escaped not in {"\\", "|"}:
                raise AssertionError("generated map row has an unsupported escape")
            current.extend(("\\", escaped))
            index += 2
            continue
        elif character == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
        index += 1
    cells.append("".join(current).strip())
    return tuple(cells)


def _decode_generated_cell(value: str) -> str:
    decoded: list[str] = []
    index = 0
    while index < len(value):
        character = value[index]
        if character == "\\":
            if index + 1 >= len(value) or value[index + 1] not in {"\\", "|"}:
                raise AssertionError("generated map row has an unsupported escape")
            decoded.append(value[index + 1])
            index += 2
            continue
        if character == "&":
            match = _CANONICAL_DECIMAL_ENTITY.match(value, index)
            if match is None:
                raise AssertionError("generated map row has an unsupported entity")
            codepoint = int(match.group(1))
            if (
                match.group(1) != str(codepoint)
                or chr(codepoint) not in _ENTITY_PUNCTUATION
            ):
                raise AssertionError("generated map row has a noncanonical entity")
            decoded.append(chr(codepoint))
            index = match.end()
            continue
        decoded.append(character)
        index += 1
    return "".join(decoded)


def _parse_markdown_table_row(line: str) -> tuple[str, ...]:
    """Parse one canonical generated row without production rendering code."""
    return tuple(
        _decode_generated_cell(cell)
        for cell in _split_markdown_table_row(line)
    )


def _encode_expected_markdown_text(value: str) -> str:
    """Independently specify the only plain-text spelling accepted by the map."""
    encoded: list[str] = []
    for character in value:
        if character == "\\":
            encoded.append("\\\\")
        elif character == "|":
            encoded.append("\\|")
        elif character in string.punctuation:
            encoded.append(f"&#{ord(character)};")
        else:
            encoded.append(character)
    return "".join(encoded)


def _encode_expected_mapping_cell(mapping: dict[str, str]) -> str:
    return (
        f"`{_encode_expected_markdown_text(mapping['competencyId'])}` "
        f"{_encode_expected_markdown_text(mapping['competencyName'])} "
        f"({_encode_expected_markdown_text(mapping['alignment'])})"
    )


def _encode_expected_table_row(cells: tuple[str, ...]) -> str:
    return "| " + " | ".join(cells) + " |"


def _map_section(
    block: str,
    heading: str,
    next_heading: str | None,
) -> tuple[str, ...]:
    start_marker = f"### {heading}\n"
    if block.count(start_marker) != 1:
        raise AssertionError(f"generated map needs one {heading} section")
    section = block.split(start_marker, maxsplit=1)[1]
    if next_heading is not None:
        end_marker = f"\n### {next_heading}\n"
        if section.count(end_marker) != 1:
            raise AssertionError(
                f"generated map needs one {next_heading} section boundary"
            )
        section = section.split(end_marker, maxsplit=1)[0]
    return tuple(section.splitlines())


def _map_table_rows(
    block: str,
    heading: str,
    next_heading: str | None,
    header: str,
    separator: str,
    expected_rows: int,
) -> tuple[str, ...]:
    """Consume every nonblank line so injected content cannot hide in a section."""
    content = tuple(
        line
        for line in _map_section(block, heading, next_heading)
        if line
    )
    if next_heading is None:
        if not content or content[-1] != END_GENERATED_MAP:
            raise AssertionError("generated map must end after its final table")
        content = content[:-1]
    if any(not line.startswith("|") or not line.endswith("|") for line in content):
        raise AssertionError(f"generated map {heading} contains unexpected content")
    if content[:2] != (header, separator):
        raise AssertionError(f"generated map {heading} table header drifted")
    rows = content[2:]
    if len(rows) != expected_rows:
        raise AssertionError(f"generated map {heading} row count drifted")
    return rows


def _assert_generated_map_contract(
    document: str,
    repository_root: Path = REPOSITORY_ROOT,
) -> None:
    block = _extract_generated_map(document)
    expected_release_rows = (
        "| 保存カタログ | 1,140 items |",
        f"| カタログ SHA-256 | `{CATALOG_SHA256}` |",
        "| コアレッスン | 30 structurally complete lessons |",
        "| コンピテンシー対応 | 90 mappings |",
        "| 統合 Capstone | 3 projects |",
        "| Primary exercise coverage | 30/30 |",
    )
    release_rows = _map_table_rows(
        block,
        "リリース集計",
        "Framework baseline",
        "| 項目 | 件数・固定値 |",
        "|---|---|",
        len(expected_release_rows),
    )
    if release_rows != expected_release_rows:
        raise AssertionError("generated map release rows are not canonical")

    framework_lines = _map_table_rows(
        block,
        "Framework baseline",
        "Mastery gates",
        "| Framework | Version | Official source | Verified |",
        "|---|---|---|---|",
        len(FRAMEWORKS),
    )
    framework_rows = tuple(
        _parse_markdown_table_row(line)
        for line in framework_lines
    )
    expected_framework_rows = tuple(
        (
            framework,
            FRAMEWORK_SOURCES[framework]["version"],
            f"[{framework}]({FRAMEWORK_SOURCES[framework]['officialUrl']})",
            FRAMEWORK_SOURCES[framework]["verifiedAt"],
        )
        for framework in FRAMEWORKS
    )
    if framework_rows != expected_framework_rows:
        raise AssertionError("generated map framework baseline is not canonical")
    expected_framework_raw_rows = tuple(
        (
            framework,
            _encode_expected_markdown_text(
                FRAMEWORK_SOURCES[framework]["version"]
            ),
            f"[{framework}]({FRAMEWORK_SOURCES[framework]['officialUrl']})",
            FRAMEWORK_SOURCES[framework]["verifiedAt"],
        )
        for framework in FRAMEWORKS
    )
    if framework_lines != tuple(
        _encode_expected_table_row(row)
        for row in expected_framework_raw_rows
    ):
        raise AssertionError("generated map framework encoding is not canonical")

    gate_lines = _map_table_rows(
        block,
        "Mastery gates",
        "30-lesson release map",
        "| Order | Gate | After | Artifact | Review evidence |",
        "|---:|---|---:|---|---|",
        len(EXPECTED_MASTERY_GATES),
    )
    gate_rows = tuple(
        _parse_markdown_table_row(line)
        for line in gate_lines
    )
    expected_gate_rows = tuple(
        (
            str(order),
            f"`{gate['id']}`",
            str(gate["after"]),
            gate["artifact"],
            gate["review"],
        )
        for order, gate in enumerate(EXPECTED_MASTERY_GATES, start=1)
    )
    if gate_rows != expected_gate_rows:
        raise AssertionError("generated map mastery gates are not canonical")
    expected_gate_raw_rows = tuple(
        (
            str(order),
            f"`{gate['id']}`",
            str(gate["after"]),
            _encode_expected_markdown_text(gate["artifact"]),
            _encode_expected_markdown_text(gate["review"]),
        )
        for order, gate in enumerate(EXPECTED_MASTERY_GATES, start=1)
    )
    if gate_lines != tuple(
        _encode_expected_table_row(row) for row in expected_gate_raw_rows
    ):
        raise AssertionError("generated map mastery gate encoding drifted")

    lesson_documents = {
        lesson_id: json.loads(
            (
                repository_root
                / "content/lessons"
                / lesson_id
                / "lesson.json"
            ).read_bytes()
        )
        for lesson_id in LESSON_IDS
    }
    competency_document = json.loads(
        (repository_root / "content/competencies.json").read_bytes()
    )
    mappings = {
        (mapping["targetId"], mapping["framework"]): mapping
        for mapping in competency_document["mappings"]
    }
    capstone_documents = {
        capstone_id: json.loads(
            (
                repository_root
                / "content/capstones"
                / f"{capstone_id}.json"
            ).read_bytes()
        )
        for capstone_id in CAPSTONE_IDS
    }

    lesson_lines = _map_table_rows(
        block,
        "30-lesson release map",
        "Capstone coverage",
        "| # | Lesson | Track / Stage | Prerequisites | Mastery gate | "
        "CS2023 | SWEBOK | SFIA | Primary / Supporting Capstone |",
        "|---:|---|---|---|---|---|---|---|---|",
        len(LESSON_IDS),
    )
    parsed_lesson_rows = []
    for line in lesson_lines:
        match = _LESSON_MAP_ROW.match(line)
        if match is None:
            raise AssertionError("generated map contains an invalid lesson row")
        parsed_lesson_rows.append(
            (match, line, _parse_markdown_table_row(line))
        )
    lesson_rows = tuple(parsed_lesson_rows)
    if len(lesson_rows) != 30:
        raise AssertionError("generated map must contain exactly 30 lesson rows")
    if tuple(
        match.group("lesson") for match, _line, _cells in lesson_rows
    ) != LESSON_IDS:
        raise AssertionError("generated map lesson IDs do not match the release")
    if tuple(
        int(match.group("ordinal"))
        for match, _line, _cells in lesson_rows
    ) != tuple(range(1, 31)):
        raise AssertionError("generated map lesson ordinals are not canonical")

    mapping_cells: list[str] = []
    for match, _line, cells in lesson_rows:
        if len(cells) != 9:
            raise AssertionError("lesson rows must contain exactly nine cells")
        lesson_id = match.group("lesson")
        ordinal = int(match.group("ordinal"))
        lesson = lesson_documents[lesson_id]
        expected_prerequisites = EXPECTED_PREREQUISITES[lesson_id]
        expected_prerequisite_cell = "<br>".join(
            f"`{value}`" for value in expected_prerequisites
        ) or "—"
        expected_gate = next(
            gate["id"]
            for gate in EXPECTED_MASTERY_GATES
            if ordinal <= gate["after"]
        )
        if cells[:5] != (
            str(ordinal),
            f"`{lesson_id}`<br>{lesson['title']}",
            f"{lesson['track']} / {lesson['stage']}",
            expected_prerequisite_cell,
            f"`{expected_gate}`",
        ):
            raise AssertionError(
                f"generated map lesson identity, prerequisite, or gate drifted: "
                f"{lesson_id}"
            )
        framework_cells = cells[5:8]
        expected_framework_cells = tuple(
            (
                f"`{mappings[(lesson_id, framework)]['competencyId']}` "
                f"{mappings[(lesson_id, framework)]['competencyName']} "
                f"({mappings[(lesson_id, framework)]['alignment']})"
            )
            for framework in FRAMEWORKS
        )
        if framework_cells != expected_framework_cells:
            raise AssertionError(
                f"generated map framework mapping drifted: {lesson_id}"
            )
        mapping_cells.extend(framework_cells)
        expected_owner = EXPECTED_PRIMARY_OWNER[lesson_id]
        supporting = tuple(
            capstone_id
            for capstone_id in CAPSTONE_IDS
            if lesson_id in capstone_documents[capstone_id]["lessonIds"]
            and capstone_id != expected_owner
        )
        expected_capstone_cell = f"Primary: `{expected_owner}`"
        if supporting:
            expected_capstone_cell += "<br>Supporting: " + ", ".join(
                f"`{value}`" for value in supporting
            )
        if cells[8] != expected_capstone_cell:
            raise AssertionError(
                f"generated map capstone ownership drifted: {lesson_id}"
            )
        expected_framework_raw_cells = tuple(
            _encode_expected_mapping_cell(mappings[(lesson_id, framework)])
            for framework in FRAMEWORKS
        )
        expected_raw_cells = (
            str(ordinal),
            f"`{lesson_id}`<br>"
            f"{_encode_expected_markdown_text(lesson['title'])}",
            f"{_encode_expected_markdown_text(lesson['track'])} / "
            f"{lesson['stage']}",
            expected_prerequisite_cell,
            f"`{expected_gate}`",
            *expected_framework_raw_cells,
            expected_capstone_cell,
        )
        if _line != _encode_expected_table_row(expected_raw_cells):
            raise AssertionError(
                f"generated map lesson encoding drifted: {lesson_id}"
            )
    if len(mapping_cells) != 90:
        raise AssertionError("generated map must expose exactly 90 mapping cells")

    capstone_lines = _map_table_rows(
        block,
        "Capstone coverage",
        None,
        "| Capstone | Lessons | Primary exercises | Evidence kinds |",
        "|---|---:|---:|---|",
        len(CAPSTONE_IDS),
    )
    if any(
        re.match(
            r"^\| `(?:global-service|legacy-evolution|oss-launch)` — ",
            line,
        )
        is None
        for line in capstone_lines
    ):
        raise AssertionError("generated map contains an invalid capstone row")
    capstone_rows = tuple(
        _parse_markdown_table_row(line) for line in capstone_lines
    )
    expected_capstone_rows = tuple(
        (
            f"`{capstone_id}` — {capstone_documents[capstone_id]['title']}",
            str(len(capstone_documents[capstone_id]["lessonIds"])),
            str(len(capstone_documents[capstone_id]["primaryExercises"])),
            ", ".join(f"`{kind}`" for kind in CAPSTONE_EVIDENCE_KINDS),
        )
        for capstone_id in CAPSTONE_IDS
    )
    if capstone_rows != expected_capstone_rows:
        raise AssertionError("generated map capstone coverage drifted")
    expected_capstone_raw_rows = tuple(
        (
            f"`{capstone_id}` — "
            f"{_encode_expected_markdown_text(capstone_documents[capstone_id]['title'])}",
            str(len(capstone_documents[capstone_id]["lessonIds"])),
            str(len(capstone_documents[capstone_id]["primaryExercises"])),
            ", ".join(f"`{kind}`" for kind in CAPSTONE_EVIDENCE_KINDS),
        )
        for capstone_id in CAPSTONE_IDS
    )
    if capstone_lines != tuple(
        _encode_expected_table_row(row)
        for row in expected_capstone_raw_rows
    ):
        raise AssertionError("generated map capstone encoding drifted")


class ContentAcceptanceTests(unittest.TestCase):
    def test_catalog_bytes_and_identity_are_bound_to_the_preserved_release(
        self,
    ) -> None:
        raw = (REPOSITORY_ROOT / "content/catalog.json").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), CATALOG_SHA256)

        document = json.loads(raw)
        items = document["items"]
        item_ids = tuple(item["id"] for item in items)
        self.assertEqual(len(item_ids), 1_140)
        self.assertEqual(len(set(item_ids)), 1_140)
        self.assertTrue(
            {
                item["coreLessonId"]
                for item in items
                if item["coreLessonId"] is not None
            }.issubset(frozenset(LESSON_IDS))
        )

    def test_roadmap_matches_fixed_prerequisites_and_six_mastery_gates(
        self,
    ) -> None:
        document = json.loads(
            (REPOSITORY_ROOT / "content/roadmap.json").read_text(
                encoding="utf-8"
            )
        )
        nodes = document["nodes"]
        self.assertEqual(tuple(node["id"] for node in nodes), LESSON_IDS)
        self.assertEqual(
            {
                node["id"]: tuple(node["prerequisiteIds"])
                for node in nodes
            },
            EXPECTED_PREREQUISITES,
        )
        self.assertEqual(
            tuple(document["masteryGates"]),
            EXPECTED_MASTERY_GATES,
        )

    def test_competency_matrix_is_one_pinned_official_triple_per_lesson(
        self,
    ) -> None:
        path = REPOSITORY_ROOT / "content/competencies.json"
        document = json.loads(path.read_bytes())
        self.assertEqual(document["frameworkVersions"], FRAMEWORK_VERSIONS)
        self.assertEqual(document["frameworkSources"], FRAMEWORK_SOURCES)

        mappings = document["mappings"]
        self.assertEqual(len(mappings), 90)
        pairs = tuple(
            (mapping["targetId"], mapping["framework"])
            for mapping in mappings
        )
        self.assertEqual(len(set(pairs)), 90)
        self.assertEqual(
            frozenset(pairs),
            frozenset(
                (lesson_id, framework)
                for lesson_id in LESSON_IDS
                for framework in FRAMEWORKS
            ),
        )

    def test_competency_parser_rejects_count_preserving_duplicate_and_drift(
        self,
    ) -> None:
        path = REPOSITORY_ROOT / "content/competencies.json"
        original = json.loads(path.read_bytes())

        duplicated = json.loads(json.dumps(original))
        duplicated["mappings"][-1] = dict(duplicated["mappings"][0])
        self.assertEqual(len(duplicated["mappings"]), 90)
        with self.assertRaises(CurriculumValidationError):
            parse_competencies_bytes(
                _json_bytes(duplicated),
                expected_target_ids=frozenset(LESSON_IDS),
                source_name="competencies.json",
            )

        drifted = json.loads(json.dumps(original))
        drifted["frameworkVersions"]["CS2023"] = "Draft"
        with self.assertRaises(CurriculumValidationError):
            parse_competencies_bytes(
                _json_bytes(drifted),
                expected_target_ids=frozenset(LESSON_IDS),
                source_name="competencies.json",
            )

    def test_capstones_have_fixed_primary_owners_and_four_evidence_kinds(
        self,
    ) -> None:
        root = REPOSITORY_ROOT / "content/capstones"
        documents = tuple(
            json.loads((root / f"{capstone_id}.json").read_bytes())
            for capstone_id in CAPSTONE_IDS
        )
        self.assertEqual(tuple(item["id"] for item in documents), CAPSTONE_IDS)

        primary_owners: dict[str, str] = {}
        for document in documents:
            with self.subTest(capstone=document["id"]):
                self.assertEqual(tuple(document["evidence"]), CAPSTONE_EVIDENCE_KINDS)
                self.assertTrue(
                    all(
                        _nonempty(document["evidence"][kind])
                        for kind in CAPSTONE_EVIDENCE_KINDS
                    )
                )
                self.assertTrue(set(document["lessonIds"]) <= set(LESSON_IDS))
                for lesson_id, exercise in document["primaryExercises"].items():
                    self.assertNotIn(lesson_id, primary_owners)
                    self.assertTrue(_nonempty(exercise))
                    primary_owners[lesson_id] = document["id"]

        self.assertEqual(primary_owners, EXPECTED_PRIMARY_OWNER)
        self.assertEqual(len(primary_owners), 30)

    def test_capstone_parser_rejects_one_owner_for_all_primary_exercises(
        self,
    ) -> None:
        root = REPOSITORY_ROOT / "content/capstones"
        mutated = {
            capstone_id: json.loads(
                (root / f"{capstone_id}.json").read_bytes()
            )
            for capstone_id in CAPSTONE_IDS
        }
        all_exercises = {
            lesson_id: document["primaryExercises"][lesson_id]
            for document in mutated.values()
            for lesson_id in document["primaryExercises"]
        }
        self.assertEqual(frozenset(all_exercises), frozenset(LESSON_IDS))
        for capstone_id, document in mutated.items():
            document["primaryExercises"] = (
                all_exercises if capstone_id == "global-service" else {}
            )
        mutated["global-service"]["lessonIds"] = list(LESSON_IDS)

        with self.assertRaises(CurriculumValidationError):
            parse_capstone_documents(
                {
                    f"{capstone_id}.json": _json_bytes(mutated[capstone_id])
                    for capstone_id in CAPSTONE_IDS
                },
                expected_lesson_ids=frozenset(LESSON_IDS),
            )

    def test_canonical_lessons_are_complete_regular_file_pairs(self) -> None:
        lessons_root = REPOSITORY_ROOT / "content/lessons"
        self.assertTrue(stat.S_ISDIR(lessons_root.lstat().st_mode))

        lesson_directories = tuple(sorted(lessons_root.iterdir()))
        self.assertEqual(
            tuple(path.name for path in lesson_directories),
            LESSON_IDS,
        )
        for ordinal, (lesson_id, directory) in enumerate(
            zip(LESSON_IDS, lesson_directories, strict=True), start=1
        ):
            with self.subTest(lesson_id=lesson_id):
                self.assertTrue(stat.S_ISDIR(directory.lstat().st_mode))
                self.assertFalse(directory.is_symlink())
                self.assertTrue(lesson_id.startswith(f"core-{ordinal:02d}-"))

                entries = tuple(sorted(directory.iterdir()))
                self.assertEqual(
                    tuple(path.name for path in entries),
                    ("body.html", "lesson.json"),
                )
                for path in entries:
                    self.assertTrue(
                        stat.S_ISREG(path.lstat().st_mode),
                        f"{path}: must be a regular file",
                    )
                    self.assertFalse(path.is_symlink())

                document = json.loads(
                    (directory / "lesson.json").read_text(encoding="utf-8")
                )
                self.assertEqual(document["id"], lesson_id)
                self.assertEqual(document["status"], "complete")

    def test_authored_bodies_have_six_sections_and_unique_visible_text(self) -> None:
        visible_bodies: dict[str, str] = {}
        for lesson_id in LESSON_IDS:
            with self.subTest(lesson_id=lesson_id):
                source = (
                    REPOSITORY_ROOT
                    / "content/lessons"
                    / lesson_id
                    / "body.html"
                ).read_text(encoding="utf-8")
                sections, visible_text = _parse_authored_body(source)
                self.assertEqual(
                    tuple(section.heading for section in sections),
                    AUTHORED_HEADINGS,
                )
                self.assertEqual(len(sections), len(AUTHORED_HEADINGS))
                self.assertTrue(all(section.body for section in sections))
                visible_bodies[lesson_id] = visible_text

        normalized = _assert_unique_visible_bodies(visible_bodies)
        self.assertEqual(len(normalized), len(LESSON_IDS))

        duplicated = dict(visible_bodies)
        duplicated[LESSON_IDS[1]] = visible_bodies[LESSON_IDS[0]]
        with self.assertRaisesRegex(AssertionError, "duplicate visible body"):
            _assert_unique_visible_bodies(duplicated)

    def test_every_lesson_closes_the_evidence_learning_loop(self) -> None:
        first_contract: _EvidenceContract | None = None
        for lesson_id in LESSON_IDS:
            with self.subTest(lesson_id=lesson_id):
                document = json.loads(
                    (
                        REPOSITORY_ROOT
                        / "content/lessons"
                        / lesson_id
                        / "lesson.json"
                    ).read_text(encoding="utf-8")
                )
                contract = _evidence_contract(document)
                _assert_evidence_references(contract)
                if first_contract is None:
                    first_contract = contract

                self.assertEqual(
                    tuple(
                        level["level"]
                        for level in document["capabilityProgression"]
                    ),
                    CAPABILITY_LEVELS,
                )

                lab = document["lab"]
                self.assertTrue(_nonempty(lab["artifact"]))
                self.assertGreaterEqual(len(lab["steps"]), 3)
                self.assertTrue(all(_nonempty(step) for step in lab["steps"]))
                self.assertTrue(_nonempty(document["teachBack"]))

                assessments = document["assessment"]
                self.assertGreaterEqual(len(assessments), 2)
                for assessment in assessments:
                    self.assertTrue(_nonempty(assessment["prompt"]))
                    self.assertTrue(_nonempty(assessment["expectedEvidence"]))
                self.assertTrue(_nonempty(document["transferTask"]))

                review = document["review"]
                self.assertEqual(review["intervalDays"], [1, 7, 30, 90])
                self.assertTrue(review["prompts"])
                self.assertTrue(
                    all(_nonempty(prompt) for prompt in review["prompts"])
                )

                rubric = document["rubric"]
                self.assertEqual(
                    tuple(item["dimension"] for item in rubric),
                    RUBRIC_DIMENSIONS,
                )
                self.assertEqual(len(rubric), 4)
                for item in rubric:
                    self.assertEqual(frozenset(item["levels"]), RUBRIC_LEVELS)
                    self.assertEqual(len(item["levels"]), 4)
                    self.assertTrue(
                        all(_nonempty(value) for value in item["levels"].values())
                    )

        self.assertIsNotNone(first_contract)
        assert first_contract is not None
        orphaned = replace(
            first_contract,
            evidence=first_contract.evidence
            + (_EvidenceItem("orphan-evidence", "artifact"),),
        )
        with self.assertRaisesRegex(
            AssertionError, "orphan or unknown objective evidence"
        ):
            _assert_evidence_references(orphaned)

    def test_content_standard_names_evidence_loop_and_four_review_roles(self) -> None:
        standard = CONTENT_STANDARD.read_text(encoding="utf-8")

        for stage in EVIDENCE_LOOP:
            self.assertIn(stage, standard)
        for role in REVIEW_ROLES:
            self.assertIn(role, standard)
        self.assertIn("4 review dimensions", standard)
        for reviewer_kind in ("human", "ai-assisted", "automated"):
            self.assertIn(f"`{reviewer_kind}`", standard)
        self.assertIn("正直に開示", standard)

    def test_curriculum_map_generated_block_matches_expected_bytes(self) -> None:
        from curriculum_builder.curriculum_map import (
            render_generated_curriculum_map,
        )

        document = CURRICULUM_MAP.read_text(encoding="utf-8")
        self.assertEqual(document.count(BEGIN_GENERATED_MAP), 1)
        self.assertEqual(document.count(END_GENERATED_MAP), 1)
        start = document.index(BEGIN_GENERATED_MAP)
        end = document.index(END_GENERATED_MAP) + len(END_GENERATED_MAP)
        self.assertEqual(
            document[start:end],
            render_generated_curriculum_map(REPOSITORY_ROOT),
        )

    def test_curriculum_map_independently_proves_release_totals_and_graph(
        self,
    ) -> None:
        document = CURRICULUM_MAP.read_text(encoding="utf-8")
        _assert_generated_map_contract(document)

        duplicated_marker = BEGIN_GENERATED_MAP + "\n" + document
        with self.assertRaisesRegex(AssertionError, "one start marker"):
            _assert_generated_map_contract(duplicated_marker)

        tampered_total = document.replace(
            "| コンピテンシー対応 | 90 mappings |",
            "| コンピテンシー対応 | 89 mappings |",
        )
        self.assertNotEqual(tampered_total, document)
        with self.assertRaisesRegex(AssertionError, "release row"):
            _assert_generated_map_contract(tampered_total)

        mutations = (
            ("V4&#46;0a", r"V4\.0a"),
            ("V4&#46;0a", "V4&period;0a"),
            ("V4&#46;0a", "V4&#x2e;0a"),
            ("| CS2023 | Final Report |", "|CS2023 | Final Report |"),
            ("| CS2023 | Final Report |", "|  CS2023 | Final Report |"),
            ("| CS2023 | Final Report |", "| CS2023| Final Report |"),
            (
                "`core-01-systems-tradeoffs`<br>システム思考",
                "`core-01-systems-tradeoffs`<br>\\システム思考",
            ),
            (
                "`core-01-systems-tradeoffs` | `foundation`",
                "`core-30-evidence-based-technical-leadership` | `foundation`",
            ),
            ("| 1 | `foundation` | 5 |", "| 1 | `foundation` | 4 |"),
            ("| CS2023 | Final Report |", "| CS2023 | Draft Report |"),
            (
                "`SF` Systems Fundamentals (direct)",
                "`AL` Systems Fundamentals (direct)",
            ),
            (
                "Primary: `global-service`<br>Supporting: "
                "`legacy-evolution`, `oss-launch`",
                "Primary: `global-service`<br>Supporting: `legacy-evolution`",
            ),
            (
                "`global-service` — 多地域の医療予約サービスを設計・運用する | 27 |",
                "`global-service` — 多地域の医療予約サービスを設計・運用する | 26 |",
            ),
            (
                "`build`, `operate`, `explain`, `review` |",
                "`build`, `operate`, `explain`, `audit` |",
            ),
        )
        for original, replacement in mutations:
            tampered = document.replace(original, replacement, 1)
            self.assertNotEqual(tampered, document)
            with self.assertRaises(AssertionError):
                _assert_generated_map_contract(tampered)

    def test_curriculum_map_requires_the_handwritten_learning_contract(self) -> None:
        document = CURRICULUM_MAP.read_text(encoding="utf-8")
        generated_only = _extract_generated_map(document)
        with self.assertRaises(AssertionError):
            _assert_generated_map_contract(generated_only)

        mutations = (
            ("# Engineering Expert Curriculum Map", "# Generated Data"),
            ("## 地図の読み方", "## 表の読み方"),
            ("## 推奨する進み方", "## 進み方"),
            ("## 更新方法", "## 再生成"),
            (
                "データ表はsource of truthから\n機械生成し、学び方と解釈上の注意は人が保守する。",
                "データ表は機械生成する。",
            ),
            (
                "資格、職位、SFIA責任level\nの認定ではない。",
                "SFIAの認定として利用できる。",
            ),
            (
                "artifact、teach-back、assessment reasoning、transferを\n"
                "揃えてからmastery gateへ進む。",
                "読了後すぐmastery gateへ進む。",
            ),
            (
                "生成表を直接編集してはならない。",
                "生成表を直接編集する。",
            ),
        )
        for original, replacement in mutations:
            with self.subTest(original=original):
                tampered = document.replace(original, replacement, 1)
                self.assertNotEqual(tampered, document)
                with self.assertRaises(AssertionError):
                    _assert_generated_map_contract(tampered)

        for injected in (
            "| unexpected | generated | row |",
            '<img src="https://example.invalid/tracker">',
        ):
            tampered = document.replace(
                END_GENERATED_MAP,
                f"{injected}\n{END_GENERATED_MAP}",
                1,
            )
            with self.assertRaises(AssertionError):
                _assert_generated_map_contract(tampered)

    def test_independent_markdown_parser_accepts_an_escaped_pipe(self) -> None:
        self.assertEqual(
            _parse_markdown_table_row(r"| 1 | boundary a\|b | final |"),
            ("1", "boundary a|b", "final"),
        )
        with self.assertRaisesRegex(AssertionError, "unsupported escape"):
            _parse_markdown_table_row(r"| \literal |")

    def test_two_fresh_builds_have_exact_deterministic_static_inventory(self) -> None:
        with TemporaryDirectory(
            prefix=".content-acceptance-",
            dir=REPOSITORY_ROOT.parent,
        ) as temporary:
            parent = Path(temporary)
            outputs = (parent / "site-a", parent / "site-b")
            for output in outputs:
                build_site(
                    REPOSITORY_ROOT / "content",
                    REPOSITORY_ROOT / "templates",
                    REPOSITORY_ROOT / "static",
                    output,
                    require_complete_curriculum=True,
                )

            first = _snapshot(outputs[0])
            second = _snapshot(outputs[1])

        self.assertEqual(first, second)
        self.assertEqual(frozenset(first), _expected_artifacts())
        self.assertEqual(len(first), 40)
        self.assertEqual(sum(path.suffix.casefold() == ".html" for path in first), 39)
        self.assertEqual(sum(path.suffix.casefold() == ".css" for path in first), 1)
        self.assertEqual(sum(path.suffix.casefold() == ".js" for path in first), 0)


if __name__ == "__main__":
    unittest.main()
