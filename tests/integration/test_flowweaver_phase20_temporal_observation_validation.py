"""RED integration tests for FlowWeaver Phase 20 guarded Temporal observation validation."""

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
from gateway.flowweaver_temporal_observation_bridge import (  # noqa: E402
    TEMPORAL_OBSERVATION_SUCCESS_VERDICT,
    observe_gateway_turn_for_flowweaver_temporal,
)
from gateway.flowweaver_temporal_observation_validation import (  # noqa: E402
    TEMPORAL_OBSERVATION_VALIDATION_SUCCESS_VERDICT,
    build_temporal_observation_duplicate_start_report,
    build_temporal_observation_rollback_drill_report,
    build_temporal_observation_validation_report,
)

pytestmark = pytest.mark.integration

PRIVATE_CHAT_ID = "oc_" + "phase20_private_chat"
PRIVATE_USER_ID = "ou_" + "phase20_private_user"
SENSITIVE_SENTINEL = "unsafe-" + "token" + "-phase20"
RAW_PROMPT_VALUE = "raw prompt phase20 value"
RAW_TOOL_OUTPUT_VALUE = "raw " + "tool output phase20 value"
CARD_JSON_VALUE = '{"type":"card_json"}'
MEDIA_PATH_VALUE = "/tmp/phase20-private.png"
CALLBACK_VALUE = "callback payload phase20 value"
RAW_EXCEPTION_VALUE = "ValueError: raw exception phase20 value"
FORBIDDEN_SENTINELS = (
    PRIVATE_CHAT_ID,
    PRIVATE_USER_ID,
    SENSITIVE_SENTINEL,
    RAW_PROMPT_VALUE,
    RAW_TOOL_OUTPUT_VALUE,
    CARD_JSON_VALUE,
    MEDIA_PATH_VALUE,
    CALLBACK_VALUE,
    RAW_EXCEPTION_VALUE,
)


class RecordingControlSurface:
    def __init__(self, wrapped: FlowWeaverRuntimeControlSurface) -> None:
        self.wrapped = wrapped
        self.calls: list[dict[str, object]] = []

    async def handle(self, request: object) -> dict[str, object]:
        assert type(request) is dict
        safe_request = copy.deepcopy(request)
        self.calls.append(safe_request)
        return await self.wrapped.handle(request)


def enabled_policy() -> dict[str, object]:
    return {
        "type": "flowweaver.gateway.temporal_observation_bridge_policy.v0",
        "enabled": True,
        "mode": "controlled_observation",
        "allow_runtime_start": True,
        "allow_runtime_query": True,
        "side_effects": [],
    }


def disabled_policy() -> dict[str, object]:
    policy = enabled_policy()
    policy.update({"enabled": False, "mode": "default_off", "allow_runtime_start": False, "allow_runtime_query": False})
    return policy


def safe_observation(**overrides: object) -> dict[str, object]:
    observation: dict[str, object] = {
        "type": "flowweaver.gateway.temporal_observation.v0",
        "version": "flowweaver.gateway.temporal_observation.v0",
        "source": "controlled_gateway_observation",
        "session_label": "safe_session_phase20",
        "turn_label": "safe_turn_phase20",
        "turn_discriminator": "safe_discriminator_000001_000001",
        "entry_count": 1,
        "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
        "claim_refs": {
            "input_ref": "claim_ref_gateway_observation_input_phase20",
            "artifact_ref": "claim_ref_gateway_observation_artifact_phase20",
            "delivery_ref": "claim_ref_gateway_observation_delivery_phase20",
        },
        "surfaces": ["final_text"],
        "checks": {
            "payloads_absent": True,
            "claim_check_refs_only": True,
            "side_effects_absent": True,
            "source_ids_sanitized": True,
        },
        "side_effects": [],
    }
    observation.update(overrides)
    return observation


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


def assert_no_forbidden_material(value: object) -> None:
    rendered = repr(value).lower()
    for forbidden in FORBIDDEN_SENTINELS:
        assert forbidden.lower() not in rendered


@pytest.mark.asyncio
async def test_phase20_validates_synthetic_gateway_observation_against_real_local_worker() -> None:
    env, worker, control = await open_real_worker()
    workflow_ids: list[str] = []
    try:
        first = await observe_gateway_turn_for_flowweaver_temporal(
            observation=safe_observation(),
            runtime_control_surface=control,
            bridge_policy=enabled_policy(),
        )
        duplicate = await observe_gateway_turn_for_flowweaver_temporal(
            observation=safe_observation(),
            runtime_control_surface=control,
            bridge_policy=enabled_policy(),
        )
        workflow_ids.append(str(first["workflow_id"]))
        disabled_call_count = len(control.calls)
        disabled = await observe_gateway_turn_for_flowweaver_temporal(
            observation=safe_observation(turn_discriminator="safe_discriminator_000001_000099"),
            runtime_control_surface=control,
            bridge_policy=disabled_policy(),
        )
        after_disabled_call_count = len(control.calls)
        existing_query = await control.handle({"operation": "query_transaction", "workflow_id": first["workflow_id"]})
        history = await env.client.get_workflow_handle(str(first["workflow_id"])).fetch_history()
        rendered, raw_events = history_text_and_bytes(history)

        duplicate_report = build_temporal_observation_duplicate_start_report(
            first_bridge_result=first,
            duplicate_bridge_result=duplicate,
        )
        rollback = build_temporal_observation_rollback_drill_report(
            enabled_bridge_result=first,
            disabled_bridge_result=disabled,
            existing_query_result=existing_query,
        )
        validation = build_temporal_observation_validation_report(
            bridge_result=first,
            history_json=rendered,
            history_event_bytes=raw_events,
            duplicate_start_report=duplicate_report,
            rollback_drill=rollback,
        )

        assert first["verdict"] == TEMPORAL_OBSERVATION_SUCCESS_VERDICT
        assert duplicate["start_status"] == "running"
        assert disabled["status"] == "disabled"
        assert after_disabled_call_count == disabled_call_count
        assert validation["verdict"] == TEMPORAL_OBSERVATION_VALIDATION_SUCCESS_VERDICT
        assert validation["history_checks"] == {"json_scanned": True, "event_bytes_scanned": True, "forbidden_material_absent": True}
        assert [call["operation"] for call in control.calls[:4]] == [
            "start_transaction",
            "query_transaction",
            "start_transaction",
            "query_transaction",
        ]
        assert "reconcile_delivery_ack" not in [call["operation"] for call in control.calls]
        for value in (first, duplicate, disabled, existing_query, duplicate_report, rollback, validation):
            assert_no_forbidden_material(value)
        for forbidden in FORBIDDEN_SENTINELS:
            assert forbidden not in rendered
            assert forbidden.encode("utf-8") not in raw_events
    finally:
        for index, workflow_id in enumerate(dict.fromkeys(workflow_ids)):
            await cancel_if_started(control, workflow_id, f"runtime_event_cancel_phase20_validation_{index}")
        await asyncio.gather(
            *(env.client.get_workflow_handle(workflow_id).result() for workflow_id in dict.fromkeys(workflow_ids)),
            return_exceptions=True,
        )
        await close_real_worker(env, worker)


@pytest.mark.asyncio
async def test_phase20_consecutive_synthetic_observations_have_distinct_temporal_transactions() -> None:
    env, worker, control = await open_real_worker()
    workflow_ids: list[str] = []
    try:
        first = await observe_gateway_turn_for_flowweaver_temporal(
            observation=safe_observation(turn_discriminator="safe_discriminator_000002_000001"),
            runtime_control_surface=control,
            bridge_policy=enabled_policy(),
        )
        second = await observe_gateway_turn_for_flowweaver_temporal(
            observation=safe_observation(turn_discriminator="safe_discriminator_000002_000002"),
            runtime_control_surface=control,
            bridge_policy=enabled_policy(),
        )
        workflow_ids.extend([str(first["workflow_id"]), str(second["workflow_id"])])

        assert first["ok"] is True
        assert second["ok"] is True
        assert first["workflow_id"] != second["workflow_id"]
        assert first["workflow_id"].startswith("runtime_tx_gateway_observation_")
        assert second["workflow_id"].startswith("runtime_tx_gateway_observation_")
        assert "safe_discriminator" not in repr(first)
        assert "safe_discriminator" not in repr(second)
        assert_no_forbidden_material(first)
        assert_no_forbidden_material(second)
    finally:
        for index, workflow_id in enumerate(dict.fromkeys(workflow_ids)):
            await cancel_if_started(control, workflow_id, f"runtime_event_cancel_phase20_consecutive_{index}")
        await asyncio.gather(
            *(env.client.get_workflow_handle(workflow_id).result() for workflow_id in dict.fromkeys(workflow_ids)),
            return_exceptions=True,
        )
        await close_real_worker(env, worker)
