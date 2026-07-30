# OSS Publication and GitHub Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the verified curriculum as a contributor-ready public GitHub repository with least-privilege CI, security and accessibility gates, GitHub Pages, transparent governance, and a clean GitHub Flow lifecycle.

**Architecture:** Pull requests run a dependency-free validation workflow that builds the complete static artifact and fails closed. Merges to `main` run the same gate before a separate least-privilege Pages deployment job; OSS documentation and templates make content decisions, corrections, security reports, and contributor expectations reviewable without private context.

**Tech Stack:** GitHub, GitHub Actions pinned to immutable SHAs, Python 3.12 standard library, GitHub Pages, Markdown, HTML5/CSS3

---

## Immutable action revisions

Verified with `git ls-remote` on 2026-07-30:

| Action | Tag | Immutable revision |
|---|---|---|
| `actions/checkout` | `v4.2.2` | `11bd71901bbe5b1630ceea73d27597364c9af683` |
| `actions/setup-python` | `v5.6.0` | `a26af69be951a213d495a4c3e4e4022e16d87065` |
| `actions/upload-pages-artifact` | `v3` | `56afc609e74202658d3ffba0e8f6dda462b719fa` |
| `actions/deploy-pages` | `v4` | `d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e` |
| `github/codeql-action` | `v3` | `3b0bd1d116c0bde30213346b22d4f634d96a2fb0` |

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
| `.github/dependabot.yml` | Monthly GitHub Actions revision review |
| `tests/test_repository_contract.py` | Required OSS files and metadata |
| `tests/test_repository_security.py` | Secret patterns, workflow permissions, and static artifact contract |
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

`CITATION.cff` uses version `0.1.0`, release date `2026-07-30`, MIT license,
repository title, and `authors: [{name: "Engineering Expert Curriculum contributors"}]`.

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
        "CHANGELOG.md": ("Unreleased", "0.1.0"),
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
→ self-review → PR → required review/CI → squash merge → branch deletion
```

It also defines four review roles for a complete lesson:

1. Technical accuracy reviewer
2. Pedagogy and evidence reviewer
3. Accessibility reviewer
4. Editorial and source reviewer

`GOVERNANCE.md` makes maintainers accountable for safety and release decisions,
reviewers accountable only for the dimension they approve, and contributors
eligible to become reviewers through three accepted contributions plus a
documented review. Framework upgrades require an issue, impact matrix, mapping
PR, and release note.

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

`CODE_OF_CONDUCT.md` adopts Contributor Covenant 2.1 by reference and names
GitHub private maintainer contact as the enforcement route. `CHANGELOG.md`
contains `Unreleased` and `0.1.0` sections following Keep a Changelog structure.

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
python3 tools/check_site.py site
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
python3 tools/check_site.py site
git status --ignored --short | sed -n '1,80p'
```

Expected: checks pass; local archive, brainstorming, and generated site appear
only as ignored entries.

- [ ] **Step 5: Commit repository security contracts**

```bash
git add .gitignore tests/test_repository_security.py
git commit -m "test: guard public repository against secret leakage"
```

### Task 6: Add least-privilege validation, CodeQL, and dependency review

**Files:**
- Create: `.github/workflows/validate.yml`
- Create: `.github/workflows/codeql.yml`
- Create: `.github/dependabot.yml`
- Modify: `tests/test_repository_security.py`

- [ ] **Step 1: Add workflow-permission assertions**

```python
def test_pull_request_workflows_are_read_only_and_sha_pinned(self) -> None:
    for relative in (
        ".github/workflows/validate.yml",
        ".github/workflows/codeql.yml",
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
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065
        with:
          python-version: "3.12"
      - name: Compile build tools
        run: python -m compileall -q curriculum_builder tools tests
      - name: Run complete test suite
        run: python -m unittest discover -s tests -v
      - name: Build static site
        run: python tools/build.py
      - name: Validate static artifact
        run: python tools/check_site.py site
      - name: Verify reproducible output
        run: |
          find site -type f -exec sha256sum {} + | sort > /tmp/build-1.sha256
          python tools/build.py
          find site -type f -exec sha256sum {} + | sort > /tmp/build-2.sha256
          diff -u /tmp/build-1.sha256 /tmp/build-2.sha256
```

Add `codeql.yml` with `contents: read`, `security-events: write` only at the job
that uploads results, Python language analysis, and the pinned checkout and
CodeQL revision from the table. Add `.github/dependabot.yml` with monthly
`github-actions` checks targeting `main`, a limit of five open PRs, and
`labels: ["dependencies", "github-actions"]`.

- [ ] **Step 4: Run workflow contracts and inspect YAML**

Run:

```bash
python3 -m unittest tests.test_repository_security -v
sed -n '1,220p' .github/workflows/validate.yml
sed -n '1,220p' .github/workflows/codeql.yml
```

Expected: tests pass; no action uses a floating tag.

- [ ] **Step 5: Commit CI and analysis**

```bash
git add .github/workflows/validate.yml .github/workflows/codeql.yml \
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
    self.assertIn("python tools/check_site.py site", text)
    self.assertLess(text.index("python tools/check_site.py site"), text.index("upload-pages-artifact"))
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
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065
        with:
          python-version: "3.12"
      - run: python -m unittest discover -s tests -v
      - run: python tools/build.py
      - run: python tools/check_site.py site
      - uses: actions/upload-pages-artifact@56afc609e74202658d3ffba0e8f6dda462b719fa
        with:
          path: site

  deploy:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      pages: write
      id-token: write
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - name: Deploy verified artifact
        id: deployment
        uses: actions/deploy-pages@d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e
```

- [ ] **Step 4: Run all workflow permission tests**

Run:

```bash
python3 -m unittest tests.test_repository_security -v
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
- Create: `docs/reviews/2026-07-30-release-readiness.md`

- [ ] **Step 1: Run the complete clean build**

Run:

```bash
python3 -m compileall -q curriculum_builder tools tests
python3 -m unittest discover -s tests -v
python3 tools/build.py
python3 tools/check_site.py site
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
git grep -nE 'BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|ghp_|github_pat_|sk-(proj-)?' \
  -- . ':(exclude)docs/superpowers/plans/*' || true
git log --oneline --decorate main..HEAD
```

Review correctness, test adequacy, content-source quality, link safety,
accessibility, security boundaries, maintainability, contributor journey, and
whether every commit is independently understandable.

- [ ] **Step 5: Commit review evidence and fixes**

```bash
git add docs/reviews/2026-07-30-release-readiness.md static templates tests
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
gh api user --jq '.login'
gh repo view engineering-expert-curriculum --json nameWithOwner,visibility 2>/dev/null || true
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

- [ ] **Step 3: Add the remote and push both branches**

Run from the implementation worktree after substituting only the verified login:

```bash
git remote add origin "$PRIVATE_EMAIL:albert-einshutoin/engineering-expert-curriculum.git"
git -C $REPO_ROOT remote add origin \
  "$PRIVATE_EMAIL:albert-einshutoin/engineering-expert-curriculum.git"
git -C $REPO_ROOT push -u origin main
git push -u origin feat/static-oss-curriculum
```

Expected: `main` and the feature branch exist remotely; `main` remains the
default release branch.

- [ ] **Step 4: Open a context-complete pull request**

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

Expected: one open PR targeting `main`.

- [ ] **Step 5: Confirm remote state**

Run:

```bash
gh pr view --json number,url,state,baseRefName,headRefName,isDraft,mergeable
gh pr checks --watch
```

Expected: PR is open, not draft, targets `main`, and every check is successful.

### Task 10: Review, merge, enable Pages, and clean branches

**Files:**
- External state: PR review and merge
- External state: repository settings, Pages, branch protection, topics
- Local state: Git worktree and merged feature branch removal

- [ ] **Step 1: Perform final PR self-review against remote diff**

Run:

```bash
gh pr diff --color=never > /tmp/engineering-curriculum-pr.diff
gh pr view --json files,commits,reviews,reviewDecision,mergeable,statusCheckRollup
```

Review the remote diff for content accuracy, test adequacy, source and framework
versioning, unsafe HTML, secret leakage, broken relative paths, CI permissions,
accessibility, documentation consistency, and OSS value. Fix findings on the
feature branch with a failing regression test first, push, and wait for checks.

- [ ] **Step 2: Configure repository metadata and protection**

Set description, homepage after Pages deployment, and topics:

```text
computer-science, curriculum, engineering, learning, oss, static-site,
software-engineering, textbook
```

Enable private vulnerability reporting, automatic feature-branch deletion, and
`main` protection requiring the `full-validation` and CodeQL checks with no
force pushes or branch deletion.

- [ ] **Step 3: Merge only the verified PR**

Run:

```bash
gh pr merge --squash --delete-branch
gh pr view --json state,mergedAt,mergeCommit,url
```

Expected: state is `MERGED`, `mergedAt` is non-null, and the remote feature
branch is absent.

- [ ] **Step 4: Verify Pages deployment and public site**

Run:

```bash
gh run list --branch main --limit 10
gh run watch "$(gh run list --workflow 'Deploy GitHub Pages' --branch main --limit 1 --json databaseId --jq '.[0].databaseId')"
gh api "repos/{owner}/{repo}/pages" --jq '{status,html_url}'
```

Expected: Pages workflow succeeds and the returned public URL serves the
verified site. Open the public URL and repeat the Home → Roadmap → Lesson →
Catalog smoke journey.

- [ ] **Step 5: Update local main and remove merged branch/worktree**

Run:

```bash
git -C $REPO_ROOT pull --ff-only origin main
git -C $REPO_ROOT worktree remove \
  $FEATURE_WORKTREE
git -C $REPO_ROOT branch -d \
  feat/static-oss-curriculum
git -C $REPO_ROOT fetch --prune
git -C $REPO_ROOT branch -vv
git -C $REPO_ROOT status --short --branch
```

Expected: local `main` matches `origin/main`; the feature worktree and local and
remote feature branches are gone; the local checksum-verified `.archive/`
remains ignored and recoverable.
