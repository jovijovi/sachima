# FlowWeaver Phase 20 Guarded Temporal Observation Validation Plan

## Status

Approved by 狗哥 for implementation on 2026-05-09.

## Objective

Validate the Phase 19 default-off Gateway Temporal observation bridge against realistic sanitized synthetic Gateway-style observations and a local test-managed Temporal Worker, while proving history no-leak, duplicate-start stability, rollback/kill-switch behavior, and safe validation reporting.

Strongest allowed verdict:

```text
ready_for_production_shadow_observation_request
```

This is readiness to request Phase 21 production-shadow observation-only approval. It does not enable production shadow.

## Scope

Create:

- `gateway/flowweaver_temporal_observation_validation.py`
- `tests/gateway/test_flowweaver_temporal_observation_validation_gate.py`
- `tests/integration/test_flowweaver_phase20_temporal_observation_validation.py`
- `docs/runbooks/flowweaver-temporal-observation-validation.md`

May narrowly extend:

- `gateway/flowweaver_temporal_observation_bridge.py` only if required for duplicate-start/query retry safe handling.

## Allowed Behavior

This implementation scope intentionally narrows the broader roadmap language: no staging/manual runtime validation and no captured production fixtures are included in this PR.

Phase 20 may:

- run local Temporal test environments and Workers in tests only;
- use sanitized synthetic Gateway-style fixtures only;
- call the Phase 19 bridge through caller-supplied runtime control surfaces;
- inspect Temporal history JSON and serialized event bytes for forbidden material;
- validate duplicate-start, consecutive-turn identity, query retry, rollback, and disabled-policy paths;
- return sanitized validation reports and stable error codes.

Phase 20 must not:

- restart production Gateway;
- write production config;
- send/edit/render/callback real messages;
- add production platform adapter behavior;
- let Gateway own Worker/service lifecycle;
- store raw prompt, card JSON, media path, platform id, callback payload, credential-shaped value, raw exception text, or tool output in history, snapshots, docs, logs, fixtures, or reports.

## Candidate Entrypoints

```python
def build_temporal_observation_validation_report(
    *,
    bridge_result: object,
    history_json: object,
    history_event_bytes: object,
    rollback_drill: object,
    duplicate_start_report: object,
) -> dict[str, object]:
    ...

async def validate_gateway_observation_against_temporal(
    *,
    observation: object,
    runtime_control_surface: object,
    bridge_policy: object,
    history_reader: object,
    rollback_drill: object,
) -> dict[str, object]:
    ...
```

Entrypoint rules:

- Accept only exact plain dict/list/str/int/bool/bytes where explicitly allowed.
- Validation output is a compact safe report, not raw history or raw bridge payloads.
- History scans cover both JSON-style representations and serialized protobuf bytes.
- Rollback report contains operator action labels only, not config values.
- Runtime/Worker lifecycle is not created by Gateway production code; lifecycle in this phase lives only inside integration tests.
- Staging Temporal clients, manual operator lifecycle, and captured real Gateway fixtures are out of scope for this PR.

## TDD Plan

1. RED gateway validation-gate tests for safe report shape, forbidden-material detection in JSON/bytes, duplicate-start report validation, rollback labels, and no raw echo.
2. GREEN minimal validation helper implementation.
3. RED integration test with a local/test-managed Temporal Worker and Phase 19 bridge flow:

   ```text
   sanitized Gateway-style observation
     -> Phase 19 bridge
     -> runtime control surface start/query
     -> Temporal workflow snapshot
     -> history JSON + event-byte no-leak scan
     -> sanitized Phase 20 validation report
   ```

4. GREEN integration harness, reusing existing Phase 5B/5C/5K runtime contracts where possible.
5. RED/GREEN duplicate-start and consecutive-turn tests.
6. RED/GREEN kill-switch rollback drill.
7. Source/diff safety gate for forbidden production side effects.

## Verification Commands

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_temporal_observation_validation_gate.py -q

TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase20_temporal_observation_validation.py \
  tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  -q

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m py_compile \
  gateway/flowweaver_temporal_observation_validation.py \
  tests/gateway/test_flowweaver_temporal_observation_validation_gate.py \
  tests/integration/test_flowweaver_phase20_temporal_observation_validation.py

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m ruff check \
  gateway/flowweaver_temporal_observation_validation.py \
  tests/gateway/test_flowweaver_temporal_observation_validation_gate.py \
  tests/integration/test_flowweaver_phase20_temporal_observation_validation.py

git diff --check
```

## Codex Review Gate

Codex must return a concrete PASS/BLOCK verdict and check:

- JSON and serialized protobuf event bytes are both scanned;
- duplicate-start handling is stable and sanitized;
- Worker/test-environment lifecycle exists only in tests;
- rollback/kill-switch is behaviorally tested;
- no production Gateway enablement, config write, restart, platform adapter mutation, send/edit/render/callback, or Temporal-backed agent execution sneaks in.
