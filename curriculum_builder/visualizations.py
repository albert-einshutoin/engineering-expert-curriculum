"""Strict immutable models for bounded lesson visualizations."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from itertools import product
import re
from types import MappingProxyType
import unicodedata

from .errors import CurriculumValidationError


_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_SIMULATION_EVENTS = frozenset({"next", "previous", "timer", "parameter-change", "reset"})


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
