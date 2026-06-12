# Sachima Roadmap Current Status

> Living dashboard. This file tracks the current roadmap position and drift guards for Sachima / FlowWeaver work. It does not replace the canonical roadmap.

```text
last_updated: 2026-06-12
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
latest_phase_d_real_local_smoke_readiness_gate: agent-run-supervisor × Sachima Phase D deterministic real local smoke readiness gate (docs-only; no smoke run; Claude Code attempted architecture/docs and hit session-limit / 429; Codex CLI substituted for architecture/docs authoring; Codex primary re-review PASS / BLOCKERS None; awaiting PR/CI/user approval)
latest_phase_d_real_local_smoke_readiness_gate_doc: docs/plans/2026-06-12-agent-run-supervisor-sachima-phase-d-deterministic-real-local-smoke-readiness-prd.md
latest_protocol_repo: jovijovi/sachima-protocols
latest_protocol_spec: https://github.com/jovijovi/sachima-protocols/blob/main/protocols/envelope/v1.md
latest_protocol_implementation: P4 Sachima Envelope v1 local conformance implementation (Sachima-side)
latest_protocol_implementation_doc: docs/dev_log/2026-05-13-sachima-envelope-v1-local-conformance-implementation.md
current_position: P4 Sachima-side local conformance implemented; agentic-ui/cross-repo conformance pending as a side tail; agent-run-supervisor Sachima local/offline integration implementation added as a default-off, non-Gateway local/offline seam; supervised local Activity design and exec_dry_run implementation are merged; controlled local dry-run evidence/fixtures merged in PR #100 and status closed in PR #101; docs-only durable runtime ownership & controlled local execution design merged in PR #102 (`e49709d6e960b8e11f8e220fa087488132f64f93`); local/offline durable-state preflight implementation merged in PR #107 (`6795da2930324cde1448586e71ff8d80bc6e9ae1`); Phase C controlled local agent execution first slice (exec_controlled one-shot wrapper, pinned-local-acpx provenance gate, atomic pre-launch claim/CAS, read-only Codex primary reviewer role only) merged in PR #114 (`21d1bafc22c6fcde2bb0af6fff6becfb0886cf4f`) per the 2026-06-12 PRD gate and user approval — Codex re-review PASS, PR CI green, post-merge local verification passed, real local smoke NOT run (no pinned local acpx binary on host; prompt materialization deferred; `agent_run_supervisor` absent on this host); Phase D deterministic real local smoke readiness gate is docs-only and prepared by Codex CLI substituting for an interrupted Claude Code architecture/docs pass; fresh-context Codex primary review first BLOCKED two docs inconsistencies, narrow fixes landed, and blocker-only re-review returned PASS / BLOCKERS None; awaiting PR/CI/user approval; persistent sessions, cancellation execution, write-capable roles, Satine/Hermes-profile ACP, controlled AI FLOW execution, live/public, Gateway involvement, and real delivery are not approved
implementation_marker_note: no live / no Gateway / no real delivery / no real local smoke yet / controlled one-shot exec wrapper only
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
| Readiness — Phase D deterministic real local smoke | Docs-only readiness gate prepared; execution BLOCKED | PRD / architecture / user review packet / manifest / dev log under `docs/plans/2026-06-12-agent-run-supervisor-sachima-phase-d-deterministic-real-local-smoke-readiness-*`; Claude Code attempted architecture/docs then hit session-limit / 429; Codex CLI substituted for authoring; Codex primary re-review PASS / BLOCKERS None; awaiting PR/CI/user approval | Defines pinned local `acpx` provisioning, untracked local-only role overlay, prompt materialization scheme, sanitized evidence, replay proof, and Definition of Ready. Runs no smoke, no AGENT, no `acpx`, no Gateway/Feishu/live, no service/runtime, and no production config. Execution remains blocked on missing pinned local `acpx`, unimplemented prompt materialization, absent `agent_run_supervisor`, and separate user approval. |
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

## Evidence index

Runtime evidence stays outside PR payloads unless a phase explicitly approves versioning it.

| Phase | Evidence |
|---|---|
| PE-1D | `/home/ubuntu/workspace/hermes/outputs/sachima/pe1d-longer-controlled-local-observation/pe1d_controlled_observation_evidence.json` |
| PE-1D summary | `/home/ubuntu/workspace/hermes/outputs/sachima/pe1d-longer-controlled-local-observation/pe1d_controlled_observation_summary.md` |
| Phase B | `/home/ubuntu/workspace/hermes/outputs/sachima/phase-b-fake-send-simulator/phase_b_fake_send_simulator_evidence.json` |
| PE-2A | `/home/ubuntu/workspace/hermes/outputs/sachima/pe2a-controlled-runtime-fake-delivery/pe2a_controlled_runtime_fake_delivery_evidence.json` |
| PE-2A post-merge | `/home/ubuntu/workspace/hermes/outputs/sachima/pe2a-controlled-runtime-fake-delivery/pe2a_controlled_runtime_fake_delivery_postmerge_evidence.json` |

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
| ROADMAP-NEXT-ARS-CTRL-EXEC-REVIEW-PR | NEXT_PHASE | Phase C controlled local exec first slice merged in PR #114 (`21d1bafc22c6fcde2bb0af6fff6becfb0886cf4f`); first Codex review BLOCK on unlocked claim-store check-and-set was fixed with locked in-process CAS + true concurrent tests; Codex blocker re-review returned `VERDICT: PASS` / `BLOCKERS: None`; PR CI green and post-merge local verification passed. | No | No | N/A — phase slice merged | Merge evidence verified; real smoke remains a separate blocked tail | Closed by PR #114 |
| ROADMAP-NEXT-ARS-CTRL-EXEC-REAL-SMOKE | NEXT_PHASE | Phase D deterministic real local smoke (read-only Codex one-shot) is currently BLOCKED on three independent execution prerequisites: (1) no pinned local acpx binary on this host (committed role config truthfully keeps `acpx_binary: null` and the provenance gate fails closed); (2) prompt materialization is deliberately unimplemented in the Phase C slice (`prompt=None`); (3) the `agent_run_supervisor` library is not installed on this host (surfaced by the Phase D readiness design pass), so the seam would raise `supervisor_library_unavailable`. A **docs-only readiness gate** is now prepared (PRD + architecture/readiness packet + user review packet + manifest + dev log; see references) — Claude Code attempted architecture/docs and hit session-limit / 429, Codex CLI substituted for authoring, fresh-context Codex primary review first BLOCKED two docs consistency issues, narrow fixes landed, and blocker-only re-review returned PASS / BLOCKERS None; design only, no smoke run, no approval to execute. | No | Yes | Any real local smoke or real AGENT execution claim | Operator pins a verified local acpx executable (carried in an untracked local-only role overlay, not committed config), a separately approved prompt-materialization gate lands, the `agent_run_supervisor` library is installed/pinned, and a separately named user approval is given; the smoke then runs with no Gateway/delivery/public ingress and sanitized evidence only | Open — BLOCKED; docs-only readiness gate prepared (Codex primary review PASS; PR/CI/user approval pending) |

## Explicit non-approvals

The current state does not approve any of the following outside the approved local/offline supervisor seam, the supervised local Activity first slice, and the Phase C controlled local exec wrapper slice (which itself ran no real agent and remains local/offline, default-off, and non-live):

```text
real_external_sachima_ingress
production_durable_runtime_code_implementation
real_external_delivery
production_delivery_control
production_agent_tool_execution_expansion
production_config_write
gateway_restart_or_reload
platform_adapter_mutation
gateway_owned_temporal_lifecycle
real_send_api_or_external_im_call
external_temporal_service_or_worker_startup
live_or_default_on_behavior
public_webhook_exposure
reverse_proxy_or_tls_config_write
real_local_smoke_execution
real_agent_execution
acpx_invocation
npx_fallback_or_network_fetch_evidence
feishu_or_im_delivery
persistent_session_execution
cancellation_execution
write_capable_claude_or_codex_roles
satine_or_hermes_profile_acp_execution
controlled_ai_flow_execution
```

The agent-run-supervisor Sachima local/offline integration design packet additionally carries, for its own scope, these non-approvals: `automatic_replies`, `worker_auto_routing`, `agent_to_agent_auto_routing`, `@all_fanout`, and `trusted_markdown_html_rendering`. See `docs/plans/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-design.md`.

## Next allowed request

The durable runtime ownership & controlled local execution **design** approval was completed by docs-only PR #102, merge `e49709d6e960b8e11f8e220fa087488132f64f93`:

```text
approve_agent_run_supervisor_sachima_supervised_local_activity_durable_runtime_ownership_controlled_local_execution_design_no_live_no_gateway_no_real_delivery_no_real_agent_execution_no_controlled_ai_flow_execution
```

The recommended next request stayed on the agent-run-supervisor → Sachima mainline and was completed by PR #107 as a separate **local/offline durable-state preflight implementation**, still with no real AGENT execution and no controlled AI FLOW execution.

```text
approve_agent_run_supervisor_sachima_supervised_local_activity_durable_state_preflight_implementation_no_live_no_gateway_no_real_delivery_no_real_agent_execution_no_controlled_ai_flow_execution
```

The merged implementation records sanitized durable state and enforces idempotency / stale-state / TOCTOU / precondition checks as fail-closed checks — never as an execution path. It does not approve implementation of real local `exec`, persistent sessions, cancellation execution, real AGENT execution, controlled AI FLOW execution, live/default-on behavior, Gateway involvement, real external ingress, real IM/Feishu delivery, or production config writes. Any later controlled local execution or controlled AI FLOW work still requires a separate explicit approval and design/implementation gate.

That separate gate has since been exercised for one narrow slice: the 2026-06-12 PRD → Claude architecture → Codex review → user review packet flow approved the **Phase C controlled local agent execution first implementation slice** (local/offline, default-off, `exec_controlled` one-shot only, pinned local acpx provenance, read-only Codex primary reviewer, atomic pre-launch claim/CAS). That slice merged in PR #114 (`21d1bafc22c6fcde2bb0af6fff6becfb0886cf4f`).

The current Phase D readiness branch is docs-only. Claude Code attempted architecture/docs for the readiness gate and then hit session-limit / 429; Codex CLI substituted for the architecture/docs authoring role. Fresh-context Codex primary review first returned BLOCK on two docs consistency issues; after narrow fixes, blocker-only re-review returned PASS / BLOCKERS None. The next allowed request on this branch is **PR/CI/user review of the docs-only readiness gate**, not smoke execution:

```text
1. PR / CI / user review of the Phase D readiness PRD / architecture packet /
   user packet / manifest / dev log / roadmap status, with no smoke, no AGENT, no acpx,
   no Gateway/Feishu/live, no service/runtime start, and no production config write.
```

After that review and user approval, a **later** Phase D deterministic real local smoke request remains BLOCKED until the operator provides a verified pinned local `acpx` executable via an untracked local-only role overlay, prompt materialization lands under separate approval, `agent_run_supervisor` is installed/pinned, and the user gives a separate named smoke approval. See `ROADMAP-NEXT-ARS-CTRL-EXEC-REAL-SMOKE`.

The Phase C approval does not extend to persistent sessions, cancellation execution, write-capable Claude/Codex roles, Satine/Hermes-profile ACP execution, controlled AI FLOW execution, live/default-on behavior, Gateway involvement or mutation, real ingress, real delivery, or production config writes.

Do not pivot to agentic-ui: the agentic-ui Sachima Envelope v1 conformance work remains an open side tail, not the default next step for the current supervisor → Sachima integration mainline.

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
- The Phase C controlled local exec first slice is a wrapper implementation only: it does not prove or claim a real local agent smoke (none was run — no pinned local acpx binary exists on this host, prompt materialization is deferred, and `agent_run_supervisor` is absent on this host), and the committed Codex reviewer role config is truthfully not runnable (`acpx_binary: null` fails the provenance gate by design).
- The Phase D readiness packet is docs-only. Codex CLI substituting for interrupted Claude Code architecture/docs authoring is not the Codex primary review and is not execution approval.
- Phase C being merged and Phase D readiness being documented do not prove Phase D real local smoke or any live/runtime expansion; those remain separate approval gates.
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
