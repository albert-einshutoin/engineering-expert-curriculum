# Static OSS Engineering Curriculum — Design Specification

Date: 2026-07-30

Status: Approved for implementation

License: MIT

Primary language: Japanese

## 1. Purpose

Turn the existing engineering curriculum prototype into an OSS textbook that
helps learners build the judgment, practical skill, and professional habits
expected of globally effective engineers.

The project retains all 1,140 existing curriculum items as a searchable-by-
browser static catalog. It promotes 30 cross-cutting lessons into a curated core
and rewrites those lessons to a higher standard: explicit prerequisites,
evidence-backed explanations, hands-on labs, assessment criteria, and links to
recognized competency frameworks.

The published site must work by opening `site/index.html` directly with a
browser. The runtime contains HTML and CSS only. JavaScript is explicitly
excluded from the first release.

## 2. Product principles

1. **Depth over inflated lesson count.** The 1,140 items describe the knowledge
   space; the 30 core lessons provide the textbook experience.
2. **Practice and proof.** Every core lesson ends with work a learner can
   perform and evidence a reviewer can assess.
3. **Judgment before recipes.** Lessons explain trade-offs, failure modes, and
   decision criteria instead of presenting one universal answer.
4. **Static and durable.** The site works over `file://`, on GitHub Pages, in
   print, and without a client-side runtime.
5. **Accessible by construction.** Semantic HTML remains understandable when
   CSS is absent, high contrast is enabled, or the page is printed.
6. **Open development.** The repository makes content gaps, evidence standards,
   corrections, and review expectations visible to contributors.

## 3. Scope

### 3.1 First public release

- A Hybrid landing page: Atlas-style overview leading to Textbook-style lessons.
- A static catalog preserving 1,140 unique curriculum items.
- Thirty curated core lessons.
- A prerequisite roadmap and competency relationship graph rendered with HTML
  and CSS.
- A CS2023, SWEBOK, and SFIA competency matrix.
- Three integrated capstones.
- Coverage for HCI, graphics, maintenance, professional practice, economics,
  communication, and OSS development.
- Contributor, governance, security, correction, and review documentation.
- Reproducible build, schema validation, link checks, accessibility checks, and
  GitHub Actions CI.
- GitHub Pages deployment of the generated static site.

### 3.2 Explicitly excluded from the first release

- JavaScript, client-side search, filtering, progress persistence, accounts, or
  analytics.
- Server-side APIs, databases, authentication, or hosted learner data.
- Automated spaced repetition. A printable review schedule is provided instead.
- Full deep rewrites of all 1,140 catalog entries.
- User-supplied HTML or content editing through the published site.

These exclusions keep the first release inspectable, portable, and safe. They
can be reconsidered through future design specifications.

## 4. Chosen approach

Use a small Python standard-library build system. Version-controlled content and
templates are the source of truth; the build produces a self-contained `site/`
directory.

This approach was selected over:

- Hand-maintained HTML, which would duplicate navigation and make consistency
  checks expensive.
- A third-party static-site generator, which would add toolchain and dependency
  maintenance without improving the required HTML/CSS runtime.

Python is used only at build and validation time. A learner or reader does not
need Python to open the generated site.

## 5. Repository structure

```text
.
├── content/
│   ├── catalog.json
│   ├── competencies.json
│   ├── roadmap.json
│   ├── capstones/
│   │   └── *.json
│   └── lessons/
│       └── <lesson-id>/
│           ├── lesson.json
│           └── body.html
├── curriculum_builder/
│   ├── __init__.py
│   ├── catalog.py
│   ├── graph.py
│   ├── models.py
│   ├── render.py
│   └── validation.py
├── templates/
│   ├── base.html
│   ├── catalog.html
│   ├── capstone.html
│   ├── competency-matrix.html
│   ├── index.html
│   ├── lesson.html
│   └── roadmap.html
├── static/
│   └── styles.css
├── tests/
│   └── test_*.py
├── tools/
│   ├── build.py
│   └── migrate_prototype.py
├── docs/
│   ├── architecture/
│   ├── content-standard.md
│   ├── curriculum-map.md
│   └── superpowers/specs/
├── site/                 # generated and gitignored
├── .github/
│   ├── ISSUE_TEMPLATE/
│   ├── workflows/
│   └── pull_request_template.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── GOVERNANCE.md
├── LICENSE
├── README.md
├── SECURITY.md
└── pyproject.toml
```

Modules have narrow responsibilities:

- `models.py` converts raw dictionaries into validated immutable domain values.
- `catalog.py` imports and groups the 1,140 catalog items.
- `graph.py` validates prerequisite references, detects cycles, and produces
  deterministic learning stages.
- `validation.py` enforces content, HTML safety, competency, and capstone rules.
- `render.py` escapes structured data and renders trusted, validated templates.
- `tools/build.py` is the thin command-line orchestrator.
- `tools/migrate_prototype.py` performs a checksum-verified, one-time migration.

No module performs network access.

## 6. Content model

### 6.1 Catalog item

Each catalog item has:

- Stable `id`
- Japanese `title`
- `domain` and `module`
- Ordered `concepts`
- `level`
- Optional `coreLessonId`

The build rejects duplicate IDs, empty titles, unknown domains, and references
to missing core lessons. The catalog page groups entries by domain and provides
an anchor index so the browser's built-in Find feature remains useful without
JavaScript.

### 6.2 Core lesson

Each `lesson.json` contains:

- Stable ID, title, summary, stage, and difficulty
- Estimated study time
- Explicit prerequisite lesson IDs
- Three to six measurable learning objectives
- Competency mappings with framework, identifier, and rationale
- At least two authoritative or primary sources
- Last-reviewed date and content status
- Lab metadata
- Assessment metadata
- Rubric dimensions and four performance levels
- Review prompts and a printable review schedule

`body.html` is an authored semantic fragment. It must contain:

1. Why this matters
2. Mental model
3. Worked example
4. Trade-offs and failure modes
5. Practical lab
6. Knowledge checks
7. Transfer task
8. Rubric
9. Sources and further study

The validator rejects scriptable or embedding elements, inline event handlers,
unsafe URL schemes, forms, and inline styles in lesson bodies. Authored body
fragments are repository-controlled, reviewed input; structured values are
always HTML-escaped by the renderer.

### 6.3 Definition of textbook quality

A lesson may display the `complete` status only when:

- Every required section and metadata field exists.
- Objectives use observable verbs and map to lab or assessment evidence.
- The worked example contains a concrete decision and its trade-offs.
- The lab produces a reviewable artifact.
- Assessment answers include reasoning, not only the correct option.
- The rubric distinguishes incomplete, developing, proficient, and exemplary
  work using observable evidence.
- Sources are relevant, reachable HTTPS links, and include primary or
  standards-based material where available.
- The content has passed technical, pedagogical, accessibility, and editorial
  review.

CI treats any lesson marked complete but failing this contract as an error.

## 7. Curated core

The first release contains these 30 lessons:

### Foundations

1. Systems thinking and engineering trade-offs
2. Algorithms, complexity, and measurement
3. Computer architecture, memory, and caches
4. Operating systems, processes, and concurrency
5. Networks, protocols, latency, and failure

### Build trustworthy software

6. Requirements and domain modeling
7. API and contract design
8. Modularity and evolutionary architecture
9. Test strategy and test-driven development
10. Threat modeling and secure-by-design development

### Data and scale

11. Data modeling and storage selection
12. Transactions, isolation, and consistency
13. Distributed coordination and partial failure
14. Performance profiling and capacity reasoning
15. Reliability, observability, and service objectives

### Human and product systems

16. HCI, usability, and accessibility
17. Graphics, rendering, and visual information
18. Product discovery and evidence-based experiments
19. Technical communication and design documents
20. Professional ethics, privacy, and societal impact

### Sustain and operate

21. Maintenance and legacy-system comprehension
22. Software evolution and safe migrations
23. Incident response and learning reviews
24. Delivery systems, CI/CD, and release safety
25. Engineering economics, cost, and capacity

### Lead and contribute

26. Code review and collaborative quality
27. Team interfaces and socio-technical architecture
28. OSS contribution, governance, and stewardship
29. Cross-cultural collaboration and async communication
30. Evidence-based technical leadership

Catalog items outside this core remain visible and can be promoted through a
future content proposal without changing their stable IDs.

## 8. Roadmap and competency model

`roadmap.json` is the canonical directed acyclic graph. Edges point from a
prerequisite to the lessons it unlocks. The build:

1. Confirms every referenced node exists.
2. Detects self-references and cycles.
3. Calculates deterministic learning stages.
4. Confirms all 30 core lessons are reachable.
5. Produces a textual ordered list and the CSS-enhanced graph from the same data.

The published graph is an ordered list with headings, links, and relationship
text. CSS Grid arranges stages on wide screens; borders and pseudo-elements draw
connectors. On narrow screens and in print it becomes a single vertical path.
Meaning never depends on connector lines or color.

`competencies.json` maps lessons and capstones to these versioned baselines,
verified against their official sources on 2026-07-30:

- [ACM/IEEE-CS/AAAI Computer Science Curricula 2023][cs2023] final report,
  endorsed in 2024
- [IEEE Computer Society SWEBOK Guide V4.0a][swebok] knowledge areas, the 2025
  minor revision of Version 4
- [SFIA 9][sfia] skills and responsibility levels

Every mapping includes a short rationale. The site renders the matrix as a
captioned HTML table with row and column headers. Framework names and versions
are displayed so future updates can be reviewed explicitly. A scheduled
quarterly issue checks official release pages; a new framework version requires
a dedicated mapping-review PR rather than an automatic version replacement.

[cs2023]: https://csed.acm.org/
[swebok]: https://www.computer.org/education/bodies-of-knowledge/software-engineering
[sfia]: https://sfia-online.org/en/the-sfia-framework

## 9. Integrated capstones

### Capstone 1 — Design and operate a global service

Design a small multi-region service from requirements through API, data model,
threat model, reliability targets, observability plan, cost estimate, and
incident exercise.

Evidence includes an architecture decision record, runnable or simulated test
evidence, service-level objectives, a failure analysis, and a reviewer rubric.

### Capstone 2 — Evolve a legacy system safely

Analyze an unfamiliar system, identify risk and technical debt, design a
strangler or staged migration, preserve compatibility, and communicate the
rollout to technical and non-technical stakeholders.

Evidence includes a system map, characterization tests, migration plan,
rollback criteria, economics analysis, and maintenance runbook.

### Capstone 3 — Launch and steward an OSS product

Turn a useful prototype into a contributor-ready public project with an
accessible interface, appropriate visual communication, automated quality
gates, security policy, governance, issue templates, and a sustainable roadmap.

Evidence includes the public repository, contribution journey, release
artifact, threat model, accessibility review, governance decisions, and a
maintainer handoff.

Each capstone has milestones, constraints, review questions, and a four-level
rubric. Together they must exercise every curated-core category.

## 10. Information architecture and visual system

The approved Hybrid direction uses:

- **Atlas landing and roadmap pages** for orientation and relationships.
- **Textbook lesson pages** for focused reading and practice.
- **Reference pages** for the catalog, competency matrix, glossary, and
  contribution standards.

Navigation remains consistent: Home, Roadmap, Core Lessons, Catalog, Capstones,
Competency Matrix, and Contribute.

The design system uses CSS custom properties for:

- Ink, paper, muted text, border, accent, success, and warning colors
- A serif reading face with a system sans-serif interface face
- A modular spacing scale
- Maximum reading width and wide reference-table width
- Focus, border, shadow, and print tokens

The visual language is editorial rather than dashboard-like. Warm paper
surfaces, restrained teal and rust accents, strong typographic hierarchy, and
visible source/rubric panels distinguish the site from a generated course list.

Required responsive states are narrow mobile, reading width, wide roadmap, and
print. CSS contains no animation necessary for comprehension.

## 11. Build and data flow

```text
catalog + lessons + roadmap + competencies + capstones
                         │
                         ▼
              parse into domain models
                         │
                         ▼
           validate schema, graph, safety, links
                         │
                         ▼
               render deterministic pages
                         │
                         ▼
                  site/ HTML + CSS
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
         local file://         GitHub Pages
```

The build writes to a temporary directory, validates the complete output, then
atomically replaces `site/`. A failed build does not leave a partially updated
site. Output ordering and timestamps are deterministic so identical input
produces identical content.

## 12. Prototype preservation and migration

The existing prototype is not deleted.

Before public-repository files replace the current root layout:

1. Enumerate the existing prototype files using an explicit allowlist.
2. Calculate SHA-256 checksums and a file-count/byte-count manifest.
3. Copy while retaining the source into `.archive/prototype-v1/`.
4. Recalculate and compare checksums.
5. Stop immediately if any file is absent or changed; retire the source only in a
   separate reviewed task.

`.archive/` and `.superpowers/` remain local and gitignored. The public
repository receives the canonical catalog data and new authored content, not
the 1,140 duplicated generated HTML pages. The migration tool is one-shot and
rerun-safe: it never clobbers an existing archive.

Before running the tool, the operator prepares the archive parent through a
root-to-repository `dir_fd` traversal: open `/`, then each absolute repository
path component with `O_DIRECTORY|O_NOFOLLOW`. Through the pinned repository FD,
create `.archive` with mode `0o700` only when absent; record its no-follow
identity, open it with the same flags, and compare `fstat` identity before
validating its directory type, owner, and permissions. This rejects intermediate
or final symlinks and existing non-directories, foreign owners, or
group/world-writable directories without changing them. If this creates a new
parent, it is `0o700` (subject to umask). After validation, `fsync` the pinned
archive FD and then the pinned repository FD that holds its name. This sequence
is required for every valid parent, new or existing, so a retry can repair a
prior repository `fsync` failure and complete the durability boundary. Every
preparation `fsync` failure stops the migration before it begins. Every opened
FD is closed, and close failures are reported rather than retried through a
pathname.

The tool requires that parent to already exist as a canonical directory owned by
the current effective user and not group/world writable. It never creates or
deletes the parent: this removes `mkdir`/`stat` ownership races and lets its
validation helper return the same pinned file descriptor it verified, rather
than reopening the pathname.

It builds the copy, checksum verification, and manifest in a randomly named
private staging directory below the archive parent. Regular data files, nested
directories, the staging root, and the manifest are `fsync`ed before publication;
the staging root is also `fsync`ed after its internal manifest rename. The only
publication commit point is a no-overwrite native directory rename:
`renameatx_np(RENAME_EXCL)` on macOS or `renameat2(RENAME_NOREPLACE)` on Linux.
The parent file descriptor is `fsync`ed immediately after that rename so the
final name is durable. If this final fsync fails, the tool raises
`PrototypePublicationDurabilityError`: the archive and manifest are already
published, no rollback occurs, power-loss durability is unknown, and operator
inspection is required.

Native source and target names must be nonempty basenames, not `.`, `..`, slash,
or NUL-containing strings. The wrapper resets `errno` before its native call and
fails closed for an unsupported platform, unavailable primitive, or failure with
no errno.

## 13. Accessibility, security, and privacy

Catalog import pins a current-euid-owned, non-group/world-writable output parent
by file descriptor and rejects intermediate/final symlinks, untrusted checkout
parents, and pathname replacement outside that descriptor. POSIX rename cannot
atomically predicate publication on the source inode. Therefore imports must run
as an exclusive operation with no concurrent same-euid writer; post-rename inode
verification detects a boundary race and fails without rolling back or deleting a
foreign entry. This is detection, not a privilege boundary or rollback guarantee.

The catalog contract is schema version 1 with 1,140 items. It records the source
SHA-256 `a55a0d0b1cfa3773031e787c2ce7ca0df34534e16a70b65ed1baa91975c82da8` and
checked-in artifact SHA-256 `4f38b5f63931a7f06e13f90f5d9ef90a0a435f30dae5d4fe70720d730a057473`.

Every generated page must meet [WCAG 2.2][wcag22] Level AA and include:

- Japanese document language, unique title, viewport metadata, and one `main`
- Skip link, visible keyboard focus, semantic landmarks, and logical headings
- Descriptive links and table captions
- WCAG AA color contrast for normal text and controls
- Layouts that remain usable at 200% zoom and narrow widths
- Print styles and non-color status labels

[wcag22]: https://www.w3.org/TR/WCAG22/

Security rules:

- No JavaScript, iframe, object, embed, form, external font, or remote image.
- No inline event handlers or unsafe URL schemes.
- Structured data is escaped at render boundaries.
- External links use HTTPS and safe `rel` attributes.
- A restrictive Content Security Policy is emitted where compatible with local
  file viewing.
- GitHub Actions use least-privilege permissions and pinned action revisions.
- The build uses no third-party Python dependency.
- No learner data, cookies, tracking, or analytics are collected.

## 14. Testing strategy

Implementation follows red-green-refactor TDD. Each production behavior begins
with a failing `unittest`.

### Unit tests

- Domain-model parsing and helpful validation errors
- Catalog uniqueness and grouping
- Graph reachability, stage ordering, and cycle detection
- HTML escaping and unsafe-fragment rejection
- Deterministic URL and output generation

### Contract tests

- Exactly 1,140 unique catalog items
- Exactly 30 curated core lessons
- Exactly three capstones
- Every complete lesson satisfies the textbook-quality schema
- Every framework mapping references an existing lesson or capstone
- All local links and assets resolve under both directory and `file://` rules
- Generated output contains no script tag or JavaScript reference
- Required semantic and accessibility landmarks exist

### Integration and acceptance tests

- Clean build from a fresh checkout using the supported Python version
- Output reproducibility across two consecutive builds
- HTML parsing of every generated page
- CSS token, responsive, focus, and print-rule contracts
- GitHub Pages artifact contains only approved static file types
- Browser smoke checks at mobile, desktop, high zoom, and print widths

If test-impact analysis is missing, fails, or selects zero tests unexpectedly,
CI runs the complete suite.

## 15. OSS operating model

The repository uses GitHub Flow:

1. Keep `main` releasable.
2. Create narrowly scoped feature branches.
3. Add tests before implementation.
4. Use small commits that explain one decision.
5. Open a PR describing motivation, before/after behavior, design decisions,
   validation, security impact, accessibility impact, and OSS value.
6. Require CI and review before merge.
7. Delete merged local and remote feature branches.

Public project files include:

- MIT License
- Bilingual README summary with Japanese primary documentation
- Contribution guide and content-quality checklist
- Code of Conduct
- Governance and maintainer responsibilities
- Security policy with private vulnerability-reporting guidance
- Issue templates for content gaps, corrections, framework updates, and code
- Pull-request template
- Errata policy and visible correction history
- Automated dependency-free validation and Pages deployment

## 16. Release sequence

1. Preserve and checksum the current prototype.
2. Establish build contracts and failing tests.
3. Implement domain models, validation, and deterministic rendering.
4. Import and validate the 1,140-item catalog.
5. Implement the design system and Hybrid page templates.
6. Author and review the 30 curated core lessons.
7. Add roadmap, competency matrix, and three capstones.
8. Add OSS documentation, CI, security, accessibility, and Pages deployment.
9. Run full validation and a clean-checkout build.
10. Perform technical, content, security, accessibility, and OSS self-review.
11. Create the public GitHub repository, push the feature branch, open the
    explanatory PR, merge only after green checks, and remove the merged branch.

## 17. Acceptance criteria

The first release is complete only when:

- The original prototype is checksum-verified in the local archive.
- `site/index.html` works when opened directly without a web server.
- The generated site contains HTML and CSS only.
- The catalog contains 1,140 unique items and exposes all existing content
  concepts without 1,140 duplicated public lesson pages.
- Thirty core lessons pass the content-quality contract.
- The roadmap is acyclic, readable without CSS, and visually connected with CSS.
- The competency matrix names framework versions and explains every mapping.
- Three capstones cover the full curated core.
- HCI, graphics, maintenance, professional practice, economics, communication,
  and OSS are represented by lessons and assessed work.
- Full tests, link checks, accessibility contracts, security checks, and build
  reproducibility checks pass.
- No placeholder text, unsafe HTML, dead local link, or runtime JavaScript
  remains.
- The public repository includes complete contributor and governance surfaces.
- GitHub Pages serves the verified build from `main`.

## 18. Future decisions

Future proposals may cover English lesson translations, optional client-side
enhancements, learner progress, spaced repetition, instructor packs, and deeper
rewrites of catalog items. They are not prerequisites for the first release and
must preserve the static baseline as a supported experience.
