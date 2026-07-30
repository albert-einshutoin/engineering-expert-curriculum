# Static Curriculum Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the existing prototype and build a dependency-free Python pipeline that validates 1,140 catalog items and produces an accessible HTML/CSS-only site that works over `file://`.

**Architecture:** Repository-controlled JSON and semantic HTML fragments are parsed into immutable domain models, validated before rendering, and emitted into an atomically replaced `site/` directory. The build separates catalog import, prerequisite-graph logic, HTML safety, rendering, and orchestration so each boundary can be tested independently.

**Tech Stack:** Python 3.12+ standard library (validated with Python 3.13), `unittest`, HTML5, CSS3, GitHub Flow

---

## File map

| Path | Responsibility |
|---|---|
| `tools/migrate_prototype.py` | Checksum-verified preservation of the existing generated prototype |
| `tools/import_catalog.py` | One-time deterministic conversion from prototype JSON to canonical catalog JSON |
| `tools/build.py` | Thin build CLI and atomic output replacement |
| `curriculum_builder/errors.py` | Public validation error type |
| `curriculum_builder/models.py` | Immutable catalog and page domain values |
| `curriculum_builder/catalog.py` | Catalog loading, validation, and grouping |
| `curriculum_builder/graph.py` | Prerequisite validation and deterministic topological stages |
| `curriculum_builder/html_safety.py` | Repository-authored HTML-fragment allowlist |
| `curriculum_builder/render.py` | Escaped HTML page rendering |
| `curriculum_builder/build.py` | Build use case and output contracts |
| `templates/*.html` | HTML document and page templates |
| `static/styles.css` | Hybrid Atlas/Textbook visual system |
| `content/catalog.json` | Canonical 1,140-item catalog |
| `content/roadmap.json` | Initial static learning-stage graph |
| `tests/test_*.py` | Unit and acceptance contracts |

### Task 1: Establish Python project and test entry point

**Files:**
- Create: `pyproject.toml`
- Create: `curriculum_builder/__init__.py`
- Create: `curriculum_builder/errors.py`
- Create: `tests/__init__.py`
- Create: `tests/test_project_contract.py`

- [ ] **Step 1: Write the failing project-contract test**

```python
# tests/test_project_contract.py
from __future__ import annotations

import importlib
from pathlib import Path
import tomllib
import unittest


class ProjectContractTests(unittest.TestCase):
    def test_package_exposes_version(self) -> None:
        package = importlib.import_module("curriculum_builder")
        self.assertEqual(package.__version__, "0.1.0")

    def test_project_metadata_matches_package_contract(self) -> None:
        package = importlib.import_module("curriculum_builder")
        pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
        with pyproject_path.open("rb") as pyproject_file:
            project = tomllib.load(pyproject_file)["project"]

        self.assertEqual(project["version"], package.__version__)
        self.assertEqual(project["license"], "MIT")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
python3.13 -m unittest tests.test_project_contract -v
```

Expected: `ERROR` with `ModuleNotFoundError: No module named 'curriculum_builder'`.

- [ ] **Step 3: Add the minimal package and tool configuration**

```toml
# pyproject.toml
[project]
name = "engineering-expert-curriculum"
version = "0.1.0"
description = "A dependency-free static textbook for engineering expertise"
requires-python = ">=3.12"
license = "MIT"
```

```python
# curriculum_builder/__init__.py
"""Build and validate the static Engineering Expert Curriculum."""

__version__ = "0.1.0"
```

```python
# curriculum_builder/errors.py
class CurriculumValidationError(ValueError):
    """Raised when version-controlled curriculum content breaks its contract."""
```

- [ ] **Step 4: Run the focused and discovered suites**

Run:

```bash
python3.13 -m unittest tests.test_project_contract -v
python3.13 -m unittest discover -s tests -v
```

Expected: both commands report `OK`.

- [ ] **Step 5: Commit the testable package skeleton**

```bash
git add pyproject.toml curriculum_builder tests
git commit -m "build: establish dependency-free curriculum package"
```

### Task 2: Preserve the prototype with verified checksums

**Files:**
- Create: `tools/migrate_prototype.py`
- Create: `tests/test_migrate_prototype.py`
- Modify: `docs/superpowers/plans/2026-07-30-static-curriculum-foundation.md`

- [ ] **Step 1: Write fail-safe preservation tests first**

Cover the exact eleven-element `LEGACY_PATHS`, an empty source, independent
manifest SHA-256/byte-count checks, and the CLI. Use `TemporaryDirectory` only.
Also cover injected copy and checksum failures, source/dangling-archive/nested
symlinks, special files such as FIFOs when available, and an archive path inside
an allowlisted subtree. Reject lexical `..` input, source/archive intermediate
symlinks, symlink routes into allowlisted archive subtrees, and casefolded
allowlist boundaries before copying. Test private staging `mkdir`/`stat`/`open`
races, a native target collision immediately before publish, and foreign
sentinels: no foreign entry may be written or deleted. Cover parent-FD identity,
FD close failures with the original operation as the cause, and a full durability
order for regular files, nested directories, staging root, manifest temp, and
manifest rename, native publish, and parent fsync. Cover missing/insecure archive
parents, NUL source/target basenames, unsupported native publish, and the
post-publish parent-fsync durability error. Parent `mkdir`/`stat` foreign races
are no longer reachable through the main flow because the parent is
operator-prepared. Every pre-publish owned-failure path retains the source and
publishes no final archive. Test only temporary fixtures, never repository
prototype files.

- [ ] **Step 2: Verify RED**

Run `python3.13 -m unittest tests.test_migrate_prototype -v` after adding each
new failure case. Confirm the missing private-staging, no-clobber publication,
or durability boundary fails for the intended safety reason before changing
production code.

- [ ] **Step 3: Implement transactional copy and atomic publication**

`preserve_prototype(source, archive)` accepts no caller-provided allowlist and
uses only `LEGACY_PATHS`. Before resolving paths, use `lexists` and `lstat` to
reject a symlink source, existing archive (including dangling symlink), and
unsafe descendant components. Reject archive locations under a legacy subtree;
an allowlist-external location such as `.archive/prototype-v1` is permitted.
First reject raw `..` parts even for relative inputs. Inspect every existing raw
component from filesystem root to final node with `lstat`, then canonicalize the
source strictly. Compare canonical paths so no symlink or traversal route can
place an archive under an allowlisted source subtree.

The ordering is deliberately read-only until safety is established: validate the
source, take its initial snapshot (and reject empty input), then perform archive
lexical/canonical boundary validation. The operator prepares the archive parent
with the no-follow creation-and-validation sequence in Task 10: it creates only
an absent directory and rejects an existing symlink, non-directory, foreign
owner, or group/world-writable directory without changing it. The tool requires
an existing canonical directory owned by the current effective user and not
group/world writable. The validation helper opens it with
`O_DIRECTORY|O_NOFOLLOW`, verifies the same inode with `fstat`, and transfers
that pinned FD to publication; the caller never reopens the pathname. It never
creates or deletes this parent, avoiding `mkdir`/`stat` ownership races at the
trusted boundary.

Verify the pinned parent inode with `fstat`. Create a random `0o700` private
staging directory below it using `dir_fd` operations; verify staging identity and
emptiness before use. This pins cleanup to owned inodes rather than replaceable
pathnames. Fail closed where required descriptor operations are unavailable.

Walk all existing allowlisted trees before copying and fail closed for symlinks,
FIFOs, sockets, devices, or other non-regular/non-directory nodes. Build a
source snapshot from streaming reads that produce each file's SHA-256 and byte
count together. Copy only approved entries into private staging, `fsync` every
regular file, nested directory, and staging root, then compare initial, staged,
and current source snapshots. Write the typed manifest through an exclusively
created temp file, `fsync` it, `fsync` staging before its internal
`manifest.json` rename, then `fsync` staging again after that rename.

The sole external commit point is a native no-overwrite directory rename of the
verified private staging directory to the final archive name:
`renameatx_np(RENAME_EXCL)` on macOS or `renameat2(RENAME_NOREPLACE)` on Linux.
Native names must be nonempty basenames and reject `.`, `..`, slash, and NUL;
the wrapper resets `errno` and fails closed for an unsupported platform, missing
native primitive, or failure without errno. An existing target always fails
without replacement. Immediately after native publish, `fsync` the prepared
parent FD so the final name is durable. If that fsync fails, raise
`PrototypePublicationDurabilityError`: the archive and manifest are already
published, no rollback occurs, power-loss durability is unknown, and the
operator must inspect it. Any failure before publish removes only the still-owned
private staging directory; foreign sentinels and the prepared parent are retained.
Source files are retained after publication, and the migration is never run
against real repository prototype files during tests. The Python 3.13 suite
exercises the same contract on macOS and Linux.

- [ ] **Step 4: Verify GREEN without running on repository files**

```bash
python3.13 -m unittest tests.test_migrate_prototype -v
python3.13 -m unittest discover -s tests -v
git diff --check
```

- [ ] **Step 5: Commit the private-staging publication tool**

```bash
git add tools/migrate_prototype.py tests/test_migrate_prototype.py docs/superpowers/plans/2026-07-30-static-curriculum-foundation.md
git commit -m "fix: publish verified prototype without clobbering"
```

### Task 3: Define immutable catalog models

**Files:**
- Create: `curriculum_builder/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write model validation tests**

```python
# tests/test_models.py
from __future__ import annotations

import unittest

from curriculum_builder.errors import CurriculumValidationError
from curriculum_builder.models import CatalogItem


VALID_ITEM = {
    "id": "D01-M01-L1",
    "title": "離散数学と論理 — 基礎",
    "domainId": 1,
    "domainTitle": "数学・統計",
    "domainSlug": "math-statistics",
    "moduleIndex": 1,
    "moduleTitle": "離散数学と論理",
    "level": 1,
    "levelLabel": "基礎",
    "concepts": ["集合・写像・関係", "命題と述語"],
    "outcome": "仕様を形式的に表現できる",
    "coreLessonId": None,
}


class CatalogItemTests(unittest.TestCase):
    def test_parses_valid_item_into_immutable_value(self) -> None:
        item = CatalogItem.from_dict(VALID_ITEM)
        self.assertEqual(item.id, "D01-M01-L1")
        self.assertEqual(item.concepts, ("集合・写像・関係", "命題と述語"))
        with self.assertRaises(AttributeError):
            item.title = "changed"  # type: ignore[misc]

    def test_rejects_invalid_identifier(self) -> None:
        raw = {**VALID_ITEM, "id": "../unsafe"}
        with self.assertRaisesRegex(CurriculumValidationError, "invalid catalog id"):
            CatalogItem.from_dict(raw)

    def test_rejects_unknown_fields(self) -> None:
        raw = {**VALID_ITEM, "path": "legacy/generated/page.html"}
        with self.assertRaisesRegex(CurriculumValidationError, "unknown fields: path"):
            CatalogItem.from_dict(raw)
```

- [ ] **Step 2: Run model tests and verify RED**

Run:

```bash
python3.13 -m unittest tests.test_models -v
```

Expected: import fails because `curriculum_builder.models` does not exist.

- [ ] **Step 3: Implement the frozen model and explicit parser**

```python
# curriculum_builder/models.py
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from curriculum_builder.errors import CurriculumValidationError

CATALOG_FIELDS = {
    "id", "title", "domainId", "domainTitle", "domainSlug", "moduleIndex",
    "moduleTitle", "level", "levelLabel", "concepts", "outcome", "coreLessonId",
}
CATALOG_ID = re.compile(r"^D[0-9]{2}-M[0-9]{2}-L[1-3]$")


@dataclass(frozen=True, slots=True)
class CatalogItem:
    id: str
    title: str
    domain_id: int
    domain_title: str
    domain_slug: str
    module_index: int
    module_title: str
    level: int
    level_label: str
    concepts: tuple[str, ...]
    outcome: str
    core_lesson_id: str | None

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "CatalogItem":
        unknown = sorted(set(raw) - CATALOG_FIELDS)
        if unknown:
            raise CurriculumValidationError(f"unknown fields: {', '.join(unknown)}")
        item_id = str(raw.get("id", ""))
        if not CATALOG_ID.fullmatch(item_id):
            raise CurriculumValidationError(f"invalid catalog id: {item_id}")
        concepts = tuple(str(value).strip() for value in raw.get("concepts", ()))
        required_text = ("title", "domainTitle", "domainSlug", "moduleTitle", "outcome")
        for field in required_text:
            if not str(raw.get(field, "")).strip():
                raise CurriculumValidationError(f"{item_id}: empty {field}")
        if not concepts or any(not concept for concept in concepts):
            raise CurriculumValidationError(f"{item_id}: concepts must be non-empty")
        level = int(raw["level"])
        if level not in (1, 2, 3):
            raise CurriculumValidationError(f"{item_id}: level must be 1, 2, or 3")
        return cls(
            id=item_id,
            title=str(raw["title"]).strip(),
            domain_id=int(raw["domainId"]),
            domain_title=str(raw["domainTitle"]).strip(),
            domain_slug=str(raw["domainSlug"]).strip(),
            module_index=int(raw["moduleIndex"]),
            module_title=str(raw["moduleTitle"]).strip(),
            level=level,
            level_label=str(raw["levelLabel"]).strip(),
            concepts=concepts,
            outcome=str(raw["outcome"]).strip(),
            core_lesson_id=(
                str(raw["coreLessonId"]).strip() if raw.get("coreLessonId") else None
            ),
        )
```

- [ ] **Step 4: Run model tests**

Run:

```bash
python3.13 -m unittest tests.test_models -v
```

Expected: three tests pass.

- [ ] **Step 5: Commit the catalog domain boundary**

```bash
git add curriculum_builder/models.py tests/test_models.py
git commit -m "feat: validate immutable catalog items"
```

### Task 4: Import exactly 1,140 canonical catalog records

**Files:**
- Create: `tools/import_catalog.py`
- Create: `curriculum_builder/catalog.py`
- Create: `tests/test_import_catalog.py`
- Create: `tests/test_catalog.py`
- Create: `content/catalog.json`

- [ ] **Step 1: Write importer and catalog contract tests**

The importer fixture must build the full legacy shape: root fields `version`,
`title`, `generated`, `domainCount`, `moduleCount`, `lessonCount`, `tracks`,
`domains`, and `lessons`; each domain contains its exact declaration and modules,
and each lesson includes the required legacy `path`. Assert that `canonicalize`
removes only `path`, supplies `coreLessonId=None`, sorts IDs, normalizes
`generatedFrom`, and records the supplied `sourceSha256`.

```python
# tests/test_catalog.py
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from curriculum_builder.catalog import load_catalog, load_repository_catalog
from curriculum_builder.errors import CurriculumValidationError


class CatalogTests(unittest.TestCase):
    def test_rejects_duplicate_ids(self) -> None:
        item = {
            "id": "D01-M01-L1", "title": "基礎", "domainId": 1,
            "domainTitle": "数学", "domainSlug": "math", "moduleIndex": 1,
            "moduleTitle": "論理", "level": 1, "levelLabel": "基礎",
            "concepts": ["集合"], "outcome": "形式化できる", "coreLessonId": None,
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(
                json.dumps({"version": 1, "generatedFrom": "test", "sourceSha256": "a" * 64, "items": [item, item]}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(CurriculumValidationError, "duplicate"):
                load_catalog(path)

    def test_repository_catalog_has_exact_contract(self) -> None:
        items = load_repository_catalog(Path("content/catalog.json"))
        self.assertEqual(len(items), 1140)
        self.assertEqual(len({item.id for item in items}), 1140)
        self.assertEqual(len({item.domain_id for item in items}), 38)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python3.13 -m unittest tests.test_import_catalog tests.test_catalog -v
```

Expected: imports fail because importer and catalog loader do not exist.

- [ ] **Step 3: Implement deterministic import and loading**

- `canonicalize` enforces the exact legacy root/domain/module/lesson schema,
  counts, and declaration links; it removes only `path`, validates through
  `CatalogItem`, and emits exactly `version`, `generatedFrom`, `sourceSha256`,
  and sorted `items`.
- JSON is read once as bytes, SHA-256 is recorded, and strict parsing rejects
  duplicate keys and noncanonical serialization. `load_catalog` is generic;
  `load_repository_catalog` additionally verifies artifact
  `4f38b5f63931a7f06e13f90f5d9ef90a0a435f30dae5d4fe70720d730a057473` and
  source `a55a0d0b1cfa3773031e787c2ce7ca0df34534e16a70b65ed1baa91975c82da8`.
- The importer opens the trusted existing output parent from root with
  `O_NOFOLLOW` directory FDs, writes an `O_EXCL` private temp using partial-write
  handling, chmods `0644`, fsyncs the file, performs dirfd `replace`, then fsyncs
  the parent. It reports prepublish, integrity, and durability states explicitly.
  A malicious exact same-euid rename race is out of scope: imports run exclusively
  and the postcheck detects rather than rolls back a foreign entry.

- [ ] **Step 4: Import the real catalog and run contracts**

Run:

```bash
python3.13 tools/import_catalog.py \
  --input $REPO_ROOT/data/curriculum.json \
  --output content/catalog.json
python3.13 -m unittest tests.test_import_catalog tests.test_catalog -v
```

Expected: all tests pass and `content/catalog.json` contains 1,140 sorted items.

- [ ] **Step 5: Commit the canonical catalog without generated pages**

```bash
git add tools/import_catalog.py curriculum_builder/catalog.py \
  tests/test_import_catalog.py tests/test_catalog.py content/catalog.json
git commit -m "feat: preserve 1140 items in canonical catalog"
```

### Task 5: Validate the prerequisite graph deterministically

**Files:**
- Create: `curriculum_builder/graph.py`
- Create: `tests/test_graph.py`
- Create: `content/roadmap.json`

- [ ] **Step 1: Write graph behavior tests**

Write the 26 Task 5 tests in `tests/test_graph.py`. They form the public graph
contract and cover:

- Sorted parallel stages returned as an immutable tuple of tuples.
- Sorted, deterministic diagnostics for cycles and missing prerequisites.
- Nodes omitted from the mapping defaulting to no prerequisites.
- Rejection of a string passed as `node_ids`, non-string IDs, empty IDs,
  leading or trailing whitespace, and duplicate IDs.
- Rejection of a non-mapping `prerequisites` argument, non-string or unknown
  mapping keys, string or non-iterable dependency collections, non-string,
  empty, or whitespace-padded dependency IDs, duplicate dependencies, and
  explicit self-dependencies.
- Exact built-in `str` identifiers, including controlled rejection of
  unhashable `str` subclasses in node, key, and dependency positions.
- Single consumption of generator-based node and dependency inputs, plus a
  one-time `items()` snapshot of the prerequisite mapping.
- Deterministic invalid-value rendering that calls each `repr` once and
  converts a failing `repr` into `CurriculumValidationError`.
- Edge-driven Kahn staging of a 1,024-node chain without per-stage scans of all
  unresolved nodes.
- Results independent of node, dependency, and mapping insertion order.
- No input mutation, immutable output, and the empty-graph result.
- The checked-in roadmap's strict version 1 root and node schemas, four unique
  IDs, exact initial titles and prerequisites, and expected topological stages,
  including successful validation when the test runs outside the repository
  working directory.

Use `strict_json_loads` for the checked-in roadmap test so duplicate JSON keys
cannot bypass the schema assertions. Keep the graph API independent from the
catalog module; JSON decoding is an artifact-test concern at this stage.

- [ ] **Step 2: Run graph tests and verify RED**

Run:

```bash
python3.13 -m unittest tests.test_graph -v
```

Expected: import fails because `curriculum_builder.graph` does not exist.

- [ ] **Step 3: Implement Kahn staging with stable ordering**

Implement the validated contract in `curriculum_builder/graph.py`; the source
file is canonical, so do not duplicate its complete implementation in this
plan. The implementation must:

1. Materialize `node_ids` exactly once, require exact built-in `str` values,
   and reject duplicate IDs before creating any set-like lookup structure.
2. Snapshot the prerequisite mapping through one `items()` call, then validate
   and use only that snapshot; never iterate, query, or index the original
   mapping again.
3. Materialize each dependency iterable exactly once in sorted node order,
   require exact built-in `str` values, validate its original sequence, and
   reject duplicates before converting it to a `frozenset`.
4. Render invalid values once before sorting their rendered forms. Replace
   failures from adversarial `repr` methods with a stable type-name placeholder.
5. Reject self-references and missing nodes with sorted messages.
6. Build indegrees and prerequisite-to-dependent reverse adjacency, then run
   edge-driven Kahn staging so each outgoing edge is updated once. Sort each
   ready stage and the complete unresolved cycle report.
7. Return a tuple of tuples without mutating caller-owned inputs.

Sorting is a reproducibility requirement: generated HTML and CSS graph
placement must not inherit set, generator, or mapping insertion order.

```json
{
  "version": 1,
  "nodes": [
    {"id": "foundation", "title": "Think", "prerequisites": []},
    {"id": "build", "title": "Build", "prerequisites": ["foundation"]},
    {"id": "operate", "title": "Run", "prerequisites": ["build"]},
    {"id": "lead", "title": "Lead", "prerequisites": ["operate"]}
  ]
}
```

- [ ] **Step 4: Run the graph tests**

Run:

```bash
python3.13 -m unittest tests.test_graph -v
```

Expected at Task 5 completion: all 26 graph and checked-in roadmap contract
tests pass. The count documents this task's reviewed baseline; later roadmap
expansion may add or deliberately replace acceptance tests.

- [ ] **Step 5: Commit deterministic roadmap primitives**

```bash
git add curriculum_builder/graph.py tests/test_graph.py content/roadmap.json
git commit -m "feat: validate deterministic learning roadmaps"
```

### Task 6: Reject unsafe authored HTML and model trusted fragments

**Files:**
- Create: `curriculum_builder/html_safety.py`
- Create: `tests/test_html_safety.py`

- [ ] **Step 1: Write safety boundary tests**

Write `tests/test_html_safety.py` against the public API
`validate_fragment(fragment) -> SafeHtml`. The contract must prove all of the
following before implementation:

- `SafeHtml` is a frozen, slotted, comparable value object whose normal
  constructor always fails; only `validate_fragment()` can issue one.
- The input is an exact, non-empty `str`, preserves the accepted source
  verbatim, allows only tab/LF/CR among C0 controls, and is bounded by both
  character and UTF-8 byte counts.
- Tags and attributes use immutable allowlists. Scriptable/remote-asset
  elements, event handlers, `style`, unknown/duplicate/valueless attributes,
  unsafe class/id tokens, duplicate IDs, invalid table values, and unsupported
  self-closing syntax fail closed.
- The fragment parser rejects comments, declarations, processing instructions,
  malformed markup, stray/mismatched/unclosed tags, excessive nesting,
  excessive attributes, and long attribute values with deterministic errors.
- A conservative content model prevents browser auto-closing, foster
  parenting, and implicit table nodes from changing the validated tree:
  phrasing-only containers, list/description/table parent-child chains,
  leading `summary`, leading `figcaption`, and structural whitespace are all
  checked explicitly.
- `href` is checked after character-reference decoding. Only file-compatible
  path-relative, query-only, or fragment references and HTTPS URLs with a
  valid host are accepted. Root-relative paths, non-HTTPS schemes,
  backslashes, whitespace/control obfuscation, credentials, invalid hosts, and
  invalid ports are rejected.
- Mixed-case markup and encoded schemes are covered. Parser/Unicode failures
  become `CurriculumValidationError`, and error strings never echo the complete
  authored fragment.
- Disallowed element and attribute names use fixed, bounded error messages;
  even an allowlist miss near the fragment-size limit cannot amplify logs or
  disclose an authored marker through the exception string.

- [ ] **Step 2: Run safety tests and verify RED**

Run:

```bash
python3.13 -m unittest tests.test_html_safety -v
```

Expected: import fails because `curriculum_builder.html_safety` does not exist.

- [ ] **Step 3: Implement the bounded fail-closed allowlist parser**

Keep the implementation in `curriculum_builder/html_safety.py` and use only
the Python standard library. Make all public allowlists immutable. Perform
cheap type/empty/size/control checks before parsing, lexically restrict start
and end tag syntax, then use `HTMLParser(convert_charrefs=True)` with an
explicit per-element frame stack, conservative content-model state, and
duplicate-ID set. Use `handle_data()` to reject non-whitespace text in
structural containers so the browser DOM matches the validated tree. Catch
unexpected parser or Unicode exceptions at the trust boundary without
including input content in the error. Construct `SafeHtml` only through a
private issuer after every validation step succeeds; future renderers must
call `validate_fragment()` instead of directly constructing trusted HTML.

- [ ] **Step 4: Run the safety tests**

Run:

```bash
python3.13 -m unittest tests.test_html_safety -v
```

Expected at Task 6 completion: all 31 HTML trust-boundary tests pass.

- [ ] **Step 5: Commit the authored-content trust boundary**

```bash
git add curriculum_builder/html_safety.py tests/test_html_safety.py
git commit -m "feat: reject scriptable lesson fragments"
```

### Task 7: Render file-compatible semantic pages

**Files:**
- Create: `curriculum_builder/render.py`
- Create: `templates/base.html`
- Create: `templates/index.html`
- Create: `templates/catalog.html`
- Create: `templates/roadmap.html`
- Create: `tests/test_render.py`

**Security handoff from Task 6:** renderer tests must reject subclasses or
forged values by requiring `type(value) is SafeHtml` for `content` and every
`html_values` entry. Immediately before raw insertion, re-run
`validate_fragment(value.value)`; the frozen wrapper is a capability boundary,
not permission to trust a stale or deliberately modified payload. Typed HTML
placeholders may appear only in element-body context, never inside a tag,
attribute, comment, script, style, or other parsing context.

After the one base-template substitution, parse the completed document once to
reject duplicate IDs, including collisions between template IDs such as
`main` and content IDs. Keep the CSP's explicit `script-src 'none'`. Do not
otherwise reparse validated HTML or rebuild it through repeated string
concatenation: validate each boundary once, substitute once, and perform only
the required final document-ID pass.

- [ ] **Step 1: Write renderer contracts**

The checked-in `tests/test_render.py` is the authoritative 30-test contract.
It covers structured escaping, exact and freshly revalidated `SafeHtml`,
file-compatible links at three depths, semantic Japanese document landmarks,
and decoded-ID collisions after the single completed-document parse.

The trust-boundary table must exercise both `$name` and `${name}` syntax and
must reject raw or text placeholders in tag-name, comment, script, style, and
unquoted-attribute contexts. Raw placeholders in quoted attributes and
duplicate placeholders in otherwise valid element-body contexts also fail.
The suite additionally pins missing/extra/overlapping keys, invalid template
syntax, one-shot mapping snapshots, type and size bounds, safe output paths,
safe fragment names, template symlink/non-regular/oversize/UTF-8/OSError
failures, working-directory independence, base placeholder counts, CSP and
asset policy, and bounded non-leaking errors. A 10,000-entry custom mapping
must be rejected after consuming no more than `MAX_VALUE_ENTRIES + 1` items;
`items()` acquisition, iteration, and entry decoding failures remain
controlled and never expose their raw exceptions.

Template lexing is linear: closing tags must match the stack top, and stray,
mismatched, unclosed, comment, quote, script, or style states fail before
substitution. A deep-open/repeated-mismatch regression proves processing stops
at the first mismatch without a depth scan. Output paths are capped at 32
directories and 1,024 total characters so relative-root expansion is bounded,
including adversarial 10,000-level paths. Boundary subtests accept depth 32
and length 1,024, reject 33 and 1,025, and verify the 32-level relative-link
prefix.

- [ ] **Step 2: Run renderer tests and verify RED**

Run:

```bash
python3.13 -m unittest tests.test_render -v
```

Expected: import fails because `curriculum_builder.render` does not exist.

- [ ] **Step 3: Implement escaped rendering with path-relative assets**

Implement the contract directly in `curriculum_builder/render.py`; do not keep
a second copy of production code in this plan. Use bounded one-read template
loading with symlink and regular-file checks, snapshot input mappings once,
lex template contexts before substitution, and escape all structured values.
Only an exact `SafeHtml` that succeeds under a fresh `validate_fragment()` may
cross a raw placeholder. Validate each rendered fragment once.

Resolve and pin the template root at construction so later `cwd` changes do
not affect reads. A template read must preserve device, inode, type/mode, size,
`mtime_ns`, and `ctime_ns` from directory-relative stat through open and the
post-read stat. Read exactly the opened size, reject early EOF and any extra
byte, then close the file and directory descriptors in reverse ownership
order.

Validate base placeholder counts and contexts, semantic landmarks, restrictive
CSP, and external or absolute asset policy before accepting the base template.
The document structure is exact and browser-stable: `html` contains
`head` then `body`; head has the four ordered meta records, title, and
stylesheet; body has the skip link, header, main, and footer; header/nav/footer
children and their text are fixed. Direct non-whitespace text, unexpected
parents, browser-auto-closing patterns, closing void elements, missing
children, and reordered or duplicate nodes fail closed. The completed page
receives one additional parse solely to reject decoded duplicate IDs across
the trusted base and validated content.

The 30 test methods include subtest matrices rather than inflating the method
count: swapped, missing, or text-interrupted `html` children; reordered and
missing head/body/header/nav/footer children; direct non-whitespace text in
each container; and a closing tag for a void meta element. Fixed title, skip,
brand, three navigation-link, and footer text each receive an independent
one-character mutation. Every mutation asserts that it changed the canonical
fixture before initializing `Renderer`. Snapshot tests independently alter
`st_dev`, `st_ino`, `st_mode`, `st_size`, `st_mtime_ns`, and `st_ctime_ns` on
both the before-to-opened and opened-to-after transitions. File- and root-close
failure subtests perform the real close first, then prove both descriptors were
handled once in reverse ownership order while returning a controlled error.

The base accepts exactly four meta records: UTF-8 charset, the fixed viewport,
the structured description placeholder, and one CSP. Unknown, duplicate, or
refresh meta records fail closed. The parsed CSP directive map must equal the
declared policy exactly; extra directives such as `script-src-elem` or
`script-src-attr` are forbidden even when `script-src 'none'` remains present.

```html
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="$description">
  <meta http-equiv="Content-Security-Policy"
        content="default-src 'none'; script-src 'none'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'none'; base-uri 'none'; form-action 'none'; object-src 'none'; frame-src 'none'; frame-ancestors 'none'">
  <title>$title · Engineering Expert Curriculum</title>
  <link rel="stylesheet" href="${root}styles.css">
</head>
<body>
  <a class="skip-link" href="#main">本文へ移動</a>
  <header class="site-header">
    <a class="brand" href="${root}index.html">Engineering Atlas</a>
    <nav aria-label="主要ナビゲーション">
      <a href="${root}roadmap/index.html">ロードマップ</a>
      <a href="${root}lessons/index.html">コアレッスン</a>
      <a href="${root}catalog/index.html">全カタログ</a>
    </nav>
  </header>
  <main id="main">$content</main>
  <footer><p>Learn · Practice · Explain · Prove</p></footer>
</body>
</html>
```

Save the following as `templates/index.html`:

```html
<section class="hero reading">
  <p class="eyebrow">Learn · Practice · Explain · Prove</p>
  <h1>地図から入り、教科書として深く学ぶ</h1>
  <p>1,140項目の知識地図と30のコアレッスンで、判断を成果物へ変える。</p>
</section>
```

Save the following as `templates/catalog.html`:

```html
<article>
  <header class="reading">
    <p class="eyebrow">Knowledge Atlas</p>
    <h1>全カタログ</h1>
    <p>$count項目を領域別に掲載しています。ブラウザのページ内検索も利用できます。</p>
  </header>
  <div class="catalog-grid">$sections</div>
</article>
```

Save the following as `templates/roadmap.html`:

```html
<article>
  <header class="reading">
    <p class="eyebrow">Prerequisite Path</p>
    <h1>学習ロードマップ</h1>
    <p>線や色が見えなくても、並びと前提文から関係を理解できます。</p>
  </header>
  <ol class="learning-path">$stages</ol>
</article>
```

- [ ] **Step 4: Run renderer tests and parse the output**

Run:

```bash
python3.13 -m unittest tests.test_render -v
```

Expected at Task 7 completion: all 30 renderer trust-boundary and rendering
tests pass.

- [ ] **Step 5: Commit file-compatible rendering**

```bash
git add curriculum_builder/render.py templates tests/test_render.py
git commit -m "feat: render semantic file-compatible pages"
```

### Task 8: Implement the Hybrid HTML/CSS design system

**Files:**
- Create: `static/styles.css`
- Create: `tests/test_styles.py`

- [ ] **Step 1: Write CSS design contracts**

```python
# tests/test_styles.py
from __future__ import annotations

from pathlib import Path
import unittest


class StyleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.css = Path("static/styles.css").read_text(encoding="utf-8")

    def test_defines_required_design_tokens(self) -> None:
        for token in (
            "--color-paper", "--color-ink", "--color-accent",
            "--space-1", "--measure-reading", "--focus-ring",
        ):
            self.assertIn(token, self.css)

    def test_has_responsive_print_and_focus_contracts(self) -> None:
        self.assertIn("@media (max-width: 48rem)", self.css)
        self.assertIn("@media print", self.css)
        self.assertIn(":focus-visible", self.css)

    def test_roadmap_uses_css_layout_without_animation(self) -> None:
        self.assertIn(".learning-path", self.css)
        self.assertIn("display: grid", self.css)
        self.assertIn(".learning-stage:not(:last-child)::after", self.css)
        self.assertNotIn("@keyframes", self.css)
```

- [ ] **Step 2: Run CSS tests and verify RED**

Run:

```bash
python3.13 -m unittest tests.test_styles -v
```

Expected: `FileNotFoundError` for `static/styles.css`.

- [ ] **Step 3: Add the complete token foundation and critical layouts**

```css
/* static/styles.css */
:root {
  color-scheme: light;
  --color-paper: #f7f3ea;
  --color-surface: #fffdf8;
  --color-ink: #172033;
  --color-muted: #596273;
  --color-border: #d9d1c1;
  --color-accent: #17616b;
  --color-warm: #9b4a2f;
  --color-success: #246b47;
  --space-1: .375rem;
  --space-2: .75rem;
  --space-3: 1.25rem;
  --space-4: 2rem;
  --space-5: 3.5rem;
  --measure-reading: 72ch;
  --measure-wide: 86rem;
  --focus-ring: 3px solid #b33c00;
  font-family: Inter, ui-sans-serif, system-ui, sans-serif;
}

* { box-sizing: border-box; }
html { background: var(--color-paper); color: var(--color-ink); }
body { margin: 0; line-height: 1.65; }
a { color: var(--color-accent); text-underline-offset: .18em; }
a:focus-visible { outline: var(--focus-ring); outline-offset: .2rem; }
.skip-link { position: absolute; left: -999rem; }
.skip-link:focus { left: var(--space-2); top: var(--space-2); z-index: 10; }
.site-header {
  display: flex; justify-content: space-between; gap: var(--space-3);
  padding: var(--space-3); border-bottom: 2px solid var(--color-ink);
}
.site-header nav { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.brand { color: var(--color-ink); font-weight: 800; text-decoration: none; }
main { width: min(100% - 2rem, var(--measure-wide)); margin-inline: auto; }
.reading { max-width: var(--measure-reading); margin-inline: auto; }
.learning-path {
  display: grid; grid-template-columns: repeat(4, minmax(12rem, 1fr));
  gap: var(--space-3); padding: 0; list-style: none;
}
.learning-stage {
  position: relative;
  border-top: .4rem solid var(--color-accent);
}
.learning-stage:not(:last-child)::after {
  content: "";
  position: absolute;
  top: 1.75rem;
  right: calc(var(--space-3) * -1);
  width: var(--space-3);
  border-top: .15rem solid var(--color-warm);
}
.catalog-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
  gap: var(--space-3);
}
footer { margin-top: var(--space-5); padding: var(--space-4); text-align: center; }

@media (max-width: 48rem) {
  .site-header { display: block; }
  .site-header nav { margin-top: var(--space-2); }
  .learning-path { grid-template-columns: 1fr; }
  .learning-stage::after { display: none; }
}

@media print {
  .site-header nav, .skip-link { display: none; }
  html { background: #fff; }
  a { color: inherit; text-decoration: none; }
  a[href^="https://"]::after { content: " (" attr(href) ")"; font-size: .8em; }
}
```

- [ ] **Step 4: Run CSS contracts**

Run:

```bash
python3.13 -m unittest tests.test_styles -v
```

Expected: three tests pass.

- [ ] **Step 5: Commit the static design system**

```bash
git add static/styles.css tests/test_styles.py
git commit -m "feat: add accessible Hybrid CSS design system"
```

### Task 9: Build the landing page, roadmap, and catalog atomically

**Files:**
- Create: `curriculum_builder/build.py`
- Create: `tools/build.py`
- Create: `tests/test_build.py`
- Use: `templates/index.html`
- Use: `templates/catalog.html`
- Use: `templates/roadmap.html`

- [ ] **Step 1: Write the end-to-end build contract**

```python
# tests/test_build.py
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from curriculum_builder.build import build_site


class _Parser(HTMLParser):
    pass


class BuildTests(unittest.TestCase):
    def test_build_is_complete_static_and_file_relative(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "site"
            build_site(
                content_root=Path("content"),
                template_root=Path("templates"),
                static_root=Path("static"),
                output_root=output,
            )
            expected = (
                output / "index.html",
                output / "styles.css",
                output / "catalog" / "index.html",
                output / "roadmap" / "index.html",
            )
            self.assertTrue(all(path.is_file() for path in expected))
            pages = list(output.rglob("*.html"))
            self.assertGreaterEqual(len(pages), 3)
            for page in pages:
                html = page.read_text(encoding="utf-8")
                _Parser().feed(html)
                self.assertNotIn("<script", html.lower())
                self.assertNotIn("javascript:", html.lower())
                self.assertNotIn('href="/', html)
            self.assertEqual(list(output.rglob("*.js")), [])

    def test_failed_build_preserves_previous_output(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "site"
            output.mkdir()
            (output / "sentinel.txt").write_text("previous", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                build_site(root / "missing", Path("templates"), Path("static"), output)
            self.assertEqual(
                (output / "sentinel.txt").read_text(encoding="utf-8"),
                "previous",
            )
```

- [ ] **Step 2: Run build tests and verify RED**

Run:

```bash
python3.13 -m unittest tests.test_build -v
```

Expected: import fails because `curriculum_builder.build` does not exist.

- [ ] **Step 3: Implement deterministic pages and atomic replacement**

```python
# curriculum_builder/build.py
from __future__ import annotations

from collections import defaultdict
from html import escape
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from curriculum_builder.catalog import load_catalog, load_repository_catalog
from curriculum_builder.html_safety import SafeHtml, validate_fragment
from curriculum_builder.render import Renderer


def _catalog_content(items: tuple[object, ...]) -> SafeHtml:
    groups: dict[str, list[object]] = defaultdict(list)
    for item in items:
        groups[item.domain_title].append(item)
    sections = []
    for domain in sorted(groups):
        entries = "".join(
            f'<li id="{escape(item.id.lower())}"><strong>{escape(item.title)}</strong>'
            f'<p>{escape(item.outcome)}</p></li>'
            for item in groups[domain]
        )
        sections.append(f"<section><h2>{escape(domain)}</h2><ol>{entries}</ol></section>")
    return validate_fragment("".join(sections))


def build_site(
    content_root: Path,
    template_root: Path,
    static_root: Path,
    output_root: Path,
) -> None:
    items = load_catalog(content_root / "catalog.json")
    roadmap = json.loads((content_root / "roadmap.json").read_text(encoding="utf-8"))
    renderer = Renderer(template_root)

    # The complete site is intentionally staged in the destination filesystem;
    # readers never observe a half-written catalog if validation or rendering fails.
    output_root.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output_root.parent) as temporary:
        stage = Path(temporary) / "site"
        (stage / "catalog").mkdir(parents=True)
        (stage / "roadmap").mkdir(parents=True)
        shutil.copy2(static_root / "styles.css", stage / "styles.css")
        home = renderer.fragment("index.html", text_values={}, html_values={})
        (stage / "index.html").write_text(
            renderer.page(
                output_path=Path("index.html"),
                title="世界で通用するエンジニアリングを学ぶ",
                description="学び、実践し、説明し、成果で証明する静的OSS教科書",
                content=home,
            ),
            encoding="utf-8",
        )
        catalog = renderer.fragment(
            "catalog.html",
            text_values={"count": f"{len(items):,}"},
            html_values={"sections": _catalog_content(items)},
        )
        (stage / "catalog" / "index.html").write_text(
            renderer.page(
                output_path=Path("catalog/index.html"),
                title="全カタログ",
                description="1,140項目のエンジニアリング知識地図",
                content=catalog,
            ),
            encoding="utf-8",
        )
        nodes = "".join(
            f'<li class="learning-stage"><h2>{escape(node["title"])}</h2></li>'
            for node in roadmap["nodes"]
        )
        roadmap_content = renderer.fragment(
            "roadmap.html",
            text_values={},
            html_values={"stages": validate_fragment(nodes)},
        )
        (stage / "roadmap" / "index.html").write_text(
            renderer.page(
                output_path=Path("roadmap/index.html"),
                title="学習ロードマップ",
                description="前提から実践、運用、リーダーシップへ進む学習経路",
                content=roadmap_content,
            ),
            encoding="utf-8",
        )
        previous = output_root.with_name(f"{output_root.name}.previous")
        if previous.exists():
            raise RuntimeError(f"stale build backup exists: {previous}")
        try:
            if output_root.exists():
                os.replace(output_root, previous)
            os.replace(stage, output_root)
        except BaseException:
            if previous.exists() and not output_root.exists():
                os.replace(previous, output_root)
            raise
        else:
            if previous.exists():
                shutil.rmtree(previous)
```

```python
# tools/build.py
from __future__ import annotations

import argparse
from pathlib import Path

from curriculum_builder.build import build_site


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("site"))
    args = parser.parse_args()
    build_site(Path("content"), Path("templates"), Path("static"), args.output)
    print(f"built {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run build tests and the real build twice**

Run:

```bash
python3.13 -m unittest tests.test_build -v
python3.13 tools/build.py
find site -type f | sort
find site -type f -exec shasum -a 256 {} + > /tmp/curriculum-build-1.sha256
python3.13 tools/build.py
find site -type f -exec shasum -a 256 {} + > /tmp/curriculum-build-2.sha256
diff -u /tmp/curriculum-build-1.sha256 /tmp/curriculum-build-2.sha256
```

Expected: tests pass; the final `diff` has no output.

- [ ] **Step 5: Commit the first complete static site**

```bash
git add curriculum_builder/build.py tools/build.py templates tests/test_build.py
git commit -m "feat: build static curriculum atlas atomically"
```

### Task 10: Verify and execute the non-destructive prototype migration

**Files:**
- Modify locally, not in Git: `$REPO_ROOT/.archive/prototype-v1/`
- Verify: `$REPO_ROOT/.archive/prototype-v1/manifest.json`

- [ ] **Step 1: Prepare and verify the archive parent before migration**

Run:

```bash
python3.13 - <<'PY'
import os
import stat
from pathlib import Path

repository = Path("$REPO_ROOT")
if not repository.is_absolute():
    raise RuntimeError("repository path must be absolute")
if not hasattr(os, "O_NOFOLLOW"):
    raise RuntimeError("safe directory file descriptors are not supported")

flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
descriptors: list[int] = []
operation_error: BaseException | None = None
try:
    current_fd = os.open("/", flags)
    descriptors.append(current_fd)
    for component in repository.parts[1:]:
        current_fd = os.open(component, flags, dir_fd=current_fd)
        descriptors.append(current_fd)
    repository_fd = current_fd

    try:
        os.mkdir(".archive", mode=0o700, dir_fd=repository_fd)
    except FileExistsError:
        pass

    expected = os.stat(".archive", dir_fd=repository_fd, follow_symlinks=False)
    if stat.S_ISLNK(expected.st_mode):
        raise RuntimeError("archive parent must not be a symlink")
    archive_fd = os.open(".archive", flags, dir_fd=repository_fd)
    descriptors.append(archive_fd)
    actual = os.fstat(archive_fd)
    if (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino):
        raise RuntimeError("archive parent changed while opening")
    if not stat.S_ISDIR(actual.st_mode):
        raise RuntimeError("archive parent must be a real directory")
    if actual.st_uid != os.geteuid():
        raise RuntimeError("archive parent must be owned by the current user")
    if actual.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise RuntimeError("archive parent must not be group/world writable")
    # Repair a prior parent-fsync failure on retry: directory before its name holder.
    os.fsync(archive_fd)
    os.fsync(repository_fd)
except BaseException as error:
    operation_error = error
    raise
finally:
    close_failures: list[str] = []
    for descriptor in reversed(descriptors):
        try:
            os.close(descriptor)
        except OSError as error:
            close_failures.append(str(error))
    if close_failures:
        detail = "; ".join(close_failures)
        if operation_error is not None:
            raise RuntimeError(f"archive parent descriptor close failed: {detail}") from operation_error
        raise RuntimeError(f"archive parent descriptor close failed: {detail}")
PY
```

Expected: the parent is a real directory owned by the current user, with no
group/world write permission. The traversal opens every repository component
from `/` with `O_DIRECTORY|O_NOFOLLOW`, so intermediate and final symlinks are
rejected before use. A new parent is created with `0o700` (or a more restrictive
umask result). After validation, every new or existing parent is `fsync`ed
before the repository FD that holds its name. This completes the durability
boundary and repairs a prior repository-`fsync` failure on retry. An existing
unsafe parent is rejected without any `chmod` or other mutation. Any preparation
`fsync` failure aborts before migration. Every opened descriptor is closed even
after an error; close failures are reported rather than retried through a
pathname.

- [ ] **Step 2: Run the complete suite before touching the prototype**

Run:

```bash
python3.13 -m unittest discover -s tests -v
```

Expected: all foundation tests pass.

- [ ] **Step 3: Record the explicit source inventory**

Run:

```bash
python3.13 -c "from tools.migrate_prototype import LEGACY_PATHS; print('\\n'.join(LEGACY_PATHS))"
```

Expected: the eleven approved legacy paths and no `.git`, `docs`, or
`.superpowers` entry.

- [ ] **Step 4: Preserve the prototype**

Run:

```bash
python3.13 tools/migrate_prototype.py \
  --source $REPO_ROOT \
  --archive $REPO_ROOT/.archive/prototype-v1
```

Expected: JSON containing `"status": "preserved"` and a positive `fileCount`.

- [ ] **Step 5: Verify manifest, archive, and Git worktrees**

Run:

```bash
python3.13 -m json.tool \
  $REPO_ROOT/.archive/prototype-v1/manifest.json \
  >/dev/null
git -C $REPO_ROOT status --short --branch
git status --short --branch
```

Expected: the original worktree retains `.git`, `.superpowers`, `.archive`, and
the committed specification; the implementation worktree remains clean.

- [ ] **Step 6: Run the clean build gate and record the foundation checkpoint**

Run:

```bash
python3.13 -m unittest discover -s tests -v
python3.13 tools/build.py
git status --short --branch
```

Expected: all tests pass; only gitignored `site/` is generated; the feature
branch has no uncommitted tracked changes.
# Task 4 import publication security note

Canonical root order is `version`, `generatedFrom`, `sourceSha256`, `items`.
The repository verifier accepts only source `a55a0d0b1cfa3773031e787c2ce7ca0df34534e16a70b65ed1baa91975c82da8`
and artifact `4f38b5f63931a7f06e13f90f5d9ef90a0a435f30dae5d4fe70720d730a057473`.

Task 4 imports with `canonicalize(source, generated_from, source_sha256=actual_sha256)`
and returns exactly `version`, `generatedFrom`, `sourceSha256`, `items`. Generic
`load_catalog` reads bytes once, rejects duplicate/noncanonical JSON, and validates
models. Repository checks use `load_repository_catalog(Path('content/catalog.json'))`:
the same bytes are SHA-256 checked against the artifact hash and their parsed
`sourceSha256` is checked against the source hash above. The writer pins a trusted
directory FD, uses an exclusive private temporary file, fsyncs file then directory,
and never uses parent creation or pathname-based temporary-file helpers.

The importer must use a pinned trusted output directory and verify the published
inode after rename. A same-euid writer at the exact POSIX rename boundary is out
of scope: run imports exclusively; report integrity failure and never rollback a
possibly foreign published entry.
