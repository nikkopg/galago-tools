---
phase: 01-adapter-control-path-run-state
reviewed: 2026-10-15T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - .gitignore
  - scripts/fast_dryrun.py
  - scripts/fast_status.py
  - tools/fast/requirements.txt
  - tools/fast/server.py
  - tools/tests/fast_test.py
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 01: Code Review Report (incremental re-review)

**Reviewed:** 2026-10-15
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

This is an incremental re-review of Phase 1's control-path/run-state files, covering changes made during Phases 2-3 (diff base `d2cead47`). `tools/fast/server.py` grew operator-abort bookkeeping (`_accepted`, `operator_abort` wording) and wait-through-pauses wiring; `scripts/fast_dryrun.py` is an entirely new simulated-only dry-run harness; `tools/tests/fast_test.py` grew substantially, including an AST-based adapter-invariant checker. The code is heavily and thoughtfully tested (the WR-01 `_accepted()` fail-closed rule for `errorCode` type-strictness is regression-tested against bools and strings for Abort/Pause). However, that same fail-closed rule was not applied uniformly: `Resume()`'s crash-recovery acceptance gate still uses a looser, pre-WR-01-style check that the rest of the module deliberately moved away from, and no test exercises it with a non-int `errorCode`. The new dry-run harness also has two concurrency/robustness gaps that are untested. No critical/security-impacting defects were found; the issues below are correctness and robustness gaps.

## Warnings

### WR-01: `Resume()`'s crash-recovery gate bypasses the module's own `_accepted()` fail-closed rule

**File:** `tools/fast/server.py:939`
**Issue:** `_accepted()` (server.py:391-403) is documented as "the single definition of 'the instrument accepted the command'... used by both `_recovery_reply`'s SUCCESS mapping and `Abort()`'s operator-abort bookkeeping so the stricter definition can never diverge between the two safety-sensitive call sites." It exists specifically to guard against `False == 0` and `"0" != 0` in Python (regression-tested in `fast_test.py` at `test_abort_bool_false_error_code_is_not_success`, `test_abort_bool_true_error_code_is_not_success`, `test_abort_str_zero_error_code_is_not_success`, and the parametrized `test_only_an_accepted_abort_sets_the_flag`).

  `Resume()`'s crash-recovery branch (lock acquired, no run in flight) does **not** call `_accepted()`:
  ```python
  accepted = service.resume(is_tip_broken=is_tip_broken)
  if isinstance(accepted, Refused) or accepted.get("errorCode") != 0:
      return _recovery_reply("resume", accepted)
  result = service.wait(...)
  ```
  If `service.resume(...)` ever returns `{"errorCode": False}` (or any other value that is `== 0` but not `type(code) is int`), `accepted.get("errorCode") != 0` evaluates `False`, so the code treats the resume as accepted and proceeds to call `service.wait(...)` — holding `_motion_lock` for the whole wait — instead of immediately reporting the rejection via `_recovery_reply`, which *would* correctly classify the same value as not-accepted. This is exactly the asymmetry WR-01 was introduced to eliminate at the other two call sites (`Abort()` and `_recovery_reply`'s own SUCCESS mapping), but it was missed here. No test in `fast_test.py` exercises this branch with a non-int `errorCode` (confirmed by grep: `test_resume_in_flight_failures_never_wait_or_release_the_owners_lock` only covers `Refused` and `{"errorCode": -2}`).
**Fix:**
  ```python
  accepted = service.resume(is_tip_broken=is_tip_broken)
  if isinstance(accepted, Refused) or not _accepted(accepted):
      return _recovery_reply("resume", accepted)
  result = service.wait(...)
  ```
  Add a regression test mirroring `test_abort_bool_false_error_code_is_not_success` for the crash-recovery Resume path (lock acquired, `service.resume.return_value = {"errorCode": False}`), asserting `service.wait` is never called.

### WR-02: `DryRunFastServer`'s auto-pause timer state is shared across overlapping simulated Transfers

**File:** `scripts/fast_dryrun.py:99-155`
**Issue:** `_arm_auto_pause`, `_fire_auto_pause`, and `ExecuteCommand`'s post-dispatch cleanup all mutate single instance attributes (`self._pause_timer`, `self._episodes_left`). The underlying `FastServer`/base_server already supports (and is tested to support, `fast_test.py::test_two_overlapping_simulated_transfers_read_running_until_both_end`) two overlapping simulated Transfers via the `_active_runs` counter. In the dry-run harness, if a second Transfer request arrives while a first is still sleeping:
  - `_arm_auto_pause()` for the second call cancels the first call's timer and resets `_episodes_left` to `_auto_pause_count`, discarding whatever auto-pause progress the first (still in-flight) transfer had armed.
  - When either Transfer's `ExecuteCommand` call returns, it unconditionally does:
    ```python
    with self._auto_pause_lock:
        if self._pause_timer is not None:
            self._pause_timer.cancel()
            self._pause_timer = None
        self._episodes_left = 0
    ```
    cancelling the *other* transfer's still-pending timer and zeroing its episode count, regardless of whether that other transfer is still in flight (`self._active_runs` is not consulted here).

  Net effect: anyone driving two overlapping Transfers through this harness (e.g., a UI test that double-clicks Run, or a test script issuing a second Transfer before the first's sleep ends) can silently lose the auto-pause episodes for whichever transfer is still running once the other one finishes — with no error or log indicating why the expected pause never fired.
**Fix:** Scope the auto-pause arm/cancel/reset to "no run remains in flight" rather than "this ExecuteCommand call returned", e.g. only cancel/reset in the `finally` when `self._active_runs == 0` (read under `_run_state_lock`), or key `_pause_timer`/`_episodes_left` by a per-call token so overlapping calls cannot clobber each other.

### WR-03: `_read_control` dies silently on any exception other than `OSError`

**File:** `scripts/fast_dryrun.py:191-202`
**Issue:**
  ```python
  def _read_control(server: DryRunFastServer, path: str, stop: threading.Event) -> None:
      while not stop.is_set():
          try:
              with open(path, "r") as fifo:
                  for line in fifo:
                      if not handle_command(server, line):
                          stop.set()
                          return
          except OSError:
              if stop.is_set():
                  return
              time.sleep(0.1)
  ```
  Only `OSError` is caught. `handle_command` can raise other exceptions (e.g. a malformed future command, or any bug in a handler) which propagate out of this daemon thread and kill it with no log message. The gRPC server keeps running, but the FIFO control path (`pause`, `clear`, `status`) becomes permanently unresponsive for the rest of the process's life, with nothing in the logs explaining why — a harness that is supposed to make pause/resume testing reliable instead fails silently and requires a restart with no diagnostic.
**Fix:**
  ```python
  for line in fifo:
      try:
          if not handle_command(server, line):
              stop.set()
              return
      except Exception:
          logging.exception("DRYRUN control: error handling line %r", line)
  ```

## Info

### IN-01: Crash-recovery `Resume()` never attributes a concurrent, non-stale operator Abort

**File:** `tools/fast/server.py:921-927, 946`
**Issue:** The crash-recovery wait's `_result_reply(result)` call passes no `operator_abort` flag, with the stated rationale that "a flag left by an earlier Abort could be stale." However, if an operator issues `Abort` *during* this same wait (Abort never takes `_motion_lock`, so it can reach the instrument while Resume's wait is in progress), the flag set by that Abort is not stale — it is for the exact run being waited on — yet the wording still falls back to the plain instrument phrasing ("run aborted at X%: ...") instead of "run aborted by operator at X%". This is a known, documented trade-off (the docstring calls it a "planner choice, D-09 scope"), not a regression, but it is a real behavior gap worth tracking if operator wording accuracy during crash-recovery resume becomes a priority.
**Fix:** If desired, read `operator_abort` under `_run_state_lock` immediately before building the reply (mirroring Transfer/RunProtocol), since by that point the wait has already completed and any flag set during it is necessarily current rather than stale.

### IN-02: Redundant `.gitignore` entry

**File:** `.gitignore:26-27`
**Issue:** `Procfile.tools` (line 27) is already matched by the `Procfile.*` glob on the line above (line 26); the explicit second entry is dead weight.
**Fix:** Remove line 27.

### IN-03: `COMMAND_TO_SERVICE_METHOD` is production-module state with no production consumer

**File:** `tools/fast/server.py:90-101`
**Issue:** This mapping is defined in the adapter module but is read only by `tools/tests/fast_test.py` (`TestOneToOneSurface`), never by `server.py` itself or any other runtime code path. This is a reasonable pattern for keeping a single source of truth that tests can verify against the real oneof surface, but it's worth a one-line comment at the definition site noting it exists for test introspection, so a future reader doesn't go looking for its runtime call site.
**Fix:** Add a short comment, e.g. `# Read only by tools/tests/fast_test.py::TestOneToOneSurface; no production caller.`

---

_Reviewed: 2026-10-15_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
