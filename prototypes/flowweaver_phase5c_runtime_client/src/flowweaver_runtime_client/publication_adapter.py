"""Safe local publication adapter for FlowWeaver shadow runtime summaries."""

from __future__ import annotations

from typing import Any

from flowweaver_runtime_client.contracts import (
    build_start_payload_from_safe_fields,
    delivery_ack_from_tool_update,
    validate_workflow_id,
)

_PUBLICATION_TYPE = "flowweaver.gateway.shadow_runtime_publication.v0"
_READY = "ready"
_OPERATION = "publish_shadow_runtime_publication"
_START_OPERATION = "start_transaction"
_ACK_OPERATION = "record_delivery_ack"
_ALLOWED_ACK_STATUSES = {"applied", "duplicate", "rejected"}
_ALLOWED_PUBLICATION_KEYS = {
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
_ALLOWED_RESULT_FIELDS = {
    "ok",
    "operation",
    "workflow_id",
    "transaction_id",
    "status",
    "runtime_call_counts",
    "ack_statuses",
    "error_code",
}
_INVALID = object()


async def publish_shadow_runtime_publication(publication: object, *, runtime_client: Any) -> dict[str, object]:
    """Publish a ready shadow summary through an already supplied runtime client."""

    try:
        safe_publication = _validate_publication(publication)
        workflow_id = validate_workflow_id(safe_publication["workflow_id"])
        transaction_id = validate_workflow_id(safe_publication["transaction_id"])
        if workflow_id != transaction_id:
            raise ValueError("invalid_publication")
        payload = _payload_from_start_request(safe_publication["start_request"], workflow_id=workflow_id)
        ack_updates = _ack_updates_from_bridge(safe_publication["ack_bridge"])
    except ValueError as exc:
        return _error_result(_validation_error_code(str(exc)))

    try:
        start_result = await runtime_client.start_transaction(payload, workflow_id=workflow_id)
        _validate_start_result(start_result, workflow_id=workflow_id, transaction_id=transaction_id)
        ack_statuses: list[str] = []
        for update in ack_updates:
            ack_result = await runtime_client.record_delivery_ack(workflow_id, update)
            ack_statuses.append(_ack_status_from_result(ack_result, workflow_id=workflow_id))
    except Exception:
        return _error_result("runtime_error")

    result: dict[str, object] = {
        "ok": True,
        "operation": _OPERATION,
        "workflow_id": workflow_id,
        "transaction_id": transaction_id,
        "status": "published",
        "runtime_call_counts": {"start_transaction": 1, "record_delivery_ack": len(ack_updates)},
        "ack_statuses": ack_statuses,
    }
    _assert_result_shape(result)
    return result


def _validate_publication(publication: object) -> dict[str, object]:
    safe = _plain_dict(publication, error="invalid_publication")
    if set(safe) != _ALLOWED_PUBLICATION_KEYS:
        raise ValueError("invalid_publication")
    if not (
        safe["type"] == _PUBLICATION_TYPE
        and safe["verdict"] == _READY
        and safe["reason"] == "ok"
        and safe["runtime_model_version"] == "flowweaver.runtime.v0"
        and safe["runtime_envelope_type"] == "flowweaver.gateway.runtime_ingress_envelope.v0"
        and safe["side_effects"] == []
    ):
        raise ValueError("invalid_publication")
    return safe


def _payload_from_start_request(start_request: object, *, workflow_id: str) -> object:
    try:
        request = _plain_dict(start_request, error="invalid_start_payload")
        if set(request) != {"operation", "workflow_id", "start_payload"}:
            raise ValueError("invalid_start_payload")
        request_workflow_id = validate_workflow_id(request["workflow_id"])
        if request["operation"] != _START_OPERATION or request_workflow_id != workflow_id:
            raise ValueError("invalid_start_payload")
        payload = build_start_payload_from_safe_fields(request["start_payload"])
        if payload.transaction_id != workflow_id:
            raise ValueError("invalid_start_payload")
        return payload
    except ValueError:
        raise ValueError("invalid_start_payload") from None


def _ack_updates_from_bridge(ack_bridge: object) -> list[object]:
    try:
        bridge = _plain_dict(ack_bridge, error="invalid_delivery_ack_update")
        if set(bridge) != {"status", "updates"} or bridge["status"] != _READY:
            raise ValueError("invalid_delivery_ack_update")
        updates = _plain_list(bridge["updates"], error="invalid_delivery_ack_update")
        if len(updates) > 20:
            raise ValueError("invalid_delivery_ack_update")
        return [delivery_ack_from_tool_update(update) for update in updates]
    except ValueError:
        raise ValueError("invalid_delivery_ack_update") from None


def _validate_start_result(result: object, *, workflow_id: str, transaction_id: str) -> None:
    safe = _plain_dict(result, error="runtime_error")
    if not (
        safe.get("ok") is True
        and safe.get("operation") == _START_OPERATION
        and safe.get("workflow_id") == workflow_id
        and safe.get("transaction_id") == transaction_id
        and safe.get("status") in {"started", "running", "published"}
    ):
        raise RuntimeError("runtime_error")


def _ack_status_from_result(result: object, *, workflow_id: str) -> str:
    safe = _plain_dict(result, error="runtime_error")
    status = safe.get("status")
    if not (
        safe.get("ok") is True
        and safe.get("operation") == _ACK_OPERATION
        and safe.get("workflow_id") == workflow_id
        and type(status) is str
        and status in _ALLOWED_ACK_STATUSES
    ):
        raise RuntimeError("runtime_error")
    return status


def _validation_error_code(error_code: str) -> str:
    if error_code in {"invalid_publication", "invalid_start_payload", "invalid_delivery_ack_update"}:
        return error_code
    return "invalid_publication"


def _error_result(error_code: str) -> dict[str, object]:
    result = {"ok": False, "operation": _OPERATION, "error_code": error_code}
    _assert_result_shape(result)
    return result


def _plain_dict(value: object, *, error: str) -> dict[str, object]:
    copied = _plain_copy(value)
    if type(copied) is not dict:
        raise ValueError(error)
    return copied


def _plain_list(value: object, *, error: str) -> list[object]:
    copied = _plain_copy(value)
    if type(copied) is not list:
        raise ValueError(error)
    return copied


def _plain_copy(value: object) -> object:
    if value is None or type(value) in {str, bool, int, float}:
        return value
    if type(value) is list:
        copied_list: list[object] = []
        for item in value:
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            copied_list.append(copied)
        return copied_list
    if type(value) is tuple:
        copied_tuple: list[object] = []
        for item in value:
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            copied_tuple.append(copied)
        return copied_tuple
    if type(value) is dict:
        copied_dict: dict[str, object] = {}
        for key, item in value.items():
            if type(key) is not str:
                return _INVALID
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            copied_dict[key] = copied
        return copied_dict
    return _INVALID


def _assert_result_shape(result: dict[str, object]) -> None:
    if not set(result) <= _ALLOWED_RESULT_FIELDS:
        raise RuntimeError("runtime_error")


__all__ = ["publish_shadow_runtime_publication"]
