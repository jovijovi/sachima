# Sachima P7 Real Delivery / ACK Closure Runbook

## Status

```text
P7_REAL_DELIVERY_ACK_CLOSURE_CONTROLLER_IMPLEMENTATION
P7_DEFAULT_OFF
P7_BOUNDED_ADAPTER_SEAM_ONLY
P7_REAL_DELIVERY_NOT_ENABLED_BY_THIS_GATE
P7_LIVE_DEFAULT_ON_NOT_APPROVED
P7_PUBLIC_INGRESS_NOT_APPROVED
P7_PRODUCTION_CONFIG_WRITE_NOT_APPROVED
P7_GATEWAY_RESTART_NOT_APPROVED
P7_GATEWAY_OWNED_WORKER_LIFECYCLE_NOT_APPROVED
P7_BOUNDED_CANARY_SEND_REQUIRES_SEPARATE_APPROVAL
```

## Scope

`gateway/sachima_delivery_ack.py` adds a narrow, default-off delivery/ACK
closure controller. It is the controlled bridge between proven fake/local
delivery evidence and a later, separately approved bounded real-delivery canary.

```text
operator-approved delivery policy
-> caller-initialized delivery slots (one per surface)
-> exactly one caller-supplied adapter send seam per idempotency key
-> ACK recorded only from an accepted send response or approved receipt
-> sanitized delivery-state projection + query/export
-> rollback that refuses new sends without a Gateway restart
```

It does **not** perform real delivery, own Gateway/runtime/Worker lifecycle,
read or write production config, construct platform adapters, open network
listeners, create credentials, or run agent roles. The adapter send seam is
always supplied by the caller; this module never builds one.

## Surfaces and slot lifecycle

`progress_card`, `rich_card`, `final_text`, `media`, and `artifact` are
independent slots. A card/progress/media ACK never implies `final_text`
delivery — final text needs its own initialized slot and its own ACK evidence.

```text
initialized -> pending -> accepted | failed | unknown -> acked | watch | failed
```

## Enable (controlled, default-off)

The policy is inert unless an operator explicitly enables it with the exact
approval token. The token is a control constant (`SACHIMA_P7_DELIVERY_ENABLE_TOKEN`),
not a secret; the delivery URL is referenced only by a safe class label, never a
real URL or credential.

```python
from gateway.sachima_delivery_ack import (
    SACHIMA_P7_DELIVERY_ENABLE_TOKEN,
    SachimaP7DeliveryAckController,
    sachima_p7_delivery_policy,
)

policy = sachima_p7_delivery_policy(
    enabled=True,
    approval_token=SACHIMA_P7_DELIVERY_ENABLE_TOKEN,
    approved_targets=["safe_recipient_group_a"],   # bounded safe labels only
    allowed_surfaces=["final_text"],               # allowlist
    delivery_url_class="safe_delivery_url_class_a", # class label, no secret
    max_attempts=2,
)
controller = SachimaP7DeliveryAckController(policy=policy)
controller.initialize_slot(slot)                   # one initialized slot per surface
result = controller.deliver_slot(attempt=attempt, adapter=caller_supplied_seam)
```

Default off: `sachima_p7_delivery_policy(enabled=False)` (the default) yields an
inert policy; every `deliver_slot` returns `p7_delivery_disabled` and makes zero
adapter calls.

## ACK source of truth

ACKs derive only from an accepted adapter send response (carrying a safe
`receipt_ref`) or a separately approved receipt event. They are never invented
from initialized slots, planned delivery, transcript rows, or optimistic
rendering. An accepted send with no safe receipt becomes WATCH
(`p7_ack_missing`), not success.

## Retry / duplicate / WATCH

- Identical replay (same idempotency key + same target/surface/refs) returns the
  stored projection and makes no second adapter call.
- Divergent replay (same key, different content) fails closed with
  `p7_divergent_replay` before any adapter call.
- A distinct attempt against an already-acked slot fails closed with
  `p7_ack_duplicate`.
- Timeout / unknown / adapter exception become WATCH (`p7_send_timeout` /
  `p7_send_unknown`), never silent success.

## Stable error codes

```text
p7_delivery_disabled            p7_ack_target_mismatch
p7_delivery_url_unconfigured    p7_ack_missing
p7_delivery_target_not_approved p7_ack_duplicate
p7_delivery_surface_not_approved p7_ack_unsafe_material
p7_send_rejected                p7_divergent_replay
p7_send_timeout                 p7_max_attempts_exceeded
p7_send_unknown                 p7_rollback_active
p7_invalid_request / p7_invalid_slot / p7_invalid_policy
```

Raw platform payloads, card JSON, media bytes/paths, callback payloads,
chat/user/message ids, credentials, connection strings, signed URLs, raw
exceptions, tracebacks, and private filesystem paths never appear in any
returned projection, ACK event, or export. Hostile material is rejected with
`p7_ack_unsafe_material` (or `p7_invalid_slot`) and scrubbed.
`scan_sachima_p7_no_leak(projection)` reports any forbidden marker; an internal
guard refuses to emit a projection that fails the scan.

## Rollback / disable

```text
controller.rollback()
1. disables P7 delivery admission;
2. refuses new sends with p7_rollback_active;
3. preserves existing slot states and WATCH unknowns;
4. keeps sanitized query/export available (controller.query());
5. requires no Gateway restart.
```

## Verification

Pure local/offline focused tests (fake adapter seam only):

```bash
source .venv/bin/activate 2>/dev/null || source venv/bin/activate 2>/dev/null || source "$HOME/.hermes/hermes-agent/venv/bin/activate"
scripts/run_tests.sh tests/gateway/test_sachima_delivery_ack.py tests/gateway/test_sachima_delivery_ack_no_leak.py -q
```

## Non-approvals

This implementation gate does **not** approve, and a bounded canary / limited
live pilot must each obtain a separate approval naming the exact recipient,
surfaces, attempt budget, rollback path, and evidence root before any of:

```text
real external delivery or delivery URL/config changes
live / default-on / public-ingress behavior
production config writes or service restart/reload
Gateway-owned Temporal/Worker/service/subprocess lifecycle
platform adapter mutation
real Sachima runtime agent/acpx/npx execution
write-capable agent roles
bounded-recipient canary send or production traffic
```
