# Sachima Private Hermes Runtime Spine Development Plan

> **For Hermes:** Treat this as a governed docs-only development plan. Source implementation still requires a separate named approval; when approved, use `subagent-driven-development` and TDD slice by slice.

**Goal:** Build the Private Hermes Runtime Spine as Sachima's minimal runtime backbone: one `task_id` spine, refs-only event truth, deterministic projection, supervised external local AGENT attachment, and optional Temporal durability.

**Architecture:** The accepted architecture is the Private Hermes Runtime Spine. It replaces four-lane / phase-label topology with one spine plus mode flags (`needs_agent`, `needs_durable`). `agent-run-supervisor` owns external local AGENT runtime/event streaming; Temporal is an optional durable orchestrator; Gateway/Delivery/FlowWeaver/Admission are deferred heavy layers unless a later concrete driver brings them back.

**Tech Stack:** Python 3.11, `uv`, `pytest`, existing `sachima_supervisor` package conventions, local/offline tests first. Temporal SDK usage is limited to later approved attach-only bridge work; no Worker/service/test server starts in this planning gate.

---

## 1. Source of truth

Authority order for runtime-spine work:

1. `docs/architecture/private-hermes-runtime-spine-design.md`
2. `docs/architecture/private-hermes-runtime-spine-architecture.svg`
3. This plan: `docs/plans/2026-07-03-sachima-private-hermes-runtime-spine-development-plan.md`
4. `docs/roadmap/current-status.md`
5. `docs/roadmap/boundary-register.md`

If this plan and the architecture docs disagree, the architecture docs win and this plan must be corrected.

## 2. Supersession statement

Older S1-S5 integration plans, P5/P6/P7 phase work, and P7 real-send canary request-packet work **no longer govern the active roadmap**. They remain valuable **support foundation**: delivered code, tests, review lessons, no-leak constraints, default-off boundaries, and delivery/canary patterns are reusable evidence and building blocks.

The change is authority, not value:

```text
old planning sequence = superseded active roadmap
old delivered work    = retained support foundation
new active roadmap    = Private Hermes Runtime Spine R0-R5
```

See `docs/roadmap/superseded-plans.md` for the register.

## 3. Phase map

Runtime-spine source implementation is **not started and not approved** by this document. Each phase opens only under its own named approval.

| Phase | Status after this planning reset | Purpose |
|---|---|---|
| R0 — Planning reset | Done as docs/status planning | Save architecture authority, new plan, supersession register, and dashboard wording. |
| R1 — Runtime spine core | Not started / requires approval | Implement the local/offline event-log, registry, projection, LaunchSpec, and capability table core. |
| R2 — Supervisor Execution Port | Not started / requires approval | Add a deterministic offline `agent-run-supervisor` execution-port seam. |
| R3 — Temporal attach-only durable bridge | Not started / requires approval | Map durable workflows to attach-only activity semantics without owning runtime lifecycle. |
| R4 — Workspace + permission + projection integration | Not started / requires approval | Integrate workspace lease, permission roundtrip, and projection surfaces. |
| R5 — Controlled canary / product hardening | Not started / requires approval | Prepare bounded canary/product hardening without default-on or live delivery. |

## 4. R0 — Planning reset

**Goal:** Make the Private Hermes Runtime Spine the active planning authority and demote historical phase plans to support foundation.

**Allowed scope:**

- Create this plan.
- Create `docs/roadmap/superseded-plans.md`.
- Update `GOAL.md`, `docs/architecture/README.md`, `docs/roadmap/current-status.md`, `docs/roadmap/reference-index.md`, `docs/roadmap/boundary-register.md`, and `docs/roadmap/README.md`.

**Explicit non-approvals:**

- No runtime/source implementation.
- No real agent, `acpx`, or `npx` execution.
- No Temporal Worker/service/runtime/subprocess startup.
- No Gateway/Feishu/live/default-on/public ingress.
- No production config, real delivery, or write-capable roles.

**Acceptance gates:**

- New plan and superseded-plan register exist.
- Current docs point to the plan/register and preserve architecture authority.
- Changed-file allowlist stays docs/roadmap/architecture/GOAL/plans only.
- Secret/platform-ID added-line scan passes.
- Stale wording scan proves old roadmap text is not presented as current authority.
- Independent Codex read-only blocker review passes.

**Next approval boundary:** R1 implementation gate.

## 5. R1 — Runtime spine core

**Goal:** Implement the local/offline spine core: one `task_id`, one monotonic event sequence authority, refs-only events, deterministic projection, registry snapshot cache, static capability registry, and typed LaunchSpec.

**Candidate files for R1:**

- Create: `sachima_supervisor/runtime_spine/__init__.py`
- Create: `sachima_supervisor/runtime_spine/events.py`
- Create: `sachima_supervisor/runtime_spine/registry.py`
- Create: `sachima_supervisor/runtime_spine/projection.py`
- Create: `sachima_supervisor/runtime_spine/capabilities.py`
- Create: `sachima_supervisor/runtime_spine/launch_spec.py`
- Test: `tests/sachima_supervisor/runtime_spine/test_event_log.py`
- Test: `tests/sachima_supervisor/runtime_spine/test_projection.py`
- Test: `tests/sachima_supervisor/runtime_spine/test_registry.py`
- Test: `tests/sachima_supervisor/runtime_spine/test_launch_spec_capabilities.py`

**Allowed scope:**

- Local/offline Python source and tests only.
- In-memory or file-local deterministic test stores only.
- No network, no platform adapters, no process launch.

**Explicit non-approvals:**

- No supervisor execution-port wiring; that is R2.
- No real agent / `acpx` / `npx`.
- No Temporal Worker, service, test server, or task queue.
- No Gateway, Feishu, live/default-on route, public ingress, production config, or real delivery.
- No write-capable AGENT roles.

**Required tests / gates:**

1. **Single seq authority:** concurrent or repeated appends for one `task_id` produce strictly monotonic sequence numbers and reject gaps/duplicates/out-of-order writes.
2. **Refs-only events:** event bodies cannot contain raw prompt/stdout/tool output/artifact/platform material; heavy content must be represented by refs.
3. **Deterministic projection:** replaying the same ordered events yields byte-stable projection output.
4. **Registry snapshot cache:** snapshot is derived from the log, versioned, and invalidated/refreshed when new events arrive.
5. **Capability registry:** static table validates `agent_kind` and feature flags without plugin loading.
6. **LaunchSpec:** typed validation rejects unknown mode flags, platform-derived values, and unsupported capabilities.
7. **Forbidden-surface scan:** added source lines contain no Gateway/Feishu/live/default-on/public-ingress/production-config/real-send/Worker-start/process-launch wiring.
8. **No-leak scan:** event/projection/log/status outputs contain refs and stable codes only.

**Next approval boundary:** R2 supervisor execution-port gate.

## 6. R2 — Supervisor Execution Port

**Goal:** Add the execution-port abstraction that lets the spine talk to `agent-run-supervisor` semantics while still using a deterministic offline adapter.

**Candidate files:**

- Create: `sachima_supervisor/runtime_spine/execution_port.py`
- Create: `sachima_supervisor/runtime_spine/fake_supervisor_port.py`
- Test: `tests/sachima_supervisor/runtime_spine/test_execution_port.py`
- Test: `tests/sachima_supervisor/runtime_spine/test_fake_supervisor_port.py`

**Allowed scope:**

- Interface + fake/offline deterministic adapter.
- Contract tests for `create_or_attach`, `stream`, `signal`, `status`, `kill`, and `liveness` semantics.
- ≤1 simulated live session per `task_id`.

**Explicit non-approvals:**

- No real `agent-run-supervisor` process.
- No real agent / `acpx` / `npx`.
- No OS process launch, subprocess, Docker, daemon, socket listener, or external service.
- No Temporal Worker/service/Gateway/live/delivery.

**Required tests / gates:**

- `create_or_attach` returns the same session for duplicate starts.
- `permission-wait` is alive, not stalled.
- `kill` / terminal states append refs-only events.
- Simulated supervisor events flow through R1 Event Log and Status Projection deterministically.
- Orphan-reaper policy is defined but only tested against fake liveness.

**Next approval boundary:** R3 Temporal attach-only durable bridge.

## 7. R3 — Temporal attach-only durable bridge

**Goal:** Connect durable workflow semantics to the spine without letting Temporal own or spawn AGENT processes.

**Candidate files:**

- Create: `sachima_supervisor/runtime_spine/temporal_bridge.py`
- Test: `tests/sachima_supervisor/runtime_spine/test_temporal_bridge_contract.py`

**Allowed scope:**

- Pure mapping/contract code.
- Static/fake-client/replay-fixture tests only.
- Heartbeat payload model limited to cursor, phase, counters, and refs.

**Explicit non-approvals:**

- No `WorkflowEnvironment`, Temporal test server, Worker, task queue, Docker, service, daemon, subprocess, or live cluster startup.
- No real agent/acpx/npx execution.
- No Gateway/live/delivery.

**Required tests / gates:**

- AgentRunActivity contract is attach-existing only.
- No create/spawn branch is reachable from the bridge.
- Heartbeats are refs-only.
- Workflow is modeled as orchestrator, not producer; activities append through the spine boundary.
- Retry/replay cannot duplicate a live agent process.

**Next approval boundary:** R4 workspace + permission + projection integration.

## 8. R4 — Workspace + permission + projection integration

**Goal:** Integrate workspace leases, permission roundtrip, read-only/default-deny role constraints, and user-visible projection surfaces.

**Candidate files:**

- Create: `sachima_supervisor/runtime_spine/workspace.py`
- Create: `sachima_supervisor/runtime_spine/permissions.py`
- Create: `sachima_supervisor/runtime_spine/view_model.py`
- Test: `tests/sachima_supervisor/runtime_spine/test_workspace_lease.py`
- Test: `tests/sachima_supervisor/runtime_spine/test_permissions.py`
- Test: `tests/sachima_supervisor/runtime_spine/test_view_model.py`

**Allowed scope:**

- Local/offline workspace lease logic.
- Permission request/decision refs and view-model projection.
- Read-only/default-deny role enforcement.

**Explicit non-approvals:**

- No write-capable AGENT roles.
- No actual IM/Gateway send/edit call.
- No platform IDs in event/projection state.
- No live/default-on/public ingress/production config/real delivery.

**Required tests / gates:**

- Single-writer lease rejects second writer until release/expiry policy says otherwise.
- Permission request emits refs-only event; answer returns through Hermes-controlled `signal(task_id, decision/ref)` model.
- Default-deny/read-only policy rejects write role attempts.
- View model is deterministic and platform-neutral.

**Next approval boundary:** R5 controlled canary/product hardening.

## 9. R5 — Controlled canary / product hardening

**Goal:** Prepare controlled product hardening and canary material without converting the project to live/default-on behavior.

**Allowed scope:**

- Observability/error handling behind default-off controls.
- Bounded canary request packet using the safe-label/receiver-bridge pattern.
- Dry-run/product-hardening evidence only unless a later real-send gate is explicitly approved.

**Explicit non-approvals:**

- No real send or delivery without a separate bounded execution approval.
- No default-on behavior.
- No public ingress.
- No production rollout/config.
- No Gateway/service lifecycle unless separately approved.

**Required tests / gates:**

- Default-off controls verified.
- Kill/rollback conditions documented.
- Safe-label receiver mapping remains private and out of core history/logs.
- Real-send canary, if later requested, binds exactly one target, one surface, and one execution.

**Next approval boundary:** separate bounded real-send / production approval, outside this plan.

## 10. First implementation slice recommendation

Start with **R1 only**. Do not bundle R2/R3/R4 just because the architecture mentions them. R1 is the smallest behavior-bearing slice that proves the spine exists:

```text
Task Registry + Event Log + Status Projection + Capability Registry + LaunchSpec
```

R1 must finish with offline tests proving:

- single monotonic `seq` authority;
- refs-only events;
- deterministic projection;
- registry snapshot cache correctness;
- static capability validation;
- no live/runtime/Gateway/Temporal Worker/process launch surfaces.

## 11. Tail register

| Tail | Class | Owner | Gate | Acceptance |
|---|---|---|---|---|
| Projection determinism can regress as event types grow. | WATCH | R1 implementer + reviewer | Every phase | Replay fixture with byte-stable projection. |
| Refs-only boundary can leak raw prompt/stdout/tool output/platform IDs. | BLOCKER if found | R1+ implementer | Every phase | Added-line scan + negative tests. |
| Duplicate launch / attach races can reappear when R2 begins. | NEXT_PHASE | R2 implementer | R2 | Duplicate `create_or_attach` tests and ≤1 live session invariant. |
| AgentRunActivity can accidentally create/spawn instead of attach. | NEXT_PHASE / BLOCKER if found | R3 implementer | R3 | Test proves no create branch and no OS process launch. |
| Permission-wait may be misclassified as stalled. | NEXT_PHASE | R2/R4 implementer | R2/R4 | Liveness tests treat permission-wait as alive. |
| Workspace lease may be implemented as git-worktree-specific instead of invariant. | WATCH | R4 implementer | R4 | Lease tests independent of git implementation. |
| P7 real-send canary remains tempting but is not current mainline. | PARKED | Hermes/controller | R5 or separate P7 gate | Separate named approval with concrete safe values only. |

## 12. Recommended next approval text

```text
批准进入 Sachima R1 Runtime Spine Core implementation gate。
目标：在 release/sachima 上实现 Private Hermes Runtime Spine 的本地/offline core：Task Registry、refs-only Task Event Log、single monotonic seq authority、deterministic Status Projection、static Capability Registry、typed LaunchSpec，并用 TDD 完成 focused unit tests。
范围：local/offline source + tests only；建议路径 sachima_supervisor/runtime_spine/* 与 tests/sachima_supervisor/runtime_spine/*。
必须覆盖：seq monotonic/gap/duplicate rejection、refs-only no-leak、projection deterministic replay、registry snapshot cache invalidation、capability validation、LaunchSpec fail-closed、forbidden live/runtime/Gateway/Worker/process surface scan。
不批准：real agent/acpx/npx execution；Temporal Worker/service/runtime/subprocess startup；Gateway/Feishu/live/default-on/public ingress；production config；real delivery；write-capable roles；R2/R3/R4/R5 implementation。
AGENT 分工：Claude Code main programmer；Codex CLI read-only blocker review；Hermes 控场、CodeGraph、验证 gates、PR/审批收口。
完成标准：local focused tests + no-leak/forbidden-surface scan + git diff --check + Codex blocker review + CI 通过后，开 PR 并发送绑定最新 head SHA 的 Feishu 审批卡。
如发现必须越界才能继续，立即暂停并报告需要哪一个新的 named approval。
```
