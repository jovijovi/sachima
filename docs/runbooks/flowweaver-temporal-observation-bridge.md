# FlowWeaver Temporal Observation Bridge Runbook

## Purpose

Phase 19 adds a default-off Gateway observation bridge that can reduce a safe observation envelope into FlowWeaver Temporal runtime control requests.

It is for Phase 20 guarded validation preparation only.

## Default State

Keep disabled unless a test or later approved guarded validation explicitly enables it.

Disabled behavior:

- returns a stable disabled result;
- performs no runtime calls;
- has `side_effects = []`;
- does not require a live Temporal client or Worker.

## Enablement Requirements

Only an explicit controlled test policy may enable the bridge in Phase 19.

Enabled bridge requirements:

1. Caller supplies `runtime_control_surface` with an async `handle(request)` method.
2. The observation is already reduced to safe labels, refs, counts, digest-like fields, exact booleans, and bounded surfaces.
3. The bridge calls:

```text
start_transaction
query_transaction
```

No other runtime control operations are allowed in Phase 19.

## Forbidden Actions

Do not use this bridge to:

- send, edit, render, or callback into platform adapters;
- reconcile live delivery ACKs;
- start or own Temporal Worker/service lifecycle;
- connect to Temporal directly;
- write config/registry files;
- restart Gateway;
- store raw platform payloads, card JSON, media paths, raw prompts, raw tool output, raw exception text, or credential-shaped values.

## Rollback / Kill Switch

Rollback is setting the bridge policy to disabled. Disabled mode is a no-op and should be safe even if a runtime control surface object is unavailable.

If unsafe input is detected, the bridge fails closed with a stable error code and zero runtime calls.

## Verification

Focused:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_temporal_observation_bridge.py -q
```

Regression:

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
