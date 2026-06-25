"""T6 — oracle conformance (FR5, Gate E).

``P5TemporalStepExecutor`` (backed by the fake control surface) must be
behaviorally substitutable for ``P5LocalOfflineRuntimeAdapter`` across the shared
public surface: ``execute`` outcome shape (claim-check refs only, no business
verdict), idempotency-fingerprint dedupe, same-step conflict rejection,
``query`` / ``cancel`` / ``recover`` / ``close`` / ``history_projection`` /
``serialized_history_bytes``, and the WP3b ``active_run_cancellation_watch ->
cancel_ambiguous`` mapping. Backend-specific bytes (digests, snapshot ``type``)
differ; the conformance axes are the *semantics*.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sachima_supervisor.ai_flow_executor import StepExecutionOutcome
from sachima_supervisor.p5_runtime_adapter import (
    P5_RUNTIME_ADAPTER_IMPLEMENTATION_APPROVAL_TOKEN,
    P5LocalOfflineRuntimeAdapter,
)
from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p5_temporal import (
    P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
    P5TemporalStepExecutor,
)
from sachima_supervisor.p5_temporal.control_surface import P5TemporalControlSurface
from sachima_supervisor.p5_temporal.runtime_client import P5TemporalRuntimeClient
from tests.sachima_supervisor.p5_temporal._fake_temporal import FakeTemporalClient

_SAFE_ARTIFACT_KEYS = {
    "artifact_id",
    "producer_step_id",
    "content_digest",
    "artifact_kind",
    "byte_count",
    "created_at_ref",
}


def _request(*, run_id="run_p5_demo_0001", step_id="architect", idempotency="idem_p5_demo_0001", attempt=1):
    digest = "sha256:" + "a" * 64
    return SimpleNamespace(
        run_id=run_id,
        step_id=step_id,
        attempt_index=attempt,
        idempotency_key=idempotency,
        transaction_ref="tx_p5_demo_0001",
        operation_ref="op_p5_demo_0001",
        workflow_spec_digest="sha256:" + "c" * 64,
        role_binding_digest="sha256:" + "d" * 64,
        input_artifact_digests=(digest,),
    )


def _role_binding():
    return SimpleNamespace(role_key="sachima.claude.read_only_reviewer", logical_role="architect")


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


def _oracle():
    return P5LocalOfflineRuntimeAdapter(
        enabled=True, approval_token=P5_RUNTIME_ADAPTER_IMPLEMENTATION_APPROVAL_TOKEN
    )


def _temporal():
    surface = P5TemporalControlSurface(P5TemporalRuntimeClient(FakeTemporalClient()))
    return P5TemporalStepExecutor(
        control_surface=surface,
        enabled=True,
        approval_token=P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
    )


def _normalize_outcome(outcome: StepExecutionOutcome) -> dict:
    assert isinstance(outcome, StepExecutionOutcome)
    # WP4: success carries NO business verdict field — the dataclass simply has none.
    assert not hasattr(outcome, "business_verdict")
    artifacts = tuple(outcome.artifact_refs)
    for ref in artifacts:
        assert set(ref) == _SAFE_ARTIFACT_KEYS
        assert C._SHA256_DIGEST_RE.fullmatch(ref["content_digest"])
    return {
        "ok": outcome.ok,
        "step_status": outcome.step_status,
        "n_artifacts": len(artifacts),
        "has_evidence": bool(outcome.evidence_ref) and bool(outcome.evidence_digest),
        "ambiguous": outcome.ambiguous,
        "interrupted": outcome.interrupted,
        "cleanup_verified": outcome.cleanup_verified,
    }


@pytest.mark.parametrize("make", [_oracle, _temporal], ids=["oracle", "temporal"])
def test_execute_success_shape_is_substitutable(make):
    adapter = make()
    outcome = adapter.execute(_request(), role_binding=_role_binding(), resolved_inputs=_resolved_inputs())
    norm = _normalize_outcome(outcome)
    assert norm["ok"] is True
    assert norm["step_status"] == "completed"
    assert norm["n_artifacts"] == 1
    assert norm["has_evidence"] is True


@pytest.mark.parametrize("make", [_oracle, _temporal], ids=["oracle", "temporal"])
def test_duplicate_identical_execute_replays_same_outcome(make):
    adapter = make()
    out1 = adapter.execute(_request(), role_binding=_role_binding(), resolved_inputs=_resolved_inputs())
    out2 = adapter.execute(_request(), role_binding=_role_binding(), resolved_inputs=_resolved_inputs())
    assert _normalize_outcome(out1) == _normalize_outcome(out2)
    # identical artifact ref content on replay
    assert out1.artifact_refs[0]["content_digest"] == out2.artifact_refs[0]["content_digest"]


@pytest.mark.parametrize("make", [_oracle, _temporal], ids=["oracle", "temporal"])
def test_same_step_divergent_request_fails_closed(make):
    adapter = make()
    adapter.execute(_request(idempotency="idem_p5_demo_0001"), role_binding=_role_binding(), resolved_inputs=_resolved_inputs())
    diverged = adapter.execute(
        _request(idempotency="idem_p5_demo_0002"),  # same run/step, divergent idempotency
        role_binding=_role_binding(),
        resolved_inputs=_resolved_inputs(),
    )
    assert diverged.ok is False
    assert diverged.error_code is not None  # a conflict-family stable code


@pytest.mark.parametrize("make", [_oracle, _temporal], ids=["oracle", "temporal"])
def test_query_recover_close_substitutable(make):
    adapter = make()
    adapter.execute(_request(), role_binding=_role_binding(), resolved_inputs=_resolved_inputs())
    snap = adapter.query(run_id="run_p5_demo_0001", step_id="architect")
    assert snap["state"] == "completed"
    assert len(snap["artifact_refs"]) == 1
    recovered = adapter.recover(run_id="run_p5_demo_0001", step_id="architect")
    assert recovered["state"] == "completed"
    closed = adapter.close()
    assert closed["state"] == "closed"


@pytest.mark.parametrize("make", [_oracle, _temporal], ids=["oracle", "temporal"])
def test_active_run_cancellation_watch_maps_to_ambiguous(make):
    adapter = make()
    adapter.execute(_request(), role_binding=_role_binding(), resolved_inputs=_resolved_inputs())
    watch = adapter.cancel(
        run_id="run_p5_demo_0001",
        step_id="architect",
        scope="active_run",
        idempotency_key="idem_cancel_0001",
        interrupt_outcome=None,
    )
    assert watch.ok is False
    assert watch.step_status == "cancel_ambiguous"
    assert watch.ambiguous is True
    assert watch.error_code == "active_run_cancellation_watch"


@pytest.mark.parametrize("make", [_oracle, _temporal], ids=["oracle", "temporal"])
def test_confirmed_cancellation_substitutable(make):
    adapter = make()
    adapter.execute(_request(), role_binding=_role_binding(), resolved_inputs=_resolved_inputs())
    confirmed = adapter.cancel(
        run_id="run_p5_demo_0001",
        step_id="architect",
        scope="active_run",
        idempotency_key="idem_cancel_0002",
        interrupt_outcome=StepExecutionOutcome(
            ok=True, step_status="cancelled", artifact_refs=(), interrupted=True, cleanup_verified=True
        ),
    )
    assert confirmed.ok is True
    assert confirmed.step_status == "cancelled"
    assert confirmed.interrupted is True and confirmed.cleanup_verified is True


@pytest.mark.parametrize("make", [_oracle, _temporal], ids=["oracle", "temporal"])
def test_unsupported_cancel_scope_fails_closed(make):
    adapter = make()
    adapter.execute(_request(), role_binding=_role_binding(), resolved_inputs=_resolved_inputs())
    rejected = adapter.cancel(
        run_id="run_p5_demo_0001",
        step_id="architect",
        scope="between_step",
        idempotency_key="idem_cancel_0003",
    )
    assert rejected.ok is False


@pytest.mark.parametrize("make", [_oracle, _temporal], ids=["oracle", "temporal"])
def test_history_projection_and_serialized_bytes_are_sanitized(make):
    adapter = make()
    adapter.execute(_request(), role_binding=_role_binding(), resolved_inputs=_resolved_inputs())
    projection = adapter.history_projection()
    assert isinstance(projection, dict)
    assert C.scan_projection_for_leak(projection) is None
    raw = adapter.serialized_history_bytes()
    assert isinstance(raw, bytes)
    assert C.scan_bytes_for_leak(raw) is None
