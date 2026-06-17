"""Controlled AI FLOW caller-owned CAS run/step store (WP4 slice 1, FR4).

Local/offline only, in-process, lock-guarded — the approved first-slice store
shape (a cross-process durable adapter remains a later, separately approved
gate). ``AiFlowRunStore`` re-implements the ``ControlledLocalExecClaimStore``
check-and-set contract at *step* granularity: ``claim_step`` is the single
atomic pre-execute boundary, identical replays return the resident projection
with no second executor call, conflicting replays fail closed, and every
resident record is revalidated on every read so hostile material can never be
projected.

Per the WP4 convention this module owns its own sanitization primitives rather
than importing private helpers from the controlled-exec store.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
_STEP_RECORD_TYPE = "sachima.supervisor.ai_flow_step_record.v1"
_RUN_RECORD_TYPE = "sachima.supervisor.ai_flow_run_record.v1"
_GATE_RECORD_TYPE = "sachima.supervisor.ai_flow_gate_record.v1"
_ARTIFACT_RECORD_TYPE = "sachima.supervisor.ai_flow_artifact_ref.v1"
_CANCEL_RECORD_TYPE = "sachima.supervisor.ai_flow_cancel_record.v1"

_STEP_VIEW_PREFIX = "ai_flow_step_view_"
_RUN_VIEW_PREFIX = "ai_flow_run_view_"
_CANCEL_VIEW_PREFIX = "ai_flow_cancel_view_"

STEP_CLAIMED = "claimed_in_progress"
STEP_COMPLETED = "completed"
STEP_FAILED_RETRYABLE = "failed_retryable"
STEP_FAILED_TERMINAL = "failed_terminal"
STEP_GATE_BLOCKED = "gate_blocked"
STEP_CANCELLED = "cancelled"
STEP_WATCH = "active_run_cancellation_watch"
STEP_CANCEL_AMBIGUOUS = "cancel_ambiguous"

_STEP_TERMINAL_STATUSES = frozenset(
    {
        STEP_COMPLETED,
        STEP_FAILED_RETRYABLE,
        STEP_FAILED_TERMINAL,
        STEP_GATE_BLOCKED,
        STEP_CANCELLED,
        STEP_WATCH,
        STEP_CANCEL_AMBIGUOUS,
    }
)
_STEP_STATUSES = frozenset({STEP_CLAIMED, *_STEP_TERMINAL_STATUSES})

#: Stable error codes any record may carry. Anything else fails closed on read.
_STORED_ERROR_CODES = frozenset(
    {
        "activity_idempotency_conflict",
        "activity_claim_conflict",
        "activity_unsafe_material",
        "activity_precondition_unmet",
        "activity_step_failed",
        "activity_step_gate_blocked",
        "activity_artifact_integrity_failed",
        "activity_supervisor_failed",
        "active_run_cancellation_watch",
        "activity_cancel_ambiguous",
        "activity_budget_exceeded",
    }
)

_REF_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_EVIDENCE_REF_RE = re.compile(r"^[a-z][a-z0-9_:-]{0,127}$")
_STABLE_CODE_RE = re.compile(r"^[a-z][a-z0-9_:-]{0,63}$")
_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")

_UNSAFE_MARKERS: tuple[str, ...] = (
    "media_path",
    "raw_prompt",
    "prompt_body",
    "card_json",
    "signed_url",
    "tool_output",
    "bearer ",
    "api_key",
    "private_key",
    "/tmp/",
    "media:",
)

_STEP_STATE_KEYS = frozenset(
    {
        "type",
        "ok",
        "status",
        "run_id",
        "step_id",
        "logical_role",
        "role_key",
        "workflow_spec_digest",
        "role_binding_digest",
        "idempotency_key",
        "attempt_index",
        "input_artifact_digests",
        "artifact_ref_count",
        "output_artifact_id",
        "output_artifact_digest",
        "output_artifact_kind",
        "evidence_ref",
        "evidence_digest",
        "error_code",
        "retryable",
        "view_model_ref",
    }
)


class AiFlowError(Exception):
    """Fail-closed CAS-store error carrying a stable code."""

    def __init__(self, error_code: str, message: str = "") -> None:
        self.error_code = error_code
        super().__init__(message or error_code)


# --------------------------------------------------------------------------- #
# Sanitization primitives (copied per module by convention)
# --------------------------------------------------------------------------- #
def _digest_hex(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _string_is_safe(value: str) -> bool:
    lowered = value.lower()
    return not any(marker in lowered for marker in _UNSAFE_MARKERS)


def _is_safe_ref(value: Any) -> bool:
    return (
        type(value) is str
        and _REF_RE.fullmatch(value) is not None
        and _string_is_safe(value)
    )


def _is_safe_evidence_ref(value: Any) -> bool:
    return (
        type(value) is str
        and _EVIDENCE_REF_RE.fullmatch(value) is not None
        and _string_is_safe(value)
    )


def _is_safe_digest(value: Any) -> bool:
    return type(value) is str and _SHA256_DIGEST_RE.fullmatch(value) is not None


def _is_safe_fingerprint(value: Any) -> bool:
    return type(value) is str and _FINGERPRINT_RE.fullmatch(value) is not None


def _is_int_at_least(value: Any, minimum: int) -> bool:
    return type(value) is int and value >= minimum


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        out: list[str] = []
        for key, item in value.items():
            out.extend(_walk_strings(str(key)))
            out.extend(_walk_strings(item))
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            out.extend(_walk_strings(item))
        return out
    return []


def _unsafe() -> AiFlowError:
    return AiFlowError("activity_unsafe_material", "unsafe durable record rejected")


def _assert_strings_safe(state: Mapping[str, Any]) -> None:
    for text in _walk_strings(state):
        if not _string_is_safe(text):
            raise _unsafe()


# --------------------------------------------------------------------------- #
# Step fingerprint (FR4 exact binding) + state builder
# --------------------------------------------------------------------------- #
def step_fingerprint(
    *,
    run_id: str,
    step_id: str,
    workflow_spec_digest: str,
    role_binding_digest: str,
    input_artifact_digests: tuple[str, ...],
    approval_ref: str,
    attempt_index: int,
) -> str:
    """Return the 64-hex step idempotency fingerprint over exactly the FR4 set."""

    payload = {
        "run_id": run_id,
        "step_id": step_id,
        "workflow_spec_digest": workflow_spec_digest,
        "role_binding_digest": role_binding_digest,
        "input_artifact_digests": list(input_artifact_digests),
        "approval_ref": approval_ref,
        "attempt_index": attempt_index,
    }
    return _digest_hex(payload)


def build_step_state(
    *,
    status: str,
    ok: bool,
    run_id: str,
    step_id: str,
    logical_role: str,
    role_key: str,
    workflow_spec_digest: str,
    role_binding_digest: str,
    idempotency_key: str,
    attempt_index: int,
    input_artifact_digests: tuple[str, ...],
    artifact_ref_count: int = 0,
    output_artifact_id: str | None = None,
    output_artifact_digest: str | None = None,
    output_artifact_kind: str | None = None,
    evidence_ref: str | None = None,
    evidence_digest: str | None = None,
    error_code: str | None = None,
    retryable: bool = False,
) -> dict[str, Any]:
    """Build a validated step record dict with a derived view-model ref."""

    core: dict[str, Any] = {
        "type": _STEP_RECORD_TYPE,
        "ok": ok,
        "status": status,
        "run_id": run_id,
        "step_id": step_id,
        "logical_role": logical_role,
        "role_key": role_key,
        "workflow_spec_digest": workflow_spec_digest,
        "role_binding_digest": role_binding_digest,
        "idempotency_key": idempotency_key,
        "attempt_index": attempt_index,
        "input_artifact_digests": list(input_artifact_digests),
        "artifact_ref_count": artifact_ref_count,
        "output_artifact_id": output_artifact_id,
        "output_artifact_digest": output_artifact_digest,
        "output_artifact_kind": output_artifact_kind,
        "evidence_ref": evidence_ref,
        "evidence_digest": evidence_digest,
        "error_code": error_code,
        "retryable": retryable,
    }
    view_model_ref = _STEP_VIEW_PREFIX + _digest_hex(core)[:16]
    return _validate_step_projection({**core, "view_model_ref": view_model_ref})


def build_run_state(
    *,
    ok: bool,
    status: str,
    run_id: str,
    workflow_id: str,
    workflow_spec_digest: str,
    role_binding_digest: str,
    approval_ref: str,
    admission_gate_ref: str | None,
    transaction_ref: str,
    operation_ref: str,
    idempotency_key: str,
    lease_id: str | None = None,
    lease_epoch: int = 0,
    lease_holder_ref: str | None = None,
    state_version: int = 0,
    error_code: str | None = None,
) -> dict[str, Any]:
    """Build a validated workflow-run record dict with a derived view ref."""

    core: dict[str, Any] = {
        "type": _RUN_RECORD_TYPE,
        "ok": ok,
        "status": status,
        "run_id": run_id,
        "workflow_id": workflow_id,
        "workflow_spec_digest": workflow_spec_digest,
        "role_binding_digest": role_binding_digest,
        "approval_ref": approval_ref,
        "admission_gate_ref": admission_gate_ref,
        "transaction_ref": transaction_ref,
        "operation_ref": operation_ref,
        "idempotency_key": idempotency_key,
        "lease_id": lease_id,
        "lease_epoch": lease_epoch,
        "lease_holder_ref": lease_holder_ref,
        "state_version": state_version,
        "error_code": error_code,
    }
    view_model_ref = _RUN_VIEW_PREFIX + _digest_hex(core)[:16]
    return _validate_run_projection({**core, "view_model_ref": view_model_ref})


def build_cancel_state(
    *,
    ok: bool,
    status: str,
    cancel_id: str,
    run_id: str,
    step_id: str | None,
    scope: str,
    transaction_ref: str,
    operation_ref: str,
    idempotency_key: str,
    reason_code: str | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    """Build a validated cancellation record dict with a derived view ref."""

    core: dict[str, Any] = {
        "type": _CANCEL_RECORD_TYPE,
        "ok": ok,
        "status": status,
        "cancel_id": cancel_id,
        "run_id": run_id,
        "step_id": step_id,
        "scope": scope,
        "transaction_ref": transaction_ref,
        "operation_ref": operation_ref,
        "idempotency_key": idempotency_key,
        "reason_code": reason_code,
        "error_code": error_code,
    }
    view_model_ref = _CANCEL_VIEW_PREFIX + _digest_hex(core)[:16]
    return _validate_cancel_projection({**core, "view_model_ref": view_model_ref})


# --------------------------------------------------------------------------- #
# Validators (validate-on-read)
# --------------------------------------------------------------------------- #
def _validate_step_projection(state: Mapping[str, Any]) -> dict[str, Any]:
    if type(state) is not dict or set(state) != _STEP_STATE_KEYS:
        raise _unsafe()
    projected = dict(state)
    if (
        projected["type"] != _STEP_RECORD_TYPE
        or projected["status"] not in _STEP_STATUSES
        or type(projected["ok"]) is not bool
        or type(projected["retryable"]) is not bool
    ):
        raise _unsafe()
    for key in ("run_id", "step_id", "logical_role", "role_key", "idempotency_key", "view_model_ref"):
        if not _is_safe_ref(projected[key]):
            raise _unsafe()
    if not projected["view_model_ref"].startswith(_STEP_VIEW_PREFIX):
        raise _unsafe()
    if not _is_safe_digest(projected["workflow_spec_digest"]) or not _is_safe_digest(
        projected["role_binding_digest"]
    ):
        raise _unsafe()
    if not _is_int_at_least(projected["attempt_index"], 1) or not _is_int_at_least(
        projected["artifact_ref_count"], 0
    ):
        raise _unsafe()
    digests = projected["input_artifact_digests"]
    if type(digests) is not list or any(not _is_safe_digest(d) for d in digests):
        raise _unsafe()
    for key in ("output_artifact_id", "output_artifact_kind"):
        if projected[key] is not None and not _is_safe_ref(projected[key]):
            raise _unsafe()
    if projected["output_artifact_digest"] is not None and not _is_safe_digest(
        projected["output_artifact_digest"]
    ):
        raise _unsafe()
    if projected["evidence_ref"] is not None and not _is_safe_evidence_ref(projected["evidence_ref"]):
        raise _unsafe()
    if projected["evidence_digest"] is not None and not _is_safe_digest(projected["evidence_digest"]):
        raise _unsafe()
    if projected["error_code"] is not None and projected["error_code"] not in _STORED_ERROR_CODES:
        raise _unsafe()
    _assert_strings_safe(projected)
    return projected


def _validate_generic(
    state: Mapping[str, Any], *, keys: frozenset[str], type_value: str
) -> dict[str, Any]:
    if type(state) is not dict or set(state) != keys:
        raise _unsafe()
    projected = dict(state)
    if projected["type"] != type_value:
        raise _unsafe()
    if "ok" in projected and type(projected["ok"]) is not bool:
        raise _unsafe()
    if "status" in projected:
        status = projected["status"]
        if type(status) is not str or _STABLE_CODE_RE.fullmatch(status) is None:
            raise _unsafe()
    if "error_code" in projected:
        code = projected["error_code"]
        if code is not None and code not in _STORED_ERROR_CODES:
            raise _unsafe()
    _assert_strings_safe(projected)
    return projected


_RUN_STATE_KEYS = frozenset(
    {
        "type",
        "ok",
        "status",
        "run_id",
        "workflow_id",
        "workflow_spec_digest",
        "role_binding_digest",
        "approval_ref",
        "admission_gate_ref",
        "transaction_ref",
        "operation_ref",
        "idempotency_key",
        "lease_id",
        "lease_epoch",
        "lease_holder_ref",
        "state_version",
        "error_code",
        "view_model_ref",
    }
)
_GATE_STATE_KEYS = frozenset(
    {"type", "run_id", "gate_type", "gate_ref", "status", "step_id"}
)
_ARTIFACT_STATE_KEYS = frozenset(
    {
        "type",
        "run_id",
        "artifact_id",
        "producer_step_id",
        "content_digest",
        "artifact_kind",
        "byte_count",
        "created_at_ref",
    }
)
_CANCEL_STATE_KEYS = frozenset(
    {
        "type",
        "ok",
        "status",
        "cancel_id",
        "run_id",
        "step_id",
        "scope",
        "transaction_ref",
        "operation_ref",
        "idempotency_key",
        "reason_code",
        "error_code",
        "view_model_ref",
    }
)


def _validate_run_projection(state: Mapping[str, Any]) -> dict[str, Any]:
    return _validate_generic(state, keys=_RUN_STATE_KEYS, type_value=_RUN_RECORD_TYPE)


def _validate_gate_projection(state: Mapping[str, Any]) -> dict[str, Any]:
    return _validate_generic(state, keys=_GATE_STATE_KEYS, type_value=_GATE_RECORD_TYPE)


def _validate_artifact_projection(state: Mapping[str, Any]) -> dict[str, Any]:
    return _validate_generic(state, keys=_ARTIFACT_STATE_KEYS, type_value=_ARTIFACT_RECORD_TYPE)


def _validate_cancel_projection(state: Mapping[str, Any]) -> dict[str, Any]:
    return _validate_generic(state, keys=_CANCEL_STATE_KEYS, type_value=_CANCEL_RECORD_TYPE)


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #
@dataclass
class AiFlowRunStore:
    """Caller-owned, in-process, lock-guarded CAS store for one workflow run set."""

    _runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    _run_idem: dict[str, tuple[str, dict[str, Any]]] = field(default_factory=dict)
    _by_step_idem: dict[str, tuple[str, dict[str, Any]]] = field(default_factory=dict)
    _steps: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    _gates: dict[tuple[str, str, str | None], dict[str, Any]] = field(default_factory=dict)
    _artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    _cancels: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    # ---- runs ----
    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            raw = self._runs.get(run_id)
            return None if raw is None else _validate_run_projection(raw)

    def record_run(
        self, *, run_id: str, idempotency_key: str, fingerprint: str, state: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        if not _is_safe_fingerprint(fingerprint):
            raise _unsafe()
        with self._lock:
            existing = self._run_idem.get(idempotency_key)
            if existing is not None:
                fp, st = existing
                validated = _validate_run_projection(st)
                if fp != fingerprint:
                    raise AiFlowError(
                        "activity_idempotency_conflict",
                        "idempotency key maps to an incompatible workflow run",
                    )
                return "replayed", validated
            if run_id in self._runs:
                raise AiFlowError(
                    "activity_claim_conflict", "run already created under a different key"
                )
            stored = _validate_run_projection(state)
            self._runs[run_id] = stored
            self._run_idem[idempotency_key] = (fingerprint, stored)
            return "acquired", stored

    def update_run(self, *, run_id: str, state: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            return self._update_run_locked(run_id=run_id, state=state)

    def _update_run_locked(self, *, run_id: str, state: dict[str, Any]) -> dict[str, Any]:
        if run_id not in self._runs:
            raise AiFlowError("activity_not_found", "no run to update")
        stored = _validate_run_projection(state)
        if stored["run_id"] != run_id:
            raise _unsafe()
        self._runs[run_id] = stored
        # keep the idempotency mirror consistent
        for key, (fp, _old) in list(self._run_idem.items()):
            if _old["run_id"] == run_id:
                self._run_idem[key] = (fp, stored)
        return stored

    # ---- steps ----
    def get_step(self, run_id: str, step_id: str) -> dict[str, Any] | None:
        with self._lock:
            raw = self._steps.get((run_id, step_id))
            return None if raw is None else _validate_step_projection(raw)

    def get_step_idempotent(self, idempotency_key: str) -> tuple[str, dict[str, Any]] | None:
        with self._lock:
            existing = self._by_step_idem.get(idempotency_key)
            if existing is None:
                return None
            fingerprint, state = existing
            if not _is_safe_fingerprint(fingerprint):
                raise _unsafe()
            return fingerprint, _validate_step_projection(state)

    def list_steps(self, run_id: str) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(
                _validate_step_projection(state)
                for (rid, _sid), state in self._steps.items()
                if rid == run_id
            )

    def claim_step(
        self,
        *,
        run_id: str,
        step_id: str,
        idempotency_key: str,
        fingerprint: str,
        state: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Atomic pre-execute claim. Returns ``("acquired"|"replayed", state)``."""

        if not _is_safe_fingerprint(fingerprint):
            raise _unsafe()
        with self._lock:
            existing = self.get_step_idempotent(idempotency_key)
            if existing is not None:
                existing_fingerprint, existing_state = existing
                if existing_fingerprint != fingerprint:
                    raise AiFlowError(
                        "activity_idempotency_conflict",
                        "idempotency key maps to an incompatible step attempt",
                    )
                return "replayed", existing_state
            if (run_id, step_id) in self._steps:
                raise AiFlowError(
                    "activity_claim_conflict",
                    "step is already claimed under a different idempotency key",
                )
            stored = _validate_step_projection(state)
            if (
                stored["status"] != STEP_CLAIMED
                or stored["run_id"] != run_id
                or stored["step_id"] != step_id
                or stored["idempotency_key"] != idempotency_key
            ):
                raise _unsafe()
            self._steps[(run_id, step_id)] = stored
            self._by_step_idem[idempotency_key] = (fingerprint, stored)
            return "acquired", stored

    def finalize_step(
        self,
        *,
        run_id: str,
        step_id: str,
        idempotency_key: str,
        fingerprint: str,
        state: dict[str, Any],
    ) -> None:
        if not _is_safe_fingerprint(fingerprint):
            raise _unsafe()
        with self._lock:
            existing = self.get_step_idempotent(idempotency_key)
            if existing is None:
                raise AiFlowError("activity_claim_conflict", "no resident step claim to finalize")
            existing_fingerprint, existing_state = existing
            if (
                existing_fingerprint != fingerprint
                or existing_state["status"] != STEP_CLAIMED
                or existing_state["run_id"] != run_id
                or existing_state["step_id"] != step_id
            ):
                raise AiFlowError("activity_claim_conflict", "resident claim does not match")
            stored = _validate_step_projection(state)
            if (
                stored["status"] not in _STEP_TERMINAL_STATUSES
                or stored["run_id"] != run_id
                or stored["step_id"] != step_id
                or stored["idempotency_key"] != idempotency_key
            ):
                raise _unsafe()
            self._steps[(run_id, step_id)] = stored
            self._by_step_idem[idempotency_key] = (fingerprint, stored)

    def finalize_step_with_artifact_if_run_schedulable(
        self,
        *,
        run_id: str,
        step_id: str,
        idempotency_key: str,
        fingerprint: str,
        state: dict[str, Any],
        artifact_projection: dict[str, Any],
        non_schedulable_state: dict[str, Any],
        schedulable_statuses: Collection[str],
    ) -> dict[str, Any]:
        """Atomically persist a step output only while the run is schedulable.

        If a cancellation changed the run while this step was still resident in
        ``claimed_in_progress``, the step is finalized fail-closed and the
        artifact is deliberately not propagated.
        """

        if not _is_safe_fingerprint(fingerprint):
            raise _unsafe()
        with self._lock:
            existing = self.get_step_idempotent(idempotency_key)
            if existing is None:
                raise AiFlowError("activity_claim_conflict", "no resident step claim to finalize")
            existing_fingerprint, existing_state = existing
            if (
                existing_fingerprint != fingerprint
                or existing_state["status"] != STEP_CLAIMED
                or existing_state["run_id"] != run_id
                or existing_state["step_id"] != step_id
            ):
                raise AiFlowError("activity_claim_conflict", "resident claim does not match")
            run = self._runs.get(run_id)
            if run is None:
                raise AiFlowError("activity_not_found", "no run to finalize step against")
            run_state = _validate_run_projection(run)
            cancellation_recorded = any(
                _validate_cancel_projection(cancel)["run_id"] == run_id
                for cancel in self._cancels.values()
            )
            if run_state["status"] in schedulable_statuses and not cancellation_recorded:
                stored = _validate_step_projection(state)
                artifact_to_store = _validate_artifact_projection(
                    {**artifact_projection, "run_id": run_id}
                )
            else:
                stored = _validate_step_projection(non_schedulable_state)
                artifact_to_store = None
            if (
                stored["status"] not in _STEP_TERMINAL_STATUSES
                or stored["run_id"] != run_id
                or stored["step_id"] != step_id
                or stored["idempotency_key"] != idempotency_key
            ):
                raise _unsafe()
            if artifact_to_store is not None:
                self._artifacts[artifact_to_store["artifact_id"]] = artifact_to_store
            self._steps[(run_id, step_id)] = stored
            self._by_step_idem[idempotency_key] = (fingerprint, stored)
            return stored

    # ---- gates / artifacts / cancellations ----
    def record_gate(self, *, run_id: str, projection: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            state = {**projection, "run_id": run_id}
            stored = _validate_gate_projection(state)
            self._gates[(run_id, stored["gate_type"], stored["step_id"])] = stored
            return stored

    def get_gate(self, *, run_id: str, gate_type: str, step_id: str | None) -> dict[str, Any] | None:
        with self._lock:
            raw = self._gates.get((run_id, gate_type, step_id))
            return None if raw is None else _validate_gate_projection(raw)

    def record_artifact(self, *, run_id: str, projection: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            state = {**projection, "run_id": run_id}
            stored = _validate_artifact_projection(state)
            self._artifacts[stored["artifact_id"]] = stored
            return stored

    def find_artifact(
        self, *, run_id: str, artifact_kind: str, producer_step_id: str
    ) -> dict[str, Any] | None:
        with self._lock:
            for raw in self._artifacts.values():
                validated = _validate_artifact_projection(raw)
                if (
                    validated["run_id"] == run_id
                    and validated["artifact_kind"] == artifact_kind
                    and validated["producer_step_id"] == producer_step_id
                ):
                    return validated
            return None

    def record_cancellation(self, *, cancel_id: str, state: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            return self._record_cancellation_locked(cancel_id=cancel_id, state=state)

    def record_cancellation_and_update_run(
        self,
        *,
        cancel_id: str,
        cancel_state: dict[str, Any],
        run_id: str,
        run_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Atomically persist cancellation evidence and the matching run status."""

        with self._lock:
            stored = self._record_cancellation_locked(cancel_id=cancel_id, state=cancel_state)
            self._update_run_locked(run_id=run_id, state=run_state)
            return stored

    def _record_cancellation_locked(self, *, cancel_id: str, state: dict[str, Any]) -> dict[str, Any]:
        stored = _validate_cancel_projection(state)
        if stored["cancel_id"] != cancel_id:
            raise _unsafe()
        existing = self._cancels.get(cancel_id)
        if existing is not None:
            existing_stored = _validate_cancel_projection(existing)
            if existing_stored == stored:
                return existing_stored
            raise AiFlowError(
                "activity_idempotency_conflict",
                "cancel id maps to an incompatible cancellation request",
            )
        self._cancels[cancel_id] = stored
        return stored

    def get_cancellation(self, cancel_id: str) -> dict[str, Any] | None:
        with self._lock:
            raw = self._cancels.get(cancel_id)
            return None if raw is None else _validate_cancel_projection(raw)

    def list_cancellations(self, run_id: str) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(
                _validate_cancel_projection(state)
                for state in self._cancels.values()
                if state["run_id"] == run_id
            )

    def list_gates(self, run_id: str) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(
                _validate_gate_projection(state)
                for (rid, _gt, _sid), state in self._gates.items()
                if rid == run_id
            )

    def list_artifacts(self, run_id: str) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(
                _validate_artifact_projection(state)
                for state in self._artifacts.values()
                if state["run_id"] == run_id
            )

    def step_fingerprints(self, run_id: str) -> dict[str, str]:
        """Return ``{step_id: fingerprint}`` for the run (validate-on-read)."""

        with self._lock:
            out: dict[str, str] = {}
            for fingerprint, state in self._by_step_idem.values():
                if not _is_safe_fingerprint(fingerprint):
                    raise _unsafe()
                validated = _validate_step_projection(state)
                if validated["run_id"] == run_id:
                    out[validated["step_id"]] = fingerprint
            return out
