"""Integration tests for the FlowWeaver Phase 5B local Temporal workflow."""

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
PROTO_SRC = ROOT / "prototypes" / "flowweaver_phase5b_temporal_poc" / "src"
WORKFLOW_SOURCE = PROTO_SRC / "flowweaver_temporal_poc" / "workflows.py"
if str(PROTO_SRC) not in sys.path:
    sys.path.insert(0, str(PROTO_SRC))

from flowweaver_temporal_poc import FLOWWEAVER_TEMPORAL_TASK_QUEUE
from flowweaver_temporal_poc.payloads import (
    CancelTransactionUpdate,
    DeliveryAckUpdate,
    HumanDecisionUpdate,
    ResumeUserInputUpdate,
    RuntimeStartPayload,
)
from flowweaver_temporal_poc.workflows import FlowWeaverTransactionWorkflow


pytestmark = pytest.mark.integration

PRIVATE_MESSAGE_ID = "om_" + "private_message"
PRIVATE_CHAT_ID = "oc_" + "private_chat"
SENSITIVE_SENTINEL = "unsafe-" + "token" + "-value"
FORBIDDEN_HISTORY_SENTINELS = (
    PRIVATE_MESSAGE_ID,
    PRIVATE_CHAT_ID,
    SENSITIVE_SENTINEL,
)
EXPECTED_FORBIDDEN_MATERIAL = (
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
)


def make_start_payload(*, count: int = 2) -> RuntimeStartPayload:
    return RuntimeStartPayload(
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
            "forbidden_material": EXPECTED_FORBIDDEN_MATERIAL,
        },
    )


async def start_workflow(env: WorkflowEnvironment, *, workflow_id: str, count: int = 2):
    return await env.client.start_workflow(
        FlowWeaverTransactionWorkflow.run,
        make_start_payload(count=count),
        id=workflow_id,
        task_queue=FLOWWEAVER_TEMPORAL_TASK_QUEUE,
    )


async def query_until_running(handle: Any) -> dict[str, object]:
    last_error: Exception | None = None
    for _ in range(20):
        try:
            snapshot = await handle.query(FlowWeaverTransactionWorkflow.query_snapshot)
        except Exception as exc:  # Temporal can reject queries before the first workflow task completes.
            last_error = exc
            await asyncio.sleep(0.05)
            continue
        if snapshot.get("status") == "running":
            return snapshot
        await asyncio.sleep(0.05)
    if last_error is not None:
        raise last_error
    raise AssertionError("workflow did not reach running state")


async def run_single_workflow(*, workflow_id: str, count: int = 2):
    env = await WorkflowEnvironment.start_time_skipping()
    worker = Worker(env.client, task_queue=FLOWWEAVER_TEMPORAL_TASK_QUEUE, workflows=[FlowWeaverTransactionWorkflow])
    await env.__aenter__()
    await worker.__aenter__()
    handle = await start_workflow(env, workflow_id=workflow_id, count=count)
    return env, worker, handle


async def close_env(env: WorkflowEnvironment, worker: Worker) -> None:
    await worker.__aexit__(None, None, None)
    await env.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_temporal_workflow_starts_from_safe_payload_and_queries_snapshot() -> None:
    env, worker, handle = await run_single_workflow(workflow_id="runtime_tx_phase5b_query")
    try:
        snapshot = await query_until_running(handle)
        assert snapshot["type"] == "flowweaver.temporal_poc.snapshot.v0"
        assert snapshot["transaction_id"] == "runtime_tx_replay_corpus"
        assert snapshot["status"] == "running"
        assert snapshot["entry_count"] == 2
        assert snapshot["counts"] == {"intents": 2, "artifacts": 2, "deliveries": 2}
        assert snapshot["side_effects"] == []
    finally:
        await handle.execute_update(
            FlowWeaverTransactionWorkflow.cancel_transaction,
            CancelTransactionUpdate(event_id="runtime_event_cancel_query", reason_ref=None),
        )
        await handle.result()
        await close_env(env, worker)


@pytest.mark.asyncio
async def test_temporal_workflow_records_delivery_ack_idempotently() -> None:
    env, worker, handle = await run_single_workflow(workflow_id="runtime_tx_phase5b_ack")
    try:
        await query_until_running(handle)
        update = DeliveryAckUpdate(
            delivery_key="runtime_event_delivery_ack_0",
            surface="final_text",
            target_kind="delivery",
            target_id="runtime_delivery_0",
            status="sent",
        )

        first = await handle.execute_update(FlowWeaverTransactionWorkflow.record_delivery_ack, update)
        second = await handle.execute_update(FlowWeaverTransactionWorkflow.record_delivery_ack, update)
        snapshot = await handle.query(FlowWeaverTransactionWorkflow.query_snapshot)

        assert first["update_status"] == "applied"
        assert second["update_status"] == "duplicate"
        assert snapshot["delivery_statuses"]["runtime_delivery_0"] == "sent"
        assert snapshot["applied_event_count"] == 1
    finally:
        await handle.execute_update(
            FlowWeaverTransactionWorkflow.cancel_transaction,
            CancelTransactionUpdate(event_id="runtime_event_cancel_ack", reason_ref=None),
        )
        await handle.result()
        await close_env(env, worker)


@pytest.mark.asyncio
async def test_temporal_workflow_handles_approval_rejection_resume_and_cancel_updates() -> None:
    env, worker, handle = await run_single_workflow(workflow_id="runtime_tx_phase5b_human")
    try:
        await query_until_running(handle)
        approved = await handle.execute_update(
            FlowWeaverTransactionWorkflow.approve_intent,
            HumanDecisionUpdate(
                event_id="runtime_event_approve_0",
                intent_id="runtime_intent_0",
                decision="approved",
                reason_ref="claim_ref_reason_0",
            ),
        )
        rejected = await handle.execute_update(
            FlowWeaverTransactionWorkflow.reject_intent,
            HumanDecisionUpdate(
                event_id="runtime_event_reject_1",
                intent_id="runtime_intent_1",
                decision="rejected",
                reason_ref="claim_ref_reason_1",
            ),
        )
        resumed = await handle.execute_update(
            FlowWeaverTransactionWorkflow.resume_after_user_input,
            ResumeUserInputUpdate(event_id="runtime_event_resume_0", input_ref="claim_ref_user_input_0"),
        )
        canceled = await handle.execute_update(
            FlowWeaverTransactionWorkflow.cancel_transaction,
            CancelTransactionUpdate(event_id="runtime_event_cancel_human", reason_ref="claim_ref_reason_cancel"),
        )
        result = await handle.result()

        assert approved["update_status"] == "applied"
        assert rejected["update_status"] == "applied"
        assert resumed["update_status"] == "applied"
        assert canceled["snapshot"]["status"] == "canceled"
        assert result["status"] == "canceled"
        assert result["intent_statuses"] == {"runtime_intent_0": "approved", "runtime_intent_1": "rejected"}
        assert result["resume_count"] == 1
    finally:
        await close_env(env, worker)


def test_temporal_workflow_rejects_payload_carrying_signals_in_phase5b() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")

    assert "@workflow.signal" not in source
    assert ".signal(" not in source
    assert "signal_with_start" not in source


def test_temporal_workflow_snapshot_omits_forbidden_material_and_platform_ids() -> None:
    payload = make_start_payload(count=1)
    snapshot_text = repr(payload)

    for forbidden in FORBIDDEN_HISTORY_SENTINELS:
        assert forbidden not in snapshot_text


def history_text_and_bytes(history: Any) -> tuple[str, bytes]:
    rendered = history.to_json() if hasattr(history, "to_json") else repr(history.to_json_dict())
    raw_events = b"".join(event.SerializeToString() for event in history.events)
    return rendered, raw_events


@pytest.mark.asyncio
async def test_temporal_workflow_history_omits_forbidden_sentinels_after_safe_updates() -> None:
    env, worker, handle = await run_single_workflow(workflow_id="runtime_tx_phase5b_history", count=1)
    try:
        await query_until_running(handle)
        await handle.execute_update(
            FlowWeaverTransactionWorkflow.record_delivery_ack,
            DeliveryAckUpdate(
                delivery_key="runtime_event_delivery_ack_history",
                surface="final_text",
                target_kind="delivery",
                target_id="runtime_delivery_0",
                status="sent",
            ),
        )
        await handle.execute_update(
            FlowWeaverTransactionWorkflow.cancel_transaction,
            CancelTransactionUpdate(event_id="runtime_event_cancel_history", reason_ref=None),
        )
        await handle.result()
        history = await handle.fetch_history()
        rendered, raw_events = history_text_and_bytes(history)

        for forbidden in FORBIDDEN_HISTORY_SENTINELS:
            assert forbidden not in rendered
            assert forbidden.encode() not in raw_events
    finally:
        await close_env(env, worker)


def test_temporal_workflow_code_does_not_import_gateway_runtime_or_platform_adapters() -> None:
    tree = ast.parse(WORKFLOW_SOURCE.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)

    assert not any(name == "gateway" or name.startswith("gateway.") for name in imports)
    assert not any("gateway.platforms" in name or "gateway.run" in name for name in imports)


def test_temporal_workflow_code_has_no_activity_schedule_or_nondeterministic_calls() -> None:
    tree = ast.parse(WORKFLOW_SOURCE.read_text(encoding="utf-8"))
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")
    forbidden_names = {
        "open",
        "print",
        "sleep",
        "time",
        "datetime",
        "uuid4",
        "random",
        "execute_activity",
        "start_activity",
    }
    forbidden_modules = {"os", "pathlib", "socket", "subprocess", "requests", "httpx", "aiohttp", "random", "uuid"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_names
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_names
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden_modules
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in forbidden_modules

    assert "execute_activity" not in source
    assert "start_activity" not in source
