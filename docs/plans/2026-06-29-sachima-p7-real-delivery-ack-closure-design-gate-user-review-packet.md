# P7 Real Delivery / ACK Closure — Design Gate (User review packet)

Date: 2026-06-29
Owner: Architect
Status: Docs-only design packet. GitHub is the live authority for PR, head SHA, CI, and merge state.

## What this PR does

Creates the architect-owned P7 design gate for future real outbound delivery and ACK closure. It fixes:

- delivery-slot lifecycle for progress / rich / final / media / artifact surfaces;
- ACK source-of-truth rules;
- final-text independence from card/progress/media sends;
- retry, duplicate, timeout, and WATCH behavior;
- rollback/disable semantics;
- no-leak evidence rules;
- the separate approvals the implementation and any canary/live rollout must each obtain.

## What this PR does not do

```text
no source implementation
no real external ingress
no real external delivery
no configured delivery URL change
no Gateway/Feishu/Lark/live/default-on behavior
no production config write
no service restart/reload
no platform adapter mutation
no runtime/Worker/service/subprocess startup
no Sachima runtime acpx/npx/agent execution
no write-capable agent role
no bounded-recipient canary send
no production traffic
```

## Why this is the right next step

P6 gives Sachima controlled AI FLOW / runtime foundations; PE-2A and Phase32 give fake/injected delivery and ACK evidence. The remaining gap is not another fake proof — it is a design that fixes, before code, when a real platform-visible send is allowed, how its ACK becomes durable truth, and how rollback prevents accidental repeat sends.

Without this gate, an implementation could overclaim `2xx` callbacks, fake-send rows, or card ACKs as final user-visible delivery — a costly bug class. The design freezes those semantics first.

## Recommended later implementation scope

If this PR passes, the next implementation should be a narrow, default-off controller, likely centered on:

```text
gateway/sachima_delivery_ack.py
tests/gateway/test_sachima_delivery_ack.py
tests/gateway/test_sachima_delivery_ack_no_leak.py
```

The first implementation should use a caller-supplied fake adapter seam and prove policy/slot/ACK/no-leak behavior without real sends. A real bounded-recipient canary remains a separate approval after the implementation gates pass.

## Exact future implementation approval phrase

Use no broader than:

```text
approve_sachima_p7_real_delivery_ack_closure_implementation_default_off_bounded_adapter_path_no_live_default_on_no_public_ingress_no_production_config_write_no_gateway_restart_no_real_agent_execution_no_write_roles_no_unbounded_delivery
```

## Future canary approval must be separate

A real canary send must later name:

- exact bounded recipient/group safe label;
- allowed delivery surfaces;
- send-attempt budget;
- delivery URL/config class without values;
- rollback path;
- evidence root;
- no-leak scanner scope.

## What a reviewer should check

- Final text is a separate slot from card/progress/media, so no card ACK implies final delivery (FR2).
- ACKs derive only from concrete approved send outcomes or approved receipts — never from initialized slots or local transcript rows (FR3).
- Unknown/timeout outcomes become WATCH, never optimistic success; divergent duplicate replay fails closed (FR4).
- Rollback disables new sends without requiring a Gateway restart (FR7).
- No raw platform payloads, private IDs, or secrets can reach any projection, log, or evidence surface (FR5, FR8).
- The packet claims no implementation, live, or production approval, and keeps implementation / canary / live as separate, named gates (FR10).
