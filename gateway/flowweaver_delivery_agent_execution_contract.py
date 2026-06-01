"""Pure FlowWeaver Phase 22 delivery/agent execution contract gate.

This module is intentionally synchronous and side-effect free. It freezes the
safe contract shape for future stub Activity orchestration without starting a
Temporal client, touching Gateway adapters, writing config, or executing agents.
"""

from __future__ import annotations

import copy
from typing import Any

FLOWWEAVER_DELIVERY_AGENT_EXECUTION_CONTRACT_TYPE = "flowweaver.gateway.delivery_agent_execution_contract.v0"
FLOWWEAVER_DELIVERY_AGENT_EXECUTION_SUCCESS_VERDICT = "ready_for_stub_activity_orchestration"
FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION = "flowweaver.delivery_agent_execution.v0"

_CONTRACT_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "scope",
    "contract_objects",
    "canonical_ids",
    "allowed_statuses",
    "claim_check_policy",
    "separate_approvals",
    "ownership_boundaries",
    "forbidden_side_effects",
    "side_effects",
]
_EXECUTION_REQUEST_FIELDS = [
    "type",
    "version",
    "transaction_id",
    "workflow_id",
    "intent_id",
    "execution_mode",
    "input_refs",
    "delivery_refs",
    "approval_gates",
    "side_effects",
]
_EXECUTION_RESULT_FIELDS = [
    "type",
    "version",
    "transaction_id",
    "workflow_id",
    "intent_id",
    "status",
    "artifact_refs",
    "delivery_refs",
    "error_code",
    "side_effects",
]
_DELIVERY_ACK_UPDATE_FIELDS = [
    "type",
    "version",
    "transaction_id",
    "workflow_id",
    "delivery_id",
    "surface",
    "status",
    "artifact_ref",
    "ack_ref",
    "occurred_at",
    "side_effects",
]
_PROGRESS_SNAPSHOT_FIELDS = [
    "type",
    "version",
    "transaction_id",
    "workflow_id",
    "status",
    "intent_statuses",
    "artifact_refs",
    "delivery_statuses",
    "counts",
    "side_effects",
]
_REFERENCE_FIELDS = ["ref", "kind", "count", "size", "checksum_hint"]
_FORBIDDEN_MATERIAL = [
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
    "callback_payload",
    "delivery_ack_payload",
    "credential",
    "token",
    "secret",
    "raw_exception_text",
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
]
_ALLOWED_STATUSES = {
    "execution_result": ["accepted", "running", "succeeded", "failed", "canceled"],
    "delivery_ack": ["sent", "failed", "acknowledged"],
    "progress_snapshot": ["pending", "running", "waiting_for_user", "completed", "failed", "canceled"],
}
_ALLOWED_DELIVERY_SURFACES = ["final_text", "rich_card", "media"]
_ALLOWED_EXECUTION_MODES = ["stub_activity_orchestration"]
_ALLOWED_INTENT_STATUSES = ["pending", "running", "waiting_for_user", "completed", "failed", "canceled"]
_ALLOWED_DELIVERY_SNAPSHOT_STATUSES = ["planned", "sent", "failed", "acknowledged"]
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
_PRIVATE_OR_RAW_ID_MARKERS = (
    "oc_",
    "ou_",
    "om_",
    "chat_",
    "user_",
    "message_",
    "platform_",
    "feishu_",
    "lark_",
    "telegram_",
    "raw_",
    "tool_output",
    "platform_payload",
    "token",
    "secret",
    "password",
    "credential",
    "api_key",
    "bearer",
    "sk-",
)


def describe_flowweaver_delivery_agent_execution_contract() -> dict[str, object]:
    """Return the exact Phase 22 delivery/agent execution contract descriptor."""

    return {
        "type": FLOWWEAVER_DELIVERY_AGENT_EXECUTION_CONTRACT_TYPE,
        "version": FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION,
        "phase": "phase22",
        "verdict": FLOWWEAVER_DELIVERY_AGENT_EXECUTION_SUCCESS_VERDICT,
        "scope": "delivery_agent_execution_contract_gate",
        "contract_objects": [
            {
                "name": "FlowWeaverExecutionRequest",
                "fields": list(_EXECUTION_REQUEST_FIELDS),
                "side_effects": [],
            },
            {
                "name": "FlowWeaverExecutionResult",
                "fields": list(_EXECUTION_RESULT_FIELDS),
                "side_effects": [],
            },
            {
                "name": "FlowWeaverDeliveryAckUpdate",
                "fields": list(_DELIVERY_ACK_UPDATE_FIELDS),
                "side_effects": [],
            },
            {
                "name": "FlowWeaverProgressSnapshot",
                "fields": list(_PROGRESS_SNAPSHOT_FIELDS),
                "side_effects": [],
            },
        ],
        "canonical_ids": {
            "transaction_id": {"kind": "canonical", "prefix": "runtime_tx_"},
            "workflow_id": {"kind": "transport_alias", "must_equal": "transaction_id"},
            "intent_id": {"kind": "canonical", "prefix": "runtime_intent_", "numeric_suffix": "strict_unpadded"},
            "delivery_id": {"kind": "canonical", "prefix": "runtime_delivery_", "numeric_suffix": "strict_unpadded"},
            "artifact_ref": {"kind": "canonical", "prefix": "runtime_artifact_", "numeric_suffix": "strict_unpadded"},
            "ack_ref": {"kind": "canonical", "prefix": "runtime_event_"},
            "claim_ref": {"kind": "claim_check_reference", "prefix": "claim_ref_"},
        },
        "allowed_statuses": copy.deepcopy(_ALLOWED_STATUSES),
        "claim_check_policy": {
            "mode": "references_only",
            "allowed_reference_fields": list(_REFERENCE_FIELDS),
            "forbidden_material": list(_FORBIDDEN_MATERIAL),
        },
        "separate_approvals": list(_SEPARATE_APPROVALS),
        "ownership_boundaries": {
            "temporal": "orchestrates_state_only",
            "hermes_agent": "executes_only_through_future_activity_boundary",
            "gateway": "owns_render_and_delivery_until_separately_approved_ack_control",
        },
        "forbidden_side_effects": list(_FORBIDDEN_SIDE_EFFECTS),
        "side_effects": [],
    }


def validate_flowweaver_delivery_agent_execution_contract(value: object) -> dict[str, object]:
    """Validate and return a safe copy of the exact Phase 22 contract."""

    expected = describe_flowweaver_delivery_agent_execution_contract()
    _assert_exact(value, expected, "invalid_contract")
    return describe_flowweaver_delivery_agent_execution_contract()


def build_flowweaver_execution_request(fields: object) -> dict[str, object]:
    """Validate and return a safe ``FlowWeaverExecutionRequest`` dict."""

    error = "invalid_execution_request"
    source = _plain_dict_with_fields(fields, _EXECUTION_REQUEST_FIELDS, error)
    transaction_id = _runtime_id(source["transaction_id"], prefix="runtime_tx_", error=error)
    workflow_id = _workflow_alias(source["workflow_id"], transaction_id=transaction_id, error=error)
    return {
        "type": _literal(source["type"], "FlowWeaverExecutionRequest", error),
        "version": _literal(source["version"], FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION, error),
        "transaction_id": transaction_id,
        "workflow_id": workflow_id,
        "intent_id": _runtime_id(source["intent_id"], prefix="runtime_intent_", error=error, strict_numeric_suffix=True),
        "execution_mode": _one_of(source["execution_mode"], _ALLOWED_EXECUTION_MODES, error),
        "input_refs": _claim_ref_list(source["input_refs"], error=error),
        "delivery_refs": _runtime_id_list(source["delivery_refs"], prefix="runtime_delivery_", error=error, strict_numeric_suffix=True),
        "approval_gates": _exact_string_list(source["approval_gates"], _SEPARATE_APPROVALS, error),
        "side_effects": _empty_list(source["side_effects"], error),
    }


def build_flowweaver_execution_result(fields: object) -> dict[str, object]:
    """Validate and return a safe ``FlowWeaverExecutionResult`` dict."""

    error = "invalid_execution_result"
    source = _plain_dict_with_fields(fields, _EXECUTION_RESULT_FIELDS, error)
    transaction_id = _runtime_id(source["transaction_id"], prefix="runtime_tx_", error=error)
    return {
        "type": _literal(source["type"], "FlowWeaverExecutionResult", error),
        "version": _literal(source["version"], FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION, error),
        "transaction_id": transaction_id,
        "workflow_id": _workflow_alias(source["workflow_id"], transaction_id=transaction_id, error=error),
        "intent_id": _runtime_id(source["intent_id"], prefix="runtime_intent_", error=error, strict_numeric_suffix=True),
        "status": _one_of(source["status"], _ALLOWED_STATUSES["execution_result"], error),
        "artifact_refs": _runtime_id_list(source["artifact_refs"], prefix="runtime_artifact_", error=error, strict_numeric_suffix=True),
        "delivery_refs": _runtime_id_list(source["delivery_refs"], prefix="runtime_delivery_", error=error, strict_numeric_suffix=True),
        "error_code": _optional_safe_code(source["error_code"], error),
        "side_effects": _empty_list(source["side_effects"], error),
    }


def build_flowweaver_delivery_ack_update(fields: object) -> dict[str, object]:
    """Validate and return a safe ``FlowWeaverDeliveryAckUpdate`` dict."""

    error = "invalid_delivery_ack_update"
    source = _plain_dict_with_fields(fields, _DELIVERY_ACK_UPDATE_FIELDS, error)
    transaction_id = _runtime_id(source["transaction_id"], prefix="runtime_tx_", error=error)
    return {
        "type": _literal(source["type"], "FlowWeaverDeliveryAckUpdate", error),
        "version": _literal(source["version"], FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION, error),
        "transaction_id": transaction_id,
        "workflow_id": _workflow_alias(source["workflow_id"], transaction_id=transaction_id, error=error),
        "delivery_id": _runtime_id(source["delivery_id"], prefix="runtime_delivery_", error=error, strict_numeric_suffix=True),
        "surface": _one_of(source["surface"], _ALLOWED_DELIVERY_SURFACES, error),
        "status": _one_of(source["status"], _ALLOWED_STATUSES["delivery_ack"], error),
        "artifact_ref": _runtime_id(source["artifact_ref"], prefix="runtime_artifact_", error=error, strict_numeric_suffix=True),
        "ack_ref": _runtime_id(source["ack_ref"], prefix="runtime_event_", error=error),
        "occurred_at": _safe_text(source["occurred_at"], error=error),
        "side_effects": _empty_list(source["side_effects"], error),
    }


def build_flowweaver_progress_snapshot(fields: object) -> dict[str, object]:
    """Validate and return a safe ``FlowWeaverProgressSnapshot`` dict."""

    error = "invalid_progress_snapshot"
    source = _plain_dict_with_fields(fields, _PROGRESS_SNAPSHOT_FIELDS, error)
    transaction_id = _runtime_id(source["transaction_id"], prefix="runtime_tx_", error=error)
    return {
        "type": _literal(source["type"], "FlowWeaverProgressSnapshot", error),
        "version": _literal(source["version"], FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION, error),
        "transaction_id": transaction_id,
        "workflow_id": _workflow_alias(source["workflow_id"], transaction_id=transaction_id, error=error),
        "status": _one_of(source["status"], _ALLOWED_STATUSES["progress_snapshot"], error),
        "intent_statuses": _status_map(
            source["intent_statuses"],
            key_prefix="runtime_intent_",
            statuses=_ALLOWED_INTENT_STATUSES,
            error=error,
        ),
        "artifact_refs": _runtime_id_list(source["artifact_refs"], prefix="runtime_artifact_", error=error, strict_numeric_suffix=True),
        "delivery_statuses": _status_map(
            source["delivery_statuses"],
            key_prefix="runtime_delivery_",
            statuses=_ALLOWED_DELIVERY_SNAPSHOT_STATUSES,
            error=error,
        ),
        "counts": _counts(source["counts"], error=error),
        "side_effects": _empty_list(source["side_effects"], error),
    }


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


def _plain_dict_with_fields(value: object, fields: list[str], error: str) -> dict[str, object]:
    if type(value) is not dict or list(value) != fields:
        _raise(error)
    _reject_unsafe(value, error=error)
    return value


def _literal(value: object, expected: str, error: str) -> str:
    if type(value) is not str or value != expected:
        _raise(error)
    return value


def _one_of(value: object, allowed: list[str], error: str) -> str:
    if type(value) is not str or value not in allowed:
        _raise(error)
    return value


def _safe_text(value: object, *, error: str) -> str:
    if type(value) is not str or not value or len(value) > 120:
        _raise(error)
    _reject_unsafe_string(value, error=error)
    return value


def _optional_safe_code(value: object, error: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or not value or len(value) > 80:
        _raise(error)
    _reject_unsafe_string(value, error=error)
    return value


def _workflow_alias(value: object, *, transaction_id: str, error: str) -> str:
    workflow_id = _runtime_id(value, prefix="runtime_tx_", error=error)
    if workflow_id != transaction_id:
        _raise(error)
    return workflow_id


def _runtime_id(value: object, *, prefix: str, error: str, strict_numeric_suffix: bool = False) -> str:
    if type(value) is not str or not value.startswith(prefix):
        _raise(error)
    _reject_unsafe_string(value, error=error)
    suffix = value[len(prefix) :]
    if not suffix:
        _raise(error)
    lowered = suffix.lower()
    if any(marker in lowered for marker in _PRIVATE_OR_RAW_ID_MARKERS):
        _raise(error)
    if strict_numeric_suffix:
        if not suffix.isdecimal():
            _raise(error)
        if suffix != "0" and suffix.startswith("0"):
            _raise(error)
    return value


def _claim_ref(value: object, *, error: str) -> dict[str, object]:
    if type(value) is not dict or list(value) != _REFERENCE_FIELDS:
        _raise(error)
    ref = _runtime_id(value["ref"], prefix="claim_ref_", error=error)
    kind = _safe_text(value["kind"], error=error)
    count = _plain_int(value["count"], error=error)
    size = _plain_int(value["size"], error=error)
    checksum_hint = _checksum_hint(value["checksum_hint"], error=error)
    return {"ref": ref, "kind": kind, "count": count, "size": size, "checksum_hint": checksum_hint}


def _claim_ref_list(value: object, *, error: str) -> list[dict[str, object]]:
    if type(value) is not list or not value:
        _raise(error)
    return [_claim_ref(item, error=error) for item in value]


def _runtime_id_list(value: object, *, prefix: str, error: str, strict_numeric_suffix: bool = False) -> list[str]:
    if type(value) is not list or not value:
        _raise(error)
    return [_runtime_id(item, prefix=prefix, error=error, strict_numeric_suffix=strict_numeric_suffix) for item in value]


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


def _plain_int(value: object, *, error: str) -> int:
    if type(value) is not int or value < 0:
        _raise(error)
    return value


def _checksum_hint(value: object, *, error: str) -> str:
    if type(value) is not str or not value.startswith("sha256:") or len(value) != 71:
        _raise(error)
    digest = value.removeprefix("sha256:")
    if any(char not in "0123456789abcdef" for char in digest):
        _raise(error)
    return value


def _status_map(value: object, *, key_prefix: str, statuses: list[str], error: str) -> dict[str, str]:
    if type(value) is not dict or not value:
        _raise(error)
    safe: dict[str, str] = {}
    for key, status in value.items():
        safe_key = _runtime_id(key, prefix=key_prefix, error=error, strict_numeric_suffix=True)
        safe[safe_key] = _one_of(status, statuses, error)
    return safe


def _counts(value: object, *, error: str) -> dict[str, int]:
    expected = ["intents", "artifacts", "deliveries"]
    if type(value) is not dict or list(value) != expected:
        _raise(error)
    return {key: _plain_int(value[key], error=error) for key in expected}


def _reject_unsafe(value: object, *, error: str) -> None:
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                _raise(error)
            lowered_key = key.lower()
            if any(marker == lowered_key or marker in lowered_key for marker in _FORBIDDEN_MATERIAL):
                _raise(error)
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
