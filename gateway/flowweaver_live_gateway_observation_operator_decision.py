"""Pure default-off operator decision gate for FlowWeaver Phase 16."""

from hashlib import sha256

FLOWWEAVER_LIVE_GATEWAY_OBSERVATION_OPERATOR_DECISION_VERSION = "flowweaver.live_gateway_observation_operator_decision.v0"
LIVE_GATEWAY_OBSERVATION_OPERATOR_DECISION_REPORT_TYPE = "flowweaver.live_gateway_observation_operator_decision_report.v0"

_PHASE = "phase16_operator_live_gateway_observation_decision_gate"
_SUCCESS_VERDICT = "ready_for_guarded_live_gateway_observation_enablement_implementation"
_BLOCKED_VERDICT = "blocked"
_DECISION_MODE = "default_off_operator_decision_gate"

_PHASE15_REPORT_TYPE = "flowweaver.live_gateway_observation_manual_review_report.v0"
_PHASE15_VERSION = "flowweaver.live_gateway_observation_manual_review.v0"
_PHASE15_VERDICT = "ready_for_live_gateway_observation_enablement_operator_decision"
_PHASE15_PHASE = "phase15_manual_live_gateway_observation_review_gate"
_PHASE15_MODE = "default_off_operator_review_gate"
_PHASE14_VERDICT = "ready_for_manual_live_gateway_observation_enablement_request_review"
_EXPECTED_PHASE15_CHAIN_IDS = {
    "review_id": "live_gateway_observation_manual_review_c81abaa6b341263e",
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
_PHASE15_REQUIRED_APPROVALS = [
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
_PHASE15_VERIFICATION_MATRIX = [
    "phase14_request_exact_shape",
    "phase14_evidence_not_live_enablement",
    "manual_review_policy_default_off",
    "approval_token_absent_reference_only",
    "operator_decision_not_granted",
    "sanitized_review_artifact_only",
    "production_actions_separate",
    "registry_config_write_absent",
    "runtime_lifecycle_absent",
    "gateway_runtime_wiring_absent",
    "side_effects_absent",
]
_VERIFICATION_MATRIX = [
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
_PHASE15_RUNBOOK_OUTLINE = [
    "phase15_is_manual_review_gate_only",
    "operator_decision_required_before_live_enablement",
    "approval_token_reference_only_no_secret_material",
    "keep_feature_flag_off_until_explicit_enablement_decision",
    "kill_switch_and_rollback_armed_before_any_enablement",
    "no_gateway_run_or_platform_adapter_wiring",
    "no_temporal_client_worker_" + "dock" + "er_or_service_lifecycle",
    "no_raw_payloads_or_secrets_in_reports_or_artifacts",
    "use_direct_pytest_for_gateway_regression",
]
_RUNBOOK_OUTLINE = [
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
_PHASE15_ARTIFACT_ALLOWED_FIELDS = [
    "review_id",
    "phase14_request_id",
    "phase13_design_id",
    "phase12_observation_id",
    "phase11_design_id",
    "phase10_run_id",
    "plan_transaction_id",
    "review_mode",
    "checks",
    "stable_error_codes",
    "approvals",
    "side_effects",
]
_ARTIFACT_ALLOWED_FIELDS = [
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
_ERROR_CODES = {
    "invalid_phase15_review",
    "invalid_operator_decision_policy",
    "operator_decision_requested",
    "live_observation_requested",
    "production_action_requested",
    "registry_or_config_write_requested",
    "runtime_lifecycle_requested",
    "side_effects_not_absent",
    "unsafe_material",
    "workflow_id_mismatch",
}
_REVIEW_FIELDS = {
    "type",
    "version",
    "ok",
    "verdict",
    "phase",
    "review_id",
    "phase14_request_id",
    "phase13_design_id",
    "phase12_observation_id",
    "phase11_design_id",
    "phase10_run_id",
    "plan_transaction_id",
    "review_mode",
    "manual_review",
    "checks",
    "artifact_policy",
    "rollback_policy",
    "required_separate_approvals",
    "verification_matrix",
    "runbook_outline",
    "side_effects",
}
_MANUAL_REVIEW_FIELDS = {
    "source_request_verdict",
    "feature_flag_ref",
    "operator_approval_ref",
    "reviewer_attestation_ref",
    "approval_token_required",
    "approval_token_supplied",
    "approval_token_material_allowed",
    "review_approved",
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
_DECISION_POLICY_FIELDS = {
    "type",
    "mode",
    "decision_scope",
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


def prepare_flowweaver_live_gateway_observation_operator_decision(*, phase15_review, operator_decision_policy):
    review_error = _validate_phase15_review(phase15_review)
    if review_error:
        return _blocked(review_error)

    policy_error = _validate_operator_decision_policy(operator_decision_policy)
    if policy_error:
        return _blocked(policy_error)

    manual_review = phase15_review["manual_review"]
    decision_id = "live_gateway_observation_operator_decision_" + _digest(
        phase15_review["review_id"],
        operator_decision_policy["operator_decision_ref"],
        phase15_review["plan_transaction_id"],
    )
    decision = {
        "source_review_verdict": _PHASE15_VERDICT,
        "feature_flag_ref": operator_decision_policy["feature_flag_ref"],
        "operator_approval_ref": operator_decision_policy["operator_approval_ref"],
        "operator_decision_ref": operator_decision_policy["operator_decision_ref"],
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
        "kill_switch_ref": operator_decision_policy["kill_switch_ref"],
        "kill_switch_armed": True,
        "rollback_mode": "feature_flag_off_first",
        "rollout_steps": list(manual_review["rollout_steps"]),
        "allowed_summary_inputs": list(manual_review["allowed_summary_inputs"]),
        "candidate_touchpoints": list(manual_review["candidate_touchpoints"]),
        "allowed_surfaces": list(manual_review["allowed_surfaces"]),
        "stable_error_codes": [],
        "safe_digest": _digest(decision_id, phase15_review["phase14_request_id"], _DECISION_MODE),
        "approvals": list(_REQUIRED_SEPARATE_APPROVALS),
        "side_effects": [],
    }
    return {
        "type": LIVE_GATEWAY_OBSERVATION_OPERATOR_DECISION_REPORT_TYPE,
        "version": FLOWWEAVER_LIVE_GATEWAY_OBSERVATION_OPERATOR_DECISION_VERSION,
        "ok": True,
        "verdict": _SUCCESS_VERDICT,
        "phase": _PHASE,
        "decision_id": decision_id,
        "phase15_review_id": phase15_review["review_id"],
        "phase14_request_id": phase15_review["phase14_request_id"],
        "phase13_design_id": phase15_review["phase13_design_id"],
        "phase12_observation_id": phase15_review["phase12_observation_id"],
        "phase11_design_id": phase15_review["phase11_design_id"],
        "phase10_run_id": phase15_review["phase10_run_id"],
        "plan_transaction_id": phase15_review["plan_transaction_id"],
        "decision_mode": _DECISION_MODE,
        "operator_decision": decision,
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
            "kill_switch_ref": operator_decision_policy["kill_switch_ref"],
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
        "type": LIVE_GATEWAY_OBSERVATION_OPERATOR_DECISION_REPORT_TYPE,
        "version": FLOWWEAVER_LIVE_GATEWAY_OBSERVATION_OPERATOR_DECISION_VERSION,
        "ok": False,
        "verdict": _BLOCKED_VERDICT,
        "phase": _PHASE,
        "error_code": code,
        "side_effects": [],
    }


def _validate_phase15_review(review):
    if type(review) is not dict:
        return "invalid_phase15_review"
    if set(review) != _REVIEW_FIELDS:
        return "invalid_phase15_review"
    if type(review.get("side_effects")) is list and review.get("side_effects") != []:
        return "side_effects_not_absent"
    if not _all_values_plain(review):
        return "invalid_phase15_review"
    if review.get("plan_transaction_id") != _EXPECTED_PHASE15_CHAIN_IDS["plan_transaction_id"]:
        return "workflow_id_mismatch"
    for key, expected in _EXPECTED_PHASE15_CHAIN_IDS.items():
        if review.get(key) != expected:
            return "invalid_phase15_review"
    expected_scalars = {
        "type": _PHASE15_REPORT_TYPE,
        "version": _PHASE15_VERSION,
        "ok": True,
        "verdict": _PHASE15_VERDICT,
        "phase": _PHASE15_PHASE,
        "review_mode": _PHASE15_MODE,
        "side_effects": [],
    }
    for key, expected in expected_scalars.items():
        if review.get(key) != expected:
            return "invalid_phase15_review"
    for key in (
        "review_id",
        "phase14_request_id",
        "phase13_design_id",
        "phase12_observation_id",
        "phase11_design_id",
        "phase10_run_id",
        "plan_transaction_id",
    ):
        if type(review.get(key)) is not str or _unsafe_string(review[key]):
            return "unsafe_material"
    id_checks = (
        (review["review_id"], "live_gateway_observation_manual_review_"),
        (review["phase14_request_id"], "live_gateway_observation_enablement_request_"),
        (review["phase13_design_id"], "live_gateway_observation_enablement_design_"),
        (review["phase12_observation_id"], "controlled_gateway_observation_hook_"),
        (review["phase11_design_id"], "controlled_gateway_observation_design_"),
    )
    for value, prefix in id_checks:
        if not _synthetic_id_matches(value, prefix):
            return "invalid_phase15_review"
    if not review["phase10_run_id"].startswith("controlled_shadow_run_"):
        return "invalid_phase15_review"
    manual_error = _validate_manual_review(review.get("manual_review"))
    if manual_error:
        return manual_error
    if review["review_id"] != _digest_id(
        "live_gateway_observation_manual_review_",
        review["phase14_request_id"],
        review["plan_transaction_id"],
        review["manual_review"]["reviewer_attestation_ref"],
    ):
        return "invalid_phase15_review"
    if review.get("required_separate_approvals") != _PHASE15_REQUIRED_APPROVALS:
        return "invalid_phase15_review"
    if review.get("verification_matrix") != _PHASE15_VERIFICATION_MATRIX:
        return "invalid_phase15_review"
    if review.get("runbook_outline") != _PHASE15_RUNBOOK_OUTLINE:
        return "invalid_phase15_review"
    if review.get("checks") != {name: True for name in _PHASE15_VERIFICATION_MATRIX}:
        return "invalid_phase15_review"
    if review["manual_review"]["safe_digest"] != _digest(
        review["review_id"],
        review["phase14_request_id"],
        review["phase13_design_id"],
        review["phase12_observation_id"],
        review["phase11_design_id"],
        review["phase10_run_id"],
        review["plan_transaction_id"],
        *review["manual_review"]["stable_error_codes"],
    ):
        return "invalid_phase15_review"
    if _validate_phase15_artifact_policy(review.get("artifact_policy")):
        return "invalid_phase15_review"
    if _validate_phase15_rollback_policy(review.get("rollback_policy")):
        return "invalid_phase15_review"
    return ""


def _validate_manual_review(manual_review):
    if type(manual_review) is not dict:
        return "invalid_phase15_review"
    if set(manual_review) != _MANUAL_REVIEW_FIELDS:
        return "invalid_phase15_review"
    expected = {
        "source_request_verdict": _PHASE14_VERDICT,
        "feature_flag_ref": "feature_flag_ref_phase13_live_gateway_observation_off",
        "operator_approval_ref": "approval_ref_phase13_enablement_design_contract",
        "reviewer_attestation_ref": "review_attestation_ref_phase15_manual_gate",
        "approval_token_required": True,
        "approval_token_supplied": False,
        "approval_token_material_allowed": False,
        "review_approved": False,
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
        "approvals": _PHASE15_REQUIRED_APPROVALS,
        "side_effects": [],
    }
    for key, value in expected.items():
        if manual_review.get(key) != value:
            return "invalid_phase15_review"
    digest = manual_review.get("safe_digest")
    if _unsafe_string(digest):
        return "unsafe_material"
    if not _safe_digest_matches(digest):
        return "invalid_phase15_review"
    return ""


def _validate_phase15_artifact_policy(policy):
    if type(policy) is not dict:
        return "invalid"
    if set(policy) != _ARTIFACT_POLICY_FIELDS:
        return "invalid"
    expected = {
        "artifact_mode": "safe_summary_only",
        "allowed_fields": _PHASE15_ARTIFACT_ALLOWED_FIELDS,
        "retention": "local_artifact_only",
        "log_policy": "sanitized_codes_only",
        "forbidden_material": _FORBIDDEN_MATERIAL,
        "side_effects": [],
    }
    return "" if all(policy.get(key) == value for key, value in expected.items()) else "invalid"


def _validate_phase15_rollback_policy(policy):
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


def _validate_operator_decision_policy(policy):
    if type(policy) is not dict:
        return "invalid_operator_decision_policy"
    if set(policy) != _DECISION_POLICY_FIELDS:
        return "invalid_operator_decision_policy"
    if type(policy.get("side_effects")) is list and policy.get("side_effects") != []:
        return "side_effects_not_absent"
    if not _all_values_plain(policy):
        return "invalid_operator_decision_policy"
    expected_scalars = {
        "type": "flowweaver.live_gateway_observation_operator_decision_policy.v0",
        "mode": _DECISION_MODE,
        "decision_scope": "operator_live_gateway_observation_enablement_decision",
        "source_review_verdict": _PHASE15_VERDICT,
        "feature_flag_ref": "feature_flag_ref_phase13_live_gateway_observation_off",
        "operator_approval_ref": "approval_ref_phase13_enablement_design_contract",
        "operator_decision_ref": "operator_decision_ref_phase16_default_off_gate",
        "approval_token_required": True,
        "kill_switch_ref": "kill_switch_ref_phase14_live_gateway_observation_default_off",
        "kill_switch_armed": True,
        "rollback_mode": "feature_flag_off_first",
        "side_effects": [],
    }
    for key, expected in expected_scalars.items():
        if policy.get(key) != expected:
            if key == "operator_decision_ref" and _unsafe_string(policy.get(key)):
                return "unsafe_material"
            return "invalid_operator_decision_policy"
    if policy.get("approval_token_material_allowed") is not False:
        return "unsafe_material"
    if policy.get("approval_token_supplied") is not False:
        return "operator_decision_requested"
    if policy.get("operator_decision_recorded") is not False:
        return "operator_decision_requested"
    if policy.get("operator_decision_approved") is not False:
        return "operator_decision_requested"
    for key in ("enablement_authorized", "requested_enabled", "live_observation_enabled"):
        if policy.get(key) is not False:
            return "live_observation_requested"
    for key in ("default_enabled",):
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
    return type(value) in {str, bool, int, float, type(None)}


def _unsafe_string(value):
    if type(value) is not str:
        return False
    lowered = value.lower()
    if lowered.startswith(("oc_", "ou_", "om_")):
        return True
    return any(fragment in lowered for fragment in _UNSAFE_VALUE_FRAGMENTS)


def _safe_digest_matches(value):
    return type(value) is str and len(value) == 16 and all(ch in "0123456789abcdef" for ch in value)


def _synthetic_id_matches(value, prefix):
    if type(value) is not str or not value.startswith(prefix):
        return False
    return _safe_digest_matches(value.removeprefix(prefix))


def _digest_id(prefix, *parts):
    return prefix + _digest(*parts)


def _digest(*parts):
    text = "|".join(str(part) for part in parts)
    return sha256(text.encode("utf-8")).hexdigest()[:16]
