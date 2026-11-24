---
phase: 04-stack-tool-registration-reads-estimate
fixed_at: 2026-10-29T00:00:00Z
review_path: .planning/phases/04-stack-tool-registration-reads-estimate/04-REVIEW.md
iteration: 2
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 4: Code Review Fix Report

**Fixed at:** 2026-10-29
**Source review:** .planning/phases/04-stack-tool-registration-reads-estimate/04-REVIEW.md
**Iteration:** 2

**Summary:**
- Findings in scope: 2 (WR-01, WR-02 of the incremental review; IN-01..IN-05 left alone by instruction)
- Fixed: 2 (both flagged "requires human verification": concurrency logic)
- Skipped: 0

**Verification:** both fixes have regression tests, and each was confirmed to fail when the
corresponding piece of the source change was reverted. Gate `bin/make proto test` (ruff, mypy,
unittest, pytest) was run in the main checkout, directly on `feat/stack-tool` with no worktree
(`workflow.use_worktrees=false` path). It is green with 267 tests (261 baseline plus 6 new), ruff
and mypy clean. The new and existing concurrency tests were run 5 times in a row: 120/120 passed
each time, with no flakes. The tests use Events and gRPC deadlines, not sleeps. The only timing
is a 0.05 s drain timeout that is patched into the busy test, and its outcome does not depend on
timing because the in-flight read stays blocked until the test releases it.

## Design (the reviewer's recommendation, as approved)

Never park a command behind a Configure.
- Admission and the service snapshot are taken together under `_state`. While a Configure is in
  progress a command is refused immediately. Handlers use the captured service.
- Configure's drain wait is bounded by `CONFIGURE_DRAIN_TIMEOUT_S` (5.0 s). On timeout it fails
  with a one-line "busy" message and the current owner is kept. The same-endpoint early return
  happens before any drain.
- `_state` is never held across `open_service`. `_owned` and `service` are swapped under it.

## Fixed Issues

### WR-01: Configure drains in-flight commands with no bound, and blocks every command including the BUSY-bypass reads while it does

**Files modified:** `tools/stack/server.py`, `tools/tests/stack_test.py`
**Commit:** d46fd4a
**Status:** fixed: requires human verification
**Applied fix:**
- `_exclusive()` now holds `_state` only to set `_reconfiguring` and to wait, with
  `CONFIGURE_DRAIN_TIMEOUT_S`, for `_readers` to reach zero. On timeout it clears the flag and
  raises the new `_ConfigureBusy("stack: busy, a command is still running; retry Configure when
  it ends")`, having changed nothing. `_state` is released before the body runs.
- `_apply_config` computes the endpoint key first and returns before any drain when the endpoint
  is unchanged. Otherwise the teardown, `open_service` and the swap run inside `_exclusive()`, and
  `_owned`/`service` are assigned together under `_state`. `open_service` runs with `_state` free.
- `_configure` re-raises `_ConfigureBusy` without dropping the owner. Every other failure still
  drops it (iteration-1 WR-02). If a validation failure leaves an owner in place, the drop takes
  the same bounded drain. If that drain is busy, the busy refusal wins and the owner is kept.
- `_teardown` clears `_owned`/`service` under `_state` and closes outside it. The lock release in
  `finally` is preserved (iteration-1 WR-01).

Tests (`TestConfigureBusy`):
- A Configure to a new endpoint and a malformed Configure, both issued while a read is in
  flight, return NOT_READY "stack: busy" (one line). `open_service` is not called again, and the
  owner is not closed, still held, and still serving. After the read ends the same Configure
  succeeds.
- A same-endpoint Configure succeeds while a read is in flight and the drain timeout is tiny,
  which proves it does not drain.
- While `open_service` is blocked, `_state` can be acquired without blocking.

### WR-02: A command parked behind a Configure can leave status READY with no service, and could run against the wrong owner in Phase 5

**Files modified:** `tools/stack/server.py`, `tools/tests/stack_test.py`
**Commit:** 6d46926
**Status:** fixed: requires human verification
**Applied fix:**
- `_in_flight()`, which parked commands, is replaced by `_admit()` and `_leave()`. `_admit()`
  takes `_state` once, refuses if `_reconfiguring` is set, and otherwise increments `_readers`
  and returns `self.service` as the snapshot.
- `_dispatchCommand` stores that snapshot in a thread-local (saved and restored, so a nested
  dispatch is safe). `_require_service()` reads the snapshot and never `self.service` inside a
  dispatch. It falls back to `self.service` only when a handler is called directly outside one.
- Refusal reply: `ERROR_FROM_TOOL "stack: reconfiguring"`. I chose ERROR_FROM_TOOL over
  NOT_READY because galago-core hides the text of NOT_READY/INVALID_ARGUMENTS replies from the
  operator (the same reason D-18 uses it), and this condition is transient, so the operator
  should see "retry". It is one line.
- `StackServer.setStatus` now holds a `READY` at `FAILED` while a failed Configure has left no
  service. `_configure_failed` is set when `_configure` drops the owner on failure and cleared on
  success. This closes the remaining WR-02 race: base `ExecuteCommand`'s trailing
  `setStatus(READY)` can land after base `Configure` has set FAILED, even when the command was
  admitted before the Configure. The bypass read path still never calls `setStatus`.

Tests (`TestReconfiguringAdmission`):
- A read and a Transfer sent while a Configure is blocked in `open_service` return
  "stack: reconfiguring" immediately (5 s gRPC deadline, so parking would fail loudly). GetStatus
  stays answerable, and admission reopens when the Configure ends.
- A handler keeps its admitted service even if `server.service` is swapped mid-command.
- A motion command's trailing `setStatus(READY)` is held until after a failing Configure has
  reported FAILED. The status stays FAILED with no service, and the next successful Configure
  returns it to READY.

**Residual behaviour to be aware of (not defects against the brief):**
- A busy refusal still makes base `Configure` set status FAILED and `is_connected = False` (the
  shared `base_server.py` is not edited), while the healthy owner is kept and keeps serving
  reads. When the blocking command is a motion command, its trailing `setStatus(READY)` restores
  READY. When the blocker is only a read, the status stays FAILED until the next successful
  Configure.
- During a Configure's drain and open window, every real-mode command, including the Phase 5
  refusals (Transfer, AcknowledgeFailure, GetFailureLatch), gets "stack: reconfiguring" rather
  than their own message.
- A side effect on IN-05, which is left unchanged: a nested dispatch while a Configure is
  draining is now refused instead of deadlocking.

## Skipped Issues

None.

## Locked constraints check

`open_service(host, port, owner="galago")` is still the only call shape. `TestAdapterInvariant`
is green, and the new code uses `Condition.wait_for`, not `.wait(`. No STACK motion method is
called, and the read bypass never calls `setStatus`, `isReady` or `parseCommand`. `tools/base_server.py`,
`~/data/nikko/stack-automation-layer` and `~/data/nikko/galago-core` are untouched. Nothing was
pushed, and `.planning/state.json` was not committed. The tests use only mocks, fake transports,
closed loopback ports and temp lock dirs.

---

## Iteration 1

Previous run (source review: the earlier REVIEW.md, WR-01..WR-05, fix scope critical_warning).
All five were fixed, with commits `3567aa0..6e1c585`. The gate was green with 261 tests.

| Finding | Summary | Commit |
|---------|---------|--------|
| WR-01 | `_teardown()` clears `_owned`/`service`, then closes, and releases the owner lock in a `finally`, so a raising `OwnedService.close()` leaks no lock. | 3567aa0 |
| WR-02 | Any `_configure` failure drops the owner, so FAILED always implies no service. | 7f77504 |
| WR-03 | `_configure_lock` serialises Configures. A `Condition`-based in-flight tracker makes Configure wait for in-flight commands before it swaps the owner. This is the code now reworked in iteration 2. | b67fbd0 |
| WR-04 | `last_error` is a property that drops writes made inside a bypassed read (thread-local). The bypass exception handler still records the error (D-13). | 28b0812 |
| WR-05 | `Config.host` must fully match a hostname/IPv4 class or a bracketed IPv6 literal, and the port must be 1..65535. | 6e1c585 |

---

_Fixed: 2026-10-29_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_
