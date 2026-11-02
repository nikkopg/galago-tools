# GAL-07 live handoff runbook: STACK -> F.A.S.T. -> STACK (live, supervised)

This runbook is the one supervised live procedure for Phase 7: the safe-order deploy (Part 1,
LIVE-08), the supervised live rehearsal `Transfer` on `stack2-6` (Part 2, LIVE-09) and the
supervised live GAL-02 handoff STACK -> F.A.S.T. -> STACK on hardware (Part 3, LIVE-10). It sits
beside the executable pre-flight gate `docs/runbooks/gal-07-live-check.sh`; the gate and this
runbook are checked together by `tools/tests/gal07_live_runbook_test.py`. Every part's entry gate
is a `PREFLIGHT OK` verdict from that script, re-run immediately before the part's typed GO gate.

`docs/runbooks/gal-02-handoff.md` (the Phase 6 simulated-session runbook) is untouched by Phase 7
and remains byte-identical; its refusal to target `10.150.1.125` or `stack-server` remains in force
there. This runbook is the only file of the two that points at the live STACK.

## Safety rules

- The live manager is exactly 10.150.1.125 port 5005 on robot `stack2-6`. The tool-store config
  host string must be byte-for-byte `10.150.1.125`: a different string (`stack-server`, a
  trailing space) is, by core design, a different endpoint key with its own lock and state files,
  and would silently split the single-owner guarantee (D-05).
- stack-mcp is closed during Galago runs. The pre-flight's lock probe refuses the session whenever
  another front end holds the owner lock; the runbook does not stop stack-mcp, it only refuses to
  run while it is open (D-05).
- A state file, a stack ledger file or a lock file is never deleted — not to clean up, not to
  recover, not after a failure. A missing state file reads as a clean start and silently clears a
  failure latch; a deleted ledger file defeats the no-second-transfer guarantee. Recovery is
  acknowledge-after-inspection, never restart-to-reset (D-11).
- A latched failure is cleared only after the operator has inspected the arm, from the
  stack-manager UI at http://10.150.1.125:5005 (primary route, D-02), with the recorded guid and
  the literal `"yes"` arm-inspected decision; the `AcknowledgeFailure` command from the STACK tool
  page is the fallback. After a restart during a transfer the message reads "tool restarted
  mid-transfer; inspect the arm; the core may not have latched this failure" — the session stops,
  and the outcome is never replayed as SUCCESS.
- Credentials (`STACK_USER`/`STACK_PASSWORD`) reach the tool server only through the operator's
  0600 env file; they are never typed into this runbook, the Findings log, a findings row or
  shell history, and every consistency check on them in this session is presence-only (D-06).
- A manual re-send of a completed step copies the step key byte-for-byte from the run's stored
  row and only inside the replay window (`REPLAY_WINDOW_S` is 600 s); a later refusal is expected
  behaviour, never a defect.

## Pre-flight

Before any part of this runbook runs, from the galago-tools root:

```bash
bash docs/runbooks/gal-07-live-check.sh
```

- The last line must read `PREFLIGHT OK` (exit 0). Every check runs even when one fails, so all
  pieces missing at once are visible in one run; the checks with issues print their own
  `missing:`/`forbidden:`/`warn:` lines above the verdict. Check 1 requires the manager to answer
  GET `/api/general/application` with productName `Stack manager`; check 2 refuses the session
  when the owner lock for `10.150.1.125:5005` is already held.
- Any `BLOCKED:` verdict (exit 1) stops the session. Never hand-edit a config, hand-write a store
  entry or drive the queue another way to clear a `BLOCKED:` line; resolve the named piece
  through this runbook's own operator steps and re-run the script.
- Parts 2 and 3 additionally run the pre-flight with `GAL07_REQUIRE_STACK_ENV=1`, so a missing
  credentials env file blocks instead of printing an advisory `warn:` line.
