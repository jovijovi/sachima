"""Prototype-only in-memory FlowWeaver runtime reconciliation harness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flowweaver_runtime_client.contracts import (
    make_error_result,
    make_success_result,
    make_update_success_result,
    sanitize_snapshot,
    validate_workflow_id,
)
from flowweaver_runtime_client.publication_adapter import publish_shadow_runtime_publication
from flowweaver_temporal_poc import FLOWWEAVER_TEMPORAL_POC_VERSION
from flowweaver_temporal_poc.payloads import (
    DeliveryAckUpdate,
    RuntimeStartPayload,
    validate_delivery_ack_update,
    validate_start_payload,
)

_SNAPSHOT_TYPE = "flowweaver.temporal_poc.snapshot.v0"
_UPDATE_RESULT_TYPE = "flowweaver.temporal_poc.update_result.v0"
_OPERATION = "reconcile_shadow_runtime_publication"
_PUBLISH_OPERATION = "publish_shadow_runtime_publication"
_QUERY_OPERATION = "query_snapshot"
_ACK_OPERATION = "record_delivery_ack"
_START_OPERATION = "start_transaction"
_ALLOWED_ERROR_CODES = {
    "invalid_publication",
    "invalid_start_payload",
    "invalid_delivery_ack_update",
    "unsafe_snapshot",
    "reconciliation_mismatch",
    "runtime_error",
}
_ALLOWED_RESULT_FIELDS = {
    "ok",
    "operation",
    "workflow_id",
    "transaction_id",
    "status",
    "publication_status",
    "snapshot_status",
    "checks",
    "reconciliation",
    "side_effects",
    "error_code",
}
_INVALID = object()


@dataclass
class _RuntimeState:
    payload_signature: dict[str, object]
    snapshot: dict[str, object]
    event_fingerprints: dict[str, tuple[str, ...]]


class InMemoryFlowWeaverRuntimeClient:
    """Small in-memory runtime facade for local reconciliation tests only."""

    def __init__(self) -> None:
        self._states: dict[str, _RuntimeState] = {}

    async def start_transaction(self, payload: object, *, workflow_id: str) -> dict[str, object]:
        try:
            validate_start_payload(payload)
            safe_workflow_id = validate_workflow_id(workflow_id)
            if type(payload) is not RuntimeStartPayload or payload.transaction_id != safe_workflow_id:
                return make_error_result(operation=_START_OPERATION, error_code="invalid_start_payload")
            signature = _payload_signature(payload)
            existing = self._states.get(safe_workflow_id)
            if existing is not None:
                if existing.payload_signature != signature:
                    return make_error_result(operation=_START_OPERATION, error_code="invalid_start_payload")
                return make_success_result(
                    operation=_START_OPERATION,
                    workflow_id=safe_workflow_id,
                    transaction_id=payload.transaction_id,
                    status="started",
                )
            self._states[safe_workflow_id] = _RuntimeState(
                payload_signature=signature,
                snapshot=_snapshot_from_payload(payload),
                event_fingerprints={},
            )
            return make_success_result(
                operation=_START_OPERATION,
                workflow_id=safe_workflow_id,
                transaction_id=payload.transaction_id,
                status="started",
            )
        except ValueError:
            return make_error_result(operation=_START_OPERATION, error_code="invalid_start_payload")

    async def record_delivery_ack(self, workflow_id: str, update: object) -> dict[str, object]:
        try:
            safe_workflow_id = validate_workflow_id(workflow_id)
            validate_delivery_ack_update(update)
            if type(update) is not DeliveryAckUpdate:
                return make_error_result(operation=_ACK_OPERATION, error_code="invalid_delivery_ack_update")
            state = self._states.get(safe_workflow_id)
            if state is None:
                return make_error_result(operation=_ACK_OPERATION, error_code="runtime_error")
            update_status = _apply_delivery_ack(state, update)
            return make_update_success_result(
                operation=_ACK_OPERATION,
                workflow_id=safe_workflow_id,
                update_result=_update_result(state.snapshot, update_status=update_status),
            )
        except ValueError:
            return make_error_result(operation=_ACK_OPERATION, error_code="invalid_delivery_ack_update")

    async def query_snapshot(self, workflow_id: str) -> dict[str, object]:
        try:
            safe_workflow_id = validate_workflow_id(workflow_id)
            state = self._states.get(safe_workflow_id)
            if state is None:
                return make_error_result(operation=_QUERY_OPERATION, error_code="runtime_error")
            return make_success_result(operation=_QUERY_OPERATION, workflow_id=safe_workflow_id, snapshot=state.snapshot)
        except ValueError:
            return make_error_result(operation=_QUERY_OPERATION, error_code="runtime_error")


async def reconcile_shadow_runtime_publication(publication: object, *, runtime_client: Any) -> dict[str, object]:
    """Publish, query, and safely reconcile one shadow runtime publication."""

    try:
        safe_publication = _safe_publication_summary(publication)
        workflow_id = validate_workflow_id(safe_publication.get("workflow_id"))
        transaction_id = validate_workflow_id(safe_publication.get("transaction_id"))
        if workflow_id != transaction_id:
            return _error_result("invalid_publication")
        start_payload = _start_payload_fields(safe_publication)
        _validate_publication_identity(safe_publication, workflow_id=workflow_id, start_payload=start_payload)
        ack_updates = _ack_updates(safe_publication)
    except ValueError:
        return _error_result("invalid_publication")

    try:
        publish_result = await publish_shadow_runtime_publication(safe_publication, runtime_client=runtime_client)
    except Exception:
        return _error_result("runtime_error")

    safe_publish_result = _plain_dict(publish_result)
    if safe_publish_result is None:
        return _error_result("runtime_error")
    if safe_publish_result.get("ok") is not True:
        return _error_result(_publication_error_code(safe_publish_result.get("error_code")))

    try:
        if validate_workflow_id(safe_publish_result.get("workflow_id")) != workflow_id:
            return _error_result("reconciliation_mismatch")
        if validate_workflow_id(safe_publish_result.get("transaction_id")) != transaction_id:
            return _error_result("reconciliation_mismatch")
        ack_statuses = _plain_string_list(safe_publish_result.get("ack_statuses"))
        if ack_statuses is None:
            return _error_result("runtime_error")
    except ValueError:
        return _error_result("runtime_error")

    try:
        query_result = await runtime_client.query_snapshot(workflow_id)
    except Exception:
        return _error_result("runtime_error")

    try:
        snapshot = _snapshot_from_query_result(query_result, workflow_id=workflow_id)
    except ValueError:
        return _error_result("unsafe_snapshot")

    checks = _reconciliation_checks(
        workflow_id=workflow_id,
        transaction_id=transaction_id,
        start_payload=start_payload,
        ack_updates=ack_updates,
        ack_statuses=ack_statuses,
        safe_publication=safe_publication,
        snapshot=snapshot,
    )
    if not all(checks.values()):
        return _error_result("reconciliation_mismatch")

    result: dict[str, object] = {
        "ok": True,
        "operation": _OPERATION,
        "workflow_id": workflow_id,
        "transaction_id": transaction_id,
        "status": "reconciled",
        "publication_status": safe_publish_result["status"],
        "snapshot_status": snapshot["status"],
        "checks": checks,
        "reconciliation": {
            "entry_count": snapshot["entry_count"],
            "record_counts": snapshot["record_counts"],
            "ack_statuses": ack_statuses,
            "applied_event_count": snapshot["applied_event_count"],
        },
        "side_effects": [],
    }
    _assert_result_shape(result)
    return result


def _apply_delivery_ack(state: _RuntimeState, update: DeliveryAckUpdate) -> str:
    delivery_statuses = _plain_dict(state.snapshot.get("delivery_statuses")) or {}
    if update.target_id not in delivery_statuses:
        return "rejected"
    fingerprint = _delivery_ack_fingerprint(update)
    existing = state.event_fingerprints.get(update.delivery_key)
    if existing == fingerprint:
        return "duplicate"
    if existing is not None:
        return "rejected"
    state.event_fingerprints[update.delivery_key] = fingerprint
    delivery_statuses[update.target_id] = update.status
    state.snapshot["delivery_statuses"] = dict(sorted(delivery_statuses.items()))
    state.snapshot["applied_event_count"] = len(state.event_fingerprints)
    return "applied"


def _snapshot_from_payload(payload: RuntimeStartPayload) -> dict[str, object]:
    entry_count = payload.entry_count
    delivery_count = payload.record_counts["deliveries"]
    return {
        "type": _SNAPSHOT_TYPE,
        "version": FLOWWEAVER_TEMPORAL_POC_VERSION,
        "transaction_id": payload.transaction_id,
        "status": "running",
        "entry_count": entry_count,
        "record_counts": dict(payload.record_counts),
        "counts": {
            "intents": entry_count,
            "artifacts": entry_count,
            "deliveries": delivery_count,
        },
        "intent_statuses": {f"runtime_intent_{index}": "pending" for index in range(entry_count)},
        "artifact_statuses": {f"runtime_artifact_{index}": "available" for index in range(entry_count)},
        "delivery_statuses": {f"runtime_delivery_{index}": "planned" for index in range(delivery_count)},
        "applied_event_count": 0,
        "resume_count": 0,
        "side_effects": [],
    }


def _update_result(snapshot: dict[str, object], *, update_status: str) -> dict[str, object]:
    return {
        "type": _UPDATE_RESULT_TYPE,
        "version": FLOWWEAVER_TEMPORAL_POC_VERSION,
        "update_status": update_status,
        "snapshot": snapshot,
        "side_effects": [],
    }


def _payload_signature(payload: RuntimeStartPayload) -> dict[str, object]:
    return {
        "transaction_id": payload.transaction_id,
        "idempotency_key": payload.idempotency_key,
        "entry_count": payload.entry_count,
        "record_counts": dict(payload.record_counts),
        "allowed_runtime_events": tuple(payload.allowed_runtime_events),
        "claim_check_policy": _plain_copy(payload.claim_check_policy),
    }


def _delivery_ack_fingerprint(update: DeliveryAckUpdate) -> tuple[str, ...]:
    return (
        _ACK_OPERATION,
        update.delivery_key,
        update.surface,
        update.target_kind,
        update.target_id,
        update.status,
    )


def _safe_publication_summary(publication: object) -> dict[str, object]:
    safe = _plain_dict(publication)
    expected = {
        "type",
        "verdict",
        "reason",
        "runtime_model_version",
        "runtime_envelope_type",
        "transaction_id",
        "workflow_id",
        "runtime_identity",
        "start_request",
        "ack_bridge",
        "checks",
        "side_effects",
    }
    if safe is None or set(safe) != expected:
        raise ValueError("invalid_publication")
    if not (
        safe["type"] == "flowweaver.gateway.shadow_runtime_publication.v0"
        and safe["verdict"] == "ready"
        and safe["reason"] == "ok"
        and safe["runtime_model_version"] == "flowweaver.runtime.v0"
        and safe["runtime_envelope_type"] == "flowweaver.gateway.runtime_ingress_envelope.v0"
        and safe["side_effects"] == []
    ):
        raise ValueError("invalid_publication")
    return safe


def _start_payload_fields(publication: dict[str, object]) -> dict[str, object]:
    start_request = _plain_dict(publication.get("start_request"))
    if start_request is None:
        raise ValueError("invalid_publication")
    start_payload = _plain_dict(start_request.get("start_payload"))
    if start_payload is None:
        raise ValueError("invalid_publication")
    return start_payload


def _ack_updates(publication: dict[str, object]) -> list[dict[str, object]]:
    ack_bridge = _plain_dict(publication.get("ack_bridge"))
    if ack_bridge is None:
        raise ValueError("invalid_publication")
    updates = _plain_list(ack_bridge.get("updates"))
    if updates is None or not all(type(item) is dict for item in updates):
        raise ValueError("invalid_publication")
    return [item for item in updates if type(item) is dict]


def _validate_publication_identity(
    publication: dict[str, object],
    *,
    workflow_id: str,
    start_payload: dict[str, object],
) -> None:
    identity = _plain_dict(publication.get("runtime_identity"))
    if identity is None or set(identity) != {"type", "strategy", "transaction_id", "workflow_id", "idempotency_key"}:
        raise ValueError("invalid_publication")
    if identity["type"] != "flowweaver.gateway.runtime_identity.v0" or identity["strategy"] != "shadow_ref_hash_v0":
        raise ValueError("invalid_publication")
    if validate_workflow_id(identity.get("transaction_id")) != workflow_id:
        raise ValueError("invalid_publication")
    if validate_workflow_id(identity.get("workflow_id")) != workflow_id:
        raise ValueError("invalid_publication")
    if start_payload.get("transaction_id") != workflow_id:
        raise ValueError("invalid_publication")
    idempotency_key = _safe_runtime_event_id(identity.get("idempotency_key"))
    if idempotency_key != _safe_runtime_event_id(start_payload.get("idempotency_key")):
        raise ValueError("invalid_publication")
    try:
        _assert_no_forbidden_rendered_material(identity)
    except RuntimeError:
        raise ValueError("invalid_publication") from None


def _safe_runtime_event_id(value: object) -> str:
    if type(value) is not str or not value.startswith("runtime_event_") or len(value) > 128:
        raise ValueError("invalid_publication")
    lowered = value.lower()
    body = lowered[len("runtime_event_") :]
    forbidden = (
        "om_",
        "oc_",
        "ou_",
        "chat",
        "message",
        "platform",
        "feishu",
        "lark",
        "telegram",
        "private",
        "raw_",
        "token",
        "secret",
        "password",
        "credential",
        "api_key",
        "bearer",
        "sk-",
    )
    if any(marker in body for marker in forbidden) or not all(
        ("a" <= char <= "z") or ("0" <= char <= "9") or char == "_" for char in value
    ):
        raise ValueError("invalid_publication")
    return value


def _snapshot_from_query_result(query_result: object, *, workflow_id: str) -> dict[str, object]:
    result = _plain_dict(query_result)
    if result is None or result.get("ok") is not True or result.get("operation") != _QUERY_OPERATION:
        raise ValueError("unsafe_snapshot")
    if validate_workflow_id(result.get("workflow_id")) != workflow_id:
        raise ValueError("unsafe_snapshot")
    snapshot = sanitize_snapshot(result.get("snapshot"))
    _assert_no_forbidden_rendered_material(snapshot)
    return snapshot


def _reconciliation_checks(
    *,
    workflow_id: str,
    transaction_id: str,
    start_payload: dict[str, object],
    ack_updates: list[dict[str, object]],
    ack_statuses: list[str],
    safe_publication: dict[str, object],
    snapshot: dict[str, object],
) -> dict[str, bool]:
    delivery_statuses = _plain_dict(snapshot.get("delivery_statuses")) or {}
    return {
        "runtime_ids_match": snapshot.get("transaction_id") == workflow_id == transaction_id,
        "entry_count_matches": snapshot.get("entry_count") == start_payload.get("entry_count"),
        "record_counts_match": _record_counts_and_status_maps_match(start_payload=start_payload, snapshot=snapshot),
        "delivery_ack_count_matches": _delivery_ack_count_matches(
            ack_updates=ack_updates,
            ack_statuses=ack_statuses,
            snapshot=snapshot,
        ),
        "delivery_statuses_match": _delivery_statuses_match(
            ack_updates=ack_updates,
            ack_statuses=ack_statuses,
            delivery_statuses=delivery_statuses,
        ),
        "side_effects_absent": safe_publication.get("side_effects") == [] and snapshot.get("side_effects") == [],
    }


def _record_counts_and_status_maps_match(*, start_payload: dict[str, object], snapshot: dict[str, object]) -> bool:
    entry_count = start_payload.get("entry_count")
    expected_record_counts = _plain_dict(start_payload.get("record_counts")) or {}
    delivery_count = expected_record_counts.get("deliveries")
    if type(entry_count) is not int or type(delivery_count) is not int:
        return False
    expected_counts = {
        "intents": expected_record_counts.get("intents"),
        "artifacts": expected_record_counts.get("artifacts"),
        "deliveries": delivery_count,
    }
    if snapshot.get("record_counts") != expected_record_counts or snapshot.get("counts") != expected_counts:
        return False
    expected_intent_keys = {f"runtime_intent_{index}" for index in range(entry_count)}
    expected_artifact_keys = {f"runtime_artifact_{index}" for index in range(entry_count)}
    expected_delivery_keys = {f"runtime_delivery_{index}" for index in range(delivery_count)}
    intent_statuses = _plain_dict(snapshot.get("intent_statuses")) or {}
    artifact_statuses = _plain_dict(snapshot.get("artifact_statuses")) or {}
    delivery_statuses = _plain_dict(snapshot.get("delivery_statuses")) or {}
    return (
        set(intent_statuses) == expected_intent_keys
        and set(artifact_statuses) == expected_artifact_keys
        and set(delivery_statuses) == expected_delivery_keys
    )


def _delivery_ack_count_matches(*, ack_updates: list[dict[str, object]], ack_statuses: list[str], snapshot: dict[str, object]) -> bool:
    record_counts = _plain_dict(snapshot.get("record_counts")) or {}
    delivery_count = record_counts.get("deliveries")
    return (
        type(delivery_count) is int
        and len(ack_statuses) == len(ack_updates)
        and len(ack_updates) <= delivery_count
        and all(status in {"applied", "duplicate"} for status in ack_statuses)
    )


def _delivery_statuses_match(
    *,
    ack_updates: list[dict[str, object]],
    ack_statuses: list[str],
    delivery_statuses: dict[str, object],
) -> bool:
    if len(ack_updates) != len(ack_statuses):
        return False
    for update, ack_status in zip(ack_updates, ack_statuses, strict=True):
        if ack_status not in {"applied", "duplicate"}:
            return False
        target_id = update.get("target_id")
        expected_status = update.get("status")
        if type(target_id) is not str or type(expected_status) is not str:
            return False
        if delivery_statuses.get(target_id) != expected_status:
            return False
    return True


def _publication_error_code(error_code: object) -> str:
    if error_code in {"invalid_publication", "invalid_start_payload", "invalid_delivery_ack_update", "runtime_error"}:
        return str(error_code)
    return "runtime_error"


def _error_result(error_code: object) -> dict[str, object]:
    safe_code = error_code if type(error_code) is str and error_code in _ALLOWED_ERROR_CODES else "runtime_error"
    result = {"ok": False, "operation": _OPERATION, "error_code": safe_code}
    _assert_result_shape(result)
    return result


def _plain_string_list(value: object) -> list[str] | None:
    copied = _plain_copy(value)
    if type(copied) is not list or not all(type(item) is str for item in copied):
        return None
    return copied


def _plain_dict(value: object) -> dict[str, object] | None:
    copied = _plain_copy(value)
    if type(copied) is not dict:
        return None
    return copied


def _plain_list(value: object) -> list[object] | None:
    copied = _plain_copy(value)
    if type(copied) is not list:
        return None
    return copied


def _plain_copy(value: object) -> object:
    if value is None or type(value) in {str, bool, int, float}:
        return value
    if type(value) is tuple:
        result: list[object] = []
        for item in value:
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            result.append(copied)
        return tuple(result)
    if type(value) is list:
        result = []
        for item in value:
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            result.append(copied)
        return result
    if type(value) is dict:
        result: dict[str, object] = {}
        for key, item in value.items():
            if type(key) is not str:
                return _INVALID
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            result[key] = copied
        return result
    return _INVALID


def _assert_result_shape(result: dict[str, object]) -> None:
    if not set(result) <= _ALLOWED_RESULT_FIELDS:
        raise RuntimeError("runtime_error")
    _assert_no_forbidden_rendered_material(result)


def _assert_no_forbidden_rendered_material(value: object) -> None:
    rendered = repr(value).lower()
    forbidden = (
        "raw_payload",
        "raw_capture",
        "raw_prompt",
        "raw_command",
        "tool_output",
        "platform_payload",
        "platform_id",
        "chat_id",
        "user_id",
        "message_id",
        "delivery_ack_payload",
        "om_private",
        "oc_private",
        "ou_private",
        "unsafe-token",
        "sk-",
        "bearer ",
        "password" + "=",
        "secret" + "=",
        "credential" + "=",
        "api" + "_key=",
    )
    if any(marker in rendered for marker in forbidden):
        raise RuntimeError("runtime_error")


__all__ = ["InMemoryFlowWeaverRuntimeClient", "reconcile_shadow_runtime_publication"]
