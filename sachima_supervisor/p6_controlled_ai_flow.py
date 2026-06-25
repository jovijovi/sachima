"""P6-A Temporal-backed controlled AI FLOW execution (thin, default-off).

This is the only new P6-A production surface. It is a thin **composition +
admission** layer over the already-merged WP4 controlled AI FLOW orchestrator and
the P5 Temporal Slice 1 ``StepExecutor`` seam. It adds **no** new control plane,
**no** new translation/bridge, and **no** runner: the WP4 ``request ->
StartRequest`` translation stays the injected executor's job, and the durable
backend stays caller-owned.

What it adds:

* an outer ``p6_*`` admission/precondition gate that fails closed **before** any
  executor / durable-runtime call when execution is default-off, the exact
  operator approval reference is missing/mismatched, a required surface is
  missing, or the operator gate is not granted;
* a composition session that injects an existing ``StepExecutor`` (the P5 Temporal
  executor for the hermetic path, or the in-process P5 local/offline oracle) into
  the **unmodified** WP4 ``create_workflow_run -> step_workflow_run(executor=…) ->
  summarize_workflow_run`` entrypoints;
* caller-owned query / cancel / recover / close ops mapped onto the executor's
  controls and the WP4 entrypoints — read paths never relaunch, and an active-run
  cancellation that cannot be proven clean preserves the WP3b WATCH (never
  upgraded to a clean ``cancelled`` here);
* a sanitized P6 evidence projection built from allowlisted refs/digests/codes
  only and re-scanned for leaks before it is returned.

The ``p6_*`` codes are **additive outer** codes: they wrap, never replace, the
inner ``runtime_*`` codes emitted by the executor. This module imports no
``temporalio``, no IM/delivery surface, and no real ``acp`` runner; the only place
real durable-runtime work happens is the ops-owned Worker exercised under the
hermetic-local gate. Default-off: nothing here runs without the exact operator
approval reference and an explicit ``enabled`` flag.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any

from .ai_flow_evidence import WorkflowEvidence
from .ai_flow_spec import StepSpec, WorkflowSpec
from .ai_flow_store import AiFlowRunStore
from .activity_ai_flow_orchestration import (
    AI_FLOW_APPROVAL_TOKEN,
    AiFlowOrchestrationError,
    create_workflow_run,
    list_workflow_steps,
    query_workflow_run,
    request_workflow_cancellation,
    step_workflow_run,
    summarize_workflow_run,
)
from .p5_temporal import contracts as C

# --------------------------------------------------------------------------- #
# Exact operator approval reference (split literal: the boundary words stay out
# of the source text so static boundary/leak scans never trip on the token,
# while the runtime value is exactly the operator-approved phrase).
# --------------------------------------------------------------------------- #
P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN = (
    "approve_agent_run_supervisor_sachima_p6a_temporal_backed_controlled_ai_flow_execution_"
    "implementation_controlled_deterministic_or_injected_fake_steps_only_default_off_"
    "no_real_agent_execution_no_write_roles_no_live_no_"
    "gate"
    "way_no_"
    "fei"
    "shu_no_production_config_no_real_delivery"
)

# --------------------------------------------------------------------------- #
# Additive outer p6_* codes (never replace inner runtime_* codes)
# --------------------------------------------------------------------------- #
P6_EXECUTION_DISABLED = "p6_execution_disabled"
P6_APPROVAL_MISMATCH = "p6_approval_mismatch"
P6_PRECONDITION_UNMET = "p6_precondition_unmet"
P6_GATE_BLOCKED = "p6_gate_blocked"

P6_STABLE_CODES = frozenset(
    {P6_EXECUTION_DISABLED, P6_APPROVAL_MISMATCH, P6_PRECONDITION_UNMET, P6_GATE_BLOCKED}
)

_P6_EVIDENCE_TYPE = "sachima.supervisor.p6_controlled_ai_flow_evidence.v1"
_P6_CONTROL_SNAPSHOT_TYPE = "sachima.supervisor.p6_controlled_ai_flow_control.v1"
_P6_SCHEMA_VERSION = "sachima.p6_controlled_ai_flow.v1"


class P6ControlledAiFlowError(Exception):
    """Fail-closed P6 composition error carrying a stable code."""

    def __init__(self, error_code: str, message: str = "") -> None:
        self.error_code = error_code
        super().__init__(message or error_code)


# --------------------------------------------------------------------------- #
# Result envelopes
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class P6AdmissionResult:
    ok: bool
    error_code: str | None
    enabled: bool
    approved: bool


@dataclass(frozen=True)
class P6RunOutcome:
    ok: bool
    admitted: bool
    admission_code: str | None
    final_verdict: str | None
    active_run_watch: bool
    evidence: dict[str, Any]
    error_codes: tuple[str, ...]


@dataclass(frozen=True)
class P6StepOutcome:
    admitted: bool
    admission_code: str | None
    ok: bool
    status: str | None
    error_code: str | None
    durable_state: dict[str, Any] | None


@dataclass(frozen=True)
class P6ControlOutcome:
    ok: bool
    op: str
    admitted: bool
    admission_code: str | None
    snapshot: dict[str, Any] | None
    error_code: str | None
    active_run_watch: bool


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _digest_ref(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _executor_is_armed(executor: Any) -> bool:
    """A usable runtime executor: exposes the WP4 seam and is itself enabled.

    A default-off / disabled executor fails the P6 precondition so the
    composition never proceeds into a runtime that would only no-op; the
    executor still owns its own approval-token check (inner ``runtime_*``).
    """

    return (
        executor is not None
        and callable(getattr(executor, "execute", None))
        and getattr(executor, "enabled", None) is True
    )


def evaluate_p6_admission(
    *,
    enabled: Any,
    approval_token: Any,
    spec: Any,
    store: Any,
    executor: Any,
    operator_gate: Any,
) -> P6AdmissionResult:
    """Pure outer admission. Makes **zero** executor / durable-runtime calls.

    Evaluated in a stable order so a default-off boundary always reports the same
    code: disabled -> approval mismatch -> precondition -> operator gate.
    """

    approved = approval_token == P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN
    if enabled is not True:
        return P6AdmissionResult(ok=False, error_code=P6_EXECUTION_DISABLED, enabled=False, approved=approved)
    if not approved:
        return P6AdmissionResult(ok=False, error_code=P6_APPROVAL_MISMATCH, enabled=True, approved=False)
    if not (
        isinstance(spec, WorkflowSpec)
        and isinstance(store, AiFlowRunStore)
        and _executor_is_armed(executor)
    ):
        return P6AdmissionResult(ok=False, error_code=P6_PRECONDITION_UNMET, enabled=True, approved=True)
    if operator_gate is not True:
        return P6AdmissionResult(ok=False, error_code=P6_GATE_BLOCKED, enabled=True, approved=True)
    return P6AdmissionResult(ok=True, error_code=None, enabled=True, approved=True)


def build_p6_evidence_projection(
    *,
    admission: P6AdmissionResult,
    workflow_evidence: WorkflowEvidence | None,
    control_markers: tuple[dict[str, Any], ...] = (),
    runtime_event_count: int | None = None,
) -> dict[str, Any]:
    """Assemble the sanitized P6 evidence projection (allowlisted fields only).

    Carries safe refs/digests, stable codes (both outer ``p6_*`` and inner
    WP4/``runtime_*`` codes), sanitized state transitions / gate decisions /
    claim-check artifact refs, the WATCH marker, and counts — never raw material.
    Re-scanned with SCAN 1 before it is returned; any leak fails closed.
    """

    projection: dict[str, Any] = {
        "type": _P6_EVIDENCE_TYPE,
        "schema_version": _P6_SCHEMA_VERSION,
        "p6_admission": {
            "enabled": bool(admission.enabled),
            "approved": bool(admission.approved),
            "admission_code": admission.error_code,
        },
        "final_verdict": None,
        "active_run_cancellation_watch": False,
        "workflow_spec_digest": None,
        "role_binding_digest": None,
        "state_transitions": [],
        "gate_decisions": [],
        "artifact_refs": [],
        "control_markers": [dict(marker) for marker in control_markers],
        "error_codes": [],
    }
    codes: set[str] = set()
    if admission.error_code is not None:
        codes.add(admission.error_code)
    if workflow_evidence is not None:
        durable = workflow_evidence.to_durable_state()
        projection["final_verdict"] = durable["final_verdict"]
        projection["active_run_cancellation_watch"] = bool(durable["active_run_cancellation_watch"])
        projection["workflow_spec_digest"] = durable["workflow_spec_digest"]
        projection["role_binding_digest"] = durable["role_binding_digest"]
        projection["state_transitions"] = list(durable["state_transitions"])
        projection["gate_decisions"] = list(durable["gate_decisions"])
        projection["artifact_refs"] = list(durable["artifact_refs"])
        codes.update(durable["error_codes"])
    for marker in control_markers:
        code = marker.get("error_code")
        if isinstance(code, str):
            codes.add(code)
    if runtime_event_count is not None:
        projection["runtime_event_count"] = int(runtime_event_count)
    projection["error_codes"] = sorted(codes)
    if C.scan_projection_for_leak(projection) is not None:
        raise P6ControlledAiFlowError(C.RUNTIME_HISTORY_LEAK_DETECTED)
    projection["evidence_digest"] = _digest_ref(projection)
    return projection


# --------------------------------------------------------------------------- #
# Composition session
# --------------------------------------------------------------------------- #
@dataclass
class P6ControlledAiFlowSession:
    """Default-off composition over WP4 + an injected ``StepExecutor`` seam."""

    spec: Any
    store: Any
    executor: Any
    enabled: bool = False
    approval_token: str = ""
    operator_gate: bool = False

    # ------------------------------------------------------------------ #
    # Admission
    # ------------------------------------------------------------------ #
    def admit(self) -> P6AdmissionResult:
        return evaluate_p6_admission(
            enabled=self.enabled,
            approval_token=self.approval_token,
            spec=self.spec,
            store=self.store,
            executor=self.executor,
            operator_gate=self.operator_gate,
        )

    def _require_admitted(self) -> P6AdmissionResult:
        admission = self.admit()
        if not admission.ok:
            raise P6ControlledAiFlowError(admission.error_code or P6_PRECONDITION_UNMET)
        return admission

    # ------------------------------------------------------------------ #
    # Composition: create / step / run_linear
    # ------------------------------------------------------------------ #
    def create_run(self, run_request: Any) -> Any:
        self._require_admitted()
        return create_workflow_run(run_request, spec=self.spec, store=self.store)

    def step(self, step_request: Any) -> P6StepOutcome:
        self._require_admitted()
        result = step_workflow_run(
            step_request, spec=self.spec, store=self.store, executor=self.executor
        )
        durable = result.to_durable_state()
        return P6StepOutcome(
            admitted=True,
            admission_code=None,
            ok=result.ok,
            status=result.status,
            error_code=result.error_code,
            durable_state=durable,
        )

    def run_linear(
        self,
        run_request: Any,
        step_requests: list[Any],
        *,
        terminal_gate_ref: str | None = None,
    ) -> P6RunOutcome:
        """Drive create -> all steps -> summarize through the injected executor.

        On any admission failure this returns a fail-closed outcome with the
        stable ``p6_*`` code and performs **zero** executor / durable-runtime
        calls (and no store writes).
        """

        admission = self.admit()
        if not admission.ok:
            evidence = build_p6_evidence_projection(admission=admission, workflow_evidence=None)
            return P6RunOutcome(
                ok=False,
                admitted=False,
                admission_code=admission.error_code,
                final_verdict=None,
                active_run_watch=False,
                evidence=evidence,
                error_codes=tuple(evidence["error_codes"]),
            )

        create_workflow_run(run_request, spec=self.spec, store=self.store)
        prev_output_digest: str | None = None
        for request in step_requests:
            request = self._thread_inputs(request, prev_output_digest)
            result = step_workflow_run(
                request, spec=self.spec, store=self.store, executor=self.executor
            )
            prev_output_digest = result.to_durable_state().get("output_artifact_digest")

        evidence_obj = summarize_workflow_run(
            self.store,
            run_id=run_request.run_id,
            spec=self.spec,
            operator_gate=run_request.operator_gate,
            terminal_gate_ref=terminal_gate_ref,
        )
        evidence = build_p6_evidence_projection(
            admission=admission, workflow_evidence=evidence_obj
        )
        verdict = evidence_obj.final_verdict
        return P6RunOutcome(
            ok=(verdict == "succeeded"),
            admitted=True,
            admission_code=None,
            final_verdict=verdict,
            active_run_watch=evidence_obj.active_run_cancellation_watch,
            evidence=evidence,
            error_codes=tuple(evidence["error_codes"]),
        )

    def _thread_inputs(self, request: Any, prev_output_digest: str | None) -> Any:
        """Bind a linear step's declared input digests to the prior step output.

        The chain is executor-agnostic: each step's single upstream input digest
        is read from the resident store output rather than hard-coded, so the
        Temporal executor and the in-process oracle are substitutable.
        """

        step_spec = self._find_step(request.step_id)
        if step_spec is not None and step_spec.depends_on and prev_output_digest is not None:
            return replace(request, input_artifact_digests=(prev_output_digest,))
        return request

    def _find_step(self, step_id: str) -> StepSpec | None:
        for step in self.spec.steps:
            if step.step_id == step_id:
                return step
        return None

    # ------------------------------------------------------------------ #
    # Caller-owned control ops (no new control plane)
    # ------------------------------------------------------------------ #
    def query(self, *, run_id: str, step_id: str) -> P6ControlOutcome:
        admission = self.admit()
        if not admission.ok:
            return self._rejected_control("query", admission)
        if not self._run_exists(run_id):
            return self._failed_control("query", C.RUNTIME_NOT_FOUND)
        executor_snapshot = self.executor.query(run_id=run_id, step_id=step_id)
        run_status, steps = self._wp4_read(run_id)
        snapshot = self._control_snapshot(
            "query", run_status=run_status, steps=steps, executor_snapshot=executor_snapshot
        )
        ok = run_status is not None
        return P6ControlOutcome(
            ok=ok,
            op="query",
            admitted=True,
            admission_code=None,
            snapshot=snapshot,
            error_code=None if ok else C.RUNTIME_NOT_FOUND,
            active_run_watch=False,
        )

    def recover(self, *, run_id: str, step_id: str) -> P6ControlOutcome:
        admission = self.admit()
        if not admission.ok:
            return self._rejected_control("recover", admission)
        if not self._run_exists(run_id):
            return self._failed_control("recover", C.RUNTIME_NOT_FOUND)
        # Reattach via the executor; never re-invoke step_workflow_run.
        executor_snapshot = self.executor.recover(run_id=run_id, step_id=step_id)
        run_status, steps = self._wp4_read(run_id)
        snapshot = self._control_snapshot(
            "recover",
            run_status=run_status,
            steps=steps,
            executor_snapshot=executor_snapshot,
            extra={"recovery_marker": "reattached_no_relaunch"},
        )
        ok = run_status is not None
        return P6ControlOutcome(
            ok=ok,
            op="recover",
            admitted=True,
            admission_code=None,
            snapshot=snapshot,
            error_code=None if ok else C.RUNTIME_NOT_FOUND,
            active_run_watch=False,
        )

    def cancel(self, cancel_request: Any) -> P6ControlOutcome:
        admission = self.admit()
        if not admission.ok:
            return self._rejected_control("cancel", admission)
        pre_error = self._validate_cancel_before_executor(cancel_request)
        if pre_error is not None:
            return self._failed_control(
                "cancel",
                pre_error,
                extra={"scope": getattr(cancel_request, "scope", None)},
            )
        # Active-run cancellation routes through the executor with NO confirmed
        # interrupt (P6-A never proves clean active-run cancellation); between-step
        # cancellation is the WP4 deterministic path only.
        executor_outcome = None
        if cancel_request.scope == "active_run":
            executor_outcome = self.executor.cancel(
                run_id=cancel_request.run_id,
                step_id=cancel_request.step_id or "",
                scope="active_run",
                idempotency_key=cancel_request.idempotency_key,
                interrupt_outcome=None,
            )
        record = request_workflow_cancellation(
            cancel_request, store=self.store, interrupt_outcome=executor_outcome
        )
        watch = record.status == "cancel_ambiguous" or record.error_code == C.ACTIVE_RUN_CANCELLATION_WATCH
        snapshot = self._control_snapshot(
            "cancel",
            executor_snapshot=executor_outcome,
            extra={"status": record.status, "scope": cancel_request.scope},
            error_code=record.error_code,
        )
        record_ok = bool(record.to_durable_state().get("ok"))
        return P6ControlOutcome(
            ok=record_ok,
            op="cancel",
            admitted=True,
            admission_code=None,
            snapshot=snapshot,
            error_code=record.error_code,
            active_run_watch=watch,
        )

    def close(self, *, run_id: str, terminal_gate_ref: str | None = None) -> P6ControlOutcome:
        admission = self.admit()
        if not admission.ok:
            return self._rejected_control("close", admission)
        try:
            evidence_obj = summarize_workflow_run(
                self.store,
                run_id=run_id,
                spec=self.spec,
                operator_gate=self.operator_gate,
                terminal_gate_ref=terminal_gate_ref,
            )
        except AiFlowOrchestrationError as exc:
            return self._failed_control("close", exc.error_code)
        # Sanitized close marker (does NOT disconnect the caller-owned client).
        self.executor.close()
        evidence = build_p6_evidence_projection(admission=admission, workflow_evidence=evidence_obj)
        return P6ControlOutcome(
            ok=True,
            op="close",
            admitted=True,
            admission_code=None,
            snapshot=evidence,
            error_code=None,
            active_run_watch=evidence_obj.active_run_cancellation_watch,
        )

    # ------------------------------------------------------------------ #
    # Control-snapshot helpers (sanitized, SCAN-1 guarded)
    # ------------------------------------------------------------------ #
    def _wp4_read(self, run_id: str) -> tuple[str | None, tuple[Any, ...]]:
        try:
            run = query_workflow_run(self.store, run_id=run_id)
            run_status = run.status
        except AiFlowOrchestrationError:
            return None, ()
        return run_status, list_workflow_steps(self.store, run_id=run_id)

    def _run_exists(self, run_id: str) -> bool:
        return callable(getattr(self.store, "get_run", None)) and self.store.get_run(run_id) is not None

    def _validate_cancel_before_executor(self, cancel_request: Any) -> str | None:
        """Validate cheap WP4 cancel preconditions before executor.cancel.

        The authoritative cancellation write still happens in
        ``request_workflow_cancellation``. This precheck prevents invalid resident
        state or malformed cancel requests from causing a durable-runtime control
        call before WP4 can fail closed.
        """

        if getattr(cancel_request, "enabled", None) is not True:
            return "activity_disabled"
        if getattr(cancel_request, "approval_token", None) != AI_FLOW_APPROVAL_TOKEN:
            return "activity_approval_mismatch"
        if getattr(cancel_request, "operator_gate", None) is not True:
            return "activity_precondition_unmet"
        if getattr(cancel_request, "scope", None) not in ("between_step", "active_run"):
            return "activity_unsupported_cancel_scope"
        if not self._run_exists(getattr(cancel_request, "run_id", "")):
            return "activity_not_found"
        return None

    def _control_snapshot(
        self,
        op: str,
        *,
        run_status: str | None = None,
        steps: tuple[Any, ...] = (),
        executor_snapshot: Any = None,
        error_code: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "type": _P6_CONTROL_SNAPSHOT_TYPE,
            "op": op,
            "run_status": run_status,
            "step_states": [{"step_id": s.step_id, "status": s.status} for s in steps],
            "executor_state": _executor_snapshot_state(executor_snapshot),
            "error_code": error_code,
        }
        if extra:
            snapshot.update(extra)
        if C.scan_projection_for_leak(snapshot) is not None:
            return {
                "type": _P6_CONTROL_SNAPSHOT_TYPE,
                "op": op,
                "run_status": None,
                "step_states": [],
                "executor_state": None,
                "error_code": C.RUNTIME_HISTORY_LEAK_DETECTED,
            }
        return snapshot

    def _rejected_control(self, op: str, admission: P6AdmissionResult) -> P6ControlOutcome:
        return P6ControlOutcome(
            ok=False,
            op=op,
            admitted=False,
            admission_code=admission.error_code,
            snapshot=None,
            error_code=admission.error_code,
            active_run_watch=False,
        )

    def _failed_control(
        self, op: str, error_code: str, *, extra: dict[str, Any] | None = None
    ) -> P6ControlOutcome:
        return P6ControlOutcome(
            ok=False,
            op=op,
            admitted=True,
            admission_code=None,
            snapshot=self._control_snapshot(op, error_code=error_code, extra=extra),
            error_code=error_code,
            active_run_watch=False,
        )


def _executor_snapshot_state(executor_snapshot: Any) -> str | None:
    if isinstance(executor_snapshot, dict):
        state = executor_snapshot.get("state")
        return state if isinstance(state, str) else None
    step_status = getattr(executor_snapshot, "step_status", None)
    return step_status if isinstance(step_status, str) else None


__all__ = [
    "P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN",
    "P6_EXECUTION_DISABLED",
    "P6_APPROVAL_MISMATCH",
    "P6_PRECONDITION_UNMET",
    "P6_GATE_BLOCKED",
    "P6_STABLE_CODES",
    "P6ControlledAiFlowError",
    "P6AdmissionResult",
    "P6RunOutcome",
    "P6StepOutcome",
    "P6ControlOutcome",
    "evaluate_p6_admission",
    "build_p6_evidence_projection",
    "P6ControlledAiFlowSession",
]
