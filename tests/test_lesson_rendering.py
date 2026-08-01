from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import curriculum_builder.build as build_module
import curriculum_builder.lesson_rendering as lesson_rendering
from curriculum_builder.build import build_site
from curriculum_builder.errors import (
    CurriculumValidationError,
    IncompleteLessonReleaseError,
)
from curriculum_builder.html_safety import MAX_FRAGMENT_BYTES
from curriculum_builder.lesson_rendering import parse_lesson_body
from curriculum_builder.visualizations import LessonSectionRole


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COMPLETE = REPOSITORY_ROOT / "tests/fixtures/complete-lesson.json"
BODY = "".join(
    f'<section id="{section_id}"><h2>{section_id}</h2><p>本文</p></section>'
    for section_id in (
        "why",
        "mental-model",
        "worked-example",
        "tradeoffs",
        "knowledge-check",
        "sources-next",
    )
)


def _body_with_text(text: str) -> str:
    return BODY.replace("本文", text, 1)


class _SyntheticDirEntry:
    def __init__(self, name: str, node: os.stat_result) -> None:
        self.name = name
        self._node = node

    def stat(self, *, follow_symlinks: bool) -> os.stat_result:
        if follow_symlinks:
            raise AssertionError("synthetic entries must not follow symlinks")
        return self._node


class _GuardedScandir:
    def __init__(
        self,
        entries: Iterator[object],
        maximum_next_calls: int,
    ) -> None:
        self._entries = entries
        self._maximum_next_calls = maximum_next_calls
        self.next_calls = 0

    def __enter__(self) -> _GuardedScandir:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def __iter__(self) -> _GuardedScandir:
        return self

    def __next__(self) -> object:
        self.next_calls += 1
        if self.next_calls > self._maximum_next_calls:
            raise AssertionError("scandir was consumed past the rejecting entry")
        return next(self._entries)


def _synthetic_lesson_roots(
    node: os.stat_result,
) -> Iterator[_SyntheticDirEntry]:
    for ordinal in range(1, 31):
        yield _SyntheticDirEntry(
            f"core-{ordinal:02}-lesson-{ordinal}",
            node,
        )
    yield _SyntheticDirEntry("core-30-duplicate-suffix", node)
    while True:
        yield _SyntheticDirEntry("PRIVATE-UNBOUNDED-ROOT-CONTENT", node)


def _synthetic_lesson_files(
    node: os.stat_result,
) -> Iterator[_SyntheticDirEntry]:
    yield _SyntheticDirEntry("lesson.json", node)
    yield _SyntheticDirEntry("body.html", node)
    yield _SyntheticDirEntry("PRIVATE-EXTRA-LESSON-CONTENT", node)
    while True:
        yield _SyntheticDirEntry("PRIVATE-UNBOUNDED-LESSON-CONTENT", node)


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, dict[str, str | None]]] = []
        self.scripts = 0
        self.remote_dependencies: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = {name.casefold(): value for name, value in attrs}
        if tag.casefold() == "script":
            self.scripts += 1
        if tag.casefold() == "a" and values.get("href") is not None:
            self.links.append((values["href"] or "", values))
        for name in ("src", "action", "formaction"):
            value = values.get(name)
            if value and "://" in value:
                self.remote_dependencies.append(value)

    handle_startendtag = handle_starttag


def _complete_document(
    *,
    lesson_id: str = "core-01-systems-tradeoffs",
    title: str | None = None,
    prerequisites: list[str] | None = None,
    status: str = "complete",
) -> dict[str, object]:
    loaded = json.loads(COMPLETE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    loaded["id"] = lesson_id
    if title is not None:
        loaded["title"] = title
    if prerequisites is not None:
        loaded["prerequisiteIds"] = prerequisites
    loaded["status"] = status
    return loaded


@contextmanager
def _site_fixture():
    with TemporaryDirectory() as directory:
        root = Path(directory).resolve(strict=True)
        content = root / "content"
        templates = root / "templates"
        static_root = root / "static"
        # Rendering edge-case tests author their own absent/empty/one/multiple
        # lesson collections. Keep that fixture independent from the growing
        # canonical authored corpus while retaining real catalog and roadmap
        # inputs; canonical lesson publication is covered by the real build.
        shutil.copytree(
            REPOSITORY_ROOT / "content",
            content,
            ignore=shutil.ignore_patterns("lessons"),
        )
        shutil.copytree(REPOSITORY_ROOT / "templates", templates)
        shutil.copytree(REPOSITORY_ROOT / "static", static_root)
        yield root, content, templates, static_root


def _add_lesson(
    content: Path,
    document: dict[str, object],
    *,
    directory_name: str | None = None,
    body: bytes | str = BODY,
) -> Path:
    lesson_id = str(document["id"])
    directory = content / "lessons" / (directory_name or lesson_id)
    directory.mkdir(parents=True)
    (directory / "lesson.json").write_text(
        json.dumps(document, ensure_ascii=False),
        encoding="utf-8",
    )
    if isinstance(body, str):
        (directory / "body.html").write_text(body, encoding="utf-8")
    else:
        (directory / "body.html").write_bytes(body)
    return directory


class LessonRenderingTests(unittest.TestCase):
    def test_lesson_body_maps_generic_and_prefixed_sections_by_order(self) -> None:
        prefixed_sequences = (
            ("review-why", "review-mental-model", "worked-example",
             "review-tradeoffs", "review-knowledge-check", "review-sources-next"),
            ("team-why", "team-mental-model", "worked-example",
             "team-tradeoffs", "team-knowledge-check", "team-sources-next"),
            ("oss-why", "oss-mental-model", "worked-example",
             "oss-tradeoffs", "oss-knowledge-check", "oss-sources-next"),
            ("async-why", "async-mental-model", "worked-example",
             "async-tradeoffs", "async-check", "async-sources"),
            ("leadership-why", "leadership-mental-model", "worked-example",
             "leadership-tradeoffs", "leadership-check", "leadership-sources"),
        )
        fragments = (BODY,) + tuple(
            "".join(
                f'<section id="{section_id}"><h2>{section_id}</h2><p>本文</p></section>'
                for section_id in section_ids
            )
            for section_ids in prefixed_sequences
        )
        for fragment in fragments:
            with self.subTest(fragment=fragment[:40]):
                body = parse_lesson_body(fragment)
                self.assertEqual(
                    tuple(section.role for section in body.sections),
                    tuple(LessonSectionRole),
                )
                self.assertEqual(
                    "".join(section.html.value for section in body.sections),
                    fragment,
                )

    def test_lesson_body_rejects_invalid_top_level_section_contracts(self) -> None:
        sections = [
            '<section id="why"><h2>why</h2></section>',
            '<section id="mental-model"><h2>mental</h2></section>',
            '<section id="worked-example"><h2>worked</h2></section>',
            '<section id="tradeoffs"><h2>tradeoffs</h2></section>',
            '<section id="knowledge-check"><h2>check</h2></section>',
            '<section id="sources-next"><h2>sources</h2></section>',
        ]
        cases = {
            "missing": "".join(sections[:-1]),
            "reordered": "".join((sections[1], sections[0], *sections[2:])),
            "duplicated": "".join((*sections[:-1], sections[0])),
            "seventh": "".join((*sections, '<section id="extra"><h2>x</h2></section>')),
            "unclosed": "".join(sections)[:-10],
            "nested impersonation": sections[0].replace(
                "</section>",
                '<section id="mental-model"><h2>fake</h2></section></section>',
            ) + "".join(sections[1:]),
        }
        for label, fragment in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(CurriculumValidationError):
                    parse_lesson_body(fragment)

    def test_draft_lesson_has_a_typed_structural_completion_failure(
        self,
    ) -> None:
        with _site_fixture() as (root, content, templates, static_root):
            _add_lesson(
                content,
                _complete_document(status="draft"),
            )

            with self.assertRaisesRegex(
                IncompleteLessonReleaseError,
                "structurally complete curriculum release",
            ):
                build_site(
                    content,
                    templates,
                    static_root,
                    root / "site",
                )

    def test_build_emits_a_complete_semantic_printable_lesson(self) -> None:
        hostile_title = "システム思考 <script>alert(1)</script>"
        with _site_fixture() as (root, content, templates, static_root):
            lesson = _complete_document(title=hostile_title)
            _add_lesson(content, lesson)

            build_site(content, templates, static_root, root / "site")

            page = root / "site/lessons/core-01-systems-tradeoffs/index.html"
            html = page.read_text(encoding="utf-8")
            self.assertNotIn("<script>alert(1)</script>", html)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
            self.assertIn("<title>システム思考 &lt;script&gt;", html)
            for section_id in (
                "learning-objectives",
                "capability-progression",
                "practice-lab",
                "teach-back",
                "assessment",
                "transfer-task",
                "review-schedule",
                "rubric",
                "sources",
                "why",
                "mental-model",
                "worked-example",
                "tradeoffs",
                "knowledge-check",
                "sources-next",
            ):
                self.assertIn(f'id="{section_id}"', html)
            for level in ("recognize", "explain", "apply", "diagnose", "lead"):
                self.assertIn(f"<h3>{level}</h3>", html)
            self.assertIn("decision-record.md", html)
            self.assertIn("1日後", html)
            self.assertIn("7日後", html)
            self.assertIn("30日後", html)
            self.assertIn("90日後", html)
            self.assertIn("<caption>4段階の評価基準</caption>", html)
            self.assertIn("期待する証拠", html)

            parser = _LinkParser()
            parser.feed(html)
            external = [
                (href, attrs)
                for href, attrs in parser.links
                if href.startswith("https://")
            ]
            self.assertEqual(len(external), 2)
            self.assertTrue(
                all(attrs.get("rel") == "noreferrer" for _, attrs in external)
            )
            self.assertEqual(parser.scripts, 0)
            self.assertEqual(parser.remote_dependencies, [])

    def test_index_is_topological_and_empty_state_is_meaningful(self) -> None:
        with _site_fixture() as (root, content, templates, static_root):
            build_site(content, templates, static_root, root / "empty-site")
            empty = (root / "empty-site/lessons/index.html").read_text(
                encoding="utf-8"
            )
            self.assertIn("公開済みのコアレッスンはまだありません", empty)
            self.assertEqual(
                list((root / "empty-site/lessons").glob("*/index.html")),
                [],
            )

            second = _complete_document(
                lesson_id="core-02-algorithms-measurement",
                title="先に字句順になる依存レッスン",
                prerequisites=["core-01-systems-tradeoffs"],
            )
            first = _complete_document(title="前提レッスン")
            _add_lesson(content, second)
            _add_lesson(content, first)
            build_site(content, templates, static_root, root / "site")
            index = (root / "site/lessons/index.html").read_text(
                encoding="utf-8"
            )
            first_link = "core-01-systems-tradeoffs/index.html"
            second_link = "core-02-algorithms-measurement/index.html"
            self.assertLess(index.index(first_link), index.index(second_link))
            self.assertTrue(
                (root / f"site/lessons/{first['id']}/index.html").is_file()
            )
            self.assertTrue(
                (root / f"site/lessons/{second['id']}/index.html").is_file()
            )

    def test_generated_external_links_must_exactly_match_lesson_sources(
        self,
    ) -> None:
        with _site_fixture() as (root, content, templates, static_root):
            lesson = _complete_document()
            _add_lesson(content, lesson)
            output = root / "site"
            build_site(content, templates, static_root, output)
            artifacts = {
                PurePosixPath(path.relative_to(output).as_posix()):
                path.read_bytes()
                for path in output.rglob("*")
                if path.is_file()
            }
            lesson_path = PurePosixPath(
                "lessons/core-01-systems-tradeoffs/index.html"
            )
            source_urls = tuple(
                str(source["url"])
                for source in lesson["sources"]  # type: ignore[index]
            )
            page = artifacts[lesson_path].replace(
                b' rel="noreferrer"',
                b"",
                1,
            )
            artifacts[lesson_path] = page

            with self.assertRaisesRegex(
                CurriculumValidationError,
                "noreferrer|lesson sources",
            ):
                build_module._validate_site_artifacts(
                    artifacts,
                    frozenset(artifacts),
                    {lesson_path: source_urls},
                )

    def test_authored_body_and_lesson_collection_fail_closed(self) -> None:
        body_cases = {
            "script": "<script>alert(1)</script>",
            "event": '<p onclick="alert(1)">unsafe</p>',
            "style": '<p style="color:red">unsafe</p>',
            "external image": '<img src="https://example.com/x.png">',
            "external authored anchor": (
                '<p><a href="https://example.com/" rel="noreferrer">'
                "unsafe source bypass"
                "</a></p>"
            ),
            "invalid UTF-8": b"<p>\xff</p>",
            "oversized": b"x" * (MAX_FRAGMENT_BYTES + 1),
        }
        for label, body in body_cases.items():
            with self.subTest(label=label), _site_fixture() as (
                root,
                content,
                templates,
                static_root,
            ):
                _add_lesson(content, _complete_document(), body=body)
                with self.assertRaises(CurriculumValidationError):
                    build_site(content, templates, static_root, root / "site")

        mutations = {
            "draft": lambda raw: raw.__setitem__("status", "draft"),
            "unknown prerequisite": lambda raw: raw.__setitem__(
                "prerequisiteIds",
                ["core-02-algorithms-measurement"],
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), _site_fixture() as (
                root,
                content,
                templates,
                static_root,
            ):
                raw = _complete_document()
                mutate(raw)
                _add_lesson(content, raw)
                with self.assertRaises(CurriculumValidationError):
                    build_site(content, templates, static_root, root / "site")

    def test_discovery_rejects_the_thirty_first_entry_without_lookahead(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            node = Path(directory).resolve(strict=True).stat()
            guarded = _GuardedScandir(
                _synthetic_lesson_roots(node),
                maximum_next_calls=31,
            )
            with patch(
                "curriculum_builder.lesson_rendering.os.scandir",
                return_value=guarded,
            ):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    "maximum lesson count",
                ):
                    lesson_rendering._discover_lesson_names(12345)

            self.assertEqual(guarded.next_calls, 31)

    def test_lesson_directory_rejects_third_entry_without_lookahead(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            content = Path(directory).resolve(strict=True)
            lessons = content / "lessons"
            lesson_id = "core-01-systems-tradeoffs"
            lesson_directory = lessons / lesson_id
            lesson_directory.mkdir(parents=True)
            node = lesson_directory.stat()
            guarded = _GuardedScandir(
                _synthetic_lesson_files(node),
                maximum_next_calls=3,
            )
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            lessons_descriptor = os.open(lessons, flags)
            try:
                with patch(
                    "curriculum_builder.lesson_rendering.os.scandir",
                    return_value=guarded,
                ):
                    with self.assertRaises(Exception) as caught:
                        lesson_rendering._load_lesson_directory(
                            lessons_descriptor,
                            lesson_id,
                            lesson_rendering.MAX_LESSON_COLLECTION_INPUT_BYTES,
                        )
            finally:
                os.close(lessons_descriptor)

            self.assertIsInstance(
                caught.exception,
                CurriculumValidationError,
            )
            self.assertRegex(str(caught.exception), "pair")
            self.assertNotIn(
                "PRIVATE-EXTRA-LESSON-CONTENT",
                str(caught.exception),
            )
            self.assertEqual(guarded.next_calls, 3)

    def test_present_empty_lesson_root_is_an_authoring_empty_state(self) -> None:
        with _site_fixture() as (root, content, templates, static_root):
            (content / "lessons").mkdir()
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            content_descriptor = os.open(content, flags)
            try:
                collection = lesson_rendering.load_lessons_from_root(
                    content_descriptor
                )
            finally:
                os.close(content_descriptor)

            self.assertTrue(collection.directory_present)
            self.assertEqual(collection.lessons, ())

            output = root / "site"
            build_site(content, templates, static_root, output)
            index = (output / "lessons/index.html").read_text(
                encoding="utf-8"
            )
            self.assertIn("公開済みのコアレッスンはまだありません", index)
            self.assertEqual(
                list((output / "lessons").glob("*/index.html")),
                [],
            )

    def test_lesson_directory_discovery_errors_do_not_leak_input(self) -> None:
        class FailingNameEntry:
            @property
            def name(self) -> str:
                raise OSError("PRIVATE-ENTRY-NAME-CONTENT")

        def failing_name_entries() -> Iterator[object]:
            yield FailingNameEntry()

        with TemporaryDirectory() as directory:
            content = Path(directory).resolve(strict=True)
            lessons = content / "lessons"
            lesson_id = "core-01-systems-tradeoffs"
            (lessons / lesson_id).mkdir(parents=True)
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            lessons_descriptor = os.open(lessons, flags)
            cases = {
                "scandir": OSError("PRIVATE-SCANDIR-CONTENT"),
                "entry name": _GuardedScandir(
                    failing_name_entries(),
                    maximum_next_calls=1,
                ),
            }
            try:
                for label, effect in cases.items():
                    with self.subTest(label=label):
                        patcher = (
                            patch(
                                "curriculum_builder.lesson_rendering.os.scandir",
                                side_effect=effect,
                            )
                            if isinstance(effect, OSError)
                            else patch(
                                "curriculum_builder.lesson_rendering.os.scandir",
                                return_value=effect,
                            )
                        )
                        with patcher:
                            with self.assertRaisesRegex(
                                CurriculumValidationError,
                                "cannot be discovered safely",
                            ) as caught:
                                lesson_rendering._load_lesson_directory(
                                    lessons_descriptor,
                                    lesson_id,
                                    lesson_rendering.MAX_LESSON_COLLECTION_INPUT_BYTES,
                                )
                        self.assertNotIn("PRIVATE-", str(caught.exception))
            finally:
                os.close(lessons_descriptor)

    def test_duplicate_numeric_ordinal_fails_before_publication(self) -> None:
        with _site_fixture() as (root, content, templates, static_root):
            first = _complete_document()
            second = _complete_document(
                lesson_id="core-01-alternative-suffix",
                title="同一ordinalの別教材",
            )
            _add_lesson(content, first)
            _add_lesson(content, second)
            output = root / "site"
            output.mkdir()
            (output / "sentinel.txt").write_text("old", encoding="utf-8")

            with self.assertRaisesRegex(
                CurriculumValidationError,
                "duplicate lesson ordinal",
            ):
                build_site(content, templates, static_root, output)

            self.assertEqual((output / "sentinel.txt").read_text(), "old")
            self.assertEqual(list(root.glob(".site.staging-*")), [])

    def test_collection_input_byte_limit_accumulates_across_lessons(
        self,
    ) -> None:
        with _site_fixture() as (root, content, templates, static_root):
            first = _add_lesson(
                content,
                _complete_document(title="PRIVATE-FIRST-TITLE"),
                body=_body_with_text("PRIVATE-FIRST-BODY"),
            )
            second = _add_lesson(
                content,
                _complete_document(
                    lesson_id="core-02-aggregate-boundary",
                    title="PRIVATE-SECOND-TITLE",
                ),
                body=_body_with_text("PRIVATE-SECOND-BODY"),
            )
            lesson_bytes = tuple(
                sum(
                    (directory / name).stat().st_size
                    for name in ("lesson.json", "body.html")
                )
                for directory in (first, second)
            )
            aggregate_bytes = sum(lesson_bytes)
            one_byte_short = aggregate_bytes - 1
            self.assertTrue(
                all(size < one_byte_short for size in lesson_bytes)
            )

            exact_output = root / "exact-site"
            with patch.object(
                lesson_rendering,
                "MAX_LESSON_COLLECTION_INPUT_BYTES",
                aggregate_bytes,
            ):
                build_site(
                    content,
                    templates,
                    static_root,
                    exact_output,
                )
            self.assertEqual(
                len(
                    list(
                        (exact_output / "lessons").glob("*/index.html")
                    )
                ),
                2,
            )

            output = root / "site"
            output.mkdir()
            (output / "sentinel.txt").write_text("old", encoding="utf-8")
            with patch.object(
                lesson_rendering,
                "MAX_LESSON_COLLECTION_INPUT_BYTES",
                one_byte_short,
            ):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    "collection exceeds maximum input byte count",
                ) as caught:
                    build_site(content, templates, static_root, output)

            self.assertNotIn("PRIVATE-FIRST", str(caught.exception))
            self.assertNotIn("PRIVATE-SECOND", str(caught.exception))
            self.assertEqual((output / "sentinel.txt").read_text(), "old")
            self.assertEqual(list(root.glob(".site.staging-*")), [])

    def test_generated_lesson_artifact_byte_limit_is_aggregate(self) -> None:
        with _site_fixture() as (root, content, templates, static_root):
            lesson_id = "core-01-systems-tradeoffs"
            _add_lesson(
                content,
                _complete_document(title="PRIVATE-ARTIFACT-TITLE"),
                body=_body_with_text("PRIVATE-ARTIFACT-BODY"),
            )
            baseline = root / "baseline"
            build_site(content, templates, static_root, baseline)
            artifact_sizes = {
                PurePosixPath(path.relative_to(baseline).as_posix()):
                path.stat().st_size
                for path in (baseline / "lessons").rglob("*")
                if path.is_file()
            }
            lesson_path = PurePosixPath(
                f"lessons/{lesson_id}/index.html"
            )
            self.assertEqual(
                frozenset(artifact_sizes),
                frozenset(
                    {
                        PurePosixPath("lessons/index.html"),
                        lesson_path,
                    }
                ),
            )
            aggregate_bytes = sum(artifact_sizes.values())
            one_byte_short = aggregate_bytes - 1
            self.assertTrue(
                all(size <= one_byte_short for size in artifact_sizes.values())
            )

            exact_output = root / "exact-site"
            with patch.object(
                lesson_rendering,
                "MAX_LESSON_ARTIFACT_BYTES",
                aggregate_bytes,
            ):
                try:
                    build_site(
                        content,
                        templates,
                        static_root,
                        exact_output,
                    )
                except CurriculumValidationError:
                    self.fail(
                        "exact aggregate lesson artifact limit must succeed"
                    )
            self.assertTrue(
                (exact_output / Path(lesson_path.as_posix())).is_file()
            )
            self.assertEqual(
                sum(
                    path.stat().st_size
                    for path in (exact_output / "lessons").rglob("*")
                    if path.is_file()
                ),
                aggregate_bytes,
            )

            output = root / "site"
            output.mkdir()
            (output / "sentinel.txt").write_text("old", encoding="utf-8")
            with patch.object(
                lesson_rendering,
                "MAX_LESSON_ARTIFACT_BYTES",
                one_byte_short,
            ):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    "lesson artifacts exceed maximum byte count",
                ) as caught:
                    build_site(content, templates, static_root, output)

            self.assertNotIn("PRIVATE-", str(caught.exception))
            self.assertIsNone(caught.exception.__cause__)
            self.assertEqual((output / "sentinel.txt").read_text(), "old")
            self.assertEqual(list(root.glob(".site.staging-*")), [])

    def test_default_budgets_fit_thirty_complete_lessons(self) -> None:
        with _site_fixture() as (root, content, templates, static_root):
            for ordinal in range(1, 31):
                _add_lesson(
                    content,
                    _complete_document(
                        lesson_id=f"core-{ordinal:02}-lesson-{ordinal}",
                        title=f"教材 {ordinal}",
                    ),
                )

            output = root / "site"
            build_site(content, templates, static_root, output)

            lesson_pages = tuple(
                path
                for path in (output / "lessons").glob("*/index.html")
                if path.is_file()
            )
            input_bytes = sum(
                path.stat().st_size
                for path in (content / "lessons").rglob("*")
                if path.is_file()
            )
            artifact_bytes = sum(
                path.stat().st_size
                for path in (output / "lessons").rglob("*")
                if path.is_file()
            )
            self.assertEqual(len(lesson_pages), 30)
            self.assertLessEqual(
                input_bytes,
                lesson_rendering.MAX_LESSON_COLLECTION_INPUT_BYTES,
            )
            self.assertLessEqual(
                artifact_bytes,
                lesson_rendering.MAX_LESSON_ARTIFACT_BYTES,
            )

    def test_lesson_close_faults_preserve_primary_and_close_outer_fds(
        self,
    ) -> None:
        for failing_role, required_outer_roles in {
            "body": ("lesson directory", "lessons root", "content root"),
            "lesson directory": ("lessons root", "content root"),
            "lessons root": ("content root",),
        }.items():
            with self.subTest(failing_role=failing_role), _site_fixture() as (
                root,
                content,
                templates,
                static_root,
            ):
                lesson_id = "core-01-systems-tradeoffs"
                _add_lesson(
                    content,
                    _complete_document(title="PRIVATE-TITLE-CONTENT"),
                    body=_body_with_text("PRIVATE-BODY-CONTENT"),
                )
                real_open = os.open
                real_close = os.close
                descriptors: dict[str, int] = {}
                closed: list[int] = []
                close_failed = False

                def recording_open(
                    target: object,
                    flags: int,
                    *args: object,
                    **kwargs: object,
                ) -> int:
                    descriptor = real_open(target, flags, *args, **kwargs)
                    spelling = os.fspath(target)  # type: ignore[arg-type]
                    if spelling == "body.html":
                        descriptors["body"] = descriptor
                    elif spelling == lesson_id:
                        descriptors["lesson directory"] = descriptor
                    elif spelling == "lessons":
                        descriptors["lessons root"] = descriptor
                    elif Path(spelling) == content:
                        descriptors["content root"] = descriptor
                    return descriptor

                def failing_close(descriptor: int) -> None:
                    nonlocal close_failed
                    closed.append(descriptor)
                    real_close(descriptor)
                    if (
                        descriptor == descriptors.get(failing_role)
                        and not close_failed
                    ):
                        close_failed = True
                        raise OSError(
                            "PRIVATE-BODY-CONTENT close implementation detail"
                        )

                with (
                    patch(
                        "curriculum_builder.lesson_rendering.os.open",
                        side_effect=recording_open,
                    ),
                    patch(
                        "curriculum_builder.lesson_rendering.os.close",
                        side_effect=failing_close,
                    ),
                ):
                    with self.assertRaises(Exception) as caught:
                        build_site(
                            content,
                            templates,
                            static_root,
                            root / "site",
                        )

                self.assertTrue(close_failed)
                self.assertIsInstance(
                    caught.exception,
                    CurriculumValidationError,
                )
                self.assertRegex(
                    str(caught.exception),
                    "descriptor close failed",
                )
                for role in required_outer_roles:
                    self.assertIn(descriptors[role], closed)
                rendered_error = "\n".join(
                    (
                        str(caught.exception),
                        *getattr(caught.exception, "__notes__", ()),
                    )
                )
                self.assertNotIn("PRIVATE-TITLE-CONTENT", rendered_error)
                self.assertNotIn("PRIVATE-BODY-CONTENT", rendered_error)

    def test_read_error_remains_primary_when_body_close_also_fails(self) -> None:
        with _site_fixture() as (root, content, templates, static_root):
            _add_lesson(
                content,
                _complete_document(title="PRIVATE-TITLE-CONTENT"),
                body="<p>PRIVATE-BODY-CONTENT</p>",
            )
            real_open = os.open
            real_read = os.read
            real_close = os.close
            body_descriptor: int | None = None
            outer_descriptors: list[int] = []
            closed: list[int] = []

            def recording_open(
                target: object,
                flags: int,
                *args: object,
                **kwargs: object,
            ) -> int:
                nonlocal body_descriptor
                descriptor = real_open(target, flags, *args, **kwargs)
                spelling = os.fspath(target)  # type: ignore[arg-type]
                if spelling == "body.html":
                    body_descriptor = descriptor
                elif spelling in {
                    "core-01-systems-tradeoffs",
                    "lessons",
                }:
                    outer_descriptors.append(descriptor)
                return descriptor

            def failing_read(descriptor: int, maximum: int) -> bytes:
                if descriptor == body_descriptor:
                    raise OSError(
                        "PRIVATE-BODY-CONTENT read implementation detail"
                    )
                return real_read(descriptor, maximum)

            def failing_close(descriptor: int) -> None:
                closed.append(descriptor)
                real_close(descriptor)
                if descriptor == body_descriptor:
                    raise OSError(
                        "PRIVATE-BODY-CONTENT close implementation detail"
                    )

            with (
                patch(
                    "curriculum_builder.lesson_rendering.os.open",
                    side_effect=recording_open,
                ),
                patch(
                    "curriculum_builder.lesson_rendering.os.read",
                    side_effect=failing_read,
                ),
                patch(
                    "curriculum_builder.lesson_rendering.os.close",
                    side_effect=failing_close,
                ),
            ):
                with self.assertRaises(Exception) as caught:
                    build_site(
                        content,
                        templates,
                        static_root,
                        root / "site",
                    )

            self.assertTrue(outer_descriptors)
            self.assertTrue(all(item in closed for item in outer_descriptors))
            self.assertIsInstance(
                caught.exception,
                CurriculumValidationError,
            )
            self.assertRegex(
                str(caught.exception),
                "cannot be read safely",
            )
            rendered_error = "\n".join(
                (
                    str(caught.exception),
                    *getattr(caught.exception, "__notes__", ()),
                )
            )
            self.assertIn(
                "descriptor also failed to close",
                rendered_error,
            )
            self.assertNotIn("PRIVATE-TITLE-CONTENT", rendered_error)
            self.assertNotIn("PRIVATE-BODY-CONTENT", rendered_error)

    def test_cycle_directory_mismatch_missing_pair_and_unsafe_nodes_fail_closed(
        self,
    ) -> None:
        with _site_fixture() as (root, content, templates, static_root):
            first = _complete_document(
                prerequisites=["core-02-algorithms-measurement"]
            )
            second = _complete_document(
                lesson_id="core-02-algorithms-measurement",
                prerequisites=["core-01-systems-tradeoffs"],
            )
            _add_lesson(content, first)
            _add_lesson(content, second)
            with self.assertRaisesRegex(CurriculumValidationError, "cycle"):
                build_site(content, templates, static_root, root / "site")

        with _site_fixture() as (root, content, templates, static_root):
            _add_lesson(
                content,
                _complete_document(),
                directory_name="core-02-algorithms-measurement",
            )
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "directory name",
            ):
                build_site(content, templates, static_root, root / "site")

        with _site_fixture() as (root, content, templates, static_root):
            directory = _add_lesson(content, _complete_document())
            (directory / "body.html").unlink()
            with self.assertRaisesRegex(CurriculumValidationError, "pair"):
                build_site(content, templates, static_root, root / "site")

        with _site_fixture() as (root, content, templates, static_root):
            directory = content / "lessons/core-01-systems-tradeoffs"
            directory.mkdir(parents=True)
            (directory / "lesson.json").symlink_to(COMPLETE)
            (directory / "body.html").write_text(BODY, encoding="utf-8")
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "regular file|symbolic",
            ):
                build_site(content, templates, static_root, root / "site")

        with _site_fixture() as (root, content, templates, static_root):
            directory = _add_lesson(content, _complete_document())
            (directory / "body.html").unlink()
            os.mkfifo(directory / "body.html")
            with self.assertRaisesRegex(
                CurriculumValidationError,
                "regular file",
            ):
                build_site(content, templates, static_root, root / "site")

    def test_lesson_read_race_rejects_and_preserves_previous_output(self) -> None:
        with _site_fixture() as (root, content, templates, static_root):
            directory = _add_lesson(content, _complete_document())
            output = root / "site"
            output.mkdir()
            (output / "sentinel.txt").write_text("old", encoding="utf-8")
            original_read = lesson_rendering._read_regular_file_at
            changed = False

            def racing_read(
                descriptor: int,
                name: str,
                maximum_bytes: int,
                label: str,
            ) -> tuple[bytes, tuple[int, int, int, int, int, int]]:
                nonlocal changed
                result = original_read(
                    descriptor,
                    name,
                    maximum_bytes,
                    label,
                )
                if not changed and name == "body.html":
                    changed = True
                    (directory / "body.html").write_text(
                        "<p>changed</p>",
                        encoding="utf-8",
                    )
                return result

            with patch(
                "curriculum_builder.lesson_rendering._read_regular_file_at",
                side_effect=racing_read,
            ):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    "changed during read",
                ):
                    build_site(content, templates, static_root, output)

            self.assertTrue(changed)
            self.assertEqual((output / "sentinel.txt").read_text(), "old")
            self.assertEqual(list(root.glob(".site.staging-*")), [])

    def test_missing_lesson_root_appearance_is_a_snapshot_change(self) -> None:
        with _site_fixture() as (root, content, templates, static_root):
            output = root / "site"
            output.mkdir()
            (output / "sentinel.txt").write_text("old", encoding="utf-8")
            original_render = build_module._render_artifacts

            def racing_render(*args: object) -> dict[PurePosixPath, bytes]:
                artifacts = original_render(*args)  # type: ignore[arg-type]
                (content / "lessons").mkdir()
                return artifacts

            with patch(
                "curriculum_builder.build._render_artifacts",
                side_effect=racing_render,
            ):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    "lessons changed",
                ):
                    build_site(content, templates, static_root, output)

            self.assertEqual((output / "sentinel.txt").read_text(), "old")
            self.assertEqual(list(root.glob(".site.staging-*")), [])

    def test_nested_lesson_artifacts_have_deterministic_safe_metadata(self) -> None:
        with _site_fixture() as (root, content, templates, static_root):
            _add_lesson(content, _complete_document())
            output = root / "site"
            build_site(content, templates, static_root, output)

            expected = {
                Path("index.html"),
                Path("styles.css"),
                Path("catalog/index.html"),
                Path("capstones/index.html"),
                Path("competencies/index.html"),
                Path("roadmap/index.html"),
                Path("lessons/index.html"),
                Path(
                    "lessons/core-01-systems-tradeoffs/index.html"
                ),
            }
            actual = {
                path.relative_to(output)
                for path in output.rglob("*")
                if path.is_file()
            }
            self.assertEqual(actual, expected)
            first = {
                path.relative_to(output): (
                    path.read_bytes(),
                    stat.S_IMODE(path.stat().st_mode),
                    path.stat().st_mtime_ns,
                )
                for path in output.rglob("*")
                if path.is_file()
            }
            build_site(content, templates, static_root, output)
            second = {
                path.relative_to(output): (
                    path.read_bytes(),
                    stat.S_IMODE(path.stat().st_mode),
                    path.stat().st_mtime_ns,
                )
                for path in output.rglob("*")
                if path.is_file()
            }
            self.assertEqual(first, second)
            self.assertEqual(
                {mode for _, mode, _ in first.values()},
                {0o644},
            )
            self.assertEqual(
                {mtime for _, _, mtime in first.values()},
                {0},
            )

    def test_generic_staging_creates_safe_arbitrary_nested_paths(self) -> None:
        with TemporaryDirectory() as directory:
            staging = Path(directory).resolve(strict=True) / "staging"
            staging.mkdir()
            descriptor = os.open(
                staging,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
            try:
                build_module._populate_staging(
                    descriptor,
                    {
                        PurePosixPath("alpha/beta/gamma.txt"): b"nested",
                        PurePosixPath("root.txt"): b"root",
                    },
                )
            finally:
                os.close(descriptor)

            self.assertEqual(
                (staging / "alpha/beta/gamma.txt").read_bytes(),
                b"nested",
            )
            for path in (staging, staging / "alpha", staging / "alpha/beta"):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755)
                self.assertEqual(path.stat().st_mtime_ns, 0)

        unsafe_artifacts = (
            {PurePosixPath("../escape.txt"): b"unsafe"},
            {
                PurePosixPath("collision"): b"file",
                PurePosixPath("collision/nested.txt"): b"nested",
            },
        )
        for artifacts in unsafe_artifacts:
            with self.subTest(paths=tuple(artifacts)):
                with self.assertRaises(CurriculumValidationError):
                    build_module._validated_artifact_directories(artifacts)

    def test_nested_staging_failure_keeps_previous_output_atomic(self) -> None:
        with _site_fixture() as (root, content, templates, static_root):
            _add_lesson(content, _complete_document())
            output = root / "site"
            output.mkdir()
            (output / "sentinel.txt").write_text("old", encoding="utf-8")
            original_write = build_module._write_file_at

            def failing_lesson_write(
                directory_fd: int,
                name: str,
                raw: bytes,
            ) -> None:
                if b'<article class="lesson reading">' in raw:
                    raise OSError("nested lesson write failed")
                original_write(directory_fd, name, raw)

            with patch(
                "curriculum_builder.build._write_file_at",
                side_effect=failing_lesson_write,
            ):
                with self.assertRaisesRegex(
                    OSError,
                    "nested lesson write failed",
                ):
                    build_site(content, templates, static_root, output)

            self.assertEqual((output / "sentinel.txt").read_text(), "old")
            self.assertEqual(list(root.glob(".site.staging-*")), [])


if __name__ == "__main__":
    unittest.main()
