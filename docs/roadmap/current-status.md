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
| Current phase | S4 read-only real-agent step design packet — docs/status design gate. The S3 hermetic-local Temporal Activity implementation is **done/merged** (Activity-compatible body + caller-owned controller over the merged S2 local/offline supervisor-adapter seam); the S1 design packet, S2 seam, S3 design packet, and S3 implementation are all merged. S4-design fixes how that merged Activity/controller would bind a bounded, single, read-only **real** agent step through agent-run-supervisor in place of the injected fake — docs only, granting no runtime/real-agent approval. |
| Current core mainlines | (1) Integrate agent-run-supervisor as the supervised real-agent step boundary; (2) integrate Temporal as the durable orchestration backbone. Completed P5/P6/P7 work is the **support foundation** for these two mainlines — not wasted work, and not the mainline itself (see the board below and the integration plan). |
| Current design focus | S4 read-only real-agent step design packet (`docs/plans/2026-07-01-sachima-s4-read-only-real-agent-step-design-packet.md`): the real-read-only-body binding contract (`ActivityInput -> the S2 adapter's injected real SupervisorSeam -> agent-run-supervisor pinned-local acpx read-only exec -> ActivityOutput`), the closed intent-class→role-key→real-read-only-role mapping (unknown/platform-derived/write-capable fail closed), real-agent side-effect idempotency (pre-claim/post-claim/duplicate/recover/no-relaunch/ambiguous), Temporal Activity retry/timeout/heartbeat/cancellation/failure semantics (per https://docs.temporal.io/), the SCAN 1/SCAN 2 no-leak boundary against real agent output, and the ops-owned Worker/task-queue boundary. Docs/status only: no source implementation, no Temporal Worker/runtime start, no real agent/acpx/npx run, no Gateway/Feishu/live/default-on/public-ingress behavior, no real send, no production config, and no write-capable roles. |
| Current repo state | `release/sachima` is the integration branch; GitHub/open-PR state is reflected only in the generated machine block below. |
| Not yet started | The S4 read-only real-agent step **implementation** (separate named approval required); the S5 downstream delivery reconnect; the paused P7 bounded real-send canary execute; limited live pilot; and P8 product/ops hardening. |

## Current core mainlines

Two integration mainlines are the active direction. Everything completed so far is **support foundation** for them.

1. **Integrate agent-run-supervisor** — make the supervised, role-bound, read-only-first real-agent step the controlled execution boundary FlowWeaver/Hermes drives. P6-B is the prerequisite capability (the read-only bridge from the WP4/P6 step seam into agent-run-supervisor controlled local exec); P6 runtime attach is the caller-owned lifecycle / recover boundary.
2. **Integrate Temporal** — make Temporal the durable workflow state / retry / query / update / recovery backbone for FlowWeaver orchestration, with Worker/service lifecycle ops-owned and never Gateway-owned. P5 is the Temporal foundation; P6-A is the controlled AI FLOW composition over the P5 step seam.

The downstream Gateway delivery/ACK surface (P7) remains **downstream delivery safety support**, not the current orchestration mainline. The staged path for both mainlines is set by the S0 calibration plan (`docs/plans/2026-06-30-sachima-mainline-calibration-agent-run-supervisor-temporal-integration-plan.md`) and the S1 architecture/design packet (`docs/plans/2026-06-30-sachima-s1-agent-run-supervisor-temporal-integration-architecture-design-packet.md`). The S3 design surface and the S3 hermetic-local Temporal Activity implementation are both merged (`docs/plans/2026-06-30-sachima-s3-activity-controller-design-packet.md`, `docs/plans/2026-06-30-sachima-s3-hermetic-local-temporal-activity-implementation-manifest.yaml`). The current design surface is the S4 read-only real-agent step design packet (`docs/plans/2026-07-01-sachima-s4-read-only-real-agent-step-design-packet.md`), docs/status only — it grants no implementation, runtime, or real-agent approval.

## Stage / feature board

| Stage / feature | Status | Role in mainline | Next |
|---|---|---|---|
| S1 integration architecture/design packet | Done (docs/status design packet) | Fixed the Activity↔agent-run-supervisor seam contract, the cross-boundary claim-check data model, the failure/recovery/no-relaunch mapping, the Temporal-history no-leak boundary, and the S2–S5 path. Docs/status only; grants no implementation/runtime/live approval. | Superseded as the active design surface by the S3 Activity/controller design packet. |
| S2 local/offline adapter seam | Done (default-off, fake/injected) | **agent-run-supervisor + Temporal seam.** Merged Activity-boundary→supervisor adapter (`sachima_supervisor/p5_temporal/s2_supervisor_adapter.py`): admission-gated default-off, injected fake/deterministic body only, claim-check idempotency keyed on `(run_ref, step_ref)`, no-relaunch recovery, dual no-leak scans. Starts no Worker/runtime; runs no real agent. | Driven by the merged S3 Activity/controller implementation. |
| S3 Activity/controller design packet | Done (docs/status design packet) | Fixed how the Temporal Activity/controller calls the merged S2 adapter seam: request/response contract, claim-check/evidence refs and stable ids/codes, intent-class→role-key mapping (fail-closed), start/query/update/recover/retry/close lifecycle, duplicate/no-relaunch/ambiguous mapping, no-leak boundary, and Worker/task-queue/ops ownership. Docs/status only; granted no implementation/runtime/live approval. | Superseded by the merged S3 hermetic-local implementation. |
| S3 hermetic-local Temporal Activity implementation | Done (merged; hermetic-local, injected-fake) | **Merged support foundation for both mainlines.** Activity-compatible body wrapping the merged S2 adapter seam plus a caller-owned controller for start/query/update/recover/retry/close, with closed role mapping, stable code/ref projection, duplicate/recover/no-relaunch handling, and SCAN 1/SCAN 2 tests. Injected-fake / controlled-deterministic only: no real agent/acpx/npx, no Gateway/live/send, no production config, no write roles. | Superseded as the active surface by the S4 read-only real-agent step design packet. |
| S4 read-only real-agent step design packet | Design candidate (docs/status design packet) | Fixes how the merged S3 Activity/controller would bind a bounded, single, read-only **real** agent step through agent-run-supervisor (pinned-local acpx read-only exec) in place of the injected fake: the real-body seam contract, the closed intent-class→role-key→real-read-only-role mapping (fail closed), real-agent side-effect idempotency (pre-claim/post-claim/duplicate/recover/no-relaunch/ambiguous), Temporal Activity retry/timeout/heartbeat/cancellation/failure semantics (per https://docs.temporal.io/), the no-leak boundary against real agent output, and the ops-owned Worker/task-queue/Gateway-excluded boundary. Docs/status only; grants no implementation/runtime/real-agent/live approval. | Requires a separate, named S4 read-only real-agent step **implementation** approval before any real agent/acpx run. |
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

1. **Review/merge the S4 read-only real-agent step design packet** — run the docs/status checks (changed-file allowlist, S3 stale-status wording scan, required non-approval markers, manifest/status parse, secret/no-leak/forbidden-approval-wording scan, `git diff --check`), Codex read-only blocker review, GitHub CI green, and the Feishu approval card bound to the latest head SHA. Docs/status only: no source implementation, no Temporal Worker/runtime start, no real agent/acpx/npx, no Gateway/Feishu/live/default-on behavior, no real send, no production config, and no write-capable roles.
2. **S4 read-only real-agent step implementation gate** — only under a separate, named approval; it would bind the merged Activity seam to one bounded, single, read-only real agent step (role-pinned, pinned-local acpx, no-leak, crash→no-relaunch proven), still without delivery/live expansion.
3. **Docs/status hygiene** — keep this dashboard lean and aligned with live repo truth without recreating PR ledgers or tail registers.

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
- additional real acpx/npx/agent execution beyond the recorded approved bounded smoke;
- write-capable Claude/Codex roles;
- Satine or Hermes-profile ACP execution;
- production cluster or production traffic.

The merged S3 implementation is hermetic-local and injected-fake only, and the current S4 gate is a **docs/status design packet**: neither approves real agent/acpx/npx execution, Gateway/Feishu/live/default-on behavior, real send, production config, write-capable roles, production cluster/traffic, or Gateway-owned Worker/service/subprocess lifecycle. The S4 read-only real-agent step **implementation**, and the later S5 delivery reconnection, each require their own separate named approval before any real-agent step or delivery reconnection.

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
  "base_head": "c3bac158be986a01605ac96931202ad8c45f32ee",
  "base_head_note": "latest first-parent base commit excluding machine status-sync self-commits",
  "open_pr_count": 0,
  "open_prs": [],
  "repository": "jovijovi/sachima",
  "scope_note": "machine dynamic status only; GitHub remains the authority for PR/merge/CI history, and approvals/phase meaning remain human-authored outside this block"
}
```
<!-- sachima-status-sync:end -->
