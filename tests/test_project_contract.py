from __future__ import annotations

import importlib
import unittest


class ProjectContractTests(unittest.TestCase):
    def test_package_exposes_version(self) -> None:
        package = importlib.import_module("curriculum_builder")
        self.assertEqual(package.__version__, "0.1.0")


if __name__ == "__main__":
    unittest.main()
