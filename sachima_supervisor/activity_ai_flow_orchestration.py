"""Controlled AI FLOW orchestrator (WP4 slice 1, FR2/FR4/FR5/FR6).

Local/offline only, default-off. Wires the validated workflow spec through
operator gates, the lock-guarded CAS step store, the injected executor seam,
claim-check artifacts, and a sanitized evidence projection. There is no real
runner, no acpx/npx, no subprocess, no socket, no Gateway/Feishu, and no
auto-routing: the graph is fixed before any step runs and no model output ever
chooses a successor.

Cancellation preserves the WP3b active-run WATCH: between-step cancellation is
deterministic; active-run cancellation only claims ``cancelled`` when the
injected interrupt outcome reports ``interrupted is True and cleanup_verified is
True``, otherwise it records ``cancel_ambiguous`` /
``active_run_cancellation_watch`` with no artifact propagation and no relaunch.

This module imports only the sibling WP4 modules (spec/store/gates/artifacts/
executor/evidence); it never imports the real cancellation bridge.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .ai_flow_artifacts import (
    AiFlowArtifactError,
    artifact_ref_projection,
    verify_artifact_ref,
)
from .ai_flow_evidence import WorkflowEvidence, build_workflow_evidence
from .ai_flow_executor import StepExecutionOutcome, StepExecutor
from .ai_flow_gates import check_gate, gate_decision_projection
from .ai_flow_spec import (
    RoleBinding,
    StepSpec,
    WorkflowSpec,
    role_binding_digest,
    workflow_spec_digest,
)
from .ai_flow_store import (
    STEP_CANCELLED,
    STEP_CANCEL_AMBIGUOUS,
    STEP_CLAIMED,
    STEP_COMPLETED,
    STEP_FAILED_RETRYABLE,
    STEP_FAILED_TERMINAL,
    STEP_GATE_BLOCKED,
    STEP_WATCH,
    AiFlowError,
    AiFlowRunStore,
    build_cancel_state,
    build_run_state,
    build_step_state,
    step_fingerprint,
)

# --------------------------------------------------------------------------- #
# Public approval token (exact §11 phrase)
# --------------------------------------------------------------------------- #
AI_FLOW_APPROVAL_TOKEN = (
    "approve_agent_run_supervisor_sachima_controlled_ai_flow_local_offline_"
    "orchestration_implementation_read_only_roles_only_bounded_steps_injected_"
    "fakes_first_no_real_workflow_execution_no_additional_acpx_invocation_no_"
    "write_roles_no_auto_routing_no_live_no_gateway_no_feishu_no_production_"
    "config_no_real_delivery"
)

_CANCEL_SCOPES = ("between_step", "active_run")
_WATCH_CODE = "active_run_cancellation_watch"

#: A run is only schedulable for new steps while it is still ``created``. Any
#: terminal/parked/ambiguous/cancelled run status fails closed before claim.
_SCHEDULABLE_RUN_STATUSES = frozenset({"created"})

_EVIDENCE_REF_RE = re.compile(r"^[a-z][a-z0-9_:-]{0,127}$")
_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_CODE_RE = re.compile(r"^[a-z][a-z0-9_:-]{0,63}$")
_ARTIFACT_REF_KEYS = (
    "artifact_id",
    "producer_step_id",
    "content_digest",
    "artifact_kind",
    "byte_count",
    "created_at_ref",
)


# --------------------------------------------------------------------------- #
# Error + requests + results
# --------------------------------------------------------------------------- #
class AiFlowOrchestrationError(Exception):
    """Fail-closed orchestration error carrying a stable code."""

    def __init__(self, error_code: str, message: str = "") -> None:
        self.error_code = error_code
        super().__init__(message or error_code)


@dataclass(frozen=True)
class WorkflowRunRequest:
    run_id: str
    workflow_id: str
    workflow_spec_digest: str
    role_binding_digest: str
    approval_ref: str
    transaction_ref: str
    operation_ref: str
    idempotency_key: str
    admission_gate_ref: str | None = None
    approval_token: str = ""
    enabled: bool = False
    operator_gate: bool = False
    lease_id: str | None = None
    lease_epoch: int = 0
    lease_holder_ref: str | None = None
    expected_state_version: int = 0


@dataclass(frozen=True)
class StepAttemptRequest:
    run_id: str
    step_id: str
    attempt_index: int
    workflow_spec_digest: str
    role_binding_digest: str
    transaction_ref: str
    operation_ref: str
    idempotency_key: str
    input_artifact_digests: tuple[str, ...] = ()
    pre_step_gate_ref: str | None = None
    post_step_gate_ref: str | None = None
    approval_token: str = ""
    enabled: bool = False
    operator_gate: bool = False
    lease_id: str | None = None
    lease_epoch: int = 0
    lease_holder_ref: str | None = None
    expected_state_version: int = 0


@dataclass(frozen=True)
class WorkflowCancellationRequest:
    cancel_id: str
    run_id: str
    scope: str
    transaction_ref: str
    operation_ref: str
    idempotency_key: str
    step_id: str | None = None
    reason_code: str | None = None
    approval_token: str = ""
    enabled: bool = False
    operator_gate: bool = False
    lease_id: str | None = None
    lease_epoch: int = 0
    lease_holder_ref: str | None = None


class _RecordResult:
    def __init__(self, state: Mapping[str, Any]) -> None:
        self._state: dict[str, Any] = dict(state)

    def to_durable_state(self) -> dict[str, Any]:
        return dict(self._state)


class WorkflowRunResult(_RecordResult):
    @property
    def run_id(self) -> str:
        return self._state["run_id"]

    @property
    def status(self) -> str:
        return self._state["status"]

    @property
    def error_code(self) -> str | None:
        return self._state["error_code"]


class StepRecordResult(_RecordResult):
    @property
    def step_id(self) -> str:
        return self._state["step_id"]

    @property
    def status(self) -> str:
        return self._state["status"]

    @property
    def ok(self) -> bool:
        return self._state["ok"]

    @property
    def error_code(self) -> str | None:
        return self._state["error_code"]


class CancellationRecordResult(_RecordResult):
    @property
    def cancel_id(self) -> str:
        return self._state["cancel_id"]

    @property
    def status(self) -> str:
        return self._state["status"]

    @property
    def error_code(self) -> str | None:
        return self._state["error_code"]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _digest_hex(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_enabled_and_approved(request: Any) -> None:
    if request.enabled is not True:
        raise AiFlowOrchestrationError("activity_disabled", "controlled AI FLOW is default-off")
    if request.approval_token != AI_FLOW_APPROVAL_TOKEN:
        raise AiFlowOrchestrationError(
            "activity_approval_mismatch", "exact controlled AI FLOW approval token required"
        )


def _safe_evidence_ref(value: Any) -> str | None:
    if type(value) is str and _EVIDENCE_REF_RE.fullmatch(value) is not None:
        return value
    return None


def _safe_digest(value: Any) -> str | None:
    if type(value) is str and _SHA256_DIGEST_RE.fullmatch(value) is not None:
        return value
    return None


def _safe_code(value: Any) -> str | None:
    if type(value) is str and _STABLE_CODE_RE.fullmatch(value) is not None:
        return value
    return None


def _resolve_step(spec: WorkflowSpec, step_id: str) -> StepSpec:
    for step in spec.steps:
        if step.step_id == step_id:
            return step
    raise AiFlowOrchestrationError("activity_unknown_step", "step id is not in the workflow spec")


def _resolve_binding(spec: WorkflowSpec, logical_role: str) -> RoleBinding:
    for role in spec.roles:
        if role.logical_role == logical_role:
            return role
    raise AiFlowOrchestrationError("activity_missing_role", "no role binding for the step")


def _producer_of(spec: WorkflowSpec, contract: str) -> str | None:
    for step in spec.steps:
        if step.output_contract == contract:
            return step.step_id
    return None


def _clean_artifact_ref(projection: Mapping[str, Any]) -> dict[str, Any]:
    return {key: projection[key] for key in _ARTIFACT_REF_KEYS}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def create_workflow_run(
    request: WorkflowRunRequest, *, spec: WorkflowSpec, store: AiFlowRunStore
) -> WorkflowRunResult:
    """Admit and create a workflow run behind the fail-closed admission gate."""

    _check_enabled_and_approved(request)
    if (
        request.workflow_id != spec.workflow_id
        or request.workflow_spec_digest != workflow_spec_digest(spec)
        or request.role_binding_digest != role_binding_digest(spec)
        or request.approval_ref != spec.approval_ref
    ):
        raise AiFlowOrchestrationError(
            "activity_spec_binding_mismatch", "run request does not bind the validated spec"
        )
    admission = check_gate(
        "admission", operator_gate=request.operator_gate, gate_ref=request.admission_gate_ref
    )
    if not admission.granted:
        raise AiFlowOrchestrationError(
            "activity_admission_gate_failed", "admission gate is not granted; run not created"
        )

    run_state = build_run_state(
        ok=False,
        status="created",
        run_id=request.run_id,
        workflow_id=request.workflow_id,
        workflow_spec_digest=request.workflow_spec_digest,
        role_binding_digest=request.role_binding_digest,
        approval_ref=request.approval_ref,
        admission_gate_ref=admission.gate_ref,
        transaction_ref=request.transaction_ref,
        operation_ref=request.operation_ref,
        idempotency_key=request.idempotency_key,
        lease_id=request.lease_id,
        lease_epoch=request.lease_epoch,
        lease_holder_ref=request.lease_holder_ref,
        state_version=request.expected_state_version,
    )
    run_fp = _digest_hex(
        {
            "run_id": request.run_id,
            "workflow_spec_digest": request.workflow_spec_digest,
            "approval_ref": request.approval_ref,
            "admission_gate_ref": admission.gate_ref,
        }
    )
    _, stored = store.record_run(
        run_id=request.run_id,
        idempotency_key=request.idempotency_key,
        fingerprint=run_fp,
        state=run_state,
    )
    store.record_gate(run_id=request.run_id, projection=gate_decision_projection(admission))
    return WorkflowRunResult(stored)


def query_workflow_run(store: AiFlowRunStore, *, run_id: str) -> WorkflowRunResult:
    state = store.get_run(run_id)
    if state is None:
        raise AiFlowOrchestrationError("activity_not_found", "no workflow run for the given id")
    return WorkflowRunResult(state)


def list_workflow_steps(store: AiFlowRunStore, *, run_id: str) -> tuple[StepRecordResult, ...]:
    return tuple(StepRecordResult(state) for state in store.list_steps(run_id))


def _build_step_terminal(
    request: StepAttemptRequest,
    step: StepSpec,
    binding: RoleBinding,
    *,
    status: str,
    ok: bool,
    error_code: str | None = None,
    retryable: bool = False,
    artifact_ref_count: int = 0,
    output_artifact_id: str | None = None,
    output_artifact_digest: str | None = None,
    output_artifact_kind: str | None = None,
    evidence_ref: str | None = None,
    evidence_digest: str | None = None,
) -> dict[str, Any]:
    return build_step_state(
        status=status,
        ok=ok,
        run_id=request.run_id,
        step_id=request.step_id,
        logical_role=step.logical_role,
        role_key=binding.role_key,
        workflow_spec_digest=request.workflow_spec_digest,
        role_binding_digest=request.role_binding_digest,
        idempotency_key=request.idempotency_key,
        attempt_index=request.attempt_index,
        input_artifact_digests=request.input_artifact_digests,
        artifact_ref_count=artifact_ref_count,
        output_artifact_id=output_artifact_id,
        output_artifact_digest=output_artifact_digest,
        output_artifact_kind=output_artifact_kind,
        evidence_ref=evidence_ref,
        evidence_digest=evidence_digest,
        error_code=error_code,
        retryable=retryable,
    )


def _resolve_inputs(
    spec: WorkflowSpec, step: StepSpec, store: AiFlowRunStore, run_id: str
) -> tuple[Mapping[str, Any], ...]:
    resolved: list[Mapping[str, Any]] = []
    for input_ref in step.input_refs:
        if not step.depends_on:
            continue  # root steps consume external workflow inputs
        producer = _producer_of(spec, input_ref)
        if producer is None:
            raise AiFlowOrchestrationError("activity_precondition_unmet", "no producer for input")
        artifact = store.find_artifact(
            run_id=run_id, artifact_kind=input_ref, producer_step_id=producer
        )
        if artifact is None:
            raise AiFlowOrchestrationError(
                "activity_precondition_unmet", "upstream artifact not propagated"
            )
        try:
            verify_artifact_ref(
                _clean_artifact_ref(artifact),
                expected_kind=input_ref,
                expected_producer=producer,
                max_bytes=spec.bounds.max_artifact_bytes,
            )
        except AiFlowArtifactError as exc:
            raise AiFlowOrchestrationError(
                "activity_artifact_integrity_failed", "upstream artifact failed re-verification"
            ) from exc
        resolved.append(artifact)
    return tuple(resolved)


def step_workflow_run(
    request: StepAttemptRequest,
    *,
    spec: WorkflowSpec,
    store: AiFlowRunStore,
    executor: StepExecutor,
) -> StepRecordResult:
    """Run one bounded step behind pre-step / post-step gates and the CAS claim."""

    _check_enabled_and_approved(request)
    run = store.get_run(request.run_id)
    if run is None:
        raise AiFlowOrchestrationError("activity_not_found", "workflow run does not exist")
    # Blocker 1: reject any step attempt once the run is no longer schedulable
    # (terminal/parked/ambiguous/cancelled) before claim/executor.
    if run["status"] not in _SCHEDULABLE_RUN_STATUSES:
        raise AiFlowOrchestrationError(
            "activity_run_not_schedulable", "run is not in a schedulable state"
        )
    # Blocker 2: bind the attempt to the resident run *and* validated spec
    # digests before any claim/executor; a divergent digest fails closed.
    if (
        request.workflow_spec_digest != workflow_spec_digest(spec)
        or request.role_binding_digest != role_binding_digest(spec)
        or request.workflow_spec_digest != run["workflow_spec_digest"]
        or request.role_binding_digest != run["role_binding_digest"]
    ):
        raise AiFlowOrchestrationError(
            "activity_spec_binding_mismatch",
            "step request does not bind the resident run / validated spec digests",
        )
    step = _resolve_step(spec, request.step_id)
    binding = _resolve_binding(spec, step.logical_role)

    fingerprint = step_fingerprint(
        run_id=request.run_id,
        step_id=request.step_id,
        workflow_spec_digest=request.workflow_spec_digest,
        role_binding_digest=request.role_binding_digest,
        input_artifact_digests=request.input_artifact_digests,
        approval_ref=request.pre_step_gate_ref or spec.approval_ref,
        attempt_index=request.attempt_index,
    )
    claim_state = _build_step_terminal(
        request, step, binding, status=STEP_CLAIMED, ok=False
    )
    disposition, resident = store.claim_step(
        run_id=request.run_id,
        step_id=request.step_id,
        idempotency_key=request.idempotency_key,
        fingerprint=fingerprint,
        state=claim_state,
    )
    if disposition == "replayed":
        return StepRecordResult(resident)

    def _finalize(state: dict[str, Any]) -> StepRecordResult:
        store.finalize_step(
            run_id=request.run_id,
            step_id=request.step_id,
            idempotency_key=request.idempotency_key,
            fingerprint=fingerprint,
            state=state,
        )
        return StepRecordResult(state)

    # Pre-step gate (no executor call when not granted).
    pre = check_gate(
        "pre_step",
        operator_gate=request.operator_gate,
        gate_ref=request.pre_step_gate_ref,
        step_id=request.step_id,
    )
    store.record_gate(run_id=request.run_id, projection=gate_decision_projection(pre))
    if not pre.granted:
        return _finalize(
            _build_step_terminal(
                request, step, binding, status=STEP_GATE_BLOCKED, ok=False,
                error_code="activity_step_gate_blocked",
            )
        )

    # Resolve & re-verify upstream inputs (claim-check handoff).
    try:
        resolved_inputs = _resolve_inputs(spec, step, store, request.run_id)
    except AiFlowOrchestrationError as exc:
        return _finalize(
            _build_step_terminal(
                request, step, binding, status=STEP_FAILED_TERMINAL, ok=False,
                error_code=exc.error_code if exc.error_code in (
                    "activity_precondition_unmet", "activity_artifact_integrity_failed",
                ) else "activity_precondition_unmet",
            )
        )

    # Blocker 2: bind the declared input artifact digests to the digests
    # actually resolved from upstream before the executor runs. A divergence
    # fails closed terminally with no executor call and no propagation.
    resolved_digests = sorted(item["content_digest"] for item in resolved_inputs)
    if sorted(request.input_artifact_digests) != resolved_digests:
        return _finalize(
            _build_step_terminal(
                request, step, binding, status=STEP_FAILED_TERMINAL, ok=False,
                error_code="activity_precondition_unmet",
            )
        )

    # Execute (injected seam only).
    try:
        outcome = executor.execute(request, role_binding=binding, resolved_inputs=resolved_inputs)
    except Exception:
        return _finalize(
            _build_step_terminal(
                request, step, binding, status=STEP_FAILED_RETRYABLE, ok=False,
                error_code="activity_step_failed", retryable=True,
            )
        )
    if not isinstance(outcome, StepExecutionOutcome) or outcome.ok is not True:
        retryable = bool(getattr(outcome, "retryable", False))
        return _finalize(
            _build_step_terminal(
                request, step, binding,
                status=STEP_FAILED_RETRYABLE if retryable else STEP_FAILED_TERMINAL,
                ok=False, error_code="activity_step_failed", retryable=retryable,
            )
        )

    # Blocker (mid-step race): re-check the resident run state after the executor
    # returns. A cancellation that landed *during* execution leaves the run no
    # longer schedulable; finalize the step fail-closed (cancel_ambiguous /
    # active-run WATCH) with no post-step gate, no artifact propagation, and no
    # relaunch rather than trusting the executor's output. A clean ``cancelled``
    # is reserved for the confirmed active-run cancellation path; here we fail
    # closed to the WATCH.
    run_after = store.get_run(request.run_id)
    if run_after is None or run_after["status"] not in _SCHEDULABLE_RUN_STATUSES:
        return _finalize(
            _build_step_terminal(
                request, step, binding, status=STEP_CANCEL_AMBIGUOUS, ok=False,
                error_code=_WATCH_CODE,
            )
        )

    # Post-step gate (no artifact propagation when not granted).
    post = check_gate(
        "post_step",
        operator_gate=request.operator_gate,
        gate_ref=request.post_step_gate_ref,
        step_id=request.step_id,
    )
    store.record_gate(run_id=request.run_id, projection=gate_decision_projection(post))
    if not post.granted:
        return _finalize(
            _build_step_terminal(
                request, step, binding, status=STEP_GATE_BLOCKED, ok=False,
                error_code="activity_step_gate_blocked",
            )
        )

    # Claim-check verify + propagate exactly one output artifact.
    try:
        verified = _verify_single_output(spec, step, outcome)
    except AiFlowArtifactError:
        return _finalize(
            _build_step_terminal(
                request, step, binding, status=STEP_FAILED_TERMINAL, ok=False,
                error_code="activity_artifact_integrity_failed",
            )
        )
    completed_state = _build_step_terminal(
        request, step, binding, status=STEP_COMPLETED, ok=True,
        artifact_ref_count=1,
        output_artifact_id=verified.artifact_id,
        output_artifact_digest=verified.content_digest,
        output_artifact_kind=verified.artifact_kind,
        evidence_ref=_safe_evidence_ref(outcome.evidence_ref),
        evidence_digest=_safe_digest(outcome.evidence_digest),
    )
    non_schedulable_state = _build_step_terminal(
        request, step, binding, status=STEP_CANCEL_AMBIGUOUS, ok=False,
        error_code=_WATCH_CODE,
    )
    stored = store.finalize_step_with_artifact_if_run_schedulable(
        run_id=request.run_id,
        step_id=request.step_id,
        idempotency_key=request.idempotency_key,
        fingerprint=fingerprint,
        state=completed_state,
        artifact_projection=artifact_ref_projection(verified),
        non_schedulable_state=non_schedulable_state,
        schedulable_statuses=_SCHEDULABLE_RUN_STATUSES,
    )
    return StepRecordResult(stored)


def _verify_single_output(spec: WorkflowSpec, step: StepSpec, outcome: StepExecutionOutcome):
    if len(outcome.artifact_refs) != 1:
        raise AiFlowArtifactError("artifact_count_invalid", "slice 1 requires exactly one output")
    return verify_artifact_ref(
        outcome.artifact_refs[0],
        expected_kind=step.output_contract,
        expected_producer=step.step_id,
        max_bytes=spec.bounds.max_artifact_bytes,
    )


def _run_status_state(run: Mapping[str, Any], status: str) -> dict[str, Any]:
    return build_run_state(
        ok=(status == "succeeded"),
        status=status,
        run_id=run["run_id"],
        workflow_id=run["workflow_id"],
        workflow_spec_digest=run["workflow_spec_digest"],
        role_binding_digest=run["role_binding_digest"],
        approval_ref=run["approval_ref"],
        admission_gate_ref=run["admission_gate_ref"],
        transaction_ref=run["transaction_ref"],
        operation_ref=run["operation_ref"],
        idempotency_key=run["idempotency_key"],
        lease_id=run["lease_id"],
        lease_epoch=run["lease_epoch"],
        lease_holder_ref=run["lease_holder_ref"],
        state_version=run["state_version"] + 1,
    )


def _update_run_status(store: AiFlowRunStore, run: Mapping[str, Any], status: str) -> None:
    store.update_run(run_id=run["run_id"], state=_run_status_state(run, status))


def request_workflow_cancellation(
    request: WorkflowCancellationRequest,
    *,
    store: AiFlowRunStore,
    interrupt_outcome: StepExecutionOutcome | None = None,
) -> CancellationRecordResult:
    """Cancel deterministically between steps; preserve the WP3b active-run WATCH."""

    _check_enabled_and_approved(request)
    if request.operator_gate is not True:
        raise AiFlowOrchestrationError("activity_precondition_unmet", "operator gate is required")
    run = store.get_run(request.run_id)
    if run is None:
        raise AiFlowOrchestrationError("activity_not_found", "workflow run does not exist")
    if request.scope not in _CANCEL_SCOPES:
        raise AiFlowOrchestrationError("activity_unsupported_cancel_scope", "unknown cancel scope")

    reason_code = _safe_code(request.reason_code)
    existing_watch = (
        run["status"] == "ambiguous_fail_closed"
        or any(
            cancel["status"] == "cancel_ambiguous" or cancel["error_code"] == _WATCH_CODE
            for cancel in store.list_cancellations(request.run_id)
        )
    )
    if request.scope == "between_step":
        # Once a run carries active-run WATCH, no later cancellation request —
        # even with a new cancel_id — may downgrade the run to clean cancelled.
        # Keep the fail-closed posture until an explicit future inspection gate.
        if existing_watch:
            status, ok, error_code, run_status = (
                "cancel_ambiguous", False, _WATCH_CODE, "ambiguous_fail_closed",
            )
        else:
            # Blocker (mid-step race): a between-step cancellation is only
            # deterministic when no step is actually in flight. If any resident step
            # for this run is still ``claimed_in_progress`` the cancellation races a
            # live step claim and cannot be attributed cleanly, so fail closed to the
            # active-run WATCH instead of recording a clean ``cancelled``.
            step_in_flight = any(
                step_state["status"] == STEP_CLAIMED for step_state in store.list_steps(request.run_id)
            )
            if step_in_flight:
                status, ok, error_code, run_status = (
                    "cancel_ambiguous", False, _WATCH_CODE, "ambiguous_fail_closed",
                )
            else:
                status, ok, error_code, run_status = "cancelled", True, None, "cancelled"
    else:
        # Same cross-cancel-id protection as the between_step branch: a prior
        # active-run WATCH must never be downgraded by a later request with a
        # different cancel_id, even one whose own interrupt outcome is confirmed.
        if existing_watch:
            status, ok, error_code, run_status = (
                "cancel_ambiguous", False, _WATCH_CODE, "ambiguous_fail_closed",
            )
        else:
            # Blocker 3: a confirmed active-run cancellation requires a matching
            # step_id resident in ``claimed_in_progress`` (an actual in-flight
            # step). Without it the interrupt outcome is unattributable, so fail
            # closed and preserve the WATCH rather than trusting a bare outcome.
            resident_step = (
                store.get_step(request.run_id, request.step_id)
                if request.step_id is not None
                else None
            )
            in_progress = resident_step is not None and resident_step["status"] == STEP_CLAIMED
            confirmed = (
                in_progress
                and interrupt_outcome is not None
                and getattr(interrupt_outcome, "interrupted", False) is True
                and getattr(interrupt_outcome, "cleanup_verified", False) is True
            )
            if confirmed:
                status, ok, error_code, run_status = "cancelled", True, None, "cancelled"
            else:
                status, ok, error_code, run_status = (
                    "cancel_ambiguous", False, _WATCH_CODE, "ambiguous_fail_closed",
                )

    cancel_state = build_cancel_state(
        ok=ok,
        status=status,
        cancel_id=request.cancel_id,
        run_id=request.run_id,
        step_id=request.step_id,
        scope=request.scope,
        transaction_ref=request.transaction_ref,
        operation_ref=request.operation_ref,
        idempotency_key=request.idempotency_key,
        reason_code=reason_code,
        error_code=error_code,
    )
    store.record_cancellation_and_update_run(
        cancel_id=request.cancel_id,
        cancel_state=cancel_state,
        run_id=request.run_id,
        run_state=_run_status_state(run, run_status),
    )
    return CancellationRecordResult(cancel_state)


def _derive_verdict(
    steps: tuple[dict[str, Any], ...],
    cancels: tuple[dict[str, Any], ...],
    *,
    expected_step_ids: frozenset[str],
) -> tuple[str, bool]:
    step_statuses = {s["status"] for s in steps}
    cancel_statuses = {c["status"] for c in cancels}
    watch = (
        "cancel_ambiguous" in cancel_statuses
        or STEP_WATCH in step_statuses
        or STEP_CANCEL_AMBIGUOUS in step_statuses
    )
    if watch:
        return "ambiguous_fail_closed", True
    if "cancelled" in cancel_statuses or STEP_CANCELLED in step_statuses:
        return "cancelled", False
    if STEP_FAILED_TERMINAL in step_statuses or STEP_FAILED_RETRYABLE in step_statuses:
        return "failed", False
    if STEP_GATE_BLOCKED in step_statuses:
        return "parked", False
    # Exact expected-step proof (anti-overclaim): terminal success requires that
    # the resident steps are *exactly* the validated spec's expected steps and
    # that every one is completed. A partial run (an expected step missing), an
    # extra/unknown resident step, or any non-completed resident step parks
    # instead of overclaiming terminal success.
    if (
        steps
        and {s["step_id"] for s in steps} == expected_step_ids
        and all(s["status"] == STEP_COMPLETED for s in steps)
    ):
        return "succeeded", False
    return "parked", False


def summarize_workflow_run(
    store: AiFlowRunStore,
    *,
    run_id: str,
    spec: WorkflowSpec,
    operator_gate: bool = False,
    terminal_gate_ref: str | None = None,
) -> WorkflowEvidence:
    """Return the deterministic sanitized terminal evidence packet for a run."""

    run = store.get_run(run_id)
    if run is None:
        raise AiFlowOrchestrationError("activity_not_found", "no workflow run for the given id")
    # Bind summary finalization to the validated spec before any terminal gate
    # or verdict. A divergent workflow id / approval ref / spec digest /
    # role-binding digest fails closed so the terminal verdict can only ever be
    # derived against the same expected-step proof the run was admitted under.
    if (
        run["workflow_id"] != spec.workflow_id
        or run["approval_ref"] != spec.approval_ref
        or run["workflow_spec_digest"] != workflow_spec_digest(spec)
        or run["role_binding_digest"] != role_binding_digest(spec)
    ):
        raise AiFlowOrchestrationError(
            "activity_spec_binding_mismatch", "summary spec does not bind the resident run"
        )
    terminal = check_gate(
        "terminal", operator_gate=operator_gate, gate_ref=terminal_gate_ref
    )
    store.record_gate(run_id=run_id, projection=gate_decision_projection(terminal))
    steps = store.list_steps(run_id)
    gates = store.list_gates(run_id)
    artifacts = store.list_artifacts(run_id)
    cancels = store.list_cancellations(run_id)
    fingerprints = store.step_fingerprints(run_id)

    expected_step_ids = frozenset(step.step_id for step in spec.steps)
    raw_verdict, watch = _derive_verdict(steps, cancels, expected_step_ids=expected_step_ids)
    verdict = raw_verdict if terminal.granted or raw_verdict == "ambiguous_fail_closed" else "parked"
    _update_run_status(store, run, verdict)

    ordered_steps = sorted(steps, key=lambda s: s["step_id"])
    state_transitions = [
        {
            "step_id": s["step_id"],
            "status": s["status"],
            "attempt_index": s["attempt_index"],
            "error_code": s["error_code"],
        }
        for s in ordered_steps
    ]
    role_binding_refs = sorted(
        ({"logical_role": s["logical_role"], "role_key": s["role_key"]} for s in ordered_steps),
        key=lambda item: item["logical_role"],
    )
    # de-duplicate role binding refs deterministically
    seen: set[tuple[str, str]] = set()
    unique_role_refs: list[dict[str, str]] = []
    for ref in role_binding_refs:
        key = (ref["logical_role"], ref["role_key"])
        if key not in seen:
            seen.add(key)
            unique_role_refs.append(ref)
    gate_decisions = [
        {
            "gate_type": g["gate_type"],
            "gate_ref": g["gate_ref"],
            "status": g["status"],
            "step_id": g["step_id"],
        }
        for g in sorted(gates, key=lambda g: (g["gate_type"], g["step_id"] or ""))
    ]
    artifact_refs = [
        {
            "artifact_id": a["artifact_id"],
            "content_digest": a["content_digest"],
            "artifact_kind": a["artifact_kind"],
            "byte_count": a["byte_count"],
            "producer_step_id": a["producer_step_id"],
        }
        for a in sorted(artifacts, key=lambda a: a["artifact_id"])
    ]
    error_codes = sorted(
        {code for code in (s["error_code"] for s in steps) if code}
        | {code for code in (c["error_code"] for c in cancels) if code}
    )

    return build_workflow_evidence(
        workflow_id=run["workflow_id"],
        workflow_spec_digest=run["workflow_spec_digest"],
        role_binding_digest=run["role_binding_digest"],
        state_transitions=state_transitions,
        step_fingerprints=fingerprints,
        role_binding_refs=unique_role_refs,
        gate_decisions=gate_decisions,
        artifact_refs=artifact_refs,
        error_codes=error_codes,
        active_run_cancellation_watch=watch,
        final_verdict=verdict,
    )
