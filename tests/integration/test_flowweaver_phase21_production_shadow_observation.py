"""RED integration tests for FlowWeaver Phase 21 production-shadow observation."""

from __future__ import annotations

import asyncio
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

from flowweaver_runtime_client.control_surface import FlowWeaverRuntimeControlSurface  # noqa: E402
from flowweaver_runtime_client.runtime_client import FlowWeaverRuntimeClient  # noqa: E402
from flowweaver_temporal_poc import FLOWWEAVER_TEMPORAL_TASK_QUEUE  # noqa: E402
from flowweaver_temporal_poc.activities import deliver_artifact, execute_agent_turn, validate_claim_check_ref  # noqa: E402
from flowweaver_temporal_poc.workflows import FlowWeaverTransactionWorkflow  # noqa: E402
from gateway.flowweaver_production_shadow_observation import (  # noqa: E402
    PRODUCTION_SHADOW_OBSERVATION_SUCCESS_VERDICT,
    observe_gateway_turn_for_flowweaver_production_shadow,
    production_shadow_observation_policy_from_config,
)

pytestmark = pytest.mark.integration

PRIVATE_CHAT_ID = "oc_" + "phase21_private_chat"
PRIVATE_USER_ID = "ou_" + "phase21_private_user"
PRIVATE_MESSAGE_ID = "om_" + "phase21_private_message"
RAW_PROMPT_VALUE = "raw prompt phase21 value"
RAW_TOOL_OUTPUT_VALUE = "raw " + "tool output phase21 value"
CARD_JSON_VALUE = '{"type":"card_json"}'
MEDIA_PATH_VALUE = "/tmp/phase21-private.png"
CALLBACK_VALUE = "callback payload phase21 value"
RAW_EXCEPTION_VALUE = "ValueError: raw exception phase21 value"
SENSITIVE_SENTINEL = "unsafe-" + "token" + "-phase21"
FORBIDDEN_SENTINELS = (
    PRIVATE_CHAT_ID,
    PRIVATE_USER_ID,
    PRIVATE_MESSAGE_ID,
    RAW_PROMPT_VALUE,
    RAW_TOOL_OUTPUT_VALUE,
    CARD_JSON_VALUE,
    MEDIA_PATH_VALUE,
    CALLBACK_VALUE,
    RAW_EXCEPTION_VALUE,
    SENSITIVE_SENTINEL,
)


class RecordingControlSurface:
    def __init__(self, wrapped: FlowWeaverRuntimeControlSurface) -> None:
        self.wrapped = wrapped
        self.calls: list[dict[str, object]] = []

    async def handle(self, request: object) -> dict[str, object]:
        assert type(request) is dict
        self.calls.append(copy.deepcopy(request))
        return await self.wrapped.handle(request)


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


async def cancel_if_started(control: RecordingControlSurface, workflow_id: object, event_id: str) -> None:
    if type(workflow_id) is not str:
        return
    await control.handle(
        {
            "operation": "cancel_transaction",
            "workflow_id": workflow_id,
            "update": {"event_type": "cancel_transaction", "event_id": event_id},
        }
    )


def history_text_and_bytes(history: Any) -> tuple[str, bytes]:
    rendered = history.to_json() if hasattr(history, "to_json") else repr(history.to_json_dict())
    raw_events = b"".join(event.SerializeToString() for event in history.events)
    return rendered, raw_events


def config(enabled: bool, *, allowlist: list[str] | None = None, timeout_ms: int = 250) -> dict[str, object]:
    return {
        "flowweaver": {
            "production_shadow_observation": {
                "enabled": enabled,
                "platform_allowlist": list(allowlist or []),
                "timeout_ms": timeout_ms,
            }
        }
    }


def gateway_turn(**overrides: object) -> dict[str, object]:
    turn: dict[str, object] = {
        "platform": "sachima",
        "session_key": f"sachima:{PRIVATE_CHAT_ID}:{PRIVATE_USER_ID}",
        "session_id": "sess_phase21_private_source",
        "message_id": PRIVATE_MESSAGE_ID,
        "turn_started_at_ns": 1_777_777_777_000_001,
        "turn_sequence": 1,
        "history_length": 7,
        "api_call_count": 2,
        "final_text_present": True,
        "rich_card_count": 1,
        "media_count": 0,
        "raw_prompt": RAW_PROMPT_VALUE,
        "tool_output": RAW_TOOL_OUTPUT_VALUE,
        "card_json": CARD_JSON_VALUE,
        "media_path": MEDIA_PATH_VALUE,
        "callback_payload": CALLBACK_VALUE,
        "raw_exception": RAW_EXCEPTION_VALUE,
        "credential": SENSITIVE_SENTINEL,
    }
    turn.update(overrides)
    return turn


def assert_no_forbidden_material(value: object) -> None:
    rendered = repr(value).lower()
    for forbidden in FORBIDDEN_SENTINELS:
        assert forbidden.lower() not in rendered


@pytest.mark.asyncio
async def test_phase21_observes_real_reduced_gateway_turn_against_local_worker_without_delivery_ack_invention() -> None:
    env, worker, control = await open_real_worker()
    workflow_ids: list[str] = []
    try:
        enabled = production_shadow_observation_policy_from_config(config(True, allowlist=["sachima"]), platform="sachima")
        disabled = production_shadow_observation_policy_from_config(config(False, allowlist=["sachima"]), platform="sachima")

        observed = await observe_gateway_turn_for_flowweaver_production_shadow(
            gateway_turn=gateway_turn(turn_sequence=1),
            runtime_control_surface=control,
            shadow_policy=enabled,
        )
        workflow_ids.append(str(observed["workflow_id"]))
        before_disabled_count = len(control.calls)
        disabled_result = await observe_gateway_turn_for_flowweaver_production_shadow(
            gateway_turn=gateway_turn(turn_sequence=2),
            runtime_control_surface=control,
            shadow_policy=disabled,
        )
        after_disabled_count = len(control.calls)
        existing_query = await control.handle({"operation": "query_transaction", "workflow_id": observed["workflow_id"]})
        history = await env.client.get_workflow_handle(str(observed["workflow_id"])).fetch_history()
        rendered, raw_events = history_text_and_bytes(history)

        assert observed["ok"] is True
        assert observed["verdict"] == PRODUCTION_SHADOW_OBSERVATION_SUCCESS_VERDICT
        assert observed["runtime_call_counts"] == {"start_transaction": 1, "query_transaction": 1}
        assert disabled_result["status"] == "disabled"
        assert after_disabled_count == before_disabled_count
        assert existing_query["operation"] == "query_transaction"
        assert existing_query["snapshot"]["transaction_id"] == observed["workflow_id"]
        operations = [call["operation"] for call in control.calls]
        assert operations[:2] == ["start_transaction", "query_transaction"]
        assert "reconcile_delivery_ack" not in operations
        start_payload = control.calls[0]["start_payload"]
        assert start_payload["record_counts"] == {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 2}
        assert observed["delivery"] == {"ack_updates": 0, "control": "unchanged"}
        for value in (observed, disabled_result, existing_query, control.calls):
            assert_no_forbidden_material(value)
        for forbidden in FORBIDDEN_SENTINELS:
            assert forbidden not in rendered
            assert forbidden.encode("utf-8") not in raw_events
    finally:
        for index, workflow_id in enumerate(dict.fromkeys(workflow_ids)):
            await cancel_if_started(control, workflow_id, f"runtime_event_cancel_phase21_shadow_{index}")
        await asyncio.gather(
            *(env.client.get_workflow_handle(workflow_id).result() for workflow_id in dict.fromkeys(workflow_ids)),
            return_exceptions=True,
        )
        await close_real_worker(env, worker)
