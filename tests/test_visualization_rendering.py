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
            VisualizationType.STATE_LOOP: StateLoopPayload(
                (a, b),
                (edge, Relationship("b-to-a", "b", "a", "B to A")),
                "b",
                "a",
            ),
            VisualizationType.CAUSAL: CausalPayload(
                (a,),
                (b,),
                (_item("outcome"),),
                (_item("mitigation"),),
                (
                    edge,
                    Relationship("b-to-outcome", "b", "outcome", "leads"),
                    Relationship(
                        "mitigation-to-outcome",
                        "mitigation",
                        "outcome",
                        "reduces",
                    ),
                ),
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

    def test_generic_notes_render_before_model_without_legacy_claims(self) -> None:
        html = render_visualization(
            "core-01-systems-tradeoffs",
            _visual(
                VisualizationType.FLOW,
                self.payloads()[VisualizationType.FLOW],
            ),
        ).value

        heading = html.index("注記")
        explanation = html.index("図を読む際の補足情報です。")
        notes = html.index('class="visualization__companion-notes"')
        first_note = html.index("note &lt;escaped&gt;")
        model = html.index("a detail")
        self.assertLess(heading, explanation)
        self.assertLess(explanation, notes)
        self.assertLess(notes, first_note)
        self.assertLess(first_note, model)
        self.assertNotIn("旧図", html)
        self.assertIn(
            '<ol class="visualization__companion-notes">',
            html,
        )
        self.assertNotIn('class="visualization__notes"', html)

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

    def test_lesson_body_rejects_visual_count_before_reading_models(self) -> None:
        body = parse_lesson_body(BODY)
        unreadable = object.__new__(Visualization)

        for count in (3, 10_000):
            with self.subTest(count=count):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    "at most two",
                ):
                    render_lesson_body(
                        "core-01-systems-tradeoffs",
                        body,
                        (unreadable,) * count,
                    )

    def test_renderer_rejects_direct_payload_type_mismatch(self) -> None:
        flow = _visual(
            VisualizationType.FLOW,
            self.payloads()[VisualizationType.FLOW],
        )
        matrix = self.payloads()[VisualizationType.MATRIX]

        with self.assertRaisesRegex(CurriculumValidationError, "payload"):
            render_visualization(
                "core-01-systems-tradeoffs",
                replace(flow, payload=matrix),
            )

    def test_renderer_rejects_direct_dangling_flow_relationship(self) -> None:
        payload = FlowPayload(
            (_item("start"), _item("finish")),
            (Relationship("dangling", "start", "missing", "進む"),),
        )

        with self.assertRaisesRegex(CurriculumValidationError, "dangling"):
            render_visualization(
                "core-01-systems-tradeoffs",
                _visual(VisualizationType.FLOW, payload),
            )

    def test_renderer_rejects_enum_shaped_direct_visualization(self) -> None:
        visual = _visual(
            VisualizationType.FLOW,
            self.payloads()[VisualizationType.FLOW],
        )
        object.__setattr__(visual, "type", "flow")

        with self.assertRaisesRegex(CurriculumValidationError, "type"):
            render_visualization("core-01-systems-tradeoffs", visual)

    def test_renderer_converts_missing_model_slots_to_safe_validation_errors(self) -> None:
        def parsed_visual() -> Visualization:
            raw = _maximum_id_visual()
            simulation = raw["simulation"]
            assert isinstance(simulation, dict)
            parameter_id = "p" * 64
            second_option = "b" * 64
            simulation["transitions"] = [{
                "id": "advance-state",
                "from": "first-state",
                "to": "second-state",
                "event": "parameter-change",
                "when": {parameter_id: second_option},
            }]
            return parse_visualizations(
                [raw],
                lesson_id="core-01-systems-tradeoffs",
                complete=False,
                objective_evidence={"obj-1": frozenset({"evidence"})},
                evidence_ids=frozenset({"evidence"}),
                source_ids=frozenset({"source"}),
            )[0]

        cases = (
            ("visualization", lambda visual: visual, "caption"),
            ("payload", lambda visual: visual.payload, "steps"),
            ("item", lambda visual: visual.payload.steps[0], "label"),
            ("relationship", lambda visual: visual.payload.transitions[0], "to_id"),
            ("simulation", lambda visual: visual.simulation, "parameters"),
            (
                "parameter",
                lambda visual: visual.simulation.parameters[0],
                "options",
            ),
            (
                "option",
                lambda visual: visual.simulation.parameters[0].options[0],
                "label",
            ),
            ("state", lambda visual: visual.simulation.states[0], "active_node_ids"),
            (
                "simulation-transition",
                lambda visual: visual.simulation.transitions[0],
                "from_id",
            ),
            ("outcome", lambda visual: visual.simulation.outcomes[0], "state_id"),
        )
        blank = object.__new__(Visualization)
        with self.assertRaisesRegex(CurriculumValidationError, "structure"):
            render_visualization("core-01-systems-tradeoffs", blank)

        for label, target, slot in cases:
            with self.subTest(label=label):
                visual = parsed_visual()
                nested = target(visual)
                assert nested is not None
                object.__delattr__(nested, slot)
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    "structure",
                ) as caught:
                    render_visualization(
                        "core-01-systems-tradeoffs",
                        visual,
                    )
                self.assertNotIn("PRIVATE", str(caught.exception))

        payload_cases = (
            (VisualizationType.HIERARCHY, lambda payload: payload.nodes[0], "parent_id"),
            (VisualizationType.COMPARISON, lambda payload: payload.cells[0], "value"),
            (VisualizationType.TIMELINE, lambda payload: payload.events[0], "phase_id"),
            (VisualizationType.NETWORK, lambda payload: payload.nodes[0], "component_id"),
            (VisualizationType.MEMORY, lambda payload: payload.layers[0], "group"),
            (VisualizationType.MATRIX, lambda payload: payload.cells[0], "status"),
            (
                VisualizationType.STATE_MACHINE,
                lambda payload: payload.transitions[0],
                "reason",
            ),
        )
        for kind, target, slot in payload_cases:
            with self.subTest(nested_kind=kind):
                payload = self.payloads()[kind]
                visual = _visual(kind, payload)
                object.__delattr__(target(payload), slot)
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    "structure",
                ):
                    render_visualization(
                        "core-01-systems-tradeoffs",
                        visual,
                    )

    def test_renderer_does_not_swallow_process_control_failures(self) -> None:
        visual = _visual(
            VisualizationType.FLOW,
            self.payloads()[VisualizationType.FLOW],
        )
        for failure in (MemoryError(), SystemExit(), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__), patch(
                "curriculum_builder.visualizations._payload_render_raw",
                side_effect=failure,
            ):
                with self.assertRaises(type(failure)):
                    render_visualization(
                        "core-01-systems-tradeoffs",
                        visual,
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
            (
                SimulationState(
                    "ready", "準備", "送信可能", {},
                    ("a",), ("a-to-b",),
                ),
                SimulationState(
                    "dropped", "破棄", "再試行", {"fault": "drop"},
                    ("b",), (),
                ),
            ),
            (SimulationTransition(
                "retry", "ready", "dropped", "parameter-change", {"fault": "drop"}
            ),),
            (SimulationOutcome("delivered", "ready", "到達を観測"),),
            1000,
        )
        visual = replace(visual, simulation=simulation)

        html = render_visualization("core-01-systems-tradeoffs", visual).value

        for expected in (
            "障害なし", "破棄", "a-to-b",
            "fault=drop", "parameter-change", "到達を観測",
            "現在の状態", "送信可能", "例示的", "決定的",
            "visualization__controls", "hidden", "disabled",
            "適用", "再生", "一時停止", "前へ", "次へ", "リセット",
        ):
            self.assertIn(expected, html)
        for expected_attribute in (
            'data-initial-state-id="ready"',
            'class="visualization__state-condition"',
            'data-parameter-id="fault"',
            'data-option-id="drop"',
            'class="visualization__simulation-transition"',
            'data-transition-id="retry"',
            'data-from-state-id="ready"',
            'data-to-state-id="dropped"',
            'class="visualization__transition-condition"',
            'class="visualization__simulation-outcome"',
            'data-outcome-id="delivered"',
        ):
            self.assertIn(expected_attribute, html)
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
                interval = (
                    1000
                    if mode in {InteractionMode.PLAYBACK, InteractionMode.HYBRID}
                    else None
                )
                visual = replace(
                    _visual(VisualizationType.FLOW, payload),
                    simulation=replace(
                        base,
                        interaction_mode=mode,
                        default_interval_ms=interval,
                    ),
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
