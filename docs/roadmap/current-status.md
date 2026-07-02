# Sachima Roadmap Current Status

> Lean project dashboard for AGENT-facing project state. This file aligns the active product goal, stage, task progress, blockers, non-approvals, and next allowed work. It is not a version-control ledger, review log, automation-results page, or historical diary.

## How to read this file

- Use this page to decide what the project is trying to achieve now, what is done, what is blocked, and what can be requested next.
- Task rows record work-state only: `Done`, `In progress`, `Blocked`, `Not started`, or `Paused`.
- A `Done` row is a project-task state, not a quality certificate. Verification and external review remain separate quality-control layers.
- Do not record version-control state, submitted-review identifiers, revision hashes, automation matrices, external-check matrices, revision bookkeeping, or process流水账 here.
- Long design details live in the referenced plans/runbooks. Runtime truth still requires fresh checks before any live or production-facing action.

## Dynamic status policy

Machine-owned dynamic status is intentionally absent from this lean dashboard. Live GitHub/CI truth stays outside this file and must be checked fresh for PR, merge, and runtime decisions.

## Current project position

| Field | Current truth |
|---|---|
| Product goal | Production-grade AI workbench inside a custom IM channel, with safe durable FlowWeaver/Hermes orchestration and controlled delivery surfaces. |
| Active mainlines | (1) Integrate agent-run-supervisor as the supervised real-agent step boundary. (2) Integrate Temporal as the durable orchestration backbone. |
| Current stage | S5 downstream delivery reconnect implementation and its quality-review closeout are **done as project-task candidates** under the named S5 gate (default-off reconnect, injected/fake send seam, S5-owned durable pre-claim). **P7 bounded real-send canary request-packet preparation is now done as a docs/status preparation candidate**: it prepares one bounded safe-label request packet plus its pre-/post-execution gates and **does not authorize execution**; the P7 real-send canary execute gate stays separate and paused. |
| Current completed foundation | S1 integration design, S2 local/offline adapter seam, S3 Activity/controller design, S3 hermetic-local Activity implementation, S4 read-only real-agent step design, S4 read-only real-agent step implementation, S5 downstream delivery reconnect design, and S5 downstream delivery reconnect implementation are all done as project-task candidates. |
| Current design authority | `docs/plans/2026-07-01-sachima-s5-downstream-delivery-reconnect-design-packet.md` defines the downstream delivery/ACK reconnect boundary, `docs/plans/2026-07-02-sachima-s5-downstream-delivery-reconnect-implementation-manifest.yaml` records the implementation-gate scope, and `docs/plans/2026-07-02-sachima-p7-bounded-real-send-canary-request-packet-preparation.md` prepares the bounded real-send canary request packet (docs-only; prepares a later execution approval, does not authorize execution). |
| Current boundary | The project is still local/offline and controlled by named gates. No live/default-on behavior, real delivery, production config, or write-capable agent role is approved by this status page. |

## Stage / feature board

| Stage / task | Status | Work-state note | Role in the mainline |
|---|---|---|---|
| Mainline calibration | Done | Current core direction is agent-run-supervisor integration plus Temporal integration. | Reclassified earlier P5/P6/P7 work as support foundation rather than wasted work. |
| S1 integration architecture/design | Done | Architecture/design task complete. | Defines Activity ↔ supervisor seam, claim-check model, failure mapping, no-leak boundary, and S2–S5 path. |
| S2 local/offline adapter seam | Done | Local/offline fake/injected seam task complete. | Provides the Activity-boundary → supervisor adapter seam with default-off admission, claim-check idempotency, no-relaunch recovery, and no-leak checks. |
| S3 Activity/controller design | Done | Activity/controller design task complete. | Defines how Temporal Activity/controller calls the S2 seam: contracts, role mapping, lifecycle, stable refs/codes, and Worker/task-queue ownership. |
| S3 hermetic-local Activity implementation | Done | Hermetic-local implementation task complete. | Adds Activity-compatible body and caller-owned controller over the S2 seam using injected-fake deterministic execution only. |
| S4 read-only real-agent step design | Done | Read-only real-agent step design task complete. | Defines how a future implementation would replace the injected fake with one bounded read-only real-agent step through agent-run-supervisor. |
| S4 read-only real-agent step implementation | Done | Bounded read-only real-agent seam implementation task complete. | Binds the S3 Activity/controller to the bounded read-only real-agent step while preserving no-leak, fail-closed, idempotency, and ops-owned lifecycle boundaries. |
| S5 downstream delivery reconnect design | Done | Downstream delivery/ACK reconnect design task complete. | Defines how the completed S4 orchestration output would reconnect to the default-off delivery/ACK surface through an injected (fake) send seam, with no real send. |
| S5 downstream delivery reconnect implementation | Done | Default-off reconnect implementation candidate complete with injected/fake send seam, S5-owned durable pre-claim, no-double-send recovery, closed mapping, no-leak, and ACK/WATCH semantics. | Binds the S4 orchestration output to the delivery/ACK controller while preserving no-leak, fail-closed, delivery idempotency, and ops-owned lifecycle boundaries. |
| P7 bounded real-send canary request-packet preparation | Done | Docs/status preparation candidate complete: prepares one bounded safe-label request packet (closed intent/channel/role/permission/target_ref/artifact_ref mapping), the S5 delivery/ACK reuse boundary, and the pre-/post-execution gates. Prepares a later execution approval; **does not authorize execution** and supplies no concrete recipient. | Downstream delivery safety support, not the current mainline. |
| P7 bounded real-send canary execute | Paused | Deliberately paused; requires a separate one-execution approval packet with concrete safe values. | Downstream delivery safety support, not the current mainline. |
| P8 product / ops hardening | Not started | Requires orchestration-mainline and limited-live readiness first. | Later production/ops hardening stage. |

## Support foundation board

| Foundation slice | Status | Why it matters now |
|---|---|---|
| P5 Temporal Slice 1 | Done | Establishes default-off, caller-owned Temporal foundation for durable orchestration. |
| P6-A controlled AI FLOW composition | Done | Provides controlled composition over the existing orchestrator and step seam using deterministic/injected execution. |
| P6-B bounded read-only real-agent step | Done for the approved bounded smoke | Proves the prerequisite bridge shape into agent-run-supervisor under strict read-only/local controls. |
| P6 runtime lifecycle / controlled attach | Done | Establishes caller-owned attach/recover boundary without starting runtime/Worker/service processes. |
| P7 delivery / ACK closure controller | Done | Provides downstream delivery safety support while staying default-off and offline. |

## Active blockers / gates

| Gate | Status | Required before |
|---|---|---|
| S5 implementation quality gate | Done | Quality review closeout complete for the S5 implementation candidate; required before P7 bounded real-send canary request-packet preparation. This status page does not authorize P7 execution. |
| Real agent / acpx / npx execution | Not approved | Any new real agent run, read-only smoke, or broader controlled AI FLOW real execution. |
| Write-capable Claude/Codex roles | Not approved | Any Sachima-run agent step that can mutate files, state, delivery surfaces, or repositories. |
| Gateway / Feishu / live / default-on behavior | Not approved | Any live IM behavior, automatic delivery, platform adapter mutation, public ingress, or default-on route. |
| Production config / service lifecycle | Not approved | Production config writes, service restarts, Worker/runtime/service/subprocess startup, or production traffic. |
| P7 real-send canary execute | Paused | A real send requires a separate named approval that binds one concrete execution packet. |
| Active-run cancellation | WATCH | Any claim that active host/ACP runs can be reliably interrupted mid-run. |

## Next allowed work

The next safe request should be one of:

1. **Request the P7 bounded real-send canary execute gate** — still paused; requires a separate named approval that binds one concrete execution packet with operator-supplied safe values before any real send.
2. **Review or refine the prepared request packet** — docs/status only, if the operator wants to adjust safe labels/classes, stop conditions, or evidence requirements without executing.
3. **Docs/status hygiene** — keep this dashboard lean and aligned with project task truth without recreating ledgers or review histories.

## Explicit non-approvals

This status page does **not** approve:

- real external Sachima ingress;
- real external delivery or production delivery control;
- P7 real-send canary execute;
- Gateway/Feishu/live/default-on behavior;
- public webhook exposure;
- production config writes or service restarts;
- Gateway-owned Temporal/Worker/service/subprocess lifecycle;
- additional real acpx/npx/agent execution;
- write-capable Claude/Codex roles;
- Satine or Hermes-profile ACP execution;
- production cluster or production traffic.

## Completion semantics

A task row can move to `Done` only when the task's own scoped deliverable is complete. That does not by itself approve the next stage, live behavior, delivery, production config, or write-capable agent execution. Future stages still need their own named approvals and their own verification gates.
