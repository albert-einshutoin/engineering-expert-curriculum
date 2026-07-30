from __future__ import annotations

from pathlib import Path
import unittest

from curriculum_builder.lessons import load_lesson


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
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


class CoreTrackTests(unittest.TestCase):
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

    def test_foundations(self) -> None:
        self.assert_track(FOUNDATIONS)
