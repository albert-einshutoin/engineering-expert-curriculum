from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import re
import unittest
from typing import TypeAlias


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_ROOT = REPOSITORY_ROOT / ".github" / "workflows"

YamlScalar: TypeAlias = str | int | bool | None
YamlValue: TypeAlias = YamlScalar | list["YamlValue"] | dict[str, "YamlValue"]

_ACTION_LEDGER = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",
    "actions/dependency-review-action": (
        "a1d282b36b6f3519aa1f3fc636f609c47dddb294"
    ),
    "actions/upload-pages-artifact": (
        "fc324d3547104276b827a68afc52ff2a11cc49c9"
    ),
    "actions/deploy-pages": "cd2ce8fcbc39b97be8ca5fce6e763baed58fa128",
    "github/codeql-action/init": (
        "f205ea1c3313d32999d8d6a48b4f6530d4437b38"
    ),
    "github/codeql-action/analyze": (
        "f205ea1c3313d32999d8d6a48b4f6530d4437b38"
    ),
}
_ACTION_REFERENCE = re.compile(
    r"(?P<action>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
    r"(?:/[A-Za-z0-9_.-]+)*)@(?P<revision>[0-9a-f]{40})\Z",
    re.ASCII,
)
_ALLOWED_PERMISSION_VALUES = frozenset({"read", "write", "none"})
_ALLOWED_PERMISSION_KEYS = frozenset(
    {"contents", "security-events", "pages", "id-token"}
)


class ConstrainedYamlError(ValueError):
    """The repository YAML left the intentionally small supported subset."""


@dataclass(frozen=True, slots=True)
class _Line:
    number: int
    indent: int
    text: str


class _ConstrainedYamlParser:
    """Parse the auditable YAML subset used by repository metadata.

    CI security tests must not silently downgrade to regular expressions when a
    workflow changes shape. This parser accepts mappings, sequences, quoted and
    plain scalars, inline scalar lists, and literal/folded blocks. Unsupported
    YAML features fail closed instead of being guessed at.
    """

    def __init__(self, source: str, *, origin: Path) -> None:
        self.origin = origin
        self.lines = self._tokenize(source)

    def _tokenize(self, source: str) -> list[_Line]:
        raw_lines = source.splitlines()
        lines: list[_Line] = []
        index = 0
        while index < len(raw_lines):
            raw = raw_lines[index]
            number = index + 1
            if "\t" in raw[: len(raw) - len(raw.lstrip(" \t"))]:
                self._fail(number, "tab indentation is unsupported")
            stripped = raw.lstrip(" ")
            if not stripped or stripped.startswith("#"):
                index += 1
                continue
            indent = len(raw) - len(stripped)
            if indent % 2:
                self._fail(number, "indentation must use two-space levels")
            if stripped.startswith(("---", "...", "&", "*", "!")):
                self._fail(number, "advanced YAML features are unsupported")
            lines.append(_Line(number, indent, stripped))
            index += 1
        return lines

    def _fail(self, number: int, message: str) -> None:
        raise ConstrainedYamlError(f"{self.origin}:{number}: {message}")

    def parse(self) -> dict[str, YamlValue]:
        if not self.lines:
            raise ConstrainedYamlError(f"{self.origin}: YAML must not be empty")
        if self.lines[0].indent != 0:
            self._fail(self.lines[0].number, "root mapping must start at column 1")
        value, cursor = self._parse_node(0, 0)
        if cursor != len(self.lines):
            self._fail(self.lines[cursor].number, "unconsumed YAML content")
        if not isinstance(value, dict):
            self._fail(self.lines[0].number, "root value must be a mapping")
        return value

    def _parse_node(self, cursor: int, indent: int) -> tuple[YamlValue, int]:
        if self.lines[cursor].text.startswith("- "):
            return self._parse_sequence(cursor, indent)
        return self._parse_mapping(cursor, indent)

    def _parse_mapping(
        self,
        cursor: int,
        indent: int,
    ) -> tuple[dict[str, YamlValue], int]:
        result: dict[str, YamlValue] = {}
        while cursor < len(self.lines):
            line = self.lines[cursor]
            if line.indent < indent:
                break
            if line.indent != indent or line.text.startswith("- "):
                self._fail(line.number, "unexpected mapping indentation")
            key, separator, raw_value = line.text.partition(":")
            if not separator or not self._valid_key(key):
                self._fail(line.number, "mapping key is invalid")
            if key in result:
                self._fail(line.number, f"duplicate mapping key {key!r}")
            cursor += 1
            if raw_value.strip() in {"|", ">", "|-", ">-"}:
                value, cursor = self._parse_block(cursor, indent, line.number)
            elif raw_value.strip():
                value = self._parse_scalar(raw_value.strip(), line.number)
            elif cursor < len(self.lines) and self.lines[cursor].indent > indent:
                value, cursor = self._parse_node(
                    cursor,
                    self.lines[cursor].indent,
                )
            else:
                value = {}
            result[key] = value
        return result, cursor

    def _parse_sequence(
        self,
        cursor: int,
        indent: int,
    ) -> tuple[list[YamlValue], int]:
        result: list[YamlValue] = []
        while cursor < len(self.lines):
            line = self.lines[cursor]
            if line.indent < indent:
                break
            if line.indent != indent or not line.text.startswith("- "):
                self._fail(line.number, "unexpected sequence indentation")
            item_text = line.text[2:].strip()
            cursor += 1
            if not item_text:
                if cursor >= len(self.lines) or self.lines[cursor].indent <= indent:
                    self._fail(line.number, "empty sequence item")
                value, cursor = self._parse_node(
                    cursor,
                    self.lines[cursor].indent,
                )
                result.append(value)
                continue
            key, separator, raw_value = item_text.partition(":")
            if separator and self._valid_key(key):
                item: dict[str, YamlValue] = {}
                if raw_value.strip() in {"|", ">", "|-", ">-"}:
                    value, cursor = self._parse_block(cursor, indent, line.number)
                elif raw_value.strip():
                    value = self._parse_scalar(raw_value.strip(), line.number)
                elif cursor < len(self.lines) and self.lines[cursor].indent > indent:
                    value, cursor = self._parse_node(
                        cursor,
                        self.lines[cursor].indent,
                    )
                else:
                    value = {}
                item[key] = value
                if cursor < len(self.lines) and self.lines[cursor].indent > indent:
                    continuation_indent = self.lines[cursor].indent
                    continuation, cursor = self._parse_mapping(
                        cursor,
                        continuation_indent,
                    )
                    duplicate = set(item) & set(continuation)
                    if duplicate:
                        self._fail(line.number, "duplicate sequence mapping key")
                    item.update(continuation)
                result.append(item)
            else:
                result.append(self._parse_scalar(item_text, line.number))
                if cursor < len(self.lines) and self.lines[cursor].indent > indent:
                    self._fail(
                        self.lines[cursor].number,
                        "scalar sequence item cannot have children",
                    )
        return result, cursor

    def _parse_block(
        self,
        cursor: int,
        parent_indent: int,
        parent_line: int,
    ) -> tuple[str, int]:
        if cursor >= len(self.lines) or self.lines[cursor].indent <= parent_indent:
            self._fail(parent_line, "block scalar must not be empty")
        block_indent = self.lines[cursor].indent
        parts: list[str] = []
        while cursor < len(self.lines) and self.lines[cursor].indent > parent_indent:
            line = self.lines[cursor]
            padding = " " * max(0, line.indent - block_indent)
            parts.append(padding + line.text)
            cursor += 1
        return "\n".join(parts) + "\n", cursor

    def _parse_scalar(self, raw: str, number: int) -> YamlValue:
        if raw.startswith(("{", "[")):
            try:
                value = ast.literal_eval(raw)
            except (SyntaxError, ValueError):
                self._fail(number, "inline collection must contain literals")
            if not self._is_scalar_collection(value):
                self._fail(number, "inline collection contains unsupported values")
            return value
        if raw.startswith(('"', "'")):
            try:
                value = ast.literal_eval(raw)
            except (SyntaxError, ValueError):
                self._fail(number, "quoted scalar is invalid")
            if not isinstance(value, str):
                self._fail(number, "quoted value must be a string")
            return value
        if raw in {"true", "false"}:
            return raw == "true"
        if raw in {"null", "~"}:
            return None
        if re.fullmatch(r"0|[1-9][0-9]*", raw, re.ASCII):
            return int(raw)
        if raw.startswith(("&", "*", "!")) or " #" in raw:
            self._fail(number, "aliases, tags, and inline comments are unsupported")
        return raw

    @staticmethod
    def _valid_key(key: str) -> bool:
        return re.fullmatch(r"[A-Za-z0-9_.-]+", key, re.ASCII) is not None

    @classmethod
    def _is_scalar_collection(cls, value: object) -> bool:
        if isinstance(value, (str, int, bool)) or value is None:
            return True
        if isinstance(value, list):
            return all(cls._is_scalar_collection(item) for item in value)
        if isinstance(value, dict):
            return all(
                isinstance(key, str) and cls._is_scalar_collection(item)
                for key, item in value.items()
            )
        return False


def _yaml_files() -> tuple[Path, ...]:
    paths = {
        *REPOSITORY_ROOT.rglob("*.yml"),
        *REPOSITORY_ROOT.rglob("*.yaml"),
    }
    return tuple(sorted(path for path in paths if ".git" not in path.parts))


def _load_yaml(path: Path) -> dict[str, YamlValue]:
    return _ConstrainedYamlParser(
        path.read_text(encoding="utf-8"),
        origin=path.relative_to(REPOSITORY_ROOT),
    ).parse()


def _workflow(name: str) -> dict[str, YamlValue]:
    path = WORKFLOWS_ROOT / name
    if not path.is_file():
        raise AssertionError(f"missing required workflow: {path.name}")
    return _load_yaml(path)


def _workflow_files() -> tuple[Path, ...]:
    if not WORKFLOWS_ROOT.is_dir():
        return ()
    return tuple(
        sorted(
            {
                *WORKFLOWS_ROOT.glob("*.yml"),
                *WORKFLOWS_ROOT.glob("*.yaml"),
            }
        )
    )


def _mapping(value: YamlValue, context: str) -> dict[str, YamlValue]:
    if not isinstance(value, dict):
        raise AssertionError(f"{context} must be a mapping")
    return value


def _sequence(value: YamlValue, context: str) -> list[YamlValue]:
    if not isinstance(value, list):
        raise AssertionError(f"{context} must be a sequence")
    return value


def _jobs(document: dict[str, YamlValue]) -> dict[str, YamlValue]:
    return _mapping(document.get("jobs"), "jobs")


def _steps(job: YamlValue, context: str) -> list[dict[str, YamlValue]]:
    mapping = _mapping(job, context)
    return [
        _mapping(step, f"{context}.steps")
        for step in _sequence(mapping.get("steps"), f"{context}.steps")
    ]


def _runs(document: dict[str, YamlValue]) -> tuple[str, ...]:
    return tuple(
        run
        for job_name, job in _jobs(document).items()
        for step in _steps(job, f"jobs.{job_name}")
        if isinstance((run := step.get("run")), str)
    )


class RepositorySecurityTests(unittest.TestCase):
    maxDiff = None

    def test_all_yaml_is_parsed_and_forbids_privileged_pr_triggers(self) -> None:
        paths = _yaml_files()
        self.assertTrue(paths)
        self.assertTrue(any(path.suffix == ".yml" for path in paths))
        for path in paths:
            with self.subTest(path=path.relative_to(REPOSITORY_ROOT)):
                document = _load_yaml(path)
                trigger = document.get("on")
                if isinstance(trigger, dict):
                    self.assertNotIn("pull_request_target", trigger)
                self.assertNotIn("pull_request_target", document)

    def test_workflows_use_only_recognized_immutable_actions(self) -> None:
        expected = {
            "codeql.yml",
            "dependency-review.yml",
            "gitleaks.yml",
            "pages.yml",
            "validate.yml",
        }
        actual = {path.name for path in _workflow_files()}
        self.assertEqual(actual, expected)
        for path in _workflow_files():
            document = _load_yaml(path)
            for job_name, job in _jobs(document).items():
                for step in _steps(job, f"{path.name}.jobs.{job_name}"):
                    reference = step.get("uses")
                    if reference is None:
                        continue
                    self.assertIsInstance(reference, str)
                    match = _ACTION_REFERENCE.fullmatch(str(reference))
                    self.assertIsNotNone(
                        match,
                        f"{path.name}: action must use owner/name@40hex",
                    )
                    assert match is not None
                    action = match.group("action")
                    self.assertIn(action, _ACTION_LEDGER)
                    self.assertEqual(
                        match.group("revision"),
                        _ACTION_LEDGER[action],
                    )

    def test_workflows_default_read_only_and_bound_every_job(self) -> None:
        allowed_overrides = {
            ("codeql.yml", "analysis"): {
                "contents": "read",
                "security-events": "write",
            },
            ("pages.yml", "deploy"): {
                "pages": "write",
                "id-token": "write",
            },
        }
        observed_overrides: dict[tuple[str, str], dict[str, YamlValue]] = {}
        for path in _workflow_files():
            document = _load_yaml(path)
            self.assertEqual(
                _mapping(document.get("permissions"), f"{path.name}.permissions"),
                {"contents": "read"},
            )
            for job_name, value in _jobs(document).items():
                job = _mapping(value, f"{path.name}.jobs.{job_name}")
                self.assertEqual(job.get("runs-on"), "ubuntu-24.04")
                timeout = job.get("timeout-minutes")
                self.assertIs(type(timeout), int)
                self.assertGreater(timeout, 0)
                self.assertLessEqual(timeout, 30)
                permissions = job.get("permissions")
                if permissions is not None:
                    permission_map = _mapping(
                        permissions,
                        f"{path.name}.jobs.{job_name}.permissions",
                    )
                    self.assertTrue(set(permission_map) <= _ALLOWED_PERMISSION_KEYS)
                    self.assertTrue(
                        set(permission_map.values()) <= _ALLOWED_PERMISSION_VALUES
                    )
                    override = (path.name, job_name)
                    self.assertIn(override, allowed_overrides)
                    self.assertEqual(permission_map, allowed_overrides[override])
                    observed_overrides[override] = permission_map
        self.assertEqual(observed_overrides, allowed_overrides)

    def test_checkout_never_persists_credentials(self) -> None:
        checkout = "actions/checkout@" + _ACTION_LEDGER["actions/checkout"]
        for path in _workflow_files():
            document = _load_yaml(path)
            for job_name, job in _jobs(document).items():
                for step in _steps(job, f"{path.name}.jobs.{job_name}"):
                    if step.get("uses") != checkout:
                        continue
                    options = _mapping(
                        step.get("with"),
                        f"{path.name}.jobs.{job_name}.checkout.with",
                    )
                    self.assertIs(options.get("persist-credentials"), False)

    def test_run_blocks_do_not_interpolate_event_data(self) -> None:
        for path in _workflow_files():
            for run in _runs(_load_yaml(path)):
                self.assertNotIn(
                    "${{",
                    run,
                    f"{path.name}: expressions must flow through typed env values",
                )

    def test_validate_runs_the_complete_deterministic_release_gate(self) -> None:
        document = _workflow("validate.yml")
        self.assertEqual(
            document.get("on"),
            {"pull_request": {}, "push": {"branches": ["main"]}},
        )
        self.assertEqual(set(_jobs(document)), {"full-validation"})
        runs = "\n".join(_runs(document))
        self.assertIn("python -m unittest discover -s tests -v", runs)
        self.assertIn("python tools/generate_curriculum_map.py --check", runs)
        self.assertEqual(runs.count("python tools/build.py"), 2)
        self.assertEqual(
            runs.count(
                "python tools/check_site.py --root site --require-current-release"
            ),
            2,
        )
        self.assertIn("sha256sum", runs)
        self.assertIn("diff -u", runs)

    def test_dependency_review_is_pull_request_only_and_read_only(self) -> None:
        document = _workflow("dependency-review.yml")
        self.assertEqual(document.get("on"), {"pull_request": {}})
        self.assertEqual(document.get("permissions"), {"contents": "read"})
        self.assertNotIn("permissions", _mapping(_jobs(document)["review"], "review"))

    def test_codeql_analyzes_python_on_pr_main_and_a_weekly_schedule(self) -> None:
        document = _workflow("codeql.yml")
        trigger = _mapping(document.get("on"), "codeql.on")
        self.assertEqual(set(trigger), {"pull_request", "push", "schedule"})
        self.assertEqual(trigger["push"], {"branches": ["main"]})
        schedule = _sequence(trigger["schedule"], "codeql.on.schedule")
        self.assertEqual(len(schedule), 1)
        cron = _mapping(schedule[0], "codeql.on.schedule[0]").get("cron")
        self.assertRegex(str(cron), r"^[0-9*,-]+ [0-9*,-]+ \* \* [0-6]$")
        jobs = _jobs(document)
        self.assertEqual(set(jobs), {"analysis"})
        analysis = _mapping(jobs["analysis"], "codeql.jobs.analysis")
        self.assertEqual(
            analysis.get("permissions"),
            {"contents": "read", "security-events": "write"},
        )
        steps = _steps(analysis, "codeql.jobs.analysis")
        init = next(
            step
            for step in steps
            if str(step.get("uses", "")).startswith("github/codeql-action/init@")
        )
        self.assertEqual(init.get("with"), {"languages": "python"})

    def test_gitleaks_verifies_official_cli_and_scans_redacted_history(self) -> None:
        document = _workflow("gitleaks.yml")
        jobs = _jobs(document)
        self.assertEqual(set(jobs), {"secret-scan"})
        steps = _steps(jobs["secret-scan"], "gitleaks.jobs.secret-scan")
        checkout = next(
            step
            for step in steps
            if str(step.get("uses", "")).startswith("actions/checkout@")
        )
        self.assertEqual(
            checkout.get("with"),
            {"fetch-depth": 0, "persist-credentials": False},
        )
        runs = "\n".join(_runs(document))
        self.assertIn("gitleaks_8.30.1_linux_x64.tar.gz", runs)
        self.assertIn(
            "551f6fc83ea457d62a0d98237cbad105"
            "af8d557003051f41f3e7ca7b3f2470eb",
            runs,
        )
        self.assertIn("sha256sum --check --strict", runs)
        self.assertIn("gitleaks git", runs)
        self.assertIn("--redact", runs)
        self.assertIn('--log-opts="--all"', runs)
        self.assertNotIn("gitleaks/gitleaks-action", str(document))

    def test_pages_deploys_only_main_after_a_verified_build(self) -> None:
        document = _workflow("pages.yml")
        self.assertEqual(document.get("on"), {"push": {"branches": ["main"]}})
        self.assertNotIn("workflow_dispatch", _mapping(document["on"], "pages.on"))
        jobs = _jobs(document)
        self.assertEqual(set(jobs), {"build", "deploy"})
        build = _mapping(jobs["build"], "pages.jobs.build")
        self.assertNotIn("permissions", build)
        deploy = _mapping(jobs["deploy"], "pages.jobs.deploy")
        self.assertEqual(deploy.get("needs"), "build")
        self.assertEqual(
            deploy.get("permissions"),
            {"pages": "write", "id-token": "write"},
        )
        environment = _mapping(
            deploy.get("environment"),
            "pages.jobs.deploy.environment",
        )
        self.assertEqual(environment.get("name"), "github-pages")
        build_steps = _steps(build, "pages.jobs.build")
        upload_index = next(
            index
            for index, step in enumerate(build_steps)
            if str(step.get("uses", "")).startswith(
                "actions/upload-pages-artifact@"
            )
        )
        checker_index = next(
            index
            for index, step in enumerate(build_steps)
            if "python tools/check_site.py" in str(step.get("run", ""))
        )
        self.assertLess(checker_index, upload_index)
        runs = "\n".join(
            run
            for step in build_steps
            if isinstance((run := step.get("run")), str)
        )
        self.assertEqual(runs.count("python tools/build.py --output"), 2)
        self.assertEqual(
            runs.count("python tools/check_site.py --root "),
            2,
        )
        self.assertIn("sha256sum", runs)
        self.assertIn("diff -u", runs)
        self.assertEqual(
            build_steps[upload_index].get("with"),
            {"path": "site-first"},
        )


if __name__ == "__main__":
    unittest.main()
