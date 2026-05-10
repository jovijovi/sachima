"""RED gate tests for FlowWeaver Phase 24 stub Activity orchestration validation."""

from __future__ import annotations

import ast
import copy
import inspect
import subprocess
from pathlib import Path
from typing import Any

import pytest

from gateway.flowweaver_delivery_agent_execution_contract import (
    FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION,
    describe_flowweaver_delivery_agent_execution_contract,
)
from gateway.flowweaver_stub_activity_orchestration import (
    FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_CONTRACT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_RESULT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT,
    FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VERSION,
    describe_flowweaver_stub_activity_orchestration_contract,
    orchestrate_flowweaver_stub_activities,
)
from gateway.flowweaver_stub_activity_orchestration_validation import (
    FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_CONTRACT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_REPORT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_SUCCESS_VERDICT,
    FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_VERSION,
    build_flowweaver_stub_activity_orchestration_validation_report,
    describe_flowweaver_stub_activity_orchestration_validation_contract,
    validate_flowweaver_stub_activity_orchestration_validation_report,
)

ROOT = Path(__file__).resolve().parents[2]
MODULE_SOURCE = ROOT / "gateway" / "flowweaver_stub_activity_orchestration_validation.py"
PLAN_DOC = ROOT / "docs" / "plans" / "2026-05-09-flowweaver-phase24-stub-activity-orchestration-validation.md"
DEV_LOG = ROOT / "docs" / "dev_log" / "2026-05-09-flowweaver-phase24-stub-activity-orchestration-validation.md"
RUNBOOK = ROOT / "docs" / "runbooks" / "flowweaver-stub-activity-orchestration-validation.md"

EXPECTED_CONTRACT_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "scope",
    "consumes_contract",
    "consumes_result",
    "entrypoints",
    "report_fields",
    "checks",
    "separate_approvals",
    "forbidden_side_effects",
    "side_effects",
]
EXPECTED_REPORT_FIELDS = [
    "type",
    "version",
    "phase",
    "ok",
    "verdict",
    "operation",
    "phase23_verdict",
    "activity_sequence",
    "summary",
    "checks",
    "error_code",
    "side_effects",
]
EXPECTED_ACTIVITY_SEQUENCE = [
    {"name": "validate_claim_check_ref", "status": "stubbed"},
    {"name": "execute_agent_turn", "status": "stubbed"},
    {"name": "deliver_artifact", "status": "planned"},
]
EXPECTED_CHECKS = [
    "phase23_contract_valid",
    "orchestration_result_valid",
    "activity_sequence_valid",
    "agent_input_claim_ref_only",
    "delivery_ack_updates_absent",
    "side_effects_absent",
]
EXPECTED_SEPARATE_APPROVALS = [
    "stub_activity_boundary_contract_design",
    "temporal_activity_execution",
    "real_agent_tool_execution",
    "real_send_edit_render_callback_control",
    "production_config_write",
    "gateway_restart",
]
EXPECTED_FORBIDDEN_SIDE_EFFECTS = [
    "temporal_client",
    "worker_lifecycle",
    "workflow_environment",
    "gateway_hook_change",
    "gateway_adapter_access",
    "config_write",
    "file_write",
    "subprocess",
    "socket",
    "docker",
    "daemon",
    "service_startup",
    "send",
    "edit",
    "render",
    "callback_control",
    "agent_execution",
    "tool_execution",
    "temporal_activity_execution",
    "orchestrator_invocation",
]
PRIVATE_CHAT_ID = "oc_" + "phase24_private_chat"
PRIVATE_USER_ID = "ou_" + "phase24_private_user"
PRIVATE_MESSAGE_ID = "om_" + "phase24_private_message"
RAW_PROMPT_VALUE = "raw prompt phase24 private value"
RAW_TOOL_VALUE = "raw " + "tool output phase24 private value"
CARD_JSON_VALUE = '{"type":"card_json","body":"phase24"}'
MEDIA_PATH_VALUE = "/tmp/phase24-private.png"
CALLBACK_VALUE = "callback payload phase24 private value"
RAW_EXCEPTION_VALUE = "RuntimeError: raw phase24 exception value"
SENSITIVE_SENTINEL = "unsafe-" + "material" + "-phase24"
BEARER_VALUE = "Bearer " + "phase24-private"
OPENAI_KEY_VALUE = "sk-" + "phase24-private"


class SneakyDict(dict[str, object]):
    def __eq__(self, other: object) -> bool:  # pragma: no cover - assertion trap
        return True


class SneakyStr(str):
    def __eq__(self, other: object) -> bool:  # pragma: no cover - assertion trap
        return True


class SneakyList(list[object]):
    def __eq__(self, other: object) -> bool:  # pragma: no cover - assertion trap
        return True


def claim_ref(index: int = 0) -> dict[str, object]:
    return {
        "ref": f"claim_ref_phase24_{index}",
        "kind": "agent_input",
        "count": 1,
        "size": 128 + index,
        "checksum_hint": "sha256:" + ("a" * 64),
    }


def execution_request(**overrides: object) -> dict[str, object]:
    request: dict[str, object] = {
        "type": "FlowWeaverExecutionRequest",
        "version": FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION,
        "transaction_id": "runtime_tx_phase24_1",
        "workflow_id": "runtime_tx_phase24_1",
        "intent_id": "runtime_intent_0",
        "execution_mode": "stub_activity_orchestration",
        "input_refs": [claim_ref()],
        "delivery_refs": ["runtime_delivery_0"],
        "approval_gates": [
            "live_config_writes",
            "gateway_restart",
            "production_enablement",
            "real_send_edit_render_callback_control",
            "real_agent_tool_execution",
        ],
        "side_effects": [],
    }
    request.update(overrides)
    return request


def phase23_result(**request_overrides: object) -> dict[str, object]:
    return orchestrate_flowweaver_stub_activities(
        execution_request=execution_request(**request_overrides),
        contract_descriptor=describe_flowweaver_delivery_agent_execution_contract(),
    )


def assert_no_raw_values(value: object) -> None:
    rendered = repr(value).lower()
    for marker in (
        PRIVATE_CHAT_ID.lower(),
        PRIVATE_USER_ID.lower(),
        PRIVATE_MESSAGE_ID.lower(),
        RAW_PROMPT_VALUE,
        RAW_TOOL_VALUE,
        CARD_JSON_VALUE.lower(),
        MEDIA_PATH_VALUE.lower(),
        CALLBACK_VALUE,
        RAW_EXCEPTION_VALUE.lower(),
        SENSITIVE_SENTINEL.lower(),
        BEARER_VALUE.lower(),
        OPENAI_KEY_VALUE.lower(),
        "flowweaverexecutionrequest",
        "execution_request",
        "runtime_tx_phase24_1",
        "claim_ref_phase24_0",
    ):
        assert marker not in rendered


def mutate_list(values: list[str], mode: str) -> list[str]:
    if mode == "missing":
        return values[:-1]
    if mode == "extra":
        return [*values, "unexpected_field"]
    if mode == "reordered":
        return [values[1], values[0], *values[2:]]
    if mode == "duplicated":
        return [*values, values[-1]]
    if mode == "bogus":
        return [*values[:-1], "bogus_field"]
    raise AssertionError(mode)


def rebuilt_with_fields(value: dict[str, Any], fields: list[str]) -> dict[str, object]:
    return {field: value.get(field, "unexpected") for field in fields}


def test_phase24_exposes_pure_synchronous_keyword_only_entrypoints() -> None:
    signature = inspect.signature(build_flowweaver_stub_activity_orchestration_validation_report)
    assert list(signature.parameters) == ["contract_descriptor", "orchestration_result"]
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())
    assert signature.return_annotation == "dict[str, object]"
    assert not inspect.iscoroutinefunction(build_flowweaver_stub_activity_orchestration_validation_report)

    for helper in (
        describe_flowweaver_stub_activity_orchestration_validation_contract,
        validate_flowweaver_stub_activity_orchestration_validation_report,
    ):
        assert not inspect.iscoroutinefunction(helper)


def test_phase24_contract_descriptor_freezes_validation_scope_and_success_verdict() -> None:
    contract = describe_flowweaver_stub_activity_orchestration_validation_contract()

    assert list(contract) == EXPECTED_CONTRACT_FIELDS
    assert contract["type"] == FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_CONTRACT_TYPE
    assert contract["version"] == FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_VERSION
    assert contract["phase"] == "phase24"
    assert contract["verdict"] == FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_SUCCESS_VERDICT
    assert contract["verdict"] == "ready_for_stub_activity_boundary_contract_design"
    assert contract["scope"] == "stub_activity_orchestration_validation"
    assert contract["consumes_contract"] == FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_CONTRACT_TYPE
    assert contract["consumes_result"] == FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_RESULT_TYPE
    assert contract["entrypoints"] == [
        "describe_flowweaver_stub_activity_orchestration_validation_contract",
        "validate_flowweaver_stub_activity_orchestration_validation_report",
        "build_flowweaver_stub_activity_orchestration_validation_report",
    ]
    assert contract["report_fields"] == EXPECTED_REPORT_FIELDS
    assert contract["checks"] == EXPECTED_CHECKS
    assert contract["separate_approvals"] == EXPECTED_SEPARATE_APPROVALS
    assert contract["forbidden_side_effects"] == EXPECTED_FORBIDDEN_SIDE_EFFECTS
    assert contract["side_effects"] == []


def test_phase24_happy_path_builds_safe_high_level_report_from_phase23_result() -> None:
    report = build_flowweaver_stub_activity_orchestration_validation_report(
        contract_descriptor=describe_flowweaver_stub_activity_orchestration_contract(),
        orchestration_result=phase23_result(),
    )

    assert report == {
        "type": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_VERSION,
        "phase": "phase24",
        "ok": True,
        "verdict": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_SUCCESS_VERDICT,
        "operation": "validate_flowweaver_stub_activity_orchestration",
        "phase23_verdict": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT,
        "activity_sequence": EXPECTED_ACTIVITY_SEQUENCE,
        "summary": {"input_refs": 1, "artifacts": 1, "deliveries": 1, "ack_updates": 0},
        "checks": {
            "phase23_contract_valid": True,
            "orchestration_result_valid": True,
            "activity_sequence_valid": True,
            "agent_input_claim_ref_only": True,
            "delivery_ack_updates_absent": True,
            "side_effects_absent": True,
        },
        "error_code": None,
        "side_effects": [],
    }
    assert_no_raw_values(report)

    validated = validate_flowweaver_stub_activity_orchestration_validation_report(copy.deepcopy(report))
    assert validated == report
    assert validated is not report


@pytest.mark.parametrize("mode", ["missing", "extra", "reordered", "bogus"])
def test_phase24_validator_rejects_report_field_mutations(mode: str) -> None:
    report = build_flowweaver_stub_activity_orchestration_validation_report(
        contract_descriptor=describe_flowweaver_stub_activity_orchestration_contract(),
        orchestration_result=phase23_result(),
    )
    mutated = rebuilt_with_fields(report, mutate_list(EXPECTED_REPORT_FIELDS, mode))

    with pytest.raises(ValueError, match="invalid_stub_activity_orchestration_validation_report"):
        validate_flowweaver_stub_activity_orchestration_validation_report(mutated)


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("activity_sequence",), SneakyList()),
        (("activity_sequence", 0, "status"), "running"),
        (("summary", "ack_updates"), 1),
        (("checks", "side_effects_absent"), 1),
        (("error_code",), "invalid_phase23_contract"),
        (("side_effects",), ["agent_execution"]),
        (("verdict",), SneakyStr("ready_for_stub_activity_boundary_contract_design")),
    ],
)
def test_phase24_validator_rejects_hostile_or_nonexact_report_values(path: tuple[object, ...], replacement: object) -> None:
    report = build_flowweaver_stub_activity_orchestration_validation_report(
        contract_descriptor=describe_flowweaver_stub_activity_orchestration_contract(),
        orchestration_result=phase23_result(),
    )
    mutated: dict[str, Any] = copy.deepcopy(report)
    current: Any = mutated
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = replacement

    with pytest.raises(ValueError, match="invalid_stub_activity_orchestration_validation_report"):
        validate_flowweaver_stub_activity_orchestration_validation_report(mutated)


def test_phase24_rejects_mutated_phase23_contract_descriptor_without_fallback() -> None:
    descriptor = describe_flowweaver_stub_activity_orchestration_contract()
    descriptor["verdict"] = "production_enabled"

    report = build_flowweaver_stub_activity_orchestration_validation_report(
        contract_descriptor=descriptor,
        orchestration_result=phase23_result(),
    )

    assert report == {
        "type": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_VERSION,
        "phase": "phase24",
        "ok": False,
        "operation": "validate_flowweaver_stub_activity_orchestration",
        "error_code": "invalid_phase23_contract",
        "side_effects": [],
    }
    assert_no_raw_values(report)


@pytest.mark.parametrize(
    ("path", "replacement", "forbidden_text"),
    [
        (("activity_sequence", 0, "status"), "running", "running"),
        (("delivery_ack_updates",), [{"delivery_id": "runtime_delivery_0"}], "runtime_delivery_0"),
        (("execution_request", "input_refs", 0, "kind"), "message text", "message text"),
        (("side_effects",), ["agent_execution"], "agent_execution"),
    ],
)
def test_phase24_rejects_mutated_orchestration_result_without_echoing_values(
    path: tuple[object, ...], replacement: object, forbidden_text: str
) -> None:
    result: dict[str, Any] = copy.deepcopy(phase23_result())
    current: Any = result
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = replacement

    report = build_flowweaver_stub_activity_orchestration_validation_report(
        contract_descriptor=describe_flowweaver_stub_activity_orchestration_contract(),
        orchestration_result=result,
    )

    assert report == {
        "type": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_VERSION,
        "phase": "phase24",
        "ok": False,
        "operation": "validate_flowweaver_stub_activity_orchestration",
        "error_code": "invalid_phase23_orchestration_result",
        "side_effects": [],
    }
    assert forbidden_text.lower() not in repr(report).lower()
    assert_no_raw_values(report)


@pytest.mark.parametrize(
    "unsafe_value",
    [
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
    ],
)
def test_phase24_error_reports_do_not_echo_raw_material(unsafe_value: str) -> None:
    result: dict[str, Any] = copy.deepcopy(phase23_result())
    result["execution_request"]["input_refs"][0]["kind"] = unsafe_value

    report = build_flowweaver_stub_activity_orchestration_validation_report(
        contract_descriptor=describe_flowweaver_stub_activity_orchestration_contract(),
        orchestration_result=result,
    )

    assert report["ok"] is False
    assert report["error_code"] == "invalid_phase23_orchestration_result"
    assert unsafe_value.lower() not in repr(report).lower()
    assert_no_raw_values(report)


def test_phase24_source_has_no_runtime_lifecycle_execution_or_orchestrator_escape_hatches() -> None:
    tree = ast.parse(MODULE_SOURCE.read_text())
    forbidden_import_roots = {
        "asyncio",
        "logging",
        "subprocess",
        "socket",
        "temporalio",
        "gateway.run",
        "gateway.platforms",
        "run_agent",
        "model_tools",
        "toolsets",
    }
    forbidden_call_names = {
        "open",
        "print",
        "eval",
        "exec",
        "__import__",
        "send_message",
        "edit_message",
        "render",
        "connect",
        "execute_activity",
        "orchestrate_flowweaver_stub_activities",
        "write_text",
        "run",
        "Popen",
        "system",
    }
    forbidden_names = {"Client", "Worker", "WorkflowEnvironment", "AIAgent"}

    for node in ast.walk(tree):
        assert not isinstance(node, (ast.AsyncFunctionDef, ast.Await, ast.With, ast.AsyncWith))
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden_import_roots
                assert not alias.name.startswith("temporalio")
                assert not alias.name.startswith("gateway.platforms")
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module not in forbidden_import_roots
            assert not module.startswith("temporalio")
            assert not module.startswith("gateway.platforms")
            imported_names = {alias.name for alias in node.names}
            assert "orchestrate_flowweaver_stub_activities" not in imported_names
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                assert func.id not in forbidden_call_names
                assert func.id not in forbidden_names
            if isinstance(func, ast.Attribute):
                assert func.attr not in forbidden_call_names
        if isinstance(node, ast.Name):
            assert node.id not in forbidden_names


def test_phase24_changed_file_guard_allows_only_validation_files() -> None:
    changed = _changed_files()
    allowed = {
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
        "docs/plans/2026-05-11-flowweaver-production-enablement-decision-packet.md",
        "docs/runbooks/flowweaver-production-enablement-decision.md",
        "docs/dev_log/2026-05-11-flowweaver-production-enablement-decision-packet.md",
        "tests/gateway/test_flowweaver_stub_activity_orchestration.py",
        "tests/gateway/test_flowweaver_temporal_observation_bridge.py",
        "tests/gateway/test_flowweaver_temporal_observation_validation_gate.py",
        "tests/gateway/test_flowweaver_production_shadow_observation.py",
        "tests/gateway/test_flowweaver_shadow_publisher.py",
    }
    forbidden_exact = {"run_agent.py", "model_tools.py", "toolsets.py", "mcp_serve.py", "gateway/run.py"}
    forbidden_prefixes = ("gateway/platforms/", "tools/", "hermes_cli/")

    assert changed <= allowed
    assert not [path for path in changed if path.startswith(forbidden_prefixes) or path in forbidden_exact]


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _changed_files() -> set[str]:
    base = _git("merge-base", "HEAD", "origin/feature/sachima-channel")
    committed = set(_git("diff", "--name-only", f"{base}...HEAD").splitlines())
    worktree = set(_git("diff", "--name-only").splitlines())
    cached = set(_git("diff", "--cached", "--name-only").splitlines())
    untracked = set(_git("ls-files", "--others", "--exclude-standard").splitlines())
    return {name for name in committed | worktree | cached | untracked if name}


def test_phase24_docs_record_boundaries_verdict_and_verification() -> None:
    for path in (PLAN_DOC, DEV_LOG, RUNBOOK):
        text = path.read_text()
        assert "ready_for_stub_activity_boundary_contract_design" in text
        assert "No Temporal client" in text
        assert "No Worker" in text
        assert "No Gateway restart requirement" in text
        assert "No real agent or tool execution" in text
        assert "No real delivery ACK updates" in text
        assert "orchestrate_flowweaver_stub_activities" in text
        assert "tests/gateway/test_flowweaver_stub_activity_orchestration_validation.py" in text
