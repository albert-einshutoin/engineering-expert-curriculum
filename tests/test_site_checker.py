from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from curriculum_builder.build import build_site
import tools.check_site as check_site_module
from tools.check_site import (
    CURRENT_RELEASE_INVENTORY,
    MAX_ISSUES,
    SiteValidationError,
    check_site,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPOSITORY_ROOT / "tools" / "check_site.py"
CSP = (
    "default-src 'none'; script-src 'none'; style-src 'self'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'none'; "
    "base-uri 'none'; form-action 'none'; object-src 'none'; "
    "frame-src 'none'"
)


def _page(
    *,
    root: str = "",
    head: str = "",
    body: str = "",
    lang: str = "ja",
    csp: str = CSP,
) -> str:
    return f"""<!doctype html>
<html lang="{lang}">
<head>
  <meta charset="utf-8">
  <meta http-equiv="Content-Security-Policy" content="{csp}">
  <title>検証ページ</title>
  <link rel="stylesheet" href="{root}styles.css">
  <link rel="stylesheet" href="{root}static/visualizations.css">
  {head}
</head>
<body>
  <a class="skip-link" href="#main">本文へ移動</a>
  <main id="main"><h1>検証ページ</h1>{body}</main>
</body>
</html>
"""


@contextmanager
def _fixture():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "guide").mkdir()
        (root / "styles.css").write_text(
            "body { color: #123456; }\n",
            encoding="utf-8",
        )
        (root / "static").mkdir()
        (root / "static" / "visualizations.css").write_text(
            ".visualization { display: grid; }\n",
            encoding="utf-8",
        )
        (root / "index.html").write_text(
            _page(
                body=(
                    '<a href="guide/">案内</a>'
                    '<a href="guide/#details">詳細</a>'
                )
            ),
            encoding="utf-8",
        )
        (root / "guide" / "index.html").write_text(
            _page(
                root="../",
                body=(
                    '<section id="details"><h2>詳細</h2></section>'
                    '<a href="../index.html">戻る</a>'
                ),
            ),
            encoding="utf-8",
        )
        yield root


class SiteCheckerHappyPathTests(unittest.TestCase):
    def test_accepts_local_file_url_compatible_site(self) -> None:
        with _fixture() as root:
            self.assertEqual(check_site(root), [])
            self.assertEqual(
                check_site(
                    root,
                    expected_entrypoints={
                        "index.html",
                        "guide/index.html",
                        "styles.css",
                        "static/visualizations.css",
                    },
                ),
                [],
            )

    def test_accepts_the_exact_current_release_inventory(self) -> None:
        with TemporaryDirectory(
            prefix=".site-checker-",
            dir=REPOSITORY_ROOT.parent,
        ) as directory:
            site = Path(directory) / "site"
            build_site(
                REPOSITORY_ROOT / "content",
                REPOSITORY_ROOT / "templates",
                REPOSITORY_ROOT / "static",
                site,
                require_complete_curriculum=True,
            )

            self.assertEqual(
                check_site(site, require_current_release=True),
                [],
            )
            inventory = {
                path.relative_to(site).as_posix()
                for path in site.rglob("*")
                if path.is_file()
            }
            self.assertEqual(inventory, set(CURRENT_RELEASE_INVENTORY))


class SiteCheckerFilesystemTests(unittest.TestCase):
    def test_missing_and_empty_roots_fail_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "missing"
            self.assertTrue(any("root" in issue for issue in check_site(missing)))
            self.assertTrue(any("empty" in issue for issue in check_site(root)))

    def test_rejects_root_file_and_symbolic_link(self) -> None:
        with TemporaryDirectory() as directory:
            parent = Path(directory)
            root_file = parent / "root.html"
            root_file.write_text(_page(), encoding="utf-8")
            link = parent / "site-link"
            link.symlink_to(parent, target_is_directory=True)
            self.assertTrue(
                any("directory" in issue for issue in check_site(root_file))
            )
            self.assertTrue(any("symbolic link" in issue for issue in check_site(link)))

    def test_rejects_casefolded_unexpected_extension(self) -> None:
        with _fixture() as root:
            (root / "payload.JS").write_text("alert(1)", encoding="utf-8")
            issues = check_site(root)
            self.assertTrue(
                any(
                    "payload.JS" in issue and "file type" in issue
                    for issue in issues
                )
            )

    def test_rejects_symbolic_and_hard_links(self) -> None:
        with _fixture() as root:
            (root / "linked.html").symlink_to(root / "index.html")
            os.link(root / "styles.css", root / "hardlink.css")
            issues = check_site(root)
            self.assertTrue(
                any(
                    "linked.html" in issue and "symbolic" in issue
                    for issue in issues
                )
            )
            self.assertTrue(
                any(
                    "hardlink.css" in issue and "hard link" in issue
                    for issue in issues
                )
            )

    def test_rejects_fifo_and_special_files_without_blocking(self) -> None:
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO is not supported")
        with _fixture() as root:
            os.mkfifo(root / "stream.css")
            issues = check_site(root)
            self.assertTrue(
                any(
                    "stream.css" in issue and "regular" in issue
                    for issue in issues
                )
            )

    def test_regular_file_close_failure_is_reported_without_retry(self) -> None:
        with _fixture() as root:
            real_close = os.close
            failed_descriptor: int | None = None
            failure_attempts = 0

            def close_then_fail_once(descriptor: int) -> None:
                nonlocal failed_descriptor, failure_attempts
                try:
                    mode = os.fstat(descriptor).st_mode
                except OSError:
                    if descriptor == failed_descriptor:
                        failure_attempts += 1
                    raise
                real_close(descriptor)
                if failed_descriptor is None and stat.S_ISREG(mode):
                    failed_descriptor = descriptor
                    failure_attempts += 1
                    raise OSError("REGULAR_CLOSE_FAILURE")

            with patch.object(
                check_site_module.os,
                "close",
                side_effect=close_then_fail_once,
            ):
                issues = check_site(root)

            self.assertEqual(failure_attempts, 1)
            self.assertTrue(
                any("could not be closed safely" in issue for issue in issues)
            )

    def test_read_failure_remains_visible_when_file_close_also_fails(self) -> None:
        with _fixture() as root:
            real_close = os.close
            injected_close = False

            def close_then_fail_once(descriptor: int) -> None:
                nonlocal injected_close
                mode = os.fstat(descriptor).st_mode
                real_close(descriptor)
                if not injected_close and stat.S_ISREG(mode):
                    injected_close = True
                    raise OSError("REGULAR_CLOSE_FAILURE")

            with (
                patch.object(
                    check_site_module.os,
                    "read",
                    side_effect=OSError("REGULAR_READ_FAILURE"),
                ),
                patch.object(
                    check_site_module.os,
                    "close",
                    side_effect=close_then_fail_once,
                ),
            ):
                issues = check_site(root)

            self.assertTrue(injected_close)
            self.assertTrue(any("unreadable" in issue for issue in issues))
            self.assertTrue(
                any("could not be closed safely" in issue for issue in issues)
            )

    def test_exact_inventory_reports_missing_and_unexpected_paths(self) -> None:
        with _fixture() as root:
            issues = check_site(
                root,
                expected_entrypoints={"index.html", "missing/index.html"},
            )
            self.assertTrue(
                any("missing expected entrypoint" in issue for issue in issues)
            )
            self.assertTrue(any("unexpected entrypoint" in issue for issue in issues))

    def test_invalid_expected_inventory_raises_typed_error(self) -> None:
        with _fixture() as root:
            for invalid in ({"../index.html"}, {"/index.html"}, {"index.html#main"}):
                with self.subTest(invalid=invalid), self.assertRaises(
                    SiteValidationError
                ):
                    check_site(root, expected_entrypoints=invalid)
            with self.assertRaises(SiteValidationError):
                check_site(
                    root,
                    expected_entrypoints={"index.html"},
                    require_current_release=True,
                )


class SiteCheckerLinkTests(unittest.TestCase):
    def _mutate_index(self, root: Path, body: str) -> list[str]:
        (root / "index.html").write_text(_page(body=body), encoding="utf-8")
        return check_site(root)

    def test_reports_missing_local_target_and_fragment(self) -> None:
        with _fixture() as root:
            issues = self._mutate_index(
                root,
                '<a href="missing.html">missing</a>'
                '<a href="guide/#missing">fragment</a>',
            )
            self.assertTrue(any("missing local target" in issue for issue in issues))
            self.assertTrue(any("missing fragment" in issue for issue in issues))

    def test_rejects_empty_and_duplicate_fragments_and_duplicate_ids(self) -> None:
        with _fixture() as root:
            issues = self._mutate_index(
                root,
                '<a href="#">empty</a><div id="same"></div>'
                '<section id="same"></section>',
            )
            self.assertTrue(any("empty fragment" in issue for issue in issues))
            self.assertTrue(any("duplicate id" in issue for issue in issues))

    def test_rejects_root_escape_absolute_and_file_scheme_links(self) -> None:
        with _fixture() as root:
            outside = root.parent / "outside.html"
            outside.write_text("outside", encoding="utf-8")
            try:
                issues = self._mutate_index(
                    root,
                    '<a href="../outside.html">plain</a>'
                    '<a href="%2e%2e/outside.html">encoded</a>'
                    '<a href="/index.html">absolute</a>'
                    '<a href="file:///etc/passwd">file</a>',
                )
            finally:
                outside.unlink()
            self.assertGreaterEqual(
                sum("root escape" in issue for issue in issues),
                3,
            )
            self.assertTrue(any("file URL" in issue for issue in issues))

    def test_external_links_require_https_and_referrer_protection(self) -> None:
        with _fixture() as root:
            issues = self._mutate_index(
                root,
                '<a href="http://example.com" rel="noreferrer">http</a>'
                '<a href="https://example.com" rel="noopener">missing rel</a>'
                '<a href="https://user@example.com" '
                'rel="noopener noreferrer">creds</a>',
            )
            self.assertTrue(any("HTTPS" in issue for issue in issues))
            self.assertTrue(any("noreferrer" in issue for issue in issues))
            self.assertTrue(any("credentials" in issue for issue in issues))

    def test_accepts_credential_free_https_anchor_with_safe_rel(self) -> None:
        with _fixture() as root:
            issues = self._mutate_index(
                root,
                '<a href="https://example.com/reference?q=1#part" '
                'rel="noreferrer">safe</a>',
            )
            self.assertEqual(issues, [])


class SiteCheckerHtmlTests(unittest.TestCase):
    def _issues_for(self, document: str) -> list[str]:
        with _fixture() as root:
            (root / "index.html").write_text(document, encoding="utf-8")
            return check_site(root)

    def test_rejects_malformed_html_and_duplicate_attributes(self) -> None:
        for mutation in (
            _page().replace("</main>", "</section>", 1),
            _page().replace('<main id="main">', '<main id="main" id="other">', 1),
            _page() + "<div",
        ):
            with self.subTest(mutation=mutation[-30:]):
                self.assertTrue(
                    any(
                        "malformed HTML" in issue
                        for issue in self._issues_for(mutation)
                    )
                )

    def test_requires_ja_nonempty_title_exactly_one_main_h1_and_skip_link(self) -> None:
        mutations = {
            "lang": _page(lang="en"),
            "title": _page().replace(
                "<title>検証ページ</title>",
                "<title> </title>",
            ),
            "main": _page().replace("</main>", "</main><main></main>"),
            "h1": _page().replace("</main>", "<h1>重複</h1></main>"),
            "skip": _page().replace("skip-link", "ordinary-link"),
        }
        for expected, document in mutations.items():
            with self.subTest(expected=expected):
                self.assertTrue(
                    any(
                        expected in issue
                        for issue in self._issues_for(document)
                    )
                )

    def test_rejects_inert_semantic_contracts(self) -> None:
        required = (
            '<a class="skip-link" href="#main">本文へ移動</a>\n'
            '  <main id="main"><h1>検証ページ</h1>'
        )
        for wrapper in (
            "template",
            "div hidden",
            "div inert",
            'div aria-hidden="true"',
            "dialog",
            "details",
        ):
            document = _page().replace(
                required,
                f"<{wrapper}>{required}",
                1,
            ).replace("</main>", f"</main></{wrapper.split()[0]}>", 1)
            with self.subTest(wrapper=wrapper):
                self.assertTrue(
                    any("inert" in issue for issue in self._issues_for(document))
                )

    def test_requires_nonempty_ordered_headings(self) -> None:
        mutations = (
            _page().replace("<h1>検証ページ</h1>", "<h1></h1>"),
            _page().replace(
                "<h1>検証ページ</h1>",
                "<h1>検証ページ</h1><h3>飛び級</h3>",
            ),
        )
        for document in mutations:
            with self.subTest(document=document[-80:]):
                self.assertTrue(
                    any("heading" in issue for issue in self._issues_for(document))
                )

    def test_skip_link_must_target_the_actual_main_element(self) -> None:
        document = _page().replace(
            '<main id="main">',
            '<div id="main"></div><main id="content">',
            1,
        )
        self.assertTrue(
            any("skip link target" in issue for issue in self._issues_for(document))
        )

    def test_requires_exactly_one_utf8_charset_declaration(self) -> None:
        mutations = (
            _page().replace('  <meta charset="utf-8">\n', "", 1),
            _page().replace('charset="utf-8"', 'charset="shift_jis"', 1),
            _page().replace(
                '  <meta charset="utf-8">',
                '  <meta charset="utf-8"><meta charset="utf-8">',
                1,
            ),
            _page().replace(
                '  <meta charset="utf-8">\n',
                "",
                1,
            ).replace(
                "</body>",
                '<meta charset="utf-8"></body>',
                1,
            ),
            _page().replace(
                '  <meta charset="utf-8">',
                "<!--" + ("padding" * 150) + '--><meta charset="utf-8">',
                1,
            ),
        )
        for document in mutations:
            with self.subTest(document=document[:100]):
                self.assertTrue(
                    any("charset" in issue for issue in self._issues_for(document))
                )

    def test_charset_byte_boundary_handles_all_html_parser_newlines(self) -> None:
        marker = '<meta charset="utf-8">'
        cases = (
            ("LF", "\n", "x"),
            ("CRLF", "\r\n", "x"),
            ("lone CR", "\r", "x"),
            ("multibyte", "\n", "界"),
        )

        for label, newline, padding_unit in cases:
            base = _page().replace("\n", newline)
            marker_start = base.index(marker)
            prefix = base[:marker_start]
            suffix = base[marker_start + len(marker) :]
            base_end = len((prefix + marker).encode("utf-8"))
            unit_size = len(padding_unit.encode("utf-8"))

            for expected_end, rejected in ((1024, False), (1025, True)):
                padding_bytes = expected_end - base_end
                units, remainder = divmod(padding_bytes, unit_size)
                padding = padding_unit * units + "x" * remainder
                document = prefix + padding + marker + suffix
                self.assertEqual(
                    len((prefix + padding + marker).encode("utf-8")),
                    expected_end,
                )

                with self.subTest(
                    newline=label,
                    expected_end=expected_end,
                ):
                    charset_rejected = any(
                        "charset" in issue for issue in self._issues_for(document)
                    )
                    self.assertEqual(charset_rejected, rejected)

    def test_rejects_forbidden_active_elements(self) -> None:
        for tag in ("script", "iframe", "object", "embed", "form", "base"):
            with self.subTest(tag=tag):
                issues = self._issues_for(_page(body=f"<{tag}></{tag}>"))
                self.assertTrue(
                    any(
                        tag in issue and "forbidden" in issue
                        for issue in issues
                    )
                )

    def test_rejects_meta_refresh_inline_handlers_and_inline_style(self) -> None:
        mutations = (
            _page(
                head=(
                    '<meta http-equiv="refresh" '
                    'content="0;url=https://example.com">'
                )
            ),
            _page(
                head=(
                    '<meta http-equiv=" refresh " '
                    'content="0;url=https://example.com">'
                )
            ),
            _page().replace("<main id=", "<main onclick=\"run()\" id=", 1),
            _page().replace("<main id=", "<main style=\"color:red\" id=", 1),
        )
        for document in mutations:
            issues = self._issues_for(document)
            self.assertTrue(any("forbidden" in issue for issue in issues))

    def test_rejects_unsafe_url_schemes_and_remote_resources(self) -> None:
        mutations = (
            '<a href="javascript:alert(1)">x</a>',
            '<img src="data:image/svg+xml,x">',
            '<img src="https://example.com/a.png">',
            '<video src="https://example.com/a.mp4"></video>',
            '<audio src="//example.com/a.mp3"></audio>',
            '<a href="#main" ping="https://example.com/audit">ping</a>',
            '<div background="https://example.com/a.png">background</div>',
        )
        for body in mutations:
            with self.subTest(body=body):
                issues = self._issues_for(_page(body=body))
                self.assertTrue(
                    any(
                        "unsafe URL" in issue or "remote resource" in issue
                        for issue in issues
                    )
                )

    def test_requires_exactly_two_ordered_local_stylesheets(self) -> None:
        links = (
            '  <link rel="stylesheet" href="styles.css">\n'
            '  <link rel="stylesheet" href="static/visualizations.css">'
        )
        without_links = _page().replace(links, "")
        mutations = (
            _page().replace("styles.css", "https://example.com/styles.css", 1),
            _page(head='<link rel="stylesheet" href="styles.css">'),
            _page().replace('rel="stylesheet"', 'rel="preload"', 1),
            _page().replace(
                '  <link rel="stylesheet" href="styles.css">\n'
                '  <link rel="stylesheet" href="static/visualizations.css">',
                '  <link rel="stylesheet" href="static/visualizations.css">\n'
                '  <link rel="stylesheet" href="styles.css">',
            ),
            without_links.replace("<body>", f"<body>\n{links}"),
            without_links.replace("</head>", f"</head>\n{links}"),
        )
        for document in mutations:
            issues = self._issues_for(document)
            self.assertTrue(any("stylesheet" in issue for issue in issues))

        for document in mutations[-2:]:
            self.assertTrue(
                any(
                    "stylesheet must be a direct child of head" in issue
                    for issue in self._issues_for(document)
                )
            )

    def test_requires_exact_csp_contract(self) -> None:
        mutations = (
            _page(csp=CSP.replace("script-src 'none'; ", "")),
            _page(csp=CSP + "; media-src https:"),
            _page(csp=CSP.replace("; ", ";  ", 1)),
            _page().replace("Content-Security-Policy", "content-security-policy", 1)
            + '<meta http-equiv="Content-Security-Policy" content="' + CSP + '">',
        )
        for document in mutations:
            self.assertTrue(any("CSP" in issue for issue in self._issues_for(document)))


class SiteCheckerCssAndCliTests(unittest.TestCase):
    def test_visualization_css_has_an_80_kib_deployed_budget(self) -> None:
        with _fixture() as root:
            (root / "static/visualizations.css").write_bytes(
                b"a" * ((80 * 1024) + 1)
            )
            issues = check_site(root)
            self.assertTrue(
                any(
                    "static/visualizations.css" in issue
                    and "too large" in issue
                    for issue in issues
                ),
                issues,
            )

    def test_css_must_be_nonempty_utf8_and_local_only(self) -> None:
        payloads = (
            b"",
            b"\xff",
            b"body { color: red; }\x00",
            b"@import 'https://example.com/a.css';",
            b"body { background: url(https://example.com/a.png); }",
            b"@font-face { src: url(font.woff2); }",
        )
        for payload in payloads:
            with self.subTest(payload=payload), _fixture() as root:
                (root / "styles.css").write_bytes(payload)
                issues = check_site(root)
                self.assertTrue(any("CSS" in issue for issue in issues))

    def test_css_comments_cannot_reconstruct_resource_syntax(self) -> None:
        payloads = (
            b"body { background: url/**/(https://example.com/a.png); }",
            b'@im/**/port "https://example.com/a.css";',
            b"@font-/**/face { src: url/**/(font.woff2); }",
        )
        for payload in payloads:
            with self.subTest(payload=payload), _fixture() as root:
                (root / "styles.css").write_bytes(payload)
                issues = check_site(root)
                self.assertTrue(any("CSS" in issue for issue in issues))

    def test_diagnostics_are_bounded(self) -> None:
        with _fixture() as root:
            for ordinal in range(MAX_ISSUES + 20):
                (root / f"payload-{ordinal:03}.JS").write_text("x", encoding="utf-8")
            issues = check_site(root)
            self.assertLessEqual(len(issues), MAX_ISSUES + 1)
            self.assertIn("additional issues omitted", issues[-1])

    def test_cli_accepts_required_root_option(self) -> None:
        with _fixture() as root:
            result = subprocess.run(
                [sys.executable, str(CHECKER), "--root", str(root)],
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")

    def test_cli_failure_has_no_traceback_or_absolute_root_leak(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory) / "missing"
            result = subprocess.run(
                [sys.executable, str(CHECKER), "--root", str(root)],
                capture_output=True,
                check=False,
                text=True,
            )
            output = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", output)
            self.assertNotIn(str(root), output)
            self.assertLess(len(output), 8_192)


if __name__ == "__main__":
    unittest.main()
