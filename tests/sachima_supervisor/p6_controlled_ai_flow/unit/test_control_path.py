"""P6-A control path (FR3/FR5, Gate 4 — no Temporal).

query / cancel / recover / close map onto the caller-owned executor controls and
the WP4 entrypoints. Read paths never relaunch work, and an active-run
cancellation that cannot be proven clean preserves the WP3b WATCH — it is never
upgraded to a clean ``cancelled`` by the composition. Admission failures return a
fail-closed control result with zero executor calls.
"""

from __future__ import annotations

from sachima_supervisor.ai_flow_store import AiFlowRunStore
from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p6_controlled_ai_flow import (
    P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN,
    P6_EXECUTION_DISABLED,
    P6ControlledAiFlowSession,
)

from tests.sachima_supervisor.p6_controlled_ai_flow._support import (
    SPEC,
    CountingExecutor,
    cancel_request,
    make_local_adapter,
    run_request,
    step_requests_in_order,
)


def _session(executor, *, enabled=True, operator_gate=True):
    return P6ControlledAiFlowSession(
        spec=SPEC,
        store=AiFlowRunStore(),
        executor=executor,
        enabled=enabled,
        approval_token=P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN,
        operator_gate=operator_gate,
    )


def test_query_is_read_only_and_reconciles_surfaces():
    adapter = make_local_adapter()
    session = _session(adapter)
    session.run_linear(run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok")
    before = adapter.launch_count
    out = session.query(run_id="run_p6_alpha", step_id="architect")
    assert out.ok is True
    assert out.op == "query"
    assert out.snapshot is not None
    assert C.scan_projection_for_leak(out.snapshot) is None
    # Read-only: no new executor launches.
    assert adapter.launch_count == before


def test_recover_reattaches_without_relaunch():
    adapter = make_local_adapter()
    session = _session(adapter)
    session.run_linear(run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok")
    before = adapter.launch_count
    out = session.recover(run_id="run_p6_alpha", step_id="architect")
    assert out.ok is True and out.op == "recover"
    assert adapter.launch_count == before


def test_between_step_cancellation_is_clean_when_no_step_in_flight():
    adapter = make_local_adapter()
    session = _session(adapter)
    session.create_run(run_request())
    # No step claimed/in flight -> deterministic clean cancellation; executor.cancel
    # is NOT used for the between-step scope.
    out = session.cancel(cancel_request(scope="between_step", step_id=None))
    assert out.ok is True
    assert out.active_run_watch is False
    assert out.snapshot["status"] == "cancelled"
    assert adapter.launch_count == 0


def test_active_run_cancellation_preserves_watch_and_never_upgrades():
    adapter = make_local_adapter()
    session = _session(adapter)
    session.run_linear(run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok")
    out = session.cancel(cancel_request(scope="active_run", step_id="architect"))
    assert out.ok is False
    assert out.active_run_watch is True
    assert out.error_code == C.ACTIVE_RUN_CANCELLATION_WATCH
    assert out.snapshot["status"] == "cancel_ambiguous"

    # A later between-step cancel with a fresh id must not downgrade the WATCH.
    later = session.cancel(
        cancel_request(scope="between_step", cancel_id="cancel_p6_0002", step_id=None)
    )
    assert later.active_run_watch is True
    assert later.snapshot["status"] == "cancel_ambiguous"


def test_close_returns_sanitized_terminal_evidence():
    adapter = make_local_adapter()
    session = _session(adapter)
    session.run_linear(run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok")
    out = session.close(run_id="run_p6_alpha", terminal_gate_ref="terminal_ref_ok")
    assert out.ok is True and out.op == "close"
    assert out.snapshot is not None
    assert C.scan_projection_for_leak(out.snapshot) is None
    assert out.snapshot["final_verdict"] == "succeeded"


def test_control_ops_fail_closed_with_zero_calls_when_disabled():
    counter = CountingExecutor(make_local_adapter())
    session = _session(counter, enabled=False)
    for out in (
        session.query(run_id="run_p6_alpha", step_id="architect"),
        session.recover(run_id="run_p6_alpha", step_id="architect"),
        session.cancel(cancel_request(scope="active_run", step_id="architect")),
        session.close(run_id="run_p6_alpha"),
    ):
        assert out.ok is False
        assert out.admission_code == P6_EXECUTION_DISABLED
    assert counter.total_calls == 0


def test_control_ops_validate_resident_state_before_executor_side_effects():
    counter = CountingExecutor(make_local_adapter())
    session = _session(counter)

    query = session.query(run_id="missing_run", step_id="architect")
    recover = session.recover(run_id="missing_run", step_id="architect")
    cancel = session.cancel(cancel_request(run_id="missing_run", scope="active_run", step_id="architect"))
    close = session.close(run_id="missing_run")

    assert query.error_code == C.RUNTIME_NOT_FOUND
    assert recover.error_code == C.RUNTIME_NOT_FOUND
    assert cancel.error_code == "activity_not_found"
    assert close.error_code == "activity_not_found"
    assert counter.total_calls == 0


def test_active_run_cancel_without_resident_in_flight_step_skips_executor_side_effect():
    counter = CountingExecutor(make_local_adapter())
    session = _session(counter)
    session.create_run(run_request())

    out = session.cancel(cancel_request(scope="active_run", step_id="architect"))

    assert out.ok is False
    assert out.active_run_watch is True
    assert out.error_code == C.ACTIVE_RUN_CANCELLATION_WATCH
    assert out.snapshot is not None
    assert out.snapshot["status"] == "cancel_ambiguous"
    assert counter.total_calls == 0
