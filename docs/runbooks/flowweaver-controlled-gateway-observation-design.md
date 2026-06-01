# FlowWeaver Controlled Gateway Observation Design Runbook

## Phase and Scope

Phase 11 implements a prototype-only **Controlled Gateway Observation / Integration Design Gate**.

A passing Phase 11 report means only:

```text
ready_for_controlled_gateway_observation_implementation
```

That verdict does **not** authorize live Gateway observation, production Gateway wiring, production config writes, Gateway restart, real IM send/edit/render/callback, platform adapter changes, tool registry writes, or Temporal service lifecycle.

## Safe Input

The only accepted evidence input is an exact Phase 10 prototype loop success report:

```text
type = flowweaver.controlled_shadow_prototype_loop_report.v0
version = flowweaver.controlled_shadow_prototype_loop.v0
verdict = controlled_shadow_prototype_loop_verified
phase = phase10_controlled_shadow_prototype_loop
side_effects = []
```

Blocked Phase 10 reports, production/live verdict strings, extra fields, missing checks, reordered verification matrices, raw material, platform identifiers, and any side effects must fail closed.

## Static Descriptors Only

Phase 11 accepts static descriptors for:

- Gateway observation boundary
- Integration policy
- Runtime handoff boundary
- Artifact policy
- Rollback policy

Descriptors may name approved labels and file paths. They must not carry live objects, callbacks, clients, adapters, config paths, sockets, subprocess handles, task queues, Temporal addresses, platform payloads, raw snapshots, or raw runtime history.

## Default-Off Boundary

Required default-off controls:

- `default_enabled = False`
- `config_write_allowed = False`
- `gateway_restart_allowed = False`
- `runtime_effects_allowed = False`
- `temporal_lifecycle_allowed = False`
- `payload_carrying_signals_allowed = False`
- `registry_write_allowed = False`
- `side_effects = []`

The Gateway remains untouched. This runbook explicitly forbids editing `gateway/run.py`, `run_agent.py`, `gateway/platforms/**`, production config, and production registry files as part of Phase 11.

## Artifact and Log Policy

Reports and artifacts are safe-summary-only. They may contain stable labels, counts, checks, digests, approval labels, and stable error codes.

They must not contain:

```text
raw_prompt
raw_tool_output
raw_card_json
raw_media_payload
raw_platform_payload
platform_message_identifiers
credentials_or_connection_strings
raw_exception_text
raw_gateway_event
raw_adapter_object
raw_callback_payload
raw_runtime_history
```

Policy metadata may name forbidden material as labels. Actual raw material must never appear in outputs or logs.

## Rollback / Kill Switch Expectations

Even though Phase 11 does not enable production behavior, future implementation plans must prove:

- kill switch required
- rollback hooks required
- config revert required
- Gateway restart requires separate approval
- production enablement requires separate approval

## Required Separate Approvals

Phase 11 reports must preserve this approval order:

```text
controlled_gateway_observation_implementation
live_gateway_observation_enablement
production_gateway_wiring
production_config_write
gateway_restart
external_temporal_service
real_send_edit_render_callback
production_tool_registry
remote_branch_or_worktree_cleanup
```

## Verification Commands

Focused Phase 11 contract:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py -q
```

Prototype regression:

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py \
  tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py \
  tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py \
  tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py \
  tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py \
  -q
```

Static checks:

```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m py_compile \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_gateway_observation_design.py \
  tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m ruff check \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_gateway_observation_design.py \
  tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py

git diff --check
```

## Operator Notes

If any future request tries to turn this report into live Gateway observation, production config, restart, Temporal lifecycle, or real IM effects, stop and require a separate approval. Phase 11 designed and implemented the map; it still does not touch the production switch.
