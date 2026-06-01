"""Prototype-only controlled-shadow design plan builder for FlowWeaver."""

from __future__ import annotations

FLOWWEAVER_CONTROLLED_SHADOW_DESIGN_VERSION = "flowweaver.controlled_shadow_design.v0"
CONTROLLED_SHADOW_SCOPE_DESCRIPTOR_TYPE = "flowweaver.controlled_shadow_scope.v0"
GATEWAY_OBSERVATION_BOUNDARY_TYPE = "flowweaver.gateway_observation_boundary.v0"
RUNTIME_EXECUTION_BOUNDARY_TYPE = "flowweaver.runtime_execution_boundary.v0"
CONTROLLED_SHADOW_ARTIFACT_POLICY_TYPE = "flowweaver.controlled_shadow_artifact_policy.v0"
CONTROLLED_SHADOW_ROLLBACK_POLICY_TYPE = "flowweaver.controlled_shadow_rollback_policy.v0"
CONTROLLED_SHADOW_PLAN_TYPE = "flowweaver.controlled_shadow_plan.v0"

_PHASE = "phase9_controlled_shadow_design"
_READY_VERDICT = "ready_for_controlled_shadow_prototype"
_BLOCKED_VERDICT = "blocked"
_PHASE8_REPORT_TYPE = "flowweaver.production_readiness_report.v0"
_PHASE8_REPORT_VERSION = "flowweaver.production_readiness_gate.v0"
_PHASE8_PHASE = "phase8_production_readiness_gate"
_PHASE8_READY_VERDICT = "ready_for_controlled_shadow_design"
_PHASE8_CANDIDATE_CONTRACT_VERSION = "flowweaver.controlled_shadow_candidate.v0"
_PHASE6_ACK_BRIDGE_VERSION = "flowweaver.gateway_ack_shadow_bridge.v0"
_PHASE7_SHADOW_LOOP_VERSION = "flowweaver.gateway_shadow_e2e_loop.v0"
_ALLOWED_SURFACES = ("final_text", "rich_card", "progress_card", "media")
_ALLOWED_RUNTIME_OPERATIONS = ("start_transaction", "query_transaction", "reconcile_delivery_ack")
_REQUIRED_PHASE8_CHECKS = {
    "phase7_result_safe",
    "gateway_boundary_shadow_only",
    "runtime_boundary_lifecycle_free",
    "operational_policy_default_off",
    "delivery_targets_match_snapshot",
    "production_actions_separate",
    "side_effects_absent",
}
_PHASE8_REPORT_FIELDS = {
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
}
_PHASE8_CANDIDATE_FIELDS = {
    "contract_version",
    "runtime_operations",
    "ack_bridge_version",
    "shadow_loop_version",
    "allowed_surfaces",
    "forbidden_material",
    "fail_closed_errors",
    "rollback_hooks_required",
}
_SHADOW_SCOPE_KEYS = {
    "type",
    "mode",
    "source_kind",
    "max_transactions",
    "max_delivery_surfaces",
    "allowed_surfaces",
    "operator_approval_ref",
    "feature_flag_ref",
    "side_effects",
}
_GATEWAY_OBSERVATION_KEYS = {
    "type",
    "observation_mode",
    "inbound_material",
    "outbound_effects",
    "adapter_imports_allowed",
    "platform_payloads_allowed",
    "message_identifiers_allowed",
    "ack_source",
    "side_effects",
}
_RUNTIME_EXECUTION_KEYS = {
    "type",
    "control_surface",
    "client_lifecycle",
    "temporal_dependency",
    "event_ingress",
    "allowed_operations",
    "worker_lifecycle",
    "side_effects",
}
_ARTIFACT_POLICY_KEYS = {
    "type",
    "artifact_mode",
    "allowed_fields",
    "forbidden_material",
    "retention",
    "log_policy",
    "side_effects",
}
_ROLLBACK_POLICY_KEYS = {
    "type",
    "default_state",
    "kill_switch_required",
    "rollback_plan_required",
    "production_actions_require_separate_approval",
    "config_write_allowed",
    "registry_write_allowed",
    "gateway_restart_allowed",
    "service_lifecycle_allowed",
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
    "controlled_shadow_plan",
    "checks",
    "artifact_policy",
    "required_separate_approvals",
    "verification_matrix",
    "runbook_outline",
    "side_effects",
    "error_code",
}
_ERROR_CODES = {
    "invalid_readiness_report",
    "invalid_shadow_scope",
    "invalid_gateway_observation_boundary",
    "invalid_runtime_execution_boundary",
    "invalid_artifact_policy",
    "invalid_rollback_policy",
    "unsafe_material",
    "side_effects_not_absent",
    "production_action_requested",
    "workflow_id_mismatch",
    "runtime_lifecycle_requested",
    "registry_or_config_write_requested",
    "artifact_policy_violation",
}
_PHASE8_FAIL_CLOSED_ERRORS = sorted(
    {
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
)
_REQUIRED_SEPARATE_APPROVALS = [
    "production_gateway_wiring",
    "production_config_write",
    "gateway_restart",
    "external_temporal_service",
    "real_send_edit_render_callback",
    "production_tool_registry",
    "remote_branch_or_worktree_cleanup",
]
_PHASE8_FORBIDDEN_MATERIAL = [
    "raw_prompt",
    "raw_tool_output",
    "raw_card_json",
    "raw_media_payload",
    "raw_platform_payload",
    "platform_message_identifiers",
    "credentials_or_connection_strings",
]
_PHASE9_FORBIDDEN_MATERIAL = [
    *_PHASE8_FORBIDDEN_MATERIAL,
    "raw_exception_text",
]
_PHASE8_RUNBOOK_OUTLINE = [
    "phase8_proves_readiness_only",
    "production_activation_requires_separate_design_and_approval",
    "keep_default_off_until_explicit_enablement",
    "rollback_plan_required_before_gateway_wiring",
    "no_raw_payloads_or_secrets_in_reports_or_runtime_history",
    "use_direct_pytest_for_integration_regression",
]
_ALLOWED_ARTIFACT_FIELDS = (
    "run_id",
    "transaction_id",
    "operation_counts",
    "delivery_counts",
    "statuses",
    "digests",
    "stable_error_codes",
    "approvals",
    "side_effects",
)
_VERIFICATION_MATRIX = [
    "phase8_report_exact_shape",
    "scope_default_off",
    "gateway_observation_only",
    "runtime_lifecycle_free",
    "validated_updates_only",
    "artifact_safe_summary_only",
    "rollback_and_kill_switch_present",
    "production_actions_separate",
    "side_effects_absent",
]
_RUNBOOK_OUTLINE = [
    "phase9_is_controlled_shadow_design_only",
    "prototype_shadow_requires_explicit_implementation_approval",
    "production_activation_requires_separate_design_and_approval",
    "keep_default_off_until_explicit_enablement",
    "rollback_and_kill_switch_required_before_any_wiring",
    "no_raw_payloads_or_secrets_in_reports_or_artifacts",
    "use_direct_pytest_for_integration_regression",
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
    "raw_exception_text",
    "platform_payload_value",
    "card_payload_value",
    "media_path_value",
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
    "subprocess",
    "dock" + "er",
    "dae" + "mon",
    "service",
}
_DESCRIPTOR_POLICY_KEYS = _SHADOW_SCOPE_KEYS | _GATEWAY_OBSERVATION_KEYS | _RUNTIME_EXECUTION_KEYS | _ARTIFACT_POLICY_KEYS | _ROLLBACK_POLICY_KEYS
_POLICY_VALUE_FIELDS = {"allowed_fields", "forbidden_material", "runbook_outline"}
_INVALID = object()


def build_flowweaver_controlled_shadow_plan(
    *,
    readiness_report: object,
    shadow_scope: object,
    gateway_observation_boundary: object,
    runtime_execution_boundary: object,
    artifact_policy: object,
    rollback_policy: object,
) -> dict[str, object]:
    """Build a safe prototype-only controlled-shadow plan from static descriptors."""

    try:
        readiness = _validate_readiness_report(readiness_report)
        scope = _validate_shadow_scope(shadow_scope, allowed_surfaces=readiness["allowed_surfaces"])
        gateway = _validate_gateway_observation_boundary(gateway_observation_boundary)
        runtime = _validate_runtime_execution_boundary(
            runtime_execution_boundary,
            allowed_operations=readiness["runtime_operations"],
        )
        artifact = _validate_artifact_policy(artifact_policy)
        rollback = _validate_rollback_policy(rollback_policy)
    except ValueError as exc:
        return _error_result(_safe_error_code(str(exc)))

    allowed_surfaces = _bounded_ordered_intersection(scope["allowed_surfaces"], readiness["allowed_surfaces"])
    runtime_operations = _bounded_ordered_intersection(runtime["allowed_operations"], readiness["runtime_operations"])
    if not allowed_surfaces or not runtime_operations:
        return _error_result("invalid_shadow_scope")

    return _success_result(
        workflow_id=readiness["workflow_id"],
        transaction_id=readiness["transaction_id"],
        source_kind=scope["source_kind"],
        mode=scope["mode"],
        allowed_surfaces=allowed_surfaces,
        max_transactions=scope["max_transactions"],
        max_delivery_surfaces=scope["max_delivery_surfaces"],
        runtime_operations=runtime_operations,
        ack_source=gateway["ack_source"],
        artifact=artifact,
        approval_refs={
            "operator_approval_ref": scope["operator_approval_ref"],
            "feature_flag_ref": scope["feature_flag_ref"],
        },
        rollback_hooks_required=readiness["rollback_hooks_required"],
        kill_switch_required=rollback["kill_switch_required"],
    )


def _validate_readiness_report(value: object) -> dict[str, object]:
    report = _plain_dict(value, error="invalid_readiness_report")
    _reject_unsafe_material(report, error="unsafe_material", allow_policy_value_fields=True)
    if set(report) != _PHASE8_REPORT_FIELDS:
        _raise("invalid_readiness_report")
    if report["side_effects"] != []:
        _raise("side_effects_not_absent")
    if not (
        report["type"] == _PHASE8_REPORT_TYPE
        and report["version"] == _PHASE8_REPORT_VERSION
        and report["ok"] is True
        and report["verdict"] == _PHASE8_READY_VERDICT
        and report["phase"] == _PHASE8_PHASE
    ):
        _raise("invalid_readiness_report")
    workflow_id = _runtime_transaction_id(report["workflow_id"], error="invalid_readiness_report")
    transaction_id = _runtime_transaction_id(report["transaction_id"], error="invalid_readiness_report")
    if workflow_id != transaction_id:
        _raise("workflow_id_mismatch")
    checks = _plain_dict(report["checks"], error="invalid_readiness_report")
    if set(checks) != _REQUIRED_PHASE8_CHECKS or any(checks[key] is not True for key in _REQUIRED_PHASE8_CHECKS):
        _raise("invalid_readiness_report")
    candidate = _validate_candidate_contract(report["candidate_contract"])
    approvals = _plain_string_list(report["required_separate_approvals"], error="invalid_readiness_report")
    if approvals != list(_REQUIRED_SEPARATE_APPROVALS):
        _raise("invalid_readiness_report")
    runbook = _plain_string_list(report["runbook_outline"], error="invalid_readiness_report")
    if runbook != list(_PHASE8_RUNBOOK_OUTLINE):
        _raise("invalid_readiness_report")
    return {
        "workflow_id": workflow_id,
        "transaction_id": transaction_id,
        "allowed_surfaces": candidate["allowed_surfaces"],
        "runtime_operations": candidate["runtime_operations"],
        "rollback_hooks_required": candidate["rollback_hooks_required"],
    }


def _validate_candidate_contract(value: object) -> dict[str, object]:
    candidate = _plain_dict(value, error="invalid_readiness_report")
    if set(candidate) != _PHASE8_CANDIDATE_FIELDS:
        _raise("invalid_readiness_report")
    if not (
        candidate["contract_version"] == _PHASE8_CANDIDATE_CONTRACT_VERSION
        and candidate["ack_bridge_version"] == _PHASE6_ACK_BRIDGE_VERSION
        and candidate["shadow_loop_version"] == _PHASE7_SHADOW_LOOP_VERSION
        and candidate["rollback_hooks_required"] is True
    ):
        _raise("invalid_readiness_report")
    operations = _plain_string_list(candidate["runtime_operations"], error="invalid_readiness_report")
    if operations != list(_ALLOWED_RUNTIME_OPERATIONS):
        _raise("invalid_readiness_report")
    surfaces = _ordered_surfaces(candidate["allowed_surfaces"], error="invalid_readiness_report")
    forbidden = _plain_string_list(candidate["forbidden_material"], error="invalid_readiness_report")
    if forbidden != list(_PHASE8_FORBIDDEN_MATERIAL):
        _raise("invalid_readiness_report")
    phase8_errors = _plain_string_list(candidate["fail_closed_errors"], error="invalid_readiness_report")
    if phase8_errors != list(_PHASE8_FAIL_CLOSED_ERRORS):
        _raise("invalid_readiness_report")
    return {
        "allowed_surfaces": surfaces,
        "runtime_operations": operations,
        "rollback_hooks_required": True,
    }


def _validate_shadow_scope(value: object, *, allowed_surfaces: list[str]) -> dict[str, object]:
    scope = _plain_dict(value, error="invalid_shadow_scope")
    _reject_unsafe_material(scope, error="unsafe_material", allow_descriptor_policy_names=True)
    if set(scope) != _SHADOW_SCOPE_KEYS:
        _raise("invalid_shadow_scope")
    if scope["side_effects"] != []:
        _raise("side_effects_not_absent")
    if scope["type"] != CONTROLLED_SHADOW_SCOPE_DESCRIPTOR_TYPE:
        _raise("invalid_shadow_scope")
    mode = _safe_string(scope["mode"], error="invalid_shadow_scope")
    source_kind = _safe_string(scope["source_kind"], error="invalid_shadow_scope")
    if mode in {"production", "live", "enabled"} or source_kind in {"live_gateway_stream", "real_feishu", "real_sachima"}:
        _raise("production_action_requested")
    if mode not in {"design_only", "prototype_shadow_candidate"}:
        _raise("invalid_shadow_scope")
    if source_kind not in {"phase7_result_replay", "phase8_readiness_replay", "simulator_fixture"}:
        _raise("invalid_shadow_scope")
    max_transactions = _bounded_int(scope["max_transactions"], minimum=1, maximum=20, error="invalid_shadow_scope")
    max_delivery_surfaces = _bounded_int(
        scope["max_delivery_surfaces"],
        minimum=0,
        maximum=20,
        error="invalid_shadow_scope",
    )
    surfaces = _ordered_surfaces(scope["allowed_surfaces"], error="invalid_shadow_scope")
    if not set(surfaces) <= set(allowed_surfaces) or len(surfaces) > max_delivery_surfaces:
        _raise("invalid_shadow_scope")
    operator_approval_ref = _synthetic_id(
        scope["operator_approval_ref"],
        prefixes=("approval_ref_",),
        error="invalid_shadow_scope",
    )
    feature_flag_ref = _synthetic_id(
        scope["feature_flag_ref"],
        prefixes=("feature_flag_ref_",),
        error="invalid_shadow_scope",
    )
    return {
        "mode": mode,
        "source_kind": source_kind,
        "max_transactions": max_transactions,
        "max_delivery_surfaces": max_delivery_surfaces,
        "allowed_surfaces": surfaces,
        "operator_approval_ref": operator_approval_ref,
        "feature_flag_ref": feature_flag_ref,
    }


def _validate_gateway_observation_boundary(value: object) -> dict[str, object]:
    boundary = _plain_dict(value, error="invalid_gateway_observation_boundary")
    _reject_unsafe_material(boundary, error="unsafe_material", allow_descriptor_policy_names=True)
    if set(boundary) != _GATEWAY_OBSERVATION_KEYS:
        _raise("invalid_gateway_observation_boundary")
    if boundary["side_effects"] != []:
        _raise("side_effects_not_absent")
    if boundary["type"] != GATEWAY_OBSERVATION_BOUNDARY_TYPE:
        _raise("invalid_gateway_observation_boundary")
    observation_mode = _safe_string(boundary["observation_mode"], error="invalid_gateway_observation_boundary")
    outbound_effects = _safe_string(boundary["outbound_effects"], error="invalid_gateway_observation_boundary")
    if observation_mode in {"observe_live_gateway", "mirror_live_gateway"} or outbound_effects in {
        "send",
        "edit",
        "render",
        "callback",
    }:
        _raise("production_action_requested")
    if not (
        observation_mode in {"sanitized_replay_only", "simulator_fixture_only"}
        and boundary["inbound_material"] == "sanitized_refs_only"
        and outbound_effects == "none"
        and boundary["ack_source"] in {"phase6_shadow_bridge", "simulator_ack_fixture"}
    ):
        _raise("invalid_gateway_observation_boundary")
    if boundary["adapter_imports_allowed"] is True:
        _raise("production_action_requested")
    if boundary["platform_payloads_allowed"] is True or boundary["message_identifiers_allowed"] is True:
        _raise("unsafe_material")
    if not all(
        boundary[key] is False
        for key in ("adapter_imports_allowed", "platform_payloads_allowed", "message_identifiers_allowed")
    ):
        _raise("invalid_gateway_observation_boundary")
    return {"ack_source": boundary["ack_source"]}


def _validate_runtime_execution_boundary(value: object, *, allowed_operations: list[str]) -> dict[str, object]:
    boundary = _plain_dict(value, error="invalid_runtime_execution_boundary")
    _reject_unsafe_material(boundary, error="unsafe_material", allow_descriptor_policy_names=True)
    extra = set(boundary) - _RUNTIME_EXECUTION_KEYS
    if extra & _RUNTIME_LIFECYCLE_EXTRA_KEYS:
        _raise("runtime_lifecycle_requested")
    if extra:
        _raise("invalid_runtime_execution_boundary")
    if boundary["side_effects"] != []:
        _raise("side_effects_not_absent")
    if boundary["type"] != RUNTIME_EXECUTION_BOUNDARY_TYPE:
        _raise("invalid_runtime_execution_boundary")
    if not (
        boundary["control_surface"] == "phase5k_control_surface"
        and boundary["client_lifecycle"] == "caller_supplied_only"
        and boundary["temporal_dependency"] == "optional_extra_only"
        and boundary["event_ingress"] == "validated_updates_only"
        and boundary["worker_lifecycle"] == "none"
    ):
        _raise("runtime_lifecycle_requested")
    operations = _plain_string_list(boundary["allowed_operations"], error="invalid_runtime_execution_boundary")
    if not operations or operations != _bounded_ordered_intersection(operations, allowed_operations):
        _raise("runtime_lifecycle_requested")
    return {"allowed_operations": operations}


def _validate_artifact_policy(value: object) -> dict[str, object]:
    policy = _plain_dict(value, error="invalid_artifact_policy")
    _reject_unsafe_material(
        policy,
        error="unsafe_material",
        allow_descriptor_policy_names=True,
        allow_policy_value_fields=True,
    )
    if set(policy) != _ARTIFACT_POLICY_KEYS:
        _raise("invalid_artifact_policy")
    if policy["side_effects"] != []:
        _raise("side_effects_not_absent")
    if not (
        policy["type"] == CONTROLLED_SHADOW_ARTIFACT_POLICY_TYPE
        and policy["artifact_mode"] == "safe_summary_only"
        and policy["retention"] in {"local_artifact_only", "docs_evidence_only"}
        and policy["log_policy"] == "sanitized_codes_only"
    ):
        _raise("invalid_artifact_policy")
    allowed_fields = _plain_string_list(policy["allowed_fields"], error="invalid_artifact_policy")
    if not allowed_fields or allowed_fields != _bounded_ordered_intersection(allowed_fields, list(_ALLOWED_ARTIFACT_FIELDS)):
        _raise("artifact_policy_violation")
    forbidden_material = _plain_string_list(policy["forbidden_material"], error="invalid_artifact_policy")
    if forbidden_material != list(_PHASE9_FORBIDDEN_MATERIAL):
        _raise("artifact_policy_violation")
    return {
        "artifact_mode": "safe_summary_only",
        "allowed_fields": allowed_fields,
        "retention": policy["retention"],
        "log_policy": "sanitized_codes_only",
        "forbidden_material": list(_PHASE9_FORBIDDEN_MATERIAL),
    }


def _validate_rollback_policy(value: object) -> dict[str, object]:
    policy = _plain_dict(value, error="invalid_rollback_policy")
    _reject_unsafe_material(policy, error="unsafe_material", allow_descriptor_policy_names=True)
    if set(policy) != _ROLLBACK_POLICY_KEYS:
        _raise("invalid_rollback_policy")
    if policy["side_effects"] != []:
        _raise("side_effects_not_absent")
    if policy["type"] != CONTROLLED_SHADOW_ROLLBACK_POLICY_TYPE:
        _raise("invalid_rollback_policy")
    if policy["config_write_allowed"] is True or policy["registry_write_allowed"] is True:
        _raise("registry_or_config_write_requested")
    if policy["service_lifecycle_allowed"] is True:
        _raise("runtime_lifecycle_requested")
    if policy["gateway_restart_allowed"] is True:
        _raise("production_action_requested")
    if policy["default_state"] != "off" or policy["production_actions_require_separate_approval"] is not True:
        _raise("production_action_requested")
    if policy["kill_switch_required"] is not True or policy["rollback_plan_required"] is not True:
        _raise("invalid_rollback_policy")
    if not all(
        policy[key] is False
        for key in ("config_write_allowed", "registry_write_allowed", "gateway_restart_allowed", "service_lifecycle_allowed")
    ):
        _raise("invalid_rollback_policy")
    return {"kill_switch_required": True}


def _success_result(
    *,
    workflow_id: str,
    transaction_id: str,
    source_kind: str,
    mode: str,
    allowed_surfaces: list[str],
    max_transactions: int,
    max_delivery_surfaces: int,
    runtime_operations: list[str],
    ack_source: str,
    artifact: dict[str, object],
    approval_refs: dict[str, object],
    rollback_hooks_required: bool,
    kill_switch_required: bool,
) -> dict[str, object]:
    report: dict[str, object] = {
        "type": CONTROLLED_SHADOW_PLAN_TYPE,
        "version": FLOWWEAVER_CONTROLLED_SHADOW_DESIGN_VERSION,
        "ok": True,
        "verdict": _READY_VERDICT,
        "phase": _PHASE,
        "workflow_id": workflow_id,
        "transaction_id": transaction_id,
        "controlled_shadow_plan": {
            "plan_version": FLOWWEAVER_CONTROLLED_SHADOW_DESIGN_VERSION,
            "source_kind": source_kind,
            "mode": mode,
            "allowed_surfaces": list(allowed_surfaces),
            "max_transactions": max_transactions,
            "max_delivery_surfaces": max_delivery_surfaces,
            "runtime_operations": list(runtime_operations),
            "ack_source": ack_source,
            "artifact_mode": artifact["artifact_mode"],
            "approval_refs": dict(approval_refs),
            "rollback_hooks_required": rollback_hooks_required,
            "kill_switch_required": kill_switch_required,
            "forbidden_material": list(_PHASE9_FORBIDDEN_MATERIAL),
            "fail_closed_errors": sorted(_ERROR_CODES),
        },
        "checks": {
            "phase8_report_exact_shape": True,
            "scope_default_off": True,
            "gateway_observation_only": True,
            "runtime_lifecycle_free": True,
            "validated_updates_only": True,
            "artifact_safe_summary_only": True,
            "rollback_and_kill_switch_present": True,
            "production_actions_separate": True,
            "side_effects_absent": True,
        },
        "artifact_policy": dict(artifact),
        "required_separate_approvals": list(_REQUIRED_SEPARATE_APPROVALS),
        "verification_matrix": list(_VERIFICATION_MATRIX),
        "runbook_outline": list(_RUNBOOK_OUTLINE),
        "side_effects": [],
    }
    _assert_report_shape(report)
    return report


def _error_result(error_code: str) -> dict[str, object]:
    report: dict[str, object] = {
        "type": CONTROLLED_SHADOW_PLAN_TYPE,
        "version": FLOWWEAVER_CONTROLLED_SHADOW_DESIGN_VERSION,
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


def _safe_string(value: object, *, error: str) -> str:
    if type(value) is not str:
        _raise(error)
    return value


def _bounded_int(value: object, *, minimum: int, maximum: int, error: str) -> int:
    if type(value) is not int or value < minimum or value > maximum:
        _raise(error)
    return value


def _ordered_surfaces(value: object, *, error: str) -> list[str]:
    surfaces = _plain_string_list(value, error=error)
    if not surfaces or any(surface not in _ALLOWED_SURFACES for surface in surfaces):
        _raise(error)
    if len(set(surfaces)) != len(surfaces):
        _raise(error)
    if [surface for surface in _ALLOWED_SURFACES if surface in surfaces] != surfaces:
        _raise(error)
    return surfaces


def _bounded_ordered_intersection(values: list[str], allowed: list[str]) -> list[str]:
    allowed_set = set(allowed)
    if any(value not in allowed_set for value in values):
        return []
    if [value for value in allowed if value in values] != values:
        return []
    return list(values)


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


def _safe_label(value: str) -> bool:
    return bool(value) and len(value) <= 128 and all(("a" <= char <= "z") or ("0" <= char <= "9") or char == "_" for char in value)


def _reject_unsafe_material(
    value: object,
    *,
    error: str,
    allow_descriptor_policy_names: bool = False,
    allow_policy_value_fields: bool = False,
    path: tuple[str, ...] = (),
) -> None:
    if allow_policy_value_fields and path and path[-1] == "allowed_fields":
        return
    if type(value) is str and allow_policy_value_fields and path:
        allowed_policy_values = _allowed_policy_values_for_path(path)
        if allowed_policy_values is not None and value in allowed_policy_values:
            return
    if type(value) is dict:
        for key, item in value.items():
            lowered = key.lower()
            allow_key_name = (
                (allow_descriptor_policy_names and not path and key in _DESCRIPTOR_POLICY_KEYS)
                or (allow_policy_value_fields and key in _POLICY_VALUE_FIELDS)
            )
            if not allow_key_name and any(lowered.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
                _raise(error)
            if not allow_key_name and (
                lowered in _UNSAFE_EXACT_KEYS or any(marker in lowered for marker in _UNSAFE_KEY_SUBSTRINGS)
            ):
                _raise(error)
            _reject_unsafe_material(
                item,
                error=error,
                allow_descriptor_policy_names=allow_descriptor_policy_names,
                allow_policy_value_fields=allow_policy_value_fields,
                path=path + (key,),
            )
        return
    if type(value) is list:
        for item in value:
            _reject_unsafe_material(
                item,
                error=error,
                allow_descriptor_policy_names=allow_descriptor_policy_names,
                allow_policy_value_fields=allow_policy_value_fields,
                path=path,
            )
        return
    if type(value) is str:
        lowered = value.lower()
        if any(lowered.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
            _raise(error)
        if any(marker in lowered for marker in _UNSAFE_VALUE_MARKERS):
            _raise(error)


def _safe_error_code(error_code: object) -> str:
    if type(error_code) is str and error_code in _ERROR_CODES:
        return error_code
    return "invalid_readiness_report"


def _allowed_policy_values_for_path(path: tuple[str, ...]) -> set[str] | None:
    if path == ("candidate_contract", "forbidden_material"):
        return set(_PHASE8_FORBIDDEN_MATERIAL)
    if path == ("forbidden_material",):
        return set(_PHASE9_FORBIDDEN_MATERIAL)
    if path == ("runbook_outline",):
        return set(_PHASE8_RUNBOOK_OUTLINE)
    return None


def _assert_report_shape(report: dict[str, object]) -> None:
    if not set(report) <= _REPORT_FIELDS:
        _raise("unsafe_material")


def _raise(code: str) -> None:
    raise ValueError(code)


__all__ = [
    "FLOWWEAVER_CONTROLLED_SHADOW_DESIGN_VERSION",
    "CONTROLLED_SHADOW_SCOPE_DESCRIPTOR_TYPE",
    "GATEWAY_OBSERVATION_BOUNDARY_TYPE",
    "RUNTIME_EXECUTION_BOUNDARY_TYPE",
    "CONTROLLED_SHADOW_ARTIFACT_POLICY_TYPE",
    "CONTROLLED_SHADOW_ROLLBACK_POLICY_TYPE",
    "CONTROLLED_SHADOW_PLAN_TYPE",
    "build_flowweaver_controlled_shadow_plan",
]
