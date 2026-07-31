from __future__ import annotations

from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from curriculum_builder.lessons import load_lesson


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BODY_HEADINGS = (
    "なぜ重要か",
    "メンタルモデル",
    "動く例で考える",
    "トレードオフと失敗モード",
    "知識チェック",
    "出典と次の学習",
)
FOUNDATION_SOURCES = {
    "core-01-systems-tradeoffs": (
        (
            "NASA Systems Engineering Handbook",
            "https://www.nasa.gov/reference/systems-engineering-handbook/",
            "primary",
        ),
        (
            "NIST SP 800-160 Vol. 1 Rev. 1: "
            "Engineering Trustworthy Secure Systems",
            "https://doi.org/10.6028/NIST.SP.800-160v1r1",
            "standard",
        ),
        (
            "The Architecture Tradeoff Analysis Method",
            "https://www.sei.cmu.edu/library/"
            "the-architecture-tradeoff-analysis-method/",
            "primary",
        ),
    ),
    "core-02-algorithms-measurement": (
        (
            "big-O notation",
            "https://www.nist.gov/dads/HTML/bigOnotation.html",
            "primary",
        ),
        (
            "SPEC CPU®2017 Run and Reporting Rules",
            "https://www.spec.org/cpu2017/Docs/runrules.html",
            "standard",
        ),
        (
            "timeit — Measure execution time of small code snippets",
            "https://docs.python.org/3/library/timeit.html",
            "primary",
        ),
        (
            "Quicksort",
            "https://www.cs.princeton.edu/courses/archive/"
            "spr18/cos226/lectures/23Quicksort.pdf",
            "primary",
        ),
    ),
    "core-03-architecture-memory-caches": (
        (
            "Intel® 64 and IA-32 Architectures Optimization",
            "https://www.intel.com/content/www/us/en/developer/articles/"
            "technical/intel64-and-ia32-architectures-optimization.html",
            "primary",
        ),
        (
            "Armv8-A memory model",
            "https://developer.arm.com/-/media/Arm%20Developer%20Community/"
            "PDF/Learn%20the%20Architecture/"
            "Armv8-A%20memory%20model%20guide.pdf"
            "?revision=58b1dd0a-3800-4218-b21a-f95a0332034c",
            "primary",
        ),
        (
            "The TLB",
            "https://docs.kernel.org/arch/x86/tlb.html",
            "primary",
        ),
    ),
    "core-04-os-processes-concurrency": (
        (
            "Chapter 17. Threads and Locks",
            "https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html",
            "standard",
        ),
        (
            "pthread_create — thread creation",
            "https://pubs.opengroup.org/onlinepubs/"
            "9799919799.2024edition/functions/pthread_create.html",
            "standard",
        ),
        (
            "fork — create a new process",
            "https://pubs.opengroup.org/onlinepubs/"
            "9799919799.2024edition/functions/fork.html",
            "standard",
        ),
        (
            "Linux kernel memory barriers",
            "https://docs.kernel.org/core-api/wrappers/memory-barriers.html",
            "primary",
        ),
        (
            "About Processes and Threads",
            "https://learn.microsoft.com/en-us/windows/win32/"
            "procthread/about-processes-and-threads",
            "primary",
        ),
    ),
    "core-05-networks-latency-failure": (
        (
            "RFC 1035: Domain Names - Implementation and Specification",
            "https://www.rfc-editor.org/rfc/rfc1035.html",
            "standard",
        ),
        (
            "RFC 9293: Transmission Control Protocol (TCP)",
            "https://www.rfc-editor.org/rfc/rfc9293.html",
            "standard",
        ),
        (
            "RFC 6298: Computing TCP's Retransmission Timer",
            "https://www.rfc-editor.org/rfc/rfc6298.html",
            "standard",
        ),
        (
            "RFC 8446: The Transport Layer Security (TLS) Protocol "
            "Version 1.3",
            "https://www.rfc-editor.org/rfc/rfc8446.html",
            "standard",
        ),
        (
            "RFC 9110: HTTP Semantics",
            "https://www.rfc-editor.org/rfc/rfc9110.html",
            "standard",
        ),
    ),
}
BUILD_SOURCES = {
    "core-06-requirements-domain-modeling": (
        (
            "ISO/IEC/IEEE 29148:2018 - Systems and software engineering — "
            "Life cycle processes — Requirements engineering",
            "https://www.iso.org/standard/72089.html",
            "standard",
        ),
        (
            "Appendix C: How to Write a Good Requirement",
            "https://www.nasa.gov/reference/"
            "appendix-c-how-to-write-a-good-requirement/",
            "primary",
        ),
        (
            "Domain-Driven Design Reference: Definitions and Pattern "
            "Summaries",
            "https://www.domainlanguage.com/wp-content/uploads/2016/05/"
            "DDD_Reference_2015-03.pdf",
            "primary",
        ),
    ),
    "core-07-api-contract-design": (
        (
            "RFC 9110: HTTP Semantics",
            "https://www.rfc-editor.org/rfc/rfc9110.html",
            "standard",
        ),
        (
            "OpenAPI Specification v3.2.0",
            "https://spec.openapis.org/oas/v3.2.0.html",
            "standard",
        ),
        (
            "JSON Schema Validation: A Vocabulary for Structural "
            "Validation of JSON",
            "https://json-schema.org/draft/2020-12/"
            "json-schema-validation",
            "standard",
        ),
        (
            "AIP-180: Backwards compatibility",
            "https://google.aip.dev/180",
            "primary",
        ),
        (
            "RFC 9457: Problem Details for HTTP APIs",
            "https://www.rfc-editor.org/rfc/rfc9457.html",
            "standard",
        ),
    ),
    "core-08-modularity-evolutionary-architecture": (
        (
            "On the Criteria To Be Used in Decomposing Systems into "
            "Modules",
            "https://doi.org/10.1145/361598.361623",
            "primary",
        ),
        (
            "ISO/IEC/IEEE 42010:2022 - Software, systems and enterprise — "
            "Architecture description",
            "https://www.iso.org/standard/74393.html",
            "standard",
        ),
        (
            "Documenting Software Architectures: Views and Beyond, "
            "Second Edition",
            "https://www.sei.cmu.edu/library/"
            "documenting-software-architectures-views-and-beyond-"
            "second-edition/",
            "primary",
        ),
        (
            "MADR 4.0.0 — The Markdown Architectural Decision Records",
            "https://adr.github.io/madr/",
            "primary",
        ),
    ),
    "core-09-test-strategy-tdd": (
        (
            "ISTQB Certified Tester Foundation Level Syllabus v4.0.1",
            "https://istqb.org/wp-content/uploads/2024/11/"
            "ISTQB_CTFL_Syllabus_v4.0.1.pdf",
            "standard",
        ),
        (
            "Test Driven Development: By Example",
            "https://www.informit.com/store/"
            "test-driven-development-by-example-9780321146533",
            "primary",
        ),
        (
            "An Empirical Analysis of Flaky Tests",
            "https://doi.org/10.1145/2635868.2635920",
            "peer-reviewed",
        ),
        (
            "Metamorphic Testing: A New Approach for Generating Next "
            "Test Cases",
            "https://www.cse.ust.hk/~scc/publ/"
            "CS98-01-metamorphictesting.pdf",
            "primary",
        ),
        (
            "Pact Specification",
            "https://docs.pact.io/getting_started/specification",
            "primary",
        ),
    ),
    "core-10-threat-modeling-secure-design": (
        (
            "Secure Software Development Framework (SSDF) Version 1.1: "
            "Recommendations for Mitigating the Risk of Software "
            "Vulnerabilities",
            "https://csrc.nist.gov/pubs/sp/800/218/final",
            "standard",
        ),
        (
            "Shifting the Balance of Cybersecurity Risk: Principles and "
            "Approaches for Secure by Design Software",
            "https://www.cisa.gov/sites/default/files/2023-10/"
            "Shifting-the-Balance-of-Cybersecurity-Risk-Principles-and-"
            "Approaches-for-Secure-by-Design-Software.pdf",
            "primary",
        ),
        (
            "Threat Modeling Cheat Sheet",
            "https://cheatsheetseries.owasp.org/cheatsheets/"
            "Threat_Modeling_Cheat_Sheet.html",
            "primary",
        ),
        (
            "OWASP Application Security Verification Standard 5.0.0",
            "https://github.com/OWASP/ASVS/releases/tag/v5.0.0_release",
            "standard",
        ),
        (
            "Insider Threat Mitigation Guide",
            "https://www.cisa.gov/sites/default/files/2022-11/"
            "Insider%20Threat%20Mitigation%20Guide_Final_508.pdf",
            "primary",
        ),
    ),
}
FOUNDATIONS = {
    "core-01-systems-tradeoffs": {
        "prerequisites": (),
        "artifact": "制約、代替案、反証条件を含む意思決定記録",
        "transfer": "医療予約システムで同じ判断を再実施",
    },
    "core-02-algorithms-measurement": {
        "prerequisites": ("core-01-systems-tradeoffs",),
        "artifact": "計算量予測と実測値の差を説明するベンチマーク報告",
        "transfer": "データ分布が変わる場合のアルゴリズム再選択",
    },
    "core-03-architecture-memory-caches": {
        "prerequisites": ("core-01-systems-tradeoffs",),
        "artifact": "アクセス局所性を変えた測定とCPU・メモリ経路図",
        "transfer": "データ指向設計を別の処理系へ適用",
    },
    "core-04-os-processes-concurrency": {
        "prerequisites": (
            "core-02-algorithms-measurement",
            "core-03-architecture-memory-caches",
        ),
        "artifact": "競合を再現し不変条件で修正した実験記録",
        "transfer": "プロセス分離とスレッド共有の再比較",
    },
    "core-05-networks-latency-failure": {
        "prerequisites": ("core-04-os-processes-concurrency",),
        "artifact": "DNSからHTTPまでの時系列トレースとタイムアウト予算",
        "transfer": "パケット損失と依存遅延を区別する診断",
    },
}
BUILD = {
    "core-06-requirements-domain-modeling": {
        "prerequisites": ("core-01-systems-tradeoffs",),
        "artifact": "用語集、境界、例外を含むドメインモデル",
        "transfer": (
            "未知のレンタル事業で用語の衝突と未宣言ルールを発見し、"
            "境界と例外を再構成する"
        ),
    },
    "core-07-api-contract-design": {
        "prerequisites": ("core-06-requirements-domain-modeling",),
        "artifact": "互換性、冪等性、失敗形式を含むAPI契約",
        "transfer": (
            "長時間オフラインになる現場端末へ互換な再送・同期API契約を"
            "設計する"
        ),
    },
    "core-08-modularity-evolutionary-architecture": {
        "prerequisites": (
            "core-06-requirements-domain-modeling",
            "core-07-api-contract-design",
        ),
        "artifact": "変更理由と依存方向を説明するモジュール図とADR",
        "transfer": (
            "変更頻度が高い料金計算モジュールの依存方向を再設計し、"
            "ADRで判断を更新する"
        ),
    },
    "core-09-test-strategy-tdd": {
        "prerequisites": (
            "core-02-algorithms-measurement",
            "core-08-modularity-evolutionary-architecture",
        ),
        "artifact": "RED-GREEN-REFACTOR履歴とリスク別テスト戦略",
        "transfer": (
            "順序と時刻に依存する非決定的障害を再現し、"
            "リスク別テスト戦略で診断する"
        ),
    },
    "core-10-threat-modeling-secure-design": {
        "prerequisites": (
            "core-07-api-contract-design",
            "core-09-test-strategy-tdd",
        ),
        "artifact": "資産、境界、攻撃経路、検証を結ぶ脅威モデル",
        "transfer": (
            "正規権限を持つ委託運用者の誤操作・資格情報悪用を含む"
            "内部者脅威へモデルを移す"
        ),
    },
}


class _BodyContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.section_depth = 0
        self.headings: list[str] = []
        self.definition_terms: list[str] = []
        self.table_captions: list[str] = []
        self.figure_count = 0
        self.figure_captions: list[str] = []
        self.table_count = 0
        self.table_headers_without_scope: list[str] = []
        self.misdiagnosis_items: list[str] = []
        self.worked_example_text: list[str] = []
        self.worked_example_code: list[str] = []
        self.dangerous_elements: list[str] = []
        self.unsafe_attributes: list[tuple[str, str]] = []
        self._heading_text: list[str] | None = None
        self._definition_text: list[str] | None = None
        self._caption_text: list[str] | None = None
        self._figure_caption_text: list[str] | None = None
        self._list_item_text: list[str] | None = None
        self._worked_code_text: list[str] | None = None
        self._in_worked_example = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.casefold()
        parent = self.stack[-1] if self.stack else None
        values = {
            name.casefold(): value or ""
            for name, value in attrs
        }
        if normalized_tag == "section":
            self.section_depth += 1
            if values.get("id") == "worked-example":
                self._in_worked_example = True
        if normalized_tag == "figure":
            self.figure_count += 1
        if normalized_tag == "table":
            self.table_count += 1
        if normalized_tag in {"script", "style"}:
            self.dangerous_elements.append(normalized_tag)
        if normalized_tag == "figcaption" and parent == "figure":
            self._figure_caption_text = []
        if normalized_tag == "th" and values.get("scope") not in {
            "col",
            "row",
            "colgroup",
            "rowgroup",
        }:
            self.table_headers_without_scope.append(values.get("scope", ""))
        if normalized_tag == "li":
            self._list_item_text = []
        if (
            normalized_tag == "code"
            and parent == "pre"
            and self._in_worked_example
        ):
            self._worked_code_text = []
        if (
            normalized_tag == "h2"
            and parent == "section"
            and self.section_depth == 1
        ):
            self._heading_text = []
        elif normalized_tag == "dt":
            self._definition_text = []
        elif normalized_tag == "caption" and parent == "table":
            self._caption_text = []

        for name, value in attrs:
            normalized_name = name.casefold()
            candidate = value or ""
            if (
                normalized_name == "style"
                or normalized_name.startswith("on")
            ):
                self.unsafe_attributes.append(
                    (normalized_name, candidate)
                )
            if normalized_name in {
                "href",
                "src",
                "action",
                "formaction",
            } and (
                "://" in candidate
                or candidate.startswith(("//", "\\"))
                or candidate.casefold().startswith(
                    ("data:", "javascript:", "vbscript:")
                )
            ):
                self.unsafe_attributes.append(
                    (normalized_name, candidate)
                )
        self.stack.append(normalized_tag)

    handle_startendtag = handle_starttag

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag == "h2" and self._heading_text is not None:
            self.headings.append(self._normalized(self._heading_text))
            self._heading_text = None
        elif normalized_tag == "dt" and self._definition_text is not None:
            self.definition_terms.append(
                self._normalized(self._definition_text)
            )
            self._definition_text = None
        elif normalized_tag == "caption" and self._caption_text is not None:
            self.table_captions.append(
                self._normalized(self._caption_text)
            )
            self._caption_text = None
        elif (
            normalized_tag == "figcaption"
            and self._figure_caption_text is not None
        ):
            self.figure_captions.append(
                self._normalized(self._figure_caption_text)
            )
            self._figure_caption_text = None
        elif normalized_tag == "li" and self._list_item_text is not None:
            item = self._normalized(self._list_item_text)
            if "誤診:" in item:
                self.misdiagnosis_items.append(item)
            self._list_item_text = None
        elif (
            normalized_tag == "code"
            and self._worked_code_text is not None
        ):
            self.worked_example_code.append(
                self._normalized(self._worked_code_text)
            )
            self._worked_code_text = None
        if normalized_tag == "section":
            self.section_depth -= 1
            if self._in_worked_example:
                self._in_worked_example = False
        if self.stack:
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        for buffer in (
            self._heading_text,
            self._definition_text,
            self._caption_text,
            self._figure_caption_text,
            self._list_item_text,
            self._worked_code_text,
        ):
            if buffer is not None:
                buffer.append(data)
        if self._in_worked_example:
            self.worked_example_text.append(data)

    @staticmethod
    def _normalized(parts: list[str]) -> str:
        return " ".join("".join(parts).split())


class _PreCodeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._in_pre = False
        self._code_text: list[str] | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag.casefold() == "pre":
            self._in_pre = True
        elif tag.casefold() == "code" and self._in_pre:
            self._code_text = []

    def handle_data(self, data: str) -> None:
        if self._code_text is not None:
            self._code_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "code" and self._code_text is not None:
            self.blocks.append("".join(self._code_text))
            self._code_text = None
        elif tag.casefold() == "pre":
            self._in_pre = False


class CoreTrackTests(unittest.TestCase):
    def body_path(self, lesson_id: str) -> Path:
        return (
            REPOSITORY_ROOT
            / "content"
            / "lessons"
            / lesson_id
            / "body.html"
        )

    def run_python_harness(
        self,
        lesson_id: str,
        marker: str,
        *,
        environment: dict[str, str] | None = None,
    ) -> dict[str, object]:
        body = self.body_path(lesson_id).read_text(encoding="utf-8")
        parser = _PreCodeParser()
        parser.feed(body)
        parser.close()
        matching = [block for block in parser.blocks if marker in block]
        self.assertEqual(len(matching), 1, f"{lesson_id}: {marker}")
        command, separator, remainder = matching[0].partition("\n")
        self.assertTrue(separator, f"{lesson_id}: harness command")
        self.assertTrue(
            command.startswith("python3.13 - "),
            f"{lesson_id}: Python 3.13 harness",
        )
        payload, terminator, _ = remainder.partition("\nPY")
        self.assertTrue(terminator, f"{lesson_id}: heredoc terminator")
        with TemporaryDirectory() as directory:
            script = Path(directory) / "harness.py"
            script.write_text(payload, encoding="utf-8")
            process_environment = os.environ.copy()
            if environment is not None:
                process_environment.update(environment)
            result = subprocess.run(
                [sys.executable, script],
                cwd=directory,
                env=process_environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        try:
            document = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            self.fail(f"{lesson_id}: invalid JSON output: {error}")
        self.assertIs(type(document), dict)
        return document

    def pre_code_blocks(self, lesson_id: str) -> list[str]:
        body = self.body_path(lesson_id).read_text(encoding="utf-8")
        parser = _PreCodeParser()
        parser.feed(body)
        parser.close()
        return parser.blocks

    def python_harness_source(
        self,
        lesson_id: str,
        marker: str,
    ) -> str:
        matching = [
            block
            for block in self.pre_code_blocks(lesson_id)
            if marker in block
        ]
        self.assertEqual(len(matching), 1, f"{lesson_id}: {marker}")
        command, separator, remainder = matching[0].partition("\n")
        self.assertTrue(separator, f"{lesson_id}: harness command")
        self.assertTrue(
            command.startswith("python3.13 - "),
            f"{lesson_id}: Python 3.13 harness",
        )
        payload, terminator, _ = remainder.partition("\nPY")
        self.assertTrue(terminator, f"{lesson_id}: heredoc terminator")
        return payload

    def execute_python_harness_source(
        self,
        payload: str,
    ) -> subprocess.CompletedProcess[str]:
        with TemporaryDirectory() as directory:
            script = Path(directory) / "harness.py"
            script.write_text(payload, encoding="utf-8")
            return subprocess.run(
                [sys.executable, script],
                cwd=directory,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )

    def assert_body_contract(self, body: str, lesson_id: str) -> None:
        parser = _BodyContractParser()
        parser.feed(body)
        parser.close()

        self.assertEqual(
            tuple(parser.headings),
            BODY_HEADINGS,
            f"{lesson_id}: ordered section headings",
        )
        self.assertGreaterEqual(
            parser.figure_count,
            1,
            f"{lesson_id}: mechanism figure",
        )
        self.assertEqual(
            len(parser.figure_captions),
            parser.figure_count,
            f"{lesson_id}: every figure has a caption",
        )
        self.assertTrue(
            all(parser.figure_captions),
            f"{lesson_id}: non-empty figure caption",
        )
        self.assertEqual(
            len(parser.table_captions),
            parser.table_count,
            f"{lesson_id}: every table has a caption",
        )
        self.assertTrue(
            all(parser.table_captions),
            f"{lesson_id}: non-empty table caption",
        )
        self.assertEqual(
            parser.table_headers_without_scope,
            [],
            f"{lesson_id}: every table header has scope",
        )
        self.assertTrue(
            any("decision table" in text for text in parser.table_captions),
            f"{lesson_id}: captioned decision table",
        )
        self.assertTrue(
            {"前提", "入力", "操作", "観測", "結論"}.issubset(
                parser.definition_terms
            ),
            f"{lesson_id}: worked example stages",
        )
        self.assertGreaterEqual(
            len(parser.misdiagnosis_items),
            2,
            f"{lesson_id}: plausible misdiagnoses",
        )
        self.assertTrue(
            all("反証:" in item for item in parser.misdiagnosis_items),
            f"{lesson_id}: misdiagnosis and rebuttal share one list item",
        )
        worked_text = " ".join(parser.worked_example_text)
        self.assertTrue(
            bool(re.search(r"\d", worked_text))
            or any(parser.worked_example_code),
            f"{lesson_id}: numeric or executable worked example",
        )
        self.assertIn("断定への注意:", body, f"{lesson_id}: caution")
        self.assertNotIn("http://", body, f"{lesson_id}: external URL")
        self.assertNotIn("https://", body, f"{lesson_id}: external URL")
        self.assertEqual(
            parser.dangerous_elements,
            [],
            f"{lesson_id}: script or style element",
        )
        self.assertEqual(
            parser.unsafe_attributes,
            [],
            f"{lesson_id}: inline behavior or remote resource",
        )

    def assert_track(
        self,
        contract: dict[str, dict[str, object]],
        *,
        expected_track: str,
        source_contract: dict[
            str,
            tuple[tuple[str, str, str], ...],
        ] | None,
    ) -> None:
        for lesson_id, expected in contract.items():
            with self.subTest(lesson_id=lesson_id):
                path = (
                    REPOSITORY_ROOT
                    / "content"
                    / "lessons"
                    / lesson_id
                    / "lesson.json"
                )
                self.assertTrue(path.is_file(), f"missing {path}")
                lesson = load_lesson(path)

                self.assertEqual(lesson.track, expected_track)
                self.assertEqual(lesson.status, "complete")
                self.assertEqual(
                    lesson.prerequisite_ids,
                    tuple(expected["prerequisites"]),
                )
                self.assertIsNotNone(lesson.lab)
                assert lesson.lab is not None
                self.assertEqual(lesson.lab.artifact, expected["artifact"])
                self.assertEqual(lesson.transfer_task, expected["transfer"])
                self.assertEqual(
                    tuple(
                        item.level
                        for item in lesson.capability_progression
                    ),
                    ("recognize", "explain", "apply", "diagnose", "lead"),
                )
                self.assertEqual(lesson.review_intervals, (1, 7, 30, 90))
                self.assertEqual(lesson.updated_at, "2026-07-30")
                if source_contract is not None:
                    self.assertEqual(
                        tuple(
                            (source.title, source.url, source.kind)
                            for source in lesson.sources
                        ),
                        source_contract[lesson_id],
                    )

    def test_foundations(self) -> None:
        self.assert_track(
            FOUNDATIONS,
            expected_track="foundations",
            source_contract=FOUNDATION_SOURCES,
        )

    def test_build(self) -> None:
        self.assert_track(
            BUILD,
            expected_track="build",
            source_contract=BUILD_SOURCES,
        )

    def test_foundation_bodies_follow_semantic_contract(self) -> None:
        for lesson_id in FOUNDATIONS:
            with self.subTest(lesson_id=lesson_id):
                body = self.body_path(lesson_id).read_text(encoding="utf-8")
                self.assert_body_contract(body, lesson_id)

    def test_build_bodies_follow_semantic_contract(self) -> None:
        for lesson_id in BUILD:
            with self.subTest(lesson_id=lesson_id):
                body = self.body_path(lesson_id).read_text(encoding="utf-8")
                self.assert_body_contract(body, lesson_id)

    def test_body_contract_rejects_heading_mutation(self) -> None:
        lesson_id = "core-01-systems-tradeoffs"
        body = self.body_path(lesson_id).read_text(encoding="utf-8")
        mutated = body.replace(
            "<h2>なぜ重要か</h2>",
            "<h2>概要</h2>",
            1,
        )

        with self.assertRaisesRegex(
            AssertionError,
            "ordered section headings",
        ):
            self.assert_body_contract(mutated, lesson_id)

    def test_body_contract_rejects_semantic_structure_mutations(self) -> None:
        lesson_id = "core-01-systems-tradeoffs"
        body = self.body_path(lesson_id).read_text(encoding="utf-8")
        worked_start = body.index('<section id="worked-example">')
        worked_end = body.index("</section>", worked_start)
        worked = body[worked_start:worked_end]
        without_marker = "".join(
            part if part.startswith("<") else re.sub(r"\d", "", part)
            for part in re.split(r"(<[^>]+>)", worked)
        )
        without_marker = re.sub(
            r"<pre><code>.*?</code></pre>",
            "<pre><code></code></pre>",
            without_marker,
            flags=re.DOTALL,
        )
        diagnosis_start = body.index("<li><strong>誤診:</strong>")
        rebuttal_start = body.index(
            "<strong>反証:</strong>",
            diagnosis_start,
        )
        without_paired_rebuttal = (
            body[:rebuttal_start]
            + "<strong>検証:</strong>"
            + body[rebuttal_start + len("<strong>反証:</strong>"):]
        )
        mutations = {
            "non-empty figure caption": body.replace(
                "判断を更新可能にする因果ループ",
                "",
                1,
            ),
            "non-empty table caption": body.replace(
                "受付方式を選ぶdecision table",
                "",
                1,
            ),
            "every table header has scope": body.replace(
                ' scope="col"',
                "",
                1,
            ),
            "misdiagnosis and rebuttal": without_paired_rebuttal,
            "numeric or executable worked example": (
                body[:worked_start]
                + without_marker
                + body[worked_end:]
            ),
        }

        for expected_message, mutated in mutations.items():
            with self.subTest(expected_message=expected_message):
                with self.assertRaisesRegex(
                    AssertionError,
                    expected_message,
                ):
                    self.assert_body_contract(mutated, lesson_id)

    def test_systems_weighted_score_is_arithmetically_correct(self) -> None:
        systems = self.body_path(
            "core-01-systems-tradeoffs"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "3×0.4 + 5×0.3 + 4×0.2 + 3×0.1 = 3.8",
            systems,
        )
        self.assertIn("同期案は3.8、キュー案は3.7", systems)
        self.assertIn("差は0.1", systems)
        self.assertNotIn("同期案は3.9", systems)
        self.assertNotIn("0.2差", systems)

    def test_algorithm_complexity_distinguishes_upper_and_tight_bounds(
        self,
    ) -> None:
        algorithms = self.body_path(
            "core-02-algorithms-measurement"
        ).read_text(encoding="utf-8")
        memory = self.body_path(
            "core-03-architecture-memory-caches"
        ).read_text(encoding="utf-8")

        self.assertIn("Big-Oは漸近上界", algorithms)
        self.assertIn("Θ(n)", algorithms)
        self.assertIn("Θ(n²)", algorithms)
        self.assertNotIn(
            "Big-Oは入力が増えたときの成長率を表す記法",
            algorithms,
        )
        self.assertNotIn("両者のBig-OはO(n)", memory)

    def test_foundation_labs_are_reproducible_from_the_lesson(self) -> None:
        systems = self.body_path(
            "core-01-systems-tradeoffs"
        ).read_text(encoding="utf-8")
        algorithms = self.body_path(
            "core-02-algorithms-measurement"
        ).read_text(encoding="utf-8")
        memory = self.body_path(
            "core-03-architecture-memory-caches"
        ).read_text(encoding="utf-8")
        concurrency = self.body_path(
            "core-04-os-processes-concurrency"
        ).read_text(encoding="utf-8")
        networks = self.body_path(
            "core-05-networks-latency-failure"
        ).read_text(encoding="utf-8")

        self.assertIn("decision-observations.csv", systems)
        self.assertIn("python3.13", systems)
        self.assertIn("repeat=7", algorithms)
        self.assertIn("json.dumps", algorithms)
        self.assertIn("全7反復値", algorithms)
        for marker in (
            "tuple(range(access_count))",
            "range(7)",
            "condition_order",
            "expected_checksums",
            "lscpu --caches",
            "sysctl",
        ):
            self.assertIn(marker, memory)
        for marker in (
            "Java 21",
            "javac RaceLab.java",
            "java RaceLab racy",
            "java RaceLab synchronized",
            "TRIALS = 200",
            "volatile int stock",
            "violations=",
            "C/C++のvolatile",
        ):
            self.assertIn(marker, concurrency)
        self.assertIn("trace-fixture.csv", networks)
        self.assertIn("curl", networks)

    def test_memory_model_diagram_is_a_machine_specific_diagnostic(
        self,
    ) -> None:
        memory = self.body_path(
            "core-03-architecture-memory-caches"
        ).read_text(encoding="utf-8")

        for marker in (
            "診断用の論理段階",
            "VIPT",
            "並行",
            "private/shared",
            "機種依存",
        ):
            self.assertIn(marker, memory)
        self.assertNotIn(
            "L1 miss時により大きい共有階層を探索する",
            memory,
        )

    def test_java_memory_model_claims_are_language_scoped(self) -> None:
        concurrency = self.body_path(
            "core-04-os-processes-concurrency"
        ).read_text(encoding="utf-8")

        self.assertIn("Java SE 21", concurrency)
        self.assertIn("happens-before", concurrency)
        self.assertIn("visibilityとordering", concurrency)
        self.assertIn("複合incrementのatomicity", concurrency)
        self.assertIn("一回の非再現", concurrency)

    def test_systems_harness_covers_every_lab_step(self) -> None:
        report = self.run_python_harness(
            "core-01-systems-tradeoffs",
            "decision_lab_v2",
        )

        self.assertEqual(
            set(report["options"]),
            {"sync", "queued", "adaptive_queue"},
        )
        self.assertEqual(report["measurement_conditions"]["sample_count"], 5)
        for option in report["options"].values():
            self.assertEqual(len(option["raw"]["response_ms"]), 5)
            self.assertIn("p95_response_ms", option["metrics"])
            self.assertIn("duplicate_rate", option["metrics"])
            self.assertIn("recovery_minutes", option["metrics"])
            self.assertIn("monthly_operations_hours", option["metrics"])
            self.assertEqual(
                set(option["scores"]),
                {
                    "latency",
                    "consistency",
                    "operations",
                    "reversibility",
                    "weighted_total",
                },
            )
            self.assertGreaterEqual(
                len(option["falsification_conditions"]),
                2,
            )
        self.assertEqual(report["decision_record"]["selected"], "sync")
        self.assertTrue(report["decision_record"]["decision_maker"])
        self.assertTrue(report["decision_record"]["review_date"])
        self.assertTrue(report["decision_record"]["unresolved_risks"])

    def test_algorithms_harness_covers_every_lab_step(self) -> None:
        report = self.run_python_harness(
            "core-02-algorithms-measurement",
            "algorithm_lab_v2",
        )

        self.assertEqual(report["seed"], 20260731)
        self.assertEqual(report["sizes"], [1000, 10000, 100000])
        self.assertEqual(
            set(report["distributions"]),
            {"unique", "duplicate_90", "front_biased"},
        )
        self.assertEqual(len(report["conditions"]), 9)
        for condition in report["conditions"]:
            self.assertEqual(condition["repeat"], 7)
            self.assertEqual(
                set(condition["samples_ns"]),
                {
                    "generation",
                    "set_build",
                    "linear_lookup",
                    "set_lookup",
                },
            )
            for samples in condition["samples_ns"].values():
                self.assertEqual(len(samples), 7)
            self.assertIn("median_ns", condition)
            self.assertIn("range_ns", condition)
            self.assertGreater(condition["query_count"], 0)
            self.assertTrue(condition["query_digest"])
            self.assertGreaterEqual(condition["crossover_queries"], 0)
            facts = condition["distribution_facts"]
            if condition["distribution"] == "unique":
                self.assertEqual(facts["unique_fraction"], 1.0)
            elif condition["distribution"] == "duplicate_90":
                self.assertEqual(facts["dominant_value_fraction"], 0.9)
            else:
                self.assertGreaterEqual(
                    facts["front_query_fraction"],
                    0.9,
                )
        self.assertTrue(report["growth_rates"])
        self.assertEqual(len(report["hypotheses"]), 2)
        self.assertTrue(report["additional_measurement"]["falsified"])

    def test_memory_harness_covers_every_lab_step(self) -> None:
        report = self.run_python_harness(
            "core-03-architecture-memory-caches",
            "memory_lab_v2",
            environment={"CURRICULUM_LAB_QUICK": "1"},
        )

        self.assertEqual(
            set(report["portable_defaults"]),
            {"l1_probe", "llc_probe", "beyond_llc_probe"},
        )
        self.assertTrue(report["topology_observation_commands"])
        self.assertTrue(report["warmup_excluded"])
        self.assertEqual(
            set(report["access_patterns"]),
            {"sequential", "stride16", "random"},
        )
        self.assertEqual(len(report["results"]), 9)
        for result in report["results"]:
            self.assertEqual(result["repeat_count"], 7)
            self.assertEqual(result["access_count"], result["size"])
            self.assertTrue(result["checksum_matches"])
            self.assertTrue(result["same_index_type"])
            self.assertEqual(len(result["samples_ns"]), 7)
        self.assertIn("cache_probe", report["additional_experiments"])
        self.assertIn("tlb_probe", report["additional_experiments"])
        self.assertTrue(report["limitations"])

    def test_concurrency_harness_is_safe_and_deterministic(self) -> None:
        body = self.body_path(
            "core-04-os-processes-concurrency"
        ).read_text(encoding="utf-8")
        safety_pattern = re.compile(
            r"<aside>.*?競合再現専用の意図的にunsafeな教材コード。"
            r"本番へ流用しない.*?</aside>\s*"
            r"<p>次を<code>RaceLab.java</code>",
            re.DOTALL,
        )

        self.assertRegex(body, safety_pattern)
        self.assertIn("CyclicBarrier", body)
        self.assertIn("join(TIMEOUT_MILLIS)", body)
        self.assertIn("isAlive()", body)
        self.assertIn("System.nanoTime()", body)
        self.assertIn("expected=%d final=%d min=%d violations=%d", body)
        self.assertIn("minimumStock", body)
        self.assertIn("elapsedNsSamples", body)
        self.assertIn("elapsed_ns_median", body)
        self.assertIn("process-message", body)
        self.assertIn("ProcessBuilder", body)
        self.assertIn("destroyForcibly()", body)
        self.assertIn("dedupe_prevented", body)
        self.assertIn("failure_radius", body)
        self.assertIn(
            "A:read(1000),B:read(1000),A:write(500),B:write(500)",
            body,
        )
        self.assertIn("java RaceLab serial", body)
        self.assertIn("java RaceLab process-message", body)
        self.assertNotIn("Thread.yield()", body)

        mutated = safety_pattern.sub(
            '<p>次を<code>RaceLab.java</code>',
            body,
            count=1,
        )
        with self.assertRaisesRegex(
            AssertionError,
            "Regex didn't match",
        ):
            self.assertRegex(mutated, safety_pattern)

    def test_concurrency_java21_harness_executes_when_configured(self) -> None:
        java_home_text = os.environ.get("CURRICULUM_JAVA21_HOME")
        if java_home_text is None:
            # Static contracts above remain mandatory on machines without a
            # JDK; CI or a local evidence run can opt into execution.
            return

        java_home = Path(java_home_text)
        javac = java_home / "bin" / "javac"
        java = java_home / "bin" / "java"
        self.assertTrue(javac.is_file(), javac)
        self.assertTrue(java.is_file(), java)
        version = subprocess.run(
            [java, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(version.returncode, 0, version.stderr)
        self.assertRegex(version.stdout, r"(?m)^openjdk 21(?:\.|\s)")

        blocks = self.pre_code_blocks(
            "core-04-os-processes-concurrency"
        )
        matching = [
            block
            for block in blocks
            if "public final class RaceLab" in block
        ]
        self.assertEqual(len(matching), 1)
        with TemporaryDirectory() as directory:
            source = Path(directory) / "RaceLab.java"
            source.write_text(matching[0], encoding="utf-8")
            compiled = subprocess.run(
                [javac, "--release", "21", source.name],
                cwd=directory,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)

            reports: dict[str, dict[str, object]] = {}
            for mode in (
                "racy",
                "synchronized",
                "serial",
                "process-message",
            ):
                executed = subprocess.run(
                    [java, "RaceLab", mode],
                    cwd=directory,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(
                    executed.returncode,
                    0,
                    f"{mode}: {executed.stderr}\n{executed.stdout}",
                )
                try:
                    report = json.loads(executed.stdout.splitlines()[-1])
                except (IndexError, json.JSONDecodeError) as error:
                    self.fail(f"{mode}: invalid final JSON line: {error}")
                self.assertEqual(report["mode"], mode)
                reports[mode] = report

        for mode in ("racy", "synchronized", "serial"):
            report = reports[mode]
            self.assertEqual(report["trials"], 200)
            self.assertGreaterEqual(report["minimum_stock"], 0)
            elapsed = report["elapsed_ns"]
            self.assertEqual(len(elapsed["samples"]), 200)
            self.assertLessEqual(elapsed["min"], elapsed["median"])
            self.assertLessEqual(elapsed["median"], elapsed["max"])
        self.assertEqual(reports["racy"]["violations"], 200)
        self.assertEqual(reports["synchronized"]["violations"], 0)
        self.assertEqual(reports["serial"]["violations"], 0)

        process_report = reports["process-message"]
        self.assertEqual(
            process_report["trial_scope"],
            "single-owner-session-not-200-thread-trials",
        )
        self.assertEqual(process_report["final_stock"], 0)
        self.assertEqual(process_report["minimum_stock"], 0)
        self.assertEqual(process_report["dedupe_prevented"], 1)
        self.assertEqual(process_report["child_exit"], 0)
        self.assertTrue(process_report["forced_cleanup"])
        self.assertTrue(process_report["parent_continued"])
        self.assertEqual(
            process_report["failure_radius"],
            "owner-child-process",
        )

    def test_network_harness_covers_every_lab_step_without_network(
        self,
    ) -> None:
        body = self.body_path(
            "core-05-networks-latency-failure"
        ).read_text(encoding="utf-8")
        self.assertIn("def main():", body)
        self.assertIn('if __name__ == "__main__":', body)
        report = self.run_python_harness(
            "core-05-networks-latency-failure",
            "network_lab_v2",
        )

        self.assertEqual(report["bind_address"], "127.0.0.1")
        self.assertFalse(report["external_network_used"])
        self.assertTrue(report["tls_simulated"])
        self.assertTrue(report["dns_cache_simulated"])
        self.assertEqual(len(report["baseline"]["cold"]), 7)
        self.assertEqual(len(report["baseline"]["warm"]), 7)
        for sample in report["baseline"]["cold"] + report["baseline"]["warm"]:
            self.assertEqual(
                set(sample["monotonic_ns"]),
                {
                    "dns_start",
                    "dns_end",
                    "connect_start",
                    "connect_end",
                    "tls_start",
                    "tls_end",
                    "first_byte",
                    "body_finish",
                },
            )
        self.assertLessEqual(report["budget"]["worst_case_ms"], 2000)
        self.assertGreater(
            report["faults"]["dependency_delay_ms"],
            report["baseline_median_ms"],
        )
        self.assertEqual(report["non_idempotent"]["automatic_retry"], "stopped")
        self.assertEqual(report["non_idempotent"]["lookup_result"], "applied")

        security = report["protocol_security"]
        self.assertEqual(security["max_line_bytes"], 256)
        self.assertLessEqual(security["socket_deadline_ms"], 1000)
        self.assertEqual(
            security["rejections"],
            {
                "unterminated": "newline_required",
                "oversized": "line_too_long",
                "timeout": "receive_timeout",
                "invalid_id": "invalid_request_id",
                "excessive_delay": "invalid_delay_ms",
                "invalid_arity": "invalid_arity",
                "invalid_mode": "invalid_mode",
            },
        )
        self.assertEqual(
            report["faults"]["connection_failure"],
            "injected_before_socket_creation",
        )
        self.assertEqual(report["faults"]["real_connector_calls"], 0)
        self.assertEqual(
            report["cleanup"]["injected_exception"],
            "observed",
        )
        self.assertTrue(report["cleanup"]["server_stopped"])
        self.assertFalse(report["cleanup"]["thread_alive"])
        self.assertTrue(report["cleanup"]["listener_closed"])

    def test_domain_model_harness_traces_rules_and_exceptions(self) -> None:
        report = self.run_python_harness(
            "core-06-requirements-domain-modeling",
            "domain_model_lab_v1",
        )

        self.assertEqual(report["fixture"], "equipment-rental-v1")
        self.assertEqual(
            {entry["term"] for entry in report["glossary"]},
            {"Asset", "Reservation", "Hold", "Checkout", "Return"},
        )
        self.assertEqual(
            {context["name"] for context in report["bounded_contexts"]},
            {"Catalog", "Rental Operations", "Billing"},
        )
        scenarios = {
            scenario["id"]: scenario
            for scenario in report["example_scenarios"]
        }
        self.assertGreaterEqual(len(scenarios), 5)
        overdue = scenarios["overdue-return"]
        self.assertEqual(overdue["command"], "ReturnAsset")
        self.assertEqual(overdue["event"], "LoanReturned")
        self.assertEqual(overdue["observed"], "accepted-overdue")
        self.assertGreater(overdue["returned_at"], overdue["due_at"])
        self.assertEqual(
            overdue["policy_event"],
            "OverdueChargeAssessmentRequested",
        )
        exceptions = {
            exception["code"]: exception
            for exception in report["exceptions"]
        }
        self.assertGreaterEqual(len(exceptions), 3)
        self.assertEqual(
            exceptions["overdue-return"]["event"],
            "LoanReturned",
        )
        self.assertTrue(exceptions["overdue-return"]["policy_event"])
        self.assertTrue(all(item["passed"] for item in report["invariants"]))
        invariant_names = {
            item["name"] for item in report["invariants"]
        }
        self.assertIn("return-restores-availability", invariant_names)
        self.assertIn(
            "overdue-return-emits-policy-event",
            invariant_names,
        )
        self.assertTrue(
            all(
                item["commands"]
                and item["events"]
                and item["invariants"]
                for item in report["traceability"]
            )
        )
        return_trace = [
            item
            for item in report["traceability"]
            if "ReturnAsset" in item["commands"]
        ]
        self.assertEqual(len(return_trace), 1)
        self.assertIn("LoanReturned", return_trace[0]["events"])
        self.assertIn(
            "overdue-return-emits-policy-event",
            return_trace[0]["invariants"],
        )
        self.assertEqual(
            {item["status"] for item in report["ambiguities"]},
            {"detected", "resolved"},
        )
        self.assertFalse(report["external_network_used"])

    def test_domain_model_rejects_overdue_return_trace_mutation(
        self,
    ) -> None:
        source = self.python_harness_source(
            "core-06-requirements-domain-modeling",
            "domain_model_lab_v1",
        )
        marker = '"id": "overdue-return",'
        self.assertIn(marker, source)
        mutated = source.replace(
            marker,
            '"id": "overdue-return-removed",',
            1,
        )

        result = self.execute_python_harness_source(mutated)

        self.assertNotEqual(result.returncode, 0)

    def test_api_contract_harness_models_replay_and_evolution(self) -> None:
        report = self.run_python_harness(
            "core-07-api-contract-design",
            "api_contract_lab_v1",
        )

        self.assertEqual(report["fixture"], "offline-field-client-v1")
        self.assertEqual(report["supported_versions"], ["v1", "v2"])
        evidence = report["idempotency_evidence"]
        self.assertEqual(evidence["initial"]["effect_count"], 1)
        self.assertEqual(evidence["replay"]["effect_count"], 1)
        self.assertEqual(
            evidence["initial"]["scope"],
            {
                "tenant": "tenant-a",
                "principal": "field-7",
                "route": "POST /work-items/{id}:complete",
                "idempotency_key": "key-42",
            },
        )
        self.assertEqual(
            evidence["initial"]["scope"],
            evidence["replay"]["scope"],
        )
        self.assertEqual(
            evidence["initial"]["request_fingerprint"],
            evidence["replay"]["request_fingerprint"],
        )
        self.assertRegex(
            evidence["initial"]["request_fingerprint"],
            r"\A[0-9a-f]{64}\Z",
        )
        self.assertRegex(
            evidence["initial"]["response_generated_at"],
            r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z",
        )
        self.assertNotEqual(
            evidence["initial"]["response_generated_at"],
            evidence["replay"]["response_generated_at"],
        )
        self.assertTrue(evidence["same_effect"])
        self.assertFalse(evidence["same_response"])
        self.assertFalse(evidence["exactly_once_claimed"])
        conflict = evidence["payload_conflict"]
        self.assertEqual(conflict["status"], 409)
        self.assertFalse(conflict["effect_applied"])
        self.assertEqual(conflict["effect_count"], 1)
        self.assertNotEqual(
            conflict["request_fingerprint"],
            evidence["initial"]["request_fingerprint"],
        )
        other_tenant = evidence["other_tenant"]
        self.assertEqual(other_tenant["scope"]["tenant"], "tenant-b")
        self.assertEqual(
            other_tenant["scope"]["idempotency_key"],
            "key-42",
        )
        self.assertNotEqual(
            other_tenant["effect"]["operation_id"],
            evidence["initial"]["effect"]["operation_id"],
        )
        self.assertEqual(other_tenant["effect_count"], 2)
        compatibility = report["compatibility_cases"]
        self.assertEqual(
            set(compatibility),
            {
                "add_optional_field",
                "remove_required_field",
                "expand_enum",
            },
        )
        trace_ids = {
            trace["id"] for trace in report["offline_client_trace"]
        }
        for change in compatibility.values():
            self.assertEqual(
                set(change),
                {"source", "wire", "semantic", "trace_id"},
            )
            self.assertIn(change["trace_id"], trace_ids)
            for axis in ("source", "wire", "semantic"):
                self.assertIs(type(change[axis]["compatible"]), bool)
                self.assertTrue(change[axis]["evidence"])
        self.assertEqual(
            set(report["problem_contract"]["rfc_standard_members"]),
            {"type", "title", "status", "detail", "instance"},
        )
        self.assertEqual(
            set(report["problem_contract"]["required_by_this_api"]),
            {"type", "title", "status"},
        )
        self.assertEqual(
            set(report["problem_contract"]["optional_by_this_api"]),
            {"detail", "instance"},
        )
        self.assertEqual(
            set(conflict["problem_details"]),
            {"type", "title", "status"},
        )
        self.assertTrue(report["authorization_boundary"]["schema_valid"])
        self.assertFalse(report["authorization_boundary"]["authorized"])
        self.assertGreaterEqual(len(report["state_transitions"]), 3)
        self.assertFalse(report["external_network_used"])

    def test_api_contract_rejects_fingerprint_check_mutation(
        self,
    ) -> None:
        source = self.python_harness_source(
            "core-07-api-contract-design",
            "api_contract_lab_v1",
        )
        marker = 'if stored["request_fingerprint"] != fingerprint:'
        self.assertIn(marker, source)
        mutated = source.replace(marker, "if False:", 1)

        result = self.execute_python_harness_source(mutated)

        self.assertNotEqual(result.returncode, 0)

    def test_api_contract_rejects_tenant_scope_mutation(self) -> None:
        source = self.python_harness_source(
            "core-07-api-contract-design",
            "api_contract_lab_v1",
        )
        marker = 'principal["tenant"],'
        self.assertIn(marker, source)
        mutated = source.replace(marker, '"shared-tenant",', 1)

        result = self.execute_python_harness_source(mutated)

        self.assertNotEqual(result.returncode, 0)

    def test_architecture_harness_exposes_dependencies_and_decision(
        self,
    ) -> None:
        report = self.run_python_harness(
            "core-08-modularity-evolutionary-architecture",
            "architecture_lab_v1",
        )

        self.assertEqual(report["fixture"], "pricing-change-hotspot-v1")
        self.assertTrue(report["before"]["cycles"])
        self.assertTrue(report["before"]["direction_violations"])
        self.assertEqual(report["after"]["cycles"], [])
        self.assertEqual(report["after"]["direction_violations"], [])
        self.assertEqual(
            report["fixture_metadata"]["kind"],
            "synthetic",
        )
        self.assertTrue(report["fixture_metadata"]["purpose"])
        self.assertEqual(
            report["fixture_metadata"]["provenance"],
            "lesson-defined synthetic scenario",
        )
        self.assertTrue(report["fixture_metadata"]["limitations"])
        architecture_body = self.body_path(
            "core-08-modularity-evolutionary-architecture"
        ).read_text(encoding="utf-8")
        self.assertIn("lesson-defined synthetic scenario", architecture_body)
        self.assertEqual(
            set(report["after"]["modules"]),
            {
                "pricing-domain",
                "pricing-application",
                "pricing-adapters",
                "reporting",
            },
        )
        criteria = report["criteria"]
        self.assertEqual(
            set(criteria),
            {
                "change_locality",
                "migration_cost",
                "operability",
                "reversibility",
            },
        )
        self.assertAlmostEqual(
            sum(criterion["weight"] for criterion in criteria.values()),
            1.0,
        )
        for criterion in criteria.values():
            self.assertEqual(
                set(criterion["scale"]),
                {"1", "2", "3", "4", "5"},
            )
            self.assertTrue(all(criterion["scale"].values()))
        self.assertEqual(len(report["options"]), 3)
        for option in report["options"]:
            self.assertEqual(set(option["ratings"]), set(criteria))
            numerator = 0.0
            denominator = 0.0
            for criterion_id, rating in option["ratings"].items():
                self.assertIn(rating["rating"], range(1, 6))
                self.assertIn(
                    str(rating["rating"]),
                    criteria[criterion_id]["scale"],
                )
                self.assertEqual(
                    rating["evidence_kind"],
                    "synthetic-fixture-observation",
                )
                self.assertTrue(rating["evidence"])
                weight = criteria[criterion_id]["weight"]
                numerator += rating["rating"] * weight
                denominator += weight
            self.assertAlmostEqual(
                option["score"],
                numerator / denominator,
            )
            self.assertTrue(option["risks"])
        winner = max(report["options"], key=lambda item: item["score"])
        self.assertEqual(report["selected_option"], winner["id"])
        adr = report["adr"]
        self.assertEqual(adr["status"], "accepted")
        for field in (
            "context",
            "decision",
            "alternatives",
            "positive_consequences",
            "negative_consequences",
            "confirmation",
        ):
            self.assertTrue(adr[field])
        impact = report["change_impact"]
        self.assertEqual(impact["target"], "pricing-domain")
        self.assertEqual(
            set(impact["actual_impacted_modules"]),
            {
                "pricing-domain",
                "pricing-application",
                "pricing-adapters",
            },
        )
        self.assertEqual(
            impact["expected_impacted_modules"],
            impact["actual_impacted_modules"],
        )
        self.assertEqual(impact["unexpected_impacted_modules"], [])
        self.assertEqual(impact["missing_expected_modules"], [])
        self.assertEqual(impact["unexpected_count"], 0)
        self.assertEqual(impact["missing_count"], 0)
        self.assertNotIn("unrelated_modules_changed", impact)
        mutations = report["impact_mutations"]
        self.assertEqual(
            set(mutations),
            {"edge_removed", "target_changed"},
        )
        expected = set(impact["expected_impacted_modules"])
        for mutation in mutations.values():
            actual = set(mutation["actual_impacted_modules"])
            unexpected = actual - expected
            missing = expected - actual
            self.assertEqual(
                set(mutation["unexpected_impacted_modules"]),
                unexpected,
            )
            self.assertEqual(
                set(mutation["missing_expected_modules"]),
                missing,
            )
            self.assertEqual(mutation["unexpected_count"], len(unexpected))
            self.assertEqual(mutation["missing_count"], len(missing))
        self.assertEqual(
            mutations["edge_removed"]["unexpected_impacted_modules"],
            [],
        )
        self.assertEqual(
            set(mutations["edge_removed"]["missing_expected_modules"]),
            {"pricing-application", "pricing-adapters"},
        )
        self.assertEqual(
            set(mutations["target_changed"]["unexpected_impacted_modules"]),
            {"reporting"},
        )
        self.assertEqual(
            set(mutations["target_changed"]["missing_expected_modules"]),
            expected,
        )
        self.assertEqual(
            adr["decision"],
            report["selected_option"],
        )
        self.assertFalse(report["external_network_used"])

    def test_testing_harness_executes_red_green_refactor_and_mutation(
        self,
    ) -> None:
        body = self.body_path(
            "core-09-test-strategy-tdd"
        ).read_text(encoding="utf-8")
        self.assertIn("subprocess.run", body)
        report = self.run_python_harness(
            "core-09-test-strategy-tdd",
            "test_strategy_lab_v1",
        )

        self.assertEqual(report["fixture"], "order-discount-v1")
        phases = report["phases"]
        self.assertEqual(
            [phase["name"] for phase in phases],
            ["RED", "GREEN", "REFACTOR"],
        )
        self.assertNotEqual(phases[0]["returncode"], 0)
        self.assertEqual(
            phases[0]["test_id"],
            "test_strategy_fixture.PureUnitTests.test_discount",
        )
        self.assertIn(
            "NotImplementedError: total is not implemented",
            phases[0]["failure_reason"],
        )
        self.assertEqual(phases[1]["returncode"], 0)
        self.assertEqual(phases[2]["returncode"], 0)
        self.assertNotEqual(
            phases[0]["source_sha256"],
            phases[1]["source_sha256"],
        )
        self.assertNotEqual(
            phases[1]["source_sha256"],
            phases[2]["source_sha256"],
        )
        self.assertEqual(
            phases[1]["behavior_sha256"],
            phases[2]["behavior_sha256"],
        )
        self.assertTrue(
            all(
                phase["command"][-4:-1]
                == ["-m", "unittest", "-q"]
                and phase["command"][-1] == phase["test_id"]
                for phase in phases
            )
        )
        strategy = {
            item["kind"]: item
            for item in report["strategy_evidence"]
        }
        self.assertEqual(
            set(strategy),
            {"unit", "integration", "contract", "property", "metamorphic"},
        )
        self.assertEqual(
            len({item["test_id"] for item in strategy.values()}),
            5,
        )
        for item in strategy.values():
            self.assertTrue(item["passed"])
            self.assertEqual(item["returncode"], 0)
            self.assertEqual(item["command"][-1], item["test_id"])
            self.assertTrue(item["boundary"])
            self.assertTrue(item["evidence"])
        self.assertEqual(strategy["unit"]["boundary"], "pure-function")
        self.assertEqual(
            strategy["integration"]["boundary"],
            "stdlib-sqlite-repository-adapter",
        )
        self.assertEqual(
            strategy["contract"]["boundary"],
            "consumer-provider-schema-and-semantics",
        )
        self.assertEqual(
            strategy["property"]["generation"],
            "bounded-exhaustive",
        )
        self.assertGreaterEqual(strategy["property"]["case_count"], 100)
        self.assertEqual(
            strategy["metamorphic"]["relation"],
            "permutation-and-zero-item-preserve-total",
        )
        defect = report["nondeterministic_defect"]
        self.assertEqual(defect["seed_sequence"], [11, 12, 13, 14])
        self.assertEqual(set(defect["outcomes"]), {"pass", "fail"})
        self.assertEqual(defect["root_cause"], "order-and-clock-coupling")
        self.assertEqual(len(defect["schedules"]), 4)
        self.assertEqual(
            set(defect["isolation"]["fixed_order_variable_clock"]),
            {"pass", "fail"},
        )
        self.assertEqual(
            set(defect["isolation"]["fixed_clock_variable_order"]),
            {"pass", "fail"},
        )
        self.assertTrue(report["mutation"]["killed"])
        self.assertNotEqual(report["mutation"]["returncode"], 0)
        self.assertEqual(
            report["mutation"]["test_id"],
            strategy["integration"]["test_id"],
        )
        self.assertIn(
            "AssertionError",
            report["mutation"]["failure_reason"],
        )
        workspace = report["workspace"]
        self.assertTrue(workspace["temporary_directory_used"])
        self.assertTrue(workspace["all_subprocesses_used_workspace_cwd"])
        self.assertEqual(
            set(workspace["explicit_test_ids"]),
            {item["test_id"] for item in strategy.values()},
        )
        self.assertFalse(report["external_network_used"])

    def test_testing_harness_isolates_symlinks_and_ambient_tests(
        self,
    ) -> None:
        source = self.python_harness_source(
            "core-09-test-strategy-tdd",
            "test_strategy_lab_v1",
        )
        with TemporaryDirectory() as directory_text:
            directory = Path(directory_text)
            victim = directory / "victim.txt"
            victim.write_text("do-not-overwrite", encoding="utf-8")
            os.symlink(victim, directory / "order_discount.py")
            ambient_marker = directory / "ambient-ran.txt"
            ambient_test = directory / "test_ambient.py"
            ambient_test.write_text(
                "from pathlib import Path\n"
                f"Path({str(ambient_marker)!r}).write_text("
                "'ran', encoding='utf-8')\n"
                "raise RuntimeError('ambient test must not run')\n",
                encoding="utf-8",
            )
            script = directory / "harness.py"
            script.write_text(source, encoding="utf-8")

            result = subprocess.run(
                [sys.executable, script],
                cwd=directory,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(
                [phase["returncode"] for phase in report["phases"]],
                [1, 0, 0],
            )
            self.assertEqual(
                victim.read_text(encoding="utf-8"),
                "do-not-overwrite",
            )
            self.assertFalse(ambient_marker.exists())

    def test_threat_model_harness_links_assets_controls_and_verification(
        self,
    ) -> None:
        report = self.run_python_harness(
            "core-10-threat-modeling-secure-design",
            "threat_model_lab_v1",
        )

        self.assertEqual(report["fixture"], "operations-portal-v1")
        self.assertEqual(
            {asset["id"] for asset in report["assets"]},
            {"customer-data", "deployment-credential", "audit-log"},
        )
        self.assertIn("operations-contractor", report["actors"])
        self.assertGreaterEqual(len(report["trust_boundaries"]), 2)
        self.assertTrue(
            all(flow["crosses"] for flow in report["cross_boundary_flows"])
        )
        self.assertEqual(
            {threat["actor_type"] for threat in report["threats"]},
            {"external", "insider"},
        )
        threat_ids = {threat["id"] for threat in report["threats"]}
        controls = {
            control["id"]: control
            for control in report["controls"]
        }
        self.assertEqual(
            {control["type"] for control in controls.values()},
            {"prevent", "detect", "recover"},
        )
        self.assertEqual(
            {link["threat_id"] for link in report["control_links"]},
            threat_ids,
        )
        for link in report["control_links"]:
            linked_types = {
                controls[control_id]["type"]
                for control_id in link["control_ids"]
            }
            self.assertEqual(
                linked_types,
                {"prevent", "detect", "recover"},
            )
        self.assertEqual(
            {link["threat_id"] for link in report["verification_links"]},
            threat_ids,
        )
        self.assertTrue(
            all(
                link["result"] == "passed"
                and link["control_id"] in controls
                for link in report["verification_links"]
            )
        )
        self.assertTrue(
            all(
                risk["threat_id"] in threat_ids
                and risk["owner"]
                and risk["review_date"]
                and risk["decision"]
                and risk["uncertainty"]
                for risk in report["residual_risks"]
            )
        )
        self.assertEqual(
            report["model_validation"],
            {
                "valid": True,
                "errors": [],
                "threat_count": len(report["threats"]),
                "control_count": len(report["controls"]),
                "verification_count": len(report["verification_links"]),
                "residual_risk_count": len(report["residual_risks"]),
            },
        )
        negative_mutations = report["negative_mutations"]
        self.assertEqual(
            set(negative_mutations),
            {
                "empty_controls",
                "unknown_reference",
                "failed_verification",
                "blank_owner",
                "missing_control_type",
            },
        )
        for mutation in negative_mutations.values():
            self.assertTrue(mutation["rejected"])
            self.assertTrue(mutation["errors"])
        self.assertFalse(report["attack_code_executed"])
        self.assertFalse(report["external_network_used"])

    def test_threat_model_rejects_disabled_validation_mutation(
        self,
    ) -> None:
        source = self.python_harness_source(
            "core-10-threat-modeling-secure-design",
            "threat_model_lab_v1",
        )
        marker = "return sorted(errors)"
        self.assertIn(marker, source)
        mutated = source.replace(marker, "return []", 1)

        result = self.execute_python_harness_source(mutated)

        self.assertNotEqual(result.returncode, 0)
