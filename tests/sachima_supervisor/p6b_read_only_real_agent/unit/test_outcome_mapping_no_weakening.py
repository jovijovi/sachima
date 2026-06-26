"""P6-B outcome mapping (FR6 — never weaken StepExecutor semantics).

The bridge returns only a sanitized ``StepExecutionOutcome``: it never sets or
infers a business verdict, never fabricates success from a supervisor status, and
maps inner failures to additive outer ``p6b_*`` codes (retryability preserved). WP4
remains the sole authority that records ``STEP_COMPLETED`` via its own
``_verify_single_output``.
"""

from __future__ import annotations

from sachima_supervisor.ai_flow_executor import StepExecutionOutcome
from sachima_supervisor.local_offline import LocalOfflineSupervisorOutcome
from sachima_supervisor.p6b_read_only_real_agent import (
    P6B_OUTPUT_UNSAFE,
    P6B_STABLE_CODES,
)

from .._support import (
    CountingSupervisor,
    build_executor,
    role_binding,
    step_request,
    success_supervisor_outcome,
)


def _execute(executor):
    return executor.execute(step_request(), role_binding=role_binding(), resolved_inputs=())


def test_success_outcome_carries_no_business_verdict(tmp_path):
    outcome = _execute(build_executor(tmp_path, invoke_supervisor=CountingSupervisor()))

    assert isinstance(outcome, StepExecutionOutcome)
    assert outcome.ok is True
    assert outcome.step_status == "completed"
    # The outcome contract has no business-verdict channel at all.
    assert not hasattr(outcome, "business_verdict")


def test_supervisor_completed_with_wrong_ref_count_is_not_trusted(tmp_path):
    def two_ref_outcome(seam_request):
        base = success_supervisor_outcome(seam_request)
        return LocalOfflineSupervisorOutcome(
            status=base.status,
            mode=base.mode,
            phase=base.phase,
            supervisor_status=base.supervisor_status,
            correlation_label=base.correlation_label,
            error_code=None,
            business_verdict=None,
            caller_verdict=None,
            artifact_ref_count=2,
            evidence_ref=base.evidence_ref,
            evidence_digest=base.evidence_digest,
            evidence_path=None,
            view_model={"status": "observed"},
        )

    outcome = _execute(
        build_executor(tmp_path, invoke_supervisor=CountingSupervisor(two_ref_outcome))
    )

    assert outcome.ok is False
    assert outcome.error_code == P6B_OUTPUT_UNSAFE


def test_supervisor_error_maps_to_stable_outer_code_preserving_retryable(tmp_path):
    def error_outcome(seam_request):
        return LocalOfflineSupervisorOutcome(
            status="error",
            mode=seam_request.mode,
            phase="exec",
            supervisor_status=None,
            correlation_label=seam_request.correlation_label,
            error_code=None,
            business_verdict=None,
            caller_verdict=None,
            artifact_ref_count=0,
            evidence_ref=None,
            evidence_digest=None,
            evidence_path=None,
            view_model={"status": "error"},
        )

    outcome = _execute(
        build_executor(tmp_path, invoke_supervisor=CountingSupervisor(error_outcome))
    )

    assert outcome.ok is False
    assert outcome.error_code in P6B_STABLE_CODES
    assert outcome.retryable is True
