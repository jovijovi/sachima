"""Integration tests for FlowWeaver Phase 31 controlled agent execution Activity."""

from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from typing import Any

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from gateway.flowweaver_agent_execution_activity import (
    FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SNAPSHOT_TYPE,
    FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_TASK_QUEUE,
    FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION,
    FlowWeaverAgentExecutionActivityWorkflow,
    build_execute_agent_turn_activity,
    build_flowweaver_agent_execution_request,
    validate_flowweaver_agent_execution_snapshot,
)
from gateway.flowweaver_temporal_stub_activity_orchestration import validate_claim_check_ref_activity

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]

PRIVATE_CHAT_ID = "oc_" + "phase31_private_chat"
PRIVATE_USER_ID = "ou_" + "phase31_private_user"
PRIVATE_MESSAGE_ID = "om_" + "phase31_private_message"
RAW_PROMPT_VALUE = "raw prompt phase31 private value"
RAW_TOOL_VALUE = "raw " + "tool output phase31 private value"
CARD_JSON_VALUE = '{"type":"card_json","body":"phase31"}'
MEDIA_PATH_VALUE = "/tmp/phase31-private.png"
CALLBACK_VALUE = "callback payload phase31 private value"
RAW_EXCEPTION_VALUE = "RuntimeError: raw phase31 exception value"
SENSITIVE_SENTINEL = "unsafe-" + "token" + "-phase31"
BEARER_VALUE = "Bearer " + "phase31-private"
OPENAI_KEY_VALUE = "sk-" + "phase31-private"
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
    b'"callback_payload"',
    b'"platform_id"',
    b'"chat_id"',
    b'"user_id"',
    b'"message_id"',
    b'"credential"',
    b'"secret"',
)


class RecordingExecutor:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def __call__(self, request: dict[str, object]) -> dict[str, object]:
        self.calls.append(copy.deepcopy(request))
        return copy.deepcopy(self.response)


def claim_ref(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "ref": "claim_ref_phase31_0",
        "kind": "agent_input",
        "count": 1,
        "size": 128,
        "checksum_hint": "sha256:" + ("a" * 64),
    }
    value.update(overrides)
    return value


def start_request(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "transaction_id": "runtime_tx_phase31_temporal",
        "workflow_id": "runtime_tx_phase31_temporal",
        "intent_id": "runtime_intent_0",
        "claim_check_ref": claim_ref(),
        "artifact_ref": "runtime_artifact_0",
    }
    kwargs.update(overrides)
    return build_flowweaver_agent_execution_request(**kwargs)  # type: ignore[arg-type]


def executor_success(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "status": "completed",
        "artifact_ref": "runtime_artifact_0",
        "raw_output": RAW_TOOL_VALUE,
        "tool_call_count": 2,
        "output_item_count": 1,
    }
    value.update(overrides)
    return value


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


async def open_worker(executor: RecordingExecutor) -> tuple[WorkflowEnvironment, Worker]:
    env = await WorkflowEnvironment.start_time_skipping()
    worker = Worker(
        env.client,
        task_queue=FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_TASK_QUEUE,
        workflows=[FlowWeaverAgentExecutionActivityWorkflow],
        activities=[validate_claim_check_ref_activity, build_execute_agent_turn_activity(executor=executor)],
    )
    await env.__aenter__()
    await worker.__aenter__()
    return env, worker


async def close_worker(env: WorkflowEnvironment, worker: Worker) -> None:
    await worker.__aexit__(None, None, None)
    await env.__aexit__(None, None, None)


async def query_until_terminal(handle: Any) -> dict[str, object]:
    last_error: Exception | None = None
    for _ in range(30):
        try:
            snapshot = await handle.query(FlowWeaverAgentExecutionActivityWorkflow.query_snapshot)
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(0.05)
            continue
        if snapshot.get("status") in {"agent_execution_completed", "rejected", "timed_out", "cancelled"}:
            return validate_flowweaver_agent_execution_snapshot(snapshot)
        await asyncio.sleep(0.05)
    if last_error is not None:
        raise last_error
    raise AssertionError("workflow did not reach terminal agent execution status")


@pytest.mark.asyncio
async def test_phase31_local_temporal_worker_executes_injected_executor_and_history_remains_sanitized() -> None:
    executor = RecordingExecutor(executor_success())
    env, worker = await open_worker(executor)
    try:
        request = start_request()
        handle = await env.client.start_workflow(
            FlowWeaverAgentExecutionActivityWorkflow.run,
            request,
            id=str(request["workflow_id"]),
            task_queue=FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_TASK_QUEUE,
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
            "activity_sequence",
            "counts",
            "execution_digest",
            "error_code",
            "side_effects",
        ]
        assert queried["type"] == FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SNAPSHOT_TYPE
        assert queried["version"] == FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION
        assert queried["phase"] == "phase31"
        assert queried["transaction_id"] == "runtime_tx_phase31_temporal"
        assert queried["workflow_id"] == "runtime_tx_phase31_temporal"
        assert queried["status"] == "agent_execution_completed"
        assert queried["intent_statuses"] == {"runtime_intent_0": "executed"}
        assert queried["artifact_refs"] == ["runtime_artifact_0"]
        assert [item["name"] for item in queried["activity_sequence"]] == [
            "validate_claim_check_ref",
            "execute_agent_turn",
        ]
        assert [item["status"] for item in queried["activity_sequence"]] == ["validated", "executed"]
        assert queried["counts"] == {"activities": 2, "artifacts": 1, "executor_calls": 1, "tool_calls": 2}
        assert str(queried["execution_digest"]).startswith("sha256:")
        assert queried["error_code"] is None
        assert queried["side_effects"] == []
        assert "delivery_refs" not in queried
        assert "delivery_ack_updates" not in queried

        assert len(executor.calls) == 1
        assert executor.calls[0]["claim_check_ref"] == "claim_ref_phase31_0"
        assert_no_raw_values(executor.calls[0])
        assert_no_raw_values(queried)

        history = await handle.fetch_history()
        history_json, _ = history_text_and_bytes(history)
        assert history_json.index("validate_claim_check_ref") < history_json.index("execute_agent_turn")
        assert_history_has_no_raw_material(history)
    finally:
        await close_worker(env, worker)


@pytest.mark.asyncio
async def test_phase31_local_temporal_worker_maps_executor_timeout_to_safe_snapshot_without_delivery_effects() -> None:
    executor = RecordingExecutor(executor_success(status="timed_out", output_item_count=0))
    env, worker = await open_worker(executor)
    try:
        request = start_request(
            transaction_id="runtime_tx_phase31_timeout",
            workflow_id="runtime_tx_phase31_timeout",
        )
        handle = await env.client.start_workflow(
            FlowWeaverAgentExecutionActivityWorkflow.run,
            request,
            id=str(request["workflow_id"]),
            task_queue=FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_TASK_QUEUE,
        )
        snapshot = await handle.result()
        safe = validate_flowweaver_agent_execution_snapshot(snapshot)

        assert len(executor.calls) == 1
        assert safe["status"] == "timed_out"
        assert safe["artifact_refs"] == []
        assert safe["counts"] == {"activities": 2, "artifacts": 0, "executor_calls": 1, "tool_calls": 2}
        assert safe["error_code"] == "executor_timeout"
        assert "delivery_refs" not in safe
        assert "delivery_ack_updates" not in safe
        assert_no_raw_values(safe)
        assert_history_has_no_raw_material(await handle.fetch_history())
    finally:
        await close_worker(env, worker)
