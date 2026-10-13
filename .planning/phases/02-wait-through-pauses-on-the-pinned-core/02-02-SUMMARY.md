---
phase: 02-wait-through-pauses-on-the-pinned-core
plan: 02
subsystem: adapter
tags: [fast-mcp, unittest, pause-resume, state-gates, gate-test]

# Dependency graph
requires:
  - phase: 02-wait-through-pauses-on-the-pinned-core
    plan: 01
    provides: "fast-mcp re-pinned to b30b38d; Transfer/RunProtocol wired with
      on_pause=self._record_pause, through_pauses=True; real-core gRPC test
      fixture (_real_core, _stub_transport)"
provides:
  - "TestRequirementsPin gate tests proving the installed core has
     RunOptions.through_pauses/on_pause, PauseInfo from fast_mcp.orchestration
     with the expected to_dict shape, a bool-only wait() guard, and idle
     state gates on pause/resume/abort called directly on the core"
  - "TestRunState.test_real_pause_info_records_like_the_stub pinning that the
     real PauseInfo satisfies the duck-typed _PauseInfoLike recorder exactly
     like the stub"
  - "_PauseInfoLike/_DictPauseInfo/_record_pause/simulate_pause docstrings
     describe the wiring as done; no stale pin or future-tense wording
     remains in server.py"
affects: ["02-03 (operator-abort wording)",
  "02-04 (paused-time-excluded-from-timeout tests)",
  "Phase 3 (deploy — this is the gate that must stay green before install)"]

# Actuals (#2632)
actuals:
  tokens: 2371
  tasks: 2
  commits: 2
  plan_head_before: 8dcc7f12a06a949a6120570522ba9f4c25bbdb3b
  plan_head_after: f7d62f8ce9c901cdedf9b82db786f273e44f3fe0

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Gate tests call the real FastService core directly (pause/resume/abort,
       wait) over a fresh MagicMock transport, rather than only exercising
       the FastServer layer, so the core's own state gates and capability
       surface are what the gate actually proves (D-03)"

key-files:
  created: []
  modified:
    - tools/tests/fast_test.py
    - tools/fast/server.py

key-decisions:
  - "D-03: the LIVE-01 gate tests join TestRequirementsPin (keeps
     02-VALIDATION.md's documented -k command accurate) and check the state
     gates by calling the real core directly, leaving the existing
     FastServer-level idle refusal tests in TestRecoveryCommands unchanged"
  - "D-05: test_real_pause_info_records_like_the_stub passes immediately —
     it pins compatibility (the duck-typed recorder already accepts the
     real PauseInfo) rather than driving a behavior change, so there is no
     natural RED for this test; this was expected per the plan"
  - "Guarded orchestration import in fast_test.py now pulls PauseInfo
     alongside RunOutcome; because the guard only catches ModuleNotFoundError,
     a core missing PauseInfo fails the whole test file loudly (ImportError),
     which is the intended gate outcome for a wrong install"

requirements-completed: [LIVE-01]

coverage:
  - id: D1
    description: "The gate fails on a core without wait-through-pauses or
      the state gates: RunOptions.through_pauses/on_pause, PauseInfo shape,
      the bool-only wait() guard, and idle refusals on pause/resume/abort
      are all asserted directly against the real core"
    requirement: "LIVE-01"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestRequirementsPin.test_installed_core_has_wait_through_pauses_and_pause_info"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestRequirementsPin.test_installed_core_refuses_pause_resume_abort_while_idle"
        status: pass
    human_judgment: false
  - id: D2
    description: "The real PauseInfo records exactly like the stub recorder
      test, and the PauseInfo/recorder docstrings in server.py describe the
      02-01 wiring as done instead of a future plan"
    requirement: "LIVE-01"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestRunState.test_real_pause_info_records_like_the_stub"
        status: pass
      - kind: other
        ref: "docstring-only AST diff of tools/fast/server.py against d60c829 (acceptance criterion)"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-10-13
status: complete
---

# Phase 2 Plan 2: Gate the installed core's wait-through-pauses capability Summary

**TestRequirementsPin now fails on any core lacking `RunOptions.through_pauses`/`on_pause`, `fast_mcp.orchestration.PauseInfo`'s shape, the bool-only `wait()` guard, or idle-state refusals on `pause`/`resume`/`abort` called directly on the core; PauseInfo/recorder docstrings in `server.py` now describe the 02-01 wiring as done.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-10-13T14:52:00Z
- **Completed:** 2026-10-13T14:57:00Z
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments
- `tools/tests/fast_test.py`'s guarded core-import block now pulls `PauseInfo`
  (alongside `RunOutcome`) from `fast_mcp.orchestration` and `RunOptions`
  (alongside `RunHandle`) from `fast_mcp.run_control`; since the guard only
  catches `ModuleNotFoundError`, a core without `PauseInfo` now fails the
  whole test file loudly with `ImportError` — the intended outcome for a
  wrong install (D-03).
- `TestRequirementsPin.test_installed_core_has_wait_through_pauses_and_pause_info`:
  asserts `RunOptions` has `through_pauses` (default `False`) and `on_pause`
  (default `None`); asserts `PauseInfo.__module__ == "fast_mcp.orchestration"`
  and its `to_dict()` keys are exactly `{errorCode, errorName, percent,
  eventPayload}`; builds a real core over a fresh `MagicMock()` transport and
  asserts `core.wait(RunHandle(), through_pauses="yes")` raises `TypeError`
  with `transport.get_status`/`get_plate_definitions` never called.
- `TestRequirementsPin.test_installed_core_refuses_pause_resume_abort_while_idle`:
  a real core over a fresh `MagicMock()` transport reporting `idle` state;
  `core.pause(hard=False)`, `core.resume(is_tip_broken=False)`, and
  `core.abort(return_liquid=False)` each return `Refused` with `state="idle"`
  and the three exact reasons ("no running protocol to pause", "no paused
  protocol to resume", "no running or paused protocol to abort"); the
  transport's `pause`/`resume`/`abort` are never called.
- `TestRunState.test_real_pause_info_records_like_the_stub`: feeds a real
  `PauseInfo` through `self.server._record_pause` inside `_run_in_flight`
  and asserts `run_state` matches the existing stub-fed test byte-for-byte
  (state `paused`, percent `0`, the five pause keys, `errorCode`/`errorName`/
  `eventPayload`, a UTC `since`), with `self.service.method_calls == []`.
  This test passes immediately — it pins the already-correct duck-typed
  compatibility rather than driving a change (D-05).
- `server.py` docstrings for `_PauseInfoLike`, `_DictPauseInfo`,
  `_record_pause`, and `simulate_pause` now describe the recorder wiring as
  done (Transfer/RunProtocol pass `RunOptions(on_pause=self._record_pause)`)
  instead of naming the old pin (`76f8c3f`) or a future "Phase 2 wires..."
  sentence. `fast_test.py`'s `_StubPauseInfo` docstring now explains it stays
  for payloads the real `PauseInfo` would sanitise away (the unencodable
  object in `test_unencodable_run_state_falls_back_to_unknown`).
- No logic change in `server.py`: a docstring-only AST diff against `d60c829`
  (the last 02-01 commit touching the file) confirms equivalence.

## Task Commits

Each task was committed atomically:

1. **Task 1: The gate rejects a core without wait-through-pauses or the state gates** - `f9fc8bd` (test)
2. **Task 2: The real PauseInfo records like the stub; PauseInfo and recorder docstrings describe the wiring as done** - `f7d62f8` (docs)

**Plan metadata:** pending (this SUMMARY's own commit)

## Files Created/Modified
- `tools/tests/fast_test.py` - guarded imports gain `PauseInfo`/`RunOptions`;
  two new `TestRequirementsPin` gate tests; `TestRunState.test_real_pause_info_records_like_the_stub`;
  `_StubPauseInfo` docstring updated
- `tools/fast/server.py` - `_PauseInfoLike`/`_DictPauseInfo`/`_record_pause`/
  `simulate_pause` docstrings rewritten to present tense (no logic change)

## Decisions Made
See `key-decisions` in frontmatter (D-03 class placement and state-gate
checking strategy; D-05 pinning-not-driving test; guarded-import ImportError
behavior).

## Observed Pre-Commit Failure Proofs (Task 1)

Per the plan's step 3, each new test was temporarily broken (never committed)
to prove it can fail, then reverted and re-verified green before committing.

**`test_installed_core_has_wait_through_pauses_and_pause_info`** — field name
changed to a nonexistent `"through_pauses_typo"`:
```
AssertionError: 'through_pauses_typo' not found in {'timeout_s': ..., 'on_progress': ...,
'cancel': ..., 'on_pause': ..., 'through_pauses': Field(name='through_pauses', ...)}
```

**`test_installed_core_refuses_pause_resume_abort_while_idle`** — expected
state changed from `"idle"` to `"running"`:
```
AssertionError: 'idle' != 'running'
- idle
+ running
```

Both temporary edits were reverted (`diff` against a pre-edit backup of the
file showed zero difference after revert) and the clean tests re-run green
before committing.

## Docstrings-Only Check Baseline (Task 2)

The last 02-01 commit touching `tools/fast/server.py` before Task 2's edits:
`d60c829d3df9e70a4291aa2992ee36e29a8aabd2` (`git log -1 --format=%H --
tools/fast/server.py`, run before any Task 2 edit). The AST-diff acceptance
criterion compared this SHA's `tools/fast/server.py` against the working
tree with every module/class/function docstring stripped, and confirmed
`ast.dump()` equality (logic unchanged, docstrings only).

## Deviations from Plan

None - plan executed exactly as written. Both tasks' acceptance criteria
and the plan-level verification passed on the first attempt after writing
the specified tests and docstring edits.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make proto
  test` exits 0 with 126 unittest tests (up from 123 after 02-01).
- `git diff --exit-code c9a89cf -- tools/base_server.py` exits 0 (unchanged).
- `git log --oneline -2` shows `f9fc8bd` (gate-test commit) then `f7d62f8`
  (docstring commit) at HEAD, in that order.
- No blockers for 02-03 (operator-abort wording).

---
*Phase: 02-wait-through-pauses-on-the-pinned-core*
*Completed: 2026-10-13*

## Self-Check: PASSED

- FOUND: tools/tests/fast_test.py
- FOUND: tools/fast/server.py
- FOUND: f9fc8bd1873d418ab1870e31a594be6519b8f5dc (Task 1)
- FOUND: f7d62f8ce9c901cdedf9b82db786f273e44f3fe0 (Task 2)
- `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make proto test` re-run: exit 0,
  126 unittest tests passed
- `git diff --exit-code c9a89cf -- tools/base_server.py` exits 0
- Every acceptance criterion from both tasks verified to pass (see commit history and the
  acceptance-criteria commands run before each commit)
