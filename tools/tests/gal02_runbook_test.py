"""GAL-02 runbook tests (FLOW-01, FLOW-04 safety): the DEP-02 gate script and the runbook text.

TestDep02Gate runs docs/runbooks/gal-02-dep02-check.sh against fixture trees built in a temp
directory, so the gate is proven unable to pass falsely. TestRunbookContent pins the runbook text.
"""
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "gal-02-handoff.md"
GATE_PATH = REPO_ROOT / "docs" / "runbooks" / "gal-02-dep02-check.sh"
FROZEN_PROTO = REPO_ROOT / "interfaces" / "tools" / "grpc_interfaces" / "stack.proto"

D07_STATEMENT = (
    "The Galago-simulated re-dispatch in Part 2a proves only that the protocol's stored STACK step "
    "survives a re-dispatch through the real queue: it returns SUCCESS and no ledger file appears "
    "in the configured ledger_dir. It does not prove that no second transfer is sent; only the "
    "offline fake-core test (tools/tests/gal02_replay_test.py) and the Part 2b run against the PAC "
    "simulator prove that."
)

_H1 = "# GAL-02 handoff runbook: STACK -> F.A.S.T. -> STACK (simulation only)"


def _make_core_tree(
    root: Path,
    *,
    tooltype: bool = True,
    stack_ts: bool = True,
    stack_fields: bool = True,
    ack: bool = False,
    proto: str = "same",
) -> None:
    """Write a minimal galago-core tree under root. proto is "same", "differs" or "missing"."""
    gen = root / "controller" / "gen-interfaces"
    (gen / "tools" / "grpc_interfaces").mkdir(parents=True)
    controller_lines = ["export enum ToolType {", '  fast = "fast",']
    if tooltype:
        controller_lines.append('  stack = "stack",')
    controller_lines.append("}")
    (gen / "controller.ts").write_text("\n".join(controller_lines) + "\n", encoding="utf-8")
    if stack_ts:
        (gen / "tools" / "grpc_interfaces" / "stack.ts").write_text(
            "export const x = 1;\n", encoding="utf-8")

    components = root / "controller" / "components" / "tools"
    components.mkdir(parents=True)
    constants = [
        "export const commandFields: CommandFields = {",
        "  fast: {",
        "    transfer: [",
        '      { name: "volume", type: "number" },',
        "    ],",
        "  },",
    ]
    if stack_fields:
        constants.append("  stack: {")
        constants.append("    transfer: [],")
        if ack:
            constants.append("    acknowledge_failure: [],")
        constants.append("  },")
    constants.append("};")
    (components / "constants.ts").write_text("\n".join(constants) + "\n", encoding="utf-8")

    vendored = root / "vendor" / "galago-tools" / "interfaces" / "tools" / "grpc_interfaces"
    if proto != "missing":
        vendored.mkdir(parents=True)
        data = FROZEN_PROTO.read_bytes()
        if proto == "differs":
            data = data + b" "
        (vendored / "stack.proto").write_bytes(data)


def _snapshot(root: Path) -> dict[str, tuple[str, int]]:
    """Relative path -> (sha256, mtime_ns) for every file under root."""
    result: dict[str, tuple[str, int]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            result[str(path.relative_to(root))] = (digest, path.stat().st_mtime_ns)
    return result


class TestDep02Gate(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        missing = [tool for tool in ("bash", "awk", "grep", "cmp") if shutil.which(tool) is None]
        if os.name == "nt" or missing:
            raise unittest.SkipTest(
                "the DEP-02 gate is a POSIX shell script for the galago-tools Linux host; "
                "bash, awk, grep and cmp are required")

    def _run(self, core: Path) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "GALAGO_CORE_DIR": str(core), "GALAGO_TOOLS_DIR": str(REPO_ROOT)}
        return subprocess.run(
            ["bash", str(GATE_PATH)], env=env, capture_output=True, text=True, timeout=30)

    def _lines(self, completed: subprocess.CompletedProcess[str]) -> list[str]:
        return completed.stdout.splitlines()

    def test_dep02_gate_blocks_on_an_empty_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = self._run(Path(tmp))
        lines = self._lines(completed)
        self.assertEqual(completed.returncode, 1)
        self.assertTrue(lines[-1].startswith("BLOCKED:"), lines)
        self.assertGreaterEqual(len([x for x in lines if x.startswith("missing:")]), 4)

    def test_dep02_gate_passes_on_a_complete_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _make_core_tree(Path(tmp))
            completed = self._run(Path(tmp))
        lines = self._lines(completed)
        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertEqual(lines[-1], "DEP-02 OK")
        self.assertEqual([x for x in lines if x.startswith("missing:")], [])
        self.assertEqual([x for x in lines if x.startswith("forbidden:")], [])

    def test_dep02_gate_blocks_each_single_missing_piece(self) -> None:
        pieces: dict[str, dict[str, object]] = {
            "tooltype": {"tooltype": False},
            "stack_ts": {"stack_ts": False},
            "stack_fields": {"stack_fields": False},
            "proto missing": {"proto": "missing"},
        }
        for label, kwargs in pieces.items():
            with self.subTest(piece=label), tempfile.TemporaryDirectory() as tmp:
                _make_core_tree(Path(tmp), **kwargs)  # type: ignore[arg-type]
                completed = self._run(Path(tmp))
                lines = self._lines(completed)
                self.assertEqual(completed.returncode, 1, completed.stdout)
                self.assertTrue(lines[-1].startswith("BLOCKED:"), lines)
                self.assertEqual(len([x for x in lines if x.startswith("missing:")]), 1, lines)

    def test_dep02_gate_blocks_when_stack_fields_expose_acknowledge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _make_core_tree(Path(tmp), ack=True)
            completed = self._run(Path(tmp))
        lines = self._lines(completed)
        self.assertEqual(completed.returncode, 1)
        self.assertTrue(any(x.startswith("forbidden:") for x in lines), lines)
        self.assertTrue(lines[-1].startswith("BLOCKED:"), lines)

    def test_dep02_gate_blocks_when_the_vendored_proto_differs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _make_core_tree(Path(tmp), proto="differs")
            completed = self._run(Path(tmp))
        lines = self._lines(completed)
        self.assertEqual(completed.returncode, 1)
        self.assertTrue(lines[-1].startswith("BLOCKED:"), lines)

    def test_dep02_gate_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_core_tree(root)
            before = _snapshot(root)
            self._run(root)
            self._run(root)
            after = _snapshot(root)
        self.assertEqual(before, after)

    def test_dep02_gate_on_the_real_sibling_tree_prints_one_verdict(self) -> None:
        sibling = REPO_ROOT.parent / "galago-core"
        if not (sibling / "controller").is_dir():
            self.skipTest(f"no sibling galago-core checkout at {sibling}")
        completed = subprocess.run(
            ["bash", str(GATE_PATH)],
            env={**os.environ, "GALAGO_CORE_DIR": str(sibling), "GALAGO_TOOLS_DIR": str(REPO_ROOT)},
            capture_output=True, text=True, timeout=30)
        last = completed.stdout.splitlines()[-1]
        if completed.returncode == 0:
            self.assertEqual(last, "DEP-02 OK")
        else:
            self.assertEqual(completed.returncode, 1)
            self.assertTrue(last.startswith("BLOCKED:"), last)


class TestRunbookContent(unittest.TestCase):
    text: str
    lines: list[str]

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = RUNBOOK_PATH.read_text(encoding="utf-8")
        cls.lines = cls.text.splitlines()

    def test_runbook_has_the_opening_and_gate_headings(self) -> None:
        for heading in (
            _H1, "## Safety rules", "## What each part proves", "## Part 2 gate: DEP-02",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, self.lines)

    def test_runbook_states_d07_exactly(self) -> None:
        self.assertIn(D07_STATEMENT, self.text)

    def test_runbook_part2_gate_runs_the_gate_script(self) -> None:
        for phrase in ("bash docs/runbooks/gal-02-dep02-check.sh", "DEP-02 OK", "BLOCKED:"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text)


if __name__ == "__main__":
    unittest.main()
