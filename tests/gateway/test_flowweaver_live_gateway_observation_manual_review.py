"""RED contract tests for FlowWeaver Phase 15 manual live Gateway observation review gate."""

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
PHASE14_TEST_PATH = ROOT / "tests" / "gateway" / "test_flowweaver_live_gateway_observation_enablement.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(PHASE5C_SRC) not in sys.path:
    sys.path.insert(0, str(PHASE5C_SRC))

WORKFLOW_ID = "runtime_tx_phase11_gateway_observation"
PHASE14_REQUIRED_APPROVALS = [
    "manual_live_gateway_observation_enablement_request_review",
    "live_gateway_observation_enablement",
    "production_gateway_wiring",
    "production_config_write",
    "gateway_restart",
    "external_temporal_service",
    "real_send_edit_render_callback",
    "production_tool_registry",
    "remote_branch_or_worktree_cleanup",
]
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
PHASE14_VERIFICATION_MATRIX = [
    "phase13_design_report_exact_shape",
    "phase13_evidence_not_live_enablement",
    "request_policy_default_off",
    "approval_token_reference_only",
    "feature_flag_kill_switch_and_rollback_armed",
    "sanitized_request_artifact_only",
    "production_actions_separate",
    "registry_config_write_absent",
    "runtime_lifecycle_absent",
    "gateway_runtime_wiring_absent",
    "side_effects_absent",
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
PHASE14_RUNBOOK_OUTLINE = [
    "phase14_is_default_off_enablement_request_only",
    "manual_request_review_required_before_live_enablement",
    "approval_token_reference_only_no_secret_material",
    "keep_feature_flag_off_until_explicit_manual_enablement",
    "kill_switch_and_rollback_armed_before_any_enablement",
    "no_gateway_run_or_platform_adapter_wiring",
    "no_temporal_client_worker_docker_or_service_lifecycle",
    "no_raw_payloads_or_secrets_in_reports_or_artifacts",
    "use_direct_pytest_for_gateway_regression",
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
PHASE15_ERROR_CODES = sorted(
    {
        "invalid_phase14_request",
        "invalid_review_policy",
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
    "review_id",
    "phase14_request_id",
    "phase13_design_id",
    "phase12_observation_id",
    "phase11_design_id",
    "phase10_run_id",
    "plan_transaction_id",
    "review_mode",
    "manual_review",
    "checks",
    "artifact_policy",
    "rollback_policy",
    "required_separate_approvals",
    "verification_matrix",
    "runbook_outline",
    "side_effects",
}
BLOCKED_FIELDS = {"type", "version", "ok", "verdict", "phase", "error_code", "side_effects"}
REVIEW_FIELDS = {
    "source_request_verdict",
    "feature_flag_ref",
    "operator_approval_ref",
    "reviewer_attestation_ref",
    "approval_token_required",
    "approval_token_supplied",
    "approval_token_material_allowed",
    "review_approved",
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
    "review_id",
    "phase14_request_id",
    "phase13_design_id",
    "phase12_observation_id",
    "phase11_design_id",
    "phase10_run_id",
    "plan_transaction_id",
    "review_mode",
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
    "oc_phase15_private_chat",
    "ou_phase15_private_user",
    "message_phase15_private",
    "raw_gateway_event_value",
    "raw_prompt_value",
    "raw_tool_output_value",
    "platform_payload_value",
    "callback_payload_value",
    "https://example.invalid/callback?access_" + "token=phase15",
    "postgres" + "://phase15.invalid/db",
    "Bearer " + "phase15secretvalue0000000000",
)


def import_manual_review_module():
    return importlib.import_module("gateway.flowweaver_live_gateway_observation_manual_review")


def phase14_helpers():
    spec = importlib.util.spec_from_file_location("phase14_test_helpers_for_phase15", PHASE14_TEST_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def safe_phase14_request() -> dict[str, object]:
    return copy.deepcopy(phase14_helpers().prepare_with())


def safe_review_policy() -> dict[str, object]:
    return {
        "type": "flowweaver.live_gateway_observation_manual_review_policy.v0",
        "mode": "default_off_operator_review_gate",
        "review_scope": "manual_live_gateway_observation_enablement_request_review",
        "source_request_verdict": "ready_for_manual_live_gateway_observation_enablement_request_review",
        "feature_flag_ref": "feature_flag_ref_phase13_live_gateway_observation_off",
        "operator_approval_ref": "approval_ref_phase13_enablement_design_contract",
        "reviewer_attestation_ref": "review_attestation_ref_phase15_manual_gate",
        "approval_token_required": True,
        "approval_token_supplied": False,
        "approval_token_material_allowed": False,
        "review_approved": False,
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


def review_with(
    *,
    phase14_request: object | None = None,
    review_policy: object | None = None,
) -> dict[str, object]:
    module = import_manual_review_module()
    return module.prepare_flowweaver_live_gateway_observation_manual_review(
        phase14_request=safe_phase14_request() if phase14_request is None else phase14_request,
        review_policy=safe_review_policy() if review_policy is None else review_policy,
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
        "type": "flowweaver.live_gateway_observation_manual_review_report.v0",
        "version": "flowweaver.live_gateway_observation_manual_review.v0",
        "ok": False,
        "verdict": "blocked",
        "phase": "phase15_manual_live_gateway_observation_review_gate",
        "error_code": error_code,
        "side_effects": [],
    }
    assert error_code in PHASE15_ERROR_CODES
    assert_no_forbidden_output(result)


def test_phase15_manual_review_helper_import_is_sync_gateway_side_and_narrow() -> None:
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

    module = import_manual_review_module()

    assert module.FLOWWEAVER_LIVE_GATEWAY_OBSERVATION_MANUAL_REVIEW_VERSION == (
        "flowweaver.live_gateway_observation_manual_review.v0"
    )
    assert module.LIVE_GATEWAY_OBSERVATION_MANUAL_REVIEW_REPORT_TYPE == (
        "flowweaver.live_gateway_observation_manual_review_report.v0"
    )
    assert not inspect.iscoroutinefunction(module.prepare_flowweaver_live_gateway_observation_manual_review)
    signature = inspect.signature(module.prepare_flowweaver_live_gateway_observation_manual_review)
    assert list(signature.parameters) == ["phase14_request", "review_policy"]
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())
    assert sorted(module.__all__) == [
        "FLOWWEAVER_LIVE_GATEWAY_OBSERVATION_MANUAL_REVIEW_VERSION",
        "LIVE_GATEWAY_OBSERVATION_MANUAL_REVIEW_REPORT_TYPE",
        "prepare_flowweaver_live_gateway_observation_manual_review",
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


def test_phase15_builds_default_off_operator_review_gate_from_exact_phase14_request() -> None:
    phase14 = safe_phase14_request()

    result = review_with(phase14_request=phase14)

    assert type(result) is dict
    assert set(result) == SUCCESS_FIELDS
    assert result["type"] == "flowweaver.live_gateway_observation_manual_review_report.v0"
    assert result["version"] == "flowweaver.live_gateway_observation_manual_review.v0"
    assert result["ok"] is True
    assert result["verdict"] == "ready_for_live_gateway_observation_enablement_operator_decision"
    assert result["phase"] == "phase15_manual_live_gateway_observation_review_gate"
    assert result["review_id"].startswith("live_gateway_observation_manual_review_")
    assert result["phase14_request_id"] == phase14["request_id"]
    assert result["phase13_design_id"] == phase14["phase13_design_id"]
    assert result["phase12_observation_id"] == phase14["phase12_observation_id"]
    assert result["phase11_design_id"] == phase14["phase11_design_id"]
    assert result["phase10_run_id"] == phase14["phase10_run_id"]
    assert result["plan_transaction_id"] == WORKFLOW_ID
    assert result["review_mode"] == "default_off_operator_review_gate"
    assert result["checks"] == {key: True for key in PHASE15_VERIFICATION_MATRIX}
    assert result["required_separate_approvals"] == PHASE15_REQUIRED_APPROVALS
    assert result["verification_matrix"] == PHASE15_VERIFICATION_MATRIX
    assert result["runbook_outline"] == PHASE15_RUNBOOK_OUTLINE
    assert result["side_effects"] == []

    review = result["manual_review"]
    assert set(review) == REVIEW_FIELDS
    assert review["source_request_verdict"] == "ready_for_manual_live_gateway_observation_enablement_request_review"
    assert review["feature_flag_ref"] == phase14["enablement_request"]["feature_flag_ref"]
    assert review["operator_approval_ref"] == phase14["enablement_request"]["operator_approval_ref"]
    assert review["reviewer_attestation_ref"] == "review_attestation_ref_phase15_manual_gate"
    assert review["approval_token_required"] is True
    assert review["approval_token_supplied"] is False
    assert review["approval_token_material_allowed"] is False
    assert review["review_approved"] is False
    assert review["enablement_authorized"] is False
    assert review["default_enabled"] is False
    assert review["requested_enabled"] is False
    assert review["live_observation_active"] is False
    assert review["config_write_allowed"] is False
    assert review["gateway_restart_allowed"] is False
    assert review["adapter_calls_allowed"] is False
    assert review["platform_payloads_allowed"] is False
    assert review["temporal_lifecycle_allowed"] is False
    assert review["registry_write_allowed"] is False
    assert review["kill_switch_ref"] == "kill_switch_ref_phase14_live_gateway_observation_default_off"
    assert review["kill_switch_armed"] is True
    assert review["rollback_mode"] == "feature_flag_off_first"
    assert review["rollout_steps"] == phase14["enablement_request"]["rollout_steps"]
    assert review["allowed_summary_inputs"] == phase14["enablement_request"]["allowed_summary_inputs"]
    assert review["candidate_touchpoints"] == phase14["enablement_request"]["candidate_touchpoints"]
    assert review["allowed_surfaces"] == phase14["enablement_request"]["allowed_surfaces"]
    assert review["stable_error_codes"] == []
    assert len(review["safe_digest"]) == 16
    assert review["approvals"] == PHASE15_REQUIRED_APPROVALS
    assert review["side_effects"] == []
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


@pytest.mark.parametrize(
    ("mutate", "error_code"),
    [
        (lambda request: request.update({"ok": False, "verdict": "blocked"}), "invalid_phase14_request"),
        (lambda request: request.update({"verdict": "production_ready"}), "production_action_requested"),
        (lambda request: request.update({"live_enabled": True}), "production_action_requested"),
        (lambda request: request.pop("checks"), "invalid_phase14_request"),
        (lambda request: request["checks"].update({"side_effects_absent": False}), "invalid_phase14_request"),
        (
            lambda request: request.update(
                {"required_separate_approvals": PHASE14_REQUIRED_APPROVALS + ["gateway_restart"]}
            ),
            "invalid_phase14_request",
        ),
        (
            lambda request: request.update({"required_separate_approvals": list(reversed(PHASE14_REQUIRED_APPROVALS))}),
            "invalid_phase14_request",
        ),
        (
            lambda request: request.update({"verification_matrix": list(reversed(PHASE14_VERIFICATION_MATRIX))}),
            "invalid_phase14_request",
        ),
        (lambda request: request.update({"side_effects": ["would_send"]}), "side_effects_not_absent"),
        (lambda request: request.update({"raw_gateway_event": "raw_gateway_event_value"}), "unsafe_material"),
    ],
)
def test_phase15_rejects_non_exact_or_unsafe_phase14_requests(mutate, error_code: str) -> None:
    request = safe_phase14_request()
    mutate(request)

    assert_blocked(review_with(phase14_request=request), error_code)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda request: request.update({"enablement_mode": "live_enablement"}),
        lambda request: request.update({"runbook_outline": list(reversed(PHASE14_RUNBOOK_OUTLINE))}),
        lambda request: request["enablement_request"].update({"default_enabled": True}),
        lambda request: request["enablement_request"].update({"allowed_summary_inputs": ["raw_gateway_event"]}),
        lambda request: request["enablement_request"].update(
            {"approvals": list(reversed(PHASE14_REQUIRED_APPROVALS))}
        ),
        lambda request: request["enablement_request"].update({"stable_error_codes": ["raw_error"]}),
        lambda request: request["artifact_policy"].update({"log_policy": "raw_logs"}),
        lambda request: request["artifact_policy"].update({"forbidden_material": []}),
        lambda request: request["rollback_policy"].update({"kill_switch_armed": False}),
    ],
)
def test_phase15_rejects_non_exact_nested_phase14_request_and_policy_values(mutate) -> None:
    request = safe_phase14_request()
    mutate(request)

    assert_blocked(review_with(phase14_request=request), "invalid_phase14_request")


@pytest.mark.parametrize(
    ("mutate", "error_code"),
    [
        (lambda policy: policy.update({"review_approved": True}), "live_observation_requested"),
        (lambda policy: policy.update({"enablement_authorized": True}), "live_observation_requested"),
        (lambda policy: policy.update({"default_enabled": True}), "live_observation_requested"),
        (lambda policy: policy.update({"requested_enabled": True}), "live_observation_requested"),
        (lambda policy: policy.update({"live_observation_enabled": True}), "live_observation_requested"),
        (lambda policy: policy.update({"approval_token_supplied": True}), "unsafe_material"),
        (lambda policy: policy.update({"approval_token_material_allowed": True}), "unsafe_material"),
        (lambda policy: policy.update({"config_write_allowed": True}), "registry_or_config_write_requested"),
        (lambda policy: policy.update({"registry_write_allowed": True}), "registry_or_config_write_requested"),
        (lambda policy: policy.update({"gateway_restart_allowed": True}), "production_action_requested"),
        (lambda policy: policy.update({"adapter_calls_allowed": True}), "production_action_requested"),
        (lambda policy: policy.update({"platform_payloads_allowed": True}), "production_action_requested"),
        (lambda policy: policy.update({"temporal_lifecycle_allowed": True}), "runtime_lifecycle_requested"),
        (lambda policy: policy.update({"kill_switch_armed": False}), "invalid_review_policy"),
        (lambda policy: policy.update({"side_effects": ["would_restart_gateway"]}), "side_effects_not_absent"),
        (lambda policy: policy.update({"reviewer_attestation_ref": "raw_prompt_value"}), "unsafe_material"),
    ],
)
def test_phase15_rejects_unsafe_or_live_review_policy(mutate, error_code: str) -> None:
    policy = safe_review_policy()
    mutate(policy)

    assert_blocked(review_with(review_policy=policy), error_code)


def test_phase15_rejects_hostile_phase14_artifact_policy_list_subclasses() -> None:
    class AlwaysEqualList(list):
        def __eq__(self, other):
            del other
            return True

    request = safe_phase14_request()
    request["artifact_policy"]["allowed_fields"] = AlwaysEqualList(["raw_prompt"])
    request["artifact_policy"]["forbidden_material"] = AlwaysEqualList([])

    assert_blocked(review_with(phase14_request=request), "invalid_phase14_request")


def test_phase15_rejects_hostile_phase14_artifact_policy_string_subclasses() -> None:
    class AlwaysEqualString(str):
        def __eq__(self, other):
            del other
            return True

    request = safe_phase14_request()
    request["artifact_policy"]["log_policy"] = AlwaysEqualString("raw_prompt")

    assert_blocked(review_with(phase14_request=request), "invalid_phase14_request")


def test_phase15_rejects_hostile_side_effect_list_subclasses() -> None:
    class AlwaysEmptyList(list):
        def __eq__(self, other):
            del other
            return True

    request = safe_phase14_request()
    request["side_effects"] = AlwaysEmptyList(["would_send"])
    policy = safe_review_policy()
    policy["side_effects"] = AlwaysEmptyList(["would_restart_gateway"])

    assert_blocked(review_with(phase14_request=request), "side_effects_not_absent")
    assert_blocked(review_with(review_policy=policy), "side_effects_not_absent")


def test_phase15_maps_hostile_objects_to_safe_blocked_report_without_serializing_them() -> None:
    class HostileRequest(dict):
        pass

    hostile = HostileRequest(safe_phase14_request())
    hostile["note"] = "raw_prompt_value platform_payload_value oc_phase15_private_chat"

    result = review_with(phase14_request=hostile)

    assert_blocked(result, "invalid_phase14_request")
    assert_no_forbidden_output(result)


def test_phase15_source_stays_out_of_live_gateway_runtime_surfaces() -> None:
    source = (ROOT / "gateway" / "flowweaver_live_gateway_observation_manual_review.py").read_text()
    forbidden_static_markers = [
        "gateway.run",
        "gateway.platforms",
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
