"""RED contract tests for FlowWeaver Phase 11 controlled Gateway observation design gate."""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PHASE5C_SRC = ROOT / "prototypes" / "flowweaver_phase5c_runtime_client" / "src"
if str(PHASE5C_SRC) not in sys.path:
    sys.path.insert(0, str(PHASE5C_SRC))

WORKFLOW_ID = "runtime_tx_phase11_gateway_observation"
PHASE10_REQUIRED_APPROVALS = [
    "production_gateway_wiring",
    "production_config_write",
    "gateway_restart",
    "external_temporal_service",
    "real_send_edit_render_callback",
    "production_tool_registry",
    "remote_branch_or_worktree_cleanup",
]
PHASE11_REQUIRED_APPROVALS = [
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
PHASE10_VERIFICATION_MATRIX = [
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
PHASE10_RUNBOOK_OUTLINE = [
    "phase10_proves_bounded_prototype_loop_only",
    "production_activation_requires_separate_design_and_approval",
    "keep_default_off_until_explicit_enablement",
    "caller_supplied_control_surface_only",
    "no_gateway_adapter_or_platform_payloads",
    "no_temporal_client_worker_docker_or_service_lifecycle",
    "no_raw_payloads_or_secrets_in_reports_or_artifacts",
    "use_direct_pytest_for_integration_regression",
]
PHASE11_FORBIDDEN_MATERIAL = [
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
PHASE11_ERROR_CODES = sorted(
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
PHASE11_VERIFICATION_MATRIX = [
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
PHASE11_RUNBOOK_OUTLINE = [
    "phase11_is_design_gate_only",
    "controlled_gateway_observation_implementation_requires_separate_approval",
    "live_gateway_observation_enablement_requires_separate_approval",
    "production_activation_requires_separate_design_and_approval",
    "keep_default_off_until_explicit_enablement",
    "rollback_and_kill_switch_required_before_any_wiring",
    "no_raw_payloads_or_secrets_in_reports_or_artifacts",
    "use_direct_pytest_for_integration_regression",
]
SUCCESS_FIELDS = {
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
BLOCKED_FIELDS = {"type", "version", "ok", "verdict", "phase", "error_code", "side_effects"}
PLAN_FIELDS = {
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
SAFE_EXISTING_MODULES = [
    "gateway/flowweaver_shadow.py",
    "gateway/flowweaver_shadow_publisher.py",
    "gateway/flowweaver_contract.py",
    "gateway/delivery_state.py",
    "gateway/progress/events.py",
]
SAFE_FUTURE_FILES = [
    "gateway/flowweaver_controlled_gateway_observation.py",
    "tests/gateway/test_flowweaver_controlled_gateway_observation.py",
]
SAFE_TOUCHPOINTS = [
    "task_tracker_snapshot",
    "flowweaver_shadow_snapshot",
    "flowweaver_shadow_runtime_publication",
    "delivery_state_summary",
]
SAFE_SURFACES = ["final_text", "rich_card", "progress_card", "media"]
SAFE_INPUTS = [
    "phase10_report",
    "shadow_runtime_publication_summary",
    "delivery_state_summary",
    "progress_snapshot_summary",
]
SAFE_OUTPUTS = ["safe_summary", "fixture_projection", "readiness_checks", "stable_error_codes"]
SAFE_RUNTIME_OPERATIONS = ["start_transaction", "query_transaction", "reconcile_delivery_ack"]
FORBIDDEN_OUTPUT_VALUES = (
    "production_ready",
    "production_enabled",
    "live_enabled",
    "gateway_enabled",
    "observation_enabled",
    "integration_enabled",
    "oc_phase11_private_chat",
    "ou_phase11_private_user",
    "message_phase11_private",
    "raw_gateway_event_value",
    "raw_prompt_value",
    "platform_payload_value",
    "callback_payload_value",
    "https://example.invalid/callback?access_" + "token=phase11",
    "postgres" + "://phase11.invalid/db",
    "Bearer " + "phase11secretvalue0000000000",
)


def import_design_module():
    return importlib.import_module("flowweaver_runtime_client.controlled_gateway_observation_design")


def safe_phase10_report() -> dict[str, object]:
    run_id = "controlled_shadow_run_phase11_gateway_observation"
    loop_result = {
        "workflow_id": WORKFLOW_ID,
        "transaction_id": WORKFLOW_ID,
        "start_status": "started",
        "ack_count": 1,
        "surfaces": ["final_text", "rich_card"],
        "status_counts": {"started": 1, "ack_applied": 1},
        "delivery_counts": {"total": 2, "sent": 1, "acknowledged": 1},
        "stable_error_codes": [],
        "safe_digest": "0123456789abcdef",
        "side_effects": [],
    }
    return {
        "type": "flowweaver.controlled_shadow_prototype_loop_report.v0",
        "version": "flowweaver.controlled_shadow_prototype_loop.v0",
        "ok": True,
        "verdict": "controlled_shadow_prototype_loop_verified",
        "phase": "phase10_controlled_shadow_prototype_loop",
        "run_id": run_id,
        "plan_transaction_id": WORKFLOW_ID,
        "publication_count": 1,
        "loop_results": [loop_result],
        "artifact": {
            "type": "flowweaver.controlled_shadow_prototype_artifact.v0",
            "artifact_mode": "safe_summary_only",
            "run_id": run_id,
            "plan_transaction_id": WORKFLOW_ID,
            "publication_count": 1,
            "operation_counts": {"phase7_loop": 1},
            "delivery_counts": {"total": 2, "sent": 1, "acknowledged": 1},
            "statuses": {"started": 1, "ack_applied": 1},
            "digests": [loop_result["safe_digest"]],
            "stable_error_codes": [],
            "approvals": list(PHASE10_REQUIRED_APPROVALS),
            "side_effects": [],
        },
        "checks": {key: True for key in PHASE10_VERIFICATION_MATRIX},
        "required_separate_approvals": list(PHASE10_REQUIRED_APPROVALS),
        "verification_matrix": list(PHASE10_VERIFICATION_MATRIX),
        "runbook_outline": list(PHASE10_RUNBOOK_OUTLINE),
        "side_effects": [],
    }


def safe_gateway_observation_boundary() -> dict[str, object]:
    return {
        "type": "flowweaver.controlled_gateway_observation_boundary.v0",
        "mode": "future_default_off_observation_candidate",
        "source_kind": "phase10_evidence_replay",
        "candidate_touchpoints": list(SAFE_TOUCHPOINTS),
        "allowed_existing_modules": list(SAFE_EXISTING_MODULES),
        "allowed_future_files": list(SAFE_FUTURE_FILES),
        "allowed_surfaces": list(SAFE_SURFACES),
        "observation_inputs": list(SAFE_INPUTS),
        "observation_outputs": list(SAFE_OUTPUTS),
        "adapter_imports_allowed": False,
        "platform_payloads_allowed": False,
        "message_identifiers_allowed": False,
        "raw_content_allowed": False,
        "send_edit_render_callback_allowed": False,
        "logs_allowed": "sanitized_codes_only",
        "side_effects": [],
    }


def safe_integration_policy() -> dict[str, object]:
    return {
        "type": "flowweaver.controlled_gateway_integration_policy.v0",
        "mode": "implementation_contract_only",
        "feature_flag_ref": "feature_flag_ref_phase11_controlled_gateway_observation_off",
        "default_enabled": False,
        "implementation_stage": "future_pr_only",
        "allowed_config_scope": "static_docs_only",
        "config_write_allowed": False,
        "gateway_restart_allowed": False,
        "runtime_effects_allowed": False,
        "temporal_lifecycle_allowed": False,
        "payload_carrying_signals_allowed": False,
        "registry_write_allowed": False,
        "operator_approval_ref": "approval_ref_phase11_implementation_contract",
        "rollout_steps": [
            "design_review",
            "implementation_pr",
            "focused_tests",
            "integration_regression",
            "fresh_context_review",
            "manual_enablement_request",
            "separate_gateway_restart_request",
            "post_enablement_observation_only_verification",
            "rollback_review",
        ],
        "rollback_required": True,
        "kill_switch_required": True,
        "side_effects": [],
    }


def safe_runtime_handoff_boundary() -> dict[str, object]:
    return {
        "type": "flowweaver.controlled_gateway_runtime_handoff_boundary.v0",
        "mode": "future_caller_supplied_only",
        "control_surface_lifecycle": "caller_supplied_only",
        "runtime_operations": list(SAFE_RUNTIME_OPERATIONS),
        "runtime_client_construction_allowed": False,
        "temporal_client_allowed": False,
        "temporal_worker_allowed": False,
        "workflow_environment_allowed": False,
        "payload_carrying_signals_allowed": False,
        "fixture_projection": "phase10_publication_fixture_shape",
        "ack_source": "shadow_runtime_publication_summary",
        "ack_target_validation": "exact_initialized_delivery_slot",
        "side_effects": [],
    }


def safe_artifact_policy() -> dict[str, object]:
    return {
        "type": "flowweaver.controlled_gateway_artifact_policy.v0",
        "artifact_mode": "safe_summary_only",
        "allowed_fields": [
            "design_id",
            "phase10_run_id",
            "plan_transaction_id",
            "candidate_touchpoints",
            "allowed_surfaces",
            "checks",
            "stable_error_codes",
            "approvals",
            "side_effects",
        ],
        "retention": "local_artifact_only",
        "log_policy": "sanitized_codes_only",
        "forbidden_material": list(PHASE11_FORBIDDEN_MATERIAL),
        "side_effects": [],
    }


def safe_rollback_policy() -> dict[str, object]:
    return {
        "type": "flowweaver.controlled_gateway_rollback_policy.v0",
        "rollback_mode": "feature_flag_off_first",
        "kill_switch_required": True,
        "rollback_hooks_required": True,
        "config_revert_required": True,
        "gateway_restart_requires_separate_approval": True,
        "production_enablement_requires_separate_approval": True,
        "side_effects": [],
    }


def design_with(
    *,
    phase10_prototype_loop_report: object | None = None,
    gateway_observation_boundary: object | None = None,
    integration_policy: object | None = None,
    runtime_handoff_boundary: object | None = None,
    artifact_policy: object | None = None,
    rollback_policy: object | None = None,
) -> dict[str, object]:
    module = import_design_module()
    return module.design_flowweaver_controlled_gateway_observation(
        phase10_prototype_loop_report=(
            safe_phase10_report() if phase10_prototype_loop_report is None else phase10_prototype_loop_report
        ),
        gateway_observation_boundary=(
            safe_gateway_observation_boundary()
            if gateway_observation_boundary is None
            else gateway_observation_boundary
        ),
        integration_policy=safe_integration_policy() if integration_policy is None else integration_policy,
        runtime_handoff_boundary=(
            safe_runtime_handoff_boundary() if runtime_handoff_boundary is None else runtime_handoff_boundary
        ),
        artifact_policy=safe_artifact_policy() if artifact_policy is None else artifact_policy,
        rollback_policy=safe_rollback_policy() if rollback_policy is None else rollback_policy,
    )


def assert_no_forbidden_output(value: object) -> None:
    rendered = repr(value)
    lowered = rendered.lower()
    for forbidden in FORBIDDEN_OUTPUT_VALUES:
        assert forbidden not in rendered
    assert "raw exception" not in lowered
    assert "callback_payload_value" not in rendered
    assert "raw_gateway_event_value" not in rendered
    assert "platform_payload_value" not in rendered
    assert "claim_check_policy" not in lowered
    assert "allowed_runtime_events" not in lowered


def assert_blocked(result: dict[str, object], error_code: str) -> None:
    assert type(result) is dict
    assert set(result) == BLOCKED_FIELDS
    assert result == {
        "type": "flowweaver.controlled_gateway_observation_design_report.v0",
        "version": "flowweaver.controlled_gateway_observation_design.v0",
        "ok": False,
        "verdict": "blocked",
        "phase": "phase11_controlled_gateway_observation_integration_design",
        "error_code": error_code,
        "side_effects": [],
    }
    assert error_code in PHASE11_ERROR_CODES
    assert_no_forbidden_output(result)


def test_phase11_design_import_is_default_off_sync_and_narrow() -> None:
    for module_name in (
        "flowweaver_runtime_client.controlled_gateway_observation_design",
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

    assert module.FLOWWEAVER_CONTROLLED_GATEWAY_OBSERVATION_DESIGN_VERSION == (
        "flowweaver.controlled_gateway_observation_design.v0"
    )
    assert module.CONTROLLED_GATEWAY_OBSERVATION_BOUNDARY_TYPE == (
        "flowweaver.controlled_gateway_observation_boundary.v0"
    )
    assert module.CONTROLLED_GATEWAY_INTEGRATION_POLICY_TYPE == (
        "flowweaver.controlled_gateway_integration_policy.v0"
    )
    assert module.CONTROLLED_GATEWAY_RUNTIME_HANDOFF_BOUNDARY_TYPE == (
        "flowweaver.controlled_gateway_runtime_handoff_boundary.v0"
    )
    assert module.CONTROLLED_GATEWAY_ARTIFACT_POLICY_TYPE == "flowweaver.controlled_gateway_artifact_policy.v0"
    assert module.CONTROLLED_GATEWAY_ROLLBACK_POLICY_TYPE == "flowweaver.controlled_gateway_rollback_policy.v0"
    assert module.CONTROLLED_GATEWAY_OBSERVATION_DESIGN_REPORT_TYPE == (
        "flowweaver.controlled_gateway_observation_design_report.v0"
    )
    assert not inspect.iscoroutinefunction(module.design_flowweaver_controlled_gateway_observation)
    signature = inspect.signature(module.design_flowweaver_controlled_gateway_observation)
    assert list(signature.parameters) == [
        "phase10_prototype_loop_report",
        "gateway_observation_boundary",
        "integration_policy",
        "runtime_handoff_boundary",
        "artifact_policy",
        "rollback_policy",
    ]
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())
    assert sorted(module.__all__) == [
        "CONTROLLED_GATEWAY_ARTIFACT_POLICY_TYPE",
        "CONTROLLED_GATEWAY_INTEGRATION_POLICY_TYPE",
        "CONTROLLED_GATEWAY_OBSERVATION_BOUNDARY_TYPE",
        "CONTROLLED_GATEWAY_OBSERVATION_DESIGN_REPORT_TYPE",
        "CONTROLLED_GATEWAY_ROLLBACK_POLICY_TYPE",
        "CONTROLLED_GATEWAY_RUNTIME_HANDOFF_BOUNDARY_TYPE",
        "FLOWWEAVER_CONTROLLED_GATEWAY_OBSERVATION_DESIGN_VERSION",
        "design_flowweaver_controlled_gateway_observation",
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


def test_phase11_design_builds_safe_default_off_contract_from_exact_phase10_evidence() -> None:
    result = design_with()

    assert type(result) is dict
    assert set(result) == SUCCESS_FIELDS
    assert result["type"] == "flowweaver.controlled_gateway_observation_design_report.v0"
    assert result["version"] == "flowweaver.controlled_gateway_observation_design.v0"
    assert result["ok"] is True
    assert result["verdict"] == "ready_for_controlled_gateway_observation_implementation"
    assert result["phase"] == "phase11_controlled_gateway_observation_integration_design"
    assert result["design_id"].startswith("controlled_gateway_observation_design_")
    assert result["phase10_run_id"] == "controlled_shadow_run_phase11_gateway_observation"
    assert result["plan_transaction_id"] == WORKFLOW_ID
    assert result["checks"] == {key: True for key in PHASE11_VERIFICATION_MATRIX}
    assert result["required_separate_approvals"] == PHASE11_REQUIRED_APPROVALS
    assert result["verification_matrix"] == PHASE11_VERIFICATION_MATRIX
    assert result["runbook_outline"] == PHASE11_RUNBOOK_OUTLINE
    assert result["side_effects"] == []

    plan = result["controlled_gateway_observation_plan"]
    assert set(plan) == PLAN_FIELDS
    assert plan["plan_version"] == "flowweaver.controlled_gateway_observation_design.v0"
    assert plan["source_kind"] == "phase10_evidence_replay"
    assert plan["mode"] == "future_default_off_observation_candidate"
    assert plan["candidate_touchpoints"] == SAFE_TOUCHPOINTS
    assert plan["allowed_existing_modules"] == SAFE_EXISTING_MODULES
    assert plan["allowed_future_files"] == SAFE_FUTURE_FILES
    assert plan["allowed_surfaces"] == SAFE_SURFACES
    assert plan["observation_inputs"] == SAFE_INPUTS
    assert plan["observation_outputs"] == SAFE_OUTPUTS
    assert plan["feature_flag_ref"] == "feature_flag_ref_phase11_controlled_gateway_observation_off"
    assert plan["operator_approval_ref"] == "approval_ref_phase11_implementation_contract"
    assert plan["runtime_operations"] == SAFE_RUNTIME_OPERATIONS
    assert plan["runtime_handoff_mode"] == "future_caller_supplied_only"
    assert plan["artifact_mode"] == "safe_summary_only"
    assert plan["approval_refs"] == {
        "operator_approval_ref": "approval_ref_phase11_implementation_contract",
        "feature_flag_ref": "feature_flag_ref_phase11_controlled_gateway_observation_off",
    }
    assert plan["rollback_hooks_required"] is True
    assert plan["kill_switch_required"] is True
    assert plan["forbidden_material"] == PHASE11_FORBIDDEN_MATERIAL
    assert plan["fail_closed_errors"] == PHASE11_ERROR_CODES
    assert result["artifact_policy"] == {
        "artifact_mode": "safe_summary_only",
        "allowed_fields": safe_artifact_policy()["allowed_fields"],
        "retention": "local_artifact_only",
        "log_policy": "sanitized_codes_only",
        "forbidden_material": PHASE11_FORBIDDEN_MATERIAL,
        "side_effects": [],
    }
    assert result["rollback_policy"] == {
        "rollback_mode": "feature_flag_off_first",
        "kill_switch_required": True,
        "rollback_hooks_required": True,
        "config_revert_required": True,
        "gateway_restart_requires_separate_approval": True,
        "production_enablement_requires_separate_approval": True,
        "side_effects": [],
    }
    assert_no_forbidden_output(result)


@pytest.mark.parametrize(
    ("mutate", "error_code"),
    [
        (lambda report: report.update({"ok": False, "verdict": "blocked"}), "invalid_phase10_report"),
        (lambda report: report.update({"verdict": "production_ready"}), "production_action_requested"),
        (lambda report: report.update({"gateway_enabled": True}), "production_action_requested"),
        (lambda report: report.pop("checks"), "invalid_phase10_report"),
        (lambda report: report["checks"].update({"side_effects_absent": False}), "invalid_phase10_report"),
        (
            lambda report: report.update(
                {"required_separate_approvals": PHASE10_REQUIRED_APPROVALS + ["gateway_restart"]}
            ),
            "invalid_phase10_report",
        ),
        (
            lambda report: report.update({"required_separate_approvals": list(reversed(PHASE10_REQUIRED_APPROVALS))}),
            "invalid_phase10_report",
        ),
        (
            lambda report: report.update({"verification_matrix": list(reversed(PHASE10_VERIFICATION_MATRIX))}),
            "invalid_phase10_report",
        ),
        (
            lambda report: report.update({"runbook_outline": list(PHASE10_RUNBOOK_OUTLINE[:-1])}),
            "invalid_phase10_report",
        ),
        (
            lambda report: report["loop_results"][0].update({"workflow_id": "runtime_tx_phase11_other"}),
            "workflow_id_mismatch",
        ),
        (lambda report: report["artifact"].update({"raw_gateway_event": "raw_gateway_event_value"}), "unsafe_material"),
        (lambda report: report.update({"side_effects": ["would_send"]}), "side_effects_not_absent"),
    ],
)
def test_phase11_design_rejects_non_exact_or_unsafe_phase10_reports(mutate, error_code: str) -> None:
    report = safe_phase10_report()
    mutate(report)

    assert_blocked(design_with(phase10_prototype_loop_report=report), error_code)


@pytest.mark.parametrize(
    ("mutate", "error_code"),
    [
        (lambda value: value.update({"mode": "live"}), "production_action_requested"),
        (lambda value: value.update({"source_kind": "real_feishu"}), "production_action_requested"),
        (lambda value: value["allowed_existing_modules"].append("gateway/run.py"), "production_action_requested"),
        (lambda value: value["allowed_existing_modules"].append("gateway/platforms/feishu.py"), "production_action_requested"),
        (lambda value: value["allowed_future_files"].append("run_agent.py"), "production_action_requested"),
        (lambda value: value["candidate_touchpoints"].append("adapter.send"), "production_action_requested"),
        (lambda value: value.update({"adapter_imports_allowed": True}), "production_action_requested"),
        (lambda value: value.update({"platform_payloads_allowed": True}), "production_action_requested"),
        (lambda value: value.update({"message_identifiers_allowed": True}), "production_action_requested"),
        (lambda value: value.update({"raw_content_allowed": True}), "unsafe_material"),
        (lambda value: value.update({"send_edit_render_callback_allowed": True}), "production_action_requested"),
        (lambda value: value.update({"side_effects": ["would_render"]}), "side_effects_not_absent"),
    ],
)
def test_phase11_design_rejects_live_gateway_or_platform_observation_boundary(mutate, error_code: str) -> None:
    boundary = safe_gateway_observation_boundary()
    mutate(boundary)

    assert_blocked(design_with(gateway_observation_boundary=boundary), error_code)


@pytest.mark.parametrize(
    ("mutate", "error_code"),
    [
        (lambda value: value.update({"mode": "production"}), "production_action_requested"),
        (lambda value: value.update({"default_enabled": True}), "production_action_requested"),
        (lambda value: value.update({"allowed_config_scope": "production_config_path"}), "registry_or_config_write_requested"),
        (lambda value: value.update({"config_write_allowed": True}), "registry_or_config_write_requested"),
        (lambda value: value.update({"gateway_restart_allowed": True}), "production_action_requested"),
        (lambda value: value.update({"runtime_effects_allowed": True}), "production_action_requested"),
        (lambda value: value.update({"temporal_lifecycle_allowed": True}), "runtime_lifecycle_requested"),
        (lambda value: value.update({"payload_carrying_signals_allowed": True}), "runtime_lifecycle_requested"),
        (lambda value: value.update({"registry_write_allowed": True}), "registry_or_config_write_requested"),
        (lambda value: value["rollout_steps"].append("systemctl_restart_gateway"), "runtime_lifecycle_requested"),
        (lambda value: value.update({"side_effects": ["would_write_config"]}), "side_effects_not_absent"),
    ],
)
def test_phase11_design_rejects_default_on_config_registry_restart_and_lifecycle_policy(
    mutate,
    error_code: str,
) -> None:
    policy = safe_integration_policy()
    mutate(policy)

    assert_blocked(design_with(integration_policy=policy), error_code)


@pytest.mark.parametrize(
    ("mutate", "error_code"),
    [
        (lambda value: value.update({"mode": "live_handoff"}), "runtime_lifecycle_requested"),
        (lambda value: value.update({"runtime_client_construction_allowed": True}), "runtime_lifecycle_requested"),
        (lambda value: value.update({"temporal_client_allowed": True}), "runtime_lifecycle_requested"),
        (lambda value: value.update({"temporal_worker_allowed": True}), "runtime_lifecycle_requested"),
        (lambda value: value.update({"workflow_environment_allowed": True}), "runtime_lifecycle_requested"),
        (lambda value: value.update({"payload_carrying_signals_allowed": True}), "runtime_lifecycle_requested"),
        (lambda value: value.update({"task_queue": "phase11_queue"}), "runtime_lifecycle_requested"),
        (lambda value: value.update({"subprocess": "python gateway/run.py"}), "runtime_lifecycle_requested"),
        (lambda value: value["runtime_operations"].append("send_message"), "production_action_requested"),
        (lambda value: value.update({"side_effects": ["would_start_worker"]}), "side_effects_not_absent"),
    ],
)
def test_phase11_design_rejects_live_runtime_handoff_or_temporal_lifecycle(mutate, error_code: str) -> None:
    boundary = safe_runtime_handoff_boundary()
    mutate(boundary)

    assert_blocked(design_with(runtime_handoff_boundary=boundary), error_code)


@pytest.mark.parametrize(
    ("mutate", "error_code"),
    [
        (lambda value: value["allowed_fields"].append("raw_gateway_event"), "artifact_policy_violation"),
        (lambda value: value.update({"log_policy": "raw_logs"}), "artifact_policy_violation"),
        (lambda value: value.update({"retention": "production_logs"}), "artifact_policy_violation"),
        (lambda value: value.update({"forbidden_material": PHASE11_FORBIDDEN_MATERIAL[:-1]}), "artifact_policy_violation"),
        (lambda value: value.update({"side_effects": ["would_log_raw"]}), "side_effects_not_absent"),
    ],
)
def test_phase11_design_rejects_unsafe_artifact_policy(mutate, error_code: str) -> None:
    policy = safe_artifact_policy()
    mutate(policy)

    assert_blocked(design_with(artifact_policy=policy), error_code)


@pytest.mark.parametrize(
    ("mutate", "error_code"),
    [
        (lambda value: value.update({"rollback_mode": "production_redeploy"}), "production_action_requested"),
        (lambda value: value.update({"kill_switch_required": False}), "invalid_rollback_policy"),
        (lambda value: value.update({"rollback_hooks_required": False}), "invalid_rollback_policy"),
        (lambda value: value.update({"config_revert_required": False}), "registry_or_config_write_requested"),
        (
            lambda value: value.update({"gateway_restart_requires_separate_approval": False}),
            "production_action_requested",
        ),
        (
            lambda value: value.update({"production_enablement_requires_separate_approval": False}),
            "production_action_requested",
        ),
        (lambda value: value.update({"side_effects": ["would_restart_gateway"]}), "side_effects_not_absent"),
    ],
)
def test_phase11_design_rejects_rollback_without_kill_switch_or_separate_approvals(mutate, error_code: str) -> None:
    policy = safe_rollback_policy()
    mutate(policy)

    assert_blocked(design_with(rollback_policy=policy), error_code)


def test_phase11_design_maps_unexpected_objects_to_safe_blocked_report_without_serializing_them() -> None:
    class HostileReport(dict):
        pass

    hostile = HostileReport(safe_phase10_report())
    hostile["note"] = "raw_prompt_value platform_payload_value oc_phase11_private_chat"

    result = design_with(phase10_prototype_loop_report=hostile)

    assert_blocked(result, "invalid_phase10_report")
    assert_no_forbidden_output(result)
