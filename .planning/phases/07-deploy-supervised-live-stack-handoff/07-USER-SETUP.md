# Phase 07 User Setup

Status: **Complete — nothing external remains to set up.**

| Service | Why it was listed | Resolution |
|---------|-------------------|------------|
| gitlab.formulatrix.com (GitLab https auth) | Plan 07-02's pinned `git+https` core install (D-04) could not authenticate: the git-credential-oauth helper launched an interactive OAuth device flow and stalled. The choice was credentials vs an explicit D-04 waiver. | Resolved at the OQ-1 blocking-human checkpoint (runbook row 1a-1, 2026-11-02T11:16:00Z): the user chose `local-clone-waiver` and the install used the verified local clone (`/home/formulatrix/data/nikko/stack-automation-layer` HEAD == pin `934a621…`). |

- Environment variables to add: none (the credentials env vars `STACK_USER`/`STACK_PASSWORD` were
  already operator-created in the 0600 file `~/.config/galago-tools/stack.env` per D-06 —
  presence-only verified, values never read; see findings row 1a-3).
- Dashboard configuration steps: none outstanding.
- Verification commands: `bash docs/runbooks/gal-07-live-check.sh` (expects, post-deploy, at most
  the known owner-lock advisory/residue; see `deferred-items.md` in this phase directory).

Deferred (user's own action, unchanged): pushing branches is outside every deploy step (D-02).
