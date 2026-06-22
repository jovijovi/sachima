"""RED integration tests for FlowWeaver Phase 7 Gateway shadow E2E loop."""

from __future__ import annotations

import copy
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

PRIVATE_CHAT_ID = "oc_" + "phase7_private_chat"
PRIVATE_USER_ID = "ou_" + "phase7_private_user"
SENSITIVE_SENTINEL = "unsafe-" + "token" + "-phase7"
FORBIDDEN_SENTINELS = (PRIVATE_CHAT_ID, PRIVATE_USER_ID, SENSITIVE_SENTINEL)


def make_start_fields(*, workflow_id: str, delivery_count: int = 1) -> dict[str, object]:
    suffix = workflow_id.removeprefix("runtime_tx_")
    return {
        "transaction_id": workflow_id,
        "idempotency_key": "runtime_event_start_" + suffix,
        "entry_count": 1,
        "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": delivery_count},
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


def make_publication(*, workflow_id: str, updates: list[dict[str, str]], delivery_count: int) -> dict[str, object]:
    suffix = workflow_id.removeprefix("runtime_tx_")
    return {
        "type": "flowweaver.gateway.shadow_runtime_publication.v0",
        "verdict": "ready",
        "reason": "ok",
        "runtime_model_version": "flowweaver.runtime.v0",
        "runtime_envelope_type": "flowweaver.gateway.runtime_ingress_envelope.v0",
        "transaction_id": workflow_id,
        "workflow_id": workflow_id,
        "runtime_identity": {
            "type": "flowweaver.gateway.runtime_identity.v0",
            "strategy": "shadow_ref_hash_v0",
            "transaction_id": workflow_id,
            "workflow_id": workflow_id,
            "idempotency_key": "runtime_event_start_" + suffix,
        },
        "start_request": {
            "operation": "start_transaction",
            "workflow_id": workflow_id,
            "start_payload": make_start_fields(workflow_id=workflow_id, delivery_count=delivery_count),
        },
        "ack_bridge": {"status": "ready", "updates": updates},
        "checks": {
            "shadow_capture_present": True,
            "dry_run_summary_valid": True,
            "runtime_envelope_valid": True,
            "start_request_safe": True,
            "delivery_ack_updates_safe": True,
            "payloads_absent": True,
            "visible_side_effects_absent": True,
            "runtime_side_effects_absent": True,
        },
        "side_effects": [],
    }


class RecordingControlSurface:
    def __init__(self, delegate: FlowWeaverRuntimeControlSurface) -> None:
        self.delegate = delegate
        self.calls: list[dict[str, object]] = []

    async def handle(self, request: object) -> dict[str, object]:
        assert type(request) is dict
        self.calls.append(copy.deepcopy(request))
        return await self.delegate.handle(request)


async def open_real_worker() -> tuple[WorkflowEnvironment, Worker, RecordingControlSurface]:
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
    return env, worker, RecordingControlSurface(FlowWeaverRuntimeControlSurface(facade))


async def close_real_worker(env: WorkflowEnvironment, worker: Worker) -> None:
    await worker.__aexit__(None, None, None)
    await env.__aexit__(None, None, None)


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
async def test_phase7_loop_starts_fresh_temporal_workflow_reconciles_via_phase6_and_replays_idempotently() -> None:
    from flowweaver_runtime_client.gateway_shadow_e2e_loop import run_shadow_gateway_e2e_loop

    env, worker, control = await open_real_worker()
    workflow_id = "runtime_tx_phase7_shadow_integration"
    publication = make_publication(
        workflow_id=workflow_id,
        delivery_count=2,
        updates=[
            {
                "event_type": "record_delivery_ack",
                "delivery_key": "runtime_event_delivery_ack_phase7_integration_0",
                "surface": "final_text",
                "target_kind": "delivery",
                "target_id": "runtime_delivery_0",
                "status": "sent",
            },
            {
                "event_type": "record_delivery_ack",
                "delivery_key": "runtime_event_delivery_ack_phase7_integration_1",
                "surface": "rich_card",
                "target_kind": "delivery",
                "target_id": "runtime_delivery_1",
                "status": "acknowledged",
            },
        ],
    )
    try:
        first = await run_shadow_gateway_e2e_loop(control, publication)
        first_ops = [call["operation"] for call in control.calls]
        duplicate = await run_shadow_gateway_e2e_loop(control, publication)
        after_duplicate = await control.handle({"operation": "query_transaction", "workflow_id": workflow_id})
        hostile = copy.deepcopy(publication)
        hostile["platform_payload"] = {"chat_id": PRIVATE_CHAT_ID, "user_id": PRIVATE_USER_ID}
        hostile["note"] = SENSITIVE_SENTINEL
        rejected = await run_shadow_gateway_e2e_loop(control, hostile)
        canceled = await control.handle(
            {
                "operation": "cancel_transaction",
                "workflow_id": workflow_id,
                "update": {"event_type": "cancel_transaction", "event_id": "runtime_event_cancel_phase7_integration"},
            }
        )
        await env.client.get_workflow_handle(workflow_id).result()
        history = await env.client.get_workflow_handle(workflow_id).fetch_history()
        rendered, raw_events = history_text_and_bytes(history)

        assert first_ops == [
            "start_transaction",
            "query_transaction",
            "query_transaction",
            "reconcile_delivery_ack",
            "query_transaction",
            "reconcile_delivery_ack",
            "query_transaction",
        ]
        assert first["ok"] is True
        assert first["start_status"] == "started"
        assert first["ack_results"] == [
            {"target_id": "runtime_delivery_0", "surface": "final_text", "status": "sent", "ack_status": "applied"},
            {
                "target_id": "runtime_delivery_1",
                "surface": "rich_card",
                "status": "acknowledged",
                "ack_status": "applied",
            },
        ]
        assert first["final_snapshot"]["delivery_statuses"] == {
            "runtime_delivery_0": "sent",
            "runtime_delivery_1": "acknowledged",
        }
        assert duplicate["start_status"] == "running"
        assert duplicate["ack_results"] == [
            {"target_id": "runtime_delivery_0", "surface": "final_text", "status": "sent", "ack_status": "duplicate"},
            {
                "target_id": "runtime_delivery_1",
                "surface": "rich_card",
                "status": "acknowledged",
                "ack_status": "duplicate",
            },
        ]
        assert after_duplicate["snapshot"]["applied_event_count"] == first["final_snapshot"]["applied_event_count"]
        assert rejected["error_code"] == "invalid_publication"
        assert canceled["snapshot"]["status"] == "canceled"
        for value in (first, duplicate, after_duplicate, rejected, canceled):
            assert_no_forbidden_material(value)
        for forbidden in FORBIDDEN_SENTINELS:
            assert forbidden not in rendered
            assert forbidden.encode() not in raw_events
    finally:
        await close_real_worker(env, worker)


@pytest.mark.asyncio
async def test_phase7_loop_rejects_missing_temporal_delivery_target_without_inventing_slot_or_history() -> None:
    from flowweaver_runtime_client.gateway_shadow_e2e_loop import run_shadow_gateway_e2e_loop

    env, worker, control = await open_real_worker()
    workflow_id = "runtime_tx_phase7_missing_integration"
    publication = make_publication(
        workflow_id=workflow_id,
        delivery_count=1,
        updates=[
            {
                "event_type": "record_delivery_ack",
                "delivery_key": "runtime_event_delivery_ack_phase7_missing_integration",
                "surface": "final_text",
                "target_kind": "delivery",
                "target_id": "runtime_delivery_1",
                "status": "sent",
            }
        ],
    )
    try:
        rejected = await run_shadow_gateway_e2e_loop(control, publication)
        after = await control.handle({"operation": "query_transaction", "workflow_id": workflow_id})
        canceled = await control.handle(
            {
                "operation": "cancel_transaction",
                "workflow_id": workflow_id,
                "update": {"event_type": "cancel_transaction", "event_id": "runtime_event_cancel_phase7_missing_integration"},
            }
        )
        await env.client.get_workflow_handle(workflow_id).result()
        history = await env.client.get_workflow_handle(workflow_id).fetch_history()
        rendered, raw_events = history_text_and_bytes(history)

        assert rejected == {
            "ok": False,
            "loop_version": "flowweaver.gateway_shadow_e2e_loop.v0",
            "operation": "gateway_shadow_e2e_loop",
            "workflow_id": workflow_id,
            "transaction_id": workflow_id,
            "error_code": "delivery_target_mismatch",
            "side_effects": [],
        }
        assert [call["operation"] for call in control.calls[:2]] == ["start_transaction", "query_transaction"]
        assert "reconcile_delivery_ack" not in [call["operation"] for call in control.calls]
        assert after["snapshot"]["delivery_statuses"] == {"runtime_delivery_0": "planned"}
        assert after["snapshot"]["applied_event_count"] == 0
        assert canceled["snapshot"]["status"] == "canceled"
        for value in (rejected, after, canceled):
            assert_no_forbidden_material(value)
        assert "runtime_delivery_1" not in rendered
        assert b"runtime_delivery_1" not in raw_events
    finally:
        await close_real_worker(env, worker)
