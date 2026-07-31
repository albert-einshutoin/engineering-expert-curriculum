from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
ISSUE_TEMPLATE_DIR = ROOT / ".github" / "ISSUE_TEMPLATE"
FORM_NAMES = {
    "content-gap.yml",
    "correction.yml",
    "framework-update.yml",
    "code-change.yml",
}
TEMPLATE_NAMES = FORM_NAMES | {"config.yml"}
COMMON_REQUIRED_IDS = {
    "why",
    "implementation",
    "risks",
    "goal",
    "quality",
    "evidence",
}
SPECIALIZED_REQUIRED_IDS = {
    "content-gap.yml": {"audience", "scope", "sources"},
    "correction.yml": {"severity", "affected_content", "sources"},
    "framework-update.yml": {
        "framework",
        "current_version",
        "target_version",
        "sources",
        "migration",
    },
    "code-change.yml": {"affected_area", "migration"},
}


def read(relative: str) -> str:
    path = ROOT / relative
    if not path.is_file():
        raise AssertionError(f"missing {relative}")
    return path.read_text(encoding="utf-8")


def form_fields(text: str) -> list[tuple[str, str]]:
    """Parse the small, deliberately constrained subset used by Issue Forms."""
    fields: list[tuple[str, str]] = []
    blocks = re.split(r"(?=^  - type: (?:input|dropdown|textarea)$)", text, flags=re.MULTILINE)
    for block in blocks:
        type_match = re.match(r"^  - type: (input|dropdown|textarea)\n", block)
        if type_match is None:
            continue
        id_match = re.search(r"^    id: ([a-z][a-z0-9_-]*)$", block, re.MULTILINE)
        if id_match is None:
            raise AssertionError(f"interactive field has no constrained id:\n{block}")
        if re.search(r"^    validations:\n      required: true$", block, re.MULTILINE) is None:
            raise AssertionError(f"field {id_match.group(1)} is not required")
        fields.append((type_match.group(1), id_match.group(1)))
    return fields


class RepositoryTemplateTests(unittest.TestCase):
    def test_issue_template_inventory_is_exact(self) -> None:
        actual = {path.name for path in ISSUE_TEMPLATE_DIR.glob("*.yml")}
        self.assertEqual(actual, TEMPLATE_NAMES)

    def test_blank_issues_are_disabled_and_security_uses_private_advisories(self) -> None:
        config = read(".github/ISSUE_TEMPLATE/config.yml")
        self.assertRegex(config, r"(?m)^blank_issues_enabled: false$")
        self.assertIn("contact_links:", config)
        self.assertIn("SECURITY.md", config)
        self.assertRegex(
            config,
            r"https://github\.com/[a-z0-9_.-]+/[a-z0-9_.-]+/security/advisories/new",
        )

    def test_each_issue_form_has_unique_required_decision_fields(self) -> None:
        for name in sorted(FORM_NAMES):
            with self.subTest(template=name):
                text = read(f".github/ISSUE_TEMPLATE/{name}")
                for key in ("name", "description", "title", "labels"):
                    self.assertRegex(text, rf"(?m)^{key}: .+$")
                self.assertRegex(text, r"(?m)^body:$")

                fields = form_fields(text)
                ids = [field_id for _, field_id in fields]
                self.assertEqual(len(ids), len(set(ids)), f"duplicate field ids in {name}")
                expected = COMMON_REQUIRED_IDS | SPECIALIZED_REQUIRED_IDS[name]
                self.assertTrue(expected <= set(ids), f"{name}: missing {sorted(expected - set(ids))}")

    def test_issue_forms_explain_the_junior_executable_contract(self) -> None:
        labels = {
            "why": "なぜ必要か",
            "implementation": "実装・執筆方法",
            "risks": "注意点・リスク",
            "goal": "GOAL",
            "quality": "守る品質",
            "evidence": "受け入れ条件・検証証拠",
        }
        for name in sorted(FORM_NAMES):
            with self.subTest(template=name):
                text = read(f".github/ISSUE_TEMPLATE/{name}")
                for field_id, label in labels.items():
                    self.assertIn(f"id: {field_id}", text)
                    self.assertIn(f'label: "{label}"', text)

    def test_pr_template_makes_change_and_decision_context_self_contained(self) -> None:
        template = read(".github/pull_request_template.md")
        required_phrases = (
            "なぜ変更するのか",
            "なぜ今なのか",
            "変更前",
            "変更後",
            "意思決定",
            "代替案",
            "実装内容",
            "テスト証拠",
            "セキュリティ",
            "アクセシビリティ",
            "技術的正確性",
            "学習設計・証拠",
            "編集・出典",
            "reviewerKind",
            "リスクとロールバック",
            "OSSとしての価値",
            "Maintainer",
            "マージ後",
            "ローカルとリモート",
            "ブランチ",
        )
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, template)

    def test_templates_contain_no_unresolved_placeholders_or_private_paths(self) -> None:
        relative_paths = [
            *(f".github/ISSUE_TEMPLATE/{name}" for name in sorted(TEMPLATE_NAMES)),
            ".github/pull_request_template.md",
        ]
        prohibited = re.compile(
            r"\b(?:TODO|TBD|FIXME)\b|/Users/|/Volumes/|example\.com|"
            r"<(?:owner|repo|repository|username)>",
            re.IGNORECASE,
        )
        for relative in relative_paths:
            with self.subTest(path=relative):
                text = read(relative)
                self.assertNotRegex(text, prohibited)
                self.assertNotRegex(text, r"(?m)^\s*placeholder:")


if __name__ == "__main__":
    unittest.main()
