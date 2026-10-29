# Phase 5 Design Spike: ledger transitions checked against the pinned core

**Phase:** 05-f5-safe-transfer-operator-acknowledge (plan 05-01, decision D-01)
**Date:** 2026-10-29
**Core:** `934a621ece116a8b263897c1e9b62b57374f4ef3` (`~/data/nikko/stack-automation-layer`, read with
`git show 934a621:stack_automation_layer/<file>`; every `service.py:N` / `results.py:N` below is a line at that commit)
**Mode:** `--auto`; open questions were resolved by the orchestrator (section 5)

**Precedence:** this spike's version wins over CONTEXT D-05..D-13 wherever they differ (D-01, D-09). Section 4
lists every difference. Sections 1-3 answer the three D-01 questions, section 6 is the binding contract that plans
05-02..05-07 implement, and section 7 is the verdict.

Nothing here is an instrument rule. Every statement is adapter bookkeeping about which ledger record survives
which core answer. The core classifies; the adapter records and never works around a core gap (PROJECT rule, D-01).

---

## 1. Restart mid-transfer (D-01 question a)

**Question.** After a tool-server restart, does `wait_transfer(guid)` on a guid the restarted core does not own still
observe `ran` / `failed` from STACK? Does a failure then latch or not? (D-09)

**Evidence.**

- `service.py:922-960` `_reattach`: looks the guid up in `_started`; when absent it builds a plain
  `TaskHandle(guid=..., kind=...)`. The docstring (`:929-933`) says a guid this service did not start "still waits on
  a handle built with that `kind` (the read is harmless -- ownership only matters for a later cancel)".
- `service.py:2010-2016` (`_wait`): latching depends on ownership.
  `owned = handle.guid in self._started` at `:2010-2011`, then
  `will_latch = owned and self._should_latch(result) and not self._relatch_suppressed(handle.guid, result)`.
- `service.py:1325` `_should_latch` is true for `failed`, `aborted`, `lost` and `cancelRequested`.
- `service.py:496-501` `_snapshot_locked` persists `started` handles only for `live = set(self._inflight)` plus the
  latch guid, and `service.py:462-468` `_restore` reinstalls `_latch`, `_started` and `_inflight`. So a guid that was in
  `_inflight` when the old process died comes back **owned**. A guid whose process died between the POST and the
  `_persist_locked` call (core limit 1), or one that finished without a latch (limit 2), comes back **foreign**.
- `service.py:1591-1601` `_motion_gates` refuses the next transfer unless the manager mode is `automated`
  (`managerNotAutomated`) and the robot row reads `idle` (`robotNotIdle`). These are core gates.
- Executed probes against the real `StackService` (pinned venv, from 05-RESEARCH.md, spike (a)):

```
--- (a1) FOREIGN guid (fresh service, empty store): wait_transfer observes failed, latch?
failed | latch_status: False
--- (a2) FOREIGN guid observes ran
ran | latch: False
--- (a3) OWNED-after-restart: persist inflight+started, new service, wait_transfer failed
restored inflight: {'11111111-2222-3333-4444-555555555555'} started: ['11111111-2222-3333-4444-555555555555']
failed | latch: True 11111111-2222-3333-4444-555555555555 | inflight after: set()
```

**Answer.** Yes. `wait_transfer` on a foreign guid still observes `ran` and `failed` from STACK (a2, a1). A foreign
`failed` does **not** latch (a1: `latch_status: False`); an owned-after-restart `failed` **does** (a3). After a
restart the adapter cannot tell which of the two cases it is in, because `_started` is private to the core. The only
honest wording is "the core may not have latched this failure", plus whatever `latch_status()` says after the wait.

**Verdict.** D-09 is confirmed as written, with one orchestrator resolution recorded in section 5 (OQ1): a live `ran`
observed after a restart is SUCCESS flagged `reattachedAfterRestart`; every other outcome after a restart is
`ERROR_FROM_TOOL` carrying the arm-inspection clause. The core's `managerNotAutomated` and `robotNotIdle` gates still
protect the next Transfer when a foreign failure did not latch. That protection is core policy, not adapter policy,
so the adapter adds no rule of its own.

---

## 2. Latch guid after Lost(submitOutcomeUnknown) (D-01 question b)

**Question.** Is `latch_status().guid` the `submit-<hex>` id immediately after `execute_transfer` returns
`Lost(submitOutcomeUnknown)`? (D-13)

**Evidence.**

- `service.py:1701-1702` `_submit_outcome_unknown`'s first statements:
  `latch_id = "submit-" + secrets.token_hex(8)` then
  `self._set_latch(latch_id, "lost", "submitOutcomeUnknown", None, terminal=False)`. The latch exists before the `Lost`
  value is even built.
- `service.py:1518-1538` `latch_status()` answers from memory under `_state_lock` with no transport call and no disk
  access, returning `LatchStatus(latched=True, guid=latch.guid, result_kind=latch.kind, reason=latch.reason,
  explanation=latch.explanation)`. Its docstring (`:1522-1527`) says it gives "the guid `acknowledge_failure` must name
  (a task guid, or a minted `submit-<hex>`/`state-<hex>` id)".
- `results.py:1072-1085` `Lost.to_dict()` is `{kind, handle, lastState, reason, detail, message, explanation, context}`.
  `handle` is `None` for this reason (`results.py:1055-1058`) and `detail` is built from `robot, mode, recovery,
  robotState` only (`service.py:1703-1708`). No structured field of the result carries the guid.
- `service.py:1348-1350` `_set_latch` is first-failure-wins: it returns early when a latch is held and its kind is not
  `stateUnsaved`. `_motion_gates` refuses with `failureLatched` before the POST when a latch is held, so a competing
  latch can only appear in a concurrent race.
- Executed probes (05-RESEARCH.md, spike (b)):

```
== 2 POST raises ReadTimeout -> Lost(submitOutcomeUnknown)
lost submitOutcomeUnknown posts 1 | latch submit-2b56c97300d7ce1d inflight set()
plan again -> failureLatched | execute same plan_id -> planNotFound
--- (b) _submit_outcome_unknown then latch_status guid
kind/reason: lost submitOutcomeUnknown handle: None detail keys: ['mode', 'recovery', 'robot', 'robotState']
latch guid: submit-7f0a958f6723b3ce True lost submitOutcomeUnknown
guid in explanation: True
```

**Answer.** Yes. `latch_status().guid` matches `submit-[0-9a-f]{16}` (the `submit-` prefix plus 16 hex digits) the instant
`execute_transfer` returns, and it appears in no structured field of the `Lost` dict. The adapter's `_find_guid`
therefore returns `None` for it, so the adapter must call `latch_status()` (zero I/O) to learn it. The one edge is the
first-failure-wins race above: if another latch was set first, `latch_status().guid` is that other latch's guid.

**Verdict.** The adapter records whatever `latch_status()` returns at that moment as `latchGuid`. That value may be
`None` (not latched) or another latch's guid in a concurrent race. The adapter never assumes a `submit-` prefix and
never parses the core's `explanation` text, which is agent-worded and forbidden by Phase 4 D-11 (the probe shows the
guid is in the explanation, and that is exactly why it must not be scraped).

---

## 3. Results that prove nothing was sent (D-01 question c)

**Question.** Which `execute_transfer` results prove that no transfer was sent, so the step key can be released
(XFR-04)? What happens on an exception?

**Evidence.**

- `service.py:911-920` `execute_transfer`: a non-string or unknown `plan_id` is `Refused(planNotFound)`, an old plan is
  `Refused(planExpired)`, otherwise `return self.start_transfer(request)`. The plan id is popped on the first attempt,
  so a second attempt on the same id is always `planNotFound`.
- `service.py:1254-1306` `start_transfer` order: latched refusal (`:1255-1257`), `_validate_locally` (`:1258-1263`),
  then `with self._submit_lock:` the motion gates (`:1266-1268`), exactly one `post_transfer` (`:1271`).
  A typed `StackHTTPError` goes to `_classify_submit_error` (`:1272-1273`); any other exception, or a body with no
  well-formed guid, goes to `_submit_outcome_unknown` (`:1274-1279`). Everything before the POST sits under the outer
  `except Exception as exc: return ReadFailed.from_error(exc)` (`:1305-1306`).
- The docstring (`:1245-1248`) states "Nothing past that point may escape to the outer guard, so a transfer that was
  actually sent is never mislabelled a failed read". Only `BaseException` (`KeyboardInterrupt`, `SystemExit`) can leave
  `execute_transfer`; ordinary exceptions are converted.
- Executed probes (05-RESEARCH.md, spike (c), probes 3-6):

```
== 3 refusals pre-POST: manager manual / manager read error
refused managerNotAutomated posts 0
readFailed posts 0
== 4 typed HTTP 500 on POST (residual-risk case)
rejected instrument 500 posts 1 | latched False | inflight set()
== 5 typed HTTP 400 busy on POST
refused stackBusy posts 1 latched False
== 6 in-flight: second transfer while first guid not terminal -> inFlight
refused inFlight {'guid': '00000000-0000-4000-8000-000000000001'} posts 1
```

(Probe 6's `posts 1` is the first transfer's POST; the refused second one sent none.)

**Answer.** Classification of every `execute_transfer` outcome:

| execute_transfer result | POST sent? | Ledger action |
|---|---|---|
| `Refused(planNotFound / planExpired / failureLatched / inFlight / managerNotAutomated / recoveryPending / robotNotIdle)`, `NeedsInput`, and `ReadFailed` from a gate or validation read | No (probe 3: 0 POSTs) | release (delete the record) |
| `Refused(stackBusy)` and `Rejected(stage="instrument", httpStatus=...)` | Yes: one POST was sent and STACK typed-refused it (probes 4 and 5: `posts 1`, no latch, no in-flight guard) | release (XFR-04 as written) |
| `Lost(submitOutcomeUnknown)` | Yes or maybe | `outcomeUnknown`, permanent, with `latchGuid` |
| any other `Lost` reason, or any object that is not one of the core's result classes | unknown | `outcomeUnknown`, permanent, never deleted (fail closed) |
| `TaskHandle` | Yes | `started` |
| an exception out of `execute_transfer` | unknown | the record stays `submitting`, permanent |

The release whitelist is by `isinstance` against the core's real classes, never by the `kind` string:
`Refused`, `Rejected`, `NeedsInput`, `ReadFailed`. Anything outside the whitelist is kept. A mock that returns garbage
is therefore kept, not deleted.

`Rejected(stage="instrument")` after a typed HTTP error and `Refused(stackBusy)` were sent once and typed-refused by
STACK. They do not prove nothing reached the instrument in the physical sense. "Proves nothing was sent" is the core's
own classification of a typed answer as a decision rather than an unknown. XFR-04 locks the release of `rejected`,
so the release stays, and the residual risk is recorded in section 5 (OQ2) and section 7.

**Verdict.** D-08 is confirmed with two additions that follow the fail-closed rule: an unexpected `Lost` reason or an
unknown result type becomes `outcomeUnknown`, never a deletion. A `ReadFailed` after the POST is reachable only if
`_submit_outcome_unknown` itself raised before its internal guards, which the core treats as impossible, so releasing
on `ReadFailed` is consistent with the core's documented guarantee.

---

## 4. Amendments (the spike's version wins)

Each amendment states what it changes in CONTEXT and why. Where the text below and CONTEXT differ, the text below is
what plans 05-02..05-07 implement.

- **A-1 (amends D-05, D-07, D-11): the ledger's `done` set is the core's `_task_ended` set.**
  A record becomes `done` only when the wait result is `ran`, `failed` or `aborted`, or `lost` with reason
  `taskNotFound`. This mirrors `service.py:1917-1930` `_task_ended`, which is also the only condition that clears the
  core's persisted in-flight guard (`service.py:2042-2046`). `timedOut`, `lost(pollFailed)`, `cancelled` and any other
  wait result (`needsInput`, `readFailed`) keep the record `started`.
  *Why:* CONTEXT D-05/D-07 treat every non-`timedOut` result as terminal. But `_should_latch` (`service.py:1325`)
  latches `lost` for any reason, while `_task_ended` does not clear `_inflight` for `lost(pollFailed)`. The probe:

```
lost pollFailed | inflight: {'11111111-2222-3333-4444-555555555555'} | latch: True pollFailed
ack: failureAcknowledged None | inflight after ack: {'11111111-2222-3333-4444-555555555555'}
1st: lost pollFailed latched True
re-attach while latched: ran | inflight: set() | latch still: True pollFailed
```

  `acknowledge_failure` does not clear `_inflight`. A ledger that recorded `lost(pollFailed)` as `done` would never wait
  that guid again, and because the guard is persisted by the core, every later Transfer would be `Refused(inFlight)`
  permanently. Keeping the record `started` lets a re-run re-attach (which works while latched) and clear the guard.
  After that re-attach observes `ran` the step is SUCCESS while the `pollFailed` latch is still held, so the next
  Transfer is refused `failureLatched` naming the guid, which is safe and visible.

- **A-2 (amends D-13 ordering): the guid to acknowledge comes from `latch_status().guid` first.**
  After any non-`ran` result, and for every refusal whose cause can latch, the adapter calls `latch_status()` once
  (zero I/O). If `latched`, the message names that guid and its `resultKind`. If not latched, it says the core did not
  latch this and tells the operator to inspect the arm. The result's own guid is labelled "task guid" and is never
  presented as the guid to acknowledge.
  *Why:* the latch is first-failure-wins (`service.py:1348-1350`) and `acknowledge_failure` answers `guidMismatch`
  unless `guid == latch.guid` (`service.py:1476-1477`). A re-attached `failed` for task guid `g` while a different latch
  (`submit-...`) is held does not re-latch, so the result's guid would be the wrong thing to tell the operator.

- **A-3 (extends D-08): the orphaned core in-flight guard is an accepted limitation.**
  If the tool dies after the core persisted `_inflight` (`service.py:1283-1285`) but before the adapter's `started`
  write, the ledger holds `submitting` (the key refuses forever) while the core holds an in-flight guid that no
  adapter path will wait. Every later Transfer is then `Refused(inFlight, guid)` until someone waits that guid. No
  adapter drain is built: it would be unplanned motion-adjacent behaviour (XFR-05 spirit). The runbook route is a
  read-only `wait_transfer(guid)` from stack-mcp, which shares the core state file for the same endpoint. This goes
  into the Phase 7 runbook (section 7).
  The in-scope mitigation: an `inFlight` refusal whose guid equals some ledger record's `handle.guid` names the owning
  step key in the message (`step key <k2> is still running; re-run that step to re-attach`).

- **A-4: SUCCESS `ran` never carries a held-latch field.**
  `ran` stays SUCCESS with an empty message (STK-07). A held latch (`stateUnsaved`, or a re-attached `lost(pollFailed)`)
  is reported by the next Transfer's `failureLatched` refusal, which names the guid, and by `GetFailureLatch`.

- **A-5 (amends D-05): records gain an optional `latchGuid` field.**
  Set only when the state is `outcomeUnknown`: the string `latch_status()` returned at that moment, or `null` when
  the core was not latched (section 2). It is absent or `null` in every other state.

- **A-6 (amends D-07 "no core call"): a ledger refusal row makes no `plan_transfer`, `execute_transfer`, `wait` or
  `wait_transfer` call.** It may call `latch_status()` once (zero I/O, in-memory) to name the current latch, where the
  section 6f template says so. Replay and mismatch make no core call at all.

**Not amended:** D-02, D-03, D-04, D-06, D-10, D-12, D-14..D-17 stand as written, with the section 6 constants and
templates filling the values CONTEXT left to the planner.

---

## 5. Resolved open questions

All five were resolved by the orchestrator in `--auto` mode, with the choice recorded here so a verifier can trace it.

- **OQ1 (XFR-03 wording vs D-09): resolved, keep D-09.** A live `ran` observed through `wait_transfer` after a restart
  is SUCCESS, with adapter-owned meta `reattachedAfterRestart: true`. It is STACK's own `completed` observation (probe
  a2), not a ledger replay. A *recorded* `ran` is replayed only within `REPLAY_WINDOW_S`, and a `done` record is never
  re-observed. Any non-`ran` outcome after a restart is `ERROR_FROM_TOOL` with the arm-inspection clause (section 6f),
  which also carries the current `latch_status()` guid when there is one. A `submitting` record after a restart is
  refused with the same clause. The stricter reading ("never SUCCESS after a restart") is a one-line change in the
  re-attach branch if the user asks for it later.
- **OQ2 (release after a typed 5xx or `stackBusy`): resolved, follow XFR-04 as written.** `Rejected(stage="instrument")`
  and `Refused(stackBusy)` release the key. The residual risk, that a 5xx from STACK may have acted server-side, is
  documented here and in section 7, not mitigated by a new rule. A re-run is still stopped by the core's own gates
  (`robotNotIdle`, `inFlight`, `stackBusy`, `managerNotAutomated`), not by the ledger. The adapter holds no instrument
  policy. If the user later wants belt-and-braces, treating `httpStatus >= 500` as `outcomeUnknown` without a latch is
  a one-branch change in the release whitelist.
- **The orphaned core in-flight guard (OQ5): resolved, document, no adapter drain.** See A-3. It goes into the Phase 7
  runbook.
- **A-4 / OQ3 (held latch on SUCCESS): resolved, no field.** See A-4.
- **OQ4 (galago-core's own command deadline versus the default `T = 300 s`): carried to the Phase 7 live acceptance.**
  It cannot be answered from this repo. The ledger already makes a "galago gave up, the arm finished" case safe: a
  re-run re-attaches, or replays within `REPLAY_WINDOW_S`, and never re-sends.

---

## 6. Binding ledger contract

Plans 05-02..05-07 implement this section. It is complete enough that none of them needs a further design decision.
A conflict between this section and CONTEXT or RESEARCH is resolved in favour of this section.

### 6a. Record schema

The file is `{"version": 1, "records": {<step_key>: <record>}}`. The step key is the JSON object key, byte-exact.

| field | type | rule |
|---|---|---|
| `fingerprint` | string | 64 lowercase hex characters (sha256), see 6d |
| `state` | string | one of `submitting`, `started`, `done`, `outcomeUnknown` |
| `instance` | string | the uuid hex minted once per `StackServer`; compared for restart detection |
| `handle` | object or null | `TaskHandle.to_dict()` (`{kind, guid, robot, estimatedS}`); required with a non-empty string `guid` when `state` is `started`; set from `started` onward |
| `result` | object or null | the terminal `to_dict()`; required with a string `kind` when `state` is `done` |
| `latchGuid` | string or null | A-5: set only when `state` is `outcomeUnknown`; otherwise absent or null |
| `createdAt` | string | aware-UTC `datetime.isoformat()`, for example `2026-10-29T12:00:00.123456+00:00` |
| `updatedAt` | string | aware-UTC `datetime.isoformat()`; refreshed on every transition |

Parsing is strict and fail closed, like the core's `_parse_state`: `type(version) is int` (a boolean `true` is rejected)
and `== LEDGER_VERSION`; `records` must be a dict; every key a string; every record a dict with a valid `state`, a
string `fingerprint` and string `instance`; `started` needs `handle.guid`, `done` needs `result.kind`. Anything else
is "corrupt" or "unknownVersion", the whole ledger is refused, and it is never treated as empty, deleted or rewritten.
A missing file is a clean start. A directory or unreadable file is "unreadable".

Write order on the fresh path (D-05, with A-1):

1. `claim` writes `submitting` after `plan_transfer` returns a `TransferPlan` and before `execute_transfer`
   (create-if-absent under the flock; an existing key is "claimed by another tool server").
2. `mark_started(handle.to_dict())` as soon as `execute_transfer` returns a `TaskHandle`.
3. `mark_done(result)` only when the wait result satisfies A-1. Otherwise the record stays `started`.

Every mutation takes the `fcntl.flock` on the sibling lock file, re-loads strictly under the lock, applies one change,
and saves atomically (temp file in the same directory, `fsync`, `os.replace`, best-effort directory `fsync`). The flock
is held only around each read-modify-write, never across a transfer.

### 6b. Final repeat-key table

`decide(record, *, fingerprint, instance, now)` returns exactly one action. The checks run in the order of the rows
below. `restarted` is true exactly when the record's `instance` differs from the caller's.

| # | action | condition | core calls | reply code | ledger effect |
|---|---|---|---|---|---|
| 1 | `fresh` | no record for the key | `plan_transfer`, then the fresh path | per 6c: `SUCCESS` only on `ran`, otherwise `ERROR_FROM_TOOL` | claim, started, done |
| 2 | `mismatch` | a record exists and its `fingerprint` differs (checked first, for every state) | none | `INVALID_ARGUMENTS` | none |
| 3 | `refuseSubmitting` | `submitting` | none (A-6: at most one `latch_status()`) | `ERROR_FROM_TOOL` | none |
| 4 | `refuseOutcomeUnknown` | `outcomeUnknown` | none (A-6: at most one `latch_status()`) | `ERROR_FROM_TOOL` | none |
| 5 | `reattach` | `started` | `wait_transfer(guid, ...)` loop only | `SUCCESS` on a live `ran` (meta adds `reattachedAfterRestart: true` when `restarted`), otherwise `ERROR_FROM_TOOL` | done only per A-1, else stays `started` |
| 6 | `replay` | `done`, result kind `ran`, and `0 <= age < REPLAY_WINDOW_S` | none | `SUCCESS`, empty message, meta `{stepKey, ledgerState: "done", result, replayed: true}` | none |
| 7 | `refuseCompleted` | `done`, result kind `ran`, and age `>= REPLAY_WINDOW_S` or age `< 0` (or `updatedAt` unparseable) | none | `ERROR_FROM_TOOL` | none |
| 8 | `refuseFailed` | `done` with any other result kind (`failed`, `aborted`, `lost(taskNotFound)`, or anything unexpected) | none (A-6: at most one `latch_status()`) | `ERROR_FROM_TOOL` | none |

`age = now - updatedAt` of the `done` record, in seconds. An age of exactly 600 s, or a negative age (a future-dated
record, clock skew), is `refuseCompleted`, so replay is fail-closed. A `done` record is never re-observed with
`wait_transfer`. Meta of every ledger-generated reply is `{stepKey, ledgerState}` plus `result` and `replayed` on a
replay (D-10). No row calls `plan_transfer`, `execute_transfer`, `wait` or `wait_transfer` except rows 1 and 5.

Re-attach rules (row 5): a bounded read-only loop, `wait_transfer(guid, timeout_s=min(remaining, WAIT_SLICE_S))`,
never called with `remaining <= 0`, exiting on the first non-`timedOut` result. A result that satisfies A-1 is recorded
`done`; `timedOut`, `lost(pollFailed)` and every other result leave the record `started` and reply `ERROR_FROM_TOOL`
with "re-run this step to re-attach". When `restarted`, every non-`ran` outcome adds the restart clause (6f) and the
current latch clause.

### 6c. Release whitelist and keep rules

| situation | ledger effect |
|---|---|
| `plan_transfer` returns anything but a `TransferPlan` | no record is ever written |
| `execute_transfer` returns an instance of `Refused`, `Rejected`, `NeedsInput` or `ReadFailed` (by `isinstance`) | `release`: delete the record (only a `submitting` record is deleted) |
| `execute_transfer` returns `Lost` with reason `submitOutcomeUnknown` | `outcomeUnknown`, `latchGuid` from one `latch_status()` call |
| `execute_transfer` returns any other `Lost`, or any object outside the core's result classes | `outcomeUnknown` as above; never deleted |
| `execute_transfer` raises | record stays `submitting`; reply carries `type(exc).__name__` only, never `str(exc)` |
| `ledger.release` or a later write raises `LedgerError` | the record stays as it is; the reply says the key will not be re-sent or could not be recorded (6f) |
| wait result satisfies A-1 | `done` |
| wait result is `timedOut`, `lost(pollFailed)`, `cancelled` or anything else | record stays `started` |
| an `AcknowledgeFailure` | never touches the ledger |

Reply mapping for the fresh path: `ran` is `SUCCESS` with an empty message. Every other kind is `ERROR_FROM_TOOL` with a
one-line message built from structured fields, with meta `to_dict()`. A ledger-write failure after the wait turns even
a `ran` into `ERROR_FROM_TOOL` ("transfer ran, but the ledger could not record it", D-04).

### 6d. Constants, fingerprint, key handling

| name | value | module | note |
|---|---|---|---|
| `LEDGER_VERSION` | `1` | `tools/stack/ledger.py` | a fingerprint or schema change needs a bump and a migration rule |
| `LEDGER_FILENAME` | `"stack-ledger.json"` | `ledger.py` | |
| `LOCK_FILENAME` | `"stack-ledger.json.lock"` | `ledger.py` | sibling lock file, mode 0600, opened with `O_NOFOLLOW` |
| `REPLAY_WINDOW_S` | `600.0` | `ledger.py` | replay only when `0 <= age < 600.0` |
| `RETENTION_DONE_S` | `604800.0` | `ledger.py` | 7 days; prune only `done` records older than this, only on a write; never `submitting`, `started` or `outcomeUnknown`; a `done` record with an unparseable `updatedAt` is kept |
| `LOCK_TIMEOUT_S` | `5.0` | `ledger.py` | `LOCK_EX` with `LOCK_NB` polling deadline; on expiry fail closed with "ledger busy" |
| `DEFAULT_TRANSFER_TIMEOUT_S` | `300.0` | `server.py` | D-11 third choice |
| `MAX_TRANSFER_TIMEOUT_S` | `3600.0` | `server.py` | the wait budget is clamped to this, never rejected |
| `WAIT_SLICE_S` | `300.0` | `server.py` | one `wait_transfer` slice; the core clamps each call to `WAIT_TRANSFER_MAX_S = 300.0` (`service.py:194`) |

Wait budget `T` (D-11): `Transfer.timeout_s` when set and `> 0`, else `Config.transfer_timeout_s` when `> 0`, else
`DEFAULT_TRANSFER_TIMEOUT_S`, then `min(T, MAX_TRANSFER_TIMEOUT_S)`. The fresh path makes one
`service.wait(handle, timeout_s=T)`.

Fingerprint (D-06): sha256 hex of `json.dumps({"v": 1, "endpoint": endpoint_key(host, port),
"request": dataclasses.asdict(TransferRequest)}, sort_keys=True, separators=(",", ":"))`. It excludes `step_key` and
`timeout_s`, so the same request on a different STACK mismatches.

Step key: used byte-exact. No `strip`, no case folding. `"run-1:stack-1 "` and `"run-1:stack-1"` are different keys.
There is no `step_key` length cap (accepted, low risk: keys are minted by the protocol and unbounded keys only grow
the JSON file). Message builders therefore place the guid and the next action before the step key (6f).

### 6e. Default ledger path (D-03)

Order: an explicit absolute `Config.ledger_dir` wins (it may sit under `/tmp`, because every test fixture does); else
`$XDG_STATE_HOME/galago-tools/stack` when `XDG_STATE_HOME` is set and absolute; else
`~/.local/state/galago-tools/stack`. The default is never under `/tmp`. A non-blank relative `Config.ledger_dir`
fails Configure with a `ValueError` before `open_service`. The path is resolved lazily at Transfer time from the
configured value plus the environment, so an unconfigured fixture still lands under `XDG_STATE_HOME`. Directory mode
0700, ledger and lock file mode 0600. Configure creates nothing; the directory is created by the first write-ahead
`claim`. The core's own state file lives elsewhere (`STACK_STATE_DIR`); the two never share a path.

### 6f. Operator message templates

Rules for every message: one line; built from structured fields only, never the core's `explanation`, `message` or
`str(exc)`; the guid to act on and the next action come **before** any step key or hint; the whole line passes through
`_one_line(line, 300)` so the tail is what gets cut. The latch clause and the restart clause are fixed strings below.

| key | reply code | template |
|---|---|---|
| ledger unreadable | `ERROR_FROM_TOOL` | `stack: step ledger unreadable (<reason>) at <path>; do not delete it; no transfer was sent` |
| write-ahead failed | `ERROR_FROM_TOOL` | `stack: no transfer was sent; the step ledger could not record the step (<reason>); fix the ledger directory, then re-run this step` |
| later write failed | `ERROR_FROM_TOOL` | `stack: transfer <kind>, but the ledger could not record it; <latch clause>; re-running this step key will not send a second transfer` |
| busy | `ERROR_FROM_TOOL` | `stack: busy; another Transfer is running in this tool; wait for it to finish, then re-run this step` |
| claimed elsewhere | `ERROR_FROM_TOOL` | `stack: this step key is claimed by another tool server sharing the ledger; no transfer was sent; re-run this step to see its state` |
| execute raised | `ERROR_FROM_TOOL` | `stack: execute failed (<ExceptionTypeName>); outcome unknown; check the STACK Manager and GetFailureLatch; this step key will not be re-sent` |
| latch clause, latched | clause | `latched guid <g> (<resultKind>); inspect the arm, then AcknowledgeFailure` |
| latch clause, not latched | clause | `the core did not latch this; inspect the arm` |
| latch clause, unavailable | clause | `latch status unavailable; read GetFailureLatch` |
| timedOut | `ERROR_FROM_TOOL` | `stack: still running (timedOut); re-run this step to re-attach` |
| pollFailed | `ERROR_FROM_TOOL` | `stack: lost (pollFailed); <latch clause>; the transfer may still be running; re-run this step to re-attach` |
| refuseSubmitting | `ERROR_FROM_TOOL` | `stack: outcome unknown for this step key; check the STACK Manager and GetFailureLatch; this step key will not be re-sent; step key <k>` (adds the restart clause first when `restarted`) |
| refuseOutcomeUnknown | `ERROR_FROM_TOOL` | `stack: outcome unknown; latched guid <latchGuid>; inspect the arm, then AcknowledgeFailure; this step key will not be re-sent; step key <k>` (with a null `latchGuid`: `no latch guid was recorded; read GetFailureLatch`) |
| refuseCompleted | `ERROR_FROM_TOOL` | `stack: step key already completed at <updatedAt>; mint a new step key per run; nothing was sent; step key <k>` |
| refuseFailed | `ERROR_FROM_TOOL` | `stack: <kind> (<reason>) is recorded for this step key; <latch clause>; then run the step under a new step key; task guid <tg>; step key <k>` |
| restart clause | clause | `tool restarted mid-transfer; inspect the arm; the core may not have latched this failure` |
| in-flight owner (A-3) | clause | `step key <k2> is still running; re-run that step to re-attach` |
| fingerprint mismatch | `INVALID_ARGUMENTS` | `stack: step key <k> was used for a different request or STACK; mint a new step key` |

A Transfer error whose cause can latch (`failed`, `aborted`, `lost`, `Refused(failureLatched)`, an `outcomeUnknown`
refusal, a `stateUnreadable` or `stateUnsaved` latch) uses the latch clause from `latch_status()` first (A-2) and puts
"task guid <tg>" after it. Non-latching errors (`Rejected`, `NeedsInput`, `ReadFailed`, `Refused(robotNotIdle)`) keep the
Phase 4 `_error_line` text and make no `latch_status` call. The `ran` path makes none either (A-4).

### 6g. ROADMAP settle-at-plan-time answers

- Replay window: `REPLAY_WINDOW_S = 600.0` seconds (F5 repeats arrived within about 1 s).
- Default ledger path: `$XDG_STATE_HOME/galago-tools/stack`, else `~/.local/state/galago-tools/stack`, never `/tmp` (6e).
- Retention: prune `done` records older than `RETENTION_DONE_S = 604800.0` (7 days), on a write only.
- No `ListTransferProfiles`-style extra command and no `Config` field are added: `stack.proto` stays frozen. Every new
  knob is an adapter constant (6d).

---

## 7. Verdict

**No core gap blocks the phase.** Every behaviour the ledger relies on is present at `934a621`: `wait_transfer` observes
foreign guids (section 1), `latch_status()` names the `submit-<hex>` id after an ambiguous submit (section 2), and
`execute_transfer` classifies each outcome so the adapter can release or keep a key (section 3). The two research
amendments A-1 and A-2 are adapter bookkeeping that follow the core's own `_task_ended` and `latch_status`; they work
around nothing. No `/gsd-quick` in stack-automation-layer is needed, and the adapter builds no workaround for any core
behaviour.

**Residual risks to carry into the Phase 7 runbook:**

1. **A typed 5xx or `stackBusy` is released (OQ2).** `Rejected(stage="instrument")` and `Refused(stackBusy)` come back
   after exactly one POST that STACK typed-refused. XFR-04 releases the key. A 5xx whose server side may still have
   acted is covered only by the core's gates (`robotNotIdle`, `inFlight`, `stackBusy`) on the re-run, not by the ledger.
2. **The orphaned core in-flight guard (A-3).** A crash between the core persisting `_inflight` and the adapter's
   `started` write leaves a `submitting` record and a core guard no adapter path waits. The recovery is a read-only
   `wait_transfer(guid)` from stack-mcp using the guid in the `inFlight` refusal.
3. **The ledger directory is never deleted.** It and the core's `STACK_STATE_DIR` must persist across service restarts
   on forb01, and the ledger should be backed up before a restart. A deleted ledger forgets every `submitting` and
   `outcomeUnknown` record, which is exactly the protection against a second transfer.
4. **galago-core's command deadline versus `T = 300 s` (OQ4)** is unconfirmed and must be checked during the Phase 7
   live acceptance.

