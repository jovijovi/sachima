# FlowWeaver Phase 17 — Guarded Live Gateway Observation Enablement Implementation Plan

> **For Hermes:** 狗哥 approved starting Phase 17 on 2026-05-08 after Phase 16 PR #53 was merged and canonical `feature/sachima-channel` was synchronized. Use TDD and keep the phase guarded/default-off.

**Goal:** Add a pure Phase 17 helper that turns the exact Phase 16 operator-decision artifact plus a default-off guarded-enablement policy into a sanitized guarded enablement implementation artifact.

**Architecture:** Implement one synchronous Gateway-side helper. It consumes an exact canonical Phase 16 decision artifact and a static guarded-enablement policy descriptor, then emits only sanitized labels, ids, digests, checks, required approvals, rollback labels, and stable error codes. It must not wire Gateway runtime behavior, call adapters, write production config, restart services, handle approval-token material, or start Temporal lifecycle.

**Tech Stack:** Python, pytest, existing FlowWeaver Gateway helper/test pattern.

---

### Task 1: Add Phase 17 RED contract tests

**Objective:** Specify the Phase 17 guarded enablement contract before production code exists.

**Files:**
- Create: `tests/gateway/test_flowweaver_live_gateway_observation_guarded_enablement.py`

**Steps:**
1. Write tests for narrow import behavior, keyword-only synchronous entrypoint, exact successful output shape, exact Phase 16 decision validation, default-off guarded-enablement policy validation, hostile subclass rejection, safe blocked output, and forbidden runtime-source surfaces.
2. Run:
   ```bash
   scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_guarded_enablement.py -q
   ```
3. Expected RED: missing `gateway.flowweaver_live_gateway_observation_guarded_enablement` module.

---

### Task 2: Implement the pure Phase 17 helper

**Objective:** Satisfy the RED tests with minimal side-effect-free code.

**Files:**
- Create: `gateway/flowweaver_live_gateway_observation_guarded_enablement.py`
- Test: `tests/gateway/test_flowweaver_live_gateway_observation_guarded_enablement.py`

**Steps:**
1. Add constants for Phase 17 version, report type, phase, guarded enablement mode, verification matrix, runbook outline, required separate approvals, and stable error codes.
2. Implement:
   ```text
   prepare_flowweaver_live_gateway_observation_guarded_enablement(*, phase16_decision, guarded_enablement_policy)
   ```
3. Validate only plain built-in `dict`, `list`, and `str` values where exactness matters.
4. Validate the exact canonical Phase 16 chain ids and recompute Phase 16 `decision_id` plus `operator_decision.safe_digest`.
5. Reject guarded enablement approval, live enablement, approval-token material, production/config/runtime/registry requests, raw material, and side effects.
6. Run focused tests and confirm GREEN.

---

### Task 3: Add operator runbook and development log

**Objective:** Document that Phase 17 is a guarded enablement contract artifact only, not live enablement.

**Files:**
- Create: `docs/runbooks/flowweaver-live-gateway-observation-guarded-enablement.md`
- Create: `docs/dev_log/2026-05-08-flowweaver-phase17-guarded-live-gateway-observation-enablement.md`

**Steps:**
1. Write the runbook with safe inputs, output contract, default-off boundary, required separate approvals, rollback, and verification commands.
2. Write the dev log with RED/GREEN evidence, boundaries, files changed, and verification status.
3. Keep docs free of raw payloads, private platform ids, credentials, connection strings, real approval-token material, raw exception text, and live Gateway observations.

---

### Task 4: Update hermetic integration allowlists

**Objective:** Preserve existing FlowWeaver changed-file invariant tests while allowing the exact Phase 17 pure helper files.

**Files:**
- Modify: `tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py`
- Modify: `tests/integration/test_flowweaver_phase5i_start_signature_parity.py`
- Modify: `tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py`
- Modify: `tests/integration/test_flowweaver_phase5k_runtime_control_surface.py`

**Steps:**
1. Add only these Phase 17 paths to each allowlist:
   ```text
   docs/plans/2026-05-08-flowweaver-phase17-guarded-live-gateway-observation-enablement.md
   docs/dev_log/2026-05-08-flowweaver-phase17-guarded-live-gateway-observation-enablement.md
   docs/runbooks/flowweaver-live-gateway-observation-guarded-enablement.md
   gateway/flowweaver_live_gateway_observation_guarded_enablement.py
   tests/gateway/test_flowweaver_live_gateway_observation_guarded_enablement.py
   ```
2. Do not add `gateway/run.py`, `run_agent.py`, `gateway/platforms/**`, production config, tools, registry, Temporal lifecycle, or platform adapters.

---

### Task 5: Verify and review

**Objective:** Prove Phase 17 is safe, bounded, and regression-free.

**Commands:**
```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_guarded_enablement.py -q

scripts/run_tests.sh \
  tests/gateway/test_flowweaver_live_gateway_observation_guarded_enablement.py \
  tests/gateway/test_flowweaver_live_gateway_observation_operator_decision.py \
  tests/gateway/test_flowweaver_live_gateway_observation_manual_review.py \
  tests/gateway/test_flowweaver_live_gateway_observation_enablement.py \
  tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py \
  tests/gateway/test_flowweaver_controlled_gateway_observation.py \
  tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py \
  -q

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

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m py_compile \
  gateway/flowweaver_live_gateway_observation_guarded_enablement.py \
  tests/gateway/test_flowweaver_live_gateway_observation_guarded_enablement.py

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m ruff check \
  gateway/flowweaver_live_gateway_observation_guarded_enablement.py \
  tests/gateway/test_flowweaver_live_gateway_observation_guarded_enablement.py

git diff --check
```

Also run a deterministic changed-file/forbidden-surface safety guard and an independent blocker-only review before committing.
