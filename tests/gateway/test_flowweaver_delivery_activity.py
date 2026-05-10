"""RED/GREEN tests for FlowWeaver Phase 32 controlled delivery and ACK Activity."""

from __future__ import annotations

import ast
import asyncio
import copy
import inspect
import subprocess
from pathlib import Path
from typing import Any

import pytest

from gateway.flowweaver_agent_execution_activity import (
    FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT,
    FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION,
    build_flowweaver_agent_execution_request,
    execute_controlled_agent_turn,
)
from gateway.flowweaver_delivery_activity import (
    FLOWWEAVER_DELIVERY_ACTIVITY_CONTRACT_TYPE,
    FLOWWEAVER_DELIVERY_ACTIVITY_REPORT_TYPE,
    FLOWWEAVER_DELIVERY_ACTIVITY_REQUEST_TYPE,
    FLOWWEAVER_DELIVERY_ACTIVITY_RESULT_TYPE,
    FLOWWEAVER_DELIVERY_ACTIVITY_SUCCESS_VERDICT,
    FLOWWEAVER_DELIVERY_ACTIVITY_VERSION,
    build_deliver_artifact_activity,
    build_flowweaver_delivery_activity_report,
    build_flowweaver_delivery_activity_request,
    deliver_controlled_artifact,
    describe_flowweaver_delivery_activity_contract,
    validate_flowweaver_delivery_activity_report,
    validate_flowweaver_delivery_activity_request,
    validate_flowweaver_delivery_activity_result,
    validate_flowweaver_delivery_activity_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]
MODULE_SOURCE = ROOT / "gateway" / "flowweaver_delivery_activity.py"
PLAN_DOC = ROOT / "docs" / "plans" / "2026-05-09-flowweaver-phase32-delivery-activity-ack-reconciliation.md"
DEV_LOG = ROOT / "docs" / "dev_log" / "2026-05-09-flowweaver-phase32-delivery-activity-ack-reconciliation.md"
RUNBOOK = ROOT / "docs" / "runbooks" / "flowweaver-delivery-activity-ack-reconciliation.md"

EXPECTED_CONTRACT_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "scope",
    "consumes_verdict",
    "entrypoints",
    "request_fields",
    "result_fields",
    "snapshot_fields",
    "report_fields",
    "delivery_surface_boundary",
    "runtime_policy",
    "ack_policy",
    "retry_policy",
    "checks",
    "separate_approvals",
    "forbidden_side_effects",
    "side_effects",
]
EXPECTED_REQUEST_FIELDS = [
    "type",
    "version",
    "phase",
    "transaction_id",
    "workflow_id",
    "intent_id",
    "agent_execution_result",
    "initialized_delivery_slots",
    "delivery_policy",
    "required_surfaces",
    "delivery_digest",
    "side_effects",
]
EXPECTED_RESULT_FIELDS = [
    "type",
    "version",
    "phase",
    "activity",
    "status",
    "artifact_ref",
    "delivery_refs",
    "surface_state",
    "ack_updates",
    "ack_results",
    "counts",
    "delivery_digest",
    "error_code",
    "retry_class",
    "side_effects",
]
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
EXPECTED_REPORT_FIELDS = [
    "type",
    "version",
    "phase",
    "ok",
    "verdict",
    "operation",
    "phase31_verdict",
    "controlled_delivery_verified",
    "ack_reconciliation_verified",
    "history_no_leak_checked",
    "result_no_leak_checked",
    "checks",
    "error_code",
    "side_effects",
]
EXPECTED_SURFACE_BOUNDARY = {
    "mode": "injected_delivery_surface_only",
    "surface_input": "safe_artifact_ref_delivery_slots_and_runtime_ids_only",
    "raw_material_access": "delivery_surface_boundary_only",
    "surface_output": "sanitized_ack_updates_only",
    "gateway_adapter_factory": "forbidden",
    "side_effects": [],
}
EXPECTED_RUNTIME_POLICY = {
    "mode": "controlled_non_production_delivery_ack_activity",
    "temporal_runtime": "local_staging_only",
    "gateway_delivery": "injected_surface_only",
    "runtime_ack_reconciliation": "injected_control_surface_required_when_enabled",
    "production_gateway_wiring": "forbidden",
    "surface_state_separation": "required",
    "side_effects": [],
}
EXPECTED_ACK_POLICY = {
    "initialized_slots_only": True,
    "target_order": "deterministic_bounded_prefix",
    "allowed_surfaces": ["progress_card", "rich_card", "final_text", "media"],
    "allowed_ack_statuses": ["sent", "failed", "acknowledged"],
    "runtime_result_statuses": ["applied", "duplicate", "rejected"],
    "rich_card_never_implies_final_text": True,
    "side_effects": [],
}
EXPECTED_RETRY_POLICY = {
    "start_to_close_timeout_seconds": 15,
    "maximum_attempts": 2,
    "non_retryable_error_types": [
        "invalid_delivery_activity_request",
        "invalid_agent_execution_result",
        "invalid_delivery_slot",
        "delivery_policy_disabled",
        "delivery_surface_required",
        "runtime_control_surface_required",
        "uninitialized_ack_target",
        "delivery_target_mismatch",
        "invalid_ack_update",
        "unsafe_material",
        "delivery_cancelled",
    ],
    "transient_error_types": [
        "delivery_surface_failed",
        "delivery_surface_timeout",
        "runtime_query_failed",
        "runtime_reconciliation_failed",
        "unsafe_runtime_output",
    ],
}
EXPECTED_CHECKS = [
    "phase31_verdict_valid",
    "delivery_surface_injected_and_observable",
    "default_off_zero_delivery_calls",
    "ack_targets_initialized_only",
    "ack_prefix_order_verified",
    "ack_replay_idempotent",
    "surface_state_separated",
    "rich_card_does_not_suppress_final_text",
    "failure_timeout_cancel_preserve_delivery_state",
    "history_no_leak_verified",
    "gateway_wiring_absent",
    "side_effects_absent",
]
EXPECTED_SEPARATE_APPROVALS = [
    "narrow_ai_flow_pilot",
    "production_gateway_wiring",
    "production_delivery_enablement",
    "production_agent_execution",
    "production_config_write",
    "gateway_restart",
    "platform_adapter_mutation",
    "gateway_owned_worker_lifecycle",
]
EXPECTED_FORBIDDEN_SIDE_EFFECTS = [
    "gateway_run_change",
    "gateway_platform_adapter_access",
    "gateway_adapter_factory",
    "platform_adapter_mutation",
    "production_config_write",
    "gateway_restart",
    "client_connect_factory",
    "workflow_environment_factory",
    "worker_lifecycle",
    "subprocess",
    "socket",
    "docker",
    "daemon",
    "service_startup",
    "raw_material_persistence",
]

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


class RecordingDeliverySurface:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def __call__(self, request: dict[str, object]) -> dict[str, object]:
        self.calls.append(copy.deepcopy(request))
        return copy.deepcopy(self.response)


class RaisingDeliverySurface:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def __call__(self, request: dict[str, object]) -> dict[str, object]:
        self.calls.append(copy.deepcopy(request))
        raise RuntimeError(RAW_EXCEPTION_VALUE)


class CancelledDeliverySurface:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def __call__(self, request: dict[str, object]) -> dict[str, object]:
        self.calls.append(copy.deepcopy(request))
        raise asyncio.CancelledError("raw phase32 cancellation value")


class RecordingRuntimeControlSurface:
    def __init__(self, *, duplicate_refs: set[str] | None = None, reject_refs: set[str] | None = None) -> None:
        self.duplicate_refs = duplicate_refs or set()
        self.reject_refs = reject_refs or set()
        self.calls: list[dict[str, object]] = []

    async def reconcile_delivery_ack(self, update: dict[str, object]) -> dict[str, object]:
        self.calls.append(copy.deepcopy(update))
        delivery_ref = str(update["delivery_ref"])
        if delivery_ref in self.reject_refs:
            status = "rejected"
            error_code = "runtime_reconciliation_failed"
        elif delivery_ref in self.duplicate_refs:
            status = "duplicate"
            error_code = None
        else:
            status = "applied"
            error_code = None
        return {
            "status": status,
            "delivery_ref": delivery_ref,
            "surface": update["surface"],
            "error_code": error_code,
            "side_effects": [],
        }


class MutatingRuntimeControlSurface:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def reconcile_delivery_ack(self, update: dict[str, object]) -> dict[str, object]:
        self.calls.append(copy.deepcopy(update))
        update["delivery_ref"] = "runtime_delivery_99"
        return {
            "status": "applied",
            "delivery_ref": update["delivery_ref"],
            "surface": update["surface"],
            "error_code": None,
            "side_effects": [],
        }


def canonical_snapshot() -> dict[str, object]:
    return {
        "type": "flowweaver.gateway.delivery_activity_snapshot.v0",
        "version": FLOWWEAVER_DELIVERY_ACTIVITY_VERSION,
        "phase": "phase32",
        "transaction_id": "runtime_tx_phase32_1",
        "workflow_id": "runtime_tx_phase32_1",
        "status": "delivery_completed",
        "intent_statuses": {"runtime_intent_0": "delivered"},
        "artifact_refs": ["runtime_artifact_0"],
        "delivery_refs": ["runtime_delivery_0", "runtime_delivery_1"],
        "surface_state": {
            "progress_card_sent": False,
            "rich_cards_sent": 1,
            "final_text_sent": True,
            "media_sent": 0,
        },
        "activity_sequence": [
            {
                "name": "deliver_artifact",
                "status": "delivered",
                "error_code": None,
                "side_effects": [],
            }
        ],
        "counts": {
            "activities": 1,
            "artifacts": 1,
            "deliveries": 2,
            "ack_updates": 2,
            "ack_applied": 2,
            "ack_duplicates": 0,
            "ack_rejected": 0,
        },
        "delivery_digest": "sha256:" + ("1" * 64),
        "error_code": None,
        "side_effects": [],
    }


def claim_ref(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "ref": "claim_ref_phase32_0",
        "kind": "agent_input",
        "count": 1,
        "size": 128,
        "checksum_hint": "sha256:" + ("a" * 64),
    }
    value.update(overrides)
    return value


async def agent_execution_result(**overrides: object) -> dict[str, object]:
    request = build_flowweaver_agent_execution_request(
        transaction_id="runtime_tx_phase32_1",
        workflow_id="runtime_tx_phase32_1",
        intent_id="runtime_intent_0",
        claim_check_ref=claim_ref(),
        artifact_ref="runtime_artifact_0",
    )
    result = await execute_controlled_agent_turn(
        execution_request=request,
        validated_claim={
            "activity": "validate_claim_check_ref",
            "status": "validated",
            "claim_ref": "claim_ref_phase32_0",
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
    result.update(overrides)
    return result


def delivery_slots(*, surfaces: list[str] | None = None) -> list[dict[str, object]]:
    selected = surfaces or ["rich_card", "final_text"]
    return [
        {
            "delivery_ref": f"runtime_delivery_{index}",
            "surface": surface,
            "artifact_ref": "runtime_artifact_0",
            "required": True,
        }
        for index, surface in enumerate(selected)
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


async def delivery_request(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "transaction_id": "runtime_tx_phase32_1",
        "workflow_id": "runtime_tx_phase32_1",
        "intent_id": "runtime_intent_0",
        "agent_execution_result": await agent_execution_result(),
        "initialized_delivery_slots": delivery_slots(),
        "enabled": True,
    }
    kwargs.update(overrides)
    return build_flowweaver_delivery_activity_request(**kwargs)  # type: ignore[arg-type]


def assert_no_raw_values(value: object) -> None:
    rendered = repr(value).lower()
    for marker in FORBIDDEN_SENTINELS:
        assert marker.lower() not in rendered
    assert "traceback" not in rendered
    assert "runtimeerror" not in rendered
    assert "temporalio.exceptions" not in rendered


@pytest.mark.asyncio
async def test_phase32_exposes_contract_and_injected_surface_ack_boundary() -> None:
    contract = describe_flowweaver_delivery_activity_contract()

    assert list(contract) == EXPECTED_CONTRACT_FIELDS
    assert contract["type"] == FLOWWEAVER_DELIVERY_ACTIVITY_CONTRACT_TYPE
    assert contract["version"] == FLOWWEAVER_DELIVERY_ACTIVITY_VERSION
    assert contract["phase"] == "phase32"
    assert contract["verdict"] == FLOWWEAVER_DELIVERY_ACTIVITY_SUCCESS_VERDICT
    assert contract["verdict"] == "ready_for_narrow_ai_flow_pilot_request"
    assert contract["scope"] == "controlled_delivery_activity_ack_reconciliation"
    assert contract["consumes_verdict"] == FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT
    assert contract["request_fields"] == EXPECTED_REQUEST_FIELDS
    assert contract["result_fields"] == EXPECTED_RESULT_FIELDS
    assert contract["snapshot_fields"] == EXPECTED_SNAPSHOT_FIELDS
    assert contract["report_fields"] == EXPECTED_REPORT_FIELDS
    assert contract["delivery_surface_boundary"] == EXPECTED_SURFACE_BOUNDARY
    assert contract["runtime_policy"] == EXPECTED_RUNTIME_POLICY
    assert contract["ack_policy"] == EXPECTED_ACK_POLICY
    assert contract["retry_policy"] == EXPECTED_RETRY_POLICY
    assert contract["checks"] == EXPECTED_CHECKS
    assert contract["separate_approvals"] == EXPECTED_SEPARATE_APPROVALS
    assert contract["forbidden_side_effects"] == EXPECTED_FORBIDDEN_SIDE_EFFECTS
    assert contract["side_effects"] == []

    assert not inspect.iscoroutinefunction(describe_flowweaver_delivery_activity_contract)
    assert not inspect.iscoroutinefunction(validate_flowweaver_delivery_activity_request)
    assert inspect.iscoroutinefunction(deliver_controlled_artifact)
    built = build_deliver_artifact_activity(
        delivery_surface=RecordingDeliverySurface(surface_success()),
        runtime_control_surface=RecordingRuntimeControlSurface(),
    )
    assert inspect.iscoroutinefunction(built)


@pytest.mark.asyncio
async def test_phase32_request_builder_accepts_safe_p31_result_and_recomputes_digest() -> None:
    request = await delivery_request()

    assert list(request) == EXPECTED_REQUEST_FIELDS
    assert request["type"] == FLOWWEAVER_DELIVERY_ACTIVITY_REQUEST_TYPE
    assert request["version"] == FLOWWEAVER_DELIVERY_ACTIVITY_VERSION
    assert request["phase"] == "phase32"
    assert request["transaction_id"] == "runtime_tx_phase32_1"
    assert request["workflow_id"] == "runtime_tx_phase32_1"
    assert request["intent_id"] == "runtime_intent_0"
    assert request["agent_execution_result"]["artifact_ref"] == "runtime_artifact_0"
    assert request["initialized_delivery_slots"] == delivery_slots()
    assert request["delivery_policy"] == {
        "enabled": True,
        "mode": "controlled_non_production_delivery_activity",
        "ack_reconciliation": "runtime_control_surface_required",
        "surfaces": ["progress_card", "rich_card", "final_text", "media"],
        "final_text_required": True,
        "rich_card_does_not_suppress_final_text": True,
        "side_effects": [],
    }
    assert request["required_surfaces"] == ["rich_card", "final_text"]
    assert str(request["delivery_digest"]).startswith("sha256:")
    assert len(str(request["delivery_digest"]).removeprefix("sha256:")) == 64
    assert request["side_effects"] == []
    assert validate_flowweaver_delivery_activity_request(copy.deepcopy(request)) == request
    assert_no_raw_values(request)


def test_phase32_validators_reject_reordered_request_fields() -> None:
    request = {
        "side_effects": [],
        "type": FLOWWEAVER_DELIVERY_ACTIVITY_REQUEST_TYPE,
        "version": FLOWWEAVER_DELIVERY_ACTIVITY_VERSION,
        "phase": "phase32",
        "transaction_id": "runtime_tx_phase32_1",
        "workflow_id": "runtime_tx_phase32_1",
        "intent_id": "runtime_intent_0",
        "agent_execution_result": {},
        "initialized_delivery_slots": [],
        "delivery_policy": {},
        "required_surfaces": [],
        "delivery_digest": "sha256:" + ("0" * 64),
    }

    with pytest.raises(ValueError, match="invalid_delivery_activity_request"):
        validate_flowweaver_delivery_activity_request(request)


def test_phase32_public_snapshot_validator_rejects_reordered_fields() -> None:
    snapshot = canonical_snapshot()
    assert validate_flowweaver_delivery_activity_snapshot(copy.deepcopy(snapshot)) == snapshot
    reordered = {"side_effects": [], **{key: value for key, value in snapshot.items() if key != "side_effects"}}

    with pytest.raises(ValueError, match="invalid_delivery_activity_snapshot"):
        validate_flowweaver_delivery_activity_snapshot(reordered)


def test_phase32_public_snapshot_validator_rejects_reordered_nested_fixed_fields() -> None:
    snapshot = canonical_snapshot()

    reordered_counts = copy.deepcopy(snapshot)
    reordered_counts["counts"] = {
        "ack_rejected": 0,
        "activities": 1,
        "artifacts": 1,
        "deliveries": 2,
        "ack_updates": 2,
        "ack_applied": 2,
        "ack_duplicates": 0,
    }
    with pytest.raises(ValueError, match="invalid_delivery_activity_snapshot"):
        validate_flowweaver_delivery_activity_snapshot(reordered_counts)

    reordered_activity_sequence = copy.deepcopy(snapshot)
    reordered_activity_sequence["activity_sequence"] = [
        {
            "side_effects": [],
            "name": "deliver_artifact",
            "status": "delivered",
            "error_code": None,
        }
    ]
    with pytest.raises(ValueError, match="invalid_delivery_activity_snapshot"):
        validate_flowweaver_delivery_activity_snapshot(reordered_activity_sequence)


@pytest.mark.asyncio
async def test_phase32_disabled_policy_makes_zero_delivery_or_runtime_calls() -> None:
    request = await delivery_request(enabled=False)
    surface = RecordingDeliverySurface(
        surface_success(
            delivery_ack("runtime_delivery_0", "rich_card"),
            delivery_ack("runtime_delivery_1", "final_text"),
        )
    )
    runtime = RecordingRuntimeControlSurface()

    result = await deliver_controlled_artifact(
        delivery_request=request,
        delivery_surface=surface,
        runtime_control_surface=runtime,
    )

    assert surface.calls == []
    assert runtime.calls == []
    assert result["status"] == "disabled"
    assert result["artifact_ref"] == "runtime_artifact_0"
    assert result["delivery_refs"] == []
    assert result["surface_state"] == {
        "progress_card_sent": False,
        "rich_cards_sent": 0,
        "final_text_sent": False,
        "media_sent": 0,
    }
    assert result["ack_updates"] == []
    assert result["ack_results"] == []
    assert result["counts"] == {
        "delivery_calls": 0,
        "ack_updates": 0,
        "ack_applied": 0,
        "ack_duplicates": 0,
        "ack_rejected": 0,
    }
    assert result["error_code"] == "delivery_policy_disabled"
    assert result["retry_class"] == "non_retryable"
    assert result["side_effects"] == []
    assert validate_flowweaver_delivery_activity_result(copy.deepcopy(result)) == result
    assert_no_raw_values(result)


@pytest.mark.asyncio
async def test_phase32_success_reconciles_initialized_ack_prefix_and_keeps_surfaces_separate() -> None:
    request = await delivery_request()
    surface = RecordingDeliverySurface(
        surface_success(
            delivery_ack("runtime_delivery_0", "rich_card"),
            delivery_ack("runtime_delivery_1", "final_text"),
        )
    )
    runtime = RecordingRuntimeControlSurface()

    result = await deliver_controlled_artifact(
        delivery_request=request,
        delivery_surface=surface,
        runtime_control_surface=runtime,
    )

    assert len(surface.calls) == 1
    assert list(surface.calls[0]) == [
        "transaction_id",
        "workflow_id",
        "intent_id",
        "artifact_ref",
        "artifact_kind",
        "initialized_delivery_slots",
        "required_surfaces",
        "delivery_policy",
        "delivery_digest",
    ]
    assert_no_raw_values(surface.calls[0])
    assert len(runtime.calls) == 2
    assert [call["delivery_ref"] for call in runtime.calls] == ["runtime_delivery_0", "runtime_delivery_1"]

    assert list(result) == EXPECTED_RESULT_FIELDS
    assert result["type"] == FLOWWEAVER_DELIVERY_ACTIVITY_RESULT_TYPE
    assert result["status"] == "delivered"
    assert result["artifact_ref"] == "runtime_artifact_0"
    assert result["delivery_refs"] == ["runtime_delivery_0", "runtime_delivery_1"]
    assert result["surface_state"] == {
        "progress_card_sent": False,
        "rich_cards_sent": 1,
        "final_text_sent": True,
        "media_sent": 0,
    }
    assert result["ack_updates"] == [
        {
            "delivery_ref": "runtime_delivery_0",
            "surface": "rich_card",
            "status": "sent",
            "ack_ref": "runtime_event_delivery_ack_0",
        },
        {
            "delivery_ref": "runtime_delivery_1",
            "surface": "final_text",
            "status": "sent",
            "ack_ref": "runtime_event_delivery_ack_1",
        },
    ]
    assert [item["status"] for item in result["ack_results"]] == ["applied", "applied"]
    assert result["counts"] == {
        "delivery_calls": 1,
        "ack_updates": 2,
        "ack_applied": 2,
        "ack_duplicates": 0,
        "ack_rejected": 0,
    }
    assert result["error_code"] is None
    assert result["retry_class"] == "none"
    assert result["side_effects"] == []
    assert validate_flowweaver_delivery_activity_result(copy.deepcopy(result)) == result
    assert_no_raw_values(result)


@pytest.mark.asyncio
async def test_phase32_rejects_runtime_ack_mutation_of_initialized_targets() -> None:
    request = await delivery_request()
    surface = RecordingDeliverySurface(
        surface_success(
            delivery_ack("runtime_delivery_0", "rich_card"),
            delivery_ack("runtime_delivery_1", "final_text"),
        )
    )

    result = await deliver_controlled_artifact(
        delivery_request=request,
        delivery_surface=surface,
        runtime_control_surface=MutatingRuntimeControlSurface(),
    )

    assert result["status"] == "rejected"
    assert result["error_code"] == "runtime_reconciliation_failed"
    assert "runtime_delivery_99" not in repr(result)
    assert result["delivery_refs"] in ([], ["runtime_delivery_0", "runtime_delivery_1"])
    assert_no_raw_values(result)


@pytest.mark.asyncio
async def test_phase32_failed_required_surface_ack_is_not_delivered_even_when_final_text_sent() -> None:
    request = await delivery_request()
    surface = RecordingDeliverySurface(
        surface_success(
            delivery_ack("runtime_delivery_0", "rich_card", status="failed"),
            delivery_ack("runtime_delivery_1", "final_text"),
        )
    )

    result = await deliver_controlled_artifact(
        delivery_request=request,
        delivery_surface=surface,
        runtime_control_surface=RecordingRuntimeControlSurface(),
    )

    assert result["status"] == "partially_delivered"
    assert result["surface_state"] == {
        "progress_card_sent": False,
        "rich_cards_sent": 0,
        "final_text_sent": True,
        "media_sent": 0,
    }
    assert result["error_code"] == "runtime_reconciliation_failed"
    assert result["retry_class"] == "transient"
    assert_no_raw_values(result)


@pytest.mark.asyncio
async def test_phase32_rich_card_only_ack_does_not_suppress_required_final_text() -> None:
    request = await delivery_request()
    surface = RecordingDeliverySurface(surface_success(delivery_ack("runtime_delivery_0", "rich_card"), status="partial"))
    runtime = RecordingRuntimeControlSurface()

    result = await deliver_controlled_artifact(
        delivery_request=request,
        delivery_surface=surface,
        runtime_control_surface=runtime,
    )

    assert len(surface.calls) == 1
    assert len(runtime.calls) == 1
    assert result["status"] == "partially_delivered"
    assert result["delivery_refs"] == ["runtime_delivery_0"]
    assert result["surface_state"] == {
        "progress_card_sent": False,
        "rich_cards_sent": 1,
        "final_text_sent": False,
        "media_sent": 0,
    }
    assert result["error_code"] == "final_text_delivery_missing"
    assert result["retry_class"] == "transient"
    assert_no_raw_values(result)


@pytest.mark.asyncio
async def test_phase32_rejects_extra_or_out_of_order_ack_target_before_runtime_reconciliation() -> None:
    request = await delivery_request()
    runtime = RecordingRuntimeControlSurface()
    extra_surface = RecordingDeliverySurface(surface_success(delivery_ack("runtime_delivery_2", "media")))

    extra = await deliver_controlled_artifact(
        delivery_request=request,
        delivery_surface=extra_surface,
        runtime_control_surface=runtime,
    )

    assert len(extra_surface.calls) == 1
    assert runtime.calls == []
    assert extra["status"] == "rejected"
    assert extra["delivery_refs"] == []
    assert extra["error_code"] == "uninitialized_ack_target"
    assert extra["retry_class"] == "non_retryable"
    assert_no_raw_values(extra)

    out_of_order_surface = RecordingDeliverySurface(surface_success(delivery_ack("runtime_delivery_1", "final_text")))
    out_of_order = await deliver_controlled_artifact(
        delivery_request=request,
        delivery_surface=out_of_order_surface,
        runtime_control_surface=runtime,
    )

    assert runtime.calls == []
    assert out_of_order["status"] == "rejected"
    assert out_of_order["error_code"] == "delivery_target_mismatch"
    assert_no_raw_values(out_of_order)


@pytest.mark.asyncio
async def test_phase32_duplicate_ack_replay_is_idempotent_and_safe() -> None:
    request = await delivery_request()
    surface = RecordingDeliverySurface(
        surface_success(
            delivery_ack("runtime_delivery_0", "rich_card"),
            delivery_ack("runtime_delivery_1", "final_text"),
        )
    )
    runtime = RecordingRuntimeControlSurface(duplicate_refs={"runtime_delivery_0", "runtime_delivery_1"})

    result = await deliver_controlled_artifact(
        delivery_request=request,
        delivery_surface=surface,
        runtime_control_surface=runtime,
    )

    assert result["status"] == "delivered"
    assert [item["status"] for item in result["ack_results"]] == ["duplicate", "duplicate"]
    assert result["counts"] == {
        "delivery_calls": 1,
        "ack_updates": 2,
        "ack_applied": 0,
        "ack_duplicates": 2,
        "ack_rejected": 0,
    }
    assert result["error_code"] is None
    assert_no_raw_values(result)


@pytest.mark.asyncio
async def test_phase32_failure_timeout_and_cancel_paths_are_stable_sanitized_and_preserve_state() -> None:
    request = await delivery_request()

    failed = await deliver_controlled_artifact(
        delivery_request=request,
        delivery_surface=RaisingDeliverySurface(),
        runtime_control_surface=RecordingRuntimeControlSurface(),
    )
    assert failed["status"] == "rejected"
    assert failed["delivery_refs"] == []
    assert failed["surface_state"]["final_text_sent"] is False
    assert failed["error_code"] == "delivery_surface_failed"
    assert failed["retry_class"] == "transient"
    assert_no_raw_values(failed)

    timed_out = await deliver_controlled_artifact(
        delivery_request=request,
        delivery_surface=RecordingDeliverySurface(surface_success(status="timed_out")),
        runtime_control_surface=RecordingRuntimeControlSurface(),
    )
    assert timed_out["status"] == "timed_out"
    assert timed_out["delivery_refs"] == []
    assert timed_out["surface_state"]["final_text_sent"] is False
    assert timed_out["error_code"] == "delivery_surface_timeout"
    assert timed_out["retry_class"] == "transient"
    assert_no_raw_values(timed_out)

    cancelled = await deliver_controlled_artifact(
        delivery_request=request,
        delivery_surface=CancelledDeliverySurface(),
        runtime_control_surface=RecordingRuntimeControlSurface(),
    )
    assert cancelled["status"] == "cancelled"
    assert cancelled["delivery_refs"] == []
    assert cancelled["surface_state"]["final_text_sent"] is False
    assert cancelled["error_code"] == "delivery_cancelled"
    assert cancelled["retry_class"] == "non_retryable"
    assert_no_raw_values(cancelled)


@pytest.mark.asyncio
async def test_phase32_report_builder_consumes_p31_verdict_and_sanitized_delivery_result() -> None:
    result = await deliver_controlled_artifact(
        delivery_request=await delivery_request(),
        delivery_surface=RecordingDeliverySurface(
            surface_success(
                delivery_ack("runtime_delivery_0", "rich_card"),
                delivery_ack("runtime_delivery_1", "final_text"),
            )
        ),
        runtime_control_surface=RecordingRuntimeControlSurface(),
    )

    report = build_flowweaver_delivery_activity_report(
        agent_execution_activity_version=FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION,
        agent_execution_activity_verdict=FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT,
        delivery_result=result,
        history_no_leak_checked=True,
    )

    assert list(report) == EXPECTED_REPORT_FIELDS
    assert report["type"] == FLOWWEAVER_DELIVERY_ACTIVITY_REPORT_TYPE
    assert report["verdict"] == FLOWWEAVER_DELIVERY_ACTIVITY_SUCCESS_VERDICT
    assert report["phase31_verdict"] == FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT
    assert report["controlled_delivery_verified"] is True
    assert report["ack_reconciliation_verified"] is True
    assert report["history_no_leak_checked"] is True
    assert report["result_no_leak_checked"] is True
    assert report["checks"] == {key: True for key in EXPECTED_CHECKS}
    assert report["error_code"] is None
    assert report["side_effects"] == []
    assert validate_flowweaver_delivery_activity_report(copy.deepcopy(report)) == report
    assert_no_raw_values(report)


@pytest.mark.asyncio
async def test_phase32_report_builder_rejects_semantically_inconsistent_delivered_result() -> None:
    valid = await deliver_controlled_artifact(
        delivery_request=await delivery_request(),
        delivery_surface=RecordingDeliverySurface(
            surface_success(
                delivery_ack("runtime_delivery_0", "rich_card"),
                delivery_ack("runtime_delivery_1", "final_text"),
            )
        ),
        runtime_control_surface=RecordingRuntimeControlSurface(),
    )
    malformed = copy.deepcopy(valid)
    malformed["delivery_refs"] = []
    malformed["ack_updates"] = []
    malformed["ack_results"] = []
    malformed["surface_state"] = {
        "progress_card_sent": False,
        "rich_cards_sent": 0,
        "final_text_sent": False,
        "media_sent": 0,
    }
    malformed["counts"] = {
        "delivery_calls": 0,
        "ack_updates": 0,
        "ack_applied": 0,
        "ack_duplicates": 0,
        "ack_rejected": 0,
    }

    with pytest.raises(ValueError, match="invalid_delivery_activity_result"):
        validate_flowweaver_delivery_activity_result(malformed)

    report = build_flowweaver_delivery_activity_report(
        agent_execution_activity_version=FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION,
        agent_execution_activity_verdict=FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT,
        delivery_result=malformed,
        history_no_leak_checked=True,
    )

    assert report == {
        "type": FLOWWEAVER_DELIVERY_ACTIVITY_REPORT_TYPE,
        "version": FLOWWEAVER_DELIVERY_ACTIVITY_VERSION,
        "phase": "phase32",
        "ok": False,
        "operation": "build_flowweaver_delivery_activity_report",
        "error_code": "invalid_controlled_delivery_result",
        "side_effects": [],
    }


@pytest.mark.asyncio
async def test_phase32_result_validator_rejects_forged_final_text_surface_state_without_ack() -> None:
    valid = await deliver_controlled_artifact(
        delivery_request=await delivery_request(),
        delivery_surface=RecordingDeliverySurface(
            surface_success(
                delivery_ack("runtime_delivery_0", "rich_card"),
                delivery_ack("runtime_delivery_1", "final_text"),
            )
        ),
        runtime_control_surface=RecordingRuntimeControlSurface(),
    )
    forged = copy.deepcopy(valid)
    forged["delivery_refs"] = ["runtime_delivery_0"]
    forged["ack_updates"] = [delivery_ack("runtime_delivery_0", "rich_card")]
    forged["ack_results"] = [
        {
            "status": "applied",
            "delivery_ref": "runtime_delivery_0",
            "surface": "rich_card",
            "error_code": None,
            "side_effects": [],
        }
    ]
    forged["surface_state"] = {
        "progress_card_sent": False,
        "rich_cards_sent": 1,
        "final_text_sent": True,
        "media_sent": 0,
    }
    forged["counts"] = {
        "delivery_calls": 1,
        "ack_updates": 1,
        "ack_applied": 1,
        "ack_duplicates": 0,
        "ack_rejected": 0,
    }

    with pytest.raises(ValueError, match="invalid_delivery_activity_result"):
        validate_flowweaver_delivery_activity_result(forged)

    report = build_flowweaver_delivery_activity_report(
        agent_execution_activity_version=FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION,
        agent_execution_activity_verdict=FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT,
        delivery_result=forged,
        history_no_leak_checked=True,
    )
    assert report["ok"] is False
    assert report["error_code"] == "invalid_controlled_delivery_result"


@pytest.mark.asyncio
async def test_phase32_activity_factory_rejects_unsafe_payload_before_delivery_surface_call() -> None:
    surface = RecordingDeliverySurface(surface_success(delivery_ack("runtime_delivery_0", "rich_card")))
    runtime = RecordingRuntimeControlSurface()
    activity_func = build_deliver_artifact_activity(delivery_surface=surface, runtime_control_surface=runtime)

    result = await activity_func({"bad": RAW_PROMPT_VALUE})

    assert surface.calls == []
    assert runtime.calls == []
    assert result["status"] == "rejected"
    assert result["error_code"] == "unsafe_material"
    assert result["side_effects"] == []
    assert_no_raw_values(result)


def test_phase32_source_forbids_gateway_wiring_adapters_hidden_lifecycle_and_config_writes() -> None:
    source = MODULE_SOURCE.read_text()
    tree = ast.parse(source)

    assert "gateway.run" not in source
    assert "gateway.platforms" not in source
    assert "run_agent" not in source
    assert "AIAgent" not in source
    assert "model_tools" not in source
    assert "toolsets" not in source
    assert "Client.connect" not in source
    assert "WorkflowEnvironment" not in source
    assert "from temporalio.worker import Worker" not in source
    assert "Worker(" not in source
    assert "save_config" not in source
    assert "yaml.safe_dump" not in source

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)
    assert not any(name == "subprocess" or name.startswith("subprocess.") for name in imported_modules)
    assert not any(name == "socket" or name.startswith("socket.") for name in imported_modules)
    assert not any("docker" in name.lower() for name in imported_modules)

    forbidden_call_names = {
        "send",
        "edit",
        "render",
        "callback",
        "acknowledge",
        "send_message",
        "send_interactive_card",
        "patch_interactive_card",
        "open",
        "write",
        "write_text",
        "Popen",
        "run",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            assert name not in forbidden_call_names


def _changed_files() -> set[str]:
    commands = [
        ["git", "diff", "--name-only", "origin/feature/sachima-channel...HEAD"],
        ["git", "diff", "--name-only"],
        ["git", "diff", "--cached", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    changed: set[str] = set()
    for command in commands:
        output = subprocess.check_output(command, cwd=ROOT, text=True)
        changed.update(line for line in output.splitlines() if line)
    return changed


def test_phase32_changed_file_guard_allows_only_delivery_activity_files_and_guard_maintenance() -> None:
    changed = _changed_files()
    allowed = {
        "gateway/flowweaver_delivery_activity.py",
        "tests/gateway/test_flowweaver_delivery_activity.py",
        "tests/integration/test_flowweaver_phase32_delivery_activity_ack_reconciliation.py",
        "docs/runbooks/flowweaver-delivery-activity-ack-reconciliation.md",
        "docs/plans/2026-05-09-flowweaver-phase32-delivery-activity-ack-reconciliation.md",
        "docs/dev_log/2026-05-09-flowweaver-phase32-delivery-activity-ack-reconciliation.md",
        "gateway/flowweaver_ai_flow_pilot.py",
        "tests/gateway/test_flowweaver_ai_flow_pilot.py",
        "tests/integration/test_flowweaver_phase33_ai_flow_pilot.py",
        "docs/runbooks/flowweaver-ai-flow-pilot.md",
        "docs/plans/2026-05-09-flowweaver-phase33-ai-flow-pilot.md",
        "docs/dev_log/2026-05-09-flowweaver-phase33-ai-flow-pilot.md",
        "tests/gateway/test_flowweaver_agent_execution_activity.py",
        "tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation_validation.py",
        "tests/gateway/test_flowweaver_stub_activity_orchestration.py",
        "tests/gateway/test_flowweaver_stub_activity_orchestration_validation.py",
        "tests/gateway/test_flowweaver_stub_activity_boundary_contract.py",
        "tests/gateway/test_flowweaver_stub_activity_boundary_contract_validation.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation_design.py",
        "tests/gateway/test_flowweaver_production_shadow_observation.py",
        "tests/gateway/test_flowweaver_shadow_publisher.py",
        "tests/gateway/test_flowweaver_temporal_observation_bridge.py",
        "tests/gateway/test_flowweaver_temporal_observation_validation_gate.py",
        "tests/integration/test_flowweaver_phase31_agent_execution_activity.py",
    }
    forbidden_prefixes = (
        "gateway/platforms/",
        "tools/",
        "plugins/",
        "cron/",
    )
    forbidden_exact = {"gateway/run.py", "run_agent.py", "model_tools.py", "toolsets.py"}

    assert sorted(changed - allowed) == []
    assert not [path for path in changed if path in forbidden_exact or path.startswith(forbidden_prefixes)]
