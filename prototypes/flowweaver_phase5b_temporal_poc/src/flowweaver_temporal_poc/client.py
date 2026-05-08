"""Manual local Temporal client helpers for the FlowWeaver Phase 5B POC."""

from __future__ import annotations

from temporalio.client import Client

from flowweaver_temporal_poc import FLOWWEAVER_TEMPORAL_TASK_QUEUE
from flowweaver_temporal_poc.payloads import RuntimeStartPayload, validate_runtime_workflow_id, validate_start_payload
from flowweaver_temporal_poc.workflows import FlowWeaverTransactionWorkflow


async def connect_local_temporal(address: str) -> Client:
    """Connect to an explicitly supplied local Temporal endpoint."""

    safe_address = _validate_local_address(address)
    try:
        return await Client.connect(safe_address)
    except Exception as exc:
        raise RuntimeError("local_temporal_unavailable") from exc


async def start_local_poc_workflow(client: Client, payload: RuntimeStartPayload, workflow_id: str) -> str:
    """Start the local POC workflow without starting any service or daemon."""

    validate_start_payload(payload)
    safe_workflow_id = _validate_workflow_id(workflow_id)
    handle = await client.start_workflow(
        FlowWeaverTransactionWorkflow.run,
        payload,
        id=safe_workflow_id,
        task_queue=FLOWWEAVER_TEMPORAL_TASK_QUEUE,
    )
    return handle.id


def _validate_local_address(address: str) -> str:
    if type(address) is not str or not address:
        raise ValueError("invalid_temporal_address") from None
    if address.startswith("localhost:") or address.startswith("127.0.0.1:"):
        return address
    raise ValueError("invalid_temporal_address") from None


def _validate_workflow_id(workflow_id: str) -> str:
    return validate_runtime_workflow_id(workflow_id)


__all__ = [
    "connect_local_temporal",
    "start_local_poc_workflow",
]
