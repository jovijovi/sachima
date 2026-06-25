"""P6-A WP4 no-weakening gate (FR2, Gate 2 — no Temporal).

The composition reuses the merged WP4 entrypoints and must not loosen any of its
fail-closed invariants: the admission gate, spec/role-binding digest binding,
claim-check artifact integrity, and the not-schedulable terminal lock all still
fire when driven through the P6-A session. (The full WP4 oracle suite is also
re-run unchanged as a regression gate.)
"""

from __future__ import annotations

import pytest

from sachima_supervisor.ai_flow_executor import StepExecutionOutcome
from sachima_supervisor.ai_flow_store import AiFlowError, AiFlowRunStore
from sachima_supervisor.activity_ai_flow_orchestration import AiFlowOrchestrationError
from sachima_supervisor.p6_controlled_ai_flow import (
    P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN,
    P6ControlledAiFlowSession,
)

from tests.sachima_supervisor.p6_controlled_ai_flow._support import (
    SPEC,
    make_local_adapter,
    run_request,
    step_request,
    step_requests_in_order,
)


def _session(executor=None):
    return P6ControlledAiFlowSession(
        spec=SPEC,
        store=AiFlowRunStore(),
        executor=executor if executor is not None else make_local_adapter(),
        enabled=True,
        approval_token=P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN,
        operator_gate=True,
    )


def test_wp4_admission_gate_is_not_weakened():
    session = _session()
    with pytest.raises(AiFlowOrchestrationError):
        session.create_run(run_request(admission_gate_ref=None))


def test_spec_binding_mismatch_still_fails_closed():
    session = _session()
    session.create_run(run_request())
    with pytest.raises(AiFlowOrchestrationError):
        session.step(step_request("architect", workflow_spec_digest="sha256:" + "0" * 64))


def test_idempotency_conflict_still_fails_closed():
    session = _session()
    session.create_run(run_request())
    session.step(step_request("architect"))
    with pytest.raises(AiFlowError):
        # Same idempotency key, divergent fingerprint -> conflict (no weakening).
        session.step(step_request("architect", attempt_index=2))


def test_claim_check_integrity_is_not_weakened():
    class _WrongKindExecutor:
        enabled = True
        approval_token = "x"

        def execute(self, request, *, role_binding, resolved_inputs):
            return StepExecutionOutcome(
                ok=True,
                step_status="completed",
                artifact_refs=(
                    {
                        "artifact_id": "artifact_architect",
                        "producer_step_id": "architect",
                        "content_digest": "sha256:" + "b" * 64,
                        "artifact_kind": "blocker_review",  # valid ref, wrong contract for architect
                        "byte_count": 12,
                        "created_at_ref": "created_at_ref_0001",
                    },
                ),
            )

    session = _session(_WrongKindExecutor())
    session.create_run(run_request())
    result = session.step(step_request("architect"))
    # Mismatched claim-check kind -> fail closed, never propagated as completed.
    assert result.status == "failed_terminal"
    assert result.error_code == "activity_artifact_integrity_failed"


def test_not_schedulable_after_terminal_is_not_weakened():
    session = _session()
    session.run_linear(run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok")
    with pytest.raises(AiFlowOrchestrationError):
        # Run is terminal/succeeded -> a fresh step attempt is rejected pre-claim.
        session.step(step_request("architect", idempotency_key="idem_architect_p6_again"))
