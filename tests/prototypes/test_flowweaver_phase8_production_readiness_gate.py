"""RED contract tests for FlowWeaver Phase 8 production readiness gate."""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE5C_SRC = ROOT / "prototypes" / "flowweaver_phase5c_runtime_client" / "src"
if str(PHASE5C_SRC) not in sys.path:
    sys.path.insert(0, str(PHASE5C_SRC))

WORKFLOW_ID = "runtime_tx_phase8_readiness"
REQUIRED_APPROVALS = {
    "production_gateway_wiring",
    "production_config_write",
    "gateway_restart",
    "external_temporal_service",
    "real_send_edit_render_callback",
    "production_tool_registry",
    "remote_branch_or_worktree_cleanup",
}
REPORT_FIELDS = {
    "type",
    "version",
    "ok",
    "verdict",
    "phase",
    "workflow_id",
    "transaction_id",
    "candidate_contract",
    "checks",
    "required_separate_approvals",
    "runbook_outline",
    "side_effects",
    "error_code",
}
ERROR_CODES = {
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
FORBIDDEN_OUTPUT_VALUES = (
    "production_enabled",
    "live_enabled",
    "oc_phase8_private_chat",
    "ou_phase8_private_user",
    "raw_prompt_payload",
    "platform_payload_value",
    "card_payload_value",
    "media_path_value",
    "https://example.invalid/callback?access_" + "token=phase8",
    "postgres" + "://phase8.invalid/db",
    "unsafe-" + "token" + "-phase8",
    "Bearer " + "phase8secretvalue0000000000",
)


def import_gate_module():
    return importlib.import_module("flowweaver_runtime_client.production_readiness_gate")


def safe_phase7_result() -> dict[str, object]:
    return {
        "ok": True,
        "loop_version": "flowweaver.gateway_shadow_e2e_loop.v0",
        "operation": "gateway_shadow_e2e_loop",
        "workflow_id": WORKFLOW_ID,
        "transaction_id": WORKFLOW_ID,
        "start_status": "started",
        "publication": {
            "type": "flowweaver.gateway_shadow_publication.v0",
            "loop_version": "flowweaver.gateway_shadow_e2e_loop.v0",
            "workflow_id": WORKFLOW_ID,
            "transaction_id": WORKFLOW_ID,
            "surface_counts": {"final_text": 1, "rich_card": 1, "progress_card": 0, "media": 0},
            "delivery_plan": [
                {
                    "delivery_key": "runtime_event_phase8_final_text_ack",
                    "surface": "final_text",
                    "target_kind": "delivery",
                    "target_id": "runtime_delivery_0",
                    "status": "sent",
                },
                {
                    "delivery_key": "runtime_event_phase8_rich_card_ack",
                    "surface": "rich_card",
                    "target_kind": "delivery",
                    "target_id": "runtime_delivery_1",
                    "status": "acknowledged",
                },
            ],
            "side_effects": [],
        },
        "ack_results": [
            {"target_id": "runtime_delivery_0", "surface": "final_text", "status": "sent", "ack_status": "applied"},
            {
                "target_id": "runtime_delivery_1",
                "surface": "rich_card",
                "status": "acknowledged",
                "ack_status": "applied",
            },
        ],
        "final_snapshot": {
            "type": "flowweaver.temporal_poc.snapshot.v0",
            "version": "flowweaver.temporal_poc.v0",
            "transaction_id": WORKFLOW_ID,
            "status": "running",
            "entry_count": 1,
            "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 2},
            "counts": {"intents": 1, "artifacts": 1, "deliveries": 2},
            "intent_statuses": {"runtime_intent_0": "pending"},
            "artifact_statuses": {"runtime_artifact_0": "available"},
            "delivery_statuses": {"runtime_delivery_0": "sent", "runtime_delivery_1": "acknowledged"},
            "applied_event_count": 2,
            "resume_count": 0,
            "side_effects": [],
        },
        "checks": {
            "start_accepted": True,
            "initial_snapshot_safe": True,
            "publication_envelope_safe": True,
            "delivery_targets_initialized": True,
            "ack_count_matches_publication": True,
            "final_snapshot_safe": True,
            "side_effects_absent": True,
        },
        "side_effects": [],
    }


def safe_gateway_boundary() -> dict[str, object]:
    return {
        "type": "flowweaver.gateway_boundary_descriptor.v0",
        "mode": "controlled_shadow_candidate",
        "surfaces": ["final_text", "rich_card"],
        "ack_source": "phase6_shadow_bridge",
        "delivery_effects": "none",
        "adapter_imports_allowed": False,
        "platform_payloads_allowed": False,
        "raw_card_payloads_allowed": False,
        "message_identifiers_allowed": False,
        "side_effects": [],
    }


def safe_runtime_boundary() -> dict[str, object]:
    return {
        "type": "flowweaver.runtime_boundary_descriptor.v0",
        "control_surface": "phase5k_control_surface",
        "temporal_dependency": "optional_extra_only",
        "client_lifecycle": "caller_supplied_only",
        "event_ingress": "validated_updates_only",
        "claim_check_policy": "refs_only",
        "side_effects": [],
    }


def safe_operational_policy() -> dict[str, object]:
    return {
        "type": "flowweaver.operational_policy.v0",
        "default_state": "off",
        "production_actions_require_separate_approval": True,
        "rollback_required": True,
        "observability_required": True,
        "config_write_allowed": False,
        "registry_write_allowed": False,
        "service_lifecycle_allowed": False,
        "gateway_restart_allowed": False,
        "side_effects": [],
    }


def evaluate(
    *,
    phase7_result: object | None = None,
    gateway_boundary: object | None = None,
    runtime_boundary: object | None = None,
    operational_policy: object | None = None,
) -> dict[str, object]:
    module = import_gate_module()
    return module.evaluate_flowweaver_production_readiness(
        phase7_result=safe_phase7_result() if phase7_result is None else phase7_result,
        gateway_boundary=safe_gateway_boundary() if gateway_boundary is None else gateway_boundary,
        runtime_boundary=safe_runtime_boundary() if runtime_boundary is None else runtime_boundary,
        operational_policy=safe_operational_policy() if operational_policy is None else operational_policy,
    )


def assert_safe_report_shape(result: dict[str, object]) -> None:
    assert type(result) is dict
    assert set(result) <= REPORT_FIELDS
    assert result["type"] == "flowweaver.production_readiness_report.v0"
    assert result["version"] == "flowweaver.production_readiness_gate.v0"
    assert result["phase"] == "phase8_production_readiness_gate"
    assert result["side_effects"] == []


def assert_error(result: dict[str, object], code: str) -> None:
    assert_safe_report_shape(result)
    assert result["ok"] is False
    assert result["verdict"] == "blocked"
    assert result["error_code"] == code
    assert code in ERROR_CODES
    assert "candidate_contract" not in result
    rendered = repr(result)
    for forbidden in FORBIDDEN_OUTPUT_VALUES:
        assert forbidden not in rendered


class HostilePhase7(dict):
    pass


def test_phase8_gate_import_is_default_off_sync_pure_and_narrow() -> None:
    for module_name in (
        "flowweaver_runtime_client.production_readiness_gate",
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

    module = import_gate_module()

    assert module.FLOWWEAVER_PRODUCTION_READINESS_GATE_VERSION == "flowweaver.production_readiness_gate.v0"
    assert module.GATEWAY_BOUNDARY_DESCRIPTOR_TYPE == "flowweaver.gateway_boundary_descriptor.v0"
    assert module.READINESS_REPORT_TYPE == "flowweaver.production_readiness_report.v0"
    assert not inspect.iscoroutinefunction(module.evaluate_flowweaver_production_readiness)
    signature = inspect.signature(module.evaluate_flowweaver_production_readiness)
    assert list(signature.parameters) == ["phase7_result", "gateway_boundary", "runtime_boundary", "operational_policy"]
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())
    assert sorted(module.__all__) == [
        "FLOWWEAVER_PRODUCTION_READINESS_GATE_VERSION",
        "GATEWAY_BOUNDARY_DESCRIPTOR_TYPE",
        "READINESS_REPORT_TYPE",
        "evaluate_flowweaver_production_readiness",
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


def test_phase8_gate_returns_ready_report_for_safe_phase7_result_and_shadow_boundaries() -> None:
    result = evaluate()

    assert_safe_report_shape(result)
    assert result["ok"] is True
    assert result["verdict"] == "ready_for_controlled_shadow_design"
    assert result["workflow_id"] == WORKFLOW_ID
    assert result["transaction_id"] == WORKFLOW_ID
    assert set(result["required_separate_approvals"]) == REQUIRED_APPROVALS
    assert result["checks"] == {
        "phase7_result_safe": True,
        "gateway_boundary_shadow_only": True,
        "runtime_boundary_lifecycle_free": True,
        "operational_policy_default_off": True,
        "delivery_targets_match_snapshot": True,
        "production_actions_separate": True,
        "side_effects_absent": True,
    }
    assert result["candidate_contract"] == {
        "contract_version": "flowweaver.controlled_shadow_candidate.v0",
        "runtime_operations": ["start_transaction", "query_transaction", "reconcile_delivery_ack"],
        "ack_bridge_version": "flowweaver.gateway_ack_shadow_bridge.v0",
        "shadow_loop_version": "flowweaver.gateway_shadow_e2e_loop.v0",
        "allowed_surfaces": ["final_text", "rich_card"],
        "forbidden_material": [
            "raw_prompt",
            "raw_tool_output",
            "raw_card_json",
            "raw_media_payload",
            "raw_platform_payload",
            "platform_message_identifiers",
            "credentials_or_connection_strings",
        ],
        "fail_closed_errors": sorted(ERROR_CODES),
        "rollback_hooks_required": True,
    }
    assert result["runbook_outline"] == [
        "phase8_proves_readiness_only",
        "production_activation_requires_separate_design_and_approval",
        "keep_default_off_until_explicit_enablement",
        "rollback_plan_required_before_gateway_wiring",
        "no_raw_payloads_or_secrets_in_reports_or_runtime_history",
        "use_direct_pytest_for_integration_regression",
    ]
    rendered = repr(result)
    assert "production_enabled" not in rendered
    assert "live_enabled" not in rendered


def test_phase8_gate_rejects_invalid_phase7_results_before_candidate_contract() -> None:
    invalid_cases: list[tuple[dict[str, object], str]] = []

    ok_false = safe_phase7_result()
    ok_false["ok"] = False
    invalid_cases.append((ok_false, "invalid_phase7_result"))

    missing_check = safe_phase7_result()
    del missing_check["checks"]["final_snapshot_safe"]
    invalid_cases.append((missing_check, "invalid_phase7_result"))

    false_check = safe_phase7_result()
    false_check["checks"]["ack_count_matches_publication"] = False
    invalid_cases.append((false_check, "invalid_phase7_result"))

    side_effects = safe_phase7_result()
    side_effects["side_effects"] = ["would_send"]
    invalid_cases.append((side_effects, "side_effects_not_absent"))

    mismatch = safe_phase7_result()
    mismatch["transaction_id"] = "runtime_tx_phase8_other"
    invalid_cases.append((mismatch, "workflow_id_mismatch"))

    missing_delivery = safe_phase7_result()
    missing_delivery["publication"]["delivery_plan"][1]["target_id"] = "runtime_delivery_2"
    invalid_cases.append((missing_delivery, "delivery_target_mismatch"))

    unknown = safe_phase7_result()
    unknown["extra_field"] = "surprise"
    invalid_cases.append((unknown, "invalid_phase7_result"))

    for phase7_result, error_code in invalid_cases:
        assert_error(evaluate(phase7_result=phase7_result), error_code)


def test_phase8_gate_rejects_production_gateway_boundary_intent() -> None:
    production_mode = safe_gateway_boundary()
    production_mode["mode"] = "production"
    assert_error(evaluate(gateway_boundary=production_mode), "production_action_requested")

    live_effect = safe_gateway_boundary()
    live_effect["delivery_effects"] = "send"
    assert_error(evaluate(gateway_boundary=live_effect), "production_action_requested")

    adapter_import = safe_gateway_boundary()
    adapter_import["adapter_imports_allowed"] = True
    assert_error(evaluate(gateway_boundary=adapter_import), "production_action_requested")

    raw_payload = safe_gateway_boundary()
    raw_payload["platform_payloads_allowed"] = True
    assert_error(evaluate(gateway_boundary=raw_payload), "unsafe_material")

    message_ids = safe_gateway_boundary()
    message_ids["message_identifiers_allowed"] = True
    assert_error(evaluate(gateway_boundary=message_ids), "unsafe_material")

    unknown_surface = safe_gateway_boundary()
    unknown_surface["surfaces"] = ["final_text", "callback"]
    assert_error(evaluate(gateway_boundary=unknown_surface), "invalid_gateway_boundary")


def test_phase8_gate_rejects_runtime_lifecycle_and_signal_intent() -> None:
    client_factory = safe_runtime_boundary()
    client_factory["client_lifecycle"] = "client_factory"
    assert_error(evaluate(runtime_boundary=client_factory), "runtime_lifecycle_requested")

    temporal_address = safe_runtime_boundary()
    temporal_address["temporal_address"] = "127.0.0.1:7233"
    assert_error(evaluate(runtime_boundary=temporal_address), "runtime_lifecycle_requested")

    signal_ingress = safe_runtime_boundary()
    signal_ingress["event_ingress"] = "payload_carrying_signals"
    assert_error(evaluate(runtime_boundary=signal_ingress), "runtime_lifecycle_requested")

    base_dependency = safe_runtime_boundary()
    base_dependency["temporal_dependency"] = "base_dependency_required"
    assert_error(evaluate(runtime_boundary=base_dependency), "runtime_lifecycle_requested")


def test_phase8_gate_rejects_config_registry_service_and_restart_policy() -> None:
    config_write = safe_operational_policy()
    config_write["config_write_allowed"] = True
    assert_error(evaluate(operational_policy=config_write), "registry_or_config_write_requested")

    registry_write = safe_operational_policy()
    registry_write["registry_write_allowed"] = True
    assert_error(evaluate(operational_policy=registry_write), "registry_or_config_write_requested")

    service_lifecycle = safe_operational_policy()
    service_lifecycle["service_lifecycle_allowed"] = True
    assert_error(evaluate(operational_policy=service_lifecycle), "runtime_lifecycle_requested")

    gateway_restart = safe_operational_policy()
    gateway_restart["gateway_restart_allowed"] = True
    assert_error(evaluate(operational_policy=gateway_restart), "production_action_requested")

    default_on = safe_operational_policy()
    default_on["default_state"] = "on"
    assert_error(evaluate(operational_policy=default_on), "production_action_requested")


def test_phase8_gate_rejects_hostile_material_and_non_plain_mappings_without_leaking_values() -> None:
    private_id = "oc_" + "phase8_private_chat"
    private_user = "ou_" + "phase8_private_user"
    hostile_phase7 = safe_phase7_result()
    hostile_phase7["platform_payload"] = {"chat_id": private_id, "user_id": private_user}
    hostile_phase7["card_json"] = "card_payload_value"
    hostile_phase7["media_path"] = "media_path_value"
    hostile_phase7["note"] = "unsafe-" + "token" + "-phase8"

    hostile_gateway = safe_gateway_boundary()
    hostile_gateway["callback_url"] = "https://example.invalid/callback?access_" + "token=phase8"

    hostile_runtime = safe_runtime_boundary()
    hostile_runtime["connection_string"] = "postgres" + "://phase8.invalid/db"

    for kwargs in (
        {"phase7_result": hostile_phase7},
        {"gateway_boundary": hostile_gateway},
        {"runtime_boundary": hostile_runtime},
        {"phase7_result": HostilePhase7(safe_phase7_result())},
    ):
        result = evaluate(**kwargs)
        assert result["ok"] is False
        rendered = repr(result)
        for forbidden in FORBIDDEN_OUTPUT_VALUES + (private_id, private_user):
            assert forbidden not in rendered
        assert set(result) <= REPORT_FIELDS


def test_phase8_gate_rejects_nested_phase7_forbidden_material_and_private_snapshot_ids() -> None:
    nested_material = safe_phase7_result()
    nested_material["final_snapshot"]["forbidden_material"] = ["raw_prompt_payload", "unsafe-" + "token" + "-phase8"]
    assert_error(evaluate(phase7_result=nested_material), "unsafe_material")

    nested_material_policy_names_only = safe_phase7_result()
    nested_material_policy_names_only["final_snapshot"]["forbidden_material"] = ["raw_prompt", "raw_tool_output"]
    assert_error(evaluate(phase7_result=nested_material_policy_names_only), "unsafe_material")

    nested_runbook_policy_name = safe_phase7_result()
    nested_runbook_policy_name["final_snapshot"]["runbook_outline"] = [
        "no_raw_payloads_or_secrets_in_reports_or_runtime_history"
    ]
    assert_error(evaluate(phase7_result=nested_runbook_policy_name), "unsafe_material")

    nested_raw_value = safe_phase7_result()
    nested_raw_value["final_snapshot"]["audit_notes"] = ["raw_card_json"]
    assert_error(evaluate(phase7_result=nested_raw_value), "unsafe_material")

    private_snapshot_id = safe_phase7_result()
    private_snapshot_id["final_snapshot"]["intent_statuses"] = {"oc_" + "phase8_private_chat": "pending"}
    assert_error(evaluate(phase7_result=private_snapshot_id), "unsafe_material")


def test_phase8_gate_returns_stable_error_for_malformed_descriptor_value_types() -> None:
    malformed_gateway = safe_gateway_boundary()
    malformed_gateway["mode"] = []

    assert_error(evaluate(gateway_boundary=malformed_gateway), "invalid_gateway_boundary")
