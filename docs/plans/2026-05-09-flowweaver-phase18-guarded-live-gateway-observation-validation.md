# FlowWeaver Phase 18 — Guarded Live Gateway Observation Validation Implementation Plan

> **For Hermes:** 狗哥 approved starting Phase 18 on 2026-05-09 after Phase 17 PR #54 was merged and canonical `feature/sachima-channel` was synchronized. Use TDD and keep the phase guarded/default-off. Codex read-only scope review returned PASS: Phase 18 must remain pure validation/review and must not perform live enablement.

**Goal:** Add a pure Phase 18 helper that turns the exact Phase 17 guarded-enablement artifact plus a default-off guarded-validation policy into a sanitized guarded validation artifact.

**Architecture:** Implement one synchronous Gateway-side helper. It consumes an exact canonical Phase 17 guarded-enablement artifact and a static guarded-validation policy descriptor, then emits only sanitized labels, ids, digests, checks, required approvals, rollback labels, and stable error codes. Its strongest verdict means only that a separate live-enablement approval request may be prepared; it must not approve live enablement, wire Gateway runtime behavior, call adapters, write production config, restart services, handle approval-token material, or start Temporal lifecycle.

**Tech Stack:** Python, pytest, existing FlowWeaver Gateway helper/test pattern.

---

## Baseline

```text
Repository: jovijovi/sachima
Base branch: feature/sachima-channel
Base HEAD: 40d45a1dcb76cd5465d8171b2bf69ddf543fb514
Phase 18 branch: feat/flowweaver-phase18-guarded-live-gateway-observation-validation
Phase 18 worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase18-guarded-live-gateway-observation-validation
```

## Definition

Phase 18 means:

```text
exact Phase 17 guarded-enablement artifact
  + static default-off guarded-validation policy descriptor
  -> safe Phase 18 guarded validation artifact
  -> ready_for_live_gateway_observation_enablement_separate_approval_request
  -> no live observation and no production side effects
```

The strongest allowed verdict is `ready_for_live_gateway_observation_enablement_separate_approval_request`. It means only that a later phase may request explicit separate approval for live enablement. It does not authorize live enablement, production Gateway wiring, production config writes, Gateway restart, real IM effects, Temporal lifecycle, or production registry writes.

## Hard Boundaries

Phase 18 must not:

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

- `gateway/flowweaver_live_gateway_observation_guarded_validation.py`
- `tests/gateway/test_flowweaver_live_gateway_observation_guarded_validation.py`
- `docs/runbooks/flowweaver-live-gateway-observation-guarded-validation.md`
- `docs/dev_log/2026-05-09-flowweaver-phase18-guarded-live-gateway-observation-validation.md`
- this plan file

Modify only exact changed-file allowlists:

- `tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py`
- `tests/integration/test_flowweaver_phase5i_start_signature_parity.py`
- `tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py`
- `tests/integration/test_flowweaver_phase5k_runtime_control_surface.py`

## Step-by-Step Plan

1. Run read-only Codex architecture review against the Phase 17 artifacts to confirm Phase 18 scope and boundaries.
2. Write RED tests first for Phase 18 import shape, exact Phase 17 consumption, success validation artifact shape, blocked report shape, hostile subclass rejection, integer boolean impersonator rejection, and forbidden runtime-source surfaces.
3. Run focused Phase 18 tests and confirm expected import-missing RED.
4. Implement the minimal pure Gateway helper.
5. Add exact validation for Phase 17 top-level fields, nested guarded-enablement fields, artifact policy, rollback policy, approval list, verification matrix, runbook outline, derived enablement id, and safe digest.
6. Add guarded-validation policy validation proving default-off/validation-only behavior: no approval-token material, no config/registry writes, no Gateway restart, no adapter calls, no Temporal lifecycle, no live observation, and no side effects.
7. Add source-surface tests proving no Gateway runtime, platform adapter, registry, Temporal, socket, subprocess, Docker, config write, logging, print, or raw serialization surface exists.
8. Add runbook and dev log documenting the default-off validation boundary, required separate approvals, verification results, and non-actions.
9. Patch only narrow changed-file allowlists if direct hermetic integration gates reject the Phase 18 files.
10. Run focused tests, Phase 11–18 regression, direct hermetic integration, `py_compile`, `ruff`, `git diff --check`, and custom safety guard.
11. Run fresh-context Codex blocker review focused on exact prior-phase contract validation and forbidden production surfaces.
12. Patch any blocker RED-first and rerun focused/regression/static/safety verification plus blocker-only review.
13. Commit, push, open PR against `feature/sachima-channel`, monitor CI, and merge if green per approved flow.

## Verification Targets

Focused:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_guarded_validation.py -q
```

Phase 11–18 regression:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_live_gateway_observation_guarded_validation.py \
  tests/gateway/test_flowweaver_live_gateway_observation_guarded_enablement.py \
  tests/gateway/test_flowweaver_live_gateway_observation_operator_decision.py \
  tests/gateway/test_flowweaver_live_gateway_observation_manual_review.py \
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
  gateway/flowweaver_live_gateway_observation_guarded_validation.py \
  tests/gateway/test_flowweaver_live_gateway_observation_guarded_validation.py

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m ruff check \
  gateway/flowweaver_live_gateway_observation_guarded_validation.py \
  tests/gateway/test_flowweaver_live_gateway_observation_guarded_validation.py

git diff --check
```

## Risks and Guardrails

- The word “ready” is allowed only for a separate future approval request; it must not imply active live observation.
- Phase 18 removes the Phase 17 validation approval from the remaining approval list only because this artifact is the validation gate; live enablement still remains separately required.
- Approval-token handling is reference-only. Real token material must never be accepted or emitted.
- Prior-phase exactness must mirror the actual Phase 17 output, not a selective summary.
- If invariant allowlists need updating, add only exact Phase 18 files; do not weaken forbidden path checks.
- No Gateway restart is authorized by this phase.
