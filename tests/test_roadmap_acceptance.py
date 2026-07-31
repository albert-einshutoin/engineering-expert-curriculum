from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
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
                        valid["nodes"][0],
                        {
                            **valid["nodes"][1],
                            "prerequisiteIds": [1],
                        },
                        *valid["nodes"][2:],
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

    def test_parser_bounds_bytes_and_never_reflects_unsafe_source_names(
        self,
    ) -> None:
        parser = getattr(build_module, "parse_roadmap_bytes")
        with self.assertRaisesRegex(
            CurriculumValidationError,
            "^roadmap exceeds maximum byte count$",
        ):
            parser(
                b" " * (build_module.MAX_ROADMAP_BYTES + 1),
                "roadmap.json",
            )
        with self.assertRaisesRegex(
            CurriculumValidationError,
            "^roadmap snapshot must be exact bytes$",
        ):
            parser(  # type: ignore[arg-type]
                bytearray(_encoded(_canonical_document())),
                "roadmap.json",
            )

        for source_name in (
            "roadmap.json\nFORGED",
            "roadmap.json\x1b[31mFORGED",
            "x" * 256,
        ):
            with self.subTest(source_name=repr(source_name)):
                with self.assertRaises(CurriculumValidationError) as caught:
                    parser(b"{", source_name)
                self.assertEqual(
                    str(caught.exception),
                    "roadmap source name is invalid",
                )
                self.assertNotIn("FORGED", str(caught.exception))
                self.assertNotIn("\x1b", str(caught.exception))

    def test_authoring_parser_rejects_duplicate_mastery_gate_identity(
        self,
    ) -> None:
        parser = getattr(build_module, "parse_roadmap_bytes")
        valid = _canonical_document()
        mutations = (
            (
                "id",
                {
                    **valid["masteryGates"][1],
                    "id": valid["masteryGates"][0]["id"],
                },
                "duplicate mastery gate ids: foundation",
            ),
            (
                "after",
                {
                    **valid["masteryGates"][1],
                    "after": valid["masteryGates"][0]["after"],
                },
                "duplicate mastery gate after values: 5",
            ),
        )
        for label, second_gate, diagnostic in mutations:
            mutated = {
                **valid,
                "masteryGates": [
                    valid["masteryGates"][0],
                    second_gate,
                    *valid["masteryGates"][2:],
                ],
            }
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    re.escape(diagnostic),
                ):
                    parser(
                        _encoded(mutated),
                        "roadmap.json",
                        require_complete=False,
                    )

    def test_authoring_identifiers_are_safe_bounded_and_never_reflected(
        self,
    ) -> None:
        parser = getattr(build_module, "parse_roadmap_bytes")
        unsafe_values = (
            "id\nFORGED",
            "id\x1b[31mFORGED",
            "id\u202eFORGED",
            "x" * 129,
        )
        for unsafe in unsafe_values:
            documents = (
                (
                    "node",
                    {
                        "version": 1,
                        "nodes": [
                            {
                                "id": unsafe,
                                "title": "Think",
                                "prerequisites": [],
                            }
                        ],
                    },
                    "node IDs contain an unsafe identifier",
                ),
                (
                    "prerequisite",
                    {
                        "version": 1,
                        "nodes": [
                            {
                                "id": "safe",
                                "title": "Think",
                                "prerequisites": [unsafe],
                            }
                        ],
                    },
                    "prerequisites for safe contain an unsafe identifier",
                ),
                (
                    "gate",
                    {
                        **_canonical_document(),
                        "masteryGates": [
                            {
                                **EXPECTED_GATES[0],
                                "id": unsafe,
                            },
                            *[
                                dict(gate)
                                for gate in EXPECTED_GATES[1:]
                            ],
                        ],
                    },
                    "mastery gate 0 id is invalid",
                ),
            )
            for label, document, diagnostic in documents:
                with self.subTest(label=label, unsafe=repr(unsafe)):
                    with self.assertRaises(
                        CurriculumValidationError
                    ) as caught:
                        parser(
                            _encoded(document),
                            "roadmap.json",
                            require_complete=False,
                        )
                    self.assertEqual(str(caught.exception), diagnostic)
                    self.assertNotIn("FORGED", str(caught.exception))
                    self.assertNotIn("\x1b", str(caught.exception))
                    self.assertLessEqual(len(str(caught.exception)), 80)

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

    def test_release_schema_rejects_an_independent_second_root(self) -> None:
        parser = getattr(build_module, "parse_roadmap_bytes")
        invalid = _canonical_document()
        invalid["nodes"][1]["prerequisiteIds"] = []

        with self.assertRaisesRegex(
            CurriculumValidationError,
            "release roadmap must have core-01 as its only root",
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

    def test_release_validator_enforces_roadmap_invariants_independently(
        self,
    ) -> None:
        parser = getattr(build_module, "parse_roadmap_bytes")
        validator = getattr(build_module, "validate_release_curriculum")
        lessons = _lessons()
        release = parser(
            _encoded(_canonical_document()),
            "roadmap.json",
            require_complete=True,
        )
        authoring_document = _canonical_document()
        authoring_document["masteryGates"] = []
        no_gates = parser(
            _encoded(authoring_document),
            "roadmap.json",
            require_complete=False,
        )
        second_root_nodes = list(release.nodes)
        second_root_nodes[1] = replace(
            second_root_nodes[1],
            prerequisite_ids=(),
        )
        boolean_ordinal_nodes = list(release.nodes)
        boolean_ordinal_nodes[0] = replace(
            boolean_ordinal_nodes[0],
            ordinal=True,
        )
        draft_lessons = (
            replace(lessons[0], status="draft"),
            *lessons[1:],
        )
        cases = (
            (
                "version",
                replace(release, version=2),
                lessons,
                "release roadmap version must be 1",
            ),
            (
                "root",
                replace(release, nodes=tuple(second_root_nodes)),
                lessons,
                "release roadmap must have core-01 as its only root",
            ),
            (
                "gates",
                no_gates,
                lessons,
                "release roadmap must contain the exact canonical mastery gates",
            ),
            (
                "ordinal type",
                replace(release, nodes=tuple(boolean_ordinal_nodes)),
                lessons,
                "release roadmap node ordinal must be an integer",
            ),
            (
                "complete",
                release,
                draft_lessons,
                "release curriculum cannot contain draft lessons",
            ),
        )
        for label, roadmap, candidate_lessons, diagnostic in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    re.escape(diagnostic),
                ):
                    validator(roadmap, candidate_lessons)

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

    def test_cli_release_gate_rejects_partial_root_atomically(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve(strict=True)
            shutil.copytree(REPOSITORY_ROOT / "content", root / "content")
            shutil.copytree(REPOSITORY_ROOT / "templates", root / "templates")
            shutil.copytree(REPOSITORY_ROOT / "static", root / "static")
            shutil.rmtree(
                root
                / "content"
                / "lessons"
                / "core-30-evidence-based-technical-leadership"
            )
            output = root / "site"
            output.mkdir()
            sentinel = output / "sentinel.txt"
            sentinel.write_text("old", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPOSITORY_ROOT / "tools/build.py"),
                    "--root",
                    str(root),
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertIn(
                "release curriculum must contain exactly 30 lessons",
                result.stderr,
            )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "old")
            self.assertEqual(tuple(root.glob(".site.staging-*")), ())

    def test_cli_release_build_accepts_a_safe_deep_root(self) -> None:
        with TemporaryDirectory() as directory:
            temporary_root = Path(directory).resolve(strict=True)
            deep_parent = temporary_root
            while len(str(deep_parent / "project")) <= 300:
                deep_parent /= "deep-roadmap-root"
            project = deep_parent / "project"
            project.mkdir(parents=True)
            shutil.copytree(
                REPOSITORY_ROOT / "content",
                project / "content",
            )
            shutil.copytree(
                REPOSITORY_ROOT / "templates",
                project / "templates",
            )
            shutil.copytree(
                REPOSITORY_ROOT / "static",
                project / "static",
            )
            output = project / "site"

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPOSITORY_ROOT / "tools/build.py"),
                    "--root",
                    str(project),
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output / "roadmap/index.html").is_file())
            self.assertEqual(tuple(output.rglob("*.js")), ())
            self.assertEqual(tuple(project.glob(".site.staging-*")), ())

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
                self.assertIn(
                    f"<h3>{gate['id'].title()}</h3>",
                    html,
                )
                self.assertIn(gate["artifact"], html)
                self.assertIn(gate["review"], html)
            self.assertEqual(
                html.count('<li class="learning-stage">'),
                30,
            )
            self.assertEqual(
                html.count('<li class="mastery-gate"'),
                6,
            )
            self.assertNotIn('<ol class="learning-path">', html)
            self.assertEqual(
                html.count('<ol class="learning-stage-list">'),
                len(
                    topological_stages(
                        tuple(lesson.id for lesson in _lessons()),
                        {
                            lesson.id: lesson.prerequisite_ids
                            for lesson in _lessons()
                        },
                    )
                ),
            )
            self.assertEqual(
                html.count('<ol class="mastery-gate-list">'),
                1,
            )
            self.assertEqual(
                html.count('<section class="mastery-gates">'),
                1,
            )
            for ordinal in range(1, 31):
                self.assertEqual(
                    html.count(
                        f'<p class="lesson-ordinal">Lesson {ordinal:02}</p>'
                    ),
                    1,
                )

            raw = _canonical_document()
            nodes = raw["nodes"]
            assert isinstance(nodes, list)
            stages = topological_stages(
                tuple(node["id"] for node in nodes),
                {
                    node["id"]: tuple(node["prerequisiteIds"])
                    for node in nodes
                },
            )
            rendered_stages = html.split(
                '<section class="roadmap-stage">'
            )[1:]
            self.assertEqual(len(rendered_stages), len(stages))
            for expected_ids, rendered_stage in zip(
                stages,
                rendered_stages,
                strict=True,
            ):
                stage_fragment = rendered_stage.split("</section>", 1)[0]
                for lesson_id in expected_ids:
                    self.assertIn(
                        f"../lessons/{lesson_id}/index.html",
                        stage_fragment,
                    )
                for lesson_id in set(
                    node["id"] for node in nodes
                ) - set(expected_ids):
                    self.assertNotIn(
                        f"../lessons/{lesson_id}/index.html",
                        stage_fragment,
                    )
            self.assertGreater(
                html.index('<section class="mastery-gates">'),
                html.rindex('<section class="roadmap-stage">'),
            )
            self.assertNotIn("<script", html.casefold())
            self.assertEqual(tuple(output.rglob("*.js")), ())
            stylesheet = (output / "styles.css").read_text(encoding="utf-8")
            self.assertIn(".mastery-gate h3", stylesheet)
            self.assertNotIn(".mastery-gate h2", stylesheet)


if __name__ == "__main__":
    unittest.main()
