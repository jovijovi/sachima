"""P6-A composition oracle (FR2/FR3, Gate 2/3 — no Temporal).

Drives the **unmodified** WP4 entrypoints
(``create_workflow_run`` -> ``step_workflow_run(executor=…)`` ->
``summarize_workflow_run``) through the P6-A composition with the in-process
``P5LocalOfflineRuntimeAdapter`` oracle and a deterministic fake. Proves a small
linear graph succeeds end-to-end, that outcomes are substitutable across
executors, and that WP4 invariants (gates, claim-check propagation, terminal
gate, idempotent replay) are not weakened by the composition.
"""

from __future__ import annotations

import pytest

from sachima_supervisor.ai_flow_store import AiFlowRunStore
from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p6_controlled_ai_flow import (
    P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN,
    P6ControlledAiFlowError,
    P6ControlledAiFlowSession,
)

from tests.sachima_supervisor.p6_controlled_ai_flow._support import (
    SPEC,
    STEP_ORDER,
    DeterministicFakeStepExecutor,
    make_local_adapter,
    run_request,
    step_request,
    step_requests_in_order,
)


def _session(executor):
    return P6ControlledAiFlowSession(
        spec=SPEC,
        store=AiFlowRunStore(),
        executor=executor,
        enabled=True,
        approval_token=P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN,
        operator_gate=True,
    )


def test_linear_flow_succeeds_through_local_adapter():
    adapter = make_local_adapter()
    session = _session(adapter)
    outcome = session.run_linear(
        run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok"
    )
    assert outcome.admitted is True
    assert outcome.ok is True
    assert outcome.final_verdict == "succeeded"
    assert outcome.active_run_watch is False
    # The Temporal-substitute oracle really ran exactly three steps.
    assert adapter.launch_count == 3


def test_outcomes_are_substitutable_across_executors():
    verdicts = set()
    completed_sets = set()
    for executor in (make_local_adapter(), DeterministicFakeStepExecutor()):
        session = _session(executor)
        outcome = session.run_linear(
            run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok"
        )
        verdicts.add(outcome.final_verdict)
        completed_sets.add(tuple(sorted(t["step_id"] for t in outcome.evidence["state_transitions"])))
    assert verdicts == {"succeeded"}
    assert completed_sets == {tuple(sorted(STEP_ORDER))}


def test_p6_evidence_is_sanitized_and_binds_the_spec():
    session = _session(make_local_adapter())
    outcome = session.run_linear(
        run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok"
    )
    ev = outcome.evidence
    assert C.scan_projection_for_leak(ev) is None
    assert ev["workflow_spec_digest"].startswith("sha256:")
    assert ev["p6_admission"] == {"enabled": True, "approved": True, "admission_code": None}
    assert len(ev["artifact_refs"]) == 3
    assert ev["final_verdict"] == "succeeded"
    assert isinstance(ev["evidence_digest"], str) and ev["evidence_digest"].startswith("sha256:")


def test_terminal_gate_not_granted_parks_even_when_steps_complete():
    # WP4 terminal-gate enforcement is preserved: a missing terminal gate ref
    # downgrades an otherwise-complete run to ``parked`` (no overclaimed success).
    session = _session(make_local_adapter())
    outcome = session.run_linear(run_request(), step_requests_in_order(), terminal_gate_ref=None)
    assert outcome.final_verdict == "parked"
    assert outcome.ok is False


def test_pre_step_gate_missing_means_zero_executor_work_for_that_step():
    adapter = make_local_adapter()
    session = _session(adapter)
    session.create_run(run_request())
    result = session.step(step_request("architect", pre_step_gate_ref=None))
    assert result.status == "gate_blocked"
    assert adapter.launch_count == 0


def test_idempotent_step_replay_does_not_run_executor_twice():
    adapter = make_local_adapter()
    session = _session(adapter)
    session.create_run(run_request())
    first = session.step(step_request("architect"))
    second = session.step(step_request("architect"))
    assert adapter.launch_count == 1
    assert first.durable_state == second.durable_state


def test_terminal_failure_fails_closed_without_propagation():
    session = _session(DeterministicFakeStepExecutor(mode="terminal_failure"))
    outcome = session.run_linear(
        run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok"
    )
    assert outcome.final_verdict == "failed"
    assert outcome.ok is False
    # No artifact propagated for a failed-closed run.
    assert outcome.evidence["artifact_refs"] == []


def test_create_run_raises_p6_error_when_not_admitted():
    session = P6ControlledAiFlowSession(
        spec=SPEC, store=AiFlowRunStore(), executor=make_local_adapter(),
        enabled=False, approval_token=P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN,
        operator_gate=True,
    )
    with pytest.raises(P6ControlledAiFlowError):
        session.create_run(run_request())
