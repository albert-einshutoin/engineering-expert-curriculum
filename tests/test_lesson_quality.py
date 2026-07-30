from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from curriculum_builder.errors import CurriculumValidationError
from curriculum_builder.lessons import MAX_LESSON_BYTES, load_lesson


FIXTURES = Path(__file__).parent / "fixtures"
COMPLETE = FIXTURES / "complete-lesson.json"
INCOMPLETE = FIXTURES / "incomplete-lesson.json"
CAPABILITY_PROGRESSION = [
    {
        "level": "recognize",
        "criterion": "制約と利害関係者を特定し、判断対象の境界を示せる",
        "evidenceIds": ["lab-map"],
    },
    {
        "level": "explain",
        "criterion": "選択肢の機構と主要なトレードオフを自分の言葉で説明できる",
        "evidenceIds": ["teach-back"],
    },
    {
        "level": "apply",
        "criterion": "制約に基づく比較を行い、レビュー可能な判断記録を作成できる",
        "evidenceIds": ["lab-map"],
    },
    {
        "level": "diagnose",
        "criterion": "観測した証拠から障害の因果経路を切り分け、反証を示せる",
        "evidenceIds": ["assessment"],
    },
    {
        "level": "lead",
        "criterion": "異なる領域へ判断方法を移し、再評価条件を関係者へ説明できる",
        "evidenceIds": ["transfer"],
    },
]


class LessonQualityTests(unittest.TestCase):
    def complete_document(self) -> dict[str, object]:
        loaded = json.loads(COMPLETE.read_text(encoding="utf-8"))
        self.assertIsInstance(loaded, dict)
        return loaded

    def write_document(
        self, directory: str, document: object, name: str = "lesson.json"
    ) -> Path:
        path = Path(directory).resolve() / name
        path.write_text(
            json.dumps(document, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def add_capability_progression(
        self, document: dict[str, object]
    ) -> dict[str, object]:
        document["capabilityProgression"] = json.loads(
            json.dumps(CAPABILITY_PROGRESSION, ensure_ascii=False)
        )
        return document

    def assert_invalid(
        self,
        document: object,
        pattern: str,
        *,
        name: str = "lesson.json",
    ) -> None:
        with TemporaryDirectory() as directory:
            path = self.write_document(directory, document, name)
            with self.assertRaisesRegex(CurriculumValidationError, pattern):
                load_lesson(path)

    def test_complete_fixture_connects_every_objective_to_evidence(self) -> None:
        lesson = load_lesson(COMPLETE)

        self.assertEqual(lesson.id, "core-01-systems-tradeoffs")
        self.assertEqual(lesson.status, "complete")
        self.assertEqual(lesson.review_intervals, (1, 7, 30, 90))
        self.assertEqual(
            {evidence.kind for evidence in lesson.evidence},
            {"artifact", "explanation", "reasoning", "transfer"},
        )
        evidence_ids = {evidence.id for evidence in lesson.evidence}
        for objective in lesson.objectives:
            self.assertTrue(objective.evidence_ids)
            self.assertLessEqual(set(objective.evidence_ids), evidence_ids)

    def test_complete_status_reports_all_missing_quality_dimensions(self) -> None:
        with self.assertRaisesRegex(
            CurriculumValidationError,
            r"complete lesson missing: teachBack, transferTask",
        ) as caught:
            load_lesson(INCOMPLETE)

        self.assertIn("core-01-systems-tradeoffs", str(caught.exception))
        self.assertIn(INCOMPLETE.name, str(caught.exception))

    def test_complete_status_requires_capability_progression(self) -> None:
        raw = self.complete_document()
        del raw["capabilityProgression"]
        self.assert_invalid(
            raw,
            r"complete lesson missing: capabilityProgression",
        )

    def test_capability_progression_is_typed_ordered_and_immutable(self) -> None:
        raw = self.add_capability_progression(self.complete_document())
        with TemporaryDirectory() as directory:
            lesson = load_lesson(self.write_document(directory, raw))

        self.assertEqual(
            tuple(item.level for item in lesson.capability_progression),
            ("recognize", "explain", "apply", "diagnose", "lead"),
        )
        self.assertEqual(
            lesson.capability_progression[0].evidence_ids,
            ("lab-map",),
        )
        with self.assertRaises(FrozenInstanceError):
            lesson.capability_progression[0].criterion = "changed"  # type: ignore[misc]

    def test_capability_progression_rejects_invalid_mastery_contracts(self) -> None:
        mutations = (
            (
                "ordered",
                lambda progression: progression.__setitem__(
                    slice(0, 2), [progression[1], progression[0]]
                ),
            ),
            (
                "duplicate",
                lambda progression: progression[1].__setitem__(
                    "level", "recognize"
                ),
            ),
            (
                "criterion",
                lambda progression: progression[0].__setitem__(
                    "criterion", ""
                ),
            ),
            (
                "unknown evidence",
                lambda progression: progression[0].__setitem__(
                    "evidenceIds", ["missing-evidence"]
                ),
            ),
            (
                "duplicate evidence",
                lambda progression: progression[0].__setitem__(
                    "evidenceIds", ["lab-map", "lab-map"]
                ),
            ),
            (
                "five capability levels",
                lambda progression: progression.pop(),
            ),
            (
                "unknown fields",
                lambda progression: progression[0].__setitem__(
                    "unexpected", True
                ),
            ),
        )
        for message, mutate in mutations:
            with self.subTest(message=message):
                raw = self.add_capability_progression(
                    self.complete_document()
                )
                progression = raw["capabilityProgression"]
                self.assertIsInstance(progression, list)
                mutate(progression)
                self.assert_invalid(raw, message)

    def test_draft_capability_progression_must_be_an_ordered_prefix(self) -> None:
        raw = self.add_capability_progression(self.complete_document())
        raw["status"] = "draft"
        raw["capabilityProgression"] = raw["capabilityProgression"][:2]
        with TemporaryDirectory() as directory:
            lesson = load_lesson(self.write_document(directory, raw))
        self.assertEqual(
            tuple(item.level for item in lesson.capability_progression),
            ("recognize", "explain"),
        )

        raw = self.add_capability_progression(self.complete_document())
        raw["status"] = "draft"
        raw["capabilityProgression"] = [
            raw["capabilityProgression"][0],
            raw["capabilityProgression"][2],
        ]
        self.assert_invalid(raw, "ordered prefix")

    def test_capability_levels_may_reference_any_known_evidence_kind(self) -> None:
        raw = self.add_capability_progression(self.complete_document())
        raw["capabilityProgression"][0]["evidenceIds"] = ["assessment"]
        with TemporaryDirectory() as directory:
            lesson = load_lesson(self.write_document(directory, raw))
        self.assertEqual(
            lesson.capability_progression[0].evidence_ids,
            ("assessment",),
        )

    def test_track_gates_use_typed_lesson_fields_without_raw_metadata(self) -> None:
        raw = self.add_capability_progression(self.complete_document())
        with TemporaryDirectory() as directory:
            lesson = load_lesson(self.write_document(directory, raw))

        self.assertIsNotNone(lesson.lab)
        assert lesson.lab is not None
        self.assertEqual(lesson.lab.artifact, "decision-record.md")
        self.assertEqual(
            lesson.transfer_task,
            "医療予約システムという別領域で同じ比較をやり直す。",
        )
        self.assertEqual(lesson.prerequisite_ids, ())
        self.assertFalse(hasattr(lesson, "raw"))

    def test_complete_status_rejects_explicit_null_quality_dimensions(self) -> None:
        for field in ("lab", "assessment", "rubric", "sources", "review"):
            with self.subTest(field=field):
                raw = self.complete_document()
                raw[field] = None
                self.assert_invalid(raw, rf"{field}.*required|{field}.*complete")

    def test_draft_allows_quality_work_to_remain_incomplete(self) -> None:
        raw = self.complete_document()
        raw["status"] = "draft"
        raw["objectives"] = []
        raw["evidence"] = []
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
            del raw[field]

        with TemporaryDirectory() as directory:
            lesson = load_lesson(self.write_document(directory, raw))

        self.assertEqual(lesson.status, "draft")
        self.assertEqual(lesson.objectives, ())
        self.assertIsNone(lesson.lab)
        self.assertEqual(lesson.review_intervals, ())

    def test_rubric_requires_four_observable_levels(self) -> None:
        raw = self.complete_document()
        del raw["rubric"][0]["levels"]["exemplary"]  # type: ignore[index]

        self.assert_invalid(raw, "rubric levels")

    def test_duplicate_json_keys_are_rejected_at_every_depth(self) -> None:
        raw = COMPLETE.read_text(encoding="utf-8")
        cases = {
            "root": raw.replace('"version": 1,', '"version": 1, "version": 1,', 1),
            "nested": raw.replace(
                '"id": "obj-1",',
                '"id": "obj-1", "id": "obj-duplicate",',
                1,
            ),
        }
        for label, duplicate in cases.items():
            with self.subTest(label=label), TemporaryDirectory() as directory:
                path = Path(directory).resolve() / "duplicate.json"
                path.write_text(duplicate, encoding="utf-8")
                with self.assertRaisesRegex(
                    CurriculumValidationError, r"duplicate JSON key"
                ):
                    load_lesson(path)

    def test_untrusted_json_key_names_are_not_echoed_in_errors(self) -> None:
        raw = self.complete_document()
        raw["customer-secret-token"] = True
        with self.assertRaises(CurriculumValidationError) as caught:
            with TemporaryDirectory() as directory:
                load_lesson(self.write_document(directory, raw))
        self.assertIn("unknown fields", str(caught.exception))
        self.assertNotIn("customer-secret-token", str(caught.exception))

        duplicate = COMPLETE.read_text(encoding="utf-8").replace(
            '"version": 1,',
            '"customer-secret-token": 1, "customer-secret-token": 2,',
            1,
        )
        with TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "duplicate.json"
            path.write_text(duplicate, encoding="utf-8")
            with self.assertRaises(CurriculumValidationError) as caught:
                load_lesson(path)
        self.assertIn("duplicate JSON key", str(caught.exception))
        self.assertNotIn("customer-secret-token", str(caught.exception))

    def test_unknown_fields_are_rejected_at_root_and_every_nested_schema(self) -> None:
        mutations = (
            ("root", lambda raw: raw.__setitem__("unexpected", True)),
            ("objective", lambda raw: raw["objectives"][0].__setitem__("x", 1)),
            ("evidence", lambda raw: raw["evidence"][0].__setitem__("x", 1)),
            (
                "capability-progression",
                lambda raw: raw["capabilityProgression"][0].__setitem__("x", 1),
            ),
            ("lab", lambda raw: raw["lab"].__setitem__("x", 1)),
            ("assessment", lambda raw: raw["assessment"][0].__setitem__("x", 1)),
            ("rubric", lambda raw: raw["rubric"][0].__setitem__("x", 1)),
            (
                "rubric-levels",
                lambda raw: raw["rubric"][0]["levels"].__setitem__("x", "value"),
            ),
            ("source", lambda raw: raw["sources"][0].__setitem__("x", 1)),
            ("review", lambda raw: raw["review"].__setitem__("x", 1)),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                raw = self.complete_document()
                mutate(raw)
                self.assert_invalid(raw, r"unknown fields")

    def test_domain_objects_are_deeply_immutable_and_do_not_expose_raw_dicts(
        self,
    ) -> None:
        lesson = load_lesson(COMPLETE)

        with self.assertRaises(FrozenInstanceError):
            lesson.status = "draft"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            lesson.evidence[0].kind = "transfer"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            lesson.rubric[0].levels.exemplary = "changed"  # type: ignore[misc]
        self.assertIsInstance(lesson.objectives, tuple)
        self.assertIsInstance(lesson.lab.steps, tuple)  # type: ignore[union-attr]
        self.assertFalse(hasattr(lesson, "raw"))

    def test_load_lesson_requires_an_exact_native_path_type(self) -> None:
        native_type = type(Path())

        class DerivedPath(native_type):
            pass

        for value in (str(COMPLETE), DerivedPath(COMPLETE)):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaisesRegex(
                    CurriculumValidationError, r"path must be an exact Path"
                ):
                    load_lesson(value)  # type: ignore[arg-type]

    def test_symlink_and_non_regular_files_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            symlink = root / "lesson-link.json"
            symlink.symlink_to(COMPLETE)
            fifo = root / "lesson.fifo"
            os.mkfifo(fifo)
            folder = root / "lesson.json"
            folder.mkdir()

            for path in (symlink, fifo, folder):
                with self.subTest(mode=stat.S_IFMT(os.lstat(path).st_mode)):
                    with self.assertRaisesRegex(
                        CurriculumValidationError, r"regular file|read safely"
                    ):
                        load_lesson(path)

    def test_symlinked_parent_directory_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            real_parent = root / "real"
            real_parent.mkdir()
            (real_parent / "lesson.json").write_bytes(COMPLETE.read_bytes())
            linked_parent = root / "linked"
            linked_parent.symlink_to(real_parent, target_is_directory=True)

            with self.assertRaisesRegex(
                CurriculumValidationError, r"symbolic link"
            ):
                load_lesson(linked_parent / "lesson.json")

    def test_symlinked_ancestor_above_the_immediate_parent_is_rejected(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            real_ancestor = root / "real"
            nested = real_ancestor / "level-two"
            nested.mkdir(parents=True)
            (nested / "lesson.json").write_bytes(COMPLETE.read_bytes())
            linked_ancestor = root / "linked"
            linked_ancestor.symlink_to(real_ancestor, target_is_directory=True)

            with self.assertRaisesRegex(
                CurriculumValidationError, r"symbolic link"
            ):
                load_lesson(
                    linked_ancestor / "level-two" / "lesson.json"
                )

    def test_lexical_parent_traversal_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            safe = root / "safe"
            safe.mkdir()
            (safe / "lesson.json").write_bytes(COMPLETE.read_bytes())
            ambiguous = safe / ".." / "safe" / "lesson.json"

            with self.assertRaisesRegex(
                CurriculumValidationError, r"parent traversal"
            ):
                load_lesson(ambiguous)

    def test_lesson_file_size_and_utf8_are_bounded(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            oversized = root / "oversized.json"
            oversized.write_bytes(b" " * (MAX_LESSON_BYTES + 1))
            invalid_utf8 = root / "invalid-utf8.json"
            invalid_utf8.write_bytes(b'{"version": "\xff"}')

            with self.assertRaisesRegex(
                CurriculumValidationError, r"maximum byte count"
            ):
                load_lesson(oversized)
            with self.assertRaisesRegex(
                CurriculumValidationError, r"valid UTF-8|UTF-8"
            ):
                load_lesson(invalid_utf8)

    def test_pathname_rebinding_during_read_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / "lesson.json"
            path.write_bytes(COMPLETE.read_bytes())
            replacement = root / "replacement.json"
            replacement.write_bytes(COMPLETE.read_bytes())
            real_open = os.open
            replaced = False

            def replace_after_open(target: object, flags: int, *args: object, **kwargs: object) -> int:
                nonlocal replaced
                descriptor = real_open(target, flags, *args, **kwargs)
                if not replaced and Path(target).name == "lesson.json":
                    replaced = True
                    path.unlink()
                    replacement.rename(path)
                return descriptor

            with patch(
                "curriculum_builder.lesson_io.os.open",
                side_effect=replace_after_open,
            ):
                with self.assertRaisesRegex(
                    CurriculumValidationError, r"changed during read"
                ):
                    load_lesson(path)
            self.assertTrue(replaced)

    def test_ancestor_rebinding_to_a_hard_link_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            ancestor = root / "ancestor"
            nested = ancestor / "nested"
            nested.mkdir(parents=True)
            path = nested / "lesson.json"
            path.write_bytes(COMPLETE.read_bytes())
            replacement = root / "replacement"
            replacement_nested = replacement / "nested"
            replacement_nested.mkdir(parents=True)
            os.link(path, replacement_nested / "lesson.json")
            retired = root / "retired"
            real_open = os.open
            swapped = False

            def swap_ancestor_after_file_open(
                target: object,
                flags: int,
                *args: object,
                **kwargs: object,
            ) -> int:
                nonlocal swapped
                descriptor = real_open(target, flags, *args, **kwargs)
                if not swapped and Path(target).name == "lesson.json":
                    swapped = True
                    ancestor.rename(retired)
                    replacement.rename(ancestor)
                return descriptor

            with patch(
                "curriculum_builder.lesson_io.os.open",
                side_effect=swap_ancestor_after_file_open,
            ):
                with self.assertRaisesRegex(
                    CurriculumValidationError, r"ancestor changed during read"
                ):
                    load_lesson(path)
            self.assertTrue(swapped)

    def test_transient_ancestor_rebinding_is_rejected_after_restore(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            ancestor = root / "ancestor"
            nested = ancestor / "nested"
            nested.mkdir(parents=True)
            path = nested / "lesson.json"
            path.write_bytes(COMPLETE.read_bytes())
            replacement = root / "replacement"
            replacement_nested = replacement / "nested"
            replacement_nested.mkdir(parents=True)
            os.link(path, replacement_nested / "lesson.json")
            retired = root / "retired"
            real_open = os.open
            swapped = False

            def swap_and_restore_after_file_open(
                target: object,
                flags: int,
                *args: object,
                **kwargs: object,
            ) -> int:
                nonlocal swapped
                descriptor = real_open(target, flags, *args, **kwargs)
                if not swapped and Path(target).name == "lesson.json":
                    swapped = True
                    ancestor.rename(retired)
                    replacement.rename(ancestor)
                    ancestor.rename(replacement)
                    retired.rename(ancestor)
                return descriptor

            with patch(
                "curriculum_builder.lesson_io.os.open",
                side_effect=swap_and_restore_after_file_open,
            ):
                with self.assertRaisesRegex(
                    CurriculumValidationError, r"ancestor changed during read"
                ):
                    load_lesson(path)
            self.assertTrue(swapped)

    def test_post_read_metadata_change_is_rejected(self) -> None:
        real_fstat = os.fstat
        regular_call_count = 0

        def changing_fstat(descriptor: int) -> object:
            nonlocal regular_call_count
            result = real_fstat(descriptor)
            if not stat.S_ISREG(result.st_mode):
                return result
            regular_call_count += 1
            if regular_call_count != 2:
                return result

            class ChangedMetadata:
                def __getattr__(self, name: str) -> object:
                    original = getattr(result, name)
                    if name == "st_mtime_ns":
                        return original + 1
                    return original

            return ChangedMetadata()

        with patch(
            "curriculum_builder.lesson_io.os.fstat",
            side_effect=changing_fstat,
        ):
            with self.assertRaisesRegex(
                CurriculumValidationError, r"changed during read"
            ):
                load_lesson(COMPLETE)

    def test_os_errors_do_not_leak_private_paths_or_contents(self) -> None:
        with patch(
            "curriculum_builder.lesson_io.os.open",
            side_effect=OSError("/private/customer/secret.json"),
        ):
            with self.assertRaises(CurriculumValidationError) as caught:
                load_lesson(COMPLETE)

        message = str(caught.exception)
        self.assertIn(COMPLETE.name, message)
        self.assertNotIn("/private/customer", message)
        self.assertNotIn("システム思考", message)

    def test_all_descriptors_close_once_in_reverse_open_order(self) -> None:
        real_open = os.open
        real_close = os.close
        opened: list[int] = []
        closed: list[int] = []

        def track_open(
            target: object,
            flags: int,
            *args: object,
            **kwargs: object,
        ) -> int:
            descriptor = real_open(target, flags, *args, **kwargs)
            opened.append(descriptor)
            return descriptor

        def track_close(descriptor: int) -> None:
            closed.append(descriptor)
            real_close(descriptor)

        with (
            patch(
                "curriculum_builder.lesson_io.os.open",
                side_effect=track_open,
            ),
            patch(
                "curriculum_builder.lesson_io.os.close",
                side_effect=track_close,
            ),
        ):
            load_lesson(COMPLETE)

        self.assertGreater(len(opened), 2)
        self.assertEqual(closed, list(reversed(opened)))
        self.assertEqual(len(closed), len(set(closed)))

    def test_successful_read_reports_close_failure_and_closes_remaining_fds(
        self,
    ) -> None:
        real_close = os.close
        closed: list[int] = []

        def close_with_one_failure(descriptor: int) -> None:
            closed.append(descriptor)
            real_close(descriptor)
            if len(closed) == 1:
                raise OSError("private-close-detail")

        with patch(
            "curriculum_builder.lesson_io.os.close",
            side_effect=close_with_one_failure,
        ):
            with self.assertRaisesRegex(
                CurriculumValidationError,
                r"lesson descriptor close failed",
            ) as caught:
                load_lesson(COMPLETE)

        self.assertGreater(len(closed), 2)
        self.assertEqual(len(closed), len(set(closed)))
        self.assertNotIn("private-close-detail", str(caught.exception))

    def test_primary_read_failure_is_preserved_when_close_also_fails(
        self,
    ) -> None:
        real_close = os.close
        closed: list[int] = []

        def close_with_one_failure(descriptor: int) -> None:
            closed.append(descriptor)
            real_close(descriptor)
            if len(closed) == 1:
                raise OSError("private-close-detail")

        with (
            patch(
                "curriculum_builder.lesson_io.os.read",
                side_effect=OSError("private-read-detail"),
            ),
            patch(
                "curriculum_builder.lesson_io.os.close",
                side_effect=close_with_one_failure,
            ),
        ):
            with self.assertRaisesRegex(
                CurriculumValidationError,
                r"lesson cannot be read safely",
            ) as caught:
                load_lesson(COMPLETE)

        self.assertGreater(len(closed), 2)
        self.assertEqual(len(closed), len(set(closed)))
        self.assertNotIn("private-read-detail", str(caught.exception))
        self.assertNotIn("private-close-detail", str(caught.exception))
        self.assertIn(
            "lesson descriptor also failed to close",
            getattr(caught.exception, "__notes__", ()),
        )

    def test_boolean_values_are_not_accepted_as_integers(self) -> None:
        mutations = (
            ("version", lambda raw: raw.__setitem__("version", True)),
            ("stage", lambda raw: raw.__setitem__("stage", True)),
            (
                "estimatedMinutes",
                lambda raw: raw.__setitem__("estimatedMinutes", True),
            ),
            (
                "review interval",
                lambda raw: raw["review"]["intervalDays"].__setitem__(0, True),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                raw = self.complete_document()
                mutate(raw)
                self.assert_invalid(raw, rf"{label}|integer")

    def test_ids_must_match_their_patterns_and_be_unique(self) -> None:
        mutations = (
            ("lesson", lambda raw: raw.__setitem__("id", "CORE-01 bad")),
            (
                "objective",
                lambda raw: raw["objectives"][0].__setitem__("id", "objective 1"),
            ),
            (
                "evidence",
                lambda raw: raw["evidence"][0].__setitem__("id", "Evidence_1"),
            ),
            (
                "prerequisite",
                lambda raw: raw["prerequisiteIds"].append("core-1-bad"),
            ),
            (
                "duplicate objective",
                lambda raw: raw["objectives"][1].__setitem__("id", "obj-1"),
            ),
            (
                "duplicate evidence",
                lambda raw: raw["evidence"][1].__setitem__("id", "lab-map"),
            ),
            (
                "duplicate prerequisite",
                lambda raw: raw["prerequisiteIds"].extend(
                    ["core-02-algorithms-measurement"] * 2
                ),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                raw = self.complete_document()
                mutate(raw)
                self.assert_invalid(raw, r"invalid|duplicate")

    def test_self_prerequisite_and_unknown_evidence_are_rejected(self) -> None:
        raw = self.complete_document()
        raw["prerequisiteIds"].append(raw["id"])
        self.assert_invalid(raw, r"self prerequisite")

        raw = self.complete_document()
        raw["objectives"][0]["evidenceIds"].append("missing-evidence")
        self.assert_invalid(raw, r"unknown evidence.*missing-evidence")

    def test_complete_objective_and_evidence_mastery_limits(self) -> None:
        raw = self.complete_document()
        raw["objectives"] = raw["objectives"][:2]
        self.assert_invalid(raw, r"3 to 6 objectives")

        raw = self.complete_document()
        raw["objectives"][0]["evidenceIds"] = []
        self.assert_invalid(raw, r"objective.*evidence")

        raw = self.complete_document()
        raw["evidence"] = raw["evidence"][:-1]
        raw["objectives"][0]["evidenceIds"] = ["lab-map"]
        raw["objectives"][2]["evidenceIds"] = ["teach-back"]
        self.assert_invalid(raw, r"evidence kinds.*transfer")

        raw = self.complete_document()
        raw["objectives"] = raw["objectives"] * 3
        self.assert_invalid(raw, r"3 to 6 objectives")

    def test_complete_lab_teach_back_transfer_and_assessment_are_substantive(
        self,
    ) -> None:
        mutations = (
            (
                "lab title",
                lambda raw: raw["lab"].__setitem__("title", ""),
            ),
            (
                "lab artifact",
                lambda raw: raw["lab"].__setitem__("artifact", ""),
            ),
            (
                "lab steps",
                lambda raw: raw["lab"].__setitem__("steps", ["one", "two"]),
            ),
            ("teachBack", lambda raw: raw.__setitem__("teachBack", "")),
            ("transferTask", lambda raw: raw.__setitem__("transferTask", "")),
            ("assessment", lambda raw: raw.__setitem__("assessment", [])),
            (
                "assessment prompt",
                lambda raw: raw["assessment"][0].__setitem__("prompt", ""),
            ),
            (
                "expectedEvidence",
                lambda raw: raw["assessment"][0].__setitem__(
                    "expectedEvidence", ""
                ),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                raw = self.complete_document()
                mutate(raw)
                self.assert_invalid(raw, label)

    def test_rubric_dimensions_and_levels_are_exact_distinct_and_nonempty(
        self,
    ) -> None:
        raw = self.complete_document()
        raw["rubric"][1]["dimension"] = "technical-correctness"
        self.assert_invalid(raw, r"rubric dimensions")

        raw = self.complete_document()
        raw["rubric"][0]["levels"]["proficient"] = ""
        self.assert_invalid(raw, r"rubric.*proficient|proficient.*non-empty")

    def test_sources_are_distinct_authoritative_https_urls(self) -> None:
        mutations = (
            (
                "at least two sources",
                lambda raw: raw.__setitem__("sources", raw["sources"][:1]),
            ),
            (
                "source URL must use HTTPS",
                lambda raw: raw["sources"][0].__setitem__(
                    "url", "http://example.com/reference"
                ),
            ),
            (
                "source URL must have a host",
                lambda raw: raw["sources"][0].__setitem__("url", "https:///path"),
            ),
            (
                "source kind",
                lambda raw: raw["sources"][0].__setitem__("kind", "blog"),
            ),
            (
                "duplicate source URL",
                lambda raw: raw["sources"][1].__setitem__(
                    "url", raw["sources"][0]["url"]
                ),
            ),
            (
                "source URL credentials",
                lambda raw: raw["sources"][0].__setitem__(
                    "url", "https://user:password@example.com/reference"
                ),
            ),
            (
                "source URL backslashes",
                lambda raw: raw["sources"][0].__setitem__(
                    "url", "https://example.com/reference\\hidden"
                ),
            ),
            (
                "source URL encoded controls",
                lambda raw: raw["sources"][0].__setitem__(
                    "url", "https://example.com/reference%0a-hidden"
                ),
            ),
            (
                "source URL encoded controls",
                lambda raw: raw["sources"][0].__setitem__(
                    "url", "https://example.com/reference%C2%80hidden"
                ),
            ),
        )
        for message, mutate in mutations:
            with self.subTest(message=message):
                raw = self.complete_document()
                mutate(raw)
                self.assert_invalid(raw, message)

    def test_source_identity_normalizes_host_port_and_fragment(self) -> None:
        cases = (
            (
                "host case",
                "https://EXAMPLE.com/reference",
                "https://example.com/reference",
            ),
            (
                "default port",
                "https://example.com:443/reference",
                "https://example.com/reference",
            ),
            (
                "trailing dot",
                "https://example.com./reference",
                "https://example.com/reference",
            ),
            (
                "fragment",
                "https://example.com/reference#first",
                "https://example.com/reference#second",
            ),
        )
        for label, first, second in cases:
            with self.subTest(label=label):
                raw = self.complete_document()
                raw["sources"][0]["url"] = first
                raw["sources"][1]["url"] = second
                self.assert_invalid(raw, r"duplicate source URL")

    def test_source_identity_normalizes_empty_path_to_root(self) -> None:
        raw = self.complete_document()
        raw["sources"][0]["url"] = "https://example.com"
        raw["sources"][1]["url"] = "https://example.com/"

        self.assert_invalid(raw, r"duplicate source URL")

    def test_source_identity_keeps_distinct_paths_and_queries(self) -> None:
        cases = (
            (
                "path",
                "https://example.com/first",
                "https://example.com/second",
            ),
            (
                "query",
                "https://example.com/reference?version=1",
                "https://example.com/reference?version=2",
            ),
        )
        for label, first, second in cases:
            with self.subTest(label=label), TemporaryDirectory() as directory:
                raw = self.complete_document()
                raw["sources"][0]["url"] = first
                raw["sources"][1]["url"] = second
                lesson = load_lesson(self.write_document(directory, raw))
                self.assertEqual(
                    tuple(source.url for source in lesson.sources),
                    (first, second),
                )

    def test_source_url_rejects_invalid_dns_names_and_ports(self) -> None:
        invalid_hosts = (
            ".",
            "bad_host.example",
            "-bad.example",
            "bad-.example",
            "bad..example",
            f"{'a' * 64}.example",
            ".".join(["a" * 63] * 4),
        )
        for host in invalid_hosts:
            with self.subTest(host=host):
                raw = self.complete_document()
                raw["sources"][0]["url"] = f"https://{host}/reference"
                self.assert_invalid(raw, r"source URL host")

        for port in ("", "0", "65536", "invalid"):
            with self.subTest(port=port):
                raw = self.complete_document()
                raw["sources"][0]["url"] = (
                    f"https://example.com:{port}/reference"
                )
                self.assert_invalid(raw, r"source URL port")

    def test_source_url_preserves_valid_unicode_display_url(self) -> None:
        for display_url in (
            "https://例え.テスト/リファレンス",
            "https://example.com",
        ):
            with self.subTest(display_url=display_url):
                raw = self.complete_document()
                raw["sources"][0]["url"] = display_url
                with TemporaryDirectory() as directory:
                    lesson = load_lesson(self.write_document(directory, raw))
                self.assertEqual(lesson.sources[0].url, display_url)

    def test_review_cycle_has_exact_intervals_and_two_prompts(self) -> None:
        raw = self.complete_document()
        raw["review"]["intervalDays"] = [1, 7, 30]
        self.assert_invalid(raw, r"review intervals")

        raw = self.complete_document()
        raw["review"]["prompts"] = ["一つだけ"]
        self.assert_invalid(raw, r"review prompts")

    def test_date_estimate_stage_difficulty_track_and_status_are_bounded(self) -> None:
        mutations = (
            (
                "updatedAt",
                lambda raw: raw.__setitem__("updatedAt", "2026-02-30"),
            ),
            (
                "estimatedMinutes",
                lambda raw: raw.__setitem__("estimatedMinutes", 0),
            ),
            ("stage", lambda raw: raw.__setitem__("stage", 99)),
            (
                "difficulty",
                lambda raw: raw.__setitem__("difficulty", "impossible"),
            ),
            ("track", lambda raw: raw.__setitem__("track", "unknown")),
            ("status", lambda raw: raw.__setitem__("status", "published")),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                raw = self.complete_document()
                mutate(raw)
                self.assert_invalid(raw, label)

    def test_text_rejects_untrimmed_control_and_excessive_values(self) -> None:
        mutations = (
            ("trimmed", lambda raw: raw.__setitem__("title", " padded")),
            ("control", lambda raw: raw.__setitem__("summary", "safe\nunsafe")),
            (
                "maximum length",
                lambda raw: raw.__setitem__("teachBack", "a" * 10_001),
            ),
        )
        for message, mutate in mutations:
            with self.subTest(message=message):
                raw = self.complete_document()
                mutate(raw)
                self.assert_invalid(raw, message)

    def test_collection_counts_are_bounded(self) -> None:
        raw = self.complete_document()
        raw["prerequisiteIds"] = [
            f"core-{index:02d}-lesson" for index in range(2, 22)
        ]
        self.assert_invalid(raw, r"prerequisiteIds.*at most")

        raw = self.complete_document()
        raw["lab"]["steps"] = [f"step-{index}" for index in range(100)]
        self.assert_invalid(raw, r"lab steps.*at most")


if __name__ == "__main__":
    unittest.main()
