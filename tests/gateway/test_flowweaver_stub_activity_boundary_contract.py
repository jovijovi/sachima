"""RED gate tests for FlowWeaver Phase 25 stub Activity boundary contract."""

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
from gateway.flowweaver_stub_activity_boundary_contract import (
    FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_REPORT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_SUCCESS_VERDICT,
    FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VERSION,
    build_flowweaver_stub_activity_boundary_contract_report,
    describe_flowweaver_stub_activity_boundary_contract,
    validate_flowweaver_stub_activity_boundary_contract_report,
)
from gateway.flowweaver_stub_activity_orchestration import (
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
)

ROOT = Path(__file__).resolve().parents[2]
MODULE_SOURCE = ROOT / "gateway" / "flowweaver_stub_activity_boundary_contract.py"
PLAN_DOC = ROOT / "docs" / "plans" / "2026-05-09-flowweaver-phase25-stub-activity-boundary-contract.md"
DEV_LOG = ROOT / "docs" / "dev_log" / "2026-05-09-flowweaver-phase25-stub-activity-boundary-contract.md"
RUNBOOK = ROOT / "docs" / "runbooks" / "flowweaver-stub-activity-boundary-contract.md"

EXPECTED_CONTRACT_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "scope",
    "consumes_contract",
    "consumes_report",
    "entrypoints",
    "activity_interfaces",
    "payload_policy",
    "execution_policy",
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
    "phase24_verdict",
    "activity_interfaces",
    "payload_policy",
    "execution_policy",
    "checks",
    "error_code",
    "side_effects",
]
EXPECTED_ACTIVITY_INTERFACES = [
    {
        "name": "validate_claim_check_ref",
        "input_fields": ["ref", "kind", "count", "size", "checksum_hint"],
        "result_fields": ["activity", "status", "claim_ref", "error_code", "side_effects"],
        "allowed_statuses": ["validated", "rejected"],
        "error_codes": ["invalid_claim_ref", "noncanonical_claim_kind", "unsafe_material"],
        "side_effects": [],
    },
    {
        "name": "execute_agent_turn",
        "input_fields": ["transaction_id", "workflow_id", "intent_id", "input_ref", "artifact_ref", "execution_mode"],
        "result_fields": ["activity", "status", "artifact_ref", "error_code", "side_effects"],
        "allowed_statuses": ["stubbed", "rejected"],
        "error_codes": ["invalid_agent_activity_input", "unsafe_material", "agent_execution_not_approved"],
        "side_effects": [],
    },
    {
        "name": "deliver_artifact",
        "input_fields": ["transaction_id", "workflow_id", "delivery_ref", "artifact_ref", "surface"],
        "result_fields": ["activity", "status", "delivery_ref", "error_code", "side_effects"],
        "allowed_statuses": ["planned", "rejected"],
        "error_codes": ["invalid_delivery_activity_input", "unsafe_material", "delivery_execution_not_approved"],
        "side_effects": [],
    },
]
EXPECTED_PAYLOAD_POLICY = {
    "mode": "claim_check_refs_only",
    "canonical_input_kind": "agent_input",
    "allowed_reference_fields": ["ref", "kind", "count", "size", "checksum_hint"],
    "forbidden_material": [
        "raw_prompt",
        "message_text",
        "tool_output",
        "card_json",
        "media_path",
        "platform_private_id",
        "callback_payload",
        "credential",
        "raw_exception_text",
    ],
    "side_effects": [],
}
EXPECTED_EXECUTION_POLICY = {
    "mode": "metadata_only_no_activity_execution",
    "timeout_policy": "metadata_label_only",
    "retry_policy": "metadata_label_only",
    "lifecycle_owner": "future_worker_separate_approval",
    "side_effects": [],
}
EXPECTED_CHECKS = [
    "phase24_contract_valid",
    "phase24_report_valid",
    "activity_interfaces_defined",
    "payload_policy_refs_only",
    "execution_policy_metadata_only",
    "side_effects_absent",
]
EXPECTED_SEPARATE_APPROVALS = [
    "stub_activity_boundary_contract_validation",
    "temporal_activity_implementation",
    "worker_lifecycle",
    "real_agent_tool_execution",
    "real_send_edit_render_callback_control",
    "delivery_ack_updates",
    "production_config_write",
    "gateway_restart",
]
EXPECTED_FORBIDDEN_SIDE_EFFECTS = [
    "temporal_sdk_import",
    "temporal_client",
    "worker_lifecycle",
    "workflow_environment",
    "activity_definition",
    "workflow_execute_activity",
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
    "delivery_ack_update",
    "agent_execution",
    "tool_execution",
    "prototype_import",
    "orchestrator_invocation",
    "validation_report_builder_invocation",
]
PRIVATE_CHAT_ID = "oc_" + "phase25_private_chat"
PRIVATE_USER_ID = "ou_" + "phase25_private_user"
PRIVATE_MESSAGE_ID = "om_" + "phase25_private_message"
RAW_PROMPT_VALUE = "raw prompt phase25 private value"
RAW_TOOL_VALUE = "raw " + "tool output phase25 private value"
CARD_JSON_VALUE = '{"type":"card_json","body":"phase25"}'
MEDIA_PATH_VALUE = "/tmp/phase25-private.png"
CALLBACK_VALUE = "callback payload phase25 private value"
RAW_EXCEPTION_VALUE = "RuntimeError: raw phase25 exception value"
SENSITIVE_SENTINEL = "unsafe-" + "material" + "-phase25"
BEARER_VALUE = "Bearer " + "phase25-private"
OPENAI_KEY_VALUE = "sk-" + "phase25-private"


class SneakyDict(dict[str, object]):
    def __eq__(self, other: object) -> bool:  # pragma: no cover - assertion trap
        return True


class SneakyStr(str):
    def __eq__(self, other: object) -> bool:  # pragma: no cover - assertion trap
        return True


class SneakyList(list[object]):
    def __eq__(self, other: object) -> bool:  # pragma: no cover - assertion trap
        return True


def claim_ref() -> dict[str, object]:
    return {
        "ref": "claim_ref_phase25_0",
        "kind": "agent_input",
        "count": 1,
        "size": 128,
        "checksum_hint": "sha256:" + ("a" * 64),
    }


def execution_request() -> dict[str, object]:
    return {
        "type": "FlowWeaverExecutionRequest",
        "version": FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION,
        "transaction_id": "runtime_tx_phase25_1",
        "workflow_id": "runtime_tx_phase25_1",
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


def phase24_report() -> dict[str, object]:
    phase23_result = orchestrate_flowweaver_stub_activities(
        execution_request=execution_request(),
        contract_descriptor=describe_flowweaver_delivery_agent_execution_contract(),
    )
    return build_flowweaver_stub_activity_orchestration_validation_report(
        contract_descriptor=describe_flowweaver_stub_activity_orchestration_contract(),
        orchestration_result=phase23_result,
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
        "runtime_tx_phase25_1",
        "claim_ref_phase25_0",
    ):
        assert marker not in rendered


def mutate_list(values: list[str], mode: str) -> list[str]:
    if mode == "missing":
        return values[:-1]
    if mode == "extra":
        return [*values, "unexpected_field"]
    if mode == "reordered":
        return [values[1], values[0], *values[2:]]
    if mode == "bogus":
        return [*values[:-1], "bogus_field"]
    raise AssertionError(mode)


def rebuilt_with_fields(value: dict[str, Any], fields: list[str]) -> dict[str, object]:
    return {field: value.get(field, "unexpected") for field in fields}


def test_phase25_exposes_pure_synchronous_keyword_only_entrypoints() -> None:
    signature = inspect.signature(build_flowweaver_stub_activity_boundary_contract_report)
    assert list(signature.parameters) == ["validation_contract_descriptor", "validation_report"]
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())
    assert signature.return_annotation == "dict[str, object]"
    assert not inspect.iscoroutinefunction(build_flowweaver_stub_activity_boundary_contract_report)

    for helper in (
        describe_flowweaver_stub_activity_boundary_contract,
        validate_flowweaver_stub_activity_boundary_contract_report,
    ):
        assert not inspect.iscoroutinefunction(helper)


def test_phase25_contract_descriptor_freezes_boundary_contract_scope_and_success_verdict() -> None:
    contract = describe_flowweaver_stub_activity_boundary_contract()

    assert list(contract) == EXPECTED_CONTRACT_FIELDS
    assert contract["type"] == FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_TYPE
    assert contract["version"] == FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VERSION
    assert contract["phase"] == "phase25"
    assert contract["verdict"] == FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_SUCCESS_VERDICT
    assert contract["verdict"] == "ready_for_stub_activity_boundary_contract_validation"
    assert contract["scope"] == "stub_activity_boundary_contract"
    assert contract["consumes_contract"] == FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_CONTRACT_TYPE
    assert contract["consumes_report"] == FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_REPORT_TYPE
    assert contract["entrypoints"] == [
        "describe_flowweaver_stub_activity_boundary_contract",
        "validate_flowweaver_stub_activity_boundary_contract_report",
        "build_flowweaver_stub_activity_boundary_contract_report",
    ]
    assert contract["activity_interfaces"] == EXPECTED_ACTIVITY_INTERFACES
    assert contract["payload_policy"] == EXPECTED_PAYLOAD_POLICY
    assert contract["execution_policy"] == EXPECTED_EXECUTION_POLICY
    assert contract["checks"] == EXPECTED_CHECKS
    assert contract["separate_approvals"] == EXPECTED_SEPARATE_APPROVALS
    assert contract["forbidden_side_effects"] == EXPECTED_FORBIDDEN_SIDE_EFFECTS
    assert contract["side_effects"] == []


def test_phase25_happy_path_builds_safe_boundary_report_from_phase24_validation_report() -> None:
    report = build_flowweaver_stub_activity_boundary_contract_report(
        validation_contract_descriptor=describe_flowweaver_stub_activity_orchestration_validation_contract(),
        validation_report=phase24_report(),
    )

    assert report == {
        "type": FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VERSION,
        "phase": "phase25",
        "ok": True,
        "verdict": FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_SUCCESS_VERDICT,
        "operation": "define_flowweaver_stub_activity_boundary_contract",
        "phase24_verdict": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_SUCCESS_VERDICT,
        "activity_interfaces": EXPECTED_ACTIVITY_INTERFACES,
        "payload_policy": EXPECTED_PAYLOAD_POLICY,
        "execution_policy": EXPECTED_EXECUTION_POLICY,
        "checks": {
            "phase24_contract_valid": True,
            "phase24_report_valid": True,
            "activity_interfaces_defined": True,
            "payload_policy_refs_only": True,
            "execution_policy_metadata_only": True,
            "side_effects_absent": True,
        },
        "error_code": None,
        "side_effects": [],
    }
    assert_no_raw_values(report)

    validated = validate_flowweaver_stub_activity_boundary_contract_report(copy.deepcopy(report))
    assert validated == report
    assert validated is not report


def test_phase25_report_freezes_exact_activity_interface_shapes_payload_policy_and_execution_policy() -> None:
    report = build_flowweaver_stub_activity_boundary_contract_report(
        validation_contract_descriptor=describe_flowweaver_stub_activity_orchestration_validation_contract(),
        validation_report=phase24_report(),
    )

    assert [item["name"] for item in report["activity_interfaces"]] == [
        "validate_claim_check_ref",
        "execute_agent_turn",
        "deliver_artifact",
    ]
    assert report["payload_policy"]["mode"] == "claim_check_refs_only"
    assert report["payload_policy"]["canonical_input_kind"] == "agent_input"
    assert report["payload_policy"]["allowed_reference_fields"] == ["ref", "kind", "count", "size", "checksum_hint"]
    assert report["execution_policy"] == EXPECTED_EXECUTION_POLICY
    assert all(item["side_effects"] == [] for item in report["activity_interfaces"])


@pytest.mark.parametrize("mode", ["missing", "extra", "reordered", "bogus"])
def test_phase25_validator_rejects_report_field_mutations(mode: str) -> None:
    report = build_flowweaver_stub_activity_boundary_contract_report(
        validation_contract_descriptor=describe_flowweaver_stub_activity_orchestration_validation_contract(),
        validation_report=phase24_report(),
    )
    mutated = rebuilt_with_fields(report, mutate_list(EXPECTED_REPORT_FIELDS, mode))

    with pytest.raises(ValueError, match="invalid_stub_activity_boundary_contract_report"):
        validate_flowweaver_stub_activity_boundary_contract_report(mutated)


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("activity_interfaces",), SneakyList()),
        (("activity_interfaces", 0, "allowed_statuses"), ["validated", "running"]),
        (("payload_policy", "canonical_input_kind"), "message text"),
        (("execution_policy", "mode"), "execute_temporal_activity"),
        (("checks", "side_effects_absent"), 1),
        (("error_code",), "invalid_phase24_report"),
        (("side_effects",), ["agent_execution"]),
        (("verdict",), SneakyStr("ready_for_stub_activity_boundary_contract_validation")),
    ],
)
def test_phase25_validator_rejects_hostile_or_nonexact_report_values(path: tuple[object, ...], replacement: object) -> None:
    report = build_flowweaver_stub_activity_boundary_contract_report(
        validation_contract_descriptor=describe_flowweaver_stub_activity_orchestration_validation_contract(),
        validation_report=phase24_report(),
    )
    mutated: dict[str, Any] = copy.deepcopy(report)
    current: Any = mutated
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = replacement

    with pytest.raises(ValueError, match="invalid_stub_activity_boundary_contract_report"):
        validate_flowweaver_stub_activity_boundary_contract_report(mutated)


def test_phase25_rejects_invalid_phase24_contract_with_sanitized_error_report() -> None:
    descriptor = describe_flowweaver_stub_activity_orchestration_validation_contract()
    descriptor["verdict"] = "production_enabled"

    report = build_flowweaver_stub_activity_boundary_contract_report(
        validation_contract_descriptor=descriptor,
        validation_report=phase24_report(),
    )

    assert report == {
        "type": FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VERSION,
        "phase": "phase25",
        "ok": False,
        "operation": "define_flowweaver_stub_activity_boundary_contract",
        "error_code": "invalid_phase24_validation_contract",
        "side_effects": [],
    }
    assert_no_raw_values(report)


def test_phase25_rejects_invalid_phase24_report_with_sanitized_error_report() -> None:
    prior = phase24_report()
    prior["verdict"] = "production_enabled"

    report = build_flowweaver_stub_activity_boundary_contract_report(
        validation_contract_descriptor=describe_flowweaver_stub_activity_orchestration_validation_contract(),
        validation_report=prior,
    )

    assert report == {
        "type": FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VERSION,
        "phase": "phase25",
        "ok": False,
        "operation": "define_flowweaver_stub_activity_boundary_contract",
        "error_code": "invalid_phase24_validation_report",
        "side_effects": [],
    }
    assert_no_raw_values(report)


def test_phase25_rejects_phase24_error_report_with_sanitized_error_report() -> None:
    prior_error = {
        "type": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VALIDATION_VERSION,
        "phase": "phase24",
        "ok": False,
        "operation": "validate_flowweaver_stub_activity_orchestration",
        "error_code": "invalid_phase23_contract",
        "side_effects": [],
    }

    report = build_flowweaver_stub_activity_boundary_contract_report(
        validation_contract_descriptor=describe_flowweaver_stub_activity_orchestration_validation_contract(),
        validation_report=prior_error,
    )

    assert report == {
        "type": FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_BOUNDARY_CONTRACT_VERSION,
        "phase": "phase25",
        "ok": False,
        "operation": "define_flowweaver_stub_activity_boundary_contract",
        "error_code": "invalid_phase24_validation_report",
        "side_effects": [],
    }
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
def test_phase25_error_reports_do_not_echo_raw_material(unsafe_value: str) -> None:
    prior = phase24_report()
    prior["phase24_verdict"] = unsafe_value

    report = build_flowweaver_stub_activity_boundary_contract_report(
        validation_contract_descriptor=describe_flowweaver_stub_activity_orchestration_validation_contract(),
        validation_report=prior,
    )

    assert report["ok"] is False
    assert report["error_code"] == "invalid_phase24_validation_report"
    assert unsafe_value.lower() not in repr(report).lower()
    assert_no_raw_values(report)


def test_phase25_source_has_no_temporal_gateway_runtime_activity_execution_or_orchestrator_escape_hatches() -> None:
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
        "prototypes",
    }
    forbidden_import_names = {
        "orchestrate_flowweaver_stub_activities",
        "build_flowweaver_stub_activity_orchestration_validation_report",
    }
    forbidden_call_names = {
        "open",
        "print",
        "eval",
        "exec",
        "__import__",
        "getattr",
        "send_message",
        "edit_message",
        "render",
        "connect",
        "execute_activity",
        "orchestrate_flowweaver_stub_activities",
        "build_flowweaver_stub_activity_orchestration_validation_report",
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
                assert not alias.name.startswith("prototypes")
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module not in forbidden_import_roots
            assert not module.startswith("temporalio")
            assert not module.startswith("gateway.platforms")
            assert not module.startswith("prototypes")
            imported_names = {alias.name for alias in node.names}
            assert not (imported_names & forbidden_import_names)
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                assert func.id not in forbidden_call_names
                assert func.id not in forbidden_names
            if isinstance(func, ast.Attribute):
                assert func.attr not in forbidden_call_names
        if isinstance(node, ast.Name):
            assert node.id not in forbidden_names


def test_phase25_changed_file_guard_allows_only_boundary_contract_files() -> None:
    changed = _changed_files()
    allowed = {
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
        "tests/gateway/test_flowweaver_stub_activity_orchestration.py",
        "tests/gateway/test_flowweaver_stub_activity_orchestration_validation.py",
        "tests/gateway/test_flowweaver_temporal_observation_bridge.py",
        "tests/gateway/test_flowweaver_temporal_observation_validation_gate.py",
        "tests/gateway/test_flowweaver_production_shadow_observation.py",
        "tests/gateway/test_flowweaver_shadow_publisher.py",
    }
    forbidden_exact = {"run_agent.py", "model_tools.py", "toolsets.py", "mcp_serve.py", "gateway/run.py"}
    forbidden_prefixes = ("gateway/platforms/", "tools/", "hermes_cli/", "prototypes/")

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


def test_phase25_docs_record_verdict_boundaries_and_no_production_enablement() -> None:
    for path in (PLAN_DOC, DEV_LOG, RUNBOOK):
        text = path.read_text()
        assert "ready_for_stub_activity_boundary_contract_validation" in text
        assert "No Temporal SDK" in text
        assert "No `Client`, `Worker`, `WorkflowEnvironment`" in text
        assert "No Gateway restart requirement" in text
        assert "No real agent or tool execution" in text
        assert "No real delivery ACK updates" in text
        assert "orchestrate_flowweaver_stub_activities" in text
        assert "build_flowweaver_stub_activity_orchestration_validation_report" in text
        assert "tests/gateway/test_flowweaver_stub_activity_boundary_contract.py" in text
