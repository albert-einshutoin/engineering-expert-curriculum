from __future__ import annotations

from html.parser import HTMLParser
import unittest

from curriculum_builder.lesson_rendering import parse_lesson_body, render_lesson_body
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
    render_visualization,
)


BODY = "".join(
    f'<section id="{section_id}"><h2>{section_id}</h2><p>本文</p></section>'
    for section_id in (
        "why", "mental-model", "worked-example", "tradeoffs",
        "knowledge-check", "sources-next",
    )
)


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

    def test_simulation_static_oracle_precedes_controls_and_is_complete(self) -> None:
        visual = _visual(VisualizationType.FLOW, self.payloads()[VisualizationType.FLOW])
        simulation = Simulation(
            SimulationKind.REQUEST_PATH,
            InteractionMode.HYBRID,
            (SimulationParameter(
                "fault", "障害", "select",
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
        object.__setattr__(visual, "simulation", simulation)

        html = render_visualization("core-01-systems-tradeoffs", visual).value

        for expected in (
            "障害なし", "破棄", "fault=none", "a-to-b",
            "fault=drop", "parameter-change", "到達を観測",
        ):
            self.assertIn(expected, html)
        if "visualization__controls" in html:
            self.assertLess(
                html.index("visualization__simulation-oracle"),
                html.index("visualization__controls"),
            )


if __name__ == "__main__":
    unittest.main()
