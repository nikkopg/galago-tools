# Phase 5: F5-safe Transfer & Operator Acknowledge - Research

**Researched:** 2026-10-29
**Domain:** Idempotent motion command (persisted step-key ledger) over the pinned STACK core `934a621`, plus operator latch read/acknowledge, in a gRPC tool adapter
**Confidence:** HIGH (every core claim was read at `934a621` and the load-bearing ones were re-run against the real core in this session; see "Design Spike Findings")

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

(Copied verbatim from `05-CONTEXT.md` `## Implementation Decisions`.)

#### Design spike first (roadmap note)
- **D-01:** Plan 05-01 is a short written design spike, `05-SPIKE.md`, checked against core
  `934a621` (read with `git show 934a621:<path>` in `~/data/nikko/stack-automation-layer`). It
  confirms or amends D-05..D-12 before any code is written. It must answer:
  - **Restart mid-transfer (limit 1):** after a restart, does `wait_transfer(guid)` on a guid the
    restarted core does not own still observe `ran`/`failed` from STACK? Does a failure then latch
    or not? (D-09)
  - **Latch guid for `Lost(submitOutcomeUnknown)`:** is `latch_status().guid` the `submit-<hex>` id
    immediately after `execute_transfer` returns? (D-13)
  - **Failures that prove nothing was sent:** which `execute_transfer` results prove that? The
    working list is `Refused(*)`, `Rejected`, `NeedsInput`, `ReadFailed`, and `Lost` only with
    `submitOutcomeUnknown`.

  If the spike finds a core gap that blocks the phase, the work stops and the gap goes to a
  `/gsd-quick` in stack-automation-layer (PROJECT.md rule). The adapter does not work around it.

#### Ledger storage (XFR-02)
- **D-02:** The ledger is one JSON document, `stack-ledger.json`, inside the ledger directory:
  - top-level `{"version": 1, "records": {<step_key>: <record>}}`;
  - writes are atomic and mirror the core's `StateStore`: temp file, `fsync`, `os.replace`, then
    `fsync` of the directory;
  - the directory is mode 0700 and the file 0600;
  - every read-modify-write is serialised by an `fcntl.flock` on a sibling lock file, so two tool
    servers sharing a directory cannot interleave.

  The adapter applies no instrument rule here; this is pure bookkeeping.
- **D-03:** Ledger directory:
  - `Config.ledger_dir` when non-blank. It must be absolute; a relative path fails `Configure` with
    a `ValueError`.
  - Otherwise `$XDG_STATE_HOME/galago-tools/stack` (only if that variable is absolute).
  - Otherwise `~/.local/state/galago-tools/stack`.
  - Never under `/tmp`.

  `Configure` resolves and validates the path but creates nothing. The directory and file are
  created on the first write-ahead record.
- **D-04:** Fail closed on the ledger, mirroring the core's state file:
  - An unreadable or corrupt ledger, or one with an unknown version, refuses every real-mode
    `Transfer` with `ERROR_FROM_TOOL`. The message names the path and says "do not delete it". The
    ledger is never treated as empty and is never auto-deleted or rewritten.
  - A missing file is a clean start.
  - A write-ahead write that fails refuses the `Transfer` before `execute_transfer`, so nothing is
    sent.
  - If a later write fails (the guid or the terminal outcome), the adapter keeps waiting, because a
    repeat finds `submitting`/`started` and refuses or re-attaches, which is safe. The step then
    ends `ERROR_FROM_TOOL` with "transfer <kind>, but the ledger could not record it", even when
    the result was `ran`.

#### Record shape and fingerprint (XFR-02, XFR-03)
- **D-05:** A record holds:
  - `fingerprint`;
  - `state`: one of `submitting` | `started` | `done` | `outcomeUnknown`;
  - `instance`: a uuid minted once per `StackServer`, used for restart detection in D-09;
  - `handle`: the core's `TaskHandle.to_dict()` once known;
  - `result`: the terminal `to_dict()` once known;
  - `createdAt` / `updatedAt`: wall-clock ISO timestamps.

  Writes happen in this order:
  1. `submitting`, after `plan_transfer` returns a `TransferPlan` and before `execute_transfer`;
  2. `started` with the handle, as soon as `execute_transfer` returns a `TaskHandle`;
  3. `done` with the result, at a terminal result other than `timedOut`.
- **D-06:** The fingerprint is the sha256 of canonical JSON (sorted keys, `None` for unset) of the
  core endpoint key (`endpoint_key(host, port)`) and the `TransferRequest` fields: robot, labware
  profile, and the source and destination device/deck/nest/transfer_profile. It excludes `step_key`
  and `timeout_s`.

  The same key with a different fingerprint is `INVALID_ARGUMENTS`, with no core call (XFR-03). This
  includes the same request on a different STACK.
  — **Reversibility:** costly — a fingerprint change makes every existing record mismatch, so it
  needs a ledger `version` bump and a migration rule.

#### Repeat-key state machine (XFR-03, XFR-04, XFR-06)
- **D-07:** On every real-mode `Transfer`, the adapter takes the motion lock and loads the ledger.
  The record found for the `step_key` decides what happens:

  | Record found | Action | Reply |
  |---|---|---|
  | none | Fresh path: `plan_transfer` → `submitting` → `execute_transfer` → `started` → `wait` → `done` | per D-10 mapping |
  | `submitting` (no guid) | Refuse, no core call | `ERROR_FROM_TOOL`: outcome unknown; check the STACK Manager and the latch (`GetFailureLatch`); this step key will not be re-sent |
  | `outcomeUnknown` | Refuse, no core call | `ERROR_FROM_TOOL` naming the recorded latch guid (`submit-<hex>`) |
  | `started` (guid, no terminal) | Re-attach: `wait_transfer(guid)` until terminal or timeout (D-11) | per D-10; then record `done` |
  | `done`, `ran`, within `REPLAY_WINDOW_S` | Replay, no core call | `SUCCESS`, empty message, meta `{result, stepKey, replayed: true}` |
  | `done`, `ran`, older than the window | Refuse, no core call | `ERROR_FROM_TOOL`: step key already completed at <time>; the protocol must mint a new key per run |
  | `done`, any non-`ran` terminal (`failed`/`aborted`/`lost`/`cancelled`) | Refuse, no core call | `ERROR_FROM_TOOL` repeating the recorded kind, reason and guid: acknowledge the latch after inspecting the arm, then run the step under a new key (a new run) |

  `REPLAY_WINDOW_S = 600` (F5 repeats arrived within ~1 s; 10 min is generous and still short).
- **D-08:** Releasing a key (XFR-04): the record is **deleted** after any outcome that proves
  nothing was sent, so the operator can fix the cause and re-run the same step.
  - Before the write-ahead: `plan_transfer`'s `Rejected`/`NeedsInput`/`ReadFailed`/`Refused` leave
    no record at all.
  - From `execute_transfer`: `Refused(*)` (incl. `planNotFound`/`planExpired`/`failureLatched`/
    `inFlight`/`stackBusy`), `Rejected`, `NeedsInput` and `ReadFailed` delete the record.
  - From `execute_transfer`: `Lost(submitOutcomeUnknown)` sets `outcomeUnknown` (permanent).
  - From `execute_transfer`: any exception leaves `submitting` (permanent, so the key refuses).

  The D-01 spike confirms this list. Acknowledging a latch never releases or edits a ledger record.
  The adapter has no command to clear a record, and adding one would need a proto change, which is
  out of scope.
- **D-09:** Restart mid-transfer (XFR-03, core limit 1): a `started` record whose `instance`
  differs from the current server's is a re-attach **across a restart**. The adapter still
  re-attaches read-only with `wait_transfer`, then:
  - `ran` is reported as SUCCESS. It is STACK's own observation, not a replay, and meta adds
    `reattachedAfterRestart: true`.
  - Every other outcome is `ERROR_FROM_TOOL` with an added clause: "tool restarted mid-transfer;
    inspect the arm. The core may not have latched this failure". The clause also carries the
    current `latch_status()` guid, if any.

  A `submitting` record after a restart is refused under D-07 with the same arm-inspection wording.
  A `done` record is never re-observed.
  The D-01 spike either confirms this rule or tightens it (for example, refusing SUCCESS after a
  restart). If it tightens it, the spike's version wins and the change is noted in the spike.

#### Reply mapping and messages (XFR-01)
- **D-10:** This decision extends Phase 4 D-10..D-12:
  - `ran` is SUCCESS with an empty message. Every other terminal kind is `ERROR_FROM_TOOL` with the
    one-line message (kind, reason, guid, hint), and meta is `to_dict()`.
  - A blank `step_key` is `INVALID_ARGUMENTS` before any core call or ledger read. This is already
    in `_check_args`.
  - `latchStatus` joins `_SUCCESS_KINDS`, and the result-mapping test gains it.
  - Ledger-generated replies (replay, refusals) use adapter-owned meta
    `{stepKey, ledgerState, result?, replayed?}` outside the contract shape.

#### Wait and timeout (XFR-01, XFR-06)
- **D-11:** The wait budget for a call is `T` = the first of these that is set:
  1. `Transfer.timeout_s` (when set and > 0);
  2. `Config.transfer_timeout_s` (when > 0);
  3. `DEFAULT_TRANSFER_TIMEOUT_S = 300`.

  How the adapter waits:
  - **Fresh path:** one `service.wait(handle, timeout_s=T)`.
  - **Re-attach:** a read-only loop of `service.wait_transfer(guid, timeout_s=min(remaining, 300))`
    until a non-`timedOut` result or until `T` is used up. The core clamps each call to
    `WAIT_TRANSFER_MAX_S = 300`.

  Neither path ever stops or re-sends motion.
  `timedOut` leaves the record `started` and replies `ERROR_FROM_TOOL` ("still running; re-run this
  step to re-attach"). Re-running the step re-attaches and finishes (XFR-06).

#### Concurrency
- **D-12:** A non-blocking, module-level motion lock (fast D-13 pattern) wraps the whole `Transfer`
  (ledger load → terminal write). A second `Transfer` in the same process is refused at once with
  `ERROR_FROM_TOOL` "busy" and never parked. base_server's BUSY gate already serialises it, so the
  lock is a backstop. `Transfer` and `AcknowledgeFailure` stay out of `READ_COMMANDS`, while
  `GetFailureLatch` stays in it, so the latch is readable during a transfer.
  - `UNAVAILABLE_COMMANDS` is removed, along with its real-mode refusal.
  - `COMMAND_TO_SERVICE_METHOD` gains `GetFailureLatch` → `latch_status`.
  - `COMMAND_TO_SERVICE_METHOD` gains `AcknowledgeFailure` → `acknowledge_failure`.
  - `Transfer` is documented as the one multi-call command.

#### Operator acknowledge and latch read (ACK-01, ACK-02)
- **D-13:** `GetFailureLatch` returns `service.latch_status()` through `_result_reply`: SUCCESS and
  meta is `to_dict()` unchanged, covering the task-guid, `submit-<hex>` and `state-<hex>` cases.

  Every Transfer error reply whose cause can latch must name the guid to acknowledge. The causes
  are `failed`, `aborted`, `lost`, `Refused(failureLatched)`, an `outcomeUnknown` refusal, and a
  `stateUnreadable`/`stateUnsaved` latch. The guid comes from the result's own fields first, then
  from a zero-I/O `latch_status()` call made after the result, which is how the `submit-<hex>` id is
  found. The message reads along the lines of
  `stack: lost (submitOutcomeUnknown); latched guid submit-ab12…; inspect the arm, then AcknowledgeFailure`.
- **D-14:** For `AcknowledgeFailure`, the adapter does three things:
  - `arm_inspected` must be exactly `"yes"` to reach `acknowledge_failure(guid.strip(), confirm=True)`.
  - Anything else is `INVALID_ARGUMENTS` with no core call, including `"no"`, which the shared
    `_check_args` currently accepts. The message says "inspect the arm and recover STACK in the
    STACK Manager, then send yes".
  - The core result maps per D-10: `failureAcknowledged` is SUCCESS, while
    `Refused(guidMismatch|nothingLatched|recoveryPending)` and `NeedsInput` are `ERROR_FROM_TOOL`.

  Simulated mode still accepts `"no"`/`"yes"` as valid arguments (Phase 4 D-17) and sleeps.
  — **Reversibility:** reversible.
- **D-15:** No adapter path acknowledges, cancels, retries or goes to the safe position on its own.
  `acknowledge_failure` has exactly one call site, in the `AcknowledgeFailure` handler, after the
  `"yes"` check.

#### Safety invariant (XFR-05)
- **D-16:** The XFR-05 AST test over `tools/stack/` replaces Phase 4 D-20. Each check has a planted
  violation that must fail:
  - **Forbidden calls:** any call to `start_transfer`, `cancel_transfer`, `go_to_safe_position`,
    `wait_safe_position` or `validate_transfer`.
  - **`execute_transfer`:** exactly one call site. It is not inside any `for`/`while` loop or
    comprehension, and it sits in the fresh-path function after the write-ahead ledger write.
  - **`plan_transfer`:** exactly one call site.
  - **`acknowledge_failure`:** exactly one call site, in the `AcknowledgeFailure` handler.
  - **`wait_transfer`:** may sit in a loop, since it is read-only.

  A behavioural test adds a fake core that counts `execute_transfer` calls. It must stay at 1 for a
  key across every scenario: F5 repeat after `ran`, retry after failure, `timedOut` re-attach,
  `submitOutcomeUnknown`, an exception after the write-ahead, and a restart (a new `StackServer` on
  the same ledger dir).
  The D-21 no-`stack_automation_layer.mcp`-import test stays.

#### Tests
- **D-17:** All tests use `MagicMock(spec=StackService)` (or a small fake), built from the core's
  real result classes and a temp ledger dir. They never contact `10.150.1.125`/`stack-server`, and
  nothing moves.
  - Write the ledger state-machine tests first, one per D-07 row, plus D-04's fail-closed cases and
    D-09's restart case.
  - Re-prove STK-05 by blocking the fake `wait` on a `threading.Event` inside a real `Transfer`:
    reads and `GetFailureLatch` answer, a second `Transfer` is refused, and status returns to READY
    after release.
  - Simulated mode still never writes the ledger.

### Claude's Discretion

(Verbatim.)

- Whether the ledger lives in `tools/stack/ledger.py` or inside `server.py`. A separate module is
  preferred for testability.
- Exact message wording, within Phase 4 D-11 (one line, no core `explanation`).
- `REPLAY_WINDOW_S`, `DEFAULT_TRANSFER_TIMEOUT_S` and record retention values. They must stay
  constants. Suggested retention: prune `done` records older than 7 days on write; never prune
  `submitting`/`started`/`outcomeUnknown`.
- The exact ISO timestamp format, and whether the record stores the plan summary for operator
  display.

### Deferred Ideas (OUT OF SCOPE)

(Verbatim.)

- An operator command to clear or inspect a ledger record (for example, `GetStepRecord`). It needs a
  proto change, which re-opens DEP-02. Consider it for v3.
- A `run_state`-style STACK heartbeat on the health `GetStatus` (carried from Phase 4's deferred
  list).
- A runbook rule for the ledger dir: never delete it, and back it up before a restart. This lands
  with Phase 7's deploy runbook.
- Adapter refusal of `Configure` while a run is in flight (v2 Future Requirement, shared with F.A.S.T.).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| XFR-01 | `Transfer`: `plan_transfer` -> `execute_transfer` -> wait to terminal in one command | Verified end-to-end flow on the real core (probe 1: `TransferPlan` -> `TaskHandle` -> `ran`, 1 POST); `plan.plan_id` is the only handle `execute_transfer` takes; wait API contracts below |
| XFR-02 | Non-blank `step_key`; persisted atomic ledger; write-ahead `submitting`, then guid, then terminal | Ledger design (atomic claim under flock, lock-free decide), strict-parse fail-closed, core `StateStore` pattern quoted |
| XFR-03 | Repeat key never submits: re-attach / replay / refuse; different request -> `INVALID_ARGUMENTS`; restart reported as needing arm inspection | State machine, restart behaviour verified (probes a1-a3), **terminal-set amendment (A-1)**, fingerprint recipe |
| XFR-04 | Outcome proving nothing was sent releases the key | Spike answer (c) with evidence; residual risk on typed 5xx / `stackBusy` flagged |
| XFR-05 | Adapter never retries motion; AST invariant with planted violations | AST rule set, parent-map helper, existing Phase 4 helper to extend, tests that must change |
| XFR-06 | `TimedOut` leaves arm running, re-run re-attaches and finishes | Probe (d): `timedOut` leaves guid in-flight, re-attach `ran` clears it; re-attach loop details |
| ACK-01 | `AcknowledgeFailure`: only exact `"yes"` reaches `acknowledge_failure(guid, confirm=True)` | Core signature/semantics quoted; placement of the real-mode "yes" check; single call site |
| ACK-02 | Latched guid visible in message and via `GetFailureLatch` (`latch_status()`), incl. `submit-<hex>` and `state-<hex>` | `LatchStatus.to_dict()` shape quoted; probe (b); **guid-authority amendment (A-2)**; message-truncation pitfall |
</phase_requirements>

## Summary

The core at `934a621` supports the whole design; **no core gap blocks the phase**. The three D-01 spike questions are answered below with line citations and with executed evidence from the real `StackService` in the pinned 3.10 venv: (a) a foreign guid is still observed (`ran`/`failed`) but a foreign failure does not latch; an owned-after-restart guid does latch; (b) `latch_status().guid` is the `submit-<16 hex>` id immediately after `execute_transfer` returns `Lost(submitOutcomeUnknown)`; (c) `Refused(*)`, `NeedsInput` and pre-POST `ReadFailed` prove nothing was sent, but **`Rejected(stage="instrument")` after a typed HTTP error and `Refused(stackBusy)` are returned after exactly one POST was sent** (the STACK refused it), so "proves nothing was sent" is a core-policy statement, not a physical proof.

Two amendments to CONTEXT are recommended and need to be written into `05-SPIKE.md` (the spike's version wins per D-01/D-09): **A-1** the ledger's "terminal" set must follow the core's own `_task_ended` (ran, failed, aborted, `lost(taskNotFound)`); `lost(pollFailed)` must stay `started`, otherwise the core's persisted in-flight guard for that guid can never be cleared and every later Transfer is `Refused(inFlight)` forever (verified: `acknowledge_failure` does not clear `_inflight`). **A-2** the guid named to the operator must come from `latch_status()` first (it is exactly what `acknowledge_failure` must name; the result's own guid can differ because the latch is first-failure-wins), not from the result's fields first.

The work is mostly adapter-side bookkeeping plus a large test migration: a dozen Phase 4 tests encode "Phase 5 commands are refused" and must be rewritten. The ledger should be a core-free pure module (`tools/stack/ledger.py`) so its state-machine tests run without the private core installed.

**Primary recommendation:** Build `ledger.py` first as a pure, flock-guarded, strictly-parsed store with an atomic `claim` (create-if-absent under flock) and a `decide()` function covering the D-07 table; wire `Transfer` as one `_run_fresh` function holding the only `plan_transfer`/`execute_transfer` call sites; adopt A-1 and A-2 in `05-SPIKE.md` before any code.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Plan / submit / wait / latch / acknowledge semantics | Core (`StackService`) | — | PROJECT rule: adapter holds no instrument policy; every gate lives in the core |
| Step-key idempotency (ledger, fingerprint, replay window) | Adapter (`tools/stack/ledger.py`) | Filesystem | The core has no step key; this is the F5 defence and is adapter bookkeeping only |
| Reply mapping, one-line operator messages | Adapter (`server.py`) | — | Phase 4 D-10..D-12; galago-core only shows `ERROR_FROM_TOOL` text |
| "yes"-only acknowledge gate | Adapter (argument rule) | Core (`confirm=True`, exact guid, recovery read) | Adapter owns the argument contract; core owns the instrument decision |
| Reads during a Transfer (STK-05) | Adapter `ExecuteCommand` override | base_server BUSY gate (bypassed for `READ_COMMANDS`) | Phase 4 D-13 mechanism, unchanged |
| Serialisation of motion | base_server BUSY gate | Adapter module-level non-blocking lock (backstop) | D-12 |
| Persistence of failure latch / ownership / in-flight guard | Core `StateStore` (`STACK_STATE_DIR`) | — | Independent of the adapter ledger; two files, two directories |
| Operator recovery (arm inspection, STACK Manager) | Human / STACK Manager | — | Never automated |

## Standard Stack

### Core

No new external packages. Everything is the Python 3.10 standard library plus modules already imported by `tools/stack/server.py`.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `stack-automation-layer` | pinned `934a621ece116a8b263897c1e9b62b57374f4ef3` | the core: `StackService`, result classes, `endpoint_key` | already pinned by `tools/stack/requirements.txt` and `_PINNED_CORE_SHA` [VERIFIED: tools/tests/stack_test.py:1050 `_PINNED_CORE_SHA = "934a621ece116a8b263897c1e9b62b57374f4ef3"`; `test_installed_core_is_the_pinned_commit` passed in this session's 120-test run] |
| `json`, `os`, `tempfile`, `fcntl`, `hashlib`, `uuid`, `dataclasses`, `time`, `pathlib` | stdlib (py3.10.12) | ledger: atomic write, flock, fingerprint, instance id | mirrors the core's own `state_store.py` (imports `contextlib, json, os, pathlib, tempfile`) [VERIFIED: state_store.py:43-48 at 934a621] |
| `pytest` / `unittest` | pytest 7.4.3 | test runner | [VERIFIED: `python -m pytest --version` in galago-py310] |
| `ruff` 0.9.4, `mypy` 1.11.2 | in venv | part of the gate; mypy has `disallow_untyped_defs = "True"` so every ledger function needs full annotations | [VERIFIED: pyproject.toml:8-25, venv versions] |

### Supporting

None.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| hand-rolled JSON + flock | SQLite (`sqlite3`) | SQLite gives atomic upserts, but D-02 locks one JSON document mirroring the core's `StateStore`; keep D-02 |
| `fcntl.flock` | `fcntl.lockf` | `lockf` is a POSIX per-process lock: two threads in one process do NOT exclude each other and closing any fd drops the lock. `flock` is per open file description, so separate `open()` calls contend even in one process. Keep `flock` [ASSUMED: standard Linux semantics, not re-run here] |

**Installation:** none (`tools/stack/requirements.txt` is unchanged).

**Version verification:** the only versioned dependency is the core, verified against git: `git rev-parse HEAD` in `~/data/nikko/stack-automation-layer` returned `934a621ece116a8b263897c1e9b62b57374f4ef3` [VERIFIED: git].

## Package Legitimacy Audit

No external packages are installed by this phase (stdlib only; the core is already pinned by SHA from the internal GitLab and unchanged).

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | — | — | — | — | — | No install step |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Design Spike Findings (answers to D-01)

All line numbers refer to files at core `934a621`, read with `git show 934a621:<path>` and the `Read` tool this session. Executed probes ran against the real `StackService` in `~/data/nikko/.venvs/galago-py310` (scratch scripts under the session scratchpad, not committed; outputs pasted below). The core's own `tests/fakes.py` `FakeTransport` was extracted with `git archive` into the scratchpad for the end-to-end probe.

### (a) Restart mid-transfer: `wait_transfer` on a guid the core does not own

**Code:** `_reattach` looks the guid up in `_started`, and if absent builds a plain handle, because "a guid this service did not start still waits on a handle built with that `kind` (the read is harmless -- ownership only matters for a later cancel)" [VERIFIED: service.py:930-933]. `_wait` then latches only when `owned = handle.guid in self._started` [VERIFIED: service.py:2010-2016]:

```python
        with self._state_lock:
            owned = handle.guid in self._started
        will_latch = (
            owned
            and self._should_latch(result)
            and not self._relatch_suppressed(handle.guid, result)
        )
```

What is persisted: `_snapshot_locked` writes `started` only for `live = set(self._inflight)` plus the latch guid [VERIFIED: service.py:496-501], and `_restore` reinstalls `_started`/`_inflight`/`_latch` [VERIFIED: service.py:462-468]. So a guid that was `_inflight` (accepted by STACK and persisted) comes back **owned**; a guid whose process died between the POST and `_persist_locked` (limit 1), or one that finished without a latch (limit 2), comes back **foreign**.

**Executed evidence:**

```
--- (a1) FOREIGN guid (fresh service, empty store): wait_transfer observes failed, latch?
failed | latch_status: False
--- (a2) FOREIGN guid observes ran
ran | latch: False
--- (a3) OWNED-after-restart: persist inflight+started, new service, wait_transfer failed
restored inflight: {'11111111-2222-3333-4444-555555555555'} started: ['11111111-2222-3333-4444-555555555555']
failed | latch: True 11111111-2222-3333-4444-555555555555 | inflight after: set()
```

**Answer:** Yes, `wait_transfer` on a foreign guid still observes `ran`/`failed` from STACK (`get_transfer(guid)`). A foreign `failed` **does not latch**; an owned-after-restart `failed` **does**. D-09 is confirmed: after a restart the adapter cannot tell which case it is (`_started` is private), so the only honest wording is "the core may not have latched this failure", plus whatever `latch_status()` says after the wait.

**What still protects the next transfer when a foreign failure did not latch:** `_motion_gates` refuses unless the manager mode is automated: `if state.mode != "automated": return Refused(reason="managerNotAutomated", ...)` and refuses `robotNotIdle` unless the robot row reads `"idle"` [VERIFIED: service.py:1591-1592, 1600-1601]. These are core gates, not adapter policy; the adapter does not need its own rule.

**D-09 vs requirement wording (needs one user confirmation, see Open Question 1):** XFR-03 says a restart during a transfer "is reported as needing arm inspection, never replayed as SUCCESS". D-09 reports `ran` as SUCCESS after a restart because it is a live STACK observation (`completed`), not a ledger replay. The probe (a2) shows that observation is real. Recommendation: keep D-09 as written (SUCCESS for a live `ran`, with `reattachedAfterRestart: true` in meta); it never replays. If the user reads XFR-03 strictly, the tightening is one line (refuse SUCCESS when `instance` differs) and the spike should record whichever is chosen.

### (b) Is `latch_status().guid` the `submit-<hex>` id right after `execute_transfer` returns `Lost(submitOutcomeUnknown)`?

**Code:** `_submit_outcome_unknown`'s first statement mints and latches, before any read: `latch_id = "submit-" + secrets.token_hex(8)` then `self._set_latch(latch_id, "lost", "submitOutcomeUnknown", None, terminal=False)` [VERIFIED: service.py:1701-1702]. `latch_status()` answers from memory under `_state_lock` and returns `LatchStatus(latched=True, guid=latch.guid, result_kind=latch.kind, reason=latch.reason, explanation=latch.explanation)` [VERIFIED: service.py:1518-1538]. The `Lost` result carries no guid: `Lost.to_dict()` is `{"kind","handle": None,"lastState","reason","detail","message","explanation","context"}` and `detail` is built from `robot, mode, recovery, robotState` only [VERIFIED: results.py:1072-1085, service.py:1703-1708].

**Executed evidence:**

```
== 2 POST raises ReadTimeout -> Lost(submitOutcomeUnknown)
lost submitOutcomeUnknown posts 1 | latch submit-2b56c97300d7ce1d inflight set()
plan again -> failureLatched | execute same plan_id -> planNotFound
--- (b) _submit_outcome_unknown then latch_status guid
kind/reason: lost submitOutcomeUnknown handle: None detail keys: ['mode', 'recovery', 'robot', 'robotState']
latch guid: submit-7f0a958f6723b3ce True lost submitOutcomeUnknown
guid in explanation: True
```

**Answer:** Yes. `latch_status().guid` matches `submit-[0-9a-f]{16}` the instant `execute_transfer` returns, and it is in no structured field of the `Lost` dict, so `_find_guid` returns `None` for it and the adapter must call `latch_status()` (zero I/O) to name it. One edge: `_set_latch` is a no-op when a latch is already held and is not `stateUnsaved` ("first-failure-wins", service.py:1348-1350). `_motion_gates` refuses with `failureLatched` before the POST when a latch is held, so this only happens in a concurrent-latch race; in that race `latch_status().guid` is the other latch's guid. The adapter must therefore record whatever `latch_status()` returns at that moment (and `None` if `latched` is false) rather than assuming a `submit-` prefix, and must never parse the free-text `explanation`.

### (c) Which `execute_transfer` results prove nothing was sent; exception paths

**Code path:** `execute_transfer` -> `planNotFound`/`planExpired` refusals, otherwise `return self.start_transfer(request)` [VERIFIED: service.py:911-920]. `start_transfer` order: latched refusal, `_validate_locally` (reads), motion gates (reads), then `with self._submit_lock:` ... exactly one `post_transfer` [VERIFIED: service.py:1254-1275]. Everything before the POST is wrapped by the outer `except Exception as exc: return ReadFailed.from_error(exc)` [VERIFIED: service.py:1305-1306]. After the POST, every failure is routed to `_submit_outcome_unknown` (`except Exception:` on the POST, bad guid, `TaskHandle` construction failure) [VERIFIED: service.py:1274-1300], and the docstring states "Nothing past that point may escape to the outer guard, so a transfer that was actually sent is never mislabelled a failed read" [VERIFIED: service.py:1245-1248]. `_parse_hhmmss` "Never raises" [VERIFIED: results.py:449-464], so the `TaskHandle` branch is effectively unreachable.

**Executed evidence (probes 3-6):**

```
== 3 refusals pre-POST: manager manual / manager read error
refused managerNotAutomated posts 0
readFailed posts 0
== 4 typed HTTP 500 on POST (residual-risk case)
rejected instrument 500 posts 1 | latched False | inflight set()
== 5 typed HTTP 400 busy on POST
refused stackBusy posts 1 latched False
== 6 in-flight: second transfer while first guid not terminal -> inFlight
refused inFlight {'guid': '00000000-0000-4000-8000-000000000001'} posts 1
```

(Probe 6's `posts 1` is the first transfer's POST; the refused second one sent none.)

**Classification (answer):**

| execute_transfer result | POST sent? | Safe to release the key? |
|---|---|---|
| `Refused(planNotFound / planExpired / failureLatched / inFlight / managerNotAutomated / recoveryPending / robotNotIdle)`, `NeedsInput`, `ReadFailed` from a gate or validation read | No (probe 3: 0 POSTs) | Yes, proven |
| `Refused(stackBusy)` and `Rejected(stage="instrument", httpStatus=...)` | **Yes, one POST was sent and STACK typed-refused it** (probes 4, 5: `posts 1`, no latch, no in-flight) | Yes by core policy (a typed HTTP answer is a decision, not an unknown); this is what XFR-04 locks. Residual risk: a 5xx whose server side may still have acted. The core's gates (`robotNotIdle`, `inFlight`, `stackBusy`) are what stop a second transfer on a re-run, not the ledger. See Open Question 2 |
| `Lost(submitOutcomeUnknown)` | Yes or maybe | No: `outcomeUnknown`, permanent (D-08) |
| `TaskHandle` | Yes | n/a (`started`) |
| any exception out of `execute_transfer` | unknown | No: leave `submitting` (D-08) |

**Exceptions out of `execute_transfer`:** by code, only `BaseException` (`KeyboardInterrupt`, `SystemExit`) can escape; `Exception` is converted. A `ReadFailed` after the POST is only reachable if `_submit_outcome_unknown` itself raised before its internal guards (its `_set_latch`/`secrets` statements), which the core treats as impossible; D-08's release-on-`ReadFailed` is therefore consistent with the core's documented guarantee. Fail-closed rule for the adapter: **release only on an explicit whitelist** (`Refused`, `Rejected`, `NeedsInput`, `ReadFailed` by `isinstance`); any other type (including an unexpected `Lost` reason or a mock returning garbage) keeps the record (`outcomeUnknown`), never deletes it.

### (d) Additional findings the CONTEXT did not ask for

**A-1. The terminal set must be the core's `_task_ended`, not "anything but `timedOut`".** `_task_ended` is true for `ran`, `failed`, `aborted` and `lost` with reason `taskNotFound`; false for `timedOut`, `cancelled` and `lost` with any other reason (notably `pollFailed`) [VERIFIED: service.py:1917-1930]. The in-flight guard clears only when `_task_ended` [VERIFIED: service.py:2042-2046], while `_should_latch` latches `failed`, `aborted`, `lost` (any reason) [VERIFIED: service.py:1325]. Executed:

```
--- (c) lost(pollFailed) leaves inflight set? (owned guid, get_transfer raises)
lost pollFailed | inflight: {'11111111-2222-3333-4444-555555555555'} | latch: True pollFailed
ack: failureAcknowledged None | inflight after ack: {'11111111-2222-3333-4444-555555555555'}
```

So after `lost(pollFailed)` the core is latched **and** the guid is still in the persisted `_inflight`; acknowledging does **not** clear `_inflight`. If the ledger recorded this as `done` (CONTEXT D-05/D-07 treat every non-`timedOut` result as terminal), no adapter path would ever wait that guid again and every later Transfer would be `Refused(inFlight)` permanently (the guard is persisted across restarts). Re-attach while latched works and clears it:

```
1st: lost pollFailed latched True
re-attach while latched: ran | inflight: set() | latch still: True pollFailed
```

**Recommendation (amends D-05/D-07/D-11):** `done` only for `ran`, `failed`, `aborted`, `lost(taskNotFound)`. Treat `timedOut`, `lost(pollFailed)` and any other result (`cancelled`, `needsInput`, `readFailed` from a wait) as **non-terminal**: record stays `started`, reply is `ERROR_FROM_TOOL` naming the latch guid (for `pollFailed`, which latches) and saying re-run this step to re-attach. A re-run re-attaches (works while latched), and after it observes `ran` the Transfer is SUCCESS while the latch (`pollFailed`) is still held, so the operator must acknowledge before the next Transfer; that next Transfer is refused `failureLatched` naming the guid, which is safe and visible.

**A-2. The guid to acknowledge must come from `latch_status()` first.** The latch is first-failure-wins (`_set_latch` returns early when a latch is held, service.py:1348-1350) and `acknowledge_failure` answers `guidMismatch` unless `guid == latch.guid` (service.py:1476-1477). A re-attached `failed` result for guid `g` while a different latch (`submit-...`) is held does not re-latch, so the result's own guid is the wrong one to tell the operator. `latch_status().guid` is by definition what `acknowledge_failure` must name ("Gives the guid `acknowledge_failure` must name", service.py:1522-1527). Rule: after any non-`ran` result (and for every refusal that mentions a latch), call `latch_status()` once (zero I/O); if `latched` name that guid and `resultKind`; if not latched say the core did not latch it and tell the operator to inspect the arm. Use the result's own guid only as the "task guid" label in the message, never as the acknowledge guid. This amends D-13's ordering.

**A-3. Orphaned core in-flight guard (accepted limitation, documentable).** If the tool dies after the core persisted `_inflight` but before the adapter's `started` write, the ledger holds `submitting` (key refuses forever) while the core holds an in-flight guid that no adapter path will wait; every Transfer is then `Refused(inFlight, guid)` until someone waits that guid. The state file is shared with stack-mcp (same endpoint key), so the runbook route is `wait_transfer(guid)` from stack-mcp using the guid in the refusal. Not worth building an adapter drain (it would be unplanned behaviour and a proto-free but unreviewed motion-adjacent path). Mitigation inside scope: when an `inFlight` refusal names a guid, look it up in the ledger (`handle.guid`) and name the owning `step_key` in the message ("step key X is still running; re-run it"). Document the orphan case in the Phase 7 runbook.

**A-4. A successful `ran` can coexist with a held latch** (`stateUnsaved` set when the core's save failed after the POST, or a re-attached `lost(pollFailed)`). `ran` stays SUCCESS with an empty message (STK-07); the next Transfer is refused with the guid. Optional (planner discretion, low value): add `latchedGuid` to adapter-owned meta on SUCCESS; not required by any requirement.

## Architecture Patterns

### System Architecture Diagram

```
gRPC ExecuteCommand(stack.transfer)                      gRPC ExecuteCommand(stack.get_failure_latch)
        |                                                          |  (READ_COMMANDS: bypasses BUSY, no setStatus)
        v                                                          v
 base ExecuteCommand: parseCommand -> NOT_READY if BUSY      _dispatchCommand -> _check_args -> latch_status()
        | setStatus(BUSY)                                           -> _result_reply (latchStatus in _SUCCESS_KINDS)
        v
 _dispatchCommand: _check_args (blank step_key => INVALID_ARGUMENTS, no I/O)
        | simulated? -> base sleep only (never touches ledger or core)
        | _admit (WR-02) -> service snapshot
        v
 Transfer handler
   |- motion lock (module-level, non-blocking) --busy--> ERROR_FROM_TOOL "busy"
   |- fingerprint(endpoint_key, TransferRequest fields)
   |- ledger.load()  --unreadable/corrupt/unknown version--> ERROR_FROM_TOOL "do not delete it"
   |- decide(record, fingerprint, instance, now):
   |     none ................ FRESH
   |     fingerprint differs . INVALID_ARGUMENTS (no core call)
   |     submitting .......... REFUSE (outcome unknown)
   |     outcomeUnknown ...... REFUSE (names latch guid)
   |     started ............. REATTACH
   |     done+ran (<=600 s) .. REPLAY -> SUCCESS {result, stepKey, replayed:true}
   |     done+ran (older) .... REFUSE (mint a new key)
   |     done+other .......... REFUSE (repeat kind/reason/guid, latch guid)
   v
 FRESH (_run_fresh: the ONLY plan/execute call sites)
   plan_transfer --not TransferPlan--> map + latch guid, no record
   ledger.claim(submitting)  --write fails--> ERROR_FROM_TOOL, nothing sent
   execute_transfer
       TaskHandle ........... ledger started(handle) -> service.wait(handle, T)
       Refused/Rejected/NeedsInput/ReadFailed ... ledger.release(key)
       Lost(submitOutcomeUnknown) ... ledger outcomeUnknown(latch guid via latch_status)
       exception / anything else .... leave submitting
   wait -> ran|failed|aborted|lost(taskNotFound) ... ledger done(result)
        -> timedOut|lost(pollFailed)|other ........ stay started
 REATTACH: loop service.wait_transfer(guid, min(remaining,300)) until non-timedOut or T spent
   -> same mapping; instance differs => restart clause + latch_status guid
```

### Recommended Project Structure

```
tools/stack/
├── __init__.py
├── ledger.py        # NEW: core-free pure store + decide(); no stack_automation_layer import
├── server.py        # EDIT: Transfer/AcknowledgeFailure/GetFailureLatch, config, mapping, locks
└── requirements.txt # unchanged
tools/tests/
├── stack_test.py          # EDIT: migrate Phase 4 tests, new Transfer/ack/invariant/restart classes
└── stack_ledger_test.py   # NEW: pure ledger tests (no core needed, never skipped)
.planning/phases/05-.../05-SPIKE.md   # NEW: Plan 05-01 deliverable, from the findings above
```

`bin/make test` discovers `tools/tests/*_test.py` for unittest and `tools/tests/` for pytest [VERIFIED: bin/make `test()` function], so a new `stack_ledger_test.py` is picked up with no config. Keeping `ledger.py` free of core imports means its tests are not subject to `stack_test.py`'s module-level `SkipTest` when the private core is absent.

### Suggested plan decomposition (planner may adjust)

1. **05-01 Spike:** write `05-SPIKE.md` from "Design Spike Findings", incorporating A-1/A-2 (and the Open Question answers). No code. User checkpoint on amendments A-1, A-2 and Open Questions 1-2.
2. **05-02 Ledger module + pure tests** (`ledger.py`, `stack_ledger_test.py`): record schema, strict parse, atomic write, flock claim, `decide()` per D-07 row, release/keep rules, retention, fingerprint.
3. **05-03 Config + Transfer + reply mapping:** ledger-dir resolve/validate in `_apply_config`, `_run_fresh`/`_reattach_loop`, message builder, motion lock, remove `UNAVAILABLE_COMMANDS`.
4. **05-04 Latch read + Acknowledge + Phase 4 test migration:** `_SUCCESS_KINDS` + `latchStatus`, map entries, real-mode "yes" gate, rewrite the tests listed below.
5. **05-05 Invariant + proofs:** replace the D-20 AST test with the XFR-05 rule set (+ planted violations), execute-count behavioural matrix, STK-05 re-proof on real Transfer, restart tests.

### Pattern 1: Core-free ledger with a lock-free decide and an atomic claim

**What:** `decide()` reads the file without a lock (readers see whole files because writes are `os.replace`); only mutations take the flock, and the claim re-checks under the lock so the write-ahead is create-if-absent.
**When to use:** the `none -> submitting` transition and every later write.
**Example (shape, not final code):**

```python
# tools/stack/ledger.py  (stdlib only; mypy-strict annotations required)
import fcntl, hashlib, json, os, tempfile, time, uuid
from pathlib import Path
from typing import Any, Callable, Optional

LEDGER_VERSION = 1
STATES = ("submitting", "started", "done", "outcomeUnknown")

class LedgerError(Exception):
    """Unreadable / corrupt / unknown version / unwritable. Fail closed."""

def fingerprint(endpoint: str, request: Any) -> str:
    canonical = json.dumps({"v": 1, "endpoint": endpoint, "request": dataclasses.asdict(request)},
                           sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def _parse(raw: bytes) -> dict[str, dict[str, Any]]:
    payload = json.loads(raw.decode("utf-8"))              # ValueError/UnicodeDecodeError -> LedgerError
    if type(payload) is not dict or type(payload.get("version")) is not int \
            or payload["version"] != LEDGER_VERSION:       # type(...) is int: bool is an int subclass
        raise LedgerError("unknown version")
    records = payload.get("records")
    if not isinstance(records, dict):
        raise LedgerError("corrupt")
    for key, rec in records.items():                       # strict per-record validation, like core _parse_state
        if not (isinstance(key, str) and isinstance(rec, dict)
                and rec.get("state") in STATES and isinstance(rec.get("fingerprint"), str)
                and isinstance(rec.get("instance"), str)):
            raise LedgerError("corrupt record")
    return records
```

Atomic write is the core's `StateStore.save` pattern: `mkdir(parents=True, exist_ok=True, mode=0o700)`, `tempfile.mkstemp(dir=directory, prefix=path.name + ".", suffix=".tmp")` (0600), write+`flush`+`os.fsync`, `os.replace(tmp, path)`, best-effort `fsync` of the directory, unlink the temp on `BaseException` [VERIFIED: state_store.py:132-152].

### Pattern 2: `Transfer` as one function with the only plan/execute call sites

`_run_fresh(service, request, key, fp, budget)` contains the single `plan_transfer` call and the single `execute_transfer` call, with the `ledger.claim(...)` write-ahead statement before `execute_transfer` in the same function body and no loop/comprehension/lambda ancestor. The re-attach path is a separate function that may loop over `wait_transfer`. This is what makes the D-16 AST rules checkable without heuristics.

### Pattern 3: Result handling by `isinstance` against the core's real classes

```python
from stack_automation_layer.results import (NeedsInput, ReadFailed, Refused, Rejected,
                                            TaskHandle, TransferPlan, Lost)

plan = service.plan_transfer(request)
if not isinstance(plan, TransferPlan):
    return self._core_error(service, plan)          # no record was written
...
outcome = service.execute_transfer(plan.plan_id)
if isinstance(outcome, TaskHandle):                  # -> started
    ...
elif isinstance(outcome, (Refused, Rejected, NeedsInput, ReadFailed)):   # whitelist -> release
    ...
elif isinstance(outcome, Lost) and outcome.reason == "submitOutcomeUnknown":
    ...                                              # -> outcomeUnknown
else:
    ...                                              # unknown shape -> keep record, fail closed
```

Tests build these from the core's real result classes, so `isinstance` works with `MagicMock(spec=StackService)` return values.

### Pattern 4: Terminal / non-terminal predicate (amendment A-1)

```python
# Mirrors StackService._task_ended (service.py:1917-1930); done == this is True.
def _is_terminal(d: dict[str, Any]) -> bool:
    kind = d.get("kind")
    return kind in ("ran", "failed", "aborted") or (
        kind == "lost" and d.get("reason") == "taskNotFound")
```

### Pattern 5: Re-attach loop (read-only, bounded)

```python
deadline = time.monotonic() + budget
while True:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return timed_out_reply
    result = service.wait_transfer(guid, timeout_s=min(remaining, WAIT_SLICE_S))  # WAIT_SLICE_S = 300.0
    if result.to_dict().get("kind") != "timedOut":
        return result            # lost(pollFailed), needsInput etc. exit the loop too; never spin
```

`wait_transfer` clamps to `WAIT_TRANSFER_MAX_S = 300.0` [VERIFIED: service.py:194], and an invalid (non-positive/non-finite) `timeout_s` becomes `NeedsInput(missing=["timeoutS"])` with zero calls [VERIFIED: service.py:1958-1959], so never call it with `remaining <= 0`.

### Pattern 6: Restart simulation in tests

A restart is a **new `StackServer()`** (new `instance` uuid) pointed at the **same ledger dir** with a **new fake core** whose state encodes owned vs foreign. Both `server.service = fake` and a ledger dir attribute are set directly, as `_RealModeGrpcTestCase.setUp` already does (it sets `server.service`, `server.config`, `server.status` without Configure) [VERIFIED: tools/tests/stack_test.py:1300-1307]. Note `_ledger_dir` is `""` in that fixture, so the ledger path must be resolved lazily at Transfer time from `self._ledger_dir` plus the environment (a pure `resolve_ledger_dir(configured)` used by both `_apply_config` and `Transfer`). A small `_FakeCore` class (not just `MagicMock`) is worth writing: it implements `plan_transfer`, `execute_transfer`, `wait`, `wait_transfer`, `latch_status`, `acknowledge_failure`, counts `execute_transfer` calls, models `foreign` guids (a foreign `failed` does not latch, per probe a1) and an `_inflight` set (`Refused(inFlight)`), and builds results from the real classes. Keep `MagicMock(spec=StackService)` for the 1:1 surface tests.

### Anti-Patterns to Avoid

- **Treating every non-`timedOut` result as terminal** (CONTEXT D-05/D-07 wording): creates the permanent `inFlight` trap (A-1).
- **Naming the result's guid as the acknowledge guid** (A-2).
- **Holding the flock for the whole Transfer:** it would block another tool server sharing the directory for minutes. Lock only around each read-modify-write.
- **Letting an exception escape `Transfer` after the write-ahead:** base `ExecuteCommand` turns it into `DRIVER_ERROR` with `str(e)`, and the bypassed read path does the same [VERIFIED: tools/base_server.py:253-259, tools/stack/server.py:508-515]. Catch `Exception` in the handler, leave the record as designed, and reply `ERROR_FROM_TOOL` with `type(exc).__name__` only (never `str(exc)`).
- **Raising `KeyError` in ledger code:** base `_dispatchCommand` maps `KeyError` to `INVALID_ARGUMENTS` [VERIFIED: tools/base_server.py:178-183]. Use `.get()` and a dedicated `LedgerError`.
- **Building the message by appending the guid last:** `_error_line` truncates to 300 chars via `_one_line` [VERIFIED: tools/stack/server.py:289, 178-184]; a long clause can cut the guid off.
- **Parsing the core's `explanation`:** agent-worded, forbidden by Phase 4 D-11.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Failure latch, ownership, in-flight guard, gates | an adapter-side latch or "robot busy" check | the core's `latch_status()`, `Refused(inFlight/failureLatched/robotNotIdle)` | Core Value: the adapter holds no instrument policy |
| Guid to acknowledge | parsing `explanation` or the result | `service.latch_status().guid` | exact-match semantics (A-2) |
| Atomic persistence | `open(path,"w")` then write | temp + `fsync` + `os.replace` + dir `fsync` (core `StateStore.save` pattern) | torn writes on crash lose the write-ahead record, the whole point |
| Mutual exclusion on the ledger file | `threading.Lock` only | `fcntl.flock` on a sibling lock file (+ the in-process motion lock) | two tool servers may share a directory (D-02) |
| Request fingerprint | ad-hoc string join | `hashlib.sha256` of `json.dumps(..., sort_keys=True, separators=(",", ":"))` of `dataclasses.asdict(TransferRequest)` + `endpoint_key` | stable across runs and field order |
| Retry / wait-forever | an adapter retry or unbounded loop | one `wait`, or a bounded read-only `wait_transfer` loop | XFR-05 |
| Endpoint normalisation | `host:port` string formatting | `stack_automation_layer.owner_lock.endpoint_key` (already imported at server.py:28) | strips brackets, lowercases, trims trailing dot [VERIFIED: owner_lock.py:50-59] |

**Key insight:** the dangerous part of this phase is not any one function, it is the *transitions* (which record state survives which failure). Keep them in a single pure `decide()` plus a small set of named ledger operations so they can be exhaustively unit-tested and the AST rules can anchor on them.

## Common Pitfalls

### Pitfall 1: `lost(pollFailed)` recorded as `done` (permanent `inFlight`)
**What goes wrong:** every later Transfer is `Refused(inFlight)` forever; the guard is persisted by the core and acknowledging does not clear it (verified).
**Why:** CONTEXT treats all non-`timedOut` results as terminal; the core's `_task_ended` does not.
**Avoid:** A-1 terminal set; test: `wait` returns `Lost(pollFailed)` -> record stays `started`, re-run re-attaches.
**Warning signs:** an `inFlight` refusal naming a guid whose ledger record is `done`.

### Pitfall 2: Acknowledge guid taken from the result
**What goes wrong:** operator sends the task guid, core answers `guidMismatch`, latch stays.
**Avoid:** A-2; test with a fake core latched on `submit-...` while a re-attached `failed` carries a task guid.

### Pitfall 3: Message truncation drops the guid
**What goes wrong:** `_one_line(line, 300)` cuts the tail, which is where the acknowledge guid and next action live.
**Avoid:** build the line as `stack: <kind> (<reason>); latched guid <g> ...` with the guid and action first, optional hints last; add a test with a maximal hint and assert the guid survives.

### Pitfall 4: A Phase 4 test still asserts the old refusal
**What goes wrong:** the gate goes red for reasons unrelated to the new code. See "Existing tests that must change".

### Pitfall 5: Tests writing the real ledger
**What goes wrong:** `_StackTestCase.setUp` patches `STACK_MCP_LOCK_DIR`, `STACK_STATE_DIR`, `STACK_USER`, `STACK_PASSWORD` but **not** `XDG_STATE_HOME` or `HOME` [VERIFIED: tools/tests/stack_test.py:124-129]. A `Transfer` test with `_ledger_dir == ""` would resolve to the real `~/.local/state/galago-tools/stack`.
**Avoid:** add `XDG_STATE_HOME` (a temp dir) to the patched env in `_StackTestCase.setUp`, and add a test that a default-resolved ledger lands under it. Also create the ledger only on write, so a test that never writes leaves nothing.

### Pitfall 6: Module-level motion lock poisoned across tests
**What goes wrong:** a failing test that leaves the lock held makes every later Transfer test say "busy".
**Avoid:** always `addCleanup(lock.release)` when a test acquires it, and assert `not locked()` in `tearDown` of the Transfer test base.

### Pitfall 7: Wait budget parking a worker
**What goes wrong:** `Transfer.timeout_s` is only checked finite and >= 0 (`_check_args`, server.py:214-217); `1e9` parks one of `serve()`'s 10 worker threads for days and blocks Configure ("busy" after 5 s).
**Avoid (discretion, [ASSUMED] value):** clamp the budget to a constant ceiling (suggest `MAX_TRANSFER_TIMEOUT_S = 3600`) rather than rejecting.

### Pitfall 8: `fcntl` is POSIX-only
**What goes wrong:** a top-level `import fcntl` makes `tools/stack/ledger.py` unimportable on Windows, and `server.py` imports it, so the whole tool fails to load there.
**Avoid:** import `fcntl` lazily inside the lock helper (or guard with `try/except ImportError`) and fail real-mode Transfers closed with a clear error if unavailable. The deployment target is Linux (forb01), so this is hygiene only.

### Pitfall 9: bool is an int
**What goes wrong:** `{"version": true}` passes `isinstance(v, int)`.
**Avoid:** `type(version) is int` (the core does exactly this: state_store.py:126).

### Pitfall 10: a failed `claim` flock wedges a worker
**Avoid:** acquire the flock with `LOCK_NB` in a short polling loop with a deadline (suggest 5 s, [ASSUMED]) and fail closed ("ledger busy") rather than blocking forever.

## Code Examples

### Fingerprint inputs come from the same builder the call uses

`_transfer_request(cmd)` currently takes a `GetTransferEstimate` command; the `Transfer` message has the same ten instrument fields with the same names (`robot`, `labware_profile`, `source_device`..`destination_transfer_profile`) plus `step_key` and `timeout_s` [VERIFIED: interfaces/tools/grpc_interfaces/stack.proto, `message Transfer` fields 1-12]. It reads fields via `cmd.HasField(...)`/`getattr`, so it works unchanged for `Transfer`; only its docstring and type hint mention the estimate. The core's `TransferRequest(robot, labware_profile, source: Location, destination: Location)` and `Location(device, deck, nest, transfer_profile)` are frozen dataclasses [VERIFIED: model.py:20-42 at 934a621], so `dataclasses.asdict` is the canonical fingerprint input.

### Acknowledge handler shape

```python
def AcknowledgeFailure(self, params):
    service = self._require_service()
    # "yes" already enforced earlier in real mode (see placement note); only call site:
    return _result_reply(service.acknowledge_failure(params.guid.strip(), confirm=True))
```

`acknowledge_failure(guid, *, confirm: bool = False)` takes keyword-only `confirm` and only the literal `True` counts [VERIFIED: service.py:1416-1418, 1465-1466]. Its results: `FailureAcknowledged | Refused | NeedsInput | ReadFailed`; `Refused` reasons seen in code are `nothingLatched`, `guidMismatch`, `recoveryPending`, `stateUnsaved` [VERIFIED: service.py:1475, 1477, 1486, 1506-1509].

**Placement of the real-mode "yes" check (recommendation):** put it in `_dispatchCommand` right after the `if self.simulated:` branch and before `_admit`, so it is `INVALID_ARGUMENTS` with no core call even when the tool is unconfigured, and simulated mode (which returns earlier) still accepts `"no"` (Phase 4 D-17; existing test `test_acknowledge_with_no_is_also_success`). `_check_args` stays unchanged so `TestCheckArgs.test_acknowledge_arm_inspected_is_exactly_yes_or_no` keeps passing.

### `_apply_config` ledger-dir validation (before `open_service`)

Validate next to the `transfer_timeout_s` check (server.py:458-462) so a bad path fails before any lock is taken:

```python
ledger_dir = config.ledger_dir
if ledger_dir.strip() and not os.path.isabs(ledger_dir):
    raise ValueError("stack: Config.ledger_dir must be an absolute path")
```

Keep `self._ledger_dir = config.ledger_dir` raw (the existing test `test_ledger_dir_is_recorded_but_never_created` asserts `server._ledger_dir == ledger` and that nothing is created) [VERIFIED: tools/tests/stack_test.py:1018-1028]. "Never under /tmp" applies to the *defaults* (D-03); an explicit `ledger_dir` under `/tmp` must stay legal because every test fixture uses `tempfile` directories. Default resolution order from D-03: `$XDG_STATE_HOME/galago-tools/stack` only when `os.path.isabs(...)`, else `Path.home() / ".local" / "state" / "galago-tools" / "stack"` (the core resolves its own directory the same way, state_store.py:63-67).

### AST rule helper additions (extend `_stack_adapter_violations`)

The existing helper is assertion-free, walks `ast.walk`, and `_plant(tree, function, statement)` inserts a statement as the first statement of a function [VERIFIED: tools/tests/stack_test.py:1107-1189]. `ast` has no parent links, so build `parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}` and walk up from each `execute_transfer` call. Rules to add, each with a planted violation:

| Rule | Planted violation that must be reported |
|---|---|
| forbidden set is now 5 names: `start_transfer, cancel_transfer, go_to_safe_position, wait_safe_position, validate_transfer` | `self.service.<name>()` for each (replaces the `len == 10` assertion) |
| exactly one `.execute_transfer(` call across `tools/stack/*.py` | add a second call elsewhere; remove the real one (count 0) |
| `execute_transfer` has no `For/AsyncFor/While/ListComp/SetComp/DictComp/GeneratorExp/Lambda` ancestor | `for _ in range(2): service.execute_transfer(p)` |
| `execute_transfer` lives in the named fresh-path function and a ledger write-ahead call (`claim`) appears before it by line number in that function | move it above the claim; move it to another function |
| exactly one `.plan_transfer(` call | add a second |
| exactly one `.acknowledge_failure(` call and it is inside `AcknowledgeFailure` | call it from `_dispatchCommand` or `Transfer` |
| no `getattr(<x>, "<name>")` / string-keyed dispatch of a forbidden or single-site method (indirection bypass) | `getattr(service, "execute_transfer")(p)` |
| `.wait_transfer(` inside a loop is allowed (negative control) | planted loop around `wait_transfer` must produce no violation |
| required functions: add the fresh-path function, `AcknowledgeFailure`, `GetFailureLatch`, `Transfer` so a rename cannot silently disable a rule | rename each, expect "missing" |

`COMMAND_TO_SERVICE_METHOD` will now contain the string `"acknowledge_failure"` as a value, so `_FORBIDDEN_SERVICE_CALLS` can no longer contain it (the existing test `test_every_key_is_a_server_method_and_every_value_a_service_method` asserts `assertNotIn(method, _FORBIDDEN_SERVICE_CALLS)`), and the string-constant rule above must exempt that one dict.

## Existing tests that must change (Phase 4 encodings of "Phase 5 is refused")

All in `tools/tests/stack_test.py` [VERIFIED by Read/grep this session]:

| Lines | Test / symbol | Change |
|---|---|---|
| 1080-1086, 1214-1222 | `_FORBIDDEN_SERVICE_CALLS` (10 names incl. `plan_transfer`, `execute_transfer`, `wait`, `wait_transfer`, `acknowledge_failure`), `test_every_forbidden_service_call_is_reported` (`len == 10`), `test_module_level_forbidden_call_is_reported` (plants `service.wait(None)`) | shrink to the 5-name set, replace the planted `wait` with a still-forbidden name, add XFR-05 rules |
| 1096, 1269-1276 | `_REQUIRED_FUNCTIONS` | add new names |
| 1529-1556 | `TestOneToOneSurface`: map has 7 keys, `mapped | UNAVAILABLE_COMMANDS == names`, `.UNAVAILABLE_COMMANDS` attribute used | map has 9 keys; `mapped | {"Transfer"} == names`; `UNAVAILABLE_COMMANDS` is removed from the module; `test_each_mapped_command_records_exactly_one_mapped_call` gains `GetFailureLatch`->`latch_status`, `AcknowledgeFailure`->`acknowledge_failure(guid, confirm=True)` |
| 1610-1650 | `TestResultMapping.SUCCESS_RESULTS` (9) and `assertEqual(len(...), 9)` | add `LatchStatus(latched=False)` and a latched one; len 10 |
| 1935-1996 | `_REFUSALS`, `TestRealModeRefusals`, `TestRealModeRefusalsOrdering` | delete the refusal expectations; replace with new Transfer/Ack tests; unconfigured `GetFailureLatch` is now `NOT_READY` "stack: not configured" |
| 2024-2027 | `_VALID_ARGS` | fine as is for `_check_args`/sim tests |
| 2130-2211 | `TestBusyReads` (injects a patched `Transfer` handler; `get_failure_latch` subtest asserts the refusal) | re-prove on the real Transfer via a blocking fake `wait`; `get_failure_latch` now answers SUCCESS with `latch_status().to_dict()` |
| 2242-2248 | `test_a_non_read_command_still_records_its_error` (Transfer `step_key="s-1"` against a bare `MagicMock(spec=StackService)`) | now runs the real handler; configure `plan_transfer.return_value` (e.g. `NeedsInput`) so it stays an `ERROR_FROM_TOOL` |
| 2343-2364 | `test_reads_never_call_set_status_but_a_transfer_brackets_busy_ready` (Transfer `step_key="k"`, `get_failure_latch` on a bare mock) | set `plan_transfer`/`latch_status` return values |
| 2300-2312 | `TestNotConfigured.test_fresh_server_reads_are_not_ready_and_the_latch_is_refused` | `GetFailureLatch` unconfigured is `NOT_READY` "stack: not configured" |
| 1018-1028 | `TestConfigureLedgerDir` | keep; add a relative-path `ValueError` test that fails before `open_service` (mirror `test_bad_transfer_timeout_fails_before_open`) |

Any test that sends a real `Transfer` with a bare `MagicMock(spec=StackService)` gets a `MagicMock` back from `plan_transfer`; the handler must treat a non-`TransferPlan` as an error via `_result_reply`, which yields "stack: unrecognised result" for a non-dict `to_dict()` (server.py:297-298), so those tests are not flaky, only wrong-reason.

## Runtime State Inventory

Not a rename/refactor phase. For completeness, the only new runtime state is the adapter ledger directory (`stack-ledger.json` + `stack-ledger.json.lock`, default `~/.local/state/galago-tools/stack`), distinct from the core's state file under `STACK_STATE_DIR` / `~/.local/state/stack-automation-layer`. Both must persist across restarts (Phase 7 runbook). Nothing in this phase renames existing runtime state.

## State of the Art

| Old Approach (Phase 4 / research) | Current Approach (core `934a621`) | When Changed | Impact |
|---|---|---|---|
| a restart silently cleared the latch and ownership (G1) | per-endpoint persisted latch/`_started`/`_inflight`, fail-closed state file | DEP-01, 2026-10-29 | restart is only dangerous for the one task in the POST->save window (limit 1) |
| latch guid hidden in free text (G2) | `latch_status()` zero-I/O read | same | `GetFailureLatch` binds 1:1; no `plan_transfer(TransferRequest())` workaround |
| latch set after the explanation build (G3) | latch first, explanation after | same | an ambiguous submit can never be left unlatched |

**Deprecated/outdated:** the Configure restart warning text was corrected in `fe8aee8`; `UNAVAILABLE_COMMANDS` and `_unavailable_reply` go away in this phase.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `fcntl.flock` locks per open file description so separate `open()` calls (even in one process) contend, unlike `lockf` | Alternatives | A same-process double-claim would not be excluded by the flock (the module motion lock still covers the in-process case) |
| A2 | Suggested constant `MAX_TRANSFER_TIMEOUT_S = 3600` for clamping `Transfer.timeout_s` | Pitfall 7 | Too low truncates a legitimate long wait (the step then `timedOut` and is re-run: safe); too high parks a worker |
| A3 | Suggested ledger flock acquisition deadline of 5 s | Pitfall 10 | Spurious "ledger busy" under heavy contention (fails closed, safe) |
| A4 | Suggested `step_key` length cap (e.g. 256 chars) as `INVALID_ARGUMENTS` hardening | Security | An over-long key from a protocol would be refused; unbounded keys grow the JSON file |
| A5 | galago-core's own gRPC/command timeout vs the default `T = 300` s is unknown | Open Question 4 | A Transfer longer than galago's deadline could look failed to galago while the arm finishes; the ledger makes the re-run safe, but the operator experience needs Phase 7 confirmation |
| A6 | Deployment target is Linux only (forb01), so `fcntl` is acceptable | Pitfall 8 | Windows hosts would need a different lock |

All other claims in this document were verified against core source at `934a621`, executed against the real core, or read from the repo this session.

## Open Questions

1. **XFR-03 wording vs D-09 (restart + live `ran`)**
   - Known: probe a2 shows a foreign guid's `ran` is a real STACK observation; D-09 reports it SUCCESS with `reattachedAfterRestart: true`. XFR-03 says a restart during a transfer is "reported as needing arm inspection, never replayed as SUCCESS".
   - Unclear: whether the user reads "never replayed" as "never from the ledger" (D-09) or "never SUCCESS at all after a restart".
   - Recommendation: keep D-09 (it never replays; SUCCESS only on a live `completed`). Record the choice in `05-SPIKE.md` and get a one-line user confirmation at the spike checkpoint. The strict reading is a one-line change.

2. **Release on `Rejected(stage="instrument", httpStatus>=500)` and `Refused(stackBusy)`**
   - Known: both are returned after one POST was sent and typed-refused (probes 4, 5); the core does not latch or guard them; XFR-04 locks `rejected` as releasable; a re-run is protected by `robotNotIdle`/`inFlight`/`stackBusy` gates.
   - Unclear: whether a 5xx can leave STACK having acted.
   - Recommendation: keep XFR-04 as written (adapter holds no instrument policy; the core classifies typed HTTP answers as decisions), document the residual in the spike. Only if the user wants belt-and-braces: treat `httpStatus >= 500` as `outcomeUnknown`-without-latch (a one-branch change in the release whitelist).

3. **Should `ran` carry a held latch in meta (A-4)?** Recommend no; the next Transfer refusal names the guid.

4. **Galago-side command deadline vs `T = 300`** (A5): not researchable from this repo; carry to Phase 7 live acceptance. The ledger design already makes a "galago gave up, arm finished" case safe (re-run re-attaches or replays within `REPLAY_WINDOW_S`).

5. **Orphaned core in-flight guard after a crash between core persist and the ledger `started` write (A-3).** Accept and document in the Phase 7 runbook (stack-mcp `wait_transfer` by the guid in the refusal).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python venv `~/data/nikko/.venvs/galago-py310` | gate and all tests | yes | 3.10.12 | — |
| `stack_automation_layer` at the pinned SHA | `stack_test.py` | yes | `934a621ece116a8b263897c1e9b62b57374f4ef3` (pin test passes) | tests skip if absent; ledger tests are core-free |
| pytest / ruff / mypy | `bin/make proto test` | yes | 7.4.3 / 0.9.4 / 1.11.2 | — |
| `fcntl` (Linux) | ledger flock | yes | stdlib | lazy import guard (Pitfall 8) |
| Local core clone `~/data/nikko/stack-automation-layer` @ `934a621` | spike citations | yes | `git rev-parse HEAD` = pinned SHA | — |
| STACK manager / network | nothing | not needed and must not be used | — | all tests use fakes; the loopback guard in `_StackTestCase` blocks non-loopback connects |

**Missing dependencies:** none.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `unittest` classes run by pytest 7.4.3 (and `unittest discover`); gate also runs ruff + mypy |
| Config file | `pyproject.toml` (`[tool.ruff]` line-length 100 / E501 ignored; `[tool.mypy]` `disallow_untyped_defs`, `check_untyped_defs`, python 3.10) |
| Quick run command | `~/data/nikko/.venvs/galago-py310/bin/python -m pytest tools/tests/stack_test.py tools/tests/stack_ledger_test.py -q -k "<pattern>"` (the existing 120-test `stack_test.py` runs in 2.3 s, verified) |
| Full suite command | `bin/make proto test` on `~/data/nikko/.venvs/galago-py310` (last green: 267 tests on `934a621`, per CONTEXT) |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| XFR-01 | plan -> execute -> wait in one command; `ran` SUCCESS empty message; every other kind `ERROR_FROM_TOOL` with reason+guid; blank `step_key` INVALID before any core/ledger call | integration (in-process gRPC, fake core) | `pytest tools/tests/stack_test.py -k "TestTransfer"` | No (Wave 0) |
| XFR-02 | ledger schema, atomic write, write-ahead before execute, `started` then `done`, 0700/0600 modes, fail-closed on corrupt/unreadable/unknown version/`version: true`, write-ahead failure sends nothing, later-write failure still waits and ends ERROR | unit (pure) + integration | `pytest tools/tests/stack_ledger_test.py` / `-k "TestLedgerFailClosed"` | No (Wave 0) |
| XFR-03 | one test per D-07 row; fingerprint mismatch INVALID (different request, different endpoint); restart (new `StackServer`, same dir) for `started` ran/failed and `submitting`; `lost(pollFailed)` stays `started` (A-1) | unit + integration | `pytest tools/tests/stack_test.py -k "TestRepeatKey or TestRestart"` | No (Wave 0) |
| XFR-04 | whitelist release: `Refused`/`Rejected`/`NeedsInput`/`ReadFailed` delete the record and a re-run sends again; exception leaves `submitting`; unknown result type keeps the record; `plan_transfer` non-plan writes no record | unit + integration | `pytest tools/tests/stack_test.py -k "TestKeyRelease"` | No (Wave 0) |
| XFR-05 | AST invariant over `tools/stack/*.py` with planted violations (table above); behavioural `execute_transfer` count stays 1 across the D-16 scenario matrix | unit (AST) + integration | `pytest tools/tests/stack_test.py -k "TestAdapterInvariant or TestNeverResends"` | Partially (Phase 4 `TestAdapterInvariant` to be rewritten) |
| XFR-06 | `timedOut` -> ERROR, record `started`, no new `execute_transfer`; re-run re-attaches and reaches `ran`; re-attach loop slices at 300 s and never calls with `remaining <= 0`; budget precedence `timeout_s` > Config > 300 | integration | `pytest tools/tests/stack_test.py -k "TestTimedOutReattach or TestWaitBudget"` | No (Wave 0) |
| ACK-01 | only `"yes"` reaches `acknowledge_failure(guid.strip(), confirm=True)`; `"no"`/`"Yes"`/` yes`/unset -> INVALID with zero core calls (also when unconfigured); simulated still accepts `"no"`; exactly one call site (AST) | integration + AST | `pytest tools/tests/stack_test.py -k "TestAcknowledge"` | Partially (`TestCheckArgs` ack tests stay) |
| ACK-02 | `GetFailureLatch` -> `latch_status()` SUCCESS meta unchanged for task-guid / `submit-<hex>` / `state-<hex>` / unlatched; reads answer during a real Transfer; messages name the `latch_status()` guid first (A-2) and keep it under truncation | unit + integration | `pytest tools/tests/stack_test.py -k "TestFailureLatch or TestLatchGuidInMessage"` | No (Wave 0) |
| STK-05 (carry-over) | blocking fake `wait` on a `threading.Event` inside a real `Transfer`: eight reads + `GetFailureLatch` answer, second Transfer refused, status BUSY then READY | integration | `pytest tools/tests/stack_test.py -k "TestBusyReads"` | Yes, to be rewritten |
| STK-06 (regression) | simulated Transfer never writes the ledger or touches the core | integration | `pytest tools/tests/stack_test.py -k "TestSimulated"` | Yes (`_assert_core_free` already asserts the ledger path is absent) |
| STK-07 (regression) | `latchStatus` in `_SUCCESS_KINDS`; mapping table extended | unit | `pytest tools/tests/stack_test.py -k "TestResultMapping"` | Yes, to be extended |

### Sampling Rate
- **Per task commit:** the `-k` quick command for the area touched (a few seconds), plus `ruff check tools/stack tools/tests`.
- **Per wave merge:** `pytest tools/tests/stack_test.py tools/tests/stack_ledger_test.py -q` and `mypy --config-file=pyproject.toml tools`.
- **Phase gate:** `bin/make proto test` fully green before `/gsd-verify-work`; also grep that nothing under `tools/stack/` contains `10.150.1.125`/`stack-server` (the existing literal rule).

### Wave 0 Gaps
- [ ] `tools/tests/stack_ledger_test.py`: pure ledger tests (schema, strict parse, atomic write, claim, release, retention, fingerprint, flock deadline); covers XFR-02/03/04.
- [ ] `_FakeCore` helper in `tools/tests/stack_test.py` (counts `execute_transfer`; models foreign guids and `_inflight`); covers XFR-03/04/05/06.
- [ ] `_StackTestCase.setUp`: patch `XDG_STATE_HOME` to a temp dir (Pitfall 5).
- [ ] Transfer test base class with lock-poison guard (Pitfall 6).
- [ ] No framework install needed.

## Security Domain

`security_enforcement` is enabled (absent = enabled; `.planning/config.json` has `security_enforcement: true`, `security_asvs_level: 1`).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (the core owns STACK credentials from `STACK_USER`/`STACK_PASSWORD`; the adapter never sees or logs them) | existing Phase 4 test `test_password_never_appears_in_replies_or_logs` stays green |
| V3 Session Management | no | — |
| V4 Access Control | yes (acknowledge is operator-only in intent) | exact `"yes"` gate + core exact-guid + `confirm=True` + core recovery read; galago-core cannot hide the command from protocols (Pitfall 5 in SUMMARY) so the core's exact-guid requirement is the real guard; accepted per requirements |
| V5 Input Validation | yes | `_check_args` (non-blank `step_key`, finite `timeout_s >= 0`); add budget clamp (A2) and optional `step_key` cap (A4); ledger path must be absolute (D-03); strict ledger parse |
| V6 Cryptography | partial | `hashlib.sha256` for the fingerprint only (an identity digest, not a secret); no hand-rolled crypto |
| V7 Error Handling/Logging | yes | one-line messages from structured fields only, never the core `explanation`, never `str(exc)`; do not log credentials |
| V8 Data Protection / V12 Files | yes | ledger dir 0700, file and lock 0600, atomic write; never delete or rewrite a corrupt ledger; treat a symlinked ledger dir/file as untrusted (use `mkstemp` in the directory; consider `O_NOFOLLOW` on the lock open) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Replay of a recorded `ran` that moves nothing (a literal step key reused across runs) | Tampering / integrity | request fingerprint, `REPLAY_WINDOW_S`, older `ran` refused with "mint a new key per run" |
| Second physical transfer from a retry/re-dispatch/restart | Elevation (safety) | write-ahead ledger, single `execute_transfer` site, AST + behavioural tests |
| Blind/guessed acknowledge clearing a latch the operator never inspected | Elevation | exact `"yes"`, core exact-guid match; `guidMismatch` never echoes the real guid |
| Ledger tampering/corruption causing silent re-send | Tampering | strict parse, fail closed, never treat as empty, never auto-delete |
| Path abuse via `Config.ledger_dir` | Tampering | absolute-path requirement; Config is operator/admin-level input |
| Information disclosure in error text (URLs, exception strings, core explanation) | Information disclosure | message built from structured fields; `type(exc).__name__` only |
| Worker exhaustion by huge `timeout_s` or a wedged ledger lock | DoS | budget clamp, non-blocking lock acquisition with deadline, non-blocking motion lock |

## Sources

### Primary (HIGH confidence)
- Core `934a621` (`git show 934a621:<path>` and the local clone): `service.py` (`plan_transfer` :855, `execute_transfer` :888, `_reattach`/`wait_transfer` :922-972, `start_transfer` :1223, `_should_latch`/`_set_latch` :1308-1358, `acknowledge_failure` :1416, `latch_status` :1518, `_motion_gates` :1566, `_submit_outcome_unknown` :1670, `_task_ended` :1917, `_wait` :1932, `wait` :2049, `_snapshot_locked`/`_persist_locked`/`_restore` :462-562, constants :164-194, `_GUID_RE` :212), `results.py` (`TaskHandle` :652, `Refused` :699, `FailureAcknowledged` :765, `LatchStatus` :798, `Ran`..`Lost` :829-1085, `LOST_MESSAGES` :1034, `_parse_hhmmss` :449), `state_store.py` (whole file), `composition.py` (`open_service`), `model.py`, `owner_lock.py` (`endpoint_key` :50), `errors.py`
- Executed probes against the real core in `~/data/nikko/.venvs/galago-py310` (outputs pasted above) and the core's own `tests/fakes.py` `FakeTransport`
- This repo at HEAD of `feat/stack-tool`: `tools/stack/server.py`, `tools/tests/stack_test.py`, `tools/base_server.py`, `tools/fast/server.py` (motion lock :719-740), `tools/tests/fast_test.py` (AST helper :3212), `interfaces/tools/grpc_interfaces/stack.proto`, `bin/make`, `pyproject.toml`
- `.planning/phases/05-.../05-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md` Phase 5, `.planning/research/SUMMARY.md` (incl. Addendum 2026-10-29), `.planning/STATE.md`, `04-REVIEW-DISPOSITION.md`

### Secondary / Tertiary
- none (no web search needed; this phase is internal-code research. The graphify graph exists but predates the stack tool (built 2026-10-13) and was not used.)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH, stdlib only, core pin verified.
- Architecture: HIGH, core behaviour read and executed; adapter patterns taken from the existing Phase 4 code.
- Pitfalls: HIGH for A-1/A-2/message truncation/test migration (each demonstrated by code or a run); MEDIUM for the three `[ASSUMED]` constants (A2-A4) and A5.

**Research date:** 2026-10-29
**Valid until:** until the core pin changes (the whole spike is a statement about `934a621`); otherwise 30 days.
