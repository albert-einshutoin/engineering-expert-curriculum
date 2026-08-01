from __future__ import annotations

from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path
import unittest
from unittest.mock import patch

from curriculum_builder.errors import CurriculumValidationError
from curriculum_builder.html_safety import validate_generated_fragment
from curriculum_builder.lesson_rendering import (
    LessonBody,
    LessonSection,
    parse_lesson_body,
    render_lesson_body,
)
from curriculum_builder.render import Renderer
from curriculum_builder.visualizations import (
    CausalPayload,
    ComparisonCell,
    ComparisonPayload,
    FlowPayload,
    HierarchyNode,
    HierarchyPayload,
    Item,
    LessonSectionRole,
    MatrixCell,
    MatrixPayload,
    MemoryLayer,
    MemoryPayload,
    NetworkNode,
    NetworkPayload,
    Relationship,
    InteractionMode,
    ParameterOption,
    Simulation,
    SimulationKind,
    SimulationOutcome,
    SimulationParameter,
    SimulationState,
    SimulationTransition,
    StateLoopPayload,
    StateMachinePayload,
    StateMachineTransition,
    TimelineEvent,
    TimelinePayload,
    Visualization,
    VisualizationType,
    parse_visualizations,
    render_visualization,
)


BODY = "".join(
    f'<section id="{section_id}"><h2>{section_id}</h2><p>本文</p></section>'
    for section_id in (
        "why", "mental-model", "worked-example", "tradeoffs",
        "knowledge-check", "sources-next",
    )
)
TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "templates"


def _maximum_id_visual() -> dict[str, object]:
    visual_id = "v" * 64
    parameter_id = "p" * 64
    first_option = "a" * 64
    second_option = "b" * 64
    return {
        "id": visual_id,
        "type": "flow",
        "caption": "上限IDの図",
        "question": "上限長でも決定的に描画できるか",
        "afterSection": "mentalModel",
        "objectiveIds": ["obj-1"],
        "evidenceIds": ["evidence"],
        "sourceIds": ["source"],
        "expectedObservation": "生成DOM IDは短く一意になる",
        "payload": {
            "steps": [
                {"id": "start", "label": "開始", "detail": "始める"},
                {"id": "finish", "label": "終了", "detail": "終える"},
            ],
            "transitions": [{
                "id": "advance", "from": "start", "to": "finish",
                "label": "進む",
            }],
        },
        "simulation": {
            "kind": "request-path",
            "interactionMode": "scenario",
            "parameters": [{
                "id": parameter_id,
                "label": "方式",
                "control": "select",
                "options": [
                    {"id": first_option, "label": "第一"},
                    {"id": second_option, "label": "第二"},
                ],
                "defaultOptionId": first_option,
            }],
            "initialStateId": "first-state",
            "states": [
                {
                    "id": "first-state", "label": "第一", "status": "待機",
                    "when": {parameter_id: first_option},
                    "activeNodeIds": ["start"], "activeEdgeIds": [],
                },
                {
                    "id": "second-state", "label": "第二", "status": "完了",
                    "when": {parameter_id: second_option},
                    "activeNodeIds": ["finish"], "activeEdgeIds": ["advance"],
                },
            ],
            "transitions": [],
            "outcomes": [
                {"id": "first-result", "stateId": "first-state", "label": "第一"},
                {"id": "second-result", "stateId": "second-state", "label": "第二"},
            ],
        },
    }


class _SemanticParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))


def _item(identifier: str, label: str | None = None) -> Item:
    return Item(identifier, label or identifier, f"{identifier} detail")


def _visual(kind: VisualizationType, payload: object) -> Visualization:
    return Visualization(
        id=f"{kind.value}-visual",
        type=kind,
        caption="caption <unsafe>",
        question="question & answer",
        after_section=LessonSectionRole.MENTAL_MODEL,
        objective_ids=("obj-1",), evidence_ids=("evidence",),
        source_ids=("source",), expected_observation="observe > outcome",
        payload=payload, notes=("note <escaped>",), simulation=None,
    )


class VisualizationRenderingTests(unittest.TestCase):
    def payloads(self) -> dict[VisualizationType, object]:
        a, b = _item("a"), _item("b")
        edge = Relationship("a-to-b", "a", "b", "A < B")
        return {
            VisualizationType.FLOW: FlowPayload((a, b), (edge,)),
            VisualizationType.HIERARCHY: HierarchyPayload((
                HierarchyNode("a", "A", "root", None),
                HierarchyNode("b", "B", "child", "a"),
            )),
            VisualizationType.COMPARISON: ComparisonPayload(
                (a,), (b,), (ComparisonCell("cell", "a", "b", "value < x"),)
            ),
            VisualizationType.STATE_LOOP: StateLoopPayload((a, b), (edge,), "b", "a"),
            VisualizationType.CAUSAL: CausalPayload(
                (a,), (b,), (_item("outcome"),), (_item("mitigation"),), (edge,)
            ),
            VisualizationType.TIMELINE: TimelinePayload(
                (a,), (TimelineEvent("event", "Event", "detail", "a", 0, None),)
            ),
            VisualizationType.NETWORK: NetworkPayload(
                (NetworkNode("a", "A", "detail", "component"), NetworkNode("b", "B", "detail", "component")),
                (_item("component"),), (edge,),
            ),
            VisualizationType.MEMORY: MemoryPayload(
                (MemoryLayer("a", "A", "detail", "group"), MemoryLayer("b", "B", "detail", "group")),
                (Relationship("a-to-b", "a", "b", "transfer", "request"),),
            ),
            VisualizationType.MATRIX: MatrixPayload(
                (a,), (b,), (MatrixCell("cell", "a", "b", "value", "value"),)
            ),
            VisualizationType.STATE_MACHINE: StateMachinePayload(
                (a, b), "a", (StateMachineTransition("a-to-b", "a", "b", "next", "allowed", None),)
            ),
        }

    def test_ten_types_emit_their_native_static_semantic_oracle(self) -> None:
        expected_tags = {
            VisualizationType.FLOW: {"ol"},
            VisualizationType.TIMELINE: {"ol"},
            VisualizationType.HIERARCHY: {"ul", "dl"},
            VisualizationType.CAUSAL: {"dl", "ul"},
            VisualizationType.COMPARISON: {"table", "th"},
            VisualizationType.MATRIX: {"table", "th"},
            VisualizationType.STATE_MACHINE: {"ul", "table"},
            VisualizationType.STATE_LOOP: {"ul"},
            VisualizationType.NETWORK: {"ul"},
            VisualizationType.MEMORY: {"ol", "ul"},
        }
        for kind, payload in self.payloads().items():
            with self.subTest(kind=kind):
                html = render_visualization("core-01-systems-tradeoffs", _visual(kind, payload)).value
                parser = _SemanticParser()
                parser.feed(html)
                tags = {tag for tag, _ in parser.tags}
                self.assertLessEqual(expected_tags[kind], tags)
                self.assertIn(f"visualization--{kind.value}", html)
                self.assertIn("&lt;unsafe&gt;", html)
                self.assertIn("question &amp; answer", html)
                self.assertIn("note &lt;escaped&gt;", html)
                self.assertNotIn("caption <unsafe>", html)
                for tag, attrs in parser.tags:
                    if "connector" in (attrs.get("class") or ""):
                        self.assertNotEqual(tag, "span")

    def test_tables_have_scoped_row_and_column_headers(self) -> None:
        for kind in (VisualizationType.COMPARISON, VisualizationType.MATRIX):
            html = render_visualization("core-01-systems-tradeoffs", _visual(kind, self.payloads()[kind])).value
            self.assertIn('scope="col"', html)
            self.assertIn('scope="row"', html)

    def test_relationship_oracles_name_both_endpoints(self) -> None:
        for kind in (VisualizationType.STATE_LOOP, VisualizationType.NETWORK, VisualizationType.MEMORY):
            html = render_visualization("core-01-systems-tradeoffs", _visual(kind, self.payloads()[kind])).value
            self.assertIn("A", html)
            self.assertIn("B", html)
            self.assertIn("→", html)

    def test_visual_is_interleaved_after_complete_logical_section(self) -> None:
        visual = _visual(VisualizationType.FLOW, self.payloads()[VisualizationType.FLOW])
        rendered = render_lesson_body(
            "core-01-systems-tradeoffs", parse_lesson_body(BODY), (visual,)
        ).value
        mental_end = rendered.index("</section>", rendered.index('id="mental-model"'))
        figure = rendered.index("<figure", mental_end)
        worked = rendered.index('id="worked-example"')
        self.assertLess(mental_end, figure)
        self.assertLess(figure, worked)

    def test_lesson_body_renderer_requires_authored_section_provenance(self) -> None:
        body = parse_lesson_body(BODY)
        forged_section = LessonSection(
            LessonSectionRole.WHY,
            validate_generated_fragment(
                '<section id="why"><button type="button" disabled>'
                "unsafe</button></section>"
            ),
        )
        forged_body = LessonBody((forged_section, *body.sections[1:]))

        with self.assertRaisesRegex(CurriculumValidationError, "authored"):
            render_lesson_body(
                "core-01-systems-tradeoffs",
                forged_body,
                (),
            )

    def test_schema_maximum_ids_render_with_bounded_unique_deterministic_dom_ids(self) -> None:
        visual = parse_visualizations(
            [_maximum_id_visual()],
            lesson_id="core-01-systems-tradeoffs",
            complete=False,
            objective_evidence={"obj-1": frozenset({"evidence"})},
            evidence_ids=frozenset({"evidence"}),
            source_ids=frozenset({"source"}),
        )[0]

        first = render_visualization("core-01-systems-tradeoffs", visual)
        second = render_visualization("core-01-systems-tradeoffs", visual)
        page = Renderer(TEMPLATE_ROOT).page(
            output_path=Path("lessons/core-01-systems-tradeoffs/index.html"),
            title="上限ID",
            description="上限IDの描画検証",
            content=first,
        )
        parser = _SemanticParser()
        parser.feed(page)
        ids = [value for _, attrs in parser.tags if (value := attrs.get("id"))]
        labels = [value for tag, attrs in parser.tags if tag == "label" and (value := attrs.get("for"))]
        controls = [
            attrs for tag, attrs in parser.tags
            if tag in {"button", "input", "select"}
        ]

        self.assertEqual(first.value, second.value)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(len(identifier) <= 64 for identifier in ids))
        self.assertTrue(all(target in ids for target in labels))
        self.assertTrue(all(control.get("id") in ids for control in controls))
        self.assertNotIn("v" * 64, ids)
        self.assertNotIn("p" * 64, ids)

    def test_lesson_body_rejects_generated_visual_namespace_collision(self) -> None:
        body = parse_lesson_body(BODY)
        first = _visual(VisualizationType.FLOW, self.payloads()[VisualizationType.FLOW])
        second = replace(first, id="second-visual")

        with (
            patch(
                "curriculum_builder.lesson_rendering.visualization_dom_namespace",
                return_value="viz-forced-collision",
                create=True,
            ),
            self.assertRaisesRegex(CurriculumValidationError, "namespace collision"),
        ):
            render_lesson_body(
                "core-01-systems-tradeoffs",
                body,
                (first, second),
            )

    def test_simulation_static_oracle_precedes_controls_and_is_complete(self) -> None:
        visual = _visual(VisualizationType.FLOW, self.payloads()[VisualizationType.FLOW])
        simulation = Simulation(
            SimulationKind.REQUEST_PATH,
            InteractionMode.HYBRID,
            (SimulationParameter(
                "fault", "障害", "radio",
                (ParameterOption("none", "障害なし"), ParameterOption("drop", "破棄")),
                "none",
            ),),
            "ready",
            (SimulationState(
                "ready", "準備", "送信可能", {"fault": "none"},
                ("a",), ("a-to-b",),
            ),),
            (SimulationTransition(
                "retry", "ready", "ready", "parameter-change", {"fault": "drop"}
            ),),
            (SimulationOutcome("delivered", "ready", "到達を観測"),),
            1000,
        )
        visual = replace(visual, simulation=simulation)

        html = render_visualization("core-01-systems-tradeoffs", visual).value

        for expected in (
            "障害なし", "破棄", "fault=none", "a-to-b",
            "fault=drop", "parameter-change", "到達を観測",
            "現在の状態", "送信可能", "例示的", "決定的",
            "visualization__controls", "hidden", "disabled",
            "適用", "再生", "一時停止", "前へ", "次へ", "リセット",
        ):
            self.assertIn(expected, html)
        self.assertLess(
            html.index("visualization__simulation-oracle"),
            html.index("visualization__controls"),
        )
        parser = _SemanticParser()
        parser.feed(html)
        ids = {
            value for _, attrs in parser.tags
            if (value := attrs.get("id")) is not None
        }
        controls = [
            attrs for tag, attrs in parser.tags
            if tag in {"button", "input", "select"}
        ]
        labels = [
            attrs["for"] for tag, attrs in parser.tags
            if tag == "label" and attrs.get("for") is not None
        ]
        self.assertTrue(all(control.get("id") in ids for control in controls))
        self.assertTrue(all(target in ids for target in labels))

    def test_timeline_groups_ordered_events_under_each_phase(self) -> None:
        payload = TimelinePayload(
            (_item("plan", "計画"), _item("release", "公開")),
            (
                TimelineEvent("draft", "下書き", "詳細1", "plan", 0, None),
                TimelineEvent("review", "レビュー", "詳細2", "plan", 1, None),
                TimelineEvent("ship", "公開", "詳細3", "release", 2, None),
            ),
        )
        html = render_visualization(
            "core-01-systems-tradeoffs",
            _visual(VisualizationType.TIMELINE, payload),
        ).value

        self.assertIn('class="visualization__timeline-phases"', html)
        self.assertEqual(html.count('class="visualization__timeline-events"'), 2)
        self.assertEqual(html.count("計画</strong>"), 1)
        self.assertLess(html.index("下書き"), html.index("レビュー"))
        self.assertLess(html.index("レビュー"), html.index("公開</strong>"))

    def test_simulation_controls_match_each_interaction_mode(self) -> None:
        base = Simulation(
            SimulationKind.REQUEST_PATH,
            InteractionMode.SCENARIO,
            (SimulationParameter(
                "fault", "障害", "select",
                (ParameterOption("none", "なし"), ParameterOption("drop", "破棄")),
                "none",
            ),),
            "ready",
            (SimulationState("ready", "準備", "待機", {}, (), ()),),
            (),
            (SimulationOutcome("ready-outcome", "ready", "準備完了"),),
            None,
        )
        expected = {
            InteractionMode.SCENARIO: (("適用", "リセット"), ("再生", "前へ")),
            InteractionMode.STEPPER: (("前へ", "次へ", "リセット"), ("適用", "再生")),
            InteractionMode.PLAYBACK: (("再生", "一時停止", "前へ", "次へ", "速度", "リセット"), ("適用",)),
            InteractionMode.HYBRID: (("適用", "再生", "一時停止", "前へ", "次へ", "速度", "リセット"), ()),
            InteractionMode.EXPLORER: (("適用", "前へ", "次へ", "リセット"), ("再生", "速度")),
        }
        payload = self.payloads()[VisualizationType.FLOW]
        for mode, (present, absent) in expected.items():
            with self.subTest(mode=mode):
                visual = replace(
                    _visual(VisualizationType.FLOW, payload),
                    simulation=replace(base, interaction_mode=mode),
                )
                html = render_visualization("core-01-systems-tradeoffs", visual).value
                controls = html[html.index("visualization__controls"):]
                for label in present:
                    self.assertIn(label, controls)
                for label in absent:
                    self.assertNotIn(label, controls)

    def test_stepper_without_parameters_omits_empty_parameter_table(self) -> None:
        simulation = Simulation(
            SimulationKind.REQUEST_PATH,
            InteractionMode.STEPPER,
            (), "ready",
            (SimulationState("ready", "準備", "待機", {}, (), ()),),
            (),
            (SimulationOutcome("ready-outcome", "ready", "準備完了"),),
            None,
        )
        visual = replace(
            _visual(VisualizationType.FLOW, self.payloads()[VisualizationType.FLOW]),
            simulation=simulation,
        )

        html = render_visualization("core-01-systems-tradeoffs", visual).value

        self.assertNotIn("パラメータと選択肢", html)
        self.assertIn("完全な遷移", html)
        self.assertIn("観測結果", html)

    def test_timeline_rejects_phase_order_that_reverses_total_event_order(self) -> None:
        raw = [{
            "id": "timeline-order",
            "type": "timeline",
            "caption": "順序",
            "question": "どの順で進むか",
            "afterSection": "mentalModel",
            "objectiveIds": ["obj-1"],
            "evidenceIds": ["evidence"],
            "sourceIds": ["source"],
            "expectedObservation": "前期から後期へ進む",
            "payload": {
                "phases": [
                    {"id": "late", "label": "後期", "detail": "後半"},
                    {"id": "early", "label": "前期", "detail": "前半"},
                ],
                "events": [
                    {"id": "first", "label": "開始", "detail": "先", "phaseId": "early", "order": 0},
                    {"id": "second", "label": "終了", "detail": "後", "phaseId": "late", "order": 1},
                ],
            },
        }]

        with self.assertRaisesRegex(CurriculumValidationError, "phase order"):
            parse_visualizations(
                raw,
                lesson_id="core-01-systems-tradeoffs",
                complete=False,
                objective_evidence={"obj-1": frozenset({"evidence"})},
                evidence_ids=frozenset({"evidence"}),
                source_ids=frozenset({"source"}),
            )


if __name__ == "__main__":
    unittest.main()
