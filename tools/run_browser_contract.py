#!/usr/bin/env python3
"""Run bounded browser contracts over local-file and Pages-style URLs."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import base64
import errno
from functools import partial
import hashlib
from http.client import RemoteDisconnected
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import socket
import statistics
import struct
import subprocess
import sys
import tempfile
from threading import Thread
import time
from typing import Iterator, Mapping, Sequence
from urllib.parse import quote, unquote_to_bytes, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.install_test_browsers import (
    BrowserMatrixError,
    BrowserProfile,
    install_archive,
    load_browser_matrix,
    resolve_platform,
    verify_safari_version,
)


@dataclass(frozen=True, slots=True)
class LoopbackServer:
    host: str
    port: int


@dataclass(frozen=True, slots=True)
class EvidenceInventory:
    dynamic_lessons: tuple[str, ...]
    diagram_type_lessons: Mapping[str, str]
    regression_states: tuple[tuple[str, str], ...]
    profiles: tuple[str, ...]


class _PagesHandler(SimpleHTTPRequestHandler):
    prefix = "/engineering-expert-curriculum/"

    def translate_path(self, path: str) -> str:
        if not path.startswith(self.prefix):
            return str(Path(self.directory) / ".browser-contract-not-found")
        return super().translate_path("/" + path.removeprefix(self.prefix))

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def serve_site(site: Path) -> Iterator[LoopbackServer]:
    root = site.resolve(strict=True)
    if not root.is_dir():
        raise BrowserMatrixError("site must be an existing directory")
    handler = partial(_PagesHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, name="browser-contract-http", daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        if host != "127.0.0.1" or not isinstance(port, int) or port <= 0:
            raise BrowserMatrixError("loopback server did not bind an ephemeral port")
        yield LoopbackServer(host, port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        if thread.is_alive():
            raise BrowserMatrixError("loopback server did not stop within its timeout")


def browser_urls(site: Path, lesson: Path, port: int) -> tuple[str, str]:
    root = site.resolve(strict=True)
    target = lesson.resolve(strict=True)
    try:
        relative = target.relative_to(root)
    except ValueError as error:
        raise BrowserMatrixError("browser target escapes the site root") from error
    if not 1 <= port <= 65535:
        raise BrowserMatrixError("loopback port is invalid")
    return (
        target.as_uri(),
        f"http://127.0.0.1:{port}/engineering-expert-curriculum/{relative.as_posix()}",
    )


def interactive_page_url(port: int, page: str) -> str:
    if type(port) is not int or not 1 <= port <= 65_535:
        raise BrowserMatrixError("interactive page server port is invalid")
    if page not in {"map3d", "progress", "daily"}:
        raise BrowserMatrixError("interactive page identity is invalid")
    return f"http://127.0.0.1:{port}{_PagesHandler.prefix}{page}.html"


def browser_evidence_inventory(catalog_bytes: bytes) -> EvidenceInventory:
    if type(catalog_bytes) is not bytes or not catalog_bytes or len(catalog_bytes) > 128 * 1024:
        raise BrowserMatrixError("visualization catalog is unavailable or over budget")
    try:
        value = json.loads(catalog_bytes.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BrowserMatrixError("visualization catalog is not valid UTF-8 JSON") from error
    if type(value) is not dict or set(value) != {"version", "lessons"} or value["version"] != 1:
        raise BrowserMatrixError("visualization catalog root drifted")
    lessons = value["lessons"]
    if type(lessons) is not list or len(lessons) != 30:
        raise BrowserMatrixError("visualization catalog must contain exactly 30 lessons")
    dynamic: list[str] = []
    types: dict[str, str] = {}
    states: list[tuple[str, str]] = []
    for row in lessons:
        if type(row) is not dict:
            raise BrowserMatrixError("visualization catalog row is not an object")
        lesson_id = row.get("lessonId")
        primary = row.get("primaryType")
        if type(lesson_id) is not str or type(primary) is not str:
            raise BrowserMatrixError("visualization catalog row identifiers are invalid")
        types.setdefault(primary, lesson_id)
        if row.get("dynamic") is True:
            simulation = row.get("simulation")
            if type(simulation) is not dict:
                raise BrowserMatrixError("dynamic visualization row lacks its simulation")
            regression = simulation.get("visualRegressionStateIds")
            if type(regression) is not list or len(regression) != 3 or any(type(item) is not str for item in regression):
                raise BrowserMatrixError("dynamic visualization row must pin three regression states")
            dynamic.append(lesson_id)
            states.extend((lesson_id, item) for item in regression)
    required_types = {"flow", "hierarchy", "comparison", "state-loop", "causal", "timeline", "network", "memory", "matrix", "state-machine"}
    if len(dynamic) != 12 or set(types) != required_types or len(states) != 36:
        raise BrowserMatrixError("browser evidence inventory is incomplete")
    return EvidenceInventory(
        tuple(dynamic), types, tuple(states),
        ("desktop", "mobile", "reduced-motion", "forced-colors"),
    )


def chromium_arguments(
    executable: Path,
    url: str,
    profile: Mapping[str, object],
    user_data_directory: Path,
    *,
    oci_container_no_sandbox: bool = False,
) -> list[str]:
    if urlsplit(url).scheme not in {"file", "http"}:
        raise BrowserMatrixError("browser URL must be local file or loopback HTTP")
    width = profile.get("width")
    height = profile.get("height")
    scale = profile.get("deviceScaleFactor")
    if type(width) is not int or type(height) is not int or type(scale) is not int:
        raise BrowserMatrixError("browser profile dimensions are invalid")
    arguments = [
        str(executable), "--headless=new", "--disable-gpu", "--no-first-run",
        "--no-default-browser-check", "--remote-debugging-port=0",
        f"--user-data-dir={user_data_directory}",
        f"--window-size={width},{height}", f"--force-device-scale-factor={scale}",
        "--enable-precise-memory-info", "--js-flags=--expose-gc", "about:blank",
    ]
    if oci_container_no_sandbox:
        if not sys.platform.startswith("linux"):
            raise BrowserMatrixError("OCI no-sandbox opt-in is Linux-only")
        # The explicit CI-only opt-in is valid for the matrix-pinned, non-root
        # container. Local Linux retains Chromium's nested sandbox by default.
        arguments.insert(3, "--no-sandbox")
    return arguments


class _ResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id") == "browser-contract-result" and values.get("data-browser-contract-result") is not None:
            self.values.append(values["data-browser-contract-result"] or "")


_RESULT_KEYS = frozenset({
    "schemaVersion", "harnessVersion", "passed", "simulationCount",
    "reachedStateIds", "requestedStateReached", "runtimeEnhancedCount",
    "runtimeErrorCount", "runtimeErrors", "warmupsMs", "samplesMs",
    "workloadMutationSamples", "longTasksMs", "observedLongTasksMs",
    "resetCycles", "baseline", "final", "instrumentation", "violations",
    "violationKinds", "externalResources", "resourceNames", "truncated",
})
_ERROR_RESULT_KEYS = frozenset({
    "schemaVersion", "harnessVersion", "passed", "violations",
    "violationKinds", "truncated",
})


def _bounded_strings(value: object, *, maximum: int, length: int) -> bool:
    return type(value) is list and len(value) <= maximum and all(
        type(item) is str and len(item) <= length for item in value
    )


def _validate_success_result(result: dict[str, object]) -> None:
    if frozenset(result) != _RESULT_KEYS:
        raise BrowserMatrixError("browser harness success result fields drifted")
    integer_fields = ("simulationCount", "runtimeEnhancedCount", "runtimeErrorCount", "resetCycles")
    if any(type(result[name]) is not int or result[name] < 0 for name in integer_fields):
        raise BrowserMatrixError("browser harness integer result fields are invalid")
    if result["runtimeErrorCount"] != 0 or result["runtimeErrors"] != []:
        raise BrowserMatrixError("browser runtime reported an initialization error")
    if result["requestedStateReached"] is not True:
        raise BrowserMatrixError("browser requested-state result is invalid")
    if result["resetCycles"] != 100 or result["runtimeEnhancedCount"] != result["simulationCount"]:
        raise BrowserMatrixError("browser runtime enhancement or reset evidence drifted")
    if not _bounded_strings(result["reachedStateIds"], maximum=64, length=64):
        raise BrowserMatrixError("browser reached-state evidence is invalid")
    if not _bounded_strings(result["resourceNames"], maximum=128, length=80):
        raise BrowserMatrixError("browser resource-name evidence is invalid")
    if not _bounded_strings(result["externalResources"], maximum=128, length=240):
        raise BrowserMatrixError("browser external-resource evidence is invalid")
    if result["violations"] != [] or result["violationKinds"] != []:
        raise BrowserMatrixError("browser harness success contains violations")
    for name, expected_length in (("warmupsMs", (0, 3)), ("samplesMs", (0, 20)), ("longTasksMs", (0, 20)), ("workloadMutationSamples", (0, 20))):
        value = result[name]
        if type(value) is not list or len(value) not in expected_length or any(
            type(item) not in (int, float) or not math.isfinite(float(item)) or float(item) < 0
            for item in value
        ):
            raise BrowserMatrixError("browser measurement result shape drifted")
    measured_lengths = tuple(
        len(result[name]) for name in ("samplesMs", "longTasksMs", "workloadMutationSamples")
    )
    if len(set(measured_lengths)) != 1 or (measured_lengths[0] == 20 and len(result["warmupsMs"]) != 3):
        raise BrowserMatrixError("browser measurement samples are not correlated")
    if any(type(item) is not int or item <= 0 for item in result["workloadMutationSamples"]):
        raise BrowserMatrixError("browser workload did not mutate product runtime state")
    observed = result["observedLongTasksMs"]
    if type(observed) is not list or len(observed) > 128 or any(
        type(item) not in (int, float) or not math.isfinite(float(item)) or float(item) < 0
        for item in observed
    ):
        raise BrowserMatrixError("browser observed Long Task evidence is invalid")
    count_keys = {"domNodes", "listeners", "timers", "heapBytes"}
    for name in ("baseline", "final"):
        value = result[name]
        if type(value) is not dict or set(value) != count_keys or any(
            type(value[key]) is not int or value[key] < 0
            for key in ("domNodes", "listeners", "timers")
        ) or type(value["heapBytes"]) is not int or value["heapBytes"] < -1:
            raise BrowserMatrixError("browser leak count evidence is invalid")
    if (result["baseline"]["heapBytes"] == -1) != (result["final"]["heapBytes"] == -1):
        raise BrowserMatrixError("browser heap availability changed during measurement")
    instrumentation = result["instrumentation"]
    if type(instrumentation) is not dict or set(instrumentation) != {"listeners", "timers", "gc", "longTasks"} or any(
        type(item) is not bool for item in instrumentation.values()
    ) or instrumentation["listeners"] is not True or instrumentation["timers"] is not True or instrumentation["longTasks"] is not True:
        raise BrowserMatrixError("browser instrumentation evidence is invalid")
    truncated = result["truncated"]
    if type(truncated) is not dict or set(truncated) != {"violations", "runtimeErrors", "longTasks", "externalResources", "resourceNames"} or any(
        value is not False for value in truncated.values()
    ):
        raise BrowserMatrixError("browser evidence was truncated")


def _validate_error_result(result: dict[str, object]) -> None:
    keys = frozenset(result)
    if keys not in {_ERROR_RESULT_KEYS, _RESULT_KEYS}:
        raise BrowserMatrixError("browser harness failure result fields drifted")
    if not _bounded_strings(result["violations"], maximum=128, length=200):
        raise BrowserMatrixError("browser harness failure violations are invalid")
    if not result["violations"] or not _bounded_strings(
        result["violationKinds"], maximum=128, length=40
    ):
        raise BrowserMatrixError("browser harness failure kinds are invalid")
    truncated = result["truncated"]
    if type(truncated) is not dict or set(truncated) != {
        "violations", "runtimeErrors", "longTasks", "externalResources", "resourceNames"
    } or any(type(value) is not bool for value in truncated.values()):
        raise BrowserMatrixError("browser harness failure truncation evidence is invalid")
    if keys == _ERROR_RESULT_KEYS:
        return
    if any(
        type(result[name]) is not int or result[name] < 0
        for name in ("simulationCount", "runtimeEnhancedCount", "runtimeErrorCount")
    ) or result["resetCycles"] != 100 or type(result["requestedStateReached"]) is not bool:
        raise BrowserMatrixError("browser harness failure counters are invalid")
    for name, maximum, length in (
        ("reachedStateIds", 64, 64), ("runtimeErrors", 128, 120),
        ("resourceNames", 128, 80), ("externalResources", 128, 240),
    ):
        if not _bounded_strings(result[name], maximum=maximum, length=length):
            raise BrowserMatrixError("browser harness failure string evidence is invalid")
    measurement_lengths: list[int] = []
    for name, allowed in (
        ("warmupsMs", {0, 3}), ("samplesMs", {0, 20}),
        ("longTasksMs", {0, 20}), ("workloadMutationSamples", {0, 20}),
    ):
        value = result[name]
        if type(value) is not list or len(value) not in allowed or any(
            type(item) not in (int, float) or not math.isfinite(float(item)) or float(item) < 0
            for item in value
        ):
            raise BrowserMatrixError("browser harness failure measurements are invalid")
        if name != "warmupsMs":
            measurement_lengths.append(len(value))
    if len(set(measurement_lengths)) != 1:
        raise BrowserMatrixError("browser harness failure measurements are uncorrelated")
    observed = result["observedLongTasksMs"]
    if type(observed) is not list or len(observed) > 128 or any(
        type(item) not in (int, float) or not math.isfinite(float(item)) or float(item) < 0
        for item in observed
    ):
        raise BrowserMatrixError("browser harness failure Long Task evidence is invalid")
    count_keys = {"domNodes", "listeners", "timers", "heapBytes"}
    for name in ("baseline", "final"):
        value = result[name]
        if type(value) is not dict or set(value) != count_keys or any(
            type(value[key]) is not int or value[key] < 0
            for key in ("domNodes", "listeners", "timers")
        ) or type(value["heapBytes"]) is not int or value["heapBytes"] < -1:
            raise BrowserMatrixError("browser harness failure leak evidence is invalid")
    instrumentation = result["instrumentation"]
    if type(instrumentation) is not dict or set(instrumentation) != {
        "listeners", "timers", "gc", "longTasks"
    } or any(type(value) is not bool for value in instrumentation.values()):
        raise BrowserMatrixError("browser harness failure instrumentation is invalid")


def parse_browser_result(dumped_html: str, *, expected_harness_version: str) -> dict[str, object]:
    if type(dumped_html) is not str or len(dumped_html.encode("utf-8")) > 1024 * 1024:
        raise BrowserMatrixError("dumped browser DOM is unavailable or over budget")
    parser = _ResultParser()
    try:
        parser.feed(dumped_html)
    except Exception as error:
        raise BrowserMatrixError("dumped browser DOM is malformed") from error
    if len(parser.values) != 1 or len(parser.values[0].encode("utf-8")) > 256 * 1024:
        raise BrowserMatrixError("browser harness result must occur exactly once and be bounded")
    try:
        result = json.loads(parser.values[0])
    except json.JSONDecodeError as error:
        raise BrowserMatrixError("browser harness result is not JSON") from error
    if type(result) is not dict or result.get("schemaVersion") != 1:
        raise BrowserMatrixError("browser harness result schema drifted")
    if result.get("harnessVersion") != expected_harness_version:
        raise BrowserMatrixError("browser harness version drifted")
    if result.get("passed") is True:
        _validate_success_result(result)
    elif result.get("passed") is False:
        _validate_error_result(result)
    if result.get("passed") is not True or type(result.get("violations")) is not list or result["violations"]:
        count = len(result.get("violations", ())) if type(result.get("violations")) is list else -1
        target = result.get("requestedStateReached") is True
        kinds = result.get("violationKinds")
        safe_kinds = tuple(item for item in kinds if item in {"csp", "error", "fetch", "XMLHttpRequest", "WebSocket", "EventSource", "window.open", "storage.setItem", "storage.removeItem", "storage.clear", "history.pushState", "history.replaceState", "navigation", "external-resource", "runtime-initialization", "runtime-error", "reset-restoration", "evidence-truncated", "harness"}) if type(kinds) is list else ()
        raise BrowserMatrixError(
            f"browser harness reported {count} bounded violations {safe_kinds}; requested-state-reached={target}"
        )
    return result


def _read_exact(stream: socket.socket, count: int) -> bytes:
    chunks: list[bytes] = []
    remaining = count
    while remaining:
        chunk = stream.recv(remaining)
        if not chunk:
            raise BrowserMatrixError("browser debugging socket closed unexpectedly")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class _BrowserDebuggingCommandError(BrowserMatrixError):
    def __init__(self, method: str, code: int | None, detail: str | None) -> None:
        self.method = method
        self.code = code
        self.detail = detail
        suffix = (
            f" ({code}: {detail})"
            if code == -32000 and detail == "Unable to capture screenshot"
            else ""
        )
        super().__init__(f"browser debugging command failed: {method}{suffix}")


class _ChromiumTargetTransportError(BrowserMatrixError):
    """A typed failure to exchange bytes with Chromium's loopback endpoint."""


class _WebSocket:
    def __init__(
        self,
        url: str,
        timeout: float,
        *,
        deadline: float | None = None,
    ) -> None:
        parsed = urlsplit(url)
        if parsed.scheme != "ws" or parsed.hostname != "127.0.0.1" or parsed.port is None:
            raise BrowserMatrixError("browser debugging endpoint is not loopback WebSocket")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise BrowserMatrixError("browser debugging timeout is invalid")
        if deadline is not None and (
            type(deadline) not in (int, float) or not math.isfinite(deadline)
        ):
            raise BrowserMatrixError("browser debugging deadline is invalid")

        def operation_timeout() -> float:
            if deadline is None:
                return float(timeout)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BrowserMatrixError(
                    "browser debugging WebSocket startup exceeded its deadline"
                )
            return min(float(timeout), remaining)

        self.socket = socket.create_connection(
            (parsed.hostname, parsed.port),
            timeout=operation_timeout(),
        )
        try:
            self.socket.settimeout(operation_timeout())
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            path = parsed.path + (("?" + parsed.query) if parsed.query else "")
            request = (
                f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{parsed.port}\r\n"
                f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode("ascii")
            self.socket.sendall(request)
            response = bytearray()
            while b"\r\n\r\n" not in response and len(response) <= 16 * 1024:
                self.socket.settimeout(operation_timeout())
                response.extend(self.socket.recv(4096))
            expected = base64.b64encode(
                hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
            ).decode("ascii")
            header = response.decode("latin-1", errors="strict")
            if not header.startswith("HTTP/1.1 101 ") or expected.lower() not in header.lower():
                raise BrowserMatrixError("browser debugging WebSocket handshake failed")
            # recv() may begin within the deadline and return a valid upgrade
            # only after it. Do not let that late success escape the startup
            # budget when restoring the ordinary per-command timeout.
            operation_timeout()
            self.socket.settimeout(timeout)
        except BaseException:
            self.close()
            raise
        self.identifier = 0
        self.events: list[dict[str, object]] = []
        self.events_truncated = False

    def close(self) -> None:
        try:
            self.socket.close()
        except OSError:
            return

    def _send_frame(self, payload: bytes, opcode: int = 1) -> None:
        if len(payload) > 1024 * 1024:
            raise BrowserMatrixError("browser debugging command exceeds its byte budget")
        mask = os.urandom(4)
        length = len(payload)
        if length < 126:
            header = bytes((0x80 | opcode, 0x80 | length))
        elif length <= 65535:
            header = bytes((0x80 | opcode, 0x80 | 126)) + struct.pack("!H", length)
        else:
            header = bytes((0x80 | opcode, 0x80 | 127)) + struct.pack("!Q", length)
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        self.socket.sendall(header + mask + masked)

    def _receive_frame(self) -> bytes:
        first, second = _read_exact(self.socket, 2)
        opcode = first & 0x0F
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", _read_exact(self.socket, 2))[0]
        elif length == 127:
            length = struct.unpack("!Q", _read_exact(self.socket, 8))[0]
        if length > 4 * 1024 * 1024:
            raise BrowserMatrixError("browser debugging response exceeds its byte budget")
        mask = _read_exact(self.socket, 4) if second & 0x80 else None
        payload = _read_exact(self.socket, length)
        if mask is not None:
            payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        if opcode == 8:
            raise BrowserMatrixError("browser debugging target closed unexpectedly")
        if opcode == 9:
            self._send_frame(payload, opcode=10)
            return self._receive_frame()
        if opcode != 1 or not first & 0x80:
            raise BrowserMatrixError("browser debugging response uses an unsupported frame")
        return payload

    def command(self, method: str, parameters: Mapping[str, object] | None = None) -> dict[str, object]:
        self.identifier += 1
        identifier = self.identifier
        payload = json.dumps(
            {"id": identifier, "method": method, "params": dict(parameters or {})},
            ensure_ascii=True, separators=(",", ":"),
        ).encode("utf-8")
        self._send_frame(payload)
        while True:
            try:
                message = json.loads(self._receive_frame().decode("utf-8", errors="strict"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise BrowserMatrixError("browser debugging response is invalid JSON") from error
            if type(message) is not dict:
                continue
            if message.get("id") != identifier:
                method_name = message.get("method")
                if type(method_name) is str and (
                    method_name.startswith("Network.")
                    or method_name in {
                        "Runtime.consoleAPICalled", "Runtime.exceptionThrown",
                    }
                ):
                    if len(self.events) < 256:
                        self.events.append(message)
                    else:
                        self.events_truncated = True
                continue
            if "error" in message:
                error = message.get("error")
                code: int | None = None
                detail: str | None = None
                if type(error) is dict:
                    raw_code = error.get("code")
                    raw_detail = error.get("message")
                    if type(raw_code) is int:
                        code = raw_code
                    if (
                        type(raw_detail) is str
                        and len(raw_detail) <= 128
                        and all(" " <= character <= "~" for character in raw_detail)
                    ):
                        detail = raw_detail
                raise _BrowserDebuggingCommandError(method, code, detail)
            if type(message.get("result")) is not dict:
                raise BrowserMatrixError(f"browser debugging command failed: {method}")
            return message["result"]


def _capture_chromium_screenshot(connection: _WebSocket) -> dict[str, object]:
    parameters = {"format": "png", "captureBeyondViewport": False}
    # Chromium can transiently return one empty compositor image under CI load.
    # Two short retries cover subsequent frames without hiding a persistent or
    # differently classified CDP failure.
    for attempt in range(3):
        try:
            return connection.command("Page.captureScreenshot", parameters)
        except _BrowserDebuggingCommandError as error:
            transient_empty_image = (
                error.method == "Page.captureScreenshot"
                and error.code == -32000
                and error.detail == "Unable to capture screenshot"
            )
            if not transient_empty_image or attempt == 2:
                raise
            time.sleep(0.1)
    raise AssertionError("closed Chromium screenshot retry loop did not terminate")


def _approved_file_path(url: str, approved_roots: Sequence[Path]) -> Path:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "file" or parsed.netloc != ""
        or parsed.query != "" or parsed.fragment != ""
        or any(token in parsed.path.lower() for token in ("%2e", "%2f", "%5c"))
    ):
        raise BrowserMatrixError("file browser resource URL is ambiguous")
    try:
        decoded = unquote_to_bytes(parsed.path).decode("utf-8", errors="strict")
        candidate = Path(decoded).resolve(strict=True)
    except (OSError, UnicodeError) as error:
        raise BrowserMatrixError("file browser resource path is unavailable") from error
    for root in approved_roots:
        try:
            approved = root.resolve(strict=True)
            candidate.relative_to(approved)
        except (OSError, ValueError):
            continue
        if approved.is_dir() and not approved.is_symlink():
            return candidate
    raise BrowserMatrixError("file browser resource escapes approved roots")


def _instrumented_harness_source(
    harness_source: str, *, approved_file_roots: Sequence[Path],
) -> str:
    roots: list[str] = []
    for root in approved_file_roots:
        try:
            resolved = root.resolve(strict=True)
        except OSError as error:
            raise BrowserMatrixError("approved browser file root is unavailable") from error
        if not resolved.is_dir() or resolved.is_symlink():
            raise BrowserMatrixError("approved browser file root must be a real directory")
        roots.append(resolved.as_uri().rstrip("/") + "/")
    descriptor = json.dumps(
        {"value": roots, "writable": False, "configurable": False},
        separators=(",", ":"),
    )
    return (
        "Object.defineProperty(window, '__browserContractApprovedFileRoots', "
        + descriptor + ");\n" + harness_source
    )


def validate_chromium_network_events(
    events: Sequence[Mapping[str, object]], *, target_url: str, truncated: bool,
    approved_file_roots: Sequence[Path] = (),
) -> None:
    if truncated or len(events) > 256:
        raise BrowserMatrixError("Chromium CDP network evidence was truncated")
    target = urlsplit(target_url)
    if target.scheme not in {"file", "http"}:
        raise BrowserMatrixError("Chromium network target is not local")
    if target.scheme == "http" and (target.hostname != "127.0.0.1" or target.port is None):
        raise BrowserMatrixError("Chromium HTTP target is not exact loopback origin")
    if target.scheme == "file":
        _approved_file_path(target_url, approved_file_roots)
    target_origin = (target.scheme, target.hostname, target.port)
    for event in events:
        if type(event) is not dict or type(event.get("method")) is not str or type(event.get("params")) is not dict:
            raise BrowserMatrixError("Chromium CDP network event shape drifted")
        method = event["method"]
        params = event["params"]
        candidate: object | None = None
        if method == "Network.requestWillBeSent" and type(params.get("request")) is dict:
            candidate = params["request"].get("url")
        elif method == "Network.responseReceived" and type(params.get("response")) is dict:
            candidate = params["response"].get("url")
        else:
            continue
        if type(candidate) is not str or len(candidate) > 2048:
            raise BrowserMatrixError("Chromium CDP network URL is invalid")
        parsed = urlsplit(candidate)
        if parsed.scheme == "data":
            continue
        if target.scheme == "file":
            if parsed.scheme == "file":
                _approved_file_path(candidate, approved_file_roots)
                allowed = True
            else:
                allowed = False
        else:
            allowed = (parsed.scheme, parsed.hostname, parsed.port) == target_origin
        if not allowed:
            raise BrowserMatrixError("Chromium requested a resource outside the exact target origin")


def _wait_debugging_port(
    directory: Path,
    process: subprocess.Popen[bytes],
    *,
    deadline: float,
) -> int:
    marker = directory / "DevToolsActivePort"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise BrowserMatrixError("Chromium exited before exposing its debugging endpoint")
        try:
            lines = marker.read_text(encoding="ascii").splitlines()
        except OSError:
            lines = []
        if lines and lines[0].isascii() and lines[0].isdecimal():
            port = int(lines[0])
            if 1 <= port <= 65535:
                return port
        time.sleep(min(0.025, max(0.0, deadline - time.monotonic())))
    raise BrowserMatrixError("Chromium debugging endpoint timed out")


def _exact_debugging_websocket(value: object, port: int, *, context: str) -> str:
    if type(value) is not str:
        raise BrowserMatrixError(f"{context} lacks its debugging URL")
    try:
        parsed = urlsplit(value)
        exact_loopback = (
            parsed.scheme == "ws"
            and parsed.hostname == "127.0.0.1"
            and parsed.port == port
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment
        )
    except ValueError:
        exact_loopback = False
    if not exact_loopback:
        raise BrowserMatrixError(f"{context} debugging URL is not exact loopback")
    return value


_TRANSIENT_CHROMIUM_ERRNOS = frozenset({
    errno.ECONNREFUSED,
    errno.ECONNRESET,
    errno.ECONNABORTED,
    errno.ETIMEDOUT,
})


def _is_transient_chromium_transport(error: OSError) -> bool:
    reason = error.reason if isinstance(error, URLError) else error
    return (
        isinstance(reason, (socket.timeout, RemoteDisconnected))
        or (
            isinstance(reason, OSError)
            and reason.errno in _TRANSIENT_CHROMIUM_ERRNOS
        )
    )


def _new_debugging_target(port: int, timeout: float) -> str:
    if type(port) is not int or not 1 <= port <= 65535:
        raise BrowserMatrixError("Chromium debugging port is invalid")
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise BrowserMatrixError("Chromium target timeout is invalid")
    request = Request(f"http://127.0.0.1:{port}/json/new?{quote('about:blank', safe='')}", method="PUT")
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read(64 * 1024 + 1)
    except HTTPError as error:
        # An HTTP response proves the endpoint is listening. Treat its status
        # as a protocol failure instead of hiding it behind readiness retries.
        raise BrowserMatrixError("Chromium target endpoint returned an HTTP error") from error
    except OSError as error:
        if _is_transient_chromium_transport(error):
            raise _ChromiumTargetTransportError(
                "Chromium target endpoint transport failed"
            ) from error
        raise BrowserMatrixError(
            "Chromium target endpoint transport failed permanently"
        ) from error
    if len(payload) > 64 * 1024:
        raise BrowserMatrixError("Chromium target response exceeds its byte budget")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BrowserMatrixError("Chromium target response is invalid") from error
    websocket_url = value.get("webSocketDebuggerUrl") if type(value) is dict else None
    return _exact_debugging_websocket(
        websocket_url,
        port,
        context="Chromium target response",
    )


def _probe_debugging_endpoint(port: int, timeout: float) -> None:
    if type(port) is not int or not 1 <= port <= 65535:
        raise BrowserMatrixError("Chromium debugging port is invalid")
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise BrowserMatrixError("Chromium readiness timeout is invalid")
    request = Request(f"http://127.0.0.1:{port}/json/version", method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read(64 * 1024 + 1)
    except HTTPError as error:
        raise BrowserMatrixError(
            "Chromium readiness endpoint returned an HTTP error"
        ) from error
    except OSError as error:
        if _is_transient_chromium_transport(error):
            raise _ChromiumTargetTransportError(
                "Chromium debugging endpoint is not ready"
            ) from error
        raise BrowserMatrixError(
            "Chromium readiness transport failed permanently"
        ) from error
    if len(payload) > 64 * 1024:
        raise BrowserMatrixError(
            "Chromium readiness response exceeds its byte budget"
        )
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BrowserMatrixError("Chromium readiness response is invalid") from error
    if type(value) is not dict:
        raise BrowserMatrixError("Chromium readiness response is invalid")
    _exact_debugging_websocket(
        value.get("webSocketDebuggerUrl"),
        port,
        context="Chromium readiness response",
    )


def _wait_debugging_endpoint(
    port: int,
    process: subprocess.Popen[bytes],
    *,
    deadline: float,
) -> None:
    """Retry only the idempotent marker-to-HTTP readiness probe."""
    last_transport_error: _ChromiumTargetTransportError | None = None
    while True:
        if process.poll() is not None:
            raise BrowserMatrixError(
                "Chromium exited before its debugging endpoint became ready"
            ) from last_transport_error
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise BrowserMatrixError(
                "Chromium debugging endpoint did not become ready before its deadline"
            ) from last_transport_error
        try:
            _probe_debugging_endpoint(port, min(remaining, 0.25))
            return
        except _ChromiumTargetTransportError as error:
            last_transport_error = error
        if process.poll() is not None:
            raise BrowserMatrixError(
                "Chromium exited before its debugging endpoint became ready"
            ) from last_transport_error
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise BrowserMatrixError(
                "Chromium debugging endpoint did not become ready before its deadline"
            ) from last_transport_error
        time.sleep(min(0.025, remaining))


def _connect_chromium_debugging(
    port: int,
    process: subprocess.Popen[bytes],
    *,
    deadline: float,
    timeout: float,
) -> _WebSocket:
    _wait_debugging_endpoint(port, process, deadline=deadline)
    if process.poll() is not None:
        raise BrowserMatrixError(
            "Chromium exited before creating its debugging target"
        )
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise BrowserMatrixError("Chromium target creation timed out")
    try:
        # PUT /json/new is intentionally single-shot: retrying after a lost
        # response could create an untracked duplicate target.
        websocket_url = _new_debugging_target(port, remaining)
    except BrowserMatrixError as error:
        if process.poll() is not None:
            raise BrowserMatrixError(
                "Chromium exited while creating its debugging target"
            ) from error
        raise
    if process.poll() is not None:
        raise BrowserMatrixError(
            "Chromium exited after creating its debugging target"
        )
    return _WebSocket(
        websocket_url,
        timeout,
        deadline=deadline,
    )


def _shutdown_chromium(
    process: subprocess.Popen[bytes], connection: _WebSocket | None,
) -> None:
    """Stop Chromium and its profile writers before removing their directory."""
    graceful_close_requested = False
    connection_close_error: BaseException | None = None
    if connection is not None:
        try:
            connection.socket.settimeout(5.0)
            connection.command("Browser.close")
            graceful_close_requested = True
        except (OSError, BrowserMatrixError):
            # A closed CDP socket commonly means Chromium already began exit.
            # The bounded process fallback below still proves the parent ended.
            graceful_close_requested = False
        finally:
            try:
                # _WebSocket.close owns ordinary socket errors, but an
                # interrupt must not skip the process shutdown below.
                connection.close()
            except BaseException as error:
                connection_close_error = error

    try:
        if graceful_close_requested:
            try:
                process.wait(timeout=5)
                if connection_close_error is not None:
                    raise connection_close_error
                return
            except subprocess.TimeoutExpired:
                pass
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    except (OSError, subprocess.SubprocessError) as error:
        failure = BrowserMatrixError("Chromium process cleanup failed")
        if connection_close_error is not None:
            failure.add_note(
                "Chromium debugging connection cleanup also failed: "
                f"{type(connection_close_error).__name__}: "
                f"{connection_close_error}"
            )
        raise failure from error
    if connection_close_error is not None:
        raise connection_close_error


def _remove_browser_profile(profile: Path) -> None:
    """Remove a private browser profile after bounded writer-race retries."""
    attempts = 50
    for attempt in range(attempts):
        try:
            shutil.rmtree(profile)
            return
        except FileNotFoundError:
            return
        except OSError as error:
            if error.errno not in {errno.ENOTEMPTY, errno.EBUSY}:
                raise BrowserMatrixError("Chromium profile cleanup failed") from error
            if attempt + 1 == attempts:
                raise BrowserMatrixError(
                    "Chromium profile cleanup remained busy after bounded retries"
                ) from error
            time.sleep(0.1)


def _cleanup_chromium_resources(
    *, process: subprocess.Popen[bytes] | None, connection: _WebSocket | None,
    profile: Path, primary_error: BaseException | None,
) -> None:
    cleanup_errors: list[BaseException] = []
    if process is not None:
        try:
            _shutdown_chromium(process, connection)
        except BaseException as error:
            cleanup_errors.append(error)
    try:
        _remove_browser_profile(profile)
    except BaseException as error:
        cleanup_errors.append(error)
    if not cleanup_errors:
        return
    if primary_error is not None:
        for error in cleanup_errors:
            primary_error.add_note(
                "Chromium cleanup also failed: "
                f"{type(error).__name__}: {error}"
            )
        return
    first, *remaining = cleanup_errors
    for error in remaining:
        first.add_note(
            "Additional Chromium cleanup failure: "
            f"{type(error).__name__}: {error}"
        )
    raise first


def run_chromium_page(
    *,
    executable: Path,
    url: str,
    profile: Mapping[str, object],
    harness_source: str,
    harness_version: str,
    screenshot: Path,
    approved_file_roots: Sequence[Path] = (),
    requested_state: str | None = None,
    measure_performance: bool = False,
    timeout: float = 30.0,
    oci_container_no_sandbox: bool = False,
) -> dict[str, object]:
    profile_directory = Path(tempfile.mkdtemp(prefix=".browser-profile-"))
    process: subprocess.Popen[bytes] | None = None
    connection: _WebSocket | None = None
    primary_error: BaseException | None = None
    try:
        args = chromium_arguments(
            executable, url, profile, profile_directory,
            oci_container_no_sandbox=oci_container_no_sandbox,
        )
        process = subprocess.Popen(
            args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, shell=False,
        )
        try:
            startup_deadline = time.monotonic() + timeout
            port = _wait_debugging_port(
                profile_directory,
                process,
                deadline=startup_deadline,
            )
            connection = _connect_chromium_debugging(
                port,
                process,
                deadline=startup_deadline,
                timeout=timeout,
            )
            connection.command("Page.enable")
            connection.command("Runtime.enable")
            connection.command("Network.enable")
            width = int(profile["width"])
            height = int(profile["height"])
            scale = int(profile["deviceScaleFactor"])
            throttle = int(profile["cpuThrottleRate"])
            connection.command("Emulation.setDeviceMetricsOverride", {
                "width": width, "height": height, "deviceScaleFactor": scale, "mobile": width <= 390,
            })
            connection.command("Emulation.setCPUThrottlingRate", {"rate": throttle})
            connection.command("Emulation.setEmulatedMedia", {
                "media": "screen",
                "features": [
                    {"name": "prefers-reduced-motion", "value": "reduce" if profile["reducedMotion"] else "no-preference"},
                    {"name": "forced-colors", "value": "active" if profile["forcedColors"] else "none"},
                ],
            })
            state_prefix = (
                "window.__browserContractRequestedState=" + json.dumps(requested_state) + ";\n"
                if requested_state is not None else ""
            )
            if measure_performance:
                state_prefix += "window.__browserContractMeasurePerformance=true;\n"
            connection.command("Page.addScriptToEvaluateOnNewDocument", {
                "source": state_prefix + _instrumented_harness_source(
                    harness_source, approved_file_roots=approved_file_roots,
                )
            })
            connection.command("Page.navigate", {"url": url})
            deadline = time.monotonic() + timeout
            result_value: str | None = None
            while time.monotonic() < deadline:
                evaluated = connection.command("Runtime.evaluate", {
                    "expression": "document.getElementById('browser-contract-result') && document.getElementById('browser-contract-result').getAttribute('data-browser-contract-result')",
                    "returnByValue": True,
                })
                remote = evaluated.get("result")
                if type(remote) is dict and type(remote.get("value")) is str:
                    result_value = remote["value"]
                    break
                time.sleep(0.05)
            if result_value is None:
                raise BrowserMatrixError("browser harness did not publish a result within its timeout")
            validate_chromium_network_events(
                connection.events, target_url=url,
                truncated=connection.events_truncated,
                approved_file_roots=approved_file_roots,
            )
            document = connection.command("DOM.getDocument", {"depth": 0})
            root = document.get("root")
            node_id = root.get("nodeId") if type(root) is dict else None
            if type(node_id) is not int:
                raise BrowserMatrixError("browser DOM root is unavailable")
            outer = connection.command("DOM.getOuterHTML", {"nodeId": node_id}).get("outerHTML")
            if type(outer) is not str:
                raise BrowserMatrixError("browser dumped DOM is unavailable")
            result = parse_browser_result(outer, expected_harness_version=harness_version)
            capture = _capture_chromium_screenshot(connection)
            encoded = capture.get("data")
            if type(encoded) is not str or len(encoded) > 16 * 1024 * 1024:
                raise BrowserMatrixError("browser screenshot is unavailable or over budget")
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            screenshot.write_bytes(base64.b64decode(encoded, validate=True))
            return result
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            if isinstance(error, BrowserMatrixError):
                raise
            raise BrowserMatrixError("Chromium browser contract failed") from error
    except BaseException as error:
        primary_error = error
        raise
    finally:
        _cleanup_chromium_resources(
            process=process, connection=connection, profile=profile_directory,
            primary_error=primary_error,
        )


_INTERACTIVE_PAGE_ASSERTIONS: Final = {
    "map3d": """(() => {
      const domainSelect = document.getElementById('domain-select');
      if (domainSelect?.value !== '1') {
        domainSelect.value = '1';
        domainSelect.dispatchEvent(new Event('change', { bubbles: true }));
      }
      const status = document.getElementById('map-status')?.textContent || '';
      const domainLink = document.getElementById('domain-link')?.href || '';
      const selectedPanelVisible = getComputedStyle(
        document.getElementById('info-panel')
      ).opacity === '1';
      return {
        ready: document.querySelectorAll('#canvas-container canvas').length === 1
          && document.querySelectorAll('.domain-label').length === 38
          && domainSelect?.options.length === 39
          && status.includes('前提')
          && status.includes('次の学習先')
          && domainLink.endsWith('/domains/01-math-statistics/index.html')
          && selectedPanelVisible,
        canvasCount: document.querySelectorAll('#canvas-container canvas').length,
        domainLabels: document.querySelectorAll('.domain-label').length,
        domainOptions: domainSelect?.options.length || 0,
        domainLink,
        documentState: document.readyState,
        hasContainer: Boolean(document.getElementById('canvas-container')),
        moduleLoaded: performance.getEntriesByType('resource').some(
          entry => entry.name.endsWith('/static/map3d.js')
        ),
        selectedPanelVisible,
        status,
        title: document.title
      };
    })()""",
    "progress": """(() => ({
      ready: document.getElementById('stat-total')?.textContent === '1,140'
        && document.getElementById('domain-grid')?.children.length === 38
        && document.getElementById('track-grid')?.children.length === 6,
      total: document.getElementById('stat-total')?.textContent || '',
      domains: document.getElementById('domain-grid')?.children.length || 0,
      tracks: document.getElementById('track-grid')?.children.length || 0
    }))()""",
    "daily": """(() => ({
      ready: document.querySelectorAll('[data-daily-output] article').length === 3,
      lessons: document.querySelectorAll('[data-daily-output] article').length
    }))()""",
}


def run_chromium_interactive_page(
    *, executable: Path, url: str, profile: Mapping[str, object], page: str,
    screenshot: Path, approved_file_roots: Sequence[Path] = (),
    timeout: float = 30.0, oci_container_no_sandbox: bool = False,
) -> dict[str, object]:
    """Execute a bounded smoke oracle for non-lesson interactive entry points."""
    if page not in _INTERACTIVE_PAGE_ASSERTIONS:
        raise BrowserMatrixError("interactive page identity is invalid")
    profile_directory = Path(tempfile.mkdtemp(prefix=".browser-profile-"))
    process: subprocess.Popen[bytes] | None = None
    connection: _WebSocket | None = None
    primary_error: BaseException | None = None
    try:
        arguments = chromium_arguments(
            executable, url, profile, profile_directory,
            oci_container_no_sandbox=oci_container_no_sandbox,
        )
        # The 3D map must exercise an actual WebGL context. The lesson harness
        # keeps GPU disabled for deterministic diagrams, while this bounded
        # smoke lets headless Chromium select its available GL implementation.
        arguments.remove("--disable-gpu")
        if page == "map3d" and sys.platform.startswith("linux"):
            # Hosted Linux has no hardware GPU. This opt-in is confined to the
            # reviewed loopback page inside the non-root CI container and makes
            # the pinned Chromium use its bundled software WebGL implementation.
            arguments[-1:-1] = (
                "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
            )
        process = subprocess.Popen(
            arguments,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, shell=False,
        )
        try:
            startup_deadline = time.monotonic() + timeout
            port = _wait_debugging_port(
                profile_directory, process, deadline=startup_deadline,
            )
            connection = _connect_chromium_debugging(
                port, process, deadline=startup_deadline, timeout=timeout,
            )
            connection.command("Page.enable")
            connection.command("Runtime.enable")
            connection.command("Network.enable")
            width = int(profile["width"])
            height = int(profile["height"])
            connection.command("Emulation.setDeviceMetricsOverride", {
                "width": width, "height": height,
                "deviceScaleFactor": int(profile["deviceScaleFactor"]),
                "mobile": width <= 390,
            })
            connection.command("Page.navigate", {"url": url})
            deadline = time.monotonic() + timeout
            assertions: dict[str, object] | None = None
            last_assertions: dict[str, object] | None = None
            while time.monotonic() < deadline:
                evaluated = connection.command("Runtime.evaluate", {
                    "expression": _INTERACTIVE_PAGE_ASSERTIONS[page],
                    "returnByValue": True,
                })
                remote = evaluated.get("result")
                value = remote.get("value") if type(remote) is dict else None
                if type(value) is dict:
                    last_assertions = value
                if type(value) is dict and value.get("ready") is True:
                    assertions = value
                    break
                time.sleep(0.05)
            exceptions = [
                event for event in connection.events
                if event.get("method") == "Runtime.exceptionThrown"
            ]
            if exceptions:
                raise BrowserMatrixError("interactive page raised a runtime exception")
            if assertions is None:
                console_messages: list[str] = []
                for event in connection.events:
                    if event.get("method") != "Runtime.consoleAPICalled":
                        continue
                    parameters = event.get("params")
                    arguments = parameters.get("args") if type(parameters) is dict else None
                    if type(arguments) is not list:
                        continue
                    for argument in arguments:
                        if type(argument) is not dict:
                            continue
                        message = argument.get("value") or argument.get("description")
                        if type(message) is str and message:
                            console_messages.append(message[:80])
                diagnostic = json.dumps(last_assertions, ensure_ascii=True, sort_keys=True)
                if console_messages:
                    diagnostic += " console=" + " | ".join(console_messages[:2])
                responses: list[str] = []
                for event in connection.events:
                    if event.get("method") != "Network.responseReceived":
                        continue
                    parameters = event.get("params")
                    response = parameters.get("response") if type(parameters) is dict else None
                    if type(response) is not dict:
                        continue
                    response_url = response.get("url")
                    status = response.get("status")
                    if type(response_url) is str and response_url.endswith(".js"):
                        responses.append(f"{response_url.rsplit('/', 1)[-1]}:{status}")
                if responses:
                    diagnostic += " responses=" + ",".join(responses[-8:])
                if len(diagnostic) > 240:
                    diagnostic = diagnostic[:240]
                raise BrowserMatrixError(
                    f"interactive page did not reach its ready contract: {diagnostic}"
                )
            validate_chromium_network_events(
                connection.events, target_url=url,
                truncated=connection.events_truncated,
                approved_file_roots=approved_file_roots,
            )
            capture = _capture_chromium_screenshot(connection)
            encoded = capture.get("data")
            if type(encoded) is not str or len(encoded) > 16 * 1024 * 1024:
                raise BrowserMatrixError("browser screenshot is unavailable or over budget")
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            screenshot.write_bytes(base64.b64decode(encoded, validate=True))
            return {"page": page, "assertions": assertions}
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            if isinstance(error, BrowserMatrixError):
                raise
            raise BrowserMatrixError("Chromium interactive contract failed") from error
    except BaseException as error:
        primary_error = error
        raise
    finally:
        _cleanup_chromium_resources(
            process=process, connection=connection, profile=profile_directory,
            primary_error=primary_error,
        )


def _reserve_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        return int(reservation.getsockname()[1])


def _connect_bidi(port: int, process: subprocess.Popen[bytes], timeout: float) -> _WebSocket:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise BrowserMatrixError("Firefox exited before exposing WebDriver BiDi")
        try:
            return _WebSocket(f"ws://127.0.0.1:{port}/session", min(2.0, timeout))
        except (OSError, BrowserMatrixError) as error:
            last_error = error
            time.sleep(0.05)
    raise BrowserMatrixError("Firefox WebDriver BiDi endpoint timed out") from last_error


def run_firefox_page(
    *,
    executable: Path,
    url: str,
    profile: Mapping[str, object],
    harness_source: str,
    harness_version: str,
    screenshot: Path,
    approved_file_roots: Sequence[Path] = (),
    requested_state: str | None = None,
    timeout: float = 30.0,
) -> dict[str, object]:
    if urlsplit(url).scheme not in {"file", "http"}:
        raise BrowserMatrixError("Firefox smoke URL must be local")
    with tempfile.TemporaryDirectory(prefix=".firefox-profile-") as profile_directory:
        port = _reserve_loopback_port()
        process = subprocess.Popen(
            [
                str(executable), "--headless", "--profile", profile_directory,
                "--remote-debugging-port", str(port), "about:blank",
            ],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, shell=False,
        )
        connection: _WebSocket | None = None
        try:
            connection = _connect_bidi(port, process, timeout)
            connection.command("session.new", {"capabilities": {}})
            created = connection.command("browsingContext.create", {"type": "tab"})
            context = created.get("context")
            if type(context) is not str:
                raise BrowserMatrixError("Firefox did not create a BiDi browsing context")
            connection.command("browsingContext.setViewport", {
                "context": context,
                "viewport": {"width": int(profile["width"]), "height": int(profile["height"])},
                "devicePixelRatio": float(profile["deviceScaleFactor"]),
            })
            state_prefix = (
                "window.__browserContractRequestedState=" + json.dumps(requested_state) + ";\n"
                if requested_state is not None else ""
            )
            connection.command("script.addPreloadScript", {
                "functionDeclaration": "() => {\n" + state_prefix
                + _instrumented_harness_source(
                    harness_source, approved_file_roots=approved_file_roots,
                ) + "\n}",
                "contexts": [context],
            })
            connection.command("browsingContext.navigate", {
                "context": context, "url": url, "wait": "complete",
            })
            deadline = time.monotonic() + timeout
            result_value: str | None = None
            while time.monotonic() < deadline:
                evaluated = connection.command("script.evaluate", {
                    "expression": "document.getElementById('browser-contract-result') && document.getElementById('browser-contract-result').getAttribute('data-browser-contract-result')",
                    "target": {"context": context}, "awaitPromise": True,
                })
                remote = evaluated.get("result")
                if type(remote) is dict and remote.get("type") == "string" and type(remote.get("value")) is str:
                    result_value = remote["value"]
                    break
                time.sleep(0.05)
            if result_value is None:
                raise BrowserMatrixError("Firefox harness did not publish a result")
            outer_result = connection.command("script.evaluate", {
                "expression": "document.documentElement.outerHTML",
                "target": {"context": context}, "awaitPromise": True,
            }).get("result")
            outer = outer_result.get("value") if type(outer_result) is dict else None
            if type(outer) is not str:
                raise BrowserMatrixError("Firefox dumped DOM is unavailable")
            result = parse_browser_result(outer, expected_harness_version=harness_version)
            capture = connection.command("browsingContext.captureScreenshot", {"context": context})
            encoded = capture.get("data")
            if type(encoded) is not str or len(encoded) > 16 * 1024 * 1024:
                raise BrowserMatrixError("Firefox screenshot is unavailable or over budget")
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            screenshot.write_bytes(base64.b64decode(encoded, validate=True))
            connection.command("session.end")
            return result
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            if isinstance(error, BrowserMatrixError):
                raise
            raise BrowserMatrixError("Firefox WebDriver BiDi contract failed") from error
        finally:
            if connection is not None:
                connection.close()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _webdriver_request(
    port: int,
    method: str,
    path: str,
    payload: Mapping[str, object] | None,
    timeout: float,
) -> object:
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = Request(
        f"http://127.0.0.1:{port}{path}", data=body, method=method,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
    except HTTPError as error:
        raw = error.read(4 * 1024 * 1024 + 1)
        if len(raw) <= 4 * 1024 * 1024:
            try:
                failure = json.loads(raw)
            except json.JSONDecodeError:
                failure = None
            value = failure.get("value") if type(failure) is dict else None
            if (
                method == "POST" and path == "/session" and error.code == 500
                and type(value) is dict
                and value.get("error") == "session not created"
                and value.get("message") == (
                    "Could not create a session: You must enable the 'Allow Remote Automation' "
                    "option in Safari's Develop menu to control Safari via WebDriver."
                )
            ):
                raise SafariSessionUnavailable(
                    "Safari Remote Automation session is unavailable"
                ) from error
        raise BrowserMatrixError("Safari WebDriver HTTP response failed") from error
    except (URLError, OSError) as error:
        raise BrowserMatrixError("Safari WebDriver request failed") from error
    if len(raw) > 4 * 1024 * 1024:
        raise BrowserMatrixError("Safari WebDriver response exceeds its byte budget")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise BrowserMatrixError("Safari WebDriver response is invalid JSON") from error
    if type(value) is not dict or "value" not in value:
        raise BrowserMatrixError("Safari WebDriver response shape drifted")
    inner = value["value"]
    if type(inner) is dict and "error" in inner:
        if (
            method == "POST" and path == "/session"
            and inner.get("error") == "session not created"
            and inner.get("message") == (
                "Could not create a session: You must enable the 'Allow Remote Automation' "
                "option in Safari's Develop menu to control Safari via WebDriver."
            )
        ):
            raise SafariSessionUnavailable(
                "Safari Remote Automation session is unavailable"
            )
        raise BrowserMatrixError("Safari WebDriver reported an automation error")
    return inner


def _assemble_safari_instrumented_html(
    document: bytes, harness_source: str,
) -> bytes:
    if type(document) is not bytes or not document or len(document) > 1024 * 1024:
        raise BrowserMatrixError("Safari source document is unavailable or over budget")
    if type(harness_source) is not str or len(harness_source.encode("utf-8")) > 128 * 1024 \
            or "</script" in harness_source.lower():
        raise BrowserMatrixError("Safari harness cannot be embedded safely")
    try:
        source = document.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise BrowserMatrixError("Safari source document is not UTF-8") from error
    head = re.search(r"<head(?:\s[^>]*)?>", source, flags=re.IGNORECASE)
    if head is None:
        raise BrowserMatrixError("Safari source document lacks a unique head")
    if re.search(r"<head(?:\s[^>]*)?>", source[head.end():], flags=re.IGNORECASE):
        raise BrowserMatrixError("Safari source document has ambiguous heads")
    instrumented = (
        source[:head.end()] + "\n<script>\n" + harness_source
        + "\n</script>\n" + source[head.end():]
    )
    return instrumented.encode("utf-8")


@contextmanager
def _safari_instrumented_document(
    *, source_document: Path, target_url: str, harness_source: str,
    approved_file_roots: Sequence[Path], requested_state: str | None,
) -> Iterator[str]:
    if source_document.is_symlink() or not source_document.is_file():
        raise BrowserMatrixError("Safari source document must be a regular file")
    parsed = urlsplit(target_url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" \
            or parsed.port is None or parsed.query or parsed.fragment:
        raise BrowserMatrixError("Safari target must be exact loopback HTTP")
    try:
        target_name = unquote_to_bytes(PurePosixPath(parsed.path).name).decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise BrowserMatrixError("Safari target URL filename is invalid") from error
    if target_name != source_document.name:
        raise BrowserMatrixError("Safari HTTP target does not bind to its source document")
    prefix = (
        "window.__browserContractRequestedState=" + json.dumps(requested_state) + ";\n"
        if requested_state is not None else ""
    )
    embedded_harness = prefix + _instrumented_harness_source(
        harness_source, approved_file_roots=approved_file_roots,
    )
    instrumented = _assemble_safari_instrumented_html(
        source_document.read_bytes(), embedded_harness,
    )
    descriptor, name = tempfile.mkstemp(
        prefix=".browser-contract-safari-", suffix=".html",
        dir=source_document.parent,
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(instrumented)
            stream.flush()
            os.fsync(stream.fileno())
        instrumented_path = str(PurePosixPath(parsed.path).with_name(temporary.name))
        instrumented_url = urlunsplit((parsed.scheme, parsed.netloc, instrumented_path, "", ""))
        yield instrumented_url
    finally:
        temporary.unlink(missing_ok=True)


def _is_safari_session_transport_unavailable(error: BaseException | None) -> bool:
    if isinstance(error, URLError):
        error = error.reason
    return isinstance(error, (ConnectionRefusedError, TimeoutError, socket.timeout)) or (
        isinstance(error, OSError) and error.errno in {errno.ECONNREFUSED, errno.ETIMEDOUT}
    )


def run_safari_smoke(
    *,
    safaridriver: Path,
    url: str,
    screenshot: Path,
    harness_version: str,
    viewport: tuple[int, int],
    timeout: float = 30.0,
) -> dict[str, object]:
    parsed_url = urlsplit(url)
    if safaridriver != Path("/usr/bin/safaridriver") or parsed_url.scheme != "http" \
            or parsed_url.hostname != "127.0.0.1" or parsed_url.port is None \
            or parsed_url.username is not None or parsed_url.password is not None \
            or parsed_url.query or parsed_url.fragment:
        raise BrowserMatrixError("Safari smoke authority must be exact loopback HTTP")
    if type(viewport) is not tuple or len(viewport) != 2 or any(
        type(value) is not int or value < 320 or value > 4096 for value in viewport
    ):
        raise BrowserMatrixError("Safari viewport is invalid")
    port = _reserve_loopback_port()
    process = subprocess.Popen(
        [str(safaridriver), "-p", str(port)], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False,
    )
    session_id: str | None = None
    try:
        deadline = time.monotonic() + timeout
        last_error: BrowserMatrixError | None = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise BrowserMatrixError("safaridriver exited before session creation")
            try:
                session = _webdriver_request(
                    port, "POST", "/session",
                    {"capabilities": {"alwaysMatch": {"browserName": "safari"}}},
                    min(5.0, timeout),
                )
                if type(session) is dict and type(session.get("sessionId")) is str:
                    session_id = session["sessionId"]
                    break
            except BrowserMatrixError as error:
                if isinstance(error, SafariSessionUnavailable):
                    raise
                cause = error.__cause__
                if not _is_safari_session_transport_unavailable(cause):
                    raise
                last_error = error
                time.sleep(0.1)
        if session_id is None:
            raise SafariSessionUnavailable(
                "Safari Remote Automation session is unavailable"
            ) from last_error
        prefix = f"/session/{quote(session_id, safe='')}"
        requested_width, requested_height = viewport
        outer_width, outer_height = viewport
        observed_viewport: dict[str, object] | None = None
        for _attempt in range(3):
            _webdriver_request(
                port, "POST", prefix + "/window/rect",
                {"width": outer_width, "height": outer_height}, timeout,
            )
            candidate = _webdriver_request(
                port, "POST", prefix + "/execute/sync",
                {
                    "script": "return {width:window.innerWidth,height:window.innerHeight,devicePixelRatio:window.devicePixelRatio};",
                    "args": [],
                }, timeout,
            )
            if type(candidate) is not dict or set(candidate) != {
                "width", "height", "devicePixelRatio"
            } or any(
                type(candidate[name]) is not int or candidate[name] <= 0
                for name in ("width", "height")
            ) or type(candidate["devicePixelRatio"]) not in (int, float) \
                    or not math.isfinite(float(candidate["devicePixelRatio"])) \
                    or float(candidate["devicePixelRatio"]) <= 0:
                raise BrowserMatrixError("Safari observed viewport is invalid")
            if candidate["width"] == requested_width \
                    and candidate["height"] == requested_height:
                observed_viewport = candidate
                break
            # WebDriver sizes the outer window. Correct the next bounded request by
            # the observed browser chrome delta so product startup sees the matrix viewport.
            outer_width += requested_width - candidate["width"]
            outer_height += requested_height - candidate["height"]
            if not 320 <= outer_width <= 4096 or not 320 <= outer_height <= 4096:
                break
        if observed_viewport is None:
            raise BrowserMatrixError("Safari viewport could not be confirmed")
        _webdriver_request(port, "POST", prefix + "/url", {"url": url}, timeout)
        deadline = time.monotonic() + timeout
        result_value: str | None = None
        while time.monotonic() < deadline:
            candidate = _webdriver_request(
                port, "POST", prefix + "/execute/sync",
                {
                    "script": "var node=document.getElementById('browser-contract-result'); return node && node.getAttribute('data-browser-contract-result');",
                    "args": [],
                }, min(5.0, timeout),
            )
            if type(candidate) is str:
                result_value = candidate
                break
            time.sleep(0.05)
        if result_value is None:
            raise BrowserMatrixError("Safari harness did not publish a result")
        title = _webdriver_request(port, "GET", prefix + "/title", None, timeout)
        source = _webdriver_request(port, "GET", prefix + "/source", None, timeout)
        if type(title) is not str or not title or type(source) is not str or len(source.encode("utf-8")) > 1024 * 1024:
            raise BrowserMatrixError("Safari smoke did not return a bounded page")
        harness_result = parse_browser_result(
            source, expected_harness_version=harness_version
        )
        element = _webdriver_request(
            port, "POST", prefix + "/element",
            {"using": "css selector", "value": "[data-action=reset]"}, timeout,
        )
        if type(element) is not dict:
            raise BrowserMatrixError("Safari smoke did not find the native reset control")
        element_id = element.get("element-6066-11e4-a52e-4f735466cecf")
        if type(element_id) is not str:
            raise BrowserMatrixError("Safari reset element identifier is unavailable")
        _webdriver_request(port, "POST", prefix + f"/element/{quote(element_id, safe='')}/click", {}, timeout)
        encoded = _webdriver_request(port, "GET", prefix + "/screenshot", None, timeout)
        if type(encoded) is not str or len(encoded) > 16 * 1024 * 1024:
            raise BrowserMatrixError("Safari screenshot is unavailable or over budget")
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        screenshot.write_bytes(base64.b64decode(encoded, validate=True))
        result = dict(harness_result)
        result["observedViewport"] = observed_viewport
        return result
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        if isinstance(error, BrowserMatrixError):
            raise
        raise BrowserMatrixError("Safari release smoke failed") from error
    finally:
        if session_id is not None:
            try:
                _webdriver_request(
                    port, "DELETE", f"/session/{quote(session_id, safe='')}", None, 5.0
                )
            except BrowserMatrixError:
                pass
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def assert_performance_contract(
    *, profile: str, samples_ms: Sequence[float], long_tasks_ms: Sequence[float],
    mutation_counts: Sequence[int], instrumentation: Mapping[str, bool],
) -> None:
    if len(samples_ms) != 20 or len(long_tasks_ms) != 20 or len(mutation_counts) != 20:
        raise BrowserMatrixError("performance instrumentation must return exactly 20 samples")
    values = tuple(float(value) for value in samples_ms)
    tasks = tuple(float(value) for value in long_tasks_ms)
    if any(not math.isfinite(value) or value <= 0 for value in values) or any(
        not math.isfinite(value) or value < 0 for value in tasks
    ):
        raise BrowserMatrixError("performance samples must be positive and long-task samples non-negative")
    if any(type(value) is not int or value <= 0 for value in mutation_counts):
        raise BrowserMatrixError("every performance sample must mutate runtime DOM state")
    if set(instrumentation) != {"longTasks"} or instrumentation["longTasks"] is not True:
        raise BrowserMatrixError("Long Task PerformanceObserver instrumentation is required")
    median = statistics.median(values)
    if profile == "desktop":
        if median > 25 or sum(value <= 50 for value in tasks) < 19:
            raise BrowserMatrixError("desktop transition performance budget exceeded")
    elif profile == "mobile":
        p95 = sorted(values)[math.ceil(0.95 * len(values)) - 1]
        if median > 50 or p95 > 100:
            raise BrowserMatrixError("mobile transition performance budget exceeded")
    else:
        raise BrowserMatrixError("performance profile must be desktop or mobile")


def assert_leak_contract(
    *, baseline: Mapping[str, int], final: Mapping[str, int], reset_cycles: int,
    instrumentation: Mapping[str, bool],
) -> None:
    if reset_cycles != 100:
        raise BrowserMatrixError("leak gate must execute exactly 100 reset cycles")
    if set(instrumentation) != {"listeners", "timers", "gc"} or not all(
        type(value) is bool and value for value in instrumentation.values()
    ):
        raise BrowserMatrixError("listener, timer, and explicit GC instrumentation are required")
    expected_keys = {"domNodes", "listeners", "timers", "heapBytes"}
    if set(baseline) != expected_keys or set(final) != expected_keys:
        raise BrowserMatrixError("leak measurements are incomplete")
    if any(type(value) is not int or value < 0 for value in (*baseline.values(), *final.values())):
        raise BrowserMatrixError("leak measurements must be non-negative integers")
    for key in ("domNodes", "listeners", "timers"):
        if final[key] != baseline[key]:
            raise BrowserMatrixError(f"{key} did not return to its post-initialization baseline")
    growth = final["heapBytes"] - baseline["heapBytes"]
    allowance = max(1024 * 1024, baseline["heapBytes"] * 0.05)
    if growth >= allowance:
        raise BrowserMatrixError("retained heap growth exceeded the closed leak budget")


def _profile_mapping(profile: BrowserProfile) -> dict[str, object]:
    return {
        "width": profile.viewport[0],
        "height": profile.viewport[1],
        "deviceScaleFactor": profile.device_scale_factor,
        "cpuThrottleRate": profile.cpu_throttle_rate,
        "reducedMotion": profile.reduced_motion,
        "forcedColors": profile.forced_colors,
    }


def _lesson(site: Path, lesson_id: str) -> Path:
    path = site / "lessons" / lesson_id / "index.html"
    if not path.is_file() or path.is_symlink():
        raise BrowserMatrixError("browser evidence lesson is absent from the built site")
    return path


def _write_report(path: Path, report: Mapping[str, object]) -> None:
    encoded = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(encoded) > 4 * 1024 * 1024:
        raise BrowserMatrixError("browser evidence report exceeds its byte budget")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".pending")
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class SafariSessionUnavailable(BrowserMatrixError):
    """Safari is installed but WebDriver cannot create a Remote Automation session."""

    reason = "remote-automation-session-unavailable"


def browser_run_plan(
    inventory: EvidenceInventory, *, include_safari: bool,
) -> tuple[dict[str, object], ...]:
    runs: list[dict[str, object]] = [
        {"browser": browser, "label": label, "profile": "desktop", "requestedState": "crossover"}
        for browser in ("chromium", "firefox")
        for label in ("core-02-file", "core-02-http")
    ]
    runs.extend(
        {"browser": "chromium", "label": f"{lesson}-{state}", "profile": profile, "requestedState": state}
        for lesson, state in inventory.regression_states
        for profile in inventory.profiles
    )
    runs.extend(
        {
            "browser": "chromium", "label": f"interactive-{page}",
            "profile": "desktop", "requestedState": None,
        }
        for page in ("map3d", "progress", "daily")
    )
    runs.extend(
        {"browser": "chromium", "label": f"type-{kind}-{lesson}", "profile": "desktop", "requestedState": None}
        for kind, lesson in sorted(inventory.diagram_type_lessons.items())
    )
    runs.extend(
        {"browser": "chromium", "label": f"performance-{fixture}", "profile": profile, "requestedState": None}
        for fixture in ("maximum", "memory", "distributed")
        for profile in ("desktop", "mobile")
    )
    if include_safari:
        runs.extend(
            {
                "browser": "safari", "label": f"core-02-http-{profile}",
                "profile": profile, "requestedState": "crossover",
            }
            for profile in ("desktop", "mobile")
        )
    return tuple(runs)


class BrowserEvidenceJournal:
    def __init__(
        self, *, path: Path, harness_version: str, inventory: EvidenceInventory,
        provenance: Mapping[str, object], plan: Sequence[Mapping[str, object]],
    ) -> None:
        if not plan or len(plan) > 169 or set(provenance) != {
            "matrixSha256", "fixtureSha256", "harnessSha256", "platform", "browsers"
        }:
            raise BrowserMatrixError("browser evidence journal inputs are incomplete")
        if any(
            type(provenance[name]) is not str
            or len(provenance[name]) != 64
            or any(character not in "0123456789abcdef" for character in provenance[name])
            for name in ("matrixSha256", "fixtureSha256", "harnessSha256")
        ):
            raise BrowserMatrixError("browser evidence digests are invalid")
        platform = provenance["platform"]
        browsers = provenance["browsers"]
        if (
            type(platform) is not dict or set(platform) != {"os", "architecture"}
            or any(type(value) is not str or not value for value in platform.values())
            or type(browsers) is not dict or set(browsers) not in (
                {"chromium", "firefox"}, {"chromium", "firefox", "safari"}
            )
        ):
            raise BrowserMatrixError("browser evidence platform provenance is invalid")
        for browser in browsers.values():
            if type(browser) is not dict or set(browser) != {
                "version", "build", "verificationStatus"
            } or type(browser["version"]) is not str or not browser["version"] \
                    or type(browser["build"]) is not str or not browser["build"] \
                    or browser["verificationStatus"] not in {"not-run", "verified"}:
                raise BrowserMatrixError("browser evidence version provenance is invalid")
        self.path = path
        self.harness_version = harness_version
        self.inventory = inventory
        self.provenance = dict(provenance)
        self.runs = [{**dict(item), "status": "not-run"} for item in plan]
        self.failure: str | None = None
        self._publish()

    def _report(self) -> dict[str, object]:
        statuses = {item["status"] for item in self.runs}
        status = (
            "failed" if self.failure is not None or "failed" in statuses
            else "blocked" if "blocked" in statuses
            else "passed" if statuses == {"passed"}
            else "running"
        )
        report: dict[str, object] = {
            "schemaVersion": 1, "harnessVersion": self.harness_version,
            "status": status, "provenance": self.provenance,
            "inventory": {
                "dynamicLessons": len(self.inventory.dynamic_lessons),
                "diagramTypes": len(self.inventory.diagram_type_lessons),
                "regressionStates": len(self.inventory.regression_states),
                "profiles": list(self.inventory.profiles),
            },
            "runs": self.runs,
        }
        if self.failure is not None:
            report["failure"] = self.failure
        return report

    def _publish(self) -> None:
        _write_report(self.path, self._report())

    def report(self) -> dict[str, object]:
        """Return a detached snapshot so callers cannot mutate journal state."""
        return json.loads(json.dumps(self._report()))

    def record(
        self, run: Mapping[str, object], *, status: str,
        result: Mapping[str, object] | None = None, reason: str | None = None,
    ) -> None:
        if status not in {"passed", "failed", "blocked"}:
            raise BrowserMatrixError("browser evidence status is invalid")
        if status == "blocked" and reason != SafariSessionUnavailable.reason:
            raise BrowserMatrixError("only typed Safari session unavailability may block")
        identity = {key: run.get(key) for key in ("browser", "label", "profile", "requestedState")}
        matches = [item for item in self.runs if all(item.get(key) == value for key, value in identity.items())]
        if len(matches) != 1:
            raise BrowserMatrixError("browser evidence run identity is ambiguous")
        target = matches[0]
        if target["status"] != "not-run":
            raise BrowserMatrixError("browser evidence run is already terminal")
        target.pop("result", None)
        target.pop("reason", None)
        target["status"] = status
        if status == "passed":
            if result is None:
                raise BrowserMatrixError("passed browser evidence requires its result")
            target["result"] = dict(result)
        else:
            if type(reason) is not str or not reason or len(reason) > 120:
                raise BrowserMatrixError("non-passing browser evidence requires a bounded reason")
            target["reason"] = reason
        self._publish()

    def fail(self, reason: str) -> None:
        if type(reason) is not str or not reason or len(reason) > 120:
            raise BrowserMatrixError("browser evidence failure reason is invalid")
        self.failure = reason
        self._publish()

    def verified_browser(
        self, name: str, *, version: str, build: str | None = None,
    ) -> None:
        browsers = self.provenance.get("browsers")
        if type(browsers) is not dict or name not in browsers or type(browsers[name]) is not dict:
            raise BrowserMatrixError("browser provenance identity is invalid")
        browsers[name]["version"] = version
        browsers[name]["verificationStatus"] = "verified"
        browsers[name]["build"] = version if build is None else build
        self._publish()


def browser_evidence_report(
    *, harness_version: str, platform_key: str, inventory: EvidenceInventory,
    successful_runs: Sequence[Mapping[str, object]], safari_blocked: bool,
) -> dict[str, object]:
    expected_successes = 167 if safari_blocked or platform_key == "linux-x86_64" else 169
    if len(successful_runs) != expected_successes:
        raise BrowserMatrixError("browser evidence success count is incomplete")
    runs = [dict(item) for item in successful_runs]
    if safari_blocked:
        for profile in ("desktop", "mobile"):
            runs.append({
                "browser": "safari", "label": f"core-02-http-{profile}",
                "profile": profile,
                "requestedState": "crossover", "status": "blocked",
                "reason": "remote-automation-session-unavailable",
            })
    return {
        "schemaVersion": 1,
        "harnessVersion": harness_version,
        "platform": platform_key,
        "status": "blocked" if safari_blocked else "passed",
        "inventory": {
            "dynamicLessons": len(inventory.dynamic_lessons),
            "diagramTypes": len(inventory.diagram_type_lessons),
            "regressionStates": len(inventory.regression_states),
            "profiles": list(inventory.profiles),
        },
        "runs": runs,
    }


def _run_browser_contract(
    *, site: Path, matrix_path: Path, cache: Path, evidence: Path,
    oci_container_no_sandbox: bool = False,
) -> dict[str, object]:
    matrix = load_browser_matrix(matrix_path)
    platform_entry = resolve_platform(matrix, None)
    if oci_container_no_sandbox and not platform_entry.key.startswith("linux-"):
        raise BrowserMatrixError("OCI no-sandbox opt-in is Linux-only")
    site = site.resolve(strict=True)
    if not site.is_dir():
        raise BrowserMatrixError("browser contract site must be a directory")
    repository = matrix_path.resolve(strict=True).parent.parent
    catalog = repository / "content" / "visualization-catalog.json"
    harness_path = repository / "tests" / "browser" / "runtime-harness.js"
    fixture = repository / str(matrix.fixtures["maximum"]["path"])
    try:
        harness_source = harness_path.read_text(encoding="utf-8")
        fixture_bytes = fixture.read_bytes()
        inventory = browser_evidence_inventory(catalog.read_bytes())
    except (OSError, UnicodeError) as error:
        raise BrowserMatrixError("browser contract inputs could not be read") from error
    if len(harness_source.encode("utf-8")) > 128 * 1024:
        raise BrowserMatrixError("browser harness exceeds its byte budget")
    if hashlib.sha256(harness_source.encode("utf-8")).hexdigest() != matrix.fixtures["harnessSha256"]:
        raise BrowserMatrixError("browser harness digest drifted")
    if hashlib.sha256(fixture_bytes).hexdigest() != matrix.fixtures["maximum"]["sha256"]:
        raise BrowserMatrixError("maximum browser fixture digest drifted")

    evidence.mkdir(parents=True, exist_ok=True)
    if evidence.is_symlink() or not evidence.is_dir():
        raise BrowserMatrixError("browser evidence directory must be a real directory")
    include_safari = platform_entry.safari is not None
    plan = browser_run_plan(inventory, include_safari=include_safari)
    os_name, architecture = platform_entry.key.split("-", 1)
    provenance: dict[str, object] = {
        "matrixSha256": matrix.source_sha256,
        "fixtureSha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "harnessSha256": hashlib.sha256(harness_source.encode("utf-8")).hexdigest(),
        "platform": {"os": os_name, "architecture": architecture},
        "browsers": {
            "chromium": {"version": platform_entry.browsers["chromium"].version, "build": platform_entry.browsers["chromium"].version, "verificationStatus": "not-run"},
            "firefox": {"version": platform_entry.browsers["firefox"].version, "build": platform_entry.browsers["firefox"].version, "verificationStatus": "not-run"},
            **({"safari": {"version": platform_entry.safari.version, "build": platform_entry.safari.build, "verificationStatus": "not-run"}} if platform_entry.safari is not None else {}),
        },
    }
    journal = BrowserEvidenceJournal(
        path=evidence / "report.json", harness_version=matrix.harness_version,
        inventory=inventory, provenance=provenance, plan=plan,
    )
    try:
        chromium = install_archive(
            platform_entry.browsers["chromium"], cache, browser_name="chromium",
            oci_container_no_sandbox=oci_container_no_sandbox,
        )
        journal.verified_browser(
            "chromium", version=platform_entry.browsers["chromium"].version
        )
        firefox = install_archive(
            platform_entry.browsers["firefox"], cache, browser_name="firefox",
            oci_container_no_sandbox=oci_container_no_sandbox,
        )
        journal.verified_browser(
            "firefox", version=platform_entry.browsers["firefox"].version
        )
        if platform_entry.safari is not None:
            verify_safari_version(
                executable=Path(platform_entry.safari.executable),
                expected_version=platform_entry.safari.version,
                expected_build=platform_entry.safari.build,
            )
            journal.verified_browser(
                "safari", version=platform_entry.safari.version,
                build=platform_entry.safari.build,
            )
    except BrowserMatrixError:
        journal.fail("browser-provisioning-or-version-preflight-failed")
        raise

    def chromium_run(
        label: str, url: str, profile_name: str, requested_state: str | None = None,
        *, measure_performance: bool = False,
        record: bool = True,
    ) -> dict[str, object]:
        run = {"browser": "chromium", "label": label, "profile": profile_name, "requestedState": requested_state}
        try:
            result = run_chromium_page(
                executable=chromium,
                url=url,
                profile=_profile_mapping(matrix.profiles[profile_name]),
                harness_source=harness_source,
                harness_version=matrix.harness_version,
                requested_state=requested_state,
                measure_performance=measure_performance,
                screenshot=evidence / f"{label}-chromium-{profile_name}.png",
                approved_file_roots=(site, fixture.parent, repository / "static"),
                oci_container_no_sandbox=oci_container_no_sandbox,
            )
        except BrowserMatrixError:
            journal.record(run, status="failed", reason="browser-contract-failed")
            raise
        if record:
            journal.record(run, status="passed", result=result)
        print(f"PASS chromium {label} {profile_name}", flush=True)
        return result

    core02 = _lesson(site, "core-02-algorithms-measurement")
    with serve_site(site) as server:
        file_url, http_url = browser_urls(site, core02, server.port)
        chromium_run("core-02-file", file_url, "desktop", "crossover")
        chromium_run("core-02-http", http_url, "desktop", "crossover")
        for label, url in (("core-02-file", file_url), ("core-02-http", http_url)):
            run = {"browser": "firefox", "label": label, "profile": "desktop", "requestedState": "crossover"}
            try:
                result = run_firefox_page(
                    executable=firefox, url=url,
                    profile=_profile_mapping(matrix.profiles["desktop"]),
                    harness_source=harness_source, harness_version=matrix.harness_version,
                    requested_state="crossover",
                    screenshot=evidence / f"{label}-firefox-desktop.png",
                    approved_file_roots=(site, fixture.parent, repository / "static"),
                )
            except BrowserMatrixError:
                journal.record(run, status="failed", reason="browser-contract-failed")
                raise
            journal.record(run, status="passed", result=result)
            print(f"PASS firefox {label} desktop", flush=True)

        # These entry points do not use the lesson visualization harness. Their
        # own bounded readiness oracles ensure module loading and data-backed UI
        # rendering are exercised in the same pinned browser as lesson pages.
        for page in ("map3d", "progress", "daily"):
            label = f"interactive-{page}"
            run = {
                "browser": "chromium", "label": label,
                "profile": "desktop", "requestedState": None,
            }
            url = interactive_page_url(server.port, page)
            try:
                result = run_chromium_interactive_page(
                    executable=chromium, url=url,
                    profile=_profile_mapping(matrix.profiles["desktop"]),
                    page=page,
                    screenshot=evidence / f"{label}-chromium-desktop.png",
                    approved_file_roots=(site, repository / "static"),
                    oci_container_no_sandbox=oci_container_no_sandbox,
                )
            except BrowserMatrixError:
                journal.record(run, status="failed", reason="interactive-page-contract-failed")
                raise
            journal.record(run, status="passed", result=result)
            print(f"PASS chromium {label} desktop", flush=True)

        # Every catalog regression state is rendered under every closed visual
        # profile. The state oracle drives only bounded native form actions.
        for lesson_id, state_id in inventory.regression_states:
            lesson_url = browser_urls(site, _lesson(site, lesson_id), server.port)[0]
            for profile_name in inventory.profiles:
                chromium_run(f"{lesson_id}-{state_id}", lesson_url, profile_name, state_id)

        # Static representative pages close the type coverage not already
        # implied by the twelve dynamic lessons.
        for diagram_type, lesson_id in sorted(inventory.diagram_type_lessons.items()):
            lesson_url = browser_urls(site, _lesson(site, lesson_id), server.port)[0]
            chromium_run(f"type-{diagram_type}-{lesson_id}", lesson_url, "desktop")

        performance_targets = (
            ("maximum", fixture.as_uri()),
            ("memory", browser_urls(site, _lesson(site, str(matrix.fixtures["memoryLessonId"])), server.port)[0]),
            ("distributed", browser_urls(site, _lesson(site, str(matrix.fixtures["distributedLessonId"])), server.port)[0]),
        )
        for label, url in performance_targets:
            for profile_name in ("desktop", "mobile"):
                result = chromium_run(
                    f"performance-{label}", url, profile_name,
                    measure_performance=True,
                    record=False,
                )
                run = {"browser": "chromium", "label": f"performance-{label}", "profile": profile_name, "requestedState": None}
                try:
                    assert_performance_contract(
                        profile=profile_name,
                        samples_ms=result["samplesMs"],
                        long_tasks_ms=result["longTasksMs"],
                        mutation_counts=result["workloadMutationSamples"],
                        instrumentation={
                            "longTasks": result["instrumentation"]["longTasks"]
                        },
                    )
                    instrumentation = result["instrumentation"]
                    assert_leak_contract(
                        baseline=result["baseline"], final=result["final"],
                        reset_cycles=result["resetCycles"],
                        instrumentation={
                            "listeners": instrumentation["listeners"],
                            "timers": instrumentation["timers"],
                            "gc": instrumentation["gc"],
                        },
                    )
                except BrowserMatrixError:
                    journal.record(run, status="failed", reason="performance-or-leak-contract-failed")
                    raise
                journal.record(run, status="passed", result=result)

        if platform_entry.safari is not None:
            safari = platform_entry.safari
            safari_runs = tuple(
                ({
                    "browser": "safari", "label": f"core-02-http-{profile_name}",
                    "profile": profile_name, "requestedState": "crossover",
                }, http_url, matrix.profiles[profile_name])
                for profile_name in safari.smoke_profiles
            )
            for index, (run, url, profile) in enumerate(safari_runs):
                try:
                    with _safari_instrumented_document(
                        source_document=core02, target_url=url,
                        harness_source=harness_source,
                        approved_file_roots=(site, fixture.parent, repository / "static"),
                        requested_state="crossover",
                    ) as instrumented_url:
                        result = run_safari_smoke(
                            safaridriver=Path("/usr/bin/safaridriver"),
                            url=instrumented_url,
                            screenshot=evidence / f"{run['label']}-safari.png",
                            harness_version=matrix.harness_version,
                            viewport=profile.viewport,
                        )
                except SafariSessionUnavailable:
                    # One failed session preflight proves the host cannot execute
                    # any remaining Safari profile; each remains an explicit blocker.
                    for blocked_run, _, _ in safari_runs[index:]:
                        journal.record(
                            blocked_run, status="blocked",
                            reason=SafariSessionUnavailable.reason,
                        )
                    print("BLOCKED safari Remote Automation session unavailable", flush=True)
                    break
                except BrowserMatrixError:
                    journal.record(run, status="failed", reason="safari-browser-contract-failed")
                    raise
                journal.record(run, status="passed", result=result)
                print(f"PASS safari {run['label']} {run['profile']}", flush=True)

    report = journal.report()
    if report["status"] == "blocked":
        raise SafariSessionUnavailable(
            "Safari release smoke blocked: Remote Automation session unavailable"
        )
    if report["status"] != "passed":
        journal.fail("browser-contract-plan-incomplete")
        raise BrowserMatrixError("browser contract did not complete its closed run plan")
    return report


def _terminalize_browser_report(path: Path) -> None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
            return
        report = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError):
        return
    if type(report) is not dict or type(report.get("runs")) is not list:
        return
    report["status"] = "failed"
    report["failure"] = "browser-contract-aborted"
    _write_report(path, report)


def run_browser_contract(
    *, site: Path, matrix_path: Path, cache: Path, evidence: Path,
    oci_container_no_sandbox: bool = False,
) -> dict[str, object]:
    try:
        return _run_browser_contract(
            site=site, matrix_path=matrix_path, cache=cache, evidence=evidence,
            oci_container_no_sandbox=oci_container_no_sandbox,
        )
    except SafariSessionUnavailable:
        raise
    except BaseException:
        # A journal may already contain individually terminal runs. Preserve
        # them and make the top-level outcome terminal for every later failure.
        try:
            _terminalize_browser_report(evidence / "report.json")
        except Exception:
            # Terminalization is best-effort and must never replace the
            # original failure, interrupt, or process exit signal.
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=Path("outputs/browser-cache"))
    parser.add_argument("--evidence", type=Path, default=Path("outputs/browser-evidence"))
    parser.add_argument("--oci-container-no-sandbox", action="store_true")
    options = parser.parse_args(argv)
    report = run_browser_contract(
        site=options.site, matrix_path=options.matrix,
        cache=options.cache, evidence=options.evidence,
        oci_container_no_sandbox=options.oci_container_no_sandbox,
    )
    print(f"browser contract passed: {len(report['runs'])} runs")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrowserMatrixError as error:
        print(f"browser contract failed: {error}", file=sys.stderr)
        raise SystemExit(1)
