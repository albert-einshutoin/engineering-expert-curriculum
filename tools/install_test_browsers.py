#!/usr/bin/env python3
"""Provision only browser archives pinned by the release browser matrix."""

from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
import errno
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from types import MappingProxyType
from typing import Callable, Iterator, Mapping
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
import zipfile


MATRIX_MAX_BYTES = 128 * 1024
PLATFORM_KEYS = ("linux-x86_64", "macos-arm64")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_VERSION = re.compile(r"[0-9]+(?:\.[0-9]+){1,4}\Z")
_OCI_IMAGE = re.compile(r"(?:[a-z0-9.-]+(?::[0-9]+)?/)+[a-z0-9._/-]+\Z")
_ARCHIVE_FORMATS = frozenset({"zip", "tar.xz", "dmg"})
_OFFICIAL_ARCHIVE_HOSTS = frozenset({"storage.googleapis.com", "archive.mozilla.org"})


class BrowserMatrixError(ValueError):
    """A bounded browser release contract could not be verified."""


@dataclass(frozen=True, slots=True)
class BrowserArchive:
    version: str
    url: str
    sha256: str
    archive_format: str
    max_bytes: int
    executable: str
    symlinks: tuple[tuple[str, str], ...] = ()
    signature_policy: str = "linux-pinned-archive"
    executable_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class SafariInstall:
    version: str
    build: str
    executable: str


@dataclass(frozen=True, slots=True)
class PlatformEntry:
    key: str
    browsers: Mapping[str, BrowserArchive]
    safari: SafariInstall | None


@dataclass(frozen=True, slots=True)
class BrowserProfile:
    viewport: tuple[int, int]
    device_scale_factor: int
    cpu_throttle_rate: int
    reduced_motion: bool
    forced_colors: bool


@dataclass(frozen=True, slots=True)
class BrowserMatrix:
    schema_version: int
    harness_version: str
    ci_image: str
    ci_digest: str
    platforms: Mapping[str, PlatformEntry]
    profiles: Mapping[str, BrowserProfile]
    fixtures: Mapping[str, object]
    measurements: Mapping[str, int | float]
    source_sha256: str


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BrowserMatrixError("browser matrix contains a duplicate key")
        result[key] = value
    return result


def _object(value: object, keys: frozenset[str], field: str) -> dict[str, object]:
    if type(value) is not dict:
        raise BrowserMatrixError(f"{field} must be an object")
    actual = frozenset(value)
    if actual != keys:
        raise BrowserMatrixError(f"{field} has missing or extra fields")
    return value


def _integer(value: object, field: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise BrowserMatrixError(f"{field} is outside its closed integer range")
    return value


def _number(value: object, field: str, minimum: float, maximum: float) -> float:
    if type(value) not in (int, float) or not minimum <= float(value) <= maximum:
        raise BrowserMatrixError(f"{field} is outside its closed numeric range")
    return float(value)


def _safe_relative(value: object, field: str) -> str:
    if type(value) is not str or not value or "\\" in value:
        raise BrowserMatrixError(f"{field} must be a safe relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise BrowserMatrixError(f"{field} must be a safe relative path")
    return value


def _link_target(value: object, field: str) -> str:
    if type(value) is not str or not value or "\\" in value:
        raise BrowserMatrixError(f"{field} must be a relative internal link target")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise BrowserMatrixError(f"{field} must be a relative internal link target")
    return value


def _archive(value: object, field: str, *, macos: bool) -> BrowserArchive:
    keys = {"version", "url", "sha256", "archiveFormat", "maxBytes", "executable", "signaturePolicy"}
    if macos:
        keys.add("symlinks")
    is_chromium = field.endswith(".chromium")
    if macos and is_chromium:
        keys.add("executableSha256")
    item = _object(
        value,
        frozenset(keys),
        field,
    )
    version = item["version"]
    if type(version) is not str or _VERSION.fullmatch(version) is None:
        raise BrowserMatrixError(f"{field}.version must be an exact numeric version")
    url = item["url"]
    if type(url) is not str:
        raise BrowserMatrixError(f"{field}.url must be HTTPS")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https" or parsed.hostname not in _OFFICIAL_ARCHIVE_HOSTS
        or parsed.username or parsed.password or parsed.port not in (None, 443)
        or parsed.fragment
    ):
        raise BrowserMatrixError(f"{field}.url must be an official HTTPS URL")
    digest = item["sha256"]
    if type(digest) is not str or _HEX64.fullmatch(digest) is None:
        raise BrowserMatrixError(f"{field}.sha256 must be 64 lowercase hexadecimal characters")
    archive_format = item["archiveFormat"]
    if archive_format not in _ARCHIVE_FORMATS:
        raise BrowserMatrixError(f"{field}.archiveFormat is unsupported")
    symlinks: tuple[tuple[str, str], ...] = ()
    if macos:
        raw_links = item["symlinks"]
        if type(raw_links) is not dict:
            raise BrowserMatrixError(f"{field}.symlinks must be an exact object")
        parsed_links = tuple(
            (
                _safe_relative(path, f"{field}.symlinks.path"),
                _link_target(target, f"{field}.symlinks.target"),
            )
            for path, target in raw_links.items()
        )
        if tuple(path for path, _ in parsed_links) != tuple(sorted(path for path, _ in parsed_links)):
            raise BrowserMatrixError(f"{field}.symlinks must be sorted")
        symlinks = parsed_links
    expected_policy = (
        "adhoc-cft" if macos and is_chromium
        else "developer-id" if macos
        else "linux-pinned-archive"
    )
    if item["signaturePolicy"] != expected_policy:
        raise BrowserMatrixError(f"{field}.signaturePolicy does not match its closed browser policy")
    executable_sha256 = None
    if macos and is_chromium:
        executable_sha256 = item["executableSha256"]
        if type(executable_sha256) is not str or _HEX64.fullmatch(executable_sha256) is None:
            raise BrowserMatrixError(f"{field}.executableSha256 must be exact")
    return BrowserArchive(
        version=version,
        url=url,
        sha256=digest,
        archive_format=archive_format,
        max_bytes=_integer(item["maxBytes"], f"{field}.maxBytes", 1, 512 * 1024 * 1024),
        executable=_safe_relative(item["executable"], f"{field}.executable"),
        symlinks=symlinks,
        signature_policy=expected_policy,
        executable_sha256=executable_sha256,
    )


def load_browser_matrix_bytes(raw: bytes) -> BrowserMatrix:
    if type(raw) is not bytes or not raw or len(raw) > MATRIX_MAX_BYTES:
        raise BrowserMatrixError("browser matrix bytes are empty, mutable, or over budget")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(text, object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise BrowserMatrixError("browser matrix is not strict UTF-8 JSON") from error
    root = _object(
        value,
        frozenset({"schemaVersion", "harnessVersion", "ciRunner", "platforms", "profiles", "fixtures", "measurements"}),
        "matrix",
    )
    if root["schemaVersion"] != 1:
        raise BrowserMatrixError("matrix.schemaVersion must equal 1")
    harness_version = root["harnessVersion"]
    if type(harness_version) is not str or _VERSION.fullmatch(harness_version) is None:
        raise BrowserMatrixError("matrix.harnessVersion must be exact")
    runner = _object(root["ciRunner"], frozenset({"image", "digest"}), "matrix.ciRunner")
    image = runner["image"]
    digest = runner["digest"]
    if type(image) is not str or _OCI_IMAGE.fullmatch(image) is None:
        raise BrowserMatrixError("matrix.ciRunner.image must be registry-qualified")
    if type(digest) is not str or not digest.startswith("sha256:") or _HEX64.fullmatch(digest[7:]) is None:
        raise BrowserMatrixError("matrix.ciRunner.digest must pin an OCI digest")

    platforms_raw = root["platforms"]
    if type(platforms_raw) is not dict or tuple(platforms_raw) != PLATFORM_KEYS:
        raise BrowserMatrixError("matrix.platforms must contain the exact ordered platform keys")
    platforms: dict[str, PlatformEntry] = {}
    for key in PLATFORM_KEYS:
        required = {"browsers"} | ({"safari"} if key == "macos-arm64" else set())
        item = _object(platforms_raw[key], frozenset(required), f"matrix.platforms.{key}")
        browsers = item["browsers"]
        if type(browsers) is not dict or tuple(browsers) != ("chromium", "firefox"):
            raise BrowserMatrixError(f"matrix.platforms.{key}.browsers must pin Chromium and Firefox")
        parsed_browsers = {
            name: _archive(browser, f"matrix.platforms.{key}.browsers.{name}", macos=key == "macos-arm64")
            for name, browser in browsers.items()
        }
        safari = None
        if key == "macos-arm64":
            safari_raw = _object(item["safari"], frozenset({"version", "build", "executable"}), "matrix.platforms.macos-arm64.safari")
            if type(safari_raw["version"]) is not str or _VERSION.fullmatch(safari_raw["version"]) is None:
                raise BrowserMatrixError("Safari version must be exact")
            if type(safari_raw["build"]) is not str or _VERSION.fullmatch(safari_raw["build"]) is None:
                raise BrowserMatrixError("Safari build must be exact")
            executable = safari_raw["executable"]
            if type(executable) is not str or not executable.startswith("/Applications/"):
                raise BrowserMatrixError("Safari executable must be the installed application path")
            safari = SafariInstall(safari_raw["version"], safari_raw["build"], executable)
        platforms[key] = PlatformEntry(key, MappingProxyType(parsed_browsers), safari)

    expected_profiles = ("desktop", "mobile", "reduced-motion", "forced-colors")
    profiles_raw = root["profiles"]
    if type(profiles_raw) is not dict or tuple(profiles_raw) != expected_profiles:
        raise BrowserMatrixError("matrix.profiles must contain the exact profile set")
    profiles: dict[str, BrowserProfile] = {}
    profile_keys = frozenset({"width", "height", "deviceScaleFactor", "cpuThrottleRate", "reducedMotion", "forcedColors"})
    for name, value in profiles_raw.items():
        item = _object(value, profile_keys, f"matrix.profiles.{name}")
        if type(item["reducedMotion"]) is not bool or type(item["forcedColors"]) is not bool:
            raise BrowserMatrixError(f"matrix.profiles.{name} media flags must be booleans")
        profiles[name] = BrowserProfile(
            (_integer(item["width"], "profile.width", 320, 4096), _integer(item["height"], "profile.height", 320, 4096)),
            _integer(item["deviceScaleFactor"], "profile.deviceScaleFactor", 1, 4),
            _integer(item["cpuThrottleRate"], "profile.cpuThrottleRate", 1, 16),
            item["reducedMotion"], item["forcedColors"],
        )
    expected_profile_values = {
        "desktop": ((1440, 900), 1, 1, False, False),
        "mobile": ((390, 844), 2, 4, False, False),
        "reduced-motion": ((1440, 900), 1, 1, True, False),
        "forced-colors": ((1440, 900), 1, 1, False, True),
    }
    for name, expected in expected_profile_values.items():
        actual = profiles[name]
        if (actual.viewport, actual.device_scale_factor, actual.cpu_throttle_rate, actual.reduced_motion, actual.forced_colors) != expected:
            raise BrowserMatrixError(f"matrix.profiles.{name} drifted from the release contract")

    fixtures = _object(root["fixtures"], frozenset({"maximum", "memoryLessonId", "distributedLessonId", "harnessSha256"}), "matrix.fixtures")
    maximum = _object(fixtures["maximum"], frozenset({"path", "sha256"}), "matrix.fixtures.maximum")
    _safe_relative(maximum["path"], "matrix.fixtures.maximum.path")
    if type(maximum["sha256"]) is not str or _HEX64.fullmatch(maximum["sha256"]) is None:
        raise BrowserMatrixError("maximum fixture digest must be exact")
    if type(fixtures["harnessSha256"]) is not str or _HEX64.fullmatch(fixtures["harnessSha256"]) is None:
        raise BrowserMatrixError("browser harness digest must be exact")
    for key in ("memoryLessonId", "distributedLessonId"):
        if type(fixtures[key]) is not str or not fixtures[key].startswith("core-"):
            raise BrowserMatrixError(f"matrix.fixtures.{key} must be a full lesson ID")

    measurement_keys = frozenset({"warmups", "samples", "resetCycles", "desktopMedianMs", "desktopLongTaskMs", "desktopRunsWithoutLongTask", "mobileMedianMs", "mobileP95Ms", "maxHeapGrowthBytes", "maxHeapGrowthRatio"})
    measurements = _object(root["measurements"], measurement_keys, "matrix.measurements")
    exact_ints = {
        "warmups": 3, "samples": 20, "resetCycles": 100,
        "desktopMedianMs": 25, "desktopLongTaskMs": 50,
        "desktopRunsWithoutLongTask": 19, "mobileMedianMs": 50,
        "mobileP95Ms": 100, "maxHeapGrowthBytes": 1048576,
    }
    for name, expected in exact_ints.items():
        if measurements[name] != expected or type(measurements[name]) is not int:
            raise BrowserMatrixError(f"matrix.measurements.{name} drifted")
    if _number(measurements["maxHeapGrowthRatio"], "matrix.measurements.maxHeapGrowthRatio", 0.05, 0.05) != 0.05:
        raise BrowserMatrixError("matrix.measurements.maxHeapGrowthRatio drifted")

    return BrowserMatrix(
        1, harness_version, image, digest,
        MappingProxyType(platforms), MappingProxyType(profiles),
        MappingProxyType(fixtures), MappingProxyType(measurements),
        hashlib.sha256(raw).hexdigest(),
    )


def load_browser_matrix(path: Path) -> BrowserMatrix:
    try:
        stat_before = path.stat(follow_symlinks=False)
        if not path.is_file() or path.is_symlink() or stat_before.st_size > MATRIX_MAX_BYTES:
            raise BrowserMatrixError("browser matrix must be a bounded regular file")
        raw = path.read_bytes()
        stat_after = path.stat(follow_symlinks=False)
    except OSError as error:
        raise BrowserMatrixError("browser matrix could not be read safely") from error
    if (stat_before.st_dev, stat_before.st_ino, stat_before.st_size, stat_before.st_mtime_ns) != (stat_after.st_dev, stat_after.st_ino, stat_after.st_size, stat_after.st_mtime_ns):
        raise BrowserMatrixError("browser matrix changed while being read")
    return load_browser_matrix_bytes(raw)


def detect_host_platform() -> str:
    machine = platform.machine().lower()
    if sys.platform.startswith("linux") and machine in {"x86_64", "amd64"}:
        return "linux-x86_64"
    if sys.platform == "darwin" and machine == "arm64":
        return "macos-arm64"
    raise BrowserMatrixError("unsupported host operating system or architecture")


def resolve_platform(matrix: BrowserMatrix, override: str | None) -> PlatformEntry:
    host = detect_host_platform()
    if override is not None and override != host:
        raise BrowserMatrixError("platform override does not match the host")
    key = override or host
    try:
        return matrix.platforms[key]
    except KeyError as error:
        raise BrowserMatrixError("host platform is absent from the matrix") from error


def _download_https(url: str, timeout: float, byte_limit: int) -> bytes:
    request = Request(url, headers={"User-Agent": "engineering-expert-curriculum-browser-contract/1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            final = urlsplit(response.geturl())
            if final.scheme != "https":
                raise BrowserMatrixError("browser download redirected away from HTTPS")
            declared = response.headers.get("Content-Length")
            if declared is not None and (not declared.isascii() or not declared.isdecimal() or int(declared) > byte_limit):
                raise BrowserMatrixError("browser download exceeds its byte ceiling")
            payload = response.read(byte_limit + 1)
    except BrowserMatrixError:
        raise
    except OSError as error:
        raise BrowserMatrixError("browser download failed") from error
    if len(payload) > byte_limit:
        raise BrowserMatrixError("browser download exceeds its byte ceiling")
    return payload


def _member_path(root: Path, name: str) -> Path:
    if not name or "\\" in name:
        raise BrowserMatrixError("browser archive contains an unsafe member path")
    pure = PurePosixPath(name)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise BrowserMatrixError("browser archive contains an absolute or parent path")
    target = root.joinpath(*pure.parts)
    try:
        target.resolve(strict=False).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise BrowserMatrixError("browser archive member escapes extraction root") from error
    return target


def _extract_zip(
    payload: bytes,
    root: Path,
    expanded_limit: int,
    expected_symlinks: tuple[tuple[str, str], ...],
) -> None:
    total = 0
    actual_symlinks: dict[str, str] = {}
    seen: set[str] = set()
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for info in archive.infolist():
                name = info.filename.rstrip("/")
                if name in seen:
                    raise BrowserMatrixError("browser archive contains a duplicate member")
                seen.add(name)
                target = _member_path(root, name)
                mode = info.external_attr >> 16
                if info.flag_bits & 0x1:
                    raise BrowserMatrixError("encrypted browser archive members are forbidden")
                if stat.S_ISLNK(mode):
                    try:
                        link_value = archive.read(info).decode("utf-8", errors="strict")
                    except (UnicodeDecodeError, RuntimeError) as error:
                        raise BrowserMatrixError("browser archive link target is invalid") from error
                    actual_symlinks[name] = _link_target(link_value, "archive symlink")
                    continue
                total += info.file_size
                if total > expanded_limit:
                    raise BrowserMatrixError("browser archive exceeds its expanded byte ceiling")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("xb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
                permissions = mode & 0o777
                target.chmod(permissions or 0o644)
        if tuple(sorted(actual_symlinks.items())) != expected_symlinks:
            raise BrowserMatrixError("browser archive symlink map does not match the matrix")
        pending = dict(actual_symlinks)
        while pending:
            progressed = False
            for name, link_value in tuple(pending.items()):
                link = _member_path(root, name)
                candidate = link.parent / link_value
                try:
                    resolved = candidate.resolve(strict=True)
                    resolved.relative_to(root.resolve(strict=True))
                except (OSError, ValueError):
                    continue
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(link_value)
                del pending[name]
                progressed = True
            if not progressed:
                raise BrowserMatrixError("browser archive symlink map is cyclic or dangling")
    except BrowserMatrixError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise BrowserMatrixError("browser ZIP could not be extracted safely") from error


def _extract_tar(payload: bytes, root: Path, expanded_limit: int) -> None:
    total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:xz") as archive:
            for info in archive:
                target = _member_path(root, info.name.rstrip("/"))
                if info.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not info.isfile():
                    raise BrowserMatrixError("browser archive links and special entries are forbidden")
                total += info.size
                if total > expanded_limit:
                    raise BrowserMatrixError("browser archive exceeds its expanded byte ceiling")
                source = archive.extractfile(info)
                if source is None:
                    raise BrowserMatrixError("browser archive file body is unavailable")
                target.parent.mkdir(parents=True, exist_ok=True)
                with source, target.open("xb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
    except BrowserMatrixError:
        raise
    except (OSError, tarfile.TarError) as error:
        raise BrowserMatrixError("browser tar archive could not be extracted safely") from error


def _tree_symlinks(root: Path) -> tuple[tuple[str, str], ...]:
    links: list[tuple[str, str]] = []
    for current, directories, files in os.walk(root, followlinks=False):
        for name in (*directories, *files):
            path = Path(current) / name
            if path.is_symlink():
                relative = path.relative_to(root).as_posix()
                links.append((relative, _link_target(os.readlink(path), "mounted symlink")))
    return tuple(sorted(links))


def _extract_dmg(
    payload_path: Path,
    root: Path,
    executable: str,
    expected_symlinks: tuple[tuple[str, str], ...],
) -> None:
    if sys.platform != "darwin":
        raise BrowserMatrixError("DMG extraction is available only on macOS")
    mount = Path(tempfile.mkdtemp(prefix=".browser-dmg-mount-"))
    attached = False
    try:
        subprocess.run(
            ["/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(payload_path)],
            check=True, capture_output=True, text=True, timeout=60,
        )
        attached = True
        top = PurePosixPath(executable).parts[0]
        source = mount / top
        if not source.is_dir() or source.is_symlink():
            raise BrowserMatrixError("DMG does not contain the pinned application")
        if _tree_symlinks(source) != tuple(
            (PurePosixPath(path).relative_to(top).as_posix(), target)
            for path, target in expected_symlinks
        ):
            raise BrowserMatrixError("mounted browser symlink map does not match the matrix")
        subprocess.run(
            ["/usr/bin/ditto", str(source), str(root / top)], check=True,
            capture_output=True, text=True, timeout=120,
        )
        if _tree_symlinks(root / top) != _tree_symlinks(source):
            raise BrowserMatrixError("copied browser symlink map drifted")
    except BrowserMatrixError:
        raise
    except (OSError, subprocess.SubprocessError) as error:
        raise BrowserMatrixError("browser DMG could not be mounted safely") from error
    finally:
        if attached:
            try:
                subprocess.run(
                    ["/usr/bin/hdiutil", "detach", str(mount)], check=True,
                    capture_output=True, text=True, timeout=30,
                )
            except (OSError, subprocess.SubprocessError) as error:
                raise BrowserMatrixError("browser DMG could not be detached") from error
        try:
            mount.rmdir()
        except OSError as error:
            raise BrowserMatrixError("browser DMG mount directory could not be removed") from error


def verify_macos_browser_bundle(
    executable: Path,
    *,
    expected_version: str,
    signature_policy: str,
    executable_sha256: str | None,
) -> None:
    bundle = next((parent for parent in executable.parents if parent.suffix == ".app"), None)
    if bundle is None:
        raise BrowserMatrixError("macOS browser executable is not inside an application bundle")
    try:
        if signature_policy == "developer-id":
            if executable_sha256 is not None:
                raise BrowserMatrixError("Developer ID policy must not carry the CfT executable digest")
            subprocess.run(
                ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(bundle)],
                check=True, capture_output=True, text=True, timeout=60,
            )
            subprocess.run(
                ["/usr/sbin/spctl", "--assess", "--type", "execute", str(bundle)],
                check=True, capture_output=True, text=True, timeout=60,
            )
        elif signature_policy == "adhoc-cft":
            if executable_sha256 is None or hashlib.sha256(executable.read_bytes()).hexdigest() != executable_sha256:
                raise BrowserMatrixError("CfT executable SHA-256 does not match the matrix")
            metadata = subprocess.run(
                ["/usr/bin/codesign", "-dvvv", str(bundle)], check=False,
                capture_output=True, text=True, timeout=30,
            )
            metadata_text = metadata.stdout + metadata.stderr
            required_metadata = ("Signature=adhoc", "TeamIdentifier=not set", "Sealed Resources=none")
            if metadata.returncode != 0 or any(item not in metadata_text for item in required_metadata):
                raise BrowserMatrixError("CfT ad-hoc signature metadata drifted")
            expected_failure = "code has no resources but signature indicates they must be present"
            strict = subprocess.run(
                ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(bundle)],
                check=False, capture_output=True, text=True, timeout=60,
            )
            gatekeeper = subprocess.run(
                ["/usr/sbin/spctl", "--assess", "--type", "execute", str(bundle)],
                check=False, capture_output=True, text=True, timeout=60,
            )
            if strict.returncode == 0 or gatekeeper.returncode == 0:
                raise BrowserMatrixError("CfT unexpectedly changed to a different signature policy")
            if expected_failure not in strict.stderr or expected_failure not in gatekeeper.stderr:
                raise BrowserMatrixError("CfT expected signature limitation drifted")
        else:
            raise BrowserMatrixError("unknown macOS browser signature policy")
        architectures = subprocess.run(
            ["/usr/bin/lipo", "-archs", str(executable)], check=True,
            capture_output=True, text=True, timeout=15,
        ).stdout.split()
        version_output = subprocess.run(
            [str(executable), "--version"], check=True,
            capture_output=True, text=True, timeout=15,
        ).stdout.strip()
    except BrowserMatrixError:
        raise
    except (OSError, subprocess.SubprocessError) as error:
        raise BrowserMatrixError("macOS browser signature or executable preflight failed") from error
    if "arm64" not in architectures:
        raise BrowserMatrixError("macOS browser executable does not contain arm64")
    pattern = rf"(?<![0-9.]){re.escape(expected_version)}(?![0-9.])"
    if re.search(pattern, version_output) is None:
        raise BrowserMatrixError("macOS browser executable version does not match the matrix")


def verify_linux_browser_binary(
    executable: Path, *, browser_name: str, expected_version: str,
) -> None:
    if browser_name not in {"chromium", "firefox"}:
        raise BrowserMatrixError("Linux browser name is outside the closed set")
    try:
        header = executable.read_bytes()[:64]
        if (
            len(header) < 20 or header[:4] != b"\x7fELF"
            or header[4] != 2 or header[5] != 1
            or int.from_bytes(header[18:20], "little") != 62
        ):
            raise BrowserMatrixError("Linux browser executable is not x86-64 ELF")
        dependencies = subprocess.run(
            ["/usr/bin/ldd", str(executable)], check=False,
            capture_output=True, text=True, timeout=30,
        )
        if dependencies.returncode != 0 or "not found" in dependencies.stdout + dependencies.stderr:
            raise BrowserMatrixError("Linux browser dependencies are unavailable")
        version = subprocess.run(
            [str(executable), "--version"], check=False,
            capture_output=True, text=True, timeout=20,
        )
        pattern = rf"(?<![0-9.]){re.escape(expected_version)}(?![0-9.])"
        if version.returncode != 0 or re.search(pattern, version.stdout + version.stderr) is None:
            raise BrowserMatrixError("Linux browser version does not match the matrix")
        if browser_name == "chromium":
            launch = subprocess.run(
                [
                    str(executable), "--headless=new", "--disable-gpu",
                    "--no-first-run", "--dump-dom", "data:text/html,<title>browser-contract</title>",
                ], check=False, capture_output=True, text=True, timeout=30,
            )
            if launch.returncode != 0 or "<title>browser-contract</title>" not in launch.stdout:
                raise BrowserMatrixError("Linux Chromium real launch preflight failed")
        else:
            with tempfile.TemporaryDirectory(prefix=".firefox-launch-") as temporary:
                screenshot = Path(temporary) / "launch.png"
                launch = subprocess.run(
                    [
                        str(executable), "--headless", "--screenshot", str(screenshot),
                        "data:text/html,<title>browser-contract</title>",
                    ], check=False, capture_output=True, text=True, timeout=30,
                )
                if launch.returncode != 0 or not screenshot.is_file() or screenshot.stat().st_size == 0:
                    raise BrowserMatrixError("Linux Firefox real launch preflight failed")
    except BrowserMatrixError:
        raise
    except (OSError, subprocess.SubprocessError) as error:
        raise BrowserMatrixError("Linux browser executable preflight failed") from error


def _validate_cached_tree(
    destination: Path, expected_symlinks: tuple[tuple[str, str], ...],
) -> None:
    if destination.is_symlink() or not destination.is_dir():
        raise BrowserMatrixError("existing browser cache tree is not a real directory")
    if _tree_symlinks(destination) != expected_symlinks:
        raise BrowserMatrixError("existing browser cache symlink map drifted")
    root = destination.resolve(strict=True)
    for relative, _target in expected_symlinks:
        link = destination.joinpath(*PurePosixPath(relative).parts)
        try:
            resolved = link.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, RuntimeError, ValueError) as error:
            raise BrowserMatrixError("existing browser cache symlink escapes its tree") from error


def _same_file_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev, left.st_ino, left.st_mode, left.st_nlink,
        left.st_size, left.st_mtime_ns,
    ) == (
        right.st_dev, right.st_ino, right.st_mode, right.st_nlink,
        right.st_size, right.st_mtime_ns,
    )


def _read_cached_archive(
    cache_root: Path, digest: str, max_bytes: int,
) -> bytes | None:
    """Read a cache hit through pinned directory descriptors.

    Both directory bindings and the archive identity are checked after the
    bounded read because pathname validation before open is vulnerable to a
    concurrent rename or special-file substitution.
    """
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    cache_fd = digest_fd = archive_fd = -1
    try:
        cache_before = os.stat(cache_root, follow_symlinks=False)
        cache_fd = os.open(cache_root, directory_flags)
        cache_opened = os.fstat(cache_fd)
        if not stat.S_ISDIR(cache_opened.st_mode) or not _same_file_identity(cache_before, cache_opened):
            raise BrowserMatrixError("browser cache parent binding changed")
        digest_fd = os.open(digest, directory_flags, dir_fd=cache_fd)
        digest_opened = os.fstat(digest_fd)
        if not stat.S_ISDIR(digest_opened.st_mode):
            raise BrowserMatrixError("browser digest cache is not a real directory")
        try:
            archive_fd = os.open(
                "archive", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=digest_fd,
            )
        except FileNotFoundError:
            return None
        archive_before = os.fstat(archive_fd)
        if not stat.S_ISREG(archive_before.st_mode) or archive_before.st_nlink != 1:
            raise BrowserMatrixError("cached browser archive is not a single-link regular file")
        if archive_before.st_size > max_bytes:
            raise BrowserMatrixError("cached browser archive exceeds its byte ceiling")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(archive_fd, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > max_bytes:
            raise BrowserMatrixError("cached browser archive exceeds its byte ceiling")
        archive_after = os.fstat(archive_fd)
        digest_after = os.stat(digest, dir_fd=cache_fd, follow_symlinks=False)
        cache_after = os.stat(cache_root, follow_symlinks=False)
        if (
            not _same_file_identity(archive_before, archive_after)
            or not _same_file_identity(digest_opened, digest_after)
            or not _same_file_identity(cache_opened, cache_after)
        ):
            raise BrowserMatrixError("cached browser archive or parent binding changed while reading")
        return payload
    except BrowserMatrixError:
        raise
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise BrowserMatrixError("cached browser archive link substitution was rejected") from error
        raise BrowserMatrixError("cached browser archive could not be read safely") from error
    finally:
        for descriptor in (archive_fd, digest_fd, cache_fd):
            if descriptor >= 0:
                os.close(descriptor)


@contextmanager
def _verified_payload_file(payload: bytes, max_bytes: int) -> Iterator[Path]:
    """Publish verified bytes only inside an installer-owned private directory."""
    if type(payload) is not bytes or len(payload) > max_bytes:
        raise BrowserMatrixError("verified browser payload exceeds its byte ceiling")
    staging_root = Path(tempfile.mkdtemp(prefix="browser-payload-"))
    parent_fd = root_fd = payload_fd = -1
    cleanup_error: BrowserMatrixError | None = None
    try:
        parent = staging_root.parent
        basename = staging_root.name
        parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        root_before = os.stat(basename, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(root_before.st_mode) or stat.S_IMODE(root_before.st_mode) != 0o700:
            raise BrowserMatrixError("browser payload staging root is not private")
        root_fd = os.open(
            basename, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
        root_opened = os.fstat(root_fd)
        if not _same_file_identity(root_before, root_opened):
            raise BrowserMatrixError("browser payload staging root binding changed")
        payload_fd = os.open(
            "archive",
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o400, dir_fd=root_fd,
        )
        offset = 0
        while offset < len(payload):
            written = os.write(payload_fd, payload[offset:offset + 1024 * 1024])
            if written <= 0:
                raise BrowserMatrixError("browser payload staging write made no progress")
            offset += written
        os.fsync(payload_fd)
        os.fchmod(payload_fd, 0o400)
        root_bound = os.fstat(root_fd)
        payload_before = os.fstat(payload_fd)
        if (
            not stat.S_ISREG(payload_before.st_mode)
            or payload_before.st_nlink != 1
            or payload_before.st_size != len(payload)
            or os.listdir(root_fd) != ["archive"]
        ):
            raise BrowserMatrixError("browser payload staging identity is invalid")
        yield staging_root / "archive"
        payload_after = os.fstat(payload_fd)
        path_after = os.stat("archive", dir_fd=root_fd, follow_symlinks=False)
        root_after = os.stat(basename, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not _same_file_identity(payload_before, payload_after)
            or not _same_file_identity(payload_before, path_after)
            or not _same_file_identity(root_bound, root_after)
            or os.listdir(root_fd) != ["archive"]
        ):
            raise BrowserMatrixError("browser payload staging changed during extraction")
        os.lseek(payload_fd, 0, os.SEEK_SET)
        observed = bytearray()
        while len(observed) <= max_bytes:
            chunk = os.read(payload_fd, min(1024 * 1024, max_bytes + 1 - len(observed)))
            if not chunk:
                break
            observed.extend(chunk)
        if bytes(observed) != payload:
            raise BrowserMatrixError("browser payload staging bytes changed during extraction")
    except BrowserMatrixError:
        raise
    except OSError as error:
        raise BrowserMatrixError("browser payload could not be staged safely") from error
    finally:
        primary_error_active = sys.exc_info()[0] is not None
        def remember_cleanup_error(message: str, error: OSError) -> None:
            nonlocal cleanup_error
            if cleanup_error is None:
                cleanup_error = BrowserMatrixError(message)
                cleanup_error.__cause__ = error

        if payload_fd >= 0:
            try:
                os.close(payload_fd)
            except OSError as error:
                remember_cleanup_error(
                    "browser payload descriptor cleanup failed", error,
                )
        if root_fd >= 0:
            try:
                os.unlink("archive", dir_fd=root_fd)
            except FileNotFoundError:
                pass
            except OSError as error:
                remember_cleanup_error(
                    "browser payload archive cleanup failed", error,
                )
        if parent_fd >= 0 and root_fd >= 0:
            try:
                current = os.stat(basename, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                current = None
            except OSError as error:
                current = None
                remember_cleanup_error(
                    "browser payload root binding cleanup failed", error,
                )
            try:
                opened = os.fstat(root_fd)
            except OSError as error:
                opened = None
                remember_cleanup_error(
                    "browser payload root descriptor cleanup failed", error,
                )
            if current is not None and opened is not None and (
                current.st_dev, current.st_ino
            ) == (opened.st_dev, opened.st_ino):
                try:
                    os.rmdir(basename, dir_fd=parent_fd)
                except OSError as error:
                    remember_cleanup_error(
                        "browser payload staging directory cleanup failed", error,
                    )
        if root_fd >= 0:
            try:
                os.close(root_fd)
            except OSError as error:
                remember_cleanup_error(
                    "browser payload root descriptor close failed", error,
                )
        if parent_fd >= 0:
            try:
                os.close(parent_fd)
            except OSError as error:
                remember_cleanup_error(
                    "browser payload parent descriptor close failed", error,
                )
        if cleanup_error is not None and not primary_error_active:
            raise cleanup_error


def _tree_inventory(root: Path) -> tuple[tuple[str, str, int | str], ...]:
    inventory: list[tuple[str, str, int | str]] = []
    for current, directories, files in os.walk(root, followlinks=False):
        for name in (*directories, *files):
            path = Path(current) / name
            relative = path.relative_to(root).as_posix()
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                inventory.append((relative, "link", os.readlink(path)))
            elif stat.S_ISDIR(metadata.st_mode):
                inventory.append((relative, "directory", 0))
            elif stat.S_ISREG(metadata.st_mode):
                inventory.append((relative, "file", metadata.st_size))
            else:
                raise BrowserMatrixError("browser extraction inventory contains a special file")
    return tuple(sorted(inventory))


def install_archive(
    archive: BrowserArchive,
    cache: Path,
    *,
    downloader: Callable[[str, float, int], bytes] = _download_https,
    browser_name: str | None = None,
) -> Path:
    try:
        cache.mkdir(parents=True, exist_ok=True)
        if cache.is_symlink() or not cache.is_dir():
            raise BrowserMatrixError("browser cache must be a real directory")
        cache_root = cache.resolve(strict=True)
        digest_root = cache_root / archive.sha256
        digest_root.mkdir(mode=0o700, exist_ok=True)
        if digest_root.is_symlink() or not digest_root.is_dir():
            raise BrowserMatrixError("browser digest cache must be a real directory")
        destination = digest_root / "extracted"
        executable = destination.joinpath(*PurePosixPath(archive.executable).parts)
        if destination.exists() or destination.is_symlink():
            _validate_cached_tree(destination, archive.symlinks)
        cached_archive = digest_root / "archive"
        payload = _read_cached_archive(cache_root, archive.sha256, archive.max_bytes)
        archive_was_cached = payload is not None
        if payload is None:
            payload = downloader(archive.url, 30.0, archive.max_bytes)
            if type(payload) is not bytes or len(payload) > archive.max_bytes:
                raise BrowserMatrixError("browser downloader violated its byte ceiling")
        if hashlib.sha256(payload).hexdigest() != archive.sha256:
            raise BrowserMatrixError("browser archive SHA-256 mismatch")
        if not archive_was_cached:
            pending_archive = digest_root / ".archive.pending"
            with pending_archive.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(pending_archive, cached_archive)
        temporary = Path(tempfile.mkdtemp(prefix=".extract-", dir=digest_root))
        try:
            expanded_limit = min(2 * 1024 * 1024 * 1024, archive.max_bytes * 8)
            needs_macos_payload = archive.archive_format == "dmg" or (
                archive.archive_format == "zip" and sys.platform == "darwin"
                and any(part.endswith(".app") for part in PurePosixPath(archive.executable).parts)
            )
            payload_context = (
                _verified_payload_file(payload, archive.max_bytes)
                if needs_macos_payload else nullcontext(None)
            )
            with payload_context as immutable_payload:
                if archive.archive_format == "zip":
                    _extract_zip(payload, temporary, expanded_limit, archive.symlinks)
                    if needs_macos_payload:
                        # Validate the byte-level archive first, then require
                        # ditto's Apple-metadata-preserving output to have the
                        # exact same path/type/size inventory.
                        validated_inventory = _tree_inventory(temporary)
                        shutil.rmtree(temporary)
                        temporary.mkdir(mode=0o700)
                        subprocess.run(
                            ["/usr/bin/ditto", "-x", "-k", str(immutable_payload), str(temporary)],
                            check=True, capture_output=True, text=True, timeout=120,
                        )
                        if _tree_inventory(temporary) != validated_inventory:
                            raise BrowserMatrixError("ditto extraction inventory drifted")
                elif archive.archive_format == "tar.xz":
                    _extract_tar(payload, temporary, expanded_limit)
                elif archive.archive_format == "dmg":
                    if immutable_payload is None:
                        raise BrowserMatrixError("DMG verified staging payload is unavailable")
                    _extract_dmg(
                        immutable_payload, temporary,
                        archive.executable, archive.symlinks,
                    )
                else:
                    raise BrowserMatrixError("browser archive format is unsupported")
            candidate = temporary.joinpath(*PurePosixPath(archive.executable).parts)
            if not candidate.is_file() or candidate.is_symlink():
                raise BrowserMatrixError("pinned browser executable is absent after extraction")
            candidate.chmod(candidate.stat().st_mode | stat.S_IXUSR)
            if sys.platform == "darwin" and any(part.endswith(".app") for part in PurePosixPath(archive.executable).parts):
                verify_macos_browser_bundle(
                    candidate,
                    expected_version=archive.version,
                    signature_policy=archive.signature_policy,
                    executable_sha256=archive.executable_sha256,
                )
            elif sys.platform.startswith("linux"):
                if browser_name is None:
                    raise BrowserMatrixError("Linux browser preflight requires its closed browser name")
                verify_linux_browser_binary(
                    candidate, browser_name=browser_name,
                    expected_version=archive.version,
                )
            previous = digest_root / ".extracted.previous"
            if previous.exists() or previous.is_symlink():
                raise BrowserMatrixError("browser cache contains stale publication state")
            if destination.exists():
                os.replace(destination, previous)
            try:
                os.replace(temporary, destination)
            except BaseException:
                if previous.exists() and not destination.exists():
                    os.replace(previous, destination)
                raise
            if previous.exists():
                shutil.rmtree(previous)
            return executable
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    except BrowserMatrixError:
        raise
    except OSError as error:
        raise BrowserMatrixError("browser archive installation failed") from error


def verify_safari_version(*, executable: Path, expected_version: str, expected_build: str) -> None:
    if executable != Path("/Applications/Safari.app/Contents/MacOS/Safari"):
        raise BrowserMatrixError("Safari executable path does not match the release contract")
    info = executable.parents[1] / "Info"
    try:
        version = subprocess.run(
            ["/usr/bin/defaults", "read", str(info), "CFBundleShortVersionString"],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        build = subprocess.run(
            ["/usr/bin/defaults", "read", str(info), "CFBundleVersion"],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise BrowserMatrixError("installed Safari version could not be verified") from error
    if version != expected_version or build != expected_build:
        raise BrowserMatrixError("installed Safari version or build does not match the matrix")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--platform")
    args = parser.parse_args(argv)
    matrix = load_browser_matrix(args.matrix)
    entry = resolve_platform(matrix, args.platform)
    for name in ("chromium", "firefox"):
        executable = install_archive(
            entry.browsers[name], args.cache, browser_name=name
        )
        print(f"{name}: {executable}")
    if entry.safari is not None:
        verify_safari_version(
            executable=Path(entry.safari.executable),
            expected_version=entry.safari.version,
            expected_build=entry.safari.build,
        )
        print(f"safari: {entry.safari.executable}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrowserMatrixError as error:
        print(f"browser install failed: {error}", file=sys.stderr)
        raise SystemExit(1)
