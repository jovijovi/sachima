"""Runtime facade for the FlowWeaver Phase 5B local Temporal POC."""

from __future__ import annotations

from typing import Any

from flowweaver_runtime_client.contracts import (
    make_success_result,
    make_update_success_result,
    sanitize_snapshot,
    validate_temporal_address,
    validate_workflow_id,
)


class FlowWeaverRuntimeClient:
    """Narrow facade over a caller-supplied local Temporal client.

    The facade connects/calls only. It never starts service lifecycles, workers, or Gateway.
    """

    def __init__(self, temporal_client: Any, *, temporal_address: str | None, task_queue: str | None = None) -> None:
        self._temporal_client = temporal_client
        self.temporal_address = validate_temporal_address(temporal_address)
        self._task_queue = task_queue

    @classmethod
    async def connect(cls, *, temporal_address: str) -> "FlowWeaverRuntimeClient":
        safe_address = validate_temporal_address(temporal_address)
        from flowweaver_temporal_poc.client import connect_local_temporal

        temporal_client = await connect_local_temporal(safe_address)
        return cls(temporal_client, temporal_address=safe_address)

    async def start_transaction(self, payload: Any, *, workflow_id: str) -> dict[str, object]:
        from flowweaver_temporal_poc import FLOWWEAVER_TEMPORAL_TASK_QUEUE
        from flowweaver_temporal_poc.payloads import validate_start_payload
        from flowweaver_temporal_poc.workflows import FlowWeaverTransactionWorkflow

        validate_start_payload(payload)
        safe_workflow_id = validate_workflow_id(workflow_id)
        handle = await self._temporal_client.start_workflow(
            FlowWeaverTransactionWorkflow.run,
            payload,
            id=safe_workflow_id,
            task_queue=self._task_queue or FLOWWEAVER_TEMPORAL_TASK_QUEUE,
        )
        return make_success_result(
            operation="start_transaction",
            workflow_id=handle.id,
            transaction_id=payload.transaction_id,
            status="started",
        )

    async def query_snapshot(self, workflow_id: str) -> dict[str, object]:
        from flowweaver_temporal_poc.payloads import snapshot_to_safe_dict
        from flowweaver_temporal_poc.workflows import FlowWeaverTransactionWorkflow

        safe_workflow_id = validate_workflow_id(workflow_id)
        handle = self._temporal_client.get_workflow_handle(safe_workflow_id)
        snapshot = await handle.query(FlowWeaverTransactionWorkflow.query_snapshot)
        safe_snapshot = sanitize_snapshot(snapshot_to_safe_dict(snapshot))
        return make_success_result(operation="query_snapshot", workflow_id=safe_workflow_id, snapshot=safe_snapshot)

    async def record_delivery_ack(self, workflow_id: str, update: Any) -> dict[str, object]:
        from flowweaver_temporal_poc.payloads import validate_delivery_ack_update
        from flowweaver_temporal_poc.workflows import FlowWeaverTransactionWorkflow

        validate_delivery_ack_update(update)
        return await self._execute_update(
            workflow_id,
            operation="record_delivery_ack",
            update_callable=FlowWeaverTransactionWorkflow.record_delivery_ack,
            update=update,
        )

    async def approve_intent(self, workflow_id: str, update: Any) -> dict[str, object]:
        from flowweaver_temporal_poc.payloads import validate_human_decision_update
        from flowweaver_temporal_poc.workflows import FlowWeaverTransactionWorkflow

        validate_human_decision_update(update, expected_decision="approved")
        return await self._execute_update(
            workflow_id,
            operation="approve_intent",
            update_callable=FlowWeaverTransactionWorkflow.approve_intent,
            update=update,
        )

    async def reject_intent(self, workflow_id: str, update: Any) -> dict[str, object]:
        from flowweaver_temporal_poc.payloads import validate_human_decision_update
        from flowweaver_temporal_poc.workflows import FlowWeaverTransactionWorkflow

        validate_human_decision_update(update, expected_decision="rejected")
        return await self._execute_update(
            workflow_id,
            operation="reject_intent",
            update_callable=FlowWeaverTransactionWorkflow.reject_intent,
            update=update,
        )

    async def cancel_transaction(self, workflow_id: str, update: Any) -> dict[str, object]:
        from flowweaver_temporal_poc.payloads import validate_cancel_transaction_update
        from flowweaver_temporal_poc.workflows import FlowWeaverTransactionWorkflow

        validate_cancel_transaction_update(update)
        return await self._execute_update(
            workflow_id,
            operation="cancel_transaction",
            update_callable=FlowWeaverTransactionWorkflow.cancel_transaction,
            update=update,
        )

    async def resume_after_user_input(self, workflow_id: str, update: Any) -> dict[str, object]:
        from flowweaver_temporal_poc.payloads import validate_resume_user_input_update
        from flowweaver_temporal_poc.workflows import FlowWeaverTransactionWorkflow

        validate_resume_user_input_update(update)
        return await self._execute_update(
            workflow_id,
            operation="resume_after_user_input",
            update_callable=FlowWeaverTransactionWorkflow.resume_after_user_input,
            update=update,
        )

    async def _execute_update(self, workflow_id: str, *, operation: str, update_callable: Any, update: Any) -> dict[str, object]:
        safe_workflow_id = validate_workflow_id(workflow_id)
        handle = self._temporal_client.get_workflow_handle(safe_workflow_id)
        result = await handle.execute_update(update_callable, update)
        return make_update_success_result(operation=operation, workflow_id=safe_workflow_id, update_result=result)


__all__ = ["FlowWeaverRuntimeClient"]
