"""Prototype-only control surface for the FlowWeaver Phase 5C runtime facade."""

from __future__ import annotations

import inspect
from typing import Any, Callable

from flowweaver_runtime_client.contracts import (
    build_start_payload_from_safe_fields,
    cancel_transaction_from_tool_update,
    delivery_ack_from_tool_update,
    make_error_result,
    make_success_result,
    sanitize_tool_request,
    validate_workflow_id,
)
from flowweaver_runtime_client.runtime_client import FlowWeaverRuntimeClient

FLOWWEAVER_RUNTIME_CONTROL_SURFACE_VERSION = "flowweaver.runtime_control.v0"
CONTROL_OPERATIONS = (
    "start_transaction",
    "query_transaction",
    "reconcile_delivery_ack",
    "cancel_transaction",
)
RUNTIME_OPERATION_BY_CONTROL_OPERATION = {
    "start_transaction": "start_transaction",
    "query_transaction": "query_snapshot",
    "reconcile_delivery_ack": "record_delivery_ack",
    "cancel_transaction": "cancel_transaction",
}
CONTROL_RESULT_FIELDS = {
    "ok",
    "operation",
    "runtime_operation",
    "workflow_id",
    "transaction_id",
    "status",
    "snapshot",
    "error_code",
}

RuntimeClientFactory = Callable[[], Any]


class FlowWeaverRuntimeControlSurface:
    """Translate safe public control operations into runtime facade calls."""

    def __init__(self, runtime_client: FlowWeaverRuntimeClient) -> None:
        self._runtime_client = runtime_client

    async def handle(self, request: object) -> dict[str, object]:
        operation = _operation_for_error_result(request)
        runtime_operation = _runtime_operation_for_error_result(operation)
        try:
            prepared = _prepare_control_request(request)
            operation = prepared["operation"]
            runtime_operation = prepared["runtime_operation"]
            runtime_result = await self._dispatch(prepared)
            return _control_result_from_runtime_result(
                control_operation=operation,
                runtime_operation=runtime_operation,
                workflow_id=prepared.get("workflow_id"),
                runtime_result=runtime_result,
            )
        except ValueError as exc:
            return _control_error_result(
                operation=operation,
                runtime_operation=runtime_operation,
                error_code=str(exc),
            )
        except Exception:
            return _control_error_result(
                operation=operation,
                runtime_operation=runtime_operation,
                error_code="runtime_error",
            )

    async def _dispatch(self, prepared: dict[str, Any]) -> dict[str, object]:
        runtime_operation = prepared["runtime_operation"]
        workflow_id = prepared["workflow_id"]
        if runtime_operation == "start_transaction":
            return await self._runtime_client.start_transaction(prepared["payload"], workflow_id=workflow_id)
        if runtime_operation == "query_snapshot":
            return await self._runtime_client.query_snapshot(workflow_id)
        if runtime_operation == "record_delivery_ack":
            return await self._runtime_client.record_delivery_ack(workflow_id, prepared["update"])
        if runtime_operation == "cancel_transaction":
            return await self._runtime_client.cancel_transaction(workflow_id, prepared["update"])
        raise ValueError("invalid_operation")


async def invoke_flowweaver_runtime_control(
    request: object,
    *,
    temporal_address: str | None = None,
    temporal_client: Any | None = None,
    runtime_client_factory: RuntimeClientFactory | None = None,
) -> dict[str, object]:
    operation = _operation_for_error_result(request)
    runtime_operation = _runtime_operation_for_error_result(operation)
    try:
        if runtime_client_factory is not None:
            runtime_client = runtime_client_factory()
            if inspect.isawaitable(runtime_client):
                runtime_client = await runtime_client
        elif temporal_client is not None:
            runtime_client = FlowWeaverRuntimeClient(temporal_client, temporal_address=temporal_address)
        else:
            if temporal_address is None:
                return _control_error_result(
                    operation=operation,
                    runtime_operation=runtime_operation,
                    error_code="temporal_address_required",
                )
            runtime_client = await FlowWeaverRuntimeClient.connect(temporal_address=temporal_address)
    except ValueError as exc:
        return _control_error_result(
            operation=operation,
            runtime_operation=runtime_operation,
            error_code=str(exc),
        )
    except Exception:
        return _control_error_result(
            operation=operation,
            runtime_operation=runtime_operation,
            error_code="runtime_error",
        )
    return await FlowWeaverRuntimeControlSurface(runtime_client).handle(request)


def _prepare_control_request(request: object) -> dict[str, Any]:
    if type(request) is not dict or not all(type(key) is str for key in request):
        raise ValueError("unsafe_request")
    operation = _validate_control_operation(request.get("operation"))
    expected_keys = _expected_control_keys(operation)
    request_keys = set(request)
    if request_keys - expected_keys:
        raise ValueError("unsafe_request")
    if expected_keys - request_keys:
        raise ValueError("missing_required_field")

    runtime_operation = RUNTIME_OPERATION_BY_CONTROL_OPERATION[operation]
    workflow_id = validate_workflow_id(request["workflow_id"])
    runtime_request: dict[str, object] = {"operation": runtime_operation, "workflow_id": workflow_id}

    if operation == "start_transaction":
        payload = build_start_payload_from_safe_fields(request["start_payload"])
        if payload.transaction_id != workflow_id:
            raise ValueError("invalid_start_payload")
        return {
            "operation": operation,
            "runtime_operation": runtime_operation,
            "workflow_id": workflow_id,
            "payload": payload,
        }
    if operation == "query_transaction":
        sanitize_tool_request(runtime_request)
        return {"operation": operation, "runtime_operation": runtime_operation, "workflow_id": workflow_id}
    if operation == "reconcile_delivery_ack":
        runtime_request["update"] = request["update"]
        safe_request = sanitize_tool_request(runtime_request)
        return {
            "operation": operation,
            "runtime_operation": runtime_operation,
            "workflow_id": workflow_id,
            "update": delivery_ack_from_tool_update(safe_request["update"]),
        }
    if operation == "cancel_transaction":
        runtime_request["update"] = request["update"]
        safe_request = sanitize_tool_request(runtime_request)
        return {
            "operation": operation,
            "runtime_operation": runtime_operation,
            "workflow_id": workflow_id,
            "update": _cancel_update_from_control_update(safe_request["update"]),
        }
    raise ValueError("invalid_operation")


def _expected_control_keys(operation: str) -> set[str]:
    if operation == "start_transaction":
        return {"operation", "workflow_id", "start_payload"}
    if operation == "query_transaction":
        return {"operation", "workflow_id"}
    if operation in {"reconcile_delivery_ack", "cancel_transaction"}:
        return {"operation", "workflow_id", "update"}
    raise ValueError("invalid_operation")


def _validate_control_operation(operation: object) -> str:
    if type(operation) is not str or operation not in CONTROL_OPERATIONS:
        raise ValueError("invalid_operation")
    return operation


def _cancel_update_from_control_update(update: object) -> Any:
    if type(update) is dict and set(update) == {"event_type", "event_id"}:
        update = {**update, "reason_ref": None}
    return cancel_transaction_from_tool_update(update)


def _control_result_from_runtime_result(
    *,
    control_operation: str,
    runtime_operation: str,
    workflow_id: object,
    runtime_result: object,
) -> dict[str, object]:
    if type(runtime_result) is not dict:
        raise ValueError("unsafe_tool_output")
    if runtime_result.get("ok") is not True:
        return _control_error_result(
            operation=control_operation,
            runtime_operation=runtime_operation,
            error_code=runtime_result.get("error_code", "runtime_error"),
        )
    safe_runtime = make_success_result(
        operation=runtime_operation,
        workflow_id=runtime_result.get("workflow_id", workflow_id),
        transaction_id=runtime_result.get("transaction_id"),
        status=runtime_result.get("status"),
        snapshot=runtime_result.get("snapshot"),
    )
    result = _remap_runtime_success_result(
        safe_runtime,
        operation=control_operation,
        runtime_operation=runtime_operation,
    )
    _assert_control_result_shape(result)
    return result


def _remap_runtime_success_result(
    runtime_result: dict[str, object], *, operation: str, runtime_operation: str
) -> dict[str, object]:
    result: dict[str, object] = {
        "ok": True,
        "operation": operation,
        "runtime_operation": runtime_operation,
    }
    for key in ("workflow_id", "transaction_id", "status", "snapshot"):
        if key in runtime_result:
            result[key] = runtime_result[key]
    return result


def _control_error_result(
    *,
    operation: str | None,
    runtime_operation: str | None,
    error_code: object,
) -> dict[str, object]:
    safe_runtime = make_error_result(operation=runtime_operation, error_code=error_code)
    result: dict[str, object] = {"ok": False}
    if operation is not None:
        result["operation"] = operation
    if runtime_operation is not None:
        result["runtime_operation"] = runtime_operation
    result["error_code"] = safe_runtime["error_code"]
    _assert_control_result_shape(result)
    return result


def _operation_for_error_result(request: object) -> str | None:
    if type(request) is not dict:
        return None
    try:
        return _validate_control_operation(request.get("operation"))
    except ValueError:
        return None


def _runtime_operation_for_error_result(operation: str | None) -> str | None:
    if operation is None:
        return None
    return RUNTIME_OPERATION_BY_CONTROL_OPERATION.get(operation)


def _assert_control_result_shape(result: dict[str, object]) -> None:
    if not set(result) <= CONTROL_RESULT_FIELDS:
        raise ValueError("unsafe_tool_output")
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
        "delivery_ack_payload",
        "oc_private",
        "ou_private",
        "om_private",
        "unsafe-token",
        "sk" + "-",
        "bearer ",
    )
    if any(marker in rendered for marker in forbidden):
        raise ValueError("unsafe_tool_output")


__all__ = [
    "CONTROL_OPERATIONS",
    "FLOWWEAVER_RUNTIME_CONTROL_SURFACE_VERSION",
    "RUNTIME_OPERATION_BY_CONTROL_OPERATION",
    "FlowWeaverRuntimeControlSurface",
    "invoke_flowweaver_runtime_control",
]
