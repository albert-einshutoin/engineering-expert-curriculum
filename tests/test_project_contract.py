from __future__ import annotations

import importlib
from pathlib import Path
import tomllib
import unittest


class ProjectContractTests(unittest.TestCase):
    def test_package_exposes_version(self) -> None:
        package = importlib.import_module("curriculum_builder")
        self.assertEqual(package.__version__, "0.2.0")

    def test_project_metadata_matches_package_contract(self) -> None:
        package = importlib.import_module("curriculum_builder")
        pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
        with pyproject_path.open("rb") as pyproject_file:
            project = tomllib.load(pyproject_file)["project"]

        self.assertEqual(project["version"], package.__version__)
        self.assertEqual(project["license"], "MIT")


if __name__ == "__main__":
    unittest.main()
