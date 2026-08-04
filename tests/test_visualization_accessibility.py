from __future__ import annotations

import base64
import errno
from http.client import RemoteDisconnected
from html.parser import HTMLParser
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
import time
import unittest
from unittest import mock
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

from tools.install_test_browsers import (
    BrowserMatrixError,
    detect_host_platform,
    load_browser_matrix_bytes,
    resolve_platform,
)
from tools.run_browser_contract import (
    assert_leak_contract,
    assert_performance_contract,
    browser_evidence_report,
    browser_evidence_inventory,
    browser_urls,
    chromium_arguments,
    parse_browser_result,
    serve_site,
    validate_chromium_network_events,
    _write_report,
    BrowserEvidenceJournal,
    SafariSessionUnavailable,
    _instrumented_harness_source,
    _webdriver_request,
    _assemble_safari_instrumented_html,
    _safari_instrumented_document,
    browser_run_plan,
    run_safari_smoke,
    run_browser_contract,
    run_chromium_page,
    _remove_browser_profile,
    _shutdown_chromium,
    _cleanup_chromium_resources,
    _capture_chromium_screenshot,
    _BrowserDebuggingCommandError,
    _ChromiumTargetTransportError,
    _connect_chromium_debugging,
    _WebSocket,
    _new_debugging_target,
    _probe_debugging_endpoint,
    _wait_debugging_endpoint,
)

from curriculum_builder.visualizations import (
    VisualizationType,
    render_visualization,
)
from curriculum_builder.lessons import load_lesson_bytes
from curriculum_builder.build import build_site
import tests.test_visualization_rendering as visualization_rendering_tests


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CSS_PATH = REPOSITORY_ROOT / "static" / "visualizations.css"

_SEMANTIC_CONTAINERS = {
    VisualizationType.FLOW: ("visualization__ordered-model",),
    VisualizationType.HIERARCHY: ("visualization__hierarchy",),
    VisualizationType.COMPARISON: ("visualization__table",),
    VisualizationType.STATE_LOOP: ("visualization__nodes",),
    VisualizationType.CAUSAL: ("visualization__causal-model",),
    VisualizationType.TIMELINE: ("visualization__timeline-phases",),
    VisualizationType.NETWORK: (
        "visualization__components",
        "visualization__nodes",
    ),
    VisualizationType.MEMORY: ("visualization__nodes",),
    VisualizationType.MATRIX: ("visualization__table",),
    VisualizationType.STATE_MACHINE: ("visualization__states",),
}

_MULTI_COLUMN_CONTAINERS = frozenset(
    (kind, container)
    for kind, containers in _SEMANTIC_CONTAINERS.items()
    if kind not in {
        VisualizationType.COMPARISON,
        VisualizationType.HIERARCHY,
        VisualizationType.MATRIX,
    }
    for container in containers
)


def _css_blocks(source: str) -> tuple[tuple[str, str, int], ...]:
    blocks: list[tuple[str, str, int]] = []
    depth = 0
    opening = -1
    prelude_start = 0
    for index, character in enumerate(source):
        if character == "{":
            if depth == 0:
                opening = index
            depth += 1
        elif character == "}":
            depth -= 1
            if depth < 0:
                raise AssertionError("CSS has an unmatched closing brace")
            if depth == 0:
                prelude = source[prelude_start:opening].strip()
                blocks.append((prelude, source[opening + 1:index], opening))
                prelude_start = index + 1
    if depth:
        raise AssertionError("CSS has an unmatched opening brace")
    return tuple(blocks)


def _selector_list(source: str) -> tuple[str, ...]:
    selectors: list[str] = []
    start = 0
    depth = 0
    for index, character in enumerate(source):
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        elif character == "," and depth == 0:
            selectors.append(" ".join(source[start:index].split()))
            start = index + 1
    selectors.append(" ".join(source[start:].split()))
    return tuple(selectors)


def _css_value_tokens(source: str) -> tuple[str, ...]:
    tokens: list[str] = []
    start = 0
    depth = 0
    for index, character in enumerate(source):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                raise AssertionError(
                    "CSS value has an unmatched closing parenthesis"
                )
        elif character.isspace() and depth == 0:
            if source[start:index].strip():
                tokens.append(source[start:index].strip())
            start = index + 1
    if source[start:].strip():
        tokens.append(source[start:].strip())
    if depth:
        raise AssertionError("CSS value has an unmatched opening parenthesis")
    return tuple(tokens)


def _rules(source: str) -> tuple[tuple[str, dict[str, str], int], ...]:
    rules: list[tuple[str, dict[str, str], int]] = []
    for prelude, body, position in _css_blocks(source):
        if prelude.startswith(("@media", "@container")):
            for selector, nested_body, nested_position in _css_blocks(body):
                declarations = {
                    name.strip(): value.strip()
                    for declaration in nested_body.split(";")
                    if ":" in declaration
                    for name, value in (declaration.split(":", 1),)
                }
                for item in _selector_list(selector):
                    rules.append(
                        (item, declarations, position + nested_position)
                    )
        elif not prelude.startswith("@"):
            declarations = {
                name.strip(): value.strip()
                for declaration in body.split(";")
                if ":" in declaration
                for name, value in (declaration.split(":", 1),)
            }
            for item in _selector_list(prelude):
                rules.append((item, declarations, position))
    return tuple(rules)


def _specificity(selector: str) -> tuple[int, int, int]:
    ids = len(re.findall(r"#[a-zA-Z0-9_-]+", selector))
    classes = len(
        re.findall(
            r"\.[a-zA-Z0-9_-]+|\[[^]]+\]|:(?!:)[a-zA-Z-]+",
            selector,
        )
    )
    elements = len(
        re.findall(
            r"(?:^|[ >+~])(?:[a-zA-Z][a-zA-Z0-9-]*|\*)",
            selector,
        )
    )
    return ids, classes, elements


def _selector_classes(selector: str) -> frozenset[str]:
    return frozenset(re.findall(r"\.([a-zA-Z0-9_-]+)", selector))


def _media_rules(
    source: str,
    media_prelude: str,
) -> dict[str, dict[str, str]]:
    blocks = tuple(
        body
        for prelude, body, _ in _css_blocks(source)
        if " ".join(prelude.split()) == media_prelude
    )
    if len(blocks) != 1:
        raise AssertionError(f"expected one {media_prelude} block")
    return {
        selector: declarations
        for selector, declarations, _ in _rules(
            f"{media_prelude} {{{blocks[0]}}}"
        )
    }


class _HierarchyStructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, frozenset[str]]] = []
        self.list_depths: list[int] = []
        self.item_depths: list[int] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = dict(attrs)
        classes = frozenset((values.get("class") or "").split())
        in_hierarchy = any(
            "visualization__hierarchy" in ancestor_classes
            for _, ancestor_classes in self.stack
        )
        if in_hierarchy and tag in {"ul", "li"}:
            list_depth = sum(
                ancestor_tag == "ul"
                for ancestor_tag, _ in self.stack
            )
            if tag == "ul":
                self.list_depths.append(list_depth + 1)
            else:
                self.item_depths.append(list_depth)
        self.stack.append((tag, classes))

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1][0] != tag:
            raise AssertionError("rendered hierarchy has malformed nesting")
        self.stack.pop()


class _CausalStructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, frozenset[str]]] = []
        self.direct_children: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = dict(attrs)
        classes = frozenset((values.get("class") or "").split())
        if (
            self.stack
            and "visualization__causal-model" in self.stack[-1][1]
        ):
            self.direct_children.append(tag)
        self.stack.append((tag, classes))

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1][0] != tag:
            raise AssertionError("rendered causal model has malformed nesting")
        self.stack.pop()


class _SimulationReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_simulation = False
        self.model_nodes: set[str] = set()
        self.model_edges: set[str] = set()
        self.active_nodes: set[str] = set()
        self.active_edges: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = frozenset((values.get("class") or "").split())
        if tag == "figure" and values.get("data-simulation-kind"):
            if self.in_simulation:
                raise AssertionError("nested simulation figure")
            self.in_simulation = True
        if not self.in_simulation:
            return
        node_id = values.get("data-node-id")
        edge_id = values.get("data-edge-id")
        if node_id and "visualization__model-node" in classes:
            self.model_nodes.add(node_id)
        if edge_id and "visualization__model-edge" in classes:
            self.model_edges.add(edge_id)
        if node_id and "visualization__state-node" in classes:
            self.active_nodes.add(node_id)
        if edge_id and "visualization__state-edge" in classes:
            self.active_edges.add(edge_id)

    def handle_endtag(self, tag: str) -> None:
        if not self.in_simulation:
            return
        if tag == "figure":
            self.in_simulation = False


class VisualizationAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.css = CSS_PATH.read_text(encoding="utf-8")
        cls.payloads = (
            visualization_rendering_tests.VisualizationRenderingTests().payloads()
        )


class BrowserContractTests(VisualizationAccessibilityTests):
    def _matrix(self) -> dict[str, object]:
        archive = {
            "version": "123.0.1",
            "url": "https://storage.googleapis.com/browser.zip",
            "sha256": "a" * 64,
            "archiveFormat": "zip",
            "maxBytes": 1048576,
            "executable": "browser/bin/browser",
            "signaturePolicy": "linux-pinned-archive",
        }
        matrix = {
            "schemaVersion": 1,
            "harnessVersion": "1.0.0",
            "ciRunner": {
                "image": "ghcr.io/example/browser-runner",
                "digest": "sha256:" + "b" * 64,
            },
            "platforms": {
                "linux-x86_64": {
                    "browsers": {
                        "chromium": dict(archive),
                        "firefox": {**archive, "sha256": "c" * 64},
                    }
                },
                "macos-arm64": {
                    "browsers": {
                        "chromium": {**archive, "sha256": "d" * 64, "signaturePolicy": "adhoc-cft", "executableSha256": "1" * 64, "symlinks": {"browser/link": "bin/browser"}},
                        "firefox": {**archive, "sha256": "e" * 64, "signaturePolicy": "developer-id", "symlinks": {}},
                    },
                    "safari": {
                        "version": "26.0",
                        "build": "21624.2.5.11.4",
                        "executable": "/Applications/Safari.app/Contents/MacOS/Safari",
                        "smokeTransport": "loopback-http",
                        "smokeProfiles": ["desktop", "mobile"],
                    },
                },
            },
            "profiles": {
                "desktop": {
                    "width": 1440,
                    "height": 900,
                    "deviceScaleFactor": 1,
                    "cpuThrottleRate": 1,
                    "reducedMotion": False,
                    "forcedColors": False,
                },
                "mobile": {
                    "width": 390,
                    "height": 844,
                    "deviceScaleFactor": 2,
                    "cpuThrottleRate": 4,
                    "reducedMotion": False,
                    "forcedColors": False,
                },
                "reduced-motion": {
                    "width": 1440,
                    "height": 900,
                    "deviceScaleFactor": 1,
                    "cpuThrottleRate": 1,
                    "reducedMotion": True,
                    "forcedColors": False,
                },
                "forced-colors": {
                    "width": 1440,
                    "height": 900,
                    "deviceScaleFactor": 1,
                    "cpuThrottleRate": 1,
                    "reducedMotion": False,
                    "forcedColors": True,
                },
            },
            "fixtures": {
                "maximum": {
                    "path": "tests/browser/runtime-fixture.html",
                    "sha256": "f" * 64,
                },
                "memoryLessonId": "core-03-architecture-memory-caches",
                "distributedLessonId": "core-13-distributed-coordination-failure",
                "harnessSha256": "9" * 64,
            },
            "measurements": {
                "warmups": 3,
                "samples": 20,
                "resetCycles": 100,
                "desktopMedianMs": 25,
                "desktopLongTaskMs": 50,
                "desktopRunsWithoutLongTask": 19,
                "mobileMedianMs": 50,
                "mobileP95Ms": 100,
                "maxHeapGrowthBytes": 1048576,
                "maxHeapGrowthRatio": 0.05,
            },
        }
        return matrix

    def _bytes(self, value: dict[str, object]) -> bytes:
        return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()

    def test_matrix_is_closed_and_pins_exact_platform_browser_profiles(self) -> None:
        matrix = load_browser_matrix_bytes(self._bytes(self._matrix()))
        self.assertEqual(tuple(matrix.platforms), ("linux-x86_64", "macos-arm64"))
        self.assertEqual(matrix.profiles["desktop"].viewport, (1440, 900))
        self.assertEqual(matrix.profiles["mobile"].viewport, (390, 844))
        self.assertEqual(matrix.profiles["mobile"].device_scale_factor, 2)
        self.assertEqual(matrix.profiles["mobile"].cpu_throttle_rate, 4)
        safari = matrix.platforms["macos-arm64"].safari
        self.assertIsNotNone(safari)
        assert safari is not None
        self.assertEqual(safari.smoke_transport, "loopback-http")
        self.assertEqual(safari.smoke_profiles, ("desktop", "mobile"))

    def test_matrix_rejects_mutable_or_incomplete_release_authority(self) -> None:
        mutations = []
        no_digest = self._matrix()
        del no_digest["ciRunner"]["digest"]  # type: ignore[index]
        mutations.append(no_digest)
        extra_platform = self._matrix()
        extra_platform["platforms"]["linux-arm64"] = extra_platform["platforms"]["linux-x86_64"]  # type: ignore[index]
        mutations.append(extra_platform)
        missing_browser = self._matrix()
        del missing_browser["platforms"]["macos-arm64"]["browsers"]["firefox"]  # type: ignore[index]
        mutations.append(missing_browser)
        safari_file = self._matrix()
        safari_file["platforms"]["macos-arm64"]["safari"]["smokeTransport"] = "file"  # type: ignore[index]
        mutations.append(safari_file)
        safari_missing_mobile = self._matrix()
        safari_missing_mobile["platforms"]["macos-arm64"]["safari"]["smokeProfiles"] = ["desktop"]  # type: ignore[index]
        mutations.append(safari_missing_mobile)
        insecure_url = self._matrix()
        insecure_url["platforms"]["linux-x86_64"]["browsers"]["chromium"]["url"] = "http://example.test/browser.zip"  # type: ignore[index]
        mutations.append(insecure_url)
        bad_hash = self._matrix()
        bad_hash["platforms"]["linux-x86_64"]["browsers"]["chromium"]["sha256"] = "latest"  # type: ignore[index]
        mutations.append(bad_hash)
        unofficial_url = self._matrix()
        unofficial_url["platforms"]["linux-x86_64"]["browsers"]["chromium"]["url"] = "https://downloads.example.test/browser.zip"  # type: ignore[index]
        mutations.append(unofficial_url)
        version_drift = self._matrix()
        version_drift["platforms"]["linux-x86_64"]["browsers"]["chromium"]["version"] = "latest"  # type: ignore[index]
        mutations.append(version_drift)
        policy_swap = self._matrix()
        policy_swap["platforms"]["macos-arm64"]["browsers"]["chromium"]["signaturePolicy"] = "developer-id"  # type: ignore[index]
        mutations.append(policy_swap)
        missing_policy = self._matrix()
        del missing_policy["platforms"]["linux-x86_64"]["browsers"]["firefox"]["signaturePolicy"]  # type: ignore[index]
        mutations.append(missing_policy)
        for value in mutations:
            with self.subTest(value=value), self.assertRaises(BrowserMatrixError):
                load_browser_matrix_bytes(self._bytes(value))

    def test_host_key_is_exact_and_override_cannot_fallback(self) -> None:
        with mock.patch("tools.install_test_browsers.sys.platform", "darwin"), mock.patch(
            "tools.install_test_browsers.platform.machine", return_value="arm64"
        ):
            self.assertEqual(detect_host_platform(), "macos-arm64")
            matrix = load_browser_matrix_bytes(self._bytes(self._matrix()))
            self.assertEqual(resolve_platform(matrix, None).key, "macos-arm64")
            with self.assertRaisesRegex(BrowserMatrixError, "host"):
                resolve_platform(matrix, "linux-x86_64")
        with mock.patch("tools.install_test_browsers.sys.platform", "linux"), mock.patch(
            "tools.install_test_browsers.platform.machine", return_value="aarch64"
        ):
            with self.assertRaisesRegex(BrowserMatrixError, "unsupported"):
                detect_host_platform()

    def test_http_contract_uses_loopback_ephemeral_port_and_pages_subpath(self) -> None:
        with TemporaryDirectory() as temporary:
            site = Path(temporary)
            lesson = site / "lessons/core-02-algorithms-measurement/index.html"
            lesson.parent.mkdir(parents=True)
            lesson.write_text("<!doctype html><title>fixture</title>", encoding="utf-8")
            with serve_site(site) as server:
                self.assertEqual(server.host, "127.0.0.1")
                self.assertGreater(server.port, 0)
                file_url, http_url = browser_urls(site, lesson, server.port)
                self.assertTrue(file_url.startswith("file:///"))
                self.assertIn(
                    f"http://127.0.0.1:{server.port}/engineering-expert-curriculum/",
                    http_url,
                )

    def test_cdp_network_evidence_is_bounded_to_the_exact_target_origin(self) -> None:
        target = "http://127.0.0.1:49152/engineering-expert-curriculum/index.html"
        validate_chromium_network_events(
            [
                {"method": "Network.requestWillBeSent", "params": {"request": {"url": target}}},
                {"method": "Network.responseReceived", "params": {"response": {"url": "http://127.0.0.1:49152/styles.css"}}},
            ],
            target_url=target,
            truncated=False,
        )
        for events, truncated in (
            ([{"method": "Network.requestWillBeSent", "params": {"request": {"url": "http://127.0.0.1:49153/exfil"}}}], False),
            ([], True),
        ):
            with self.assertRaises(BrowserMatrixError):
                validate_chromium_network_events(
                    events, target_url=target, truncated=truncated
                )

    def test_file_network_evidence_stays_under_approved_roots_without_url_ambiguity(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            site = root / "site"
            fixture = root / "fixtures"
            outside = root / "outside.js"
            for path in (site / "index.html", site / "styles.css", fixture / "maximum.html", outside):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture", encoding="utf-8")
            target = (site / "index.html").as_uri()
            validate_chromium_network_events(
                [{"method": "Network.requestWillBeSent", "params": {"request": {"url": (site / "styles.css").as_uri()}}}],
                target_url=target, truncated=False,
                approved_file_roots=(site, fixture),
            )
            forbidden = (
                outside.as_uri(),
                "file://localhost" + (site / "styles.css").as_posix(),
                target + "?cache=1",
                target + "#fragment",
                (site / "%2e%2e" / "outside.js").as_uri().replace("%252e", "%2e"),
            )
            for candidate in forbidden:
                with self.subTest(candidate=candidate), self.assertRaises(BrowserMatrixError):
                    validate_chromium_network_events(
                        [{"method": "Network.requestWillBeSent", "params": {"request": {"url": candidate}}}],
                        target_url=target, truncated=False,
                        approved_file_roots=(site, fixture),
                    )

    def test_file_resource_observer_receives_only_closed_approved_root_prefixes(self) -> None:
        with TemporaryDirectory() as temporary:
            site = Path(temporary) / "site"
            fixture = Path(temporary) / "fixtures"
            site.mkdir()
            fixture.mkdir()
            source = _instrumented_harness_source(
                "/* harness */", approved_file_roots=(site, fixture)
            )
        self.assertIn(site.resolve().as_uri() + "/", source)
        self.assertIn(fixture.resolve().as_uri() + "/", source)
        self.assertIn("/* harness */", source)
        harness = (REPOSITORY_ROOT / "tests/browser/runtime-harness.js").read_text(encoding="utf-8")
        self.assertIn("__browserContractApprovedFileRoots", harness)
        self.assertIn("resource.protocol === 'file:'", harness)

    def test_performance_and_leak_thresholds_fail_closed(self) -> None:
        assert_performance_contract(
            profile="desktop",
            samples_ms=[20.0] * 19 + [51.0],
            long_tasks_ms=[0.0] * 19 + [51.0],
            mutation_counts=[1] * 20,
            instrumentation={"longTasks": True},
        )
        assert_performance_contract(
            profile="mobile",
            samples_ms=[40.0] * 19 + [100.0],
            long_tasks_ms=[0.0] * 20,
            mutation_counts=[1] * 20,
            instrumentation={"longTasks": True},
        )
        with self.assertRaises(BrowserMatrixError):
            assert_performance_contract(
                profile="desktop",
                samples_ms=[26.0] * 20,
                long_tasks_ms=[0.0] * 20,
                mutation_counts=[1] * 20,
                instrumentation={"longTasks": True},
            )
        with self.assertRaises(BrowserMatrixError):
            assert_performance_contract(
                profile="desktop",
                samples_ms=[0.0] * 20,
                long_tasks_ms=[0.0] * 20,
                mutation_counts=[1] * 20,
                instrumentation={"longTasks": True},
            )
        with self.assertRaises(BrowserMatrixError):
            assert_performance_contract(
                profile="desktop",
                samples_ms=[1.0] * 20,
                long_tasks_ms=[0.0] * 20,
                mutation_counts=[0] * 20,
                instrumentation={"longTasks": True},
            )
        with self.assertRaises(BrowserMatrixError):
            assert_performance_contract(
                profile="desktop", samples_ms=[1.0] * 20,
                long_tasks_ms=[0.0] * 20, mutation_counts=[1] * 20,
                instrumentation={"longTasks": False},
            )

    def test_harness_uses_real_long_tasks_exact_listener_semantics_and_runtime_errors_fail(self) -> None:
        source = (REPOSITORY_ROOT / "tests/browser/runtime-harness.js").read_text(
            encoding="utf-8"
        )
        for required in (
            "observer.takeRecords()", "await flushObserverCallbacks()",
            "listenerRegistry", "captureOption(options)", "once",
            "runtimeErrorCount > 0", "runtime-error",
            "resource.origin !== window.location.origin", "truncated",
        ):
            self.assertIn(required, source)
        self.assertNotIn("longTasksMs: samples.slice()", source)

    def test_maximum_fixture_is_enhanced_by_product_runtime_and_measured_by_native_actions(self) -> None:
        fixture = (REPOSITORY_ROOT / "tests/browser/runtime-fixture.html").read_text(
            encoding="utf-8"
        )
        harness = (REPOSITORY_ROOT / "tests/browser/runtime-harness.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('data-visualization-id="browser-maximum-fixture"', fixture)
        self.assertIn('data-interaction-mode="stepper"', fixture)
        self.assertEqual(fixture.count('class="visualization__model-node"'), 64)
        self.assertEqual(fixture.count('class="visualization__model-edge"'), 128)
        for action in ("next", "previous", "reset"):
            self.assertIn(f'data-action="{action}"', fixture)
        self.assertIn("click(root, 'next')", harness)
        self.assertIn("click(root, 'reset')", harness)
        self.assertNotIn("item.classList.add('is-active')", harness)
        assert_leak_contract(
            baseline={"domNodes": 100, "listeners": 5, "timers": 0, "heapBytes": 10_000_000},
            final={"domNodes": 100, "listeners": 5, "timers": 0, "heapBytes": 10_500_000},
            reset_cycles=100,
            instrumentation={"listeners": True, "timers": True, "gc": True},
        )
        with self.assertRaises(BrowserMatrixError):
            assert_leak_contract(
                baseline={"domNodes": 100, "listeners": 5, "timers": 0, "heapBytes": 10_000_000},
                final={"domNodes": 100, "listeners": 5, "timers": 0, "heapBytes": 10_000_000},
                reset_cycles=100,
                instrumentation={"listeners": True, "timers": True, "gc": False},
            )

    def test_repository_browser_matrix_pins_reviewed_release_authority(self) -> None:
        matrix = load_browser_matrix_bytes(
            (REPOSITORY_ROOT / "tests/browser-matrix.json").read_bytes()
        )
        self.assertEqual(
            (matrix.ci_image, matrix.ci_digest),
            (
                "mcr.microsoft.com/playwright/python",
                "sha256:80fd7c1aad9600ea348572dd46ca00b9ea31d890831f5838fc61319ab79900d2",
            ),
        )
        self.assertEqual(
            matrix.platforms["macos-arm64"].browsers["chromium"].sha256,
            "1c516b5d6c00a074034d5ce03dc1cc9bd2cde2a09293d9613244e0bc153cb80f",
        )
        fixture = REPOSITORY_ROOT / str(matrix.fixtures["maximum"]["path"])
        self.assertEqual(
            hashlib.sha256(fixture.read_bytes()).hexdigest(),
            matrix.fixtures["maximum"]["sha256"],
        )
        self.assertEqual(
            hashlib.sha256(
                (REPOSITORY_ROOT / "tests/browser/runtime-harness.js").read_bytes()
            ).hexdigest(),
            matrix.fixtures["harnessSha256"],
        )

    def test_outputs_ignore_is_exact_and_root_anchored(self) -> None:
        entries = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertEqual(entries.count("/outputs/"), 1)
        self.assertNotIn("outputs/", entries)
        self.assertFalse(any(entry in {"tests/", "static/", "content/"} for entry in entries))

    def test_evidence_inventory_covers_all_dynamic_types_and_regression_states(self) -> None:
        inventory = browser_evidence_inventory(
            (REPOSITORY_ROOT / "content/visualization-catalog.json").read_bytes()
        )
        self.assertEqual(len(inventory.dynamic_lessons), 12)
        self.assertEqual(set(inventory.diagram_type_lessons), {item.value for item in VisualizationType})
        self.assertEqual(len(inventory.regression_states), 36)
        self.assertEqual(inventory.profiles, ("desktop", "mobile", "reduced-motion", "forced-colors"))

    def test_all_real_simulation_active_references_resolve_to_rendered_model_elements(self) -> None:
        inventory = browser_evidence_inventory(
            (REPOSITORY_ROOT / "content/visualization-catalog.json").read_bytes()
        )
        with TemporaryDirectory(prefix=".browser-reference-", dir=REPOSITORY_ROOT.parent) as temporary:
            output = Path(temporary) / "site"
            build_site(
                REPOSITORY_ROOT / "content",
                REPOSITORY_ROOT / "templates",
                REPOSITORY_ROOT / "static",
                output,
                require_complete_curriculum=True,
            )
            for lesson_id in inventory.dynamic_lessons:
                parser = _SimulationReferenceParser()
                parser.feed(
                    (output / "lessons" / lesson_id / "index.html").read_text(encoding="utf-8")
                )
                with self.subTest(lesson_id=lesson_id):
                    self.assertTrue(parser.model_nodes)
                    self.assertTrue(parser.active_nodes <= parser.model_nodes)
                    self.assertTrue(parser.active_edges <= parser.model_edges)

    def test_chromium_arguments_are_explicit_bounded_and_enable_required_instrumentation(self) -> None:
        with mock.patch("tools.run_browser_contract.sys.platform", "linux"):
            args = chromium_arguments(
                Path("/cache/chrome"),
                "file:///tmp/site/index.html",
                self._matrix()["profiles"]["mobile"],  # type: ignore[index]
                Path("/tmp/profile"),
                oci_container_no_sandbox=True,
            )
        self.assertEqual(args[0], "/cache/chrome")
        self.assertIn("--headless=new", args)
        self.assertIn("--no-sandbox", args)
        self.assertIn("--remote-debugging-port=0", args)
        self.assertIn("--enable-precise-memory-info", args)
        self.assertIn("--js-flags=--expose-gc", args)
        self.assertEqual(args[-1], "about:blank")
        self.assertFalse(any("shell" in item for item in args))

        with mock.patch("tools.run_browser_contract.sys.platform", "linux"):
            default_linux_args = chromium_arguments(
                Path("/cache/chrome"),
                "file:///tmp/site/index.html",
                self._matrix()["profiles"]["mobile"],  # type: ignore[index]
                Path("/tmp/profile"),
            )
        self.assertNotIn("--no-sandbox", default_linux_args)

        with mock.patch("tools.run_browser_contract.sys.platform", "darwin"), \
                self.assertRaises(BrowserMatrixError):
            chromium_arguments(
                Path("/cache/chrome"),
                "file:///tmp/site/index.html",
                self._matrix()["profiles"]["mobile"],  # type: ignore[index]
                Path("/tmp/profile"),
                oci_container_no_sandbox=True,
            )

    def test_chromium_shutdown_prefers_cdp_before_process_signals(self) -> None:
        connection = mock.Mock()
        process = mock.Mock()
        process.wait.return_value = 0

        _shutdown_chromium(process, connection)

        connection.command.assert_called_once_with("Browser.close")
        connection.close.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=5)
        process.terminate.assert_not_called()
        process.kill.assert_not_called()

    def test_chromium_shutdown_falls_back_when_cdp_close_fails(self) -> None:
        connection = mock.Mock()
        connection.command.side_effect = BrowserMatrixError("CDP closed")
        process = mock.Mock()
        process.poll.return_value = None
        process.wait.return_value = 0

        _shutdown_chromium(process, connection)

        connection.close.assert_called_once_with()
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=5)
        process.kill.assert_not_called()

    def test_chromium_shutdown_stops_process_before_propagating_interrupt(self) -> None:
        connection = mock.Mock()
        connection.close.side_effect = KeyboardInterrupt("close interrupted")
        process = mock.Mock()
        process.wait.return_value = 0

        with self.assertRaisesRegex(KeyboardInterrupt, "close interrupted"):
            _shutdown_chromium(process, connection)

        process.wait.assert_called_once_with(timeout=5)
        process.terminate.assert_not_called()
        process.kill.assert_not_called()

    def test_chromium_shutdown_escalates_bounded_timeouts_to_kill(self) -> None:
        connection = mock.Mock()
        connection.command.side_effect = BrowserMatrixError("CDP closed")
        process = mock.Mock()
        process.poll.return_value = None
        process.wait.side_effect = (
            subprocess.TimeoutExpired("chrome", 5),
            0,
        )

        _shutdown_chromium(process, connection)

        self.assertEqual(process.wait.call_count, 2)
        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()

    def test_chromium_profile_cleanup_retries_only_transient_writer_races(self) -> None:
        with TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profile"
            profile.mkdir()
            transient = OSError(
                errno.ENOTEMPTY,
                "Directory not empty",
                str(profile / "Default"),
            )
            with mock.patch(
                "tools.run_browser_contract.shutil.rmtree",
                side_effect=(transient, None),
            ) as remove, mock.patch("tools.run_browser_contract.time.sleep") as sleep:
                _remove_browser_profile(profile)
        self.assertEqual(remove.call_count, 2)
        sleep.assert_called_once()

    def test_chromium_profile_cleanup_fails_after_a_bounded_busy_retry(self) -> None:
        with TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profile"
            profile.mkdir()
            busy = OSError(errno.EBUSY, "Device or resource busy", str(profile))
            with mock.patch(
                "tools.run_browser_contract.shutil.rmtree",
                side_effect=busy,
            ) as remove, mock.patch("tools.run_browser_contract.time.sleep"), \
                    self.assertRaisesRegex(
                        BrowserMatrixError, "bounded retries"
                    ):
                _remove_browser_profile(profile)
        self.assertEqual(remove.call_count, 50)

    def test_chromium_screenshot_retries_only_the_closed_empty_image_error(
        self,
    ) -> None:
        transient = _BrowserDebuggingCommandError(
            "Page.captureScreenshot", -32000, "Unable to capture screenshot"
        )
        connection = mock.Mock()
        connection.command.side_effect = (
            transient,
            transient,
            {"data": "cG5n"},
        )
        with mock.patch("tools.run_browser_contract.time.sleep") as sleep:
            self.assertEqual(
                _capture_chromium_screenshot(connection),
                {"data": "cG5n"},
            )
        self.assertEqual(connection.command.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_cdp_command_preserves_the_closed_screenshot_error_fields(self) -> None:
        connection = _WebSocket.__new__(_WebSocket)
        connection.identifier = 0
        connection.events = []
        connection.events_truncated = False
        payload = json.dumps({
            "id": 1,
            "error": {"code": -32000, "message": "Unable to capture screenshot"},
        }).encode("utf-8")
        with mock.patch.object(connection, "_send_frame"), mock.patch.object(
            connection, "_receive_frame", return_value=payload
        ), self.assertRaises(_BrowserDebuggingCommandError) as caught:
            connection.command("Page.captureScreenshot")
        self.assertEqual(caught.exception.method, "Page.captureScreenshot")
        self.assertEqual(caught.exception.code, -32000)
        self.assertEqual(caught.exception.detail, "Unable to capture screenshot")

    def test_cdp_command_does_not_expose_unbounded_or_control_error_data(self) -> None:
        unsafe_messages = ("secret\ninjected", "s" * 129)
        for unsafe_message in unsafe_messages:
            connection = _WebSocket.__new__(_WebSocket)
            connection.identifier = 0
            connection.events = []
            connection.events_truncated = False
            payload = json.dumps({
                "id": 1,
                "error": {
                    "code": -32000,
                    "message": unsafe_message,
                    "data": {"credential": "must-not-be-logged"},
                },
            }).encode("utf-8")
            with self.subTest(message=unsafe_message[:16]), mock.patch.object(
                connection, "_send_frame"
            ), mock.patch.object(
                connection, "_receive_frame", return_value=payload
            ), self.assertRaises(_BrowserDebuggingCommandError) as caught:
                connection.command("Page.captureScreenshot")
            diagnostic = str(caught.exception)
            self.assertEqual(
                diagnostic,
                "browser debugging command failed: Page.captureScreenshot",
            )
            self.assertIsNone(caught.exception.detail)
            self.assertNotIn("secret", diagnostic)
            self.assertNotIn("credential", diagnostic)

    def test_chromium_screenshot_preserves_final_retry_diagnostic(self) -> None:
        errors = tuple(
            _BrowserDebuggingCommandError(
                "Page.captureScreenshot", -32000, "Unable to capture screenshot"
            )
            for _ in range(3)
        )
        connection = mock.Mock()
        connection.command.side_effect = errors
        with mock.patch("tools.run_browser_contract.time.sleep") as sleep, \
                self.assertRaisesRegex(
                    BrowserMatrixError,
                    r"Page\.captureScreenshot.*-32000.*Unable to capture screenshot",
                ) as caught:
            _capture_chromium_screenshot(connection)
        self.assertIs(caught.exception, errors[-1])
        self.assertEqual(connection.command.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_chromium_screenshot_does_not_retry_other_cdp_errors(self) -> None:
        errors = (
            _BrowserDebuggingCommandError(
                "Page.captureScreenshot", -32001, "Unable to capture screenshot"
            ),
            _BrowserDebuggingCommandError(
                "Page.captureScreenshot", -32000, "Internal error"
            ),
            _BrowserDebuggingCommandError(
                "Runtime.evaluate", -32000, "Unable to capture screenshot"
            ),
        )
        for error in errors:
            connection = mock.Mock()
            connection.command.side_effect = error
            with self.subTest(error=str(error)), mock.patch(
                "tools.run_browser_contract.time.sleep"
            ) as sleep, self.assertRaises(_BrowserDebuggingCommandError) as caught:
                _capture_chromium_screenshot(connection)
            self.assertIs(caught.exception, error)
            connection.command.assert_called_once_with(
                "Page.captureScreenshot",
                {"format": "png", "captureBeyondViewport": False},
            )
            sleep.assert_not_called()

    def test_chromium_debugging_readiness_retries_only_transport_failure(self) -> None:
        process = mock.Mock()
        process.poll.return_value = None
        transport = _ChromiumTargetTransportError(
            "Chromium target endpoint is not ready"
        )
        with mock.patch(
            "tools.run_browser_contract._probe_debugging_endpoint",
            side_effect=(transport, None),
        ) as probe, mock.patch(
            "tools.run_browser_contract.time.sleep"
        ) as sleep:
            _wait_debugging_endpoint(
                9222, process, deadline=time.monotonic() + 1.0
            )
        self.assertEqual(probe.call_count, 2)
        sleep.assert_called_once()

    def test_chromium_debugging_readiness_fails_immediately_after_process_exit(self) -> None:
        process = mock.Mock()
        process.poll.return_value = 1
        with mock.patch(
            "tools.run_browser_contract._probe_debugging_endpoint"
        ) as probe, self.assertRaisesRegex(
            BrowserMatrixError,
            "exited before its debugging endpoint became ready",
        ):
            _wait_debugging_endpoint(
                9222, process, deadline=time.monotonic() + 1.0
            )
        probe.assert_not_called()

    def test_chromium_readiness_stops_when_process_exits_after_transport_error(
        self,
    ) -> None:
        process = mock.Mock()
        process.poll.side_effect = (None, 9)
        transport = _ChromiumTargetTransportError(
            "Chromium target endpoint is not ready"
        )
        with mock.patch(
            "tools.run_browser_contract._probe_debugging_endpoint",
            side_effect=transport,
        ) as probe, mock.patch(
            "tools.run_browser_contract.time.sleep"
        ) as sleep, self.assertRaisesRegex(
            BrowserMatrixError,
            "exited before its debugging endpoint became ready",
        ) as caught:
            _wait_debugging_endpoint(
                9222, process, deadline=time.monotonic() + 1.0
            )
        probe.assert_called_once()
        sleep.assert_not_called()
        self.assertIs(caught.exception.__cause__, transport)

    def test_chromium_readiness_preserves_last_transport_at_deadline(
        self,
    ) -> None:
        process = mock.Mock()
        process.poll.return_value = None
        transport = _ChromiumTargetTransportError(
            "Chromium target endpoint is not ready"
        )
        with mock.patch(
            "tools.run_browser_contract._probe_debugging_endpoint",
            side_effect=transport,
        ) as probe, mock.patch(
            "tools.run_browser_contract.time.monotonic",
            side_effect=(0.0, 0.5),
        ), mock.patch(
            "tools.run_browser_contract.time.sleep"
        ) as sleep, self.assertRaisesRegex(
            BrowserMatrixError,
            "before its deadline",
        ) as caught:
            _wait_debugging_endpoint(9222, process, deadline=0.25)
        probe.assert_called_once_with(9222, 0.25)
        sleep.assert_not_called()
        self.assertIs(caught.exception.__cause__, transport)

    def test_chromium_readiness_transport_failure_is_typed_and_exact_loopback(self) -> None:
        with mock.patch(
            "tools.run_browser_contract.urlopen",
            side_effect=ConnectionRefusedError(errno.ECONNREFUSED, "not ready"),
        ) as request, self.assertRaises(
            _ChromiumTargetTransportError
        ) as caught:
            _probe_debugging_endpoint(9222, 0.25)
        sent = request.call_args.args[0]
        self.assertEqual(
            sent.full_url,
            "http://127.0.0.1:9222/json/version",
        )
        self.assertEqual(sent.method, "GET")
        self.assertIsInstance(caught.exception.__cause__, ConnectionRefusedError)

    def test_chromium_readiness_http_response_is_protocol_failure(self) -> None:
        response = HTTPError(
            "http://127.0.0.1:9222/json/version",
            503,
            "not ready",
            {},
            io.BytesIO(b"unavailable"),
        )
        with mock.patch(
            "tools.run_browser_contract.urlopen",
            side_effect=response,
        ), self.assertRaisesRegex(
            BrowserMatrixError,
            "returned an HTTP error",
        ) as caught:
            _probe_debugging_endpoint(9222, 0.25)
        self.assertNotIsInstance(
            caught.exception,
            _ChromiumTargetTransportError,
        )

    def test_chromium_readiness_does_not_retry_nontransient_os_errors(self) -> None:
        failures = (
            OSError(errno.EMFILE, "too many files"),
            OSError(errno.ENFILE, "system file table full"),
            OSError(errno.EACCES, "permission denied"),
            OSError(errno.EINVAL, "invalid argument"),
            URLError(OSError(errno.EACCES, "permission denied")),
        )
        for failure in failures:
            with self.subTest(failure=repr(failure)), mock.patch(
                "tools.run_browser_contract.urlopen",
                side_effect=failure,
            ), self.assertRaises(BrowserMatrixError) as caught:
                _probe_debugging_endpoint(9222, 0.25)
            self.assertNotIsInstance(
                caught.exception,
                _ChromiumTargetTransportError,
            )

    def test_chromium_readiness_types_only_allowlisted_transient_errors(self) -> None:
        failures = (
            OSError(errno.ECONNREFUSED, "refused"),
            OSError(errno.ECONNRESET, "reset"),
            OSError(errno.ECONNABORTED, "aborted"),
            OSError(errno.ETIMEDOUT, "timed out"),
            URLError(OSError(errno.ECONNREFUSED, "refused")),
            RemoteDisconnected("remote closed"),
        )
        for failure in failures:
            with self.subTest(failure=repr(failure)), mock.patch(
                "tools.run_browser_contract.urlopen",
                side_effect=failure,
            ), self.assertRaises(_ChromiumTargetTransportError):
                _probe_debugging_endpoint(9222, 0.25)

    def test_chromium_websocket_handshake_uses_absolute_startup_deadline(self) -> None:
        stream = mock.Mock()
        with mock.patch(
            "tools.run_browser_contract.socket.create_connection",
            return_value=stream,
        ) as connect, mock.patch(
            "tools.run_browser_contract.time.monotonic",
            side_effect=(0.0, 0.2, 1.1),
        ), self.assertRaisesRegex(
            BrowserMatrixError,
            "deadline",
        ):
            _WebSocket(
                "ws://127.0.0.1:9222/devtools/page/target",
                5.0,
                deadline=1.0,
            )
        connect.assert_called_once_with(("127.0.0.1", 9222), timeout=1.0)
        stream.sendall.assert_called_once()
        stream.recv.assert_not_called()
        stream.close.assert_called_once()

    def test_chromium_websocket_rejects_valid_handshake_completed_after_deadline(
        self,
    ) -> None:
        stream = mock.Mock()
        nonce = b"\0" * 16
        key = base64.b64encode(nonce).decode("ascii")
        accepted = base64.b64encode(hashlib.sha1(
            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
        ).digest()).decode("ascii")
        stream.recv.return_value = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            f"Sec-WebSocket-Accept: {accepted}\r\n\r\n"
        ).encode("ascii")
        with mock.patch(
            "tools.run_browser_contract.socket.create_connection",
            return_value=stream,
        ), mock.patch(
            "tools.run_browser_contract.os.urandom",
            return_value=nonce,
        ), mock.patch(
            "tools.run_browser_contract.time.monotonic",
            side_effect=(0.0, 0.1, 0.2, 1.1),
        ), self.assertRaisesRegex(
            BrowserMatrixError,
            "deadline",
        ):
            _WebSocket(
                "ws://127.0.0.1:9222/devtools/page/target",
                5.0,
                deadline=1.0,
            )
        stream.recv.assert_called_once_with(4096)
        stream.close.assert_called_once()

    def test_chromium_debugging_orchestration_uses_one_put_and_shared_deadline(
        self,
    ) -> None:
        process = mock.Mock()
        process.poll.return_value = None
        connection = mock.Mock()
        with mock.patch(
            "tools.run_browser_contract._wait_debugging_endpoint"
        ) as readiness, mock.patch(
            "tools.run_browser_contract._new_debugging_target",
            return_value="ws://127.0.0.1:9222/devtools/page/target",
        ) as target, mock.patch(
            "tools.run_browser_contract._WebSocket",
            return_value=connection,
        ) as websocket, mock.patch(
            "tools.run_browser_contract.time.monotonic",
            return_value=0.25,
        ):
            result = _connect_chromium_debugging(
                9222,
                process,
                deadline=1.0,
                timeout=5.0,
            )
        self.assertIs(result, connection)
        readiness.assert_called_once_with(9222, process, deadline=1.0)
        target.assert_called_once_with(9222, 0.75)
        websocket.assert_called_once_with(
            "ws://127.0.0.1:9222/devtools/page/target",
            5.0,
            deadline=1.0,
        )

    def test_chromium_put_transport_failure_is_single_shot_and_exit_aware(self) -> None:
        process = mock.Mock()
        process.poll.side_effect = (None, 9)
        transport = _ChromiumTargetTransportError(
            "Chromium target endpoint transport failed"
        )
        with mock.patch(
            "tools.run_browser_contract._wait_debugging_endpoint"
        ), mock.patch(
            "tools.run_browser_contract._new_debugging_target",
            side_effect=transport,
        ) as target, self.assertRaisesRegex(
            BrowserMatrixError,
            "exited while creating",
        ) as caught:
            _connect_chromium_debugging(
                9222,
                process,
                deadline=time.monotonic() + 1.0,
                timeout=5.0,
            )
        target.assert_called_once()
        self.assertIs(caught.exception.__cause__, transport)

    def test_chromium_process_exit_before_put_skips_target_creation(self) -> None:
        process = mock.Mock()
        process.poll.return_value = 7
        with mock.patch(
            "tools.run_browser_contract._wait_debugging_endpoint"
        ), mock.patch(
            "tools.run_browser_contract._new_debugging_target"
        ) as target, self.assertRaisesRegex(
            BrowserMatrixError,
            "exited before creating",
        ):
            _connect_chromium_debugging(
                9222,
                process,
                deadline=time.monotonic() + 1.0,
                timeout=5.0,
            )
        target.assert_not_called()

    def test_chromium_target_protocol_failures_are_not_retryable(self) -> None:
        cases = (
            (b"{" + b"x" * (64 * 1024), "byte budget"),
            (b"not-json", "response is invalid"),
            (b"\xff", "response is invalid"),
            (json.dumps({"id": "target"}).encode("utf-8"), "lacks its debugging URL"),
            (json.dumps({
                "webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/target",
            }).encode("utf-8"), "not exact loopback"),
            (json.dumps({
                "webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/page/target",
            }).encode("utf-8"), "not exact loopback"),
        )
        for payload, message in cases:
            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = payload
            with self.subTest(message=message), mock.patch(
                "tools.run_browser_contract.urlopen",
                return_value=response,
            ), self.assertRaisesRegex(BrowserMatrixError, message) as caught:
                _new_debugging_target(9222, 0.25)
            self.assertNotIsInstance(
                caught.exception,
                _ChromiumTargetTransportError,
            )

        process = mock.Mock()
        process.poll.return_value = None
        protocol = BrowserMatrixError("Chromium target response is invalid")
        with mock.patch(
            "tools.run_browser_contract._probe_debugging_endpoint",
            side_effect=protocol,
        ) as probe, mock.patch(
            "tools.run_browser_contract.time.sleep"
        ) as sleep, self.assertRaises(BrowserMatrixError) as caught:
            _wait_debugging_endpoint(
                9222, process, deadline=time.monotonic() + 1.0
            )
        self.assertIs(caught.exception, protocol)
        probe.assert_called_once()
        sleep.assert_not_called()

    def test_chromium_target_creation_uses_one_exact_loopback_put(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/target",
        }).encode("utf-8")
        with mock.patch(
            "tools.run_browser_contract.urlopen",
            return_value=response,
        ) as request:
            websocket = _new_debugging_target(9222, 0.25)
        self.assertEqual(
            websocket,
            "ws://127.0.0.1:9222/devtools/page/target",
        )
        sent = request.call_args.args[0]
        self.assertEqual(
            sent.full_url,
            "http://127.0.0.1:9222/json/new?about%3Ablank",
        )
        self.assertEqual(sent.method, "PUT")
        request.assert_called_once()

    def test_chromium_cleanup_failure_does_not_mask_the_primary_error(self) -> None:
        with TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profile"
            profile.mkdir()
            with mock.patch(
                "tools.run_browser_contract.tempfile.mkdtemp",
                return_value=str(profile),
            ), mock.patch(
                "tools.run_browser_contract.subprocess.Popen",
                side_effect=OSError("launch failed"),
            ), mock.patch(
                "tools.run_browser_contract._remove_browser_profile",
                side_effect=BrowserMatrixError("profile cleanup failed"),
            ), self.assertRaisesRegex(OSError, "launch failed") as caught:
                run_chromium_page(
                    executable=Path("/cache/chrome"),
                    url="file:///tmp/site/index.html",
                    profile=self._matrix()["profiles"]["mobile"],  # type: ignore[index]
                    harness_source="",
                    harness_version="1.0.0",
                    screenshot=Path(temporary) / "shot.png",
                )
        self.assertIn(
            "profile cleanup failed",
            "\n".join(getattr(caught.exception, "__notes__", ())),
        )

    def test_chromium_process_cleanup_failure_does_not_mask_browser_error(self) -> None:
        process = mock.Mock()
        with TemporaryDirectory() as temporary, mock.patch(
            "tools.run_browser_contract.subprocess.Popen",
            return_value=process,
        ), mock.patch(
            "tools.run_browser_contract._wait_debugging_port",
            side_effect=BrowserMatrixError("browser result failed"),
        ), mock.patch(
            "tools.run_browser_contract._shutdown_chromium",
            side_effect=BrowserMatrixError("process cleanup failed"),
        ), self.assertRaisesRegex(
            BrowserMatrixError, "browser result failed"
        ) as caught:
            run_chromium_page(
                executable=Path("/cache/chrome"),
                url="file:///tmp/site/index.html",
                profile=self._matrix()["profiles"]["mobile"],  # type: ignore[index]
                harness_source="",
                harness_version="1.0.0",
                screenshot=Path(temporary) / "shot.png",
            )
        self.assertIn(
            "process cleanup failed",
            "\n".join(getattr(caught.exception, "__notes__", ())),
        )

    def test_chromium_cleanup_preserves_primary_and_all_secondary_failures(
        self,
    ) -> None:
        primary = RuntimeError("browser result failed")
        process = mock.Mock()
        with TemporaryDirectory() as temporary, mock.patch(
            "tools.run_browser_contract._shutdown_chromium",
            side_effect=KeyboardInterrupt("shutdown interrupted"),
        ), mock.patch(
            "tools.run_browser_contract._remove_browser_profile",
            side_effect=SystemExit("profile cleanup exited"),
        ):
            _cleanup_chromium_resources(
                process=process, connection=None,
                profile=Path(temporary) / "profile",
                primary_error=primary,
            )
        notes = "\n".join(getattr(primary, "__notes__", ()))
        self.assertIn("KeyboardInterrupt: shutdown interrupted", notes)
        self.assertIn("SystemExit: profile cleanup exited", notes)

    def test_chromium_cleanup_preserves_first_failure_type_without_primary(
        self,
    ) -> None:
        process = mock.Mock()
        with TemporaryDirectory() as temporary, mock.patch(
            "tools.run_browser_contract._shutdown_chromium",
            side_effect=KeyboardInterrupt("shutdown interrupted"),
        ), mock.patch(
            "tools.run_browser_contract._remove_browser_profile",
            side_effect=SystemExit("profile cleanup exited"),
        ), self.assertRaises(KeyboardInterrupt) as caught:
            _cleanup_chromium_resources(
                process=process, connection=None,
                profile=Path(temporary) / "profile",
                primary_error=None,
            )
        self.assertIn(
            "SystemExit: profile cleanup exited",
            "\n".join(getattr(caught.exception, "__notes__", ())),
        )

    def test_dumped_dom_result_is_unique_bounded_versioned_and_fail_closed(self) -> None:
        result = {
            "schemaVersion": 1,
            "harnessVersion": "1.0.0",
            "passed": True,
            "simulationCount": 1,
            "reachedStateIds": ["initial"],
            "requestedStateReached": True,
            "runtimeEnhancedCount": 1,
            "runtimeErrorCount": 0,
            "runtimeErrors": [],
            "warmupsMs": [],
            "samplesMs": [],
            "workloadMutationSamples": [],
            "longTasksMs": [],
            "observedLongTasksMs": [],
            "resetCycles": 100,
            "baseline": {"domNodes": 1, "listeners": 1, "timers": 0, "heapBytes": 1},
            "final": {"domNodes": 1, "listeners": 1, "timers": 0, "heapBytes": 1},
            "instrumentation": {"listeners": True, "timers": True, "gc": False, "longTasks": True},
            "violations": [],
            "violationKinds": [],
            "externalResources": [],
            "resourceNames": ["visualization.js"],
            "truncated": {"violations": False, "runtimeErrors": False, "longTasks": False, "externalResources": False, "resourceNames": False},
        }
        encoded = __import__("html").escape(json.dumps(result), quote=True)
        dumped = f'<p id="browser-contract-result" data-browser-contract-result="{encoded}"></p>'
        self.assertTrue(parse_browser_result(dumped, expected_harness_version="1.0.0")["passed"])
        for invalid in ("<p></p>", dumped + dumped, dumped.replace("1.0.0", "2.0.0")):
            with self.subTest(invalid=invalid[:30]), self.assertRaises(BrowserMatrixError):
                parse_browser_result(invalid, expected_harness_version="1.0.0")
        for mutation in (
            {**result, "unexpected": True},
            {**result, "runtimeErrorCount": 1},
            {**result, "truncated": {**result["truncated"], "resourceNames": True}},
        ):
            encoded = __import__("html").escape(json.dumps(mutation), quote=True)
            with self.assertRaises(BrowserMatrixError):
                parse_browser_result(
                    f'<p id="browser-contract-result" data-browser-contract-result="{encoded}"></p>',
                    expected_harness_version="1.0.0",
                )
        failed = {
            **result, "passed": False,
            "violations": ["reset-restoration"],
            "violationKinds": ["reset-restoration"],
        }
        failed_encoded = __import__("html").escape(json.dumps(failed), quote=True)
        with self.assertRaisesRegex(BrowserMatrixError, "reset-restoration"):
            parse_browser_result(
                f'<p id="browser-contract-result" data-browser-contract-result="{failed_encoded}"></p>',
                expected_harness_version="1.0.0",
            )

    def test_requested_hybrid_state_is_traversed_before_generic_control_exploration(self) -> None:
        source = (
            REPOSITORY_ROOT / "tests/browser/runtime-harness.js"
        ).read_text(encoding="utf-8")
        apply_position = source.index("applyRequestedConditions(root);")
        traversal_position = source.index("for (var targetStep = 0;")
        generic_position = source.index(
            "var controls = root.querySelectorAll(", traversal_position
        )
        self.assertLess(apply_position, traversal_position)
        self.assertLess(traversal_position, generic_position)
        self.assertIn(
            "if (record(root)) { return; }\n      click(root, 'reset');",
            source[traversal_position:generic_position],
        )

    def test_safari_preflight_blocker_is_atomically_reported_for_both_smokes(self) -> None:
        inventory = browser_evidence_inventory(
            (REPOSITORY_ROOT / "content/visualization-catalog.json").read_bytes()
        )
        successful = [
            {"browser": "chromium", "label": f"run-{index}", "result": {"passed": True}}
            for index in range(167)
        ]
        report = browser_evidence_report(
            harness_version="1.0.0", platform_key="macos-arm64",
            inventory=inventory, successful_runs=successful,
            safari_blocked=True,
        )
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(len(report["runs"]), 169)
        self.assertEqual(
            [row["label"] for row in report["runs"][-2:]],
            ["core-02-http-desktop", "core-02-http-mobile"],
        )
        self.assertEqual(
            [row["profile"] for row in report["runs"][-2:]],
            ["desktop", "mobile"],
        )
        self.assertTrue(all(
            row["reason"] == "remote-automation-session-unavailable"
            for row in report["runs"][-2:]
        ))
        with self.assertRaises(BrowserMatrixError):
            browser_evidence_report(
                harness_version="1.0.0", platform_key="macos-arm64",
                inventory=inventory, successful_runs=successful[:-1],
                safari_blocked=True,
            )
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.json"
            _write_report(path, report)
            self.assertEqual(json.loads(path.read_bytes()), report)
            self.assertFalse((path.parent / ".report.json.pending").exists())

    def test_partial_report_records_each_pass_fail_block_and_not_run_with_provenance(self) -> None:
        inventory = browser_evidence_inventory(
            (REPOSITORY_ROOT / "content/visualization-catalog.json").read_bytes()
        )
        plan = browser_run_plan(inventory, include_safari=True)
        self.assertEqual(len(plan), 169)
        self.assertEqual(
            [(run["browser"], run["label"], run["profile"]) for run in plan[:4]],
            [
                ("chromium", "core-02-file", "desktop"),
                ("chromium", "core-02-http", "desktop"),
                ("firefox", "core-02-file", "desktop"),
                ("firefox", "core-02-http", "desktop"),
            ],
        )
        self.assertEqual(
            [(run["browser"], run["label"], run["profile"]) for run in plan[-2:]],
            [
                ("safari", "core-02-http-desktop", "desktop"),
                ("safari", "core-02-http-mobile", "mobile"),
            ],
        )
        provenance = {
            "matrixSha256": "a" * 64,
            "fixtureSha256": "b" * 64,
            "harnessSha256": "c" * 64,
            "platform": {"os": "darwin", "architecture": "arm64"},
            "browsers": {
                "chromium": {"version": "151.0.7922.71", "build": "151.0.7922.71", "verificationStatus": "not-run"},
                "firefox": {"version": "153.0.1", "build": "153.0.1", "verificationStatus": "not-run"},
                "safari": {"version": "26.5", "build": "21624.2.5.11.4", "verificationStatus": "not-run"},
            },
        }
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.json"
            journal = BrowserEvidenceJournal(
                path=path, harness_version="1.0.0", inventory=inventory,
                provenance=provenance, plan=plan,
            )
            journal.record(plan[0], status="passed", result={"passed": True})
            journal.record(plan[1], status="failed", reason="browser-contract-failed")
            journal.record(plan[-2], status="blocked", reason="remote-automation-session-unavailable")
            report = json.loads(path.read_bytes())
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["provenance"], provenance)
            self.assertEqual(
                [row["status"] for row in report["runs"][:3]],
                ["passed", "failed", "not-run"],
            )
            self.assertEqual(report["runs"][-2]["status"], "blocked")
            self.assertEqual(report["runs"][-1]["status"], "not-run")
            with self.assertRaises(BrowserMatrixError):
                journal.record(plan[-1], status="blocked", reason="generic-webdriver-error")
            journal.record(
                plan[-1], status="blocked",
                reason=SafariSessionUnavailable.reason,
            )

    def test_runner_atomically_terminalizes_every_post_journal_failure(self) -> None:
        with TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            report_path = evidence / "report.json"

            def fail_after_journal(**_kwargs: object) -> dict[str, object]:
                _write_report(report_path, {
                    "schemaVersion": 1, "status": "running",
                    "runs": [{"label": "lesson", "status": "not-run"}],
                })
                raise BrowserMatrixError("lesson lookup failed")

            with mock.patch(
                "tools.run_browser_contract._run_browser_contract",
                side_effect=fail_after_journal,
            ):
                with self.assertRaisesRegex(BrowserMatrixError, "lesson lookup"):
                    run_browser_contract(
                        site=Path(temporary), matrix_path=Path("matrix.json"),
                        cache=Path(temporary) / "cache", evidence=evidence,
                    )
            report = json.loads(report_path.read_bytes())
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["failure"], "browser-contract-aborted")
            self.assertEqual(report["runs"][0]["status"], "not-run")
            self.assertFalse((evidence / ".report.json.pending").exists())

    def test_runner_propagates_explicit_oci_no_sandbox_authority(self) -> None:
        expected = {"runs": []}
        with TemporaryDirectory() as temporary, mock.patch(
            "tools.run_browser_contract._run_browser_contract",
            return_value=expected,
        ) as run:
            actual = run_browser_contract(
                site=Path(temporary), matrix_path=Path("matrix.json"),
                cache=Path(temporary) / "cache",
                evidence=Path(temporary) / "evidence",
                oci_container_no_sandbox=True,
            )
        self.assertIs(actual, expected)
        self.assertIs(run.call_args.kwargs["oci_container_no_sandbox"], True)

    def test_runner_terminalizes_interrupt_and_exit_without_replacing_the_base_exception(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for interruption in (KeyboardInterrupt(), SystemExit(73)):
                with self.subTest(interruption=type(interruption).__name__):
                    evidence = root / type(interruption).__name__
                    report_path = evidence / "report.json"

                    def interrupt_after_journal(**_kwargs: object) -> dict[str, object]:
                        _write_report(report_path, {
                            "schemaVersion": 1, "status": "running",
                            "runs": [
                                {"label": "complete", "status": "passed"},
                                {"label": "remaining", "status": "not-run"},
                            ],
                        })
                        raise interruption

                    with mock.patch(
                        "tools.run_browser_contract._run_browser_contract",
                        side_effect=interrupt_after_journal,
                    ):
                        with self.assertRaises(type(interruption)) as caught:
                            run_browser_contract(
                                site=root, matrix_path=root / "matrix.json",
                                cache=root / "cache", evidence=evidence,
                            )
                    self.assertIs(caught.exception, interruption)
                    report = json.loads(report_path.read_bytes())
                    self.assertEqual(report["status"], "failed")
                    self.assertEqual(report["failure"], "browser-contract-aborted")
                    self.assertEqual(
                        [run["status"] for run in report["runs"]],
                        ["passed", "not-run"],
                    )
                    self.assertFalse((evidence / ".report.json.pending").exists())

    def test_report_terminalization_failure_cannot_mask_keyboard_interrupt(self) -> None:
        interruption = KeyboardInterrupt()
        with TemporaryDirectory() as temporary, mock.patch(
            "tools.run_browser_contract._run_browser_contract",
            side_effect=interruption,
        ), mock.patch(
            "tools.run_browser_contract._terminalize_browser_report",
            side_effect=OSError("injected atomic report failure"),
        ):
            with self.assertRaises(KeyboardInterrupt) as caught:
                run_browser_contract(
                    site=Path(temporary), matrix_path=Path("matrix.json"),
                    cache=Path(temporary) / "cache",
                    evidence=Path(temporary) / "evidence",
                )
        self.assertIs(caught.exception, interruption)

    def test_safari_smoke_uses_preinstrumented_document_and_returns_its_result(self) -> None:
        process = mock.Mock()
        process.poll.return_value = None
        expected = {"passed": True, "schemaVersion": 1}
        requests = mock.Mock(side_effect=(
            {"sessionId": "session-1"},
            {"x": 0, "y": 0, "width": 1440, "height": 952},
            {"width": 1440, "height": 900, "devicePixelRatio": 1},
            None, "published", "Lesson",
            "<html></html>",
            {"element-6066-11e4-a52e-4f735466cecf": "reset-1"}, None,
            __import__("base64").b64encode(b"png").decode("ascii"), None,
        ))
        with TemporaryDirectory() as temporary, \
                mock.patch("tools.run_browser_contract.subprocess.Popen", return_value=process), \
                mock.patch("tools.run_browser_contract._webdriver_request", requests), \
                mock.patch("tools.run_browser_contract.parse_browser_result", return_value=expected) as parser:
            screenshot = Path(temporary) / "safari.png"
            result = run_safari_smoke(
                safaridriver=Path("/usr/bin/safaridriver"),
                url="http://127.0.0.1:8123/lesson.html",
                screenshot=screenshot,
                harness_version="1.0.0",
                viewport=(1440, 900),
            )
            screenshot_bytes = screenshot.read_bytes()
        self.assertEqual(result, {
            **expected,
            "observedViewport": {
                "width": 1440, "height": 900, "devicePixelRatio": 1,
            },
        })
        execute_calls = [
            call for call in requests.call_args_list
            if call.args[2].endswith("/execute/sync")
        ]
        self.assertEqual(len(execute_calls), 2)
        self.assertIn("window.innerWidth", execute_calls[0].args[3]["script"])
        self.assertIn("browser-contract-result", execute_calls[1].args[3]["script"])
        rect_calls = [
            call for call in requests.call_args_list
            if call.args[2].endswith("/window/rect")
        ]
        self.assertEqual([call.args[1] for call in rect_calls], ["POST"])
        self.assertEqual(rect_calls[0].args[3], {"width": 1440, "height": 900})
        parser.assert_called_once_with("<html></html>", expected_harness_version="1.0.0")
        self.assertEqual(screenshot_bytes, b"png")

    def test_safari_smoke_rejects_file_authority_and_unconfirmed_viewport(self) -> None:
        for url in (
            "file:///tmp/lesson.html",
            "http://localhost:8123/lesson.html",
            "http://127.0.0.1:8123/lesson.html?mutable=1",
            "http://user@127.0.0.1:8123/lesson.html",
        ):
            with self.subTest(url=url), self.assertRaisesRegex(
                BrowserMatrixError, "loopback HTTP"
            ):
                run_safari_smoke(
                    safaridriver=Path("/usr/bin/safaridriver"), url=url,
                    screenshot=Path("unused.png"), harness_version="1.0.0",
                    viewport=(1440, 900),
                )
        process = mock.Mock()
        process.poll.return_value = None
        requests = mock.Mock(side_effect=(
            {"sessionId": "session-1"},
            {"x": 0, "y": 0, "width": 1280, "height": 720},
            {"width": "unknown", "height": 720, "devicePixelRatio": 1},
            None,
        ))
        with mock.patch("tools.run_browser_contract.subprocess.Popen", return_value=process), \
                mock.patch("tools.run_browser_contract._webdriver_request", requests), \
                self.assertRaisesRegex(BrowserMatrixError, "viewport"):
            run_safari_smoke(
                safaridriver=Path("/usr/bin/safaridriver"),
                url="http://127.0.0.1:8123/lesson.html",
                screenshot=Path("unused.png"), harness_version="1.0.0",
                viewport=(1440, 900),
            )

    def test_only_transient_safari_session_creation_failure_is_typed_blocked(self) -> None:
        process = mock.Mock()
        process.poll.return_value = None

        def transient(*_args: object, **_kwargs: object) -> object:
            raise BrowserMatrixError("transport") from ConnectionRefusedError("not ready")

        with mock.patch("tools.run_browser_contract.subprocess.Popen", return_value=process), \
                mock.patch("tools.run_browser_contract._webdriver_request", side_effect=transient), \
                mock.patch("tools.run_browser_contract.time.monotonic", side_effect=(0.0, 0.0, 1.0)), \
                mock.patch("tools.run_browser_contract.time.sleep"):
            with self.assertRaises(SafariSessionUnavailable):
                run_safari_smoke(
                    safaridriver=Path("/usr/bin/safaridriver"), url="http://127.0.0.1:8123/lesson.html",
                    screenshot=Path("unused.png"),
                    harness_version="1.0.0", viewport=(1440, 900), timeout=0.5,
                )

        with mock.patch("tools.run_browser_contract.subprocess.Popen", return_value=process), \
                mock.patch(
                    "tools.run_browser_contract._webdriver_request",
                    side_effect=BrowserMatrixError("protocol failure"),
                ):
            with self.assertRaises(BrowserMatrixError) as caught:
                run_safari_smoke(
                    safaridriver=Path("/usr/bin/safaridriver"), url="http://127.0.0.1:8123/lesson.html",
                    screenshot=Path("unused.png"),
                    harness_version="1.0.0", viewport=(1440, 900), timeout=0.5,
                )
        self.assertNotIsInstance(caught.exception, SafariSessionUnavailable)

    def test_safari_http_error_blocks_only_the_exact_remote_automation_response(self) -> None:
        exact = {
            "value": {
                "error": "session not created",
                "message": "Could not create a session: You must enable the 'Allow Remote Automation' option in Safari's Develop menu to control Safari via WebDriver.",
                "stacktrace": "",
            }
        }
        generic = {
            "value": {
                "error": "session not created",
                "message": "Safari crashed during startup",
                "stacktrace": "",
            }
        }
        for body, blocked in ((exact, True), (generic, False)):
            response = HTTPError(
                "http://127.0.0.1:8123/session", 500, "error", {},
                io.BytesIO(json.dumps(body).encode("utf-8")),
            )
            with self.subTest(blocked=blocked), mock.patch(
                "tools.run_browser_contract.urlopen", side_effect=response,
            ):
                with self.assertRaises(BrowserMatrixError) as caught:
                    _webdriver_request(8123, "POST", "/session", {}, 1.0)
            self.assertEqual(
                isinstance(caught.exception, SafariSessionUnavailable), blocked
            )

    def test_safari_document_installs_harness_before_csp_and_product_runtime(self) -> None:
        original = b"""<!doctype html><html><head>
<meta http-equiv="Content-Security-Policy" content="script-src 'self'">
</head><body><script src="product.js"></script></body></html>"""
        assembled = _assemble_safari_instrumented_html(
            original, "window.__preNavigationHarness = true;"
        ).decode("utf-8")
        harness = assembled.index("window.__preNavigationHarness = true")
        self.assertLess(harness, assembled.index("Content-Security-Policy"))
        self.assertLess(harness, assembled.index("product.js"))
        self.assertIn("<!doctype html>", assembled)
        runtime_harness = (
            REPOSITORY_ROOT / "tests/browser/runtime-harness.js"
        ).read_text(encoding="utf-8")
        self.assertIn("reset-restoration", runtime_harness)

    def test_safari_instrumented_document_preserves_http_origin_and_is_always_removed(self) -> None:
        with TemporaryDirectory() as temporary:
            site = Path(temporary) / "site"
            source = site / "lesson" / "index.html"
            source.parent.mkdir(parents=True)
            source.write_text("<!doctype html><html><head></head><body></body></html>", encoding="utf-8")
            with _safari_instrumented_document(
                source_document=source,
                target_url="http://127.0.0.1:8123/lesson/index.html",
                harness_source="window.__harness = true;",
                approved_file_roots=(site,), requested_state="crossover",
            ) as instrumented_url:
                parsed = urlsplit(instrumented_url)
                self.assertEqual((parsed.scheme, parsed.hostname, parsed.port), ("http", "127.0.0.1", 8123))
                instrumented = source.parent / Path(parsed.path).name
                self.assertEqual(instrumented.parent.resolve(), source.parent.resolve())
                self.assertTrue(instrumented.is_file())
                self.assertIn("crossover", instrumented.read_text(encoding="utf-8"))
            self.assertFalse(instrumented.exists())

    def test_accessibility_explorer_is_a_finite_manual_audit_not_an_at_emulator(self) -> None:
        path = REPOSITORY_ROOT / (
            "content/lessons/core-16-hci-usability-accessibility/lesson.json"
        )
        document = json.loads(path.read_bytes())
        visual = document["visualizations"][0]
        simulation = visual["simulation"]
        self.assertEqual(simulation["interactionMode"], "explorer")
        self.assertEqual(
            tuple(parameter["id"] for parameter in simulation["parameters"]),
            ("viewport", "focus-step", "motion-preference"),
        )
        selections = {
            tuple(sorted(state.get("when", {}).items()))
            for state in simulation["states"]
            if state["id"] != simulation["initialStateId"]
        }
        self.assertEqual(len(selections), 12)
        self.assertEqual(len(selections), len(simulation["states"]) - 1)
        model = load_lesson_bytes(path.read_bytes(), path.name).visualizations[0]
        rendered = str(render_visualization(document["id"], model))
        for atom in (
            "focus order", "reflow checklist", "prefers-reduced-motion",
            "支援技術のエミュレータではありません", 'data-action="next"',
            'data-action="previous"', 'data-action="reset"',
            "完全な遷移", "観測結果",
        ):
            self.assertIn(atom, rendered)

    def test_meaning_specific_selectors_match_real_renderer_containers(self) -> None:
        selectors = {selector for selector, _, _ in _rules(self.css)}
        for kind, containers in _SEMANTIC_CONTAINERS.items():
            with self.subTest(kind=kind.value):
                html = render_visualization(
                    "core-01-systems-tradeoffs",
                    visualization_rendering_tests._visual(
                        kind, self.payloads[kind]
                    ),
                ).value
                self.assertIn(f"visualization--{kind.value}", html)
                for container in containers:
                    self.assertIn(container, html)
                    self.assertIn(
                        f".visualization--{kind.value} .{container}",
                        selectors,
                    )

    def test_hierarchy_groups_real_nested_lists_with_non_color_boundaries(self) -> None:
        html = render_visualization(
            "core-01-systems-tradeoffs",
            visualization_rendering_tests._visual(
                VisualizationType.HIERARCHY,
                self.payloads[VisualizationType.HIERARCHY],
            ),
        ).value
        parser = _HierarchyStructureParser()
        parser.feed(html)
        parser.close()
        self.assertEqual(parser.stack, [])
        self.assertEqual(parser.list_depths, [1, 2])
        self.assertEqual(parser.item_depths, [1, 2])

        first_media = min(
            position
            for prelude, _, position in _css_blocks(self.css)
            if prelude.startswith("@media")
        )
        rules = {
            selector: declarations
            for selector, declarations, _ in _rules(self.css[:first_media])
        }
        container = ".visualization--hierarchy .visualization__hierarchy"
        root_list = f"{container} > ul"
        direct_item = f"{container} > ul > li"
        nested_list = f"{container} li > ul"
        nested_item = f"{container} li > ul > li"
        hierarchy_selectors = (
            container,
            root_list,
            direct_item,
            nested_list,
            nested_item,
        )
        for selector in hierarchy_selectors:
            self.assertIn(selector, rules)

        self.assertFalse(
            {
                "grid-template-columns",
                "grid-auto-flow",
                "grid-auto-columns",
            }
            & rules[container].keys()
        )
        self.assertEqual(rules[root_list].get("list-style-type"), "disc")
        self.assertEqual(rules[nested_list].get("list-style-type"), "circle")
        for selector in (root_list, direct_item, nested_list, nested_item):
            with self.subTest(selector=selector):
                declarations = rules[selector]
                border = declarations.get("border-inline-start", "")
                self.assertRegex(border, r"^[1-9][0-9]*px\s+solid\s+currentColor$")
                self.assertIn("padding-inline-start", declarations)
                self.assertTrue(
                    {"margin-block", "margin-block-start"}
                    & declarations.keys()
                )

        mobile = _media_rules(self.css, "@media (max-width: 20rem)")
        self.assertEqual(
            mobile[nested_list].get("margin-inline-start"),
            "0",
        )
        self.assertIn("padding-inline-start", mobile[nested_list])
        for selector in (direct_item, nested_item):
            self.assertIn("padding-inline-start", mobile[selector])

        container_narrow = _media_rules(
            self.css,
            "@container (max-width: 20rem)",
        )
        self.assertEqual(
            container_narrow[nested_list].get("margin-inline-start"),
            "0",
        )
        self.assertIn("padding-inline-start", container_narrow[nested_list])
        for selector in (direct_item, nested_item):
            self.assertIn("padding-inline-start", container_narrow[selector])

        forced_colors = _media_rules(
            self.css,
            "@media (forced-colors: active)",
        )
        for selector in (root_list, direct_item, nested_list, nested_item):
            self.assertEqual(
                forced_colors[selector].get("border-color"),
                "currentColor",
            )

        print_rules = _media_rules(self.css, "@media print")
        for selector in (direct_item, nested_item):
            self.assertEqual(
                print_rules[selector].get("break-inside"),
                "avoid",
            )

    def test_causal_pairs_fill_two_columns_by_row(self) -> None:
        html = render_visualization(
            "core-01-systems-tradeoffs",
            visualization_rendering_tests._visual(
                VisualizationType.CAUSAL,
                self.payloads[VisualizationType.CAUSAL],
            ),
        ).value
        parser = _CausalStructureParser()
        parser.feed(html)
        parser.close()
        self.assertEqual(parser.stack, [])
        self.assertEqual(parser.direct_children, ["dt", "dd"] * 4)

        first_media = min(
            position
            for prelude, _, position in _css_blocks(self.css)
            if prelude.startswith("@media")
        )
        desktop_rules = {
            selector: declarations
            for selector, declarations, _ in _rules(self.css[:first_media])
        }
        selector = ".visualization--causal .visualization__causal-model"
        self.assertIn(selector, desktop_rules)
        declarations = desktop_rules[selector]
        self.assertEqual(declarations.get("display"), "grid")
        self.assertEqual(
            _css_value_tokens(declarations.get("grid-template-columns", "")),
            ("max-content", "minmax(0, 1fr)"),
        )
        self.assertIn(declarations.get("grid-auto-flow"), {None, "row"})
        self.assertNotIn("grid-auto-columns", declarations)

        mobile = _media_rules(self.css, "@media (max-width: 20rem)")
        self.assertEqual(mobile[selector].get("grid-template-columns"), "1fr")
        self.assertEqual(mobile[selector].get("grid-auto-flow"), "row")

    def test_narrow_overrides_preserve_dom_row_order_without_implicit_columns(self) -> None:
        top_level = _css_blocks(self.css)
        mobile_blocks = tuple(
            (body, position)
            for prelude, body, position in top_level
            if "@media (max-width: 20rem)" == " ".join(prelude.split())
        )
        self.assertEqual(len(mobile_blocks), 1)
        mobile_body, mobile_position = mobile_blocks[0]
        container_blocks = tuple(
            (body, position)
            for prelude, body, position in top_level
            if "@container (max-width: 20rem)" == " ".join(prelude.split())
        )
        self.assertEqual(len(container_blocks), 1)
        _, container_position = container_blocks[0]
        mobile_rules = {
            selector: (declarations, position)
            for selector, declarations, position in _rules(
                f"@media (max-width: 20rem) {{{mobile_body}}}"
            )
        }
        desktop_rules = {
            selector: (declarations, position)
            for selector, declarations, position in _rules(
                self.css[:mobile_position]
            )
        }
        container_rules = _media_rules(
            self.css,
            "@container (max-width: 20rem)",
        )
        expected_narrow = {
            "grid-template-columns": "1fr",
            "grid-auto-flow": "row",
        }
        for kind, container in _MULTI_COLUMN_CONTAINERS:
            selector = f".visualization--{kind.value} .{container}"
            with self.subTest(selector=selector):
                self.assertIn(selector, desktop_rules)
                self.assertIn(selector, mobile_rules)
                desktop_declarations, _ = desktop_rules[selector]
                mobile_declarations, _ = mobile_rules[selector]
                self.assertIn("grid-template-columns", desktop_declarations)
                self.assertIn(
                    desktop_declarations.get("grid-auto-flow"),
                    {None, "row"},
                )
                self.assertNotIn("grid-auto-columns", desktop_declarations)
                node_classes = {
                    f"visualization--{kind.value}",
                    container,
                }
                competing_desktop_rules = [
                    (candidate, position)
                    for candidate, (declarations, position) in desktop_rules.items()
                    if _selector_classes(candidate)
                    and _selector_classes(candidate) <= node_classes
                    and {
                        "grid-template-columns",
                        "grid-auto-flow",
                    }
                    & declarations.keys()
                ]
                self.assertTrue(competing_desktop_rules)
                self.assertLessEqual(
                    max(
                        _specificity(candidate)
                        for candidate, _ in competing_desktop_rules
                    ),
                    _specificity(selector),
                )
                self.assertLess(
                    max(position for _, position in competing_desktop_rules),
                    mobile_position,
                )
                self.assertLess(
                    max(position for _, position in competing_desktop_rules),
                    container_position,
                )
                self.assertLessEqual(
                    max(
                        _specificity(candidate)
                        for candidate, _ in competing_desktop_rules
                    ),
                    _specificity(selector),
                )
                self.assertEqual(
                    {name: mobile_declarations.get(name) for name in expected_narrow},
                    expected_narrow,
                )
                self.assertNotIn("grid-auto-columns", mobile_declarations)
                self.assertIn(selector, container_rules)
                self.assertEqual(
                    {
                        name: container_rules[selector].get(name)
                        for name in expected_narrow
                    },
                    expected_narrow,
                )
                self.assertNotIn("grid-auto-columns", container_rules[selector])
        wrapping_selectors = {
            f".visualization--{kind.value} .{container}"
            for kind, container in _MULTI_COLUMN_CONTAINERS
            if kind is not VisualizationType.CAUSAL
        }
        generated_connectors = [
            selector
            for selector, _, _ in _rules(self.css)
            if any(selector.startswith(f"{base} >") for base in wrapping_selectors)
            and re.search(r"::(?:before|after)\b", selector)
        ]
        self.assertEqual(generated_connectors, [])

        # Narrow rules only change layout. All instructional information stays
        # in the semantic DOM instead of width-dependent generated content.
        for selector in wrapping_selectors:
            narrow_declarations = (
                mobile_rules[selector][0],
                container_rules[selector],
            )
            for declarations in narrow_declarations:
                with self.subTest(selector=selector):
                    self.assertNotIn("display", declarations)
                    self.assertNotIn("visibility", declarations)
                    self.assertNotIn("content", declarations)

    def test_grid_contents_can_shrink_and_wrap_unbroken_text(self) -> None:
        desktop = {
            selector: declarations
            for selector, declarations, _ in _rules(self.css)
        }
        self.assertEqual(
            desktop[".visualization :is(dt, dd, li, th, td)"].get(
                "min-inline-size"
            ),
            "0",
        )
        self.assertEqual(
            desktop[".visualization :is(dt, dd, li, th, td)"].get(
                "overflow-wrap"
            ),
            "anywhere",
        )

    def test_uses_shared_base_and_exact_closed_modifier_set(self) -> None:
        modifiers = set(
            re.findall(r"\.visualization--([a-z-]+)\b", self.css)
        )
        self.assertEqual(
            modifiers,
            {
                "flow",
                "hierarchy",
                "comparison",
                "state-loop",
                "causal",
                "timeline",
                "network",
                "memory",
                "matrix",
                "state-machine",
            },
        )
        self.assertRegex(self.css, r"(?s)\.visualization\s*\{[^}]+\}")

    def test_reflows_at_320px_without_generated_layout_connectors(self) -> None:
        mobile = re.search(
            r"@media\s*\(max-width:\s*20rem\)\s*\{(?P<body>.*?)(?=\n@media|\Z)",
            self.css,
            re.DOTALL,
        )
        self.assertIsNotNone(mobile)
        assert mobile is not None
        self.assertIn("grid-template-columns: 1fr", mobile.group("body"))
        self.assertNotRegex(mobile.group("body"), r"::(?:before|after)")

    def test_supports_focus_state_and_logical_layout_without_color_only_state(self) -> None:
        self.assertIn(":focus-visible", self.css)
        self.assertRegex(self.css, r"outline:\s*(?!none)")
        self.assertRegex(
            self.css,
            r"\b(?:margin|padding|border)-(?:inline|block)(?:-(?:start|end))?:",
        )
        self.assertRegex(
            self.css,
            r"(?s)\[aria-current=[\"']step[\"']\].*?(?:border|outline|font-weight)",
        )

    def test_supports_forced_colors_reduced_motion_and_print(self) -> None:
        self.assertIn("@media (forced-colors: active)", self.css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.css)
        self.assertIn("@media print", self.css)
        self.assertNotIn("forced-color-adjust: none", self.css.casefold())
        self.assertRegex(
            self.css,
            r"(?s)@media print.*?\.visualization__simulation-oracle.*?display:\s*block",
        )
        self.assertRegex(
            self.css,
            r"(?s)@media print.*?\.visualization__controls.*?display:\s*none",
        )

    def test_generated_content_is_connector_only_and_never_essential_text(self) -> None:
        values = re.findall(r"\bcontent\s*:\s*([^;]+);", self.css)
        self.assertTrue(values)
        self.assertTrue(
            all(value.strip() in {'""', "''", "none"} for value in values),
            values,
        )

    def test_layout_uses_only_css_grid_flex_and_pseudo_connectors(self) -> None:
        self.assertRegex(self.css, r"display:\s*(?:grid|flex)")
        self.assertNotRegex(self.css, r"\b(?:svg|canvas)\b")


if __name__ == "__main__":
    unittest.main()
