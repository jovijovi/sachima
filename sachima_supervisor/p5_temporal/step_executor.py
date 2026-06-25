"""P5 Temporal ``StepExecutor`` bridge (FR1 / FR5, Gates A + E).

``P5TemporalStepExecutor`` implements the exact merged WP4 ``StepExecutor``
Protocol shape from ``sachima_supervisor.ai_flow_executor`` —

    execute(request, *, role_binding, resolved_inputs) -> StepExecutionOutcome

— in front of a real Temporal durable backend, **default-off** behind an enable
flag and an exact approval token. With the flag off or the token mismatched it
makes **zero** Temporal/control-surface calls and the caller stays on the
local/offline baseline (Gate A).

It is the only place WP4 ↔ sanitized ``contracts`` translation happens; the
workflow never imports WP4 internals. WP4 semantics are preserved: caller-owned
orchestration (no business verdict inferred from success), claim-check artifact
refs only, controlled-deterministic Slice 1 body (no real ``acpx``/agent), and
the WP3b active-run cancellation WATCH (``active_run_cancellation_watch ->
cancel_ambiguous``). It exposes the same control surface as the local oracle
``P5LocalOfflineRuntimeAdapter`` (``query`` / ``cancel`` / ``recover`` / ``close``
/ ``history_projection`` / ``serialized_history_bytes``) so the Temporal backend
is behaviorally substitutable (Gate E conformance).
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Mapping
from typing import Any

from ..ai_flow_executor import StepExecutionOutcome
from . import contracts as C

#: Exact PR B implementation approval token. Split across literals to mirror the
#: repo's token style; the boundary underscores are part of the token. It encodes
#: the in-force non-approvals so an accidental enable cannot widen scope.
P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN = (
    "approve_agent_run_supervisor_sachima_p5_temporal_pr_b_first_slice_runtime_implementation_"
    "hermetic_local_and_staging_namespace_ops_owned_worker_only_caller_supplied_temporal_client_"
    "behind_executor_protocol_seam_default_off_controlled_deterministic_step_body_"
    "no_production_cluster_no_production_traffic_no_p6_real_acpx_or_agent_execution_"
    "no_gateway_owned_lifecycle_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery"
)


def _run_blocking(coro: Any) -> Any:
    """Drive a coroutine to completion from a synchronous caller.

    No running loop (the WP4 orchestrator / unit context) → ``asyncio.run``.
    Inside a running loop → a dedicated worker thread with its own loop, so the
    sync WP4 ``execute`` contract holds without ever blocking a live loop.
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    box: dict[str, Any] = {}

    def _worker() -> None:
        try:
            box["result"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - control surface is no-throw
            box["exc"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()
    if "exc" in box:
        raise box["exc"]
    return box.get("result")


def _failure(code: str, *, ambiguous: bool = False, interrupted: bool = False) -> StepExecutionOutcome:
    return StepExecutionOutcome(
        ok=False,
        step_status=C.CANCEL_AMBIGUOUS if ambiguous else "failed_terminal",
        artifact_refs=(),
        error_code=code,
        retryable=False,
        interrupted=interrupted,
        cleanup_verified=False,
        ambiguous=ambiguous,
    )


def _require_ref(obj: Any, attr: str) -> str:
    """Extract required WP4 identity material as a safe history ref, or fail closed.

    ``None`` / a missing attribute / a non-``str`` value is rejected here, and empty /
    whitespace / the stringified-``None`` sentinel (``'none'`` / ``'None'``) is rejected
    by ``safe_ref`` *before* normalization. Missing or malformed identity material can
    therefore never be ``str(...)``-collapsed into a safe-looking workflow id and start
    Temporal work — the executor fails closed before any control-surface call.
    """

    value = getattr(obj, attr, None)
    if type(value) is not str:
        raise C.ContractError(C.INVALID_START_PAYLOAD)
    return C.safe_ref(value)


def _optional_ref(obj: Any, attr: str, *, default: str) -> str:
    """Optional WP4 ref (e.g. ``transaction_ref``).

    ``None`` / a missing attribute / empty / whitespace / the stringified-``None``
    sentinel falls back to the supplied (already-safe) default; a present value is
    normalized strictly so raw/malformed material still fails closed.
    """

    value = getattr(obj, attr, None)
    if value is None:
        return default
    if type(value) is not str:
        raise C.ContractError(C.INVALID_START_PAYLOAD)
    if value.strip() == "" or value.strip().lower() == "none":
        return default
    return C.safe_ref(value)


class P5TemporalStepExecutor:
    """Default-off WP4 ``StepExecutor`` over a Temporal control surface."""

    def __init__(
        self,
        *,
        control_surface: Any = None,
        enabled: bool = False,
        approval_token: str = "",
        runner: Any = None,
    ) -> None:
        self._control_surface = control_surface
        self.enabled = enabled
        self.approval_token = approval_token
        self._runner = runner or _run_blocking
        self._history: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # WP4 protocol — sync execute (caller-owned orchestration drives this)
    # ------------------------------------------------------------------ #
    def execute(
        self,
        request: Any,
        *,
        role_binding: Any,
        resolved_inputs: tuple[Mapping[str, Any], ...],
    ) -> StepExecutionOutcome:
        gate = self._admit()
        if gate is not None:
            return gate
        translated = self._translate_or_fail(request, role_binding, resolved_inputs)
        if isinstance(translated, StepExecutionOutcome):
            return translated
        return self._runner(self._astart_and_outcome(translated))

    async def aexecute(
        self,
        request: Any,
        *,
        role_binding: Any,
        resolved_inputs: tuple[Mapping[str, Any], ...],
    ) -> StepExecutionOutcome:
        gate = self._admit()
        if gate is not None:
            return gate
        translated = self._translate_or_fail(request, role_binding, resolved_inputs)
        if isinstance(translated, StepExecutionOutcome):
            return translated
        return await self._astart_and_outcome(translated)

    # ------------------------------------------------------------------ #
    # Admission (Gate A) — zero Temporal call when default-off / mismatched
    # ------------------------------------------------------------------ #
    def _admission_code(self) -> str | None:
        """Gate A decision shared by **every** control-surface entry point.

        Returns the stable rejection code when the runtime is default-off, the
        approval token is missing/mismatched, or no control surface is wired —
        else ``None``. It is pure: it makes **zero** Temporal/control-surface
        calls, so ``execute`` / ``aexecute`` *and* ``query`` / ``recover`` /
        ``cancel`` / ``close`` can all consult it before touching the backend.
        Absent the enable flag or the exact token, zero Temporal calls are made
        on any path.
        """

        if self.enabled is not True:
            return C.RUNTIME_DISABLED
        if self.approval_token != P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN:
            return C.RUNTIME_APPROVAL_MISMATCH
        if self._control_surface is None:
            return C.RUNTIME_PRECONDITION_UNMET
        return None

    def _admit(self) -> StepExecutionOutcome | None:
        code = self._admission_code()
        if code is None:
            return None
        self._record("execute_rejected", error_code=code)
        return _failure(code)

    # ------------------------------------------------------------------ #
    # WP4 -> sanitized contracts translation (only place this happens)
    # ------------------------------------------------------------------ #
    def _translate_or_fail(
        self, request: Any, role_binding: Any, resolved_inputs: tuple[Mapping[str, Any], ...]
    ) -> C.StartRequest | StepExecutionOutcome:
        try:
            return self._translate(request, role_binding, resolved_inputs)
        except C.ContractError as exc:
            code = exc.code if exc.code in C.STABLE_CODES else C.INVALID_START_PAYLOAD
            self._record("execute_rejected", error_code=code)
            return _failure(code)

    def _translate(
        self, request: Any, role_binding: Any, resolved_inputs: tuple[Mapping[str, Any], ...]
    ) -> C.StartRequest:
        # Required identity material is extracted strictly: None / missing attr /
        # non-str / empty / the stringified-None sentinel fails closed *before* any
        # control-surface call (never str(...)-collapsed into a safe-looking id).
        run_ref = _require_ref(request, "run_id")
        step_ref = _require_ref(request, "step_id")
        # transaction_ref is optional and falls back to the run ref; a present value
        # is normalized strictly so raw/malformed material still fails closed.
        workflow_ref = _optional_ref(request, "transaction_ref", default=run_ref)
        role_key = _require_ref(role_binding, "role_key")
        idem = _require_ref(request, "idempotency_key")
        attempt = getattr(request, "attempt_index", 1)
        if not isinstance(resolved_inputs, (list, tuple)):
            raise C.ContractError(C.INVALID_START_PAYLOAD)
        # Fail closed on any raw/private/secret material in the resolved inputs —
        # only claim-check refs + digests may cross into Temporal history.
        for item in resolved_inputs:
            if C.scan_projection_for_leak(item) is not None:
                raise C.ContractError(C.RUNTIME_UNSAFE_MATERIAL)
        claim_refs = tuple(C.artifact_ref_to_claim_check(item) for item in resolved_inputs)
        return C.build_start_request(
            run_ref=run_ref,
            workflow_ref=workflow_ref,
            step_ref=step_ref,
            attempt_index=attempt,
            role_keys=(role_key,),
            input_claim_refs=claim_refs,
            idempotency_material=idem,
        )

    async def _astart_and_outcome(self, start_request: C.StartRequest) -> StepExecutionOutcome:
        workflow_id = C.deterministic_workflow_id(start_request)
        result = await self._control_surface.start(start_request, workflow_id=workflow_id)
        return self._outcome_from_start_result(start_request, result)

    def _outcome_from_start_result(
        self, start_request: C.StartRequest, result: Mapping[str, Any]
    ) -> StepExecutionOutcome:
        if not isinstance(result, Mapping) or result.get("ok") is not True:
            code = (result.get("error_code") if isinstance(result, Mapping) else None) or C.RUNTIME_ERROR
            if code not in C.STABLE_CODES:
                code = C.RUNTIME_ERROR
            self._record(
                "execute_rejected",
                run_ref=start_request.run_ref,
                step_ref=start_request.step_ref,
                error_code=code,
            )
            return _failure(code)
        snapshot = result.get("snapshot") or {}
        artifact_refs = tuple(
            {key: ref[key] for key in C.ALLOWED_ARTIFACT_REF_KEYS}
            for ref in snapshot.get("artifact_refs", ())
            if isinstance(ref, Mapping) and set(ref) == set(C.ALLOWED_ARTIFACT_REF_KEYS)
        )
        evidence_ref, evidence_digest = C.deterministic_evidence(start_request)
        self._record(
            "execute_completed", run_ref=start_request.run_ref, step_ref=start_request.step_ref
        )
        # Caller-owned orchestration: success carries NO business verdict.
        return StepExecutionOutcome(
            ok=True,
            step_status="completed",
            artifact_refs=artifact_refs,
            evidence_ref=evidence_ref,
            evidence_digest=evidence_digest,
        )

    # ------------------------------------------------------------------ #
    # Oracle-conformant control surface (Gate E)
    # ------------------------------------------------------------------ #
    def query(self, *, run_id: str, step_id: str) -> dict[str, Any]:
        return self._runner(self.aquery(run_id=run_id, step_id=step_id))

    async def aquery(self, *, run_id: str, step_id: str) -> dict[str, Any]:
        # Gate A: default-off / mismatched / unwired makes zero Temporal calls.
        code = self._admission_code()
        if code is not None:
            return self._rejected_snapshot(run_id, step_id, code, event="query_rejected")
        run_ref, step_ref, workflow_id = self._refs(run_id, step_id)
        result = await self._control_surface.query(workflow_id=workflow_id)
        return self._normalize_snapshot(run_ref, step_ref, result)

    def recover(self, *, run_id: str, step_id: str) -> dict[str, Any]:
        return self._runner(self.arecover(run_id=run_id, step_id=step_id))

    async def arecover(self, *, run_id: str, step_id: str) -> dict[str, Any]:
        # Gate A: default-off / mismatched / unwired makes zero Temporal calls.
        code = self._admission_code()
        if code is not None:
            return self._rejected_snapshot(run_id, step_id, code, event="recover_rejected")
        # Reattach by workflow id; never auto-relaunch uncertain work.
        run_ref, step_ref, workflow_id = self._refs(run_id, step_id)
        result = await self._control_surface.recover(workflow_id=workflow_id)
        return self._normalize_snapshot(run_ref, step_ref, result, recovered=True)

    def cancel(
        self,
        *,
        run_id: str,
        step_id: str,
        scope: str,
        idempotency_key: str,
        interrupt_outcome: StepExecutionOutcome | None = None,
    ) -> StepExecutionOutcome:
        return self._runner(
            self.acancel(
                run_id=run_id,
                step_id=step_id,
                scope=scope,
                idempotency_key=idempotency_key,
                interrupt_outcome=interrupt_outcome,
            )
        )

    async def acancel(
        self,
        *,
        run_id: str,
        step_id: str,
        scope: str,
        idempotency_key: str,
        interrupt_outcome: StepExecutionOutcome | None = None,
    ) -> StepExecutionOutcome:
        # Gate A: default-off / mismatched / unwired makes zero Temporal calls.
        code = self._admission_code()
        if code is not None:
            self._record(
                "cancel_rejected",
                run_ref=self._best_effort_ref(run_id),
                step_ref=self._best_effort_ref(step_id),
                error_code=code,
            )
            return _failure(code)
        run_ref, step_ref, workflow_id = self._refs(run_id, step_id)
        if scope != "active_run":
            self._record("cancel_rejected", run_ref=run_ref, step_ref=step_ref, error_code=C.RUNTIME_CANCEL_SCOPE_UNSUPPORTED)
            return _failure(C.RUNTIME_CANCEL_SCOPE_UNSUPPORTED)
        # Admission guarantees a wired control surface here.
        update = C.build_update_payload(event_key=C.safe_ref(str(idempotency_key)), event_type="request_cancel", ref=None)
        # Cooperative cancellation request; no-throw.
        await self._control_surface.cancel(workflow_id=workflow_id, update=update)
        confirmed = (
            interrupt_outcome is not None
            and getattr(interrupt_outcome, "interrupted", False) is True
            and getattr(interrupt_outcome, "cleanup_verified", False) is True
        )
        if confirmed:
            self._record("cancel_confirmed", run_ref=run_ref, step_ref=step_ref)
            return StepExecutionOutcome(
                ok=True,
                step_status="cancelled",
                artifact_refs=(),
                interrupted=True,
                cleanup_verified=True,
            )
        # WP3b WATCH: never report a clean cancellation we cannot prove.
        self._record("cancel_watch", run_ref=run_ref, step_ref=step_ref, error_code=C.ACTIVE_RUN_CANCELLATION_WATCH)
        return _failure(C.ACTIVE_RUN_CANCELLATION_WATCH, ambiguous=True)

    def close(self) -> dict[str, Any]:
        return self._runner(self.aclose())

    async def aclose(self) -> dict[str, Any]:
        # Gate A: default-off / mismatched / unwired makes zero Temporal calls.
        code = self._admission_code()
        if code is not None:
            self._record("close_rejected", error_code=code)
            return {
                "type": C.SNAPSHOT_TYPE,
                "state": "store_invalid",
                "snapshot_version": len(self._history),
                "error_code": code,
            }
        await self._control_surface.close()
        self._record("closed")
        return {"type": C.SNAPSHOT_TYPE, "state": "closed", "snapshot_version": len(self._history)}

    # ------------------------------------------------------------------ #
    # Sanitized local history projection (SCAN 1 + conformance)
    # ------------------------------------------------------------------ #
    def history_projection(self) -> dict[str, Any]:
        with self._lock:
            return {
                "type": C.HISTORY_TYPE,
                "snapshot_version": len(self._history),
                "events": [dict(event) for event in self._history],
            }

    def serialized_history_bytes(self) -> bytes:
        return C.canonical_json_bytes(self.history_projection())

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _refs(self, run_id: str, step_id: str) -> tuple[str, str, str]:
        run_ref = C.safe_ref(str(run_id))
        step_ref = C.safe_ref(str(step_id))
        return run_ref, step_ref, C.workflow_id_from_refs(run_ref, step_ref)

    def _best_effort_ref(self, value: Any) -> str:
        """Sanitize a ref for an admission-rejected marker; never raises.

        On the Gate A rejection path no Temporal call is made, so an unsafe
        run/step ref must not leak nor raise — it collapses to a constant safe id.
        """

        try:
            return C.safe_ref(str(value))
        except C.ContractError:
            return "ref_rejected"

    def _rejected_snapshot(self, run_id: str, step_id: str, code: str, *, event: str) -> dict[str, Any]:
        """Record + return a sanitized store-invalid snapshot for a Gate A
        rejection, without ever touching the control surface."""

        run_ref = self._best_effort_ref(run_id)
        step_ref = self._best_effort_ref(step_id)
        self._record(event, run_ref=run_ref, step_ref=step_ref, error_code=code)
        return self._snapshot_marker(run_ref, step_ref, "store_invalid", code)

    def _snapshot_marker(self, run_ref: str, step_ref: str, state: str, error_code: str | None) -> dict[str, Any]:
        return {
            "type": C.SNAPSHOT_TYPE,
            "run_ref": run_ref,
            "step_ref": step_ref,
            "state": state,
            "snapshot_version": len(self._history),
            "artifact_refs": [],
            "error_code": error_code,
        }

    def _normalize_snapshot(
        self, run_ref: str, step_ref: str, result: Mapping[str, Any], *, recovered: bool = False
    ) -> dict[str, Any]:
        if not isinstance(result, Mapping) or result.get("ok") is not True:
            code = (result.get("error_code") if isinstance(result, Mapping) else None) or C.RUNTIME_NOT_FOUND
            if code not in C.STABLE_CODES:
                code = C.RUNTIME_ERROR
            state = "not_found" if code == C.RUNTIME_NOT_FOUND else "store_invalid"
            return self._snapshot_marker(run_ref, step_ref, state, code)
        snapshot = result.get("snapshot") or {}
        artifact_refs = [
            {key: ref[key] for key in C.ALLOWED_ARTIFACT_REF_KEYS}
            for ref in snapshot.get("artifact_refs", ())
            if isinstance(ref, Mapping) and set(ref) == set(C.ALLOWED_ARTIFACT_REF_KEYS)
        ]
        marker = {
            "type": C.SNAPSHOT_TYPE,
            "run_ref": run_ref,
            "step_ref": step_ref,
            "state": snapshot.get("state", "running"),
            "snapshot_version": snapshot.get("snapshot_version", len(self._history)),
            "artifact_refs": artifact_refs,
            "error_code": snapshot.get("error_code"),
        }
        if recovered:
            marker["recovery_marker"] = "reattached_by_workflow_id"
        return marker

    def _record(
        self,
        event: str,
        *,
        run_ref: str | None = None,
        step_ref: str | None = None,
        error_code: str | None = None,
    ) -> None:
        with self._lock:
            projection = {
                "event": C.safe_ref(event),
                "sequence": len(self._history) + 1,
                "run_ref": run_ref,
                "step_ref": step_ref,
                "error_code": error_code,
            }
            if C.scan_projection_for_leak(projection) is not None:
                projection = {
                    "event": "history_projection_rejected",
                    "sequence": len(self._history) + 1,
                    "run_ref": None,
                    "step_ref": None,
                    "error_code": C.RUNTIME_UNSAFE_MATERIAL,
                }
            self._history.append(projection)


__all__ = [
    "P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN",
    "P5TemporalStepExecutor",
]
