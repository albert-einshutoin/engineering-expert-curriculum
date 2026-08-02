#!/usr/bin/env python3
"""Run bounded browser contracts over local-file and Pages-style URLs."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import base64
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import socket
import statistics
import struct
import subprocess
import sys
import tempfile
from threading import Thread
import time
from typing import Iterator, Mapping, Sequence
from urllib.parse import quote, urlsplit
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
) -> list[str]:
    if urlsplit(url).scheme not in {"file", "http"}:
        raise BrowserMatrixError("browser URL must be local file or loopback HTTP")
    width = profile.get("width")
    height = profile.get("height")
    scale = profile.get("deviceScaleFactor")
    if type(width) is not int or type(height) is not int or type(scale) is not int:
        raise BrowserMatrixError("browser profile dimensions are invalid")
    return [
        str(executable), "--headless=new", "--disable-gpu", "--no-first-run",
        "--no-default-browser-check", "--remote-debugging-port=0",
        f"--user-data-dir={user_data_directory}",
        f"--window-size={width},{height}", f"--force-device-scale-factor={scale}",
        "--enable-precise-memory-info", "--js-flags=--expose-gc", "about:blank",
    ]


class _ResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id") == "browser-contract-result" and values.get("data-browser-contract-result") is not None:
            self.values.append(values["data-browser-contract-result"] or "")


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
    if result.get("passed") is not True or type(result.get("violations")) is not list or result["violations"]:
        count = len(result.get("violations", ())) if type(result.get("violations")) is list else -1
        target = result.get("requestedStateReached") is True
        kinds = result.get("violationKinds")
        safe_kinds = tuple(item for item in kinds if item in {"csp", "error", "fetch", "XMLHttpRequest", "WebSocket", "EventSource", "window.open", "storage.setItem", "storage.removeItem", "storage.clear", "history.pushState", "history.replaceState", "navigation", "external-resource", "runtime-initialization", "harness"}) if type(kinds) is list else ()
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


class _WebSocket:
    def __init__(self, url: str, timeout: float) -> None:
        parsed = urlsplit(url)
        if parsed.scheme != "ws" or parsed.hostname != "127.0.0.1" or parsed.port is None:
            raise BrowserMatrixError("browser debugging endpoint is not loopback WebSocket")
        self.socket = socket.create_connection((parsed.hostname, parsed.port), timeout=timeout)
        self.socket.settimeout(timeout)
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
            response.extend(self.socket.recv(4096))
        expected = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        header = response.decode("latin-1", errors="strict")
        if not header.startswith("HTTP/1.1 101 ") or expected.lower() not in header.lower():
            self.close()
            raise BrowserMatrixError("browser debugging WebSocket handshake failed")
        self.identifier = 0

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
            if type(message) is not dict or message.get("id") != identifier:
                continue
            if "error" in message or type(message.get("result")) is not dict:
                raise BrowserMatrixError(f"browser debugging command failed: {method}")
            return message["result"]


def _wait_debugging_port(directory: Path, process: subprocess.Popen[bytes], timeout: float) -> int:
    deadline = time.monotonic() + timeout
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
        time.sleep(0.025)
    raise BrowserMatrixError("Chromium debugging endpoint timed out")


def _new_debugging_target(port: int, timeout: float) -> str:
    request = Request(f"http://127.0.0.1:{port}/json/new?{quote('about:blank', safe='')}", method="PUT")
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read(64 * 1024 + 1)
    except OSError as error:
        raise BrowserMatrixError("Chromium target creation failed") from error
    if len(payload) > 64 * 1024:
        raise BrowserMatrixError("Chromium target response exceeds its byte budget")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise BrowserMatrixError("Chromium target response is invalid") from error
    websocket_url = value.get("webSocketDebuggerUrl") if type(value) is dict else None
    if type(websocket_url) is not str:
        raise BrowserMatrixError("Chromium target response lacks its debugging URL")
    return websocket_url


def run_chromium_page(
    *,
    executable: Path,
    url: str,
    profile: Mapping[str, object],
    harness_source: str,
    harness_version: str,
    screenshot: Path,
    requested_state: str | None = None,
    measure_performance: bool = False,
    timeout: float = 30.0,
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix=".browser-profile-") as profile_directory:
        args = chromium_arguments(executable, url, profile, Path(profile_directory))
        process = subprocess.Popen(
            args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, shell=False,
        )
        connection: _WebSocket | None = None
        try:
            port = _wait_debugging_port(Path(profile_directory), process, timeout)
            connection = _WebSocket(_new_debugging_target(port, timeout), timeout)
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
            connection.command("Page.addScriptToEvaluateOnNewDocument", {"source": state_prefix + harness_source})
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
            document = connection.command("DOM.getDocument", {"depth": 0})
            root = document.get("root")
            node_id = root.get("nodeId") if type(root) is dict else None
            if type(node_id) is not int:
                raise BrowserMatrixError("browser DOM root is unavailable")
            outer = connection.command("DOM.getOuterHTML", {"nodeId": node_id}).get("outerHTML")
            if type(outer) is not str:
                raise BrowserMatrixError("browser dumped DOM is unavailable")
            result = parse_browser_result(outer, expected_harness_version=harness_version)
            capture = connection.command("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
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
        finally:
            if connection is not None:
                connection.close()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


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
                "functionDeclaration": "() => {\n" + state_prefix + harness_source + "\n}",
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
    except (HTTPError, URLError, OSError) as error:
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
        raise BrowserMatrixError("Safari WebDriver reported an automation error")
    return inner


def run_safari_smoke(
    *,
    safaridriver: Path,
    url: str,
    screenshot: Path,
    timeout: float = 30.0,
) -> dict[str, object]:
    if safaridriver != Path("/usr/bin/safaridriver") or urlsplit(url).scheme not in {"file", "http"}:
        raise BrowserMatrixError("Safari smoke authority is not the pinned local contract")
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
                last_error = error
                time.sleep(0.1)
        if session_id is None:
            raise BrowserMatrixError("Safari WebDriver session is unavailable") from last_error
        prefix = f"/session/{quote(session_id, safe='')}"
        _webdriver_request(port, "POST", prefix + "/url", {"url": url}, timeout)
        title = _webdriver_request(port, "GET", prefix + "/title", None, timeout)
        source = _webdriver_request(port, "GET", prefix + "/source", None, timeout)
        if type(title) is not str or not title or type(source) is not str or len(source.encode("utf-8")) > 1024 * 1024:
            raise BrowserMatrixError("Safari smoke did not return a bounded page")
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
        return {"browser": "safari", "url": url, "title": title, "nativeResetClicked": True}
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
    mutation_counts: Sequence[int],
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


def browser_evidence_report(
    *, harness_version: str, platform_key: str, inventory: EvidenceInventory,
    successful_runs: Sequence[Mapping[str, object]], safari_blocked: bool,
) -> dict[str, object]:
    expected_successes = 164 if safari_blocked or platform_key == "linux-x86_64" else 166
    if len(successful_runs) != expected_successes:
        raise BrowserMatrixError("browser evidence success count is incomplete")
    runs = [dict(item) for item in successful_runs]
    if safari_blocked:
        for label in ("core-02-file", "core-02-http"):
            runs.append({
                "browser": "safari", "label": label, "profile": "desktop",
                "requestedState": None, "status": "blocked",
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


def run_browser_contract(
    *, site: Path, matrix_path: Path, cache: Path, evidence: Path,
) -> dict[str, object]:
    matrix = load_browser_matrix(matrix_path)
    platform_entry = resolve_platform(matrix, None)
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
    if hashlib.sha256(fixture_bytes).hexdigest() != matrix.fixtures["maximum"]["sha256"]:
        raise BrowserMatrixError("maximum browser fixture digest drifted")

    chromium = install_archive(platform_entry.browsers["chromium"], cache)
    firefox = install_archive(platform_entry.browsers["firefox"], cache)
    evidence.mkdir(parents=True, exist_ok=True)
    if evidence.is_symlink() or not evidence.is_dir():
        raise BrowserMatrixError("browser evidence directory must be a real directory")
    results: list[dict[str, object]] = []
    safari_blocked = False

    def chromium_run(
        label: str, url: str, profile_name: str, requested_state: str | None = None,
        *, measure_performance: bool = False,
    ) -> dict[str, object]:
        result = run_chromium_page(
            executable=chromium,
            url=url,
            profile=_profile_mapping(matrix.profiles[profile_name]),
            harness_source=harness_source,
            harness_version=matrix.harness_version,
            requested_state=requested_state,
            measure_performance=measure_performance,
            screenshot=evidence / f"{label}-chromium-{profile_name}.png",
        )
        results.append({
            "browser": "chromium", "label": label, "profile": profile_name,
            "requestedState": requested_state, "result": result,
        })
        print(f"[{len(results)}] PASS chromium {label} {profile_name}", flush=True)
        return result

    core02 = _lesson(site, "core-02-algorithms-measurement")
    with serve_site(site) as server:
        file_url, http_url = browser_urls(site, core02, server.port)
        chromium_run("core-02-file", file_url, "desktop", "crossover")
        chromium_run("core-02-http", http_url, "desktop", "crossover")
        for label, url in (("core-02-file", file_url), ("core-02-http", http_url)):
            result = run_firefox_page(
                executable=firefox, url=url,
                profile=_profile_mapping(matrix.profiles["desktop"]),
                harness_source=harness_source, harness_version=matrix.harness_version,
                requested_state="crossover",
                screenshot=evidence / f"{label}-firefox-desktop.png",
            )
            results.append({"browser": "firefox", "label": label, "profile": "desktop", "requestedState": "crossover", "result": result})
            print(f"[{len(results)}] PASS firefox {label} desktop", flush=True)

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
                )
                assert_performance_contract(
                    profile=profile_name,
                    samples_ms=result["samplesMs"],
                    long_tasks_ms=result["longTasksMs"],
                    mutation_counts=result["workloadMutationSamples"],
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

        if platform_entry.safari is not None:
            safari = platform_entry.safari
            verify_safari_version(
                executable=Path(safari.executable), expected_version=safari.version,
                expected_build=safari.build,
            )
            try:
                result = run_safari_smoke(
                    safaridriver=Path("/usr/bin/safaridriver"), url=file_url,
                    screenshot=evidence / "core-02-file-safari-desktop.png",
                )
            except BrowserMatrixError:
                safari_blocked = True
                print("[165-166] BLOCKED safari Remote Automation session unavailable", flush=True)
            else:
                results.append({"browser": "safari", "label": "core-02-file", "profile": "desktop", "requestedState": None, "result": result})
                print(f"[{len(results)}] PASS safari core-02-file desktop", flush=True)
                result = run_safari_smoke(
                    safaridriver=Path("/usr/bin/safaridriver"), url=http_url,
                    screenshot=evidence / "core-02-http-safari-desktop.png",
                )
                results.append({"browser": "safari", "label": "core-02-http", "profile": "desktop", "requestedState": None, "result": result})
                print(f"[{len(results)}] PASS safari core-02-http desktop", flush=True)

    report = browser_evidence_report(
        harness_version=matrix.harness_version, platform_key=platform_entry.key,
        inventory=inventory, successful_runs=results,
        safari_blocked=safari_blocked,
    )
    _write_report(evidence / "report.json", report)
    if safari_blocked:
        raise BrowserMatrixError(
            "Safari release smoke blocked: Remote Automation session unavailable"
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=Path("outputs/browser-cache"))
    parser.add_argument("--evidence", type=Path, default=Path("outputs/browser-evidence"))
    options = parser.parse_args(argv)
    report = run_browser_contract(
        site=options.site, matrix_path=options.matrix,
        cache=options.cache, evidence=options.evidence,
    )
    print(f"browser contract passed: {len(report['runs'])} runs")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrowserMatrixError as error:
        print(f"browser contract failed: {error}", file=sys.stderr)
        raise SystemExit(1)
