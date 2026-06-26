"""P6-B control path (FR8 — query/recover no relaunch; cancel preserves WATCH).

Active-run cancellation never reports a clean ``cancelled`` in P6-B. The WP3b
WATCH is preserved even if a caller supplies a confirmed-looking lower-layer
interrupt outcome; real cancellation proof is a separate gate. Query / recover
read resident state only and never relaunch.
"""

from __future__ import annotations

from sachima_supervisor.ai_flow_executor import StepExecutionOutcome
from sachima_supervisor.activity_controlled_exec import ControlledLocalExecClaimStore
from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p6b_read_only_real_agent import P6B_EXECUTION_DISABLED

from .._support import (
    CountingSupervisor,
    RUN_ID,
    STEP_ID,
    build_executor,
    role_binding,
    step_request,
)


def test_active_run_cancel_preserves_watch(tmp_path):
    executor = build_executor(tmp_path)

    outcome = executor.cancel(
        run_id=RUN_ID, step_id=STEP_ID, scope="active_run", idempotency_key="idem_cancel_p6b"
    )

    assert outcome.ok is False
    assert outcome.error_code == C.ACTIVE_RUN_CANCELLATION_WATCH
    assert outcome.ambiguous is True
    assert outcome.step_status == C.CANCEL_AMBIGUOUS
    assert outcome.cleanup_verified is False


def test_unsupported_cancel_scope_fails_closed(tmp_path):
    executor = build_executor(tmp_path)

    outcome = executor.cancel(
        run_id=RUN_ID, step_id=STEP_ID, scope="between_step", idempotency_key="idem_cancel_p6b"
    )

    assert outcome.ok is False
    assert outcome.error_code == C.RUNTIME_CANCEL_SCOPE_UNSUPPORTED


def test_confirmed_external_interrupt_still_preserves_watch(tmp_path):
    executor = build_executor(tmp_path)
    confirming = StepExecutionOutcome(
        ok=True, step_status="cancelled", artifact_refs=(), interrupted=True, cleanup_verified=True
    )

    outcome = executor.cancel(
        run_id=RUN_ID,
        step_id=STEP_ID,
        scope="active_run",
        idempotency_key="idem_cancel_p6b",
        interrupt_outcome=confirming,
    )

    assert outcome.ok is False
    assert outcome.error_code == C.ACTIVE_RUN_CANCELLATION_WATCH
    assert outcome.step_status == C.CANCEL_AMBIGUOUS
    assert outcome.ambiguous is True
    assert outcome.cleanup_verified is False


def test_query_before_any_run_is_not_found_without_launch(tmp_path):
    supervisor = CountingSupervisor()
    executor = build_executor(tmp_path, invoke_supervisor=supervisor)

    snapshot = executor.query(run_id=RUN_ID, step_id=STEP_ID)

    assert snapshot["state"] == "not_found"
    assert supervisor.calls == 0


def test_query_and_recover_after_run_never_relaunch(tmp_path):
    supervisor = CountingSupervisor()
    store = ControlledLocalExecClaimStore()
    executor = build_executor(tmp_path, invoke_supervisor=supervisor, controlled_exec_store=store)

    executor.execute(step_request(), role_binding=role_binding(), resolved_inputs=())
    assert supervisor.calls == 1

    query = executor.query(run_id=RUN_ID, step_id=STEP_ID)
    recover = executor.recover(run_id=RUN_ID, step_id=STEP_ID)

    assert supervisor.calls == 1  # neither read relaunched
    assert query["state"] == "completed"
    assert recover["recovery_marker"] == "reattached_no_relaunch"
    assert C.scan_projection_for_leak(query) is None
    assert C.scan_projection_for_leak(recover) is None


def test_disabled_control_ops_make_zero_calls(tmp_path):
    supervisor = CountingSupervisor()
    executor = build_executor(tmp_path, enabled=False, invoke_supervisor=supervisor)

    cancel = executor.cancel(
        run_id=RUN_ID, step_id=STEP_ID, scope="active_run", idempotency_key="idem_cancel_p6b"
    )
    query = executor.query(run_id=RUN_ID, step_id=STEP_ID)
    close = executor.close()

    assert cancel.ok is False
    assert cancel.error_code == P6B_EXECUTION_DISABLED
    assert query["error_code"] == P6B_EXECUTION_DISABLED
    assert close["state"] == "store_invalid"
    assert supervisor.calls == 0
