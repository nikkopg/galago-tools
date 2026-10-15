# Phase 3 Acceptance Evidence (D-13)

Evidence record for the deploy and supervised live acceptance scenarios. Fed from
`03-DEPLOY.md`'s runbook/evidence where noted. Created by plan 03-02; later plans in this
phase (03-03 to 03-08) fill the remaining sections.

## Summary

| Requirement | Scenario | Result | Evidence |
|---|---|---|---|
| LIVE-04 | LIVE-04 Deploy (core → galago-tools → galago-web, safe order) | PASS | `03-DEPLOY.md` Deploy evidence table (Steps 1, 2, 2b reconnect, Step 3 cached + no-cache); `## LIVE-04 Deploy` below |
| — | Dry run (D-07) | PASS | `## Dry run (D-07)` below |
| LIVE-06 | LIVE-06a: Pause → Resume → SUCCESS | PASS | `## LIVE-06a: Pause -> Resume -> SUCCESS` below |
| LIVE-05 | LIVE-05: Deck 3 empty → prompt → fix deck → Resume → SUCCESS | not run | — |
| LIVE-06 | LIVE-06b: Pause → Abort → aborted by operator, queue FAILED | not run | — |
| LIVE-07 | LIVE-07: galago-web restart mid-run → tool-page recovery | not run | — |

## LIVE-04 Deploy

- Date/time: 2026-10-14, 2026-10-14T10:38:29Z (Step 1 start) through 2026-10-14T13:10:08Z
  (no-cache Step 3 `docker compose up -d` complete), UTC.
- Operator: the user gave the go-ahead (D-03, literal reply `go`) and reconnected the
  production F.A.S.T. tool from `galago-web` (Step 2b, Simulate off, configuration unchanged);
  the user also made the Step 3 "No cache rebuild" decision after the cached attempt's finding.
  Claude ran every command and check; Claude sent no `Configure`, `ExecuteCommand`, or any
  other command to any tool.
- **SHAs and images:**
  - Service core (fast-mcp): pre-deploy `76f8c3fee41b0a2df3519aa74b022152df673824` → deployed
    `b30b38df48e8480f325228145ccae7915a56e437`.
  - `galago-tools` deployed HEAD: `fdbe1303b102c877e67ce9bca18600cc9ac8ed64` (last code commit
    `d9acdcf0e8f203cd553aaafad2e262b387bcdc06`); running adapter SHA before restart was
    `7c0ff7b953986bbc62221a14bad8b9594795b1f4`.
  - `galago-core` HEAD (entry-gate and both Step 3 attempts, unchanged throughout):
    `d95c2e143ca13d8837bd9c248d6579777b2ebdc9`.
  - `galago-web` image before: `sha256:9ad9c64fee6baa7ea9351c7cfa03bceb8f0db7f974fabbb6865b1143948880ca`
    (also tagged `galago-core-galago-web:rollback-pre-live04`).
  - `galago-web` image after (final, no-cache rebuild):
    `sha256:26917ca79a781bb3b3563b481d1845ce1defeb92c33a0dc97e9368baf39029a2`.
- **Step checks:**
  - Step 1 (core into the service `.venv`, D-05 step 1): PASS — `direct_url.json` pinned to
    `b30b38d`, `TestRequirementsPin` 3/3 `OK`, freeze diff shows only `fast-mcp` changed.
  - Step 2 (restart `galago-tools`, D-05 step 2): PASS — `is-active` → `active`, new MainPID
    `4044033`, journal/trace-log clean, no traceback.
  - Step 2b (operator reconnect, plan 03-02 Task 1): PASS — `fast_status.py --port 40001` →
    `READY`/`run_state.state: idle`; `F.A.S.T.log` shows a real-mode `Received configuration`
    line with the pre-deploy host/port/`expected_tray_id` and no `simulated` flag; non-blocking
    observation: the operator needed to navigate away from and back to the tools page to see
    the `READY` status render (UI staleness, not a functional blocker).
  - Step 3, cached attempt (D-05 step 3, plan 03-02 Task 2): BLOCKED, not scored PASS/FAIL —
    every content/connectivity/safety check PASSed (`/api/health` 200, `/runs` 200,
    `is_tip_broken` under `/app/.next/server`, `run_state` under `/app/gen-interfaces`, host
    port reachable, `fast_status.py` READY/idle, `galago-tools` MainPID unchanged), but the
    rebuild reused Docker's cache for every layer (galago-core `controller/` unchanged since an
    out-of-runbook rebuild already recorded in `03-DEPLOY.md`'s Pre-deploy record) and produced
    a running image ID byte-identical to `rollback-pre-live04`.
  - Step 3, no-cache rebuild (user decision "No cache rebuild"): PASS — re-confirmed read-only
    before the rebuild (no run `RUNNING`, `fast_status.py` READY/idle, `galago-tools`
    MainPID/`galago-core` HEAD unchanged); `rollback-pre-live04` left untouched; ran
    `docker compose build --no-cache galago-web` then `docker compose up -d` (the compose file
    defines only the `galago-web` service, so nothing else was recreated); the running image ID
    (`sha256:26917ca7...`) differs from the rollback tag and every Step 3 check PASSed.
- **Safe order (the four times, strictly increasing):** step 1 check passed
  `2026-10-14T10:38:46Z` < `galago-tools` restart `2026-10-14T10:39:24Z` < step 2 run_state
  check passed `2026-10-14T10:50:24Z` < `galago-web` build start `2026-10-14T13:08:07Z`
  (the no-cache rebuild that produced the final PASSing result).
- **Rollback anchors:** `galago-core-galago-web:rollback-pre-live04` =
  `sha256:9ad9c64fee6baa7ea9351c7cfa03bceb8f0db7f974fabbb6865b1143948880ca`; service core
  rollback target `76f8c3fee41b0a2df3519aa74b022152df673824`; running adapter SHA rollback
  target `7c0ff7b953986bbc62221a14bad8b9594795b1f4`. **Caveat:** `rollback-pre-live04` was built
  at `2026-10-14T08:10:47Z` from the same `galago-core` HEAD `d95c2e1` as the final deploy, so
  rolling `galago-web` back to it restores identical content, not the pre-milestone UI; a true
  pre-milestone rollback needs a fresh rebuild from the pre-milestone `galago-core` commit (see
  `03-DEPLOY.md` Rollback (D-06) section).
- **Result: PASS** — every Step 1/2/2b/3 check PASSed (Step 3 PASSed on the no-cache rebuild
  after the cached attempt's documented, non-blocking finding was resolved by explicit user
  decision); the safe order holds; rollback anchors are recorded for every layer.
- **Post-deploy note (2026-10-15):** `galago-web` was later rebuilt outside the runbook from
  `galago-core` `d4726ff` (Phase 2 code-review and UI-review fixes; the gitlink `cb7886d` and
  protos are unchanged). The image is `sha256:10e7493591f1...`, built 09:00:58 WIB. The dry run,
  galago-core's 02-UAT completion and the live scenarios all ran on this image. Details are in
  `03-DEPLOY.md` under "Post-deploy galago-web rebuild". LIVE-04's result is unaffected.

## Dry run (D-07)

- Date/time: 2026-10-15T02:06:06Z (run start) to 2026-10-15T02:14:15Z (final resume reply),
  UTC; 2026-10-15 09:06:06 WIB to 2026-10-15 09:14:15 WIB. Harness itself was started
  2026-10-14T13:25:21Z (2026-10-14 20:25:21 WIB) and configured simulated at
  2026-10-15T02:01:38Z (2026-10-15 09:01:38 WIB).
- Operator: the user registered FAST-DRYRUN (port 40003, host `sim-no-contact.invalid`,
  Simulate on), created the DRYRUN protocol, ran the walkthrough's nine steps in the deployed
  `galago-web` UI, chose Return liquid = yes at the abort prompt, and deleted FAST-DRYRUN
  afterward. Operator replies in order: "done, FAST-DRYRUN set to 40003 and simulated, created
  DRYRUN protocol"; "followed you 1-9 steps, check my last run"; "resume in tool page is
  disabled" (sent while the step was still running, before the 09:13:46 reply — correct step-4
  behavior, not a fault); "deleted FAST-DRYRUN, all visual checks passed". Claude ran the harness,
  read the logs, and sent no command to FAST-DRYRUN or to the production F.A.S.T. tool.
- Harness: `scripts/fast_dryrun.py` at commit `5cd20eb92962430b678701e1c9dc620ab1a903b2`;
  port 40003; `--auto-pause-after 90 --auto-pause-count 2` (rearm delay 5s, default); log
  `$HOME/.local/share/galago/dryrun/harness-20261014T132521Z.log`.
- Checklist results:
  1. PASS — run started 09:06:06 WIB; the harness log shows the `fast transfer` command sent at
     that time and `Running command Transfer`/BUSY in the same line; operator confirmed the
     control bar rendered tool, command, running badge and progress during the run ("followed
     you 1-9 steps" / "all visual checks passed").
  2. PASS — Pause instrument sent a `pause` command at 09:06:18 WIB, reply SUCCESS at 09:06:19;
     operator confirmed the confirmation dialog opened and the simulated pause changed nothing
     in the run state, as expected.
  3. PASS — no abort or other command appears in the harness log between the 09:06:19 pause
     reply and the 09:07:36 auto-pause (episode 1); this absence is the evidence that Stop ->
     Cancel sent nothing, matching the operator's account that the Abort confirmation opened
     with Return-liquid unselected, no countdown, and Cancel closed it with no command sent.
  4. PASS — operator reported "resume in tool page is disabled" while the step was still
     running (before the 09:13:46 transfer reply), matching the Run Recovery card's expected
     disabled state and "A run step is tracking this tool; use the run page." text while a run
     step tracks the tool.
  5. PASS — auto-pause episode 1 fired at 09:07:36 WIB, 90s after the 09:06:06 run start,
     carrying `WRONG_PLATE_PAUSE` (errorCode -645, errorName WrongPlateType, percent 40,
     eventPayload.wrongDetection [{expectedPlateID 1, detectedPlateID null, position 3}]), which
     renders as "WrongPlateType (-645)" / "Deck 3: expected plate 1, found none"; operator
     confirmed via "all visual checks passed".
  6. PASS — Resume sent with `is_tip_broken "no"` at 09:08:36 WIB, reply SUCCESS at 09:08:51
     (15s simulated Resume estimate), matching the operator's chosen "Tip broken? no".
  7. PASS — auto-pause episode 2 fired at 09:08:56 WIB (5s rearm delay after the 09:08:51
     Resume SUCCESS, as designed); Abort sent with `return_liquid "yes"` at 09:09:35 WIB, reply
     SUCCESS at 09:09:50 (15s simulated Abort estimate); operator's Return-liquid choice: **yes**.
  8. PASS — the transfer itself replied SUCCESS at 09:13:46 WIB (step ended); the tool-page
     Resume was sent with `is_tip_broken "no"` at 09:14:00 WIB (after the step ended), reply
     SUCCESS at 09:14:15; operator confirmed the Run Recovery card was enabled at that point and
     reported success.
  9. PASS — operator confirmed "deleted FAST-DRYRUN"; independently re-verified via
     `tool.getAll` on the deployed `galago-web` API, which now lists only `Pf400` (port 40000)
     and `F.A.S.T` (port 40001) — no FAST-DRYRUN record remains. No ufw rule was added for
     40003 in Task 1 (the container reached the harness directly), so none needed removal. The
     DRYRUN protocol record was not reported deleted; the plan treats that as optional and
     leaves it to the operator.
- Commands seen: harness log, in order, all SUCCESS:
  - 09:06:06 WIB `fast.transfer` (deck 1->3, plate 1->1, A1->A1, 8x1, 260, fresh, expected_tray_id
    0 — the form's blank-field default) — reply SUCCESS at 09:13:46 (step end).
  - 09:06:18 WIB `fast.pause` -> SUCCESS 09:06:19.
  - 09:07:36 WIB auto-pause episode 1 (no operator command; harness-internal).
  - 09:08:36 WIB `fast.resume` (`is_tip_broken "no"`) -> SUCCESS 09:08:51.
  - 09:08:56 WIB auto-pause episode 2 (no operator command; harness-internal).
  - 09:09:35 WIB `fast.abort` (`return_liquid "yes"`) -> SUCCESS 09:09:50.
  - 09:13:46 WIB transfer reply SUCCESS (step ends).
  - 09:14:00 WIB `fast.resume` (`is_tip_broken "no"`, tool page, after the step ended) ->
    SUCCESS 09:14:15.
  - **Note — two extra operator-initiated commands, not in the walkthrough script:**
    09:11:22 WIB `fast.pause` -> SUCCESS 09:11:23, and 09:11:46 WIB `fast.abort`
    (`return_liquid "no"`) -> SUCCESS 09:12:01. Both occurred after the scripted abort
    (09:09:35-09:09:50) and before the transfer's own reply (09:13:46), i.e. while the run was
    still in flight and unpaused (both auto-pause episodes already spent). The operator did not
    state what produced them when asked; recorded here honestly rather than attributed to Stop
    -> Cancel (which the log independently shows sent nothing, item 3 above) or to any scripted
    step. They do not change the pass/fail of any of the nine walkthrough items and both replied
    SUCCESS, so they carry no safety implication for D-07.
- Production tool untouched: `~/.local/share/galago/trace_logs/1791974367/F.A.S.T.log`
  (694,871 lines total) contains zero `Running command` lines in the entire file, and the window
  2026-10-15 09:06:06-09:14:15 WIB (02:06:06-02:14:15 UTC) contains only `HTTP Request: GET
  http://10.150.1.170:5003/status` polling lines (112 lines, all `200 OK`). No `Configure`,
  `ExecuteCommand`, `Pause`, `Resume`, or `Abort` reached the production F.A.S.T. tool at any
  point during the dry run.
- Teardown: `quit` written to the control FIFO shortly after the Task 2 operator reply
  (2026-10-15, after 09:14 WIB); PID 17097 exited within 2s without needing SIGTERM; `ss -ltn`
  shows nothing listening on port 40003; the control
  FIFO (`$HOME/.local/share/galago/dryrun/control`) is gone (removed by the harness on quit); the
  log file is kept per the plan. FAST-DRYRUN was removed from the workcell (operator-reported and
  independently confirmed via `tool.getAll`). No ufw rule was ever added for port 40003, so none
  needed removal.
- Result: PASS
  - All nine walkthrough items passed, the harness command sequence matched (transfer, pause,
    resume `is_tip_broken no`, abort with the operator's `return_liquid yes`, and a final resume
    `is_tip_broken no` after the transfer's reply), no command reached the production F.A.S.T.
    tool, and the harness and its workcell record were fully torn down. The two extra,
    unexplained operator-initiated commands at 09:11 are noted above but do not affect this
    result. The live scenarios (03-04 to 03-07) may proceed.

## LIVE-06a: Pause -> Resume -> SUCCESS

- Date/time: run window 2026-10-15T03:19:38Z-03:24:34Z UTC (2026-10-15 10:19:38-10:24:34 WIB).
  Within it: F.A.S.T transfer started 03:19:40.785Z (10:19:40 WIB); operator Pause sent
  03:20:15Z (10:20:15 WIB), state paused at 22% 03:20:17Z (10:20:17 WIB); operator Resume sent
  03:23:30Z (10:23:30 WIB), state running again 03:23:32Z (10:23:32 WIB); Transfer ended SUCCESS
  03:24:32.471Z (10:24:32 WIB).
- Operator: the user, at the instrument with the e-stop within reach, created the run, started it,
  pressed Pause once the head was moving, and Resumed with Tip broken? no. Operator replies:
  Task 1 "paused at 22% (start 10.19.38, pause 10.20.17, parameters as used, checklist confirmed)";
  Task 2 "done: resumed at 10.23.33 (tip broken started unselected: no)", later clarified: (1) the
  Tip broken? choice was blank/unselected with Confirm disabled, no was chosen; (2) no success
  popup appeared on the run page — the result showed as the step/queue status, not a popup; (3) a
  `tool_paused` prompt appeared during the pause showing the paused time with Resume/Abort options.
  Claude sent no command; Claude read `fast_status.py`, the F.A.S.T.log, the Pf400 log, the journal,
  and `galago-web`'s run/queue records (read-only `GET`/tRPC query calls only, no write).
- Transfer parameters: as used, F.A.S.T transfer source_deck 1, dest_deck 3, source_plate_id 1,
  dest_plate_id 1, A1 to A1, num_rows 1, num_cols 1, volume 50, tip_reuse fresh, expected_tray_id
  blank (0, Config value applies).
  - **Deviation flagged for review:** the operator ran protocol **"test"**, not the planned
    single-transfer "LIVE-06a" protocol, and used **num_rows 1** (plan proposed 8). Protocol
    "test" wraps the F.A.S.T transfer in two simulated Pf400 moves (location 100 before, location
    12 after) — Pf400 is the established simulated baseline, so these add no new motion risk. The
    operator's reply "parameters as used" did not list these; they were reconstructed read-only
    from `galago-web`'s run record (`run.id 154129ecbe01e7000`, `protocolName "test"`) rather than
    read as a literal operator statement of parameters. The plan permits reported value changes
    (D-10); this record flags the substitution so the user can object. The LIVE-06a claim still
    holds on the evidence below: one F.A.S.T transfer step stays open through the operator's Pause
    and the same step ends SUCCESS after Resume, independent of num_rows or the wrapping protocol.
- Decisions chosen: Tip broken? started unselected (blank, Confirm disabled) — confirmed by the
  operator; the operator chose **no** (tip intact).
- Log excerpt: production F.A.S.T.log, `~/.local/share/galago/trace_logs/1791974367/F.A.S.T.log`
  (local time):
  ```
  2026-10-15 10:19:40 | INFO | Running command Transfer
  2026-10-15 10:19:41 | INFO | fast run progress 0% (running)
  ...
  2026-10-15 10:20:15 | INFO | fast run progress 20% (running)
  2026-10-15 10:20:15 | INFO | Running command Pause
  2026-10-15 10:20:15 | INFO | HTTP Request: PUT http://10.150.1.170:5003/protocol/pause?hardPause=false "HTTP/1.1 200 OK"
  2026-10-15 10:20:17 | INFO | fast run progress 22% (paused)
  2026-10-15 10:23:30 | INFO | Running command Resume
  2026-10-15 10:23:30 | INFO | HTTP Request: PUT http://10.150.1.170:5003/protocol/resume?isTipBroken=false "HTTP/1.1 200 OK"
  2026-10-15 10:23:32 | INFO | fast run progress 25% (running)
  ...
  2026-10-15 10:24:32 | INFO | fast run progress 100% (idle)
  2026-10-15 10:24:32 | DEBUG | ExecuteCommand Response: response: SUCCESS
  ```
  Note: the production adapter logs no separate `ExecuteCommand Response` text line for the Pause
  or Resume control commands themselves; their success is the instrument's HTTP 200 OK plus the
  observed state change (paused at 22%, running again at 25%) — this applies symmetrically to both
  control commands, not just Resume, and matches 03-DEPLOY.md's documented adapter behavior.
- Final step result: the Transfer's own response line, `ExecuteCommand Response: response: SUCCESS`
  at 10:24:32 WIB (03:24:32.471Z), for the same Transfer opened at 10:19:40 WIB — no second
  Transfer or retry in the window. The run page showed no success popup (operator-confirmed); the
  result was reflected in the step/queue status returning to completed, matching `galago-web`'s
  queue record for this command (`queueId 104`, `status COMPLETED`, `completedAt 03:24:32.471Z`,
  the same instant as the log's SUCCESS line).
- Queue state: `galago-web` run `154129ecbe01e7000` (protocol "test"), `commandQueue.getAll`
  (read-only tRPC query) shows all 3 steps COMPLETED: Pf400 move (`queueId 103`)
  `startedAt 03:19:38.258Z` -> `completedAt 03:19:39.270Z`; F.A.S.T transfer (`queueId 104`)
  `startedAt 03:19:40.785Z` -> `completedAt 03:24:32.471Z`; Pf400 move (`queueId 105`)
  `startedAt 03:24:33.973Z` -> `completedAt 03:24:34.985Z`. The Pf400 log independently confirms
  `Running command Move` / `ExecuteCommand Response: response: SUCCESS` at 10:19:38-10:19:39 WIB
  and 10:24:33-10:24:34 WIB — the queue advanced past the F.A.S.T. step immediately after its
  SUCCESS, meaning the step stayed open through the entire pause and ended with the run's real
  outcome, not an early/false completion.
- Control commands in window: window 10:17:40-10:26:33 WIB (2 min before the reported start to
  2 min after the reported end). Counts: Transfer=1, Pause=1, Resume=1, Abort=0 — matches the
  operator's reported actions exactly, all operator-sent: yes. `journalctl --user -u galago-tools
  --since "2026-10-15 10:17:40" --until "2026-10-15 10:26:33"` shows no entries (no tool restart).
  `systemctl --user show galago-tools -p MainPID` -> `4044033`, unchanged from the post-deploy
  value throughout.
  - Correction (orchestrator, after the record was written): MainPID shows only the manager
    process. The tool servers did restart shortly **before** this window, without a service
    restart. The journal shows the manager stopping F.A.S.T. and Tool Box at 09:59:58 WIB
    (requests from `10.150.1.89`, i.e. the `:8081` manager page) and starting Pf400, F.A.S.T. and
    Tool Box again at 10:16:36 WIB. The new F.A.S.T. server PID is `727894` and the new Pf400
    PID is `727872`, both children of `4044033`. The operator then reconnected F.A.S.T. at
    10:16:52 WIB (`Received configuration` with host `10.150.1.170`, port 5003,
    `expected_tray_id` 90, no `simulated`).
  - That reconnect was 2 min 46 s before the run started (10:19:38). It ran the same deployed
    code (editable install of this tree, core `b30b38d`), so this result stands.
  - The restart also overwrote `F.A.S.T.log` in place. Production-log lines from before
    10:16:36 (the dry-run window, the 02-UAT runs) now survive only in the records already
    written.
- Screenshots: none provided.
- D-11 criteria:
  - PAUSED with a percent after Pause: `fast_status.py --port 40001` polled at 10:22:35 WIB during
    the pause returned `status BUSY`, `run_state.state paused`, `percent 22.0`,
    `pause.since 2026-10-15T03:20:17Z`, `errorName NoError`, `isHardPause false`; the F.A.S.T.log
    shows the matching `fast run progress 22% (paused)` line; the operator confirmed a
    `tool_paused` prompt appeared showing the paused time with Resume/Abort options. Observed: met.
  - The step stayed open while paused: no `ExecuteCommand Response` line for the Transfer between
    `Running command Transfer` (10:19:40 WIB) and the SUCCESS response (10:24:32 WIB); exactly one
    `Running command Transfer` in the window; `commandQueue.getAll` shows the F.A.S.T. transfer
    (`queueId 104`) was the only step not yet `COMPLETED` while `queueId 103` (the preceding Pf400
    move) had already completed at 10:19:39 WIB. Observed: met.
  - State returned to running after Resume: `Running command Resume` at 10:23:30 WIB (HTTP PUT
    `.../protocol/resume?isTipBroken=false` -> 200 OK) followed by `fast run progress 25%
    (running)` at 10:23:32 WIB, while the Transfer was still open (no response yet). Observed: met.
  - The same step ended SUCCESS: the same Transfer (one `Running command Transfer` in the whole
    window) ends with `ExecuteCommand Response: response: SUCCESS` at 10:24:32 WIB;
    `commandQueue.getAll` shows the same `queueId 104` COMPLETED at `03:24:32.471Z`, the identical
    instant; no second Transfer or retry appears anywhere in the window. Observed: met.
  - No control command the operator did not send: window counts Pause=1, Resume=1, Abort=0, exactly
    matching the operator's reported actions; `journalctl` shows no tool restart in the window;
    `systemctl` MainPID stayed `4044033` throughout (no restart, so no other command source is
    possible). Observed: met.
- Result: PASS
  - All five D-11 criteria hold on read-only evidence from the production F.A.S.T.log, Pf400 log,
    `fast_status.py`, the journal and `galago-web`'s queue record; the control-command window
    matches the operator's reported actions exactly (Pause 1, Resume 1, Abort 0); `galago-tools`
    did not restart (`journalctl` empty, MainPID unchanged at `4044033`). The one deviation
    (protocol "test" with num_rows 1, instead of the planned single-transfer "LIVE-06a" protocol
    with num_rows 8) is flagged above for the user's review but does not affect this result — the
    F.A.S.T transfer step itself (the thing D-11 tests) stayed open through the operator's Pause
    and ended SUCCESS after Resume, regardless of num_rows or the wrapping Pf400 moves. LIVE-06a
    is half of requirement LIVE-06; LIVE-06b (Pause -> Abort) is a separate scenario in plan 03-06
    and is not addressed by this record.

## LIVE-05: Deck 3 empty -> prompt -> fix deck -> Resume -> SUCCESS

(Not run — plan 03-05 fills this section.)

## LIVE-06b: Pause -> Abort -> aborted by operator, queue FAILED

(Not run — plan 03-06 fills this section.)

## LIVE-07: galago-web restart mid-run -> tool-page recovery

(Not run — plan 03-07 fills this section.)

## Safety invariant audit

(Not run — a later plan in this phase fills this section.)

## Flagged assumptions

- **A-EDGE-LIVE-04** (edge-probe fallback, `unclassified` / `unresolved`): deploy edge cases
  were not auto-classified. Handled explicitly, not silently: plan 03-01 stops the deploy on
  any failed check and rolls back in reverse order only on the user's go-ahead; plan 03-02
  compared the Step 3 cached-rebuild finding against the reconnect host's pre-deploy record
  rather than assuming it, stopped on the finding, and proceeded only after the user's explicit
  "No cache rebuild" decision.
- **A-EDGE-LIVE-05** (edge-probe fallback, `unclassified` / `unresolved`): the instrument's
  exact `eventPayload` shape for the deck-3-empty pause is not assumed; plan 03-05's record
  quotes both the raw payload and the rendered text. Plan 03-03's dry run also exercises the UI
  paths this scenario uses, without hardware.
- **A-EDGE-LIVE-06** (edge-probe fallback, `unclassified` / `unresolved`): pause/resume edges
  were not auto-classified. Plan 03-04 checks the step stays open and ends with the run's real
  outcome, stopping on anything else; plan 03-06 treats the F.A.S.T.log as the authoritative
  source for the step's reply if the run view shows no error text (galago-core debt F3, out of
  scope here), and the record says so. Plan 03-03's dry run also exercises these UI paths
  without hardware.
- **A-EDGE-LIVE-07** (edge-probe fallback, `unclassified` / `unresolved`): after a
  `galago-web` restart mid-run, the queue is assumed not to re-dispatch the held step (design
  section 8, not re-verified by probe); plan 03-07 checks for any new `Transfer` command after
  the restart and stops if one appears. Plan 03-03's dry run also exercises these UI paths
  without hardware.
- **Edge-probe fallback accounting for the phase:** 4 items surfaced (A-EDGE-LIVE-04 to 07), 0
  authored into truths as resolved edges, all 4 carried as flagged assumptions here, each with
  the plan that handles it.
- **RESEARCH A1:** a throwaway stdin-driven harness script is the right shape for driving
  `simulate_pause` during the dry run (no existing prior art confirms this exact approach) —
  low risk, disposable dev-only script; plan 03-03 owns this.
- **RESEARCH A2:** galago-core's UAT test 5 (deck-3/pause-prompt) being satisfied by this
  phase's LIVE-05 scenario is a reasonable cross-repo inference, not something either repo's
  planning doc states explicitly as linked — low risk; worst case the user re-runs galago-core's
  UAT test 5 separately.
- **RESEARCH A3:** ufw rules for ports 40001/11010/3010 are already correctly configured (not
  re-verified via `sudo ufw status`, which requires a password unavailable non-interactively) —
  low-to-medium risk in principle, but plan 03-02's Step 3 checks (both the cached and the
  no-cache attempt) confirmed the container reaches `host.docker.internal:40001` directly,
  resolving this assumption for the deploy itself; no new port was introduced.
