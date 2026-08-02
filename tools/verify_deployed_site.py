#!/usr/bin/env python3
"""Verify a deployed Pages site against its canonical release manifest."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import posixpath
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from tools.verify_release_manifest import (
    MAX_FILE_BYTES,
    MAX_MANIFEST_BYTES,
    MAX_TOTAL_BYTES,
    ReleaseManifest,
    ReleaseManifestError,
    parse_manifest_bytes,
)


class DeployedSiteError(ValueError):
    """The deployed site failed its bounded verification contract."""


@dataclass(frozen=True, slots=True)
class FetchPolicy:
    timeout_seconds: float = 10.0
    total_seconds: float = 90.0
    max_redirects: int = 3
    max_retries: int = 2
    max_manifest_bytes: int = MAX_MANIFEST_BYTES
    max_file_bytes: int = MAX_FILE_BYTES
    max_total_bytes: int = MAX_TOTAL_BYTES

    def validate(self) -> None:
        values = (
            self.timeout_seconds,
            self.total_seconds,
            self.max_redirects,
            self.max_retries,
            self.max_manifest_bytes,
            self.max_file_bytes,
            self.max_total_bytes,
        )
        if any(type(value) not in {int, float} or value <= 0 for value in values):
            raise DeployedSiteError("fetch policy must contain positive fixed bounds")
        if type(self.max_redirects) is not int or type(self.max_retries) is not int:
            raise DeployedSiteError("redirect and retry bounds must be integers")


def _validated_base(raw: str):
    if type(raw) is not str:
        raise DeployedSiteError("Pages base URL must be a string")
    parsed = urlsplit(raw)
    try:
        port = parsed.port
    except ValueError as error:
        raise DeployedSiteError("Pages base URL has an invalid port") from error
    hostname = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or not hostname.endswith(".github.io")
        or hostname == ".github.io"
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.query
        or parsed.fragment
        or not parsed.path.endswith("/")
    ):
        raise DeployedSiteError("Pages base URL is outside the allowed HTTPS origin")
    decoded = unquote(parsed.path)
    if "%" in decoded or "\\" in decoded or decoded != posixpath.normpath(decoded) + "/":
        raise DeployedSiteError("Pages base path is not canonical")
    return parsed


def _validate_scoped_url(raw: str, base) -> str:
    parsed = urlsplit(raw)
    try:
        port = parsed.port
    except ValueError as error:
        raise DeployedSiteError("deployed URL has an invalid port") from error
    if (
        parsed.scheme != "https"
        or parsed.hostname != base.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.query
        or parsed.fragment
    ):
        raise DeployedSiteError("deployed URL escaped the Pages origin")
    decoded = unquote(parsed.path)
    if "%" in decoded or "\\" in decoded or not decoded.startswith(base.path):
        raise DeployedSiteError("deployed URL escaped the Pages subpath")
    relative = decoded[len(base.path) :]
    if not relative or relative.startswith("/") or posixpath.normpath(relative) != relative:
        raise DeployedSiteError("deployed URL path is not canonical")
    return raw


class _ScopedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, base, maximum: int) -> None:
        super().__init__()
        self.base = base
        self.maximum = maximum
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if self.count > self.maximum:
            raise DeployedSiteError("deployed request exceeded its redirect budget")
        absolute_url = urljoin(req.full_url, newurl)
        _validate_scoped_url(absolute_url, self.base)
        return super().redirect_request(req, fp, code, msg, headers, absolute_url)


def _fetch(url: str, *, base, opener, policy: FetchPolicy, maximum: int, deadline: float) -> bytes:
    _validate_scoped_url(url, base)
    last_error: Exception | None = None
    for _attempt in range(policy.max_retries + 1):
        if time.monotonic() >= deadline:
            raise DeployedSiteError("deployed verification exceeded its total deadline")
        request = Request(
            url,
            headers={
                "Accept-Encoding": "identity",
                "User-Agent": "engineering-expert-curriculum-verifier/1",
            },
        )
        response = None
        try:
            response = opener.open(request, timeout=policy.timeout_seconds)
            if getattr(response, "status", 200) != 200:
                raise DeployedSiteError("deployed request returned a non-success status")
            _validate_scoped_url(response.geturl(), base)
            headers = response.headers
            encoding = headers.get("Content-Encoding") if hasattr(headers, "get") else None
            if encoding not in {None, "", "identity"}:
                raise DeployedSiteError("deployed response used an unsupported content encoding")
            length = headers.get("Content-Length") if hasattr(headers, "get") else None
            if length is not None:
                try:
                    declared = int(length)
                except (TypeError, ValueError) as error:
                    raise DeployedSiteError("deployed response has an invalid length") from error
                if declared < 0 or declared > maximum:
                    raise DeployedSiteError("deployed response exceeds its declared byte budget")
            chunks: list[bytes] = []
            remaining = maximum + 1
            while remaining:
                chunk = response.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                if type(chunk) is not bytes:
                    raise DeployedSiteError("deployed response returned non-byte content")
                chunks.append(chunk)
                remaining -= len(chunk)
                if time.monotonic() >= deadline:
                    raise DeployedSiteError("deployed verification exceeded its total deadline")
            body = b"".join(chunks)
            if len(body) > maximum or (length is not None and len(body) != declared):
                raise DeployedSiteError("deployed response was truncated or over budget")
            return body
        except HTTPError as error:
            if error.code not in {502, 503, 504}:
                raise DeployedSiteError("deployed request failed without a safe retry") from error
            last_error = error
            continue
        except (URLError, TimeoutError, ConnectionError) as error:
            last_error = error
            continue
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception as error:
                    raise DeployedSiteError(
                        "deployed response could not be closed safely"
                    ) from error
    raise DeployedSiteError("deployed request exhausted its retry budget") from last_error


def verify_deployed_site(
    base_url: str,
    manifest_url: str,
    *,
    expected_commit: str,
    policy: FetchPolicy = FetchPolicy(),
    opener=None,
) -> ReleaseManifest:
    policy.validate()
    base = _validated_base(base_url)
    expected_manifest_url = base_url + "release-manifest.json"
    if manifest_url != expected_manifest_url:
        raise DeployedSiteError("manifest URL must be the exact release-root URL")
    _validate_scoped_url(manifest_url, base)
    if opener is None:
        opener = build_opener(_ScopedRedirectHandler(base, policy.max_redirects))
    deadline = time.monotonic() + policy.total_seconds
    manifest_bytes = _fetch(
        manifest_url, base=base, opener=opener, policy=policy,
        maximum=policy.max_manifest_bytes, deadline=deadline,
    )
    try:
        manifest = parse_manifest_bytes(manifest_bytes, expected_commit=expected_commit)
    except ReleaseManifestError as error:
        raise DeployedSiteError("deployed manifest is invalid") from error
    total = 0
    for entry in manifest.files:
        artifact_url = base_url + quote(entry.path.as_posix(), safe="/")
        body = _fetch(
            artifact_url, base=base, opener=opener, policy=policy,
            maximum=min(policy.max_file_bytes, entry.bytes), deadline=deadline,
        )
        total += len(body)
        if total > policy.max_total_bytes:
            raise DeployedSiteError("deployed site exceeded its aggregate byte budget")
        if len(body) != entry.bytes or hashlib.sha256(body).hexdigest() != entry.sha256:
            raise DeployedSiteError("deployed artifact does not match the release manifest")
    final_manifest = _fetch(
        manifest_url, base=base, opener=opener, policy=policy,
        maximum=policy.max_manifest_bytes, deadline=deadline,
    )
    if final_manifest != manifest_bytes:
        raise DeployedSiteError("deployed manifest changed during verification")
    return manifest


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--manifest-url")
    parser.add_argument("--expected-commit", required=True)
    options = parser.parse_args(arguments)
    manifest_url = options.manifest_url or options.base_url + "release-manifest.json"
    try:
        verify_deployed_site(
            options.base_url, manifest_url, expected_commit=options.expected_commit
        )
    except DeployedSiteError as error:
        print(f"deployed site verification failed: {error}", file=sys.stderr)
        return 1
    except Exception:
        print("deployed site verification failed safely", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
