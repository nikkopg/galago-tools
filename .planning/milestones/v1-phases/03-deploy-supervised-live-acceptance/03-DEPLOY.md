# Phase 3 Deploy Runbook

**Status:** Entry gate met (re-checked 2026-10-14T10:16Z, after the earlier same-day
2026-10-14T10:08:54Z check FAILed — see note below the table). Task 1 complete: the
pre-deploy record, runbook and rollback are written below. Task 2 (D-03) complete: the user
replied `go` — see "Go-ahead (D-03)" below; the F.A.S.T. tool was restored to `READY` before
the reply. Plan 03-01's deploy steps 1-2 (D-05) complete. Plan 03-02 Step 2b (operator
reconnect) PASSed; Step 3 (galago-web rebuild) initially ran via `docker compose up -d --build`
and PASSed every content/connectivity check, but produced a byte-identical image ID (Docker
cache hit on every layer, since `galago-web` had already been rebuilt from the same HEAD
outside this runbook) — BLOCKED pending a user decision. The user chose a no-cache rebuild;
that rebuild ran, produced a genuinely new image ID, and PASSed every Step 3 check — see the
Step 3 row below.

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

**Caveat (plan 03-02):** `rollback-pre-live04` (`sha256:9ad9c64...`) was built at
`2026-10-14T08:10:47Z` from the **same** galago-core HEAD `d95c2e1` as the live-04 rebuild
itself (an out-of-runbook rebuild that happened before this plan ran, recorded in the
Pre-deploy record above). Rolling `galago-web` back to this tag restores **identical
content** to what Step 3 just deployed, not the pre-milestone UI — the HEAD never changed
across this deploy, only the image's cache state did. A true pre-milestone `galago-web`
rollback (e.g. to undo the whole Phase 02 UI) would need a fresh `--no-cache` rebuild from
the pre-milestone galago-core commit, not a retag of this anchor.

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
| Step 1 | 2026-10-14T10:38:29Z | 2026-10-14T10:38:46Z | `~/.local/bin/uv pip install --python .venv/bin/python "git+file:///home/formulatrix/data/nikko/fast/fast-mcp@b30b38df48e8480f325228145ccae7915a56e437"` | Baseline (pre-install) run of `TestRequirementsPin` on the old core exited 1 (`ImportError: cannot import name 'PauseInfo' from 'fast_mcp.orchestration'`), proving the check discriminates. Install: `Uninstalled 1 package`/`Installed 1 package` (`fast-mcp` only, matching the D-04 dry-run preview). Post-install: `direct_url.json` assert passed, printed `pinned file:///home/formulatrix/data/nikko/fast/fast-mcp`; `TestRequirementsPin -v` → `Ran 3 tests in 0.003s` / `OK` (all 3 pass). `uv pip freeze` diff against the pre-deploy freeze: only the `fast-mcp` line changed (`76f8c3fe` → `b30b38d`), no other package. | PASS |
| Step 2 | 2026-10-14T10:39:24Z (restart local 17:39:24 WIB) | 2026-10-14T10:39:38Z (both ports listening) | `systemctl --user restart galago-tools` | `systemctl --user is-active galago-tools` → `active`. `MainPID` `944069` → `4044033` (`ActiveEnterTimestamp` 2026-10-14 17:39:26 WIB). Journal since restart shows `Killed process F.A.S.T` (old), then `Started Pf400 on port 40000` and `Started F.A.S.T on port 40001`, no Python traceback. Newest trace-log folder `~/.local/share/galago/trace_logs/1791974367/F.A.S.T.log` contains `fast server started, listening on 40001` (count 1), no traceback. `fast_status.py --port 40001` → `{"status": "NOT_CONFIGURED", "run_state": null, ...}` (expected — no Configure sent, awaiting plan 03-02's operator reconnect). | PASS |
| Step 2b reconnect | — | 2026-10-14T10:50:24Z | Operator reconnected the F.A.S.T. tool from `galago-web` (Simulate off, configuration unchanged); operator reply: "connected, but i need to change to other page first then back to the tools page to see the ready status" (UI observation, non-blocking — recorded below). Claude sent no `Configure`. | `fast_status.py --port 40001` → `{"status": "READY", "run_state": {"percent": 0.0, "state": "idle", "pause": null}, ...}`. Newest trace-log folder unchanged (`~/.local/share/galago/trace_logs/1791974367/`); `F.A.S.T.log` line 3: `Received configuration: toolId: "F.A.S.T" fast { host: "10.150.1.170" port: 5003 expected_tray_id: 90 }` — host/port/`expected_tray_id` match the Pre-deploy record exactly, no `simulated` flag; `grep -ic traceback` over the 444-line log → `0`. | PASS |
| Step 3 (cached attempt) | 2026-10-14T10:50:35Z | 2026-10-14T10:51:18Z | Pre-step-3 checks: `git -C galago-core rev-parse HEAD` → `d95c2e143ca13d8837bd9c248d6579777b2ebdc9` (equals the Entry-gate SHA); `git -C galago-core status --short controller/` → empty; `.dockerignore` present. Recorded running image `sha256:9ad9c64fee6baa7ea9351c7cfa03bceb8f0db7f974fabbb6865b1143948880ca` and tagged it `galago-core-galago-web:rollback-pre-live04` (D-06 anchor). Then, from `/home/formulatrix/data/nikko/galago-core`: `TOOLBOX_PORT=11010 docker compose up -d --build`. | Build output: every layer `CACHED`, `writing image sha256:9ad9c64fee6baa7ea9351c7cfa03bceb8f0db7f974fabbb6865b1143948880ca done`; `Container galago-web Recreate/Recreated/Started`. Post-build checks all PASSed (health/runs 200, `is_tip_broken`/`run_state` present, host port reachable, `fast_status.py` READY/idle, `galago-tools` MainPID unchanged) but the running image ID was **identical** to `rollback-pre-live04` — the build was satisfied entirely from Docker's cache because galago-core's `controller/` had not changed since the out-of-runbook rebuild already recorded in the Pre-deploy record (`2026-10-14T08:10:47Z`, same HEAD `d95c2e1`). | BLOCKED — identical image ID; not scored PASS/FAIL, see the no-cache rebuild row below |
| Step 3 (no-cache rebuild, user decision) | 2026-10-14T13:08:07Z | 2026-10-14T13:10:08Z | User's explicit decision: "No cache rebuild" — force a no-cache rebuild so the must-have "galago-web container is running on a new image ID" is genuinely met, rather than accepting the cached, identical-content result above. Re-confirmed read-only immediately before the rebuild: `galago-web /api/runs` → `{"count": 0, "data": []}` (no `RUNNING` run); `fast_status.py --port 40001` → `READY`/`idle`; `galago-tools` MainPID `4044033` unchanged; galago-core HEAD still `d95c2e143ca13d8837bd9c248d6579777b2ebdc9`, `controller/` clean. The `rollback-pre-live04` tag was left untouched (still `sha256:9ad9c64...`) — not re-tagged. From `/home/formulatrix/data/nikko/galago-core`: `TOOLBOX_PORT=11010 docker compose build --no-cache galago-web` (ran 2026-10-14T13:08:07Z–13:10:02Z, exit 0, produced `sha256:26917ca79a781bb3b3563b481d1845ce1defeb92c33a0dc97e9368baf39029a2`), then `TOOLBOX_PORT=11010 docker compose up -d` (2026-10-14T13:10:08Z, `Container galago-web Recreate/Recreated/Started`; only one service, `galago-web`, is defined in `docker-compose.yml`, so nothing else was touched). | `docker inspect galago-web --format '{{.State.Status}} {{.Image}}'` → `running sha256:26917ca79a781bb3b3563b481d1845ce1defeb92c33a0dc97e9368baf39029a2` — differs from `rollback-pre-live04` (`sha256:9ad9c64...`). `curl /api/health` → `200`; `curl /runs` → `200`. `docker exec galago-web grep -rl is_tip_broken /app/.next/server` → `/app/.next/server/chunks/6756.js`. `docker exec galago-web grep -rl run_state /app/gen-interfaces` → `/app/gen-interfaces/tools/grpc_interfaces/tool_base.ts`. Container TCP probe to `host.docker.internal:40001` → `open`. `fast_status.py --port 40001` → `{"status": "READY", "run_state": {"state": "idle", ...}}`. `systemctl --user show galago-tools -p MainPID -p ActiveState` → `MainPID=4044033`, `ActiveState=active` (unchanged). All seven step-3 checks PASS. | PASS |

**Note on the Step 3 finding (plan 03-02):** the first `docker compose up -d --build` run
reused Docker's build cache for every layer because galago-core's `controller/` had not
changed since an out-of-runbook rebuild already recorded in the Pre-deploy record
(`2026-10-14T08:10:47Z`, same HEAD `d95c2e1`), producing a byte-identical image ID. Every
content/connectivity/safety check PASSed in that attempt; only the literal must-have ("running
image ID differs from the rollback tag") could not be satisfied by that exact command, because
there was no new content for a rebuild to produce. Execution stopped there per plan 03-02's
own instruction and the no-self-rollback directive, and the user was asked to decide. The user
replied "No cache rebuild." Claude then ran `docker compose build --no-cache galago-web`
followed by `docker compose up -d` (not `--build`, since the image was already freshly built),
which produced a genuinely new image ID (`sha256:26917ca7...`) and PASSed every Step 3 check,
including the one the cached attempt could not meet. Step 3 is now recorded `PASS`.

**Safe order (LIVE-04):** four strictly increasing UTC times —
step 1 check passed `2026-10-14T10:38:46Z` <
`galago-tools` restart `2026-10-14T10:39:24Z` <
step 2 run_state check passed `2026-10-14T10:50:24Z` <
`galago-web` build start `2026-10-14T13:08:07Z` (the no-cache rebuild that produced the
final, PASSing result; the earlier cached attempt's build start `2026-10-14T10:50:35Z` is
also later than the step 2 check and does not break the order).

### Post-deploy record (Task 3)

- Deployed galago-tools HEAD: `fdbe1303b102c877e67ce9bca18600cc9ac8ed64`; last code commit (`tools interfaces setup.py requirements.txt`): `d9acdcf0e8f203cd553aaafad2e262b387bcdc06` (unchanged from the pre-deploy record — the editable install now serves this HEAD, including the regenerated proto with `run_state`/`Pause`).
- Post-deploy MainPID: `4044033`, active since `2026-10-14 17:39:26 WIB`.
- Post-deploy trace-log folder: `~/.local/share/galago/trace_logs/1791974367/`; F.A.S.T. log: `~/.local/share/galago/trace_logs/1791974367/F.A.S.T.log`. Later plans compare against this path to detect an unexpected restart.
- `fast_status.py --port 40000` (Pf400) also reads `NOT_CONFIGURED` post-restart — expected, every tool server loses its configuration on restart; Pf400 is out of scope for this plan's reconnect (plan 03-02 covers F.A.S.T. only).
- `galago-web` was not touched; Claude sent no `Configure`, `ExecuteCommand` or any other command to any tool in this task.

### Post-deploy galago-web rebuild (outside this runbook, 2026-10-15)

- `galago-web` was rebuilt again outside this runbook, from `galago-core` HEAD
  `d4726ff` ("fix(02): apply UI review fixes to the control bar"). The image is
  `sha256:10e7493591f10a9d5092807ed344a590784c61e4a0926140ddcc07a779d8f089`, created
  2026-10-15 09:00:58 WIB, and the container was recreated at 2026-10-15T02:01:02Z. It replaces
  the `26917ca7...` image that Step 3 recorded.
- Changes between `d95c2e1` and `d4726ff` are galago-core Phase 2 code-review fixes
  (WR-01..WR-07) and UI-review fixes to the control bar, all in `controller/`. The
  `vendor/galago-tools` gitlink is still `cb7886d`, so the protos match this repo, and the
  D-01.3 condition still holds.
- `galago-tools` did not restart (MainPID `4044033`), and the service core is still `b30b38d`.
- The safe order still holds: this rebuild comes after the step 2 `run_state` check.
- Everything after it was exercised on this image:
  - the dry run (D-07, run started 09:06:06 WIB)
  - galago-core's 02-UAT completion (`c71d2a1`, 09:43 WIB, 8/8 pass, including test 2
    Pause/Resume/Abort and test 5 instrument pause on the real F.A.S.T.)
  - the live scenarios from 03-04 on
- Rollback (D-06): `rollback-pre-live04` (`9ad9c64`, from `d95c2e1`) is still the recorded
  anchor. Rolling back to it would also undo the WR fixes.

### Tool-server restart without a service restart (2026-10-15)

- The `galago-tools` manager stopped the tool servers at 09:59:58 WIB and started them again
  at 10:16:36 WIB. The `:8081` manager page did this (requests from `10.150.1.89`), not
  systemd. MainPID `4044033` did not change.
  - New PIDs: F.A.S.T. `727894`, Pf400 `727872`.
  - F.A.S.T. was reconnected at 10:16:52 WIB in real mode with the pre-deploy
    host/port/tray.
  - The servers run the same editable-install code and core `b30b38d`.
- **The MainPID check cannot detect a tool-server restart.** From 03-05 on, every no-restart
  check also compares the PID listening on `:40001` with `ss -ltnp` (baseline `727894`). It
  also checks that line 2 of `F.A.S.T.log` (the `fast server started` line, currently
  `2026-10-15 10:16:36`) has not changed.
- A tool-server restart **overwrites `F.A.S.T.log` in place**. Read the production log evidence
  for a scenario before anything restarts.

### D-14 redeploy (LIVE-05 fix)

- LIVE-05's first attempt (plan 03-05) scored FAIL (`03-ACCEPTANCE.md`, commit `eb8ca7f`): the
  instrument's wrong-plate sentinel `-1` rendered literally as "found -1" instead of "found none"
  in the `tool_paused` prompt, because galago-core's `pausePrompt.ts` `describeWrongDetectionEntry`
  mapped only `null`/`undefined`/`""` to "none". Per D-14, the scenario stopped there pending a fix.
- galago-core fixed it on 2026-10-15 as quick task `261015-f48`, commits `07fb7fa`, `e6b0e97` and
  `ad87ea5` (HEAD `ad87ea5`, 11:00:07 WIB): `controller/components/runs/pausePrompt.ts` gained a new
  `isNoPlateDetected` function that maps `null`, `undefined`, `""`, `-1` and `"-1"` to "none"; unit
  tests were added. The `vendor/galago-tools` gitlink is still `cb7886d`, so the protos are
  unchanged — this is a galago-core-only fix.
- `galago-web` was rebuilt again outside this runbook at 2026-10-15 11:02:27 WIB. New image:
  `sha256:b0e183e5513d11f80494e83d214f14c42dcbe8931d4616aee995f5ec8271f317`; the container was
  created at `2026-10-15T04:02:31Z`. It replaces the `10e7493591f...` image recorded in the
  "Post-deploy galago-web rebuild" note above.
- Bundle check (read-only, before the rerun): `docker exec galago-web grep -o
  '.\{0,40\}-1===r.\{0,40\}' /app/.next/static/chunks/pages/runs-8bc5bbafd0ab0b33.js` showed the
  deployed bundle contains `-1===r||"-1"===r?"none"`, confirming the fix is present in what the
  operator's browser actually runs.
- `galago-tools` was **not** restarted for this redeploy: MainPID stayed `4044033`, the F.A.S.T.
  listener PID stayed `727894`, `F.A.S.T.log` line 2 still read `2026-10-15 10:16:36 ... fast server
  started`, and `journalctl --user -u galago-tools` showed no entries since 10:45. The safe order
  still holds: core and tools are unchanged, only the web layer was rebuilt.
- The operator reconnected F.A.S.T. at 11:05:44 WIB before rerunning the scenario; the "Received
  configuration" log line shows host `10.150.1.170`, port `5003`, `expected_tray_id` 90, no
  simulated flag.
- The operator reran LIVE-05 after this redeploy; plan 03-05's `03-ACCEPTANCE.md` record now scores
  it PASS, with the first attempt kept there as history.
- Rollback (D-06): `rollback-pre-live04` (`9ad9c64`, from `d95c2e1`) is still the recorded anchor.
  Rolling back to it would undo all of Phase 2's code-review/UI-review fixes (WR-01..WR-07, the
  control-bar fixes) **and** this D-14 none-plate fix.

### D-14 redeploy (LIVE-06b adapter fix)

- LIVE-06b's attempt 2 (plan 03-06, `03-ACCEPTANCE.md`) exposed a wording defect: the instrument
  reports an operator abort as `error_name NoError` / `error_code 0`, not as empty/`None` fields,
  so `tools/fast/server.py`'s `_message_for` appended a `": [outcome]"` suffix the D-09/D-11
  wording does not call for ("run aborted by operator at 22%: NoError (0)"). Per D-14, the
  scenario stopped there pending a fix.
- This repo fixed it on 2026-10-15: `7d77e23` (RED test for the `NoError (0)` suffix) then
  `201d987` (fix: `_is_no_error` now treats a `NoError`/`0` report with no message as no error, so
  the wording reads `"run aborted by operator at <p>%"` with no suffix; real errors keep their
  suffix; the non-operator abort wording is unchanged).
- Gate, re-run fresh before redeploying: `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash
  bin/make proto test` exit 0, **144 tests passed**; `ruff check tools/fast/server.py
  tools/tests/fast_test.py` → "All checks passed!"; `mypy tools/fast/server.py` → "Success: no
  issues found in 1 source file". This is an adapter-only fix: no proto change, so galago-core's
  `vendor/galago-tools` gitlink (`cb7886d`) and galago-web are unaffected by the fix itself.
- Redeploy, on the user's literal "go": `systemctl --user restart galago-tools` at
  2026-10-15T04:40:59Z (11:40:59 WIB). Journal: the manager stopped the old tool processes
  (Pf400 `727872`, F.A.S.T. `727894`) at 11:40:59-11:41:00 WIB, then started fresh: `MainPID`
  `4044033` -> `836290` (`ActiveEnterTimestamp` 2026-10-15 11:41:00 WIB); new F.A.S.T. listener PID
  `727894` -> `836333`; new Pf400 listener PID `836310`. New trace-log folder
  `~/.local/share/galago/trace_logs/1792039261/`; `F.A.S.T.log` line 2:
  `2026-10-15 11:41:02 | INFO | fast server started, listening on 40001` — no traceback.
  `fast_status.py --port 40001` read `NOT_CONFIGURED` immediately after (expected, awaiting the
  operator's reconnect). galago-core (`b30b38d` core, `d4726ff`-derived `galago-web`) was not
  touched.
- **Connect-all-tools incident (galago-core observation, non-blocking, out of scope for this
  phase)**: at 11:42:04 WIB a "Connect all tools" action from the `:8081` manager page sent
  F.A.S.T. an **empty** config (`fast {\n}`); the log shows `2026-10-15 11:42:04 | ERROR | Failed
  to configure Tool=F.A.S.T-fast: Config.host is required`. Pf400 failed the same way
  (`"[Errno -2] Name or service not known"`). Nothing moved. Root cause (galago-core, out of
  scope): `ToolsComponent.tsx` sends `{[tool.type]: tool.config}` to "Connect all", but the stored
  config is already wrapped as `{fast:{...}}`, so the nested key is dropped and the handler
  receives an empty object. Recorded here for the user's awareness; not fixed in this phase.
- The operator then reconnected F.A.S.T. from its own tool page at 11:44:12 WIB (`Received
  configuration`: host `10.150.1.170`, port 5003, `expected_tray_id` 90, no `simulated` flag —
  real mode), and reconnected Pf400 with Simulate ON (status `SIMULATED`, this environment's
  established baseline per the Pre-deploy record above, not a new finding).
- The operator reran LIVE-06b after this redeploy; plan 03-06's `03-ACCEPTANCE.md` record now
  scores it PASS, with both earlier attempts (the rehearsal missing `get_status`, and the wording-
  defect attempt that found this bug) kept there as history.
- Rollback (D-06, this fix only): `git revert 201d987` (restores the `": [outcome]"` suffix
  behavior), then `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make proto test`
  to confirm the gate, then `systemctl --user restart galago-tools` and the operator reconnects
  F.A.S.T. from `galago-web`. The broader rollback anchor (`rollback-pre-live04`,
  `9ad9c64`, from `d95c2e1`) is unaffected — this fix never touched the proto or `galago-web`, so
  that anchor's caveat (undoes Phase 2 WR fixes + the LIVE-05 none-plate fix) is unchanged by this
  entry.
- **New no-restart baseline for 03-07 and later plans**: `galago-tools` MainPID `836290`, F.A.S.T.
  listener PID `836333`, trace-log folder `1792039261` (`F.A.S.T.log` line 2:
  `2026-10-15 11:41:02 ... fast server started`). From 03-07 on, compare against these values
  (not the earlier `4044033`/`727894`/`1791974367` baseline) to detect an unexpected restart.

### LIVE-07 attempt 1: tool-server restart and queue-defect redeploy note (2026-10-15)

- At 12:04:42 WIB the F.A.S.T. tool server restarted again with no `galago-tools` service restart
  (MainPID stayed `836290`); the F.A.S.T. listener PID went `836333` -> `867162`, most likely
  another `:8081` manager-page action (same pattern as the 2026-10-15 09:59:58-10:16:36 WIB
  restart noted above). This overwrote `F.A.S.T.log` in place; the operator reconnected F.A.S.T.
  at 12:04:50 WIB. Both happened before LIVE-07 attempt 1 started.
- **New no-restart baseline for the LIVE-07 rerun**: `galago-tools` MainPID `836290` (unchanged),
  F.A.S.T. listener PID `867162`, trace-log folder `1792039261` still current (the folder is
  unchanged; only the log file inside it was overwritten). Re-check this listener PID (not
  `836333`) at the start of the rerun to detect any further unexpected tool-server restart.
- LIVE-07 attempt 1 (`03-ACCEPTANCE.md` `## LIVE-07`) FAILed: D-12's restart/recovery mechanics
  held completely, but `galago-web`'s queue (`controller/server/utils/SqliteQueue.ts`
  `startNext()`) re-ran a previously operator-aborted LIVE-06b step instead of dispatching
  LIVE-07's own transfer. This is a galago-core queue defect, not an adapter or deploy-order
  fault; no change to this repo's deployed code is implicated.
- **D-14 route**: once galago-core lands the queue fix (`startNext()` must skip or remove FAILED
  rows instead of re-running them), `galago-web` needs a rebuild following this runbook's safe
  order (D-05) — core and `galago-tools` are unaffected, so only the `galago-web` rebuild step
  applies, the same shape as the LIVE-05 and LIVE-06b D-14 redeploys above. After the rebuild:
  rerun LIVE-07, and also rerun the LIVE-06b follow-up check (after an abort, starting a new run
  must not re-run the aborted step) per the note added under `03-ACCEPTANCE.md`'s `## LIVE-06b`
  Result.

### D-14 redeploy (queue re-run fix)

- LIVE-07 attempt 1 (above) exposed a galago-core queue defect: an operator-aborted step stayed in
  `_queue` and re-ran on the next `startNext()`. Per D-14, the scenario stopped pending a
  galago-core fix.
- galago-core fixed it (quick task `261015-h0q`): commits `4b575ed`, `5598347`, `e18a177`,
  `a0afd61`. An accepted operator Abort (sent through `galago-web`'s run controls) now calls
  `fail(..., {dequeue: true})`, which removes that step from the `_queue` table, so `startNext`
  cannot re-run it; other failures keep the upstream retry behavior; a late-accepted abort is
  handled by `_recordAcceptedAbort` → `dequeue`.
- galago-core HEAD at the rebuild was `a0afd61`, with a later docs-only commit `539464a` recording
  a todo: "Queue errors 'Item N not found' after clear during abort" (minor, pre-existing —
  clearing the queue while an aborted step is still finishing produces a spurious error state; not
  fixed here). `vendor/galago-tools` gitlink unchanged (`cb7886d`); `controller/` clean — no proto
  or adapter-facing change, so only `galago-web` needs a rebuild.
- Rebuild (`galago-web` only, following this runbook's safe order — core and `galago-tools` are
  unaffected): image `sha256:94bdfa7e4dba1cc98923b096995f68a07e9aced6e5972e624a205bc0a3abe6ba`,
  built 2026-10-15 14:05:18 WIB. `/api/health` returns 200. The fix verified present in the
  deployed server bundle: `/app/.next/server/chunks/6756.js` carries the `dequeue: true` fail-path.
- `galago-tools` untouched by this redeploy: MainPID `836290` (unchanged), F.A.S.T. listener PID
  `867162` (unchanged), `F.A.S.T.log` line 2 still reads the pre-existing `12:04:42 | INFO | fast
  server started, listening on 40001` (no new restart). F.A.S.T. stayed `READY` through the
  redeploy, so no operator reconnect was needed this time (unlike the `galago-tools`-service
  redeploys above, which do require a reconnect).
- The operator reran LIVE-06b's follow-up check and LIVE-07 after this redeploy; `03-ACCEPTANCE.md`
  now scores both PASS (the LIVE-06b follow-up note under `## LIVE-06b`, and the scored rerun under
  `## LIVE-07`), with LIVE-07 attempt 1 kept there as history.
- Two residual galago-core queue findings surfaced by these reruns (FINDING (a): an aborted run's
  later steps stay queued; FINDING (b): a `galago-web`-restart-orphaned step's queue row stays
  `STARTED` and would re-run) are NOT fixed by this redeploy — they are recorded in
  `03-ACCEPTANCE.md`'s `## Flagged assumptions` as blocking items for the phase close-out decision
  in plan 03-08, each with an operator workaround (Clear All before starting another run).
- Rollback (D-06, this fix only): `rollback-pre-live04` (`9ad9c64`, from `galago-core` `d95c2e1`)
  would undo this fix along with every other post-deploy galago-core/`galago-web` change recorded
  in this document (the LIVE-05 none-plate fix, the LIVE-06b wording-adjacent `galago-web`
  content, and this queue fix) — it predates all of them. A rollback of this fix alone would need a
  fresh `galago-web` rebuild from galago-core HEAD immediately before `4b575ed`, not the
  `rollback-pre-live04` tag.
- **New no-restart baseline, unchanged from the LIVE-07 attempt 1 entry above**: `galago-tools`
  MainPID `836290`, F.A.S.T. listener PID `867162`, trace-log folder `1792039261`. This redeploy
  did not touch `galago-tools`, so the baseline carries forward unchanged into the LIVE-07 rerun
  and the LIVE-06b follow-up check.

### CR-01 redeploy (2026-10-16, after milestone re-verification)

- Why: Phase 2 gap-closure plan 02-05 (`134e097` fix, `7c2e15a` test) changed `Resume`'s
  crash-recovery branch after the last deploy (`201d987`). The user chose redeploy, no live rerun:
  LIVE-07 used the in-flight Resume path, which CR-01 did not touch (see `03-VERIFICATION.md`
  Resolution).
- Gate: `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make proto test` 147
  passed; ruff clean; mypy clean. Pre-restart: F.A.S.T. `READY`/idle, `galago-web` queue empty.
- Log backup: trace folder `1792039261` copied to
  `~/.local/share/galago/log-backups/pre-cr01-redeploy-*/`.
- Restart, on the user's "go 1": `systemctl --user restart galago-tools` at 2026-10-16 05:47:21
  WIB. MainPID `836290` -> `1940146`; F.A.S.T. listener `867162` -> `1940246`; new trace folder
  `1792104444`, `F.A.S.T.log` line 2 `fast server started, listening on 40001`, no traceback.
  Editable install, so the service runs HEAD.
- Reconnect: at the user's request, Claude sent `Configure` over gRPC with the pre-restart configs
  (F.A.S.T. real mode `10.150.1.170:5003`, `expected_tray_id` 90; Pf400 `simulated: true`). This
  departs from the operator-only reconnect rule, at the user's instruction. F.A.S.T. `READY`
  (idle), Pf400 `SIMULATED`. No motion command sent. Core and `galago-web` not touched (no proto
  change).
- New no-restart baseline: MainPID `1940146`, F.A.S.T. listener `1940246`, trace folder
  `1792104444`.
- Rollback: `git revert 7c2e15a 134e097`, re-run the gate, `systemctl --user restart galago-tools`,
  reconnect F.A.S.T.

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
