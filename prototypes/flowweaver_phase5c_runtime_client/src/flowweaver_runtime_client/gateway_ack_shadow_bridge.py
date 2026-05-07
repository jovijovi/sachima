"""Prototype-only shadow bridge from Gateway-like ACKs to runtime control."""

from __future__ import annotations

from typing import Any

from flowweaver_runtime_client.contracts import (
    delivery_ack_from_tool_update,
    sanitize_snapshot,
    validate_workflow_id,
)

FLOWWEAVER_GATEWAY_ACK_SHADOW_BRIDGE_VERSION = "flowweaver.gateway_ack_shadow_bridge.v0"
SHADOW_ACK_ENVELOPE_TYPE = "flowweaver.gateway_ack_shadow.v0"
ALLOWED_SHADOW_ACK_STATUSES = ("sent", "failed", "acknowledged")

_BRIDGE_OPERATION = "gateway_ack_shadow_bridge"
_RUNTIME_OPERATION = "record_delivery_ack"
_QUERY_OPERATION = "query_transaction"
_RECONCILE_OPERATION = "reconcile_delivery_ack"
_ACK_EVENT_TYPE = "record_delivery_ack"
_REQUIRED_ACK_KEYS = {
    "type",
    "workflow_id",
    "delivery_key",
    "surface",
    "target_kind",
    "target_id",
    "status",
}
_ALLOWED_SURFACES = ("final_text", "rich_card", "media", "progress_card")
_ALLOWED_TARGET_KINDS = ("delivery",)
_RESULT_FIELDS = {
    "ok",
    "bridge_version",
    "operation",
    "runtime_operation",
    "workflow_id",
    "target_id",
    "status",
    "snapshot",
    "error_code",
}
_UPDATE_STATUSES = ("applied", "duplicate", "rejected")
_BRIDGE_ERROR_CODES = {
    "unsafe_ack_envelope",
    "snapshot_unavailable",
    "workflow_id_mismatch",
    "delivery_target_mismatch",
    "runtime_reconciliation_failed",
    "runtime_error",
}
_UNSAFE_KEY_SUBSTRINGS = (
    "raw_",
    "tool_output",
    "platform_payload",
    "platform_id",
    "chat_id",
    "user_id",
    "message_id",
    "card_json",
    "media_path",
    "delivery_ack_payload",
    "credential",
    "password",
    "api_key",
    "bearer",
    "connection_string",
)
_UNSAFE_EXACT_KEYS = {"token", "secret"}
_UNSAFE_VALUE_MARKERS = (
    "unsafe-" + "token",
    "sk" + "-",
    "bearer ",
    "password" + "=",
    "secret" + "=",
    "api" + "_key=",
)
_PRIVATE_PREFIXES = (
    "om_",
    "oc_",
    "ou_",
    "chat_",
    "message_",
    "platform_",
    "feishu_",
    "lark_",
    "telegram_",
)
_SYNTHETIC_ID_FORBIDDEN_SUBSTRINGS = (
    "allowed_runtime_events",
    "claim_check_policy",
    "forbidden_material",
    "raw_",
    "tool_output",
    "platform_payload",
    "token",
    "secret",
    "password",
    "credential",
    "api_key",
    "bearer",
    "sk" + "-",
)


async def reconcile_shadow_gateway_ack(control_surface: Any, ack_envelope: object) -> dict[str, object]:
    """Preflight a sanitized shadow ACK and reconcile it through Phase 5K control."""

    try:
        ack = _prepare_ack_envelope(ack_envelope)
    except ValueError:
        return _bridge_error_result(error_code="unsafe_ack_envelope")

    try:
        snapshot = await _query_safe_snapshot(control_surface, ack["workflow_id"])
    except RuntimeError:
        return _bridge_error_result(
            error_code="runtime_error",
            workflow_id=ack["workflow_id"],
            target_id=ack["target_id"],
            runtime_operation=_RUNTIME_OPERATION,
        )
    except ValueError as exc:
        return _bridge_error_result(
            error_code=str(exc),
            workflow_id=ack["workflow_id"],
            target_id=ack["target_id"],
            runtime_operation=_RUNTIME_OPERATION,
        )

    delivery_statuses = snapshot["delivery_statuses"]
    if type(delivery_statuses) is not dict or ack["target_id"] not in delivery_statuses:
        return _bridge_error_result(
            error_code="delivery_target_mismatch",
            workflow_id=ack["workflow_id"],
            target_id=ack["target_id"],
            runtime_operation=_RUNTIME_OPERATION,
        )

    update = {
        "event_type": _ACK_EVENT_TYPE,
        "delivery_key": ack["delivery_key"],
        "surface": ack["surface"],
        "target_kind": ack["target_kind"],
        "target_id": ack["target_id"],
        "status": ack["status"],
    }
    try:
        delivery_ack_from_tool_update(update)
        runtime_result = await control_surface.handle(
            {
                "operation": _RECONCILE_OPERATION,
                "workflow_id": ack["workflow_id"],
                "update": update,
            }
        )
        return _bridge_success_result(
            runtime_result,
            workflow_id=ack["workflow_id"],
            target_id=ack["target_id"],
        )
    except ValueError:
        return _bridge_error_result(
            error_code="runtime_reconciliation_failed",
            workflow_id=ack["workflow_id"],
            target_id=ack["target_id"],
            runtime_operation=_RUNTIME_OPERATION,
        )
    except Exception:
        return _bridge_error_result(
            error_code="runtime_error",
            workflow_id=ack["workflow_id"],
            target_id=ack["target_id"],
            runtime_operation=_RUNTIME_OPERATION,
        )


def _prepare_ack_envelope(ack_envelope: object) -> dict[str, str]:
    ack = _plain_string_dict(ack_envelope)
    _reject_unsafe_material(ack)
    if set(ack) != _REQUIRED_ACK_KEYS:
        _raise()
    if ack["type"] != SHADOW_ACK_ENVELOPE_TYPE:
        _raise()
    safe = {
        "workflow_id": _safe_workflow_id(ack["workflow_id"]),
        "delivery_key": _synthetic_id(ack["delivery_key"], prefixes=("runtime_event_",)),
        "surface": _closed_string(ack["surface"], _ALLOWED_SURFACES),
        "target_kind": _closed_string(ack["target_kind"], _ALLOWED_TARGET_KINDS),
        "target_id": _synthetic_id(ack["target_id"], prefixes=("runtime_delivery_",)),
        "status": _closed_string(ack["status"], ALLOWED_SHADOW_ACK_STATUSES),
    }
    delivery_ack_from_tool_update(
        {
            "event_type": _ACK_EVENT_TYPE,
            "delivery_key": safe["delivery_key"],
            "surface": safe["surface"],
            "target_kind": safe["target_kind"],
            "target_id": safe["target_id"],
            "status": safe["status"],
        }
    )
    return safe


async def _query_safe_snapshot(control_surface: Any, workflow_id: str) -> dict[str, object]:
    try:
        result = await control_surface.handle({"operation": _QUERY_OPERATION, "workflow_id": workflow_id})
    except Exception as exc:
        raise RuntimeError("runtime_error") from exc
    if type(result) is not dict or result.get("ok") is not True:
        raise ValueError("snapshot_unavailable")
    if "workflow_id" in result and result["workflow_id"] != workflow_id:
        raise ValueError("workflow_id_mismatch")
    try:
        snapshot = sanitize_snapshot(result.get("snapshot"))
    except ValueError as exc:
        raise ValueError("snapshot_unavailable") from exc
    if snapshot["transaction_id"] != workflow_id:
        raise ValueError("workflow_id_mismatch")
    return snapshot


def _bridge_success_result(runtime_result: object, *, workflow_id: str, target_id: str) -> dict[str, object]:
    if type(runtime_result) is not dict or runtime_result.get("ok") is not True:
        return _bridge_error_result(
            error_code="runtime_reconciliation_failed",
            workflow_id=workflow_id,
            target_id=target_id,
            runtime_operation=_RUNTIME_OPERATION,
        )
    if "workflow_id" in runtime_result and runtime_result["workflow_id"] != workflow_id:
        return _bridge_error_result(
            error_code="workflow_id_mismatch",
            workflow_id=workflow_id,
            target_id=target_id,
            runtime_operation=_RUNTIME_OPERATION,
        )
    status = _runtime_update_status(runtime_result.get("status"))
    if status is None:
        return _bridge_error_result(
            error_code="runtime_reconciliation_failed",
            workflow_id=workflow_id,
            target_id=target_id,
            runtime_operation=_RUNTIME_OPERATION,
        )
    try:
        snapshot = sanitize_snapshot(runtime_result.get("snapshot"))
    except ValueError:
        return _bridge_error_result(
            error_code="runtime_reconciliation_failed",
            workflow_id=workflow_id,
            target_id=target_id,
            runtime_operation=_RUNTIME_OPERATION,
        )
    if snapshot["transaction_id"] != workflow_id:
        return _bridge_error_result(
            error_code="workflow_id_mismatch",
            workflow_id=workflow_id,
            target_id=target_id,
            runtime_operation=_RUNTIME_OPERATION,
        )
    result: dict[str, object] = {
        "ok": True,
        "bridge_version": FLOWWEAVER_GATEWAY_ACK_SHADOW_BRIDGE_VERSION,
        "operation": _BRIDGE_OPERATION,
        "runtime_operation": _RUNTIME_OPERATION,
        "workflow_id": workflow_id,
        "target_id": target_id,
        "status": status,
        "snapshot": snapshot,
    }
    _assert_bridge_result(result)
    return result


def _bridge_error_result(
    *,
    error_code: object,
    workflow_id: str | None = None,
    target_id: str | None = None,
    runtime_operation: str | None = None,
) -> dict[str, object]:
    safe_error_code = error_code if type(error_code) is str and error_code in _BRIDGE_ERROR_CODES else "runtime_error"
    result: dict[str, object] = {
        "ok": False,
        "bridge_version": FLOWWEAVER_GATEWAY_ACK_SHADOW_BRIDGE_VERSION,
        "operation": _BRIDGE_OPERATION,
        "error_code": safe_error_code,
    }
    if runtime_operation is not None:
        result["runtime_operation"] = runtime_operation
    if workflow_id is not None:
        result["workflow_id"] = workflow_id
    if target_id is not None:
        result["target_id"] = target_id
    _assert_bridge_result(result)
    return result


def _plain_string_dict(value: object) -> dict[str, str]:
    if type(value) is not dict:
        _raise()
    result: dict[str, str] = {}
    for key, item in value.items():
        if type(key) is not str or type(item) is not str:
            _raise()
        result[key] = item
    return result


def _safe_workflow_id(value: object) -> str:
    try:
        return validate_workflow_id(value)
    except ValueError:
        _raise()


def _synthetic_id(value: object, *, prefixes: tuple[str, ...]) -> str:
    if type(value) is not str or not value or len(value) > 128:
        _raise()
    if not value.startswith(prefixes):
        _raise()
    lowered = value.lower()
    body_prefix = next((prefix for prefix in prefixes if lowered.startswith(prefix)), "")
    body = lowered[len(body_prefix) :]
    if any(lowered.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
        _raise()
    if any(
        marker in body
        for marker in ("om_", "oc_", "ou_", "chat", "message", "platform", "feishu", "lark", "telegram", "private")
    ):
        _raise()
    if any(marker in lowered for marker in _SYNTHETIC_ID_FORBIDDEN_SUBSTRINGS):
        _raise()
    if not all(("a" <= char <= "z") or ("0" <= char <= "9") or char == "_" for char in value):
        _raise()
    return value


def _closed_string(value: object, allowed: tuple[str, ...]) -> str:
    if type(value) is not str or value not in allowed:
        _raise()
    return value


def _runtime_update_status(value: object) -> str | None:
    if type(value) is str and value in _UPDATE_STATUSES:
        return value
    return None


def _reject_unsafe_material(value: object) -> None:
    if type(value) is dict:
        for key, item in value.items():
            lowered = key.lower()
            if lowered in _UNSAFE_EXACT_KEYS or any(marker in lowered for marker in _UNSAFE_KEY_SUBSTRINGS):
                _raise()
            _reject_unsafe_material(item)
        return
    if type(value) is list:
        for item in value:
            _reject_unsafe_material(item)
        return
    if type(value) is str:
        lowered = value.lower()
        if any(lowered.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
            _raise()
        if any(marker in lowered for marker in _UNSAFE_VALUE_MARKERS):
            _raise()


def _assert_bridge_result(result: dict[str, object]) -> None:
    if not set(result) <= _RESULT_FIELDS:
        raise RuntimeError("unsafe bridge result")
    rendered = repr(result).lower()
    forbidden = (
        "allowed_runtime_events",
        "claim_check_policy",
        "forbidden_material",
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
        "card_json",
        "media_path",
        "delivery_ack_payload",
        "oc_private",
        "ou_private",
        "om_private",
        "unsafe-" + "token",
        "sk" + "-",
        "bearer ",
    )
    if any(marker in rendered for marker in forbidden):
        raise RuntimeError("unsafe bridge result")


def _raise() -> None:
    raise ValueError("unsafe_ack_envelope") from None


__all__ = [
    "ALLOWED_SHADOW_ACK_STATUSES",
    "FLOWWEAVER_GATEWAY_ACK_SHADOW_BRIDGE_VERSION",
    "SHADOW_ACK_ENVELOPE_TYPE",
    "reconcile_shadow_gateway_ack",
]
