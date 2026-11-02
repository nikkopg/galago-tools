"""GAL-07 live runbook tests (LIVE-08): the pre-flight gate script and the runbook text.

TestLiveGate runs docs/runbooks/gal-07-live-check.sh against a fixture HTTP server, fixture
trees and stubbed helpers, so the gate is proven unable to pass falsely (one missing piece at a
time, plus the complete set passing, the read-only proof and the fail-closed degenerate inputs).
TestRunbookContent pins the runbook text.
"""
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "gal-07-live-handoff.md"
GATE_PATH = REPO_ROOT / "docs" / "runbooks" / "gal-07-live-check.sh"

_HOST_CORE_VENV = Path.home() / "data" / "nikko" / ".venvs" / "galago-py310" / "bin" / "python"


def _imports_pinned_core(python: str) -> bool:
    """True when `python -c "import stack_automation_layer.owner_lock"` succeeds from the repo
    root — the exact probe gate check 2 performs on the candidates below."""
    try:
        return subprocess.run(
            [python, "-c", "import stack_automation_layer.owner_lock"],
            cwd=REPO_ROOT, capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _lock_probe_python() -> str:
    """A python that can import the pinned core for the fixture's check-2 override.

    sys.executable first (fastest, fully offline), then the host service venv the real gate
    probes by default; falling back to sys.executable keeps the previous behavior when no
    candidate imports the core, and the gate itself emits its own `missing:` line — a loud
    environment gap, never a silent skip.
    """
    for candidate in (sys.executable, str(_HOST_CORE_VENV)):
        if _imports_pinned_core(candidate):
            return candidate
    return sys.executable


# Requirement-only environment skips (bash, importable core) fail instead of silently skipping
# when the verification run wants a full proof.
GAL07_REQUIRE_ALL = "GAL07_REQUIRE_ALL"

PINNED_CORE_SHA = "934a621ece116a8b263897c1e9b62b57374f4ef3"
LIVE_HOST = "10.150.1.125"
LIVE_PORT = "5005"

H1 = "# GAL-07 live handoff runbook: STACK -> F.A.S.T. -> STACK (live, supervised)"

REQUIRED_HEADINGS = [
    H1,
    "## Safety rules",
    "## Pre-flight",
    "## Part 1: deploy (LIVE-08)",
    "## Part 2: supervised live Transfer (LIVE-09)",
    "## Part 3: supervised live GAL-02 handoff (LIVE-10)",
    "## Recovery drill (D-11)",
    "## Findings log",
]

FINDINGS_ROWS = (
    ["G0"]
    + [f"1a-{n}" for n in range(1, 7)]
    + [f"2a-{n}" for n in range(1, 4)]
    + [f"3a-{n}" for n in range(1, 4)]
)

REQUIRED_PHRASES = [
    "bash docs/runbooks/gal-07-live-check.sh",
    "PREFLIGHT OK",
    "BLOCKED:",
    "Stack manager",
    "10.150.1.125",
    "http://10.150.1.125:5005",
    "tools/tests/gal07_live_runbook_test.py",
    "docs/runbooks/gal-02-handoff.md",
    "remains in force",
    "never delete",
    "stack2-6",
    "GetFailureLatch",
    "GetRobotStates",
    "GetManagerState",
    "GetLabwarePresence",
    "ListDevices",
    "ListLabwareProfiles",
    "numberOfRuns",
    "nest-1/deck1/A1",
    "orange-nest/deck1/A1",
    "rack/l1/A1",
    "REPLAY_WINDOW_S",
    "600 s",
    "tool restarted mid-transfer; inspect the arm; the core may not have latched this failure",
    "GAL07_REQUIRE_STACK_ENV=1",
    "systemctl --user restart galago-tools",
    "stack-ledger.json",
    "not found in store",
    "fast_status.py --port 40012",
    "uv pip install --python .venv/bin/python -r tools/stack/requirements.txt",
    "direct_url.json",
    "TOOLBOX_PORT=11010 docker compose up -d --build",
]

MANAGER_APPLICATION_JSON = json.dumps(
    {"productVersion": "0.12.0-beta.1+1157", "productName": "Stack manager"}
)


def skip_or_fail(reason: str) -> None:
    """Skip with reason, or fail when GAL07_REQUIRE_ALL is set (REQUIRE_ALL_ENV pattern from
    tools/tests/gal02_harness.py with the Phase 7 variable name)."""
    if os.environ.get(GAL07_REQUIRE_ALL, "") not in ("", "0"):
        raise AssertionError(f"{reason} ({GAL07_REQUIRE_ALL} is set, so this skip is a failure)")
    raise unittest.SkipTest(reason)


def _tools_json(stored_stack_host: str, fast_present: bool = True) -> str:
    """The production-store shape as probed 2026-11-02: a stack tool entry whose config carries
    the snake_case host/port/ledger_dir keys, plus (for the complete fixture) a fast tool."""
    tools: list[dict[str, Any]] = [
        {
            "id": 11,
            "type": "stack",
            "name": "Stack",
            "port": "40012",
            "config": {"host": stored_stack_host, "port": "5005", "ledger_dir": ""},
        },
    ]
    if fast_present:
        tools.append({"id": 12, "type": "fast", "name": "Fast", "port": "40001", "config": {}})
    return json.dumps(tools)


def _snapshot(root: Path) -> dict[str, tuple[str, int]]:
    """Relative path -> (sha256, mtime_ns) for every file under root."""
    result: dict[str, tuple[str, int]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            result[str(path.relative_to(root))] = (digest, path.stat().st_mtime_ns)
    return result


def _fixture_handler(routes: dict[str, tuple[int, str]]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            route = routes.get(self.path)
            if route is None:
                self.respond(404, "")
            else:
                self.respond(route[0], route[1])

        def respond(self, status: int, body: str) -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: str) -> None:  # noqa: A002
            # silent: the fixture server must not pollute the test output
            pass

    return Handler


class TestLiveGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.name == "nt" or shutil.which("bash") is None:
            skip_or_fail("the GAL-07 pre-flight is a POSIX shell script for the galago-tools "
                         "Linux host; bash is required")

    def _run(self, extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, **extra_env}
        return subprocess.run(
            ["bash", str(GATE_PATH)], env=env, capture_output=True, text=True, timeout=30)

    def _lines(self, completed: subprocess.CompletedProcess[str]) -> list[str]:
        return completed.stdout.splitlines()

    @contextlib.contextmanager
    def _fixture_web(self, routes: dict[str, tuple[int, str]]) -> Iterator[str]:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _fixture_handler(routes))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}"
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    @contextlib.contextmanager
    def _complete_env(
        self,
        *,
        application_json: str = MANAGER_APPLICATION_JSON,
        tools_json: str = _tools_json(LIVE_HOST),
        runs_json: str = "[]",
        core_commit: str = PINNED_CORE_SHA,
        direct_url_missing: bool = False,
        dep02_ok: bool = True,
        dep02_missing: bool = False,
        docker_ok: bool = True,
        docker_empty_output: bool = False,
        with_holder: bool = False,
        credentials_file: bool = True,
        credentials_mode: int = 0o600,
        credentials_assignments: int = 1,
        require_stack_env: bool = False,
        extra_env: dict[str, str] | None = None,
    ) -> Iterator[dict[str, str]]:
        """Every check's target is a fixture, so one gate run in the sandbox either passes or
        fails for one named reason. Set a single piece wrong to prove its own refusal line."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock_dir = root / "locks"
            lock_dir.mkdir()
            venv_dir = root / "services-venv"
            dist_info = (
                venv_dir / "lib" / "python3.10" / "site-packages"
                / "stack_automation_layer-1.0.0.dist-info")
            dist_info.mkdir(parents=True)
            if not direct_url_missing:
                (dist_info / "direct_url.json").write_text(
                    json.dumps({"dir_info": {}, "url": "https://fixture.invalid/core",
                                "vcs_info": {"vcs": "git", "commit_id": core_commit}}),
                    encoding="utf-8")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            if not dep02_missing:
                dep02 = bin_dir / "dep02-stub.sh"
                dep02.write_text(
                    'echo "DEP-02 OK"\nexit 0\n' if dep02_ok else
                    'echo "still missing the DEP-02 build pieces"\nexit 1\n',
                    encoding="utf-8")
                dep02.chmod(0o755)
            if docker_ok and not docker_empty_output:
                docker_body = "echo /app/gen-interfaces/tools/grpc_interfaces/stack.ts\nexit 0\n"
            elif docker_empty_output:
                docker_body = "exit 0\n"
            else:
                docker_body = 'echo "cannot reach the container" >&2\nexit 1\n'
            docker_stub = bin_dir / "docker-stub"
            docker_stub.write_text(docker_body, encoding="utf-8")
            docker_stub.chmod(0o755)
            stack_env = root / "stack.env"
            if credentials_file:
                stack_env.write_text("STACK_USER=operator-fixture\n" * credentials_assignments,
                                     encoding="utf-8")
                stack_env.chmod(credentials_mode)
            holder_fd: int | None = None
            if with_holder:
                # The probe cannot see content without a live holder: the test process holds the
                # non-blocking flock and the 256-byte holder record for the whole run below.
                path = _lock_file_path(lock_dir)
                fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                record = json.dumps(
                    {"owner": "mcp", "pid": os.getpid(), "endpoint": f"{LIVE_HOST}:{LIVE_PORT}"})
                data = record.ljust(256).encode("utf-8")
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, data)
                holder_fd = fd
            env = {
                "STACK_HOST": LIVE_HOST,
                "STACK_PORT": LIVE_PORT,
                "GAL07_LOCK_PROBE_PYTHON": _lock_probe_python(),
                "STACK_MCP_LOCK_DIR": str(lock_dir),
                "GALAGO_SERVICES_VENV": str(venv_dir),
                "GAL07_STACK_ENV": str(stack_env),
                "GAL07_DOCKER": str(bin_dir / "docker-stub"),
            }
            if not dep02_missing:
                env["GAL07_DEP02_GATE"] = str(bin_dir / "dep02-stub.sh")
            else:
                env["GAL07_DEP02_GATE"] = str(root / "absent" / "dep02-check.sh")
            if require_stack_env:
                env["GAL07_REQUIRE_STACK_ENV"] = "1"
            if extra_env:
                env.update(extra_env)
            try:
                with self._fixture_web({
                    "/api/general/application": (200, application_json),
                    "/api/tools": (200, tools_json),
                    "/api/runs": (200, runs_json),
                }) as url:
                    env["STACK_MANAGER_URL"] = url
                    env["GALAGO_WEB_URL"] = url
                    self._current_root: Path | None = root
                    yield env
            finally:
                if holder_fd is not None:
                    fcntl.flock(holder_fd, fcntl.LOCK_UN)
                    os.close(holder_fd)
            self._current_root = None

    def test_gate_refuses_a_wrong_manager_identity(self) -> None:
        with self._complete_env(
            application_json=json.dumps(
                {"productVersion": "0.12.0-beta.1+1157", "productName": "Other"})
        ) as env:
            completed = self._run(env)
        lines = self._lines(completed)
        self.assertEqual(completed.returncode, 1, completed.stdout)
        self.assertTrue(lines[-1].startswith("BLOCKED:"), lines)
        self.assertIn("STACK manager identity", "\n".join(lines), lines)
        self.assertEqual(len([x for x in lines if x.startswith("missing:")]), 1, lines)

    def test_gate_accepts_the_good_manager_identity(self) -> None:
        with self._complete_env() as env:
            completed = self._run(env)
        lines = self._lines(completed)
        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertEqual(lines[-1], "PREFLIGHT OK")
        self.assertEqual([x for x in lines if x.startswith(("missing:", "forbidden:"))], [])
        self.assertEqual([x for x in lines if x.startswith("warn:")], [], lines)
        self.assertIsNone(re.search(r"missing:.*manager identity", "\n".join(lines)), lines)

    def test_gate_accepts_the_production_store_and_runs_shapes(self) -> None:
        """The production galago-web store nests the STACK config under `.config.stack`, and the
        run list is a {"count": n, "data": [...]} envelope; both must satisfy the checks."""
        nested_tools = json.dumps([
            {"id": 11, "type": "stack", "name": "Stack", "port": 40012,
             "config": {"stack": {"host": LIVE_HOST, "port": "5005", "ledger_dir": ""}}},
            {"id": 12, "type": "fast", "name": "Fast", "port": 40001, "config": {}},
        ])
        environments_runs = json.dumps({"count": 0, "data": []})
        with self._complete_env(tools_json=nested_tools, runs_json=environments_runs) as env:
            completed = self._run(env)
        lines = self._lines(completed)
        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertEqual(lines[-1], "PREFLIGHT OK")
        self.assertEqual([x for x in lines if x.startswith(("missing:", "forbidden:"))], [], lines)

    def test_gate_blocks_each_single_removed_piece(self) -> None:
        cases: dict[str, dict[str, Any]] = {
            "identity": {
                "application_json": json.dumps(
                    {"productVersion": "0.12.0-beta.1+1157", "productName": "Other"}),
                "needle": "STACK manager identity"},
            "held_lock": {
                "with_holder": True,
                "needle": "only one front end may hold it",
                "also": "mcp"},
            "venv_pin": {"core_commit": "0" * 40, "needle": "stack_automation_layer pinned"},
            "dep02_stub_fails": {"dep02_ok": False, "needle": "DEP-02 gate re-run"},
            "dep02_missing": {"dep02_missing": True, "needle": "DEP-02 gate re-run"},
            "web_bundle": {"docker_ok": False, "needle": "Command_Transfer"},
            "docker_empty_output": {"docker_empty_output": True, "needle": "Command_Transfer"},
            "store_no_fast": {"tools_json": _tools_json(LIVE_HOST, fast_present=False),
                              "needle": "type fast"},
            "stored_host": {"tools_json": _tools_json("stack-server"),
                            "needle": "byte-exactly", "also": "different lock/state key"},
            "running_run": {"runs_json": json.dumps([{"state": "RUNNING"}]),
                            "needle": "state RUNNING"},
            "running_run_envelope": {
                "runs_json": json.dumps({"count": 1, "data": [{"state": "RUNNING"}]}),
                "needle": "state RUNNING"},
            "creds_required": {"credentials_file": False, "require_stack_env": True,
                               "needle": "stack credentials env file"},
        }
        for piece, case in cases.items():
            with self.subTest(piece=piece):
                kwargs = {k: v for k, v in case.items() if k not in ("needle", "also")}
                with self._complete_env(**kwargs) as env:
                    completed = self._run(env)
                lines = self._lines(completed)
                self.assertEqual(completed.returncode, 1, (piece, completed.stdout))
                self.assertTrue(lines[-1].startswith("BLOCKED:"), (piece, lines[-1]))
                joined = "\n".join(lines)
                self.assertIn(case["needle"], joined, (piece, joined))
                if "also" in case:
                    self.assertIn(case["also"], joined, (piece, joined))
                self.assertGreaterEqual(
                    len([x for x in lines if x.startswith(("missing:", "forbidden:"))]),
                    1, (piece, lines))

    def test_gate_fails_closed_on_degenerate_inputs(self) -> None:
        cases: dict[str, dict[str, Any]] = {
            "empty_application": {"application_json": "", "needle": "STACK manager identity"},
            "non_json_application": {"application_json": "<html>gateway</html>",
                                     "needle": "STACK manager identity"},
            "empty_tools": {"tools_json": "", "needle": "JSON tool array"},
            "non_json_tools": {"tools_json": "gateway error", "needle": "JSON tool array"},
            "empty_runs": {"runs_json": "", "needle": "parsable runs list"},
            "non_json_runs": {"runs_json": "gateway error", "needle": "parsable runs list"},
            "runs_unexpected_envelope": {
                "runs_json": json.dumps({"count": 0}), "needle": "parsable runs list"},
            "missing_direct_url": {"direct_url_missing": True,
                                   "needle": "stack_automation_layer pinned"},
        }
        for label, case in cases.items():
            with self.subTest(case=label):
                kwargs = {k: v for k, v in case.items() if k != "needle"}
                with self._complete_env(**kwargs) as env:  # type: ignore[arg-type]
                    completed = self._run(env)
                lines = self._lines(completed)
                self.assertEqual(completed.returncode, 1, (label, completed.stdout))
                self.assertTrue(lines[-1].startswith("BLOCKED:"), (label, lines[-1]))
                self.assertIn(case["needle"], "\n".join(lines), (label, lines))

    def test_gate_credential_env_is_advisory_when_unrequired(self) -> None:
        cases: dict[str, dict[str, Any]] = {
            "missing file": {"credentials_file": False},
            "no assignment line": {"credentials_assignments": 0},
            "too-open mode": {"credentials_mode": 0o644},
        }
        for label, kwargs in cases.items():
            with self.subTest(case=label), self._complete_env(**kwargs) as env:
                completed = self._run(env)
            lines = self._lines(completed)
            self.assertEqual(completed.returncode, 0, (label, completed.stdout))
            self.assertEqual(lines[-1], "PREFLIGHT OK")
            self.assertEqual(len([x for x in lines if x.startswith("warn:")]), 1, (label, lines))
            self.assertEqual([x for x in lines if x.startswith("missing:")], [], (label, lines))

    def test_gate_credential_env_blocks_when_required(self) -> None:
        cases: dict[str, dict[str, Any]] = {
            "missing file": {"credentials_file": False},
            "no assignment line": {"credentials_assignments": 0},
            "too-open mode": {"credentials_mode": 0o644},
        }
        for label, kwargs in cases.items():
            with self.subTest(case=label), self._complete_env(
                **kwargs, require_stack_env=True,
            ) as env:
                completed = self._run(env)
            lines = self._lines(completed)
            self.assertEqual(completed.returncode, 1, (label, completed.stdout))
            self.assertTrue(lines[-1].startswith("BLOCKED:"), (label, lines[-1]))
            self.assertGreaterEqual(
                len([x for x in lines if x.startswith("missing:")]), 1, (label, lines))

    def test_gate_is_read_only(self) -> None:
        with self._complete_env() as env:
            root = self._current_root
            assert root is not None
            before = _snapshot(root)
            first = self._run(env)
            second = self._run(env)
            after = _snapshot(root)
        for completed in (first, second):
            self.assertEqual(completed.returncode, 0, completed.stdout)
            self.assertEqual(self._lines(completed)[-1], "PREFLIGHT OK")
        self.assertEqual(before, after)


def _lock_file_path(lock_dir: Path) -> Path:
    """The real lock path for the live endpoint, computed with the pinned core's own helpers so
    the fixture cannot drift from what open_service acquires. Computed through the resolved
    core-importable python (see _lock_probe_python) so the invariant does not depend on the
    interpreter running pytest importing the core itself."""
    script = (
        "import json\n"
        "from stack_automation_layer.owner_lock import endpoint_key, lock_path\n"
        f"print(json.dumps(str(lock_path(endpoint_key({LIVE_HOST!r}, {int(LIVE_PORT)}), {str(lock_dir)!r}))))"
    )
    completed = subprocess.run(
        [_lock_probe_python(), "-c", script],
        cwd=REPO_ROOT, capture_output=True, timeout=60)
    if completed.returncode != 0:
        raise AssertionError(
            f"cannot import the pinned core through {_lock_probe_python()} "
            f"({_HOST_CORE_VENV} also rejected): {completed.stderr.decode()}")
    return Path(json.loads(completed.stdout.decode()))


class TestRunbookContent(unittest.TestCase):
    text: str
    lines: list[str]

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = RUNBOOK_PATH.read_text(encoding="utf-8")
        cls.lines = cls.text.splitlines()

    def test_runbook_has_every_section_heading(self) -> None:
        positions = []
        for heading in REQUIRED_HEADINGS:
            with self.subTest(heading=heading):
                self.assertIn(heading, self.lines)
                positions.append(self.lines.index(heading))
        self.assertEqual(positions, sorted(positions), "headings are out of order")

    def test_runbook_carries_the_required_phrases(self) -> None:
        for phrase in REQUIRED_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text)

    def test_runbook_carries_one_go_gate_per_part(self) -> None:
        """D-10: each live part waits for a typed go recorded with a UTC timestamp — exactly one
        "Reply: literal go" line per part slice, never anywhere else."""
        starts = [next(i for i, line in enumerate(self.lines)
                       if line.startswith(f"## Part {n}:")) for n in (1, 2, 3)]
        drill = next(i for i, line in enumerate(self.lines)
                     if line.startswith("## Recovery drill"))
        bounds = [(starts[0], starts[1]), (starts[1], starts[2]), (starts[2], drill)]
        for n, (start, end) in enumerate(bounds, start=1):
            with self.subTest(part=n):
                section = "\n".join(self.lines[start:end])
                self.assertEqual(section.count("Reply: literal go"), 1, section[-400:])
                self.assertIn("UTC", section, section[-400:])
        self.assertEqual(self.text.count("Reply: literal go"), 3, self.text)

    def test_runbook_findings_log_has_every_row(self) -> None:
        start = self.lines.index("## Findings log")
        section = self.lines[start:]
        for row_id in FINDINGS_ROWS:
            with self.subTest(row=row_id):
                self.assertTrue(
                    any(line.startswith(f"| {row_id} |") for line in section),
                    f"no Findings row {row_id}")

    def test_runbook_holds_no_credential_values(self) -> None:
        self.assertIsNone(re.search(r"STACK_(USER|PASSWORD)=[^\s$<\"']", self.text))
        self.assertIsNone(re.search(r"Bearer [A-Za-z0-9._-]{8,}", self.text))


if __name__ == "__main__":
    unittest.main()
