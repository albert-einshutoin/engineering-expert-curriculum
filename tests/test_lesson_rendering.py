from __future__ import annotations

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
from curriculum_builder.errors import CurriculumValidationError
from curriculum_builder.html_safety import MAX_FRAGMENT_BYTES


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COMPLETE = REPOSITORY_ROOT / "tests/fixtures/complete-lesson.json"
BODY = (
    '<section id="mechanism">'
    "<h2>判断を構成する機構</h2>"
    "<p>制約、証拠、再評価条件を結び付けます。</p>"
    "</section>"
)


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
        shutil.copytree(REPOSITORY_ROOT / "content", content)
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
                "mechanism",
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
