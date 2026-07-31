from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]

PUBLIC_FILES = (
    "README.md",
    "README.en.md",
    "LICENSE",
    "CITATION.cff",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "GOVERNANCE.md",
    "SECURITY.md",
    "ERRATA.md",
    "CHANGELOG.md",
    ".gitignore",
)

MIT_LICENSE = """MIT License

Copyright (c) 2026 Engineering Expert Curriculum contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def read(relative: str) -> str:
    path = ROOT / relative
    if not path.is_file():
        raise AssertionError(f"missing {relative}")
    return path.read_text(encoding="utf-8")


class RepositoryContractTests(unittest.TestCase):
    def test_required_public_files_exist_and_are_substantial(self) -> None:
        for relative in PUBLIC_FILES:
            with self.subTest(path=relative):
                path = ROOT / relative
                self.assertTrue(path.is_file(), f"missing {relative}")
                if relative != ".gitignore":
                    self.assertGreater(len(path.read_text(encoding="utf-8").strip()), 120)

    def test_public_documents_contain_no_placeholders_private_paths_or_email(self) -> None:
        for relative in PUBLIC_FILES[:-1]:
            with self.subTest(path=relative):
                text = read(relative)
                self.assertNotRegex(text, re.compile(r"\b(?:TODO|TBD)\b", re.IGNORECASE))
                self.assertNotIn("/Users/", text)
                self.assertNotIn("/Volumes/", text)
                self.assertNotRegex(
                    text,
                    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
                )

    def test_license_is_canonical_mit_text(self) -> None:
        self.assertEqual(read("LICENSE"), MIT_LICENSE)

    def test_japanese_readme_states_the_product_and_learning_contracts(self) -> None:
        readme = read("README.md")
        phrases = (
            "1,140",
            "30のコアレッスン",
            "6つの習熟ゲート",
            "3つのCapstone",
            "CS2023",
            "SWEBOK V4.0a",
            "SFIA 9",
            "site/index.html",
            "file://",
            "HTMLとCSS",
            "JavaScriptを使用しません",
            "Learn → Practice → Explain → Prove → Transfer → Review",
            "ai-assisted",
            "human approval",
            "CONTRIBUTING.md",
            "SECURITY.md",
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)

    def test_english_readme_summarizes_the_public_contract(self) -> None:
        readme = read("README.en.md")
        phrases = (
            "1,140",
            "30 core lessons",
            "six mastery gates",
            "three capstones",
            "CS2023",
            "SWEBOK V4.0a",
            "SFIA 9",
            "file://",
            "HTML and CSS",
            "no JavaScript",
            "Learn → Practice → Explain → Prove → Transfer → Review",
            "AI-assisted",
            "human approval",
            "CONTRIBUTING.md",
            "SECURITY.md",
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)

    def test_citation_metadata_identifies_the_release_and_repository(self) -> None:
        citation = read("CITATION.cff")
        for line in (
            'cff-version: "1.2.0"',
            'version: "0.1.0"',
            "date-released: 2026-07-31",
            "license: MIT",
            'repository-code: "https://github.com/albert-einshutoin/engineering-expert-curriculum"',
        ):
            with self.subTest(line=line):
                self.assertIn(line, citation)

    def test_contributing_defines_github_flow_tdd_and_review_accountability(self) -> None:
        contributing = read("CONTRIBUTING.md")
        phrases = (
            "GitHub Flow",
            "Issue → feature branch → RED → GREEN → REFACTOR",
            "python3 -m unittest discover -s tests -v",
            "技術的正確性",
            "学習設計・証拠",
            "アクセシビリティ",
            "編集・出典",
            "reviewerKind",
            "human",
            "ai-assisted",
            "automated",
            "ローカルとリモートのマージ済みブランチを削除",
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, contributing)

    def test_governance_defines_roles_conflicts_appeals_and_continuity(self) -> None:
        governance = read("GOVERNANCE.md")
        phrases = (
            "Maintainer",
            "Reviewer",
            "Contributor",
            "利益相反",
            "異議申立て",
            "後継",
            "framework update",
            "impact matrix",
            "mapping PR",
            "release note",
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, governance)

    def test_security_uses_only_github_private_vulnerability_reporting(self) -> None:
        security = read("SECURITY.md")
        for phrase in (
            "GitHub Security Advisory",
            "Privately report a vulnerability",
            "公開Issueを作成しないでください",
            "最新リリース",
            "learner dataを保存しません",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, security)
        self.assertNotIn("CODE_OF_CONDUCT.md", security)
        self.assertNotRegex(security, re.compile(r"(?:email|メール)", re.IGNORECASE))

    def test_conduct_policy_does_not_misroute_reports_to_security(self) -> None:
        conduct = read("CODE_OF_CONDUCT.md")
        self.assertIn("GitHub Report Abuse", conduct)
        self.assertIn("機密のプロジェクト行動規範窓口は、現時点では利用できません", conduct)
        self.assertIn("公開Issueへ機密情報を投稿しないでください", conduct)
        self.assertNotIn("Security Advisory", conduct)
        self.assertNotIn("SECURITY.md", conduct)

    def test_errata_defines_severity_and_public_history_schema(self) -> None:
        errata = read("ERRATA.md")
        for phrase in ("Critical", "Substantive", "Editorial", "訂正履歴"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, errata)
        self.assertIn(
            "| 日付 | リリース/commit | 重大度 | 対象 | 旧記述 | 新記述 | 理由 | 検証 |",
            errata,
        )

    def test_changelog_has_unreleased_and_initial_release_sections(self) -> None:
        changelog = read("CHANGELOG.md")
        self.assertIn("## [Unreleased]", changelog)
        self.assertIn("## [0.1.0] - 2026-07-31", changelog)

    def test_gitignore_covers_generated_and_root_local_legacy_paths(self) -> None:
        ignored = set(read(".gitignore").splitlines())
        expected = {
            "__pycache__/",
            ".pytest_cache/",
            ".mypy_cache/",
            ".ruff_cache/",
            ".venv/",
            ".env",
            "*.log",
            "build/",
            "dist/",
            "site/",
            "/.archive/",
            "/.superpowers/",
            "/daily.html",
            "/roadmap.html",
            "/README.txt",
        }
        self.assertTrue(expected <= ignored, f"missing ignores: {sorted(expected - ignored)}")


if __name__ == "__main__":
    unittest.main()
