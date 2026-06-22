"""Pure default-off live Gateway observation enablement request helper for FlowWeaver Phase 14."""

from __future__ import annotations

from hashlib import sha256

FLOWWEAVER_LIVE_GATEWAY_OBSERVATION_ENABLEMENT_VERSION = "flowweaver.live_gateway_observation_enablement.v0"
LIVE_GATEWAY_OBSERVATION_ENABLEMENT_REQUEST_TYPE = "flowweaver.live_gateway_observation_enablement_request.v0"

_PHASE = "phase14_live_gateway_observation_enablement_implementation"
_SUCCESS_VERDICT = "ready_for_manual_live_gateway_observation_enablement_request_review"
_BLOCKED_VERDICT = "blocked"
_ENABLEMENT_MODE = "default_off_manual_review_request"

_PHASE13_REPORT_TYPE = "flowweaver.live_gateway_observation_enablement_design_report.v0"
_PHASE13_VERSION = "flowweaver.live_gateway_observation_enablement_design.v0"
_PHASE13_VERDICT = "ready_for_live_gateway_observation_enablement_implementation"
_PHASE13_PHASE = "phase13_live_gateway_observation_enablement_design"
_PHASE13_MODE = "default_off_design_gate"
_PHASE12_VERDICT = "ready_for_live_gateway_observation_enablement_design"

_ALLOWED_TOUCHPOINTS = [
    "task_tracker_snapshot",
    "flowweaver_shadow_snapshot",
    "flowweaver_shadow_runtime_publication",
    "delivery_state_summary",
]
_ALLOWED_SURFACES = ["final_text", "rich_card", "progress_card", "media"]
_ALLOWED_SUMMARY_INPUTS = [
    "phase12_observation_hook_report",
    "sanitized_shadow_runtime_publication_summary",
    "sanitized_delivery_state_summary",
    "sanitized_progress_snapshot_summary",
]
_ROLLOUT_STEPS = [
    "design_review",
    "implementation_pr",
    "focused_contract_tests",
    "gateway_regression_tests",
    "fresh_context_review",
    "manual_enablement_request",
    "separate_gateway_restart_request_if_required",
    "post_enablement_observation_only_verification",
    "rollback_review",
]

_PHASE13_REQUIRED_APPROVALS = [
    "live_gateway_observation_enablement_implementation",
    "live_gateway_observation_enablement",
    "production_gateway_wiring",
    "production_config_write",
    "gateway_restart",
    "external_temporal_service",
    "real_send_edit_render_callback",
    "production_tool_registry",
    "remote_branch_or_worktree_cleanup",
]
_REQUIRED_SEPARATE_APPROVALS = [
    "manual_live_gateway_observation_enablement_request_review",
    "live_gateway_observation_enablement",
    "production_gateway_wiring",
    "production_config_write",
    "gateway_restart",
    "external_temporal_service",
    "real_send_edit_render_callback",
    "production_tool_registry",
    "remote_branch_or_worktree_cleanup",
]
_PHASE13_VERIFICATION_MATRIX = [
    "phase12_report_exact_shape",
    "phase12_evidence_not_live_enablement",
    "enablement_policy_default_off",
    "feature_flag_and_operator_approval_required",
    "kill_switch_and_rollback_required",
    "sanitized_observation_evidence_only",
    "production_actions_separate",
    "runtime_lifecycle_absent",
    "gateway_runtime_wiring_absent",
    "side_effects_absent",
]
_VERIFICATION_MATRIX = [
    "phase13_design_report_exact_shape",
    "phase13_evidence_not_live_enablement",
    "request_policy_default_off",
    "approval_token_reference_only",
    "feature_flag_kill_switch_and_rollback_armed",
    "sanitized_request_artifact_only",
    "production_actions_separate",
    "registry_config_write_absent",
    "runtime_lifecycle_absent",
    "gateway_runtime_wiring_absent",
    "side_effects_absent",
]
_PHASE13_RUNBOOK_OUTLINE = [
    "phase13_is_enablement_design_gate_only",
    "live_gateway_observation_enablement_implementation_requires_separate_approval",
    "live_gateway_observation_enablement_requires_separate_approval",
    "production_activation_requires_separate_design_and_approval",
    "keep_default_off_until_explicit_enablement",
    "rollback_and_kill_switch_required_before_any_enablement",
    "no_gateway_run_or_platform_adapter_wiring",
    "no_temporal_client_worker_" + "dock" + "er_or_service_lifecycle",
    "no_raw_payloads_or_secrets_in_reports_or_artifacts",
    "use_direct_pytest_for_integration_regression",
]
_RUNBOOK_OUTLINE = [
    "phase14_is_default_off_enablement_request_only",
    "manual_request_review_required_before_live_enablement",
    "approval_token_reference_only_no_secret_material",
    "keep_feature_flag_off_until_explicit_manual_enablement",
    "kill_switch_and_rollback_armed_before_any_enablement",
    "no_gateway_run_or_platform_adapter_wiring",
    "no_temporal_client_worker_" + "dock" + "er_or_service_lifecycle",
    "no_raw_payloads_or_secrets_in_reports_or_artifacts",
    "use_direct_pytest_for_gateway_regression",
]
_FORBIDDEN_MATERIAL = [
    "raw_prompt",
    "raw_tool_output",
    "raw_card_json",
    "raw_media_payload",
    "raw_platform_payload",
    "platform_message_identifiers",
    "credentials_or_connection_strings",
    "raw_exception_text",
    "raw_gateway_event",
    "raw_adapter_object",
    "raw_callback_payload",
    "raw_runtime_history",
]
_PHASE13_ARTIFACT_ALLOWED_FIELDS = [
    "design_id",
    "phase12_observation_id",
    "phase11_design_id",
    "phase10_run_id",
    "plan_transaction_id",
    "enablement_mode",
    "checks",
    "stable_error_codes",
    "approvals",
    "side_effects",
]
_ARTIFACT_ALLOWED_FIELDS = [
    "request_id",
    "phase13_design_id",
    "phase12_observation_id",
    "phase11_design_id",
    "phase10_run_id",
    "plan_transaction_id",
    "enablement_mode",
    "checks",
    "stable_error_codes",
    "approvals",
    "side_effects",
]
_PHASE13_ERROR_CODES = sorted(
    {
        "invalid_artifact_policy",
        "invalid_enablement_policy",
        "invalid_observation_evidence_policy",
        "invalid_phase12_report",
        "invalid_rollback_policy",
        "live_observation_requested",
        "production_action_requested",
        "registry_or_config_write_requested",
        "runtime_lifecycle_requested",
        "side_effects_not_absent",
        "unsafe_material",
        "workflow_id_mismatch",
    }
)
_ERROR_CODES = {
    "invalid_phase13_report",
    "invalid_request_policy",
    "live_observation_requested",
    "production_action_requested",
    "registry_or_config_write_requested",
    "runtime_lifecycle_requested",
    "side_effects_not_absent",
    "unsafe_material",
    "workflow_id_mismatch",
}
_REPORT_FIELDS = {
    "type",
    "version",
    "ok",
    "verdict",
    "phase",
    "design_id",
    "phase12_observation_id",
    "phase11_design_id",
    "phase10_run_id",
    "plan_transaction_id",
    "enablement_mode",
    "enablement_design",
    "checks",
    "artifact_policy",
    "rollback_policy",
    "required_separate_approvals",
    "verification_matrix",
    "runbook_outline",
    "side_effects",
}
_DESIGN_FIELDS = {
    "source_observation_verdict",
    "feature_flag_ref",
    "operator_approval_ref",
    "default_enabled",
    "candidate_touchpoints",
    "allowed_surfaces",
    "evidence_mode",
    "allowed_summary_inputs",
    "rollout_steps",
    "rollback_mode",
    "kill_switch_required",
    "stable_error_codes",
    "safe_digest",
    "approvals",
    "side_effects",
}
_PHASE13_ARTIFACT_POLICY_FIELDS = {
    "artifact_mode",
    "allowed_fields",
    "retention",
    "log_policy",
    "forbidden_material",
    "side_effects",
}
_PHASE13_ROLLBACK_POLICY_FIELDS = {
    "rollback_mode",
    "kill_switch_required",
    "config_revert_required",
    "gateway_restart_requires_separate_approval",
    "production_enablement_requires_separate_approval",
    "live_disable_verification_required",
    "side_effects",
}
_REQUEST_POLICY_FIELDS = {
    "type",
    "mode",
    "feature_flag_ref",
    "operator_approval_ref",
    "approval_token_required",
    "approval_token_supplied",
    "approval_token_material_allowed",
    "default_enabled",
    "requested_enabled",
    "live_observation_enabled",
    "config_write_allowed",
    "gateway_restart_allowed",
    "adapter_calls_allowed",
    "platform_payloads_allowed",
    "temporal_lifecycle_allowed",
    "registry_write_allowed",
    "kill_switch_ref",
    "kill_switch_armed",
    "rollback_mode",
    "side_effects",
}
_UNSAFE_EXACT_KEYS = set(_FORBIDDEN_MATERIAL)
_UNSAFE_KEY_SUBSTRINGS = (
    "raw_",
    "payload",
    "credential",
    "connection_string",
    "password",
    "secret",
    "access_" + "token",
    "bearer",
    "message_id",
    "chat_id",
    "user_id",
)
_UNSAFE_VALUE_MARKERS = (
    "raw_",
    "platform_payload_value",
    "callback_payload_value",
    "access_" + "token",
    "bearer ",
    "secretvalue",
    "postgres" + "://",
    "mysql" + "://",
    "mongodb" + "://",
    "redis" + "://",
)
_CONFIG_REGISTRY_MARKERS = ("config_write", "registry_write", "config.yaml", "tools." + "registry")
_RUNTIME_LIFECYCLE_MARKERS = (
    "temporal_worker",
    "temporal_lifecycle",
    "workflowenvironment",
    "worker_started",
    "start_" + "workflow",
)
_PRODUCTION_VALUE_MARKERS = (
    "production_ready",
    "production_enabled",
    "live_enabled",
    "gateway_enabled",
    "observation_enabled",
    "integration_enabled",
)
_PRIVATE_PREFIXES = ("oc_", "ou_", "om_", "message_")
_POLICY_DESCRIPTOR_KEYS = {
    "approval_token_required",
    "approval_token_supplied",
    "approval_token_material_allowed",
    "platform_payloads_allowed",
    "forbidden_material",
    "allowed_fields",
    "allowed_summary_inputs",
    "candidate_touchpoints",
    "allowed_surfaces",
    "runbook_outline",
    "verification_matrix",
    "required_separate_approvals",
    "approvals",
    "rollout_steps",
    "stable_error_codes",
    "log_policy",
}
_INVALID = object()


def prepare_flowweaver_live_gateway_observation_enablement_request(
    *,
    phase13_design_report: object,
    request_policy: object,
) -> dict[str, object]:
    """Build a pure Phase 14 manual-review request without enabling live observation."""

    try:
        design = _validate_phase13_report(phase13_design_report)
        policy = _validate_request_policy(request_policy, design=design)
    except ValueError as exc:
        return _error_result(_safe_error_code(exc.args[0] if exc.args else "invalid_phase13_report"))
    except Exception:
        return _error_result("invalid_phase13_report")

    stable_codes = sorted(set(design["stable_error_codes"]))
    request_id = _request_id(
        design_id=design["design_id"],
        plan_transaction_id=design["plan_transaction_id"],
        feature_flag_ref=policy["feature_flag_ref"],
    )
    enablement_request = {
        "source_design_verdict": _PHASE13_VERDICT,
        "feature_flag_ref": policy["feature_flag_ref"],
        "operator_approval_ref": policy["operator_approval_ref"],
        "approval_token_required": True,
        "approval_token_supplied": False,
        "approval_token_material_allowed": False,
        "default_enabled": False,
        "requested_enabled": False,
        "live_observation_active": False,
        "config_write_allowed": False,
        "gateway_restart_allowed": False,
        "adapter_calls_allowed": False,
        "platform_payloads_allowed": False,
        "temporal_lifecycle_allowed": False,
        "registry_write_allowed": False,
        "kill_switch_ref": policy["kill_switch_ref"],
        "kill_switch_armed": True,
        "rollback_mode": policy["rollback_mode"],
        "rollout_steps": list(design["rollout_steps"]),
        "allowed_summary_inputs": list(design["allowed_summary_inputs"]),
        "candidate_touchpoints": list(design["candidate_touchpoints"]),
        "allowed_surfaces": list(design["allowed_surfaces"]),
        "stable_error_codes": stable_codes,
        "safe_digest": _safe_digest(
            request_id,
            design["design_id"],
            design["phase12_observation_id"],
            design["phase11_design_id"],
            design["phase10_run_id"],
            design["plan_transaction_id"],
            *stable_codes,
        ),
        "approvals": list(_REQUIRED_SEPARATE_APPROVALS),
        "side_effects": [],
    }
    return {
        "type": LIVE_GATEWAY_OBSERVATION_ENABLEMENT_REQUEST_TYPE,
        "version": FLOWWEAVER_LIVE_GATEWAY_OBSERVATION_ENABLEMENT_VERSION,
        "ok": True,
        "verdict": _SUCCESS_VERDICT,
        "phase": _PHASE,
        "request_id": request_id,
        "phase13_design_id": design["design_id"],
        "phase12_observation_id": design["phase12_observation_id"],
        "phase11_design_id": design["phase11_design_id"],
        "phase10_run_id": design["phase10_run_id"],
        "plan_transaction_id": design["plan_transaction_id"],
        "enablement_mode": _ENABLEMENT_MODE,
        "enablement_request": enablement_request,
        "checks": {key: True for key in _VERIFICATION_MATRIX},
        "artifact_policy": {
            "artifact_mode": "safe_summary_only",
            "allowed_fields": list(_ARTIFACT_ALLOWED_FIELDS),
            "retention": "local_artifact_only",
            "log_policy": "sanitized_codes_only",
            "forbidden_material": list(_FORBIDDEN_MATERIAL),
            "side_effects": [],
        },
        "rollback_policy": {
            "rollback_mode": policy["rollback_mode"],
            "kill_switch_ref": policy["kill_switch_ref"],
            "kill_switch_armed": True,
            "config_revert_required": True,
            "gateway_restart_requires_separate_approval": True,
            "production_enablement_requires_separate_approval": True,
            "live_disable_verification_required": True,
            "side_effects": [],
        },
        "required_separate_approvals": list(_REQUIRED_SEPARATE_APPROVALS),
        "verification_matrix": list(_VERIFICATION_MATRIX),
        "runbook_outline": list(_RUNBOOK_OUTLINE),
        "side_effects": [],
    }


def _validate_phase13_report(value: object) -> dict[str, object]:
    report = _plain_dict(value, error="invalid_phase13_report")
    if report.get("side_effects") != []:
        _raise("side_effects_not_absent")
    if _safe_string_or_invalid(report.get("verdict")) in _PRODUCTION_VALUE_MARKERS:
        _raise("production_action_requested")
    extra_fields = set(report) - _REPORT_FIELDS
    if any(_matches_marker(field, _PRODUCTION_VALUE_MARKERS) for field in extra_fields):
        _raise("production_action_requested")
    _reject_unsafe_material(report, error="unsafe_material", allow_policy_names=True)
    if extra_fields:
        _raise("invalid_phase13_report")
    if set(report) != _REPORT_FIELDS:
        _raise("invalid_phase13_report")
    if not (
        report["type"] == _PHASE13_REPORT_TYPE
        and report["version"] == _PHASE13_VERSION
        and report["ok"] is True
        and report["verdict"] == _PHASE13_VERDICT
        and report["phase"] == _PHASE13_PHASE
        and report["enablement_mode"] == _PHASE13_MODE
    ):
        _raise("invalid_phase13_report")
    checks = _plain_dict(report["checks"], error="invalid_phase13_report")
    if set(checks) != set(_PHASE13_VERIFICATION_MATRIX) or any(
        checks[key] is not True for key in _PHASE13_VERIFICATION_MATRIX
    ):
        _raise("invalid_phase13_report")
    if _plain_string_list(report["required_separate_approvals"], error="invalid_phase13_report") != list(
        _PHASE13_REQUIRED_APPROVALS
    ):
        _raise("invalid_phase13_report")
    if _plain_string_list(report["verification_matrix"], error="invalid_phase13_report") != list(
        _PHASE13_VERIFICATION_MATRIX
    ):
        _raise("invalid_phase13_report")
    if _plain_string_list(report["runbook_outline"], error="invalid_phase13_report") != list(_PHASE13_RUNBOOK_OUTLINE):
        _raise("invalid_phase13_report")

    phase12_observation_id = _synthetic_id(
        report["phase12_observation_id"],
        prefixes=("controlled_gateway_observation_hook_",),
        error="invalid_phase13_report",
    )
    phase11_design_id = _synthetic_id(
        report["phase11_design_id"],
        prefixes=("controlled_gateway_observation_design_",),
        error="invalid_phase13_report",
    )
    phase10_run_id = _synthetic_id(
        report["phase10_run_id"],
        prefixes=("controlled_shadow_run_",),
        error="invalid_phase13_report",
    )
    plan_transaction_id = _runtime_transaction_id(report["plan_transaction_id"], error="invalid_phase13_report")
    design = _validate_enablement_design(
        report["enablement_design"],
        phase12_observation_id=phase12_observation_id,
        phase11_design_id=phase11_design_id,
        phase10_run_id=phase10_run_id,
        plan_transaction_id=plan_transaction_id,
    )
    design_id = _synthetic_id(
        report["design_id"],
        prefixes=("live_gateway_observation_enablement_design_",),
        error="invalid_phase13_report",
    )
    expected_design_id = _design_id(
        observation_id=phase12_observation_id,
        plan_transaction_id=plan_transaction_id,
        feature_flag_ref=design["feature_flag_ref"],
    )
    if design_id != expected_design_id:
        _raise("invalid_phase13_report")
    if design["safe_digest"] != _safe_digest(
        design_id,
        phase12_observation_id,
        phase11_design_id,
        phase10_run_id,
        plan_transaction_id,
        *design["stable_error_codes"],
    ):
        _raise("invalid_phase13_report")
    _validate_phase13_artifact_policy(report["artifact_policy"])
    _validate_phase13_rollback_policy(report["rollback_policy"])
    return {
        "design_id": design_id,
        "phase12_observation_id": phase12_observation_id,
        "phase11_design_id": phase11_design_id,
        "phase10_run_id": phase10_run_id,
        "plan_transaction_id": plan_transaction_id,
        "feature_flag_ref": design["feature_flag_ref"],
        "operator_approval_ref": design["operator_approval_ref"],
        "candidate_touchpoints": design["candidate_touchpoints"],
        "allowed_surfaces": design["allowed_surfaces"],
        "allowed_summary_inputs": design["allowed_summary_inputs"],
        "rollout_steps": design["rollout_steps"],
        "rollback_mode": design["rollback_mode"],
        "stable_error_codes": design["stable_error_codes"],
    }


def _validate_enablement_design(
    value: object,
    *,
    phase12_observation_id: str,
    phase11_design_id: str,
    phase10_run_id: str,
    plan_transaction_id: str,
) -> dict[str, object]:
    del phase12_observation_id, phase11_design_id, phase10_run_id, plan_transaction_id
    design = _plain_dict(value, error="invalid_phase13_report")
    if design.get("side_effects") != []:
        _raise("side_effects_not_absent")
    if set(design) != _DESIGN_FIELDS:
        _raise("invalid_phase13_report")
    if not (
        design["source_observation_verdict"] == _PHASE12_VERDICT
        and design["feature_flag_ref"] == "feature_flag_ref_phase13_live_gateway_observation_off"
        and design["operator_approval_ref"] == "approval_ref_phase13_enablement_design_contract"
        and design["default_enabled"] is False
        and design["evidence_mode"] == "sanitized_observation_summaries_only"
        and design["rollback_mode"] == "feature_flag_off_first"
        and design["kill_switch_required"] is True
    ):
        _raise("invalid_phase13_report")
    candidate_touchpoints = _plain_string_list(design["candidate_touchpoints"], error="invalid_phase13_report")
    if candidate_touchpoints != list(_ALLOWED_TOUCHPOINTS):
        _raise("invalid_phase13_report")
    allowed_surfaces = _plain_string_list(design["allowed_surfaces"], error="invalid_phase13_report")
    if allowed_surfaces != list(_ALLOWED_SURFACES):
        _raise("invalid_phase13_report")
    allowed_summary_inputs = _plain_string_list(design["allowed_summary_inputs"], error="invalid_phase13_report")
    if allowed_summary_inputs != list(_ALLOWED_SUMMARY_INPUTS):
        _raise("invalid_phase13_report")
    rollout_steps = _plain_string_list(design["rollout_steps"], error="invalid_phase13_report")
    if rollout_steps != list(_ROLLOUT_STEPS):
        _raise("invalid_phase13_report")
    stable_error_codes = _safe_label_list(design["stable_error_codes"], error="invalid_phase13_report")
    if stable_error_codes != []:
        if any(_matches_marker(code, _RUNTIME_LIFECYCLE_MARKERS) for code in stable_error_codes):
            _raise("runtime_lifecycle_requested")
        _raise("invalid_phase13_report")
    if not _is_safe_digest(design["safe_digest"]):
        _raise("invalid_phase13_report")
    if _plain_string_list(design["approvals"], error="invalid_phase13_report") != list(_PHASE13_REQUIRED_APPROVALS):
        _raise("invalid_phase13_report")
    return {
        "feature_flag_ref": design["feature_flag_ref"],
        "operator_approval_ref": design["operator_approval_ref"],
        "candidate_touchpoints": candidate_touchpoints,
        "allowed_surfaces": allowed_surfaces,
        "allowed_summary_inputs": allowed_summary_inputs,
        "rollout_steps": rollout_steps,
        "rollback_mode": design["rollback_mode"],
        "stable_error_codes": stable_error_codes,
        "safe_digest": design["safe_digest"],
    }


def _validate_phase13_artifact_policy(value: object) -> None:
    policy = _plain_dict(value, error="invalid_phase13_report")
    if policy.get("side_effects") != []:
        _raise("side_effects_not_absent")
    if set(policy) != _PHASE13_ARTIFACT_POLICY_FIELDS:
        _raise("invalid_phase13_report")
    artifact_mode = _plain_string(policy["artifact_mode"], error="invalid_phase13_report")
    allowed_fields = _plain_string_list(policy["allowed_fields"], error="invalid_phase13_report")
    retention = _plain_string(policy["retention"], error="invalid_phase13_report")
    log_policy = _plain_string(policy["log_policy"], error="invalid_phase13_report")
    forbidden_material = _plain_string_list(policy["forbidden_material"], error="invalid_phase13_report")
    if not (
        artifact_mode == "safe_summary_only"
        and allowed_fields == list(_PHASE13_ARTIFACT_ALLOWED_FIELDS)
        and retention == "local_artifact_only"
        and log_policy == "sanitized_codes_only"
        and forbidden_material == list(_FORBIDDEN_MATERIAL)
    ):
        _raise("invalid_phase13_report")


def _validate_phase13_rollback_policy(value: object) -> None:
    policy = _plain_dict(value, error="invalid_phase13_report")
    if policy.get("side_effects") != []:
        _raise("side_effects_not_absent")
    if set(policy) != _PHASE13_ROLLBACK_POLICY_FIELDS:
        _raise("invalid_phase13_report")
    if not (
        policy["rollback_mode"] == "feature_flag_off_first"
        and policy["kill_switch_required"] is True
        and policy["config_revert_required"] is True
        and policy["gateway_restart_requires_separate_approval"] is True
        and policy["production_enablement_requires_separate_approval"] is True
        and policy["live_disable_verification_required"] is True
    ):
        _raise("invalid_phase13_report")


def _validate_request_policy(value: object, *, design: dict[str, object]) -> dict[str, object]:
    policy = _plain_dict(value, error="invalid_request_policy")
    if policy.get("side_effects") != []:
        _raise("side_effects_not_absent")
    if policy.get("approval_token_supplied") is not False or policy.get("approval_token_material_allowed") is not False:
        _raise("unsafe_material")
    if policy.get("default_enabled") is not False or policy.get("requested_enabled") is not False:
        _raise("live_observation_requested")
    if policy.get("live_observation_enabled") is not False:
        _raise("live_observation_requested")
    if policy.get("config_write_allowed") is not False or policy.get("registry_write_allowed") is not False:
        _raise("registry_or_config_write_requested")
    if (
        policy.get("gateway_restart_allowed") is not False
        or policy.get("adapter_calls_allowed") is not False
        or policy.get("platform_payloads_allowed") is not False
    ):
        _raise("production_action_requested")
    if policy.get("temporal_lifecycle_allowed") is not False:
        _raise("runtime_lifecycle_requested")
    _reject_unsafe_material(policy, error="unsafe_material", allow_policy_names=True)
    if set(policy) != _REQUEST_POLICY_FIELDS:
        _raise("invalid_request_policy")
    if not (
        policy["type"] == "flowweaver.live_gateway_observation_enablement_request_policy.v0"
        and policy["mode"] == _ENABLEMENT_MODE
        and policy["feature_flag_ref"] == design["feature_flag_ref"]
        and policy["operator_approval_ref"] == design["operator_approval_ref"]
        and policy["approval_token_required"] is True
        and policy["kill_switch_ref"] == "kill_switch_ref_phase14_live_gateway_observation_default_off"
        and policy["kill_switch_armed"] is True
        and policy["rollback_mode"] == design["rollback_mode"]
    ):
        _raise("invalid_request_policy")
    return {
        "feature_flag_ref": policy["feature_flag_ref"],
        "operator_approval_ref": policy["operator_approval_ref"],
        "kill_switch_ref": policy["kill_switch_ref"],
        "rollback_mode": policy["rollback_mode"],
    }


def _reject_unsafe_material(value: object, *, error: str, allow_policy_names: bool = False) -> None:
    stack = [value]
    while stack:
        current = stack.pop()
        if type(current) is dict:
            for key, item in current.items():
                if type(key) is not str:
                    _raise(error)
                lowered_key = key.lower()
                if not (allow_policy_names and key in _POLICY_DESCRIPTOR_KEYS):
                    if lowered_key in _UNSAFE_EXACT_KEYS or any(marker in lowered_key for marker in _UNSAFE_KEY_SUBSTRINGS):
                        _raise(error)
                if allow_policy_names and key in {
                    "forbidden_material",
                    "runbook_outline",
                    "verification_matrix",
                    "required_separate_approvals",
                    "approvals",
                    "rollout_steps",
                    "allowed_fields",
                    "allowed_summary_inputs",
                    "candidate_touchpoints",
                    "allowed_surfaces",
                    "stable_error_codes",
                    "log_policy",
                }:
                    continue
                stack.append(item)
        elif type(current) is list:
            stack.extend(current)
        elif type(current) is str:
            lowered = current.lower()
            if current.startswith(_PRIVATE_PREFIXES):
                _raise(error)
            if any(marker in lowered for marker in _UNSAFE_VALUE_MARKERS):
                _raise(error)
            if any(marker in lowered for marker in _CONFIG_REGISTRY_MARKERS):
                _raise("registry_or_config_write_requested")
            if any(marker in lowered for marker in _RUNTIME_LIFECYCLE_MARKERS):
                _raise("runtime_lifecycle_requested")
            if any(marker in lowered for marker in _PRODUCTION_VALUE_MARKERS):
                _raise("production_action_requested")
        elif type(current) in {int, bool} or current is None:
            continue
        else:
            _raise(error)


def _plain_dict(value: object, *, error: str) -> dict[str, object]:
    if type(value) is not dict or not all(type(key) is str for key in value):
        _raise(error)
    return value


def _plain_string_list(value: object, *, error: str) -> list[str]:
    if type(value) is not list or not all(type(item) is str for item in value):
        _raise(error)
    return list(value)


def _plain_string(value: object, *, error: str) -> str:
    if type(value) is not str:
        _raise(error)
    return value


def _safe_label_list(value: object, *, error: str) -> list[str]:
    labels = _plain_string_list(value, error=error)
    for label in labels:
        if not label or len(label) > 96 or not all(ch.islower() or ch.isdigit() or ch in "._-" for ch in label):
            _raise(error)
    if len(set(labels)) != len(labels):
        _raise(error)
    return labels


def _safe_string_or_invalid(value: object) -> object:
    if type(value) is str:
        return value
    return _INVALID


def _synthetic_id(value: object, *, prefixes: tuple[str, ...], error: str) -> str:
    if type(value) is not str or not any(value.startswith(prefix) for prefix in prefixes):
        _raise(error)
    _validate_safe_identifier(value, error=error)
    return value


def _runtime_transaction_id(value: object, *, error: str) -> str:
    if type(value) is not str or not value.startswith("runtime_tx_"):
        _raise(error)
    _validate_safe_identifier(value, error=error)
    return value


def _validate_safe_identifier(value: str, *, error: str) -> None:
    if len(value) > 96 or not all(ch.islower() or ch.isdigit() or ch == "_" for ch in value):
        _raise(error)
    if any(marker in value for marker in ("raw_", "token", "secret", "password", "credential", "api_key", "bearer")):
        _raise(error)


def _is_safe_digest(value: object) -> bool:
    return type(value) is str and len(value) == 16 and all(ch in "0123456789abcdef" for ch in value)


def _design_id(*, observation_id: str, plan_transaction_id: str, feature_flag_ref: str) -> str:
    digest = _safe_digest(observation_id, plan_transaction_id, feature_flag_ref)
    return f"live_gateway_observation_enablement_design_{digest}"


def _request_id(*, design_id: str, plan_transaction_id: str, feature_flag_ref: str) -> str:
    digest = _safe_digest(design_id, plan_transaction_id, feature_flag_ref)
    return f"live_gateway_observation_enablement_request_{digest}"


def _safe_digest(*parts: str) -> str:
    payload = "|".join(parts).encode("utf-8")
    return sha256(payload).hexdigest()[:16]


def _matches_marker(value: object, markers: tuple[str, ...]) -> bool:
    if type(value) is not str:
        return False
    lowered = value.lower()
    return any(marker in lowered for marker in markers)


def _safe_error_code(value: object) -> str:
    if type(value) is str and value in _ERROR_CODES:
        return value
    return "invalid_phase13_report"


def _error_result(error_code: str) -> dict[str, object]:
    return {
        "type": LIVE_GATEWAY_OBSERVATION_ENABLEMENT_REQUEST_TYPE,
        "version": FLOWWEAVER_LIVE_GATEWAY_OBSERVATION_ENABLEMENT_VERSION,
        "ok": False,
        "verdict": _BLOCKED_VERDICT,
        "phase": _PHASE,
        "error_code": error_code,
        "side_effects": [],
    }


def _raise(error_code: str) -> None:
    raise ValueError(error_code)


__all__ = [
    "FLOWWEAVER_LIVE_GATEWAY_OBSERVATION_ENABLEMENT_VERSION",
    "LIVE_GATEWAY_OBSERVATION_ENABLEMENT_REQUEST_TYPE",
    "prepare_flowweaver_live_gateway_observation_enablement_request",
]
