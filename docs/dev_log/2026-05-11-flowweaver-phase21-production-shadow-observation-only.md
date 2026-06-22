# FlowWeaver Phase 21 Production-Shadow Observation-Only Dev Log

## 2026-05-09 Start

Branch/worktree:

```text
feat/flowweaver-phase21-production-shadow-observation-only
/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase21-production-shadow-observation-only
```

Base:

```text
68b030f7b [verified] feat(flowweaver): add phase20 temporal observation validation (#59)
```

## Scope Confirmation

Goal: add a bounded, default-off production-shadow observation sidecar for real Gateway turns after ingress reduction, using only caller-supplied runtime control surfaces and start/query runtime operations.

Strongest allowed verdict:

```text
ready_for_separate_delivery_or_agent_execution_design
```

Boundary summary:

- default off by `flowweaver.production_shadow_observation.enabled=false`;
- narrow allowlisted platforms only when explicitly enabled;
- no Gateway-owned Temporal Client, Worker, namespace, task queue, service, daemon, Docker, socket, or subprocess lifecycle;
- no production Gateway restart/config write/platform adapter mutation;
- no send/edit/render/callback behavior change;
- no delivery ACK invention;
- no Temporal-backed agent/tool execution;
- no raw prompt, message text, platform/chat/user/message id, card JSON, media path, callback payload, credential-shaped value, raw exception text, or tool output in runtime requests, history, snapshots, logs, docs, fixtures, or user-visible output.

## Codex Scope Review

Initial read-only Codex review result: `PASS`.

Blockers: `<none>`.

Required constraint captured from Codex: the Gateway hook must be a bounded sidecar. Any observation timeout/error must become sanitized counters/stable codes and must not mutate `response`, `agent_result.delivery_state`, `already_sent`, `should_skip_final_text`, or adapter delivery behavior.

## TDD Evidence

RED/GREEN sequence:

1. Initial gateway gate failed with `ModuleNotFoundError: No module named 'gateway.flowweaver_production_shadow_observation'`, proving the new Phase 21 API was absent.
2. Added minimal `gateway/flowweaver_production_shadow_observation.py` and `GatewayRunner._maybe_observe_flowweaver_production_shadow` hook.
3. Gateway gate reached GREEN: `tests/gateway/test_flowweaver_production_shadow_observation.py` reported `12 passed`.
4. Local test-managed Temporal Worker integration reached GREEN: `tests/integration/test_flowweaver_phase21_production_shadow_observation.py` reported `1 passed`.
5. Legacy guard allowlist recursion was fixed and Phase19/20/21 gateway guard collection reached GREEN: `47 passed`.
6. Codex final review then found two coverage blockers:
   - enabled-but-not-allowlisted platform path needed explicit zero-runtime-call coverage;
   - Gateway hook timeout/failure path needed explicit delivery-state/skip-decision preservation coverage.
7. Added the missing tests:
   - `test_phase21_enabled_but_not_allowlisted_skips_without_touching_runtime`;
   - `test_phase21_gateway_runner_hook_timeout_preserves_delivery_state_and_skip_decision`.
8. Phase21 gateway gate reached GREEN again: `14 passed`.

## Verification Log

Fresh verification after the Codex blocker patch:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_production_shadow_observation.py -q
=> 14 passed

scripts/run_tests.sh tests/gateway/test_flowweaver_temporal_observation_bridge.py tests/gateway/test_flowweaver_temporal_observation_validation_gate.py tests/gateway/test_flowweaver_production_shadow_observation.py -q
=> 49 passed

TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 tests/integration/test_flowweaver_phase21_production_shadow_observation.py tests/integration/test_flowweaver_phase20_temporal_observation_validation.py tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py -q
=> 5 passed

scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_publisher.py tests/prototypes/test_flowweaver_phase5c_tool_surface.py tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py tests/integration/test_flowweaver_phase5i_start_signature_parity.py tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py tests/integration/test_flowweaver_phase5k_runtime_control_surface.py -q
=> 16 passed

python -m py_compile targeted changed Python files
=> pass

python -m ruff check targeted changed Python files
=> pass

git diff --check
=> pass

added-line security scan
=> pass

forbidden-surface added-lines scan on production code
=> pass
```

## Review / Safety Gate

Final Codex review sequence:

1. Initial final blocker review: `BLOCK` for two missing coverage tests only. Codex reported no production lifecycle, adapter mutation, or raw-material leak blocker in the implementation.
2. Blocker patch added both explicit tests and all local verification was rerun.
3. Narrow Codex re-review result: `PASS`.

Final Codex re-review notes:

```text
VERDICT: PASS
BLOCKERS:
- None
NOTES:
- Both prior coverage blockers are addressed in the live diff.
- I did not find a concrete new Phase 21 blocker in the reviewed patch.
```
