"""Strict immutable models for bounded lesson visualizations."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from html import escape
import hashlib
from itertools import product
import re
from types import MappingProxyType
from typing import TypeVar
import unicodedata

from .catalog import strict_json_loads
from .errors import CurriculumValidationError
from .html_safety import (
    SafeHtml,
    validate_fragment,
    validate_generated_fragment,
)


_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_CORE_LESSON_ID = re.compile(
    r"core-(0[1-9]|[12][0-9]|30)-[a-z0-9]+(?:-[a-z0-9]+)*\Z",
    re.ASCII,
)
_SIMULATION_EVENTS = frozenset({"next", "previous", "timer", "parameter-change", "reset"})
_DOM_NAMESPACE_PREFIX = b"visualization-dom-v1\0"
_DOM_NAMESPACE_DIGEST_HEX_CHARS = 20
MAX_VISUALIZATION_CATALOG_BYTES = 64 * 1024
_CatalogEnum = TypeVar("_CatalogEnum", bound=StrEnum)


class VisualizationType(StrEnum):
    FLOW = "flow"
    HIERARCHY = "hierarchy"
    COMPARISON = "comparison"
    STATE_LOOP = "state-loop"
    CAUSAL = "causal"
    TIMELINE = "timeline"
    NETWORK = "network"
    MEMORY = "memory"
    MATRIX = "matrix"
    STATE_MACHINE = "state-machine"


class LessonSectionRole(StrEnum):
    WHY = "why"
    MENTAL_MODEL = "mentalModel"
    WORKED_EXAMPLE = "workedExample"
    TRADEOFFS = "tradeoffs"
    KNOWLEDGE_CHECK = "knowledgeCheck"
    SOURCES_NEXT = "sourcesNext"


class InteractionMode(StrEnum):
    SCENARIO = "scenario"
    STEPPER = "stepper"
    PLAYBACK = "playback"
    HYBRID = "hybrid"
    EXPLORER = "explorer"


class SimulationKind(StrEnum):
    COMPLEXITY_GROWTH = "complexity-growth"
    MEMORY_ACCESS = "memory-access"
    SCHEDULER_INTERLEAVING = "scheduler-interleaving"
    REQUEST_PATH = "request-path"
    RETRY_CONTRACT = "retry-contract"
    ISOLATION_SCHEDULE = "isolation-schedule"
    DISTRIBUTED_FAILURE = "distributed-failure"
    QUEUE_CAPACITY = "queue-capacity"
    SLO_BURN = "slo-burn"
    ACCESSIBLE_UI_STATE = "accessible-ui-state"
    MIGRATION_PHASE = "migration-phase"
    RELEASE_SAFETY = "release-safety"


@dataclass(frozen=True, slots=True)
class Item:
    id: str
    label: str
    detail: str


@dataclass(frozen=True, slots=True)
class HierarchyNode:
    id: str
    label: str
    detail: str
    parent_id: str | None


@dataclass(frozen=True, slots=True)
class NetworkNode:
    id: str
    label: str
    detail: str
    component_id: str


@dataclass(frozen=True, slots=True)
class MemoryLayer:
    id: str
    label: str
    detail: str
    group: str


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    id: str
    label: str
    detail: str
    phase_id: str
    order: int
    lane: str | None


@dataclass(frozen=True, slots=True)
class Relationship:
    id: str
    from_id: str
    to_id: str
    label: str
    kind: str | None = None


@dataclass(frozen=True, slots=True)
class ComparisonCell:
    id: str
    alternative_id: str
    criterion_id: str
    value: str


@dataclass(frozen=True, slots=True)
class MatrixCell:
    id: str
    row_id: str
    column_id: str
    value: str
    status: str


@dataclass(frozen=True, slots=True)
class StateMachineTransition:
    id: str
    from_id: str
    to_id: str
    event: str
    status: str
    reason: str | None


@dataclass(frozen=True, slots=True)
class FlowPayload:
    steps: tuple[Item, ...]
    transitions: tuple[Relationship, ...]


@dataclass(frozen=True, slots=True)
class HierarchyPayload:
    nodes: tuple[HierarchyNode, ...]


@dataclass(frozen=True, slots=True)
class ComparisonPayload:
    alternatives: tuple[Item, ...]
    criteria: tuple[Item, ...]
    cells: tuple[ComparisonCell, ...]


@dataclass(frozen=True, slots=True)
class StateLoopPayload:
    states: tuple[Item, ...]
    transitions: tuple[Relationship, ...]
    exit_state_id: str
    recovery_state_id: str


@dataclass(frozen=True, slots=True)
class CausalPayload:
    causes: tuple[Item, ...]
    mechanisms: tuple[Item, ...]
    outcomes: tuple[Item, ...]
    mitigations: tuple[Item, ...]
    relations: tuple[Relationship, ...]


@dataclass(frozen=True, slots=True)
class TimelinePayload:
    phases: tuple[Item, ...]
    events: tuple[TimelineEvent, ...]


@dataclass(frozen=True, slots=True)
class NetworkPayload:
    nodes: tuple[NetworkNode, ...]
    components: tuple[Item, ...]
    connections: tuple[Relationship, ...]


@dataclass(frozen=True, slots=True)
class MemoryPayload:
    layers: tuple[MemoryLayer, ...]
    transfers: tuple[Relationship, ...]


@dataclass(frozen=True, slots=True)
class MatrixPayload:
    rows: tuple[Item, ...]
    columns: tuple[Item, ...]
    cells: tuple[MatrixCell, ...]


@dataclass(frozen=True, slots=True)
class StateMachinePayload:
    states: tuple[Item, ...]
    initial_state_id: str
    transitions: tuple[StateMachineTransition, ...]


VisualizationPayload = (
    FlowPayload | HierarchyPayload | ComparisonPayload | StateLoopPayload
    | CausalPayload | TimelinePayload | NetworkPayload | MemoryPayload
    | MatrixPayload | StateMachinePayload
)


@dataclass(frozen=True, slots=True)
class ParameterOption:
    id: str
    label: str


@dataclass(frozen=True, slots=True)
class SimulationParameter:
    id: str
    label: str
    control: str
    options: tuple[ParameterOption, ...]
    default_option_id: str


@dataclass(frozen=True, slots=True)
class SimulationState:
    id: str
    label: str
    status: str
    when: Mapping[str, str]
    active_node_ids: tuple[str, ...]
    active_edge_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "when", MappingProxyType(dict(self.when)))


@dataclass(frozen=True, slots=True)
class SimulationTransition:
    id: str
    from_id: str
    to_id: str
    event: str
    when: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "when", MappingProxyType(dict(self.when)))


@dataclass(frozen=True, slots=True)
class SimulationOutcome:
    id: str
    state_id: str
    label: str


@dataclass(frozen=True, slots=True)
class Simulation:
    kind: SimulationKind
    interaction_mode: InteractionMode
    parameters: tuple[SimulationParameter, ...]
    initial_state_id: str
    states: tuple[SimulationState, ...]
    transitions: tuple[SimulationTransition, ...]
    outcomes: tuple[SimulationOutcome, ...]
    default_interval_ms: int | None


@dataclass(frozen=True, slots=True)
class Visualization:
    id: str
    type: VisualizationType
    caption: str
    question: str
    after_section: LessonSectionRole
    objective_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    expected_observation: str
    payload: VisualizationPayload
    notes: tuple[str, ...]
    simulation: Simulation | None


@dataclass(frozen=True, slots=True)
class CatalogSimulation:
    kind: SimulationKind
    interaction_mode: InteractionMode
    static_equivalent_id: str
    visual_regression_state_ids: tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class VisualizationAssignment:
    lesson_id: str
    primary_type: VisualizationType
    optional_secondary_type: VisualizationType
    dynamic: bool
    simulation: CatalogSimulation | None


@dataclass(frozen=True, slots=True)
class VisualizationCatalog:
    version: int
    lessons: tuple[VisualizationAssignment, ...]


def _fail(path: str, reason: str) -> None:
    # Diagnostics name the schema location but never echo an authored value: this
    # keeps hostile strings and large inputs out of bounded CI output.
    raise CurriculumValidationError(f"{path}: {reason}")


def _mapping(value: object, path: str) -> dict[str, object]:
    if type(value) is not dict:
        _fail(path, "must be an exact object")
    assert isinstance(value, dict)
    if any(type(key) is not str for key in value):
        _fail(path, "field names must be strings")
    return value


def _fields(raw: dict[str, object], *, required: set[str], optional: set[str], path: str) -> None:
    unknown = sorted(set(raw) - required - optional)
    if unknown:
        _fail(path, "contains unknown fields")
    missing = sorted(required - set(raw))
    if missing:
        _fail(path, f"missing fields: {', '.join(missing[:8])}")


def _sequence(value: object, path: str, low: int, high: int) -> list[object]:
    if type(value) is not list:
        _fail(path, "must be an exact array")
    assert isinstance(value, list)
    if not low <= len(value) <= high:
        _fail(path, f"item count must be {low}..{high}")
    return value


def _text(value: object, path: str, high: int, *, low: int = 1) -> str:
    if type(value) is not str:
        _fail(path, "must be a string")
    assert isinstance(value, str)
    if value != value.strip() or not low <= len(value) <= high:
        _fail(path, f"text length must be {low}..{high}")
    if any(_is_forbidden_unicode(char) for char in value):
        _fail(path, "contains forbidden Unicode")
    return value


def _is_forbidden_unicode(character: str) -> bool:
    codepoint = ord(character)
    return (
        unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
        or 0xFDD0 <= codepoint <= 0xFDEF
        or codepoint & 0xFFFF in {0xFFFE, 0xFFFF}
    )


def _id(value: object, path: str) -> str:
    result = _text(value, path, 64)
    if _ID.fullmatch(result) is None:
        _fail(path, "must be an ASCII identifier")
    return result


def _ids(value: object, path: str, low: int, high: int) -> tuple[str, ...]:
    result = tuple(
        _id(item, f"{path}[{index}]")
        for index, item in enumerate(_sequence(value, path, low, high))
    )
    if len(set(result)) != len(result):
        _fail(path, "must not contain duplicate IDs")
    return result


def _enum(value: object, allowed: frozenset[str], path: str) -> str:
    result = _text(value, path, 64)
    if result not in allowed:
        _fail(path, "is outside the closed enum")
    return result


def _unique(records: tuple[object, ...], path: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for record in records:
        identifier = getattr(record, "id")
        if identifier in result:
            _fail(path, "contains duplicate IDs")
        result[identifier] = record
    return result


def _item_record(value: object, path: str) -> Item:
    raw = _mapping(value, path)
    _fields(raw, required={"id", "label", "detail"}, optional=set(), path=path)
    return Item(
        _id(raw["id"], f"{path}.id"),
        _text(raw["label"], f"{path}.label", 160),
        _text(raw["detail"], f"{path}.detail", 600),
    )


def _items(value: object, path: str, low: int = 1, high: int = 64) -> tuple[Item, ...]:
    result = tuple(
        _item_record(item, f"{path}[{index}]")
        for index, item in enumerate(_sequence(value, path, low, high))
    )
    _unique(result, path)
    return result


def _relationship(value: object, path: str, *, kind: bool = False) -> Relationship:
    raw = _mapping(value, path)
    required = {"id", "from", "to", "label"} | ({"kind"} if kind else set())
    _fields(raw, required=required, optional=set(), path=path)
    return Relationship(
        _id(raw["id"], f"{path}.id"), _id(raw["from"], f"{path}.from"),
        _id(raw["to"], f"{path}.to"), _text(raw["label"], f"{path}.label", 160),
        _id(raw["kind"], f"{path}.kind") if kind else None,
    )


def _relationships(
    value: object,
    path: str,
    *,
    low: int = 0,
    kind: bool = False,
) -> tuple[Relationship, ...]:
    result = tuple(
        _relationship(item, f"{path}[{index}]", kind=kind)
        for index, item in enumerate(_sequence(value, path, low, 128))
    )
    _unique(result, path)
    return result


def _check_refs(edges: tuple[Relationship, ...], nodes: set[str], path: str) -> None:
    for index, edge in enumerate(edges):
        if edge.from_id not in nodes or edge.to_id not in nodes:
            _fail(f"{path}[{index}]", "has a dangling endpoint")


def _adjacency(
    nodes: set[str],
    edges: tuple[Relationship, ...],
    *,
    undirected: bool = False,
) -> dict[str, list[str]]:
    adjacent = {node: [] for node in nodes}
    for edge in edges:
        adjacent[edge.from_id].append(edge.to_id)
        if undirected:
            adjacent[edge.to_id].append(edge.from_id)
    return adjacent


def _reachable(start: str, adjacent: Mapping[str, list[str]]) -> set[str]:
    # Every queue entry is a validated node and every edge is scanned at most
    # once, so traversal is bounded by the schema limits and remains O(V + E).
    seen: set[str] = set()
    queue = deque([start])
    while queue:
        node = queue.popleft()
        if node in seen:
            continue
        seen.add(node)
        queue.extend(adjacent[node])
    return seen


def _reachable_from(starts: set[str], adjacent: Mapping[str, list[str]]) -> set[str]:
    seen: set[str] = set()
    queue = deque(starts)
    while queue:
        node = queue.popleft()
        if node in seen:
            continue
        seen.add(node)
        queue.extend(adjacent[node])
    return seen


def _has_cycle(nodes: set[str], adjacent: Mapping[str, list[str]]) -> bool:
    indegree = {node: 0 for node in nodes}
    for targets in adjacent.values():
        for target in targets:
            indegree[target] += 1
    queue = deque(node for node, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for target in adjacent[node]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    return visited != len(nodes)


def _parse_flow_payload(raw: dict[str, object], path: str) -> FlowPayload:
    _fields(raw, required={"steps", "transitions"}, optional=set(), path=path)
    steps = _items(raw["steps"], f"{path}.steps")
    transitions = _relationships(raw["transitions"], f"{path}.transitions")
    nodes = set(_unique(steps, f"{path}.steps"))
    _check_refs(transitions, nodes, f"{path}.transitions")
    indegree = {node: 0 for node in nodes}
    for edge in transitions:
        indegree[edge.to_id] += 1
    starts = [node for node, degree in indegree.items() if degree == 0]
    adjacent = _adjacency(nodes, transitions)
    if len(starts) != 1 or _reachable(starts[0], adjacent) != nodes:
        _fail(path, "flow must have one connected start")
    if _has_cycle(nodes, adjacent):
        _fail(path, "flow must be acyclic")
    order = {step.id: index for index, step in enumerate(steps)}
    if any(order[edge.from_id] >= order[edge.to_id] for edge in transitions):
        _fail(path, "flow transitions must reach a later step")
    return FlowPayload(steps, transitions)


def _parse_hierarchy_node(value: object, path: str) -> HierarchyNode:
    raw = _mapping(value, path)
    _fields(
        raw,
        required={"id", "label", "detail", "parentId"},
        optional=set(),
        path=path,
    )
    parent = raw["parentId"]
    return HierarchyNode(
        _id(raw["id"], f"{path}.id"),
        _text(raw["label"], f"{path}.label", 160),
        _text(raw["detail"], f"{path}.detail", 600),
        None if parent is None else _id(parent, f"{path}.parentId"),
    )


def _parse_hierarchy_payload(
    raw: dict[str, object], path: str
) -> HierarchyPayload:
    _fields(raw, required={"nodes"}, optional=set(), path=path)
    nodes = tuple(
        _parse_hierarchy_node(value, f"{path}.nodes[{index}]")
        for index, value in enumerate(
            _sequence(raw["nodes"], f"{path}.nodes", 1, 64)
        )
    )
    known = set(_unique(nodes, f"{path}.nodes"))
    roots = [node.id for node in nodes if node.parent_id is None]
    if len(roots) != 1:
        _fail(path, "hierarchy must have one root")
    edges = tuple(
        Relationship(node.id, node.parent_id, node.id, "")
        for node in nodes
        if node.parent_id is not None
    )
    _check_refs(edges, known, f"{path}.nodes")
    adjacent = _adjacency(known, edges)
    if _has_cycle(known, adjacent) or _reachable(roots[0], adjacent) != known:
        _fail(path, "hierarchy must be connected and acyclic")
    return HierarchyPayload(nodes)


def _parse_comparison_cell(value: object, path: str) -> ComparisonCell:
    raw = _mapping(value, path)
    _fields(
        raw,
        required={"id", "alternativeId", "criterionId", "value"},
        optional=set(),
        path=path,
    )
    return ComparisonCell(
        _id(raw["id"], f"{path}.id"),
        _id(raw["alternativeId"], f"{path}.alternativeId"),
        _id(raw["criterionId"], f"{path}.criterionId"),
        _text(raw["value"], f"{path}.value", 160),
    )


def _parse_comparison_payload(
    raw: dict[str, object], path: str
) -> ComparisonPayload:
    _fields(
        raw,
        required={"alternatives", "criteria", "cells"},
        optional=set(),
        path=path,
    )
    alternatives = _items(raw["alternatives"], f"{path}.alternatives")
    criteria = _items(raw["criteria"], f"{path}.criteria")
    if len(alternatives) + len(criteria) > 64:
        _fail(path, "primary item count exceeds 64")
    _unique(alternatives + criteria, path)
    cells = tuple(
        _parse_comparison_cell(value, f"{path}.cells[{index}]")
        for index, value in enumerate(
            _sequence(raw["cells"], f"{path}.cells", 1, 128)
        )
    )
    _unique(cells, f"{path}.cells")
    expected = {
        (alternative.id, criterion.id)
        for alternative in alternatives
        for criterion in criteria
    }
    actual = {(cell.alternative_id, cell.criterion_id) for cell in cells}
    if actual != expected or len(actual) != len(cells):
        _fail(path, "comparison cells must form a complete Cartesian set")
    return ComparisonPayload(alternatives, criteria, cells)


def _parse_state_loop_payload(
    raw: dict[str, object], path: str
) -> StateLoopPayload:
    _fields(
        raw,
        required={"states", "transitions", "exitStateId", "recoveryStateId"},
        optional=set(),
        path=path,
    )
    states = _items(raw["states"], f"{path}.states")
    transitions = _relationships(
        raw["transitions"], f"{path}.transitions", low=1
    )
    known = set(_unique(states, f"{path}.states"))
    _check_refs(transitions, known, f"{path}.transitions")
    exit_id = _id(raw["exitStateId"], f"{path}.exitStateId")
    recovery_id = _id(raw["recoveryStateId"], f"{path}.recoveryStateId")
    if exit_id not in known or recovery_id not in known:
        _fail(path, "state-loop has a dangling state reference")
    adjacent = _adjacency(known, transitions)
    if not _has_cycle(known, adjacent):
        _fail(path, "state-loop requires a feedback cycle")
    if exit_id not in _reachable(recovery_id, adjacent):
        _fail(path, "state-loop requires a recovery path to exit")
    if _reachable(states[0].id, adjacent) != known:
        _fail(path, "state-loop states must be connected")
    return StateLoopPayload(states, transitions, exit_id, recovery_id)


def _parse_causal_payload(raw: dict[str, object], path: str) -> CausalPayload:
    _fields(
        raw,
        required={"causes", "mechanisms", "outcomes", "mitigations", "relations"},
        optional=set(),
        path=path,
    )
    causes = _items(raw["causes"], f"{path}.causes")
    mechanisms = _items(raw["mechanisms"], f"{path}.mechanisms")
    outcomes = _items(raw["outcomes"], f"{path}.outcomes")
    mitigations = _items(raw["mitigations"], f"{path}.mitigations")
    all_items = causes + mechanisms + outcomes + mitigations
    if len(all_items) > 64:
        _fail(path, "primary item count exceeds 64")
    known = set(_unique(all_items, path))
    relations = _relationships(raw["relations"], f"{path}.relations", low=1)
    _check_refs(relations, known, f"{path}.relations")
    adjacent = _adjacency(known, relations)
    if _has_cycle(known, adjacent):
        _fail(path, "causal relations must be acyclic")
    undirected = _adjacency(known, relations, undirected=True)
    if _reachable(causes[0].id, undirected) != known:
        _fail(path, "causal items must form one connected explanation")
    cause_reachable = _reachable_from({cause.id for cause in causes}, adjacent)
    reachable_mechanisms = {
        mechanism.id
        for mechanism in mechanisms
        if mechanism.id in cause_reachable
    }
    after_mechanism = _reachable_from(reachable_mechanisms, adjacent)
    if any(outcome.id not in after_mechanism for outcome in outcomes):
        _fail(path, "every outcome must trace through a mechanism to a cause")
    return CausalPayload(causes, mechanisms, outcomes, mitigations, relations)


def _parse_timeline_event(value: object, path: str) -> TimelineEvent:
    raw = _mapping(value, path)
    _fields(
        raw,
        required={"id", "label", "detail", "phaseId", "order"},
        optional={"lane"},
        path=path,
    )
    order = raw["order"]
    if type(order) is not int or not 0 <= order <= 127:
        _fail(f"{path}.order", "must be an integer from 0 through 127")
    lane = None if "lane" not in raw else _id(raw["lane"], f"{path}.lane")
    return TimelineEvent(
        _id(raw["id"], f"{path}.id"),
        _text(raw["label"], f"{path}.label", 160),
        _text(raw["detail"], f"{path}.detail", 600),
        _id(raw["phaseId"], f"{path}.phaseId"),
        order,
        lane,
    )


def _parse_timeline_payload(
    raw: dict[str, object], path: str
) -> TimelinePayload:
    _fields(raw, required={"phases", "events"}, optional=set(), path=path)
    phases = _items(raw["phases"], f"{path}.phases", high=8)
    phase_ids = set(_unique(phases, f"{path}.phases"))
    events = tuple(
        _parse_timeline_event(value, f"{path}.events[{index}]")
        for index, value in enumerate(
            _sequence(raw["events"], f"{path}.events", 1, 64)
        )
    )
    _unique(events, f"{path}.events")
    _unique(phases + events, path)
    if any(event.phase_id not in phase_ids for event in events):
        _fail(path, "timeline has a dangling phase")
    keys = [(event.order, event.lane) for event in events]
    if len(set(keys)) != len(keys):
        _fail(path, "timeline order must be total")
    if keys != sorted(keys, key=lambda key: (key[0], key[1] or "")):
        _fail(path, "timeline events must retain total authored order")
    phase_order = {phase.id: index for index, phase in enumerate(phases)}
    event_phase_order = [phase_order[event.phase_id] for event in events]
    if event_phase_order != sorted(event_phase_order):
        _fail(path, "timeline phase order must preserve total event order")
    return TimelinePayload(phases, events)


def _parse_network_node(value: object, path: str) -> NetworkNode:
    raw = _mapping(value, path)
    _fields(
        raw,
        required={"id", "label", "detail", "componentId"},
        optional=set(),
        path=path,
    )
    return NetworkNode(
        _id(raw["id"], f"{path}.id"),
        _text(raw["label"], f"{path}.label", 160),
        _text(raw["detail"], f"{path}.detail", 600),
        _id(raw["componentId"], f"{path}.componentId"),
    )


def _parse_network_payload(raw: dict[str, object], path: str) -> NetworkPayload:
    _fields(
        raw,
        required={"nodes", "components", "connections"},
        optional=set(),
        path=path,
    )
    components = _items(raw["components"], f"{path}.components", high=8)
    component_ids = set(_unique(components, f"{path}.components"))
    nodes = tuple(
        _parse_network_node(value, f"{path}.nodes[{index}]")
        for index, value in enumerate(
            _sequence(raw["nodes"], f"{path}.nodes", 1, 64)
        )
    )
    known = set(_unique(nodes, f"{path}.nodes"))
    connections = _relationships(raw["connections"], f"{path}.connections")
    _check_refs(connections, known, f"{path}.connections")
    _unique(components + nodes, path)
    if any(node.component_id not in component_ids for node in nodes):
        _fail(path, "network node has a dangling component")
    component_by_node = {node.id: node.component_id for node in nodes}
    if any(
        component_by_node[edge.from_id] != component_by_node[edge.to_id]
        for edge in connections
    ):
        _fail(path, "network connection crosses declared components")
    if _has_cycle(known, _adjacency(known, connections)):
        _fail(path, "network connections must be acyclic")
    undirected = _adjacency(known, connections, undirected=True)
    for component in component_ids:
        members = {node.id for node in nodes if node.component_id == component}
        if (
            not members
            or _reachable(next(iter(members)), undirected) & members != members
        ):
            _fail(path, "network component must be connected")
    return NetworkPayload(nodes, components, connections)


def _parse_memory_layer(value: object, path: str) -> MemoryLayer:
    raw = _mapping(value, path)
    _fields(
        raw,
        required={"id", "label", "detail", "group"},
        optional=set(),
        path=path,
    )
    return MemoryLayer(
        _id(raw["id"], f"{path}.id"),
        _text(raw["label"], f"{path}.label", 160),
        _text(raw["detail"], f"{path}.detail", 600),
        _id(raw["group"], f"{path}.group"),
    )


def _parse_memory_payload(raw: dict[str, object], path: str) -> MemoryPayload:
    _fields(raw, required={"layers", "transfers"}, optional=set(), path=path)
    layers = tuple(
        _parse_memory_layer(value, f"{path}.layers[{index}]")
        for index, value in enumerate(
            _sequence(raw["layers"], f"{path}.layers", 1, 64)
        )
    )
    known = set(_unique(layers, f"{path}.layers"))
    if len({layer.group for layer in layers}) > 8:
        _fail(path, "memory group count exceeds 8")
    transfers = _relationships(
        raw["transfers"], f"{path}.transfers", kind=True
    )
    _check_refs(transfers, known, f"{path}.transfers")
    adjacent = _adjacency(known, transfers)
    if _has_cycle(known, adjacent):
        _fail(path, "memory transfers must be acyclic")
    if _reachable(layers[0].id, adjacent) != known:
        _fail(path, "memory layers must be connected in order")
    order = {layer.id: index for index, layer in enumerate(layers)}
    if any(order[edge.from_id] >= order[edge.to_id] for edge in transfers):
        _fail(path, "memory transfer must follow layer order")
    return MemoryPayload(layers, transfers)


def _parse_matrix_cell(value: object, path: str) -> MatrixCell:
    raw = _mapping(value, path)
    _fields(
        raw,
        required={"id", "rowId", "columnId", "value", "status"},
        optional=set(),
        path=path,
    )
    return MatrixCell(
        _id(raw["id"], f"{path}.id"),
        _id(raw["rowId"], f"{path}.rowId"),
        _id(raw["columnId"], f"{path}.columnId"),
        _text(raw["value"], f"{path}.value", 160),
        _enum(
            raw["status"],
            frozenset({"value", "not-applicable"}),
            f"{path}.status",
        ),
    )


def _parse_matrix_payload(raw: dict[str, object], path: str) -> MatrixPayload:
    _fields(
        raw,
        required={"rows", "columns", "cells"},
        optional=set(),
        path=path,
    )
    rows = _items(raw["rows"], f"{path}.rows")
    columns = _items(raw["columns"], f"{path}.columns")
    if len(rows) + len(columns) > 64:
        _fail(path, "primary item count exceeds 64")
    _unique(rows + columns, path)
    cells = tuple(
        _parse_matrix_cell(value, f"{path}.cells[{index}]")
        for index, value in enumerate(
            _sequence(raw["cells"], f"{path}.cells", 1, 128)
        )
    )
    _unique(cells, f"{path}.cells")
    expected = {
        (row.id, column.id) for row in rows for column in columns
    }
    actual = {(cell.row_id, cell.column_id) for cell in cells}
    if actual != expected or len(actual) != len(cells):
        _fail(path, "matrix cells must form a complete Cartesian set")
    return MatrixPayload(rows, columns, cells)


def _parse_state_machine_transition(
    value: object, path: str
) -> StateMachineTransition:
    raw = _mapping(value, path)
    _fields(
        raw,
        required={"id", "from", "to", "event", "status"},
        optional={"reason"},
        path=path,
    )
    status = _enum(
        raw["status"], frozenset({"allowed", "rejected"}), f"{path}.status"
    )
    reason = (
        None
        if "reason" not in raw
        else _text(raw["reason"], f"{path}.reason", 600)
    )
    if (status == "rejected") != (reason is not None):
        _fail(path, "only rejected transitions require a reason")
    return StateMachineTransition(
        _id(raw["id"], f"{path}.id"),
        _id(raw["from"], f"{path}.from"),
        _id(raw["to"], f"{path}.to"),
        _enum(raw["event"], _SIMULATION_EVENTS, f"{path}.event"),
        status,
        reason,
    )


def _parse_state_machine_payload(
    raw: dict[str, object], path: str
) -> StateMachinePayload:
    _fields(
        raw,
        required={"states", "initialStateId", "transitions"},
        optional=set(),
        path=path,
    )
    states = _items(raw["states"], f"{path}.states")
    known = set(_unique(states, f"{path}.states"))
    initial = _id(raw["initialStateId"], f"{path}.initialStateId")
    if initial not in known:
        _fail(path, "state-machine initial state is dangling")
    transitions = tuple(
        _parse_state_machine_transition(
            value, f"{path}.transitions[{index}]"
        )
        for index, value in enumerate(
            _sequence(raw["transitions"], f"{path}.transitions", 0, 128)
        )
    )
    _unique(transitions, f"{path}.transitions")
    if any(
        edge.from_id not in known or edge.to_id not in known
        for edge in transitions
    ):
        _fail(path, "state-machine transition has a dangling endpoint")
    allowed = tuple(
        Relationship(edge.id, edge.from_id, edge.to_id, edge.event)
        for edge in transitions
        if edge.status == "allowed"
    )
    if _reachable(initial, _adjacency(known, allowed)) != known:
        _fail(path, "state-machine contains unreachable states")
    return StateMachinePayload(states, initial, transitions)


_PayloadParser = Callable[[dict[str, object], str], VisualizationPayload]
_PAYLOAD_PARSERS: Mapping[VisualizationType, _PayloadParser] = MappingProxyType(
    {
        VisualizationType.FLOW: _parse_flow_payload,
        VisualizationType.HIERARCHY: _parse_hierarchy_payload,
        VisualizationType.COMPARISON: _parse_comparison_payload,
        VisualizationType.STATE_LOOP: _parse_state_loop_payload,
        VisualizationType.CAUSAL: _parse_causal_payload,
        VisualizationType.TIMELINE: _parse_timeline_payload,
        VisualizationType.NETWORK: _parse_network_payload,
        VisualizationType.MEMORY: _parse_memory_payload,
        VisualizationType.MATRIX: _parse_matrix_payload,
        VisualizationType.STATE_MACHINE: _parse_state_machine_payload,
    }
)


def _parse_payload(
    kind: VisualizationType, value: object, path: str
) -> VisualizationPayload:
    raw = _mapping(value, path)
    return _PAYLOAD_PARSERS[kind](raw, path)


def _when(value: object | None, path: str, parameters: Mapping[str, set[str]]) -> Mapping[str, str]:
    if value is None: return MappingProxyType({})
    raw = _mapping(value, path)
    result: dict[str, str] = {}
    for key in sorted(raw):
        if key not in parameters: _fail(path, "references an unknown parameter")
        option = _id(raw[key], f"{path}.{key}")
        if option not in parameters[key]: _fail(path, "references an unknown option")
        result[key] = option
    return MappingProxyType(result)


def _matches(conditions: Mapping[str, str], selection: Mapping[str, str]) -> bool:
    return all(selection.get(key) == value for key, value in conditions.items())


def _index_simulation_transitions(
    transitions: tuple[SimulationTransition, ...],
) -> dict[tuple[str, str], tuple[SimulationTransition, ...]]:
    mutable: dict[tuple[str, str], list[SimulationTransition]] = {}
    for transition in transitions:
        key = (transition.from_id, transition.event)
        mutable.setdefault(key, []).append(transition)
    return {key: tuple(bucket) for key, bucket in mutable.items()}


def _validate_simulation_domain(
    *,
    path: str,
    mode: InteractionMode,
    selections: list[dict[str, str]],
    states: tuple[SimulationState, ...],
    initial_state_id: str,
    transitions: tuple[SimulationTransition, ...],
) -> None:
    transition_index = _index_simulation_transitions(transitions)
    conditional_path_mode = mode in {
        InteractionMode.HYBRID,
        InteractionMode.EXPLORER,
    }

    # The Cartesian domain is rejected above 64. Within that closed domain each
    # state and transition is inspected once per selection, and each active
    # graph is traversed once. Thus validation is linear in the bounded expanded
    # domain C * (V + E), and O(V + E) with the schema-fixed C <= 64.
    for selection in selections:
        applicable_state_ids = {
            state.id for state in states if _matches(state.when, selection)
        }
        if mode is InteractionMode.SCENARIO:
            if len(applicable_state_ids) != 1:
                _fail(path, "scenario states must partition parameter combinations")

        active_transitions: list[SimulationTransition] = []
        for bucket in transition_index.values():
            matches = [
                edge for edge in bucket if _matches(edge.when, selection)
            ]
            if len(matches) > 1:
                _fail(path, "simulation transitions are ambiguous")
            active_transitions.extend(matches)

        if not conditional_path_mode:
            continue
        if initial_state_id not in applicable_state_ids:
            _fail(path, "initial state is unavailable for a parameter selection")
        if any(
            edge.from_id not in applicable_state_ids
            or edge.to_id not in applicable_state_ids
            for edge in active_transitions
        ):
            _fail(path, "transition conditions do not imply endpoint conditions")

        adjacency = {state_id: [] for state_id in applicable_state_ids}
        for edge in active_transitions:
            adjacency[edge.from_id].append(edge.to_id)
        if _reachable(initial_state_id, adjacency) != applicable_state_ids:
            _fail(path, "parameter selection has an unreachable step path")


def _parse_parameter_option(value: object, path: str) -> ParameterOption:
    raw = _mapping(value, path)
    _fields(raw, required={"id", "label"}, optional=set(), path=path)
    return ParameterOption(
        _id(raw["id"], f"{path}.id"),
        _text(raw["label"], f"{path}.label", 160),
    )


def _parse_simulation_parameter(
    value: object, path: str
) -> SimulationParameter:
    raw = _mapping(value, path)
    _fields(
        raw,
        required={"id", "label", "control", "options", "defaultOptionId"},
        optional=set(),
        path=path,
    )
    options = tuple(
        _parse_parameter_option(option, f"{path}.options[{index}]")
        for index, option in enumerate(
            _sequence(raw["options"], f"{path}.options", 2, 12)
        )
    )
    option_ids = set(_unique(options, f"{path}.options"))
    default = _id(raw["defaultOptionId"], f"{path}.defaultOptionId")
    if default not in option_ids:
        _fail(path, "default option is dangling")
    return SimulationParameter(
        _id(raw["id"], f"{path}.id"),
        _text(raw["label"], f"{path}.label", 160),
        _enum(
            raw["control"], frozenset({"select", "radio"}), f"{path}.control"
        ),
        options,
        default,
    )


def _parse_simulation_parameters(
    value: object, path: str
) -> tuple[tuple[SimulationParameter, ...], dict[str, set[str]]]:
    parameters = tuple(
        _parse_simulation_parameter(parameter, f"{path}[{index}]")
        for index, parameter in enumerate(_sequence(value, path, 0, 8))
    )
    _unique(parameters, path)
    option_ids = {
        parameter.id: {option.id for option in parameter.options}
        for parameter in parameters
    }
    combinations = 1
    for options in option_ids.values():
        combinations *= len(options)
    if combinations > 64:
        _fail(path, "parameter Cartesian space exceeds 64")
    return parameters, option_ids


def _parse_simulation_state(
    value: object,
    path: str,
    parameter_options: Mapping[str, set[str]],
    node_ids: set[str],
    edge_ids: set[str],
) -> SimulationState:
    raw = _mapping(value, path)
    _fields(
        raw,
        required={"id", "label", "status", "activeNodeIds", "activeEdgeIds"},
        optional={"when"},
        path=path,
    )
    active_nodes = _ids(raw["activeNodeIds"], f"{path}.activeNodeIds", 0, 64)
    active_edges = _ids(raw["activeEdgeIds"], f"{path}.activeEdgeIds", 0, 128)
    if not set(active_nodes) <= node_ids or not set(active_edges) <= edge_ids:
        _fail(path, "active reference is dangling")
    return SimulationState(
        _id(raw["id"], f"{path}.id"),
        _text(raw["label"], f"{path}.label", 160),
        _text(raw["status"], f"{path}.status", 160),
        _when(raw.get("when"), f"{path}.when", parameter_options),
        active_nodes,
        active_edges,
    )


def _parse_simulation_transition(
    value: object,
    path: str,
    parameter_options: Mapping[str, set[str]],
) -> SimulationTransition:
    raw = _mapping(value, path)
    _fields(
        raw,
        required={"id", "from", "to", "event"},
        optional={"when"},
        path=path,
    )
    return SimulationTransition(
        _id(raw["id"], f"{path}.id"),
        _id(raw["from"], f"{path}.from"),
        _id(raw["to"], f"{path}.to"),
        _enum(raw["event"], _SIMULATION_EVENTS, f"{path}.event"),
        _when(raw.get("when"), f"{path}.when", parameter_options),
    )


def _parse_simulation_outcome(value: object, path: str) -> SimulationOutcome:
    raw = _mapping(value, path)
    _fields(
        raw,
        required={"id", "stateId", "label"},
        optional=set(),
        path=path,
    )
    return SimulationOutcome(
        _id(raw["id"], f"{path}.id"),
        _id(raw["stateId"], f"{path}.stateId"),
        _text(raw["label"], f"{path}.label", 160),
    )


def _parse_interval(
    raw: dict[str, object], path: str, mode: InteractionMode
) -> int | None:
    interval = raw.get("defaultIntervalMs")
    playback = mode in {InteractionMode.PLAYBACK, InteractionMode.HYBRID}
    if playback:
        if (
            type(interval) is not int
            or not 250 <= interval <= 5000
            or interval % 50
        ):
            _fail(
                f"{path}.defaultIntervalMs",
                "must be 250..5000 and a multiple of 50",
            )
        assert isinstance(interval, int)
        return interval
    if "defaultIntervalMs" in raw:
        _fail(path, "default interval is forbidden for this mode")
    return None


def _parameter_selections(
    parameter_options: Mapping[str, set[str]],
) -> list[dict[str, str]]:
    if not parameter_options:
        return [{}]
    return [
        dict(zip(parameter_options, values, strict=True))
        for values in product(
            *(parameter_options[key] for key in parameter_options)
        )
    ]


def _validate_simulation_references(
    *,
    path: str,
    state_ids: set[str],
    initial: str,
    transitions: tuple[SimulationTransition, ...],
    outcomes: tuple[SimulationOutcome, ...],
) -> None:
    if initial not in state_ids:
        _fail(path, "simulation initial state is dangling")
    if any(
        edge.from_id not in state_ids or edge.to_id not in state_ids
        for edge in transitions
    ):
        _fail(path, "simulation transition has a dangling endpoint")
    if any(outcome.state_id not in state_ids for outcome in outcomes):
        _fail(path, "simulation outcome has a dangling state")


def _validate_unconditional_reachability(
    path: str,
    mode: InteractionMode,
    state_ids: set[str],
    initial: str,
    transitions: tuple[SimulationTransition, ...],
) -> None:
    if mode in {
        InteractionMode.SCENARIO,
        InteractionMode.HYBRID,
        InteractionMode.EXPLORER,
    }:
        return
    adjacency = {state: [] for state in state_ids}
    for edge in transitions:
        adjacency[edge.from_id].append(edge.to_id)
    if _reachable(initial, adjacency) != state_ids:
        _fail(path, "simulation contains unreachable states")


def _parse_simulation(
    value: object, path: str, node_ids: set[str], edge_ids: set[str]
) -> Simulation:
    raw = _mapping(value, path)
    required = {
        "kind", "interactionMode", "parameters", "initialStateId",
        "states", "transitions", "outcomes",
    }
    _fields(raw, required=required, optional={"defaultIntervalMs"}, path=path)
    kind = SimulationKind(
        _enum(
            raw["kind"],
            frozenset(item.value for item in SimulationKind),
            f"{path}.kind",
        )
    )
    mode = InteractionMode(
        _enum(
            raw["interactionMode"],
            frozenset(item.value for item in InteractionMode),
            f"{path}.interactionMode",
        )
    )
    parameters, options = _parse_simulation_parameters(
        raw["parameters"], f"{path}.parameters"
    )
    states = tuple(
        _parse_simulation_state(
            item, f"{path}.states[{index}]", options, node_ids, edge_ids
        )
        for index, item in enumerate(
            _sequence(raw["states"], f"{path}.states", 1, 64)
        )
    )
    state_ids = set(_unique(states, f"{path}.states"))
    initial = _id(raw["initialStateId"], f"{path}.initialStateId")
    transitions = tuple(
        _parse_simulation_transition(
            item, f"{path}.transitions[{index}]", options
        )
        for index, item in enumerate(
            _sequence(raw["transitions"], f"{path}.transitions", 0, 128)
        )
    )
    _unique(transitions, f"{path}.transitions")
    outcomes = tuple(
        _parse_simulation_outcome(item, f"{path}.outcomes[{index}]")
        for index, item in enumerate(
            _sequence(raw["outcomes"], f"{path}.outcomes", 1, 64)
        )
    )
    _unique(outcomes, f"{path}.outcomes")
    _validate_simulation_references(
        path=path,
        state_ids=state_ids,
        initial=initial,
        transitions=transitions,
        outcomes=outcomes,
    )
    interval = _parse_interval(raw, path, mode)
    selections = _parameter_selections(options)
    _validate_simulation_domain(
        path=path,
        mode=mode,
        selections=selections,
        states=states,
        initial_state_id=initial,
        transitions=transitions,
    )
    _validate_unconditional_reachability(path, mode, state_ids, initial, transitions)
    return Simulation(
        kind, mode, parameters, initial, states, transitions, outcomes, interval
    )


def _payload_ids(payload: VisualizationPayload) -> tuple[set[str], set[str]]:
    if isinstance(payload, FlowPayload):
        return (
            {item.id for item in payload.steps},
            {edge.id for edge in payload.transitions},
        )
    if isinstance(payload, HierarchyPayload):
        return {item.id for item in payload.nodes}, set()
    if isinstance(payload, ComparisonPayload):
        return (
            {item.id for item in payload.alternatives + payload.criteria},
            {cell.id for cell in payload.cells},
        )
    if isinstance(payload, StateLoopPayload):
        return (
            {item.id for item in payload.states},
            {edge.id for edge in payload.transitions},
        )
    if isinstance(payload, CausalPayload):
        items = (
            payload.causes
            + payload.mechanisms
            + payload.outcomes
            + payload.mitigations
        )
        return {item.id for item in items}, {edge.id for edge in payload.relations}
    if isinstance(payload, TimelinePayload):
        return {item.id for item in payload.phases + payload.events}, set()
    if isinstance(payload, NetworkPayload):
        return (
            {item.id for item in payload.nodes},
            {edge.id for edge in payload.connections},
        )
    if isinstance(payload, MemoryPayload):
        return (
            {item.id for item in payload.layers},
            {edge.id for edge in payload.transfers},
        )
    if isinstance(payload, MatrixPayload):
        return (
            {item.id for item in payload.rows + payload.columns},
            {cell.id for cell in payload.cells},
        )
    return {item.id for item in payload.states}, {edge.id for edge in payload.transitions}


def _catalog_enum(
    enum_type: type[_CatalogEnum],
    value: object,
    path: str,
) -> _CatalogEnum:
    if type(value) is not str:
        _fail(path, "must be a string enum")
    try:
        return enum_type(value)
    except ValueError:
        _fail(path, "must use a supported enum value")


def parse_visualization_catalog_bytes(
    raw: bytes,
    source_name: str,
) -> VisualizationCatalog:
    """Parse one descriptor-pinned exact assignment catalog snapshot."""
    if type(raw) is not bytes:
        _fail("visualization catalog", "snapshot must be exact bytes")
    if len(raw) > MAX_VISUALIZATION_CATALOG_BYTES:
        _fail("visualization catalog", "exceeds maximum byte count")
    source = _text(source_name, "visualization catalog source name", 255)
    document = _mapping(strict_json_loads(raw, source), "catalog")
    _fields(
        document,
        required={"version", "lessons"},
        optional=set(),
        path="catalog",
    )
    if type(document["version"]) is not int or document["version"] != 1:
        _fail("catalog.version", "must be integer 1")
    rows = _sequence(document["lessons"], "catalog.lessons", 30, 30)
    assignments: list[VisualizationAssignment] = []
    for index, item in enumerate(rows):
        path = f"catalog.lessons[{index}]"
        row = _mapping(item, path)
        dynamic = row.get("dynamic")
        if type(dynamic) is not bool:
            _fail(f"{path}.dynamic", "must be a boolean")
        required = {
            "lessonId",
            "primaryType",
            "optionalSecondaryType",
            "dynamic",
        }
        if dynamic:
            required.add("simulation")
        _fields(row, required=required, optional=set(), path=path)
        lesson_id = _text(row["lessonId"], f"{path}.lessonId", 128)
        if _CORE_LESSON_ID.fullmatch(lesson_id) is None:
            _fail(f"{path}.lessonId", "must be a full canonical lesson ID")
        primary_type = _catalog_enum(
            VisualizationType,
            row["primaryType"],
            f"{path}.primaryType",
        )
        secondary_type = _catalog_enum(
            VisualizationType,
            row["optionalSecondaryType"],
            f"{path}.optionalSecondaryType",
        )
        simulation: CatalogSimulation | None = None
        if dynamic:
            simulation_path = f"{path}.simulation"
            raw_simulation = _mapping(row["simulation"], simulation_path)
            _fields(
                raw_simulation,
                required={
                    "kind",
                    "interactionMode",
                    "staticEquivalentId",
                    "visualRegressionStateIds",
                },
                optional=set(),
                path=simulation_path,
            )
            state_ids = _ids(
                raw_simulation["visualRegressionStateIds"],
                f"{simulation_path}.visualRegressionStateIds",
                3,
                3,
            )
            simulation = CatalogSimulation(
                kind=_catalog_enum(
                    SimulationKind,
                    raw_simulation["kind"],
                    f"{simulation_path}.kind",
                ),
                interaction_mode=_catalog_enum(
                    InteractionMode,
                    raw_simulation["interactionMode"],
                    f"{simulation_path}.interactionMode",
                ),
                static_equivalent_id=_id(
                    raw_simulation["staticEquivalentId"],
                    f"{simulation_path}.staticEquivalentId",
                ),
                visual_regression_state_ids=(
                    state_ids[0],
                    state_ids[1],
                    state_ids[2],
                ),
            )
        assignments.append(
            VisualizationAssignment(
                lesson_id=lesson_id,
                primary_type=primary_type,
                optional_secondary_type=secondary_type,
                dynamic=dynamic,
                simulation=simulation,
            )
        )
    lesson_ids = tuple(item.lesson_id for item in assignments)
    if len(set(lesson_ids)) != len(lesson_ids):
        _fail("catalog.lessons", "must not contain duplicate lesson IDs")
    if lesson_ids != tuple(sorted(lesson_ids)):
        _fail("catalog.lessons", "must be sorted by full lesson ID")
    return VisualizationCatalog(version=1, lessons=tuple(assignments))


def validate_visualization_assignments(
    catalog: VisualizationCatalog,
    lesson_visualizations: Mapping[str, tuple[Visualization, ...]],
) -> None:
    """Bind every complete lesson to the reviewed release-wide catalog.

    Comparing full lesson IDs and ordered types prevents a correct aggregate
    count from hiding swapped diagrams. Simulation metadata remains optional
    until runtime migration, but any authored simulation must already match the
    sole catalog capability granted to that lesson.
    """
    expected = {assignment.lesson_id: assignment for assignment in catalog.lessons}
    actual_ids = set(lesson_visualizations)
    if actual_ids != set(expected):
        _fail("visualization assignments", "must cover the exact catalog lesson IDs")
    for lesson_id in sorted(expected):
        assignment = expected[lesson_id]
        visuals = lesson_visualizations[lesson_id]
        if type(visuals) is not tuple or not 1 <= len(visuals) <= 2:
            _fail(f"lesson[{lesson_id}].visualizations", "must contain one or two visuals")
        if visuals[0].type is not assignment.primary_type:
            _fail(f"lesson[{lesson_id}]", "has the wrong primary visualization type")
        if len(visuals) == 2 and visuals[1].type is not assignment.optional_secondary_type:
            _fail(f"lesson[{lesson_id}]", "has an unapproved secondary visualization type")
        for visual in visuals:
            simulation = visual.simulation
            if simulation is None:
                continue
            approved = assignment.simulation
            if (
                not assignment.dynamic
                or approved is None
                or visual.id != approved.static_equivalent_id
                or simulation.kind is not approved.kind
                or simulation.interaction_mode is not approved.interaction_mode
            ):
                _fail(f"lesson[{lesson_id}]", "has an unapproved simulation")


def parse_visualizations(
    value: object | None,
    *,
    lesson_id: str,
    complete: bool,
    objective_evidence: Mapping[str, frozenset[str]],
    evidence_ids: frozenset[str],
    source_ids: frozenset[str],
) -> tuple[Visualization, ...]:
    """Validate and detach a lesson's authored visualization snapshot."""
    validated_lesson_id = _id(lesson_id, "lesson_id")
    lesson_path = f"lesson[{validated_lesson_id}]"
    if type(complete) is not bool:
        _fail(f"{lesson_path}.complete", "must be a boolean")
    if value is None:
        if complete:
            _fail(
                f"{lesson_path}.visualizations",
                "complete lessons require visualizations",
            )
        return ()
    values = _sequence(value, f"{lesson_path}.visualizations", 1, 2)
    required = {
        "id", "type", "caption", "question", "afterSection",
        "objectiveIds", "evidenceIds", "sourceIds",
        "expectedObservation", "payload",
    }
    parsed: list[Visualization] = []
    for index, item in enumerate(values):
        indexed_path = f"{lesson_path}.visualizations[{index}]"
        raw = _mapping(item, indexed_path)
        path = indexed_path
        visualization_id: str | None = None
        if "id" in raw:
            visualization_id = _id(raw["id"], f"{indexed_path}.id")
            path = f"{lesson_path}.visualization[{visualization_id}]"
        _fields(raw, required=required, optional={"notes", "simulation"}, path=path)
        assert visualization_id is not None
        kind_value = _enum(
            raw["type"],
            frozenset(kind.value for kind in VisualizationType),
            f"{path}.type",
        )
        kind = VisualizationType(kind_value)
        objectives = _ids(
            raw["objectiveIds"], f"{path}.objectiveIds", 1, 6
        )
        evidence = _ids(raw["evidenceIds"], f"{path}.evidenceIds", 1, 8)
        sources = _ids(raw["sourceIds"], f"{path}.sourceIds", 1, 8)
        if not set(objectives) <= set(objective_evidence):
            _fail(path, "has a dangling objective reference")
        if not set(evidence) <= evidence_ids:
            _fail(path, "has a dangling evidence reference")
        if not set(sources) <= source_ids:
            _fail(path, "has a dangling source reference")
        reachable_evidence: set[str] = set()
        for objective in objectives:
            reachable_evidence.update(objective_evidence[objective])
        if not set(evidence) <= reachable_evidence:
            _fail(path, "evidence is not reachable from referenced objectives")
        payload = _parse_payload(kind, raw["payload"], f"{path}.payload")
        node_ids, edge_ids = _payload_ids(payload)
        simulation = (
            None
            if "simulation" not in raw
            else _parse_simulation(
                raw["simulation"], f"{path}.simulation", node_ids, edge_ids
            )
        )
        notes = tuple(
            _text(note, f"{path}.notes[{note_index}]", 600)
            for note_index, note in enumerate(
                _sequence(raw.get("notes", []), f"{path}.notes", 0, 8)
            )
        )
        placement = LessonSectionRole(
            _enum(
                raw["afterSection"],
                frozenset(role.value for role in LessonSectionRole),
                f"{path}.afterSection",
            )
        )
        parsed.append(
            Visualization(
                visualization_id,
                kind,
                _text(raw["caption"], f"{path}.caption", 160),
                _text(raw["question"], f"{path}.question", 160),
                placement,
                objectives,
                evidence,
                sources,
                _text(
                    raw["expectedObservation"],
                    f"{path}.expectedObservation",
                    300,
                ),
                payload,
                notes,
                simulation,
            )
        )
    result = tuple(parsed)
    _unique(result, f"{lesson_path}.visualizations")
    if sum(visual.simulation is not None for visual in result) > 1:
        _fail(
            f"{lesson_path}.visualizations",
            "lesson must contain at most one simulation",
        )
    return result


_PAYLOAD_TYPES = MappingProxyType(
    {
        VisualizationType.FLOW: FlowPayload,
        VisualizationType.HIERARCHY: HierarchyPayload,
        VisualizationType.COMPARISON: ComparisonPayload,
        VisualizationType.STATE_LOOP: StateLoopPayload,
        VisualizationType.CAUSAL: CausalPayload,
        VisualizationType.TIMELINE: TimelinePayload,
        VisualizationType.NETWORK: NetworkPayload,
        VisualizationType.MEMORY: MemoryPayload,
        VisualizationType.MATRIX: MatrixPayload,
        VisualizationType.STATE_MACHINE: StateMachinePayload,
    }
)


def _bounded_models(
    value: object,
    expected: type[object],
    path: str,
    maximum: int = 128,
) -> tuple[object, ...]:
    if type(value) is not tuple or len(value) > maximum:
        _fail(path, "must be a bounded exact tuple")
    assert isinstance(value, tuple)
    if any(type(item) is not expected for item in value):
        _fail(path, "contains an invalid immutable model")
    return value


def _bounded_id_values(value: object, path: str, maximum: int) -> list[object]:
    if type(value) is not tuple or len(value) > maximum:
        _fail(path, "must be a bounded exact tuple")
    assert isinstance(value, tuple)
    return list(value)


def _item_raw(item: Item) -> dict[str, object]:
    return {"id": item.id, "label": item.label, "detail": item.detail}


def _relationship_raw(edge: Relationship) -> dict[str, object]:
    raw: dict[str, object] = {
        "id": edge.id,
        "from": edge.from_id,
        "to": edge.to_id,
        "label": edge.label,
    }
    if edge.kind is not None:
        raw["kind"] = edge.kind
    return raw


def _payload_render_raw(
    kind: VisualizationType,
    payload: VisualizationPayload,
    path: str,
) -> dict[str, object]:
    """Snapshot a direct model into the same bounded grammar used at parse time."""
    expected = _PAYLOAD_TYPES[kind]
    if type(payload) is not expected:
        _fail(path, "payload type does not match visualization type")
    if type(payload) is FlowPayload:
        return {
            "steps": [
                _item_raw(item)
                for item in _bounded_models(payload.steps, Item, f"{path}.steps")
            ],
            "transitions": [
                _relationship_raw(edge)
                for edge in _bounded_models(
                    payload.transitions, Relationship, f"{path}.transitions"
                )
            ],
        }
    if type(payload) is HierarchyPayload:
        return {"nodes": [
            {
                **_item_raw(node),
                "parentId": node.parent_id,
            }
            for node in _bounded_models(payload.nodes, HierarchyNode, f"{path}.nodes")
        ]}
    if type(payload) is ComparisonPayload:
        return {
            "alternatives": [
                _item_raw(item) for item in _bounded_models(
                    payload.alternatives, Item, f"{path}.alternatives"
                )
            ],
            "criteria": [
                _item_raw(item) for item in _bounded_models(
                    payload.criteria, Item, f"{path}.criteria"
                )
            ],
            "cells": [
                {
                    "id": cell.id,
                    "alternativeId": cell.alternative_id,
                    "criterionId": cell.criterion_id,
                    "value": cell.value,
                }
                for cell in _bounded_models(
                    payload.cells, ComparisonCell, f"{path}.cells"
                )
            ],
        }
    if type(payload) is StateLoopPayload:
        return {
            "states": [
                _item_raw(item) for item in _bounded_models(
                    payload.states, Item, f"{path}.states"
                )
            ],
            "transitions": [
                _relationship_raw(edge) for edge in _bounded_models(
                    payload.transitions, Relationship, f"{path}.transitions"
                )
            ],
            "exitStateId": payload.exit_state_id,
            "recoveryStateId": payload.recovery_state_id,
        }
    if type(payload) is CausalPayload:
        return {
            name: [
                _item_raw(item) for item in _bounded_models(
                    getattr(payload, name), Item, f"{path}.{name}"
                )
            ]
            for name in ("causes", "mechanisms", "outcomes", "mitigations")
        } | {
            "relations": [
                _relationship_raw(edge) for edge in _bounded_models(
                    payload.relations, Relationship, f"{path}.relations"
                )
            ]
        }
    if type(payload) is TimelinePayload:
        return {
            "phases": [
                _item_raw(item) for item in _bounded_models(
                    payload.phases, Item, f"{path}.phases"
                )
            ],
            "events": [
                {
                    "id": event.id,
                    "label": event.label,
                    "detail": event.detail,
                    "phaseId": event.phase_id,
                    "order": event.order,
                    **({"lane": event.lane} if event.lane is not None else {}),
                }
                for event in _bounded_models(
                    payload.events, TimelineEvent, f"{path}.events"
                )
            ],
        }
    if type(payload) is NetworkPayload:
        return {
            "nodes": [
                {
                    **_item_raw(node),
                    "componentId": node.component_id,
                }
                for node in _bounded_models(
                    payload.nodes, NetworkNode, f"{path}.nodes"
                )
            ],
            "components": [
                _item_raw(item) for item in _bounded_models(
                    payload.components, Item, f"{path}.components"
                )
            ],
            "connections": [
                _relationship_raw(edge) for edge in _bounded_models(
                    payload.connections, Relationship, f"{path}.connections"
                )
            ],
        }
    if type(payload) is MemoryPayload:
        return {
            "layers": [
                {**_item_raw(layer), "group": layer.group}
                for layer in _bounded_models(
                    payload.layers, MemoryLayer, f"{path}.layers"
                )
            ],
            "transfers": [
                _relationship_raw(edge) for edge in _bounded_models(
                    payload.transfers, Relationship, f"{path}.transfers"
                )
            ],
        }
    if type(payload) is MatrixPayload:
        return {
            "rows": [
                _item_raw(item) for item in _bounded_models(
                    payload.rows, Item, f"{path}.rows"
                )
            ],
            "columns": [
                _item_raw(item) for item in _bounded_models(
                    payload.columns, Item, f"{path}.columns"
                )
            ],
            "cells": [
                {
                    "id": cell.id,
                    "rowId": cell.row_id,
                    "columnId": cell.column_id,
                    "value": cell.value,
                    "status": cell.status,
                }
                for cell in _bounded_models(
                    payload.cells, MatrixCell, f"{path}.cells"
                )
            ],
        }
    assert type(payload) is StateMachinePayload
    return {
        "states": [
            _item_raw(item) for item in _bounded_models(
                payload.states, Item, f"{path}.states"
            )
        ],
        "initialStateId": payload.initial_state_id,
        "transitions": [
            {
                "id": edge.id,
                "from": edge.from_id,
                "to": edge.to_id,
                "event": edge.event,
                "status": edge.status,
                **({"reason": edge.reason} if edge.reason is not None else {}),
            }
            for edge in _bounded_models(
                payload.transitions,
                StateMachineTransition,
                f"{path}.transitions",
            )
        ],
    }


def _simulation_render_raw(simulation: Simulation, path: str) -> dict[str, object]:
    if type(simulation.kind) is not SimulationKind:
        _fail(f"{path}.kind", "must be an exact simulation enum")
    if type(simulation.interaction_mode) is not InteractionMode:
        _fail(f"{path}.interactionMode", "must be an exact interaction enum")
    parameters = []
    for parameter in _bounded_models(
        simulation.parameters, SimulationParameter, f"{path}.parameters"
    ):
        assert isinstance(parameter, SimulationParameter)
        parameters.append({
            "id": parameter.id,
            "label": parameter.label,
            "control": parameter.control,
            "options": [
                {"id": option.id, "label": option.label}
                for option in _bounded_models(
                    parameter.options,
                    ParameterOption,
                    f"{path}.parameters.options",
                )
            ],
            "defaultOptionId": parameter.default_option_id,
        })
    states = []
    for state in _bounded_models(
        simulation.states, SimulationState, f"{path}.states"
    ):
        assert isinstance(state, SimulationState)
        if type(state.when) is not MappingProxyType:
            _fail(f"{path}.states.when", "must be an immutable mapping")
        if len(state.when) > 8:
            _fail(f"{path}.states.when", "exceeds parameter count")
        states.append({
            "id": state.id,
            "label": state.label,
            "status": state.status,
            "when": dict(state.when),
            "activeNodeIds": _bounded_id_values(
                state.active_node_ids, f"{path}.states.activeNodeIds", 64
            ),
            "activeEdgeIds": _bounded_id_values(
                state.active_edge_ids, f"{path}.states.activeEdgeIds", 128
            ),
        })
    transitions = []
    for edge in _bounded_models(
        simulation.transitions, SimulationTransition, f"{path}.transitions"
    ):
        assert isinstance(edge, SimulationTransition)
        if type(edge.when) is not MappingProxyType:
            _fail(f"{path}.transitions.when", "must be an immutable mapping")
        if len(edge.when) > 8:
            _fail(f"{path}.transitions.when", "exceeds parameter count")
        transitions.append({
            "id": edge.id,
            "from": edge.from_id,
            "to": edge.to_id,
            "event": edge.event,
            "when": dict(edge.when),
        })
    raw: dict[str, object] = {
        "kind": simulation.kind.value,
        "interactionMode": simulation.interaction_mode.value,
        "parameters": parameters,
        "initialStateId": simulation.initial_state_id,
        "states": states,
        "transitions": transitions,
        "outcomes": [
            {
                "id": outcome.id,
                "stateId": outcome.state_id,
                "label": outcome.label,
            }
            for outcome in _bounded_models(
                simulation.outcomes, SimulationOutcome, f"{path}.outcomes"
            )
        ],
    }
    if simulation.default_interval_ms is not None:
        raw["defaultIntervalMs"] = simulation.default_interval_ms
    return raw


def _validate_visualization_for_rendering_unchecked(
    lesson_id: object,
    visual: object,
) -> tuple[str, Visualization]:
    """Reissue a fresh model so low-level mutation cannot bypass parse invariants."""
    validated_lesson_id = _id(lesson_id, "visualization.render.lessonId")
    if type(visual) is not Visualization:
        _fail("visualization.render", "requires an exact Visualization model")
    assert isinstance(visual, Visualization)
    if type(visual.type) is not VisualizationType:
        _fail("visualization.render.type", "must be an exact visualization enum")
    if type(visual.after_section) is not LessonSectionRole:
        _fail("visualization.render.afterSection", "must be an exact section enum")
    path = "visualization.render"
    visual_id = _id(visual.id, f"{path}.id")
    for name, value, maximum in (
        ("caption", visual.caption, 160),
        ("question", visual.question, 160),
        ("expectedObservation", visual.expected_observation, 300),
    ):
        _text(value, f"{path}.{name}", maximum)
    for name, values, low, high in (
        ("objectiveIds", visual.objective_ids, 1, 6),
        ("evidenceIds", visual.evidence_ids, 1, 8),
        ("sourceIds", visual.source_ids, 1, 8),
    ):
        if type(values) is not tuple:
            _fail(f"{path}.{name}", "must be an exact tuple")
        if not low <= len(values) <= high:
            _fail(f"{path}.{name}", "has an invalid item count")
        _ids(list(values), f"{path}.{name}", low, high)
    if type(visual.notes) is not tuple or len(visual.notes) > 8:
        _fail(f"{path}.notes", "must be a bounded exact tuple")
    notes = tuple(
        _text(note, f"{path}.notes[{index}]", 600)
        for index, note in enumerate(visual.notes)
    )
    payload = _parse_payload(
        visual.type,
        _payload_render_raw(visual.type, visual.payload, f"{path}.payload"),
        f"{path}.payload",
    )
    node_ids, edge_ids = _payload_ids(payload)
    simulation = None
    if visual.simulation is not None:
        if type(visual.simulation) is not Simulation:
            _fail(f"{path}.simulation", "must be an exact Simulation model")
        simulation = _parse_simulation(
            _simulation_render_raw(visual.simulation, f"{path}.simulation"),
            f"{path}.simulation",
            node_ids,
            edge_ids,
        )
    return validated_lesson_id, Visualization(
        visual_id,
        visual.type,
        visual.caption,
        visual.question,
        visual.after_section,
        visual.objective_ids,
        visual.evidence_ids,
        visual.source_ids,
        visual.expected_observation,
        payload,
        notes,
        simulation,
    )


def _validate_visualization_for_rendering(
    lesson_id: object,
    visual: object,
) -> tuple[str, Visualization]:
    """Convert expected structural corruption into one safe validation error."""
    try:
        return _validate_visualization_for_rendering_unchecked(
            lesson_id,
            visual,
        )
    except CurriculumValidationError:
        raise
    except (AttributeError, TypeError, ValueError):
        # Slots can be removed through low-level Python APIs even on frozen
        # dataclasses. These expected structural failures contain no useful
        # author detail; process-control and allocation failures still escape.
        _fail("visualization.render", "model structure is invalid")


def _e(value: str, *, quote: bool = False) -> str:
    return escape(value, quote=quote)


def _item_description(
    item: Item | HierarchyNode | NetworkNode | MemoryLayer,
    *,
    runtime_node: bool = False,
) -> str:
    node_attribute = (
        f' class="visualization__model-node" data-node-id="{_e(item.id, quote=True)}"'
        if runtime_node else ""
    )
    return (
        f"<dt{node_attribute}>{_e(item.label)}</dt>"
        f"<dd>{_e(item.detail)}</dd>"
    )


def _relationship_list(
    relationships: tuple[Relationship, ...],
    labels: Mapping[str, str],
) -> str:
    entries = "".join(
        f'<li class="visualization__model-edge" data-edge-id="{_e(edge.id, quote=True)}">'
        f"{_e(labels[edge.from_id])} → {_e(labels[edge.to_id])}: "
        f"{_e(edge.label)}"
        + (f" ({_e(edge.kind)})" if edge.kind is not None else "")
        + "</li>"
        for edge in relationships
    )
    return f'<ul class="visualization__relationships">{entries}</ul>'


def _render_flow(payload: FlowPayload) -> str:
    outgoing = {step.id: [] for step in payload.steps}
    labels = {step.id: step.label for step in payload.steps}
    for edge in payload.transitions:
        outgoing[edge.from_id].append(edge)
    entries = "".join(
        "<li><dl>"
        + _item_description(step, runtime_node=True)
        + "</dl>"
        + (
            _relationship_list(tuple(outgoing[step.id]), labels)
            if outgoing[step.id]
            else ""
        )
        + "</li>"
        for step in payload.steps
    )
    return f'<ol class="visualization__ordered-model">{entries}</ol>'


def _render_hierarchy(payload: HierarchyPayload) -> str:
    children: dict[str | None, list[HierarchyNode]] = {}
    for node in payload.nodes:
        children.setdefault(node.parent_id, []).append(node)

    # Validation caps and proves acyclicity before rendering; recursion follows
    # that authored tree and is therefore bounded by the 64-node schema limit.
    def branch(parent: str | None) -> str:
        return "<ul>" + "".join(
            "<li><dl>"
            + _item_description(node, runtime_node=True)
            + "</dl>"
            + (branch(node.id) if node.id in children else "")
            + "</li>"
            for node in children.get(parent, ())
        ) + "</ul>"

    return f'<div class="visualization__hierarchy">{branch(None)}</div>'


def _render_table(
    caption: str,
    rows: tuple[Item, ...],
    columns: tuple[Item, ...],
    values: Mapping[tuple[str, str], str],
) -> str:
    headings = "".join(
        f'<th scope="col">{_e(column.label)}'
        f"<small>{_e(column.detail)}</small></th>"
        for column in columns
    )
    body = "".join(
        "<tr>"
        f'<th scope="row">{_e(row.label)}<small>{_e(row.detail)}</small></th>'
        + "".join(
            f"<td>{_e(values[(row.id, column.id)])}</td>"
            for column in columns
        )
        + "</tr>"
        for row in rows
    )
    return (
        '<table class="visualization__table">'
        f"<caption>{_e(caption)}</caption>"
        f'<thead><tr><th scope="col">項目</th>{headings}</tr></thead>'
        f"<tbody>{body}</tbody></table>"
    )


def _render_causal(payload: CausalPayload) -> str:
    groups = (
        ("原因", payload.causes),
        ("機構", payload.mechanisms),
        ("結果", payload.outcomes),
        ("対策", payload.mitigations),
    )
    definitions = "".join(
        f"<dt>{label}</dt><dd><dl>"
        + "".join(_item_description(item) for item in items)
        + "</dl></dd>"
        for label, items in groups
    )
    labels = {
        item.id: item.label
        for _, items in groups
        for item in items
    }
    return (
        f'<dl class="visualization__causal-model">{definitions}</dl>'
        + _relationship_list(payload.relations, labels)
    )


def _render_timeline(payload: TimelinePayload) -> str:
    events_by_phase = {phase.id: [] for phase in payload.phases}
    for event in payload.events:
        events_by_phase[event.phase_id].append(event)
    phases = "".join(
        "<li>"
        f"<strong>{_e(phase.label)}</strong>"
        f"<p>{_e(phase.detail)}</p>"
        + (
            '<ol class="visualization__timeline-events">'
            + "".join(
                "<li>"
                f"<strong>{_e(event.label)}</strong>"
                f"<p>{_e(event.detail)}</p>"
                f"<p>順序: {event.order}</p>"
                + (f"<p>lane: {_e(event.lane)}</p>" if event.lane else "")
                + "</li>"
                for event in events_by_phase[phase.id]
            )
            + "</ol>"
            if events_by_phase[phase.id]
            else "<p>このフェーズにはイベントがありません。</p>"
        )
        + "</li>"
        for phase in payload.phases
    )
    return f'<ol class="visualization__timeline-phases">{phases}</ol>'


def _render_nodes_and_edges(
    nodes: tuple[Item | NetworkNode | MemoryLayer, ...],
    relationships: tuple[Relationship, ...],
    *, ordered: bool = False,
) -> str:
    tag = "ol" if ordered else "ul"
    node_entries = "".join(
        f"<li><dl>{_item_description(node, runtime_node=True)}</dl></li>" for node in nodes
    )
    labels = {node.id: node.label for node in nodes}
    return (
        f'<{tag} class="visualization__nodes">{node_entries}</{tag}>'
        + _relationship_list(relationships, labels)
    )


def _render_state_loop(payload: StateLoopPayload) -> str:
    labels = {state.id: state.label for state in payload.states}
    return (
        _render_nodes_and_edges(payload.states, payload.transitions)
        + '<dl class="visualization__state-loop-contract">'
        f"<dt>終了状態</dt><dd>{_e(labels[payload.exit_state_id])}</dd>"
        f"<dt>回復状態</dt><dd>{_e(labels[payload.recovery_state_id])}</dd>"
        "</dl>"
    )


def _render_network(payload: NetworkPayload) -> str:
    components = {component.id: component for component in payload.components}
    component_model = "".join(
        _item_description(component) for component in payload.components
    )
    nodes = "".join(
        "<li><dl>"
        + _item_description(node, runtime_node=True)
        + f"<dt>component</dt><dd>{_e(components[node.component_id].label)}</dd>"
        + "</dl></li>"
        for node in payload.nodes
    )
    labels = {node.id: node.label for node in payload.nodes}
    return (
        f'<dl class="visualization__components">{component_model}</dl>'
        f'<ul class="visualization__nodes">{nodes}</ul>'
        + _relationship_list(payload.connections, labels)
    )


def _render_memory(payload: MemoryPayload) -> str:
    nodes = "".join(
        "<li><dl>"
        + _item_description(layer, runtime_node=True)
        + f"<dt>group</dt><dd>{_e(layer.group)}</dd>"
        + "</dl></li>"
        for layer in payload.layers
    )
    labels = {layer.id: layer.label for layer in payload.layers}
    return (
        f'<ol class="visualization__nodes">{nodes}</ol>'
        + _relationship_list(payload.transfers, labels)
    )


def _render_state_machine(payload: StateMachinePayload) -> str:
    state_entries = "".join(
        "<li>"
        + ("<strong>初期状態: </strong>" if state.id == payload.initial_state_id else "")
        + f"{_e(state.label)}: {_e(state.detail)}</li>"
        for state in payload.states
    )
    labels = {state.id: state.label for state in payload.states}
    rows = "".join(
        "<tr>"
        f'<th scope="row">{_e(edge.event)}</th>'
        f"<td>{_e(labels[edge.from_id])}</td>"
        f"<td>{_e(labels[edge.to_id])}</td>"
        f"<td>{_e(edge.status)}</td>"
        f"<td>{_e(edge.reason or '—')}</td>"
        "</tr>"
        for edge in payload.transitions
    )
    return (
        f'<ul class="visualization__states">{state_entries}</ul>'
        '<table class="visualization__transitions"><caption>状態遷移</caption>'
        '<thead><tr><th scope="col">イベント</th><th scope="col">開始</th>'
        '<th scope="col">終了</th><th scope="col">判定</th>'
        '<th scope="col">理由</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )


def _render_payload(payload: VisualizationPayload) -> str:
    if isinstance(payload, FlowPayload):
        return _render_flow(payload)
    if isinstance(payload, HierarchyPayload):
        return _render_hierarchy(payload)
    if isinstance(payload, ComparisonPayload):
        values = {
            (cell.alternative_id, cell.criterion_id): cell.value
            for cell in payload.cells
        }
        return _render_table("選択肢の比較", payload.alternatives, payload.criteria, values)
    if isinstance(payload, StateLoopPayload):
        return _render_state_loop(payload)
    if isinstance(payload, CausalPayload):
        return _render_causal(payload)
    if isinstance(payload, TimelinePayload):
        return _render_timeline(payload)
    if isinstance(payload, NetworkPayload):
        return _render_network(payload)
    if isinstance(payload, MemoryPayload):
        return _render_memory(payload)
    if isinstance(payload, MatrixPayload):
        values = {
            (cell.row_id, cell.column_id): (
                cell.value if cell.status == "value" else f"該当なし: {cell.value}"
            )
            for cell in payload.cells
        }
        return _render_table("判断マトリクス", payload.rows, payload.columns, values)
    return _render_state_machine(payload)


def _render_simulation_oracle(simulation: Simulation) -> str:
    def mapping_codes(class_name: str, values: Mapping[str, str]) -> str:
        if not values:
            return "常時"
        return "、".join(
            f'<code class="{class_name}" '
            f'data-parameter-id="{_e(key, quote=True)}" '
            f'data-option-id="{_e(value, quote=True)}">'
            f"{_e(key)}={_e(value)}</code>"
            for key, value in sorted(values.items())
        )

    parameter_rows = "".join(
        "<tr>"
        f'<th scope="row">{_e(parameter.label)}</th>'
        f"<td>{'、'.join(_e(option.label) for option in parameter.options)}</td>"
        f"<td>{_e(parameter.default_option_id)}</td>"
        "</tr>"
        for parameter in simulation.parameters
    )
    state_items = "".join(
        f'<li data-state-id="{_e(state.id, quote=True)}" data-step-index="{index}">'
        f"<strong>{_e(state.label)}</strong>: {_e(state.status)}"
        f'; 条件 {mapping_codes("visualization__state-condition", state.when)}'
        "; node "
        + (
            "、".join(
                f'<code class="visualization__state-node" '
                f'data-node-id="{_e(value, quote=True)}">{_e(value)}</code>'
                for value in state.active_node_ids
            )
            or "なし"
        )
        + "; edge "
        + (
            "、".join(
                f'<code class="visualization__state-edge" '
                f'data-edge-id="{_e(value, quote=True)}">{_e(value)}</code>'
                for value in state.active_edge_ids
            )
            or "なし"
        )
        + "</li>"
        for index, state in enumerate(simulation.states)
    )
    transition_rows = "".join(
        f'<tr class="visualization__simulation-transition" '
        f'data-transition-id="{_e(edge.id, quote=True)}" '
        f'data-transition-event="{_e(edge.event, quote=True)}" '
        f'data-from-state-id="{_e(edge.from_id, quote=True)}" '
        f'data-to-state-id="{_e(edge.to_id, quote=True)}">'
        f'<th scope="row">{_e(edge.event)}</th>'
        f"<td>{_e(edge.from_id)}</td><td>{_e(edge.to_id)}</td>"
        f'<td>{mapping_codes("visualization__transition-condition", edge.when)}</td>'
        "</tr>"
        for edge in simulation.transitions
    )
    outcome_rows = "".join(
        f'<tr class="visualization__simulation-outcome" '
        f'data-outcome-id="{_e(outcome.id, quote=True)}" '
        f'data-state-id="{_e(outcome.state_id, quote=True)}">'
        f'<th scope="row">{_e(outcome.label)}</th>'
        f"<td>{_e(outcome.state_id)}</td></tr>"
        for outcome in simulation.outcomes
    )
    parameter_table = (
        '<table><caption>パラメータと選択肢</caption><thead><tr>'
        '<th scope="col">パラメータ</th><th scope="col">選択肢</th>'
        '<th scope="col">既定値</th></tr></thead>'
        f"<tbody>{parameter_rows}</tbody></table>"
        if simulation.parameters
        else ""
    )
    static_oracle = (
        '<div class="visualization__simulation-oracle">'
        + parameter_table
        + f'<ol class="visualization__simulation-states">{state_items}</ol>'
        '<table><caption>完全な遷移</caption><thead><tr>'
        '<th scope="col">イベント</th><th scope="col">開始</th>'
        '<th scope="col">終了</th><th scope="col">条件</th></tr></thead>'
        f"<tbody>{transition_rows}</tbody></table>"
        '<table><caption>観測結果</caption><thead><tr>'
        '<th scope="col">結果</th><th scope="col">状態</th></tr></thead>'
        f"<tbody>{outcome_rows}</tbody></table>"
        "</div>"
    )
    initial = next(
        state for state in simulation.states
        if state.id == simulation.initial_state_id
    )
    status = (
        '<p class="visualization__current-status" aria-live="polite">'
        f"現在の状態: {_e(initial.label)} — {_e(initial.status)}"
        "</p>"
    )
    model_note = (
        '<p class="visualization__simulation-note">'
        "このモデルは例示的かつ決定的であり、実システムの完全な再現ではありません。"
        "</p>"
    )
    return static_oracle + status + model_note


def _render_simulation_controls(
    simulation: Simulation,
    figure_id: str,
) -> str:
    mode = simulation.interaction_mode
    scenario = mode in {
        InteractionMode.SCENARIO,
        InteractionMode.HYBRID,
        InteractionMode.EXPLORER,
    }
    stepping = mode in {
        InteractionMode.STEPPER,
        InteractionMode.PLAYBACK,
        InteractionMode.HYBRID,
        InteractionMode.EXPLORER,
    }
    playback = mode in {InteractionMode.PLAYBACK, InteractionMode.HYBRID}

    parameter_controls = ""
    if scenario:
        fields: list[str] = []
        # Authored order is already schema-bounded and deterministic. Using its
        # index keeps control IDs fixed-length instead of leaking a 64-byte
        # authored identifier into the DOM namespace.
        for parameter_index, parameter in enumerate(simulation.parameters):
            control_id = f"{figure_id}-p-{parameter_index}"
            if parameter.control == "select":
                options = "".join(
                    f'<option value="{_e(option.id, quote=True)}"'
                    + (
                        " selected"
                        if option.id == parameter.default_option_id
                        else ""
                    )
                    + f">{_e(option.label)}</option>"
                    for option in parameter.options
                )
                fields.append(
                    f'<label for="{_e(control_id, quote=True)}">'
                    f"{_e(parameter.label)}</label>"
                    f'<select id="{_e(control_id, quote=True)}" '
                    f'data-parameter-id="{_e(parameter.id, quote=True)}" disabled>'
                    f"{options}</select>"
                )
            else:
                radios = "".join(
                    f'<label for="{_e(f"{control_id}-o-{option_index}", quote=True)}">'
                    f'<input id="{_e(f"{control_id}-o-{option_index}", quote=True)}" '
                    f'data-parameter-id="{_e(parameter.id, quote=True)}" '
                    f'type="radio" name="{_e(control_id, quote=True)}" '
                    f'value="{_e(option.id, quote=True)}" disabled'
                    + (
                        " checked"
                        if option.id == parameter.default_option_id
                        else ""
                    )
                    + f">{_e(option.label)}</label>"
                    for option_index, option in enumerate(parameter.options)
                )
                fields.append(
                    f"<fieldset disabled><legend>{_e(parameter.label)}</legend>"
                    f"{radios}</fieldset>"
                )
        parameter_controls = "".join(fields)

    def button(role: str, label: str) -> str:
        return (
            f'<button id="{_e(f"{figure_id}-{role}", quote=True)}" '
            f'type="button" data-action="{_e(role, quote=True)}" disabled>{label}</button>'
        )

    actions: list[str] = []
    if scenario:
        actions.append(button("apply", "適用"))
    if playback:
        actions.extend(
            (
                button("play", "再生"),
                button("pause", "一時停止"),
            )
        )
    if stepping:
        actions.extend(
            (
                button("previous", "前へ"),
                button("next", "次へ"),
            )
        )
    if playback:
        speed_id = f"{figure_id}-speed"
        actions.append(
            f'<label for="{_e(speed_id, quote=True)}">速度</label>'
            f'<select id="{_e(speed_id, quote=True)}" data-action="speed" disabled>'
            '<option value="0.5">0.5x</option>'
            '<option value="1" selected>1x</option>'
            '<option value="2">2x</option></select>'
        )
    actions.append(button("reset", "リセット"))
    return (
        '<div class="visualization__controls" hidden>'
        f"{parameter_controls}{''.join(actions)}</div>"
    )


def visualization_dom_namespace(lesson_id: str, visual_id: str) -> str:
    """Return the fixed-length DOM namespace for one authored visualization."""
    if type(lesson_id) is not str or type(visual_id) is not str:
        raise CurriculumValidationError("visual namespace inputs must be strings")
    try:
        lesson_bytes = lesson_id.encode("ascii")
        visual_bytes = visual_id.encode("ascii")
    except UnicodeError:
        raise CurriculumValidationError(
            "visual namespace inputs must be ASCII identifiers"
        ) from None
    # The versioned prefix, ASCII schema IDs, and NUL separator are fixed
    # canonical bytes. SHA-256 with a fixed 80-bit lowercase-hex prefix keeps
    # every derived DOM ID bounded; render_lesson_body still rejects the rare
    # truncation collision before combining visualizations.
    digest = hashlib.sha256(
        _DOM_NAMESPACE_PREFIX + lesson_bytes + b"\0" + visual_bytes
    ).hexdigest()[:_DOM_NAMESPACE_DIGEST_HEX_CHARS]
    return f"viz-{digest}"


def _render_validated_visualization(
    lesson_id: str,
    visual: Visualization,
) -> SafeHtml:
    """Render the fresh model issued by the bounded render validator."""
    figure_id = visualization_dom_namespace(lesson_id, visual.id)
    notes = "".join(f"<li>{_e(note)}</li>" for note in visual.notes)
    companion_notes = (
        '<div class="visualization__companion">'
        "<h3>注記</h3>"
        "<p>図を読む際の補足情報です。</p>"
        f'<ol class="visualization__companion-notes">{notes}</ol>'
        "</div>"
        if notes
        else ""
    )
    simulation_oracle = (
        ""
        if visual.simulation is None
        else _render_simulation_oracle(visual.simulation)
    )
    safe_figure = validate_generated_fragment(
        f'<figure id="{_e(figure_id, quote=True)}" '
        f'class="visualization visualization--{_e(visual.type.value, quote=True)}"'
        f' data-visualization-id="{_e(figure_id, quote=True)}"'
        + ("" if visual.simulation is None else
           f' data-simulation-kind="{_e(visual.simulation.kind.value, quote=True)}"'
           f' data-interaction-mode="{_e(visual.simulation.interaction_mode.value, quote=True)}"'
           f' data-initial-state-id="{_e(visual.simulation.initial_state_id, quote=True)}"'
           f' data-default-interval-ms="{visual.simulation.default_interval_ms or 1000}"')
        + ">"
        f"<figcaption>{_e(visual.caption)}</figcaption>"
        + companion_notes
        + f'<p class="visualization__question">{_e(visual.question)}</p>'
        + _render_payload(visual.payload)
        + f'<p class="visualization__observation">{_e(visual.expected_observation)}</p>'
        + simulation_oracle
        + "</figure>"
    )
    if visual.simulation is None:
        return safe_figure
    controls = _render_simulation_controls(visual.simulation, figure_id)
    # Author-controlled values were escaped and validated above. The combined
    # renderer-owned control grammar is independently validated without
    # widening the authored-fragment allowlist.
    return validate_generated_fragment(
        safe_figure.value[:-len("</figure>")]
        + controls
        + "</figure>"
    )


def render_visualization(lesson_id: str, visual: Visualization) -> SafeHtml:
    """Validate once, then render a complete semantic model."""
    lesson_id, visual = _validate_visualization_for_rendering(lesson_id, visual)
    return _render_validated_visualization(lesson_id, visual)
