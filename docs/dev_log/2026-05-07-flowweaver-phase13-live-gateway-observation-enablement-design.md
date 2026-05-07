# FlowWeaver Phase 13 — Live Gateway Observation Enablement Design Gate Dev Log

## Task Background

狗哥 approved continuing to Phase 13 after Phase 12 PR #47 was merged and local canonical `feature/sachima-channel` was synchronized.

```text
Base branch: feature/sachima-channel
Base merge commit: 041bdfcbfdaa9ef276fe1f21892af46795785e5e
Implementation branch: feat/flowweaver-phase13-live-gateway-observation-enablement-design
Implementation worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase13-live-gateway-observation-enablement-design
Started at: 2026-05-07 23:28:12 CST +0800
```

## Implementation Target

Phase 13 defines the next default-off design gate after Phase 12:

```text
exact Phase 12 safe observation hook report
  + static enablement policy descriptor
  + static observation evidence policy descriptor
  + artifact/log/redaction policy
  + rollback/kill-switch policy
  -> safe Phase 13 enablement design report
  -> ready_for_live_gateway_observation_enablement_implementation
```

This remains pure and side-effect-free. It does not wire live Gateway behavior.

## Hard Boundaries Preserved

```text
No gateway/run.py changes.
No run_agent.py changes.
No gateway/platforms/** changes.
No production config writes.
No production tool registry writes.
No Gateway restart.
No real send/edit/render/callback.
No live Gateway observation enablement.
No Temporal client, Worker, WorkflowEnvironment, Docker, daemon, socket, subprocess, task queue, namespace, address, or service lifecycle.
No payload-carrying Temporal Signals.
No raw prompt/tool/card/media/platform/Gateway/runtime/callback material in reports or artifacts.
```

## Files Added

```text
docs/plans/2026-05-07-flowweaver-phase13-live-gateway-observation-enablement-design.md
docs/runbooks/flowweaver-live-gateway-observation-enablement-design.md
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/live_gateway_observation_enablement_design.py
tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py
```

## TDD Evidence

### RED

Created `tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py` first, defining import/default-off boundaries, exact Phase 12 evidence consumption, safe design projection, descriptor validation, no-live/no-raw constraints, and source forbidden-surface scans.

```text
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py -q
33 failed
Expected RED: missing Phase 13 design module import (sanitized import-missing failure)
```

### GREEN

Added `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/live_gateway_observation_enablement_design.py` as a pure synchronous prototype-side design gate. Initial GREEN attempts exposed scanner handling around approval labels and descriptor fields (`approvals`, `platform_payloads_allowed`, `raw_material_allowed`). Patched the scanner to distinguish static policy/approval metadata from leak surfaces while still rejecting unsafe raw values in evidence inputs.

```text
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py -q
33 passed in 0.41s
```

## Implementation Notes

- The module imports only `hashlib.sha256`.
- The entrypoint is synchronous and keyword-only:

```text
design_flowweaver_live_gateway_observation_enablement(...)
```

- Success output uses only stable labels, checks, digests, approval labels, and stable error codes.
- Blocked output contains only safe fields:

```text
type
version
ok = False
verdict = blocked
phase
error_code
side_effects = []
```

- The helper consumes exact Phase 12 report shape and rejects missing fields, extra production fields, reordered approval lists, mutated nested observation values, side effects, unsafe raw material, and private platform-like identifiers.
- The helper accepts static descriptors only. It rejects live/default-on requests, config/registry writes, Gateway restart approval leakage, adapter calls, Temporal lifecycle, raw material, and side effects.

## Verification Results

Initial focused verification:

```text
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py -q
33 passed in 0.41s
```

The direct hermetic integration chain initially failed on existing Phase 5H/5I/5J/5K changed-file invariant allowlists. Root cause: Phase 13 intentionally adds a new pure prototype design module, focused prototype tests, runbook, plan, and dev log. Patched only those allowlists for the exact Phase 13 files; no forbidden `gateway/run.py`, `run_agent.py`, `gateway/platforms/**`, config, registry, or Temporal lifecycle paths were added.

Verification after narrow allowlist patch:

```text
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py \
  tests/gateway/test_flowweaver_controlled_gateway_observation.py \
  tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py \
  -q
125 passed in 0.49s

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
38 passed in 1.81s

py_compile: PASS
ruff: PASS
git diff --check: PASS
FINAL_PHASE13_ENABLEMENT_DESIGN_SAFETY_GUARD: PASS
```

## Codex Fresh-Context Review

Initial Codex blocker review returned BLOCK:

```text
VERDICT: BLOCK

BLOCKERS:
- Phase 13 accepted mutated nested Phase 12 values as ok=True: candidate touchpoints, allowed surfaces, shadow surfaces, publication/ack/visible counts, and stable error codes were not exact enough.
- Phase 13 accepted mutated Phase 12 observation id and safe digest values that only matched prefix/shape.
- Phase 13 did not reject a lifecycle-shaped worker marker in stable error codes.
- Dev log included raw import exception text in RED evidence.
```

Fix applied:

- Added RED regression tests for exact Phase 12 nested values, observation id consistency, safe digest consistency, stable-code exactness, and lifecycle-shaped worker markers.
- Tightened Phase 13 validation to require exact Phase 12 nested values, recompute Phase 12 observation id, recompute Phase 12 safe digest, and preserve exact empty Phase 12 stable error codes.
- Added worker to runtime-lifecycle marker rejection for real evidence fields while keeping policy metadata exceptions bounded.
- Sanitized plan/dev-log RED evidence to avoid raw exception text.
- Re-ran focused, regression, direct integration, static, diff, and safety guard verification.

Final verification after Codex blocker fix:

```text
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py -q
43 passed in 0.42s

scripts/run_tests.sh tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py \
  tests/gateway/test_flowweaver_controlled_gateway_observation.py \
  tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py \
  -q
135 passed in 0.51s

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
38 passed in 1.80s

py_compile: PASS
ruff: PASS
git diff --check: PASS
FINAL_PHASE13_ENABLEMENT_DESIGN_SAFETY_GUARD: PASS
```

Codex blocker-only re-review returned PASS:

```text
VERDICT: PASS

BLOCKERS:
- none
```
