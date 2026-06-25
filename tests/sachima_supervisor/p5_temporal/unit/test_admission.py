"""T0 — default-off admission + exact approval token (Gate A, FR1).

Proves ``P5TemporalStepExecutor`` makes **zero** Temporal/control-surface calls
when disabled or when the approval token is missing/mismatched, and returns the
stable codes ``runtime_disabled`` / ``runtime_approval_mismatch`` /
``runtime_precondition_unmet``. The caller stays on the local/offline baseline.

Gate A is enforced on **every** control-surface entry point — not just
``execute`` / ``aexecute`` but ``query`` / ``recover`` / ``cancel`` / ``close``:
absent the enable flag or the exact token, each returns a sanitized, no-throw
result and reaches the control surface zero times (verified with a tripwire
surface whose every method fails if called).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sachima_supervisor.p5_temporal import (
    P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
    P5TemporalStepExecutor,
)
from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.ai_flow_executor import StepExecutionOutcome


class _TripwireControlSurface:
    """Any awaited dispatch is a contract violation on the disabled/mismatch path.

    Every control-surface method increments ``calls`` and fails if reached, so a
    Gate A regression on *any* of start/query/recover/cancel/close is caught.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def start(self, *a, **k):  # pragma: no cover - must never run
        self.calls += 1
        raise AssertionError("control surface must not be reached when default-off")

    # The disabled / mismatch path must short-circuit before any other method too.
    async def query(self, *a, **k):  # pragma: no cover
        self.calls += 1
        raise AssertionError("no Temporal call allowed")

    async def recover(self, *a, **k):  # pragma: no cover
        self.calls += 1
        raise AssertionError("no Temporal call allowed")

    async def cancel(self, *a, **k):  # pragma: no cover
        self.calls += 1
        raise AssertionError("no Temporal call allowed")

    async def close(self, *a, **k):  # pragma: no cover
        self.calls += 1
        raise AssertionError("no Temporal call allowed")


def _request():
    return SimpleNamespace(
        run_id="run_p5_demo_0001",
        step_id="architect",
        attempt_index=1,
        transaction_ref="tx_p5_demo_0001",
        operation_ref="op_p5_demo_0001",
        idempotency_key="idem_p5_demo_0001",
        input_artifact_digests=("sha256:" + "a" * 64,),
    )


def _role_binding():
    return SimpleNamespace(role_key="sachima_claude_read_only_reviewer", logical_role="architect")


def _resolved_inputs():
    return (
        {
            "artifact_id": "claim_ref_input_0",
            "producer_step_id": "root",
            "content_digest": "sha256:" + "a" * 64,
            "artifact_kind": "input",
            "byte_count": 128,
            "created_at_ref": "created_at_ref_p5_0001",
        },
    )


def test_disabled_makes_no_temporal_call():
    tripwire = _TripwireControlSurface()
    executor = P5TemporalStepExecutor(
        control_surface=tripwire,
        enabled=False,
        approval_token=P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
    )
    outcome = executor.execute(_request(), role_binding=_role_binding(), resolved_inputs=_resolved_inputs())
    assert isinstance(outcome, StepExecutionOutcome)
    assert outcome.ok is False
    assert outcome.error_code == C.RUNTIME_DISABLED
    assert tripwire.calls == 0


def test_mismatched_token_makes_no_temporal_call():
    tripwire = _TripwireControlSurface()
    executor = P5TemporalStepExecutor(
        control_surface=tripwire,
        enabled=True,
        approval_token="not_the_exact_token",
    )
    outcome = executor.execute(_request(), role_binding=_role_binding(), resolved_inputs=_resolved_inputs())
    assert outcome.ok is False
    assert outcome.error_code == C.RUNTIME_APPROVAL_MISMATCH
    assert tripwire.calls == 0


def test_empty_token_makes_no_temporal_call():
    tripwire = _TripwireControlSurface()
    executor = P5TemporalStepExecutor(control_surface=tripwire, enabled=True, approval_token="")
    outcome = executor.execute(_request(), role_binding=_role_binding(), resolved_inputs=_resolved_inputs())
    assert outcome.ok is False
    assert outcome.error_code == C.RUNTIME_APPROVAL_MISMATCH
    assert tripwire.calls == 0


def test_enabled_and_approved_but_no_runtime_precondition_unmet():
    # Flag on + exact token, but no control surface wired => fail closed with
    # runtime_precondition_unmet and still no Temporal call.
    executor = P5TemporalStepExecutor(
        control_surface=None,
        enabled=True,
        approval_token=P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
    )
    outcome = executor.execute(_request(), role_binding=_role_binding(), resolved_inputs=_resolved_inputs())
    assert outcome.ok is False
    assert outcome.error_code == C.RUNTIME_PRECONDITION_UNMET


def test_token_constant_is_exact_and_encodes_non_approvals():
    token = P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN
    assert token.startswith("approve_agent_run_supervisor_sachima_p5_temporal_pr_b")
    for must in (
        "hermetic_local",
        "staging",
        "ops_owned_worker",
        "caller_supplied_temporal_client",
        "default_off",
        "controlled_deterministic",
        "no_production_cluster",
        "no_p6_real_acpx",
        "no_gateway",
        "no_feishu",
        "no_real_delivery",
    ):
        assert must in token, must


# --------------------------------------------------------------------------- #
# Gate A on the control surface (query / recover / cancel / close), not just
# execute. Disabled or mismatched-token executors must reach the control surface
# zero times for every method and return sanitized, no-throw results.
# --------------------------------------------------------------------------- #
def _disabled_executor(tripwire):
    # Exact token but flag off => default-off; must short-circuit everywhere.
    return P5TemporalStepExecutor(
        control_surface=tripwire,
        enabled=False,
        approval_token=P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
    )


def _mismatched_executor(tripwire):
    # Flag on but wrong token => token mismatch; must short-circuit everywhere.
    return P5TemporalStepExecutor(
        control_surface=tripwire,
        enabled=True,
        approval_token="not_the_exact_token",
    )


_ADMISSION_CASES = pytest.mark.parametrize(
    "make, expected_code",
    [
        (_disabled_executor, C.RUNTIME_DISABLED),
        (_mismatched_executor, C.RUNTIME_APPROVAL_MISMATCH),
    ],
    ids=["disabled", "mismatched_token"],
)


@_ADMISSION_CASES
def test_query_makes_no_temporal_call(make, expected_code):
    tripwire = _TripwireControlSurface()
    snap = make(tripwire).query(run_id="run_p5_demo_0001", step_id="architect")
    assert isinstance(snap, dict)
    assert snap["state"] == "store_invalid"
    assert snap["error_code"] == expected_code
    assert snap["artifact_refs"] == []
    assert C.scan_projection_for_leak(snap) is None
    assert tripwire.calls == 0


@_ADMISSION_CASES
def test_recover_makes_no_temporal_call(make, expected_code):
    tripwire = _TripwireControlSurface()
    snap = make(tripwire).recover(run_id="run_p5_demo_0001", step_id="architect")
    assert isinstance(snap, dict)
    assert snap["state"] == "store_invalid"
    assert snap["error_code"] == expected_code
    # No reattachment claim is made when the call never happened.
    assert "recovery_marker" not in snap
    assert tripwire.calls == 0


@_ADMISSION_CASES
def test_cancel_makes_no_temporal_call(make, expected_code):
    tripwire = _TripwireControlSurface()
    outcome = make(tripwire).cancel(
        run_id="run_p5_demo_0001",
        step_id="architect",
        scope="active_run",
        idempotency_key="idem_cancel_0001",
        interrupt_outcome=None,
    )
    assert isinstance(outcome, StepExecutionOutcome)
    assert outcome.ok is False
    assert outcome.error_code == expected_code
    assert tripwire.calls == 0


@_ADMISSION_CASES
def test_close_makes_no_temporal_call(make, expected_code):
    tripwire = _TripwireControlSurface()
    closed = make(tripwire).close()
    assert isinstance(closed, dict)
    assert closed["state"] == "store_invalid"
    assert closed["error_code"] == expected_code
    assert tripwire.calls == 0


def test_disabled_control_surface_calls_are_no_throw_on_unsafe_refs():
    # Even hostile run/step refs must neither raise nor reach the control surface
    # on the Gate A rejection path, and the sanitized marker must not leak.
    tripwire = _TripwireControlSurface()
    executor = _disabled_executor(tripwire)
    hostile = "post" + "gres://user:pw@host/db"
    snap = executor.query(run_id=hostile, step_id="/home/ecs-user/.ssh/id_rsa")
    assert snap["error_code"] == C.RUNTIME_DISABLED
    assert C.scan_projection_for_leak(snap) is None
    cancelled = executor.cancel(
        run_id=hostile,
        step_id="architect",
        scope="active_run",
        idempotency_key=hostile,
    )
    assert cancelled.ok is False
    assert cancelled.error_code == C.RUNTIME_DISABLED
    # Local sanitized history must stay leak-free after rejecting hostile input.
    assert C.scan_projection_for_leak(executor.history_projection()) is None
    assert tripwire.calls == 0
