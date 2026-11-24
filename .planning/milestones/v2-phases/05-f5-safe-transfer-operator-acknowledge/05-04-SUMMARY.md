---
phase: 05-f5-safe-transfer-operator-acknowledge
plan: 04
subsystem: stack-operator-latch
tags: [failure-latch, acknowledge, yes-gate, latch-guid, ast-invariant, stack-core-934a621, safety]

requires:
  - phase: 05-f5-safe-transfer-operator-acknowledge
    provides: "05-02 fresh-path Transfer, _run_fresh/_finish, _FakeCore and AST call-site rules; 05-SPIKE.md amendment A-2 and the 6f latch-clause templates"
provides:
  - "GetFailureLatch bound 1:1 to StackService.latch_status(); 'latchStatus' joins the SUCCESS allowlist; it answers while a Transfer holds the tool BUSY"
  - "AcknowledgeFailure: reaches acknowledge_failure(guid.strip(), confirm=True) exactly once, only for arm_inspected exactly 'yes' (checked in _dispatchCommand before admission and again in the handler); never touches the ledger"
  - "_latch_clause(service) and _transfer_error_reply(service, result): every latching Transfer error names latch_status().guid first, labels the result's own guid 'task guid', and keeps the latched guid inside the 300-character cap"
  - "Phase 4's not-yet-available command set and its reply helper removed; COMMAND_TO_SERVICE_METHOD has nine entries and Transfer is the only unmapped oneof message"
  - "Acknowledge AST rule: exactly one acknowledge_failure call site, inside AcknowledgeFailure, after a comparison against the constant 'yes' (planted violations for missing call, stray call and removed check)"
affects: [05-05, 05-06, 05-07, phase-07-runbook]

actuals:
  tokens: 9200
  tasks: 3
  commits: 6
plan_head_before: 5b1eee84f9be703ebbba42994ad4d61c845f91fd
plan_head_after: 67a670dec4e19dd8fa8b8a798aea182a926eead3

tech-stack:
  added: []
  patterns:
    - "Defence in depth on the operator gate: the exact 'yes' is checked in _dispatchCommand (before _admit, so it beats not-configured and reaches no core) and again as the first statement of the handler (a direct call is gated too)"
    - "Latch guid always read from latch_status() (one zero-I/O call), never parsed from the core's explanation; the result's own guid is labelled 'task guid' after it"
    - "_latch_clause never raises: an exception or a non-LatchStatus answer reads 'latch status unavailable; read GetFailureLatch'"

key-files:
  created: []
  modified:
    - tools/stack/server.py
    - tools/tests/stack_test.py

key-decisions:
  - "The yes gate lives in _dispatchCommand next to (not inside) _check_args, so simulated mode keeps accepting arm_inspected 'no' and sleeping EST_ACK_S"
  - "The later-ledger-write-failure message now carries the latch clause (spike 6f template) for latching results only; a ran result with a write failure makes no latch_status call (A-4). This closes the clause 05-02 deferred"
  - "_finish takes the service so every wait result goes through _transfer_error_reply; ran stays SUCCESS because _transfer_error_reply only rewrites latching kinds"
  - "A refused(failureLatched) reply repeats the latched guid as 'task guid' because the core puts it in detail.guid; it is labelled, never presented as the guid to acknowledge"

patterns-established:
  - "AST rule helpers stay pure and assertion-free; new rule appends strings and tests plant violations with _plant, a deep-copy rename, or ast.increment_lineno to reorder"

requirements-completed: [ACK-01, ACK-02, XFR-05]

coverage:
  - id: D1
    description: "GetFailureLatch returns SUCCESS with empty message and meta equal to latch_status().to_dict() for a task-guid, submit-<hex>, state-<hex> and unlatched status; latch_status is the only core call; idempotent; answers while BUSY; NOT_READY when unconfigured"
    requirement: "ACK-02"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestFailureLatch"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestBusyReads.test_reads_answer_while_busy_and_a_second_transfer_is_refused"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestResultMapping"
        status: pass
    human_judgment: false
  - id: D2
    description: "AcknowledgeFailure sends acknowledge_failure(guid.strip(), confirm=True) once only for arm_inspected exactly 'yes'; 'no', 'Yes', 'YES', ' yes', 'yes ', 'yes\\n', 'y', 'true', full-width 'yes', '' and unset are INVALID_ARGUMENTS with zero core calls, also unconfigured and also when the handler is called directly; core refusals are ERROR_FROM_TOOL; simulated mode still accepts 'no'"
    requirement: "ACK-01"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestAcknowledge"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestSimulatedCommands.test_acknowledge_with_no_is_also_success"
        status: pass
    human_judgment: false
  - id: D3
    description: "Acknowledging never reads, writes or deletes a ledger record (bytes and mtime identical; no ledger directory created)"
    requirement: "ACK-01"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestAcknowledgeLeavesTheLedgerAlone"
        status: pass
    human_judgment: false
  - id: D4
    description: "acknowledge_failure has exactly one call site across tools/stack, inside AcknowledgeFailure, after a comparison against 'yes'; planted violations for a missing call, a stray call (in GetManagerState and Transfer), a second call, a removed check, a check after the call and a check elsewhere"
    requirement: "XFR-05"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestAdapterInvariant"
        status: pass
    human_judgment: false
  - id: D5
    description: "Every real-mode command with no service is NOT_READY 'stack: not configured'; the refusal machinery is gone; the map has nine entries and Transfer is the only unmapped oneof message"
    requirement: "ACK-01"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestUnconfiguredOrdering"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestOneToOneSurface"
        status: pass
    human_judgment: false
  - id: D6
    description: "Every latching Transfer error (failed, aborted, lost, refused failureLatched) names latch_status().guid first and labels the result's guid 'task guid'; first-failure-wins case; unlatched core says 'did not latch'; 300-character cap keeps the latched guid even with a 400-character reason; non-latching errors and ran make no latch_status call; a raising latch_status degrades to 'read GetFailureLatch'; explanation never read"
    requirement: "ACK-02"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestLatchGuidInMessage"
        status: pass
    human_judgment: false
  - id: D7
    description: "The prohibition 'MUST NOT acknowledge a failure from any path other than an operator AcknowledgeFailure with arm_inspected exactly yes' (descriptor-less, flagged unverified in the plan)"
    requirement: "ACK-01"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestAcknowledge"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestAdapterInvariant.test_acknowledge_failure_planted_in_transfer_is_reported"
        status: pass
    human_judgment: false
  - id: D8
    description: "The prohibition 'MUST NOT name the result's own task guid as the guid to acknowledge, and MUST NOT parse the core's explanation text' (descriptor-less, flagged unverified in the plan)"
    requirement: "ACK-02"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestLatchGuidInMessage.test_the_first_failure_wins_and_the_task_guid_is_never_the_one_to_acknowledge"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestLatchGuidInMessage.test_the_explanation_text_is_never_read"
        status: pass
    human_judgment: false

duration: 14min
completed: 2026-10-29
status: complete
---

# Phase 5 Plan 04: Failure Latch Read, Operator Acknowledge, Latch Guid in Errors Summary

**`GetFailureLatch` now reads `latch_status()` 1:1 (including `submit-<hex>` and `state-<hex>` ids, mid-transfer), `AcknowledgeFailure` reaches the core only for an exact `"yes"` through a single AST-pinned call site, and every latching Transfer error names the guid to acknowledge from `latch_status()` first, with the result's own guid labelled "task guid" and the latched guid kept inside the 300-character cap.**

## Performance

- **Duration:** about 14 min (session start was not captured; estimated from commit times)
- **Completed:** 2026-10-29T09:02Z
- **Tasks:** 3 (latch read, acknowledge, latch guid in messages), each RED then GREEN
- **Files:** 2 modified (`tools/stack/server.py`, `tools/tests/stack_test.py`), none created
- **Gate:** `bin/make proto test` exits 0: ruff clean, mypy clean, 413 tests passed; `tools/tests/stack_test.py` is now 176 tests (was 152 after Task 1 RED/GREEN, 146 before the plan)

## Accomplishments

- **Task 1: `GetFailureLatch`.** `"latchStatus"` joined `_SUCCESS_KINDS`, the map gained `"GetFailureLatch": "latch_status"`, the handler is `_result_reply(service.latch_status())`. `READ_COMMANDS` already held it, so it answers while Transfer holds the tool BUSY and does not flip status. Unconfigured it is `NOT_READY "stack: not configured"`.
- **Task 2: `AcknowledgeFailure`.** The exact `"yes"` is checked in `_dispatchCommand` right after the simulated branch and before `_admit`, so it beats not-configured and reaches no core; the handler repeats `if params.arm_inspected != "yes"` as its first statement and then makes the single `service.acknowledge_failure(params.guid.strip(), confirm=True)` call. `_check_args` is unchanged, so simulated mode still accepts `"no"`. The not-yet-available set, `_unavailable_reply` and the conditional in `_dispatchCommand` are deleted. The AST helper now requires exactly one call site and a `Compare` containing `Constant("yes")` at a lower line number inside `AcknowledgeFailure`; `AcknowledgeFailure` and `GetFailureLatch` are required functions.
- **Task 3: latch guid in errors.** `_latch_clause` calls `latch_status()` once and renders the three spike 6f clauses (latched, not latched, unavailable); it never raises and never reads `explanation`. `_transfer_error_reply` handles failed, aborted, lost and refused(failureLatched): `stack: <kind> (<reason capped at 60>); <latch clause>; task guid <g>`, whole line through `_one_line(…, 300)`, meta the result's `to_dict()` unchanged. It is used for a non-`TransferPlan` plan result and for every wait result in `_finish`.

## Task Commits

1. **Task 1 RED:** `766ec0f` `test(05-04): failing GetFailureLatch tests (ACK-02)`
2. **Task 1 GREEN:** `4e4be39` `feat(05-04): GetFailureLatch reads latch_status() 1:1 (ACK-02)`
3. **Task 2 RED:** `0f8a9a8` `test(05-04): failing AcknowledgeFailure tests (ACK-01)`
4. **Task 2 GREEN:** `cbe35fc` `feat(05-04): operator-only AcknowledgeFailure behind an exact "yes" (ACK-01)`
5. **Task 3 RED:** `9b0dc92` `test(05-04): failing latch-guid message tests (A-2)`
6. **Task 3 GREEN:** `67a670d` `feat(05-04): Transfer errors name the guid to acknowledge (ACK-02, A-2)`

Every `test(05-04)` commit precedes its `feat(05-04)` commit.

## RED Evidence

- Task 1 RED (`-k "TestFailureLatch or TestResultMapping or TestBusyReads or TestNotConfigured or TestOneToOneSurface or TestReadBypassEdges"`): `11 failed, 20 passed`, e.g. `AssertionError: 7 != 6` (ERROR_FROM_TOOL instead of NOT_READY for the unconfigured latch) and the `LatchStatus` rows missing from the allowlist. After GREEN: full `stack_test.py` 152 passed.
- Task 2 RED (full file): `22 failed, 141 passed`; the failures included `AssertionError: True is not false` on `hasattr(stack_server, "UNAVAILABLE_COMMANDS")`, every `TestAcknowledge` test, and the AST tests that need the real call and the `'yes'` check (`test_real_sources_are_clean` reported the missing acknowledge call). After GREEN: 163 passed.
- Task 3 RED (`-k TestLatchGuidInMessage`): `9 failed, 4 passed` (the 4 passing are the non-latching, ran-path and unconfigured-style controls that hold before the change). After GREEN: 176 passed.

## Decisions Made

See `key-decisions` in the frontmatter. The one beyond the plan text: the later-write-failure message carries the latch clause (06f template that 05-02 deferred), for latching kinds only.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Later-ledger-write-failure message lacked the latch clause**
- **Found during:** Task 3 (`_finish` now holds the service and `_latch_clause` exists; 05-02 deferred this explicitly to 05-04/05-05)
- **Issue:** After a failed/aborted/lost result whose ledger write failed, the operator got `stack: transfer <kind>, but the ledger could not record it; re-running ...` with no guid to acknowledge, contradicting spike 6f and A-2.
- **Fix:** `_LATER_WRITE_FAILED` gained a `{latch}` slot filled with `"<latch clause>; "` for latching (or unknown) results; a `ran` result with a write failure makes no `latch_status` call (A-4). Two tests cover both.
- **Files modified:** `tools/stack/server.py`, `tools/tests/stack_test.py`
- **Commit:** `67a670d` (tests in `9b0dc92`)

### Plan-scope notes (not defects)

- `test_a_second_acknowledge_failure_call_is_reported` and `test_one_acknowledge_failure_call_inside_its_handler_is_allowed` from 05-02 assumed zero real calls. The first now plants one call (making two); the second is replaced by `test_the_real_handler_has_exactly_one_call_after_a_yes_check`.
- The Phase 4 comment above `_RECONFIGURING_MESSAGE` referenced the removed `_unavailable_reply`; reworded.
- `refused(failureLatched)` replies repeat the latched guid as "task guid" because the core places it in `detail.guid` (`_find_guid`); the plan specifies this wording. It is labelled, never the guid to acknowledge.

## Issues Encountered

None. `~/.local/state/galago-tools` does not exist after the full gate (no test wrote the real ledger).

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or schema: `AcknowledgeFailure` and `GetFailureLatch` already existed in the frozen `stack.proto`; `tools/base_server.py`, `interfaces/` and `tools/grpc_interfaces/` are unchanged since `5b1eee8`. T-05-13 through T-05-16 are each covered by tests (11 negative yes variants plus the direct handler call; first-failure-wins; 400-character reason; raising `latch_status`).

## Next Phase Readiness

Ready for 05-05 (release whitelist, `outcomeUnknown`, in-flight owner clause) and 05-06 (`decide()` wiring, re-attach). Both can call `_transfer_error_reply(service, result)` and `_latch_clause(service)`; `_finish` now takes `(service, ledger, key, result, write_failed)`.

## Self-Check: PASSED

- `.planning/phases/05-f5-safe-transfer-operator-acknowledge/05-04-SUMMARY.md`, `tools/stack/server.py`, `tools/tests/stack_test.py`: present.
- Commits `766ec0f`, `4e4be39`, `0f8a9a8`, `cbe35fc`, `9b0dc92`, `67a670d` are ancestors of HEAD; `git rev-list --count 5b1eee8..HEAD` = 6 (matches `commits: 6`).
- Acceptance: `"latchStatus"`, `"GetFailureLatch": "latch_status"`, `confirm=True`, `def _transfer_error_reply`, `def _latch_clause`, `class TestFailureLatch`, `class TestAcknowledge`, `class TestLatchGuidInMessage` all present; surface check prints `surface ok` (no `UNAVAILABLE_COMMANDS`, no `_unavailable_reply`, 9 map entries).
- Verification: `bin/make proto test` exit 0 (413 passed); `git diff 5b1eee8 -- tools/base_server.py interfaces tools/grpc_interfaces` is empty.
