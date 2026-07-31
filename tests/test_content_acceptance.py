from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import re
import stat
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


def _assert_generated_map_contract(document: str) -> None:
    block = _extract_generated_map(document)
    expected_release_rows = (
        "| 保存カタログ | 1,140 items |",
        f"| カタログ SHA-256 | `{CATALOG_SHA256}` |",
        "| コアレッスン | 30 complete lessons |",
        "| コンピテンシー対応 | 90 mappings |",
        "| 統合 Capstone | 3 projects |",
        "| Primary exercise coverage | 30/30 |",
    )
    for row in expected_release_rows:
        if block.count(row) != 1:
            raise AssertionError(f"missing or duplicated release row: {row}")

    lesson_rows = tuple(
        (match, line)
        for line in block.splitlines()
        if (match := _LESSON_MAP_ROW.match(line)) is not None
    )
    if len(lesson_rows) != 30:
        raise AssertionError("generated map must contain exactly 30 lesson rows")
    if tuple(match.group("lesson") for match, _line in lesson_rows) != LESSON_IDS:
        raise AssertionError("generated map lesson IDs do not match the release")
    if tuple(int(match.group("ordinal")) for match, _line in lesson_rows) != tuple(
        range(1, 31)
    ):
        raise AssertionError("generated map lesson ordinals are not canonical")

    mapping_cells: list[str] = []
    for match, line in lesson_rows:
        cells = tuple(cell.strip() for cell in line[1:-1].split("|"))
        if len(cells) != 9:
            raise AssertionError("lesson rows must contain exactly nine cells")
        framework_cells = cells[5:8]
        if any(
            re.fullmatch(
                r"`[^`]+` .+ \((?:direct|foundational|partial)\)",
                cell,
            )
            is None
            for cell in framework_cells
        ):
            raise AssertionError("framework cells must carry code and alignment")
        mapping_cells.extend(framework_cells)
        expected_owner = EXPECTED_PRIMARY_OWNER[match.group("lesson")]
        if f"Primary: `{expected_owner}`" not in cells[8]:
            raise AssertionError("generated map has the wrong primary owner")
    if len(mapping_cells) != 90:
        raise AssertionError("generated map must expose exactly 90 mapping cells")

    capstone_rows = tuple(
        line
        for line in block.splitlines()
        if re.match(
            r"^\| `(?:global-service|legacy-evolution|oss-launch)` — ",
            line,
        )
    )
    if len(capstone_rows) != 3:
        raise AssertionError("generated map must contain three capstone rows")
    capstone_ids = tuple(
        row.split("`", maxsplit=2)[1] for row in capstone_rows
    )
    if capstone_ids != CAPSTONE_IDS:
        raise AssertionError("generated map capstone IDs do not match the release")


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
        self.assertIn("4 役すべて", standard)

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
