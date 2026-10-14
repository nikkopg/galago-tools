# Phase 3: Deploy & Supervised Live Acceptance - Pattern Map

**Mapped:** 2026-10-14
**Files analyzed:** 5 (artifacts this phase produces or may touch)
**Analogs found:** 4 / 5

This phase ships almost no production code. The planner's job is to assign per-wave *documents*
(runbook, acceptance log) and, if Open Question 1 is resolved by building it, one throwaway
dry-run harness script. There is no controller/service/component churn — classification below
reflects that reality rather than forcing a web-app taxonomy onto an ops phase.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|-----------------|---------------|
| `03-DEPLOY.md` (runbook) | config/doc (ops runbook) | batch (sequential steps with checks) | `.planning/phases/03-.../03-CONTEXT.md` §"Deploy procedure (LIVE-04)" (D-03..D-06) — the decisions already enumerate the exact step/check/rollback shape to transcribe | exact (content already drafted in CONTEXT.md; runbook is a transcription + an evidence table) |
| `03-ACCEPTANCE.md` (evidence log) | test (acceptance record) | event-driven (one row per live scenario observation) | `.planning/phases/02-wait-through-pauses-on-the-pinned-core/02-VERIFICATION.md` and `02-VALIDATION.md` — existing phase-evidence doc structure in this repo | role-match |
| one-off `.venv` capability check (D-05 step 1) | test / utility (verification script) | request-response (import + assert, no network) | `tools/tests/fast_test.py` `TestRequirementsPin` (lines 3405-3470) | exact — Pitfall 3 in RESEARCH.md says invoke these methods directly, don't hand-roll |
| dry-run harness script (Open Question 1, if built) | utility / service bootstrap (throwaway, not gated) | event-driven (stdin-driven loop calling an in-process method) | `tools/fast/server.py` `__main__` block (lines 991-998) + `simulate_pause` (lines 610-625) + `tools/base_server.py` `serve()` (lines 296-310+) | role-match (compose existing pieces; no single file already does this) |
| per-scenario operator checklist (embedded in plans, D-08/D-09) | doc (procedure) | request-response (operator-driven steps, Claude observes) | CONTEXT.md D-08..D-12 (scenario order, pass criteria, exact wording) | exact — content is already fully specified; planner copies verbatim |

## Pattern Assignments

### `03-DEPLOY.md` (ops runbook, batch/checked-steps)

**Analog:** `03-CONTEXT.md` decisions D-03 through D-06 (this phase's own CONTEXT.md — the
runbook is not reverse-engineered from code, it is transcribed from locked decisions).

**Structure to copy** — "step, exact command, check, rollback" triples, in this order:

```text
Pre-deploy checks (D-04):
  - queue idle (galago-core UI / API)
  - instrument idle: read-only GetStatus
  - record current SHAs: service .venv core 76f8c3fe, galago-tools HEAD, galago-core HEAD,
    running galago-web image ID (git rev-parse HEAD + docker image inspect at deploy time)

Step 1 — core into .venv (D-02, D-05.1):
  command: ~/.local/bin/uv pip install --python .venv/bin/python \
    "git+file:///home/formulatrix/data/nikko/fast/fast-mcp@b30b38df48e8480f325228145ccae7915a56e437"
  check: direct_url.json commit_id == b30b38d...; run TestRequirementsPin's two methods
         against .venv/bin/python (see Shared Pattern "capability gate check" below)

Step 2 — restart galago-tools (D-05.2):
  command: systemctl --user restart galago-tools
  check: systemctl --user is-active galago-tools; journalctl --user -u galago-tools (clean);
         tool reachable on :40001; health GetStatus returns run_state (read-only)

Step 3 — rebuild galago-web (D-05.3):
  command: cd <galago-core>; TOOLBOX_PORT=11010 docker compose up -d --build
  check: docker ps shows container Up; run page loads; F.A.S.T. tool shows control bar capability

Rollback (D-06, reverse order):
  1. previous galago-web image/checkout
  2. previous galago-tools checkout + restart
  3. core 76f8c3f into .venv (uv pip install, same command shape as step 1, prior SHA)
  NEVER roll the core back while the new UI/adapter are still running.
```

Source for the exact commands (verbatim, verified against the live host this session):
`.planning/phases/03-deploy-supervised-live-acceptance/03-RESEARCH.md` §"Code Examples" (lines
441-476) — copy these command blocks into `03-DEPLOY.md` rather than retyping them.

---

### `03-ACCEPTANCE.md` (evidence log)

**Analog:** `.planning/phases/02-wait-through-pauses-on-the-pinned-core/02-VERIFICATION.md` /
`02-VALIDATION.md` — existing convention in this repo for recording phase-level pass/fail
evidence against requirements.

**Row shape to copy** (per D-13, one block per scenario):

```markdown
### LIVE-06a: Pause -> Resume -> SUCCESS
- Date/time:
- Operator:
- Transfer parameters: (plates/wells/volume per D-10)
- Decisions chosen: (tip intact yes/no, return liquid yes/no, as applicable)
- Journal excerpt: (journalctl --user -u galago-tools, relevant lines only)
- Final step result / queue state:
- Screenshot(s): (run page / modal, if available)
- Pass/Fail against D-11 criteria:
```

Repeat per scenario in D-09 order (LIVE-06a, LIVE-05, LIVE-06b, LIVE-07). LIVE-04 (the deploy
itself) gets its own block fed from the D-05 step checks rather than a live scenario.

---

### `.venv` capability gate check (D-05 step 1's check)

**Analog:** `tools/tests/fast_test.py` lines 3405-3470, `TestRequirementsPin`.

**Imports pattern** (top of `fast_test.py`, already in repo — reuse, don't re-type):
```python
import importlib.metadata
import json
from dataclasses import fields
from typing import Any, cast
from unittest.mock import MagicMock
```

**Core pattern to invoke, not hand-copy** (lines 3422-3466):
```python
def test_installed_core_has_wait_through_pauses_and_pause_info(self) -> None:
    option_fields = {f.name: f for f in fields(RunOptions)}
    self.assertIn("through_pauses", option_fields)
    self.assertIs(option_fields["through_pauses"].default, False)
    self.assertIn("on_pause", option_fields)
    self.assertIsNone(option_fields["on_pause"].default)

    self.assertEqual(PauseInfo.__module__, "fast_mcp.orchestration")
    info = PauseInfo(error_code=-645, error_name="WrongPlateType", percent=0,
                      event_payload={"k": 1})
    self.assertEqual(set(info.to_dict()), {"errorCode", "errorName", "percent", "eventPayload"})
    ...

def test_installed_core_refuses_pause_resume_abort_while_idle(self) -> None:
    transport = MagicMock()
    transport.get_status.return_value = {"currentState": "idle"}
    core = _real_core(self, transport)
    pause_result = core.pause(hard=False)
    self.assertIsInstance(pause_result, Refused)
    ...
```

**How the runbook invokes this (Claude's Discretion resolution):** run it as a `unittest`
invocation against the freshly-pinned interpreter, not a copied script:
```bash
$HOME/data/nikko/.venvs/galago-py310/bin/python -m unittest \
  tools.tests.fast_test.TestRequirementsPin -v
```
(RESEARCH.md "Quick run command", confirmed this avoids Pitfall 3 — copy-paste drift between a
one-off deploy script and the gated test.)

---

### Dry-run harness script (Open Question 1 — if the plan decides to build it)

**No single existing analog** — this is genuinely new, composed from three existing pieces.
Treat `tools/fast/server.py`'s own process-entry pattern as the shape to imitate, with the
`simulate_pause` hook substituted for the normal gRPC command surface.

**Server bootstrap pattern** (`tools/fast/server.py` lines 991-998, the `__main__` block):
```python
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser()
    parser.add_argument("--port")
    args = parser.parse_args()
    if not args.port:
        raise RuntimeWarning("Port must be provided...")
    serve(FastServer(), str(args.port))
```
The harness should mirror this (argparse a spare port, e.g. `--port=40099`), but set
`simulated=True` on the `FastServer` instance before calling `serve(...)`, and run `serve(...)`
in a background thread so the main thread can read stdin.

**Hook to drive from the harness's stdin loop** (`tools/fast/server.py` lines 610-625,
verbatim — call this directly on the live Python object, never over gRPC):
```python
def simulate_pause(self, pause: Optional[dict[str, Any]]) -> None:
    if not self.simulated:
        raise RuntimeError("simulate_pause is only available in simulated mode")
    if pause is None:
        self._clear_pause()
    else:
        self._record_pause(_DictPauseInfo(pause))
```

**`serve()` signature to reuse unchanged** (`tools/base_server.py` lines 296+):
```python
def serve(tool_server: 'ToolServer', port: str, num_workers: int = 10) -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=num_workers))
    tool_driver_pb2_grpc.add_ToolDriverServicer_to_server(tool_server, server)
    ...
```

**Placement:** per RESEARCH.md Pitfall 2, this must be a throwaway script — either untracked
under a scratch path or, if kept, clearly labeled under something like `scripts/dryrun/` — and
must **never** modify `tools/base_server.py` or `tools/fast/server.py` (explicit phase boundary
and Anti-Pattern in RESEARCH.md). It is not a gated test file and does not go through
`bin/make proto test`.

---

### Operator checklists (per-scenario, D-08/D-09/D-11/D-12)

**Analog:** CONTEXT.md decisions, already fully worded — no codebase analog needed; this is a
direct transcription task.

**Shape to copy per scenario:**
```text
Setup (no motion): <protocol/queue prep, e.g. D-10 transfer params>
Checklist:
  [ ] Operator present at instrument, e-stop within reach
  [ ] Claude has prepared <setup>, no motion yet
  -- STOP: wait for operator's explicit go-ahead before each motion-affecting step --
  [ ] Operator starts the run
  [ ] Operator sends Pause  -> Claude watches journalctl + run page, records what it sees
  [ ] Operator sends Resume/Abort (per scenario) -> Claude records outcome
Pass criteria: <copy verbatim from D-11 for this scenario>
```

## Shared Patterns

### Capability/state-gate verification (reuse, never hand-roll)
**Source:** `tools/tests/fast_test.py` `TestRequirementsPin` (lines 3405-3470)
**Apply to:** The D-05 step 1 check in `03-DEPLOY.md`, and any gap-fix re-verification after D-14.
Invoke via `unittest`, do not copy the assertions into a new script (Pitfall 3).

### Exact wording strings (do not retype from memory — grep and paste)
**Source:** `tools/fast/server.py:350` — `f"run aborted by operator at {result.percent}%"`
**Apply to:** `03-ACCEPTANCE.md` LIVE-06b pass criteria and any pre-check grep step in
`03-DEPLOY.md`/plan must_haves.

### Safe-order deploy with check-gate per step
**Source:** CONTEXT.md D-05 (already the authoritative sequence); RESEARCH.md Pattern 1.
**Apply to:** `03-DEPLOY.md` structure and the first plan's must_haves — never advance to the
next deploy step without the prior step's check passing.

### D-01 entry gate as a live checkpoint
**Source:** CONTEXT.md D-01 (four conditions) + RESEARCH.md Pitfall 1.
**Apply to:** The first task of the first plan in this phase — a `checkpoint:human-verify`-style
gate that re-checks all four conditions at execution time, not planning time, and stops cleanly
if any still fail (as of 2026-10-14 condition 1 is not met).

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| Dry-run harness script (Open Question 1) | utility | event-driven | No existing script in either repo drives `simulate_pause` outside `unittest` (RESEARCH.md: "repo-wide grep, this session — only hit is the test file and docstrings"); composed from three existing building blocks above rather than copied from one analog |

## Metadata

**Analog search scope:** `tools/tests/fast_test.py`, `tools/fast/server.py`, `tools/base_server.py`,
`.planning/phases/01-*`, `.planning/phases/02-*` (existing phase-evidence docs), this phase's own
`03-CONTEXT.md`/`03-RESEARCH.md`.
**Files scanned:** ~8 (targeted, no full-file reads beyond what RESEARCH.md had already verified
with line numbers).
**Pattern extraction date:** 2026-10-14
