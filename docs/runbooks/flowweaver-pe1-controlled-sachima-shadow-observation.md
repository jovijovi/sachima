# FlowWeaver PE-1 Controlled Sachima Shadow Observation Runbook

## Purpose

PE-1 narrows the existing FlowWeaver production-shadow sidecar to a default-off, Sachima-only, observation-only production-shadow gate.

It does not authorize default-on production, production config writes, Gateway restart/reload, platform adapter mutation, production delivery control, or production agent/tool execution.

## Flag Shape

Read-only config shape:

```yaml
flowweaver:
  production_shadow_observation:
    enabled: false
    platform_allowlist: []
    timeout_ms: 250
```

PE-1 starts are allowed only when the operator has separately approved operational config and the config is exactly:

```yaml
flowweaver:
  production_shadow_observation:
    enabled: true
    platform_allowlist: [sachima]
    timeout_ms: 250
```

Any non-Sachima platform, empty allowlist, invalid allowlist, duplicated allowlist, or allowlist containing extra platforms produces no runtime start.

## Runtime Ownership

Gateway must use only an injected runtime control surface. Gateway must not create or own Temporal clients, Workers, namespaces, task queues, services, daemons, Docker processes, sockets, subprocesses, or external runtime lifecycle.

Allowed runtime operations remain bounded to:

```text
start_transaction
query_transaction
```

Forbidden operations include delivery ACK reconciliation, send/edit/render/callback behavior, production agent/tool execution, config writes, and service lifecycle operations.

## Observation Envelope

PE-1 may export only sanitized labels, counters, refs, digests, statuses, and stable error codes.

Forbidden everywhere:

- raw prompt or message text;
- raw tool output;
- card JSON;
- media path or bytes;
- platform/chat/user/message identifiers;
- callback payloads;
- credentials, tokens, passwords, API keys, connection strings;
- raw exception text.

## Delivery Safety

The Gateway hook runs as a sidecar after response normalization and must not mutate:

- `response`;
- `delivery_state`;
- `already_sent`;
- `should_skip_final_text()` behavior;
- adapter send/edit/render/callback behavior;
- ACK state.

Observation failure, unsafe runtime output, missing runtime surface, timeout, or platform mismatch must fail closed without changing user-visible delivery.

## Rollback

Any one of these stops new observation starts:

1. Set `flowweaver.production_shadow_observation.enabled=false`.
2. Remove `sachima` from the allowlist.
3. Add any extra platform to the PE-1 allowlist, which fails closed for PE-1 starts.
4. Remove the injected runtime control surface.
5. Stop the externally managed runtime or Temporal Worker if one was separately approved.
6. Revert the PE-1 PR.

Rollback must not require raw payload inspection and must not mutate platform adapters.

## Operational Approval Boundary

This runbook is not itself an approval to write production config or restart Gateway. Those require separate explicit approvals:

```text
approve_production_config_write
approve_gateway_restart_or_reload
approve_sachima_platform_allowlist
approve_external_runtime_control_surface
approve_external_temporal_service_or_worker_if_used
```

## Verification

Before merging PE-1 code, run:

```bash
python -m pytest -q tests/gateway/test_flowweaver_pe1_controlled_sachima_shadow_observation.py
python -m pytest -q tests/gateway/test_flowweaver_production_shadow_observation.py tests/gateway/test_flowweaver_ai_flow_pilot.py
python -m pytest -o addopts= -n 4 -q tests/integration/test_flowweaver_phase21_production_shadow_observation.py tests/integration/test_flowweaver_phase33_ai_flow_pilot.py
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase5*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```
