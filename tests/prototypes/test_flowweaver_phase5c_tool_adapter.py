"""Runtime facade and tool-adapter tests for FlowWeaver Phase 5C."""

from __future__ import annotations

import asyncio
import ast
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
PHASE5B_SRC = ROOT / "prototypes" / "flowweaver_phase5b_temporal_poc" / "src"
PHASE5C_SRC = ROOT / "prototypes" / "flowweaver_phase5c_runtime_client" / "src"
for path in (PHASE5C_SRC, PHASE5B_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from flowweaver_temporal_poc import FLOWWEAVER_TEMPORAL_TASK_QUEUE
from flowweaver_temporal_poc.payloads import (
    CancelTransactionUpdate,
    DeliveryAckUpdate,
    HumanDecisionUpdate,
    ResumeUserInputUpdate,
    RuntimeStartPayload,
)
from flowweaver_temporal_poc.workflows import FlowWeaverTransactionWorkflow


SAFE_START_PAYLOAD = RuntimeStartPayload(
    transaction_id="runtime_tx_replay_corpus",
    idempotency_key="runtime_event_start_runtime_tx_replay_corpus",
    entry_count=1,
    record_counts={"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
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

SAFE_SNAPSHOT = {
    "type": "flowweaver.temporal_poc.snapshot.v0",
    "version": "flowweaver.temporal_poc.v0",
    "transaction_id": "runtime_tx_replay_corpus",
    "status": "running",
    "entry_count": 1,
    "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
    "counts": {"intents": 1, "artifacts": 1, "deliveries": 1},
    "intent_statuses": {"runtime_intent_0": "pending"},
    "artifact_statuses": {"runtime_artifact_0": "available"},
    "delivery_statuses": {"runtime_delivery_0": "planned"},
    "applied_event_count": 0,
    "resume_count": 0,
    "side_effects": [],
}


class FakeHandle:
    def __init__(self) -> None:
        self.queries: list[Any] = []
        self.updates: list[tuple[Any, Any]] = []
        self.snapshot = dict(SAFE_SNAPSHOT)
        self.update_result = {
            "type": "flowweaver.temporal_poc.update_result.v0",
            "version": "flowweaver.temporal_poc.v0",
            "update_status": "applied",
            "snapshot": dict(SAFE_SNAPSHOT),
            "side_effects": [],
            "tool_output": "drop me",
            "platform_payload": {"chat_id": "oc_" + "private"},
        }

    async def query(self, query_callable: Any) -> dict[str, Any]:
        self.queries.append(query_callable)
        return self.snapshot

    async def execute_update(self, update_callable: Any, update: Any) -> dict[str, Any]:
        self.updates.append((update_callable, update))
        return self.update_result


class FakeTemporalClient:
    def __init__(self) -> None:
        self.handle = FakeHandle()
        self.started: dict[str, Any] | None = None
        self.handles_requested: list[str] = []

    async def start_workflow(self, workflow_run: Any, payload: Any, *, id: str, task_queue: str) -> Any:
        self.started = {"workflow_run": workflow_run, "payload": payload, "id": id, "task_queue": task_queue}
        return SimpleNamespace(id=id)

    def get_workflow_handle(self, workflow_id: str) -> FakeHandle:
        self.handles_requested.append(workflow_id)
        return self.handle


class RuntimeClientThatLeaksValueError:
    async def query_snapshot(self, workflow_id: str) -> dict[str, object]:
        raise ValueError("sec" + "ret")


@pytest.mark.asyncio
async def test_runtime_client_start_transaction_calls_phase5b_workflow_with_validated_payload() -> None:
    from flowweaver_runtime_client.runtime_client import FlowWeaverRuntimeClient

    fake_client = FakeTemporalClient()
    facade = FlowWeaverRuntimeClient(fake_client, temporal_address="localhost:7233")

    result = await facade.start_transaction(SAFE_START_PAYLOAD, workflow_id="runtime_tx_phase5c_start")

    assert fake_client.started is not None
    assert fake_client.started["workflow_run"].__qualname__ == FlowWeaverTransactionWorkflow.run.__qualname__
    assert fake_client.started["payload"] == SAFE_START_PAYLOAD
    assert fake_client.started["id"] == "runtime_tx_phase5c_start"
    assert fake_client.started["task_queue"] == FLOWWEAVER_TEMPORAL_TASK_QUEUE
    assert result["workflow_id"] == "runtime_tx_phase5c_start"
    assert result["transaction_id"] == "runtime_tx_replay_corpus"
    assert result["status"] == "started"


@pytest.mark.asyncio
async def test_runtime_client_query_snapshot_uses_query_method_and_sanitizes_phase5b_snapshot() -> None:
    from flowweaver_runtime_client.runtime_client import FlowWeaverRuntimeClient

    fake_client = FakeTemporalClient()
    fake_client.handle.snapshot.update({"raw_payload": "drop", "chat_id": "oc_" + "private"})
    facade = FlowWeaverRuntimeClient(fake_client, temporal_address="127.0.0.1:7233")

    result = await facade.query_snapshot("runtime_tx_phase5c_query")

    assert fake_client.handles_requested == ["runtime_tx_phase5c_query"]
    assert [query.__qualname__ for query in fake_client.handle.queries] == [
        FlowWeaverTransactionWorkflow.query_snapshot.__qualname__
    ]
    assert result["snapshot"]["status"] == "running"
    rendered = repr(result)
    assert "raw_payload" not in rendered
    assert "chat_id" not in rendered
    assert "oc_private" not in rendered


@pytest.mark.asyncio
async def test_state_changing_operations_call_exact_validated_update_methods() -> None:
    from flowweaver_runtime_client.runtime_client import FlowWeaverRuntimeClient

    fake_client = FakeTemporalClient()
    facade = FlowWeaverRuntimeClient(fake_client, temporal_address="localhost:7233")

    await facade.record_delivery_ack(
        "runtime_tx_phase5c_updates",
        DeliveryAckUpdate(
            delivery_key="runtime_event_delivery_ack_0",
            surface="final_text",
            target_kind="delivery",
            target_id="runtime_delivery_0",
            status="sent",
        ),
    )
    await facade.approve_intent(
        "runtime_tx_phase5c_updates",
        HumanDecisionUpdate(
            event_id="runtime_event_approve_0",
            intent_id="runtime_intent_0",
            decision="approved",
            reason_ref="claim_ref_reason_0",
        ),
    )
    await facade.reject_intent(
        "runtime_tx_phase5c_updates",
        HumanDecisionUpdate(
            event_id="runtime_event_reject_0",
            intent_id="runtime_intent_0",
            decision="rejected",
            reason_ref="claim_ref_reason_1",
        ),
    )
    await facade.resume_after_user_input(
        "runtime_tx_phase5c_updates",
        ResumeUserInputUpdate(event_id="runtime_event_resume_0", input_ref="claim_ref_user_input_0"),
    )
    await facade.cancel_transaction(
        "runtime_tx_phase5c_updates",
        CancelTransactionUpdate(event_id="runtime_event_cancel_0", reason_ref=None),
    )

    assert [call[0].__qualname__ for call in fake_client.handle.updates] == [
        FlowWeaverTransactionWorkflow.record_delivery_ack.__qualname__,
        FlowWeaverTransactionWorkflow.approve_intent.__qualname__,
        FlowWeaverTransactionWorkflow.reject_intent.__qualname__,
        FlowWeaverTransactionWorkflow.resume_after_user_input.__qualname__,
        FlowWeaverTransactionWorkflow.cancel_transaction.__qualname__,
    ]


def test_runtime_client_requires_explicit_local_endpoint_and_rejects_remote_endpoint() -> None:
    from flowweaver_runtime_client.runtime_client import FlowWeaverRuntimeClient

    fake_client = FakeTemporalClient()
    with pytest.raises(ValueError, match="temporal_address_required"):
        FlowWeaverRuntimeClient(fake_client, temporal_address=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="invalid_temporal_address"):
        FlowWeaverRuntimeClient(fake_client, temporal_address="temporal.example.com:7233")


@pytest.mark.asyncio
async def test_tool_adapter_converts_mcp_style_dicts_to_safe_results_without_leaking_errors() -> None:
    from flowweaver_runtime_client.tool_adapter import FlowWeaverRuntimeToolAdapter

    fake_client = FakeTemporalClient()
    adapter = FlowWeaverRuntimeToolAdapter.from_temporal_client(fake_client, temporal_address="localhost:7233")

    result = await adapter.handle(
        {
            "operation": "record_delivery_ack",
            "workflow_id": "runtime_tx_phase5c_adapter",
            "update": {
                "event_type": "record_delivery_ack",
                "delivery_key": "runtime_event_delivery_ack_adapter",
                "surface": "final_text",
                "target_kind": "delivery",
                "target_id": "runtime_delivery_0",
                "status": "sent",
            },
        }
    )

    assert result["ok"] is True
    assert result["operation"] == "record_delivery_ack"
    assert result["workflow_id"] == "runtime_tx_phase5c_adapter"
    assert result["status"] == "applied"
    rendered = repr(result)
    assert "tool_output" not in rendered
    assert "platform_payload" not in rendered
    assert "chat_id" not in rendered

    error = await adapter.handle(
        {
            "operation": "query_snapshot",
            "workflow_id": "runtime_tx_phase5c_adapter",
            "raw_payload": "do not leak this raw exception-shaped detail",
        }
    )
    assert error == {"ok": False, "operation": "query_snapshot", "error_code": "unsafe_request"}
    assert "raw exception" not in repr(error)


@pytest.mark.asyncio
async def test_tool_adapter_maps_unknown_runtime_value_errors_to_stable_error_codes() -> None:
    from flowweaver_runtime_client.tool_adapter import FlowWeaverRuntimeToolAdapter

    adapter = FlowWeaverRuntimeToolAdapter(RuntimeClientThatLeaksValueError())  # type: ignore[arg-type]

    result = await adapter.handle({"operation": "query_snapshot", "workflow_id": "runtime_tx_phase5c_error"})

    assert result == {"ok": False, "operation": "query_snapshot", "error_code": "runtime_error"}
    assert "sec" + "ret" not in repr(result)


@pytest.mark.asyncio
async def test_invoke_flowweaver_runtime_returns_safe_error_when_runtime_creation_fails() -> None:
    from flowweaver_runtime_client.tool_adapter import invoke_flowweaver_runtime

    request = {"operation": "query_snapshot", "workflow_id": "runtime_tx_phase5c_connect_error"}

    invalid_address = await invoke_flowweaver_runtime(request, temporal_address="temporal.example.test:7233")
    assert invalid_address == {
        "ok": False,
        "operation": "query_snapshot",
        "error_code": "invalid_temporal_address",
    }

    def leaking_factory() -> object:
        raise ValueError("sec" + "ret")

    factory_error = await invoke_flowweaver_runtime(request, runtime_client_factory=leaking_factory)
    assert factory_error == {"ok": False, "operation": "query_snapshot", "error_code": "runtime_error"}
    assert "sec" + "ret" not in repr(factory_error)


def test_runtime_client_and_adapter_do_not_start_services_shell_out_or_read_real_config() -> None:
    runtime_source = (PHASE5C_SRC / "flowweaver_runtime_client" / "runtime_client.py").read_text(encoding="utf-8")
    adapter_source = (PHASE5C_SRC / "flowweaver_runtime_client" / "tool_adapter.py").read_text(encoding="utf-8")
    tree = ast.parse(runtime_source + "\n" + adapter_source)

    forbidden_modules = {"subprocess", "socket", "os"}
    forbidden_calls = {"system", "popen", "run", "Popen", "open", "write_text", "start_worker"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(alias.name.split(".")[0] in forbidden_modules for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in forbidden_modules
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_calls

    combined = runtime_source + adapter_source
    forbidden_markers = ("temporal server start", "docker", "systemctl", "gateway restart", "config.yaml")
    assert not any(marker in combined.lower() for marker in forbidden_markers)
