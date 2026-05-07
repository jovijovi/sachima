"""RED integration tests for FlowWeaver Phase 6 Gateway ACK shadow bridge."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

ROOT = Path(__file__).resolve().parents[2]
PHASE5B_SRC = ROOT / "prototypes" / "flowweaver_phase5b_temporal_poc" / "src"
PHASE5C_SRC = ROOT / "prototypes" / "flowweaver_phase5c_runtime_client" / "src"
for path in (PHASE5C_SRC, PHASE5B_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from flowweaver_temporal_poc import FLOWWEAVER_TEMPORAL_TASK_QUEUE  # noqa: E402
from flowweaver_temporal_poc.activities import deliver_artifact, execute_agent_turn, validate_claim_check_ref  # noqa: E402
from flowweaver_temporal_poc.workflows import FlowWeaverTransactionWorkflow  # noqa: E402
from flowweaver_runtime_client.control_surface import FlowWeaverRuntimeControlSurface  # noqa: E402
from flowweaver_runtime_client.runtime_client import FlowWeaverRuntimeClient  # noqa: E402

pytestmark = pytest.mark.integration

PRIVATE_CHAT_ID = "oc_" + "phase6_private_chat"
PRIVATE_USER_ID = "ou_" + "phase6_private_user"
SENSITIVE_SENTINEL = "unsafe-" + "token" + "-phase6"
FORBIDDEN_SENTINELS = (PRIVATE_CHAT_ID, PRIVATE_USER_ID, SENSITIVE_SENTINEL)


def make_start_fields(*, workflow_id: str, count: int = 1) -> dict[str, object]:
    suffix = workflow_id.removeprefix("runtime_tx_")
    return {
        "transaction_id": workflow_id,
        "idempotency_key": "runtime_event_start_" + suffix,
        "entry_count": count,
        "record_counts": {"transactions": 1, "intents": count, "artifacts": count, "deliveries": count},
        "allowed_runtime_events": [
            "start_transaction",
            "record_operation",
            "publish_artifact",
            "plan_delivery",
            "record_delivery_ack",
            "approve_intent",
            "reject_intent",
            "cancel_transaction",
            "resume_after_user_input",
        ],
        "claim_check_policy": {
            "mode": "references_only",
            "allowed_reference_fields": ["ref", "kind", "count", "size", "checksum_hint"],
            "forbidden_material": [
                "raw_snapshot",
                "raw_capture",
                "full_agent_result",
                "raw_prompt",
                "raw_command",
                "stdout",
                "stderr",
                "tool_output",
                "card_json",
                "media_bytes",
                "media_path",
                "platform_payload",
                "platform_id",
                "chat_id",
                "user_id",
                "message_id",
                "delivery_ack_payload",
                "credential",
                "token",
                "secret",
            ],
        },
    }


async def open_real_worker() -> tuple[WorkflowEnvironment, Worker, FlowWeaverRuntimeControlSurface]:
    env = await WorkflowEnvironment.start_time_skipping()
    worker = Worker(
        env.client,
        task_queue=FLOWWEAVER_TEMPORAL_TASK_QUEUE,
        workflows=[FlowWeaverTransactionWorkflow],
        activities=[validate_claim_check_ref, execute_agent_turn, deliver_artifact],
    )
    await env.__aenter__()
    await worker.__aenter__()
    facade = FlowWeaverRuntimeClient(env.client, temporal_address="localhost:7233")
    return env, worker, FlowWeaverRuntimeControlSurface(facade)


async def close_real_worker(env: WorkflowEnvironment, worker: Worker) -> None:
    await worker.__aexit__(None, None, None)
    await env.__aexit__(None, None, None)


async def query_until_running(
    control: FlowWeaverRuntimeControlSurface, workflow_id: str, *, require_activity_boundary: bool = False
) -> dict[str, object]:
    last: dict[str, object] | None = None
    for _ in range(40):
        result = await control.handle({"operation": "query_transaction", "workflow_id": workflow_id})
        if result.get("ok") is True:
            snapshot = result.get("snapshot")
            if type(snapshot) is dict and snapshot.get("status") == "running":
                activity_boundary = snapshot.get("activity_boundary")
                if not require_activity_boundary or (
                    type(activity_boundary) is dict and activity_boundary.get("status") == "completed"
                ):
                    return result
        last = result
        await asyncio.sleep(0.05)
    raise AssertionError(f"workflow did not reach running through control surface: {last!r}")


def history_text_and_bytes(history: Any) -> tuple[str, bytes]:
    rendered = history.to_json() if hasattr(history, "to_json") else repr(history.to_json_dict())
    raw_events = b"".join(event.SerializeToString() for event in history.events)
    return rendered, raw_events


def assert_no_forbidden_material(value: object) -> None:
    rendered = repr(value).lower()
    for forbidden in FORBIDDEN_SENTINELS:
        assert forbidden.lower() not in rendered
    assert "raw_prompt" not in rendered
    assert "platform_payload" not in rendered
    assert "workflowalreadystartederror" not in rendered


@pytest.mark.asyncio
async def test_phase6_shadow_bridge_reconciles_and_replays_ack_without_history_leaks() -> None:
    from flowweaver_runtime_client.gateway_ack_shadow_bridge import reconcile_shadow_gateway_ack

    env, worker, control = await open_real_worker()
    workflow_id = "runtime_tx_phase6_shadow_integration"
    try:
        started = await control.handle(
            {"operation": "start_transaction", "workflow_id": workflow_id, "start_payload": make_start_fields(workflow_id=workflow_id)}
        )
        snapshot_result = await query_until_running(control, workflow_id, require_activity_boundary=True)
        ack_envelope = {
            "type": "flowweaver.gateway_ack_shadow.v0",
            "workflow_id": workflow_id,
            "delivery_key": "runtime_event_delivery_ack_phase6_shadow_integration",
            "surface": "final_text",
            "target_kind": "delivery",
            "target_id": "runtime_delivery_0",
            "status": "acknowledged",
        }

        acked = await reconcile_shadow_gateway_ack(control, ack_envelope)
        duplicate = await reconcile_shadow_gateway_ack(control, ack_envelope)
        after_duplicate = await control.handle({"operation": "query_transaction", "workflow_id": workflow_id})
        hostile = await reconcile_shadow_gateway_ack(
            control,
            {**ack_envelope, "delivery_key": "runtime_event_delivery_ack_phase6_hostile", "platform_payload": {"chat_id": PRIVATE_CHAT_ID, "user_id": PRIVATE_USER_ID}, "note": SENSITIVE_SENTINEL},
        )
        canceled = await control.handle(
            {
                "operation": "cancel_transaction",
                "workflow_id": workflow_id,
                "update": {"event_type": "cancel_transaction", "event_id": "runtime_event_cancel_phase6_shadow_integration"},
            }
        )
        await env.client.get_workflow_handle(workflow_id).result()
        history = await env.client.get_workflow_handle(workflow_id).fetch_history()
        rendered, raw_events = history_text_and_bytes(history)

        assert started["ok"] is True
        assert snapshot_result["snapshot"]["activity_boundary"]["status"] == "completed"
        assert acked["ok"] is True
        assert acked["operation"] == "gateway_ack_shadow_bridge"
        assert acked["runtime_operation"] == "record_delivery_ack"
        assert acked["status"] == "applied"
        assert acked["snapshot"]["delivery_statuses"] == {"runtime_delivery_0": "acknowledged"}
        assert duplicate["status"] == "duplicate"
        assert after_duplicate["snapshot"]["applied_event_count"] == acked["snapshot"]["applied_event_count"]
        assert hostile["error_code"] == "unsafe_ack_envelope"
        assert canceled["snapshot"]["status"] == "canceled"
        for value in (started, snapshot_result, acked, duplicate, after_duplicate, hostile, canceled):
            assert_no_forbidden_material(value)
        for forbidden in FORBIDDEN_SENTINELS:
            assert forbidden not in rendered
            assert forbidden.encode() not in raw_events
    finally:
        await close_real_worker(env, worker)


@pytest.mark.asyncio
async def test_phase6_shadow_bridge_rejects_missing_delivery_target_without_inventing_runtime_slot() -> None:
    from flowweaver_runtime_client.gateway_ack_shadow_bridge import reconcile_shadow_gateway_ack

    env, worker, control = await open_real_worker()
    workflow_id = "runtime_tx_phase6_shadow_missing_target"
    try:
        await control.handle(
            {"operation": "start_transaction", "workflow_id": workflow_id, "start_payload": make_start_fields(workflow_id=workflow_id)}
        )
        before = await query_until_running(control, workflow_id)
        rejected = await reconcile_shadow_gateway_ack(
            control,
            {
                "type": "flowweaver.gateway_ack_shadow.v0",
                "workflow_id": workflow_id,
                "delivery_key": "runtime_event_delivery_ack_phase6_missing_target",
                "surface": "final_text",
                "target_kind": "delivery",
                "target_id": "runtime_delivery_1",
                "status": "sent",
            },
        )
        after = await control.handle({"operation": "query_transaction", "workflow_id": workflow_id})
        canceled = await control.handle(
            {
                "operation": "cancel_transaction",
                "workflow_id": workflow_id,
                "update": {"event_type": "cancel_transaction", "event_id": "runtime_event_cancel_phase6_missing_target"},
            }
        )
        await env.client.get_workflow_handle(workflow_id).result()
        history = await env.client.get_workflow_handle(workflow_id).fetch_history()
        rendered, raw_events = history_text_and_bytes(history)

        assert before["snapshot"]["delivery_statuses"] == {"runtime_delivery_0": "planned"}
        assert rejected == {
            "ok": False,
            "bridge_version": "flowweaver.gateway_ack_shadow_bridge.v0",
            "operation": "gateway_ack_shadow_bridge",
            "runtime_operation": "record_delivery_ack",
            "workflow_id": workflow_id,
            "target_id": "runtime_delivery_1",
            "error_code": "delivery_target_mismatch",
        }
        assert after["snapshot"]["delivery_statuses"] == {"runtime_delivery_0": "planned"}
        assert after["snapshot"]["applied_event_count"] == before["snapshot"]["applied_event_count"]
        assert canceled["snapshot"]["status"] == "canceled"
        for value in (before, rejected, after, canceled):
            assert_no_forbidden_material(value)
        assert "runtime_delivery_1" not in rendered
        assert b"runtime_delivery_1" not in raw_events
    finally:
        await close_real_worker(env, worker)
