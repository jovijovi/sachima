# FlowWeaver Phase 14 — Live Gateway Observation Enablement Implementation Dev Log

## Task Background

狗哥 approved starting Phase 14 after Phase 13 PR #48 was merged and local canonical `feature/sachima-channel` was synchronized.

```text
Base branch: feature/sachima-channel
Base merge commit: 525b1131e204134be6619e69d5fa0c9ad220ee3e
Implementation branch: feat/flowweaver-phase14-live-gateway-observation-enablement-implementation
Implementation worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase14-live-gateway-observation-enablement-implementation
Started at: 2026-05-08 09:55:42 CST +0800
```

## Implementation Target

Phase 14 implements the next default-off helper after Phase 13:

```text
exact Phase 13 enablement design report
  + static default-off request policy descriptor
  -> safe Phase 14 manual-review enablement request artifact
  -> ready_for_manual_live_gateway_observation_enablement_request_review
```

This remains pure and side-effect-free. It does not wire or enable live Gateway behavior.

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
No real approval-token material accepted or emitted.
No Temporal client, Worker, WorkflowEnvironment, Docker, daemon, socket, subprocess, task queue, namespace, address, or service lifecycle.
No payload-carrying Temporal Signals.
No raw prompt/tool/card/media/platform/Gateway/runtime/callback material in reports or artifacts.
```

## Files Added

```text
docs/plans/2026-05-08-flowweaver-phase14-live-gateway-observation-enablement-implementation.md
docs/runbooks/flowweaver-live-gateway-observation-enablement-implementation.md
gateway/flowweaver_live_gateway_observation_enablement.py
tests/gateway/test_flowweaver_live_gateway_observation_enablement.py
```

## TDD Evidence

### RED

Created `tests/gateway/test_flowweaver_live_gateway_observation_enablement.py` first, defining import/default-off boundaries, exact Phase 13 design consumption, safe manual-review request projection, request-policy validation, no-live/no-raw constraints, and source forbidden-surface scans.

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_enablement.py -q
37 failed
Expected RED: missing Phase 14 Gateway helper module import (sanitized import-missing failure)
```

### GREEN

Added `gateway/flowweaver_live_gateway_observation_enablement.py` as a pure synchronous Gateway-side helper. Initial GREEN attempts exposed two useful guardrail refinements:

- The safe output must not contain verdict-like strings such as `observation_enabled`, even as false field names; the request artifact now uses `live_observation_active = False` instead.
- Static descriptor values such as `log_policy` need exact validation, not raw-value serialization into the artifact.
- Source-surface scans reject literal production registry markers; static marker strings were split without adding runtime behavior.

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_enablement.py -q
37 passed in 0.42s
```

## Implementation Notes

- The module imports only `hashlib.sha256`.
- The entrypoint is synchronous and keyword-only:

```text
prepare_flowweaver_live_gateway_observation_enablement_request(...)
```

- Success output uses only stable labels, checks, short safe digests, approval labels, kill-switch labels, rollback labels, and stable error codes.
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

- The helper consumes exact Phase 13 report shape and rejects missing fields, extra production fields, reordered approval lists, mutated nested enablement values, mutated derived ids/digests, side effects, unsafe raw material, and private platform-like identifiers.
- The helper accepts a static request policy only. It rejects default-on or requested-on states, approval-token material, config/registry writes, Gateway restart, adapter calls, Temporal lifecycle, raw material, and side effects.

## Verification Results

Initial focused verification:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_enablement.py -q
37 passed in 0.42s
```

The direct hermetic integration chain initially failed on existing Phase 5H/5I/5J/5K changed-file invariant allowlists. Root cause: Phase 14 intentionally adds a new pure Gateway helper, focused Gateway tests, runbook, plan, and dev log. Patched only those allowlists for the exact Phase 14 files; no forbidden `gateway/run.py`, `run_agent.py`, `gateway/platforms/**`, config, registry, or Temporal lifecycle paths were added.

Verification after narrow allowlist patch:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_enablement.py \
  tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py \
  tests/gateway/test_flowweaver_controlled_gateway_observation.py \
  tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py \
  -q
172 passed in 0.56s

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
FINAL_PHASE14_ENABLEMENT_IMPLEMENTATION_SAFETY_GUARD: PASS changed_files=9 impl_files=1
```

## Codex Fresh-Context Review

Initial Codex blocker review returned BLOCK:

```text
VERDICT: BLOCK

BLOCKERS:
- Phase 13 artifact-policy exactness was bypassable: descriptor lists such as allowed_fields and forbidden_material could be replaced by hostile list subclasses whose equality lied, allowing a non-exact unsafe Phase 13 report to return the success verdict.
```

Fix applied:

- Added a RED regression test using a hostile list subclass for Phase 13 artifact-policy lists.
- Added a RED regression test using a hostile string subclass for Phase 13 artifact-policy `log_policy`.
- Added a regression probe for hostile side-effect list subclasses.
- Tightened Phase 14 validation to convert artifact-policy `artifact_mode`, `allowed_fields`, `retention`, `log_policy`, and `forbidden_material` through exact plain string / plain-string-list validation before comparing.
- Updated this dev log so verification status matches the actual gate outputs.

Verification after Codex blocker fix:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_enablement.py::test_phase14_rejects_hostile_phase13_artifact_policy_list_subclasses \
  tests/gateway/test_flowweaver_live_gateway_observation_enablement.py::test_phase14_rejects_hostile_phase13_artifact_policy_string_subclasses \
  tests/gateway/test_flowweaver_live_gateway_observation_enablement.py::test_phase14_rejects_hostile_side_effect_list_subclasses \
  -q
3 passed in 0.39s

scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_enablement.py -q
40 passed in 0.44s

scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_enablement.py \
  tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py \
  tests/gateway/test_flowweaver_controlled_gateway_observation.py \
  tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py \
  -q
175 passed in 0.56s

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
FINAL_PHASE14_ENABLEMENT_IMPLEMENTATION_SAFETY_GUARD: PASS changed_files=9 impl_files=1
```

Codex blocker-only re-review returned PASS:

```text
VERDICT: PASS

BLOCKERS:
- none

NOTES:
- Fresh hostile subclass probe returned invalid_phase13_report for artifact-policy list and string subclasses.
- git diff --check passed.
```
