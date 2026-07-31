from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTENT_STANDARD = REPOSITORY_ROOT / "docs/content-standard.md"
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
        "`status: complete` はレッスン単体の構造的完全性だけを示し、commit単位の"
        "公開可能性を保証しないことをMUSTとする。",
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
        "各review記録は `reviewerKind` を `human` または `ai-assisted` として正直に"
        "開示することをMUSTとする。",
        "AI支援の開示を削除せず、`ai-assisted` reviewを `human` reviewとして表記"
        "しないことをMUSTとする。",
    ),
    EXPECTED_H2[11]: (
        "この標準の発効後に `complete` へ変更するcommitは、少なくとも一つの "
        "`reviewerKind: human` approvalを持つことをMUSTとする。",
        "発効前の既存 `complete` レッスンへhuman approvalを遡及して推定しないことを"
        "MUSTとする。",
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
    "発効後のcomplete変更にhuman approvalがあり、過去の承認を推定・継承していない。",
    "Generated map、full tests、2回build、local link、安全性、accessibility検査が一致した。",
)

_ATX_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")
_OPEN_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(?:[^`~]*)$")
_CHECKBOX = re.compile(r"^\s*[-*+]\s+\[ \]\s+(.+?)\s*$")


@dataclass(frozen=True, slots=True)
class _StandardDocument:
    h1: tuple[str, ...]
    h2: tuple[str, ...]
    sections: dict[str, tuple[str, ...]]


def _visible_lines(source: str) -> tuple[str, ...]:
    """Return prose lines while excluding Markdown's hidden code/comment text."""
    without_comments = re.sub(r"<!--.*?-->", "", source, flags=re.DOTALL)
    visible: list[str] = []
    fence_character: str | None = None
    fence_width = 0
    for line in without_comments.splitlines():
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
            fence_character = opening.group(1)[0]
            fence_width = len(opening.group(1))
            continue
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
                completion.replace("保証しない", "保証する"),
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
