from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTENT_STANDARD = REPOSITORY_ROOT / "docs/content-standard.md"
DESIGN_SPEC = (
    REPOSITORY_ROOT
    / "docs/superpowers/specs/2026-07-30-static-oss-curriculum-design.md"
)
EXPECTED_H1 = "Engineering Expert Curriculum コンテンツ品質標準"
EXPECTED_H2 = (
    "1. 適用範囲と規範語",
    "2. `complete` の定義",
    "3. 六段階 evidence loop",
    "4. 著者執筆と構造化データの責任分離",
    "5. Objective・能力・evidenceの追跡",
    "6. ラボ成果物",
    "7. Reasoning assessment",
    "8. 評価rubric",
    "9. Source hierarchy",
    "10. Accessibilityと静的配信",
    "11. Review roles",
    "12. 完了、更新、Errata、例外",
    "13. Contributor・reviewerチェックリスト",
)
REQUIRED_CLAUSES = {
    EXPECTED_H2[0]: (
        "`MUST` は例外なく満たす要件、`SHOULD` は理由と代替証拠が必要な要件、"
        "`MAY` は任意の改善として解釈することをMUSTとする。",
    ),
    EXPECTED_H2[1]: (
        "`status: complete` はmachine-validated structural completenessだけを示し、"
        "内容の正確性、human review、公開承認、学習者のmasteryを証明しないことを"
        "MUSTとする。",
        "公開commitは、全レッスンの構造的完全性に加え、release-level test、2回の"
        "決定的build、link検査、安全性検査、accessibility検査、review approvalを"
        "満たすことをMUSTとする。",
    ),
    EXPECTED_H2[2]: (
        "Evidence loopは Learn → Practice → Explain → Prove → Transfer → Review の"
        "順序をMUSTとする。",
    ),
    EXPECTED_H2[3]: (
        "`body.html` の著者執筆sectionと `lesson.json` の構造化データは責任境界を"
        "分離することをMUSTとする。",
    ),
    EXPECTED_H2[4]: (
        "すべてのobjectiveと能力段階は既知のevidence IDへ追跡でき、すべての"
        "evidenceはobjectiveまたは能力段階から参照されることをMUSTとする。",
    ),
    EXPECTED_H2[5]: (
        "各labは提出可能なartifact名、3手順以上、失敗時に保存する観測値、安全な"
        "停止条件を持つことをMUSTとする。",
    ),
    EXPECTED_H2[6]: (
        "各assessmentは2問以上とし、reasoning、代替案、反証、結論を変える条件を"
        "問うことをMUSTとする。",
    ),
    EXPECTED_H2[7]: (
        "各rubricはtechnical correctness、judgment、evidence、communicationの"
        "4観点×incomplete、developing、proficient、exemplaryの4段階を持つことを"
        "MUSTとする。",
        "`proficient` は支援なしで正しい成果を説明・再現できる合格境界として"
        "定義することをMUSTとする。",
    ),
    EXPECTED_H2[8]: (
        "各lessonはsource hierarchyに従い、異なる2件以上のHTTPS URLを持つことを"
        "MUSTとする。",
    ),
    EXPECTED_H2[9]: (
        "公開成果物はHTMLとCSSのみで理解でき、JavaScriptなしで全情報へ到達できる"
        "ことをMUSTとする。",
        "すべてのactive elementはkeyboardで到達・操作でき、visible focusと単独で"
        "理解できる名前を持つことをMUSTとする。",
    ),
    EXPECTED_H2[10]: (
        "技術的正確性、学習設計・証拠、アクセシビリティ、編集・出典の4 review "
        "dimensionsを独立して記録することをMUSTとする。",
        "各review記録は `reviewerKind` を `human`、`ai-assisted`、`automated` の"
        "いずれかとして正直に開示することをMUSTとする。",
        "AI支援または自動生成のreviewを `human` approvalとして扱わないことを"
        "MUSTとする。",
    ),
    EXPECTED_H2[11]: (
        "公開可能性はcommit単位のPR・release evidenceと、認証済みmaintainerによる"
        "明示的decisionで判定することをMUSTとする。",
        "`v0.1.0` から発効するこの開示方針を、既存contentへ遡及してhuman approvalを"
        "推定または付与するために使わないことをMUSTとする。",
        "承認は将来の変更にのみ効力を持ち、過去または後続のcommitへ自動継承しない"
        "ことをMUSTとする。",
    ),
    EXPECTED_H2[12]: (
        "Contributorとreviewerは公開前に次のチェックリストを上から順に確認することを"
        "MUSTとする。",
    ),
}
EXPECTED_CHECKLIST = (
    "構造的completeとcommit単位の公開可能性を別々に判定した。",
    "6 authored sectionsが順序どおりで、重複本文やplaceholderがない。",
    "全objectiveと5能力段階が4種evidenceへ追跡できる。",
    "Labを第三者が安全に再現でき、artifactと失敗証拠を提出できる。",
    "2問以上のassessmentがreasoning、代替案、反証を要求する。",
    "Transferが重要制約を変え、同じ判断のコピーになっていない。",
    "Rubricの4観点×4段階が観測可能で、proficient境界が明確である。",
    "Source hierarchy、version、関連性、断定範囲、異なる2件以上のHTTPS URLを確認した。",
    "Semantic HTML、keyboard、zoom、contrast、print、JS0を確認した。",
    "4 review dimensions、reviewerKind、author fix、再確認結果を記録した。",
    "v0.1.0以後のreviewerKindを開示し、AI reviewをhuman approvalに数えていない。",
    "Generated map、full tests、2回build、local link、安全性、accessibility検査と認証済みmaintainer decisionが揃った。",
)
EXPECTED_EVIDENCE_TABLE = (
    ("段階", "学習者の行動", "MUSTとなる証拠"),
    ("Learn", "機構、境界、制約、失敗モードを理解する", "objective、メンタルモデル、出典"),
    ("Practice", "固定条件で手を動かし結果を観測する", "3手順以上のlabと提出成果物"),
    ("Explain", "自分の言葉で因果関係と代替案を説明する", "teach-backとexplanation evidence"),
    ("Prove", "もっともらしい誤診を反証して判断する", "問いとexpected evidenceを持つassessment"),
    ("Transfer", "一つの重要制約を変え、判断を再実行する", "transfer taskと更新された証拠"),
    ("Review", "時間を空けて再現・説明・修正する", "1/7/30/90日後のpromptとrubric再評価"),
)
EXPECTED_REVIEW_TABLE = (
    ("役割", "独立して確認する責任"),
    ("技術的正確性", "機構、code、測定、制約、failure mode、sourceとの一致"),
    ("学習設計・証拠", "objective、六段階loop、assessment、transfer、rubricの採点可能性"),
    ("アクセシビリティ", "semantic HTML、keyboard、読み順、zoom、contrast、print"),
    ("編集・出典", "用語、断定範囲、version、引用、link、Errata履歴"),
)

_ATX_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")
_OPEN_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_CHECKBOX = re.compile(r"^\s*[-*+]\s+\[ \]\s+(.+?)\s*$")
_SETEXT_UNDERLINE = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
_RAW_HTML = re.compile(
    r"</?(?:pre|code|template|h[1-6])(?:[ \t][^>]*)?>",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class _StandardDocument:
    h1: tuple[str, ...]
    h2: tuple[str, ...]
    sections: dict[str, tuple[str, ...]]


def _visible_lines(source: str) -> tuple[str, ...]:
    """Return prose lines while excluding Markdown's hidden code/comment text."""
    # This normative document has no legitimate hidden commentary. Rejecting
    # comment delimiters avoids parser ambiguity around nesting and truncation.
    if "<!--" in source or "-->" in source:
        raise AssertionError("required clause cannot be hidden in HTML comments")

    visible: list[str] = []
    fence_character: str | None = None
    fence_width = 0
    for line in source.splitlines():
        if fence_character is not None:
            if re.fullmatch(
                rf" {{0,3}}{re.escape(fence_character)}{{{fence_width},}}[ \t]*",
                line,
            ):
                fence_character = None
                fence_width = 0
            continue

        opening = _OPEN_FENCE.fullmatch(line)
        if opening is not None:
            delimiter, info = opening.groups()
            if delimiter[0] == "`" and "`" in info:
                raise AssertionError(
                    "content standard has an invalid backtick fence info string"
                )
            fence_character = delimiter[0]
            fence_width = len(delimiter)
            continue
        if re.match(r"^(?: {4}|\t)", line) or re.match(r"^ {0,3}>", line):
            continue
        if _RAW_HTML.search(line):
            raise AssertionError("content standard contains forbidden raw HTML")
        visible.append(line)
    if fence_character is not None:
        raise AssertionError("content standard contains an unclosed code fence")
    return tuple(visible)


def _heading_text(raw: str) -> str:
    return re.sub(r"[ \t]+#+[ \t]*$", "", raw).strip()


def _parse_standard(source: str) -> _StandardDocument:
    h1: list[str] = []
    h2: list[str] = []
    sections: dict[str, list[str]] = {}
    active_section: str | None = None
    visible = _visible_lines(source)
    for index, line in enumerate(visible):
        if (
            index > 0
            and visible[index - 1].strip()
            and _SETEXT_UNDERLINE.fullmatch(line)
        ):
            raise AssertionError("content standard headings must use ATX Markdown")
    first_content = next((line for line in visible if line.strip()), "")
    if first_content != f"# {EXPECTED_H1}":
        raise AssertionError("content standard must begin with the exact H1")

    for line in visible:
        heading = _ATX_HEADING.fullmatch(line)
        if heading is not None:
            level = len(heading.group(1))
            title = _heading_text(heading.group(2))
            if level == 1:
                h1.append(title)
                active_section = None
            elif level == 2:
                h2.append(title)
                sections.setdefault(title, [])
                active_section = title
            continue
        if active_section is not None:
            sections[active_section].append(line)

    return _StandardDocument(
        h1=tuple(h1),
        h2=tuple(h2),
        sections={name: tuple(lines) for name, lines in sections.items()},
    )


def _normalized_prose(lines: tuple[str, ...]) -> str:
    return " ".join(" ".join(lines).split())


def _markdown_table(lines: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    rows: list[tuple[str, ...]] = []
    for line in lines:
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = tuple(cell.strip() for cell in stripped[1:-1].split("|"))
        if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return tuple(rows)


def _assert_content_standard(source: str) -> None:
    parsed = _parse_standard(source)
    if parsed.h1 != (EXPECTED_H1,):
        raise AssertionError("content standard must have one exact H1")
    if parsed.h2 != EXPECTED_H2:
        raise AssertionError("content standard H2 order must be exact")
    if set(parsed.sections) != set(EXPECTED_H2):
        raise AssertionError("content standard sections must be exact")

    for section, clauses in REQUIRED_CLAUSES.items():
        prose = _normalized_prose(parsed.sections[section])
        for clause in clauses:
            if _normalized_prose((clause,)) not in prose:
                raise AssertionError(
                    f"content standard section lacks required clause: {section}"
                )

    if _markdown_table(parsed.sections[EXPECTED_H2[2]]) != EXPECTED_EVIDENCE_TABLE:
        raise AssertionError("evidence loop table rows must be exact")
    if _markdown_table(parsed.sections[EXPECTED_H2[10]]) != EXPECTED_REVIEW_TABLE:
        raise AssertionError("review role table rows must be exact")

    checklist = tuple(
        match.group(1)
        for line in parsed.sections[EXPECTED_H2[-1]]
        if (match := _CHECKBOX.fullmatch(line)) is not None
    )
    if checklist != EXPECTED_CHECKLIST:
        raise AssertionError("content standard checklist order must be exact")


def _valid_standard() -> str:
    lines = [f"# {EXPECTED_H1}", ""]
    for heading in EXPECTED_H2:
        lines.extend((f"## {heading}", ""))
        lines.extend(REQUIRED_CLAUSES[heading])
        if heading == EXPECTED_H2[2]:
            lines.extend(
                "| " + " | ".join(row) + " |" for row in EXPECTED_EVIDENCE_TABLE[:1]
            )
            lines.append("|---|---|---|")
            lines.extend(
                "| " + " | ".join(row) + " |" for row in EXPECTED_EVIDENCE_TABLE[1:]
            )
        if heading == EXPECTED_H2[10]:
            lines.extend(
                "| " + " | ".join(row) + " |" for row in EXPECTED_REVIEW_TABLE[:1]
            )
            lines.append("|---|---|")
            lines.extend(
                "| " + " | ".join(row) + " |" for row in EXPECTED_REVIEW_TABLE[1:]
            )
        if heading == EXPECTED_H2[-1]:
            lines.extend(f"- [ ] {item}" for item in EXPECTED_CHECKLIST)
        lines.append("")
    return "\n".join(lines)


class ContentStandardContractTests(unittest.TestCase):
    def test_independent_validator_accepts_the_canonical_contract(self) -> None:
        _assert_content_standard(_valid_standard())

    def test_repository_content_standard_satisfies_the_canonical_contract(
        self,
    ) -> None:
        _assert_content_standard(CONTENT_STANDARD.read_text(encoding="utf-8"))

    def test_design_spec_uses_the_same_model_b_status_boundary(self) -> None:
        design = _normalized_prose(
            tuple(DESIGN_SPEC.read_text(encoding="utf-8").splitlines())
        )
        clauses = (
            "`status: complete` is a machine-validated structural state; it does not "
            "prove human review, factual correctness, publication approval, or learner "
            "mastery.",
            "Publishability is decided per commit from PR and release evidence plus an "
            "explicit decision by an authenticated maintainer.",
            "`reviewerKind` is one of `human`, `ai-assisted`, or `automated`; AI-assisted "
            "and automated reviews never count as human approval.",
            "Starting with `v0.1.0`, this disclosure policy applies prospectively and "
            "does not infer or retroactively grant human approval to existing content.",
            "Review evidence covers four dimensions: technical accuracy, learning design "
            "and evidence, accessibility, and editorial and source quality.",
        )
        for clause in clauses:
            with self.subTest(clause=clause):
                self.assertIn(_normalized_prose((clause,)), design)

    def test_heading_deletion_reordering_duplication_and_extension_fail(
        self,
    ) -> None:
        valid = _valid_standard()
        first = f"## {EXPECTED_H2[0]}"
        second = f"## {EXPECTED_H2[1]}"
        mutations = {
            "delete": valid.replace(first, "### removed", 1),
            "reorder": valid.replace(first, "## SWAP", 1)
            .replace(second, first, 1)
            .replace("## SWAP", second, 1),
            "duplicate": valid.replace(second, f"{first}\n\n{second}", 1),
            "extra": valid.replace(second, f"## Extra policy\n\n{second}", 1),
        }
        for label, mutated in mutations.items():
            with self.subTest(label=label), self.assertRaisesRegex(
                AssertionError, "H2 order|sections"
            ):
                _assert_content_standard(mutated)

    def test_tokens_in_wrong_sections_comments_or_fences_do_not_count(
        self,
    ) -> None:
        valid = _valid_standard()
        clause = REQUIRED_CLAUSES[EXPECTED_H2[1]][0]
        wrong_section = valid.replace(clause, "", 1).replace(
            f"## {EXPECTED_H2[2]}",
            f"## {EXPECTED_H2[2]}\n\n{clause}",
            1,
        )
        hidden_in_comment = valid.replace(clause, f"<!-- {clause} -->", 1)
        hidden_in_fence = valid.replace(
            clause,
            f"```text\n{clause}\n```",
            1,
        )
        for label, mutated in {
            "wrong section": wrong_section,
            "comment": hidden_in_comment,
            "fence": hidden_in_fence,
        }.items():
            with self.subTest(label=label), self.assertRaisesRegex(
                AssertionError, "required clause"
            ):
                _assert_content_standard(mutated)

    def test_hidden_normative_prose_and_unclosed_comments_are_rejected(
        self,
    ) -> None:
        valid = _valid_standard()
        clause = REQUIRED_CLAUSES[EXPECTED_H2[1]][0]
        mutations = {
            "unclosed HTML comment": valid.replace(
                clause,
                f"<!-- {clause}",
                1,
            ),
            "four-space indented code": valid.replace(
                clause,
                f"    {clause}",
                1,
            ),
            "blockquote": valid.replace(
                clause,
                f"> {clause}",
                1,
            ),
            "raw pre": valid.replace(
                clause,
                f"<pre>{clause}</pre>",
                1,
            ),
            "raw code": valid.replace(
                clause,
                f"<code>{clause}</code>",
                1,
            ),
            "raw template": valid.replace(
                clause,
                f"<template>{clause}</template>",
                1,
            ),
            "tilde fence with a backtick in info": valid.replace(
                clause,
                f"~~~language`variant\n{clause}\n~~~",
                1,
            ),
            "nested HTML comment": valid.replace(
                clause,
                f"<!-- outer <!-- inner --> {clause} -->",
                1,
            ),
        }
        for label, mutated in mutations.items():
            with self.subTest(label=label), self.assertRaises(AssertionError):
                _assert_content_standard(mutated)

    def test_invalid_backtick_fence_info_is_rejected(self) -> None:
        valid = _valid_standard()
        clause = REQUIRED_CLAUSES[EXPECTED_H2[1]][0]
        mutated = valid.replace(
            clause,
            f"```language`variant\n{clause}\n```",
            1,
        )

        with self.assertRaises(AssertionError):
            _assert_content_standard(mutated)

    def test_tilde_fence_info_may_contain_a_backtick(self) -> None:
        valid = _valid_standard()
        next_heading = f"## {EXPECTED_H2[1]}"
        with_valid_fence = valid.replace(
            next_heading,
            "~~~language`variant\n"
            "This fenced example is not normative prose.\n"
            "~~~\n\n"
            f"{next_heading}",
            1,
        )

        _assert_content_standard(with_valid_fence)

    def test_setext_and_raw_html_extra_headings_are_rejected(self) -> None:
        valid = _valid_standard()
        insert_at = f"## {EXPECTED_H2[1]}"
        mutations = {
            "Setext H1": valid.replace(
                insert_at,
                f"Hidden policy\n=============\n\n{insert_at}",
                1,
            ),
            "Setext H2": valid.replace(
                insert_at,
                f"Hidden policy\n-------------\n\n{insert_at}",
                1,
            ),
            "raw HTML H2": valid.replace(
                insert_at,
                f"<h2>Hidden policy</h2>\n\n{insert_at}",
                1,
            ),
        }
        mutations.update(
            {
                f"raw HTML H{level}": valid.replace(
                    insert_at,
                    f"<h{level}>Hidden policy</h{level}>\n\n{insert_at}",
                    1,
                )
                for level in range(1, 7)
            }
        )
        for label, mutated in mutations.items():
            with self.subTest(label=label), self.assertRaises(AssertionError):
                _assert_content_standard(mutated)

    def test_evidence_and_review_tables_have_exact_semantic_rows(self) -> None:
        standard = CONTENT_STANDARD.read_text(encoding="utf-8")
        mutations = {
            "extra evidence row": standard.replace(
                "| Review | 時間を空けて再現・説明・修正する | "
                "1/7/30/90日後のpromptとrubric再評価 |",
                "| Review | 時間を空けて再現・説明・修正する | "
                "1/7/30/90日後のpromptとrubric再評価 |\n"
                "| Observe | 読む | ページ表示 |",
                1,
            ),
            "extra review role": standard.replace(
                "| 編集・出典 | 用語、断定範囲、version、引用、link、Errata履歴 |",
                "| 編集・出典 | 用語、断定範囲、version、引用、link、Errata履歴 |\n"
                "| AI承認 | human approvalを代行する |",
                1,
            ),
        }
        for label, mutated in mutations.items():
            self.assertNotEqual(mutated, standard)
            with self.subTest(label=label), self.assertRaises(AssertionError):
                _assert_content_standard(mutated)

    def test_ai_never_human_and_prospective_policy_are_direct_contracts(
        self,
    ) -> None:
        valid = _valid_standard()
        mutations = {
            "AI-never-human clause deleted": valid.replace(
                REQUIRED_CLAUSES[EXPECTED_H2[10]][2],
                "",
                1,
            ),
            "prospective nonretroactive clause deleted": valid.replace(
                REQUIRED_CLAUSES[EXPECTED_H2[11]][1],
                "",
                1,
            ),
        }
        for label, mutated in mutations.items():
            self.assertNotEqual(mutated, valid)
            with self.subTest(label=label), self.assertRaises(AssertionError):
                _assert_content_standard(mutated)

    def test_design_spec_defines_six_authored_and_nine_generated_responsibilities(
        self,
    ) -> None:
        source = DESIGN_SPEC.read_text(encoding="utf-8")
        authored_contract = (
            "`body.html` is an authored semantic fragment. It must contain exactly "
            "these six sections in order:\n\n"
            "1. Why this matters\n"
            "2. Mental model\n"
            "3. Worked example\n"
            "4. Trade-offs and failure modes\n"
            "5. Knowledge checks\n"
            "6. Sources and further study"
        )
        generated_contract = (
            "`lesson.json` has exactly nine structured responsibilities that the "
            "renderer generates outside the authored body: objectives, capability "
            "progression, lab, teach-back, assessment, transfer, review, rubric, "
            "and sources."
        )
        self.assertIn(authored_contract, source)
        self.assertIn(generated_contract, source)
        authored_region = source.split(
            "`body.html` is an authored semantic fragment.", 1
        )[1].split("The validator rejects", 1)[0]
        for contradictory_heading in ("Practical lab", "Transfer task", "Rubric"):
            with self.subTest(heading=contradictory_heading):
                self.assertNotIn(contradictory_heading, authored_region)

    def test_design_spec_separates_source_shape_from_reachability_audit(
        self,
    ) -> None:
        source = _normalized_prose(
            tuple(DESIGN_SPEC.read_text(encoding="utf-8").splitlines())
        )
        clauses = (
            "The dependency-free validator checks source metadata and the syntax "
            "and distinctness of at least two HTTPS URLs; it does not make network "
            "requests or guarantee reachability.",
            "Source reachability remains an editorial responsibility.",
            "An optional planned scheduled link audit is not implemented in v0.1.0, "
            "so neither the dependency-free build nor current CI claims network "
            "reachability.",
        )
        for clause in clauses:
            with self.subTest(clause=clause):
                self.assertIn(_normalized_prose((clause,)), source)

    def test_weakened_normative_or_reversed_completion_claims_fail(self) -> None:
        valid = _valid_standard()
        normative = REQUIRED_CLAUSES[EXPECTED_H2[0]][0]
        completion = REQUIRED_CLAUSES[EXPECTED_H2[1]][0]
        mutations = {
            "MUST to MAY": valid.replace(
                normative,
                normative.replace("MUSTとする", "MAYとする"),
                1,
            ),
            "complete equals published": valid.replace(
                completion,
                completion.replace("証明しない", "証明する"),
                1,
            ),
        }
        for label, mutated in mutations.items():
            with self.subTest(label=label), self.assertRaisesRegex(
                AssertionError, "required clause"
            ):
                _assert_content_standard(mutated)

    def test_ai_human_disclosure_and_ordered_checklist_cannot_be_removed(
        self,
    ) -> None:
        valid = _valid_standard()
        disclosure = REQUIRED_CLAUSES[EXPECTED_H2[10]][1]
        checklist_item = f"- [ ] {EXPECTED_CHECKLIST[4]}"
        mutations = {
            "AI-human disclosure": valid.replace(disclosure, "", 1),
            "checklist item": valid.replace(checklist_item, "", 1),
        }
        for label, mutated in mutations.items():
            with self.subTest(label=label), self.assertRaises(AssertionError):
                _assert_content_standard(mutated)
