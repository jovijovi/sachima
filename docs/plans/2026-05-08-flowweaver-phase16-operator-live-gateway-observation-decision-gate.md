# FlowWeaver Phase 16 — Operator Live Gateway Observation Decision Gate Implementation Plan

> **For Hermes:** 狗哥 approved starting Phase 16 on 2026-05-08 after Phase 15 PR #52 was merged and canonical `feature/sachima-channel` was synchronized. Use TDD and keep the phase pure/default-off.

**Goal:** Add a pure Phase 16 helper that turns the Phase 15 manual-review artifact plus a default-off operator-decision policy into a safe operator-decision gate artifact, without enabling live Gateway observation.

**Architecture:** Implement one synchronous Gateway-side helper that consumes an exact Phase 15 review report plus a static default-off operator-decision policy descriptor. The helper emits only sanitized labels, ids, digests, checks, approval refs, rollback refs, and stable error codes. It must not wire Gateway runtime behavior, call adapters, write production config, restart services, handle real approval-token material, or start any Temporal lifecycle.

**Tech Stack:** Python, pytest, existing FlowWeaver Gateway helper/test pattern.

---

### Task 1: Add Phase 16 RED contract tests

**Objective:** Specify the Phase 16 contract before production code exists.

**Files:**
- Create: `tests/gateway/test_flowweaver_live_gateway_observation_operator_decision.py`

**Steps:**
1. Write tests for narrow import behavior, keyword-only synchronous entrypoint, exact successful output shape, exact Phase 15 review validation, default-off operator-decision policy validation, hostile subclass rejection, safe blocked output, and forbidden runtime-source surfaces.
2. Run:
   ```bash
   scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_operator_decision.py -q
   ```
3. Expected RED: missing `gateway.flowweaver_live_gateway_observation_operator_decision` module.

---

### Task 2: Implement the pure Phase 16 helper

**Objective:** Satisfy the RED tests with minimal side-effect-free code.

**Files:**
- Create: `gateway/flowweaver_live_gateway_observation_operator_decision.py`
- Test: `tests/gateway/test_flowweaver_live_gateway_observation_operator_decision.py`

**Steps:**
1. Add constants for the Phase 16 version, report type, phase, decision mode, verification matrix, runbook outline, required separate approvals, and stable error codes.
2. Implement:
   ```text
   prepare_flowweaver_live_gateway_observation_operator_decision(*, phase15_review, operator_decision_policy)
   ```
3. Validate only plain built-in `dict`, `list`, and `str` values where exactness matters.
4. Reject operator-decision approval, live/production/config/runtime/material requests with stable blocked reports.
5. Run the focused tests and confirm GREEN.

---

### Task 3: Add operator runbook and development log

**Objective:** Document that Phase 16 is an operator-decision gate only, not live enablement.

**Files:**
- Create: `docs/runbooks/flowweaver-live-gateway-observation-operator-decision.md`
- Create: `docs/dev_log/2026-05-08-flowweaver-phase16-operator-live-gateway-observation-decision-gate.md`

**Steps:**
1. Write the runbook with safe inputs, output contract, default-off boundary, required separate approvals, and verification commands.
2. Write the dev log with RED/GREEN evidence, safety boundaries, files changed, and verification status.
3. Keep docs free of raw payloads, private platform ids, credentials, connection strings, real approval-token material, raw exception text, and live Gateway observations.

---

### Task 4: Update hermetic integration allowlists

**Objective:** Preserve existing FlowWeaver changed-file invariant tests while allowing the exact Phase 16 pure helper files.

**Files:**
- Modify: `tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py`
- Modify: `tests/integration/test_flowweaver_phase5i_start_signature_parity.py`
- Modify: `tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py`
- Modify: `tests/integration/test_flowweaver_phase5k_runtime_control_surface.py`

**Steps:**
1. Add only these Phase 16 paths to each allowlist:
   ```text
   docs/plans/2026-05-08-flowweaver-phase16-operator-live-gateway-observation-decision-gate.md
   docs/dev_log/2026-05-08-flowweaver-phase16-operator-live-gateway-observation-decision-gate.md
   docs/runbooks/flowweaver-live-gateway-observation-operator-decision.md
   gateway/flowweaver_live_gateway_observation_operator_decision.py
   tests/gateway/test_flowweaver_live_gateway_observation_operator_decision.py
   ```
2. Do not add `gateway/run.py`, `run_agent.py`, `gateway/platforms/**`, production config, tools, registry, Temporal lifecycle, or platform adapters.

---

### Task 5: Verify and review

**Objective:** Prove the Phase 16 implementation is safe and bounded.

**Commands:**
```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_operator_decision.py -q

scripts/run_tests.sh \
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
  gateway/flowweaver_live_gateway_observation_operator_decision.py \
  tests/gateway/test_flowweaver_live_gateway_observation_operator_decision.py

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m ruff check \
  gateway/flowweaver_live_gateway_observation_operator_decision.py \
  tests/gateway/test_flowweaver_live_gateway_observation_operator_decision.py

git diff --check
```

Also run an independent blocker-only review before committing.
