# Engineering Expert Curriculum

[日本語README](README.md)

Engineering Expert Curriculum is a Japanese-first, static OSS textbook for building and demonstrating engineering judgment. It preserves a 1,140-item knowledge map while turning 30 core lessons into evidence-based learning journeys with six mastery gates and three capstones.

> Learn → Practice → Explain → Prove → Transfer → Review

## What it provides

- A browser-searchable catalog of 1,140 engineering topics.
- 30 core lessons spanning foundations, trustworthy software, data and scale, human and product systems, operations, and technical leadership.
- six mastery gates that require reviewable artifacts rather than completion clicks.
- three capstones: operating a global service, evolving a legacy system safely, and launching and stewarding an OSS product.
- Rationale-backed mappings to CS2023, SWEBOK V4.0a, and SFIA 9.
- Prerequisites, labs, reasoning assessments, transfer tasks, rubrics, and spaced review prompts.

The learning loop is intentionally cumulative. Learners study a mechanism and its limits, practice under fixed conditions, explain causality in their own words, prove a decision with evidence, repeat it after one constraint changes, and review it after time has passed.

## Static delivery contract

v0.1.0 is the immutable HTML/CSS-only release. In v0.2.0, every lesson remains complete and understandable with HTML and CSS and no JavaScript; approved simulation lessons may progressively load the single repository-owned `static/visualization.js` asset. After building, open `site/index.html` directly over `file://` or publish the same output on GitHub Pages. Disabled, blocked, or failed JavaScript never removes lesson information.

The dependency-free runtime uses no network, storage, analytics, or URL state. There are no accounts, server APIs, databases, or collected, retained, or transmitted learner data.

The information structure remains meaningful without CSS and does not rely on color or connector lines alone. Browser Find provides catalog search, keeping the first release portable and inspectable.

12 approved lessons provide ten visualization types while preserving the same causal and state trace under keyboard operation, reduced motion, and forced colors. Release candidates are exercised in pinned Chromium and Firefox builds plus the installed Safari build. Browser caches, screenshots, and raw performance reports remain local under `outputs/` and are not release artifacts.

Each deployment carries a root release manifest binding the commit to the byte size and SHA-256 of every HTML, CSS, and JavaScript artifact. The Pages workflow verifies those bytes after deployment. The manifest is not, by itself, a signature or proof of publisher authenticity. Meta CSP cannot enforce `frame-ancestors`, and this repository cannot configure arbitrary GitHub Pages response headers, so it does not claim clickjacking protection.

## Build and validate

Python 3.12 or later is required at build time. Readers do not need Python after the site is generated.

```sh
python3 tools/build.py
open site/index.html
```

Run the complete contract suite before proposing a change:

```sh
python3 -m unittest discover -s tests -v
python3 tools/build.py
```

The builder uses the Python standard library, performs no network access, and produces deterministic static output from version-controlled content and templates.

## Evidence and review

A lesson marked `status: complete` has machine-validated structural completeness. That status does not establish factual correctness, publication approval, human review, or learner mastery.

Every review record discloses `reviewerKind` as `human`, `ai-assisted`, or `automated`. AI-assisted and automated results never count as human approval. Publication remains a per-commit decision backed by tests, review evidence, and an authenticated maintainer decision.

Review is recorded independently for technical accuracy, learning design and evidence, accessibility, and editorial and source quality. Capstone evidence must include the artifact, observations, reasoning, changed-constraint transfer, author fixes, and independent re-evaluation.

## Repository map

Canonical content lives under `content/`; the prerequisite graph is `content/roadmap.json`; competency mappings are in `content/competencies.json`; the standard-library builder is under `curriculum_builder/`; templates, CSS, and the optional first-party progressive runtime are under `templates/` and `static/`; and executable contracts live in `tests/`. Generated `site/` output is intentionally not version controlled.

## Contributing and reporting

The contribution workflow, TDD expectations, review roles, and branch cleanup rules are in [CONTRIBUTING.md](CONTRIBUTING.md). Governance is documented in [GOVERNANCE.md](GOVERNANCE.md), public corrections in [ERRATA.md](ERRATA.md), and release history in [CHANGELOG.md](CHANGELOG.md).

Do not disclose suspected vulnerabilities in a public issue. Follow the private GitHub route in [SECURITY.md](SECURITY.md). Community behavior is governed separately by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Frameworks, license, and citation

CS2023, SWEBOK, and SFIA names and materials belong to their respective owners. Curriculum mappings explain alignment and do not imply endorsement, accreditation, or certification by those organizations.

The project is available under the [MIT License](LICENSE). Use [CITATION.cff](CITATION.cff) for machine-readable citation metadata.
