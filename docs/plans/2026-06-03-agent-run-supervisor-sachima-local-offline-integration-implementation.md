# agent-run-supervisor × Sachima Local/Offline Integration Implementation

> **For Hermes:** This implementation is local/offline only. It does not approve live behavior, Gateway involvement, real external ingress, real delivery, production config writes, Gateway restart/reload, automatic replies, worker auto-routing, or controlled AI FLOW execution.

## Approval

User approval received in chat:

```text
approve_agent_run_supervisor_sachima_local_offline_integration_implementation_no_live_no_gateway_no_real_delivery
```

## Goal

Add a default-off Sachima-owned local/offline caller seam for `agent-run-supervisor` that can:

1. validate a caller-owned sanitized request;
2. build an `agent_run_supervisor.caller.CallerInvocationSpec` through the public caller boundary;
3. call `invoke_caller` lazily and optionally through injected fakes for tests;
4. map `CallerResult` into a sanitized caller-owned offline view model;
5. write sanitized local evidence JSON when requested.

The concrete caller remains a local Sachima/FlowWeaver/Hermes controller or Activity wrapper. The Gateway is not the caller.

## Scope

Allowed changed areas:

- `sachima_supervisor/` — new non-Gateway local/offline seam package.
- `tests/sachima_supervisor/` — TDD tests for gates, mapping, evidence, and forbidden surfaces.
- `pyproject.toml` — package inclusion for the new seam.
- roadmap / plan / dev-log docs for post-merge status and evidence.

## Implemented Boundary

The new seam is default-off and requires the exact approval token plus `enabled=True`. It accepts only:

```text
exec_dry_run
exec
session_create
session_send
session_status
session_close
```

Cancellation and rollback remain future concerns. The first safe probe is still `exec_dry_run` / config preview.

## Safety Invariants

The returned view model and evidence file do not include:

```text
raw prompts
platform ids
card JSON
media bytes or paths
tool output
tokens / credentials / secrets / raw signatures
raw acpx stdout
raw exceptions / tracebacks
```

The seam imports `agent_run_supervisor` lazily only inside the invocation path. Importing `sachima_supervisor.local_offline` does not require the external library to be installed.

## Acceptance Gates

- [ ] RED/GREEN tests for `tests/sachima_supervisor/test_local_offline.py`.
- [ ] `python3 -m py_compile sachima_supervisor/*.py tests/sachima_supervisor/test_local_offline.py`.
- [ ] Focused Sachima tests around the new seam and existing local/fake surfaces.
- [ ] `git diff --check`.
- [ ] Changed-file allowlist.
- [ ] Secret/no-leak/static forbidden-surface scan.
- [ ] Codex primary review after implementation candidate is ready.
- [ ] PR CI green before merge.

## Still Not Approved

```text
real_external_sachima_ingress
real_external_delivery
production_delivery_control
production_agent_tool_execution_expansion
production_config_write
gateway_restart_or_reload
platform_adapter_mutation
gateway_owned_temporal_lifecycle
real_send_api_or_external_im_call
external_temporal_service_or_worker_startup
live_or_default_on_behavior
public_webhook_exposure
automatic_replies
worker_auto_routing
agent_to_agent_auto_routing
@all_fanout
trusted_markdown_html_rendering
```

## Next Decision After This PR

If this PR merges, the next higher-risk request would still need a separate design/approval packet before any controlled AI FLOW execution or live/Gateway/real-delivery surface is attempted.
