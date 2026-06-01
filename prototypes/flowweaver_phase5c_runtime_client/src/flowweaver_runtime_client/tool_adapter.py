"""MCP-style dictionary adapter for the FlowWeaver Phase 5C runtime facade."""

from __future__ import annotations

import inspect
from typing import Any, Callable

from flowweaver_runtime_client.contracts import (
    build_start_payload_from_safe_fields,
    cancel_transaction_from_tool_update,
    delivery_ack_from_tool_update,
    human_decision_from_tool_update,
    make_error_result,
    resume_user_input_from_tool_update,
    sanitize_tool_request,
    validate_operation,
)
from flowweaver_runtime_client.runtime_client import FlowWeaverRuntimeClient


RuntimeClientFactory = Callable[[], Any]


class FlowWeaverRuntimeToolAdapter:
    """Accept one closed-set operation dictionary and return safe tool-visible results."""

    def __init__(self, runtime_client: FlowWeaverRuntimeClient) -> None:
        self._runtime_client = runtime_client

    @classmethod
    def from_temporal_client(cls, temporal_client: Any, *, temporal_address: str) -> "FlowWeaverRuntimeToolAdapter":
        return cls(FlowWeaverRuntimeClient(temporal_client, temporal_address=temporal_address))

    async def handle(self, request: object) -> dict[str, object]:
        operation = _operation_for_error_result(request)
        try:
            safe_request = sanitize_tool_request(request)
            operation = validate_operation(safe_request["operation"])
            if operation == "start_transaction":
                payload = _start_payload_from_request(safe_request)
                workflow_id = _required_field(safe_request, "workflow_id")
                return await self._runtime_client.start_transaction(payload, workflow_id=workflow_id)
            if operation == "query_snapshot":
                workflow_id = _required_field(safe_request, "workflow_id")
                return await self._runtime_client.query_snapshot(workflow_id)
            if operation == "record_delivery_ack":
                workflow_id = _required_field(safe_request, "workflow_id")
                update = delivery_ack_from_tool_update(_required_field(safe_request, "update"))
                return await self._runtime_client.record_delivery_ack(workflow_id, update)
            if operation == "approve_intent":
                workflow_id = _required_field(safe_request, "workflow_id")
                update = human_decision_from_tool_update(_required_field(safe_request, "update"), operation="approve_intent")
                return await self._runtime_client.approve_intent(workflow_id, update)
            if operation == "reject_intent":
                workflow_id = _required_field(safe_request, "workflow_id")
                update = human_decision_from_tool_update(_required_field(safe_request, "update"), operation="reject_intent")
                return await self._runtime_client.reject_intent(workflow_id, update)
            if operation == "cancel_transaction":
                workflow_id = _required_field(safe_request, "workflow_id")
                update = cancel_transaction_from_tool_update(_required_field(safe_request, "update"))
                return await self._runtime_client.cancel_transaction(workflow_id, update)
            if operation == "resume_after_user_input":
                workflow_id = _required_field(safe_request, "workflow_id")
                update = resume_user_input_from_tool_update(_required_field(safe_request, "update"))
                return await self._runtime_client.resume_after_user_input(workflow_id, update)
        except ValueError as exc:
            return make_error_result(operation=operation, error_code=str(exc))
        except Exception:
            return make_error_result(operation=operation, error_code="runtime_error")
        return make_error_result(operation=operation, error_code="invalid_operation")


def _start_payload_from_request(request: dict[str, object]) -> Any:
    if "start_payload" in request:
        return build_start_payload_from_safe_fields(request["start_payload"])
    if "payload" in request:
        return build_start_payload_from_safe_fields(request["payload"])
    raise ValueError("invalid_start_payload")


def _required_field(request: dict[str, object], key: str) -> Any:
    if key not in request:
        raise ValueError("missing_required_field")
    return request[key]


def _operation_for_error_result(request: object) -> str | None:
    if type(request) is not dict:
        return None
    operation = request.get("operation")
    if type(operation) is not str:
        return None
    try:
        return validate_operation(operation)
    except ValueError:
        return None


async def invoke_flowweaver_runtime(
    request: object,
    *,
    temporal_address: str | None = None,
    temporal_client: Any | None = None,
    runtime_client_factory: RuntimeClientFactory | None = None,
) -> dict[str, object]:
    operation = _operation_for_error_result(request)
    try:
        if runtime_client_factory is not None:
            runtime_client = runtime_client_factory()
            if inspect.isawaitable(runtime_client):
                runtime_client = await runtime_client
        elif temporal_client is not None:
            runtime_client = FlowWeaverRuntimeClient(temporal_client, temporal_address=temporal_address)
        else:
            if temporal_address is None:
                return make_error_result(operation=operation, error_code="temporal_address_required")
            runtime_client = await FlowWeaverRuntimeClient.connect(temporal_address=temporal_address)
    except ValueError as exc:
        return make_error_result(operation=operation, error_code=str(exc))
    except Exception:
        return make_error_result(operation=operation, error_code="runtime_error")
    adapter = FlowWeaverRuntimeToolAdapter(runtime_client)
    return await adapter.handle(request)


__all__ = ["FlowWeaverRuntimeToolAdapter", "invoke_flowweaver_runtime"]
