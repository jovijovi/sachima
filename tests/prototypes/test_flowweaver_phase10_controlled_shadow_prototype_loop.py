"""RED contract tests for FlowWeaver Phase 10 controlled-shadow prototype loop."""

from __future__ import annotations

import copy
import importlib
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PHASE5B_SRC = ROOT / "prototypes" / "flowweaver_phase5b_temporal_poc" / "src"
PHASE5C_SRC = ROOT / "prototypes" / "flowweaver_phase5c_runtime_client" / "src"
for path in (PHASE5C_SRC, PHASE5B_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from flowweaver_temporal_poc.payloads import build_runtime_start_payload, start_signature_from_payload  # noqa: E402

WORKFLOW_ID = "runtime_tx_phase10_prototype_loop"
REQUIRED_APPROVALS_IN_PHASE9_ORDER = [
    "production_gateway_wiring",
    "production_config_write",
    "gateway_restart",
    "external_temporal_service",
    "real_send_edit_render_callback",
    "production_tool_registry",
    "remote_branch_or_worktree_cleanup",
]
PHASE9_FAIL_CLOSED_ERRORS = [
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
PHASE9_VERIFICATION_MATRIX = [
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
PHASE9_RUNBOOK_OUTLINE = [
    "phase9_is_controlled_shadow_design_only",
    "prototype_shadow_requires_explicit_implementation_approval",
    "production_activation_requires_separate_design_and_approval",
    "keep_default_off_until_explicit_enablement",
    "rollback_and_kill_switch_required_before_any_wiring",
    "no_raw_payloads_or_secrets_in_reports_or_artifacts",
    "use_direct_pytest_for_integration_regression",
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
SUCCESS_FIELDS = {
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
BLOCKED_FIELDS = {"type", "version", "ok", "verdict", "phase", "error_code", "side_effects"}
LOOP_RESULT_FIELDS = {
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
ARTIFACT_FIELDS = {
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
ERROR_CODES = {
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
FORBIDDEN_OUTPUT_VALUES = (
    "production_enabled",
    "production_ready",
    "live_enabled",
    "gateway_enabled",
    "oc_phase10_private_chat",
    "ou_phase10_private_user",
    "raw_prompt_payload_value",
    "platform_payload_value",
    "card_payload_value",
    "media_path_value",
    "https://example.invalid/callback?access_" + "token=phase10",
    "postgres" + "://phase10.invalid/db",
    "unsafe-" + "token" + "-phase10",
    "Bearer " + "phase10secretvalue0000000000",
)
SAFE_START_FIELDS = {
    "transaction_id": WORKFLOW_ID,
    "idempotency_key": "runtime_event_start_phase10_prototype_loop",
    "entry_count": 1,
    "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
    "allowed_runtime_events": [
        "start_transaction",
        "record_operation",
        "publish_artifact",
        "plan_delivery",
        "record_delivery_ack",
        "approve_intent",
        "reject_intent",
        "cancel_transaction",
        "resume_after_user_input",
    ],
    "claim_check_policy": {
        "mode": "references_only",
        "allowed_reference_fields": ["ref", "kind", "count", "size", "checksum_hint"],
        "forbidden_material": [
            "raw_snapshot",
            "raw_capture",
            "full_agent_result",
            "raw_prompt",
            "raw_command",
            "stdout",
            "stderr",
            "tool_output",
            "card_json",
            "media_bytes",
            "media_path",
            "platform_payload",
            "platform_id",
            "chat_id",
            "user_id",
            "message_id",
            "delivery_ack_payload",
            "credential",
            "token",
            "secret",
        ],
    },
}


def import_loop_module():
    return importlib.import_module("flowweaver_runtime_client.controlled_shadow_prototype_loop")


def import_phase9_module():
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
            "fail_closed_errors": [
                "delivery_target_mismatch",
                "invalid_gateway_boundary",
                "invalid_operational_policy",
                "invalid_phase7_result",
                "invalid_runtime_boundary",
                "not_shadow_only",
                "production_action_requested",
                "registry_or_config_write_requested",
                "runtime_lifecycle_requested",
                "side_effects_not_absent",
                "unsafe_material",
                "workflow_id_mismatch",
            ],
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
        "required_separate_approvals": list(REQUIRED_APPROVALS_IN_PHASE9_ORDER),
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


def safe_phase9_plan_report() -> dict[str, object]:
    module = import_phase9_module()
    return module.build_flowweaver_controlled_shadow_plan(
        readiness_report=safe_readiness_report(),
        shadow_scope={
            "type": "flowweaver.controlled_shadow_scope.v0",
            "mode": "prototype_shadow_candidate",
            "source_kind": "phase8_readiness_replay",
            "max_transactions": 3,
            "max_delivery_surfaces": 2,
            "allowed_surfaces": ["final_text", "rich_card"],
            "operator_approval_ref": "approval_ref_phase10_implementation_approved",
            "feature_flag_ref": "feature_flag_ref_phase10_controlled_shadow_off",
            "side_effects": [],
        },
        gateway_observation_boundary={
            "type": "flowweaver.gateway_observation_boundary.v0",
            "observation_mode": "sanitized_replay_only",
            "inbound_material": "sanitized_refs_only",
            "outbound_effects": "none",
            "adapter_imports_allowed": False,
            "platform_payloads_allowed": False,
            "message_identifiers_allowed": False,
            "ack_source": "phase6_shadow_bridge",
            "side_effects": [],
        },
        runtime_execution_boundary={
            "type": "flowweaver.runtime_execution_boundary.v0",
            "control_surface": "phase5k_control_surface",
            "client_lifecycle": "caller_supplied_only",
            "temporal_dependency": "optional_extra_only",
            "event_ingress": "validated_updates_only",
            "allowed_operations": ["start_transaction", "query_transaction", "reconcile_delivery_ack"],
            "worker_lifecycle": "none",
            "side_effects": [],
        },
        artifact_policy={
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
        },
        rollback_policy={
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
        },
    )


def safe_run_policy(*, max_publications: int = 3, max_delivery_updates_per_publication: int = 2) -> dict[str, object]:
    return {
        "type": "flowweaver.controlled_shadow_prototype_run_policy.v0",
        "mode": "prototype_loop_only",
        "source_kind": "sanitized_publication_fixture",
        "max_publications": max_publications,
        "max_delivery_updates_per_publication": max_delivery_updates_per_publication,
        "control_surface_lifecycle": "caller_supplied_only",
        "gateway_effects_allowed": False,
        "temporal_lifecycle_allowed": False,
        "payload_carrying_signals_allowed": False,
        "artifact_mode": "safe_summary_only",
        "log_policy": "sanitized_codes_only",
        "side_effects": [],
    }


def snapshot_for_start_fields(start_fields: dict[str, object], *, applied_event_count: int = 0) -> dict[str, object]:
    payload = build_runtime_start_payload(**start_fields)
    count = payload.entry_count
    delivery_count = payload.record_counts["deliveries"]
    return {
        "type": "flowweaver.temporal_poc.snapshot.v0",
        "version": "flowweaver.temporal_poc.v0",
        "transaction_id": payload.transaction_id,
        "status": "running",
        "entry_count": count,
        "record_counts": dict(payload.record_counts),
        "start_signature": start_signature_from_payload(payload),
        "counts": {"intents": count, "artifacts": count, "deliveries": delivery_count},
        "intent_statuses": {f"runtime_intent_{index}": "pending" for index in range(count)},
        "artifact_statuses": {f"runtime_artifact_{index}": "available" for index in range(count)},
        "delivery_statuses": {f"runtime_delivery_{index}": "planned" for index in range(delivery_count)},
        "applied_event_count": applied_event_count,
        "resume_count": 0,
        "side_effects": [],
    }


class RecordingControlSurface:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.snapshot: dict[str, object] | None = None
        self.applied_delivery_events: set[str] = set()

    async def handle(self, request: object) -> dict[str, object]:
        assert type(request) is dict, "loop must call control surface with plain dict requests"
        self.calls.append(copy.deepcopy(request))
        operation = request.get("operation")
        workflow_id = request.get("workflow_id")
        if operation == "start_transaction":
            start_payload = request.get("start_payload")
            assert type(start_payload) is dict
            if self.snapshot is None:
                self.snapshot = snapshot_for_start_fields(start_payload)
                status = "started"
            else:
                status = "running"
            return {
                "ok": True,
                "operation": "start_transaction",
                "runtime_operation": "start_transaction",
                "workflow_id": workflow_id,
                "transaction_id": self.snapshot["transaction_id"],
                "status": status,
            }
        if operation == "query_transaction":
            if self.snapshot is None:
                return {"ok": False, "operation": "query_transaction", "error_code": "snapshot_unavailable"}
            return {
                "ok": True,
                "operation": "query_transaction",
                "runtime_operation": "query_snapshot",
                "workflow_id": workflow_id,
                "transaction_id": self.snapshot["transaction_id"],
                "status": self.snapshot["status"],
                "snapshot": copy.deepcopy(self.snapshot),
            }
        if operation == "reconcile_delivery_ack":
            assert self.snapshot is not None
            update = request.get("update")
            assert type(update) is dict
            status = "duplicate" if update["delivery_key"] in self.applied_delivery_events else "applied"
            if status == "applied":
                self.applied_delivery_events.add(update["delivery_key"])
                self.snapshot["applied_event_count"] += 1
            delivery_statuses = dict(self.snapshot["delivery_statuses"])
            delivery_statuses[update["target_id"]] = update["status"]
            self.snapshot["delivery_statuses"] = delivery_statuses
            return {
                "ok": True,
                "operation": "reconcile_delivery_ack",
                "runtime_operation": "record_delivery_ack",
                "workflow_id": workflow_id,
                "status": status,
                "snapshot": copy.deepcopy(self.snapshot),
            }
        raise AssertionError(f"unexpected operation: {operation!r}")


class ExplodingControlSurface:
    async def handle(self, request: object) -> dict[str, object]:
        raise RuntimeError("sec" + "ret raw_prompt platform_payload oc_phase10_private_chat")


class HostilePlan(dict):
    pass


def safe_publication(*, workflow_id: str = WORKFLOW_ID, updates: list[dict[str, str]] | None = None, delivery_count: int = 1) -> dict[str, object]:
    suffix = workflow_id.removeprefix("runtime_tx_")
    start_fields = copy.deepcopy(SAFE_START_FIELDS)
    start_fields["transaction_id"] = workflow_id
    start_fields["idempotency_key"] = "runtime_event_start_" + suffix
    start_fields["record_counts"] = {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": delivery_count}
    if updates is None:
        updates = [
            {
                "event_type": "record_delivery_ack",
                "delivery_key": "runtime_event_delivery_ack_" + suffix + "_0",
                "surface": "final_text",
                "target_kind": "delivery",
                "target_id": "runtime_delivery_0",
                "status": "sent",
            }
        ]
    return {
        "type": "flowweaver.gateway.shadow_runtime_publication.v0",
        "verdict": "ready",
        "reason": "ok",
        "runtime_model_version": "flowweaver.runtime.v0",
        "runtime_envelope_type": "flowweaver.gateway.runtime_ingress_envelope.v0",
        "transaction_id": workflow_id,
        "workflow_id": workflow_id,
        "runtime_identity": {
            "type": "flowweaver.gateway.runtime_identity.v0",
            "strategy": "shadow_ref_hash_v0",
            "transaction_id": workflow_id,
            "workflow_id": workflow_id,
            "idempotency_key": "runtime_event_start_" + suffix,
        },
        "start_request": {"operation": "start_transaction", "workflow_id": workflow_id, "start_payload": start_fields},
        "ack_bridge": {"status": "ready", "updates": updates},
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


def assert_no_forbidden_output(value: object) -> None:
    rendered = repr(value)
    lowered = rendered.lower()
    for forbidden in FORBIDDEN_OUTPUT_VALUES:
        assert forbidden not in rendered
    assert "raw_prompt_payload_value" not in rendered
    assert "platform_payload_value" not in rendered
    assert "card_payload_value" not in rendered
    assert "media_path_value" not in rendered
    assert "forbidden_material" not in lowered
    assert "claim_check_policy" not in lowered
    assert "allowed_runtime_events" not in lowered
    assert "raw exception" not in lowered


def assert_blocked(result: dict[str, object], error_code: str) -> None:
    assert type(result) is dict
    assert set(result) == BLOCKED_FIELDS
    assert result == {
        "type": "flowweaver.controlled_shadow_prototype_loop_report.v0",
        "version": "flowweaver.controlled_shadow_prototype_loop.v0",
        "ok": False,
        "verdict": "blocked",
        "phase": "phase10_controlled_shadow_prototype_loop",
        "error_code": error_code,
        "side_effects": [],
    }
    assert error_code in ERROR_CODES
    assert_no_forbidden_output(result)


def test_phase10_loop_import_is_default_off_async_and_narrow() -> None:
    for module_name in (
        "flowweaver_runtime_client.controlled_shadow_prototype_loop",
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

    module = import_loop_module()

    assert module.FLOWWEAVER_CONTROLLED_SHADOW_PROTOTYPE_LOOP_VERSION == (
        "flowweaver.controlled_shadow_prototype_loop.v0"
    )
    assert module.CONTROLLED_SHADOW_PROTOTYPE_RUN_POLICY_TYPE == (
        "flowweaver.controlled_shadow_prototype_run_policy.v0"
    )
    assert module.CONTROLLED_SHADOW_PROTOTYPE_LOOP_REPORT_TYPE == (
        "flowweaver.controlled_shadow_prototype_loop_report.v0"
    )
    assert module.CONTROLLED_SHADOW_PROTOTYPE_ARTIFACT_TYPE == (
        "flowweaver.controlled_shadow_prototype_artifact.v0"
    )
    assert inspect.iscoroutinefunction(module.run_flowweaver_controlled_shadow_prototype_loop)
    signature = inspect.signature(module.run_flowweaver_controlled_shadow_prototype_loop)
    assert list(signature.parameters) == [
        "controlled_shadow_plan_report",
        "publication_fixtures",
        "control_surface",
        "run_policy",
    ]
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())
    assert sorted(module.__all__) == [
        "CONTROLLED_SHADOW_PROTOTYPE_ARTIFACT_TYPE",
        "CONTROLLED_SHADOW_PROTOTYPE_LOOP_REPORT_TYPE",
        "CONTROLLED_SHADOW_PROTOTYPE_RUN_POLICY_TYPE",
        "FLOWWEAVER_CONTROLLED_SHADOW_PROTOTYPE_LOOP_VERSION",
        "run_flowweaver_controlled_shadow_prototype_loop",
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


@pytest.mark.asyncio
async def test_phase10_loop_verifies_safe_phase9_plan_and_runs_bounded_phase7_fixture() -> None:
    module = import_loop_module()
    control = RecordingControlSurface()

    result = await module.run_flowweaver_controlled_shadow_prototype_loop(
        controlled_shadow_plan_report=safe_phase9_plan_report(),
        publication_fixtures=[safe_publication()],
        control_surface=control,
        run_policy=safe_run_policy(),
    )

    assert [call["operation"] for call in control.calls] == [
        "start_transaction",
        "query_transaction",
        "query_transaction",
        "reconcile_delivery_ack",
        "query_transaction",
    ]
    assert type(result) is dict
    assert set(result) == SUCCESS_FIELDS
    assert result["type"] == "flowweaver.controlled_shadow_prototype_loop_report.v0"
    assert result["version"] == "flowweaver.controlled_shadow_prototype_loop.v0"
    assert result["ok"] is True
    assert result["verdict"] == "controlled_shadow_prototype_loop_verified"
    assert result["phase"] == "phase10_controlled_shadow_prototype_loop"
    assert result["run_id"].startswith("controlled_shadow_run_")
    assert result["plan_transaction_id"] == WORKFLOW_ID
    assert result["publication_count"] == 1
    assert result["side_effects"] == []
    assert result["required_separate_approvals"] == REQUIRED_APPROVALS_IN_PHASE9_ORDER
    assert result["verification_matrix"] == PHASE10_VERIFICATION_MATRIX
    assert result["runbook_outline"] == PHASE10_RUNBOOK_OUTLINE
    assert result["checks"] == {key: True for key in PHASE10_VERIFICATION_MATRIX}

    assert len(result["loop_results"]) == 1
    loop_result = result["loop_results"][0]
    assert set(loop_result) == LOOP_RESULT_FIELDS
    assert loop_result["workflow_id"] == WORKFLOW_ID
    assert loop_result["transaction_id"] == WORKFLOW_ID
    assert loop_result["start_status"] == "started"
    assert loop_result["ack_count"] == 1
    assert loop_result["surfaces"] == ["final_text"]
    assert loop_result["status_counts"] == {"started": 1, "ack_applied": 1}
    assert loop_result["delivery_counts"] == {"total": 1, "sent": 1}
    assert loop_result["stable_error_codes"] == []
    assert type(loop_result["safe_digest"]) is str and len(loop_result["safe_digest"]) == 16
    assert loop_result["side_effects"] == []

    artifact = result["artifact"]
    assert set(artifact) == ARTIFACT_FIELDS
    assert artifact["type"] == "flowweaver.controlled_shadow_prototype_artifact.v0"
    assert artifact["artifact_mode"] == "safe_summary_only"
    assert artifact["run_id"] == result["run_id"]
    assert artifact["plan_transaction_id"] == WORKFLOW_ID
    assert artifact["publication_count"] == 1
    assert artifact["operation_counts"] == {"phase7_loop": 1}
    assert artifact["delivery_counts"] == {"total": 1, "sent": 1}
    assert artifact["statuses"] == {"started": 1, "ack_applied": 1}
    assert artifact["digests"] == [loop_result["safe_digest"]]
    assert artifact["stable_error_codes"] == []
    assert artifact["approvals"] == REQUIRED_APPROVALS_IN_PHASE9_ORDER
    assert artifact["side_effects"] == []
    assert_no_forbidden_output(result)


@pytest.mark.asyncio
async def test_phase10_loop_rejects_non_exact_phase9_plan_before_control_surface_call() -> None:
    module = import_loop_module()
    invalid_cases: list[tuple[dict[str, object], str]] = []

    blocked = safe_phase9_plan_report()
    blocked["ok"] = False
    blocked["verdict"] = "blocked"
    invalid_cases.append((blocked, "invalid_phase9_plan"))

    wrong_verdict = safe_phase9_plan_report()
    wrong_verdict["verdict"] = "production_ready"
    invalid_cases.append((wrong_verdict, "production_action_requested"))

    missing_top = safe_phase9_plan_report()
    del missing_top["checks"]
    invalid_cases.append((missing_top, "invalid_phase9_plan"))

    extra_top = safe_phase9_plan_report()
    extra_top["gateway_enabled"] = True
    invalid_cases.append((extra_top, "production_action_requested"))

    mismatch = safe_phase9_plan_report()
    mismatch["transaction_id"] = "runtime_tx_phase10_other"
    invalid_cases.append((mismatch, "workflow_id_mismatch"))

    duplicate_approval = safe_phase9_plan_report()
    duplicate_approval["required_separate_approvals"] = list(REQUIRED_APPROVALS_IN_PHASE9_ORDER) + [
        "gateway_restart"
    ]
    invalid_cases.append((duplicate_approval, "invalid_phase9_plan"))

    missing_matrix = safe_phase9_plan_report()
    missing_matrix["verification_matrix"] = list(PHASE9_VERIFICATION_MATRIX[:-1])
    invalid_cases.append((missing_matrix, "invalid_phase9_plan"))

    reordered_matrix = safe_phase9_plan_report()
    reordered_matrix["verification_matrix"] = list(reversed(PHASE9_VERIFICATION_MATRIX))
    invalid_cases.append((reordered_matrix, "invalid_phase9_plan"))

    bogus_matrix = safe_phase9_plan_report()
    bogus_matrix["verification_matrix"] = list(PHASE9_VERIFICATION_MATRIX) + ["live_enabled"]
    invalid_cases.append((bogus_matrix, "production_action_requested"))

    missing_runbook = safe_phase9_plan_report()
    missing_runbook["runbook_outline"] = list(PHASE9_RUNBOOK_OUTLINE[:-1])
    invalid_cases.append((missing_runbook, "invalid_phase9_plan"))

    reordered_runbook = safe_phase9_plan_report()
    reordered_runbook["runbook_outline"] = list(reversed(PHASE9_RUNBOOK_OUTLINE))
    invalid_cases.append((reordered_runbook, "invalid_phase9_plan"))

    incomplete_fail_closed = safe_phase9_plan_report()
    incomplete_fail_closed["controlled_shadow_plan"]["fail_closed_errors"] = list(PHASE9_FAIL_CLOSED_ERRORS[:-1])
    invalid_cases.append((incomplete_fail_closed, "invalid_phase9_plan"))

    reordered_fail_closed = safe_phase9_plan_report()
    reordered_fail_closed["controlled_shadow_plan"]["fail_closed_errors"] = list(reversed(PHASE9_FAIL_CLOSED_ERRORS))
    invalid_cases.append((reordered_fail_closed, "invalid_phase9_plan"))

    duplicate_fail_closed = safe_phase9_plan_report()
    duplicate_fail_closed["controlled_shadow_plan"]["fail_closed_errors"] = list(PHASE9_FAIL_CLOSED_ERRORS) + [
        "unsafe_material"
    ]
    invalid_cases.append((duplicate_fail_closed, "invalid_phase9_plan"))

    bogus_fail_closed = safe_phase9_plan_report()
    bogus_fail_closed["controlled_shadow_plan"]["fail_closed_errors"] = ["not_a_phase9_code"]
    invalid_cases.append((bogus_fail_closed, "invalid_phase9_plan"))

    artifact_raw_field = safe_phase9_plan_report()
    artifact_raw_field["artifact_policy"]["allowed_fields"] = ["run_id", "raw_prompt"]
    invalid_cases.append((artifact_raw_field, "artifact_policy_violation"))

    missing_phase7_operation = safe_phase9_plan_report()
    missing_phase7_operation["controlled_shadow_plan"]["runtime_operations"] = ["start_transaction"]
    invalid_cases.append((missing_phase7_operation, "invalid_phase9_plan"))

    side_effects = safe_phase9_plan_report()
    side_effects["side_effects"] = ["would_send"]
    invalid_cases.append((side_effects, "side_effects_not_absent"))

    hostile_plan = HostilePlan(safe_phase9_plan_report())
    control = RecordingControlSurface()
    assert_blocked(
        await module.run_flowweaver_controlled_shadow_prototype_loop(
            controlled_shadow_plan_report=hostile_plan,
            publication_fixtures=[safe_publication()],
            control_surface=control,
            run_policy=safe_run_policy(),
        ),
        "invalid_phase9_plan",
    )

    for plan_report, error_code in invalid_cases:
        control = RecordingControlSurface()
        result = await module.run_flowweaver_controlled_shadow_prototype_loop(
            controlled_shadow_plan_report=plan_report,
            publication_fixtures=[safe_publication()],
            control_surface=control,
            run_policy=safe_run_policy(),
        )
        assert_blocked(result, error_code)
        assert control.calls == []


@pytest.mark.asyncio
async def test_phase10_loop_rejects_default_on_lifecycle_and_production_run_policy() -> None:
    module = import_loop_module()
    invalid_cases: list[tuple[dict[str, object], str]] = []

    wrong_mode = safe_run_policy()
    wrong_mode["mode"] = "production_gateway"
    invalid_cases.append((wrong_mode, "production_action_requested"))

    too_many_publications = safe_run_policy(max_publications=4)
    invalid_cases.append((too_many_publications, "invalid_run_policy"))

    too_many_delivery_updates = safe_run_policy(max_delivery_updates_per_publication=3)
    invalid_cases.append((too_many_delivery_updates, "invalid_run_policy"))

    gateway_effects = safe_run_policy()
    gateway_effects["gateway_effects_allowed"] = True
    invalid_cases.append((gateway_effects, "production_action_requested"))

    temporal_lifecycle = safe_run_policy()
    temporal_lifecycle["temporal_lifecycle_allowed"] = True
    invalid_cases.append((temporal_lifecycle, "runtime_lifecycle_requested"))

    payload_signals = safe_run_policy()
    payload_signals["payload_carrying_signals_allowed"] = True
    invalid_cases.append((payload_signals, "runtime_lifecycle_requested"))

    registry_write = safe_run_policy()
    registry_write["registry_write"] = True
    invalid_cases.append((registry_write, "registry_or_config_write_requested"))

    task_queue = safe_run_policy()
    task_queue["task_queue"] = "phase10"
    invalid_cases.append((task_queue, "runtime_lifecycle_requested"))

    side_effects = safe_run_policy()
    side_effects["side_effects"] = ["would_render"]
    invalid_cases.append((side_effects, "side_effects_not_absent"))

    for run_policy, error_code in invalid_cases:
        control = RecordingControlSurface()
        result = await module.run_flowweaver_controlled_shadow_prototype_loop(
            controlled_shadow_plan_report=safe_phase9_plan_report(),
            publication_fixtures=[safe_publication()],
            control_surface=control,
            run_policy=run_policy,
        )
        assert_blocked(result, error_code)
        assert control.calls == []


@pytest.mark.asyncio
async def test_phase10_loop_bounds_and_sanitizes_publication_fixtures_before_phase7_runtime_calls() -> None:
    module = import_loop_module()

    first = safe_publication(workflow_id="runtime_tx_phase10_fixture_one")
    second = safe_publication(workflow_id="runtime_tx_phase10_fixture_two")
    control = RecordingControlSurface()
    assert_blocked(
        await module.run_flowweaver_controlled_shadow_prototype_loop(
            controlled_shadow_plan_report=safe_phase9_plan_report(),
            publication_fixtures=[first, second],
            control_surface=control,
            run_policy=safe_run_policy(max_publications=1),
        ),
        "publication_limit_exceeded",
    )
    assert control.calls == []

    unsafe_publication = safe_publication()
    unsafe_publication["platform_payload"] = {
        "chat_id": "oc_" + "phase10_private_chat",
        "user_id": "ou_" + "phase10_private_user",
    }
    unsafe_publication["card_json"] = {"body": "raw card should never enter"}
    unsafe_publication["media_path"] = "/tmp/raw-phase10-media.png"
    unsafe_publication["note"] = "unsafe-" + "token" + "-phase10"
    control = RecordingControlSurface()
    assert_blocked(
        await module.run_flowweaver_controlled_shadow_prototype_loop(
            controlled_shadow_plan_report=safe_phase9_plan_report(),
            publication_fixtures=[unsafe_publication],
            control_surface=control,
            run_policy=safe_run_policy(),
        ),
        "invalid_publication_fixture",
    )
    assert control.calls == []

    skipped_status = safe_publication()
    skipped_status["ack_bridge"]["updates"][0]["status"] = "skipped"
    control = RecordingControlSurface()
    assert_blocked(
        await module.run_flowweaver_controlled_shadow_prototype_loop(
            controlled_shadow_plan_report=safe_phase9_plan_report(),
            publication_fixtures=[skipped_status],
            control_surface=control,
            run_policy=safe_run_policy(),
        ),
        "invalid_publication_fixture",
    )
    assert control.calls == []

    surface_outside_phase9_plan = safe_publication()
    surface_outside_phase9_plan["ack_bridge"]["updates"][0]["surface"] = "progress_card"
    control = RecordingControlSurface()
    assert_blocked(
        await module.run_flowweaver_controlled_shadow_prototype_loop(
            controlled_shadow_plan_report=safe_phase9_plan_report(),
            publication_fixtures=[surface_outside_phase9_plan],
            control_surface=control,
            run_policy=safe_run_policy(),
        ),
        "invalid_publication_fixture",
    )
    assert control.calls == []

    missing_initialized_delivery_slot = safe_publication()
    missing_initialized_delivery_slot["ack_bridge"]["updates"][0]["target_id"] = "runtime_delivery_9"
    control = RecordingControlSurface()
    assert_blocked(
        await module.run_flowweaver_controlled_shadow_prototype_loop(
            controlled_shadow_plan_report=safe_phase9_plan_report(),
            publication_fixtures=[missing_initialized_delivery_slot],
            control_surface=control,
            run_policy=safe_run_policy(),
        ),
        "invalid_publication_fixture",
    )
    assert control.calls == []

    two_updates = safe_publication(
        workflow_id="runtime_tx_phase10_delivery_bound",
        delivery_count=2,
        updates=[
            {
                "event_type": "record_delivery_ack",
                "delivery_key": "runtime_event_delivery_ack_phase10_delivery_bound_0",
                "surface": "final_text",
                "target_kind": "delivery",
                "target_id": "runtime_delivery_0",
                "status": "sent",
            },
            {
                "event_type": "record_delivery_ack",
                "delivery_key": "runtime_event_delivery_ack_phase10_delivery_bound_1",
                "surface": "rich_card",
                "target_kind": "delivery",
                "target_id": "runtime_delivery_1",
                "status": "acknowledged",
            },
        ],
    )
    control = RecordingControlSurface()
    assert_blocked(
        await module.run_flowweaver_controlled_shadow_prototype_loop(
            controlled_shadow_plan_report=safe_phase9_plan_report(),
            publication_fixtures=[two_updates],
            control_surface=control,
            run_policy=safe_run_policy(max_delivery_updates_per_publication=1),
        ),
        "delivery_update_limit_exceeded",
    )
    assert control.calls == []


@pytest.mark.asyncio
async def test_phase10_loop_rejects_uninitialized_delivery_target_before_phase7_runtime_call() -> None:
    module = import_loop_module()
    for target_id in ("runtime_delivery_9", "runtime_delivery_00"):
        missing_initialized_delivery_slot = safe_publication()
        missing_initialized_delivery_slot["ack_bridge"]["updates"][0]["target_id"] = target_id
        control = RecordingControlSurface()

        assert_blocked(
            await module.run_flowweaver_controlled_shadow_prototype_loop(
                controlled_shadow_plan_report=safe_phase9_plan_report(),
                publication_fixtures=[missing_initialized_delivery_slot],
                control_surface=control,
                run_policy=safe_run_policy(),
            ),
            "invalid_publication_fixture",
        )
        assert control.calls == []


@pytest.mark.asyncio
async def test_phase10_loop_maps_phase7_runtime_failures_to_safe_stable_error_without_exception_text() -> None:
    module = import_loop_module()

    result = await module.run_flowweaver_controlled_shadow_prototype_loop(
        controlled_shadow_plan_report=safe_phase9_plan_report(),
        publication_fixtures=[safe_publication()],
        control_surface=ExplodingControlSurface(),
        run_policy=safe_run_policy(),
    )

    assert_blocked(result, "phase7_loop_failed")
    assert_no_forbidden_output(result)


@pytest.mark.asyncio
async def test_phase10_loop_rejects_missing_control_surface_handle_without_serializing_object() -> None:
    module = import_loop_module()

    result = await module.run_flowweaver_controlled_shadow_prototype_loop(
        controlled_shadow_plan_report=safe_phase9_plan_report(),
        publication_fixtures=[safe_publication()],
        control_surface={"connect": "temporal_address"},
        run_policy=safe_run_policy(),
    )

    assert_blocked(result, "control_surface_contract_violation")
