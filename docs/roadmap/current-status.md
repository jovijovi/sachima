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
| Active mainlines | (1) Preserve the Private Hermes Runtime Spine as the highest architecture guidance for Hermes, Claude Code, Codex CLI, and engineers. (2) Follow the R0-R5 development roadmap in `docs/plans/2026-07-03-sachima-private-hermes-runtime-spine-development-plan.md`; R1, R2, R3, R4, and R5 are done as local/offline/default-off slices. (3) Execute the operator-approved `agent-run-supervisor` integration mainline as five governed PR slices: AgentRunSupervisorPort adapter, host-local read-only real AGENT smoke, persistent session lifecycle, StatusProjection + task workbench view, and single-user production-shaped E2E. (4) Keep P7 downstream real-send canary execution paused as delivery-safety support, not the mainline. |
| Current stage | R0 planning reset is done as a docs/status planning task, R1 runtime-spine core is done as a local/offline implementation task, R2 supervisor execution port is done as a deterministic fake/offline implementation task, R3 Temporal attach-only durable bridge is done as a local/offline implementation task, R4 workspace + permission + projection integration is done as a local/offline implementation task, and R5 controlled canary / product hardening is done as a default-off local/offline preparation task. The runtime-spine architecture is saved under `docs/architecture/`, the active R0-R5 development roadmap is saved under `docs/plans/`, and old phase plans are registered as superseded active roadmap / retained support foundation. Earlier S1-S5/P7 work remains useful support foundation and must be interpreted through the runtime-spine boundary. |
| Current completed foundation | R1 runtime-spine core, R2 supervisor execution port, R3 Temporal attach-only durable bridge, R4 workspace + permission + projection integration, R5 controlled canary / product hardening, S1 integration design, S2 local/offline adapter seam, S3 Activity/controller design, S3 hermetic-local Activity implementation, S4 read-only real-agent step design, S4 read-only real-agent step implementation, S5 downstream delivery reconnect design, S5 downstream delivery reconnect implementation, and P7 bounded real-send canary request-packet preparation are all done as project-task candidates/support foundation. |
| Current design authority | `docs/architecture/private-hermes-runtime-spine-design.md` and `docs/architecture/private-hermes-runtime-spine-architecture.svg` are the highest architecture guidance. `docs/plans/2026-07-03-sachima-private-hermes-runtime-spine-development-plan.md` is the active development roadmap under that architecture, and `docs/roadmap/superseded-plans.md` records old roadmap supersession. They supersede phase-label/topology interpretations that imply four independent lanes, Gateway-owned runtime lifecycle, Temporal-owned AGENT processes, or heavy Admission/Delivery/FlowWeaver as P0 components. |
| Current boundary | R1/R2/R3/R4/R5 runtime-spine work is local/offline/default-off foundation. The approved `agent-run-supervisor` integration mainline may add Sachima source/tests/docs/runbook in five governed PR slices, with PR1 using injected/default-fake supervisor adapter only and later host-local read-only real AGENT smoke/E2E limited to controlled local fixtures. This status page still does not approve live/default-on behavior, real delivery, production config, Gateway lifecycle, Temporal Worker/service startup, write-capable agent roles, public webhook exposure, or real external Sachima ingress. |

## Stage / feature board

| Stage / task | Status | Work-state note | Role in the mainline |
|---|---|---|---|
| Mainline calibration | Done | Current core direction is the Private Hermes Runtime Spine: one per-user Hermes Agent, one `task_id` spine, `needs_agent` / `needs_durable` mode flags, and deferred heavy layers. | Reclassified earlier P5/P6/P7 work as support foundation rather than wasted work. |
| Private Hermes Runtime Spine architecture | Done | Claude Code Architect authored the final design and SVG after Hermes/Codex roundtable review. | Highest guiding architecture for Hermes, Claude Code, Codex CLI, and engineers. |
| R0 runtime-spine planning reset | Done | New R0-R5 development plan and superseded-plans register define the active roadmap. | Makes old S1-S5/P5/P6/P7 plans support foundation rather than active roadmap. |
| R1 runtime-spine core | Done | Local/offline core implementation task complete. | Provides Task Registry, refs-only Event Log, monotonic seq authority, deterministic Status Projection, static Capability Registry, and typed LaunchSpec for the next candidate gate. |
| R2 supervisor execution port | Done | Deterministic fake/offline execution-port implementation task complete. | Adds offline/fake supervisor port semantics only. |
| R3 Temporal attach-only durable bridge | Done | Local/offline attach-only durable bridge implementation task complete. | Adds attach-only durable bridge contracts without Worker/service startup. |
| R4 workspace + permission + projection integration | Done | Local/offline implementation task complete: workspace single-writer lease, permission roundtrip, read-only/default-deny role policy, and platform-neutral refs-only view model. | Adds lease, permission roundtrip, and platform-neutral view model. |
| R5 controlled canary / product hardening | Done | Default-off local/offline preparation task complete: controlled canary packet, dry-run observability report, stable stop/rollback semantics, and safe-label receiver-bridge boundary. | Keeps canary/product hardening default-off; real send remains separate. |
| AgentRunSupervisorPort adapter | Done | Local/offline PR1 implementation task complete: injected/default-fake backend adapter only, no real process startup. | Adds a Sachima-side adapter from runtime-spine `ExecutionPort` semantics to an injected supervisor backend surface. |
| Host-local read-only real AGENT smoke | Not started | Governed PR2 slice; allowed only as a controlled host-local read-only smoke harness with safe cwd/artifact dir and no file/git/network/API mutation by the tested AGENT. | First real local supervisor smoke after PR1 adapter gate. |
| Persistent session lifecycle | Not started | Governed PR3 slice; persistent create/attach/stream/signal/kill/close/liveness/orphan semantics through the adapter. | Hardens lifecycle and lease/task binding. |
| StatusProjection + task workbench view | Not started | Governed PR4 slice; deterministic projection/workbench mapping with no raw log/prompt/platform leakage. | Makes supervised task state visible through safe refs-only fields. |
| Single-user production-shaped E2E | Not started | Governed PR5 slice; default-off single-task fixture with cleanup/health/rollback proof and no live ingress/delivery/config. | End-to-end proof while preserving non-approvals. |
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
| R3 Temporal attach-only durable bridge implementation | Done | R3 attach-only durable bridge source implementation is complete as a local/offline task; this status page does not approve Worker/service startup or live execution. |
| Agent-run-supervisor integration mainline | Approved / gated | Five PR slices named in the operator approval: PR1 adapter, PR2 host-local read-only real AGENT smoke, PR3 persistent session lifecycle, PR4 StatusProjection + task workbench view, PR5 single-user production-shaped E2E. Each slice still requires focused tests, no-leak/forbidden-surface scan, read-only blocker review, CI, and merge guard before advancing. |
| Real agent / acpx / npx execution | Partially approved / still gated | Approved only for the later host-local read-only smoke/E2E slices named above, with no file/git/network/external API mutation by the tested AGENT and no Gateway/live/delivery/default-on behavior. Any broader real execution remains not approved. |
| Write-capable Claude/Codex roles | Not approved | Any Sachima-run agent step that can mutate files, state, delivery surfaces, or repositories. |
| Gateway / Feishu / live / default-on behavior | Not approved | Any live IM behavior, automatic delivery, platform adapter mutation, public ingress, or default-on route. |
| Production config / service lifecycle | Not approved | Production config writes, service restarts, Worker/runtime/service/subprocess startup, or production traffic. |
| P7 real-send canary execute | Paused | A real send requires a separate named approval that binds one concrete execution packet. |
| Active-run cancellation | WATCH | Any claim that active host/ACP runs can be reliably interrupted mid-run. |

## Next allowed work

The next safe work under the current operator approval is:

1. **Finish PR1 AgentRunSupervisorPort adapter** — Sachima source/tests/docs/runbook only; injected/default-fake backend; no real process startup.
2. **After PR1 merges, start PR2 host-local read-only real AGENT smoke** — controlled local harness only; no file/git/network/API mutation by the tested AGENT.
3. **Then PR3 persistent session lifecycle** — adapter lifecycle semantics only; no Gateway/Temporal Worker/service ownership.
4. **Then PR4 StatusProjection + task workbench view** — refs-only view fields; no raw logs/stdout/prompts/platform IDs.
5. **Then PR5 single-user production-shaped E2E** — default-off fixture with cleanup/health/rollback proof; no real ingress/delivery/production config.

P7 real-send canary execution remains paused and separate from this mainline.

## Explicit non-approvals

This status page does **not** approve:

- additional R5 source/runtime work beyond the default-off local/offline canary-hardening surface except for the named `agent-run-supervisor` integration PR slices;
- real external Sachima ingress;
- real external delivery or production delivery control;
- P7 real-send canary execute;
- Gateway/Feishu/live/default-on behavior;
- public webhook exposure;
- production config writes or service restarts;
- Gateway-owned Temporal/Worker/service/subprocess lifecycle;
- real acpx/npx/agent execution beyond the approved host-local read-only smoke/E2E slices;
- write-capable Claude/Codex roles;
- Satine or Hermes-profile ACP execution;
- production cluster or production traffic.

## Completion semantics

A task row can move to `Done` only when the task's own scoped deliverable is complete. That does not by itself approve the next stage, live behavior, delivery, production config, or write-capable agent execution. Future stages still need their own named approvals and their own verification gates.
