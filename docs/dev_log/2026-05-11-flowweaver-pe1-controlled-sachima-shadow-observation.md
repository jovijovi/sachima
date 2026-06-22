# Dev Log — FlowWeaver PE-1 Controlled Sachima Shadow Observation

## Scope

Implement PE-1 only: default-off, Sachima-only, observation-only production-shadow gating.

This branch does not write production config, restart/reload Gateway, mutate platform adapters, control production delivery, invent ACKs, run production agent/tools, or create/own Temporal runtime lifecycle.

Branch/worktree:

```text
feat/flowweaver-pe1-controlled-sachima-shadow-observation
/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-pe1-controlled-sachima-shadow-observation
```

Base:

```text
feature/sachima-channel @ c52dc8034b75
```

## Approval

狗哥 approved starting PE-1 implementation in Feishu.

Operational approvals remain separate and have not been granted in this branch:

```text
approve_production_config_write
approve_gateway_restart_or_reload
approve_sachima_platform_allowlist
approve_external_runtime_control_surface
approve_external_temporal_service_or_worker_if_used
```

## RED Evidence

Added PE-1 focused tests first. Initial focused run failed because the PE-1 Sachima-only policy resolver did not exist yet. This confirmed the missing PE-1 gate before production code was added.

## GREEN Implementation

Implemented:

- `pe1_controlled_sachima_shadow_policy_from_config(...)` in `gateway/flowweaver_production_shadow_observation.py`;
- Gateway hook now builds its policy through the PE-1 Sachima-only resolver;
- PE-1 focused tests cover default-off, exact `sachima` allowlist, duplicate/non-exact allowlist rejection, forged non-Sachima policy rejection, non-Sachima skip, start/query-only runtime calls, no ACK invention, and delivery-state preservation;
- docs/runbook/plan for PE-1 boundaries and rollback.

## Verification Log

```text
python -m pytest -q tests/gateway/test_flowweaver_pe1_controlled_sachima_shadow_observation.py
=> 4 passed in 2.77s

python -m pytest -q tests/gateway/test_flowweaver_production_shadow_observation.py tests/gateway/test_flowweaver_ai_flow_pilot.py
=> 22 passed in 3.24s

python -m pytest -o addopts= -n 4 -q tests/integration/test_flowweaver_phase21_production_shadow_observation.py tests/integration/test_flowweaver_phase33_ai_flow_pilot.py
=> 9 passed in 1.97s

scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase5*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
=> 715 passed in 5.69s

git diff --check: PASS
python -m py_compile gateway/flowweaver_production_shadow_observation.py gateway/flowweaver_ai_flow_pilot.py: PASS
static no-leak scan: STATIC_SCAN_PASS
```

## Review Status

First fresh-context blocker review found two PE-1 boundary issues:

```text
- duplicate `sachima` allowlist entries were normalized before exactness checks;
- the public observer entrypoint could accept a forged non-Sachima enabled policy.
```

Both were fixed with focused regression coverage.

Second fresh-context blocker reviews: PASS, blockers none.

Review notes confirmed:

```text
- exact Sachima-only allowlist now rejects duplicates and non-Sachima policies;
- public observer boundary skips forged non-Sachima enabled policies before runtime calls;
- Gateway owns no runtime lifecycle and `gateway/run.py` is unchanged;
- guard maintenance is exact-path PE-1 allowlist maintenance only;
- docs keep operational config/restart/runtime approvals separate.
```

## Review Focus

Fresh-context review must block on:

- PE-1 being default-off;
- only exact `platform_allowlist: [sachima]` starts runtime observation;
- non-Sachima platforms do not start runtime even if configured;
- Gateway owns no runtime lifecycle;
- no production config writes or restart/reload behavior;
- no delivery mutation or ACK invention;
- no raw material in runtime requests, results, docs evidence, logs, or user-visible output.
