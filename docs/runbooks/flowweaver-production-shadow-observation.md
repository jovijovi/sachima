# FlowWeaver Production-Shadow Observation Runbook

## Purpose

Phase 21 adds a default-off, observation-only Gateway sidecar that can mirror sanitized real-turn state into FlowWeaver Temporal runtime state through start/query operations.

It does not enable delivery control, Temporal-backed agent execution, production Gateway restarts, config writes, platform adapter mutation, or send/edit/render/callback behavior.

## Strongest Phase 21 Verdict

```text
ready_for_separate_delivery_or_agent_execution_design
```

That verdict means a future phase may design delivery or agent-execution integration. It does not mean those behaviors are enabled.

## Enablement Prerequisites

Operators need all of these before requesting live enablement:

1. An externally managed FlowWeaver runtime control surface.
2. An externally managed Temporal service/Worker, if the runtime surface is Temporal-backed.
3. A narrow platform allowlist.
4. Explicit approval for any Gateway restart/reload needed to apply configuration.
5. Explicit approval for any production config write.

Gateway itself must not create the Temporal client, Worker, namespace, task queue, service, daemon, Docker process, socket listener, or subprocess lifecycle.

## Flag Shape

Read-only flag shape:

```yaml
flowweaver:
  production_shadow_observation:
    enabled: false
    platform_allowlist: []
    timeout_ms: 250
```

Default is disabled. An enabled flag without an allowlisted platform still produces no observation starts.

## Safe Operation

When enabled and allowlisted, Gateway reduces a completed turn to safe observation labels and counters only:

- safe hashed session/turn labels;
- safe claim-check references;
- final/rich/media surface counts;
- start/query runtime operation counts;
- stable status/error codes.

Forbidden everywhere:

- raw prompt or message text;
- raw tool output;
- card JSON;
- media path or bytes;
- platform/chat/user/message identifiers;
- callback payloads;
- credentials, tokens, passwords, API keys, or connection strings;
- raw exception text.

## Disable / Rollback

Any one of these stops new observation starts:

1. Set `flowweaver.production_shadow_observation.enabled` to `false`.
2. Remove the current platform from `platform_allowlist`.
3. Remove the injected runtime control surface.

Existing safe runtime snapshots may still be queried by operator tooling, but Gateway must not invent delivery ACKs during rollback.

## Known Stable Codes

- `disabled`
- `platform_not_allowlisted`
- `no_visible_surface`
- `runtime_control_surface_required`
- `runtime_start_failed`
- `runtime_query_failed`
- `unsafe_runtime_output`
- `timeout`
- `invalid_shadow_policy`
- `invalid_gateway_turn`

## Non-Goals

- No delivery control.
- No Temporal-backed agent/tool execution.
- No production ACK reconciliation from real sends.
- No platform-specific rendering changes.
- No Gateway-owned Temporal lifecycle.
- No production config write or Gateway restart without a separate approval.
