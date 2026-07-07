# Sachima Roadmap Current Status

> Lean project dashboard for AGENT-facing project state. This file aligns the active product goal, stage, task progress, blockers, non-approvals, and next allowed work. It is not a repository-process ledger, results database, or historical diary.

## How to read this file

- Use this page to decide what the project is trying to achieve now, what is done, what is blocked, and what can be requested next.
- Task rows record work-state only: `Done`, `In progress`, `Blocked`, `Not started`, or `Paused`.
- A `Done` row is a project-task state, not a quality certificate. Quality-control evidence remains outside the task-state row unless it changes the task state.
- Do not record repository/process bookkeeping, external-check matrices, hashes, or流水账 here.
- Long design details live in the referenced plans/runbooks. Runtime truth still requires fresh checks before any live or production-facing action.

## Dynamic status policy

Machine-owned dynamic status is intentionally absent from this lean dashboard. This page records only the human/developer-facing task state and boundary posture.

## Current project position

| Field | Current truth |
|---|---|
| Product goal | Production-grade AI workbench inside a custom IM channel, guided by the private-Hermes runtime spine: one per-user Hermes Agent, one `task_id` spine, supervised external local AGENT event streams, optional Temporal durability, and controlled delivery surfaces. |
| Active mainlines | (1) Preserve the Private Hermes Runtime Spine as the highest architecture guidance for Hermes, Claude Code, Codex CLI, and engineers. (2) Keep the R0-R5 runtime-spine foundation done as local/offline/default-off slices under `docs/plans/2026-07-03-sachima-private-hermes-runtime-spine-development-plan.md`. (3) Treat the already-completed `agent-run-supervisor` foundation as support for the live-stream consumption mainline: adapter, host-local read-only smoke shape, persistent lifecycle, workbench view, production-shaped E2E, and safe live-progress projection. (4) Advance live-stream consumption through `docs/plans/2026-07-05-ars-live-stream-integration-plan.md`: LS1 workbench composition (done), LS2 source binding (done), LS3 caller-API compatibility smoke (done), and LS4-A default-off local/offline query activation gate (done), then request a separately approved LS4 runtime/Gateway query surface. (5) Keep P7 downstream real-send canary execution paused as delivery-safety support, not the mainline. |
| Current stage | R0 planning reset, R1 runtime-spine core, R2 supervisor execution port, R3 Temporal attach-only durable bridge, R4 workspace + permission + projection integration, and R5 controlled canary / product hardening are done as local/offline/default-off foundation. The runtime-spine architecture is saved under `docs/architecture/`, the active R0-R5 development roadmap is saved under `docs/plans/`, and old phase plans are registered as superseded active roadmap / retained support foundation. The `agent-run-supervisor` live-progress safe projection exists as a standalone local/offline read-model; LS1 has wired that projection into the combined task workbench view, LS2 has added private source binding / cursor state for tracked sessions, LS3 has locked the synthetic-artifact caller-API compatibility smoke as a local/offline task, and LS4-A has added a default-off local/offline `query_task_live_progress` activation gate over that binding + combined view. The LS4 runtime/Gateway/Feishu query surface remains the next separately approved gate. |
| Current completed foundation | R1 runtime-spine core, R2 supervisor execution port, R3 Temporal attach-only durable bridge, R4 workspace + permission + projection integration, R5 controlled canary / product hardening, agent-run-supervisor adapter/persistent lifecycle/workbench/E2E foundations, agent-run-supervisor live-progress safe projection, LS1 live workbench composition, LS2 live-progress source binding, LS3 caller-API compatibility smoke, LS4-A default-off query activation gate, S1 integration design, S2 local/offline adapter seam, S3 Activity/controller design, S3 hermetic-local Activity implementation, S4 read-only real-agent step design, S4 read-only real-agent step implementation, S5 downstream delivery reconnect design, S5 downstream delivery reconnect implementation, and P7 bounded real-send canary request-packet preparation are all done as project-task candidates/support foundation. |
| Current design authority | `docs/architecture/private-hermes-runtime-spine-design.md` and `docs/architecture/private-hermes-runtime-spine-architecture.svg` are the highest architecture guidance. `docs/plans/2026-07-03-sachima-private-hermes-runtime-spine-development-plan.md` is the active development roadmap under that architecture, and `docs/roadmap/superseded-plans.md` records old roadmap supersession. They supersede phase-label/topology interpretations that imply four independent lanes, Gateway-owned runtime lifecycle, Temporal-owned AGENT processes, or heavy Admission/Delivery/FlowWeaver as P0 components. |
| Current boundary | R1/R2/R3/R4/R5 runtime-spine work and the existing agent-run-supervisor foundation remain local/offline/default-off. The live-stream integration plan has completed LS1 local/offline workbench composition, LS2 private source binding, LS3 synthetic-artifact caller-API compatibility smoke, and LS4-A default-off local/offline query activation gate; the later LS4 runtime/Gateway/query activation surface remains a separate approval gate. This status page still does not approve live/default-on behavior, real delivery, production config, Gateway lifecycle, Temporal Worker/service startup, write-capable agent roles, public webhook exposure, real external Sachima ingress, or broad real acpx/npx/agent execution. |

## Stage / feature board

| Stage / task | Status | Work-state note | Role in the mainline |
|---|---|---|---|
| Mainline calibration | Done | Current core direction is the Private Hermes Runtime Spine: one per-user Hermes Agent, one `task_id` spine, `needs_agent` / `needs_durable` mode flags, and deferred heavy layers. | Reclassified earlier P5/P6/P7 work as support foundation rather than wasted work. |
| Private Hermes Runtime Spine architecture | Done | Claude Code Architect authored the final design and SVG after Hermes/Codex roundtable convergence. | Highest guiding architecture for Hermes, Claude Code, Codex CLI, and engineers. |
| R0 runtime-spine planning reset | Done | New R0-R5 development plan and superseded-plans register define the active roadmap. | Makes old S1-S5/P5/P6/P7 plans support foundation rather than active roadmap. |
| R1 runtime-spine core | Done | Local/offline core implementation task complete. | Provides Task Registry, refs-only Event Log, monotonic seq authority, deterministic Status Projection, static Capability Registry, and typed LaunchSpec for the next candidate gate. |
| R2 supervisor execution port | Done | Deterministic fake/offline execution-port implementation task complete. | Adds offline/fake supervisor port semantics only. |
| R3 Temporal attach-only durable bridge | Done | Local/offline attach-only durable bridge implementation task complete. | Adds attach-only durable bridge contracts without Worker/service startup. |
| R4 workspace + permission + projection integration | Done | Local/offline implementation task complete: workspace single-writer lease, permission roundtrip, read-only/default-deny role policy, and platform-neutral refs-only view model. | Adds lease, permission roundtrip, and platform-neutral view model. |
| R5 controlled canary / product hardening | Done | Default-off local/offline preparation task complete: controlled canary packet, dry-run observability report, stable stop/rollback semantics, and safe-label receiver-bridge boundary. | Keeps canary/product hardening default-off; real send remains separate. |
| AgentRunSupervisorPort adapter | Done | Local/offline implementation task complete: injected/default-fake backend adapter only, no real process startup. | Adds a Sachima-side adapter from runtime-spine `ExecutionPort` semantics to an injected supervisor backend surface. |
| Host-local read-only real AGENT smoke | Done | Local/offline implementation task complete: bounded read-only smoke harness over the adapter plus fail-closed real-supervisor readiness gate; no real launch by default and no runner is marked ready without a local path whose bytes match the pinned digest. | Proves the first host-local read-only supervisor-smoke shape while preserving default-off/non-live boundaries. |
| Persistent session lifecycle | Done | Local/offline implementation task complete: persistent create/attach re-attach over a reconstructed port (no duplicate `agent_attached`; fresh/missing backend fails closed, no respawn), `stream(since_seq=...)` resume cursor + refs-only `LifecycleSnapshot` safe resume data, adapter-local default-off `close` handoff, explicit status/liveness backend-read-failure policy (transient stable code, no mark/kill/mutation), and no role/workspace-ref drift on re-attach. | Hardens lifecycle and lease/task binding. |
| StatusProjection + task workbench view | Done | Local/offline implementation task complete: a refs-only workbench view composing the `TaskViewModel` Status Projection with the `LifecycleSnapshot` for a locally tracked session — deterministic, byte-stable, fail-closed, no-leak — plus a focused test file, a runbook, and package exports. No live UI/IM/delivery. | Makes supervised task state visible through safe refs-only fields. |
| Single-user production-shaped E2E | Done | Local/offline implementation task complete: a default-off single-user fixture that drives the adapter through reconstruct/attach (one session, one `agent_attached`), an optional deterministic permission-wait + operator-decision path, a renderable workbench view before cleanup, deterministic kill/orphan-free cleanup + lease release, and a rollback-safe restart, summarized in a fail-closed, byte-stable, no-leak `ProductionE2EReport`; plus a focused test file, a runbook, and package exports. This does **not** mean production上线, live ingress, real delivery, Gateway behavior, Temporal Worker startup, or production config. | End-to-end proof while preserving non-approvals. |
| Live stream safe projection | Done | Local/offline projection task complete: `LiveProgressProjection` maps `agent-run-supervisor` progress artifacts and cursor pages into refs-only, fail-closed, byte-stable Sachima projection data. It is not yet wired into the task workbench/query chain. | Provides the safe read-model foundation for live-stream consumption. |
| Live stream workbench/query integration plan | Done as docs-only plan | `docs/plans/2026-07-05-ars-live-stream-integration-plan.md` defines LS1 through LS4: workbench composition, source binding, caller-API compatibility smoke, and later runtime/query activation. Source implementation remains unapproved until a named LS approval. | Governs the next live-stream consumption mainline. |
| LS1 live workbench composition | Done | Local/offline slice complete: composes the `AgentRunSupervisorWorkbenchView` with the `LiveProgressProjection` into one refs-only, fail-closed, byte-stable combined workbench view for a locally tracked session. No live UI/IM/delivery. | First live-stream consumption slice under the integration plan. |
| LS2 live-progress source binding | Done | Local/offline slice complete: a host-owned `LiveProgressSourceBindings` layer resolves a tracked session to its private reader-only `artifact_dir`, safe `artifact_ref`, and foreign `last_seen_cursor`, and drives the LS1 view from that binding. The private path is never serialized/logged; the foreign cursor never enters `TaskEventLog`. | Binds tracked sessions to their private live-progress source. |
| LS3 caller-API compatibility smoke | Done | Local/offline slice complete: a read-only smoke reads synthetic `progress.json` + `normalized-events.jsonl` through the real `agent_run_supervisor.hermes_caller.events` caller API and maps them into the existing refs-only projection / combined workbench view plus a stable outcome report, locking Sachima's reader contract, `has_more`/`next_cursor`/`after_seq` cursor behavior, nullable-field normalization, legacy no-`seq` fallback, and corrupt / import-absent fail-closed boundaries against the current ARS API. Reads fixtures only — no real AGENT/acpx/npx launch, no Gateway/Feishu/live/default-on, and no hard import of `agent-run-supervisor` at module load. The real caller API now comes only from the exact-pinned `agent-run-supervisor` PyPI extra (installed in CI via `dev`), so real-API tests run for real there and skip only on lean environments without the extra. | Pins field/cursor/nullable compatibility so later runtime wiring does not guess field names. |
| LS4-A default-off query activation gate | Done | Local/offline slice complete: a `query_task_live_progress(task_id, session_id, after_seq=None, limit=100)` entrypoint (plus a `LiveProgressQueryService`) that is **disabled by default** — a caller must present an explicit `LiveProgressQueryActivationGate` for an approved `local_offline`/`hermes_internal` surface before any read. A disabled query fails closed with a stable code and never calls the reader, appends no `TaskEventLog` event, updates no binding cursor, and launches nothing. An enabled local/offline query resolves the LS2 binding and composes the LS1 combined view using the private `artifact_dir` for the reader only (never serialized) and `after_seq` override else the binding cursor; it stays read-only. Gateway/Feishu/IM/delivery/public-ingress/Temporal-Worker/production/default-on surfaces are denied by an exact allowlist. | Gives Sachima a controlled, default-off local/offline live-progress query without touching runtime/Gateway. |
| Packaged agent-run-supervisor dependency | Done | Dependency task complete: `agent-run-supervisor==0.1.3` is declared as an exact-pinned optional extra (mirrored into `dev` for CI), the pin checker expects `0.1.3`, and every source-path channel — the gateway `sys.path` shim envs, the test sibling-checkout constant, and runbook `PYTHONPATH` instructions — is retired repo-wide with a packaging guard test (`test_no_agent_run_supervisor_source_path_references`) plus pin-consistency and lock-resolution tests. Unreleased ARS changes are validated only by installing a locally built wheel/editable package into an isolated environment; the checker reports such versions honestly. All lazy-import, fail-closed, and default-off gates are unchanged. | Makes the installed exact-pinned distribution the only way Sachima reaches agent-run-supervisor. |
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
| S5 implementation quality gate | Done | Quality closeout complete for the S5 implementation candidate; required before P7 bounded real-send canary request-packet preparation. This status page does not authorize P7 execution. |
| R3 Temporal attach-only durable bridge implementation | Done | R3 attach-only durable bridge source implementation is complete as a local/offline task; this status page does not approve Worker/service startup or live execution. |
| Agent-run-supervisor integration foundation | Done | Adapter, host-local smoke shape, persistent lifecycle, workbench view, production-shaped E2E, and live-progress safe projection are complete as local/offline/default-off foundation. The library itself is consumed only as the exact-pinned `agent-run-supervisor==0.1.3` PyPI extra — no source-checkout / `PYTHONPATH` / `sys.path` channel remains. Fresh repo/runtime checks are still required before reuse. |
| Live stream workbench/query integration | LS1-LS3 + LS4-A done; LS4 runtime/Gateway surface not approved | LS1 workbench composition, LS2 private source binding, LS3 caller-API compatibility smoke, and LS4-A default-off local/offline query activation gate are done as local/offline/default-off slices; the LS4 runtime/Gateway/Feishu query surface remains a later separately approved task. |
| Agent-run-supervisor/acpx runner pin | Done as local/offline maintenance | Sachima runner-provenance gates admit host-local overlays only when they pin verified absolute local `acpx` 0.12.0 executables. Historical 0.10.0 smoke evidence is retained as history only. This does not approve real acpx/npx/agent execution. |
| Real agent / acpx / npx execution | Not approved outside completed synthetic-artifact caller-API smoke | LS1 and LS2 use fakes/local binding only; completed LS3 imports/reads synthetic artifacts through the caller API but must not launch a real agent/acpx/npx process. Any broader real execution remains not approved. |
| Write-capable Claude/Codex roles | Not approved | Any Sachima-run agent step that can mutate files, state, delivery surfaces, or repositories. |
| Gateway / Feishu / live / default-on behavior | Not approved | Any live IM behavior, automatic delivery, platform adapter mutation, public ingress, or default-on route. |
| Production config / service lifecycle | Not approved | Production config writes, service restarts, Worker/runtime/service/subprocess startup, or production traffic. |
| P7 real-send canary execute | Paused | A real send requires a separate named approval that binds one concrete execution packet. |
| Active-run cancellation | WATCH | Any claim that active host/ACP runs can be reliably interrupted mid-run. |

## Next allowed work

The next safe work is:

1. **Request or approve a separately scoped LS4 runtime/Gateway query surface** — LS1 workbench composition, LS2 private source binding, LS3 synthetic-artifact caller-API compatibility smoke, and LS4-A default-off local/offline query activation gate are done as local/offline/default-off slices; the remaining LS4 runtime/Gateway/Feishu surface is the next candidate.
2. **Keep the LS4 runtime/Gateway surface separate from live/default-on rollout** — the LS4-A gate stays local/offline (`local_offline`/`hermes_internal`) and default-off; any runtime/Gateway/query activation still needs its own named approval and must not imply real AGENT/acpx/npx launch, Gateway/Feishu/live/default-on behavior, real delivery, service lifecycle, or production config.

P7 real-send canary execution remains paused and separate from this mainline.

## Explicit non-approvals

This status page does **not** approve:

- additional R5 source/runtime work beyond the default-off local/offline canary-hardening surface except for the named `agent-run-supervisor` integration slices;
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
