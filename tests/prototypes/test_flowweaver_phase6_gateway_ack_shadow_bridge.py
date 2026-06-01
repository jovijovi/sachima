"""RED contract tests for FlowWeaver Phase 6 Gateway ACK shadow bridge."""

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
    "transaction_id": "runtime_tx_phase6_shadow_bridge",
    "idempotency_key": "runtime_event_start_phase6_shadow_bridge",
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
SAFE_SNAPSHOT = {
    "type": "flowweaver.temporal_poc.snapshot.v0",
    "version": "flowweaver.temporal_poc.v0",
    "transaction_id": "runtime_tx_phase6_shadow_bridge",
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
}
SAFE_ACK = {
    "type": "flowweaver.gateway_ack_shadow.v0",
    "workflow_id": "runtime_tx_phase6_shadow_bridge",
    "delivery_key": "runtime_event_delivery_ack_phase6_shadow_bridge",
    "surface": "final_text",
    "target_kind": "delivery",
    "target_id": "runtime_delivery_0",
    "status": "sent",
}


class RecordingControlSurface:
    def __init__(self, *, snapshot: dict[str, object] | None = None) -> None:
        self.snapshot = snapshot or SAFE_SNAPSHOT
        self.calls: list[dict[str, object]] = []
        self.ack_count = 0

    async def handle(self, request: object) -> dict[str, object]:
        assert type(request) is dict, "bridge must call control surface with plain dict requests"
        self.calls.append(request)
        if request.get("operation") == "query_transaction":
            return {
                "ok": True,
                "operation": "query_transaction",
                "runtime_operation": "query_snapshot",
                "workflow_id": request["workflow_id"],
                "transaction_id": self.snapshot["transaction_id"],
                "status": self.snapshot["status"],
                "snapshot": self.snapshot,
            }
        if request.get("operation") == "reconcile_delivery_ack":
            self.ack_count += 1
            status = "applied" if self.ack_count == 1 else "duplicate"
            snapshot = dict(self.snapshot)
            delivery_statuses = dict(snapshot["delivery_statuses"])
            update = request["update"]
            assert type(update) is dict
            delivery_statuses[update["target_id"]] = update["status"]
            snapshot["delivery_statuses"] = delivery_statuses
            snapshot["applied_event_count"] = 1
            self.snapshot = snapshot
            return {
                "ok": True,
                "operation": "reconcile_delivery_ack",
                "runtime_operation": "record_delivery_ack",
                "workflow_id": request["workflow_id"],
                "status": status,
                "snapshot": snapshot,
            }
        raise AssertionError(f"unexpected control request: {request!r}")


class FailingControlSurface:
    async def handle(self, request: object) -> dict[str, object]:
        raise ValueError("sec" + "ret raw_prompt platform_payload")


def import_bridge_module():
    return importlib.import_module("flowweaver_runtime_client.gateway_ack_shadow_bridge")


def test_shadow_bridge_import_is_optional_default_off_and_narrow() -> None:
    for module_name in (
        "flowweaver_runtime_client.gateway_ack_shadow_bridge",
        "gateway",
        "gateway.platforms.feishu",
        "mcp",
        "flowweaver_temporal_poc.client",
        "flowweaver_temporal_poc.workflows",
    ):
        sys.modules.pop(module_name, None)
    for module_name in list(sys.modules):
        if module_name == "temporalio" or module_name.startswith("temporalio."):
            sys.modules.pop(module_name, None)

    module = import_bridge_module()

    assert module.FLOWWEAVER_GATEWAY_ACK_SHADOW_BRIDGE_VERSION == "flowweaver.gateway_ack_shadow_bridge.v0"
    assert module.SHADOW_ACK_ENVELOPE_TYPE == "flowweaver.gateway_ack_shadow.v0"
    assert module.ALLOWED_SHADOW_ACK_STATUSES == ("sent", "failed", "acknowledged")
    assert "skipped" not in module.ALLOWED_SHADOW_ACK_STATUSES
    assert hasattr(module, "reconcile_shadow_gateway_ack")
    assert "temporalio" not in sys.modules
    assert "mcp" not in sys.modules
    assert "gateway" not in sys.modules
    assert "gateway.platforms.feishu" not in sys.modules
    assert "flowweaver_temporal_poc.client" not in sys.modules
    assert "flowweaver_temporal_poc.workflows" not in sys.modules


@pytest.mark.asyncio
async def test_shadow_bridge_queries_snapshot_then_reconciles_safe_ack() -> None:
    module = import_bridge_module()
    control = RecordingControlSurface()

    result = await module.reconcile_shadow_gateway_ack(control, SAFE_ACK)

    assert [call["operation"] for call in control.calls] == ["query_transaction", "reconcile_delivery_ack"]
    assert control.calls[0] == {"operation": "query_transaction", "workflow_id": "runtime_tx_phase6_shadow_bridge"}
    assert control.calls[1] == {
        "operation": "reconcile_delivery_ack",
        "workflow_id": "runtime_tx_phase6_shadow_bridge",
        "update": {
            "event_type": "record_delivery_ack",
            "delivery_key": "runtime_event_delivery_ack_phase6_shadow_bridge",
            "surface": "final_text",
            "target_kind": "delivery",
            "target_id": "runtime_delivery_0",
            "status": "sent",
        },
    }
    assert result["ok"] is True
    assert result["bridge_version"] == "flowweaver.gateway_ack_shadow_bridge.v0"
    assert result["operation"] == "gateway_ack_shadow_bridge"
    assert result["runtime_operation"] == "record_delivery_ack"
    assert result["workflow_id"] == "runtime_tx_phase6_shadow_bridge"
    assert result["target_id"] == "runtime_delivery_0"
    assert result["status"] == "applied"
    assert result["snapshot"]["delivery_statuses"] == {"runtime_delivery_0": "sent"}
    assert set(result) <= {
        "ok",
        "bridge_version",
        "operation",
        "runtime_operation",
        "workflow_id",
        "target_id",
        "status",
        "snapshot",
        "error_code",
    }


@pytest.mark.asyncio
async def test_shadow_bridge_rejects_missing_delivery_target_before_reconcile_call() -> None:
    module = import_bridge_module()
    control = RecordingControlSurface()
    missing_target_ack = {**SAFE_ACK, "target_id": "runtime_delivery_1"}

    result = await module.reconcile_shadow_gateway_ack(control, missing_target_ack)

    assert result == {
        "ok": False,
        "bridge_version": "flowweaver.gateway_ack_shadow_bridge.v0",
        "operation": "gateway_ack_shadow_bridge",
        "runtime_operation": "record_delivery_ack",
        "workflow_id": "runtime_tx_phase6_shadow_bridge",
        "target_id": "runtime_delivery_1",
        "error_code": "delivery_target_mismatch",
    }
    assert [call["operation"] for call in control.calls] == ["query_transaction"]
    assert "runtime_delivery_1" not in control.snapshot["delivery_statuses"]


@pytest.mark.asyncio
async def test_shadow_bridge_replays_duplicate_ack_without_raw_material() -> None:
    module = import_bridge_module()
    control = RecordingControlSurface()

    first = await module.reconcile_shadow_gateway_ack(control, SAFE_ACK)
    second = await module.reconcile_shadow_gateway_ack(control, SAFE_ACK)

    assert first["status"] == "applied"
    assert second["status"] == "duplicate"
    assert [call["operation"] for call in control.calls] == [
        "query_transaction",
        "reconcile_delivery_ack",
        "query_transaction",
        "reconcile_delivery_ack",
    ]
    assert "raw_prompt" not in repr(second)
    assert "platform_payload" not in repr(second)


@pytest.mark.asyncio
async def test_shadow_bridge_rejects_extra_fields_skipped_status_and_raw_platform_material_before_runtime_call() -> None:
    module = import_bridge_module()
    control = RecordingControlSurface()

    extra = await module.reconcile_shadow_gateway_ack(control, {**SAFE_ACK, "debug_note": "safe_but_extra"})
    skipped = await module.reconcile_shadow_gateway_ack(control, {**SAFE_ACK, "status": "skipped"})
    hostile = await module.reconcile_shadow_gateway_ack(
        control,
        {
            **SAFE_ACK,
            "platform_payload": {"chat_id": "oc_" + "phase6_private_chat"},
            "media_path": "/tmp/raw-platform-media.png",
        },
    )

    assert extra["error_code"] == "unsafe_ack_envelope"
    assert skipped["error_code"] == "unsafe_ack_envelope"
    assert hostile["error_code"] == "unsafe_ack_envelope"
    assert control.calls == []
    for result in (extra, skipped, hostile):
        rendered = repr(result)
        assert "skipped" not in rendered
        assert "oc_phase6_private_chat" not in rendered
        assert "media_path" not in rendered
        assert "platform_payload" not in rendered


@pytest.mark.asyncio
async def test_shadow_bridge_runtime_failures_return_stable_errors_without_exception_text() -> None:
    module = import_bridge_module()

    result = await module.reconcile_shadow_gateway_ack(FailingControlSurface(), SAFE_ACK)

    assert result == {
        "ok": False,
        "bridge_version": "flowweaver.gateway_ack_shadow_bridge.v0",
        "operation": "gateway_ack_shadow_bridge",
        "runtime_operation": "record_delivery_ack",
        "workflow_id": "runtime_tx_phase6_shadow_bridge",
        "target_id": "runtime_delivery_0",
        "error_code": "runtime_error",
    }
    rendered = repr(result)
    assert "sec" + "ret" not in rendered
    assert "raw_prompt" not in rendered
    assert "platform_payload" not in rendered
