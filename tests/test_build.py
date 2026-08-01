from __future__ import annotations

from contextlib import contextmanager
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import curriculum_builder.build as build_module
from curriculum_builder.build import (
    BuildCleanupError,
    BuildPostCommitError,
    BuildPublicationDurabilityError,
    BuildPublicationStateError,
    BuildStagingCleanupError,
    MAX_ROADMAP_BYTES,
    MAX_STYLESHEET_BYTES,
    MAX_VISUALIZATION_STYLESHEET_BYTES,
    _open_trusted_directory,
    _publish_directory,
    _read_stable_regular_file,
    build_site,
)
from curriculum_builder.catalog import (
    load_catalog_bytes,
    load_repository_catalog_bytes,
    serialize_catalog_document,
)
from curriculum_builder.errors import CurriculumValidationError
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_CANONICAL_LESSON_DIRECTORY = re.compile(
    r"core-(0[1-9]|[12][0-9]|30)-[a-z0-9]+(?:-[a-z0-9]+)*\Z",
    re.ASCII,
)


def _repository_lesson_source_counts(
    content_root: Path = REPOSITORY_ROOT / "content",
) -> dict[str, int]:
    # This acceptance oracle deliberately avoids the production collection
    # loader. Independent namespace and JSON checks prevent one shared loader
    # defect from making both generated output and its expected inventory agree.
    lessons_root = content_root / "lessons"
    if not lessons_root.is_dir() or lessons_root.is_symlink():
        raise AssertionError("canonical lessons root must be a directory")
    counts: dict[str, int] = {}
    ordinals: set[int] = set()

    def reject_duplicate_keys(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise AssertionError("duplicate lesson JSON key")
            value[key] = item
        return value

    with os.scandir(lessons_root) as entries:
        discovered = sorted(entries, key=lambda entry: entry.name)
    if len(discovered) > 30:
        raise AssertionError("too many canonical lessons")
    for entry in discovered:
        match = _CANONICAL_LESSON_DIRECTORY.fullmatch(entry.name)
        if (
            match is None
            or entry.is_symlink()
            or not entry.is_dir(follow_symlinks=False)
        ):
            raise AssertionError("unsafe canonical lesson directory")
        ordinal = int(match.group(1))
        if ordinal in ordinals:
            raise AssertionError("duplicate canonical lesson ordinal")
        ordinals.add(ordinal)
        directory = Path(entry.path)
        with os.scandir(directory) as children:
            names = {child.name for child in children}
        if names != {"lesson.json", "body.html"}:
            raise AssertionError("canonical lesson files must be exact")
        for name in names:
            node = os.lstat(directory / name)
            if not stat.S_ISREG(node.st_mode) or stat.S_ISLNK(node.st_mode):
                raise AssertionError("canonical lesson file must be regular")
        try:
            document = json.loads(
                (directory / "lesson.json").read_text(encoding="utf-8"),
                object_pairs_hook=reject_duplicate_keys,
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise AssertionError("canonical lesson JSON is invalid") from error
        if type(document) is not dict or document.get("id") != entry.name:
            raise AssertionError("canonical lesson directory/id mismatch")
        sources = document.get("sources")
        if type(sources) is not list or not sources:
            raise AssertionError("canonical lesson sources are invalid")
        for source in sources:
            if (
                type(source) is not dict
                or set(source) != {"title", "url", "kind"}
                or any(
                    type(value) is not str or not value
                    for value in source.values()
                )
            ):
                raise AssertionError("canonical lesson source is invalid")
        counts[entry.name] = len(sources)
    return counts


@contextmanager
def _fail_root_close(target: Path):
    original_open = os.open
    original_close = os.close
    state: dict[str, object] = {
        "descriptor": None,
        "failed": False,
    }
    canonical_target = target.resolve(strict=True)

    def recording_open(
        path: object,
        *args: object,
        **kwargs: object,
    ) -> int:
        descriptor = original_open(  # type: ignore[arg-type]
            path,
            *args,
            **kwargs,
        )
        if (
            kwargs.get("dir_fd") is None
            and isinstance(path, (str, os.PathLike))
            and Path(path) == canonical_target
        ):
            state["descriptor"] = descriptor
        return descriptor

    def failing_close(descriptor: int) -> None:
        if (
            descriptor == state["descriptor"]
            and not state["failed"]
        ):
            state["failed"] = True
            original_close(descriptor)
            raise OSError(f"root close failed: {canonical_target.name}")
        original_close(descriptor)

    with patch(
        "curriculum_builder.build.os.open",
        side_effect=recording_open,
    ), patch(
        "curriculum_builder.build.os.close",
        side_effect=failing_close,
    ):
        yield state


def _catalog_item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "id": "D01-M01-L1",
        "title": "Intro",
        "domainId": 1,
        "domainTitle": "Domain",
        "domainSlug": "domain",
        "moduleIndex": 1,
        "moduleTitle": "Module",
        "level": 1,
        "levelLabel": "Basic",
        "concepts": ["one", "two"],
        "outcome": "Outcome",
        "coreLessonId": None,
    }
    item.update(overrides)
    return item


def _roadmap(
    nodes: list[dict[str, object]] | None = None,
    **overrides: object,
) -> dict[str, object]:
    value: dict[str, object] = {
        "version": 1,
        "nodes": nodes
        if nodes is not None
        else [
            {"id": "foundation", "title": "Think", "prerequisites": []},
            {
                "id": "build",
                "title": "Build",
                "prerequisites": ["foundation"],
            },
            {"id": "operate", "title": "Run", "prerequisites": ["build"]},
            {"id": "lead", "title": "Lead", "prerequisites": ["operate"]},
        ],
    }
    value.update(overrides)
    return value


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


@contextmanager
def _fixture(
    *,
    catalog_items: list[dict[str, object]] | None = None,
    roadmap: object | None = None,
):
    with TemporaryDirectory() as directory:
        temporary_root = Path(directory).resolve(strict=True)
        # build_site validates the output parent before checking source overlap.
        # Nesting keeps that parent runner-owned even when /tmp is root-owned.
        root = temporary_root / "workspace"
        root.mkdir()
        content = root / "content"
        templates = root / "templates"
        static_root = root / "static"
        content.mkdir()
        shutil.copytree(REPOSITORY_ROOT / "templates", templates)
        static_root.mkdir()
        (static_root / "styles.css").write_bytes(
            (REPOSITORY_ROOT / "static" / "styles.css").read_bytes()
        )
        (static_root / "visualizations.css").write_bytes(
            (REPOSITORY_ROOT / "static" / "visualizations.css").read_bytes()
        )
        (content / "catalog.json").write_bytes(
            serialize_catalog_document(
                catalog_items or [_catalog_item()],
                "test fixture",
                source_sha256="0" * 64,
            )
        )
        if roadmap is None:
            roadmap = _roadmap()
        _write_json(content / "roadmap.json", roadmap)
        yield root, content, templates, static_root


class _DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.has_csp = False
        self.has_script = False
        self.event_attributes: list[str] = []
        self.remote_attributes: list[str] = []
        self.external_links: list[tuple[str, str | None]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag == "script":
            self.has_script = True
        values = {name.casefold(): value for name, value in attrs}
        if normalized_tag == "meta" and (
            values.get("http-equiv", "").casefold()
            == "content-security-policy"
        ):
            self.has_csp = True
        for name, value in attrs:
            normalized_name = name.casefold()
            if normalized_name == "id" and value is not None:
                self.ids.add(value)
            if normalized_name == "href" and value is not None:
                self.links.append(value)
            if normalized_name.startswith("on"):
                self.event_attributes.append(normalized_name)
            if normalized_name in {"href", "src", "action", "formaction"}:
                candidate = value or ""
                if (
                    normalized_tag == "a"
                    and normalized_name == "href"
                    and candidate.startswith("https://")
                ):
                    self.external_links.append(
                        (candidate, values.get("rel"))
                    )
                    continue
                if (
                    "://" in candidate
                    or candidate.startswith(("/", "\\", "//"))
                    or candidate.casefold().startswith(
                        ("data:", "javascript:", "vbscript:")
                    )
                ):
                    self.remote_attributes.append(candidate)

    handle_startendtag = handle_starttag


def _assert_static_site(
    test: unittest.TestCase,
    output: Path,
    lesson_source_counts: dict[str, int] | None = None,
    competency_source_count: int = 0,
) -> dict[Path, bytes]:
    source_counts = lesson_source_counts or {}
    expected = {
        Path("index.html"),
        Path("styles.css"),
        Path("static/visualizations.css"),
        Path("catalog/index.html"),
        Path("capstones/index.html"),
        Path("competencies/index.html"),
        Path("roadmap/index.html"),
        Path("lessons/index.html"),
    }
    expected.update(
        Path("lessons") / lesson_id / "index.html"
        for lesson_id in source_counts
    )
    if competency_source_count:
        expected.update(
            Path("capstones") / capstone_id / "index.html"
            for capstone_id in (
                "global-service",
                "legacy-evolution",
                "oss-launch",
            )
        )
    actual = {
        path.relative_to(output)
        for path in output.rglob("*")
        if path.is_file()
    }
    test.assertEqual(actual, expected)
    test.assertEqual(list(output.rglob("*.js")), [])
    test.assertEqual(
        (output / "static/visualizations.css").read_bytes(),
        (REPOSITORY_ROOT / "static/visualizations.css").read_bytes(),
    )

    ids_by_page: dict[Path, set[str]] = {}
    links_by_page: dict[Path, list[str]] = {}
    for relative in sorted(path for path in expected if path.suffix == ".html"):
        document = (output / relative).read_text(encoding="utf-8")
        parser = _DocumentParser()
        parser.feed(document)
        parser.close()
        test.assertTrue(parser.has_csp, relative)
        test.assertFalse(parser.has_script, relative)
        test.assertEqual(parser.event_attributes, [], relative)
        test.assertEqual(parser.remote_attributes, [], relative)
        lesson_id = (
            relative.parts[1]
            if len(relative.parts) == 3
            and relative.parts[0] == "lessons"
            else None
        )
        expected_source_count = source_counts.get(lesson_id or "", 0)
        if relative == Path("competencies/index.html"):
            expected_source_count = competency_source_count
        test.assertEqual(
            len(parser.external_links),
            expected_source_count,
            relative,
        )
        test.assertTrue(
            all(
                href.startswith("https://") and rel == "noreferrer"
                for href, rel in parser.external_links
            ),
            relative,
        )
        ids_by_page[relative] = parser.ids
        links_by_page[relative] = parser.links

    for page, links in links_by_page.items():
        for link in links:
            if link.startswith("https://"):
                continue
            path_part, separator, fragment = link.partition("#")
            target = (
                page
                if not path_part
                else Path(os.path.normpath(page.parent / path_part))
            )
            test.assertNotIn("..", target.parts, (page, link))
            test.assertIn(target, expected, (page, link))
            if separator:
                test.assertIn(fragment, ids_by_page[target], (page, link))

    return {
        relative: (output / relative).read_bytes()
        for relative in sorted(expected)
    }


class BuildAcceptanceTests(unittest.TestCase):
    def test_repository_lesson_oracle_is_independent_of_production_loader(
        self,
    ) -> None:
        forged_id = "core-30-forged-production-loader"
        forged = SimpleNamespace(
            lessons=(
                SimpleNamespace(
                    lesson=SimpleNamespace(
                        id=forged_id,
                        sources=(),
                    )
                ),
            )
        )
        with patch(
            f"{__name__}.load_lessons_from_root",
            return_value=forged,
            create=True,
        ):
            counts = _repository_lesson_source_counts()

        lessons_root = REPOSITORY_ROOT / "content" / "lessons"
        with os.scandir(lessons_root) as entries:
            raw_directory_ids = {
                entry.name
                for entry in entries
                if entry.is_dir(follow_symlinks=False)
            }
        self.assertEqual(set(counts), raw_directory_ids)
        self.assertNotIn(forged_id, counts)
        self.assertEqual(counts["core-01-systems-tradeoffs"], 3)

    def test_build_is_complete_static_file_relative_and_keeps_all_items(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory).resolve(strict=True) / "site"
            build_site(
                content_root=REPOSITORY_ROOT / "content",
                template_root=REPOSITORY_ROOT / "templates",
                static_root=REPOSITORY_ROOT / "static",
                output_root=output,
            )

            _assert_static_site(
                self,
                output,
                _repository_lesson_source_counts(),
            )
            catalog = (output / "catalog/index.html").read_text(
                encoding="utf-8"
            )
            self.assertEqual(
                catalog.count('<section class="catalog-card">'),
                38,
            )
            self.assertEqual(
                catalog.count('<h2 class="catalog-card__title">'),
                38,
            )
            self.assertEqual(
                catalog.count('<ol class="catalog-card__list">'),
                38,
            )
            self.assertEqual(catalog.count("<li id="), 1_140)
            parser = _DocumentParser()
            parser.feed(catalog)
            self.assertEqual(len(parser.ids), 1_141)

            roadmap = (output / "roadmap/index.html").read_text(
                encoding="utf-8"
            )
            lesson_ids = tuple(sorted(_repository_lesson_source_counts()))
            self.assertEqual(len(lesson_ids), 30)
            for lesson_id in lesson_ids:
                self.assertEqual(
                    roadmap.count(
                        f'../lessons/{lesson_id}/index.html'
                    ),
                    1,
                )
            gate_positions = tuple(
                roadmap.index(f'id="mastery-{gate_id}"')
                for gate_id in (
                    "foundation",
                    "builder",
                    "scaler",
                    "human",
                    "operator",
                    "leader",
                )
            )
            self.assertEqual(gate_positions, tuple(sorted(gate_positions)))

    def test_build_is_byte_mode_and_mtime_deterministic(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory).resolve(strict=True) / "site"
            arguments = (
                REPOSITORY_ROOT / "content",
                REPOSITORY_ROOT / "templates",
                REPOSITORY_ROOT / "static",
                output,
            )
            build_site(*arguments)
            first_bytes = _assert_static_site(
                self,
                output,
                _repository_lesson_source_counts(),
            )
            first_metadata = {
                path.relative_to(output): (
                    stat.S_IMODE(path.stat().st_mode),
                    path.stat().st_mtime_ns,
                )
                for path in output.rglob("*")
            }
            first_digests = {
                path: hashlib.sha256(value).hexdigest()
                for path, value in first_bytes.items()
            }

            build_site(*arguments)

            second_bytes = _assert_static_site(
                self,
                output,
                _repository_lesson_source_counts(),
            )
            second_metadata = {
                path.relative_to(output): (
                    stat.S_IMODE(path.stat().st_mode),
                    path.stat().st_mtime_ns,
                )
                for path in output.rglob("*")
            }
            self.assertEqual(
                first_digests,
                {
                    path: hashlib.sha256(value).hexdigest()
                    for path, value in second_bytes.items()
                },
            )
            self.assertEqual(first_metadata, second_metadata)
            self.assertEqual(
                set(first_metadata.values()),
                {(0o644, 0), (0o755, 0)},
            )

    def test_dynamic_values_are_escaped_before_fragment_validation(self) -> None:
        marker = '<img src=x onerror="alert(1)">'
        with _fixture(
            catalog_items=[
                _catalog_item(title=marker, outcome=f"Outcome {marker}")
            ]
        ) as (root, content, templates, static_root):
            output = root / "site"
            build_site(content, templates, static_root, output)
            catalog = (output / "catalog/index.html").read_text(
                encoding="utf-8"
            )

            self.assertNotIn(marker, catalog)
            self.assertEqual(catalog.count("&lt;img"), 2)
            _assert_static_site(self, output)

    def test_cli_builds_from_an_unrelated_working_directory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve(strict=True)
            unrelated = root / "cwd"
            unrelated.mkdir()
            output = root / "published"
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPOSITORY_ROOT / "tools/build.py"),
                    "--output",
                    str(output),
                ],
                cwd=unrelated,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(output), result.stdout)
            _assert_static_site(
                self,
                output,
                _repository_lesson_source_counts(),
                competency_source_count=3,
            )

    def test_cli_rejects_control_characters_without_log_injection(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve(strict=True)
            unrelated = root / "cwd"
            unrelated.mkdir()
            for suffix in (
                "published\nFORGED\x1b[31m",
                "published\u2028FORGED",
            ):
                with self.subTest(suffix=suffix):
                    output = root / suffix
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(REPOSITORY_ROOT / "tools/build.py"),
                            "--output",
                            str(output),
                        ],
                        cwd=unrelated,
                        check=False,
                        capture_output=True,
                        text=True,
                    )

                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, "")
                    self.assertIn("control character", result.stderr)
                    self.assertNotIn("FORGED", result.stderr)
                    self.assertNotIn("\x1b", result.stderr)
                    self.assertFalse(output.exists())


class BuildInputValidationTests(unittest.TestCase):
    def test_fixture_nests_overlap_root_below_owned_temporary_directory(
        self,
    ) -> None:
        with _fixture() as (root, content, templates, static_root):
            self.assertEqual(root.name, "workspace")
            self.assertEqual(
                (content.parent, templates.parent, static_root.parent),
                (root, root, root),
            )
            if hasattr(os, "geteuid"):
                self.assertEqual(os.stat(root.parent).st_uid, os.geteuid())

    def test_repository_catalog_uses_fixed_provenance_but_fixture_is_generic(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            official_output = (
                Path(directory).resolve(strict=True) / "official"
            )
            with patch(
                "curriculum_builder.build.load_repository_catalog_bytes",
                wraps=load_repository_catalog_bytes,
            ) as repository_loader, patch(
                "curriculum_builder.build.load_catalog_bytes",
                wraps=load_catalog_bytes,
            ) as generic_loader:
                build_site(
                    REPOSITORY_ROOT / "content",
                    REPOSITORY_ROOT / "templates",
                    REPOSITORY_ROOT / "static",
                    official_output,
                )
            repository_loader.assert_called_once()
            generic_loader.assert_not_called()

        with _fixture() as (root, content, templates, static_root):
            with patch(
                "curriculum_builder.build.load_repository_catalog_bytes",
                wraps=load_repository_catalog_bytes,
            ) as repository_loader, patch(
                "curriculum_builder.build.load_catalog_bytes",
                wraps=load_catalog_bytes,
            ) as generic_loader:
                build_site(content, templates, static_root, root / "site")
            repository_loader.assert_not_called()
            generic_loader.assert_called_once()

    def test_catalog_rendering_uses_the_pinned_bytes_during_path_race(
        self,
    ) -> None:
        with _fixture(
            catalog_items=[_catalog_item(title="Pinned title")]
        ) as (root, content, templates, static_root):
            catalog_path = content / "catalog.json"
            pinned = catalog_path.read_bytes()
            raced = serialize_catalog_document(
                [_catalog_item(title="Raced title")],
                "test fixture",
                source_sha256="0" * 64,
            )
            original_reader = _read_stable_regular_file
            catalog_reads = 0

            def racing_reader(
                directory: object,
                name: str,
                maximum_bytes: int,
            ) -> bytes:
                nonlocal catalog_reads
                if name != "catalog.json":
                    return original_reader(
                        directory,  # type: ignore[arg-type]
                        name,
                        maximum_bytes,
                    )
                catalog_reads += 1
                if catalog_reads == 1:
                    snapshot = original_reader(
                        directory,  # type: ignore[arg-type]
                        name,
                        maximum_bytes,
                    )
                    catalog_path.write_bytes(raced)
                    return snapshot
                catalog_path.write_bytes(pinned)
                return original_reader(
                    directory,  # type: ignore[arg-type]
                    name,
                    maximum_bytes,
                )

            with patch(
                "curriculum_builder.build._read_stable_regular_file",
                side_effect=racing_reader,
            ):
                build_site(content, templates, static_root, root / "site")

            catalog = (root / "site/catalog/index.html").read_text(
                encoding="utf-8"
            )
            self.assertEqual(catalog_reads, 2)
            self.assertIn("Pinned title", catalog)
            self.assertNotIn("Raced title", catalog)

    def test_template_rendering_uses_pinned_bytes_during_root_swap(
        self,
    ) -> None:
        with _fixture() as (root, content, templates, static_root):
            original_marker = "Pinned template marker"
            raced_marker = "Raced template marker"
            index_path = templates / "index.html"
            index_path.write_text(
                index_path.read_text(encoding="utf-8").replace(
                    "地図から入り、教科書として深く学ぶ",
                    original_marker,
                ),
                encoding="utf-8",
            )
            raced = root / "templates-raced"
            shutil.copytree(templates, raced)
            raced_index = raced / "index.html"
            raced_index.write_text(
                raced_index.read_text(encoding="utf-8").replace(
                    original_marker,
                    raced_marker,
                ),
                encoding="utf-8",
            )
            saved = root / "templates-pinned"
            original_render = build_module._render_artifacts
            restored = False

            def swapping_render(
                items: object,
                roadmap: object,
                template_source: object,
                static_assets: object,
                lessons: object,
                competencies: object,
                capstones: object,
            ) -> dict[object, bytes]:
                nonlocal restored
                templates.rename(saved)
                raced.rename(templates)
                try:
                    return original_render(
                        items,  # type: ignore[arg-type]
                        roadmap,  # type: ignore[arg-type]
                        template_source,  # type: ignore[arg-type]
                        static_assets,  # type: ignore[arg-type]
                        lessons,  # type: ignore[arg-type]
                        competencies,  # type: ignore[arg-type]
                        capstones,  # type: ignore[arg-type]
                    )
                finally:
                    templates.rename(raced)
                    saved.rename(templates)
                    restored = True

            with patch(
                "curriculum_builder.build._render_artifacts",
                side_effect=swapping_render,
            ):
                build_site(content, templates, static_root, root / "site")

            self.assertTrue(restored)
            self.assertTrue(index_path.is_file())
            home = (root / "site/index.html").read_text(encoding="utf-8")
            self.assertIn(original_marker, home)
            self.assertNotIn(raced_marker, home)

    def test_ambiguous_repository_catalog_path_cannot_bypass_provenance(
        self,
    ) -> None:
        ambiguous = REPOSITORY_ROOT / "content" / ".." / "content"
        with TemporaryDirectory() as directory, patch(
            "curriculum_builder.build.load_catalog_bytes",
            wraps=load_catalog_bytes,
        ) as generic_loader:
            output = Path(directory).resolve(strict=True) / "site"
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "ambiguous parent traversal",
            ):
                build_site(
                    ambiguous,
                    REPOSITORY_ROOT / "templates",
                    REPOSITORY_ROOT / "static",
                    output,
                )
        generic_loader.assert_not_called()

    def test_roadmap_schema_and_graph_fail_closed(self) -> None:
        valid_nodes = _roadmap()["nodes"]
        assert isinstance(valid_nodes, list)
        cases: dict[str, object] = {
            "root": [],
            "root fields": {**_roadmap(), "unknown": True},
            "version type": {**_roadmap(), "version": True},
            "version value": {**_roadmap(), "version": 2},
            "nodes type": {"version": 1, "nodes": {}},
            "empty nodes": {"version": 1, "nodes": []},
            "node type": {"version": 1, "nodes": [None]},
            "node fields": {
                "version": 1,
                "nodes": [{**valid_nodes[0], "unknown": True}],
            },
            "id type": _roadmap(
                [{"id": 1, "title": "Think", "prerequisites": []}]
            ),
            "title type": _roadmap(
                [{"id": "a", "title": 1, "prerequisites": []}]
            ),
            "blank title": _roadmap(
                [{"id": "a", "title": " ", "prerequisites": []}]
            ),
            "padded title": _roadmap(
                [{"id": "a", "title": " Think ", "prerequisites": []}]
            ),
            "prerequisites type": _roadmap(
                [{"id": "a", "title": "A", "prerequisites": "b"}]
            ),
            "duplicate id": _roadmap(
                [
                    {"id": "a", "title": "A", "prerequisites": []},
                    {"id": "a", "title": "Again", "prerequisites": []},
                ]
            ),
            "unknown prerequisite": _roadmap(
                [{"id": "a", "title": "A", "prerequisites": ["missing"]}]
            ),
            "self reference": _roadmap(
                [{"id": "a", "title": "A", "prerequisites": ["a"]}]
            ),
            "cycle": _roadmap(
                [
                    {"id": "a", "title": "A", "prerequisites": ["b"]},
                    {"id": "b", "title": "B", "prerequisites": ["a"]},
                ]
            ),
        }
        for label, roadmap in cases.items():
            with self.subTest(label=label), _fixture(
                roadmap=roadmap
            ) as (root, content, templates, static_root):
                with self.assertRaises(CurriculumValidationError):
                    build_site(content, templates, static_root, root / "site")

    def test_roadmap_rejects_duplicate_keys_and_input_limits(self) -> None:
        with _fixture() as (root, content, templates, static_root):
            (content / "roadmap.json").write_text(
                '{"version":1,"version":1,"nodes":[]}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "duplicate JSON key",
            ):
                build_site(content, templates, static_root, root / "site")

        with _fixture() as (root, content, templates, static_root):
            (content / "roadmap.json").write_bytes(
                b" " * (MAX_ROADMAP_BYTES + 1)
            )
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "roadmap.json exceeds maximum byte count",
            ):
                build_site(content, templates, static_root, root / "site")

    def test_stylesheet_must_be_stable_bounded_regular_file(self) -> None:
        with _fixture() as (root, content, templates, static_root):
            styles = static_root / "styles.css"
            styles.unlink()
            styles.symlink_to(REPOSITORY_ROOT / "static/styles.css")
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "styles.css must be a regular file",
            ):
                build_site(content, templates, static_root, root / "site")

        with _fixture() as (root, content, templates, static_root):
            (static_root / "styles.css").write_bytes(
                b"x" * (MAX_STYLESHEET_BYTES + 1)
            )
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "styles.css exceeds maximum byte count",
            ):
                build_site(content, templates, static_root, root / "site")

        with _fixture() as (root, content, templates, static_root):
            output = root / "site"
            output.mkdir()
            (output / "sentinel.txt").write_text("old", encoding="utf-8")
            (static_root / "styles.css").write_bytes(
                b'a { background: url("https://evil.example/a.png"); }'
            )
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "styles.css",
            ):
                build_site(
                    content,
                    templates,
                    static_root,
                    output,
                )

            self.assertEqual(
                (output / "sentinel.txt").read_text(),
                "old",
            )
            self.assertEqual(
                list(root.glob(".site.staging-*")),
                [],
            )

        with _fixture() as (_, __, ___, static_root):
            with _open_trusted_directory(
                static_root,
                "static_root",
            ) as handle:
                original_read = os.read
                changed = False

                def racing_read(descriptor: int, count: int) -> bytes:
                    nonlocal changed
                    chunk = original_read(descriptor, count)
                    if chunk and not changed:
                        changed = True
                        (static_root / "styles.css").write_bytes(b"changed")
                    return chunk

                with patch(
                    "curriculum_builder.build.os.read",
                    side_effect=racing_read,
                ):
                    with self.assertRaisesRegex(
                        CurriculumValidationError,
                        "styles.css changed during read",
                    ):
                        _read_stable_regular_file(
                            handle,
                            "styles.css",
                            MAX_STYLESHEET_BYTES,
                        )

    def test_visualization_stylesheet_is_regular_bounded_and_rechecked(self) -> None:
        with _fixture() as (root, content, templates, static_root):
            stylesheet = static_root / "visualizations.css"
            stylesheet.unlink()
            stylesheet.symlink_to(REPOSITORY_ROOT / "static/visualizations.css")
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "visualizations.css must be a regular file",
            ):
                build_site(content, templates, static_root, root / "site")

        with _fixture() as (root, content, templates, static_root):
            (static_root / "visualizations.css").write_bytes(
                b"x" * (MAX_VISUALIZATION_STYLESHEET_BYTES + 1)
            )
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "visualizations.css exceeds maximum byte count",
            ):
                build_site(content, templates, static_root, root / "site")

        with _fixture() as (root, content, templates, static_root):
            original_render = build_module._render_artifacts

            def racing_render(*args: object, **kwargs: object) -> object:
                result = original_render(*args, **kwargs)  # type: ignore[arg-type]
                (static_root / "visualizations.css").write_bytes(b"changed")
                return result

            with patch(
                "curriculum_builder.build._render_artifacts",
                side_effect=racing_render,
            ), self.assertRaisesRegex(
                CurriculumValidationError,
                "visualizations.css changed during build",
            ):
                build_site(content, templates, static_root, root / "site")

        with _fixture() as (root, content, templates, static_root):
            original_render = build_module._render_artifacts

            def replacing_render(*args: object, **kwargs: object) -> object:
                result = original_render(*args, **kwargs)  # type: ignore[arg-type]
                stylesheet = static_root / "visualizations.css"
                replacement = static_root / "visualizations.replacement"
                replacement.write_bytes(stylesheet.read_bytes())
                os.replace(replacement, stylesheet)
                return result

            with patch(
                "curriculum_builder.build._render_artifacts",
                side_effect=replacing_render,
            ), self.assertRaisesRegex(
                CurriculumValidationError,
                "visualizations.css changed during build",
            ):
                build_site(content, templates, static_root, root / "site")

    def test_roots_and_output_boundaries_reject_symlinks_permissions_and_overlap(
        self,
    ) -> None:
        with _fixture() as (root, content, templates, static_root):
            linked = root / "linked-static"
            linked.symlink_to(static_root, target_is_directory=True)
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "symbolic link",
            ):
                build_site(content, templates, linked, root / "site")

        with _fixture() as (root, content, templates, static_root):
            actual_parent = root / "actual-parent"
            actual_parent.mkdir()
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(
                actual_parent,
                target_is_directory=True,
            )
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "symbolic link",
            ):
                build_site(
                    content,
                    templates,
                    static_root,
                    linked_parent / "site",
                )

        with _fixture() as (root, content, templates, static_root):
            linked_parent = root / "linked-source-parent"
            linked_parent.symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "symbolic link",
            ):
                build_site(
                    linked_parent / "content",
                    templates,
                    static_root,
                    root / "site",
                )

        with _fixture() as (root, content, templates, static_root):
            os.chmod(static_root, 0o777)
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "group/world writable",
            ):
                build_site(content, templates, static_root, root / "site")

        with _fixture() as (root, content, templates, static_root):
            output = root / "site"
            output.mkdir(mode=0o755)
            os.chmod(output, 0o777)
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "group/world writable",
            ):
                build_site(content, templates, static_root, output)

        with _fixture() as (root, content, templates, static_root):
            for output in (
                content / "site",
                root,
            ):
                with self.subTest(output=output):
                    with self.assertRaisesRegex(
                        CurriculumValidationError,
                        "overlaps source",
                    ):
                        build_site(content, templates, static_root, output)

        with _fixture() as (root, content, templates, static_root):
            output = root / "site"
            output.symlink_to(root / "missing", target_is_directory=True)
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "output_root must be a real directory or absent",
            ):
                build_site(content, templates, static_root, output)

    def test_render_time_output_parent_rebinding_stops_before_staging(
        self,
    ) -> None:
        with _fixture() as (root, content, templates, static_root):
            output_parent = root / "output-parent"
            output_parent.mkdir()
            output = output_parent / "site"
            moved_parent = content / "moved-output-parent"
            original_render = build_module._render_artifacts
            rebound = False

            def render_then_rebind(*args: object, **kwargs: object):
                nonlocal rebound
                artifacts = original_render(*args, **kwargs)  # type: ignore[arg-type]
                os.rename(output_parent, moved_parent)
                output_parent.mkdir()
                rebound = True
                return artifacts

            captured: BaseException | None = None
            with patch(
                "curriculum_builder.build._render_artifacts",
                side_effect=render_then_rebind,
            ):
                try:
                    build_site(
                        content,
                        templates,
                        static_root,
                        output,
                    )
                except BaseException as error:
                    captured = error

            self.assertTrue(rebound)
            self.assertIsInstance(captured, CurriculumValidationError)
            self.assertFalse(output.exists())
            self.assertFalse((moved_parent / "site").exists())
            self.assertEqual(
                list(moved_parent.glob(".site.staging-*")),
                [],
            )


class BuildPublicationTests(unittest.TestCase):
    def test_each_root_close_failure_after_publish_is_postcommit(self) -> None:
        for root_label in (
            "content",
            "templates",
            "static",
            "output-parent",
        ):
            with self.subTest(root_label=root_label), _fixture() as (
                root,
                content,
                templates,
                static_root,
            ):
                output = root / "site"
                target = {
                    "content": content,
                    "templates": templates,
                    "static": static_root,
                    "output-parent": root,
                }[root_label]
                with _fail_root_close(target) as state:
                    with self.assertRaises(
                        BuildPublicationStateError
                    ) as raised:
                        build_site(
                            content,
                            templates,
                            static_root,
                            output,
                        )

                self.assertTrue(state["failed"])
                self.assertIn("site is visible", str(raised.exception))
                _assert_static_site(self, output)

    def test_root_close_is_secondary_to_existing_postcommit_failure(
        self,
    ) -> None:
        with _fixture() as (root, content, templates, static_root):
            output = root / "site"
            output.mkdir()
            (output / "sentinel.txt").write_text("old", encoding="utf-8")
            with _fail_root_close(root) as state, patch(
                "curriculum_builder.build._fsync_parent_after_publish",
                side_effect=OSError("primary publish fsync failure"),
            ):
                with self.assertRaises(
                    BuildPublicationDurabilityError
                ) as raised:
                    build_site(
                        content,
                        templates,
                        static_root,
                        output,
                    )

            self.assertTrue(state["failed"])
            self.assertIsInstance(raised.exception.__cause__, OSError)
            self.assertIn(
                "primary publish fsync failure",
                str(raised.exception.__cause__),
            )
            self.assertTrue(
                any(
                    "root close failed" in note
                    for note in raised.exception.__notes__
                )
            )
            _assert_static_site(self, output)
            self.assertEqual(len(list(root.glob(".site.staging-*"))), 1)

    def test_staging_initialization_cleanup_preserves_primary_and_reports_residue(
        self,
    ) -> None:
        cases = (
            ("fstat", True, False),
            ("fstat", False, True),
            ("scandir", True, True),
        )
        for primary_kind, fail_close, fail_rmdir in cases:
            with self.subTest(
                primary_kind=primary_kind,
                fail_close=fail_close,
                fail_rmdir=fail_rmdir,
            ), _fixture() as (root, content, templates, static_root):
                output = root / "site"
                output.mkdir()
                (output / "sentinel.txt").write_text(
                    "old",
                    encoding="utf-8",
                )
                original_open_directory = build_module._open_directory_at
                original_fstat = os.fstat
                original_scandir = os.scandir
                original_close = os.close
                original_rmdir = os.rmdir
                staging_descriptor: int | None = None
                primary_failed = False
                close_failed = False
                rmdir_failed = False

                def recording_open(
                    parent_fd: int,
                    name: str,
                ) -> int:
                    nonlocal staging_descriptor
                    descriptor = original_open_directory(parent_fd, name)
                    if name.startswith(".site.staging-"):
                        staging_descriptor = descriptor
                    return descriptor

                def failing_fstat(descriptor: int) -> os.stat_result:
                    nonlocal primary_failed
                    if (
                        primary_kind == "fstat"
                        and descriptor == staging_descriptor
                        and not primary_failed
                    ):
                        primary_failed = True
                        raise OSError("staging fstat primary")
                    return original_fstat(descriptor)

                def failing_scandir(path: object):
                    nonlocal primary_failed
                    if (
                        primary_kind == "scandir"
                        and path == staging_descriptor
                        and not primary_failed
                    ):
                        primary_failed = True
                        raise OSError("staging scandir primary")
                    return original_scandir(path)  # type: ignore[arg-type]

                def failing_close(descriptor: int) -> None:
                    nonlocal close_failed
                    if (
                        fail_close
                        and descriptor == staging_descriptor
                        and not close_failed
                    ):
                        close_failed = True
                        original_close(descriptor)
                        raise OSError("staging close secondary")
                    original_close(descriptor)

                def failing_rmdir(
                    path: object,
                    *args: object,
                    **kwargs: object,
                ) -> None:
                    nonlocal rmdir_failed
                    if (
                        fail_rmdir
                        and isinstance(path, str)
                        and path.startswith(".site.staging-")
                        and not rmdir_failed
                    ):
                        rmdir_failed = True
                        raise OSError("staging rmdir secondary")
                    original_rmdir(  # type: ignore[arg-type]
                        path,
                        *args,
                        **kwargs,
                    )

                with patch(
                    "curriculum_builder.build._open_directory_at",
                    side_effect=recording_open,
                ), patch(
                    "curriculum_builder.build.os.fstat",
                    side_effect=failing_fstat,
                ), patch(
                    "curriculum_builder.build.os.scandir",
                    side_effect=failing_scandir,
                ), patch(
                    "curriculum_builder.build.os.close",
                    side_effect=failing_close,
                ), patch(
                    "curriculum_builder.build.os.rmdir",
                    side_effect=failing_rmdir,
                ):
                    if fail_rmdir:
                        with self.assertRaises(
                            BuildStagingCleanupError
                        ) as raised:
                            build_site(
                                content,
                                templates,
                                static_root,
                                output,
                            )
                    else:
                        with self.assertRaisesRegex(
                            OSError,
                            f"staging {primary_kind} primary",
                        ) as raised:
                            build_site(
                                content,
                                templates,
                                static_root,
                                output,
                            )

                self.assertTrue(primary_failed)
                self.assertEqual(close_failed, fail_close)
                self.assertEqual(rmdir_failed, fail_rmdir)
                self.assertEqual(
                    (output / "sentinel.txt").read_text(),
                    "old",
                )
                residue = list(root.glob(".site.staging-*"))
                self.assertEqual(len(residue), int(fail_rmdir))
                if fail_rmdir:
                    self.assertIsInstance(
                        raised.exception.__cause__,
                        OSError,
                    )
                    self.assertIn(
                        f"staging {primary_kind} primary",
                        str(raised.exception.__cause__),
                    )
                notes = raised.exception.__notes__
                if fail_close:
                    self.assertTrue(
                        any(
                            "staging close secondary" in note
                            for note in notes
                        )
                    )
                if fail_rmdir:
                    self.assertTrue(
                        any(
                            "staging rmdir secondary" in note
                            for note in notes
                        )
                    )

    def test_prepublication_failure_preserves_previous_output_and_cleans_stage(
        self,
    ) -> None:
        with _fixture() as (root, content, templates, static_root):
            output = root / "site"
            output.mkdir()
            (output / "sentinel.txt").write_text(
                "previous",
                encoding="utf-8",
            )
            with patch(
                "curriculum_builder.build._publish_directory",
                side_effect=OSError("rename failed"),
            ):
                with self.assertRaisesRegex(OSError, "rename failed"):
                    build_site(content, templates, static_root, output)

            self.assertEqual(
                (output / "sentinel.txt").read_text(encoding="utf-8"),
                "previous",
            )
            self.assertEqual(
                list(root.glob(".site.staging-*")),
                [],
            )

    def test_native_publish_unavailable_fails_closed(self) -> None:
        with _fixture() as (root, content, templates, static_root):
            output = root / "site"
            output.mkdir()
            (output / "sentinel.txt").write_text("old", encoding="utf-8")
            with patch(
                "curriculum_builder.build._native_rename_function",
                side_effect=RuntimeError("unsupported"),
            ):
                with self.assertRaisesRegex(RuntimeError, "unsupported"):
                    build_site(content, templates, static_root, output)

            self.assertEqual((output / "sentinel.txt").read_text(), "old")
            self.assertEqual(list(root.glob(".site.staging-*")), [])

    def test_racing_publish_target_is_never_overwritten_or_deleted(
        self,
    ) -> None:
        with _fixture() as (root, content, templates, static_root):
            output = root / "site"

            def competing_publish(
                parent_fd: int,
                source_name: str,
                target_name: str,
                *,
                replace_existing: bool,
            ) -> None:
                self.assertFalse(replace_existing)
                os.mkdir(target_name, mode=0o700, dir_fd=parent_fd)
                target_fd = os.open(
                    target_name,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=parent_fd,
                )
                try:
                    competitor_fd = os.open(
                        "foreign.txt",
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=target_fd,
                    )
                    try:
                        os.write(competitor_fd, b"foreign")
                    finally:
                        os.close(competitor_fd)
                finally:
                    os.close(target_fd)
                _publish_directory(
                    parent_fd,
                    source_name,
                    target_name,
                    replace_existing=replace_existing,
                )

            with patch(
                "curriculum_builder.build._publish_directory",
                side_effect=competing_publish,
            ):
                with self.assertRaises(FileExistsError):
                    build_site(content, templates, static_root, output)

            self.assertEqual(
                (output / "foreign.txt").read_bytes(),
                b"foreign",
            )
            self.assertEqual(list(root.glob(".site.staging-*")), [])

    def test_existing_target_replacement_at_exchange_is_preserved(
        self,
    ) -> None:
        with _fixture() as (root, content, templates, static_root):
            output = root / "site"
            output.mkdir()
            (output / "original.txt").write_text(
                "original",
                encoding="utf-8",
            )
            displaced_name = "site.displaced-by-competitor"
            original_publish = _publish_directory

            def competing_exchange(
                parent_fd: int,
                source_name: str,
                target_name: str,
                *,
                replace_existing: bool,
            ) -> None:
                self.assertTrue(replace_existing)
                os.rename(
                    target_name,
                    displaced_name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                )
                os.mkdir(target_name, mode=0o700, dir_fd=parent_fd)
                competitor_fd = os.open(
                    target_name,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=parent_fd,
                )
                try:
                    sentinel_fd = os.open(
                        "competitor.txt",
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=competitor_fd,
                    )
                    try:
                        os.write(sentinel_fd, b"competitor")
                    finally:
                        os.close(sentinel_fd)
                finally:
                    os.close(competitor_fd)
                original_publish(
                    parent_fd,
                    source_name,
                    target_name,
                    replace_existing=replace_existing,
                )

            with patch(
                "curriculum_builder.build._publish_directory",
                side_effect=competing_exchange,
            ):
                with self.assertRaises(
                    BuildPublicationStateError
                ):
                    build_site(content, templates, static_root, output)

            _assert_static_site(self, output)
            recovery = list(root.glob(".site.staging-*"))
            self.assertEqual(len(recovery), 1)
            self.assertEqual(
                (recovery[0] / "competitor.txt").read_bytes(),
                b"competitor",
            )
            self.assertEqual(
                (root / displaced_name / "original.txt").read_text(),
                "original",
            )

    def test_publisher_failure_after_native_rename_is_postcommit(
        self,
    ) -> None:
        for replace_existing in (False, True):
            for failure_type in (KeyboardInterrupt, OSError):
                with self.subTest(
                    replace_existing=replace_existing,
                    failure_type=failure_type.__name__,
                ), _fixture() as (
                    root,
                    content,
                    templates,
                    static_root,
                ):
                    output = root / "site"
                    if replace_existing:
                        output.mkdir()
                        (output / "sentinel.txt").write_text(
                            "old",
                            encoding="utf-8",
                        )
                    original_publish = _publish_directory
                    failure = failure_type(
                        "publisher failed after native rename"
                    )

                    def publish_then_fail(
                        parent_fd: int,
                        source_name: str,
                        target_name: str,
                        *,
                        replace_existing: bool,
                    ) -> None:
                        original_publish(
                            parent_fd,
                            source_name,
                            target_name,
                            replace_existing=replace_existing,
                        )
                        raise failure

                    captured: BaseException | None = None
                    with patch(
                        "curriculum_builder.build._publish_directory",
                        side_effect=publish_then_fail,
                    ):
                        try:
                            build_site(
                                content,
                                templates,
                                static_root,
                                output,
                            )
                        except BaseException as error:
                            captured = error

                    self.assertIsInstance(
                        captured,
                        BuildPublicationStateError,
                    )
                    assert captured is not None
                    self.assertIs(captured.__cause__, failure)
                    _assert_static_site(self, output)
                    recovery = list(root.glob(".site.staging-*"))
                    self.assertEqual(
                        len(recovery),
                        int(replace_existing),
                    )
                    if replace_existing:
                        self.assertEqual(
                            (recovery[0] / "sentinel.txt").read_text(),
                            "old",
                        )

    def test_output_parent_rebinding_around_native_publish_is_postcommit(
        self,
    ) -> None:
        for timing in ("before-native", "after-native"):
            with self.subTest(timing=timing), _fixture() as (
                root,
                content,
                templates,
                static_root,
            ):
                output_parent = root / f"publish-parent-{timing}"
                output_parent.mkdir()
                output = output_parent / "site"
                moved_parent = content / f"moved-parent-{timing}"
                original_publish = _publish_directory

                def publish_while_rebinding(
                    parent_fd: int,
                    source_name: str,
                    target_name: str,
                    *,
                    replace_existing: bool,
                ) -> None:
                    if timing == "before-native":
                        os.rename(output_parent, moved_parent)
                        output_parent.mkdir()
                    original_publish(
                        parent_fd,
                        source_name,
                        target_name,
                        replace_existing=replace_existing,
                    )
                    if timing == "after-native":
                        os.rename(output_parent, moved_parent)
                        output_parent.mkdir()

                captured: BaseException | None = None
                with patch(
                    "curriculum_builder.build._publish_directory",
                    side_effect=publish_while_rebinding,
                ):
                    try:
                        build_site(
                            content,
                            templates,
                            static_root,
                            output,
                        )
                    except BaseException as error:
                        captured = error

                self.assertIsInstance(
                    captured,
                    BuildPublicationStateError,
                )
                self.assertFalse(output.exists())
                _assert_static_site(self, moved_parent / "site")

    def test_ambiguous_publisher_failure_never_runs_precommit_cleanup(
        self,
    ) -> None:
        with _fixture() as (root, content, templates, static_root):
            output = root / "site"
            output.mkdir()
            (output / "sentinel.txt").write_text("old", encoding="utf-8")
            original_publish = _publish_directory
            original_stat = os.stat
            failure = KeyboardInterrupt(
                "publisher interrupted after native rename"
            )
            published = False

            def publish_then_fail(
                parent_fd: int,
                source_name: str,
                target_name: str,
                *,
                replace_existing: bool,
            ) -> None:
                nonlocal published
                original_publish(
                    parent_fd,
                    source_name,
                    target_name,
                    replace_existing=replace_existing,
                )
                published = True
                raise failure

            def fail_reconciliation(
                path: object,
                *args: object,
                **kwargs: object,
            ) -> os.stat_result:
                if published and path == "site":
                    raise OSError("publication reconciliation failed")
                return original_stat(path, *args, **kwargs)  # type: ignore[arg-type]

            captured: BaseException | None = None
            with patch(
                "curriculum_builder.build._publish_directory",
                side_effect=publish_then_fail,
            ), patch(
                "curriculum_builder.build.os.stat",
                side_effect=fail_reconciliation,
            ):
                try:
                    build_site(
                        content,
                        templates,
                        static_root,
                        output,
                    )
                except BaseException as error:
                    captured = error

            self.assertIsInstance(captured, BuildPublicationStateError)
            assert captured is not None
            self.assertIs(captured.__cause__, failure)
            self.assertTrue(
                any(
                    "publication reconciliation failed" in note
                    for note in captured.__notes__
                )
            )
            _assert_static_site(self, output)
            recovery = list(root.glob(".site.staging-*"))
            self.assertEqual(len(recovery), 1)
            self.assertEqual(
                (recovery[0] / "sentinel.txt").read_text(),
                "old",
            )

    def test_file_and_directory_fsync_fail_before_publish(self) -> None:
        for fail_directory in (False, True):
            with self.subTest(
                fail_directory=fail_directory
            ), _fixture() as (root, content, templates, static_root):
                output = root / "site"
                output.mkdir()
                (output / "sentinel.txt").write_text(
                    "old",
                    encoding="utf-8",
                )
                original_fsync = os.fsync
                failed = False

                def failing_fsync(descriptor: int) -> None:
                    nonlocal failed
                    is_directory = stat.S_ISDIR(
                        os.fstat(descriptor).st_mode
                    )
                    if not failed and is_directory == fail_directory:
                        failed = True
                        raise OSError("fsync failed")
                    original_fsync(descriptor)

                with patch(
                    "curriculum_builder.build.os.fsync",
                    side_effect=failing_fsync,
                ):
                    with self.assertRaisesRegex(OSError, "fsync failed"):
                        build_site(
                            content,
                            templates,
                            static_root,
                            output,
                        )
                self.assertTrue(failed)
                self.assertEqual(
                    (output / "sentinel.txt").read_text(),
                    "old",
                )
                self.assertEqual(
                    list(root.glob(".site.staging-*")),
                    [],
                )

    def test_stale_legacy_backup_fails_without_mutating_any_output(self) -> None:
        with _fixture() as (root, content, templates, static_root):
            output = root / "site"
            output.mkdir()
            (output / "sentinel.txt").write_text("old", encoding="utf-8")
            stale = root / "site.previous"
            stale.mkdir()
            (stale / "foreign.txt").write_text("foreign", encoding="utf-8")

            with self.assertRaisesRegex(
                CurriculumValidationError,
                "stale build backup exists",
            ):
                build_site(content, templates, static_root, output)

            self.assertEqual((output / "sentinel.txt").read_text(), "old")
            self.assertEqual((stale / "foreign.txt").read_text(), "foreign")
            self.assertEqual(list(root.glob(".site.staging-*")), [])

    def test_private_staging_collision_is_retried_without_deleting_foreign_entry(
        self,
    ) -> None:
        with _fixture() as (root, content, templates, static_root):
            collision = root / (".site.staging-" + "0" * 32)
            collision.mkdir()
            (collision / "foreign.txt").write_text(
                "foreign",
                encoding="utf-8",
            )
            values = [
                type("UUID", (), {"hex": "0" * 32})(),
                type("UUID", (), {"hex": "1" * 32})(),
            ]
            with patch(
                "curriculum_builder.build.uuid.uuid4",
                side_effect=values,
            ):
                build_site(content, templates, static_root, root / "site")

            self.assertEqual(
                (collision / "foreign.txt").read_text(encoding="utf-8"),
                "foreign",
            )
            _assert_static_site(self, root / "site")

    def test_publish_durability_failure_keeps_new_output_and_old_recovery_entry(
        self,
    ) -> None:
        with _fixture() as (root, content, templates, static_root):
            output = root / "site"
            output.mkdir()
            (output / "sentinel.txt").write_text("old", encoding="utf-8")
            with patch(
                "curriculum_builder.build._fsync_parent_after_publish",
                side_effect=OSError("fsync failed"),
            ):
                with self.assertRaises(BuildPublicationDurabilityError):
                    build_site(content, templates, static_root, output)

            _assert_static_site(self, output)
            recovery = list(root.glob(".site.staging-*"))
            self.assertEqual(len(recovery), 1)
            self.assertEqual(
                (recovery[0] / "sentinel.txt").read_text(encoding="utf-8"),
                "old",
            )

    def test_postrename_stat_failure_is_explicitly_postcommit(
        self,
    ) -> None:
        with _fixture() as (root, content, templates, static_root):
            output = root / "site"
            output.mkdir()
            (output / "sentinel.txt").write_text("old", encoding="utf-8")
            original_publish = _publish_directory
            original_stat = os.stat
            committed = False

            def publishing(
                parent_fd: int,
                source_name: str,
                target_name: str,
                *,
                replace_existing: bool,
            ) -> None:
                nonlocal committed
                original_publish(
                    parent_fd,
                    source_name,
                    target_name,
                    replace_existing=replace_existing,
                )
                committed = True

            def failing_stat(
                path: object,
                *args: object,
                **kwargs: object,
            ) -> os.stat_result:
                if committed and path == "site":
                    raise OSError("post-rename stat failed")
                return original_stat(path, *args, **kwargs)  # type: ignore[arg-type]

            with patch(
                "curriculum_builder.build._publish_directory",
                side_effect=publishing,
            ), patch(
                "curriculum_builder.build.os.stat",
                side_effect=failing_stat,
            ):
                with self.assertRaises(BuildPostCommitError) as raised:
                    build_site(content, templates, static_root, output)

            self.assertNotIn("before publication", str(raised.exception))
            _assert_static_site(self, output)
            recovery = list(root.glob(".site.staging-*"))
            self.assertEqual(len(recovery), 1)
            self.assertEqual(
                (recovery[0] / "sentinel.txt").read_text(),
                "old",
            )

    def test_previous_descriptor_close_failure_is_postcommit_and_keeps_recovery(
        self,
    ) -> None:
        with _fixture() as (root, content, templates, static_root):
            output = root / "site"
            output.mkdir()
            (output / "sentinel.txt").write_text("old", encoding="utf-8")
            original_open = __import__(
                "curriculum_builder.build",
                fromlist=["_open_directory_at"],
            )._open_directory_at
            original_close = os.close
            previous_descriptor: int | None = None
            close_failed = False

            def recording_open(parent_fd: int, name: str) -> int:
                nonlocal previous_descriptor
                descriptor = original_open(parent_fd, name)
                if name == "site":
                    previous_descriptor = descriptor
                return descriptor

            def failing_close(descriptor: int) -> None:
                nonlocal close_failed
                if (
                    descriptor == previous_descriptor
                    and not close_failed
                ):
                    close_failed = True
                    original_close(descriptor)
                    raise OSError("previous close failed")
                original_close(descriptor)

            with patch(
                "curriculum_builder.build._open_directory_at",
                side_effect=recording_open,
            ), patch(
                "curriculum_builder.build.os.close",
                side_effect=failing_close,
            ):
                with self.assertRaises(BuildPostCommitError) as raised:
                    build_site(content, templates, static_root, output)

            self.assertTrue(close_failed)
            self.assertNotIn("before publication", str(raised.exception))
            _assert_static_site(self, output)
            recovery = list(root.glob(".site.staging-*"))
            self.assertEqual(len(recovery), 1)
            self.assertEqual(
                (recovery[0] / "sentinel.txt").read_text(),
                "old",
            )

    def test_postcommit_close_failure_does_not_replace_primary_cause(
        self,
    ) -> None:
        with _fixture() as (root, content, templates, static_root):
            output = root / "site"
            output.mkdir()
            (output / "sentinel.txt").write_text("old", encoding="utf-8")
            original_publish = _publish_directory
            original_open = __import__(
                "curriculum_builder.build",
                fromlist=["_open_directory_at"],
            )._open_directory_at
            original_stat = os.stat
            original_close = os.close
            previous_descriptor: int | None = None
            committed = False
            close_failed = False

            def recording_open(parent_fd: int, name: str) -> int:
                nonlocal previous_descriptor
                descriptor = original_open(parent_fd, name)
                if name == "site":
                    previous_descriptor = descriptor
                return descriptor

            def publishing(
                parent_fd: int,
                source_name: str,
                target_name: str,
                *,
                replace_existing: bool,
            ) -> None:
                nonlocal committed
                original_publish(
                    parent_fd,
                    source_name,
                    target_name,
                    replace_existing=replace_existing,
                )
                committed = True

            def failing_stat(
                path: object,
                *args: object,
                **kwargs: object,
            ) -> os.stat_result:
                if committed and path == "site":
                    raise OSError("primary post-rename stat failure")
                return original_stat(path, *args, **kwargs)  # type: ignore[arg-type]

            def failing_close(descriptor: int) -> None:
                nonlocal close_failed
                if (
                    descriptor == previous_descriptor
                    and not close_failed
                ):
                    close_failed = True
                    original_close(descriptor)
                    raise OSError("secondary close failure")
                original_close(descriptor)

            with patch(
                "curriculum_builder.build._open_directory_at",
                side_effect=recording_open,
            ), patch(
                "curriculum_builder.build._publish_directory",
                side_effect=publishing,
            ), patch(
                "curriculum_builder.build.os.stat",
                side_effect=failing_stat,
            ), patch(
                "curriculum_builder.build.os.close",
                side_effect=failing_close,
            ):
                with self.assertRaises(BuildPostCommitError) as raised:
                    build_site(content, templates, static_root, output)

            self.assertTrue(close_failed)
            self.assertIsInstance(raised.exception.__cause__, OSError)
            self.assertIn(
                "primary post-rename stat failure",
                str(raised.exception.__cause__),
            )
            self.assertTrue(
                any(
                    "secondary close failure" in note
                    for note in raised.exception.__notes__
                )
            )
            _assert_static_site(self, output)
            recovery = list(root.glob(".site.staging-*"))
            self.assertEqual(len(recovery), 1)
            self.assertEqual(
                (recovery[0] / "sentinel.txt").read_text(),
                "old",
            )

    def test_postpublish_cleanup_failure_keeps_new_output_and_reports_state(
        self,
    ) -> None:
        with _fixture() as (root, content, templates, static_root):
            output = root / "site"
            output.mkdir()
            (output / "sentinel.txt").write_text("old", encoding="utf-8")
            with patch(
                "curriculum_builder.build._remove_owned_directory",
                side_effect=OSError("cleanup failed"),
            ):
                with self.assertRaises(BuildCleanupError):
                    build_site(content, templates, static_root, output)

            _assert_static_site(self, output)
            self.assertEqual(len(list(root.glob(".site.staging-*"))), 1)

    def test_recovery_cleanup_refuses_a_nested_cross_device_directory(
        self,
    ) -> None:
        with _fixture() as (root, content, templates, static_root):
            output = root / "site"
            nested = output / "nested"
            nested.mkdir(parents=True)
            (nested / "sentinel.txt").write_text(
                "old",
                encoding="utf-8",
            )
            original_publish = _publish_directory
            original_open_directory = build_module._open_directory_at
            original_scandir = os.scandir
            original_unlink = os.unlink
            published = False
            recovery_descriptor: int | None = None
            nested_opened = False
            unlink_calls: list[object] = []

            class DifferentDeviceEntry:
                def __init__(self, entry: os.DirEntry[str]) -> None:
                    self._entry = entry
                    self.name = entry.name

                def stat(
                    self,
                    *,
                    follow_symlinks: bool = True,
                ) -> os.stat_result:
                    current = self._entry.stat(
                        follow_symlinks=follow_symlinks
                    )
                    fields = list(current)
                    fields[2] = current.st_dev + 1
                    return os.stat_result(fields)

            class ScandirProxy:
                def __init__(self, delegate: object) -> None:
                    self._delegate = delegate

                def __enter__(self) -> tuple[object, ...]:
                    entries = self._delegate.__enter__()
                    return tuple(
                        DifferentDeviceEntry(entry)
                        if entry.name == "nested"
                        else entry
                        for entry in entries
                    )

                def __exit__(self, *arguments: object) -> object:
                    return self._delegate.__exit__(*arguments)

            def publishing(
                parent_fd: int,
                source_name: str,
                target_name: str,
                *,
                replace_existing: bool,
            ) -> None:
                nonlocal published
                original_publish(
                    parent_fd,
                    source_name,
                    target_name,
                    replace_existing=replace_existing,
                )
                published = True

            def recording_open(
                parent_fd: int,
                name: str,
            ) -> int:
                nonlocal recovery_descriptor, nested_opened
                descriptor = original_open_directory(parent_fd, name)
                if published and name.startswith(".site.staging-"):
                    recovery_descriptor = descriptor
                if published and name == "nested":
                    nested_opened = True
                return descriptor

            def cross_device_scandir(path: object):
                delegate = original_scandir(path)  # type: ignore[arg-type]
                if path == recovery_descriptor:
                    return ScandirProxy(delegate)
                return delegate

            def recording_unlink(
                path: object,
                *args: object,
                **kwargs: object,
            ) -> None:
                unlink_calls.append(path)
                original_unlink(  # type: ignore[arg-type]
                    path,
                    *args,
                    **kwargs,
                )

            captured: BaseException | None = None
            with patch(
                "curriculum_builder.build._publish_directory",
                side_effect=publishing,
            ), patch(
                "curriculum_builder.build._open_directory_at",
                side_effect=recording_open,
            ), patch(
                "curriculum_builder.build.os.scandir",
                side_effect=cross_device_scandir,
            ), patch(
                "curriculum_builder.build.os.unlink",
                side_effect=recording_unlink,
            ):
                try:
                    build_site(
                        content,
                        templates,
                        static_root,
                        output,
                    )
                except BaseException as error:
                    captured = error

            self.assertIsInstance(captured, BuildCleanupError)
            self.assertFalse(nested_opened)
            self.assertEqual(unlink_calls, [])
            _assert_static_site(self, output)
            recovery = list(root.glob(".site.staging-*"))
            self.assertEqual(len(recovery), 1)
            self.assertEqual(
                (recovery[0] / "nested/sentinel.txt").read_text(),
                "old",
            )

    def test_cleanup_revalidates_each_opened_nested_directory(
        self,
    ) -> None:
        cases = ["identity", "device", "mode"]
        if hasattr(os, "geteuid"):
            cases.append("owner")
        for mutation in cases:
            with self.subTest(mutation=mutation), TemporaryDirectory() as path:
                root = Path(path).resolve(strict=True)
                nested = root / "nested"
                nested.mkdir()
                sentinel = nested / "sentinel.txt"
                sentinel.write_text("keep", encoding="utf-8")
                root_fd = os.open(
                    root,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                )
                original_open_directory = build_module._open_directory_at
                original_fstat = os.fstat
                original_unlink = os.unlink
                nested_fd: int | None = None
                unlink_calls: list[object] = []

                def recording_open(parent_fd: int, name: str) -> int:
                    nonlocal nested_fd
                    descriptor = original_open_directory(parent_fd, name)
                    if name == "nested":
                        nested_fd = descriptor
                    return descriptor

                def mutating_fstat(descriptor: int) -> os.stat_result:
                    current = original_fstat(descriptor)
                    if descriptor != nested_fd:
                        return current
                    fields = list(current)
                    if mutation == "identity":
                        fields[1] = current.st_ino + 1
                    elif mutation == "device":
                        fields[2] = current.st_dev + 1
                    elif mutation == "mode":
                        fields[0] = current.st_mode | stat.S_IWGRP
                    else:
                        fields[4] = current.st_uid + 1
                    return os.stat_result(fields)

                def recording_unlink(
                    target: object,
                    *args: object,
                    **kwargs: object,
                ) -> None:
                    unlink_calls.append(target)
                    original_unlink(  # type: ignore[arg-type]
                        target,
                        *args,
                        **kwargs,
                    )

                try:
                    with patch(
                        "curriculum_builder.build._open_directory_at",
                        side_effect=recording_open,
                    ), patch(
                        "curriculum_builder.build.os.fstat",
                        side_effect=mutating_fstat,
                    ), patch(
                        "curriculum_builder.build.os.unlink",
                        side_effect=recording_unlink,
                    ):
                        with self.assertRaises(RuntimeError):
                            build_module._clear_directory_fd(root_fd)
                finally:
                    os.close(root_fd)

                self.assertEqual(unlink_calls, [])
                self.assertEqual(sentinel.read_text(), "keep")

    def test_missing_input_never_partially_generates_or_damages_repository_site(
        self,
    ) -> None:
        repository_site = REPOSITORY_ROOT / "site"
        repository_before = (
            None
            if not os.path.lexists(repository_site)
            else (
                repository_site.lstat().st_dev,
                repository_site.lstat().st_ino,
            )
        )
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve(strict=True)
            output = root / "site"
            output.mkdir()
            (output / "sentinel.txt").write_text("previous", encoding="utf-8")

            with self.assertRaises(CurriculumValidationError):
                build_site(
                    root / "missing",
                    REPOSITORY_ROOT / "templates",
                    REPOSITORY_ROOT / "static",
                    output,
                )

            self.assertEqual((output / "sentinel.txt").read_text(), "previous")
            self.assertEqual(list(root.glob(".site.staging-*")), [])

        repository_after = (
            None
            if not os.path.lexists(repository_site)
            else (
                repository_site.lstat().st_dev,
                repository_site.lstat().st_ino,
            )
        )
        self.assertEqual(repository_after, repository_before)


if __name__ == "__main__":
    unittest.main()
