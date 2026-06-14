# Sachima Roadmap Current Status

> Living dashboard. This file tracks the current roadmap position and drift guards for Sachima / FlowWeaver work. It does not replace the canonical roadmap.

```text
last_updated: 2026-06-14
base_branch: release/sachima
latest_behavior_phase: PE-2A controlled runtime + fake delivery
latest_behavior_phase_sha: 1f587a0b0355f7eb18a2cdff64bc1bc93ea109dd
latest_design_packet: P4 Sachima Envelope v1 / agentic-ui controlled external ingress design packet
latest_design_packet_doc: docs/plans/2026-05-12-sachima-envelope-v1-agentic-ui-p4-design-packet.md
latest_supervisor_integration_design_packet: agent-run-supervisor × Sachima local/offline integration design (docs-only; design only)
latest_supervisor_integration_design_packet_doc: docs/plans/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-design.md
latest_supervisor_integration_implementation: agent-run-supervisor × Sachima local/offline integration implementation (default-off; local/offline only)
latest_supervisor_integration_implementation_doc: docs/plans/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-implementation.md
latest_supervised_local_activity_design_packet: agent-run-supervisor × Sachima supervised local Activity design (docs-only; design only)
latest_supervised_local_activity_design_packet_doc: docs/plans/2026-06-03-agent-run-supervisor-sachima-supervised-local-activity-design.md
latest_supervised_local_activity_implementation: agent-run-supervisor × Sachima supervised local Activity implementation (exec_dry_run; injected supervisor only; local/offline only)
latest_supervised_local_activity_implementation_doc: docs/plans/2026-06-03-agent-run-supervisor-sachima-supervised-local-activity-implementation.md
latest_supervised_local_activity_controlled_dry_run_evidence: agent-run-supervisor × Sachima supervised local Activity controlled local dry-run evidence (injected/fake supervisor only; local/offline only)
latest_supervised_local_activity_controlled_dry_run_evidence_doc: docs/plans/2026-06-03-agent-run-supervisor-sachima-supervised-local-activity-controlled-dry-run-evidence.md
latest_supervised_local_activity_durable_runtime_controlled_local_execution_design: agent-run-supervisor × Sachima supervised local Activity durable runtime ownership & controlled local execution design (docs-only; design only; merged in PR #102)
latest_supervised_local_activity_durable_runtime_controlled_local_execution_design_doc: docs/plans/2026-06-04-agent-run-supervisor-sachima-supervised-local-activity-durable-runtime-controlled-local-execution-design.md
latest_supervised_local_activity_durable_state_preflight_implementation: agent-run-supervisor × Sachima supervised local Activity durable-state preflight implementation (local/offline only; merged in PR #107)
latest_supervised_local_activity_durable_state_preflight_implementation_doc: docs/plans/2026-06-08-agent-run-supervisor-sachima-supervised-local-activity-durable-state-preflight-implementation.md
latest_controlled_local_exec_implementation: agent-run-supervisor × Sachima controlled local agent execution first slice (Phase C; exec_controlled one-shot wrapper; local/offline only; default-off; merged in PR #114, merge commit 21d1bafc22c6fcde2bb0af6fff6becfb0886cf4f; real local smoke NOT run)
latest_controlled_local_exec_implementation_doc: docs/plans/2026-06-12-agent-run-supervisor-sachima-controlled-local-agent-execution-first-slice-implementation.md
latest_phase_d_real_local_smoke_readiness_gate: agent-run-supervisor × Sachima Phase D deterministic real local smoke readiness gate (docs-only; no smoke run; Claude Code attempted architecture/docs and hit session-limit / 429; Codex CLI substituted for architecture/docs authoring; Codex primary re-review PASS / BLOCKERS None; merged in PR #117, merge commit eb7227301d715b40d4eb6628bf32fb800017bd42)
latest_phase_d_real_local_smoke_readiness_gate_doc: docs/plans/2026-06-12-agent-run-supervisor-sachima-phase-d-deterministic-real-local-smoke-readiness-prd.md
latest_phase_d_smoke_prerequisites_implementation: agent-run-supervisor × Sachima Phase D smoke prerequisites implementation (pinned local acpx provenance verifier with injected probe; deterministic prompt materialization fixture/builder + explicit prompt_materializer seam defaulting to Phase C prompt=None; agent_run_supervisor exact-pin checker; local/offline, injected fakes only; no smoke run; merged in PR #119, merge commit 0c9e4342e2befe1db6ecf5774c51b313c8bb5f5b; Codex blocker-only re-review PASS; PR checks and post-merge local verification passed)
latest_phase_d_smoke_prerequisites_implementation_doc: docs/plans/2026-06-12-agent-run-supervisor-sachima-phase-d-smoke-prerequisites-implementation.md
latest_phase_d_real_local_smoke_execution: agent-run-supervisor × Sachima Phase D deterministic real local smoke (host-local read-only Codex one-shot; pinned local acpx 0.10.0; prompt affordance repaired with inline JSON projection; execution pipeline PASS and business verdict PASS; no Gateway/Feishu/live; no production config; evidence outside repo)
latest_phase_d_real_local_smoke_execution_doc: docs/dev_log/2026-06-12-agent-run-supervisor-sachima-phase-d-real-local-smoke.md
latest_phase_e_persistent_sessions_cancellation_design: agent-run-supervisor × Sachima Phase E persistent sessions / cancellation design (docs-only; design only; merged in PR #123, merge commit 9e435eb443de67a923c43787f5ef7cb8ae8ad981)
latest_phase_e_persistent_sessions_cancellation_design_doc: docs/plans/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-sessions-cancellation-design.md
latest_phase_e_persistent_sessions_cancellation_design_manifest: docs/plans/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-sessions-cancellation-design-manifest.yaml
latest_phase_e_persistent_sessions_cancellation_design_dev_log: docs/dev_log/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-sessions-cancellation-design.md
latest_phase_e_persistent_session_lifecycle_implementation: agent-run-supervisor × Sachima Phase E persistent session lifecycle preflight / state-machine implementation (local/offline only; injected fakes only; merged in PR #125, merge commit a564a775f809cfdd08209863702d0249610dd286; no real session launch; no cancellation execution; no real AGENT/acpx/npx; no live/Gateway/Feishu/production config/real delivery; post-merge local verification passed)
latest_phase_e_persistent_session_lifecycle_implementation_doc: docs/plans/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-session-lifecycle-state-machine-implementation.md
latest_phase_e_persistent_session_lifecycle_implementation_manifest: docs/plans/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-session-lifecycle-state-machine-implementation-manifest.yaml
latest_phase_e_persistent_session_lifecycle_implementation_dev_log: docs/dev_log/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-session-lifecycle-state-machine-implementation.md
latest_phase_e2_bounded_real_persistent_session_execution: agent-run-supervisor × Sachima Phase E-2 bounded real persistent-session execution (local/offline only; pinned local acpx only; default-off; CI-safe; merged in PR #127 (merge commit `813c0eb051efd822d214b2cd8619b8a941536abb`); local tests + self-test smoke + one minimal real smoke pass; Codex blocker-only re-review PASS; no cancellation execution; no live/Gateway/Feishu/production config/real delivery)
latest_phase_e2_bounded_real_persistent_session_execution_doc: docs/plans/2026-06-13-agent-run-supervisor-sachima-phase-e2-bounded-real-persistent-session-execution.md
latest_phase_e2_bounded_real_persistent_session_execution_manifest: docs/plans/2026-06-13-agent-run-supervisor-sachima-phase-e2-bounded-real-persistent-session-execution-manifest.yaml
latest_phase_e2_bounded_real_persistent_session_execution_dev_log: docs/dev_log/2026-06-13-agent-run-supervisor-sachima-phase-e2-bounded-real-persistent-session-execution.md
latest_ars_remaining_goals_plan: agent-run-supervisor × Sachima remaining-goals plan and implementation roadmap (docs-only planning gate; Claude Code architect draft; Codex CLI blocker-only review PASS; Hermes accepted with WP1a/WP1b split; merged in PR #128, merge commit `ae27fbf458b32d05a85703095102c79c17c14071`; docs-only planning gate; no implementation/execution/additional acpx/live/Gateway/Feishu/production config/real delivery approval)
latest_ars_remaining_goals_plan_doc: docs/plans/2026-06-13-agent-run-supervisor-sachima-remaining-goals-plan-and-implementation-roadmap.md
latest_ars_remaining_goals_plan_manifest: docs/plans/2026-06-13-agent-run-supervisor-sachima-remaining-goals-plan-and-implementation-roadmap-manifest.yaml
latest_ars_remaining_goals_plan_dev_log: docs/dev_log/2026-06-13-agent-run-supervisor-sachima-remaining-goals-plan-and-implementation-roadmap.md
latest_protocol_repo: jovijovi/sachima-protocols
latest_protocol_spec: https://github.com/jovijovi/sachima-protocols/blob/main/protocols/envelope/v1.md
latest_protocol_implementation: P4 Sachima Envelope v1 local conformance implementation (Sachima-side)
latest_protocol_implementation_doc: docs/dev_log/2026-05-13-sachima-envelope-v1-local-conformance-implementation.md
current_position: P4 Sachima-side local conformance implemented; agentic-ui/cross-repo conformance pending as a side tail; agent-run-supervisor → Sachima local/offline integration, supervised local Activity, controlled dry-run evidence, durable-state preflight, and Phase C controlled local exec wrapper have merged; Phase D readiness docs merged in PR #117 and repo-side smoke prerequisites merged in PR #119; after separate user approvals, host-local DoR provisioning passed and one deterministic Phase D real local read-only Codex smoke ran through pinned local acpx 0.10.0 with execution pipeline PASS and business verdict PASS. Evidence is stored outside the repo under `/home/ubuntu/workspace/hermes/outputs/sachima/phase-d-real-local-smoke/`. This proves one bounded local read-only smoke only; write-capable roles, Satine/Hermes-profile ACP, controlled AI FLOW execution, live/public ingress, Gateway/Feishu involvement, production config writes, and real delivery remain unapproved. The Phase E persistent sessions / cancellation docs-only design packet merged in PR #123. The Phase E persistent-session lifecycle preflight / state-machine implementation merged in PR #125 (merge commit a564a775f809cfdd08209863702d0249610dd286); it is local/offline only with injected fakes, no real session launch, no cancellation execution, no real AGENT/acpx/npx, and no live/Gateway/Feishu/production config/real delivery. After a separate user approval, the Phase E-2 bounded real persistent-session execution slice merged in PR #127 (merge commit `813c0eb051efd822d214b2cd8619b8a941536abb`): a default-off, fail-closed, CI-safe bridge that lets the merged Phase E lifecycle state machine drive a real local pinned-acpx persistent session for create / one read-only turn / close, plus a committed non-runnable persistent role and a reproducible smoke script. Local focused tests (44), Phase E lifecycle tests (106), the full supervisor suite (475), compileall, git diff --check, smoke `--self-test`, and one minimal real smoke pass. The real smoke evidence is outside the repo under `/data/agents/workspace/hermes/outputs/sachima/phase-e2-bounded-real-persistent-session-execution/20260613T063219Z/`; it verified create/session_open, one completed turn, close/session_closed, external supervisor session.json closed, exactly one supervisor session and turn, business marker match, `final_message_persisted=false`, no npx runner, and all non-approvals. Codex blocker-only re-review PASS / BLOCKERS None. It holds all prior non-approvals and adds no cancellation execution, no npx/network runnable fallback, and no live/Gateway/Feishu/production config/real delivery. The docs-only remaining-goals plan merged in PR #128 (merge commit `ae27fbf458b32d05a85703095102c79c17c14071`) and records WP1a as the next implementation gate: Claude Code read-only role + capability-gate extension with injected fakes only; WP1b real read-only smoke stays separate.
implementation_marker_note: no live / no Gateway / no real delivery / Phase D real local read-only smoke PASS only / controlled one-shot exec wrapper + smoke prerequisites preparation + single smoke evidence / Phase E local-offline lifecycle state-machine only / Phase E-2 bounded real persistent-session execution bridge merged in PR #127 (default-off; pinned local acpx only; one minimal real smoke + Codex review PASS) / remaining-goals plan merged in PR #128 (WP1a next; WP1b separate)
```

## Canonical references

- North star: `GOAL.md`
- Gap basis: `docs/sachima-final-goal-gap-analysis.md`
- Canonical roadmap: `docs/plans/2026-05-11-sachima-final-goal-phase-development-plan.md`
- Canonical external protocol: `jovijovi/sachima-protocols` → `protocols/envelope/v1.md` (`https://github.com/jovijovi/sachima-protocols/blob/main/protocols/envelope/v1.md`)
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
- agent-run-supervisor Sachima Phase D deterministic real local smoke readiness gate (docs-only; design/readiness only; no smoke run): `docs/plans/2026-06-12-agent-run-supervisor-sachima-phase-d-deterministic-real-local-smoke-readiness-prd.md`, `...-architecture.md`, `...-user-review-packet.md` (+ manifest)
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
- PE-2 design packet: `docs/plans/2026-05-12-flowweaver-pe2-design-packet.md`
- Latest PE-2A dev log: `docs/dev_log/2026-05-12-flowweaver-pe2a-controlled-runtime-fake-delivery.md`

## How to use this file

Before any roadmap, phase, PR, CI, merge, review, or next-phase-readiness work:

1. Read this file.
2. Read the canonical roadmap linked above.
3. Read the latest relevant dev log and evidence links below.
4. State the current phase, next allowed request, explicit non-approvals, and open tails before changing files.

If this file is stale or contradicts a requested task, stop and report the drift risk.

## Current phase map

| Phase | Status | Evidence / decision | Strongest current meaning |
|---|---|---|---|
| P1 — PE-1D longer controlled local observation | Done | PE-1D evidence path listed below; PR #78 governance validation, merge `8ad7f90f9e96afd6740508bd89df062f1eeb9f1e` | Ready for fake-send / PE-2 design evidence use; exact default-port behavior remains WATCH |
| P2 — Fake-send / simulator delivery loop | Done | PR #79 design, PR #80 implementation; merge `10486c7c585974dce3f37c74437ada3419d67904` for implementation | Fake delivery and ACK semantics proven locally; does not approve real delivery |
| P3 — PE-2 design packet only | Done | PR #81, merge `84f6a9010d72fe6ab3a0dac4ecaea3c3fb252ddf` | May request separately approved PE-2A implementation; not live or real ingress |
| Bridge — PE-2A controlled runtime + fake delivery | Done | PR #82, merge `1f587a0b0355f7eb18a2cdff64bc1bc93ea109dd` | Controlled local runtime-delivery bridge proven with fake delivery; does not approve real external ingress |
| P4 — Controlled external ingress | Sachima-side local conformance implemented; agentic-ui/cross-repo pending | `jovijovi/sachima-protocols` → `protocols/envelope/v1.md`; local pointer `docs/protocols/sachima-envelope-v1.md`; design packet `docs/plans/2026-05-12-sachima-envelope-v1-agentic-ui-p4-design-packet.md`; implementation dev log `docs/dev_log/2026-05-13-sachima-envelope-v1-local-conformance-implementation.md` | Canonical external envelope has Sachima-side local implementation; agentic-ui conformance, public exposure, live ingress, and real delivery still require separate approval |
| Design — agent-run-supervisor local/offline supervisor integration | Done (docs-only) | Design packet `docs/plans/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-design.md` + manifest + dev log | Defines a caller-owned local supervisor library seam (caller is a Sachima/FlowWeaver/Hermes controller, not Gateway); does not approve live behavior, Gateway involvement, or real delivery |
| Implementation — agent-run-supervisor local/offline supervisor integration | Local/offline implementation added (default-off, non-Gateway) | Implementation doc `docs/plans/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-implementation.md`; code under `sachima_supervisor/`; tests under `tests/sachima_supervisor/`; PR #97 merge `5affc2fbb68d483683cd61c0871cec528127388e` | Provides a caller-owned local/offline seam and sanitized offline evidence/view model; does not approve controlled AI FLOW execution, live/default-on behavior, Gateway involvement, real ingress, or real delivery |
| Design — agent-run-supervisor supervised local Activity | Design packet added (docs-only) | Design packet `docs/plans/2026-06-03-agent-run-supervisor-sachima-supervised-local-activity-design.md` + manifest + dev log; PR #98 merge `675853fd2db2b8f9df781ea46803fd0747ea78cb` | Defines Sachima/FlowWeaver Activity request/response, role mapping, state, retry/query/update semantics around the local/offline seam; does not approve runtime implementation, controlled AI FLOW execution, live/default-on behavior, Gateway involvement, real ingress, or real delivery |
| Implementation — agent-run-supervisor supervised local Activity | Done (local/offline first slice) | Implementation doc `docs/plans/2026-06-03-agent-run-supervisor-sachima-supervised-local-activity-implementation.md`; code under `sachima_supervisor/activity.py`; tests under `tests/sachima_supervisor/test_activity.py`; PR #99 merge `8152d09ee0f847d335a76e2ef90459642fb72e9d` | Provides an `exec_dry_run` Activity wrapper with injected supervisor calls only, role-map allowlist, idempotency, sanitized durable state/query results, and no-leak tests; does not approve real local exec/sessions, controlled AI FLOW execution, live/default-on behavior, Gateway involvement, real ingress, or real delivery |
| Evidence — supervised local Activity controlled dry-run | Done (local/offline fixtures) | PR #100 merge `3fea6e2e8ee836e924c3e0eef1b3ff3a2b930c59`; fixture `tests/fixtures/sachima_supervisor/controlled_local_activity_dry_run_evidence.v1.json`; builder `sachima_supervisor/activity_evidence.py` | Proves the Activity wrapper can produce deterministic local dry-run evidence without real AGENT execution; does not approve real local exec/sessions, controlled AI FLOW execution, live/default-on behavior, Gateway involvement, real ingress, or real delivery |
| Design — supervised local Activity durable runtime ownership & controlled local execution | Done (docs-only) | Design packet `docs/plans/2026-06-04-agent-run-supervisor-sachima-supervised-local-activity-durable-runtime-controlled-local-execution-design.md` + manifest + dev log; PR #102 merge `e49709d6e960b8e11f8e220fa087488132f64f93`; base `3b917eeff1c782cea2075909061037816c4eff93` (PR #101) | Defines that Sachima/FlowWeaver owns durable product/transaction/Activity state, leases, idempotency, retry/update/close policy, role mapping, claim-check refs, and the business decision to request a future local execution; supervisor stays an independent local library; Gateway excluded; runtime is caller-supplied. Design labels only — does not approve implementation, real local exec, sessions, cancellation execution, real AGENT execution, controlled AI FLOW execution, live/default-on behavior, Gateway involvement, real ingress, or real delivery |
| Implementation — supervised local Activity durable-state preflight | Done (local/offline only) | Plan `docs/plans/2026-06-08-agent-run-supervisor-sachima-supervised-local-activity-durable-state-preflight-implementation.md` + manifest + dev log; code `sachima_supervisor/activity_preflight.py`; tests `tests/sachima_supervisor/test_activity_durable_state_preflight.py`; PR #107 merge `6795da2930324cde1448586e71ff8d80bc6e9ae1` | Adds a fail-closed preflight that validates exact approval, `exec_dry_run`, role allowlist, prior dry-run evidence digest, lease, state version, idempotency, operator gate, budgets, and sanitized refs before storing a sanitized query projection; no supervisor call, no runtime start, no real local exec/sessions/cancellation, no real AGENT execution, no controlled AI FLOW execution, no live/Gateway/real delivery |
| Implementation — controlled local agent execution first slice (Phase C) | Merged in PR #114; real local smoke NOT run | Plan `docs/plans/2026-06-12-agent-run-supervisor-sachima-controlled-local-agent-execution-first-slice-implementation.md` + manifest + dev log; code `sachima_supervisor/activity_controlled_exec.py` + `sachima_supervisor/roles/codex_primary_reviewer_exec_controlled_v1.json`; tests `tests/sachima_supervisor/test_activity_controlled_exec.py` (112 new incl. 4 true-concurrency claim/CAS tests; suite 229 green); PR #114 merge `21d1bafc22c6fcde2bb0af6fff6becfb0886cf4f`; PRD gate + user approval 2026-06-12 | Adds the default-off `exec_controlled` one-shot wrapper over the public local/offline supervisor boundary: pinned-local-acpx no-fetch provenance (role-file sha256 binding; committed role config truthfully null-binary and not runnable), atomic pre-launch claim/CAS via a lock-guarded in-process store (single mutex around every check-and-set; concurrent identical starts launch exactly once, concurrent conflicts fail closed pre-launch; cross-process durable store adapter is a later gate) with in-progress/terminal replay and fail-closed conflicts, preflight/lease/state-version binding, exact operator gate, read-only Codex primary reviewer as the only runnable role, sanitized claim state/query, business_verdict permanently null; does not run or approve real local smoke, persistent sessions, cancellation, write-capable roles, Satine, controlled AI FLOW execution, live/Gateway/real delivery |
| Readiness — Phase D deterministic real local smoke | Merged in PR #117; docs-only readiness superseded by later DoR/smoke PASS | PRD / architecture / user review packet / manifest / dev log under `docs/plans/2026-06-12-agent-run-supervisor-sachima-phase-d-deterministic-real-local-smoke-readiness-*`; Claude Code attempted architecture/docs then hit session-limit / 429; Codex CLI substituted for authoring; Codex primary re-review PASS / BLOCKERS None; PR #117 merge `eb7227301d715b40d4eb6628bf32fb800017bd42` | Defines pinned local `acpx` provisioning, untracked local-only role overlay, prompt materialization scheme, sanitized evidence, replay proof, and Definition of Ready. PR #117 itself ran no smoke, no AGENT, no `acpx`, no Gateway/Feishu/live, no service/runtime, and no production config. The later host-local DoR and single read-only smoke were separate approvals recorded below. |
| Implementation — Phase D smoke prerequisites | Merged in PR #119; local/post-merge verification passed; subsequent smoke PASS recorded separately | Plan `docs/plans/2026-06-12-agent-run-supervisor-sachima-phase-d-smoke-prerequisites-implementation.md` + manifest + dev log; code `sachima_supervisor/activity_controlled_exec.py` (provenance helper + `prompt_materializer` seam), `sachima_supervisor/smoke_prompt.py`, `sachima_supervisor/supervisor_library.py`; fixture `tests/fixtures/sachima_supervisor/phase_d_smoke_prompt.v1.txt`; tests `tests/sachima_supervisor/` (suite 325 green incl. new provenance/materializer/pin tests and the Codex round-1 review-fix tests); PR #119 merge `0c9e4342e2befe1db6ecf5774c51b313c8bb5f5b`; Codex blocker-only review round 1 BLOCKED two gates, both fixed; blocker-only re-review PASS / BLOCKERS None | Implements repo-side readiness prerequisites with injected fakes only. The PR #119 slice itself ran no smoke and approved no live/Gateway/Feishu/production behavior; a later separately approved host-local DoR and one read-only Phase D real smoke passed and are recorded in the execution row below. |
| Execution — Phase D deterministic real local smoke | Done (single host-local read-only Codex one-shot) | Manifest `docs/plans/2026-06-12-agent-run-supervisor-sachima-phase-d-real-local-smoke-manifest.yaml`; dev log `docs/dev_log/2026-06-12-agent-run-supervisor-sachima-phase-d-real-local-smoke.md`; evidence summary `/home/ubuntu/workspace/hermes/outputs/sachima/phase-d-real-local-smoke/phase_d_smoke_v2_20260612165247_summary.json`; post-verify `/home/ubuntu/workspace/hermes/outputs/sachima/phase-d-real-local-smoke/phase_d_smoke_v2_20260612165247_post_verify.json`; final validation `/home/ubuntu/workspace/hermes/outputs/sachima/phase-d-real-local-smoke/phase_d_smoke_v2_20260612165247_final_validation.json` | Proves exactly one local read-only Codex one-shot can launch through pinned local acpx 0.10.0, complete with `VERDICT: PASS`, and replay without a duplicate run. It does not approve persistent sessions, cancellation, write-capable roles, Satine/Hermes-profile ACP, controlled AI FLOW, live/Gateway/Feishu/public ingress, production config, or real delivery. |
| Design — Phase E persistent sessions / cancellation | Merged in PR #123 | Design packet `docs/plans/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-sessions-cancellation-design.md` + manifest + dev log; PR #123 merge `9e435eb443de67a923c43787f5ef7cb8ae8ad981` | Design-only: defines persistent-session records/lifecycle (create/send/query/close/abort/list), lease/epoch/session-binding guards, lock ordering, cancellation request-vs-execution semantics, fail-closed ambiguity rules, no-leak rules, and the failure-taxonomy extension. Strongest meaning = design only; it does not approve implementation, persistent session execution, cancellation execution, session-capable roles, real AGENT/acpx execution, controlled AI FLOW, live/Gateway/Feishu/public ingress, production config writes, or real delivery |
| Implementation — Phase E persistent-session lifecycle preflight / state machine | Merged in PR #125; post-merge local verification passed | Plan `docs/plans/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-session-lifecycle-state-machine-implementation.md` + manifest + dev log; code `sachima_supervisor/activity_session_lifecycle.py`; tests `tests/sachima_supervisor/test_activity_session_lifecycle.py`; PR #125 merge `a564a775f809cfdd08209863702d0249610dd286` | Local/offline Option A implementation: caller-owned Session/Turn/CancellationRequest state records, create/send/query/list/close/abort/request-cancellation commands, lease/epoch/state-version/session-binding/idempotency/operator/budget guards, injected fakes only, cancellation request-state only, validate-on-read no-leak hardening, and fail-closed ambiguity rules. It does not approve or perform real persistent session launch, cancellation execution, real AGENT/acpx/npx, controlled AI FLOW, live/Gateway/Feishu/public ingress, production config writes, service restarts, platform mutation, or real delivery. |
| P5 — Production durable runtime integration | Pending | Not started | Blocked until P4/P5 approvals and runtime design gates |
| P6 — Controlled AI FLOW execution | Pending | Not started | Blocked until durable runtime and safety gates |
| P7 — Real delivery and ACK closure | Pending | Not started | Blocked until fake/local delivery and AI FLOW gates are production-ready and separately approved |
| P8 — Product / ops hardening | Pending | Not started | Blocked until limited live pilot readiness |

## Latest phase / bridge PRs

This table tracks phase-bearing and bridge-phase PRs. Pure roadmap-status maintenance PRs do not need to be listed here unless they change the roadmap state.

| PR | Purpose | Merge commit | Notes |
|---|---|---|---|
| #78 | Validate phase-gate drift control for PE-1D | `8ad7f90f9e96afd6740508bd89df062f1eeb9f1e` | Docs / governance validation |
| #79 | Phase B fake-send simulator plan | `d1dc4602777a51570f5981b02c9c8a1b7c18847e` | Docs-only plan |
| #80 | Phase B fake-send simulator implementation | `10486c7c585974dce3f37c74437ada3419d67904` | Fake-send / simulator implementation |
| #81 | PE-2 design packet | `84f6a9010d72fe6ab3a0dac4ecaea3c3fb252ddf` | Design-only packet |
| #82 | PE-2A controlled runtime fake delivery bridge | `1f587a0b0355f7eb18a2cdff64bc1bc93ea109dd` | Controlled local runtime + fake delivery implementation |
| #96 | agent-run-supervisor local/offline integration design | `9305dd29b407cc2b8ddb1ba7ad6508abf5d619da` | Docs-only design; no implementation/live/Gateway/real delivery approval |
| #97 | agent-run-supervisor local/offline supervisor seam | `5affc2fbb68d483683cd61c0871cec528127388e` | Default-off local/offline seam; no controlled AI FLOW execution/live/Gateway/real delivery approval |
| #98 | agent-run-supervisor supervised local Activity design | `675853fd2db2b8f9df781ea46803fd0747ea78cb` | Docs-only Activity design; no implementation/live/Gateway/real delivery/controlled AI FLOW approval |
| #99 | agent-run-supervisor supervised local Activity wrapper | `8152d09ee0f847d335a76e2ef90459642fb72e9d` | Local/offline `exec_dry_run` Activity implementation; injected supervisor only; no real local exec/sessions/live/Gateway/real delivery/controlled AI FLOW approval |
| #100 | agent-run-supervisor supervised local Activity dry-run evidence | `3fea6e2e8ee836e924c3e0eef1b3ff3a2b930c59` | Deterministic local/offline evidence fixtures; injected/fake supervisor outcomes only; no real local exec/sessions/live/Gateway/real delivery/controlled AI FLOW approval |
| #102 | agent-run-supervisor supervised local Activity durable runtime ownership & controlled local execution design | `e49709d6e960b8e11f8e220fa087488132f64f93` | Docs-only durable-runtime-ownership + controlled-local-execution design; design labels only; no implementation/local exec/sessions/cancellation execution/real AGENT execution/controlled AI FLOW/live/Gateway/real delivery approval |
| #107 | agent-run-supervisor supervised local Activity durable-state preflight implementation | `6795da2930324cde1448586e71ff8d80bc6e9ae1` | Local/offline preflight only; validates durable preconditions and stores sanitized query state; no real local exec/sessions/cancellation execution/real AGENT execution/controlled AI FLOW/live/Gateway/real delivery approval |
| #117 | Phase D deterministic real local smoke readiness gate | `eb7227301d715b40d4eb6628bf32fb800017bd42` | Docs-only readiness gate; defines pinned local acpx/prompt materialization/sanitized evidence/DoR; no smoke, no AGENT, no acpx/npx, no Gateway/Feishu/live, no production config approval |
| #119 | Phase D smoke prerequisites implementation | `0c9e4342e2befe1db6ecf5774c51b313c8bb5f5b` | Implements repo-side prerequisite gates with injected fakes only; no smoke, no AGENT, no acpx/npx, no Gateway/Feishu/live, no production config approval |
| #123 | Phase E persistent sessions / cancellation design | `9e435eb443de67a923c43787f5ef7cb8ae8ad981` | Docs-only design; no implementation, persistent-session execution, cancellation execution, AGENT/acpx execution, live/Gateway/Feishu/production config, or real delivery approval |
| #125 | Phase E persistent-session lifecycle state machine | `a564a775f809cfdd08209863702d0249610dd286` | Local/offline implementation with injected fakes only; no real session launch, cancellation execution, AGENT/acpx/npx execution, live/Gateway/Feishu/production config, service restart, platform mutation, or real delivery approval |

## Evidence index

Runtime evidence stays outside PR payloads unless a phase explicitly approves versioning it.

| Phase | Evidence |
|---|---|
| PE-1D | `/home/ubuntu/workspace/hermes/outputs/sachima/pe1d-longer-controlled-local-observation/pe1d_controlled_observation_evidence.json` |
| PE-1D summary | `/home/ubuntu/workspace/hermes/outputs/sachima/pe1d-longer-controlled-local-observation/pe1d_controlled_observation_summary.md` |
| Phase B | `/home/ubuntu/workspace/hermes/outputs/sachima/phase-b-fake-send-simulator/phase_b_fake_send_simulator_evidence.json` |
| PE-2A | `/home/ubuntu/workspace/hermes/outputs/sachima/pe2a-controlled-runtime-fake-delivery/pe2a_controlled_runtime_fake_delivery_evidence.json` |
| PE-2A post-merge | `/home/ubuntu/workspace/hermes/outputs/sachima/pe2a-controlled-runtime-fake-delivery/pe2a_controlled_runtime_fake_delivery_postmerge_evidence.json` |
| Phase D smoke host-local DoR | `/home/ubuntu/workspace/hermes/outputs/sachima/phase-d-smoke-host-provisioning-dor/host_local_dor_verification.json` |
| Phase D real local smoke summary | `/home/ubuntu/workspace/hermes/outputs/sachima/phase-d-real-local-smoke/phase_d_smoke_v2_20260612165247_summary.json` |
| Phase D real local smoke post-verify | `/home/ubuntu/workspace/hermes/outputs/sachima/phase-d-real-local-smoke/phase_d_smoke_v2_20260612165247_post_verify.json` |
| Phase D real local smoke final validation | `/home/ubuntu/workspace/hermes/outputs/sachima/phase-d-real-local-smoke/phase_d_smoke_v2_20260612165247_final_validation.json` |

## Open tails

| ID | Class | Description | Blocks current phase? | Blocks next phase? | Required before | Acceptance method | Status |
|---|---|---|---:|---:|---|---|---|
| ROADMAP-WATCH-8788 | WATCH | PE-1D used fallback loopback `18788` because default `8788` was occupied by an existing Gateway. Exact default-port behavior is not proven for external ingress or live claims. | No | No | Real external ingress, exact-port live claim, or maintenance-window work | Separate maintenance-window approval and exact-port rerun without opportunistic Gateway restart | Open |
| ROADMAP-NEXT-P4-DESIGN | NEXT_PHASE | Controlled external ingress should start with a design packet before implementation. | No | No | P4 implementation request | `jovijovi/sachima-protocols` (`protocols/envelope/v1.md`) and `docs/plans/2026-05-12-sachima-envelope-v1-agentic-ui-p4-design-packet.md` | Closed by design packet |
| ROADMAP-NEXT-P4-ENV-V1-CONFORMANCE | NEXT_PHASE | Implement Sachima Envelope v1 local conformance across Sachima and agentic-ui without live/public ingress or real delivery. | No | Yes | Any P4 behavior-bearing implementation claim | Canonical spec in `jovijovi/sachima-protocols` (`protocols/envelope/v1.md`), separate implementation approval, local-only conformance tests, HMAC/schema/no-leak probes, review blockers zero | Open — Sachima-side local implementation delivered; agentic-ui and cross-repo probes pending |
| ROADMAP-WATCH-STATUS-DASHBOARD | WATCH | This dashboard is the living progress index and must be updated after roadmap/phase closure. | No | No | Any claim of phase closure or next-phase readiness | Update this file or explain N/A in the PR | Open |
| ROADMAP-NEXT-ARS-LOCAL-OFFLINE-IMPL | NEXT_PHASE | agent-run-supervisor Sachima local/offline integration implementation required a separate approval after the design packet. | No | No | Any local/offline supervisor integration implementation code | Exact approval `approve_agent_run_supervisor_sachima_local_offline_integration_implementation_no_live_no_gateway_no_real_delivery`; caller stays a Sachima/FlowWeaver/Hermes controller, never the Gateway | Closed by PR #97 local/offline seam implementation |
| ROADMAP-NEXT-ARS-SUPERVISED-LOCAL-ACTIVITY-IMPL | NEXT_PHASE | Supervised local Activity implementation requires a separate approval after this design packet. | No | No | Any Sachima/FlowWeaver Activity wrapper code around `sachima_supervisor` | Exact approval `approve_agent_run_supervisor_sachima_supervised_local_activity_implementation_no_live_no_gateway_no_real_delivery`; first slice should start with dry-run/injected supervisor calls, no live/Gateway/real delivery | Closed by PR #99 local/offline first-slice implementation |
| ROADMAP-NEXT-ARS-SUPERVISED-LOCAL-ACTIVITY-DRY-RUN-EVIDENCE | NEXT_PHASE | Controlled local Activity dry-run evidence/fixtures required a separate approval after the first Activity implementation. | No | No | Any claim that the Activity wrapper has deterministic local dry-run evidence for role mapping, idempotency, sanitized state/query, or injected supervisor outcomes | Exact approval `approve_agent_run_supervisor_sachima_supervised_local_activity_controlled_local_dry_run_evidence_no_live_no_gateway_no_real_delivery_no_real_agent_execution`; fixtures must use injected/fake supervisor outcomes only | Closed by PR #100 local/offline deterministic evidence fixtures |
| ROADMAP-NEXT-ARS-DURABLE-RUNTIME-CONTROLLED-LOCAL-EXEC-DESIGN | NEXT_PHASE | Durable runtime ownership & controlled local execution semantics around the supervised local Activity required a docs-only design gate after the dry-run evidence. | No | No | Any later local/offline durable-state preflight implementation, real local exec, real AGENT execution, or controlled AI FLOW execution claim | PR #102 merge `e49709d6e960b8e11f8e220fa087488132f64f93`; design labels only; Sachima/FlowWeaver owns durable state, supervisor stays an independent local library, Gateway excluded, runtime caller-supplied | Closed by PR #102 docs-only design packet |
| ROADMAP-NEXT-ARS-DURABLE-STATE-PREFLIGHT-IMPL | NEXT_PHASE | Local/offline durable-state preflight implementation required a separate approval after the durable runtime ownership & controlled local execution design. | No | No | Any future real local exec, persistent session, cancellation execution, real AGENT execution, or controlled AI FLOW execution request | Exact approval `approve_agent_run_supervisor_sachima_supervised_local_activity_durable_state_preflight_implementation_no_live_no_gateway_no_real_delivery_no_real_agent_execution_no_controlled_ai_flow_execution`; preflight stores sanitized durable state/query only and must not call a supervisor/runtime/Gateway/delivery surface | Closed by PR #107 merge `6795da2930324cde1448586e71ff8d80bc6e9ae1` |
| ROADMAP-NEXT-ARS-CONTROLLED-AI-FLOW | NEXT_PHASE | Controlled AI FLOW execution via the local supervisor seam remains a separate future phase. | No | Yes | Any real controlled AI FLOW execution claim, real AGENT launch from Sachima, or production agent/tool execution expansion | Separate design/approval after supervised local Activity implementation evidence and durable-runtime ownership gates; no live/Gateway/real delivery by default | Open |
| ROADMAP-NEXT-ARS-CTRL-EXEC-REVIEW-PR | NEXT_PHASE | Phase C controlled local exec first slice merged in PR #114 (`21d1bafc22c6fcde2bb0af6fff6becfb0886cf4f`); first Codex review BLOCK on unlocked claim-store check-and-set was fixed with locked in-process CAS + true concurrent tests; Codex blocker re-review returned `VERDICT: PASS` / `BLOCKERS: None`; PR CI green and post-merge local verification passed. | No | No | N/A — phase slice merged | Merge evidence verified; real smoke was later handled by the separate Phase D smoke gate | Closed by PR #114 |
| ROADMAP-NEXT-ARS-CTRL-EXEC-REAL-SMOKE | NEXT_PHASE | Phase D deterministic real local smoke (single read-only Codex one-shot) was approved separately after PR #119 and host-local DoR. First smoke attempt proved the execution pipeline but returned `VERDICT: BLOCKERS` because the prompt asked Codex to read a file while forbidding all file-read mechanisms. The prompt affordance was repaired by passing a host-verified inline JSON projection; the second smoke completed through pinned local `acpx@0.10.0` with `VERDICT: PASS`. | No | No | N/A for this completed smoke; any additional real smoke or real AGENT execution needs separate approval | Evidence summary, post-verify, final validation, clean worktree, no duplicate replay, no npx/network runner, no leftover acpx/codex processes | Closed for the single approved Phase D smoke; future live/Gateway/Feishu/production config/persistent-session/write-role/controlled-AI-FLOW work remains unapproved |
| ROADMAP-NEXT-ARS-PHASE-E-SESSIONS-CANCELLATION-DESIGN | NEXT_PHASE | Phase E persistent sessions / cancellation design packet merged in docs-only PR #123. Persistent-session and cancellation implementation/execution remain separately gated; the design recommends the local/offline lifecycle preflight / state-machine slice (injected fakes only) as the first later implementation gate. | No | No | N/A for design gate; any persistent-session or cancellation implementation request remains separate | PR #123 merged with Codex primary review `VERDICT: PASS` / `BLOCKERS: None` and status sync | Closed by PR #123 |
| ROADMAP-NEXT-ARS-PHASE-E-LIFECYCLE-STATE-MACHINE-IMPL | NEXT_PHASE | Phase E persistent-session lifecycle preflight / state-machine implementation merged in PR #125. This closed the allowed local/offline Option A slice with injected fakes only; no real session launch, no cancellation execution, no real AGENT/acpx/npx, and no live/Gateway/Feishu/production/delivery expansion. | No | No | N/A for the local/offline state-machine slice; any bounded real persistent-session execution, cancellation execution, real AGENT/acpx execution, controlled AI FLOW, or live/Gateway/Feishu/production/delivery expansion requires a new separate gate | PR #125 merged after local verification, Codex blocker-only re-review, GitHub CI, and post-merge local verification | Closed by PR #125 |
| ROADMAP-NEXT-ARS-PHASE-E2-BOUNDED-REAL-PERSISTENT-SESSION | NEXT_PHASE | Phase E-2 bounded real persistent-session execution merged in PR #127 after separate owner approval. It proves exactly one local/offline pinned-acpx persistent-session lifecycle (`create -> one read-only turn -> close`) plus one real smoke PASS with evidence outside the repo; no cancellation execution, no Gateway/Feishu/live/production config/real delivery. | No | No | N/A for the merged Phase E-2 slice; any additional persistent-session execution, cancellation execution, controlled AI FLOW, write-capable role, or live/Gateway/Feishu/production/delivery expansion remains separate | Evidence root `/data/agents/workspace/hermes/outputs/sachima/phase-e2-bounded-real-persistent-session-execution/20260613T063219Z/`; local 44/106/475 tests; smoke summary/final validation PASS; Codex blocker-only re-review PASS | Merged in PR #127 |
| ROADMAP-NEXT-ARS-CLAUDE-CODE-READONLY | NEXT_PHASE | The remaining-goals planning gate recommends WP1a as the next mainline step: add a Sachima-side Claude Code read-only role and minimal capability-gate extension with injected fakes only. | No | No | Any Sachima-side Claude Code role/capability implementation | Exact approval `approve_agent_run_supervisor_sachima_claude_code_read_only_role_capability_extension_local_offline_implementation_injected_fakes_only_no_real_smoke_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery`; no real smoke, no write roles, no additional acpx, no live/Gateway/Feishu/production config/real delivery | Open — planning gate merged in PR #128 (`ae27fbf458b32d05a85703095102c79c17c14071`); WP1a implementation not yet merged |

## Explicit non-approvals

The current state does not approve any of the following outside the approved local/offline supervisor seam, the supervised local Activity first slice, the Phase C controlled local exec wrapper slice, the single approved Phase D read-only real local smoke, the Phase E local/offline lifecycle state-machine implementation, and the separately approved Phase E-2 bounded real persistent-session execution merged in PR #127 plus its single minimal real smoke:

```text
real_external_sachima_ingress
production_durable_runtime_code_implementation
real_external_delivery
production_delivery_control
production_agent_tool_execution_expansion
production_config_write
gateway_involvement_or_mutation
gateway_restart_or_reload
platform_adapter_mutation
gateway_owned_temporal_lifecycle
real_send_api_or_external_im_call
external_temporal_service_or_worker_startup
live_or_default_on_behavior
public_webhook_exposure
reverse_proxy_or_tls_config_write
additional_real_local_smoke_execution
additional_real_agent_execution
additional_acpx_invocation
npx_fallback_or_network_fetch_evidence
feishu_or_im_delivery
unbounded_or_additional_persistent_session_execution
cancellation_execution
write_capable_claude_or_codex_roles
satine_or_hermes_profile_acp_execution
controlled_ai_flow_execution
```

The agent-run-supervisor Sachima local/offline integration design packet additionally carries, for its own scope, these non-approvals: `automatic_replies`, `worker_auto_routing`, `agent_to_agent_auto_routing`, `@all_fanout`, and `trusted_markdown_html_rendering`. See `docs/plans/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-design.md`.

## Next allowed request

The Phase D readiness docs, repo-side prerequisites, host-local DoR provisioning, and one separately approved deterministic real local smoke have all been exercised. The smoke evidence proves a bounded **local read-only Codex one-shot** only:

```text
execution_pipeline: PASS
business_task: VERDICT: PASS
```

That docs-only design gate has now been used: the Phase E persistent sessions / cancellation design packet merged in PR #123. The follow-on local/offline persistent-session lifecycle preflight / state-machine implementation merged in PR #125. PR #125 closed only the injected-fakes state-machine slice; it did not approve real persistent-session execution, cancellation execution, real AGENT/acpx/npx execution, live/Gateway/Feishu, production config, service restart, platform mutation, or real delivery.

After a later separate owner approval, Phase E-2 bounded real persistent-session execution is now merged in PR #127 and one minimal real smoke has passed. This proves exactly one local/offline pinned-acpx persistent-session lifecycle (`create -> one read-only turn -> close`) with evidence outside the repo. It still does not approve cancellation execution, additional/unbounded persistent-session execution, controlled AI FLOW, write-capable roles, live/Gateway/Feishu/public ingress, production config, service restart, platform mutation, or real delivery.

The previously approved request for PR #125 was:

```text
approve_agent_run_supervisor_sachima_phase_e_persistent_session_lifecycle_preflight_state_machine_local_offline_implementation_no_real_session_launch_no_cancellation_execution_no_real_agent_execution_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

PR #125 is now merged and locally post-verified; Phase E-2 is now merged in PR #127 with its single approved real smoke PASS. The next safe mainline request must be a **new separately approved gate** for cancellation execution, additional bounded persistent-session execution, controlled AI FLOW readiness, or another explicitly scoped step, still excluding live/Gateway/Feishu/production config/real delivery unless explicitly approved.

A docs-only remaining-goals plan merged in PR #128 (merge commit `ae27fbf458b32d05a85703095102c79c17c14071`) and recommends the next concrete implementation gate as **WP1a — Claude Code read-only role + capability-gate extension, injected fakes only**. That future gate would still exclude real Claude Code smoke, additional `acpx` invocation, multi-turn sessions, cancellation execution, controlled AI FLOW execution, write-capable roles, live/Gateway/Feishu/production config, and real delivery.

Do not skip straight to live/runtime expansion.

Still requires separate explicit approval before any future work:

```text
additional real local smoke or real AGENT execution beyond the approved Phase E-2 smoke
additional or unbounded persistent session execution beyond the approved Phase E-2 bounded lifecycle
cancellation execution
write-capable Claude/Codex roles
Satine or Hermes-profile ACP execution
controlled AI FLOW execution
Gateway / Feishu / IM / public ingress / real delivery
production config writes, service restarts, platform adapter mutation
```

Do not pivot to agentic-ui by default: the agentic-ui Sachima Envelope v1 conformance work remains an open side tail, not the default next step for the current supervisor → Sachima integration mainline.

FlowWeaver continuity note: Sachima protocol work and the supervisor integration are high-priority insertions, not a cancellation or shelving of the existing FlowWeaver roadmap.

## Drift guard

Do not infer any of these from the completed phases:

- PE-2A fake delivery success does not prove real delivery safety.
- Loopback/synthetic ingress success does not prove public external ingress safety.
- A design packet does not approve implementation.
- The supervised local Activity design packet by itself does not approve runtime code, controlled AI FLOW execution, live/default-on behavior, Gateway involvement, real ingress, or real delivery.
- The supervised local Activity implementation first slice does not approve real local `exec`, persistent sessions, cancellation/rollback, controlled AI FLOW execution, live/default-on behavior, Gateway involvement, real ingress, or real delivery.
- The durable runtime ownership & controlled local execution design packet is docs-only and uses design labels; it does not approve implementation, durable-runtime code, real local `exec`, persistent sessions, cancellation execution, real AGENT execution, controlled AI FLOW execution, a Gateway-owned or Worker-owned runtime lifecycle, live/default-on behavior, Gateway involvement, real ingress, or real delivery.
- The durable-state preflight implementation validates durable preconditions and stores sanitized query state only; it does not approve real local `exec`, persistent sessions, cancellation execution, real AGENT execution, controlled AI FLOW execution, a Gateway-owned or Worker-owned runtime lifecycle, live/default-on behavior, Gateway involvement, real ingress, or real delivery.
- The local/offline supervisor seam does not approve controlled AI FLOW execution, live/default-on behavior, Gateway involvement, real ingress, or real delivery.
- The Phase C controlled local exec first slice is a wrapper implementation only; it did not by itself prove a real local agent smoke. The later Phase D smoke proof came only after separate host-local DoR provisioning and separate user approval.
- The Phase D readiness packet is docs-only. Codex CLI substituting for interrupted Claude Code architecture/docs authoring is not the Codex primary review and is not execution approval.
- The Phase D smoke prerequisites implementation shipped verifiers, builders, and checkers exercised with injected fakes only. The later host-local DoR and real smoke were separate approvals and local evidence steps; PR #119 itself did not approve live/Gateway/Feishu/production behavior.
- The single Phase D real local smoke PASS proves only a bounded local read-only Codex one-shot. It does not approve persistent sessions, controlled AI FLOW, live/default-on behavior, Gateway/Feishu involvement, public ingress, production config writes, or real delivery.
- The Phase E persistent sessions / cancellation design packet is docs-only and uses design labels; it does not approve implementation, persistent session execution, cancellation execution, session-capable role configs, real AGENT/acpx execution, controlled AI FLOW execution, live/default-on behavior, Gateway/Feishu involvement, public ingress, production config writes, or real delivery — and its merged design status confers no implementation or execution approval.
- Sachima Envelope v1 Sachima-side local conformance does not approve agentic-ui conformance, cross-repo probes, public external ingress, or real delivery.
- Callback HTTP 2xx means receiver acceptance only; it does not prove browser-visible or IM-visible delivery.
- A local runtime bridge does not approve production durable runtime ownership.
- ACK evidence from fake-send does not approve real IM ACK reconciliation.
- Completed PRs do not close open `WATCH` tails unless this file records the closure.
- A roadmap/phase PR is not complete if this file should have changed and did not.

## Completion rule for agents

A roadmap or phase task is not complete until:

- tests, reviews, and evidence pass where applicable;
- PR / merge / post-merge status is recorded where applicable;
- this file reflects the new phase state;
- remaining tails are classified as `BLOCKER`, `NEXT_PHASE`, `WATCH`, or `PARKED`.
