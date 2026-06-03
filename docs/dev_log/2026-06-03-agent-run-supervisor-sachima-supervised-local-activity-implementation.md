# Dev Log — agent-run-supervisor × Sachima Supervised Local Activity Implementation

Date: 2026-06-03
Branch: `feat/supervised-local-activity`
Base: `release/sachima` @ `675853fd2db2b8f9df781ea46803fd0747ea78cb`
Approval: `approve_agent_run_supervisor_sachima_supervised_local_activity_implementation_no_live_no_gateway_no_real_delivery`

## Scope

Implemented the first local/offline Activity wrapper slice around the existing `sachima_supervisor.local_offline` seam:

- `exec_dry_run` only;
- injected supervisor callable only;
- role-key allowlist;
- claim-check/workspace ref validation;
- sanitized durable state and query result mapping;
- idempotency replay/conflict handling;
- no Gateway, no live, no real delivery, no real AGENT execution, no controlled AI FLOW execution.

## TDD Evidence

RED evidence before production code:

```text
python3 -m pytest tests/sachima_supervisor/test_activity.py -q
22 failed — ModuleNotFoundError: No module named 'sachima_supervisor.activity'
```

Focused GREEN after implementation and hardening:

```text
python3 -m pytest tests/sachima_supervisor/test_activity.py tests/sachima_supervisor/test_local_offline.py -q
66 passed in 0.43s
```

Compile / diff hygiene:

```text
python3 -m py_compile sachima_supervisor/*.py tests/sachima_supervisor/test_activity.py tests/sachima_supervisor/test_local_offline.py
# exit 0

git diff --check
# exit 0
```

## Implementation Notes

`SupervisedLocalActivityRequest` is default-off. `start_supervised_local_activity` requires the exact Activity approval token and an injected supervisor callable. The Activity builds a lower-level `LocalOfflineSupervisorRequest` with the existing local-offline implementation token, `role_file` from an allowlist, and claim-check refs only. It leaves raw `prompt` and `context` as `None` for this first slice.

`ActivityStateStore` is an in-memory durable-state stand-in for this local/offline slice. It records sanitized state by `activity_id` and idempotency key. Reusing the same key with an identical request replays the stored result without a second supervisor call. Reusing it for a different request fails closed with `activity_idempotency_conflict`.

Supervisor outputs are treated as another trust boundary: unsafe/malformed status, verdict, evidence ref, digest, or artifact count collapses to `activity_supervisor_failed` instead of persisting raw data.

## Boundary Checks Added

- default-off gate: `activity_disabled`;
- exact approval gate: `activity_approval_mismatch`;
- injected-supervisor requirement: `activity_supervisor_injection_required`;
- dry-run-first requirement: `activity_dry_run_required`;
- first-slice mode allowlist: `activity_unsupported_mode`;
- role allowlist: `activity_unknown_role`;
- platform/private/secret/card/media material rejection: `activity_unsafe_material`;
- idempotency conflict: `activity_idempotency_conflict`;
- lower supervisor failure or unsafe outcome: `activity_supervisor_failed`.

## Non-Approvals Preserved

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

## Review Evidence

Codex primary review:

```text
VERDICT: PASS
BLOCKERS:
- None
```

Reviewer notes: inspected git status/diffs/tracked changes/all listed untracked files; confirmed focused pytest, compile, and diff-check evidence.

## Pending Gates

- GitHub PR CI and mergeability after PR creation.
