# Sachima R5 Controlled Canary / Product Hardening

> Scope: R5 local/offline product hardening and bounded canary preparation for the Private Hermes Runtime Spine. This document does not approve real-send execution, live/default-on behavior, Gateway/service lifecycle, production rollout, real agent execution, or write-capable roles.

## Goal

R5 prepares the runtime spine for a later bounded canary without converting Sachima into a live/default-on delivery system. The approved R5 deliverable is a default-off, refs-only, dry-run-only control surface that can describe one future canary packet and one observable dry-run report.

## Authority

1. `docs/architecture/private-hermes-runtime-spine-design.md`
2. `docs/plans/2026-07-03-sachima-private-hermes-runtime-spine-development-plan.md`
3. `docs/roadmap/current-status.md`
4. Completed R1/R2/R3/R4 local/offline runtime-spine foundation

## Implemented local/offline shape

R5 adds a pure runtime-spine canary packet model:

- `CanaryRequestPacket` is always default-off, dry-run-only, and execution-not-authorized.
- The only surface is exactly `final_text`.
- The attempt budget is exactly `1`.
- `target_ref` and `receiver_bridge_ref` are opaque `safe_*` labels only.
- Concrete receiver mapping, endpoint material, platform identifiers, and raw payloads stay outside the core.
- `CanaryDryRunReport` can report dry-run readiness only; it cannot claim a send or expose receiver mapping.
- Serialization is canonical JSON after full trust-boundary validation.

## Safe-label receiver-bridge boundary

The runtime spine may carry a safe label such as `safe_*` as a claim-check reference. It must not carry the receiver address book. The private receiver/bridge owns the mapping from safe label to exactly one local transcript or later approved test recipient.

Core history, event logs, status projections, view models, dry-run reports, docs/status dashboards, and PR artifacts must remain refs-only. If a future canary needs concrete target material, that material belongs to a separately approved receiver/bridge config or operator-owned private mapping, never to this R5 core surface.

## Default-off and stop semantics

A canary packet is blocked unless a later named execution gate binds all concrete safe values. Stop conditions are part of the packet contract:

- approval missing
- duplicate attempt
- leak detected
- receiver unavailable
- unexpected surface

Any widening of surface, attempt budget, receiver scope, live/default-on behavior, or concrete receiver mapping is a fail-closed blocker and requires a new named approval.

## Observability and rollback semantics

R5 observability is dry-run/product-hardening evidence only:

- `send_attempts` is always `0`.
- `sent` counter is always `0`.
- ready dry-run status is explicit and stable.
- rollback is represented by a safe rollback ref, not by executing a service restart or config mutation.
- error surfaces carry stable codes only, never raw exception or raw platform output.

## Verification matrix

| Requirement | Evidence |
|---|---|
| Default-off controls | Packet validation pins default-off, dry-run-only, execution-not-authorized. |
| Single bounded canary shape | Tests reject non-`final_text` surfaces and attempts other than `1`. |
| Private receiver mapping | Tests reject platform-shaped refs and keep mapping out of packet/report dictionaries. |
| No real send | Dry-run report validator rejects any send attempt or `sent` counter. |
| Stable refs-only observability | Packet/report serialization passes no-leak scan and exact validation. |
| Preserve R1-R4 semantics | Runtime-spine regression tests remain the required gate. |

## Explicit non-approvals

R5 does not approve:

- real send or delivery;
- P7 real-send canary execution;
- live/default-on/public ingress;
- Gateway, Feishu, platform-adapter mutation, or service lifecycle;
- production config writes or production rollout;
- Temporal Worker/service/runtime/test server/task queue startup;
- real agent, acpx, or npx execution;
- Docker, daemon, subprocess, socket listener, or external service startup;
- write-capable AGENT roles.

## Next approval boundary

A later bounded execution approval must bind exactly one concrete safe label, one surface, one attempt, one receiver class, one evidence class, and one rollback/stop policy. If those concrete values are missing or require live/service/production mutation, execution must stop and ask for a narrower named approval.
