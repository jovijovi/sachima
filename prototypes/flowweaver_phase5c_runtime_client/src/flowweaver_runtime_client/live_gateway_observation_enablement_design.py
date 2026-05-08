"""Pure default-off live Gateway observation enablement design gate for FlowWeaver Phase 13."""

from __future__ import annotations

from hashlib import sha256

FLOWWEAVER_LIVE_GATEWAY_OBSERVATION_ENABLEMENT_DESIGN_VERSION = (
    "flowweaver.live_gateway_observation_enablement_design.v0"
)
LIVE_GATEWAY_OBSERVATION_ENABLEMENT_DESIGN_REPORT_TYPE = (
    "flowweaver.live_gateway_observation_enablement_design_report.v0"
)

_PHASE = "phase13_live_gateway_observation_enablement_design"
_SUCCESS_VERDICT = "ready_for_live_gateway_observation_enablement_implementation"
_BLOCKED_VERDICT = "blocked"
_ENABLEMENT_MODE = "default_off_design_gate"

_PHASE12_REPORT_TYPE = "flowweaver.controlled_gateway_observation_hook_report.v0"
_PHASE12_VERSION = "flowweaver.controlled_gateway_observation_hook.v0"
_PHASE12_VERDICT = "ready_for_live_gateway_observation_enablement_design"
_PHASE12_PHASE = "phase12_controlled_gateway_observation_hook"
_PHASE12_MODE = "default_off_static_projection"
_PHASE11_VERDICT = "ready_for_controlled_gateway_observation_implementation"
_SHADOW_PUBLICATION_TYPE = "flowweaver.gateway.shadow_runtime_publication.v0"

_ALLOWED_TOUCHPOINTS = [
    "task_tracker_snapshot",
    "flowweaver_shadow_snapshot",
    "flowweaver_shadow_runtime_publication",
    "delivery_state_summary",
]
_ALLOWED_SURFACES = ["final_text", "rich_card", "progress_card", "media"]
_PHASE12_SUMMARY_INPUTS = [
    "phase11_design_report",
    "shadow_runtime_publication_summary",
    "delivery_state_summary",
    "progress_snapshot_summary",
]
_ALLOWED_SUMMARY_INPUTS = [
    "phase12_observation_hook_report",
    "sanitized_shadow_runtime_publication_summary",
    "sanitized_delivery_state_summary",
    "sanitized_progress_snapshot_summary",
]
_PHASE12_SHADOW_SURFACES = ["final_text", "rich_card"]
_PHASE12_DELIVERY_SURFACE_COUNTS = {"final_text": 1, "rich_card": 1, "progress_card": 0, "media": 0}
_PHASE12_DELIVERY_STATUS_COUNTS = {"sent": 1, "acknowledged": 1, "failed": 0}
_PHASE12_PROGRESS_EVENT_COUNTS = {"tool.started": 1, "tool.completed": 1}
_PHASE12_STABLE_ERROR_CODES: list[str] = []
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

_PHASE12_REQUIRED_APPROVALS = [
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
    "live_gateway_observation_enablement_implementation",
    *_PHASE12_REQUIRED_APPROVALS,
]
_PHASE12_VERIFICATION_MATRIX = [
    "phase11_report_exact_shape",
    "phase11_evidence_not_live_enablement",
    "gateway_hook_default_off",
    "sanitized_shadow_publication_summary_only",
    "delivery_state_summary_only",
    "progress_snapshot_summary_only",
    "artifact_safe_summary_only",
    "production_actions_separate",
    "runtime_lifecycle_absent",
    "side_effects_absent",
]
_VERIFICATION_MATRIX = [
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
_PHASE12_RUNBOOK_OUTLINE = [
    "phase12_is_default_off_observation_hook_only",
    "live_gateway_observation_enablement_requires_separate_approval",
    "production_activation_requires_separate_design_and_approval",
    "keep_default_off_until_explicit_enablement",
    "no_gateway_run_or_platform_adapter_wiring",
    "no_temporal_client_worker_" + "dock" + "er_or_service_lifecycle",
    "no_raw_payloads_or_secrets_in_reports_or_artifacts",
    "use_direct_pytest_for_integration_regression",
]
_RUNBOOK_OUTLINE = [
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
_PHASE12_ERROR_CODES = sorted(
    {
        "invalid_delivery_state_summary",
        "invalid_phase11_report",
        "invalid_progress_snapshot_summary",
        "invalid_shadow_runtime_publication_summary",
        "live_observation_requested",
        "production_action_requested",
        "runtime_lifecycle_requested",
        "side_effects_not_absent",
        "unsafe_material",
        "workflow_id_mismatch",
    }
)
_ERROR_CODES = {
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
_ARTIFACT_ALLOWED_FIELDS = [
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

_REPORT_FIELDS = {
    "type",
    "version",
    "ok",
    "verdict",
    "phase",
    "observation_id",
    "phase11_design_id",
    "phase10_run_id",
    "plan_transaction_id",
    "observation_mode",
    "controlled_gateway_observation",
    "checks",
    "artifact_policy",
    "required_separate_approvals",
    "verification_matrix",
    "runbook_outline",
    "side_effects",
}
_OBSERVATION_FIELDS = {
    "source_design_verdict",
    "candidate_touchpoints",
    "allowed_surfaces",
    "summary_inputs",
    "shadow_runtime_publication",
    "delivery_state",
    "progress_snapshot",
    "stable_error_codes",
    "safe_digest",
    "approvals",
    "side_effects",
}
_SHADOW_FIELDS = {
    "type",
    "verdict",
    "workflow_id",
    "transaction_id",
    "publication_count",
    "ack_update_count",
    "surfaces",
    "stable_error_codes",
    "side_effects",
}
_DELIVERY_FIELDS = {"surface_counts", "status_counts", "stable_error_codes", "side_effects"}
_PROGRESS_FIELDS = {"event_counts", "visible_event_count", "stable_error_codes", "side_effects"}
_PHASE12_ARTIFACT_FIELDS = {"artifact_mode", "log_policy", "forbidden_material", "side_effects"}
_ENABLEMENT_POLICY_FIELDS = {
    "type",
    "mode",
    "feature_flag_ref",
    "operator_approval_ref",
    "default_enabled",
    "config_write_allowed",
    "gateway_restart_allowed",
    "adapter_calls_allowed",
    "platform_payloads_allowed",
    "temporal_lifecycle_allowed",
    "registry_write_allowed",
    "kill_switch_required",
    "rollout_steps",
    "side_effects",
}
_EVIDENCE_POLICY_FIELDS = {
    "type",
    "evidence_mode",
    "source_report_type",
    "allowed_inputs",
    "allowed_touchpoints",
    "allowed_surfaces",
    "raw_material_allowed",
    "logs_allowed",
    "forbidden_material",
    "side_effects",
}
_ARTIFACT_POLICY_FIELDS = {
    "type",
    "artifact_mode",
    "allowed_fields",
    "retention",
    "log_policy",
    "forbidden_material",
    "side_effects",
}
_ROLLBACK_POLICY_FIELDS = {
    "type",
    "rollback_mode",
    "kill_switch_required",
    "config_revert_required",
    "gateway_restart_requires_separate_approval",
    "production_enablement_requires_separate_approval",
    "live_disable_verification_required",
    "side_effects",
}
_POLICY_DESCRIPTOR_KEYS = _ENABLEMENT_POLICY_FIELDS | _EVIDENCE_POLICY_FIELDS | _ARTIFACT_POLICY_FIELDS | _ROLLBACK_POLICY_FIELDS
_ALLOWED_EVENT_KEYS = {"tool.started", "tool.completed"}
_ALLOWED_SURFACE_KEYS = set(_ALLOWED_SURFACES)
_ALLOWED_DELIVERY_STATUS_KEYS = {"sent", "acknowledged", "failed"}
_PRIVATE_PREFIXES = ("om_", "oc_", "ou_", "chat_", "message_", "platform_", "feishu_", "lark_", "telegram_")
_PRODUCTION_VALUE_MARKERS = (
    "production_ready",
    "production_enabled",
    "gateway_enabled",
    "live_enabled",
    "observation_enabled",
    "integration_enabled",
    "adapter.send",
    "edit_message",
    "send_message",
    "render_card",
    "callback_handler",
    "gateway/platforms",
    "gateway/run.py",
    "run_" + "agent.py",
)
_CONFIG_REGISTRY_MARKERS = (
    "production_config",
    "config_path",
    "config_write",
    "registry_write",
    "tool_registry",
    "tools/registry",
)
_RUNTIME_LIFECYCLE_MARKERS = (
    "temporal_address",
    "namespace",
    "task_queue",
    "worker",
    "workflowenvironment",
    "workflow_environment",
    "client_factory",
    "connect_helper",
    "signal_" + "with_start",
    "payload_carrying_signal",
    "sub" + "process",
    "so" + "cket",
    "system" + "ctl",
    "service",
    "dae" + "mon",
    "dock" + "er",
)
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
_UNSAFE_EXACT_KEYS = {"token", "secret"}
_UNSAFE_VALUE_MARKERS = (
    "raw_prompt_value",
    "raw_tool_output_value",
    "raw_card_json_value",
    "raw_media_payload_value",
    "raw_platform_payload_value",
    "raw_gateway_event_value",
    "raw_adapter_object_value",
    "raw_callback_payload_value",
    "raw_runtime_history_value",
    "raw_gateway_event",
    "platform_payload_value",
    "callback_payload_value",
    "unsafe-" + "token",
    "sk" + "-",
    "bearer ",
    "password" + "=",
    "secret" + "=",
    "api" + "_key=",
    "access_" + "tok" + "en=",
    "client_" + "sec" + "ret=",
    "signature=",
    "://".join(("postgres", "")),
    "://".join(("mysql", "")),
    "://".join(("mongodb", "")),
    "://".join(("redis", "")),
)
_INVALID = object()


def design_flowweaver_live_gateway_observation_enablement(
    *,
    phase12_observation_hook_report: object,
    enablement_policy: object,
    observation_evidence_policy: object,
    artifact_policy: object,
    rollback_policy: object,
) -> dict[str, object]:
    """Build a pure Phase 13 enablement design report without enabling observation."""

    try:
        phase12 = _validate_phase12_report(phase12_observation_hook_report)
        enablement = _validate_enablement_policy(enablement_policy)
        evidence = _validate_observation_evidence_policy(observation_evidence_policy)
        artifact = _validate_artifact_policy(artifact_policy)
        rollback = _validate_rollback_policy(rollback_policy)
    except ValueError as exc:
        return _error_result(_safe_error_code(exc.args[0] if exc.args else "invalid_phase12_report"))
    except Exception:
        return _error_result("invalid_phase12_report")

    stable_codes = sorted(set(phase12["stable_error_codes"]))
    design_id = _design_id(
        observation_id=phase12["observation_id"],
        plan_transaction_id=phase12["plan_transaction_id"],
        feature_flag_ref=enablement["feature_flag_ref"],
    )
    enablement_design = {
        "source_observation_verdict": _PHASE12_VERDICT,
        "feature_flag_ref": enablement["feature_flag_ref"],
        "operator_approval_ref": enablement["operator_approval_ref"],
        "default_enabled": False,
        "candidate_touchpoints": list(evidence["allowed_touchpoints"]),
        "allowed_surfaces": list(evidence["allowed_surfaces"]),
        "evidence_mode": evidence["evidence_mode"],
        "allowed_summary_inputs": list(evidence["allowed_inputs"]),
        "rollout_steps": list(enablement["rollout_steps"]),
        "rollback_mode": rollback["rollback_mode"],
        "kill_switch_required": True,
        "stable_error_codes": stable_codes,
        "safe_digest": _safe_digest(
            design_id,
            phase12["observation_id"],
            phase12["phase11_design_id"],
            phase12["phase10_run_id"],
            phase12["plan_transaction_id"],
            *stable_codes,
        ),
        "approvals": list(_REQUIRED_SEPARATE_APPROVALS),
        "side_effects": [],
    }
    return {
        "type": LIVE_GATEWAY_OBSERVATION_ENABLEMENT_DESIGN_REPORT_TYPE,
        "version": FLOWWEAVER_LIVE_GATEWAY_OBSERVATION_ENABLEMENT_DESIGN_VERSION,
        "ok": True,
        "verdict": _SUCCESS_VERDICT,
        "phase": _PHASE,
        "design_id": design_id,
        "phase12_observation_id": phase12["observation_id"],
        "phase11_design_id": phase12["phase11_design_id"],
        "phase10_run_id": phase12["phase10_run_id"],
        "plan_transaction_id": phase12["plan_transaction_id"],
        "enablement_mode": _ENABLEMENT_MODE,
        "enablement_design": enablement_design,
        "checks": {key: True for key in _VERIFICATION_MATRIX},
        "artifact_policy": {
            "artifact_mode": artifact["artifact_mode"],
            "allowed_fields": list(artifact["allowed_fields"]),
            "retention": artifact["retention"],
            "log_policy": artifact["log_policy"],
            "forbidden_material": list(_FORBIDDEN_MATERIAL),
            "side_effects": [],
        },
        "rollback_policy": {
            "rollback_mode": rollback["rollback_mode"],
            "kill_switch_required": True,
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


def _validate_phase12_report(value: object) -> dict[str, object]:
    report = _plain_dict(value, error="invalid_phase12_report")
    if report.get("side_effects") != []:
        _raise("side_effects_not_absent")
    if _safe_string_or_invalid(report.get("verdict")) in {
        "production_ready",
        "production_enabled",
        "live_enabled",
        "gateway_enabled",
        "observation_enabled",
        "integration_enabled",
    }:
        _raise("production_action_requested")
    extra_fields = set(report) - _REPORT_FIELDS
    if any(_matches_marker(field, _PRODUCTION_VALUE_MARKERS) for field in extra_fields):
        _raise("production_action_requested")
    _reject_unsafe_material(report, error="unsafe_material", allow_policy_names=True)
    if extra_fields:
        _raise("invalid_phase12_report")
    if set(report) != _REPORT_FIELDS:
        _raise("invalid_phase12_report")
    if not (
        report["type"] == _PHASE12_REPORT_TYPE
        and report["version"] == _PHASE12_VERSION
        and report["ok"] is True
        and report["verdict"] == _PHASE12_VERDICT
        and report["phase"] == _PHASE12_PHASE
        and report["observation_mode"] == _PHASE12_MODE
    ):
        _raise("invalid_phase12_report")
    checks = _plain_dict(report["checks"], error="invalid_phase12_report")
    if set(checks) != set(_PHASE12_VERIFICATION_MATRIX) or any(checks[key] is not True for key in _PHASE12_VERIFICATION_MATRIX):
        _raise("invalid_phase12_report")
    if _plain_string_list(report["required_separate_approvals"], error="invalid_phase12_report") != list(
        _PHASE12_REQUIRED_APPROVALS
    ):
        _raise("invalid_phase12_report")
    if _plain_string_list(report["verification_matrix"], error="invalid_phase12_report") != list(
        _PHASE12_VERIFICATION_MATRIX
    ):
        _raise("invalid_phase12_report")
    if _plain_string_list(report["runbook_outline"], error="invalid_phase12_report") != list(_PHASE12_RUNBOOK_OUTLINE):
        _raise("invalid_phase12_report")
    phase11_design_id = _synthetic_id(
        report["phase11_design_id"],
        prefixes=("controlled_gateway_observation_design_",),
        error="invalid_phase12_report",
    )
    phase10_run_id = _synthetic_id(
        report["phase10_run_id"],
        prefixes=("controlled_shadow_run_",),
        error="invalid_phase12_report",
    )
    plan_transaction_id = _runtime_transaction_id(report["plan_transaction_id"], error="invalid_phase12_report")
    observation_id = _synthetic_id(
        report["observation_id"],
        prefixes=("controlled_gateway_observation_hook_",),
        error="invalid_phase12_report",
    )
    if observation_id != _phase12_observation_id(
        phase11_design_id=phase11_design_id,
        plan_transaction_id=plan_transaction_id,
    ):
        _raise("invalid_phase12_report")
    observation = _validate_phase12_observation(
        report["controlled_gateway_observation"],
        observation_id=observation_id,
        phase11_design_id=phase11_design_id,
        phase10_run_id=phase10_run_id,
        plan_transaction_id=plan_transaction_id,
    )
    _validate_phase12_artifact_policy(report["artifact_policy"])
    return {
        "observation_id": observation_id,
        "phase11_design_id": phase11_design_id,
        "phase10_run_id": phase10_run_id,
        "plan_transaction_id": plan_transaction_id,
        "candidate_touchpoints": observation["candidate_touchpoints"],
        "allowed_surfaces": observation["allowed_surfaces"],
        "stable_error_codes": observation["stable_error_codes"],
    }


def _validate_phase12_observation(
    value: object,
    *,
    observation_id: str,
    phase11_design_id: str,
    phase10_run_id: str,
    plan_transaction_id: str,
) -> dict[str, object]:
    observation = _plain_dict(value, error="invalid_phase12_report")
    if observation.get("side_effects") != []:
        _raise("side_effects_not_absent")
    if set(observation) != _OBSERVATION_FIELDS:
        _raise("invalid_phase12_report")
    if observation["source_design_verdict"] != _PHASE11_VERDICT:
        _raise("invalid_phase12_report")
    candidate_touchpoints = _plain_string_list(observation["candidate_touchpoints"], error="invalid_phase12_report")
    if candidate_touchpoints != list(_ALLOWED_TOUCHPOINTS):
        _raise("invalid_phase12_report")
    allowed_surfaces = _plain_string_list(observation["allowed_surfaces"], error="invalid_phase12_report")
    if allowed_surfaces != list(_ALLOWED_SURFACES):
        _raise("invalid_phase12_report")
    if _plain_string_list(observation["summary_inputs"], error="invalid_phase12_report") != list(_PHASE12_SUMMARY_INPUTS):
        _raise("invalid_phase12_report")
    shadow = _validate_shadow_projection(observation["shadow_runtime_publication"], plan_transaction_id=plan_transaction_id)
    delivery = _validate_delivery_projection(observation["delivery_state"])
    progress = _validate_progress_projection(observation["progress_snapshot"])
    stable_error_codes = _safe_label_list(observation["stable_error_codes"], error="invalid_phase12_report")
    expected_codes = sorted(
        set(shadow["stable_error_codes"] + delivery["stable_error_codes"] + progress["stable_error_codes"])
    )
    if stable_error_codes != expected_codes or stable_error_codes != list(_PHASE12_STABLE_ERROR_CODES):
        _raise("invalid_phase12_report")
    if observation["safe_digest"] != _safe_digest(
        observation_id,
        phase11_design_id,
        phase10_run_id,
        plan_transaction_id,
        *stable_error_codes,
    ):
        _raise("invalid_phase12_report")
    if _plain_string_list(observation["approvals"], error="invalid_phase12_report") != list(_PHASE12_REQUIRED_APPROVALS):
        _raise("invalid_phase12_report")
    return {
        "candidate_touchpoints": candidate_touchpoints,
        "allowed_surfaces": allowed_surfaces,
        "stable_error_codes": stable_error_codes,
    }


def _validate_shadow_projection(value: object, *, plan_transaction_id: str) -> dict[str, object]:
    shadow = _plain_dict(value, error="invalid_phase12_report")
    if shadow.get("side_effects") != []:
        _raise("side_effects_not_absent")
    if set(shadow) != _SHADOW_FIELDS:
        _raise("invalid_phase12_report")
    if shadow["type"] != _SHADOW_PUBLICATION_TYPE or shadow["verdict"] != "ready":
        _raise("invalid_phase12_report")
    workflow_id = _runtime_transaction_id(shadow["workflow_id"], error="invalid_phase12_report")
    transaction_id = _runtime_transaction_id(shadow["transaction_id"], error="invalid_phase12_report")
    if workflow_id != plan_transaction_id or transaction_id != plan_transaction_id:
        _raise("workflow_id_mismatch")
    publication_count = _bounded_int(shadow["publication_count"], minimum=0, maximum=20, error="invalid_phase12_report")
    ack_update_count = _bounded_int(shadow["ack_update_count"], minimum=0, maximum=20, error="invalid_phase12_report")
    surfaces = _plain_string_list(shadow["surfaces"], error="invalid_phase12_report")
    stable_error_codes = _safe_label_list(shadow["stable_error_codes"], error="invalid_phase12_report")
    if not (
        publication_count == 1
        and ack_update_count == 1
        and surfaces == list(_PHASE12_SHADOW_SURFACES)
        and stable_error_codes == list(_PHASE12_STABLE_ERROR_CODES)
    ):
        _raise("invalid_phase12_report")
    return {"stable_error_codes": stable_error_codes}


def _validate_delivery_projection(value: object) -> dict[str, object]:
    delivery = _plain_dict(value, error="invalid_phase12_report")
    if delivery.get("side_effects") != []:
        _raise("side_effects_not_absent")
    if set(delivery) != _DELIVERY_FIELDS:
        _raise("invalid_phase12_report")
    surface_counts = _safe_count_dict(delivery["surface_counts"], allowed_keys=_ALLOWED_SURFACE_KEYS, error="invalid_phase12_report")
    status_counts = _safe_count_dict(delivery["status_counts"], allowed_keys=_ALLOWED_DELIVERY_STATUS_KEYS, error="invalid_phase12_report")
    stable_error_codes = _safe_label_list(delivery["stable_error_codes"], error="invalid_phase12_report")
    if not (
        surface_counts == _PHASE12_DELIVERY_SURFACE_COUNTS
        and status_counts == _PHASE12_DELIVERY_STATUS_COUNTS
        and stable_error_codes == list(_PHASE12_STABLE_ERROR_CODES)
    ):
        _raise("invalid_phase12_report")
    return {"stable_error_codes": stable_error_codes}


def _validate_progress_projection(value: object) -> dict[str, object]:
    progress = _plain_dict(value, error="invalid_phase12_report")
    if progress.get("side_effects") != []:
        _raise("side_effects_not_absent")
    if set(progress) != _PROGRESS_FIELDS:
        _raise("invalid_phase12_report")
    event_counts = _safe_count_dict(progress["event_counts"], allowed_keys=_ALLOWED_EVENT_KEYS, error="invalid_phase12_report")
    visible_event_count = _bounded_int(progress["visible_event_count"], minimum=0, maximum=200, error="invalid_phase12_report")
    stable_error_codes = _safe_label_list(progress["stable_error_codes"], error="invalid_phase12_report")
    if not (
        event_counts == _PHASE12_PROGRESS_EVENT_COUNTS
        and visible_event_count == 2
        and stable_error_codes == list(_PHASE12_STABLE_ERROR_CODES)
    ):
        _raise("invalid_phase12_report")
    return {"stable_error_codes": stable_error_codes}


def _validate_phase12_artifact_policy(value: object) -> None:
    policy = _plain_dict(value, error="invalid_phase12_report")
    if set(policy) != _PHASE12_ARTIFACT_FIELDS or policy.get("side_effects") != []:
        _raise("invalid_phase12_report")
    if not (
        policy["artifact_mode"] == "safe_summary_only"
        and policy["log_policy"] == "sanitized_codes_only"
        and policy["forbidden_material"] == list(_FORBIDDEN_MATERIAL)
    ):
        _raise("invalid_phase12_report")


def _validate_enablement_policy(value: object) -> dict[str, object]:
    policy = _plain_dict(value, error="invalid_enablement_policy")
    if policy.get("side_effects") != []:
        _raise("side_effects_not_absent")
    if policy.get("default_enabled") is not False:
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
    if set(policy) != _ENABLEMENT_POLICY_FIELDS:
        _raise("invalid_enablement_policy")
    if not (
        policy["type"] == "flowweaver.live_gateway_observation_enablement_policy.v0"
        and policy["mode"] == "default_off_manual_enablement_design"
        and policy["feature_flag_ref"] == "feature_flag_ref_phase13_live_gateway_observation_off"
        and policy["operator_approval_ref"] == "approval_ref_phase13_enablement_design_contract"
        and policy["kill_switch_required"] is True
    ):
        _raise("invalid_enablement_policy")
    rollout_steps = _plain_string_list(policy["rollout_steps"], error="invalid_enablement_policy")
    if rollout_steps != list(_ROLLOUT_STEPS):
        _raise("invalid_enablement_policy")
    return {
        "feature_flag_ref": policy["feature_flag_ref"],
        "operator_approval_ref": policy["operator_approval_ref"],
        "rollout_steps": rollout_steps,
    }


def _validate_observation_evidence_policy(value: object) -> dict[str, object]:
    policy = _plain_dict(value, error="invalid_observation_evidence_policy")
    if policy.get("side_effects") != []:
        _raise("side_effects_not_absent")
    if policy.get("raw_material_allowed") is not False:
        _raise("unsafe_material")
    _reject_unsafe_material(policy, error="unsafe_material", allow_policy_names=True)
    if set(policy) != _EVIDENCE_POLICY_FIELDS:
        _raise("invalid_observation_evidence_policy")
    if not (
        policy["type"] == "flowweaver.live_gateway_observation_evidence_policy.v0"
        and policy["evidence_mode"] == "sanitized_observation_summaries_only"
        and policy["source_report_type"] == _PHASE12_REPORT_TYPE
        and policy["logs_allowed"] == "sanitized_codes_only"
        and policy["forbidden_material"] == list(_FORBIDDEN_MATERIAL)
    ):
        _raise("invalid_observation_evidence_policy")
    allowed_inputs = _plain_string_list(policy["allowed_inputs"], error="invalid_observation_evidence_policy")
    if allowed_inputs != list(_ALLOWED_SUMMARY_INPUTS):
        _raise("invalid_observation_evidence_policy")
    allowed_touchpoints = _ordered_subset(
        policy["allowed_touchpoints"],
        allowed=_ALLOWED_TOUCHPOINTS,
        error="invalid_observation_evidence_policy",
    )
    allowed_surfaces = _ordered_subset(policy["allowed_surfaces"], allowed=_ALLOWED_SURFACES, error="invalid_observation_evidence_policy")
    return {
        "evidence_mode": policy["evidence_mode"],
        "allowed_inputs": allowed_inputs,
        "allowed_touchpoints": allowed_touchpoints,
        "allowed_surfaces": allowed_surfaces,
    }


def _validate_artifact_policy(value: object) -> dict[str, object]:
    policy = _plain_dict(value, error="invalid_artifact_policy")
    if policy.get("side_effects") != []:
        _raise("side_effects_not_absent")
    if set(policy) != _ARTIFACT_POLICY_FIELDS:
        _raise("invalid_artifact_policy")
    if not (
        policy["type"] == "flowweaver.live_gateway_observation_artifact_policy.v0"
        and policy["artifact_mode"] == "safe_summary_only"
        and policy["allowed_fields"] == list(_ARTIFACT_ALLOWED_FIELDS)
        and policy["retention"] == "local_artifact_only"
        and policy["log_policy"] == "sanitized_codes_only"
        and policy["forbidden_material"] == list(_FORBIDDEN_MATERIAL)
    ):
        _raise("invalid_artifact_policy")
    return {
        "artifact_mode": policy["artifact_mode"],
        "allowed_fields": policy["allowed_fields"],
        "retention": policy["retention"],
        "log_policy": policy["log_policy"],
    }


def _validate_rollback_policy(value: object) -> dict[str, object]:
    policy = _plain_dict(value, error="invalid_rollback_policy")
    if policy.get("side_effects") != []:
        _raise("side_effects_not_absent")
    if set(policy) != _ROLLBACK_POLICY_FIELDS:
        _raise("invalid_rollback_policy")
    if not (
        policy["type"] == "flowweaver.live_gateway_observation_rollback_policy.v0"
        and policy["rollback_mode"] == "feature_flag_off_first"
        and policy["kill_switch_required"] is True
        and policy["config_revert_required"] is True
        and policy["gateway_restart_requires_separate_approval"] is True
        and policy["production_enablement_requires_separate_approval"] is True
        and policy["live_disable_verification_required"] is True
    ):
        _raise("invalid_rollback_policy")
    return {"rollback_mode": policy["rollback_mode"]}


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
                    "fail_closed_errors",
                    "required_separate_approvals",
                    "approvals",
                    "rollout_steps",
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


def _safe_label_list(value: object, *, error: str) -> list[str]:
    labels = _plain_string_list(value, error=error)
    for label in labels:
        if not label or len(label) > 96 or not all(ch.islower() or ch.isdigit() or ch in "._-" for ch in label):
            _raise(error)
    if len(set(labels)) != len(labels):
        _raise(error)
    return labels


def _ordered_subset(value: object, *, allowed: list[str], error: str) -> list[str]:
    labels = _safe_label_list(value, error=error)
    if not labels or any(label not in allowed for label in labels):
        _raise(error)
    if labels != [label for label in allowed if label in labels]:
        _raise(error)
    return labels


def _safe_count_dict(value: object, *, allowed_keys: set[str], error: str) -> dict[str, int]:
    counts = _plain_dict(value, error=error)
    if set(counts) != allowed_keys:
        _raise(error)
    result: dict[str, int] = {}
    for key in sorted(allowed_keys):
        count = counts[key]
        result[key] = _bounded_int(count, minimum=0, maximum=200, error=error)
    return {key: result[key] for key in counts}


def _bounded_int(value: object, *, minimum: int, maximum: int, error: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _raise(error)
    return value


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


def _phase12_observation_id(*, phase11_design_id: str, plan_transaction_id: str) -> str:
    digest = _safe_digest(phase11_design_id, plan_transaction_id)
    return f"controlled_gateway_observation_hook_{digest}"


def _design_id(*, observation_id: str, plan_transaction_id: str, feature_flag_ref: str) -> str:
    digest = _safe_digest(observation_id, plan_transaction_id, feature_flag_ref)
    return f"live_gateway_observation_enablement_design_{digest}"


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
    return "invalid_phase12_report"


def _error_result(error_code: str) -> dict[str, object]:
    return {
        "type": LIVE_GATEWAY_OBSERVATION_ENABLEMENT_DESIGN_REPORT_TYPE,
        "version": FLOWWEAVER_LIVE_GATEWAY_OBSERVATION_ENABLEMENT_DESIGN_VERSION,
        "ok": False,
        "verdict": _BLOCKED_VERDICT,
        "phase": _PHASE,
        "error_code": _safe_error_code(error_code),
        "side_effects": [],
    }


def _raise(error: str) -> None:
    raise ValueError(error)


__all__ = [
    "FLOWWEAVER_LIVE_GATEWAY_OBSERVATION_ENABLEMENT_DESIGN_VERSION",
    "LIVE_GATEWAY_OBSERVATION_ENABLEMENT_DESIGN_REPORT_TYPE",
    "design_flowweaver_live_gateway_observation_enablement",
]
