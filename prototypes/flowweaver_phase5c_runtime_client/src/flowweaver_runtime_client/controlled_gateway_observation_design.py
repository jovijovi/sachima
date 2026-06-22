"""Prototype-only controlled Gateway observation design contract for FlowWeaver Phase 11."""

from __future__ import annotations

from hashlib import sha256

FLOWWEAVER_CONTROLLED_GATEWAY_OBSERVATION_DESIGN_VERSION = "flowweaver.controlled_gateway_observation_design.v0"
CONTROLLED_GATEWAY_OBSERVATION_BOUNDARY_TYPE = "flowweaver.controlled_gateway_observation_boundary.v0"
CONTROLLED_GATEWAY_INTEGRATION_POLICY_TYPE = "flowweaver.controlled_gateway_integration_policy.v0"
CONTROLLED_GATEWAY_RUNTIME_HANDOFF_BOUNDARY_TYPE = "flowweaver.controlled_gateway_runtime_handoff_boundary.v0"
CONTROLLED_GATEWAY_ARTIFACT_POLICY_TYPE = "flowweaver.controlled_gateway_artifact_policy.v0"
CONTROLLED_GATEWAY_ROLLBACK_POLICY_TYPE = "flowweaver.controlled_gateway_rollback_policy.v0"
CONTROLLED_GATEWAY_OBSERVATION_DESIGN_REPORT_TYPE = "flowweaver.controlled_gateway_observation_design_report.v0"

_PHASE = "phase11_controlled_gateway_observation_integration_design"
_SUCCESS_VERDICT = "ready_for_controlled_gateway_observation_implementation"
_BLOCKED_VERDICT = "blocked"
_PHASE10_REPORT_TYPE = "flowweaver.controlled_shadow_prototype_loop_report.v0"
_PHASE10_VERSION = "flowweaver.controlled_shadow_prototype_loop.v0"
_PHASE10_PHASE = "phase10_controlled_shadow_prototype_loop"
_PHASE10_VERDICT = "controlled_shadow_prototype_loop_verified"
_PHASE10_ARTIFACT_TYPE = "flowweaver.controlled_shadow_prototype_artifact.v0"

_ALLOWED_SURFACES = ("final_text", "rich_card", "progress_card", "media")
_ALLOWED_TOUCHPOINTS = (
    "task_tracker_snapshot",
    "flowweaver_shadow_snapshot",
    "flowweaver_shadow_runtime_publication",
    "delivery_state_summary",
)
_ALLOWED_EXISTING_MODULES = (
    "gateway/flowweaver_shadow.py",
    "gateway/flowweaver_shadow_publisher.py",
    "gateway/flowweaver_contract.py",
    "gateway/delivery_state.py",
    "gateway/progress/events.py",
)
_ALLOWED_FUTURE_FILES = (
    "gateway/flowweaver_controlled_gateway_observation.py",
    "tests/gateway/test_flowweaver_controlled_gateway_observation.py",
)
_ALLOWED_OBSERVATION_INPUTS = (
    "phase10_report",
    "shadow_runtime_publication_summary",
    "delivery_state_summary",
    "progress_snapshot_summary",
)
_ALLOWED_OBSERVATION_OUTPUTS = ("safe_summary", "fixture_projection", "readiness_checks", "stable_error_codes")
_ALLOWED_RUNTIME_OPERATIONS = ("start_transaction", "query_transaction", "reconcile_delivery_ack")
_ALLOWED_ROLLOUT_STEPS = (
    "design_review",
    "implementation_pr",
    "focused_tests",
    "integration_regression",
    "fresh_context_review",
    "manual_enablement_request",
    "separate_gateway_restart_request",
    "post_enablement_observation_only_verification",
    "rollback_review",
)
_ALLOWED_ARTIFACT_FIELDS = (
    "design_id",
    "phase10_run_id",
    "plan_transaction_id",
    "candidate_touchpoints",
    "allowed_surfaces",
    "checks",
    "stable_error_codes",
    "approvals",
    "side_effects",
)

_PHASE10_SUCCESS_FIELDS = {
    "type",
    "version",
    "ok",
    "verdict",
    "phase",
    "run_id",
    "plan_transaction_id",
    "publication_count",
    "loop_results",
    "artifact",
    "checks",
    "required_separate_approvals",
    "verification_matrix",
    "runbook_outline",
    "side_effects",
}
_PHASE10_LOOP_RESULT_FIELDS = {
    "workflow_id",
    "transaction_id",
    "start_status",
    "ack_count",
    "surfaces",
    "status_counts",
    "delivery_counts",
    "stable_error_codes",
    "safe_digest",
    "side_effects",
}
_PHASE10_ARTIFACT_FIELDS = {
    "type",
    "artifact_mode",
    "run_id",
    "plan_transaction_id",
    "publication_count",
    "operation_counts",
    "delivery_counts",
    "statuses",
    "digests",
    "stable_error_codes",
    "approvals",
    "side_effects",
}
_GATEWAY_OBSERVATION_BOUNDARY_FIELDS = {
    "type",
    "mode",
    "source_kind",
    "candidate_touchpoints",
    "allowed_existing_modules",
    "allowed_future_files",
    "allowed_surfaces",
    "observation_inputs",
    "observation_outputs",
    "adapter_imports_allowed",
    "platform_payloads_allowed",
    "message_identifiers_allowed",
    "raw_content_allowed",
    "send_edit_render_callback_allowed",
    "logs_allowed",
    "side_effects",
}
_INTEGRATION_POLICY_FIELDS = {
    "type",
    "mode",
    "feature_flag_ref",
    "default_enabled",
    "implementation_stage",
    "allowed_config_scope",
    "config_write_allowed",
    "gateway_restart_allowed",
    "runtime_effects_allowed",
    "temporal_lifecycle_allowed",
    "payload_carrying_signals_allowed",
    "registry_write_allowed",
    "operator_approval_ref",
    "rollout_steps",
    "rollback_required",
    "kill_switch_required",
    "side_effects",
}
_RUNTIME_HANDOFF_FIELDS = {
    "type",
    "mode",
    "control_surface_lifecycle",
    "runtime_operations",
    "runtime_client_construction_allowed",
    "temporal_client_allowed",
    "temporal_worker_allowed",
    "workflow_environment_allowed",
    "payload_carrying_signals_allowed",
    "fixture_projection",
    "ack_source",
    "ack_target_validation",
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
    "rollback_hooks_required",
    "config_revert_required",
    "gateway_restart_requires_separate_approval",
    "production_enablement_requires_separate_approval",
    "side_effects",
}
_REPORT_FIELDS = {
    "type",
    "version",
    "ok",
    "verdict",
    "phase",
    "design_id",
    "phase10_run_id",
    "plan_transaction_id",
    "controlled_gateway_observation_plan",
    "checks",
    "artifact_policy",
    "rollback_policy",
    "required_separate_approvals",
    "verification_matrix",
    "runbook_outline",
    "side_effects",
    "error_code",
}
_ERROR_CODES = {
    "artifact_policy_violation",
    "invalid_artifact_policy",
    "invalid_gateway_observation_boundary",
    "invalid_integration_policy",
    "invalid_phase10_report",
    "invalid_rollback_policy",
    "invalid_runtime_handoff_boundary",
    "production_action_requested",
    "registry_or_config_write_requested",
    "runtime_lifecycle_requested",
    "side_effects_not_absent",
    "unsafe_material",
    "workflow_id_mismatch",
}
_PHASE10_REQUIRED_APPROVALS = [
    "production_gateway_wiring",
    "production_config_write",
    "gateway_restart",
    "external_temporal_service",
    "real_send_edit_render_callback",
    "production_tool_registry",
    "remote_branch_or_worktree_cleanup",
]
_REQUIRED_SEPARATE_APPROVALS = [
    "controlled_gateway_observation_implementation",
    "live_gateway_observation_enablement",
    *_PHASE10_REQUIRED_APPROVALS,
]
_PHASE10_VERIFICATION_MATRIX = [
    "phase9_plan_exact_shape",
    "plan_default_off",
    "run_policy_default_off",
    "publication_fixtures_bounded",
    "publication_fixtures_safe",
    "caller_supplied_control_surface_only",
    "gateway_effects_absent",
    "runtime_lifecycle_absent",
    "validated_updates_only",
    "phase7_loop_results_safe",
    "artifact_safe_summary_only",
    "production_actions_separate",
    "side_effects_absent",
]
_PHASE10_RUNBOOK_OUTLINE = [
    "phase10_proves_bounded_prototype_loop_only",
    "production_activation_requires_separate_design_and_approval",
    "keep_default_off_until_explicit_enablement",
    "caller_supplied_control_surface_only",
    "no_gateway_adapter_or_platform_payloads",
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
_VERIFICATION_MATRIX = [
    "phase10_report_exact_shape",
    "phase10_evidence_not_live_enablement",
    "gateway_observation_boundary_static",
    "integration_policy_default_off",
    "runtime_handoff_lifecycle_free",
    "allowed_touchpoints_bounded",
    "artifact_safe_summary_only",
    "rollback_and_kill_switch_present",
    "production_actions_separate",
    "side_effects_absent",
]
_RUNBOOK_OUTLINE = [
    "phase11_is_design_gate_only",
    "controlled_gateway_observation_implementation_requires_separate_approval",
    "live_gateway_observation_enablement_requires_separate_approval",
    "production_activation_requires_separate_design_and_approval",
    "keep_default_off_until_explicit_enablement",
    "rollback_and_kill_switch_required_before_any_wiring",
    "no_raw_payloads_or_secrets_in_reports_or_artifacts",
    "use_direct_pytest_for_integration_regression",
]

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
    "run_agent.py",
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
    "postgres://",
    "mysql://",
    "mongodb://",
    "redis://",
)
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
_DESCRIPTOR_KEYS = (
    _GATEWAY_OBSERVATION_BOUNDARY_FIELDS
    | _INTEGRATION_POLICY_FIELDS
    | _RUNTIME_HANDOFF_FIELDS
    | _ARTIFACT_POLICY_FIELDS
    | _ROLLBACK_POLICY_FIELDS
)
_POLICY_VALUE_FIELDS = {"allowed_fields", "forbidden_material", "runbook_outline"}
_INVALID = object()


def design_flowweaver_controlled_gateway_observation(
    *,
    phase10_prototype_loop_report: object,
    gateway_observation_boundary: object,
    integration_policy: object,
    runtime_handoff_boundary: object,
    artifact_policy: object,
    rollback_policy: object,
) -> dict[str, object]:
    """Build a pure, default-off Phase 11 Gateway observation design report."""

    try:
        phase10 = _validate_phase10_report(phase10_prototype_loop_report)
        gateway = _validate_gateway_observation_boundary(gateway_observation_boundary)
        integration = _validate_integration_policy(integration_policy)
        runtime = _validate_runtime_handoff_boundary(runtime_handoff_boundary)
        artifact = _validate_artifact_policy(artifact_policy)
        rollback = _validate_rollback_policy(rollback_policy)
    except ValueError as exc:
        return _error_result(_safe_error_code(str(exc)))
    except Exception:
        return _error_result("invalid_phase10_report")

    surfaces = _bounded_ordered_intersection(gateway["allowed_surfaces"], _ALLOWED_SURFACES)
    operations = _bounded_ordered_intersection(runtime["runtime_operations"], _ALLOWED_RUNTIME_OPERATIONS)
    if not surfaces or not operations:
        return _error_result("invalid_gateway_observation_boundary")

    design_id = _design_id(
        phase10_run_id=phase10["run_id"],
        plan_transaction_id=phase10["plan_transaction_id"],
        touchpoints=gateway["candidate_touchpoints"],
    )
    return _success_result(
        design_id=design_id,
        phase10_run_id=phase10["run_id"],
        plan_transaction_id=phase10["plan_transaction_id"],
        gateway=gateway,
        integration=integration,
        runtime=runtime,
        artifact=artifact,
        rollback=rollback,
        allowed_surfaces=surfaces,
        runtime_operations=operations,
    )


def _validate_phase10_report(value: object) -> dict[str, object]:
    report = _plain_dict(value, error="invalid_phase10_report")
    if report.get("side_effects") != []:
        _raise("side_effects_not_absent")
    if report.get("verdict") in {
        "production_ready",
        "production_enabled",
        "live_enabled",
        "gateway_enabled",
        "observation_enabled",
        "integration_enabled",
    }:
        _raise("production_action_requested")
    extra_fields = set(report) - _PHASE10_SUCCESS_FIELDS
    if any(_matches_marker(field, _PRODUCTION_VALUE_MARKERS) for field in extra_fields):
        _raise("production_action_requested")
    _reject_unsafe_material(report, error="unsafe_material", allow_policy_value_fields=True)
    if extra_fields:
        _raise("invalid_phase10_report")
    if set(report) != _PHASE10_SUCCESS_FIELDS:
        _raise("invalid_phase10_report")
    if not (
        report["type"] == _PHASE10_REPORT_TYPE
        and report["version"] == _PHASE10_VERSION
        and report["ok"] is True
        and report["verdict"] == _PHASE10_VERDICT
        and report["phase"] == _PHASE10_PHASE
    ):
        _raise("invalid_phase10_report")
    run_id = _synthetic_id(report["run_id"], prefixes=("controlled_shadow_run_",), error="invalid_phase10_report")
    plan_transaction_id = _runtime_transaction_id(report["plan_transaction_id"], error="invalid_phase10_report")
    publication_count = _bounded_int(report["publication_count"], minimum=0, maximum=20, error="invalid_phase10_report")
    loop_results = _plain_list(report["loop_results"], error="invalid_phase10_report")
    if publication_count != len(loop_results):
        _raise("invalid_phase10_report")
    validated_loop_results = [_validate_phase10_loop_result(item) for item in loop_results]
    artifact = _validate_phase10_artifact(
        report["artifact"],
        run_id=run_id,
        plan_transaction_id=plan_transaction_id,
        publication_count=publication_count,
    )
    checks = _plain_dict(report["checks"], error="invalid_phase10_report")
    if set(checks) != set(_PHASE10_VERIFICATION_MATRIX) or any(checks[key] is not True for key in _PHASE10_VERIFICATION_MATRIX):
        _raise("invalid_phase10_report")
    approvals = _plain_string_list(report["required_separate_approvals"], error="invalid_phase10_report")
    if approvals != list(_PHASE10_REQUIRED_APPROVALS):
        _raise("invalid_phase10_report")
    matrix = _plain_string_list(report["verification_matrix"], error="invalid_phase10_report")
    if matrix != list(_PHASE10_VERIFICATION_MATRIX):
        _raise("invalid_phase10_report")
    runbook = _plain_string_list(report["runbook_outline"], error="invalid_phase10_report")
    if runbook != list(_PHASE10_RUNBOOK_OUTLINE):
        _raise("invalid_phase10_report")
    return {
        "run_id": run_id,
        "plan_transaction_id": plan_transaction_id,
        "publication_count": publication_count,
        "loop_results": validated_loop_results,
        "artifact": artifact,
    }


def _validate_phase10_loop_result(value: object) -> dict[str, object]:
    result = _plain_dict(value, error="invalid_phase10_report")
    if result.get("side_effects") != []:
        _raise("side_effects_not_absent")
    if set(result) != _PHASE10_LOOP_RESULT_FIELDS:
        _raise("invalid_phase10_report")
    workflow_id = _runtime_transaction_id(result["workflow_id"], error="invalid_phase10_report")
    transaction_id = _runtime_transaction_id(result["transaction_id"], error="invalid_phase10_report")
    if workflow_id != transaction_id:
        _raise("workflow_id_mismatch")
    if result["start_status"] not in {"started", "running"}:
        _raise("invalid_phase10_report")
    ack_count = _bounded_int(result["ack_count"], minimum=0, maximum=20, error="invalid_phase10_report")
    surfaces = _ordered_subset(result["surfaces"], allowed=_ALLOWED_SURFACES, error="invalid_phase10_report")
    status_counts = _safe_count_dict(result["status_counts"], error="invalid_phase10_report")
    delivery_counts = _safe_count_dict(result["delivery_counts"], error="invalid_phase10_report")
    stable_error_codes = _safe_label_list(result["stable_error_codes"], error="invalid_phase10_report", allow_empty=True)
    safe_digest = _safe_digest(result["safe_digest"], error="invalid_phase10_report")
    return {
        "workflow_id": workflow_id,
        "transaction_id": transaction_id,
        "ack_count": ack_count,
        "surfaces": surfaces,
        "status_counts": status_counts,
        "delivery_counts": delivery_counts,
        "stable_error_codes": stable_error_codes,
        "safe_digest": safe_digest,
    }


def _validate_phase10_artifact(
    value: object,
    *,
    run_id: str,
    plan_transaction_id: str,
    publication_count: int,
) -> dict[str, object]:
    artifact = _plain_dict(value, error="invalid_phase10_report")
    if artifact.get("side_effects") != []:
        _raise("side_effects_not_absent")
    if set(artifact) != _PHASE10_ARTIFACT_FIELDS:
        _raise("invalid_phase10_report")
    if not (
        artifact["type"] == _PHASE10_ARTIFACT_TYPE
        and artifact["artifact_mode"] == "safe_summary_only"
        and artifact["run_id"] == run_id
        and artifact["plan_transaction_id"] == plan_transaction_id
        and artifact["publication_count"] == publication_count
    ):
        _raise("invalid_phase10_report")
    approvals = _plain_string_list(artifact["approvals"], error="invalid_phase10_report")
    if approvals != list(_PHASE10_REQUIRED_APPROVALS):
        _raise("invalid_phase10_report")
    _safe_count_dict(artifact["operation_counts"], error="invalid_phase10_report")
    _safe_count_dict(artifact["delivery_counts"], error="invalid_phase10_report")
    _safe_count_dict(artifact["statuses"], error="invalid_phase10_report")
    digests = _plain_string_list(artifact["digests"], error="invalid_phase10_report")
    if any(not _is_safe_digest(item) for item in digests):
        _raise("invalid_phase10_report")
    _safe_label_list(artifact["stable_error_codes"], error="invalid_phase10_report", allow_empty=True)
    return dict(artifact)


def _validate_gateway_observation_boundary(value: object) -> dict[str, object]:
    boundary = _plain_dict(value, error="invalid_gateway_observation_boundary")
    if boundary.get("side_effects") != []:
        _raise("side_effects_not_absent")
    _reject_requested_actions(boundary)
    _reject_unsafe_material(boundary, error="unsafe_material", allow_descriptor_policy_names=True)
    if set(boundary) != _GATEWAY_OBSERVATION_BOUNDARY_FIELDS:
        _raise("invalid_gateway_observation_boundary")
    if boundary["type"] != CONTROLLED_GATEWAY_OBSERVATION_BOUNDARY_TYPE:
        _raise("invalid_gateway_observation_boundary")
    mode = _safe_string(boundary["mode"], error="invalid_gateway_observation_boundary")
    source_kind = _safe_string(boundary["source_kind"], error="invalid_gateway_observation_boundary")
    if mode in {"live", "production", "enabled"} or source_kind in {"real_feishu", "real_sachima", "live_gateway_stream"}:
        _raise("production_action_requested")
    if mode not in {"design_only", "future_default_off_observation_candidate"}:
        _raise("invalid_gateway_observation_boundary")
    if source_kind not in {"phase10_evidence_replay", "gateway_shadow_publication_summary", "simulator_fixture"}:
        _raise("invalid_gateway_observation_boundary")
    if boundary["adapter_imports_allowed"] is True or boundary["send_edit_render_callback_allowed"] is True:
        _raise("production_action_requested")
    if boundary["platform_payloads_allowed"] is True or boundary["message_identifiers_allowed"] is True:
        _raise("production_action_requested")
    if boundary["raw_content_allowed"] is True:
        _raise("unsafe_material")
    if not all(
        boundary[key] is False
        for key in (
            "adapter_imports_allowed",
            "platform_payloads_allowed",
            "message_identifiers_allowed",
            "raw_content_allowed",
            "send_edit_render_callback_allowed",
        )
    ):
        _raise("invalid_gateway_observation_boundary")
    logs_allowed = boundary["logs_allowed"]
    if logs_allowed not in {"sanitized_codes_only", "false", False}:
        _raise("invalid_gateway_observation_boundary")
    return {
        "mode": mode,
        "source_kind": source_kind,
        "candidate_touchpoints": _ordered_subset(
            boundary["candidate_touchpoints"],
            allowed=_ALLOWED_TOUCHPOINTS,
            error="invalid_gateway_observation_boundary",
        ),
        "allowed_existing_modules": _ordered_subset(
            boundary["allowed_existing_modules"],
            allowed=_ALLOWED_EXISTING_MODULES,
            error="invalid_gateway_observation_boundary",
        ),
        "allowed_future_files": _ordered_subset(
            boundary["allowed_future_files"],
            allowed=_ALLOWED_FUTURE_FILES,
            error="invalid_gateway_observation_boundary",
        ),
        "allowed_surfaces": _ordered_subset(
            boundary["allowed_surfaces"],
            allowed=_ALLOWED_SURFACES,
            error="invalid_gateway_observation_boundary",
        ),
        "observation_inputs": _ordered_subset(
            boundary["observation_inputs"],
            allowed=_ALLOWED_OBSERVATION_INPUTS,
            error="invalid_gateway_observation_boundary",
        ),
        "observation_outputs": _ordered_subset(
            boundary["observation_outputs"],
            allowed=_ALLOWED_OBSERVATION_OUTPUTS,
            error="invalid_gateway_observation_boundary",
        ),
    }


def _validate_integration_policy(value: object) -> dict[str, object]:
    policy = _plain_dict(value, error="invalid_integration_policy")
    if policy.get("side_effects") != []:
        _raise("side_effects_not_absent")
    _reject_requested_actions(policy)
    _reject_unsafe_material(policy, error="unsafe_material", allow_descriptor_policy_names=True)
    if set(policy) != _INTEGRATION_POLICY_FIELDS:
        _raise("invalid_integration_policy")
    if policy["type"] != CONTROLLED_GATEWAY_INTEGRATION_POLICY_TYPE:
        _raise("invalid_integration_policy")
    mode = _safe_string(policy["mode"], error="invalid_integration_policy")
    if mode in {"production", "live", "enabled"}:
        _raise("production_action_requested")
    if mode not in {"design_gate_only", "implementation_contract_only"}:
        _raise("invalid_integration_policy")
    if policy["default_enabled"] is True or policy["runtime_effects_allowed"] is True:
        _raise("production_action_requested")
    if policy["config_write_allowed"] is True or policy["registry_write_allowed"] is True:
        _raise("registry_or_config_write_requested")
    if policy["gateway_restart_allowed"] is True:
        _raise("production_action_requested")
    if policy["temporal_lifecycle_allowed"] is True or policy["payload_carrying_signals_allowed"] is True:
        _raise("runtime_lifecycle_requested")
    if not all(
        policy[key] is False
        for key in (
            "default_enabled",
            "config_write_allowed",
            "gateway_restart_allowed",
            "runtime_effects_allowed",
            "temporal_lifecycle_allowed",
            "payload_carrying_signals_allowed",
            "registry_write_allowed",
        )
    ):
        _raise("invalid_integration_policy")
    if policy["implementation_stage"] not in {"design_only", "future_pr_only"}:
        _raise("invalid_integration_policy")
    if policy["allowed_config_scope"] not in {"static_docs_only", "test_fixture_only"}:
        _raise("registry_or_config_write_requested")
    feature_flag_ref = _synthetic_id(policy["feature_flag_ref"], prefixes=("feature_flag_ref_",), error="invalid_integration_policy")
    operator_approval_ref = _synthetic_id(
        policy["operator_approval_ref"],
        prefixes=("approval_ref_",),
        error="invalid_integration_policy",
    )
    rollout_steps = _ordered_subset(policy["rollout_steps"], allowed=_ALLOWED_ROLLOUT_STEPS, error="invalid_integration_policy")
    if policy["rollback_required"] is not True or policy["kill_switch_required"] is not True:
        _raise("invalid_integration_policy")
    return {
        "feature_flag_ref": feature_flag_ref,
        "operator_approval_ref": operator_approval_ref,
        "rollout_steps": rollout_steps,
    }


def _validate_runtime_handoff_boundary(value: object) -> dict[str, object]:
    boundary = _plain_dict(value, error="invalid_runtime_handoff_boundary")
    if boundary.get("side_effects") != []:
        _raise("side_effects_not_absent")
    _reject_runtime_lifecycle_keys(boundary)
    _reject_requested_actions(boundary)
    _reject_unsafe_material(boundary, error="unsafe_material", allow_descriptor_policy_names=True)
    extra = set(boundary) - _RUNTIME_HANDOFF_FIELDS
    if extra:
        _raise("invalid_runtime_handoff_boundary")
    if boundary["type"] != CONTROLLED_GATEWAY_RUNTIME_HANDOFF_BOUNDARY_TYPE:
        _raise("invalid_runtime_handoff_boundary")
    if boundary["mode"] not in {"no_live_handoff", "future_caller_supplied_only"}:
        _raise("runtime_lifecycle_requested")
    if boundary["control_surface_lifecycle"] not in {"none", "caller_supplied_only"}:
        _raise("runtime_lifecycle_requested")
    if any(
        boundary[key] is True
        for key in (
            "runtime_client_construction_allowed",
            "temporal_client_allowed",
            "temporal_worker_allowed",
            "workflow_environment_allowed",
            "payload_carrying_signals_allowed",
        )
    ):
        _raise("runtime_lifecycle_requested")
    if not all(
        boundary[key] is False
        for key in (
            "runtime_client_construction_allowed",
            "temporal_client_allowed",
            "temporal_worker_allowed",
            "workflow_environment_allowed",
            "payload_carrying_signals_allowed",
        )
    ):
        _raise("invalid_runtime_handoff_boundary")
    operations = _ordered_subset(
        boundary["runtime_operations"],
        allowed=_ALLOWED_RUNTIME_OPERATIONS,
        error="invalid_runtime_handoff_boundary",
    )
    if boundary["fixture_projection"] != "phase10_publication_fixture_shape":
        _raise("invalid_runtime_handoff_boundary")
    if boundary["ack_source"] not in {"phase6_shadow_bridge", "shadow_runtime_publication_summary"}:
        _raise("invalid_runtime_handoff_boundary")
    if boundary["ack_target_validation"] != "exact_initialized_delivery_slot":
        _raise("invalid_runtime_handoff_boundary")
    return {"mode": boundary["mode"], "runtime_operations": operations}


def _validate_artifact_policy(value: object) -> dict[str, object]:
    policy = _plain_dict(value, error="invalid_artifact_policy")
    if policy.get("side_effects") != []:
        _raise("side_effects_not_absent")
    if set(policy) != _ARTIFACT_POLICY_FIELDS:
        _raise("invalid_artifact_policy")
    if policy["type"] != CONTROLLED_GATEWAY_ARTIFACT_POLICY_TYPE or policy["artifact_mode"] != "safe_summary_only":
        _raise("invalid_artifact_policy")
    allowed_fields = _ordered_subset(
        policy["allowed_fields"],
        allowed=_ALLOWED_ARTIFACT_FIELDS,
        error="artifact_policy_violation",
    )
    if policy["retention"] not in {"docs_evidence_only", "local_artifact_only"}:
        _raise("artifact_policy_violation")
    if policy["log_policy"] not in {"sanitized_codes_only", "no_logs"}:
        _raise("artifact_policy_violation")
    forbidden = _plain_string_list(policy["forbidden_material"], error="invalid_artifact_policy")
    if forbidden != list(_FORBIDDEN_MATERIAL):
        _raise("artifact_policy_violation")
    _reject_unsafe_material(
        policy,
        error="unsafe_material",
        allow_descriptor_policy_names=True,
        allow_policy_value_fields=True,
    )
    return {
        "artifact_mode": "safe_summary_only",
        "allowed_fields": allowed_fields,
        "retention": policy["retention"],
        "log_policy": policy["log_policy"],
        "forbidden_material": list(_FORBIDDEN_MATERIAL),
        "side_effects": [],
    }


def _validate_rollback_policy(value: object) -> dict[str, object]:
    policy = _plain_dict(value, error="invalid_rollback_policy")
    if policy.get("side_effects") != []:
        _raise("side_effects_not_absent")
    _reject_requested_actions(policy)
    _reject_unsafe_material(policy, error="unsafe_material", allow_descriptor_policy_names=True)
    if set(policy) != _ROLLBACK_POLICY_FIELDS:
        _raise("invalid_rollback_policy")
    if policy["type"] != CONTROLLED_GATEWAY_ROLLBACK_POLICY_TYPE:
        _raise("invalid_rollback_policy")
    if policy["rollback_mode"] not in {"design_only", "feature_flag_off_first"}:
        _raise("production_action_requested")
    if policy["config_revert_required"] is not True:
        _raise("registry_or_config_write_requested")
    if policy["gateway_restart_requires_separate_approval"] is not True:
        _raise("production_action_requested")
    if policy["production_enablement_requires_separate_approval"] is not True:
        _raise("production_action_requested")
    if policy["kill_switch_required"] is not True or policy["rollback_hooks_required"] is not True:
        _raise("invalid_rollback_policy")
    return {
        "rollback_mode": policy["rollback_mode"],
        "kill_switch_required": True,
        "rollback_hooks_required": True,
        "config_revert_required": True,
        "gateway_restart_requires_separate_approval": True,
        "production_enablement_requires_separate_approval": True,
        "side_effects": [],
    }


def _success_result(
    *,
    design_id: str,
    phase10_run_id: str,
    plan_transaction_id: str,
    gateway: dict[str, object],
    integration: dict[str, object],
    runtime: dict[str, object],
    artifact: dict[str, object],
    rollback: dict[str, object],
    allowed_surfaces: list[str],
    runtime_operations: list[str],
) -> dict[str, object]:
    report: dict[str, object] = {
        "type": CONTROLLED_GATEWAY_OBSERVATION_DESIGN_REPORT_TYPE,
        "version": FLOWWEAVER_CONTROLLED_GATEWAY_OBSERVATION_DESIGN_VERSION,
        "ok": True,
        "verdict": _SUCCESS_VERDICT,
        "phase": _PHASE,
        "design_id": design_id,
        "phase10_run_id": phase10_run_id,
        "plan_transaction_id": plan_transaction_id,
        "controlled_gateway_observation_plan": {
            "plan_version": FLOWWEAVER_CONTROLLED_GATEWAY_OBSERVATION_DESIGN_VERSION,
            "source_kind": gateway["source_kind"],
            "mode": gateway["mode"],
            "candidate_touchpoints": list(gateway["candidate_touchpoints"]),
            "allowed_existing_modules": list(gateway["allowed_existing_modules"]),
            "allowed_future_files": list(gateway["allowed_future_files"]),
            "allowed_surfaces": list(allowed_surfaces),
            "observation_inputs": list(gateway["observation_inputs"]),
            "observation_outputs": list(gateway["observation_outputs"]),
            "feature_flag_ref": integration["feature_flag_ref"],
            "operator_approval_ref": integration["operator_approval_ref"],
            "runtime_operations": list(runtime_operations),
            "runtime_handoff_mode": runtime["mode"],
            "artifact_mode": artifact["artifact_mode"],
            "approval_refs": {
                "operator_approval_ref": integration["operator_approval_ref"],
                "feature_flag_ref": integration["feature_flag_ref"],
            },
            "rollback_hooks_required": rollback["rollback_hooks_required"],
            "kill_switch_required": rollback["kill_switch_required"],
            "forbidden_material": list(_FORBIDDEN_MATERIAL),
            "fail_closed_errors": sorted(_ERROR_CODES),
        },
        "checks": {key: True for key in _VERIFICATION_MATRIX},
        "artifact_policy": dict(artifact),
        "rollback_policy": dict(rollback),
        "required_separate_approvals": list(_REQUIRED_SEPARATE_APPROVALS),
        "verification_matrix": list(_VERIFICATION_MATRIX),
        "runbook_outline": list(_RUNBOOK_OUTLINE),
        "side_effects": [],
    }
    _assert_report_shape(report)
    return report


def _error_result(error_code: str) -> dict[str, object]:
    report: dict[str, object] = {
        "type": CONTROLLED_GATEWAY_OBSERVATION_DESIGN_REPORT_TYPE,
        "version": FLOWWEAVER_CONTROLLED_GATEWAY_OBSERVATION_DESIGN_VERSION,
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
        items = []
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


def _ordered_subset(value: object, *, allowed: tuple[str, ...], error: str) -> list[str]:
    values = _plain_string_list(value, error=error)
    if not values or len(set(values)) != len(values):
        _raise(error)
    if any(_matches_marker(item, _PRODUCTION_VALUE_MARKERS) for item in values):
        _raise("production_action_requested")
    if any(_matches_marker(item, _CONFIG_REGISTRY_MARKERS) for item in values):
        _raise("registry_or_config_write_requested")
    if any(_matches_marker(item, _RUNTIME_LIFECYCLE_MARKERS) for item in values):
        _raise("runtime_lifecycle_requested")
    if [item for item in allowed if item in values] != values:
        _raise(error)
    return values


def _safe_label_list(value: object, *, error: str, allow_empty: bool = False) -> list[str]:
    labels = _plain_string_list(value, error=error)
    if not allow_empty and not labels:
        _raise(error)
    if len(set(labels)) != len(labels) or any(not _safe_label(item) for item in labels):
        _raise(error)
    return labels


def _safe_count_dict(value: object, *, error: str) -> dict[str, int]:
    counts = _plain_dict(value, error=error)
    result: dict[str, int] = {}
    for key, item in counts.items():
        if not _safe_label(key) or type(item) is not int or item < 0 or item > 10_000:
            _raise(error)
        result[key] = item
    return result


def _runtime_transaction_id(value: object, *, error: str) -> str:
    return _synthetic_id(value, prefixes=("runtime_tx_",), error=error)


def _synthetic_id(value: object, *, prefixes: tuple[str, ...], error: str) -> str:
    if type(value) is not str or not value or len(value) > 160:
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
    if any(_matches_marker(lowered, markers) for markers in (_PRODUCTION_VALUE_MARKERS, _CONFIG_REGISTRY_MARKERS)):
        _raise(error)
    if not all(("a" <= char <= "z") or ("0" <= char <= "9") or char == "_" for char in lowered):
        _raise(error)
    return value


def _safe_label(value: str) -> bool:
    return bool(value) and len(value) <= 128 and all(("a" <= char <= "z") or ("0" <= char <= "9") or char == "_" for char in value)


def _safe_digest(value: object, *, error: str) -> str:
    if type(value) is not str or not _is_safe_digest(value):
        _raise(error)
    return value


def _is_safe_digest(value: str) -> bool:
    return bool(value) and len(value) <= 128 and all(("a" <= char.lower() <= "f") or ("0" <= char <= "9") for char in value)


def _bounded_ordered_intersection(values: list[str], allowed: tuple[str, ...]) -> list[str]:
    allowed_set = set(allowed)
    if any(value not in allowed_set for value in values):
        return []
    if [value for value in allowed if value in values] != values:
        return []
    return list(values)


def _phase10_allowed_surfaces(loop_results: list[dict[str, object]]) -> list[str]:
    surfaces: list[str] = []
    for result in loop_results:
        for surface in result["surfaces"]:
            if surface not in surfaces:
                surfaces.append(surface)
    if not surfaces:
        return list(_ALLOWED_SURFACES)
    return [surface for surface in _ALLOWED_SURFACES if surface in surfaces]


def _design_id(*, phase10_run_id: str, plan_transaction_id: str, touchpoints: list[str]) -> str:
    digest = sha256((phase10_run_id + "|" + plan_transaction_id + "|" + "|".join(touchpoints)).encode()).hexdigest()[:16]
    return "controlled_gateway_observation_design_" + digest


def _reject_requested_actions(value: object) -> None:
    marker = _find_marker(value, _PRODUCTION_VALUE_MARKERS)
    if marker:
        _raise("production_action_requested")
    marker = _find_marker(value, _CONFIG_REGISTRY_MARKERS)
    if marker:
        _raise("registry_or_config_write_requested")
    marker = _find_marker(value, _RUNTIME_LIFECYCLE_MARKERS)
    if marker:
        _raise("runtime_lifecycle_requested")


def _reject_runtime_lifecycle_keys(value: object) -> None:
    marker = _find_marker(value, _RUNTIME_LIFECYCLE_MARKERS)
    if marker:
        _raise("runtime_lifecycle_requested")


def _find_marker(value: object, markers: tuple[str, ...]) -> str | None:
    if type(value) is dict:
        for key, item in value.items():
            if key not in _DESCRIPTOR_KEYS and _matches_marker(key, markers):
                return key
            found = _find_marker(item, markers)
            if found:
                return found
    elif type(value) is list:
        for item in value:
            found = _find_marker(item, markers)
            if found:
                return found
    elif type(value) is str and _matches_marker(value, markers):
        return value
    return None


def _matches_marker(value: str, markers: tuple[str, ...]) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in markers)


def _reject_unsafe_material(
    value: object,
    *,
    error: str,
    allow_descriptor_policy_names: bool = False,
    allow_policy_value_fields: bool = False,
    path: tuple[str, ...] = (),
) -> None:
    if allow_policy_value_fields and path and path[-1] in _POLICY_VALUE_FIELDS:
        allowed_policy_values = _allowed_policy_values_for_path(path)
        if allowed_policy_values is None:
            return
        if type(value) is str and value in allowed_policy_values:
            return
    if type(value) is dict:
        for key, item in value.items():
            lowered = key.lower()
            allow_key_name = (
                (allow_descriptor_policy_names and key in _DESCRIPTOR_KEYS)
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


def _allowed_policy_values_for_path(path: tuple[str, ...]) -> set[str] | None:
    if path == ("forbidden_material",):
        return set(_FORBIDDEN_MATERIAL)
    if path == ("runbook_outline",):
        return set(_PHASE10_RUNBOOK_OUTLINE)
    if path == ("controlled_gateway_observation_plan", "forbidden_material"):
        return set(_FORBIDDEN_MATERIAL)
    return None


def _safe_error_code(error_code: object) -> str:
    if type(error_code) is str and error_code in _ERROR_CODES:
        return error_code
    return "invalid_phase10_report"


def _assert_report_shape(report: dict[str, object]) -> None:
    if not set(report) <= _REPORT_FIELDS:
        _raise("unsafe_material")


def _raise(code: str) -> None:
    raise ValueError(code)


__all__ = [
    "FLOWWEAVER_CONTROLLED_GATEWAY_OBSERVATION_DESIGN_VERSION",
    "CONTROLLED_GATEWAY_OBSERVATION_BOUNDARY_TYPE",
    "CONTROLLED_GATEWAY_INTEGRATION_POLICY_TYPE",
    "CONTROLLED_GATEWAY_RUNTIME_HANDOFF_BOUNDARY_TYPE",
    "CONTROLLED_GATEWAY_ARTIFACT_POLICY_TYPE",
    "CONTROLLED_GATEWAY_ROLLBACK_POLICY_TYPE",
    "CONTROLLED_GATEWAY_OBSERVATION_DESIGN_REPORT_TYPE",
    "design_flowweaver_controlled_gateway_observation",
]
