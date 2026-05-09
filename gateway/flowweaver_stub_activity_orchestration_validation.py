"""Pure FlowWeaver Phase 24 validation for Phase 23 stub orchestration.

This module consumes a Phase 23 stub Activity orchestration contract descriptor
and an already-built Phase 23 orchestration result. It returns a sanitized
high-level validation report only. It does not construct Temporal clients, start
Workers, touch Gateway hooks/adapters, or invoke the Phase 23 orchestrator.
"""

from __future__ import annotations

import copy

from gateway.flowweaver_stub_activity_orchestration import (
    FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_CONTRACT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_RESULT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT,
    describe_flowweaver_stub_activity_orchestration_contract,
    validate_flowweaver_stub_activity_orchestration_result,
)

FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_CONTRACT_TYPE = (
    "flowweaver.gateway.stub_activity_orchestration_validation_contract.v0"
)
FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_REPORT_TYPE = (
    "flowweaver.gateway.stub_activity_orchestration_validation_report.v0"
)
FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_SUCCESS_VERDICT = "ready_for_stub_activity_boundary_contract_design"
FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_VERSION = "flowweaver.stub_activity_orchestration_validation.v0"

_OPERATION = "validate_flowweaver_stub_activity_orchestration"
_CONTRACT_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "scope",
    "consumes_contract",
    "consumes_result",
    "entrypoints",
    "report_fields",
    "checks",
    "separate_approvals",
    "forbidden_side_effects",
    "side_effects",
]
_REPORT_FIELDS = [
    "type",
    "version",
    "phase",
    "ok",
    "verdict",
    "operation",
    "phase23_verdict",
    "activity_sequence",
    "summary",
    "checks",
    "error_code",
    "side_effects",
]
_ERROR_REPORT_FIELDS = ["type", "version", "phase", "ok", "operation", "error_code", "side_effects"]
_ACTIVITY_SEQUENCE = [
    {"name": "validate_claim_check_ref", "status": "stubbed"},
    {"name": "execute_agent_turn", "status": "stubbed"},
    {"name": "deliver_artifact", "status": "planned"},
]
_CHECKS = [
    "phase23_contract_valid",
    "orchestration_result_valid",
    "activity_sequence_valid",
    "agent_input_claim_ref_only",
    "delivery_ack_updates_absent",
    "side_effects_absent",
]
_SEPARATE_APPROVALS = [
    "stub_activity_boundary_contract_design",
    "temporal_activity_execution",
    "real_agent_tool_execution",
    "real_send_edit_render_callback_control",
    "production_config_write",
    "gateway_restart",
]
_FORBIDDEN_SIDE_EFFECTS = [
    "temporal_client",
    "worker_lifecycle",
    "workflow_environment",
    "gateway_hook_change",
    "gateway_adapter_access",
    "config_write",
    "file_write",
    "subprocess",
    "socket",
    "docker",
    "daemon",
    "service_startup",
    "send",
    "edit",
    "render",
    "callback_control",
    "agent_execution",
    "tool_execution",
    "temporal_activity_execution",
    "orchestrator_invocation",
]
_ALLOWED_ERROR_CODES = {"invalid_phase23_contract", "invalid_phase23_orchestration_result"}
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
    "traceback",
    "unsafe-material",
    "unsafe-token",
    "bearer ",
    "password=",
    "secret=",
    "api_key=",
    "sk-",
    "flowweaverexecutionrequest",
    "execution_request",
)


def describe_flowweaver_stub_activity_orchestration_validation_contract() -> dict[str, object]:
    """Return the exact Phase 24 validation contract."""

    return {
        "type": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_CONTRACT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_VERSION,
        "phase": "phase24",
        "verdict": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_SUCCESS_VERDICT,
        "scope": "stub_activity_orchestration_validation",
        "consumes_contract": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_CONTRACT_TYPE,
        "consumes_result": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_RESULT_TYPE,
        "entrypoints": [
            "describe_flowweaver_stub_activity_orchestration_validation_contract",
            "validate_flowweaver_stub_activity_orchestration_validation_report",
            "build_flowweaver_stub_activity_orchestration_validation_report",
        ],
        "report_fields": list(_REPORT_FIELDS),
        "checks": list(_CHECKS),
        "separate_approvals": list(_SEPARATE_APPROVALS),
        "forbidden_side_effects": list(_FORBIDDEN_SIDE_EFFECTS),
        "side_effects": [],
    }


def validate_flowweaver_stub_activity_orchestration_validation_report(value: object) -> dict[str, object]:
    """Validate and return a sanitized Phase 24 validation report copy."""

    error = "invalid_stub_activity_orchestration_validation_report"
    if type(value) is not dict:
        _raise(error)
    if list(value) == _ERROR_REPORT_FIELDS:
        return _validate_error_report(value, error=error)
    source = _plain_dict_with_fields(value, _REPORT_FIELDS, error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_REPORT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_VERSION, error),
        "phase": _literal(source["phase"], "phase24", error),
        "ok": _true(source["ok"], error),
        "verdict": _literal(
            source["verdict"], FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_SUCCESS_VERDICT, error
        ),
        "operation": _literal(source["operation"], _OPERATION, error),
        "phase23_verdict": _literal(
            source["phase23_verdict"], FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT, error
        ),
        "activity_sequence": _activity_sequence(source["activity_sequence"], error=error),
        "summary": _summary(source["summary"], error=error),
        "checks": _checks(source["checks"], error=error),
        "error_code": _none(source["error_code"], error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    _assert_no_forbidden_rendered_material(safe, error=error)
    return safe


def build_flowweaver_stub_activity_orchestration_validation_report(
    *, contract_descriptor: object, orchestration_result: object
) -> dict[str, object]:
    """Build a sanitized Phase 24 validation report from caller-provided Phase 23 artifacts."""

    try:
        _validate_phase23_contract_descriptor(contract_descriptor)
    except ValueError:
        return _error_report("invalid_phase23_contract")

    try:
        result = validate_flowweaver_stub_activity_orchestration_result(orchestration_result)
        _validate_phase23_boundary(result)
    except ValueError:
        return _error_report("invalid_phase23_orchestration_result")

    request = result["execution_request"]
    execution_result = result["execution_result"]
    summary = {
        "input_refs": len(request["input_refs"]),
        "artifacts": len(execution_result["artifact_refs"]),
        "deliveries": len(execution_result["delivery_refs"]),
        "ack_updates": 0,
    }
    report = {
        "type": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_VERSION,
        "phase": "phase24",
        "ok": True,
        "verdict": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_SUCCESS_VERDICT,
        "operation": _OPERATION,
        "phase23_verdict": result["verdict"],
        "activity_sequence": list(_ACTIVITY_SEQUENCE),
        "summary": summary,
        "checks": {
            "phase23_contract_valid": True,
            "orchestration_result_valid": True,
            "activity_sequence_valid": True,
            "agent_input_claim_ref_only": True,
            "delivery_ack_updates_absent": True,
            "side_effects_absent": True,
        },
        "error_code": None,
        "side_effects": [],
    }
    return validate_flowweaver_stub_activity_orchestration_validation_report(report)


def _validate_phase23_contract_descriptor(value: object) -> None:
    _assert_exact(value, describe_flowweaver_stub_activity_orchestration_contract(), "invalid_phase23_contract")


def _validate_phase23_boundary(result: dict[str, object]) -> None:
    _assert_exact(
        result["activity_sequence"],
        [
            {
                "name": "validate_claim_check_ref",
                "status": "stubbed",
                "input_refs": [item["ref"] for item in result["execution_request"]["input_refs"]],
                "side_effects": [],
            },
            {
                "name": "execute_agent_turn",
                "status": "stubbed",
                "intent_id": result["execution_request"]["intent_id"],
                "side_effects": [],
            },
            {
                "name": "deliver_artifact",
                "status": "planned",
                "delivery_refs": list(result["execution_request"]["delivery_refs"]),
                "side_effects": [],
            },
        ],
        "invalid_phase23_orchestration_result",
    )
    request = result["execution_request"]
    if type(request["input_refs"]) is not list or len(request["input_refs"]) != 1:
        _raise("invalid_phase23_orchestration_result")
    input_ref = request["input_refs"][0]
    if type(input_ref) is not dict or input_ref.get("kind") != "agent_input":
        _raise("invalid_phase23_orchestration_result")
    if result["delivery_ack_updates"] != []:
        _raise("invalid_phase23_orchestration_result")
    _require_side_effects_absent(result, error="invalid_phase23_orchestration_result")


def _validate_error_report(value: dict[str, object], *, error: str) -> dict[str, object]:
    source = _plain_dict_with_fields(value, _ERROR_REPORT_FIELDS, error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_REPORT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_VERSION, error),
        "phase": _literal(source["phase"], "phase24", error),
        "ok": _false(source["ok"], error),
        "operation": _literal(source["operation"], _OPERATION, error),
        "error_code": _one_of(source["error_code"], _ALLOWED_ERROR_CODES, error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    _assert_no_forbidden_rendered_material(safe, error=error)
    return safe


def _plain_dict_with_fields(value: object, fields: list[str], error: str) -> dict[str, object]:
    if type(value) is not dict or list(value) != fields:
        _raise(error)
    _reject_unsafe(value, error=error)
    return value


def _literal(value: object, expected: str, error: str) -> str:
    if type(value) is not str or value != expected:
        _raise(error)
    return value


def _one_of(value: object, allowed: set[str], error: str) -> str:
    if type(value) is not str or value not in allowed:
        _raise(error)
    return value


def _true(value: object, error: str) -> bool:
    if value is not True:
        _raise(error)
    return True


def _false(value: object, error: str) -> bool:
    if value is not False:
        _raise(error)
    return False


def _none(value: object, error: str) -> None:
    if value is not None:
        _raise(error)
    return None


def _empty_list(value: object, error: str) -> list[object]:
    if type(value) is not list or value:
        _raise(error)
    return []


def _activity_sequence(value: object, *, error: str) -> list[dict[str, str]]:
    _assert_exact(value, _ACTIVITY_SEQUENCE, error)
    return copy.deepcopy(_ACTIVITY_SEQUENCE)


def _summary(value: object, *, error: str) -> dict[str, int]:
    expected = {"input_refs": 1, "artifacts": 1, "deliveries": 1, "ack_updates": 0}
    _assert_exact(value, expected, error)
    return dict(expected)


def _checks(value: object, *, error: str) -> dict[str, bool]:
    if type(value) is not dict or list(value) != _CHECKS:
        _raise(error)
    safe: dict[str, bool] = {}
    for key in _CHECKS:
        if value[key] is not True:
            _raise(error)
        safe[key] = True
    return safe


def _require_side_effects_absent(value: object, *, error: str) -> None:
    if type(value) is dict:
        for key, item in value.items():
            if key == "side_effects" and item != []:
                _raise(error)
            _require_side_effects_absent(item, error=error)
        return
    if type(value) is list:
        for item in value:
            _require_side_effects_absent(item, error=error)


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
        return
    if value is None or type(value) in {bool, int}:
        return
    _raise(error)


def _reject_unsafe_string(value: str, *, error: str) -> None:
    lowered = value.lower()
    if any(marker in lowered for marker in _RAW_VALUE_MARKERS):
        _raise(error)


def _assert_no_forbidden_rendered_material(value: object, *, error: str) -> None:
    try:
        _reject_unsafe_string(repr(value), error=error)
    except ValueError:
        _raise(error)


def _error_report(error_code: str) -> dict[str, object]:
    safe_error = error_code if error_code in _ALLOWED_ERROR_CODES else "invalid_phase23_orchestration_result"
    return {
        "type": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_VERSION,
        "phase": "phase24",
        "ok": False,
        "operation": _OPERATION,
        "error_code": safe_error,
        "side_effects": [],
    }


def _raise(error: str) -> None:
    raise ValueError(error)
