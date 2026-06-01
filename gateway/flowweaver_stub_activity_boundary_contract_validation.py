"""Pure FlowWeaver Phase 26 validation for the Phase 25 stub Activity boundary contract.

This module consumes caller-provided Phase 25 boundary contract artifacts and
returns sanitized validation metadata only. It does not define Temporal
Activities, import Temporal SDK APIs, call Gateway adapters, execute agents/tools,
or invoke earlier-phase builders/orchestrators.
"""

from __future__ import annotations

import copy

from gateway.flowweaver_stub_activity_boundary_contract import (
    FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_REPORT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_SUCCESS_VERDICT,
    FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_TYPE,
    describe_flowweaver_stub_activity_boundary_contract,
    validate_flowweaver_stub_activity_boundary_contract_report,
)

FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VALIDATION_CONTRACT_TYPE = (
    "flowweaver.gateway.stub_activity_boundary_contract_validation_contract.v0"
)
FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VALIDATION_REPORT_TYPE = (
    "flowweaver.gateway.stub_activity_boundary_contract_validation_report.v0"
)
FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VALIDATION_SUCCESS_VERDICT = "ready_for_stub_activity_implementation_design"
FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VALIDATION_VERSION = "flowweaver.stub_activity_boundary_contract_validation.v0"

_OPERATION = "validate_flowweaver_stub_activity_boundary_contract"
_CONTRACT_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "scope",
    "consumes_contract",
    "consumes_report",
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
    "phase25_verdict",
    "activity_interface_names",
    "validation_summary",
    "checks",
    "error_code",
    "side_effects",
]
_ERROR_REPORT_FIELDS = ["type", "version", "phase", "ok", "operation", "error_code", "side_effects"]
_ACTIVITY_INTERFACE_NAMES = ["validate_claim_check_ref", "execute_agent_turn", "deliver_artifact"]
_VALIDATION_SUMMARY = {
    "activity_interface_count": 3,
    "payload_policy_mode": "claim_check_refs_only",
    "canonical_input_kind": "agent_input",
    "execution_policy_mode": "metadata_only_no_activity_execution",
    "runtime_side_effects": "absent",
}
_CHECKS = [
    "phase25_contract_valid",
    "phase25_report_valid",
    "activity_interfaces_consistent",
    "payload_policy_refs_only",
    "execution_policy_metadata_only",
    "separate_approvals_preserved",
    "side_effects_absent",
]
_SEPARATE_APPROVALS = [
    "stub_activity_implementation_design",
    "temporal_activity_implementation",
    "worker_lifecycle",
    "real_agent_tool_execution",
    "real_send_edit_render_callback_control",
    "delivery_ack_updates",
    "production_config_write",
    "gateway_restart",
]
_FORBIDDEN_SIDE_EFFECTS = [
    "temporal_sdk_import",
    "temporal_client",
    "worker_lifecycle",
    "workflow_environment",
    "activity_definition",
    "workflow_execute_activity",
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
    "delivery_ack_update",
    "agent_execution",
    "tool_execution",
    "prototype_import",
    "orchestrator_invocation",
    "boundary_contract_builder_invocation",
    "orchestration_validation_builder_invocation",
]
_ALLOWED_ERROR_CODES = {"invalid_phase25_boundary_contract", "invalid_phase25_boundary_contract_report"}
_RAW_VALUE_MARKERS = (
    "oc_",
    "ou_",
    "om_",
    "raw prompt",
    "raw tool output",
    '"type":"card_json"',
    '"type": "card_json"',
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
    FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_REPORT_TYPE,
)


def describe_flowweaver_stub_activity_boundary_contract_validation_contract() -> dict[str, object]:
    """Return the exact Phase 26 boundary contract validation descriptor."""

    return {
        "type": FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VALIDATION_CONTRACT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VALIDATION_VERSION,
        "phase": "phase26",
        "verdict": FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VALIDATION_SUCCESS_VERDICT,
        "scope": "stub_activity_boundary_contract_validation",
        "consumes_contract": FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_TYPE,
        "consumes_report": FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_REPORT_TYPE,
        "entrypoints": [
            "describe_flowweaver_stub_activity_boundary_contract_validation_contract",
            "validate_flowweaver_stub_activity_boundary_contract_validation_report",
            "build_flowweaver_stub_activity_boundary_contract_validation_report",
        ],
        "report_fields": list(_REPORT_FIELDS),
        "checks": list(_CHECKS),
        "separate_approvals": list(_SEPARATE_APPROVALS),
        "forbidden_side_effects": list(_FORBIDDEN_SIDE_EFFECTS),
        "side_effects": [],
    }


def validate_flowweaver_stub_activity_boundary_contract_validation_report(value: object) -> dict[str, object]:
    """Validate and return a sanitized Phase 26 validation report copy."""

    error = "invalid_stub_activity_boundary_contract_validation_report"
    if type(value) is not dict:
        _raise(error)
    if _keys_match_exactly(value, _ERROR_REPORT_FIELDS):
        return _validate_error_report(value, error=error)
    source = _plain_dict_with_fields(value, _REPORT_FIELDS, error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VALIDATION_REPORT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VALIDATION_VERSION, error),
        "phase": _literal(source["phase"], "phase26", error),
        "ok": _true(source["ok"], error),
        "verdict": _literal(source["verdict"], FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VALIDATION_SUCCESS_VERDICT, error),
        "operation": _literal(source["operation"], _OPERATION, error),
        "phase25_verdict": _literal(source["phase25_verdict"], FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_SUCCESS_VERDICT, error),
        "activity_interface_names": _activity_interface_names(source["activity_interface_names"], error=error),
        "validation_summary": _validation_summary(source["validation_summary"], error=error),
        "checks": _checks(source["checks"], error=error),
        "error_code": _none(source["error_code"], error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    _assert_no_forbidden_rendered_material(safe, error=error)
    return safe


def build_flowweaver_stub_activity_boundary_contract_validation_report(
    *, boundary_contract_descriptor: object, boundary_contract_report: object
) -> dict[str, object]:
    """Build a sanitized Phase 26 validation report from caller-provided Phase 25 artifacts."""

    try:
        contract = _validate_phase25_boundary_contract_descriptor(boundary_contract_descriptor)
    except ValueError:
        return _error_report("invalid_phase25_boundary_contract")

    try:
        _assert_plain_tree(boundary_contract_report, error="invalid_phase25_boundary_contract_report")
        report = validate_flowweaver_stub_activity_boundary_contract_report(boundary_contract_report)
        if report.get("ok") is not True:
            _raise("invalid_phase25_boundary_contract_report")
        _literal(report.get("verdict"), FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_SUCCESS_VERDICT, "invalid")
        _validate_phase25_report_matches_contract(report, contract)
    except ValueError:
        return _error_report("invalid_phase25_boundary_contract_report")

    result = {
        "type": FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VALIDATION_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VALIDATION_VERSION,
        "phase": "phase26",
        "ok": True,
        "verdict": FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VALIDATION_SUCCESS_VERDICT,
        "operation": _OPERATION,
        "phase25_verdict": report["verdict"],
        "activity_interface_names": [item["name"] for item in contract["activity_interfaces"]],
        "validation_summary": copy.deepcopy(_VALIDATION_SUMMARY),
        "checks": {key: True for key in _CHECKS},
        "error_code": None,
        "side_effects": [],
    }
    return validate_flowweaver_stub_activity_boundary_contract_validation_report(result)


def _validate_phase25_boundary_contract_descriptor(value: object) -> dict[str, object]:
    expected = describe_flowweaver_stub_activity_boundary_contract()
    _assert_exact(value, expected, "invalid_phase25_boundary_contract")
    return copy.deepcopy(expected)


def _validate_phase25_report_matches_contract(report: dict[str, object], contract: dict[str, object]) -> None:
    _assert_exact(report["activity_interfaces"], contract["activity_interfaces"], "invalid_phase25_boundary_contract_report")
    _assert_exact(report["payload_policy"], contract["payload_policy"], "invalid_phase25_boundary_contract_report")
    _assert_exact(report["execution_policy"], contract["execution_policy"], "invalid_phase25_boundary_contract_report")
    _assert_exact(report["side_effects"], [], "invalid_phase25_boundary_contract_report")


def _validate_error_report(value: dict[str, object], *, error: str) -> dict[str, object]:
    source = _plain_dict_with_fields(value, _ERROR_REPORT_FIELDS, error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VALIDATION_REPORT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VALIDATION_VERSION, error),
        "phase": _literal(source["phase"], "phase26", error),
        "ok": _false(source["ok"], error),
        "operation": _literal(source["operation"], _OPERATION, error),
        "error_code": _one_of(source["error_code"], _ALLOWED_ERROR_CODES, error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    _assert_no_forbidden_rendered_material(safe, error=error)
    return safe


def _plain_dict_with_fields(value: object, fields: list[str], error: str) -> dict[str, object]:
    if type(value) is not dict or not _keys_match_exactly(value, fields):
        _raise(error)
    _assert_no_forbidden_rendered_material(value, error=error)
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


def _activity_interface_names(value: object, *, error: str) -> list[str]:
    _assert_exact(value, _ACTIVITY_INTERFACE_NAMES, error)
    return list(_ACTIVITY_INTERFACE_NAMES)


def _validation_summary(value: object, *, error: str) -> dict[str, object]:
    _assert_exact(value, _VALIDATION_SUMMARY, error)
    return copy.deepcopy(_VALIDATION_SUMMARY)


def _checks(value: object, *, error: str) -> dict[str, bool]:
    source = _plain_dict_with_fields(value, _CHECKS, error)
    safe: dict[str, bool] = {}
    for key in _CHECKS:
        if source[key] is not True:
            _raise(error)
        safe[key] = True
    return safe


def _assert_exact(value: object, expected: object, error: str) -> None:
    if type(expected) is dict:
        if type(value) is not dict or not _keys_match_exactly(value, list(expected)):
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


def _keys_match_exactly(value: dict[object, object], expected_keys: list[str]) -> bool:
    actual_keys = list(value.keys())
    if len(actual_keys) != len(expected_keys):
        return False
    for actual, expected in zip(actual_keys, expected_keys, strict=True):
        if type(actual) is not str or actual != expected:
            return False
    return True


def _assert_plain_tree(value: object, *, error: str) -> None:
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                _raise(error)
            _assert_plain_tree(item, error=error)
        return
    if type(value) is list:
        for item in value:
            _assert_plain_tree(item, error=error)
        return
    if value is None or type(value) in {str, int, bool}:
        return
    _raise(error)


def _assert_no_forbidden_rendered_material(value: object, *, error: str) -> None:
    rendered = repr(value).lower()
    if any(marker in rendered for marker in _RAW_VALUE_MARKERS):
        _raise(error)


def _error_report(error_code: str) -> dict[str, object]:
    safe_error = error_code if error_code in _ALLOWED_ERROR_CODES else "invalid_phase25_boundary_contract_report"
    return {
        "type": FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VALIDATION_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VALIDATION_VERSION,
        "phase": "phase26",
        "ok": False,
        "operation": _OPERATION,
        "error_code": safe_error,
        "side_effects": [],
    }


def _raise(error: str) -> None:
    raise ValueError(error)
