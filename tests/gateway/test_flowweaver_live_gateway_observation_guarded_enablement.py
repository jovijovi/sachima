"""RED contract tests for FlowWeaver Phase 17 guarded live Gateway observation enablement."""

from __future__ import annotations

import copy
import importlib
import importlib.util
import inspect
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE16_TEST_PATH = ROOT / "tests" / "gateway" / "test_flowweaver_live_gateway_observation_operator_decision.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WORKFLOW_ID = "runtime_tx_phase11_gateway_observation"
PHASE17_REQUIRED_APPROVALS = [
    "guarded_live_gateway_observation_enablement_validation",
    "live_gateway_observation_enablement",
    "production_gateway_wiring",
    "production_config_write",
    "gateway_restart",
    "external_temporal_service",
    "real_send_edit_render_callback",
    "production_tool_registry",
    "remote_branch_or_worktree_cleanup",
]
PHASE16_REQUIRED_APPROVALS = [
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
PHASE16_VERIFICATION_MATRIX = [
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
PHASE17_VERIFICATION_MATRIX = [
    "phase16_decision_exact_shape",
    "phase16_evidence_not_live_enablement",
    "guarded_enablement_policy_default_off",
    "approval_token_absent_reference_only",
    "guarded_enablement_not_authorized",
    "live_observation_not_enabled",
    "sanitized_guarded_enablement_artifact_only",
    "production_actions_separate",
    "registry_config_write_absent",
    "runtime_lifecycle_absent",
    "gateway_runtime_wiring_absent",
    "side_effects_absent",
]
PHASE16_RUNBOOK_OUTLINE = [
    "phase16_is_operator_decision_gate_only",
    "operator_decision_requires_separate_live_enablement_approval",
    "approval_token_reference_only_no_secret_material",
    "keep_feature_flag_off_until_explicit_live_enablement",
    "kill_switch_and_rollback_armed_before_any_enablement",
    "no_gateway_run_or_platform_adapter_wiring",
    "no_temporal_client_worker_docker_or_service_lifecycle",
    "no_raw_payloads_or_secrets_in_reports_or_artifacts",
    "use_direct_pytest_for_gateway_regression",
]
PHASE17_RUNBOOK_OUTLINE = [
    "phase17_is_guarded_enablement_contract_only",
    "guarded_enablement_requires_separate_validation",
    "live_enablement_requires_separate_operator_approval",
    "approval_token_reference_only_no_secret_material",
    "keep_feature_flag_off_until_explicit_live_enablement",
    "kill_switch_and_rollback_armed_before_any_enablement",
    "no_gateway_run_or_platform_adapter_wiring",
    "no_temporal_client_worker_docker_or_service_lifecycle",
    "no_raw_payloads_or_secrets_in_reports_or_artifacts",
    "use_direct_pytest_for_gateway_regression",
]
FORBIDDEN_MATERIAL = [
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
PHASE17_ERROR_CODES = sorted(
    {
        "invalid_phase16_decision",
        "invalid_guarded_enablement_policy",
        "guarded_enablement_requested",
        "live_observation_requested",
        "production_action_requested",
        "registry_or_config_write_requested",
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
    "enablement_id",
    "phase16_decision_id",
    "phase15_review_id",
    "phase14_request_id",
    "phase13_design_id",
    "phase12_observation_id",
    "phase11_design_id",
    "phase10_run_id",
    "plan_transaction_id",
    "enablement_mode",
    "guarded_enablement",
    "checks",
    "artifact_policy",
    "rollback_policy",
    "required_separate_approvals",
    "verification_matrix",
    "runbook_outline",
    "side_effects",
}
BLOCKED_FIELDS = {"type", "version", "ok", "verdict", "phase", "error_code", "side_effects"}
GUARDED_ENABLEMENT_FIELDS = {
    "source_decision_verdict",
    "feature_flag_ref",
    "operator_approval_ref",
    "operator_decision_ref",
    "guarded_enablement_ref",
    "implementation_review_ref",
    "approval_token_required",
    "approval_token_supplied",
    "approval_token_material_allowed",
    "guarded_enablement_authorized",
    "default_enabled",
    "requested_enabled",
    "live_observation_active",
    "shadow_observation_only",
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
ARTIFACT_ALLOWED_FIELDS = [
    "enablement_id",
    "phase16_decision_id",
    "phase15_review_id",
    "phase14_request_id",
    "phase13_design_id",
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
    "oc_phase17_private_chat",
    "ou_phase17_private_user",
    "message_phase17_private",
    "raw_gateway_event_value",
    "raw_prompt_value",
    "raw_tool_output_value",
    "platform_payload_value",
    "callback_payload_value",
    "https://example.invalid/callback?access_" + "token=phase17",
    "postgres" + "://phase17.invalid/db",
    "Bearer " + "phase17secretvalue0000000000",
)


def import_guarded_enablement_module():
    return importlib.import_module("gateway.flowweaver_live_gateway_observation_guarded_enablement")


def phase16_helpers():
    spec = importlib.util.spec_from_file_location("phase16_test_helpers_for_phase17", PHASE16_TEST_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def safe_phase16_decision() -> dict[str, object]:
    return copy.deepcopy(phase16_helpers().decide_with())


def safe_guarded_enablement_policy() -> dict[str, object]:
    return {
        "type": "flowweaver.live_gateway_observation_guarded_enablement_policy.v0",
        "mode": "guarded_enablement_implementation_default_off",
        "implementation_scope": "guarded_live_gateway_observation_enablement_contract",
        "source_decision_verdict": "ready_for_guarded_live_gateway_observation_enablement_implementation",
        "feature_flag_ref": "feature_flag_ref_phase13_live_gateway_observation_off",
        "operator_approval_ref": "approval_ref_phase13_enablement_design_contract",
        "operator_decision_ref": "operator_decision_ref_phase16_default_off_gate",
        "guarded_enablement_ref": "guarded_enablement_ref_phase17_default_off_contract",
        "implementation_review_ref": "implementation_review_ref_phase17_guarded_contract",
        "approval_token_required": True,
        "approval_token_supplied": False,
        "approval_token_material_allowed": False,
        "guarded_enablement_authorized": False,
        "default_enabled": False,
        "requested_enabled": False,
        "live_observation_enabled": False,
        "config_write_allowed": False,
        "gateway_restart_allowed": False,
        "adapter_calls_allowed": False,
        "platform_payloads_allowed": False,
        "temporal_lifecycle_allowed": False,
        "registry_write_allowed": False,
        "kill_switch_ref": "kill_switch_ref_phase14_live_gateway_observation_default_off",
        "kill_switch_armed": True,
        "rollback_mode": "feature_flag_off_first",
        "side_effects": [],
    }


def enable_with(
    *,
    phase16_decision: object | None = None,
    guarded_enablement_policy: object | None = None,
) -> dict[str, object]:
    module = import_guarded_enablement_module()
    return module.prepare_flowweaver_live_gateway_observation_guarded_enablement(
        phase16_decision=safe_phase16_decision() if phase16_decision is None else phase16_decision,
        guarded_enablement_policy=(
            safe_guarded_enablement_policy() if guarded_enablement_policy is None else guarded_enablement_policy
        ),
    )


def assert_no_forbidden_output(value: object) -> None:
    text = repr(value)
    for forbidden in FORBIDDEN_OUTPUT_VALUES:
        assert forbidden not in text


def assert_blocked(result: dict[str, object], error_code: str) -> None:
    assert type(result) is dict
    assert set(result) == BLOCKED_FIELDS
    assert result == {
        "type": "flowweaver.live_gateway_observation_guarded_enablement_report.v0",
        "version": "flowweaver.live_gateway_observation_guarded_enablement.v0",
        "ok": False,
        "verdict": "blocked",
        "phase": "phase17_guarded_live_gateway_observation_enablement",
        "error_code": error_code,
        "side_effects": [],
    }
    assert error_code in PHASE17_ERROR_CODES
    assert_no_forbidden_output(result)


def digest16(*parts: object) -> str:
    return sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:16]


def expected_phase16_decision_id(decision: dict[str, object]) -> str:
    return "live_gateway_observation_operator_decision_" + digest16(
        decision["phase15_review_id"],
        decision["operator_decision"]["operator_decision_ref"],
        decision["plan_transaction_id"],
    )


def expected_phase16_operator_decision_digest(decision: dict[str, object]) -> str:
    operator_decision = decision["operator_decision"]
    return digest16(
        decision["decision_id"],
        decision["phase14_request_id"],
        "default_off_operator_decision_gate",
    )


def recompute_phase16_derivatives(decision: dict[str, object]) -> dict[str, object]:
    decision["decision_id"] = expected_phase16_decision_id(decision)
    decision["operator_decision"]["safe_digest"] = expected_phase16_operator_decision_digest(decision)
    return decision


def test_phase17_guarded_enablement_helper_import_is_sync_gateway_side_and_narrow() -> None:
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

    module = import_guarded_enablement_module()

    assert not inspect.iscoroutinefunction(module.prepare_flowweaver_live_gateway_observation_guarded_enablement)
    signature = inspect.signature(module.prepare_flowweaver_live_gateway_observation_guarded_enablement)
    assert list(signature.parameters) == ["phase16_decision", "guarded_enablement_policy"]
    assert all(param.kind is inspect.Parameter.KEYWORD_ONLY for param in signature.parameters.values())
    assert "gateway.run" not in sys.modules
    assert "gateway.platforms.feishu" not in sys.modules
    assert "tools.registry" not in sys.modules
    assert "temporalio" not in sys.modules


def test_phase17_success_output_is_safe_default_off_guarded_enablement_artifact() -> None:
    phase16_decision = safe_phase16_decision()
    result = enable_with(phase16_decision=phase16_decision)

    assert type(result) is dict
    assert set(result) == SUCCESS_FIELDS
    assert result["type"] == "flowweaver.live_gateway_observation_guarded_enablement_report.v0"
    assert result["version"] == "flowweaver.live_gateway_observation_guarded_enablement.v0"
    assert result["ok"] is True
    assert result["verdict"] == "ready_for_guarded_live_gateway_observation_validation"
    assert result["phase"] == "phase17_guarded_live_gateway_observation_enablement"
    assert result["enablement_id"].startswith("live_gateway_observation_guarded_enablement_")
    assert result["phase16_decision_id"] == phase16_decision["decision_id"]
    assert result["phase15_review_id"] == phase16_decision["phase15_review_id"]
    assert result["phase14_request_id"] == phase16_decision["phase14_request_id"]
    assert result["phase13_design_id"] == phase16_decision["phase13_design_id"]
    assert result["phase12_observation_id"] == phase16_decision["phase12_observation_id"]
    assert result["phase11_design_id"] == phase16_decision["phase11_design_id"]
    assert result["phase10_run_id"] == phase16_decision["phase10_run_id"]
    assert result["plan_transaction_id"] == WORKFLOW_ID
    assert result["enablement_mode"] == "guarded_enablement_implementation_default_off"
    assert result["side_effects"] == []
    assert result["required_separate_approvals"] == PHASE17_REQUIRED_APPROVALS
    assert result["verification_matrix"] == PHASE17_VERIFICATION_MATRIX
    assert result["runbook_outline"] == PHASE17_RUNBOOK_OUTLINE
    assert result["checks"] == {name: True for name in PHASE17_VERIFICATION_MATRIX}

    guarded_enablement = result["guarded_enablement"]
    assert type(guarded_enablement) is dict
    assert set(guarded_enablement) == GUARDED_ENABLEMENT_FIELDS
    assert guarded_enablement["source_decision_verdict"] == "ready_for_guarded_live_gateway_observation_enablement_implementation"
    assert guarded_enablement["feature_flag_ref"] == "feature_flag_ref_phase13_live_gateway_observation_off"
    assert guarded_enablement["operator_approval_ref"] == "approval_ref_phase13_enablement_design_contract"
    assert guarded_enablement["operator_decision_ref"] == "operator_decision_ref_phase16_default_off_gate"
    assert guarded_enablement["guarded_enablement_ref"] == "guarded_enablement_ref_phase17_default_off_contract"
    assert guarded_enablement["implementation_review_ref"] == "implementation_review_ref_phase17_guarded_contract"
    assert guarded_enablement["approval_token_required"] is True
    assert guarded_enablement["approval_token_supplied"] is False
    assert guarded_enablement["approval_token_material_allowed"] is False
    assert guarded_enablement["guarded_enablement_authorized"] is False
    assert guarded_enablement["default_enabled"] is False
    assert guarded_enablement["requested_enabled"] is False
    assert guarded_enablement["live_observation_active"] is False
    assert guarded_enablement["shadow_observation_only"] is True
    assert guarded_enablement["config_write_allowed"] is False
    assert guarded_enablement["gateway_restart_allowed"] is False
    assert guarded_enablement["adapter_calls_allowed"] is False
    assert guarded_enablement["platform_payloads_allowed"] is False
    assert guarded_enablement["temporal_lifecycle_allowed"] is False
    assert guarded_enablement["registry_write_allowed"] is False
    assert guarded_enablement["kill_switch_ref"] == "kill_switch_ref_phase14_live_gateway_observation_default_off"
    assert guarded_enablement["kill_switch_armed"] is True
    assert guarded_enablement["rollback_mode"] == "feature_flag_off_first"
    assert guarded_enablement["rollout_steps"] == phase16_decision["operator_decision"]["rollout_steps"]
    assert guarded_enablement["allowed_summary_inputs"] == phase16_decision["operator_decision"]["allowed_summary_inputs"]
    assert guarded_enablement["candidate_touchpoints"] == phase16_decision["operator_decision"]["candidate_touchpoints"]
    assert guarded_enablement["allowed_surfaces"] == phase16_decision["operator_decision"]["allowed_surfaces"]
    assert guarded_enablement["stable_error_codes"] == []
    assert len(guarded_enablement["safe_digest"]) == 16
    assert all(char in "0123456789abcdef" for char in guarded_enablement["safe_digest"])
    assert guarded_enablement["approvals"] == PHASE17_REQUIRED_APPROVALS
    assert guarded_enablement["side_effects"] == []
    assert_no_forbidden_output(result)


def test_phase17_artifact_and_rollback_policies_remain_safe_summary_only() -> None:
    result = enable_with()

    assert result["artifact_policy"] == {
        "artifact_mode": "safe_summary_only",
        "allowed_fields": ARTIFACT_ALLOWED_FIELDS,
        "retention": "local_artifact_only",
        "log_policy": "sanitized_codes_only",
        "forbidden_material": FORBIDDEN_MATERIAL,
        "side_effects": [],
    }
    assert result["rollback_policy"] == {
        "rollback_mode": "feature_flag_off_first",
        "kill_switch_ref": "kill_switch_ref_phase14_live_gateway_observation_default_off",
        "kill_switch_armed": True,
        "config_revert_required": True,
        "gateway_restart_requires_separate_approval": True,
        "production_enablement_requires_separate_approval": True,
        "live_disable_verification_required": True,
        "side_effects": [],
    }


def test_phase17_ids_and_digests_are_deterministic_and_do_not_use_private_material() -> None:
    first = enable_with()
    second = enable_with()
    assert first["enablement_id"] == second["enablement_id"]
    assert first["guarded_enablement"]["safe_digest"] == second["guarded_enablement"]["safe_digest"]

    phase16_decision = safe_phase16_decision()
    phase16_decision["phase16_private_marker"] = "oc_phase17_private_chat"
    assert_blocked(enable_with(phase16_decision=phase16_decision), "invalid_phase16_decision")


def test_phase17_blocks_non_exact_or_mutated_phase16_decision() -> None:
    assert_blocked(enable_with(phase16_decision=[]), "invalid_phase16_decision")

    phase16_decision = safe_phase16_decision()
    phase16_decision["type"] = "flowweaver.wrong.v0"
    assert_blocked(enable_with(phase16_decision=phase16_decision), "invalid_phase16_decision")

    phase16_decision = safe_phase16_decision()
    phase16_decision["extra_runtime_payload"] = "raw_gateway_event_value"
    assert_blocked(enable_with(phase16_decision=phase16_decision), "invalid_phase16_decision")

    phase16_decision = safe_phase16_decision()
    phase16_decision["operator_decision"]["feature_flag_ref"] = "feature_flag_ref_other"
    assert_blocked(enable_with(phase16_decision=phase16_decision), "invalid_phase16_decision")

    phase16_decision = safe_phase16_decision()
    phase16_decision["required_separate_approvals"] = list(reversed(PHASE16_REQUIRED_APPROVALS))
    assert_blocked(enable_with(phase16_decision=phase16_decision), "invalid_phase16_decision")

    phase16_decision = safe_phase16_decision()
    phase16_decision["verification_matrix"] = PHASE16_VERIFICATION_MATRIX + ["unexpected_check"]
    assert_blocked(enable_with(phase16_decision=phase16_decision), "invalid_phase16_decision")

    phase16_decision = safe_phase16_decision()
    phase16_decision["side_effects"] = ["write_config"]
    assert_blocked(enable_with(phase16_decision=phase16_decision), "side_effects_not_absent")


def test_phase17_rejects_tampered_phase16_ids_and_operator_decision_digest() -> None:
    decision = safe_phase16_decision()
    assert decision["decision_id"] == expected_phase16_decision_id(decision)
    assert decision["operator_decision"]["safe_digest"] == expected_phase16_operator_decision_digest(decision)

    for key, bogus in {
        "decision_id": "live_gateway_observation_operator_decision_ffffffffffffffff",
        "phase15_review_id": "nonsense_but_safe_label",
        "phase14_request_id": "nonsense_but_safe_label",
        "phase13_design_id": "nonsense_but_safe_label",
        "phase12_observation_id": "nonsense_but_safe_label",
        "phase11_design_id": "nonsense_but_safe_label",
        "phase10_run_id": "nonsense_but_safe_label",
    }.items():
        phase16_decision = safe_phase16_decision()
        phase16_decision[key] = bogus
        assert_blocked(enable_with(phase16_decision=phase16_decision), "invalid_phase16_decision")

    phase16_decision = safe_phase16_decision()
    phase16_decision["operator_decision"]["safe_digest"] = "f" * 16
    assert_blocked(enable_with(phase16_decision=phase16_decision), "invalid_phase16_decision")

    phase16_decision = safe_phase16_decision()
    phase16_decision["operator_decision"]["safe_digest"] = "raw_prompt_value"
    assert_blocked(enable_with(phase16_decision=phase16_decision), "unsafe_material")


def test_phase17_rejects_internally_consistent_but_noncanonical_phase16_ids() -> None:
    for key, bogus in {
        "phase15_review_id": "live_gateway_observation_manual_review_ffffffffffffffff",
        "phase14_request_id": "live_gateway_observation_enablement_request_ffffffffffffffff",
        "phase13_design_id": "live_gateway_observation_enablement_design_ffffffffffffffff",
        "phase12_observation_id": "controlled_gateway_observation_hook_ffffffffffffffff",
        "phase11_design_id": "controlled_gateway_observation_design_ffffffffffffffff",
        "phase10_run_id": "controlled_shadow_run_other_safe_label",
    }.items():
        phase16_decision = safe_phase16_decision()
        phase16_decision[key] = bogus
        recompute_phase16_derivatives(phase16_decision)
        assert_blocked(enable_with(phase16_decision=phase16_decision), "invalid_phase16_decision")


def test_phase17_rejects_integer_boolean_impersonators() -> None:
    phase16_decision = safe_phase16_decision()
    phase16_decision["ok"] = 1
    assert_blocked(enable_with(phase16_decision=phase16_decision), "invalid_phase16_decision")

    phase16_decision = safe_phase16_decision()
    phase16_decision["checks"][PHASE16_VERIFICATION_MATRIX[0]] = 1
    assert_blocked(enable_with(phase16_decision=phase16_decision), "invalid_phase16_decision")

    phase16_decision = safe_phase16_decision()
    phase16_decision["operator_decision"]["approval_token_required"] = 1
    assert_blocked(enable_with(phase16_decision=phase16_decision), "invalid_phase16_decision")

    phase16_decision = safe_phase16_decision()
    phase16_decision["operator_decision"]["approval_token_supplied"] = 0
    assert_blocked(enable_with(phase16_decision=phase16_decision), "invalid_phase16_decision")

    phase16_decision = safe_phase16_decision()
    phase16_decision["rollback_policy"]["kill_switch_armed"] = 1
    assert_blocked(enable_with(phase16_decision=phase16_decision), "invalid_phase16_decision")

    policy = safe_guarded_enablement_policy()
    policy["approval_token_required"] = 1
    assert_blocked(enable_with(guarded_enablement_policy=policy), "invalid_guarded_enablement_policy")

    policy = safe_guarded_enablement_policy()
    policy["approval_token_supplied"] = 0
    assert_blocked(enable_with(guarded_enablement_policy=policy), "invalid_guarded_enablement_policy")

    policy = safe_guarded_enablement_policy()
    policy["kill_switch_armed"] = 1
    assert_blocked(enable_with(guarded_enablement_policy=policy), "invalid_guarded_enablement_policy")


def test_phase17_blocks_invalid_guarded_enablement_policy_shape_and_mode() -> None:
    assert_blocked(enable_with(guarded_enablement_policy=[]), "invalid_guarded_enablement_policy")

    policy = safe_guarded_enablement_policy()
    policy["mode"] = "live_enablement_now"
    assert_blocked(enable_with(guarded_enablement_policy=policy), "invalid_guarded_enablement_policy")

    policy = safe_guarded_enablement_policy()
    policy["extra_operator_token"] = "raw_prompt_value"
    assert_blocked(enable_with(guarded_enablement_policy=policy), "invalid_guarded_enablement_policy")

    policy = safe_guarded_enablement_policy()
    policy["side_effects"] = ["write_config"]
    assert_blocked(enable_with(guarded_enablement_policy=policy), "side_effects_not_absent")


def test_phase17_blocks_guarded_enablement_or_live_enablement_attempts() -> None:
    for field in ("approval_token_supplied", "guarded_enablement_authorized"):
        policy = safe_guarded_enablement_policy()
        policy[field] = True
        assert_blocked(enable_with(guarded_enablement_policy=policy), "guarded_enablement_requested")

    for field in ("default_enabled", "requested_enabled", "live_observation_enabled"):
        policy = safe_guarded_enablement_policy()
        policy[field] = True
        assert_blocked(enable_with(guarded_enablement_policy=policy), "live_observation_requested")


def test_phase17_blocks_production_registry_runtime_and_gateway_side_effect_requests() -> None:
    for field in ("config_write_allowed", "gateway_restart_allowed", "adapter_calls_allowed", "platform_payloads_allowed"):
        policy = safe_guarded_enablement_policy()
        policy[field] = True
        assert_blocked(enable_with(guarded_enablement_policy=policy), "production_action_requested")

    policy = safe_guarded_enablement_policy()
    policy["registry_write_allowed"] = True
    assert_blocked(enable_with(guarded_enablement_policy=policy), "registry_or_config_write_requested")

    policy = safe_guarded_enablement_policy()
    policy["temporal_lifecycle_allowed"] = True
    assert_blocked(enable_with(guarded_enablement_policy=policy), "runtime_lifecycle_requested")

    policy = safe_guarded_enablement_policy()
    policy["side_effects"] = ["restart_gateway"]
    assert_blocked(enable_with(guarded_enablement_policy=policy), "side_effects_not_absent")


def test_phase17_rejects_hostile_subclasses_before_projection() -> None:
    class SneakyDict(dict):
        pass

    class SneakyList(list):
        pass

    class SneakyStr(str):
        pass

    phase16_decision = safe_phase16_decision()
    assert_blocked(enable_with(phase16_decision=SneakyDict(phase16_decision)), "invalid_phase16_decision")

    phase16_decision = safe_phase16_decision()
    phase16_decision["required_separate_approvals"] = SneakyList(PHASE16_REQUIRED_APPROVALS)
    assert_blocked(enable_with(phase16_decision=phase16_decision), "invalid_phase16_decision")

    policy = safe_guarded_enablement_policy()
    policy["guarded_enablement_ref"] = SneakyStr("guarded_enablement_ref_phase17_default_off_contract")
    assert_blocked(enable_with(guarded_enablement_policy=policy), "invalid_guarded_enablement_policy")


def test_phase17_blocks_unsafe_raw_or_private_material_without_echoing_it() -> None:
    policy = safe_guarded_enablement_policy()
    policy["guarded_enablement_ref"] = "raw_prompt_value"
    assert_blocked(enable_with(guarded_enablement_policy=policy), "unsafe_material")

    phase16_decision = safe_phase16_decision()
    phase16_decision["operator_decision"]["operator_decision_ref"] = "oc_phase17_private_chat"
    result = enable_with(phase16_decision=phase16_decision)
    assert result["ok"] is False
    assert result["error_code"] in {"invalid_phase16_decision", "unsafe_material"}
    assert_no_forbidden_output(result)


def test_phase17_blocks_workflow_identity_mismatch() -> None:
    phase16_decision = safe_phase16_decision()
    phase16_decision["plan_transaction_id"] = "runtime_tx_other"
    assert_blocked(enable_with(phase16_decision=phase16_decision), "workflow_id_mismatch")


def test_phase17_source_has_no_runtime_or_platform_wiring_surface() -> None:
    source_path = ROOT / "gateway" / "flowweaver_live_gateway_observation_guarded_enablement.py"
    source = source_path.read_text(encoding="utf-8")

    forbidden_import_or_call_terms = (
        "gateway.run",
        "gateway.platforms",
        "tools.registry",
        "toolsets",
        "temporalio",
        "Client.connect",
        "WorkflowEnvironment",
        "Worker(",
        "start_workflow",
        "execute_update",
        "@workflow.signal",
        "signal_with_start",
        "subprocess",
        "socket.",
        "systemctl",
        "write_text",
        "write_bytes",
        "open(",
        "print(",
        "logger.",
        "logging.",
        "requests.",
        "httpx.",
        "aiohttp.",
    )
    for term in forbidden_import_or_call_terms:
        assert term not in source
