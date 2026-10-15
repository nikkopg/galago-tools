---
phase: 02-wait-through-pauses-on-the-pinned-core
reviewed: 2026-10-15T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - scripts/fast_dryrun.py
  - scripts/fast_status.py
  - tools/fast/server.py
  - tools/tests/fast_test.py
findings:
  critical: 1
  warning: 2
  info: 1
  total: 4
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-10-15T00:00:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed `scripts/fast_dryrun.py`, `scripts/fast_status.py`, `tools/fast/server.py`,
and `tools/tests/fast_test.py` for everything changed since `d89f837` (the
previous phase-02 review commit), which spans commit `d9acdcf` ("fix(02): WR-01
fail closed on non-int errorCode for operator-abort and recovery replies"),
the phase-03 dry-run harness work, and the `201d987` `_is_no_error` wording fix.

The adapter code is generally careful: `_accepted()` centralizes the "did the
instrument really accept this" rule for `Abort()` and `_recovery_reply()`, the
motion-lock/control-command split is well tested, and `_run_in_flight()`'s
counter-based nesting is exercised against overlapping runs. However, the
headline finding is that the WR-01 fix in this same phase (`d9acdcf`) did not
actually reach every "safety-sensitive call site" its own docstring claims to
cover: `Resume()`'s crash-recovery branch still uses the old, loosely-typed
`!= 0` comparison instead of `_accepted()`, so the exact bug the commit set out
to eliminate still exists on one path, untested.

## Critical Issues

### CR-01: Resume()'s crash-recovery acceptance check still has the WR-01 bug the phase's own fix claims to have eliminated

**File:** `tools/fast/server.py:938-941`
**Issue:**

```python
accepted = service.resume(is_tip_broken=is_tip_broken)
if isinstance(accepted, Refused) or accepted.get("errorCode") != 0:
    return _recovery_reply("resume", accepted)
result = service.wait(
    RunHandle(plates=None, stale_done=False),
    on_progress=self._log_progress, timeout_s=self._timeout(None))
```

Commit `d9acdcf` (in this same review scope) introduced `_accepted()` precisely
because `errorCode == 0` is true for a bool `False` in Python (`False == 0`),
letting a malformed/falsy instrument reply be credited as "accepted" when it
is not an actual `int` `0`. That commit fixed `Abort()`'s operator-abort flag
and `_recovery_reply()`'s SUCCESS mapping, and `_accepted()`'s own docstring
states it exists "so the stricter definition can never diverge between the two
safety-sensitive call sites." It does diverge: `Resume()`'s crash-recovery
branch (reached when no motion command is in flight — the lock-acquired path)
never calls `_accepted()`. It inlines `accepted.get("errorCode") != 0`, which
is exactly the old, disproven pattern: if the instrument's `resume()` reply
carries `{"errorCode": False}` (the identical adversarial shape the phase
added a regression test for on `Abort()` — `test_abort_bool_false_error_code_is_not_success`),
`False != 0` evaluates to `False`, so the code treats resume as accepted and
proceeds straight into `service.wait(...)`, waiting on a run that was never
actually resumed, instead of immediately returning the rejection to the
operator via `_recovery_reply`. (The second `Resume()` path — lock not
acquired, a motion command already in flight — correctly calls
`_recovery_reply()` which uses `_accepted()`; only the crash-recovery wait
branch is affected.)

This is unexercised by the test suite: `test_crash_recovery_resume_waits_and_holds_the_lock`
and `TestRecoveryCommands` only use `errorCode: 0` (a real int) for the
crash-recovery path; no test drives `{"errorCode": False}` or a missing
`errorCode` key through this specific branch the way `test_abort_bool_false_error_code_is_not_success`
does for `Abort()`.

**Fix:**
```python
accepted = service.resume(is_tip_broken=is_tip_broken)
if not _accepted(accepted):
    return _recovery_reply("resume", accepted)
result = service.wait(
    RunHandle(plates=None, stale_done=False),
    on_progress=self._log_progress, timeout_s=self._timeout(None))
```
(`_accepted()` already handles the `Refused` case via its `isinstance(result, dict)`
guard, so the separate `isinstance(accepted, Refused)` check can be folded in or
kept — either way, replace the raw `!= 0` comparison.) Add a regression test
mirroring `test_abort_bool_false_error_code_is_not_success` for this exact
crash-recovery branch.

## Warnings

### WR-02: `_is_no_error()` repeats the same loose-comparison pattern WR-01 was meant to retire

**File:** `tools/fast/server.py:310-318`
**Issue:**
```python
def _is_no_error(outcome: object) -> bool:
    error_name = getattr(outcome, "error_name", None)
    error_code = getattr(outcome, "error_code", None)
    message = getattr(outcome, "message", None)
    return (error_code in (None, 0) and error_name in (None, "NoError")
            and not message)
```
`error_code in (None, 0)` is true for `error_code = False` as well (`False == 0`),
the same class of bug `_accepted()` was written to close elsewhere in this
file. `error_code` here comes from `RunOutcome` (a `fast_mcp` dataclass) rather
than a raw instrument dict, so the practical exposure is smaller than CR-01,
but it is the same anti-pattern this phase otherwise tries to eliminate, and if
`fast_mcp` ever passes through a non-int `error_code` (e.g. from imprecise JSON
deserialization upstream), an operator-abort with a real (falsy-but-not-zero)
error could be reported as "no error", silently dropping the error detail from
the operator-facing message.
**Fix:** Use the same strict check as `_accepted()`:
```python
return (type(error_code) in (type(None), int) and error_code in (None, 0)
        and error_name in (None, "NoError") and not message)
```
or factor a shared `_is_real_int_zero_or_none(value)` helper used by both
`_accepted()` and `_is_no_error()`.

### WR-03: gRPC channel is never closed in `fast_status.py`

**File:** `scripts/fast_status.py:34-51`
**Issue:** `channel = grpc.insecure_channel(...)` is created in `main()` but
never closed on either the success or `grpc.RpcError` return paths. For a
one-shot CLI invocation the OS reclaims the socket on process exit, so this is
not a functional bug today, but the script's own docstring stresses it "must
be safe to run against a live instrument at any time," implying frequent/
scripted invocation (e.g. polling loops, health-check wrappers) where an
unclosed channel per invocation is needless and inconsistent with the
cleanup discipline shown elsewhere in this phase (e.g. `fast_dryrun.py`'s
`channel.close()` in its self-test, `tearDown`/`addCleanup(channel.close)`
patterns throughout `fast_test.py`).
**Fix:**
```python
with grpc.insecure_channel(f"{args.host}:{args.port}") as channel:
    stub = tool_driver_pb2_grpc.ToolDriverStub(channel)
    ...
```

## Info

### IN-01: `fast_dryrun.py`'s `handle_command()` reaches into `FastServer`/`DryRunFastServer` private state from a free function

**File:** `scripts/fast_dryrun.py:174-181`
**Issue:**
```python
if cmd == "clear":
    with server._auto_pause_lock:
        server._suppress_rearm = True
        server._episodes_left = 0
    server.simulate_pause(None)
    with server._auto_pause_lock:
        server._suppress_rearm = False
    return True
```
`handle_command` directly manipulates `server._auto_pause_lock`,
`server._suppress_rearm`, and `server._episodes_left` — private (`_`-prefixed)
attributes of `DryRunFastServer` — from a module-level function rather than
through a method on the class. This is harness-only code (not shipped to
production), so the risk is low, but it couples the control-FIFO protocol
tightly to the class's internal locking scheme and will be easy to break
silently if `DryRunFastServer`'s internals are refactored without also
updating this free function.
**Fix:** Move the "clear" handling into a `DryRunFastServer.clear_pause_and_suppress_rearm()`
method that owns its own locking, and have `handle_command` call that method
instead of reaching into the instance's private state directly.

---

_Reviewed: 2026-10-15T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
