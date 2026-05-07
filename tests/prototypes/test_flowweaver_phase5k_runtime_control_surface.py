"""RED contract tests for FlowWeaver Phase 5K runtime control surface."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
PHASE5B_SRC = ROOT / "prototypes" / "flowweaver_phase5b_temporal_poc" / "src"
PHASE5C_SRC = ROOT / "prototypes" / "flowweaver_phase5c_runtime_client" / "src"
for path in (PHASE5C_SRC, PHASE5B_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from flowweaver_temporal_poc.payloads import build_runtime_start_payload, start_signature_from_payload  # noqa: E402

SAFE_START_FIELDS = {
    "transaction_id": "runtime_tx_phase5k_contract",
    "idempotency_key": "runtime_event_start_phase5k_contract",
    "entry_count": 1,
    "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
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
SAFE_START_PAYLOAD = build_runtime_start_payload(**SAFE_START_FIELDS)
SAFE_ACTIVITY_BOUNDARY = {
    "type": "flowweaver.temporal_poc.activity_boundary.v0",
    "version": "flowweaver.temporal_poc.v0",
    "status": "completed",
    "activities": {
        "validate_claim_check_ref": "validated",
        "execute_agent_turn": "completed",
        "deliver_artifact": "planned",
    },
    "refs": {
        "input_ref": "claim_ref_phase5k_start",
        "artifact_ref": "claim_ref_phase5k_artifact_0",
        "delivery_ref": "claim_ref_phase5k_delivery_0",
    },
    "side_effects": [],
}
SAFE_SNAPSHOT = {
    "type": "flowweaver.temporal_poc.snapshot.v0",
    "version": "flowweaver.temporal_poc.v0",
    "transaction_id": "runtime_tx_phase5k_contract",
    "status": "running",
    "entry_count": 1,
    "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
    "start_signature": start_signature_from_payload(SAFE_START_PAYLOAD),
    "counts": {"intents": 1, "artifacts": 1, "deliveries": 1},
    "intent_statuses": {"runtime_intent_0": "pending"},
    "artifact_statuses": {"runtime_artifact_0": "available"},
    "delivery_statuses": {"runtime_delivery_0": "planned"},
    "applied_event_count": 0,
    "resume_count": 0,
    "side_effects": [],
    "activity_boundary": SAFE_ACTIVITY_BOUNDARY,
}
SAFE_UPDATE_RESULT = {
    "type": "flowweaver.temporal_poc.update_result.v0",
    "version": "flowweaver.temporal_poc.v0",
    "update_status": "applied",
    "snapshot": SAFE_SNAPSHOT,
    "side_effects": [],
}


class RecordingRuntimeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def start_transaction(self, payload: object, *, workflow_id: str) -> dict[str, object]:
        self.calls.append(("start_transaction", {"payload": payload, "workflow_id": workflow_id}))
        return {
            "ok": True,
            "operation": "start_transaction",
            "workflow_id": workflow_id,
            "transaction_id": "runtime_tx_phase5k_contract",
            "status": "started",
        }

    async def query_snapshot(self, workflow_id: str) -> dict[str, object]:
        self.calls.append(("query_snapshot", workflow_id))
        return {
            "ok": True,
            "operation": "query_snapshot",
            "workflow_id": workflow_id,
            "transaction_id": "runtime_tx_phase5k_contract",
            "status": "running",
            "snapshot": SAFE_SNAPSHOT,
        }

    async def record_delivery_ack(self, workflow_id: str, update: object) -> dict[str, object]:
        self.calls.append(("record_delivery_ack", {"workflow_id": workflow_id, "update": update}))
        return {
            "ok": True,
            "operation": "record_delivery_ack",
            "workflow_id": workflow_id,
            "status": "applied",
            "snapshot": SAFE_SNAPSHOT,
        }

    async def cancel_transaction(self, workflow_id: str, update: object) -> dict[str, object]:
        self.calls.append(("cancel_transaction", {"workflow_id": workflow_id, "update": update}))
        return {
            "ok": True,
            "operation": "cancel_transaction",
            "workflow_id": workflow_id,
            "status": "applied",
            "snapshot": SAFE_SNAPSHOT,
        }


class RuntimeClientThatLeaks:
    async def query_snapshot(self, workflow_id: str) -> dict[str, object]:
        raise ValueError("sec" + "ret" + " raw_prompt platform_payload")


def test_control_contract_import_is_optional_and_has_closed_public_operations() -> None:
    for module_name in (
        "flowweaver_runtime_client.control_surface",
        "mcp",
        "flowweaver_temporal_poc.client",
        "flowweaver_temporal_poc.workflows",
    ):
        sys.modules.pop(module_name, None)
    for module_name in list(sys.modules):
        if module_name == "temporalio" or module_name.startswith("temporalio."):
            sys.modules.pop(module_name, None)

    module = importlib.import_module("flowweaver_runtime_client.control_surface")

    assert module.FLOWWEAVER_RUNTIME_CONTROL_SURFACE_VERSION == "flowweaver.runtime_control.v0"
    assert module.CONTROL_OPERATIONS == (
        "start_transaction",
        "query_transaction",
        "reconcile_delivery_ack",
        "cancel_transaction",
    )
    assert module.RUNTIME_OPERATION_BY_CONTROL_OPERATION == {
        "start_transaction": "start_transaction",
        "query_transaction": "query_snapshot",
        "reconcile_delivery_ack": "record_delivery_ack",
        "cancel_transaction": "cancel_transaction",
    }
    assert "temporalio" not in sys.modules
    assert "mcp" not in sys.modules
    assert "flowweaver_temporal_poc.client" not in sys.modules
    assert "flowweaver_temporal_poc.workflows" not in sys.modules


@pytest.mark.asyncio
async def test_control_surface_maps_public_operations_to_existing_runtime_facade_with_safe_results() -> None:
    from flowweaver_runtime_client.control_surface import FlowWeaverRuntimeControlSurface

    runtime = RecordingRuntimeClient()
    control = FlowWeaverRuntimeControlSurface(runtime)  # type: ignore[arg-type]

    started = await control.handle(
        {
            "operation": "start_transaction",
            "workflow_id": "runtime_tx_phase5k_contract",
            "start_payload": SAFE_START_FIELDS,
        }
    )
    queried = await control.handle({"operation": "query_transaction", "workflow_id": "runtime_tx_phase5k_contract"})
    acked = await control.handle(
        {
            "operation": "reconcile_delivery_ack",
            "workflow_id": "runtime_tx_phase5k_contract",
            "update": {
                "event_type": "record_delivery_ack",
                "delivery_key": "runtime_event_delivery_ack_phase5k_contract",
                "surface": "final_text",
                "target_kind": "delivery",
                "target_id": "runtime_delivery_0",
                "status": "sent",
            },
        }
    )
    canceled = await control.handle(
        {
            "operation": "cancel_transaction",
            "workflow_id": "runtime_tx_phase5k_contract",
            "update": {"event_type": "cancel_transaction", "event_id": "runtime_event_cancel_phase5k_contract"},
        }
    )

    assert [call[0] for call in runtime.calls] == [
        "start_transaction",
        "query_snapshot",
        "record_delivery_ack",
        "cancel_transaction",
    ]
    assert started["operation"] == "start_transaction"
    assert started["runtime_operation"] == "start_transaction"
    assert queried["operation"] == "query_transaction"
    assert queried["runtime_operation"] == "query_snapshot"
    assert queried["snapshot"]["activity_boundary"] == SAFE_ACTIVITY_BOUNDARY
    assert acked["operation"] == "reconcile_delivery_ack"
    assert acked["runtime_operation"] == "record_delivery_ack"
    assert canceled["operation"] == "cancel_transaction"
    assert canceled["runtime_operation"] == "cancel_transaction"
    for result in (started, queried, acked, canceled):
        assert set(result) <= {
            "ok",
            "operation",
            "runtime_operation",
            "workflow_id",
            "transaction_id",
            "status",
            "snapshot",
            "error_code",
        }
        assert "query_snapshot" not in repr(result) or result["operation"] == "query_transaction"
        assert "raw_prompt" not in repr(result)
        assert "platform_payload" not in repr(result)


@pytest.mark.asyncio
async def test_control_surface_rejects_start_payload_transaction_id_mismatch_before_runtime_call() -> None:
    from flowweaver_runtime_client.control_surface import FlowWeaverRuntimeControlSurface

    runtime = RecordingRuntimeClient()
    control = FlowWeaverRuntimeControlSurface(runtime)  # type: ignore[arg-type]
    mismatched_start_fields = dict(SAFE_START_FIELDS)
    mismatched_start_fields["transaction_id"] = "runtime_tx_phase5k_other"
    mismatched_start_fields["idempotency_key"] = "runtime_event_start_phase5k_other"

    result = await control.handle(
        {
            "operation": "start_transaction",
            "workflow_id": "runtime_tx_phase5k_contract",
            "start_payload": mismatched_start_fields,
        }
    )

    assert result == {
        "ok": False,
        "operation": "start_transaction",
        "runtime_operation": "start_transaction",
        "error_code": "invalid_start_payload",
    }
    assert runtime.calls == []
    assert "runtime_tx_phase5k_other" not in repr(result)


@pytest.mark.asyncio
async def test_control_surface_rejects_extra_fields_and_unsafe_material_before_runtime_call() -> None:
    from flowweaver_runtime_client.control_surface import FlowWeaverRuntimeControlSurface

    runtime = RecordingRuntimeClient()
    control = FlowWeaverRuntimeControlSurface(runtime)  # type: ignore[arg-type]

    extra = await control.handle(
        {"operation": "query_transaction", "workflow_id": "runtime_tx_phase5k_contract", "debug_note": "safe_but_extra"}
    )
    hostile = await control.handle(
        {
            "operation": "reconcile_delivery_ack",
            "workflow_id": "runtime_tx_phase5k_contract",
            "update": {
                "event_type": "record_delivery_ack",
                "delivery_key": "runtime_event_delivery_ack_phase5k_hostile",
                "surface": "final_text",
                "target_kind": "delivery",
                "target_id": "runtime_delivery_0",
                "status": "sent",
                "platform_payload": {"chat_id": "oc_" + "phase5k_private_chat"},
            },
        }
    )

    assert extra == {
        "ok": False,
        "operation": "query_transaction",
        "runtime_operation": "query_snapshot",
        "error_code": "unsafe_request",
    }
    assert hostile == {
        "ok": False,
        "operation": "reconcile_delivery_ack",
        "runtime_operation": "record_delivery_ack",
        "error_code": "unsafe_request",
    }
    assert runtime.calls == []
    assert "oc_phase5k_private_chat" not in repr(hostile)


@pytest.mark.asyncio
async def test_control_surface_runtime_failures_return_stable_errors_without_exception_text() -> None:
    from flowweaver_runtime_client.control_surface import FlowWeaverRuntimeControlSurface

    control = FlowWeaverRuntimeControlSurface(RuntimeClientThatLeaks())  # type: ignore[arg-type]

    result = await control.handle({"operation": "query_transaction", "workflow_id": "runtime_tx_phase5k_error"})

    assert result == {
        "ok": False,
        "operation": "query_transaction",
        "runtime_operation": "query_snapshot",
        "error_code": "runtime_error",
    }
    assert "sec" + "ret" not in repr(result)
    assert "raw_prompt" not in repr(result)
    assert "platform_payload" not in repr(result)


@pytest.mark.asyncio
async def test_invoke_flowweaver_runtime_control_supports_factory_and_safe_creation_errors() -> None:
    from flowweaver_runtime_client.control_surface import invoke_flowweaver_runtime_control

    async def factory() -> RecordingRuntimeClient:
        return RecordingRuntimeClient()

    ok = await invoke_flowweaver_runtime_control(
        {"operation": "query_transaction", "workflow_id": "runtime_tx_phase5k_factory"},
        runtime_client_factory=factory,
    )
    missing_address = await invoke_flowweaver_runtime_control(
        {"operation": "query_transaction", "workflow_id": "runtime_tx_phase5k_factory"}
    )
    invalid_address = await invoke_flowweaver_runtime_control(
        {"operation": "query_transaction", "workflow_id": "runtime_tx_phase5k_factory"},
        temporal_address="temporal.example.test:7233",
    )

    assert ok["ok"] is True
    assert ok["operation"] == "query_transaction"
    assert ok["runtime_operation"] == "query_snapshot"
    assert missing_address == {
        "ok": False,
        "operation": "query_transaction",
        "runtime_operation": "query_snapshot",
        "error_code": "temporal_address_required",
    }
    assert invalid_address == {
        "ok": False,
        "operation": "query_transaction",
        "runtime_operation": "query_snapshot",
        "error_code": "invalid_temporal_address",
    }
