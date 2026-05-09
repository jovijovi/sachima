# FlowWeaver Phase 20 Guarded Temporal Observation Validation Dev Log

## 2026-05-09 Start

Branch/worktree:

```text
feat/flowweaver-phase20-guarded-temporal-observation-validation
/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase20-guarded-temporal-observation-validation
```

Base:

```text
5b37757a8 [verified] feat(progress): show context usage in task cards (#58)
```

## Scope Confirmation

Goal: validate Phase 19 Gateway Temporal observation bridge using sanitized synthetic Gateway-style observations plus local test-managed Temporal evidence.

Strongest allowed verdict:

```text
ready_for_production_shadow_observation_request
```

Boundary summary:

- local/test Worker lifecycle allowed only inside tests;
- observation-only validation, no production shadow enablement;
- no production Gateway restart/config write/platform adapter mutation;
- no send/edit/render/callback behavior;
- no Gateway-owned Worker/service lifecycle;
- no raw prompt, card JSON, media path, platform id, callback payload, credential-shaped value, raw exception text, or tool output in history, snapshots, reports, logs, docs, or fixtures.

## TDD Evidence

Completed:

- RED gate: `scripts/run_tests.sh tests/gateway/test_flowweaver_temporal_observation_validation_gate.py -q` failed with missing `gateway.flowweaver_temporal_observation_validation`.
- GREEN gate: added pure Phase 20 validation helpers and bounded Phase 19 query retry; same focused gate passed `12 passed`.
- RED/GREEN integration: added local test-managed Temporal Worker validation harness for sanitized synthetic Gateway-style observations; focused integration passed `2 passed`.
- Maintenance GREEN: updated older phase diff allowlists so Phase 20 files remain inside explicit guarded surfaces.
- Final review blocker RED/GREEN: Codex found `tool_output` history evidence could bypass the no-leak scan. Added JSON/event-byte RED cases for `tool_output` key forms, including whitespace before `:`, then fixed the scanner with key-shape detection while allowing a bare policy-list string.

## Codex Scope Review

Initial read-only Codex review result: `BLOCK`.

Blocker: the new Phase 20 docs/runbook still echoed broader roadmap language around staging/manual validation and captured fixtures. The implementation scope is now narrowed to local test-managed Temporal only and sanitized synthetic Gateway-style fixtures only.

Blocker-only Codex re-review result: `PASS`, blockers `<none>`.

Final Codex review result: `BLOCK`.

Blocker: `tool_output` / raw tool-output evidence in history JSON/event bytes could still produce a success verdict.

Tool-output blocker-only Codex re-review result: `PASS`, blockers `<none>`. Notes: key forms and raw tool-output text are rejected; bare `"tool_output"` policy string remains allowed.

## Verification Log

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_temporal_observation_validation_gate.py -q
=> RED: ModuleNotFoundError: No module named 'gateway.flowweaver_temporal_observation_validation'

scripts/run_tests.sh tests/gateway/test_flowweaver_temporal_observation_validation_gate.py -q
=> 12 passed in 1.57s

scripts/run_tests.sh tests/gateway/test_flowweaver_temporal_observation_validation_gate.py::test_phase20_history_scan_rejects_forbidden_json_or_event_byte_material -q
=> RED after Codex blocker: 2 failed for `tool_output` key/value history evidence

scripts/run_tests.sh tests/gateway/test_flowweaver_temporal_observation_validation_gate.py::test_phase20_history_scan_rejects_forbidden_json_or_event_byte_material -q
=> 11 passed in 1.12s

TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 tests/integration/test_flowweaver_phase20_temporal_observation_validation.py -q
=> 2 passed in 1.57s

scripts/run_tests.sh tests/gateway/test_flowweaver_temporal_observation_validation_gate.py -q
=> 16 passed in 1.17s

scripts/run_tests.sh tests/gateway/test_flowweaver_temporal_observation_bridge.py tests/gateway/test_flowweaver_temporal_observation_validation_gate.py -q
=> 35 passed in 1.24s

TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 tests/integration/test_flowweaver_phase20_temporal_observation_validation.py tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py tests/integration/test_flowweaver_phase5b_temporal_workflow.py -q
=> 18 passed in 1.99s

TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py tests/integration/test_flowweaver_phase5i_start_signature_parity.py tests/integration/test_flowweaver_phase5k_runtime_control_surface.py -q
=> 16 passed in 2.19s

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m py_compile gateway/flowweaver_temporal_observation_bridge.py gateway/flowweaver_temporal_observation_validation.py tests/gateway/test_flowweaver_temporal_observation_bridge.py tests/gateway/test_flowweaver_temporal_observation_validation_gate.py tests/integration/test_flowweaver_phase20_temporal_observation_validation.py tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py tests/integration/test_flowweaver_phase5i_start_signature_parity.py tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py tests/integration/test_flowweaver_phase5k_runtime_control_surface.py
=> pass

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m ruff check gateway/flowweaver_temporal_observation_bridge.py gateway/flowweaver_temporal_observation_validation.py tests/gateway/test_flowweaver_temporal_observation_bridge.py tests/gateway/test_flowweaver_temporal_observation_validation_gate.py tests/integration/test_flowweaver_phase20_temporal_observation_validation.py tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py tests/integration/test_flowweaver_phase5i_start_signature_parity.py tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py tests/integration/test_flowweaver_phase5k_runtime_control_surface.py
=> All checks passed

git diff --check
=> pass

Custom forbidden-surface scan
=> FORBIDDEN_SURFACE_OK changed_files=12 production_files=2
```

## Review / Safety Gate

Pending independent final review.
