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
DESIGN_SPEC = (
    REPOSITORY_ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-07-30-static-oss-curriculum-design.md"
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
PRIVATE_VOLUME_NAME = "/" + "Volumes" + "/Satechi"
_BASH_BLOCK = re.compile(r"```bash\n(?P<body>.*?)\n```", re.DOTALL)
_GH_INVOCATION = re.compile(r"(?<![A-Za-z0-9_-])gh\s+(?P<group>[A-Za-z][A-Za-z0-9-]*)\b")


def _read(path: Path) -> str:
    if not path.is_file():
        raise AssertionError(f"missing {path.relative_to(REPOSITORY_ROOT)}")
    return path.read_text(encoding="utf-8")


def _bash_lines(markdown: str) -> list[str]:
    blocks = (match.group("body").replace("\\\n", " ") for match in _BASH_BLOCK.finditer(markdown))
    return [line.strip() for block in blocks for line in block.splitlines() if line.strip()]


def _repo_values(invocation: str) -> list[str]:
    values = re.findall(
        r"--repo(?:=|\s+)(?P<value>\"[^\"]*\"|'[^']*'|[^\s)#]+)",
        invocation,
    )
    return [value.strip("\"'") for value in values]


def assert_gh_invocations_are_scoped(test: unittest.TestCase, markdown: str) -> None:
    """Fail closed unless each shell-visible gh invocation has an exact scope."""
    seen = 0
    for line in _bash_lines(markdown):
        matches = list(_GH_INVOCATION.finditer(line))
        for index, match in enumerate(matches):
            seen += 1
            end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
            invocation = line[match.start():end]
            group = match.group("group")
            if group == "api":
                if re.match(r"gh\s+api\s+user\b", invocation):
                    test.assertNotIn("--repo", invocation, line)
                elif re.match(r"gh\s+api\s+graphql\b", invocation):
                    test.assertEqual(
                        invocation.count('owner="${PUBLIC_REPOSITORY_SLUG%%/*}"'),
                        1,
                        line,
                    )
                    test.assertEqual(
                        invocation.count('name="${PUBLIC_REPOSITORY_SLUG#*/}"'),
                        1,
                        line,
                    )
                else:
                    endpoints = re.findall(
                        r"(?:\"|')?(repos/[^\s\"')]+)",
                        invocation,
                    )
                    test.assertEqual(len(endpoints), 1, line)
                    test.assertTrue(
                        endpoints[0].startswith("repos/$PUBLIC_REPOSITORY_SLUG"),
                        line,
                    )
            elif group in {"label", "pr", "release", "run"}:
                test.assertEqual(
                    _repo_values(invocation),
                    ["$PUBLIC_REPOSITORY_SLUG"],
                    line,
                )
            else:
                test.fail(f"unclassified gh command group {group!r}: {line}")
    test.assertGreater(seen, 0)


class PublicationPlanContractTests(unittest.TestCase):
    def test_public_plans_do_not_disclose_private_paths_or_personal_email(self) -> None:
        for path in PUBLIC_PLAN_DOCUMENTS:
            with self.subTest(path=path.name):
                text = _read(path)
                self.assertNotIn("/Users/", text)
                self.assertNotIn(PRIVATE_VOLUME_NAME, text)
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
        for match in _ACTION_REFERENCE.finditer(_read(PUBLICATION_PLAN)):
            action = match.group("action")
            with self.subTest(action=action):
                self.assertEqual(
                    match.group("revision"),
                    workflow_ledger[action],
                    f"{action} example drifted from the workflow ledger",
                )

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
            'regex:/(?:Volumes)/[A-Za-z0-9._ -]+/==>$VOLUME_ROOT/',
            'regex:/(?:Users)/[A-Za-z0-9._-]+/==>$USER_HOME/',
            "(?!example\\.(?:com|invalid)\\b)",
            "==>$PRIVATE_EMAIL",
            "commit.author_email",
            "commit.committer_email",
            "PUBLIC_NOREPLY_EMAIL",
            "@users.noreply.github.com",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, publication)

    def test_public_identity_and_noreply_address_are_derived_and_exact(self) -> None:
        publication = _read(PUBLICATION_PLAN)
        for phrase in (
            "PUBLIC_ACCOUNT_ID",
            'PUBLIC_REPOSITORY_SLUG="${PUBLIC_OWNER}/engineering-expert-curriculum"',
            'EXPECTED_NOREPLY_EMAIL="${PUBLIC_ACCOUNT_ID}+${PUBLIC_OWNER}@users.noreply.github.com"',
            'test "$PUBLIC_NOREPLY_EMAIL" = "$EXPECTED_NOREPLY_EMAIL"',
            'test "$REPOSITORY_NAME_WITH_OWNER" = "$PUBLIC_REPOSITORY_SLUG"',
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, publication)

    def test_every_repository_scoped_gh_command_uses_the_verified_slug(self) -> None:
        assert_gh_invocations_are_scoped(self, _read(PUBLICATION_PLAN))

    def test_gh_scope_validation_rejects_wrapped_or_misdirected_commands(self) -> None:
        wrapped_valid = """```bash
RESULT="$(gh api "repos/$PUBLIC_REPOSITORY_SLUG" --jq '.id')"
gh pr view "$PUBLIC_PR_URL" --repo "$PUBLIC_REPOSITORY_SLUG"
```
"""
        assert_gh_invocations_are_scoped(self, wrapped_valid)

        wrong_repo = """```bash
RESULT="$(gh api "repos/wrong/project" --jq '.id')" # repos/$PUBLIC_REPOSITORY_SLUG
gh pr view "$PUBLIC_PR_URL" --repo "wrong/project" # --repo "$PUBLIC_REPOSITORY_SLUG"
```
"""
        with self.assertRaises(AssertionError):
            assert_gh_invocations_are_scoped(self, wrong_repo)

    def test_private_reporting_and_labels_are_verified_before_first_push(self) -> None:
        publication = _read(PUBLICATION_PLAN)
        push = publication.index(
            'git -C "$PUBLICATION_CLONE" push --set-upstream public'
        )
        for phrase in (
            'gh api --method PUT "repos/$PUBLIC_REPOSITORY_SLUG/private-vulnerability-reporting"',
            "PRIVATE_REPORTING_STATUS",
            "204 No Content",
            'gh label create code --repo "$PUBLIC_REPOSITORY_SLUG"',
            'gh label create content --repo "$PUBLIC_REPOSITORY_SLUG"',
            'gh label create correction --repo "$PUBLIC_REPOSITORY_SLUG"',
            'gh label create framework-update --repo "$PUBLIC_REPOSITORY_SLUG"',
            'gh label list --repo "$PUBLIC_REPOSITORY_SLUG"',
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, publication)
                self.assertLess(publication.index(phrase), push)

    def test_review_evidence_uses_the_actual_implementation_date(self) -> None:
        publication = _read(PUBLICATION_PLAN)
        evidence = "docs/reviews/2026-07-31-release-readiness.md"
        self.assertIn(f"Create: `{evidence}`", publication)
        self.assertIn(f"git add {evidence}", publication)
        self.assertNotIn("2026-07-30-release-readiness.md", publication)

    def test_sanitized_history_is_verified_before_any_public_push(self) -> None:
        publication = _read(PUBLICATION_PLAN)
        verification = publication.split(
            "**Step 4: Verify rewritten refs, identity, paths, secrets, and tests**",
            maxsplit=1,
        )[1].split("**Step 5: Push exactly the reviewed public refs**", maxsplit=1)[0]
        required_verification = (
            "for-each-ref",
            " log \\",
            "git grep --quiet",
            "PRIVATE_PATH_PATTERN='/(Users)/[[:alnum:]_.-]+/|/(Volumes)/[[:alnum:]_. -]+/'",
            "SAFE_FIXTURE_EMAIL_DOMAINS = {\"example.com\", \"example.invalid\"}",
            "unexpected email-like text found in rewritten history",
            '"$GITLEAKS_DIR/gitleaks" git',
            "b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5",
            "python3.13 -m unittest discover -s tests -v",
        )
        push_command = 'git -C "$PUBLICATION_CLONE" push --set-upstream public'
        self.assertIn(push_command, publication)
        push_index = publication.index(push_command)
        for phrase in required_verification:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, verification)
        normalized_verification = verification.replace("\\\n", " ")
        self.assertRegex(
            normalized_verification,
            re.compile(
                r'(?m)^[ \t]*"\$GITLEAKS_DIR/gitleaks" git\b'
                r'(?=[^\n]*--log-opts="refs/heads/main '
                r'refs/heads/feat/static-oss-curriculum")'
                r'(?=[^\n]*"\$PUBLICATION_CLONE"(?:\s|$))[^\n]*$',
            ),
        )
        self.assertLess(publication.index(verification), push_index)
        self.assertIn("set -euo pipefail", verification)
        self.assertNotIn("|| true", publication)
        self.assertNotIn(
            '"$(git -C "$PUBLICATION_CLONE" rev-list',
            verification,
        )

    def test_push_requires_a_sha_bound_successful_preflight_token(self) -> None:
        publication = _read(PUBLICATION_PLAN)
        verification = publication.split(
            "**Step 4: Verify rewritten refs, identity, paths, secrets, and tests**",
            maxsplit=1,
        )[1].split("**Step 5: Push exactly the reviewed public refs**", maxsplit=1)[0]
        push = publication.split(
            "**Step 5: Push exactly the reviewed public refs**",
            maxsplit=1,
        )[1].split("**Step 6: Open a context-complete pull request**", maxsplit=1)[0]
        for phrase in (
            "PUBLICATION_PREFLIGHT_TOKEN",
            "PREFLIGHT_PAYLOAD",
            "refs/heads/main",
            "refs/heads/feat/static-oss-curriculum",
            'repository.slug=$PUBLIC_REPOSITORY_SLUG',
            'repository.url=$PUBLIC_REPOSITORY',
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, verification)
                self.assertIn(phrase, push)
        self.assertIn('test "$(cat "$PUBLICATION_PREFLIGHT_TOKEN")" = "$PREFLIGHT_PAYLOAD"', push)
        normalized_push = re.sub(r"\s+", " ", push.replace("\\\n", " "))
        remote_add = normalized_push.index(
            'git -C "$PUBLICATION_CLONE" remote add public "$PUBLIC_REPOSITORY"'
        )
        remote_verify = normalized_push.index(
            'test "$(git -C "$PUBLICATION_CLONE" remote get-url public)" = '
            '"$PUBLIC_REPOSITORY"'
        )
        token_verify = normalized_push.index(
            'test "$(cat "$PUBLICATION_PREFLIGHT_TOKEN")" = "$PREFLIGHT_PAYLOAD"'
        )
        actual_push = normalized_push.index(
            'git -C "$PUBLICATION_CLONE" push --set-upstream public'
        )
        self.assertLess(remote_add, remote_verify)
        self.assertLess(remote_verify, token_verify)
        self.assertLess(token_verify, actual_push)

    def test_repository_settings_are_applied_and_read_back_before_merge(self) -> None:
        publication = _read(PUBLICATION_PLAN)
        settings = publication.split(
            "**Step 2: Configure repository metadata and protection**",
            maxsplit=1,
        )[1].split("**Step 3: Merge only the verified PR**", maxsplit=1)[0]
        settings = re.sub(r"\s+", " ", settings.replace("\\\n", " "))
        for phrase in (
            'gh api --method PUT "repos/$PUBLIC_REPOSITORY_SLUG/actions/permissions"',
            "sha_pinning_required=true",
            'gh api "repos/$PUBLIC_REPOSITORY_SLUG/actions/permissions"',
            'gh api --method PUT "repos/$PUBLIC_REPOSITORY_SLUG/actions/permissions/workflow"',
            "default_workflow_permissions=read",
            "can_approve_pull_request_reviews=false",
            'gh api "repos/$PUBLIC_REPOSITORY_SLUG/actions/permissions/workflow"',
            'gh api --method POST "repos/$PUBLIC_REPOSITORY_SLUG/pages"',
            "build_type=workflow",
            'gh api "repos/$PUBLIC_REPOSITORY_SLUG/pages"',
            'gh api --method PUT "repos/$PUBLIC_REPOSITORY_SLUG/environments/github-pages"',
            "custom_branch_policies",
            'environments/github-pages/deployment-branch-policies',
            '"1:main"',
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, settings)

    def test_both_merges_are_bound_to_the_reviewed_head_commit(self) -> None:
        publication = _read(PUBLICATION_PLAN).replace("\\\n", " ")
        initial_merge = publication.split(
            "**Step 3: Merge only the verified PR**",
            maxsplit=1,
        )[1].split("**Step 4: Verify Pages deployment and public site**", maxsplit=1)[0]
        release_merge = publication.split(
            "The release metadata PR now has its own Model B commit",
            maxsplit=1,
        )[1].split("**Step 6: Clean only the merged public feature branch**", maxsplit=1)[0]
        for section, prefix, pr_url, merge_prefix in (
            (initial_merge, "PR", "$PUBLIC_PR_URL", "PUBLIC"),
            (release_merge, "RELEASE", "$RELEASE_PR_URL", "RELEASE"),
        ):
            section = re.sub(r"\s+", " ", section)
            reviewed = f"${{{prefix}_HEAD_SHA}}"
            current = f"CURRENT_{prefix}_HEAD_SHA"
            merge_sha = f"${{{merge_prefix}_MERGE_SHA}}"
            with self.subTest(prefix=prefix):
                self.assertIn(f'{current}="$(gh pr view "{pr_url}"', section)
                self.assertIn(f'test "${current}" = "{reviewed}"', section)
                self.assertIn(f'--match-head-commit "{reviewed}"', section)
                self.assertIn(
                    f'test "$(git -C "$PUBLICATION_CLONE" rev-parse "{merge_sha}^2")" = "{reviewed}"',
                    section,
                )

    def test_workflow_and_https_evidence_are_bound_to_each_merge_sha(self) -> None:
        publication = _read(PUBLICATION_PLAN)
        pages = publication.split(
            "**Step 4: Verify Pages deployment and public site**",
            maxsplit=1,
        )[1].split(
            "**Step 5: Materialize release metadata through a PR, then publish**",
            maxsplit=1,
        )[0]
        pages = re.sub(r"\s+", " ", pages.replace("\\\n", " "))
        for phrase in (
            '--commit "$PUBLIC_MERGE_SHA"',
            'gh run view "$PAGES_RUN_ID" --repo "$PUBLIC_REPOSITORY_SLUG"',
            '"$PUBLIC_MERGE_SHA:completed:success"',
            "PUBLIC_HTTPS_EVIDENCE_SOURCE",
            "public HTTPS smoke: PASS",
            "tested commit: $PUBLIC_MERGE_SHA",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, pages)

        release = publication.split(
            "**Step 5: Materialize release metadata through a PR, then publish**",
            maxsplit=1,
        )[1].split("**Step 6: Clean only the merged public feature branch**", maxsplit=1)[0]
        for phrase in (
            'docs/reviews/2026-07-31-release-readiness.md',
            '"Validate" "CodeQL" "Gitleaks" "Deploy GitHub Pages"',
            '--commit "$expected_sha"',
            'test "$run_state" = "$expected_sha:completed:success"',
            'verify_workflow_run_for_sha "$workflow_name" "$RELEASE_MERGE_SHA"',
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, release)
        evidence = publication.index("PUBLIC_HTTPS_EVIDENCE_SOURCE")
        metadata_branch = publication.index("switch -c release/v0.1.0-metadata")
        tag = publication.index("tag -a v0.1.0")
        self.assertLess(evidence, metadata_branch)
        self.assertLess(metadata_branch, tag)

    def test_release_commit_and_annotated_tag_use_verified_public_identity(self) -> None:
        publication = _read(PUBLICATION_PLAN).replace("\\\n", " ")
        release = publication.split(
            "**Step 5: Materialize release metadata through a PR, then publish**",
            maxsplit=1,
        )[1].split("**Step 6: Clean only the merged public feature branch**", maxsplit=1)[0]
        for command in ("commit", "tag -a v0.1.0"):
            with self.subTest(command=command):
                self.assertRegex(
                    release,
                    re.compile(
                        r'git -C "\$PUBLICATION_CLONE"\s+'
                        r'-c user\.name="\$PUBLIC_AUTHOR_NAME"\s+'
                        r'-c user\.email="\$PUBLIC_NOREPLY_EMAIL"\s+'
                        + re.escape(command)
                    ),
                )
        for phrase in (
            "RELEASE_METADATA_SHA",
            "%(authorname)",
            "%(authoremail)",
            "%(committername)",
            "%(committeremail)",
            "%(taggername)",
            "%(taggeremail)",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, release)
        self.assertLess(release.index("%(taggeremail)"), release.index("push public refs/tags/v0.1.0"))

    def test_current_site_checker_cli_is_used_everywhere(self) -> None:
        publication = _read(PUBLICATION_PLAN)
        self.assertNotRegex(publication, re.compile(r"tools/check_site\.py site(?:\s|$)"))
        self.assertIn(
            "tools/check_site.py --root site --require-current-release",
            publication,
        )

    def test_link_audit_is_described_as_optional_and_not_implemented(self) -> None:
        design = _read(DESIGN_SPEC)
        self.assertIn("optional planned scheduled link audit", design)
        self.assertIn("not implemented in v0.1.0", design)
        self.assertNotIn("checked by scheduled link audits", design)

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
            "required_approving_review_count=0",
            "required_review_thread_resolution=true",
            "Model B",
            "authenticated Maintainer",
            "reviewerKind",
            "gh pr merge --merge --delete-branch",
            '"state":"MERGED"',
            "2 parents",
            'tag -a v0.1.0',
            "gh release create v0.1.0",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, publication)

    def test_release_metadata_is_materialized_by_a_second_reviewed_pr(self) -> None:
        publication = _read(PUBLICATION_PLAN)
        for phrase in (
            "release metadata branch",
            "date-released",
            "[0.1.0] - ${RELEASE_DATE}",
            "release metadata PR",
            "gh pr create",
            "gh pr merge --merge --delete-branch",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, publication)
        metadata_pr = publication.find("release metadata PR")
        tag = publication.find('tag -a v0.1.0')
        self.assertGreaterEqual(metadata_pr, 0)
        self.assertGreaterEqual(tag, 0)
        self.assertLess(metadata_pr, tag)


if __name__ == "__main__":
    unittest.main()
