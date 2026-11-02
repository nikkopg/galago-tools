"""GAL-07 live runbook tests (LIVE-08): the pre-flight gate script and the runbook text.

TestLiveGate runs docs/runbooks/gal-07-live-check.sh against a fixture HTTP server, fixture
trees and stubbed helpers, so the gate is proven unable to pass falsely. TestRunbookContent
pins the runbook text.
"""
import contextlib
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
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "gal-07-live-handoff.md"
GATE_PATH = REPO_ROOT / "docs" / "runbooks" / "gal-07-live-check.sh"

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
]

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
            skip_or_fail(
                "the GAL-07 pre-flight is a POSIX shell script for the galago-tools Linux host; "
                "bash is required")

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
    def _identity_env(
        self, app_json: str = MANAGER_APPLICATION_JSON
    ) -> Iterator[dict[str, str]]:
        """A fixture HTTP manager plus a lock dir holding no lock file, so check 2 is free and
        check 1 (the manager identity) is the only variable."""
        with tempfile.TemporaryDirectory() as lock_dir, self._fixture_web({
            "/api/general/application": (200, app_json),
        }) as mgr_url:
            yield {
                "STACK_MANAGER_URL": mgr_url,
                "STACK_HOST": LIVE_HOST,
                "STACK_PORT": LIVE_PORT,
                "GAL07_LOCK_PROBE_PYTHON": sys.executable,
                "STACK_MCP_LOCK_DIR": lock_dir,
            }

    def test_gate_refuses_a_wrong_manager_identity(self) -> None:
        with self._identity_env(
            json.dumps({"productVersion": "0.12.0-beta.1+1157", "productName": "Other"})
        ) as env:
            completed = self._run(env)
        lines = self._lines(completed)
        self.assertEqual(completed.returncode, 1, completed.stdout)
        self.assertTrue(lines[-1].startswith("BLOCKED:"), lines)
        self.assertGreaterEqual(
            len([x for x in lines if x.startswith("missing:")]), 1, lines)

    def test_gate_accepts_the_good_manager_identity(self) -> None:
        with self._identity_env() as env:
            completed = self._run(env)
        lines = self._lines(completed)
        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertEqual(lines[-1], "PREFLIGHT OK")
        self.assertIsNone(
            re.search(r"missing:.*manager identity", "\n".join(lines)), lines)


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

    def test_runbook_holds_no_credential_values(self) -> None:
        self.assertIsNone(re.search(r"STACK_(USER|PASSWORD)=[^\s$<\"']", self.text))
        self.assertIsNone(re.search(r"Bearer [A-Za-z0-9._-]{8,}", self.text))


if __name__ == "__main__":
    unittest.main()
