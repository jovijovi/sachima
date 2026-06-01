# FlowWeaver Temporal Observation Validation Runbook

## Purpose

Phase 20 validates the Phase 19 Gateway Temporal observation bridge before any production-shadow observation request.

It proves that sanitized synthetic Gateway-style observation events can be mirrored into a local test-managed Temporal runtime without leaking raw material, while preserving duplicate-start, rollback, and kill-switch safety.

This runbook is intentionally narrower than the broader roadmap wording: Phase 20 implementation uses no staging runtime, no manual operator lifecycle, and no captured real Gateway fixtures.

## Default State

No production Gateway behavior is enabled by this phase.

Default behavior remains:

- no production Gateway restart;
- no production config write;
- no platform adapter mutation;
- no send/edit/render/callback changes;
- no Temporal-backed delivery or agent execution;
- Gateway does not own Worker/service lifecycle.

## Validation Prerequisites

1. Phase 19 bridge exists and is default-off.
2. Observation inputs are reduced synthetic/sanitized Gateway-style envelopes only.
3. Runtime control surface is caller-supplied.
4. Local/test Temporal Worker lifecycle is owned only by the test harness, never by production Gateway code.
5. History scans inspect both JSON-style output and serialized event bytes.

## Guarded Validation Flow

```text
sanitized synthetic observation fixture
  -> observe_gateway_turn_for_flowweaver_temporal(...)
  -> caller-supplied runtime control surface
  -> Temporal workflow start/query
  -> safe snapshot
  -> history JSON + event-byte no-leak scan
  -> sanitized validation report
```

## Rollback / Kill Switch Drill

The rollback drill is behavioral and test-local:

1. Enable only the controlled test policy.
2. Validate one observation start/query succeeds.
3. Disable the policy.
4. Verify no new start occurs while existing query/read evidence remains safe.
5. Emit only operator action labels such as `disable_observation_policy` and `verify_existing_snapshot`; do not emit raw config values.

## Forbidden Material

Validation reports, docs, logs, fixtures, and Temporal history must not include:

- raw prompts or raw user text;
- card JSON;
- media paths or media bytes;
- platform/private identifiers;
- callback payloads;
- credential-shaped values;
- raw exception text;
- raw tool output;
- production config values.

## Verification

Focused:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_temporal_observation_validation_gate.py -q
```

Integration/regression:

```bash
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase20_temporal_observation_validation.py \
  tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  -q
```

## Success Signal

The strongest Phase 20 signal is:

```text
ready_for_production_shadow_observation_request
```

This only means Phase 21 can be requested. It does not enable production shadow observation.
