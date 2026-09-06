# Sachima Project Goal

## Hermes v2026.8.31 source-baseline reconciliation

This tree is the upstream-structure-first merge candidate based on Hermes
Agent `v2026.8.31`. It preserves the private Runtime Spine and native semantic
delegation while adapting product capability at upstream extension seams:
platform plugins, provider plugins, the existing tool registry, and the
dashboard API. The candidate does not itself imply a deployment, runtime
restart, configuration change, or new live surface.

The retained product additions are the default-off Sachima channel, Feishu
Task Workbench and approval presentation, profile-contained workspace and
media tools, image edit/history manifests, MiniMax-CN compatibility, Tavily,
and the official Gemini CLI ACP provider. Current upstream implementations own
Chronos, Mixture-of-Agents, gateway Session continuity, and declarative Desktop
memory-provider configuration. Full Temporal runtime, FlowWeaver/P6, P7
delivery activation, NeMo Relay, and reliable active-Run cancellation remain
explicitly deferred.

## One-sentence goal

Sachima should become a production-grade AI workbench inside a custom IM channel: a safe, reliable, durable, observable, and recoverable private-Hermes runtime-spine system designed for real production use, able to receive real IM requests, coordinate external local AGENT work, orchestrate durable long tasks, deliver results back through the channel, and preserve clear operational control.

## Target architecture

```text
Private Hermes Agent = per-user product brain and user-facing decision surface
Thin Dispatcher + Task Registry(task_id) = one task spine, with needs_agent / needs_durable as mode flags rather than lanes
Execution Port = single runtime boundary for create_or_attach / stream / signal / status / kill / liveness
agent-run-supervisor = external local AGENT event-stream runtime and liveness/permission boundary
Temporal / durable runtime = optional durable workflow backbone when needs_durable=true; workflow orchestrates, activities append
Task Event Log + Status Projection = spine-owned canonical truth and deterministic user-visible state
Evidence / Blob Store = raw prompt/stdout/tool/artifact/platform material by ref only
Hermes Gateway = platform rendering, delivery, and ACK boundary; not the runtime-spine owner
FlowWeaver / Delivery / Admission = deferred heavy layers that return only when a concrete driver requires them
```

## Final product behavior

The final Sachima experience should let an operator use IM as a real AI workbench:

1. Send a natural-language request, text or supported media, through Sachima.
2. Have Hermes classify and split the request into high-density intent summaries, never raw-text fallback cards.
3. Register the request on the private-Hermes runtime spine with a stable `task_id`; use Temporal when the task needs durable execution.
4. Show progress, approvals, blockers, artifacts, and delivery state through deterministic status projection into the IM surface.
5. Run long AI FLOW tasks such as planning, coding, testing, PR creation, CI wait, merge coordination, report generation, and recovery.
6. Deliver final text, rich cards, media, and artifacts without suppressing or confusing delivery surfaces.
7. Survive process restarts, retries, duplicate messages, partial failures, and operator rollback.
8. Keep raw prompts, platform IDs, card JSON, media bytes/paths, tool output, credentials, and raw exception text out of durable history and user-visible evidence.

## Non-negotiable principles

- Safety before live capability: prove no-leak, fail-closed, and rollback before enabling wider behavior.
- Low intrusion: Gateway should not silently own Temporal service, Worker, task queue, daemon, Docker, socket, or subprocess lifecycle.
- Explicit approvals: production config writes, Gateway restart/reload, real external ingress, delivery control, platform adapter mutation, PE-2 implementation, and live/default-on behavior each require separately named approval.
- Exact scoping: Sachima PE-1 allowlist remains exact `[sachima]`; duplicates, extra platforms, hostile list/string subclasses, and forged policies fail closed.
- Claim-check discipline: durable state carries sanitized refs, counts, digests, statuses, and stable error codes, not raw material.
- Delivery separation: final text, rich cards, progress cards, media, and ACKs are tracked as separate surfaces.

## Current architecture line

Current stable direction after the private-Hermes runtime-spine roundtable:

```text
Private Hermes Runtime Spine = highest guidance for Hermes, Claude Code, Codex CLI, and engineers.
P0 = one task_id spine + static Capability Registry + typed LaunchSpec + Execution Port + Task Event Log + Status Projection + Evidence refs + workspace lease + supervisor create_or_attach/liveness + Temporal attach-only AgentRunActivity.
Deferred = B→D live promotion, agent-death respawn resume, heavy Admission/Delivery/FlowWeaver, and live/default-on behavior.
```

The architecture guide and SVG live in `docs/architecture/private-hermes-runtime-spine-design.md` and `docs/architecture/private-hermes-runtime-spine-architecture.svg`. The active development roadmap is `docs/plans/2026-07-03-sachima-private-hermes-runtime-spine-development-plan.md`; old phase plans are superseded as active roadmap and retained as support foundation in `docs/roadmap/superseded-plans.md`. Implementation, real delivery, production config, Gateway lifecycle, Temporal Worker/service startup, and write-capable AGENT roles still require separate named approvals.

## Planning basis

Use these documents as the canonical project compass:

- `GOAL.md` — this project goal and boundary summary.
- `docs/architecture/private-hermes-runtime-spine-design.md` — highest architecture guidance for the current private-Hermes runtime spine.
- `docs/architecture/private-hermes-runtime-spine-architecture.svg` — architecture diagram for the same runtime-spine design.
- `docs/plans/2026-07-03-sachima-private-hermes-runtime-spine-development-plan.md` — active R0-R5 development roadmap for the runtime spine.
- `docs/roadmap/superseded-plans.md` — register of old plans superseded as active roadmap but retained as support foundation.
- `docs/sachima-final-goal-gap-analysis.md` — detailed gap analysis and phase-planning basis.
- `docs/sachima-channel.md` — current Sachima adapter/channel behavior.
