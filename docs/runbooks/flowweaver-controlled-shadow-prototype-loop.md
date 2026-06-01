# FlowWeaver Controlled Shadow Prototype Loop Runbook

## Status

This runbook documents the Phase 10 controlled-shadow **prototype loop** boundary. It is not a production activation guide.

Current approved scope:

```text
Phase 10 implementation = prototype-only bounded fixture loop
Default state = off
Production side effects = none
Runtime lifecycle ownership = none
Gateway integration = none
```

## What Phase 10 Proves

A successful Phase 10 report means only:

```text
controlled_shadow_prototype_loop_verified
```

That verdict means an exact Phase 9 controlled-shadow plan report, bounded sanitized Phase 7-style publication fixtures, and a caller-supplied fake/prototype control surface produced safe evidence.

It does **not** mean production readiness, production enablement, live Gateway observation, or permission to wire runtime behavior into the running Gateway.

## Entry Point

```python
await run_flowweaver_controlled_shadow_prototype_loop(
    controlled_shadow_plan_report=phase9_report,
    publication_fixtures=sanitized_fixtures,
    control_surface=caller_supplied_control_surface,
    run_policy=prototype_run_policy,
)
```

The entry point is async because Phase 7 already uses an async control-surface contract. Phase 10 does not own event-loop, service, Docker, Gateway, or Temporal lifecycle.

## Required Inputs

### Phase 9 plan report

Must be an exact safe Phase 9 success report:

```text
type = flowweaver.controlled_shadow_plan.v0
version = flowweaver.controlled_shadow_design.v0
verdict = ready_for_controlled_shadow_prototype
side_effects = []
workflow_id == transaction_id
```

Phase 10 rejects missing or extra fields, wrong verdicts, non-exact required approvals, non-exact `verification_matrix`, non-exact `runbook_outline`, and non-exact `controlled_shadow_plan.fail_closed_errors`.

### Run policy

Must remain default-off:

```text
type = flowweaver.controlled_shadow_prototype_run_policy.v0
mode = prototype_loop_only
source_kind = sanitized_publication_fixture
control_surface_lifecycle = caller_supplied_only
gateway_effects_allowed = false
temporal_lifecycle_allowed = false
payload_carrying_signals_allowed = false
artifact_mode = safe_summary_only
log_policy = sanitized_codes_only
side_effects = []
```

`max_publications` must be within the Phase 9 plan transaction bound. `max_delivery_updates_per_publication` must be within the Phase 9 delivery-surface bound.

### Publication fixtures

Fixtures must be sanitized Phase 7 ready publications. They may contain only safe synthetic runtime IDs, safe counts, statuses, and claim-check policy metadata. They must not include raw prompts, raw tool output, raw card JSON, raw media values or paths, raw platform payloads, platform chat/user/message identifiers, credentials, connection strings, or raw exception text.

Delivery ACK updates must stay bounded and tied to initialized runtime delivery slots. Phase 10 does not invent slots to force parity.

### Control surface

The only live object accepted is a caller-supplied object with an async `handle(request)` method. Phase 10 must not construct, connect, start, serialize, or persist it.

## What Phase 10 Does Not Enable

Phase 10 does not enable or perform:

```text
production Gateway wiring
real Feishu/Sachima send/edit/render/callback effects
Gateway restart
Docker / daemon / service startup
external Temporal service lifecycle
Temporal client or Worker construction
production config writes
production tool registry writes
payload-carrying Temporal Signals
live Gateway observation
remote branch or worktree cleanup
```

The implementation must not modify `gateway/run.py`, `run_agent.py`, `gateway/platforms/**`, production config, or production registry files.

## Report and Artifact Policy

Successful reports and artifacts contain only safe summaries:

```text
stable synthetic IDs
counts
statuses
safe digests
stable error codes
required approval labels
side_effects = []
```

Blocked reports contain only:

```text
type
version
ok = false
verdict = blocked
phase
error_code
side_effects = []
```

Raw Phase 7 publications, start payloads, snapshots, ACK envelopes, exception text, tool output, card JSON, media data/paths, platform payloads, private identifiers, credentials, and connection strings must never appear in Phase 10 reports or artifacts.

## Required Separate Approvals

A successful Phase 10 report repeats these separate approvals:

```text
production_gateway_wiring
production_config_write
gateway_restart
external_temporal_service
real_send_edit_render_callback
production_tool_registry
remote_branch_or_worktree_cleanup
```

None of those actions are approved by this runbook or by a passing Phase 10 result.

## Verification Commands

Focused Phase 10 gate:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py -q
```

Prototype regression gate:

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py \
  tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py \
  tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py \
  tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py \
  tests/prototypes/test_flowweaver_phase6_gateway_ack_shadow_bridge.py \
  tests/prototypes/test_flowweaver_phase5k_runtime_control_surface.py \
  tests/prototypes/test_flowweaver_phase5k_mcp_control_surface.py \
  tests/prototypes/test_flowweaver_phase5j_activity_contract.py \
  tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py \
  tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5c_tool_adapter.py \
  tests/prototypes/test_flowweaver_phase5c_mcp_server_surface.py \
  tests/prototypes/test_flowweaver_phase5c_tool_surface.py \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  -q
```

Integration regression warning:

```text
scripts/run_tests.sh intentionally ignores tests/integration/**.
```

Use direct hermetic pytest for integration regression:

```bash
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py \
  tests/integration/test_flowweaver_phase6_gateway_ack_shadow_bridge.py \
  tests/integration/test_flowweaver_phase5k_runtime_control_surface.py \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py \
  tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  -q
```
