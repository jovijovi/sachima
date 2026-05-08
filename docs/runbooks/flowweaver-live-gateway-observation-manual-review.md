# FlowWeaver Live Gateway Observation Manual Review Runbook

## Phase and Scope

Phase 15 is a pure **Manual Live Gateway Observation Review Gate** helper.

A passing Phase 15 artifact means only:

```text
ready_for_live_gateway_observation_enablement_operator_decision
```

That verdict does **not** authorize live Gateway observation, production Gateway wiring, production config writes, Gateway restart, real IM send/edit/render/callback, platform adapter changes, production tool registry writes, external Temporal service lifecycle, or real approval-token handling.

## Safe Input

Phase 15 accepts only an exact successful Phase 14 request artifact:

```text
type = flowweaver.live_gateway_observation_enablement_request.v0
version = flowweaver.live_gateway_observation_enablement.v0
verdict = ready_for_manual_live_gateway_observation_enablement_request_review
phase = phase14_live_gateway_observation_enablement_implementation
enablement_mode = default_off_manual_review_request
side_effects = []
```

Phase 15 also accepts one static review-policy descriptor only:

```text
type = flowweaver.live_gateway_observation_manual_review_policy.v0
mode = default_off_operator_review_gate
review_scope = manual_live_gateway_observation_enablement_request_review
review_approved = False
enablement_authorized = False
default_enabled = False
requested_enabled = False
live_observation_enabled = False
approval_token_required = True
approval_token_supplied = False
approval_token_material_allowed = False
side_effects = []
```

The review policy is metadata, not a runtime object. It must not contain platform payloads, private IDs, raw prompts, raw tool output, card JSON, media payloads, callback payloads, raw Gateway/runtime history, raw exception text, credentials, connection strings, or real approval-token material.

## Default-Off Boundary

Required default-off behavior:

- `review_approved` must be exactly `False`.
- `enablement_authorized` must be exactly `False`.
- `default_enabled` must be exactly `False`.
- `requested_enabled` must be exactly `False`.
- live observation must remain inactive in the artifact.
- approval-token material must be absent; only reference labels are allowed.
- config writes must be disallowed.
- registry writes must be disallowed.
- Gateway restart must be disallowed.
- platform adapter calls must be disallowed.
- Temporal lifecycle must be disallowed.
- kill switch and rollback policy must be present and armed.
- every accepted input and output must preserve `side_effects = []`.

Phase 15 does not edit or wire:

```text
gateway/run.py
run_agent.py
gateway/platforms/**
production config
production tool registry
```

## Output Contract

Successful output is a safe operator-decision review artifact:

```text
type = flowweaver.live_gateway_observation_manual_review_report.v0
version = flowweaver.live_gateway_observation_manual_review.v0
verdict = ready_for_live_gateway_observation_enablement_operator_decision
phase = phase15_manual_live_gateway_observation_review_gate
review_mode = default_off_operator_review_gate
side_effects = []
```

The review artifact may include only stable labels, derived ids, short safe digests, checks, required approvals, rollback labels, kill-switch labels, and stable error codes. It must not include raw Gateway events, raw cards, raw callbacks, raw platform payloads, private platform IDs, credentials, connection strings, or real approval-token material.

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

Phase 15 reports preserve this approval boundary:

```text
operator_live_gateway_observation_enablement_decision
live_gateway_observation_enablement
production_gateway_wiring
production_config_write
gateway_restart
external_temporal_service
real_send_edit_render_callback
production_tool_registry
remote_branch_or_worktree_cleanup
```

No item above is approved by Phase 15 itself.

## Verification Commands

Focused Phase 15 contract:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_manual_review.py -q
```

Phase 11–15 regression:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_live_gateway_observation_manual_review.py \
  tests/gateway/test_flowweaver_live_gateway_observation_enablement.py \
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
  gateway/flowweaver_live_gateway_observation_manual_review.py \
  tests/gateway/test_flowweaver_live_gateway_observation_manual_review.py

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m ruff check \
  gateway/flowweaver_live_gateway_observation_manual_review.py \
  tests/gateway/test_flowweaver_live_gateway_observation_manual_review.py

git diff --check
```

## Operator Notes

If any future request tries to turn this review artifact into live observation, production wiring, production config changes, Gateway restart, Temporal lifecycle, platform adapter calls, real IM effects, or actual approval-token handling, stop and require separate approval. Phase 15 builds the operator decision gate; it still does not press the switch.
