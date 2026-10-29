---
phase: 05-f5-safe-transfer-operator-acknowledge
plan: 02
subsystem: stack-transfer-tracer
tags: [transfer, step-key-ledger, write-ahead, flock, ast-invariant, stack-core-934a621, safety]

requires:
  - phase: 05-f5-safe-transfer-operator-acknowledge
    provides: "05-SPIKE.md section 6 binding ledger contract (schema, constants, templates) and amendment A-1"
  - phase: 04-stack-tool-registration-reads-estimate
    provides: "frozen stack.proto, reply mapping (_result_reply, _one_line), _require_service admission, Config.ledger_dir / transfer_timeout_s recorded"
provides:
  - "tools/stack/ledger.py: core-free, proto-free step-key ledger (strict fail-closed load, create-if-absent claim, mark_started, mark_done, flock + atomic write)"
  - "Real-mode StackServer.Transfer fresh path: plan_transfer -> write-ahead submitting record -> execute_transfer -> started -> one wait -> done, returning SUCCESS on ran"
  - "Module-level non-blocking motion lock, wait budget (D-11), instance id, endpoint fingerprint"
  - "XFR-05 call-site AST rule set with planted violations (replaces Phase 4's blanket no-motion rule)"
  - "_FakeCore / _TransferTestCase fixtures reused by plans 05-03..05-07"
affects: [05-03, 05-04, 05-05, 05-06, 05-07, phase-07-runbook]

actuals:
  tokens: 11400
  tasks: 3
  commits: 5
plan_head_before: 9134f742b554f3f225934c2191db75dfef87ed5d
plan_head_after: a2d653f5072107ea2f7aaa7693ed41e18a2ddc42

tech-stack:
  added: []
  patterns:
    - "Write-ahead claim before the single execute_transfer call site; once claimed, any failure leaves the record at submitting or later, never absent"
    - "Ledger mutation = flock on sibling lock file, strict re-load under the lock, one change, atomic save (mkstemp, fsync, os.replace, dir fsync)"
    - "Tests fake the core with a _FakeCore that implements only the six methods the adapter may touch"
    - "Call-site invariant via AST: single site per guarded method, loop-ancestor walk, lineno order against the claim call"

key-files:
  created:
    - tools/stack/ledger.py
  modified:
    - tools/stack/server.py
    - tools/tests/stack_test.py

key-decisions:
  - "Existing-record interim rule: any step key that already has a ledger record gets ERROR_FROM_TOOL and no core call (replaced by decide() in plan 05-06)"
  - "A non-TaskHandle execute_transfer result keeps the record at submitting and returns the Phase 4 _result_reply (interim fail-safe; plan 05-05 adds the release whitelist)"
  - "_finish writes done only for the A-1 terminal set (ran, failed, aborted, lost(taskNotFound)); a timedOut wait leaves the record started"
  - "Ledger JSON serialisation failure is mapped to LedgerError('unwritable') so a non-serialisable handle cannot escape past the claim as a raw exception"
  - "fcntl is imported lazily before the mkdir/lock-file open, so an unsupported platform creates nothing"

patterns-established:
  - "_stack_adapter_violations stays pure and assertion-free; new rules append strings and tests plant violations with _plant or a deep-copy rename"

requirements-completed: [XFR-01, XFR-02, XFR-05]

coverage:
  - id: D1
    description: "A real-mode Transfer with a fresh step key runs plan, write-ahead, execute, started, one wait, done in one command and returns SUCCESS with empty message and meta equal to Ran.to_dict()"
    requirement: "XFR-01"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestTransferFreshPath.test_the_happy_path_is_success_with_ran_meta_and_the_ordered_calls"
        status: pass
    human_judgment: false
  - id: D2
    description: "The ledger file holds the step key in state submitting (with fingerprint and instance id) at the instant execute_transfer is called; it ends done with handle and result; dir 0700, files 0600; blank ledger_dir resolves under XDG_STATE_HOME"
    requirement: "XFR-02"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestTransferFreshPath.test_the_write_ahead_record_is_on_disk_when_execute_transfer_is_called"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestTransferFreshPath.test_a_fresh_ledger_directory_is_0700_and_the_files_are_0600"
        status: pass
    human_judgment: false
  - id: D3
    description: "A repeated step key sends no plan_transfer or execute_transfer; a corrupt ledger refuses with the path and 'do not delete it', no core call, bytes unchanged; an execute exception leaves the record at submitting and names only the exception type"
    requirement: "XFR-02"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestTransferFreshPath (test_a_repeat_of_the_step_key_sends_nothing, test_a_corrupt_ledger_refuses_the_transfer_and_is_left_untouched, test_execute_raising_leaves_the_record_submitting)"
        status: pass
    human_judgment: false
  - id: D4
    description: "XFR-05 call-site invariant: no forbidden motion/safe-position/validate call; execute_transfer and plan_transfer each have exactly one call site in _run_fresh; execute has no loop ancestor and follows the claim; no getattr or alias indirection; acknowledge_failure confined to AcknowledgeFailure; each rule has a planted violation"
    requirement: "XFR-05"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestAdapterInvariant (23 tests, 13 new)"
        status: pass
    human_judgment: false
  - id: D5
    description: "The crash-safety claim: a crash between the temp-file write and os.replace leaves the previous ledger intact (fsync of temp, os.replace, directory fsync)"
    requirement: "XFR-02"
    verification: []
    human_judgment: true
    rationale: "The plan marks this truth verification: backstop. The ordering is in Ledger._save and reviewable by reading, but no test injects a crash between the fsync and the replace"

duration: 25min
completed: 2026-10-29
status: complete
---

# Phase 5 Plan 02: Fresh-Path Transfer Tracer Summary

**A real-mode `Transfer` now runs plan, write-ahead `submitting` record, `execute_transfer`, `started`, one `wait` and `done` through a new core-free flock-and-atomic-write step ledger, and Phase 4's blanket no-motion AST rule is replaced by XFR-05 call-site rules (single sites, no loop, after the claim, no indirection) with 13 new planted-violation tests.**

## Performance

- **Duration:** about 25 min (start time was not captured; approximate)
- **Completed:** 2026-10-29T08:49:04Z
- **Tasks:** 3 (tracer, migration, AST rules)
- **Files:** 1 created (`tools/stack/ledger.py`), 2 modified (`tools/stack/server.py`, `tools/tests/stack_test.py`)
- **Gate:** `bin/make proto test` exits 0: ruff clean, mypy "no issues found in 93 source files", 293 tests passed (was 120 in `stack_test.py` alone before; that file now has 146 tests)

## Accomplishments

- **Tracer proven on one path.** gRPC -> `Transfer` -> ledger on disk -> `_FakeCore` -> reply works end to end. Fake call order is `[plan_transfer, execute_transfer, wait]`, execute count 1, reply SUCCESS with empty message and meta equal to `Ran.to_dict()`. The fake `execute_transfer` reads the ledger file when called and sees the key in state `submitting` with the 64-hex fingerprint and this server's instance id.
- **Ledger v1 (`tools/stack/ledger.py`, stdlib only).** `resolve_ledger_dir` (explicit absolute dir, else `$XDG_STATE_HOME/galago-tools/stack`, else `~/.local/state/galago-tools/stack`; a relative value raises `ValueError`), `fingerprint` (sha256 of canonical JSON of version, endpoint and `dataclasses.asdict(request)`), `is_terminal` (A-1 set), `LedgerError(reason, path)`, and `Ledger` with strict fail-closed `load`, create-if-absent `claim`, `mark_started`, `mark_done`. Every mutation takes `fcntl.flock` (non-blocking poll to `LOCK_TIMEOUT_S = 5.0`, then "busy"), re-loads strictly under the lock and saves atomically. `type(version) is int` rejects a JSON `true`.
- **`Transfer` handler.** Non-blocking module `_MOTION_LOCK` (busy reply when held), byte-exact step key, `_endpoint()`, `_wait_budget()` (D-11, clamped to 3600 s), ledger errors and a relative `ledger_dir` mapped to `_ledger_error_reply` (names the path, "do not delete it", no core call). `Transfer` left `UNAVAILABLE_COMMANDS`, so an unconfigured Transfer is `NOT_READY "stack: not configured"`.
- **`_run_fresh` holds the only `plan_transfer` and `execute_transfer` calls.** Claim before execute; execute inside `try/except Exception` (record stays `submitting`, reply carries `type(exc).__name__` only); a `TaskHandle` leads to `mark_started` then exactly one `service.wait(handle, timeout_s=budget)` then `_finish`. A ledger write failure after the wait turns even `ran` into `ERROR_FROM_TOOL` (D-04) without stopping the wait.
- **XFR-05 rules.** `_FORBIDDEN_SERVICE_CALLS` shrinks to `start_transfer`, `cancel_transfer`, `go_to_safe_position`, `wait_safe_position`, `validate_transfer`. New rules: `_SINGLE_SITE_CALLS`, `_LOOP_NODES` ancestor walk (For, AsyncFor, While, three comprehensions, GeneratorExp, Lambda), `_WRITE_AHEAD_CALL` lineno order, getattr-by-string, `_ACK_CALL` confined to `_ACK_HANDLER` at most once. `wait_transfer` and `wait` stay unrestricted.
- **TestAdapterInvariant went from 10 to 23 test methods (+13).** Counted with `ast` before and after Task 3.

## Task Commits

1. **Task 1 RED:** `fc75e51` `test(05-02): add failing fresh-path Transfer tracer`
2. **Task 1 GREEN:** `33d9d3f` `feat(05-02): fresh-path Transfer through a write-ahead step ledger (XFR-01, XFR-02)`
3. **Task 2:** `a58c70d` `test(05-02): migrate Phase 4 refusal and no-motion tests to the wired Transfer (D-16)` (changes only `tools/tests/stack_test.py`)
4. **Task 3 RED:** `94730bb` `test(05-02): planted violations for the XFR-05 call-site rules`
5. **Task 3 GREEN:** `a2d653f` `feat(05-02): XFR-05 call-site invariant replaces the blanket no-motion rule (D-16)`

`git log --reverse --grep='(05-02)'` starts with a `test` commit, so the plan's ordering check passes.

## RED Evidence (quoted)

Task 1 RED, `pytest -k TestTransferFreshPath` before any production code: `12 failed, 120 deselected, 12 errors`. The 12 errors are the cleanup assertion hitting `AttributeError: module 'tools.stack.server' has no attribute '_MOTION_LOCK'`. The 12 failures:

```
AssertionError: 'RuntimeError' not found in 'stack: Transfer is not available in this build'
AssertionError: '/tmp/tmpiyfw8gxd/ledger/stack-ledger.json' not found in 'stack: Transfer is not available in this build'
AssertionError: Lists differ: [] != ['plan_transfer']
FileNotFoundError: [Errno 2] No such file or directory: '/tmp/tmpq55636t1/ledger/stack-ledger.json'
FileNotFoundError: [Errno 2] No such file or directory: '/tmp/tmpjfoiu2wi/ledger'
AssertionError: 0 != 1   (write-ahead probe: execute_transfer was never called)
```

After the GREEN commit `12 passed`. Right after it, five Phase 4 tests were red as the plan predicted (`test_allowed_read_calls_are_not_reported`, `test_real_sources_are_clean`, `test_every_oneof_message_has_a_handler_and_the_sets_are_disjoint`, `test_valid_phase_5_commands_are_refused_without_a_service_call`, `test_transfer_and_ack_with_good_arguments_are_refused_not_unconfigured`, e.g. `AssertionError: 'stack: not configured' != 'stack: Transfer is not available in this build'`); Task 2 turned them green (`133 passed`).

Task 3 RED, `pytest -k TestAdapterInvariant` before the rule logic: `11 failed, 12 passed`. The 11 failures were the new planted tests (second execute/plan site, loops, claim order, getattr, alias, acknowledge outside and twice, cross-module count, required-function pin, removed execute call). The 2 negative controls (`wait_transfer` in a loop, one `acknowledge_failure` inside its handler) passed in RED by design. After the rule logic: `23 passed`.

## Decisions Made

- **Existing key means no call (interim).** `Transfer` refuses any key with a record via `ERROR_FROM_TOOL` and meta `{stepKey, ledgerState}`, with no `plan_transfer` or `execute_transfer`. Plan 05-06 replaces this with `decide()`.
- **Non-handle execute results are kept, not released (interim).** Anything other than a `TaskHandle` from `execute_transfer` leaves the record `submitting` and returns the Phase 4 reply. Plan 05-05 adds the release whitelist.
- **Serialisation errors are ledger errors.** `_save` maps `TypeError`/`ValueError` from `json.dumps` to `LedgerError("unwritable")`, so a bad handle cannot escape the `LedgerError` handlers after the claim.
- **Lock-file order.** `fcntl` is imported first, so an unsupported platform raises `LedgerError("unsupported")` before any directory or lock file is created.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] mypy `no-any-return` in `_endpoint`**
- **Found during:** Task 1 verify (`mypy`, part of `bin/make test`)
- **Issue:** `endpoint_key` is untyped in the core, so returning it from a function annotated `-> str` failed `Returning Any from function declared to return "str"`.
- **Fix:** wrapped in `str(...)`.
- **Files modified:** `tools/stack/server.py`
- **Commit:** `33d9d3f`

### Plan-scope choices (not defects)

- **Later-write-failure message has no latch clause yet.** Spike 6f's template is `transfer <kind>, but the ledger could not record it; <latch clause>; re-running ...`. The plan's `_finish(ledger, key, result, write_failed)` signature has no service to call `latch_status()` on, and the plan text specifies only `transfer <kind>, but the ledger could not record it`. The clause (and `latch_status` handling) lands with plans 05-04/05-05. Today's text is `stack: transfer <kind>, but the ledger could not record it; re-running this step key will not send a second transfer`.
- **One rule beyond the plan.** An uncalled attribute reference to a guarded method (`fn = service.execute_transfer`) is reported ("referenced without a call"), closing an alias route around the single-call-site rule. It has its own planted test (`test_an_aliased_guarded_method_is_reported`).
- **Constants placed with the test commit.** `_SINGLE_SITE_CALLS`, `_LOOP_NODES`, `_WRITE_AHEAD_CALL`, `_ACK_CALL`, `_ACK_HANDLER` are defined in the Task 3 RED commit (the tests reference them); the rule logic and `_REQUIRED_FUNCTIONS` update are in the GREEN commit.
- **Planted nodes carry small line numbers.** `_plant` uses `ast.parse(statement)` line numbers, so a planted `execute_transfer` inside `_run_fresh` also trips "before the write-ahead claim". That is a correct report (the planted call is not after the claim), and the tests assert on the fragment they target.

## Issues Encountered

None beyond the mypy fix. `~/.local/state/galago-tools` does not exist after the full gate, confirming no test wrote the real ledger.

## Authentication Gates

None.

## Known Stubs

None in the data-flow sense. Two intentional interim rules, both named in the plan and resolved by later plans: the existing-record refusal (plan 05-06) and the keep-everything-but-a-handle execute branch (plan 05-05). They fail safe (nothing is ever re-sent).

## Threat Flags

None. The ledger directory, lock file and `execute_transfer` call site are the surface already in the plan's threat model (T-05-02..T-05-07). No network endpoint, auth path or schema changed; `tools/base_server.py` and `interfaces/` are unchanged since `e1bf845`.

## Self-Check: PASSED

- `tools/stack/ledger.py`, `.planning/phases/05-f5-safe-transfer-operator-acknowledge/05-02-SUMMARY.md`: present.
- Commits `fc75e51`, `33d9d3f`, `a58c70d`, `94730bb`, `a2d653f` are all ancestors of HEAD.
- `bin/make proto test` exit 0; ledger.py imports nothing from `stack_automation_layer` or `tools.grpc*`; `git diff --quiet e1bf845 -- tools/base_server.py interfaces/` exits 0.
