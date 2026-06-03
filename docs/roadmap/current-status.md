# Sachima Roadmap Current Status

> Living dashboard. This file tracks the current roadmap position and drift guards for Sachima / FlowWeaver work. It does not replace the canonical roadmap.

```text
last_updated: 2026-06-03
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
latest_protocol_repo: jovijovi/sachima-protocols
latest_protocol_spec: https://github.com/jovijovi/sachima-protocols/blob/main/protocols/envelope/v1.md
latest_protocol_implementation: P4 Sachima Envelope v1 local conformance implementation (Sachima-side)
latest_protocol_implementation_doc: docs/dev_log/2026-05-13-sachima-envelope-v1-local-conformance-implementation.md
current_position: P4 Sachima-side local conformance implemented; agentic-ui/cross-repo conformance pending; agent-run-supervisor Sachima local/offline integration implementation added as a default-off, non-Gateway local/offline seam; supervised local Activity design packet added; supervised local Activity implementation merged as an exec_dry_run wrapper with injected supervisor calls only; controlled local dry-run evidence/fixtures approved for this PR; live/public, Gateway involvement, real AGENT execution, controlled AI FLOW execution, and real delivery not approved
implementation_marker_note: no live / no Gateway / no real delivery / no real AGENT execution
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
| Evidence — supervised local Activity controlled dry-run | Implementation candidate (local/offline fixtures only) | This PR adds injected/fake supervisor evidence fixtures, role-map/idempotency fixtures, and sanitized durable-state/query evidence; PR number pending until opened | Proves the Activity wrapper can produce deterministic local dry-run evidence without real AGENT execution; does not approve real local exec/sessions, controlled AI FLOW execution, live/default-on behavior, Gateway involvement, real ingress, or real delivery |
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
| ROADMAP-NEXT-ARS-SUPERVISED-LOCAL-ACTIVITY-DRY-RUN-EVIDENCE | NEXT_PHASE | Controlled local Activity dry-run evidence/fixtures required a separate approval after the first Activity implementation. | No | Yes | Any claim that the Activity wrapper has deterministic local dry-run evidence for role mapping, idempotency, sanitized state/query, or injected supervisor outcomes | Exact approval `approve_agent_run_supervisor_sachima_supervised_local_activity_controlled_local_dry_run_evidence_no_live_no_gateway_no_real_delivery_no_real_agent_execution`; fixtures must use injected/fake supervisor outcomes only | Candidate closure by this PR; final closure requires PR merge/CI and PR number recording |
| ROADMAP-NEXT-ARS-CONTROLLED-AI-FLOW | NEXT_PHASE | Controlled AI FLOW execution via the local supervisor seam remains a separate future phase. | No | Yes | Any real controlled AI FLOW execution claim, real AGENT launch from Sachima, or production agent/tool execution expansion | Separate design/approval after supervised local Activity implementation evidence and durable-runtime ownership gates; no live/Gateway/real delivery by default | Open |

## Explicit non-approvals

The current state does not approve any of the following outside the approved local/offline supervisor seam and supervised local Activity first slice:

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
real_agent_execution
controlled_ai_flow_execution
```

The agent-run-supervisor Sachima local/offline integration design packet additionally carries, for its own scope, these non-approvals: `automatic_replies`, `worker_auto_routing`, `agent_to_agent_auto_routing`, `@all_fanout`, and `trusted_markdown_html_rendering`. See `docs/plans/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-design.md`.

## Next allowed request

Recommended next work after this implementation candidate merges can be either of the following, depending on priority:

Option A — agentic-ui Sachima Envelope v1 local conformance and cross-repo probes only:

```text
approve_p4_agentic_ui_sachima_envelope_v1_local_conformance_and_cross_repo_probes_no_live_no_public_ingress_no_real_delivery
```

This approval would allow agentic-ui-side local conformance implementation and cross-repo probes for Sachima Envelope v1 after the Sachima-side local implementation. It would not approve public exposure, Gateway restart/reload, production config writes, real external delivery, real AI FLOW execution, Temporal service/Worker lifecycle, or live/default-on behavior.

Option B — controlled local Activity dry-run evidence/fixtures only:

```text
approve_agent_run_supervisor_sachima_supervised_local_activity_controlled_local_dry_run_evidence_no_live_no_gateway_no_real_delivery_no_real_agent_execution
```

This approval would allow additional local/offline evidence around the supervised Activity wrapper using injected/fake supervisor outcomes, role-map fixtures, idempotency fixtures, and sanitized durable-state/query evidence. It would not approve real local `exec`, persistent sessions, cancellation, live behavior, Gateway involvement, real external ingress, real IM/Feishu delivery, production config writes, real AGENT execution, real AGENT auto-routing, or controlled AI FLOW execution.

A later controlled-AI-FLOW approval remains separate after supervised local Activity implementation evidence and durable-runtime ownership gates.

The agentic-ui Sachima Envelope v1 conformance work (Option A) remains open regardless of which option is chosen first.

FlowWeaver continuity note: Sachima protocol work and the supervisor integration are high-priority insertions, not a cancellation or shelving of the existing FlowWeaver roadmap.

## Drift guard

Do not infer any of these from the completed phases:

- PE-2A fake delivery success does not prove real delivery safety.
- Loopback/synthetic ingress success does not prove public external ingress safety.
- A design packet does not approve implementation.
- The supervised local Activity design packet by itself does not approve runtime code, controlled AI FLOW execution, live/default-on behavior, Gateway involvement, real ingress, or real delivery.
- The supervised local Activity implementation first slice does not approve real local `exec`, persistent sessions, cancellation/rollback, controlled AI FLOW execution, live/default-on behavior, Gateway involvement, real ingress, or real delivery.
- The local/offline supervisor seam does not approve controlled AI FLOW execution, live/default-on behavior, Gateway involvement, real ingress, or real delivery.
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
