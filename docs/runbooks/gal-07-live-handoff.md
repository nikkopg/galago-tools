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
  page is the fallback. After a restart during a transfer the message reads
  "tool restarted mid-transfer; inspect the arm; the core may not have latched this failure" —
  the session stops, and the outcome is never replayed as SUCCESS.
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

## Part 1: deploy (LIVE-08)

Part 1 lands the DEP-02 STACK lineage on forb01 in the safe order: the core into the service
`.venv` first, the service restart second, the operator reconnect third, and `galago-web` rebuilt
last. The order evidence is the four strictly increasing UTC timestamps in this part's evidence
table. Nothing in this part works around the pre-flight.

### Pre-deploy record (rollback anchors)

Filled at execution time, before the GO gate:

- galago-web pre-deploy image ID: `<docker inspect galago-web --format='{{.Image}}'>`
- service `.venv` pre-deploy core (rollback target): `fast_mcp` at the v1 pin `b30b38d` (no
  stack_automation_layer yet)
- running adapter SHA (rollback target): this checkout's HEAD, which the deploy does not change

### GO gate for Part 1 (D-10)

- **Decision:** deploy the STACK tool now in the safe order of this part.
- **Who:** The user (operator), in this session; no auto-advance passes this gate.
- When: Session time, UTC — after the pre-flight's `PREFLIGHT OK` and the pre-deploy record
  above; the reply's UTC timestamp is recorded in Findings row 1a-1.
- Reply: literal go.

### Step 1 — core into the service `.venv`

Preview first, so only `stack_automation_layer` changes (uv only, never pip, never
`bin/make deps` — the service `.venv` is uv-managed):

```bash
cd /home/formulatrix/data/nikko/galago-tools
~/.local/bin/uv pip install --dry-run --python .venv/bin/python -r tools/stack/requirements.txt
```

The pinned `git+https://gitlab.formulatrix.com/...@934a621ece116a8b263897c1e9b62b57374f4ef3`
install must authenticate with the user's GitLab credentials; an auth failure here is a hard
stop. The resolution checkpoint (credentials, or the user's explicit D-04 waiver for a verified
local-clone install) lives in plan 07-02, which executes this step — the resolution and both
sides' verbatim reasons go into Findings row 1a-1. Never hand-edit the pin to make an install
pass.

```bash
~/.local/bin/uv pip install --python .venv/bin/python -r tools/stack/requirements.txt
.venv/bin/python -c "import importlib.metadata as m, json; d = json.loads(m.distribution('stack_automation_layer').read_text('direct_url.json')); assert d['vcs_info']['commit_id'] == '934a621ece116a8b263897c1e9b62b57374f4ef3'"
.venv/bin/python -m unittest tools.tests.stack_test -v
```

**Do not continue unless** the direct_url commit assert and the unittest run both pass. If either
fails: do not restart anything, record findings row 1a-2 as FAIL, stop the session, and reinstall
only on the user's go-ahead (D-14).

### Step 2 — credentials env file, log backup (D-06), restart

1. The operator creates the credentials env file through an editor (never a heredoc, never a
   printed value), exactly one assignment line per credential name:

   ```bash
   install -m 600 /dev/null ~/.config/galago-tools/stack.env   # then edit it as the operator
   grep -c '^STACK_USER=' ~/.config/galago-tools/stack.env     # presence-only: prints 1
   grep -c '^STACK_PASSWORD=' ~/.config/galago-tools/stack.env # presence-only: prints 1
   stat -c '%a' ~/.config/galago-tools/stack.env               # prints 600
   ```

2. Wire it before the restart, then daemon-reload:

   ```bash
   systemctl --user edit galago-tools   # add: EnvironmentFile=%h/.config/galago-tools/stack.env
   systemctl --user daemon-reload
   ```

3. Back up the logs before the restart (D-06) — a tool-server start truncates its log in place:

   ```bash
   TS=$(date -u +%Y%m%dT%H%M%SZ); BK=~/.local/share/galago/log-backups/pre-gal07-$TS
   mkdir -p "$BK"
   cp -a ~/.local/share/galago/trace_logs/$(ls -t ~/.local/share/galago/trace_logs/ | head -1) "$BK"/
   journalctl --user -u galago-tools --since "@$(($(date +%s) - 86400))" --no-pager > "$BK/journal.log"
   systemctl --user show galago-tools -p MainPID -p ActiveEnterTimestamp | tee "$BK/service.txt"
   ss -ltnp | grep -E ':(40000|40001|40012|11010|8081)\b' | tee "$BK/listeners.txt"
   ```

4. Restart, then check (record findings rows 1a-3 and 1a-4):

   ```bash
   systemctl --user restart galago-tools
   systemctl --user is-active galago-tools                 # active
   systemctl --user show galago-tools -p MainPID           # differs from $BK/service.txt
   journalctl --user -u galago-tools --since "<restart>" --no-pager | grep -iE 'traceback'
   .venv/bin/python scripts/fast_status.py --port 40012    # NOT_CONFIGURED
   ss -ltnp | grep -E ':(40000|40001|40012|11010|8081)\b'   # the listener-PID re-baseline
   ```

   Expected: `is-active` active, a new `MainPID`, no Python traceback in the journal, the STACK
   tool server on :40012 answering `NOT_CONFIGURED`, and the newest `trace_logs` folder holding
   `Stack.log`. The `ss` listener-PID re-baseline is the no-restart reference for the rest of the
   session: the manager page on :8081 can restart a single tool server without changing
   `MainPID`, so only the listener PIDs prove no tool restart.

**Do not continue unless** all Step 2 checks pass.

### Step 2b — operator reconnect, in the decided order

The operator works from galago-web's tool pages (a `Configure` is a user click, never something
an automated session sends):

1. The F.A.S.T. tool is created and Configured **first**.
2. The STACK tool is then Configured in **real mode LAST**, so the final store action before any
   run is the STACK Configure (the planner decision per OQ-3, guarding the Phase 6 watch item
   where reconfiguring one tool dropped the other's store entry — the failure modes were
   "Tool ... not found in store. Must be configured first.").
3. The stored STACK config is used unchanged: host `10.150.1.125`, port `5005`, snake_case keys,
   empty `ledger_dir`. This closes the pre-flight's D-12 store gap: the `missing: a type fast
   tool` and host lines disappear after this step, and check 6 now asserts the stored host is
   byte-for-byte `10.150.1.125`.
4. Expect exactly one restart-warning line in `Stack.log` at the STACK open (the D-09 latch
   clause below). More than one, or a traceback, is a finding.
5. Post-connect checks (record findings row 1a-5):

   ```bash
   .venv/bin/python scripts/fast_status.py --port 40012   # READY
   ```

   and from the STACK tool page: `GetRobotStates` lists `stack2-6 idle`; `GetManagerState` is
   `automated` with recovery null.

### Step 3 — rebuild galago-web (last)

```bash
docker tag galago-core-galago-web:latest galago-core-galago-web:rollback-pre-gal07
cd /home/formulatrix/data/nikko/galago-core
TOOLBOX_PORT=11010 docker compose up -d --build
docker inspect galago-web --format='{{.Image}}'
curl -sf http://localhost:3010/api/health
docker exec galago-web grep -rl Command_Transfer /app/gen-interfaces | head -1
```

Expected: the running image ID differs from the `rollback-pre-gal07` anchor; `/api/health` and
the runs page answer 200; `Command_Transfer` is present in the container bundle. Cache-hit STOP
rule (v1 precedent): if the rebuilt image ID is byte-identical to the anchor, stop the session
for a user decision — a cache hit never counts as "new". Record findings row 1a-6 and the four
strictly increasing UTC timestamps in the evidence table.

### Interrupted deploy

If any step of Part 1 fails or is interrupted, stop the session where it stands, keep the partial
state, never delete anything to retry, re-run `bash docs/runbooks/gal-07-live-check.sh`, and
resume only after its `PREFLIGHT OK`. Rollback runs only on the user's go-ahead, in reverse
order (galago-web, adapter, core) — never roll the core back while the new UI runs.

### Part 1 evidence table (LIVE-08 order proof)

| Step | UTC start | UTC end | Check output (one line summary) | Result |
|------|-----------|---------|---------------------------------|--------|
| Step 1 | | | | |
| Step 2 | | | | |
| Step 2b | | | | |
| Step 3 | | | | |

The four `UTC start` values must be strictly increasing: it is the LIVE-08 order proof, and the
two anchor facts (core install before the restart, restart before the rebuild) come from it.

## Part 2: supervised live Transfer (LIVE-09)

The rehearsal Transfer moves one plate on `stack2-6` with the user present. One command is in the
blast radius: a single `Transfer` from the STACK tool page, nothing queued.

1. Re-run the pre-flight immediately before the GO gate, both forms, each ending `PREFLIGHT OK`:

   ```bash
   bash docs/runbooks/gal-07-live-check.sh
   GAL07_REQUIRE_STACK_ENV=1 bash docs/runbooks/gal-07-live-check.sh
   ```

2. GO gate (D-10):

   - **Decision:** send exactly one supervised live Stack `Transfer` on hardware.
   - **Who:** The user (operator), in this session; no auto-advance passes this gate.
   - When: Session time, UTC — after the pre-flight re-run; the reply's UTC timestamp goes
     into Findings row 2a-1.
   - Reply: literal go.

3. Reads-first parameter selection (never hardcode hardware params): from the STACK tool page
   run `ListDevices`, `ListLabwareProfiles` and `GetLabwarePresence` for robot `stack2-6`, and
   pick a device/deck/nest triple and a labware profile the presence read reports. The known
   hardware nests are `nest-1/deck1/A1`, `orange-nest/deck1/A1` and `rack/l1/A1`; the source and
   destination should be two different nests holding labware.

4. The event: one single `Transfer` from the Stack tool page with a fresh per-event step key,
   recorded with UTC times (start, reply) in findings row 2a-2. Expected duration 30-32 s (the
   estimate runs about 1.7x conservative on hardware — compare `GetTransferEstimate` or the
   tool's own estimate against the wall clock, and record both).

5. Expected outcome (record findings row 2a-3): the transfer returns SUCCESS with result `ran`;
   afterwards `stack2-6` is idle, `GetManagerState` is automated with recovery null, and no
   failure latch is set (`GetFailureLatch` shows none). A step key is never reused across runs;
   a forced re-send of this completed step (if the user asks for one) copies the step key
   byte-for-byte from the run's stored row and only inside `REPLAY_WINDOW_S` (600 s).

## Part 3: supervised live GAL-02 handoff (LIVE-10)

1. Re-run both pre-flight forms as in Part 2. The pre-flight's check 6 is the pre-store check:
   the store must hold a configured stack tool (host byte-for-byte `10.150.1.125`) and a fast
   tool; a `missing: a type fast tool` line here is the Phase 6 watch item, resolved through the
   operator's store steps, never through the run form.

2. GO gate (D-10):

   - **Decision:** run the supervised live GAL-02 handoff on hardware.
   - **Who:** The user (operator), in this session; no auto-advance passes this gate.
   - When: Session time, UTC — after the pre-flight re-run; the reply's UTC timestamp goes
     into Findings row 3a-1.
   - Reply: literal go.

3. Live parameter mapping (from the queue form, no script edit): `stack_tool` is `Stack` (the
   store's exact name), `fast_tool` is the real F.A.S.T. tool name from the store, `numberOfRuns`
   stays at 1, and the nest triples come from the Part 2 reads (`source_*` from the nest chosen
   as the plate's home, `fast_*` for the F.A.S.T.-side position; the F.A.S.T. step fields keep
   the v1 config values). `batch_label` is a fresh per-run label.

4. The run: the three legs complete in order (the Tool Box note, the STACK in leg, the F.A.S.T.
   `transfer`, the STACK out leg) to overall SUCCESS (record findings row 3a-2). Fresh step keys
   are minted per run; keys are read from the run's stored rows. Expected total wall time ≈ 35 s
   + the F.A.S.T. transfer time + 35 s, plus queue overhead.

5. Post-run (record findings row 3a-3): `stack2-6` idle and automated with recovery null; the
   ledger at `~/.local/state/galago-tools/stack/` holds one done record per leg key; nothing was
   deleted; no failure latch is set.

## Recovery drill (D-11)

Run this drill for any failed or ambiguous live outcome (`failed`, `timedOut`, `lost`, a
restart during a transfer, a refusal whose reason is not self-explanatory), with the session
stopped:

1. Stop the session. No new commands are sent; nothing is re-queued.
2. Read the ledger at `~/.local/state/galago-tools/stack/stack-ledger.json` (a plain read, never
   a delete) and run `GetFailureLatch` from the STACK tool page — a zero-I/O read of the core's
   injected latch, which shows the guid to acknowledge even after a restart.
3. The operator inspects the arm physically. Nothing moves again until the operator says what
   the arm is doing (or has done).
4. Clear the latched failure from the stack-manager UI at `http://10.150.1.125:5005` (the
   primary live recovery route, D-02): use the recorded guid and answer the arm-inspected
   decision with the literal `yes`.
5. The `AcknowledgeFailure` command from the STACK tool page is the fallback, with the same
   guid and the same literal `yes` decision.
6. Never delete the state file, a ledger file or a lock file (a missing state file reads as a
   clean start and silently clears a latch), and never restart the tool server to clear a
   failure: a restart during a transfer is announced as
   "tool restarted mid-transfer; inspect the arm; the core may not have latched this failure",
   and such an outcome is never replayed as SUCCESS. Recovery is acknowledge-after-inspection,
   never restart-to-reset.
7. A manual re-send of a completed step copies the step key byte-for-byte from the run's stored
   row and only inside the replay window (`REPLAY_WINDOW_S` is 600 s). A re-send after the
   window answers "step key already completed ... nothing was sent" — that refusal is expected
   behaviour, never a defect.

## Findings log

Fill a row when its step is done. The Result is PASS or FAIL against the expectations above, and
a FAIL stops the session (D-14: stop → fix → gate → redeploy → rerun, never silent pass). Never
paste a credential or token.

| Row | UTC timestamp | Requirement | Observation | Result |
|-----|---------------|-------------|-------------|--------|
| G0 | | LIVE-08, LIVE-09, LIVE-10 | | |
| 1a-1 | | LIVE-08 | | |
| 1a-2 | | LIVE-08 | | |
| 1a-3 | | LIVE-08 | | |
| 1a-4 | | LIVE-08 | | |
| 1a-5 | | LIVE-08 | | |
| 1a-6 | | LIVE-08 | | |
| 2a-1 | | LIVE-09 | | |
| 2a-2 | | LIVE-09 | | |
| 2a-3 | | LIVE-09 | | |
| 3a-1 | | LIVE-10 | | |
| 3a-2 | | LIVE-10 | | |
| 3a-3 | | LIVE-10 | | |

Row guidance: G0 is the entry pre-flight verdict for each part (exit code and last line; one
commit of evidence per part or one line per run). 1a-1 records the OQ-1 core-install decision and
the Part 1 GO reply timestamp; 1a-2 the Step 1 install and its discriminating checks; 1a-3 the
credentials wiring and the pre-restart backup (paths and counts only); 1a-4 the restart checks
including the listener-PID re-baseline; 1a-5 the reconnect order and the post-connect reads;
1a-6 the galago-web rebuild (image IDs, health, bundle) and the four strictly increasing UTC
timestamps. 2a-1 the Part 2 pre-flight, reads and GO reply timestamp; 2a-2 the rehearsal Transfer
(keys, outcome, wall time); 2a-3 the post-run state. 3a-1 the Part 3 pre-flight, pre-store check
and GO reply timestamp; 3a-2 the three-leg run; 3a-3 the post-run ledger and counts.
