from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from curriculum_builder.build import build_site
from curriculum_builder.capstones import (
    CAPSTONE_IDS,
    EVIDENCE_KINDS,
    RUBRIC_LEVELS,
    Capstone,
    load_capstones,
    parse_capstone_documents,
)
from curriculum_builder.errors import CurriculumValidationError


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CAPSTONES = REPOSITORY_ROOT / "content/capstones"
LESSON_IDS = tuple(
    path.parent.name
    for path in sorted(
        (REPOSITORY_ROOT / "content/lessons").glob("core-*/lesson.json")
    )
)


def _documents() -> dict[str, bytes]:
    return {
        f"{capstone_id}.json": (
            CAPSTONES / f"{capstone_id}.json"
        ).read_bytes()
        for capstone_id in CAPSTONE_IDS
    }


def _decoded() -> dict[str, dict[str, object]]:
    return {
        name: json.loads(raw)
        for name, raw in _documents().items()
    }


def _encoded(documents: dict[str, dict[str, object]]) -> dict[str, bytes]:
    return {
        name: json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        for name, document in documents.items()
    }


def _parse(
    documents: dict[str, dict[str, object]],
) -> tuple[Capstone, ...]:
    return parse_capstone_documents(
        _encoded(documents),
        expected_lesson_ids=frozenset(LESSON_IDS),
    )


class CapstoneContractTests(unittest.TestCase):
    def test_release_has_three_exact_immutable_capstones(self) -> None:
        capstones = load_capstones(CAPSTONES)

        self.assertEqual(
            tuple(value.id for value in capstones),
            CAPSTONE_IDS,
        )
        self.assertEqual(
            set().union(*(set(value.lesson_ids) for value in capstones)),
            set(LESSON_IDS),
        )
        for capstone in capstones:
            self.assertEqual(capstone.evidence_kinds, EVIDENCE_KINDS)
            self.assertEqual(
                tuple(capstone.rubric),
                RUBRIC_LEVELS,
            )
            self.assertIsInstance(capstone.constraints, tuple)
            self.assertIsInstance(capstone.lesson_ids, tuple)
            self.assertIsInstance(capstone.milestones, tuple)
            self.assertIsInstance(capstone.review_questions, tuple)
            with self.assertRaises(TypeError):
                capstone.evidence["extra"] = "no"  # type: ignore[index]

    def test_each_primary_exercise_is_semantic_not_an_id_only_claim(self) -> None:
        capstones = load_capstones(CAPSTONES)
        primary_exercises = {
            lesson_id: exercise
            for capstone in capstones
            for lesson_id, exercise in capstone.primary_exercises.items()
        }

        self.assertEqual(set(primary_exercises), set(LESSON_IDS))
        for lesson_id, exercise in primary_exercises.items():
            with self.subTest(lesson_id=lesson_id):
                self.assertNotIn(lesson_id, exercise)
                self.assertGreaterEqual(len(exercise), 24)
                self.assertTrue(
                    any(
                        verb in exercise
                        for verb in (
                            "検証",
                            "再現",
                            "測定",
                            "追跡",
                            "再評価",
                            "更新",
                            "監査",
                            "実行",
                            "導く",
                            "比較",
                        )
                    )
                )

    def test_all_briefs_require_the_complete_independent_review_cycle(self) -> None:
        for capstone in load_capstones(CAPSTONES):
            review = capstone.evidence["review"]
            for required in (
                "第三者",
                "finding",
                "author fix",
                "独立再評価",
                "単一制約",
            ):
                with self.subTest(capstone=capstone.id, required=required):
                    self.assertIn(required, review)

    def test_root_and_nested_schemas_are_exact(self) -> None:
        cases: list[tuple[str, dict[str, dict[str, object]], str]] = []
        for location in ("root", "evidence", "rubric", "primaryExercises"):
            documents = _decoded()
            target = documents["global-service.json"]
            if location == "root":
                target["surprise"] = "x"
            else:
                nested = target[location]
                assert isinstance(nested, dict)
                nested["surprise"] = "x"
            cases.append((location, documents, "fields must be exactly"))

        documents = _decoded()
        del documents["global-service.json"]["scenario"]
        cases.append(("missing root", documents, "fields must be exactly"))

        documents = _decoded()
        evidence = documents["global-service.json"]["evidence"]
        assert isinstance(evidence, dict)
        del evidence["operate"]
        cases.append(("missing evidence", documents, "fields must be exactly"))

        for label, documents, expected in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    expected,
                ):
                    _parse(documents)

    def test_wrong_native_types_and_unsafe_text_fail_closed(self) -> None:
        mutations = (
            ("version", True),
            ("title", 1),
            ("constraints", "not-a-list"),
            ("lessonIds", {"x": "y"}),
            ("milestones", [1]),
            ("reviewQuestions", ["safe", "\nforged"]),
        )
        for field, replacement in mutations:
            documents = _decoded()
            documents["global-service.json"][field] = replacement
            with self.subTest(field=field):
                with self.assertRaises(CurriculumValidationError):
                    _parse(documents)

    def test_duplicate_json_keys_at_root_and_nested_fail_closed(self) -> None:
        documents = _documents()
        valid = documents["global-service.json"].decode("utf-8")
        cases = (
            valid.replace(
                '"version": 1,',
                '"version": 1, "version": 1,',
                1,
            ),
            valid.replace(
                '"build": ',
                '"build": "duplicate", "build": ',
                1,
            ),
            valid.replace(
                '"incomplete": ',
                '"incomplete": "duplicate", "incomplete": ',
                1,
            ),
        )
        for raw in cases:
            mutated = dict(documents)
            mutated["global-service.json"] = raw.encode("utf-8")
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "duplicate JSON key",
            ):
                parse_capstone_documents(
                    mutated,
                    expected_lesson_ids=frozenset(LESSON_IDS),
                )

    def test_exact_ids_filename_binding_order_and_cross_document_duplicates(
        self,
    ) -> None:
        documents = _decoded()
        documents["global-service.json"]["id"] = "oss-launch"
        with self.assertRaisesRegex(
            CurriculumValidationError,
            "filename stem must equal capstone id",
        ):
            _parse(documents)

        missing = _documents()
        del missing["global-service.json"]
        with self.assertRaisesRegex(
            CurriculumValidationError,
            "capstone files must be exactly",
        ):
            parse_capstone_documents(
                missing,
                expected_lesson_ids=frozenset(LESSON_IDS),
            )

    def test_unknown_duplicate_and_missing_lesson_coverage_fail_closed(
        self,
    ) -> None:
        unknown = _decoded()
        lesson_ids = unknown["global-service.json"]["lessonIds"]
        assert isinstance(lesson_ids, list)
        lesson_ids.append("core-01-invented")
        with self.assertRaisesRegex(
            CurriculumValidationError,
            "unknown lesson",
        ):
            _parse(unknown)

        duplicate = _decoded()
        lesson_ids = duplicate["global-service.json"]["lessonIds"]
        assert isinstance(lesson_ids, list)
        lesson_ids.append(lesson_ids[0])
        with self.assertRaisesRegex(
            CurriculumValidationError,
            "duplicate lesson",
        ):
            _parse(duplicate)

        missing = _decoded()
        for document in missing.values():
            lesson_ids = document["lessonIds"]
            assert isinstance(lesson_ids, list)
            if LESSON_IDS[0] in lesson_ids:
                lesson_ids.remove(LESSON_IDS[0])
        with self.assertRaisesRegex(
            CurriculumValidationError,
            "missing capstone lesson coverage|primary exercise",
        ):
            _parse(missing)

    def test_primary_exercises_reject_id_water_filling_and_wrong_owner(
        self,
    ) -> None:
        documents = _decoded()
        primary = documents["global-service.json"]["primaryExercises"]
        assert isinstance(primary, dict)
        first = next(iter(primary))
        primary[first] = first
        with self.assertRaisesRegex(
            CurriculumValidationError,
            "primary exercise",
        ):
            _parse(documents)

        documents = _decoded()
        source = documents["global-service.json"]["primaryExercises"]
        target = documents["oss-launch.json"]["primaryExercises"]
        assert isinstance(source, dict)
        assert isinstance(target, dict)
        moved_id = next(iter(source))
        target[moved_id] = source.pop(moved_id)
        with self.assertRaisesRegex(
            CurriculumValidationError,
            "primaryExercises|primary exercise owner",
        ):
            _parse(documents)

    def test_invalid_utf8_size_symlink_and_draft_reference_are_rejected(
        self,
    ) -> None:
        documents = _documents()
        documents["global-service.json"] = b"\xff"
        with self.assertRaisesRegex(
            CurriculumValidationError,
            "valid UTF-8",
        ):
            parse_capstone_documents(
                documents,
                expected_lesson_ids=frozenset(LESSON_IDS),
            )

        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            shutil.copytree(REPOSITORY_ROOT / "content/lessons", root / "lessons")
            shutil.copytree(CAPSTONES, root / "real-capstones")
            os.symlink(root / "real-capstones", root / "capstones")
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "symbolic link",
            ):
                load_capstones(root / "capstones")

            metadata = root / "lessons" / LESSON_IDS[0] / "lesson.json"
            document = json.loads(metadata.read_text(encoding="utf-8"))
            document["status"] = "draft"
            for field in (
                "capabilityProgression",
                "lab",
                "teachBack",
                "assessment",
                "transferTask",
                "rubric",
                "sources",
                "review",
            ):
                document.pop(field)
            metadata.write_text(
                json.dumps(document, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "draft lessons cannot be referenced",
            ):
                load_capstones(root / "real-capstones")


class CapstoneRenderingTests(unittest.TestCase):
    def test_release_build_generates_index_and_three_semantic_briefs(self) -> None:
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "site"
            build_site(
                REPOSITORY_ROOT / "content",
                REPOSITORY_ROOT / "templates",
                REPOSITORY_ROOT / "static",
                output,
                require_complete_curriculum=True,
            )

            index = (output / "capstones/index.html").read_text()
            self.assertIn("<h1>統合Capstone</h1>", index)
            self.assertNotIn("<script", index.casefold())
            for capstone_id in CAPSTONE_IDS:
                path = output / "capstones" / capstone_id / "index.html"
                document = path.read_text(encoding="utf-8")
                self.assertIn("<h1>", document)
                self.assertIn("<h2>制約</h2>", document)
                self.assertIn("<h2>提出証拠</h2>", document)
                self.assertIn("<h2>Milestone</h2>", document)
                self.assertIn("<h2>レビュー質問</h2>", document)
                self.assertIn("<caption>4段階評価rubric</caption>", document)
                self.assertIn('scope="col"', document)
                self.assertIn('href="../../../lessons/core-', document)
                self.assertNotIn("<script", document.casefold())
                self.assertNotIn(".js", document.casefold())
            base_links = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("capstones/index.html", base_links)

    def test_invalid_capstone_never_replaces_previous_site(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            content = root / "content"
            templates = root / "templates"
            static = root / "static"
            output = root / "site"
            shutil.copytree(REPOSITORY_ROOT / "content", content)
            shutil.copytree(REPOSITORY_ROOT / "templates", templates)
            shutil.copytree(REPOSITORY_ROOT / "static", static)
            build_site(
                content,
                templates,
                static,
                output,
                require_complete_curriculum=True,
            )
            before = {
                path.relative_to(output): path.read_bytes()
                for path in output.rglob("*")
                if path.is_file()
            }
            target = content / "capstones/global-service.json"
            document = json.loads(target.read_text(encoding="utf-8"))
            document["unknown"] = "must fail before publication"
            target.write_text(
                json.dumps(document, ensure_ascii=False),
                encoding="utf-8",
            )

            with self.assertRaises(CurriculumValidationError):
                build_site(
                    content,
                    templates,
                    static,
                    output,
                    require_complete_curriculum=True,
                )

            after = {
                path.relative_to(output): path.read_bytes()
                for path in output.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
