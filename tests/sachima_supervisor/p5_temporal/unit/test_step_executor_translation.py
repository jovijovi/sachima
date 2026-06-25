"""T0b — executor WP4→contracts translation rejects raw refs before any Temporal
call (Gate A/B blocker fix).

Regression for the blocker where raw connection strings / private paths / Windows
paths / signed URLs in WP4 *request refs* (``run_id`` / ``step_id`` /
``transaction_ref`` / ``idempotency_key``) were normalized into safe-looking ids
and entered ``StartRequest`` / Temporal history. The executor must now fail closed
with ``invalid_start_payload`` **before** the control surface is ever awaited, and
a clean dotted WP4 request must still be admitted through translation.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sachima_supervisor.ai_flow_executor import StepExecutionOutcome
from sachima_supervisor.p5_temporal import (
    P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
    P5TemporalStepExecutor,
)
from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p5_temporal.control_surface import P5TemporalControlSurface
from sachima_supervisor.p5_temporal.runtime_client import P5TemporalRuntimeClient
from tests.sachima_supervisor.p5_temporal._fake_temporal import FakeTemporalClient


_POSTGRES_URL = "post" + "gres://user:" + "pw" + "@host/db"
_SIGNED_URL = "https://example.test/object?" + "X-Amz-" + "Signature=abc"
_TOKEN_URL = "https://example.test/iam?" + "to" + "ken=abc"


class _TripwireControlSurface:
    """Any awaited dispatch is a contract violation on the reject-before-start path."""

    def __init__(self) -> None:
        self.calls = 0

    async def start(self, *a, **k):  # pragma: no cover - must never run for unsafe refs
        self.calls += 1
        raise AssertionError("control surface must not be reached for unsafe refs")

    async def query(self, *a, **k):  # pragma: no cover
        self.calls += 1
        raise AssertionError("no Temporal call allowed")

    async def cancel(self, *a, **k):  # pragma: no cover
        self.calls += 1
        raise AssertionError("no Temporal call allowed")


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


def _clean_request():
    return SimpleNamespace(
        run_id="run_p5_demo_0001",
        step_id="architect",
        attempt_index=1,
        transaction_ref="tx_p5_demo_0001",
        idempotency_key="idem_p5_demo_0001",
    )


def _enabled_executor(control_surface):
    return P5TemporalStepExecutor(
        control_surface=control_surface,
        enabled=True,
        approval_token=P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
    )


@pytest.mark.parametrize(
    "field, value",
    [
        ("run_id", _POSTGRES_URL),
        ("step_id", "/home/ecs-user/.ssh/id_rsa"),
        ("transaction_ref", "C:\\Users\\x\\.ssh\\id_rsa"),
        ("idempotency_key", _SIGNED_URL),
    ],
)
def test_unsafe_request_ref_rejected_before_any_temporal_call(field, value):
    tripwire = _TripwireControlSurface()
    executor = _enabled_executor(tripwire)
    request = _clean_request()
    setattr(request, field, value)
    outcome = executor.execute(
        request, role_binding=_role_binding(), resolved_inputs=_resolved_inputs()
    )
    assert isinstance(outcome, StepExecutionOutcome)
    assert outcome.ok is False
    assert outcome.error_code == C.INVALID_START_PAYLOAD
    # Zero control-surface calls: rejection happened in translation, before start.
    assert tripwire.calls == 0


def test_unsafe_role_key_rejected_before_any_temporal_call():
    tripwire = _TripwireControlSurface()
    executor = _enabled_executor(tripwire)
    outcome = executor.execute(
        _clean_request(),
        role_binding=SimpleNamespace(role_key=_TOKEN_URL),
        resolved_inputs=_resolved_inputs(),
    )
    assert outcome.ok is False
    assert outcome.error_code == C.INVALID_START_PAYLOAD
    assert tripwire.calls == 0


def test_clean_dotted_request_is_admitted_through_translation():
    # GREEN companion: a clean dotted role + refs must NOT be rejected by the
    # raw-ref guard — translation succeeds and start is reached exactly once.
    fake = FakeTemporalClient()
    surface = P5TemporalControlSurface(P5TemporalRuntimeClient(fake))
    executor = _enabled_executor(surface)
    outcome = executor.execute(
        _clean_request(),
        role_binding=SimpleNamespace(role_key="sachima.codex.primary_reviewer"),
        resolved_inputs=_resolved_inputs(),
    )
    assert outcome.ok is True
    assert outcome.step_status == "completed"
    assert fake.start_calls == 1


# --------------------------------------------------------------------------- #
# Missing / None / empty / stringified-None identity material must fail closed
# BEFORE any Temporal call (Gate A/B blocker fix). Pre-fix `str(getattr(...))`
# turned None into 'None'->'none' and missing/empty into a bare 'ref_', starting
# Temporal work with malformed identity. Now translation rejects it with zero
# control-surface calls.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "field, value",
    [
        ("run_id", None),
        ("run_id", ""),
        ("run_id", "   "),
        ("run_id", "none"),
        ("run_id", "None"),
        ("step_id", None),
        ("step_id", ""),
        ("step_id", "none"),
        ("idempotency_key", None),
        ("idempotency_key", ""),
        ("idempotency_key", "None"),
    ],
)
def test_missing_none_empty_request_ref_rejected_before_any_temporal_call(field, value):
    tripwire = _TripwireControlSurface()
    executor = _enabled_executor(tripwire)
    request = _clean_request()
    setattr(request, field, value)
    outcome = executor.execute(
        request, role_binding=_role_binding(), resolved_inputs=_resolved_inputs()
    )
    assert isinstance(outcome, StepExecutionOutcome)
    assert outcome.ok is False
    assert outcome.error_code == C.INVALID_START_PAYLOAD
    # Zero control-surface calls: rejected in translation, before any start.
    assert tripwire.calls == 0


@pytest.mark.parametrize("attr", ["run_id", "step_id", "idempotency_key"])
def test_missing_request_attr_rejected_before_any_temporal_call(attr):
    # A required identity attribute that is entirely absent must also fail closed.
    tripwire = _TripwireControlSurface()
    executor = _enabled_executor(tripwire)
    request = _clean_request()
    delattr(request, attr)
    outcome = executor.execute(
        request, role_binding=_role_binding(), resolved_inputs=_resolved_inputs()
    )
    assert outcome.ok is False
    assert outcome.error_code == C.INVALID_START_PAYLOAD
    assert tripwire.calls == 0


@pytest.mark.parametrize(
    "role_binding",
    [
        SimpleNamespace(),                      # role_key attribute absent
        SimpleNamespace(role_key=None),         # None
        SimpleNamespace(role_key=""),           # empty
        SimpleNamespace(role_key="none"),       # stringified-None sentinel
    ],
)
def test_missing_none_empty_role_key_rejected_before_any_temporal_call(role_binding):
    tripwire = _TripwireControlSurface()
    executor = _enabled_executor(tripwire)
    outcome = executor.execute(
        _clean_request(), role_binding=role_binding, resolved_inputs=_resolved_inputs()
    )
    assert outcome.ok is False
    assert outcome.error_code == C.INVALID_START_PAYLOAD
    assert tripwire.calls == 0


@pytest.mark.parametrize("transaction_ref", [None, "", "   ", "none", "None"])
def test_optional_transaction_ref_falls_back_to_run_ref_and_starts_once(transaction_ref):
    # GREEN: transaction_ref is optional — None / empty / the stringified-None
    # sentinel falls back to the run ref (workflow_ref) and still starts exactly
    # once, NOT rejected like the required identity refs.
    fake = FakeTemporalClient()
    surface = P5TemporalControlSurface(P5TemporalRuntimeClient(fake))
    executor = _enabled_executor(surface)
    request = _clean_request()
    request.transaction_ref = transaction_ref
    outcome = executor.execute(
        request, role_binding=_role_binding(), resolved_inputs=_resolved_inputs()
    )
    assert outcome.ok is True
    assert outcome.step_status == "completed"
    assert fake.start_calls == 1


def test_missing_transaction_ref_attr_falls_back_to_run_ref_and_starts_once():
    fake = FakeTemporalClient()
    surface = P5TemporalControlSurface(P5TemporalRuntimeClient(fake))
    executor = _enabled_executor(surface)
    request = _clean_request()
    delattr(request, "transaction_ref")  # optional attribute entirely absent
    outcome = executor.execute(
        request, role_binding=_role_binding(), resolved_inputs=_resolved_inputs()
    )
    assert outcome.ok is True
    assert fake.start_calls == 1
