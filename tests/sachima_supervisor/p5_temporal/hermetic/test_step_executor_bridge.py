"""T6 hermetic StepExecutor bridge (FR5, Gate E).

Drives the WP4 ``execute(request, *, role_binding, resolved_inputs) ->
StepExecutionOutcome`` shape against a **real** Temporal Worker: success carries
claim-check refs only and no business verdict, and the WP3b active-run
cancellation WATCH (``active_run_cancellation_watch -> cancel_ambiguous``) is
preserved. The async ``aexecute`` is used so the executor runs on the env loop.
"""

from __future__ import annotations

from types import SimpleNamespace

from sachima_supervisor.ai_flow_executor import StepExecutionOutcome
from sachima_supervisor.p5_temporal import (
    P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
    P5TemporalStepExecutor,
)
from sachima_supervisor.p5_temporal import contracts as C

from tests.sachima_supervisor.p5_temporal.hermetic._harness import (
    control_surface_for,
    p5_worker_env,
    run_async,
)


def _wp4_request():
    return SimpleNamespace(
        run_id="run_p5_bridge_0001",
        step_id="reviewer",
        attempt_index=1,
        idempotency_key="idem_p5_bridge_0001",
        transaction_ref="tx_p5_bridge_0001",
        operation_ref="op_p5_bridge_0001",
        input_artifact_digests=("sha256:" + "a" * 64,),
    )


def _role_binding():
    return SimpleNamespace(role_key="sachima.codex.primary_reviewer", logical_role="reviewer")


def _resolved_inputs():
    return (
        {
            "artifact_id": "claim_ref_input_0",
            "producer_step_id": "root",
            "content_digest": "sha256:" + "a" * 64,
            "artifact_kind": "input",
            "byte_count": 64,
            "created_at_ref": "created_at_ref_p5_0001",
        },
    )


def test_execute_returns_claim_check_outcome_with_no_business_verdict():
    async def scenario():
        async with p5_worker_env() as env:
            executor = P5TemporalStepExecutor(
                control_surface=control_surface_for(env),
                enabled=True,
                approval_token=P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
            )
            return await executor.aexecute(
                _wp4_request(), role_binding=_role_binding(), resolved_inputs=_resolved_inputs()
            )

    outcome = run_async(scenario())
    assert isinstance(outcome, StepExecutionOutcome)
    assert outcome.ok is True
    assert outcome.step_status == "completed"
    assert not hasattr(outcome, "business_verdict")
    assert len(outcome.artifact_refs) == 1
    ref = outcome.artifact_refs[0]
    assert set(ref) == set(C.ALLOWED_ARTIFACT_REF_KEYS)
    assert C._SHA256_DIGEST_RE.fullmatch(ref["content_digest"])
    assert outcome.evidence_ref and C._SHA256_DIGEST_RE.fullmatch(outcome.evidence_digest)


def test_cancellation_watch_is_preserved_on_real_run():
    async def scenario():
        async with p5_worker_env() as env:
            executor = P5TemporalStepExecutor(
                control_surface=control_surface_for(env),
                enabled=True,
                approval_token=P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
            )
            await executor.aexecute(
                _wp4_request(), role_binding=_role_binding(), resolved_inputs=_resolved_inputs()
            )
            unconfirmed = await executor.acancel(
                run_id="run_p5_bridge_0001",
                step_id="reviewer",
                scope="active_run",
                idempotency_key="idem_cancel_0001",
                interrupt_outcome=None,
            )
            confirmed = await executor.acancel(
                run_id="run_p5_bridge_0001",
                step_id="reviewer",
                scope="active_run",
                idempotency_key="idem_cancel_0002",
                interrupt_outcome=StepExecutionOutcome(
                    ok=True, step_status="cancelled", artifact_refs=(), interrupted=True, cleanup_verified=True
                ),
            )
            return unconfirmed, confirmed

    unconfirmed, confirmed = run_async(scenario())
    assert unconfirmed.ok is False
    assert unconfirmed.step_status == "cancel_ambiguous"
    assert unconfirmed.error_code == C.ACTIVE_RUN_CANCELLATION_WATCH
    # Only an independently-proven interrupt may report a clean cancellation.
    assert confirmed.ok is True and confirmed.step_status == "cancelled"
