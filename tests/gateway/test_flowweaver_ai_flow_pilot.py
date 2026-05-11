"""Tests for FlowWeaver Phase 33 narrow AI FLOW pilot contract."""

from __future__ import annotations

import ast
import copy
import subprocess
from pathlib import Path

import pytest

from gateway.flowweaver_agent_execution_activity import FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT
from gateway.flowweaver_delivery_activity import FLOWWEAVER_DELIVERY_ACTIVITY_SUCCESS_VERDICT
from gateway.flowweaver_ai_flow_pilot import (
    FLOWWEAVER_AI_FLOW_PILOT_CONTRACT_TYPE,
    FLOWWEAVER_AI_FLOW_PILOT_DECISION_PACKET_TYPE,
    FLOWWEAVER_AI_FLOW_PILOT_REPORT_TYPE,
    FLOWWEAVER_AI_FLOW_PILOT_SUCCESS_VERDICT,
    FLOWWEAVER_AI_FLOW_PILOT_VERSION,
    build_flowweaver_ai_flow_pilot_report,
    build_flowweaver_ai_flow_pilot_request,
    describe_flowweaver_ai_flow_pilot_contract,
    validate_flowweaver_ai_flow_pilot_decision_packet,
    validate_flowweaver_ai_flow_pilot_report,
    validate_flowweaver_ai_flow_pilot_request,
    validate_flowweaver_ai_flow_pilot_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]
MODULE_SOURCE = ROOT / "gateway" / "flowweaver_ai_flow_pilot.py"

PRIVATE_CHAT_ID = "oc_" + "phase33_private_chat"
PRIVATE_USER_ID = "ou_" + "phase33_private_user"
PRIVATE_MESSAGE_ID = "om_" + "phase33_private_message"
RAW_PROMPT_VALUE = "raw prompt phase33 private value"
RAW_TOOL_VALUE = "raw " + "tool output phase33 private value"
CARD_JSON_VALUE = '{"type":"card_json","body":"phase33"}'
MEDIA_PATH_VALUE = "/tmp/phase33-private.png"
CALLBACK_VALUE = "callback payload phase33 private value"
RAW_EXCEPTION_VALUE = "RuntimeError: raw phase33 exception value"
SENSITIVE_SENTINEL = "unsafe-" + "token" + "-phase33"
BEARER_VALUE = "Bearer " + "phase33-private"
OPENAI_KEY_VALUE = "sk-" + "phase33-private"
FORBIDDEN_SENTINELS = (
    PRIVATE_CHAT_ID,
    PRIVATE_USER_ID,
    PRIVATE_MESSAGE_ID,
    RAW_PROMPT_VALUE,
    RAW_TOOL_VALUE,
    CARD_JSON_VALUE,
    MEDIA_PATH_VALUE,
    CALLBACK_VALUE,
    RAW_EXCEPTION_VALUE,
    SENSITIVE_SENTINEL,
    BEARER_VALUE,
    OPENAI_KEY_VALUE,
)
PHASE33_NOT_READY_VERDICT = "not_ready_for_production_enablement"
EXPECTED_CONTRACT_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "scope",
    "consumes_verdicts",
    "entrypoints",
    "request_fields",
    "snapshot_fields",
    "decision_packet_fields",
    "report_fields",
    "composition_boundary",
    "runtime_policy",
    "pilot_policy",
    "decision_policy",
    "checks",
    "separate_approvals",
    "forbidden_side_effects",
    "side_effects",
]
EXPECTED_REQUEST_FIELDS = [
    "type",
    "version",
    "phase",
    "transaction_id",
    "workflow_id",
    "intent_id",
    "agent_execution_request",
    "initialized_delivery_slots",
    "pilot_policy",
    "decision_policy",
    "pilot_digest",
    "side_effects",
]
EXPECTED_SNAPSHOT_FIELDS = [
    "type",
    "version",
    "phase",
    "transaction_id",
    "workflow_id",
    "status",
    "intent_statuses",
    "artifact_refs",
    "delivery_refs",
    "surface_state",
    "activity_sequence",
    "counts",
    "execution_digest",
    "delivery_digest",
    "decision_packet",
    "error_code",
    "side_effects",
]
EXPECTED_DECISION_PACKET_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "pilot_status",
    "evidence",
    "rollback",
    "separate_approvals_required",
    "unresolved_risks",
    "side_effects",
]
EXPECTED_REPORT_FIELDS = [
    "type",
    "version",
    "phase",
    "ok",
    "verdict",
    "operation",
    "phase31_verdict",
    "phase32_verdict",
    "pilot_verified",
    "decision_packet_verified",
    "history_no_leak_checked",
    "checks",
    "error_code",
    "side_effects",
]
EXPECTED_CHECKS = [
    "phase31_boundary_composed",
    "phase32_boundary_composed",
    "default_off_zero_calls",
    "artifact_delivery_separated",
    "ack_replay_idempotent",
    "rollback_checklist_present",
    "decision_packet_separate_approvals",
    "history_no_leak_verified",
    "gateway_wiring_absent",
    "side_effects_absent",
]
EXPECTED_SEPARATE_APPROVALS = [
    "production_gateway_wiring",
    "production_delivery_enablement",
    "production_agent_execution",
    "production_config_write",
    "gateway_restart",
    "platform_adapter_mutation",
    "gateway_owned_worker_lifecycle",
]


def claim_ref(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "ref": "claim_ref_phase33_0",
        "kind": "agent_input",
        "count": 1,
        "size": 128,
        "checksum_hint": "sha256:" + ("a" * 64),
    }
    value.update(overrides)
    return value


def delivery_slots(*, surfaces: list[str] | None = None) -> list[dict[str, object]]:
    selected = surfaces or ["rich_card", "final_text"]
    return [
        {
            "delivery_ref": f"runtime_delivery_{index}",
            "surface": surface,
            "artifact_ref": "runtime_artifact_0",
            "required": True,
        }
        for index, surface in enumerate(selected)
    ]


def pilot_request(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "transaction_id": "runtime_tx_phase33_1",
        "workflow_id": "runtime_tx_phase33_1",
        "intent_id": "runtime_intent_0",
        "claim_check_ref": claim_ref(),
        "artifact_ref": "runtime_artifact_0",
        "initialized_delivery_slots": delivery_slots(),
        "enabled": True,
    }
    kwargs.update(overrides)
    return build_flowweaver_ai_flow_pilot_request(**kwargs)  # type: ignore[arg-type]


def canonical_decision_packet() -> dict[str, object]:
    return {
        "type": FLOWWEAVER_AI_FLOW_PILOT_DECISION_PACKET_TYPE,
        "version": FLOWWEAVER_AI_FLOW_PILOT_VERSION,
        "phase": "phase33",
        "verdict": FLOWWEAVER_AI_FLOW_PILOT_SUCCESS_VERDICT,
        "pilot_status": "pilot_completed",
        "evidence": {
            "phase31_executed": True,
            "phase32_delivered": True,
            "history_no_leak_checked": True,
            "result_no_leak_checked": True,
            "progress_snapshots_sanitized": True,
            "side_effects_absent": True,
        },
        "rollback": {
            "kill_switch_ref": "rollback_phase33_disable_pilot",
            "steps": ["disable_pilot_policy", "preserve_canonical_branch", "rerun_clean_verification"],
            "operator_required": True,
            "side_effects": [],
        },
        "separate_approvals_required": EXPECTED_SEPARATE_APPROVALS,
        "unresolved_risks": ["production_enablement_not_approved", "live_gateway_wiring_not_approved"],
        "side_effects": [],
    }


def non_ready_decision_packet(
    *,
    pilot_status: str,
    phase31_executed: bool = False,
    phase32_delivered: bool = False,
) -> dict[str, object]:
    packet = canonical_decision_packet()
    packet["verdict"] = PHASE33_NOT_READY_VERDICT
    packet["pilot_status"] = pilot_status
    packet["evidence"] = {
        **packet["evidence"],
        "phase31_executed": phase31_executed,
        "phase32_delivered": phase32_delivered,
    }
    return packet


def canonical_snapshot() -> dict[str, object]:
    return {
        "type": "flowweaver.gateway.ai_flow_pilot_snapshot.v0",
        "version": FLOWWEAVER_AI_FLOW_PILOT_VERSION,
        "phase": "phase33",
        "transaction_id": "runtime_tx_phase33_1",
        "workflow_id": "runtime_tx_phase33_1",
        "status": "pilot_completed",
        "intent_statuses": {"runtime_intent_0": "delivered"},
        "artifact_refs": ["runtime_artifact_0"],
        "delivery_refs": ["runtime_delivery_0", "runtime_delivery_1"],
        "surface_state": {
            "progress_card_sent": False,
            "rich_cards_sent": 1,
            "final_text_sent": True,
            "media_sent": 0,
        },
        "activity_sequence": [
            {"name": "validate_claim_check_ref", "status": "validated", "error_code": None, "side_effects": []},
            {"name": "execute_agent_turn", "status": "executed", "error_code": None, "side_effects": []},
            {"name": "deliver_artifact", "status": "delivered", "error_code": None, "side_effects": []},
        ],
        "counts": {
            "activities": 3,
            "artifacts": 1,
            "deliveries": 2,
            "executor_calls": 1,
            "tool_calls": 2,
            "ack_updates": 2,
            "ack_applied": 2,
            "ack_duplicates": 0,
            "ack_rejected": 0,
        },
        "execution_digest": "sha256:" + ("1" * 64),
        "delivery_digest": "sha256:" + ("2" * 64),
        "decision_packet": canonical_decision_packet(),
        "error_code": None,
        "side_effects": [],
    }


def assert_no_raw_values(value: object) -> None:
    rendered = repr(value).lower()
    for marker in FORBIDDEN_SENTINELS:
        assert marker.lower() not in rendered
    assert "traceback" not in rendered
    assert "runtimeerror" not in rendered
    assert "temporalio.exceptions" not in rendered


def test_phase33_exposes_contract_for_controlled_ai_flow_pilot_only() -> None:
    contract = describe_flowweaver_ai_flow_pilot_contract()

    assert list(contract) == EXPECTED_CONTRACT_FIELDS
    assert contract["type"] == FLOWWEAVER_AI_FLOW_PILOT_CONTRACT_TYPE
    assert contract["version"] == FLOWWEAVER_AI_FLOW_PILOT_VERSION
    assert contract["phase"] == "phase33"
    assert contract["verdict"] == "ready_for_separate_production_enablement_decision"
    assert contract["scope"] == "narrow_ai_flow_pilot"
    assert contract["consumes_verdicts"] == {
        "phase31": FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT,
        "phase32": FLOWWEAVER_DELIVERY_ACTIVITY_SUCCESS_VERDICT,
    }
    assert contract["request_fields"] == EXPECTED_REQUEST_FIELDS
    assert contract["snapshot_fields"] == EXPECTED_SNAPSHOT_FIELDS
    assert contract["decision_packet_fields"] == EXPECTED_DECISION_PACKET_FIELDS
    assert contract["report_fields"] == EXPECTED_REPORT_FIELDS
    assert contract["checks"] == EXPECTED_CHECKS
    assert contract["separate_approvals"] == EXPECTED_SEPARATE_APPROVALS
    assert contract["side_effects"] == []
    assert contract["runtime_policy"]["production_gateway_wiring"] == "forbidden"
    assert contract["runtime_policy"]["production_enablement"] == "separate_approval_required"
    assert_no_raw_values(contract)


def test_phase33_request_builder_embeds_exact_phase31_request_and_delivery_slots() -> None:
    request = pilot_request()

    assert list(request) == EXPECTED_REQUEST_FIELDS
    assert request["type"] == "flowweaver.gateway.ai_flow_pilot_request.v0"
    assert request["version"] == FLOWWEAVER_AI_FLOW_PILOT_VERSION
    assert request["phase"] == "phase33"
    assert request["transaction_id"] == "runtime_tx_phase33_1"
    assert request["workflow_id"] == "runtime_tx_phase33_1"
    assert request["intent_id"] == "runtime_intent_0"
    assert request["agent_execution_request"]["phase"] == "phase31"
    assert request["agent_execution_request"]["claim_check_ref"] == claim_ref()
    assert request["agent_execution_request"]["artifact_ref"] == "runtime_artifact_0"
    assert request["initialized_delivery_slots"] == delivery_slots()
    assert request["pilot_policy"] == {
        "enabled": True,
        "mode": "controlled_local_staging_ai_flow_pilot",
        "scenario": "repo_workflow_planning_implementation_pr",
        "agent_execution": "phase31_injected_executor_only",
        "delivery": "phase32_injected_delivery_only",
        "history_no_leak_required": True,
        "side_effects": [],
    }
    assert request["decision_policy"] == {
        "max_verdict": FLOWWEAVER_AI_FLOW_PILOT_SUCCESS_VERDICT,
        "requires_separate_approvals": EXPECTED_SEPARATE_APPROVALS,
        "rollback_required": True,
        "kill_switch_required": True,
        "side_effects": [],
    }
    assert str(request["pilot_digest"]).startswith("sha256:")
    assert request["side_effects"] == []
    assert validate_flowweaver_ai_flow_pilot_request(copy.deepcopy(request)) == request
    assert_no_raw_values(request)


def test_phase33_public_validators_reject_reordered_fields_and_raw_material() -> None:
    request = pilot_request()
    reordered = {"side_effects": [], **{key: value for key, value in request.items() if key != "side_effects"}}
    with pytest.raises(ValueError, match="invalid_ai_flow_pilot_request"):
        validate_flowweaver_ai_flow_pilot_request(reordered)

    with pytest.raises(ValueError, match="invalid_ai_flow_pilot_request"):
        pilot_request(claim_check_ref=claim_ref(ref="claim_ref_" + PRIVATE_CHAT_ID))
    with pytest.raises(ValueError, match="invalid_ai_flow_pilot_request"):
        validate_flowweaver_ai_flow_pilot_request({**request, "pilot_digest": "sha256:" + ("0" * 63) + "z"})

    snapshot = canonical_snapshot()
    assert validate_flowweaver_ai_flow_pilot_snapshot(copy.deepcopy(snapshot)) == snapshot
    reordered_snapshot = {"side_effects": [], **{key: value for key, value in snapshot.items() if key != "side_effects"}}
    with pytest.raises(ValueError, match="invalid_ai_flow_pilot_snapshot"):
        validate_flowweaver_ai_flow_pilot_snapshot(reordered_snapshot)

    decision_packet = canonical_decision_packet()
    assert validate_flowweaver_ai_flow_pilot_decision_packet(copy.deepcopy(decision_packet)) == decision_packet
    bad_packet = copy.deepcopy(decision_packet)
    bad_packet["verdict"] = "production_enabled"
    with pytest.raises(ValueError, match="invalid_ai_flow_pilot_decision_packet"):
        validate_flowweaver_ai_flow_pilot_decision_packet(bad_packet)


def test_phase33_non_completed_decision_packets_are_not_ready_and_snapshots_reject_forged_outputs() -> None:
    timed_out_packet = non_ready_decision_packet(pilot_status="timed_out", phase31_executed=True)
    assert validate_flowweaver_ai_flow_pilot_decision_packet(copy.deepcopy(timed_out_packet)) == timed_out_packet

    overstated_packet = copy.deepcopy(timed_out_packet)
    overstated_packet["verdict"] = FLOWWEAVER_AI_FLOW_PILOT_SUCCESS_VERDICT
    with pytest.raises(ValueError, match="invalid_ai_flow_pilot_decision_packet"):
        validate_flowweaver_ai_flow_pilot_decision_packet(overstated_packet)

    forged_failed = canonical_snapshot()
    forged_failed["status"] = "agent_execution_failed"
    forged_failed["intent_statuses"] = {"runtime_intent_0": "rejected"}
    forged_failed["activity_sequence"] = [
        {"name": "validate_claim_check_ref", "status": "validated", "error_code": None, "side_effects": []},
        {"name": "execute_agent_turn", "status": "rejected", "error_code": "executor_failed", "side_effects": []},
    ]
    forged_failed["counts"] = {
        **forged_failed["counts"],
        "activities": 2,
        "artifacts": 1,
        "deliveries": 1,
        "executor_calls": 1,
        "tool_calls": 0,
        "ack_updates": 0,
        "ack_applied": 0,
    }
    forged_failed["artifact_refs"] = ["runtime_artifact_0"]
    forged_failed["delivery_refs"] = ["runtime_delivery_0"]
    forged_failed["surface_state"] = {
        "progress_card_sent": False,
        "rich_cards_sent": 0,
        "final_text_sent": False,
        "media_sent": 0,
    }
    forged_failed["decision_packet"] = non_ready_decision_packet(pilot_status="agent_execution_failed")
    forged_failed["error_code"] = "executor_failed"
    with pytest.raises(ValueError, match="invalid_ai_flow_pilot_snapshot"):
        validate_flowweaver_ai_flow_pilot_snapshot(forged_failed)


def test_phase33_rejects_forged_success_snapshot_and_decision_evidence() -> None:
    forged = canonical_snapshot()
    forged["activity_sequence"] = []
    forged["decision_packet"] = {
        **forged["decision_packet"],
        "evidence": {
            **forged["decision_packet"]["evidence"],
            "phase31_executed": False,
            "phase32_delivered": False,
            "history_no_leak_checked": False,
            "result_no_leak_checked": False,
            "progress_snapshots_sanitized": False,
        },
    }

    with pytest.raises(ValueError, match="invalid_ai_flow_pilot_snapshot"):
        validate_flowweaver_ai_flow_pilot_snapshot(copy.deepcopy(forged))
    with pytest.raises(ValueError, match="invalid_ai_flow_pilot_decision_packet"):
        validate_flowweaver_ai_flow_pilot_decision_packet(copy.deepcopy(forged["decision_packet"]))

    report = build_flowweaver_ai_flow_pilot_report(
        agent_execution_activity_verdict=FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT,
        delivery_activity_verdict=FLOWWEAVER_DELIVERY_ACTIVITY_SUCCESS_VERDICT,
        pilot_snapshot=forged,
        decision_packet=forged["decision_packet"],
        history_no_leak_checked=True,
    )
    assert report["ok"] is False
    assert report["error_code"] in {"invalid_ai_flow_pilot_snapshot", "invalid_ai_flow_pilot_decision_packet"}

    counts_forged = canonical_snapshot()
    counts_forged["counts"] = {**counts_forged["counts"], "deliveries": 16}
    with pytest.raises(ValueError, match="invalid_ai_flow_pilot_snapshot"):
        validate_flowweaver_ai_flow_pilot_snapshot(counts_forged)

    activity_error_forged = canonical_snapshot()
    activity_error_forged["activity_sequence"] = [
        dict(activity_error_forged["activity_sequence"][0]),
        {**activity_error_forged["activity_sequence"][1], "error_code": "unknown_non_null_error_code"},
        {**activity_error_forged["activity_sequence"][2], "error_code": "unknown_runtime_non_null_error_code"},
    ]
    with pytest.raises(ValueError, match="invalid_ai_flow_pilot_snapshot"):
        validate_flowweaver_ai_flow_pilot_snapshot(activity_error_forged)

    duplicate_delivery_refs = canonical_snapshot()
    duplicate_delivery_refs["delivery_refs"] = ["runtime_delivery_0", "runtime_delivery_0"]
    with pytest.raises(ValueError, match="invalid_ai_flow_pilot_snapshot"):
        validate_flowweaver_ai_flow_pilot_snapshot(duplicate_delivery_refs)

    ack_totals_forged = canonical_snapshot()
    ack_totals_forged["counts"] = {
        **ack_totals_forged["counts"],
        "ack_updates": 0,
        "ack_applied": 0,
        "ack_duplicates": 0,
        "ack_rejected": 0,
    }
    with pytest.raises(ValueError, match="invalid_ai_flow_pilot_snapshot"):
        validate_flowweaver_ai_flow_pilot_snapshot(ack_totals_forged)

    surface_forged = canonical_snapshot()
    surface_forged["surface_state"] = {**surface_forged["surface_state"], "final_text_sent": False}
    with pytest.raises(ValueError, match="invalid_ai_flow_pilot_snapshot"):
        validate_flowweaver_ai_flow_pilot_snapshot(surface_forged)


def test_phase33_report_builder_requires_successful_p31_p32_evidence_and_decision_packet() -> None:
    snapshot = canonical_snapshot()
    decision_packet = validate_flowweaver_ai_flow_pilot_decision_packet(snapshot["decision_packet"])

    report = build_flowweaver_ai_flow_pilot_report(
        agent_execution_activity_verdict=FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT,
        delivery_activity_verdict=FLOWWEAVER_DELIVERY_ACTIVITY_SUCCESS_VERDICT,
        pilot_snapshot=snapshot,
        decision_packet=decision_packet,
        history_no_leak_checked=True,
    )

    assert list(report) == EXPECTED_REPORT_FIELDS
    assert report["type"] == FLOWWEAVER_AI_FLOW_PILOT_REPORT_TYPE
    assert report["version"] == FLOWWEAVER_AI_FLOW_PILOT_VERSION
    assert report["phase"] == "phase33"
    assert report["ok"] is True
    assert report["verdict"] == FLOWWEAVER_AI_FLOW_PILOT_SUCCESS_VERDICT
    assert report["pilot_verified"] is True
    assert report["decision_packet_verified"] is True
    assert report["history_no_leak_checked"] is True
    assert report["checks"] == {key: True for key in EXPECTED_CHECKS}
    assert report["error_code"] is None
    assert report["side_effects"] == []
    assert validate_flowweaver_ai_flow_pilot_report(copy.deepcopy(report)) == report
    assert_no_raw_values(report)

    failed_snapshot = copy.deepcopy(snapshot)
    failed_snapshot["status"] = "timed_out"
    failed_snapshot["intent_statuses"] = {"runtime_intent_0": "timed_out"}
    failed_snapshot["decision_packet"] = {
        **decision_packet,
        "pilot_status": "timed_out",
        "evidence": {**decision_packet["evidence"], "phase32_delivered": False},
    }
    failed_report = build_flowweaver_ai_flow_pilot_report(
        agent_execution_activity_verdict=FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT,
        delivery_activity_verdict=FLOWWEAVER_DELIVERY_ACTIVITY_SUCCESS_VERDICT,
        pilot_snapshot=failed_snapshot,
        decision_packet=failed_snapshot["decision_packet"],
        history_no_leak_checked=True,
    )
    assert failed_report["ok"] is False
    assert failed_report["error_code"] == "invalid_ai_flow_pilot_snapshot"


def test_phase33_source_forbids_production_gateway_wiring_lifecycle_and_raw_logs() -> None:
    source = MODULE_SOURCE.read_text()
    tree = ast.parse(source)

    forbidden_source_markers = (
        "gateway.run",
        "gateway.platforms",
        "run_agent",
        "AIAgent",
        "model_tools",
        "toolsets",
        "Client.connect",
        "WorkflowEnvironment",
        "from temporalio.worker import Worker",
        "Worker(",
        "save_config",
        "yaml.safe_dump",
        "print(",
        "logger.",
        "logging.",
    )
    for marker in forbidden_source_markers:
        assert marker not in source

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)
    assert not any(name == "subprocess" or name.startswith("subprocess.") for name in imported_modules)
    assert not any(name == "socket" or name.startswith("socket.") for name in imported_modules)
    assert not any("docker" in name.lower() for name in imported_modules)

    forbidden_call_names = {
        "send",
        "edit",
        "render",
        "callback",
        "acknowledge",
        "send_message",
        "send_interactive_card",
        "patch_interactive_card",
        "open",
        "write",
        "write_text",
        "Popen",
        "run_agent",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            assert name not in forbidden_call_names


def _changed_files() -> set[str]:
    commands = [
        ["git", "diff", "--name-only", "origin/feature/sachima-channel...HEAD"],
        ["git", "diff", "--name-only"],
        ["git", "diff", "--cached", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    changed: set[str] = set()
    for command in commands:
        output = subprocess.check_output(command, cwd=ROOT, text=True)
        changed.update(line for line in output.splitlines() if line)
    return changed


def test_phase33_changed_file_guard_allows_only_ai_flow_pilot_files_and_guard_maintenance() -> None:
    changed = _changed_files()
    allowed = {
        "gateway/flowweaver_ai_flow_pilot.py",
        "tests/gateway/test_flowweaver_ai_flow_pilot.py",
        "tests/integration/test_flowweaver_phase33_ai_flow_pilot.py",
        "docs/runbooks/flowweaver-ai-flow-pilot.md",
        "docs/plans/2026-05-09-flowweaver-phase33-ai-flow-pilot.md",
        "docs/dev_log/2026-05-09-flowweaver-phase33-ai-flow-pilot.md",
        "docs/plans/2026-05-11-flowweaver-production-enablement-decision-packet.md",
        "docs/runbooks/flowweaver-production-enablement-decision.md",
        "docs/dev_log/2026-05-11-flowweaver-production-enablement-decision-packet.md",
        "docs/plans/2026-05-11-flowweaver-pe1-controlled-sachima-shadow-observation.md",
        "docs/runbooks/flowweaver-pe1-controlled-sachima-shadow-observation.md",
        "docs/dev_log/2026-05-11-flowweaver-pe1-controlled-sachima-shadow-observation.md",
        "gateway/flowweaver_production_shadow_observation.py",
        "tests/gateway/test_flowweaver_pe1_controlled_sachima_shadow_observation.py",
        "tests/integration/test_flowweaver_phase21_production_shadow_observation.py",
        "tests/gateway/test_flowweaver_agent_execution_activity.py",
        "tests/gateway/test_flowweaver_delivery_activity.py",
        "tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py",
        "tests/gateway/test_flowweaver_stub_activity_boundary_contract.py",
        "tests/gateway/test_flowweaver_production_shadow_observation.py",
        "tests/gateway/test_flowweaver_temporal_observation_bridge.py",
        "tests/gateway/test_flowweaver_shadow_publisher.py",
        "tests/gateway/test_flowweaver_stub_activity_orchestration_validation.py",
        "tests/gateway/test_flowweaver_temporal_observation_validation_gate.py",
        "tests/gateway/test_flowweaver_stub_activity_boundary_contract_validation.py",
        "tests/gateway/test_flowweaver_stub_activity_orchestration.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation_design.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation_validation.py",
    }
    forbidden_prefixes = (
        "gateway/platforms/",
        "tools/",
        "plugins/",
        "cron/",
    )
    forbidden_exact = {"gateway/run.py", "run_agent.py", "model_tools.py", "toolsets.py"}

    assert sorted(changed - allowed) == []
    assert not [path for path in changed if path in forbidden_exact or path.startswith(forbidden_prefixes)]
