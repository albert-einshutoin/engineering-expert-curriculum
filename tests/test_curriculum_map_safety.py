from __future__ import annotations

import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from curriculum_builder import curriculum_map
from curriculum_builder.errors import CurriculumValidationError
from tools import generate_curriculum_map


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BEGIN = curriculum_map.BEGIN_GENERATED_MAP
END = curriculum_map.END_GENERATED_MAP


class MarkdownCellSafetyTests(unittest.TestCase):
    def test_hostile_markdown_and_html_are_rendered_as_plain_text(self) -> None:
        source = r'<img src="https://example.invalid/x"> [link](https://example.invalid) `code` a|b \\ *em* ~strike~'

        rendered = curriculum_map._markdown_cell(source)

        self.assertEqual(
            rendered,
            r'&lt;img src="https://example.invalid/x"&gt; \[link\](https://example.invalid) \`code\` a\|b \\\\ \*em\* \~strike\~',
        )
        self.assertNotIn("<img", rendered)
        self.assertNotIn("[link](", rendered)

    def test_control_characters_and_oversized_cells_fail_closed(self) -> None:
        for character in ("\x00", "\t", "\n", "\r", "\u2028", "\u202e"):
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


if __name__ == "__main__":
    unittest.main()
