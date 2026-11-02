# GAL-02 handoff runbook: STACK -> F.A.S.T. -> STACK (simulation only)

This runbook sits beside the protocol `docs/runbooks/gal-02-handoff.protocol.json`. The protocol is
checked by `tools/tests/gal02_handoff_test.py` and `tools/tests/gal02_replay_test.py` (offline), and
this runbook by `tools/tests/gal02_runbook_test.py`. It covers Phase 6 requirements FLOW-01 (the
protocol and this runbook), FLOW-02 (Galago-simulated workcell run), FLOW-03 (a re-dispatched STACK
step sends no second transfer) and FLOW-04 (STACK real mode against the PAC simulator).

## Safety rules

- Simulation only. Nothing in this runbook moves hardware.
- Nothing targets 10.150.1.125 or stack-server before Phase 7.
- The executor (an automated session) never starts Docker, the PAC simulator, galago-core, a tool server or a run.
- The executor never clicks a real-mode Configure and never sends a STACK command (SAL runbook A.0, A.10).
- Production galago-web (:3010) and its DB are never used (D-16e).
- Credentials come only through the sourced sim env files. They are never typed into this runbook, the Findings log or shell history.
- Galago-simulated STACK and real-mode STACK use separate tool-server processes and separate Galago tool instances (D-16b).
- A ledger file is never deleted (Phase 5).

## What each part proves

| Part | Environment | Proves | Does not prove |
|------|-------------|--------|----------------|
| Part 1 | Offline: node script stub and the fake core, no Docker | The protocol emits the right four rows and keys; a re-dispatched stored STACK step is answered from the ledger (replayed SUCCESS) and the fake core's accepted-submit count stays at 1 | That galago-core imports and queues the protocol the same way; anything about the PAC simulator |
| Part 2a | Dev galago-core, STACK and F.A.S.T. both Galago-simulated | The protocol imports (Mode Script, four rows), runs to completion through the real queue, and its stored STACK step survives a re-dispatch | That no second transfer is sent (simulated mode never writes the ledger and never reaches an instrument) |
| Part 2b | Dev galago-core, STACK in real mode against the loopback PAC simulator, F.A.S.T. Galago-simulated | A real-mode run completes against the simulator, and a re-sent in leg is answered `replayed true` with no second manager task | Anything about hardware: the simulator models no plate presence or grip (SAL A.7) |

The Galago-simulated re-dispatch in Part 2a proves only that the protocol's stored STACK step survives a re-dispatch through the real queue: it returns SUCCESS and no ledger file appears in the configured ledger_dir. It does not prove that no second transfer is sent; only the offline fake-core test (tools/tests/gal02_replay_test.py) and the Part 2b run against the PAC simulator prove that.

## The protocol

`docs/runbooks/gal-02-handoff.protocol.json` is galago-core's script-protocol export format. Its
script emits four queue rows, in this order:

1. a Tool Box note naming the run's key base;
2. STACK `transfer` (in leg: source location -> F.A.S.T.-side location);
3. F.A.S.T. `transfer`;
4. STACK `transfer` (out leg: the in leg's locations swapped).

"Three steps" means the three tool steps (rows 2 to 4). The script emits no `acknowledge_failure` and
no other operator-only command.

### Parameters

Every parameter name is used exactly as written below. All values reach the script as strings; the
script converts numbers itself. "Required" means a blank value stops the script (see below).

| Name | Type | Required | Default | Meaning |
|------|------|----------|---------|---------|
| `batch_label` | string | yes | `GAL02` | Run label at the start of both STACK step keys; only its first 20 characters are used |
| `stack_tool` | string | yes | `STACK` | Name of the STACK tool instance in the workcell (exact case) |
| `fast_tool` | string | yes | `FAST` | Name of the F.A.S.T. tool instance in the workcell (exact case) |
| `robot` | string | yes | `sim-arm-1` | STACK robot for both transfers |
| `labware_profile` | string | yes | `greiner 96 white` | STACK labware profile for both transfers |
| `source_device` | string | yes | `sim-nest-a` | Where the plate starts and returns: STACK device |
| `source_deck` | string | yes | `sim-deck-a` | Source STACK deck |
| `source_nest` | string | yes | `sim-A1` | Source STACK nest |
| `source_transfer_profile` | string | no | blank | STACK transfer profile for the source location; blank sends none |
| `fast_device` | string | yes | `sim-nest-b` | STACK device that stands for the F.A.S.T. deck position |
| `fast_deck` | string | yes | `sim-deck-b` | STACK deck for the F.A.S.T. position |
| `fast_nest` | string | yes | `sim-B1` | STACK nest for the F.A.S.T. position |
| `fast_transfer_profile` | string | no | blank | STACK transfer profile for the F.A.S.T.-side location; blank sends none |
| `stack_timeout_s` | number | no | blank | Wait budget in seconds for each STACK transfer; blank uses the adapter default |
| `fast_step_source_deck` | number | yes | 1 | F.A.S.T. `source_deck` (deck slot number) |
| `fast_step_dest_deck` | number | yes | 3 | F.A.S.T. `dest_deck` (deck slot number) |
| `fast_step_source_plate_id` | number | yes | 1 | F.A.S.T. `source_plate_id` |
| `fast_step_dest_plate_id` | number | yes | 1 | F.A.S.T. `dest_plate_id` |
| `fast_step_source_start_row` | string | yes | `A` | F.A.S.T. `source_start_row` (one or two letters) |
| `fast_step_source_start_col` | number | yes | 1 | F.A.S.T. `source_start_col` |
| `fast_step_dest_start_row` | string | yes | `A` | F.A.S.T. `dest_start_row` (one or two letters) |
| `fast_step_dest_start_col` | number | yes | 1 | F.A.S.T. `dest_start_col` |
| `fast_step_num_rows` | number | yes | 8 | F.A.S.T. `num_rows` |
| `fast_step_num_cols` | number | yes | 1 | F.A.S.T. `num_cols` |
| `fast_step_volume` | number | yes | 10 | F.A.S.T. `volume` in microlitres, above 0 |
| `fast_step_tip_reuse` | select | yes | `fresh` | F.A.S.T. `tip_reuse` mode: `fresh` or `reuse` |
| `fast_step_expected_tray_id` | number | no | blank | F.A.S.T. `expected_tray_id`; blank sends none |

Why the F.A.S.T. names carry `fast_step_`: the F.A.S.T. proto has an integer `source_deck`, and the STACK
`source_deck` is a string. Both would collide in galago-core's flat params and in its per-parameter
workcell variables (D-13). The deck fields (`source_deck`, `fast_deck`) are STACK strings (D-14).

### Step keys

- The key base is the first 20 code points of the batch label, then the ISO timestamp, then 8 hex
  characters. The keys end `-in` and `-out`, and are at most 58 characters.
- They are minted once at queue time and stored with the queued commands. They stay stable across an F5
  re-dispatch and a retry, and are new on every run.
- Keep `numberOfRuns` at 1. A value above 1 would evaluate the script once per run.
- Preview re-evaluates the script, so its keys differ from the run's. Record keys from the run's stored
  rows, never from Preview.
- A blank optional input is omitted from the emitted params. It is never sent as an empty string.
- A blank required input throws. The run form then shows only "Could not generate commands for the given
  params." and the real message appears in Preview.
- galago-core replaces any value that starts `{{` and ends `}}`. Step keys never do.

## Part 1: offline proof (any session)

No Docker, no galago-core, no instrument. Needs node (the nvm copy is enough) and the venv.

Quick command:

```bash
cd /home/formulatrix/data/nikko/galago-tools
source ~/data/nikko/.venvs/galago-py310/bin/activate
export PATH=$HOME/.nvm/versions/node/v24.14.1/bin:$PATH
python -m pytest tools/tests/gal02_handoff_test.py tools/tests/gal02_replay_test.py tools/tests/gal02_runbook_test.py -q -rs -p no:cacheprovider
```

Full gate:

```bash
cd /home/formulatrix/data/nikko/galago-tools
source ~/data/nikko/.venvs/galago-py310/bin/activate
export PATH=$HOME/.nvm/versions/node/v24.14.1/bin:$PATH
bin/make proto test
```

Expect 0 skipped in the gal02 modules. A skip means node was not found, and then nothing was proven.

Part 1 proves (D-06): the protocol script yields the four rows and run-unique keys; the out leg is the in
leg swapped; a re-dispatch of the stored in-leg params through a real-mode StackServer on the fake core is
answered `SUCCESS` with `replayed` true while the accepted-submit count stays at 1; a refused first try
releases the key; a re-send after `REPLAY_WINDOW_S` is refused with "step key already completed". It does not
prove that galago-core imports or queues the script the same way (Part 2 owns that).

## Part 2 gate: DEP-02

Part 2 needs galago-core Phase 5 (DEP-02, STACK Codegen & Command Forms). It has not landed unless
this gate says so.

1. From the galago-tools root run:

   ```bash
   bash docs/runbooks/gal-02-dep02-check.sh
   ```

   The script is read-only. Set `GALAGO_CORE_DIR` if galago-core is not at `../galago-core`.
2. `DEP-02 OK` on the last line means continue.
3. Any `BLOCKED:` line means stop. Part 2 does not start. The `missing:` and `forbidden:` lines above it say which piece is absent; see galago-core `.planning/ROADMAP.md` Phase 5.
4. Never hand-write stack types into galago-core and never drive the queue another way to get around the gate (D-01).
5. Record the verdict line and the printed galago-core HEAD in Findings row G0.
6. Once the gate is OK, also confirm two things (the operator runs both):
   - the dev galago-core in use was started from that source (its dev compose bind-mounts `./controller`);
   - galago-core's own `controller/test/commandFields.test.ts` passes there.

## Part 2 shared setup (operator)

Everything here is the operator's. The executor does not run any of it.

Working directory (not committed):

```bash
export GAL06_DIR=/home/formulatrix/data/nikko/.venvs/gal06
mkdir -p "$GAL06_DIR"
```

It holds the logs, the lock and state dirs and the compose override.

Dev galago-core (separate compose project, separate DB; never production galago-web on :3010, D-16e):

```bash
cd /home/formulatrix/data/nikko/galago-core
docker compose -p galago-gal06 -f docker-compose.dev.yml -f "$GAL06_DIR/ports.override.yml" up -d
export GALAGO_DEV_URL=http://localhost:3020
```

`$GAL06_DIR/ports.override.yml` maps 3020:3010 and 9239:9229 and adds
`extra_hosts: host.docker.internal:host-gateway`. Copy its shape from
`~/data/nikko/.venvs/gal05-ports.override.yml` and change the host ports. Confirm the UI answers at
`$GALAGO_DEV_URL` before going on.

Tool servers. Start each in the foreground from the galago-tools root with the venv python, in its own
terminal, tee'd to `$GAL06_DIR/gal02-<name>.log`:

```bash
cd /home/formulatrix/data/nikko/galago-tools
source ~/data/nikko/.venvs/galago-py310/bin/activate
# F.A.S.T., Galago-simulated, port 40011
FAST_MCP_LOCK_DIR="$GAL06_DIR/fast-locks" python -m tools.fast.server --port=40011 2>&1 | tee "$GAL06_DIR/gal02-fast.log"
# STACK, Galago-simulated, port 40010 (Part 2a), no credentials
python -m tools.stack.server --port=40010 2>&1 | tee "$GAL06_DIR/gal02-stack-sim.log"
```

The STACK real-mode server on port 40012 belongs to Part 2b only. Never use the systemd galago-tools
service. galago-core reaches tools through `host.docker.internal`, so only the port matters. The host
firewall may need a rule for 40010-40012 (operator, sudo).

Import the protocol (D-16a). The Protocols-page Import button drops `mode` and `scriptContent`
(`controller/components/protocols/ProtocolPageComponent.tsx`, lines 137-146), so a script protocol
imported that way arrives as an empty visual protocol. Do not use it. Post the `protocol` object instead:

```bash
cd /home/formulatrix/data/nikko/galago-tools
jq .protocol docs/runbooks/gal-02-handoff.protocol.json | curl -sS -X POST "$GALAGO_DEV_URL/api/protocols" -H 'content-type: application/json' --data @-
```

Post-import check, in the dev UI: Mode is Script, the script is present, and Preview with the default
params shows four rows (note, STACK transfer, FAST transfer, STACK transfer) and no error. Record this in
Findings row 2a-1.

## Part 2a: Galago-simulated workcell run (FLOW-02, FLOW-03 simulated half)

Both tools are Galago-simulated, so nothing reaches an instrument. Gate OK first (Part 2 gate).

1. Create the workcell tools in the dev UI:
   - `STACK-SIM`: type stack, port 40010, Simulated ON, Config host 127.0.0.1, ledger_dir
     `/home/formulatrix/.local/state/galago-tools/stack-galago-simulated`;
   - `FAST`: type fast, port 40011, Simulated ON, Config host sim-no-contact.invalid, port 5003,
     expected_tray_id 0, run_timeout_s 0.
2. Ledger baseline: list `/home/formulatrix/.local/state/galago-tools/stack-galago-simulated` and
   `/home/formulatrix/.local/state/galago-tools/stack`. Note what is there. Do not delete anything.
3. Queue the protocol once with `stack_tool` STACK-SIM, `fast_tool` FAST and `batch_label`
   GAL02-SIM-yyyymmdd (today's date). Leave the other parameters at their defaults.
4. Expected: about 150 s in total (about 35 s, 80 s, 35 s). The four rows complete in order. Instance
   names are exact and case-sensitive. Record row 2a-2 with the run's stored keys and the time.
5. Forced re-dispatch, from the STACK-SIM tool page: send `transfer` with the in leg's stored params,
   with `step_key` copied byte for byte from the run's stored row. Expected: SUCCESS after about 35 s
   with no meta (simulated mode keeps no ledger).
6. List the ledger dirs again: there is still no `stack-ledger.json`. In the log,
   `grep -c 'Running command Transfer' "$GAL06_DIR/gal02-stack-sim.log"` is 3 (two legs, one re-send).
7. Record row 2a-3 and include the phrase "does not prove that no second transfer is sent": this part
   shows the stored step survives a re-dispatch, nothing more.
8. Stop the STACK-SIM process (Ctrl-C) before Part 2b. A process that was ever configured simulated is
   never reused for a real-mode run (D-16b).

## Part 2b: STACK real mode against the PAC simulator (FLOW-04)

The sim account is the only account used, and only through the sourced env files.

Preconditions:

- the DEP-02 gate prints `DEP-02 OK`;
- the PAC checkout `STACK_PAC_DIR` is at 26e00251e (`git -C "$STACK_PAC_DIR" describe --tags` ends `-g26e00251e`);
- at least 3 GB is free on the scratch filesystem (`df -h`);
- the first build takes about 12 minutes.

Steps (operator):

1. Choose `STACK_SIM_PORT`, for example 15005. It must be free in `ss -ltn` and is never 5005 (taken on
   this host by an unrelated container) and never 5006 (the Device master API, D-15).
2. Build, start and seed the simulator per the stack-automation-layer runbook
   `docs/runbooks/stack-validation.md`: A.1 (build and start with `scripts/sim_up.sh up`), A.2 (seed the
   account and the lab) and A.3 (manager mode: Manual to build the lab, Automated before the run). Those
   steps are referenced, never copied here. They write `$STACK_SIM_DIR/sim.env` and
   `$STACK_SIM_DIR/sim-account.env`.
3. Start the STACK real-mode tool server on port 40012 in its own terminal:

   ```bash
   cd /home/formulatrix/data/nikko/galago-tools
   source ~/data/nikko/.venvs/galago-py310/bin/activate
   set -a; . "$STACK_SIM_DIR/sim.env"; . "$STACK_SIM_DIR/sim-account.env"; set +a
   STACK_MCP_LOCK_DIR="$GAL06_DIR/stack-pacsim-locks" STACK_STATE_DIR="$GAL06_DIR/stack-pacsim-state" \
     python -m tools.stack.server --port=40012 2>&1 | tee "$GAL06_DIR/gal02-stack-pacsim.log"
   ```

   Confirm the account is present without printing it: `grep -c '^STACK_USER=' "$STACK_SIM_DIR/sim-account.env"`
   prints 1 (D-09). Credentials are process-global: switching STACK means restarting the process with
   other env values.
4. Create the workcell tool `STACK-PACSIM`: type stack, port 40012, Simulated OFF, Config host 127.0.0.1,
   port `$STACK_SIM_PORT`, ledger_dir `/home/formulatrix/.local/state/galago-tools/stack-sim`. The path is
   absolute because `~` is refused, and it is pinned after the first Transfer. **Run the Hardware-refusal
   preflight below before the operator clicks Configure.**

### Hardware-refusal preflight

Stop the run if any item fails (D-10). The host string comes from the Config form, so check it first:

```bash
HOST=127.0.0.1   # the exact string you will type into the Config host field
case "$HOST" in
  10.150.1.125|stack-server) echo "REFUSED: $HOST is the real STACK"; false ;;
  *) echo "host ok: $HOST" ;;
esac
```

Then confirm each of these, and record the result in Findings row 2b-0:

- the last `Received configuration` line in `$GAL06_DIR/gal02-stack-pacsim.log` (after Configure) shows host
  "127.0.0.1" and the sim port;
- `ss -ltn` shows `127.0.0.1:$STACK_SIM_PORT` and not 0.0.0.0;
- `curl -fsS http://127.0.0.1:$STACK_SIM_PORT/api/general/application` reports productName "Stack manager"
  and productVersion 0.12.0-beta.1+1157;
- GetRobotStates from the STACK-PACSIM tool page lists only names starting `sim-` (the seeded robot is
  sim-arm-1);
- GetManagerState is automated and the robot sim-arm-1 is idle (SAL A.3).

### Forced re-dispatch and the no-second-POST evidence

D-11 and D-16d. The PAC simulator manager has no list-tasks endpoint, so the count is calibrated first.

1. Calibrate. Pick one counter and record its baseline: transfer submissions in the manager logs under
   `$STACK_SIM_DIR/logs-mgr`, or `docker logs stack-sim-manager` (read by the operator), or the task rows in
   `$STACK_SIM_DIR/db/pac-manager.db`.
2. Queue the protocol once with `stack_tool` STACK-PACSIM, `fast_tool` FAST and `batch_label`
   GAL02-PACSIM-yyyymmdd. The counter should read +1 after the in leg (this is the calibration) and +2
   after the run. Copy the keys from the run's stored rows and the task guids from the log. Record row
   2b-1 (calibration) and row 2b-2 (the run).
3. Within 600 s (`REPLAY_WINDOW_S`) of the in leg, re-send the in leg's stored params from the
   STACK-PACSIM tool page, with `step_key` copied byte for byte. A key that differs in any character (case, a
   trailing space) is a new step and sends a new transfer.
   - Expected: SUCCESS; meta `replayed` true, `stepKey` the in key, `ledgerState` done, the same task
     guid; an immediate reply; the robot idle; the counter +0.
   - Blank form numbers arrive as 0 (`timeout_s` 0 means unset) and blank strings as empty. A changed
     instrument field answers INVALID_ARGUMENTS and nothing is sent. If the reply is a fingerprint
     mismatch, record it as a Finding. Do not retry with edits.
   - Record row 2b-3, including how the blank fields arrived.
4. After 600 s, re-send once more. Expect ERROR_FROM_TOOL with "step key already completed ... nothing was
   sent" and the counter +0. Record row 2b-4.
5. Read the ledger `/home/formulatrix/.local/state/galago-tools/stack-sim/stack-ledger.json`. Expect one
   record per run key, state done. Never delete the file. Record row 2b-5.
6. If the counter did not move +1 on the in leg, record that it cannot prove +0. The claim then rests on:
   the same guid, the immediate reply, the robot idle, one ledger record per key, and the Part 1 counter.
   The user judges whether that suffices.

## If something goes wrong

- The script throws: use Preview in the dev UI. The run form only shows "Could not generate commands for
  the given params."
- "Unknown tools": the instance names are exact and case-sensitive (STACK-SIM, STACK-PACSIM, FAST).
- NOT_READY "stack: not configured" after simulated then real on one process: restart the process.
- Configure refuses `ledger_dir`: it is not absolute, or it is pinned to another path.
- The sim port bind fails: pick another free `STACK_SIM_PORT`, never 5005 or 5006.
- The robot is not idle or recovery is pending: the operator follows SAL A.3.
- The gate says BLOCKED: stop. See Part 2 gate.

## Known limitations

- The sim models no plate presence or grip (SAL A.7).
- Galago-simulated mode never writes the ledger.
- The run page cannot re-send a completed row (v1 Finding F5), so a re-dispatch goes through the tool page.
- The run view may show no tool error text (F3), so read the tool-server log.
- Step keys use Math.random for uniqueness, not secrecy.

## Teardown (operator only; the executor never runs it)

1. Ctrl-C the tool servers (40010, 40011, 40012).
2. Stop the simulator (SAL A.10):

   ```bash
   STACK_SIM_DIR="$STACK_SIM_DIR" scripts/sim_up.sh down
   ```

3. Bring the dev galago-core down:

   ```bash
   docker compose -p galago-gal06 -f docker-compose.dev.yml -f "$GAL06_DIR/ports.override.yml" down
   ```

4. Never delete a ledger file.

## Upstream follow-ups

- galago-core: the Protocols-page Import drops `mode` and `scriptContent`
  (`ProtocolPageComponent.tsx:137-146`). The runbook works around it with `POST /api/protocols`.
- v1 Finding F5: the queue re-executes a completed row.
- F3: no tool error text in the run view (DEP-03).

## Findings log

Fill a row when its step is done. The Result is PASS or FAIL against the expectations above, and a FAIL
stops Part 2. Never paste a credential or token.

| Row | UTC timestamp | Requirement | Observation | Result |
|-----|---------------|-------------|-------------|--------|
| G0 | | FLOW-02, FLOW-03, FLOW-04 | not run yet | pending |
| 2a-1 | | FLOW-01, FLOW-02 | not run yet | pending |
| 2a-2 | | FLOW-02 | not run yet | pending |
| 2a-3 | | FLOW-03 (simulated half) | not run yet | pending |
| 2b-0 | | FLOW-04 | not run yet | pending |
| 2b-1 | | FLOW-04 | not run yet | pending |
| 2b-2 | | FLOW-04 | not run yet | pending |
| 2b-3 | | FLOW-04 | not run yet | pending |
| 2b-4 | | FLOW-04 | not run yet | pending |
| 2b-5 | | FLOW-04 | not run yet | pending |
