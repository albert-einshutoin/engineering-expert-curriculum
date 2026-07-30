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

    def assert_track(self, contract: dict[str, dict[str, object]]) -> None:
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

                self.assertEqual(lesson.track, "foundations")
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
                self.assertEqual(
                    tuple(
                        (source.title, source.url, source.kind)
                        for source in lesson.sources
                    ),
                    FOUNDATION_SOURCES[lesson_id],
                )

    def test_foundations(self) -> None:
        self.assert_track(FOUNDATIONS)

    def test_foundation_bodies_follow_semantic_contract(self) -> None:
        for lesson_id in FOUNDATIONS:
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
        self.assertIn(
            "A:read(1000),B:read(1000),A:write(500),B:write(500)",
            body,
        )
        self.assertIn("java RaceLab serial", body)
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

    def test_network_harness_covers_every_lab_step_without_network(
        self,
    ) -> None:
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
        self.assertEqual(report["faults"]["connection_failure"], "observed")
        self.assertEqual(report["non_idempotent"]["automatic_retry"], "stopped")
        self.assertEqual(report["non_idempotent"]["lookup_result"], "applied")
