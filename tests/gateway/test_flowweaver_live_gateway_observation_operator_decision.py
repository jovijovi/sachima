"""RED contract tests for FlowWeaver Phase 16 live Gateway observation operator-decision gate."""

from __future__ import annotations

import copy
import importlib
import importlib.util
import inspect
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE15_TEST_PATH = ROOT / "tests" / "gateway" / "test_flowweaver_live_gateway_observation_manual_review.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WORKFLOW_ID = "runtime_tx_phase11_gateway_observation"
PHASE15_REQUIRED_APPROVALS = [
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
PHASE15_VERIFICATION_MATRIX = [
    "phase14_request_exact_shape",
    "phase14_evidence_not_live_enablement",
    "manual_review_policy_default_off",
    "approval_token_absent_reference_only",
    "operator_decision_not_granted",
    "sanitized_review_artifact_only",
    "production_actions_separate",
    "registry_config_write_absent",
    "runtime_lifecycle_absent",
    "gateway_runtime_wiring_absent",
    "side_effects_absent",
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
PHASE15_RUNBOOK_OUTLINE = [
    "phase15_is_manual_review_gate_only",
    "operator_decision_required_before_live_enablement",
    "approval_token_reference_only_no_secret_material",
    "keep_feature_flag_off_until_explicit_enablement_decision",
    "kill_switch_and_rollback_armed_before_any_enablement",
    "no_gateway_run_or_platform_adapter_wiring",
    "no_temporal_client_worker_docker_or_service_lifecycle",
    "no_raw_payloads_or_secrets_in_reports_or_artifacts",
    "use_direct_pytest_for_gateway_regression",
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
PHASE16_ERROR_CODES = sorted(
    {
        "invalid_phase15_review",
        "invalid_operator_decision_policy",
        "operator_decision_requested",
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
    "decision_id",
    "phase15_review_id",
    "phase14_request_id",
    "phase13_design_id",
    "phase12_observation_id",
    "phase11_design_id",
    "phase10_run_id",
    "plan_transaction_id",
    "decision_mode",
    "operator_decision",
    "checks",
    "artifact_policy",
    "rollback_policy",
    "required_separate_approvals",
    "verification_matrix",
    "runbook_outline",
    "side_effects",
}
BLOCKED_FIELDS = {"type", "version", "ok", "verdict", "phase", "error_code", "side_effects"}
DECISION_FIELDS = {
    "source_review_verdict",
    "feature_flag_ref",
    "operator_approval_ref",
    "operator_decision_ref",
    "approval_token_required",
    "approval_token_supplied",
    "approval_token_material_allowed",
    "operator_decision_recorded",
    "operator_decision_approved",
    "enablement_authorized",
    "default_enabled",
    "requested_enabled",
    "live_observation_active",
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
    "decision_id",
    "phase15_review_id",
    "phase14_request_id",
    "phase13_design_id",
    "phase12_observation_id",
    "phase11_design_id",
    "phase10_run_id",
    "plan_transaction_id",
    "decision_mode",
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
    "oc_phase16_private_chat",
    "ou_phase16_private_user",
    "message_phase16_private",
    "raw_gateway_event_value",
    "raw_prompt_value",
    "raw_tool_output_value",
    "platform_payload_value",
    "callback_payload_value",
    "https://example.invalid/callback?access_" + "token=phase16",
    "postgres" + "://phase16.invalid/db",
    "Bearer " + "phase16secretvalue0000000000",
)


def import_operator_decision_module():
    return importlib.import_module("gateway.flowweaver_live_gateway_observation_operator_decision")


def phase15_helpers():
    spec = importlib.util.spec_from_file_location("phase15_test_helpers_for_phase16", PHASE15_TEST_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def safe_phase15_review() -> dict[str, object]:
    return copy.deepcopy(phase15_helpers().review_with())


def safe_operator_decision_policy() -> dict[str, object]:
    return {
        "type": "flowweaver.live_gateway_observation_operator_decision_policy.v0",
        "mode": "default_off_operator_decision_gate",
        "decision_scope": "operator_live_gateway_observation_enablement_decision",
        "source_review_verdict": "ready_for_live_gateway_observation_enablement_operator_decision",
        "feature_flag_ref": "feature_flag_ref_phase13_live_gateway_observation_off",
        "operator_approval_ref": "approval_ref_phase13_enablement_design_contract",
        "operator_decision_ref": "operator_decision_ref_phase16_default_off_gate",
        "approval_token_required": True,
        "approval_token_supplied": False,
        "approval_token_material_allowed": False,
        "operator_decision_recorded": False,
        "operator_decision_approved": False,
        "enablement_authorized": False,
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


def decide_with(
    *,
    phase15_review: object | None = None,
    operator_decision_policy: object | None = None,
) -> dict[str, object]:
    module = import_operator_decision_module()
    return module.prepare_flowweaver_live_gateway_observation_operator_decision(
        phase15_review=safe_phase15_review() if phase15_review is None else phase15_review,
        operator_decision_policy=(
            safe_operator_decision_policy() if operator_decision_policy is None else operator_decision_policy
        ),
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
        "type": "flowweaver.live_gateway_observation_operator_decision_report.v0",
        "version": "flowweaver.live_gateway_observation_operator_decision.v0",
        "ok": False,
        "verdict": "blocked",
        "phase": "phase16_operator_live_gateway_observation_decision_gate",
        "error_code": error_code,
        "side_effects": [],
    }
    assert error_code in PHASE16_ERROR_CODES
    assert_no_forbidden_output(result)


def digest16(*parts: object) -> str:
    return sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:16]


def expected_phase15_review_id(review: dict[str, object]) -> str:
    return "live_gateway_observation_manual_review_" + digest16(
        review["phase14_request_id"],
        review["plan_transaction_id"],
        review["manual_review"]["reviewer_attestation_ref"],
    )


def expected_phase15_manual_review_digest(review: dict[str, object]) -> str:
    manual_review = review["manual_review"]
    return digest16(
        review["review_id"],
        review["phase14_request_id"],
        review["phase13_design_id"],
        review["phase12_observation_id"],
        review["phase11_design_id"],
        review["phase10_run_id"],
        review["plan_transaction_id"],
        *manual_review["stable_error_codes"],
    )


def recompute_phase15_derivatives(review: dict[str, object]) -> dict[str, object]:
    review["review_id"] = expected_phase15_review_id(review)
    review["manual_review"]["safe_digest"] = expected_phase15_manual_review_digest(review)
    return review


def test_phase16_operator_decision_helper_import_is_sync_gateway_side_and_narrow() -> None:
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

    module = import_operator_decision_module()

    assert module.FLOWWEAVER_LIVE_GATEWAY_OBSERVATION_OPERATOR_DECISION_VERSION == (
        "flowweaver.live_gateway_observation_operator_decision.v0"
    )
    assert module.LIVE_GATEWAY_OBSERVATION_OPERATOR_DECISION_REPORT_TYPE == (
        "flowweaver.live_gateway_observation_operator_decision_report.v0"
    )
    entrypoint = module.prepare_flowweaver_live_gateway_observation_operator_decision
    signature = inspect.signature(entrypoint)
    assert list(signature.parameters) == ["phase15_review", "operator_decision_policy"]
    assert all(param.kind is inspect.Parameter.KEYWORD_ONLY for param in signature.parameters.values())
    assert not inspect.iscoroutinefunction(entrypoint)

    assert "gateway.run" not in sys.modules
    assert "gateway.platforms.feishu" not in sys.modules
    assert "tools.registry" not in sys.modules
    assert "toolsets" not in sys.modules
    assert not any(name == "temporalio" or name.startswith("temporalio.") for name in sys.modules)


def test_phase16_success_output_is_safe_default_off_operator_decision_artifact() -> None:
    phase15_review = safe_phase15_review()
    result = decide_with(phase15_review=phase15_review)

    assert type(result) is dict
    assert set(result) == SUCCESS_FIELDS
    assert result["type"] == "flowweaver.live_gateway_observation_operator_decision_report.v0"
    assert result["version"] == "flowweaver.live_gateway_observation_operator_decision.v0"
    assert result["ok"] is True
    assert result["verdict"] == "ready_for_guarded_live_gateway_observation_enablement_implementation"
    assert result["phase"] == "phase16_operator_live_gateway_observation_decision_gate"
    assert result["decision_mode"] == "default_off_operator_decision_gate"
    assert result["phase15_review_id"] == phase15_review["review_id"]
    assert result["phase14_request_id"] == phase15_review["phase14_request_id"]
    assert result["phase13_design_id"] == phase15_review["phase13_design_id"]
    assert result["phase12_observation_id"] == phase15_review["phase12_observation_id"]
    assert result["phase11_design_id"] == phase15_review["phase11_design_id"]
    assert result["phase10_run_id"] == phase15_review["phase10_run_id"]
    assert result["plan_transaction_id"] == WORKFLOW_ID
    assert str(result["decision_id"]).startswith("live_gateway_observation_operator_decision_")
    assert len(str(result["decision_id"]).rsplit("_", 1)[-1]) == 16

    decision = result["operator_decision"]
    assert type(decision) is dict
    assert set(decision) == DECISION_FIELDS
    assert decision["source_review_verdict"] == "ready_for_live_gateway_observation_enablement_operator_decision"
    assert decision["feature_flag_ref"] == "feature_flag_ref_phase13_live_gateway_observation_off"
    assert decision["operator_approval_ref"] == "approval_ref_phase13_enablement_design_contract"
    assert decision["operator_decision_ref"] == "operator_decision_ref_phase16_default_off_gate"
    assert decision["approval_token_required"] is True
    assert decision["approval_token_supplied"] is False
    assert decision["approval_token_material_allowed"] is False
    assert decision["operator_decision_recorded"] is False
    assert decision["operator_decision_approved"] is False
    assert decision["enablement_authorized"] is False
    assert decision["default_enabled"] is False
    assert decision["requested_enabled"] is False
    assert decision["live_observation_active"] is False
    assert decision["config_write_allowed"] is False
    assert decision["gateway_restart_allowed"] is False
    assert decision["adapter_calls_allowed"] is False
    assert decision["platform_payloads_allowed"] is False
    assert decision["temporal_lifecycle_allowed"] is False
    assert decision["registry_write_allowed"] is False
    assert decision["kill_switch_ref"] == "kill_switch_ref_phase14_live_gateway_observation_default_off"
    assert decision["kill_switch_armed"] is True
    assert decision["rollback_mode"] == "feature_flag_off_first"
    assert decision["rollout_steps"] == phase15_review["manual_review"]["rollout_steps"]
    assert decision["allowed_summary_inputs"] == phase15_review["manual_review"]["allowed_summary_inputs"]
    assert decision["candidate_touchpoints"] == phase15_review["manual_review"]["candidate_touchpoints"]
    assert decision["allowed_surfaces"] == phase15_review["manual_review"]["allowed_surfaces"]
    assert decision["stable_error_codes"] == []
    assert decision["approvals"] == PHASE16_REQUIRED_APPROVALS
    assert decision["side_effects"] == []
    assert len(str(decision["safe_digest"])) == 16

    assert result["checks"] == {name: True for name in PHASE16_VERIFICATION_MATRIX}
    assert result["required_separate_approvals"] == PHASE16_REQUIRED_APPROVALS
    assert result["verification_matrix"] == PHASE16_VERIFICATION_MATRIX
    assert result["runbook_outline"] == PHASE16_RUNBOOK_OUTLINE
    assert result["side_effects"] == []
    assert_no_forbidden_output(result)


def test_phase16_artifact_and_rollback_policies_remain_safe_summary_only() -> None:
    result = decide_with()

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
    assert_no_forbidden_output(result)


def test_phase16_ids_and_digests_are_deterministic_and_do_not_use_private_material() -> None:
    first = decide_with()
    second = decide_with()

    assert first == second
    assert "oc_" not in repr(first)
    assert "ou_" not in repr(first)
    assert "om_" not in repr(first)


def test_phase16_blocks_non_exact_or_mutated_phase15_review() -> None:
    assert_blocked(decide_with(phase15_review=[]), "invalid_phase15_review")

    phase15_review = safe_phase15_review()
    phase15_review["type"] = "flowweaver.wrong.v0"
    assert_blocked(decide_with(phase15_review=phase15_review), "invalid_phase15_review")

    phase15_review = safe_phase15_review()
    phase15_review["extra_runtime_payload"] = "raw_gateway_event_value"
    assert_blocked(decide_with(phase15_review=phase15_review), "invalid_phase15_review")

    phase15_review = safe_phase15_review()
    phase15_review["manual_review"]["feature_flag_ref"] = "feature_flag_ref_other"
    assert_blocked(decide_with(phase15_review=phase15_review), "invalid_phase15_review")

    phase15_review = safe_phase15_review()
    phase15_review["required_separate_approvals"] = list(reversed(PHASE15_REQUIRED_APPROVALS))
    assert_blocked(decide_with(phase15_review=phase15_review), "invalid_phase15_review")

    phase15_review = safe_phase15_review()
    phase15_review["verification_matrix"] = PHASE15_VERIFICATION_MATRIX + ["unexpected_check"]
    assert_blocked(decide_with(phase15_review=phase15_review), "invalid_phase15_review")

    phase15_review = safe_phase15_review()
    phase15_review["side_effects"] = ["write_config"]
    assert_blocked(decide_with(phase15_review=phase15_review), "side_effects_not_absent")


def test_phase16_rejects_tampered_phase15_ids_and_manual_review_digest() -> None:
    review = safe_phase15_review()
    assert review["review_id"] == expected_phase15_review_id(review)
    assert review["manual_review"]["safe_digest"] == expected_phase15_manual_review_digest(review)

    for key, bogus in {
        "review_id": "live_gateway_observation_manual_review_ffffffffffffffff",
        "phase14_request_id": "nonsense_but_safe_label",
        "phase13_design_id": "nonsense_but_safe_label",
        "phase12_observation_id": "nonsense_but_safe_label",
        "phase11_design_id": "nonsense_but_safe_label",
        "phase10_run_id": "nonsense_but_safe_label",
    }.items():
        phase15_review = safe_phase15_review()
        phase15_review[key] = bogus
        assert_blocked(decide_with(phase15_review=phase15_review), "invalid_phase15_review")

    phase15_review = safe_phase15_review()
    phase15_review["manual_review"]["safe_digest"] = "f" * 16
    assert_blocked(decide_with(phase15_review=phase15_review), "invalid_phase15_review")

    phase15_review = safe_phase15_review()
    phase15_review["manual_review"]["safe_digest"] = "raw_prompt_value"
    assert_blocked(decide_with(phase15_review=phase15_review), "unsafe_material")


def test_phase16_rejects_internally_consistent_but_noncanonical_phase15_ids() -> None:
    for key, bogus in {
        "phase14_request_id": "live_gateway_observation_enablement_request_ffffffffffffffff",
        "phase13_design_id": "live_gateway_observation_enablement_design_ffffffffffffffff",
        "phase12_observation_id": "controlled_gateway_observation_hook_ffffffffffffffff",
        "phase11_design_id": "controlled_gateway_observation_design_ffffffffffffffff",
        "phase10_run_id": "controlled_shadow_run_other_safe_label",
    }.items():
        phase15_review = safe_phase15_review()
        phase15_review[key] = bogus
        recompute_phase15_derivatives(phase15_review)
        assert_blocked(decide_with(phase15_review=phase15_review), "invalid_phase15_review")


def test_phase16_blocks_invalid_operator_decision_policy_shape_and_mode() -> None:
    assert_blocked(decide_with(operator_decision_policy=[]), "invalid_operator_decision_policy")

    policy = safe_operator_decision_policy()
    policy["type"] = "flowweaver.wrong.v0"
    assert_blocked(decide_with(operator_decision_policy=policy), "invalid_operator_decision_policy")

    policy = safe_operator_decision_policy()
    policy["extra"] = "raw_prompt_value"
    assert_blocked(decide_with(operator_decision_policy=policy), "invalid_operator_decision_policy")

    policy = safe_operator_decision_policy()
    policy["mode"] = "live_enablement"
    assert_blocked(decide_with(operator_decision_policy=policy), "invalid_operator_decision_policy")

    policy = safe_operator_decision_policy()
    policy["side_effects"] = ["send"]
    assert_blocked(decide_with(operator_decision_policy=policy), "side_effects_not_absent")


def test_phase16_blocks_operator_decision_or_live_enablement_attempts() -> None:
    for field in ("operator_decision_recorded", "operator_decision_approved"):
        policy = safe_operator_decision_policy()
        policy[field] = True
        assert_blocked(decide_with(operator_decision_policy=policy), "operator_decision_requested")

    for field in ("enablement_authorized", "requested_enabled", "live_observation_enabled"):
        policy = safe_operator_decision_policy()
        policy[field] = True
        assert_blocked(decide_with(operator_decision_policy=policy), "live_observation_requested")

    policy = safe_operator_decision_policy()
    policy["approval_token_supplied"] = True
    assert_blocked(decide_with(operator_decision_policy=policy), "operator_decision_requested")

    policy = safe_operator_decision_policy()
    policy["approval_token_material_allowed"] = True
    assert_blocked(decide_with(operator_decision_policy=policy), "unsafe_material")


def test_phase16_blocks_production_registry_runtime_and_gateway_side_effect_requests() -> None:
    for field in ("config_write_allowed", "gateway_restart_allowed", "adapter_calls_allowed", "platform_payloads_allowed"):
        policy = safe_operator_decision_policy()
        policy[field] = True
        assert_blocked(decide_with(operator_decision_policy=policy), "production_action_requested")

    policy = safe_operator_decision_policy()
    policy["registry_write_allowed"] = True
    assert_blocked(decide_with(operator_decision_policy=policy), "registry_or_config_write_requested")

    policy = safe_operator_decision_policy()
    policy["temporal_lifecycle_allowed"] = True
    assert_blocked(decide_with(operator_decision_policy=policy), "runtime_lifecycle_requested")


def test_phase16_rejects_hostile_subclasses_before_projection() -> None:
    class SneakyDict(dict):
        pass

    class SneakyList(list):
        pass

    class SneakyStr(str):
        pass

    phase15_review = safe_phase15_review()
    assert_blocked(decide_with(phase15_review=SneakyDict(phase15_review)), "invalid_phase15_review")

    phase15_review = safe_phase15_review()
    phase15_review["required_separate_approvals"] = SneakyList(PHASE15_REQUIRED_APPROVALS)
    assert_blocked(decide_with(phase15_review=phase15_review), "invalid_phase15_review")

    policy = safe_operator_decision_policy()
    policy["operator_decision_ref"] = SneakyStr("operator_decision_ref_phase16_default_off_gate")
    assert_blocked(decide_with(operator_decision_policy=policy), "invalid_operator_decision_policy")


def test_phase16_blocks_unsafe_raw_or_private_material_without_echoing_it() -> None:
    policy = safe_operator_decision_policy()
    policy["operator_decision_ref"] = "raw_prompt_value"
    assert_blocked(decide_with(operator_decision_policy=policy), "unsafe_material")

    policy = safe_operator_decision_policy()
    policy["operator_decision_ref"] = "oc_phase16_private_chat"
    result = decide_with(operator_decision_policy=policy)
    assert_blocked(result, "unsafe_material")
    assert "oc_phase16_private_chat" not in repr(result)

    policy = safe_operator_decision_policy()
    policy["operator_decision_ref"] = "Bearer " + "phase16secretvalue0000000000"
    result = decide_with(operator_decision_policy=policy)
    assert_blocked(result, "unsafe_material")
    assert "phase16secretvalue" not in repr(result)


def test_phase16_blocks_workflow_identity_mismatch() -> None:
    phase15_review = safe_phase15_review()
    phase15_review["plan_transaction_id"] = "runtime_tx_other"
    assert_blocked(decide_with(phase15_review=phase15_review), "workflow_id_mismatch")


def test_phase16_source_has_no_runtime_or_platform_wiring_surface() -> None:
    source_path = ROOT / "gateway" / "flowweaver_live_gateway_observation_operator_decision.py"
    source = source_path.read_text(encoding="utf-8")
    lowered = source.lower()

    forbidden_markers = (
        "gateway.run",
        "gateway.platforms",
        "tools.registry",
        "model_tools",
        "toolsets",
        "systemctl",
        "daemon",
        "subprocess",
        "socket.",
        "config.yaml",
        "write_text",
        "write_bytes",
        "open(",
        "print(",
        "logger.",
        "logging.",
        "requests",
        "httpx",
        "aiohttp",
        "start_workflow",
        "execute_update",
        "workflowenvironment",
        "worker(",
        "client.connect",
        "temporalio",
        "@workflow.signal",
        ".signal(",
        "signal_with_start",
        "approval_token_material_allowed = true",
        "live_observation_enabled = true",
    )
    assert {marker for marker in forbidden_markers if marker in lowered} == set()
    assert "docker" not in lowered
    assert "from hashlib import sha256" in source
    assert source.count("import ") == 1
