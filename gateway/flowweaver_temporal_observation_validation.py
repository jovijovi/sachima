"""Pure Phase 20 validation helpers for FlowWeaver Temporal observation evidence."""

from __future__ import annotations

import re
from typing import Any

from gateway.flowweaver_temporal_observation_bridge import (
    FLOWWEAVER_TEMPORAL_OBSERVATION_BRIDGE_VERSION,
    TEMPORAL_OBSERVATION_BRIDGE_RESULT_TYPE,
    TEMPORAL_OBSERVATION_SUCCESS_VERDICT,
)

FLOWWEAVER_TEMPORAL_OBSERVATION_VALIDATION_VERSION = "flowweaver.temporal_observation_validation.v0"
TEMPORAL_OBSERVATION_VALIDATION_REPORT_TYPE = "flowweaver.gateway.temporal_observation_validation_report.v0"
TEMPORAL_OBSERVATION_DUPLICATE_START_REPORT_TYPE = "flowweaver.gateway.temporal_observation_duplicate_start.v0"
TEMPORAL_OBSERVATION_ROLLBACK_DRILL_REPORT_TYPE = "flowweaver.gateway.temporal_observation_rollback_drill.v0"
TEMPORAL_OBSERVATION_VALIDATION_SUCCESS_VERDICT = "ready_for_production_shadow_observation_request"

_OPERATION = "validate_gateway_observation_against_temporal"
_ROLLBACK_ACTIONS = ["disable_observation_policy", "verify_existing_snapshot"]
_TOOL_OUTPUT_KEY_RE = re.compile(r"[\"']tool_output[\"']\s*:")
_ALLOWED_ERRORS = {
    "invalid_bridge_result",
    "invalid_duplicate_start_report",
    "invalid_history_evidence",
    "invalid_rollback_drill",
    "history_contains_forbidden_material",
}


def build_temporal_observation_duplicate_start_report(
    *,
    first_bridge_result: object,
    duplicate_bridge_result: object,
) -> dict[str, object]:
    """Summarize duplicate-start behavior without echoing raw bridge payloads."""

    try:
        first = _validate_successful_bridge_result(first_bridge_result)
        duplicate = _validate_successful_bridge_result(duplicate_bridge_result)
        if first["workflow_id"] != duplicate["workflow_id"] or first["transaction_id"] != duplicate["transaction_id"]:
            _raise("invalid_duplicate_start_report")
        first_status = _bridge_start_status(first, error="invalid_duplicate_start_report")
        duplicate_status = _bridge_start_status(duplicate, error="invalid_duplicate_start_report")
        if duplicate_status != "running":
            _raise("invalid_duplicate_start_report")
        report = {
            "type": TEMPORAL_OBSERVATION_DUPLICATE_START_REPORT_TYPE,
            "version": FLOWWEAVER_TEMPORAL_OBSERVATION_VALIDATION_VERSION,
            "status": "idempotent",
            "workflow_id": first["workflow_id"],
            "start_statuses": [first_status, duplicate_status],
            "side_effects": [],
        }
        _assert_no_forbidden_rendered_material(report, error="invalid_duplicate_start_report")
        return report
    except ValueError:
        return _safe_aux_error(
            report_type=TEMPORAL_OBSERVATION_DUPLICATE_START_REPORT_TYPE,
            error_code="invalid_duplicate_start_report",
        )


def build_temporal_observation_rollback_drill_report(
    *,
    enabled_bridge_result: object,
    disabled_bridge_result: object,
    existing_query_result: object,
) -> dict[str, object]:
    """Summarize the local kill-switch drill using only safe action labels."""

    try:
        enabled = _validate_successful_bridge_result(enabled_bridge_result)
        disabled = _plain_dict(disabled_bridge_result, error="invalid_rollback_drill")
        _reject_unsafe_material(disabled, error="invalid_rollback_drill")
        if not (
            disabled.get("type") == TEMPORAL_OBSERVATION_BRIDGE_RESULT_TYPE
            and disabled.get("version") == FLOWWEAVER_TEMPORAL_OBSERVATION_BRIDGE_VERSION
            and disabled.get("ok") is False
            and disabled.get("operation") == "observe_gateway_turn_for_flowweaver_temporal"
            and disabled.get("status") == "disabled"
            and disabled.get("error_code") == "disabled"
            and disabled.get("side_effects") == []
        ):
            _raise("invalid_rollback_drill")
        query = _validate_existing_query_result(existing_query_result, workflow_id=str(enabled["workflow_id"]))
        report = {
            "type": TEMPORAL_OBSERVATION_ROLLBACK_DRILL_REPORT_TYPE,
            "version": FLOWWEAVER_TEMPORAL_OBSERVATION_VALIDATION_VERSION,
            "status": "verified",
            "runtime_mutation_blocked": True,
            "existing_query_safe": query["status"] == "running",
            "operator_actions": list(_ROLLBACK_ACTIONS),
            "side_effects": [],
        }
        _assert_no_forbidden_rendered_material(report, error="invalid_rollback_drill")
        return report
    except ValueError:
        return _safe_aux_error(
            report_type=TEMPORAL_OBSERVATION_ROLLBACK_DRILL_REPORT_TYPE,
            error_code="invalid_rollback_drill",
        )


def build_temporal_observation_validation_report(
    *,
    bridge_result: object,
    history_json: object,
    history_event_bytes: object,
    rollback_drill: object,
    duplicate_start_report: object,
) -> dict[str, object]:
    """Build a sanitized Phase 20 validation report from local Temporal evidence."""

    try:
        bridge = _validate_successful_bridge_result(bridge_result)
        duplicate = _validate_duplicate_start_report(duplicate_start_report)
        rollback = _validate_rollback_drill_report(rollback_drill)
        _validate_history_evidence(history_json=history_json, history_event_bytes=history_event_bytes)
    except ValueError as exc:
        error_code = str(exc) if str(exc) in _ALLOWED_ERRORS else "invalid_bridge_result"
        return _error_report(error_code)

    report = {
        "type": TEMPORAL_OBSERVATION_VALIDATION_REPORT_TYPE,
        "version": FLOWWEAVER_TEMPORAL_OBSERVATION_VALIDATION_VERSION,
        "ok": True,
        "verdict": TEMPORAL_OBSERVATION_VALIDATION_SUCCESS_VERDICT,
        "operation": _OPERATION,
        "bridge_checks": {
            "phase19_verdict": bridge["verdict"],
            "start_query_only": True,
            "side_effects_absent": True,
        },
        "history_checks": {
            "json_scanned": True,
            "event_bytes_scanned": True,
            "forbidden_material_absent": True,
        },
        "duplicate_start": {"status": duplicate["status"], "start_statuses": duplicate["start_statuses"]},
        "rollback": {"status": rollback["status"], "operator_actions": rollback["operator_actions"]},
        "side_effects": [],
    }
    _assert_no_forbidden_rendered_material(report, error="invalid_bridge_result")
    return report


def _validate_successful_bridge_result(value: object) -> dict[str, object]:
    result = _plain_dict(value, error="invalid_bridge_result")
    _reject_unsafe_material(result, error="invalid_bridge_result")
    expected_counts = {"start_transaction": 1, "query_transaction": 1}
    if not (
        result.get("type") == TEMPORAL_OBSERVATION_BRIDGE_RESULT_TYPE
        and result.get("version") == FLOWWEAVER_TEMPORAL_OBSERVATION_BRIDGE_VERSION
        and result.get("ok") is True
        and result.get("verdict") == TEMPORAL_OBSERVATION_SUCCESS_VERDICT
        and result.get("operation") == "observe_gateway_turn_for_flowweaver_temporal"
        and type(result.get("workflow_id")) is str
        and result.get("transaction_id") == result.get("workflow_id")
        and result.get("runtime_call_counts") == expected_counts
        and result.get("side_effects") == []
    ):
        _raise("invalid_bridge_result")
    _bridge_start_status(result, error="invalid_bridge_result")
    if result.get("query_status") not in {"created", "running", "waiting_for_user", "canceled", "completed", "failed"}:
        _raise("invalid_bridge_result")
    workflow_id = str(result["workflow_id"])
    if not workflow_id.startswith("runtime_tx_gateway_observation_") or len(workflow_id) > 128:
        _raise("invalid_bridge_result")
    _validate_bridge_snapshot_summary(result.get("snapshot_summary"))
    _validate_bridge_checks(result.get("checks"))
    _assert_no_forbidden_rendered_material(result, error="invalid_bridge_result")
    return result


def _bridge_start_status(result: dict[str, object], *, error: str) -> str:
    status = result.get("start_status")
    if type(status) is not str or status not in {"started", "running"}:
        _raise(error)
    return status


def _validate_bridge_snapshot_summary(value: object) -> None:
    summary = _plain_dict(value, error="invalid_bridge_result")
    if set(summary) != {"status", "entry_count", "record_counts", "counts", "side_effects"}:
        _raise("invalid_bridge_result")
    if summary["status"] not in {"created", "running", "waiting_for_user", "canceled", "completed", "failed"}:
        _raise("invalid_bridge_result")
    entry_count = summary["entry_count"]
    if type(entry_count) is not int or not (1 <= entry_count <= 20):
        _raise("invalid_bridge_result")
    record_counts = _plain_dict(summary["record_counts"], error="invalid_bridge_result")
    counts = _plain_dict(summary["counts"], error="invalid_bridge_result")
    if record_counts != {"transactions": 1, "intents": entry_count, "artifacts": entry_count, "deliveries": record_counts.get("deliveries")}:
        _raise("invalid_bridge_result")
    if type(record_counts.get("deliveries")) is not int or not (entry_count <= record_counts["deliveries"] <= 20):
        _raise("invalid_bridge_result")
    if counts != {"intents": entry_count, "artifacts": entry_count, "deliveries": record_counts["deliveries"]}:
        _raise("invalid_bridge_result")
    if summary["side_effects"] != []:
        _raise("invalid_bridge_result")


def _validate_bridge_checks(value: object) -> None:
    checks = _plain_dict(value, error="invalid_bridge_result")
    expected = {
        "policy_enabled",
        "observation_safe",
        "start_payload_safe",
        "query_snapshot_safe",
        "runtime_side_effects_absent",
    }
    if set(checks) != expected or not all(checks[key] is True for key in expected):
        _raise("invalid_bridge_result")


def _validate_existing_query_result(value: object, *, workflow_id: str) -> dict[str, object]:
    result = _plain_dict(value, error="invalid_rollback_drill")
    _reject_unsafe_material(result, error="invalid_rollback_drill")
    if not (
        result.get("ok") is True
        and result.get("operation") == "query_transaction"
        and result.get("runtime_operation") == "query_snapshot"
        and result.get("workflow_id") == workflow_id
        and result.get("transaction_id") in {None, workflow_id}
    ):
        _raise("invalid_rollback_drill")
    snapshot = _plain_dict(result.get("snapshot"), error="invalid_rollback_drill")
    if snapshot.get("transaction_id") != workflow_id or snapshot.get("side_effects") != []:
        _raise("invalid_rollback_drill")
    status = snapshot.get("status")
    if type(status) is not str:
        _raise("invalid_rollback_drill")
    _assert_no_forbidden_rendered_material(result, error="invalid_rollback_drill", allow_start_signature=True)
    return {"status": status}


def _validate_duplicate_start_report(value: object) -> dict[str, object]:
    report = _plain_dict(value, error="invalid_duplicate_start_report")
    _reject_unsafe_material(report, error="invalid_duplicate_start_report")
    if not (
        report.get("type") == TEMPORAL_OBSERVATION_DUPLICATE_START_REPORT_TYPE
        and report.get("version") == FLOWWEAVER_TEMPORAL_OBSERVATION_VALIDATION_VERSION
        and report.get("status") == "idempotent"
        and type(report.get("workflow_id")) is str
        and report.get("side_effects") == []
    ):
        _raise("invalid_duplicate_start_report")
    statuses = _plain_list(report.get("start_statuses"), error="invalid_duplicate_start_report")
    if len(statuses) != 2 or statuses[0] not in {"started", "running"} or statuses[1] != "running":
        _raise("invalid_duplicate_start_report")
    _assert_no_forbidden_rendered_material(report, error="invalid_duplicate_start_report")
    return {"status": "idempotent", "start_statuses": [statuses[0], statuses[1]]}


def _validate_rollback_drill_report(value: object) -> dict[str, object]:
    report = _plain_dict(value, error="invalid_rollback_drill")
    _reject_unsafe_material(report, error="invalid_rollback_drill")
    if not (
        report.get("type") == TEMPORAL_OBSERVATION_ROLLBACK_DRILL_REPORT_TYPE
        and report.get("version") == FLOWWEAVER_TEMPORAL_OBSERVATION_VALIDATION_VERSION
        and report.get("status") == "verified"
        and report.get("runtime_mutation_blocked") is True
        and report.get("existing_query_safe") is True
        and report.get("operator_actions") == _ROLLBACK_ACTIONS
        and report.get("side_effects") == []
    ):
        _raise("invalid_rollback_drill")
    _assert_no_forbidden_rendered_material(report, error="invalid_rollback_drill")
    return {"status": "verified", "operator_actions": list(_ROLLBACK_ACTIONS)}


def _validate_history_evidence(*, history_json: object, history_event_bytes: object) -> None:
    if type(history_json) is not str or type(history_event_bytes) is not bytes:
        _raise("invalid_history_evidence")
    if not history_json or not history_event_bytes:
        _raise("invalid_history_evidence")
    if _contains_forbidden_history_material(history_json) or _contains_forbidden_history_material(
        history_event_bytes.decode("utf-8", errors="ignore")
    ):
        _raise("history_contains_forbidden_material")


def _contains_forbidden_history_material(text: str) -> bool:
    lowered = text.lower()
    forbidden_markers = (
        "unsafe-" + "token",
        "sk" + "-",
        "bearer ",
        "raw prompt",
        "raw " + "tool output",
        "callback payload",
        "valueerror:",
        "runtimeerror:",
        "traceback",
        "oc_",
        "ou_",
        "om_",
        "/tmp/",
        "\\tmp\\",
        '"type":"card_json"',
        '"type": "card_json"',
        "'type': 'card_json'",
    )
    return _TOOL_OUTPUT_KEY_RE.search(lowered) is not None or any(marker in lowered for marker in forbidden_markers)


def _safe_aux_error(*, report_type: str, error_code: str) -> dict[str, object]:
    return {
        "type": report_type,
        "version": FLOWWEAVER_TEMPORAL_OBSERVATION_VALIDATION_VERSION,
        "ok": False,
        "error_code": error_code,
        "side_effects": [],
    }


def _error_report(error_code: object) -> dict[str, object]:
    safe_error = error_code if type(error_code) is str and error_code in _ALLOWED_ERRORS else "invalid_bridge_result"
    return {
        "type": TEMPORAL_OBSERVATION_VALIDATION_REPORT_TYPE,
        "version": FLOWWEAVER_TEMPORAL_OBSERVATION_VALIDATION_VERSION,
        "ok": False,
        "operation": _OPERATION,
        "error_code": safe_error,
        "side_effects": [],
    }


def _reject_unsafe_material(value: object, *, error: str) -> None:
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                _raise(error)
            lowered = key.lower()
            if _unsafe_key(lowered):
                _raise(error)
            _reject_unsafe_material(item, error=error)
        return
    if type(value) is list:
        for item in value:
            _reject_unsafe_material(item, error=error)
        return
    if type(value) is str:
        lowered = value.lower()
        if _unsafe_string(lowered):
            _raise(error)
        return
    if type(value) in {bool, int} or value is None:
        return
    _raise(error)


def _unsafe_key(lowered: str) -> bool:
    exact = {"token", "secret"}
    substrings = (
        "raw_",
        "tool_output",
        "platform_payload",
        "chat_id",
        "user_id",
        "message_id",
        "callback",
        "credential",
        "password",
        "api_key",
        "bearer",
        "connection_string",
    )
    return lowered in exact or any(marker in lowered for marker in substrings)


def _unsafe_string(lowered: str) -> bool:
    markers = (
        "unsafe-" + "token",
        "sk" + "-",
        "bearer ",
        "raw prompt",
        "raw " + "tool output",
        "callback payload",
        "valueerror:",
        "runtimeerror:",
        "traceback",
        "/tmp/",
        "\\tmp\\",
        '"type":"card_json"',
        '"type": "card_json"',
    )
    private_prefixes = ("oc_", "ou_", "om_", "feishu_", "lark_", "telegram_")
    return lowered.startswith(private_prefixes) or _TOOL_OUTPUT_KEY_RE.search(lowered) is not None or any(
        marker in lowered for marker in markers
    )


def _plain_dict(value: object, *, error: str) -> dict[str, object]:
    copied = _plain_copy(value)
    if type(copied) is not dict:
        _raise(error)
    return copied


def _plain_list(value: object, *, error: str) -> list[object]:
    copied = _plain_copy(value)
    if type(copied) is not list:
        _raise(error)
    return copied


def _plain_copy(value: object) -> object:
    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is list:
        copied_list: list[object] = []
        for item in value:
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            copied_list.append(copied)
        return copied_list
    if type(value) is dict:
        copied_dict: dict[str, object] = {}
        for key, item in value.items():
            if type(key) is not str:
                return _INVALID
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            copied_dict[key] = copied
        return copied_dict
    return _INVALID


def _assert_no_forbidden_rendered_material(value: object, *, error: str, allow_start_signature: bool = False) -> None:
    rendered = repr(value).lower()
    forbidden = [
        "unsafe-" + "token",
        "sk" + "-",
        "bearer ",
        "raw prompt",
        "raw " + "tool output",
        "callback payload",
        "valueerror:",
        "runtimeerror:",
        "traceback",
        "oc_phase20_private",
        "ou_phase20_private",
        "om_phase20_private",
        "/tmp/phase20",
        '"type":"card_json"',
        '"type": "card_json"',
    ]
    if not allow_start_signature:
        forbidden.extend(["raw_payload", "raw_capture", "platform_payload", "chat_id", "user_id", "message_id"])
    if _TOOL_OUTPUT_KEY_RE.search(rendered) is not None or any(marker in rendered for marker in forbidden):
        _raise(error)


def _raise(error: str) -> None:
    raise ValueError(error) from None


_INVALID = object()

__all__ = [
    "FLOWWEAVER_TEMPORAL_OBSERVATION_VALIDATION_VERSION",
    "TEMPORAL_OBSERVATION_VALIDATION_REPORT_TYPE",
    "TEMPORAL_OBSERVATION_VALIDATION_SUCCESS_VERDICT",
    "build_temporal_observation_duplicate_start_report",
    "build_temporal_observation_rollback_drill_report",
    "build_temporal_observation_validation_report",
]
