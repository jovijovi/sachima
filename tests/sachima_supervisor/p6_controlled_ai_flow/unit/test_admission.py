"""P6-A admission gate (FR1, Gate 1 — merge-blocking, no Temporal).

The outer p6_* admission protects the default-off boundary: disabled, mismatched
approval, unmet preconditions, and a missing operator gate must each return a
stable p6_* code and perform **zero** executor / Temporal calls. The inner
runtime_* codes are never replaced by the outer p6_* family.
"""

from __future__ import annotations

import pytest

from sachima_supervisor.p6_controlled_ai_flow import (
    P6_APPROVAL_MISMATCH,
    P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN,
    P6_EXECUTION_DISABLED,
    P6_GATE_BLOCKED,
    P6_PRECONDITION_UNMET,
    P6_STABLE_CODES,
    P6ControlledAiFlowSession,
    evaluate_p6_admission,
)

from tests.sachima_supervisor.p6_controlled_ai_flow._support import (
    SPEC,
    CountingExecutor,
    DeterministicFakeStepExecutor,
    run_request,
    step_requests_in_order,
)
from sachima_supervisor.ai_flow_store import AiFlowRunStore


_DEFAULT_EXECUTOR = object()


def _session(*, enabled=True, approval_token=None, operator_gate=True, executor=_DEFAULT_EXECUTOR, spec=SPEC, store=None):
    return P6ControlledAiFlowSession(
        spec=spec,
        store=AiFlowRunStore() if store is None else store,
        executor=(
            CountingExecutor(DeterministicFakeStepExecutor())
            if executor is _DEFAULT_EXECUTOR
            else executor
        ),
        enabled=enabled,
        approval_token=(
            P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN if approval_token is None else approval_token
        ),
        operator_gate=operator_gate,
    )


def test_token_is_the_exact_operator_phrase():
    assert P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN == (
        "approve_agent_run_supervisor_sachima_p6a_temporal_backed_controlled_ai_flow_execution_"
        "implementation_controlled_deterministic_or_injected_fake_steps_only_default_off_"
        "no_real_agent_execution_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_"
        "no_real_delivery"
    )


def test_p6_codes_are_additive_and_distinct_from_runtime_codes():
    from sachima_supervisor.p5_temporal import contracts as C

    assert P6_STABLE_CODES == {
        P6_EXECUTION_DISABLED,
        P6_APPROVAL_MISMATCH,
        P6_PRECONDITION_UNMET,
        P6_GATE_BLOCKED,
    }
    # p6_* never collapses or replaces the inner runtime_* family.
    assert P6_STABLE_CODES.isdisjoint(C.STABLE_CODES)
    assert all(code.startswith("p6_") for code in P6_STABLE_CODES)


def test_disabled_returns_p6_execution_disabled_and_zero_calls():
    counter = CountingExecutor(DeterministicFakeStepExecutor())
    session = _session(enabled=False, executor=counter)
    adm = session.admit()
    assert adm.ok is False and adm.error_code == P6_EXECUTION_DISABLED
    outcome = session.run_linear(run_request(), step_requests_in_order())
    assert outcome.admitted is False
    assert outcome.admission_code == P6_EXECUTION_DISABLED
    assert outcome.final_verdict is None
    assert counter.total_calls == 0


def test_approval_mismatch_returns_p6_approval_mismatch_and_zero_calls():
    counter = CountingExecutor(DeterministicFakeStepExecutor())
    session = _session(approval_token="not_the_token", executor=counter)
    adm = session.admit()
    assert adm.ok is False and adm.error_code == P6_APPROVAL_MISMATCH
    outcome = session.run_linear(run_request(), step_requests_in_order())
    assert outcome.admission_code == P6_APPROVAL_MISMATCH
    assert counter.total_calls == 0


def test_disabled_takes_precedence_over_mismatch():
    # Both wrong: the disabled check is evaluated first (stable ordering).
    session = _session(enabled=False, approval_token="not_the_token")
    assert session.admit().error_code == P6_EXECUTION_DISABLED


def test_precondition_unmet_when_executor_not_armed():
    disarmed = CountingExecutor(DeterministicFakeStepExecutor(enabled=False))
    session = _session(executor=disarmed)
    adm = session.admit()
    assert adm.ok is False and adm.error_code == P6_PRECONDITION_UNMET
    outcome = session.run_linear(run_request(), step_requests_in_order())
    assert outcome.admission_code == P6_PRECONDITION_UNMET
    assert disarmed.total_calls == 0


@pytest.mark.parametrize("bad", ["store", "spec", "executor"])
def test_precondition_unmet_when_required_surface_missing(bad):
    counter = CountingExecutor(DeterministicFakeStepExecutor())
    kwargs = dict(executor=counter)
    if bad == "store":
        kwargs["store"] = object()
    elif bad == "spec":
        kwargs["spec"] = object()
    elif bad == "executor":
        kwargs["executor"] = None
    session = _session(**kwargs)
    assert session.admit().error_code == P6_PRECONDITION_UNMET
    assert counter.total_calls == 0


def test_gate_blocked_when_operator_gate_not_granted():
    counter = CountingExecutor(DeterministicFakeStepExecutor())
    session = _session(operator_gate=False, executor=counter)
    adm = session.admit()
    assert adm.ok is False and adm.error_code == P6_GATE_BLOCKED
    outcome = session.run_linear(run_request(), step_requests_in_order())
    assert outcome.admission_code == P6_GATE_BLOCKED
    assert counter.total_calls == 0


def test_admission_failure_evidence_is_sanitized_and_carries_the_p6_code():
    from sachima_supervisor.p5_temporal import contracts as C

    session = _session(enabled=False)
    outcome = session.run_linear(run_request(), step_requests_in_order())
    assert outcome.evidence is not None
    assert C.scan_projection_for_leak(outcome.evidence) is None
    assert P6_EXECUTION_DISABLED in outcome.error_codes
    assert outcome.evidence["p6_admission"]["admission_code"] == P6_EXECUTION_DISABLED


def test_pure_evaluate_helper_makes_no_executor_calls():
    counter = CountingExecutor(DeterministicFakeStepExecutor())
    adm = evaluate_p6_admission(
        enabled=False,
        approval_token=P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN,
        spec=SPEC,
        store=AiFlowRunStore(),
        executor=counter,
        operator_gate=True,
    )
    assert adm.error_code == P6_EXECUTION_DISABLED
    assert counter.total_calls == 0


def test_admitted_session_actually_executes_when_fully_approved():
    counter = CountingExecutor(DeterministicFakeStepExecutor())
    session = _session(executor=counter)
    assert session.admit().ok is True
    outcome = session.run_linear(run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok")
    assert outcome.admitted is True
    assert outcome.final_verdict == "succeeded"
    assert counter.execute_calls == 3
