from __future__ import annotations

from copy import deepcopy
from html.parser import HTMLParser
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from curriculum_builder.competencies import (
    MAX_COMPETENCIES_BYTES,
    MAX_RATIONALE_CHARS,
    CompetencyMatrix,
    load_competencies,
    parse_competencies_bytes,
)
from curriculum_builder.build import build_site
from curriculum_builder.errors import CurriculumValidationError


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COMPETENCIES = REPOSITORY_ROOT / "content/competencies.json"
LESSON_IDS = frozenset(
    path.parent.name
    for path in (
        REPOSITORY_ROOT / "content/lessons"
    ).glob("core-*/lesson.json")
)
EXPECTED_VERSIONS = {
    "CS2023": "Final Report",
    "SWEBOK": "V4.0a",
    "SFIA": "9",
}
FRAMEWORK_ORDER = ("CS2023", "SWEBOK", "SFIA")
EXPECTED_SOURCES = {
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
# This oracle is intentionally independent of curriculum_builder.competencies.
# A typo copied into production validation and content must still fail here.
OFFICIAL_USED_PAIRS = {
    "CS2023": frozenset(
        {
            ("AL", "Algorithmic Foundations"),
            ("AR", "Architecture and Organization"),
            ("DM", "Data Management"),
            ("GIT", "Graphics and Interactive Techniques"),
            ("HCI", "Human-Computer Interaction"),
            ("NC", "Networking and Communication"),
            ("OS", "Operating Systems"),
            ("PDC", "Parallel and Distributed Computing"),
            ("SE", "Software Engineering"),
            ("SEC", "Security"),
            ("SEP", "Society, Ethics, and the Profession"),
            ("SF", "Systems Fundamentals"),
        }
    ),
    "SWEBOK": frozenset(
        {
            ("CHAPTER 01", "Software Requirements"),
            ("CHAPTER 02", "Software Architecture"),
            ("CHAPTER 03", "Software Design"),
            ("CHAPTER 05", "Software Testing"),
            ("CHAPTER 06", "Software Engineering Operations"),
            ("CHAPTER 07", "Software Maintenance"),
            ("CHAPTER 08", "Software Configuration Management"),
            ("CHAPTER 09", "Software Engineering Management"),
            ("CHAPTER 10", "Software Engineering Process"),
            ("CHAPTER 12", "Software Quality"),
            ("CHAPTER 13", "Software Security"),
            ("CHAPTER 14", "Software Engineering Professional Practice"),
            ("CHAPTER 15", "Software Engineering Economics"),
            ("CHAPTER 16", "Computing Foundations"),
            ("CHAPTER 17", "Mathematical Foundations"),
            ("CHAPTER 18", "Engineering Foundations"),
        }
    ),
    "SFIA": frozenset(
        {
            ("ACIN", "Accessibility and inclusion"),
            ("ARCH", "Solution architecture"),
            ("ASUP", "Application support"),
            ("CHMG", "Change control"),
            ("CPMG", "Capacity management"),
            ("DBDS", "Database design"),
            ("DESN", "Systems design"),
            ("DTAN", "Data modelling and design"),
            ("GOVN", "Governance"),
            ("IFDN", "Infrastructure design"),
            ("INCA", "Content design and authoring"),
            ("INVA", "Investment appraisal"),
            ("ITSP", "Strategic planning"),
            ("NTDS", "Network design"),
            ("OFCL", "Organisational facilitation"),
            ("ORDI", "Organisation design and implementation"),
            ("PEDP", "Information and data compliance"),
            ("PROG", "Programming/software development"),
            ("QUAS", "Quality assurance"),
            ("RELM", "Release management"),
            ("REQM", "Requirements definition and management"),
            ("SCTY", "Information security"),
            ("SLMO", "Service level management"),
            ("SWDN", "Software design"),
            ("TEST", "Functional testing"),
            ("URCH", "User research"),
            ("USUP", "Incident management"),
            ("VISL", "Data visualisation"),
        }
    ),
}
EXPECTED_ALIGNMENTS = {
    "core-01-systems-tradeoffs": ("direct", "direct", "direct"),
    "core-02-algorithms-measurement": (
        "direct",
        "foundational",
        "foundational",
    ),
    "core-03-architecture-memory-caches": (
        "direct",
        "foundational",
        "foundational",
    ),
    "core-04-os-processes-concurrency": (
        "direct",
        "foundational",
        "direct",
    ),
    "core-05-networks-latency-failure": (
        "direct",
        "foundational",
        "direct",
    ),
    "core-06-requirements-domain-modeling": (
        "partial",
        "direct",
        "direct",
    ),
    "core-07-api-contract-design": ("partial", "direct", "direct"),
    "core-08-modularity-evolutionary-architecture": (
        "partial",
        "direct",
        "direct",
    ),
    "core-09-test-strategy-tdd": ("partial", "direct", "direct"),
    "core-10-threat-modeling-secure-design": (
        "direct",
        "direct",
        "direct",
    ),
    "core-11-data-modeling-storage": (
        "direct",
        "foundational",
        "direct",
    ),
    "core-12-transactions-isolation-consistency": (
        "direct",
        "foundational",
        "direct",
    ),
    "core-13-distributed-coordination-failure": (
        "direct",
        "foundational",
        "direct",
    ),
    "core-14-performance-capacity": (
        "foundational",
        "direct",
        "direct",
    ),
    "core-15-reliability-observability-slo": (
        "partial",
        "direct",
        "direct",
    ),
    "core-16-hci-usability-accessibility": (
        "direct",
        "partial",
        "direct",
    ),
    "core-17-graphics-visual-information": (
        "direct",
        "partial",
        "direct",
    ),
    "core-18-product-discovery-experiments": (
        "partial",
        "direct",
        "direct",
    ),
    "core-19-technical-communication-design-docs": (
        "direct",
        "direct",
        "direct",
    ),
    "core-20-ethics-privacy-societal-impact": (
        "direct",
        "direct",
        "partial",
    ),
    "core-21-maintenance-legacy-comprehension": (
        "partial",
        "direct",
        "direct",
    ),
    "core-22-evolution-safe-migrations": (
        "partial",
        "direct",
        "direct",
    ),
    "core-23-incident-response-learning": (
        "partial",
        "direct",
        "direct",
    ),
    "core-24-delivery-ci-release-safety": (
        "partial",
        "direct",
        "direct",
    ),
    "core-25-engineering-economics-capacity": (
        "partial",
        "direct",
        "direct",
    ),
    "core-26-code-review-collaborative-quality": (
        "partial",
        "direct",
        "direct",
    ),
    "core-27-team-interfaces-sociotechnical-architecture": (
        "partial",
        "direct",
        "direct",
    ),
    "core-28-oss-governance-stewardship": (
        "direct",
        "direct",
        "direct",
    ),
    "core-29-cross-cultural-async-collaboration": (
        "direct",
        "direct",
        "direct",
    ),
    "core-30-evidence-based-technical-leadership": (
        "partial",
        "direct",
        "direct",
    ),
}


def _document() -> dict[str, object]:
    return json.loads(COMPETENCIES.read_text(encoding="utf-8"))


def _encoded(document: object) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _parse(document: object) -> CompetencyMatrix:
    return parse_competencies_bytes(
        _encoded(document),
        expected_target_ids=LESSON_IDS,
        source_name="competencies.json",
    )


class _MatrixParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.captions = 0
        self.column_headers = 0
        self.column_header_labels: list[str] = []
        self.in_column_header = False
        self.competency_tables = 0
        self.table_captions: list[str] = []
        self.table_data_rows: list[int] = []
        self.table_header_labels: list[list[str]] = []
        self.in_competency_table = False
        self.in_table_body = False
        self.in_caption = False
        self.row_headers = 0
        self.rows = 0
        self.lesson_links: list[str] = []
        self.nowrap_cells = 0
        self.wrapping_cells = 0
        self.has_script = False
        self.text: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = dict(attrs)
        if tag == "script":
            self.has_script = True
        elif (
            tag == "table"
            and "competency-matrix"
            in (values.get("class") or "").split()
        ):
            self.competency_tables += 1
            self.table_captions.append("")
            self.table_data_rows.append(0)
            self.table_header_labels.append([])
            self.in_competency_table = True
        elif tag == "tbody" and self.in_competency_table:
            self.in_table_body = True
        elif tag == "caption":
            self.captions += 1
            self.in_caption = True
        elif tag == "th" and values.get("scope") == "col":
            self.column_headers += 1
            self.in_column_header = True
        elif tag == "th" and values.get("scope") == "row":
            self.row_headers += 1
        elif tag == "tr":
            self.rows += 1
            if self.in_table_body:
                self.table_data_rows[-1] += 1
        elif (
            tag == "a"
            and (values.get("href") or "").startswith("../lessons/core-")
        ):
            self.lesson_links.append(values["href"] or "")
        classes = frozenset((values.get("class") or "").split())
        if classes & {
            "competency-framework",
            "competency-version",
            "competency-code",
            "competency-strength",
        }:
            self.nowrap_cells += 1
        if classes & {
            "competency-name",
            "competency-rationale",
        }:
            self.wrapping_cells += 1

    def handle_data(self, data: str) -> None:
        self.text.append(data)
        if self.in_column_header:
            self.column_header_labels.append(data)
            self.table_header_labels[-1].append(data)
        if self.in_caption:
            self.table_captions[-1] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "th":
            self.in_column_header = False
        elif tag == "caption":
            self.in_caption = False
        elif tag == "tbody":
            self.in_table_body = False
        elif tag == "table":
            self.in_competency_table = False


class CompetencyContractTests(unittest.TestCase):
    def test_framework_sources_are_machine_readable_and_version_bound(
        self,
    ) -> None:
        document = _document()
        self.assertEqual(document["frameworkSources"], EXPECTED_SOURCES)

        matrix = load_competencies(
            COMPETENCIES,
            expected_target_ids=LESSON_IDS,
        )
        self.assertEqual(
            {
                framework: {
                    "version": source.version,
                    "officialUrl": source.official_url,
                    "verifiedAt": source.verified_at,
                }
                for framework, source in matrix.framework_sources.items()
            },
            EXPECTED_SOURCES,
        )

    def test_used_official_pairs_match_an_independent_oracle(self) -> None:
        document = _document()
        actual = {framework: set() for framework in FRAMEWORK_ORDER}
        for mapping in document["mappings"]:
            actual[mapping["framework"]].add(
                (mapping["competencyId"], mapping["competencyName"])
            )

        self.assertEqual(
            {
                framework: frozenset(pairs)
                for framework, pairs in actual.items()
            },
            OFFICIAL_USED_PAIRS,
        )

    def test_all_alignments_are_explicit_and_independently_anchored(
        self,
    ) -> None:
        matrix = load_competencies(
            COMPETENCIES,
            expected_target_ids=LESSON_IDS,
        )
        actual = {
            lesson_id: tuple(
                mapping.alignment
                for mapping in matrix.mappings
                if mapping.target_id == lesson_id
            )
            for lesson_id in sorted(LESSON_IDS)
        }
        self.assertEqual(actual, EXPECTED_ALIGNMENTS)
        self.assertEqual(
            {mapping.alignment for mapping in matrix.mappings},
            {"direct", "foundational", "partial"},
        )

        security_incident = next(
            mapping
            for mapping in matrix.mappings
            if mapping.target_id == "core-23-incident-response-learning"
            and mapping.framework == "CS2023"
        )
        self.assertEqual(security_incident.alignment, "partial")
        self.assertIn(
            "セキュリティインシデント",
            security_incident.rationale,
        )
        self.assertIn("限定", security_incident.rationale)

        infrastructure = next(
            mapping
            for mapping in matrix.mappings
            if mapping.target_id == "core-03-architecture-memory-caches"
            and mapping.framework == "SFIA"
        )
        self.assertEqual(infrastructure.alignment, "foundational")

    def test_unknown_or_mistyped_alignment_fails_closed(self) -> None:
        for value in ("adjacent", "", True, None):
            document = _document()
            document["mappings"][0]["alignment"] = value
            with self.subTest(value=value):
                with self.assertRaises(CurriculumValidationError):
                    _parse(document)

    def test_repository_matrix_is_exact_complete_and_immutable(self) -> None:
        matrix = load_competencies(
            COMPETENCIES,
            expected_target_ids=LESSON_IDS,
        )

        self.assertEqual(dict(matrix.framework_versions), EXPECTED_VERSIONS)
        self.assertEqual(len(LESSON_IDS), 30)
        self.assertEqual(len(matrix.mappings), 90)
        self.assertIsInstance(matrix.mappings, tuple)
        self.assertEqual(
            matrix.mappings,
            tuple(
                sorted(
                    matrix.mappings,
                    key=lambda value: (
                        value.target_id,
                        FRAMEWORK_ORDER.index(value.framework),
                    ),
                )
            ),
        )
        for lesson_id in LESSON_IDS:
            mappings = tuple(
                value
                for value in matrix.mappings
                if value.target_id == lesson_id
            )
            self.assertEqual(len(mappings), 3, lesson_id)
            self.assertEqual(
                {value.framework for value in mappings},
                set(FRAMEWORK_ORDER),
                lesson_id,
            )
            self.assertTrue(
                all(value.rationale for value in mappings),
                lesson_id,
            )

        with self.assertRaises((AttributeError, TypeError)):
            matrix.mappings += ()
        with self.assertRaises(TypeError):
            matrix.framework_versions["CS2023"] = "forged"  # type: ignore[index]

    def test_mapping_order_does_not_change_the_immutable_result(self) -> None:
        document = _document()
        reversed_document = deepcopy(document)
        reversed_document["mappings"] = list(
            reversed(document["mappings"])  # type: ignore[arg-type]
        )

        self.assertEqual(_parse(document), _parse(reversed_document))

    def test_root_and_nested_schema_are_exact(self) -> None:
        document = _document()
        mutations: tuple[tuple[str, object], ...] = (
            (
                "root missing",
                {
                    key: value
                    for key, value in document.items()
                    if key != "mappings"
                },
            ),
            ("root unknown", {**document, "unknown": True}),
            ("root wrong type", []),
            (
                "versions missing",
                {
                    **document,
                    "frameworkVersions": {
                        "CS2023": "Final Report",
                        "SWEBOK": "V4.0a",
                    },
                },
            ),
            (
                "versions unknown",
                {
                    **document,
                    "frameworkVersions": {
                        **document["frameworkVersions"],  # type: ignore[dict-item]
                        "UNKNOWN": "1",
                    },
                },
            ),
            (
                "versions wrong type",
                {**document, "frameworkVersions": []},
            ),
            (
                "sources missing",
                {
                    **document,
                    "frameworkSources": {
                        framework: source
                        for framework, source in document[
                            "frameworkSources"
                        ].items()
                        if framework != "SFIA"
                    },
                },
            ),
            (
                "sources unknown",
                {
                    **document,
                    "frameworkSources": {
                        **document["frameworkSources"],
                        "UNKNOWN": EXPECTED_SOURCES["SFIA"],
                    },
                },
            ),
            (
                "sources wrong type",
                {**document, "frameworkSources": []},
            ),
            (
                "source field missing",
                {
                    **document,
                    "frameworkSources": {
                        **document["frameworkSources"],
                        "CS2023": {
                            "version": "Final Report",
                            "officialUrl": (
                                "https://csed.acm.org/final-report/"
                            ),
                        },
                    },
                },
            ),
            (
                "source URL changed",
                {
                    **document,
                    "frameworkSources": {
                        **document["frameworkSources"],
                        "CS2023": {
                            **document["frameworkSources"]["CS2023"],
                            "officialUrl": "https://example.invalid/",
                        },
                    },
                },
            ),
            (
                "source date changed",
                {
                    **document,
                    "frameworkSources": {
                        **document["frameworkSources"],
                        "CS2023": {
                            **document["frameworkSources"]["CS2023"],
                            "verifiedAt": "2026-07-30",
                        },
                    },
                },
            ),
            (
                "mappings wrong type",
                {**document, "mappings": {}},
            ),
            (
                "mapping missing",
                {
                    **document,
                    "mappings": [
                        {
                            key: value
                            for key, value in document["mappings"][0].items()  # type: ignore[index,union-attr]
                            if key != "rationale"
                        },
                        *document["mappings"][1:],  # type: ignore[index]
                    ],
                },
            ),
            (
                "mapping unknown",
                {
                    **document,
                    "mappings": [
                        {
                            **document["mappings"][0],  # type: ignore[index,dict-item]
                            "unknown": True,
                        },
                        *document["mappings"][1:],  # type: ignore[index]
                    ],
                },
            ),
            (
                "mapping wrong type",
                {
                    **document,
                    "mappings": [
                        [],
                        *document["mappings"][1:],  # type: ignore[index]
                    ],
                },
            ),
        )
        for label, mutation in mutations:
            with self.subTest(label=label):
                with self.assertRaises(CurriculumValidationError):
                    _parse(mutation)

    def test_duplicate_json_keys_fail_at_every_depth(self) -> None:
        valid_mapping = json.dumps(
            _document()["mappings"][0],  # type: ignore[index]
            ensure_ascii=False,
        )
        duplicate_documents = (
            b'{"version":1,"version":1,"frameworkVersions":{},"mappings":[]}',
            (
                b'{"version":1,"frameworkVersions":'
                b'{"CS2023":"Final Report","CS2023":"Final Report"},'
                b'"mappings":[]}'
            ),
            (
                b'{"version":1,"frameworkVersions":'
                b'{"CS2023":"Final Report","SWEBOK":"V4.0a","SFIA":"9"},'
                b'"mappings":['
                + valid_mapping[:-1].encode("utf-8")
                + b',"targetId":"duplicate"}]}'
            ),
        )
        for raw in duplicate_documents:
            with self.subTest(raw=raw[:60]):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    "duplicate JSON key",
                ):
                    parse_competencies_bytes(
                        raw,
                        expected_target_ids=LESSON_IDS,
                        source_name="competencies.json",
                    )

    def test_exact_count_target_and_framework_coverage_fail_closed(self) -> None:
        document = _document()
        mappings = document["mappings"]  # type: ignore[assignment]
        mutations = {
            "89 mappings": {**document, "mappings": mappings[:-1]},
            "91 mappings": {
                **document,
                "mappings": [*mappings, deepcopy(mappings[-1])],
            },
            "duplicate target-framework": {
                **document,
                "mappings": [
                    *mappings[:-1],
                    deepcopy(mappings[-2]),
                ],
            },
            "unknown target": {
                **document,
                "mappings": [
                    {
                        **mappings[0],
                        "targetId": "core-31-does-not-exist",
                    },
                    *mappings[1:],
                ],
            },
            "missing target": {
                **document,
                "mappings": [
                    {
                        **mappings[0],
                        "targetId": mappings[3]["targetId"],
                    },
                    *mappings[1:],
                ],
            },
            "unknown framework": {
                **document,
                "mappings": [
                    {**mappings[0], "framework": "UNKNOWN"},
                    *mappings[1:],
                ],
            },
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label):
                with self.assertRaises(CurriculumValidationError):
                    _parse(mutation)

    def test_official_identifier_and_name_pair_must_match(self) -> None:
        document = _document()
        mappings = document["mappings"]  # type: ignore[assignment]
        mutations = {
            "unknown identifier": "NOT-OFFICIAL",
            "wrong name for identifier": mappings[1]["competencyName"],
        }
        for label, replacement in mutations.items():
            changed = deepcopy(document)
            if label == "unknown identifier":
                changed["mappings"][0]["competencyId"] = replacement
            else:
                changed["mappings"][0]["competencyName"] = replacement
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    "official competency",
                ):
                    _parse(changed)

    def test_text_contract_rejects_padding_controls_types_and_oversize(self) -> None:
        document = _document()
        cases: tuple[tuple[str, str, object], ...] = (
            ("target padding", "targetId", " core-01-systems-tradeoffs"),
            ("framework padding", "framework", "CS2023 "),
            ("id control", "competencyId", "SF\n"),
            ("name bidi", "competencyName", "Systems\u202eFundamentals"),
            ("empty rationale", "rationale", "   "),
            ("rationale control", "rationale", "unsafe\u0000text"),
            (
                "rationale oversized",
                "rationale",
                "a" * (MAX_RATIONALE_CHARS + 1),
            ),
            ("rationale wrong type", "rationale", True),
        )
        for label, field, value in cases:
            changed = deepcopy(document)
            changed["mappings"][0][field] = value
            with self.subTest(label=label):
                with self.assertRaises(CurriculumValidationError):
                    _parse(changed)

    def test_snapshot_arguments_are_exact_and_bounded(self) -> None:
        raw = COMPETENCIES.read_bytes()
        invalid_calls = (
            ("raw type", {"raw": bytearray(raw)}),
            ("target type", {"expected_target_ids": tuple(LESSON_IDS)}),
            ("source type", {"source_name": Path("competencies.json")}),
            ("source control", {"source_name": "matrix\n.json"}),
        )
        for label, changes in invalid_calls:
            arguments: dict[str, object] = {
                "raw": raw,
                "expected_target_ids": LESSON_IDS,
                "source_name": "competencies.json",
            }
            arguments.update(changes)
            with self.subTest(label=label):
                with self.assertRaises(CurriculumValidationError):
                    parse_competencies_bytes(**arguments)  # type: ignore[arg-type]

        with self.assertRaisesRegex(
            CurriculumValidationError,
            "maximum byte count",
        ):
            parse_competencies_bytes(
                b" " * (MAX_COMPETENCIES_BYTES + 1),
                expected_target_ids=LESSON_IDS,
                source_name="competencies.json",
            )
        with self.assertRaisesRegex(
            CurriculumValidationError,
            "UTF-8",
        ):
            parse_competencies_bytes(
                b'{"version":"\xff"}',
                expected_target_ids=LESSON_IDS,
                source_name="competencies.json",
            )

    def test_loader_rejects_symlinks_and_pathname_rebinding(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            linked = root / "competencies.json"
            linked.symlink_to(COMPETENCIES)
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "regular file|symbolic",
            ):
                load_competencies(
                    linked,
                    expected_target_ids=LESSON_IDS,
                )

            path = root / "matrix.json"
            path.write_bytes(COMPETENCIES.read_bytes())
            replacement = root / "replacement.json"
            replacement.write_bytes(COMPETENCIES.read_bytes())
            real_open = os.open
            replaced = False

            def replace_after_open(
                target: object,
                flags: int,
                *args: object,
                **kwargs: object,
            ) -> int:
                nonlocal replaced
                descriptor = real_open(target, flags, *args, **kwargs)
                if not replaced and Path(target).name == path.name:
                    replaced = True
                    path.unlink()
                    replacement.rename(path)
                return descriptor

            with patch(
                "curriculum_builder.lesson_io.os.open",
                side_effect=replace_after_open,
            ):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    "changed during read",
                ):
                    load_competencies(
                        path,
                        expected_target_ids=LESSON_IDS,
                    )
            self.assertTrue(replaced)

    def test_loader_rejects_nonregular_oversize_and_invalid_utf8(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            fifo = root / "matrix.fifo"
            os.mkfifo(fifo)
            oversized = root / "oversized.json"
            oversized.write_bytes(b" " * (MAX_COMPETENCIES_BYTES + 1))
            invalid = root / "invalid.json"
            invalid.write_bytes(b'{"version":"\xff"}')
            for label, path in (
                ("fifo", fifo),
                ("oversize", oversized),
                ("utf8", invalid),
            ):
                with self.subTest(label=label):
                    with self.assertRaises(CurriculumValidationError):
                        load_competencies(
                            path,
                            expected_target_ids=LESSON_IDS,
                        )


class CompetencyBuildTests(unittest.TestCase):
    def test_release_build_renders_accessible_static_escaped_matrix(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory).resolve() / "site"
            build_site(
                REPOSITORY_ROOT / "content",
                REPOSITORY_ROOT / "templates",
                REPOSITORY_ROOT / "static",
                output,
                require_complete_curriculum=True,
            )

            page = output / "competencies/index.html"
            document = page.read_text(encoding="utf-8")
            parser = _MatrixParser()
            parser.feed(document)
            parser.close()
            expected_headers = [
                "レッスン",
                "フレームワーク",
                "版",
                "対応強度",
                "公式識別子・名称",
                "対応根拠",
            ]
            self.assertEqual(parser.competency_tables, 6)
            self.assertEqual(parser.captions, 6)
            self.assertEqual(parser.table_data_rows, [15] * 6)
            self.assertEqual(parser.column_headers, 36)
            self.assertEqual(
                parser.table_header_labels,
                [
                    expected_headers,
                    expected_headers,
                    expected_headers,
                    expected_headers,
                    expected_headers,
                    expected_headers,
                ],
            )
            self.assertEqual(
                parser.table_captions,
                [
                    "foundations — 5レッスン・15対応",
                    "build — 5レッスン・15対応",
                    "data-scale — 5レッスン・15対応",
                    "human-product — 5レッスン・15対応",
                    "sustain — 5レッスン・15対応",
                    "lead — 5レッスン・15対応",
                ],
            )
            self.assertEqual(parser.row_headers, 90)
            self.assertEqual(parser.rows, 96)
            self.assertEqual(len(parser.lesson_links), 90)
            self.assertEqual(parser.nowrap_cells, 360)
            self.assertEqual(parser.wrapping_cells, 180)
            self.assertFalse(parser.has_script)
            self.assertEqual(list(output.rglob("*.js")), [])
            visible_text = " ".join(parser.text)
            for framework, version in EXPECTED_VERSIONS.items():
                self.assertIn(framework, visible_text)
                self.assertIn(version, visible_text)

    def test_rationale_markup_is_escaped_by_the_rendering_boundary(self) -> None:
        document = _document()
        document["mappings"][0]["rationale"] = (
            '<script>alert("unsafe")</script> & evidence'
        )
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            content = root / "content"
            templates = root / "templates"
            static_root = root / "static"
            content.mkdir()
            templates.mkdir()
            static_root.mkdir()
            # The focused renderer test uses a complete repository snapshot so
            # release validation remains active rather than bypassing gates.
            for source, destination in (
                (REPOSITORY_ROOT / "content", content),
                (REPOSITORY_ROOT / "templates", templates),
                (REPOSITORY_ROOT / "static", static_root),
            ):
                for current_root, directories, files in os.walk(source):
                    relative = Path(current_root).relative_to(source)
                    (destination / relative).mkdir(parents=True, exist_ok=True)
                    for name in files:
                        source_file = Path(current_root) / name
                        target_file = destination / relative / name
                        target_file.write_bytes(source_file.read_bytes())
                    directories.sort()
            (content / "competencies.json").write_bytes(_encoded(document))
            output = root / "site"

            build_site(
                content,
                templates,
                static_root,
                output,
                require_complete_curriculum=True,
            )
            rendered = (output / "competencies/index.html").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("<script>", rendered)
            self.assertIn("&lt;script&gt;", rendered)
            self.assertIn("&amp; evidence", rendered)

    def test_release_rejects_missing_matrix_without_replacing_output(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            content = root / "content"
            templates = root / "templates"
            static_root = root / "static"
            for source, destination in (
                (REPOSITORY_ROOT / "content", content),
                (REPOSITORY_ROOT / "templates", templates),
                (REPOSITORY_ROOT / "static", static_root),
            ):
                for current_root, directories, files in os.walk(source):
                    relative = Path(current_root).relative_to(source)
                    (destination / relative).mkdir(parents=True, exist_ok=True)
                    for name in files:
                        source_file = Path(current_root) / name
                        if (
                            source == REPOSITORY_ROOT / "content"
                            and name == "competencies.json"
                        ):
                            continue
                        (destination / relative / name).write_bytes(
                            source_file.read_bytes()
                        )
                    directories.sort()
            output = root / "site"
            output.mkdir()
            sentinel = output / "sentinel.txt"
            sentinel.write_text("old", encoding="utf-8")

            with self.assertRaises(CurriculumValidationError):
                build_site(
                    content,
                    templates,
                    static_root,
                    output,
                    require_complete_curriculum=True,
                )

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "old")
            self.assertEqual(list(root.glob(".site.staging-*")), [])

    def test_matrix_styles_are_print_readable_without_dynamic_behavior(
        self,
    ) -> None:
        stylesheet = (REPOSITORY_ROOT / "static/styles.css").read_text(
            encoding="utf-8"
        )
        template = (
            REPOSITORY_ROOT / "templates/competency-matrix.html"
        ).read_text(encoding="utf-8")
        self.assertIn(".competency-matrix", stylesheet)
        self.assertIn(".competency-frameworks", stylesheet)
        self.assertIn("@media print", stylesheet)
        self.assertRegex(
            stylesheet,
            (
                r"(?s)@page competency-matrix\s*\{.*"
                r"size:\s*Letter landscape"
            ),
        )
        self.assertRegex(
            stylesheet,
            (
                r"(?s)@media print.*"
                r"\.competency-matrix-page\s*\{.*"
                r"page:\s*competency-matrix"
            ),
        )
        self.assertRegex(
            stylesheet,
            (
                r"(?s)@media print.*"
                r"\.competency-matrix thead.*"
                r"\.competency-matrix thead tr.*"
                r"\.competency-matrix thead th.*"
                r"break-inside:\s*avoid.*"
                r"white-space:\s*nowrap"
            ),
        )
        self.assertRegex(
            stylesheet,
            (
                r"(?s)@media print.*"
                r"\.competency-matrix \+ \.competency-matrix.*"
                r"break-before:\s*page"
            ),
        )
        self.assertRegex(
            stylesheet,
            (
                r"(?s)@media print.*"
                r"\.competency-matrix th:first-child.*"
                r"\.competency-matrix td:last-child.*"
                r"inline-size:\s*auto.*"
                r"min-inline-size:\s*0"
            ),
        )
        self.assertRegex(
            stylesheet,
            (
                r"(?s)@media print.*"
                r"\.competency-framework.*"
                r"\.competency-version.*"
                r"\.competency-code.*"
                r"\.competency-strength.*"
                r"white-space:\s*nowrap"
            ),
        )
        self.assertRegex(
            stylesheet,
            (
                r"(?s)@media print.*"
                r"\.competency-name.*"
                r"\.competency-rationale.*"
                r"overflow-wrap:\s*anywhere"
            ),
        )
        self.assertNotRegex(
            template + stylesheet,
            r"(?i)<script|javascript:|@keyframes|animation\s*:|transition\s*:",
        )


if __name__ == "__main__":
    unittest.main()
