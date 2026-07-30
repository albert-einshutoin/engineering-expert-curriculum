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
  loader detects observed symlink, rebinding, and content changes, but does not
  use owner or mode bits as an authority decision and does not claim a privilege
  boundary against a concurrent same-euid writer.
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

- [ ] **Step 1: Write the exact Foundations contract**

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

- [ ] **Step 2: Run the track test and verify RED**

Run:

```bash
python3 -m unittest tests.test_core_tracks.CoreTrackTests.test_foundations -v
```

Expected: failure listing all five missing lesson directories.

- [ ] **Step 3: Author each lesson using the complete mastery loop**

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

- [ ] **Step 4: Run the focused quality and rendering gates**

Run:

```bash
python3 -m unittest \
  tests.test_lesson_quality \
  tests.test_core_tracks.CoreTrackTests.test_foundations \
  tests.test_lesson_rendering -v
```

Expected: all tests pass and five lesson pages render.

- [ ] **Step 5: Commit the Foundations track**

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

- [ ] **Step 1: Add the exact Build track contract**

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

- [ ] **Step 2: Run the Build track test and verify RED**

Run:

```bash
python3 -m unittest tests.test_core_tracks.CoreTrackTests.test_build -v
```

Expected: failure listing five missing Build lessons.

- [ ] **Step 3: Author all five lessons against the mastery contract**

Use the same six body sections defined in Task 3. Labs must produce the exact
artifacts in `BUILD`; transfer tasks must respectively cover an unfamiliar
business domain, an offline client, a high-change module, a nondeterministic
defect, and an insider threat. Authoritative sources must include
ISO/IEC/IEEE 29148 or SWEBOK V4.0a, RFC 9110 or OpenAPI, IEEE 42010, primary
testing literature, and NIST SSDF or OWASP guidance as appropriate.

- [ ] **Step 4: Run Build track gates**

Run:

```bash
python3 -m unittest \
  tests.test_lesson_quality \
  tests.test_core_tracks.CoreTrackTests.test_build \
  tests.test_lesson_rendering -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit the Build track**

```bash
git add content/lessons/core-{06,07,08,09,10}-* tests/test_core_tracks.py
git commit -m "content: connect software design to trustworthy evidence"
```

### Task 5: Author the Data and Scale track

**Files:**
- Create: `content/lessons/core-11-data-modeling-storage/{lesson.json,body.html}`
- Create: `content/lessons/core-12-transactions-isolation-consistency/{lesson.json,body.html}`
- Create: `content/lessons/core-13-distributed-coordination-failure/{lesson.json,body.html}`
- Create: `content/lessons/core-14-performance-capacity/{lesson.json,body.html}`
- Create: `content/lessons/core-15-reliability-observability-slo/{lesson.json,body.html}`
- Modify: `tests/test_core_tracks.py`

- [ ] **Step 1: Add the exact Data and Scale contract**

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

- [ ] **Step 2: Run the Data and Scale test and verify RED**

Run:

```bash
python3 -m unittest tests.test_core_tracks.CoreTrackTests.test_data_scale -v
```

Expected: five missing lessons.

- [ ] **Step 3: Author the five evidence-heavy lessons**

Use the Task 3 section contract. Every worked example must contain measured or
simulated evidence. Transfer tasks must change one hidden assumption: access
pattern, concurrency, network partition, request mix, or user-visible
reliability. Sources must include database vendor documentation or original
papers, RFCs, peer-reviewed distributed-systems work, platform profiling
documentation, and the Google SRE or OpenTelemetry primary materials.

- [ ] **Step 4: Run Data and Scale gates**

Run:

```bash
python3 -m unittest \
  tests.test_lesson_quality \
  tests.test_core_tracks.CoreTrackTests.test_data_scale \
  tests.test_lesson_rendering -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit the Data and Scale track**

```bash
git add content/lessons/core-{11,12,13,14,15}-* tests/test_core_tracks.py
git commit -m "content: teach evidence-driven scale and reliability"
```

### Task 6: Author the Human and Product Systems track

**Files:**
- Create: `content/lessons/core-16-hci-usability-accessibility/{lesson.json,body.html}`
- Create: `content/lessons/core-17-graphics-visual-information/{lesson.json,body.html}`
- Create: `content/lessons/core-18-product-discovery-experiments/{lesson.json,body.html}`
- Create: `content/lessons/core-19-technical-communication-design-docs/{lesson.json,body.html}`
- Create: `content/lessons/core-20-ethics-privacy-societal-impact/{lesson.json,body.html}`
- Modify: `tests/test_core_tracks.py`

- [ ] **Step 1: Add the exact Human and Product contract**

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

- [ ] **Step 2: Run the Human and Product test and verify RED**

Run:

```bash
python3 -m unittest tests.test_core_tracks.CoreTrackTests.test_human_product -v
```

Expected: five missing lessons.

- [ ] **Step 3: Author the five human-centered lessons**

Use real interfaces and decision scenarios rather than generic advice. The HCI
lab audits this generated curriculum site against WCAG 2.2 AA. The graphics lab
recreates one roadmap and one quantitative chart with semantic HTML/CSS and a
text equivalent. The experiment lab defines guardrail metrics. The
communication lab produces both a one-page executive summary and a technical
appendix. The ethics lab uses the ACM Code of Ethics and NIST Privacy Framework
to identify unevenly distributed harm.

- [ ] **Step 4: Run Human and Product gates**

Run:

```bash
python3 -m unittest \
  tests.test_lesson_quality \
  tests.test_core_tracks.CoreTrackTests.test_human_product \
  tests.test_lesson_rendering -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit the Human and Product track**

```bash
git add content/lessons/core-{16,17,18,19,20}-* tests/test_core_tracks.py
git commit -m "content: integrate human product and ethical judgment"
```

### Task 7: Author the Sustain and Operate track

**Files:**
- Create: `content/lessons/core-21-maintenance-legacy-comprehension/{lesson.json,body.html}`
- Create: `content/lessons/core-22-evolution-safe-migrations/{lesson.json,body.html}`
- Create: `content/lessons/core-23-incident-response-learning/{lesson.json,body.html}`
- Create: `content/lessons/core-24-delivery-ci-release-safety/{lesson.json,body.html}`
- Create: `content/lessons/core-25-engineering-economics-capacity/{lesson.json,body.html}`
- Modify: `tests/test_core_tracks.py`

- [ ] **Step 1: Add the exact Sustain and Operate contract**

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

- [ ] **Step 2: Run the Sustain test and verify RED**

Run:

```bash
python3 -m unittest tests.test_core_tracks.CoreTrackTests.test_sustain -v
```

Expected: five missing lessons.

- [ ] **Step 3: Author the five lifecycle lessons**

All labs operate on a small supplied legacy fixture so outputs can be reviewed.
Each lesson must distinguish successful command execution from demonstrated
system outcome. Use SWEBOK V4.0a maintenance/operations knowledge areas, NIST
incident guidance, SLSA provenance, DORA delivery evidence, and FinOps or cloud
provider cost guidance as appropriate.

- [ ] **Step 4: Run Sustain and Operate gates**

Run:

```bash
python3 -m unittest \
  tests.test_lesson_quality \
  tests.test_core_tracks.CoreTrackTests.test_sustain \
  tests.test_lesson_rendering -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit the Sustain and Operate track**

```bash
git add content/lessons/core-{21,22,23,24,25}-* tests/test_core_tracks.py
git commit -m "content: teach safe software evolution and operations"
```

### Task 8: Author the Lead and Contribute track

**Files:**
- Create: `content/lessons/core-26-code-review-collaborative-quality/{lesson.json,body.html}`
- Create: `content/lessons/core-27-team-interfaces-sociotechnical-architecture/{lesson.json,body.html}`
- Create: `content/lessons/core-28-oss-governance-stewardship/{lesson.json,body.html}`
- Create: `content/lessons/core-29-cross-cultural-async-collaboration/{lesson.json,body.html}`
- Create: `content/lessons/core-30-evidence-based-technical-leadership/{lesson.json,body.html}`
- Modify: `tests/test_core_tracks.py`

- [ ] **Step 1: Add the exact Lead and Contribute contract**

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

- [ ] **Step 2: Run the Lead test and verify RED**

Run:

```bash
python3 -m unittest tests.test_core_tracks.CoreTrackTests.test_lead -v
```

Expected: five missing lessons.

- [ ] **Step 3: Author the five leadership lessons**

Each lab must involve reviewing or enabling another contributor, not only
producing an individual artifact. The OSS lesson uses this repository as the
working example. The async collaboration lesson requires a context-complete
decision that can be reviewed without a meeting. The final leadership lesson
requires explicit metrics, dissent, uncertainty, ethics, cost, and a reversible
first step.

- [ ] **Step 4: Run Lead and Contribute gates**

Run:

```bash
python3 -m unittest \
  tests.test_lesson_quality \
  tests.test_core_tracks.CoreTrackTests.test_lead \
  tests.test_lesson_rendering -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit the Lead and Contribute track**

```bash
git add content/lessons/core-{26,27,28,29,30}-* tests/test_core_tracks.py
git commit -m "content: develop collaborative technical leadership"
```

### Task 9: Replace the stage placeholder with the 30-lesson roadmap

**Files:**
- Modify: `content/roadmap.json`
- Modify: `tests/test_core_tracks.py`
- Modify: `curriculum_builder/build.py`
- Create: `tests/test_roadmap_acceptance.py`

- [ ] **Step 1: Write the complete roadmap acceptance test**

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

- [ ] **Step 2: Run the roadmap test and verify RED**

Run:

```bash
python3 -m unittest tests.test_roadmap_acceptance -v
```

Expected: failure because the placeholder roadmap has four non-lesson nodes.

- [ ] **Step 3: Write the canonical roadmap**

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

- [ ] **Step 4: Render and test the full roadmap**

Run:

```bash
python3 -m unittest tests.test_graph tests.test_roadmap_acceptance -v
python3 tools/build.py
```

Expected: all roadmap tests pass and the generated page links all 30 lessons.

- [ ] **Step 5: Commit the prerequisite and mastery roadmap**

```bash
git add content/roadmap.json curriculum_builder/build.py \
  tests/test_core_tracks.py tests/test_roadmap_acceptance.py
git commit -m "feat: connect thirty lessons through mastery gates"
```

### Task 10: Add the versioned competency matrix

**Files:**
- Create: `curriculum_builder/competencies.py`
- Create: `content/competencies.json`
- Create: `templates/competency-matrix.html`
- Create: `tests/test_competencies.py`
- Modify: `curriculum_builder/build.py`

- [ ] **Step 1: Write competency integrity tests**

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

- [ ] **Step 2: Run competency tests and verify RED**

Run:

```bash
python3 -m unittest tests.test_competencies -v
```

Expected: import failure because competency loader does not exist.

- [ ] **Step 3: Implement version and reference validation**

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

- [ ] **Step 4: Map, render, and test all lessons**

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

- [ ] **Step 5: Commit the framework matrix**

```bash
git add curriculum_builder/competencies.py content/competencies.json \
  templates/competency-matrix.html tests/test_competencies.py \
  curriculum_builder/build.py
git commit -m "feat: map core mastery to global competency frameworks"
```

### Task 11: Add three integrated capstones

**Files:**
- Create: `curriculum_builder/capstones.py`
- Create: `content/capstones/global-service.json`
- Create: `content/capstones/legacy-evolution.json`
- Create: `content/capstones/oss-launch.json`
- Create: `templates/capstone.html`
- Create: `tests/test_capstones.py`
- Modify: `curriculum_builder/build.py`

- [ ] **Step 1: Write capstone coverage tests**

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

- [ ] **Step 2: Run capstone tests and verify RED**

Run:

```bash
python3 -m unittest tests.test_capstones -v
```

Expected: import failure because `curriculum_builder.capstones` does not exist.

- [ ] **Step 3: Implement capstone parsing and exact briefs**

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

- [ ] **Step 4: Render and run capstone acceptance**

Run:

```bash
python3 -m unittest tests.test_capstones -v
python3 tools/build.py
```

Expected: two tests pass; three capstone pages and an index are generated.

- [ ] **Step 5: Commit the integrated proof of expertise**

```bash
git add curriculum_builder/capstones.py content/capstones templates/capstone.html \
  tests/test_capstones.py curriculum_builder/build.py
git commit -m "content: prove expertise through integrated capstones"
```

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
