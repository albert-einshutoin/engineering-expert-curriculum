from __future__ import annotations

from dataclasses import dataclass, replace
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import stat
from tempfile import TemporaryDirectory
import unicodedata
import unittest

from curriculum_builder.build import build_site


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


class ContentAcceptanceTests(unittest.TestCase):
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
