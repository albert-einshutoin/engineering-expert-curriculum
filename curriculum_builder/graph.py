"""Deterministic validation and staging for curriculum prerequisite graphs."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

from .errors import CurriculumValidationError


def _render_sorted(values: Iterable[object]) -> str:
    return ", ".join(
        repr(value)
        for value in sorted(values, key=repr)
    )


def _validate_node_ids(values: tuple[object, ...]) -> tuple[str, ...]:
    invalid_types = tuple(value for value in values if not isinstance(value, str))
    if invalid_types:
        raise CurriculumValidationError(
            f"node IDs must be strings: {_render_sorted(invalid_types)}"
        )

    node_ids = tuple(value for value in values if isinstance(value, str))
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

    invalid_types = tuple(value for value in values if not isinstance(value, str))
    if invalid_types:
        raise CurriculumValidationError(
            f"prerequisites for {node_id} must be strings: "
            f"{_render_sorted(invalid_types)}"
        )

    dependencies = tuple(value for value in values if isinstance(value, str))
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

    invalid_keys = tuple(
        key for key in prerequisites if not isinstance(key, str)
    )
    if invalid_keys:
        raise CurriculumValidationError(
            f"prerequisite keys must be strings: {_render_sorted(invalid_keys)}"
        )

    unknown_keys = sorted(set(prerequisites) - nodes)
    if unknown_keys:
        raise CurriculumValidationError(
            f"unknown prerequisite nodes: {', '.join(unknown_keys)}"
        )

    normalized: dict[str, frozenset[str]] = {}
    for node_id in sorted(nodes):
        dependencies = _validate_dependencies(
            node_id,
            prerequisites[node_id] if node_id in prerequisites else (),
        )
        normalized[node_id] = frozenset(dependencies)

    self_dependencies = sorted(
        node_id for node_id in nodes if node_id in normalized[node_id]
    )
    if self_dependencies:
        raise CurriculumValidationError(
            f"self dependency: {', '.join(self_dependencies)}"
        )

    missing = sorted(
        {
            dependency
            for dependencies in normalized.values()
            for dependency in dependencies
            if dependency not in nodes
        }
    )
    if missing:
        raise CurriculumValidationError(f"missing node: {', '.join(missing)}")

    stages: list[tuple[str, ...]] = []
    remaining = set(nodes)
    while remaining:
        # Stable sorting makes generated HTML and CSS graph placement reproducible
        # across machines instead of inheriting set or input iteration order.
        ready = tuple(
            sorted(
                node_id
                for node_id in remaining
                if normalized[node_id].isdisjoint(remaining)
            )
        )
        if not ready:
            raise CurriculumValidationError(
                f"cycle: {', '.join(sorted(remaining))}"
            )
        stages.append(ready)
        remaining.difference_update(ready)
    return tuple(stages)
