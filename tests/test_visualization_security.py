from __future__ import annotations

from pathlib import Path
import hashlib
import io
import os
import stat
import subprocess
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest import mock
import zipfile

from curriculum_builder.errors import CurriculumValidationError
from curriculum_builder.javascript_safety import (
    MAX_JAVASCRIPT_BYTES,
    validate_reviewed_visualization_runtime,
    validate_javascript_bytes,
)
from tools.install_test_browsers import (
    BrowserArchive,
    BrowserMatrixError,
    install_archive,
    main as install_main,
    verify_macos_browser_bundle,
    verify_linux_browser_binary,
    verify_safari_version,
)


class JavaScriptSafetyTests(unittest.TestCase):
    def test_accepts_a_small_closed_classic_script(self) -> None:
        source = b"(function () { 'use strict'; var value = 1; }());\n"
        self.assertIn("use strict", validate_javascript_bytes(source))

    def test_rejects_invalid_input_encoding_size_and_ambiguous_lexing(self) -> None:
        payloads = (
            object(), b"", b"\xff", b"x" * (MAX_JAVASCRIPT_BYTES + 1),
            b"'unterminated", b"/* unterminated", b"`template`", b"(function () {",
            b"'\\u0066etch'", b"//# sourceMappingURL=x\n",
            "var x = 1;\u202e".encode(),
        )
        for payload in payloads:
            with self.subTest(payload=repr(payload)[:40]):
                with self.assertRaises(CurriculumValidationError):
                    validate_javascript_bytes(payload)

    def test_rejects_every_forbidden_runtime_capability_even_in_comments(self) -> None:
        tokens = (
            "eval", "Function", "import(", "fetch", "XMLHttpRequest",
            "WebSocket", "EventSource", "Worker", "ServiceWorker",
            "localStorage", "sessionStorage", "indexedDB", "caches", "cookie",
            "clipboard", "location", "history", "innerHTML", "outerHTML",
            "DOMParser", "insertAdjacentHTML", "requestAnimationFrame",
            "MutationObserver", "createElement", "style", "https://example.com",
            "URLSearchParams", "//# sourceURL=x",
        )
        for token in tokens:
            with self.subTest(token=token), self.assertRaises(CurriculumValidationError):
                validate_javascript_bytes(f"/* {token} */\nvar safe = 1;".encode())

    def test_rejects_obfuscated_navigation_and_beacon_member_forms(self) -> None:
        payloads = (
            b"window [ 'open' ] ('x');",
            b"window [ 'o' + 'pen' ] ('x');",
            b"navigator [ \"sendBeacon\" ] ('x');",
            b"navigator [ 'send' + 'Beacon' ] ('x');",
            b"globalThis.navigation.navigate('x');",
            b"var x = navigation['currentEntry'];",
            b"open('x');",
            b"globalThis.open('x');",
            b"self.open('x');",
            b"top.open('x');",
            b"parent.open('x');",
            b"document.defaultView.open('x');",
            b"document['defaultView']['open']('x');",
            b"document.defaultView['o' + 'pen']('x');",
            b"var opener = globalThis.open; opener('x');",
            b"var w = window; w['op' + 'en']('x');",
            b"var g = globalThis; g['open']('x');",
            b"var n = navigator; n['send' + 'Beacon']('x');",
        )
        for payload in payloads:
            with self.subTest(payload=payload), self.assertRaises(CurriculumValidationError):
                validate_javascript_bytes(payload)

    def test_browser_authority_is_limited_to_direct_first_party_members(self) -> None:
        allowed = (
            b"window.matchMedia('print');",
            b"window.setTimeout(callback, 250);",
            b"window.clearTimeout(timer);",
            b"window.addEventListener('pagehide', callback);",
        )
        for source in allowed:
            with self.subTest(source=source):
                self.assertEqual(validate_javascript_bytes(source), source.decode())

        forbidden = (
            b"var w = (window);",
            b"var w = [window][0];",
            b"var w = { value: window }.value;",
            b"var w = ready ? window : model;",
            b"function authority() { return window; }",
            b"var w = (model, window);",
            b"var w = model; w = window;",
            b"window['setTimeout'](callback, 250);",
            b"window.document;",
            b"globalThis.setTimeout(callback, 250);",
            b"navigator.language;",
            b"var authority = self; authority['open']('x');",
            b"var authority = top; authority['open']('x');",
            b"var authority = parent; authority['open']('x');",
            b"var authority = document.defaultView; authority['open']('x');",
            b"window.setTimeout['con' + 'structor']('return 1')();",
            b"window.matchMedia.constructor('return 1')();",
            b"var timer = window.setTimeout; timer(callback, 250);",
            b"window.matchMedia('print').constructor('return 1')();",
        )
        for source in forbidden:
            with self.subTest(source=source):
                with self.assertRaises(CurriculumValidationError):
                    validate_javascript_bytes(source)

    def test_rejects_constructor_and_prototype_escape_members(self) -> None:
        payloads = (
            b"[].filter.constructor('return 1')();",
            b"[]['filter']['con' + 'structor']('return 1')();",
            b"value.prototype;",
            b"value['proto' + 'type'];",
            b"value.__proto__;",
            b"value['__pro' + 'to__'];",
        )
        for source in payloads:
            with self.subTest(source=source):
                with self.assertRaises(CurriculumValidationError):
                    validate_javascript_bytes(source)

    def test_rejects_reflection_and_string_derived_meta_member_escapes(self) -> None:
        payloads = (
            b"Reflect.get([], 'con' + 'structor')('return 1')();",
            b"[]['filter']['constructor'.slice(0)]('return 1')();",
            b"Object.getOwnPropertyDescriptor([], 'filter').value['con' + 'structor']('return 1')();",
        )
        for source in payloads:
            with self.subTest(source=source):
                with self.assertRaises(CurriculumValidationError):
                    validate_javascript_bytes(source)

    def test_rejects_computed_meta_member_key_generators(self) -> None:
        payloads = (
            b"[][['con', 'structor'].join('')]('return 1')();",
            b"[][String.fromCharCode(99,111,110,115,116,114,117,99,116,111,114)]('return 1')();",
        )
        for source in payloads:
            with self.subTest(source=source):
                with self.assertRaises(CurriculumValidationError):
                    validate_javascript_bytes(source)

    def test_reviewed_runtime_requires_the_versioned_exact_digest(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "static/visualization.js").read_bytes()
        self.assertIn("use strict", validate_reviewed_visualization_runtime(source))
        mutation = source.replace(b"use strict", b"use  strict", 1)
        with self.assertRaises(CurriculumValidationError):
            validate_reviewed_visualization_runtime(mutation)

    def test_navigation_words_in_ordinary_text_do_not_create_false_positives(self) -> None:
        source = b"var explanation = 'open navigation sendBeacon'; // ordinary prose\n"
        self.assertEqual(validate_javascript_bytes(source), source.decode())

    def test_open_as_non_call_identifier_is_not_a_false_positive(self) -> None:
        payloads = (
            b"var openState = 'open'; // open is ordinary prose\n",
            b"var w = model; w['open']; // non-browser object\n",
        )
        for source in payloads:
            with self.subTest(source=source):
                self.assertEqual(validate_javascript_bytes(source), source.decode())


class BrowserProvisioningSecurityTests(unittest.TestCase):
    def _archive(
        self,
        payload: bytes,
        *,
        archive_format: str = "zip",
        symlinks: tuple[tuple[str, str], ...] = (),
    ) -> BrowserArchive:
        return BrowserArchive(
            version="123.0.1",
            url="https://storage.googleapis.com/browser.zip",
            sha256=hashlib.sha256(payload).hexdigest(),
            archive_format=archive_format,
            max_bytes=max(len(payload), 1),
            executable="browser/bin/browser",
            symlinks=symlinks,
        )

    def _zip(
        self,
        entries: dict[str, bytes],
        *,
        symlink: str | None = None,
        symlink_target: str = "target",
    ) -> bytes:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
            if symlink is not None:
                info = zipfile.ZipInfo(symlink)
                info.external_attr = (0o120777 << 16)
                archive.writestr(info, symlink_target)
        return output.getvalue()

    def test_installer_hashes_before_extracting_into_digest_named_cache(self) -> None:
        payload = self._zip({"browser/bin/browser": b"binary"})
        definition = self._archive(payload)
        with TemporaryDirectory() as temporary:
            completed = install_archive(
                definition,
                Path(temporary),
                downloader=lambda _url, _timeout, _limit: payload,
            )
            self.assertIn(definition.sha256, completed.parts)
            self.assertEqual(completed.read_bytes(), b"binary")
            self.assertTrue(os.access(completed, os.X_OK))
            self.assertEqual(
                install_archive(
                    definition,
                    Path(temporary),
                    downloader=lambda *_args: (_ for _ in ()).throw(AssertionError("downloaded twice")),
                ),
                completed,
            )

    def test_cache_hit_revalidates_archive_and_rejects_tree_parent_symlink_escape(self) -> None:
        payload = self._zip({"browser/bin/browser": b"binary"})
        definition = self._archive(payload)
        with TemporaryDirectory() as temporary:
            cache = Path(temporary) / "cache"
            executable = install_archive(
                definition, cache, downloader=lambda *_args: payload
            )
            executable.write_bytes(b"tampered")
            self.assertEqual(
                install_archive(
                    definition, cache,
                    downloader=lambda *_args: (_ for _ in ()).throw(
                        AssertionError("cache hit downloaded again")
                    ),
                ).read_bytes(),
                b"binary",
            )
            outside = Path(temporary) / "outside"
            outside.mkdir()
            browser_parent = executable.parents[1]
            for child in sorted(browser_parent.rglob("*"), reverse=True):
                if child.is_file() or child.is_symlink():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            browser_parent.rmdir()
            browser_parent.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(BrowserMatrixError, "symlink|escape"):
                install_archive(definition, cache, downloader=lambda *_args: payload)

    def test_cache_hit_rejects_mutated_cached_archive(self) -> None:
        payload = self._zip({"browser/bin/browser": b"binary"})
        definition = self._archive(payload)
        with TemporaryDirectory() as temporary:
            cache = Path(temporary)
            install_archive(definition, cache, downloader=lambda *_args: payload)
            (cache / definition.sha256 / "archive").write_bytes(b"X" + payload[1:])
            with self.assertRaisesRegex(BrowserMatrixError, "SHA-256"):
                install_archive(definition, cache, downloader=lambda *_args: payload)

    def test_cached_archive_open_rejects_post_stat_symlink_fifo_and_oversize_swaps(self) -> None:
        payload = self._zip({"browser/bin/browser": b"binary"})
        definition = self._archive(payload)
        original_open = os.open
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for attack in ("symlink", "fifo", "oversize"):
                with self.subTest(attack=attack):
                    cache = root / attack
                    install_archive(definition, cache, downloader=lambda *_args: payload)
                    cached = cache / definition.sha256 / "archive"
                    outside = root / f"{attack}-outside"
                    outside.write_bytes(payload)
                    swapped = False

                    def swap_then_open(path: object, flags: int, mode: int = 0o777, *, dir_fd: int | None = None) -> int:
                        nonlocal swapped
                        if path == "archive" and dir_fd is not None and not swapped:
                            swapped = True
                            cached.unlink()
                            if attack == "symlink":
                                cached.symlink_to(outside)
                            elif attack == "fifo":
                                os.mkfifo(cached)
                            else:
                                cached.write_bytes(payload + b"X")
                        return original_open(path, flags, mode, dir_fd=dir_fd)

                    with mock.patch("tools.install_test_browsers.os.open", side_effect=swap_then_open):
                        with self.assertRaisesRegex(
                            BrowserMatrixError, "regular|link|byte ceiling|changed"
                        ):
                            install_archive(
                                definition, cache,
                                downloader=lambda *_args: (_ for _ in ()).throw(
                                    AssertionError("cache attack must not redownload")
                                ),
                            )

    def test_macos_zip_ditto_uses_private_verified_payload_after_cache_swap(self) -> None:
        good = self._zip({"Browser.app/Contents/MacOS/browser": b"good"})
        bad = self._zip({
            "Browser.app/Contents/MacOS/browser": b"bad",
            "Browser.app/Contents/Resources/extra": b"unexpected",
        })
        definition = BrowserArchive(
            version="123.0.1", url="https://storage.googleapis.com/browser.zip",
            sha256=hashlib.sha256(good).hexdigest(), archive_format="zip",
            max_bytes=len(good), executable="Browser.app/Contents/MacOS/browser",
            signature_policy="developer-id",
        )
        with TemporaryDirectory() as temporary:
            cache = Path(temporary) / "cache"

            def ditto(arguments: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                source = Path(arguments[3])
                destination = Path(arguments[4])
                cached = cache / definition.sha256 / "archive"
                cached.write_bytes(bad)
                self.assertEqual(source.read_bytes(), good)
                with zipfile.ZipFile(source) as archive:
                    archive.extractall(destination)
                return subprocess.CompletedProcess(arguments, 0, "", "")

            with mock.patch("tools.install_test_browsers.sys.platform", "darwin"), \
                    mock.patch("tools.install_test_browsers.subprocess.run", side_effect=ditto), \
                    mock.patch("tools.install_test_browsers.verify_macos_browser_bundle"):
                executable = install_archive(
                    definition, cache, downloader=lambda *_args: good,
                )
            self.assertEqual(executable.read_bytes(), b"good")
            self.assertFalse((executable.parents[1] / "Resources/extra").exists())

    def test_dmg_ignores_precreated_predictable_symlink_fifo_and_hardlink(self) -> None:
        payload = b"verified dmg payload"
        definition = BrowserArchive(
            version="123.0.1", url="https://storage.googleapis.com/browser.dmg",
            sha256=hashlib.sha256(payload).hexdigest(), archive_format="dmg",
            max_bytes=len(payload), executable="Browser.app/Contents/MacOS/browser",
            signature_policy="developer-id",
        )
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for attack in ("symlink", "fifo", "hardlink"):
                with self.subTest(attack=attack):
                    cache = root / attack
                    digest_root = cache / definition.sha256
                    digest_root.mkdir(parents=True)
                    predictable = digest_root / f".{definition.sha256}.download"
                    victim = root / f"{attack}-victim"
                    victim.write_bytes(b"victim")
                    if attack == "symlink":
                        predictable.symlink_to(victim)
                    elif attack == "fifo":
                        os.mkfifo(predictable)
                        fifo_reader = os.open(predictable, os.O_RDONLY | os.O_NONBLOCK)
                    else:
                        os.link(victim, predictable)

                    def extract(source: Path, destination: Path, *_args: object) -> None:
                        if stat.S_ISFIFO(source.lstat().st_mode):
                            raise AssertionError("predictable FIFO staging path was used")
                        self.assertEqual(source.read_bytes(), payload)
                        executable = destination / definition.executable
                        executable.parent.mkdir(parents=True)
                        executable.write_bytes(b"browser")

                    try:
                        with mock.patch("tools.install_test_browsers.sys.platform", "darwin"), \
                                mock.patch("tools.install_test_browsers._extract_dmg", side_effect=extract), \
                                mock.patch("tools.install_test_browsers.verify_macos_browser_bundle"):
                            install_archive(
                                definition, cache, downloader=lambda *_args: payload,
                            )
                    finally:
                        if attack == "fifo":
                            os.close(fifo_reader)
                    self.assertEqual(victim.read_bytes(), b"victim")

    def test_linux_preflight_requires_x86_64_elf_dependencies_version_and_launch(self) -> None:
        elf = bytearray(64)
        elf[:7] = b"\x7fELF\x02\x01\x01"
        elf[18:20] = (62).to_bytes(2, "little")
        with TemporaryDirectory() as temporary:
            executable = Path(temporary) / "chrome"
            executable.write_bytes(elf)
            executable.chmod(0o755)
            with mock.patch("tools.install_test_browsers.subprocess.run") as run:
                run.side_effect = (
                    mock.Mock(returncode=0, stdout="libc.so => /lib/libc.so\n", stderr=""),
                    mock.Mock(returncode=0, stdout="Chromium 123.0.1\n", stderr=""),
                    mock.Mock(returncode=0, stdout="<html><head><title>browser-contract</title></head></html>\n", stderr=""),
                )
                verify_linux_browser_binary(
                    executable, browser_name="chromium", expected_version="123.0.1"
                )
            for mutation in (b"not-elf", bytes(elf[:18] + (183).to_bytes(2, "little") + elf[20:])):
                executable.write_bytes(mutation)
                with self.assertRaises(BrowserMatrixError):
                    verify_linux_browser_binary(
                        executable, browser_name="chromium", expected_version="123.0.1"
                    )

    def test_installer_rejects_hash_size_traversal_absolute_and_links(self) -> None:
        payloads = (
            self._zip({"../escape": b"x", "browser/bin/browser": b"binary"}),
            self._zip({"/absolute": b"x", "browser/bin/browser": b"binary"}),
            self._zip({"browser/bin/browser": b"binary"}, symlink="browser/link"),
        )
        with TemporaryDirectory() as temporary:
            for payload in payloads:
                with self.subTest(payload=hashlib.sha256(payload).hexdigest()), self.assertRaises(BrowserMatrixError):
                    install_archive(
                        self._archive(payload), Path(temporary),
                        downloader=lambda _url, _timeout, _limit, value=payload: value,
                    )
            valid = self._zip({"browser/bin/browser": b"binary"})
            bad = BrowserArchive(
                version="123.0.1", url="https://storage.googleapis.com/browser.zip",
                sha256="0" * 64, archive_format="zip", max_bytes=len(valid),
                executable="browser/bin/browser",
                symlinks=(),
            )
            with self.assertRaises(BrowserMatrixError):
                install_archive(bad, Path(temporary), downloader=lambda *_args: valid)
            with self.assertRaises(BrowserMatrixError):
                install_archive(
                    self._archive(valid), Path(temporary),
                    downloader=lambda *_args: valid + b"x",
                )

    def test_macos_bundle_accepts_only_the_exact_internal_symlink_map(self) -> None:
        valid = self._zip(
            {"browser/bin/browser": b"binary", "browser/target": b"target"},
            symlink="browser/link",
        )
        with TemporaryDirectory() as temporary:
            calls = 0

            def download(*_args: object) -> bytes:
                nonlocal calls
                calls += 1
                return valid

            with self.assertRaises(BrowserMatrixError):
                install_archive(
                    self._archive(valid), Path(temporary), downloader=download
                )
            installed = install_archive(
                self._archive(valid, symlinks=(("browser/link", "target"),)),
                Path(temporary), downloader=download,
            )
            self.assertEqual(calls, 1)
            self.assertTrue(installed.is_file())
            self.assertEqual(os.readlink(installed.parents[1] / "link"), "target")

        malicious = (
            (("browser/link", "/absolute"),),
            (("browser/link", "../../../escape"),),
            (("browser/link", "missing"),),
            (),
        )
        for expected in malicious:
            with TemporaryDirectory() as temporary, self.assertRaises(BrowserMatrixError):
                install_archive(
                    self._archive(valid, symlinks=expected), Path(temporary),
                    downloader=lambda *_args, value=valid: value,
                )

        cycle = self._zip(
            {"browser/bin/browser": b"binary"},
            symlink="browser/link-a",
            symlink_target="link-b",
        )
        output = io.BytesIO(cycle)
        rewritten = io.BytesIO()
        with zipfile.ZipFile(output) as source, zipfile.ZipFile(rewritten, "w") as destination:
            for info in source.infolist():
                destination.writestr(info, source.read(info))
            info = zipfile.ZipInfo("browser/link-b")
            info.external_attr = (0o120777 << 16)
            destination.writestr(info, "link-a")
        cycle_payload = rewritten.getvalue()
        with TemporaryDirectory() as temporary, self.assertRaises(BrowserMatrixError):
            install_archive(
                self._archive(
                    cycle_payload,
                    symlinks=(("browser/link-a", "link-b"), ("browser/link-b", "link-a")),
                ),
                Path(temporary), downloader=lambda *_args: cycle_payload,
            )

    def test_tar_installer_rejects_symbolic_and_hard_links(self) -> None:
        for link_type in (tarfile.SYMTYPE, tarfile.LNKTYPE):
            output = io.BytesIO()
            with tarfile.open(fileobj=output, mode="w:xz") as archive:
                executable = tarfile.TarInfo("browser/bin/browser")
                executable.size = 6
                archive.addfile(executable, io.BytesIO(b"binary"))
                link = tarfile.TarInfo("browser/link")
                link.type = link_type
                link.linkname = "browser/bin/browser"
                archive.addfile(link)
            payload = output.getvalue()
            with TemporaryDirectory() as temporary, self.assertRaises(BrowserMatrixError):
                install_archive(
                    self._archive(payload, archive_format="tar.xz"), Path(temporary),
                    downloader=lambda *_args, value=payload: value,
                )

    def test_safari_preflight_requires_exact_installed_version(self) -> None:
        with mock.patch("tools.install_test_browsers.subprocess.run") as run:
            run.side_effect = (
                mock.Mock(stdout="26.5\n"),
                mock.Mock(stdout="21624.2.5.11.4\n"),
                mock.Mock(stdout="26.5\n"),
                mock.Mock(stdout="21624.2.5.11.4\n"),
            )
            verify_safari_version(
                executable=Path("/Applications/Safari.app/Contents/MacOS/Safari"),
                expected_version="26.5",
                expected_build="21624.2.5.11.4",
            )
            self.assertEqual(
                run.call_args_list[0].args[0][2],
                "/Applications/Safari.app/Contents/Info",
            )
            with self.assertRaises(BrowserMatrixError):
                verify_safari_version(
                    executable=Path("/Applications/Safari.app/Contents/MacOS/Safari"),
                    expected_version="26.4",
                    expected_build="21624.2.5.11.4",
                )

    def test_installer_cli_provisions_only_host_archives_and_checks_safari(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as temporary, mock.patch(
            "tools.install_test_browsers.detect_host_platform", return_value="macos-arm64"
        ), mock.patch("tools.install_test_browsers.install_archive") as install, mock.patch(
            "tools.install_test_browsers.verify_safari_version"
        ) as safari:
            install.side_effect = (
                Path(temporary) / "chromium",
                Path(temporary) / "firefox",
            )
            self.assertEqual(
                install_main([
                    "--matrix", str(root / "tests/browser-matrix.json"),
                    "--cache", temporary,
                ]),
                0,
            )
            self.assertEqual(install.call_count, 2)
            self.assertEqual(
                [call.args[0].version for call in install.call_args_list],
                ["151.0.7922.71", "153.0.1"],
            )
            safari.assert_called_once()

    def test_macos_bundle_requires_signature_gatekeeper_arm64_and_exact_version(self) -> None:
        executable = Path(
            "/cache/Browser.app/Contents/MacOS/browser"
        )
        with mock.patch("tools.install_test_browsers.subprocess.run") as run:
            run.side_effect = (
                mock.Mock(stdout=""),
                mock.Mock(stdout=""),
                mock.Mock(stdout="arm64\n"),
                mock.Mock(stdout="Browser 123.0.1\n"),
            )
            verify_macos_browser_bundle(
                executable,
                expected_version="123.0.1",
                signature_policy="developer-id",
                executable_sha256=None,
            )
            self.assertEqual(
                [call.args[0][0] for call in run.call_args_list],
                ["/usr/bin/codesign", "/usr/sbin/spctl", "/usr/bin/lipo", str(executable)],
            )
        with mock.patch(
            "tools.install_test_browsers.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, ["codesign"]),
        ), self.assertRaises(BrowserMatrixError):
            verify_macos_browser_bundle(
                executable,
                expected_version="123.0.1",
                signature_policy="developer-id",
                executable_sha256=None,
            )

    def test_cft_adhoc_policy_pins_executable_and_exact_signature_metadata(self) -> None:
        with TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "Chrome.app/Contents/MacOS"
            bundle.mkdir(parents=True)
            executable = bundle / "Chrome"
            executable.write_bytes(b"exact executable")
            digest = hashlib.sha256(executable.read_bytes()).hexdigest()
            metadata = "Signature=adhoc\nTeamIdentifier=not set\nSealed Resources=none\n"
            expected_failure = "code has no resources but signature indicates they must be present"
            with mock.patch("tools.install_test_browsers.subprocess.run") as run:
                run.side_effect = (
                    mock.Mock(stdout="", stderr=metadata, returncode=0),
                    mock.Mock(stdout="", stderr=expected_failure, returncode=1),
                    mock.Mock(stdout="", stderr=expected_failure, returncode=1),
                    mock.Mock(stdout="arm64\n", stderr="", returncode=0),
                    mock.Mock(stdout="Google Chrome for Testing 123.0.1\n", stderr="", returncode=0),
                )
                verify_macos_browser_bundle(
                    executable,
                    expected_version="123.0.1",
                    signature_policy="adhoc-cft",
                    executable_sha256=digest,
                )
            with mock.patch("tools.install_test_browsers.subprocess.run") as run:
                run.return_value = mock.Mock(
                    stdout="", stderr=metadata.replace("not set", "TEAM123"), returncode=0
                )
                with self.assertRaises(BrowserMatrixError):
                    verify_macos_browser_bundle(
                        executable,
                        expected_version="123.0.1",
                        signature_policy="adhoc-cft",
                        executable_sha256=digest,
                    )


if __name__ == "__main__":
    unittest.main()
