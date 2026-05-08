# FlowWeaver Live Gateway Observation Enablement Design Runbook

## Phase and Scope

Phase 13 is a pure **Live Gateway Observation Enablement Design Gate**.

A passing Phase 13 report means only:

```text
ready_for_live_gateway_observation_enablement_implementation
```

That verdict does **not** authorize live Gateway observation, production Gateway wiring, production config writes, Gateway restart, real IM send/edit/render/callback, platform adapter changes, production tool registry writes, or Temporal service lifecycle.

## Safe Input

Phase 13 accepts only an exact successful Phase 12 hook report:

```text
type = flowweaver.controlled_gateway_observation_hook_report.v0
version = flowweaver.controlled_gateway_observation_hook.v0
verdict = ready_for_live_gateway_observation_enablement_design
phase = phase12_controlled_gateway_observation_hook
observation_mode = default_off_static_projection
side_effects = []
```

Phase 13 also accepts static policy descriptors only:

- `enablement_policy`
- `observation_evidence_policy`
- `artifact_policy`
- `rollback_policy`

These descriptors are policy metadata, not runtime objects. They must not contain platform payloads, private IDs, raw prompts, raw tool output, card JSON, media payloads, callback payloads, raw Gateway/runtime history, raw exception text, credentials, or connection strings.

## Default-Off Boundary

Required default-off behavior:

- `default_enabled` must be exactly `False`.
- config writes must be disallowed.
- registry writes must be disallowed.
- Gateway restart must be disallowed.
- platform adapter calls must be disallowed.
- Temporal lifecycle must be disallowed.
- kill switch and rollback policy must be present.
- every accepted input and output must preserve `side_effects = []`.

Phase 13 does not edit or wire:

```text
gateway/run.py
run_agent.py
gateway/platforms/**
production config
production tool registry
```

## Output Contract

Successful output is a safe design report:

```text
type = flowweaver.live_gateway_observation_enablement_design_report.v0
version = flowweaver.live_gateway_observation_enablement_design.v0
verdict = ready_for_live_gateway_observation_enablement_implementation
phase = phase13_live_gateway_observation_enablement_design
enablement_mode = default_off_design_gate
side_effects = []
```

Blocked output contains only:

```text
type
version
ok = False
verdict = blocked
phase
error_code
side_effects = []
```

## Required Separate Approvals

Phase 13 reports preserve this approval boundary:

```text
live_gateway_observation_enablement_implementation
live_gateway_observation_enablement
production_gateway_wiring
production_config_write
gateway_restart
external_temporal_service
real_send_edit_render_callback
production_tool_registry
remote_branch_or_worktree_cleanup
```

No item above is approved by Phase 13 itself.

## Verification Commands

Focused Phase 13 contract:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py -q
```

Phase 11–13 regression:

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py \
  tests/gateway/test_flowweaver_controlled_gateway_observation.py \
  tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py \
  -q
```

Direct hermetic integration chain:

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

Static checks:

```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m py_compile \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/live_gateway_observation_enablement_design.py \
  tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m ruff check \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/live_gateway_observation_enablement_design.py \
  tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py

git diff --check
```

## Operator Notes

If any future request tries to turn this design report into live observation, production wiring, production config changes, Gateway restart, Temporal lifecycle, platform adapter calls, or real IM effects, stop and require separate approval. Phase 13 designs the enablement contract; it still does not press the switch.
