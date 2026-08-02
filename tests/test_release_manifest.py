from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import tools.create_release_manifest as create_module
import tools.verify_deployed_site as deployed_module
import tools.verify_release_manifest as verifier_module
from tools.create_release_manifest import create_manifest_bytes, write_release_manifest
from tools.verify_release_manifest import (
    ReleaseManifest,
    ReleaseManifestError,
    parse_manifest_bytes,
    verify_release_manifest,
)
from tools.verify_deployed_site import DeployedSiteError, FetchPolicy, verify_deployed_site


COMMIT = "0123456789abcdef0123456789abcdef01234567"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _canonical(
    path: str = "index.html",
    source: bytes = b"hello",
    *,
    commit: str = COMMIT,
) -> bytes:
    import hashlib

    return (
        json.dumps(
            {
                "schemaVersion": 1,
                "commit": commit,
                "files": [
                    {
                        "path": path,
                        "bytes": len(source),
                        "sha256": hashlib.sha256(source).hexdigest(),
                    }
                ],
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


class ManifestSchemaTests(unittest.TestCase):
    def test_accepts_the_exact_canonical_schema(self) -> None:
        manifest = parse_manifest_bytes(_canonical(), expected_commit=COMMIT)
        self.assertEqual(manifest.commit, COMMIT)
        self.assertEqual(manifest.files[0].path.as_posix(), "index.html")

    def test_rejects_unknown_duplicate_and_wrong_typed_fields(self) -> None:
        invalid = (
            b'{"schemaVersion":1,"schemaVersion":1,"commit":"'
            + COMMIT.encode()
            + b'","files":[]}\n',
            b'{"schemaVersion":true,"commit":"' + COMMIT.encode() + b'","files":[]}\n',
            b'{"schemaVersion":1,"commit":"' + COMMIT.encode() + b'","files":[],"extra":1}\n',
        )
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ReleaseManifestError):
                parse_manifest_bytes(raw)

    def test_rejects_noncanonical_json_serialization(self) -> None:
        value = json.loads(_canonical())
        noncanonical = json.dumps(value, indent=2).encode("utf-8") + b"\n"
        with self.assertRaises(ReleaseManifestError):
            parse_manifest_bytes(noncanonical)

    def test_rejects_unsafe_duplicate_and_unsorted_paths(self) -> None:
        entry = {"path": "b.js", "bytes": 1, "sha256": "0" * 64}
        for paths in (("../a.js",), ("/a.js",), ("a\\b.js",), ("b.js", "a.js"), ("a.js", "a.js")):
            value = {
                "schemaVersion": 1,
                "commit": COMMIT,
                "files": [{**entry, "path": path} for path in paths],
            }
            with self.subTest(paths=paths), self.assertRaises(ReleaseManifestError):
                parse_manifest_bytes(json.dumps(value).encode())

    def test_rejects_oversized_manifest_and_expected_commit_mismatch(self) -> None:
        with self.assertRaises(ReleaseManifestError):
            parse_manifest_bytes(b" " * (128 * 1024 + 1))
        with self.assertRaises(ReleaseManifestError):
            parse_manifest_bytes(_canonical(), expected_commit="f" * 40)

    def test_deep_json_is_normalized_to_the_typed_manifest_error(self) -> None:
        deeply_nested = b"[" * 10_000 + b"0" + b"]" * 10_000
        with self.assertRaises(ReleaseManifestError):
            parse_manifest_bytes(deeply_nested)


class LocalManifestTests(unittest.TestCase):
    def test_manifest_clis_start_from_an_unrelated_working_directory(self) -> None:
        scripts = (
            "create_release_manifest.py",
            "verify_release_manifest.py",
            "verify_deployed_site.py",
        )
        with TemporaryDirectory() as directory:
            for script in scripts:
                with self.subTest(script=script):
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(REPOSITORY_ROOT / "tools" / script),
                            "--help",
                        ],
                        cwd=directory,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_generator_is_deterministic_and_local_verifier_covers_all_assets(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "static").mkdir()
            (root / "index.html").write_bytes(b"<h1>ok</h1>\n")
            (root / "styles.css").write_bytes(b"body{}\n")
            (root / "static" / "app.js").write_bytes(b"'use strict';\n")
            first = create_manifest_bytes(root, commit=COMMIT)
            second = create_manifest_bytes(root, commit=COMMIT)
            self.assertEqual(first, second)
            manifest_path = root / "release-manifest.json"
            write_release_manifest(root, manifest_path, commit=COMMIT)
            manifest = verify_release_manifest(
                root, manifest_path, expected_commit=COMMIT
            )
            self.assertEqual(
                tuple(entry.path.as_posix() for entry in manifest.files),
                ("index.html", "static/app.js", "styles.css"),
            )

    def test_verifier_rejects_missing_extra_and_mutated_assets(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            asset = root / "index.html"
            asset.write_bytes(b"hello")
            manifest = root / "release-manifest.json"
            manifest.write_bytes(_canonical())
            self.assertEqual(verify_release_manifest(root, manifest).commit, COMMIT)
            asset.write_bytes(b"changed")
            with self.assertRaises(ReleaseManifestError):
                verify_release_manifest(root, manifest)
            asset.write_bytes(b"hello")
            (root / "extra.css").write_bytes(b"x")
            with self.assertRaises(ReleaseManifestError):
                verify_release_manifest(root, manifest)

    def test_generator_rejects_links_special_files_and_unexpected_types(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            asset = root / "index.html"
            asset.write_bytes(b"hello")
            link = root / "linked.html"
            link.symlink_to(asset)
            with self.assertRaises(ReleaseManifestError):
                create_manifest_bytes(root, commit=COMMIT)
            link.unlink()
            os.link(asset, root / "hard.html")
            with self.assertRaises(ReleaseManifestError):
                create_manifest_bytes(root, commit=COMMIT)
            (root / "hard.html").unlink()
            (root / "unexpected.json").write_bytes(b"{}")
            with self.assertRaises(ReleaseManifestError):
                create_manifest_bytes(root, commit=COMMIT)

    def test_walk_rejects_a_nested_parent_swap_before_file_open(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "site"
            nested = root / "nested"
            outside = base / "outside"
            nested.mkdir(parents=True)
            outside.mkdir()
            (nested / "a.html").write_bytes(b"trusted")
            (outside / "a.html").write_bytes(b"outside")
            original_open = verifier_module._open_descriptor
            swapped = False

            def racing_open(path, flags, *args, **kwargs):
                nonlocal swapped
                candidate = os.fspath(path)
                if not swapped and (
                    candidate == os.fspath(nested / "a.html")
                    or (candidate == "a.html" and kwargs.get("dir_fd") is not None)
                ):
                    swapped = True
                    nested.rename(root / "old")
                    nested.symlink_to(outside, target_is_directory=True)
                return original_open(path, flags, *args, **kwargs)

            with patch.object(
                verifier_module,
                "_open_descriptor",
                side_effect=racing_open,
            ):
                with self.assertRaises(ReleaseManifestError):
                    create_manifest_bytes(root, commit=COMMIT)

    def test_walk_fails_closed_without_nofollow_support(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_bytes(b"hello")
            with patch.object(verifier_module.os, "O_NOFOLLOW", None):
                with self.assertRaises(ReleaseManifestError):
                    create_manifest_bytes(root, commit=COMMIT)

    def test_walk_rejects_directory_membership_change_after_scan(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_bytes(b"hello")
            original_open = verifier_module._open_descriptor
            injected = False

            def racing_open(path, flags, *args, **kwargs):
                nonlocal injected
                if (
                    not injected
                    and os.fspath(path) == "index.html"
                    and kwargs.get("dir_fd") is not None
                ):
                    injected = True
                    (root / "late.css").write_bytes(b"body{}")
                return original_open(path, flags, *args, **kwargs)

            with patch.object(
                verifier_module,
                "_open_descriptor",
                side_effect=racing_open,
            ):
                with self.assertRaises(ReleaseManifestError):
                    create_manifest_bytes(root, commit=COMMIT)

    def test_publication_rejects_root_swap_immediately_after_scan(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "site"
            root.mkdir()
            (root / "index.html").write_bytes(b"trusted")
            moved_root = base / "moved-site"
            original_scan = create_module.scan_release_files_at

            def scan_then_swap(descriptor, binding):
                files = original_scan(descriptor, binding)
                root.rename(moved_root)
                root.mkdir()
                (root / "index.html").write_bytes(b"replacement")
                return files

            with patch.object(
                create_module,
                "scan_release_files_at",
                side_effect=scan_then_swap,
            ):
                with self.assertRaises(ReleaseManifestError):
                    write_release_manifest(
                        root,
                        root / "release-manifest.json",
                        commit=COMMIT,
                    )
            self.assertFalse((moved_root / "release-manifest.json").exists())
            self.assertFalse((root / "release-manifest.json").exists())

    def test_parent_fsync_failure_is_an_explicit_post_commit_error(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_bytes(b"hello")
            manifest = root / "release-manifest.json"
            original_fsync = os.fsync
            calls = 0

            def fail_parent_fsync(descriptor):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected parent fsync failure")
                return original_fsync(descriptor)

            with patch.object(create_module.os, "fsync", side_effect=fail_parent_fsync):
                with self.assertRaises(ReleaseManifestError) as raised:
                    write_release_manifest(root, manifest, commit=COMMIT)
            self.assertTrue(getattr(raised.exception, "published", False))
            self.assertEqual(calls, 2)
            self.assertEqual(verify_release_manifest(root, manifest).commit, COMMIT)

    def test_publication_rejects_root_swap_during_parent_fsync(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "site"
            root.mkdir()
            (root / "index.html").write_bytes(b"hello")
            manifest = root / "release-manifest.json"
            original_fsync = os.fsync
            calls = 0

            def swap_during_parent_fsync(descriptor):
                nonlocal calls
                calls += 1
                if calls == 2:
                    root.rename(base / "published-site")
                    root.mkdir()
                return original_fsync(descriptor)

            with patch.object(
                create_module.os,
                "fsync",
                side_effect=swap_during_parent_fsync,
            ):
                with self.assertRaises(ReleaseManifestError) as raised:
                    write_release_manifest(root, manifest, commit=COMMIT)
            self.assertTrue(getattr(raised.exception, "published", False))
            self.assertTrue((base / "published-site" / manifest.name).is_file())

    def test_post_replace_root_metadata_failure_is_a_post_commit_error(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_bytes(b"hello")
            manifest = root / "release-manifest.json"
            original_replace = os.replace
            original_lstat = os.lstat
            replaced = False

            def tracked_replace(*args, **kwargs):
                nonlocal replaced
                original_replace(*args, **kwargs)
                replaced = True

            def fail_after_replace(path):
                if replaced and Path(path) == root:
                    raise OSError("injected post-replace metadata failure")
                return original_lstat(path)

            with (
                patch.object(create_module.os, "replace", side_effect=tracked_replace),
                patch.object(create_module.os, "lstat", side_effect=fail_after_replace),
            ):
                with self.assertRaises(
                    create_module.ReleaseManifestPostCommitError
                ) as raised:
                    write_release_manifest(root, manifest, commit=COMMIT)
            self.assertTrue(raised.exception.published)
            self.assertTrue(manifest.is_file())


class _Response:
    def __init__(
        self,
        url: str,
        body: bytes,
        *,
        status: int = 200,
        headers=None,
        close_error: Exception | None = None,
    ):
        self.url = url
        self.body = body
        self.status = status
        self.headers = headers or {}
        self.offset = 0
        self.close_error = close_error
        self.close_count = 0

    def read(self, size: int = -1) -> bytes:
        if self.offset >= len(self.body):
            return b""
        end = len(self.body) if size < 0 else min(len(self.body), self.offset + size)
        chunk = self.body[self.offset:end]
        self.offset = end
        return chunk

    def geturl(self) -> str:
        return self.url

    def close(self) -> None:
        self.close_count += 1
        if self.close_error is not None:
            raise self.close_error


class _TrackedHTTPError(HTTPError):
    def __init__(self, url: str, code: int):
        super().__init__(url, code, "failure", {}, None)
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1


def _sleep_past_deadline() -> None:
    time.sleep(2)


def _return_before_deadline() -> str:
    return "ok"


def _return_large_valid_manifest() -> ReleaseManifest:
    value = {
        "schemaVersion": 1,
        "commit": COMMIT,
        "files": [
            {
                "path": f"assets/{index:04d}.js",
                "bytes": 0,
                "sha256": f"{index:064x}",
            }
            for index in range(900)
        ],
    }
    raw = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    return parse_manifest_bytes(raw, expected_commit=COMMIT)


class _Opener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request.full_url, timeout, request.headers))
        if not self.responses:
            raise AssertionError("unexpected request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class DeployedManifestTests(unittest.TestCase):
    BASE = "https://albert-einshutoin.github.io/engineering-expert-curriculum/"

    def test_verifies_manifest_artifacts_and_stable_manifest_bytes(self) -> None:
        manifest_url = self.BASE + "release-manifest.json"
        manifest = _canonical()
        opener = _Opener(
            [
                _Response(manifest_url, manifest),
                _Response(self.BASE + "index.html", b"hello"),
                _Response(manifest_url, manifest),
            ]
        )
        result = verify_deployed_site(
            self.BASE,
            manifest_url,
            expected_commit=COMMIT,
            opener=opener,
        )
        self.assertEqual(result.commit, COMMIT)
        self.assertEqual(len(opener.requests), 3)
        self.assertTrue(
            all(
                headers.get("Accept-encoding") == "identity"
                for _, _, headers in opener.requests
            )
        )

    def test_rejects_unsafe_origins_subpaths_and_redirected_final_urls(self) -> None:
        manifest_url = self.BASE + "release-manifest.json"
        for base, candidate in (
            (
                "http://example.github.io/repo/",
                "http://example.github.io/repo/release-manifest.json",
            ),
            (self.BASE, "https://attacker.invalid/release-manifest.json"),
            (self.BASE, "https://albert-einshutoin.github.io/other/release-manifest.json"),
        ):
            with self.subTest(candidate=candidate), self.assertRaises(DeployedSiteError):
                verify_deployed_site(base, candidate, expected_commit=COMMIT, opener=_Opener([]))
        opener = _Opener(
            [_Response("https://attacker.invalid/release-manifest.json", _canonical())]
        )
        with self.assertRaises(DeployedSiteError):
            verify_deployed_site(
                self.BASE,
                manifest_url,
                expected_commit=COMMIT,
                opener=opener,
            )

    def test_rejects_oversized_partial_and_mutating_responses(self) -> None:
        manifest_url = self.BASE + "release-manifest.json"
        small_policy = FetchPolicy(max_manifest_bytes=32)
        with self.assertRaises(DeployedSiteError):
            verify_deployed_site(
                self.BASE,
                manifest_url,
                expected_commit=COMMIT,
                policy=small_policy,
                opener=_Opener([_Response(manifest_url, _canonical())]),
            )
        opener = _Opener(
            [
                _Response(manifest_url, _canonical()),
                _Response(self.BASE + "index.html", b"hello"),
                _Response(manifest_url, _canonical(source=b"different")),
            ]
        )
        with self.assertRaises(DeployedSiteError):
            verify_deployed_site(
                self.BASE,
                manifest_url,
                expected_commit=COMMIT,
                policy=FetchPolicy(consistency_retries=0),
                opener=opener,
            )

    def test_retries_only_transient_transport_failures_with_a_fixed_bound(self) -> None:
        manifest_url = self.BASE + "release-manifest.json"
        manifest = _canonical()
        opener = _Opener(
            [
                URLError("temporary"),
                _Response(manifest_url, manifest),
                _Response(self.BASE + "index.html", b"hello"),
                _Response(manifest_url, manifest),
            ]
        )
        verify_deployed_site(self.BASE, manifest_url, expected_commit=COMMIT, opener=opener)
        self.assertEqual(len(opener.requests), 4)

    def test_eventual_consistency_retries_404_then_current_deployment(self) -> None:
        manifest_url = self.BASE + "release-manifest.json"
        not_found = _TrackedHTTPError(manifest_url, 404)
        opener = _Opener(
            [
                not_found,
                _Response(manifest_url, _canonical()),
                _Response(self.BASE + "index.html", b"hello"),
                _Response(manifest_url, _canonical()),
            ]
        )
        policy = FetchPolicy(consistency_retries=2, backoff_seconds=0.001)
        with patch.object(deployed_module.time, "sleep") as sleep:
            result = verify_deployed_site(
                self.BASE,
                manifest_url,
                expected_commit=COMMIT,
                policy=policy,
                opener=opener,
            )
        self.assertEqual(result.commit, COMMIT)
        self.assertEqual(not_found.close_count, 1)
        sleep.assert_called_once_with(0.001)

    def test_eventual_consistency_retries_old_commit_and_old_asset_hash(self) -> None:
        manifest_url = self.BASE + "release-manifest.json"
        old_commit = "f" * 40
        opener = _Opener(
            [
                _Response(manifest_url, _canonical(commit=old_commit)),
                _Response(manifest_url, _canonical()),
                _Response(self.BASE + "index.html", b"outdated"),
                _Response(manifest_url, _canonical()),
                _Response(self.BASE + "index.html", b"hello"),
                _Response(manifest_url, _canonical()),
            ]
        )
        policy = FetchPolicy(consistency_retries=3, backoff_seconds=0.001)
        with patch.object(deployed_module.time, "sleep") as sleep:
            result = verify_deployed_site(
                self.BASE,
                manifest_url,
                expected_commit=COMMIT,
                policy=policy,
                opener=opener,
            )
        self.assertEqual(result.commit, COMMIT)
        self.assertEqual(sleep.call_count, 2)

    def test_eventual_consistency_stops_at_the_retry_and_deadline_bounds(self) -> None:
        manifest_url = self.BASE + "release-manifest.json"
        failures = [_TrackedHTTPError(manifest_url, 404) for _ in range(3)]
        opener = _Opener(failures)
        policy = FetchPolicy(consistency_retries=2, backoff_seconds=0.001)
        with patch.object(deployed_module.time, "sleep"):
            with self.assertRaises(DeployedSiteError):
                verify_deployed_site(
                    self.BASE,
                    manifest_url,
                    expected_commit=COMMIT,
                    policy=policy,
                    opener=opener,
                )
        self.assertEqual(len(opener.requests), 3)
        self.assertTrue(all(error.close_count == 1 for error in failures))

    def test_policy_rejects_nonfinite_fractional_and_wrong_typed_bounds(self) -> None:
        invalid = (
            FetchPolicy(total_seconds=float("inf")),
            FetchPolicy(total_seconds=float("nan")),
            FetchPolicy(max_manifest_bytes=1024.5),
            FetchPolicy(max_file_bytes=float("inf")),
            FetchPolicy(max_total_bytes=True),
            FetchPolicy(consistency_retries=-1),
        )
        for policy in invalid:
            with self.subTest(policy=policy), self.assertRaises(DeployedSiteError):
                policy.validate()
        with self.assertRaises(DeployedSiteError):
            verify_deployed_site(
                self.BASE,
                self.BASE + "release-manifest.json",
                expected_commit=123,
                opener=_Opener([]),
            )

    def test_eof_after_deadline_is_rejected_and_hard_boundary_can_terminate(self) -> None:
        class SlowEof(_Response):
            def read(self, size: int = -1) -> bytes:
                time.sleep(0.03)
                return b""

        url = self.BASE + "release-manifest.json"
        policy = FetchPolicy(timeout_seconds=0.01, total_seconds=0.01)
        start = time.monotonic()
        with self.assertRaises(DeployedSiteError):
            deployed_module._fetch(
                url,
                base=deployed_module._validated_base(self.BASE),
                opener=_Opener([SlowEof(url, b"")]),
                policy=policy,
                maximum=1,
                deadline=start + policy.total_seconds,
            )
        with self.assertRaises(DeployedSiteError):
            deployed_module._run_with_hard_deadline(_sleep_past_deadline, 0.05)
        self.assertEqual(
            deployed_module._run_with_hard_deadline(_return_before_deadline, 2.0),
            "ok",
        )
        self.assertLess(time.monotonic() - start, 0.75)

    def test_hard_deadline_drains_a_large_valid_worker_result(self) -> None:
        result = deployed_module._run_with_hard_deadline(
            _return_large_valid_manifest,
            2.0,
        )
        self.assertEqual(result.commit, COMMIT)
        self.assertEqual(len(result.files), 900)

    def test_http_and_response_close_are_exactly_once_and_preserve_primary(self) -> None:
        manifest_url = self.BASE + "release-manifest.json"
        transient = _TrackedHTTPError(manifest_url, 503)
        opener = _Opener(
            [
                transient,
                _Response(manifest_url, _canonical()),
                _Response(self.BASE + "index.html", b"hello"),
                _Response(manifest_url, _canonical()),
            ]
        )
        verify_deployed_site(self.BASE, manifest_url, expected_commit=COMMIT, opener=opener)
        self.assertEqual(transient.close_count, 1)

        invalid = _Response(
            manifest_url,
            b"",
            status=500,
            close_error=OSError("secondary close failure"),
        )
        with self.assertRaises(DeployedSiteError):
            try:
                verify_deployed_site(
                    self.BASE,
                    manifest_url,
                    expected_commit=COMMIT,
                    opener=_Opener([invalid]),
                )
            except DeployedSiteError as error:
                self.assertIn("non-success status", str(error))
                raise
        self.assertEqual(invalid.close_count, 1)

    def test_does_not_retry_other_permanent_http_failures(self) -> None:
        manifest_url = self.BASE + "release-manifest.json"
        forbidden = _TrackedHTTPError(manifest_url, 403)
        opener = _Opener(
            [
                forbidden,
                AssertionError("a permanent failure must not be retried"),
            ]
        )
        with self.assertRaises(DeployedSiteError):
            verify_deployed_site(
                self.BASE,
                manifest_url,
                expected_commit=COMMIT,
                opener=opener,
            )
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(forbidden.close_count, 1)


if __name__ == "__main__":
    unittest.main()
