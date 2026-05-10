"""Integration tests for FlowWeaver Phase 33 narrow AI FLOW pilot."""

from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from typing import Any

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from gateway.flowweaver_agent_execution_activity import build_execute_agent_turn_activity
from gateway.flowweaver_ai_flow_pilot import (
    FLOWWEAVER_AI_FLOW_PILOT_SNAPSHOT_TYPE,
    FLOWWEAVER_AI_FLOW_PILOT_SUCCESS_VERDICT,
    FLOWWEAVER_AI_FLOW_PILOT_TASK_QUEUE,
    FLOWWEAVER_AI_FLOW_PILOT_VERSION,
    FlowWeaverAIFlowPilotWorkflow,
    build_flowweaver_ai_flow_pilot_activity_wrappers,
    build_flowweaver_ai_flow_pilot_request,
    validate_flowweaver_ai_flow_pilot_snapshot,
)
from gateway.flowweaver_delivery_activity import build_deliver_artifact_activity
from gateway.flowweaver_temporal_stub_activity_orchestration import validate_claim_check_ref_activity

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]

PRIVATE_CHAT_ID = "oc_" + "phase33_private_chat"
PRIVATE_USER_ID = "ou_" + "phase33_private_user"
PRIVATE_MESSAGE_ID = "om_" + "phase33_private_message"
RAW_PROMPT_VALUE = "raw prompt phase33 private value"
RAW_TOOL_VALUE = "raw " + "tool output phase33 private value"
CARD_JSON_VALUE = '{"type":"card_json","body":"phase33"}'
MEDIA_PATH_VALUE = "/tmp/phase33-private.png"
CALLBACK_VALUE = "callback payload phase33 private value"
RAW_EXCEPTION_VALUE = "RuntimeError: raw phase33 exception value"
SENSITIVE_SENTINEL = "unsafe-" + "token" + "-phase33"
BEARER_VALUE = "Bearer " + "phase33-private"
OPENAI_KEY_VALUE = "sk-" + "phase33-private"
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
    "execution_digest",
    "delivery_digest",
    "decision_packet",
    "error_code",
    "side_effects",
]
EXPECTED_SEPARATE_APPROVALS = [
    "production_gateway_wiring",
    "production_delivery_enablement",
    "production_agent_execution",
    "production_config_write",
    "gateway_restart",
    "platform_adapter_mutation",
    "gateway_owned_worker_lifecycle",
]
EXPECTED_DECISION_PACKET_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "pilot_status",
    "evidence",
    "rollback",
    "separate_approvals_required",
    "unresolved_risks",
    "side_effects",
]
EXPECTED_EVIDENCE_FIELDS = [
    "phase31_executed",
    "phase32_delivered",
    "history_no_leak_checked",
    "result_no_leak_checked",
    "progress_snapshots_sanitized",
    "side_effects_absent",
]
EXPECTED_ROLLBACK_FIELDS = ["kill_switch_ref", "steps", "operator_required", "side_effects"]


class RecordingExecutor:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []
        self.raw_internal_material = RAW_PROMPT_VALUE

    async def __call__(self, request: dict[str, object]) -> dict[str, object]:
        self.calls.append(copy.deepcopy(request))
        return copy.deepcopy(self.response)


class RecordingDeliverySurface:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []
        self.raw_internal_material = CARD_JSON_VALUE

    async def __call__(self, request: dict[str, object]) -> dict[str, object]:
        self.calls.append(copy.deepcopy(request))
        return copy.deepcopy(self.response)


class BlockingDeliverySurface(RecordingDeliverySurface):
    def __init__(self, response: dict[str, object]) -> None:
        super().__init__(response)
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def __call__(self, request: dict[str, object]) -> dict[str, object]:
        self.calls.append(copy.deepcopy(request))
        self.entered.set()
        await self.release.wait()
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


@activity.defn(name="validate_claim_check_ref")
async def validate_claim_check_ref_with_unknown_success_error(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "activity": "validate_claim_check_ref",
        "status": "validated",
        "claim_ref": payload["claim_check_ref"]["ref"],
        "error_code": "unknown_non_null_error_code",
        "side_effects": [],
    }


async def validate_claim_check_ref_raises_raw_exception(payload: dict[str, Any]) -> dict[str, Any]:
    raise RuntimeError(RAW_EXCEPTION_VALUE)


def claim_ref(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "ref": "claim_ref_phase33_temporal_0",
        "kind": "agent_input",
        "count": 1,
        "size": 128,
        "checksum_hint": "sha256:" + ("a" * 64),
    }
    value.update(overrides)
    return value


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


def start_request(*, transaction_id: str = "runtime_tx_phase33_temporal", enabled: bool = True) -> dict[str, object]:
    return build_flowweaver_ai_flow_pilot_request(
        transaction_id=transaction_id,
        workflow_id=transaction_id,
        intent_id="runtime_intent_0",
        claim_check_ref=claim_ref(),
        artifact_ref="runtime_artifact_0",
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


def canonical_temporal_snapshot(snapshot: object) -> dict[str, object]:
    if type(snapshot) is not dict:
        raise AssertionError("expected Temporal-decoded snapshot dict")
    surface_state = snapshot["surface_state"]
    counts = snapshot["counts"]
    decision_packet = snapshot["decision_packet"]
    if type(surface_state) is not dict or type(counts) is not dict or type(decision_packet) is not dict:
        raise AssertionError("expected Temporal-decoded nested snapshot dicts")
    evidence = decision_packet["evidence"]
    rollback = decision_packet["rollback"]
    if type(evidence) is not dict or type(rollback) is not dict:
        raise AssertionError("expected Temporal-decoded decision packet dicts")
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
        "executor_calls": counts["executor_calls"],
        "tool_calls": counts["tool_calls"],
        "ack_updates": counts["ack_updates"],
        "ack_applied": counts["ack_applied"],
        "ack_duplicates": counts["ack_duplicates"],
        "ack_rejected": counts["ack_rejected"],
    }
    canonical["decision_packet"] = {
        key: decision_packet[key]
        for key in EXPECTED_DECISION_PACKET_FIELDS
    }
    canonical["decision_packet"]["evidence"] = {key: evidence[key] for key in EXPECTED_EVIDENCE_FIELDS}
    canonical["decision_packet"]["rollback"] = {key: rollback[key] for key in EXPECTED_ROLLBACK_FIELDS}
    return validate_flowweaver_ai_flow_pilot_snapshot(canonical)


async def open_worker(
    executor: RecordingExecutor,
    surface: RecordingDeliverySurface,
    runtime: RecordingRuntimeControlSurface,
    claim_activity: object = validate_claim_check_ref_activity,
) -> tuple[WorkflowEnvironment, Worker]:
    env = await WorkflowEnvironment.start_time_skipping()
    worker = Worker(
        env.client,
        task_queue=FLOWWEAVER_AI_FLOW_PILOT_TASK_QUEUE,
        workflows=[FlowWeaverAIFlowPilotWorkflow],
        activities=build_flowweaver_ai_flow_pilot_activity_wrappers(
            claim_activity=claim_activity,
            execute_activity=build_execute_agent_turn_activity(executor=executor),
            deliver_activity=build_deliver_artifact_activity(delivery_surface=surface, runtime_control_surface=runtime),
        ),
    )
    await env.__aenter__()
    await worker.__aenter__()
    return env, worker


async def close_worker(env: WorkflowEnvironment, worker: Worker) -> None:
    await worker.__aexit__(None, None, None)
    await env.__aexit__(None, None, None)


async def query_until_terminal(handle: Any) -> dict[str, object]:
    last_error: Exception | None = None
    terminal = {"pilot_completed", "disabled", "agent_execution_failed", "partially_delivered", "timed_out", "cancelled", "rejected"}
    for _ in range(30):
        try:
            snapshot = await handle.query(FlowWeaverAIFlowPilotWorkflow.query_snapshot)
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(0.05)
            continue
        if snapshot.get("status") in terminal:
            return canonical_temporal_snapshot(snapshot)
        await asyncio.sleep(0.05)
    if last_error is not None:
        raise last_error
    raise AssertionError("workflow did not reach terminal AI FLOW pilot status")


@pytest.mark.asyncio
async def test_phase33_local_temporal_worker_composes_agent_execution_delivery_and_decision_packet() -> None:
    executor = RecordingExecutor(executor_success())
    surface = RecordingDeliverySurface(
        surface_success(
            delivery_ack("runtime_delivery_0", "rich_card"),
            delivery_ack("runtime_delivery_1", "final_text"),
        )
    )
    runtime = RecordingRuntimeControlSurface()
    env, worker = await open_worker(executor, surface, runtime)
    try:
        request = start_request()
        handle = await env.client.start_workflow(
            FlowWeaverAIFlowPilotWorkflow.run,
            request,
            id=str(request["workflow_id"]),
            task_queue=FLOWWEAVER_AI_FLOW_PILOT_TASK_QUEUE,
        )
        snapshot = await handle.result()
        queried = await query_until_terminal(handle)

        assert snapshot == queried
        assert list(queried) == EXPECTED_SNAPSHOT_FIELDS
        assert queried["type"] == FLOWWEAVER_AI_FLOW_PILOT_SNAPSHOT_TYPE
        assert queried["version"] == FLOWWEAVER_AI_FLOW_PILOT_VERSION
        assert queried["phase"] == "phase33"
        assert queried["status"] == "pilot_completed"
        assert queried["intent_statuses"] == {"runtime_intent_0": "delivered"}
        assert queried["artifact_refs"] == ["runtime_artifact_0"]
        assert queried["delivery_refs"] == ["runtime_delivery_0", "runtime_delivery_1"]
        assert queried["surface_state"] == {
            "progress_card_sent": False,
            "rich_cards_sent": 1,
            "final_text_sent": True,
            "media_sent": 0,
        }
        assert [item["name"] for item in queried["activity_sequence"]] == [
            "validate_claim_check_ref",
            "execute_agent_turn",
            "deliver_artifact",
        ]
        assert [item["status"] for item in queried["activity_sequence"]] == ["validated", "executed", "delivered"]
        assert queried["counts"] == {
            "activities": 3,
            "artifacts": 1,
            "deliveries": 2,
            "executor_calls": 1,
            "tool_calls": 2,
            "ack_updates": 2,
            "ack_applied": 2,
            "ack_duplicates": 0,
            "ack_rejected": 0,
        }
        decision_packet = queried["decision_packet"]
        assert decision_packet["verdict"] == FLOWWEAVER_AI_FLOW_PILOT_SUCCESS_VERDICT
        assert decision_packet["pilot_status"] == "pilot_completed"
        assert decision_packet["separate_approvals_required"] == EXPECTED_SEPARATE_APPROVALS
        assert decision_packet["rollback"]["operator_required"] is True
        assert "production_enabled" not in repr(decision_packet)
        assert queried["error_code"] is None

        assert len(executor.calls) == 1
        assert len(surface.calls) == 1
        assert len(runtime.calls) == 2
        assert_no_raw_values(executor.calls[0])
        assert_no_raw_values(surface.calls[0])
        assert_no_raw_values(runtime.calls)
        assert_no_raw_values(queried)
        assert_history_has_no_raw_material(await handle.fetch_history())
    finally:
        await close_worker(env, worker)


@pytest.mark.asyncio
async def test_phase33_progress_query_after_agent_success_before_delivery_is_sanitized() -> None:
    executor = RecordingExecutor(executor_success())
    surface = BlockingDeliverySurface(
        surface_success(
            delivery_ack("runtime_delivery_0", "rich_card"),
            delivery_ack("runtime_delivery_1", "final_text"),
        )
    )
    runtime = RecordingRuntimeControlSurface()
    env, worker = await open_worker(executor, surface, runtime)
    try:
        request = start_request(transaction_id="runtime_tx_phase33_progress_after_agent")
        handle = await env.client.start_workflow(
            FlowWeaverAIFlowPilotWorkflow.run,
            request,
            id=str(request["workflow_id"]),
            task_queue=FLOWWEAVER_AI_FLOW_PILOT_TASK_QUEUE,
        )
        await asyncio.wait_for(surface.entered.wait(), timeout=5)
        progress = canonical_temporal_snapshot(await handle.query(FlowWeaverAIFlowPilotWorkflow.query_snapshot))

        assert progress["status"] == "running"
        assert progress["intent_statuses"] == {"runtime_intent_0": "executed"}
        assert [item["name"] for item in progress["activity_sequence"]] == [
            "validate_claim_check_ref",
            "execute_agent_turn",
        ]
        assert progress["decision_packet"]["pilot_status"] == "running"
        assert progress["decision_packet"]["verdict"] == "not_ready_for_production_enablement"
        assert progress["decision_packet"]["evidence"]["phase31_executed"] is True
        assert progress["decision_packet"]["evidence"]["phase32_delivered"] is False
        assert progress["error_code"] is None
        assert_no_raw_values(progress)

        surface.release.set()
        final_snapshot = canonical_temporal_snapshot(await handle.result())
        assert final_snapshot["status"] == "pilot_completed"
        assert_history_has_no_raw_material(await handle.fetch_history())
    finally:
        surface.release.set()
        await close_worker(env, worker)


@pytest.mark.asyncio
async def test_phase33_default_off_policy_makes_zero_executor_delivery_or_runtime_calls() -> None:
    executor = RecordingExecutor(executor_success())
    surface = RecordingDeliverySurface(surface_success(delivery_ack("runtime_delivery_0", "rich_card")))
    runtime = RecordingRuntimeControlSurface()
    env, worker = await open_worker(executor, surface, runtime)
    try:
        request = start_request(transaction_id="runtime_tx_phase33_disabled", enabled=False)
        handle = await env.client.start_workflow(
            FlowWeaverAIFlowPilotWorkflow.run,
            request,
            id=str(request["workflow_id"]),
            task_queue=FLOWWEAVER_AI_FLOW_PILOT_TASK_QUEUE,
        )
        snapshot = await handle.result()
        safe = canonical_temporal_snapshot(snapshot)

        assert executor.calls == []
        assert surface.calls == []
        assert runtime.calls == []
        assert safe["status"] == "disabled"
        assert safe["intent_statuses"] == {"runtime_intent_0": "disabled"}
        assert safe["artifact_refs"] == []
        assert safe["delivery_refs"] == []
        assert safe["activity_sequence"] == []
        assert safe["counts"] == {
            "activities": 0,
            "artifacts": 0,
            "deliveries": 0,
            "executor_calls": 0,
            "tool_calls": 0,
            "ack_updates": 0,
            "ack_applied": 0,
            "ack_duplicates": 0,
            "ack_rejected": 0,
        }
        assert safe["decision_packet"]["pilot_status"] == "disabled"
        assert safe["decision_packet"]["verdict"] == "not_ready_for_production_enablement"
        assert safe["error_code"] == "pilot_policy_disabled"
        assert_no_raw_values(safe)
        assert_history_has_no_raw_material(await handle.fetch_history())
    finally:
        await close_worker(env, worker)


@pytest.mark.asyncio
async def test_phase33_claim_success_with_unknown_error_code_fails_closed_before_executor() -> None:
    executor = RecordingExecutor(executor_success())
    surface = RecordingDeliverySurface(surface_success(delivery_ack("runtime_delivery_0", "rich_card")))
    runtime = RecordingRuntimeControlSurface()
    env, worker = await open_worker(
        executor,
        surface,
        runtime,
        claim_activity=validate_claim_check_ref_with_unknown_success_error,
    )
    try:
        request = start_request(transaction_id="runtime_tx_phase33_claim_unknown_error")
        handle = await env.client.start_workflow(
            FlowWeaverAIFlowPilotWorkflow.run,
            request,
            id=str(request["workflow_id"]),
            task_queue=FLOWWEAVER_AI_FLOW_PILOT_TASK_QUEUE,
        )
        safe = canonical_temporal_snapshot(await handle.result())

        assert executor.calls == []
        assert surface.calls == []
        assert runtime.calls == []
        assert safe["status"] == "rejected"
        assert safe["intent_statuses"] == {"runtime_intent_0": "rejected"}
        assert safe["activity_sequence"] == [
            {"name": "validate_claim_check_ref", "status": "rejected", "error_code": "invalid_claim_ref", "side_effects": []}
        ]
        assert safe["counts"] == {
            "activities": 1,
            "artifacts": 0,
            "deliveries": 0,
            "executor_calls": 0,
            "tool_calls": 0,
            "ack_updates": 0,
            "ack_applied": 0,
            "ack_duplicates": 0,
            "ack_rejected": 0,
        }
        assert safe["decision_packet"]["pilot_status"] == "rejected"
        assert safe["decision_packet"]["evidence"]["phase31_executed"] is False
        assert safe["decision_packet"]["evidence"]["phase32_delivered"] is False
        assert safe["error_code"] == "invalid_claim_ref"
        assert_no_raw_values(safe)
        assert_history_has_no_raw_material(await handle.fetch_history())
    finally:
        await close_worker(env, worker)


@pytest.mark.asyncio
async def test_phase33_claim_activity_exception_returns_sanitized_non_ready_snapshot_without_history_leak() -> None:
    executor = RecordingExecutor(executor_success())
    surface = RecordingDeliverySurface(surface_success(delivery_ack("runtime_delivery_0", "rich_card")))
    runtime = RecordingRuntimeControlSurface()
    env, worker = await open_worker(
        executor,
        surface,
        runtime,
        claim_activity=validate_claim_check_ref_raises_raw_exception,
    )
    try:
        request = start_request(transaction_id="runtime_tx_phase33_claim_exception")
        handle = await env.client.start_workflow(
            FlowWeaverAIFlowPilotWorkflow.run,
            request,
            id=str(request["workflow_id"]),
            task_queue=FLOWWEAVER_AI_FLOW_PILOT_TASK_QUEUE,
        )
        safe = canonical_temporal_snapshot(await handle.result())

        assert executor.calls == []
        assert surface.calls == []
        assert runtime.calls == []
        assert safe["status"] == "rejected"
        assert safe["decision_packet"]["pilot_status"] == "rejected"
        assert safe["decision_packet"]["verdict"] == "not_ready_for_production_enablement"
        assert safe["activity_sequence"] == [
            {"name": "validate_claim_check_ref", "status": "rejected", "error_code": "invalid_claim_ref", "side_effects": []}
        ]
        assert safe["error_code"] == "invalid_claim_ref"
        assert_no_raw_values(safe)
        assert_history_has_no_raw_material(await handle.fetch_history())
    finally:
        await close_worker(env, worker)


@pytest.mark.asyncio
async def test_phase33_agent_failure_skips_delivery_and_keeps_rollback_decision_packet() -> None:
    executor = RecordingExecutor(executor_success(status="timed_out", output_item_count=0))
    surface = RecordingDeliverySurface(surface_success(delivery_ack("runtime_delivery_0", "rich_card")))
    runtime = RecordingRuntimeControlSurface()
    env, worker = await open_worker(executor, surface, runtime)
    try:
        request = start_request(transaction_id="runtime_tx_phase33_timeout")
        handle = await env.client.start_workflow(
            FlowWeaverAIFlowPilotWorkflow.run,
            request,
            id=str(request["workflow_id"]),
            task_queue=FLOWWEAVER_AI_FLOW_PILOT_TASK_QUEUE,
        )
        safe = canonical_temporal_snapshot(await handle.result())

        assert len(executor.calls) == 1
        assert surface.calls == []
        assert runtime.calls == []
        assert safe["status"] == "timed_out"
        assert safe["intent_statuses"] == {"runtime_intent_0": "timed_out"}
        assert [item["name"] for item in safe["activity_sequence"]] == ["validate_claim_check_ref", "execute_agent_turn"]
        assert safe["counts"]["executor_calls"] == 1
        assert safe["counts"]["deliveries"] == 0
        assert safe["decision_packet"]["pilot_status"] == "timed_out"
        assert safe["decision_packet"]["verdict"] == "not_ready_for_production_enablement"
        assert safe["decision_packet"]["evidence"]["phase32_delivered"] is False
        assert safe["decision_packet"]["rollback"]["steps"] == [
            "disable_pilot_policy",
            "preserve_canonical_branch",
            "rerun_clean_verification",
        ]
        assert safe["error_code"] == "executor_timeout"
        assert_no_raw_values(safe)
        assert_history_has_no_raw_material(await handle.fetch_history())
    finally:
        await close_worker(env, worker)


@pytest.mark.asyncio
async def test_phase33_ack_replay_duplicate_results_are_idempotent_and_decision_packet_remains_non_production() -> None:
    executor = RecordingExecutor(executor_success())
    surface = RecordingDeliverySurface(
        surface_success(
            delivery_ack("runtime_delivery_0", "rich_card"),
            delivery_ack("runtime_delivery_1", "final_text"),
        )
    )
    runtime = RecordingRuntimeControlSurface(duplicate_refs={"runtime_delivery_0", "runtime_delivery_1"})
    env, worker = await open_worker(executor, surface, runtime)
    try:
        request = start_request(transaction_id="runtime_tx_phase33_duplicate_ack")
        handle = await env.client.start_workflow(
            FlowWeaverAIFlowPilotWorkflow.run,
            request,
            id=str(request["workflow_id"]),
            task_queue=FLOWWEAVER_AI_FLOW_PILOT_TASK_QUEUE,
        )
        safe = canonical_temporal_snapshot(await handle.result())

        assert safe["status"] == "pilot_completed"
        assert safe["counts"]["ack_applied"] == 0
        assert safe["counts"]["ack_duplicates"] == 2
        assert safe["decision_packet"]["verdict"] == FLOWWEAVER_AI_FLOW_PILOT_SUCCESS_VERDICT
        assert "production_enabled" not in repr(safe)
        assert_no_raw_values(safe)
        assert_history_has_no_raw_material(await handle.fetch_history())
    finally:
        await close_worker(env, worker)


@pytest.mark.asyncio
async def test_phase33_cancelled_executor_maps_to_sanitized_rollback_snapshot() -> None:
    executor = RecordingExecutor(executor_success(status="cancelled", output_item_count=0))
    surface = RecordingDeliverySurface(surface_success(delivery_ack("runtime_delivery_0", "rich_card")))
    runtime = RecordingRuntimeControlSurface()
    env, worker = await open_worker(executor, surface, runtime)
    try:
        request = start_request(transaction_id="runtime_tx_phase33_cancelled")
        handle = await env.client.start_workflow(
            FlowWeaverAIFlowPilotWorkflow.run,
            request,
            id=str(request["workflow_id"]),
            task_queue=FLOWWEAVER_AI_FLOW_PILOT_TASK_QUEUE,
        )
        safe = canonical_temporal_snapshot(await handle.result())

        assert safe["status"] == "cancelled"
        assert surface.calls == []
        assert runtime.calls == []
        assert safe["error_code"] == "executor_cancelled"
        assert safe["decision_packet"]["pilot_status"] == "cancelled"
        assert safe["decision_packet"]["verdict"] == "not_ready_for_production_enablement"
        assert safe["decision_packet"]["rollback"]["operator_required"] is True
        assert_no_raw_values(safe)
        assert_history_has_no_raw_material(await handle.fetch_history())
    finally:
        await close_worker(env, worker)
