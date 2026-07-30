from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
import os
import shutil
import stat
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

import curriculum_builder.render as render_module
from curriculum_builder.errors import CurriculumValidationError
from curriculum_builder.html_safety import SafeHtml, validate_fragment
from curriculum_builder.render import (
    MAX_PLACEHOLDERS,
    MAX_STRUCTURED_TEXT_CHARS,
    MAX_TEMPLATE_BYTES,
    Renderer,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = REPOSITORY_ROOT / "templates"


class ExactString(str):
    pass


class EntriesMapping(Mapping[object, object]):
    def __init__(self, entries: tuple[tuple[object, object], ...]) -> None:
        self.entries = entries
        self.items_calls = 0

    def __getitem__(self, key: object) -> object:
        raise AssertionError("renderer must use the mapping snapshot")

    def __iter__(self) -> Iterator[object]:
        raise AssertionError("renderer must use items() exactly once")

    def __len__(self) -> int:
        return len(self.entries)

    def items(self) -> tuple[tuple[object, object], ...]:
        self.items_calls += 1
        return self.entries


class LargeEntriesMapping(Mapping[object, object]):
    def __init__(self) -> None:
        self.items_calls = 0
        self.consumed = 0

    def __getitem__(self, key: object) -> object:
        raise AssertionError("renderer must use the mapping snapshot")

    def __iter__(self) -> Iterator[object]:
        raise AssertionError("renderer must use items() exactly once")

    def __len__(self) -> int:
        return 10_000

    def items(self) -> Iterator[tuple[str, str]]:
        self.items_calls += 1
        for index in range(10_000):
            self.consumed += 1
            yield f"value{index}", "x"


class RaisingItemsMapping(Mapping[object, object]):
    def __getitem__(self, key: object) -> object:
        raise AssertionError("renderer must not use __getitem__")

    def __iter__(self) -> Iterator[object]:
        raise AssertionError("renderer must not use __iter__")

    def __len__(self) -> int:
        return 1

    def items(self) -> object:
        raise RuntimeError("sensitive-items-marker")


class RaisingIterationMapping(RaisingItemsMapping):
    def items(self) -> Iterator[tuple[str, str]]:
        def entries() -> Iterator[tuple[str, str]]:
            raise RuntimeError("sensitive-iteration-marker")
            yield "unused", "unused"

        return entries()


class RaisingEntryMapping(RaisingItemsMapping):
    def items(self) -> tuple[object, ...]:
        class RaisingEntry:
            def __iter__(self) -> Iterator[object]:
                raise RuntimeError("sensitive-entry-marker")

        return (RaisingEntry(),)


class RendererTests(unittest.TestCase):
    def setUp(self) -> None:
        self.renderer = Renderer(TEMPLATE_ROOT)

    @contextmanager
    def temporary_templates(self) -> Iterator[Path]:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copyfile(TEMPLATE_ROOT / "base.html", root / "base.html")
            yield root

    def renderer_with_fragment(self, name: str, source: str) -> Renderer:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        shutil.copyfile(TEMPLATE_ROOT / "base.html", root / "base.html")
        (root / name).write_text(source, encoding="utf-8")
        return Renderer(root)

    def assert_validation_error(
        self,
        message: str,
        callable_object: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        with self.assertRaisesRegex(
            CurriculumValidationError,
            f"^{message}$",
        ):
            callable_object(*args, **kwargs)  # type: ignore[operator]

    def test_escapes_structured_values_but_keeps_revalidated_content(self) -> None:
        html = self.renderer.page(
            output_path=Path("lessons/example/index.html"),
            title="<判断>",
            description='比較 & "選択"',
            content=validate_fragment("<section><h2>本文</h2></section>"),
        )

        self.assertIn("&lt;判断&gt;", html)
        self.assertIn("比較 &amp; &quot;選択&quot;", html)
        self.assertIn("<section><h2>本文</h2></section>", html)
        self.assertNotIn("<判断>", html)

    def test_uses_file_compatible_relative_links_at_every_depth(self) -> None:
        cases = (
            (Path("index.html"), ""),
            (Path("catalog/index.html"), "../"),
            (Path("lessons/example/index.html"), "../../"),
        )
        for output_path, root in cases:
            with self.subTest(output_path=output_path):
                html = self.renderer.page(
                    output_path=output_path,
                    title="例",
                    description="説明",
                    content=validate_fragment("<p>本文</p>"),
                )
                for target in (
                    "styles.css",
                    "index.html",
                    "roadmap/index.html",
                    "lessons/index.html",
                    "catalog/index.html",
                ):
                    self.assertIn(f'href="{root}{target}"', html)
                self.assertNotIn('href="/', html)

    def test_renders_semantic_japanese_document_without_scripts(self) -> None:
        html = self.renderer.page(
            output_path=Path("index.html"),
            title="ホーム",
            description="説明",
            content=self.renderer.fragment(
                "index.html",
                text_values={},
                html_values={},
            ),
        )

        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn('<html lang="ja">', html)
        self.assertIn('class="skip-link" href="#main"', html)
        self.assertIn('<nav aria-label="主要ナビゲーション">', html)
        self.assertIn("script-src 'none'", html)
        self.assertNotIn("<script", html.casefold())

    def test_fragment_escapes_text_and_accepts_exact_safe_html(self) -> None:
        fragment = self.renderer.fragment(
            "catalog.html",
            text_values={"count": "<1140>"},
            html_values={
                "sections": validate_fragment("<section>安全</section>")
            },
        )

        self.assertIn("&lt;1140&gt;", fragment.value)
        self.assertIn("<section>安全</section>", fragment.value)

    def test_fragment_supports_braced_placeholders_in_safe_contexts(self) -> None:
        renderer = self.renderer_with_fragment(
            "braced.html",
            '<section class="${kind}"><h2>${heading}</h2>${body}</section>',
        )

        fragment = renderer.fragment(
            "braced.html",
            text_values={"kind": "reading", "heading": "<判断>"},
            html_values={"body": validate_fragment("<p>本文</p>")},
        )

        self.assertEqual(
            fragment.value,
            '<section class="reading"><h2>&lt;判断&gt;</h2><p>本文</p></section>',
        )

    def test_rejects_forged_subclasses_and_revalidates_exact_safe_html(self) -> None:
        class ForgedSafeHtml(SafeHtml):
            pass

        forged = object.__new__(ForgedSafeHtml)
        object.__setattr__(forged, "value", "<p>forged</p>")
        self.assert_validation_error(
            "raw HTML requires exact SafeHtml",
            self.renderer.page,
            output_path=Path("index.html"),
            title="例",
            description="説明",
            content=forged,
        )
        self.assert_validation_error(
            "raw HTML requires exact SafeHtml",
            self.renderer.fragment,
            "catalog.html",
            text_values={"count": "1"},
            html_values={"sections": forged},
        )

        modified = validate_fragment("<p>valid</p>")
        object.__setattr__(modified, "value", "<script>changed</script>")
        self.assert_validation_error(
            "disallowed HTML element",
            self.renderer.page,
            output_path=Path("index.html"),
            title="例",
            description="説明",
            content=modified,
        )
        deleted = validate_fragment("<p>valid</p>")
        object.__delattr__(deleted, "value")
        self.assert_validation_error(
            "raw HTML could not be revalidated",
            self.renderer.page,
            output_path=Path("index.html"),
            title="例",
            description="説明",
            content=deleted,
        )

    def test_rejects_raw_placeholders_outside_element_body_context(self) -> None:
        cases = (
            ("tag.html", "<$sections>x</$sections>", "<p>x</p>"),
            (
                "quoted.html",
                '<p class="$sections">x</p>',
                "<strong>x</strong>",
            ),
            (
                "unquoted.html",
                "<p class=$sections>x</p>",
                "<strong>x</strong>",
            ),
            (
                "comment.html",
                "<!-- $sections --><p>x</p>",
                "--><p>x</p>",
            ),
            (
                "script.html",
                "<script>$sections</script>",
                "alert(1)",
            ),
            (
                "style.html",
                "<style>$sections</style>",
                "body{color:red}",
            ),
        )
        for name, source, safe_body_value in cases:
            with self.subTest(name=name):
                renderer = self.renderer_with_fragment(name, source)
                self.assert_validation_error(
                    "raw HTML placeholder requires element-body context",
                    renderer.fragment,
                    name,
                    text_values={},
                    html_values={
                        "sections": validate_fragment(safe_body_value)
                    },
                )

    def test_rejects_duplicate_raw_placeholder_even_in_body_context(self) -> None:
        renderer = self.renderer_with_fragment(
            "duplicate.html",
            "<section>$sections</section><aside>$sections</aside>",
        )

        self.assert_validation_error(
            "fragment placeholders must each occur exactly once",
            renderer.fragment,
            "duplicate.html",
            text_values={},
            html_values={"sections": validate_fragment("<p>x</p>")},
        )

    def test_allows_text_only_in_element_text_or_quoted_attributes(self) -> None:
        renderer = self.renderer_with_fragment(
            "text.html",
            '<p class="$kind">${body}</p>',
        )

        fragment = renderer.fragment(
            "text.html",
            text_values={"kind": "reading", "body": '<"&>'},
            html_values={},
        )

        self.assertEqual(
            fragment.value,
            '<p class="reading">&lt;&quot;&amp;&gt;</p>',
        )

    def test_rejects_text_placeholders_in_unsafe_parser_contexts(self) -> None:
        cases = (
            ("tag.html", "<$value>x</$value>"),
            ("unquoted.html", "<p class=$value>x</p>"),
            ("comment.html", "<!-- $value --><p>x</p>"),
            ("script.html", "<script>$value</script>"),
            ("style.html", "<style>$value</style>"),
        )
        for name, source in cases:
            with self.subTest(name=name):
                renderer = self.renderer_with_fragment(name, source)
                self.assert_validation_error(
                    "text placeholder requires element-text or "
                    "quoted-attribute context",
                    renderer.fragment,
                    name,
                    text_values={"value": "reading"},
                    html_values={},
                )

    def test_rejects_incomplete_or_mismatched_template_markup_early(
        self,
    ) -> None:
        cases = (
            ("unclosed-tag.html", "<section><p>x</p>"),
            ("unclosed-comment.html", "<p>x</p><!--"),
            ("unclosed-double-quote.html", '<p class="reading'),
            ("unclosed-single-quote.html", "<p class='reading"),
            ("unclosed-script.html", "<script>x"),
            ("unclosed-style.html", "<style>x"),
            ("stray.html", "</p><p>x</p>"),
            ("mismatch.html", "<section><p>x</section></p>"),
        )
        for name, source in cases:
            with self.subTest(name=name):
                renderer = self.renderer_with_fragment(name, source)
                self.assert_validation_error(
                    "template markup is invalid",
                    renderer.fragment,
                    name,
                    text_values={},
                    html_values={},
                )

    def test_stops_lexing_at_first_deep_mismatched_closing_tag(self) -> None:
        depth = 2_048
        source = "<div>" * depth + "</span>" * depth

        with patch.object(
            render_module,
            "_tag_details",
            wraps=render_module._tag_details,
        ) as tag_details:
            self.assert_validation_error(
                "template markup is invalid",
                render_module._placeholder_contexts,
                source,
                (),
            )

        self.assertEqual(tag_details.call_count, depth + 1)

    def test_rejects_missing_extra_overlapping_and_invalid_placeholders(self) -> None:
        missing = self.renderer_with_fragment("missing.html", "<p>$value</p>")
        extra = self.renderer_with_fragment("extra.html", "<p>fixed</p>")
        invalid = self.renderer_with_fragment("invalid.html", "<p>$</p>")

        self.assert_validation_error(
            "template placeholders do not match provided values",
            missing.fragment,
            "missing.html",
            text_values={},
            html_values={},
        )
        self.assert_validation_error(
            "template placeholders do not match provided values",
            extra.fragment,
            "extra.html",
            text_values={"value": "x"},
            html_values={},
        )
        self.assert_validation_error(
            "text and raw HTML keys must be disjoint",
            missing.fragment,
            "missing.html",
            text_values={"value": "x"},
            html_values={"value": validate_fragment("<p>x</p>")},
        )
        self.assert_validation_error(
            "invalid template placeholder syntax",
            invalid.fragment,
            "invalid.html",
            text_values={},
            html_values={},
        )

    def test_snapshots_custom_mappings_once_and_rejects_duplicate_entries(
        self,
    ) -> None:
        renderer = self.renderer_with_fragment(
            "mapping.html",
            "<section>$body</section>",
        )
        text = EntriesMapping(())
        raw = EntriesMapping((("body", validate_fragment("<p>x</p>")),))

        self.assertEqual(
            renderer.fragment(
                "mapping.html",
                text_values=text,  # type: ignore[arg-type]
                html_values=raw,  # type: ignore[arg-type]
            ).value,
            "<section><p>x</p></section>",
        )
        self.assertEqual(text.items_calls, 1)
        self.assertEqual(raw.items_calls, 1)

        duplicates = EntriesMapping((("body", "x"), ("body", "y")))
        self.assert_validation_error(
            "duplicate text value keys",
            renderer.fragment,
            "mapping.html",
            text_values=duplicates,
            html_values={},
        )

        large = LargeEntriesMapping()
        self.assert_validation_error(
            "text values exceed maximum entry count",
            renderer.fragment,
            "mapping.html",
            text_values=large,
            html_values={},
        )
        self.assertEqual(large.items_calls, 1)
        self.assertLessEqual(large.consumed, 129)

        for broken in (
            RaisingItemsMapping(),
            RaisingIterationMapping(),
            RaisingEntryMapping(),
        ):
            with self.subTest(mapping_type=type(broken).__name__):
                with self.assertRaisesRegex(
                    CurriculumValidationError,
                    r"^cannot snapshot text values$",
                ) as caught:
                    renderer.fragment(
                        "mapping.html",
                        text_values=broken,
                        html_values={},
                    )
                self.assertNotIn("sensitive-", str(caught.exception))

    def test_rejects_non_mapping_non_string_and_oversized_values(self) -> None:
        renderer = self.renderer_with_fragment("value.html", "<p>$value</p>")
        cases = (
            (
                {"value": ExactString("x")},
                "text value must be an exact string",
            ),
            (
                EntriesMapping(((ExactString("value"), "x"),)),
                "text value keys must be exact strings",
            ),
            (
                {"value": "x" * (MAX_STRUCTURED_TEXT_CHARS + 1)},
                "text value exceeds maximum character count",
            ),
        )
        for text_values, message in cases:
            with self.subTest(message=message):
                self.assert_validation_error(
                    message,
                    renderer.fragment,
                    "value.html",
                    text_values=text_values,
                    html_values={},
                )

        self.assert_validation_error(
            "text_values must be a mapping",
            renderer.fragment,
            "value.html",
            text_values=(("value", "x"),),
            html_values={},
        )
        self.assert_validation_error(
            "html_values must be a mapping",
            renderer.fragment,
            "value.html",
            text_values={"value": "x"},
            html_values=(("body", validate_fragment("<p>x</p>")),),
        )

    def test_rejects_invalid_page_values_without_echoing_them(self) -> None:
        marker = "sensitive-structured-marker"
        cases = (
            (
                {"title": ExactString(marker), "description": "説明"},
                "title must be an exact string",
            ),
            (
                {"title": "例", "description": ExactString(marker)},
                "description must be an exact string",
            ),
            (
                {
                    "title": marker * (MAX_STRUCTURED_TEXT_CHARS + 1),
                    "description": "説明",
                },
                "title exceeds maximum character count",
            ),
            (
                {"title": "例", "description": f"説明\x00{marker}"},
                "description contains a disallowed control character",
            ),
        )
        for values, message in cases:
            with self.subTest(message=message):
                with self.assertRaises(CurriculumValidationError) as caught:
                    self.renderer.page(
                        output_path=Path("index.html"),
                        content=validate_fragment("<p>x</p>"),
                        **values,
                    )
                self.assertEqual(str(caught.exception), message)
                self.assertNotIn(marker, str(caught.exception))

    def test_rejects_unsafe_output_paths_and_does_not_mutate_valid_path(
        self,
    ) -> None:
        self.assertEqual(render_module.MAX_OUTPUT_DEPTH, 32)
        self.assertEqual(render_module.MAX_OUTPUT_PATH_CHARS, 1_024)

        def path_with_exact_length(total: int) -> Path:
            depth = 8
            filename = "index.html"
            remaining = total - len(filename) - depth
            directories: list[str] = []
            for slots in range(depth, 0, -1):
                part_length = min(128, remaining - (slots - 1))
                self.assertGreaterEqual(part_length, 1)
                directories.append("a" * part_length)
                remaining -= part_length
            self.assertEqual(remaining, 0)
            result = Path(*(directories + [filename]))
            self.assertEqual(len(str(result)), total)
            self.assertTrue(all(len(part) <= 128 for part in result.parts))
            return result

        exact_depth = Path(
            *(
                ["level"] * render_module.MAX_OUTPUT_DEPTH
                + ["index.html"]
            )
        )
        exact_depth_html = self.renderer.page(
            output_path=exact_depth,
            title="例",
            description="説明",
            content=validate_fragment("<p>x</p>"),
        )
        exact_root = "../" * render_module.MAX_OUTPUT_DEPTH
        self.assertEqual(len(exact_root), 96)
        self.assertIn(f'href="{exact_root}styles.css"', exact_depth_html)

        exact_length = path_with_exact_length(
            render_module.MAX_OUTPUT_PATH_CHARS
        )
        self.renderer.page(
            output_path=exact_length,
            title="例",
            description="説明",
            content=validate_fragment("<p>x</p>"),
        )
        over_length = path_with_exact_length(
            render_module.MAX_OUTPUT_PATH_CHARS + 1
        )
        cases = (
            Path("/tmp/index.html"),
            Path("."),
            Path("../index.html"),
            Path("lessons/../index.html"),
            Path("lessons\\index.html"),
            Path("bad\x00.html"),
            Path("index.htm"),
            Path("space here/index.html"),
            Path(
                "/".join(
                    ["level"] * (render_module.MAX_OUTPUT_DEPTH + 1)
                    + ["index.html"]
                )
            ),
            Path(
                "/".join(
                    ["a" * 100]
                    * ((render_module.MAX_OUTPUT_PATH_CHARS // 100) + 1)
                    + ["index.html"]
                )
            ),
            Path("/".join(["a"] * 10_000 + ["index.html"])),
            over_length,
        )
        for output_path in cases:
            with self.subTest(output_path=output_path):
                self.assert_validation_error(
                    "output_path must be a safe relative HTML file",
                    self.renderer.page,
                    output_path=output_path,
                    title="例",
                    description="説明",
                    content=validate_fragment("<p>x</p>"),
                )

        valid = Path("lessons/example/index.html")
        before = valid.parts
        self.renderer.page(
            output_path=valid,
            title="例",
            description="説明",
            content=validate_fragment("<p>x</p>"),
        )
        self.assertEqual(valid.parts, before)

    def test_rejects_unsafe_fragment_names(self) -> None:
        cases: tuple[object, ...] = (
            Path("index.html"),
            ExactString("index.html"),
            "",
            "/tmp/x.html",
            "../x.html",
            "nested/x.html",
            r"nested\x.html",
            "bad\x00.html",
            ".html",
            "x.htm",
        )
        for name in cases:
            with self.subTest(name=name):
                self.assert_validation_error(
                    "fragment template name is unsafe",
                    self.renderer.fragment,
                    name,
                    text_values={},
                    html_values={},
                )

    def test_rejects_symlink_nonregular_oversized_and_invalid_utf8_templates(
        self,
    ) -> None:
        with self.temporary_templates() as root:
            renderer = Renderer(root)
            (root / "directory.html").mkdir()
            (root / "large.html").write_bytes(b"x" * (MAX_TEMPLATE_BYTES + 1))
            (root / "invalid.html").write_bytes(b"\xff")
            os.symlink(root / "base.html", root / "linked.html")

            for name, message in (
                ("directory.html", "template must be a regular file"),
                ("large.html", "template exceeds maximum byte count"),
                ("invalid.html", "template is not valid UTF-8 text"),
                ("linked.html", "template symlinks are not allowed"),
                ("missing.html", "could not read template"),
            ):
                with self.subTest(name=name):
                    self.assert_validation_error(
                        message,
                        renderer.fragment,
                        name,
                        text_values={},
                        html_values={},
                    )

    def test_rejects_early_template_eof_without_accepting_valid_prefix(
        self,
    ) -> None:
        source = b"<p>trusted</p> "
        renderer = self.renderer_with_fragment(
            "short-read.html",
            source.decode("utf-8"),
        )

        with patch(
            "curriculum_builder.render.os.read",
            side_effect=(source[:-1], b""),
        ):
            self.assert_validation_error(
                "template changed during read",
                renderer.fragment,
                "short-read.html",
                text_values={},
                html_values={},
            )

    def test_rejects_template_growth_and_post_read_metadata_change(
        self,
    ) -> None:
        source = b"<p>trusted</p>"
        renderer = self.renderer_with_fragment(
            "changing.html",
            source.decode("utf-8"),
        )
        template_path = renderer._template_root / "changing.html"

        with patch(
            "curriculum_builder.render.os.read",
            side_effect=(source, b"x", b""),
        ):
            self.assert_validation_error(
                "template changed during read",
                renderer.fragment,
                "changing.html",
                text_values={},
                html_values={},
            )
        self.assertEqual(template_path.read_bytes(), source)

        real_fstat = os.fstat
        fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        for transition, changed_call in (
            ("before-to-opened", 2),
            ("opened-to-after", 3),
        ):
            for changed_field in fields:
                with self.subTest(
                    transition=transition,
                    changed_field=changed_field,
                ):
                    call_count = 0

                    def changing_fstat(descriptor: int) -> object:
                        nonlocal call_count
                        call_count += 1
                        result = real_fstat(descriptor)
                        if call_count != changed_call:
                            return result

                        class ChangedMetadata:
                            def __getattr__(self, name: str) -> object:
                                original = getattr(result, name)
                                if name != changed_field:
                                    return original
                                if name == "st_mode":
                                    return original ^ stat.S_IXUSR
                                return original + 1

                        return ChangedMetadata()

                    with patch(
                        "curriculum_builder.render.os.fstat",
                        side_effect=changing_fstat,
                    ):
                        self.assert_validation_error(
                            "template changed during read",
                            renderer.fragment,
                            "changing.html",
                            text_values={},
                            html_values={},
                        )
                    self.assertEqual(call_count, changed_call)
                    self.assertEqual(template_path.read_bytes(), source)

    def test_wraps_template_os_errors_without_leaking_paths(self) -> None:
        with patch(
            "curriculum_builder.render.os.open",
            side_effect=OSError("secret-template-path"),
        ):
            with self.assertRaisesRegex(
                CurriculumValidationError,
                r"^could not read template$",
            ) as caught:
                self.renderer.fragment(
                    "index.html",
                    text_values={},
                    html_values={},
                )
        self.assertNotIn("secret-template-path", str(caught.exception))

    def test_renderer_is_independent_of_later_working_directory_changes(
        self,
    ) -> None:
        previous = Path.cwd()
        with TemporaryDirectory() as temporary:
            try:
                os.chdir(temporary)
                fragment = self.renderer.fragment(
                    "index.html",
                    text_values={},
                    html_values={},
                )
            finally:
                os.chdir(previous)

        self.assertIn("<section", fragment.value)

    def test_pins_template_root_identity_against_directory_replacement(
        self,
    ) -> None:
        with self.temporary_templates() as root:
            (root / "index.html").write_text("<p>trusted</p>", encoding="utf-8")
            renderer = Renderer(root)
            moved = root.with_name(f"{root.name}-moved")
            root.rename(moved)
            root.mkdir()
            (root / "index.html").write_text("<p>replacement</p>", encoding="utf-8")

            self.assert_validation_error(
                "template_root changed during rendering",
                renderer.fragment,
                "index.html",
                text_values={},
                html_values={},
            )

    def test_closes_template_descriptors_in_reverse_ownership_order(
        self,
    ) -> None:
        real_open = os.open
        real_close = os.close
        for failed_owner in (None, "file", "root"):
            with self.subTest(failed_owner=failed_owner):
                opened: list[int] = []
                closed: list[int] = []

                def recording_open(
                    *args: object,
                    **kwargs: object,
                ) -> int:
                    descriptor = real_open(  # type: ignore[arg-type]
                        *args,
                        **kwargs,
                    )
                    opened.append(descriptor)
                    return descriptor

                def recording_close(descriptor: int) -> None:
                    closed.append(descriptor)
                    real_close(descriptor)
                    failed_descriptor = (
                        opened[1]
                        if failed_owner == "file"
                        else opened[0]
                    )
                    if (
                        failed_owner is not None
                        and descriptor == failed_descriptor
                    ):
                        raise OSError("injected close failure")

                with (
                    patch(
                        "curriculum_builder.render.os.open",
                        side_effect=recording_open,
                    ),
                    patch(
                        "curriculum_builder.render.os.close",
                        side_effect=recording_close,
                    ),
                ):
                    if failed_owner is None:
                        self.renderer.fragment(
                            "index.html",
                            text_values={},
                            html_values={},
                        )
                    else:
                        self.assert_validation_error(
                            "could not read template",
                            self.renderer.fragment,
                            "index.html",
                            text_values={},
                            html_values={},
                        )

                self.assertEqual(len(opened), 2)
                self.assertEqual(closed, list(reversed(opened)))
                self.assertEqual(
                    Counter(closed),
                    Counter(opened),
                )

    def test_rejects_invalid_template_roots(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            file_root = root / "file"
            file_root.write_text("x", encoding="utf-8")
            symlink_root = root / "linked"
            os.symlink(TEMPLATE_ROOT, symlink_root)

            cases: tuple[object, ...] = (
                str(TEMPLATE_ROOT),
                file_root,
                symlink_root,
                root / "missing",
            )
            for candidate in cases:
                with self.subTest(candidate=candidate):
                    self.assert_validation_error(
                        "template_root must be a real directory",
                        Renderer,
                        candidate,
                    )

    def test_rejects_base_placeholder_and_security_policy_regressions(self) -> None:
        base = (TEMPLATE_ROOT / "base.html").read_text(encoding="utf-8")
        charset = '  <meta charset="utf-8">\n'
        viewport = (
            '  <meta name="viewport" '
            'content="width=device-width, initial-scale=1">\n'
        )
        title = (
            "  <title>$title · Engineering Expert Curriculum</title>\n"
        )
        stylesheet = (
            '  <link rel="stylesheet" href="${root}styles.css">\n'
        )
        skip = '  <a class="skip-link" href="#main">本文へ移動</a>\n'
        brand = (
            '    <a class="brand" href="${root}index.html">'
            "Engineering Atlas</a>\n"
        )
        nav_open = '    <nav aria-label="主要ナビゲーション">\n'
        roadmap_link = (
            '      <a href="${root}roadmap/index.html">'
            "ロードマップ</a>\n"
        )
        lessons_link = (
            '      <a href="${root}lessons/index.html">'
            "コアレッスン</a>\n"
        )
        catalog_link = (
            '      <a href="${root}catalog/index.html">'
            "全カタログ</a>\n"
        )
        nav = (
            nav_open
            + roadmap_link
            + lessons_link
            + catalog_link
            + "    </nav>\n"
        )
        header_open = '  <header class="site-header">\n'
        header = header_open + brand + nav + "  </header>\n"
        main = '  <main id="main">$content</main>\n'
        footer = (
            "  <footer><p>Learn · Practice · Explain · Prove</p>"
            "</footer>\n"
        )
        body_sequence = skip + header + main + footer

        security_cases = (
            (
                base.replace(
                    '<main id="main">$content</main>',
                    '<main id="$content"></main>',
                ),
                "raw HTML placeholder requires element-body context",
            ),
            (
                base.replace(
                    '<footer><p>Learn · Practice · Explain · Prove</p></footer>',
                    "<footer>$content</footer>",
                ),
                "base template placeholders do not match required counts",
            ),
            (
                base.replace("script-src 'none'; ", ""),
                "base template CSP is incomplete",
            ),
            (
                base.replace(
                    "script-src 'none';",
                    "script-src 'none'; script-src-elem 'self';",
                ),
                "base template CSP is incomplete",
            ),
            (
                base.replace(
                    "script-src 'none';",
                    "script-src 'none'; script-src-attr 'unsafe-inline';",
                ),
                "base template CSP is incomplete",
            ),
            (
                base.replace(
                    "script-src 'none';",
                    "script-src 'none'; script-src 'self';",
                ),
                "base template CSP is incomplete",
            ),
            (
                base.replace(
                    "  <title>",
                    '  <meta http-equiv="refresh" '
                    'content="0;url=https://evil.example">\n'
                    "  <title>",
                ),
                "base template markup is invalid",
            ),
            (
                base.replace(
                    '  <meta http-equiv="Content-Security-Policy"',
                    "  <p>browser-moves-this-to-body</p>\n"
                    '  <meta http-equiv="Content-Security-Policy"',
                ),
                "base template markup is invalid",
            ),
            (
                base.replace(
                    '  <header class="site-header">',
                    '  <p><header class="site-header">',
                ).replace(
                    "  </header>\n  <main",
                    "  </header></p>\n  <main",
                ),
                "base template markup is invalid",
            ),
            (
                base.replace(
                    "  <title>",
                    '  <meta name="robots" content="index">\n  <title>',
                ),
                "base template markup is invalid",
            ),
            (
                base.replace(
                    '  <meta charset="utf-8">',
                    '  <meta charset="utf-8">\n  <meta charset="utf-8">',
                ),
                "base template markup is invalid",
            ),
            (
                base.replace(
                    "${root}styles.css",
                    "https://cdn.example/${root}styles.css",
                ),
                "base template contains an external or absolute asset URL",
            ),
        )
        structural_cases = (
            (
                base.replace(charset + viewport, viewport + charset, 1),
                "base template markup is invalid",
            ),
            (
                base.replace(title + stylesheet, stylesheet + title, 1),
                "base template markup is invalid",
            ),
            (
                base.replace(charset, "", 1),
                "base template markup is invalid",
            ),
            (
                base.replace(
                    title,
                    "  <p>$title · Engineering Expert Curriculum</p>\n",
                    1,
                ),
                "base template markup is invalid",
            ),
            (
                base.replace(stylesheet, brand, 1),
                "base template markup is invalid",
            ),
            (
                base.replace(
                    body_sequence,
                    header + skip + main + footer,
                    1,
                ),
                "base template markup is invalid",
            ),
            (
                base.replace(skip, "", 1),
                "base template markup is invalid",
            ),
            (
                base.replace(header, brand + nav, 1),
                "base template markup is invalid",
            ),
            (
                base.replace(
                    main,
                    "  <footer>$content</footer>\n",
                    1,
                ),
                "base template markup is invalid",
            ),
            (
                base.replace(footer, "", 1),
                "base template markup is invalid",
            ),
            (
                base.replace(
                    header,
                    header_open + nav + brand + "  </header>\n",
                    1,
                ),
                "base template markup is invalid",
            ),
            (
                base.replace(
                    header,
                    header_open + roadmap_link + nav + "  </header>\n",
                    1,
                ),
                "base template markup is invalid",
            ),
            (
                base.replace(
                    header,
                    header_open
                    + brand
                    + roadmap_link
                    + lessons_link
                    + catalog_link
                    + "  </header>\n",
                    1,
                ),
                "base template markup is invalid",
            ),
            (
                base.replace(
                    roadmap_link + lessons_link,
                    lessons_link + roadmap_link,
                    1,
                ),
                "base template markup is invalid",
            ),
            (
                base.replace(roadmap_link, lessons_link, 1),
                "base template markup is invalid",
            ),
            (
                base.replace(
                    footer,
                    "  <footer></footer>\n",
                    1,
                ),
                "base template markup is invalid",
            ),
            (
                base.replace(
                    footer,
                    "  <footer></footer>"
                    "<p>Learn · Practice · Explain · Prove</p>\n",
                    1,
                ),
                "base template markup is invalid",
            ),
            *(
                (
                    base.replace(
                        opening,
                        opening + "DIRECT-TEXT",
                        1,
                    ),
                    "base template markup is invalid",
                )
                for opening in (
                    "<head>\n",
                    "<body>\n",
                    header_open,
                    nav_open,
                    "  <footer>",
                )
            ),
            (
                base.replace(
                    charset,
                    charset.rstrip("\n") + "</meta>\n",
                    1,
                ),
                "template markup is invalid",
            ),
        )
        cases = security_cases + structural_cases
        for index, (source, message) in enumerate(cases):
            self.assertNotEqual(
                source,
                base,
                f"base mutation {index} must change the fixture",
            )
            with self.subTest(index=index, message=message):
                with TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    (root / "base.html").write_text(source, encoding="utf-8")
                    self.assert_validation_error(message, Renderer, root)

    def test_rejects_excessive_placeholder_count(self) -> None:
        renderer = self.renderer_with_fragment(
            "many.html",
            "<p>"
            + "".join(
                f"${{value{index}}}"
                for index in range(MAX_PLACEHOLDERS + 1)
            )
            + "</p>",
        )
        values = {
            f"value{index}": "x"
            for index in range(MAX_PLACEHOLDERS + 1)
        }

        self.assert_validation_error(
            "template exceeds maximum placeholder count",
            renderer.fragment,
            "many.html",
            text_values=values,
            html_values={},
        )

    def test_rejects_content_id_collisions_in_completed_document(self) -> None:
        self.assert_validation_error(
            "duplicate rendered HTML id",
            self.renderer.page,
            output_path=Path("index.html"),
            title="例",
            description="説明",
            content=validate_fragment('<section id="ma&#105;n">本文</section>'),
        )

    def test_wraps_completed_document_parser_errors_without_input_leak(self) -> None:
        marker = "sensitive-document-marker"
        with patch(
            "curriculum_builder.render._DocumentIdParser.feed",
            side_effect=RuntimeError(marker),
        ):
            with self.assertRaisesRegex(
                CurriculumValidationError,
                r"^could not parse rendered HTML document$",
            ) as caught:
                self.renderer.page(
                    output_path=Path("index.html"),
                    title="例",
                    description="説明",
                    content=validate_fragment(f"<p>{marker}</p>"),
                )
        self.assertNotIn(marker, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
