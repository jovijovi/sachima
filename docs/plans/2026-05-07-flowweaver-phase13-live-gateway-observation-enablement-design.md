# FlowWeaver Phase 13 Live Gateway Observation Enablement Design Gate Plan

> **For Hermes:** 狗哥 approved continuing to Phase 13 on 2026-05-07 after Phase 12 PR #47 was merged and canonical `feature/sachima-channel` was synchronized. This phase is a design gate only. It must not enable live Gateway observation or wire production behavior.

**Goal:** Define a safe, default-off design gate for how live Gateway observation could later be enabled, using exact Phase 12 safe observation-hook evidence while keeping production effects behind separate approvals.

**Architecture:** Phase 13 consumes the exact Phase 12 safe hook report and emits a pure prototype-side design report. It describes feature flag, operator approval, kill switch, rollback, evidence, redaction, and verification contracts for a later implementation/enablement phase. It must not edit `gateway/run.py`, `run_agent.py`, `gateway/platforms/**`, production config, production registry, Gateway lifecycle, Temporal lifecycle, or real IM surfaces.

**Tech Stack:** Python, pytest, existing FlowWeaver Phase 11 prototype design contract, Phase 12 Gateway safe projection helper, docs/runbooks/dev_log. No production Gateway runtime, Temporal Worker, external service, socket, subprocess, Docker, platform adapter, or config write.

---

## Baseline

```text
Timestamp: 2026-05-07 23:28:12 CST +0800
Repository: jovijovi/sachima
Base branch: feature/sachima-channel
Base HEAD: 041bdfcbfdaa9ef276fe1f21892af46795785e5e
Phase 13 branch: feat/flowweaver-phase13-live-gateway-observation-enablement-design
Phase 13 worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase13-live-gateway-observation-enablement-design
```

## Definition

Phase 13 means:

```text
exact Phase 12 safe observation hook report
  + static enablement policy descriptor
  + static observation evidence policy descriptor
  + static rollback/kill-switch policy descriptor
  + artifact/log/redaction policy
  -> safe Phase 13 enablement design report
  -> verdict ready_for_live_gateway_observation_enablement_implementation
  -> no live observation and no production side effects
```

The strongest allowed verdict is `ready_for_live_gateway_observation_enablement_implementation`. It means only that a later implementation PR may build the default-off enablement mechanism. It does not authorize live enablement, production Gateway wiring, production config writes, Gateway restart, real IM effects, Temporal lifecycle, or production registry writes.

## Hard Boundaries

Phase 13 must not:

- modify `gateway/run.py`
- modify `run_agent.py`
- modify `gateway/platforms/**`
- write production config or registry files
- restart Gateway
- enable live Gateway observation
- send/edit/render/callback real IM content
- start or own Temporal client, Worker, WorkflowEnvironment, Docker, daemon, socket, subprocess, task queue, namespace, address, or service lifecycle
- emit raw prompt/tool/card/media/platform/Gateway/runtime/callback material, private IDs, credentials, or connection strings

## Planned Files

Create:

- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/live_gateway_observation_enablement_design.py`
- `tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py`
- `docs/runbooks/flowweaver-live-gateway-observation-enablement-design.md`
- `docs/dev_log/2026-05-07-flowweaver-phase13-live-gateway-observation-enablement-design.md`
- this plan file

Modify only if existing invariant gates fail closed on the new Phase 13 files:

- `tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py`
- `tests/integration/test_flowweaver_phase5i_start_signature_parity.py`
- `tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py`
- `tests/integration/test_flowweaver_phase5k_runtime_control_surface.py`

## Step-by-Step Plan

1. Write RED tests first for Phase 13 import shape, exact Phase 12 consumption, success report shape, and blocked report shape.
2. Run focused Phase 13 tests and confirm expected sanitized import-missing RED.
3. Implement the minimal pure prototype module.
4. Add exact validation for Phase 12 top-level fields, nested observation, artifact policy, approval list, verification matrix, and runbook outline.
5. Add fail-closed tests for missing/extra/reordered/duplicated/mutated Phase 12 fields and unsafe raw/private/production values.
6. Add source-surface tests proving no Gateway runtime, platform adapter, registry, Temporal, socket, subprocess, Docker, config write, logging, print, or raw serialization surface exists.
7. Add runbook and dev log documenting the default-off boundary, required separate approvals, verification results, and non-actions.
8. Patch only narrow changed-file allowlists if direct hermetic integration gates reject the Phase 13 files.
9. Run focused tests, Phase 11–13 regression, direct hermetic integration, `py_compile`, `ruff`, `git diff --check`, and custom safety guard.
10. Run fresh-context Codex blocker review focused on exact prior-phase contract validation and forbidden production surfaces.
11. Patch any blocker RED-first and rerun focused/regression/static/safety verification plus blocker-only review.
12. Commit, push, open PR against `feature/sachima-channel`, and report PR URL/check state.

## Verification Targets

Focused:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py -q
```

Phase 11–13 regression:

```bash
scripts/run_tests.sh \
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
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/live_gateway_observation_enablement_design.py \
  tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m ruff check \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/live_gateway_observation_enablement_design.py \
  tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py

git diff --check
```

## Risks and Guardrails

- The word “live” is allowed only in policy/design labels and required-approval labels; it must not imply active enablement.
- Forbidden-surface scanners must distinguish static approval boundaries from runtime calls.
- Prior-phase exactness must mirror the actual Phase 12 output, not a selective summary.
- If invariant allowlists need updating, add only exact Phase 13 files; do not weaken forbidden path checks.
- No Gateway restart is authorized by this phase.
