"""Pure FlowWeaver Phase 28 validation for the Phase 27 stub Activity implementation design.

This module consumes caller-provided Phase 27 implementation design artifacts and
returns sanitized validation metadata only. It does not define callable
Activities, import Temporal SDK APIs, call Gateway adapters, execute agents/tools,
or invoke earlier-phase builders/orchestrators.
"""

from __future__ import annotations

import copy

from gateway.flowweaver_stub_activity_implementation_design import (
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_DESIGN_CONTRACT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_DESIGN_REPORT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_DESIGN_SUCCESS_VERDICT,
    describe_flowweaver_stub_activity_implementation_design_contract,
    validate_flowweaver_stub_activity_implementation_design_report,
)

FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_CONTRACT_TYPE = (
    "flowweaver.gateway.stub_activity_implementation_validation_contract.v0"
)
FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_REPORT_TYPE = (
    "flowweaver.gateway.stub_activity_implementation_validation_report.v0"
)
FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_SUCCESS_VERDICT = (
    "ready_for_separately_approved_stub_activity_implementation"
)
FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_VERSION = "flowweaver.stub_activity_implementation_validation.v0"

_OPERATION = "validate_flowweaver_stub_activity_implementation_design"
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
    "validation_summary",
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
    "phase27_verdict",
    "activity_design_unit_names",
    "validation_summary",
    "checks",
    "error_code",
    "side_effects",
]
_ERROR_REPORT_FIELDS = ["type", "version", "phase", "ok", "operation", "error_code", "side_effects"]
_ACTIVITY_DESIGN_UNIT_NAMES = ["validate_claim_check_ref", "execute_agent_turn", "deliver_artifact"]
_VALIDATION_SUMMARY = {
    "activity_design_unit_count": 3,
    "implementation_mode": "design_only_no_callable_activities",
    "verification_mode": "metadata_static_validation_only",
    "payload_policy_mode": "claim_check_refs_only",
    "runtime_side_effects": "absent",
}
_CHECKS = [
    "phase27_contract_valid",
    "phase27_report_valid",
    "activity_design_units_valid",
    "implementation_policy_design_only",
    "verification_policy_static_only",
    "separate_approvals_preserved",
    "side_effects_absent",
    "raw_material_absent",
]
_SEPARATE_APPROVALS = [
    "stub_activity_implementation",
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
    "callable_activity_definition",
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
    "implementation_design_builder_invocation",
    "boundary_contract_validation_builder_invocation",
    "boundary_contract_builder_invocation",
    "orchestration_validation_builder_invocation",
    "orchestrator_invocation",
]
_ALLOWED_ERROR_CODES = {
    "invalid_phase27_stub_activity_implementation_design_contract",
    "invalid_phase27_stub_activity_implementation_design_report",
}
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
    "bearer ",
    "password=",
    "secret=",
    "api_key=",
    "sk-",
    "flowweaverexecutionrequest",
    "execution_request",
    "runtime_tx_phase28_1",
    "claim_ref_phase28_0",
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_DESIGN_REPORT_TYPE,
)


def describe_flowweaver_stub_activity_implementation_validation_contract() -> dict[str, object]:
    """Return the exact Phase 28 implementation validation descriptor."""

    return {
        "type": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_CONTRACT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_VERSION,
        "phase": "phase28",
        "verdict": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_SUCCESS_VERDICT,
        "scope": "stub_activity_implementation_validation",
        "consumes_contract": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_DESIGN_CONTRACT_TYPE,
        "consumes_report": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_DESIGN_REPORT_TYPE,
        "entrypoints": [
            "describe_flowweaver_stub_activity_implementation_validation_contract",
            "validate_flowweaver_stub_activity_implementation_validation_report",
            "build_flowweaver_stub_activity_implementation_validation_report",
        ],
        "report_fields": list(_REPORT_FIELDS),
        "validation_summary": copy.deepcopy(_VALIDATION_SUMMARY),
        "checks": list(_CHECKS),
        "separate_approvals": list(_SEPARATE_APPROVALS),
        "forbidden_side_effects": list(_FORBIDDEN_SIDE_EFFECTS),
        "side_effects": [],
    }


def validate_flowweaver_stub_activity_implementation_validation_report(value: object) -> dict[str, object]:
    """Validate and return a sanitized Phase 28 implementation validation report copy."""

    error = "invalid_stub_activity_implementation_validation_report"
    if type(value) is not dict:
        _raise(error)
    if _keys_match_exactly(value, _ERROR_REPORT_FIELDS):
        return _validate_error_report(value, error=error)
    source = _plain_dict_with_fields(value, _REPORT_FIELDS, error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_REPORT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_VERSION, error),
        "phase": _literal(source["phase"], "phase28", error),
        "ok": _true(source["ok"], error),
        "verdict": _literal(source["verdict"], FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_SUCCESS_VERDICT, error),
        "operation": _literal(source["operation"], _OPERATION, error),
        "phase27_verdict": _literal(
            source["phase27_verdict"],
            FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_DESIGN_SUCCESS_VERDICT,
            error,
        ),
        "activity_design_unit_names": _activity_design_unit_names(source["activity_design_unit_names"], error=error),
        "validation_summary": _validation_summary(source["validation_summary"], error=error),
        "checks": _checks(source["checks"], error=error),
        "error_code": _none(source["error_code"], error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    _assert_no_forbidden_rendered_material(safe, error=error)
    return safe


def build_flowweaver_stub_activity_implementation_validation_report(
    *, implementation_design_contract_descriptor: object, implementation_design_report: object
) -> dict[str, object]:
    """Build sanitized Phase 28 validation metadata from caller-provided Phase 27 artifacts."""

    try:
        design_contract = _validate_phase27_implementation_design_descriptor(
            implementation_design_contract_descriptor
        )
    except ValueError:
        return _error_report("invalid_phase27_stub_activity_implementation_design_contract")

    try:
        _assert_plain_tree(
            implementation_design_report,
            error="invalid_phase27_stub_activity_implementation_design_report",
        )
        report = validate_flowweaver_stub_activity_implementation_design_report(implementation_design_report)
        if report.get("ok") is not True:
            _raise("invalid_phase27_stub_activity_implementation_design_report")
        _literal(
            report.get("verdict"),
            FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_DESIGN_SUCCESS_VERDICT,
            "invalid_phase27_stub_activity_implementation_design_report",
        )
        _validate_phase27_report_matches_design(report, design_contract)
    except ValueError:
        return _error_report("invalid_phase27_stub_activity_implementation_design_report")

    result = {
        "type": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_VERSION,
        "phase": "phase28",
        "ok": True,
        "verdict": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_SUCCESS_VERDICT,
        "operation": _OPERATION,
        "phase27_verdict": report["verdict"],
        "activity_design_unit_names": [unit["name"] for unit in report["activity_design_units"]],
        "validation_summary": copy.deepcopy(_VALIDATION_SUMMARY),
        "checks": {key: True for key in _CHECKS},
        "error_code": None,
        "side_effects": [],
    }
    return validate_flowweaver_stub_activity_implementation_validation_report(result)


def _validate_phase27_implementation_design_descriptor(value: object) -> dict[str, object]:
    expected = describe_flowweaver_stub_activity_implementation_design_contract()
    _assert_exact(value, expected, "invalid_phase27_stub_activity_implementation_design_contract")
    return copy.deepcopy(expected)


def _validate_phase27_report_matches_design(report: dict[str, object], design_contract: dict[str, object]) -> None:
    _assert_exact(
        report["activity_design_units"],
        design_contract["design_units"],
        "invalid_phase27_stub_activity_implementation_design_report",
    )
    _assert_exact(
        report["implementation_policy"],
        design_contract["implementation_policy"],
        "invalid_phase27_stub_activity_implementation_design_report",
    )
    _assert_exact(
        report["verification_policy"],
        design_contract["verification_policy"],
        "invalid_phase27_stub_activity_implementation_design_report",
    )
    _assert_exact(report["side_effects"], [], "invalid_phase27_stub_activity_implementation_design_report")


def _validate_error_report(value: dict[str, object], *, error: str) -> dict[str, object]:
    source = _plain_dict_with_fields(value, _ERROR_REPORT_FIELDS, error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_REPORT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_VERSION, error),
        "phase": _literal(source["phase"], "phase28", error),
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


def _activity_design_unit_names(value: object, *, error: str) -> list[str]:
    _assert_exact(value, _ACTIVITY_DESIGN_UNIT_NAMES, error)
    return list(_ACTIVITY_DESIGN_UNIT_NAMES)


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
    safe_error = (
        error_code
        if error_code in _ALLOWED_ERROR_CODES
        else "invalid_phase27_stub_activity_implementation_design_report"
    )
    return {
        "type": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_VERSION,
        "phase": "phase28",
        "ok": False,
        "operation": _OPERATION,
        "error_code": safe_error,
        "side_effects": [],
    }


def _raise(error: str) -> None:
    raise ValueError(error)
