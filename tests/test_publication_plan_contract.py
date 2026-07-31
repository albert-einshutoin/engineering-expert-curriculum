from __future__ import annotations

from pathlib import Path
import re
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PUBLICATION_PLAN = (
    REPOSITORY_ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-07-30-oss-publication.md"
)
PUBLIC_PLAN_DOCUMENTS = (
    PUBLICATION_PLAN,
    REPOSITORY_ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-07-30-static-curriculum-foundation.md",
    REPOSITORY_ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-07-30-expert-learning-content.md",
)
WORKFLOWS_ROOT = REPOSITORY_ROOT / ".github" / "workflows"

_ACTION_REFERENCE = re.compile(
    r"uses:\s*(?P<action>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
    r"(?:/[A-Za-z0-9_.-]+)*)@(?P<revision>[0-9a-f]{40})\s*$",
    re.MULTILINE | re.ASCII,
)
_LEDGER_ROW = re.compile(
    r"^\| `(?P<action>[^`]+)` \| `(?P<revision>[0-9a-f]{40})` \|$",
    re.MULTILINE | re.ASCII,
)
_EMAIL = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE | re.ASCII,
)


def _read(path: Path) -> str:
    if not path.is_file():
        raise AssertionError(f"missing {path.relative_to(REPOSITORY_ROOT)}")
    return path.read_text(encoding="utf-8")


class PublicationPlanContractTests(unittest.TestCase):
    def test_public_plans_do_not_disclose_private_paths_or_personal_email(self) -> None:
        for path in PUBLIC_PLAN_DOCUMENTS:
            with self.subTest(path=path.name):
                text = _read(path)
                self.assertNotIn("/Users/", text)
                self.assertNotIn("/Volumes/Satechi", text)
                self.assertIsNone(_EMAIL.search(text))

    def test_publication_action_ledger_exactly_matches_workflows(self) -> None:
        workflow_ledger: dict[str, str] = {}
        for path in sorted(WORKFLOWS_ROOT.glob("*.yml")):
            for match in _ACTION_REFERENCE.finditer(_read(path)):
                action = match.group("action")
                revision = match.group("revision")
                existing = workflow_ledger.setdefault(action, revision)
                self.assertEqual(
                    existing,
                    revision,
                    f"{action} has inconsistent workflow revisions",
                )

        publication_ledger = {
            match.group("action"): match.group("revision")
            for match in _LEDGER_ROW.finditer(_read(PUBLICATION_PLAN))
        }
        self.assertEqual(publication_ledger, workflow_ledger)

    def test_release_automation_is_review_only_and_pages_is_main_push_only(self) -> None:
        workflows = "\n".join(
            _read(path) for path in sorted(WORKFLOWS_ROOT.glob("*.yml"))
        )
        pages = _read(WORKFLOWS_ROOT / "pages.yml")
        publication = _read(PUBLICATION_PLAN)
        self.assertNotIn("pull_request_target", workflows)
        self.assertNotIn("pull_request_target", publication)
        self.assertNotIn("workflow_dispatch", pages)
        self.assertNotIn("workflow_dispatch", publication)
        self.assertRegex(pages, r'on:\n  push:\n    branches: \["main"\]')

    def test_plan_covers_dependency_and_official_gitleaks_review(self) -> None:
        publication = _read(PUBLICATION_PLAN)
        for phrase in (
            ".github/workflows/dependency-review.yml",
            ".github/workflows/gitleaks.yml",
            "actions/dependency-review-action",
            "gitleaks_8.30.1",
            "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb",
            "gitleaks git",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, publication)

    def test_history_is_sanitized_in_an_isolated_two_ref_sibling_clone(self) -> None:
        publication = _read(PUBLICATION_PLAN)
        for phrase in (
            'PUBLICATION_CLONE="${REPO_ROOT}-public"',
            'git clone --no-local --no-checkout --single-branch --branch main "$REPO_ROOT" "$PUBLICATION_CLONE"',
            'git -C "$PUBLICATION_CLONE" fetch --no-tags "$FEATURE_WORKTREE"',
            'refs/heads/feat/static-oss-curriculum:refs/heads/feat/static-oss-curriculum',
            "git filter-repo",
            "--refs refs/heads/main refs/heads/feat/static-oss-curriculum",
            '--replace-text "$REPLACEMENTS_FILE"',
            "commit.author_email",
            "commit.committer_email",
            "PUBLIC_NOREPLY_EMAIL",
            "@users.noreply.github.com",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, publication)

    def test_sanitized_history_is_verified_before_any_public_push(self) -> None:
        publication = _read(PUBLICATION_PLAN)
        required_verification = (
            "git for-each-ref",
            "git log",
            "git grep",
            "gitleaks git",
            "python3.13 -m unittest discover -s tests -v",
        )
        push_command = 'git -C "$PUBLICATION_CLONE" push --set-upstream public'
        self.assertIn(push_command, publication)
        push_index = publication.index(push_command)
        for phrase in required_verification:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, publication)
                self.assertLess(publication.index(phrase), push_index)

    def test_plan_forbids_broad_or_source_checkout_publication(self) -> None:
        publication = _read(PUBLICATION_PLAN)
        forbidden = (
            "git clone --mirror",
            "git push --mirror",
            "git push --all",
            'git -C "$REPO_ROOT" push',
            'git -C "$FEATURE_WORKTREE" push',
            'git -C "$REPO_ROOT" worktree remove',
            'git -C "$REPO_ROOT" branch -d',
            'git -C "$FEATURE_WORKTREE" branch -d',
            "gh pr merge --squash",
        )
        for phrase in forbidden:
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, publication)

        for phrase in (
            "元リポジトリ、元feature branch、元worktree、非公開archiveは削除しない",
            'git -C "$PUBLICATION_CLONE" branch -d feat/static-oss-curriculum',
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, publication)

    def test_public_merge_settings_and_release_are_explicit(self) -> None:
        publication = _read(PUBLICATION_PLAN)
        for phrase in (
            "default_workflow_permissions=read",
            "Require actions to be pinned to a full-length commit SHA",
            "build_type=workflow",
            "github-pages",
            "required_status_checks",
            "full-validation",
            "analysis",
            "review",
            "secret-scan",
            "gh pr merge --merge --delete-branch",
            '"state":"MERGED"',
            "2 parents",
            "git tag -a v0.1.0",
            "gh release create v0.1.0",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, publication)


if __name__ == "__main__":
    unittest.main()
