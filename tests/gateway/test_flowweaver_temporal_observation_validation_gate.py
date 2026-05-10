"""RED gate tests for FlowWeaver Phase 20 Temporal observation validation."""

from __future__ import annotations

import ast
import copy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PHASE5B_SRC = ROOT / "prototypes" / "flowweaver_phase5b_temporal_poc" / "src"
PHASE5C_SRC = ROOT / "prototypes" / "flowweaver_phase5c_runtime_client" / "src"
MODULE_SOURCE = ROOT / "gateway" / "flowweaver_temporal_observation_validation.py"
BRIDGE_SOURCE = ROOT / "gateway" / "flowweaver_temporal_observation_bridge.py"
for path in (PHASE5C_SRC, PHASE5B_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from gateway.flowweaver_temporal_observation_bridge import (  # noqa: E402
    FLOWWEAVER_TEMPORAL_OBSERVATION_BRIDGE_VERSION,
    TEMPORAL_OBSERVATION_BRIDGE_RESULT_TYPE,
    TEMPORAL_OBSERVATION_SUCCESS_VERDICT,
    observe_gateway_turn_for_flowweaver_temporal,
)
from gateway.flowweaver_temporal_observation_validation import (  # noqa: E402
    FLOWWEAVER_TEMPORAL_OBSERVATION_VALIDATION_VERSION,
    TEMPORAL_OBSERVATION_VALIDATION_REPORT_TYPE,
    TEMPORAL_OBSERVATION_VALIDATION_SUCCESS_VERDICT,
    build_temporal_observation_duplicate_start_report,
    build_temporal_observation_rollback_drill_report,
    build_temporal_observation_validation_report,
)

VALIDATION_OPERATION = "validate_gateway_observation_against_temporal"
WORKFLOW_ID = "runtime_tx_gateway_observation_" + "a" * 20
SENSITIVE_SENTINEL = "unsafe-" + "token" + "-phase20"
PRIVATE_CHAT_ID = "oc_" + "phase20_private_chat"
PRIVATE_USER_ID = "ou_" + "phase20_private_user"
RAW_PROMPT_VALUE = "raw prompt phase20 value"
RAW_TOOL_OUTPUT_VALUE = "raw " + "tool output phase20 value"
CARD_JSON_VALUE = '{"type":"card_json"}'
MEDIA_PATH_VALUE = "/tmp/phase20-private.png"
CALLBACK_VALUE = "callback payload phase20 value"
RAW_EXCEPTION_VALUE = "ValueError: raw exception phase20 value"


def bridge_result(*, workflow_id: str = WORKFLOW_ID, start_status: str = "started") -> dict[str, object]:
    return {
        "type": TEMPORAL_OBSERVATION_BRIDGE_RESULT_TYPE,
        "version": FLOWWEAVER_TEMPORAL_OBSERVATION_BRIDGE_VERSION,
        "ok": True,
        "verdict": TEMPORAL_OBSERVATION_SUCCESS_VERDICT,
        "operation": "observe_gateway_turn_for_flowweaver_temporal",
        "workflow_id": workflow_id,
        "transaction_id": workflow_id,
        "start_status": start_status,
        "query_status": "running",
        "runtime_call_counts": {"start_transaction": 1, "query_transaction": 1},
        "snapshot_summary": {
            "status": "running",
            "entry_count": 1,
            "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
            "counts": {"intents": 1, "artifacts": 1, "deliveries": 1},
            "side_effects": [],
        },
        "checks": {
            "policy_enabled": True,
            "observation_safe": True,
            "start_payload_safe": True,
            "query_snapshot_safe": True,
            "runtime_side_effects_absent": True,
        },
        "side_effects": [],
    }


def disabled_bridge_result() -> dict[str, object]:
    return {
        "type": TEMPORAL_OBSERVATION_BRIDGE_RESULT_TYPE,
        "version": FLOWWEAVER_TEMPORAL_OBSERVATION_BRIDGE_VERSION,
        "ok": False,
        "operation": "observe_gateway_turn_for_flowweaver_temporal",
        "status": "disabled",
        "error_code": "disabled",
        "side_effects": [],
    }


def query_result(*, workflow_id: str = WORKFLOW_ID) -> dict[str, object]:
    return {
        "ok": True,
        "operation": "query_transaction",
        "runtime_operation": "query_snapshot",
        "workflow_id": workflow_id,
        "transaction_id": workflow_id,
        "status": "running",
        "snapshot": {
            "type": "flowweaver.temporal_poc.snapshot.v0",
            "version": "flowweaver.temporal_poc.v0",
            "transaction_id": workflow_id,
            "status": "running",
            "entry_count": 1,
            "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
            "start_signature": {
                "type": "flowweaver.temporal_poc.start_signature.v0",
                "version": "flowweaver.temporal_poc.v0",
                "idempotency_key": "runtime_event_start_gateway_observation_" + "a" * 20,
                "event_contract_digest": "runtime_sig_" + "b" * 64,
                "claim_policy_digest": "runtime_sig_" + "c" * 64,
            },
            "counts": {"intents": 1, "artifacts": 1, "deliveries": 1},
            "intent_statuses": {"runtime_intent_0": "pending"},
            "artifact_statuses": {"runtime_artifact_0": "planned"},
            "delivery_statuses": {"runtime_delivery_0": "planned"},
            "applied_event_count": 0,
            "resume_count": 0,
            "side_effects": [],
        },
    }


def assert_no_forbidden_output(value: object) -> None:
    rendered = repr(value).lower()
    forbidden_values = (
        SENSITIVE_SENTINEL.lower(),
        PRIVATE_CHAT_ID.lower(),
        PRIVATE_USER_ID.lower(),
        RAW_PROMPT_VALUE,
        RAW_TOOL_OUTPUT_VALUE,
        CARD_JSON_VALUE.lower(),
        MEDIA_PATH_VALUE.lower(),
        CALLBACK_VALUE,
        RAW_EXCEPTION_VALUE.lower(),
    )
    for marker in forbidden_values:
        assert marker not in rendered


class SneakyStr(str):
    pass


class FlakyQueryControlSurface:
    def __init__(self, *, fail_queries: int = 2) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail_queries = fail_queries

    async def handle(self, request: object) -> dict[str, object]:
        assert type(request) is dict
        safe_request = copy.deepcopy(request)
        self.calls.append(safe_request)
        operation = safe_request["operation"]
        workflow_id = safe_request["workflow_id"]
        if operation == "start_transaction":
            return {
                "ok": True,
                "operation": "start_transaction",
                "runtime_operation": "start_transaction",
                "workflow_id": workflow_id,
                "transaction_id": workflow_id,
                "status": "started",
            }
        if operation == "query_transaction" and self.fail_queries:
            self.fail_queries -= 1
            return {"ok": False, "operation": "query_transaction", "runtime_operation": "query_snapshot", "error_code": "runtime_error"}
        if operation == "query_transaction":
            return query_result(workflow_id=str(workflow_id))
        raise AssertionError(f"forbidden operation: {operation}")


def enabled_policy() -> dict[str, object]:
    return {
        "type": "flowweaver.gateway.temporal_observation_bridge_policy.v0",
        "enabled": True,
        "mode": "controlled_observation",
        "allow_runtime_start": True,
        "allow_runtime_query": True,
        "side_effects": [],
    }


def safe_observation(**overrides: object) -> dict[str, object]:
    observation: dict[str, object] = {
        "type": "flowweaver.gateway.temporal_observation.v0",
        "version": "flowweaver.gateway.temporal_observation.v0",
        "source": "controlled_gateway_observation",
        "session_label": "safe_session_phase20",
        "turn_label": "safe_turn_phase20",
        "turn_discriminator": "safe_discriminator_000001_000001",
        "entry_count": 1,
        "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
        "claim_refs": {
            "input_ref": "claim_ref_gateway_observation_input_phase20",
            "artifact_ref": "claim_ref_gateway_observation_artifact_phase20",
            "delivery_ref": "claim_ref_gateway_observation_delivery_phase20",
        },
        "surfaces": ["final_text"],
        "checks": {
            "payloads_absent": True,
            "claim_check_refs_only": True,
            "side_effects_absent": True,
            "source_ids_sanitized": True,
        },
        "side_effects": [],
    }
    observation.update(overrides)
    return observation


def test_phase20_validation_report_success_shape_is_safe_and_high_level_only() -> None:
    duplicate = build_temporal_observation_duplicate_start_report(
        first_bridge_result=bridge_result(start_status="started"),
        duplicate_bridge_result=bridge_result(start_status="running"),
    )
    rollback = build_temporal_observation_rollback_drill_report(
        enabled_bridge_result=bridge_result(),
        disabled_bridge_result=disabled_bridge_result(),
        existing_query_result=query_result(),
    )

    report = build_temporal_observation_validation_report(
        bridge_result=bridge_result(),
        history_json='{"events":[{"safe":"runtime_tx_gateway_observation"}]}',
        history_event_bytes=b"safe runtime history bytes",
        duplicate_start_report=duplicate,
        rollback_drill=rollback,
    )

    assert report == {
        "type": TEMPORAL_OBSERVATION_VALIDATION_REPORT_TYPE,
        "version": FLOWWEAVER_TEMPORAL_OBSERVATION_VALIDATION_VERSION,
        "ok": True,
        "verdict": TEMPORAL_OBSERVATION_VALIDATION_SUCCESS_VERDICT,
        "operation": VALIDATION_OPERATION,
        "bridge_checks": {"phase19_verdict": TEMPORAL_OBSERVATION_SUCCESS_VERDICT, "start_query_only": True, "side_effects_absent": True},
        "history_checks": {"json_scanned": True, "event_bytes_scanned": True, "forbidden_material_absent": True},
        "duplicate_start": {"status": "idempotent", "start_statuses": ["started", "running"]},
        "rollback": {"status": "verified", "operator_actions": ["disable_observation_policy", "verify_existing_snapshot"]},
        "side_effects": [],
    }
    assert_no_forbidden_output(report)


@pytest.mark.parametrize(
    ("history_json", "history_event_bytes"),
    [
        (f'{{"chat":"{PRIVATE_CHAT_ID}"}}', b"safe bytes"),
        ('{"safe":true}', b"prefix " + SENSITIVE_SENTINEL.encode("utf-8")),
        (f'{{"prompt":"{RAW_PROMPT_VALUE}"}}', b"safe bytes"),
        (f'{{"tool_output":"{RAW_TOOL_OUTPUT_VALUE}"}}', b"safe bytes"),
        ('{"safe":true}', f'{{"tool_output":"{RAW_TOOL_OUTPUT_VALUE}"}}'.encode("utf-8")),
        ('{"tool_output" : "phase20 hidden value"}', b"safe bytes"),
        ('{"safe":true}', b'{"tool_output" : "phase20 hidden value"}'),
        (f'{{"card":{CARD_JSON_VALUE}}}', b"safe bytes"),
        (f'{{"media":"{MEDIA_PATH_VALUE}"}}', b"safe bytes"),
        (f'{{"callback":"{CALLBACK_VALUE}"}}', b"safe bytes"),
        (f'{{"exc":"{RAW_EXCEPTION_VALUE}"}}', b"safe bytes"),
    ],
)
def test_phase20_history_scan_rejects_forbidden_json_or_event_byte_material(
    history_json: str,
    history_event_bytes: bytes,
) -> None:
    report = build_temporal_observation_validation_report(
        bridge_result=bridge_result(),
        history_json=history_json,
        history_event_bytes=history_event_bytes,
        duplicate_start_report=build_temporal_observation_duplicate_start_report(
            first_bridge_result=bridge_result(start_status="started"),
            duplicate_bridge_result=bridge_result(start_status="running"),
        ),
        rollback_drill=build_temporal_observation_rollback_drill_report(
            enabled_bridge_result=bridge_result(),
            disabled_bridge_result=disabled_bridge_result(),
            existing_query_result=query_result(),
        ),
    )

    assert report == {
        "type": TEMPORAL_OBSERVATION_VALIDATION_REPORT_TYPE,
        "version": FLOWWEAVER_TEMPORAL_OBSERVATION_VALIDATION_VERSION,
        "ok": False,
        "operation": VALIDATION_OPERATION,
        "error_code": "history_contains_forbidden_material",
        "side_effects": [],
    }
    assert_no_forbidden_output(report)


def test_phase20_validation_rejects_hostile_scalar_subclasses_without_echo() -> None:
    report = build_temporal_observation_validation_report(
        bridge_result=bridge_result(),
        history_json=SneakyStr('{"safe":true}'),
        history_event_bytes=b"safe bytes",
        duplicate_start_report=build_temporal_observation_duplicate_start_report(
            first_bridge_result=bridge_result(start_status="started"),
            duplicate_bridge_result=bridge_result(start_status="running"),
        ),
        rollback_drill=build_temporal_observation_rollback_drill_report(
            enabled_bridge_result=bridge_result(),
            disabled_bridge_result=disabled_bridge_result(),
            existing_query_result=query_result(),
        ),
    )

    assert report == {
        "type": TEMPORAL_OBSERVATION_VALIDATION_REPORT_TYPE,
        "version": FLOWWEAVER_TEMPORAL_OBSERVATION_VALIDATION_VERSION,
        "ok": False,
        "operation": VALIDATION_OPERATION,
        "error_code": "invalid_history_evidence",
        "side_effects": [],
    }
    assert_no_forbidden_output(report)


@pytest.mark.asyncio
async def test_phase20_bridge_retries_sanitized_query_unavailability_before_failing_closed() -> None:
    control = FlakyQueryControlSurface(fail_queries=2)

    result = await observe_gateway_turn_for_flowweaver_temporal(
        observation=safe_observation(),
        runtime_control_surface=control,
        bridge_policy=enabled_policy(),
    )

    assert result["ok"] is True
    assert result["query_status"] == "running"
    assert [call["operation"] for call in control.calls] == [
        "start_transaction",
        "query_transaction",
        "query_transaction",
        "query_transaction",
    ]
    assert_no_forbidden_output(result)


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _phase_diff_base() -> str:
    parents = _git("rev-list", "--parents", "-n", "1", "HEAD").split()
    if len(parents) > 2:
        return "HEAD"
    return _git("merge-base", "HEAD", "origin/feature/sachima-channel")


def _changed_files() -> set[str]:
    base = _phase_diff_base()
    committed = set(_git("diff", "--name-only", f"{base}..HEAD").splitlines())
    worktree = set(_git("diff", "--name-only").splitlines())
    cached = set(_git("diff", "--cached", "--name-only").splitlines())
    untracked = set(_git("ls-files", "--others", "--exclude-standard").splitlines())
    return {name for name in committed | worktree | cached | untracked if name}


def test_phase20_diff_stays_inside_guarded_validation_allowlist() -> None:
    changed_files = _changed_files()
    allowed_changed_files = {
        "docs/plans/2026-05-10-flowweaver-phase20-guarded-temporal-observation-validation.md",
        "docs/dev_log/2026-05-10-flowweaver-phase20-guarded-temporal-observation-validation.md",
        "docs/runbooks/flowweaver-temporal-observation-validation.md",
        "gateway/flowweaver_temporal_observation_bridge.py",
        "gateway/flowweaver_temporal_observation_validation.py",
        "tests/gateway/test_flowweaver_temporal_observation_validation_gate.py",
        "tests/integration/test_flowweaver_phase20_temporal_observation_validation.py",
        "docs/plans/2026-05-11-flowweaver-phase21-production-shadow-observation-only.md",
        "docs/dev_log/2026-05-11-flowweaver-phase21-production-shadow-observation-only.md",
        "docs/runbooks/flowweaver-production-shadow-observation.md",
        "gateway/flowweaver_production_shadow_observation.py",
        "gateway/run.py",
        "tests/gateway/test_flowweaver_production_shadow_observation.py",
        "tests/integration/test_flowweaver_phase21_production_shadow_observation.py",
        "tests/gateway/test_flowweaver_shadow_publisher.py",
        "tests/prototypes/test_flowweaver_phase5c_tool_surface.py",
        "tests/gateway/test_flowweaver_temporal_observation_bridge.py",
        "tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py",
        "tests/integration/test_flowweaver_phase5i_start_signature_parity.py",
        "tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py",
        "tests/integration/test_flowweaver_phase5k_runtime_control_surface.py",
        "docs/plans/2026-05-09-flowweaver-phase22-delivery-agent-execution-contract-gate.md",
        "docs/dev_log/2026-05-09-flowweaver-phase22-delivery-agent-execution-contract-gate.md",
        "docs/runbooks/flowweaver-delivery-agent-execution-contract.md",
        "gateway/flowweaver_delivery_agent_execution_contract.py",
        "tests/gateway/test_flowweaver_delivery_agent_execution_contract.py",
        "docs/plans/2026-05-09-flowweaver-phase23-stub-activity-orchestration.md",
        "docs/dev_log/2026-05-09-flowweaver-phase23-stub-activity-orchestration.md",
        "docs/runbooks/flowweaver-stub-activity-orchestration.md",
        "gateway/flowweaver_stub_activity_orchestration.py",
        "tests/gateway/test_flowweaver_stub_activity_orchestration.py",
        "docs/plans/2026-05-09-flowweaver-phase24-stub-activity-orchestration-validation.md",
        "docs/dev_log/2026-05-09-flowweaver-phase24-stub-activity-orchestration-validation.md",
        "docs/runbooks/flowweaver-stub-activity-orchestration-validation.md",
        "gateway/flowweaver_stub_activity_orchestration_validation.py",
        "tests/gateway/test_flowweaver_stub_activity_orchestration_validation.py",
        "docs/plans/2026-05-09-flowweaver-phase25-stub-activity-boundary-contract.md",
        "docs/dev_log/2026-05-09-flowweaver-phase25-stub-activity-boundary-contract.md",
        "docs/runbooks/flowweaver-stub-activity-boundary-contract.md",
        "gateway/flowweaver_stub_activity_boundary_contract.py",
        "tests/gateway/test_flowweaver_stub_activity_boundary_contract.py",
        "docs/plans/2026-05-09-flowweaver-phase26-stub-activity-boundary-contract-validation.md",
        "docs/dev_log/2026-05-09-flowweaver-phase26-stub-activity-boundary-contract-validation.md",
        "docs/runbooks/flowweaver-stub-activity-boundary-contract-validation.md",
        "gateway/flowweaver_stub_activity_boundary_contract_validation.py",
        "tests/gateway/test_flowweaver_stub_activity_boundary_contract_validation.py",
        "docs/plans/2026-05-09-flowweaver-phase27-stub-activity-implementation-design.md",
        "docs/dev_log/2026-05-09-flowweaver-phase27-stub-activity-implementation-design.md",
        "docs/runbooks/flowweaver-stub-activity-implementation-design.md",
        "gateway/flowweaver_stub_activity_implementation_design.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation_design.py",
        "docs/plans/2026-05-09-flowweaver-phase28-stub-activity-implementation-validation.md",
        "docs/dev_log/2026-05-09-flowweaver-phase28-stub-activity-implementation-validation.md",
        "docs/runbooks/flowweaver-stub-activity-implementation-validation.md",
        "gateway/flowweaver_stub_activity_implementation_validation.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation_validation.py",
        "docs/plans/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md",
        "docs/dev_log/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md",
        "docs/plans/2026-05-09-flowweaver-phase29-stub-activity-implementation.md",
        "docs/dev_log/2026-05-09-flowweaver-phase29-stub-activity-implementation.md",
        "docs/runbooks/flowweaver-stub-activity-implementation.md",
        "gateway/flowweaver_stub_activity_implementation.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation.py",
        "docs/plans/2026-05-09-flowweaver-phase30-temporal-stub-activity-orchestration.md",
        "docs/dev_log/2026-05-09-flowweaver-phase30-temporal-stub-activity-orchestration.md",
        "docs/runbooks/flowweaver-temporal-stub-activity-orchestration.md",
        "gateway/flowweaver_temporal_stub_activity_orchestration.py",
        "tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py",
        "docs/plans/2026-05-09-flowweaver-phase31-agent-execution-activity.md",
        "docs/dev_log/2026-05-09-flowweaver-phase31-agent-execution-activity.md",
        "docs/runbooks/flowweaver-agent-execution-activity.md",
        "gateway/flowweaver_agent_execution_activity.py",
        "tests/gateway/test_flowweaver_agent_execution_activity.py",
        "tests/integration/test_flowweaver_phase31_agent_execution_activity.py",
        "gateway/flowweaver_delivery_activity.py",
        "tests/gateway/test_flowweaver_delivery_activity.py",
        "tests/integration/test_flowweaver_phase32_delivery_activity_ack_reconciliation.py",
        "docs/runbooks/flowweaver-delivery-activity-ack-reconciliation.md",
        "docs/plans/2026-05-09-flowweaver-phase32-delivery-activity-ack-reconciliation.md",
        "docs/dev_log/2026-05-09-flowweaver-phase32-delivery-activity-ack-reconciliation.md",
        "gateway/flowweaver_ai_flow_pilot.py",
        "tests/gateway/test_flowweaver_ai_flow_pilot.py",
        "tests/integration/test_flowweaver_phase33_ai_flow_pilot.py",
        "docs/runbooks/flowweaver-ai-flow-pilot.md",
        "docs/plans/2026-05-09-flowweaver-phase33-ai-flow-pilot.md",
        "docs/dev_log/2026-05-09-flowweaver-phase33-ai-flow-pilot.md",
    }
    forbidden_prefixes = ("gateway/platforms/", "tools/", "hermes_cli/")
    forbidden_exact = {"pyproject.toml", "run_agent.py", "model_tools.py", "toolsets.py"}

    assert sorted(changed_files - allowed_changed_files) == []
    assert not [path for path in changed_files if path in forbidden_exact or path.startswith(forbidden_prefixes)]


def test_phase20_validation_source_has_no_production_gateway_or_worker_lifecycle() -> None:
    assert MODULE_SOURCE.exists(), "Phase 20 must add the validation helper module"
    tree = ast.parse(MODULE_SOURCE.read_text(encoding="utf-8") + "\n" + BRIDGE_SOURCE.read_text(encoding="utf-8"))
    imports: list[str] = []
    calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)

    forbidden_import_roots = {"temporalio", "gateway.platforms", "tools", "socket", "subprocess", "logging", "os"}
    forbidden_call_names = {
        "Client",
        "Worker",
        "WorkflowEnvironment",
        "connect",
        "connect_local_temporal",
        "start_workflow",
        "execute_update",
        "send_message",
        "edit_message",
        "render",
        "callback",
        "write_text",
        "system",
        "Popen",
        "run",
    }

    assert sorted(root for root in imports if root in forbidden_import_roots) == []
    assert sorted(call for call in calls if call in forbidden_call_names) == []
