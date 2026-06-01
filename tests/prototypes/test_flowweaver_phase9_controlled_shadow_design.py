"""RED contract tests for FlowWeaver Phase 9 controlled-shadow design gate."""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE5C_SRC = ROOT / "prototypes" / "flowweaver_phase5c_runtime_client" / "src"
if str(PHASE5C_SRC) not in sys.path:
    sys.path.insert(0, str(PHASE5C_SRC))

WORKFLOW_ID = "runtime_tx_phase9_controlled_shadow"
REQUIRED_APPROVALS_IN_PHASE8_ORDER = [
    "production_gateway_wiring",
    "production_config_write",
    "gateway_restart",
    "external_temporal_service",
    "real_send_edit_render_callback",
    "production_tool_registry",
    "remote_branch_or_worktree_cleanup",
]
REQUIRED_APPROVALS = set(REQUIRED_APPROVALS_IN_PHASE8_ORDER)
REPORT_FIELDS = {
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
ERROR_CODES = {
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
FORBIDDEN_OUTPUT_VALUES = (
    "production_enabled",
    "live_enabled",
    "oc_phase9_private_chat",
    "ou_phase9_private_user",
    "raw_prompt_payload_value",
    "platform_payload_value",
    "card_payload_value",
    "media_path_value",
    "https://example.invalid/callback?access_" + "token=phase9",
    "postgres" + "://phase9.invalid/db",
    "unsafe-" + "token" + "-phase9",
    "Bearer " + "phase9secretvalue0000000000",
)
PHASE8_ERROR_CODES = {
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
FORBIDDEN_MATERIAL = [
    "raw_prompt",
    "raw_tool_output",
    "raw_card_json",
    "raw_media_payload",
    "raw_platform_payload",
    "platform_message_identifiers",
    "credentials_or_connection_strings",
    "raw_exception_text",
]


class HostileReadinessReport(dict):
    pass


def import_design_module():
    return importlib.import_module("flowweaver_runtime_client.controlled_shadow_design")


def safe_readiness_report() -> dict[str, object]:
    return {
        "type": "flowweaver.production_readiness_report.v0",
        "version": "flowweaver.production_readiness_gate.v0",
        "ok": True,
        "verdict": "ready_for_controlled_shadow_design",
        "phase": "phase8_production_readiness_gate",
        "workflow_id": WORKFLOW_ID,
        "transaction_id": WORKFLOW_ID,
        "candidate_contract": {
            "contract_version": "flowweaver.controlled_shadow_candidate.v0",
            "runtime_operations": ["start_transaction", "query_transaction", "reconcile_delivery_ack"],
            "ack_bridge_version": "flowweaver.gateway_ack_shadow_bridge.v0",
            "shadow_loop_version": "flowweaver.gateway_shadow_e2e_loop.v0",
            "allowed_surfaces": ["final_text", "rich_card"],
            "forbidden_material": FORBIDDEN_MATERIAL[:-1],
            "fail_closed_errors": sorted(PHASE8_ERROR_CODES),
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
        "required_separate_approvals": list(REQUIRED_APPROVALS_IN_PHASE8_ORDER),
        "runbook_outline": [
            "phase8_proves_readiness_only",
            "production_activation_requires_separate_design_and_approval",
            "keep_default_off_until_explicit_enablement",
            "rollback_plan_required_before_gateway_wiring",
            "no_raw_payloads_or_secrets_in_reports_or_runtime_history",
            "use_direct_pytest_for_integration_regression",
        ],
        "side_effects": [],
    }


def safe_shadow_scope() -> dict[str, object]:
    return {
        "type": "flowweaver.controlled_shadow_scope.v0",
        "mode": "prototype_shadow_candidate",
        "source_kind": "phase8_readiness_replay",
        "max_transactions": 3,
        "max_delivery_surfaces": 2,
        "allowed_surfaces": ["final_text", "rich_card"],
        "operator_approval_ref": "approval_ref_phase9_design_approved",
        "feature_flag_ref": "feature_flag_ref_phase9_controlled_shadow_off",
        "side_effects": [],
    }


def safe_gateway_observation_boundary() -> dict[str, object]:
    return {
        "type": "flowweaver.gateway_observation_boundary.v0",
        "observation_mode": "sanitized_replay_only",
        "inbound_material": "sanitized_refs_only",
        "outbound_effects": "none",
        "adapter_imports_allowed": False,
        "platform_payloads_allowed": False,
        "message_identifiers_allowed": False,
        "ack_source": "phase6_shadow_bridge",
        "side_effects": [],
    }


def safe_runtime_execution_boundary() -> dict[str, object]:
    return {
        "type": "flowweaver.runtime_execution_boundary.v0",
        "control_surface": "phase5k_control_surface",
        "client_lifecycle": "caller_supplied_only",
        "temporal_dependency": "optional_extra_only",
        "event_ingress": "validated_updates_only",
        "allowed_operations": ["start_transaction", "query_transaction", "reconcile_delivery_ack"],
        "worker_lifecycle": "none",
        "side_effects": [],
    }


def safe_artifact_policy() -> dict[str, object]:
    return {
        "type": "flowweaver.controlled_shadow_artifact_policy.v0",
        "artifact_mode": "safe_summary_only",
        "allowed_fields": [
            "run_id",
            "transaction_id",
            "operation_counts",
            "delivery_counts",
            "statuses",
            "digests",
            "stable_error_codes",
            "approvals",
            "side_effects",
        ],
        "forbidden_material": list(FORBIDDEN_MATERIAL),
        "retention": "local_artifact_only",
        "log_policy": "sanitized_codes_only",
        "side_effects": [],
    }


def safe_rollback_policy() -> dict[str, object]:
    return {
        "type": "flowweaver.controlled_shadow_rollback_policy.v0",
        "default_state": "off",
        "kill_switch_required": True,
        "rollback_plan_required": True,
        "production_actions_require_separate_approval": True,
        "config_write_allowed": False,
        "registry_write_allowed": False,
        "gateway_restart_allowed": False,
        "service_lifecycle_allowed": False,
        "side_effects": [],
    }


def build(
    *,
    readiness_report: object | None = None,
    shadow_scope: object | None = None,
    gateway_observation_boundary: object | None = None,
    runtime_execution_boundary: object | None = None,
    artifact_policy: object | None = None,
    rollback_policy: object | None = None,
) -> dict[str, object]:
    module = import_design_module()
    return module.build_flowweaver_controlled_shadow_plan(
        readiness_report=safe_readiness_report() if readiness_report is None else readiness_report,
        shadow_scope=safe_shadow_scope() if shadow_scope is None else shadow_scope,
        gateway_observation_boundary=(
            safe_gateway_observation_boundary()
            if gateway_observation_boundary is None
            else gateway_observation_boundary
        ),
        runtime_execution_boundary=(
            safe_runtime_execution_boundary() if runtime_execution_boundary is None else runtime_execution_boundary
        ),
        artifact_policy=safe_artifact_policy() if artifact_policy is None else artifact_policy,
        rollback_policy=safe_rollback_policy() if rollback_policy is None else rollback_policy,
    )


def assert_safe_report_shape(result: dict[str, object]) -> None:
    assert type(result) is dict
    assert set(result) <= REPORT_FIELDS
    assert result["type"] == "flowweaver.controlled_shadow_plan.v0"
    assert result["version"] == "flowweaver.controlled_shadow_design.v0"
    assert result["phase"] == "phase9_controlled_shadow_design"
    assert result["side_effects"] == []


def assert_error(result: dict[str, object], code: str) -> None:
    assert_safe_report_shape(result)
    assert result["ok"] is False
    assert result["verdict"] == "blocked"
    assert result["error_code"] == code
    assert code in ERROR_CODES
    assert "controlled_shadow_plan" not in result
    rendered = repr(result)
    for forbidden in FORBIDDEN_OUTPUT_VALUES:
        assert forbidden not in rendered


def test_phase9_design_import_is_default_off_sync_pure_and_narrow() -> None:
    for module_name in (
        "flowweaver_runtime_client.controlled_shadow_design",
        "gateway",
        "gateway.run",
        "gateway.platforms.feishu",
        "mcp",
        "tools.registry",
        "hermes_cli.platforms",
        "toolsets",
        "flowweaver_temporal_poc.client",
        "flowweaver_temporal_poc.workflows",
    ):
        sys.modules.pop(module_name, None)
    for module_name in list(sys.modules):
        if module_name == "temporalio" or module_name.startswith("temporalio."):
            sys.modules.pop(module_name, None)

    module = import_design_module()

    assert module.FLOWWEAVER_CONTROLLED_SHADOW_DESIGN_VERSION == "flowweaver.controlled_shadow_design.v0"
    assert module.CONTROLLED_SHADOW_SCOPE_DESCRIPTOR_TYPE == "flowweaver.controlled_shadow_scope.v0"
    assert module.GATEWAY_OBSERVATION_BOUNDARY_TYPE == "flowweaver.gateway_observation_boundary.v0"
    assert module.RUNTIME_EXECUTION_BOUNDARY_TYPE == "flowweaver.runtime_execution_boundary.v0"
    assert module.CONTROLLED_SHADOW_ARTIFACT_POLICY_TYPE == "flowweaver.controlled_shadow_artifact_policy.v0"
    assert module.CONTROLLED_SHADOW_ROLLBACK_POLICY_TYPE == "flowweaver.controlled_shadow_rollback_policy.v0"
    assert module.CONTROLLED_SHADOW_PLAN_TYPE == "flowweaver.controlled_shadow_plan.v0"
    assert not inspect.iscoroutinefunction(module.build_flowweaver_controlled_shadow_plan)
    signature = inspect.signature(module.build_flowweaver_controlled_shadow_plan)
    assert list(signature.parameters) == [
        "readiness_report",
        "shadow_scope",
        "gateway_observation_boundary",
        "runtime_execution_boundary",
        "artifact_policy",
        "rollback_policy",
    ]
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())
    assert sorted(module.__all__) == [
        "CONTROLLED_SHADOW_ARTIFACT_POLICY_TYPE",
        "CONTROLLED_SHADOW_PLAN_TYPE",
        "CONTROLLED_SHADOW_ROLLBACK_POLICY_TYPE",
        "CONTROLLED_SHADOW_SCOPE_DESCRIPTOR_TYPE",
        "FLOWWEAVER_CONTROLLED_SHADOW_DESIGN_VERSION",
        "GATEWAY_OBSERVATION_BOUNDARY_TYPE",
        "RUNTIME_EXECUTION_BOUNDARY_TYPE",
        "build_flowweaver_controlled_shadow_plan",
    ]
    assert "temporalio" not in sys.modules
    assert "mcp" not in sys.modules
    assert "tools.registry" not in sys.modules
    assert "hermes_cli.platforms" not in sys.modules
    assert "toolsets" not in sys.modules
    assert "gateway" not in sys.modules
    assert "gateway.run" not in sys.modules
    assert "gateway.platforms.feishu" not in sys.modules
    assert "flowweaver_temporal_poc.client" not in sys.modules
    assert "flowweaver_temporal_poc.workflows" not in sys.modules


def test_phase9_design_returns_controlled_shadow_plan_for_exact_phase8_report_and_descriptors() -> None:
    result = build()

    assert_safe_report_shape(result)
    assert result["ok"] is True
    assert result["verdict"] == "ready_for_controlled_shadow_prototype"
    assert result["workflow_id"] == WORKFLOW_ID
    assert result["transaction_id"] == WORKFLOW_ID
    assert set(result["required_separate_approvals"]) == REQUIRED_APPROVALS
    assert result["checks"] == {
        "phase8_report_exact_shape": True,
        "scope_default_off": True,
        "gateway_observation_only": True,
        "runtime_lifecycle_free": True,
        "validated_updates_only": True,
        "artifact_safe_summary_only": True,
        "rollback_and_kill_switch_present": True,
        "production_actions_separate": True,
        "side_effects_absent": True,
    }
    assert result["controlled_shadow_plan"] == {
        "plan_version": "flowweaver.controlled_shadow_design.v0",
        "source_kind": "phase8_readiness_replay",
        "mode": "prototype_shadow_candidate",
        "allowed_surfaces": ["final_text", "rich_card"],
        "max_transactions": 3,
        "max_delivery_surfaces": 2,
        "runtime_operations": ["start_transaction", "query_transaction", "reconcile_delivery_ack"],
        "ack_source": "phase6_shadow_bridge",
        "artifact_mode": "safe_summary_only",
        "approval_refs": {
            "operator_approval_ref": "approval_ref_phase9_design_approved",
            "feature_flag_ref": "feature_flag_ref_phase9_controlled_shadow_off",
        },
        "rollback_hooks_required": True,
        "kill_switch_required": True,
        "forbidden_material": list(FORBIDDEN_MATERIAL),
        "fail_closed_errors": sorted(ERROR_CODES),
    }
    assert result["artifact_policy"] == {
        "artifact_mode": "safe_summary_only",
        "allowed_fields": safe_artifact_policy()["allowed_fields"],
        "retention": "local_artifact_only",
        "log_policy": "sanitized_codes_only",
        "forbidden_material": list(FORBIDDEN_MATERIAL),
    }
    assert result["verification_matrix"] == [
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
    assert result["runbook_outline"] == [
        "phase9_is_controlled_shadow_design_only",
        "prototype_shadow_requires_explicit_implementation_approval",
        "production_activation_requires_separate_design_and_approval",
        "keep_default_off_until_explicit_enablement",
        "rollback_and_kill_switch_required_before_any_wiring",
        "no_raw_payloads_or_secrets_in_reports_or_artifacts",
        "use_direct_pytest_for_integration_regression",
    ]
    rendered = repr(result)
    assert "production_enabled" not in rendered
    assert "live_enabled" not in rendered


def test_phase9_design_rejects_non_exact_phase8_readiness_reports() -> None:
    invalid_cases: list[tuple[dict[str, object], str]] = []

    ok_false = safe_readiness_report()
    ok_false["ok"] = False
    ok_false["verdict"] = "blocked"
    invalid_cases.append((ok_false, "invalid_readiness_report"))

    wrong_verdict = safe_readiness_report()
    wrong_verdict["verdict"] = "ready_for_controlled_shadow_prototype"
    invalid_cases.append((wrong_verdict, "invalid_readiness_report"))

    missing_check = safe_readiness_report()
    del missing_check["checks"]["delivery_targets_match_snapshot"]
    invalid_cases.append((missing_check, "invalid_readiness_report"))

    side_effects = safe_readiness_report()
    side_effects["side_effects"] = ["would_send"]
    invalid_cases.append((side_effects, "side_effects_not_absent"))

    mismatch = safe_readiness_report()
    mismatch["transaction_id"] = "runtime_tx_phase9_other"
    invalid_cases.append((mismatch, "workflow_id_mismatch"))

    missing_candidate_field = safe_readiness_report()
    del missing_candidate_field["candidate_contract"]["ack_bridge_version"]
    invalid_cases.append((missing_candidate_field, "invalid_readiness_report"))

    broadened_operation = safe_readiness_report()
    broadened_operation["candidate_contract"]["runtime_operations"] = [
        "start_transaction",
        "query_transaction",
        "reconcile_delivery_ack",
        "execute_live_gateway_delivery",
    ]
    invalid_cases.append((broadened_operation, "invalid_readiness_report"))

    missing_approval = safe_readiness_report()
    missing_approval["required_separate_approvals"] = ["production_gateway_wiring"]
    invalid_cases.append((missing_approval, "invalid_readiness_report"))

    duplicate_approval = safe_readiness_report()
    duplicate_approval["required_separate_approvals"] = list(REQUIRED_APPROVALS_IN_PHASE8_ORDER) + [
        "gateway_restart"
    ]
    invalid_cases.append((duplicate_approval, "invalid_readiness_report"))

    wrong_runbook = safe_readiness_report()
    wrong_runbook["runbook_outline"] = ["phase8_proves_readiness_only", "custom_step"]
    invalid_cases.append((wrong_runbook, "invalid_readiness_report"))

    unsafe_runbook = safe_readiness_report()
    unsafe_runbook["runbook_outline"] = ["raw_prompt_payload_value"]
    invalid_cases.append((unsafe_runbook, "unsafe_material"))

    bogus_phase8_error = safe_readiness_report()
    bogus_phase8_error["candidate_contract"]["fail_closed_errors"] = ["not_a_phase8_code"]
    invalid_cases.append((bogus_phase8_error, "invalid_readiness_report"))

    extra_candidate_forbidden = safe_readiness_report()
    extra_candidate_forbidden["candidate_contract"]["forbidden_material"] = FORBIDDEN_MATERIAL[:-1] + [
        "unsafe-" + "token" + "-phase9"
    ]
    invalid_cases.append((extra_candidate_forbidden, "unsafe_material"))

    unknown = safe_readiness_report()
    unknown["extra_field"] = "surprise"
    invalid_cases.append((unknown, "invalid_readiness_report"))

    for readiness_report, error_code in invalid_cases:
        assert_error(build(readiness_report=readiness_report), error_code)


def test_phase9_design_rejects_live_scope_and_gateway_observation_intent() -> None:
    production_mode = safe_shadow_scope()
    production_mode["mode"] = "production"
    assert_error(build(shadow_scope=production_mode), "production_action_requested")

    live_source = safe_shadow_scope()
    live_source["source_kind"] = "live_gateway_stream"
    assert_error(build(shadow_scope=live_source), "production_action_requested")

    live_observation = safe_gateway_observation_boundary()
    live_observation["observation_mode"] = "observe_live_gateway"
    assert_error(build(gateway_observation_boundary=live_observation), "production_action_requested")

    outbound_effect = safe_gateway_observation_boundary()
    outbound_effect["outbound_effects"] = "send"
    assert_error(build(gateway_observation_boundary=outbound_effect), "production_action_requested")

    adapter_import = safe_gateway_observation_boundary()
    adapter_import["adapter_imports_allowed"] = True
    assert_error(build(gateway_observation_boundary=adapter_import), "production_action_requested")

    platform_payload = safe_gateway_observation_boundary()
    platform_payload["platform_payloads_allowed"] = True
    assert_error(build(gateway_observation_boundary=platform_payload), "unsafe_material")

    message_ids = safe_gateway_observation_boundary()
    message_ids["message_identifiers_allowed"] = True
    assert_error(build(gateway_observation_boundary=message_ids), "unsafe_material")

    unknown_surface = safe_shadow_scope()
    unknown_surface["allowed_surfaces"] = ["final_text", "callback"]
    assert_error(build(shadow_scope=unknown_surface), "invalid_shadow_scope")


def test_phase9_design_rejects_runtime_lifecycle_and_signal_intent() -> None:
    client_factory = safe_runtime_execution_boundary()
    client_factory["client_lifecycle"] = "client_factory"
    assert_error(build(runtime_execution_boundary=client_factory), "runtime_lifecycle_requested")

    temporal_address = safe_runtime_execution_boundary()
    temporal_address["temporal_address"] = "127.0.0.1:7233"
    assert_error(build(runtime_execution_boundary=temporal_address), "runtime_lifecycle_requested")

    signal_ingress = safe_runtime_execution_boundary()
    signal_ingress["event_ingress"] = "payload_carrying_signals"
    assert_error(build(runtime_execution_boundary=signal_ingress), "runtime_lifecycle_requested")

    base_dependency = safe_runtime_execution_boundary()
    base_dependency["temporal_dependency"] = "base_dependency_required"
    assert_error(build(runtime_execution_boundary=base_dependency), "runtime_lifecycle_requested")

    worker_owner = safe_runtime_execution_boundary()
    worker_owner["worker_lifecycle"] = "owned"
    assert_error(build(runtime_execution_boundary=worker_owner), "runtime_lifecycle_requested")

    forbidden_operation = safe_runtime_execution_boundary()
    forbidden_operation["allowed_operations"] = ["start_transaction", "execute_live_gateway_delivery"]
    assert_error(build(runtime_execution_boundary=forbidden_operation), "runtime_lifecycle_requested")


def test_phase9_design_enforces_safe_artifact_policy_and_no_raw_material_leaks() -> None:
    result = build()
    rendered = repr(result)
    for forbidden in FORBIDDEN_OUTPUT_VALUES:
        assert forbidden not in rendered

    incomplete_forbidden = safe_artifact_policy()
    incomplete_forbidden["forbidden_material"] = ["raw_prompt"]
    assert_error(build(artifact_policy=incomplete_forbidden), "artifact_policy_violation")

    extra_artifact_forbidden = safe_artifact_policy()
    extra_artifact_forbidden["forbidden_material"] = list(FORBIDDEN_MATERIAL) + [
        "unsafe-" + "token" + "-phase9"
    ]
    assert_error(build(artifact_policy=extra_artifact_forbidden), "unsafe_material")

    raw_allowed_field = safe_artifact_policy()
    raw_allowed_field["allowed_fields"] = ["run_id", "raw_prompt"]
    assert_error(build(artifact_policy=raw_allowed_field), "artifact_policy_violation")

    unsafe_report = safe_readiness_report()
    unsafe_report["candidate_contract"]["audit_notes"] = ["raw_card_json"]
    assert_error(build(readiness_report=unsafe_report), "unsafe_material")

    private_report = safe_readiness_report()
    private_report["checks"]["oc_" + "phase9_private_chat"] = True
    assert_error(build(readiness_report=private_report), "unsafe_material")

    hostile_scope = HostileReadinessReport(safe_shadow_scope())
    assert_error(build(shadow_scope=hostile_scope), "invalid_shadow_scope")

    hostile_gateway = safe_gateway_observation_boundary()
    hostile_gateway["callback_url"] = "https://example.invalid/callback?access_" + "token=phase9"
    assert_error(build(gateway_observation_boundary=hostile_gateway), "unsafe_material")

    hostile_artifact = safe_artifact_policy()
    hostile_artifact["connection_string"] = "postgres" + "://phase9.invalid/db"
    assert_error(build(artifact_policy=hostile_artifact), "unsafe_material")


def test_phase9_design_rejects_config_registry_service_restart_and_default_on_policy() -> None:
    default_on = safe_rollback_policy()
    default_on["default_state"] = "on"
    assert_error(build(rollback_policy=default_on), "production_action_requested")

    no_kill_switch = safe_rollback_policy()
    no_kill_switch["kill_switch_required"] = False
    assert_error(build(rollback_policy=no_kill_switch), "invalid_rollback_policy")

    no_rollback = safe_rollback_policy()
    no_rollback["rollback_plan_required"] = False
    assert_error(build(rollback_policy=no_rollback), "invalid_rollback_policy")

    config_write = safe_rollback_policy()
    config_write["config_write_allowed"] = True
    assert_error(build(rollback_policy=config_write), "registry_or_config_write_requested")

    registry_write = safe_rollback_policy()
    registry_write["registry_write_allowed"] = True
    assert_error(build(rollback_policy=registry_write), "registry_or_config_write_requested")

    service_lifecycle = safe_rollback_policy()
    service_lifecycle["service_lifecycle_allowed"] = True
    assert_error(build(rollback_policy=service_lifecycle), "runtime_lifecycle_requested")

    gateway_restart = safe_rollback_policy()
    gateway_restart["gateway_restart_allowed"] = True
    assert_error(build(rollback_policy=gateway_restart), "production_action_requested")


def test_phase9_design_returns_stable_error_for_malformed_descriptor_value_types() -> None:
    malformed_scope = safe_shadow_scope()
    malformed_scope["mode"] = []
    assert_error(build(shadow_scope=malformed_scope), "invalid_shadow_scope")

    malformed_gateway = safe_gateway_observation_boundary()
    malformed_gateway["observation_mode"] = []
    assert_error(build(gateway_observation_boundary=malformed_gateway), "invalid_gateway_observation_boundary")
