# Phase 7 API Coverage Matrix (COVERAGE.md)

- **AI statement:** Phase 7 introduces no AI/LLM capability - no model, prompt, agent, embedding or retrieval work exists in any plan or artifact. The ai-integration framework's provider/eval side (AI-SPEC, eval dimensions) does not apply here; the COVERAGE concern reduces to the API enumeration below.

| capability | decision | reason |
|---|---|---|
| STACK manager REST /api/v2 transfer + estimation + status polls | INTEGRATE | Live-proven: 07-01 gate checks 1-8; stack_test.py 271 adapter tests; ledger keys LIVE-09 + 4 LIVE-10 legs all done (rows 3a-*) |
| STACK manager /api/general/application identity probe | INTEGRATE | Gate check 1 requires productName "Stack manager"; wrong-identity refusal trial pinned in gal07 tests; live row 1a-5 |
| STACK owner-lock namespace probe (pinned core helpers + flock) | INTEGRATE | Gate check 2 via pinned-core helpers only (D-05); galago single-owner ok: after 9344957; both holder dispositions test-pinned; live rows 3a-* |
| F.A.S.T. panel :5003 /status polling + internal liquid transfer | INTEGRATE | Reached only via the FA100056 tool server (tunnel 127.0.0.1:5003); FA100056.log progress 0->100% + SUCCESS 05:42:29Z (row 3a-2); deck/bounds rules pinned in fast tests |
| galago-core store :3010 (tools, health, protocols GET/POST, trpc delete, runs) | INTEGRATE | Import/delete proven live in the D-14 chain (row 3a-1) and dev-side by gal-02 row 2a-1; D-12 gates check 6 re-asserts both tool types |
| ToolDriver GetStatus generic read (:40012 / :40001) | INTEGRATE | scripts/fast_status.py, the v1-proven read-only checker reused for every restart check (rows 1a-4, 3a-3); no new client code |
| AI/LLM provider integration (models, prompts, agents, embeddings) | OPT-OUT | No AI capability built or invoked anywhere in this phase - the gsd-ai-integration-phase framework has no subject; re-run this matrix when a future phase adds AI work |
| Third-party SaaS/auth surfaces (OAuth device flows, cloud APIs) | OPT-OUT | The pinned git+https URL needs browser auth; the phase never drives it headlessly - the OQ-1 local-clone-waiver (row 1a-1) honors D-04 without host credentials |

Signed: 2026-11-03, recorded on /gsd-execute-phase 7's verification path (the verify:pre api-coverage gate fired on the phase's legitimate API wording).
