"""Integration tests for FlowWeaver Phase 32 delivery Activity and ACK reconciliation."""

from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from typing import Any

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from gateway.flowweaver_agent_execution_activity import (
    build_flowweaver_agent_execution_request,
    execute_controlled_agent_turn,
)
from gateway.flowweaver_delivery_activity import (
    FLOWWEAVER_DELIVERY_ACTIVITY_SNAPSHOT_TYPE,
    FLOWWEAVER_DELIVERY_ACTIVITY_TASK_QUEUE,
    FLOWWEAVER_DELIVERY_ACTIVITY_VERSION,
    FlowWeaverDeliveryActivityWorkflow,
    build_deliver_artifact_activity,
    build_flowweaver_delivery_activity_request,
    validate_flowweaver_delivery_activity_snapshot,
)

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]

PRIVATE_CHAT_ID = "oc_" + "phase32_private_chat"
PRIVATE_USER_ID = "ou_" + "phase32_private_user"
PRIVATE_MESSAGE_ID = "om_" + "phase32_private_message"
RAW_PROMPT_VALUE = "raw prompt phase32 private value"
RAW_TOOL_VALUE = "raw " + "tool output phase32 private value"
CARD_JSON_VALUE = '{"type":"card_json","body":"phase32"}'
MEDIA_PATH_VALUE = "/tmp/phase32-private.png"
CALLBACK_VALUE = "callback payload phase32 private value"
RAW_EXCEPTION_VALUE = "RuntimeError: raw phase32 exception value"
SENSITIVE_SENTINEL = "unsafe-" + "token" + "-phase32"
BEARER_VALUE = "Bearer " + "phase32-private"
OPENAI_KEY_VALUE = "sk-" + "phase32-private"
FORBIDDEN_SENTINELS = (
    PRIVATE_CHAT_ID,
    PRIVATE_USER_ID,
    PRIVATE_MESSAGE_ID,
    RAW_PROMPT_VALUE,
    RAW_TOOL_VALUE,
    CARD_JSON_VALUE,
    MEDIA_PATH_VALUE,
    CALLBACK_VALUE,
    RAW_EXCEPTION_VALUE,
    SENSITIVE_SENTINEL,
    BEARER_VALUE,
    OPENAI_KEY_VALUE,
)
FORBIDDEN_HISTORY_KEY_PATTERNS = (
    b'"raw_prompt"',
    b'"tool_output"',
    b'"raw_output"',
    b'"card_json"',
    b'"media_path"',
    b'"media_bytes"',
    b'"callback_payload"',
    b'"delivery_ack_payload"',
    b'"platform_id"',
    b'"chat_id"',
    b'"user_id"',
    b'"message_id"',
    b'"credential"',
    b'"secret"',
)
EXPECTED_SNAPSHOT_FIELDS = [
    "type",
    "version",
    "phase",
    "transaction_id",
    "workflow_id",
    "status",
    "intent_statuses",
    "artifact_refs",
    "delivery_refs",
    "surface_state",
    "activity_sequence",
    "counts",
    "delivery_digest",
    "error_code",
    "side_effects",
]


class RecordingDeliverySurface:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []
        self.raw_internal_material = CARD_JSON_VALUE

    async def __call__(self, request: dict[str, object]) -> dict[str, object]:
        self.calls.append(copy.deepcopy(request))
        return copy.deepcopy(self.response)


class RecordingRuntimeControlSurface:
    def __init__(self, *, duplicate_refs: set[str] | None = None) -> None:
        self.duplicate_refs = duplicate_refs or set()
        self.calls: list[dict[str, object]] = []
        self.raw_internal_material = CALLBACK_VALUE

    async def reconcile_delivery_ack(self, update: dict[str, object]) -> dict[str, object]:
        self.calls.append(copy.deepcopy(update))
        delivery_ref = str(update["delivery_ref"])
        status = "duplicate" if delivery_ref in self.duplicate_refs else "applied"
        return {
            "status": status,
            "delivery_ref": delivery_ref,
            "surface": update["surface"],
            "error_code": None,
            "side_effects": [],
        }


def claim_ref(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "ref": "claim_ref_phase32_temporal_0",
        "kind": "agent_input",
        "count": 1,
        "size": 128,
        "checksum_hint": "sha256:" + ("a" * 64),
    }
    value.update(overrides)
    return value


async def agent_result(transaction_id: str = "runtime_tx_phase32_temporal") -> dict[str, object]:
    request = build_flowweaver_agent_execution_request(
        transaction_id=transaction_id,
        workflow_id=transaction_id,
        intent_id="runtime_intent_0",
        claim_check_ref=claim_ref(),
        artifact_ref="runtime_artifact_0",
    )
    return await execute_controlled_agent_turn(
        execution_request=request,
        validated_claim={
            "activity": "validate_claim_check_ref",
            "status": "validated",
            "claim_ref": "claim_ref_phase32_temporal_0",
            "error_code": None,
            "side_effects": [],
        },
        executor=RecordingDeliverySurface(
            {
                "status": "completed",
                "artifact_ref": "runtime_artifact_0",
                "raw_output": RAW_TOOL_VALUE,
                "tool_call_count": 2,
                "output_item_count": 1,
            }
        ),
    )


def delivery_slots() -> list[dict[str, object]]:
    return [
        {
            "delivery_ref": "runtime_delivery_0",
            "surface": "rich_card",
            "artifact_ref": "runtime_artifact_0",
            "required": True,
        },
        {
            "delivery_ref": "runtime_delivery_1",
            "surface": "final_text",
            "artifact_ref": "runtime_artifact_0",
            "required": True,
        },
    ]


def delivery_ack(delivery_ref: str, surface: str, status: str = "sent") -> dict[str, object]:
    suffix = delivery_ref.removeprefix("runtime_delivery_")
    return {
        "delivery_ref": delivery_ref,
        "surface": surface,
        "status": status,
        "ack_ref": f"runtime_event_delivery_ack_{suffix}",
    }


def surface_success(*acks: dict[str, object], status: str = "completed") -> dict[str, object]:
    return {"status": status, "ack_updates": list(acks)}


async def start_request(*, transaction_id: str = "runtime_tx_phase32_temporal", enabled: bool = True) -> dict[str, object]:
    return build_flowweaver_delivery_activity_request(
        transaction_id=transaction_id,
        workflow_id=transaction_id,
        intent_id="runtime_intent_0",
        agent_execution_result=await agent_result(transaction_id),
        initialized_delivery_slots=delivery_slots(),
        enabled=enabled,
    )


def assert_no_raw_values(value: object) -> None:
    rendered = repr(value).lower()
    for marker in FORBIDDEN_SENTINELS:
        assert marker.lower() not in rendered
    assert "traceback" not in rendered
    assert "runtimeerror" not in rendered
    assert "temporalio.exceptions" not in rendered


def history_text_and_bytes(history: Any) -> tuple[str, bytes]:
    rendered = history.to_json() if hasattr(history, "to_json") else repr(history.to_json_dict())
    raw_events = b"".join(event.SerializeToString() for event in history.events)
    return rendered, raw_events


def assert_history_has_no_raw_material(history: Any) -> None:
    rendered, raw_events = history_text_and_bytes(history)
    rendered_bytes = rendered.encode("utf-8", "ignore")
    for marker in FORBIDDEN_SENTINELS:
        assert marker not in rendered
        assert marker.encode() not in raw_events
    for pattern in FORBIDDEN_HISTORY_KEY_PATTERNS:
        assert pattern not in rendered_bytes
        assert pattern not in raw_events


async def open_worker(
    surface: RecordingDeliverySurface,
    runtime: RecordingRuntimeControlSurface,
) -> tuple[WorkflowEnvironment, Worker]:
    env = await WorkflowEnvironment.start_time_skipping()
    worker = Worker(
        env.client,
        task_queue=FLOWWEAVER_DELIVERY_ACTIVITY_TASK_QUEUE,
        workflows=[FlowWeaverDeliveryActivityWorkflow],
        activities=[build_deliver_artifact_activity(delivery_surface=surface, runtime_control_surface=runtime)],
    )
    await env.__aenter__()
    await worker.__aenter__()
    return env, worker


async def close_worker(env: WorkflowEnvironment, worker: Worker) -> None:
    await worker.__aexit__(None, None, None)
    await env.__aexit__(None, None, None)


def canonical_temporal_snapshot(snapshot: object) -> dict[str, object]:
    if type(snapshot) is not dict:
        raise AssertionError("expected Temporal-decoded snapshot dict")
    surface_state = snapshot["surface_state"]
    counts = snapshot["counts"]
    if type(surface_state) is not dict or type(counts) is not dict:
        raise AssertionError("expected Temporal-decoded snapshot nested dicts")
    activity_sequence = []
    for item in snapshot["activity_sequence"]:
        if type(item) is not dict:
            raise AssertionError("expected Temporal-decoded activity item dict")
        activity_sequence.append(
            {
                "name": item["name"],
                "status": item["status"],
                "error_code": item["error_code"],
                "side_effects": item["side_effects"],
            }
        )
    canonical = {key: snapshot[key] for key in EXPECTED_SNAPSHOT_FIELDS}
    canonical["surface_state"] = {
        "progress_card_sent": surface_state["progress_card_sent"],
        "rich_cards_sent": surface_state["rich_cards_sent"],
        "final_text_sent": surface_state["final_text_sent"],
        "media_sent": surface_state["media_sent"],
    }
    canonical["activity_sequence"] = activity_sequence
    canonical["counts"] = {
        "activities": counts["activities"],
        "artifacts": counts["artifacts"],
        "deliveries": counts["deliveries"],
        "ack_updates": counts["ack_updates"],
        "ack_applied": counts["ack_applied"],
        "ack_duplicates": counts["ack_duplicates"],
        "ack_rejected": counts["ack_rejected"],
    }
    return validate_flowweaver_delivery_activity_snapshot(canonical)


async def query_until_terminal(handle: Any) -> dict[str, object]:
    last_error: Exception | None = None
    for _ in range(30):
        try:
            snapshot = await handle.query(FlowWeaverDeliveryActivityWorkflow.query_snapshot)
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(0.05)
            continue
        if snapshot.get("status") in {"delivery_completed", "partially_delivered", "disabled", "rejected", "timed_out", "cancelled"}:
            return canonical_temporal_snapshot(snapshot)
        await asyncio.sleep(0.05)
    if last_error is not None:
        raise last_error
    raise AssertionError("workflow did not reach terminal delivery status")


@pytest.mark.asyncio
async def test_phase32_local_temporal_worker_delivers_artifact_reconciles_acks_and_history_remains_sanitized() -> None:
    surface = RecordingDeliverySurface(
        surface_success(
            delivery_ack("runtime_delivery_0", "rich_card"),
            delivery_ack("runtime_delivery_1", "final_text"),
        )
    )
    runtime = RecordingRuntimeControlSurface()
    env, worker = await open_worker(surface, runtime)
    try:
        request = await start_request()
        handle = await env.client.start_workflow(
            FlowWeaverDeliveryActivityWorkflow.run,
            request,
            id=str(request["workflow_id"]),
            task_queue=FLOWWEAVER_DELIVERY_ACTIVITY_TASK_QUEUE,
        )
        snapshot = await handle.result()
        queried = await query_until_terminal(handle)

        assert snapshot == queried
        assert list(queried) == [
            "type",
            "version",
            "phase",
            "transaction_id",
            "workflow_id",
            "status",
            "intent_statuses",
            "artifact_refs",
            "delivery_refs",
            "surface_state",
            "activity_sequence",
            "counts",
            "delivery_digest",
            "error_code",
            "side_effects",
        ]
        assert queried["type"] == FLOWWEAVER_DELIVERY_ACTIVITY_SNAPSHOT_TYPE
        assert queried["version"] == FLOWWEAVER_DELIVERY_ACTIVITY_VERSION
        assert queried["phase"] == "phase32"
        assert queried["transaction_id"] == "runtime_tx_phase32_temporal"
        assert queried["workflow_id"] == "runtime_tx_phase32_temporal"
        assert queried["status"] == "delivery_completed"
        assert queried["intent_statuses"] == {"runtime_intent_0": "delivered"}
        assert queried["artifact_refs"] == ["runtime_artifact_0"]
        assert queried["delivery_refs"] == ["runtime_delivery_0", "runtime_delivery_1"]
        assert queried["surface_state"] == {
            "progress_card_sent": False,
            "rich_cards_sent": 1,
            "final_text_sent": True,
            "media_sent": 0,
        }
        assert [item["name"] for item in queried["activity_sequence"]] == ["deliver_artifact"]
        assert [item["status"] for item in queried["activity_sequence"]] == ["delivered"]
        assert queried["counts"] == {
            "activities": 1,
            "artifacts": 1,
            "deliveries": 2,
            "ack_updates": 2,
            "ack_applied": 2,
            "ack_duplicates": 0,
            "ack_rejected": 0,
        }
        assert str(queried["delivery_digest"]).startswith("sha256:")
        assert queried["error_code"] is None
        assert queried["side_effects"] == []

        assert len(surface.calls) == 1
        assert len(runtime.calls) == 2
        assert_no_raw_values(surface.calls[0])
        assert_no_raw_values(runtime.calls)
        assert_no_raw_values(queried)

        history = await handle.fetch_history()
        history_json, _ = history_text_and_bytes(history)
        assert "deliver_artifact" in history_json
        assert_history_has_no_raw_material(history)
    finally:
        await close_worker(env, worker)


@pytest.mark.asyncio
async def test_phase32_local_temporal_worker_preserves_disabled_policy_without_delivery_calls() -> None:
    surface = RecordingDeliverySurface(
        surface_success(
            delivery_ack("runtime_delivery_0", "rich_card"),
            delivery_ack("runtime_delivery_1", "final_text"),
        )
    )
    runtime = RecordingRuntimeControlSurface()
    env, worker = await open_worker(surface, runtime)
    try:
        request = await start_request(transaction_id="runtime_tx_phase32_disabled", enabled=False)
        handle = await env.client.start_workflow(
            FlowWeaverDeliveryActivityWorkflow.run,
            request,
            id=str(request["workflow_id"]),
            task_queue=FLOWWEAVER_DELIVERY_ACTIVITY_TASK_QUEUE,
        )
        snapshot = await handle.result()
        safe = canonical_temporal_snapshot(snapshot)

        assert surface.calls == []
        assert runtime.calls == []
        assert safe["status"] == "disabled"
        assert safe["intent_statuses"] == {"runtime_intent_0": "disabled"}
        assert safe["delivery_refs"] == []
        assert safe["surface_state"] == {
            "progress_card_sent": False,
            "rich_cards_sent": 0,
            "final_text_sent": False,
            "media_sent": 0,
        }
        assert safe["counts"] == {
            "activities": 1,
            "artifacts": 1,
            "deliveries": 0,
            "ack_updates": 0,
            "ack_applied": 0,
            "ack_duplicates": 0,
            "ack_rejected": 0,
        }
        assert safe["error_code"] == "delivery_policy_disabled"
        assert_no_raw_values(safe)
        assert_history_has_no_raw_material(await handle.fetch_history())
    finally:
        await close_worker(env, worker)
