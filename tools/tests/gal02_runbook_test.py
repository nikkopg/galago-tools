"""GAL-02 runbook tests (FLOW-01, FLOW-04 safety): the DEP-02 gate script and the runbook text.

TestDep02Gate runs docs/runbooks/gal-02-dep02-check.sh against fixture trees built in a temp
directory, so the gate is proven unable to pass falsely. TestRunbookContent pins the runbook text.
"""
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Optional

from tools.tests.gal02_harness import load_export, skip_or_fail

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

REQUIRED_HEADINGS = [
    _H1,
    "## Safety rules",
    "## What each part proves",
    "## The protocol",
    "## Part 1: offline proof (any session)",
    "## Part 2 gate: DEP-02",
    "## Part 2 shared setup (operator)",
    "## Part 2a: Galago-simulated workcell run (FLOW-02, FLOW-03 simulated half)",
    "## Part 2b: STACK real mode against the PAC simulator (FLOW-04)",
    "### Hardware-refusal preflight",
    "### Forced re-dispatch and the no-second-POST evidence",
    "## If something goes wrong",
    "## Known limitations",
    "## Teardown (operator only; the executor never runs it)",
    "## Upstream follow-ups",
    "## Findings log",
]

FINDINGS_ROWS = ["G0", "2a-1", "2a-2", "2a-3", "2b-0", "2b-1", "2b-2", "2b-3", "2b-4", "2b-5"]

REQUIRED_PHRASES = [
    "jq .protocol docs/runbooks/gal-02-handoff.protocol.json",
    "/api/protocols",
    "galago-gal06",
    "STACK-SIM",
    "STACK-PACSIM",
    "STACK_SIM_PORT",
    "GetRobotStates",
    "sim-arm-1",
    "Stack manager",
    "10.150.1.125",
    "stack-server",
    "REPLAY_WINDOW_S",
    "replayed",
    "step key already completed",
    "numberOfRuns",
    "/home/formulatrix/.local/state/galago-tools/stack-sim",
    "scripts/sim_up.sh down",
    "ProtocolPageComponent.tsx",
]


def _make_core_tree(
    root: Path,
    *,
    tooltype: bool = True,
    stack_ts: bool = True,
    stack_fields: bool = True,
    ack: bool = False,
    proto: str = "same",
    stack_lines: Optional[list[str]] = None,
    tooltype_outside_enum: bool = False,
    stack_ts_text: str = "export interface Command_Transfer {\n  step_key: string;\n}\n",
) -> None:
    """Write a minimal galago-core tree under root. proto is "same", "differs" or "missing".

    stack_lines, when given, replaces the whole stack block (opener to closer) with those raw lines.
    A trailing `zzz` tool block that does hold `transfer` follows it, so a block that fails to end
    cleanly would be seen to spill into it."""
    gen = root / "controller" / "gen-interfaces"
    (gen / "tools" / "grpc_interfaces").mkdir(parents=True)
    controller_lines = ["export enum ToolType {", '  fast = "fast",']
    if tooltype:
        controller_lines.append('  stack = "stack",')
    controller_lines.append("}")
    if tooltype_outside_enum:
        # Same line, wrong enum: must not satisfy the ToolType check.
        controller_lines.extend(["export enum Other {", '  stack = "stack",', "}"])
    (gen / "controller.ts").write_text("\n".join(controller_lines) + "\n", encoding="utf-8")
    if stack_ts:
        (gen / "tools" / "grpc_interfaces" / "stack.ts").write_text(stack_ts_text, encoding="utf-8")

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
    if stack_lines is not None:
        constants.extend(stack_lines)
        constants.extend(["  zzz: {", "    transfer: [],", "  },"])
    elif stack_fields:
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
            skip_or_fail(
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

    def test_dep02_gate_does_not_count_substring_decoys_as_stack_transfer(self) -> None:
        # CR-01: list_transfer_profiles / get_transfer_estimate contain "transfer" but are not it.
        cases: dict[str, list[str]] = {
            "decoy command names only": [
                "  stack: {",
                "    list_transfer_profiles: [{ name: \"refresh\", type: \"boolean\" }],",
                "    get_transfer_estimate: [{ name: \"robot\", type: \"text\" }],",
                "  },",
            ],
            "transfer only as a quoted field name": [
                "  stack: {",
                "    get_labware_presence: [{ name: \"transfer\", type: \"text\" }],",
                "  },",
            ],
            "transfer indented one level too deep (nested)": [
                "  stack: {",
                "    get_manager_state: [",
                "      transfer: [],",
                "    ],",
                "  },",
            ],
            "one-line block without transfer, next tool has it": [
                "  stack: { get_manager_state: [] },",
            ],
            "one-line block with transfer second, next tool has it": [
                "  stack: { get_manager_state: [], transfer: [] },",
            ],
        }
        for label, lines in cases.items():
            with self.subTest(case=label), tempfile.TemporaryDirectory() as tmp:
                _make_core_tree(Path(tmp), stack_lines=lines)
                completed = self._run(Path(tmp))
                out = self._lines(completed)
                self.assertEqual(completed.returncode, 1, completed.stdout)
                self.assertTrue(out[-1].startswith("BLOCKED:"), out)
                self.assertEqual(
                    [x for x in out if x.startswith("missing:")],
                    ["missing: commandFields.stack.transfer in "
                     "controller/components/tools/constants.ts"], out)

    def test_dep02_gate_accepts_the_transfer_key_with_decoys_and_a_one_line_block(self) -> None:
        cases: dict[str, list[str]] = {
            "key plus decoys": [
                "  stack: {",
                "    transfer: [{ name: \"step_key\", type: \"text\" }],",
                "    list_transfer_profiles: [{ name: \"refresh\", type: \"boolean\" }],",
                "    get_transfer_estimate: [],",
                "  },",
            ],
            "one-line block with transfer first": [
                "  stack: { transfer: [], get_manager_state: [] },",
            ],
        }
        for label, lines in cases.items():
            with self.subTest(case=label), tempfile.TemporaryDirectory() as tmp:
                _make_core_tree(Path(tmp), stack_lines=lines)
                completed = self._run(Path(tmp))
                self.assertEqual(completed.returncode, 0, completed.stdout)
                self.assertEqual(self._lines(completed)[-1], "DEP-02 OK")

    def test_dep02_gate_reports_a_missing_stack_block_even_if_other_tools_have_transfer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _make_core_tree(Path(tmp), stack_fields=False)
            completed = self._run(Path(tmp))
        out = self._lines(completed)
        self.assertEqual(completed.returncode, 1, completed.stdout)
        self.assertEqual(
            [x for x in out if x.startswith("missing:")],
            ["missing: commandFields.stack block in controller/components/tools/constants.ts"], out)

    def test_dep02_gate_scopes_tooltype_to_its_own_enum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _make_core_tree(Path(tmp), tooltype=False, tooltype_outside_enum=True)
            completed = self._run(Path(tmp))
        out = self._lines(completed)
        self.assertEqual(completed.returncode, 1, completed.stdout)
        self.assertEqual(
            [x for x in out if x.startswith("missing:")],
            ["missing: ToolType.stack in controller/gen-interfaces/controller.ts"], out)

    def test_dep02_gate_requires_the_generated_stack_file_to_export_transfer(self) -> None:
        for label, text in (("empty", ""), ("stale", "export const x = 1;\n")):
            with self.subTest(case=label), tempfile.TemporaryDirectory() as tmp:
                _make_core_tree(Path(tmp), stack_ts_text=text)
                completed = self._run(Path(tmp))
                out = self._lines(completed)
                self.assertEqual(completed.returncode, 1, completed.stdout)
                self.assertEqual(len([x for x in out if x.startswith("missing:")]), 1, out)

    def test_dep02_gate_reports_a_revision_only_for_a_checkout_root(self) -> None:
        if shutil.which("git") is None:
            skip_or_fail("git is required for the revision check")
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        with tempfile.TemporaryDirectory() as tmp:
            outer = Path(tmp) / "outer"
            outer.mkdir()
            subprocess.run([*git, "init", "-q", str(outer)], check=True, capture_output=True)
            subprocess.run(
                [*git, "-C", str(outer), "commit", "-q", "--allow-empty", "-m", "x"],
                check=True, capture_output=True)
            head = subprocess.run(
                ["git", "-C", str(outer), "rev-parse", "--short", "HEAD"],
                check=True, capture_output=True, text=True).stdout.strip()
            inner = outer / "galago-core"
            inner.mkdir()
            _make_core_tree(inner)
            nested = self._lines(self._run(inner))
            at_root = self._lines(self._run(outer))  # the repository root itself reports it
        self.assertIn("galago-core HEAD: unknown", nested)
        self.assertNotIn(f"galago-core HEAD: {head}", nested)
        self.assertIn(f"galago-core HEAD: {head}", at_root)

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

    def test_dep02_gate_is_read_only_inside_a_real_git_repo_and_the_tools_tree(self) -> None:
        if shutil.which("git") is None:
            skip_or_fail("git is required")
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]

        def porcelain() -> str:
            return subprocess.run(
                ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
                capture_output=True, text=True, check=False).stdout

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_core_tree(root)
            subprocess.run([*git, "init", "-q", str(root)], check=True, capture_output=True)
            subprocess.run([*git, "-C", str(root), "add", "-A"], check=True, capture_output=True)
            subprocess.run(
                [*git, "-C", str(root), "commit", "-q", "-m", "x"], check=True, capture_output=True)
            before = _snapshot(root)
            tools_before = porcelain()
            completed = self._run(root)
            self._run(root)
            after = _snapshot(root)
            tools_after = porcelain()
        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertEqual(before, after)
        self.assertEqual(tools_before, tools_after)

    def test_dep02_gate_on_the_real_sibling_tree_prints_one_consistent_verdict(self) -> None:
        """Informational only: the sibling checkout is environment dependent, so this asserts the
        verdict line agrees with the exit code. The fixture-tree tests above are the authority."""
        sibling = REPO_ROOT.parent / "galago-core"
        if not (sibling / "controller").is_dir():
            skip_or_fail(f"no sibling galago-core checkout at {sibling}")
        completed = subprocess.run(
            ["bash", str(GATE_PATH)],
            env={**os.environ, "GALAGO_CORE_DIR": str(sibling), "GALAGO_TOOLS_DIR": str(REPO_ROOT)},
            capture_output=True, text=True, timeout=30)
        lines = completed.stdout.splitlines()
        if completed.returncode == 0:
            self.assertEqual(lines[-1], "DEP-02 OK")
            self.assertEqual([x for x in lines if x.startswith(("missing:", "forbidden:"))], [])
        else:
            self.assertEqual(completed.returncode, 1)
            self.assertTrue(lines[-1].startswith("BLOCKED:"), lines[-1])
            self.assertTrue(any(x.startswith(("missing:", "forbidden:")) for x in lines), lines)


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

    def test_runbook_has_every_section_heading(self) -> None:
        positions = []
        for heading in REQUIRED_HEADINGS:
            with self.subTest(heading=heading):
                self.assertIn(heading, self.lines)
                positions.append(self.lines.index(heading))
        self.assertEqual(positions, sorted(positions), "headings are out of order")

    def test_runbook_names_every_protocol_parameter(self) -> None:
        names = [p["name"] for p in load_export()["protocol"]["parameters"]]
        self.assertEqual(len(names), 27)
        for name in names:
            with self.subTest(parameter=name):
                self.assertIn(f"`{name}`", self.text)

    def test_runbook_carries_the_required_procedure_phrases(self) -> None:
        for phrase in REQUIRED_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text)

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
