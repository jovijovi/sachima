"""FlowWeaver Phase 29 plain callable stub Activity implementations.

This module implements non-production, synchronous, side-effect-free stub
functions for the future Activity units. It consumes caller-provided Phase 28
validation artifacts and returns sanitized implementation metadata only. It does
not import Temporal SDK APIs, define Temporal Activities, call Gateway adapters,
execute agents/tools, perform delivery, update ACKs, or own runtime lifecycle.
"""

from __future__ import annotations

import copy

from gateway.flowweaver_stub_activity_implementation_validation import (
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_CONTRACT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_REPORT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_SUCCESS_VERDICT,
    describe_flowweaver_stub_activity_implementation_validation_contract,
    validate_flowweaver_stub_activity_implementation_validation_report,
)

FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_CONTRACT_TYPE = "flowweaver.gateway.stub_activity_implementation_contract.v0"
FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_REPORT_TYPE = "flowweaver.gateway.stub_activity_implementation_report.v0"
FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_SUCCESS_VERDICT = "ready_for_local_temporal_stub_activity_orchestration"
FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VERSION = "flowweaver.stub_activity_implementation.v0"

_OPERATION = "implement_flowweaver_stub_activities"
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
    "activity_functions",
    "implementation_policy",
    "validation_policy",
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
    "phase28_verdict",
    "activity_function_names",
    "implementation_policy",
    "validation_policy",
    "checks",
    "error_code",
    "side_effects",
]
_ERROR_REPORT_FIELDS = ["type", "version", "phase", "ok", "operation", "error_code", "side_effects"]
_ACTIVITY_NAMES = ["validate_claim_check_ref", "execute_agent_turn", "deliver_artifact"]
_ACTIVITY_FUNCTIONS = [
    {
        "name": "validate_claim_check_ref",
        "implementation_mode": "plain_callable_stub_no_external_effects",
        "input_fields": ["claim_check_ref", "policy_descriptor"],
        "result_fields": ["activity", "status", "claim_ref", "error_code", "side_effects"],
        "allowed_statuses": ["validated", "rejected"],
        "error_codes": ["invalid_claim_ref", "noncanonical_claim_kind", "unsafe_material"],
        "runtime_calls": [],
        "side_effects": [],
    },
    {
        "name": "execute_agent_turn",
        "implementation_mode": "plain_callable_stub_no_external_effects",
        "input_fields": ["execution_request", "validated_claim"],
        "result_fields": ["activity", "status", "artifact_ref", "error_code", "side_effects"],
        "allowed_statuses": ["stubbed", "rejected"],
        "error_codes": ["invalid_agent_activity_input", "unsafe_material", "agent_execution_not_approved"],
        "runtime_calls": [],
        "side_effects": [],
    },
    {
        "name": "deliver_artifact",
        "implementation_mode": "plain_callable_stub_no_external_effects",
        "input_fields": ["artifact", "delivery_plan"],
        "result_fields": ["activity", "status", "delivery_ref", "error_code", "side_effects"],
        "allowed_statuses": ["planned", "rejected"],
        "error_codes": ["invalid_delivery_activity_input", "unsafe_material", "delivery_execution_not_approved"],
        "runtime_calls": [],
        "side_effects": [],
    },
]
_IMPLEMENTATION_POLICY = {
    "mode": "plain_callable_stubs_only",
    "temporal_sdk": "forbidden_in_phase29",
    "activity_decorators": "forbidden_in_phase29",
    "agent_tool_execution": "stubbed_not_executed",
    "gateway_delivery_ack": "stubbed_not_executed",
    "claim_check_storage_io": "forbidden_in_phase29",
    "side_effects": [],
}
_VALIDATION_POLICY = {
    "mode": "exact_inputs_sanitized_stub_outputs",
    "required_next_phase": "local_temporal_stub_activity_orchestration",
    "exact_key_validation": "required",
    "raw_material_policy": "reject_and_do_not_echo",
    "side_effects": [],
}
_CHECKS = [
    "phase28_contract_valid",
    "phase28_report_valid",
    "activity_functions_callable",
    "implementation_policy_plain_stubs_only",
    "validation_policy_exact_inputs",
    "separate_approvals_preserved",
    "side_effects_absent",
    "raw_material_absent",
]
_SEPARATE_APPROVALS = [
    "local_temporal_stub_activity_orchestration",
    "temporal_activity_definition",
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
    "claim_check_storage_io",
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
    "implementation_validation_builder_invocation",
    "implementation_design_builder_invocation",
    "orchestrator_invocation",
]
_ALLOWED_ERROR_CODES = {
    "invalid_phase28_stub_activity_implementation_validation_contract",
    "invalid_phase28_stub_activity_implementation_validation_report",
}
_RAW_VALUE_MARKERS = (
    "oc_",
    "ou_",
    "om_",
    "raw prompt",
    "raw tool output",
    "card_json",
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
    "private",
    "flowweaverexecutionrequest",
    "execution_request",
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_REPORT_TYPE,
)
_CLAIM_FIELDS = ["ref", "kind", "count", "size", "checksum_hint"]
_CLAIM_POLICY = {
    "mode": "claim_check_refs_only",
    "allowed_kinds": ["agent_input"],
    "checksum_hint": "sha256_64_lower_hex",
    "side_effects": [],
}
_EXECUTION_REQUEST_FIELDS = [
    "transaction_id",
    "workflow_id",
    "intent_id",
    "input_ref",
    "artifact_ref",
    "execution_mode",
]
_VALIDATED_CLAIM_FIELDS = ["activity", "status", "claim_ref", "error_code", "side_effects"]
_ARTIFACT_FIELDS = ["artifact_ref", "kind", "status"]
_DELIVERY_PLAN_FIELDS = ["transaction_id", "workflow_id", "delivery_ref", "artifact_ref", "surface"]
_HEX = frozenset("0123456789abcdef")
_MAX_PLAIN_TREE_DEPTH = 64


def describe_flowweaver_stub_activity_implementation_contract() -> dict[str, object]:
    """Return the exact Phase 29 callable-stub implementation descriptor."""

    return {
        "type": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_CONTRACT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VERSION,
        "phase": "phase29",
        "verdict": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_SUCCESS_VERDICT,
        "scope": "stub_activity_implementation",
        "consumes_contract": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_CONTRACT_TYPE,
        "consumes_report": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_REPORT_TYPE,
        "entrypoints": [
            "describe_flowweaver_stub_activity_implementation_contract",
            "validate_flowweaver_stub_activity_implementation_report",
            "build_flowweaver_stub_activity_implementation_report",
            "validate_claim_check_ref",
            "execute_agent_turn",
            "deliver_artifact",
        ],
        "report_fields": list(_REPORT_FIELDS),
        "activity_functions": copy.deepcopy(_ACTIVITY_FUNCTIONS),
        "implementation_policy": copy.deepcopy(_IMPLEMENTATION_POLICY),
        "validation_policy": copy.deepcopy(_VALIDATION_POLICY),
        "checks": list(_CHECKS),
        "separate_approvals": list(_SEPARATE_APPROVALS),
        "forbidden_side_effects": list(_FORBIDDEN_SIDE_EFFECTS),
        "side_effects": [],
    }


def validate_flowweaver_stub_activity_implementation_report(value: object) -> dict[str, object]:
    """Validate and return a sanitized Phase 29 implementation report copy."""

    error = "invalid_stub_activity_implementation_report"
    if type(value) is not dict:
        _raise(error)
    if _keys_match_exactly(value, _ERROR_REPORT_FIELDS):
        return _validate_error_report(value, error=error)
    source = _plain_dict_with_fields(value, _REPORT_FIELDS, error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_REPORT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VERSION, error),
        "phase": _literal(source["phase"], "phase29", error),
        "ok": _true(source["ok"], error),
        "verdict": _literal(source["verdict"], FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_SUCCESS_VERDICT, error),
        "operation": _literal(source["operation"], _OPERATION, error),
        "phase28_verdict": _literal(
            source["phase28_verdict"],
            FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_SUCCESS_VERDICT,
            error,
        ),
        "activity_function_names": _activity_names(source["activity_function_names"], error=error),
        "implementation_policy": _implementation_policy(source["implementation_policy"], error=error),
        "validation_policy": _validation_policy(source["validation_policy"], error=error),
        "checks": _checks(source["checks"], error=error),
        "error_code": _none(source["error_code"], error),
        "side_effects": _empty_list(source["side_effects"], error),
    }
    _assert_no_forbidden_rendered_material(safe, error=error)
    return safe


def build_flowweaver_stub_activity_implementation_report(
    *, implementation_validation_descriptor: object, implementation_validation_report: object
) -> dict[str, object]:
    """Build sanitized Phase 29 implementation metadata from caller-provided Phase 28 artifacts."""

    try:
        _validate_phase28_implementation_validation_descriptor(implementation_validation_descriptor)
    except ValueError:
        return _error_report("invalid_phase28_stub_activity_implementation_validation_contract")

    try:
        _assert_plain_tree(
            implementation_validation_report,
            error="invalid_phase28_stub_activity_implementation_validation_report",
        )
        report = validate_flowweaver_stub_activity_implementation_validation_report(
            implementation_validation_report
        )
        if report.get("ok") is not True:
            _raise("invalid_phase28_stub_activity_implementation_validation_report")
        _literal(
            report.get("verdict"),
            FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_SUCCESS_VERDICT,
            "invalid_phase28_stub_activity_implementation_validation_report",
        )
        _assert_exact(
            report.get("activity_design_unit_names"),
            _ACTIVITY_NAMES,
            "invalid_phase28_stub_activity_implementation_validation_report",
        )
        _assert_exact(report.get("side_effects"), [], "invalid_phase28_stub_activity_implementation_validation_report")
    except ValueError:
        return _error_report("invalid_phase28_stub_activity_implementation_validation_report")

    result = {
        "type": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VERSION,
        "phase": "phase29",
        "ok": True,
        "verdict": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_SUCCESS_VERDICT,
        "operation": _OPERATION,
        "phase28_verdict": report["verdict"],
        "activity_function_names": list(_ACTIVITY_NAMES),
        "implementation_policy": copy.deepcopy(_IMPLEMENTATION_POLICY),
        "validation_policy": copy.deepcopy(_VALIDATION_POLICY),
        "checks": {key: True for key in _CHECKS},
        "error_code": None,
        "side_effects": [],
    }
    return validate_flowweaver_stub_activity_implementation_report(result)


def validate_claim_check_ref(*, claim_check_ref: object, policy_descriptor: object) -> dict[str, object]:
    """Validate a safe claim-check reference and return a deterministic stub result."""

    if _contains_forbidden_material(claim_check_ref) or _contains_forbidden_material(policy_descriptor):
        return _claim_result(status="rejected", claim_ref=None, error_code="unsafe_material")
    try:
        _assert_exact(policy_descriptor, _CLAIM_POLICY, "invalid_claim_ref")
        claim = _plain_dict_with_fields(claim_check_ref, _CLAIM_FIELDS, "invalid_claim_ref")
        ref = _safe_identifier(claim["ref"], prefix="claim_ref_", error="invalid_claim_ref")
        kind = _literal(claim["kind"], "agent_input", "noncanonical_claim_kind")
        _positive_int(claim["count"], "invalid_claim_ref")
        _positive_int(claim["size"], "invalid_claim_ref")
        _checksum_hint(claim["checksum_hint"], "invalid_claim_ref")
    except ValueError as exc:
        code = str(exc) if str(exc) in {"invalid_claim_ref", "noncanonical_claim_kind"} else "invalid_claim_ref"
        return _claim_result(status="rejected", claim_ref=None, error_code=code)
    if kind != "agent_input":
        return _claim_result(status="rejected", claim_ref=None, error_code="noncanonical_claim_kind")
    return _claim_result(status="validated", claim_ref=ref, error_code=None)


def execute_agent_turn(*, execution_request: object, validated_claim: object) -> dict[str, object]:
    """Return a deterministic stubbed agent Activity result without executing an agent or tool."""

    if _contains_forbidden_material(execution_request) or _contains_forbidden_material(validated_claim):
        return _agent_result(status="rejected", artifact_ref=None, error_code="unsafe_material")
    try:
        request = _plain_dict_with_fields(execution_request, _EXECUTION_REQUEST_FIELDS, "invalid_agent_activity_input")
        claim = _plain_dict_with_fields(validated_claim, _VALIDATED_CLAIM_FIELDS, "invalid_agent_activity_input")
        transaction_id = _safe_identifier(request["transaction_id"], prefix="runtime_tx_", error="invalid_agent_activity_input")
        workflow_id = _safe_identifier(request["workflow_id"], prefix="runtime_tx_", error="invalid_agent_activity_input")
        if workflow_id != transaction_id:
            _raise("invalid_agent_activity_input")
        _safe_identifier(request["intent_id"], prefix="runtime_intent_", error="invalid_agent_activity_input")
        input_ref = _safe_identifier(request["input_ref"], prefix="claim_ref_", error="invalid_agent_activity_input")
        artifact_ref = _safe_identifier(request["artifact_ref"], prefix="runtime_artifact_", error="invalid_agent_activity_input")
        _literal(request["execution_mode"], "stub_activity_implementation", "invalid_agent_activity_input")
        _literal(claim["activity"], "validate_claim_check_ref", "invalid_agent_activity_input")
        _literal(claim["status"], "validated", "invalid_agent_activity_input")
        claim_ref = _safe_identifier(claim["claim_ref"], prefix="claim_ref_", error="invalid_agent_activity_input")
        if claim_ref != input_ref:
            _raise("invalid_agent_activity_input")
        _none(claim["error_code"], "invalid_agent_activity_input")
        _empty_list(claim["side_effects"], "invalid_agent_activity_input")
    except ValueError as exc:
        code = "unsafe_material" if str(exc) == "unsafe_material" else "invalid_agent_activity_input"
        return _agent_result(status="rejected", artifact_ref=None, error_code=code)
    return _agent_result(status="stubbed", artifact_ref=artifact_ref, error_code=None)


def deliver_artifact(*, artifact: object, delivery_plan: object) -> dict[str, object]:
    """Return a deterministic stubbed delivery plan without rendering, sending, or ACKing."""

    if _contains_forbidden_material(artifact) or _contains_forbidden_material(delivery_plan):
        return _delivery_result(status="rejected", delivery_ref=None, error_code="unsafe_material")
    try:
        safe_artifact = _plain_dict_with_fields(artifact, _ARTIFACT_FIELDS, "invalid_delivery_activity_input")
        plan = _plain_dict_with_fields(delivery_plan, _DELIVERY_PLAN_FIELDS, "invalid_delivery_activity_input")
        artifact_ref = _safe_identifier(
            safe_artifact["artifact_ref"], prefix="runtime_artifact_", error="invalid_delivery_activity_input"
        )
        _literal(safe_artifact["kind"], "stub_agent_result", "invalid_delivery_activity_input")
        _literal(safe_artifact["status"], "stubbed", "invalid_delivery_activity_input")
        transaction_id = _safe_identifier(plan["transaction_id"], prefix="runtime_tx_", error="invalid_delivery_activity_input")
        workflow_id = _safe_identifier(plan["workflow_id"], prefix="runtime_tx_", error="invalid_delivery_activity_input")
        if workflow_id != transaction_id:
            _raise("invalid_delivery_activity_input")
        delivery_ref = _safe_identifier(plan["delivery_ref"], prefix="runtime_delivery_", error="invalid_delivery_activity_input")
        plan_artifact_ref = _safe_identifier(
            plan["artifact_ref"], prefix="runtime_artifact_", error="invalid_delivery_activity_input"
        )
        if plan_artifact_ref != artifact_ref:
            _raise("invalid_delivery_activity_input")
        _literal(plan["surface"], "final_text", "invalid_delivery_activity_input")
    except ValueError as exc:
        code = "unsafe_material" if str(exc) == "unsafe_material" else "invalid_delivery_activity_input"
        return _delivery_result(status="rejected", delivery_ref=None, error_code=code)
    return _delivery_result(status="planned", delivery_ref=delivery_ref, error_code=None)


def _validate_phase28_implementation_validation_descriptor(value: object) -> dict[str, object]:
    expected = describe_flowweaver_stub_activity_implementation_validation_contract()
    _assert_exact(value, expected, "invalid_phase28_stub_activity_implementation_validation_contract")
    return copy.deepcopy(expected)


def _validate_error_report(value: dict[str, object], *, error: str) -> dict[str, object]:
    source = _plain_dict_with_fields(value, _ERROR_REPORT_FIELDS, error)
    safe = {
        "type": _literal(source["type"], FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_REPORT_TYPE, error),
        "version": _literal(source["version"], FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VERSION, error),
        "phase": _literal(source["phase"], "phase29", error),
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


def _positive_int(value: object, error: str) -> int:
    if type(value) is not int or value <= 0:
        _raise(error)
    return value


def _checksum_hint(value: object, error: str) -> str:
    if type(value) is not str or not value.startswith("sha256:"):
        _raise(error)
    digest = value.removeprefix("sha256:")
    if len(digest) != 64 or any(character not in _HEX for character in digest):
        _raise(error)
    return value


def _activity_names(value: object, *, error: str) -> list[str]:
    _assert_exact(value, _ACTIVITY_NAMES, error)
    return list(_ACTIVITY_NAMES)


def _implementation_policy(value: object, *, error: str) -> dict[str, object]:
    _assert_exact(value, _IMPLEMENTATION_POLICY, error)
    return copy.deepcopy(_IMPLEMENTATION_POLICY)


def _validation_policy(value: object, *, error: str) -> dict[str, object]:
    _assert_exact(value, _VALIDATION_POLICY, error)
    return copy.deepcopy(_VALIDATION_POLICY)


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


def _assert_plain_tree(value: object, *, error: str, seen: set[int] | None = None, depth: int = 0) -> None:
    if depth > _MAX_PLAIN_TREE_DEPTH:
        _raise(error)
    if seen is None:
        seen = set()
    if type(value) is dict:
        identity = id(value)
        if identity in seen:
            _raise(error)
        seen.add(identity)
        try:
            for key, item in value.items():
                if type(key) is not str:
                    _raise(error)
                _assert_plain_tree(item, error=error, seen=seen, depth=depth + 1)
        finally:
            seen.remove(identity)
        return
    if type(value) is list:
        identity = id(value)
        if identity in seen:
            _raise(error)
        seen.add(identity)
        try:
            for item in value:
                _assert_plain_tree(item, error=error, seen=seen, depth=depth + 1)
        finally:
            seen.remove(identity)
        return
    if value is None or type(value) in {str, int, bool}:
        return
    _raise(error)


def _contains_forbidden_material(value: object, seen: set[int] | None = None, depth: int = 0) -> bool:
    if depth > _MAX_PLAIN_TREE_DEPTH:
        return True
    if seen is None:
        seen = set()
    if type(value) is str:
        rendered = value.lower()
        return any(marker in rendered for marker in _RAW_VALUE_MARKERS)
    if value is None or type(value) in {int, bool}:
        return False
    if type(value) is list:
        identity = id(value)
        if identity in seen:
            return True
        seen.add(identity)
        try:
            return any(_contains_forbidden_material(item, seen, depth + 1) for item in value)
        finally:
            seen.remove(identity)
    if type(value) is dict:
        identity = id(value)
        if identity in seen:
            return True
        seen.add(identity)
        try:
            for key, item in value.items():
                if type(key) is not str or _contains_forbidden_material(key, seen, depth + 1):
                    return True
                if _contains_forbidden_material(item, seen, depth + 1):
                    return True
            return False
        finally:
            seen.remove(identity)
    return True


def _assert_no_forbidden_rendered_material(value: object, *, error: str) -> None:
    if _contains_forbidden_material(value):
        _raise(error)


def _safe_identifier(value: object, *, prefix: str, error: str) -> str:
    if type(value) is not str or not value.startswith(prefix):
        _raise(error)
    if _contains_forbidden_material(value):
        _raise("unsafe_material")
    suffix = value[len(prefix) :]
    if not suffix or any(not (character.islower() or character.isdigit() or character == "_") for character in suffix):
        _raise(error)
    return value


def _claim_result(*, status: str, claim_ref: str | None, error_code: str | None) -> dict[str, object]:
    return {
        "activity": "validate_claim_check_ref",
        "status": status,
        "claim_ref": claim_ref,
        "error_code": error_code,
        "side_effects": [],
    }


def _agent_result(*, status: str, artifact_ref: str | None, error_code: str | None) -> dict[str, object]:
    return {
        "activity": "execute_agent_turn",
        "status": status,
        "artifact_ref": artifact_ref,
        "error_code": error_code,
        "side_effects": [],
    }


def _delivery_result(*, status: str, delivery_ref: str | None, error_code: str | None) -> dict[str, object]:
    return {
        "activity": "deliver_artifact",
        "status": status,
        "delivery_ref": delivery_ref,
        "error_code": error_code,
        "side_effects": [],
    }


def _error_report(error_code: str) -> dict[str, object]:
    safe_error = (
        error_code
        if error_code in _ALLOWED_ERROR_CODES
        else "invalid_phase28_stub_activity_implementation_validation_report"
    )
    return {
        "type": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VERSION,
        "phase": "phase29",
        "ok": False,
        "operation": _OPERATION,
        "error_code": safe_error,
        "side_effects": [],
    }


def _raise(error: str) -> None:
    raise ValueError(error)
