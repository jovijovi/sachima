# agent-run-supervisor × Sachima Supervised Local Activity Implementation

> **For Hermes:** This implementation is local/offline only. It implements the first `exec_dry_run` Activity slice with an injected supervisor callable. It does not approve live behavior, Gateway involvement, real external ingress, real IM/Feishu delivery, production config writes, Gateway restart/reload, automatic replies, worker auto-routing, real AGENT execution, or controlled AI FLOW execution.

## Approval

Status markers:

```text
marker_note: no live / no gateway / no real delivery / no real agent execution
LOCAL_OFFLINE_ONLY
EXEC_DRY_RUN_ONLY
INJECTED_SUPERVISOR_ONLY
NO_LIVE
NO_GATEWAY
NO_REAL_DELIVERY
NO_REAL_AGENT_EXECUTION
CONTROLLED_AI_FLOW_EXECUTION_NOT_APPROVED
```

User approval received in chat:

```text
approve_agent_run_supervisor_sachima_supervised_local_activity_implementation_no_live_no_gateway_no_real_delivery
```

## Goal

Add a Sachima-owned Activity/controller wrapper around the already-merged `sachima_supervisor.local_offline` seam so FlowWeaver/Sachima can validate local Activity requests, resolve allowlisted roles, call an injected supervisor dry-run path, store sanitized durable state, and query that state without introducing Gateway/live/real-delivery surfaces.

## Scope

Allowed changed areas:

- `sachima_supervisor/activity.py` — first-slice Activity API and in-memory state store.
- `sachima_supervisor/__init__.py` — public exports for the Activity API.
- `tests/sachima_supervisor/test_activity.py` — RED/GREEN tests for Activity behavior and boundaries.
- roadmap / plan / manifest / dev-log docs for status and evidence.

## Implemented Boundary

The first slice is intentionally narrower than the full design packet:

```text
implemented_mode: exec_dry_run only
supervisor_call: injected callable only
real_local_exec: not implemented
session_modes: not implemented
cancel_or_rollback: not implemented
Gateway_or_delivery: not present
```

The Activity requires:

- `enabled=True`;
- exact approval token `approve_agent_run_supervisor_sachima_supervised_local_activity_implementation_no_live_no_gateway_no_real_delivery`;
- `dry_run_first=True`;
- first-slice mode `exec_dry_run`;
- a role key from the local allowlist;
- claim-check/workspace refs without platform-private, secret-shaped, card, media, or raw path material;
- an injected supervisor callable, so no default runtime invocation can happen by accident.

## Safety Invariants

Durable Activity state and query results include only:

```text
stable status/error codes
caller-owned activity / transaction / operation refs
role key
mode / phase
artifact ref count
evidence ref / digest
caller verdict code
view-model ref
retryable flag
```

They do not include:

```text
raw prompt/context/model output
platform private ids
card JSON
media bytes or paths
raw evidence paths
tool output
raw exception text or tracebacks
credentials or secret-shaped values
```

The Activity treats the injected supervisor as a boundary too: malformed or unsafe lower-level outcome fields collapse to `activity_supervisor_failed` rather than being persisted.

## Acceptance Gates

- [ ] RED test evidence for missing `sachima_supervisor.activity` module.
- [ ] GREEN focused tests: `python3 -m pytest tests/sachima_supervisor/test_activity.py tests/sachima_supervisor/test_local_offline.py -q`.
- [ ] Compile check: `python3 -m py_compile sachima_supervisor/*.py tests/sachima_supervisor/test_activity.py tests/sachima_supervisor/test_local_offline.py`.
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
real_agent_execution
controlled_ai_flow_execution
```

## Next Decision After This PR

If this PR merges, the next request should remain local/offline and weaker than controlled AI FLOW: controlled local Activity evidence/fixtures around role mapping, idempotency, sanitized durable state, and injected dry-run supervisor outcomes. Real local `exec`, persistent sessions, cancellation, live Gateway behavior, public ingress, and real delivery all remain separate approvals.
