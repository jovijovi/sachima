"""Prototype-only default-off Gateway shadow E2E loop harness."""

from __future__ import annotations

import asyncio
from typing import Any

from flowweaver_runtime_client.contracts import (
    build_start_payload_from_safe_fields,
    sanitize_snapshot,
    validate_workflow_id,
)
from flowweaver_runtime_client.gateway_ack_shadow_bridge import (
    ALLOWED_SHADOW_ACK_STATUSES,
    SHADOW_ACK_ENVELOPE_TYPE,
    reconcile_shadow_gateway_ack,
)

FLOWWEAVER_GATEWAY_SHADOW_E2E_LOOP_VERSION = "flowweaver.gateway_shadow_e2e_loop.v0"
SHADOW_PUBLICATION_ENVELOPE_TYPE = "flowweaver.gateway_shadow_publication.v0"

_OPERATION = "gateway_shadow_e2e_loop"
_READY_PUBLICATION_TYPE = "flowweaver.gateway.shadow_runtime_publication.v0"
_READY = "ready"
_START_OPERATION = "start_transaction"
_QUERY_OPERATION = "query_transaction"
_ACK_OPERATION = "record_delivery_ack"
_ALLOWED_SURFACES = ("final_text", "rich_card", "progress_card", "media")
_PUBLICATION_KEYS = {
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
_START_REQUEST_KEYS = {"operation", "workflow_id", "start_payload"}
_RUNTIME_IDENTITY_KEYS = {"type", "strategy", "transaction_id", "workflow_id", "idempotency_key"}
_CHECK_KEYS = {
    "shadow_capture_present",
    "dry_run_summary_valid",
    "runtime_envelope_valid",
    "start_request_safe",
    "delivery_ack_updates_safe",
    "payloads_absent",
    "visible_side_effects_absent",
    "runtime_side_effects_absent",
}
_ACK_BRIDGE_KEYS = {"status", "updates"}
_ACK_UPDATE_KEYS = {"event_type", "delivery_key", "surface", "target_kind", "target_id", "status"}
_RESULT_FIELDS = {
    "ok",
    "loop_version",
    "operation",
    "workflow_id",
    "transaction_id",
    "start_status",
    "publication",
    "ack_results",
    "final_snapshot",
    "checks",
    "side_effects",
    "error_code",
}
_ERROR_CODES = {
    "invalid_publication",
    "invalid_start_payload",
    "invalid_delivery_plan",
    "start_failed",
    "snapshot_unavailable",
    "workflow_id_mismatch",
    "delivery_target_mismatch",
    "ack_reconciliation_failed",
    "runtime_error",
    "unsafe_output",
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
_PRIVATE_PREFIXES = ("om_", "oc_", "ou_", "chat_", "message_", "platform_", "feishu_", "lark_", "telegram_")
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
_INVALID = object()


async def run_shadow_gateway_e2e_loop(control_surface: Any, publication: object) -> dict[str, object]:
    """Run the prototype-only shadow Gateway publication-to-ACK loop."""

    try:
        safe_publication = _validate_ready_publication(publication)
    except ValueError as exc:
        return _error_result(str(exc))

    workflow_id = safe_publication["workflow_id"]
    transaction_id = safe_publication["transaction_id"]
    try:
        start_result = await control_surface.handle(safe_publication["start_request"])
    except Exception:
        return _error_result("runtime_error", workflow_id=workflow_id, transaction_id=transaction_id)
    if type(start_result) is not dict or start_result.get("ok") is not True:
        return _error_result("start_failed", workflow_id=workflow_id, transaction_id=transaction_id)
    if start_result.get("workflow_id") not in {None, workflow_id}:
        return _error_result("workflow_id_mismatch", workflow_id=workflow_id, transaction_id=transaction_id)
    start_status = _safe_status(start_result.get("status"), default="started")

    initial_snapshot = await _query_ready_snapshot(control_surface, workflow_id)
    if initial_snapshot is None:
        return _error_result("snapshot_unavailable", workflow_id=workflow_id, transaction_id=transaction_id)
    if initial_snapshot["transaction_id"] != transaction_id:
        return _error_result("workflow_id_mismatch", workflow_id=workflow_id, transaction_id=transaction_id)

    delivery_plan = safe_publication["delivery_plan"]
    delivery_statuses = initial_snapshot["delivery_statuses"]
    if type(delivery_statuses) is not dict or any(item["target_id"] not in delivery_statuses for item in delivery_plan):
        return _error_result("delivery_target_mismatch", workflow_id=workflow_id, transaction_id=transaction_id)

    publication_envelope = _publication_envelope(
        workflow_id=workflow_id,
        transaction_id=transaction_id,
        delivery_plan=delivery_plan,
    )
    ack_results: list[dict[str, object]] = []
    for item in delivery_plan:
        ack_envelope = {
            "type": SHADOW_ACK_ENVELOPE_TYPE,
            "workflow_id": workflow_id,
            "delivery_key": item["delivery_key"],
            "surface": item["surface"],
            "target_kind": item["target_kind"],
            "target_id": item["target_id"],
            "status": item["status"],
        }
        ack_result = await reconcile_shadow_gateway_ack(control_surface, ack_envelope)
        if type(ack_result) is not dict or ack_result.get("ok") is not True:
            return _error_result("ack_reconciliation_failed", workflow_id=workflow_id, transaction_id=transaction_id)
        ack_results.append(
            {
                "target_id": item["target_id"],
                "surface": item["surface"],
                "status": item["status"],
                "ack_status": _safe_ack_status(ack_result.get("status")),
            }
        )

    final_snapshot = await _query_ready_snapshot(control_surface, workflow_id)
    if final_snapshot is None:
        return _error_result("snapshot_unavailable", workflow_id=workflow_id, transaction_id=transaction_id)
    if final_snapshot["transaction_id"] != transaction_id:
        return _error_result("workflow_id_mismatch", workflow_id=workflow_id, transaction_id=transaction_id)

    result: dict[str, object] = {
        "ok": True,
        "loop_version": FLOWWEAVER_GATEWAY_SHADOW_E2E_LOOP_VERSION,
        "operation": _OPERATION,
        "workflow_id": workflow_id,
        "transaction_id": transaction_id,
        "start_status": start_status,
        "publication": publication_envelope,
        "ack_results": ack_results,
        "final_snapshot": final_snapshot,
        "checks": {
            "start_accepted": True,
            "initial_snapshot_safe": True,
            "publication_envelope_safe": True,
            "delivery_targets_initialized": True,
            "ack_count_matches_publication": len(ack_results) == len(delivery_plan),
            "final_snapshot_safe": True,
            "side_effects_absent": True,
        },
        "side_effects": [],
    }
    return _checked_result(result)


def _validate_ready_publication(publication: object) -> dict[str, object]:
    safe = _plain_dict(publication, error="invalid_publication")
    _reject_unsafe_material(safe, error="invalid_publication", allow_start_contract=True)
    if set(safe) != _PUBLICATION_KEYS:
        _raise("invalid_publication")
    if not (
        safe["type"] == _READY_PUBLICATION_TYPE
        and safe["verdict"] == _READY
        and safe["reason"] == "ok"
        and safe["runtime_model_version"] == "flowweaver.runtime.v0"
        and safe["runtime_envelope_type"] == "flowweaver.gateway.runtime_ingress_envelope.v0"
        and safe["side_effects"] == []
    ):
        _raise("invalid_publication")
    workflow_id = _workflow_id(safe["workflow_id"], error="invalid_publication")
    transaction_id = _workflow_id(safe["transaction_id"], error="invalid_publication")
    if workflow_id != transaction_id:
        _raise("workflow_id_mismatch")
    start_request = _start_request(safe["start_request"], workflow_id=workflow_id)
    _runtime_identity(
        safe["runtime_identity"],
        workflow_id=workflow_id,
        idempotency_key=start_request["start_payload"]["idempotency_key"],
    )
    _checks(safe["checks"])
    delivery_plan = _delivery_plan_from_ack_bridge(safe["ack_bridge"])
    return {
        "workflow_id": workflow_id,
        "transaction_id": transaction_id,
        "start_request": start_request,
        "delivery_plan": delivery_plan,
    }


def _start_request(value: object, *, workflow_id: str) -> dict[str, object]:
    request = _plain_dict(value, error="invalid_start_payload")
    if set(request) != _START_REQUEST_KEYS:
        _raise("invalid_start_payload")
    if request["operation"] != _START_OPERATION or request["workflow_id"] != workflow_id:
        _raise("invalid_start_payload")
    try:
        payload = build_start_payload_from_safe_fields(request["start_payload"])
    except ValueError:
        _raise("invalid_start_payload")
    if payload.transaction_id != workflow_id:
        _raise("invalid_start_payload")
    return {
        "operation": _START_OPERATION,
        "workflow_id": workflow_id,
        "start_payload": _plain_dict(request["start_payload"], error="invalid_start_payload"),
    }


def _runtime_identity(value: object, *, workflow_id: str, idempotency_key: object) -> None:
    identity = _plain_dict(value, error="invalid_publication")
    if set(identity) != _RUNTIME_IDENTITY_KEYS:
        _raise("invalid_publication")
    if not (
        identity["type"] == "flowweaver.gateway.runtime_identity.v0"
        and identity["strategy"] == "shadow_ref_hash_v0"
        and identity["transaction_id"] == workflow_id
        and identity["workflow_id"] == workflow_id
        and identity["idempotency_key"] == idempotency_key
    ):
        _raise("invalid_publication")
    _synthetic_id(identity["idempotency_key"], prefixes=("runtime_event_",), error="invalid_publication")


def _checks(value: object) -> None:
    checks = _plain_dict(value, error="invalid_publication")
    if set(checks) != _CHECK_KEYS or not all(checks[key] is True for key in _CHECK_KEYS):
        _raise("invalid_publication")


def _delivery_plan_from_ack_bridge(value: object) -> list[dict[str, str]]:
    bridge = _plain_dict(value, error="invalid_delivery_plan")
    if set(bridge) != _ACK_BRIDGE_KEYS or bridge["status"] != _READY:
        _raise("invalid_delivery_plan")
    updates = _plain_list(bridge["updates"], error="invalid_delivery_plan")
    if len(updates) > 20:
        _raise("invalid_delivery_plan")
    return [_delivery_descriptor(update) for update in updates]


def _delivery_descriptor(value: object) -> dict[str, str]:
    update = _plain_string_dict(value, error="invalid_delivery_plan")
    if set(update) != _ACK_UPDATE_KEYS:
        _raise("invalid_delivery_plan")
    if update["event_type"] != _ACK_OPERATION:
        _raise("invalid_delivery_plan")
    return {
        "delivery_key": _synthetic_id(update["delivery_key"], prefixes=("runtime_event_",), error="invalid_delivery_plan"),
        "surface": _closed_string(update["surface"], _ALLOWED_SURFACES, error="invalid_delivery_plan"),
        "target_kind": _closed_string(update["target_kind"], ("delivery",), error="invalid_delivery_plan"),
        "target_id": _synthetic_id(update["target_id"], prefixes=("runtime_delivery_",), error="invalid_delivery_plan"),
        "status": _closed_string(update["status"], ALLOWED_SHADOW_ACK_STATUSES, error="invalid_delivery_plan"),
    }


async def _query_ready_snapshot(control_surface: Any, workflow_id: str) -> dict[str, object] | None:
    for _ in range(20):
        try:
            result = await control_surface.handle({"operation": _QUERY_OPERATION, "workflow_id": workflow_id})
        except Exception:
            await asyncio.sleep(0.05)
            continue
        if type(result) is not dict or result.get("ok") is not True:
            await asyncio.sleep(0.05)
            continue
        if result.get("workflow_id") not in {None, workflow_id}:
            return None
        try:
            snapshot = sanitize_snapshot(result.get("snapshot"))
        except ValueError:
            await asyncio.sleep(0.05)
            continue
        if snapshot["transaction_id"] != workflow_id:
            return None
        return snapshot
    return None


def _publication_envelope(
    *, workflow_id: str, transaction_id: str, delivery_plan: list[dict[str, str]]
) -> dict[str, object]:
    surface_counts = {surface: 0 for surface in _ALLOWED_SURFACES}
    for item in delivery_plan:
        surface_counts[item["surface"]] += 1
    envelope: dict[str, object] = {
        "type": SHADOW_PUBLICATION_ENVELOPE_TYPE,
        "loop_version": FLOWWEAVER_GATEWAY_SHADOW_E2E_LOOP_VERSION,
        "workflow_id": workflow_id,
        "transaction_id": transaction_id,
        "surface_counts": surface_counts,
        "delivery_plan": [dict(item) for item in delivery_plan],
        "side_effects": [],
    }
    _assert_no_forbidden_rendered_material(envelope, error="unsafe_output")
    return envelope


def _error_result(error_code: object, *, workflow_id: str | None = None, transaction_id: str | None = None) -> dict[str, object]:
    safe_error_code = error_code if type(error_code) is str and error_code in _ERROR_CODES else "runtime_error"
    result: dict[str, object] = {
        "ok": False,
        "loop_version": FLOWWEAVER_GATEWAY_SHADOW_E2E_LOOP_VERSION,
        "operation": _OPERATION,
        "error_code": safe_error_code,
        "side_effects": [],
    }
    if workflow_id is not None:
        result["workflow_id"] = workflow_id
    if transaction_id is not None:
        result["transaction_id"] = transaction_id
    return _checked_result(result)


def _checked_result(result: dict[str, object]) -> dict[str, object]:
    if not set(result) <= _RESULT_FIELDS:
        raise RuntimeError("unsafe_output")
    _assert_no_forbidden_rendered_material(result, error="unsafe_output")
    return result


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


def _plain_dict(value: object, *, error: str) -> dict[str, object]:
    copied = _plain_copy(value)
    if type(copied) is not dict:
        _raise(error)
    return copied


def _plain_list(value: object, *, error: str) -> list[object]:
    copied = _plain_copy(value)
    if type(copied) is not list:
        _raise(error)
    return copied


def _plain_string_dict(value: object, *, error: str) -> dict[str, str]:
    copied = _plain_dict(value, error=error)
    if not all(type(key) is str and type(item) is str for key, item in copied.items()):
        _raise(error)
    return {key: item for key, item in copied.items() if type(item) is str}


def _workflow_id(value: object, *, error: str) -> str:
    try:
        return validate_workflow_id(value)
    except ValueError:
        _raise(error)


def _synthetic_id(value: object, *, prefixes: tuple[str, ...], error: str) -> str:
    if type(value) is not str or not value or len(value) > 128:
        _raise(error)
    if not value.startswith(prefixes):
        _raise(error)
    lowered = value.lower()
    body_prefix = next((prefix for prefix in prefixes if lowered.startswith(prefix)), "")
    body = lowered[len(body_prefix) :]
    if any(lowered.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
        _raise(error)
    if any(
        marker in body
        for marker in ("om_", "oc_", "ou_", "chat", "message", "platform", "feishu", "lark", "telegram", "private")
    ):
        _raise(error)
    if any(marker in lowered for marker in _SYNTHETIC_ID_FORBIDDEN_SUBSTRINGS):
        _raise(error)
    if not all(("a" <= char <= "z") or ("0" <= char <= "9") or char == "_" for char in value):
        _raise(error)
    return value


def _closed_string(value: object, allowed: tuple[str, ...], *, error: str) -> str:
    if type(value) is not str or value not in allowed:
        _raise(error)
    return value


def _safe_status(value: object, *, default: str) -> str:
    if type(value) is str and value in {"started", "running", "published"}:
        return value
    return default


def _safe_ack_status(value: object) -> str:
    if type(value) is str and value in {"applied", "duplicate", "rejected"}:
        return value
    return "rejected"


def _reject_unsafe_material(
    value: object,
    *,
    error: str,
    allow_start_contract: bool = False,
    path: tuple[str, ...] = (),
) -> None:
    if allow_start_contract and path == ("start_request", "start_payload", "claim_check_policy", "forbidden_material"):
        return
    if type(value) is dict:
        for key, item in value.items():
            lowered = key.lower()
            if not (
                allow_start_contract
                and path == ("start_request", "start_payload", "claim_check_policy")
                and key == "forbidden_material"
            ):
                if lowered in _UNSAFE_EXACT_KEYS or any(marker in lowered for marker in _UNSAFE_KEY_SUBSTRINGS):
                    _raise(error)
            _reject_unsafe_material(item, error=error, allow_start_contract=allow_start_contract, path=path + (key,))
        return
    if type(value) is list:
        for item in value:
            _reject_unsafe_material(item, error=error, allow_start_contract=allow_start_contract, path=path)
        return
    if type(value) is str:
        lowered = value.lower()
        if any(lowered.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
            _raise(error)
        if any(marker in lowered for marker in _UNSAFE_VALUE_MARKERS):
            _raise(error)


def _assert_no_forbidden_rendered_material(value: object, *, error: str) -> None:
    rendered = repr(value).lower()
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
        "delivery_ack_payload",
        "card_json",
        "media_path",
        "oc_private",
        "ou_private",
        "om_private",
        "unsafe-" + "token",
        "sk" + "-",
        "bearer ",
    )
    if any(marker in rendered for marker in forbidden):
        _raise(error)


def _raise(error: str) -> None:
    raise ValueError(error) from None


__all__ = [
    "FLOWWEAVER_GATEWAY_SHADOW_E2E_LOOP_VERSION",
    "SHADOW_PUBLICATION_ENVELOPE_TYPE",
    "run_shadow_gateway_e2e_loop",
]
