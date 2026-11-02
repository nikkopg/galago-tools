# Phase 7: Deploy & Supervised Live STACK + Handoff - Research

**Researched:** 2026-11-02
**Domain:** Safe-order deployment of the STACK tool on forb01 (production), runbook authoring with executable pre-flight gates, and supervised live acceptance on real hardware (`10.150.1.125:5005`, robot `stack2-6`)
**Confidence:** HIGH (every load-bearing claim below was verified by reading the actual files/probing the actual host this session; flagged assumptions are few and listed)

## Summary

Phase 7 is a deploy + supervised-acceptance phase, not an adapter-coding phase. The adapter
(`tools/stack/`), the ledger, and the GAL-02 protocol are built and proven through the loopback PAC
simulator (Phases 4–6, all complete). What remains is: (1) deploy the DEP-02 build on **forb01**
in the v1 LIVE-04 safe order, (2) author a **new** live runbook (`docs/runbooks/gal-07-live-handoff.md`)
with an **executable pre-flight gate** and per-event GO gates, and (3) run two supervised live
events — a single `Transfer` rehearsal (LIVE-09), then the full GAL-02 handoff (LIVE-10).

Research on the live host (forb01 — this machine) surfaced **five deployment-blocking facts the
plan must handle explicitly**:

1. **The service `.venv` does not have `stack_automation_layer` installed at all** (fast-mcp is at
   the v1 pin `b30b38d`; `stack_automation_layer` has no distribution metadata in `.venv`). The
   "core into the service `.venv`" step is a real install, not a bump of an existing package.
2. **The pinned git+https install is currently broken on forb01**: the pin in
   `tools/stack/requirements.txt` points at
   `git+https://gitlab.formulatrix.com/nikkopg/stack-automation-layer.git@934a621…`, but
   `git ls-remote` against that URL fails ("HTTP Basic: Access denied … 2FA"), and
   `~/.git-credentials` holds **zero** `gitlab.formulatrix.com` entries. Every core install so far
   (the gate venv) used the **local clone** at `~/data/nikko/stack-automation-layer` — exactly what
   D-04 rules out. The user must either provide working GitLab credentials (interactive oauth/device
   flow — helpers are `cache` + `git-credential-oauth`) or explicitly approve the local-clone
   fallback. This is a hard checkpoint before Step 1 of the deploy.
3. **The production workcell store already contains a live STACK tool**: `GET /api/tools` on
   production galago-web (:3010) returns exactly one tool — id 11, type `stack`, name `Stack`,
   `localhost:40012`, config host `"10.150.1.125"`, port `"5005"`. The **F.A.S.T. tool instance is
   absent** from the store, so the D-12 pre-store check fails today: LIVE-10 cannot run until a
   FAST tool is (re-)configured. This is the Phase 6 UAT watch item made concrete.
4. **The systemd unit has no STACK credentials and no EnvironmentFile.** Real-mode Configure needs
   `STACK_USER`/`STACK_PASSWORD` in the tool-server process environment (the core reads them only
   there); the unit currently sets neither. The runbook needs an operator step that creates a 0600
   env file and wires it via `systemctl --user edit` + daemon-reload **before** the restart.
5. **The manager relaunches workcell tools automatically on service restart** (via the galago API's
   workcell config), and the manager page can restart a single tool server without a service
   restart, truncating that tool's log in place (`open(log_file, "w")`). So the runbook's
   no-restart checks must track the **tool-server listener PID** (`ss -ltnp`) and logs must be
   backed up **before** every restart (D-06) — the v1 finding, re-confirmed in code.

Everything else the phase needs is proven pattern reuse: the v1 `03-DEPLOY.md` safe-order runbook
(uv install → service restart → operator reconnect → `galago-web` rebuild, with rollback anchors and
a literal `go` gate per event), the Phase 6 runbook+protocol+check-script triple, and the generic
`ToolDriver` GetStatus script (`scripts/fast_status.py` works against any tool server, including the
STACK, via `--port`).

**Primary recommendation:** Plan the phase as: pre-flight script + live runbook authoring (with
tests, offline) → GO gate → deploy (install core into service `.venv` after the GitLab-credential
checkpoint, back up logs, restart service, operator reconnects Stack + FAST, rebuild `galago-web`)
→ GO gate → supervised LIVE-09 rehearsal Transfer → GO gate → supervised LIVE-10 GAL-02 handoff →
findings log + teardown. No adapter code changes except D-14-style fixes if a live defect appears.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Implementation Decisions (locked)

- **D-01:** Live runs proceed **without DEP-03** (no galago-core operator AcknowledgeFailure UI
  control, F3 tool-error display, or F5 root cause required first). LIVE-08..10 run on the DEP-02
  core.
- **D-02:** Operator clearing of a latched failure live happens from the **stack-manager UI**; the
  adapter-side `AcknowledgeFailure` tool-page command remains the in-Galago fallback. The runbook
  documents the manager-UI path as the primary live recovery route with the recorded guid +
  `"yes"` arm-inspected decision.
- **D-03:** Deploy on **forb01**, same host as the F.A.S.T. deployment (core in `.venv`,
  `galago-tools` systemd user service, manager on `:8081`), reusing the v1 LIVE-04 safe-order
  procedure.
- **D-04:** DEP-02 core install is a **pin bump** in the fork to the DEP-02 build lineage
  (galago-core `a5fa75f`) into the service `.venv`, followed by the `galago-tools` restart and the
  `galago-web` rebuild — **not a local-clone install**. *(Research note: the git+https install the
  pin uses is currently broken on forb01 — see Open Questions OQ-1; resolving it is the user's
  call, not a D-04 change.)*
- **D-05:** stack-mcp closure is enforced by a **pre-flight check that refuses** the session if a
  lock is held (reuse the Configure lock-holder failure message as the detection signal) — the
  runbook does not actively stop stack-mcp.
- **D-06:** **Backup each restart**: every restart in the session prefixes a timestamped copy of
  the relevant service/tool logs into a backups directory.
- **D-07:** The live runbook is a **new file** `docs/runbooks/gal-07-live-handoff.md`; the Phase 6
  runbook `docs/runbooks/gal-02-handoff.md` stays pristine and its `10.150.1.125|stack-server`
  refusal remains in force there.
- **D-08:** The runbook gets an **executable exit-code pre-flight gate** (like
  `docs/runbooks/gal-02-dep02-check.sh`) verifying live preconditions: correct manager host
  (`10.150.1.125:5005` / `stack2-6`), stack-mcp absent, DEP-02 build installed, core reachable.
- **D-09:** Staged order: **pre-flight + deploy → supervised live single `Transfer` (LIVE-09,
  rehearsal) → supervised live GAL-02 handoff on hardware (LIVE-10)**.
- **D-10:** **Explicit per-event go-ahead**: each live event (deploy, LIVE-09, LIVE-10) waits for a
  typed go-ahead from the user, recorded in the session log with a timestamp; no auto-advance
  passes a GO gate.
- **D-11:** Drill for an **ambiguous or failed live outcome**: stop the session, inspect the ledger
  state and the core in-flight guard, operator inspects the arm, then clear via the manager UI
  affected state (a restart-during-transfer is reported as needing arm inspection, never replayed
  as SUCCESS).
- **D-12:** **Pre-store check** guards against the Phase 6 UAT watch item: the pre-flight/first-run
  checklist verifies every tool in the GAL-02 protocol (STACK and F.A.S.T.) is configured in the
  tool store in an up-front-decided configuration order before a run is started.

### the agent's Discretion

- Exact contents/format of the runbook sections and the pre-flight script implementation details
- Backup directory naming and log file selection specifics
- How the pre-store check is expressed (script assertion vs runbook checklist) — planner's call
- Internal ordering of the three-part check script assertions

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LIVE-08 | Deployed in the safe order (core → service `.venv` → restart `galago-tools` → rebuild `galago-web`); stack-mcp closed during Galago runs; both front ends use the identical host string, lock dir and core state dir, so a galago ↔ mcp hand-over shares the persisted failure latch; the state file is never deleted | v1 `03-DEPLOY.md` safe-order runbook with four strictly-increasing UTC timestamps; verified service `.venv`/systemd/manager facts (§Standard Stack, §Deploy Facts); lock/state-dir resolution rules read from core source (§Architecture Patterns P2/P3); lock-probe pre-flight design (§P1) |
| LIVE-09 | A supervised, runbook-gated live STACK Transfer reaches `ran` on `stack2-6` with the user present | Hardware facts (manager `10.150.1.125:5005`, robot `stack2-6`, nests, build `0.12.0-beta.1+1157`) re-verified live; `ran` mapping and D-09 restart clause from `tools/stack/server.py`; GO-gate + findings-row pattern from v1/Phase 6 |
| LIVE-10 | A supervised live GAL-02 handoff runs STACK → F.A.S.T. → STACK to SUCCESS on hardware | GAL-02 protocol (27 params) verified; **production store currently lacks a FAST tool** — D-12 pre-store check must gate this (§Deploy Facts #3); live param values from reads-first runbook step (ListDevices/ListLabwareProfiles/GetLabwarePresence) |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Safe-order deploy (core install, service restart, web rebuild) | Host (forb01 shell + systemd + docker) | — | v1 LIVE-04 precedent; all three moving parts are host-managed, no code tier |
| Pre-flight gate (host/lock/DEP-02/store checks) | Host script (`docs/runbooks/gal-07-*.sh`) | gate venv python (uses pinned core's own `owner_lock` helpers) | Exit-code gate pattern from Phase 6; must fail closed before anything touches hardware |
| Live `Transfer` (LIVE-09) | Production galago-web (:3010) tool page — operator | galago-tools STACK tool server (:40012) → core → manager | Operator-run like all live events; the adapter is already proven and changes only on a live defect (D-14 route) |
| GAL-02 handoff (LIVE-10) | Production galago-web queue | STACK + F.A.S.T. tool servers on forb01 | Script protocol queued through the real queue; three tool steps in order |
| Failure recovery (D-11 drill) | STACK manager UI at `10.150.1.125:5005` — operator | STACK tool page (`AcknowledgeFailure` fallback, D-02) | Core owns the latch; the manager UI is the primary live clearing route per D-02 |
| Log backup per restart (D-06) | Host shell (cp into a timestamped backups dir) | — | Tool-server start truncates its log file in place (verified in `web_server.py`) |

## Standard Stack

No new external packages are installed by this phase. The stack is already built and pinned; the
phase deploys it.

### Core (deploy artifacts — versions verified this session)

| Artifact | Version / SHA | Purpose | Verification |
|----------|--------------|---------|--------------|
| stack-automation-layer (the core) | pinned `934a621ece116a8b263897c1e9b62b57374f4ef3` in `tools/stack/requirements.txt:2` | The only STACK dependency; must land in the **service** `.venv` | [VERIFIED: requirements.txt:2 — quote: `stack-automation-layer @ git+https://gitlab.formulatrix.com/nikkopg/stack-automation-layer.git@934a621ece116a8b263897c1e9b62b57374f4ef3`; service `.venv` has **no** stack_automation_layer metadata (probe); local clone `~/data/nikko/stack-automation-layer` HEAD = `934a621` ("docs(runbook): record the additive latchStatus kind"), clean except untracked `uv.lock`] |
| galago-tools fork | `feat/stack-tool` @ `c2fd2d1` (HEAD), editable install — service runs HEAD after restart | The adapter + manager | [VERIFIED: git log; `.venv` editable install confirmed by v1 freeze `-e file:///home/formulatrix/data/nikko/galago-tools`] |
| galago-core | HEAD `a799627`, vendor gitlink `bcbbf8e` (04-01 commit; `stack.proto` byte-unchanged since) | Rebuild source for `galago-web`; DEP-02 codegen | [VERIFIED: git log + `git diff --quiet bcbbf8e HEAD -- interfaces/.../stack.proto` clean + gate run] |
| DEP-02 gate | `docs/runbooks/gal-02-dep02-check.sh` exit 0, last line `DEP-02 OK` | Re-run as part of the live pre-flight | [VERIFIED: ran this session — `galago-core: ../galago-core`, `galago-core HEAD: a799627`, `DEP-02 OK`, exit 0] |
| uv | 0.11.2 at `~/.local/bin/uv` | The service `.venv` is **uv-managed** — "uv only, never pip" (v1 rule) | [VERIFIED: `uv --version`; 03-DEPLOY.md:256; note `bin/make deps` uses `python -m pip` — do not use it for the service `.venv`] |
| galago-web | Docker container `galago-web`, `0.0.0.0:3010->3010` | Production front end; rebuilt from galago-core HEAD | [VERIFIED: `docker ps`] |
| galago-tools service | systemd **user** unit `galago-tools.service` (manager `:8081`, toolbox `:11010`), `KillSignal=SIGINT`, `ExecStartPre` waits on `http://10.150.1.138:3010/api/health` | Runs the manager + all tool servers | [VERIFIED: read `~/.config/systemd/user/galago-tools.service`] |
| ToolDriver GetStatus script | `scripts/fast_status.py` — generic (`--port`), read-only | Tool-health probe for the STACK tool server too (e.g. `--port 40012`) | [VERIFIED: script calls `tool_driver_pb2_grpc.ToolDriverStub.GetStatus` with `--host/--port/--timeout` args; no fast-specific payload] |
| node | v24.14.1 (nvm) | Protocol/runbook tests (`gal02_*` modules need node) | [VERIFIED: `node --version`] |

### STACK tool-server launch facts (verified in code)

- The manager starts any tool via `get_shell_command(tool_type, port)` =
  `[sys.executable, '-m', f'tools.{tool_type}.server', f'--port={port}']`
  [VERIFIED: tools/utils.py:30-31] — `tools/stack` is auto-discovered by `find_tool_packages()`,
  so a workcell entry of type `stack` on port 40012 launches the STACK tool server with no extra
  wiring.
- `relaunch_all_tools()` stops running tools, reloads the workcell config **from the galago API**
  (`Db` reads `http://localhost:3010/api`), and starts every tool in it [VERIFIED:
  tools/web_server.py:330-370; tools/toolbox/db.py:15-17 `_api_url = "http://localhost:3010/api"`].
  So a `systemctl --user restart galago-tools` will start the Stack tool server (:40012) because
  the production workcell already contains it.
- `start_tool` writes `trace_logs/<ts>/{tool_name}.log` and **opens the log with `"w"` (truncate) on
  every start** [VERIFIED: tools/web_server.py:416-421] — the tool log name for the live tool will
  be `Stack.log` (tool name "Stack"), and any restart (service or manager-page) destroys prior
  content. This is the D-06 backup trigger, re-confirmed in code.
- Adapter constants for the runbook: `DEFAULT_PORT = 5005` (`server.py:93`),
  `DEFAULT_TRANSFER_TIMEOUT_S = 300.0` (`:98`), `MAX_TRANSFER_TIMEOUT_S = 3600.0` (`:99`);
  ledger `REPLAY_WINDOW_S = 600.0` (`ledger.py:55`), retention `RETENTION_DONE_S = 604800.0` =
  7 days (`:57`). [VERIFIED: quoted verbatim from the files this session]
- `fast_status.py` is tool-generic, so the plan does **not** need a `stack_status.py` (though a
  thin alias is allowed under discretion).

## Package Legitimacy Audit

No external registry packages are introduced by this phase. The single runtime dependency is the
private GitLab package `stack-automation-layer`, already pinned by full commit SHA in-repo since
Phase 4 [VERIFIED: requirements.txt:2] — the legitimacy gate (registry checks, postinstall-script
scan) does not apply to a private git dependency pinned by SHA, and no `npm view` / `pip index`
equivalent exists for it. **Disposition: no new packages; nothing to audit.**

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| stack-automation-layer | private GitLab (git+https) | in-use since Phase 4 | n/a | gitlab.formulatrix.com/nikkopg/stack-automation-layer @ `934a621` | OK (pinned private dep, proven through Phase 6 gate + 267-test gate runs) | Approved (no new install source) |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram (live topology after deploy)

```
 Operator (user present; typed GO before each event)
   │  tool page / queue UI
   ▼
 galago-web (:3010, docker) ── workcell tool store: Stack (id 11, :40012) + FAST (MISSING today — D-12)
   │ gRPC ExecuteCommand
   ▼
 galago-tools systemd user service (forb01)  ── manager page :8081 (can restart ONE tool server)
   ├── tools.pf400.server  :40000  (baseline, untouched)
   ├── tools.toolbox.server:11010  (baseline)
   ├── tools.fast.server   :40001  (driver → F.A.S.T. 10.150.1.170:5003)   ← LIVE-10 leg 2
   └── tools.stack.server  :40012  (owner="galago" lock)                    ← LIVE-09/10 legs 1+3
         │  open_service("10.150.1.125", 5005, owner="galago")
         ▼
   STACK manager 10.150.1.125:5005 (host stack-server, build 0.12.0-beta.1+1157)
         └── robot stack2-6 (nests nest-1, orange-nest, rack / deck1)      ← the only motion in v2

 Host state on forb01 (survives restarts — never delete):
   /tmp/stack-automation-layer-locks/stack-10.150.1.125_5005-<sha12>.lock   (single-owner lock)
   ~/.local/state/stack-automation-layer/stack-10.150.1.125_5005-<sha12>.state.json (latch/ownership/in-flight)
   ~/.local/state/galago-tools/stack/stack-ledger.json (+ .lock)            (step-key ledger; default ledger_dir "")
   trace_logs/<ts>/{Stack,F.A.S.T.}.log  ← truncated on every (re)start → D-06 backup
```

Trace the primary use case: operator clicks GO → queue runs the stored STACK step → tool server
holds the galago lock → core plan→execute→wait → manager moves `stack2-6` → `ran` → SUCCESS +
ledger record; a re-dispatch of the same step key replays from the ledger without a second POST.

### Pattern 1: Executable pre-flight gate (D-05/D-08) — fail-closed, read-only

**What:** A new sibling of `docs/runbooks/gal-02-dep02-check.sh` (that script's shape: `set -u`,
run every check, exit 0 with a final `OK` line / exit 1 with `BLOCKED:` lines) that verifies the
**live** preconditions and refuses the session otherwise. Assert (inverted host rule vs Phase 6):
the configured STACK host **is** `10.150.1.125` port `5005`; the manager identity answers
`productName "Stack manager"`; the owner lock for `10.150.1.125:5005` is **not held**; the
service `.venv` has the pinned core (direct_url assert); the galago-web bundle has the stack
types; the tool store holds Stack **and** FAST (D-12); no run in flight.

**Lock probe (D-05 detection signal)** — reuse the core's own resolution so the probe cannot drift
from what the tool server will do:

```python
# Source: stack-automation-layer/stack_automation_layer/owner_lock.py (verified at 934a621)
import fcntl, json, os, sys
from stack_automation_layer.owner_lock import endpoint_key, lock_path, default_lock_dir

host, port = "10.150.1.125", 5005
path = lock_path(endpoint_key(host, port), default_lock_dir())  # honors STACK_MCP_LOCK_DIR
try:
    fd = os.open(path, os.O_RDWR)          # no O_CREAT: absent file == nobody holds it
except FileNotFoundError:
    print("PREFLIGHT OK: no lock file") ; sys.exit(0)
fd2 = os.open(path, os.O_RDONLY)
try:
    fcntl.flock(fd2, fcntl.LOCK_EX | fcntl.LOCK_NB)   # probe; holder unaffected
    fcntl.flock(fd2, fcntl.LOCK_UN)
    print("PREFLIGHT OK: lock free")
except BlockingIOError:
    raw = os.read(fd2, 256)                # the 256-byte holder record
    print(f"BLOCKED: STACK manager {host}:{port} is already owned by "
          f"{raw.decode(errors='replace').strip()}; only one front end may hold it "
          f"(stop the other owner first)")
    sys.exit(1)
finally:
    os.close(fd2); os.close(fd)
```

The refusal wording mirrors `StackOwnedError` verbatim — [VERIFIED:
owner_lock.py:79-86: `f"STACK manager {host}:{port} is already owned by {holder}; only one front "
"end may hold it at a time (stop the other owner first)"`] — satisfying D-05's "reuse the Configure
lock-holder failure message as the detection signal". Note `default_lock_dir()` is
`$STACK_MCP_LOCK_DIR` else `<tempdir>/stack-automation-layer-locks` [VERIFIED: owner_lock.py:36-47];
the service sets no override, so on forb01 the path is `/tmp/stack-automation-layer-locks/…`
(tempfile.gettempdir() = /tmp for the service user).

**When to use:** run before the deploy GO gate and again before each live event.

### Pattern 2: Safe-order deploy (D-03/D-04) — v1 LIVE-04 procedure with STACK deltas

**What:** Reuse `03-DEPLOY.md`'s shape — pre-deploy record (rollback anchors), Step 1 core install,
Step 2 restart, Step 2b operator reconnect, Step 3 `galago-web` rebuild — with four strictly
increasing UTC timestamps proving the order. STACK deltas (all verified this session):

1. **Step 1 install** (checkpoint first — see OQ-1):
   `~/.local/bin/uv pip install --python .venv/bin/python -r tools/stack/requirements.txt`
   (uv, never pip — the `.venv` is uv-managed). **Check**, mirroring v1's discriminating assert:
   ```bash
   .venv/bin/python -c "import importlib.metadata as m, json; d = json.loads(m.distribution('stack_automation_layer').read_text('direct_url.json')); assert d['vcs_info']['commit_id'] == '934a621ece116a8b263897c1e9b62b57374f4ef3'"
   .venv/bin/python -m unittest tools.tests.stack_test -v   # pin test included
   ```
   Pre-check with `uv pip install --dry-run …` (v1 D-04 pattern) so only `stack-automation-layer`
   changes. Today this install **cannot succeed from the git+https pin** (OQ-1) — the checkpoint
   resolves it (user adds credentials, or explicitly approves a `file://` local-clone install).
2. **Credential env before restart** (new vs v1): operator creates a 0600 env file, e.g.
   `~/.config/galago-tools/stack.env` with `STACK_USER`/`STACK_PASSWORD` (+ `STACK_MCP_LOCK_DIR` /
   `STACK_STATE_DIR` only if the user decides parity needs explicit values — see OQ-2), wires it
   with `systemctl --user edit galago-tools` (`EnvironmentFile=%h/.config/galago-tools/stack.env`)
   + `systemctl --user daemon-reload`. Credentials never appear in the runbook, commands, or
   findings (verify with presence-only checks like `grep -c '^STACK_USER='`, the Phase 6 D-09
   pattern).
3. **Log backup before restart** (D-06): timestamped copy of the current trace folder
   (`~/.local/share/galago/trace_logs/<newest>/` — `F.A.S.T.log`, `Pf400.log`, `Tool Box.log`,
   `web_server.log`), the journal since the last restart, and — once it exists — `Stack.log`.
4. **Step 2 restart** `systemctl --user restart galago-tools`; expect the manager to relaunch workcell
   tools **including Stack on :40012** (workcell config comes from the galago API). Check
   `is-active`, new `MainPID`, journal "Started …", no traceback, `scripts/fast_status.py --port 40012`
   → `NOT_CONFIGURED`. Record the **tool-server listener PIDs** via `ss -ltnp` — the no-restart
   baseline for the rest of the session (MainPID cannot detect a manager-page tool restart).
5. **Step 2b operator reconnect**: operator Configures `Stack` (real mode; the stored config host
   `10.150.1.125` port `5005` is already correct — verified in the store) and FAST. Expect one
   `_RESTART_WARNING` log line on the STACK open; `READY`. **Check**: `GetRobotStates` lists
   `stack2-6` idle; `GetManagerState` automated, recovery null.
6. **Step 3 rebuild** `galago-web` from galago-core `a799627`: `docker tag` the current image as the
   rollback anchor, then `TOOLBOX_PORT=11010 docker compose up -d --build` from
   `/home/formulatrix/data/nikko/galago-core`. **Checks** (v1 pattern): new image ID; `/api/health`
   200; `docker exec galago-web grep -rl Command_Transfer /app/gen-interfaces` finds the stack
   types; container reaches `host.docker.internal:40012`. Watch the v1 lesson: a cache-hit rebuild
   produces a byte-identical image ID and BLOCKED the gate — if `controller/` changed since the last
   build (it has: DEP-02 codegen + later commits) a normal `--build` suffices, but record the image
   ID either way and stop for a user decision if it comes out identical.

### Pattern 3: State/lock dir parity & "never delete" rules (LIVE-08)

**What:** The runbook documents (and the pre-flight where scriptable) the shared-state rules, all
read from core source this session:

- Lock dir: `$STACK_MCP_LOCK_DIR` else `<tempdir>/stack-automation-layer-locks` [VERIFIED:
  owner_lock.py:36-47]. State dir: `$STACK_STATE_DIR` else `$XDG_STATE_HOME/stack-automation-layer`
  (absolute only) else `~/.local/state/stack-automation-layer` [VERIFIED: state_store.py:52-64];
  state file = `lock_path(key, dir).with_suffix(".state.json")` [VERIFIED: state_store.py:108].
  State is keyed per **endpoint** (host:port), so `10.150.1.125` and `stack-server` are **different
  keys** — the runbook pins the canonical string `10.150.1.125:5005` for both front ends.
- Ledger dir: explicit absolute `ledger_dir` else `$XDG_STATE_HOME/galago-tools/stack` else
  `~/.local/state/galago-tools/stack` [VERIFIED: tools/stack/ledger.py:91-106]. The live tool's
  stored `ledger_dir` is `""` → default path; the dir does not exist yet (clean baseline; only
  `stack-sim` from Phase 6 exists — leave it alone).
- Never delete the state file (missing reads as a clean start — silently clears a latch) and never
  delete a ledger file (Phase 5 rule). A failed/ambiguous outcome drills per D-11, never by
  deleting state.

### Pattern 4: Per-event GO gates + findings log (D-10, D-11)

**What:** v1's `03-DEPLOY.md` format — each live event waits for a literal typed `go` recorded with
a UTC timestamp; findings rows (G0/…, Phase 6 format: Row / UTC timestamp / Requirement /
Observation / Result PASS|FAIL) carry the evidence; a FAIL stops the session (D-14: stop → fix →
gate → redeploy → rerun, never silent pass). D-11 drill section: stop → read
`~/.local/state/galago-tools/stack/stack-ledger.json` + `GetFailureLatch` (zero-I/O `latch_status()`
read) → operator inspects the arm → clear via the **stack-manager UI** at `http://10.150.1.125:5005`
(D-02 primary route) with the recorded guid + `"yes"` arm-inspected decision; the in-Galago
`AcknowledgeFailure` tool-page command is the fallback. A restart during a transfer is reported as
"inspect the arm" (`server.py:245-251` — verbatim: `"tool restarted mid-transfer; inspect the arm; "
"the core may not have latched "`), never replayed as SUCCESS.

### Pattern 5: Reads-first live parameter selection

**What:** Do not hardcode hardware transfer params in the runbook. After Configure, the operator
runs the reads from the STACK tool page — `ListDevices`, `ListLabwareProfiles`,
`GetLabwarePresence(robot=stack2-6)` — and picks the actual device/deck/nest triples and a
labware profile that reports presence (known hardware nests: `nest-1/deck1/A1`, `orange-nest/deck1/A1`,
`rack/l1/A1` [VERIFIED: PROJECT.md:167-168]). Expect the estimate to run ~1.7x conservative on
hardware and the actual transfer 30–32 s [VERIFIED: PROJECT.md:169, and SUMMARY §gaps citing SAL
runbook B3/B7]. LIVE-10 reuses the Phase 6 protocol JSON with live values: `stack_tool=Stack`
(case-insensitive match, but the store entry is `Stack`), a real FAST tool name, `numberOfRuns=1`,
keys read from the run's stored rows.

### Recommended Project Structure

```
docs/runbooks/
├── gal-07-live-handoff.md            # NEW live runbook (D-07): safety rules, parts, GO gates, recovery drill, findings log
├── gal-07-live-check.sh              # NEW executable pre-flight (D-08): host==10.150.1.125:5005, lock free, DEP-02 build, core reachable, store ready
└── gal-02-handoff.md                 # UNCHANGED (D-07: stays pristine; its 10.150.1.125 refusal remains in force)
tools/tests/
└── gal07_live_runbook_test.py        # NEW: gate script against fixture trees (bad host refuses; held lock refuses; missing core refuses) + runbook-text pins — mirror gal02_runbook_test.py
```

### Anti-Patterns to Avoid

- **Working around a failed check** (Phase 6 rule, restated): a `BLOCKED:` pre-flight line stops the
  session; never hand-edit configs or drive the queue another way to pass.
- **Deleting state/ledger files to "reset"**: the state file missing reads as a clean start and
  silently clears a latch; a ledger file deletion defeats F5.
- **Restarting a tool server to clear a failure**: a restart during a transfer can lose that task's
  ownership (core limits 1–2 at `934a621`); recovery is acknowledge-after-inspection, not restart.
- **Reusing a step key across runs live**: keys are minted per run by the protocol script; a manual
  tool-page re-send must copy the key **byte-for-byte** from the stored row (Phase 6 2b-3 lesson)
  and only inside the 600 s replay window.
- **`pip` into the service `.venv` / `bin/make deps` for the deploy**: that venv is uv-managed
  (v1 rule); `bin/make deps` shells out to `python -m pip` [VERIFIED: bin/make:30-35].

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| "Is the owner lock held?" | Custom PID scanning, ps greps, or re-implemented lock naming | The pinned core's `endpoint_key` + `lock_path` + `default_lock_dir` + a non-blocking `flock` probe (Pattern 1) | The lock filename embeds a sha256 digest and env resolution; any hand-rolled name can drift from what `open_service` actually locks |
| "Is the STACK tool server healthy?" | A new gRPC client script | `scripts/fast_status.py --port 40012` (generic ToolDriver GetStatus) | Already read-only, already trusted by v1 restart checks, works for any tool type [VERIFIED: source] |
| "Does galago-core have the stack types?" | Grepping node_modules / the DB | `bash docs/runbooks/gal-02-dep02-check.sh` + `docker exec galago-web grep -rl Command_Transfer /app/gen-interfaces` | The gate script is proven (fixture-tested) and the container check is the v1 pattern for "what the operator's browser actually runs" |
| Port-in-use / listener checks | Python port probes | `ss -ltnp` | v1 precedent; also yields the listener PID the runbook must baseline |
| Credential presence checks | Printing/matching credential values | `grep -c '^STACK_USER=' file` (presence-only) | Phase 6 D-09 pattern; secrets never enter runbook/logs/shell history |

**Key insight:** every check this phase needs already exists as a proven, tested artifact — the
phase composes them into a live pre-flight; it does not invent new detection mechanisms.

## Runtime State Inventory

Included deliberately: this phase's core risk is runtime state on the live host, and every category
below was probed this session on forb01.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Ledger: `~/.local/state/galago-tools/stack-sim/stack-ledger.json` (Phase 6 PACSIM sim — 2 done records); live default ledger dir `~/.local/state/galago-tools/stack` **does not exist yet**. Core state: `~/.local/state/stack-automation-layer` **does not exist yet** (clean — no prior latch on forb01). Tool store: production workcell has **only** `Stack` (id 11, host `10.150.1.125`, port `"5005"`, `ledger_dir ""`); no FAST tool | Runbook baseline step lists both dirs (read-only, never delete); D-12 pre-store check must fail today (FAST missing) — operator (re-)creates the FAST tool before LIVE-10 |
| Live service config | `galago-tools.service` (user unit): no `EnvironmentFile`, no STACK_* env; `systemctl --user show-environment` has no STACK_* keys; manager relaunches workcell tools on service restart; `:5005` on forb01 is an **unrelated local container** (never use it as the STACK host — the live host is `10.150.1.125`) | Operator adds the 0600 env file + `systemctl --user edit` before the restart (Pattern 2 step 2); runbook pins host `10.150.1.125` |
| OS-registered state | systemd user unit `galago-tools.service` (no rename involved); Docker container `galago-web` (image from 2026-10-15, pre-DEP-02) | Deploy rebuilds galago-web; no unit changes beyond the EnvironmentFile |
| Secrets/env vars | `STACK_USER`/`STACK_PASSWORD` must exist in the **tool-server process env** (core reads them only there); none are set anywhere on forb01 today; `~/.git-credentials` has no gitlab.formulatrix.com entry (count 0) | Operator-provisioned env file (never typed into runbook/history); GitLab credential fix is the user's action (OQ-1) |
| Build artifacts | Service `.venv`: `fast_mcp` @ `b30b38d` (v1 pin — untouched this phase), **no `stack_automation_layer`**; gate venv `~/data/nikko/.venvs/galago-py310` has the core installed **from the local clone** (`file:///home/formulatrix/data/nikko/stack-automation-layer` @ `934a621`) | Step 1 installs the core into the service `.venv` (after OQ-1 checkpoint); verify via `direct_url.json` commit assert |

## Common Pitfalls

### Pitfall 1: The git+https core install fails on forb01 (auth)
**What goes wrong:** Step 1 `uv pip install -r tools/stack/requirements.txt` shells out to git
against `gitlab.formulatrix.com` over https; current credentials fail ("HTTP Basic: Access denied
… 2FA") and no gitlab credential is stored.
**Why it happens:** every install so far used the local clone; the https pin was never exercised.
**How to avoid:** make the pre-flight/Step-1a a **dry-run install check**; stop at a
`checkpoint:human-verify` for the user to authenticate (interactive oauth) or explicitly approve the
local-clone fallback (which D-04 rejects by default).
**Warning signs:** `fatal: Authentication failed for 'https://gitlab.formulatrix.com/…'` during
dry-run.

### Pitfall 2: Configure fails after deploy — credentials missing in the service env
**What goes wrong:** the restarted Stack tool server comes up, but real-mode Configure fails
because `STACK_USER`/`STACK_PASSWORD` are absent from the systemd user environment.
**Why it happens:** the unit has no EnvironmentFile and nothing else on the host exports those
names; the core reads credentials only from the process environment.
**How to avoid:** the credential env-file step happens **before** the service restart (Pattern 2
step 2); the runbook's post-restart check includes a successful real-mode Configure.
**Warning signs:** auth/identity-probe failure in `Stack.log` at Configure time.

### Pitfall 3: Docker cache-hit "rebuild" produces an identical image ID
**What goes wrong:** Step 3's must-have "running image differs from the rollback anchor" is not met
because every layer cached; v1 hit exactly this and had to stop for a user decision.
**Why it happens:** `docker compose up -d --build` reuses cached layers when `controller/` is
unchanged since the last build.
**How to avoid:** record the pre-deploy image ID + creation date; if the rebuilt ID is identical,
STOP and put the no-cache decision to the user (v1 precedent). DEP-02 changed `gen-interfaces`, so
a real change is expected this time.
**Warning signs:** `writing image sha256:…` equal to the rollback anchor.

### Pitfall 4: A manager-page tool-server restart silently invalidates log evidence
**What goes wrong:** the `:8081` page (or `relaunch_all`) restarts one tool server; `MainPID` is
unchanged, the tool's log file is truncated in place, and "no restart" claims become unverifiable.
**Why it happens:** `start_tool` opens `{tool_name}.log` with `"w"`; the manager can start/stop
tools independently of systemd.
**How to avoid:** back up logs before **every** restart (D-06); baseline and re-check the
tool-server listener PIDs from `ss -ltnp` (not just `MainPID`) — v1's confirmed finding, now also
read in code (`web_server.py:400-460`).
**Warning signs:** `Stack.log`'s "Starting Stack (stack) on port 40012" first line newer than the
last recorded baseline.

### Pitfall 5: The tool store loses/omits a tool the protocol needs (the Phase 6 watch item)
**What goes wrong:** GAL-02's out-leg (or the F.A.S.T. leg) fails with `Tool … not found in store.
Must be configured first.` after the other tool was reconfigured.
**Why it happens:** observed live in Phase 6 (STACK-PACSIM vanished from the store after STACK-SIM
was reconfigured); the production store today holds only the Stack tool — no FAST tool at all.
**How to avoid:** D-12 pre-store check before every run: `GET /api/tools` lists **both** a
type-`stack` and a type-`fast` tool, configured in the up-front-decided order (planner's call);
re-verify from the tool page that both answer `READY`/`SIMULATED` before queuing.
**Warning signs:** any `not found in store` error; `GET /api/tools` returning a single tool.

### Pitfall 6: Wrong host string silently splits lock/state keys
**What goes wrong:** configuring the STACK tool with `stack-server` instead of `10.150.1.125` (or
vice versa) creates a **different** endpoint key → different lock and state files → the single-owner
guarantee and latch hand-over silently stop applying.
**Why it happens:** the core keys state per host-string + port; hostnames and IPs are different keys
by design.
**How to avoid:** the pre-flight asserts the Config host is exactly `10.150.1.125` (inverted Phase 6
rule); the runbook states the canonical string once and uses it everywhere.
**Warning signs:** two lock files in the lock dir; `endpoint` fields differing in holder records.

### Pitfall 7: Replay-window expiry makes a legitimate manual re-send look like a defect
**What goes wrong:** an operator re-sends the in-leg params from the tool page > 600 s after the
step completed and gets `ERROR_FROM_TOOL "step key already completed … nothing was sent"`.
**Why it happens:** `REPLAY_WINDOW_S = 600.0` — a recorded `ran` replays only inside the window
(ledger.py:54-55, verified); past it the refusal is by design (F5 defence).
**How to avoid:** the runbook times any forced re-dispatch check within 600 s of the in leg (Phase 6
2b-3 precedent) and labels the late-re-send refusal as expected behaviour, not a failure.

### Pitfall 8: Treating `TimedOut`/restart-during-transfer as "failed, re-run"
**What goes wrong:** an operator "fixes" a `TimedOut` or mid-transfer restart by re-running the step
from scratch or restarting the tool server.
**Why it happens:** the arm is still moving / ownership may be lost; a fresh run would queue a
second transfer (the core's in-flight guard covers only in-flight tasks — a second valid submit is
**accepted and queued**, PROJECT.md:169-170).
**How to avoid:** D-11 drill wording: stop → ledger + `GetFailureLatch` → arm inspection → manager-UI
clear; re-running the **same** step (same key) is the only re-run path, and it re-attaches rather
than re-submits.

## Code Examples

### Step-1 install + discriminating check (service `.venv`)

```bash
# Source: v1 03-DEPLOY.md Step 1 pattern; pin from tools/stack/requirements.txt:2
cd /home/formulatrix/data/nikko/galago-tools
~/.local/bin/uv pip install --dry-run --python .venv/bin/python -r tools/stack/requirements.txt  # preview: only stack-automation-layer changes
~/.local/bin/uv pip install --python .venv/bin/python -r tools/stack/requirements.txt
.venv/bin/python -c "import importlib.metadata as m, json; d = json.loads(m.distribution('stack_automation_layer').read_text('direct_url.json')); assert d['vcs_info']['commit_id'] == '934a621ece116a8b263897c1e9b62b57374f4ef3'"
.venv/bin/python -m unittest tools.tests.stack_test -v
```

### Pre-restart baseline + backup (D-06)

```bash
# Source: v1 03-DEPLOY.md ("Logs to watch", no-restart baseline rows)
TS=$(date -u +%Y%m%dT%H%M%SZ); BK=~/.local/share/galago/log-backups/pre-gal07-$TS
mkdir -p "$BK"
cp -a ~/.local/share/galago/trace_logs/$(ls -t ~/.local/share/galago/trace_logs/ | head -1) "$BK"/
journalctl --user -u galago-tools --since "@$(($(date +%s) - 86400))" --no-pager > "$BK/journal.log"
systemctl --user show galago-tools -p MainPID -p ActiveEnterTimestamp | tee "$BK/service.txt"
ss -ltnp | grep -E ':(40000|40001|40012|11010|8081)\b' | tee "$BK/listeners.txt"
```

### Post-deploy STACK health + hardware identity (read-only)

```bash
.venv/bin/python scripts/fast_status.py --port 40012        # → NOT_CONFIGURED after restart, READY after Configure
curl -fsS -m 5 http://10.150.1.125:5005/api/general/application
# → {"productVersion":"0.12.0-beta.1+1157","productName":"Stack manager",…,"computerInfo":"stack-server"}  [VERIFIED this session]
```

### Pre-store check (D-12)

```bash
# Source: production API probe this session; Phase 6 findings 2a-1/2b-0 (snake_case config keys)
curl -sf http://localhost:3010/api/tools | jq -e '[.[] | .type] | contains(["stack"]) and contains(["fast"])'
# today → false (only "Stack" exists) ⇒ BLOCKED until the operator adds/Configures the FAST tool
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Restart clears the core latch/ownership (v1 G1 gap) | State persisted per manager endpoint; survives restart + front-end hand-over (two narrow limits remain) | DEP-01 `934a621` (2026-10-29) | Recovery drill is acknowledge-after-inspection, never "restart to reset"; D-09 restart clause corrected in `fe8aee8` |
| Operator-guid discovery via `plan_transfer(TransferRequest())` workaround | `GetFailureLatch` binds 1:1 to zero-I/O `latch_status()` | DEP-01 | The guid to acknowledge is always readable from the tool page |
| fast-mcp-style local-clone installs (`file://`) | D-04 demands the git+https pin install — **currently blocked by auth on forb01** | this phase | Checkpoint required before Step 1 (OQ-1) |
| Dev-compose galago-core (Phase 6, :3020) | Production galago-web (:3010) is the live target | this phase | D-16e's "never production" rule was Phase-6-scoped; Phase 7 is the production deploy — the runbook must say so explicitly and re-baseline prod |

**Deprecated/outdated:**
- `plan_transfer(TransferRequest())` latch probe — superseded by `GetFailureLatch` (G2 resolved).
- "Restart clears the latch" runbook language — replaced by the two remaining limits (crash between
  POST-acceptance and state save; foreign finished task).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The GitLab https auth failure is resolvable by the user (interactive oauth login / new token) and is preferred over a local-clone install | Pitfall 1 / OQ-1 | Deploy Step 1 blocked; if the user prefers local-clone, D-04 needs their explicit waiver — plan must carry the checkpoint either way |
| A2 | stack-mcp does not run on forb01 (no launcher config, no install, no env trace found) and is closed during live runs; the lock probe is the enforcement (D-05) | Deploy Facts #5 / OQ-2 | If stack-mcp runs on forb01 under a different user, its lock dir differs and the probe on the service's default dir would miss it — the pre-flight would pass while a second owner exists; mitigate by also checking `ss`/process list for stack-mcp and asking the user to confirm |
| A3 | The production workcell's stored Stack config (host `10.150.1.125`, port `"5005"`, snake_case keys, empty ledger_dir) is correct as-is and the operator's Configure needs no edits | Deploy Facts #3 | Configure would target the wrong endpoint; the pre-flight's host assertion + post-Configure `Received configuration` log check catch it |
| A4 | The manager will start the Stack tool server on :40012 automatically at service restart (because the tool is in the workcell config fetched from the galago API) | Architecture Patterns P2 | If it does not, the operator starts it from the manager page (:8081 `start_tool` action) — the runbook should include that fallback step |
| A5 | `fast_status.py` GetStatus works identically against a stack tool server (same ToolDriver service, no fast-specific fields) | Standard Stack | If wrong, only the health check breaks — Configure/read results from the tool page remain authoritative; a thin `stack_status.py` alias is a trivial fallback |
| A6 | The F.A.S.T. tool can be (re-)added to the production workcell with the v1 config (host `10.150.1.170`, port 5003, `expected_tray_id` 90) by the operator at LIVE-10 prep | Deploy Facts #3 / LIVE-10 | LIVE-10 blocked until the store holds both tools — which is exactly what D-12 asserts, so the failure mode is a clean BLOCKED, not a hazard |

## Open Questions (RESOLVED)

All three questions raised during research are dispositioned below; none remains open.

1. **How will the pinned git+https install authenticate on forb01? (OQ-1 — blocks Step 1) — (RESOLVED)**
   - What we know: pin URL + auth failure + zero stored gitlab credentials + all prior installs were
     local-clone (all [VERIFIED] this session). D-04 says "not a local-clone install".
   - What's unclear: whether the user will add working GitLab credentials or explicitly waive D-04.
   - **Disposition (RESOLVED):** carried as plan 07-02 Task 1 — a blocking user checkpoint before
     deploy Step 1, with a read-only dry-run install probe first: the user either adds working
     GitLab credentials (honoring D-04 exactly) or explicitly waives D-04 for a verified
     local-clone install; the choice is recorded verbatim in findings row 1a-1 with a UTC
     timestamp, and nothing is installed until the separate typed-go gate in 07-02 Task 2.
2. **Where does stack-mcp run, and do lock/state dirs need explicit `STACK_MCP_LOCK_DIR` /
   `STACK_STATE_DIR` values for LIVE-08's parity clause? (OQ-2) — (RESOLVED)**
   - What we know: defaults on forb01 (service user) are `/tmp/stack-automation-layer-locks` and
     `~/.local/state/stack-automation-layer`; no stack-mcp installation/config found on forb01.
   - What's unclear: the user's stack-mcp setup (host, user, env) — only the user knows.
   - **Disposition (RESOLVED):** the lock-probe pre-flight (D-05, plan 07-01) is the hard gate
     either way — the session refuses if any holder owns the `10.150.1.125:5005` lock; the runbook
     documents both front ends' resolved default dirs and asks the user to confirm stack-mcp is
     closed as a pre-flight checklist item. No explicit `STACK_MCP_LOCK_DIR`/`STACK_STATE_DIR`
     values are introduced.
3. **Configuration order for the D-12 pre-store check (OQ-3, planner discretion) — (RESOLVED)**
   - What we know: planner discretion per CONTEXT.md; the recommendation was FAST first, then
     STACK.
   - **Disposition (RESOLVED):** planner decision — FAST is created and Configured first, then the
     STACK real-mode Configure LAST so the final store action before any run is the STACK
     Configure; pinned in 07-01 Task 3 (runbook Part 1 Step 2b) and executed by 07-02 Task 3.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| forb01 host access (this machine) | everything | ✓ | hostname `forb01` | — |
| uv | Step-1 core install | ✓ | 0.11.2 | — |
| systemd user service `galago-tools` | service restart | ✓ | active, MainPID 1940146 | — |
| docker + galago-core compose | `galago-web` rebuild | ✓ | container `galago-web` on :3010 | — |
| galago-core checkout at HEAD `a799627` | rebuild source; DEP-02 gate | ✓ | vendor gitlink `bcbbf8e`, gate `DEP-02 OK` | — |
| gate venv (Python 3.10) `~/data/nikko/.venvs/galago-py310` | tests, pre-flight python | ✓ | 3.10.12 (v1 gate) | — |
| node (nvm) v24.14.1 | gal02 protocol/runbook tests | ✓ | v24.14.1 | — |
| STACK manager `10.150.1.125:5005` | identity + live runs | ✓ | build `0.12.0-beta.1+1157`, host `stack-server` (read-only GET; no motion) | — |
| GitLab https auth for the core pin install | Step-1 install | ✗ | — | user adds credentials, or user-approved local-clone install (checkpoint) |
| `STACK_USER`/`STACK_PASSWORD` in service env | real-mode Configure | ✗ | — | operator env-file step (Pattern 2 step 2) — planned, not yet done |
| FAST tool instance in production store | LIVE-10 | ✗ | — | operator adds/configures it (D-12 gate makes the gap explicit) |

**Missing dependencies with no fallback:** none — every ✗ above has a user/operator action that
unblocks it; the pre-flight turns each into a clean `BLOCKED:` instead of a mid-session surprise.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + unittest on the 3.10 gate venv (v1 gate); node v24.14.1 for protocol tests |
| Config file | none new — reuse `bin/make proto test` gate |
| Quick run command | `GAL02_REQUIRE_ALL=1 python -m pytest tools/tests/gal02_handoff_test.py tools/tests/gal02_replay_test.py tools/tests/gal02_runbook_test.py -q -rs -p no:cacheprovider` (plus the new `gal07` module) |
| Full suite command | `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make proto test` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LIVE-08 (order) | Four strictly-increasing UTC deploy timestamps recorded | manual-recorded (findings rows) | — (evidence in runbook findings log) | n/a |
| LIVE-08 (pre-flight) | Gate refuses bad host / held lock / missing core build / missing store entries | unit (script vs fixture trees, exit codes) | `python -m pytest tools/tests/gal07_live_runbook_test.py -q -x` | ❌ Wave 0 |
| LIVE-08 (runbook text) | Runbook contains safety rules, GO-gate, recovery-drill, never-delete clauses | unit (text pins, mirror `gal02_runbook_test.py`) | same module | ❌ Wave 0 |
| LIVE-09 | Live `Transfer` reaches `ran` on `stack2-6` | manual-only — live motion, supervised session, user's typed GO (justification: hardware motion is the requirement itself) | — | n/a |
| LIVE-10 | Live GAL-02 handoff SUCCESS on hardware | manual-only (same justification) | — | n/a |
| (support) | Adapter unchanged — existing suites stay green | regression | full gate | ✅ |

### Sampling Rate
- **Per task commit:** quick command (new gal07 module + gal02 modules)
- **Per wave merge:** full gate
- **Phase gate:** full suite green; live events' findings rows all PASS before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tools/tests/gal07_live_runbook_test.py` — gate-script fixture tests + runbook-text pins
- [ ] `docs/runbooks/gal-07-live-check.sh` + `docs/runbooks/gal-07-live-handoff.md` (the artifacts the tests pin)

## Security Domain

### Applicable ASVS Categories (level 1, `security_enforcement: true`)

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (instrument creds) | Credentials only from `STACK_USER`/`STACK_PASSWORD` env; operator-owned 0600 env file; never in runbook/logs (Phase 6 D-09 pattern) |
| V3 Session Management | no | No new sessions; the single-owner owner-lock **is** the session control |
| V4 Access Control | yes | Single-owner lock probe refuses a second front end (D-05); GO gates are operator-only authority |
| V5 Input Validation | yes | Pre-flight script validates args/paths; adapter unchanged (its argument validation is Phases 4–5 tested) |
| V6 Cryptography | no | Nothing cryptographic added (step keys are uniqueness, not secrecy — Phase 6 runbook) |
| V7 Errors & Logging | yes | Findings log never carries credentials/tokens (presence-only `grep -c` checks); logs backed up, never edited |
| V9 Communications | noted | Manager HTTP API is plain-HTTP on the lab LAN — core-owned, out of this repo's control; document, don't "fix" |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Second front end moves the arm concurrently | Tampering/Elevation | Owner-lock probe in pre-flight; stack-mcp closed (D-05); identical host string pinned |
| Credential leakage into runbook/session evidence | Information disclosure | Presence-only checks; env file 0600; operator owns the file |
| Unintended motion from a stale queue/step | Tampering (safety) | Per-run step keys + ledger; GO gates; no auto-advance (D-10); re-dispatch only within replay window |
| Secret leakage via pre-flight script args/logs | Information disclosure | Read env/config, never echo values; mirror `gal-02-dep02-check.sh`'s "read-only, prints no secrets" contract |

## Sources

### Primary (HIGH confidence)
- Read this session: `tools/stack/server.py` (constants `:93,:98-99`, restart warning `:245-251`,
  `:282-287`, Configure path `:770-935`), `tools/stack/ledger.py` (`:45-57`, `:91-106`),
  `tools/stack/requirements.txt:2`, `tools/web_server.py:330-460`, `tools/utils.py:30-31`,
  `tools/toolbox/db.py:1-50`, `scripts/fast_status.py`, `docs/runbooks/gal-02-dep02-check.sh`,
  `docs/runbooks/gal-02-handoff.md` (+ findings log), `~/.config/systemd/user/galago-tools.service`
- Local core clone `~/data/nikko/stack-automation-layer` @ `934a621`:
  `owner_lock.py:36-47,60-88,149-207`, `state_store.py:13-19,52-64,108`
- Planning docs: ROADMAP §Phase 7; REQUIREMENTS §LIVE-08..10; PROJECT.md (Context/Constraints/
  Key Decisions); STATE.md (blockers, watch item); research SUMMARY.md §Addendum; v1
  `03-DEPLOY.md` (safe-order runbook, rollback, GO gate, log/PID findings)

### Secondary (MEDIUM confidence)
- Live host probes this session (read-only): `hostname`; `.venv` package metadata;
  `systemctl --user show-environment` (key names only); `ss -ltnp`; `docker ps`;
  `GET http://localhost:3010/api/health` and `/api/tools`;
  `GET http://10.150.1.125:5005/api/general/application` (identity only — no command, no motion);
  `git ls-remote` auth failure; `git -C galago-core log/ls-tree/status`; DEP-02 gate run
  (`DEP-02 OK`)

### Tertiary (LOW confidence)
- None — no web research was used; all claims are code/file/host-verified or tagged [ASSUMED]

## Metadata

**Confidence breakdown:**
- Deploy procedure & host facts: HIGH — every fact read from the live host's files, unit, store API,
  or probed read-only this session
- Pre-flight & runbook patterns: HIGH — composed from proven, fixture-tested Phase 6 artifacts and
  the v1 deploy runbook
- Live-event behaviour (LIVE-09/10): HIGH on adapter/core semantics (Phases 5–6 code + addendum),
  inherently manual for the hardware events themselves
- Cross-front-end parity (stack-mcp side): LOW→[ASSUMED] — stack-mcp's runtime was not found on
  forb01; user confirmation needed (OQ-2)

**Research date:** 2026-11-02
**Valid until:** 2026-12-02 (stable: pinned deps, frozen contract; re-verify the store contents and
the galago-core HEAD at plan/execute time — both move)
