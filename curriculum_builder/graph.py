"""Deterministic validation and staging for curriculum prerequisite graphs."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

from .errors import CurriculumValidationError


def _render_sorted(values: Iterable[object]) -> str:
    rendered: list[str] = []
    for value in values:
        try:
            value_repr = repr(value)
        except Exception:
            value_repr = f"<unrepresentable {type(value).__name__}>"
        rendered.append(value_repr)
    return ", ".join(sorted(rendered))


def _validate_node_ids(values: tuple[object, ...]) -> tuple[str, ...]:
    invalid_types = tuple(value for value in values if type(value) is not str)
    if invalid_types:
        raise CurriculumValidationError(
            f"node IDs must be strings: {_render_sorted(invalid_types)}"
        )

    node_ids = tuple(value for value in values if type(value) is str)
    if any(not node_id for node_id in node_ids):
        raise CurriculumValidationError("node IDs must be non-empty strings")

    padded = tuple(node_id for node_id in node_ids if node_id != node_id.strip())
    if padded:
        raise CurriculumValidationError(
            "node IDs must not have leading or trailing whitespace: "
            f"{_render_sorted(padded)}"
        )

    duplicates = sorted(
        node_id for node_id, count in Counter(node_ids).items() if count > 1
    )
    if duplicates:
        raise CurriculumValidationError(
            f"duplicate node ids: {', '.join(duplicates)}"
        )
    return node_ids


def _validate_dependencies(node_id: str, raw: object) -> tuple[str, ...]:
    if isinstance(raw, str):
        raise CurriculumValidationError(
            f"prerequisites for {node_id} must be an iterable of node IDs, "
            "not a string"
        )
    try:
        values = tuple(raw)  # type: ignore[arg-type]
    except TypeError as error:
        raise CurriculumValidationError(
            f"prerequisites for {node_id} must be iterable"
        ) from error

    invalid_types = tuple(value for value in values if type(value) is not str)
    if invalid_types:
        raise CurriculumValidationError(
            f"prerequisites for {node_id} must be strings: "
            f"{_render_sorted(invalid_types)}"
        )

    dependencies = tuple(value for value in values if type(value) is str)
    if any(not dependency for dependency in dependencies):
        raise CurriculumValidationError(
            f"prerequisites for {node_id} must be non-empty strings"
        )

    padded = tuple(
        dependency
        for dependency in dependencies
        if dependency != dependency.strip()
    )
    if padded:
        raise CurriculumValidationError(
            f"prerequisites for {node_id} must not have leading or trailing "
            f"whitespace: {_render_sorted(padded)}"
        )

    duplicates = sorted(
        dependency
        for dependency, count in Counter(dependencies).items()
        if count > 1
    )
    if duplicates:
        raise CurriculumValidationError(
            f"duplicate prerequisites for {node_id}: {', '.join(duplicates)}"
        )
    return dependencies


def _snapshot_prerequisites(
    prerequisites: Mapping[str, Iterable[str]],
) -> dict[str, object]:
    try:
        raw_entries = tuple(prerequisites.items())
    except Exception as error:
        raise CurriculumValidationError(
            "cannot snapshot prerequisites mapping"
        ) from error

    entries: list[tuple[object, object]] = []
    for index, entry in enumerate(raw_entries):
        try:
            key, value = entry
        except (TypeError, ValueError) as error:
            raise CurriculumValidationError(
                f"prerequisites mapping item {index} must be a key-value pair"
            ) from error
        entries.append((key, value))

    invalid_keys = tuple(key for key, _ in entries if type(key) is not str)
    if invalid_keys:
        raise CurriculumValidationError(
            f"prerequisite keys must be strings: {_render_sorted(invalid_keys)}"
        )

    keys = tuple(key for key, _ in entries if type(key) is str)
    duplicates = sorted(
        key for key, count in Counter(keys).items() if count > 1
    )
    if duplicates:
        raise CurriculumValidationError(
            f"duplicate prerequisite keys: {', '.join(duplicates)}"
        )
    return {
        key: value
        for key, value in entries
        if type(key) is str
    }


def topological_stages(
    node_ids: Iterable[str],
    prerequisites: Mapping[str, Iterable[str]],
) -> tuple[tuple[str, ...], ...]:
    """Return immutable parallel stages after strict graph validation."""
    if isinstance(node_ids, str):
        raise CurriculumValidationError(
            "node_ids must be an iterable of node IDs, not a string"
        )
    try:
        raw_node_ids = tuple(node_ids)
    except TypeError as error:
        raise CurriculumValidationError("node_ids must be iterable") from error
    validated_node_ids = _validate_node_ids(raw_node_ids)
    nodes = frozenset(validated_node_ids)

    if not isinstance(prerequisites, Mapping):
        raise CurriculumValidationError("prerequisites must be a mapping")

    prerequisite_snapshot = _snapshot_prerequisites(prerequisites)
    unknown_keys = sorted(
        key for key in prerequisite_snapshot if key not in nodes
    )
    if unknown_keys:
        raise CurriculumValidationError(
            f"unknown prerequisite nodes: {', '.join(unknown_keys)}"
        )

    normalized: dict[str, frozenset[str]] = {}
    for node_id in sorted(nodes):
        dependencies = _validate_dependencies(
            node_id,
            prerequisite_snapshot.get(node_id, ()),
        )
        normalized[node_id] = frozenset(dependencies)

    self_dependencies = sorted(
        node_id for node_id in nodes if node_id in normalized[node_id]
    )
    if self_dependencies:
        raise CurriculumValidationError(
            f"self dependency: {', '.join(self_dependencies)}"
        )

    indegree = {node_id: len(normalized[node_id]) for node_id in nodes}
    dependents: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    missing_nodes: set[str] = set()
    for dependent in sorted(nodes):
        for prerequisite in normalized[dependent]:
            if prerequisite not in nodes:
                missing_nodes.add(prerequisite)
                continue
            dependents[prerequisite].append(dependent)

    missing = sorted(missing_nodes)
    if missing:
        raise CurriculumValidationError(f"missing node: {', '.join(missing)}")

    stages: list[tuple[str, ...]] = []
    unresolved = set(nodes)
    ready = tuple(sorted(node_id for node_id in nodes if indegree[node_id] == 0))
    while ready:
        stages.append(ready)
        next_ready: list[str] = []
        for prerequisite in ready:
            unresolved.remove(prerequisite)
            # Reverse adjacency lets Kahn staging update each outgoing edge once;
            # rescanning all unresolved nodes per level would become quadratic.
            for dependent in dependents[prerequisite]:
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    next_ready.append(dependent)
        # Sorting keeps same-level CSS placement reproducible across inputs.
        ready = tuple(sorted(next_ready))

    if unresolved:
        raise CurriculumValidationError(
            f"cycle: {', '.join(sorted(unresolved))}"
        )
    return tuple(stages)
