"""Prototype-only controlled-shadow Phase 10 loop harness."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from flowweaver_runtime_client.gateway_shadow_e2e_loop import run_shadow_gateway_e2e_loop

FLOWWEAVER_CONTROLLED_SHADOW_PROTOTYPE_LOOP_VERSION = "flowweaver.controlled_shadow_prototype_loop.v0"
CONTROLLED_SHADOW_PROTOTYPE_RUN_POLICY_TYPE = "flowweaver.controlled_shadow_prototype_run_policy.v0"
CONTROLLED_SHADOW_PROTOTYPE_LOOP_REPORT_TYPE = "flowweaver.controlled_shadow_prototype_loop_report.v0"
CONTROLLED_SHADOW_PROTOTYPE_ARTIFACT_TYPE = "flowweaver.controlled_shadow_prototype_artifact.v0"

_PHASE = "phase10_controlled_shadow_prototype_loop"
_SUCCESS_VERDICT = "controlled_shadow_prototype_loop_verified"
_BLOCKED_VERDICT = "blocked"
_PHASE9_REPORT_TYPE = "flowweaver.controlled_shadow_plan.v0"
_PHASE9_VERSION = "flowweaver.controlled_shadow_design.v0"
_PHASE9_PHASE = "phase9_controlled_shadow_design"
_PHASE9_VERDICT = "ready_for_controlled_shadow_prototype"
_PHASE7_PUBLICATION_TYPE = "flowweaver.gateway.shadow_runtime_publication.v0"
_PHASE7_RUNTIME_MODEL_VERSION = "flowweaver.runtime.v0"
_PHASE7_RUNTIME_ENVELOPE_TYPE = "flowweaver.gateway.runtime_ingress_envelope.v0"
_PHASE7_READY = "ready"

_ALLOWED_SURFACES = ("final_text", "rich_card", "progress_card", "media")
_ALLOWED_RUNTIME_OPERATIONS = ("start_transaction", "query_transaction", "reconcile_delivery_ack")
_ALLOWED_ACK_STATUSES = ("sent", "failed", "acknowledged")
_ALLOWED_PHASE7_START_STATUSES = ("started", "running")
_ALLOWED_PHASE7_ACK_STATUSES = ("applied", "duplicate", "rejected")

_PHASE9_REPORT_FIELDS = {
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
}
_PHASE9_PLAN_FIELDS = {
    "plan_version",
    "source_kind",
    "mode",
    "allowed_surfaces",
    "max_transactions",
    "max_delivery_surfaces",
    "runtime_operations",
    "ack_source",
    "artifact_mode",
    "approval_refs",
    "rollback_hooks_required",
    "kill_switch_required",
    "forbidden_material",
    "fail_closed_errors",
}
_PHASE9_ARTIFACT_POLICY_FIELDS = {
    "artifact_mode",
    "allowed_fields",
    "retention",
    "log_policy",
    "forbidden_material",
}
_PHASE9_CHECKS = [
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
_PHASE9_RUNBOOK_OUTLINE = [
    "phase9_is_controlled_shadow_design_only",
    "prototype_shadow_requires_explicit_implementation_approval",
    "production_activation_requires_separate_design_and_approval",
    "keep_default_off_until_explicit_enablement",
    "rollback_and_kill_switch_required_before_any_wiring",
    "no_raw_payloads_or_secrets_in_reports_or_artifacts",
    "use_direct_pytest_for_integration_regression",
]
_PHASE9_FORBIDDEN_MATERIAL = [
    "raw_prompt",
    "raw_tool_output",
    "raw_card_json",
    "raw_media_payload",
    "raw_platform_payload",
    "platform_message_identifiers",
    "credentials_or_connection_strings",
    "raw_exception_text",
]
_PHASE9_FAIL_CLOSED_ERRORS = [
    "artifact_policy_violation",
    "invalid_artifact_policy",
    "invalid_gateway_observation_boundary",
    "invalid_readiness_report",
    "invalid_rollback_policy",
    "invalid_runtime_execution_boundary",
    "invalid_shadow_scope",
    "production_action_requested",
    "registry_or_config_write_requested",
    "runtime_lifecycle_requested",
    "side_effects_not_absent",
    "unsafe_material",
    "workflow_id_mismatch",
]
_REQUIRED_SEPARATE_APPROVALS = [
    "production_gateway_wiring",
    "production_config_write",
    "gateway_restart",
    "external_temporal_service",
    "real_send_edit_render_callback",
    "production_tool_registry",
    "remote_branch_or_worktree_cleanup",
]
_PHASE9_ALLOWED_ARTIFACT_FIELDS = [
    "run_id",
    "transaction_id",
    "operation_counts",
    "delivery_counts",
    "statuses",
    "digests",
    "stable_error_codes",
    "approvals",
    "side_effects",
]

_RUN_POLICY_FIELDS = {
    "type",
    "mode",
    "source_kind",
    "max_publications",
    "max_delivery_updates_per_publication",
    "control_surface_lifecycle",
    "gateway_effects_allowed",
    "temporal_lifecycle_allowed",
    "payload_carrying_signals_allowed",
    "artifact_mode",
    "log_policy",
    "side_effects",
}
_PUBLICATION_FIELDS = {
    "type",
    "verdict",
    "reason",
    "runtime_model_version",
    "runtime_envelope_type",
    "transaction_id",
    "workflow_id",
    "runtime_identity",
    "start_request",
    "ack_bridge",
    "checks",
    "side_effects",
}
_RUNTIME_IDENTITY_FIELDS = {"type", "strategy", "transaction_id", "workflow_id", "idempotency_key"}
_START_REQUEST_FIELDS = {"operation", "workflow_id", "start_payload"}
_PUBLICATION_CHECKS = {
    "shadow_capture_present",
    "dry_run_summary_valid",
    "runtime_envelope_valid",
    "start_request_safe",
    "delivery_ack_updates_safe",
    "payloads_absent",
    "visible_side_effects_absent",
    "runtime_side_effects_absent",
}
_ACK_BRIDGE_FIELDS = {"status", "updates"}
_ACK_UPDATE_FIELDS = {"event_type", "delivery_key", "surface", "target_kind", "target_id", "status"}

_VERIFICATION_MATRIX = [
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
_RUNBOOK_OUTLINE = [
    "phase10_proves_bounded_prototype_loop_only",
    "production_activation_requires_separate_design_and_approval",
    "keep_default_off_until_explicit_enablement",
    "caller_supplied_control_surface_only",
    "no_gateway_adapter_or_platform_payloads",
    "no_temporal_client_worker_" + "dock" + "er_or_service_lifecycle",
    "no_raw_payloads_or_secrets_in_reports_or_artifacts",
    "use_direct_pytest_for_integration_regression",
]
_SUCCESS_FIELDS = {
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
_LOOP_RESULT_FIELDS = {
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
_ARTIFACT_FIELDS = {
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
_ERROR_CODES = {
    "invalid_phase9_plan",
    "invalid_run_policy",
    "invalid_publication_fixture",
    "publication_limit_exceeded",
    "delivery_update_limit_exceeded",
    "control_surface_contract_violation",
    "phase7_loop_failed",
    "unsafe_material",
    "side_effects_not_absent",
    "production_action_requested",
    "runtime_lifecycle_requested",
    "registry_or_config_write_requested",
    "artifact_policy_violation",
    "workflow_id_mismatch",
}
_PRODUCTION_MARKERS = {
    "production_ready",
    "production_enabled",
    "live_enabled",
    "gateway_enabled",
    "live_gateway_stream",
    "production_gateway",
    "real_feishu",
    "real_sachima",
}
_PRODUCTION_ACTION_WORDS = {"send", "edit", "render", "callback"}
_RUNTIME_LIFECYCLE_EXTRA_KEYS = {
    "temporal_address",
    "namespace",
    "task_queue",
    "worker",
    "workflow_environment",
    "client_factory",
    "connect_helper",
    "subprocess",
    "dock" + "er",
    "dae" + "mon",
    "system" + "ctl",
    "service_lifecycle",
}
_REGISTRY_CONFIG_EXTRA_KEYS = {"registry_write", "config_write", "registry_writer", "config_writer"}
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
_UNSAFE_EXACT_KEYS = {"token", "secret"}
_UNSAFE_VALUE_MARKERS = (
    "raw_" + "prompt_payload_value",
    "platform_" + "payload_value",
    "card_" + "payload_value",
    "media_" + "path_value",
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
_INVALID = object()


async def run_flowweaver_controlled_shadow_prototype_loop(
    *,
    controlled_shadow_plan_report: object,
    publication_fixtures: object,
    control_surface: Any,
    run_policy: object,
) -> dict[str, object]:
    """Run a default-off controlled-shadow prototype loop over safe fixtures."""

    try:
        plan = _validate_phase9_plan_report(controlled_shadow_plan_report)
        policy = _validate_run_policy(run_policy, plan=plan)
        _validate_control_surface(control_surface)
        fixtures = _validate_publication_fixtures(publication_fixtures, plan=plan, policy=policy)
    except ValueError as exc:
        return _blocked_result(str(exc))

    loop_results: list[dict[str, object]] = []
    for publication in fixtures:
        phase7_result = await run_shadow_gateway_e2e_loop(control_surface, publication)
        if type(phase7_result) is not dict or phase7_result.get("ok") is not True:
            return _blocked_result(_map_phase7_error(phase7_result))
        try:
            loop_results.append(_summarize_phase7_result(phase7_result))
        except ValueError as exc:
            return _blocked_result(str(exc))

    return _success_result(plan=plan, loop_results=loop_results)


def _validate_phase9_plan_report(value: object) -> dict[str, object]:
    report = _plain_dict(value, error="invalid_phase9_plan")
    if report.get("side_effects") != []:
        _raise("side_effects_not_absent")
    if _contains_production_enablement(report.get("verdict")):
        _raise("production_action_requested")
    extra = set(report) - _PHASE9_REPORT_FIELDS
    if extra:
        _raise(_classify_extra_keys(extra, default="invalid_phase9_plan"))
    if set(report) != _PHASE9_REPORT_FIELDS:
        _raise("invalid_phase9_plan")
    if not (
        report["type"] == _PHASE9_REPORT_TYPE
        and report["version"] == _PHASE9_VERSION
        and report["ok"] is True
        and report["verdict"] == _PHASE9_VERDICT
        and report["phase"] == _PHASE9_PHASE
    ):
        _raise("invalid_phase9_plan")
    workflow_id = _runtime_transaction_id(report["workflow_id"], error="invalid_phase9_plan")
    transaction_id = _runtime_transaction_id(report["transaction_id"], error="invalid_phase9_plan")
    if workflow_id != transaction_id:
        _raise("workflow_id_mismatch")
    plan = _validate_controlled_shadow_plan(report["controlled_shadow_plan"])
    checks = _plain_dict(report["checks"], error="invalid_phase9_plan")
    if set(checks) != set(_PHASE9_CHECKS) or any(checks[key] is not True for key in _PHASE9_CHECKS):
        _raise("invalid_phase9_plan")
    artifact_policy = _validate_phase9_artifact_policy(report["artifact_policy"])
    approvals = _plain_string_list(report["required_separate_approvals"], error="invalid_phase9_plan")
    if approvals != list(_REQUIRED_SEPARATE_APPROVALS):
        _raise("invalid_phase9_plan")
    verification_matrix = _plain_string_list(report["verification_matrix"], error="invalid_phase9_plan")
    if any(_contains_production_enablement(item) for item in verification_matrix):
        _raise("production_action_requested")
    if verification_matrix != list(_PHASE9_CHECKS):
        _raise("invalid_phase9_plan")
    runbook_outline = _plain_string_list(report["runbook_outline"], error="invalid_phase9_plan")
    if runbook_outline != list(_PHASE9_RUNBOOK_OUTLINE):
        _raise("invalid_phase9_plan")
    return {
        "workflow_id": workflow_id,
        "transaction_id": transaction_id,
        "allowed_surfaces": plan["allowed_surfaces"],
        "max_transactions": plan["max_transactions"],
        "max_delivery_surfaces": plan["max_delivery_surfaces"],
        "runtime_operations": plan["runtime_operations"],
        "artifact_policy": artifact_policy,
        "required_separate_approvals": approvals,
    }


def _validate_controlled_shadow_plan(value: object) -> dict[str, object]:
    plan = _plain_dict(value, error="invalid_phase9_plan")
    extra = set(plan) - _PHASE9_PLAN_FIELDS
    if extra:
        _raise(_classify_extra_keys(extra, default="invalid_phase9_plan"))
    if set(plan) != _PHASE9_PLAN_FIELDS:
        _raise("invalid_phase9_plan")
    if plan["plan_version"] != _PHASE9_VERSION:
        _raise("invalid_phase9_plan")
    source_kind = _closed_string(
        plan["source_kind"],
        ("phase7_result_replay", "phase8_readiness_replay", "simulator_fixture"),
        error="invalid_phase9_plan",
    )
    mode = _closed_string(plan["mode"], ("design_only", "prototype_shadow_candidate"), error="invalid_phase9_plan")
    if _contains_production_enablement(source_kind) or _contains_production_enablement(mode):
        _raise("production_action_requested")
    allowed_surfaces = _ordered_subset(plan["allowed_surfaces"], _ALLOWED_SURFACES, error="invalid_phase9_plan")
    max_transactions = _bounded_int(plan["max_transactions"], minimum=1, maximum=20, error="invalid_phase9_plan")
    max_delivery_surfaces = _bounded_int(
        plan["max_delivery_surfaces"], minimum=0, maximum=20, error="invalid_phase9_plan"
    )
    if max_delivery_surfaces < len(allowed_surfaces):
        _raise("invalid_phase9_plan")
    runtime_operations = _ordered_subset(
        plan["runtime_operations"], _ALLOWED_RUNTIME_OPERATIONS, error="invalid_phase9_plan"
    )
    if runtime_operations != list(_ALLOWED_RUNTIME_OPERATIONS):
        _raise("invalid_phase9_plan")
    if plan["ack_source"] not in {"phase6_shadow_bridge", "simulator_ack_fixture"}:
        _raise("invalid_phase9_plan")
    if plan["artifact_mode"] != "safe_summary_only":
        _raise("artifact_policy_violation")
    approvals = _plain_dict(plan["approval_refs"], error="invalid_phase9_plan")
    if set(approvals) != {"operator_approval_ref", "feature_flag_ref"}:
        _raise("invalid_phase9_plan")
    _synthetic_id(approvals["operator_approval_ref"], prefixes=("approval_ref_",), error="invalid_phase9_plan")
    _synthetic_id(approvals["feature_flag_ref"], prefixes=("feature_flag_ref_",), error="invalid_phase9_plan")
    if plan["rollback_hooks_required"] is not True or plan["kill_switch_required"] is not True:
        _raise("invalid_phase9_plan")
    forbidden_material = _plain_string_list(plan["forbidden_material"], error="invalid_phase9_plan")
    if forbidden_material != list(_PHASE9_FORBIDDEN_MATERIAL):
        _raise("artifact_policy_violation")
    fail_closed_errors = _plain_string_list(plan["fail_closed_errors"], error="invalid_phase9_plan")
    if fail_closed_errors != list(_PHASE9_FAIL_CLOSED_ERRORS):
        _raise("invalid_phase9_plan")
    return {
        "allowed_surfaces": allowed_surfaces,
        "max_transactions": max_transactions,
        "max_delivery_surfaces": max_delivery_surfaces,
        "runtime_operations": runtime_operations,
    }


def _validate_phase9_artifact_policy(value: object) -> dict[str, object]:
    policy = _plain_dict(value, error="invalid_phase9_plan")
    if set(policy) != _PHASE9_ARTIFACT_POLICY_FIELDS:
        _raise("invalid_phase9_plan")
    if policy["artifact_mode"] != "safe_summary_only":
        _raise("artifact_policy_violation")
    allowed_fields = _plain_string_list(policy["allowed_fields"], error="invalid_phase9_plan")
    if not allowed_fields or allowed_fields != _ordered_intersection(allowed_fields, _PHASE9_ALLOWED_ARTIFACT_FIELDS):
        _raise("artifact_policy_violation")
    if policy["retention"] not in {"local_artifact_only", "docs_evidence_only"}:
        _raise("artifact_policy_violation")
    if policy["log_policy"] != "sanitized_codes_only":
        _raise("artifact_policy_violation")
    forbidden_material = _plain_string_list(policy["forbidden_material"], error="invalid_phase9_plan")
    if forbidden_material != list(_PHASE9_FORBIDDEN_MATERIAL):
        _raise("artifact_policy_violation")
    return dict(policy)


def _validate_run_policy(value: object, *, plan: dict[str, object]) -> dict[str, int]:
    policy = _plain_dict(value, error="invalid_run_policy")
    if policy.get("side_effects") != []:
        _raise("side_effects_not_absent")
    extra = set(policy) - _RUN_POLICY_FIELDS
    if extra:
        _raise(_classify_extra_keys(extra, default="invalid_run_policy"))
    if set(policy) != _RUN_POLICY_FIELDS:
        _raise("invalid_run_policy")
    if policy["type"] != CONTROLLED_SHADOW_PROTOTYPE_RUN_POLICY_TYPE:
        _raise("invalid_run_policy")
    mode = _safe_string(policy["mode"], error="invalid_run_policy")
    source_kind = _safe_string(policy["source_kind"], error="invalid_run_policy")
    if _contains_production_enablement(mode) or _contains_production_enablement(source_kind):
        _raise("production_action_requested")
    if mode != "prototype_loop_only" or source_kind != "sanitized_publication_fixture":
        _raise("invalid_run_policy")
    max_publications = _bounded_int(policy["max_publications"], minimum=1, maximum=20, error="invalid_run_policy")
    max_delivery_updates = _bounded_int(
        policy["max_delivery_updates_per_publication"], minimum=0, maximum=20, error="invalid_run_policy"
    )
    if max_publications > plan["max_transactions"] or max_delivery_updates > plan["max_delivery_surfaces"]:
        _raise("invalid_run_policy")
    if policy["control_surface_lifecycle"] != "caller_supplied_only":
        _raise("runtime_lifecycle_requested")
    if policy["gateway_effects_allowed"] is True:
        _raise("production_action_requested")
    if policy["temporal_lifecycle_allowed"] is True or policy["payload_carrying_signals_allowed"] is True:
        _raise("runtime_lifecycle_requested")
    if policy["gateway_effects_allowed"] is not False:
        _raise("invalid_run_policy")
    if policy["temporal_lifecycle_allowed"] is not False or policy["payload_carrying_signals_allowed"] is not False:
        _raise("invalid_run_policy")
    if policy["artifact_mode"] != "safe_summary_only":
        _raise("artifact_policy_violation")
    if policy["log_policy"] != "sanitized_codes_only":
        _raise("invalid_run_policy")
    return {"max_publications": max_publications, "max_delivery_updates_per_publication": max_delivery_updates}


def _validate_control_surface(control_surface: object) -> None:
    handle = getattr(control_surface, "handle", None)
    if handle is None or not callable(handle):
        _raise("control_surface_contract_violation")


def _validate_publication_fixtures(
    value: object, *, plan: dict[str, object], policy: dict[str, int]
) -> list[dict[str, object]]:
    fixtures = _plain_list(value, error="invalid_publication_fixture")
    if not fixtures:
        _raise("invalid_publication_fixture")
    if len(fixtures) > policy["max_publications"] or len(fixtures) > plan["max_transactions"]:
        _raise("publication_limit_exceeded")
    return [_validate_publication_fixture(item, plan=plan, policy=policy) for item in fixtures]


def _validate_publication_fixture(
    value: object, *, plan: dict[str, object], policy: dict[str, int]
) -> dict[str, object]:
    publication = _plain_dict(value, error="invalid_publication_fixture")
    if publication.get("side_effects") != []:
        _raise("side_effects_not_absent")
    _reject_unsafe_material(publication, error="invalid_publication_fixture", allow_start_contract=True)
    if set(publication) != _PUBLICATION_FIELDS:
        _raise("invalid_publication_fixture")
    if not (
        publication["type"] == _PHASE7_PUBLICATION_TYPE
        and publication["verdict"] == _PHASE7_READY
        and publication["reason"] == "ok"
        and publication["runtime_model_version"] == _PHASE7_RUNTIME_MODEL_VERSION
        and publication["runtime_envelope_type"] == _PHASE7_RUNTIME_ENVELOPE_TYPE
    ):
        _raise("invalid_publication_fixture")
    workflow_id = _runtime_transaction_id(publication["workflow_id"], error="invalid_publication_fixture")
    transaction_id = _runtime_transaction_id(publication["transaction_id"], error="invalid_publication_fixture")
    if workflow_id != transaction_id:
        _raise("workflow_id_mismatch")
    _validate_runtime_identity(publication["runtime_identity"], workflow_id=workflow_id)
    start_contract = _validate_start_request(publication["start_request"], workflow_id=workflow_id)
    checks = _plain_dict(publication["checks"], error="invalid_publication_fixture")
    if set(checks) != _PUBLICATION_CHECKS or any(checks[key] is not True for key in _PUBLICATION_CHECKS):
        _raise("invalid_publication_fixture")
    ack_count = _validate_ack_bridge(
        publication["ack_bridge"],
        allowed_surfaces=plan["allowed_surfaces"],
        delivery_count=start_contract["delivery_count"],
    )
    if ack_count > policy["max_delivery_updates_per_publication"] or ack_count > plan["max_delivery_surfaces"]:
        _raise("delivery_update_limit_exceeded")
    return publication


def _validate_runtime_identity(value: object, *, workflow_id: str) -> None:
    identity = _plain_dict(value, error="invalid_publication_fixture")
    if set(identity) != _RUNTIME_IDENTITY_FIELDS:
        _raise("invalid_publication_fixture")
    if not (
        identity["type"] == "flowweaver.gateway.runtime_identity.v0"
        and identity["strategy"] == "shadow_ref_hash_v0"
        and identity["transaction_id"] == workflow_id
        and identity["workflow_id"] == workflow_id
    ):
        _raise("invalid_publication_fixture")
    _synthetic_id(identity["idempotency_key"], prefixes=("runtime_event_",), error="invalid_publication_fixture")


def _validate_start_request(value: object, *, workflow_id: str) -> dict[str, int]:
    request = _plain_dict(value, error="invalid_publication_fixture")
    if set(request) != _START_REQUEST_FIELDS:
        _raise("invalid_publication_fixture")
    if request["operation"] != "start_transaction" or request["workflow_id"] != workflow_id:
        _raise("invalid_publication_fixture")
    payload = _plain_dict(request["start_payload"], error="invalid_publication_fixture")
    if payload.get("transaction_id") != workflow_id:
        _raise("workflow_id_mismatch")
    record_counts = _plain_dict(payload.get("record_counts"), error="invalid_publication_fixture")
    delivery_count = _bounded_int(record_counts.get("deliveries"), minimum=0, maximum=20, error="invalid_publication_fixture")
    return {"delivery_count": delivery_count}


def _validate_ack_bridge(value: object, *, allowed_surfaces: list[str], delivery_count: int) -> int:
    bridge = _plain_dict(value, error="invalid_publication_fixture")
    if set(bridge) != _ACK_BRIDGE_FIELDS or bridge["status"] != "ready":
        _raise("invalid_publication_fixture")
    updates = _plain_list(bridge["updates"], error="invalid_publication_fixture")
    if len(updates) > 20:
        _raise("delivery_update_limit_exceeded")
    for update in updates:
        descriptor = _plain_string_dict(update, error="invalid_publication_fixture")
        if set(descriptor) != _ACK_UPDATE_FIELDS:
            _raise("invalid_publication_fixture")
        if descriptor["event_type"] != "record_delivery_ack":
            _raise("invalid_publication_fixture")
        _synthetic_id(descriptor["delivery_key"], prefixes=("runtime_event_",), error="invalid_publication_fixture")
        _closed_string(descriptor["surface"], tuple(allowed_surfaces), error="invalid_publication_fixture")
        _closed_string(descriptor["target_kind"], ("delivery",), error="invalid_publication_fixture")
        target_id = _synthetic_id(
            descriptor["target_id"], prefixes=("runtime_delivery_",), error="invalid_publication_fixture"
        )
        _validate_initialized_delivery_target(target_id, delivery_count=delivery_count)
        _closed_string(descriptor["status"], _ALLOWED_ACK_STATUSES, error="invalid_publication_fixture")
    return len(updates)


def _validate_initialized_delivery_target(target_id: str, *, delivery_count: int) -> None:
    suffix = target_id.removeprefix("runtime_delivery_")
    if not suffix.isdigit():
        _raise("invalid_publication_fixture")
    index = int(suffix)
    if suffix != str(index) or index >= delivery_count:
        _raise("invalid_publication_fixture")


def _summarize_phase7_result(result: dict[str, object]) -> dict[str, object]:
    workflow_id = _runtime_transaction_id(result.get("workflow_id"), error="phase7_loop_failed")
    transaction_id = _runtime_transaction_id(result.get("transaction_id"), error="phase7_loop_failed")
    if workflow_id != transaction_id:
        _raise("workflow_id_mismatch")
    start_status = _closed_string(result.get("start_status"), _ALLOWED_PHASE7_START_STATUSES, error="phase7_loop_failed")
    ack_items = _plain_list(result.get("ack_results"), error="phase7_loop_failed")
    surfaces: list[str] = []
    status_counts: dict[str, int] = {start_status: 1}
    delivery_counts: dict[str, int] = {"total": len(ack_items)}
    digest_parts = [workflow_id, transaction_id, start_status, str(len(ack_items))]
    for item in ack_items:
        ack = _plain_dict(item, error="phase7_loop_failed")
        if set(ack) != {"target_id", "surface", "status", "ack_status"}:
            _raise("phase7_loop_failed")
        _synthetic_id(ack["target_id"], prefixes=("runtime_delivery_",), error="phase7_loop_failed")
        surface = _closed_string(ack["surface"], _ALLOWED_SURFACES, error="phase7_loop_failed")
        delivery_status = _closed_string(ack["status"], _ALLOWED_ACK_STATUSES, error="phase7_loop_failed")
        ack_status = _closed_string(ack["ack_status"], _ALLOWED_PHASE7_ACK_STATUSES, error="phase7_loop_failed")
        if surface not in surfaces:
            surfaces.append(surface)
        status_counts[f"ack_{ack_status}"] = status_counts.get(f"ack_{ack_status}", 0) + 1
        delivery_counts[delivery_status] = delivery_counts.get(delivery_status, 0) + 1
        digest_parts.extend([surface, delivery_status, ack_status])
    ordered_surfaces = [surface for surface in _ALLOWED_SURFACES if surface in surfaces]
    summary = {
        "workflow_id": workflow_id,
        "transaction_id": transaction_id,
        "start_status": start_status,
        "ack_count": len(ack_items),
        "surfaces": ordered_surfaces,
        "status_counts": status_counts,
        "delivery_counts": delivery_counts,
        "stable_error_codes": [],
        "safe_digest": sha256("|".join(digest_parts).encode("utf-8")).hexdigest()[:16],
        "side_effects": [],
    }
    _assert_loop_result(summary)
    return summary


def _success_result(*, plan: dict[str, object], loop_results: list[dict[str, object]]) -> dict[str, object]:
    run_id = "controlled_shadow_run_" + plan["transaction_id"].removeprefix("runtime_tx_")
    status_counts: dict[str, int] = {}
    delivery_counts: dict[str, int] = {"total": 0}
    digests: list[str] = []
    for item in loop_results:
        for key, count in item["status_counts"].items():
            status_counts[key] = status_counts.get(key, 0) + count
        for key, count in item["delivery_counts"].items():
            delivery_counts[key] = delivery_counts.get(key, 0) + count
        digests.append(item["safe_digest"])
    report = {
        "type": CONTROLLED_SHADOW_PROTOTYPE_LOOP_REPORT_TYPE,
        "version": FLOWWEAVER_CONTROLLED_SHADOW_PROTOTYPE_LOOP_VERSION,
        "ok": True,
        "verdict": _SUCCESS_VERDICT,
        "phase": _PHASE,
        "run_id": run_id,
        "plan_transaction_id": plan["transaction_id"],
        "publication_count": len(loop_results),
        "loop_results": [dict(item) for item in loop_results],
        "artifact": {
            "type": CONTROLLED_SHADOW_PROTOTYPE_ARTIFACT_TYPE,
            "artifact_mode": "safe_summary_only",
            "run_id": run_id,
            "plan_transaction_id": plan["transaction_id"],
            "publication_count": len(loop_results),
            "operation_counts": {"phase7_loop": len(loop_results)},
            "delivery_counts": delivery_counts,
            "statuses": status_counts,
            "digests": list(digests),
            "stable_error_codes": [],
            "approvals": list(plan["required_separate_approvals"]),
            "side_effects": [],
        },
        "checks": {key: True for key in _VERIFICATION_MATRIX},
        "required_separate_approvals": list(plan["required_separate_approvals"]),
        "verification_matrix": list(_VERIFICATION_MATRIX),
        "runbook_outline": list(_RUNBOOK_OUTLINE),
        "side_effects": [],
    }
    _assert_success_report(report)
    return report


def _blocked_result(error_code: object) -> dict[str, object]:
    safe_code = error_code if type(error_code) is str and error_code in _ERROR_CODES else "invalid_phase9_plan"
    return {
        "type": CONTROLLED_SHADOW_PROTOTYPE_LOOP_REPORT_TYPE,
        "version": FLOWWEAVER_CONTROLLED_SHADOW_PROTOTYPE_LOOP_VERSION,
        "ok": False,
        "verdict": _BLOCKED_VERDICT,
        "phase": _PHASE,
        "error_code": safe_code,
        "side_effects": [],
    }


def _map_phase7_error(value: object) -> str:
    if type(value) is not dict:
        return "phase7_loop_failed"
    code = value.get("error_code")
    if code in {"invalid_publication", "invalid_start_payload", "invalid_delivery_plan"}:
        return "invalid_publication_fixture"
    if code == "workflow_id_mismatch":
        return "workflow_id_mismatch"
    return "phase7_loop_failed"


def _assert_success_report(report: dict[str, object]) -> None:
    if set(report) != _SUCCESS_FIELDS:
        raise RuntimeError("unsafe_output")
    artifact = report["artifact"]
    if type(artifact) is not dict or set(artifact) != _ARTIFACT_FIELDS:
        raise RuntimeError("unsafe_output")
    for item in report["loop_results"]:
        _assert_loop_result(item)
    _assert_no_forbidden_rendered_material(report)


def _assert_loop_result(result: dict[str, object]) -> None:
    if set(result) != _LOOP_RESULT_FIELDS:
        raise RuntimeError("unsafe_output")
    _assert_no_forbidden_rendered_material(result)


def _plain_copy(value: object) -> object:
    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is list:
        copied_list: list[object] = []
        for item in value:
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            copied_list.append(copied)
        return copied_list
    if type(value) is tuple:
        copied_tuple: list[object] = []
        for item in value:
            copied = _plain_copy(item)
            if copied is _INVALID:
                return _INVALID
            copied_tuple.append(copied)
        return copied_tuple
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


def _plain_string_dict(value: object, *, error: str) -> dict[str, str]:
    copied = _plain_dict(value, error=error)
    if not all(type(key) is str and type(item) is str for key, item in copied.items()):
        _raise(error)
    return {key: item for key, item in copied.items() if type(item) is str}


def _safe_string(value: object, *, error: str) -> str:
    if type(value) is not str:
        _raise(error)
    return value


def _bounded_int(value: object, *, minimum: int, maximum: int, error: str) -> int:
    if type(value) is not int or value < minimum or value > maximum:
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


def _closed_string(value: object, allowed: tuple[str, ...], *, error: str) -> str:
    if type(value) is not str or value not in allowed:
        _raise(error)
    return value


def _ordered_subset(value: object, allowed: tuple[str, ...], *, error: str) -> list[str]:
    items = _plain_string_list(value, error=error)
    if not items or len(set(items)) != len(items):
        _raise(error)
    if items != [item for item in allowed if item in items]:
        _raise(error)
    return items


def _ordered_intersection(values: list[str], allowed: list[str]) -> list[str]:
    if any(value not in set(allowed) for value in values):
        return []
    if values != [item for item in allowed if item in values]:
        return []
    return list(values)


def _classify_extra_keys(keys: set[str], *, default: str) -> str:
    lowered = {key.lower() for key in keys}
    if lowered & _REGISTRY_CONFIG_EXTRA_KEYS:
        return "registry_or_config_write_requested"
    if lowered & _RUNTIME_LIFECYCLE_EXTRA_KEYS:
        return "runtime_lifecycle_requested"
    if any(_contains_production_enablement(key) for key in lowered):
        return "production_action_requested"
    if any(key in _UNSAFE_EXACT_KEYS or any(marker in key for marker in _UNSAFE_KEY_SUBSTRINGS) for key in lowered):
        return "unsafe_material"
    return default


def _contains_production_enablement(value: object) -> bool:
    if type(value) is not str:
        return False
    lowered = value.lower()
    return lowered in _PRODUCTION_MARKERS or lowered in _PRODUCTION_ACTION_WORDS


def _reject_unsafe_material(
    value: object,
    *,
    error: str,
    allow_start_contract: bool = False,
    path: tuple[str, ...] = (),
) -> None:
    if allow_start_contract and path == ("start_request", "start_payload", "claim_check_policy", "forbidden_material"):
        return
    if type(value) is dict:
        for key, item in value.items():
            lowered = key.lower()
            if not (
                allow_start_contract
                and path == ("start_request", "start_payload", "claim_check_policy")
                and key == "forbidden_material"
            ):
                if lowered in _UNSAFE_EXACT_KEYS or any(marker in lowered for marker in _UNSAFE_KEY_SUBSTRINGS):
                    _raise(error)
            _reject_unsafe_material(item, error=error, allow_start_contract=allow_start_contract, path=path + (key,))
        return
    if type(value) is list:
        for item in value:
            _reject_unsafe_material(item, error=error, allow_start_contract=allow_start_contract, path=path)
        return
    if type(value) is str:
        lowered = value.lower()
        if any(lowered.startswith(prefix) for prefix in _PRIVATE_PREFIXES):
            _raise(error)
        if any(marker in lowered for marker in _UNSAFE_VALUE_MARKERS):
            _raise(error)


def _assert_no_forbidden_rendered_material(value: object) -> None:
    rendered = repr(value).lower()
    forbidden = (
        "allowed_runtime_events",
        "claim_check_policy",
        "forbidden_material",
        "raw_" + "prompt_payload_value",
        "platform_" + "payload_value",
        "card_" + "payload_value",
        "media_" + "path_value",
        "production_ready",
        "production_enabled",
        "live_enabled",
        "gateway_enabled",
        "raw exception",
        "unsafe-" + "token",
        "bearer ",
        "postgres://",
        "oc_" + "phase10_private_chat",
        "ou_" + "phase10_private_user",
    )
    for marker in forbidden:
        if marker in rendered:
            raise RuntimeError("unsafe_output")


def _raise(code: str) -> None:
    raise ValueError(code)


__all__ = [
    "FLOWWEAVER_CONTROLLED_SHADOW_PROTOTYPE_LOOP_VERSION",
    "CONTROLLED_SHADOW_PROTOTYPE_RUN_POLICY_TYPE",
    "CONTROLLED_SHADOW_PROTOTYPE_LOOP_REPORT_TYPE",
    "CONTROLLED_SHADOW_PROTOTYPE_ARTIFACT_TYPE",
    "run_flowweaver_controlled_shadow_prototype_loop",
]
