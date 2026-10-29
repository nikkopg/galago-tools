---
phase: 05-f5-safe-transfer-operator-acknowledge
plan: 03
subsystem: stack-step-ledger
tags: [step-key-ledger, decide, state-machine, retention, flock, fail-closed, core-free-tests, tdd]

requires:
  - phase: 05-f5-safe-transfer-operator-acknowledge
    provides: "05-02 tools/stack/ledger.py (strict load, claim, mark_started, mark_done, flock + atomic save) and the 05-SPIKE.md section 6 binding contract"
provides:
  - "tools/tests/stack_ledger_test.py: 90 core-free tests (stdlib + tools.stack.ledger only) that run, never skip, without the private core"
  - "ledger.decide(record, *, fingerprint, instance, now) -> Decision(action, restarted, record): the pure D-07 repeat-key table as amended by 05-SPIKE.md 6b, with eight action constants and REPLAY_WINDOW_S = 600.0"
  - "Ledger.release, Ledger.mark_outcome_unknown (latchGuid, A-5), Ledger.find_by_guid, RETENTION_DONE_S = 604800.0 prune on write"
  - "Stricter load: fingerprint must be 64 lowercase hex, createdAt/updatedAt must be aware ISO-8601; mark_done raises ValueError for a non-terminal result (A-1 at the storage layer)"
affects: [05-04, 05-05, 05-06, 05-07, phase-07-runbook]

actuals:
  tokens: 14400
  tasks: 3
  commits: 6
plan_head_before: 770588a677da00810f8b87c1286f0dfcde75e7e8
plan_head_after: 78482353d619cb74ac7554ee2f8dd46a8aaa34f9

tech-stack:
  added: []
  patterns:
    - "decide() is pure: fingerprint check first for every state, then state dispatch; replay only for done+ran with 0 <= age < REPLAY_WINDOW_S, so exactly 600 s, a negative age and an unparseable updatedAt all refuse (fail closed)"
    - "Retention prune runs inside _mutate only when the change wrote something, so load() and no-op mutations never rewrite the file"
    - "Test-first per TDD gate: test commit (RED, ImportError) then feat commit (GREEN) for decide and for the transitions"

key-files:
  created:
    - tools/tests/stack_ledger_test.py
  modified:
    - tools/stack/ledger.py

key-decisions:
  - "decide() treats any state it does not know (unreachable after the strict load) as REFUSE_OUTCOME_UNKNOWN, so an unexpected record can never lead to a fresh send"
  - "_mutate gained a required now parameter so the retention prune has a clock; it is private (server.py never calls it) and no public Ledger signature changed"
  - "A prune only happens on a mutation that actually changed the file (a failed claim or a release of an absent key writes nothing and prunes nothing)"
  - "Spike 6d says a done record with an unparseable updatedAt is kept by retention; the strict load already rejects such a file, so _prune keeps it defensively (age None -> kept) without a reachable test"

patterns-established:
  - "Core-free test file: local frozen dataclasses mirror core TransferRequest/Location so dataclasses.asdict works without the core"

requirements-completed: [XFR-02, XFR-03, XFR-04]

coverage:
  - id: D1
    description: "The persisted ledger fails closed for every malformed shape (non-UTF-8, invalid JSON, non-object, bad version, bad records, unknown state, bad fingerprint, missing instance, bad or naive timestamps, started without guid, done without kind, directory at the path), never changes the file bytes, and a missing file loads as {} creating nothing; saves are atomic with 0700/0600 modes and flock serialisation"
    requirement: "XFR-02"
    verification:
      - kind: unit
        ref: "tools/tests/stack_ledger_test.py#TestLedgerStorage"
        status: pass
    human_judgment: false
  - id: D2
    description: "resolve_ledger_dir order (absolute configured wins, absolute XDG_STATE_HOME, else ~/.local/state, relative raises ValueError, default never under /tmp) and fingerprint determinism and sensitivity to endpoint and every request field"
    requirement: "XFR-02"
    verification:
      - kind: unit
        ref: "tools/tests/stack_ledger_test.py#TestResolveLedgerDir"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_ledger_test.py#TestFingerprint"
        status: pass
    human_judgment: false
  - id: D3
    description: "decide() returns exactly one action per D-07 row (fresh, mismatch, refuseSubmitting, refuseOutcomeUnknown, reattach, replay, refuseCompleted, refuseFailed), with replay only for done+ran with 0 <= age < 600 s, restarted reported for every state, and no I/O or mutation"
    requirement: "XFR-03"
    verification:
      - kind: unit
        ref: "tools/tests/stack_ledger_test.py#TestDecide"
        status: pass
    human_judgment: false
  - id: D4
    description: "Release deletes only its key, mark_outcome_unknown records latchGuid, find_by_guid finds the owning step key, is_terminal matches the A-1 set, mark_done refuses a non-terminal result, and retention prunes only done records older than 7 days on a write"
    requirement: "XFR-04"
    verification:
      - kind: unit
        ref: "tools/tests/stack_ledger_test.py#TestTransitions"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_ledger_test.py#TestIsTerminal"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_ledger_test.py#TestRetention"
        status: pass
    human_judgment: false
  - id: D5
    description: "The prohibition 'MUST NOT prune or delete a submitting, started or outcomeUnknown record, and MUST NOT treat a corrupt ledger as empty' (descriptor-less, flagged unverified in the plan)"
    requirement: "XFR-03"
    verification:
      - kind: unit
        ref: "tools/tests/stack_ledger_test.py#TestRetention.test_unfinished_records_of_any_age_are_kept"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_ledger_test.py#TestRetention.test_a_corrupt_ledger_is_never_pruned_or_treated_as_empty"
        status: pass
    human_judgment: false

duration: 3min
completed: 2026-10-29
status: complete
---

# Phase 5 Plan 03: Ledger Contract, decide() and Transitions Summary

**The core-free step ledger now has a 90-test contract (fail closed, atomic, flock, 0700/0600, path resolution, fingerprint), the pure `decide()` repeat-key state machine from 05-SPIKE.md 6b, and the release / outcomeUnknown / find-by-guid / 7-day-retention transitions, all written test first.**

## Performance

- **Duration:** about 3 min of wall clock for the execution session (start captured 2026-10-29T08:51:15Z)
- **Tasks:** 3 (storage contract, decide, transitions)
- **Files:** 1 created (`tools/tests/stack_ledger_test.py`), 1 modified (`tools/stack/ledger.py`)
- **Gate:** `pytest tools/tests/stack_ledger_test.py` 90 passed, 0 skipped; `pytest tools/tests/stack_test.py` 146 passed (unchanged); `ruff check tools/stack tools/tests` clean; `mypy` clean on both files

## Accomplishments

- **Task 1: storage contract proven, two real gaps fixed.** `TestLedgerStorage`, `TestResolveLedgerDir` and `TestFingerprint` run against the 05-02 implementation. Seven malformed shapes loaded when they should not have (fingerprint format and timestamps); fixed in `fix(05-03)`.
- **Task 2: `decide()`.** Fingerprint check first for every state; then `submitting` -> refuseSubmitting, `started` -> reattach, `outcomeUnknown` (and any unknown state) -> refuseOutcomeUnknown, `done`+not-`ran` -> refuseFailed, `done`+`ran` with `0 <= age < 600` -> replay, otherwise refuseCompleted. `restarted = record["instance"] != instance`. Pure and frozen `Decision`. A test pins REFUSE_COMPLETED at exactly 600 s.
- **Task 3: transitions.** `release`, `mark_outcome_unknown` (A-5 `latchGuid`, string or None), `find_by_guid` (read-only strict load, deterministic by sorted key), `RETENTION_DONE_S` prune inside `_mutate`, `mark_done` ValueError for non-terminal results, and `is_terminal` hardened for non-dict input and non-string kinds (a list `kind` previously raised TypeError on the frozenset lookup).

## Malformed shapes covered (Task 1, 30 subTests in one test, plus 4 unknownVersion subTests)

Raw bytes: non-UTF-8 bytes, invalid JSON, empty file, top-level list, top-level string.
Documents: version missing, version 2, version `true`, version `"1"`, version `1.0`, records missing, records a list, a record that is a list, a record that is null, unknown state, state missing, fingerprint short, fingerprint not hex, fingerprint upper case, fingerprint not a string, instance missing, createdAt unparseable, updatedAt unparseable, updatedAt naive, createdAt naive, updatedAt missing, started without handle, started handle without guid, started handle with empty guid, done without result, done result without kind, done result kind not a string, handle not an object, latchGuid not a string, a good record next to a bad one.
Separately: a directory at the ledger path (unreadable) and a missing file (loads `{}`, creates nothing). Each malformed shape also checks that `claim` refuses, the bytes are unchanged and no `*.tmp` is left.

## Task Commits

1. **Task 1 test:** `e2dd0e6` `test(05-03): ledger storage contract (XFR-02)`
2. **Task 1 fix:** `9204c70` `fix(05-03): ledger load rejects a bad fingerprint or timestamp (XFR-02)`
3. **Task 2 RED:** `326e6d8` `test(05-03): failing decide() state-machine tests (D-07, D-17)`
4. **Task 2 GREEN:** `682bb08` `feat(05-03): pure decide() for the repeat-key ledger (XFR-03)`
5. **Task 3 RED:** `645d76c` `test(05-03): failing transition and retention tests (D-08, A-1)`
6. **Task 3 GREEN:** `7848235` `feat(05-03): ledger release, outcomeUnknown, lookup and retention (XFR-04)`

`git log --reverse --grep='decide'` starts with the `test(05-03)` commit, so the ordering check passes. No 05-03 commit touches `tools/stack/server.py` or `tools/tests/stack_test.py`.

## RED Evidence

- Task 1: before the fix commit, `python -m unittest tools.tests.stack_ledger_test` reported `FAILED (failures=7)`, all in `test_every_malformed_ledger_fails_closed_and_is_never_modified` for shapes `fingerprint not 64 hex (short)`, `fingerprint not hex`, `fingerprint upper case`, `createdAt unparseable`, `updatedAt unparseable`, `updatedAt naive`, `createdAt naive` (`AssertionError: LedgerError not raised`). After the fix: 38 passed.
- Task 2 RED: `ImportError: cannot import name 'FRESH' from 'tools.stack.ledger'` (the whole file fails collection, by the direct-import form chosen). GREEN: 61 passed.
- Task 3 RED: `ImportError` for `RETENTION_DONE_S`. GREEN: 90 passed.

## Decisions Made

See `key-decisions` in the frontmatter. In short: unknown state in `decide()` refuses (never fresh); `_mutate` takes the clock for retention; prune only on a mutation that wrote.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Ledger load accepted a malformed fingerprint and malformed timestamps**
- **Found during:** Task 1 (the storage tests the plan asked for exposed it)
- **Issue:** `_validate_record` only checked that `fingerprint`, `createdAt` and `updatedAt` were strings, so a short or non-hex fingerprint and an unparseable or naive timestamp loaded cleanly. A bad `updatedAt` would later make `decide()` and retention misjudge a record.
- **Fix:** fingerprint must fullmatch `[0-9a-f]{64}`; both timestamps must parse with `datetime.fromisoformat` and carry a UTC offset.
- **Files modified:** `tools/stack/ledger.py`
- **Commit:** `9204c70`

**2. [Rule 1 - Bug] `is_terminal` raised on non-dict input and on an unhashable `kind`**
- **Found during:** Task 3 (the plan's must_haves require False for a list input)
- **Issue:** `result.get` on a list raised AttributeError, and `{"kind": ["ran"]}` raised TypeError at the frozenset membership test.
- **Fix:** return False unless the input is a Mapping and `kind` is a string.
- **Files modified:** `tools/stack/ledger.py`
- **Commit:** `7848235`

**Total deviations:** 2 auto-fixed (2 Rule 1). **Impact:** both tighten the fail-closed behaviour the plan required, no public signature changed, `stack_test.py` still 146 passed.

### Plan-scope notes (not defects)

- The retention truth "a `done` record with an unparseable `updatedAt` is kept" (spike 6d) is implemented in `_prune` but is unreachable through the public API, since the strict load rejects such a file first. It has no test for that reason.
- `_mutate` is private and gained a required `now` argument; the only callers are in `ledger.py`.
- The RED commits break collection of the whole test file (direct imports of the new names) rather than only the new class. The plan allows "ImportError or missing names".

## Issues Encountered

None.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None. No network endpoint, auth path or schema changed. The surface touched (ledger file, sibling lock file, temp file) is the one in the plan's threat model (T-05-08..T-05-12): T-05-08 (two-thread Barrier claim test, 5 rounds), T-05-09 (age 600 s, negative age, old record all refuse), T-05-10 (held lock gives `busy`), T-05-11 (symlinked lock path refused) are each covered by a test.

## Next Phase Readiness

Ready for 05-04 (server.py / stack_test.py, parallel) and 05-05/05-06, which wire `release`, `mark_outcome_unknown`, `find_by_guid` and `decide()` into `Transfer`. Plan 05-06 must call `decide()` with an aware `now` and the server's instance id; `mark_done` now raises ValueError on a non-terminal result, so callers must keep checking `is_terminal` first (05-02's `_finish` already does).

## Self-Check: PASSED

- `tools/stack/ledger.py`, `tools/tests/stack_ledger_test.py`, this SUMMARY: present.
- Commits `e2dd0e6`, `9204c70`, `326e6d8`, `682bb08`, `645d76c`, `7848235` are ancestors of HEAD; `git rev-list --count 770588a..HEAD` = 6 (matches `commits: 6`).
- Acceptance: AST import check exits 0; `def decide`, `class TestDecide`, `def release`, `def mark_outcome_unknown`, `def find_by_guid` all present; scope check on server.py / stack_test.py clean.
- Verification: `pytest tools/tests/stack_ledger_test.py` 90 passed; `ruff check tools/stack tools/tests` and `mypy` on both files clean.
