from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory
import unittest

import curriculum_builder.build as build_module
from curriculum_builder.errors import CurriculumValidationError
from curriculum_builder.graph import topological_stages
from curriculum_builder.lessons import Lesson, load_lesson


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LESSONS_ROOT = REPOSITORY_ROOT / "content" / "lessons"
ROADMAP_PATH = REPOSITORY_ROOT / "content" / "roadmap.json"
_ORDINAL = re.compile(r"^core-(0[1-9]|[12][0-9]|30)-")
EXPECTED_GATES = (
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


def _ordinal(lesson_id: str) -> int:
    match = _ORDINAL.match(lesson_id)
    if match is None:
        raise AssertionError(f"non-canonical lesson id: {lesson_id}")
    return int(match.group(1))


def _lessons() -> tuple[Lesson, ...]:
    loaded = tuple(
        load_lesson(path)
        for path in sorted(LESSONS_ROOT.glob("*/lesson.json"))
    )
    return tuple(sorted(loaded, key=lambda lesson: _ordinal(lesson.id)))


def _canonical_document() -> dict[str, object]:
    return {
        "version": 1,
        "nodes": [
            {
                "id": lesson.id,
                "title": lesson.title,
                "track": lesson.track,
                "prerequisiteIds": list(lesson.prerequisite_ids),
            }
            for lesson in _lessons()
        ],
        "masteryGates": [dict(gate) for gate in EXPECTED_GATES],
    }


def _encoded(document: object) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")


class RoadmapAcceptanceTests(unittest.TestCase):
    def test_repository_roadmap_is_an_exact_projection_of_all_lessons(self) -> None:
        raw = json.loads(ROADMAP_PATH.read_text(encoding="utf-8"))

        self.assertEqual(raw, _canonical_document())
        ids = tuple(node["id"] for node in raw["nodes"])
        self.assertEqual(len(ids), 30)
        self.assertEqual(len(set(ids)), 30)
        self.assertEqual(tuple(map(_ordinal, ids)), tuple(range(1, 31)))

    def test_all_thirty_lessons_are_reachable_and_acyclic(self) -> None:
        raw = _canonical_document()
        nodes = raw["nodes"]
        assert isinstance(nodes, list)
        ids = tuple(node["id"] for node in nodes)
        prerequisites = {
            node["id"]: tuple(node["prerequisiteIds"])
            for node in nodes
        }

        stages = topological_stages(ids, prerequisites)

        self.assertEqual(set().union(*map(set, stages)), set(ids))
        self.assertEqual(stages[0], ("core-01-systems-tradeoffs",))
        positions = {
            lesson_id: index
            for index, stage in enumerate(stages)
            for lesson_id in stage
        }
        for lesson_id, dependencies in prerequisites.items():
            self.assertTrue(
                all(
                    positions[dependency] < positions[lesson_id]
                    for dependency in dependencies
                )
            )

    def test_mastery_gates_have_exact_order_and_reviewable_outputs(self) -> None:
        raw = json.loads(ROADMAP_PATH.read_text(encoding="utf-8"))

        self.assertEqual(tuple(raw["masteryGates"]), EXPECTED_GATES)
        self.assertEqual(
            tuple(gate["after"] for gate in raw["masteryGates"]),
            (5, 10, 15, 20, 25, 30),
        )
        self.assertTrue(
            all(
                gate["artifact"] and gate["review"]
                for gate in raw["masteryGates"]
            )
        )

    def test_release_schema_rejects_unknown_missing_and_wrong_nested_values(
        self,
    ) -> None:
        parser = getattr(build_module, "parse_roadmap_bytes")
        valid = _canonical_document()
        mutations: tuple[tuple[str, object, str], ...] = (
            (
                "unknown root",
                {**valid, "unknown": True},
                "roadmap root fields",
            ),
            (
                "missing gates",
                {"version": 1, "nodes": valid["nodes"]},
                "release roadmap requires masteryGates",
            ),
            (
                "node unknown",
                {
                    **valid,
                    "nodes": [
                        {**valid["nodes"][0], "unknown": True},
                        *valid["nodes"][1:],
                    ],
                },
                "roadmap node 0 fields",
            ),
            (
                "node track type",
                {
                    **valid,
                    "nodes": [
                        {**valid["nodes"][0], "track": 1},
                        *valid["nodes"][1:],
                    ],
                },
                "roadmap node 0 track must be a string",
            ),
            (
                "nested prerequisite type",
                {
                    **valid,
                    "nodes": [
                        {
                            **valid["nodes"][1],
                            "prerequisiteIds": [1],
                        },
                        *valid["nodes"][1:],
                    ],
                },
                "prerequisites for core-02-algorithms-measurement "
                "must be strings",
            ),
            (
                "gate unknown",
                {
                    **valid,
                    "masteryGates": [
                        {**valid["masteryGates"][0], "unknown": True},
                        *valid["masteryGates"][1:],
                    ],
                },
                "mastery gate 0 fields",
            ),
            (
                "gate after bool",
                {
                    **valid,
                    "masteryGates": [
                        {**valid["masteryGates"][0], "after": True},
                        *valid["masteryGates"][1:],
                    ],
                },
                "mastery gate 0 after must be an integer",
            ),
            (
                "gate artifact type",
                {
                    **valid,
                    "masteryGates": [
                        {**valid["masteryGates"][0], "artifact": []},
                        *valid["masteryGates"][1:],
                    ],
                },
                "mastery gate 0 artifact must be a string",
            ),
        )
        for label, document, diagnostic in mutations:
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    re.escape(diagnostic),
                ):
                    parser(
                        _encoded(document),
                        "roadmap.json",
                        require_complete=True,
                    )

    def test_release_schema_rejects_duplicate_json_keys(self) -> None:
        parser = getattr(build_module, "parse_roadmap_bytes")
        with self.assertRaisesRegex(
            CurriculumValidationError,
            "duplicate JSON key",
        ):
            parser(
                b'{"version":1,"version":1,"nodes":[],"masteryGates":[]}',
                "roadmap.json",
                require_complete=True,
            )

    def test_release_schema_validates_root_before_nested_data(self) -> None:
        parser = getattr(build_module, "parse_roadmap_bytes")
        invalid = _canonical_document()
        invalid["version"] = True
        invalid["nodes"] = [None]

        with self.assertRaisesRegex(
            CurriculumValidationError,
            "^roadmap version must be integer 1$",
        ):
            parser(
                _encoded(invalid),
                "roadmap.json",
                require_complete=True,
            )

    def test_release_validation_rejects_missing_duplicate_and_drift(
        self,
    ) -> None:
        parser = getattr(build_module, "parse_roadmap_bytes")
        validator = getattr(build_module, "validate_release_curriculum")
        lessons = _lessons()
        roadmap = parser(
            _encoded(_canonical_document()),
            "roadmap.json",
            require_complete=True,
        )
        cases = (
            (
                "missing lesson",
                lessons[:-1],
                "release curriculum must contain exactly 30 lessons",
            ),
            (
                "duplicate lesson",
                (*lessons[:-1], lessons[0]),
                "release lesson IDs must be unique",
            ),
        )
        for label, mutated_lessons, diagnostic in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    re.escape(diagnostic),
                ):
                    validator(roadmap, mutated_lessons)

        changed = _canonical_document()
        changed["nodes"][0]["title"] = "drift"
        drifted = parser(
            _encoded(changed),
            "roadmap.json",
            require_complete=True,
        )
        with self.assertRaisesRegex(
            CurriculumValidationError,
            "roadmap node does not match lesson metadata",
        ):
            validator(drifted, lessons)

    def test_release_build_rejects_partial_curriculum_without_publication(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve(strict=True)
            content = root / "content"
            shutil.copytree(REPOSITORY_ROOT / "content", content)
            shutil.rmtree(
                content
                / "lessons"
                / "core-30-evidence-based-technical-leadership"
            )
            output = root / "site"
            output.mkdir()
            sentinel = output / "sentinel.txt"
            sentinel.write_text("old", encoding="utf-8")

            with self.assertRaisesRegex(
                CurriculumValidationError,
                "release curriculum must contain exactly 30 lessons",
            ):
                build_module.build_site(
                    content,
                    REPOSITORY_ROOT / "templates",
                    REPOSITORY_ROOT / "static",
                    output,
                    require_complete_curriculum=True,
                )

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "old")
            self.assertEqual(tuple(root.glob(".site.staging-*")), ())

    def test_release_build_links_every_lesson_and_renders_six_gates(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory).resolve(strict=True) / "site"

            build_module.build_site(
                REPOSITORY_ROOT / "content",
                REPOSITORY_ROOT / "templates",
                REPOSITORY_ROOT / "static",
                output,
                require_complete_curriculum=True,
            )

            html = (output / "roadmap/index.html").read_text(encoding="utf-8")
            for lesson in _lessons():
                self.assertEqual(
                    html.count(
                        f'../lessons/{lesson.id}/index.html'
                    ),
                    1,
                )
            for gate in EXPECTED_GATES:
                self.assertEqual(
                    html.count(f'id="mastery-{gate["id"]}"'),
                    1,
                )
                self.assertIn(gate["artifact"], html)
                self.assertIn(gate["review"], html)
            self.assertNotIn("<script", html.casefold())
            self.assertEqual(tuple(output.rglob("*.js")), ())


if __name__ == "__main__":
    unittest.main()
