# OSS Publication and GitHub Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the verified curriculum as a contributor-ready public GitHub repository with least-privilege CI, security and accessibility gates, GitHub Pages, transparent governance, and a clean GitHub Flow lifecycle.

**Architecture:** Pull requests run a dependency-free validation workflow that builds the complete static artifact and fails closed. Merges to `main` run the same gate before a separate least-privilege Pages deployment job; OSS documentation and templates make content decisions, corrections, security reports, and contributor expectations reviewable without private context.

**Tech Stack:** GitHub, GitHub Actions pinned to immutable SHAs, Python 3.13 standard library, GitHub Pages, Markdown, HTML5/CSS3

---

## Current workflow ledger

This ledger is copied from the checked-in workflows, not from mutable release
tags. `tests/test_publication_plan_contract.py` fails whenever this table and
the complete set of `uses:` references drift in either direction.

| Action | Immutable revision |
|---|---|
| `actions/checkout` | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `actions/dependency-review-action` | `a1d282b36b6f3519aa1f3fc636f609c47dddb294` |
| `actions/deploy-pages` | `cd2ce8fcbc39b97be8ca5fce6e763baed58fa128` |
| `actions/setup-python` | `5fda3b95a4ea91299a34e894583c3862153e4b97` |
| `actions/upload-pages-artifact` | `fc324d3547104276b827a68afc52ff2a11cc49c9` |
| `github/codeql-action/analyze` | `f205ea1c3313d32999d8d6a48b4f6530d4437b38` |
| `github/codeql-action/init` | `f205ea1c3313d32999d8d6a48b4f6530d4437b38` |

## File map

| Path | Responsibility |
|---|---|
| `README.md` | Japanese-first product and learner entry point |
| `README.en.md` | English OSS overview and contribution entry point |
| `LICENSE` | MIT license |
| `CONTRIBUTING.md` | GitHub Flow, TDD, content review, and contributor journey |
| `CODE_OF_CONDUCT.md` | Community conduct and enforcement route |
| `GOVERNANCE.md` | Roles, decisions, framework updates, and succession |
| `SECURITY.md` | Supported version and private vulnerability reporting |
| `ERRATA.md` | Correction severity, workflow, and visible history |
| `CHANGELOG.md` | Release-level changes |
| `CITATION.cff` | Machine-readable citation metadata |
| `.github/ISSUE_TEMPLATE/*.yml` | Junior-executable content, correction, and code issues |
| `.github/pull_request_template.md` | Motivation, before/after, evidence, risk, and OSS value |
| `.github/workflows/validate.yml` | Pull-request and branch validation |
| `.github/workflows/pages.yml` | Verified artifact deployment |
| `.github/workflows/codeql.yml` | Python build-tool static analysis |
| `.github/workflows/dependency-review.yml` | Pull-request dependency policy |
| `.github/workflows/gitleaks.yml` | Official Gitleaks CLI full-history scan |
| `.github/dependabot.yml` | Monthly GitHub Actions revision review |
| `tests/test_repository_contract.py` | Required OSS files and metadata |
| `tests/test_repository_security.py` | Secret patterns, workflow permissions, and static artifact contract |
| `tests/test_publication_plan_contract.py` | Privacy-safe, two-ref publication runbook contract |
| `tests/test_accessibility_contract.py` | Generated semantic and WCAG-oriented contracts |
| `tools/check_site.py` | Link, markup, static-file, and deterministic artifact validation |

### Task 1: Add the public project identity and MIT license

**Files:**
- Create: `LICENSE`
- Create: `README.md`
- Create: `README.en.md`
- Create: `CITATION.cff`
- Create: `tests/test_repository_contract.py`

- [ ] **Step 1: Write the repository identity test**

```python
# tests/test_repository_contract.py
from __future__ import annotations

from pathlib import Path
import unittest


class RepositoryContractTests(unittest.TestCase):
    def test_required_public_files_exist_and_are_not_placeholders(self) -> None:
        required = (
            "README.md", "README.en.md", "LICENSE", "CITATION.cff",
            "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "GOVERNANCE.md",
            "SECURITY.md", "ERRATA.md", "CHANGELOG.md",
        )
        for relative in required:
            with self.subTest(path=relative):
                path = Path(relative)
                self.assertTrue(path.is_file())
                text = path.read_text(encoding="utf-8")
                self.assertGreater(len(text.strip()), 120)
                self.assertNotIn("T" + "BD", text)
                self.assertNotIn("TO" + "DO", text)

    def test_readme_states_the_static_and_learning_contracts(self) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")
        for phrase in (
            "1,140", "30", "HTML", "CSS", "JavaScriptを使用しません",
            "Learn → Practice → Explain → Prove → Transfer → Review",
        ):
            self.assertIn(phrase, readme)
```

- [ ] **Step 2: Run the identity test and verify RED**

Run:

```bash
python3 -m unittest tests.test_repository_contract -v
```

Expected: failures for missing public files.

- [ ] **Step 3: Add the MIT license and bilingual entry points**

Use the unmodified MIT permission and warranty text with:

```text
Copyright (c) 2026 Engineering Expert Curriculum contributors
```

`README.md` must contain:

```markdown
# Engineering Expert Curriculum

1,140項目の知識地図と30の教科書品質レッスンを使い、世界で通用する
エンジニアリング判断を「成果物」で身につける静的OSS教材です。

Learn → Practice → Explain → Prove → Transfer → Review

## 特徴
- `site/index.html`を直接開けるHTML＋CSSサイト
- JavaScriptを使用しません
- 30レッスン、6習熟ゲート、3 Capstones
- CS2023、SWEBOK V4.0a、SFIA 9との対応
- TDDで検証される教材品質、リンク、前提グラフ、アクセシビリティ

## ローカルで読む
python3 tools/build.py
open site/index.html

## 検証
python3 -m unittest discover -s tests -v

## Contributing
日本語: CONTRIBUTING.md
English overview: README.en.md
```

Expand both READMEs with the learner route, repository structure, build support,
content status meaning, capstone evidence, contribution links, security route,
license, and acknowledgement that framework names belong to their respective
owners.

Before the public release exists, `CITATION.cff` identifies the upcoming
version `0.1.0` without `date-released`; `CHANGELOG.md` keeps the initial
release notes under `Unreleased`. The release metadata PR in Task 10 adds the
actual release date immediately before the tag is created. Citation metadata
also uses the MIT license, repository title, and
`authors: [{name: "Engineering Expert Curriculum contributors"}]`.

- [ ] **Step 4: Run the focused identity assertions**

Run:

```bash
python3 -m unittest \
  tests.test_repository_contract.RepositoryContractTests.test_readme_states_the_static_and_learning_contracts \
  -v
```

Expected: the README contract passes; the all-files test remains RED until the
governance documents are added in Task 2.

- [ ] **Step 5: Commit the public identity**

```bash
git add LICENSE README.md README.en.md CITATION.cff tests/test_repository_contract.py
git commit -m "docs: establish MIT licensed public project identity"
```

### Task 2: Define contribution, conduct, governance, security, and Errata

**Files:**
- Create: `CONTRIBUTING.md`
- Create: `CODE_OF_CONDUCT.md`
- Create: `GOVERNANCE.md`
- Create: `SECURITY.md`
- Create: `ERRATA.md`
- Create: `CHANGELOG.md`
- Modify: `tests/test_repository_contract.py`

- [ ] **Step 1: Add documentation-content assertions**

```python
def test_operating_docs_define_required_decisions(self) -> None:
    expectations = {
        "CONTRIBUTING.md": (
            "GitHub Flow", "RED", "GREEN", "REFACTOR", "content review",
            "accessibility", "security",
        ),
        "GOVERNANCE.md": (
            "Maintainer", "Reviewer", "Contributor", "framework version",
            "decision record", "succession",
        ),
        "SECURITY.md": (
            "private vulnerability report", "supported version",
            "Do not open a public issue",
        ),
        "ERRATA.md": (
            "critical", "substantive", "editorial", "correction history",
        ),
        "CHANGELOG.md": ("Unreleased", "1,140"),
    }
    for relative, phrases in expectations.items():
        text = Path(relative).read_text(encoding="utf-8")
        for phrase in phrases:
            self.assertIn(phrase, text, f"{relative}: missing {phrase}")
```

- [ ] **Step 2: Run the operating-doc tests and verify RED**

Run:

```bash
python3 -m unittest tests.test_repository_contract -v
```

Expected: missing-file failures.

- [ ] **Step 3: Write the operating documents with explicit policies**

`CONTRIBUTING.md` defines:

```text
Issue → feature branch → failing test → minimal change → full validation
→ self-review → PR → required review/CI → merge commit → public branch deletion
```

It also defines four review roles for a complete lesson:

1. Technical accuracy reviewer
2. Pedagogy and evidence reviewer
3. Accessibility reviewer
4. Editorial and source reviewer

`GOVERNANCE.md` makes maintainers accountable for safety and release decisions,
uses truthful Model B governance while only one authenticated Maintainer is
available, makes reviewers accountable only for the dimension they actually
review, and never represents AI-assisted or automated review as independent
human approval. Contributors become eligible to be reviewers through three
accepted contributions plus a documented review. Framework upgrades require
an issue, impact matrix, mapping PR, and release note.

`SECURITY.md` supports only the latest `main`/release, directs reporters to the
GitHub Security tab's private advisory flow, prohibits public vulnerability
issues, sets acknowledgement and status-update expectations without promising
an unsafe fixed deadline, and explains that the site stores no learner data.

`ERRATA.md` defines:

- Critical: unsafe or materially wrong guidance; label immediately and publish
  a visible correction.
- Substantive: changes learning outcome, assessment, mapping, or lab result;
  require technical and pedagogical review.
- Editorial: wording, typography, or dead link without meaning change; require
  one reviewer.

`CODE_OF_CONDUCT.md` adopts Contributor Covenant 2.1 by reference, truthfully
states that no confidential project conduct channel exists yet, and identifies
GitHub Report Abuse as a platform route rather than project enforcement.
Before release, `CHANGELOG.md` keeps the initial notes under `Unreleased`.

- [ ] **Step 4: Run all repository-contract tests**

Run:

```bash
python3 -m unittest tests.test_repository_contract -v
```

Expected: all repository-contract tests pass.

- [ ] **Step 5: Commit the OSS operating model**

```bash
git add CONTRIBUTING.md CODE_OF_CONDUCT.md GOVERNANCE.md SECURITY.md \
  ERRATA.md CHANGELOG.md tests/test_repository_contract.py
git commit -m "docs: define transparent OSS stewardship"
```

### Task 3: Add junior-executable issue templates and a self-contained PR template

**Files:**
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/ISSUE_TEMPLATE/content-gap.yml`
- Create: `.github/ISSUE_TEMPLATE/correction.yml`
- Create: `.github/ISSUE_TEMPLATE/code-change.yml`
- Create: `.github/pull_request_template.md`
- Modify: `tests/test_repository_contract.py`

- [ ] **Step 1: Write template-contract tests**

```python
def test_issue_and_pr_templates_preserve_decision_context(self) -> None:
    issue_phrases = (
        "なぜ必要か", "実装・執筆方法", "注意点", "GOAL",
        "守る品質", "受け入れ条件", "検証方法",
    )
    for path in Path(".github/ISSUE_TEMPLATE").glob("*.yml"):
        if path.name == "config.yml":
            continue
        text = path.read_text(encoding="utf-8")
        for phrase in issue_phrases:
            self.assertIn(phrase, text, f"{path}: missing {phrase}")
    pr = Path(".github/pull_request_template.md").read_text(encoding="utf-8")
    for phrase in (
        "なぜ変更するのか", "変更前", "変更後", "意思決定",
        "テスト証拠", "セキュリティ", "アクセシビリティ", "OSSとしての価値",
    ):
        self.assertIn(phrase, pr)
```

- [ ] **Step 2: Run the template test and verify RED**

Run:

```bash
python3 -m unittest \
  tests.test_repository_contract.RepositoryContractTests.test_issue_and_pr_templates_preserve_decision_context \
  -v
```

Expected: failure because templates do not exist.

- [ ] **Step 3: Create structured issue forms**

Each issue form contains required textarea fields with these IDs:

```yaml
- id: why
  attributes: {label: "なぜ必要か"}
  validations: {required: true}
- id: implementation
  attributes: {label: "実装・執筆方法"}
  validations: {required: true}
- id: cautions
  attributes: {label: "注意点"}
  validations: {required: true}
- id: goal
  attributes: {label: "GOAL"}
  validations: {required: true}
- id: quality
  attributes: {label: "守る品質"}
  validations: {required: true}
- id: acceptance
  attributes: {label: "受け入れ条件"}
  validations: {required: true}
- id: verification
  attributes: {label: "検証方法"}
  validations: {required: true}
```

Specialize descriptions and labels for content gaps, corrections, and build
changes. Disable blank issues in `config.yml`; link security reports to the
repository Security tab.

The PR template requires motivation, before/after, alternatives, exact changed
surfaces, test commands and outputs, content/source review, security,
accessibility, compatibility, OSS value, screenshots for visual changes, and a
branch-cleanup checkbox.

- [ ] **Step 4: Run template and YAML-shape checks**

Run:

```bash
python3 -m unittest tests.test_repository_contract -v
python3 -c "from pathlib import Path; assert len(list(Path('.github/ISSUE_TEMPLATE').glob('*.yml'))) == 4"
```

Expected: tests pass and exactly four YAML template files exist.

- [ ] **Step 5: Commit contributor workflows**

```bash
git add .github/ISSUE_TEMPLATE .github/pull_request_template.md \
  tests/test_repository_contract.py
git commit -m "docs: make issues and pull requests decision complete"
```

### Task 4: Validate all generated HTML, links, assets, and static file types

**Files:**
- Create: `tools/check_site.py`
- Create: `tests/test_site_checker.py`
- Create: `tests/test_accessibility_contract.py`

- [ ] **Step 1: Write site-checker and accessibility tests**

```python
# tests/test_site_checker.py
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.check_site import check_site


class SiteCheckerTests(unittest.TestCase):
    def test_reports_missing_relative_link_and_script(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text(
                '<main><a href="missing.html">x</a><script src="app.js"></script></main>',
                encoding="utf-8",
            )
            issues = check_site(root)
            self.assertIn("index.html: missing local target missing.html", issues)
            self.assertIn("index.html: script is forbidden", issues)
```

```python
# tests/test_accessibility_contract.py
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from curriculum_builder.build import build_site
from tools.check_site import check_site


class AccessibilityContractTests(unittest.TestCase):
    def test_every_generated_page_has_required_semantics(self) -> None:
        with TemporaryDirectory() as directory:
            site = Path(directory) / "site"
            build_site(Path("content"), Path("templates"), Path("static"), site)
            issues = check_site(site)
            semantic = [
                issue for issue in issues
                if any(term in issue for term in ("lang", "title", "main", "skip", "heading"))
            ]
            self.assertEqual(semantic, [])
```

- [ ] **Step 2: Run checker tests and verify RED**

Run:

```bash
python3 -m unittest tests.test_site_checker tests.test_accessibility_contract -v
```

Expected: import failure because `tools.check_site` does not exist.

- [ ] **Step 3: Implement a standard-library site checker**

```python
# tools/check_site.py
from __future__ import annotations

import argparse
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

ALLOWED_SUFFIXES = {".html", ".css"}


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.has_main = False
        self.has_title = False
        self.has_skip = False
        self.lang = ""
        self.scripts = 0
        self.headings: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "html":
            self.lang = values.get("lang", "") or ""
        elif tag == "main":
            self.has_main = True
        elif tag == "title":
            self.has_title = True
        elif tag == "script":
            self.scripts += 1
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.headings.append(int(tag[1]))
        elif tag == "a":
            href = values.get("href", "") or ""
            self.links.append(href)
            if href == "#main" and "skip-link" in (values.get("class", "") or ""):
                self.has_skip = True
        elif tag in {"link", "img"}:
            target = values.get("href") or values.get("src")
            if target:
                self.links.append(target)


def check_site(root: Path) -> list[str]:
    issues: list[str] = []
    for file_path in sorted(path for path in root.rglob("*") if path.is_file()):
        relative = file_path.relative_to(root).as_posix()
        if file_path.suffix not in ALLOWED_SUFFIXES:
            issues.append(f"{relative}: disallowed static file type")
            continue
        if file_path.suffix != ".html":
            continue
        parser = PageParser()
        parser.feed(file_path.read_text(encoding="utf-8"))
        if parser.lang != "ja":
            issues.append(f"{relative}: html lang must be ja")
        if not parser.has_title:
            issues.append(f"{relative}: missing title")
        if not parser.has_main:
            issues.append(f"{relative}: missing main")
        if not parser.has_skip:
            issues.append(f"{relative}: missing skip link")
        if parser.scripts:
            issues.append(f"{relative}: script is forbidden")
        if parser.headings.count(1) != 1:
            issues.append(f"{relative}: page must contain exactly one h1 heading")
        for previous, current in zip(parser.headings, parser.headings[1:]):
            if current > previous + 1:
                issues.append(
                    f"{relative}: heading level jumps from h{previous} to h{current}"
                )
        for raw_link in parser.links:
            parsed = urlparse(raw_link)
            if parsed.scheme:
                if parsed.scheme != "https":
                    issues.append(f"{relative}: external link must use https: {raw_link}")
                continue
            if raw_link.startswith("#"):
                continue
            target = (file_path.parent / unquote(parsed.path)).resolve()
            if not target.exists():
                issues.append(f"{relative}: missing local target {raw_link}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    issues = check_site(args.root.resolve())
    for issue in issues:
        print(issue)
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Build and validate the entire site**

Run:

```bash
python3 -m unittest tests.test_site_checker tests.test_accessibility_contract -v
python3 tools/build.py
python3 tools/check_site.py --root site --require-current-release
```

Expected: tests pass and checker exits zero with no output.

- [ ] **Step 5: Commit the static-site release gate**

```bash
git add tools/check_site.py tests/test_site_checker.py tests/test_accessibility_contract.py
git commit -m "test: fail closed on unsafe static site output"
```

### Task 5: Add repository security and secret-regression checks

**Files:**
- Create: `tests/test_repository_security.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write security regression tests**

```python
# tests/test_repository_security.py
from __future__ import annotations

from pathlib import Path
import re
import unittest


class RepositorySecurityTests(unittest.TestCase):
    def test_tracked_text_contains_no_common_secret_material(self) -> None:
        patterns = {
            "private key": re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
            "GitHub token": re.compile(r"(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}"),
            "OpenAI key": re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
        }
        roots = (
            Path("content"), Path("curriculum_builder"), Path("templates"),
            Path("static"), Path("tools"), Path("tests"), Path(".github"),
        )
        files = [
            path for root in roots if root.exists()
            for path in root.rglob("*") if path.is_file()
        ]
        for path in files:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for label, pattern in patterns.items():
                self.assertIsNone(pattern.search(text), f"{path}: possible {label}")

    def test_local_and_generated_directories_are_ignored(self) -> None:
        ignored = Path(".gitignore").read_text(encoding="utf-8")
        for entry in (".archive/", ".superpowers/", "site/", ".venv/", "__pycache__/"):
            self.assertIn(entry, ignored)
```

- [ ] **Step 2: Run the security tests**

Run:

```bash
python3 -m unittest tests.test_repository_security -v
```

Expected: tests pass; if a fixture triggers its own detector, replace the
literal test token with concatenated non-secret fragments so the scanner tests
behavior without storing a token-shaped string.

- [ ] **Step 3: Add remaining local artifacts to `.gitignore`**

```gitignore
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.log
coverage.xml
dist/
build/
```

- [ ] **Step 4: Run all security and static-output checks**

Run:

```bash
python3 -m unittest tests.test_repository_security tests.test_html_safety -v
python3 tools/build.py
python3 tools/check_site.py --root site --require-current-release
git status --ignored --short | sed -n '1,80p'
```

Expected: checks pass; local archive, brainstorming, and generated site appear
only as ignored entries.

- [ ] **Step 5: Commit repository security contracts**

```bash
git add .gitignore tests/test_repository_security.py
git commit -m "test: guard public repository against secret leakage"
```

### Task 6: Add least-privilege validation, CodeQL, dependency review, and secret scanning

**Files:**
- Create: `.github/workflows/validate.yml`
- Create: `.github/workflows/codeql.yml`
- Create: `.github/workflows/dependency-review.yml`
- Create: `.github/workflows/gitleaks.yml`
- Create: `.github/dependabot.yml`
- Modify: `tests/test_repository_security.py`

- [ ] **Step 1: Add workflow-permission assertions**

```python
def test_pull_request_workflows_are_read_only_and_sha_pinned(self) -> None:
    for relative in (
        ".github/workflows/validate.yml",
        ".github/workflows/codeql.yml",
        ".github/workflows/dependency-review.yml",
        ".github/workflows/gitleaks.yml",
    ):
        text = Path(relative).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", text)
        for uses_line in (
            line.strip() for line in text.splitlines() if line.strip().startswith("- uses:")
        ):
            revision = uses_line.rsplit("@", 1)[-1].split()[0]
            self.assertRegex(revision, r"^[0-9a-f]{40}$")
```

- [ ] **Step 2: Run the workflow test and verify RED**

Run:

```bash
python3 -m unittest \
  tests.test_repository_security.RepositorySecurityTests.test_pull_request_workflows_are_read_only_and_sha_pinned \
  -v
```

Expected: failure because workflows do not exist.

- [ ] **Step 3: Add the fail-closed validation workflow**

```yaml
# .github/workflows/validate.yml
name: Validate

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: validate-${{ github.ref }}
  cancel-in-progress: true

jobs:
  full-validation:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          persist-credentials: false
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
        with:
          python-version: "3.13"
      - name: Compile build tools
        run: python -m compileall -q curriculum_builder tools tests
      - name: Run complete test suite
        run: python -m unittest discover -s tests -v
      - name: Build static site
        run: python tools/build.py
      - name: Validate static artifact
        run: python tools/check_site.py --root site --require-current-release
      - name: Verify reproducible output
        run: |
          find site -type f -exec sha256sum {} + | sort > /tmp/build-1.sha256
          python tools/build.py
          find site -type f -exec sha256sum {} + | sort > /tmp/build-2.sha256
          diff -u /tmp/build-1.sha256 /tmp/build-2.sha256
```

Add `codeql.yml` with `contents: read`, `security-events: write` only at the job
that uploads results, Python language analysis, and the pinned checkout and
CodeQL revisions from the current workflow ledger. Add
`dependency-review.yml` using
`actions/dependency-review-action@a1d282b36b6f3519aa1f3fc636f609c47dddb294`
on `pull_request` only. Add `.github/dependabot.yml` with monthly
`github-actions` checks targeting `main`, a limit of five open PRs, and
`labels: ["dependencies", "github-actions"]`.

Add `.github/workflows/gitleaks.yml` on `pull_request` and pushes to `main`.
It checks out complete history without retained credentials, downloads the
official `gitleaks_8.30.1_linux_x64.tar.gz`, verifies SHA-256
`551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`,
then runs the verified `gitleaks git` binary with redaction and a nonzero exit
on findings. Do not replace this CLI verification with a floating third-party
Action.

- [ ] **Step 4: Run workflow contracts and inspect YAML**

Run:

```bash
python3.13 -m unittest tests.test_repository_security -v
sed -n '1,220p' .github/workflows/validate.yml
sed -n '1,220p' .github/workflows/codeql.yml
sed -n '1,160p' .github/workflows/dependency-review.yml
sed -n '1,180p' .github/workflows/gitleaks.yml
```

Expected: tests pass; no action uses a floating tag.

- [ ] **Step 5: Commit CI and analysis**

```bash
git add .github/workflows/validate.yml .github/workflows/codeql.yml \
  .github/workflows/dependency-review.yml .github/workflows/gitleaks.yml \
  .github/dependabot.yml tests/test_repository_security.py
git commit -m "ci: validate curriculum with least privilege"
```

### Task 7: Add verified GitHub Pages deployment

**Files:**
- Create: `.github/workflows/pages.yml`
- Modify: `tests/test_repository_security.py`

- [ ] **Step 1: Write Pages permission and provenance tests**

```python
def test_pages_workflow_builds_before_upload_and_limits_write_permissions(self) -> None:
    text = Path(".github/workflows/pages.yml").read_text(encoding="utf-8")
    self.assertIn("python -m unittest discover -s tests -v", text)
    self.assertIn("python tools/check_site.py --root site --require-current-release", text)
    self.assertLess(text.index("python tools/check_site.py --root site --require-current-release"), text.index("upload-pages-artifact"))
    self.assertIn("pages: write", text)
    self.assertIn("id-token: write", text)
    self.assertIn("environment:\n      name: github-pages", text)
```

- [ ] **Step 2: Run the Pages test and verify RED**

Run:

```bash
python3 -m unittest \
  tests.test_repository_security.RepositorySecurityTests.test_pages_workflow_builds_before_upload_and_limits_write_permissions \
  -v
```

Expected: failure because `pages.yml` does not exist.

- [ ] **Step 3: Add build-before-deploy workflow**

```yaml
# .github/workflows/pages.yml
name: Deploy GitHub Pages

on:
  push:
    branches: ["main"]

permissions:
  contents: read

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          persist-credentials: false
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
        with:
          python-version: "3.13"
      - run: python -m unittest discover -s tests -v
      - run: python tools/generate_curriculum_map.py --check
      - run: python tools/build.py
      - run: python tools/check_site.py --root site --require-current-release
      - uses: actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9
        with:
          path: site

  deploy:
    needs: build
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    permissions:
      pages: write
      id-token: write
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - name: Deploy verified artifact
        id: deployment
        uses: actions/deploy-pages@cd2ce8fcbc39b97be8ca5fce6e763baed58fa128
```

- [ ] **Step 4: Run all workflow permission tests**

Run:

```bash
python3.13 -m unittest tests.test_repository_security -v
```

Expected: all tests pass; Pages write permissions appear only in the deployment
job.

- [ ] **Step 5: Commit Pages deployment**

```bash
git add .github/workflows/pages.yml tests/test_repository_security.py
git commit -m "ci: deploy only verified static Pages artifact"
```

### Task 8: Perform local release validation and visual/accessibility review

**Files:**
- Create: `docs/reviews/2026-07-31-release-readiness.md`

- [ ] **Step 1: Run the complete clean build**

Run:

```bash
python3 -m compileall -q curriculum_builder tools tests
python3 -m unittest discover -s tests -v
python3 tools/build.py
python3 tools/check_site.py --root site --require-current-release
```

Expected: every command exits zero.

- [ ] **Step 2: Verify file-only behavior**

Run:

```bash
open "file://$(pwd)/site/index.html"
```

Review these exact journeys with network disabled:

1. Home → Roadmap → lesson 1 → Catalog
2. Home → lesson 30 → prerequisite lesson
3. Home → competency matrix → mapped lesson
4. Home → each of three capstones

Expected: all links and CSS work without a server or JavaScript.

- [ ] **Step 3: Perform accessibility and responsive review**

Review at 320 CSS px, 1280 CSS px, 200% zoom, keyboard-only navigation, macOS
VoiceOver headings/landmarks/links, high-contrast preference, and print preview.
Record each route, observed result, and any correction in the release-readiness
document. A visual connector line may disappear; textual prerequisite meaning
must remain.

- [ ] **Step 4: Perform security and OSS self-review**

Run:

```bash
git diff main...HEAD --check
if git grep --quiet -E 'BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|ghp_|github_pat_|sk-(proj-)?' \
  -- . ':(exclude)docs/superpowers/plans/*'; then
  echo "potential secret marker found; stop publication" >&2
  exit 1
else
  grep_status=$?
  test "$grep_status" -eq 1
fi
git log --oneline --decorate main..HEAD
```

Review correctness, test adequacy, content-source quality, link safety,
accessibility, security boundaries, maintainability, contributor journey, and
whether every commit is independently understandable.

- [ ] **Step 5: Commit review evidence and fixes**

```bash
git add docs/reviews/2026-07-31-release-readiness.md static templates tests
git commit -m "docs: record static curriculum release evidence"
```

If no tracked fixes are needed outside the review document, commit only the
review document.

### Task 9: Create the public GitHub repository and open the GitHub Flow PR

**Files:**
- External state: public repository `engineering-expert-curriculum`
- External state: pull request from `feat/static-oss-curriculum` to `main`

- [ ] **Step 1: Verify GitHub identity and repository-name availability**

Run:

```bash
set -euo pipefail
PUBLIC_OWNER="$(gh api user --jq '.login')"
PUBLIC_ACCOUNT_ID="$(gh api user --jq '.id | tostring')"
test -n "$PUBLIC_OWNER"
test -n "$PUBLIC_ACCOUNT_ID"
PUBLIC_REPOSITORY_SLUG="${PUBLIC_OWNER}/engineering-expert-curriculum"
test "$PUBLIC_REPOSITORY_SLUG" = "${PUBLIC_OWNER}/engineering-expert-curriculum"
if REPOSITORY_PROBE="$(gh api --include "repos/$PUBLIC_REPOSITORY_SLUG" 2>&1)"; then
  echo "repository already exists; inspect it instead of overwriting" >&2
  exit 1
else
  probe_status=$?
  test "$probe_status" -eq 1
  printf '%s\n' "$REPOSITORY_PROBE" | grep -Eq '^HTTP/[0-9.]+ 404 Not Found$'
fi
```

Expected: authenticated login is returned; no existing repository is found. If
the repository exists, stop and inspect ownership and contents instead of
overwriting it.

- [ ] **Step 2: Create the empty public repository**

Use the connected GitHub repository-creation operation with:

```text
name: engineering-expert-curriculum
visibility: public
description: Static OSS textbook for learning, practicing, and proving world-class engineering judgment
initialize: false
```

Expected: one empty public repository owned by the authenticated account.
Immediately verify its exact identity, enable the only private security-report
route, and provision the labels referenced by the issue forms. All commands
are scoped to the previously verified slug; failure of any command stops before
the first content push.

```bash
set -euo pipefail
REPOSITORY_NAME_WITH_OWNER="$(gh api "repos/$PUBLIC_REPOSITORY_SLUG" --jq '.full_name')"
REPOSITORY_VISIBILITY="$(gh api "repos/$PUBLIC_REPOSITORY_SLUG" --jq '.visibility')"
REPOSITORY_SIZE="$(gh api "repos/$PUBLIC_REPOSITORY_SLUG" --jq '.size')"
test "$REPOSITORY_NAME_WITH_OWNER" = "$PUBLIC_REPOSITORY_SLUG"
test "$REPOSITORY_VISIBILITY" = "public"
test "$REPOSITORY_SIZE" = "0"
# The verified response binds nameWithOwner to "$PUBLIC_REPOSITORY_SLUG".
gh api --method PUT "repos/$PUBLIC_REPOSITORY_SLUG/private-vulnerability-reporting"
PRIVATE_REPORTING_STATUS="$(gh api --include \
  "repos/$PUBLIC_REPOSITORY_SLUG/private-vulnerability-reporting")"
printf '%s\n' "$PRIVATE_REPORTING_STATUS" | \
  grep -Eq '^HTTP/[0-9.]+ 204 No Content$'

gh label create code --repo "$PUBLIC_REPOSITORY_SLUG" --color 1d76db \
  --description "Changes to build, validation, or repository code" --force
gh label create content --repo "$PUBLIC_REPOSITORY_SLUG" --color 0e8a16 \
  --description "Curriculum content additions or improvements" --force
gh label create correction --repo "$PUBLIC_REPOSITORY_SLUG" --color d73a4a \
  --description "Verified corrections and errata" --force
gh label create framework-update --repo "$PUBLIC_REPOSITORY_SLUG" --color 5319e7 \
  --description "Versioned CS2023, SWEBOK, or SFIA updates" --force
PUBLIC_LABELS="$(gh label list --repo "$PUBLIC_REPOSITORY_SLUG" \
  --limit 100 --json name --jq 'map(.name) | sort | .[]')"
for required_label in code content correction framework-update; do
  printf '%s\n' "$PUBLIC_LABELS" | grep -Fqx "$required_label"
done
```

Expected: the exact repository is empty and public, private vulnerability
reporting returns success, and all four template labels exist. Do not continue
if the security route cannot be verified.

- [ ] **Step 3: Build a sanitized two-ref publication clone**

Never add the public remote to `$REPO_ROOT` or `$FEATURE_WORKTREE`. Resolve both
trusted source checkouts and create one fresh sibling clone. A mirror clone,
broad ref publication, or push from either source checkout is outside this
runbook.

```bash
REPO_ROOT="${REPO_ROOT:?set REPO_ROOT to the original main checkout}"
FEATURE_WORKTREE="${FEATURE_WORKTREE:?set FEATURE_WORKTREE to the reviewed feature checkout}"
PUBLICATION_CLONE="${REPO_ROOT}-public"
PUBLIC_OWNER="${PUBLIC_OWNER:?set PUBLIC_OWNER to the login verified in Step 1}"
PUBLIC_ACCOUNT_ID="${PUBLIC_ACCOUNT_ID:?set PUBLIC_ACCOUNT_ID to the id verified in Step 1}"
PUBLIC_REPOSITORY_SLUG="${PUBLIC_REPOSITORY_SLUG:?set the exact slug verified in Step 2}"
PUBLIC_REPOSITORY="https://github.com/${PUBLIC_REPOSITORY_SLUG}.git"
test "$FEATURE_WORKTREE" != "$REPO_ROOT"
test ! -e "$PUBLICATION_CLONE"
git clone --no-local --no-checkout --single-branch --branch main "$REPO_ROOT" "$PUBLICATION_CLONE"
git -C "$PUBLICATION_CLONE" fetch --no-tags "$FEATURE_WORKTREE" \
  "refs/heads/feat/static-oss-curriculum:refs/heads/feat/static-oss-curriculum"
test "$(git -C "$PUBLICATION_CLONE" rev-parse refs/heads/main)" = \
  "$(git -C "$REPO_ROOT" rev-parse refs/heads/main)"
test "$(git -C "$PUBLICATION_CLONE" rev-parse refs/heads/feat/static-oss-curriculum)" = \
  "$(git -C "$FEATURE_WORKTREE" rev-parse HEAD)"
git -C "$PUBLICATION_CLONE" remote remove origin
```

The clone imports only `main` through the single-branch clone and the one
explicit feature ref through the exact refspec above. Confirm `main` resolves
to the source `main` SHA and the feature ref resolves to the reviewed
`$FEATURE_WORKTREE` HEAD before rewriting history.

Prepare a private replace-text file whose specific rules run before its generic
rules:

```text
regex:/(?:Volumes)/[^/]+/Developer/engineering-expert-curriculum-worktrees/static-oss-curriculum==>$FEATURE_WORKTREE
regex:/(?:Volumes)/[^/]+/Developer/engineering-expert-curriculum==>$REPO_ROOT
regex:/(?:Volumes)/[^/]+/==>$VOLUME_ROOT/
regex:/(?:Users)/[^/]+/\.pyenv/versions/[0-9.]+/bin/python3\.13==>python3.13
regex:/(?:Users)/[^/]+/==>$USER_HOME/
```

Set `REPLACEMENTS_FILE` to that mode-`0600` file. Obtain the verified public
account's GitHub noreply address from GitHub settings, export it as
`PUBLIC_NOREPLY_EMAIL`, and require it to match the documented
`<account-id>+<login>@users.noreply.github.com` form. Do not guess the account
ID or login. Then rewrite exactly the two public refs:

```bash
export PUBLIC_AUTHOR_NAME="Engineering Expert Curriculum contributors"
EXPECTED_NOREPLY_EMAIL="${PUBLIC_ACCOUNT_ID}+${PUBLIC_OWNER}@users.noreply.github.com"
PUBLIC_NOREPLY_EMAIL="${PUBLIC_NOREPLY_EMAIL:?copy the verified GitHub noreply address}"
test "$PUBLIC_NOREPLY_EMAIL" = "$EXPECTED_NOREPLY_EMAIL"
git -C "$PUBLICATION_CLONE" filter-repo --force \
  --refs refs/heads/main refs/heads/feat/static-oss-curriculum \
  --replace-text "$REPLACEMENTS_FILE" \
  --replace-message "$REPLACEMENTS_FILE" \
  --commit-callback '
import os
public_name = os.environ["PUBLIC_AUTHOR_NAME"].encode()
public_email = os.environ["PUBLIC_NOREPLY_EMAIL"].encode()
commit.author_name = public_name
commit.author_email = public_email
commit.committer_name = public_name
commit.committer_email = public_email
'
```

`git filter-repo` changes both author and committer identity to the verified
noreply identity and replaces historical private path text. The source
repository and feature worktree are read-only inputs and remain unchanged.

- [ ] **Step 4: Verify rewritten refs, identity, paths, secrets, and tests**

Perform every gate in the isolated clone before creating or pushing to the
public repository:

```bash
set -euo pipefail
git -C "$PUBLICATION_CLONE" for-each-ref --format='%(refname)' \
  refs/heads refs/tags refs/remotes
test "$(git -C "$PUBLICATION_CLONE" for-each-ref --format='%(refname)' \
  refs/heads refs/tags refs/remotes)" = \
  "$(printf '%s\n' refs/heads/feat/static-oss-curriculum refs/heads/main)"
git -C "$PUBLICATION_CLONE" log \
  refs/heads/main refs/heads/feat/static-oss-curriculum \
  --format='%H%x09%an%x09%ae%x09%cn%x09%ce'
test "$(git -C "$PUBLICATION_CLONE" log \
  refs/heads/main refs/heads/feat/static-oss-curriculum \
  --format='%ae%n%ce' | LC_ALL=C sort -u)" = "$PUBLIC_NOREPLY_EMAIL"
PRIVATE_TEXT_PATTERN='/(Users)/|/(Volumes)/|[[:alnum:]._%+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,}'
if git -C "$PUBLICATION_CLONE" log \
  refs/heads/main refs/heads/feat/static-oss-curriculum --format='%B' | \
  grep -Eq "$PRIVATE_TEXT_PATTERN"; then
  echo "private text found in rewritten commit messages" >&2
  exit 1
else
  grep_status=$?
  test "$grep_status" -eq 1
fi
while IFS= read -r commit_sha; do
  if (cd "$PUBLICATION_CLONE" && git grep --quiet -I -E \
    "$PRIVATE_TEXT_PATTERN" "$commit_sha" --); then
    echo "private text found in rewritten history" >&2
    exit 1
  else
    git_grep_status=$?
    test "$git_grep_status" -eq 1
  fi
done < <(git -C "$PUBLICATION_CLONE" rev-list \
  refs/heads/main refs/heads/feat/static-oss-curriculum)

GITLEAKS_DIR="$(mktemp -d /tmp/gitleaks-publication.XXXXXX)"
GITLEAKS_ARCHIVE="$GITLEAKS_DIR/gitleaks_8.30.1_darwin_arm64.tar.gz"
chmod 700 "$GITLEAKS_DIR"
curl --fail --location --proto '=https' --tlsv1.2 --output "$GITLEAKS_ARCHIVE" \
  https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_darwin_arm64.tar.gz
printf '%s  %s\n' \
  b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5 \
  "$GITLEAKS_ARCHIVE" | shasum -a 256 -c -
tar --extract --gzip --file "$GITLEAKS_ARCHIVE" --directory "$GITLEAKS_DIR" gitleaks
"$GITLEAKS_DIR/gitleaks" git --redact --no-banner --exit-code 1 \
  --log-opts="refs/heads/main refs/heads/feat/static-oss-curriculum" \
  "$PUBLICATION_CLONE"
git -C "$PUBLICATION_CLONE" switch feat/static-oss-curriculum
(cd "$PUBLICATION_CLONE" && python3.13 -m unittest discover -s tests -v)
(cd "$PUBLICATION_CLONE" && python3.13 tools/generate_curriculum_map.py --check)
(cd "$PUBLICATION_CLONE" && python3.13 tools/build.py)
(cd "$PUBLICATION_CLONE" && python3.13 tools/check_site.py --root site --require-current-release)
PREFLIGHT_MAIN_SHA="$(git -C "$PUBLICATION_CLONE" rev-parse refs/heads/main)"
PREFLIGHT_FEATURE_SHA="$(git -C "$PUBLICATION_CLONE" rev-parse \
  refs/heads/feat/static-oss-curriculum)"
PREFLIGHT_PAYLOAD="$(printf '%s\n%s' \
  "refs/heads/main=$PREFLIGHT_MAIN_SHA" \
  "refs/heads/feat/static-oss-curriculum=$PREFLIGHT_FEATURE_SHA")"
PUBLICATION_PREFLIGHT_TOKEN="$PUBLICATION_CLONE/.git/publication-preflight-token"
umask 077
printf '%s' "$PREFLIGHT_PAYLOAD" > "$PUBLICATION_PREFLIGHT_TOKEN"
```

Expected: local heads are exactly `main` and `feat/static-oss-curriculum`, with
no tags; every author and committer uses the one verified noreply identity;
private paths and other email addresses are absent from every reachable blob;
the official Gitleaks CLI and all tests/build checks pass. If any gate fails,
discard only the publication clone, correct the source feature through TDD,
and restart from a fresh sibling clone.

- [ ] **Step 5: Push exactly the reviewed public refs**

Only after the repository-name check, rewrite verification, and public
repository creation succeed, add the public remote inside the isolated clone:

```bash
set -euo pipefail
PREFLIGHT_MAIN_SHA="$(git -C "$PUBLICATION_CLONE" rev-parse refs/heads/main)"
PREFLIGHT_FEATURE_SHA="$(git -C "$PUBLICATION_CLONE" rev-parse \
  refs/heads/feat/static-oss-curriculum)"
PREFLIGHT_PAYLOAD="$(printf '%s\n%s' \
  "refs/heads/main=$PREFLIGHT_MAIN_SHA" \
  "refs/heads/feat/static-oss-curriculum=$PREFLIGHT_FEATURE_SHA")"
PUBLICATION_PREFLIGHT_TOKEN="$PUBLICATION_CLONE/.git/publication-preflight-token"
test -f "$PUBLICATION_PREFLIGHT_TOKEN"
test "$(cat "$PUBLICATION_PREFLIGHT_TOKEN")" = "$PREFLIGHT_PAYLOAD"
PRIVATE_REPORTING_STATUS="$(gh api --include \
  "repos/$PUBLIC_REPOSITORY_SLUG/private-vulnerability-reporting")"
printf '%s\n' "$PRIVATE_REPORTING_STATUS" | \
  grep -Eq '^HTTP/[0-9.]+ 204 No Content$'
git -C "$PUBLICATION_CLONE" remote add public "$PUBLIC_REPOSITORY"
git -C "$PUBLICATION_CLONE" push --set-upstream public \
  refs/heads/main:refs/heads/main \
  refs/heads/feat/static-oss-curriculum:refs/heads/feat/static-oss-curriculum
```

Expected: only `main` and the reviewed feature ref exist publicly; `main`
remains the default release branch. Never broaden the refspec.

- [ ] **Step 6: Open a context-complete pull request**

Create a PR whose body contains:

```markdown
## なぜ変更するのか
既存の1,140生成ページは学習項目を網羅していましたが、前提、一次資料、
実践ラボ、評価証拠、更新責任が薄く、エキスパート成長を判定できませんでした。

## 変更前
- 1,140の類似生成ページ
- JavaScript依存の進捗UI
- CI、OSS運営、コンピテンシー対応なし

## 変更後
- 1,140項目を保つ静的カタログ
- 30の証拠ベース教材、6習熟ゲート、3 Capstones
- HTML＋CSSのみ、file://対応
- CS2023、SWEBOK V4.0a、SFIA 9対応
- TDD、セキュリティ、アクセシビリティ、OSS運営、Pages

## 意思決定
Python標準ライブラリによる決定的ビルドを採用し、外部依存と実行時JSを除外しました。
元プロトタイプはSHA-256検証済みローカルアーカイブへ保存しています。

## テスト証拠
完全な実行コマンド、件数、再現ビルド、file://、キーボード、VoiceOver、
ズーム、印刷、セキュリティ確認の結果を記載します。

## OSSとしての価値
第三者が教材の誤りを訂正し、新しいレッスンを品質契約付きで提案し、
CIで同じ基準を再現できます。
```

Save that body as `/tmp/engineering-curriculum-pr.md`, then run:

```bash
PUBLIC_PR_URL="$(gh pr create --repo "$PUBLIC_REPOSITORY_SLUG" --base main \
  --head "${PUBLIC_OWNER}:feat/static-oss-curriculum" \
  --title "feat: publish the static expert curriculum" \
  --body-file /tmp/engineering-curriculum-pr.md)"
test -n "$PUBLIC_PR_URL"
```

Expected: one open PR targeting `main`.

- [ ] **Step 7: Confirm remote state**

Run:

```bash
gh pr view "$PUBLIC_PR_URL" --repo "$PUBLIC_REPOSITORY_SLUG" \
  --json number,url,state,baseRefName,headRefName,isDraft,mergeable
gh pr checks "$PUBLIC_PR_URL" --repo "$PUBLIC_REPOSITORY_SLUG" --watch
```

Expected: PR is open, not draft, targets `main`, and every check is successful.

### Task 10: Harden settings, merge with history, publish, and clean the public feature

**Files:**
- External state: PR review and merge
- External state: repository settings, Pages, environment, ruleset, topics, release
- Local state: isolated publication clone only

- [ ] **Step 1: Perform final PR self-review against remote diff**

Run:

```bash
gh pr diff "$PUBLIC_PR_URL" --repo "$PUBLIC_REPOSITORY_SLUG" --color=never \
  > /tmp/engineering-curriculum-pr.diff
gh pr view "$PUBLIC_PR_URL" --repo "$PUBLIC_REPOSITORY_SLUG" \
  --json files,commits,reviews,reviewDecision,mergeable,statusCheckRollup
```

Review the remote diff for content accuracy, test adequacy, source and framework
versioning, unsafe HTML, secret leakage, broken relative paths, CI permissions,
accessibility, documentation consistency, and OSS value. Fix findings on the
source feature branch with a failing regression test first, rebuild a fresh
sanitized publication clone, repush the same two explicit refs, and wait for
checks.

For Model B, verify the reviewed commit and unresolved threads from the exact
repository, then publish a truthful authenticated Maintainer decision. Do not
select `human` unless a human actually performed that review.

```bash
PR_NUMBER="$(gh pr view "$PUBLIC_PR_URL" --repo "$PUBLIC_REPOSITORY_SLUG" \
  --json number --jq '.number')"
PR_HEAD_SHA="$(gh pr view "$PUBLIC_PR_URL" --repo "$PUBLIC_REPOSITORY_SLUG" \
  --json headRefOid --jq '.headRefOid')"
test -n "$PR_NUMBER"
test -n "$PR_HEAD_SHA"
THREAD_STATE="$(gh api graphql \
  -F owner="${PUBLIC_REPOSITORY_SLUG%%/*}" \
  -F name="${PUBLIC_REPOSITORY_SLUG#*/}" -F number="$PR_NUMBER" \
  -f query='query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){pullRequest(number:$number){reviewThreads(first:100){nodes{isResolved}pageInfo{hasNextPage}}}}}' \
  --jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)] | length | tostring + ":" + (.data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage | tostring)')"
test "$THREAD_STATE" = "0:false"
REVIEWER_KIND="${REVIEWER_KIND:?set human, ai-assisted, or automated truthfully}"
case "$REVIEWER_KIND" in human|ai-assisted|automated) ;; *) exit 1 ;; esac
MAINTAINER_DECISION_FILE="${MAINTAINER_DECISION_FILE:?write the Model B decision record}"
test -s "$MAINTAINER_DECISION_FILE"
grep -Fqx "commit: $PR_HEAD_SHA" "$MAINTAINER_DECISION_FILE"
grep -Fqx "reviewerKind: $REVIEWER_KIND" "$MAINTAINER_DECISION_FILE"
grep -Fqx "independent human approval: none" "$MAINTAINER_DECISION_FILE"
grep -Fqx "unresolved threads: 0" "$MAINTAINER_DECISION_FILE"
for dimension in "technical accuracy" "learning design and evidence" \
  accessibility "editorial and source quality"; do
  grep -Fqx "review dimension: $dimension" "$MAINTAINER_DECISION_FILE"
done
grep -Eq '^residual risk: .+' "$MAINTAINER_DECISION_FILE"
gh pr comment "$PUBLIC_PR_URL" --repo "$PUBLIC_REPOSITORY_SLUG" \
  --body-file "$MAINTAINER_DECISION_FILE"
```

- [ ] **Step 2: Configure repository metadata and protection**

Set description, homepage after Pages deployment, and topics:

```text
computer-science, curriculum, engineering, learning, oss, static-site,
software-engineering, textbook
```

Before merging, configure and verify all of these settings:

- Actions default workflow permissions are read-only
  (`default_workflow_permissions=read`) and Actions cannot approve pull
  requests. Enable **Require actions to be pinned to a full-length commit SHA**.
- Pages uses GitHub Actions (`build_type=workflow`), not a branch directory.
- The `github-pages` environment permits deployments from `main` only and has
  no unreviewed custom branch policy.
- A `main` repository ruleset blocks force pushes and deletions, requires a
  pull request, and sets `required_status_checks` to the actual contexts:
  `full-validation`, `analysis`, `review`, and `secret-scan`. Confirm the names
  from the successful PR check rollup before saving the ruleset.
- The pull-request rule uses Model B parameters
  `required_approving_review_count=0` and
  `required_review_thread_resolution=true`. Zero is deliberate: a one-person
  repository cannot manufacture independent human approval. The authenticated
  Maintainer instead records the exact commit, four review dimensions,
  `reviewerKind`, absence of independent human approval, residual risk, and
  unresolved-thread count before merge. When a second qualified reviewer is
  available, governance can migrate to Model A and raise the approval count.
- Merge commits are enabled; squash and rebase merges are disabled so the
  public setting matches `CONTRIBUTING.md` and this runbook.
- Private vulnerability reporting remains enabled, automatic deletion of
  merged public feature branches is enabled, and Actions from forks retain
  read-only tokens.

Use the repository settings/API response as evidence. A successful workflow
alone does not prove these controls are configured.

Save the following exact payload as `/tmp/engineering-curriculum-main-ruleset.json`:

```json
{
  "name": "main-protection",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": {
    "ref_name": {"exclude": [], "include": ["~DEFAULT_BRANCH"]}
  },
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {
      "type": "pull_request",
      "parameters": {
        "allowed_merge_methods": ["merge"],
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_approving_review_count": 0,
        "required_review_thread_resolution": true
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "do_not_enforce_on_create": false,
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          {"context": "full-validation"},
          {"context": "analysis"},
          {"context": "review"},
          {"context": "secret-scan"}
        ]
      }
    }
  ]
}
```

Create and read back that exact ruleset, then configure and verify the merge
and branch-cleanup settings:

```bash
RULESET_ID="$(gh api --method POST \
  "repos/$PUBLIC_REPOSITORY_SLUG/rulesets" \
  --input /tmp/engineering-curriculum-main-ruleset.json --jq '.id')"
test -n "$RULESET_ID"
test "$(gh api "repos/$PUBLIC_REPOSITORY_SLUG/rulesets/$RULESET_ID" \
  --jq '[.rules[].type] | contains(["deletion","non_fast_forward","pull_request","required_status_checks"])')" = true
test "$(gh api "repos/$PUBLIC_REPOSITORY_SLUG/rulesets/$RULESET_ID" \
  --jq '[.rules[] | select(.type == "pull_request") | .parameters.required_approving_review_count] | unique | .[]')" = 0
test "$(gh api "repos/$PUBLIC_REPOSITORY_SLUG/rulesets/$RULESET_ID" \
  --jq '[.rules[] | select(.type == "pull_request") | .parameters.required_review_thread_resolution] | unique | .[]')" = true
test "$(gh api "repos/$PUBLIC_REPOSITORY_SLUG/rulesets/$RULESET_ID" \
  --jq '[.rules[] | select(.type == "required_status_checks") | .parameters.required_status_checks[].context] | sort | join(",")')" = \
  "analysis,full-validation,review,secret-scan"
gh api --method PATCH "repos/$PUBLIC_REPOSITORY_SLUG" \
  -F allow_merge_commit=true -F allow_squash_merge=false \
  -F allow_rebase_merge=false -F delete_branch_on_merge=true
PRIVATE_REPORTING_STATUS="$(gh api --include \
  "repos/$PUBLIC_REPOSITORY_SLUG/private-vulnerability-reporting")"
printf '%s\n' "$PRIVATE_REPORTING_STATUS" | \
  grep -Eq '^HTTP/[0-9.]+ 204 No Content$'
gh api "repos/$PUBLIC_REPOSITORY_SLUG" \
  --jq '{allow_merge_commit,allow_squash_merge,allow_rebase_merge,delete_branch_on_merge}'
```

Record the verified ruleset JSON and authenticated Maintainer decision in the
PR. Do not infer protection from a successful workflow alone.

- [ ] **Step 3: Merge only the verified PR**

Run:

```bash
gh pr merge --merge --delete-branch --repo "$PUBLIC_REPOSITORY_SLUG" \
  "$PUBLIC_PR_URL"
gh pr view "$PUBLIC_PR_URL" --repo "$PUBLIC_REPOSITORY_SLUG" \
  --json state,mergedAt,mergeCommit,url
PUBLIC_MERGE_SHA="$(gh pr view "$PUBLIC_PR_URL" \
  --repo "$PUBLIC_REPOSITORY_SLUG" --json mergeCommit --jq '.mergeCommit.oid')"
test -n "$PUBLIC_MERGE_SHA"
git -C "$PUBLICATION_CLONE" fetch public main
test "$(git -C "$PUBLICATION_CLONE" rev-parse refs/remotes/public/main)" = \
  "$PUBLIC_MERGE_SHA"
test "$(git -C "$PUBLICATION_CLONE" rev-list --parents -n 1 \
  "$PUBLIC_MERGE_SHA" | awk '{print NF}')" -eq 3
```

Expected: the JSON contains `"state":"MERGED"`, `mergedAt` and `mergeCommit`
are non-null, and the public remote feature branch is absent. Fetch public
`main` into `$PUBLICATION_CLONE` and verify the merge commit has exactly
`2 parents`; this preserves the reviewed feature history instead of collapsing
it into a squash commit.

- [ ] **Step 4: Verify Pages deployment and public site**

Run:

```bash
gh run list --repo "$PUBLIC_REPOSITORY_SLUG" --branch main --limit 10
PAGES_RUN_ID="$(gh run list --repo "$PUBLIC_REPOSITORY_SLUG" \
  --workflow 'Deploy GitHub Pages' --branch main --limit 1 \
  --json databaseId --jq '.[0].databaseId')"
test -n "$PAGES_RUN_ID"
gh run watch "$PAGES_RUN_ID" --repo "$PUBLIC_REPOSITORY_SLUG"
gh api "repos/$PUBLIC_REPOSITORY_SLUG/pages" --jq '{status,html_url}'
```

Expected: Pages workflow succeeds and the returned public URL serves the
verified site. Open the public URL and repeat the Home → Roadmap → Lesson →
Catalog smoke journey.

- [ ] **Step 5: Materialize release metadata through a PR, then publish**

The initial public PR intentionally contains only `Unreleased` notes and no
`date-released`. From the isolated publication clone, create a dedicated
release metadata branch. Materialize the actual UTC date, verify the exact
`[0.1.0] - ${RELEASE_DATE}` heading and `date-released`, then open a second
release metadata PR. The tag must not exist before that PR is reviewed and
merged.

```bash
set -euo pipefail
git -C "$PUBLICATION_CLONE" switch main
git -C "$PUBLICATION_CLONE" pull --ff-only public main
RELEASE_DATE="$(date -u +%F)"
test -n "$RELEASE_DATE"
git -C "$PUBLICATION_CLONE" switch -c release/v0.1.0-metadata
(cd "$PUBLICATION_CLONE" && RELEASE_DATE="$RELEASE_DATE" python3.13 - <<'PY'
from datetime import date
import os
from pathlib import Path

release_date = os.environ["RELEASE_DATE"]
date.fromisoformat(release_date)

citation_path = Path("CITATION.cff")
citation = citation_path.read_text(encoding="utf-8")
version_line = 'version: "0.1.0"\n'
if citation.count(version_line) != 1 or "date-released:" in citation:
    raise SystemExit("citation is not in the expected unreleased state")
citation_path.write_text(
    citation.replace(
        version_line,
        f'{version_line}date-released: {release_date}\n',
        1,
    ),
    encoding="utf-8",
)

changelog_path = Path("CHANGELOG.md")
changelog = changelog_path.read_text(encoding="utf-8")
unreleased = "## [Unreleased]\n"
footer = (
    "[Unreleased]: https://github.com/albert-einshutoin/"
    "engineering-expert-curriculum/commits/main\n"
)
if changelog.count(unreleased) != 1 or changelog.count(footer) != 1:
    raise SystemExit("changelog is not in the expected unreleased state")
body_start = changelog.index("### Added", changelog.index(unreleased))
body_end = changelog.index(footer)
release_body = changelog[body_start:body_end].rstrip()
prefix = changelog[: changelog.index(unreleased) + len(unreleased)]
released = (
    f"{prefix}\n- 次回releaseの変更は、検証証拠が確定した時点で追記します。\n\n"
    f"## [0.1.0] - {release_date}\n\n{release_body}\n\n"
    "[Unreleased]: https://github.com/albert-einshutoin/"
    "engineering-expert-curriculum/compare/v0.1.0...HEAD\n"
    "[0.1.0]: https://github.com/albert-einshutoin/"
    "engineering-expert-curriculum/releases/tag/v0.1.0\n"
)
changelog_path.write_text(released, encoding="utf-8")
PY
)
(cd "$PUBLICATION_CLONE" && python3.13 -m unittest discover -s tests -v)
(cd "$PUBLICATION_CLONE" && python3.13 tools/build.py)
(cd "$PUBLICATION_CLONE" && \
  python3.13 tools/check_site.py --root site --require-current-release)
git -C "$PUBLICATION_CLONE" add CITATION.cff CHANGELOG.md
git -C "$PUBLICATION_CLONE" commit -m "docs: materialize v0.1.0 release metadata"
git -C "$PUBLICATION_CLONE" push --set-upstream public \
  refs/heads/release/v0.1.0-metadata:refs/heads/release/v0.1.0-metadata
RELEASE_PR_URL="$(gh pr create --repo "$PUBLIC_REPOSITORY_SLUG" --base main \
  --head "${PUBLIC_OWNER}:release/v0.1.0-metadata" \
  --title "docs: materialize v0.1.0 release metadata" \
  --body "Records the actual release date after the curriculum PR; no tag or release exists yet.")"
test -n "$RELEASE_PR_URL"
gh pr checks "$RELEASE_PR_URL" --repo "$PUBLIC_REPOSITORY_SLUG" --watch

RELEASE_PR_NUMBER="$(gh pr view "$RELEASE_PR_URL" \
  --repo "$PUBLIC_REPOSITORY_SLUG" --json number --jq '.number')"
RELEASE_HEAD_SHA="$(gh pr view "$RELEASE_PR_URL" \
  --repo "$PUBLIC_REPOSITORY_SLUG" --json headRefOid --jq '.headRefOid')"
test -n "$RELEASE_PR_NUMBER"
test -n "$RELEASE_HEAD_SHA"
RELEASE_THREAD_STATE="$(gh api graphql \
  -F owner="${PUBLIC_REPOSITORY_SLUG%%/*}" \
  -F name="${PUBLIC_REPOSITORY_SLUG#*/}" -F number="$RELEASE_PR_NUMBER" \
  -f query='query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){pullRequest(number:$number){reviewThreads(first:100){nodes{isResolved}pageInfo{hasNextPage}}}}}' \
  --jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)] | length | tostring + ":" + (.data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage | tostring)')"
test "$RELEASE_THREAD_STATE" = "0:false"
RELEASE_REVIEWER_KIND="${RELEASE_REVIEWER_KIND:?set the truthful reviewerKind}"
case "$RELEASE_REVIEWER_KIND" in human|ai-assisted|automated) ;; *) exit 1 ;; esac
RELEASE_DECISION_FILE="${RELEASE_DECISION_FILE:?write the metadata PR Model B decision}"
test -s "$RELEASE_DECISION_FILE"
grep -Fqx "commit: $RELEASE_HEAD_SHA" "$RELEASE_DECISION_FILE"
grep -Fqx "reviewerKind: $RELEASE_REVIEWER_KIND" "$RELEASE_DECISION_FILE"
grep -Fqx "independent human approval: none" "$RELEASE_DECISION_FILE"
grep -Fqx "unresolved threads: 0" "$RELEASE_DECISION_FILE"
for dimension in "technical accuracy" "learning design and evidence" \
  accessibility "editorial and source quality"; do
  grep -Fqx "review dimension: $dimension" "$RELEASE_DECISION_FILE"
done
grep -Eq '^residual risk: .+' "$RELEASE_DECISION_FILE"
gh pr comment "$RELEASE_PR_URL" --repo "$PUBLIC_REPOSITORY_SLUG" \
  --body-file "$RELEASE_DECISION_FILE"
```

The release metadata PR now has its own Model B commit, `reviewerKind`,
four-dimension, residual-risk, and unresolved-thread evidence. Merge it with
the same history-preserving strategy and verify the result before creating the
tag:

```bash
gh pr merge --merge --delete-branch --repo "$PUBLIC_REPOSITORY_SLUG" \
  "$RELEASE_PR_URL"
gh pr view "$RELEASE_PR_URL" --repo "$PUBLIC_REPOSITORY_SLUG" \
  --json state,mergedAt,mergeCommit,url
RELEASE_MERGE_SHA="$(gh pr view "$RELEASE_PR_URL" \
  --repo "$PUBLIC_REPOSITORY_SLUG" --json mergeCommit --jq '.mergeCommit.oid')"
test -n "$RELEASE_MERGE_SHA"
git -C "$PUBLICATION_CLONE" switch main
git -C "$PUBLICATION_CLONE" pull --ff-only public main
test "$(git -C "$PUBLICATION_CLONE" rev-parse HEAD)" = "$RELEASE_MERGE_SHA"
test "$(git -C "$PUBLICATION_CLONE" rev-list --parents -n 1 \
  "$RELEASE_MERGE_SHA" | awk '{print NF}')" -eq 3
test "$(git -C "$PUBLICATION_CLONE" show HEAD:CITATION.cff | \
  grep -Ec "^date-released: ${RELEASE_DATE}$")" -eq 1
test "$(git -C "$PUBLICATION_CLONE" show HEAD:CHANGELOG.md | \
  grep -Ec "^## \[0\.1\.0\] - ${RELEASE_DATE}$")" -eq 1
git -C "$PUBLICATION_CLONE" tag -a v0.1.0 -m "Engineering Expert Curriculum v0.1.0"
test "$(git -C "$PUBLICATION_CLONE" rev-list -n 1 v0.1.0)" = \
  "$RELEASE_MERGE_SHA"
git -C "$PUBLICATION_CLONE" push public refs/tags/v0.1.0:refs/tags/v0.1.0
REMOTE_RELEASE_SHA="$(git -C "$PUBLICATION_CLONE" ls-remote public \
  'refs/tags/v0.1.0^{}' | awk '{print $1}')"
test "$REMOTE_RELEASE_SHA" = "$RELEASE_MERGE_SHA"
gh release create v0.1.0 --repo "$PUBLIC_REPOSITORY_SLUG" --verify-tag \
  --title "Engineering Expert Curriculum v0.1.0" --notes-from-tag
gh release view v0.1.0 --repo "$PUBLIC_REPOSITORY_SLUG" \
  --json tagName,isDraft,isPrerelease,publishedAt,url,targetCommitish
```

Expected: tag `v0.1.0` points at the verified public merge commit and the
release is published, not a draft or prerelease.

- [ ] **Step 6: Clean only the merged public feature branch**

Run:

```bash
git -C "$PUBLICATION_CLONE" fetch public --prune
git -C "$PUBLICATION_CLONE" branch -d feat/static-oss-curriculum
git -C "$PUBLICATION_CLONE" branch -d release/v0.1.0-metadata
git -C "$PUBLICATION_CLONE" branch -vv
git -C "$PUBLICATION_CLONE" status --short --branch
```

Expected: public `main` and `v0.1.0` remain, and only the merged public feature
branch has been cleaned. 元リポジトリ、元feature branch、元worktree、非公開archiveは削除しない。
They remain intact and recoverable until a separately authorized retention
decision; this publication runbook never removes or rewrites them.
