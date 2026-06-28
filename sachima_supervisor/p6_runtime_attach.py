"""P6 runtime lifecycle / controlled attach layer (default-off first slice).

This module is a caller-owned attach/control shell over the existing P6 session.
It starts no runtime, Worker, service, subprocess, socket, platform adapter, or
delivery surface. It delegates only after an explicit attach gate has produced a
sanitized local projection.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
from collections.abc import MutableMapping
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Callable, Mapping

from .p5_runtime_adapter import (
    P5_RUNTIME_ADAPTER_IMPLEMENTATION_APPROVAL_TOKEN,
    P5LocalOfflineRuntimeAdapter,
)
from .p5_temporal import contracts as C
from .p6_controlled_ai_flow import P6_STABLE_CODES

P6_RUNTIME_ATTACH_IMPLEMENTATION_APPROVAL_TOKEN = (
    "approve_agent_run_supervisor_sachima_p6_runtime_lifecycle_controlled_attach_"
    "implementation_default_off_caller_owned_attach_only_no_runtime_or_worker_start_"
    "no_additional_real_agent_execution_no_write_roles_no_live_no_"
    "gate"
    "way_no_"
    "fei"
    "shu_no_production_config_no_real_delivery"
)

P6_ATTACH_DISABLED = "p6_attach_disabled"
P6_ATTACH_APPROVAL_MISMATCH = "p6_attach_approval_mismatch"
P6_ATTACH_GATE_BLOCKED = "p6_attach_gate_blocked"
P6_ATTACH_PRECONDITION_UNMET = "p6_attach_precondition_unmet"
P6_ATTACH_UNSAFE_MATERIAL = "p6_attach_unsafe_material"
P6_ATTACH_BACKEND_UNAVAILABLE = "p6_attach_backend_unavailable"
P6_ATTACH_HEALTH_DEGRADED = "p6_attach_health_degraded"
P6_ATTACH_NOT_ATTACHED = "p6_attach_not_attached"
P6_ATTACH_IDEMPOTENCY_CONFLICT = "p6_attach_idempotency_conflict"

P6_RUNTIME_ATTACH_STABLE_CODES = frozenset(
    {
        P6_ATTACH_DISABLED,
        P6_ATTACH_APPROVAL_MISMATCH,
        P6_ATTACH_GATE_BLOCKED,
        P6_ATTACH_PRECONDITION_UNMET,
        P6_ATTACH_UNSAFE_MATERIAL,
        P6_ATTACH_BACKEND_UNAVAILABLE,
        P6_ATTACH_HEALTH_DEGRADED,
        P6_ATTACH_NOT_ATTACHED,
        P6_ATTACH_IDEMPOTENCY_CONFLICT,
    }
)

_ATTACH_STATE_TYPE = "sachima.supervisor.p6_runtime_attach_state.v1"
_ATTACH_RESULT_TYPE = "sachima.supervisor.p6_runtime_attach_result.v1"
_SCHEMA_VERSION = 1
_SAFE_REF_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_ALLOWED_RUNTIME_KINDS = frozenset({"local_offline_like", "temporal_like"})
_ALLOWED_HEALTH = frozenset({"healthy", "degraded", "unavailable", "unknown"})
_UNSAFE_FINGERPRINT_VALUE = object()
_START_FINGERPRINT_FIELDS = (
    "run_id",
    "workflow_id",
    "workflow_spec_digest",
    "role_binding_digest",
    "approval_ref",
    "transaction_ref",
    "operation_ref",
    "idempotency_key",
)
_STEP_FINGERPRINT_FIELDS = (
    "run_id",
    "step_id",
    "attempt_index",
    "workflow_spec_digest",
    "role_binding_digest",
    "input_artifact_digests",
    "transaction_ref",
    "operation_ref",
    "idempotency_key",
)


@dataclass(frozen=True)
class RuntimeAttachRequest:
    """Sanitized caller-owned attach request.

    The request carries only safe refs and booleans. The caller supplies the actual
    P6/P5 control surface by constructing ``P6RuntimeAttachSession``; that object is
    never serialized into attach state.
    """

    enabled: bool
    approval_token: str
    attach_ref: str
    runtime_kind: str
    operator_gate: bool
    lease_id: str
    lease_epoch: int
    holder_ref: str
    state_version: int
    namespace_ref: str | None = None
    task_queue_ref: str | None = None


@dataclass(frozen=True)
class P6RuntimeAttachOutcome:
    ok: bool
    op: str
    admitted: bool
    error_code: str | None = None
    snapshot: dict[str, Any] | None = None
    active_run_watch: bool = False
    replayed: bool = False
    attach_status: str = "unattached"

    def to_projection(self) -> dict[str, Any]:
        projection = {
            "type": _ATTACH_RESULT_TYPE,
            "schema_version": _SCHEMA_VERSION,
            "ok": self.ok,
            "op": self.op,
            "admitted": self.admitted,
            "error_code": self.error_code,
            "snapshot": self.snapshot,
            "active_run_watch": self.active_run_watch,
            "replayed": self.replayed,
            "attach_status": self.attach_status,
        }
        if C.scan_projection_for_leak(projection) is not None:
            return {
                "type": _ATTACH_RESULT_TYPE,
                "schema_version": _SCHEMA_VERSION,
                "ok": False,
                "op": self.op,
                "admitted": False,
                "error_code": P6_ATTACH_UNSAFE_MATERIAL,
                "snapshot": None,
                "active_run_watch": False,
                "replayed": False,
                "attach_status": "unattached",
            }
        return projection


class P6RuntimeAttachSession:
    """Default-off caller-owned attach shell over an existing P6 session."""

    def __init__(
        self,
        *,
        p6_session: Any,
        claim_store: MutableMapping[str, dict[str, str]] | None = None,
    ) -> None:
        self._p6_session = p6_session
        self._attach_state: dict[str, Any] | None = None
        self._claim_store: MutableMapping[str, dict[str, str]] = {} if claim_store is None else claim_store
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Attach / state
    # ------------------------------------------------------------------ #
    def attach(
        self,
        request: RuntimeAttachRequest,
        *,
        health_probe: Callable[[], Mapping[str, Any]] | None = None,
    ) -> P6RuntimeAttachOutcome:
        code = self._attach_rejection_code(request)
        if code is not None:
            return self._rejected("attach", code)
        health = self._safe_health(health_probe)
        if isinstance(health, str):
            return self._rejected("attach", health)
        state = self._build_attach_state(request, health)
        if C.scan_projection_for_leak(state) is not None:
            return self._rejected("attach", P6_ATTACH_UNSAFE_MATERIAL)
        self._attach_state = state
        return P6RuntimeAttachOutcome(
            ok=True,
            op="attach",
            admitted=True,
            snapshot=copy.deepcopy(state),
            attach_status="attached",
        )

    def attach_state(self) -> dict[str, Any]:
        if self._attach_state is None:
            return {
                "type": _ATTACH_STATE_TYPE,
                "schema_version": _SCHEMA_VERSION,
                "attach_status": "unattached",
                "runtime_health": "unknown",
                "error_code": P6_ATTACH_NOT_ATTACHED,
            }
        state = copy.deepcopy(self._attach_state)
        if C.scan_projection_for_leak(state) is not None:
            return {
                "type": _ATTACH_STATE_TYPE,
                "schema_version": _SCHEMA_VERSION,
                "attach_status": "unattached",
                "runtime_health": "unknown",
                "error_code": P6_ATTACH_UNSAFE_MATERIAL,
            }
        return state

    # ------------------------------------------------------------------ #
    # Start / control wrappers
    # ------------------------------------------------------------------ #
    def start(
        self,
        run_request: Any,
        step_requests: list[Any],
        *,
        terminal_gate_ref: str | None = None,
    ) -> P6RuntimeAttachOutcome:
        if not self._is_attached():
            return self._rejected("start", P6_ATTACH_NOT_ATTACHED)
        if not self._start_refs_are_safe(
            run_request, step_requests, terminal_gate_ref=terminal_gate_ref
        ):
            return self._rejected("start", P6_ATTACH_UNSAFE_MATERIAL)
        fingerprint = self._start_fingerprint(
            run_request, step_requests, terminal_gate_ref=terminal_gate_ref
        )
        if fingerprint is None:
            return self._rejected("start", P6_ATTACH_UNSAFE_MATERIAL)
        run_id = getattr(run_request, "run_id", None)
        if not isinstance(run_id, str) or not run_id:
            return self._rejected("start", P6_ATTACH_UNSAFE_MATERIAL)
        with self._lock:
            previous_record = self._claim_store.get(run_id)
            previous = previous_record.get("fingerprint") if isinstance(previous_record, Mapping) else None
            if previous is not None:
                if previous != fingerprint:
                    return self._rejected("start", P6_ATTACH_IDEMPOTENCY_CONFLICT)
                recovery_step = (
                    previous_record.get("recovery_step")
                    if isinstance(previous_record, Mapping)
                    else None
                ) or self._first_step_id(step_requests)
                recovered = self.recover(run_id=run_id, step_id=recovery_step or "")
                return P6RuntimeAttachOutcome(
                    ok=recovered.ok,
                    op="start",
                    admitted=recovered.admitted,
                    error_code=recovered.error_code,
                    snapshot=recovered.snapshot,
                    active_run_watch=recovered.active_run_watch,
                    replayed=True,
                    attach_status=recovered.attach_status,
                )
            # Claim before delegation while holding the in-process lock and write
            # the claim into caller-owned storage. If the underlying caller-owned
            # P6 session launches work and then loses the response or raises, a
            # duplicate identical start must recover/reattach instead of relaunching,
            # even if the attach wrapper instance is recreated with the same store.
            first_step = self._first_step_id(step_requests)
            self._claim_store[run_id] = {
                "fingerprint": fingerprint,
                "recovery_step": first_step or "",
            }
        try:
            outcome = self._p6_session.run_linear(
                run_request, step_requests, terminal_gate_ref=terminal_gate_ref
            )
        except BaseException:  # noqa: BLE001 - boundary returns stable code only
            return self._rejected("start", P6_ATTACH_BACKEND_UNAVAILABLE)
        return self._from_p6_outcome("start", outcome)

    def query(self, *, run_id: str, step_id: str) -> P6RuntimeAttachOutcome:
        if not self._is_attached():
            return self._rejected("query", P6_ATTACH_NOT_ATTACHED)
        if not self._is_safe_ref(run_id) or not self._is_safe_ref(step_id):
            return self._rejected("query", P6_ATTACH_UNSAFE_MATERIAL)
        try:
            return self._from_p6_outcome("query", self._p6_session.query(run_id=run_id, step_id=step_id))
        except BaseException:  # noqa: BLE001
            return self._rejected("query", P6_ATTACH_BACKEND_UNAVAILABLE)

    def recover(self, *, run_id: str, step_id: str) -> P6RuntimeAttachOutcome:
        if not self._is_attached():
            return self._rejected("recover", P6_ATTACH_NOT_ATTACHED)
        if not self._is_safe_ref(run_id) or not self._is_safe_ref(step_id):
            return self._rejected("recover", P6_ATTACH_UNSAFE_MATERIAL)
        try:
            return self._from_p6_outcome("recover", self._p6_session.recover(run_id=run_id, step_id=step_id))
        except BaseException:  # noqa: BLE001
            return self._rejected("recover", P6_ATTACH_BACKEND_UNAVAILABLE)

    def cancel(self, cancel_request: Any) -> P6RuntimeAttachOutcome:
        if not self._is_attached():
            return self._rejected("cancel", P6_ATTACH_NOT_ATTACHED)
        if not self._cancel_refs_are_safe(cancel_request):
            return self._rejected("cancel", P6_ATTACH_UNSAFE_MATERIAL)
        try:
            return self._from_p6_outcome("cancel", self._p6_session.cancel(cancel_request))
        except BaseException:  # noqa: BLE001
            return self._rejected("cancel", P6_ATTACH_BACKEND_UNAVAILABLE)

    def close(
        self,
        *,
        run_id: str,
        terminal_gate_ref: str | None = None,
        detach: bool = False,
    ) -> P6RuntimeAttachOutcome:
        if not self._is_attached():
            return self._rejected("close", P6_ATTACH_NOT_ATTACHED)
        if not self._is_safe_ref(run_id):
            return self._rejected("close", P6_ATTACH_UNSAFE_MATERIAL)
        if terminal_gate_ref is not None and not self._is_safe_ref(terminal_gate_ref):
            return self._rejected("close", P6_ATTACH_UNSAFE_MATERIAL)
        try:
            outcome = self._from_p6_outcome(
                "close",
                self._p6_session.close(run_id=run_id, terminal_gate_ref=terminal_gate_ref),
            )
        except BaseException:  # noqa: BLE001
            return self._rejected("close", P6_ATTACH_BACKEND_UNAVAILABLE)
        if detach and self._attach_state is not None:
            self._attach_state = {**self._attach_state, "attach_status": "detached"}
            outcome = P6RuntimeAttachOutcome(
                ok=outcome.ok,
                op=outcome.op,
                admitted=outcome.admitted,
                error_code=outcome.error_code,
                snapshot=outcome.snapshot,
                active_run_watch=outcome.active_run_watch,
                replayed=outcome.replayed,
                attach_status="detached",
            )
        return outcome

    # ------------------------------------------------------------------ #
    # Admission / validation
    # ------------------------------------------------------------------ #
    def _attach_rejection_code(self, request: RuntimeAttachRequest) -> str | None:
        if not isinstance(request, RuntimeAttachRequest):
            return P6_ATTACH_PRECONDITION_UNMET
        if request.enabled is not True:
            return P6_ATTACH_DISABLED
        if request.approval_token != P6_RUNTIME_ATTACH_IMPLEMENTATION_APPROVAL_TOKEN:
            return P6_ATTACH_APPROVAL_MISMATCH
        if request.operator_gate is not True:
            return P6_ATTACH_GATE_BLOCKED
        if request.runtime_kind not in _ALLOWED_RUNTIME_KINDS:
            return P6_ATTACH_PRECONDITION_UNMET
        if not all(
            self._is_safe_ref(value)
            for value in (
                request.attach_ref,
                request.lease_id,
                request.holder_ref,
            )
        ):
            return P6_ATTACH_UNSAFE_MATERIAL
        if request.namespace_ref is not None and not self._is_safe_ref(request.namespace_ref):
            return P6_ATTACH_UNSAFE_MATERIAL
        if request.task_queue_ref is not None and not self._is_safe_ref(request.task_queue_ref):
            return P6_ATTACH_UNSAFE_MATERIAL
        if type(request.lease_epoch) is not int or request.lease_epoch < 0:
            return P6_ATTACH_PRECONDITION_UNMET
        if type(request.state_version) is not int or request.state_version < 1:
            return P6_ATTACH_PRECONDITION_UNMET
        if not self._p6_session_is_attached_capable():
            return P6_ATTACH_PRECONDITION_UNMET
        return None

    def _p6_session_is_attached_capable(self) -> bool:
        required = ("run_linear", "query", "recover", "cancel", "close", "admit")
        if not all(callable(getattr(self._p6_session, name, None)) for name in required):
            return False
        try:
            admission = self._p6_session.admit()
        except BaseException:  # noqa: BLE001
            return False
        if getattr(admission, "ok", None) is not True:
            return False
        return self._executor_is_first_slice_local_offline()

    def _executor_is_first_slice_local_offline(self) -> bool:
        """Reject broader real/P6-B runners for this first attach slice.

        The approved implementation may attach only to deterministic/injected-fake
        or local/offline P5-style executor surfaces. It must not wrap the reusable
        P6-B real-agent bridge, acpx/npx runners, or write-capable role surfaces.
        """

        executor = getattr(self._p6_session, "executor", None)
        if executor is None:
            return False
        token = getattr(executor, "approval_token", None)
        if token != P5_RUNTIME_ADAPTER_IMPLEMENTATION_APPROVAL_TOKEN:
            return False
        cursor = executor
        seen: set[int] = set()
        saw_local_offline_adapter = False
        while cursor is not None and id(cursor) not in seen:
            seen.add(id(cursor))
            if isinstance(cursor, P5LocalOfflineRuntimeAdapter):
                saw_local_offline_adapter = True
            label = f"{type(cursor).__module__}.{type(cursor).__name__}".lower()
            if any(marker in label for marker in ("p6b", "real_agent", "acpx", "npx", "codex", "claude")):
                return False
            cursor = getattr(cursor, "wrapped", None)
        return saw_local_offline_adapter

    def _safe_health(
        self, health_probe: Callable[[], Mapping[str, Any]] | None
    ) -> dict[str, Any] | str:
        if health_probe is None:
            return {"runtime_health": "unknown", "backend_ref": "safe_backend_ref_unknown"}
        try:
            raw = health_probe()
        except BaseException:  # noqa: BLE001
            return P6_ATTACH_BACKEND_UNAVAILABLE
        if not isinstance(raw, Mapping):
            return P6_ATTACH_PRECONDITION_UNMET
        if C.scan_projection_for_leak(dict(raw)) is not None:
            return P6_ATTACH_UNSAFE_MATERIAL
        runtime_health = raw.get("runtime_health", "unknown")
        backend_ref = raw.get("backend_ref", "safe_backend_ref_unknown")
        if runtime_health not in _ALLOWED_HEALTH:
            return P6_ATTACH_PRECONDITION_UNMET
        if not self._is_safe_ref(backend_ref):
            return P6_ATTACH_UNSAFE_MATERIAL
        if runtime_health == "degraded":
            return P6_ATTACH_HEALTH_DEGRADED
        if runtime_health == "unavailable":
            return P6_ATTACH_BACKEND_UNAVAILABLE
        health = {"runtime_health": runtime_health, "backend_ref": backend_ref}
        if C.scan_projection_for_leak(health) is not None:
            return P6_ATTACH_UNSAFE_MATERIAL
        return health

    @staticmethod
    def _is_safe_ref(value: Any) -> bool:
        if type(value) is not str or not _SAFE_REF_RE.match(value):
            return False
        return C.scan_projection_for_leak({"ref": value}) is None

    def _cancel_refs_are_safe(self, cancel_request: Any) -> bool:
        required = ("cancel_id", "run_id", "scope", "transaction_ref", "operation_ref", "idempotency_key")
        for name in required:
            if not self._is_safe_ref(getattr(cancel_request, name, None)):
                return False
        step_id = getattr(cancel_request, "step_id", None)
        if step_id is not None and not self._is_safe_ref(step_id):
            return False
        reason_code = getattr(cancel_request, "reason_code", None)
        if reason_code is not None and not self._is_safe_ref(reason_code):
            return False
        return True

    def _start_refs_are_safe(
        self,
        run_request: Any,
        step_requests: list[Any],
        *,
        terminal_gate_ref: str | None,
    ) -> bool:
        if self._object_projection(run_request, _START_FINGERPRINT_FIELDS) is None:
            return False
        if terminal_gate_ref is not None and not self._is_safe_ref(terminal_gate_ref):
            return False
        for step in step_requests:
            if self._object_projection(step, _STEP_FINGERPRINT_FIELDS) is None:
                return False
        return True

    def _build_attach_state(
        self, request: RuntimeAttachRequest, health: Mapping[str, Any]
    ) -> dict[str, Any]:
        state: dict[str, Any] = {
            "type": _ATTACH_STATE_TYPE,
            "schema_version": _SCHEMA_VERSION,
            "attach_status": "attached",
            "runtime_kind": request.runtime_kind,
            "attach_ref": request.attach_ref,
            "runtime_health": health["runtime_health"],
            "backend_ref": health["backend_ref"],
            "error_code": None,
            "lease": {
                "lease_id": request.lease_id,
                "lease_epoch": request.lease_epoch,
                "holder_ref": request.holder_ref,
                "state_version": request.state_version,
            },
        }
        if request.namespace_ref is not None:
            state["namespace_ref"] = request.namespace_ref
        if request.task_queue_ref is not None:
            state["task_queue_ref"] = request.task_queue_ref
        state["attach_digest"] = _digest_ref(state)
        return state

    def _is_attached(self) -> bool:
        return self._attach_state is not None and self._attach_state.get("attach_status") == "attached"

    # ------------------------------------------------------------------ #
    # Outcome / fingerprint helpers
    # ------------------------------------------------------------------ #
    def _from_p6_outcome(self, op: str, outcome: Any) -> P6RuntimeAttachOutcome:
        snapshot = getattr(outcome, "snapshot", None)
        if snapshot is None:
            snapshot = getattr(outcome, "evidence", None)
        safe_snapshot = dict(snapshot) if isinstance(snapshot, Mapping) else None
        if safe_snapshot is not None and C.scan_projection_for_leak(safe_snapshot) is not None:
            return self._rejected(op, P6_ATTACH_UNSAFE_MATERIAL)
        error_code = self._safe_downstream_error_code(
            getattr(outcome, "error_code", None) or getattr(outcome, "admission_code", None)
        )
        if error_code == P6_ATTACH_UNSAFE_MATERIAL:
            return self._rejected(op, P6_ATTACH_UNSAFE_MATERIAL)
        return P6RuntimeAttachOutcome(
            ok=getattr(outcome, "ok", None) is True,
            op=op,
            admitted=getattr(outcome, "admitted", True) is True,
            error_code=error_code,
            snapshot=safe_snapshot,
            active_run_watch=getattr(outcome, "active_run_watch", False) is True,
            replayed=getattr(outcome, "replayed", False) is True,
            attach_status=str(self._attach_state.get("attach_status", "attached"))
            if self._attach_state is not None
            else "unattached",
        )

    @staticmethod
    def _safe_downstream_error_code(code: Any) -> str | None:
        if code is None:
            return None
        allowed = P6_RUNTIME_ATTACH_STABLE_CODES | C.STABLE_CODES | P6_STABLE_CODES
        if type(code) is not str:
            return P6_ATTACH_UNSAFE_MATERIAL
        if code not in allowed:
            return P6_ATTACH_UNSAFE_MATERIAL
        if C.scan_projection_for_leak({"error_code": code}) is not None:
            return P6_ATTACH_UNSAFE_MATERIAL
        return code

    @staticmethod
    def _rejected(op: str, code: str) -> P6RuntimeAttachOutcome:
        return P6RuntimeAttachOutcome(
            ok=False,
            op=op,
            admitted=False,
            error_code=code if code in P6_RUNTIME_ATTACH_STABLE_CODES else P6_ATTACH_PRECONDITION_UNMET,
            snapshot=None,
            active_run_watch=False,
            replayed=False,
            attach_status="unattached",
        )

    def _start_fingerprint(
        self,
        run_request: Any,
        step_requests: list[Any],
        *,
        terminal_gate_ref: str | None,
    ) -> str | None:
        material = {
            "run": self._object_projection(run_request, _START_FINGERPRINT_FIELDS),
            "steps": [self._object_projection(step, _STEP_FINGERPRINT_FIELDS) for step in step_requests],
            "terminal_gate_ref": terminal_gate_ref,
        }
        if any(value is None for value in material["steps"]):
            return None
        if material["run"] is None:
            return None
        if C.scan_projection_for_leak(material) is not None:
            return None
        return _digest_ref(material)

    @staticmethod
    def _object_projection(obj: Any, fields: tuple[str, ...]) -> dict[str, Any] | None:
        raw: Mapping[str, Any]
        if is_dataclass(obj) and not isinstance(obj, type):
            raw = asdict(obj)
        else:
            raw = {field: getattr(obj, field, None) for field in fields}
        out: dict[str, Any] = {}
        for field, value in raw.items():
            normalized = P6RuntimeAttachSession._normalize_fingerprint_value(field, value)
            if normalized is _UNSAFE_FINGERPRINT_VALUE:
                return None
            out[field] = normalized
        return out

    @staticmethod
    def _normalize_fingerprint_value(field: str, value: Any) -> Any:
        if value is None:
            return None
        if type(value) in {int, bool}:
            return value
        if type(value) is str:
            if field == "approval_token":
                return _digest_ref({"approval_token": value})
            return value if P6RuntimeAttachSession._is_safe_ref(value) else _UNSAFE_FINGERPRINT_VALUE
        if isinstance(value, tuple):
            normalized = [P6RuntimeAttachSession._normalize_fingerprint_value(field, item) for item in value]
            return normalized if _UNSAFE_FINGERPRINT_VALUE not in normalized else _UNSAFE_FINGERPRINT_VALUE
        if isinstance(value, list):
            normalized = [P6RuntimeAttachSession._normalize_fingerprint_value(field, item) for item in value]
            return normalized if _UNSAFE_FINGERPRINT_VALUE not in normalized else _UNSAFE_FINGERPRINT_VALUE
        return _UNSAFE_FINGERPRINT_VALUE

    @staticmethod
    def _first_step_id(step_requests: list[Any]) -> str | None:
        if not step_requests:
            return None
        value = getattr(step_requests[0], "step_id", None)
        return value if isinstance(value, str) and value else None


def _digest_ref(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "P6_RUNTIME_ATTACH_IMPLEMENTATION_APPROVAL_TOKEN",
    "P6_ATTACH_DISABLED",
    "P6_ATTACH_APPROVAL_MISMATCH",
    "P6_ATTACH_GATE_BLOCKED",
    "P6_ATTACH_PRECONDITION_UNMET",
    "P6_ATTACH_UNSAFE_MATERIAL",
    "P6_ATTACH_BACKEND_UNAVAILABLE",
    "P6_ATTACH_HEALTH_DEGRADED",
    "P6_ATTACH_NOT_ATTACHED",
    "P6_ATTACH_IDEMPOTENCY_CONFLICT",
    "P6_RUNTIME_ATTACH_STABLE_CODES",
    "RuntimeAttachRequest",
    "P6RuntimeAttachOutcome",
    "P6RuntimeAttachSession",
]
