"""RED contract tests for FlowWeaver Phase 13 live Gateway observation enablement design gate."""

from __future__ import annotations

import copy
import importlib
import importlib.util
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PHASE5C_SRC = ROOT / "prototypes" / "flowweaver_phase5c_runtime_client" / "src"
PHASE12_TEST_PATH = ROOT / "tests" / "gateway" / "test_flowweaver_controlled_gateway_observation.py"
if str(PHASE5C_SRC) not in sys.path:
    sys.path.insert(0, str(PHASE5C_SRC))

WORKFLOW_ID = "runtime_tx_phase11_gateway_observation"
PHASE12_REQUIRED_APPROVALS = [
    "live_gateway_observation_enablement",
    "production_gateway_wiring",
    "production_config_write",
    "gateway_restart",
    "external_temporal_service",
    "real_send_edit_render_callback",
    "production_tool_registry",
    "remote_branch_or_worktree_cleanup",
]
PHASE13_REQUIRED_APPROVALS = [
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
PHASE12_VERIFICATION_MATRIX = [
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
PHASE12_RUNBOOK_OUTLINE = [
    "phase12_is_default_off_observation_hook_only",
    "live_gateway_observation_enablement_requires_separate_approval",
    "production_activation_requires_separate_design_and_approval",
    "keep_default_off_until_explicit_enablement",
    "no_gateway_run_or_platform_adapter_wiring",
    "no_temporal_client_worker_docker_or_service_lifecycle",
    "no_raw_payloads_or_secrets_in_reports_or_artifacts",
    "use_direct_pytest_for_integration_regression",
]
PHASE12_FORBIDDEN_MATERIAL = [
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
PHASE12_ERROR_CODES = sorted(
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
PHASE13_ERROR_CODES = sorted(
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
PHASE13_VERIFICATION_MATRIX = [
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
PHASE13_RUNBOOK_OUTLINE = [
    "phase13_is_enablement_design_gate_only",
    "live_gateway_observation_enablement_implementation_requires_separate_approval",
    "live_gateway_observation_enablement_requires_separate_approval",
    "production_activation_requires_separate_design_and_approval",
    "keep_default_off_until_explicit_enablement",
    "rollback_and_kill_switch_required_before_any_enablement",
    "no_gateway_run_or_platform_adapter_wiring",
    "no_temporal_client_worker_docker_or_service_lifecycle",
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
BLOCKED_FIELDS = {"type", "version", "ok", "verdict", "phase", "error_code", "side_effects"}
ENABLEMENT_DESIGN_FIELDS = {
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
ALLOWED_TOUCHPOINTS = [
    "task_tracker_snapshot",
    "flowweaver_shadow_snapshot",
    "flowweaver_shadow_runtime_publication",
    "delivery_state_summary",
]
ALLOWED_SURFACES = ["final_text", "rich_card", "progress_card", "media"]
ALLOWED_SUMMARY_INPUTS = [
    "phase12_observation_hook_report",
    "sanitized_shadow_runtime_publication_summary",
    "sanitized_delivery_state_summary",
    "sanitized_progress_snapshot_summary",
]
ROLLOUT_STEPS = [
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
ARTIFACT_ALLOWED_FIELDS = [
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
FORBIDDEN_OUTPUT_VALUES = (
    "production_ready",
    "production_enabled",
    "live_enabled",
    "gateway_enabled",
    "observation_enabled",
    "integration_enabled",
    "oc_phase13_private_chat",
    "ou_phase13_private_user",
    "message_phase13_private",
    "raw_gateway_event_value",
    "raw_prompt_value",
    "raw_tool_output_value",
    "platform_payload_value",
    "callback_payload_value",
    "https://example.invalid/callback?access_" + "token=phase13",
    "postgres" + "://phase13.invalid/db",
    "Bearer " + "phase13secretvalue0000000000",
)


def import_design_module():
    return importlib.import_module("flowweaver_runtime_client.live_gateway_observation_enablement_design")


def phase12_helpers():
    spec = importlib.util.spec_from_file_location("phase12_test_helpers_for_phase13", PHASE12_TEST_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def safe_phase12_report() -> dict[str, object]:
    return copy.deepcopy(phase12_helpers().observe_with())


def safe_enablement_policy() -> dict[str, object]:
    return {
        "type": "flowweaver.live_gateway_observation_enablement_policy.v0",
        "mode": "default_off_manual_enablement_design",
        "feature_flag_ref": "feature_flag_ref_phase13_live_gateway_observation_off",
        "operator_approval_ref": "approval_ref_phase13_enablement_design_contract",
        "default_enabled": False,
        "config_write_allowed": False,
        "gateway_restart_allowed": False,
        "adapter_calls_allowed": False,
        "platform_payloads_allowed": False,
        "temporal_lifecycle_allowed": False,
        "registry_write_allowed": False,
        "kill_switch_required": True,
        "rollout_steps": list(ROLLOUT_STEPS),
        "side_effects": [],
    }


def safe_observation_evidence_policy() -> dict[str, object]:
    return {
        "type": "flowweaver.live_gateway_observation_evidence_policy.v0",
        "evidence_mode": "sanitized_observation_summaries_only",
        "source_report_type": "flowweaver.controlled_gateway_observation_hook_report.v0",
        "allowed_inputs": list(ALLOWED_SUMMARY_INPUTS),
        "allowed_touchpoints": list(ALLOWED_TOUCHPOINTS),
        "allowed_surfaces": list(ALLOWED_SURFACES),
        "raw_material_allowed": False,
        "logs_allowed": "sanitized_codes_only",
        "forbidden_material": list(PHASE12_FORBIDDEN_MATERIAL),
        "side_effects": [],
    }


def safe_artifact_policy() -> dict[str, object]:
    return {
        "type": "flowweaver.live_gateway_observation_artifact_policy.v0",
        "artifact_mode": "safe_summary_only",
        "allowed_fields": list(ARTIFACT_ALLOWED_FIELDS),
        "retention": "local_artifact_only",
        "log_policy": "sanitized_codes_only",
        "forbidden_material": list(PHASE12_FORBIDDEN_MATERIAL),
        "side_effects": [],
    }


def safe_rollback_policy() -> dict[str, object]:
    return {
        "type": "flowweaver.live_gateway_observation_rollback_policy.v0",
        "rollback_mode": "feature_flag_off_first",
        "kill_switch_required": True,
        "config_revert_required": True,
        "gateway_restart_requires_separate_approval": True,
        "production_enablement_requires_separate_approval": True,
        "live_disable_verification_required": True,
        "side_effects": [],
    }


def design_with(
    *,
    phase12_observation_hook_report: object | None = None,
    enablement_policy: object | None = None,
    observation_evidence_policy: object | None = None,
    artifact_policy: object | None = None,
    rollback_policy: object | None = None,
) -> dict[str, object]:
    module = import_design_module()
    return module.design_flowweaver_live_gateway_observation_enablement(
        phase12_observation_hook_report=(
            safe_phase12_report() if phase12_observation_hook_report is None else phase12_observation_hook_report
        ),
        enablement_policy=safe_enablement_policy() if enablement_policy is None else enablement_policy,
        observation_evidence_policy=(
            safe_observation_evidence_policy()
            if observation_evidence_policy is None
            else observation_evidence_policy
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
    assert "access_token" not in lowered
    assert "callback_payload_value" not in rendered
    assert "raw_gateway_event_value" not in rendered
    assert "platform_payload_value" not in rendered


def assert_blocked(result: dict[str, object], error_code: str) -> None:
    assert type(result) is dict
    assert set(result) == BLOCKED_FIELDS
    assert result == {
        "type": "flowweaver.live_gateway_observation_enablement_design_report.v0",
        "version": "flowweaver.live_gateway_observation_enablement_design.v0",
        "ok": False,
        "verdict": "blocked",
        "phase": "phase13_live_gateway_observation_enablement_design",
        "error_code": error_code,
        "side_effects": [],
    }
    assert error_code in PHASE13_ERROR_CODES
    assert_no_forbidden_output(result)


def test_phase13_design_import_is_sync_prototype_only_and_narrow() -> None:
    for module_name in (
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

    assert module.FLOWWEAVER_LIVE_GATEWAY_OBSERVATION_ENABLEMENT_DESIGN_VERSION == (
        "flowweaver.live_gateway_observation_enablement_design.v0"
    )
    assert module.LIVE_GATEWAY_OBSERVATION_ENABLEMENT_DESIGN_REPORT_TYPE == (
        "flowweaver.live_gateway_observation_enablement_design_report.v0"
    )
    assert not inspect.iscoroutinefunction(module.design_flowweaver_live_gateway_observation_enablement)
    signature = inspect.signature(module.design_flowweaver_live_gateway_observation_enablement)
    assert list(signature.parameters) == [
        "phase12_observation_hook_report",
        "enablement_policy",
        "observation_evidence_policy",
        "artifact_policy",
        "rollback_policy",
    ]
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())
    assert sorted(module.__all__) == [
        "FLOWWEAVER_LIVE_GATEWAY_OBSERVATION_ENABLEMENT_DESIGN_VERSION",
        "LIVE_GATEWAY_OBSERVATION_ENABLEMENT_DESIGN_REPORT_TYPE",
        "design_flowweaver_live_gateway_observation_enablement",
    ]
    assert "temporalio" not in sys.modules
    assert "mcp" not in sys.modules
    assert "tools.registry" not in sys.modules
    assert "hermes_cli.platforms" not in sys.modules
    assert "toolsets" not in sys.modules
    assert "gateway.run" not in sys.modules
    assert "gateway.platforms.feishu" not in sys.modules
    assert "flowweaver_temporal_poc.client" not in sys.modules
    assert "flowweaver_temporal_poc.workflows" not in sys.modules


def test_phase13_design_builds_safe_default_off_enablement_plan_from_exact_phase12_evidence() -> None:
    phase12 = safe_phase12_report()

    result = design_with(phase12_observation_hook_report=phase12)

    assert type(result) is dict
    assert set(result) == SUCCESS_FIELDS
    assert result["type"] == "flowweaver.live_gateway_observation_enablement_design_report.v0"
    assert result["version"] == "flowweaver.live_gateway_observation_enablement_design.v0"
    assert result["ok"] is True
    assert result["verdict"] == "ready_for_live_gateway_observation_enablement_implementation"
    assert result["phase"] == "phase13_live_gateway_observation_enablement_design"
    assert result["design_id"].startswith("live_gateway_observation_enablement_design_")
    assert result["phase12_observation_id"] == phase12["observation_id"]
    assert result["phase11_design_id"] == phase12["phase11_design_id"]
    assert result["phase10_run_id"] == phase12["phase10_run_id"]
    assert result["plan_transaction_id"] == WORKFLOW_ID
    assert result["enablement_mode"] == "default_off_design_gate"
    assert result["checks"] == {key: True for key in PHASE13_VERIFICATION_MATRIX}
    assert result["required_separate_approvals"] == PHASE13_REQUIRED_APPROVALS
    assert result["verification_matrix"] == PHASE13_VERIFICATION_MATRIX
    assert result["runbook_outline"] == PHASE13_RUNBOOK_OUTLINE
    assert result["side_effects"] == []

    design = result["enablement_design"]
    assert set(design) == ENABLEMENT_DESIGN_FIELDS
    assert design["source_observation_verdict"] == "ready_for_live_gateway_observation_enablement_design"
    assert design["feature_flag_ref"] == "feature_flag_ref_phase13_live_gateway_observation_off"
    assert design["operator_approval_ref"] == "approval_ref_phase13_enablement_design_contract"
    assert design["default_enabled"] is False
    assert design["candidate_touchpoints"] == phase12["controlled_gateway_observation"]["candidate_touchpoints"]
    assert design["allowed_surfaces"] == phase12["controlled_gateway_observation"]["allowed_surfaces"]
    assert design["evidence_mode"] == "sanitized_observation_summaries_only"
    assert design["allowed_summary_inputs"] == ALLOWED_SUMMARY_INPUTS
    assert design["rollout_steps"] == ROLLOUT_STEPS
    assert design["rollback_mode"] == "feature_flag_off_first"
    assert design["kill_switch_required"] is True
    assert design["stable_error_codes"] == []
    assert len(design["safe_digest"]) == 16
    assert design["approvals"] == PHASE13_REQUIRED_APPROVALS
    assert design["side_effects"] == []
    assert result["artifact_policy"] == {
        "artifact_mode": "safe_summary_only",
        "allowed_fields": ARTIFACT_ALLOWED_FIELDS,
        "retention": "local_artifact_only",
        "log_policy": "sanitized_codes_only",
        "forbidden_material": PHASE12_FORBIDDEN_MATERIAL,
        "side_effects": [],
    }
    assert result["rollback_policy"] == {
        "rollback_mode": "feature_flag_off_first",
        "kill_switch_required": True,
        "config_revert_required": True,
        "gateway_restart_requires_separate_approval": True,
        "production_enablement_requires_separate_approval": True,
        "live_disable_verification_required": True,
        "side_effects": [],
    }
    assert_no_forbidden_output(result)


@pytest.mark.parametrize(
    ("mutate", "error_code"),
    [
        (lambda report: report.update({"ok": False, "verdict": "blocked"}), "invalid_phase12_report"),
        (lambda report: report.update({"verdict": "production_ready"}), "production_action_requested"),
        (lambda report: report.update({"live_enabled": True}), "production_action_requested"),
        (lambda report: report.pop("checks"), "invalid_phase12_report"),
        (lambda report: report["checks"].update({"side_effects_absent": False}), "invalid_phase12_report"),
        (
            lambda report: report.update(
                {"required_separate_approvals": PHASE12_REQUIRED_APPROVALS + ["gateway_restart"]}
            ),
            "invalid_phase12_report",
        ),
        (
            lambda report: report.update({"required_separate_approvals": list(reversed(PHASE12_REQUIRED_APPROVALS))}),
            "invalid_phase12_report",
        ),
        (
            lambda report: report.update({"verification_matrix": list(reversed(PHASE12_VERIFICATION_MATRIX))}),
            "invalid_phase12_report",
        ),
        (lambda report: report.update({"side_effects": ["would_send"]}), "side_effects_not_absent"),
        (lambda report: report.update({"raw_gateway_event": "raw_gateway_event_value"}), "unsafe_material"),
    ],
)
def test_phase13_design_rejects_non_exact_or_unsafe_phase12_reports(mutate, error_code: str) -> None:
    report = safe_phase12_report()
    mutate(report)

    assert_blocked(design_with(phase12_observation_hook_report=report), error_code)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda report: report.update({"observation_mode": "live_projection"}),
        lambda report: report.update({"runbook_outline": list(reversed(PHASE12_RUNBOOK_OUTLINE))}),
        lambda report: report["controlled_gateway_observation"].update({"summary_inputs": ["phase11_design_report"]}),
        lambda report: report["controlled_gateway_observation"].update(
            {"approvals": list(reversed(PHASE12_REQUIRED_APPROVALS))}
        ),
        lambda report: report["controlled_gateway_observation"].update({"stable_error_codes": ["raw_error"]}),
        lambda report: report["artifact_policy"].update({"log_policy": "raw_logs"}),
        lambda report: report["artifact_policy"].update({"forbidden_material": []}),
    ],
)
def test_phase13_design_rejects_non_exact_nested_phase12_observation_and_policy_values(mutate) -> None:
    report = safe_phase12_report()
    mutate(report)

    assert_blocked(design_with(phase12_observation_hook_report=report), "invalid_phase12_report")


@pytest.mark.parametrize(
    ("mutate", "error_code"),
    [
        (lambda report: report["controlled_gateway_observation"].__setitem__("candidate_touchpoints", ["task_tracker_snapshot"]), "invalid_phase12_report"),
        (lambda report: report["controlled_gateway_observation"].__setitem__("allowed_surfaces", ["final_text"]), "invalid_phase12_report"),
        (
            lambda report: report["controlled_gateway_observation"]["shadow_runtime_publication"].__setitem__(
                "surfaces", ["final_text"]
            ),
            "invalid_phase12_report",
        ),
        (
            lambda report: report["controlled_gateway_observation"]["shadow_runtime_publication"].__setitem__(
                "publication_count", 0
            ),
            "invalid_phase12_report",
        ),
        (
            lambda report: report["controlled_gateway_observation"]["shadow_runtime_publication"].__setitem__(
                "ack_update_count", 0
            ),
            "invalid_phase12_report",
        ),
        (
            lambda report: report["controlled_gateway_observation"]["progress_snapshot"].__setitem__(
                "visible_event_count", 0
            ),
            "invalid_phase12_report",
        ),
        (
            lambda report: report["controlled_gateway_observation"].__setitem__("safe_digest", "0" * 16),
            "invalid_phase12_report",
        ),
        (
            lambda report: report.__setitem__("observation_id", "controlled_gateway_observation_hook_0000000000000000"),
            "invalid_phase12_report",
        ),
        (
            lambda report: report["controlled_gateway_observation"].__setitem__(
                "stable_error_codes", ["phase13_extra_error"]
            ),
            "invalid_phase12_report",
        ),
        (
            lambda report: [
                report["controlled_gateway_observation"][name].__setitem__("stable_error_codes", ["temporal_worker_started"])
                for name in ("shadow_runtime_publication", "delivery_state", "progress_snapshot")
            ]
            and report["controlled_gateway_observation"].__setitem__(
                "stable_error_codes", ["temporal_worker_started"]
            ),
            "runtime_lifecycle_requested",
        ),
    ],
)
def test_phase13_design_rejects_phase12_nested_values_that_do_not_match_exact_safe_hook_output(
    mutate,
    error_code: str,
) -> None:
    report = safe_phase12_report()
    mutate(report)

    assert_blocked(design_with(phase12_observation_hook_report=report), error_code)


@pytest.mark.parametrize(
    ("factory_name", "mutate", "error_code"),
    [
        ("enablement", lambda value: value.update({"default_enabled": True}), "live_observation_requested"),
        ("enablement", lambda value: value.update({"config_write_allowed": True}), "registry_or_config_write_requested"),
        ("enablement", lambda value: value.update({"gateway_restart_allowed": True}), "production_action_requested"),
        ("enablement", lambda value: value.update({"adapter_calls_allowed": True}), "production_action_requested"),
        ("enablement", lambda value: value.update({"temporal_lifecycle_allowed": True}), "runtime_lifecycle_requested"),
        ("enablement", lambda value: value.update({"side_effects": ["would_restart_gateway"]}), "side_effects_not_absent"),
        ("evidence", lambda value: value.update({"raw_material_allowed": True}), "unsafe_material"),
        ("evidence", lambda value: value.update({"allowed_inputs": ["raw_gateway_event"]}), "unsafe_material"),
        ("artifact", lambda value: value.update({"log_policy": "raw_logs"}), "invalid_artifact_policy"),
        ("artifact", lambda value: value.update({"forbidden_material": []}), "invalid_artifact_policy"),
        ("rollback", lambda value: value.update({"kill_switch_required": False}), "invalid_rollback_policy"),
        ("rollback", lambda value: value.update({"side_effects": ["would_write_config"]}), "side_effects_not_absent"),
    ],
)
def test_phase13_design_rejects_unsafe_enablement_evidence_artifact_or_rollback_policy(
    factory_name: str,
    mutate,
    error_code: str,
) -> None:
    kwargs = {
        "enablement_policy": safe_enablement_policy(),
        "observation_evidence_policy": safe_observation_evidence_policy(),
        "artifact_policy": safe_artifact_policy(),
        "rollback_policy": safe_rollback_policy(),
    }
    value = kwargs[
        {
            "enablement": "enablement_policy",
            "evidence": "observation_evidence_policy",
            "artifact": "artifact_policy",
            "rollback": "rollback_policy",
        }[factory_name]
    ]
    mutate(value)

    assert_blocked(design_with(**kwargs), error_code)


def test_phase13_design_maps_hostile_objects_to_safe_blocked_report_without_serializing_them() -> None:
    class HostileReport(dict):
        pass

    hostile = HostileReport(safe_phase12_report())
    hostile["note"] = "raw_prompt_value platform_payload_value oc_phase13_private_chat"

    result = design_with(phase12_observation_hook_report=hostile)

    assert_blocked(result, "invalid_phase12_report")
    assert_no_forbidden_output(result)


def test_phase13_design_source_stays_out_of_live_gateway_runtime_surfaces() -> None:
    source = (
        ROOT
        / "prototypes"
        / "flowweaver_phase5c_runtime_client"
        / "src"
        / "flowweaver_runtime_client"
        / "live_gateway_observation_enablement_design.py"
    ).read_text()
    forbidden_static_markers = [
        "gateway.platforms",
        "gateway.run",
        "run_agent",
        "tools.registry",
        "temporalio",
        "Client.connect",
        "Worker",
        "WorkflowEnvironment",
        "start_workflow",
        "execute_update",
        "signal_" + "with_start",
        "sub" + "process",
        "dock" + "er",
        "system" + "ctl",
        "so" + "cket",
        "Path.write_",
        "logger.",
        "logging.",
        "print(",
        "repr(",
    ]
    for marker in forbidden_static_markers:
        assert marker not in source
