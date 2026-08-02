from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from urllib.error import HTTPError, URLError

from tools.create_release_manifest import create_manifest_bytes, write_release_manifest
from tools.verify_release_manifest import (
    ReleaseManifestError,
    parse_manifest_bytes,
    verify_release_manifest,
)
from tools.verify_deployed_site import DeployedSiteError, FetchPolicy, verify_deployed_site


COMMIT = "0123456789abcdef0123456789abcdef01234567"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _canonical(path: str = "index.html", source: bytes = b"hello") -> bytes:
    import hashlib

    return (
        json.dumps(
            {
                "schemaVersion": 1,
                "commit": COMMIT,
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


class _Response:
    def __init__(self, url: str, body: bytes, *, status: int = 200, headers=None):
        self.url = url
        self.body = body
        self.status = status
        self.headers = headers or {}
        self.offset = 0

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
        return None


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
            verify_deployed_site(self.BASE, manifest_url, expected_commit=COMMIT, opener=opener)

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
            verify_deployed_site(self.BASE, manifest_url, expected_commit=COMMIT, opener=opener)

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

    def test_does_not_retry_a_permanent_http_failure(self) -> None:
        manifest_url = self.BASE + "release-manifest.json"
        opener = _Opener(
            [
                HTTPError(manifest_url, 404, "not found", {}, None),
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


if __name__ == "__main__":
    unittest.main()
