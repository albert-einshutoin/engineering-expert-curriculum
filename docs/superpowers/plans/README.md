# Static OSS Curriculum Implementation Plan Index

Execute the approved curriculum design as three independently testable
milestones without losing the existing prototype or weakening the final quality
gate. The stack is Python 3.12 standard library, HTML5, CSS3, JSON, `unittest`,
GitHub Actions, and GitHub Pages.

Foundation first establishes preservation, canonical data, safety boundaries,
and static rendering. Learning Content then adds the 30-lesson evidence graph,
competencies, and capstones. OSS Publication finally makes the already-verified
artifact publicly operable through GitHub Flow, CI, governance, and Pages.

## Required execution order

1. [Static Curriculum Foundation](2026-07-30-static-curriculum-foundation.md)
2. [Expert Learning Content](2026-07-30-expert-learning-content.md)
3. [OSS Publication and GitHub Release](2026-07-30-oss-publication.md)

Do not begin a later plan until the previous plan's complete test suite and
checkpoint are green. A later failure runs the full suite; no impact-analysis
result or empty test selection may replace complete validation.

## Working milestones

| Milestone | Independently demonstrable outcome |
|---|---|
| Foundation | The original prototype is checksum-preserved, 1,140 catalog items validate, and a file-compatible Atlas site builds with no JavaScript |
| Learning Content | Thirty complete lessons, six mastery gates, three framework families, and three capstones render and pass evidence contracts |
| OSS Publication | A public MIT repository, green PR, GitHub Pages deployment, contributor operations, and cleaned merged branches |

## Approved-spec coverage

| Design requirement | Implemented by |
|---|---|
| Static HTML/CSS and `file://` support | Foundation Tasks 7–9 |
| Python standard-library deterministic build | Foundation Tasks 1, 7, 9 |
| Preserve the existing prototype without deletion | Foundation Tasks 2 and 10 |
| Canonical 1,140-item catalog | Foundation Task 4 |
| Safe authored HTML and escaped structured data | Foundation Tasks 6–7 |
| CSS roadmap and semantic fallback | Foundation Tasks 5 and 8; Content Task 9 |
| Thirty textbook-quality lessons | Content Tasks 1–8 and 12 |
| Learn–Practice–Explain–Prove–Transfer–Review | Content Tasks 1–2 |
| HCI, graphics, maintenance, professional practice, economics, communication, and OSS gaps | Content Tasks 6–8 |
| CS2023, SWEBOK V4.0a, and SFIA 9 matrix | Content Task 10 |
| Three integrated capstones | Content Task 11 |
| Accessibility and security contracts | Foundation Task 6; Publication Tasks 4–7 |
| MIT and contributor operating model | Publication Tasks 1–3 |
| CI, CodeQL, dependency review, and Pages | Publication Tasks 6–7 |
| Local, visual, accessibility, and release self-review | Publication Task 8 |
| Public repository, PR, merge proof, Pages proof, and branch cleanup | Publication Tasks 9–10 |

## Definition of implementation completion

- [ ] Every checkbox in all three plans is complete.
- [ ] Every commit named by the plans exists in the feature-branch history or
      is represented by an equally narrow TDD commit.
- [ ] The full test suite, clean build, site checker, reproducibility comparison,
      security review, keyboard review, VoiceOver review, zoom review, print
      review, and `file://` journeys pass.
- [ ] The GitHub PR state is `MERGED`, not merely open or mergeable.
- [ ] The latest Pages deployment from the merge commit succeeds and its public
      URL serves the verified artifact.
- [ ] Local and remote feature branches are removed while the ignored local
      prototype archive remains checksum-verifiable.
