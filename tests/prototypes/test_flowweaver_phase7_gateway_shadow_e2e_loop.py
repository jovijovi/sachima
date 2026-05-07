"""RED contract tests for FlowWeaver Phase 7 Gateway shadow E2E loop."""

from __future__ import annotations

import copy
import importlib
import inspect
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

WORKFLOW_ID = "runtime_tx_phase7_shadow_loop"
SAFE_START_FIELDS = {
    "transaction_id": WORKFLOW_ID,
    "idempotency_key": "runtime_event_start_phase7_shadow_loop",
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
SAFE_PUBLICATION = {
    "type": "flowweaver.gateway.shadow_runtime_publication.v0",
    "verdict": "ready",
    "reason": "ok",
    "runtime_model_version": "flowweaver.runtime.v0",
    "runtime_envelope_type": "flowweaver.gateway.runtime_ingress_envelope.v0",
    "transaction_id": WORKFLOW_ID,
    "workflow_id": WORKFLOW_ID,
    "runtime_identity": {
        "type": "flowweaver.gateway.runtime_identity.v0",
        "strategy": "shadow_ref_hash_v0",
        "transaction_id": WORKFLOW_ID,
        "workflow_id": WORKFLOW_ID,
        "idempotency_key": "runtime_event_start_phase7_shadow_loop",
    },
    "start_request": {
        "operation": "start_transaction",
        "workflow_id": WORKFLOW_ID,
        "start_payload": SAFE_START_FIELDS,
    },
    "ack_bridge": {
        "status": "ready",
        "updates": [
            {
                "event_type": "record_delivery_ack",
                "delivery_key": "runtime_event_delivery_ack_phase7_shadow_loop_0",
                "surface": "final_text",
                "target_kind": "delivery",
                "target_id": "runtime_delivery_0",
                "status": "sent",
            }
        ],
    },
    "checks": {
        "shadow_capture_present": True,
        "dry_run_summary_valid": True,
        "runtime_envelope_valid": True,
        "start_request_safe": True,
        "delivery_ack_updates_safe": True,
        "payloads_absent": True,
        "visible_side_effects_absent": True,
        "runtime_side_effects_absent": True,
    },
    "side_effects": [],
}


def import_loop_module():
    return importlib.import_module("flowweaver_runtime_client.gateway_shadow_e2e_loop")


def snapshot_for_start_fields(start_fields: dict[str, object], *, applied_event_count: int = 0) -> dict[str, object]:
    payload = build_runtime_start_payload(**start_fields)
    count = payload.entry_count
    delivery_count = payload.record_counts["deliveries"]
    return {
        "type": "flowweaver.temporal_poc.snapshot.v0",
        "version": "flowweaver.temporal_poc.v0",
        "transaction_id": payload.transaction_id,
        "status": "running",
        "entry_count": count,
        "record_counts": dict(payload.record_counts),
        "start_signature": start_signature_from_payload(payload),
        "counts": {"intents": count, "artifacts": count, "deliveries": delivery_count},
        "intent_statuses": {f"runtime_intent_{index}": "pending" for index in range(count)},
        "artifact_statuses": {f"runtime_artifact_{index}": "available" for index in range(count)},
        "delivery_statuses": {f"runtime_delivery_{index}": "planned" for index in range(delivery_count)},
        "applied_event_count": applied_event_count,
        "resume_count": 0,
        "side_effects": [],
    }


class RecordingControlSurface:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.snapshot: dict[str, object] | None = None
        self.applied_delivery_events: set[str] = set()

    async def handle(self, request: object) -> dict[str, object]:
        assert type(request) is dict, "loop must call control surface with plain dict requests"
        self.calls.append(copy.deepcopy(request))
        operation = request.get("operation")
        workflow_id = request.get("workflow_id")
        if operation == "start_transaction":
            start_payload = request.get("start_payload")
            assert type(start_payload) is dict
            if self.snapshot is None:
                self.snapshot = snapshot_for_start_fields(start_payload)
                status = "started"
            else:
                status = "running"
            return {
                "ok": True,
                "operation": "start_transaction",
                "runtime_operation": "start_transaction",
                "workflow_id": workflow_id,
                "transaction_id": self.snapshot["transaction_id"],
                "status": status,
            }
        if operation == "query_transaction":
            if self.snapshot is None:
                return {"ok": False, "operation": "query_transaction", "error_code": "snapshot_unavailable"}
            return {
                "ok": True,
                "operation": "query_transaction",
                "runtime_operation": "query_snapshot",
                "workflow_id": workflow_id,
                "transaction_id": self.snapshot["transaction_id"],
                "status": self.snapshot["status"],
                "snapshot": copy.deepcopy(self.snapshot),
            }
        if operation == "reconcile_delivery_ack":
            assert self.snapshot is not None
            update = request.get("update")
            assert type(update) is dict
            status = "duplicate" if update["delivery_key"] in self.applied_delivery_events else "applied"
            if status == "applied":
                self.applied_delivery_events.add(update["delivery_key"])
                self.snapshot["applied_event_count"] += 1
            delivery_statuses = dict(self.snapshot["delivery_statuses"])
            delivery_statuses[update["target_id"]] = update["status"]
            self.snapshot["delivery_statuses"] = delivery_statuses
            return {
                "ok": True,
                "operation": "reconcile_delivery_ack",
                "runtime_operation": "record_delivery_ack",
                "workflow_id": workflow_id,
                "status": status,
                "snapshot": copy.deepcopy(self.snapshot),
            }
        raise AssertionError(f"unexpected operation: {operation!r}")


def test_phase7_loop_import_is_default_off_async_and_narrow() -> None:
    for module_name in (
        "flowweaver_runtime_client.gateway_shadow_e2e_loop",
        "gateway",
        "gateway.run",
        "gateway.platforms.feishu",
        "mcp",
        "tools.registry",
        "flowweaver_temporal_poc.client",
        "flowweaver_temporal_poc.workflows",
    ):
        sys.modules.pop(module_name, None)
    for module_name in list(sys.modules):
        if module_name == "temporalio" or module_name.startswith("temporalio."):
            sys.modules.pop(module_name, None)

    module = import_loop_module()

    assert module.FLOWWEAVER_GATEWAY_SHADOW_E2E_LOOP_VERSION == "flowweaver.gateway_shadow_e2e_loop.v0"
    assert module.SHADOW_PUBLICATION_ENVELOPE_TYPE == "flowweaver.gateway_shadow_publication.v0"
    assert inspect.iscoroutinefunction(module.run_shadow_gateway_e2e_loop)
    assert sorted(module.__all__) == [
        "FLOWWEAVER_GATEWAY_SHADOW_E2E_LOOP_VERSION",
        "SHADOW_PUBLICATION_ENVELOPE_TYPE",
        "run_shadow_gateway_e2e_loop",
    ]
    assert "temporalio" not in sys.modules
    assert "mcp" not in sys.modules
    assert "tools.registry" not in sys.modules
    assert "gateway" not in sys.modules
    assert "gateway.run" not in sys.modules
    assert "gateway.platforms.feishu" not in sys.modules
    assert "flowweaver_temporal_poc.client" not in sys.modules
    assert "flowweaver_temporal_poc.workflows" not in sys.modules


@pytest.mark.asyncio
async def test_phase7_loop_starts_queries_publishes_and_routes_ack_through_phase6_bridge() -> None:
    module = import_loop_module()
    control = RecordingControlSurface()

    result = await module.run_shadow_gateway_e2e_loop(control, SAFE_PUBLICATION)

    assert [call["operation"] for call in control.calls] == [
        "start_transaction",
        "query_transaction",
        "query_transaction",
        "reconcile_delivery_ack",
        "query_transaction",
    ]
    assert control.calls[0] == SAFE_PUBLICATION["start_request"]
    assert control.calls[2] == {"operation": "query_transaction", "workflow_id": WORKFLOW_ID}
    assert control.calls[3] == {
        "operation": "reconcile_delivery_ack",
        "workflow_id": WORKFLOW_ID,
        "update": SAFE_PUBLICATION["ack_bridge"]["updates"][0],
    }
    assert result["ok"] is True
    assert result["loop_version"] == "flowweaver.gateway_shadow_e2e_loop.v0"
    assert result["operation"] == "gateway_shadow_e2e_loop"
    assert result["workflow_id"] == WORKFLOW_ID
    assert result["transaction_id"] == WORKFLOW_ID
    assert result["start_status"] == "started"
    assert result["side_effects"] == []
    assert set(result) <= {
        "ok",
        "loop_version",
        "operation",
        "workflow_id",
        "transaction_id",
        "start_status",
        "publication",
        "ack_results",
        "final_snapshot",
        "checks",
        "side_effects",
        "error_code",
    }
    assert result["publication"] == {
        "type": "flowweaver.gateway_shadow_publication.v0",
        "loop_version": "flowweaver.gateway_shadow_e2e_loop.v0",
        "workflow_id": WORKFLOW_ID,
        "transaction_id": WORKFLOW_ID,
        "surface_counts": {"final_text": 1, "rich_card": 0, "progress_card": 0, "media": 0},
        "delivery_plan": [
            {
                "delivery_key": "runtime_event_delivery_ack_phase7_shadow_loop_0",
                "surface": "final_text",
                "target_kind": "delivery",
                "target_id": "runtime_delivery_0",
                "status": "sent",
            }
        ],
        "side_effects": [],
    }
    assert result["ack_results"] == [
        {"target_id": "runtime_delivery_0", "surface": "final_text", "status": "sent", "ack_status": "applied"}
    ]
    assert result["final_snapshot"]["delivery_statuses"] == {"runtime_delivery_0": "sent"}
    assert result["checks"] == {
        "start_accepted": True,
        "initial_snapshot_safe": True,
        "publication_envelope_safe": True,
        "delivery_targets_initialized": True,
        "ack_count_matches_publication": True,
        "final_snapshot_safe": True,
        "side_effects_absent": True,
    }


def make_publication(*, workflow_id: str, updates: list[dict[str, str]], delivery_count: int) -> dict[str, object]:
    suffix = workflow_id.removeprefix("runtime_tx_")
    publication = copy.deepcopy(SAFE_PUBLICATION)
    publication["workflow_id"] = workflow_id
    publication["transaction_id"] = workflow_id
    publication["runtime_identity"]["workflow_id"] = workflow_id
    publication["runtime_identity"]["transaction_id"] = workflow_id
    publication["runtime_identity"]["idempotency_key"] = "runtime_event_start_" + suffix
    publication["start_request"]["workflow_id"] = workflow_id
    start_payload = publication["start_request"]["start_payload"]
    start_payload["transaction_id"] = workflow_id
    start_payload["idempotency_key"] = "runtime_event_start_" + suffix
    start_payload["record_counts"] = {
        "transactions": 1,
        "intents": 1,
        "artifacts": 1,
        "deliveries": delivery_count,
    }
    publication["ack_bridge"] = {"status": "ready", "updates": updates}
    return publication


@pytest.mark.asyncio
async def test_phase7_loop_requires_simulated_acks_to_match_initialized_delivery_slots() -> None:
    module = import_loop_module()
    control = RecordingControlSurface()
    updates = [
        {
            "event_type": "record_delivery_ack",
            "delivery_key": "runtime_event_delivery_ack_phase7_cardinality_0",
            "surface": "final_text",
            "target_kind": "delivery",
            "target_id": "runtime_delivery_0",
            "status": "sent",
        },
        {
            "event_type": "record_delivery_ack",
            "delivery_key": "runtime_event_delivery_ack_phase7_cardinality_1",
            "surface": "rich_card",
            "target_kind": "delivery",
            "target_id": "runtime_delivery_1",
            "status": "acknowledged",
        },
    ]
    publication = make_publication(
        workflow_id="runtime_tx_phase7_cardinality",
        updates=updates,
        delivery_count=2,
    )

    result = await module.run_shadow_gateway_e2e_loop(control, publication)

    assert result["ok"] is True
    assert result["publication"]["surface_counts"] == {"final_text": 1, "rich_card": 1, "progress_card": 0, "media": 0}
    assert result["publication"]["delivery_plan"] == [
        {
            "delivery_key": "runtime_event_delivery_ack_phase7_cardinality_0",
            "surface": "final_text",
            "target_kind": "delivery",
            "target_id": "runtime_delivery_0",
            "status": "sent",
        },
        {
            "delivery_key": "runtime_event_delivery_ack_phase7_cardinality_1",
            "surface": "rich_card",
            "target_kind": "delivery",
            "target_id": "runtime_delivery_1",
            "status": "acknowledged",
        },
    ]
    assert result["ack_results"] == [
        {"target_id": "runtime_delivery_0", "surface": "final_text", "status": "sent", "ack_status": "applied"},
        {
            "target_id": "runtime_delivery_1",
            "surface": "rich_card",
            "status": "acknowledged",
            "ack_status": "applied",
        },
    ]
    assert result["final_snapshot"]["delivery_statuses"] == {
        "runtime_delivery_0": "sent",
        "runtime_delivery_1": "acknowledged",
    }
    assert result["final_snapshot"]["applied_event_count"] == 2


@pytest.mark.asyncio
async def test_phase7_loop_rejects_missing_target_before_phase6_reconcile_or_slot_invention() -> None:
    module = import_loop_module()
    control = RecordingControlSurface()
    publication = make_publication(
        workflow_id="runtime_tx_phase7_missing_target",
        delivery_count=1,
        updates=[
            {
                "event_type": "record_delivery_ack",
                "delivery_key": "runtime_event_delivery_ack_phase7_missing_target",
                "surface": "final_text",
                "target_kind": "delivery",
                "target_id": "runtime_delivery_1",
                "status": "sent",
            }
        ],
    )

    result = await module.run_shadow_gateway_e2e_loop(control, publication)

    assert result == {
        "ok": False,
        "loop_version": "flowweaver.gateway_shadow_e2e_loop.v0",
        "operation": "gateway_shadow_e2e_loop",
        "workflow_id": "runtime_tx_phase7_missing_target",
        "transaction_id": "runtime_tx_phase7_missing_target",
        "error_code": "delivery_target_mismatch",
        "side_effects": [],
    }
    assert [call["operation"] for call in control.calls] == ["start_transaction", "query_transaction"]
    assert control.snapshot is not None
    assert control.snapshot["delivery_statuses"] == {"runtime_delivery_0": "planned"}
    assert control.snapshot["applied_event_count"] == 0


@pytest.mark.asyncio
async def test_phase7_loop_replay_reports_duplicate_ack_without_increasing_applied_events() -> None:
    module = import_loop_module()
    control = RecordingControlSurface()
    publication = make_publication(
        workflow_id="runtime_tx_phase7_replay",
        delivery_count=1,
        updates=[
            {
                "event_type": "record_delivery_ack",
                "delivery_key": "runtime_event_delivery_ack_phase7_replay",
                "surface": "final_text",
                "target_kind": "delivery",
                "target_id": "runtime_delivery_0",
                "status": "sent",
            }
        ],
    )

    first = await module.run_shadow_gateway_e2e_loop(control, publication)
    second = await module.run_shadow_gateway_e2e_loop(control, publication)

    assert first["ack_results"] == [
        {"target_id": "runtime_delivery_0", "surface": "final_text", "status": "sent", "ack_status": "applied"}
    ]
    assert second["ack_results"] == [
        {"target_id": "runtime_delivery_0", "surface": "final_text", "status": "sent", "ack_status": "duplicate"}
    ]
    assert first["final_snapshot"]["applied_event_count"] == 1
    assert second["final_snapshot"]["applied_event_count"] == 1


class HostilePublication(dict):
    pass


class ExplodingControlSurface:
    async def handle(self, request: object) -> dict[str, object]:
        raise RuntimeError("sec" + "ret raw_prompt platform_payload oc_phase7_private_chat")


@pytest.mark.asyncio
async def test_phase7_loop_requires_actual_runtime_identity_and_true_checks_before_runtime_call() -> None:
    module = import_loop_module()
    stale_identity = copy.deepcopy(SAFE_PUBLICATION)
    stale_identity["runtime_identity"]["type"] = "flowweaver.runtime_identity.v0"
    stale_identity["runtime_identity"]["strategy"] = "shadow_capture_v0"
    false_checks = copy.deepcopy(SAFE_PUBLICATION)
    false_checks["checks"]["runtime_envelope_valid"] = False

    identity_control = RecordingControlSurface()
    checks_control = RecordingControlSurface()
    identity_result = await module.run_shadow_gateway_e2e_loop(identity_control, stale_identity)
    checks_result = await module.run_shadow_gateway_e2e_loop(checks_control, false_checks)

    assert identity_result == {
        "ok": False,
        "loop_version": "flowweaver.gateway_shadow_e2e_loop.v0",
        "operation": "gateway_shadow_e2e_loop",
        "error_code": "invalid_publication",
        "side_effects": [],
    }
    assert checks_result == identity_result
    assert identity_control.calls == []
    assert checks_control.calls == []


@pytest.mark.asyncio
async def test_phase7_loop_rejects_raw_platform_card_media_and_secret_shaped_material_before_runtime_call() -> None:
    module = import_loop_module()
    control = RecordingControlSurface()
    private_chat_id = "oc_" + "phase7_private_chat"
    private_user_id = "ou_" + "phase7_private_user"
    sensitive = "unsafe-" + "token" + "-phase7"
    hostile_publication = copy.deepcopy(SAFE_PUBLICATION)
    hostile_publication["platform_payload"] = {"chat_id": private_chat_id, "user_id": private_user_id}
    hostile_publication["card_json"] = {"body": "raw card should never enter"}
    hostile_publication["media_path"] = "/tmp/raw-phase7-media.png"
    hostile_publication["note"] = sensitive

    skipped_publication = copy.deepcopy(SAFE_PUBLICATION)
    skipped_publication["ack_bridge"]["updates"][0]["status"] = "skipped"

    hostile_mapping = HostilePublication(SAFE_PUBLICATION)

    results = [
        await module.run_shadow_gateway_e2e_loop(control, hostile_publication),
        await module.run_shadow_gateway_e2e_loop(control, skipped_publication),
        await module.run_shadow_gateway_e2e_loop(control, hostile_mapping),
    ]

    assert [result["error_code"] for result in results] == [
        "invalid_publication",
        "invalid_delivery_plan",
        "invalid_publication",
    ]
    assert control.calls == []
    for result in results:
        rendered = repr(result)
        assert "skipped" not in rendered
        assert private_chat_id not in rendered
        assert private_user_id not in rendered
        assert sensitive not in rendered
        assert "card_json" not in rendered
        assert "media_path" not in rendered
        assert "platform_payload" not in rendered
        assert set(result) <= {"ok", "loop_version", "operation", "error_code", "side_effects"}


@pytest.mark.asyncio
async def test_phase7_loop_runtime_failures_return_stable_errors_without_exception_text() -> None:
    module = import_loop_module()

    result = await module.run_shadow_gateway_e2e_loop(ExplodingControlSurface(), SAFE_PUBLICATION)

    assert result == {
        "ok": False,
        "loop_version": "flowweaver.gateway_shadow_e2e_loop.v0",
        "operation": "gateway_shadow_e2e_loop",
        "workflow_id": WORKFLOW_ID,
        "transaction_id": WORKFLOW_ID,
        "error_code": "runtime_error",
        "side_effects": [],
    }
    rendered = repr(result)
    assert "sec" + "ret" not in rendered
    assert "raw_prompt" not in rendered
    assert "platform_payload" not in rendered
    assert "oc_phase7_private_chat" not in rendered
