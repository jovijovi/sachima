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
| Product goal | Production-grade AI workbench inside a custom IM channel, guided by the private-Hermes runtime spine: one per-user Hermes Agent, one `task_id` spine, supervised external local AGENT event streams, optional Temporal durability, and controlled delivery surfaces. |
| Active mainlines | (1) Preserve the Private Hermes Runtime Spine as the highest architecture guidance for Hermes, Claude Code, Codex CLI, and engineers. (2) Implement/validate the runtime-spine P0 only under separate approval. (3) Keep P7 downstream real-send canary execution paused as delivery-safety support, not the mainline. |
| Current stage | Private Hermes Runtime Spine architecture is the current top-level design authority and is saved under `docs/architecture/`. P0 implementation is not started. Earlier S1–S5/P7 work remains useful support foundation and must be interpreted through the runtime-spine boundary. |
| Current completed foundation | S1 integration design, S2 local/offline adapter seam, S3 Activity/controller design, S3 hermetic-local Activity implementation, S4 read-only real-agent step design, S4 read-only real-agent step implementation, S5 downstream delivery reconnect design, S5 downstream delivery reconnect implementation, and P7 bounded real-send canary request-packet preparation are all done as project-task candidates/support foundation. |
| Current design authority | `docs/architecture/private-hermes-runtime-spine-design.md` and `docs/architecture/private-hermes-runtime-spine-architecture.svg` are the highest architecture guidance. They supersede phase-label/topology interpretations that imply four independent lanes, Gateway-owned runtime lifecycle, Temporal-owned AGENT processes, or heavy Admission/Delivery/FlowWeaver as P0 components. |
| Current boundary | The architecture authority is docs/design guidance only. It does not approve runtime/source implementation, live/default-on behavior, real delivery, production config, Gateway lifecycle, Temporal Worker/service startup, real agent/acpx/npx execution, or write-capable agent roles. |

## Stage / feature board

| Stage / task | Status | Work-state note | Role in the mainline |
|---|---|---|---|
| Mainline calibration | Done | Current core direction is the Private Hermes Runtime Spine: one per-user Hermes Agent, one `task_id` spine, `needs_agent` / `needs_durable` mode flags, and deferred heavy layers. | Reclassified earlier P5/P6/P7 work as support foundation rather than wasted work. |
| Private Hermes Runtime Spine architecture | Done | Claude Code Architect authored the final design and SVG after Hermes/Codex roundtable review. | Highest guiding architecture for Hermes, Claude Code, Codex CLI, and engineers. |
| Runtime-spine P0 implementation/spike | Not started | Requires separate named approval before any source/runtime implementation. | Would validate the spine invariants: monotonic Event Log seq, refs-only evidence, projection replay, supervisor liveness/permission, workspace lease, and AgentRunActivity attach-not-spawn. |
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
| Runtime-spine P0 implementation/spike | Not approved | Any source/runtime implementation or spike for the new architecture authority. |
| Real agent / acpx / npx execution | Not approved | Any new real agent run, read-only smoke, or broader controlled AI FLOW real execution. |
| Write-capable Claude/Codex roles | Not approved | Any Sachima-run agent step that can mutate files, state, delivery surfaces, or repositories. |
| Gateway / Feishu / live / default-on behavior | Not approved | Any live IM behavior, automatic delivery, platform adapter mutation, public ingress, or default-on route. |
| Production config / service lifecycle | Not approved | Production config writes, service restarts, Worker/runtime/service/subprocess startup, or production traffic. |
| P7 real-send canary execute | Paused | A real send requires a separate named approval that binds one concrete execution packet. |
| Active-run cancellation | WATCH | Any claim that active host/ACP runs can be reliably interrupted mid-run. |

## Next allowed work

The next safe request should be one of:

1. **Request the runtime-spine P0 implementation/spike gate** — source/runtime work is not approved by this status page; a separate named approval must bind the exact P0 slice, tests, non-approvals, and AGENT role split.
2. **Review or refine the architecture authority** — docs/status only, if the operator wants wording or diagram adjustments without implementation.
3. **Review or refine the prepared P7 request packet** — docs/status only, if the operator wants to adjust safe labels/classes, stop conditions, or evidence requirements without executing.
4. **Request the P7 bounded real-send canary execute gate** — still paused; requires a separate named approval that binds one concrete execution packet with operator-supplied safe values before any real send.

## Explicit non-approvals

This status page does **not** approve:

- runtime-spine P0 source/runtime implementation or spike;
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
