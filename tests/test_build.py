from __future__ import annotations

from contextlib import contextmanager
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from curriculum_builder.build import (
    BuildCleanupError,
    BuildPostCommitError,
    BuildPublicationDurabilityError,
    MAX_ROADMAP_BYTES,
    MAX_STYLESHEET_BYTES,
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
        root = Path(directory).resolve(strict=True)
        content = root / "content"
        templates = root / "templates"
        static_root = root / "static"
        content.mkdir()
        shutil.copytree(REPOSITORY_ROOT / "templates", templates)
        static_root.mkdir()
        (static_root / "styles.css").write_bytes(
            (REPOSITORY_ROOT / "static" / "styles.css").read_bytes()
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
) -> dict[Path, bytes]:
    expected = {
        Path("index.html"),
        Path("styles.css"),
        Path("catalog/index.html"),
        Path("roadmap/index.html"),
        Path("lessons/index.html"),
    }
    actual = {
        path.relative_to(output)
        for path in output.rglob("*")
        if path.is_file()
    }
    test.assertEqual(actual, expected)
    test.assertEqual(list(output.rglob("*.js")), [])

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
        ids_by_page[relative] = parser.ids
        links_by_page[relative] = parser.links

    for page, links in links_by_page.items():
        for link in links:
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
    def test_build_is_complete_static_file_relative_and_keeps_all_items(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory).resolve(strict=True) / "site"
            build_site(
                content_root=REPOSITORY_ROOT / "content",
                template_root=REPOSITORY_ROOT / "templates",
                static_root=REPOSITORY_ROOT / "static",
                output_root=output,
            )

            _assert_static_site(self, output)
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
            positions: list[int] = []
            for title, prerequisite in (
                ("Think", "なし"),
                ("Build", "Think"),
                ("Run", "Build"),
                ("Lead", "Run"),
            ):
                marker = (
                    f"<h2>{title}</h2>"
                    '<p class="prerequisite-text">'
                    f"<strong>前提:</strong> {prerequisite}</p>"
                )
                self.assertIn(marker, roadmap)
                positions.append(roadmap.index(marker))
            self.assertEqual(positions, sorted(positions))

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
            first_bytes = _assert_static_site(self, output)
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

            second_bytes = _assert_static_site(self, output)
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
            _assert_static_site(self, output)


class BuildInputValidationTests(unittest.TestCase):
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


class BuildPublicationTests(unittest.TestCase):
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
