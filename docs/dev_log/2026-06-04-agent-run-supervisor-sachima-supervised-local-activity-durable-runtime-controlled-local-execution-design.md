# Dev Log — agent-run-supervisor × Sachima Supervised Local Activity — Durable Runtime Ownership & Controlled Local Execution Design

Date: 2026-06-04
Branch: `docs/supervised-local-activity-durable-runtime-design`
Base: `release/sachima` @ `3b917eeff1c782cea2075909061037816c4eff93` (PR #101 status closure)
Approval: `approve_agent_run_supervisor_sachima_supervised_local_activity_durable_runtime_ownership_controlled_local_execution_design_no_live_no_gateway_no_real_delivery_no_real_agent_execution_no_controlled_ai_flow_execution`

## Scope

Docs-only design packet that decides durable runtime **ownership** and **controlled local execution** semantics around the already-merged supervised local Activity wrapper (`sachima_supervisor.activity`, PR #99) and its deterministic dry-run evidence (PR #100), on top of the PR #101 status closure. It defines:

- a durable runtime ownership model expressed as **design labels only** — records, leases, attempts, query projections, evidence refs, state transitions;
- the controlled-local-execution **precondition gate list** that must hold before any future real local execution may even be requested;
- start/query/update/retry/close/cancel semantics, with **cancellation execution not approved**;
- idempotency / stale-state / TOCTOU / retry-ambiguity rules;
- no-leak / durable-state / log allow-and-forbid rules;
- a stable failure taxonomy;
- docs-only verification gates and the next, narrower approval text.

No runtime code, no tests, no execution, no service/Worker/CLI/Docker/socket/Gateway lifecycle. `sachima_supervisor/activity.py` and `sachima_supervisor/activity_evidence.py` were read **for factual reference only** and were not edited.

## Approval Interpretation

- **Approved:** a docs-only Sachima design gate for durable runtime ownership and controlled local execution semantics around the merged supervised local Activity wrapper/evidence.
- **Not approved:** implementation, runtime code changes, real local `exec`, persistent sessions, cancellation execution, live/default-on behavior, Gateway involvement, real external ingress, real IM/Feishu delivery, production config writes, real AGENT execution, real AGENT auto-routing, controlled AI FLOW execution.

The packet stays caller-owned by a Sachima/FlowWeaver controller and deliberately does not name the Gateway as a caller, runtime owner, renderer, or delivery surface. Any durable runtime / Temporal abstraction is a design label for a future caller-supplied component, not an approval to start or own one.

## Preflight Evidence

Roadmap preflight (per AGENTS.md) before writing:

- Read `GOAL.md`, `AGENTS.md` preflight section, and `docs/roadmap/current-status.md`.
- Read the four prior plan docs: local/offline integration design + implementation, supervised local Activity design + implementation, and the controlled dry-run evidence packet.
- Read `sachima_supervisor/activity.py` and `sachima_supervisor/activity_evidence.py` for factual reference only.

State of the world at preflight:

- Current position: supervised local Activity design + `exec_dry_run` implementation merged (PR #98/#99); controlled local dry-run evidence/fixtures merged (PR #100); status closed (PR #101). Live/public, Gateway involvement, real AGENT execution, controlled AI FLOW execution, and real delivery are not approved.
- Next allowed request in current-status names exactly this design gate token.
- Open tails: `ROADMAP-NEXT-ARS-CONTROLLED-AI-FLOW` (open), `ROADMAP-WATCH-8788` (open), `ROADMAP-WATCH-STATUS-DASHBOARD` (open), `ROADMAP-NEXT-P4-ENV-V1-CONFORMANCE` (open side tail). The requested task is allowed by current-status as the recommended docs-only next step.

## Design Basis

| Source | Use |
|---|---|
| `GOAL.md` | Low-intrusion + safety-before-live + claim-check + delivery-separation principles drive caller-owned, runtime-caller-supplied ownership. |
| PR #96/#97 | Caller is a Sachima/FlowWeaver/Hermes controller, never the Gateway; default-off local/offline seam exists. |
| PR #98 | Activity request/response, role mapping, durable-state rules, lifecycle labels. |
| PR #99 (`activity.py`) | `ActivityStateStore` idempotency fingerprinting, sanitized `_build_durable_state`, `_state_from_supervisor_outcome` trust-boundary collapse → generalized into the durable record/lease/attempt model. |
| PR #100 (`activity_evidence.py`) | Deterministic injected/fake-only evidence + `fixture_digest` → the "prior dry-run evidence digest" precondition. |
| PR #101 | Status closure; current base for this packet. |

## Key Decision

Sachima/FlowWeaver owns the durable product/transaction runtime — product transaction state, Activity state, leases, idempotency, retry/update/close policy, role mapping, claim-check refs, and the business decision about whether a future local execution may be requested. `agent-run-supervisor` remains an independent local supervision library owning local run/session internals and redacted evidence **only once invoked by an approved caller**. The Gateway is not a caller, lifecycle owner, renderer, or delivery surface in this phase. A Temporal/durable runtime is at most a future caller-supplied abstraction; this design starts and owns no Worker, service, CLI, Docker, socket, or Gateway lifecycle. Controlled local execution remains gated behind a full precondition list and a separate, narrower future approval.

## Files Changed

```text
docs/plans/2026-06-04-agent-run-supervisor-sachima-supervised-local-activity-durable-runtime-controlled-local-execution-design.md            (new — design packet)
docs/plans/2026-06-04-agent-run-supervisor-sachima-supervised-local-activity-durable-runtime-controlled-local-execution-design-manifest.yaml (new — manifest)
docs/dev_log/2026-06-04-agent-run-supervisor-sachima-supervised-local-activity-durable-runtime-controlled-local-execution-design.md          (new — this dev log)
docs/roadmap/current-status.md                                                                                                              (updated — metadata, current_position, phase map, PR table, tail, next allowed request)
```

No code, tests, fixtures, or `.hermes` files were created or modified.

## Verification Plan

This is a docs/status-only PR; gates are documentation and governance gates, run by Hermes:

- docs marker gate (status markers present and unambiguous);
- manifest YAML parse + required keys (`design_only: true`, `implementation_approved: false`, `local_execution_approved: false`, `real_agent_execution_approved: false`, `controlled_ai_flow_execution_approved: false`, `live_approved: false`, `gateway_approved: false`, `real_delivery_approved: false`, `status: design_packet_candidate`, `created_at: 2026-06-04T00:00:00+08:00`, `pr_number: null`, `pr_url: null`);
- changed-file allowlist (docs/status only, 4 paths);
- secret-shaped scan / no-leak scan;
- forbidden-surface scan;
- Codex primary review (no blockers);
- GitHub PR CI docs-only fast path.

**Hermes ran the gates and the Codex primary review.** The Documentation Engineer authored the docs only and did not commit, push, merge, run tests, edit configs, run Gateway, call network services, or touch runtime code.

## Verification Evidence

Hermes local docs gates before PR:

```text
changed-file allowlist: pass (4 docs/status paths, no extras)
manifest YAML parse + required booleans: pass
required marker gate: pass
secret-shaped scan: 0 findings
positive approval / forbidden-surface scan: 0 findings
git diff --check: pass
```

Codex primary review:

```text
initial read-only sandbox: unable to execute due bwrap loopback restriction; no files modified
rerun mode: danger-full-access review-only in isolated worktree; no file modifications after review
VERDICT: PASS
BLOCKERS: None
```

Codex notes: only the scoped four files are present; boundaries are preserved — docs-only design, Sachima/FlowWeaver owns durable state, supervisor remains an independent local library, Gateway is excluded, runtime is caller-supplied, and the next approval remains local/offline preflight with no real AGENT or controlled AI FLOW execution.

## Explicit Non-Approvals Preserved

```text
runtime_code_implementation
durable_runtime_code_implementation
real_local_exec
persistent_sessions
cancellation_execution
real_external_sachima_ingress
real_external_delivery
production_delivery_control
production_agent_tool_execution_expansion
production_config_write
gateway_restart_or_reload
platform_adapter_mutation
gateway_owned_temporal_lifecycle
gateway_as_caller_or_renderer_or_delivery_surface
external_temporal_service_or_worker_startup
real_send_api_or_external_im_call
live_or_default_on_behavior
public_webhook_exposure
automatic_replies
worker_auto_routing
agent_to_agent_auto_routing
@all_fanout
trusted_markdown_html_rendering
real_agent_execution
controlled_ai_flow_execution
```

## Next Decision After This PR

While this PR is open, the next action is to review/merge this docs-only design PR. After merge, the next request should be a separate **local/offline durable-state preflight implementation** — still no real AGENT execution and no controlled AI FLOW execution:

```text
approve_agent_run_supervisor_sachima_supervised_local_activity_durable_state_preflight_implementation_no_live_no_gateway_no_real_delivery_no_real_agent_execution_no_controlled_ai_flow_execution
```

Do not pivot to agentic-ui; the agentic-ui Sachima Envelope v1 conformance work remains an open side tail, not the default next step. Real local `exec`, persistent sessions, cancellation execution, real AGENT execution, controlled AI FLOW execution, live/default-on, Gateway involvement, real ingress, and real delivery all remain separate, later, separately threat-modeled approvals.
