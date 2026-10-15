---
phase: 03-deploy-supervised-live-acceptance
reviewed: 2026-10-15T19:15:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - scripts/fast_dryrun.py
  - scripts/fast_status.py
  - tools/fast/server.py
  - tools/tests/fast_test.py
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-10-15T19:15:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed the phase's actual diff against `3b6a8d1`: the new `_is_no_error` helper and
operator-abort wording change in `tools/fast/server.py` (commits `7d77e23`/`201d987`), its
matching test in `tools/tests/fast_test.py`, and the two new scripts `scripts/fast_status.py`
(read-only `GetStatus` printer) and `scripts/fast_dryrun.py` (simulated-only dry-run harness).

Ran the full `fast_test.py` suite (140 tests, all pass, including the new
`test_message_for_treats_the_instruments_noerror_outcome_as_no_error`), `ruff check` (clean),
and `mypy --config-file=pyproject.toml tools` (clean — the Makefile's mypy gate only scans
`tools/`, not `scripts/`). Also executed `fast_dryrun.py --self-test` end to end; it passes.

The `_is_no_error`/wording change is correct and well covered by tests. No blocking defects
found. Two warnings worth fixing before relying on `fast_dryrun.py` for further supervised
live sessions: a timer/completion race that can leave a phantom "paused" `run_state` behind,
and an inconsistency with this same module's own documented bool-vs-int safety convention.
Three minor quality items are listed as info.

## Warnings

### WR-01: Auto-pause timer can leave a phantom "paused" run_state after the run/clear it targeted has already ended

**File:** `scripts/fast_dryrun.py:99-155` (`_arm_auto_pause`/`_fire_auto_pause`/`ExecuteCommand`), and `scripts/fast_dryrun.py:174-181` (`handle_command`'s `"clear"`)

**Issue:** `_fire_auto_pause` takes a snapshot of "is a run in flight" under `_auto_pause_lock`
+ `_run_state_lock`, releases both locks, and only *then* calls `self.simulate_pause(...)`
outside any lock:

```python
def _fire_auto_pause(self) -> None:
    with self._auto_pause_lock:
        with self._run_state_lock:
            in_flight = self._active_runs > 0
        if self._episodes_left <= 0 or not in_flight:
            return
        self._episodes_left -= 1
        episode = self._auto_pause_count - self._episodes_left
    self.simulate_pause(dict(WRONG_PLATE_PAUSE))   # <-- runs unsynchronized with run end
```

`ExecuteCommand`'s cleanup only calls `threading.Timer.cancel()` after the blocking Transfer
call returns; `cancel()` has no effect once the timer thread has already started running its
callback. So there is a real window where: the transfer's simulated sleep ends and
`_run_in_flight()`'s `finally` clears `_run_record["pause"]`/decrements `_active_runs` to 0 in
the main thread, while the timer thread — already past its `in_flight` check — calls
`simulate_pause(...)` a moment later and sets `_run_record["pause"]`/`"state"] = "paused"` again.
The result is a `run_state` that reads `paused` indefinitely for a run that already finished and
returned `SUCCESS` to the caller, with nothing in flight to `Resume`/`Abort` against (only a
manual `clear` FIFO command recovers it).

The same unsynchronized-call pattern lets a concurrently-firing timer re-pause immediately after
an operator's `clear` FIFO command: `_suppress_rearm` only guards the *rearm* logic inside
`_clear_pause`, not `_fire_auto_pause` itself, so a timer that is already past its `in_flight`
check when `clear` runs will still call `simulate_pause(...)` right after `clear` finishes.

This is a dev-only, simulated-only harness (no real instrument risk), but it is specifically
meant to drive a supervised walkthrough with an operator watching the run/tool pages, so a
spuriously reappearing "paused" prompt after a completed run is a real, if narrow-window,
correctness bug in the tool this phase ships for that purpose.

**Fix:** Make the in-flight check and the `simulate_pause` call atomic with respect to
`_run_in_flight`'s exit, e.g. tag each armed timer with the current run's generation/epoch
(incremented on every 0→1 `_active_runs` transition) and have `_fire_auto_pause` compare its
captured epoch against the current one while still holding `_run_state_lock`, only recording the
pause inside that same critical section:

```python
def _fire_auto_pause(self) -> None:
    with self._auto_pause_lock:
        with self._run_state_lock:
            if self._episodes_left <= 0 or self._active_runs == 0:
                return
            self._episodes_left -= 1
            episode = self._auto_pause_count - self._episodes_left
            # record the pause while still holding the lock that
            # _run_in_flight's exit also takes, so the two can't interleave
            self._run_record["pause"] = dict(WRONG_PLATE_PAUSE)
            self._run_record["state"] = "paused"
    logging.info("DRYRUN auto pause episode %d", episode)
```
(or equivalent — the key fix is closing the gap between the `in_flight` read and the pause
write).


### WR-02: `_is_no_error` diverges from this module's own documented bool-vs-int safety rule

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

`error_code in (None, 0)` uses Python `==` membership, which is true for `error_code is False`
(`False == 0`). This is exactly the footgun `_accepted()` 40 lines below explicitly guards
against and documents as a deliberate, safety-sensitive rule shared with `fast_mcp`:

> "WR-01: the single definition of "the instrument accepted the command" -- True only when
> `result` is a dict whose `errorCode` is the literal int 0 ... Mirrors
> `fast_mcp.orchestration._pause_info`'s own rule (`type(code) is int`) ... Used by both
> `_recovery_reply`'s SUCCESS mapping and `Abort()`'s operator-abort bookkeeping so the stricter
> definition can never diverge between the two safety-sensitive call sites."

`RunOutcome.error_code` is populated from raw instrument JSON via `fast_mcp.orchestration
._event_error` (`payload.get("errorCode")`) with **no** `type(code) is int` guard (unlike
`_pause_info`, which does guard it at line 98 of that module) — so an instrument payload that
ever reports `"errorCode": false` would reach `RunOutcome.error_code` as a Python `bool`, not an
`int`. `_is_no_error` would then treat it as "no error" via the `==` coincidence rather than by
an explicit, intentional rule, silently diverging from the one-definition principle the adjacent
`_accepted()` comment insists on keeping in sync.

In practice a JSON `false` happens to be semantically "no error" too, so this is not currently
exploitable into a wrong message, but it is an inconsistency with an explicitly documented
safety convention in the very same file, and the next person to extend this function (e.g. to
also special-case a nonzero-but-falsy value) will not get the same protection `_accepted()` has.

**Fix:** Mirror the established pattern:

```python
def _is_no_error(outcome: object) -> bool:
    error_name = getattr(outcome, "error_name", None)
    error_code = getattr(outcome, "error_code", None)
    message = getattr(outcome, "message", None)
    code_is_zero = type(error_code) is int and error_code == 0
    return ((error_code is None or code_is_zero)
            and error_name in (None, "NoError") and not message)
```

## Info

### IN-01: `fast_status.py` missing the project's standard `# type: ignore[attr-defined]` on the pb2 enum `.Name()` call

**File:** `scripts/fast_status.py:46`
**Issue:** `tool_base_pb2.ToolStatus.Name(reply.status)` fails `mypy` (`error: "type[ToolStatus]"
has no attribute "Name"`), the same known false positive already worked around with
`# type: ignore[attr-defined]` at `tools/fast/server.py:153` and twice in
`scripts/fast_dryrun.py:294` / `:153`. `bin/make test`'s mypy step only scans `tools/`, so this
doesn't break CI today, but it is inconsistent with the codebase's established handling and will
surface as a real error for anyone who runs `mypy` over `scripts/`.
**Fix:**
```python
"status": tool_base_pb2.ToolStatus.Name(reply.status),  # type: ignore[attr-defined]
```

### IN-02: `WRONG_PLATE_PAUSE`'s nested payload is shared (shallow-copied), not deep-copied, across pause records

**File:** `scripts/fast_dryrun.py:47-54`, used via `dict(WRONG_PLATE_PAUSE)` at lines 118, 166
**Issue:** `dict(WRONG_PLATE_PAUSE)` only copies the top-level keys; the nested `eventPayload`
dict (and its `wrongDetection` list/dict) is the exact same object shared by every pause record
produced over the harness's lifetime — including concurrent ones from overlapping auto-pause
episodes and FIFO `pause` commands. Nothing mutates it today, so this is latent rather than an
active bug, but it is an easy-to-reintroduce hazard the next time this module is extended (e.g.
to vary `wrongDetection` per episode).
**Fix:** Use `copy.deepcopy(WRONG_PLATE_PAUSE)` (or `json.loads(json.dumps(...))`) wherever a
fresh independent pause payload is needed.

### IN-03: `import signal` inside a function body instead of at module scope

**File:** `scripts/fast_dryrun.py:239`
**Issue:** All other imports in the file are at module top; this one is a local import inside
`serve_dryrun()`, with no apparent reason (no conditional/optional-dependency need — `signal` is
stdlib and always available).
**Fix:** Move `import signal` up to the top-level import block with the rest.

---

_Reviewed: 2026-10-15T19:15:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
