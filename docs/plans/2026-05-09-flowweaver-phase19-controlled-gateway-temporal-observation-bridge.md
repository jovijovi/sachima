# FlowWeaver Phase 19 Controlled Gateway Temporal Observation Bridge Plan

## Status

Approved by 狗哥 for implementation on 2026-05-09.

## Objective

Add the first behavior-bearing, default-off Gateway observation bridge into the existing FlowWeaver Temporal runtime control surface.

The bridge consumes only a reduced sanitized observation envelope, calls only a caller-supplied runtime control surface, and returns a safe summary whose strongest verdict is:

```text
ready_for_guarded_temporal_observation_validation
```

This is readiness for Phase 20 guarded validation only. It is not production enablement.

## Scope

Create:

- `gateway/flowweaver_temporal_observation_bridge.py`
- `tests/gateway/test_flowweaver_temporal_observation_bridge.py`
- `docs/runbooks/flowweaver-temporal-observation-bridge.md`

Maintain phase guard allowlists only if existing integration guards need to recognize the new Phase 19 files.

No `gateway/run.py` wiring in this phase.

## Entrypoint

```python
async def observe_gateway_turn_for_flowweaver_temporal(
    *,
    observation: object,
    runtime_control_surface: object,
    bridge_policy: object,
) -> dict[str, object]:
    ...
```

## Required Behavior

1. Default-off no-op:
   - disabled policy returns a stable disabled result;
   - runtime control surface receives zero calls;
   - result has `side_effects = []`.
2. Sanitized observation validation:
   - exact plain dict/list/str/bool/int types only;
   - no raw prompt/body/tool output, card JSON, media path, private platform ids, callback payloads, raw exception text, credential-shaped values, or hostile subclasses;
   - exact booleans for check fields, rejecting integer impersonators.
3. Runtime call path when enabled:
   - call sequence is exactly `start_transaction` then `query_transaction` through `runtime_control_surface.handle`;
   - no reconcile/cancel/send/edit/render/callback behavior;
   - no Temporal client, Worker, WorkflowEnvironment, subprocess, socket, config write, or platform adapter import.
4. Start payload safety:
   - generated start payload must be accepted by the existing Phase 5C `build_start_payload_from_safe_fields` contract;
   - result must not echo the raw start payload or policy internals.
5. Consecutive-turn identity safety:
   - same safe session label plus different safe turn discriminator yields distinct runtime transaction ids;
   - raw discriminator/source refs are not exported.

## TDD Plan

1. RED import/API test for the new module and entrypoint.
2. GREEN minimal module for import shape only.
3. RED behavior tests for default-off, unsafe inputs, enabled start/query, identity collision avoidance, and source safety.
4. GREEN implementation.
5. Focused verification:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_temporal_observation_bridge.py -q
```

6. Regression verification:

```bash
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py \
  tests/integration/test_flowweaver_phase6_gateway_ack_shadow_bridge.py \
  tests/integration/test_flowweaver_phase5k_runtime_control_surface.py \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
```

## Codex Scope Review

Read-only Codex review returned BLOCK because the implementation files were absent. It confirmed:

- entrypoint signature above;
- success verdict above;
- required tests: default-off, sanitized rejection, start/query-only path, identity safety, and source guard;
- hard boundaries: caller-supplied runtime surface only, no lifecycle, no production Gateway side effects.

## Non-Goals

- No production shadow enablement.
- No platform adapter mutation.
- No Gateway restart or config writes.
- No runtime Worker/service lifecycle.
- No delivery ACK reconciliation from live Gateway in this phase.
- No Temporal-backed agent/tool execution.
