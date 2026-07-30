from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
import unittest

from curriculum_builder.catalog import strict_json_loads
from curriculum_builder.errors import CurriculumValidationError
from curriculum_builder.graph import topological_stages


class SingleUseIds:
    def __init__(self, values: tuple[str, ...]) -> None:
        self._values = values
        self.iterations = 0

    def __iter__(self) -> Iterator[str]:
        self.iterations += 1
        if self.iterations > 1:
            raise AssertionError("node IDs were consumed more than once")
        return iter(self._values)


class GraphTests(unittest.TestCase):
    def test_builds_sorted_parallel_stages(self) -> None:
        stages = topological_stages(
            node_ids=("build", "foundation", "operate", "lead"),
            prerequisites={
                "foundation": (),
                "build": ("foundation",),
                "operate": ("foundation",),
                "lead": ("build", "operate"),
            },
        )

        self.assertEqual(
            stages,
            (("foundation",), ("build", "operate"), ("lead",)),
        )

    def test_reports_a_cycle_with_sorted_remaining_nodes(self) -> None:
        with self.assertRaisesRegex(
            CurriculumValidationError, r"^cycle: a, b, downstream$"
        ):
            topological_stages(
                node_ids=("downstream", "b", "a"),
                prerequisites={
                    "downstream": ("a",),
                    "b": ("a",),
                    "a": ("b",),
                },
            )

    def test_rejects_missing_prerequisites_in_sorted_error(self) -> None:
        with self.assertRaisesRegex(
            CurriculumValidationError, r"^missing node: alpha, unknown$"
        ):
            topological_stages(
                node_ids=("a",),
                prerequisites={"a": ("unknown", "alpha")},
            )

    def test_nodes_omitted_from_mapping_have_no_prerequisites(self) -> None:
        self.assertEqual(
            topological_stages(
                node_ids=("independent", "dependent"),
                prerequisites={"dependent": ("independent",)},
            ),
            (("independent",), ("dependent",)),
        )

    def test_rejects_string_node_collection(self) -> None:
        with self.assertRaisesRegex(
            CurriculumValidationError,
            r"^node_ids must be an iterable of node IDs, not a string$",
        ):
            topological_stages("abc", {})

    def test_rejects_invalid_node_ids_with_deterministic_messages(self) -> None:
        cases = (
            (
                (None, 1),
                "node IDs must be strings: 1, None",
            ),
            (
                ("",),
                "node IDs must be non-empty strings",
            ),
            (
                ("b ", " a"),
                "node IDs must not have leading or trailing whitespace: ' a', 'b '",
            ),
        )
        for node_ids, message in cases:
            with self.subTest(node_ids=node_ids):
                with self.assertRaisesRegex(
                    CurriculumValidationError, f"^{message}$"
                ):
                    topological_stages(node_ids, {})

    def test_rejects_duplicate_node_ids_in_sorted_error(self) -> None:
        with self.assertRaisesRegex(
            CurriculumValidationError, r"^duplicate node ids: a, b$"
        ):
            topological_stages(("b", "a", "b", "a"), {})

    def test_rejects_non_mapping_prerequisites(self) -> None:
        with self.assertRaisesRegex(
            CurriculumValidationError, r"^prerequisites must be a mapping$"
        ):
            topological_stages(("a",), ())  # type: ignore[arg-type]

    def test_rejects_non_string_prerequisite_keys_deterministically(self) -> None:
        prerequisites: dict[object, tuple[str, ...]] = {
            None: (),
            1: (),
            "a": (),
        }

        with self.assertRaisesRegex(
            CurriculumValidationError,
            r"^prerequisite keys must be strings: 1, None$",
        ):
            topological_stages(("a",), prerequisites)  # type: ignore[arg-type]

    def test_rejects_unknown_prerequisite_keys_in_sorted_error(self) -> None:
        with self.assertRaisesRegex(
            CurriculumValidationError,
            r"^unknown prerequisite nodes: alpha, unknown$",
        ):
            topological_stages(
                ("a",),
                {"unknown": (), "a": (), "alpha": ()},
            )

    def test_rejects_a_string_as_a_dependency_collection(self) -> None:
        with self.assertRaisesRegex(
            CurriculumValidationError,
            r"^prerequisites for a must be an iterable of node IDs, not a string$",
        ):
            topological_stages(("a",), {"a": "dependency"})

    def test_rejects_non_iterable_dependency_collection(self) -> None:
        with self.assertRaisesRegex(
            CurriculumValidationError,
            r"^prerequisites for a must be iterable$",
        ):
            topological_stages(("a",), {"a": 1})  # type: ignore[dict-item]

    def test_rejects_invalid_dependency_ids_with_deterministic_messages(self) -> None:
        cases = (
            (
                (None, 1),
                "prerequisites for a must be strings: 1, None",
            ),
            (
                ("",),
                "prerequisites for a must be non-empty strings",
            ),
            (
                ("z ", " dependency"),
                "prerequisites for a must not have leading or trailing whitespace: "
                "' dependency', 'z '",
            ),
        )
        for dependencies, message in cases:
            with self.subTest(dependencies=dependencies):
                with self.assertRaisesRegex(
                    CurriculumValidationError, f"^{message}$"
                ):
                    topological_stages(("a",), {"a": dependencies})

    def test_rejects_duplicate_dependencies_in_sorted_error(self) -> None:
        with self.assertRaisesRegex(
            CurriculumValidationError,
            r"^duplicate prerequisites for node: a, b$",
        ):
            topological_stages(
                ("node", "a", "b"),
                {"node": ("b", "a", "b", "a")},
            )

    def test_rejects_self_dependency_explicitly(self) -> None:
        with self.assertRaisesRegex(
            CurriculumValidationError, r"^self dependency: a$"
        ):
            topological_stages(("a",), {"a": ("a",)})

    def test_consumes_generator_inputs_once(self) -> None:
        node_ids = SingleUseIds(("lead", "build", "foundation"))
        dependency_iterations: dict[str, int] = {
            "foundation": 0,
            "build": 0,
            "lead": 0,
        }

        def dependencies(node: str, values: tuple[str, ...]) -> Iterator[str]:
            dependency_iterations[node] += 1
            if dependency_iterations[node] > 1:
                raise AssertionError(f"{node} dependencies consumed more than once")
            yield from values

        stages = topological_stages(
            node_ids,
            {
                "foundation": dependencies("foundation", ()),
                "build": dependencies("build", ("foundation",)),
                "lead": dependencies("lead", ("build",)),
            },
        )

        self.assertEqual(
            stages,
            (("foundation",), ("build",), ("lead",)),
        )
        self.assertEqual(node_ids.iterations, 1)
        self.assertEqual(
            dependency_iterations,
            {"foundation": 1, "build": 1, "lead": 1},
        )

    def test_result_is_independent_of_input_and_mapping_order(self) -> None:
        first = topological_stages(
            ("lead", "operate", "foundation", "build"),
            {
                "lead": ("operate", "build"),
                "operate": ("foundation",),
                "build": ("foundation",),
            },
        )
        second = topological_stages(
            ("build", "foundation", "lead", "operate"),
            {
                "build": ("foundation",),
                "operate": ("foundation",),
                "lead": ("build", "operate"),
            },
        )

        self.assertEqual(first, second)
        self.assertEqual(
            first,
            (("foundation",), ("build", "operate"), ("lead",)),
        )

    def test_does_not_mutate_inputs_and_returns_immutable_tuples(self) -> None:
        node_ids = ["build", "foundation"]
        dependencies = ["foundation"]
        prerequisites = {"build": dependencies}

        stages = topological_stages(node_ids, prerequisites)

        self.assertEqual(node_ids, ["build", "foundation"])
        self.assertEqual(dependencies, ["foundation"])
        self.assertEqual(prerequisites, {"build": ["foundation"]})
        self.assertIsInstance(stages, tuple)
        self.assertTrue(all(isinstance(stage, tuple) for stage in stages))

    def test_empty_graph_has_no_stages(self) -> None:
        self.assertEqual(topological_stages((), {}), ())


class RoadmapContractTests(unittest.TestCase):
    def test_checked_in_roadmap_has_strict_initial_schema_and_stages(self) -> None:
        path = Path("content/roadmap.json")
        document = strict_json_loads(path.read_bytes(), path)

        self.assertIsInstance(document, Mapping)
        assert isinstance(document, Mapping)
        self.assertEqual(set(document), {"version", "nodes"})
        self.assertIs(type(document["version"]), int)
        self.assertEqual(document["version"], 1)
        self.assertIsInstance(document["nodes"], list)
        nodes = document["nodes"]
        assert isinstance(nodes, list)
        self.assertEqual(len(nodes), 4)
        self.assertTrue(all(isinstance(node, Mapping) for node in nodes))
        self.assertTrue(
            all(
                set(node) == {"id", "title", "prerequisites"}
                for node in nodes
                if isinstance(node, Mapping)
            )
        )
        self.assertTrue(
            all(
                type(node["id"]) is str
                and type(node["title"]) is str
                and type(node["prerequisites"]) is list
                for node in nodes
                if isinstance(node, Mapping)
            )
        )

        ids = tuple(node["id"] for node in nodes)
        titles = tuple(node["title"] for node in nodes)
        prerequisites = {
            node["id"]: tuple(node["prerequisites"])
            for node in nodes
        }
        self.assertEqual(ids, ("foundation", "build", "operate", "lead"))
        self.assertEqual(titles, ("Think", "Build", "Run", "Lead"))
        self.assertEqual(
            prerequisites,
            {
                "foundation": (),
                "build": ("foundation",),
                "operate": ("build",),
                "lead": ("operate",),
            },
        )
        self.assertEqual(
            topological_stages(ids, prerequisites),
            (("foundation",), ("build",), ("operate",), ("lead",)),
        )


if __name__ == "__main__":
    unittest.main()
