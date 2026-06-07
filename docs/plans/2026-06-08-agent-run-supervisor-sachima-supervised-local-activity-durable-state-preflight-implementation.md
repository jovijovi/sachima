# agent-run-supervisor × Sachima Supervised Local Activity Durable-State Preflight Implementation

> **For Hermes:** This implementation is local/offline only. It adds a fail-closed durable-state preflight gate before any future controlled local execution request can be considered. It does not approve or perform real local `exec`, persistent sessions, cancellation execution, real AGENT execution, controlled AI FLOW execution, live/default-on behavior, Gateway involvement, real external ingress, real IM/Feishu delivery, or production config writes.

## Approval

Status markers:

```text
marker_note: no live / no gateway / no real delivery / no real agent execution / no controlled AI FLOW execution
LOCAL_OFFLINE_ONLY
DURABLE_STATE_PREFLIGHT_ONLY
FAIL_CLOSED_PRECONDITION_GATE
SANITIZED_DURABLE_STATE_ONLY
NO_LIVE
NO_GATEWAY
NO_REAL_DELIVERY
NO_REAL_AGENT_EXECUTION
CONTROLLED_AI_FLOW_EXECUTION_NOT_APPROVED
```

User-approved next request, as recorded by `docs/roadmap/current-status.md` after PR #102:

```text
approve_agent_run_supervisor_sachima_supervised_local_activity_durable_state_preflight_implementation_no_live_no_gateway_no_real_delivery_no_real_agent_execution_no_controlled_ai_flow_execution
```

## Goal

Add the Sachima-owned durable-state preflight slice that validates whether a future local execution request has the required durable preconditions before any later execution phase can be requested.

This is a preflight gate, not execution. It records sanitized durable state for a caller-owned Activity and query path:

- exact approval token and default-off `enabled=True`;
- `exec_dry_run` mode only;
- role allowlist resolution;
- prior controlled dry-run evidence digest match;
- current lease id / epoch / holder and state-version check;
- idempotency fingerprint replay and conflict rejection;
- operator gate;
- budget bounds;
- sanitized query projection only.

## Scope

Allowed changed areas:

- `sachima_supervisor/activity_preflight.py` — durable-state preflight API and in-memory store.
- `sachima_supervisor/__init__.py` — public exports for the preflight API.
- `tests/sachima_supervisor/test_activity_durable_state_preflight.py` — contract, fail-closed, no-leak, and forbidden-surface tests.
- This implementation plan and manifest.
- Matching dev log.
- `docs/roadmap/current-status.md` status and tail update.

## Implemented Boundary

```text
implemented_surface: durable-state preflight only
implemented_mode: exec_dry_run only
state_store: in-memory local/offline store
query: sanitized read-only projection
supervisor_call: none
real_local_exec: not implemented
persistent_sessions: not implemented
cancel_or_rollback: not implemented
Gateway_or_delivery: not present
controlled_ai_flow_execution: not implemented
```

The preflight requires all of the following before writing state:

- `enabled=True`;
- exact approval token `approve_agent_run_supervisor_sachima_supervised_local_activity_durable_state_preflight_implementation_no_live_no_gateway_no_real_delivery_no_real_agent_execution_no_controlled_ai_flow_execution`;
- mode `exec_dry_run`;
- role key from `ROLE_KEY_ALLOWLIST`;
- safe claim-check refs only;
- prior dry-run evidence digest equal to `build_controlled_local_dry_run_evidence()["fixture_digest"]`;
- matching lease id, lease epoch, lease holder, and expected state version;
- exact `operator_gate is True`;
- exact integer budget fields within bounds;
- compatible idempotency fingerprint for repeats.

## Durable State Projection

The durable preflight state stores only:

```text
stable type/status/phase codes
caller-owned activity / transaction / operation refs
role key
mode
idempotency key
prior dry-run evidence digest
lease id / epoch / holder
state version
attempt index / count
artifact/evidence placeholders as sanitized null/count fields
caller verdict / error placeholders as sanitized null fields
retryable flag
view-model ref digest
```

It does not include:

```text
raw prompt/context/model output
platform private ids
card JSON
media bytes or paths
raw evidence paths
tool output
raw exception text or tracebacks
credentials or secret-shaped values
Gateway / delivery / webhook data
```

## Acceptance Gates

- [ ] GREEN focused tests: `scripts/run_tests.sh tests/sachima_supervisor/test_activity.py tests/sachima_supervisor/test_activity_controlled_dry_run_evidence.py tests/sachima_supervisor/test_activity_durable_state_preflight.py`.
- [ ] Compile check: `python -m compileall -q sachima_supervisor tests/sachima_supervisor`.
- [ ] `git diff --check`.
- [ ] Changed-file allowlist.
- [ ] Secret/no-leak/static forbidden-surface scan.
- [ ] CodeGraph sync/status in the feature worktree.
- [ ] Codex primary review from a fresh context. Because Codex temporarily substituted for Claude Code after Claude Code timeouts, this final review must be a separate review-only pass.
- [ ] GitHub PR CI green before merge.

## Role / Process Caveat

The default split is Claude Code as main programmer and Codex as primary reviewer. Claude Code timed out twice without a usable implementation artifact, so Codex temporarily acted as a substitute worker under the fallback rule. That authoring pass does not count as the independent review gate; a later fresh Codex blocker-only review remains required before commit / PR completion.

## Still Not Approved

```text
real_external_sachima_ingress
production_durable_runtime_code_implementation
real_local_exec
persistent_sessions
cancellation_execution
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

If this PR merges, the next request may discuss a later controlled local execution design/implementation gate, but only after fresh approval. This PR by itself only establishes a local/offline durable-state preflight and sanitized query path; it does not start a runtime or execute an AGENT.
