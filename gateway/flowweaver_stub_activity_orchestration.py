"""Pure FlowWeaver Phase 23 stub Activity orchestration helper.

This module is intentionally synchronous and side-effect free. It consumes the
Phase 22 delivery/agent execution contract, validates a single canonical
``FlowWeaverExecutionRequest``, and returns only sanitized stub orchestration
objects. It does not construct Temporal clients, start Workers, touch Gateway
hooks, or execute real agent/delivery behavior.
"""

from __future__ import annotations

import copy
from typing import Any

from gateway.flowweaver_delivery_agent_execution_contract import (
    FLOWWEAVER_DELIVERY_AGENT_EXECUTION_CONTRACT_TYPE,
    FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION,
    build_flowweaver_execution_request,
    build_flowweaver_execution_result,
    build_flowweaver_progress_snapshot,
    validate_flowweaver_delivery_agent_execution_contract,
)

FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_CONTRACT_TYPE = "flowweaver.gateway.stub_activity_orchestration_contract.v0"
FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_RESULT_TYPE = "flowweaver.gateway.stub_activity_orchestration_result.v0"
FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT = "ready_for_stub_activity_orchestration_validation"
FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VERSION = "flowweaver.stub_activity_orchestration.v0"

_CONTRACT_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "scope",
    "consumes_contract",
    "entrypoints",
    "activity_sequence",
    "result_fields",
    "checks",
    "separate_approvals",
    "forbidden_side_effects",
    "side_effects",
]
_RESULT_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "operation",
    "activity_sequence",
    "execution_request",
    "execution_result",
    "progress_snapshot",
    "delivery_ack_updates",
    "checks",
    "forbidden_side_effects",
    "side_effects",
]
_ACTIVITY_SEQUENCE = [
    "validate_claim_check_ref",
    "execute_agent_turn",
    "deliver_artifact",
]
_ENTRYPOINTS = [
    "describe_flowweaver_stub_activity_orchestration_contract",
    "validate_flowweaver_stub_activity_orchestration_result",
    "orchestrate_flowweaver_stub_activities",
]
_CHECKS = [
    "phase22_contract_descriptor_valid",
    "execution_request_valid",
    "activity_sequence_stubbed",
    "delivery_ack_updates_absent",
    "side_effects_absent",
]
_SEPARATE_APPROVALS = [
    "live_config_writes",
    "gateway_restart",
    "production_enablement",
    "real_send_edit_render_callback_control",
    "real_agent_tool_execution",
]
_FORBIDDEN_SIDE_EFFECTS = [
    "temporal_client",
    "worker_lifecycle",
    "gateway_hook_change",
    "config_write",
    "file_write",
    "subprocess",
    "socket",
    "send",
    "edit",
    "render",
    "callback_control",
    "agent_execution",
    "tool_execution",
    "temporal_activity_execution",
]
_RAW_VALUE_MARKERS = (
    "oc_",
    "ou_",
    "om_",
    "raw prompt",
    "tool output",
    "card_json",
    "media_path",
    "/tmp/",
    "callback payload",
    "runtimeerror:",
    "valueerror:",
    "unsafe-token",
    "bearer ",
    "password=",
    "secret=",
    "api_key=",
    "sk-",
)


def describe_flowweaver_stub_activity_orchestration_contract() -> dict[str, object]:
    """Return the exact Phase 23 stub Activity orchestration contract."""

    return {
        "type": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_CONTRACT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VERSION,
        "phase": "phase23",
        "verdict": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT,
        "scope": "stub_activity_orchestration",
        "consumes_contract": FLOWWEAVER_DELIVERY_AGENT_EXECUTION_CONTRACT_TYPE,
        "entrypoints": list(_ENTRYPOINTS),
        "activity_sequence": list(_ACTIVITY_SEQUENCE),
        "result_fields": list(_RESULT_FIELDS),
        "checks": list(_CHECKS),
        "separate_approvals": list(_SEPARATE_APPROVALS),
        "forbidden_side_effects": list(_FORBIDDEN_SIDE_EFFECTS),
        "side_effects": [],
    }


def validate_flowweaver_stub_activity_orchestration_result(value: object) -> dict[str, object]:
    """Validate and return a sanitized Phase 23 orchestration result copy."""

    error = "invalid_stub_activity_orchestration_result"
    source = _plain_dict_with_fields(value, _RESULT_FIELDS, error)
    try:
        execution_request = build_flowweaver_execution_request(source["execution_request"])
        _validate_single_stub_request(execution_request, error=error)
        execution_result = build_flowweaver_execution_result(source["execution_result"])
        progress_snapshot = build_flowweaver_progress_snapshot(source["progress_snapshot"])
    except ValueError:
        _raise(error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_RESULT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VERSION, error),
        "phase": _literal(source["phase"], "phase23", error),
        "verdict": _literal(source["verdict"], FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT, error),
        "operation": _literal(source["operation"], "orchestrate_flowweaver_stub_activities", error),
        "activity_sequence": _activity_sequence(source["activity_sequence"], execution_request, error=error),
        "execution_request": execution_request,
        "execution_result": _validate_execution_result_matches_request(execution_result, execution_request, error=error),
        "progress_snapshot": _validate_progress_snapshot_matches_request(progress_snapshot, execution_request, error=error),
        "delivery_ack_updates": _empty_list(source["delivery_ack_updates"], error),
        "checks": _checks(source["checks"], error=error),
        "forbidden_side_effects": _exact_string_list(source["forbidden_side_effects"], _FORBIDDEN_SIDE_EFFECTS, error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    _reject_unsafe(safe, error=error)
    return safe


def orchestrate_flowweaver_stub_activities(*, execution_request: object, contract_descriptor: object) -> dict[str, object]:
    """Build a sanitized Phase 23 stub orchestration result.

    The function validates the Phase 22 contract descriptor and a single
    canonical execution request, then creates planned/stubbed artifacts only.
    It does not execute activities, call agent/tools, produce delivery ACKs, or
    own any runtime lifecycle.
    """

    validate_flowweaver_delivery_agent_execution_contract(contract_descriptor)
    request = build_flowweaver_execution_request(execution_request)
    _validate_single_stub_request(request, error="invalid_stub_activity_orchestration_request")
    execution_result = build_flowweaver_execution_result(
        {
            "type": "FlowWeaverExecutionResult",
            "version": FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION,
            "transaction_id": request["transaction_id"],
            "workflow_id": request["workflow_id"],
            "intent_id": request["intent_id"],
            "status": "accepted",
            "artifact_refs": ["runtime_artifact_0"],
            "delivery_refs": list(request["delivery_refs"]),
            "error_code": None,
            "side_effects": [],
        }
    )
    progress_snapshot = build_flowweaver_progress_snapshot(
        {
            "type": "FlowWeaverProgressSnapshot",
            "version": FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION,
            "transaction_id": request["transaction_id"],
            "workflow_id": request["workflow_id"],
            "status": "running",
            "intent_statuses": {request["intent_id"]: "running"},
            "artifact_refs": ["runtime_artifact_0"],
            "delivery_statuses": {"runtime_delivery_0": "planned"},
            "counts": {"intents": 1, "artifacts": 1, "deliveries": 1},
            "side_effects": [],
        }
    )
    result = {
        "type": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_RESULT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VERSION,
        "phase": "phase23",
        "verdict": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT,
        "operation": "orchestrate_flowweaver_stub_activities",
        "activity_sequence": [
            {
                "name": "validate_claim_check_ref",
                "status": "stubbed",
                "input_refs": [item["ref"] for item in request["input_refs"]],
                "side_effects": [],
            },
            {
                "name": "execute_agent_turn",
                "status": "stubbed",
                "intent_id": request["intent_id"],
                "side_effects": [],
            },
            {
                "name": "deliver_artifact",
                "status": "planned",
                "delivery_refs": list(request["delivery_refs"]),
                "side_effects": [],
            },
        ],
        "execution_request": request,
        "execution_result": execution_result,
        "progress_snapshot": progress_snapshot,
        "delivery_ack_updates": [],
        "checks": {
            "phase22_contract_descriptor_valid": True,
            "execution_request_valid": True,
            "activity_sequence_stubbed": True,
            "delivery_ack_updates_absent": True,
            "side_effects_absent": True,
        },
        "forbidden_side_effects": list(_FORBIDDEN_SIDE_EFFECTS),
        "side_effects": [],
    }
    return validate_flowweaver_stub_activity_orchestration_result(result)


def _plain_dict_with_fields(value: object, fields: list[str], error: str) -> dict[str, object]:
    if type(value) is not dict or list(value) != fields:
        _raise(error)
    _reject_unsafe(value, error=error)
    return value


def _literal(value: object, expected: str, error: str) -> str:
    if type(value) is not str or value != expected:
        _raise(error)
    return value


def _exact_string_list(value: object, expected: list[str], error: str) -> list[str]:
    if type(value) is not list or len(value) != len(expected):
        _raise(error)
    for item, expected_item in zip(value, expected, strict=True):
        if type(item) is not str or item != expected_item:
            _raise(error)
    return list(expected)


def _empty_list(value: object, error: str) -> list[object]:
    if type(value) is not list or value:
        _raise(error)
    return []


def _checks(value: object, *, error: str) -> dict[str, bool]:
    expected = list(_CHECKS)
    if type(value) is not dict or list(value) != expected:
        _raise(error)
    safe: dict[str, bool] = {}
    for key in expected:
        if value[key] is not True:
            _raise(error)
        safe[key] = True
    return safe


def _activity_sequence(value: object, request: dict[str, object], *, error: str) -> list[dict[str, object]]:
    expected = [
        {
            "name": "validate_claim_check_ref",
            "status": "stubbed",
            "input_refs": [item["ref"] for item in request["input_refs"]],
            "side_effects": [],
        },
        {
            "name": "execute_agent_turn",
            "status": "stubbed",
            "intent_id": request["intent_id"],
            "side_effects": [],
        },
        {
            "name": "deliver_artifact",
            "status": "planned",
            "delivery_refs": list(request["delivery_refs"]),
            "side_effects": [],
        },
    ]
    _assert_exact(value, expected, error)
    return copy.deepcopy(expected)


def _validate_single_stub_request(request: dict[str, object], *, error: str) -> None:
    if request["intent_id"] != "runtime_intent_0":
        _raise(error)
    if request["delivery_refs"] != ["runtime_delivery_0"]:
        _raise(error)
    if type(request["input_refs"]) is not list or len(request["input_refs"]) != 1:
        _raise(error)
    input_ref = request["input_refs"][0]
    if type(input_ref) is not dict or input_ref.get("kind") != "agent_input":
        _raise(error)
    if request["execution_mode"] != "stub_activity_orchestration":
        _raise(error)


def _validate_execution_result_matches_request(
    result: dict[str, object], request: dict[str, object], *, error: str
) -> dict[str, object]:
    expected = {
        "type": "FlowWeaverExecutionResult",
        "version": FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION,
        "transaction_id": request["transaction_id"],
        "workflow_id": request["workflow_id"],
        "intent_id": request["intent_id"],
        "status": "accepted",
        "artifact_refs": ["runtime_artifact_0"],
        "delivery_refs": ["runtime_delivery_0"],
        "error_code": None,
        "side_effects": [],
    }
    _assert_exact(result, expected, error)
    return copy.deepcopy(expected)


def _validate_progress_snapshot_matches_request(
    snapshot: dict[str, object], request: dict[str, object], *, error: str
) -> dict[str, object]:
    expected = {
        "type": "FlowWeaverProgressSnapshot",
        "version": FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION,
        "transaction_id": request["transaction_id"],
        "workflow_id": request["workflow_id"],
        "status": "running",
        "intent_statuses": {"runtime_intent_0": "running"},
        "artifact_refs": ["runtime_artifact_0"],
        "delivery_statuses": {"runtime_delivery_0": "planned"},
        "counts": {"intents": 1, "artifacts": 1, "deliveries": 1},
        "side_effects": [],
    }
    _assert_exact(snapshot, expected, error)
    return copy.deepcopy(expected)


def _assert_exact(value: object, expected: object, error: str) -> None:
    if type(expected) is dict:
        if type(value) is not dict or list(value) != list(expected):
            _raise(error)
        for key, expected_value in expected.items():
            _assert_exact(value[key], expected_value, error)
        return
    if type(expected) is list:
        if type(value) is not list or len(value) != len(expected):
            _raise(error)
        for item, expected_item in zip(value, expected, strict=True):
            _assert_exact(item, expected_item, error)
        return
    if expected is None:
        if value is not None:
            _raise(error)
        return
    if type(value) is not type(expected) or value != expected:
        _raise(error)


def _reject_unsafe(value: object, *, error: str) -> None:
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                _raise(error)
            _reject_unsafe_string(key, error=error)
            _reject_unsafe(item, error=error)
        return
    if type(value) is list:
        for item in value:
            _reject_unsafe(item, error=error)
        return
    if type(value) is str:
        _reject_unsafe_string(value, error=error)


def _reject_unsafe_string(value: str, *, error: str) -> None:
    lowered = value.lower()
    if any(marker in lowered for marker in _RAW_VALUE_MARKERS):
        _raise(error)


def _raise(error: str) -> None:
    raise ValueError(error)
