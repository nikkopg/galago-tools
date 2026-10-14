# Phase 3 Deploy Runbook

**Status:** Entry gate met (re-checked 2026-10-14T10:16Z, after the earlier same-day
2026-10-14T10:08:54Z check FAILed — see note below the table). Task 1 complete: the
pre-deploy record, runbook and rollback are written below. Task 2 (D-03) complete: the user
replied `go` — see "Go-ahead (D-03)" below; the F.A.S.T. tool was restored to `READY` before
the reply. Task 3 in progress: deploy steps 1-2 (D-05).

## Entry gate (D-01)

| Condition | Check | Evidence | Result |
|-----------|-------|----------|--------|
| D-01.1 | galago-core Phase 2 code-complete (every PLAN has a SUMMARY, `controller/` clean) AND every open 02-UAT item depends on the deploy | Code-complete checks pass (re-run, fresh): 6/6 `02-0N-PLAN.md` have a matching `02-0N-SUMMARY.md` under `/home/formulatrix/data/nikko/galago-core/.planning/phases/02-run-page-live-controls`; `git -C /home/formulatrix/data/nikko/galago-core status --short controller/` is empty; galago-core HEAD `d95c2e143ca13d8837bd9c248d6579777b2ebdc9` (commit `test(02): reclassify Test 2 as blocked on galago-tools deploy`). `02-UAT.md` (updated 2026-10-14T10:10:52.930Z, status `partial`): 8 tests total, 6 `pass`, 2 `blocked`, 0 `issue`, 0 `pending`. Both open items are `blocked_by: prior-phase` with reasons that explicitly defer to this phase's deploy: **test 2** ("i got Action refused Tool replied UNRECOGNIZED_COMMAND... Re-run after galago-tools Phase 3 deploy") and **test 5** ("running galago-tools servers started 2026-10-12 13:15, before the wait-through-pauses/run_state/Pause adapter work... Unblocks after galago-tools Phase 3 deploy"). Test 8 (open and NOT deploy-dependent at the 10:08:54Z check) now shows `result: pass` — it was completed independently of this deploy. No open item fails to depend on the deploy. | PASS |
| D-01.2 | `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make proto test` exits 0 on `feat/fast-tool`; regenerated `tools/grpc_interfaces/tool_base_pb2.pyi` contains `run_state` | Re-run, fresh. Exit code 0. unittest summary: `Ran 143 tests in 1.091s` / `OK`. pytest summary: `143 passed in 1.28s`. `tools/grpc_interfaces/tool_base_pb2.pyi:205,213-214` contains `run_state: _struct_pb2.Struct` and `run_state` in `__slots__`. | PASS |
| D-01.3 | galago-core's `vendor/galago-tools` gitlink has `run_state` in `tool_base.proto` and `message Pause` in `fast.proto`, both files identical to this repo's HEAD, and galago-core's `npm test` (tsc) and `npm run test:unit` (vitest) both exit 0 | Re-run, fresh. `git -C /home/formulatrix/data/nikko/galago-core ls-tree HEAD vendor/galago-tools` → commit `cb7886d1f3bdcdeeee71c55996f0dd62cf49ba7f` (unchanged submodule pin). That commit's `interfaces/tools/grpc_interfaces/tool_base.proto:135` → `optional google.protobuf.Struct run_state = 4;`. That commit's `interfaces/tools/grpc_interfaces/fast.proto:72` → `message Pause {}`. `git diff --quiet cb7886d1f3bdcdeeee71c55996f0dd62cf49ba7f -- interfaces/tools/grpc_interfaces/tool_base.proto interfaces/tools/grpc_interfaces/fast.proto` exit 0 (identical to this repo's HEAD). `npm --prefix /home/formulatrix/data/nikko/galago-core/controller test` (`tsc --noEmit`) exit 0, 0 errors. `npm --prefix /home/formulatrix/data/nikko/galago-core/controller run test:unit` (vitest) exit 0, `Test Files 11 passed (11)`, `Tests 210 passed (210)`. | PASS |
| D-01.4 | The local fast-mcp clone at `/home/formulatrix/data/nikko/fast/fast-mcp` contains commit `b30b38df48e8480f325228145ccae7915a56e437` | Re-run, fresh. `git -C /home/formulatrix/data/nikko/fast/fast-mcp cat-file -e b30b38df48e8480f325228145ccae7915a56e437^{commit}` exit 0. Clone branch `fix/run-recovery-gate`, HEAD `b4b67d86039dc9440b1456e333e5a944f2fabc17`. `git merge-base --is-ancestor b30b38df48e8480f325228145ccae7915a56e437 HEAD` → true. | PASS |

**Overall gate result: PASS** (all four conditions). Re-checked 2026-10-14T10:16Z UTC /
17:16 WIB, at the user's request after the galago-core 02-UAT run completed.

**Earlier check failed, now cleared:** at 2026-10-14T10:08:54Z (UTC) / 17:08:54 WIB, D-01.1
FAILed because `02-UAT.md` test 8 was `[pending]` and did not depend on the deploy (the
other two open items, tests 2 and 5, already depended on it). The galago-core team then
finished UAT: test 8 now reads `result: pass`, and test 2 was reclassified from `issue` to
`blocked` with a reason that also defers to this deploy (commit `d95c2e1`, 2026-10-14
17:10:52 WIB). D-01.2, D-01.3 and D-01.4 PASSed at both checks.

### Deferred galago-core 02-UAT items

Both open 02-UAT items depend on this phase's deploy and are re-tested after plan 03-02
(new adapter + rebuilt `galago-web`), before the live scenarios:

- **Test 2** (Pause/Resume/Abort confirm wiring): blocked — sending Pause against the
  currently-deployed adapter (`fast.proto` with no `message Pause`) returns
  `UNRECOGNIZED_COMMAND`; the confirmation UI, send path and refusal-toast behavior were
  otherwise verified correct. Needs the deploy's `Pause` command.
- **Test 5** (`tool_paused` prompt on an instrument pause): blocked — the running
  `galago-tools` (started 2026-10-12 13:15, before the wait-through-pauses/`run_state`/
  `Pause` adapter work landed 2026-10-13) fails a paused transfer immediately with
  `ERROR_FROM_TOOL` instead of leaving a step open and prompting. Needs the deploy's
  `run_state`/wait-through-pauses adapter; covered by 03-05's LIVE-05 evidence.

## Pre-deploy record (D-04)

Recorded 2026-10-14T10:09Z-10:16Z (UTC) / 17:09-17:16 WIB.

### Service core (pre-deploy)

`.venv/lib/python3.10/site-packages/fast_mcp-*.dist-info/direct_url.json`:
```json
{"url":"file:///home/formulatrix/data/nikko/fast/fast-mcp","vcs_info":{"vcs":"git","commit_id":"76f8c3fee41b0a2df3519aa74b022152df673824","requested_revision":"76f8c3fee41b0a2df3519aa74b022152df673824"}}
```

<details>
<summary><code>~/.local/bin/uv pip freeze --python .venv/bin/python</code> (38 lines, pre-deploy)</summary>

```
annotated-types==0.8.0
anyio==4.15.1
appdirs==1.4.4
certifi==2026.7.22
cffi==2.1.1
charset-normalizer==3.5.1
clr-loader==0.3.1
colorama==0.4.6
comtypes==1.4.10
cython==3.0.11
exceptiongroup==1.3.1
fast-mcp @ git+file:///home/formulatrix/data/nikko/fast/fast-mcp@76f8c3fee41b0a2df3519aa74b022152df673824
-e file:///home/formulatrix/data/nikko/galago-tools
grpcio==1.70.0
grpcio-reflection==1.70.0
grpcio-tools==1.70.0
h11==0.16.0
httpcore==1.0.9
httpx==0.28.1
idna==3.19
msl-loadlib==0.10.0
packaging==25.0
parse==1.22.1
pillow==11.0.0
protobuf==5.29.6
pycparser==3.0
pydantic==2.8.2
pydantic-core==2.20.1
pyhamilton==1.491.17
pyserial==3.5
python-dotenv==1.0.0
pythonnet==3.1.0
requests==2.29.0
setuptools==84.0.0
typing-extensions==4.16.0
urllib3==1.26.20
waiter==1.5.1
websockets==15.0.1
```
</summary>
</details>

### Step-1 install preview (D-04/T-03-02, dry run — nothing installed)

```
~/.local/bin/uv pip install --dry-run --python .venv/bin/python "git+file:///home/formulatrix/data/nikko/fast/fast-mcp@b30b38df48e8480f325228145ccae7915a56e437"
```
```
   Updating file:///home/formulatrix/data/nikko/fast/fast-mcp (b30b38df48e8480f325228145ccae7915a56e437)
    Updated file:///home/formulatrix/data/nikko/fast/fast-mcp (b30b38df48e8480f325228145ccae7915a56e437)
Resolved 9 packages in 1.82s
Would download 1 package
Would uninstall 1 package
Would install 1 package
 - fast-mcp==0.1.0 (from git+file:///home/formulatrix/data/nikko/fast/fast-mcp@76f8c3fee41b0a2df3519aa74b022152df673824)
 + fast-mcp @ git+file:///home/formulatrix/data/nikko/fast/fast-mcp@b30b38df48e8480f325228145ccae7915a56e437
```
Only `fast-mcp` would change (uninstall the pinned `76f8c3fe` build, install the pinned
`b30b38d` build). No other package would change — nothing flagged for extra user review
under T-03-02.

### galago-tools (pre-deploy)

- `systemctl --user show galago-tools -p MainPID -p ActiveEnterTimestamp`: `MainPID=944069`,
  `ActiveEnterTimestamp=Mon 2026-10-12 13:15:55 WIB`.
- Running adapter SHA: `git log --before="2026-10-12 13:15:55 +0700" -1` →
  `7c0ff7b953986bbc62221a14bad8b9594795b1f4` (2026-10-09T16:58:09+07:00, "test(fast): cover
  operator Abort/Resume and scope the no-auto-abort invariant") — cross-checked against the
  last recorded deploy, `7c0ff7b` (CONTEXT.md), match. Confirmed read-only: that commit's
  `interfaces/tools/grpc_interfaces/fast.proto` has no `message Pause` and
  `interfaces/tools/grpc_interfaces/tool_base.proto` has no `run_state` (supports the
  galago-web reasoning below).
- Current HEAD: `7f857a9681c85533b248ba8cc57292d977b99dfd`.
- Last code commit (`git log -1 --format=%H -- tools interfaces setup.py requirements.txt`):
  `d9acdcf0e8f203cd553aaafad2e262b387bcdc06` (2026-10-13T20:04:24+07:00, "fix(02): WR-01 fail
  closed on non-int errorCode for operator-abort and recovery replies"). Note: this commit
  postdates the running service's `ActiveEnterTimestamp` — the working tree has moved on
  since the last restart, which is expected for an editable install; Task 3's restart will
  load current HEAD's code, not `7c0ff7b`.
- `git status --porcelain -- tools interfaces setup.py requirements.txt`: empty (clean —
  confirmed, so no uncommitted code would be deployed).

### galago-core (pre-deploy)

- HEAD: `d95c2e143ca13d8837bd9c248d6579777b2ebdc9` (equals the D-01.1 value above).
- `git -C /home/formulatrix/data/nikko/galago-core status --short controller/`: empty.
- `.dockerignore` present at `/home/formulatrix/data/nikko/galago-core/.dockerignore`.

### galago-web (pre-deploy)

- `docker inspect galago-web`: image ID
  `sha256:9ad9c64fee6baa7ea9351c7cfa03bceb8f0db7f974fabbb6865b1143948880ca`, Created
  `2026-10-14T08:10:47.886061214Z`, StartedAt `2026-10-14T08:10:48.266136278Z`.
  `docker image ls galago-core-galago-web` → `galago-core-galago-web:latest` at that same ID.
- **galago-web was rebuilt outside this runbook at 2026-10-14T08:10:47Z** — after the last
  recorded deploy (2026-10-12, galago-core `ce8d40d`). Safety reasoning to show the user at
  the go-ahead: the running adapter SHA's (`7c0ff7b`) `fast.proto` has no `message Pause`
  (`git show 7c0ff7b953986bbc62221a14bad8b9594795b1f4:interfaces/tools/grpc_interfaces/fast.proto`
  confirms this), so no Pause could have reached the core through it regardless of which UI
  build ran against it, and Abort/Resume reached core `76f8c3fe` as intended (consistent with
  the 02-UAT test 3 pass and test 2's `UNRECOGNIZED_COMMAND` finding above).

### Tools idle (pre-deploy) — FINDING: F.A.S.T. is not READY

- `.venv/bin/python scripts/fast_status.py --port 40001` →
  `{"port": 40001, "status": "SIMULATED", "uptime": 187089, "error_message": "", "run_state": null}`
- `.venv/bin/python scripts/fast_status.py --port 40000` (Pf400) →
  `{"port": 40000, "status": "SIMULATED", "uptime": 187089, "error_message": "", "run_state": null}`
- Neither port is `BUSY` (no run is in flight — see below), but **neither is `READY`** as
  the acceptance criteria for this record expect. Pf400 (`:40000`) has run `simulated: true`
  continuously since 2026-10-12 17:03:18 WIB (`Pf400.log` line 4) — that is this environment's
  established baseline for Pf400 and not a new finding.
- **F.A.S.T. (`:40001`) is the new finding.** Its newest trace log
  (`~/.local/share/galago/trace_logs/1791785755/F.A.S.T.log`) shows it toggled between real
  and simulated configuration during today's galago-core 02-UAT session and was left
  `simulated: true` by the **last** "Received configuration" line:
  ```
  2026-10-14 16:37:48 | INFO | Received configuration: simulated: true
  toolId: "F.A.S.T"
  fast {
    host: "10.150.1.170"
    port: 5003
    expected_tray_id: 90
  }
  ```
  (Earlier today it was briefly reconfigured to real mode at 16:15:30/16:15:32, i.e. this is
  a deliberate toggle back to simulated, not a stuck flag.) Last 5 lines of `F.A.S.T.log`:
  ```
  2026-10-14 17:09:16 | INFO | Running command Transfer
  2026-10-14 17:09:23 | ERROR | Failed o execute commad for Tool F.A.S.T, Error=None
  2026-10-14 17:10:36 | DEBUG | ExecuteCommand Response: response: SUCCESS
  return_reply: true

  ```
- **No Galago run is in flight:** `GET http://localhost:3010/api/runs` lists 9 runs, all
  `status: CREATED`, none `RUNNING`; the last F.A.S.T. activity above (17:09:16-17:10:36 WIB)
  already completed with `SUCCESS`. The queue is idle.
- **Why this matters for Task 2/Task 3:** Task 3's precondition is "`fast_status.py` reports
  `READY` (not `BUSY`) for `--port 40001` and `--port 40000` right now." F.A.S.T. currently
  reads `SIMULATED`, which satisfies "not `BUSY`" (no run in flight) but not literal `READY`.
  This is very likely a leftover from the galago-core team's just-finished UAT session
  (`02-UAT.md` updated 10:10:52Z, minutes before this record) and not a sign of an in-progress
  run — but Claude does not send `Configure` (prohibition) and cannot resolve this itself.
  **The operator should confirm or restore F.A.S.T.'s real-mode configuration before replying
  "go" at Task 2**, since Task 3 will re-check this precondition and will refuse to proceed if
  it is not met.

### Rollback anchors

- galago-web pre-deploy image ID: `sha256:9ad9c64fee6baa7ea9351c7cfa03bceb8f0db7f974fabbb6865b1143948880ca`
- Service core pre-deploy (rollback target): `76f8c3fee41b0a2df3519aa74b022152df673824`
- Running adapter SHA (rollback target): `7c0ff7b953986bbc62221a14bad8b9594795b1f4`

## Go-ahead (D-03)

**Decision:** Deploy the live-control stack now, in the safe order of this document's
Runbook (D-05): core `b30b38d` into the service `.venv`, restart `galago-tools`, then
(plan 03-02) the operator reconnects the F.A.S.T. tool and `galago-web` is rebuilt.

**Who:** The user (operator), in this session.
**When:** 2026-10-14, after reviewing the Entry gate (D-01) results and the Pre-deploy
record (D-04) above, including the "Tools idle" finding that F.A.S.T. (`:40001`) read
`SIMULATED` rather than `READY`.
**Reply:** literal `go`.

**Note — F.A.S.T. restored before the reply:** before answering, the user restored the
F.A.S.T. tool server's configuration from `SIMULATED` back to `READY`. This was confirmed
at the user's request with a fresh re-check: `scripts/fast_status.py --port 40001` → `READY`;
`scripts/fast_status.py --port 40000` (Pf400) → `SIMULATED` (this environment's established
baseline per the Pre-deploy record above — Pf400 has run `simulated: true` continuously
since 2026-10-12 and this is not a new finding or a sign of a run in flight).

**Task 3 precondition re-check (live, immediately before Step 1):** UTC 2026-10-14T10:37:17Z —
`.venv/bin/python scripts/fast_status.py --port 40001` → `{"status": "READY", ...}`;
`--port 40000` → `{"status": "SIMULATED", ...}` (established baseline, not `BUSY`, consistent
with the finding above). `GET http://localhost:3010/api/runs` → 9 runs, all `status: "CREATED"`,
none `RUNNING` — no Galago run in flight. The precondition's intent — no tool `BUSY`, no run in
flight before the restart that will drop every tool server's connection — is met: F.A.S.T. is
literally `READY`; Pf400's `SIMULATED` is the environment's pre-existing, already-documented
baseline rather than a new or blocking condition, and is not `BUSY`. Proceeding to Task 3.

## Runbook (D-05)

Run every command from `/home/formulatrix/data/nikko/galago-tools` unless noted. No command
in this section runs until the user answers Task 2's go-ahead with `go` (D-03).

### Step 1 — core into the service `.venv` (D-02)

**Command:**
```
~/.local/bin/uv pip install --python .venv/bin/python "git+file:///home/formulatrix/data/nikko/fast/fast-mcp@b30b38df48e8480f325228145ccae7915a56e437"
```
(uv only, never pip — the service `.venv` is uv-managed.)

**Check:**
```
.venv/bin/python -c "import importlib.metadata as m, json; d = json.loads(m.distribution('fast_mcp').read_text('direct_url.json')); assert d['vcs_info']['commit_id'] == 'b30b38df48e8480f325228145ccae7915a56e437'"
.venv/bin/python -m unittest tools.tests.fast_test.TestRequirementsPin -v
```
Expected: the assert passes silently (`direct_url.json`'s `vcs_info.commit_id` equals
`b30b38df48e8480f325228145ccae7915a56e437`); `TestRequirementsPin` ends `OK` (3 tests).

**Do not continue unless** both checks pass. If either fails: do not restart anything; stop
and report; reinstalling `76f8c3fe` happens only on the user's go-ahead (D-06).

### Step 2 — restart `galago-tools` (D-05)

Run immediately after Step 1's check passes.

**Command:**
```
systemctl --user restart galago-tools
```

**Check:**
```
systemctl --user is-active galago-tools
journalctl --user -u galago-tools --since "<restart local time>" --no-pager
ls -dt ~/.local/share/galago/trace_logs/*/ | head -1
.venv/bin/python scripts/fast_status.py --port 40001
```
Expected: `is-active` prints `active`; `MainPID` differs from the pre-deploy `944069`; the
journal since the restart shows `Started F.A.S.T on port 40001` and no Python traceback; the
newest `trace_logs` folder's `F.A.S.T.log` shows `fast server started, listening on 40001`
and no traceback; `fast_status.py --port 40001` answers `status: "NOT_CONFIGURED"` (expected
right after a restart — the tool server has no configuration until the operator reconnects
it). The old `galago-web` against the new adapter is safe in this window: the proto change is
additive and the old UI never sends `Pause`.

**Do not continue unless** all of the above pass. If any check fails: STOP, leave `galago-web`
alone, report the journal and log excerpt; rollback only on the user's go-ahead (D-06).

### Step 2b — operator reconnects F.A.S.T. (plan 03-02, not this plan)

The operator reconnects the F.A.S.T. tool from `galago-web` (Claude never sends `Configure`).

**Check:** `.venv/bin/python scripts/fast_status.py --port 40001` shows `status: "READY"` with
`run_state.state == "idle"`.

**Do not continue to Step 3 unless** this check passes.

### Step 3 — rebuild `galago-web` (plan 03-02, not this plan)

**Command (from `/home/formulatrix/data/nikko/galago-core`):**
```
docker tag galago-core-galago-web:latest galago-core-galago-web:rollback-pre-live04
TOOLBOX_PORT=11010 docker compose up -d --build
```

**Check:**
```
docker inspect galago-web --format='{{.Image}}'
curl -sf http://localhost:3010/api/health
curl -sf http://localhost:3010/runs
docker exec galago-web grep -r is_tip_broken /app/.next/server 2>/dev/null | head -1
docker exec galago-web grep -r run_state /app/gen-interfaces 2>/dev/null | head -1
```
Expected: a new image ID; `/api/health` and `/runs` answer 200; the built app under
`/app/.next/server` contains `is_tip_broken`; `/app/gen-interfaces` contains `run_state`; the
container reaches `host.docker.internal:40001`; `fast_status.py` still reports `READY`/`idle`.
No motion happens during deploy (D-03).

## Rollback (D-06)

Reverse order. Each step runs only on the user's explicit go-ahead (D-06). Never roll the
core back while the new UI and adapter are running.

### (1) galago-web — first

```
docker tag galago-core-galago-web:rollback-pre-live04 galago-core-galago-web:latest
cd /home/formulatrix/data/nikko/galago-core
TOOLBOX_PORT=11010 docker compose up -d --no-build --force-recreate galago-web
```
Check: the running image ID equals the pre-deploy one
(`sha256:9ad9c64fee6baa7ea9351c7cfa03bceb8f0db7f974fabbb6865b1143948880ca`).

### (2) galago-tools — second

```
cd /home/formulatrix/data/nikko/galago-tools
git status --porcelain   # must be empty before switching
git switch --detach 7c0ff7b953986bbc62221a14bad8b9594795b1f4
PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make proto
systemctl --user restart galago-tools
```
Then the operator reconnects F.A.S.T. from `galago-web`. Switch back to `feat/fast-tool` when
fixing forward (`git switch feat/fast-tool`).

### (3) core — last

```
~/.local/bin/uv pip install --python .venv/bin/python "git+file:///home/formulatrix/data/nikko/fast/fast-mcp@76f8c3fee41b0a2df3519aa74b022152df673824"
```
Check: `direct_url.json`'s `vcs_info.commit_id` equals `76f8c3fee41b0a2df3519aa74b022152df673824`.

State plainly: never roll the core back while the new UI and adapter run — that is the one
window LIVE-04's safe order exists to prevent.

## Deploy evidence

| Step | UTC start | UTC end | Command | Check output | Result |
|------|-----------|---------|---------|---------------|--------|
| Step 1 | — | — | (not yet run) | — | pending (Task 3) |
| Step 2 | — | — | (not yet run) | — | pending (Task 3) |
| Step 2b reconnect | — | — | (not yet run — operator action) | — | pending (plan 03-02) |
| Step 3 | — | — | (not yet run) | — | pending (plan 03-02) |

## Logs to watch (D-08)

- Manager/journal lines (does NOT carry tool command lines — verified 2026-10-14):
  ```
  journalctl --user -u galago-tools --since "<time>" --no-pager
  ```
- The F.A.S.T. tool's own command log (command/response lines live here, not in the journal):
  ```
  ~/.local/share/galago/trace_logs/<newest>/F.A.S.T.log
  ```
  Find the newest folder with `ls -dt ~/.local/share/galago/trace_logs/*/ | head -1`.
