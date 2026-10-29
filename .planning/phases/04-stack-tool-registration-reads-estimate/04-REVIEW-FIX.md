---
phase: 04-stack-tool-registration-reads-estimate
fixed_at: 2026-10-29T00:00:00Z
review_path: .planning/phases/04-stack-tool-registration-reads-estimate/04-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 4: Code Review Fix Report

**Fixed at:** 2026-10-29
**Source review:** .planning/phases/04-stack-tool-registration-reads-estimate/04-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (WR-01..WR-05; IN-01..IN-03 left alone by instruction)
- Fixed: 5 (WR-04 is partial by design, see below)
- Skipped: 0

**Verification:** each fix has a regression test that was confirmed to fail without the
source change and pass with it. The full gate `bin/make proto test` (ruff, mypy, unittest,
pytest) was run twice: first in the isolated worktree, then again in the main checkout after
the fast-forward. Both runs are green with 261 tests (250 baseline plus 11 new), ruff and mypy
clean. The main-checkout run is the reproducible one.

## Fixed Issues

### WR-01: A failing `OwnedService.close()` leaks the owner lock and leaves a dead service marked usable

**Files modified:** `tools/stack/server.py`, `tools/tests/stack_test.py`
**Commit:** 3567aa0
**Applied fix:** New `StackServer._teardown()` clears `_owned` and `service` first, then calls
`close()`. A `finally` releases the owner lock through the core's idempotent
`OwnerLock.release()`, because the core marks itself closed before the transport close and so
skips the release when that raises. `_configure` uses it for the close-first branch. Test
`TestConfigureCloseFails` injects a raising close callback. It asserts NOT_READY and FAILED, no
service, the old lock free, and that a same-endpoint retry opens a fresh session instead of
reusing the half-closed one.

### WR-02: A Configure that fails validation keeps the previous service, and reads are still served under status FAILED

**Files modified:** `tools/stack/server.py`, `tools/tests/stack_test.py`
**Commit:** 7f77504
**Applied fix:** Chose the second policy from the review: any `_configure` failure drops the
owner, so FAILED always implies no service. `_configure` now wraps `_apply_config` and calls
`_teardown()` on any exception. Test `TestConfigureFailureDropsService` covers a blank host and a
bad timeout. After each it checks no service, the lock released, and a bypass read returning
NOT_READY "stack: not configured" without touching the old transport.

### WR-03: No synchronisation between Configure and in-flight commands, or between concurrent Configures

**Files modified:** `tools/stack/server.py`, `tools/tests/stack_test.py`
**Commit:** b67fbd0
**Applied fix:** `_configure_lock` serialises Configures. A small in-flight tracker (a
`threading.Condition` with a reader count and a reconfiguring flag) lets real-mode
`_dispatchCommand` bracket each command with `_in_flight()`. `_configure` takes `_exclusive()`,
which blocks new commands and waits for in-flight ones before closing or swapping the owner, so
`_owned` and `service` change together and a read never meets a closed transport. The tracker
uses `Condition.wait_for`, not `.wait()`, because the AST invariant bans any `.wait()` call in
`tools/stack/`; the invariant test is unchanged and green. Simulated mode skips the tracker. Tests
(`TestConfigureConcurrency`): a Configure parks behind a blocked in-flight read, the old lock stays
held, the read completes SUCCESS on an open transport, then the Configure completes. Two concurrent
Configures to different ports leave one consistent owner and the other port's lock free.
Requires human verification: this is concurrency logic. The tests were run five times with no
flakes, but a Configure waits without a timeout for in-flight commands (each is bounded by the core's
transport timeouts).

### WR-04: The bypass read path mutates `last_error`, so a read can clear or overwrite a motion command's error

**Files modified:** `tools/stack/server.py`, `tools/tests/stack_test.py`
**Commit:** 28b0812
**Applied fix:** `last_error` on `StackServer` is now a property. Writes made on a thread inside a
bypassed read (a thread-local flag set in the `ExecuteCommand` override) are dropped, so successful,
refused and `ERROR_FROM_TOOL` reads no longer touch it. A save-and-restore approach was rejected
because it could clobber a motion command's concurrent write with a stale value. Tests: reads of
each kind leave a pre-set `last_error` and `GetStatus.error_message` unchanged, the same holds
while a Transfer is blocked BUSY, and a non-read command still records its error.
Requires human verification, and the fix is partial by design: the bypass exception handler still
sets `last_error = str(e)`. CONTEXT D-13 locks "turns an Exception into DRIVER_ERROR and sets
`last_error`", and the existing test
`test_exception_becomes_driver_error_with_last_error_and_status_kept` asserts it. So a read that
raises can still overwrite a motion command's error text. Closing that last gap means amending D-13
and that test.

### WR-05: `host` is interpolated into a URL unvalidated, while STACK credentials are sent to it

**Files modified:** `tools/stack/server.py`, `tools/tests/stack_test.py`
**Commit:** 6e1c585
**Applied fix:** `_apply_config` now requires the stripped host to fully match a hostname/IPv4
character class (`A-Za-z0-9._-`) or a bracketed IPv6 literal. That rejects `@ / ? # \`,
whitespace, scheme prefixes and stray colons. It also requires the port to be in 1..65535, with 0
still meaning the default. No hardware host literal was added to `tools/stack/`. The tests
(`TestConfigureHostValidation`) use `stack-server` and `10.150.1.125` only as strings handed to a
mocked `open_service`, never connected to. They accept `127.0.0.1`, `localhost`, `stack-server`,
`10.150.1.125`, `[::1]` and padded hosts. They reject the injection forms and out-of-range ports
before any open.
Note: a bare unbracketed IPv6 such as `::1` is now rejected, because the core would build the
malformed URL `http://::1:5005`; the bracketed form is accepted.

---

_Fixed: 2026-10-29_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
