"""Runtime facade for the FlowWeaver Phase 5B local Temporal POC."""

from __future__ import annotations

from typing import Any

from flowweaver_runtime_client.contracts import (
    make_error_result,
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
        from temporalio.exceptions import WorkflowAlreadyStartedError

        validate_start_payload(payload)
        safe_workflow_id = validate_workflow_id(workflow_id)
        try:
            handle = await self._temporal_client.start_workflow(
                FlowWeaverTransactionWorkflow.run,
                payload,
                id=safe_workflow_id,
                task_queue=self._task_queue or FLOWWEAVER_TEMPORAL_TASK_QUEUE,
            )
        except WorkflowAlreadyStartedError:
            return await self._duplicate_start_result(payload, workflow_id=safe_workflow_id)
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
        safe_workflow_id = validate_workflow_id(workflow_id)
        rejected = await self._rejected_delivery_ack_if_target_missing(safe_workflow_id, update)
        if rejected is not None:
            return rejected
        return await self._execute_update(
            safe_workflow_id,
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

    async def _duplicate_start_result(self, payload: Any, *, workflow_id: str) -> dict[str, object]:
        from flowweaver_temporal_poc.payloads import snapshot_to_safe_dict
        from flowweaver_temporal_poc.workflows import FlowWeaverTransactionWorkflow

        try:
            handle = self._temporal_client.get_workflow_handle(workflow_id)
            snapshot = await handle.query(FlowWeaverTransactionWorkflow.query_snapshot)
            safe_snapshot = sanitize_snapshot(snapshot_to_safe_dict(snapshot))
        except Exception:
            return make_error_result(operation="start_transaction", error_code="runtime_error")
        if not _snapshot_matches_start_payload(safe_snapshot, payload):
            return make_error_result(operation="start_transaction", error_code="invalid_start_payload")
        return make_success_result(
            operation="start_transaction",
            workflow_id=workflow_id,
            transaction_id=payload.transaction_id,
            status="running",
        )

    async def _rejected_delivery_ack_if_target_missing(self, workflow_id: str, update: Any) -> dict[str, object] | None:
        from flowweaver_temporal_poc import FLOWWEAVER_TEMPORAL_POC_VERSION
        from flowweaver_temporal_poc.payloads import snapshot_to_safe_dict
        from flowweaver_temporal_poc.workflows import FlowWeaverTransactionWorkflow

        try:
            handle = self._temporal_client.get_workflow_handle(workflow_id)
            snapshot = await handle.query(FlowWeaverTransactionWorkflow.query_snapshot)
            safe_snapshot = sanitize_snapshot(snapshot_to_safe_dict(snapshot))
        except Exception:
            return make_error_result(operation="record_delivery_ack", error_code="runtime_error")
        delivery_statuses = safe_snapshot["delivery_statuses"]
        if type(delivery_statuses) is dict and update.target_id in delivery_statuses:
            return None
        return make_update_success_result(
            operation="record_delivery_ack",
            workflow_id=workflow_id,
            update_result={
                "type": "flowweaver.temporal_poc.update_result.v0",
                "version": FLOWWEAVER_TEMPORAL_POC_VERSION,
                "update_status": "rejected",
                "snapshot": safe_snapshot,
                "side_effects": [],
            },
        )

    async def _execute_update(self, workflow_id: str, *, operation: str, update_callable: Any, update: Any) -> dict[str, object]:
        safe_workflow_id = validate_workflow_id(workflow_id)
        handle = self._temporal_client.get_workflow_handle(safe_workflow_id)
        result = await handle.execute_update(update_callable, update)
        return make_update_success_result(operation=operation, workflow_id=safe_workflow_id, update_result=result)


def _snapshot_matches_start_payload(snapshot: dict[str, object], payload: Any) -> bool:
    from flowweaver_temporal_poc.payloads import start_signature_from_payload

    if snapshot.get("status") not in {"running", "waiting_for_user"}:
        return False
    if snapshot.get("transaction_id") != payload.transaction_id:
        return False
    if snapshot.get("entry_count") != payload.entry_count:
        return False
    if snapshot.get("record_counts") != payload.record_counts:
        return False
    if snapshot.get("start_signature") != start_signature_from_payload(payload):
        return False
    expected_counts = {
        "intents": payload.entry_count,
        "artifacts": payload.entry_count,
        "deliveries": payload.record_counts["deliveries"],
    }
    if snapshot.get("counts") != expected_counts:
        return False
    if snapshot.get("side_effects") != []:
        return False
    return (
        set(snapshot.get("intent_statuses", {})) == {f"runtime_intent_{index}" for index in range(payload.entry_count)}
        and set(snapshot.get("artifact_statuses", {})) == {f"runtime_artifact_{index}" for index in range(payload.entry_count)}
        and set(snapshot.get("delivery_statuses", {}))
        == {f"runtime_delivery_{index}" for index in range(payload.record_counts["deliveries"])}
    )


__all__ = ["FlowWeaverRuntimeClient"]
