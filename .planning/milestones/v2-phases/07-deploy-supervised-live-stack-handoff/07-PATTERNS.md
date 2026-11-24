# Phase 7: Deploy & Supervised Live STACK + Handoff - Pattern Map

**Mapped:** 2026-11-02
**Files analyzed:** 3 new files (+1 optional under discretion) — no repo source files are modified (D-07 keeps `gal-02-handoff.md` pristine; host-level changes are systemd/store/docker, not repo files)
**Analogs found:** 4 / 4 (all git-tracked — verified with `git ls-files` per the tracked-source gate)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `docs/runbooks/gal-07-live-check.sh` | utility (executable pre-flight gate script) | batch (read-only checks, fail-closed) | `docs/runbooks/gal-02-dep02-check.sh` | exact |
| `docs/runbooks/gal-07-live-handoff.md` | documentation (live runbook) | event-driven (supervised live events, per-event GO gates) | `docs/runbooks/gal-02-handoff.md` (structure, safety rules, findings rows) + `.planning/milestones/v1-phases/03-deploy-supervised-live-acceptance/03-DEPLOY.md` (safe-order deploy, GO gate, rollback anchors) | exact |
| `tools/tests/gal07_live_runbook_test.py` | test (pytest/unittest module) | batch (fixture-tree gate tests + runbook text pins) | `tools/tests/gal02_runbook_test.py` (+ `tools/tests/gal02_harness.py` for `skip_or_fail`) | exact |
| `scripts/stack_status.py` *(optional — planner's call; research A5 says a thin alias is a trivial fallback)* | utility (read-only CLI) | request-response (gRPC GetStatus) | `scripts/fast_status.py` | exact |

**Why the inverted-assertion analog is exact:** D-08 explicitly names `docs/runbooks/gal-02-dep02-check.sh` as the pattern to mirror; the live pre-flight is a sibling script whose host assertion is inverted (Phase 6 refuses `10.150.1.125|stack-server`; Phase 7 requires it).

## Pattern Assignments

### `docs/runbooks/gal-07-live-check.sh` (utility, batch — fail-closed read-only gate)

**Analog:** `docs/runbooks/gal-02-dep02-check.sh` (131 lines)

**Script header contract** (lines 1-26) — copy this shape: purpose, READ-ONLY pledge, numbered checks list, exit-code contract, env overrides:

```bash
#!/usr/bin/env bash
# GAL-02 DEP-02 gate (Phase 6, D-01).
#
# Purpose: decide whether galago-core Phase 5 (DEP-02, "STACK Codegen & Command Forms") has landed,
# so that Part 2 of docs/runbooks/gal-02-handoff.md may start. Part 2 never works around DEP-02.
#
# READ-ONLY: this script writes no file, makes no network call and changes no git state. ...
#
# Checks (every check runs; there is no `set -e`):
#   1. ...
#
# Exit codes: 0 = "DEP-02 OK" (last line); 1 = "BLOCKED: ..." (last line).
#
# Environment overrides:
#   GALAGO_TOOLS_DIR  the galago-tools root   (default: two levels above this script)
#   GALAGO_CORE_DIR   the galago-core checkout (default: $GALAGO_TOOLS_DIR/../galago-core)

set -u
```

**Env-resolution + failed-accumulator skeleton** (lines 28-32, 57-61) — every check runs (no `set -e`); each failure sets `failed=1` and prints its own `missing:`/`BLOCKED:` line:

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GT="${GALAGO_TOOLS_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
GC="${GALAGO_CORE_DIR:-$GT/../galago-core}"

failed=0

# 1. checkout
if [ ! -d "$GC/controller" ]; then
  echo "missing: galago-core checkout at $GC"
  failed=1
fi
```

**Verdict lines** (lines 126-131) — exit 0 ends with an `OK` line; exit 1 ends with a `BLOCKED:` line naming what to do:

```bash
if [ "$failed" -eq 0 ]; then
  echo "DEP-02 OK"
  exit 0
fi
echo "BLOCKED: galago-core Phase 5 (DEP-02, STACK Codegen & Command Forms) has not landed; see $GC/.planning/ROADMAP.md Phase 5"
exit 1
```

**Deltas for the live script (from RESEARCH.md Pattern 1 + D-05/D-08):** the live checks are: (a) the STACK manager identity answers `10.150.1.125:5005` with `productName "Stack manager"` (`curl -fsS -m 5 http://10.150.1.125:5005/api/general/application` — read-only GET, no motion); (b) the owner lock is **not held** — probed with the pinned core's own helpers, never a hand-rolled lock name:

```python
# Source: RESEARCH.md Pattern 1 (verified at core 934a621); embed in the check script via
# .venv/bin/python - <<'PY' (or a heredoc-free temp file), NEVER a re-implemented lock name
import fcntl, os, sys
from stack_automation_layer.owner_lock import endpoint_key, lock_path, default_lock_dir

host, port = "10.150.1.125", 5005
path = lock_path(endpoint_key(host, port), default_lock_dir())  # honors STACK_MCP_LOCK_DIR
try:
    fd = os.open(path, os.O_RDWR)          # no O_CREAT: absent file == nobody holds it
except FileNotFoundError:
    print("PREFLIGHT OK: no lock file"); sys.exit(0)
fd2 = os.open(path, os.O_RDONLY)
try:
    fcntl.flock(fd2, fcntl.LOCK_EX | fcntl.LOCK_NB)   # probe; holder unaffected
    fcntl.flock(fd2, fcntl.LOCK_UN)
    print("PREFLIGHT OK: lock free")
except BlockingIOError:
    raw = os.read(fd2, 256)                # the 256-byte holder record
    print(f"BLOCKED: STACK manager {host}:{port} is already owned by "
          f"{raw.decode(errors='replace').strip()}; only one front end may hold it "
          f"(stop the other owner first)")
    sys.exit(1)
finally:
    os.close(fd2); os.close(fd)
```

The refusal wording mirrors `StackOwnedError` verbatim (core `owner_lock.py:79-86`) — this satisfies D-05's "reuse the Configure lock-holder failure message as the detection signal". Additional live checks: (c) service `.venv` has the pinned DEP-02 core — `direct_url.json` commit assert + `unittest tools.tests.stack_test` (v1 Step-1 check pattern, below); (d) `bash docs/runbooks/gal-02-dep02-check.sh` re-run still prints `DEP-02 OK`; (e) `galago-web` bundle has the stack types (`docker exec galago-web grep -rl Command_Transfer /app/gen-interfaces`); (f) D-12 pre-store check: `curl -sf http://localhost:3010/api/tools | jq -e '[.[] | .type] | contains(["stack"]) and contains(["fast"])'` (false today → BLOCKED until the operator adds the FAST tool); (g) no run in flight. Keep the "prints no secrets" contract (presence-only checks, `grep -c '^STACK_USER='`).

---

### `docs/runbooks/gal-07-live-handoff.md` (documentation, event-driven supervised live events)

**Primary analog:** `docs/runbooks/gal-02-handoff.md` (374 lines) — structure, safety-rules section, findings-row format
**Secondary analog:** v1 `.planning/milestones/v1-phases/03-deploy-supervised-live-acceptance/03-DEPLOY.md` (634 lines) — safe-order deploy procedure, GO gate, rollback anchors, four-timestamp evidence table

**Runbook opening** (gal-02 lines 1-7) — states what artifacts the runbook sits beside and which tests pin it:

```markdown
# GAL-02 handoff runbook: STACK -> F.A.S.T. -> STACK (simulation only)

This runbook sits beside the protocol `docs/runbooks/gal-02-handoff.protocol.json`. The protocol is
checked by `tools/tests/gal02_handoff_test.py` and `tools/tests/gal02_replay_test.py` (offline), and
this runbook by `tools/tests/gal02_runbook_test.py`. It covers Phase 6 requirements ...
```

For `gal-07`: the H1 becomes `# GAL-07 live handoff runbook: STACK -> F.A.S.T. -> STACK (live, supervised)`; it references `docs/runbooks/gal-07-live-check.sh` and `tools/tests/gal07_live_runbook_test.py`, and pins LIVE-08/09/10.

**Safety-rules section** (gal-02 lines 9-18) — a bullet list of absolute prohibitions; the live version inverts the host rule and adds the never-delete clauses:

```markdown
## Safety rules

- Simulation only. Nothing in this runbook moves hardware.
- Nothing targets 10.150.1.125 or stack-server before Phase 7.
- ...
- Credentials come only through the sourced sim env files. They are never typed into this runbook, the
  Findings log or shell history.
- ...
- A ledger file is never deleted (Phase 5).
```

Live-version bullets (D-01/D-02/D-04/D-05/D-07/D-11 + RESEARCH Pattern 3): host is **exactly** `10.150.1.125:5005` (never the forb01-local :5005 container, never `stack-server` as the config string); stack-mcp closed (lock probe enforces); state file and ledger file **never deleted** (missing state reads as a clean start and silently clears a latch); recovery is acknowledge-after-inspection via the **stack-manager UI** (`http://10.150.1.125:5005`, D-02 primary) with the `AcknowledgeFailure` tool-page command as fallback — **never** restart-to-reset; credentials only via the operator's 0600 env file, never printed.

**Hardware preflight section** (gal-02 lines 264-285) — the pre-flight is runbook-embedded, gated on the exact config string, and records into a findings row:

```markdown
### Hardware-refusal preflight

Stop the run if any item fails (D-10). The host string comes from the Config form, so check it first:

```bash
HOST=127.0.0.1   # the exact string you will type into the Config host field
case "$HOST" in
  10.150.1.125|stack-server) echo "REFUSED: $HOST is the real STACK"; false ;;
  *) echo "host ok: $HOST" ;;
esac
```

Then confirm each of these, and record the result in Findings row 2b-0:
- ...
- `curl -fsS http://127.0.0.1:$STACK_SIM_PORT/api/general/application` reports productName "Stack manager"
  and productVersion 0.12.0-beta.1+1157;
- GetRobotStates from the STACK-PACSIM tool page lists only names starting `sim-` ...;
- GetManagerState is automated and the robot sim-arm-1 is idle (SAL A.3).
```

Live version: the case-match **requires** `10.150.1.125` (inverted); identity check goes to `http://10.150.1.125:5005/api/general/application` (verified this session → `{"productVersion":"0.12.0-beta.1+1157","productName":"Stack manager",…,"computerInfo":"stack-server"}`); `GetRobotStates` must list `stack2-6` idle; `GetManagerState` automated with recovery null. Then run `bash docs/runbooks/gal-07-live-check.sh` and require its final `PREFLIGHT OK` / `DEP-02 OK`.

**GO gate (typed go-ahead)** — v1 03-DEPLOY.md lines 217-228:

```markdown
## Go-ahead (D-03)

**Decision:** Deploy the live-control stack now, in the safe order of this document's
Runbook (D-05): core `b30b38d` into the service `.venv`, restart `galago-tools`, then ...
**Who:** The user (operator), in this session.
**When:** 2026-10-14, after reviewing the Entry gate (D-01) results and the Pre-deploy
record (D-04) above ...
**Reply:** literal `go`.
```

Plus the live re-check immediately before Step 1 (v1 lines 236-243): re-run the pre-flight, re-check `GET /api/runs` has no `RUNNING` run, record the UTC timestamp. D-10: one such gate per live event (deploy, LIVE-09, LIVE-10) — no auto-advance.

**Safe-order deploy steps** — v1 03-DEPLOY.md lines 250-324, each step = Command / Check / "Do not continue unless". Step 1 (install + discriminating check), STACK version per RESEARCH Code Example §Step-1:

```bash
# Source: v1 03-DEPLOY.md Step 1 pattern; pin from tools/stack/requirements.txt:2
cd /home/formulatrix/data/nikko/galago-tools
~/.local/bin/uv pip install --dry-run --python .venv/bin/python -r tools/stack/requirements.txt  # preview: only stack-automation-layer changes
~/.local/bin/uv pip install --python .venv/bin/python -r tools/stack/requirements.txt
.venv/bin/python -c "import importlib.metadata as m, json; d = json.loads(m.distribution('stack_automation_layer').read_text('direct_url.json')); assert d['vcs_info']['commit_id'] == '934a621ece116a8b263897c1e9b62b57374f4ef3'"
.venv/bin/python -m unittest tools.tests.stack_test -v
```

```markdown
**Do not continue unless** both checks pass. If either fails: do not restart anything; stop
and report; reinstalling `76f8c3fe` happens only on the user's go-ahead (D-06).
```

(uv only, never pip — the service `.venv` is uv-managed; `bin/make deps` uses pip — never for the service venv.) The dry-run preview is the v1 D-04 pattern and doubles as the OQ-1 credential checkpoint probe (an auth failure here is the `checkpoint:human-verify`).

Step 2 (restart) checks (v1 lines 278-294): `systemctl --user is-active`, new `MainPID`, journal "Started …" with no traceback, `scripts/fast_status.py --port 40012` → `NOT_CONFIGURED`; STACK deltas per RESEARCH Pattern 2 step 4: record listener PIDs via `ss -ltnp` (a manager-page tool restart changes those, not `MainPID`) and **back up logs before the restart** (D-06).

Step 3 (rebuild, v1 lines 307-324):

```bash
docker tag galago-core-galago-web:latest galago-core-galago-web:rollback-pre-live04
TOOLBOX_PORT=11010 docker compose up -d --build
```

```bash
docker inspect galago-web --format='{{.Image}}'
curl -sf http://localhost:3010/api/health
curl -sf http://localhost:3010/runs
docker exec galago-web grep -rl Command_Transfer /app/gen-interfaces 2>/dev/null | head -1
```

Expected: a new image ID (v1 lesson, lines 379-393: a cache-hit rebuild produced a byte-identical image ID and BLOCKED the gate — if the rebuilt ID equals the rollback anchor, STOP for a user decision); `/api/health` 200; stack types in `/app/gen-interfaces`; container reaches `host.docker.internal:40012`.

**Rollback-anchors section** — v1 lines 211-215:

```markdown
### Rollback anchors

- galago-web pre-deploy image ID: `sha256:9ad9c64fee6baa7ea9351c7cfa03bceb8f0db7f974fabbb6865b1143948880ca`
- Service core pre-deploy (rollback target): `76f8c3fee41b0a2df3519aa74b022152df673824`
- Running adapter SHA (rollback target): `7c0ff7b953986bbc62221a14bad8b9594795b1f4`
```

**Recovery drill section** (D-11; extends gal-02's "If something goes wrong", lines 315-324): stop the session → read `~/.local/state/galago-tools/stack/stack-ledger.json` + `GetFailureLatch` from the STACK tool page → operator inspects the arm → clear via the stack-manager UI at `http://10.150.1.125:5005` with the recorded guid + `"yes"` arm-inspected decision. Restart-during-transfer wording from `tools/stack/server.py:245-251` (verbatim: `"tool restarted mid-transfer; inspect the arm; " "the core may not have latched "`) — reported as needing arm inspection, **never** replayed as SUCCESS.

**Reads-first parameter section** (RESEARCH Pattern 5): never hardcode hardware params — after Configure the operator runs `ListDevices`, `ListLabwareProfiles`, `GetLabwarePresence(robot=stack2-6)` from the STACK tool page and picks the device/deck/nest triples (known nests: `nest-1/deck1/A1`, `orange-nest/deck1/A1`, `rack/l1/A1`).

**Findings-log format** (gal-02 lines 358-366) — copy the table verbatim with new row IDs:

```markdown
## Findings log

Fill a row when its step is done. The Result is PASS or FAIL against the expectations above, and a FAIL
stops Part 2. Never paste a credential or token.

| Row | UTC timestamp | Requirement | Observation | Result |
|-----|---------------|-------------|-------------|--------|
| G0 | 2026-11-02, before 03:49:41Z | FLOW-02, FLOW-03, FLOW-04 | `bash docs/runbooks/gal-02-dep02-check.sh` exit 0, last line `DEP-02 OK`. ... | PASS |
```

v1's four-timestamp deploy-evidence table (03-DEPLOY.md lines 372-401) is the LIVE-08 order proof: each row carries `Started`/`Completed` UTC timestamps and the summary asserts strictly-increasing order (`step 1 check passed … < step 2 … < step 2b … < step 3 …`).

---

### `tools/tests/gal07_live_runbook_test.py` (test, batch — offline fixture tests + text pins)

**Analog:** `tools/tests/gal02_runbook_test.py` (443 lines); helper `skip_or_fail` from `tools/tests/gal02_harness.py:102-106`

**Module skeleton** (gal02 lines 1-21) — docstring naming what is proven, stdlib imports, repo-relative paths as module constants:

```python
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
```

For `gal07`: `RUNBOOK_PATH = ... / "gal-07-live-handoff.md"`, `GATE_PATH = ... / "gal-07-live-check.sh"`.

**Gate-run harness** (gal02 lines 147-162) — POSIX-tool skip, subprocess with env overrides, stdout-lines helper:

```python
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
```

**Fixture-tree builder + falsification tests** (gal02 lines 76-134, 164-196) — build minimal fixture trees with per-piece kwargs, assert `BLOCKED:` last line on each single missing piece and exactly one `missing:` line, and the `OK` line on a complete tree:

```python
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
```

For `gal07` the fixtures are the live preconditions: bad host string (e.g. `127.0.0.1` or `stack-server` in the stored config → BLOCKED), held lock (pre-create + `flock` a fixture lock file → BLOCKED with the holder record), missing/pinned-wrong core in the venv tree, store missing the FAST tool, manager identity mismatch. The live script must therefore accept env overrides for each check's target (e.g. `GALAGO_WEB_URL`, `STACK_HOST`, lock-dir override) exactly as the DEP-02 gate accepts `GALAGO_CORE_DIR`.

**Read-only proof tests** (gal02 lines 327-362) — the gate script must be byte-identical before/after runs (sha256+mtime snapshot) and leave the repo's `git status --porcelain` unchanged:

```python
    def test_dep02_gate_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_core_tree(root)
            before = _snapshot(root)
            self._run(root)
            self._run(root)
            after = _snapshot(root)
        self.assertEqual(before, after)
```

(`_snapshot` is gal02 lines 137-144: relative path → `(sha256, mtime_ns)` for every file under root.)

**Runbook text pins** (gal02 lines 384-439) — headings present and in order; required phrases; findings rows exist; **no credential values**:

```python
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
```

For `gal07`: REQUIRED_HEADINGS ≈ safety rules, per-event GO gates, recovery drill, never-delete clauses, findings log (per RESEARCH Validation Architecture row "LIVE-08 (runbook text)"); REQUIRED_PHRASES ≈ `10.150.1.125`, `stack2-6`, `gal-07-live-check.sh`, `PREFLIGHT OK`/`BLOCKED:`, `REPLAY_WINDOW_S`, the restart-warning phrase from `server.py:245-251`, `GetFailureLatch`, stack-manager-UI recovery route. Reuse `skip_or_fail` (gal02_harness.py:102-106) for any environment-dependent skip so `GAL02_REQUIRE_ALL=1` (rename/reuse per planner) turns hidden skips into failures. Module must run under both `python -m unittest` and pytest (plain `unittest.TestCase` classes).

---

### `scripts/stack_status.py` (optional, utility, request-response) — planner's call

**Analog:** `scripts/fast_status.py` (55 lines, read whole). Research A5 says no new script is needed (`fast_status.py --port 40012` already works — the ToolDriver GetStatus RPC is tool-generic). If the planner wants a thin alias for runbook ergonomics, copy the entire structure:

```python
# scripts/fast_status.py:2-13 — the read-only contract is load-bearing (T-03-03: safe against
# a live instrument at any time); an alias must keep it verbatim
"""Read-only tool-health printer (D-04, D-05 steps 1-2, Phase 3 LIVE-04).

Calls GetStatus on a running tool server's ToolDriver gRPC service -- the same
heartbeat RPC galago-core already polls -- and prints one JSON line with the
reply. This script sends no command and no configuration: it never calls
ExecuteCommand or Configure, and must never be changed to do so ...

Usage:
    .venv/bin/python scripts/fast_status.py [--host HOST] [--port PORT] [--timeout SECONDS]
"""
```

Core body (lines 34-51): `grpc.insecure_channel` → `tool_driver_pb2_grpc.ToolDriverStub(channel)` → `stub.GetStatus(empty_pb2.Empty(), timeout=args.timeout)`; on `grpc.RpcError` print `{"port": ..., "error": e.code().name}` and return 2; success prints one JSON line with `status`/`uptime`/`error_message`/`run_state` and returns 0.

## Shared Patterns

### Exit-code gate contract (applies to the pre-flight script and its tests)
**Source:** `docs/runbooks/gal-02-dep02-check.sh:11,20,26,126-131`
**Apply to:** `docs/runbooks/gal-07-live-check.sh`
`set -u` (never `set -e` — every check runs so the operator sees all failures at once); per-check `missing:`/`forbidden:`/`BLOCKED:` lines; exit 0 ends with the `OK` verdict line, exit 1 ends with a `BLOCKED:` line naming the remedy. Environment-overridable paths for fixture testing.

### Read-only / no-secrets contract (applies to every script and runbook command)
**Source:** `docs/runbooks/gal-02-dep02-check.sh:7-9`; `scripts/fast_status.py:5-10`; `tools/tests/gal02_runbook_test.py:327-362,437-439`
**Apply to:** `gal-07-live-check.sh`, `gal-07-live-handoff.md`, `gal07_live_runbook_test.py`
Scripts write no file and mutate no state (proven by snapshot tests); the manager GET is identity-only (no motion); credentials appear only as presence checks (`grep -c '^STACK_USER=' file` — Phase 6 D-09 pattern), never as values in runbook, logs, or shell history.

### Per-event GO gates + findings rows (applies to all three live events)
**Source:** v1 `03-DEPLOY.md:217-228` (typed `go`, who/when/reply), `:372-401` (four strictly-increasing UTC timestamps); `docs/runbooks/gal-02-handoff.md:358-366` (Row / UTC timestamp / Requirement / Observation / Result)
**Apply to:** `gal-07-live-handoff.md` — deploy, LIVE-09, LIVE-10 each get a literal-typed-`go` gate recorded with a UTC timestamp (D-10); a FAIL row stops the session (D-14 route: stop → fix → gate → redeploy → rerun, never silent pass).

### Fail-closed never-delete / never-restart-to-recover (applies to runbook + pre-flight)
**Source:** `docs/runbooks/gal-02-handoff.md:18,349`; RESEARCH Patterns 3-4; `tools/stack/server.py:245-251` (restart warning verbatim)
**Apply to:** `gal-07-live-handoff.md` recovery sections and `gal-07-live-check.sh` (the probe reads, never deletes, lock/state files). Recovery = ledger read + `GetFailureLatch` → arm inspection → manager-UI acknowledge; restart-during-transfer is reported as "inspect the arm", never replayed SUCCESS.

### Core-pin verification via `direct_url.json` (applies to deploy Step 1 + pre-flight check d)
**Source:** v1 `03-DEPLOY.md:258-264`; `tools/tests/stack_test.py:1150-1172` (`TestRequirementsPin`); `tools/stack/requirements.txt:2`
**Apply to:** `gal-07-live-handoff.md` deploy step and the pre-flight's DEP-02-build assertion: `importlib.metadata.distribution('stack_automation_layer').read_text('direct_url.json')` → `vcs_info.commit_id == '934a621ece116a8b263897c1e9b62b57374f4ef3'`, then `.venv/bin/python -m unittest tools.tests.stack_test -v`. Install with uv only (`~/.local/bin/uv pip install --python .venv/bin/python …`), previewed with `--dry-run` first (also the OQ-1 credential checkpoint probe).

### Test-module conventions (applies to the new test file)
**Source:** `tools/tests/gal02_runbook_test.py` (whole file); `tools/tests/gal02_harness.py:102-106`
**Apply to:** `tools/tests/gal07_live_runbook_test.py`
Repo-relative `Path(__file__).resolve().parents[2]` constants; env-overridden `subprocess.run(["bash", GATE_PATH], …)` harness; fixture trees with per-piece kwargs + `subTest` for one-missing-piece matrix; `_snapshot` read-only proof; text-pin class reading the runbook once in `setUpClass`; `skip_or_fail` so `*_REQUIRE_ALL=1` promotes skips to failures; runs under unittest and pytest; no pytest fixtures, no network.

## No Analog Found

None — every planned artifact has a proven, fixture-tested analog in-repo (the Phase 6 triple + the v1 deploy runbook). The only genuinely new *content* is the live pre-flight's inverted host assertion, the owner-lock probe (RESEARCH Pattern 1 supplies the verified code), and the D-12 store check (one-line `jq` assertion, RESEARCH Code Examples) — all specified in RESEARCH.md, none requiring an in-repo analog.

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| — | — | — | No uncategorized files remain |

## Metadata

**Analog search scope:** `docs/runbooks/`, `tools/tests/`, `scripts/`, `.planning/milestones/v1-phases/03-deploy-supervised-live-acceptance/`, `tools/stack/`
**Files scanned:** 4 analogs read in full (gal-02-dep02-check.sh, gal-02-handoff.md, gal02_runbook_test.py, fast_status.py) + v1 03-DEPLOY.md (targeted sections) + gal02_harness.py (helper) + stack_test.py/requirements.txt (pin-check confirmation)
**Tracked-source gate:** all named analogs verified git-tracked via `git ls-files` (including `.planning/milestones/.../03-DEPLOY.md`)
**Pattern extraction date:** 2026-11-02
