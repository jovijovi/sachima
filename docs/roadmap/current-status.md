# Sachima Roadmap Current Status

> Lean project dashboard. This file records the current project phase, feature/task implementation status, active blockers, and next allowed work. It is not a GitHub/PR log.

## How to read this file

- GitHub is the authority for PRs, commits, CI, and merge history.
- `current-status.md` is the authority for the current project dashboard only: phase, feature/task state, blockers, boundaries, and next decision.
- Historical PR ledgers, tail registers, and evidence indexes are not routine status surfaces for this project.
- External evidence is referenced only when it materially supports a current stage decision and is not already represented by GitHub/CI/PR metadata.

## Current project position

| Field | Current truth |
|---|---|
| Product goal | Production-grade AI workbench inside a custom IM channel, with safe durable FlowWeaver/Hermes orchestration and controlled delivery surfaces. |
| Current phase | S3 Activity/controller design — docs/status design packet refining how the Temporal Activity/controller calls the merged S2 supervisor-adapter seam. The S1 design packet and the S2 local/offline adapter seam (default-off, fake/injected) are merged. Docs/status only. |
| Current core mainlines | (1) Integrate agent-run-supervisor as the supervised real-agent step boundary; (2) integrate Temporal as the durable orchestration backbone. Completed P5/P6/P7 work is the **support foundation** for these two mainlines — not wasted work, and not the mainline itself (see the board below and the integration plan). |
| Current implementation focus | S3 Activity/controller design packet as the current design surface: it fixes the Temporal Activity↔merged-S2-adapter request/response contract, the claim-check/evidence refs and stable ids/codes, the intent-class→role-key mapping (unknown / arbitrary / platform-derived roles fail closed), the start/query/update/recover/retry/close lifecycle, the duplicate/recover/no-relaunch/ambiguous mapping, the Temporal-history no-leak boundary, and Worker/task-queue/ops ownership. Docs only: no Temporal Worker/service/subprocess start, no real agent/acpx/npx run, no controller enablement, no Gateway/Feishu/live/default-on/public-ingress behavior, no real send, and no production config writes. |
| Current repo state | `release/sachima` is the integration branch; GitHub/open-PR state is reflected only in the generated machine block below. |
| Not yet started | The S3 hermetic-local Temporal Activity implementation and the later slices (S4 read-only real-agent step, S5 downstream delivery reconnect); the paused P7 bounded real-send canary execute; limited live pilot; and P8 product/ops hardening. |

## Current core mainlines

Two integration mainlines are the active direction. Everything completed so far is **support foundation** for them.

1. **Integrate agent-run-supervisor** — make the supervised, role-bound, read-only-first real-agent step the controlled execution boundary FlowWeaver/Hermes drives. P6-B is the prerequisite capability (the read-only bridge from the WP4/P6 step seam into agent-run-supervisor controlled local exec); P6 runtime attach is the caller-owned lifecycle / recover boundary.
2. **Integrate Temporal** — make Temporal the durable workflow state / retry / query / update / recovery backbone for FlowWeaver orchestration, with Worker/service lifecycle ops-owned and never Gateway-owned. P5 is the Temporal foundation; P6-A is the controlled AI FLOW composition over the P5 step seam.

The downstream Gateway delivery/ACK surface (P7) is **downstream delivery safety support**, not the current orchestration mainline. The staged path for both mainlines is set by the S0 calibration plan (`docs/plans/2026-06-30-sachima-mainline-calibration-agent-run-supervisor-temporal-integration-plan.md`) and the S1 architecture/design packet (`docs/plans/2026-06-30-sachima-s1-agent-run-supervisor-temporal-integration-architecture-design-packet.md`); the current design surface is the S3 Activity/controller design packet (`docs/plans/2026-06-30-sachima-s3-activity-controller-design-packet.md`), which refines how the Temporal Activity/controller calls the merged S2 supervisor-adapter seam.

## Stage / feature board

| Stage / feature | Status | Role in mainline | Next |
|---|---|---|---|
| S1 integration architecture/design packet | Done (docs/status design packet) | Fixed the Activity↔agent-run-supervisor seam contract, the cross-boundary claim-check data model, the failure/recovery/no-relaunch mapping, the Temporal-history no-leak boundary, and the S2–S5 path. Docs/status only; grants no implementation/runtime/live approval. | Superseded as the active design surface by the S3 Activity/controller design packet. |
| S2 local/offline adapter seam | Done (default-off, fake/injected) | **agent-run-supervisor + Temporal seam.** Merged Activity-boundary→supervisor adapter (`sachima_supervisor/p5_temporal/s2_supervisor_adapter.py`): admission-gated default-off, injected fake/deterministic body only, claim-check idempotency keyed on `(run_ref, step_ref)`, no-relaunch recovery, dual no-leak scans. Starts no Worker/runtime; runs no real agent. | Driven by the S3 Activity/controller design; the S3 implementation is a separate named approval. |
| S3 Activity/controller design packet | Done (docs/status design packet) | **Current design surface for both mainlines.** Fixes how the Temporal Activity/controller calls the merged S2 adapter seam: request/response contract, claim-check/evidence refs and stable ids/codes, intent-class→role-key mapping (fail-closed), start/query/update/recover/retry/close lifecycle, duplicate/no-relaunch/ambiguous mapping, no-leak boundary, and Worker/task-queue/ops ownership. Docs/status only; grants no implementation/runtime/live approval. | S3 hermetic-local Temporal Activity implementation (injected-fake, namespace/task-queue scoped, no real agent) is the next request and requires separate named implementation approval. |
| P5 Temporal Slice 1 | Done (support foundation) | **Temporal foundation.** Default-off caller-owned Temporal Slice 1 with controlled-deterministic step body; hermetic-local/staging namespace only, Worker/service ops-owned. | Durable backbone for the Temporal mainline; no production cluster/traffic implied. |
| P6-A controlled AI FLOW composition | Done (support foundation) | **Controlled AI FLOW composition control.** Default-off outer composition over the unmodified WP4 orchestrator + the P5 `StepExecutor` seam; deterministic/injected-fake step bodies only. | Orchestration seam the Temporal mainline drives; no real agent execution or live delivery implied. |
| P6-B bounded read-only real-agent step | Done for the single approved smoke (support foundation) | **Controlled real-agent step / agent-run-supervisor prerequisite.** Default-off read-only bridge from the WP4/P6 step seam into agent-run-supervisor controlled local exec; one pinned-local read-only smoke recorded, no duplicate replay/recover, no live surfaces. | Prerequisite capability for the agent-run-supervisor mainline; any additional real agent/acpx/npx execution requires separate approval. |
| P6 runtime lifecycle / controlled attach | Done as implementation slice (support foundation) | **Caller-owned lifecycle / recover boundary.** Default-off caller-owned attach shell over an already supplied P6 session: fail-closed admission, sanitized state, idempotent no-relaunch recovery, WP3b WATCH preserved; starts no runtime/Worker/service/subprocess. | Recover/attach boundary for both mainlines; not a Worker/runtime startup approval. |
| Feishu task workbench title summary | Done | Downstream IM surface; task-card title summary stabilization is merged. | No phase change. |
| Feishu PR approval-card stale-head hardening | Done | Downstream IM surface; reissuing a PR approval card invalidates older unresolved same-PR cards and fails closed on stale callbacks/resolvers. | Runtime deployment/restart is operational, not a roadmap phase. |
| P7 real delivery / ACK closure | Done as implementation slice (support foundation) | **Downstream delivery safety support — NOT the current mainline.** Default-off delivery/ACK closure controller and offline TDD tests; bounded caller-supplied adapter seam only; no real delivery. | Reconnect downstream only after the orchestration mainline is safe (plan stage S5). |
| P7 bounded real-send canary request prep | Prep slice (default-off) — paused | **Downstream delivery safety support.** Preparation gate fixing the bounded canary request-packet contract and block conditions; no send, no controller enablement, no concrete recipient supplied. | **Paused.** P7 real-send canary execute requires a separate, named future send approval binding one execution packet; it is not the current mainline. |
| P8 product / ops hardening | Not started | Product/ops hardening after limited live-pilot readiness. | Requires orchestration-mainline + live-pilot readiness first. |

## Active blockers / gates

| Gate | Status | Required before |
|---|---|---|
| Additional real agent/acpx/npx execution | Not approved | Any new real agent run, real smoke beyond the recorded one-shot, or broader controlled AI FLOW real execution. |
| Write-capable Claude/Codex roles | Not approved | Any role that can modify files or perform non-read-only agent execution through Sachima. |
| Gateway/Feishu/live/default-on behavior | Not approved by roadmap status | Any live IM behavior, automatic delivery, platform adapter mutation, public ingress, or default-on route. |
| Production config / service lifecycle | Not approved by roadmap status | Production config writes, Gateway-owned Temporal/Worker lifecycle, runtime/Worker/service/subprocess startup, or production traffic. |
| P7 real-send canary execute | Paused — separate approval required | A real send needs a separate, named future approval binding one execution packet with concrete safe values (see `docs/runbooks/sachima-p7-bounded-real-send-canary-request.md`). Pausing it is a deliberate calibration decision; it is downstream delivery safety support, not the current mainline. |
| WP3b active-run cancellation | WATCH | Any claim that active host/ACP runs can be reliably interrupted mid-run. |

## Next allowed work

The next safe request should be one of:

1. **S3 hermetic-local Temporal Activity implementation** — implement the Temporal Activity body and the caller-owned controller that drive the merged S2 supervisor-adapter seam, with an **injected-fake / controlled-deterministic body only**, namespace- and task-queue-scoped, ops-owned Worker, and hermetic-local/offline tests, per the S3 Activity/controller design packet (`docs/plans/2026-06-30-sachima-s3-activity-controller-design-packet.md`). This requires a **separate, named implementation approval**; it runs no real agent/acpx/npx, enables no Gateway/Feishu/live/default-on behavior, performs no real send, and writes no production config.
2. **Docs/status hygiene** — keep this dashboard lean and aligned with live repo truth without recreating PR ledgers or tail registers.

P7 bounded real-send canary execute is **paused**: it is downstream delivery safety support, not the current mainline, and a real send requires a separate, named future approval binding one execution packet (`docs/runbooks/sachima-p7-bounded-real-send-canary-request.md`). Keep the controller default-off until that approval exists.

## Explicit non-approvals

This status page does **not** approve:

- real external Sachima ingress;
- real external delivery or production delivery control;
- P7 real-send canary execute (paused; separate, named future approval required);
- Gateway/Feishu/live/default-on behavior;
- public webhook exposure;
- production config writes or service restarts;
- Gateway-owned Temporal/Worker/service/subprocess lifecycle;
- Temporal Worker/service/runtime/subprocess startup by this design gate;
- additional real acpx/npx/agent execution beyond the recorded approved bounded smoke;
- write-capable Claude/Codex roles;
- Satine or Hermes-profile ACP execution;
- production cluster or production traffic.

The current S3 Activity/controller design gate is **docs/status only**: it starts no Temporal Worker/service/runtime/subprocess, runs no agent/acpx/npx, performs no real send, and writes no production config. The scoped P5 hermetic-local/staging Temporal lifecycle grant remains ops-owned and is not exercised here; the S3 implementation and the later integration slices (S4–S5) each require their own named approval before any runtime, real-agent step, or delivery reconnection.

## Completion rule

A roadmap/phase task is complete only when:

- the feature/task row above reflects its current implementation status;
- blockers and non-approvals remain explicit;
- GitHub/CI/PR facts are left to GitHub instead of copied here as a ledger;
- any non-GitHub evidence is referenced only when it materially affects the current decision.

## Machine-owned dynamic status

<!-- sachima-status-sync:start -->
> Generated by `tools/sync_roadmap_status.py`; do not edit manually.
> Source of truth: git/GitHub. This block is evidence only; it does not grant approvals.

```json
{
  "base_branch": "release/sachima",
  "base_head": "d9a9baee3d02e4eac843094cb94a9d450447d0bd",
  "base_head_note": "latest first-parent base commit excluding machine status-sync self-commits",
  "open_pr_count": 1,
  "open_prs": [
    {
      "baseRefName": "release/sachima",
      "headRefName": "feat/s3-activity-controller-design-packet",
      "isDraft": false,
      "mergeStateStatus": "CLEAN",
      "number": 194,
      "title": "docs(sachima): add S3 activity controller design packet",
      "url": "https://github.com/jovijovi/sachima/pull/194"
    }
  ],
  "repository": "jovijovi/sachima",
  "scope_note": "machine dynamic status only; GitHub remains the authority for PR/merge/CI history, and approvals/phase meaning remain human-authored outside this block"
}
```
<!-- sachima-status-sync:end -->
