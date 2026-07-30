from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.migrate_prototype import LEGACY_PATHS, preserve_prototype


class PrototypeMigrationTests(unittest.TestCase):
    def test_moves_only_allowlisted_files_and_verifies_manifest(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets").mkdir()
            (root / "assets" / "styles.css").write_text("body{}", encoding="utf-8")
            (root / "index.html").write_text("<main>legacy</main>", encoding="utf-8")
            (root / ".git").mkdir()
            archive = root / ".archive" / "prototype-v1"

            manifest = preserve_prototype(
                source=root,
                archive=archive,
                allowed_paths=("assets", "index.html"),
            )

            self.assertFalse((root / "index.html").exists())
            self.assertTrue((archive / "index.html").exists())
            self.assertTrue((root / ".git").exists())
            self.assertEqual(manifest["fileCount"], 2)
            saved = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, manifest)

    def test_refuses_to_overwrite_an_existing_archive(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / ".archive" / "prototype-v1"
            archive.mkdir(parents=True)

            with self.assertRaisesRegex(FileExistsError, "archive already exists"):
                preserve_prototype(root, archive, ("index.html",))

    def test_production_allowlist_does_not_include_repository_metadata(self) -> None:
        self.assertNotIn(".git", LEGACY_PATHS)
        self.assertNotIn("docs", LEGACY_PATHS)
        self.assertNotIn(".superpowers", LEGACY_PATHS)
