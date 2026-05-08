"""Pure guarded default-off live Gateway observation enablement contract for FlowWeaver Phase 17."""

from hashlib import sha256

FLOWWEAVER_LIVE_GATEWAY_OBSERVATION_GUARDED_ENABLEMENT_VERSION = (
    "flowweaver.live_gateway_observation_guarded_enablement.v0"
)
LIVE_GATEWAY_OBSERVATION_GUARDED_ENABLEMENT_REPORT_TYPE = (
    "flowweaver.live_gateway_observation_guarded_enablement_report.v0"
)

_PHASE = "phase17_guarded_live_gateway_observation_enablement"
_SUCCESS_VERDICT = "ready_for_guarded_live_gateway_observation_validation"
_BLOCKED_VERDICT = "blocked"
_ENABLEMENT_MODE = "guarded_enablement_implementation_default_off"

_PHASE16_REPORT_TYPE = "flowweaver.live_gateway_observation_operator_decision_report.v0"
_PHASE16_VERSION = "flowweaver.live_gateway_observation_operator_decision.v0"
_PHASE16_VERDICT = "ready_for_guarded_live_gateway_observation_enablement_implementation"
_PHASE16_PHASE = "phase16_operator_live_gateway_observation_decision_gate"
_PHASE16_MODE = "default_off_operator_decision_gate"
_EXPECTED_PHASE16_CHAIN_IDS = {
    "decision_id": "live_gateway_observation_operator_decision_12d34b5a6e0878cf",
    "phase15_review_id": "live_gateway_observation_manual_review_c81abaa6b341263e",
    "phase14_request_id": "live_gateway_observation_enablement_request_ba4d61c64d04d38f",
    "phase13_design_id": "live_gateway_observation_enablement_design_3d368ad45def1de4",
    "phase12_observation_id": "controlled_gateway_observation_hook_c08ee0d596ddc6ea",
    "phase11_design_id": "controlled_gateway_observation_design_8fb94e114020c84a",
    "phase10_run_id": "controlled_shadow_run_phase11_gateway_observation",
    "plan_transaction_id": "runtime_tx_phase11_gateway_observation",
}

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
_PHASE16_REQUIRED_APPROVALS = [
    "operator_live_gateway_observation_enablement_decision",
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
    "guarded_live_gateway_observation_enablement_validation",
    "live_gateway_observation_enablement",
    "production_gateway_wiring",
    "production_config_write",
    "gateway_restart",
    "external_temporal_service",
    "real_send_edit_render_callback",
    "production_tool_registry",
    "remote_branch_or_worktree_cleanup",
]
_PHASE16_VERIFICATION_MATRIX = [
    "phase15_review_exact_shape",
    "phase15_evidence_not_live_enablement",
    "operator_decision_policy_default_off",
    "approval_token_absent_reference_only",
    "operator_decision_not_granted",
    "enablement_not_authorized",
    "sanitized_operator_decision_artifact_only",
    "production_actions_separate",
    "registry_config_write_absent",
    "runtime_lifecycle_absent",
    "gateway_runtime_wiring_absent",
    "side_effects_absent",
]
_VERIFICATION_MATRIX = [
    "phase16_decision_exact_shape",
    "phase16_evidence_not_live_enablement",
    "guarded_enablement_policy_default_off",
    "approval_token_absent_reference_only",
    "guarded_enablement_not_authorized",
    "live_observation_not_enabled",
    "sanitized_guarded_enablement_artifact_only",
    "production_actions_separate",
    "registry_config_write_absent",
    "runtime_lifecycle_absent",
    "gateway_runtime_wiring_absent",
    "side_effects_absent",
]
_PHASE16_RUNBOOK_OUTLINE = [
    "phase16_is_operator_decision_gate_only",
    "operator_decision_requires_separate_live_enablement_approval",
    "approval_token_reference_only_no_secret_material",
    "keep_feature_flag_off_until_explicit_live_enablement",
    "kill_switch_and_rollback_armed_before_any_enablement",
    "no_gateway_run_or_platform_adapter_wiring",
    "no_temporal_client_worker_" + "dock" + "er_or_service_lifecycle",
    "no_raw_payloads_or_secrets_in_reports_or_artifacts",
    "use_direct_pytest_for_gateway_regression",
]
_RUNBOOK_OUTLINE = [
    "phase17_is_guarded_enablement_contract_only",
    "guarded_enablement_requires_separate_validation",
    "live_enablement_requires_separate_operator_approval",
    "approval_token_reference_only_no_secret_material",
    "keep_feature_flag_off_until_explicit_live_enablement",
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
_PHASE16_ARTIFACT_ALLOWED_FIELDS = [
    "decision_id",
    "phase15_review_id",
    "phase14_request_id",
    "phase13_design_id",
    "phase12_observation_id",
    "phase11_design_id",
    "phase10_run_id",
    "plan_transaction_id",
    "decision_mode",
    "checks",
    "stable_error_codes",
    "approvals",
    "side_effects",
]
_ARTIFACT_ALLOWED_FIELDS = [
    "enablement_id",
    "phase16_decision_id",
    "phase15_review_id",
    "phase14_request_id",
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
_ERROR_CODES = {
    "invalid_phase16_decision",
    "invalid_guarded_enablement_policy",
    "guarded_enablement_requested",
    "live_observation_requested",
    "production_action_requested",
    "registry_or_config_write_requested",
    "runtime_lifecycle_requested",
    "side_effects_not_absent",
    "unsafe_material",
    "workflow_id_mismatch",
}
_DECISION_FIELDS = {
    "type",
    "version",
    "ok",
    "verdict",
    "phase",
    "decision_id",
    "phase15_review_id",
    "phase14_request_id",
    "phase13_design_id",
    "phase12_observation_id",
    "phase11_design_id",
    "phase10_run_id",
    "plan_transaction_id",
    "decision_mode",
    "operator_decision",
    "checks",
    "artifact_policy",
    "rollback_policy",
    "required_separate_approvals",
    "verification_matrix",
    "runbook_outline",
    "side_effects",
}
_OPERATOR_DECISION_FIELDS = {
    "source_review_verdict",
    "feature_flag_ref",
    "operator_approval_ref",
    "operator_decision_ref",
    "approval_token_required",
    "approval_token_supplied",
    "approval_token_material_allowed",
    "operator_decision_recorded",
    "operator_decision_approved",
    "enablement_authorized",
    "default_enabled",
    "requested_enabled",
    "live_observation_active",
    "config_write_allowed",
    "gateway_restart_allowed",
    "adapter_calls_allowed",
    "platform_payloads_allowed",
    "temporal_lifecycle_allowed",
    "registry_write_allowed",
    "kill_switch_ref",
    "kill_switch_armed",
    "rollback_mode",
    "rollout_steps",
    "allowed_summary_inputs",
    "candidate_touchpoints",
    "allowed_surfaces",
    "stable_error_codes",
    "safe_digest",
    "approvals",
    "side_effects",
}
_ARTIFACT_POLICY_FIELDS = {
    "artifact_mode",
    "allowed_fields",
    "retention",
    "log_policy",
    "forbidden_material",
    "side_effects",
}
_ROLLBACK_POLICY_FIELDS = {
    "rollback_mode",
    "kill_switch_ref",
    "kill_switch_armed",
    "config_revert_required",
    "gateway_restart_requires_separate_approval",
    "production_enablement_requires_separate_approval",
    "live_disable_verification_required",
    "side_effects",
}
_POLICY_FIELDS = {
    "type",
    "mode",
    "implementation_scope",
    "source_decision_verdict",
    "feature_flag_ref",
    "operator_approval_ref",
    "operator_decision_ref",
    "guarded_enablement_ref",
    "implementation_review_ref",
    "approval_token_required",
    "approval_token_supplied",
    "approval_token_material_allowed",
    "guarded_enablement_authorized",
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
_UNSAFE_VALUE_FRAGMENTS = (
    "raw_prompt",
    "raw_tool_output",
    "raw_card_json",
    "raw_media_payload",
    "raw_platform_payload",
    "raw_gateway_event",
    "raw_adapter_object",
    "raw_callback_payload",
    "raw_runtime_history",
    "raw_exception",
    "access_token",
    "bearer ",
    "postgres://",
    "mysql://",
    "mongodb://",
    "callback_payload_value",
    "platform_payload_value",
    "raw_gateway_event_value",
    "raw_tool_output_value",
    "raw_prompt_value",
)


def prepare_flowweaver_live_gateway_observation_guarded_enablement(*, phase16_decision, guarded_enablement_policy):
    decision_error = _validate_phase16_decision(phase16_decision)
    if decision_error:
        return _blocked(decision_error)

    policy_error = _validate_guarded_enablement_policy(guarded_enablement_policy)
    if policy_error:
        return _blocked(policy_error)

    operator_decision = phase16_decision["operator_decision"]
    enablement_id = _digest_id(
        "live_gateway_observation_guarded_enablement_",
        phase16_decision["decision_id"],
        guarded_enablement_policy["guarded_enablement_ref"],
        phase16_decision["plan_transaction_id"],
    )
    guarded_enablement = {
        "source_decision_verdict": _PHASE16_VERDICT,
        "feature_flag_ref": guarded_enablement_policy["feature_flag_ref"],
        "operator_approval_ref": guarded_enablement_policy["operator_approval_ref"],
        "operator_decision_ref": guarded_enablement_policy["operator_decision_ref"],
        "guarded_enablement_ref": guarded_enablement_policy["guarded_enablement_ref"],
        "implementation_review_ref": guarded_enablement_policy["implementation_review_ref"],
        "approval_token_required": True,
        "approval_token_supplied": False,
        "approval_token_material_allowed": False,
        "guarded_enablement_authorized": False,
        "default_enabled": False,
        "requested_enabled": False,
        "live_observation_active": False,
        "shadow_observation_only": True,
        "config_write_allowed": False,
        "gateway_restart_allowed": False,
        "adapter_calls_allowed": False,
        "platform_payloads_allowed": False,
        "temporal_lifecycle_allowed": False,
        "registry_write_allowed": False,
        "kill_switch_ref": guarded_enablement_policy["kill_switch_ref"],
        "kill_switch_armed": True,
        "rollback_mode": "feature_flag_off_first",
        "rollout_steps": list(operator_decision["rollout_steps"]),
        "allowed_summary_inputs": list(operator_decision["allowed_summary_inputs"]),
        "candidate_touchpoints": list(operator_decision["candidate_touchpoints"]),
        "allowed_surfaces": list(operator_decision["allowed_surfaces"]),
        "stable_error_codes": [],
        "safe_digest": _digest(
            enablement_id,
            phase16_decision["decision_id"],
            phase16_decision["phase14_request_id"],
            _ENABLEMENT_MODE,
        ),
        "approvals": list(_REQUIRED_SEPARATE_APPROVALS),
        "side_effects": [],
    }
    return {
        "type": LIVE_GATEWAY_OBSERVATION_GUARDED_ENABLEMENT_REPORT_TYPE,
        "version": FLOWWEAVER_LIVE_GATEWAY_OBSERVATION_GUARDED_ENABLEMENT_VERSION,
        "ok": True,
        "verdict": _SUCCESS_VERDICT,
        "phase": _PHASE,
        "enablement_id": enablement_id,
        "phase16_decision_id": phase16_decision["decision_id"],
        "phase15_review_id": phase16_decision["phase15_review_id"],
        "phase14_request_id": phase16_decision["phase14_request_id"],
        "phase13_design_id": phase16_decision["phase13_design_id"],
        "phase12_observation_id": phase16_decision["phase12_observation_id"],
        "phase11_design_id": phase16_decision["phase11_design_id"],
        "phase10_run_id": phase16_decision["phase10_run_id"],
        "plan_transaction_id": phase16_decision["plan_transaction_id"],
        "enablement_mode": _ENABLEMENT_MODE,
        "guarded_enablement": guarded_enablement,
        "checks": {name: True for name in _VERIFICATION_MATRIX},
        "artifact_policy": {
            "artifact_mode": "safe_summary_only",
            "allowed_fields": list(_ARTIFACT_ALLOWED_FIELDS),
            "retention": "local_artifact_only",
            "log_policy": "sanitized_codes_only",
            "forbidden_material": list(_FORBIDDEN_MATERIAL),
            "side_effects": [],
        },
        "rollback_policy": {
            "rollback_mode": "feature_flag_off_first",
            "kill_switch_ref": guarded_enablement_policy["kill_switch_ref"],
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


def _blocked(error_code):
    code = error_code if error_code in _ERROR_CODES else "unsafe_material"
    return {
        "type": LIVE_GATEWAY_OBSERVATION_GUARDED_ENABLEMENT_REPORT_TYPE,
        "version": FLOWWEAVER_LIVE_GATEWAY_OBSERVATION_GUARDED_ENABLEMENT_VERSION,
        "ok": False,
        "verdict": _BLOCKED_VERDICT,
        "phase": _PHASE,
        "error_code": code,
        "side_effects": [],
    }


def _validate_phase16_decision(decision):
    if type(decision) is not dict:
        return "invalid_phase16_decision"
    if set(decision) != _DECISION_FIELDS:
        return "invalid_phase16_decision"
    if type(decision.get("side_effects")) is list and decision.get("side_effects") != []:
        return "side_effects_not_absent"
    if not _all_values_plain(decision):
        return "invalid_phase16_decision"
    if decision.get("plan_transaction_id") != _EXPECTED_PHASE16_CHAIN_IDS["plan_transaction_id"]:
        return "workflow_id_mismatch"
    for key, expected in _EXPECTED_PHASE16_CHAIN_IDS.items():
        if decision.get(key) != expected:
            return "invalid_phase16_decision"
    expected_scalars = {
        "type": _PHASE16_REPORT_TYPE,
        "version": _PHASE16_VERSION,
        "ok": True,
        "verdict": _PHASE16_VERDICT,
        "phase": _PHASE16_PHASE,
        "decision_mode": _PHASE16_MODE,
        "side_effects": [],
    }
    for key, expected in expected_scalars.items():
        if decision.get(key) != expected:
            return "invalid_phase16_decision"
    decision_error = _validate_operator_decision(decision.get("operator_decision"))
    if decision_error:
        return decision_error
    if decision["decision_id"] != _digest_id(
        "live_gateway_observation_operator_decision_",
        decision["phase15_review_id"],
        decision["operator_decision"]["operator_decision_ref"],
        decision["plan_transaction_id"],
    ):
        return "invalid_phase16_decision"
    if decision["operator_decision"]["safe_digest"] != _digest(
        decision["decision_id"],
        decision["phase14_request_id"],
        _PHASE16_MODE,
    ):
        return "invalid_phase16_decision"
    if decision.get("required_separate_approvals") != _PHASE16_REQUIRED_APPROVALS:
        return "invalid_phase16_decision"
    if decision.get("verification_matrix") != _PHASE16_VERIFICATION_MATRIX:
        return "invalid_phase16_decision"
    if decision.get("runbook_outline") != _PHASE16_RUNBOOK_OUTLINE:
        return "invalid_phase16_decision"
    if decision.get("checks") != {name: True for name in _PHASE16_VERIFICATION_MATRIX}:
        return "invalid_phase16_decision"
    if _validate_phase16_artifact_policy(decision.get("artifact_policy")):
        return "invalid_phase16_decision"
    if _validate_phase16_rollback_policy(decision.get("rollback_policy")):
        return "invalid_phase16_decision"
    return ""


def _validate_operator_decision(operator_decision):
    if type(operator_decision) is not dict:
        return "invalid_phase16_decision"
    if set(operator_decision) != _OPERATOR_DECISION_FIELDS:
        return "invalid_phase16_decision"
    expected = {
        "source_review_verdict": "ready_for_live_gateway_observation_enablement_operator_decision",
        "feature_flag_ref": "feature_flag_ref_phase13_live_gateway_observation_off",
        "operator_approval_ref": "approval_ref_phase13_enablement_design_contract",
        "operator_decision_ref": "operator_decision_ref_phase16_default_off_gate",
        "approval_token_required": True,
        "approval_token_supplied": False,
        "approval_token_material_allowed": False,
        "operator_decision_recorded": False,
        "operator_decision_approved": False,
        "enablement_authorized": False,
        "default_enabled": False,
        "requested_enabled": False,
        "live_observation_active": False,
        "config_write_allowed": False,
        "gateway_restart_allowed": False,
        "adapter_calls_allowed": False,
        "platform_payloads_allowed": False,
        "temporal_lifecycle_allowed": False,
        "registry_write_allowed": False,
        "kill_switch_ref": "kill_switch_ref_phase14_live_gateway_observation_default_off",
        "kill_switch_armed": True,
        "rollback_mode": "feature_flag_off_first",
        "rollout_steps": _ROLLOUT_STEPS,
        "allowed_summary_inputs": _ALLOWED_SUMMARY_INPUTS,
        "candidate_touchpoints": _ALLOWED_TOUCHPOINTS,
        "allowed_surfaces": _ALLOWED_SURFACES,
        "stable_error_codes": [],
        "approvals": _PHASE16_REQUIRED_APPROVALS,
        "side_effects": [],
    }
    for key, value in expected.items():
        if operator_decision.get(key) != value:
            return "invalid_phase16_decision"
    digest = operator_decision.get("safe_digest")
    if _unsafe_string(digest):
        return "unsafe_material"
    if not _safe_digest_matches(digest):
        return "invalid_phase16_decision"
    return ""


def _validate_phase16_artifact_policy(policy):
    if type(policy) is not dict:
        return "invalid"
    if set(policy) != _ARTIFACT_POLICY_FIELDS:
        return "invalid"
    expected = {
        "artifact_mode": "safe_summary_only",
        "allowed_fields": _PHASE16_ARTIFACT_ALLOWED_FIELDS,
        "retention": "local_artifact_only",
        "log_policy": "sanitized_codes_only",
        "forbidden_material": _FORBIDDEN_MATERIAL,
        "side_effects": [],
    }
    return "" if all(policy.get(key) == value for key, value in expected.items()) else "invalid"


def _validate_phase16_rollback_policy(policy):
    if type(policy) is not dict:
        return "invalid"
    if set(policy) != _ROLLBACK_POLICY_FIELDS:
        return "invalid"
    expected = {
        "rollback_mode": "feature_flag_off_first",
        "kill_switch_ref": "kill_switch_ref_phase14_live_gateway_observation_default_off",
        "kill_switch_armed": True,
        "config_revert_required": True,
        "gateway_restart_requires_separate_approval": True,
        "production_enablement_requires_separate_approval": True,
        "live_disable_verification_required": True,
        "side_effects": [],
    }
    return "" if all(policy.get(key) == value for key, value in expected.items()) else "invalid"


def _validate_guarded_enablement_policy(policy):
    if type(policy) is not dict:
        return "invalid_guarded_enablement_policy"
    if set(policy) != _POLICY_FIELDS:
        return "invalid_guarded_enablement_policy"
    if type(policy.get("side_effects")) is list and policy.get("side_effects") != []:
        return "side_effects_not_absent"
    if not _all_values_plain(policy):
        return "invalid_guarded_enablement_policy"
    expected_scalars = {
        "type": "flowweaver.live_gateway_observation_guarded_enablement_policy.v0",
        "mode": _ENABLEMENT_MODE,
        "implementation_scope": "guarded_live_gateway_observation_enablement_contract",
        "source_decision_verdict": _PHASE16_VERDICT,
        "feature_flag_ref": "feature_flag_ref_phase13_live_gateway_observation_off",
        "operator_approval_ref": "approval_ref_phase13_enablement_design_contract",
        "operator_decision_ref": "operator_decision_ref_phase16_default_off_gate",
        "guarded_enablement_ref": "guarded_enablement_ref_phase17_default_off_contract",
        "implementation_review_ref": "implementation_review_ref_phase17_guarded_contract",
        "approval_token_required": True,
        "kill_switch_ref": "kill_switch_ref_phase14_live_gateway_observation_default_off",
        "kill_switch_armed": True,
        "rollback_mode": "feature_flag_off_first",
        "side_effects": [],
    }
    for key, expected in expected_scalars.items():
        if policy.get(key) != expected:
            if key in {"guarded_enablement_ref", "implementation_review_ref"} and _unsafe_string(policy.get(key)):
                return "unsafe_material"
            return "invalid_guarded_enablement_policy"
    if policy.get("approval_token_material_allowed") is not False:
        return "unsafe_material"
    for key in ("approval_token_supplied", "guarded_enablement_authorized"):
        if policy.get(key) is not False:
            return "guarded_enablement_requested"
    for key in ("default_enabled", "requested_enabled", "live_observation_enabled"):
        if policy.get(key) is not False:
            return "live_observation_requested"
    for key in ("config_write_allowed", "gateway_restart_allowed", "adapter_calls_allowed", "platform_payloads_allowed"):
        if policy.get(key) is not False:
            return "production_action_requested"
    if policy.get("registry_write_allowed") is not False:
        return "registry_or_config_write_requested"
    if policy.get("temporal_lifecycle_allowed") is not False:
        return "runtime_lifecycle_requested"
    return ""


def _all_values_plain(value):
    if type(value) is dict:
        return all(type(key) is str and _all_values_plain(item) for key, item in value.items())
    if type(value) is list:
        return all(_all_values_plain(item) for item in value)
    return type(value) in {str, bool, type(None)}


def _unsafe_string(value):
    if type(value) is not str:
        return False
    lowered = value.lower()
    if lowered.startswith(("oc_", "ou_", "om_")):
        return True
    return any(fragment in lowered for fragment in _UNSAFE_VALUE_FRAGMENTS)


def _safe_digest_matches(value):
    return type(value) is str and len(value) == 16 and all(ch in "0123456789abcdef" for ch in value)


def _digest_id(prefix, *parts):
    return prefix + _digest(*parts)


def _digest(*parts):
    text = "|".join(str(part) for part in parts)
    return sha256(text.encode("utf-8")).hexdigest()[:16]
