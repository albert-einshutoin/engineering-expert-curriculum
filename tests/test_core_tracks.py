from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
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
        self.figure_caption_count = 0
        self.dangerous_elements: list[str] = []
        self.unsafe_attributes: list[tuple[str, str]] = []
        self._capture_tag: str | None = None
        self._capture_text: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.casefold()
        parent = self.stack[-1] if self.stack else None
        if normalized_tag == "section":
            self.section_depth += 1
        if normalized_tag == "figure":
            self.figure_count += 1
        if normalized_tag in {"script", "style"}:
            self.dangerous_elements.append(normalized_tag)
        if normalized_tag == "figcaption" and parent == "figure":
            self.figure_caption_count += 1
        if (
            normalized_tag == "h2"
            and parent == "section"
            and self.section_depth == 1
        ):
            self._start_capture("h2")
        elif normalized_tag == "dt":
            self._start_capture("dt")
        elif normalized_tag == "caption" and parent == "table":
            self._start_capture("caption")

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
        if self._capture_tag == normalized_tag:
            captured = " ".join("".join(self._capture_text).split())
            if normalized_tag == "h2":
                self.headings.append(captured)
            elif normalized_tag == "dt":
                self.definition_terms.append(captured)
            else:
                self.table_captions.append(captured)
            self._capture_tag = None
            self._capture_text = []
        if normalized_tag == "section":
            self.section_depth -= 1
        if self.stack:
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        if self._capture_tag is not None:
            self._capture_text.append(data)

    def _start_capture(self, tag: str) -> None:
        if self._capture_tag is not None:
            raise AssertionError("nested body contract capture")
        self._capture_tag = tag
        self._capture_text = []


class CoreTrackTests(unittest.TestCase):
    def body_path(self, lesson_id: str) -> Path:
        return (
            REPOSITORY_ROOT
            / "content"
            / "lessons"
            / lesson_id
            / "body.html"
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
        self.assertGreaterEqual(
            parser.figure_caption_count,
            1,
            f"{lesson_id}: figure caption",
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
            body.count("誤診:"),
            2,
            f"{lesson_id}: plausible misdiagnoses",
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
