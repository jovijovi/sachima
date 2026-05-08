# FlowWeaver Phase 14 Live Gateway Observation Enablement Implementation Plan

> **For Hermes:** 狗哥 approved starting Phase 14 on 2026-05-08 after Phase 13 PR #48 was merged and canonical `feature/sachima-channel` was synchronized. This phase implements a pure default-off enablement request helper only. It must not enable live Gateway observation or wire production behavior.

**Goal:** Build the safe Gateway-side helper that turns an exact Phase 13 design report plus a default-off request policy into a review-only enablement request artifact.

**Architecture:** Phase 14 consumes the exact Phase 13 design report and emits a pure Gateway-side manual-review request artifact. The artifact preserves feature-flag, operator approval, approval-token, kill-switch, rollback, evidence, redaction, and verification contracts, but it keeps live observation disabled. It must not edit `gateway/run.py`, `run_agent.py`, `gateway/platforms/**`, production config, production registry, Gateway lifecycle, Temporal lifecycle, or real IM surfaces.

**Tech Stack:** Python, pytest, existing FlowWeaver Phase 12 Gateway helper, Phase 13 prototype design contract, docs/runbooks/dev_log. No production Gateway runtime, Temporal Worker, external service, socket, subprocess, Docker, platform adapter, or config write.

---

## Baseline

```text
Timestamp: 2026-05-08 09:55:42 CST +0800
Repository: jovijovi/sachima
Base branch: feature/sachima-channel
Base HEAD: 525b1131e204134be6619e69d5fa0c9ad220ee3e
Phase 14 branch: feat/flowweaver-phase14-live-gateway-observation-enablement-implementation
Phase 14 worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase14-live-gateway-observation-enablement-implementation
```

## Definition

Phase 14 means:

```text
exact Phase 13 enablement design report
  + static default-off request policy descriptor
  -> safe Phase 14 manual-review enablement request artifact
  -> verdict ready_for_manual_live_gateway_observation_enablement_request_review
  -> no live observation and no production side effects
```

The strongest allowed verdict is `ready_for_manual_live_gateway_observation_enablement_request_review`. It means only that a human/operator can review the request artifact. It does not authorize live enablement, production Gateway wiring, production config writes, Gateway restart, real IM effects, Temporal lifecycle, or production registry writes.

## Hard Boundaries

Phase 14 must not:

- modify `gateway/run.py`
- modify `run_agent.py`
- modify `gateway/platforms/**`
- write production config or registry files
- restart Gateway
- enable live Gateway observation
- send/edit/render/callback real IM content
- start or own Temporal client, Worker, WorkflowEnvironment, Docker, daemon, socket, subprocess, task queue, namespace, address, or service lifecycle
- accept or emit real approval-token material, raw prompt/tool/card/media/platform/Gateway/runtime/callback material, private IDs, credentials, or connection strings

## Planned Files

Create:

- `gateway/flowweaver_live_gateway_observation_enablement.py`
- `tests/gateway/test_flowweaver_live_gateway_observation_enablement.py`
- `docs/runbooks/flowweaver-live-gateway-observation-enablement-implementation.md`
- `docs/dev_log/2026-05-08-flowweaver-phase14-live-gateway-observation-enablement-implementation.md`
- this plan file

Modify only if existing invariant gates fail closed on the new Phase 14 files:

- `tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py`
- `tests/integration/test_flowweaver_phase5i_start_signature_parity.py`
- `tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py`
- `tests/integration/test_flowweaver_phase5k_runtime_control_surface.py`

## Step-by-Step Plan

1. Write RED tests first for Phase 14 import shape, exact Phase 13 consumption, success request artifact shape, and blocked report shape.
2. Run focused Phase 14 tests and confirm expected sanitized import-missing RED.
3. Implement the minimal pure Gateway helper.
4. Add exact validation for Phase 13 top-level fields, nested enablement design, artifact policy, rollback policy, approval list, verification matrix, runbook outline, derived design id, and safe digest.
5. Add fail-closed tests for missing/extra/reordered/mutated Phase 13 fields and unsafe raw/private/production values.
6. Add request-policy validation proving default-off/manual-review only: no approval-token material, no config/registry writes, no Gateway restart, no adapter calls, no Temporal lifecycle, no side effects.
7. Add source-surface tests proving no Gateway runtime, platform adapter, registry, Temporal, socket, subprocess, Docker, config write, logging, print, or raw serialization surface exists.
8. Add runbook and dev log documenting the default-off boundary, required separate approvals, verification results, and non-actions.
9. Patch only narrow changed-file allowlists if direct hermetic integration gates reject the Phase 14 files.
10. Run focused tests, Phase 11–14 regression, direct hermetic integration, `py_compile`, `ruff`, `git diff --check`, and custom safety guard.
11. Run fresh-context Codex blocker review focused on exact prior-phase contract validation and forbidden production surfaces.
12. Patch any blocker RED-first and rerun focused/regression/static/safety verification plus blocker-only review.
13. Commit, push, open PR against `feature/sachima-channel`, and report PR URL/check state.

## Verification Targets

Focused:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_enablement.py -q
```

Phase 11–14 regression:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_live_gateway_observation_enablement.py \
  tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py \
  tests/gateway/test_flowweaver_controlled_gateway_observation.py \
  tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py \
  -q
```

Direct hermetic chain:

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

Static:

```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m py_compile \
  gateway/flowweaver_live_gateway_observation_enablement.py \
  tests/gateway/test_flowweaver_live_gateway_observation_enablement.py

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m ruff check \
  gateway/flowweaver_live_gateway_observation_enablement.py \
  tests/gateway/test_flowweaver_live_gateway_observation_enablement.py

git diff --check
```

## Risks and Guardrails

- The word “enablement” is allowed only in review/request labels and required-approval labels; it must not imply active live observation.
- Approval-token handling is reference-only. Real token material must never be accepted or emitted.
- Forbidden-surface scanners must distinguish static approval boundaries from runtime calls.
- Prior-phase exactness must mirror the actual Phase 13 output, not a selective summary.
- If invariant allowlists need updating, add only exact Phase 14 files; do not weaken forbidden path checks.
- No Gateway restart is authorized by this phase.
