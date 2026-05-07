# FlowWeaver Controlled Shadow Plan Builder Runbook

## Status

This runbook documents the Phase 9 controlled-shadow **plan builder** boundary. It is not a production activation guide.

Current approved scope:

```text
Phase 9 implementation = prototype-only static plan builder
Default state = off
Production side effects = none
Runtime lifecycle ownership = none
```

## What Phase 9 Proves

A passing Phase 9 result means only:

```text
ready_for_controlled_shadow_prototype
```

That verdict means the static controlled-shadow prototype plan contract is safe enough for a later separately approved prototype execution phase. It does not authorize live Gateway observation, production Gateway wiring, real Feishu/Sachima effects, service lifecycle changes, or production config/registry writes.

## Plan Builder Entry Point

```python
build_flowweaver_controlled_shadow_plan(
    *,
    readiness_report,
    shadow_scope,
    gateway_observation_boundary,
    runtime_execution_boundary,
    artifact_policy,
    rollback_policy,
)
```

The function is synchronous and pure. It returns a plain dictionary report and must not construct clients, workers, adapters, sockets, subprocesses, services, or persistent writers.

## Required Inputs

### Phase 8 readiness report

Must be an exact safe Phase 8 success report:

```text
type = flowweaver.production_readiness_report.v0
version = flowweaver.production_readiness_gate.v0
verdict = ready_for_controlled_shadow_design
side_effects = []
workflow_id == transaction_id
```

The report must include only the merged Phase 8 success-report fields and must carry the required checks, candidate contract, required separate approvals, and runbook outline.

### Shadow scope descriptor

Must remain default-off and replay/prototype scoped:

```text
type = flowweaver.controlled_shadow_scope.v0
mode = prototype_shadow_candidate
source_kind = phase8_readiness_replay
side_effects = []
```

Live Gateway streams, production modes, private platform identifiers, and delivery-capable scopes are rejected.

### Gateway observation boundary

Must be sanitized observation only:

```text
type = flowweaver.gateway_observation_boundary.v0
observation_mode = sanitized_replay_only
inbound_material = sanitized_refs_only
outbound_effects = none
adapter_imports_allowed = false
platform_payloads_allowed = false
message_identifiers_allowed = false
side_effects = []
```

The builder must not import or call Gateway adapters.

### Runtime execution boundary

Must be lifecycle-free:

```text
type = flowweaver.runtime_execution_boundary.v0
control_surface = phase5k_control_surface
client_lifecycle = caller_supplied_only
temporal_dependency = optional_extra_only
event_ingress = validated_updates_only
worker_lifecycle = none
side_effects = []
```

Payload-carrying Signals, Temporal address/task-queue descriptors, client factories, workers, services, daemons, and subprocess ownership are rejected.

### Artifact policy

Must allow safe summaries only:

```text
type = flowweaver.controlled_shadow_artifact_policy.v0
artifact_mode = safe_summary_only
retention = local_artifact_only
log_policy = sanitized_codes_only
side_effects = []
```

Allowed artifact fields are limited to stable IDs, counts, statuses, digests, approvals, stable error codes, and side-effect evidence.

Forbidden material must include:

```text
raw prompt text
raw tool output
raw card JSON
raw media payloads
raw platform payloads
platform message identifiers
credentials or connection strings
raw exception text
```

Use policy metadata names only in policy fields. Raw values must never appear in outputs, logs, reports, or user-visible artifacts.

### Rollback policy

Must keep the plan off and reversible:

```text
type = flowweaver.controlled_shadow_rollback_policy.v0
default_state = off
kill_switch_required = true
rollback_plan_required = true
production_actions_require_separate_approval = true
config_write_allowed = false
registry_write_allowed = false
gateway_restart_allowed = false
service_lifecycle_allowed = false
side_effects = []
```

## Required Separate Approvals

A successful Phase 9 report must carry these separate approvals:

```text
production_gateway_wiring
production_config_write
gateway_restart
external_temporal_service
real_send_edit_render_callback
production_tool_registry
remote_branch_or_worktree_cleanup
```

None of those actions are approved by this runbook.

## Verification Matrix

A successful report must include these checks as true:

```text
phase8_report_exact_shape
scope_default_off
gateway_observation_only
runtime_lifecycle_free
validated_updates_only
artifact_safe_summary_only
rollback_and_kill_switch_present
production_actions_separate
side_effects_absent
```

## Verification Commands

Focused Phase 9 test:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py -q
```

Phase 8 compatibility test:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py -q
```

Prototype regression gate:

```bash
scripts/run_tests.sh \
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

Use direct hermetic pytest for integration tests:

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

## Operator Notes

If Phase 9 returns `blocked`, inspect only the stable `error_code`. Do not ask the plan builder to emit raw input values for debugging.

If future work needs live observation, Gateway wiring, service lifecycle, production config, or real IM effects, stop and create a separate design/approval gate first. Do not sneak those actions through a prototype runbook.
