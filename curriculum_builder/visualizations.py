"""Strict immutable models for bounded lesson visualizations."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from itertools import product
import re
from types import MappingProxyType
import unicodedata

from .errors import CurriculumValidationError


_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_PLACEMENTS = frozenset({"why", "mentalModel", "workedExample", "tradeoffs", "knowledgeCheck", "sourcesNext"})
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


@dataclass(frozen=True, slots=True)
class SimulationTransition:
    id: str
    from_id: str
    to_id: str
    event: str
    when: Mapping[str, str]


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
    after_section: str
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
    result = tuple(_id(item, f"{path}[{index}]") for index, item in enumerate(_sequence(value, path, low, high)))
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
    return Item(_id(raw["id"], f"{path}.id"), _text(raw["label"], f"{path}.label", 160), _text(raw["detail"], f"{path}.detail", 600))


def _items(value: object, path: str, low: int = 1, high: int = 64) -> tuple[Item, ...]:
    result = tuple(_item_record(item, f"{path}[{index}]") for index, item in enumerate(_sequence(value, path, low, high)))
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


def _relationships(value: object, path: str, *, low: int = 0, kind: bool = False) -> tuple[Relationship, ...]:
    result = tuple(_relationship(item, f"{path}[{index}]", kind=kind) for index, item in enumerate(_sequence(value, path, low, 128)))
    _unique(result, path)
    return result


def _check_refs(edges: tuple[Relationship, ...], nodes: set[str], path: str) -> None:
    for index, edge in enumerate(edges):
        if edge.from_id not in nodes or edge.to_id not in nodes:
            _fail(f"{path}[{index}]", "has a dangling endpoint")


def _adjacency(nodes: set[str], edges: tuple[Relationship, ...], *, undirected: bool = False) -> dict[str, list[str]]:
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


def _parse_payload(kind: VisualizationType, value: object, path: str) -> VisualizationPayload:
    raw = _mapping(value, path)
    if kind is VisualizationType.FLOW:
        _fields(raw, required={"steps", "transitions"}, optional=set(), path=path)
        steps = _items(raw["steps"], f"{path}.steps")
        transitions = _relationships(raw["transitions"], f"{path}.transitions")
        nodes = set(_unique(steps, f"{path}.steps")); _check_refs(transitions, nodes, f"{path}.transitions")
        indegree = {node: 0 for node in nodes}
        for edge in transitions: indegree[edge.to_id] += 1
        starts = [node for node, degree in indegree.items() if degree == 0]
        adjacent = _adjacency(nodes, transitions)
        if len(starts) != 1 or _reachable(starts[0], adjacent) != nodes:
            _fail(path, "flow must have one connected start")
        if _has_cycle(nodes, adjacent): _fail(path, "flow must be acyclic")
        order = {step.id: index for index, step in enumerate(steps)}
        if any(order[edge.from_id] >= order[edge.to_id] for edge in transitions):
            _fail(path, "flow transitions must reach a later step")
        return FlowPayload(steps, transitions)
    if kind is VisualizationType.HIERARCHY:
        _fields(raw, required={"nodes"}, optional=set(), path=path)
        values = _sequence(raw["nodes"], f"{path}.nodes", 1, 64)
        nodes: list[HierarchyNode] = []
        for index, value in enumerate(values):
            item_path = f"{path}.nodes[{index}]"; item = _mapping(value, item_path)
            _fields(item, required={"id", "label", "detail", "parentId"}, optional=set(), path=item_path)
            parent = item["parentId"]
            nodes.append(HierarchyNode(_id(item["id"], f"{item_path}.id"), _text(item["label"], f"{item_path}.label", 160), _text(item["detail"], f"{item_path}.detail", 600), None if parent is None else _id(parent, f"{item_path}.parentId")))
        result = tuple(nodes); known = set(_unique(result, f"{path}.nodes")); roots = [node.id for node in result if node.parent_id is None]
        if len(roots) != 1: _fail(path, "hierarchy must have one root")
        edges = tuple(Relationship(node.id, node.parent_id, node.id, "") for node in result if node.parent_id is not None)
        _check_refs(edges, known, f"{path}.nodes"); adjacent = _adjacency(known, edges)
        if _has_cycle(known, adjacent) or _reachable(roots[0], adjacent) != known: _fail(path, "hierarchy must be connected and acyclic")
        return HierarchyPayload(result)
    if kind is VisualizationType.COMPARISON:
        _fields(raw, required={"alternatives", "criteria", "cells"}, optional=set(), path=path)
        alternatives = _items(raw["alternatives"], f"{path}.alternatives"); criteria = _items(raw["criteria"], f"{path}.criteria")
        if len(alternatives) + len(criteria) > 64: _fail(path, "primary item count exceeds 64")
        _unique(alternatives + criteria, path)
        cells: list[ComparisonCell] = []
        for index, value in enumerate(_sequence(raw["cells"], f"{path}.cells", 1, 128)):
            item_path = f"{path}.cells[{index}]"; item = _mapping(value, item_path)
            _fields(item, required={"id", "alternativeId", "criterionId", "value"}, optional=set(), path=item_path)
            cells.append(ComparisonCell(_id(item["id"], f"{item_path}.id"), _id(item["alternativeId"], f"{item_path}.alternativeId"), _id(item["criterionId"], f"{item_path}.criterionId"), _text(item["value"], f"{item_path}.value", 160)))
        result = tuple(cells); _unique(result, f"{path}.cells")
        expected = {(a.id, c.id) for a in alternatives for c in criteria}; actual = {(cell.alternative_id, cell.criterion_id) for cell in result}
        if actual != expected or len(actual) != len(result): _fail(path, "comparison cells must form a complete Cartesian set")
        return ComparisonPayload(alternatives, criteria, result)
    if kind is VisualizationType.STATE_LOOP:
        _fields(raw, required={"states", "transitions", "exitStateId", "recoveryStateId"}, optional=set(), path=path)
        states = _items(raw["states"], f"{path}.states"); transitions = _relationships(raw["transitions"], f"{path}.transitions", low=1)
        known = set(_unique(states, f"{path}.states")); _check_refs(transitions, known, f"{path}.transitions")
        exit_id = _id(raw["exitStateId"], f"{path}.exitStateId"); recovery_id = _id(raw["recoveryStateId"], f"{path}.recoveryStateId")
        if exit_id not in known or recovery_id not in known: _fail(path, "state-loop has a dangling state reference")
        adjacent = _adjacency(known, transitions)
        if not _has_cycle(known, adjacent): _fail(path, "state-loop requires a feedback cycle")
        if exit_id not in _reachable(recovery_id, adjacent): _fail(path, "state-loop requires a recovery path to exit")
        if _reachable(states[0].id, adjacent) != known: _fail(path, "state-loop states must be connected")
        return StateLoopPayload(states, transitions, exit_id, recovery_id)
    if kind is VisualizationType.CAUSAL:
        _fields(raw, required={"causes", "mechanisms", "outcomes", "mitigations", "relations"}, optional=set(), path=path)
        causes = _items(raw["causes"], f"{path}.causes"); mechanisms = _items(raw["mechanisms"], f"{path}.mechanisms"); outcomes = _items(raw["outcomes"], f"{path}.outcomes"); mitigations = _items(raw["mitigations"], f"{path}.mitigations")
        all_items = causes + mechanisms + outcomes + mitigations
        if len(all_items) > 64: _fail(path, "primary item count exceeds 64")
        known = set(_unique(all_items, path)); relations = _relationships(raw["relations"], f"{path}.relations", low=1); _check_refs(relations, known, f"{path}.relations")
        adjacent = _adjacency(known, relations)
        if _has_cycle(known, adjacent): _fail(path, "causal relations must be acyclic")
        if _reachable(causes[0].id, _adjacency(known, relations, undirected=True)) != known:
            _fail(path, "causal items must form one connected explanation")
        cause_reachable = _reachable_from({cause.id for cause in causes}, adjacent)
        reachable_mechanisms = {
            mechanism.id for mechanism in mechanisms
            if mechanism.id in cause_reachable
        }
        after_mechanism = _reachable_from(reachable_mechanisms, adjacent)
        if any(outcome.id not in after_mechanism for outcome in outcomes):
            _fail(path, "every outcome must trace through a mechanism to a cause")
        return CausalPayload(causes, mechanisms, outcomes, mitigations, relations)
    if kind is VisualizationType.TIMELINE:
        _fields(raw, required={"phases", "events"}, optional=set(), path=path)
        phases = _items(raw["phases"], f"{path}.phases", high=8); phase_ids = set(_unique(phases, f"{path}.phases")); events: list[TimelineEvent] = []
        for index, value in enumerate(_sequence(raw["events"], f"{path}.events", 1, 64)):
            item_path = f"{path}.events[{index}]"; item = _mapping(value, item_path)
            _fields(item, required={"id", "label", "detail", "phaseId", "order"}, optional={"lane"}, path=item_path)
            order = item["order"]
            if type(order) is not int or not 0 <= order <= 127: _fail(f"{item_path}.order", "must be an integer from 0 through 127")
            lane = None if "lane" not in item else _id(item["lane"], f"{item_path}.lane")
            events.append(TimelineEvent(_id(item["id"], f"{item_path}.id"), _text(item["label"], f"{item_path}.label", 160), _text(item["detail"], f"{item_path}.detail", 600), _id(item["phaseId"], f"{item_path}.phaseId"), order, lane))
        result = tuple(events); _unique(result, f"{path}.events")
        _unique(phases + result, path)
        if any(event.phase_id not in phase_ids for event in result): _fail(path, "timeline has a dangling phase")
        keys = [(event.order, event.lane) for event in result]
        if len(set(keys)) != len(keys): _fail(path, "timeline order must be total")
        if keys != sorted(keys, key=lambda key: (key[0], key[1] or "")): _fail(path, "timeline events must retain total authored order")
        return TimelinePayload(phases, result)
    if kind is VisualizationType.NETWORK:
        _fields(raw, required={"nodes", "components", "connections"}, optional=set(), path=path)
        components = _items(raw["components"], f"{path}.components", high=8); component_ids = set(_unique(components, f"{path}.components")); nodes: list[NetworkNode] = []
        for index, value in enumerate(_sequence(raw["nodes"], f"{path}.nodes", 1, 64)):
            item_path = f"{path}.nodes[{index}]"; item = _mapping(value, item_path); _fields(item, required={"id", "label", "detail", "componentId"}, optional=set(), path=item_path)
            nodes.append(NetworkNode(_id(item["id"], f"{item_path}.id"), _text(item["label"], f"{item_path}.label", 160), _text(item["detail"], f"{item_path}.detail", 600), _id(item["componentId"], f"{item_path}.componentId")))
        node_result = tuple(nodes); known = set(_unique(node_result, f"{path}.nodes")); connections = _relationships(raw["connections"], f"{path}.connections"); _check_refs(connections, known, f"{path}.connections")
        _unique(components + node_result, path)
        if any(node.component_id not in component_ids for node in node_result): _fail(path, "network node has a dangling component")
        component_by_node = {node.id: node.component_id for node in node_result}
        if any(component_by_node[edge.from_id] != component_by_node[edge.to_id] for edge in connections):
            _fail(path, "network connection crosses declared components")
        if _has_cycle(known, _adjacency(known, connections)):
            _fail(path, "network connections must be acyclic")
        undirected = _adjacency(known, connections, undirected=True)
        for component in component_ids:
            members = {node.id for node in node_result if node.component_id == component}
            if not members or _reachable(next(iter(members)), undirected) & members != members: _fail(path, "network component must be connected")
        return NetworkPayload(node_result, components, connections)
    if kind is VisualizationType.MEMORY:
        _fields(raw, required={"layers", "transfers"}, optional=set(), path=path)
        layers: list[MemoryLayer] = []
        for index, value in enumerate(_sequence(raw["layers"], f"{path}.layers", 1, 64)):
            item_path = f"{path}.layers[{index}]"; item = _mapping(value, item_path); _fields(item, required={"id", "label", "detail", "group"}, optional=set(), path=item_path)
            layers.append(MemoryLayer(_id(item["id"], f"{item_path}.id"), _text(item["label"], f"{item_path}.label", 160), _text(item["detail"], f"{item_path}.detail", 600), _id(item["group"], f"{item_path}.group")))
        layer_result = tuple(layers); known = set(_unique(layer_result, f"{path}.layers"));
        if len({layer.group for layer in layer_result}) > 8: _fail(path, "memory group count exceeds 8")
        transfers = _relationships(raw["transfers"], f"{path}.transfers", kind=True); _check_refs(transfers, known, f"{path}.transfers")
        adjacent = _adjacency(known, transfers)
        if _has_cycle(known, adjacent): _fail(path, "memory transfers must be acyclic")
        if _reachable(layer_result[0].id, adjacent) != known: _fail(path, "memory layers must be connected in order")
        order = {layer.id: index for index, layer in enumerate(layer_result)}
        if any(order[edge.from_id] >= order[edge.to_id] for edge in transfers): _fail(path, "memory transfer must follow layer order")
        return MemoryPayload(layer_result, transfers)
    if kind is VisualizationType.MATRIX:
        _fields(raw, required={"rows", "columns", "cells"}, optional=set(), path=path)
        rows = _items(raw["rows"], f"{path}.rows"); columns = _items(raw["columns"], f"{path}.columns")
        if len(rows) + len(columns) > 64: _fail(path, "primary item count exceeds 64")
        _unique(rows + columns, path)
        cells: list[MatrixCell] = []
        for index, value in enumerate(_sequence(raw["cells"], f"{path}.cells", 1, 128)):
            item_path = f"{path}.cells[{index}]"; item = _mapping(value, item_path); _fields(item, required={"id", "rowId", "columnId", "value", "status"}, optional=set(), path=item_path)
            status = _enum(item["status"], frozenset({"value", "not-applicable"}), f"{item_path}.status")
            cells.append(MatrixCell(_id(item["id"], f"{item_path}.id"), _id(item["rowId"], f"{item_path}.rowId"), _id(item["columnId"], f"{item_path}.columnId"), _text(item["value"], f"{item_path}.value", 160), status))
        result = tuple(cells); _unique(result, f"{path}.cells"); expected = {(row.id, column.id) for row in rows for column in columns}; actual = {(cell.row_id, cell.column_id) for cell in result}
        if actual != expected or len(actual) != len(result): _fail(path, "matrix cells must form a complete Cartesian set")
        return MatrixPayload(rows, columns, result)
    _fields(raw, required={"states", "initialStateId", "transitions"}, optional=set(), path=path)
    states = _items(raw["states"], f"{path}.states"); known = set(_unique(states, f"{path}.states")); initial = _id(raw["initialStateId"], f"{path}.initialStateId")
    if initial not in known: _fail(path, "state-machine initial state is dangling")
    transitions: list[StateMachineTransition] = []
    for index, value in enumerate(_sequence(raw["transitions"], f"{path}.transitions", 0, 128)):
        item_path = f"{path}.transitions[{index}]"; item = _mapping(value, item_path); _fields(item, required={"id", "from", "to", "event", "status"}, optional={"reason"}, path=item_path)
        status = _enum(item["status"], frozenset({"allowed", "rejected"}), f"{item_path}.status"); reason = None if "reason" not in item else _text(item["reason"], f"{item_path}.reason", 600)
        if (status == "rejected") != (reason is not None): _fail(item_path, "only rejected transitions require a reason")
        transitions.append(StateMachineTransition(_id(item["id"], f"{item_path}.id"), _id(item["from"], f"{item_path}.from"), _id(item["to"], f"{item_path}.to"), _enum(item["event"], _SIMULATION_EVENTS, f"{item_path}.event"), status, reason))
    transition_result = tuple(transitions); _unique(transition_result, f"{path}.transitions")
    if any(edge.from_id not in known or edge.to_id not in known for edge in transition_result): _fail(path, "state-machine transition has a dangling endpoint")
    allowed = tuple(Relationship(edge.id, edge.from_id, edge.to_id, edge.event) for edge in transition_result if edge.status == "allowed")
    if _reachable(initial, _adjacency(known, allowed)) != known: _fail(path, "state-machine contains unreachable states")
    return StateMachinePayload(states, initial, transition_result)


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


def _parse_simulation(value: object, path: str, node_ids: set[str], edge_ids: set[str]) -> Simulation:
    raw = _mapping(value, path)
    required = {"kind", "interactionMode", "parameters", "initialStateId", "states", "transitions", "outcomes"}
    _fields(raw, required=required, optional={"defaultIntervalMs"}, path=path)
    kind = SimulationKind(_enum(raw["kind"], frozenset(kind.value for kind in SimulationKind), f"{path}.kind")); mode = InteractionMode(_enum(raw["interactionMode"], frozenset(mode.value for mode in InteractionMode), f"{path}.interactionMode"))
    parameters: list[SimulationParameter] = []
    for index, value in enumerate(_sequence(raw["parameters"], f"{path}.parameters", 0, 8)):
        item_path = f"{path}.parameters[{index}]"; item = _mapping(value, item_path); _fields(item, required={"id", "label", "control", "options", "defaultOptionId"}, optional=set(), path=item_path)
        options: list[ParameterOption] = []
        for option_index, option_value in enumerate(_sequence(item["options"], f"{item_path}.options", 2, 12)):
            option_path = f"{item_path}.options[{option_index}]"; option = _mapping(option_value, option_path); _fields(option, required={"id", "label"}, optional=set(), path=option_path)
            options.append(ParameterOption(_id(option["id"], f"{option_path}.id"), _text(option["label"], f"{option_path}.label", 160)))
        option_result = tuple(options); option_ids = set(_unique(option_result, f"{item_path}.options")); default = _id(item["defaultOptionId"], f"{item_path}.defaultOptionId")
        if default not in option_ids: _fail(item_path, "default option is dangling")
        parameters.append(SimulationParameter(_id(item["id"], f"{item_path}.id"), _text(item["label"], f"{item_path}.label", 160), _enum(item["control"], frozenset({"select", "radio"}), f"{item_path}.control"), option_result, default))
    parameter_result = tuple(parameters); _unique(parameter_result, f"{path}.parameters"); parameter_options = {parameter.id: {option.id for option in parameter.options} for parameter in parameter_result}
    combinations = 1
    for options in parameter_options.values(): combinations *= len(options)
    if combinations > 64: _fail(path, "parameter Cartesian space exceeds 64")
    states: list[SimulationState] = []
    for index, value in enumerate(_sequence(raw["states"], f"{path}.states", 1, 64)):
        item_path = f"{path}.states[{index}]"; item = _mapping(value, item_path); _fields(item, required={"id", "label", "status", "activeNodeIds", "activeEdgeIds"}, optional={"when"}, path=item_path)
        active_nodes = _ids(item["activeNodeIds"], f"{item_path}.activeNodeIds", 0, 64); active_edges = _ids(item["activeEdgeIds"], f"{item_path}.activeEdgeIds", 0, 128)
        if not set(active_nodes) <= node_ids or not set(active_edges) <= edge_ids: _fail(item_path, "active reference is dangling")
        states.append(SimulationState(_id(item["id"], f"{item_path}.id"), _text(item["label"], f"{item_path}.label", 160), _text(item["status"], f"{item_path}.status", 160), _when(item.get("when"), f"{item_path}.when", parameter_options), active_nodes, active_edges))
    state_result = tuple(states); state_ids = set(_unique(state_result, f"{path}.states")); initial = _id(raw["initialStateId"], f"{path}.initialStateId")
    if initial not in state_ids: _fail(path, "simulation initial state is dangling")
    transitions: list[SimulationTransition] = []
    for index, value in enumerate(_sequence(raw["transitions"], f"{path}.transitions", 0, 128)):
        item_path = f"{path}.transitions[{index}]"; item = _mapping(value, item_path); _fields(item, required={"id", "from", "to", "event"}, optional={"when"}, path=item_path)
        transitions.append(SimulationTransition(_id(item["id"], f"{item_path}.id"), _id(item["from"], f"{item_path}.from"), _id(item["to"], f"{item_path}.to"), _enum(item["event"], _SIMULATION_EVENTS, f"{item_path}.event"), _when(item.get("when"), f"{item_path}.when", parameter_options)))
    transition_result = tuple(transitions); _unique(transition_result, f"{path}.transitions")
    if any(edge.from_id not in state_ids or edge.to_id not in state_ids for edge in transition_result): _fail(path, "simulation transition has a dangling endpoint")
    outcomes: list[SimulationOutcome] = []
    for index, value in enumerate(_sequence(raw["outcomes"], f"{path}.outcomes", 1, 64)):
        item_path = f"{path}.outcomes[{index}]"; item = _mapping(value, item_path); _fields(item, required={"id", "stateId", "label"}, optional=set(), path=item_path)
        outcomes.append(SimulationOutcome(_id(item["id"], f"{item_path}.id"), _id(item["stateId"], f"{item_path}.stateId"), _text(item["label"], f"{item_path}.label", 160)))
    outcome_result = tuple(outcomes); _unique(outcome_result, f"{path}.outcomes")
    if any(outcome.state_id not in state_ids for outcome in outcome_result): _fail(path, "simulation outcome has a dangling state")
    interval = raw.get("defaultIntervalMs")
    playback = mode in {InteractionMode.PLAYBACK, InteractionMode.HYBRID}
    if playback:
        if type(interval) is not int or not 250 <= interval <= 5000 or interval % 50: _fail(f"{path}.defaultIntervalMs", "must be 250..5000 and a multiple of 50")
    elif "defaultIntervalMs" in raw: _fail(path, "default interval is forbidden for this mode")
    selections = [dict(zip(parameter_options, values, strict=True)) for values in product(*(parameter_options[key] for key in parameter_options))] if parameter_options else [{}]
    for selection in selections:
        matching_states = [state for state in state_result if _matches(state.when, selection)]
        if mode is InteractionMode.SCENARIO and len(matching_states) != 1: _fail(path, "scenario states must partition parameter combinations")
        for state in state_result:
            for event in _SIMULATION_EVENTS:
                matches = [edge for edge in transition_result if edge.from_id == state.id and edge.event == event and _matches(edge.when, selection)]
                if len(matches) > 1: _fail(path, "simulation transitions are ambiguous")
    reachable = {initial}
    queue = deque([initial])
    adjacency = {state: [] for state in state_ids}
    for edge in transition_result: adjacency[edge.from_id].append(edge.to_id)
    while queue:
        current = queue.popleft()
        for target in adjacency[current]:
            if target not in reachable: reachable.add(target); queue.append(target)
    if reachable != state_ids and mode is not InteractionMode.SCENARIO: _fail(path, "simulation contains unreachable states")
    return Simulation(kind, mode, parameter_result, initial, state_result, transition_result, outcome_result, interval if playback else None)


def _payload_ids(payload: VisualizationPayload) -> tuple[set[str], set[str]]:
    if isinstance(payload, FlowPayload): return {item.id for item in payload.steps}, {edge.id for edge in payload.transitions}
    if isinstance(payload, HierarchyPayload): return {item.id for item in payload.nodes}, set()
    if isinstance(payload, ComparisonPayload): return {item.id for item in payload.alternatives + payload.criteria}, {cell.id for cell in payload.cells}
    if isinstance(payload, StateLoopPayload): return {item.id for item in payload.states}, {edge.id for edge in payload.transitions}
    if isinstance(payload, CausalPayload): return {item.id for item in payload.causes + payload.mechanisms + payload.outcomes + payload.mitigations}, {edge.id for edge in payload.relations}
    if isinstance(payload, TimelinePayload): return {item.id for item in payload.phases + payload.events}, set()
    if isinstance(payload, NetworkPayload): return {item.id for item in payload.nodes}, {edge.id for edge in payload.connections}
    if isinstance(payload, MemoryPayload): return {item.id for item in payload.layers}, {edge.id for edge in payload.transfers}
    if isinstance(payload, MatrixPayload): return {item.id for item in payload.rows + payload.columns}, {cell.id for cell in payload.cells}
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
    _id(lesson_id, "lesson_id")
    if type(complete) is not bool: _fail("complete", "must be a boolean")
    if value is None:
        if complete: _fail("visualizations", "complete lessons require visualizations")
        return ()
    values = _sequence(value, "visualizations", 1, 2)
    required = {"id", "type", "caption", "question", "afterSection", "objectiveIds", "evidenceIds", "sourceIds", "expectedObservation", "payload"}
    parsed: list[Visualization] = []
    for index, item in enumerate(values):
        path = f"visualizations[{index}]"; raw = _mapping(item, path); _fields(raw, required=required, optional={"notes", "simulation"}, path=path)
        kind_value = _enum(raw["type"], frozenset(kind.value for kind in VisualizationType), f"{path}.type"); kind = VisualizationType(kind_value)
        objectives = _ids(raw["objectiveIds"], f"{path}.objectiveIds", 1, 6); evidence = _ids(raw["evidenceIds"], f"{path}.evidenceIds", 1, 8); sources = _ids(raw["sourceIds"], f"{path}.sourceIds", 1, 8)
        if not set(objectives) <= set(objective_evidence): _fail(path, "has a dangling objective reference")
        if not set(evidence) <= evidence_ids: _fail(path, "has a dangling evidence reference")
        if not set(sources) <= source_ids: _fail(path, "has a dangling source reference")
        reachable_evidence: set[str] = set()
        for objective in objectives:
            reachable_evidence.update(objective_evidence[objective])
        if not set(evidence) <= reachable_evidence:
            _fail(path, "evidence is not reachable from referenced objectives")
        payload = _parse_payload(kind, raw["payload"], f"{path}.payload"); node_ids, edge_ids = _payload_ids(payload)
        simulation = None if "simulation" not in raw else _parse_simulation(raw["simulation"], f"{path}.simulation", node_ids, edge_ids)
        notes = tuple(_text(note, f"{path}.notes[{note_index}]", 600) for note_index, note in enumerate(_sequence(raw.get("notes", []), f"{path}.notes", 0, 8)))
        parsed.append(Visualization(_id(raw["id"], f"{path}.id"), kind, _text(raw["caption"], f"{path}.caption", 160), _text(raw["question"], f"{path}.question", 160), _enum(raw["afterSection"], _PLACEMENTS, f"{path}.afterSection"), objectives, evidence, sources, _text(raw["expectedObservation"], f"{path}.expectedObservation", 300), payload, notes, simulation))
    result = tuple(parsed)
    _unique(result, "visualizations")
    return result
