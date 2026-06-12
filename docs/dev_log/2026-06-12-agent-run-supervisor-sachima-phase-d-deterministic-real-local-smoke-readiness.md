# Phase D Deterministic Real Local Smoke Readiness — Dev Log

## 2026-06-12 — Gate opened

User approved preparing the readiness gate only:

- pinned local `acpx_binary` scheme;
- prompt materialization scheme;
- PRD / review packet / risk boundaries;
- no real smoke;
- no real AGENT launch;
- no Gateway/Feishu/live;
- no production config writes;
- AGENT split: Hermes controls, Claude Code architecture/docs, Codex primary review;
- if Claude Code quota/usage fails, Codex CLI may substitute for architecture/docs, followed by a separate fresh-context Codex primary review.

Fresh preflight:

- `release/sachima` synced to PR #116 merge.
- No open PRs against `release/sachima` at start.
- `acpx` not found on PATH.
- `codex`, `claude`, `codegraph`, and `gh` available.
- Worktree-local CodeGraph initialized and up to date.

No real smoke or real AGENT execution was run.

## 2026-06-12 — Architecture / documentation-engineer pass (Claude Code attempted, interrupted)

Claude Code began the architect + documentation engineer pass under the Hermes-controlled gate. The pass was docs-only; no commit/push/PR/merge, no production config, no agent/runtime/smoke invoked. Claude Code then hit a session-limit / 429 error after partial docs edits, so Codex CLI substituted for the architecture/docs authoring role as allowed by the user-approved scope.

### Inputs read (read-only context)

- Phase C implementation, manifest, and dev log (PR #114): `sachima_supervisor/activity_controlled_exec.py`, `docs/plans/2026-06-12-...-controlled-local-agent-execution-first-slice-implementation*.{md,yaml}`, `docs/dev_log/...-controlled-local-agent-execution-first-slice-implementation.md`.
- The local/offline seam `sachima_supervisor/local_offline.py` (request shape `LocalOfflineSupervisorRequest`, `invoke_local_offline_supervisor`, boundary checks).
- The committed read-only Codex role config `sachima_supervisor/roles/codex_primary_reviewer_exec_controlled_v1.json` (`acpx_binary: null`).
- `AGENTS.md`, `GOAL.md`, `docs/roadmap/current-status.md`, and the Phase D PRD skeleton (Hermes-owned).

### Key design decisions recorded in the architecture packet

1. **Pinned `acpx` provenance** mapped exactly onto the merged `_check_runner_provenance` gate (role-file `sha256` binding; non-null absolute whitespace-free non-`npx` binary; read-only capability) plus an out-of-band operator step (absolute path + binary `sha256` + sanitized `acpx --version`).
2. **`npx`/network fetch stays forbidden** — argued from strict-offline evidence, the repo dependency-pinning policy (post-litellm / post–Shai-Hulud), and determinism; the gate rejects null and `npx`-basename runners.
3. **No host-local path in committed role JSON.** Decision: keep the committed config null/portable and carry the real path only in an **untracked local-only role overlay**, read via the existing `start_controlled_local_exec(role_root=...)` parameter. No production config write; no host path in git.
4. **Prompt materialization** as a small repo-controlled fixture/builder (mirrors `build_controlled_local_dry_run_evidence`), bounded and harmless, passing `_value_is_unsafe` / `_EXEC_UNSAFE_MARKERS`; only the digest reaches durable state.
5. **Exact construction boundary** = a materialization-aware variant of `_build_local_offline_request` that flips today's hardcoded `prompt=None` to `prompt=<materialized>` after an acquired claim and before the supervisor call, behind all existing gates; one `invoke_local_offline_supervisor` call, one role.
6. **Sanitized evidence** reuses `_validate_claim_state_projection` / `_CLAIM_STATE_KEYS` plus an out-of-PR sanitized record via the seam `evidence_dir` / `_write_evidence` path.
7. **Replay/no-duplicate-launch** proof on the atomic claim/CAS (invocation counter == 1 across an identical replay), **rollback/cleanup** (delete untracked overlay; ephemeral in-process store; nothing production touched), and a **RED-first test/probe plan** with the real-`acpx` smoke gated behind an env marker + pinned binary + installed library (skipped by default).
8. A **Definition of Ready** checklist gating any future smoke.

### New finding — third execution blocker

Read-only preflight on this host showed the `agent_run_supervisor` Python library is **not installed** in any candidate interpreter (system `python3` and the shared `~/.hermes/hermes-agent/venv`). So `invoke_local_offline_supervisor` would raise `supervisor_library_unavailable`. This is a **third** independent execution blocker beyond the two in the baseline (missing pinned `acpx`; deferred prompt materialization). The Phase C suite passes only because tests inject a fake supervisor. Recorded in the architecture packet (§3), the manifest `current_blockers_for_execution`, the user review packet, the PRD, and `docs/roadmap/current-status.md`.

### Files changed in this pass

- `docs/plans/2026-06-12-...-phase-d-...-architecture.md` — placeholder → full readiness design.
- `docs/plans/2026-06-12-...-phase-d-...-user-review-packet.md` — placeholder → presentable approval packet.
- `docs/plans/2026-06-12-...-phase-d-...-manifest.yaml` — added readiness-design schemes, third blocker, Definition of Ready, Claude/Codex/user review-gate placeholders.
- `docs/roadmap/current-status.md` — minimal: readiness gate recorded as docs-only/prepared; Phase D execution stays BLOCKED; non-approvals explicit.
- this dev log.

### Verification (docs-only, safe)

```text
git status --short --branch      # readiness-gate docs only, no code/config changes
git diff --check                 # clean
static greps over docs           # no forbidden surface invoked; approval token matches code
read-only host preflight         # acpx absent; codex/claude present; npx present (forbidden path); agent_run_supervisor absent
```

No `acpx`/`npx`/`codex`/`claude` through the product path, Gateway, Feishu/IM, service/runtime call was made. No real smoke, no real AGENT launch. Codex primary review of this gate is pending.

## 2026-06-12 — Architecture/docs substitution pass (Codex CLI)

Codex CLI continued as the architecture/docs authoring substitute after the Claude Code session-limit / 429 interruption. This is an authoring/documentation pass, **not** the fresh-context Codex primary review.

### Inputs read (read-only context)

- `AGENTS.md`, `GOAL.md`, `docs/roadmap/current-status.md`, and the canonical roadmap `docs/plans/2026-05-11-sachima-final-goal-phase-development-plan.md`.
- Phase D PRD, architecture packet, user review packet, manifest, and this dev log.
- `sachima_supervisor/activity_controlled_exec.py` via CodeGraph for `start_controlled_local_exec`, `_check_runner_provenance`, `_build_local_offline_request`, and the claim/CAS sequence.
- `sachima_supervisor/local_offline.py` via CodeGraph for `LocalOfflineSupervisorRequest`, `build_caller_invocation_spec`, `_resolve_spec_factory`, and `invoke_local_offline_supervisor`.
- `sachima_supervisor/roles/codex_primary_reviewer_exec_controlled_v1.json` confirming committed `acpx_binary: null` and read-only non-runnable role posture.

### Consistency edits

- PRD now records the Claude Code 429 interruption, Codex architecture/docs substitution, the still-pending separate Codex primary review, the third execution blocker (`agent_run_supervisor` absent), and the untracked local-only role overlay decision.
- Architecture packet now separates Codex authoring substitution from Codex primary review and fixes the prompt-materialization construction point to match current code ordering: gates/provenance -> claim/CAS -> materialization-aware seam request -> supervisor call.
- User review packet and manifest now state that committed role JSON stays portable/non-runnable and that host-local `acpx` paths belong only in an untracked overlay.
- `docs/roadmap/current-status.md` now records the docs-only Phase D readiness gate, the Claude 429/Codex authoring substitution, the pending fresh-context Codex primary review, the three blockers, and the explicit non-approvals for no smoke / no AGENT / no `acpx` / no Gateway / no Feishu/live / no production config.

No real smoke, real AGENT, `acpx`, `npx`, Gateway, Feishu/IM, service/runtime start, product-path `codex`/`claude`, or production config write was invoked.

### Verification (docs-only, safe)

```text
git status --short --branch
git diff --check
rg -n "[ \t]+$" <Phase D readiness docs + current-status>
rg -n "<stale contradiction patterns>" <Phase D readiness docs + current-status>
```

Results:

- `git status --short --branch` showed only docs changes: `docs/roadmap/current-status.md` modified and the Phase D PRD / architecture / user packet / manifest / dev log untracked.
- `git diff --check` returned clean.
- trailing-whitespace grep found no matches.
- stale-contradiction grep found no claims that the smoke is approved/run, no primary-review completion claim, no two-blocker wording, and no committed-role-path approval. It only matched the intended negative guardrail wording that host-local paths must not be committed.

## 2026-06-12 — Fresh-context Codex primary review and blocker fix

Codex CLI ran a separate fresh-context primary review in review-only mode. Hermes captured before/after checksums and verified the review did not modify files.

Result:

```text
VERDICT: BLOCK
BLOCKERS:
1. Architecture packet still said the future smoke supplies "two missing real-world inputs" even though the same packet correctly records three execution blockers.
2. PRD next-approval wording conditioned the future smoke on pinned acpx + prompt fixture only, not the full Definition of Ready including installed/pinned agent_run_supervisor.
```

Narrow fixes applied:

- Architecture packet now says the smoke supplies two wrapper-level inputs **plus** requires a pinned/importable `agent_run_supervisor` library.
- PRD, user review packet, and manifest next-approval text now explicitly require the full Definition of Ready, including installed/pinned `agent_run_supervisor`, before any real smoke.

No real smoke, real AGENT, `acpx`, `npx`, Gateway, Feishu/IM, service/runtime start, product-path `codex`/`claude`, or production config write was invoked.

Blocker-only re-review then returned:

```text
VERDICT: PASS
BLOCKERS:
- None.
```

Checksum comparison before/after the review was empty, confirming the review-only Codex pass did not modify files. Remaining gate is PR/CI/user approval; real smoke execution remains separately blocked.
