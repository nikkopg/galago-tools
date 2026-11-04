---
capability: secure-phase
phase: 07-deploy-supervised-live-stack-handoff
audited: 2026-11-03T07:31:34Z
threats_open: 0
verdict: SECURED
---

# Phase 07 Security Audit — supervised live stack handoff

**Sources verified against implemented artifacts (not plan claims):**
`docs/runbooks/gal-07-live-check.sh`, `tools/tests/gal07_live_runbook_test.py`,
`docs/runbooks/gal-07-live-handoff.md`, the ledger-replay refusal path
(`tools/stack/ledger.py`, `tools/stack/server.py`) and the service-venv core pinned at
`934a621` (`.venv/.../stack_automation_layer-0.1.0.dist-info/direct_url.json`
`vcs_info.commit_id == 934a621ece116a8b263897c1e9b62b57374f4ef3`; local clone HEAD
`/home/formulatrix/data/nikko/stack-automation-layer` confirmed byte-equal to the pin).

**Falsification matrix executed live during this audit:**
`python -m pytest tools/tests/gal07_live_runbook_test.py` — **15 passed, 0 skipped**
(22.69 s): 10 gate trials (12 one-piece-removed subTests + 8 fail-closed degenerate-input
subTests + both holder dispositions + both credential dispositions + the read-only proof)
and 5 runbook-content pins. The gate cannot pass falsely: every single removed piece and
every degenerate HTTP/goJSON input produced a distinct `missing:`/`forbidden:` refusal and
a `BLOCKED:` verdict.

**Threat Flags:** neither `07-03-SUMMARY.md` nor `07-04-SUMMARY.md` carries a
`## Threat Flags` section — no unregistered attack surface from the executor side.
The D-14 two-plate amendment (plan shape said 2 keys / 3 legs; live event ran 4 keys /
5 legs) is recorded in findings rows 3a-1..3a-3 with per-leg ledger+log accounting
(16 attempt lines explained line-by-line: 1 rehearsal + 5 `invalidSource` manager
refusals + 1 pre-split failed attempt + 2 `movementError` queue attempts + the 4 run
legs + 2 no-ledger SUCCESS exchanges = expected-behaviour class) — it is a recorded
deviation whose new surface (two extra per-run keys) it itself counts; **not** an
unregistered threat.

---

## T-07-10 — re-send / fresh-key re-run queuing a second transfer (07-03, Tampering-safety, critical, mitigate)

**MITIGATED_VERIFIED**

- One-Transfer-only rule + never re-send after an ambiguous outcome:
  `docs/runbooks/gal-07-live-handoff.md:303-305` (recovery drill step 1: "Stop the
  session. No new commands are sent; nothing is re-queued") and
  `docs/runbooks/gal-07-live-handoff.md:258-267` (Part 2 event step; a forced re-send
  copies the stored key byte-for-byte inside the window only).
- One-Transfer-per-key enforced by the ledger-replay state machine in the pinned path:
  `tools/stack/ledger.py:161-193` — `submitting` → REFUSE_SUBMITTING; unknown/mismatch →
  MISMATCH; `done` outside `0 <= age < REPLAY_WINDOW_S` → REFUSE_COMPLETED; unknown
  state → "outcomeUnknown … never re-send". The refusal wording the caller sees is
  `tools/stack/server.py:259-261` ("step key already completed at …; the protocol must
  mint a new step key per run; **nothing was sent**") wired at `server.py:1146-1147`.
- The verify counts exactly baseline+1: `07-03-PLAN.md:166` assert
  `n == base + 1` against STACK2-6.log.
- Live proof: findings row 2a-3 (`docs/runbooks/gal-07-live-handoff.md:344`) — ledger
  record `GAL07-LIVE9-20261103T035107Z` state done, "Transfer count … = baseline(0)+1 =
  exactly 1 … no second submission".
- Falsification: `tools/tests/gal07_live_runbook_test.py` gate matrix (cannot pass on a
  missing piece) and runbook pins REQUIRED_PHRASES `stack-ledger.json`, `PREFLIGHT OK`,
  `BLOCKED:` (lines 84-117).

## T-07-11 — tool-server restart mid-event losing core task ownership (07-03, Tampering, high, mitigate)

**MITIGATED_VERIFIED**

- Restart-warning clause with never-replay-as-SUCCESS:
  `docs/runbooks/gal-07-live-handoff.md:32-35` ("tool restarted mid-transfer; inspect the
  arm; the core may not have latched this failure" — "the outcome is never replayed as
  SUCCESS") and again in the drill (`:316-321`).
- Falsified by test pin: `tools/tests/gal07_live_runbook_test.py:108` pins the full
  restart-warning phrase into REQUIRED_PHRASES (verified present in the runbook text by
  `test_runbook_carries_the_required_phrases`).
- Listener-PID re-check: runbook records the `ss -ltnp` re-baseline at
  `docs/runbooks/gal-07-live-handoff.md:149,160` and findings rows 2a-3/3a-3 confirm
  "listener PIDs unchanged vs the 07-02 baseline … T-07-11 held" (2a-3) and "no restart
  in the whole LIVE-10 window, T-07-16 held" (3a-3).

## T-07-12 — unrecorded or auto-advanced go (07-03, Repudiation, medium, mitigate)

**MITIGATED_VERIFIED**

- One literal-go gate per part, UTC-timestamped, no auto-advance:
  `docs/runbooks/gal-07-live-handoff.md:88-93` (Part 1), `:244-250` (Part 2), `:276-282`
  (Part 3).
- Test-enforced: `tools/tests/gal07_live_runbook_test.py:541-554`
  (`test_runbook_carries_one_go_gate_per_part`) asserts exactly one "Reply: literal go"
  per part slice and a UTC marker in each, and exactly 3 in the whole text.
- Recorded evidence: findings row 2a-1 — typed go `2026-11-03T03:51:07Z`; row 3a-1 — typed
  go `2026-11-03T05:36:05Z`; row 1a-6 — typed go `01:31:09Z`.

## T-07-SC (07-03) — npm/pip/cargo installs (Tampering, high, mitigate)

**MITIGATED_VERIFIED**

- Plans 07-03/07-04 install nothing: their tasks are one operator checkpoint + one
  recording task; their verify commands run only `python3`, `curl`, `jq`, `pytest`.
  Confirmed in `07-03-PLAN.md<::tasks>` and `07-04-PLAN.md<::tasks>`, and in both
  SUMMARYs `tech-stack.added: []`.
- The only dependency action in the phase (plan 07-02's Step 1, outside these two
  registers) is the commit-pinned core install from
  `docs/runbooks/gal-07-live-handoff.md:105-116` — never pip/`bin/make deps`, a
  `uv` install from a git+ URL locked at `934a621e…`, with a dry-run preview showing
  exactly one package (findings 1a-2) and the direct_url commit assert +
  the pre-flight's check 3 (`gal-07-live-check.sh:187-201`) holding it to the pin.

## T-07-13 — fresh-key re-run after an ambiguous leg queuing a second transfer (07-04, Tampering-safety, critical, mitigate)

**MITIGATED_VERIFIED**

- `numberOfRuns` pinned at 1 and per-run key minting: `docs/runbooks/gal-07-live-handoff.md:284-293`
  ("`numberOfRuns` stays at 1", "Fresh step keys are minted per run; keys are read from the
  run's stored rows"); the repeated-key refusal wording again at
  `tools/stack/server.py:259-261`.
- The D-11 drill as the only recovery path (never delete state, never restart to reset,
  never re-send): `docs/runbooks/gal-07-live-handoff.md:299-325` and the safety-rules
  never-delete/never-restart clauses at `:26-35`; pinned by test REQUIRED_PHRASES
  "never delete" and "GetFailureLatch".
- The verify counts exactly baseline+the-legs: `07-04-PLAN.md:176` assert
  `n == base + 2` plus `len(done) >= 3` on the ledger. The live two-plate amendment
  superseded the two-key shape; the evidence stands on the per-leg accounting recorded in
  findings row 3a-3 (`:347`): 4 fresh per-run keys all state done/ran, each leg
  one ledger record + one attempt line, both `movementError` keys kept as never-deleted
  D-14 history.
- Live proof: rows 3a-2/3a-3 (`:346-347`) — "no re-send of any leg, no restart, no state
  deletion at any point".

## T-07-14 — tool store losing a tool (07-04, Tampering, medium, mitigate)

**MITIGATED_VERIFIED**

- D-12 pre-store check implemented in the gate (check 6), not merely documented:
  `docs/runbooks/gal-07-live-check.sh:223-244` — requires a type `stack` AND a type
  `fast` tool at `$GALAGO_WEB_URL/api/tools`, and the stored stack host byte-equal to
  `$STACK_HOST` (refusal line names "byte-exactly … a different string is a different
  lock/state key"), failing closed on empty/non-JSON bodies (`:226-229`).
- Falsified by tests: `tools/tests/gal07_live_runbook_test.py` cases `store_no_fast`,
  `stored_host` (needles "type fast" / "byte-exactly"), `empty_tools`, `non_json_tools`.
- Runbook Part 3 wires it at the entry gate: `docs/runbooks/gal-07-live-handoff.md:271-274`;
  live PASS recorded at findings row 3a-1 (`:345`, "pre-store check holds both STORE2-6
  types").

## T-07-15 — replay-window refusal misread as a defect (07-04, Repudiation, low, mitigate)

**MITIGATED_VERIFIED**

- The 600 s rule pinned in the runbook text:
  `docs/runbooks/gal-07-live-handoff.md:39-41` ("a later refusal is expected behaviour,
  never a defect") and drill step 7 (`:322-325`); test-pinned by REQUIRED_PHRASES
  `REPLAY_WINDOW_S` and `600 s`.
- The refusal path exists in the implemented code, not just docs:
  `tools/stack/ledger.py:55` (`REPLAY_WINDOW_S = 600.0`) and
  `tools/stack/ledger.py:183-191` — a done/ran record only replays strictly inside the
  window; window-edge age, negative age (clock skew) and unparseable `updatedAt` all
  REFUSE (fail closed, `_age_s` at `:146-158`); `server.py:1146-1147` emits the
  refusal. In-window re-dispatch reuses the stored key byte-for-byte (`server.py:1107-1112`).
- Lived correctly during the event: row 3a-3 records the operator's own late-window
  "already completed, nothing was sent" probes as expected behaviour, "recorded as
  expected behavior, not motion".

## T-07-16 — mid-run tool-server restart truncating Stack.log (07-04, DoS-evidence, medium, mitigate)

**MITIGATED_VERIFIED**

- Listener-PID re-check against the 07-02 baseline: runbook `ss` re-baseline at
  `docs/runbooks/gal-07-live-handoff.md:149,160` (with the rationale that only listener
  PIDs prove no single-tool restart, `:163-167`); findings rows 2a-3 and 3a-3 verified
  PIDs unchanged after every motion ("T-07-16 held").
- D-06 pre-restart backups implemented as steps: `docs/runbooks/gal-07-live-handoff.md:141-150`
  (copy trace_logs + journal + service/listener snapshot) and executed at findings row
  1a-4 (backup `pre-gal07-20261102T112327Z`).
- Even under the real relaunch that occurred in Part 1 (11:55:12Z manager relaunch), the
  tool-log attempt accounting in row 3a-3 evidences that submission counts are
  reconstructable per folder — the log surface is the live folder's own file, counted
  within it.

## Ledger-replay spot-check (service-venv core at the pinned commit)

**VERIFIED**

- The service venv's installed `stack_automation_layer` resolves to the pinned commit via
  `.venv/lib/python3.10/site-packages/stack_automation_layer-0.1.0.dist-info/direct_url.json`
  (`vcs_info.commit_id = 934a621ece116a8b263897c1e9b62b57374f4ef3`, matching
  `/home/formulatrix/data/nikko/stack-automation-layer` HEAD).
- The gate's check 3 asserts exactly this from `direct_url.json`
  (`docs/runbooks/gal-07-live-check.sh:187-201`), falsified by
  `venv_pin`/`missing_direct_url` test cases (wrong commit and absent file both →
  `BLOCKED:`).
- `REPLAY_WINDOW_S`-gated refusal path confirmed in `tools/stack/ledger.py:55,183-193`
  and `tools/stack/server.py:1107-1112,1146-1147` (see T-07-15).
- Owner-lock primitives the gate probes exist in the pinned core:
  `.venv/.../stack_automation_layer/owner_lock.py:42-197` (`default_lock_dir`,
  `endpoint_key`, `lock_path`, `LockHolder`, `StackOwnedError`, `acquire_owner_lock` with
  the "already owned by … only one front end" wording at `:82`).

## Pre-flight gate disposition summary (the declared single-owner enforcement)

All gate obligations verified present and falsified:

- Identity check: `gal-07-live-check.sh:80-87`.
- Owner-lock single-owner enforcement incl. the flocked `galago`-holder exemption
  ("GALAGO-OWNED", `:156-177`) and refusal of `mcp`/`stack-mcp`/unknown/absent owners
  (`:160-166`); both dispositions proven by tests
  (`test_gate_accepts_the_galago_owned_lock`, `test_gate_blocks_an_unknown_lock_owner`,
  and the `held_lock` removal case).
- H-02 corroboration branch fail-closed: `gal-07-live-check.sh:108-122` — a fallback lock
  probe that cannot prove the same lock dir as the service venv core emits
  `forbidden: … uncorroborated` and sets `failed=1`. *(Note: the fixture tests always set
  `GAL07_LOCK_PROBE_PYTHON`, so this branch is code-verified here but exercised only at
  runtime, not in the test matrix — recorded as an observational note, not a gap; the
  branch's failure direction is fail-closed.)*
- DEP-02 re-run gate: `:203-211` (missing/failing gate never counts as OK).
- Web bundle: `:213-221`. RUNNING-run check: `:247-267` (unrecognized envelope fails
  closed). Credentials presence-only (mode 0600, assignment-line count, value never
  read/echoed): `:269-298`; tested advisory-vs-blocking.
- Read-only proof: header `:10-14` + `test_gate_is_read_only` (file-tree snapshot before/
  after two runs, including no lock file creation — the probe opens without `O_CREAT`,
  `:137`).

The gate was re-executed during this audit through its full test module with zero skips.

**New findings:** none blocking. One observational note above (uncorroborated
fallback-corroboration branch not exercised by the fixture matrix). Findings rows
2a-1..3a-3 record two pre-event D-14 cycles (manager mode/robot-disconnection, arm-reach
`movementError` × 2) — both resolved by acknowledge-after-inspection with the latch clear
and no motion outside the event; the D-11 discipline held under fire.

## Security Audit Complete
