# Superseded Plans Register

This register marks historical Sachima planning lines that are **superseded as the active roadmap** by the Private Hermes Runtime Spine architecture and the new development plan.

Superseded does **not** mean discarded. The old work is not wasted. Delivered code, tests, review lessons, no-leak constraints, default-off boundaries, canary-request patterns, and failure findings remain support foundation for the runtime-spine roadmap.

## Current authority

Use these documents for current planning authority:

1. `docs/architecture/private-hermes-runtime-spine-design.md`
2. `docs/architecture/private-hermes-runtime-spine-architecture.svg`
3. `docs/plans/2026-07-03-sachima-private-hermes-runtime-spine-development-plan.md`
4. `docs/roadmap/current-status.md`
5. `docs/roadmap/boundary-register.md`

Historical docs remain discoverable through `docs/roadmap/reference-index.md`, but they must not override the authority list above.

## Category register

| Category | Status | Retained value | Must not be used as current authority |
|---|---|---|---|
| Original final-goal / PE planning | Superseded as active roadmap; retained as historical evidence. | Product ambition, early gap framing, safety instincts, and final-workbench motivation. | Phase sequence, PE milestone ordering, or old assumptions that FlowWeaver/Admission/Delivery are P0 runtime-spine components. |
| Agent-run-supervisor local/offline phases | Superseded as active roadmap; retained as support foundation. | Local/offline supervisor seams, controlled execution lessons, persistent-session/cancellation findings, and read-only role constraints. | Any roadmap claim that supervisor integration alone is the whole mainline, or that historical phase ordering dictates R1-R5. |
| P5 / P6 / P7 phase roadmap | Superseded as active roadmap; retained as support foundation. | Temporal foundation, controlled AI FLOW composition, bounded real-agent prerequisites, caller-owned lifecycle boundaries, and delivery/ACK safety patterns. | Any claim that P5/P6/P7 phase labels are current architecture components or next-phase authorities. |
| S1-S5 integration line | Superseded as active roadmap; retained as validated evidence. | S2 seam, S3 Activity/controller, S4 bounded read-only real-agent step, S5 downstream reconnect, no-leak/fail-closed/idempotency lessons. | Treating S1-S5 as the active implementation sequence. Future work must map through R1-R5. |
| P7 real-send canary request packet | Superseded as active roadmap; retained as R5 support pattern. | Bounded request-packet discipline, safe-label requirement, exact one-target/one-surface/one-execution thinking, post-send evidence model. | Any live-send authorization. Real send still requires a separate bounded approval with concrete safe values and receiver mapping. |

## Current roadmap mapping

Historical work should be interpreted through the runtime-spine map:

| Runtime-spine phase | Historical support it may reuse |
|---|---|
| R1 Runtime Spine Core | No-leak/fail-closed patterns from S2-S5; Temporal-state lessons from P5; status-dashboard discipline. |
| R2 Supervisor Execution Port | agent-run-supervisor local/offline seams; P6 controlled attach/lifecycle lessons; bounded read-only role constraints. |
| R3 Temporal attach-only durable bridge | P5 Temporal foundation; S3 Activity/controller; S4 attach-not-spawn and heartbeat/no-leak lessons. |
| R4 Workspace + permission + projection integration | P6 runtime lifecycle, permission-wait/liveness lessons, projection/status no-leak constraints. |
| R5 Controlled canary / product hardening | P7 delivery/ACK closure and bounded real-send request-packet pattern. |

## Boundary reminder

This register does **not** approve:

- runtime/source implementation;
- real agent, `acpx`, or `npx` execution;
- Temporal Worker/service/runtime/subprocess startup;
- Gateway/Feishu/live/default-on/public ingress;
- production config writes;
- real delivery;
- write-capable Claude/Codex/AGENT roles.

Approvals come only from the named phase gates in the current development plan.
