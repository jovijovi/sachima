"""RED contract tests for FlowWeaver Phase 12 controlled Gateway observation hook."""

from __future__ import annotations

import copy
import importlib
import importlib.util
import inspect
import sys
from pathlib import Path

import pytest

from gateway.flowweaver_controlled_gateway_observation import (
    CONTROLLED_GATEWAY_OBSERVATION_HOOK_REPORT_TYPE,
    FLOWWEAVER_CONTROLLED_GATEWAY_OBSERVATION_HOOK_VERSION,
    build_flowweaver_controlled_gateway_observation,
)

ROOT = Path(__file__).resolve().parents[2]
PHASE5C_SRC = ROOT / "prototypes" / "flowweaver_phase5c_runtime_client" / "src"
PHASE11_TEST_PATH = ROOT / "tests" / "prototypes" / "test_flowweaver_phase11_controlled_gateway_observation_design.py"
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
SUCCESS_FIELDS = {
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
BLOCKED_FIELDS = {"type", "version", "ok", "verdict", "phase", "error_code", "side_effects"}
OBSERVATION_FIELDS = {
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
FORBIDDEN_OUTPUT_VALUES = (
    "production_ready",
    "production_enabled",
    "live_enabled",
    "gateway_enabled",
    "observation_enabled",
    "integration_enabled",
    "oc_phase12_private_chat",
    "ou_phase12_private_user",
    "message_phase12_private",
    "raw_gateway_event_value",
    "raw_prompt_value",
    "raw_tool_output_value",
    "platform_payload_value",
    "callback_payload_value",
    "https://example.invalid/callback?access_" + "token=phase12",
)


def phase11_helpers():
    spec = importlib.util.spec_from_file_location("phase11_test_helpers_for_phase12", PHASE11_TEST_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def safe_phase11_report() -> dict[str, object]:
    return copy.deepcopy(phase11_helpers().design_with())


def safe_shadow_runtime_publication_summary() -> dict[str, object]:
    return {
        "type": "flowweaver.gateway.shadow_runtime_publication.v0",
        "verdict": "ready",
        "reason": "ok",
        "runtime_model_version": "flowweaver.runtime.v0",
        "runtime_envelope_type": "flowweaver.runtime.ingress_envelope.v0",
        "transaction_id": WORKFLOW_ID,
        "workflow_id": WORKFLOW_ID,
        "start_status": "ready",
        "publication_count": 1,
        "ack_bridge": {
            "status": "ready",
            "update_count": 1,
            "surfaces": ["final_text", "rich_card"],
            "stable_error_codes": [],
            "side_effects": [],
        },
        "checks": {
            "shadow_capture_present": True,
            "dry_run_summary_valid": True,
            "runtime_envelope_valid": True,
            "start_request_safe": True,
            "delivery_ack_updates_safe": True,
            "payloads_absent": True,
            "visible_side_effects_absent": True,
            "runtime_side_effects_absent": True,
        },
        "side_effects": [],
    }


def safe_delivery_state_summary() -> dict[str, object]:
    return {
        "type": "flowweaver.gateway.delivery_state_summary.v0",
        "transaction_id": WORKFLOW_ID,
        "surface_counts": {"final_text": 1, "rich_card": 1, "progress_card": 0, "media": 0},
        "status_counts": {"sent": 1, "acknowledged": 1, "failed": 0},
        "stable_error_codes": [],
        "side_effects": [],
    }


def safe_progress_snapshot_summary() -> dict[str, object]:
    return {
        "type": "flowweaver.gateway.progress_snapshot_summary.v0",
        "transaction_id": WORKFLOW_ID,
        "event_counts": {"tool.started": 1, "tool.completed": 1},
        "visible_event_count": 2,
        "stable_error_codes": [],
        "side_effects": [],
    }


def observe_with(
    *,
    phase11_design_report: object | None = None,
    shadow_runtime_publication_summary: object | None = None,
    delivery_state_summary: object | None = None,
    progress_snapshot_summary: object | None = None,
    enabled: object = False,
) -> dict[str, object]:
    return build_flowweaver_controlled_gateway_observation(
        phase11_design_report=safe_phase11_report() if phase11_design_report is None else phase11_design_report,
        shadow_runtime_publication_summary=(
            safe_shadow_runtime_publication_summary()
            if shadow_runtime_publication_summary is None
            else shadow_runtime_publication_summary
        ),
        delivery_state_summary=safe_delivery_state_summary() if delivery_state_summary is None else delivery_state_summary,
        progress_snapshot_summary=(
            safe_progress_snapshot_summary() if progress_snapshot_summary is None else progress_snapshot_summary
        ),
        enabled=enabled,
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
        "type": "flowweaver.controlled_gateway_observation_hook_report.v0",
        "version": "flowweaver.controlled_gateway_observation_hook.v0",
        "ok": False,
        "verdict": "blocked",
        "phase": "phase12_controlled_gateway_observation_hook",
        "error_code": error_code,
        "side_effects": [],
    }
    assert error_code in PHASE12_ERROR_CODES
    assert_no_forbidden_output(result)


def test_phase12_hook_import_is_default_off_sync_and_narrow() -> None:
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

    module = importlib.import_module("gateway.flowweaver_controlled_gateway_observation")

    assert FLOWWEAVER_CONTROLLED_GATEWAY_OBSERVATION_HOOK_VERSION == (
        "flowweaver.controlled_gateway_observation_hook.v0"
    )
    assert CONTROLLED_GATEWAY_OBSERVATION_HOOK_REPORT_TYPE == (
        "flowweaver.controlled_gateway_observation_hook_report.v0"
    )
    assert not inspect.iscoroutinefunction(module.build_flowweaver_controlled_gateway_observation)
    signature = inspect.signature(module.build_flowweaver_controlled_gateway_observation)
    assert list(signature.parameters) == [
        "phase11_design_report",
        "shadow_runtime_publication_summary",
        "delivery_state_summary",
        "progress_snapshot_summary",
        "enabled",
    ]
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())
    assert sorted(module.__all__) == [
        "CONTROLLED_GATEWAY_OBSERVATION_HOOK_REPORT_TYPE",
        "FLOWWEAVER_CONTROLLED_GATEWAY_OBSERVATION_HOOK_VERSION",
        "build_flowweaver_controlled_gateway_observation",
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


def test_phase12_hook_builds_safe_default_off_projection_from_exact_phase11_evidence() -> None:
    phase11 = safe_phase11_report()

    result = observe_with(phase11_design_report=phase11)

    assert type(result) is dict
    assert set(result) == SUCCESS_FIELDS
    assert result["type"] == "flowweaver.controlled_gateway_observation_hook_report.v0"
    assert result["version"] == "flowweaver.controlled_gateway_observation_hook.v0"
    assert result["ok"] is True
    assert result["verdict"] == "ready_for_live_gateway_observation_enablement_design"
    assert result["phase"] == "phase12_controlled_gateway_observation_hook"
    assert result["observation_id"].startswith("controlled_gateway_observation_hook_")
    assert result["phase11_design_id"] == phase11["design_id"]
    assert result["phase10_run_id"] == phase11["phase10_run_id"]
    assert result["plan_transaction_id"] == WORKFLOW_ID
    assert result["observation_mode"] == "default_off_static_projection"
    assert result["checks"] == {key: True for key in PHASE12_VERIFICATION_MATRIX}
    assert result["required_separate_approvals"] == PHASE12_REQUIRED_APPROVALS
    assert result["verification_matrix"] == PHASE12_VERIFICATION_MATRIX
    assert result["runbook_outline"] == PHASE12_RUNBOOK_OUTLINE
    assert result["side_effects"] == []

    observation = result["controlled_gateway_observation"]
    assert set(observation) == OBSERVATION_FIELDS
    assert observation["source_design_verdict"] == "ready_for_controlled_gateway_observation_implementation"
    assert observation["candidate_touchpoints"] == phase11["controlled_gateway_observation_plan"]["candidate_touchpoints"]
    assert observation["allowed_surfaces"] == phase11["controlled_gateway_observation_plan"]["allowed_surfaces"]
    assert observation["summary_inputs"] == [
        "phase11_design_report",
        "shadow_runtime_publication_summary",
        "delivery_state_summary",
        "progress_snapshot_summary",
    ]
    assert observation["shadow_runtime_publication"] == {
        "type": "flowweaver.gateway.shadow_runtime_publication.v0",
        "verdict": "ready",
        "workflow_id": WORKFLOW_ID,
        "transaction_id": WORKFLOW_ID,
        "publication_count": 1,
        "ack_update_count": 1,
        "surfaces": ["final_text", "rich_card"],
        "stable_error_codes": [],
        "side_effects": [],
    }
    assert observation["delivery_state"] == {
        "surface_counts": {"final_text": 1, "rich_card": 1, "progress_card": 0, "media": 0},
        "status_counts": {"sent": 1, "acknowledged": 1, "failed": 0},
        "stable_error_codes": [],
        "side_effects": [],
    }
    assert observation["progress_snapshot"] == {
        "event_counts": {"tool.started": 1, "tool.completed": 1},
        "visible_event_count": 2,
        "stable_error_codes": [],
        "side_effects": [],
    }
    assert observation["stable_error_codes"] == []
    assert len(observation["safe_digest"]) == 16
    assert observation["approvals"] == PHASE12_REQUIRED_APPROVALS
    assert observation["side_effects"] == []
    assert result["artifact_policy"] == {
        "artifact_mode": "safe_summary_only",
        "log_policy": "sanitized_codes_only",
        "forbidden_material": phase11["controlled_gateway_observation_plan"]["forbidden_material"],
        "side_effects": [],
    }
    assert_no_forbidden_output(result)


@pytest.mark.parametrize(
    ("mutate", "error_code"),
    [
        (lambda report: report.update({"ok": False, "verdict": "blocked"}), "invalid_phase11_report"),
        (lambda report: report.update({"verdict": "production_ready"}), "production_action_requested"),
        (lambda report: report.update({"gateway_enabled": True}), "production_action_requested"),
        (lambda report: report.pop("checks"), "invalid_phase11_report"),
        (lambda report: report["checks"].update({"side_effects_absent": False}), "invalid_phase11_report"),
        (
            lambda report: report.update(
                {"required_separate_approvals": PHASE12_REQUIRED_APPROVALS + ["gateway_restart"]}
            ),
            "invalid_phase11_report",
        ),
        (
            lambda report: report.update({"required_separate_approvals": list(reversed(PHASE12_REQUIRED_APPROVALS))}),
            "invalid_phase11_report",
        ),
        (
            lambda report: report.update({"verification_matrix": list(reversed(PHASE12_VERIFICATION_MATRIX))}),
            "invalid_phase11_report",
        ),
        (lambda report: report.update({"side_effects": ["would_send"]}), "side_effects_not_absent"),
        (lambda report: report.update({"raw_gateway_event": "raw_gateway_event_value"}), "unsafe_material"),
    ],
)
def test_phase12_hook_rejects_non_exact_or_unsafe_phase11_reports(mutate, error_code: str) -> None:
    report = safe_phase11_report()
    mutate(report)

    assert_blocked(observe_with(phase11_design_report=report), error_code)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda report: report["artifact_policy"].update({"log_policy": "raw_logs"}),
        lambda report: report["artifact_policy"].update({"forbidden_material": []}),
        lambda report: report["rollback_policy"].update({"rollback_mode": "production_redeploy"}),
        lambda report: report["rollback_policy"].update({"kill_switch_required": False}),
        lambda report: report["controlled_gateway_observation_plan"].update(
            {"observation_inputs": ["phase10_report"]}
        ),
        lambda report: report["controlled_gateway_observation_plan"].update(
            {"runtime_operations": ["query_transaction"]}
        ),
        lambda report: report["controlled_gateway_observation_plan"].update(
            {
                "approval_refs": {
                    "operator_approval_ref": "approval_ref_phase11_implementation_contract",
                    "feature_flag_ref": "feature_flag_ref_phase11_controlled_gateway_observation_off",
                    "extra": "benign_label",
                }
            }
        ),
    ],
)
def test_phase12_hook_rejects_non_exact_nested_phase11_plan_and_policy_values(mutate) -> None:
    report = safe_phase11_report()
    mutate(report)

    assert_blocked(observe_with(phase11_design_report=report), "invalid_phase11_report")


@pytest.mark.parametrize("enabled", [True, "true", 1])
def test_phase12_hook_rejects_live_enablement_requests(enabled: object) -> None:
    assert_blocked(observe_with(enabled=enabled), "live_observation_requested")


@pytest.mark.parametrize(
    ("summary_factory", "mutate", "error_code"),
    [
        (
            safe_shadow_runtime_publication_summary,
            lambda value: value.update({"verdict": "live_enabled"}),
            "production_action_requested",
        ),
        (
            safe_shadow_runtime_publication_summary,
            lambda value: value.update({"workflow_id": "runtime_tx_phase12_other"}),
            "workflow_id_mismatch",
        ),
        (
            safe_shadow_runtime_publication_summary,
            lambda value: value["ack_bridge"].update({"raw_platform_payload": "platform_payload_value"}),
            "unsafe_material",
        ),
        (
            safe_shadow_runtime_publication_summary,
            lambda value: value.update({"side_effects": ["would_start_runtime"]}),
            "side_effects_not_absent",
        ),
        (
            safe_delivery_state_summary,
            lambda value: value.update({"chat_id": "oc_phase12_private_chat"}),
            "unsafe_material",
        ),
        (
            safe_delivery_state_summary,
            lambda value: value.update({"side_effects": ["would_edit"]}),
            "side_effects_not_absent",
        ),
        (
            safe_progress_snapshot_summary,
            lambda value: value.update({"raw_prompt": "raw_prompt_value"}),
            "unsafe_material",
        ),
        (
            safe_progress_snapshot_summary,
            lambda value: value.update({"side_effects": ["would_log_raw"]}),
            "side_effects_not_absent",
        ),
    ],
)
def test_phase12_hook_rejects_unsafe_shadow_delivery_or_progress_summaries(
    summary_factory,
    mutate,
    error_code: str,
) -> None:
    summary = summary_factory()
    mutate(summary)
    kwargs = {
        "shadow_runtime_publication_summary": safe_shadow_runtime_publication_summary(),
        "delivery_state_summary": safe_delivery_state_summary(),
        "progress_snapshot_summary": safe_progress_snapshot_summary(),
    }
    if summary_factory is safe_shadow_runtime_publication_summary:
        kwargs["shadow_runtime_publication_summary"] = summary
    elif summary_factory is safe_delivery_state_summary:
        kwargs["delivery_state_summary"] = summary
    else:
        kwargs["progress_snapshot_summary"] = summary

    assert_blocked(observe_with(**kwargs), error_code)


def test_phase12_hook_maps_hostile_objects_to_safe_blocked_report_without_serializing_them() -> None:
    class HostileReport(dict):
        pass

    hostile = HostileReport(safe_phase11_report())
    hostile["note"] = "raw_prompt_value platform_payload_value oc_phase12_private_chat"

    result = observe_with(phase11_design_report=hostile)

    assert_blocked(result, "invalid_phase11_report")
    assert_no_forbidden_output(result)


def test_phase12_hook_source_stays_out_of_live_gateway_runtime_surfaces() -> None:
    source = (ROOT / "gateway" / "flowweaver_controlled_gateway_observation.py").read_text()
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
        "logger.debug",
        "logging.",
        "print(",
        "repr(",
    ]
    for marker in forbidden_static_markers:
        assert marker not in source
