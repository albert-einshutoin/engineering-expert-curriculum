# Expert Learning Content Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn 30 cross-cutting engineering topics into a measurable growth path where the learner repeatedly studies, applies, explains, proves, transfers, and reviews engineering judgment.

**Architecture:** Each lesson is an independently validated metadata document plus a semantic body fragment. A shared mastery contract connects objectives to labs, assessments, teach-back prompts, transfer tasks, review intervals, and four-level rubrics; roadmap, competency, and capstone pages are generated from the same content graph.

**Tech Stack:** Python 3.12 standard library, JSON, semantic HTML5, CSS3, `unittest`

---

## Growth model

Every lesson follows the same evidence loop:

```text
Learn → Practice → Explain → Prove → Transfer → Review
  ▲                                                │
  └──────────────── feedback and revision ─────────┘
```

The learner advances through five observable capability levels:

| Level | Evidence |
|---|---|
| Recognize | Identifies the concept and names the relevant constraint |
| Explain | Explains the mechanism and trade-off in their own words |
| Apply | Uses the concept to produce a correct artifact |
| Diagnose | Finds a failure using evidence and rejects plausible wrong causes |
| Lead | Frames the decision, communicates risk, reviews others, and improves the system |

Completion is not a page view. A lesson is complete when the learner can submit
its artifact, teach-back, assessment reasoning, and transfer answer at
`proficient` or better.

## File map

| Path | Responsibility |
|---|---|
| `curriculum_builder/lessons.py` | Lesson metadata loading and quality validation |
| `curriculum_builder/competencies.py` | Versioned framework mapping validation |
| `curriculum_builder/capstones.py` | Capstone coverage and evidence validation |
| `content/lessons/<id>/lesson.json` | Objectives, prerequisites, evidence, sources, and review cycle |
| `content/lessons/<id>/body.html` | Authored textbook explanation and worked example |
| `content/competencies.json` | CS2023, SWEBOK V4.0a, and SFIA 9 mappings |
| `content/capstones/*.json` | Integrated project briefs and rubrics |
| `content/roadmap.json` | Thirty-lesson prerequisite graph and mastery gates |
| `templates/lesson.html` | Textbook lesson presentation |
| `templates/lessons-index.html` | Core curriculum index |
| `templates/competency-matrix.html` | Accessible framework matrix |
| `templates/capstone.html` | Capstone brief and rubric |
| `tests/test_lesson_quality.py` | Complete-lesson quality contract |
| `tests/test_core_tracks.py` | Exact IDs, counts, prerequisites, and track coverage |
| `tests/test_competencies.py` | Framework version and mapping integrity |
| `tests/test_capstones.py` | Three-capstone coverage contract |

### Task 1: Define the lesson-quality domain model

**Files:**
- Create: `curriculum_builder/lessons.py`
- Create: `tests/test_lesson_quality.py`
- Create: `tests/fixtures/complete-lesson.json`
- Create: `tests/fixtures/incomplete-lesson.json`

- [ ] **Step 1: Write the quality-contract tests**

```python
# tests/test_lesson_quality.py
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from curriculum_builder.errors import CurriculumValidationError
from curriculum_builder.lessons import load_lesson


class LessonQualityTests(unittest.TestCase):
    def test_complete_fixture_connects_every_objective_to_evidence(self) -> None:
        lesson = load_lesson(Path("tests/fixtures/complete-lesson.json"))
        self.assertEqual(lesson.status, "complete")
        self.assertEqual(lesson.review_intervals, (1, 7, 30, 90))
        self.assertEqual(
            tuple(item.level for item in lesson.capability_progression),
            ("recognize", "explain", "apply", "diagnose", "lead"),
        )
        evidence_ids = {evidence.id for evidence in lesson.evidence}
        for objective in lesson.objectives:
            self.assertTrue(set(objective.evidence_ids) <= evidence_ids)

    def test_complete_status_rejects_missing_quality_dimensions(self) -> None:
        with self.assertRaisesRegex(
            CurriculumValidationError,
            "complete lesson missing: teachBack, transferTask",
        ):
            load_lesson(Path("tests/fixtures/incomplete-lesson.json"))

    def test_rubric_requires_four_observable_levels(self) -> None:
        raw = json.loads(
            Path("tests/fixtures/complete-lesson.json").read_text(encoding="utf-8")
        )
        del raw["rubric"][0]["levels"]["exemplary"]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "broken-rubric.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(CurriculumValidationError, "rubric levels"):
                load_lesson(path)
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
python3 -m unittest tests.test_lesson_quality -v
```

Expected: import fails because `curriculum_builder.lessons` does not exist.

- [ ] **Step 3: Create the complete fixture**

```json
{
  "version": 1,
  "id": "core-01-systems-tradeoffs",
  "title": "システム思考とエンジニアリングのトレードオフ",
  "summary": "局所最適ではなく制約、フィードバック、二次効果から判断する。",
  "track": "foundations",
  "stage": 1,
  "difficulty": "foundation",
  "estimatedMinutes": 180,
  "prerequisiteIds": [],
  "objectives": [
    {
      "id": "obj-1",
      "statement": "制約と利害関係者を含むシステム境界を図示できる",
      "evidenceIds": ["lab-map", "transfer"]
    },
    {
      "id": "obj-2",
      "statement": "二つ以上の選択肢を可逆性、費用、リスクで比較できる",
      "evidenceIds": ["lab-map", "assessment"]
    },
    {
      "id": "obj-3",
      "statement": "新しい証拠によって判断を更新する条件を説明できる",
      "evidenceIds": ["teach-back", "transfer"]
    }
  ],
  "evidence": [
    {"id": "lab-map", "kind": "artifact", "description": "比較表付き意思決定記録"},
    {"id": "teach-back", "kind": "explanation", "description": "5分の図解説明"},
    {"id": "assessment", "kind": "reasoning", "description": "障害シナリオへの判断根拠"},
    {"id": "transfer", "kind": "transfer", "description": "未知の制約下での再評価"}
  ],
  "capabilityProgression": [
    {
      "level": "recognize",
      "criterion": "制約と利害関係者を特定し、判断対象の境界を示せる",
      "evidenceIds": ["lab-map"]
    },
    {
      "level": "explain",
      "criterion": "選択肢の機構と主要なトレードオフを自分の言葉で説明できる",
      "evidenceIds": ["teach-back"]
    },
    {
      "level": "apply",
      "criterion": "制約に基づく比較を行い、レビュー可能な判断記録を作成できる",
      "evidenceIds": ["lab-map"]
    },
    {
      "level": "diagnose",
      "criterion": "観測した証拠から障害の因果経路を切り分け、反証を示せる",
      "evidenceIds": ["assessment"]
    },
    {
      "level": "lead",
      "criterion": "異なる領域へ判断方法を移し、再評価条件を関係者へ説明できる",
      "evidenceIds": ["transfer"]
    }
  ],
  "lab": {
    "title": "同期処理とキューを比較する",
    "artifact": "decision-record.md",
    "steps": [
      "利用者、運用者、事業の成功条件を列挙する",
      "同期処理とキューの障害経路を図示する",
      "可逆性、遅延、費用、データ損失リスクを比較する",
      "判断と再評価条件を一ページにまとめる"
    ]
  },
  "teachBack": "図だけを使い、選ばなかった案が有利になる条件も5分で説明する。",
  "assessment": [
    {
      "prompt": "平均遅延が改善したのに利用者体験が悪化する因果経路を二つ示す。",
      "expectedEvidence": "境界、遅延分布、再試行、二次効果を関連付けた説明"
    }
  ],
  "transferTask": "医療予約システムという別領域で同じ比較をやり直す。",
  "rubric": [
    {
      "dimension": "technical-correctness",
      "levels": {
        "incomplete": "機構の説明に重大な誤りがある",
        "developing": "主要機構は正しいが境界条件が抜ける",
        "proficient": "機構、境界、失敗条件を正確に説明する",
        "exemplary": "複数層の相互作用と反例まで正確に説明する"
      }
    },
    {
      "dimension": "judgment",
      "levels": {
        "incomplete": "結論だけで制約と代替案がない",
        "developing": "主要制約を挙げるが代替案の反証が弱い",
        "proficient": "代替案、リスク、再評価条件がつながる",
        "exemplary": "二次効果と利害関係者間の緊張まで比較する"
      }
    },
    {
      "dimension": "evidence",
      "levels": {
        "incomplete": "観測可能な証拠がない",
        "developing": "証拠はあるが結論との因果が弱い",
        "proficient": "再現可能な証拠で結論と反証を支える",
        "exemplary": "不確実性と測定限界を含めて証拠を評価する"
      }
    },
    {
      "dimension": "communication",
      "levels": {
        "incomplete": "読者と決定事項が分からない",
        "developing": "結論は伝わるが前提と影響が不足する",
        "proficient": "読者が判断、実行、再評価できる",
        "exemplary": "異なる利害関係者が非同期に合意形成できる"
      }
    }
  ],
  "sources": [
    {
      "title": "NASA Systems Engineering Handbook",
      "url": "https://www.nasa.gov/reference/systems-engineering-handbook/",
      "kind": "primary"
    },
    {
      "title": "ISO/IEC/IEEE 42010 overview",
      "url": "https://www.iso-architecture.org/ieee-1471/",
      "kind": "standard"
    }
  ],
  "review": {
    "intervalDays": [1, 7, 30, 90],
    "prompts": [
      "今回の判断で最も壊れやすい前提は何か",
      "新しい証拠で結論が反転する条件は何か"
    ]
  },
  "updatedAt": "2026-07-30",
  "status": "complete"
}
```

Create `incomplete-lesson.json` from the same object but remove `teachBack` and
`transferTask`.

- [ ] **Step 4: Implement immutable lesson parsing and complete-status gates**

Implement `load_lesson(path: Path)` as a strict trust boundary:

- Accept only the exact native `Path` type, pin a bounded regular-file
  descriptor, reject symbolic links and file changes, and decode strict UTF-8
  JSON with duplicate-key rejection.
- Treat version-controlled lesson files as exclusive-workspace inputs. The
  loader detects symbolic links, persistent pathname rebinding, and leaf content
  changes. Ancestor bindings compare device, inode, and type rather than
  timestamps so unrelated child churn in shared parents does not fail a build.
  It does not use owner or mode bits as an authority decision and does not claim
  a privilege boundary against a concurrent same-euid move-and-restore writer.
- Enforce exact root and nested schemas, exact scalar types (including
  bool-as-int rejection), bounded lists and strings, trimmed/control-safe text,
  ID patterns, uniqueness, and known evidence references.
- Convert every nested value to `@dataclass(frozen=True, slots=True)` plus
  tuples. The public `Lesson` API exposes typed fields such as
  `prerequisite_ids`, `objectives`, `evidence`, `capability_progression`,
  `lab`, `transfer_task`, `rubric`, `sources`, and `review`; it never exposes
  the mutable decoded JSON object.
- For `complete`, require the exact ordered capability progression
  `recognize → explain → apply → diagnose → lead`. Each entry has exact
  `{level, criterion, evidenceIds}` fields, a substantive criterion, and at
  least one unique known evidence reference. This progression is independent
  from the four rubric quality levels and must not be coupled to a particular
  evidence kind.
- A draft may omit `capabilityProgression` or provide a valid non-empty prefix
  of the five levels. A complete lesson also enforces the objective, lab,
  teach-back, assessment, transfer, rubric, source, review, date, stage,
  difficulty, track, and estimate gates defined above.

- [ ] **Step 5: Run tests and commit the mastery contract**

Run:

```bash
python3 -m unittest tests.test_lesson_quality -v
git add curriculum_builder/lessons.py tests/test_lesson_quality.py tests/fixtures
git commit -m "feat: enforce evidence-based lesson mastery"
```

Expected: the complete lesson-quality contract passes and the commit succeeds.

### Task 2: Render textbook lessons and printable review schedules

**Files:**
- Create: `curriculum_builder/lesson_rendering.py`
- Create: `templates/lesson.html`
- Create: `templates/lessons-index.html`
- Create: `tests/test_lesson_rendering.py`
- Modify: `curriculum_builder/build.py`
- Modify: `curriculum_builder/html_safety.py`
- Modify: `curriculum_builder/lessons.py`
- Modify: `static/styles.css`

- [x] **Step 1: Write the lesson rendering test**

```python
# tests/test_lesson_rendering.py
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from curriculum_builder.build import build_site


class LessonRenderingTests(unittest.TestCase):
    def test_build_emits_textbook_and_review_evidence_sections(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "site"
            build_site(Path("content"), Path("templates"), Path("static"), output)
            page = output / "lessons" / "core-01-systems-tradeoffs" / "index.html"
            html = page.read_text(encoding="utf-8")
            self.assertIn("<h1>システム思考", html)
            self.assertIn('id="learning-objectives"', html)
            self.assertIn('id="practice-lab"', html)
            self.assertIn('id="teach-back"', html)
            self.assertIn('id="transfer-task"', html)
            self.assertIn("1日後", html)
            self.assertIn("90日後", html)
```

The test fixture creates complete lessons under a temporary `content_root`;
the canonical content tree intentionally remains empty until Task 3. The
contract also covers empty, one-, and multi-lesson builds, topological links,
hostile metadata escaping, rejected authored markup, source-link policy, input
races, and nested staging failures.

- [x] **Step 2: Run the test and verify RED**

Run:

```bash
python3 -m unittest tests.test_lesson_rendering -v
```

Expected: `FileNotFoundError` for the generated lesson page.

- [x] **Step 3: Add semantic lesson templates and render helpers**

```html
<article class="lesson reading">
  <header>
    <p class="eyebrow">$track · Stage $stage</p>
    <h1>$title</h1>
    <p class="lede">$summary</p>
    <dl class="lesson-meta">
      <dt>学習時間</dt><dd>$estimated_minutes分</dd>
      <dt>難易度</dt><dd>$difficulty</dd>
    </dl>
  </header>
  <section id="learning-objectives">
    <h2>到達目標</h2>$objectives
  </section>
  <section id="capability-progression"><h2>能力の進行</h2>$capabilities</section>
  $body
  <section id="practice-lab"><h2>実践ラボ</h2>$lab</section>
  <section id="teach-back"><h2>説明して理解を確かめる</h2>$teach_back</section>
  <section id="assessment"><h2>アセスメント</h2>$assessment</section>
  <section id="transfer-task"><h2>別問題へ転用する</h2>$transfer_task</section>
  <section id="review-schedule"><h2>復習スケジュール</h2>$review_schedule</section>
  <section id="rubric"><h2>評価ルーブリック</h2>$rubric_table</section>
  <section id="sources"><h2>出典</h2>$sources</section>
</article>
```

Use the foundation plan's `Renderer.fragment()` method.
`curriculum_builder.lesson_rendering` owns sorted descriptor-relative
discovery, the shared `lesson.json`/`body.html` directory snapshot, bounded
exact-byte reads, complete-only graph validation, semantic rendering, and
topological index rendering. `load_lesson_bytes()` parses pinned metadata bytes
without reopening a pathname. Builds require exclusive control of the workspace
namespace; descriptor pinning and before/after signatures detect ordinary and
persistent TOCTOU changes, while exclusivity closes the portable same-writer
ABA gap.

Migrate `templates/lessons.html` to the plan's
`templates/lessons-index.html` name so there is one authoritative index
template. The generated artifact validator permits external navigation only
when the exact lesson source URL appears as an HTTPS
`<a rel="noreferrer">`; all resource dependencies remain local and
JavaScript-free.

- [x] **Step 4: Add the editorial lesson styles**

```css
.lesson { padding-block: var(--space-5); }
.eyebrow { color: var(--color-warm); font-weight: 800; letter-spacing: .08em; }
.lede { font-family: ui-serif, Georgia, serif; font-size: 1.3rem; }
.lesson-meta { display: flex; flex-wrap: wrap; gap: var(--space-3); }
.lesson-meta div, .evidence-panel, .rubric {
  padding: var(--space-3);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
}
.lesson h2 { margin-top: var(--space-5); border-bottom: 1px solid var(--color-border); }
```

Add 320px reflow, visible focus, forced-colors, and print rules. Print CSS may
keep short list and table rows together, but must not mark whole `article`,
`section`, large tables, code blocks, or textbook bodies as unbreakable.

- [x] **Step 5: Run and commit the textbook renderer**

Run:

```bash
python3 -m unittest tests.test_lesson_rendering tests.test_build -v
git add templates curriculum_builder static/styles.css tests/test_lesson_rendering.py
git commit -m "feat: render evidence-based textbook lessons"
```

Expected: focused tests pass.

### Task 3: Author the Foundations track

**Files:**
- Create: `content/lessons/core-01-systems-tradeoffs/{lesson.json,body.html}`
- Create: `content/lessons/core-02-algorithms-measurement/{lesson.json,body.html}`
- Create: `content/lessons/core-03-architecture-memory-caches/{lesson.json,body.html}`
- Create: `content/lessons/core-04-os-processes-concurrency/{lesson.json,body.html}`
- Create: `content/lessons/core-05-networks-latency-failure/{lesson.json,body.html}`
- Modify: `tests/test_core_tracks.py`

- [x] **Step 1: Write the exact Foundations contract**

```python
FOUNDATIONS = {
    "core-01-systems-tradeoffs": {
        "prerequisites": (),
        "artifact": "制約、代替案、反証条件を含む意思決定記録",
        "transfer": "医療予約システムで同じ判断を再実施",
    },
    "core-02-algorithms-measurement": {
        "prerequisites": ("core-01-systems-tradeoffs",),
        "artifact": "計算量予測と実測値の差を説明するベンチマーク報告",
        "transfer": "データ分布が変わる場合のアルゴリズム再選択",
    },
    "core-03-architecture-memory-caches": {
        "prerequisites": ("core-01-systems-tradeoffs",),
        "artifact": "アクセス局所性を変えた測定とCPU・メモリ経路図",
        "transfer": "データ指向設計を別の処理系へ適用",
    },
    "core-04-os-processes-concurrency": {
        "prerequisites": (
            "core-02-algorithms-measurement",
            "core-03-architecture-memory-caches",
        ),
        "artifact": "競合を再現し不変条件で修正した実験記録",
        "transfer": "プロセス分離とスレッド共有の再比較",
    },
    "core-05-networks-latency-failure": {
        "prerequisites": ("core-04-os-processes-concurrency",),
        "artifact": "DNSからHTTPまでの時系列トレースとタイムアウト予算",
        "transfer": "パケット損失と依存遅延を区別する診断",
    },
}


class CoreTrackTests(unittest.TestCase):
    def assert_track(self, contract: dict[str, object]) -> None:
        for lesson_id, expected in contract.items():
            path = Path("content/lessons") / lesson_id / "lesson.json"
            self.assertTrue(path.is_file(), f"missing {path}")
            lesson = load_lesson(path)
            self.assertEqual(lesson.status, "complete")
            if isinstance(expected, dict):
                prerequisites = tuple(expected["prerequisites"])
                artifact = str(expected["artifact"])
                transfer = str(expected["transfer"])
            else:
                prerequisites, artifact = expected
                transfer = None
            self.assertEqual(
                lesson.prerequisite_ids,
                prerequisites,
            )
            self.assertIsNotNone(lesson.lab)
            assert lesson.lab is not None
            self.assertEqual(lesson.lab.artifact, artifact)
            if transfer is not None:
                self.assertEqual(lesson.transfer_task, transfer)
            else:
                self.assertTrue(lesson.transfer_task)
            self.assertEqual(
                tuple(item.level for item in lesson.capability_progression),
                ("recognize", "explain", "apply", "diagnose", "lead"),
            )

    def test_foundations(self) -> None:
        self.assert_track(FOUNDATIONS)
```

Import `Path`, `unittest`, and `load_lesson` at the top of
`tests/test_core_tracks.py`.

- [x] **Step 2: Run the track test and verify RED**

Run:

```bash
python3.13 -m unittest tests.test_core_tracks -v
```

Expected: the Foundations module fails because all five lesson directories are
missing. Run the whole module so canonical body, arithmetic, Big-O, and mutation
contracts cannot be bypassed as the module grows.

- [x] **Step 3: Author each lesson using the complete mastery loop**

For every listed lesson, create `lesson.json` using the Task 1 schema and a
`body.html` containing these exact semantic sections:

```html
<section><h2>なぜ重要か</h2><p>誤判断が利用者、運用、費用へ与える具体的な結果を示す。</p></section>
<section><h2>メンタルモデル</h2><p>対象の境界、状態、因果関係を図と文章で説明する。</p></section>
<section><h2>動く例で考える</h2><p>入力、操作、観測値、結論を再現可能な順序で示す。</p></section>
<section><h2>トレードオフと失敗モード</h2><p>選択肢、成立条件、反証、回復方法を比較する。</p></section>
<section><h2>知識チェック</h2><p>正答だけでなく、誤答がもっともらしく見える理由も説明する。</p></section>
<section><h2>出典と次の学習</h2><p>本文の主張に対応するHTTPS一次資料を二件以上示す。</p></section>
```

Minimum content evidence per lesson: one mechanism diagram expressed as HTML,
one numeric or executable worked example, two plausible-but-wrong diagnoses,
one decision table, one lab artifact, one five-minute teach-back, one novel
transfer scenario, and a four-level rubric.

- [x] **Step 4: Run the focused quality and rendering gates**

Run:

```bash
python3.13 -m unittest \
  tests.test_lesson_quality \
  tests.test_core_tracks \
  tests.test_lesson_rendering -v
```

Expected: all 72 focused tests pass and five lesson pages render. The 72 tests
include every `tests.test_core_tracks` contract, including canonical body,
weighted-score arithmetic, Big-O/Θ, and mutation coverage.

Implementation note (2026-07-31): the Foundations module first failed with five
missing lesson files, then the complete 72-test focused bundle and full suite
passed. An
Important-review follow-up added exact contracts for all 19 source records,
ordered semantic body structure, weighted-score arithmetic, and the Big-O/Θ
distinction. The pre-fix source titles and score failed the exact contracts;
mutations of the first H2 and Big-O definition also failed the canonical
tests. A second review corrected the SPEC reference to the official H1
`SPEC CPU®2017 Run and Reporting Rules`; the old title failed the source
oracle before the lesson metadata was changed. The final full suite passed 334
tests. A quality-review follow-up then added mutation-tested structural
contracts for non-empty captions, scoped table headers, paired diagnosis and
rebuttal items, and executable or numeric worked examples. The old content
failed new contracts for complete experiment fixtures, machine-specific cache
topology, Java memory-model scope, and independently derived build inventory.
After correction, the 76-test focused bundle and all 338 tests passed. A final
quality and security review exposed six more regressions: incomplete lab-step
coverage in five lessons and a build oracle coupled to the production lesson
loader. The old bodies failed executable output contracts, including deletion
of the Java unsafe-code warning, and the forged production-loader result broke
the old inventory oracle. The corrected lessons now execute complete local
harnesses for decisions, algorithms, memory, and networking; the concurrency
harness is statically checked for deterministic barriers, termination, output,
and its safety warning. The independent inventory oracle enumerates canonical
directories and parses standard JSON without the production loader. All four
embedded Python harnesses also ran successfully at their documented defaults.
The final security follow-up first committed failing executable contracts as
`c7b3b13`. The networking harness now bounds lines to 256 bytes, requires a
newline, applies accepted-socket deadlines, validates exact command shapes and
values, deterministically injects connection refusal before socket creation,
and proves server cleanup after malformed input and a controlled handler
exception (`0dc4bc7`). A self-review contract then required an explicit
`main()` lifetime (`2a61e51`); the harness now starts inside `try`, closes in
`finally`, and verifies the non-daemon thread after join (`b6ea86f`). The Java
lab tracks the actual intermediate minimum and
all 200 elapsed samples for each thread mode. Its `process-message` mode
implements an owner child, request-ID deduplication, bounded IPC and exit, and a
separate forced-cleanup failure-radius probe without mixing process startup
cost into the 200 thread trials (`a389c7a`). The optional execution gate
extracted the authored source and passed `javac --release 21` plus all four
public modes using the official OpenJDK Archive macOS/AArch64 build 21.0.2+13-58
from `https://jdk.java.net/archive/`. The downloaded archive matched the
published SHA-256
`b3d588e16ec1e0ef9805d8a696591bd518a5cea62567da8f53b5ce32d11d22e4`
and was used only from a temporary directory. The final 82-test focused bundle
and all 345 tests passed.
Two repository-external builds each emitted 10 regular artifacts, including
five lesson pages and 1,140 catalog items. Both produced aggregate SHA-256
`1c5d384abf74b2192316acf9ae16877d98aaf4fe9af61a797233647646a4b791`:
sort every artifact's UTF-8 relative POSIX path bytewise, then feed
`path + NUL + decimal byte length + NUL + file bytes` to SHA-256. The verifier
included all artifacts and rejected symlinks and non-regular entries.
The initial content was committed as `b385baf`; the review fixes and regression
contracts were committed as `a1e5a94`, `06bad7a`, `2638bec`, `90e44d3`,
`7f0b090`, `fa5de10`, `408e26d`, `9b218cd`, and `4a85b45`.

- [x] **Step 5: Commit the Foundations track**

```bash
git add content/lessons/core-0{1,2,3,4,5}-* tests/test_core_tracks.py
git commit -m "content: teach foundational engineering judgment"
```

### Task 4: Author the Build Trustworthy Software track

**Files:**
- Create: `content/lessons/core-06-requirements-domain-modeling/{lesson.json,body.html}`
- Create: `content/lessons/core-07-api-contract-design/{lesson.json,body.html}`
- Create: `content/lessons/core-08-modularity-evolutionary-architecture/{lesson.json,body.html}`
- Create: `content/lessons/core-09-test-strategy-tdd/{lesson.json,body.html}`
- Create: `content/lessons/core-10-threat-modeling-secure-design/{lesson.json,body.html}`
- Modify: `tests/test_core_tracks.py`
- Modify: `tests/test_build.py`

- [x] **Step 1: Add the exact Build track contract**

```python
BUILD = {
    "core-06-requirements-domain-modeling": (
        ("core-01-systems-tradeoffs",),
        "用語集、境界、例外を含むドメインモデル",
    ),
    "core-07-api-contract-design": (
        ("core-06-requirements-domain-modeling",),
        "互換性、冪等性、失敗形式を含むAPI契約",
    ),
    "core-08-modularity-evolutionary-architecture": (
        ("core-06-requirements-domain-modeling", "core-07-api-contract-design"),
        "変更理由と依存方向を説明するモジュール図とADR",
    ),
    "core-09-test-strategy-tdd": (
        ("core-02-algorithms-measurement", "core-08-modularity-evolutionary-architecture"),
        "RED-GREEN-REFACTOR履歴とリスク別テスト戦略",
    ),
    "core-10-threat-modeling-secure-design": (
        ("core-07-api-contract-design", "core-09-test-strategy-tdd"),
        "資産、境界、攻撃経路、検証を結ぶ脅威モデル",
    ),
}


def test_build(self) -> None:
    self.assert_track(BUILD)
```

- [x] **Step 2: Run the Build track test and verify RED**

Run:

```bash
python3.13 -m unittest tests.test_core_tracks.CoreTrackTests.test_build -v
```

Expected: failure listing five missing Build lessons.

- [x] **Step 3: Author all five lessons against the mastery contract**

Use the same six body sections defined in Task 3. Labs must produce the exact
artifacts in `BUILD`; transfer tasks must respectively cover an unfamiliar
business domain, an offline client, a high-change module, a nondeterministic
defect, and an insider threat. Authoritative sources must include
ISO/IEC/IEEE 29148 or SWEBOK V4.0a, RFC 9110 or OpenAPI, IEEE 42010, primary
testing literature, and NIST SSDF or OWASP guidance as appropriate.

- [x] **Step 4: Run Build track gates**

Run:

```bash
python3.13 -m unittest \
  tests.test_lesson_quality \
  tests.test_core_tracks \
  tests.test_lesson_rendering -v
```

Expected: all tests pass.

- [x] **Step 5: Commit the Build track**

```bash
git add content/lessons/core-{06,07,08,09,10}-* tests/test_core_tracks.py
git commit -m "content: connect software design to trustworthy evidence"
```

**Task 4 evidence (2026-07-31):**

- RED contract commits: `557cfa9`, `ed10dc9`. The first focused run reported
  exactly five missing Build lessons.
- GREEN content commits: `1fd1778`, `7fd6d57`, `e2c2d2e`, `393386c`,
  `1cd0e86`, `d8d02e5`. `1cd0e86` aligns every directory, lesson ID,
  prerequisite, source oracle, and harness oracle with the canonical contract.
- The growing repository inventory exposed a stale fixed-five acceptance
  oracle. `afe5411` keeps it independent from the production loader while
  comparing against raw lesson-directory enumeration, rejecting a forged
  loader-only lesson, and retaining the `core-01` source-count sentinel.
- The review-corrected test counts, security evidence, and sole valid
  deterministic build hash are recorded below. Earlier non-canonical
  file-digest aggregation is not accepted as Task 4 evidence.

**Task 4 review correction evidence (2026-07-31):**

- All commands ran with CPython 3.13.5 via `python3.13` on Darwin 25.5.0
  arm64. The formal Task 4 RED and quality commands above intentionally name
  `python3.13`; an unversioned interpreter is not an accepted condition.
- Review RED commits `8e3c63b`, `8897795`, and `a572593` first exposed the
  Return/overdue, scoped idempotency, computed architecture, typed threat
  validation, and isolated TDD evidence gaps. The pre-fix focused runs failed
  for each missing behavior, including an ambient test that changed the
  nominal GREEN and REFACTOR exits from `[1, 0, 0]` to `[1, 1, 1]`.
- GREEN commits `05e0a89`, `9fcb6dd`, `fc7ef12`, `629eb1d`, and `4fb1c72`
  implement the five review corrections without weakening the original
  contracts. The NASA source is fixed exactly to the official H1
  `Appendix C: How to Write a Good Requirement` and direct page
  `https://www.nasa.gov/reference/appendix-c-how-to-write-a-good-requirement/`.
- Residual-review RED commits `0d4d253`, `ffb1747`, and `1d66de0` then expose
  independent-scenario state counting, ambiguous impact deltas, synthetic
  evidence presented without provenance, partial rating anchors, and
  unvalidated actor/identity/date relationships. GREEN commits `00b8dfd`,
  `db732ca`, and `4f330a7` close those contracts.
- The Build evidence is exactly 10 `unittest` methods, not 11 informal gates.
  The five default harness methods are
  `test_domain_model_harness_traces_rules_and_exceptions`,
  `test_api_contract_harness_models_replay_and_evolution`,
  `test_architecture_harness_exposes_dependencies_and_decision`,
  `test_testing_harness_executes_red_green_refactor_and_mutation`, and
  `test_threat_model_harness_links_assets_controls_and_verification`.
  The five negative/adversarial methods are
  `test_domain_model_rejects_overdue_return_trace_mutation`,
  `test_api_contract_rejects_fingerprint_check_mutation`,
  `test_api_contract_rejects_tenant_scope_mutation`,
  `test_testing_harness_isolates_symlinks_and_ambient_tests`, and
  `test_threat_model_rejects_disabled_validation_mutation`.
- Those methods execute 21 explicit mutation cases: two state/trace source
  mutations in core-06, two contract source mutations in core-07, two impact
  data mutations in core-08, one production-code mutation in core-09, and
  13 model plus one validator-source mutation in core-10. The core-09
  adversarial method separately proves both symlink-victim preservation and
  ambient-test exclusion. The formal Task 4 quality command passes 94 tests,
  and `python3.13 -m unittest discover -s tests` passes all 357 tests.
- Each of two independent repository-external builds contains 15 regular
  artifacts, 14 HTML files, zero JavaScript files, and 483,498 bytes. The
  canonical aggregate algorithm rejects symlinks and non-regular entries,
  encodes every relative POSIX path as UTF-8, sorts those path bytes bytewise,
  then feeds, for every artifact in that order,
  `path bytes + NUL + ASCII decimal byte length + NUL + file bytes` directly
  into one SHA-256 state. Both builds produce
  `f4e4a0e5cd67c9991aee70d7a6d7e3656c5950cd961d9bf7bb7e0c41e3e8339b`.
  No per-file-digest concatenation is used.
- Security scans report zero unsafe HTML, secret, dangerous execution, or body
  external-URL patterns. The catalog remains exactly 1,140 items with SHA-256
  `4f38b5f63931a7f06e13f90f5d9ef90a0a435f30dae5d4fe70720d730a057473`.
  The preserved non-public prototype archive remains independently
  verifiable: 1,194 files, 16,805,630 bytes, and zero manifest SHA-256
  mismatches.

### Task 5: Author the Data and Scale track

**Files:**
- Create: `content/lessons/core-11-data-modeling-storage/{lesson.json,body.html}`
- Create: `content/lessons/core-12-transactions-isolation-consistency/{lesson.json,body.html}`
- Create: `content/lessons/core-13-distributed-coordination-failure/{lesson.json,body.html}`
- Create: `content/lessons/core-14-performance-capacity/{lesson.json,body.html}`
- Create: `content/lessons/core-15-reliability-observability-slo/{lesson.json,body.html}`
- Modify: `tests/test_core_tracks.py`

- [x] **Step 1: Add the exact Data and Scale contract**

```python
DATA_SCALE = {
    "core-11-data-modeling-storage": (
        ("core-06-requirements-domain-modeling",),
        "アクセスパターン、整合性、成長予測を含むストレージADR",
    ),
    "core-12-transactions-isolation-consistency": (
        ("core-11-data-modeling-storage",),
        "二つの分離異常を再現するトランザクション実験",
    ),
    "core-13-distributed-coordination-failure": (
        ("core-05-networks-latency-failure", "core-12-transactions-isolation-consistency"),
        "重複、順序、部分障害を再現する決定的シミュレーション",
    ),
    "core-14-performance-capacity": (
        (
            "core-02-algorithms-measurement",
            "core-03-architecture-memory-caches",
            "core-11-data-modeling-storage",
        ),
        "ボトルネック証拠、負荷曲線、容量限界を含む性能報告",
    ),
    "core-15-reliability-observability-slo": (
        (
            "core-05-networks-latency-failure",
            "core-13-distributed-coordination-failure",
            "core-14-performance-capacity",
        ),
        "利用者ジャーニーから導いたSLI、SLO、アラート、ランブック",
    ),
}


def test_data_scale(self) -> None:
    self.assert_track(DATA_SCALE)
```

- [x] **Step 2: Run the Data and Scale test and verify RED**

Run:

```bash
python3 -m unittest tests.test_core_tracks.CoreTrackTests.test_data_scale -v
```

Expected: five missing lessons.

- [x] **Step 3: Author the five evidence-heavy lessons**

Use the Task 3 section contract. Every worked example must contain measured or
simulated evidence. Transfer tasks must change one hidden assumption: access
pattern, concurrency, network partition, request mix, or user-visible
reliability. Sources must include database vendor documentation or original
papers, RFCs, peer-reviewed distributed-systems work, platform profiling
documentation, and the Google SRE or OpenTelemetry primary materials.

- [x] **Step 4: Run Data and Scale gates**

Run:

```bash
python3.13 -m unittest \
  tests.test_lesson_quality \
  tests.test_lesson_rendering -v
python3.13 -m unittest \
  tests.test_core_tracks.CoreTrackTests.test_data_scale \
  tests.test_core_tracks.CoreTrackTests.test_data_scale_bodies_follow_semantic_contract \
  tests.test_core_tracks.CoreTrackTests.test_storage_harness_compares_models_and_recomputes_adr \
  tests.test_core_tracks.CoreTrackTests.test_storage_harness_rejects_access_pattern_mutation \
  tests.test_core_tracks.CoreTrackTests.test_transaction_harness_reproduces_anomalies_and_retry \
  tests.test_core_tracks.CoreTrackTests.test_transaction_harness_rejects_serializable_check_mutation \
  tests.test_core_tracks.CoreTrackTests.test_coordination_harness_replays_partial_failure \
  tests.test_core_tracks.CoreTrackTests.test_coordination_harness_rejects_same_key_different_payload \
  tests.test_core_tracks.CoreTrackTests.test_coordination_harness_rejects_partition_mutation \
  tests.test_core_tracks.CoreTrackTests.test_performance_harness_separates_simulation_and_measurement \
  tests.test_core_tracks.CoreTrackTests.test_performance_harness_rejects_capacity_mutation \
  tests.test_core_tracks.CoreTrackTests.test_reliability_harness_derives_slo_alerts_and_runbook \
  tests.test_core_tracks.CoreTrackTests.test_reliability_harness_rejects_good_event_mutation -v
```

Expected: all tests pass.

- [x] **Step 5: Commit the Data and Scale track**

```bash
git add content/lessons/core-{11,12,13,14,15}-* tests/test_core_tracks.py
git commit -m "content: teach evidence-driven scale and reliability"
```

**Task 5 evidence (2026-07-31):**

- RED commit `fd7fab8` added the exact metadata, body, mastery-evidence, and
  executable-harness contracts; the first focused run reported exactly five
  missing Data and Scale lessons. Source review RED commit `ee3b751` rejected
  the imprecise PostgreSQL isolation heading, and review RED commit `4ff6fea`
  exposed storage ratings detached from workload frequency, inconsistent
  capacity arithmetic, an untraced Little-law observation, and a hard-coded
  profile result. Final spec-review RED commit `bb373e5` then proved that
  partition mutation failed with an incidental `KeyError`, active concurrency
  was circularly derived, performance had six sources, and reliability lacked
  timestamped independent windows and a journey-only transfer.
- GREEN content commits `cbda1d2`, `2387c10`, `9a29a97`, `f3ab0d5`, and
  `6624daf` implement core-11 through core-15. `b0a0fdb` pins the PostgreSQL 18
  source to `13.2. Transaction Isolation`. Review GREEN commits `60b73c5` and
  `7f1126e` derive storage access-fit ratings from query frequencies, calculate
  projected records and safe capacity from their inputs, and derive the
  reported cProfile function from `pstats`. Final GREEN commits `fc94d74`,
  `6d8338e`, `ddeca86`, and `7687614` add a causal partition diagnostic,
  compare Little's formula with an independent synthetic concurrency input,
  retain exactly five performance sources including Python 3.13 profiler
  documentation, calculate timestamped 5-minute and 60-minute burn windows,
  and compute the search-to-purchase journey-only transfer diff.
- Second-round RED commit `0c94cdd` exposes the remaining causal-evidence and
  print-safety gaps. GREEN commits `94c319e`, `ca078e5`, `a5510fc`, `3e49c39`,
  and `5f40abd` derive all four storage query contributions, reject conflicting
  idempotency-key reuse by typed error, calculate arithmetic means from bounded
  latency samples, derive baseline and transfer knees from separate load
  curves, adopt Semantic Conventions 1.43
  `deployment.environment.name`, calculate correlation and unique-series
  cardinality from fixtures, and preserve complete preformatted text in print.
- The Data and Scale evidence is 13 named `unittest` methods: two metadata/body
  contracts, five default harness executions, five source-mutation rejections,
  and one same-key/different-input conflict rejection. The default harnesses
  change exactly one learning assumption
  each—access pattern, concurrency, partition, request mix, or user-visible
  reliability—and the five negative runs prove the relevant decision changes
  fail closed when causal checks are corrupted. The reliability method also
  executes normal, short-window-only, and both-window failure scenarios and
  requires both burn conditions before paging. All 13 focused methods pass
  with CPython 3.13.5; the separate lesson quality/rendering gate passes 67
  tests, and the CSS gate passes 18 tests. The complete repository suite passes
  all 371 tests.
- Two independent repository-external builds each contain 20 regular
  artifacts, 19 HTML files, zero JavaScript files, and 651,000 bytes. The
  canonical aggregate algorithm encodes each sorted relative POSIX path,
  byte length, and file payload into one SHA-256 state; both builds produce
  `be08916ae2fc368fcfe46864042339ea2c9a96bdd8d782c37f3b5596818736a2`.
- Chrome 150 Letter-PDF regression evidence covers the two longest changed
  harnesses: core-11 renders as 20 pages and core-13 as 22 pages, both at
  612 by 792 points. PDFKit text extraction finds the long-line suffixes, and
  1224 by 1584 page images confirm that preformatted text wraps without
  right-edge clipping.
- Task 5 scans report zero authored-body unsafe-HTML, scoped secret,
  dangerous-execution, and body external-URL matches. The catalog remains
  exactly 1,140 items with SHA-256
  `4f38b5f63931a7f06e13f90f5d9ef90a0a435f30dae5d4fe70720d730a057473`.
  The preserved non-public prototype archive remains independently
  verifiable: 1,194 files, 16,805,630 bytes, and zero manifest SHA-256
  mismatches.

### Task 6: Author the Human and Product Systems track

**Files:**
- Create: `content/lessons/core-16-hci-usability-accessibility/{lesson.json,body.html}`
- Create: `content/lessons/core-17-graphics-visual-information/{lesson.json,body.html}`
- Create: `content/lessons/core-18-product-discovery-experiments/{lesson.json,body.html}`
- Create: `content/lessons/core-19-technical-communication-design-docs/{lesson.json,body.html}`
- Create: `content/lessons/core-20-ethics-privacy-societal-impact/{lesson.json,body.html}`
- Modify: `tests/test_core_tracks.py`

- [x] **Step 1: Add the exact Human and Product contract**

```python
HUMAN_PRODUCT = {
    "core-16-hci-usability-accessibility": (
        ("core-06-requirements-domain-modeling",),
        "キーボード、ズーム、読み上げ、ユーザビリティの監査記録",
    ),
    "core-17-graphics-visual-information": (
        ("core-03-architecture-memory-caches", "core-16-hci-usability-accessibility"),
        "視覚表現と同等のテキスト構造を持つ静的データ図",
    ),
    "core-18-product-discovery-experiments": (
        ("core-06-requirements-domain-modeling", "core-16-hci-usability-accessibility"),
        "反証可能な仮説、成功指標、停止条件を持つ実験計画",
    ),
    "core-19-technical-communication-design-docs": (
        ("core-01-systems-tradeoffs", "core-06-requirements-domain-modeling"),
        "読者別の要約、代替案、リスク、決定を含む設計文書",
    ),
    "core-20-ethics-privacy-societal-impact": (
        (
            "core-10-threat-modeling-secure-design",
            "core-16-hci-usability-accessibility",
            "core-19-technical-communication-design-docs",
        ),
        "影響を受ける人、データライフサイクル、軽減策を含む影響評価",
    ),
}


def test_human_product(self) -> None:
    self.assert_track(HUMAN_PRODUCT)
```

- [x] **Step 2: Run the Human and Product test and verify RED**

Run:

```bash
python3.13 -m unittest tests.test_core_tracks.CoreTrackTests.test_human_product -v
```

Expected: five missing lessons.

- [x] **Step 3: Author the five human-centered lessons**

Use real interfaces and decision scenarios rather than generic advice. The HCI
lab audits this generated curriculum site against WCAG 2.2 AA. The graphics lab
recreates one roadmap and one quantitative chart with semantic HTML/CSS and a
text equivalent. The experiment lab defines guardrail metrics. The
communication lab produces both a one-page executive summary and a technical
appendix. The ethics lab uses the ACM Code of Ethics and NIST Privacy Framework
to identify unevenly distributed harm.

- [x] **Step 4: Run Human and Product gates**

Run:

```bash
python3.13 -m unittest \
  tests.test_lesson_quality \
  tests.test_core_tracks.CoreTrackTests.test_human_product \
  tests.test_lesson_rendering -v
```

Expected: all tests pass.

- [x] **Step 5: Commit the Human and Product track**

```bash
git add content/lessons/core-{16,17,18,19,20}-* tests/test_core_tracks.py
git commit -m "content: integrate human product and ethical judgment"
```

**Task 6 evidence (2026-07-31):**

- RED commit `55fec5b` added only the exact metadata, authoritative-source,
  semantic-body, mastery-evidence, executable-harness, and causal-mutation
  contracts. The first focused run reported exactly five missing
  `lesson.json` files for core-16 through core-20, with no production content
  added before that failure.
- GREEN commits `b27bdfc`, `8fcf6ac`, `84516d6`, `bc12a54`, and `0d9c3e4`
  implement HCI/accessibility, semantic graphics, product experimentation,
  technical communication, and ethics/privacy respectively. Each lesson has a
  local CPython 3.13 JSON harness embedded in the static body, an explicit
  synthetic or simulated provenance and limitation, zero subprocesses, a
  bounded record count, and no external network access.
- The five transfer runs change exactly one hidden assumption each: input mode,
  display mode, guardrail threshold, audience, or affected population. The five
  source-mutation tests corrupt the causal calculation rather than only its
  final JSON and require the lesson-specific diagnostic
  `hci-causal-invariant`, `graphics-causal-invariant`,
  `experiment-causal-invariant`, `communication-causal-invariant`, or
  `ethics-causal-invariant`. The initial 13 named Human and Product methods
  pass:
  metadata, semantic body, standards/practice scope, five default harnesses,
  and five causal negative executions.
- An independent review then reported zero Critical findings and four Important
  evidence gaps: HCI changed an input-mode label without re-observing an
  operation, graphics described HTML/CSS as dictionaries without generating an
  artifact, communication asserted an audience transfer from literals, and
  ethics listed lifecycle phase names without tracing them to harms, controls,
  and residual risks. Tests-only RED commits `1263f5e`, `b26ee49`, and
  `803fa74` reproduce all four classes of defect with eight additional default
  and source-mutation methods.
- Review GREEN commits `d43ed66` and `43d76cb` derive mode-specific HCI
  operations, observations, summaries, and changed dimensions. `0b95c8b`
  generates roadmap and chart HTML/CSS from one fixture, validates the
  resulting node, edge, caption, scope, table-row, and safety structure with
  the standard-library HTML parser, and preserves one data fingerprint across
  color and monochrome artifacts. `7eb2b56` generates executive and implementer
  views from an audience argument while structurally comparing their shared
  decision evidence and reader-specific sections. `0ecc874` validates all
  collect/use/share/retain/delete records and proves complete ID references
  from purpose, necessity, access, retention, and owner through harms,
  controls, and residual risks.
- A second independent review found the HCI worked-example prose lagging behind
  its mode-specific harness and found that the generated graphics artifact was
  still a table without a quantitative visual mark. Tests-only RED commit
  `ad8e161` requires the HCI narrative to state the 3/4 to 2/4 outcome change
  and requires three fixture-derived marks on one normalized 0–100 scale,
  actual color and monochrome presentations, visible values, non-color cues,
  print preservation, and the dedicated `graphics-scale-invariant` mutation
  diagnostic.
- GREEN commit `38f8928` synchronizes the HCI operation, actual, and summary
  explanation. `e8f04aa` adds the visible 40%, 60%, and 100% chart bars, the
  matching semantic table, generated `meter` marks, color styling, and
  monochrome length, pattern, border, and text cues. The first complete-suite
  run then correctly failed closed because the authored body used attributes
  and an element outside the repository HTML allowlist. Commit `d52750a`
  replaces those nodes with policy-valid semantic markup; the build and full
  suite then pass. The final independent review at `d52750a` reports zero
  Critical, Important, or Minor findings.
- A subsequent security review at `ae5b21f` reported zero Critical findings and
  two Important false-green boundaries. An unknown graphics `display_mode`
  could escape a generated CSS selector because it was interpolated before an
  allowlist check, and lifecycle records could preserve unsafe free text for
  over-collection, public access, unlimited retention, or disabled deletion.
  Tests-only RED commit `d5335f5` reproduces the exact
  `x}body{display:none}/*` selector payload, an HTML attribute payload, an
  unknown mode, and all four lifecycle policy violations.
- Security GREEN commit `8737a86` selects class names and CSS only from fixed
  color/monochrome mappings, validates the combined HTML and CSS artifacts, and
  rejects untrusted modes with `graphics-display-mode-invariant`. Commit
  `914fa31` derives the lifecycle fixture from structured inputs and validates
  approved purpose, necessary data classes, forbidden classes, allowed roles,
  bounded retention, delete SLA, and enabled deletion before preserving the
  complete phase-to-harm/control/residual-risk trace. Unsafe policy inputs fail
  with `ethics-lifecycle-policy-invariant`.
- The isolated security re-review of `914fa31` confirmed those two fixes, then
  found one additional Important HTML-validation gap: trusted display mode and
  CSS could still wrap a roadmap containing a `javascript:` or `data:` link
  because the parser checked neither an exact tag nor attribute allowlist.
  Tests-only RED commit `55c7d28` proves both active URL payloads were accepted
  as `valid=True`. GREEN commit `4d59238` restricts artifacts to the exact
  section/figure/list/table/meter tags and per-tag attributes needed by the
  renderer, rejects duplicate attributes, and makes both payloads fail with
  `graphics-artifact-invariant`.
- The final security re-review isolated fixed commit `4d59238` with
  `git archive` and reports zero Critical, Important, or Minor findings.
  Unknown tags, unknown attributes, case-varied duplicate attributes, both
  active URL schemes, all three display-mode payloads, and all lifecycle
  policy violations fail closed while normal color and monochrome artifacts
  remain valid.
- The HCI audit derives keyboard, 200% zoom, reading-order, and usability
  results for the generated static curriculum while distinguishing WCAG 2.2
  Level AA and ISO 9241-210:2019 from the non-standard APCA practice and the
  WCAG 3.0 Working Draft. The graphics artifact keeps roadmap and quantitative
  chart data equivalent across semantic HTML/CSS, text rows, and monochrome
  transfer. The experiment changes only its complaint guardrail and recomputes
  continue to stop. The communication views keep one weighted decision across
  a one-page summary, technical appendix, and validated ADR. The impact
  assessment calculates affected-group inherent and residual risk and exposes
  uneven harm when a high-risk population is added.
- All 32 Human and Product methods now pass, including nineteen
  review-regression
  methods whose bypass mutations fail with
  `hci-input-mode-invariant`, `graphics-artifact-invariant`,
  `graphics-scale-invariant`, `graphics-display-mode-invariant`,
  `communication-audience-invariant`, `ethics-lifecycle-invariant`, or
  `ethics-lifecycle-policy-invariant`.
  The separate lesson quality/rendering gate passes 67 tests, the CSS gate
  passes 19 tests, and the complete repository suite passes all 404 tests.
  Scoped scans report zero authored-body unsafe-HTML, body external-URL,
  secret, and dangerous-execution matches.
- Two consecutive clean builds each contain 25 regular artifacts, 24 HTML
  files, zero JavaScript files, zero symbolic links, and 803,947 bytes. The
  canonical aggregate
  algorithm encodes each sorted relative POSIX path, byte length, and file
  payload into one SHA-256 state; both builds produce
  `fd60c0e046ea685b32ad753d838caf25a782fbb66ecb9e9c80d4ced0fd78baf4`.
- Chrome 150 Letter-PDF evidence covers the two longest final changed bodies:
  core-17 renders as 25 pages and core-20 as 21 pages, both at 612 by 792
  points, tagged and without PDF JavaScript. PDFKit text extraction, with
  printed line-break hyphenation normalized, retains
  `graphics-display-mode-invariant`, `graphics-scale-invariant`,
  `display-monochrome`, `ethics-lifecycle-policy-invariant`,
  `make-expired-personal-data-unavailable`, and
  `affected-population-must-change-risk`, proving both policy boundaries and
  late harness suffixes remain present in print.
- The catalog remains exactly 1,140 items with SHA-256
  `4f38b5f63931a7f06e13f90f5d9ef90a0a435f30dae5d4fe70720d730a057473`.
  The preserved non-public prototype archive remains independently
  verifiable: 1,194 files, 16,805,630 bytes, and zero manifest SHA-256
  mismatches.

### Task 7: Author the Sustain and Operate track

**Files:**
- Create: `content/lessons/core-21-maintenance-legacy-comprehension/{lesson.json,body.html}`
- Create: `content/lessons/core-22-evolution-safe-migrations/{lesson.json,body.html}`
- Create: `content/lessons/core-23-incident-response-learning/{lesson.json,body.html}`
- Create: `content/lessons/core-24-delivery-ci-release-safety/{lesson.json,body.html}`
- Create: `content/lessons/core-25-engineering-economics-capacity/{lesson.json,body.html}`
- Modify: `tests/test_core_tracks.py`

- [x] **Step 1: Add the exact Sustain and Operate contract**

```python
SUSTAIN = {
    "core-21-maintenance-legacy-comprehension": (
        ("core-08-modularity-evolutionary-architecture", "core-09-test-strategy-tdd"),
        "実行経路、変更理由、未知領域を示すシステム地図と特性テスト",
    ),
    "core-22-evolution-safe-migrations": (
        (
            "core-08-modularity-evolutionary-architecture",
            "core-12-transactions-isolation-consistency",
            "core-21-maintenance-legacy-comprehension",
        ),
        "expand-contract段階、観測、停止、ロールバックを含む移行計画",
    ),
    "core-23-incident-response-learning": (
        ("core-15-reliability-observability-slo", "core-21-maintenance-legacy-comprehension"),
        "影響、意思決定、証拠、寄与要因、検証可能な対策を含むレビュー",
    ),
    "core-24-delivery-ci-release-safety": (
        ("core-09-test-strategy-tdd", "core-15-reliability-observability-slo"),
        "失敗を閉じるCI、段階配信、来歴、ロールバックの実行証拠",
    ),
    "core-25-engineering-economics-capacity": (
        (
            "core-14-performance-capacity",
            "core-15-reliability-observability-slo",
            "core-24-delivery-ci-release-safety",
        ),
        "機会費用、運用時間、信頼性、容量を含む投資比較",
    ),
}


def test_sustain(self) -> None:
    self.assert_track(SUSTAIN)
```

- [x] **Step 2: Run the Sustain test and verify RED**

Run:

```bash
python3.13 -m unittest tests.test_core_tracks.CoreTrackTests.test_sustain -v
```

Expected: five missing lessons.

- [x] **Step 3: Author the five lifecycle lessons**

All labs operate on a small supplied legacy fixture so outputs can be reviewed.
Each lesson must distinguish successful command execution from demonstrated
system outcome. Use SWEBOK V4.0a maintenance/operations knowledge areas, NIST
incident guidance, SLSA provenance, DORA delivery evidence, and FinOps or cloud
provider cost guidance as appropriate.

- [x] **Step 4: Run Sustain and Operate gates**

Run:

```bash
python3.13 -m unittest \
  tests.test_lesson_quality \
  tests.test_core_tracks.CoreTrackTests.test_sustain \
  tests.test_lesson_rendering -v
```

Expected: all tests pass.

- [x] **Step 5: Commit the Sustain and Operate track**

```bash
git add content/lessons/core-{21,22,23,24,25}-* tests/test_core_tracks.py
git commit -m "content: teach safe software evolution and operations"
```

#### Task 7 verification evidence

- The initial contract was fixed in RED commits `d2b46f6` and `0743f48`.
  The five canonical lessons were then authored in commits `3a7f5ed`,
  `eaa9771`, `30e3f0b`, `fde6f43`, and `83eb311`. Duplicate template IDs
  were reproduced in `2146bb2` and fixed in `ffb7e01`.
- False-green mutations were added before every corrective implementation.
  Commits `c2054fe`, `538b4d5`, `2d2ef93`, `e70f6de`, `28159a3`,
  `e8e9ada`, and `ef5a0a2` cover independent expected observations,
  full transfer snapshots, symmetric missing/unknown/type/nested/multiple
  changes, canonical migration phases, evidence chronology and uniqueness,
  provenance and artifact identity, and main-first input validation.
  Commits `6b12931` and `3dcd265` additionally prove that known invariant
  failures produce one typed diagnostic line without exposing a Python
  traceback, while unexpected exceptions remain uncaught.
- The broad Task 7 gate selects every `CoreTrackTests` method beginning with
  `test_sustain`, `test_legacy`, `test_migration`, `test_incident`,
  `test_delivery`, or `test_economics`; all 48 tests pass. The specified
  lesson quality, Sustain contract, and rendering gate passes all 68 tests.
  The complete repository suite passes all 452 tests.
- Two consecutive clean builds each contain 30 regular artifacts, 29 HTML
  files, zero JavaScript files, zero symbolic links, zero special nodes, and
  965,247 bytes. The canonical aggregate algorithm encodes each sorted
  relative POSIX path, byte length, and payload; both builds produce
  `39426ef6fa5a2c2bbbde780eb0792936fb0e025da81daa79331860d146aff327`.
- Chrome 150 Letter-PDF evidence covers core-21 and core-22. Both render as
  18 pages at 612 by 792 points, are tagged, and contain no PDF JavaScript.
  PDFKit text extraction retains
  `maintenance-comprehension-invariant`, `fixture snapshot drift`,
  `affected path`, `migration-causal-invariant`,
  `migration-transfer-invariant`, `migration-plan-invariant`,
  `migration-rollback-outcome-invariant`, `reader compatibility`,
  `dual write`, `rollback`, and `backfill error rate`.
- Independent quality review of fixed commit
  `3dcd2657df031aca7d6ad8fa7395c628dc20638d` concluded
  Critical 0 / Important 0 / Minor 0. Fifteen expanded malformed-input
  mutations fail closed with lesson-specific diagnostics and no false-green
  system outcome. A separate security review also concluded
  Critical 0 / Important 0 / Minor 0.
- Security verification reports zero authored-body active markup, unsafe
  attributes or schemes, duplicate IDs, forbidden harness imports or calls,
  and generated CSP violations. Gitleaks scanned 37 commits from `4323422`
  through `3dcd265` and found no leaks. Symlinked output is rejected while
  preserving the existing sentinel.
- The catalog remains exactly 1,140 unique items with SHA-256
  `4f38b5f63931a7f06e13f90f5d9ef90a0a435f30dae5d4fe70720d730a057473`.
  The preserved non-public prototype archive remains unchanged and
  independently verifiable: 1,194 files, 16,805,630 bytes, and zero missing,
  extra, hash-mismatched, unsafe-path, symbolic-link, or special-node entries.

### Task 8: Author the Lead and Contribute track

**Files:**
- Create: `content/lessons/core-26-code-review-collaborative-quality/{lesson.json,body.html}`
- Create: `content/lessons/core-27-team-interfaces-sociotechnical-architecture/{lesson.json,body.html}`
- Create: `content/lessons/core-28-oss-governance-stewardship/{lesson.json,body.html}`
- Create: `content/lessons/core-29-cross-cultural-async-collaboration/{lesson.json,body.html}`
- Create: `content/lessons/core-30-evidence-based-technical-leadership/{lesson.json,body.html}`
- Modify: `tests/test_core_tracks.py`

- [x] **Step 1: Add the exact Lead and Contribute contract**

```python
LEAD = {
    "core-26-code-review-collaborative-quality": (
        ("core-09-test-strategy-tdd", "core-19-technical-communication-design-docs"),
        "優先度、根拠、修正可能性を備えたレビューと改善後の再評価",
    ),
    "core-27-team-interfaces-sociotechnical-architecture": (
        (
            "core-08-modularity-evolutionary-architecture",
            "core-19-technical-communication-design-docs",
            "core-26-code-review-collaborative-quality",
        ),
        "所有権、依存、認知負荷、SLOを含むチームインターフェース",
    ),
    "core-28-oss-governance-stewardship": (
        (
            "core-10-threat-modeling-secure-design",
            "core-19-technical-communication-design-docs",
            "core-26-code-review-collaborative-quality",
        ),
        "第三者が貢献からリリースまで完遂できるOSSリポジトリ",
    ),
    "core-29-cross-cultural-async-collaboration": (
        ("core-19-technical-communication-design-docs", "core-27-team-interfaces-sociotechnical-architecture"),
        "時差、言語、文脈差を越える非同期RFCと決定ログ",
    ),
    "core-30-evidence-based-technical-leadership": (
        (
            "core-20-ethics-privacy-societal-impact",
            "core-25-engineering-economics-capacity",
            "core-27-team-interfaces-sociotechnical-architecture",
            "core-28-oss-governance-stewardship",
            "core-29-cross-cultural-async-collaboration",
        ),
        "戦略、指標、リスク、投資順、撤退条件を含む技術方針",
    ),
}


def test_lead(self) -> None:
    self.assert_track(LEAD)
```

- [x] **Step 2: Run the Lead test and verify RED**

Run:

```bash
python3.13 -m unittest tests.test_core_tracks.CoreTrackTests.test_lead -v
```

Expected: five missing lessons.

- [x] **Step 3: Author the five leadership lessons**

Each lab must involve reviewing or enabling another contributor, not only
producing an individual artifact. The OSS lesson uses this repository as the
working example. The async collaboration lesson requires a context-complete
decision that can be reviewed without a meeting. The final leadership lesson
requires explicit metrics, dissent, uncertainty, ethics, cost, and a reversible
first step.

- [x] **Step 4: Run Lead and Contribute gates**

Run:

```bash
python3.13 -m unittest \
  tests.test_lesson_quality \
  tests.test_core_tracks.CoreTrackTests.test_lead \
  tests.test_lesson_rendering -v
```

Expected: all tests pass.

- [x] **Step 5: Commit the Lead and Contribute track**

```bash
git add content/lessons/core-{26,27,28,29,30}-* tests/test_core_tracks.py
git commit -m "content: develop collaborative technical leadership"
```

#### Task 8 verification evidence

- Tests-only RED commit `8a44715` fixed the Lead contract before the lessons
  existed. The five canonical lessons were then authored in commits `e69cc4b`,
  `8faf58a`, `65c5079`, `1c9f839`, and `698465c`; `bf11c2c` keeps the Lead
  fixtures isolated from the preceding Sustain track.
- Independent quality review of that first complete implementation reported
  zero Critical, five Important, and one Minor finding. Tests-only RED commit
  `c1f06ba` reproduces all five false-green boundaries: simulated rather than
  observed review outcomes, partial team-interface transfer, a non-causal
  async window, conflated required and observed release evidence, and a
  leadership selection detached from its ranking. Before the fixes, the six
  focused methods fail with five errors and three subtest failures.
- GREEN commits `83d8dde`, `e8e666d`, `381a56e`, `4764b81`, and `0889a3b`
  make both review cycles apply and verify actual patches, recompute the team
  interface and contributor enablement together, distinguish required
  approval from observed verified evidence, derive overlap and response
  windows from participant availability, and derive strategy ranking and
  selection from the same context. Commit `3ecaa0d` pins the Task 8 commands
  to Python 3.13.
- At fixed implementation commit
  `e8e666d843a1268f7c84104ff47e7a5e5c1e9c17`, the six review-regression
  methods pass. The specified lesson quality, Lead contract, and rendering
  gate passes all 68 tests; all 142 core-track tests pass; and the complete
  repository suite passes all 474 tests.
- Two consecutive clean builds each contain 35 regular artifacts, 34 HTML
  files, one CSS file, zero JavaScript files, 30 lesson pages, and 1,140,849
  bytes. The canonical aggregate algorithm encodes each sorted relative POSIX
  path, byte length, and payload; both builds produce
  `1ddb29d7f40ef9bfb84395ca1c9dabf9d7e96debdea3ec2a8a987b1abca753d2`.
- Chrome 150 Letter-PDF evidence covers the two longest final Lead bodies:
  core-26 renders as 24 pages and core-28 as 23 pages, both at 612 by 792
  points, tagged, and without PDF JavaScript. PDFKit text extraction retains
  the actual-outcome, independent-reevaluation, transfer, observed-approval,
  and provenance boundaries through the late harness suffixes.
- The same quality reviewer rechecked every original finding against the fixed
  HEAD and concluded Critical 0 / Important 0 / Minor 0. A separate security
  delta review of `bf11c2c..e8e666d` also concluded Critical 0 / Important 0 /
  Minor 0 after 230 related tests, an isolated build, static HTML inspection,
  and a seven-commit gitleaks scan.
- Security verification reports zero authored-body script or style elements,
  unsafe attributes, unsafe URL schemes, external authored URLs, or per-page
  duplicate IDs. All 34 generated HTML pages carry CSP and contain no script
  element. Gitleaks also scanned the complete 14-commit Task 8 implementation
  range and found no leaks.
- The catalog remains exactly 1,140 unique items with SHA-256
  `4f38b5f63931a7f06e13f90f5d9ef90a0a435f30dae5d4fe70720d730a057473`.
  The preserved non-public prototype archive remains independently
  verifiable: 1,194 files, 16,805,630 bytes, and zero missing, extra,
  hash-mismatched, unsafe-path, symbolic-link, or special-node entries.

### Task 9: Replace the stage placeholder with the 30-lesson roadmap

**Files:**
- Modify: `content/roadmap.json`
- Modify: `tests/test_core_tracks.py`
- Modify: `curriculum_builder/build.py`
- Create: `tests/test_roadmap_acceptance.py`

Tasks 2–8 intentionally accept an absent, empty, or partial `content/lessons`
tree as an authoring state. Task 9 is the release/roadmap gate: its acceptance
tests must require exactly 30 complete lessons with the unique ordinals 1–30,
and must reject a roadmap or release build that omits or duplicates any one of
them. Keep this exact-count release requirement out of the Task 2 loader so
incremental authoring and the meaningful empty state remain available.

- [x] **Step 1: Write the complete roadmap acceptance test**

```python
# tests/test_roadmap_acceptance.py
from __future__ import annotations

import json
from pathlib import Path
import unittest

from curriculum_builder.graph import topological_stages


class RoadmapAcceptanceTests(unittest.TestCase):
    def test_all_thirty_lessons_are_reachable_and_acyclic(self) -> None:
        raw = json.loads(Path("content/roadmap.json").read_text(encoding="utf-8"))
        ids = tuple(node["id"] for node in raw["nodes"])
        prerequisites = {
            node["id"]: tuple(node["prerequisiteIds"])
            for node in raw["nodes"]
        }
        stages = topological_stages(ids, prerequisites)
        self.assertEqual(len(ids), 30)
        self.assertEqual(set().union(*map(set, stages)), set(ids))
        self.assertEqual(stages[0], ("core-01-systems-tradeoffs",))

    def test_mastery_gates_have_reviewable_outputs(self) -> None:
        raw = json.loads(Path("content/roadmap.json").read_text(encoding="utf-8"))
        self.assertEqual(
            [gate["id"] for gate in raw["masteryGates"]],
            ["foundation", "builder", "scaler", "human", "operator", "leader"],
        )
        self.assertTrue(all(gate["artifact"] and gate["review"] for gate in raw["masteryGates"]))
```

- [x] **Step 2: Run the roadmap test and verify RED**

Run:

```bash
python3.13 -m unittest tests.test_roadmap_acceptance -v
```

Expected: failure because the placeholder roadmap has four non-lesson nodes.

- [x] **Step 3: Write the canonical roadmap**

Populate `content/roadmap.json` with the exact prerequisites from Tasks 3–8 and
six mastery gates:

```json
{
  "masteryGates": [
    {"id": "foundation", "after": 5, "artifact": "未知システムの診断記録", "review": "機構と証拠を説明できる"},
    {"id": "builder", "after": 10, "artifact": "契約・テスト・脅威モデル付きサービス", "review": "信頼性を設計へ埋め込める"},
    {"id": "scaler", "after": 15, "artifact": "負荷・障害・SLO実験", "review": "分散失敗を測定し判断できる"},
    {"id": "human", "after": 20, "artifact": "アクセシブルな検証済み改善", "review": "人と社会への影響を説明できる"},
    {"id": "operator", "after": 25, "artifact": "移行・運用・費用計画", "review": "変更を安全かつ経済的に進められる"},
    {"id": "leader", "after": 30, "artifact": "他者が実行可能な技術方針", "review": "不確実性の中で組織を前進させられる"}
  ]
}
```

Each node also includes `id`, `title`, `track`, and `prerequisiteIds`.

- [x] **Step 4: Render and test the full roadmap**

Run:

```bash
python3.13 -m unittest tests.test_graph tests.test_roadmap_acceptance -v
python3.13 tools/build.py
```

Expected: all roadmap tests pass and the generated page links all 30 lessons.

- [x] **Step 5: Commit the prerequisite and mastery roadmap**

```bash
git add content/roadmap.json curriculum_builder/build.py \
  tests/test_core_tracks.py tests/test_roadmap_acceptance.py
git commit -m "feat: connect thirty lessons through mastery gates"
```

#### Task 9 verification evidence

- The tests-only RED commit `cb64ede` introduced the independent 30-lesson
  projection oracle, strict release-schema mutations, exact mastery gates,
  partial-release rejection, and static-link acceptance. The focused run
  produced one projection failure and seven missing-feature errors while the
  already-authored DAG oracle passed. Commit `2249839` supplied the minimal
  canonical roadmap, immutable parser, release binding, static rendering, and
  explicit `require_complete_curriculum` release mode.
- A second RED commit, `c8b6b57`, proved that ordinary topological completion
  alone still allowed an independent second root. Commit `d74a9d1` now requires
  `core-01-systems-tradeoffs` to be the only release root, so every other
  lesson is reachable from the curriculum entry point.
- Authoring remains incremental: the lesson collection loader and the default
  `build_site` API still accept an absent, empty, or partial lesson tree.
  `tools/build.py` opts into the release contract, where exactly 30 complete
  lessons, unique ordinals 1–30, the canonical metadata projection, and all
  six ordered mastery gates are mandatory before publication.
- The roadmap, graph, build, lesson-rendering, and stylesheet gate passes all
  111 tests. The complete repository suite passes all 484 tests. Two
  consecutive clean release builds each contain 35 regular artifacts, 34 HTML
  files, one CSS file, zero JavaScript files, zero symbolic links, and
  1,155,439 bytes. Both produce canonical aggregate SHA-256
  `29360f57b961b73887d4ce8c7bc722526b72209bdab0dd856cc23f204d76bafe`.
- Gitleaks 8.30.1 scanned all four Task 9 implementation commits from
  `5ddb8da..d74a9d1` and found no leaks. `git diff --check` is clean.
  The catalog remains exactly 1,140 unique items with SHA-256
  `4f38b5f63931a7f06e13f90f5d9ef90a0a435f30dae5d4fe70720d730a057473`.
  The private prototype archive remains unchanged and independently
  verifiable: 1,194 files, 16,805,630 bytes, and zero missing, extra,
  hash-mismatched, symbolic-link, or special-node entries.

#### Task 9 quality-review remediation

- The first independent quality review reported Critical 0 / Important 4 /
  Minor 1. Tests-only commit `8e1d3d6` reproduced every finding: a partial
  parser result could bypass mastery-gate checks in the release validator,
  the byte parser lacked its own size and safe-label boundary, decorative
  arrows represented nonexistent graph edges, the CLI release decision lacked
  an end-to-end regression, and authoring mode accepted duplicate gate identity.
- Commit `bd5ecd5` makes `validate_release_curriculum` independently recheck
  version, the exact six mastery gates, immutable node values, ordinals,
  graph validity, the single `core-01` root, metadata equality, and complete
  lessons. `parse_roadmap_bytes` now bounds exact bytes before JSON decoding,
  rejects unsafe diagnostic labels without reflecting them, and rejects
  duplicate gate IDs or `after` values even in authoring mode.
- Commit `e28a3a4` removes all decorative prerequisite arrows and CSS counters.
  The 30 lessons are now rendered in nine semantic topological-stage sections,
  with their canonical ordinals present as DOM text. The six mastery gates use
  a separate section and ordered list, so assistive technology no longer sees
  one misleading 36-item lesson sequence. Commit `e5554b0` additionally
  fail-closes forged mutable roadmap values at the validator boundary.
- The CLI regression builds from a copied root missing lesson 30 and proves a
  nonzero result, unchanged prior output, and zero staging residue. Removing
  the explicit release option from `tools/build.py` therefore fails the test.
  The expanded focused gate passes all 115 tests and the complete suite passes
  all 488 tests.
- Two consecutive release builds each contain 35 regular artifacts, 34 HTML
  files, one CSS file, zero JavaScript files, nine topological-stage sections,
  30 lesson list items, and six separately listed mastery gates. Both contain
  1,158,954 bytes and produce canonical aggregate SHA-256
  `2f44d246e1a8e2f0e851c5e99e15fe05179d2051e3b5d946af51bd947af64ced`.
  Catalog and archive preservation evidence remains unchanged.

#### Task 9 second quality-review remediation

- The second independent review reported Critical 0 / Important 1 / Minor 3.
  Tests-only commit `ff76e59` reproduced unsafe or unbounded roadmap
  identifiers reaching public graph diagnostics, a forged boolean ordinal
  passing integer equality, an absolute diagnostic label coupling valid builds
  to checkout-path length, and a dead mastery-gate heading selector.
- Commit `bc32e59` gives graph node, prerequisite-key, and dependency IDs one
  bounded ASCII identifier contract before any value-dependent diagnostic.
  Authoring mastery-gate IDs use a stricter HTML-safe contract. Release
  validation now requires an exact `int` ordinal, roadmap parsing receives the
  fixed safe label `roadmap.json`, and the stylesheet targets the rendered
  mastery-gate `h3`. A CLI regression builds successfully from a safe path over
  300 characters without JavaScript or staging residue.
- Self-review then identified that trailing control whitespace or overlong
  ASCII-space padding could still enter the legacy padding diagnostic after
  `strip()`. Tests-only commit `a769e1f` reproduced eight failures. Commit
  `911810e` preserves the actionable legacy diagnostic only for bounded ASCII
  space padding; all control, bidirectional, escape, or overlong identifiers
  now use fixed non-reflective diagnostics.
- The final focused gate passes all 118 tests and the complete suite passes all
  491 tests. Two repository-external release builds each contain 35 regular
  artifacts, 34 HTML files, one CSS file, zero JavaScript files, zero symbolic
  links, and zero special nodes. Each contains 1,158,954 bytes, nine
  topological stages, 30 lesson list items, and six mastery gates. Both produce
  canonical aggregate SHA-256
  `253aad1329906f9ee7e6a69073238444a3034ed2376e2947f36761047451cf08`.
- The 1,140-item catalog remains unique with SHA-256
  `4f38b5f63931a7f06e13f90f5d9ef90a0a435f30dae5d4fe70720d730a057473`.
  The private prototype archive remains unchanged: 1,194 files, 16,805,630
  bytes, and zero missing, extra, hash-mismatched, symbolic-link, special-node,
  or unsafe-path entries. Gitleaks and `git diff --check` are clean for the
  complete remediation range.

### Task 10: Add the versioned competency matrix

**Files:**
- Create: `curriculum_builder/competencies.py`
- Create: `content/competencies.json`
- Create: `templates/competency-matrix.html`
- Create: `tests/test_competencies.py`
- Modify: `curriculum_builder/build.py`

- [x] **Step 1: Write competency integrity tests**

```python
# tests/test_competencies.py
from __future__ import annotations

from pathlib import Path
import unittest

from curriculum_builder.competencies import load_competencies


class CompetencyTests(unittest.TestCase):
    def test_versions_and_mapping_rationales_are_explicit(self) -> None:
        matrix = load_competencies(Path("content/competencies.json"))
        self.assertEqual(
            matrix.framework_versions,
            {"CS2023": "Final Report", "SWEBOK": "V4.0a", "SFIA": "9"},
        )
        self.assertTrue(all(mapping.rationale for mapping in matrix.mappings))

    def test_every_core_lesson_maps_to_all_three_framework_families(self) -> None:
        matrix = load_competencies(Path("content/competencies.json"))
        for number in range(1, 31):
            prefix = f"core-{number:02d}-"
            mappings = [value for value in matrix.mappings if value.target_id.startswith(prefix)]
            self.assertEqual({value.framework for value in mappings}, {"CS2023", "SWEBOK", "SFIA"})
```

- [x] **Step 2: Run competency tests and verify RED**

Run:

```bash
python3 -m unittest tests.test_competencies -v
```

Expected: import failure because competency loader does not exist.

- [x] **Step 3: Implement version and reference validation**

```python
# curriculum_builder/competencies.py
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from curriculum_builder.errors import CurriculumValidationError


@dataclass(frozen=True, slots=True)
class Mapping:
    target_id: str
    framework: str
    competency_id: str
    rationale: str


@dataclass(frozen=True, slots=True)
class CompetencyMatrix:
    framework_versions: dict[str, str]
    mappings: tuple[Mapping, ...]


def load_competencies(path: Path) -> CompetencyMatrix:
    raw = json.loads(path.read_text(encoding="utf-8"))
    versions = raw["frameworkVersions"]
    expected = {"CS2023": "Final Report", "SWEBOK": "V4.0a", "SFIA": "9"}
    if versions != expected:
        raise CurriculumValidationError(f"framework versions must be {expected}")
    mappings = tuple(
        Mapping(
            target_id=value["targetId"],
            framework=value["framework"],
            competency_id=value["competencyId"],
            rationale=value["rationale"].strip(),
        )
        for value in raw["mappings"]
    )
    if any(not value.rationale for value in mappings):
        raise CurriculumValidationError("every competency mapping needs a rationale")
    return CompetencyMatrix(versions, mappings)
```

- [x] **Step 4: Map, render, and test all lessons**

Create three justified mappings per lesson using the official CS2023, SWEBOK
V4.0a, and SFIA 9 identifiers. Render a captioned table whose row headers are
lesson links and whose columns name framework and version.

Run:

```bash
python3 -m unittest tests.test_competencies -v
python3 tools/build.py
```

Expected: both competency tests pass and
`site/competencies/index.html` contains 90 or more justified mapping rows.

- [x] **Step 5: Commit the framework matrix**

```bash
git add curriculum_builder/competencies.py content/competencies.json \
  templates/competency-matrix.html tests/test_competencies.py \
  curriculum_builder/build.py
git commit -m "feat: map core mastery to global competency frameworks"
```

#### Task 10 verification evidence

- Tests-only commit `018254d` defined the fail-closed contract before the
  loader existed. The focused RED run failed with the expected
  `ModuleNotFoundError`. Commit `3f36629` supplies the immutable parser,
  version-pinned data, exact release binding, semantic static table, global
  navigation, print treatment, and escaping boundary.
- Primary-source verification on 2026-07-31 used the
  [CS2023 Final Report](https://csed.acm.org/final-report/),
  [SWEBOK Guide V4.0a](https://www.computer.org/education/bodies-of-knowledge/software-engineering),
  and [SFIA 9 skills index](https://sfia-online.org/en/sfia-9/skills/all-skills-a-z?set_language=en).
  The checked-in matrix uses official identifier-and-name pairs and pins
  `CS2023: Final Report`, `SWEBOK: V4.0a`, and `SFIA: 9`. It deliberately
  makes no certification or SFIA responsibility-level claim.
- The matrix contains exactly 90 immutable mappings: one CS2023, one SWEBOK,
  and one SFIA mapping for each of the 30 release lessons. Unknown fields,
  duplicate JSON keys, wrong versions, unofficial identifier/name pairs,
  missing or duplicate coverage, unsafe text, invalid UTF-8, oversized input,
  symbolic links, pathname rebinding, and non-regular files all fail closed.
  Missing or changing matrix input cannot replace a previously published
  output.
- All 14 focused competency tests and the complete 505-test repository suite
  pass with CPython 3.13. Two repository-external release builds each contain
  36 regular artifacts, 35 HTML files, one CSS file, zero JavaScript files,
  zero symbolic links, and zero special nodes. Each contains 1,198,716 bytes
  and produces canonical aggregate SHA-256
  `48593db553275cb3301405334d543d98855d88ff71b18cd6c07f60793ded087d`.
- The generated matrix has one caption, five scoped column headers, 90 scoped
  row headers, and 90 static lesson links. Screen layout permits horizontal
  reading of the wide table; print CSS restores a normal-width table without
  animation or dynamic behavior.
- Gitleaks 8.30.1 scanned both Task 10 commits from
  `092838b..3f36629` and found no leaks. `git diff --check` is clean. The
  catalog remains exactly 1,140 unique items with SHA-256
  `4f38b5f63931a7f06e13f90f5d9ef90a0a435f30dae5d4fe70720d730a057473`.
  The private prototype archive remains unchanged: 1,194 files, 16,805,630
  bytes, and zero missing, extra, hash-mismatched, symbolic-link, special-node,
  or unsafe-path entries.

#### Task 10 quality-review remediation

- The independent specification review reported Critical 0 / Important 2 /
  Minor 1. Tests-only commit `9542352` reproduced the missing machine-readable
  source metadata, the absence of per-mapping alignment strength, and the
  print token contract. Commit `ef670c6` adds exact official URL, version, and
  verification-date metadata; an immutable `direct | foundational | partial`
  alignment for every mapping; a sixth semantic table column; and a visible
  non-certification and non-SFIA-level disclaimer.
- The test oracle hard-codes every official identifier/name pair used by the
  matrix and all 90 alignment decisions without importing or deriving
  production allowlists. The resulting distribution is 63 direct, 10
  foundational, and 17 partial mappings. In particular,
  `core-03` → SFIA `IFDN` is foundational, while `core-23` → CS2023 `SEC` is
  partial and its rationale explicitly limits the overlap to security
  incidents rather than claiming all operational incidents are Security.
- Chrome 150 Letter-PDF probing exposed a second print defect after the first
  GREEN: the screen selectors for the 17-rem lesson column and 26-rem
  rationale column had greater specificity than the generic print reset,
  producing 89 pages. Tests-only commit `3e828da` fixes that requirement in
  the CSS contract; commit `2c8ef52` explicitly resets both selectors,
  preserves framework/version/code tokens with no-wrap monospace treatment,
  and reduces the same matrix to six readable pages.
- The final Chrome artifact is a tagged, JavaScript-free, portrait Letter PDF
  at 612 by 792 points. PDFKit extraction preserves `CS2023`, `Final Report`,
  `SWEBOK`, `V4.0a`, `SFIA`, `CHAPTER 18`, `IFDN`, and `SEC` as continuous
  tokens and finds none of the prior split forms such as `CS2\n023`,
  `V4.\n0a`, `CHAPTER\n18`, or `IF\nDN`. Page-one raster inspection confirms
  the same result visually.
- The first complete-suite run after source links correctly exposed one stale
  release expectation. A too-broad helper change then proved, through 23
  authoring-mode failures, that authoring pages intentionally have no verified
  framework links. Commit `a8adfa5` makes the release-only expectation
  explicit, and `f0b230e` simplifies source rendering without changing
  output. The focused competency and build gate passes all 54 tests; the
  complete suite passes all 509 tests.
- Two final repository-external builds each contain 36 regular artifacts,
  35 HTML files, one CSS file, zero JavaScript files, zero symbolic links,
  and zero special nodes. Each contains 1,216,139 bytes and produces canonical
  aggregate SHA-256
  `919d1e981a7539a56596acf5519613e444f70fe900ddb3eadf8f181244b01fc7`.
  Gitleaks 8.30.1 reports no leaks across the six remediation commits, and
  `git diff --check` is clean.
- The catalog remains exactly 1,140 unique items with SHA-256
  `4f38b5f63931a7f06e13f90f5d9ef90a0a435f30dae5d4fe70720d730a057473`.
  The private archive remains independently unchanged: 1,194 files,
  16,805,630 bytes, with zero missing, extra, hash-mismatched, symbolic-link,
  special-node, or unsafe-path entries.

#### Task 10 final print-token remediation

- The final specification review found one remaining Minor issue: all 90
  alignment values could still split in Chrome print output. Tests-only commit
  `4390442` expands the static HTML/CSS contract from 270 to 360 protected
  framework, version, code, and alignment tokens and reproduces the missing
  `.competency-strength` selector. Commit `18de89f` adds that selector to the
  existing no-wrap monospace print rule.
- Chrome 150 continues to generate a six-page, tagged, JavaScript-free Letter
  PDF at 612 by 792 points. PDFKit now extracts `direct`, `foundational`, and
  `partial` continuously, finds none of the reviewed split forms, and retains
  continuous extraction for all previously checked framework, version, and
  code tokens.
- All 18 focused competency tests and the complete 509-test suite pass. Two
  external builds each contain 36 regular artifacts, 35 HTML files, one CSS
  file, zero JavaScript files, zero symbolic links, and zero special nodes.
  Each contains 1,216,163 bytes and produces canonical aggregate SHA-256
  `6e37c8a9f3ed6ab7c97f8d03c6edf6599f1fa06dabfb223fc3a60f8120671627`.
  Gitleaks reports no leaks, `git diff --check` is clean, and catalog/archive
  preservation evidence remains unchanged.

#### Task 10 renderer-safe print-card remediation

- Chrome 150 exposed a final cross-renderer defect that DOM and text extraction
  alone could not prove away: a fragmented semantic table could retain text
  while Poppler or PDFKit omitted header or cell paint runs. Tests-only commits
  `85c3d2f`, `1e7bc0f`, `55c99f2`, `e36cc3b`, `f44ba7d`, and `87d4390`
  reproduce the successive named-page, six-table, stable-column, and
  renderer-independent print-card requirements. The fixed-column experiment
  improved text ordering but did not eliminate renderer-specific paint loss,
  so it was superseded rather than treated as release evidence.
- Commit `879ad5b` keeps the screen document as six semantic, track-scoped
  tables, each with a unique caption, six real column headers, five lessons,
  and 15 mappings. Commits `50993ac` and `22b168c` remove table-layout-engine
  dependence only inside `@media print`: every one of the 90 mappings becomes
  a labelled, non-splitting block card, the original table header is hidden,
  and horizontal track captions remain visible. The resulting static HTML
  still contains all 90 links and mappings and requires no JavaScript.
- Two fresh Chrome PDFs each contain 18 tagged, JavaScript-free, landscape
  Letter pages at 792 by 612 points. PDFKit extraction finds all six print
  labels exactly 90 times after whitespace normalization. Sixty-five distinct
  framework, version, alignment, and official-ID signatures match their
  source-derived multiplicities with zero mismatch in both PDFs. Poppler and
  PDFKit rasterization of both runs produces identical per-page hashes within
  each renderer. Full 18-page contact-sheet review in both renderers, plus
  original-resolution review of renderer-sensitive page 10, finds zero missing
  content, clipped labels, split cards, or unexpected blank pages. The PDF byte
  hashes differ, while all 18 rendered pages remain deterministic.
- The focused competency/style gate passes all 37 tests and the complete suite
  passes all 509 tests. Two final repository-external builds each contain 36
  artifacts, 35 HTML files, one CSS file, and zero JavaScript files. Each
  contains 1,220,599 bytes and produces canonical aggregate SHA-256
  `4afb01c4fea41a69a5b7d5e4ddcc76cd443efd3ddd92cb37eea9e1a80f488dd1`.
  Gitleaks 8.30.1 reports no leaks across all 11 remediation commits and
  `git diff --check` is clean.
- The catalog remains exactly 1,140 unique items with SHA-256
  `4f38b5f63931a7f06e13f90f5d9ef90a0a435f30dae5d4fe70720d730a057473`.
  The private archive remains independently unchanged: 1,194 files,
  16,805,630 bytes, with zero missing, extra, hash-mismatched, symbolic-link,
  special-node, or unsafe-path entries.

### Task 11: Add three integrated capstones

**Files:**
- Create: `curriculum_builder/capstones.py`
- Create: `content/capstones/global-service.json`
- Create: `content/capstones/legacy-evolution.json`
- Create: `content/capstones/oss-launch.json`
- Create: `templates/capstone.html`
- Create: `tests/test_capstones.py`
- Modify: `curriculum_builder/build.py`

- [x] **Step 1: Write capstone coverage tests**

```python
# tests/test_capstones.py
from __future__ import annotations

from pathlib import Path
import unittest

from curriculum_builder.capstones import load_capstones


class CapstoneTests(unittest.TestCase):
    def test_three_capstones_cover_every_core_lesson(self) -> None:
        capstones = load_capstones(Path("content/capstones"))
        self.assertEqual(
            tuple(value.id for value in capstones),
            ("global-service", "legacy-evolution", "oss-launch"),
        )
        covered = set().union(*(set(value.lesson_ids) for value in capstones))
        for number in range(1, 31):
            self.assertTrue(
                any(value.startswith(f"core-{number:02d}-") for value in covered),
                f"core lesson {number} is not exercised by a capstone",
            )

    def test_each_capstone_requires_build_operate_explain_and_review_evidence(self) -> None:
        for capstone in load_capstones(Path("content/capstones")):
            self.assertEqual(
                set(capstone.evidence_kinds),
                {"build", "operate", "explain", "review"},
            )
```

- [x] **Step 2: Run capstone tests and verify RED**

Run:

```bash
python3.13 -m unittest tests.test_capstones -v
```

Expected: import failure because `curriculum_builder.capstones` does not exist.

- [x] **Step 3: Implement capstone parsing and exact briefs**

Each JSON document contains `id`, `title`, `scenario`, `constraints`,
`lessonIds`, four evidence records, milestones, review questions, and the same
four rubric levels as lessons.

```json
[
  {
    "id": "global-service",
    "evidence": {
      "build": "API、データモデル、脅威モデル、テスト",
      "operate": "SLO、観測、負荷・障害実験、費用",
      "explain": "代替案と判断を含む設計レビュー",
      "review": "失敗証拠から更新したADR"
    }
  },
  {
    "id": "legacy-evolution",
    "evidence": {
      "build": "特性テストと段階移行",
      "operate": "停止・ロールバック・保守ランブック",
      "explain": "技術・事業向け移行説明",
      "review": "リスクと費用を再評価した計画"
    }
  },
  {
    "id": "oss-launch",
    "evidence": {
      "build": "アクセシブルな公開リポジトリ",
      "operate": "CI、セキュリティ、リリース、Errata",
      "explain": "新規貢献者向け導線とガバナンス",
      "review": "第三者の貢献結果を反映した改善"
    }
  }
]
```

Implement `load_capstones()` as sorted immutable parsing with unique-ID,
lesson-reference, evidence-kind, and rubric validation.

- [x] **Step 4: Render and run capstone acceptance**

Run:

```bash
python3.13 -m unittest tests.test_capstones -v
python3.13 tools/build.py
```

Expected: two tests pass; three capstone pages and an index are generated.

- [x] **Step 5: Commit the integrated proof of expertise**

```bash
git add curriculum_builder/capstones.py content/capstones templates/capstone.html \
  tests/test_capstones.py curriculum_builder/build.py
git commit -m "content: prove expertise through integrated capstones"
```

#### Task 11 verification evidence

- Tests-only commits `2743622` and `9455f26` fixed the loader/content and
  static-publication contracts before implementation. The first focused RED
  failed with the expected `ModuleNotFoundError`; the second proved that the
  existing builder neither generated capstone pages nor rejected a malformed
  capstone before publication.
- Commits `ba19788` and `38c18b0` implement three exact immutable briefs,
  descriptor-pinned bounded loading, complete lesson-reference validation,
  semantic primary exercises, four evidence kinds, four rubric levels, static
  index/detail rendering, global navigation, print treatment, and atomic
  publication. Commit `57b8537` updates the independent artifact inventory.
- The three briefs cover the exact 30-lesson release. Every lesson has one
  accountable primary exercise with an observable action, while additional
  references are explicitly reinforcement. Every review requires a third-party
  finding, author fix, independent re-evaluation, and one-constraint transfer;
  the rendered brief states that it is an assignment rather than a completion
  or mastery record.
- Root and nested unknown or missing fields, duplicate JSON keys, wrong native
  types, unsafe or oversized text, invalid UTF-8, symbolic links, pathname
  changes, wrong file/id binding, noncanonical order, unknown/draft/duplicate
  lessons, incomplete union coverage, ID-only primary exercises, wrong primary
  ownership, incomplete evidence/rubric sets, and incomplete review cycles fail
  closed. A malformed release input leaves the previously published site byte
  unchanged.
- Security self-review added independent RED cases for parent-directory
  rebinding, mistyped document-map keys, and platforms without effective
  no-follow directory support. Commits `0501157`, `dc97b11`, and `fc6bf5b`
  make each boundary fail closed before any capstone is accepted.
- Review-remediation tests-only commits `f516a24` and `f01bb5e` reproduce the
  remaining confused-deputy path, capstone-leaf replacement, generic exercise,
  reflected lesson-ID diagnostic, descriptor-close masking, fragmented print
  card, and footer-only final-page failures. Commit `9ea2d89` pins the exact
  `capstones` leaf identity, enforces bounded indexed diagnostics without
  reflecting rejected values, preserves a primary validation error when close
  also fails, and requires NFKC-normalized unique exercises with two
  lesson-specific semantic anchors. Commit `7794858` replaces the print grid
  with a non-fragmenting block flow and removes the site footer from capstone
  print documents.
- Test refinement commit `1da589b` proves that raw-distinct ASCII-space and
  ideographic-space variants collide after normalization, rather than testing
  only byte-identical exercise reuse.
- All 20 focused capstone tests and the complete 529-test repository suite pass
  with CPython 3.12.13. Two repository-external builds each contain 40 artifacts,
  39 HTML files, four capstone pages, and zero JavaScript files; both have the
  canonical aggregate SHA-256
  `ca90b2453c203c8245fb4592b33399b297b71089a477d62cb795a0162e880c11`.
- Chromium generated tagged, JavaScript-free, Letter PDFs of six pages for
  each of the three briefs. PDFKit extraction finds all 30 primary-exercise
  markers and all 46 reinforcement markers. Full 18-page Poppler raster review
  confirms that every rendered lesson heading, explanation, and enclosing
  border stays on one page, including the previously fragmented global-service
  and OSS-launch cards; each final page contains its rubric and no footer-only
  or blank page remains. The canonical catalog
  remains at SHA-256
  `4f38b5f63931a7f06e13f90f5d9ef90a0a435f30dae5d4fe70720d730a057473`.
  The private prototype payload remains 1,194 files and 16,805,630 bytes; its
  separate 157,542-byte manifest makes the observed archive total 1,195 files.
  Gitleaks scanned both the complete Task 11 history and all remediation and
  evidence commits and reported no leaks; `git diff --check` is clean.

### Task 12: Run the complete learning-quality gate

**Files:**
- Create: `tests/test_content_acceptance.py`
- Create: `docs/content-standard.md`
- Create: `docs/curriculum-map.md`

- [ ] **Step 1: Add the release-level content acceptance test**

```python
# tests/test_content_acceptance.py
from __future__ import annotations

from pathlib import Path
import unittest

from curriculum_builder.lessons import load_lesson


class ContentAcceptanceTests(unittest.TestCase):
    def test_release_has_thirty_complete_nonduplicated_lesson_bodies(self) -> None:
        metadata = sorted(Path("content/lessons").glob("*/lesson.json"))
        bodies = [path.with_name("body.html") for path in metadata]
        self.assertEqual(len(metadata), 30)
        self.assertTrue(all(path.is_file() for path in bodies))
        self.assertTrue(all(load_lesson(path).status == "complete" for path in metadata))
        normalized = {
            " ".join(path.read_text(encoding="utf-8").split())
            for path in bodies
        }
        self.assertEqual(len(normalized), 30)

    def test_every_body_contains_required_textbook_sections(self) -> None:
        headings = (
            "なぜ重要か", "メンタルモデル", "動く例で考える",
            "トレードオフと失敗モード", "知識チェック", "出典と次の学習",
        )
        for body in Path("content/lessons").glob("*/body.html"):
            html = body.read_text(encoding="utf-8")
            for heading in headings:
                self.assertIn(heading, html, f"{body}: missing {heading}")
```

- [ ] **Step 2: Run the full suite**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: all foundation and learning-content tests pass.

- [ ] **Step 3: Document the contributor-facing content standard**

`docs/content-standard.md` must define the six-step evidence loop, required
sections, source hierarchy, lab artifact rules, reasoned assessment rules,
rubric language, accessibility rules, review roles, and the prohibition on
marking a lesson complete before all checks pass.

`docs/curriculum-map.md` must list the 30 lessons, exact prerequisites, mastery
gates, capstone coverage, and framework versions in one reviewable map.

- [ ] **Step 4: Build twice and compare output**

Run:

```bash
python3 tools/build.py
find site -type f -exec shasum -a 256 {} + | sort > /tmp/content-build-1.sha256
python3 tools/build.py
find site -type f -exec shasum -a 256 {} + | sort > /tmp/content-build-2.sha256
diff -u /tmp/content-build-1.sha256 /tmp/content-build-2.sha256
```

Expected: no diff.

- [ ] **Step 5: Commit the curriculum quality gate**

```bash
git add tests/test_content_acceptance.py docs/content-standard.md docs/curriculum-map.md
git commit -m "docs: define reviewable expert growth standard"
```
