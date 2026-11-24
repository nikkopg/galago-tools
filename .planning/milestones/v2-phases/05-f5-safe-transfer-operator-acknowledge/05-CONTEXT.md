# Phase 5: F5-safe Transfer & Operator Acknowledge - Context

**Gathered:** 2026-10-29
**Status:** Ready for planning
**Mode:** `--auto` (every gray area resolved with the recommended option; see `05-DISCUSSION-LOG.md`)

<domain>
## Phase Boundary

Wire the three Phase 4 placeholders in `tools/stack/server.py` to the pinned core `934a621`:

- `Transfer`: the only motion path. It runs `plan_transfer` → `execute_transfer` → wait to a terminal
  result in one command, guarded by a persisted `step_key` ledger so that a re-run, re-dispatch or
  tool-server restart never sends a second transfer for the same key.
- `GetFailureLatch`: bound 1:1 to `latch_status()`.
- `AcknowledgeFailure`: operator-only; only `"yes"` reaches `acknowledge_failure(guid, confirm=True)`.

The phase also replaces Phase 4's blanket no-motion AST invariant (Phase 4 D-20) with the narrower
XFR-05 invariant, and re-proves STK-05 (reads answer while BUSY) on the real `Transfer` path.

`stack.proto` stays frozen (Phase 4 D-01..D-05). **No proto or `Config` field is added in this phase.**
Every new knob (replay window, retention, default timeout) is an adapter constant.

Not in this phase:
- the GAL-02 workflow and simulated runs (Phase 6);
- galago-core forms and the Ack control (DEP-02/DEP-03);
- deploy and any live motion (Phase 7);
- STACK cancel and safe-position from Galago (out of scope for v2).

All tests use a fake or mocked core. Nothing moves.

</domain>

<decisions>
## Implementation Decisions

### Design spike first (roadmap note)
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

### Ledger storage (XFR-02)
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

### Record shape and fingerprint (XFR-02, XFR-03)
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

### Repeat-key state machine (XFR-03, XFR-04, XFR-06)
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

### Reply mapping and messages (XFR-01)
- **D-10:** This decision extends Phase 4 D-10..D-12:
  - `ran` is SUCCESS with an empty message. Every other terminal kind is `ERROR_FROM_TOOL` with the
    one-line message (kind, reason, guid, hint), and meta is `to_dict()`.
  - A blank `step_key` is `INVALID_ARGUMENTS` before any core call or ledger read. This is already
    in `_check_args`.
  - `latchStatus` joins `_SUCCESS_KINDS`, and the result-mapping test gains it.
  - Ledger-generated replies (replay, refusals) use adapter-owned meta
    `{stepKey, ledgerState, result?, replayed?}` outside the contract shape.

### Wait and timeout (XFR-01, XFR-06)
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

### Concurrency
- **D-12:** A non-blocking, module-level motion lock (fast D-13 pattern) wraps the whole `Transfer`
  (ledger load → terminal write). A second `Transfer` in the same process is refused at once with
  `ERROR_FROM_TOOL` "busy" and never parked. base_server's BUSY gate already serialises it, so the
  lock is a backstop. `Transfer` and `AcknowledgeFailure` stay out of `READ_COMMANDS`, while
  `GetFailureLatch` stays in it, so the latch is readable during a transfer.
  - `UNAVAILABLE_COMMANDS` is removed, along with its real-mode refusal.
  - `COMMAND_TO_SERVICE_METHOD` gains `GetFailureLatch` → `latch_status`.
  - `COMMAND_TO_SERVICE_METHOD` gains `AcknowledgeFailure` → `acknowledge_failure`.
  - `Transfer` is documented as the one multi-call command.

### Operator acknowledge and latch read (ACK-01, ACK-02)
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

### Safety invariant (XFR-05)
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

### Tests
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
- Whether the ledger lives in `tools/stack/ledger.py` or inside `server.py`. A separate module is
  preferred for testability.
- Exact message wording, within Phase 4 D-11 (one line, no core `explanation`).
- `REPLAY_WINDOW_S`, `DEFAULT_TRANSFER_TIMEOUT_S` and record retention values. They must stay
  constants. Suggested retention: prune `done` records older than 7 days on write; never prune
  `submitting`/`started`/`outcomeUnknown`.
- The exact ISO timestamp format, and whether the record stores the plan summary for operator
  display.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope and research
- `.planning/ROADMAP.md` § "Phase 5": goal, five success criteria, spike note, the settle-at-plan-time list
- `.planning/REQUIREMENTS.md` § "F5-safe Transfer" and § "Operator acknowledge": XFR-01..06, ACK-01..02
- `.planning/PROJECT.md`: Core Value (never a second transfer; no auto pause/abort/ack), Constraints, Key Decisions
- `.planning/research/SUMMARY.md`: Q2 (TimedOut / `submitOutcomeUnknown` / latch / thread safety, ~:150-180), Critical Pitfalls 1-4 (~:270-300), the reply-mapping table (~:398-410), and **§ Addendum (2026-10-29)** (core `934a621`: limits 1-2, fail-closed state, `latch_status`)
- `.planning/phases/04-stack-tool-registration-reads-estimate/04-CONTEXT.md`: D-01..D-22 (frozen proto, reply mapping, `READ_COMMANDS`, `_check_args`, the D-20 invariant this phase replaces)
- `.planning/phases/04-stack-tool-registration-reads-estimate/04-REVIEW-FIX.md` and `04-REVIEW-DISPOSITION.md`: the WR-01..WR-05 concurrency and Configure rules the new code must keep

### Adapter code (this repo)
- `tools/stack/server.py`:
  - constants: `UNAVAILABLE_COMMANDS` (:77), `READ_COMMANDS` (:83), `_SUCCESS_KINDS` (:123);
  - helpers: `_transfer_request` (:156), `_check_args` (:205), `_error_line` (:271), `_result_reply` (:292);
  - `StackServer`: `_apply_config` (records `ledger_dir`/`transfer_timeout_s`, :447), `_dispatchCommand` (:520), `_require_service` (:546), the `Transfer`/`AcknowledgeFailure`/`GetFailureLatch` placeholders (:582-592).
- `tools/tests/stack_test.py`: the Phase 4 harness, the D-20 invariant to replace, the STK-05 injected-slow test to re-prove on real Transfer, and the `_PINNED_CORE_SHA` pin test.
- `tools/fast/server.py`: the non-blocking motion lock (fast D-13) and the v1 no-auto-abort invariant pattern.
- `tools/tests/fast_test.py`: the AST invariant helper with a planted violation.
- `tools/base_server.py`: the BUSY gate and `_dispatchCommand`. **Do not edit.**

### STACK core (`~/data/nikko/stack-automation-layer` @ `934a621`, pinned in `tools/stack/requirements.txt`)
- `stack_automation_layer/service.py`:
  - `plan_transfer` (:855), `execute_transfer` (:888), `_reattach`/`wait_transfer` (:930-972, clamp `WAIT_TRANSFER_MAX_S=300` :194), `acknowledge_failure` (:1416), `latch_status` (:1518), `wait` (:2049);
  - `start_transfer` (:1223, ownership and in-flight :1284-1302);
  - constants: `PLAN_TTL_S=600` (:187), `DEFAULT_WAIT_TIMEOUT_S=600` (:164).
- `stack_automation_layer/results.py`: `TaskHandle.to_dict/from_dict` (:652), `Refused` (:699), `FailureAcknowledged` (:765), `LatchStatus` (:798), `Ran`/`Failed`/`Aborted`/`Cancelled`/`TimedOut`/`Lost` (:829-1080), `LOST_MESSAGES` (:1031)
- `stack_automation_layer/state_store.py`: the atomic-write and fail-closed pattern the ledger mirrors (D-02, D-04)
- `docs/runbooks/stack-validation.md`: operator recovery and acknowledge wording

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- From `server.py`:
  - `_transfer_request(cmd)` already builds the core `TransferRequest` (blank → `None`); use it for both the call and the fingerprint input.
  - `_check_args` already enforces a non-blank `step_key`, a finite `timeout_s` >= 0, a non-blank guid and `arm_inspected` ∈ {yes, no}.
  - `_result_reply`/`_error_line`/`_find_guid`/`_hint` already map kinds and pull guids.
- `_require_service()` returns the admitted service per thread (WR-02). `Transfer` must use it for every core call in one command.
- The core's `TaskHandle.to_dict()`/`from_dict()` round-trip is designed for persisted re-attach.

### Established Patterns
- Handler per message class name; `Estimate<Cmd>` constants (`EST_TRANSFER_S = 35`, `EST_ACK_S = 2`) are unchanged.
- An error message is one line built from structured fields and never from the core's `explanation` (Phase 4 D-11).
- Verification gate: `bin/make proto test` on `~/data/nikko/.venvs/galago-py310`. It was last green at 267 tests on `934a621`.
- `ERROR_FROM_TOOL` is the operator-visible code. galago-core hides `INVALID_ARGUMENTS`/`NOT_READY` text, so XFR-03's fingerprint mismatch and ACK-01's not-yes are invisible beyond the code. This is accepted per the requirements.

### Integration Points
- The `Config.ledger_dir` and `Config.transfer_timeout_s` values Phase 4 recorded are consumed here.
- Phase 6's GAL-02 protocol mints the per-run `step_key`s this ledger relies on (Pitfall 1).
- Phase 7 deploy: the ledger dir and the core's `STACK_STATE_DIR` must persist across service restarts on forb01.

</code_context>

<specifics>
## Specific Ideas

- The roadmap calls this the highest-risk phase. The ledger state machine (D-07) is the contract, so
  implement it as a small, pure, separately tested unit before wiring it into `Transfer`.
- The operator-facing message for every refusal names the next action: check the STACK Manager,
  read `GetFailureLatch`, `AcknowledgeFailure` after inspection, or mint a new step key. It never
  just reports a state name.

</specifics>

<deferred>
## Deferred Ideas

- An operator command to clear or inspect a ledger record (for example, `GetStepRecord`). It needs a
  proto change, which re-opens DEP-02. Consider it for v3.
- A `run_state`-style STACK heartbeat on the health `GetStatus` (carried from Phase 4's deferred
  list).
- A runbook rule for the ledger dir: never delete it, and back it up before a restart. This lands
  with Phase 7's deploy runbook.
- Adapter refusal of `Configure` while a run is in flight (v2 Future Requirement, shared with F.A.S.T.).

</deferred>

---

*Phase: 05-f5-safe-transfer-operator-acknowledge*
*Context gathered: 2026-10-29*
