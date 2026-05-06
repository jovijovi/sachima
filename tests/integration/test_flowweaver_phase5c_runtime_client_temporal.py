"""Integration coverage for the FlowWeaver Phase 5C runtime client facade."""

from __future__ import annotations

import ast
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
WORKFLOW_SOURCE = PHASE5B_SRC / "flowweaver_temporal_poc" / "workflows.py"
for path in (PHASE5C_SRC, PHASE5B_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from flowweaver_temporal_poc import FLOWWEAVER_TEMPORAL_TASK_QUEUE  # noqa: E402
from flowweaver_temporal_poc.payloads import (  # noqa: E402
    CancelTransactionUpdate,
    DeliveryAckUpdate,
    HumanDecisionUpdate,
    ResumeUserInputUpdate,
    RuntimeStartPayload,
    build_runtime_start_payload,
)
from flowweaver_temporal_poc.workflows import FlowWeaverTransactionWorkflow  # noqa: E402

from flowweaver_runtime_client.runtime_client import FlowWeaverRuntimeClient  # noqa: E402
from flowweaver_runtime_client.tool_adapter import FlowWeaverRuntimeToolAdapter  # noqa: E402


pytestmark = pytest.mark.integration

PRIVATE_CHAT_ID = "oc_" + "phase5c_private_chat"
PRIVATE_USER_ID = "ou_" + "phase5c_private_user"
SENSITIVE_SENTINEL = "unsafe-" + "token" + "-phase5c"
FORBIDDEN_HISTORY_SENTINELS = (PRIVATE_CHAT_ID, PRIVATE_USER_ID, SENSITIVE_SENTINEL)


def make_start_payload(*, count: int = 2) -> RuntimeStartPayload:
    return build_runtime_start_payload(
        transaction_id="runtime_tx_replay_corpus",
        idempotency_key="runtime_event_start_runtime_tx_replay_corpus",
        entry_count=count,
        record_counts={"transactions": 1, "intents": count, "artifacts": count, "deliveries": count},
        allowed_runtime_events=(
            "start_transaction",
            "record_operation",
            "publish_artifact",
            "plan_delivery",
            "record_delivery_ack",
            "approve_intent",
            "reject_intent",
            "cancel_transaction",
            "resume_after_user_input",
        ),
        claim_check_policy={
            "mode": "references_only",
            "allowed_reference_fields": ("ref", "kind", "count", "size", "checksum_hint"),
            "forbidden_material": (
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
            ),
        },
    )


async def query_until_running(facade: FlowWeaverRuntimeClient, workflow_id: str) -> dict[str, object]:
    last_error: Exception | None = None
    for _ in range(20):
        try:
            result = await facade.query_snapshot(workflow_id)
        except Exception as exc:  # Temporal can reject queries before first workflow task completes.
            last_error = exc
            await asyncio.sleep(0.05)
            continue
        if result["snapshot"].get("status") == "running":
            return result
        await asyncio.sleep(0.05)
    if last_error is not None:
        raise last_error
    raise AssertionError("workflow did not reach running state")


def history_text_and_bytes(history: Any) -> tuple[str, bytes]:
    rendered = history.to_json() if hasattr(history, "to_json") else repr(history.to_json_dict())
    raw_events = b"".join(event.SerializeToString() for event in history.events)
    return rendered, raw_events


@pytest.mark.asyncio
async def test_phase5c_facade_starts_queries_updates_and_preserves_history_no_leak() -> None:
    env = await WorkflowEnvironment.start_time_skipping()
    worker = Worker(env.client, task_queue=FLOWWEAVER_TEMPORAL_TASK_QUEUE, workflows=[FlowWeaverTransactionWorkflow])
    await env.__aenter__()
    await worker.__aenter__()
    workflow_id = "runtime_tx_phase5c_integration"
    facade = FlowWeaverRuntimeClient(env.client, temporal_address="localhost:7233")
    try:
        started = await facade.start_transaction(make_start_payload(count=2), workflow_id=workflow_id)
        assert started["workflow_id"] == workflow_id
        snapshot_result = await query_until_running(facade, workflow_id)
        assert snapshot_result["snapshot"]["status"] == "running"

        ack = await facade.record_delivery_ack(
            workflow_id,
            DeliveryAckUpdate(
                delivery_key="runtime_event_delivery_ack_phase5c",
                surface="final_text",
                target_kind="delivery",
                target_id="runtime_delivery_0",
                status="sent",
            ),
        )
        approved = await facade.approve_intent(
            workflow_id,
            HumanDecisionUpdate(
                event_id="runtime_event_approve_phase5c",
                intent_id="runtime_intent_0",
                decision="approved",
                reason_ref="claim_ref_reason_phase5c_approve",
            ),
        )
        rejected = await facade.reject_intent(
            workflow_id,
            HumanDecisionUpdate(
                event_id="runtime_event_reject_phase5c",
                intent_id="runtime_intent_1",
                decision="rejected",
                reason_ref="claim_ref_reason_phase5c_reject",
            ),
        )
        resumed = await facade.resume_after_user_input(
            workflow_id,
            ResumeUserInputUpdate(event_id="runtime_event_resume_phase5c", input_ref="claim_ref_user_input_phase5c"),
        )
        canceled = await facade.cancel_transaction(
            workflow_id,
            CancelTransactionUpdate(event_id="runtime_event_cancel_phase5c", reason_ref=None),
        )
        result = await env.client.get_workflow_handle(workflow_id).result()
        history = await env.client.get_workflow_handle(workflow_id).fetch_history()
        rendered, raw_events = history_text_and_bytes(history)

        assert ack["status"] == "applied"
        assert approved["status"] == "applied"
        assert rejected["status"] == "applied"
        assert resumed["status"] == "applied"
        assert canceled["snapshot"]["status"] == "canceled"
        assert result["status"] == "canceled"
        for forbidden in FORBIDDEN_HISTORY_SENTINELS:
            assert forbidden not in rendered
            assert forbidden.encode() not in raw_events
    finally:
        await worker.__aexit__(None, None, None)
        await env.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_hostile_adapter_input_is_rejected_before_temporal_history_can_record_it() -> None:
    env = await WorkflowEnvironment.start_time_skipping()
    worker = Worker(env.client, task_queue=FLOWWEAVER_TEMPORAL_TASK_QUEUE, workflows=[FlowWeaverTransactionWorkflow])
    await env.__aenter__()
    await worker.__aenter__()
    workflow_id = "runtime_tx_phase5c_negative"
    facade = FlowWeaverRuntimeClient(env.client, temporal_address="localhost:7233")
    adapter = FlowWeaverRuntimeToolAdapter(facade)
    try:
        await facade.start_transaction(make_start_payload(count=1), workflow_id=workflow_id)
        await query_until_running(facade, workflow_id)
        rejected = await adapter.handle(
            {
                "operation": "record_delivery_ack",
                "workflow_id": workflow_id,
                "update": {
                    "event_type": "record_delivery_ack",
                    "delivery_key": "runtime_event_delivery_ack_negative",
                    "surface": "final_text",
                    "target_kind": "delivery",
                    "target_id": "runtime_delivery_0",
                    "status": "sent",
                    "platform_payload": {"chat_id": PRIVATE_CHAT_ID, "user_id": PRIVATE_USER_ID},
                    "note": SENSITIVE_SENTINEL,
                },
            }
        )
        assert rejected == {"ok": False, "operation": "record_delivery_ack", "error_code": "unsafe_request"}

        await facade.cancel_transaction(workflow_id, CancelTransactionUpdate(event_id="runtime_event_cancel_negative", reason_ref=None))
        await env.client.get_workflow_handle(workflow_id).result()
        history = await env.client.get_workflow_handle(workflow_id).fetch_history()
        rendered, raw_events = history_text_and_bytes(history)
        for forbidden in FORBIDDEN_HISTORY_SENTINELS:
            assert forbidden not in repr(rejected)
            assert forbidden not in rendered
            assert forbidden.encode() not in raw_events
    finally:
        await worker.__aexit__(None, None, None)
        await env.__aexit__(None, None, None)


def test_phase5c_and_phase5b_workflow_code_use_no_payload_carrying_signals() -> None:
    phase5c_sources = [
        PHASE5C_SRC / "flowweaver_runtime_client" / "runtime_client.py",
        PHASE5C_SRC / "flowweaver_runtime_client" / "tool_adapter.py",
        PHASE5C_SRC / "flowweaver_runtime_client" / "mcp_server.py",
    ]
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8") + "\n" + "\n".join(
        path.read_text(encoding="utf-8") for path in phase5c_sources
    )
    assert "@workflow.signal" not in source
    assert ".signal(" not in source
    assert "signal_with_start" not in source


def test_phase5c_runtime_client_code_does_not_import_gateway_or_platform_adapters() -> None:
    sources = [
        PHASE5C_SRC / "flowweaver_runtime_client" / "runtime_client.py",
        PHASE5C_SRC / "flowweaver_runtime_client" / "tool_adapter.py",
        PHASE5C_SRC / "flowweaver_runtime_client" / "mcp_server.py",
    ]
    tree = ast.parse("\n".join(path.read_text(encoding="utf-8") for path in sources))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)

    assert not any(name == "gateway" or name.startswith("gateway.") for name in imports)
    assert not any("gateway.platforms" in name or "gateway.run" in name for name in imports)
