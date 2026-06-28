# Sachima Roadmap Reference Index

> Extracted from `current-status.md` during the 2026-06-26 status-dashboard slimdown. This file keeps stable reference links and side-capability pointers so the live status page can stay lean.

## Canonical references

- North star: `GOAL.md`
- Gap basis: `docs/sachima-final-goal-gap-analysis.md`
- Canonical roadmap: `docs/plans/2026-05-11-sachima-final-goal-phase-development-plan.md`
- Canonical external protocol: `jovijovi/sachima-protocols` → <https://github.com/jovijovi/sachima-protocols/blob/main/protocols/envelope/v1.md> (`https://github.com/jovijovi/sachima-protocols/blob/main/protocols/envelope/v1.md`)
- Local protocol pointer: `docs/protocols/sachima-envelope-v1.md`
- Latest P4 design packet: `docs/plans/2026-05-12-sachima-envelope-v1-agentic-ui-p4-design-packet.md`
- Latest P4 design dev log: `docs/dev_log/2026-05-12-sachima-envelope-v1-agentic-ui-p4-design-packet.md`
- Latest Sachima-side v1 implementation dev log: `docs/dev_log/2026-05-13-sachima-envelope-v1-local-conformance-implementation.md`
- agent-run-supervisor Sachima local/offline integration design packet: `docs/plans/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-design.md`
- agent-run-supervisor Sachima local/offline integration design dev log: `docs/dev_log/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-design.md`
- agent-run-supervisor Sachima local/offline integration implementation: `docs/plans/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-implementation.md`
- agent-run-supervisor Sachima local/offline integration implementation dev log: `docs/dev_log/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-implementation.md`
- agent-run-supervisor Sachima supervised local Activity design packet: `docs/plans/2026-06-03-agent-run-supervisor-sachima-supervised-local-activity-design.md`
- agent-run-supervisor Sachima supervised local Activity design dev log: `docs/dev_log/2026-06-03-agent-run-supervisor-sachima-supervised-local-activity-design.md`
- agent-run-supervisor Sachima supervised local Activity implementation: `docs/plans/2026-06-03-agent-run-supervisor-sachima-supervised-local-activity-implementation.md`
- agent-run-supervisor Sachima supervised local Activity implementation dev log: `docs/dev_log/2026-06-03-agent-run-supervisor-sachima-supervised-local-activity-implementation.md`
- agent-run-supervisor Sachima supervised local Activity controlled dry-run evidence: `docs/plans/2026-06-03-agent-run-supervisor-sachima-supervised-local-activity-controlled-dry-run-evidence.md` (+ manifest)
- agent-run-supervisor Sachima supervised local Activity controlled dry-run evidence dev log: `docs/dev_log/2026-06-03-agent-run-supervisor-sachima-supervised-local-activity-controlled-dry-run-evidence.md`
- agent-run-supervisor Sachima supervised local Activity controlled dry-run evidence fixture: `tests/fixtures/sachima_supervisor/controlled_local_activity_dry_run_evidence.v1.json`
- agent-run-supervisor Sachima supervised local Activity durable runtime ownership & controlled local execution design packet: `docs/plans/2026-06-04-agent-run-supervisor-sachima-supervised-local-activity-durable-runtime-controlled-local-execution-design.md` (+ manifest)
- agent-run-supervisor Sachima supervised local Activity durable runtime ownership & controlled local execution design dev log: `docs/dev_log/2026-06-04-agent-run-supervisor-sachima-supervised-local-activity-durable-runtime-controlled-local-execution-design.md`
- agent-run-supervisor Sachima supervised local Activity durable-state preflight implementation: `docs/plans/2026-06-08-agent-run-supervisor-sachima-supervised-local-activity-durable-state-preflight-implementation.md` (+ manifest)
- agent-run-supervisor Sachima supervised local Activity durable-state preflight implementation dev log: `docs/dev_log/2026-06-08-agent-run-supervisor-sachima-supervised-local-activity-durable-state-preflight-implementation.md`
- agent-run-supervisor Sachima controlled local agent execution first slice (Phase C) implementation: `docs/plans/2026-06-12-agent-run-supervisor-sachima-controlled-local-agent-execution-first-slice-implementation.md` (+ manifest)
- agent-run-supervisor Sachima controlled local agent execution first slice (Phase C) dev log: `docs/dev_log/2026-06-12-agent-run-supervisor-sachima-controlled-local-agent-execution-first-slice-implementation.md`
- agent-run-supervisor Sachima Phase D deterministic real local smoke readiness gate (docs-only; design/readiness only; no smoke run): `docs/plans/2026-06-12-agent-run-supervisor-sachima-phase-d-deterministic-real-local-smoke-readiness-prd.md`, `docs/plans/2026-06-12-agent-run-supervisor-sachima-phase-d-deterministic-real-local-smoke-readiness-architecture.md`, `docs/plans/2026-06-12-agent-run-supervisor-sachima-phase-d-deterministic-real-local-smoke-readiness-user-review-packet.md` (+ manifest)
- agent-run-supervisor Sachima Phase D deterministic real local smoke readiness gate dev log: `docs/dev_log/2026-06-12-agent-run-supervisor-sachima-phase-d-deterministic-real-local-smoke-readiness.md`
- agent-run-supervisor Sachima Phase D smoke prerequisites implementation (prerequisites preparation only; no smoke run): `docs/plans/2026-06-12-agent-run-supervisor-sachima-phase-d-smoke-prerequisites-implementation.md` (+ manifest)
- agent-run-supervisor Sachima Phase D smoke prerequisites implementation dev log: `docs/dev_log/2026-06-12-agent-run-supervisor-sachima-phase-d-smoke-prerequisites.md`
- agent-run-supervisor Sachima Phase D smoke prompt fixture: `tests/fixtures/sachima_supervisor/phase_d_smoke_prompt.v1.txt` (builder `sachima_supervisor/smoke_prompt.py`)
- agent-run-supervisor Sachima Phase D deterministic real local smoke manifest: `docs/plans/2026-06-12-agent-run-supervisor-sachima-phase-d-real-local-smoke-manifest.yaml`
- agent-run-supervisor Sachima Phase D deterministic real local smoke dev log: `docs/dev_log/2026-06-12-agent-run-supervisor-sachima-phase-d-real-local-smoke.md`
- agent-run-supervisor Sachima Phase E persistent sessions / cancellation design packet (docs-only; design only; merged in PR #123): `docs/plans/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-sessions-cancellation-design.md` (+ manifest `docs/plans/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-sessions-cancellation-design-manifest.yaml`)
- agent-run-supervisor Sachima Phase E persistent sessions / cancellation design dev log: `docs/dev_log/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-sessions-cancellation-design.md`
- agent-run-supervisor Sachima Phase E persistent-session lifecycle preflight / state-machine implementation (local/offline only; injected fakes only; merged in PR #125): `docs/plans/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-session-lifecycle-state-machine-implementation.md` (+ manifest `docs/plans/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-session-lifecycle-state-machine-implementation-manifest.yaml`)
- agent-run-supervisor Sachima Phase E persistent-session lifecycle preflight / state-machine implementation dev log: `docs/dev_log/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-session-lifecycle-state-machine-implementation.md`
- agent-run-supervisor Sachima Phase E-2 bounded real persistent-session execution (local/offline only; pinned local acpx only; default-off; merged in PR #127): `docs/plans/2026-06-13-agent-run-supervisor-sachima-phase-e2-bounded-real-persistent-session-execution.md` (+ manifest `docs/plans/2026-06-13-agent-run-supervisor-sachima-phase-e2-bounded-real-persistent-session-execution-manifest.yaml`)
- agent-run-supervisor Sachima Phase E-2 bounded real persistent-session execution dev log: `docs/dev_log/2026-06-13-agent-run-supervisor-sachima-phase-e2-bounded-real-persistent-session-execution.md`
- agent-run-supervisor Sachima Phase E-2 bridge module: `sachima_supervisor/activity_session_real_execution.py` (committed portable role `sachima_supervisor/roles/session_worker_persistent_v1.json`; smoke `scripts/sachima_phase_e2_persistent_session_smoke.py`; tests `tests/sachima_supervisor/test_activity_session_real_execution.py`)
- agent-run-supervisor Sachima remaining-goals plan and implementation roadmap (docs-only; merged in PR #128; Claude Code architect draft + Codex blocker review PASS; recommends WP1a next): `docs/plans/2026-06-13-agent-run-supervisor-sachima-remaining-goals-plan-and-implementation-roadmap.md` (+ manifest `docs/plans/2026-06-13-agent-run-supervisor-sachima-remaining-goals-plan-and-implementation-roadmap-manifest.yaml`; dev log `docs/dev_log/2026-06-13-agent-run-supervisor-sachima-remaining-goals-plan-and-implementation-roadmap.md`)
- agent-run-supervisor Sachima WP1a Claude Code read-only role + capability-gate extension (local/offline; injected fakes / self-test only; merged in PR #131, merge commit `d2e8c49f7042715062ec755eb8177396d6df3bcd`; Codex primary blocker review PASS; PR checks passed): `docs/plans/2026-06-14-agent-run-supervisor-sachima-wp1a-claude-code-read-only-role-implementation.md` (+ manifest `docs/plans/2026-06-14-agent-run-supervisor-sachima-wp1a-claude-code-read-only-role-implementation-manifest.yaml`; dev log `docs/dev_log/2026-06-14-agent-run-supervisor-sachima-wp1a-claude-code-read-only-role-implementation.md`); code `sachima_supervisor/activity_controlled_exec.py` + committed role `sachima_supervisor/roles/claude_code_read_only_reviewer_v1.json`; smoke `scripts/sachima_claude_code_read_only_smoke.py`; tests `tests/sachima_supervisor/test_claude_code_read_only_role.py` + WP1a additions in `tests/sachima_supervisor/test_activity_controlled_exec.py`
- agent-run-supervisor Sachima WP1b Claude Code read-only smoke dependency/install/invocation note (docs-only prerequisite; no smoke/acpx invocation): `docs/runbooks/agent-run-supervisor-wp1b-claude-code-read-only-smoke-dependency-installation-invocation.md` (+ manifest `docs/plans/2026-06-14-agent-run-supervisor-sachima-wp1b-claude-code-read-only-smoke-dependency-installation-invocation-manifest.yaml`)
- agent-run-supervisor Sachima WP2 bounded multi-turn persistent session hardening (local/offline only; merged in PR #137 per machine status block): dev log `docs/dev_log/2026-06-15-agent-run-supervisor-sachima-wp2-bounded-multi-turn-persistent-session-hardening.md`; code `scripts/sachima_phase_e2_persistent_session_smoke.py`; tests `tests/sachima_supervisor/test_activity_session_real_execution.py`
- agent-run-supervisor Sachima WP3a cancellation request-state + supervisor interrupt API (merged in PR #138, merge commit `c74c2302129d2e9e1409910966c1075b4b19fabf`; local gates, final Codex blocker-only re-review, and PR CI passed; local/offline injected-fake interrupt API state machine only; no real interrupt; no real cancellation execution): `docs/plans/2026-06-15-agent-run-supervisor-sachima-wp3a-cancellation-request-state-interrupt-api.md` (+ manifest `docs/plans/2026-06-15-agent-run-supervisor-sachima-wp3a-cancellation-request-state-interrupt-api-manifest.yaml`; dev log `docs/dev_log/2026-06-15-agent-run-supervisor-sachima-wp3a-cancellation-request-state-interrupt-api.md`); code `sachima_supervisor/activity_session_lifecycle.py`; tests `tests/sachima_supervisor/test_activity_session_lifecycle.py`
- agent-run-supervisor Sachima WP3b bounded real cancellation execution (merged in PR #140, merge commit `3fe18ab9451d290a70036697da118351d604be27`; local/offline only; deterministic self-test/fail-closed cancellation bridge verified; real host/ACP `--cancel-during-turn` did not reliably prove active-run cancellation and remains WATCH): code `sachima_supervisor/activity_session_real_execution.py`, `sachima_supervisor/activity_session_lifecycle.py`; smoke script `scripts/sachima_phase_e2_persistent_session_smoke.py`; tests `tests/sachima_supervisor/test_activity_session_real_execution.py`
- agent-run-supervisor Sachima WP4 controlled AI FLOW local/offline orchestration design (merged in PR #142, merge commit `bb5e5d9bf707fde7934939cc473544511bd65ffd`; docs-only design packet; no implementation/execution/write roles/live/Gateway/Feishu/production config/real delivery): `docs/plans/2026-06-17-agent-run-supervisor-sachima-wp4-controlled-ai-flow-local-offline-orchestration-design.md` (+ manifest `docs/plans/2026-06-17-agent-run-supervisor-sachima-wp4-controlled-ai-flow-local-offline-orchestration-design-manifest.yaml`; dev log `docs/dev_log/2026-06-17-agent-run-supervisor-sachima-wp4-controlled-ai-flow-local-offline-orchestration-design.md`)
- PE-2 design packet: `docs/plans/2026-05-12-flowweaver-pe2-design-packet.md`
- Latest PE-2A dev log: `docs/dev_log/2026-05-12-flowweaver-pe2a-controlled-runtime-fake-delivery.md`


- agent-run-supervisor Sachima P6 runtime lifecycle / controlled attach plan (docs-only candidate): `docs/plans/2026-06-28-agent-run-supervisor-sachima-p6-runtime-lifecycle-controlled-attach-plan-prd.md`, `docs/plans/2026-06-28-agent-run-supervisor-sachima-p6-runtime-lifecycle-controlled-attach-plan-technical-solution.md`, `docs/plans/2026-06-28-agent-run-supervisor-sachima-p6-runtime-lifecycle-controlled-attach-plan-user-review-packet.md` (+ manifest)
- agent-run-supervisor Sachima P6 runtime lifecycle / controlled attach plan dev log: `docs/dev_log/2026-06-28-agent-run-supervisor-sachima-p6-runtime-lifecycle-controlled-attach-plan.md`

## Side capability references

These references are not phase approvals, but they preserve implementation state
for cross-cutting Sachima/Hermes capabilities that future work may need to
re-enter.

- xAI/Grok Imagine multi-reference image generation status snapshot:
  `docs/dev_log/2026-06-25-xai-multi-reference-image-generation-status.md`
- xAI Imagine API refresh PRD:
  `docs/plans/2026-06-19-xai-imagine-api-refresh-prd.md`
- xAI Imagine API refresh dev log:
  `docs/dev_log/2026-06-19-xai-imagine-api-refresh.md`
