"""P6-A translation reuse (FR3/FR4, Gate 3/5 — no real Temporal Worker).

Proves the composition injects the existing ``P5TemporalStepExecutor`` seam — the
WP4 ``request -> StartRequest`` translation is the executor's job, not a P6 bridge
— and that unsafe/raw material is rejected by that seam **before** any
control-surface (Temporal) call. A spy control surface stands in for the durable
backend so the real translation runs without a Worker.
"""

from __future__ import annotations

import pathlib

from sachima_supervisor.ai_flow_store import AiFlowRunStore
from sachima_supervisor.p5_temporal import contracts as C
from sachima_supervisor.p5_temporal.step_executor import (
    P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
    P5TemporalStepExecutor,
)
from sachima_supervisor.p6_controlled_ai_flow import (
    P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN,
    P6ControlledAiFlowSession,
)

from tests.sachima_supervisor.p6_controlled_ai_flow._support import (
    SPEC,
    run_request,
    step_request,
)

_P6_SOURCE = (
    pathlib.Path(__file__).resolve().parents[4]
    / "sachima_supervisor"
    / "p6_controlled_ai_flow.py"
)


class SpyControlSurface:
    """No-Worker stand-in: records calls and returns controlled-deterministic
    success snapshots so the real executor translation can run end-to-end."""

    def __init__(self) -> None:
        self.start_calls = 0
        self.other_calls = 0
        self.last_start_request = None

    async def start(self, start_request, *, workflow_id):
        self.start_calls += 1
        self.last_start_request = start_request
        return {
            "ok": True,
            "op": "start",
            "workflow_id": workflow_id,
            "snapshot": {
                "state": "completed",
                "artifact_refs": (C.deterministic_artifact_ref(start_request),),
            },
            "error_code": None,
            "replayed": False,
        }

    async def query(self, *, workflow_id):
        self.other_calls += 1
        return {"ok": False, "op": "query", "workflow_id": workflow_id, "snapshot": None, "error_code": C.RUNTIME_NOT_FOUND}

    async def cancel(self, *, workflow_id, update):
        self.other_calls += 1
        return {"ok": True, "op": "cancel", "workflow_id": workflow_id, "snapshot": None, "error_code": None}

    async def recover(self, *, workflow_id):
        self.other_calls += 1
        return {"ok": False, "op": "recover", "workflow_id": workflow_id, "snapshot": None, "error_code": C.RUNTIME_NOT_FOUND}

    async def close(self):
        self.other_calls += 1
        return {"ok": True, "op": "close", "snapshot": None, "error_code": None}


def _temporal_executor(surface):
    return P5TemporalStepExecutor(
        control_surface=surface,
        enabled=True,
        approval_token=P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN,
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


def test_composition_drives_the_executor_translation_seam():
    surface = SpyControlSurface()
    session = _session(_temporal_executor(surface))
    session.create_run(run_request())
    result = session.step(step_request("architect"))
    assert result.status == "completed"
    # The translation happened *inside* the executor: the control surface received
    # a sanitized C.StartRequest, never a raw WP4 request.
    assert surface.start_calls == 1
    assert isinstance(surface.last_start_request, C.StartRequest)
    assert surface.last_start_request.run_ref == "run_p6_alpha"
    assert surface.last_start_request.step_ref == "architect"


def test_unsafe_resolved_input_is_rejected_before_any_temporal_call():
    surface = SpyControlSurface()
    executor = _temporal_executor(surface)
    # Drive the seam directly with raw/unsafe resolved-input material.
    unsafe_input = {
        "artifact_id": "claim_ref_x",
        "producer_step_id": "root",
        "content_digest": "sha256:" + "a" * 64,
        "artifact_kind": "input",
        "byte_count": 64,
        "created_at_ref": "created_at_ref_0001",
        "signed_url": "https://example.invalid/blob?x-amz-signature=deadbeef",
    }

    class _Req:
        run_id = "run_p6_alpha"
        step_id = "architect"
        attempt_index = 1
        idempotency_key = "idem_architect_p6"
        transaction_ref = "txn_p6_alpha"
        operation_ref = "op_p6_alpha"
        input_artifact_digests = ("sha256:" + "a" * 64,)

    class _Role:
        role_key = "sachima_claude_read_only_reviewer"

    outcome = executor.execute(_Req(), role_binding=_Role(), resolved_inputs=(unsafe_input,))
    assert outcome.ok is False
    assert outcome.error_code == C.RUNTIME_UNSAFE_MATERIAL
    # The unsafe material never reached the durable backend.
    assert surface.start_calls == 0


def test_p6_source_does_not_reimplement_the_translation_bridge():
    src = _P6_SOURCE.read_text(encoding="utf-8")
    # No redundant adapter/bridge: P6 must not build StartRequests / claim-check
    # refs itself — it delegates translation to the injected executor seam.
    for forbidden in ("build_start_request", "artifact_ref_to_claim_check", "StartRequest(", "def _translate"):
        assert forbidden not in src, f"P6 must not reimplement translation: found {forbidden!r}"
