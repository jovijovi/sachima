# P7 Real Delivery / ACK Closure — Design Gate (Technical solution)

Date: 2026-06-29
Owner: Architect
Status: **Docs-only, no-code technical solution.** No source implementation, Gateway/Feishu/Lark/live behavior, production config, service restart, real delivery, public ingress, or real agent execution is approved here.

## 0. Architecture verdict

The later implementation should be a **thin default-off delivery control layer over existing delivery-slot and runtime ACK semantics**, not a new Gateway lifecycle owner.

The core decision:

```text
P7DeliveryAckController (future)
  validates an operator-approved delivery policy
  consumes initialized delivery slots and sanitized artifact refs
  calls exactly one approved adapter send seam when enabled
  records ACKs only from concrete send outcomes or approved receipts
  stores sanitized delivery state projections
  never starts Gateway/runtime/Worker/service and never creates credentials/config
```

P7 implementation is not a shortcut to live rollout. It is the controlled bridge between proven fake/local delivery and a separately approved bounded real delivery canary.

## 1. Proposed future source surface

Allowed future source surface, if separately approved:

```text
gateway/sachima_delivery_ack.py                    # new narrow controller, default-off
tests/gateway/test_sachima_delivery_ack.py         # pure unit tests with fake adapter seam
tests/gateway/test_sachima_delivery_ack_no_leak.py # hostile payload/no-leak tests
docs/runbooks/sachima-real-delivery-ack-closure.md # operator runbook after implementation approval
```

Possible existing surfaces to reuse:

- `gateway/delivery.py` for generic routing constraints and adapter result classification patterns.
- `gateway/flowweaver_delivery_activity.py` for initialized-slot and injected ACK reconciliation semantics.
- `gateway/flowweaver_pe2_controlled_runtime_delivery_bridge.py` for fake-send-derived ACK ordering and no-leak patterns.
- `docs/sachima-channel.md` for current callback-envelope and delivery URL naming.

Forbidden future source surface unless separately approved:

```text
production config files
Gateway service startup/restart code
Feishu/Lark platform adapters for this gate
Temporal Worker/service lifecycle
pyproject.toml or lockfile dependency changes
new real-agent role configs
protocol authority files outside this repo
```

## 2. Future data model, design labels only

A later implementation may add sanitized local shapes equivalent to:

```text
P7DeliverySlot
  delivery_ref: runtime_delivery_N
  surface: progress_card | rich_card | final_text | media | artifact
  artifact_ref: runtime_artifact_N | null
  required: bool
  state: initialized | pending | accepted | failed | unknown | acked | watch
  state_version: int

P7DeliveryAttempt
  attempt_id: runtime_delivery_attempt_N
  delivery_ref: runtime_delivery_N
  idempotency_key: digest ref
  target_ref: approved safe label
  started_at_ref: coarse timestamp/ref
  result_status: accepted | failed | timeout | unknown
  error_code: stable code or null

P7AckEvent
  ack_ref: runtime_delivery_ack_N
  delivery_ref: runtime_delivery_N
  surface: surface label
  status: sent | failed | acknowledged | unknown
  source: send_response | approved_receipt
  duplicate: bool
  state_version: int
```

No field may contain raw text, raw card JSON, raw media bytes/paths, callback payloads, chat/user/message IDs, recipient IDs, credentials, connection strings, signed URLs, raw exception text, stdout/stderr, or private filesystem paths.

## 3. Future delivery algorithm

Future `deliver_slot(slot, policy, adapter_surface)` must:

1. validate `enabled=True` and exact approval token;
2. validate bounded target and surface allowlist;
3. reject slots not in `initialized`/retry-safe states;
4. construct a sanitized send request from safe refs only;
5. call the caller-supplied adapter surface exactly once for the idempotency key;
6. classify response as `accepted`, `failed`, `timeout`, or `unknown`;
7. record ACK only from accepted send response or approved receipt;
8. return sanitized state projection.

It must not read or write production config, construct platform adapters, start/restart Gateway, create network listeners, start Workers, spawn subprocesses, run agent roles, or mutate delivery protocol authority.

## 4. ACK reconciliation rules

| Case | Required behavior |
|---|---|
| Accepted final text send | Record final-text ACK for that slot only. |
| Accepted rich/progress card send | Record card ACK; do not mark final text delivered. |
| Accepted media send | Record media ACK with safe artifact ref only. |
| Failed send | Stable failure code; no sent ACK. |
| Timeout/unknown | WATCH state; no optimistic success. |
| Duplicate identical replay | Return stored projection, no second send. |
| Duplicate divergent replay | Fail closed before adapter call. |
| ACK for uninitialized slot | Reject with `p7_ack_target_mismatch`. |
| Raw payload in response | Reject/sanitize to `p7_ack_unsafe_material`. |

## 5. Rollback / disable design

Future rollback controls:

```text
1. Disable P7 delivery admission.
2. Refuse new sends with p7_delivery_disabled.
3. Preserve existing delivery state for query/export.
4. Mark unknown outcomes WATCH until operator resolution.
5. Keep runtime/AI FLOW query paths available if separately safe.
6. Do not restart Gateway or stop runtime/Worker unless separate ops approval names that action.
```

Rollback proof should run without real sends in the first implementation gate, then with a bounded approved canary only under a later live approval.

## 6. No-leak strategy

Future tests and docs gates must scan:

1. delivery-state JSON/projections;
2. ACK event projections;
3. fake/real adapter response classifications;
4. logs/dev logs/user review packets;
5. PR body and evidence summaries.

Forbidden markers include:

```text
raw_prompt
raw platform payload
card_json
media_path
media_bytes
callback_payload
chat_id
user_id
message_id
credential
token
secret
bearer
Traceback
[PRIVATE_HOME_PATH]
[PRIVATE_TEMP_PATH]
signed URL query secrets
```

Any hit is a critical blocker unless it appears only as a quoted forbidden marker in docs/checklists.

## 7. Boundary discipline for future implementation

A later implementation PR should define its own concrete verification commands, scripts, or CI checks from the implementation plan. This design gate only fixes the boundary intent:

- keep the first implementation narrow, default-off, and limited to the delivery/ACK closure surface;
- require an explicit changed-file scope for implementation, tests, runbook/status docs, and no unrelated runtime/config surfaces;
- reject accidental service lifecycle changes, Gateway restart/reload behavior, public ingress, production config writes, direct platform-send shortcuts, or unbounded delivery paths unless separately approved;
- treat any static boundary scan as an implementation-time guardrail, not as the design itself.

The current docs-only design PR remains stricter: docs/status only, no source/config/runtime changes.

## 8. Later TDD task plan

A later implementation PR should be TDD-first:

1. RED: disabled policy makes zero adapter calls.
2. GREEN: policy gate and stable disabled projection.
3. RED: unapproved target/surface fails before adapter call.
4. GREEN: bounded target/surface validator.
5. RED: final text and rich/progress cards are independent slots.
6. GREEN: slot state model and ACK projection.
7. RED: accepted send records ACK only for initialized slot.
8. GREEN: one-slot delivery path through caller-supplied fake adapter seam.
9. RED: duplicate identical replay is idempotent; divergent replay fails closed.
10. GREEN: idempotency/fingerprint store.
11. RED: timeout/unknown outcome becomes WATCH and never success.
12. GREEN: stable failure/WATCH projections.
13. RED/GREEN: no-leak canary over responses, logs, projections, docs evidence.
14. Focused suite + static forbidden-surface scan + head-bound PR gate.

## 9. Review handoff

This docs-only gate is successful only if:

- current docs do not imply implementation/live approval;
- `current-status.md` remains a lean phase/task dashboard;
- no source/config/runtime files are modified;
- future approval phrases separate design, implementation, canary, live rollout, config write, restart, real agent execution, and production traffic.
