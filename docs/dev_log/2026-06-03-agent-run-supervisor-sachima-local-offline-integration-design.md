# agent-run-supervisor × Sachima Local/Offline Integration Design — Dev Log

## Scope

Received the user approval token:

```text
approve_agent_run_supervisor_sachima_local_offline_integration_design_no_live_no_gateway_no_real_delivery
```

Boundary decision: this is treated as **local/offline integration design only** — a docs-only design packet for using `agent-run-supervisor` as a local supervisor library under a Sachima/FlowWeaver caller. It does **not** approve runtime code implementation, live/default-on behavior, Gateway restart/reload/replace, production config writes, real external ingress, real IM/Feishu delivery, public webhook exposure, automatic replies, worker auto-routing, platform adapter mutation, or Gateway-owned lifecycle. The design stays caller-owned by a Sachima/FlowWeaver/Hermes controller; the Gateway is not named as the concrete caller and may be a future presentation/ingress surface only after separate approval.

## Base / Worktree / Branch

```text
repo:        jovijovi/sachima
base branch: release/sachima
base sha:    c36e27631a315039e87fcfb37188d853cbdc8db4
worktree:    /home/ecs-user/workspace/hermes/worktrees/sachima/docs-agent-run-supervisor-local-offline-design
branch:      docs/agent-run-supervisor-local-offline-design
```

## Role Split

```text
Hermes        — PM / controller: owns scope interpretation, approval boundary, and acceptance.
Claude Code   — documentation engineer: authors the design packet, manifest, dev log, and the narrow roadmap update.
Codex         — primary reviewer: independent read-only consistency + boundary review before any merge claim.
```

## Evidence Consumed

Sachima-side authority and prior evidence (already on record):

- `GOAL.md` — safety before live capability, low intrusion, explicit per-axis approvals, claim-check discipline, delivery separation.
- `docs/sachima-final-goal-gap-analysis.md` — §4 "Production agent/tool execution" and Phase F "Controlled AI FLOW execution" name the missing supervised local AGENT run/session seam.
- `docs/plans/2026-05-11-sachima-final-goal-phase-development-plan.md` — phase roadmap and acceptance discipline.
- `docs/plans/2026-05-12-flowweaver-pe2-design-packet.md` — caller-supplied control-surface pattern; "design packet ≠ implementation" boundary.
- `docs/plans/2026-05-12-sachima-envelope-v1-agentic-ui-p4-design-packet.md` and `docs/roadmap/current-status.md` — current P4 position and intact non-approvals.

Cross-repo agent-run-supervisor authority facts (consumed, not re-derived):

```text
- independent local Python library + dev CLI; not Sachima, not Gateway plugin, not IM adapter, not daemon
- owns AgentRoleSpec, acpx/ACP invocation compilation, local run/session lifecycle, observed stdout/event parsing,
  status classification, redacted local artifacts/audit evidence
- I1 generic caller boundary: src/agent_run_supervisor/caller.py with CallerInvocationSpec, CallerResult,
  invoke_caller; CallerResult.business_verdict remains None/null
- L2 local/offline Hermes caller: src/agent_run_supervisor/hermes_caller/ with offline Feishu view-model/payload
  dicts; no Feishu SDK/API, no IM delivery, no public ingress, no Gateway/Sachima behavior, no automatic replies,
  no live/default-on behavior
```

No `agent-run-supervisor` source was modified or required to be checked out for this docs-only packet; the authority facts above were used directly.

## Files Changed

Created:

- `docs/plans/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-design.md`
- `docs/plans/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-design-manifest.yaml`
- `docs/dev_log/2026-06-03-agent-run-supervisor-sachima-local-offline-integration-design.md`

Updated (narrowly):

- `docs/roadmap/current-status.md` — added a docs-only local/offline supervisor integration design entry after P4 and before P5/P6; preserved stable phase labels, all explicit non-approvals, and the open agentic-ui envelope conformance tail.

## Design Decision

```text
Concrete caller   = a local Sachima/FlowWeaver/Hermes controller or Activity wrapper (NOT the Gateway).
agent-run-supervisor = a local library / evidence layer (role-spec compile, acpx/ACP run/session, observed-event
                       parsing, status classification, redacted artifacts/audit).
Flow              = Sachima intention -> FlowWeaver transaction/Activity (caller) -> invoke_caller (I1 generic)
                    -> acpx/ACP AGENT (local exec or session) -> redacted artifacts -> caller-owned business
                    verdict + offline progress/result view model -> NO REAL DELIVERY.
business_verdict  = always None/null from the library; the caller interprets it.
```

Caller-owned input contract: role selection, `AgentRoleSpec` mapping (selected, not hand-built), prompt/context assembly from refs, `cwd`/allowed roots, exec/session mode, run/session artifact dirs, correlation ids. No platform-private IDs in the generic supervisor API.

Output contract: supervisor status, artifact refs, normalized events/result summary, caller-owned business verdict, caller-built progress/result view model. No raw outputs in durable state or cards.

Mode mapping: one-shot `exec`, persistent `session`, dry-run/config-preview (preferred first concrete step later), status/close; cancellation/rollback deferred as future implementation concerns.

FlowWeaver integration: local/offline Activity or controller seam with claim-check refs, no-throw wrappers, and an evidence-only local probe; durable query/update/cancel deferred to the P5 runtime-ownership decision.

## Verification Plan

Docs-only gates for this PR:

```text
git status --short        # only the four allowed paths change
git diff --check          # no whitespace/conflict markers
changed-file allowlist    # docs/plans/, docs/dev_log/, docs/roadmap/current-status.md only
no-secret / no-raw-log scan of the three new docs and the roadmap edit
required status markers present: DESIGN_ONLY, IMPLEMENTATION_NOT_APPROVED, LIVE_NOT_APPROVED,
  GATEWAY_NOT_APPROVED, REAL_DELIVERY_NOT_APPROVED
```

Then two independent reviews plus the Codex primary review:

1. Consistency / phase-gate review — goal trace, evidence inputs, approval boundary, tails, next approval text.
2. Security / low-intrusion review — no implementation/live implication, no Gateway-as-caller, no real ingress/delivery, no raw-material leaks, changed-file guard intact.
3. Independent Codex primary review — read-only.

If any review finds a blocker, patch the docs and rerun a blocker-only review.

## Explicit Non-Approvals

```text
real_external_sachima_ingress
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
automatic_replies
worker_auto_routing
agent_to_agent_auto_routing
@all_fanout
trusted_markdown_html_rendering
```

## Review Status

```text
Hermes consistency / phase-gate gate: PASS
Hermes security / low-intrusion gate:  PASS
independent Codex primary review:     PASS, no blockers
```

Codex caveat: the first read-only sandbox review could not inspect the worktree because the sandbox failed before shell/file access. The review was rerun in the same isolated worktree with `danger-full-access`, `-a never`, and an explicit "review only, do not modify files" prompt; `git status` after the run showed no Codex-authored modifications.

## Local Verification

```text
git status --short:        PASS — only the four allowed docs paths changed
git diff --check:          PASS
changed-file allowlist:    PASS
required status markers:   PASS
manifest parse / repo gate: PASS
secret-shaped scan:        PASS, 0 findings
```

Remaining external gate:

```text
commit / push / PR / GitHub CI (docs-only fast path)
```
