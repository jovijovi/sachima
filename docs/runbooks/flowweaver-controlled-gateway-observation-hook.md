# FlowWeaver Controlled Gateway Observation Hook Runbook

## Phase and Scope

Phase 12 implements a pure, default-off **Controlled Gateway Observation Hook / Safe Projection** helper.

A passing Phase 12 report means only:

```text
ready_for_live_gateway_observation_enablement_design
```

That verdict does **not** authorize live Gateway observation, production Gateway wiring, production config writes, Gateway restart, real IM send/edit/render/callback, platform adapter changes, production tool registry writes, or Temporal service lifecycle.

## Safe Input

Phase 12 accepts only an exact successful Phase 11 design report:

```text
type = flowweaver.controlled_gateway_observation_design_report.v0
version = flowweaver.controlled_gateway_observation_design.v0
verdict = ready_for_controlled_gateway_observation_implementation
phase = phase11_controlled_gateway_observation_integration_design
side_effects = []
```

Phase 12 also accepts caller-supplied sanitized summaries only:

- `shadow_runtime_publication_summary`
- `delivery_state_summary`
- `progress_snapshot_summary`

These are summaries, not live Gateway objects. They must not contain platform payloads, private IDs, raw prompts, raw tool output, card JSON, media payloads, callback payloads, raw runtime history, raw exception text, credentials, or connection strings.

## Default-Off Boundary

Required default-off behavior:

- `enabled` must be exactly `False`.
- Any truthy or non-false enablement request fails closed with `live_observation_requested`.
- The helper emits safe summaries only.
- `side_effects` must be `[]` in every accepted input and output.

Phase 12 does not edit or wire:

```text
gateway/run.py
run_agent.py
gateway/platforms/**
production config
production tool registry
```

## Output Contract

Successful output is a safe report:

```text
type = flowweaver.controlled_gateway_observation_hook_report.v0
version = flowweaver.controlled_gateway_observation_hook.v0
verdict = ready_for_live_gateway_observation_enablement_design
phase = phase12_controlled_gateway_observation_hook
observation_mode = default_off_static_projection
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

Phase 12 reports preserve this approval boundary:

```text
live_gateway_observation_enablement
production_gateway_wiring
production_config_write
gateway_restart
external_temporal_service
real_send_edit_render_callback
production_tool_registry
remote_branch_or_worktree_cleanup
```

No item above is approved by Phase 12 itself.

## Verification Commands

Focused Phase 12 contract:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_controlled_gateway_observation.py -q
```

Phase 7–12 regression:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_controlled_gateway_observation.py \
  tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py \
  tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py \
  tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py \
  tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py \
  tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py \
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
  gateway/flowweaver_controlled_gateway_observation.py \
  tests/gateway/test_flowweaver_controlled_gateway_observation.py

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m ruff check \
  gateway/flowweaver_controlled_gateway_observation.py \
  tests/gateway/test_flowweaver_controlled_gateway_observation.py

git diff --check
```

## Operator Notes

If any future request tries to turn this report into live observation, Gateway wiring, production config changes, Gateway restart, Temporal lifecycle, platform adapter calls, or real IM effects, stop and require separate approval. Phase 12 is a safe projection hook; it still does not press the production switch.
