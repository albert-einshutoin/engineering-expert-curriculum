# Interactive Visual Learning vNext — Design Specification

Date: 2026-08-01

Status: Approved for implementation

Target release: v0.2.0 candidate

License: MIT

Primary language: Japanese

## 1. Purpose

Add a semantic visual explanation to every one of the 30 core lessons and add a
bounded, deterministic simulation to the 12 lessons where time or state change
materially improves understanding.

The existing prose, runnable examples, labs, assessments, sources, and rubrics
remain part of the textbook. Visuals supplement those explanations; they do not
replace them. A learner must still be able to understand every relationship and
complete every lesson when JavaScript fails, is blocked, or is disabled.

This specification deliberately changes the v0.1.0 runtime contract. v0.1.0 is
the immutable HTML/CSS-only release. v0.2.0 may include one small first-party
JavaScript asset on the 12 simulation pages, while keeping semantic HTML as the
source of truth and retaining `file://`, GitHub Pages, print, keyboard, and
assistive-technology support.

## 2. Accepted product decisions

1. Use a meaning-based diagram kit rather than one generic numbered-list style.
2. Give all 30 core lessons at least one CSS diagram.
3. Use progressive enhancement for exactly 12 simulations; do not add
   animation where a static relationship communicates the idea better.
4. Store structured visualization data with lesson metadata, validate it in the
   Python build, and render deterministic semantic HTML.
5. Use only repository-owned HTML, CSS, and JavaScript. Do not use Mermaid or
   any other browser runtime dependency in this release.
6. Preserve all existing lesson content and place visuals next to the concept
   they explain, normally immediately after the mental-model section.

## 3. Goals and non-goals

### 3.1 Goals

- Make flow, hierarchy, causality, comparison, state, time, network, and memory
  relationships visually distinguishable.
- Let a learner step through memory access, request transmission, scheduling,
  retries, transactions, incidents, migrations, and releases without requiring
  a server.
- Keep the static explanation complete before enhancement starts.
- Make authoring and review deterministic, bounded, testable, and safe for an
  OSS contributor workflow.
- Expose the same facts through visual layout, text trace, and structured
  fallback content.
- Preserve the existing dependency-free Python build and generated-site model.

### 3.2 Non-goals

- Replacing lesson prose with animations.
- Adding accounts, progress storage, analytics, remote APIs, search, or user
  supplied content.
- Running arbitrary Mermaid, HTML, CSS, SVG, or JavaScript from lesson JSON.
- Implementing a general graph-layout engine in the browser.
- Accurately emulating a specific CPU, operating system, network, database, or
  assistive technology.
- Introducing Canvas, WebGL, inline SVG, Web Components, a package manager, or
  a third-party JavaScript library in v0.2.0.
- Making every visual interactive merely because JavaScript is available.

## 4. Learning design

Each visual has one explicit learning question, such as “where can this request
wait?”, “which invariant is violated?”, or “which layer owns this decision?”.
It is not decorative illustration.

Every visual provides four equivalent layers:

1. **Caption:** the question or relationship being explained.
2. **Semantic model:** ordered lists, definition lists, or tables containing all
   nodes, relationships, states, and outcomes.
3. **CSS composition:** position, connectors, grouping, emphasis, and scale.
4. **Optional simulation:** a deterministic change of the same checked-in
   model, with a textual state trace that remains available to every learner.

The primary visual normally follows the lesson's mental-model explanation. A
second visual is allowed near the worked example, trade-off table, or lab only
when it answers a different question. v0.2.0 limits each lesson to two visuals
and one simulation to prevent visual density from displacing practice.

The visual must state its limits. A memory hierarchy is a diagnostic model, not
a promise about a particular processor. A request path is a model, not a packet
capture. The accessibility simulation demonstrates layout and focus behavior;
it is not a substitute for testing with a browser and assistive technology.

## 5. System architecture

```text
lesson.json + body.html
        |
        v
strict JSON and body validation
        |
        v
immutable Visualization domain model
        |
        +------> semantic HTML renderer ------> complete no-JS lesson
        |
        +------> CSS class contract ----------> meaning-based composition
        |
        +------> bounded state model ---------> optional shared JS runtime
                                                    |
                                                    v
                         scenario choice / step / playback / reset
```

The Python build remains authoritative. The browser runtime never invents graph
layout, downloads data, parses a diagram language, or mutates the lesson's
meaning. It changes only the active step and the presentation of already
rendered, validated states.

### 5.1 Planned repository changes

```text
curriculum_builder/
  visualizations.py       # immutable models, validation, semantic rendering
static/
  visualizations.css      # diagram kit and simulation states
  visualization.js        # one dependency-free progressive-enhancement runtime
tests/
  browser-matrix.json
  test_visualization_models.py
  test_visualization_rendering.py
  test_visualization_runtime.py
  test_visualization_accessibility.py
  test_visualization_security.py
```

Existing files updated by the feature include lesson JSON/body fragments, the
lesson renderer and template, the site checker, README files, content standard,
security documentation, changelog, and release validation. Generated `site/`
remains ignored and reproducible.

`content/visualization-catalog.json` is added as the checked-in source of truth
for the exact 30 lesson-to-primary-type assignments and the exact 12
lesson-to-simulation-kind assignments. Existing source records gain stable IDs
so visuals can reference evidence without duplicating URLs.

### 5.2 Responsibility boundaries

- `visualizations.py` accepts only strict structured data and emits typed,
  immutable models or bounded validation errors.
- The lesson body parser retains the six required sections and exposes stable
  insertion points. It does not execute or interpret visualization content.
- The renderer inserts a visual after its validated `afterSection` target and
  HTML-escapes every structured string.
- `visualizations.css` owns layout and presentation; essential reading order and
  relationships do not depend on generated content or color.
- `visualization.js` owns only deterministic control state. It does not fetch,
  store, navigate, evaluate strings, or create lesson content.

## 6. Visualization content model

`lesson.json` gains an optional `visualizations` array. For the 30 complete core
lessons it becomes required and contains one or two entries.

The normative common shape, shown with illustrative lesson values, is:

```json
{
  "visualizations": [
    {
      "id": "memory-load-path",
      "type": "memory",
      "caption": "一つのロードが値へ到達する診断経路",
      "question": "待ち時間はどの段階で発生し得るか",
      "afterSection": "mentalModel",
      "objectiveIds": ["obj-path"],
      "evidenceIds": ["locality-report", "teach-back"],
      "sourceIds": ["src-intel-optimization"],
      "expectedObservation": "変換待ちと転送待ちを別の仮説として説明する",
      "payload": {
        "layers": [
          {
            "id": "cpu",
            "label": "CPU",
            "detail": "仮想アドレスの値を要求する",
            "group": "request"
          },
          {
            "id": "tlb",
            "label": "TLB",
            "detail": "ページ変換を検索する",
            "group": "translation"
          }
        ],
        "transfers": [
          {
            "id": "cpu-to-tlb",
            "from": "cpu",
            "to": "tlb",
            "label": "仮想アドレス",
            "kind": "request"
          }
        ]
      },
      "notes": [
        "具体的な並行性とprivate/shared範囲は実装依存である"
      ],
      "simulation": {
        "kind": "memory-access",
        "interactionMode": "hybrid",
        "parameters": [
          {
            "id": "access-pattern",
            "label": "アクセス順",
            "control": "select",
            "options": [
              {"id": "sequential", "label": "連続"},
              {"id": "stride", "label": "stride"},
              {"id": "random", "label": "ランダム"}
            ],
            "defaultOptionId": "sequential"
          }
        ],
        "initialStateId": "lookup",
        "defaultIntervalMs": 1200,
        "states": [
          {
            "id": "lookup",
            "label": "変換を検索",
            "activeNodeIds": ["cpu", "tlb"],
            "activeEdgeIds": ["cpu-to-tlb"],
            "status": "CPUからTLBへ変換要求を送る"
          }
        ],
        "transitions": [
          {
            "id": "lookup-next",
            "from": "lookup",
            "to": "lookup",
            "event": "parameter-change"
          }
        ],
        "outcomes": [
          {
            "id": "translation-observed",
            "stateId": "lookup",
            "label": "変換と転送を別々に観測する"
          }
        ]
      }
    }
  ]
}
```

The example is illustrative at the value level. The field names, discriminated
union, traceability fields, interaction modes, grammar, and closed bounds in
this specification are normative. Failing schema tests pin them before
production code; the implementation plan may decompose modules but may not
silently rename or broaden the content contract.

### 6.1 Allowed diagram types

The closed v0.2.0 enum is:

- `flow`: directional work or decision path.
- `hierarchy`: containment, levels, or ownership.
- `comparison`: alternatives aligned by the same criteria.
- `state-loop`: a cycle with a recovery or feedback path.
- `causal`: cause, mechanism, consequence, and countermeasure.
- `timeline`: ordered phases, events, or rollout windows.
- `network`: bounded nodes and explicitly authored connections.
- `memory`: address, cache, storage, and locality relationships.
- `matrix`: two-dimensional classification or decision evidence.
- `state-machine`: finite states and permitted transitions.

Each type maps to a fixed renderer and CSS contract. Unknown types fail the
build. Authors cannot supply class names, style declarations, selector strings,
HTML, or layout coordinates.

### 6.2 Type-specific semantic contracts

`type` selects a discriminated `payload`; there is no universal bag of optional
nodes and edges. The validator, renderer, semantic HTML oracle, and CSS component
are selected together:

| Type | Required payload | Type invariant | Semantic HTML oracle |
| --- | --- | --- | --- |
| flow | ordered steps and labelled transitions | one start; every nonterminal step reaches a later step | ordered list with transition text |
| hierarchy | nodes with one parent reference | one root; connected and acyclic; every nonroot has one parent | nested list plus descriptions |
| comparison | alternatives, criteria, and cells | every alternative has one cell for every criterion | table with row and column headers |
| state-loop | states, transitions, exit, and recovery | at least one declared feedback cycle and one exit/recovery path | state list and complete transition list |
| causal | causes, mechanisms, outcomes, and mitigations | each outcome traces to a cause through a mechanism | definition list and labelled relation list |
| timeline | phases and ordered events | stable total order; ties require an authored lane/order key | ordered event list grouped by phase |
| network | nodes, components, and connections | every node belongs to a declared connected component | node list and endpoint-naming connection list |
| memory | ordered layers and transfers | layer order is complete; every transfer joins known layers | ordered layer list and transfer descriptions |
| matrix | row axis, column axis, and cells | complete Cartesian cell set unless an explicit not-applicable cell exists | native table with scoped headers |
| state-machine | states, initial state, and allowed/rejected transitions | one initial state; all endpoints exist; rejected transitions include a reason | state list and transition table |

The discriminated union rejects fields owned by another type. For example, a
comparison cannot quietly accept `connections`, and a hierarchy cannot encode a
second parent. The rendered oracle is tested before CSS so visual layout cannot
mask an incomplete semantic model.

The exact payload keys are `steps`/`transitions` for `flow`,
`nodes`/`parentId` for `hierarchy`, `alternatives`/`criteria`/`cells` for
`comparison`, `states`/`transitions`/`exitStateId`/`recoveryStateId` for
`state-loop`, `causes`/`mechanisms`/`outcomes`/`mitigations`/`relations` for
`causal`, `phases`/`events` for `timeline`,
`nodes`/`components`/`connections` for `network`, `layers`/`transfers` for
`memory`, `rows`/`columns`/`cells` for `matrix`, and
`states`/`initialStateId`/`transitions` for `state-machine`. Child records use
only the IDs, labels, details, references, and closed kind/status enums required
by their row above; unknown or cross-type keys fail validation.

### 6.3 Bounds and invariants

For v0.2.0, one visual is limited to:

- 64 primary structural items such as nodes, steps, rows, or states.
- 128 relationships, cells, transfers, or transitions.
- 64 simulation states and 128 simulation transitions.
- 8 groups.
- 160 Unicode scalar values per label or status.
- 600 Unicode scalar values per explanatory note.
- An overall encoded JSON budget enforced within the existing lesson budget.

All authored IDs use ASCII
`[a-z][a-z0-9]*(?:-[a-z0-9]+)*`, are 1–64 characters, and are unique within
their declared scope. One lesson has 1–2 visuals. Each visual has 1–6
`objectiveIds`, 1–8 `evidenceIds`, 1–8 `sourceIds`, 0–8 notes, a 1–160 character
caption and question, and a 1–300 character `expectedObservation`.

A simulation uses these exact common keys: `kind`, `interactionMode`,
`parameters`, `initialStateId`, `states`, `transitions`, `outcomes`, and—only for
`playback` or `hybrid`—`defaultIntervalMs`. It has 0–8 parameters, 1–64 states,
0–128 transitions, and 1–64 outcomes. `defaultIntervalMs` is an integer from 250
through 5000 inclusive and a multiple of 50. Its absence in a playback-capable
mode, or its presence in another mode, is an error.

A parameter uses `id`, `label`, `control`, `options`, and `defaultOptionId`.
`control` is `select` or `radio`; there are 2–12 `{id, label}` options and the
default references one of them. A state uses `id`, `label`, `status`, optional
closed parameter `when` mappings, and bounded `activeNodeIds`/`activeEdgeIds`.
A transition uses `id`, `from`, `to`, `event`, and optional `when`; `event` is
`next`, `previous`, `timer`, `parameter-change`, or `reset`. For any current
state, parameter selection, and event, at most one transition may match. An
outcome uses `id`, `stateId`, and `label`. Every reference is validated against
the selected diagram payload or simulation scope.

For `scenario`, every valid parameter combination matches exactly one state.
For `explorer` and `hybrid`, every valid combination reaches exactly one initial
state and a deterministic step path. Unreachable states, overlapping `when`
mappings, and a Cartesian parameter space larger than 64 combinations fail the
build.

Validation rejects duplicate object keys, unknown fields, invalid Unicode,
control or bidirectional override characters, non-finite numbers, duplicate IDs,
dangling references, disconnected required nodes, forbidden cycles, illegal
degree, empty labels, unsafe URLs, and values outside closed enums or numeric
bounds. Diagnostics are sorted and bounded so malformed input cannot create
unbounded CI output.

Cycles in the diagram payload are permitted only for `state-loop` and
`state-machine`, and only when the authored type declares them. Other directed
diagram payloads must be acyclic. Simulation state transitions follow their own
closed state-machine contract and may return to a prior state for reset,
recovery, or parameter change. A topological stage is computed at build time
where the selected diagram type requires it and is emitted deterministically;
the browser never performs layout.

### 6.4 Placement

`afterSection` is a closed enum referencing six logical lesson roles:
`why`, `mentalModel`, `workedExample`, `tradeoffs`, `knowledgeCheck`, or
`sourcesNext`. These are schema values, not authored DOM IDs. Existing lesson
IDs include both generic and lesson-prefixed forms, so the body parser maps the
six validated sections in their required order to these typed roles. The
renderer interleaves a generated figure after the selected role. Raw string
replacement, DOM-ID guessing, and arbitrary CSS selectors are not used.

The default and recommended placement is `mentalModel`. Visuals tied to a
measurement or decision table may follow `workedExample` or `tradeoffs`.

### 6.5 Existing figure migration

The current 30 lesson bodies already contain one or more semantic figures. The
feature must not leave a generic numbered figure beside a second diagram that
repeats the same facts. For each existing figure, the content migration records
one of two outcomes:

1. Migrate its caption, nodes, relationships, caveats, and reading order into a
   structured visualization, then remove only the redundant authored markup.
2. Retain it unchanged because it answers a distinct learning question.

An acceptance test and content review compare the original caption and every
meaningful list/table item with the migrated semantic output. No explanatory
fact may disappear merely because the presentation becomes visual. Runnable
commands and code examples remain authored lesson content; a diagram explains
their model or result but never replaces the executable example.

### 6.6 Learning-evidence traceability

Every visual declares at least one existing `objectiveId`, one `evidenceId`, one
stable lesson `sourceId`, and one observable `expectedObservation`. The build
rejects dangling references and verifies that each evidence ID is already
reachable from the referenced objective's evidence contract.

The content migration gives every source a stable lesson-local ID without
changing its title, URL, or kind. The visual references that ID; it does not copy
the URL or introduce a second source list.

Review records score four visual-specific dimensions with observable evidence:

1. **Technical fidelity:** every node, relation, state, caveat, and source claim
   agrees with the lesson and its cited material.
2. **Learning alignment:** the visual question and expected observation directly
   support the referenced objective and evidence artifact.
3. **Static/dynamic equivalence:** a reviewer can recover every simulation
   state, transition, parameter option, and outcome from the static oracle.
4. **Transfer value:** the learner can use the visual to explain or judge the
   worked example, lab, assessment, or a stated transfer task.

For each dimension the record uses `incomplete`, `developing`, `proficient`, or
`exemplary` and links the generated figure, objective IDs, evidence IDs, source
IDs, no-JS capture, and reviewer kind. `complete` requires at least `proficient`
in all four dimensions; automated or AI-assisted evidence is never represented
as independent human review.

## 7. Generated semantic HTML

Every visual is a `<figure>` with a unique page-local ID and a `<figcaption>`.
The essential model is rendered with native elements:

- An `<ol>` for flow, timeline, and ordered state traces.
- A `<dl>` for causal and hierarchy explanations.
- A `<table>` for matrix and comparison evidence.
- A semantically ordered node list plus relationship list for network, memory,
  state-loop, and state-machine diagrams.

Decorative connectors use CSS pseudo-elements and are absent from the
accessibility tree. The relationship list names both endpoints, so connector
position is never the only carrier of meaning.

Simulation figures also contain:

- A static parameter/options table, complete state/transition list, and outcome
  table visible without JavaScript; modes without a field omit only that empty
  structure.
- A current-step status block.
- Native controls selected by the simulation's interaction mode.
- A visible statement that the model is illustrative and deterministic.

The closed interaction modes are:

| Mode | Required controls | Appropriate use |
| --- | --- | --- |
| scenario | bounded parameter selects, apply, reset | compare a finite set of independent cases |
| stepper | previous, next, reset | inspect a sequence where autoplay would hide reasoning |
| playback | play/pause, previous, next, reset, speed 0.5x/1x/2x | observe an authored time sequence |
| hybrid | scenario controls plus playback controls | choose a fault/configuration, then observe its sequence |
| explorer | scenario controls plus stepper controls | choose a context, then inspect states without autoplay |

Parameters are closed select/radio choices generated from validated options;
v0.2.0 does not accept arbitrary text. Controls not required by the selected
mode are not rendered. Reset is required in every mode.

Controls are emitted with `hidden` and remain hidden until initialization fully
succeeds. JavaScript removes `hidden` only after validating the figure's
required DOM contract. The static figure and complete static oracle are visible first
and remain the fallback.

## 8. CSS visual system

`visualizations.css` extends the existing design tokens rather than creating a
second visual language. Each component has a structural base class and one
closed meaning class generated by the renderer.

### 8.1 Meaning patterns

- Flow diagrams use a left-to-right path when space allows and a vertical
  document-order path on narrow viewports.
- Hierarchies use nested grouping and borders, not indentation alone.
- Causal diagrams pair cause and consequence with a labelled mechanism.
- Comparisons and matrices keep criteria aligned and retain native table
  semantics.
- Timelines expose sequence with ordered markers and phase labels.
- Networks use a bounded build-time stage grid and an adjacent relationship
  list; arbitrary coordinates are forbidden.
- Memory diagrams show address translation and storage distance as conceptual
  layers, with explicit warnings against interpreting size as universal latency.
- State diagrams pair current state, permitted transition, and rejected
  transition. Color is supplementary to text and shape.

### 8.2 Responsive, print, and failure behavior

- At 320 CSS pixels, the visual becomes a single-column reading sequence with
  no horizontal page scroll.
- At 200% and 400% zoom, controls reflow and text remains readable without
  clipping.
- Print hides controls and motion-only decoration, then expands the complete
  semantic trace and relationship list.
- If CSS fails, the native lists, descriptions, and tables preserve the same
  facts in document order.
- CSS does not use generated textual content for essential information.

## 9. Progressive JavaScript runtime

Only the 12 simulation pages include a relative, deferred classic script:

```html
<script src="../../static/visualization.js" defer></script>
```

The renderer calculates the relative prefix; the literal shown above is one
nested-lesson example. A classic script is used instead of an ES module so the
same artifact can be exercised over `file://` without module CORS differences.

The runtime is one dependency-free file with a raw size budget of 40 KiB. It
uses event delegation within each validated figure and a finite deterministic
state machine. Its permitted operations are:

- Read closed enum, integer, and ID values already emitted by the build.
- Change the current step and a small set of renderer-owned state attributes.
- Start one bounded timer for autoplay and cancel it on pause, reset, page hide,
  completion, or figure failure.
- Update the existing status text and control labels with `textContent`.

The DOM serialization and mutation allowlist is exact. The runtime may read
`id`, `data-visualization-id`, `data-simulation-kind`,
`data-interaction-mode`, `data-initial-state-id`, `data-state-id`,
`data-node-id`, `data-edge-id`, `data-step-index`,
`data-default-interval-ms`, `data-parameter-id`, `data-option-id`,
`data-transition-id`, `data-transition-event`, `data-from-state-id`,
`data-to-state-id`, `data-outcome-id`, and `data-action`. Parameter and option
attributes encode only the validated finite selection; transition attributes
encode the authored closed event enum (`next`, `previous`, `timer`,
`parameter-change`, or `reset`) and validated endpoints; action values are the
fixed renderer-owned control enum. A condition-bearing element must carry both
parameter and option attributes, and an element carrying either one without the
other is invalid. No other `data-*` attribute is read by the runtime. It may
change only the native
`hidden` and `disabled` properties, `aria-current` with the fixed value `step`,
`aria-pressed` with `true`/`false`, `textContent` on renderer-owned status and
play-label nodes, and the fixed classes `is-enhanced`, `is-active`,
`is-complete`, and `has-runtime-error`. Values are validated IDs, bounded
integers, or fixed literals; authored text is never passed to a selector.

Scenario mode is the deliberate edge-free exception: its authored transition
set is empty, Apply resolves the unique state in the validated finite parameter
partition, and Reset restores `data-initial-state-id`. Missing or overlapping
partition entries fail before enhancement. Event-keyed transitions remain
mandatory for state movement in every non-scenario mode.

For every finite parameter selection in a non-scenario mode, each reachable
non-initial state has exactly one applicable `reset` edge whose target is the
authored initial state. Missing, duplicate, misdirected, or selection-specific
reset gaps fail in both schema and runtime DOM validation.

The runtime must not use `fetch`, XMLHttpRequest, WebSocket, EventSource,
dynamic `import()`, Worker, Service Worker, storage APIs, query/hash state,
clipboard, navigation, `eval`, `Function`, `innerHTML`, `outerHTML`, DOMParser,
`insertAdjacentHTML`, runtime style injection, or remote resources.
Browser authority is also closed: `globalThis`, `navigator`, `self`, `top`,
`parent`, `document.defaultView`, and bare `window` values are forbidden. The
handwritten first-party runtime may use only complete direct calls to
`window.matchMedia`, `window.setTimeout`, `window.clearTimeout`, and
`window.addEventListener` measured from the reviewed artifact. Extracting those
members or continuing the rooted expression through another property,
computed member, or constructor is invalid.
The closed source grammar also rejects `constructor`, `prototype`, and
`__proto__` in executable code and in concatenated computed member names.
`document` is limited to the complete direct `querySelectorAll` call used by
the fixed asset; it is never accepted as a value.

There is no continuous `requestAnimationFrame`, polling loop, document-wide
MutationObserver, or browser graph-layout algorithm. Runtime complexity for one
transition is O(V + E), and the page is idle when no transition is running.

### 9.1 Initialization and failure contract

Initialization is per figure and transactional:

1. Find a renderer-owned simulation root.
2. Validate required controls, unique IDs, step count, references, and numeric
   bounds from the DOM.
3. Build the in-memory state without changing the visible fallback.
4. Apply the initial state.

Timer transitions always synchronize the visible current-state text, while a
separate visually hidden polite live region is updated only for explicit user
actions. This avoids repeated playback announcements. With reduced motion,
play, pause, and speed are disabled and the visible/live status explains why.
Scenario Reset restores every parameter control to its authored default before
restoring the matching initial state. A persisted `pageshow` after `pagehide`
repeats transactional initialization from the exact fallback snapshot; global
and per-control listeners remain singletons and failure stays in fallback.

Generated deferred script elements are direct children of `body` and have no
non-whitespace data, character/entity reference, or comment content. The model
validator, generated-document validator, build parser, and release checker all
enforce the same empty, explicitly paired external-script contract; non-void
self-closing syntax such as `<script />` is malformed.
5. Reveal controls and mark the root as enhanced.

Any exception before step 5 leaves the complete static figure visible. Any
exception afterward cancels the timer, removes every enhancement class and
mutable ARIA attribute, restores native `hidden`/`disabled` properties and all
steps to their original renderer state, hides the controls, and sets an existing fallback message to
“動的表示を利用できません。静的図を表示しています。” No exception from one
figure may prevent another figure or the lesson from working.

## 10. Simulation inventory

The v0.2.0 simulations are fixed to these 12 lessons:

| Lesson | Simulation | Mode | Learner-controlled change | Static equivalent |
| --- | --- | --- | --- | --- |
| core-02 | complexity-growth | scenario | input size and algorithm family | value table and ordered curve samples |
| core-03 | memory-access | hybrid | working-set class and access order | cache/TLB/memory path plus all states |
| core-04 | scheduler-interleaving | playback | next thread step | complete interleaving trace and invariant table |
| core-05 | request-path | hybrid | latency/failure injection point | DNS/TCP/TLS/request phase list |
| core-07 | retry-contract | playback | request, timeout, retry, idempotency outcome | request/response/retry sequence |
| core-12 | isolation-schedule | hybrid | transaction step and isolation choice | schedule table and anomaly explanation |
| core-13 | distributed-failure | hybrid | duplicate, reorder, partition, recovery step | event log and state transition list |
| core-14 | queue-capacity | scenario | load band and worker capacity | load/queue/tail-latency comparison table |
| core-15 | slo-burn | scenario | error-window scenario | SLI/SLO/burn calculation table |
| core-16 | accessible-ui-state | explorer | viewport, focus step, motion preference | focus order and reflow checklist |
| core-22 | migration-phase | playback | expand, migrate, contract phase | compatibility matrix and phase timeline |
| core-24 | release-safety | playback | build, attest, canary, promote, rollback | provenance and release-gate state machine |

All controls select from authored finite parameters, states, transitions, and
outcomes. v0.2.0 does not accept free-form text input. Any pseudo-random ordering
uses a checked-in deterministic seed and must reproduce byte-for-byte expected
traces in tests.

`content/visualization-catalog.json` contains these 12 exact lesson, kind, mode,
and static-equivalent assignments. The build compares the complete key set and
every value with lesson JSON; additions, omissions, type drift, or a second
source of defaults fail validation.

## 11. Static visual inventory for all 30 lessons

Every lesson receives the primary diagram shown below. The secondary type may
be used only when it answers a distinct question. “Dynamic” means the lesson is
also in the simulation inventory above.

| Lesson | Primary | Optional secondary | Dynamic |
| --- | --- | --- | --- |
| core-01 | causal | matrix | No |
| core-02 | comparison | flow | Yes |
| core-03 | memory | matrix | Yes |
| core-04 | timeline | state-machine | Yes |
| core-05 | timeline | comparison | Yes |
| core-06 | network | state-machine | No |
| core-07 | state-machine | timeline | Yes |
| core-08 | network | matrix | No |
| core-09 | state-loop | matrix | No |
| core-10 | network | matrix | No |
| core-11 | matrix | flow | No |
| core-12 | timeline | network | Yes |
| core-13 | timeline | state-machine | Yes |
| core-14 | causal | comparison | Yes |
| core-15 | state-loop | timeline | Yes |
| core-16 | flow | matrix | Yes |
| core-17 | flow | comparison | No |
| core-18 | causal | matrix | No |
| core-19 | hierarchy | comparison | No |
| core-20 | causal | matrix | No |
| core-21 | network | state-loop | No |
| core-22 | state-machine | timeline | Yes |
| core-23 | timeline | causal | No |
| core-24 | state-machine | network | Yes |
| core-25 | matrix | comparison | No |
| core-26 | state-loop | matrix | No |
| core-27 | network | matrix | No |
| core-28 | flow | hierarchy | No |
| core-29 | timeline | matrix | No |
| core-30 | causal | matrix | No |

The visualization catalog contains the exact 30 lesson IDs, required primary
type, allowed optional secondary type, dynamic flag, and—where dynamic—the
simulation kind, mode, static-equivalent ID, and three visual-regression state
IDs. Tests compare the entire catalog projection with both tables in this
specification and with rendered lessons. A correct count with a swapped type or
kind is a failure.

The domain-model lesson uses a static bounded-context network because time does
not improve that relationship. The API lesson then animates communication,
failure, retry, and idempotency across those kinds of boundaries.

## 12. Accessibility contract

The target remains WCAG 2.2 Level AA as a product and review standard.

- Semantic lists, descriptions, tables, captions, headings, and button names are
  the primary information channel.
- Keyboard focus order follows document order. Simulation does not move focus.
- Native controls have visible focus indicators and at least a 24 by 24 CSS
  pixel target.
- Current step uses visible text and `aria-current="step"`; it is not indicated
  by color or motion alone.
- The status region uses polite announcements only after an explicit learner
  action. Autoplay does not announce every frame.
- `prefers-reduced-motion: reduce` disables autoplay and transitions. Manual
  previous/next controls remain usable.
- Forced-colors mode uses system colors, borders, and `currentColor`; essential
  UI does not opt out with `forced-color-adjust: none`.
- Controls, status, and visual nodes reflow at 320 pixels and 400% zoom.
- High contrast, CSS-disabled reading order, print, and screen-reader output are
  release-gate scenarios rather than visual spot checks.
- Pointer hover may add emphasis but can never reveal unique information.

## 13. Security and privacy contract

The site remains local-first, telemetry-free, and unable to communicate with a
server. The exact v0.2.0 CSP candidate is:

```text
default-src 'none'; script-src 'self'; script-src-attr 'none'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'none'; worker-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'
```

This is a versioned policy change, not a silent relaxation. The base template,
renderer contract, site checker, mutation tests, README, content standard,
security documentation, and release evidence must change together.

The policy is delivered by a meta element so the built site also works over
`file://`. `frame-ancestors` is not enforced from meta CSP and GitHub Pages does
not provide this repository with arbitrary response-header control. The release
therefore does not claim clickjacking prevention. This residual limitation is
documented rather than weakening or overstating the test result.

Additional rules:

- No inline script, inline event handler, inline style, external script, remote
  font, remote image, iframe, form, object, or embedded active content.
- All asset URLs are build-generated relative paths beneath `static/`.
- The site checker parses and compares the complete directive map and rejects
  missing, duplicate, weakened, or extra directives.
- The CSP meta element is the first security-sensitive element in `<head>` and
  appears before every stylesheet, script, preload, or other resource-bearing
  element; the checker rejects placement drift.
- Browser evidence over both `file://` and the Pages-style subpath contains no
  unexpected CSP violation or external request.
- Lesson JSON is treated as untrusted build input even though it is reviewed in
  the repository.
- Runtime code uses closed selectors owned by the renderer and never interprets
  contributor-authored strings as markup, code, URLs, or selectors.
- No learner data is collected, retained, transmitted, or encoded into a URL.

If a future visual needs Mermaid, arbitrary SVG, a remote library, or a broader
CSP, that work requires a separate threat model and design decision.

## 14. Determinism and performance

The same checked-in input must produce byte-identical generated output across
timezone, locale, file modification time, directory enumeration order, and two
fresh builds.

- Nodes, edges, groups, and steps retain validated authored order where order
  is pedagogical; otherwise the schema defines one stable sort key.
- IDs are deterministic functions of the lesson ID and visualization ID.
- No build timestamp, random runtime ID, viewport-derived layout, or network
  result enters generated HTML.
- `visualization.js` is copied byte-for-byte and included only on simulation
  lessons. Build and release checking independently require the exact bytes to
  match the versioned reviewed SHA-256 constant; the bounded source lexer is
  defense in depth rather than the primary trust boundary. Updating that
  constant requires reviewing the runtime diff, running DOM/security tests,
  independently calculating SHA-256, and committing the literal digest. Tests
  neither derive nor rewrite the accepted digest.
- A transition is O(V + E), does not perform forced layout in a loop, and leaves
  no active timer at completion.

`tests/browser-matrix.json` pins the release measurement environment: runner
image/digest, architecture, browser build, viewport, device scale factor, CPU
throttle, fixture hash, and harness version. The primary desktop profile is
1440x900 at device scale 1 without throttling. The mobile profile is 390x844 at
device scale 2 with 4x CPU throttling. Any change to the matrix is a reviewed
test-contract change, not an implicit CI update.

The maximum-bound 64-item/128-relationship fixture and the heaviest real memory
and distributed-failure simulations receive 3 warm-up runs and 20 measured
runs. On desktop, the median transition is at most 25 ms and at least 19 of 20
runs contain no task over 50 ms. On the mobile profile, the median is at most 50
ms and the 95th percentile is at most 100 ms. Raw samples, browser version, and
fixture hash are retained as release evidence.

The leak gate runs 100 complete play/reset or explore/reset cycles in the pinned
browser with an instrumented listener/timer registry. At completion the DOM node
count, listener count, and active timer count equal the post-initialization
baseline. In the dedicated browser process where explicit GC is enabled, two GC
cycles leave retained-heap growth below the larger of 1 MiB or 5% of baseline.
If GC or instrumentation is unavailable, the leak gate is not marked passed.

The checker enforces a 40 KiB raw JavaScript budget, an 80 KiB raw
`visualizations.css` budget, at most one JavaScript asset per lesson, at most 96
KiB of generated visualization HTML per lesson, and at most 512 KiB for any
complete lesson HTML file. A larger budget requires a documented ADR with
measured learner value and performance evidence.

## 15. Error handling

### 15.1 Build-time failures

Invalid visualization input fails closed before `site/` is atomically replaced.
The previous complete output remains intact. Errors identify lesson, visual, and
field without echoing unbounded attacker-controlled content.

The build rejects:

- Missing visuals for a complete core lesson.
- A simulation outside the approved 12-lesson inventory.
- A simulation whose static equivalent is absent.
- Duplicate, dangling, disconnected, cyclic, overlarge, or unknown schema data.
- Unsafe authored body placement or multiple visuals targeting an invalid
  section boundary.
- Asset inventory, CSP, or template drift.

### 15.2 Runtime failures

JavaScript failure is a loss of enhancement, never a loss of lesson content.
404, syntax error, initialization error, DOM mismatch, and timer cancellation
are tested independently. The learner always retains caption, semantic model,
complete static parameter/state/transition/outcome oracle, lab, and assessment.

## 16. TDD and verification strategy

Implementation follows RED-GREEN-REFACTOR in small commits. Each behavior begins
with the narrowest failing unit or acceptance test, and every production change
is followed by the relevant focused suite before the full gate.

### 16.1 Model and renderer tests

- Accept one minimal instance of every diagram type.
- Reject every unknown field, enum, reference, bound, character class, and
  forbidden cycle.
- Mutate each CSP directive and prove the checker rejects it.
- Prove every structured string is escaped and no authored value becomes a
  class, selector, URL, style, or HTML fragment.
- Prove the full lesson set, every primary/allowed-secondary type, and every
  simulation kind/mode/static-equivalent mapping exactly matches
  `content/visualization-catalog.json`; correct counts with swapped assignments
  fail.
- Prove each simulation contains a complete static trace.
- Prove each visual's objective, evidence, and source references resolve and its
  four-dimension review record meets the required level.
- Prove two fresh builds are byte-identical under changed locale, timezone,
  mtime, and input enumeration order.

### 16.2 Runtime tests

- Load each simulation over both `file://` and a GitHub Pages-style subpath.
- Verify only the controls required by each interaction mode are rendered and
  that scenario, stepper, playback, hybrid, and explorer behaviors all work.
- Verify reduced motion prevents autoplay.
- Verify controls stay hidden on script 404, syntax failure, invalid DOM, and
  initialization exception.
- Inject failure before and after every permitted DOM mutation, during a manual
  transition, inside a timer callback, and after status `textContent` changes;
  verify timer cancellation, complete `hidden`/`disabled`/ARIA/class restoration,
  full static trace visibility, and isolation from every other figure.
- Verify no network request, storage write, navigation mutation, inline script,
  dynamic code execution, or undeclared asset occurs.
- Verify independent figures do not share timers or state.
- Verify deterministic end state after repeated runs and seed-controlled paths.
- Verify idle CPU, bounded long tasks, and no growth after 100 reset cycles.

### 16.3 Accessibility and visual tests

- Keyboard-only operation and visible focus.
- Screen-reader reading order, control names, current-step state, and restrained
  announcements.
- 320-pixel viewport, 200% and 400% zoom, forced-colors, high contrast, CSS
  disabled, reduced motion, and print.
- Long Japanese strings, mixed Japanese/English technical terms, and layout
  wrapping without clipping.
- Static screenshots for every diagram type and every visual-regression state
  ID declared for all 12 simulations, under the pinned desktop/narrow/reduced-
  motion/forced-colors profiles.

Automated browser runs use the exact pinned build in
`tests/browser-matrix.json`. Before release, `file://` and Pages-style subpath
smoke tests also run in the then-current stable Chromium, Firefox, and Safari on
macOS, with exact OS/browser versions recorded. An unavailable or unexecuted
required browser is a blocked release, not a pass or skip. A browser may be
removed only through a reviewed specification change with a documented reason.

Browser automation is evidence, not the only oracle. Semantic assertions,
checker assertions, and human visual review all remain required.

### 16.4 Full release gate

The release gate runs:

1. Python unit, property-style boundary, mutation, and acceptance tests.
2. Deterministic clean builds and complete site inventory checks.
3. HTML, link, CSP, asset, and no-external-request checks.
4. Runtime browser tests over `file://` and Pages-style HTTP subpaths.
5. Accessibility, print, reduced-motion, forced-colors, and zoom scenarios.
6. Performance and reset-cycle leak checks.
7. Security scan and dependency inventory proving the runtime remains
   first-party and dependency-free.
8. Manual content review that diagrams are accurate, useful, and not merely
   decorative.
9. A release manifest binding merge SHA to every tested HTML/CSS/JS path, size,
   and SHA-256; the Pages deployment must consume that exact uploaded artifact.
   After deployment, downloaded Pages bytes are compared with the manifest (or
   an equivalent Pages artifact attestation is verified) before the release is
   declared complete.

If selective-impact analysis fails, returns an unknown result, or identifies
zero targets for a changed contract, the complete release gate runs. A skipped
test is not a passing result.

## 17. Documentation and OSS contribution model

The feature updates:

- `README.md` and `README.en.md` to describe the v0.2.0 progressive-enhancement
  contract without rewriting v0.1.0 history.
- `docs/content-standard.md` with diagram questions, schema examples, static
  equivalents, source expectations, and accessibility review steps.
- `CONTRIBUTING.md` with TDD commands and a visual contribution checklist.
- `SECURITY.md` with the first-party runtime boundary and reporting guidance.
- `CHANGELOG.md` with the user-visible visual-learning change.
- Pull-request templates with no-JS, reduced-motion, keyboard, CSP, and
  deterministic-build evidence fields.

An OSS contributor should be able to add or improve a diagram by changing
validated data and content, without learning a private CSS convention or
writing JavaScript. Adding a new diagram type or simulation kind requires tests,
documentation, accessibility evidence, security review, and maintainer approval.

## 18. Delivery sequence

1. **Contract migration:** failing tests for v0.2.0 docs, CSP, asset inventory,
   and the new semantic/no-JS promise.
2. **Domain model:** strict visualization models, bounds, graph validation, and
   deterministic diagnostics.
3. **Semantic renderer:** insertion at typed lesson sections and complete static
   equivalents.
4. **CSS kit:** one representative lesson per diagram type, responsive/print/
   forced-colors validation, then rollout to all 30 lessons.
5. **Runtime foundation:** transactional initialization and shared controls with
   failure-path tests.
6. **Twelve simulations:** implement in pedagogical clusters—computation and
   memory, concurrency and communication, data and distributed systems,
   reliability and delivery.
7. **Documentation and contributor path:** examples, review checklist, and
   security guidance.
8. **Release validation:** clean build, complete tests, browser/accessibility/
   performance evidence, self-review, PR review, Pages preview, and v0.2.0
   release decision.

Each phase is a reviewable commit or small commit series. The feature branch is
merged through GitHub Flow only after required CI and review evidence is green.
The merged branch is then removed locally and remotely after verifying the
actual merged state.

## 19. Acceptance criteria

The work is complete only when all of the following are evidenced:

- All 30 lessons contain at least one accurate meaning-based CSS diagram in
  addition to the existing explanation.
- The approved 12 lessons contain deterministic simulations with the exact
  scenario/stepper/playback/hybrid/explorer controls assigned by the catalog;
  every mode supports reset and only playback-capable modes expose speed.
- With JavaScript disabled or broken, every page still exposes the full model,
  every parameter option, state, transition, outcome, lesson section, lab,
  assessment, and source.
- The built site works by opening `site/index.html` directly and from a GitHub
  Pages subpath.
- No external request, analytics, account, storage, server API, or third-party
  runtime dependency exists.
- CSP and site inventory match the exact v0.2.0 contract.
- Keyboard, screen-reader, reduced-motion, forced-colors, zoom, narrow viewport,
  CSS-disabled, and print evidence passes.
- Builds are byte-deterministic and the JavaScript/performance/leak budgets pass.
- Security and self-review find no unresolved critical or high-severity issue.
- README, content standard, contribution guide, security policy, and changelog
  match the implemented behavior.
- The PR is actually merged, GitHub Pages serves the verified merge commit, and
  its served HTML/CSS/JS bytes match the tested manifest or verified Pages
  artifact attestation before obsolete merged branches are removed without
  touching preserved user work.

## 20. Deferred decisions

The following require separate evidence and are intentionally deferred:

- More than two visuals or one simulation per lesson.
- Interactive catalog search or progress tracking.
- Learner-authored diagrams or arbitrary data import.
- Mermaid, SVG authoring, Canvas, WebGL, third-party packages, or server-backed
  simulations.
- Automated personalization or spaced repetition.
- Runtime persistence, URL-addressable simulation state, or telemetry.

These are not prerequisites for an expert-quality visual textbook. The v0.2.0
priority is a complete, inspectable, accessible explanation that becomes more
explorable—not less understandable—when JavaScript succeeds.
