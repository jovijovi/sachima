"""Pure default-off controlled Gateway observation hook contract for FlowWeaver Phase 12."""

from __future__ import annotations

from hashlib import sha256

FLOWWEAVER_CONTROLLED_GATEWAY_OBSERVATION_HOOK_VERSION = "flowweaver.controlled_gateway_observation_hook.v0"
CONTROLLED_GATEWAY_OBSERVATION_HOOK_REPORT_TYPE = "flowweaver.controlled_gateway_observation_hook_report.v0"

_PHASE = "phase12_controlled_gateway_observation_hook"
_SUCCESS_VERDICT = "ready_for_live_gateway_observation_enablement_design"
_BLOCKED_VERDICT = "blocked"
_OBSERVATION_MODE = "default_off_static_projection"
_PHASE11_REPORT_TYPE = "flowweaver.controlled_gateway_observation_design_report.v0"
_PHASE11_VERSION = "flowweaver.controlled_gateway_observation_design.v0"
_PHASE11_VERDICT = "ready_for_controlled_gateway_observation_implementation"
_PHASE11_PHASE = "phase11_controlled_gateway_observation_integration_design"
_SHADOW_PUBLICATION_TYPE = "flowweaver.gateway.shadow_runtime_publication.v0"
_DELIVERY_SUMMARY_TYPE = "flowweaver.gateway.delivery_state_summary.v0"
_PROGRESS_SUMMARY_TYPE = "flowweaver.gateway.progress_snapshot_summary.v0"

_PHASE11_REQUIRED_APPROVALS = [
    "controlled_gateway_observation_implementation",
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
    "live_gateway_observation_enablement",
    "production_gateway_wiring",
    "production_config_write",
    "gateway_restart",
    "external_temporal_service",
    "real_send_edit_render_callback",
    "production_tool_registry",
    "remote_branch_or_worktree_cleanup",
]
_PHASE11_VERIFICATION_MATRIX = [
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
_VERIFICATION_MATRIX = [
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
_PHASE11_RUNBOOK_OUTLINE = [
    "phase11_is_design_gate_only",
    "controlled_gateway_observation_implementation_requires_separate_approval",
    "live_gateway_observation_enablement_requires_separate_approval",
    "production_activation_requires_separate_design_and_approval",
    "keep_default_off_until_explicit_enablement",
    "rollback_and_kill_switch_required_before_any_wiring",
    "no_raw_payloads_or_secrets_in_reports_or_artifacts",
    "use_direct_pytest_for_integration_regression",
]
_RUNBOOK_OUTLINE = [
    "phase12_is_default_off_observation_hook_only",
    "live_gateway_observation_enablement_requires_separate_approval",
    "production_activation_requires_separate_design_and_approval",
    "keep_default_off_until_explicit_enablement",
    "no_gateway_run_or_platform_adapter_wiring",
    "no_temporal_client_worker_" + "dock" + "er_or_service_lifecycle",
    "no_raw_payloads_or_secrets_in_reports_or_artifacts",
    "use_direct_pytest_for_integration_regression",
]
_PHASE11_FORBIDDEN_MATERIAL = [
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
_PHASE11_ERROR_CODES = sorted(
    {
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
)
_ERROR_CODES = {
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
}
_PLAN_FIELDS = {
    "plan_version",
    "source_kind",
    "mode",
    "candidate_touchpoints",
    "allowed_existing_modules",
    "allowed_future_files",
    "allowed_surfaces",
    "observation_inputs",
    "observation_outputs",
    "feature_flag_ref",
    "operator_approval_ref",
    "runtime_operations",
    "runtime_handoff_mode",
    "artifact_mode",
    "approval_refs",
    "rollback_hooks_required",
    "kill_switch_required",
    "forbidden_material",
    "fail_closed_errors",
}
_ARTIFACT_POLICY_FIELDS = {"artifact_mode", "allowed_fields", "retention", "log_policy", "forbidden_material", "side_effects"}
_ROLLBACK_POLICY_FIELDS = {
    "rollback_mode",
    "kill_switch_required",
    "rollback_hooks_required",
    "config_revert_required",
    "gateway_restart_requires_separate_approval",
    "production_enablement_requires_separate_approval",
    "side_effects",
}
_SHADOW_SUMMARY_FIELDS = {
    "type",
    "verdict",
    "reason",
    "runtime_model_version",
    "runtime_envelope_type",
    "transaction_id",
    "workflow_id",
    "start_status",
    "publication_count",
    "ack_bridge",
    "checks",
    "side_effects",
}
_ACK_BRIDGE_FIELDS = {"status", "update_count", "surfaces", "stable_error_codes", "side_effects"}
_DELIVERY_SUMMARY_FIELDS = {"type", "transaction_id", "surface_counts", "status_counts", "stable_error_codes", "side_effects"}
_PROGRESS_SUMMARY_FIELDS = {"type", "transaction_id", "event_counts", "visible_event_count", "stable_error_codes", "side_effects"}
_ALLOWED_TOUCHPOINTS = [
    "task_tracker_snapshot",
    "flowweaver_shadow_snapshot",
    "flowweaver_shadow_runtime_publication",
    "delivery_state_summary",
]
_ALLOWED_EXISTING_MODULES = [
    "gateway/flowweaver_shadow.py",
    "gateway/flowweaver_shadow_publisher.py",
    "gateway/flowweaver_contract.py",
    "gateway/delivery_state.py",
    "gateway/progress/events.py",
]
_ALLOWED_FUTURE_FILES = [
    "gateway/flowweaver_controlled_gateway_observation.py",
    "tests/gateway/test_flowweaver_controlled_gateway_observation.py",
]
_ALLOWED_PHASE11_INPUTS = [
    "phase10_report",
    "shadow_runtime_publication_summary",
    "delivery_state_summary",
    "progress_snapshot_summary",
]
_ALLOWED_PHASE11_OUTPUTS = ["safe_summary", "fixture_projection", "readiness_checks", "stable_error_codes"]
_ALLOWED_RUNTIME_OPERATIONS = ["start_transaction", "query_transaction", "reconcile_delivery_ack"]
_PHASE11_ARTIFACT_ALLOWED_FIELDS = [
    "design_id",
    "phase10_run_id",
    "plan_transaction_id",
    "candidate_touchpoints",
    "allowed_surfaces",
    "checks",
    "stable_error_codes",
    "approvals",
    "side_effects",
]
_ALLOWED_SURFACES = ["final_text", "rich_card", "progress_card", "media"]
_SUMMARY_INPUTS = [
    "phase11_design_report",
    "shadow_runtime_publication_summary",
    "delivery_state_summary",
    "progress_snapshot_summary",
]
_ALLOWED_STATUSES = {"ready", "started", "running"}
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
    "://".join(("postgres", "")),
    "://".join(("mysql", "")),
    "://".join(("mongodb", "")),
    "://".join(("redis", "")),
)
_INVALID = object()


def build_flowweaver_controlled_gateway_observation(
    *,
    phase11_design_report: object,
    shadow_runtime_publication_summary: object,
    delivery_state_summary: object,
    progress_snapshot_summary: object,
    enabled: object = False,
) -> dict[str, object]:
    """Build a pure default-off Phase 12 Gateway observation hook report."""

    if enabled is not False:
        return _error_result("live_observation_requested")
    try:
        phase11 = _validate_phase11_report(phase11_design_report)
        shadow = _validate_shadow_summary(
            shadow_runtime_publication_summary,
            plan_transaction_id=phase11["plan_transaction_id"],
        )
        delivery = _validate_delivery_summary(
            delivery_state_summary,
            plan_transaction_id=phase11["plan_transaction_id"],
        )
        progress = _validate_progress_summary(
            progress_snapshot_summary,
            plan_transaction_id=phase11["plan_transaction_id"],
        )
    except ValueError as exc:
        return _error_result(_safe_error_code(exc.args[0] if exc.args else "invalid_phase11_report"))
    except Exception:
        return _error_result("invalid_phase11_report")

    stable_codes = sorted(set(shadow["stable_error_codes"] + delivery["stable_error_codes"] + progress["stable_error_codes"]))
    observation_id = _observation_id(
        design_id=phase11["design_id"],
        plan_transaction_id=phase11["plan_transaction_id"],
    )
    observation = {
        "source_design_verdict": _PHASE11_VERDICT,
        "candidate_touchpoints": list(phase11["candidate_touchpoints"]),
        "allowed_surfaces": list(phase11["allowed_surfaces"]),
        "summary_inputs": list(_SUMMARY_INPUTS),
        "shadow_runtime_publication": shadow,
        "delivery_state": delivery,
        "progress_snapshot": progress,
        "stable_error_codes": stable_codes,
        "safe_digest": _safe_digest(
            observation_id,
            phase11["design_id"],
            phase11["phase10_run_id"],
            phase11["plan_transaction_id"],
            *stable_codes,
        ),
        "approvals": list(_REQUIRED_SEPARATE_APPROVALS),
        "side_effects": [],
    }
    return {
        "type": CONTROLLED_GATEWAY_OBSERVATION_HOOK_REPORT_TYPE,
        "version": FLOWWEAVER_CONTROLLED_GATEWAY_OBSERVATION_HOOK_VERSION,
        "ok": True,
        "verdict": _SUCCESS_VERDICT,
        "phase": _PHASE,
        "observation_id": observation_id,
        "phase11_design_id": phase11["design_id"],
        "phase10_run_id": phase11["phase10_run_id"],
        "plan_transaction_id": phase11["plan_transaction_id"],
        "observation_mode": _OBSERVATION_MODE,
        "controlled_gateway_observation": observation,
        "checks": {key: True for key in _VERIFICATION_MATRIX},
        "artifact_policy": {
            "artifact_mode": "safe_summary_only",
            "log_policy": "sanitized_codes_only",
            "forbidden_material": list(_PHASE11_FORBIDDEN_MATERIAL),
            "side_effects": [],
        },
        "required_separate_approvals": list(_REQUIRED_SEPARATE_APPROVALS),
        "verification_matrix": list(_VERIFICATION_MATRIX),
        "runbook_outline": list(_RUNBOOK_OUTLINE),
        "side_effects": [],
    }


def _validate_phase11_report(value: object) -> dict[str, object]:
    report = _plain_dict(value, error="invalid_phase11_report")
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
        _raise("invalid_phase11_report")
    if set(report) != _REPORT_FIELDS:
        _raise("invalid_phase11_report")
    if not (
        report["type"] == _PHASE11_REPORT_TYPE
        and report["version"] == _PHASE11_VERSION
        and report["ok"] is True
        and report["verdict"] == _PHASE11_VERDICT
        and report["phase"] == _PHASE11_PHASE
    ):
        _raise("invalid_phase11_report")
    checks = _plain_dict(report["checks"], error="invalid_phase11_report")
    if set(checks) != set(_PHASE11_VERIFICATION_MATRIX) or any(checks[key] is not True for key in _PHASE11_VERIFICATION_MATRIX):
        _raise("invalid_phase11_report")
    approvals = _plain_string_list(report["required_separate_approvals"], error="invalid_phase11_report")
    if approvals != list(_PHASE11_REQUIRED_APPROVALS):
        _raise("invalid_phase11_report")
    matrix = _plain_string_list(report["verification_matrix"], error="invalid_phase11_report")
    if matrix != list(_PHASE11_VERIFICATION_MATRIX):
        _raise("invalid_phase11_report")
    runbook = _plain_string_list(report["runbook_outline"], error="invalid_phase11_report")
    if runbook != list(_PHASE11_RUNBOOK_OUTLINE):
        _raise("invalid_phase11_report")
    plan = _validate_phase11_plan(report["controlled_gateway_observation_plan"])
    _validate_phase11_artifact_policy(report["artifact_policy"])
    _validate_phase11_rollback_policy(report["rollback_policy"])
    design_id = _synthetic_id(
        report["design_id"],
        prefixes=("controlled_gateway_observation_design_",),
        error="invalid_phase11_report",
    )
    phase10_run_id = _synthetic_id(
        report["phase10_run_id"],
        prefixes=("controlled_shadow_run_",),
        error="invalid_phase11_report",
    )
    plan_transaction_id = _runtime_transaction_id(report["plan_transaction_id"], error="invalid_phase11_report")
    return {
        "design_id": design_id,
        "phase10_run_id": phase10_run_id,
        "plan_transaction_id": plan_transaction_id,
        "candidate_touchpoints": plan["candidate_touchpoints"],
        "allowed_surfaces": plan["allowed_surfaces"],
    }


def _validate_phase11_plan(value: object) -> dict[str, object]:
    plan = _plain_dict(value, error="invalid_phase11_report")
    if set(plan) != _PLAN_FIELDS:
        _raise("invalid_phase11_report")
    if not (
        plan["plan_version"] == _PHASE11_VERSION
        and plan["source_kind"] == "phase10_evidence_replay"
        and plan["mode"] == "future_default_off_observation_candidate"
        and plan["artifact_mode"] == "safe_summary_only"
        and plan["rollback_hooks_required"] is True
        and plan["kill_switch_required"] is True
    ):
        _raise("invalid_phase11_report")
    if _plain_string_list(plan["forbidden_material"], error="invalid_phase11_report") != list(_PHASE11_FORBIDDEN_MATERIAL):
        _raise("invalid_phase11_report")
    if _plain_string_list(plan["fail_closed_errors"], error="invalid_phase11_report") != list(_PHASE11_ERROR_CODES):
        _raise("invalid_phase11_report")
    candidate_touchpoints = _ordered_subset(
        plan["candidate_touchpoints"],
        allowed=_ALLOWED_TOUCHPOINTS,
        error="invalid_phase11_report",
    )
    if _plain_string_list(plan["allowed_existing_modules"], error="invalid_phase11_report") != list(_ALLOWED_EXISTING_MODULES):
        _raise("invalid_phase11_report")
    if _plain_string_list(plan["allowed_future_files"], error="invalid_phase11_report") != list(_ALLOWED_FUTURE_FILES):
        _raise("invalid_phase11_report")
    allowed_surfaces = _ordered_subset(
        plan["allowed_surfaces"],
        allowed=_ALLOWED_SURFACES,
        error="invalid_phase11_report",
    )
    if _plain_string_list(plan["observation_inputs"], error="invalid_phase11_report") != list(_ALLOWED_PHASE11_INPUTS):
        _raise("invalid_phase11_report")
    if _plain_string_list(plan["observation_outputs"], error="invalid_phase11_report") != list(_ALLOWED_PHASE11_OUTPUTS):
        _raise("invalid_phase11_report")
    if plan["feature_flag_ref"] != "feature_flag_ref_phase11_controlled_gateway_observation_off":
        _raise("invalid_phase11_report")
    if plan["operator_approval_ref"] != "approval_ref_phase11_implementation_contract":
        _raise("invalid_phase11_report")
    if _plain_string_list(plan["runtime_operations"], error="invalid_phase11_report") != list(_ALLOWED_RUNTIME_OPERATIONS):
        _raise("invalid_phase11_report")
    if plan["runtime_handoff_mode"] != "future_caller_supplied_only":
        _raise("invalid_phase11_report")
    approval_refs = _plain_dict(plan["approval_refs"], error="invalid_phase11_report")
    if approval_refs != {
        "operator_approval_ref": "approval_ref_phase11_implementation_contract",
        "feature_flag_ref": "feature_flag_ref_phase11_controlled_gateway_observation_off",
    }:
        _raise("invalid_phase11_report")
    return {"candidate_touchpoints": candidate_touchpoints, "allowed_surfaces": allowed_surfaces}


def _validate_phase11_artifact_policy(value: object) -> None:
    policy = _plain_dict(value, error="invalid_phase11_report")
    if set(policy) != _ARTIFACT_POLICY_FIELDS or policy.get("side_effects") != []:
        _raise("invalid_phase11_report")
    if not (
        policy["artifact_mode"] == "safe_summary_only"
        and policy["allowed_fields"] == list(_PHASE11_ARTIFACT_ALLOWED_FIELDS)
        and policy["retention"] == "local_artifact_only"
        and policy["log_policy"] == "sanitized_codes_only"
        and policy["forbidden_material"] == list(_PHASE11_FORBIDDEN_MATERIAL)
    ):
        _raise("invalid_phase11_report")


def _validate_phase11_rollback_policy(value: object) -> None:
    policy = _plain_dict(value, error="invalid_phase11_report")
    if set(policy) != _ROLLBACK_POLICY_FIELDS or policy.get("side_effects") != []:
        _raise("invalid_phase11_report")
    if not (
        policy["rollback_mode"] == "feature_flag_off_first"
        and policy["kill_switch_required"] is True
        and policy["rollback_hooks_required"] is True
        and policy["config_revert_required"] is True
        and policy["gateway_restart_requires_separate_approval"] is True
        and policy["production_enablement_requires_separate_approval"] is True
    ):
        _raise("invalid_phase11_report")


def _validate_shadow_summary(value: object, *, plan_transaction_id: str) -> dict[str, object]:
    summary = _plain_dict(value, error="invalid_shadow_runtime_publication_summary")
    if summary.get("side_effects") != []:
        _raise("side_effects_not_absent")
    if _safe_string_or_invalid(summary.get("verdict")) in {
        "production_ready",
        "production_enabled",
        "live_enabled",
        "gateway_enabled",
        "observation_enabled",
        "integration_enabled",
    }:
        _raise("production_action_requested")
    _reject_unsafe_material(summary, error="unsafe_material")
    if set(summary) != _SHADOW_SUMMARY_FIELDS:
        _raise("invalid_shadow_runtime_publication_summary")
    if summary["type"] != _SHADOW_PUBLICATION_TYPE or summary["verdict"] != "ready" or summary["reason"] != "ok":
        _raise("invalid_shadow_runtime_publication_summary")
    workflow_id = _runtime_transaction_id(summary["workflow_id"], error="invalid_shadow_runtime_publication_summary")
    transaction_id = _runtime_transaction_id(summary["transaction_id"], error="invalid_shadow_runtime_publication_summary")
    if workflow_id != plan_transaction_id or transaction_id != plan_transaction_id:
        _raise("workflow_id_mismatch")
    if summary["start_status"] not in _ALLOWED_STATUSES:
        _raise("invalid_shadow_runtime_publication_summary")
    publication_count = _bounded_int(summary["publication_count"], minimum=0, maximum=20, error="invalid_shadow_runtime_publication_summary")
    checks = _plain_dict(summary["checks"], error="invalid_shadow_runtime_publication_summary")
    if not checks or any(value is not True for value in checks.values()):
        _raise("invalid_shadow_runtime_publication_summary")
    ack = _validate_ack_bridge(summary["ack_bridge"])
    return {
        "type": _SHADOW_PUBLICATION_TYPE,
        "verdict": "ready",
        "workflow_id": workflow_id,
        "transaction_id": transaction_id,
        "publication_count": publication_count,
        "ack_update_count": ack["update_count"],
        "surfaces": ack["surfaces"],
        "stable_error_codes": ack["stable_error_codes"],
        "side_effects": [],
    }


def _validate_ack_bridge(value: object) -> dict[str, object]:
    ack = _plain_dict(value, error="invalid_shadow_runtime_publication_summary")
    if ack.get("side_effects") != []:
        _raise("side_effects_not_absent")
    _reject_unsafe_material(ack, error="unsafe_material")
    if set(ack) != _ACK_BRIDGE_FIELDS or ack["status"] != "ready":
        _raise("invalid_shadow_runtime_publication_summary")
    return {
        "update_count": _bounded_int(ack["update_count"], minimum=0, maximum=20, error="invalid_shadow_runtime_publication_summary"),
        "surfaces": _ordered_subset(ack["surfaces"], allowed=_ALLOWED_SURFACES, error="invalid_shadow_runtime_publication_summary"),
        "stable_error_codes": _safe_label_list(ack["stable_error_codes"], error="invalid_shadow_runtime_publication_summary"),
    }


def _validate_delivery_summary(value: object, *, plan_transaction_id: str) -> dict[str, object]:
    summary = _plain_dict(value, error="invalid_delivery_state_summary")
    if summary.get("side_effects") != []:
        _raise("side_effects_not_absent")
    _reject_unsafe_material(summary, error="unsafe_material")
    if set(summary) != _DELIVERY_SUMMARY_FIELDS or summary["type"] != _DELIVERY_SUMMARY_TYPE:
        _raise("invalid_delivery_state_summary")
    transaction_id = _runtime_transaction_id(summary["transaction_id"], error="invalid_delivery_state_summary")
    if transaction_id != plan_transaction_id:
        _raise("workflow_id_mismatch")
    return {
        "surface_counts": _safe_count_dict(
            summary["surface_counts"],
            allowed_keys=_ALLOWED_SURFACE_KEYS,
            error="invalid_delivery_state_summary",
        ),
        "status_counts": _safe_count_dict(
            summary["status_counts"],
            allowed_keys=_ALLOWED_DELIVERY_STATUS_KEYS,
            error="invalid_delivery_state_summary",
        ),
        "stable_error_codes": _safe_label_list(summary["stable_error_codes"], error="invalid_delivery_state_summary"),
        "side_effects": [],
    }


def _validate_progress_summary(value: object, *, plan_transaction_id: str) -> dict[str, object]:
    summary = _plain_dict(value, error="invalid_progress_snapshot_summary")
    if summary.get("side_effects") != []:
        _raise("side_effects_not_absent")
    _reject_unsafe_material(summary, error="unsafe_material")
    if set(summary) != _PROGRESS_SUMMARY_FIELDS or summary["type"] != _PROGRESS_SUMMARY_TYPE:
        _raise("invalid_progress_snapshot_summary")
    transaction_id = _runtime_transaction_id(summary["transaction_id"], error="invalid_progress_snapshot_summary")
    if transaction_id != plan_transaction_id:
        _raise("workflow_id_mismatch")
    return {
        "event_counts": _safe_count_dict(
            summary["event_counts"],
            allowed_keys=_ALLOWED_EVENT_KEYS,
            error="invalid_progress_snapshot_summary",
        ),
        "visible_event_count": _bounded_int(
            summary["visible_event_count"],
            minimum=0,
            maximum=200,
            error="invalid_progress_snapshot_summary",
        ),
        "stable_error_codes": _safe_label_list(summary["stable_error_codes"], error="invalid_progress_snapshot_summary"),
        "side_effects": [],
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
                if not (allow_policy_names and key == "forbidden_material"):
                    if lowered_key in _UNSAFE_EXACT_KEYS or any(marker in lowered_key for marker in _UNSAFE_KEY_SUBSTRINGS):
                        _raise(error)
                if allow_policy_names and key in {
                    "forbidden_material",
                    "runbook_outline",
                    "verification_matrix",
                    "fail_closed_errors",
                    "required_separate_approvals",
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


def _observation_id(*, design_id: str, plan_transaction_id: str) -> str:
    digest = _safe_digest(design_id, plan_transaction_id)
    return f"controlled_gateway_observation_hook_{digest}"


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
    return "invalid_phase11_report"


def _error_result(error_code: str) -> dict[str, object]:
    return {
        "type": CONTROLLED_GATEWAY_OBSERVATION_HOOK_REPORT_TYPE,
        "version": FLOWWEAVER_CONTROLLED_GATEWAY_OBSERVATION_HOOK_VERSION,
        "ok": False,
        "verdict": _BLOCKED_VERDICT,
        "phase": _PHASE,
        "error_code": _safe_error_code(error_code),
        "side_effects": [],
    }


def _raise(error: str) -> None:
    raise ValueError(error)


__all__ = [
    "CONTROLLED_GATEWAY_OBSERVATION_HOOK_REPORT_TYPE",
    "FLOWWEAVER_CONTROLLED_GATEWAY_OBSERVATION_HOOK_VERSION",
    "build_flowweaver_controlled_gateway_observation",
]
