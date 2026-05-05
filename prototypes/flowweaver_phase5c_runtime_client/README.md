# FlowWeaver Phase 5C Runtime Client / MCP Tool Prototype

Prototype-only runtime client for the local FlowWeaver Temporal POC.

Boundaries:

- Default-off: no production Hermes tool registration.
- Local stdio MCP wrapper only, configured manually by an operator in a later step.
- Requires an explicit local Temporal endpoint such as `localhost:7233`; there is no implicit default.
- Does not start Gateway, Docker, workers, daemons, or a Temporal service.
- Tool-visible results pass through a Phase 5C whitelist sanitizer before leaving the adapter.

Phase 5C exposes one MCP tool surface: `flowweaver_runtime`, with a closed-set `operation` field.

## Operations

`flowweaver_runtime` accepts one of these operations:

- `start_transaction`
- `query_snapshot`
- `record_delivery_ack`
- `approve_intent`
- `reject_intent`
- `cancel_transaction`
- `resume_after_user_input`

The adapter accepts MCP-style dictionaries and converts them to Phase 5B validated dataclasses before calling Temporal Updates or Queries. Unknown operations are rejected; state-changing operations use explicit method calls, not dynamic method dispatch.

## Local MCP wrapper

The wrapper is import-safe and does not auto-run. To start it manually in a local development shell:

```bash
python -m flowweaver_runtime_client.mcp_server --temporal-address localhost:7233
```

That command runs stdio transport only. Operators must configure any agent-side MCP entry explicitly in a later step; this prototype does not edit runtime config.
