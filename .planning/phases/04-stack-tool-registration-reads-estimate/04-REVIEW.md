---
phase: 04-stack-tool-registration-reads-estimate
reviewed: 2026-10-29T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - tools/stack/server.py
  - tools/tests/stack_test.py
findings:
  critical: 0
  warning: 2
  info: 5
  total: 7
status: issues_found
---

# Phase 4: Code Review Report (incremental, after WR-01..WR-05 fixes)

**Reviewed:** 2026-10-29
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

This is an incremental review of `git diff 69e102a..HEAD` for `tools/stack/server.py` and `tools/tests/stack_test.py`. I also read the core at the pinned SHA (`ed8ce478`) for `OwnedService`, `OwnerLock` and `endpoint_key`.

All five earlier warnings are fixed as described. I found no blocker.

**Concurrency primitives.** I traced each one and found no deadlock, lost wakeup or reader-count leak.
- `_in_flight` increments `_readers` and enters the `try` with no raising statement between them. The decrement runs in a `finally`, and it notifies when the count reaches zero, which is the only condition `_exclusive` waits on.
- `_exclusive` clears `_reconfiguring` and calls `notify_all` in a `finally`, so an exception in the body cannot wedge new commands.
- Lock order is always `_configure_lock` then `_state`. `_in_flight` takes only `_state`, so there is no inversion.
- The `Condition` uses the default `RLock`, and the `with self._state` block spans the `yield` on one thread, so ownership is consistent.

**`last_error` property.** The thread-local suppression is correct.
- The setter tolerates the base `__init__` write, because `_read_bypass` does not exist yet and the write falls through to `_last_error`.
- The flag is reset in `finally` on every exit path, so a reused gRPC worker thread cannot carry a stale `active=True`.

**`_teardown`.** It is sound against the core: `OwnerLock.release()` is idempotent, and `ExitStack.close()` runs every callback.

**`_HOST_RE`.** It is anchored with `fullmatch` and is ASCII-only. The ASCII-only regex and `endpoint_key` agree on bracketed IPv6.

The two warnings are second-order effects of the new waiting behaviour. IN-01..IN-03 are carried forward unchanged.

## Warnings

### WR-01: Configure drains in-flight commands with no bound, and blocks every command including the BUSY-bypass reads while it does

**File:** `tools/stack/server.py:346-367` (with `369-382`)

**Issue:** `_exclusive` holds `self._state` for the whole body of `_configure`. That body includes `open_service`, which does a lock acquire, the identity probe and network I/O. It also does the `wait_for(not self._readers)` with no timeout.

Two consequences:
- **Reads stall behind Configure.** `_in_flight` has to take `_state`. So every command, including the D-13 reads that are meant to answer while a motion command holds the tool, is parked from the moment a Configure arrives until it finishes. The Configure itself waits for any in-flight Transfer. In Phase 5 a Transfer is in flight for up to the transfer timeout, which is minutes. A single Configure (for example the controller re-sending Config after a reconnect) therefore freezes all reads for that whole time. This is the opposite of what the bypass exists for.
- **Worker exhaustion.** `serve()` uses 10 workers. The parked commands and the Configure each occupy one. Once ten gRPC threads are parked, `GetStatus` and the health probe cannot be served at all, and the controller sees the tool as dead.

The same-endpoint early return (`_apply_config` line 403) also drains in-flight commands, although it changes nothing.

**Fix:** Bound the wait, and do not drain when nothing will change. For example:
```python
with self._configure_lock:
    if not self._wait_idle(timeout=CONFIGURE_DRAIN_TIMEOUT_S):  # wait_for(..., timeout=)
        raise RuntimeError("stack: busy, retry Configure when the running command ends")
```
`Condition.wait_for(predicate, timeout)` returns the predicate's value. Compute the endpoint key and return early outside `_exclusive` when the endpoint is unchanged. Do the I/O-heavy `open_service` outside `_state`, and swap `_owned` and `service` under it.

### WR-02: A command parked behind a Configure can leave status READY with no service, and could run against the wrong owner in Phase 5

**File:** `tools/stack/server.py:459-467` (with base `tools/base_server.py:220-239` and `Configure` at `98-121`)

**Issue:** The new wait makes an old race wide. A non-read command passes `parseCommand`, and base `ExecuteCommand` sets BUSY. It then parks in `_in_flight` for the whole Configure. This is easy to hit: Transfer, AcknowledgeFailure and GetFailureLatch all enter `_in_flight` before the refusal check.

When the Configure fails and is torn down, the order of events is:
1. The Configure thread leaves `_exclusive`.
2. Base `Configure` calls `setStatus(FAILED)` and sets `last_error`.
3. The parked command wakes, sees `service is None`, and replies NOT_READY "stack: not configured". That reply overwrites `last_error`.
4. The base `finally` runs `setStatus(READY)`.

If step 4 lands after step 2, GetStatus reports READY with no service, and the Configure's error text is replaced. Reads still return NOT_READY, but the operator-visible status is wrong until the next Configure.

A forward-looking variant: in Phase 5 a Transfer that was admitted against owner A but parked across a successful Configure to endpoint B would execute on B, because `self.service` is resolved after the wait.

**Fix:** Take the admission decision and the service snapshot together in `_in_flight`. If a Configure is running, refuse immediately with NOT_READY or ERROR_FROM_TOOL "stack: reconfiguring" instead of parking. This also removes most of WR-01. Alternatively, have `_dispatchCommand` capture `service` under `_state` once and pass it to the handlers.

## Info

### IN-01: Simulated to real Configure toggle silently ignores a changed host (carried forward)

**File:** `tools/stack/server.py:283` (via `tools/base_server.py:98-101`)

**Issue:** When a tool goes from simulated back to real, base `Configure` returns SUCCESS without calling `_configure`. The new host and port are ignored, and the previous owner (or none) is used. The shared `base_server.py` is intentionally unedited, so this only needs documenting or a test. Phase 5 should not rely on that path to re-point an endpoint. Related: a real to simulated Configure does not release the owner lock, so the endpoint stays held while the tool reports SIMULATED.

### IN-02: Truncation limits are bare literals, and `last_error` is not bounded like the reply (carried forward)

**File:** `tools/stack/server.py:266, 458, 446, 444`

**Issue:** The 300 and 500 limits are repeated literals. In the bypass exception handler the reply is truncated with `_one_line(str(e), 500)`, but `self.last_error = str(e)` is stored unbounded and is exposed through `GetStatus`.

**Fix:** Define `_ERROR_LINE_LIMIT` and `_ARG_LINE_LIMIT` constants. Store `_one_line(str(e), 500)` in `last_error`.

### IN-03: `logging.basicConfig` in `__main__` has no effect (carried forward)

**File:** `tools/stack/server.py:546`

**Issue:** `tools.base_server` already configures logging at import, so this second call is a no-op. The same pattern exists in sibling tools, so this is low priority.

### IN-04: `_teardown` reaches into the core's private `_lock` and silently skips the release if it is renamed

**File:** `tools/stack/server.py:336-338`

**Issue:** `getattr(owned, "_lock", None)` followed by `if lock is not None` means a core refactor that renames `_lock` turns the WR-01 safety net into a silent no-op. The lock leak would return with no signal. The SHA is pinned (D-22), but a bump will not fail loudly.

**Fix:** Drop the `None` fallback so a rename raises `AttributeError`, or add a test that asserts the core still exposes `OwnedService._lock` with an idempotent `release()`. Better, ask the core to release the lock in a `finally` inside `OwnedService.close()`.

### IN-05: `_in_flight` is not reentrant, so a nested dispatch would deadlock against a waiting Configure

**File:** `tools/stack/server.py:369-382`

**Issue:** If a command running inside `_in_flight` dispatches another command through `_dispatchCommand` on the same thread, the inner call blocks while a Configure holds `_reconfiguring`. The outer command cannot finish and decrement `_readers`, and the Configure waits for it. The base `runSequence` does this. Nothing in this phase calls it, but Phase 5 composite commands could.

**Fix:** Track a per-thread depth in a `threading.local` and skip the wait when the depth is greater than zero, or document that nested dispatch is forbidden.

---

_Reviewed: 2026-10-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
