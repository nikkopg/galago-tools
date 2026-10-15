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
| LIVE-05 | LIVE-05: Deck 3 empty → prompt → fix deck → Resume → SUCCESS | PASS | `## LIVE-05` below — rerun after the D-14 fix (galago-core `ad87ea5`, galago-web `b0e183e`); first attempt (FAIL, "found -1") kept as history in the same section |
| LIVE-06 | LIVE-06b: Pause → Abort → aborted by operator, queue FAILED | PASS | `## LIVE-06b` below — scored rerun after the D-14 fix (`7d77e23`, `201d987`); two earlier attempts (rehearsal, then the wording-defect attempt) kept as history in the same section |
| LIVE-07 | LIVE-07: galago-web restart mid-run → tool-page recovery | PASS | `## LIVE-07` below — scored rerun after the D-14 queue-fix redeploy (galago-core `a0afd61`, `galago-web` `94bdfa7e`); attempt 1 (FAIL, the queue re-ran a previously operator-aborted LIVE-06b step) kept as history in the same section |

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

- Date/time: scored (rerun) run created 2026-10-15T04:05:50.517Z (11:05:50 WIB); within it: Transfer
  started 11:06:05 WIB, instrument paused itself at 11:06:13 WIB (0%, no operator Pause command),
  plate placed on deck 3 at an unreported time (operator did not give it; between 11:06:13 and
  11:06:27 WIB per the log), operator Resume sent 11:06:27 WIB, running again 11:06:27 WIB, Transfer
  ended SUCCESS 11:07:13 WIB. A superseded run, `15413f0fc681e7000`, was created
  2026-10-15T04:05:30Z (11:05:30 WIB) but sent no Transfer to the tool; the operator said "use the
  latest LIVE-05" without explaining it — recorded as superseded, excluded from the window below,
  likely created before the operator's 11:05:44 WIB F.A.S.T. reconnect.
  - **First attempt (FAIL, D-14)**: scenario run `154132ef8081e7000`, created
    2026-10-15T03:39:00.737Z (10:39:00 WIB), ran 03:39:04.840Z-03:44:52.654Z UTC
    (10:39:04-10:44:52 WIB), against galago-core HEAD `d4726ff` / galago-web image
    `sha256:10e7493...`. Scored FAIL on 2026-10-15 (commit `eb8ca7f`) because the rendered pause
    detail read "found -1" instead of "found none" — kept as history under each bullet below and
    under Result.
- Operator: the user, at the instrument with the e-stop within reach, reran protocol LIVE-05 after
  galago-core's none-plate fix (quick task 261015-f48, commits `07fb7fa`, `e6b0e97`, `ad87ea5`) and
  the `galago-web` rebuild that followed it, read the `tool_paused` prompt, placed plate 1 on deck 3,
  chose Tip broken? no, and pressed Resume. Operator replies, verbatim, in order: (1) "galago-core
  none plate fix is done, reran the LIVE-05. check"; (2) "reason was -645, yes they were unselected,
  use the latest LIVE-05, step completed"; (3), in answer to "Did the prompt read 'Deck 3: expected
  plate 1, found none'?": "yes it says none now". The operator did not report the deck-fix
  (plate-placed) time, and did not explicitly confirm deck 3 was empty at the rerun's start beyond
  the instrument pausing itself on -645 — both noted plainly, not assumed. Claude sent no command;
  Claude re-verified read-only the D-14 fix (galago-core commits, the deployed `galago-web` bundle,
  that `galago-tools` was not restarted) and read `fast_status.py` and the production F.A.S.T.log
  for the rerun window.
  - **First attempt (FAIL, D-14) operator record** (kept for history): the user created protocol
    LIVE-05, started a pre-scenario run forgetting to remove the destination plate from deck 3 first
    (so it ran to SUCCESS without pausing), then removed the plate and started the scenario run
    scored FAIL, read the prompt, placed plate 1, chose Tip broken? no, and pressed Resume. Operator
    replies then: Task 1 "prompt: WrongPlateType (-645) / deck3: expected plate 1, found -1 /
    nothing preselected: yes (start 10.39.00, protocol + parameters as used, checklist confirmed)";
    Task 2 "previous run i forgot to remove plate on the deck 3, thats why it suceeded. done, check
    my last run".
- Transfer parameters: as used in the rerun — F.A.S.T transfer source_deck 1, dest_deck 3,
  source_plate_id 1, dest_plate_id 1, A2 to A2, num_rows 8, num_cols 1, volume 10, tip_reuse fresh,
  expected_tray_id 0 (blank, Config value applies) — matching the plan's D-10 proposal exactly and
  identical to the first attempt's parameters.
  - **First attempt (FAIL, D-14)**: both the pre-scenario run `1541326eee81e7000` (deck 3 NOT empty,
    SUCCESS without pausing, excluded) and the scenario run `154132ef8081e7000` (deck 3 genuinely
    empty, scored FAIL) used these identical parameters; full detail preserved in git history
    (commit `eb8ca7f`).
- Decisions chosen: Tip broken? no (tip intact); nothing preselected (operator: "reason was -645,
  yes they were unselected" — confirming the Tip broken?/Return liquid? choices were unselected
  before Resume, same as the first attempt).
- Log excerpt: production F.A.S.T.log (local time), rerun scenario window only:
  ```
  2026-10-15 11:06:05 | INFO | Running command Transfer
  2026-10-15 11:06:05 | INFO | HTTP Request: POST http://10.150.1.170:5003/protocol/run "HTTP/1.1 200 OK"
  2026-10-15 11:06:05 | INFO | fast run progress 0% (running)
  2026-10-15 11:06:13 | INFO | fast run progress 0% (paused)
  ...
  2026-10-15 11:06:27 | INFO | Running command Resume
  2026-10-15 11:06:27 | INFO | HTTP Request: PUT http://10.150.1.170:5003/protocol/resume?isTipBroken=false "HTTP/1.1 200 OK"
  2026-10-15 11:06:27 | INFO | fast run progress 0% (running)
  ...
  2026-10-15 11:07:13 | DEBUG | ExecuteCommand Response: response: SUCCESS
  ```
  No "Running command Pause" line appears anywhere in the window — the instrument paused on its own
  before any aspirate, exactly as D-11 requires. No `fast_status.py` poll was taken while this run
  was paused (the pause payload was NOT snapshotted live this time) — stated plainly, not assumed
  (A-EDGE-LIVE-05). The -645/WrongPlateType reason rests on the operator's direct report ("reason
  was -645") plus the physical inference that the instrument paused itself at 0% before any aspirate
  with deck 3 reported empty at the start, consistent with the first attempt's directly-captured
  payload on the identical protocol and parameters (`errorCode -645.0`, `errorName "WrongPlateType"`,
  `eventPayload {"wrongDetection":[{"detectedPlateID":-1.0,"position":3.0,"expectedPlateID":1.0}],
  "trayType":1.0}`, quoted in the first-attempt history below).
  Rendered detail the operator reported from the `tool_paused` prompt this time: "yes it says none
  now", in direct answer to "Did the prompt read 'Deck 3: expected plate 1, found none'?" — i.e. the
  prompt now reads "Deck 3: expected plate 1, found none". This is the fixed rendering: galago-core's
  `pausePrompt.ts` (quick task 261015-f48, commits `07fb7fa`/`e6b0e97`/`ad87ea5`, HEAD `ad87ea5`,
  2026-10-15 11:00:07 WIB) adds `isNoPlateDetected`, which maps `null`, `undefined`, `""`, `-1` and
  `"-1"` to "none" (unit tests added); the deployed `galago-web` bundle was verified (read-only) to
  carry the fix: `docker exec galago-web grep -o '.\{0,40\}-1===r.\{0,40\}'
  /app/.next/static/chunks/pages/runs-8bc5bbafd0ab0b33.js` shows the bundle contains
  `-1===r||"-1"===r?"none"`.
  - **First attempt (FAIL, D-14)**: production F.A.S.T.log, scenario run only:
    ```
    2026-10-15 10:39:04 | INFO | Running command Transfer
    2026-10-15 10:39:05 | INFO | fast run progress 0% (running)
    2026-10-15 10:39:13 | INFO | fast run progress 0% (paused)
    ...
    2026-10-15 10:44:03 | INFO | Running command Resume
    2026-10-15 10:44:03 | INFO | HTTP Request: PUT http://10.150.1.170:5003/protocol/resume?isTipBroken=false "HTTP/1.1 200 OK"
    2026-10-15 10:44:04 | INFO | fast run progress 0% (running)
    ...
    2026-10-15 10:44:52 | INFO | fast run progress 100% (idle)
    2026-10-15 10:44:52 | DEBUG | ExecuteCommand Response: response: SUCCESS
    ```
    `fast_status.py` polled live at 10:41:44 WIB during the pause (A-EDGE-LIVE-05):
    ```json
    {"status":"BUSY","run_state":{"percent":0.0,"state":"paused","pause":{"percent":0.0,"since":"2026-10-15T03:39:13.318197+00:00","errorName":"WrongPlateType","errorCode":-645.0,"eventPayload":{"wrongDetection":[{"detectedPlateID":-1.0,"position":3.0,"expectedPlateID":1.0}],"trayType":1.0}}}}
    ```
    Rendered detail then: "deck3: expected plate 1, found -1" — the sentinel `-1` stringified
    literally instead of mapping to "none"; root cause and fix are in `03-DEPLOY.md`'s "D-14
    redeploy (LIVE-05 fix)" subsection.
- Final step result: the Transfer's own response line, `ExecuteCommand Response: response: SUCCESS`
  at 11:07:13 WIB, for the same Transfer opened at 11:06:05 WIB (one `Running command Transfer` in
  the rerun window, no retry, no second step).
  - **First attempt (FAIL, D-14)**: `ExecuteCommand Response: response: SUCCESS` at 10:44:52 WIB for
    the Transfer opened 10:39:04 WIB; `commandQueue.getAll` independently confirmed `queueId 107`,
    `runId 154132ef8081e7000`, COMPLETED at the identical instant (kept for history; that queue entry
    no longer exists — see Queue state below).
- Queue state: `galago-web` `commandQueue.getAll` (read-only tRPC query) is now empty for both the
  rerun and the first attempt — the queue was cleared since the first attempt's record was made — so
  it cannot be used as evidence for the rerun; stated plainly rather than claiming queue evidence
  that is no longer available. The rerun's SUCCESS is instead evidenced by the F.A.S.T.log's
  `ExecuteCommand Response: response: SUCCESS` line and `fast_status.py` reporting `READY`/idle
  immediately after.
  - **First attempt (FAIL, D-14)**: `commandQueue.getAll` then showed pre-scenario run
    `1541326eee81e7000` `queueId 106` COMPLETED and scenario run `154132ef8081e7000` `queueId 107`
    COMPLETED, matching the log exactly (kept for history).
- Control commands in window: rerun window 11:04:05-11:09:13 WIB (2 min before the rerun Transfer's
  start to 2 min after its end). Counts in the window: Transfer=1, Pause=0, Resume=1, Abort=0 —
  matches the operator's reported actions exactly (no Pause command — the instrument paused on its
  own; one Resume, operator-sent), all operator-sent: yes. `journalctl --user -u galago-tools` shows
  no entries in the window (no tool restart, consistent with the D-14 redeploy note that
  `galago-tools` was not restarted); `systemctl --user show galago-tools -p MainPID` -> `4044033`,
  unchanged; the F.A.S.T. listener on port 40001 is still PID `727894` — no tool-server restart
  either.
  - **First attempt (FAIL, D-14)**: window 10:37:04-10:46:52 WIB, Transfer=1, Pause=0, Resume=1,
    Abort=0, same MainPID `4044033` and listener PID `727894` throughout (kept for history).
- Screenshots: none provided (neither attempt).
- D-11 criteria:
  - The instrument pauses itself with WrongPlateType (-645), no "Running command Pause" in the
    window: Observed: met. The F.A.S.T.log shows `fast run progress 0% (paused)` at 11:06:13 WIB
    immediately after the Transfer started, with no `Running command Pause` line anywhere in the
    window; the operator directly reported "reason was -645". No live `fast_status.py` poll was
    taken during this pause (unlike the first attempt) — stated plainly; the -645/WrongPlateType
    attribution rests on the operator's report plus the physical inference (self-pause at 0%
    pre-aspirate, deck 3 reported empty) and is consistent with the first attempt's
    directly-captured payload on the identical parameters.
  - The pause's eventPayload names deck position 3, expected plate 1, detected none: not
    independently re-captured this run (no live snapshot taken). The first attempt's
    directly-captured payload on the identical protocol/parameters was
    `{"wrongDetection":[{"detectedPlateID":-1.0,"position":3.0,"expectedPlateID":1.0}],
    "trayType":1.0}` — position 3 and expectedPlateID 1 named correctly, `detectedPlateID` the
    sentinel `-1`. The fix (`isNoPlateDetected`) now maps that same `-1` sentinel to "none" at
    render time, confirmed present in the deployed bundle. Observed this run: the rendered text is
    "none" (operator-confirmed), consistent with the fixed mapping applied to the same underlying
    sentinel; not re-verified from a fresh raw payload.
  - The `tool_paused` prompt shows the reason (WrongPlateType (-645)) and "Deck 3: expected plate 1,
    found none", with nothing preselected: Observed: **met**. The operator reported the reason
    correctly ("reason was -645") and, asked directly "Did the prompt read 'Deck 3: expected plate
    1, found none'?", replied "yes it says none now"; nothing preselected ("yes they were
    unselected"). This reverses the first attempt's sole failing criterion ("found -1"), with the
    fix verified present in the deployed `galago-web` bundle (`-1===r||"-1"===r?"none"` in
    `/app/.next/static/chunks/pages/runs-8bc5bbafd0ab0b33.js`).
  - After the operator places plate 1 on deck 3 and resumes with Tip broken? no, the same step ends
    SUCCESS: Observed: met. Exactly one `Running command Transfer` in the rerun window (11:06:05
    WIB), one `Running command Resume` (11:06:27 WIB, HTTP PUT
    `.../protocol/resume?isTipBroken=false` -> 200 OK), and the same Transfer's `ExecuteCommand
    Response: response: SUCCESS` at 11:07:13 WIB; no retry, no second step.
  - No control command the operator did not send: Observed: met. Window counts Transfer=1, Pause=0,
    Resume=1, Abort=0, exactly matching the operator's reported actions; `journalctl` shows no tool
    restart in the window; `systemctl` MainPID stayed `4044033` and the F.A.S.T. listener PID stayed
    `727894` throughout.
- Result: PASS
  - Rerun after the D-14 fix: galago-core `ad87ea5` (quick task 261015-f48), `galago-web` image
    `b0e183e` (built 2026-10-15 11:02:27 WIB, container created 2026-10-15T04:02:31Z), `galago-tools`
    unrestarted (MainPID `4044033`, F.A.S.T. listener PID `727894`). Every D-11 criterion now holds:
    the reason -645 is shown (operator-reported); the detail line reads "Deck 3: expected plate 1,
    found none" (operator-observed on the fixed build; the fix is verified present in the deployed
    bundle); nothing is preselected; after Resume with tip intact "no", the SAME step ended SUCCESS,
    with no retry and no second step; no control command the operator did not send. Two caveats
    carried forward honestly rather than assumed away: no `fast_status.py` snapshot was taken while
    this run was paused (A-EDGE-LIVE-05 — the -645 reason and payload shape rest on the operator's
    report plus consistency with the first attempt's directly-captured payload on identical
    parameters, not a fresh snapshot), and the operator did not explicitly state deck 3 was empty at
    the rerun's start beyond the instrument pausing itself on -645. This evidence also demonstrates
    the 2026-10-12 incident's recovery behavior that this milestone exists to prove, and also covers
    galago-core 02-UAT test 5 (deferred there to this phase; RESEARCH A2, `03-DEPLOY.md` "Deferred
    galago-core 02-UAT items").
  - **First attempt (FAIL, D-14)**: scenario run `154132ef8081e7000`, scored FAIL on 2026-10-15
    (commit `eb8ca7f`) because the rendered pause detail read "deck3: expected plate 1, found -1"
    instead of "Deck 3: expected plate 1, found none" — galago-core's `pausePrompt.ts`
    `describeWrongDetectionEntry` (`controller/components/runs/pausePrompt.ts:203-207`, as it stood
    before the fix) mapped only `null`/`undefined`/`""` to "none" and otherwise stringified the raw
    value, so the instrument's `-1` sentinel rendered literally. Every other D-11 criterion held on
    that attempt too (self-pause, no Pause command, correct reason text, nothing preselected,
    SUCCESS after the deck fix and Resume with one Transfer/one Resume/no retry, and control
    commands matching the operator's actions exactly). galago-tools and `fast-mcp` were not
    implicated: the adapter passed the instrument's `eventPayload` through unchanged; the bug was
    solely in galago-core's plain-language rendering of the `-1` sentinel. The fix (quick task
    261015-f48, galago-core commits `07fb7fa`/`e6b0e97`/`ad87ea5`) and the `galago-web` redeploy that
    followed are recorded in `03-DEPLOY.md`'s "D-14 redeploy (LIVE-05 fix)" subsection.
## LIVE-06b: Pause -> Abort -> aborted by operator, queue FAILED

- Date/time: scored rerun — run `154151287281e7000` created 2026-10-15T04:45:02.053Z (11:45:02
  WIB); within it: Transfer started 04:45:03.564Z (11:45:03 WIB), operator Pause sent 11:45:29
  WIB (12% paused at 11:45:30 WIB), operator Abort sent 11:46:12 WIB (returnLiquid=false),
  ERROR_FROM_TOOL at 11:46:13 WIB (`failedAt` 04:46:13.158Z). All times 2026-10-15 WIB, galago-web
  image `b0e183e5513d11f80494e83d214f14c42dcbe8931d4616aee995f5ec8271f317`, `galago-tools`
  post-redeploy (MainPID `836290`, F.A.S.T. listener `836333`).
  - **Attempt 1 (rehearsal, not scored)**: run `154147d89501e7000`, created 04:24:41.514Z
    (11:24:41 WIB). The protocol had only the Transfer step — the `get_status` step was missing —
    so this attempt could not show the later step failing to run, and is not scored. Transfer
    started 11:25:03 WIB, Pause sent 11:25:27 WIB (12% paused at 11:25:31 WIB), Abort sent
    11:27:32 WIB (`returnLiquid=false`), ERROR_FROM_TOOL at 11:27:33 WIB with
    `error_message: "run aborted by operator at 12%: NoError (0)"`. `fast_status.py` polled live
    at 11:26:18 WIB during the pause: `status BUSY`, `run_state.percent 12.0`,
    `run_state.state paused`, `pause.errorName "NoError"`, `pause.errorCode 0`,
    `pause.isHardPause false`, `pause.since "2026-10-15T04:25:31+00:00"`. Queue (`queueId 110`)
    went FAILED with error `"Error from tool \"F.A.S.T\": run aborted by operator at 12%:
    NoError (0)"`.
  - **Attempt 2 (not scored — exposed the D-14 defect)**: run `15414b331c01e7000`, with both
    Transfer and `get_status` steps (protocol fixed). A second run, `15414b1f8301e7000`, created
    04:31:51Z, sent nothing to the tool and was superseded. Transfer started 11:32:02 WIB, Pause
    sent 11:32:38 WIB (22% paused at 11:32:39 WIB), Abort sent 11:32:46 WIB
    (`returnLiquid=false`), ERROR_FROM_TOOL at 11:32:47 WIB with
    `error_message: "run aborted by operator at 22%: NoError (0)"`. Queue: Transfer (`queueId 113`)
    FAILED with error `"Error from tool \"F.A.S.T\": run aborted by operator at 22%: NoError (0)"`;
    `get_status` (`queueId 114`) stayed CREATED and never ran — no `Running command GetStatus`
    appears anywhere in the F.A.S.T.log, even 8+ minutes later. Operator's answer for this attempt,
    verbatim: "i didnt return liquid, abort disabled" — Return liquid was **no**, and Abort stayed
    disabled until a choice was made (nothing preselected). This attempt was not scored because of
    the `": NoError (0)"` suffix, a wording defect (see D-14 fix below).
- Operator: the user, at the instrument with the e-stop within reach, created the two-step
  LIVE-06b protocol (Transfer then `get_status`), started each run, pressed Pause once the head
  was moving, and Aborted with a Return-liquid choice of their own each time. Claude sent no
  command to any tool on any attempt; Claude read `fast_status.py`, the production F.A.S.T.log,
  `galago-web`'s run/queue records (read-only `GET`/tRPC query calls only) and the journal.
  - **Precondition note:** the plan's Task 1 precondition check `grep -c 'run aborted by operator
    at' tools/fast/server.py` expects `1` but, re-run now, prints `3` — `tools/fast/server.py:330`
    and `:884` are docstring occurrences of the same phrase, and only `:361` is the code line that
    produces the wording. The wording itself is unchanged in substance; the count was a planning
    miscount, not a sign of drift, recorded here plainly per the continuation instructions.
  - **D-14 fix (found live during attempt 2)**: the instrument reports an operator abort as
    `error_name NoError` / `error_code 0`, not as empty/`None` fields, so
    `tools/fast/server.py`'s `_message_for` appended the `": [outcome]"` suffix even though D-09/
    D-11 expect it only for a real error. Fixed in this repo: `7d77e23` (RED test,
    `test_operator_abort_with_no_error_report_has_no_suffix`-shaped coverage in
    `tools/tests/fast_test.py`) then `201d987` (fix: `_is_no_error` now treats a `NoError`/`0`
    report with no message as no error, so the wording reads `"run aborted by operator at <p>%"`
    with no suffix; real errors keep their suffix; the non-operator abort wording is unchanged).
    Gate, re-run fresh for this record: `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash
    bin/make proto test` exit 0, **144 tests passed**; `ruff check tools/fast/server.py
    tools/tests/fast_test.py` → "All checks passed!"; `mypy tools/fast/server.py` → "Success: no
    issues found in 1 source file". `grep -n 'run aborted by operator at'
    tools/fast/server.py` now shows lines 330 (docstring), 361 (code), 884 (docstring) — 3 matches,
    1 code line, consistent with the precondition note above.
  - **Redeploy (adapter fix only, no proto/schema change)**: on the user's literal "go",
    `systemctl --user restart galago-tools` at 2026-10-15T04:40:59Z (11:40:59 WIB). Journal:
    manager killed the old Pf400 (`727872`) and F.A.S.T. (`727894`) processes at 11:40:59-11:41:00
    WIB, then started fresh: `MainPID` `4044033` -> `836290`, active since `2026-10-15 11:41:00
    WIB`; new F.A.S.T. listener PID `727894` -> `836333`; new Pf400 PID `836310`. New trace-log
    folder `~/.local/share/galago/trace_logs/1792039261/`; `F.A.S.T.log` line 2:
    `2026-10-15 11:41:02 | INFO | fast server started, listening on 40001` — no traceback.
    `fast_status.py --port 40001` read `NOT_CONFIGURED` immediately after (expected, awaiting
    reconnect).
    - **Connect-all-tools incident (galago-core observation, non-blocking, out of scope)**: at
      11:42:04 WIB a "Connect all tools" action from the `:8081` manager page sent F.A.S.T. an
      **empty** config (`fast {\n}`); the log shows
      `2026-10-15 11:42:04 | ERROR | Failed to configure Tool=F.A.S.T-fast: Config.host is
      required`, and `fast_status.py` would have read `FAILED` (not re-polled live at that
      instant; the next polled read is the post-reconnect `READY` below). Pf400 failed the same
      way (`"[Errno -2] Name or service not known"`, confirmed still present in its
      `error_message` field at time of writing). Nothing moved. Root cause (galago-core, out of
      scope for this phase): `ToolsComponent.tsx` sends `{[tool.type]: tool.config}` to "Connect
      all", but the stored config is already wrapped as `{fast:{...}}`, so the nested key is
      dropped and the handler receives an empty object. Recorded as a galago-core observation per
      the continuation instructions, not fixed here.
    - **Reconnect**: the operator reconnected F.A.S.T. from its own tool page at 11:44:12 WIB
      (`Received configuration`: host `10.150.1.170`, port 5003, `expected_tray_id` 90, no
      `simulated` flag — real mode) and reconnected Pf400 with Simulate ON (status `SIMULATED`,
      this environment's established baseline per `03-DEPLOY.md`'s Pre-deploy record, not a new
      finding).
- Transfer parameters: the two-step protocol as used on every attempt — F.A.S.T transfer
  source_deck 1, dest_deck 3, source_plate_id 1, dest_plate_id 1, A3 to A3 (column 3), num_rows 8,
  num_cols 1, volume 50, tip_reuse fresh, expected_tray_id 0 (blank, Config value applies); then
  F.A.S.T get_status (read-only, no args) — matching the plan's D-10 proposal exactly. Attempt 1's
  protocol lacked the `get_status` step (fixed before attempt 2).
- Decisions chosen: Return liquid? **no** on every attempt (`returnLiquid=false` in every Abort
  request). The operator's reply for attempt 2, verbatim: "i didnt return liquid, abort disabled"
  — confirming Return liquid? started unselected and Abort stayed disabled until a choice was
  made. The operator's reply for the scored rerun: "paused at 12%, start 11.45.03, paused
  11.45.30, return-liquid no, run page shows error_from_tool" — the choice (no) is restated, but
  the operator did not re-state "unselected" for this specific run. No `fast_status.py` snapshot
  was taken during this run's pause either. Both points are carried forward honestly rather than
  assumed: the "nothing preselected" behavior is the same dialog on the same `galago-web` build
  (`b0e183e`) that attempt 2 already confirmed unselected minutes earlier against the identical
  code path, so the record relies on that confirmation rather than a fresh one for the rerun
  (A-EDGE-LIVE-06-style honesty, not a new assumption).
- Log excerpt: scored rerun, production F.A.S.T.log (local time; the production log was
  overwritten in place by the 11:40:59 WIB restart — this excerpt is from a backup copy taken
  before the overwrite would have destroyed it, `fast-log-20261015T1147-newadapter.log`, itself a
  copy of the post-redeploy `~/.local/share/galago/trace_logs/1792039261/F.A.S.T.log`):
  ```
  2026-10-15 11:41:02 | INFO | fast server started, listening on 40001
  2026-10-15 11:44:12 | INFO | Received configuration: toolId: "F.A.S.T" ...
  2026-10-15 11:45:03 | INFO | Running command Transfer
  2026-10-15 11:45:04 | INFO | fast run progress 0% (running)
  ...
  2026-10-15 11:45:29 | INFO | Running command Pause
  2026-10-15 11:45:30 | INFO | fast run progress 12% (paused)
  2026-10-15 11:46:12 | INFO | Running command Abort
  2026-10-15 11:46:13 | INFO | fast run progress 12% (aborted)
  2026-10-15 11:46:13 | DEBUG | ExecuteCommand Response: response: ERROR_FROM_TOOL
  error_message: "run aborted by operator at 12%"
  ```
  No `Running command GetStatus` line appears anywhere in this log (0 occurrences, re-checked at
  time of writing) — the `get_status` step never ran.
  - **Attempt 1** (backup `fast-log-20261015T1129.log`):
    ```
    2026-10-15 11:25:03 | INFO | Running command Transfer
    2026-10-15 11:25:27 | INFO | Running command Pause
    2026-10-15 11:25:31 | INFO | fast run progress 12% (paused)
    2026-10-15 11:27:32 | INFO | Running command Abort
    2026-10-15 11:27:33 | INFO | fast run progress 12% (aborted)
    2026-10-15 11:27:33 | DEBUG | ExecuteCommand Response: response: ERROR_FROM_TOOL
    error_message: "run aborted by operator at 12%: NoError (0)"
    ```
  - **Attempt 2** (backup `fast-log-20261015T1140.log`):
    ```
    2026-10-15 11:32:02 | INFO | Running command Transfer
    2026-10-15 11:32:38 | INFO | Running command Pause
    2026-10-15 11:32:39 | INFO | fast run progress 22% (paused)
    2026-10-15 11:32:46 | INFO | Running command Abort
    2026-10-15 11:32:47 | INFO | fast run progress 22% (aborted)
    2026-10-15 11:32:47 | DEBUG | ExecuteCommand Response: response: ERROR_FROM_TOOL
    error_message: "run aborted by operator at 22%: NoError (0)"
    ```
    No `Running command GetStatus` appears in this log either, including 8+ minutes after the
    abort (checked live at 11:40 WIB, before the restart).
- Final step result: the scored rerun's Transfer ends `ExecuteCommand Response: response:
  ERROR_FROM_TOOL` at 11:46:13 WIB with `error_message: "run aborted by operator at 12%"` (no
  suffix — the D-14 fix applied); `galago-web`'s `commandQueue.getAll` independently confirms
  `queueId 115`, `runId 154151287281e7000`, `status FAILED`,
  `error.message "Error from tool \"F.A.S.T\": run aborted by operator at 12%"`,
  `failedAt "2026-10-15T04:46:13.158Z"` — the identical instant and identical wording (no
  suffix). The operator confirmed: "run page shows error_from_tool" — the run view did show error
  text this time, so the A-EDGE-LIVE-06 fallback (treating the log as authoritative when the run
  view shows nothing) was not needed for this record.
  - **Attempt 1**: ERROR_FROM_TOOL "run aborted by operator at 12%: NoError (0)" at 11:27:33 WIB;
    not scored (protocol lacked `get_status`).
  - **Attempt 2**: ERROR_FROM_TOOL "run aborted by operator at 22%: NoError (0)" at 11:32:47 WIB;
    not scored (wording defect, fixed by D-14 above).
- Queue state: `galago-web` run `154151287281e7000` (protocol `LIVE-06b`, `protocolId 4`):
  `commandQueue.getAll` (read-only tRPC query, re-checked at time of writing) shows `queueId 115`
  (transfer) `status FAILED`, `startedAt 04:45:03.564Z`, `failedAt 04:46:13.158Z`; `queueId 116`
  (get_status) `status CREATED` — never started, never completed. `commandQueue.state` (read-only
  tRPC query) reads `"FAILED"`. `GET http://localhost:3010/api/runs` independently confirms the
  run record: `protocolName "LIVE-06b"`, two commands (`transfer` then `get_status`), the
  `get_status` command's top-level status still `CREATED` with no `startedAt`/`completedAt`.
  - **Attempt 1**: `queueId 110` (transfer only, single-step protocol) FAILED, matching the log.
  - **Attempt 2**: `queueId 113` (transfer) FAILED; `queueId 114` (get_status) CREATED — never
    ran, matching the log's absence of any `Running command GetStatus` line.
- Control commands in window: scored-rerun window 11:43:03-11:48:13 WIB (2 min before the
  Transfer's 11:45:03 WIB start to 2 min after the 11:46:13 WIB abort reply). Counts in the
  window: Transfer=1, Pause=1, Resume=0, Abort=1, GetStatus=0 — matches the operator's reported
  actions exactly (one Pause, one Abort, no Resume, and critically no GetStatus), all
  operator-sent: yes. `journalctl --user -u galago-tools --since "2026-10-15 11:43:03" --until
  "2026-10-15 11:48:13"` (re-checked) shows no tool-manager activity in that narrower window
  (the restart and reconnects all happened earlier, 11:40:59-11:44:12 WIB, well before this
  window opens) — no restart or reconfiguration occurred during the scored run itself.
  - **Attempt 1**: window 11:23:03-11:29:33 WIB (approx.), Transfer=1, Pause=1, Resume=0, Abort=1,
    GetStatus=0 (protocol had no `get_status` step).
  - **Attempt 2**: window 11:30:02-11:34:47 WIB (approx.), Transfer=1, Pause=1, Resume=0, Abort=1,
    GetStatus=0 — the later step never ran even though it existed in the protocol.
- Screenshots: none provided (any attempt).
- D-11 criteria: observed on the scored rerun, the one scored run per D-11's "one abort run is
  enough":
  - Return liquid? had no preselection: Observed: met (attempt 2's confirmation — "abort
    disabled [until chosen]" — on the identical `galago-web` build `b0e183e` and the same dialog;
    not re-confirmed verbatim for the scored rerun itself, carried forward honestly as a named
    caveat above rather than silently assumed).
  - The step ended ERROR_FROM_TOOL "run aborted by operator at [p]%": Observed: **met** —
    `ERROR_FROM_TOOL` at 11:46:13 WIB, `error_message "run aborted by operator at 12%"`, exactly
    the D-09/D-11 wording with no suffix, confirmed in both the F.A.S.T.log and
    `commandQueue.getAll`'s `error.message`.
  - The queue is FAILED: Observed: met — `commandQueue.state` reads `"FAILED"`; `queueId 115`
    status `FAILED`.
  - No later step ran: Observed: met — `queueId 116` (`get_status`) stayed `CREATED`; zero
    `Running command GetStatus` lines anywhere in the post-redeploy F.A.S.T.log.
  - The operator's choice is recorded: Observed: met — Return liquid `no`
    (`returnLiquid=false` in the Abort HTTP call), operator-confirmed ("return-liquid no").
  - No control command the operator did not send: Observed: met — window counts Transfer=1,
    Pause=1, Resume=0, Abort=1, GetStatus=0, exactly matching the operator's reported actions; no
    tool-manager restart/reconfiguration occurred inside the 11:43:03-11:48:13 WIB window itself
    (the redeploy and both Connect-all/reconnect events predate it).
  - **Non-blocking galago-core observation (out of scope)**: after the abort, the run page's Gantt
    timeline keeps drawing the Transfer bar out to its estimated duration instead of ending it at
    the failure. This does not affect the queue: galago-core's `command_queue.ts` `break`s out of
    its dispatch loop on a failed step (verified in code and in the state above — `queueId 116`
    never started). Recorded for the user's awareness; not fixed in this phase (galago-core debt,
    out of scope).
- Result: PASS
  - Every D-11 criterion holds on the scored rerun (`154151287281e7000`, protocol `LIVE-06b`,
    galago-web `b0e183e`, `galago-tools` post-redeploy MainPID `836290`/F.A.S.T. listener
    `836333`): Return liquid had no preselection (via attempt 2's confirmation on the same build
    and dialog); the step ended `ERROR_FROM_TOOL` "run aborted by operator at 12%" with no
    suffix; the queue is FAILED; the `get_status` step never ran; the operator's Return-liquid
    choice (no) is recorded; no control command the operator did not send appears in the window.
    D-11 states one scored abort run is enough. Two earlier attempts are kept as history above:
    attempt 1 (rehearsal, not scored — the protocol lacked the `get_status` step needed to prove
    "no later step runs") and attempt 2 (not scored — exposed a wording defect, D-14, where the
    instrument's `NoError`/`errorCode 0` abort report produced a `": NoError (0)"` suffix on the
    "aborted by operator" text). The defect was fixed in this repo (`7d77e23`, `201d987`), the gate
    re-ran green (144 tests, ruff clean, mypy clean), and `galago-tools` was redeployed
    (`systemctl --user restart galago-tools`, MainPID `4044033` -> `836290`) on the user's explicit
    "go" before this scored rerun. One non-blocking galago-core incident occurred during the
    redeploy window (an empty-config "Connect all tools" push, unrelated to this fix, recorded
    above as a galago-core observation) and was resolved by the operator reconnecting F.A.S.T.
    directly before the scored run. Caveats carried forward honestly: no live `fast_status.py`
    pause snapshot was taken during the scored rerun's pause (the log's "12% (paused)" line plus
    the operator's report are the evidence), and the operator did not re-state "unselected" for
    this specific run (attempt 2's confirmation on the identical build/dialog is cited instead).
    LIVE-06a (03-04, PASS) and LIVE-06b (this record, PASS) together satisfy requirement LIVE-06.
  - **Note added after LIVE-07 attempt 1 (2026-10-15 ~12:11 WIB, D-14):** this record's
    as-specified D-11 criteria held at the time they were written and this Result (PASS) is not
    retracted — it still reflects what D-11 asked LIVE-06b to prove. LIVE-07 attempt 1
    (`## LIVE-07` below) then showed, via `galago-web`'s queue (`controller/server/utils/
    SqliteQueue.ts` `fail()`/`startNext()`), that this run's aborted transfer (`queueId 115`)
    re-runs the next time the queue is started instead of staying FAILED and out of the way. After
    the galago-core fix lands, a LIVE-06b follow-up check is required: after an abort, starting a
    new run must not re-run the aborted step.
  - **LIVE-06b follow-up check (2026-10-15, ~14:18-14:19 WIB, D-14, after the galago-core queue fix
    and the `galago-web` rebuild below): PASS.** `galago-web` run `154197632481e7000` (protocol
    LIVE-06b): Transfer A5→A5, 8×1, 50 µL, fresh, followed by `get_status` — the same two-step
    shape as the scored rerun above. An earlier run, `154197193781e7000` (created
    2026-10-15T07:17:49Z), sent no command to the tool and was superseded. Sequence: 14:18:28 WIB
    Transfer started; 14:18:56 WIB operator Pause (12% paused at 14:18:57 WIB); 14:19:06 WIB
    operator Abort, `returnLiquid=false` (operator: "A done (return liquid: no)"),
    `ERROR_FROM_TOOL "run aborted by operator at 12%"` at 14:19:07 WIB; the queue went FAILED. The
    orchestrator read a `docker cp` copy of `/app/data/queue.db` (read-only): the
    `command_queue_2_queue` table held ONLY one row, `(121, position 1)` — LIVE-06b's `get_status`
    step. The aborted transfer, row 120, had been **dequeued** (its `commands` row stays FAILED),
    matching the galago-core fix: an accepted operator Abort now calls `fail(..., {dequeue: true})`,
    which removes the row from `_queue` so `startNext` cannot re-run it. The fix holds.
  - **FINDING (a) — aborted run's remaining steps stay queued (galago-core, read-only observation,
    not fixed here):** row 121 (LIVE-06b's `get_status`) sat at position 1 and would have run on
    the next queue start, ahead of a different run's own steps — the fix dequeues only the aborted
    step itself, not the rest of that run. Here it was a harmless `get_status`; in a real protocol,
    a later Transfer step of an aborted run would run when someone starts a different run next. The
    operator cleared the queue before starting LIVE-07 ("queed cleared before LIVE-07: yes"), so
    this finding was observed in the queue table but not exercised — no unintended motion occurred.
    **Operator workaround:** Clear All after any abort, before starting another run. Not a LIVE-06b
    failure — this run's own D-11 criteria, scored above, already held, and the thing this
    follow-up check exists to prove (the aborted step itself does not re-run) held exactly: row 120
    was dequeued, never restarted. Flagged as a blocking item for the phase close-out decision in
    plan 03-08 (see `## Flagged assumptions` below).

## LIVE-07: galago-web restart mid-run -> tool-page recovery

- Date/time: scored rerun — `galago-web` run `1541991a8101e7000` (protocol LIVE-07), queue row
  124: Transfer A6→A6, 8×1, 50 µL, fresh, expected_tray_id 0. F.A.S.T Transfer started 14:22:13 WIB
  (queue `startedAt` `2026-10-15T07:22:13.600Z`); operator Pause sent 14:23:06 WIB (46% paused at
  14:23:08 WIB); `docker restart galago-web` at 14:23:40 WIB (2026-10-15T07:23:40Z) on the
  operator's go-restart; `galago-web` running again and `/api/health` answering at 14:23:46 WIB
  (`docker inspect galago-web`'s `State.StartedAt 2026-10-15T07:23:41.137995454Z`, independently
  re-confirmed live by the orchestrator); tool-page Resume sent 14:24:06 WIB; instrument
  idle/SUCCESS at 14:24:50 WIB; tool-page `get_status` sent 14:24:56 WIB. All times 2026-10-15 WIB,
  `galago-web` image `sha256:94bdfa7e4dba1cc98923b096995f68a07e9aced6e5972e624a205bc0a3abe6ba`
  (the D-14 queue-fix rebuild — see `03-DEPLOY.md`'s "D-14 redeploy (queue re-run fix)"
  subsection), `galago-tools` unrestarted (MainPID `836290`, F.A.S.T. listener `867162`,
  unchanged from the attempt-1 baseline, independently re-confirmed live by the orchestrator).
  - **Attempt 1 (FAIL, D-14).** Baseline note: at 12:04:42 WIB (2026-10-15) the F.A.S.T. tool
    server itself restarted again with no `galago-tools` service restart (MainPID stayed `836290`;
    the F.A.S.T. listener PID went `836333` -> `867162`), overwriting `F.A.S.T.log` in place (line
    2 now reads the 12:04:42 restart) — most likely another `:8081` manager-page action, the same
    pattern as the restarts noted earlier in this document. F.A.S.T. was reconnected at 12:04:50
    WIB. Both happened before this scenario started, so the no-restart baseline for this attempt is
    listener `867162` (not the `836333` baseline recorded in `03-DEPLOY.md`'s LIVE-06b redeploy
    note). Scenario proper: `galago-web` run `15415a78d881e7000`, protocol `LIVE-07`, created
    `2026-10-15T05:05:22Z` (12:05:22 WIB); within it, the F.A.S.T Transfer started 12:05:34 WIB,
    operator Pause sent 12:05:55 WIB (paused at 5% per the log at 12:05:56 WIB — the operator's own
    reply reported 2%, a discrepancy flagged plainly rather than reconciled), `docker restart
    galago-web` at 12:07:27 WIB (2026-10-15T05:07:27Z) on the operator's go-restart, `galago-web`
    running again and `/api/health` answering at 12:07:32 WIB (2026-10-15T05:07:32Z), tool-page
    Resume sent 12:08:56 WIB, instrument idle/SUCCESS at 12:10:11 WIB, tool-page `get_status` sent
    12:10:33 WIB. Kept for history; commit `2eec866`.
- Operator: the user, at the instrument with the e-stop within reach, created the run, started it,
  paused it, and, after the galago-core queue fix landed and `galago-web` was rebuilt, authorized
  the restart. Replies, verbatim, in order: (1) "started"; (2) "run page show paused, go-restart";
  (3) "recovered: resume at 14.23, get_status completed, run page shows nothing, tip broken: no,
  queed cleared before LIVE-07: yes". **Discrepancy flagged plainly, not reconciled:** the
  operator's reported Resume time ("14.23") is about 43s before the F.A.S.T.log's "Running command
  Resume" line (14:24:06 WIB) — the same style of minor timing discrepancy already flagged on
  attempt 1 (2% vs 5% paused). Claude sent no motion or control command to any tool; the only
  command Claude ran that changed anything was `docker restart galago-web`, after the operator's
  literal go-restart. Claude read `fast_status.py`, the F.A.S.T.log, `docker inspect galago-web`,
  and `galago-web`'s queue record (read-only, via a `docker cp` copy of `/app/data/queue.db`)
  throughout.
  - **Attempt 1 (FAIL, D-14)**: the user, at the instrument with the e-stop within reach, created
    protocol LIVE-07, started the run, paused it, and authorized the restart. Replies, verbatim, in
    order: (1) "paused at 2%, start 12.05.30 paused 12.05.56, parameters as used, checklist
    confirmed"; (2) "go-restart"; (3) "done,check logs"; (4) "1. not sure which col it transfered
    to 2. run page shows no control after the restart, i was in the run recovery page when after
    the restart tho"; (5) "galago-core fix is on theway, tip broken was unselected". Claude sent no
    motion or control command to any tool; the only command Claude ran that changed anything was
    `docker restart galago-web`, after the operator's literal go-restart. Kept for history.
- Transfer parameters: as used — one F.A.S.T Transfer, source_deck 1, dest_deck 3,
  source_plate_id 1, dest_plate_id 1, A6 to A6 (column 6), num_rows 8, num_cols 1, volume 50 µL,
  tip_reuse fresh, expected_tray_id 0 (blank, Config value applies). The queue record confirms this
  run's own parameters executed this time (`source_start_col "6"`, matching the protocol record),
  unlike attempt 1, where the queue dispatched a different run's column-3 transfer.
  - **Attempt 1 (FAIL, D-14)**: one F.A.S.T Transfer, source_deck 1, dest_deck 3,
    source_plate_id 1, dest_plate_id 1, A4 to A4 (column 4), num_rows 8, num_cols 1, volume 50 µL,
    tip_reuse fresh, expected_tray_id 0 (blank, Config value applies) — matching the plan's D-10
    proposal exactly. This was the protocol's recorded parameters, not necessarily what the
    instrument physically did — see that attempt's Final step result and Queue state, kept for
    history below.
- Restart (D-12): `docker restart galago-web` run at 14:23:40 WIB (2026-10-15T07:23:40Z),
  authorized by the operator's literal "go-restart" reply, while `fast_status.py --port 40001`
  reported `BUSY`/`run_state.state paused` at 46% (`pause.errorName "NoError"`, `pause.errorCode
  0`, `pause.since "2026-10-15T07:23:08+00:00"`, `lastExecutedTask 15`, `isHardPause false`).
  `galago-web` reported running and `curl -sf http://localhost:3010/api/health` succeeded at
  14:23:46 WIB (`docker inspect galago-web`'s `State.StartedAt 2026-10-15T07:23:41.137995454Z`,
  independently re-confirmed by the orchestrator); the running image was the D-14 queue-fix
  rebuild (`sha256:94bdfa7e...`, built 14:05:18 WIB — see `03-DEPLOY.md`). Checks after the
  restart, all read-only:
  - `fast_status.py --port 40001` still read `BUSY`/`paused`, same 46% and the same `pause.since`
    — met (the orphaned Transfer still waited).
  - `systemctl --user show galago-tools -p MainPID` still read `836290` — met (no tool process
    was restarted by this command; independently re-confirmed by the orchestrator after the fact).
  - The F.A.S.T. listener stayed `867162` — met (same PID as the pre-scenario baseline;
    independently re-confirmed live: `ps` shows PID `867162` still running
    `tools.fast.server --port=40001` as a child of `836290`).
  - F.A.S.T.log: the Transfer opened at 14:22:13 WIB had no `ExecuteCommand Response` yet; no new
    "Running command Transfer" line appears between the restart and the Resume; no Pause, Resume
    or Abort line appears between the operator's 14:23:06 WIB Pause and the 14:24:06 WIB Resume —
    met (independently re-verified: `journalctl --user -u galago-tools --since
    "2026-10-15 14:20:13" --until "2026-10-15 14:26:56"` shows no entries — no tool-manager
    activity in this window either).
  - All Restart (D-12) checks passed; the mechanics this scenario exists to prove (an orphaned
    Transfer survives a `galago-web` restart and still holds the motion lock) held exactly as
    designed, this time against the queue-fixed build.
  - **Attempt 1 (FAIL, D-14) restart record**: `docker restart galago-web` run at 12:07:27 WIB
    (2026-10-15T05:07:27Z), authorized by the operator's literal "go-restart" reply, while
    `fast_status.py --port 40001` reported `BUSY`/`run_state.state paused` at 5%. `galago-web`
    reported running and `/api/health` succeeded at 12:07:32 WIB (2026-10-15T05:07:32Z); the
    running image was unchanged (`b0e183e...`, the same image LIVE-06b ran against). Every check
    (fast_status BUSY/paused 5%, MainPID `836290` unchanged, F.A.S.T. listener `867162` unchanged,
    no new Transfer/Pause/Resume/Abort line between the operator's Pause and the tool-page Resume)
    passed — the restart-and-recovery mechanics held completely even on the FAILing attempt. Kept
    for history.
- Decisions chosen: Resume (not the Abort fallback) from the F.A.S.T tool page's Run Recovery
  card; Tip broken? **no**. The operator did not restate "unselected" for this attempt; attempt 1
  confirmed the card started unselected ("tip broken was unselected"), and the card is unchanged
  by the queue-only fix (galago-core's D-14 fix touched only `SqliteQueue.ts`'s `fail`/
  `startNext`, not the tool page's Run Recovery UI), so that confirmation is cited here rather than
  re-stated fresh.
  - **Attempt 1 (FAIL, D-14)**: Resume (not the Abort fallback) from the F.A.S.T tool page's Run
    Recovery card; Tip broken? **no**, confirmed by the operator as started unselected ("tip broken
    was unselected"). Kept for history.
- Log excerpt: production F.A.S.T.log, `~/.local/share/galago/trace_logs/1792039261/F.A.S.T.log`
  (a copy taken for this record, `fast-log-20261015-live07-rerun.log`), local time, spanning
  before and after the restart:
  ```
  2026-10-15 14:22:13 | INFO | Running command Transfer
  2026-10-15 14:22:14 | INFO | fast run progress 0% (running)
  ...
  2026-10-15 14:23:06 | INFO | Running command Pause
  2026-10-15 14:23:08 | INFO | fast run progress 46% (paused)
  [docker restart galago-web at 14:23:40 WIB; running + /api/health OK at 14:23:46 WIB]
  2026-10-15 14:24:06 | INFO | Running command Resume
  2026-10-15 14:24:08 | INFO | fast run progress 46% (running)
  ...
  2026-10-15 14:24:50 | INFO | fast run progress 100% (idle)
  2026-10-15 14:24:50 | DEBUG | ExecuteCommand Response: response: SUCCESS
  2026-10-15 14:24:56 | INFO | Running command GetStatus
  2026-10-15 14:24:56 | DEBUG | ExecuteCommand Response: response: SUCCESS
  ```
  Exactly one "Running command Transfer" line appears in the whole rerun window (14:22:13 WIB,
  before the restart); no second or later Transfer line appears anywhere, including after the
  restart — independently re-confirmed by grepping `fast-log-20261015-live07-rerun.log`'s
  14:20:13-14:26:56 WIB window for "Running command Transfer" (count: 1).
  - **Attempt 1 (FAIL, D-14)**: production F.A.S.T.log, `fast-log-20261015-live07.log`, spanning
    before and after that restart:
    ```
    2026-10-15 12:04:42 | INFO | fast server started, listening on 40001
    2026-10-15 12:04:50 | INFO | Received configuration: toolId: "F.A.S.T" ...
    ...
    2026-10-15 12:05:34 | INFO | Running command Transfer
    2026-10-15 12:05:34 | INFO | fast run progress 0% (running)
    ...
    2026-10-15 12:05:55 | INFO | Running command Pause
    2026-10-15 12:05:56 | INFO | fast run progress 5% (paused)
    [docker restart galago-web at 12:07:27 WIB; running + /api/health OK at 12:07:32 WIB]
    2026-10-15 12:08:56 | INFO | Running command Resume
    2026-10-15 12:08:57 | INFO | fast run progress 5% (running)
    ...
    2026-10-15 12:10:11 | INFO | fast run progress 100% (idle)
    2026-10-15 12:10:11 | DEBUG | ExecuteCommand Response: response: SUCCESS
    2026-10-15 12:10:33 | INFO | Running command GetStatus
    2026-10-15 12:10:33 | DEBUG | ExecuteCommand Response: response: SUCCESS
    ```
    Exactly one "Running command Transfer" line in the whole window (12:05:34 WIB, before the
    restart); no second or later Transfer line appears anywhere, including after the restart. Kept
    for history.
- Final step result: the Transfer opened at 14:22:13 WIB ended `ExecuteCommand Response: response:
  SUCCESS` at 14:24:50 WIB, its wait having survived the 14:23:40 WIB restart and ended after the
  tool-page Resume — the D-12 mechanic (an orphaned Transfer's wait ends and the motion lock
  clears after tool-page recovery) held. **This time it was LIVE-07's own Transfer step**: the
  queue snapshot (`queue-live07-rerun.json`, read via a `docker cp` copy of `/app/data/queue.db`,
  read-only) shows `queueId 124`, `runId "1541991a8101e7000"` (LIVE-07), `source_start_col "6"`
  (column A6), matching the protocol record above exactly — unlike attempt 1, where the queue
  dispatched a different run's step.
  - **Attempt 1 (FAIL, D-14)**: the Transfer opened at 12:05:34 WIB ended `ExecuteCommand Response:
    response: SUCCESS` at 12:10:11 WIB, its wait having survived the 12:07:27 WIB restart and ended
    after the tool-page Resume — the D-12 mechanic itself held. **However, per that attempt's Queue
    state, this was not LIVE-07's own Transfer step**: `galago-web`'s queue showed the command that
    actually ran (`queueId 115`) belonged to the earlier LIVE-06b run and carried that run's
    column-3 (A3) parameters, not LIVE-07's column-4 (A4) parameters, even though the protocol
    record was LIVE-07's. The operator could not confirm which column was physically dosed ("not
    sure which col it transfered to"); the queue record indicated column 3 (A3), not column 4
    (A4) — unverified physically. Kept for history.
- Queue state: `galago-web` run `1541991a8101e7000` (protocol LIVE-07), queue row 124: Transfer
  A6→A6, 8×1, 50 µL, fresh, expected_tray_id 0. The orchestrator read a `docker cp` copy of
  `/app/data/queue.db` (read-only, `queue-live07-rerun.json`), taken after the tool-page recovery
  and before the operator cleared the queue:

  | queueId | runId | status | command | source_start_col | startedAt |
  |---|---|---|---|---|---|
  | 124 | `1541991a8101e7000` (LIVE-07) | **STARTED** | transfer | 6 (A6→A6) | `2026-10-15T07:22:13.600Z` |

  Queue state after: the operator cleared the queue ("queed cleared before LIVE-07: yes"); a
  re-read showed both the queue and commands tables empty.

  **FINDING (b) — orphaned-step row survives recovery (galago-core, read-only observation, not
  fixed here):** after the `galago-web` restart and the tool-page recovery, queue row 124 — the
  LIVE-07 transfer, already finished SUCCESS on the instrument per the log above — stayed in the
  `command_queue_2_queue` table at position 0 with status `STARTED`, not `COMPLETED`. `galago-web`
  never saw the step finish: the restart dropped the gRPC call that would have reported the
  outcome back to the queue (the same orphaned-step mechanism design section 8 describes), so the
  queue table never learned that the Transfer the adapter and instrument both completed had
  actually ended. If anyone had started the queue before it was cleared, `startNext()` would have
  picked up row 124 (still `STARTED`, still at position 0) and re-run the A6 transfer — unintended
  motion, the same class of defect as the queue re-run bug attempt 1 found (the D-14 queue-fix root
  cause was `fail()` leaving FAILED rows in `_queue`; this is the sibling case for a STARTED row
  orphaned by a `galago-web` restart, not touched by that fix). The orchestrator stopped the
  operator before the queue was started again; the operator cleared it, and a re-read confirmed
  both the queue and commands tables empty. **Operator workaround:** Clear All after any
  `galago-web` restart recovery, before starting another run. Flagged as a blocking item for the
  phase close-out decision in plan 03-08 — not a LIVE-07 failure: every D-11 criterion below still
  holds, since the re-run never actually happened (see `## Flagged assumptions` below).
  - **Attempt 1 (FAIL, D-14)**: `galago-web` `commandQueue.getAll` (read-only tRPC query), read by
    the orchestrator at ~12:11 WIB, before the operator cleared the queue:

    | queueId | runId | status | command | source_start_col | startedAt |
    |---|---|---|---|---|---|
    | 115 | `154151287281e7000` (LIVE-06b) | STARTED | transfer | 3 (A3→A3) | `2026-10-15T05:05:34.196Z` — identical instant to the log's only "Running command Transfer" line; `error` field still held the 11:46 WIB operator-abort message from LIVE-06b |
    | 116 | `154151287281e7000` (LIVE-06b) | CREATED | get_status | — | never started |
    | 117 | `15415a78d881e7000` (LIVE-07) | CREATED | transfer | 4 (A4→A4) | never started |

    Queue state after: OFFLINE (the operator cleared the queue afterward).

    **Root cause (galago-core, read-only observation, fixed by the D-14 redeploy above):**
    `controller/server/utils/SqliteQueue.ts`. `fail()` (line 493) marked a queue item FAILED but
    left it in the `_queue` table; `startNext()` (lines 112-145) selected the first `_queue` entry
    by position, regardless of status, and set it STARTED. When the operator started LIVE-07,
    `startNext()` picked `queueId 115` — the LIVE-06b transfer the operator had aborted at 11:46
    WIB in plan 03-06 — ahead of LIVE-07's own `queueId 117`, and re-ran it. LIVE-07's transfer
    never ran. The operator believed the A4 transfer was running; the queue record showed A3 ran
    instead.

    **Consequence:** after an operator abort, the next queue start silently re-ran the aborted step
    instead of the newly queued one. This was real, unrequested motion that the operator did not
    intend and had no way to see on the run page (the run page showed no control bar for the
    interrupted step by design, per D-12, so there was nothing on screen distinguishing "running
    LIVE-07" from "re-running LIVE-06b's aborted step"). This conflicted directly with the
    project's core value: "an operator running a F.A.S.T. step from Galago can always see what the
    instrument is doing." Fixed (galago-core quick task `261015-h0q`, commits `4b575ed`/`5598347`/
    `e18a177`/`a0afd61` — see `03-DEPLOY.md`'s "D-14 redeploy (queue re-run fix)" subsection). Kept
    for history.
- Control commands in window: rerun window 14:20:13-14:26:56 WIB (2 min before the Transfer's
  14:22:13 WIB start to 2 min after the 14:24:56 WIB `get_status` reply). Counts: Transfer=1,
  Pause=1, Resume=1, Abort=0, GetStatus=1 — matches the operator's reported actions exactly, all
  operator-sent: yes. `journalctl --user -u galago-tools --since "2026-10-15 14:20:13" --until
  "2026-10-15 14:26:56"` (re-checked) shows no entries — no tool-manager restart or
  reconfiguration in this window; `systemctl --user show galago-tools -p MainPID` stayed `836290`
  throughout (re-confirmed); the F.A.S.T. listener stayed `867162` throughout (re-confirmed via
  `ps` — no tool-server restart either, unlike the LIVE-06b D-14 redeploy earlier the same day,
  which restarted the `galago-tools` service; this queue-fix redeploy touched only galago-core and
  `galago-web`).
  - **Attempt 1 (FAIL, D-14)**: window 12:03:22-12:12:33 WIB (2 min before the run's creation to 2
    min after the `get_status` reply). Counts: Transfer=1, Pause=1, Resume=1, Abort=0,
    GetStatus=1 — every command line was triggered by an operator action (start, Pause, tool-page
    Resume, tool-page get_status), so no command appeared that the operator did not initiate in
    that narrow sense; but, per that attempt's Queue state, the Transfer line's **content** (which
    queue item it executed) was not the one the operator selected — the operator's "start the run"
    action for LIVE-07 triggered the queue's `startNext()`, which silently substituted a different,
    previously-aborted step. `journalctl` showed no service-level tool restart in this narrower
    window (the 12:04:42 tool-server restart predated it); `systemctl` MainPID stayed `836290`
    throughout. Kept for history.
- Screenshots: none provided (either attempt).
- D-11 criteria: observed per D-12's pass conditions (one restart scenario, rerun against the
  queue-fixed build):
  - No control bar on the run page after the restart: **met** — operator: "run page shows
    nothing" (D-12's expected no-control-bar state for the interrupted step).
  - Run Recovery enabled on the F.A.S.T tool page: **met** — the operator used it to send Resume.
  - The tool-page Resume answered SUCCESS on acceptance: **met** — "Running command Resume" at
    14:24:06 WIB, followed immediately by the run continuing ("fast run progress 46% (running)" at
    14:24:08 WIB); no separate `ExecuteCommand Response` text line for Resume itself (consistent
    with the production adapter's logging behavior for control commands recorded elsewhere in this
    file).
  - The instrument run completed: **met** — `fast run progress 100% (idle)` and `ExecuteCommand
    Response: response: SUCCESS` at 14:24:50 WIB.
  - The original Transfer's response appeared after the restart (its wait ended, the motion lock
    cleared) **for LIVE-07's own step this time**: **met** — the Transfer that ended was `queueId
    124` (LIVE-07's own transfer, column A6), matching the protocol parameters exactly; this
    reverses attempt 1's partial failure (where the Transfer that ended belonged to a different
    run).
  - The tool was READY and a following `get_status` ran SUCCESS: **met** — `Running command
    GetStatus` and `ExecuteCommand Response: response: SUCCESS` at 14:24:56 WIB; `fast_status.py`
    read READY/idle (independently re-confirmed live by the orchestrator: `{"status": "READY", ...,
    "run_state": {"percent": 100.0, "state": "idle", "pause": null}}`).
  - No Transfer was dispatched after the restart: **met** — exactly one "Running command Transfer"
    line in the whole window, before the 14:23:40 WIB restart; no second Transfer line appears
    anywhere afterward.
  - No control command the operator did not send: **met, in substance as well as in the letter
    this time** — every log line traces to an operator-initiated action, and (unlike attempt 1)
    the Transfer that executed was the one the operator selected to run; the queue dispatched
    LIVE-07's own step, not a substituted one. FINDING (b) above is a separate, latent risk (an
    orphaned STARTED row that would re-run on a future queue start) — it did not materialize as an
    unintended command in this run's window, so this criterion holds for LIVE-07 itself; it is
    flagged for the phase close-out decision rather than scored against this criterion.
  - **Attempt 1 (FAIL, D-14)**:
    - No control bar on the run page after the restart: met — operator: "run page shows no
      control after the restart, i was in the run recovery page".
    - Run Recovery enabled on the F.A.S.T tool page: met — the operator used it to send Resume.
    - The tool-page Resume answered SUCCESS on acceptance: met — "Running command Resume" at
      12:08:56 WIB, followed immediately by the run continuing ("fast run progress 5% (running)"
      at 12:08:57 WIB).
    - The instrument run completed: met — `fast run progress 100% (idle)` and `ExecuteCommand
      Response: response: SUCCESS` at 12:10:11 WIB.
    - The original Transfer's response appeared after the restart: met, but for the wrong step —
      a Transfer's wait did end and the motion lock did clear exactly as D-12 predicts; the
      Transfer that ended was `queueId 115` (LIVE-06b's aborted step), not LIVE-07's `queueId 117`.
    - The tool was READY and a following `get_status` ran SUCCESS: met — `Running command
      GetStatus` and `ExecuteCommand Response: response: SUCCESS` at 12:10:33 WIB; `fast_status.py`
      read READY/idle.
    - No Transfer was dispatched after the restart: met literally — only one "Running command
      Transfer" line existed in the whole window, before the 12:07:27 WIB restart; no second
      Transfer line appeared anywhere afterward. This was the exact check A-EDGE-LIVE-07 called
      for, and it passed — but it did not catch this failure mode, because the wrong step was
      dispatched before the restart, when the run was started, not after it.
    - No control command the operator did not send: not met as intended — every log line traced
      to an operator-initiated action, but the Transfer that executed was not the one the operator
      selected to run; the queue silently substituted a different run's previously-aborted step
      for the one the operator started. The letter of this criterion (no extraneous log line)
      held; its purpose (the operator controls what the instrument does) did not.
    Kept for history.
- Result: PASS
  - The rerun, against galago-core's queue-fix redeploy (`03-DEPLOY.md`'s "D-14 redeploy (queue
    re-run fix)" subsection: galago-core quick task `261015-h0q`, commits `4b575ed`/`5598347`/
    `e18a177`/`a0afd61`, `galago-web` image `94bdfa7e...` built 14:05:18 WIB), holds every D-12/
    D-11 criterion: the orphaned Transfer survived the `docker restart galago-web` and still held
    the motion lock after it; the run page showed no control bar for the interrupted step; the
    F.A.S.T tool page's Run Recovery card worked; the tool-page Resume was accepted and the
    instrument finished; the original Transfer's wait ended and the motion lock cleared **for
    LIVE-07's own step** (queue row 124, column A6, matching the protocol parameters); a following
    `get_status` ran SUCCESS with the tool READY; no Transfer was dispatched after the restart; and
    no control command the operator did not send appears in the window. Attempt 1 (FAIL, kept as
    history above under each bullet) failed only because the queue's `startNext()` re-ran a
    previously operator-aborted LIVE-06b step instead of LIVE-07's own transfer — a galago-core
    queue defect, now fixed (D-14) and verified not to recur here.
  - **FINDING (a) and FINDING (b)** (both galago-core queue defects of the same class as the one
    just fixed — a queued step runs on the next start even though the operator did not intend it)
    do not affect this Result: LIVE-07's own criteria all held on this run. They are recorded as
    blocking items for the phase close-out decision in plan 03-08, each with its operator
    workaround (Clear All after any abort or any `galago-web` restart recovery, before starting
    another run) — see Queue state above (FINDING (b)) and `## LIVE-06b`'s follow-up note above
    (FINDING (a)), and `## Flagged assumptions` below.
  - **Attempt 1 (FAIL, D-14), kept for history:** D-12's restart-and-recovery mechanics themselves
    held completely: the orphaned Transfer survived the `docker restart galago-web`, the run page
    correctly showed no control bar, the F.A.S.T tool page's Run Recovery card worked, Resume was
    accepted and the instrument finished, and a following `get_status` ran SUCCESS with the tool
    READY. The attempt FAILed because the queue executed an unintended, previously
    operator-aborted step (galago-core queue re-run defect, `controller/server/utils/
    SqliteQueue.ts` `fail()`/`startNext()`) instead of LIVE-07's own transfer — real motion the
    operator did not intend and could not see coming, which the physical evidence (deck 3's plate:
    water in column 3 vs column 4) was never confirmed or refuted. Per D-14 that attempt stopped
    there; the operator made the instrument safe (queue cleared, OFFLINE), the galago-core fix
    proceeded, and LIVE-07 was rerun on the fixed `galago-web` build along with the LIVE-06b
    follow-up check above — both now PASS.

## 261015-o44 live verification (resolves FINDING (a) and FINDING (b))

User-requested, after LIVE-07 passed: live-verify galago-core quick task `261015-o44`
(commits `662bb12`, `38b5d17`, `7627bf6`), deployed in `galago-web` image `ab544595abe2`
(galago-core HEAD `99e3986`; `99e3986` is also a docs-only commit recording the Phase 1
review fixes WR-01/IN-01/IN-02 that ride along in the same image). Image built
2026-10-15T11:38:08Z (18:38:08 WIB), container recreated 2026-10-15T11:44:52Z (18:44:52 WIB,
independently confirmed via `docker inspect galago-web`). Ancestry independently re-verified:
`git -C galago-core merge-base --is-ancestor 662bb12 HEAD` / `38b5d17` / `7627bf6` all → true;
`vendor/galago-tools` gitlink unchanged (`cb7886d`), so this verification needed no
`galago-tools` or proto change. `galago-tools` was not restarted for it: MainPID `836290`,
F.A.S.T. listener `867162`, unchanged from the LIVE-07 rerun baseline throughout (re-confirmed
live via `systemctl --user show` and `ss -ltnp`); `journalctl --user -u galago-tools` shows no
entries across either check window, including across the `docker restart galago-web` in check
(b). These checks close FINDING (a) and FINDING (b), both flagged above as blocking items for
this close-out decision.

### (a) An accepted abort removes the run's remaining steps — PASS

- Run `15420f33a301e7000` (protocol: Transfer A5→A5 then `get_status` — the operator reused the
  LIVE-06b protocol shape, not the suggested A7).
- F.A.S.T.log (`~/.local/share/galago/trace_logs/1792039261/F.A.S.T.log`, continuous since the
  12:04:42 WIB restart recorded under `## LIVE-07`'s Attempt 1 baseline note, no further
  overwrite):
  ```
  2026-10-15 18:40:19 | INFO | Running command Transfer
  2026-10-15 18:41:12 | INFO | Running command Pause
  2026-10-15 18:41:13 | INFO | fast run progress 12% (paused)
  2026-10-15 18:41:21 | INFO | Running command Abort
  2026-10-15 18:41:21 | INFO | fast run progress 12% (aborted)
  2026-10-15 18:41:21 | DEBUG | ExecuteCommand Response: response: ERROR_FROM_TOOL
  error_message: "run aborted by operator at 12%"
  ```
  Operator: "a done (return liquid: no)" — Abort with `returnLiquid=false`. No `: NoError (0)`
  suffix (the D-14 wording fix, `201d987`, still holds). Window 18:38:19-18:43:21 WIB: exactly
  Transfer=1, Pause=1, Abort=1, GetStatus=0 — no extraneous command.
- Queue table, read from a read-only copy of `/app/data/queue.db` (`docker cp`, independently
  re-queried for this record): `command_queue_2_queue` EMPTY; `command_queue_2_commands` shows
  `queue_id 132` (transfer) `status FAILED`, `queue_id 133` (get_status) `status SKIPPED`. Matches
  the operator's report exactly: the aborted step's own remainder (`get_status`) never ran and the
  queue carries nothing forward.
- Result: PASS — an accepted abort dequeues the aborted step and skips the run's remaining step;
  no unintended motion.

### (b) An orphan left by a restarted galago-web is never re-dispatched — PASS

- Run `154210ef5381e7000` (protocol: Transfer A5→A5 then `get_status`).
- F.A.S.T.log, same continuous file:
  ```
  2026-10-15 18:44:05 | INFO | Running command Transfer
  2026-10-15 18:44:32 | INFO | Running command Pause
  2026-10-15 18:44:34 | INFO | fast run progress 12% (paused)
  [docker restart galago-web at 18:44:52 WIB (operator: "go-restart"); container recreated
   2026-10-15T11:44:52Z, healthy by 18:44:57 WIB]
  2026-10-15 18:45:38 | INFO | Running command Resume
  2026-10-15 18:46:48 | INFO | fast run progress 100% (idle)
  2026-10-15 18:46:48 | DEBUG | ExecuteCommand Response: response: SUCCESS
  ```
  F.A.S.T. stayed BUSY/paused at 12% with the same `pause.since` across the restart (re-confirmed
  live before/after); `galago-tools` MainPID `836290` and F.A.S.T. listener `867162` were
  unchanged (`journalctl` empty across the restart window, 18:42:00-18:49:00 WIB). Window
  18:42:05-18:48:38 WIB: exactly Transfer=1, Pause=1, Resume=1, GetStatus=0 — zero Transfer
  commands after the restart.
- Queue table, read-only `docker cp` copy of `/app/data/queue.db` (re-queried): right after the
  restart, `queue_id 134` (transfer) went `FAILED` with
  `error.message "Interrupted: galago-web restarted while this step was running. It was not
  re-run; check the instrument before re-queuing it."`; `queue_id 135` (get_status) `SKIPPED`;
  `command_queue_2_queue` EMPTY — the orphaned step was never re-dispatched by the restart itself.
  The operator then sent the tool-page Resume ("recovered: resume at 18.45, get_status...tip
  broken: no"); the Resume ran to SUCCESS (18:46:48 WIB) but is a distinct, operator-initiated
  action on the still-open original Transfer, not a re-dispatch — `galago-core`'s
  `recoverInterruptedSteps` had already failed and dequeued row 134 at process start, before the
  operator acted. Final state, re-queried after the Resume: `command_queue_2_queue` still EMPTY;
  `command_queue_2_commands` final: `queue_id 132 FAILED`, `queue_id 133 SKIPPED`, `queue_id 134
  FAILED`, `queue_id 135 SKIPPED` (both checks' rows, confirmed together in one query). F.A.S.T.
  ended READY/idle (`fast_status.py` re-confirmed live:
  `{"status": "READY", "run_state": {"percent": 100.0, "state": "idle", "pause": null}}`).
- Result: PASS — a STARTED step orphaned by a `galago-web` restart is failed and dequeued at
  startup, never re-dispatched; the operator's subsequent tool-page Resume completes the
  already-open instrument-side step exactly once, with no second Transfer.

Both findings are now RESOLVED (galago-core `261015-o44`, live-verified) — see the updated
`## Flagged assumptions` entries below.

## Safety invariant audit

Design section 7 invariant 1 (D-11): every `Running command Pause`, `Running command Resume` and
`Running command Abort` line in the post-deploy F.A.S.T. log history, from the LIVE-04 deploy
restart (`2026-10-14 17:39:26 WIB`, trace dir `1791974367`) to now (`2026-10-15 18:47 WIB`,
trace dir `1792039261`), mapped to an operator action recorded in a scenario section. Compiled
from the surviving log files: the live current `~/.local/share/galago/trace_logs/1792039261/
F.A.S.T.log` plus the backup copies taken before each in-place overwrite
(`fast-log-20261015T1129.log`, `fast-log-20261015T1140.log`,
`fast-log-20261015T1147-newadapter.log`, `fast-log-20261015-live07.log`,
`fast-log-20261015-live07-rerun.log`, `fast-log-20261015-o44-checks.log`, in
`.planning`'s working scratch area). Every timestamp below was independently re-grepped from
these files for this record.

- Control commands found: 20 lines total — Pause 9, Resume 6, Abort 5, in order:

  | # | Time (WIB) | Command | Surviving source |
  |---|---|---|---|
  | 1 | 10:20:15 | Pause | old dir, post-10:16:36 backup |
  | 2 | 10:23:30 | Resume | old dir, post-10:16:36 backup |
  | 3 | 10:44:03 | Resume | old dir, post-10:16:36 backup |
  | 4 | 11:06:27 | Resume | old dir, post-10:16:36 backup |
  | 5 | 11:25:27 | Pause | old dir, post-10:16:36 backup |
  | 6 | 11:27:32 | Abort | old dir, post-10:16:36 backup |
  | 7 | 11:32:38 | Pause | old dir, post-10:16:36 backup |
  | 8 | 11:32:46 | Abort | old dir, post-10:16:36 backup |
  | 9 | 11:45:29 | Pause | new dir, post-11:41:02 backup |
  | 10 | 11:46:12 | Abort | new dir, post-11:41:02 backup |
  | 11 | 12:05:55 | Pause | new dir, live/continuous since 12:04:42 |
  | 12 | 12:08:56 | Resume | new dir, live/continuous since 12:04:42 |
  | 13 | 14:18:56 | Pause | new dir, live/continuous since 12:04:42 |
  | 14 | 14:19:06 | Abort | new dir, live/continuous since 12:04:42 |
  | 15 | 14:23:06 | Pause | new dir, live/continuous since 12:04:42 |
  | 16 | 14:24:06 | Resume | new dir, live/continuous since 12:04:42 |
  | 17 | 18:41:12 | Pause | new dir, live/continuous since 12:04:42 |
  | 18 | 18:41:21 | Abort | new dir, live/continuous since 12:04:42 |
  | 19 | 18:44:32 | Pause | new dir, live/continuous since 12:04:42 |
  | 20 | 18:45:38 | Resume | new dir, live/continuous since 12:04:42 |

  Re-checked zero other `Running command` lines of any type appear in the gap windows below (no
  stray Transfer/GetStatus either).

- Mapped to operator actions:

  | # | Time | -> Scenario / action |
  |---|---|---|
  | 1-2 | 10:20:15, 10:23:30 | `## LIVE-06a`: operator Pause, operator Resume |
  | 3 | 10:44:03 | `## LIVE-05` first attempt (FAIL, kept as history): operator Resume |
  | 4 | 11:06:27 | `## LIVE-05` scored rerun: operator Resume |
  | 5-6 | 11:25:27, 11:27:32 | `## LIVE-06b` attempt 1 (rehearsal, not scored): operator Pause, operator Abort |
  | 7-8 | 11:32:38, 11:32:46 | `## LIVE-06b` attempt 2 (not scored, exposed the wording defect): operator Pause, operator Abort |
  | 9-10 | 11:45:29, 11:46:12 | `## LIVE-06b` scored rerun: operator Pause, operator Abort |
  | 11-12 | 12:05:55, 12:08:56 | `## LIVE-07` attempt 1 (FAIL, kept as history): operator Pause, operator tool-page Resume |
  | 13-14 | 14:18:56, 14:19:06 | `## LIVE-06b` follow-up check: operator Pause, operator Abort |
  | 15-16 | 14:23:06, 14:24:06 | `## LIVE-07` scored rerun: operator Pause, operator tool-page Resume |
  | 17-18 | 18:41:12, 18:41:21 | `## 261015-o44 live verification` check (a): operator Pause, operator Abort |
  | 19-20 | 18:44:32, 18:45:38 | `## 261015-o44 live verification` check (b): operator Pause, operator tool-page Resume |

  All 20 lines map to an operator action already recorded (verbatim operator reply or directly
  observed tool-page action) in a scenario section of this document.

- Unmapped: none. Every Pause/Resume/Abort line since the LIVE-04 deploy traces to a recorded
  operator action.

  **Gaps named precisely (no surviving log, not claimed as audited):**
  - **2026-10-14 ~17:47 WIB -> 2026-10-15 10:16:36 WIB:** the original trace dir
    (`1791974367`)'s `F.A.S.T.log` was overwritten in place by the 10:16:36 WIB tool-server
    restart, destroying everything written before that instant. No backup survives for this
    window. Known activity inside it, from written-at-the-time records outside this phase's own
    log: the dry run (separate harness, port 40003 — its own section already confirmed, at the
    time, zero `Running command` lines reached the production F.A.S.T.log during its own narrower
    09:06-09:14 WIB sub-window, before the overwrite); galago-core's 02-UAT completion
    (`c71d2a1`, ~09:43 WIB) includes test 2 (Pause/Resume/Abort) and test 5 (instrument pause),
    both run against the real F.A.S.T. tool per `03-DEPLOY.md`'s note — evidenced only in
    galago-core's own `02-UAT.md` (re-confirmed present: tests 2 and 5 both `result: pass`),
    not re-derivable from this phase's log, which no longer covers this period. Stated plainly:
    this window's production-tool-log coverage does not survive to this audit; what stands is the
    record written at the time, in a different document.
  - **2026-10-15 ~11:47 WIB -> 12:02:49 WIB:** backup coverage of the new trace dir
    (`1792039261`) ends at 11:47 (`fast-log-20261015T1147-newadapter.log`); the next surviving
    evidence is the journal's 12:02:49 WIB tool-kill sequence and the 12:04:42 WIB restart
    content. No scenario in this document claims any operator action in this sub-window — the
    LIVE-06b scored rerun ended 11:46:13 WIB and LIVE-07 attempt 1 began 12:05:22 WIB — so there
    is no gap between two recorded events to account for, but this is an absence-of-claim, not a
    fresh log audit of that minute range.

- galago-tools restarts:
  - **2026-10-15 10:16:36 WIB** — tool-server restart (not a `systemctl` service restart; the
    `:8081` manager page, requests from `10.150.1.89`), stopping/starting Pf400, F.A.S.T. and
    Tool Box. `galago-tools` MainPID unchanged (`4044033`); new F.A.S.T. listener PID `727894`.
    Recorded in `03-DEPLOY.md`'s "Tool-server restart without a service restart" subsection and
    the `## LIVE-06a` Control commands correction. Explained; no unmapped command resulted.
  - **2026-10-15 11:40:59-11:41:00 WIB** — `galago-tools` **service** restart (`systemctl --user
    restart galago-tools`), the D-14 LIVE-06b adapter fix redeploy on the user's literal "go".
    MainPID `4044033` -> `836290`; new trace dir `1792039261`. Recorded in `03-DEPLOY.md`'s "D-14
    redeploy (LIVE-06b adapter fix)" subsection. Explained, recorded D-14 redeploy; no unmapped
    command resulted (the operator reconnected before any scenario resumed).
  - **2026-10-15 ~12:02:49-12:04:42 WIB** — tool-server restart (same `:8081` manager-page
    pattern as the first one; journal shows `Killed process 836333`/`F.A.S.T`/`836332`/`Tool
    Box`/`836310`/`Pf400` at 12:02:49-12:02:50 WIB, then `Started ... F.A.S.T on port 40001` at
    12:04:42 WIB). `galago-tools` MainPID unchanged (`836290`); F.A.S.T. listener PID `836333` ->
    `867162`. Recorded in `03-ACCEPTANCE.md`'s `## LIVE-07` Attempt 1 baseline note (the precise
    12:02:49 WIB kill-sequence timestamp is newly re-derived here from `journalctl`, narrowing the
    previously-recorded "at 12:04:42 WIB" restart instant to its start). Explained; no unmapped
    command resulted.
  - **No further restart from 12:04:42 WIB to now**: `journalctl --user -u galago-tools --since
    "2026-10-15 12:04:42"` (re-run for this record) shows only client-connection and
    image-not-found lines, no `Killed process`/`Started` pair; `systemctl --user show galago-tools
    -p MainPID` reads `836290` live; the F.A.S.T. listener PID (`ss -ltnp`) reads `867162` live —
    both match the baseline recorded under `## LIVE-07`'s rerun and carried through the
    `261015-o44` checks. The `docker restart galago-web` in check (b) (18:44:52 WIB) produced zero
    `galago-tools` journal entries, confirming it did not touch the tool-server process.
  - galago-tools did not keep the literal LIVE-04 post-deploy MainPID (`4044033`) through the
    whole acceptance — it changed once, at the 11:40:59 WIB D-14 redeploy above. That change is a
    recorded D-14 redeploy with its own gate rerun and operator go-ahead (`03-DEPLOY.md`), which is
    exactly the alternative this invariant's wording allows ("or that every change is a recorded
    D-14 redeploy"). From 11:41:00 WIB on, MainPID `836290` held through the rest of the
    acceptance, including the `261015-o44` checks just run.

- Result: PASS
  - 20 control-command lines found since the LIVE-04 deploy restart, all 20 mapped
  to a recorded operator action, 0 unmapped; 3 tool-process restarts found, all 3 explained (2
  tool-server-only restarts via the `:8081` manager page, 1 `galago-tools` service restart that is
  a recorded D-14 redeploy); 2 named gaps where no production log survives, both honestly stated
  with no claim of coverage beyond the written record from the time; 0 unexplained restarts.

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
- **Queue re-run defect found by LIVE-07 attempt 1 (2026-10-15, D-14, not an edge-probe item):**
  `galago-web`'s `startNext()` (`controller/server/utils/SqliteQueue.ts`, lines 112-145) dispatched
  the first `_queue` row by position regardless of status, and `fail()` (line 493) never removed a
  FAILED row from that table, so an operator-aborted row re-ran the next time the queue started
  instead of the newly queued step. Found live during LIVE-07 attempt 1 — see `## LIVE-07`'s Queue
  state bullet for the root cause and the note added under `## LIVE-06b`'s Result. **Fixed**
  (galago-core quick task `261015-h0q`, commits `4b575ed`/`5598347`/`e18a177`/`a0afd61`: an accepted
  operator Abort now calls `fail(..., {dequeue: true})`, removing the row from `_queue`): rerun PASS
  for both items this required — LIVE-07 (`## LIVE-07` above) and the LIVE-06b follow-up check
  (`## LIVE-06b` above) — both confirm the fix holds. See `03-DEPLOY.md`'s "D-14 redeploy (queue
  re-run fix)" subsection for the redeploy evidence.
- **FINDING (a) — aborted run's remaining steps stay queued (galago-core, 2026-10-15). RESOLVED
  (galago-core `261015-o44`, live-verified in plan 03-08):** the D-14 queue fix above dequeued
  only the aborted step itself; any later steps of that same run stayed in `_queue` and would have
  run on the next queue start, ahead of a different run's own steps. Observed in the LIVE-06b
  follow-up check's queue table (row 121, `get_status`, harmless here) but not exercised there —
  the operator cleared the queue before starting LIVE-07. Not a LIVE-06b failure — that run's own
  D-11 criteria held, and the thing the follow-up check exists to prove (the aborted step itself
  does not re-run) held exactly. galago-core fixed the remainder-dequeue gap (`662bb12`: an
  accepted abort now removes the aborted run's remaining steps, not just the aborted step itself)
  and it was live-verified PASS in plan 03-08, check (a): run `15420f33a301e7000`'s `get_status` step (row 133)
  went `SKIPPED`, the queue table EMPTY. No operator workaround is needed going forward; the
  previously-recommended "Clear All after any abort" workaround is now redundant, not required.
  Full detail: `## LIVE-06b`'s follow-up note and `## 261015-o44 live verification` check (a)
  above.
- **FINDING (b) — orphaned STARTED row survives `galago-web`-restart recovery (galago-core,
  2026-10-15). RESOLVED (galago-core `261015-o44`, live-verified in plan 03-08):** after a
  `galago-web` restart mid-run and tool-page recovery, the finished step's queue row stayed
  `STARTED` (`galago-web` never saw it finish — the restart dropped the gRPC call that would have
  reported the outcome) and would have re-run on the next queue start. Observed in the LIVE-07
  rerun's queue table (row 124) but not exercised there — the orchestrator stopped the operator
  before the queue could be started again. Not a LIVE-07 failure — every D-11/D-12 criterion for
  that scenario held. galago-core fixed it (`38b5d17`: a STARTED step left by a previous process is
  failed and dequeued at startup, never re-dispatched) and it was live-verified PASS in plan 03-08,
  check (b): run `154210ef5381e7000`'s orphaned transfer (row 134) was failed with an explicit
  "Interrupted: galago-web restarted..." message and dequeued immediately after the restart, before
  the operator's Resume; zero Transfer commands reached the tool after the restart. No operator
  workaround is needed going forward; the previously-recommended "Clear All after any restart
  recovery" workaround is now redundant, not required. Full detail: `## LIVE-07`'s Queue state
  bullet and `## 261015-o44 live verification` check (b) above.
- Findings (a) and (b) were both galago-core queue defects of the same class as the fixed re-run
  defect above: a queued step ran on the next start even though the operator did not intend it.
  Neither was a LIVE-06b or LIVE-07 failure — every scored D-11/D-12 criterion for both scenarios
  held. Both were carried forward from plans 03-06/03-07 as blocking items for this phase's
  close-out decision and are now resolved by galago-core `261015-o44`, live-verified read-only in
  plan 03-08 (`## 261015-o44 live verification`, `## Safety invariant audit`).
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
