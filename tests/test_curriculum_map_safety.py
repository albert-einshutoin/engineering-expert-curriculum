from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import shutil
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from curriculum_builder import curriculum_map
from curriculum_builder.catalog import load_catalog_bytes
from curriculum_builder.errors import CurriculumValidationError
from tools import generate_curriculum_map


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BEGIN = curriculum_map.BEGIN_GENERATED_MAP
END = curriculum_map.END_GENERATED_MAP


class MarkdownCellSafetyTests(unittest.TestCase):
    def test_hostile_markdown_and_html_are_rendered_as_plain_text(self) -> None:
        source = (
            r'<img src="https://example.invalid/x"> '
            r'[link](https://example.invalid) `code` a|b \\ *em* ~strike~'
        )

        rendered = curriculum_map._markdown_cell(source)

        self.assertEqual(
            rendered,
            r'&lt;img src="https://example.invalid/x"&gt; '
            r'\[link\](https://example.invalid) \`code\` a\|b '
            r'\\\\ \*em\* \~strike\~',
        )
        self.assertNotIn("<img", rendered)
        self.assertNotIn("[link](", rendered)

    def test_control_characters_and_oversized_cells_fail_closed(self) -> None:
        for character in (
            "\x00",
            "\t",
            "\n",
            "\r",
            "\u2028",
            "\u202e",
            "\ud800",
        ):
            with self.subTest(character=ascii(character)):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    "control",
                ):
                    curriculum_map._markdown_cell(f"safe{character}unsafe")

        maximum = curriculum_map.MAX_MARKDOWN_CELL_CHARACTERS
        self.assertEqual(
            curriculum_map._markdown_cell("x" * maximum),
            "x" * maximum,
        )
        with self.assertRaisesRegex(
            CurriculumValidationError,
            "maximum",
        ):
            curriculum_map._markdown_cell("x" * (maximum + 1))

    def test_bare_autolinks_mentions_and_issue_references_are_neutralized(self) -> None:
        source = (
            "https://example.invalid/path www.example.invalid "
            "maintainer@example.invalid @maintainer #123"
        )

        rendered = curriculum_map._markdown_cell(source)

        for active_spelling in (
            "https://",
            "www.example",
            "maintainer@example",
            "@maintainer",
            "#123",
        ):
            self.assertNotIn(active_spelling, rendered)


class CurriculumMapCliContractTests(unittest.TestCase):
    def _repository(self, directory: str, generated: str = "old") -> Path:
        root = Path(directory)
        docs = root / "docs"
        docs.mkdir()
        (docs / "curriculum-map.md").write_text(
            f"# Map\n\n{BEGIN}\n{generated}\n{END}\n",
            encoding="utf-8",
        )
        return root

    def _run(
        self,
        root: Path,
        generated: str,
        *arguments: str,
    ) -> int:
        block = f"{BEGIN}\n{generated}\n{END}"
        with patch.object(
            generate_curriculum_map,
            "render_generated_curriculum_map",
            return_value=block,
        ):
            return generate_curriculum_map.main(
                list(arguments),
                repository_root=root,
            )

    def test_check_reports_current_without_touching_the_document(self) -> None:
        with TemporaryDirectory(
            prefix=".map-cli-current-",
            dir=REPOSITORY_ROOT.parent,
        ) as directory:
            root = self._repository(directory, generated="current")
            target = root / "docs/curriculum-map.md"
            before = target.read_bytes()
            before_stat = target.stat()

            self.assertEqual(self._run(root, "current", "--check"), 0)

            after_stat = target.stat()
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual(after_stat.st_ino, before_stat.st_ino)
            self.assertEqual(after_stat.st_mtime_ns, before_stat.st_mtime_ns)

    def test_check_reports_stale_without_writing(self) -> None:
        with TemporaryDirectory(
            prefix=".map-cli-stale-",
            dir=REPOSITORY_ROOT.parent,
        ) as directory:
            root = self._repository(directory)
            target = root / "docs/curriculum-map.md"
            before = target.read_bytes()
            before_stat = target.stat()

            self.assertEqual(self._run(root, "new", "--check"), 1)

            after_stat = target.stat()
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual(after_stat.st_ino, before_stat.st_ino)
            self.assertEqual(after_stat.st_mtime_ns, before_stat.st_mtime_ns)

    def test_update_is_mode_preserving_atomic_and_idempotent(self) -> None:
        with TemporaryDirectory(
            prefix=".map-cli-update-",
            dir=REPOSITORY_ROOT.parent,
        ) as directory:
            root = self._repository(directory)
            target = root / "docs/curriculum-map.md"
            target.chmod(0o640)
            before_inode = target.stat().st_ino

            self.assertEqual(self._run(root, "new"), 0)

            first = target.read_bytes()
            first_stat = target.stat()
            self.assertIn(f"{BEGIN}\nnew\n{END}".encode(), first)
            self.assertNotEqual(first_stat.st_ino, before_inode)
            self.assertEqual(stat.S_IMODE(first_stat.st_mode), 0o640)
            self.assertEqual(tuple((root / "docs").glob(".curriculum-map-*")), ())

            self.assertEqual(self._run(root, "new"), 0)
            second_stat = target.stat()
            self.assertEqual(target.read_bytes(), first)
            self.assertEqual(second_stat.st_ino, first_stat.st_ino)
            self.assertEqual(second_stat.st_mtime_ns, first_stat.st_mtime_ns)

    def test_invalid_marker_counts_fail_without_changing_the_document(self) -> None:
        invalid_documents = (
            "# no markers\n",
            f"{BEGIN}\nold\n{BEGIN}\nold\n{END}\n",
            f"{BEGIN}\nold\n{END}\n{END}\n",
        )
        for index, document in enumerate(invalid_documents):
            with self.subTest(index=index), TemporaryDirectory(
                prefix=".map-cli-marker-",
                dir=REPOSITORY_ROOT.parent,
            ) as directory:
                root = Path(directory)
                (root / "docs").mkdir()
                target = root / "docs/curriculum-map.md"
                target.write_text(document, encoding="utf-8")
                before = target.read_bytes()

                self.assertEqual(self._run(root, "new"), 1)
                self.assertEqual(target.read_bytes(), before)

    def test_symbolic_linked_document_and_parent_fail_without_writing(self) -> None:
        for linked_parent in (False, True):
            with self.subTest(linked_parent=linked_parent), TemporaryDirectory(
                prefix=".map-cli-link-",
                dir=REPOSITORY_ROOT.parent,
            ) as directory:
                base = Path(directory)
                root = base / "repository"
                root.mkdir()
                outside = base / "outside"
                outside.mkdir()
                victim = outside / "curriculum-map.md"
                victim.write_text(
                    f"# Victim\n{BEGIN}\nold\n{END}\n",
                    encoding="utf-8",
                )
                if linked_parent:
                    (root / "docs").symlink_to(outside, target_is_directory=True)
                else:
                    (root / "docs").mkdir()
                    (root / "docs/curriculum-map.md").symlink_to(victim)
                before = victim.read_bytes()

                self.assertEqual(self._run(root, "new"), 1)

                self.assertEqual(victim.read_bytes(), before)

    def test_oversized_document_fails_before_marker_parsing(self) -> None:
        with TemporaryDirectory(
            prefix=".map-cli-large-",
            dir=REPOSITORY_ROOT.parent,
        ) as directory:
            root = self._repository(directory)
            target = root / "docs/curriculum-map.md"
            target.write_bytes(
                b"x" * (generate_curriculum_map.MAX_CURRICULUM_MAP_BYTES + 1)
            )
            before = target.read_bytes()

            self.assertEqual(self._run(root, "new"), 1)
            self.assertEqual(target.read_bytes(), before)

    def test_partial_write_and_file_fsync_failure_preserve_old_bytes(self) -> None:
        failures = ("write", "fsync")
        for failure in failures:
            with self.subTest(failure=failure), TemporaryDirectory(
                prefix=".map-cli-failure-",
                dir=REPOSITORY_ROOT.parent,
            ) as directory:
                root = self._repository(directory)
                target = root / "docs/curriculum-map.md"
                before = target.read_bytes()
                real_fsync = os.fsync

                def fail_write(descriptor: int, payload: bytes) -> None:
                    os.write(descriptor, payload[:7])
                    raise OSError("injected write failure")

                def fail_file_fsync(descriptor: int) -> None:
                    if stat.S_ISREG(os.fstat(descriptor).st_mode):
                        raise OSError("injected file fsync failure")
                    real_fsync(descriptor)

                patcher = (
                    patch.object(
                        generate_curriculum_map,
                        "_write_all",
                        side_effect=fail_write,
                    )
                    if failure == "write"
                    else patch.object(
                        generate_curriculum_map.os,
                        "fsync",
                        side_effect=fail_file_fsync,
                    )
                )
                with patcher:
                    self.assertEqual(self._run(root, "new"), 1)

                self.assertEqual(target.read_bytes(), before)
                self.assertEqual(
                    tuple((root / "docs").glob(".curriculum-map-*")),
                    (),
                )

    def test_target_replacement_during_write_is_not_overwritten(self) -> None:
        with TemporaryDirectory(
            prefix=".map-cli-race-",
            dir=REPOSITORY_ROOT.parent,
        ) as directory:
            root = self._repository(directory)
            target = root / "docs/curriculum-map.md"
            replacement = root / "docs/concurrent.md"
            concurrent = b"concurrent replacement\n"
            replacement.write_bytes(concurrent)
            real_write_all = generate_curriculum_map._write_all

            def replace_target(descriptor: int, payload: bytes) -> None:
                real_write_all(descriptor, payload)
                os.replace(replacement, target)

            with patch.object(
                generate_curriculum_map,
                "_write_all",
                side_effect=replace_target,
            ):
                self.assertEqual(self._run(root, "new"), 1)

            self.assertEqual(target.read_bytes(), concurrent)
            self.assertEqual(
                tuple((root / "docs").glob(".curriculum-map-*")),
                (),
            )

    def test_success_fsyncs_file_before_parent_directory(self) -> None:
        with TemporaryDirectory(
            prefix=".map-cli-fsync-",
            dir=REPOSITORY_ROOT.parent,
        ) as directory:
            root = self._repository(directory)
            events: list[str] = []
            real_fsync = os.fsync

            def record_fsync(descriptor: int) -> None:
                events.append(
                    "directory"
                    if stat.S_ISDIR(os.fstat(descriptor).st_mode)
                    else "file"
                )
                real_fsync(descriptor)

            with patch.object(
                generate_curriculum_map.os,
                "fsync",
                side_effect=record_fsync,
            ):
                self.assertEqual(self._run(root, "new"), 0)

            self.assertEqual(events, ["file", "directory"])


class CurriculumMapReleaseSnapshotTests(unittest.TestCase):
    def _copy_content(self, directory: str) -> Path:
        root = Path(directory)
        shutil.copytree(REPOSITORY_ROOT / "content", root / "content")
        return root

    def test_canonical_but_wrong_catalog_sha_is_rejected(self) -> None:
        with TemporaryDirectory(
            prefix=".map-catalog-sha-",
            dir=REPOSITORY_ROOT.parent,
        ) as directory:
            root = self._copy_content(directory)
            catalog = root / "content/catalog.json"
            altered = catalog.read_bytes().replace(
                b"Programming",
                b"ProgramminX",
                1,
            )
            self.assertEqual(len(load_catalog_bytes(altered, catalog)), 1_140)
            catalog.write_bytes(altered)

            with self.assertRaisesRegex(
                CurriculumValidationError,
                "SHA-256 mismatch",
            ):
                curriculum_map.render_generated_curriculum_map(root)

    def test_catalog_symlink_and_oversize_fail_at_the_bounded_reader(self) -> None:
        cases = ("symlink", "oversize")
        for case in cases:
            with self.subTest(case=case), TemporaryDirectory(
                prefix=".map-catalog-input-",
                dir=REPOSITORY_ROOT.parent,
            ) as directory:
                root = self._copy_content(directory)
                catalog = root / "content/catalog.json"
                if case == "symlink":
                    catalog.unlink()
                    catalog.symlink_to(REPOSITORY_ROOT / "content/catalog.json")
                    expected = "regular file"
                else:
                    catalog.write_bytes(
                        b"x" * (curriculum_map.MAX_CATALOG_BYTES + 1)
                    )
                    expected = "maximum byte count"

                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    expected,
                ):
                    curriculum_map.render_generated_curriculum_map(root)

    def test_release_input_change_between_snapshots_fails_closed(self) -> None:
        real_capture = curriculum_map._capture_release_inputs
        calls = 0

        def return_changed_second_snapshot(handle: object) -> object:
            nonlocal calls
            calls += 1
            snapshot = real_capture(handle)
            if calls == 2:
                return replace(
                    snapshot,
                    roadmap_bytes=snapshot.roadmap_bytes + b" ",
                )
            return snapshot

        with patch.object(
            curriculum_map,
            "_capture_release_inputs",
            side_effect=return_changed_second_snapshot,
        ):
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "release inputs changed during map generation",
            ):
                curriculum_map.render_generated_curriculum_map(REPOSITORY_ROOT)
        self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
