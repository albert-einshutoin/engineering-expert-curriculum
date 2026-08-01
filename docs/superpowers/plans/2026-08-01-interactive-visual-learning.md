# Interactive Visual Learning vNext Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an accurate CSS diagram to all 30 core lessons and a deterministic, progressively enhanced simulation to the approved 12 lessons without losing no-JS, `file://`, accessibility, security, or reproducible-build guarantees.

**Architecture:** Strict lesson JSON is parsed into immutable Python visualization unions, interleaved with six typed authored-body sections, and rendered as semantic HTML before CSS or JavaScript is considered. A meaning-based CSS kit composes the semantic oracle; one bounded first-party classic script enhances only the 12 approved pages. Exact catalog, CSP, artifact, browser, and deployed-byte contracts fail closed.

**Tech Stack:** Python 3.13 standard library, immutable dataclasses and `StrEnum`, HTML5, CSS3, dependency-free classic JavaScript, `unittest`, headless browser command-line fixtures, GitHub Actions, GitHub Pages.

---

## Scope and execution rules

The schema, renderer, content, runtime, and release gates are coupled by one exact
artifact inventory, so they remain one sequential plan. Each task must leave the
repository's full Python suite green. Temporary compatibility is permitted only
where this plan explicitly says a newly parsed field remains optional until the
final content-enforcement task.

For every task:

1. Record `BASE_SHA=$(git rev-parse HEAD)`.
2. Write the narrow failing test first and run it to observe the expected RED.
3. Implement only the behavior covered by that test.
4. Run focused tests, then `python3.13 -m unittest discover -s tests -v`.
5. Run `git diff --check` and self-review the diff.
6. Commit with the public noreply identity.
7. Run an independent specification review, then an independent code-quality
   review for `BASE_SHA..HEAD`; fix and re-review every Critical or Important
   issue before continuing.

Set the repository-local public identity once before Task 1:

```bash
git config --local user.name 'Engineering Expert Curriculum contributors'
git config --local user.email '75466198+albert-einshutoin@users.noreply.github.com'
```

Every task below supplies its exact commit message.

## Task 0: Freeze the approved specification and reviewed plan

Before recording the Task 1 `BASE_SHA`, stage only the approved design and this
implementation plan, confirm no production file is staged, and commit them as
one reviewed planning baseline:

```bash
git add docs/superpowers/specs/2026-08-01-interactive-visual-learning-design.md docs/superpowers/plans/2026-08-01-interactive-visual-learning.md
git diff --cached --name-only
git commit -m "docs: plan interactive visual learning implementation"
git status --short
```

Expected staged paths are exactly the two paths above and the final status is
empty. Every later range review begins after this planning commit, so approved
requirements cannot be silently mixed into a production task.

## File responsibility map

### New production files

- `curriculum_builder/visualizations.py` — immutable type unions, catalog model,
  exact parsing, cross-reference validation, semantic HTML rendering.
- `curriculum_builder/javascript_safety.py` — conservative UTF-8/size/token and
  forbidden-runtime API validation for the single first-party script.
- `content/visualization-catalog.json` — exact 30 primary/secondary assignments
  and exact 12 kind/mode/static/regression-state assignments.
- `static/visualizations.css` — diagram layout, responsive, print, forced-color,
  reduced-motion, and enhanced-state styles.
- `static/visualization.js` — per-figure transactional progressive enhancement.

### New test and release files

- `tests/test_visualization_models.py` — exact schema and graph invariants.
- `tests/test_visualization_rendering.py` — typed section insertion and ten
  semantic HTML oracles.
- `tests/test_visualization_security.py` — source/script sinks and malicious
  input mutations.
- `tests/test_visualization_runtime.py` — static runtime source and generated DOM
  contracts.
- `tests/test_visualization_accessibility.py` — no-JS, controls, reflow, print,
  forced-colors, and reduced-motion contracts.
- `tests/fixtures/visualization-migration-v1.json` — independent v0.1 captions,
  ordered facts, body residual digests, source projections, and retain/migrate
  outcomes.
- `tests/browser-matrix.json` — exact browser command, version, viewport,
  throttling, fixture hashes, and harness version used for release evidence.
- `tests/browser/runtime-fixture.html` — maximum-bound semantic fixture.
- `tests/browser/runtime-harness.js` — self-running, external test harness that
  instruments forbidden APIs and writes a machine-readable DOM result.
- `tools/run_browser_contract.py` — standard-library browser launcher for
  `file://` and Pages-style loopback subpaths.
- `tools/install_test_browsers.py` — bounded HTTPS download, SHA-256 check, and
  safe extraction of the exact browser archives pinned by the matrix.
- `tools/create_release_manifest.py` — deterministic path/size/SHA-256 manifest.
- `tools/verify_release_manifest.py` — local manifest and artifact verification.
- `tools/verify_deployed_site.py` — bounded HTTPS comparison with the deployed
  Pages artifact.

### Existing integration files

- `curriculum_builder/lessons.py` — source IDs and optional-then-required lesson
  visualization parsing.
- `curriculum_builder/lesson_rendering.py` — production six-section parser and
  typed interleaving.
- `curriculum_builder/render.py` — exact head/CSP/two-CSS/conditional-script
  template contract.
- `curriculum_builder/build.py` — descriptor-pinned catalog/assets, exact output
  inventory, and atomic publication.
- `tools/check_site.py` — `.js`, two stylesheets, conditional script, CSP order,
  local-reference, size, and exact inventory verification.
- `templates/base.html` — CSP-first head, base stylesheet, visual stylesheet,
  renderer-owned conditional deferred script placeholder.
- `templates/lesson.html` — continues to receive one already-interleaved `$body`.
- All `content/lessons/*/lesson.json` — stable source IDs and structured visuals.
- Twenty-nine `content/lessons/*/body.html` plus the primary core-17 figure —
  remove only migrated generic figures; retain the distinct core-17 worked-
  example chart.
- README, contribution, security, content-standard, changelog, PR template, and
  workflows — publish the versioned v0.2.0 contract and evidence requirements.

## Task 1: Implement the immutable visualization domain model

**Files:**
- Create: `curriculum_builder/visualizations.py`
- Create: `tests/test_visualization_models.py`

- [ ] **Step 1: Write RED tests for common fields and all ten payload unions**

Create table-driven tests that call `parse_visualizations()` with one minimal
valid `flow`, `hierarchy`, `comparison`, `state-loop`, `causal`, `timeline`,
`network`, `memory`, `matrix`, and `state-machine` document. The intended public
surface is:

```python
visuals = parse_visualizations(
    raw,
    lesson_id="core-01-systems-tradeoffs",
    complete=False,
    objective_evidence={"obj-system": frozenset({"decision-record"})},
    evidence_ids=frozenset({"decision-record"}),
    source_ids=frozenset({"src-01"}),
)
self.assertIsInstance(visuals[0].payload, CausalPayload)
self.assertEqual(visuals[0].after_section, LessonSectionRole.MENTAL_MODEL)
```

Run:

```bash
python3.13 -m unittest tests.test_visualization_models -v
```

Expected: RED because the module and API do not exist.

- [ ] **Step 2: Add immutable enums, records, and exact parsers**

Implement `StrEnum` values and `@dataclass(frozen=True, slots=True)` records.
Expose exactly:

```python
def parse_visualizations(
    value: object | None,
    *,
    lesson_id: str,
    complete: bool,
    objective_evidence: Mapping[str, frozenset[str]],
    evidence_ids: frozenset[str],
    source_ids: frozenset[str],
) -> tuple[Visualization, ...]: ...
```

Use ASCII IDs matching `[a-z][a-z0-9]*(?:-[a-z0-9]+)*`, the exact bounds from
the approved specification, and exact-object validation. Do not accept raw
class, style, HTML, selector, URL, or coordinate fields.

- [ ] **Step 3: Add RED boundary and graph tests**

Cover unknown/cross-type fields, duplicate IDs, dangling references,
disconnected required nodes, forbidden/required cycles, incomplete comparison
and matrix cells, multiple hierarchy parents, ambiguous simulation transitions,
overlapping parameter `when` mappings, invalid intervals `249`, `5001`, `251`,
and all count/text/Unicode limits.

Expected RED: each mutation is accepted before its validation exists.

- [ ] **Step 4: Implement deterministic invariants and bounded diagnostics**

Use tuple snapshots, stable authored order, `MappingProxyType` only where a map
must be exposed, and O(V+E) validation. Comments must explain why graph
traversal is bounded and why diagnostics never echo arbitrary author values.

- [ ] **Step 5: Verify and commit**

```bash
python3.13 -m unittest tests.test_visualization_models -v
python3.13 -m unittest discover -s tests -v
git add curriculum_builder/visualizations.py tests/test_visualization_models.py
git commit -m "feat: validate immutable lesson visualizations"
```

Expected: focused tests and all existing tests PASS.

## Task 2: Parse typed lesson sections and render semantic visual oracles

**Files:**
- Modify: `curriculum_builder/lesson_rendering.py`
- Modify: `curriculum_builder/lessons.py`
- Modify: `curriculum_builder/visualizations.py`
- Modify: `curriculum_builder/html_safety.py`
- Modify: `curriculum_builder/render.py`
- Create: `tests/test_visualization_rendering.py`
- Modify: `tests/test_lesson_quality.py`
- Modify: `tests/test_lesson_rendering.py`
- Modify: `tests/test_html_safety.py`
- Modify: `tests/test_render.py`
- Modify: `tests/fixtures/complete-lesson.json`
- Modify: `tests/fixtures/incomplete-lesson.json`

- [ ] **Step 1: Write RED tests for the six production section roles**

Test generic IDs and prefixed core-26–30 IDs. The production API is:

```python
body = parse_lesson_body(SIX_SECTION_FRAGMENT)
self.assertEqual(
    tuple(section.role for section in body.sections),
    tuple(LessonSectionRole),
)
```

Also reject missing, reordered, duplicated, seventh top-level, unclosed, and
nested-section impersonation cases.

- [ ] **Step 2: Implement `LessonSection`, `LessonBody`, and one-pass parsing**

Replace `LoadedLesson.body: SafeHtml` with `LessonBody`. Map validated top-level
section order to logical roles; never infer roles from author DOM IDs. Preserve
the original validated section bytes and existing link checks.

- [ ] **Step 3: Write RED semantic-oracle tests for ten visual types**

Assert native output by type: ordered list for flow/timeline, nested list for
hierarchy, definition and relation lists for causal, native tables with scoped
headers for comparison/matrix, a state list plus transition table for
state-machine, and node plus endpoint-naming
relationship lists for network/memory/state-loop. Assert every structured value
is escaped and decorative connectors contain no text.

- [ ] **Step 4: Implement rendering and typed interleaving**

Implement:

```python
def render_lesson_body(
    lesson_id: str,
    body: LessonBody,
    visualizations: tuple[Visualization, ...],
) -> SafeHtml: ...
```

Emit each visual immediately after the complete selected logical section. Keep
`templates/lesson.html`'s single `$body` placeholder. Render the complete static
parameter/state/transition/outcome oracle before any enhancement controls.

Preserve the strict authored-fragment grammar. Add a separate closed generated
HTML grammar and provenance-aware `SafeHtml` revalidation for renderer-owned
native controls; revalidate each capability immediately before substitution and
the final generated document. This is an explicit safety-boundary expansion of
Task 2's file scope, required so valid simulation markup is both publishable and
unable to widen what lesson authors may submit.

- [ ] **Step 5: Integrate optional source IDs and optional visualizations**

Add `Source.id: str | None` and `Lesson.visualizations`. During Tasks 2–6,
legacy sources without IDs and complete lessons without visuals remain accepted;
if a visualization exists, every source ID and objective/evidence relationship
is mandatory and validated. The enforcement switch happens only in Task 7.

- [ ] **Step 6: Verify and commit**

```bash
python3.13 -m unittest tests.test_visualization_rendering tests.test_lesson_quality tests.test_lesson_rendering -v
python3.13 -m unittest discover -s tests -v
git add curriculum_builder/lesson_rendering.py curriculum_builder/lessons.py curriculum_builder/visualizations.py curriculum_builder/html_safety.py curriculum_builder/render.py tests/test_visualization_rendering.py tests/test_lesson_quality.py tests/test_lesson_rendering.py tests/test_html_safety.py tests/test_render.py tests/fixtures/complete-lesson.json tests/fixtures/incomplete-lesson.json
git commit -m "feat: render semantic lesson visualizations"
```

## Task 3: Add the CSS visual system and static asset pipeline

**Files:**
- Create: `static/visualizations.css`
- Modify: `templates/base.html`
- Modify: `curriculum_builder/render.py`
- Modify: `curriculum_builder/build.py`
- Modify: `curriculum_builder/visualizations.py`
- Modify: `curriculum_builder/html_safety.py`
- Modify: `tools/check_site.py`
- Modify: `tests/test_styles.py`
- Modify: `tests/test_render.py`
- Modify: `tests/test_build.py`
- Modify: `tests/test_site_checker.py`
- Create: `tests/test_visualization_accessibility.py`
- Modify: `tests/test_content_acceptance.py`
- Modify: `tests/test_lesson_rendering.py`

- [ ] **Step 1: Write RED tests for the second local stylesheet**

Require `styles.css` plus `${root}static/visualizations.css`, in that order, on
every page. Require stable regular-file input, exact byte copy, 80 KiB maximum,
before/after identity verification, and exact generated inventory. Keep the
v0.1 `script-src 'none'` policy until Task 8.

- [ ] **Step 2: Implement descriptor-pinned asset loading and checker support**

Generalize the existing `styles.css` snapshot path to a closed asset table. Do
not replace it with glob discovery. The expected output paths are exactly:

```python
PurePosixPath("styles.css")
PurePosixPath("static/visualizations.css")
```

Update every independent exact-artifact oracle, including content acceptance
and lesson rendering tests, in the same commit so the second stylesheet cannot
be omitted by one production path while focused asset tests remain green.

- [ ] **Step 3: Write RED CSS semantics and accessibility tests**

Require all ten component classes, logical properties, visible focus, non-color
state markers, `@media (max-width: 20rem)`, `@media (forced-colors: active)`,
`@media (prefers-reduced-motion: reduce)`, and `@media print`. Require that
generated content never supplies essential text and `forced-color-adjust: none`
is absent.

- [ ] **Step 4: Implement the meaning-based CSS kit**

Use a shared `.visualization` base and closed modifiers:

```css
.visualization--flow {}
.visualization--hierarchy {}
.visualization--comparison {}
.visualization--state-loop {}
.visualization--causal {}
.visualization--timeline {}
.visualization--network {}
.visualization--memory {}
.visualization--matrix {}
.visualization--state-machine {}
```

Use Grid/Flexbox and pseudo-element connectors only. At 320px, fall back to one
column and remove layout-dependent connectors. Print expands all semantic
oracles and hides only enhancement controls.

- [ ] **Step 5: Verify and commit**

```bash
python3.13 -m unittest tests.test_styles tests.test_render tests.test_build tests.test_site_checker tests.test_visualization_accessibility -v
python3.13 -m unittest discover -s tests -v
git add static/visualizations.css templates/base.html curriculum_builder/render.py curriculum_builder/build.py tools/check_site.py tests/test_styles.py tests/test_render.py tests/test_build.py tests/test_site_checker.py tests/test_visualization_accessibility.py tests/test_content_acceptance.py tests/test_lesson_rendering.py
git commit -m "feat: add accessible CSS visualization system"
```

## Task 4: Freeze the catalog, legacy-content oracle, and source IDs

**Files:**
- Create: `content/visualization-catalog.json`
- Create: `tests/fixtures/visualization-migration-v1.json`
- Modify: `curriculum_builder/visualizations.py`
- Modify: `curriculum_builder/build.py`
- Modify: all 30 `content/lessons/*/lesson.json`
- Modify: `tests/test_visualization_models.py`
- Modify: `tests/test_content_acceptance.py`
- Modify: `tests/test_build.py`

- [ ] **Step 1: Generate and review an independent v0.1 migration oracle**

Before changing content, record for all 31 existing figures: lesson ID, logical
section role, occurrence, exact caption, ordered visible fact atoms, table cells,
and `migrate`/`retain`. Record the residual body SHA-256 after removing only the
selected primary figure, and the exact ordered `(title, url, kind)` projection
for all 126 sources. Core-17's worked-example chart is `retain`; the 30 primary
figures are `migrate`.

- [ ] **Step 2: Write RED catalog and source-projection tests**

Use this exact catalog root and assignment shape:

```json
{
  "version": 1,
  "lessons": [
    {
      "lessonId": "core-01-systems-tradeoffs",
      "primaryType": "causal",
      "optionalSecondaryType": "matrix",
      "dynamic": false
    },
    {
      "lessonId": "core-02-algorithms-measurement",
      "primaryType": "comparison",
      "optionalSecondaryType": "flow",
      "dynamic": true,
      "simulation": {
        "kind": "complexity-growth",
        "interactionMode": "scenario",
        "staticEquivalentId": "complexity-growth-static",
        "visualRegressionStateIds": [
          "small-input",
          "crossover",
          "large-input"
        ]
      }
    }
  ]
}
```

For dynamic rows require the exact nested `simulation` object shown above;
static rows must omit it. The four simulation fields never appear at row level.
Assert the exact 30 full IDs, primary/secondary values, and approved 12 kind/mode
values from the design specification.

Use these exact dynamic identifiers from the first catalog commit; Tasks 9–11
later make the cross-references live without renaming them:

| Lesson | Static equivalent | Regression states |
| --- | --- | --- |
| core-02 | `complexity-growth-static` | `small-input`, `crossover`, `large-input` |
| core-03 | `memory-access-static` | `tlb-lookup`, `l1-hit`, `memory-return` |
| core-04 | `scheduler-interleaving-static` | `read-old-value`, `lost-update`, `locked-complete` |
| core-05 | `request-path-static` | `dns-lookup`, `tls-ready`, `deadline-exceeded` |
| core-07 | `retry-contract-static` | `request-accepted`, `response-lost`, `retry-replayed` |
| core-12 | `isolation-schedule-static` | `concurrent-read`, `write-skew`, `transaction-retried` |
| core-13 | `distributed-failure-static` | `duplicate-received`, `partition-detected`, `recovery-converged` |
| core-14 | `queue-capacity-static` | `stable-load`, `saturation`, `capacity-recovered` |
| core-15 | `slo-burn-static` | `budget-healthy`, `fast-burn`, `page-triggered` |
| core-16 | `accessible-ui-state-static` | `narrow-viewport`, `keyboard-focus`, `reduced-motion` |
| core-22 | `migration-phase-static` | `expand-ready`, `backfill-paused`, `contract-complete` |
| core-24 | `release-safety-static` | `artifact-verified`, `canary-rejected`, `rollback-complete` |

- [ ] **Step 3: Add stable lesson-local source IDs without changing sources**

Assign current-order `src-01` through `src-05`. Do not renumber or derive IDs
from URLs. Prove the pre/post `(title, url, kind)` projection and order are
identical for all 126 sources.

- [ ] **Step 4: Implement descriptor-pinned catalog parsing**

Expose:

```python
def parse_visualization_catalog_bytes(
    raw: bytes,
    source_name: str,
) -> VisualizationCatalog: ...
```

Enforce exact root/row shapes, full-ID sort order, no duplicates, and closed
assignment enums. Build reads and revalidates the same pinned bytes before
atomic publication; it does not yet require lesson visuals until Task 7.

- [ ] **Step 5: Verify and commit**

```bash
python3.13 -m unittest tests.test_visualization_models tests.test_content_acceptance tests.test_build -v
python3.13 -m unittest discover -s tests -v
git add content/visualization-catalog.json tests/fixtures/visualization-migration-v1.json curriculum_builder/visualizations.py curriculum_builder/build.py tests/test_visualization_models.py tests/test_content_acceptance.py tests/test_build.py content/lessons/core-*/lesson.json
git commit -m "feat: freeze visual assignments and source identity"
```

## Task 5: Migrate causal and network lessons

**Files:**
- Modify lesson JSON/body pairs for core-01, 06, 08, 10, 14, 18, 20, 21, 27, 30
- Modify: `tests/test_content_acceptance.py`
- Modify: `tests/test_capstones.py`
- Modify: `tests/test_core_tracks.py`
- Modify: `curriculum_builder/visualizations.py`
- Modify: `tests/test_visualization_rendering.py`

- [ ] **Step 1: Add RED exact-assignment and legacy-fact tests for the group**

Require primary types:

```text
causal: core-01, core-14, core-18, core-20, core-30
network: core-06, core-08, core-10, core-21, core-27
```

Each visual must reference at least one objective, one reachable evidence ID,
one source ID, and an observable expected result.

When a legacy test fixture converts a complete lesson to draft by removing
complete-only fields, remove `visualizations` in the same fixture transformation
so the test continues to exercise its intended capstone boundary rather than a
new dangling visualization reference.

Update the core-track visual-evidence contract to count retained authored body
figures plus parsed structured visualizations. Move caption mutations to the
structured caption for migrated lessons, while continuing to reject empty
captions and avoiding double-counting core-17's retained worked-example chart.

- [ ] **Step 2: Add structured payloads and remove only migrated figures**

Translate every legacy caption and ordered fact atom into the appropriate
payload plus labelled semantic relations. Keep surrounding paragraphs, asides,
tables, code, and section IDs byte-equivalent to the residual oracle.

When correct typed grouping differs from the legacy list order, store the exact
legacy atoms in ordered `notes` and render that companion oracle before the
typed model. This preserves the original accessible reading order without
misclassifying facts under causal or network headings. Independent Task 5
contracts include every common field, ordered note, item/node/component detail,
and complete labelled relationship, not merely nonempty IDs and labels.

- [ ] **Step 3: Verify no-JS output, source projection, and full suite**

```bash
python3.13 -m unittest tests.test_content_acceptance tests.test_visualization_rendering -v
python3.13 tools/build.py --output site
python3.13 tools/check_site.py --root site --require-current-release
python3.13 -m unittest discover -s tests -v
```

- [ ] **Step 4: Commit**

```bash
git add content/lessons/core-{01,06,08,10,14,18,20,21,27,30}-*/{lesson.json,body.html} curriculum_builder/visualizations.py tests/test_content_acceptance.py tests/test_capstones.py tests/test_core_tracks.py tests/test_visualization_rendering.py
git commit -m "content: add causal and network lesson diagrams"
```

## Task 6: Migrate timeline and state lessons

**Files:**
- Modify lesson JSON/body pairs for core-04, 05, 07, 09, 12, 13, 15, 22, 23, 24, 26, 29
- Modify: `tests/test_content_acceptance.py`

- [ ] **Step 1: Add RED exact-assignment tests**

Require:

```text
timeline: core-04, core-05, core-12, core-13, core-23, core-29
state-machine: core-07, core-22, core-24
state-loop: core-09, core-15, core-26
```

- [ ] **Step 2: Migrate payloads without adding simulations yet**

Encode complete ordered events or allowed/rejected transitions. Dynamic lessons
remain complete static visualizations with `simulation` absent until Tasks 9–11.
Preserve all legacy fact atoms and residual body digests.

- [ ] **Step 3: Verify and commit**

```bash
python3.13 -m unittest tests.test_content_acceptance tests.test_visualization_models tests.test_visualization_rendering -v
python3.13 -m unittest discover -s tests -v
git add content/lessons/core-{04,05,07,09,12,13,15,22,23,24,26,29}-*/{lesson.json,body.html} tests/test_content_acceptance.py
git commit -m "content: add timeline and state lesson diagrams"
```

## Task 7: Migrate the remaining lessons and enforce exact static coverage

**Files:**
- Modify lesson JSON/body pairs for core-02, 03, 11, 16, 17, 19, 25, 28
- Modify: `curriculum_builder/lessons.py`
- Modify: `curriculum_builder/visualizations.py`
- Modify: `curriculum_builder/build.py`
- Modify: `tests/test_content_acceptance.py`
- Modify: `tests/test_lesson_quality.py`
- Modify: `tests/test_build.py`
- Modify: `tests/fixtures/complete-lesson.json`
- Modify: `tests/test_core_tracks.py`

- [ ] **Step 1: Add RED migration tests for remaining primary types**

Require:

```text
comparison: core-02
memory: core-03
matrix: core-11, core-25
flow: core-16, core-17, core-28
hierarchy: core-19
```

Retain core-17's separate worked-example chart unchanged.

- [ ] **Step 2: Migrate content and preserve independent oracles**

Translate primary figures, validate traceability, and keep executable examples
untouched. Confirm all 30 source projections and residual digests.

- [ ] **Step 3: Flip complete-release enforcement to exact 30 coverage**

Complete lessons now require 1–2 visualizations and stable source IDs. Validate
the whole lesson set against `visualization-catalog.json`: exact primary type,
allowed optional secondary, dynamic flag, and no unapproved simulation. Correct
counts with swapped assignments must fail.

Migrate the shared complete-lesson fixture to a minimal valid structured visual
and update the core-track contract to preserve retained authored figures plus
structured visuals. These contract fixtures change in the same commit as the
complete-release switch so they cannot mask a missing production visual.

- [ ] **Step 4: Verify build and commit**

```bash
python3.13 -m unittest tests.test_content_acceptance tests.test_lesson_quality tests.test_build -v
python3.13 tools/build.py --output site
python3.13 tools/check_site.py --root site --require-current-release
python3.13 -m unittest discover -s tests -v
git add content/lessons/core-{02,03,11,16,17,19,25,28}-*/{lesson.json,body.html} curriculum_builder/lessons.py curriculum_builder/visualizations.py curriculum_builder/build.py tests/test_content_acceptance.py tests/test_lesson_quality.py tests/test_build.py tests/fixtures/complete-lesson.json tests/test_core_tracks.py
git commit -m "content: complete semantic diagrams for all lessons"
```

## Task 8: Implement the safe progressive runtime and v0.2 asset contract

**Files:**
- Create: `curriculum_builder/javascript_safety.py`
- Create: `static/visualization.js`
- Modify: `static/visualizations.css`
- Modify: `templates/base.html`
- Modify: `curriculum_builder/render.py`
- Modify: `curriculum_builder/build.py`
- Modify: `tools/check_site.py`
- Create: `tests/test_visualization_security.py`
- Create: `tests/test_visualization_runtime.py`
- Create: `tests/fixtures/visualization-runtime-dom-harness.js`
- Modify: `tests/test_render.py`
- Modify: `tests/test_build.py`
- Modify: `tests/test_site_checker.py`
- Modify: `tests/test_accessibility_contract.py`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/content-standard.md`
- Modify: `SECURITY.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/test_repository_contract.py`
- Modify: `tests/test_content_standard_contract.py`
- Modify: `tests/test_visualization_rendering.py`
- Modify: `tests/test_html_safety.py`
- Modify: `tests/test_competencies.py`
- Modify: `tests/test_content_acceptance.py`
- Modify: `tests/test_lesson_rendering.py`
- Modify: `tests/test_roadmap_acceptance.py`

- [ ] **Step 1: Write RED JS source-safety tests**

Require exact UTF-8, nonempty, <=40 KiB, no control/bidi characters, template
literals, Unicode escapes, remote URL literals, source-map directives, or
forbidden APIs from the design specification. Mutation tests cover `eval`,
`Function`, dynamic import, fetch/XHR/WebSocket/EventSource, Worker/ServiceWorker,
storage/cookie/clipboard, navigation/history, HTML sinks, style injection,
`requestAnimationFrame`, and MutationObserver.

- [ ] **Step 2: Implement conservative first-party JS validation**

Use a bounded lexer that removes ordinary quoted strings and comments while
rejecting malformed/ambiguous syntax. It is a defense-in-depth source contract,
not an AST-security claim. Comments explain why the closed handwritten runtime
and real-browser instrumentation are still required.

- [ ] **Step 3: Write RED runtime behavior tests**

The DOM allowlist is exact. Test transactional initialization, figure-local
state, scenario/stepper/playback/hybrid/explorer controls, reset, timer cleanup,
reduced motion, explicit-action status updates, and full restoration after a
fault at each permitted mutation point.

Execute the actual classic runtime in a dependency-free Node DOM/EventTarget,
timer, and media-query harness. Source-marker assertions are supplementary only;
the required gate drives all five modes, parameter changes, faults, isolation,
and 100 reset cycles and verifies exact DOM/listener/timer restoration.

Extend the renderer-owned generated HTML grammar and visualization renderer with
the exact fixed `data-*` identifiers, state/node/edge identifiers, interaction
mode, interval, and action attributes consumed by the runtime. Keep authored
HTML grammar unchanged. Static oracle content remains complete and controls are
initially hidden/disabled until transactional enhancement succeeds.

Serialize and validate the authored closed transition event on every runtime
edge. Runtime resolution uses the exact tuple `(current state, finite parameter
selection, event)`; `previous`, `next`, `timer`, `parameter-change`, and `reset`
never fall back to raw array position when an authored transition is required.
Condition and control class inventories must equal the corresponding complete
attribute inventories, so a missing attribute cannot silently become an
unconditional node or an ignored enabled control.

- [ ] **Step 4: Implement one dependency-free classic script**

Use a strict IIFE, fixed selectors, `Map`/`Set`, per-figure controller, one owned
timer, fixed state classes, `textContent`, native `hidden`/`disabled`, and the
approved ARIA mutations. Do not use build tooling, modules, network, storage,
runtime layout, or arbitrary selector construction.

Add non-color visual rules for the runtime's fixed enhanced, active, complete,
and error classes, including forced-colors, reduced-motion, focus, and print
behavior. CSS generated content never supplies state text; the semantic DOM
remains the only source of essential status information.

- [ ] **Step 5: Migrate CSP, template, build, and checker atomically**

Use the exact v0.2.0 CSP from the specification. CSP meta is before every
resource-bearing head element. All pages load two CSS files; only approved
simulation pages load exactly one relative `../../static/visualization.js` with
`defer`, no inline body, no `async`, and no module. Allow only exact `.js` path
and inventory.

The JS artifact is present from Task 8 onward. Script tags are derived only from
validated lesson `simulation` data, not the catalog's future `dynamic` flag:
Task 8 has 0 scripted lessons, Task 9 has 5, Task 10 has 9, and Task 11 has 12.
At each intermediate commit, the checker requires exact equality between the
actual simulation-bearing lesson set and the script-bearing page set. Task 11
then enables the final rule that this set exactly equals the catalog's 12
dynamic assignments.

Update the competency artifact inventory from zero JavaScript files to exactly
`static/visualization.js`, while independently requiring zero script-bearing
lesson pages at the Task 8 boundary because no lesson simulation exists yet.
Apply the same exact artifact/page distinction to content, lesson-rendering, and
roadmap acceptance inventories so no independent release oracle retains the
v0.1 zero-JavaScript artifact assumption.

In the same step, replace the current-release “no JavaScript” claim with the
versioned truth: v0.1.0 remains HTML/CSS-only; v0.2.0 remains completely
understandable without JavaScript and may load the one first-party enhancement
on approved simulation lessons. Update security and content-standard contracts
with no network/storage/analytics and the documented meta-CSP clickjacking
limitation. Do not leave documentation claiming a JS-free artifact after the
asset exists.

- [ ] **Step 6: Verify and commit**

```bash
python3.13 -m unittest tests.test_visualization_security tests.test_visualization_runtime tests.test_render tests.test_build tests.test_site_checker tests.test_accessibility_contract -v
python3.13 -m unittest discover -s tests -v
git add curriculum_builder/javascript_safety.py curriculum_builder/render.py curriculum_builder/build.py curriculum_builder/visualizations.py curriculum_builder/html_safety.py static/visualization.js static/visualizations.css templates/base.html tools/check_site.py tests/test_visualization_security.py tests/test_visualization_runtime.py tests/fixtures/visualization-runtime-dom-harness.js tests/test_render.py tests/test_build.py tests/test_site_checker.py tests/test_accessibility_contract.py tests/test_repository_contract.py tests/test_content_standard_contract.py tests/test_visualization_rendering.py tests/test_html_safety.py tests/test_competencies.py tests/test_content_acceptance.py tests/test_lesson_rendering.py tests/test_roadmap_acceptance.py README.md README.en.md docs/content-standard.md SECURITY.md CHANGELOG.md
git commit -m "feat: add safe progressive visualization runtime"
```

## Task 9: Author computation, memory, concurrency, network, and API simulations

**Files:**
- Modify lesson JSON for core-02, 03, 04, 05, 07
- Modify: `tests/test_content_acceptance.py`
- Modify: `tests/test_visualization_runtime.py`

- [ ] **Step 1: Add RED exact-state tests**

Require:

```text
core-02 complexity-growth / scenario
core-03 memory-access / hybrid
core-04 scheduler-interleaving / playback
core-05 request-path / hybrid
core-07 retry-contract / playback
```

Each has finite parameters, deterministic states/transitions/outcomes, complete
static equivalents, initial/branch/recovery regression state IDs, and a
250–5000ms multiple-of-50 interval only for playback-capable modes.

- [ ] **Step 2: Author simulations from existing worked examples**

Use checked-in finite states only. Core-03 distinguishes translation and
transfer without claiming universal latency; core-05 separates DNS/TCP/TLS/
request/retry; core-07 separates side effect from observed response.

- [ ] **Step 3: Verify and commit**

```bash
python3.13 -m unittest tests.test_content_acceptance tests.test_visualization_runtime -v
python3.13 -m unittest discover -s tests -v
git add content/lessons/core-{02,03,04,05,07}-*/lesson.json tests/test_content_acceptance.py tests/test_visualization_runtime.py
git commit -m "content: add foundational system simulations"
```

## Task 10: Author data, distributed, performance, and reliability simulations

**Files:**
- Modify lesson JSON for core-12, 13, 14, 15
- Modify: `tests/test_content_acceptance.py`
- Modify: `tests/test_visualization_runtime.py`

- [ ] **Step 1: Add RED exact-state tests**

Require:

```text
core-12 isolation-schedule / hybrid
core-13 distributed-failure / hybrid
core-14 queue-capacity / scenario
core-15 slo-burn / scenario
```

- [ ] **Step 2: Author finite, explainable scenario tables**

Core-12 covers anomaly/abort/retry; core-13 covers duplicate/reorder/partition/
recovery; core-14 covers offered load/queue/tail/capacity; core-15 covers SLO
window/error budget/burn/response. Static tables reproduce every result.

- [ ] **Step 3: Verify and commit**

```bash
python3.13 -m unittest tests.test_content_acceptance tests.test_visualization_runtime -v
python3.13 -m unittest discover -s tests -v
git add content/lessons/core-{12,13,14,15}-*/lesson.json tests/test_content_acceptance.py tests/test_visualization_runtime.py
git commit -m "content: add data and reliability simulations"
```

## Task 11: Author accessibility, migration, and release simulations

**Files:**
- Modify lesson JSON for core-16, 22, 24
- Modify: `curriculum_builder/visualizations.py`
- Modify: `tests/test_content_acceptance.py`
- Modify: `tests/test_visualization_runtime.py`
- Modify: `tests/test_visualization_accessibility.py`

- [ ] **Step 1: Add RED final-inventory tests**

Require:

```text
core-16 accessible-ui-state / explorer
core-22 migration-phase / playback
core-24 release-safety / playback
```

Require exactly 12 simulations total and reject any missing, extra, swapped
kind/mode, missing static equivalent, or invalid regression-state reference.

- [ ] **Step 2: Author simulations and explicit limitations**

Core-16 demonstrates focus/reflow/motion preference but explicitly says it is
not an assistive-technology emulator. Core-22 includes expand/migrate/contract,
stop, rollback, and compatibility. Core-24 includes source/digest/provenance,
canary, promote, and fail-closed rollback.

- [ ] **Step 3: Enforce exact dynamic coverage and commit**

```bash
python3.13 -m unittest tests.test_content_acceptance tests.test_visualization_runtime tests.test_visualization_accessibility -v
python3.13 -m unittest discover -s tests -v
git add content/lessons/core-{16,22,24}-*/lesson.json curriculum_builder/visualizations.py tests/test_content_acceptance.py tests/test_visualization_runtime.py tests/test_visualization_accessibility.py
git commit -m "content: complete interactive lesson simulations"
```

## Task 12: Add real-browser, accessibility, performance, and leak gates

**Files:**
- Create: `tests/browser-matrix.json`
- Create: `tests/browser/runtime-fixture.html`
- Create: `tests/browser/runtime-harness.js`
- Create: `tools/install_test_browsers.py`
- Create: `tools/run_browser_contract.py`
- Modify: `tests/test_visualization_accessibility.py`
- Modify: `tests/test_visualization_security.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write RED harness contract tests**

Require an exact matrix containing a registry-qualified CI runner image pinned
by OCI digest, architecture, browser archive version/HTTPS URL/SHA-256/executable
path, desktop 1440x900/DPR1/no throttle, mobile 390x844/DPR2/4x throttle, harness
version, and maximum-fixture SHA-256. Reject missing browsers, mutable image
tags without digest, checksum mismatch, and version drift.

The matrix has closed, non-overlapping `linux-x86_64` and `macos-arm64`
platform entries. Linux browser archives are used only inside the digest-pinned
OCI runner; native release smoke on this Darwin arm64 host uses only the macOS
archives and the separately pinned installed Safari version. The installer and
runner derive one exact key from `sys.platform` plus `platform.machine()`, reject
an override that disagrees with the host, reject missing/extra platform keys,
and never fall back across operating systems or architectures.

Add only `/outputs/` to `.gitignore` for generated browser caches, screenshots,
reports, and release-candidate builds. Repository tests require this exact
root-anchored entry and continue to reject broad source-directory ignores.

- [ ] **Step 2: Implement verified browser provisioning**

Resolve the then-current official stable Chromium and Firefox archives once,
download them, calculate and independently re-check SHA-256, then commit the
exact version/URL/digest values to the matrix. `install_test_browsers.py` reads
only that matrix, downloads with Python `urllib` using HTTPS, enforces timeout
and byte ceilings, verifies SHA-256 before extraction, rejects absolute/parent/
link archive entries, and extracts beneath an ignored cache directory named by
the archive hash. CI and local release tests use only those verified binaries.
Safari is not downloaded; the macOS release preflight checks the installed
Safari build against the exact version recorded for that release.

- [ ] **Step 3: Implement a dependency-free browser runner**

Use Python standard-library `subprocess`, `http.server`, loopback ephemeral port,
bounded timeouts, and explicit argument lists. Do not shell-interpolate paths.
Run the external self-test harness over both:

```text
file:///absolute/build/site/lessons/core-02-algorithms-measurement/index.html
http://127.0.0.1:49152/engineering-expert-curriculum/lessons/core-02-algorithms-measurement/index.html
```

The harness instruments forbidden APIs before loading the runtime, performs
native `.click()`/`.change()` actions, records console/CSP/network/storage/
navigation violations, and writes one bounded JSON result into the dumped DOM.

- [ ] **Step 4: Implement performance and leak measurements**

Run 3 warmups plus 20 samples for maximum, memory, and distributed fixtures.
Enforce desktop median <=25ms and 19/20 without >50ms long task; mobile median
<=50ms and p95 <=100ms. After 100 reset cycles require baseline DOM/listener/
timer counts and, when explicit GC is available, retained growth below max(1
MiB, 5%). Unavailable instrumentation is failure.

- [ ] **Step 5: Capture complete browser and visual evidence**

Exercise all 12 pages, all 10 types, and the three catalog regression states
under desktop, narrow, reduced-motion, and forced-colors profiles. Keep generated
screenshots/reports under ignored `outputs/`; do not commit machine-specific
artifacts. Run current stable Chromium, Firefox, and Safari on macOS for release
smoke evidence; an unavailable required browser blocks release.

- [ ] **Step 6: Verify and commit**

```bash
python3.13 -m unittest tests.test_visualization_accessibility tests.test_visualization_security -v
python3.13 tools/build.py --output site
python3.13 tools/install_test_browsers.py --matrix tests/browser-matrix.json --cache outputs/browser-cache
python3.13 tools/run_browser_contract.py --site site --matrix tests/browser-matrix.json
python3.13 -m unittest discover -s tests -v
git add tests/browser-matrix.json tests/browser/runtime-fixture.html tests/browser/runtime-harness.js tools/install_test_browsers.py tools/run_browser_contract.py tests/test_visualization_accessibility.py tests/test_visualization_security.py .gitignore
git commit -m "test: verify visualizations in real browsers"
```

## Task 13: Update public contracts, CI, manifests, and release evidence

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/content-standard.md`
- Modify: `CONTRIBUTING.md`
- Modify: `SECURITY.md`
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml`
- Modify: `curriculum_builder/__init__.py`
- Modify: `CITATION.cff`
- Modify: `.github/pull_request_template.md`
- Modify: `.github/workflows/validate.yml`
- Modify: `.github/workflows/pages.yml`
- Modify: `.github/workflows/codeql.yml`
- Create: `tools/create_release_manifest.py`
- Create: `tools/verify_release_manifest.py`
- Create: `tools/verify_deployed_site.py`
- Create: `tests/test_release_manifest.py`
- Modify: `tests/test_repository_contract.py`
- Modify: `tests/test_repository_security.py`
- Modify: `tests/test_publication_plan_contract.py`
- Modify: `tests/test_site_checker.py`
- Modify: `tools/check_site.py`

- [ ] **Step 1: Write RED documentation and workflow contract tests**

Require v0.1.0 history to remain HTML/CSS-only while v0.2.0 states semantic
no-JS completeness plus optional first-party JS. Require diagram authoring,
traceability, review rubric, no-JS, keyboard, reduced-motion, CSP, deterministic
build, and browser evidence in contribution and PR contracts. CodeQL analyzes
both Python and JavaScript. Require `0.2.0` to match exactly in
`pyproject.toml`, `curriculum_builder.__version__`, `CITATION.cff`, changelog,
and repository version tests, with release date `2026-08-01`.

- [ ] **Step 2: Update public documentation and workflow gates**

Describe exactly what changed, why JavaScript is bounded, what remains local,
and the clickjacking/header residual limitation. CI runs full Python tests,
runtime source checks, deterministic double build, site checker, and pinned
browser contract. The browser job uses the exact OCI image digest recorded in
`tests/browser-matrix.json`, invokes `install_test_browsers.py`, and tests the
verified archive executables; a repository test rejects YAML/matrix drift.
Unknown/failed/zero-target selection runs the full gate.

- [ ] **Step 3: Write RED canonical manifest tests**

The manifest schema is:

```json
{
  "schemaVersion": 1,
  "commit": "0123456789abcdef0123456789abcdef01234567",
  "files": [
    {"path": "index.html", "bytes": 1234, "sha256": "64 lowercase hex"}
  ]
}
```

Require sorted safe relative paths, exact size/hash, HTML/CSS/JS coverage,
manifest self-exclusion, bounded reads/retries/redirects, HTTPS and same-origin/
same-subpath deployment verification.

`verify_deployed_site.py` accepts a manifest URL beneath the validated Pages
base URL, fetches that manifest itself under the same timeout, byte, retry,
redirect-count, same-origin, and same-subpath limits, then verifies every listed
artifact. There is no separate unbounded downloader in the release procedure.

- [ ] **Step 4: Implement manifest generation and verification**

Pages builds once, browser-tests `site-first`, creates the manifest for the
actual commit, uploads that exact directory, deploys it, then compares the
served manifest/hash and every served HTML/CSS/JS byte before claiming success.
Never rebuild between verification and upload. Extend `tools/check_site.py` with
an exact `--with-release-manifest` mode that permits only root
`release-manifest.json` in addition to the normal inventory and validates it
before upload; ordinary builds continue to reject arbitrary JSON artifacts.

- [ ] **Step 5: Verify and commit**

```bash
python3.13 -m unittest tests.test_release_manifest tests.test_repository_contract tests.test_repository_security tests.test_publication_plan_contract -v
python3.13 -m unittest discover -s tests -v
python3.13 tools/build.py --output site
python3.13 tools/check_site.py --root site --require-current-release
python3.13 tools/install_test_browsers.py --matrix tests/browser-matrix.json --cache outputs/browser-cache
python3.13 tools/run_browser_contract.py --site site --matrix tests/browser-matrix.json
python3.13 tools/create_release_manifest.py --root site --commit 0123456789abcdef0123456789abcdef01234567 --output site/release-manifest.json
python3.13 tools/verify_release_manifest.py --root site --manifest site/release-manifest.json
python3.13 tools/check_site.py --root site --require-current-release --with-release-manifest
git add README.md README.en.md docs/content-standard.md CONTRIBUTING.md SECURITY.md CHANGELOG.md pyproject.toml curriculum_builder/__init__.py CITATION.cff .github/pull_request_template.md .github/workflows/validate.yml .github/workflows/pages.yml .github/workflows/codeql.yml tools/create_release_manifest.py tools/verify_release_manifest.py tools/verify_deployed_site.py tools/check_site.py tests/test_release_manifest.py tests/test_repository_contract.py tests/test_repository_security.py tests/test_publication_plan_contract.py tests/test_site_checker.py
git commit -m "docs: publish the interactive visual learning contract"
```

The synthetic 40-hex commit above tests the manifest schema and byte coverage
without falsely claiming that the uncommitted Task 13 tree is represented by
the previous commit. Task 14 regenerates release evidence against each actual
committed candidate HEAD.

## Task 14: Complete final review, PR, merge, Pages verification, and cleanup

**Files:**
- Create: `docs/reviews/2026-08-01-interactive-visual-learning-readiness.md`
- Modify only files required by verified review findings.

- [ ] **Step 1: Run the clean full release gate**

```bash
python3.13 -m compileall -q curriculum_builder tools tests
python3.13 -m unittest discover -s tests -v
python3.13 tools/generate_curriculum_map.py --check
python3.13 tools/build.py --output outputs/release-site-first
python3.13 tools/check_site.py --root outputs/release-site-first --require-current-release
python3.13 tools/build.py --output outputs/release-site-second
python3.13 tools/check_site.py --root outputs/release-site-second --require-current-release
(cd outputs/release-site-first && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256) > /tmp/visual-site-first.sha256
(cd outputs/release-site-second && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256) > /tmp/visual-site-second.sha256
diff -u /tmp/visual-site-first.sha256 /tmp/visual-site-second.sha256
python3.13 tools/install_test_browsers.py --matrix tests/browser-matrix.json --cache outputs/browser-cache
python3.13 tools/run_browser_contract.py --site outputs/release-site-first --matrix tests/browser-matrix.json
FINAL_CANDIDATE_SHA=$(git rev-parse HEAD)
python3.13 tools/create_release_manifest.py --root outputs/release-site-first --commit "$FINAL_CANDIDATE_SHA" --output outputs/release-site-first/release-manifest.json
python3.13 tools/verify_release_manifest.py --root outputs/release-site-first --manifest outputs/release-site-first/release-manifest.json
python3.13 tools/check_site.py --root outputs/release-site-first --require-current-release --with-release-manifest
git diff --check
```

- [ ] **Step 2: Run independent final reviews**

Request whole-range specification, Python, JavaScript, security, accessibility,
content-learning, silent-failure, and code-quality reviews. Fix every Critical
or Important issue with a new failing regression test, rerun the full gate, and
obtain re-review approval. Record reviewer kind honestly.

- [ ] **Step 3: Commit release-readiness evidence**

The review record includes commit, tests, no-JS/file/HTTP/browser evidence,
performance raw report hashes, source/legacy oracles, CSP/security result,
accessibility evidence, unresolved threads, residual risk, and explicit
maintainer decision. Record the reviewed implementation parent SHA explicitly,
then commit only this evidence file:

```bash
git add docs/reviews/2026-08-01-interactive-visual-learning-readiness.md
git commit -m "docs: record interactive visual release readiness"
```

- [ ] **Step 4: Re-run the complete gate on the final feature HEAD**

The readiness commit changes HEAD, so repeat validation and regenerate the
manifest against the final commit before any push:

```bash
python3.13 -m compileall -q curriculum_builder tools tests
python3.13 -m unittest discover -s tests -v
python3.13 tools/generate_curriculum_map.py --check
python3.13 tools/build.py --output outputs/final-release-site-first
python3.13 tools/check_site.py --root outputs/final-release-site-first --require-current-release
python3.13 tools/build.py --output outputs/final-release-site-second
python3.13 tools/check_site.py --root outputs/final-release-site-second --require-current-release
(cd outputs/final-release-site-first && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256) > /tmp/visual-final-site-first.sha256
(cd outputs/final-release-site-second && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256) > /tmp/visual-final-site-second.sha256
diff -u /tmp/visual-final-site-first.sha256 /tmp/visual-final-site-second.sha256
python3.13 tools/install_test_browsers.py --matrix tests/browser-matrix.json --cache outputs/browser-cache
python3.13 tools/run_browser_contract.py --site outputs/final-release-site-first --matrix tests/browser-matrix.json
FINAL_FEATURE_SHA=$(git rev-parse HEAD)
python3.13 tools/create_release_manifest.py --root outputs/final-release-site-first --commit "$FINAL_FEATURE_SHA" --output outputs/final-release-site-first/release-manifest.json
python3.13 tools/verify_release_manifest.py --root outputs/final-release-site-first --manifest outputs/final-release-site-first/release-manifest.json
python3.13 tools/check_site.py --root outputs/final-release-site-first --require-current-release --with-release-manifest
git diff --check
git status --short
```

Expected: every command succeeds and `git status --short` is empty.

- [ ] **Step 5: Push and create a self-contained PR**

Push `feat/interactive-visual-learning`, create a PR whose body explains the
v0.1→v0.2 contract change, architecture, learning value, migration safety,
security boundary, tests, release/version change, and before/after behavior.
Wait for all CI and inspect
unresolved review threads and mergeability independently.

- [ ] **Step 6: Merge and verify the actual deployed artifact**

Merge only when required checks pass and no blocking thread remains. Confirm PR
state is actually `MERGED`, capture merge SHA, and wait for Pages workflow
success.

Confirm the Pages bytes are bound to the merge SHA, not merely a feature or PR
SHA.

Have the bounded deployment verifier fetch the manifest produced by the
successful main workflow and bind it to the actual merge SHA:

```bash
python3.13 tools/verify_deployed_site.py \
  --base-url https://albert-einshutoin.github.io/engineering-expert-curriculum/ \
  --manifest-url https://albert-einshutoin.github.io/engineering-expert-curriculum/release-manifest.json \
  --expected-commit "$MERGE_SHA"
```

- [ ] **Step 7: Create and verify the v0.2.0 release**

First prove `v0.2.0` does not already exist and `public/main` resolves to the
verified merge SHA. Create an annotated tag with the public noreply identity,
push that exact tag, and create a GitHub Release from the checked-in v0.2.0
changelog:

```bash
git fetch public main --tags
test "$(git rev-parse public/main)" = "$MERGE_SHA"
test -z "$(git tag --list v0.2.0)"
git -c user.name='Engineering Expert Curriculum contributors' \
  -c user.email='75466198+albert-einshutoin@users.noreply.github.com' \
  tag -a v0.2.0 "$MERGE_SHA" -m 'Release v0.2.0'
git push public refs/tags/v0.2.0
gh release create v0.2.0 --repo albert-einshutoin/engineering-expert-curriculum \
  --verify-tag --title 'Engineering Expert Curriculum v0.2.0' \
  --notes-file CHANGELOG.md
gh release view v0.2.0 --repo albert-einshutoin/engineering-expert-curriculum \
  --json tagName,targetCommitish,url,isDraft,isPrerelease
```

Verify the remote tag peels to `$MERGE_SHA`, the release is neither draft nor
prerelease, and its URL is public.

- [ ] **Step 8: Clean merged branch without deleting preserved work**

After verified merge and deployment, remove only the merged remote/local
feature branch and this feature worktree. Preserve the earlier
`static-oss-curriculum` worktree, archives, prototypes, and every unrelated user
artifact. Re-fetch and report clean `main`, final merge SHA, Pages URL, and
remaining worktrees.
