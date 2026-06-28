"""P6 runtime lifecycle / controlled attach first implementation slice.

All tests are local/offline: no Temporal server/Worker, no subprocess, no Gateway,
no Feishu/live/default-on behavior, no real acpx/agent execution, and no delivery.
"""

from __future__ import annotations

from dataclasses import replace
import threading
from typing import Any

from sachima_supervisor.ai_flow_store import AiFlowRunStore
from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p6_controlled_ai_flow import (
    P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN,
    P6ControlledAiFlowSession,
)
from sachima_supervisor.p6_runtime_attach import (
    P6_RUNTIME_ATTACH_IMPLEMENTATION_APPROVAL_TOKEN,
    P6_ATTACH_APPROVAL_MISMATCH,
    P6_ATTACH_DISABLED,
    P6_ATTACH_GATE_BLOCKED,
    P6_ATTACH_IDEMPOTENCY_CONFLICT,
    P6_ATTACH_NOT_ATTACHED,
    P6_ATTACH_PRECONDITION_UNMET,
    P6_ATTACH_UNSAFE_MATERIAL,
    RuntimeAttachRequest,
    P6RuntimeAttachSession,
)
from tests.sachima_supervisor.p6_controlled_ai_flow._support import (
    SPEC,
    CountingExecutor,
    cancel_request,
    make_local_adapter,
    run_request,
    step_requests_in_order,
)


class _CountingHealthProbe:
    def __init__(self, snapshot: dict[str, Any] | None = None) -> None:
        self.calls = 0
        self.snapshot = snapshot or {"runtime_health": "healthy", "backend_ref": "safe_backend_ref"}

    def __call__(self) -> dict[str, Any]:
        self.calls += 1
        return dict(self.snapshot)


def _p6_session(executor: Any, *, store: AiFlowRunStore | None = None) -> P6ControlledAiFlowSession:
    return P6ControlledAiFlowSession(
        spec=SPEC,
        store=AiFlowRunStore() if store is None else store,
        executor=executor,
        enabled=True,
        approval_token=P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN,
        operator_gate=True,
    )


def _request(**overrides: Any) -> RuntimeAttachRequest:
    base = dict(
        enabled=True,
        approval_token=P6_RUNTIME_ATTACH_IMPLEMENTATION_APPROVAL_TOKEN,
        attach_ref="runtime_attach_ref_alpha",
        runtime_kind="local_offline_like",
        operator_gate=True,
        lease_id="lease_attach_alpha",
        lease_epoch=1,
        holder_ref="operator_attach_holder",
        state_version=1,
    )
    base.update(overrides)
    return RuntimeAttachRequest(**base)


def _attach_session(counter: CountingExecutor | None = None):
    counter = counter or CountingExecutor(make_local_adapter())
    attached = P6RuntimeAttachSession(p6_session=_p6_session(counter))
    attach = attached.attach(_request(), health_probe=_CountingHealthProbe())
    assert attach.ok is True
    return attached, counter


def test_disabled_mismatch_and_gate_blocked_make_zero_calls():
    counter = CountingExecutor(make_local_adapter())
    for request, code in (
        (_request(enabled=False), P6_ATTACH_DISABLED),
        (_request(approval_token="wrong_token"), P6_ATTACH_APPROVAL_MISMATCH),
        (_request(operator_gate=False), P6_ATTACH_GATE_BLOCKED),
    ):
        probe = _CountingHealthProbe()
        session = P6RuntimeAttachSession(p6_session=_p6_session(counter))
        result = session.attach(request, health_probe=probe)
        assert result.ok is False
        assert result.error_code == code
        assert result.snapshot is None
        assert probe.calls == 0
    assert counter.total_calls == 0


def test_unsafe_attach_material_fails_closed_without_echo_or_probe():
    counter = CountingExecutor(make_local_adapter())
    probe = _CountingHealthProbe()
    session = P6RuntimeAttachSession(p6_session=_p6_session(counter))

    result = session.attach(
        _request(attach_ref="/home/ecs-user/private/runtime", holder_ref="operator_attach_holder"),
        health_probe=probe,
    )

    assert result.ok is False
    assert result.error_code == P6_ATTACH_UNSAFE_MATERIAL
    assert result.snapshot is None
    assert probe.calls == 0
    assert counter.total_calls == 0
    assert C.scan_projection_for_leak(result.to_projection()) is None


def test_attach_returns_sanitized_projection_and_health_snapshot():
    probe = _CountingHealthProbe({"runtime_health": "healthy", "backend_ref": "safe_backend_ref"})
    session = P6RuntimeAttachSession(p6_session=_p6_session(CountingExecutor(make_local_adapter())))

    result = session.attach(_request(), health_probe=probe)

    assert result.ok is True
    assert result.snapshot is not None
    assert result.snapshot["attach_status"] == "attached"
    assert result.snapshot["runtime_health"] == "healthy"
    assert result.snapshot["backend_ref"] == "safe_backend_ref"
    assert result.snapshot["lease"]["lease_epoch"] == 1
    assert C.scan_projection_for_leak(result.snapshot) is None
    assert probe.calls == 1


def test_query_recover_close_fail_closed_before_attach_with_zero_executor_calls():
    counter = CountingExecutor(make_local_adapter())
    session = P6RuntimeAttachSession(p6_session=_p6_session(counter))

    for out in (
        session.query(run_id="run_p6_alpha", step_id="architect"),
        session.recover(run_id="run_p6_alpha", step_id="architect"),
        session.cancel(cancel_request(scope="active_run", step_id="architect")),
        session.close(run_id="run_p6_alpha"),
    ):
        assert out.ok is False
        assert out.error_code == P6_ATTACH_NOT_ATTACHED
        assert out.admitted is False
    assert counter.total_calls == 0


class _OkAdmission:
    ok = True
    error_code = None


class _RaisingAfterLaunchP6Session:
    def __init__(self, executor: Any) -> None:
        self.executor = executor
        self.run_linear_calls = 0
        self.recover_calls = 0

    def admit(self):
        return _OkAdmission()

    def run_linear(self, run_request, step_requests, *, terminal_gate_ref=None):
        self.run_linear_calls += 1
        self.executor.execute_calls += 1
        raise RuntimeError("lost response after launch")

    def query(self, *, run_id: str, step_id: str):
        raise AssertionError("query should not be called")

    def recover(self, *, run_id: str, step_id: str):
        self.recover_calls += 1
        return type(
            "RecoverOutcome",
            (),
            {
                "ok": False,
                "admitted": True,
                "error_code": "runtime_not_found",
                "snapshot": {"type": "fake_snapshot", "recovery_marker": "reattached_no_relaunch"},
                "active_run_watch": False,
                "replayed": True,
            },
        )()

    def cancel(self, cancel_request):
        raise AssertionError("cancel should not be called")

    def close(self, *, run_id: str, terminal_gate_ref=None):
        raise AssertionError("close should not be called")


class _RealRunnerLikeExecutor:
    enabled = True
    approval_token = "approve_p6b_real_agent_runner"

    def execute(self, request, *, role_binding, resolved_inputs):
        raise AssertionError("real runner must never be called")

    def query(self, **kw):
        raise AssertionError("real runner must never be called")

    def recover(self, **kw):
        raise AssertionError("real runner must never be called")

    def cancel(self, **kw):
        raise AssertionError("real runner must never be called")

    def close(self):
        raise AssertionError("real runner must never be called")


def test_lost_response_after_launch_records_claim_before_delegate_and_never_relaunches():
    counter = CountingExecutor(make_local_adapter())
    p6_session = _RaisingAfterLaunchP6Session(counter)
    session = P6RuntimeAttachSession(p6_session=p6_session)
    assert session.attach(_request(), health_probe=_CountingHealthProbe()).ok is True

    first = session.start(run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok")
    assert first.ok is False
    assert first.error_code == "p6_attach_backend_unavailable"
    assert p6_session.run_linear_calls == 1
    assert counter.execute_calls == 1

    second = session.start(run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok")
    assert second.replayed is True
    assert second.snapshot is not None
    assert second.snapshot["recovery_marker"] == "reattached_no_relaunch"
    assert p6_session.run_linear_calls == 1
    assert counter.execute_calls == 1
    assert p6_session.recover_calls == 1


def test_attach_rejects_real_runner_like_p6_session_before_health_probe_or_execution():
    probe = _CountingHealthProbe()
    session = P6RuntimeAttachSession(
        p6_session=_p6_session(_RealRunnerLikeExecutor())
    )

    result = session.attach(_request(), health_probe=probe)

    assert result.ok is False
    assert result.error_code == P6_ATTACH_PRECONDITION_UNMET
    assert probe.calls == 0


def test_raw_start_identifiers_fail_closed_before_delegate():
    session, counter = _attach_session()
    raw_run = replace(run_request(), workflow_id="/home/ecs-user/private/workflow")
    raw_step = step_requests_in_order()
    raw_step[0] = replace(raw_step[0], idempotency_key="om_private_message")

    out1 = session.start(raw_run, step_requests_in_order(), terminal_gate_ref="terminal_ref_ok")
    out2 = session.start(run_request(), raw_step, terminal_gate_ref="terminal_ref_ok")
    out3 = session.start(run_request(), step_requests_in_order(), terminal_gate_ref="/tmp/private_gate")

    assert out1.ok is False and out1.error_code == P6_ATTACH_UNSAFE_MATERIAL
    assert out2.ok is False and out2.error_code == P6_ATTACH_UNSAFE_MATERIAL
    assert out3.ok is False and out3.error_code == P6_ATTACH_UNSAFE_MATERIAL
    assert counter.total_calls == 0


class _BlockingRunLinearP6Session:
    def __init__(self, executor: Any) -> None:
        self.executor = executor
        self.run_linear_calls = 0
        self.entered = threading.Event()
        self.release = threading.Event()

    def admit(self):
        return _OkAdmission()

    def run_linear(self, run_request, step_requests, *, terminal_gate_ref=None):
        self.run_linear_calls += 1
        self.executor.execute_calls += 1
        self.entered.set()
        assert self.release.wait(timeout=5), "test did not release run_linear"
        return type(
            "RunOutcome",
            (),
            {
                "ok": True,
                "admitted": True,
                "error_code": None,
                "evidence": {"type": "fake_evidence", "final_verdict": "succeeded"},
                "active_run_watch": False,
                "replayed": False,
            },
        )()

    def query(self, *, run_id: str, step_id: str):
        return {"type": "fake_snapshot", "state": "completed", "run_ref": run_id, "step_ref": step_id}

    def recover(self, *, run_id: str, step_id: str):
        return type(
            "RecoverOutcome",
            (),
            {
                "ok": True,
                "admitted": True,
                "error_code": None,
                "snapshot": {"type": "fake_snapshot", "recovery_marker": "reattached_no_relaunch"},
                "active_run_watch": False,
                "replayed": True,
            },
        )()

    def cancel(self, cancel_request):
        raise AssertionError("cancel should not be called")

    def close(self, *, run_id: str, terminal_gate_ref=None):
        raise AssertionError("close should not be called")


class _TokenSpoofExecutor:
    enabled = True
    approval_token = make_local_adapter().approval_token

    def execute(self, request, *, role_binding, resolved_inputs):
        raise AssertionError("spoof executor must never be called")

    def query(self, **kw):
        raise AssertionError("spoof executor must never be called")

    def recover(self, **kw):
        raise AssertionError("spoof executor must never be called")

    def cancel(self, **kw):
        raise AssertionError("spoof executor must never be called")

    def close(self):
        raise AssertionError("spoof executor must never be called")


def test_concurrent_identical_start_claim_is_atomic_and_launches_once():
    counter = CountingExecutor(make_local_adapter())
    p6_session = _BlockingRunLinearP6Session(counter)
    session = P6RuntimeAttachSession(p6_session=p6_session)
    assert session.attach(_request(), health_probe=_CountingHealthProbe()).ok is True
    results = []

    def call_start():
        results.append(session.start(run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok"))

    first = threading.Thread(target=call_start)
    second = threading.Thread(target=call_start)
    first.start()
    assert p6_session.entered.wait(timeout=5)
    second.start()
    second.join(timeout=5)
    p6_session.release.set()
    first.join(timeout=5)

    assert len(results) == 2
    assert p6_session.run_linear_calls == 1
    assert counter.execute_calls == 1
    assert any(item.replayed for item in results)
    assert any(item.ok for item in results)


def test_attach_rejects_executor_that_only_spoofs_local_offline_token():
    session = P6RuntimeAttachSession(p6_session=_p6_session(_TokenSpoofExecutor()))
    probe = _CountingHealthProbe()

    result = session.attach(_request(), health_probe=probe)

    assert result.ok is False
    assert result.error_code == P6_ATTACH_PRECONDITION_UNMET
    assert probe.calls == 0


def test_start_delegates_only_after_attach_and_duplicate_identical_start_never_reexecutes():
    session, counter = _attach_session()

    first = session.start(run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok")
    assert first.ok is True
    assert first.replayed is False
    assert counter.execute_calls == 3

    second = session.start(run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok")
    assert second.ok is True
    assert second.replayed is True
    assert second.snapshot is not None
    assert second.snapshot["recovery_marker"] == "reattached_no_relaunch"
    # The duplicate path may query/recover, but it must not execute the steps again.
    assert counter.execute_calls == 3



def test_divergent_duplicate_start_detects_lease_and_state_fields():
    session, counter = _attach_session()
    first = session.start(run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok")
    assert first.ok is True
    assert counter.execute_calls == 3

    divergent_run = replace(run_request(), lease_id="lease_changed", expected_state_version=99)
    divergent_steps = step_requests_in_order()
    divergent_steps[0] = replace(
        divergent_steps[0],
        lease_id="lease_changed",
        expected_state_version=99,
        pre_step_gate_ref="pre_step_gate_changed",
    )
    divergent = session.start(divergent_run, divergent_steps, terminal_gate_ref="terminal_ref_ok")

    assert divergent.ok is False
    assert divergent.error_code == P6_ATTACH_IDEMPOTENCY_CONFLICT
    assert counter.execute_calls == 3


def test_caller_owned_claim_store_preserves_no_relaunch_across_session_recreation():
    claim_store = {}
    counter = CountingExecutor(make_local_adapter())
    first_p6 = _RaisingAfterLaunchP6Session(counter)
    first_session = P6RuntimeAttachSession(p6_session=first_p6, claim_store=claim_store)
    assert first_session.attach(_request(), health_probe=_CountingHealthProbe()).ok is True

    first = first_session.start(run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok")
    assert first.ok is False
    assert first.error_code == "p6_attach_backend_unavailable"
    assert first_p6.run_linear_calls == 1
    assert counter.execute_calls == 1

    second_p6 = _RaisingAfterLaunchP6Session(counter)
    second_session = P6RuntimeAttachSession(p6_session=second_p6, claim_store=claim_store)
    assert second_session.attach(_request(), health_probe=_CountingHealthProbe()).ok is True
    second = second_session.start(run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok")

    assert second.replayed is True
    assert second.snapshot is not None
    assert second.snapshot["recovery_marker"] == "reattached_no_relaunch"
    assert second_p6.run_linear_calls == 0
    assert counter.execute_calls == 1
    assert second_p6.recover_calls == 1


def test_divergent_duplicate_start_fails_closed_before_executor_call():
    session, counter = _attach_session()
    first = session.start(run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok")
    assert first.ok is True
    assert counter.execute_calls == 3

    divergent_steps = step_requests_in_order()
    divergent_steps[0] = replace(divergent_steps[0], idempotency_key="idem_architect_changed")
    divergent = session.start(run_request(), divergent_steps, terminal_gate_ref="terminal_ref_ok")

    assert divergent.ok is False
    assert divergent.error_code == P6_ATTACH_IDEMPOTENCY_CONFLICT
    assert counter.execute_calls == 3


def test_recover_is_read_only_and_never_relaunches():
    session, counter = _attach_session()
    session.start(run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok")
    before = counter.execute_calls

    out = session.recover(run_id="run_p6_alpha", step_id="architect")

    assert out.ok is True
    assert out.snapshot is not None
    assert out.snapshot["recovery_marker"] == "reattached_no_relaunch"
    assert counter.execute_calls == before


def test_active_run_cancellation_watch_is_preserved_through_attach_layer():
    session, _counter = _attach_session()
    session.start(run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok")

    out = session.cancel(cancel_request(scope="active_run", step_id="architect"))

    assert out.ok is False
    assert out.active_run_watch is True
    assert out.error_code == C.ACTIVE_RUN_CANCELLATION_WATCH
    assert out.snapshot is not None
    assert out.snapshot["status"] == "cancel_ambiguous"


def test_close_detaches_without_disconnect_or_delivery_side_effects():
    session, counter = _attach_session()
    session.start(run_request(), step_requests_in_order(), terminal_gate_ref="terminal_ref_ok")

    closed = session.close(run_id="run_p6_alpha", terminal_gate_ref="terminal_ref_ok", detach=True)

    assert closed.ok is True
    assert closed.snapshot is not None
    assert closed.snapshot["final_verdict"] == "succeeded"
    assert closed.attach_status == "detached"
    assert session.attach_state()["attach_status"] == "detached"
    # Existing P6 close marker is allowed; no extra runtime/client disconnect semantics are added here.
    assert counter.control_calls >= 1
    assert C.scan_projection_for_leak(closed.snapshot) is None




def test_health_probe_unsafe_extra_material_fails_closed():
    counter = CountingExecutor(make_local_adapter())
    probe = _CountingHealthProbe(
        {
            "runtime_health": "healthy",
            "backend_ref": "safe_backend_ref",
            "raw_prompt": "do not persist this",
        }
    )
    session = P6RuntimeAttachSession(p6_session=_p6_session(counter))

    result = session.attach(_request(), health_probe=probe)

    assert result.ok is False
    assert result.error_code == P6_ATTACH_UNSAFE_MATERIAL
    assert session.attach_state()["attach_status"] == "unattached"
    assert counter.total_calls == 0
    assert C.scan_projection_for_leak(result.to_projection()) is None


def test_raw_control_identifiers_fail_closed_before_p6_session_call():
    session, counter = _attach_session()

    query = session.query(run_id="/home/ecs-user/private/run", step_id="architect")
    recover = session.recover(run_id="run_p6_alpha", step_id="om_private_message_id")
    close = session.close(run_id="/tmp/private/run")

    assert query.ok is False and query.error_code == P6_ATTACH_UNSAFE_MATERIAL
    assert recover.ok is False and recover.error_code == P6_ATTACH_UNSAFE_MATERIAL
    assert close.ok is False and close.error_code == P6_ATTACH_UNSAFE_MATERIAL
    assert counter.total_calls == 0
    assert C.scan_projection_for_leak(query.to_projection()) is None
    assert C.scan_projection_for_leak(recover.to_projection()) is None
    assert C.scan_projection_for_leak(close.to_projection()) is None


class _LeakyErrorCodeP6Session:
    def __init__(self, executor: Any) -> None:
        self.executor = executor

    def admit(self):
        return _OkAdmission()

    def run_linear(self, run_request, step_requests, *, terminal_gate_ref=None):
        raise AssertionError("run should not be called")

    def query(self, *, run_id: str, step_id: str):
        return type(
            "QueryOutcome",
            (),
            {
                "ok": False,
                "admitted": True,
                "error_code": "/home/ecs-user/private/raw_prompt",
                "snapshot": {"type": "fake_snapshot", "state": "failed"},
                "active_run_watch": False,
                "replayed": False,
            },
        )()

    def recover(self, *, run_id: str, step_id: str):
        raise AssertionError("recover should not be called")

    def cancel(self, cancel_request):
        raise AssertionError("cancel should not be called")

    def close(self, *, run_id: str, terminal_gate_ref=None):
        raise AssertionError("close should not be called")


def test_downstream_raw_or_nonstable_error_code_is_collapsed_before_public_outcome():
    session = P6RuntimeAttachSession(
        p6_session=_LeakyErrorCodeP6Session(CountingExecutor(make_local_adapter()))
    )
    assert session.attach(_request(), health_probe=_CountingHealthProbe()).ok is True

    result = session.query(run_id="run_p6_alpha", step_id="architect")

    assert result.ok is False
    assert result.error_code == P6_ATTACH_UNSAFE_MATERIAL
    assert C.scan_projection_for_leak(result.to_projection()) is None


class _OkWithLeakyErrorCodeP6Session(_LeakyErrorCodeP6Session):
    def query(self, *, run_id: str, step_id: str):
        return type(
            "QueryOutcome",
            (),
            {
                "ok": True,
                "admitted": True,
                "error_code": "/home/ecs-user/private/raw_prompt",
                "snapshot": {"type": "fake_snapshot", "state": "completed"},
                "active_run_watch": False,
                "replayed": False,
            },
        )()


def test_downstream_unsafe_error_code_forces_rejected_even_when_delegate_claims_ok():
    session = P6RuntimeAttachSession(
        p6_session=_OkWithLeakyErrorCodeP6Session(CountingExecutor(make_local_adapter()))
    )
    assert session.attach(_request(), health_probe=_CountingHealthProbe()).ok is True

    result = session.query(run_id="run_p6_alpha", step_id="architect")

    assert result.ok is False
    assert result.admitted is False
    assert result.error_code == P6_ATTACH_UNSAFE_MATERIAL
    assert result.snapshot is None
    assert C.scan_projection_for_leak(result.to_projection()) is None


def test_attach_state_and_attach_result_are_deep_copied_against_caller_mutation():
    session = P6RuntimeAttachSession(p6_session=_p6_session(CountingExecutor(make_local_adapter())))
    result = session.attach(_request(), health_probe=_CountingHealthProbe())
    assert result.snapshot is not None

    result.snapshot["lease"]["lease_id"] = "/home/ecs-user/private/raw_prompt"
    snapshot = session.attach_state()
    snapshot["lease"]["holder_ref"] = "/tmp/private_holder"
    again = session.attach_state()

    assert again["lease"]["lease_id"] == "lease_attach_alpha"
    assert again["lease"]["holder_ref"] == "operator_attach_holder"
    assert C.scan_projection_for_leak(again) is None


def test_public_package_exports_runtime_attach_api():
    import sachima_supervisor as public

    assert public.P6RuntimeAttachSession is P6RuntimeAttachSession
    assert public.RuntimeAttachRequest is RuntimeAttachRequest
    assert public.P6_RUNTIME_ATTACH_IMPLEMENTATION_APPROVAL_TOKEN == P6_RUNTIME_ATTACH_IMPLEMENTATION_APPROVAL_TOKEN
