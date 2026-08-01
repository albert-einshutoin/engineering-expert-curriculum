from __future__ import annotations

from dataclasses import FrozenInstanceError
from copy import deepcopy
import json
from pathlib import Path
from types import MappingProxyType
import unittest

from curriculum_builder.errors import CurriculumValidationError
from curriculum_builder.visualizations import (
    LessonSectionRole,
    SimulationState,
    SimulationTransition,
    VisualizationType,
    parse_visualization_catalog_bytes,
    parse_visualizations,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ASSIGNMENTS = (
    ("core-01-systems-tradeoffs", "causal", "matrix", False, None),
    ("core-02-algorithms-measurement", "comparison", "flow", True, ("complexity-growth", "scenario", "complexity-growth-static", ("small-input", "crossover", "large-input"))),
    ("core-03-architecture-memory-caches", "memory", "matrix", True, ("memory-access", "hybrid", "memory-access-static", ("tlb-lookup", "l1-hit", "memory-return"))),
    ("core-04-os-processes-concurrency", "timeline", "state-machine", True, ("scheduler-interleaving", "playback", "scheduler-interleaving-static", ("read-old-value", "lost-update", "locked-complete"))),
    ("core-05-networks-latency-failure", "timeline", "comparison", True, ("request-path", "hybrid", "request-path-static", ("dns-lookup", "tls-ready", "deadline-exceeded"))),
    ("core-06-requirements-domain-modeling", "network", "state-machine", False, None),
    ("core-07-api-contract-design", "state-machine", "timeline", True, ("retry-contract", "playback", "retry-contract-static", ("request-accepted", "response-lost", "retry-replayed"))),
    ("core-08-modularity-evolutionary-architecture", "network", "matrix", False, None),
    ("core-09-test-strategy-tdd", "state-loop", "matrix", False, None),
    ("core-10-threat-modeling-secure-design", "network", "matrix", False, None),
    ("core-11-data-modeling-storage", "matrix", "flow", False, None),
    ("core-12-transactions-isolation-consistency", "timeline", "network", True, ("isolation-schedule", "hybrid", "isolation-schedule-static", ("concurrent-read", "write-skew", "transaction-retried"))),
    ("core-13-distributed-coordination-failure", "timeline", "state-machine", True, ("distributed-failure", "hybrid", "distributed-failure-static", ("duplicate-received", "partition-detected", "recovery-converged"))),
    ("core-14-performance-capacity", "causal", "comparison", True, ("queue-capacity", "scenario", "queue-capacity-static", ("stable-load", "saturation", "capacity-recovered"))),
    ("core-15-reliability-observability-slo", "state-loop", "timeline", True, ("slo-burn", "scenario", "slo-burn-static", ("budget-healthy", "fast-burn", "page-triggered"))),
    ("core-16-hci-usability-accessibility", "flow", "matrix", True, ("accessible-ui-state", "explorer", "accessible-ui-state-static", ("narrow-viewport", "keyboard-focus", "reduced-motion"))),
    ("core-17-graphics-visual-information", "flow", "comparison", False, None),
    ("core-18-product-discovery-experiments", "causal", "matrix", False, None),
    ("core-19-technical-communication-design-docs", "hierarchy", "comparison", False, None),
    ("core-20-ethics-privacy-societal-impact", "causal", "matrix", False, None),
    ("core-21-maintenance-legacy-comprehension", "network", "state-loop", False, None),
    ("core-22-evolution-safe-migrations", "state-machine", "timeline", True, ("migration-phase", "playback", "migration-phase-static", ("expand-ready", "backfill-paused", "contract-complete"))),
    ("core-23-incident-response-learning", "timeline", "causal", False, None),
    ("core-24-delivery-ci-release-safety", "state-machine", "network", True, ("release-safety", "playback", "release-safety-static", ("artifact-verified", "canary-rejected", "rollback-complete"))),
    ("core-25-engineering-economics-capacity", "matrix", "comparison", False, None),
    ("core-26-code-review-collaborative-quality", "state-loop", "matrix", False, None),
    ("core-27-team-interfaces-sociotechnical-architecture", "network", "matrix", False, None),
    ("core-28-oss-governance-stewardship", "flow", "hierarchy", False, None),
    ("core-29-cross-cultural-async-collaboration", "timeline", "matrix", False, None),
    ("core-30-evidence-based-technical-leadership", "causal", "matrix", False, None),
)


def _item(identifier: str) -> dict[str, object]:
    return {"id": identifier, "label": identifier.title(), "detail": "説明"}


def _payloads() -> dict[str, dict[str, object]]:
    return {
        "flow": {
            "steps": [_item("start"), _item("finish")],
            "transitions": [
                {"id": "advance", "from": "start", "to": "finish", "label": "進む"}
            ],
        },
        "hierarchy": {
            "nodes": [
                {**_item("root"), "parentId": None},
                {**_item("child"), "parentId": "root"},
            ]
        },
        "comparison": {
            "alternatives": [_item("left"), _item("right")],
            "criteria": [_item("cost")],
            "cells": [
                {"id": "left-cost", "alternativeId": "left", "criterionId": "cost", "value": "低い"},
                {"id": "right-cost", "alternativeId": "right", "criterionId": "cost", "value": "高い"},
            ],
        },
        "state-loop": {
            "states": [_item("ready"), _item("retry"), _item("done")],
            "transitions": [
                {"id": "fail", "from": "ready", "to": "retry", "label": "失敗"},
                {"id": "again", "from": "retry", "to": "ready", "label": "再試行"},
                {"id": "recover", "from": "retry", "to": "done", "label": "復旧"},
            ],
            "exitStateId": "done",
            "recoveryStateId": "retry",
        },
        "causal": {
            "causes": [_item("load")],
            "mechanisms": [_item("queue")],
            "outcomes": [_item("delay")],
            "mitigations": [_item("limit")],
            "relations": [
                {"id": "load-queues", "from": "load", "to": "queue", "label": "蓄積"},
                {"id": "queue-delays", "from": "queue", "to": "delay", "label": "待機"},
                {"id": "limit-load", "from": "limit", "to": "load", "label": "抑制"},
            ],
        },
        "timeline": {
            "phases": [_item("expand")],
            "events": [{**_item("deploy"), "phaseId": "expand", "order": 1}],
        },
        "network": {
            "nodes": [
                {**_item("client"), "componentId": "path"},
                {**_item("server"), "componentId": "path"},
            ],
            "components": [_item("path")],
            "connections": [
                {"id": "request", "from": "client", "to": "server", "label": "要求"}
            ],
        },
        "memory": {
            "layers": [
                {**_item("cpu"), "group": "request"},
                {**_item("cache"), "group": "storage"},
            ],
            "transfers": [
                {"id": "load", "from": "cpu", "to": "cache", "label": "読込", "kind": "request"}
            ],
        },
        "matrix": {
            "rows": [_item("fast")],
            "columns": [_item("safe")],
            "cells": [
                {"id": "fast-safe", "rowId": "fast", "columnId": "safe", "value": "適合", "status": "value"}
            ],
        },
        "state-machine": {
            "states": [_item("idle"), _item("running")],
            "initialStateId": "idle",
            "transitions": [
                {"id": "start", "from": "idle", "to": "running", "event": "next", "status": "allowed"},
                {"id": "reject", "from": "running", "to": "running", "event": "next", "status": "rejected", "reason": "完了後は開始できない"},
            ],
        },
    }


def _visual(kind: str, payload: dict[str, object], **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": f"{kind}-visual",
        "type": kind,
        "caption": "関係を説明する図",
        "question": "何がどこへ進むか",
        "afterSection": "mentalModel",
        "objectiveIds": ["obj-path"],
        "evidenceIds": ["trace"],
        "sourceIds": ["source-one"],
        "expectedObservation": "経路と結果を説明できる",
        "payload": payload,
        "notes": ["この図は診断用の限定モデルである"],
    }
    value.update(overrides)
    return value


def _parse(value: object, *, complete: bool = True):
    return parse_visualizations(
        value,
        lesson_id="core-01-example",
        complete=complete,
        objective_evidence={"obj-path": frozenset({"trace"})},
        evidence_ids=frozenset({"trace"}),
        source_ids=frozenset({"source-one"}),
    )


def _scenario_simulation() -> dict[str, object]:
    return {
        "kind": "complexity-growth",
        "interactionMode": "scenario",
        "parameters": [{
            "id": "size", "label": "入力", "control": "select",
            "options": [{"id": "small", "label": "小"}, {"id": "large", "label": "大"}],
            "defaultOptionId": "small",
        }],
        "initialStateId": "small-state",
        "states": [
            {"id": "small-state", "label": "小", "status": "一定", "when": {"size": "small"}, "activeNodeIds": ["start"], "activeEdgeIds": []},
            {"id": "large-state", "label": "大", "status": "増加", "when": {"size": "large"}, "activeNodeIds": ["finish"], "activeEdgeIds": ["advance"]},
        ],
        "transitions": [],
        "outcomes": [
            {"id": "small-result", "stateId": "small-state", "label": "小さい入力"},
            {"id": "large-result", "stateId": "large-state", "label": "大きい入力"},
        ],
    }


class VisualizationCatalogTests(unittest.TestCase):
    def _catalog_bytes(self) -> bytes:
        return (REPOSITORY_ROOT / "content/visualization-catalog.json").read_bytes()

    def _projection(self, catalog) -> tuple[tuple[object, ...], ...]:
        return tuple(
            (
                assignment.lesson_id,
                assignment.primary_type.value,
                assignment.optional_secondary_type.value,
                assignment.dynamic,
                None
                if assignment.simulation is None
                else (
                    assignment.simulation.kind.value,
                    assignment.simulation.interaction_mode.value,
                    assignment.simulation.static_equivalent_id,
                    assignment.simulation.visual_regression_state_ids,
                ),
            )
            for assignment in catalog.lessons
        )

    def test_repository_catalog_matches_the_independent_exact_inventory(self) -> None:
        catalog = parse_visualization_catalog_bytes(
            self._catalog_bytes(),
            "visualization-catalog.json",
        )

        self.assertEqual(catalog.version, 1)
        self.assertEqual(self._projection(catalog), EXPECTED_ASSIGNMENTS)

    def test_catalog_parser_rejects_shape_sort_duplicate_and_enum_mutations(self) -> None:
        baseline = json.loads(self._catalog_bytes())
        mutations: list[tuple[str, dict[str, object]]] = []

        unknown_root = deepcopy(baseline)
        unknown_root["defaultPrimaryType"] = "flow"
        mutations.append(("root shape", unknown_root))
        for field in ("version", "lessons"):
            missing_root_field = deepcopy(baseline)
            missing_root_field.pop(field)
            mutations.append((f"root missing {field}", missing_root_field))
        invalid_version = deepcopy(baseline)
        invalid_version["version"] = True
        mutations.append(("version invalid", invalid_version))
        twenty_nine_rows = deepcopy(baseline)
        twenty_nine_rows["lessons"].pop()
        mutations.append(("29 rows", twenty_nine_rows))
        thirty_one_rows = deepcopy(baseline)
        extra_row = deepcopy(thirty_one_rows["lessons"][-1])
        extra_row["lessonId"] = "core-30-z-extra"
        thirty_one_rows["lessons"].append(extra_row)
        mutations.append(("31 rows", thirty_one_rows))

        for field in (
            "lessonId",
            "primaryType",
            "optionalSecondaryType",
            "dynamic",
        ):
            missing_row_field = deepcopy(baseline)
            missing_row_field["lessons"][1].pop(field)
            mutations.append((f"row missing {field}", missing_row_field))
        row_level = deepcopy(baseline)
        row_level["lessons"][1]["interactionMode"] = "scenario"
        mutations.append(("row-level simulation", row_level))
        static_simulation = deepcopy(baseline)
        static_simulation["lessons"][0]["simulation"] = deepcopy(
            static_simulation["lessons"][1]["simulation"]
        )
        mutations.append(("static simulation", static_simulation))
        unsorted = deepcopy(baseline)
        unsorted["lessons"][0], unsorted["lessons"][1] = (
            unsorted["lessons"][1], unsorted["lessons"][0]
        )
        mutations.append(("sort", unsorted))
        duplicate = deepcopy(baseline)
        duplicate["lessons"][1]["lessonId"] = duplicate["lessons"][0]["lessonId"]
        mutations.append(("duplicate", duplicate))
        invalid_primary_type = deepcopy(baseline)
        invalid_primary_type["lessons"][0]["primaryType"] = "graph"
        mutations.append(("primaryType enum", invalid_primary_type))
        invalid_secondary_type = deepcopy(baseline)
        invalid_secondary_type["lessons"][0]["optionalSecondaryType"] = "graph"
        mutations.append(("optionalSecondaryType enum", invalid_secondary_type))

        missing_dynamic_simulation = deepcopy(baseline)
        missing_dynamic_simulation["lessons"][1].pop("simulation")
        mutations.append(
            ("dynamic simulation missing", missing_dynamic_simulation)
        )
        unknown_simulation_field = deepcopy(baseline)
        unknown_simulation_field["lessons"][1]["simulation"]["seed"] = 1
        mutations.append(("simulation unknown field", unknown_simulation_field))
        for field in (
            "kind",
            "interactionMode",
            "staticEquivalentId",
            "visualRegressionStateIds",
        ):
            missing_simulation_field = deepcopy(baseline)
            missing_simulation_field["lessons"][1]["simulation"].pop(field)
            mutations.append(
                (f"simulation missing {field}", missing_simulation_field)
            )
        invalid_kind = deepcopy(baseline)
        invalid_kind["lessons"][1]["simulation"]["kind"] = "unknown-kind"
        mutations.append(("simulation kind enum", invalid_kind))
        invalid_interaction_mode = deepcopy(baseline)
        invalid_interaction_mode["lessons"][1]["simulation"][
            "interactionMode"
        ] = "random"
        mutations.append(
            ("simulation interactionMode enum", invalid_interaction_mode)
        )

        regression_ids = {
            state_id
            for row in baseline["lessons"]
            if "simulation" in row
            for state_id in row["simulation"]["visualRegressionStateIds"]
        }
        duplicate_boundary_id = "mutation-boundary"
        control_boundary_id = "mutation-control"
        self.assertTrue(
            {duplicate_boundary_id, control_boundary_id}.isdisjoint(regression_ids)
        )
        duplicate_regression_state = deepcopy(baseline)
        duplicate_regression_state["lessons"][1]["simulation"][
            "visualRegressionStateIds"
        ] = [duplicate_boundary_id, duplicate_boundary_id, control_boundary_id]
        mutations.append(
            ("duplicate visualRegressionStateIds", duplicate_regression_state)
        )

        self.assertEqual(len(mutations), 25)
        self.assertEqual(len(mutations), len({name for name, _ in mutations}))
        for name, document in mutations:
            with self.subTest(name=name):
                with self.assertRaises(CurriculumValidationError):
                    parse_visualization_catalog_bytes(
                        json.dumps(document).encode(),
                        "mutated.json",
                    )

    def test_independent_inventory_rejects_assignment_swaps(self) -> None:
        document = json.loads(self._catalog_bytes())
        document["lessons"][0]["primaryType"], document["lessons"][1]["primaryType"] = (
            document["lessons"][1]["primaryType"],
            document["lessons"][0]["primaryType"],
        )
        catalog = parse_visualization_catalog_bytes(
            json.dumps(document).encode(),
            "swapped.json",
        )

        with self.assertRaises(AssertionError):
            self.assertEqual(self._projection(catalog), EXPECTED_ASSIGNMENTS)


class VisualizationModelTests(unittest.TestCase):
    def test_direct_simulation_constructors_detach_when_mappings(self) -> None:
        state_when = {"size": "small"}
        transition_when = {"size": "small"}

        state = SimulationState(
            "ready", "準備", "待機", state_when, ("start",), ()
        )
        transition = SimulationTransition(
            "advance", "ready", "done", "next", transition_when
        )
        state_when["size"] = "large"
        transition_when["size"] = "large"

        self.assertEqual(dict(state.when), {"size": "small"})
        self.assertEqual(dict(transition.when), {"size": "small"})
        self.assertIsInstance(state.when, MappingProxyType)
        self.assertIsInstance(transition.when, MappingProxyType)
        with self.assertRaises(TypeError):
            state.when["size"] = "large"  # type: ignore[index]
        with self.assertRaises(TypeError):
            transition.when["size"] = "large"  # type: ignore[index]

    def test_after_section_uses_the_closed_section_role_enum(self) -> None:
        visual = _parse([_visual("flow", deepcopy(_payloads()["flow"]))])[0]

        self.assertIsInstance(visual.after_section, LessonSectionRole)
        self.assertEqual(visual.after_section, LessonSectionRole.MENTAL_MODEL)

    def test_accepts_all_ten_payloads_with_common_fields_in_authored_order(self) -> None:
        raw = [_visual(kind, payload) for kind, payload in _payloads().items()]

        parsed = tuple(_parse([visual]) [0] for visual in raw)

        self.assertEqual(
            tuple(item.type for item in parsed),
            tuple(VisualizationType(kind) for kind in _payloads()),
        )
        self.assertTrue(all(item.caption == "関係を説明する図" for item in parsed))
        self.assertTrue(all(item.objective_ids == ("obj-path",) for item in parsed))
        self.assertTrue(all(item.evidence_ids == ("trace",) for item in parsed))
        self.assertTrue(all(item.source_ids == ("source-one",) for item in parsed))
        self.assertTrue(all(item.notes == ("この図は診断用の限定モデルである",) for item in parsed))

    def test_result_is_a_detached_immutable_tuple_snapshot(self) -> None:
        raw = [_visual("flow", _payloads()["flow"])]
        parsed = _parse(raw)
        raw.clear()

        self.assertIsInstance(parsed, tuple)
        self.assertEqual(parsed[0].id, "flow-visual")
        with self.assertRaises(FrozenInstanceError):
            parsed[0].caption = "変更"  # type: ignore[misc]

    def test_parameter_when_is_the_only_public_mapping_and_is_read_only(self) -> None:
        simulation = _scenario_simulation()

        visual = _parse([_visual("flow", _payloads()["flow"], simulation=simulation)])[0]

        when = visual.simulation.states[0].when  # type: ignore[union-attr]
        self.assertIsInstance(when, MappingProxyType)
        with self.assertRaises(TypeError):
            when["size"] = "large"  # type: ignore[index]

    def test_scenario_uses_partitioned_states_without_authored_transitions(self) -> None:
        valid = _scenario_simulation()
        parsed = _parse([
            _visual("flow", deepcopy(_payloads()["flow"]), simulation=valid)
        ])[0]
        self.assertEqual(parsed.simulation.transitions, ())  # type: ignore[union-attr]

        invalid = deepcopy(valid)
        invalid["transitions"] = [{
            "id": "implicit-apply",
            "from": "small-state",
            "to": "large-state",
            "event": "parameter-change",
            "when": {"size": "large"},
        }]
        with self.assertRaises(CurriculumValidationError):
            _parse([
                _visual("flow", deepcopy(_payloads()["flow"]), simulation=invalid)
            ])

    def test_complete_lessons_require_one_or_two_visuals(self) -> None:
        for value in (None, [], [_visual("flow", _payloads()["flow"])] * 3):
            with self.subTest(value=value):
                with self.assertRaises(CurriculumValidationError):
                    _parse(value)

        self.assertEqual(_parse(None, complete=False), ())

    def test_rejects_unknown_cross_type_and_raw_presentation_fields(self) -> None:
        mutations = (
            ("common", lambda value: value.__setitem__("style", "color:red")),
            ("cross-type", lambda value: value["payload"].__setitem__("connections", [])),  # type: ignore[union-attr]
            ("child-html", lambda value: value["payload"]["steps"][0].__setitem__("html", "<b>x</b>")),  # type: ignore[index,union-attr]
        )
        for name, mutate in mutations:
            with self.subTest(name=name):
                value = _visual("flow", deepcopy(_payloads()["flow"]))
                mutate(value)
                with self.assertRaises(CurriculumValidationError):
                    _parse([value])

    def test_rejects_invalid_ascii_ids_and_duplicate_ids_in_every_scope(self) -> None:
        cases: list[dict[str, object]] = []
        invalid = _visual("flow", deepcopy(_payloads()["flow"]), id="Upper")
        cases.append(invalid)
        duplicate_nodes = _visual("flow", deepcopy(_payloads()["flow"]))
        duplicate_nodes["payload"]["steps"][1]["id"] = "start"  # type: ignore[index]
        cases.append(duplicate_nodes)
        duplicate_edges = _visual("flow", deepcopy(_payloads()["flow"]))
        duplicate_edges["payload"]["transitions"].append(deepcopy(duplicate_edges["payload"]["transitions"][0]))  # type: ignore[index,union-attr]
        cases.append(duplicate_edges)
        duplicate_visuals = [_visual("flow", deepcopy(_payloads()["flow"]))] * 2

        for value in cases:
            with self.subTest(value=value.get("id")):
                with self.assertRaises(CurriculumValidationError):
                    _parse([value])
        with self.assertRaises(CurriculumValidationError):
            _parse(duplicate_visuals)

    def test_rejects_dangling_traceability_and_payload_references(self) -> None:
        cases = (
            _visual("flow", deepcopy(_payloads()["flow"]), objectiveIds=["obj-missing"]),
            _visual("flow", deepcopy(_payloads()["flow"]), evidenceIds=["missing"]),
            _visual("flow", deepcopy(_payloads()["flow"]), sourceIds=["missing"]),
        )
        dangling_edge = _visual("flow", deepcopy(_payloads()["flow"]))
        dangling_edge["payload"]["transitions"][0]["to"] = "missing"  # type: ignore[index]

        for value in (*cases, dangling_edge):
            with self.subTest(value=value):
                with self.assertRaises(CurriculumValidationError):
                    _parse([value])

    def test_rejects_disconnected_required_nodes_across_graph_payloads(self) -> None:
        flow = _visual("flow", deepcopy(_payloads()["flow"]))
        flow["payload"]["steps"].append(_item("orphan"))  # type: ignore[index,union-attr]
        hierarchy = _visual("hierarchy", deepcopy(_payloads()["hierarchy"]))
        hierarchy["payload"]["nodes"].append({**_item("orphan"), "parentId": "orphan"})  # type: ignore[index,union-attr]
        network = _visual("network", deepcopy(_payloads()["network"]))
        network["payload"]["nodes"].append({**_item("orphan"), "componentId": "path"})  # type: ignore[index,union-attr]
        causal = _visual("causal", deepcopy(_payloads()["causal"]))
        causal["payload"]["mitigations"].append(_item("unused"))  # type: ignore[index,union-attr]

        for value in (flow, hierarchy, network, causal):
            with self.subTest(kind=value["type"]):
                with self.assertRaises(CurriculumValidationError):
                    _parse([value])

    def test_rejects_forbidden_cycles_and_requires_declared_feedback_cycle(self) -> None:
        flow = _visual("flow", deepcopy(_payloads()["flow"]))
        flow["payload"]["transitions"].append({"id": "back", "from": "finish", "to": "start", "label": "戻る"})  # type: ignore[index,union-attr]
        memory = _visual("memory", deepcopy(_payloads()["memory"]))
        memory["payload"]["transfers"].append({"id": "back", "from": "cache", "to": "cpu", "label": "戻る", "kind": "response"})  # type: ignore[index,union-attr]
        state_loop = _visual("state-loop", deepcopy(_payloads()["state-loop"]))
        state_loop["payload"]["transitions"] = [state_loop["payload"]["transitions"][0], state_loop["payload"]["transitions"][2]]  # type: ignore[index]

        for value in (flow, memory, state_loop):
            with self.subTest(kind=value["type"]):
                with self.assertRaises(CurriculumValidationError):
                    _parse([value])

    def test_rejects_incomplete_or_duplicate_comparison_and_matrix_cells(self) -> None:
        for kind in ("comparison", "matrix"):
            with self.subTest(kind=kind, mutation="missing"):
                payload = deepcopy(_payloads()[kind])
                payload["cells"].pop()
                with self.assertRaises(CurriculumValidationError):
                    _parse([_visual(kind, payload)])
            with self.subTest(kind=kind, mutation="duplicate-coordinate"):
                payload = deepcopy(_payloads()[kind])
                duplicate = deepcopy(payload["cells"][0])
                duplicate["id"] = "duplicate-cell"
                payload["cells"].append(duplicate)
                with self.assertRaises(CurriculumValidationError):
                    _parse([_visual(kind, payload)])

    def test_rejects_multiple_hierarchy_parent_encodings(self) -> None:
        value = _visual("hierarchy", deepcopy(_payloads()["hierarchy"]))
        value["payload"]["nodes"][1]["parentIds"] = ["root", "other"]  # type: ignore[index]

        with self.assertRaises(CurriculumValidationError):
            _parse([value])

    def test_rejects_ambiguous_transitions_and_overlapping_when_mappings(self) -> None:
        simulation = _scenario_simulation()
        simulation["interactionMode"] = "hybrid"
        simulation["defaultIntervalMs"] = 250
        simulation["transitions"] = [
            {"id": "first", "from": "small-state", "to": "large-state", "event": "next", "when": {"size": "small"}},
            {"id": "second", "from": "small-state", "to": "small-state", "event": "next"},
        ]

        with self.assertRaises(CurriculumValidationError):
            _parse([_visual("flow", deepcopy(_payloads()["flow"]), simulation=simulation)])

    def test_hybrid_and_explorer_require_executable_paths_for_every_selection(self) -> None:
        for mode in ("hybrid", "explorer"):
            invalid_initial = _scenario_simulation()
            invalid_initial["interactionMode"] = mode
            if mode == "hybrid":
                invalid_initial["defaultIntervalMs"] = 250
            invalid_initial["transitions"] = [
                {
                    "id": "small-only-edge",
                    "from": "small-state",
                    "to": "large-state",
                    "event": "next",
                    "when": {"size": "small"},
                }
            ]

            invalid_edge = deepcopy(invalid_initial)
            invalid_edge["states"][0]["when"] = {}  # type: ignore[index]

            for mutation, simulation in (
                ("initial", invalid_initial),
                ("edge", invalid_edge),
            ):
                with self.subTest(mode=mode, mutation=mutation):
                    with self.assertRaises(CurriculumValidationError):
                        _parse([
                            _visual(
                                "flow",
                                deepcopy(_payloads()["flow"]),
                                simulation=simulation,
                            )
                        ])

    def test_maximum_parameter_domain_is_validated_through_the_public_api(self) -> None:
        parameters = [
            {
                "id": f"parameter-{index}",
                "label": f"条件{index}",
                "control": "select",
                "options": [
                    {"id": "zero", "label": "0"},
                    {"id": "one", "label": "1"},
                ],
                "defaultOptionId": "zero",
            }
            for index in range(6)
        ]
        states: list[dict[str, object]] = [
            {
                "id": "initial",
                "label": "初期",
                "status": "開始",
                "activeNodeIds": ["start"],
                "activeEdgeIds": [],
            }
        ]
        transitions: list[dict[str, object]] = []
        for number in range(1, 64):
            bits = f"{number:06b}"
            suffix = bits.replace("0", "z").replace("1", "o")
            conditions = {
                f"parameter-{index}": "one" if bit == "1" else "zero"
                for index, bit in enumerate(bits)
            }
            state_id = f"state-{suffix}"
            states.append(
                {
                    "id": state_id,
                    "label": suffix,
                    "status": "分岐",
                    "when": conditions,
                    "activeNodeIds": ["finish"],
                    "activeEdgeIds": ["advance"],
                }
            )
            transitions.append(
                {
                    "id": f"edge-{suffix}",
                    "from": "initial",
                    "to": state_id,
                    "event": "next",
                    "when": conditions,
                }
            )
        simulation = {
            "kind": "complexity-growth",
            "interactionMode": "hybrid",
            "parameters": parameters,
            "initialStateId": "initial",
            "defaultIntervalMs": 250,
            "states": states,
            "transitions": transitions,
            "outcomes": [
                {"id": "observed", "stateId": "initial", "label": "観測"}
            ],
        }

        parsed = _parse([
            _visual(
                "flow",
                deepcopy(_payloads()["flow"]),
                simulation=simulation,
            )
        ])

        self.assertEqual(len(parsed[0].simulation.states), 64)  # type: ignore[union-attr]
        self.assertEqual(len(parsed[0].simulation.transitions), 63)  # type: ignore[union-attr]
        overflow = deepcopy(simulation)
        overflow["parameters"].append(  # type: ignore[union-attr]
            {
                "id": "parameter-6",
                "label": "条件6",
                "control": "select",
                "options": [
                    {"id": "zero", "label": "0"},
                    {"id": "one", "label": "1"},
                ],
                "defaultOptionId": "zero",
            }
        )
        with self.assertRaises(CurriculumValidationError):
            _parse([
                _visual(
                    "flow",
                    deepcopy(_payloads()["flow"]),
                    simulation=overflow,
                )
            ])

    def test_interval_closed_bounds_and_multiple_of_fifty(self) -> None:
        for interval, accepted in ((249, False), (250, True), (251, False), (5000, True), (5001, False)):
            with self.subTest(interval=interval):
                simulation = _scenario_simulation()
                simulation["interactionMode"] = "playback"
                simulation["defaultIntervalMs"] = interval
                simulation["transitions"] = [
                    {"id": "advance-state", "from": "small-state", "to": "large-state", "event": "next"}
                ]
                if accepted:
                    self.assertIsNotNone(_parse([_visual("flow", deepcopy(_payloads()["flow"]), simulation=simulation)])[0].simulation)
                else:
                    with self.assertRaises(CurriculumValidationError):
                        _parse([_visual("flow", deepcopy(_payloads()["flow"]), simulation=simulation)])

    def test_enforces_count_text_and_unicode_scalar_limits(self) -> None:
        mutations = []
        too_many_steps = _visual("flow", deepcopy(_payloads()["flow"]))
        too_many_steps["payload"]["steps"] = [_item(f"node-{index}") for index in range(65)]  # type: ignore[index]
        mutations.append(too_many_steps)
        too_many_notes = _visual("flow", deepcopy(_payloads()["flow"]), notes=["注記"] * 9)
        mutations.append(too_many_notes)
        long_caption = _visual("flow", deepcopy(_payloads()["flow"]), caption="あ" * 161)
        mutations.append(long_caption)
        long_observation = _visual("flow", deepcopy(_payloads()["flow"]), expectedObservation="あ" * 301)
        mutations.append(long_observation)
        long_note = _visual("flow", deepcopy(_payloads()["flow"]), notes=["あ" * 601])
        mutations.append(long_note)
        bidi = _visual("flow", deepcopy(_payloads()["flow"]), caption="安全\u202e危険")
        mutations.append(bidi)
        surrogate = _visual("flow", deepcopy(_payloads()["flow"]), question="不正\ud800")
        mutations.append(surrogate)
        noncharacter = _visual("flow", deepcopy(_payloads()["flow"]), question="不正\ufdd0")
        mutations.append(noncharacter)

        for index, value in enumerate(mutations):
            with self.subTest(index=index):
                with self.assertRaises(CurriculumValidationError):
                    _parse([value])

        boundary = _visual(
            "flow", deepcopy(_payloads()["flow"]), caption="あ" * 160,
            question="い" * 160, expectedObservation="う" * 300,
            notes=["え" * 600] * 8,
        )
        self.assertEqual(len(_parse([boundary])[0].caption), 160)
        scalar_boundary = _visual(
            "flow", deepcopy(_payloads()["flow"]), caption="😀" * 160,
        )
        self.assertEqual(len(_parse([scalar_boundary])[0].caption), 160)

    def test_evidence_may_be_reachable_from_the_union_of_referenced_objectives(self) -> None:
        value = _visual(
            "flow", deepcopy(_payloads()["flow"]),
            objectiveIds=["obj-path", "obj-cost"], evidenceIds=["trace", "report"],
        )

        parsed = parse_visualizations(
            [value], lesson_id="core-01-example", complete=True,
            objective_evidence={
                "obj-path": frozenset({"trace"}),
                "obj-cost": frozenset({"report"}),
            },
            evidence_ids=frozenset({"trace", "report"}),
            source_ids=frozenset({"source-one"}),
        )

        self.assertEqual(parsed[0].evidence_ids, ("trace", "report"))

    def test_rejects_null_interval_when_the_field_is_forbidden(self) -> None:
        simulation = _scenario_simulation()
        simulation["defaultIntervalMs"] = None

        with self.assertRaises(CurriculumValidationError):
            _parse([_visual("flow", deepcopy(_payloads()["flow"]), simulation=simulation)])

    def test_rejects_structural_id_collisions_across_payload_collections(self) -> None:
        cases = []
        comparison = deepcopy(_payloads()["comparison"])
        comparison["criteria"][0]["id"] = "left"  # type: ignore[index]
        cases.append(_visual("comparison", comparison))
        timeline = deepcopy(_payloads()["timeline"])
        timeline["events"][0]["id"] = "expand"  # type: ignore[index]
        cases.append(_visual("timeline", timeline))
        network = deepcopy(_payloads()["network"])
        network["components"][0]["id"] = "client"  # type: ignore[index]
        network["nodes"][0]["componentId"] = "client"  # type: ignore[index]
        network["nodes"][1]["componentId"] = "client"  # type: ignore[index]
        cases.append(_visual("network", network))
        matrix = deepcopy(_payloads()["matrix"])
        matrix["columns"][0]["id"] = "fast"  # type: ignore[index]
        cases.append(_visual("matrix", matrix))

        for value in cases:
            with self.subTest(kind=value["type"]):
                with self.assertRaises(CurriculumValidationError):
                    _parse([value])

    def test_rejects_unknown_simulation_kind_and_empty_present_array(self) -> None:
        simulation = _scenario_simulation()
        simulation["kind"] = "invented-simulation"

        with self.assertRaises(CurriculumValidationError):
            _parse([_visual("flow", deepcopy(_payloads()["flow"]), simulation=simulation)])
        with self.assertRaises(CurriculumValidationError):
            _parse([], complete=False)

    def test_rejects_more_than_one_simulation_per_lesson_without_echoing_content(self) -> None:
        secret = "private-second-caption"
        first = _visual(
            "flow",
            deepcopy(_payloads()["flow"]),
            id="first-visual",
            simulation=_scenario_simulation(),
        )
        second = _visual(
            "flow",
            deepcopy(_payloads()["flow"]),
            id="second-visual",
            caption=secret,
            simulation=_scenario_simulation(),
        )

        with self.assertRaises(CurriculumValidationError) as raised:
            _parse([first, second])

        diagnostic = str(raised.exception)
        self.assertIn("core-01-example", diagnostic)
        self.assertIn("at most one simulation", diagnostic)
        self.assertNotIn(secret, diagnostic)

    def test_diagnostics_do_not_echo_unknown_author_values(self) -> None:
        secret_marker = "attacker-secret-marker"
        value = _visual("flow", deepcopy(_payloads()["flow"]))
        value[secret_marker] = "https://attacker.invalid/secret"

        with self.assertRaises(CurriculumValidationError) as raised:
            _parse([value])

        self.assertNotIn(secret_marker, str(raised.exception))
        self.assertNotIn("attacker.invalid", str(raised.exception))

    def test_diagnostics_identify_validated_lesson_visual_and_field(self) -> None:
        malicious_target = "private-attacker-value"
        value = _visual("flow", deepcopy(_payloads()["flow"]), id="request-path")
        value["payload"]["transitions"][0]["to"] = malicious_target  # type: ignore[index]

        with self.assertRaises(CurriculumValidationError) as raised:
            parse_visualizations(
                [value],
                lesson_id="core-05-network",
                complete=True,
                objective_evidence={"obj-path": frozenset({"trace"})},
                evidence_ids=frozenset({"trace"}),
                source_ids=frozenset({"source-one"}),
            )

        diagnostic = str(raised.exception)
        self.assertIn("core-05-network", diagnostic)
        self.assertIn("request-path", diagnostic)
        self.assertIn("payload.transitions[0]", diagnostic)
        self.assertNotIn(malicious_target, diagnostic)

    def test_network_components_cannot_be_joined_through_another_component(self) -> None:
        payload = deepcopy(_payloads()["network"])
        payload["components"].append(_item("other"))
        payload["nodes"].append({**_item("peer"), "componentId": "other"})
        payload["connections"].append(
            {"id": "cross-component", "from": "server", "to": "peer", "label": "越境"}
        )

        with self.assertRaises(CurriculumValidationError):
            _parse([_visual("network", payload)])


if __name__ == "__main__":
    unittest.main()
