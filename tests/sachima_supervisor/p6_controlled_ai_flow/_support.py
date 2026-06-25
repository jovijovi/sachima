"""Shared P6-A test builders / fakes (no Temporal).

Reuses the merged WP4 surfaces unmodified — the canonical bounded linear
read-only flow, the run/step/cancel request shapes, and the injected-fake
``StepExecutor`` seam — so the P6-A composition can be driven end-to-end without
a Temporal dependency. Nothing here imports ``temporalio``, Gateway, Feishu, or a
real runner.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from sachima_supervisor.ai_flow_executor import StepExecutionOutcome
from sachima_supervisor.ai_flow_spec import (
    canonical_read_only_workflow_mapping,
    role_binding_digest,
    validate_workflow_spec,
    workflow_spec_digest,
)
from sachima_supervisor.activity_ai_flow_orchestration import (
    AI_FLOW_APPROVAL_TOKEN,
    StepAttemptRequest,
    WorkflowCancellationRequest,
    WorkflowRunRequest,
)
from sachima_supervisor.p5_runtime_adapter import (
    P5_RUNTIME_ADAPTER_IMPLEMENTATION_APPROVAL_TOKEN,
    P5LocalOfflineRuntimeAdapter,
)

SPEC = validate_workflow_spec(canonical_read_only_workflow_mapping())
WSD = workflow_spec_digest(SPEC)
RBD = role_binding_digest(SPEC)
STEP_ORDER = ("architect", "programmer_candidate", "reviewer")
_OUTPUT_CONTRACT = {
    "architect": "architecture_packet",
    "programmer_candidate": "implementation_candidate_analysis",
    "reviewer": "blocker_review",
}


def run_request(**o: Any) -> WorkflowRunRequest:
    base = dict(
        run_id="run_p6_alpha",
        workflow_id=SPEC.workflow_id,
        workflow_spec_digest=WSD,
        role_binding_digest=RBD,
        approval_ref=SPEC.approval_ref,
        transaction_ref="txn_p6_alpha",
        operation_ref="op_p6_alpha",
        idempotency_key="idem_run_p6",
        admission_gate_ref="admission_ref_ok",
        approval_token=AI_FLOW_APPROVAL_TOKEN,
        enabled=True,
        operator_gate=True,
    )
    base.update(o)
    return WorkflowRunRequest(**base)


def step_request(step_id: str, **o: Any) -> StepAttemptRequest:
    base = dict(
        run_id="run_p6_alpha",
        step_id=step_id,
        attempt_index=1,
        workflow_spec_digest=WSD,
        role_binding_digest=RBD,
        input_artifact_digests=(),
        pre_step_gate_ref=f"pre_{step_id}",
        post_step_gate_ref=f"post_{step_id}",
        transaction_ref="txn_p6_alpha",
        operation_ref="op_p6_alpha",
        idempotency_key=f"idem_{step_id}_p6",
        approval_token=AI_FLOW_APPROVAL_TOKEN,
        enabled=True,
        operator_gate=True,
    )
    base.update(o)
    return StepAttemptRequest(**base)


def step_requests_in_order(**common: Any) -> list[StepAttemptRequest]:
    return [step_request(step_id, **common) for step_id in STEP_ORDER]


def cancel_request(**o: Any) -> WorkflowCancellationRequest:
    base = dict(
        cancel_id="cancel_p6_0001",
        run_id="run_p6_alpha",
        scope="active_run",
        transaction_ref="txn_p6_alpha",
        operation_ref="op_p6_alpha",
        idempotency_key="idem_cancel_p6",
        step_id="architect",
        reason_code="operator_requested",
        approval_token=AI_FLOW_APPROVAL_TOKEN,
        enabled=True,
        operator_gate=True,
    )
    base.update(o)
    return WorkflowCancellationRequest(**base)


@dataclass
class DeterministicFakeStepExecutor:
    """Enabled, deterministic, claim-check-only fake StepExecutor.

    Exposes ``enabled`` / ``approval_token`` so the P6 admission precondition
    treats it as an armed runtime executor, and counts every seam call so a test
    can prove a default-off / mismatched admission performed zero executor work.
    """

    enabled: bool = True
    approval_token: str = P5_RUNTIME_ADAPTER_IMPLEMENTATION_APPROVAL_TOKEN
    mode: str = "success"
    calls: int = 0
    control_calls: int = 0

    def execute(self, request: Any, *, role_binding: Any, resolved_inputs: Any) -> StepExecutionOutcome:
        self.calls += 1
        if self.mode == "terminal_failure":
            return StepExecutionOutcome(
                ok=False, step_status="failed_terminal", artifact_refs=(),
                error_code="activity_step_failed", retryable=False,
            )
        kind = _OUTPUT_CONTRACT[request.step_id]
        body = f"p6 deterministic {request.step_id} body".encode()
        artifact = {
            "artifact_id": f"p6_artifact_{request.step_id}",
            "producer_step_id": request.step_id,
            "content_digest": "sha256:" + hashlib.sha256(body).hexdigest(),
            "artifact_kind": kind,
            "byte_count": len(body),
            "created_at_ref": "created_at_ref_p6_0001",
        }
        return StepExecutionOutcome(
            ok=True, step_status="completed", artifact_refs=(artifact,),
            evidence_ref=f"evidence_ref_{request.step_id}",
        )

    def query(self, *, run_id: str, step_id: str) -> dict[str, Any]:
        self.control_calls += 1
        return {"type": "fake_snapshot", "state": "completed", "run_ref": run_id, "step_ref": step_id}

    def cancel(self, *, run_id, step_id, scope, idempotency_key, interrupt_outcome=None) -> StepExecutionOutcome:
        self.control_calls += 1
        return StepExecutionOutcome(
            ok=False, step_status="cancel_ambiguous", artifact_refs=(),
            error_code="active_run_cancellation_watch", ambiguous=True,
        )

    def recover(self, *, run_id: str, step_id: str) -> dict[str, Any]:
        self.control_calls += 1
        return {"type": "fake_snapshot", "state": "completed", "run_ref": run_id, "step_ref": step_id}

    def close(self) -> dict[str, Any]:
        self.control_calls += 1
        return {"type": "fake_snapshot", "state": "closed"}


@dataclass
class CountingExecutor:
    """Wrap a real StepExecutor and count every seam call (admission proof)."""

    wrapped: Any
    execute_calls: int = 0
    control_calls: int = 0

    @property
    def enabled(self) -> Any:
        return getattr(self.wrapped, "enabled", None)

    @property
    def approval_token(self) -> Any:
        return getattr(self.wrapped, "approval_token", None)

    def execute(self, request: Any, *, role_binding: Any, resolved_inputs: Any) -> Any:
        self.execute_calls += 1
        return self.wrapped.execute(request, role_binding=role_binding, resolved_inputs=resolved_inputs)

    def query(self, **kw: Any) -> Any:
        self.control_calls += 1
        return self.wrapped.query(**kw)

    def cancel(self, **kw: Any) -> Any:
        self.control_calls += 1
        return self.wrapped.cancel(**kw)

    def recover(self, **kw: Any) -> Any:
        self.control_calls += 1
        return self.wrapped.recover(**kw)

    def close(self) -> Any:
        self.control_calls += 1
        return self.wrapped.close()

    @property
    def total_calls(self) -> int:
        return self.execute_calls + self.control_calls


def make_local_adapter() -> P5LocalOfflineRuntimeAdapter:
    """An enabled, approved P5 local/offline runtime adapter (no Temporal)."""

    return P5LocalOfflineRuntimeAdapter(
        enabled=True,
        approval_token=P5_RUNTIME_ADAPTER_IMPLEMENTATION_APPROVAL_TOKEN,
    )
