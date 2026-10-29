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

