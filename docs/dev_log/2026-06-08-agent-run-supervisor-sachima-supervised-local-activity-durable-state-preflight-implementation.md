# Dev Log — agent-run-supervisor × Sachima Supervised Local Activity Durable-State Preflight Implementation

Date: 2026-06-08
Branch: `feature/ars-durable-state-preflight`
Base: `release/sachima` @ `db84704da896eb7b42ee66fc0ef60d9ba0025f6a`
Approval: `approve_agent_run_supervisor_sachima_supervised_local_activity_durable_state_preflight_implementation_no_live_no_gateway_no_real_delivery_no_real_agent_execution_no_controlled_ai_flow_execution`

## Scope

Implemented a local/offline durable-state preflight gate after the supervised local Activity controlled dry-run evidence phase:

- `exec_dry_run` preflight only;
- exact approval token and default-off gate;
- prior controlled dry-run evidence digest check;
- role allowlist;
- claim-check/workspace ref validation;
- lease id / epoch / holder validation;
- state-version TOCTOU validation;
- idempotency replay/conflict handling;
- operator gate;
- budget bounds;
- sanitized durable state and query projection;
- no Gateway, no live, no real delivery, no real AGENT execution, no controlled AI FLOW execution.

## Process Note

Default AGENT split was preserved as the target workflow: Hermes controls/verifies, Claude Code is main programmer, Codex is primary reviewer. Claude Code timed out twice without a usable implementation artifact. Codex temporarily acted as a substitute worker to produce the implementation candidate, which is a role deviation under the documented fallback rule. That authoring pass is not counted as independent review; a separate fresh Codex review-only pass remains required before PR completion.

## Implementation Notes

`DurableStatePreflightRequest` is default-off. `run_durable_state_preflight` requires the exact durable-state preflight approval token, `enabled=True`, `exec_dry_run`, an allowlisted Activity role key, safe refs, prior dry-run evidence digest, a matching lease, matching state version, exact operator gate, and integer budget bounds.

`DurableStatePreflightStore` is an in-memory durable-state stand-in for this local/offline slice. It records sanitized state by `activity_id` and idempotency key. Reusing the same key with an identical request replays stored state. Reusing it for a different fingerprint fails closed with `activity_idempotency_conflict`.

`query_durable_state_preflight` returns only the sanitized projection already stored by the preflight; it does not call the supervisor, rehydrate raw material, or touch runtime/Gateway surfaces.

## Boundary Checks Added

- default-off gate: `activity_disabled`;
- exact approval gate: `activity_approval_mismatch`;
- mode gate: `activity_unsupported_mode`;
- role allowlist: `activity_unknown_role`;
- platform/private/secret/card/media/raw material rejection: `activity_unsafe_material`;
- prior evidence digest mismatch: `activity_precondition_unmet`;
- operator gate mismatch: `activity_precondition_unmet`;
- budget bounds mismatch: `activity_budget_exceeded`;
- missing/mismatched lease: `activity_lease_lost`;
- stale lease epoch: `activity_stale_state`;
- expected state-version mismatch: `activity_toctou_conflict`;
- idempotency conflict: `activity_idempotency_conflict`;
- missing query target: `activity_not_found`.

## Final Local Verification Evidence

After Codex blocker fixes:

```text
scripts/run_tests.sh tests/sachima_supervisor
117 tests passed, 0 failed

python -m compileall -q sachima_supervisor tests/sachima_supervisor
# exit 0

changed-file allowlist
# 7 expected files only

manifest boolean gate
# implementation_approved=true; local_execution/live/gateway/real_delivery/real_agent_execution/controlled_ai_flow_execution=false

secret-shaped added-line scan
# clean

forbidden source/runtime surface scan for sachima_supervisor/activity_preflight.py
# clean

git diff --check
# exit 0

git diff --cached --check
# exit 0

codegraph sync && codegraph status
# exit 0; index up to date
```

## Review Evidence

Codex read-only sandbox attempt was blocked by the known environment issue:

```text
bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted
```

Codex was rerun in the same isolated worktree with `danger-full-access -a never`, strict review-only instructions, and before/after checksums.

Initial Codex review found two blockers:

```text
1. public store/query could expose malicious resident state
2. None lease id/holder could pass when request and stored lease matched
```

First blocker-only re-review found one same-surface blocker:

```text
get_idempotent() returned resident fingerprint without validating fingerprint shape
```

After the final narrow fix, Codex blocker-only re-review returned:

```text
VERDICT: PASS
BLOCKERS:
- None
```

Checksum verification confirmed the final review did not modify files.

## Non-Approvals Preserved

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

## Pending Gates

- GitHub PR creation, CI, and mergeability.
