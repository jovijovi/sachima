"""Prototype-only production readiness gate for FlowWeaver shadow integration."""

from __future__ import annotations

FLOWWEAVER_PRODUCTION_READINESS_GATE_VERSION = "flowweaver.production_readiness_gate.v0"
GATEWAY_BOUNDARY_DESCRIPTOR_TYPE = "flowweaver.gateway_boundary_descriptor.v0"
READINESS_REPORT_TYPE = "flowweaver.production_readiness_report.v0"

_PHASE = "phase8_production_readiness_gate"
_READY_VERDICT = "ready_for_controlled_shadow_design"
_BLOCKED_VERDICT = "blocked"
_PHASE7_LOOP_VERSION = "flowweaver.gateway_shadow_e2e_loop.v0"
_PHASE7_OPERATION = "gateway_shadow_e2e_loop"
_PHASE7_PUBLICATION_TYPE = "flowweaver.gateway_shadow_publication.v0"
_PHASE6_ACK_BRIDGE_VERSION = "flowweaver.gateway_ack_shadow_bridge.v0"
_CANDIDATE_CONTRACT_VERSION = "flowweaver.controlled_shadow_candidate.v0"
_RUNTIME_BOUNDARY_TYPE = "flowweaver.runtime_boundary_descriptor.v0"
_OPERATIONAL_POLICY_TYPE = "flowweaver.operational_policy.v0"
_ALLOWED_PHASE7_KEYS = {
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
}
_REQUIRED_PHASE7_CHECKS = {
    "start_accepted",
    "initial_snapshot_safe",
    "publication_envelope_safe",
    "delivery_targets_initialized",
    "ack_count_matches_publication",
    "final_snapshot_safe",
    "side_effects_absent",
}
_ALLOWED_PUBLICATION_KEYS = {
    "type",
    "loop_version",
    "workflow_id",
    "transaction_id",
    "surface_counts",
    "delivery_plan",
    "side_effects",
}
_ALLOWED_DELIVERY_KEYS = {"delivery_key", "surface", "target_kind", "target_id", "status"}
_ALLOWED_ACK_RESULT_KEYS = {"target_id", "surface", "status", "ack_status"}
_ALLOWED_PHASE7_START_STATUSES = ("started", "running")
_ALLOWED_SURFACES = ("final_text", "rich_card", "progress_card", "media")
_ALLOWED_ACK_STATUSES = ("sent", "failed", "acknowledged")
_ALLOWED_ACK_RESULT_STATUSES = ("applied", "duplicate", "rejected")
_GATEWAY_KEYS = {
    "type",
    "mode",
    "surfaces",
    "ack_source",
    "delivery_effects",
    "adapter_imports_allowed",
    "platform_payloads_allowed",
    "raw_card_payloads_allowed",
    "message_identifiers_allowed",
    "side_effects",
}
_RUNTIME_KEYS = {
    "type",
    "control_surface",
    "temporal_dependency",
    "client_lifecycle",
    "event_ingress",
    "claim_check_policy",
    "side_effects",
}
_OPERATIONAL_KEYS = {
    "type",
    "default_state",
    "production_actions_require_separate_approval",
    "rollback_required",
    "observability_required",
    "config_write_allowed",
    "registry_write_allowed",
    "service_lifecycle_allowed",
    "gateway_restart_allowed",
    "side_effects",
}
_REPORT_FIELDS = {
    "type",
    "version",
    "ok",
    "verdict",
    "phase",
    "workflow_id",
    "transaction_id",
    "candidate_contract",
    "checks",
    "required_separate_approvals",
    "runbook_outline",
    "side_effects",
    "error_code",
}
_ERROR_CODES = {
    "invalid_phase7_result",
    "invalid_gateway_boundary",
    "invalid_runtime_boundary",
    "invalid_operational_policy",
    "unsafe_material",
    "side_effects_not_absent",
    "production_action_requested",
    "workflow_id_mismatch",
    "delivery_target_mismatch",
    "not_shadow_only",
    "runtime_lifecycle_requested",
    "registry_or_config_write_requested",
}
_REQUIRED_SEPARATE_APPROVALS = [
    "production_gateway_wiring",
    "production_config_write",
    "gateway_restart",
    "external_temporal_service",
    "real_send_edit_render_callback",
    "production_tool_registry",
    "remote_branch_or_worktree_cleanup",
]
_RUNBOOK_OUTLINE = [
    "phase8_proves_readiness_only",
    "production_activation_requires_separate_design_and_approval",
    "keep_default_off_until_explicit_enablement",
    "rollback_plan_required_before_gateway_wiring",
    "no_raw_payloads_or_secrets_in_reports_or_runtime_history",
    "use_direct_pytest_for_integration_regression",
]
_FAIL_CLOSED_ERRORS = sorted(_ERROR_CODES)
_FORBIDDEN_MATERIAL = [
    "raw_prompt",
    "raw_tool_output",
    "raw_card_json",
    "raw_media_payload",
    "raw_platform_payload",
    "platform_message_identifiers",
    "credentials_or_connection_strings",
]
_UNSAFE_KEY_SUBSTRINGS = (
    "raw_",
    "tool_output",
    "platform_payload",
    "platform_id",
    "chat_id",
    "user_id",
    "message_id",
    "card_json",
    "media_path",
    "delivery_ack_payload",
    "credential",
    "password",
    "api_key",
    "bearer",
    "connection_string",
    "callback_url",
)
_UNSAFE_EXACT_KEYS = {"token", "secret", "forbidden_material", "runbook_outline"}
_UNSAFE_VALUE_MARKERS = (
    "raw_prompt",
    "raw_tool_output",
    "raw_card",
    "raw_media",
    "raw_platform",
    "platform_message_identifiers",
    "unsafe-" + "token",
    "sk" + "-",
    "bearer ",
    "password" + "=",
    "secret" + "=",
    "api" + "_key=",
    "access_" + "tok" + "en=",
    "client_" + "sec" + "ret=",
    "signature=",
    "postgres://",
    "mysql://",
    "mongodb://",
    "redis://",
)
_PRIVATE_PREFIXES = ("om_", "oc_", "ou_", "chat_", "message_", "platform_", "feishu_", "lark_", "telegram_")
_SYNTHETIC_ID_FORBIDDEN_SUBSTRINGS = (
    "allowed_runtime_events",
    "claim_check_policy",
    "forbidden_material",
    "raw_",
    "tool_output",
    "platform_payload",
    "token",
    "secret",
    "password",
    "credential",
    "api_key",
    "bearer",
    "sk" + "-",
)
_RUNTIME_LIFECYCLE_EXTRA_KEYS = {
    "temporal_address",
    "task_queue",
    "worker",
    "workflow_environment",
    "client_factory",
    "connect_helper",
    "dock" + "er",
    "dae" + "mon",
    "service",
}
_INVALID = object()


def evaluate_flowweaver_production_readiness(
    *,
    phase7_result: object,
    gateway_boundary: object,
    runtime_boundary: object,
    operational_policy: object,
) -> dict[str, object]:
    """Evaluate whether a Phase 7 shadow proof is ready for controlled-shadow design."""

    try:
        phase7 = _validate_phase7_result(phase7_result)
        gateway = _validate_gateway_boundary(gateway_boundary)
        _validate_runtime_boundary(runtime_boundary)
        _validate_operational_policy(operational_policy)
    except ValueError as exc:
        return _error_result(_safe_error_code(str(exc)))

    return _success_result(
        workflow_id=phase7["workflow_id"],
        transaction_id=phase7["transaction_id"],
        surfaces=gateway["surfaces"],
    )


def _validate_phase7_result(value: object) -> dict[str, object]:
    result = _plain_dict(value, error="invalid_phase7_result")
    _reject_unsafe_material(result, error="unsafe_material")
    if set(result) != _ALLOWED_PHASE7_KEYS:
        _raise("invalid_phase7_result")
    if result["side_effects"] != []:
        _raise("side_effects_not_absent")
    if not (result["ok"] is True and result["loop_version"] == _PHASE7_LOOP_VERSION and result["operation"] == _PHASE7_OPERATION):
        _raise("invalid_phase7_result")
    if result["start_status"] not in _ALLOWED_PHASE7_START_STATUSES:
        _raise("invalid_phase7_result")
    workflow_id = _runtime_transaction_id(result["workflow_id"], error="invalid_phase7_result")
    transaction_id = _runtime_transaction_id(result["transaction_id"], error="invalid_phase7_result")
    if workflow_id != transaction_id:
        _raise("workflow_id_mismatch")
    checks = _plain_dict(result["checks"], error="invalid_phase7_result")
    if set(checks) != _REQUIRED_PHASE7_CHECKS or any(checks[key] is not True for key in _REQUIRED_PHASE7_CHECKS):
        _raise("invalid_phase7_result")
    publication = _validate_phase7_publication(result["publication"], workflow_id=workflow_id)
    snapshot = _validate_phase7_snapshot(result["final_snapshot"], workflow_id=workflow_id)
    _validate_ack_results(result["ack_results"], publication["delivery_targets"])
    snapshot_targets = snapshot["delivery_targets"]
    if any(target not in snapshot_targets for target in publication["delivery_targets"]):
        _raise("delivery_target_mismatch")
    return {"workflow_id": workflow_id, "transaction_id": transaction_id}


def _validate_phase7_publication(value: object, *, workflow_id: str) -> dict[str, object]:
    publication = _plain_dict(value, error="invalid_phase7_result")
    if set(publication) != _ALLOWED_PUBLICATION_KEYS:
        _raise("invalid_phase7_result")
    if publication["side_effects"] != []:
        _raise("side_effects_not_absent")
    if not (
        publication["type"] == _PHASE7_PUBLICATION_TYPE
        and publication["loop_version"] == _PHASE7_LOOP_VERSION
        and publication["workflow_id"] == workflow_id
        and publication["transaction_id"] == workflow_id
    ):
        _raise("invalid_phase7_result")
    surface_counts = _plain_int_dict(publication["surface_counts"], error="invalid_phase7_result")
    if set(surface_counts) != set(_ALLOWED_SURFACES) or any(surface_counts[surface] < 0 for surface in _ALLOWED_SURFACES):
        _raise("invalid_phase7_result")
    delivery_plan = _plain_list(publication["delivery_plan"], error="invalid_phase7_result")
    counted = {surface: 0 for surface in _ALLOWED_SURFACES}
    targets: list[str] = []
    for item in delivery_plan:
        delivery = _plain_dict(item, error="invalid_phase7_result")
        if set(delivery) != _ALLOWED_DELIVERY_KEYS:
            _raise("invalid_phase7_result")
        surface = _literal(delivery["surface"], allowed=_ALLOWED_SURFACES, error="invalid_phase7_result")
        counted[surface] += 1
        _synthetic_id(delivery["delivery_key"], prefixes=("runtime_event_",), error="invalid_phase7_result")
        if delivery["target_kind"] != "delivery":
            _raise("invalid_phase7_result")
        target = _synthetic_id(delivery["target_id"], prefixes=("runtime_delivery_",), error="invalid_phase7_result")
        _literal(delivery["status"], allowed=_ALLOWED_ACK_STATUSES, error="invalid_phase7_result")
        targets.append(target)
    if counted != surface_counts:
        _raise("invalid_phase7_result")
    return {"delivery_targets": tuple(targets)}


def _validate_phase7_snapshot(value: object, *, workflow_id: str) -> dict[str, object]:
    snapshot = _plain_dict(value, error="invalid_phase7_result")
    if snapshot.get("transaction_id") != workflow_id:
        _raise("workflow_id_mismatch")
    if snapshot.get("side_effects") != []:
        _raise("side_effects_not_absent")
    delivery_statuses = _plain_dict(snapshot.get("delivery_statuses"), error="invalid_phase7_result")
    targets = tuple(
        _synthetic_id(target, prefixes=("runtime_delivery_",), error="invalid_phase7_result")
        for target in sorted(delivery_statuses)
    )
    for status in delivery_statuses.values():
        _literal(status, allowed=("planned",) + _ALLOWED_ACK_STATUSES, error="invalid_phase7_result")
    return {"delivery_targets": targets}


def _validate_ack_results(value: object, delivery_targets: tuple[str, ...]) -> None:
    ack_results = _plain_list(value, error="invalid_phase7_result")
    if len(ack_results) != len(delivery_targets):
        _raise("delivery_target_mismatch")
    for item in ack_results:
        ack = _plain_dict(item, error="invalid_phase7_result")
        if set(ack) != _ALLOWED_ACK_RESULT_KEYS:
            _raise("invalid_phase7_result")
        target = _synthetic_id(ack["target_id"], prefixes=("runtime_delivery_",), error="invalid_phase7_result")
        if target not in delivery_targets:
            _raise("delivery_target_mismatch")
        _literal(ack["surface"], allowed=_ALLOWED_SURFACES, error="invalid_phase7_result")
        _literal(ack["status"], allowed=_ALLOWED_ACK_STATUSES, error="invalid_phase7_result")
        _literal(ack["ack_status"], allowed=_ALLOWED_ACK_RESULT_STATUSES, error="invalid_phase7_result")


def _validate_gateway_boundary(value: object) -> dict[str, object]:
    boundary = _plain_dict(value, error="invalid_gateway_boundary")
    _reject_unsafe_material(boundary, error="unsafe_material", allow_descriptor_policy_names=True)
    if _has_truthy(boundary, ("adapter_imports_allowed",)):
        _raise("production_action_requested")
    if _has_truthy(boundary, ("platform_payloads_allowed", "raw_card_payloads_allowed", "message_identifiers_allowed")):
        _raise("unsafe_material")
    mode = boundary.get("mode")
    delivery_effects = boundary.get("delivery_effects")
    if type(mode) is not str or type(delivery_effects) is not str:
        _raise("invalid_gateway_boundary")
    if mode in {"production", "live", "enabled"} or delivery_effects in {
        "send",
        "edit",
        "render",
        "callback",
    }:
        _raise("production_action_requested")
    if set(boundary) != _GATEWAY_KEYS:
        _raise("invalid_gateway_boundary")
    if boundary["side_effects"] != []:
        _raise("side_effects_not_absent")
    if boundary["type"] != GATEWAY_BOUNDARY_DESCRIPTOR_TYPE:
        _raise("invalid_gateway_boundary")
    if boundary["mode"] not in {"shadow_only", "controlled_shadow_candidate"}:
        _raise("not_shadow_only")
    if boundary["ack_source"] != "phase6_shadow_bridge" or boundary["delivery_effects"] != "none":
        _raise("invalid_gateway_boundary")
    if not all(boundary[key] is False for key in ("adapter_imports_allowed", "platform_payloads_allowed", "raw_card_payloads_allowed", "message_identifiers_allowed")):
        _raise("invalid_gateway_boundary")
    surfaces = _plain_string_list(boundary["surfaces"], error="invalid_gateway_boundary")
    if any(surface not in _ALLOWED_SURFACES for surface in surfaces):
        _raise("invalid_gateway_boundary")
    if len(set(surfaces)) != len(surfaces):
        _raise("invalid_gateway_boundary")
    if [surface for surface in _ALLOWED_SURFACES if surface in surfaces] != surfaces:
        _raise("invalid_gateway_boundary")
    return {"surfaces": surfaces}


def _validate_runtime_boundary(value: object) -> None:
    boundary = _plain_dict(value, error="invalid_runtime_boundary")
    _reject_unsafe_material(boundary, error="unsafe_material", allow_descriptor_policy_names=True)
    extra = set(boundary) - _RUNTIME_KEYS
    if extra & _RUNTIME_LIFECYCLE_EXTRA_KEYS:
        _raise("runtime_lifecycle_requested")
    if extra:
        _raise("invalid_runtime_boundary")
    if boundary["side_effects"] != []:
        _raise("side_effects_not_absent")
    if boundary["type"] != _RUNTIME_BOUNDARY_TYPE:
        _raise("invalid_runtime_boundary")
    if not (
        boundary["control_surface"] == "phase5k_control_surface"
        and boundary["temporal_dependency"] == "optional_extra_only"
        and boundary["client_lifecycle"] == "caller_supplied_only"
        and boundary["event_ingress"] == "validated_updates_only"
        and boundary["claim_check_policy"] == "refs_only"
    ):
        _raise("runtime_lifecycle_requested")


def _validate_operational_policy(value: object) -> None:
    policy = _plain_dict(value, error="invalid_operational_policy")
    _reject_unsafe_material(policy, error="unsafe_material", allow_descriptor_policy_names=True)
    if set(policy) != _OPERATIONAL_KEYS:
        _raise("invalid_operational_policy")
    if policy["side_effects"] != []:
        _raise("side_effects_not_absent")
    if policy["type"] != _OPERATIONAL_POLICY_TYPE:
        _raise("invalid_operational_policy")
    if policy["config_write_allowed"] is True or policy["registry_write_allowed"] is True:
        _raise("registry_or_config_write_requested")
    if policy["service_lifecycle_allowed"] is True:
        _raise("runtime_lifecycle_requested")
    if policy["gateway_restart_allowed"] is True:
        _raise("production_action_requested")
    if policy["default_state"] != "off" or policy["production_actions_require_separate_approval"] is not True:
        _raise("production_action_requested")
    if policy["rollback_required"] is not True or policy["observability_required"] is not True:
        _raise("invalid_operational_policy")
    if not all(policy[key] is False for key in ("config_write_allowed", "registry_write_allowed", "service_lifecycle_allowed", "gateway_restart_allowed")):
        _raise("invalid_operational_policy")


def _success_result(*, workflow_id: str, transaction_id: str, surfaces: list[str]) -> dict[str, object]:
    report: dict[str, object] = {
        "type": READINESS_REPORT_TYPE,
        "version": FLOWWEAVER_PRODUCTION_READINESS_GATE_VERSION,
        "ok": True,
        "verdict": _READY_VERDICT,
        "phase": _PHASE,
        "workflow_id": workflow_id,
        "transaction_id": transaction_id,
        "candidate_contract": {
            "contract_version": _CANDIDATE_CONTRACT_VERSION,
            "runtime_operations": ["start_transaction", "query_transaction", "reconcile_delivery_ack"],
            "ack_bridge_version": _PHASE6_ACK_BRIDGE_VERSION,
            "shadow_loop_version": _PHASE7_LOOP_VERSION,
            "allowed_surfaces": list(surfaces),
            "forbidden_material": list(_FORBIDDEN_MATERIAL),
            "fail_closed_errors": list(_FAIL_CLOSED_ERRORS),
            "rollback_hooks_required": True,
        },
        "checks": {
            "phase7_result_safe": True,
            "gateway_boundary_shadow_only": True,
            "runtime_boundary_lifecycle_free": True,
            "operational_policy_default_off": True,
            "delivery_targets_match_snapshot": True,
            "production_actions_separate": True,
            "side_effects_absent": True,
        },
        "required_separate_approvals": list(_REQUIRED_SEPARATE_APPROVALS),
        "runbook_outline": list(_RUNBOOK_OUTLINE),
        "side_effects": [],
    }
    _assert_report_shape(report)
    return report


def _error_result(error_code: str) -> dict[str, object]:
    report: dict[str, object] = {
        "type": READINESS_REPORT_TYPE,
        "version": FLOWWEAVER_PRODUCTION_READINESS_GATE_VERSION,
        "ok": False,
        "verdict": _BLOCKED_VERDICT,
        "phase": _PHASE,
        "error_code": _safe_error_code(error_code),
        "side_effects": [],
    }
    _assert_report_shape(report)
    return report


def _plain_copy(value: object) -> object:
    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is list:
        items: list[object] = []
        for item in value:
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            items.append(copied)
        return items
    if type(value) is tuple:
        items: list[object] = []
        for item in value:
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            items.append(copied)
        return items
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


def _plain_string_list(value: object, *, error: str) -> list[str]:
    copied = _plain_list(value, error=error)
    if not all(type(item) is str for item in copied):
        _raise(error)
    return copied


def _plain_int_dict(value: object, *, error: str) -> dict[str, int]:
    copied = _plain_dict(value, error=error)
    if not all(type(key) is str and type(item) is int for key, item in copied.items()):
        _raise(error)
    return {key: item for key, item in copied.items() if type(item) is int}


def _literal(value: object, *, allowed: tuple[str, ...], error: str) -> str:
    if type(value) is not str or value not in allowed:
        _raise(error)
    return value


def _runtime_transaction_id(value: object, *, error: str) -> str:
    return _synthetic_id(value, prefixes=("runtime_tx_",), error=error)


def _synthetic_id(value: object, *, prefixes: tuple[str, ...], error: str) -> str:
    if type(value) is not str or not value or len(value) > 128:
        _raise(error)
    lowered = value.lower()
    if not lowered.startswith(prefixes):
        _raise(error)
    if any(lowered.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
        _raise(error)
    prefix = next((item for item in prefixes if lowered.startswith(item)), "")
    body = lowered[len(prefix) :]
    if any(marker in body for marker in ("om_", "oc_", "ou_", "chat", "message", "platform", "feishu", "lark", "telegram", "private")):
        _raise(error)
    if any(marker in lowered for marker in _SYNTHETIC_ID_FORBIDDEN_SUBSTRINGS):
        _raise(error)
    if not all(("a" <= char <= "z") or ("0" <= char <= "9") or char == "_" for char in lowered):
        _raise(error)
    return value


def _reject_unsafe_material(
    value: object,
    *,
    error: str,
    allow_report_policy_names: bool = False,
    allow_descriptor_policy_names: bool = False,
    path: tuple[str, ...] = (),
) -> None:
    if allow_report_policy_names and path and path[-1] in {"forbidden_material", "runbook_outline"}:
        return
    descriptor_policy_keys = _GATEWAY_KEYS | _RUNTIME_KEYS | _OPERATIONAL_KEYS
    if type(value) is dict:
        for key, item in value.items():
            lowered = key.lower()
            allow_key_name = allow_descriptor_policy_names and not path and key in descriptor_policy_keys
            if not allow_key_name and any(lowered.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
                _raise(error)
            if not allow_key_name and (
                lowered in _UNSAFE_EXACT_KEYS or any(marker in lowered for marker in _UNSAFE_KEY_SUBSTRINGS)
            ):
                _raise(error)
            _reject_unsafe_material(
                item,
                error=error,
                allow_report_policy_names=allow_report_policy_names,
                allow_descriptor_policy_names=allow_descriptor_policy_names,
                path=path + (key,),
            )
        return
    if type(value) is list:
        for item in value:
            _reject_unsafe_material(
                item,
                error=error,
                allow_report_policy_names=allow_report_policy_names,
                allow_descriptor_policy_names=allow_descriptor_policy_names,
                path=path,
            )
        return
    if type(value) is str:
        lowered = value.lower()
        if any(lowered.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
            _raise(error)
        if any(marker in lowered for marker in _UNSAFE_VALUE_MARKERS):
            _raise(error)


def _has_truthy(mapping: dict[str, object], keys: tuple[str, ...]) -> bool:
    return any(mapping.get(key) is True for key in keys)


def _safe_error_code(error_code: object) -> str:
    if type(error_code) is str and error_code in _ERROR_CODES:
        return error_code
    return "invalid_phase7_result"


def _assert_report_shape(report: dict[str, object]) -> None:
    if not set(report) <= _REPORT_FIELDS:
        _raise("unsafe_material")


def _raise(code: str) -> None:
    raise ValueError(code)


__all__ = [
    "FLOWWEAVER_PRODUCTION_READINESS_GATE_VERSION",
    "GATEWAY_BOUNDARY_DESCRIPTOR_TYPE",
    "READINESS_REPORT_TYPE",
    "evaluate_flowweaver_production_readiness",
]
