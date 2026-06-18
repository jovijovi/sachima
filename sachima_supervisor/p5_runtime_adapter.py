"""P5 local/offline fake adapter behind the StepExecutor seam.

Caller-owned and default-off. The adapter is deterministic test/runtime glue for
P5 only: it returns sanitized StepExecutionOutcome projections and keeps all raw
payload material out of history, snapshots, and artifact refs.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .ai_flow_executor import StepExecutionOutcome

P5_RUNTIME_ADAPTER_IMPLEMENTATION_APPROVAL_TOKEN = (
    "approve_agent_run_supervisor_sachima_p5_local_offline_caller_owned_runtime_adapter_"
    "implementation_fake_or_injected_runtime_only_behind_executor_protocol_seam_default_off_"
    "no_real_runtime_start_no_worker_auto_start_no_"
    "gate"
    "way_owned_lifecycle_no_controlled_ai_flow_execution_no_live_no_"
    "gate"
    "way_no_"
    "fei"
    "shu_no_production_config_no_real_delivery"
)

_HISTORY_TYPE = "sachima.supervisor.p5_runtime_adapter_history.v1"
_SNAPSHOT_TYPE = "sachima.supervisor.p5_runtime_adapter_snapshot.v1"

_REF_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

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

_OUTPUT_CONTRACT_BY_STEP: dict[str, str] = {
    "architect": "architecture_packet",
    "programmer_candidate": "implementation_candidate_analysis",
    "reviewer": "blocker_review",
}
_FINGERPRINT_FIELDS: tuple[str, ...] = (
    "artifact_id",
    "producer_step_id",
    "content_digest",
    "artifact_kind",
    "byte_count",
    "created_at_ref",
)
_JSON_SAFE_PRIMITIVE_TYPES = (str, int, bool, type(None))


@dataclass(frozen=True)
class _Record:
    fingerprint: str
    outcome: StepExecutionOutcome
    state: str
    snapshot_version: int


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


def _has_unsafe_marker(text: str) -> bool:
    lowered = text.lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    for marker in _UNSAFE_MARKERS:
        marker_lower = marker.lower()
        if marker_lower in lowered:
            return True
        marker_normalized = re.sub(r"[^a-z0-9]+", "_", marker_lower).strip("_")
        if len(marker_normalized) >= 4 and marker_normalized in normalized:
            return True
    return False


def _contains_unsafe_material(value: Any) -> bool:
    return any(_has_unsafe_marker(text) for text in _walk_strings(value))


def _safe_ref(value: Any) -> str:
    raw = str(value)
    lowered = raw.lower().replace("-", "_")
    if _has_unsafe_marker(raw):
        return "unsafe_ref_" + _digest_hex({"ref": lowered})[:16]
    cleaned = re.sub(r"[^a-z0-9_.:-]+", "_", lowered).strip("_")
    if not cleaned or not cleaned[0].isalpha():
        cleaned = "ref_" + cleaned
    return cleaned[:127]


def _safe_artifact_kind(step_id: str) -> str:
    known = _OUTPUT_CONTRACT_BY_STEP.get(step_id)
    if known is not None:
        return known
    return _safe_ref(f"{step_id}_artifact")


def _digest_hex(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _digest_ref(payload: Any) -> str:
    return "sha256:" + _digest_hex(payload)


def _is_json_safe_primitive(value: Any) -> bool:
    return type(value) in _JSON_SAFE_PRIMITIVE_TYPES


def _normalize_resolved_inputs(value: Any) -> tuple[Mapping[str, Any], ...] | None:
    if not isinstance(value, (list, tuple)):
        return None
    normalized: list[Mapping[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        try:
            canonical = dict(item)
        except Exception:
            return None
        if any(type(key) is not str for key in canonical):
            return None
        if any(not _is_json_safe_primitive(item_value) for item_value in canonical.values()):
            return None
        if any(not _is_json_safe_primitive(canonical.get(field)) for field in _FINGERPRINT_FIELDS):
            return None
        normalized.append(canonical)
    return tuple(normalized)


def _normalize_input_digests(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, (list, tuple)):
        return None
    out: list[str] = []
    for item in value:
        if type(item) is not str:
            return None
        out.append(item)
    return tuple(out)


def _normalize_attempt_index(value: Any) -> int | None:
    if type(value) is not int or value < 1:
        return None
    return value


def _request_fingerprint(
    request: Any,
    role_binding: Any,
    resolved_inputs: tuple[Mapping[str, Any], ...],
    *,
    input_artifact_digests: tuple[str, ...],
    attempt_index: int,
) -> str:
    safe_inputs = [{field: item.get(field) for field in _FINGERPRINT_FIELDS} for item in resolved_inputs]
    payload = {
        "run_id": str(getattr(request, "run_id", None)),
        "step_id": str(getattr(request, "step_id", None)),
        "attempt_index": attempt_index,
        "workflow_spec_digest": str(getattr(request, "workflow_spec_digest", None)),
        "role_binding_digest": str(getattr(request, "role_binding_digest", None)),
        "input_artifact_digests": list(input_artifact_digests),
        "idempotency_key": str(getattr(request, "idempotency_key", None)),
        "role_key": str(getattr(role_binding, "role_key", None)),
        "resolved_inputs": safe_inputs,
    }
    return _digest_hex(payload)


def _failure(code: str, *, retryable: bool = False, ambiguous: bool = False) -> StepExecutionOutcome:
    return StepExecutionOutcome(
        ok=False,
        step_status="cancel_ambiguous" if ambiguous else "failed_terminal",
        artifact_refs=(),
        error_code=code,
        retryable=retryable,
        ambiguous=ambiguous,
    )


class P5LocalOfflineRuntimeAdapter:
    """Deterministic fake StepExecutor with sanitized local control views."""

    def __init__(self, *, approval_token: str = "", enabled: bool = False) -> None:
        self.approval_token = approval_token
        self.enabled = enabled
        self.launch_count = 0
        self._records_by_idem: dict[str, _Record] = {}
        self._records_by_step: dict[tuple[str, str], _Record] = {}
        self._history: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    def execute(
        self,
        request: Any,
        *,
        role_binding: Any,
        resolved_inputs: tuple[Mapping[str, Any], ...],
    ) -> StepExecutionOutcome:
        """Execute one fake step through the existing StepExecutor Protocol."""

        with self._lock:
            if self.enabled is not True:
                self._record_event("execute_rejected", error_code="runtime_adapter_disabled")
                return _failure("runtime_adapter_disabled")
            if self.approval_token != P5_RUNTIME_ADAPTER_IMPLEMENTATION_APPROVAL_TOKEN:
                self._record_event("execute_rejected", error_code="runtime_adapter_approval_mismatch")
                return _failure("runtime_adapter_approval_mismatch")
            normalized_inputs = _normalize_resolved_inputs(resolved_inputs)
            input_digests = _normalize_input_digests(
                getattr(request, "input_artifact_digests", ())
            )
            attempt_index = _normalize_attempt_index(getattr(request, "attempt_index", None))
            if normalized_inputs is None or input_digests is None or attempt_index is None:
                self._record_event("execute_rejected", error_code="runtime_adapter_invalid_request")
                return _failure("runtime_adapter_invalid_request")
            request_probe = {
                "run_id": getattr(request, "run_id", None),
                "step_id": getattr(request, "step_id", None),
                "idempotency_key": getattr(request, "idempotency_key", None),
                "transaction_ref": getattr(request, "transaction_ref", None),
                "operation_ref": getattr(request, "operation_ref", None),
                "input_artifact_digests": list(input_digests),
                "role_key": getattr(role_binding, "role_key", None),
            }
            if _contains_unsafe_material(normalized_inputs) or _contains_unsafe_material(request_probe):
                self._record_event("execute_rejected", error_code="runtime_unsafe_material")
                return _failure("runtime_unsafe_material")

            idem = _safe_ref(str(getattr(request, "idempotency_key", "missing_idempotency_key")))
            run_id = _safe_ref(str(getattr(request, "run_id", "missing_run")))
            step_id = _safe_ref(str(getattr(request, "step_id", "missing_step")))
            fingerprint = _request_fingerprint(
                request,
                role_binding,
                normalized_inputs,
                input_artifact_digests=input_digests,
                attempt_index=attempt_index,
            )
            existing = self._records_by_idem.get(idem)
            if existing is not None:
                if existing.fingerprint != fingerprint:
                    self._record_event(
                        "execute_rejected",
                        run_id=run_id,
                        step_id=step_id,
                        error_code="runtime_adapter_idempotency_conflict",
                    )
                    return _failure("runtime_adapter_idempotency_conflict")
                self._record_event("execute_replayed", run_id=run_id, step_id=step_id)
                return existing.outcome

            self.launch_count += 1
            artifact = self._build_artifact_ref(
                request=request, role_binding=role_binding, attempt_index=attempt_index
            )
            outcome = StepExecutionOutcome(
                ok=True,
                step_status="completed",
                artifact_refs=(artifact,),
                evidence_ref=f"p5_evidence_{_digest_hex({'run_id': run_id, 'step_id': step_id})[:16]}",
                evidence_digest=_digest_ref(
                    {"run_id": run_id, "step_id": step_id, "fingerprint": fingerprint}
                ),
            )
            record = _Record(
                fingerprint=fingerprint,
                outcome=outcome,
                state="completed",
                snapshot_version=len(self._history) + 1,
            )
            self._records_by_idem[idem] = record
            self._records_by_step[(run_id, step_id)] = record
            self._record_event("execute_completed", run_id=run_id, step_id=step_id)
            return outcome

    def query(self, *, run_id: str, step_id: str) -> dict[str, Any]:
        """Return a stable sanitized snapshot without invoking the fake step."""

        with self._lock:
            key = (_safe_ref(run_id), _safe_ref(step_id))
            record = self._records_by_step.get(key)
            if record is None:
                return {
                    "type": _SNAPSHOT_TYPE,
                    "run_id": key[0],
                    "step_id": key[1],
                    "state": "not_found",
                    "snapshot_version": len(self._history),
                    "artifact_refs": [],
                    "error_code": "runtime_adapter_not_found",
                }
            return {
                "type": _SNAPSHOT_TYPE,
                "run_id": key[0],
                "step_id": key[1],
                "state": record.state,
                "snapshot_version": record.snapshot_version,
                "artifact_refs": [dict(item) for item in record.outcome.artifact_refs],
                "error_code": record.outcome.error_code,
            }

    def cancel(
        self,
        *,
        run_id: str,
        step_id: str,
        scope: str,
        idempotency_key: str,
        interrupt_outcome: StepExecutionOutcome | None = None,
    ) -> StepExecutionOutcome:
        """No-throw cancellation view; unconfirmed active-run remains WATCH."""

        del idempotency_key
        with self._lock:
            safe_run = _safe_ref(run_id)
            safe_step = _safe_ref(step_id)
            if scope != "active_run":
                self._record_event(
                    "cancel_rejected",
                    run_id=safe_run,
                    step_id=safe_step,
                    error_code="runtime_adapter_cancel_scope_unsupported",
                )
                return _failure("runtime_adapter_cancel_scope_unsupported")
            confirmed = (
                interrupt_outcome is not None
                and interrupt_outcome.interrupted is True
                and interrupt_outcome.cleanup_verified is True
            )
            if confirmed:
                self._record_event("cancel_confirmed", run_id=safe_run, step_id=safe_step)
                return StepExecutionOutcome(
                    ok=True,
                    step_status="cancelled",
                    artifact_refs=(),
                    interrupted=True,
                    cleanup_verified=True,
                )
            self._record_event(
                "cancel_watch",
                run_id=safe_run,
                step_id=safe_step,
                error_code="active_run_cancellation_watch",
            )
            return StepExecutionOutcome(
                ok=False,
                step_status="cancel_ambiguous",
                artifact_refs=(),
                error_code="active_run_cancellation_watch",
                interrupted=False,
                cleanup_verified=False,
                ambiguous=True,
            )

    def recover(self, *, run_id: str, step_id: str) -> dict[str, Any]:
        """Return the current sanitized snapshot; no replay is attempted."""

        return self.query(run_id=run_id, step_id=step_id)

    def close(self) -> dict[str, Any]:
        """Return a sanitized close marker without mutating external state."""

        with self._lock:
            self._record_event("closed")
            return {"type": _SNAPSHOT_TYPE, "state": "closed", "snapshot_version": len(self._history)}

    def history_projection(self) -> dict[str, Any]:
        """Return sanitized local history suitable for JSON persistence tests."""

        with self._lock:
            return {
                "type": _HISTORY_TYPE,
                "snapshot_version": len(self._history),
                "events": [dict(event) for event in self._history],
            }

    def serialized_history_bytes(self) -> bytes:
        """Return canonical sanitized history bytes."""

        return json.dumps(
            self.history_projection(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    def _build_artifact_ref(
        self, *, request: Any, role_binding: Any, attempt_index: int
    ) -> dict[str, Any]:
        run_id = _safe_ref(str(getattr(request, "run_id", "missing_run")))
        step_id = _safe_ref(str(getattr(request, "step_id", "missing_step")))
        kind = _safe_artifact_kind(step_id)
        body_digest_payload = {
            "run_id": run_id,
            "step_id": step_id,
            "attempt_index": attempt_index,
            "role_key": _safe_ref(str(getattr(role_binding, "role_key", "role"))),
            "kind": kind,
        }
        content_digest = _digest_ref(body_digest_payload)
        if _SHA256_DIGEST_RE.fullmatch(content_digest) is None:
            raise AssertionError("derived digest invariant failed")
        return {
            "artifact_id": _safe_ref(f"p5_artifact_{run_id}_{step_id}_{attempt_index}"),
            "producer_step_id": step_id,
            "content_digest": content_digest,
            "artifact_kind": kind,
            "byte_count": len(json.dumps(body_digest_payload, sort_keys=True).encode("utf-8")),
            "created_at_ref": "created_at_ref_p5_local_0001",
        }

    def _record_event(
        self,
        event: str,
        *,
        run_id: str | None = None,
        step_id: str | None = None,
        error_code: str | None = None,
    ) -> None:
        projection = {
            "event": _safe_ref(event),
            "sequence": len(self._history) + 1,
            "run_id": None if run_id is None else _safe_ref(run_id),
            "step_id": None if step_id is None else _safe_ref(step_id),
            "error_code": error_code,
        }
        if _contains_unsafe_material(projection):
            projection = {
                "event": "history_projection_rejected",
                "sequence": len(self._history) + 1,
                "run_id": None,
                "step_id": None,
                "error_code": "runtime_unsafe_material",
            }
        self._history.append(projection)


__all__ = [
    "P5_RUNTIME_ADAPTER_IMPLEMENTATION_APPROVAL_TOKEN",
    "P5LocalOfflineRuntimeAdapter",
]
