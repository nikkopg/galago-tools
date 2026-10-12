---
phase: 01-adapter-control-path-run-state
reviewed: 2026-10-12T22:44:20Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - interfaces/tools/grpc_interfaces/fast.proto
  - interfaces/tools/grpc_interfaces/tool_base.proto
  - tools/fast/server.py
  - tools/tests/fast_test.py
findings:
  critical: 1
  warning: 1
  info: 3
  total: 5
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-10-12T22:44:20Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed the diff against `8febd4b` for the fast.proto/tool_base.proto schema additions (`Pause`, `StatusReply.run_state`) and the corresponding `tools/fast/server.py` adapter logic (control-command bypass of `base_server`'s readiness gate, the `_run_state_lock`/`_active_runs`/`_run_record` bookkeeping, the simulated `simulate_pause` dev hook, and Resume's two-path non-blocking-lock logic), plus the accompanying `tools/tests/fast_test.py`.

The safety invariants called out in the design doc hold up well under tracing: no code path in `server.py` calls `pause`/`resume`/`abort` on its own initiative (only `Pause()`/`Resume()`/`Abort()` do, and those are only reachable from the operator's own control commands); the adapter never compares against an instrument-state string on the control path (mechanically enforced by the file's own `TestAdapterInvariant` AST checker); physical yes/no decisions are never defaulted (`_decision` returns `None` on anything but exact "yes"/"no", and `None` is always rejected, never coerced to `False`); and `_build_run_state()`/`_get_status`/`GetStatus` never call anything beyond `.status()` on the service, so run-state observation cannot command the instrument.

One genuine concurrency/correctness bug was found in the new `_run_in_flight()` bookkeeping (it unconditionally resets the run record on *every* entry, not just the first, so an overlapping second run silently wipes out a recorded pause for a run that is still in flight) and one data-integrity inconsistency was found in `_log_progress` (it writes `percent` into `run_state` without running it through the same `_run_percent()` sanitizer that every other ingestion path in this file uses). Both are documented below, with lower-severity notes for the rest.

## Critical Issues

### CR-01: `_run_in_flight()` resets the run record on every entry, not just the first, silently clobbering an in-flight pause

**File:** `tools/fast/server.py:514-530`

**Issue:** `_run_in_flight()` is explicitly documented and tested as counter-based ("a counted run, not a boolean", D-19) so that two overlapping `LONG_RUNNING_COMMANDS` runs can be tracked simultaneously (`test_two_overlapping_simulated_transfers_read_running_until_both_end`). But its entry path unconditionally reassigns `self._run_record` on *every* call, regardless of the current `_active_runs` value:

```python
with self._run_state_lock:
    self._active_runs += 1
    self._run_record = {"state": "running", "percent": None, "pause": None}
```

Contrast this with the exit path, which correctly only touches shared state when the counter *transitions* to zero (`if self._active_runs == 0: self._run_record["pause"] = None`). The entry path has no equivalent `if self._active_runs == 0:` guard.

Concretely: if run A is in flight (`_active_runs == 1`) and has a pause recorded via `_record_pause`/`simulate_pause` (`_run_record["pause"]` is set, `_run_record["state"] == "paused"`), and a second overlapping run B then enters `_run_in_flight()` (`_active_runs` 1→2), B's entry **wipes the dict back to `{"state": "running", "percent": None, "pause": None}`**, erasing A's recorded pause even though A is still in flight and nothing resumed or aborted it. `_build_run_state()` will now report `"running"` instead of `"paused"` for A until A's pause is (if ever) re-recorded — with no Resume/Abort command having been issued. This directly undermines the stated guarantee in `_build_run_state()`'s own docstring: "a recorded pause always reads paused with its detail regardless of whether a run is in flight."

In real mode this can't happen today because `Transfer`/`RunProtocol` both take `_motion_lock` before entering `_run_in_flight()`, so only one can be in flight at a time. But in simulated mode — the exact scenario this phase's `simulate_pause` hook (ADP-10, D-20) exists to exercise for galago-core's pause-prompt UI testing — `_motion_lock` is never touched (base_server's simulated dispatch sleeps without calling `Transfer()`/`RunProtocol()` at all), so two overlapping simulated Transfers genuinely can both be in flight concurrently, and this is a live, reachable bug in exactly the feature this phase ships. It is not covered by `test_two_overlapping_simulated_transfers_read_running_until_both_end` because that test never records a pause during the overlap.

**Fix:** Only (re)initialize the record on the 0→1 transition, mirroring the exit path's 1→0 guard:

```python
@contextmanager
def _run_in_flight(self) -> Iterator[None]:
    with self._run_state_lock:
        if self._active_runs == 0:
            self._run_record = {"state": "running", "percent": None, "pause": None}
        self._active_runs += 1
    try:
        yield
    finally:
        with self._run_state_lock:
            self._active_runs -= 1
            if self._active_runs == 0:
                self._run_record["pause"] = None
```

## Warnings

### WR-01: `_log_progress` writes `percent` into `run_state` without the `_run_percent()` sanitization every other path uses

**File:** `tools/fast/server.py:532-538`

**Issue:** `_run_percent()` is documented as the canonical guard for anything that ends up in `run_state["percent"]` (D-11/ADP-05): "a bool, a string, NaN/infinity, or a missing value becomes None." It is applied on the `service.status()` mapping path (`_build_run_state`, line 634) and on the `_record_pause` path (line 551). It is **not** applied in `_log_progress`:

```python
def _log_progress(self, percent: int, state: str) -> None:
    logging.info("fast run progress %s%% (%s)", percent, state)
    with self._run_state_lock:
        self._run_record["percent"] = percent
        self._run_record["state"] = state
        if state == "running":
            self._run_record["pause"] = None
```

`_log_progress` is wired as `RunOptions(on_progress=self._log_progress)` for `Transfer`, `RunProtocol`, and `Resume`'s crash-recovery wait — i.e. it is the one callback that receives progress directly from `fast_mcp`/the instrument during a real run, the same class of untyped, instrument-sourced data that `_run_percent` exists to sanitize elsewhere in this file. If a percent value that `_run_percent` would reject (e.g. `NaN`, a bool, a string) is ever delivered through this callback, it is stored into `_run_record["percent"]` verbatim and then read back unfiltered by `_build_run_state()`'s real-mode in-flight branch (`"percent": self._run_record["percent"]`, line 619) straight into the gRPC `run_state` reply — the one code path in the file where this specific sanitizer is bypassed.

**Fix:** Route through the same sanitizer used everywhere else, following the same "only overwrite when valid" pattern already used in `_record_pause`:

```python
def _log_progress(self, percent: int, state: str) -> None:
    logging.info("fast run progress %s%% (%s)", percent, state)
    with self._run_state_lock:
        sanitized = _run_percent(percent)
        if sanitized is not None:
            self._run_record["percent"] = sanitized
        self._run_record["state"] = state
        if state == "running":
            self._run_record["pause"] = None
```

## Info

### IN-01: `_run_record`'s initial state is seeded as `"running"` although no run is in flight

**File:** `tools/fast/server.py:417-419`

**Issue:** `FastServer.__init__` seeds `self._run_record = {"state": "running", "percent": None, "pause": None}` before any run has started. Today this has no observable effect — `_build_run_state()` derives `"state"` from `_active_runs`/`pause` directly in simulated mode and only reads `_run_record["state"]` when `_active_runs > 0` in real mode, so the bogus initial value is never surfaced before the first `_run_in_flight()` call overwrites it. It is, however, a misleading placeholder that an incautious future change (e.g. a refactor that reads `_run_record["state"]` unconditionally) could turn into a real bug.

**Fix:** Seed it as idle for clarity: `{"state": "idle", "percent": None, "pause": None}`.

### IN-02: `tool_base.proto` has no trailing newline

**File:** `interfaces/tools/grpc_interfaces/tool_base.proto:136`

**Issue:** The file (including the newly added `run_state` field block touched by this diff) ends with `}` and no trailing newline, which `protoc`/most linters flag and which some diff/patch tools handle poorly.

**Fix:** Add a trailing newline at EOF.

### IN-03: `_run_percent`'s return type annotation doesn't match the int branch's actual return value

**File:** `tools/fast/server.py:156-167`

**Issue:** `_run_percent` is annotated `-> Optional[float]`, but for the `isinstance(value, int)` branch it `return value`s the original `int` unmodified rather than `float(value)`. This is harmless at runtime (protobuf's `Struct` and the tests both accept the int as-is, and Python's numeric tower makes this acceptable to most type checkers), but the annotation implies a normalized `float` output when the function can, by design, hand back either an `int` or a `float`.

**Fix:** Either widen the annotation to `Optional[t.Union[int, float]]` or explicitly document that ints are intentionally preserved verbatim (the latter matches the existing docstring's "the adapter never rounds, clamps or converts" intent better than silently converting to float).

---

_Reviewed: 2026-10-12T22:44:20Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
