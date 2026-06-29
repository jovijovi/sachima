# P7 Real Delivery / ACK Closure — Design Gate (PRD)

Date: 2026-06-29
Owner: Architect
Status: **Docs-only design gate.** This artifact specifies the target design for real outbound delivery and ACK closure. It does not approve implementation, real delivery, live/default-on behavior, production config writes, service/runtime/Worker startup, real external ingress, or Sachima runtime agent/acpx/npx execution.
Branch: `docs/p7-real-delivery-ack-design`
Base: `release/sachima`

## Scope

This gate fixes the design for P7 real outbound delivery and ACK closure so the later implementation is small, bounded, and reviewable. It:

1. states the real-delivery / ACK-closure problem and why it is a new risk class;
2. separates existing fake/local/injected delivery evidence from real IM delivery;
3. specifies the delivery-slot state model, ACK source-of-truth, retry/duplicate/idempotency, failure/WATCH, rollback, and no-leak semantics;
4. fixes the boundaries and the separate approvals that the later implementation and any canary/live rollout must each obtain.

## Authority inputs

- `GOAL.md` — production-grade IM AI workbench goal: safety, durability, observability, recoverability, operational control.
- `docs/roadmap/current-status.md` — phase/feature dashboard and explicit non-approvals.
- `docs/sachima-channel.md` — current adapter behavior, delivery callback envelope, fake-send simulator status.
- `docs/protocols/sachima-envelope-v1.md` — pointer to the canonical external Sachima protocol authority.
- `docs/runbooks/flowweaver-delivery-activity-ack-reconciliation.md` — injected-surface delivery/ACK contract.
- `docs/runbooks/flowweaver-pe2-controlled-runtime-fake-delivery.md` — PE-2A controlled-runtime fake-delivery evidence boundary.
- `gateway/delivery.py`, `gateway/flowweaver_delivery_activity.py`, `gateway/flowweaver_pe2_controlled_runtime_delivery_bridge.py` — current delivery routing, injected delivery/ACK Activity, and fake-send bridge.

## Problem

Sachima already has strong local and staging-shaped delivery evidence: adapter callback envelopes, local fallback/fake-send behavior, PE-2A controlled-runtime fake-send ACK closure, Phase32 injected delivery with sanitized ACK reconciliation, and P6 controlled AI FLOW / runtime-attach foundations.

P7 is a different risk class. Real delivery means a platform-visible message leaves the system, and ACK closure becomes operational truth rather than simulator truth. The failure to design out is treating an HTTP `2xx` callback, a fake-send ACK, or a rendered rich card as proof that the final user-visible response was delivered.

The design fixes exact closure semantics before any code or live behavior:

```text
initialized delivery slot
  -> approved, bounded real-send attempt
  -> platform/client response classified accepted | failed | unknown
  -> sanitized ACK tied to the originating slot
  -> durable delivery-state projection
  -> rollback that proves no further sends
```

## Design goal

A design that makes the later implementation narrow and verifiable:

```text
explicit delivery slots for progress / rich / final / media / artifact
final text is never marked delivered by a card/progress/media send
ACKs derive only from concrete approved send outcomes (or approved receipts)
retries and duplicates are idempotent; divergent replay fails closed
failures return stable codes, never raw platform payloads
rollback disables real sends without killing Gateway/runtime
live/canary enablement stays a separate, later approval
```

## Non-goals / non-approvals

This design gate approves none of:

```text
source implementation
real external Sachima ingress
real external delivery or delivery-URL/config changes
Gateway/Feishu/Lark/live/default-on behavior
production config writes
service restart or reload
Gateway-owned Temporal/Worker/service/subprocess lifecycle
platform adapter mutation
new credentials, secrets, tokens, or connection strings
Sachima runtime agent/acpx/npx execution
write-capable agent roles
bounded-recipient canary send or limited live pilot
production cluster or production traffic
```

## Current evidence boundary

| Evidence | What it proves | What it does not prove |
|---|---|---|
| Sachima adapter callback envelope | Adapter can format assistant delivery callbacks and local fallback records. | User-visible delivery, browser-visible delivery, real IM delivery, or ACK closure. |
| Phase B fake-send simulator | Local send semantics, surface separation, transcript safety, duplicate probes. | Real platform transport behavior or real recipient visibility. |
| PE-2A controlled runtime + fake delivery | Runtime operations can record ACKs derived from fake-send responses. | Real delivery control, public ingress, production runtime, or live behavior. |
| Phase32 injected delivery Activity | Delivery/ACK reconciliation can be modeled through injected surfaces. | Gateway adapter wiring or production delivery enablement. |
| P6 runtime attach | Runtime lifecycle attach can stay caller-owned/default-off. | Delivery implementation or live platform behavior. |

## Functional requirements for the implementation gate

### FR1 — Explicit delivery-slot lifecycle

Every surface must be initialized before send/ACK:

```text
slot_initialized -> send_pending -> send_accepted | send_failed | send_unknown -> ack_recorded | ack_rejected | ack_watch
```

Each slot carries only safe refs and stable metadata: `delivery_ref`, `surface`, `artifact_ref`, `attempt_id`, `idempotency_key`, `state_version`, `ack_ref`, and stable status/error codes.

### FR2 — Surface separation

`progress_card`, `rich_card`, `final_text`, `media`, and `artifact` are separate surfaces. A card/progress/media ACK must never imply final-text delivery. Final text needs its own slot and its own ACK evidence.

### FR3 — ACK source of truth

ACKs may only be derived from an approved send-path response or a separately approved callback/receipt event. ACKs must not be invented from initialized slots, planned delivery, local transcript rows, or optimistic UI rendering.

### FR4 — Retry and duplicate behavior

Retries reuse idempotency keys and slot state. Identical replay returns the stored projection. Divergent replay fails closed before another send. Unknown send outcome becomes WATCH, not silent success.

### FR5 — Failure semantics

Failures return stable codes only, such as:

```text
p7_delivery_disabled
p7_delivery_target_not_approved
p7_delivery_url_unconfigured
p7_send_rejected
p7_send_timeout
p7_ack_missing
p7_ack_target_mismatch
p7_ack_duplicate
p7_ack_unsafe_material
p7_rollback_active
```

Raw platform response bodies, callback payloads, card JSON, message IDs, chat IDs, user IDs, credentials, connection strings, signed URLs, raw exceptions, and tracebacks must never appear in durable state, evidence, logs, or user-visible cards.

### FR6 — Real-send approval and target binding

A future real-send canary must require a separate approval naming:

- delivery URL/config path class without secret values;
- platform/channel class;
- bounded recipient/group safe label;
- allowed surfaces;
- maximum send attempts;
- time budget;
- rollback command/class;
- evidence root;
- no-leak gates.

### FR7 — Rollback and disable

Rollback must disable new sends and leave query/recovery safe:

1. disable P7 delivery admission;
2. refuse new sends with `p7_delivery_disabled`;
3. preserve existing slot states and WATCH unknowns;
4. continue allowing sanitized query/export;
5. avoid Gateway restart unless separately approved.

### FR8 — Observability and evidence

Evidence must be sanitized and repeatable:

- counts by surface and status;
- safe delivery refs and ACK refs;
- retry/duplicate counts;
- stable error-code histogram;
- rollback proof;
- no-leak scan result;
- no raw delivery payloads or private IDs.

### FR9 — Protocol authority separation

Wire-level Sachima protocol decisions remain in the `sachima-protocols` repository. This repo may point to that authority and define local implementation constraints, but must not silently become the canonical protocol spec.

### FR10 — Review handoff

This design gate ends by requesting implementation approval separately. It must not open the door to live/default-on behavior by phrasing implementation readiness as production readiness.

## Design-complete criteria

This gate is design-complete when:

- the slot lifecycle, surface separation, ACK source-of-truth, retry/duplicate/idempotency, failure/WATCH, rollback, and no-leak rules are each specified unambiguously enough to implement and test against;
- the change stays docs/status only and asserts no implementation, live, or production approval;
- the later implementation, canary, and live rollout each carry a distinct, named approval.

## Later implementation approval phrase

If this design gate passes and implementation is desired, the next approval should be no broader than:

```text
approve_sachima_p7_real_delivery_ack_closure_implementation_default_off_bounded_adapter_path_no_live_default_on_no_public_ingress_no_production_config_write_no_gateway_restart_no_real_agent_execution_no_write_roles_no_unbounded_delivery
```

A later canary/live approval must still be separate and must name the exact bounded recipient, surfaces, attempt budget, rollback path, and evidence root.
