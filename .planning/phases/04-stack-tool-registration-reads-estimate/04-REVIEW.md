---
phase: 04-stack-tool-registration-reads-estimate
reviewed: 2026-10-29T00:00:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - interfaces/controller.proto
  - interfaces/tools/grpc_interfaces/stack.proto
  - interfaces/tools/grpc_interfaces/tool_base.proto
  - pyproject.toml
  - tools/stack/__init__.py
  - tools/stack/requirements.txt
  - tools/stack/server.py
  - tools/tests/stack_test.py
findings:
  critical: 0
  warning: 5
  info: 3
  total: 8
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-10-29
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

The adapter is small and disciplined. I traced each safety property you listed and found no blocker.

- **No real-mode motion path.** Transfer, AcknowledgeFailure and GetFailureLatch return a constant refusal without touching the service. The AST invariant test pins this.
- **Allowlisted SUCCESS.** Only kinds in `_SUCCESS_KINDS` map to SUCCESS. The kind strings match the core's `ClassVar` kinds.
- **No credential leak.** Reply and log text carry no credentials. The core's `StackCredentialsMissing` message is fixed text, and `_error_line` and `_hint` never echo free text.
- **BUSY bypass leaves tool status alone.** The bypass never calls `setStatus`, `isReady` or `parseCommand`.
- **Proto numbering.** `ToolType` 24, `Command` 24 and `Config` 43 do not collide.
- **Tests.** The 103 tests pass.

The remaining problems are robustness issues around the Configure lifecycle and shared state under concurrency. The core's `OwnedService.close()` ordering is the source of the worst one (WR-01).

## Warnings

### WR-01: A failing `OwnedService.close()` leaks the owner lock and leaves a dead service marked usable

**File:** `tools/stack/server.py:296-306`

**Issue:** The core's `OwnedService.close()` sets `_closed = True` before calling `self._stack.close()`, then `self._lock.release()`. If the transport close raises, the lock is never released, and a second `close()` is a silent no-op.

In `_configure`, `self._owned.close()` is called before `self._owned = None` and `self.service = None`. So when close raises:
- `_owned` and `service` still point at the half-closed owner.
- Status is FAILED and the exception propagates.
- A retry Configure for the **same** endpoint hits the `self._owned.endpoint == key` early return, reports SUCCESS and READY, and serves reads from a closed client.
- A retry for a **different** endpoint calls the no-op `close()`, nulls the references and opens the new endpoint. The old lock is leaked until process exit.

This breaks the "lock released on failure" lifecycle property. The cause is partly in the core, but the adapter can defend against it.

**Fix:**
```python
if self._owned is not None:
    owned, self._owned, self.service = self._owned, None, None
    owned.close()   # references are already cleared, so a raise leaves "no service"
```
Clear the references first, and also try `owned._lock.release()` in a `finally` or report the leak. At minimum, never leave `service` set after a failed close. Add a test where `OwnedService.close` raises.

### WR-02: A Configure that fails validation keeps the previous service, and reads are still served under status FAILED

**File:** `tools/stack/server.py:284-292` (with the bypass at `324-337`)

**Issue:** The blank-host and bad-`transfer_timeout_s` checks raise before the old owner is closed. Base `Configure` sets FAILED and `NOT_READY` with the error text. `self._owned` and `self.service` stay live and keep the owner lock.

Because the read bypass skips `isReady`, every read command keeps succeeding against the old endpoint while `GetStatus` reports FAILED.

The operator is told the tool is not configured, yet reads answer from a different, previously configured STACK. The close-first branch (a failed open leaves no service) is handled correctly. The validation-failure branch is inconsistent with it.

**Fix:** Choose one policy and test it. Either:
- validate before touching state and keep the old service, but make the bypass require `self.status != FAILED` or a flag set only by a successful configure; or
- on any `_configure` failure, close and null the owner so FAILED always implies no service.

### WR-03: No synchronisation between Configure and in-flight commands, or between concurrent Configures

**File:** `tools/stack/server.py:283-307, 354-357`

**Issue:** `serve()` uses a 10-thread executor.

- The reads bypass the BUSY gate by design. A Configure can therefore run `self._owned.close()` while a bypassed read holds a local `service` reference obtained from `_require_service()`. That read then talks to a closed transport and surfaces a DRIVER_ERROR or `readFailed` instead of a clean refusal.
- Two concurrent Configures can both pass the endpoint comparison. Both call `open_service`. The loser gets `StackOwnedError`, but only after the first has swapped state. Then `_owned` and `service` can end up from different calls, because the two assignments at lines 305-306 are not atomic.

**Fix:** Guard `_configure` and the service lookup with a `threading.RLock`. Snapshot `(owned, service)` once per command under the lock. Alternatively, serialise Configure against the bypass path with a read/write lock.

### WR-04: The bypass read path mutates `last_error`, so a read can clear or overwrite a motion command's error

**File:** `tools/stack/server.py:329-336`; base behaviour at `tools/base_server.py:167-183`

**Issue:** The override never changes `status`, as intended. But `_dispatchCommand` in base real mode sets `self.last_error = response_tmp.error_message` for every reply. A successful read therefore resets `last_error` to `""`. A failed read, or the bypass exception handler at line 334, overwrites it. `GetStatus.error_message` is what galago-core shows the operator.

From Phase 5 on, a concurrent read can erase the failure text of the in-flight Transfer, or replace it with a read error, with no change in status. This is the same class of leak the BUSY-read design set out to avoid.

**Fix:** In the bypass, save and restore `self.last_error` around `_dispatchCommand`, for example `prev = self.last_error; try: ...; finally: self.last_error = prev`. Or have read replies skip `last_error` updates by overriding the real-mode branch for READ_COMMANDS. Add a test: a failing Transfer's `last_error` survives a concurrent read.

### WR-05: `host` is interpolated into a URL unvalidated, while STACK credentials are sent to it

**File:** `tools/stack/server.py:284-305`; core `composition.py` (`f"http://{host}:{port}"`)

**Issue:** The adapter only strips the host. A host containing URL-reserved characters changes where the JWT login and credentials go, for example `good-host@attacker`, `host/path#`, `host?x=` or an embedded `:`. `endpoint_key` only rejects an empty host. The STACK user and password are also sent to whatever address Config names.

Config comes from the trusted controller, so this is a hardening gap rather than an exploitable remote bug. It still sits on a credential boundary the review was asked to scrutinise.

**Fix:** Validate in `_configure` that the host is a bare hostname or IP literal, with no `/`, `@`, `?`, `#` or whitespace. For example:
```python
if not re.fullmatch(r"[A-Za-z0-9.\-]+|\[[0-9A-Fa-f:.]+\]", host):
    raise ValueError("stack: Config.host must be a bare hostname or IP address")
```
Also check that `port` is in 1..65535 explicitly, to give a clearer message than the core's.

## Info

### IN-01: Simulated to real Configure toggle silently ignores a changed host

**File:** `tools/stack/server.py:283` (via `tools/base_server.py:98-101`)

**Issue:** When a tool goes from simulated back to real, base `Configure` takes its first branch. It returns SUCCESS without calling `_configure`, so the new host and port in that request are ignored and the previous owner (or none) is used. The shared `base_server.py` is intentionally unedited, so this is only worth documenting, or covering with a test, so Phase 5 does not rely on that path to re-point an endpoint.

### IN-02: Truncation limits are bare literals, and `last_error` is not bounded like the reply

**File:** `tools/stack/server.py:257, 346, 334-336`

**Issue:** The 300 and 500 limits are repeated magic numbers. In the bypass exception handler the reply is truncated by `_one_line(str(e), 500)`, but `self.last_error = str(e)` is stored unbounded and then exposed through `GetStatus`.

**Fix:** Define `_ERROR_LINE_LIMIT` and `_ARG_LINE_LIMIT` constants. Store `_one_line(str(e), 500)` in `last_error`.

### IN-03: `logging.basicConfig` in `__main__` has no effect

**File:** `tools/stack/server.py:431`

**Issue:** `tools.base_server` already calls `logging.basicConfig` at import. This second call is a no-op, so the intended `DEBUG` level and default format are not what actually applies. The same pattern exists in sibling tools, so this is low priority.

---

_Reviewed: 2026-10-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
