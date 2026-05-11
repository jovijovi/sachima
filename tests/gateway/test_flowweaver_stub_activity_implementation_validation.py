"""RED gate tests for FlowWeaver Phase 28 stub Activity implementation validation."""

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
    build_flowweaver_stub_activity_boundary_contract_report,
    describe_flowweaver_stub_activity_boundary_contract,
)
from gateway.flowweaver_stub_activity_boundary_contract_validation import (
    build_flowweaver_stub_activity_boundary_contract_validation_report,
    describe_flowweaver_stub_activity_boundary_contract_validation_contract,
)
from gateway.flowweaver_stub_activity_implementation_design import (
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_DESIGN_CONTRACT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_DESIGN_REPORT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_DESIGN_SUCCESS_VERDICT,
    build_flowweaver_stub_activity_implementation_design_report,
    describe_flowweaver_stub_activity_implementation_design_contract,
)
from gateway.flowweaver_stub_activity_implementation_validation import (
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_CONTRACT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_REPORT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_SUCCESS_VERDICT,
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_VERSION,
    build_flowweaver_stub_activity_implementation_validation_report,
    describe_flowweaver_stub_activity_implementation_validation_contract,
    validate_flowweaver_stub_activity_implementation_validation_report,
)
from gateway.flowweaver_stub_activity_orchestration import (
    describe_flowweaver_stub_activity_orchestration_contract,
    orchestrate_flowweaver_stub_activities,
)
from gateway.flowweaver_stub_activity_orchestration_validation import (
    build_flowweaver_stub_activity_orchestration_validation_report,
    describe_flowweaver_stub_activity_orchestration_validation_contract,
)

ROOT = Path(__file__).resolve().parents[2]
MODULE_SOURCE = ROOT / "gateway" / "flowweaver_stub_activity_implementation_validation.py"
PLAN_DOC = ROOT / "docs" / "plans" / "2026-05-09-flowweaver-phase28-stub-activity-implementation-validation.md"
DEV_LOG = ROOT / "docs" / "dev_log" / "2026-05-09-flowweaver-phase28-stub-activity-implementation-validation.md"
RUNBOOK = ROOT / "docs" / "runbooks" / "flowweaver-stub-activity-implementation-validation.md"

EXPECTED_CONTRACT_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "scope",
    "consumes_contract",
    "consumes_report",
    "entrypoints",
    "report_fields",
    "validation_summary",
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
    "phase27_verdict",
    "activity_design_unit_names",
    "validation_summary",
    "checks",
    "error_code",
    "side_effects",
]
EXPECTED_ACTIVITY_NAMES = ["validate_claim_check_ref", "execute_agent_turn", "deliver_artifact"]
EXPECTED_VALIDATION_SUMMARY = {
    "activity_design_unit_count": 3,
    "implementation_mode": "design_only_no_callable_activities",
    "verification_mode": "metadata_static_validation_only",
    "payload_policy_mode": "claim_check_refs_only",
    "runtime_side_effects": "absent",
}
EXPECTED_CHECKS = [
    "phase27_contract_valid",
    "phase27_report_valid",
    "activity_design_units_valid",
    "implementation_policy_design_only",
    "verification_policy_static_only",
    "separate_approvals_preserved",
    "side_effects_absent",
    "raw_material_absent",
]
EXPECTED_SEPARATE_APPROVALS = [
    "stub_activity_implementation",
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
    "callable_activity_definition",
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
    "implementation_design_builder_invocation",
    "boundary_contract_validation_builder_invocation",
    "boundary_contract_builder_invocation",
    "orchestration_validation_builder_invocation",
    "orchestrator_invocation",
]
PRIVATE_CHAT_ID = "oc_" + "phase28_private_chat"
PRIVATE_USER_ID = "ou_" + "phase28_private_user"
PRIVATE_MESSAGE_ID = "om_" + "phase28_private_message"
RAW_PROMPT_VALUE = "raw prompt phase28 private value"
RAW_TOOL_VALUE = "raw " + "tool output phase28 private value"
CARD_JSON_VALUE = '{"type":"card_json","body":"phase28"}'
MEDIA_PATH_VALUE = "/tmp/phase28-private.png"
CALLBACK_VALUE = "callback payload phase28 private value"
RAW_EXCEPTION_VALUE = "RuntimeError: raw phase28 exception value"
SENSITIVE_SENTINEL = "unsafe-" + "material" + "-phase28"
BEARER_VALUE = "Bearer " + "phase28-private"
OPENAI_KEY_VALUE = "sk-" + "phase28-private"


class SneakyDict(dict[str, object]):
    def __eq__(self, other: object) -> bool:  # pragma: no cover - assertion trap
        return True


class SneakyStr(str):
    def __eq__(self, other: object) -> bool:  # pragma: no cover - assertion trap
        return True


class SneakyKeyStr(str):
    def __eq__(self, other: object) -> bool:  # pragma: no cover - assertion trap
        return True

    def __hash__(self) -> int:  # pragma: no cover - dict-key attack fixture
        return str.__hash__(self)


class ExplodingKeyStr(str):
    def __eq__(self, other: object) -> bool:  # pragma: no cover - assertion trap
        raise RuntimeError("key equality executed")

    def __hash__(self) -> int:  # pragma: no cover - dict-key attack fixture
        return str.__hash__(self)


class SneakyList(list[object]):
    def __eq__(self, other: object) -> bool:  # pragma: no cover - assertion trap
        return True


def claim_ref() -> dict[str, object]:
    return {
        "ref": "claim_ref_phase28_0",
        "kind": "agent_input",
        "count": 1,
        "size": 128,
        "checksum_hint": "sha256:" + ("a" * 64),
    }


def execution_request() -> dict[str, object]:
    return {
        "type": "FlowWeaverExecutionRequest",
        "version": FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION,
        "transaction_id": "runtime_tx_phase28_1",
        "workflow_id": "runtime_tx_phase28_1",
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


def phase25_report() -> dict[str, object]:
    return build_flowweaver_stub_activity_boundary_contract_report(
        validation_contract_descriptor=describe_flowweaver_stub_activity_orchestration_validation_contract(),
        validation_report=phase24_report(),
    )


def phase26_report() -> dict[str, object]:
    return build_flowweaver_stub_activity_boundary_contract_validation_report(
        boundary_contract_descriptor=describe_flowweaver_stub_activity_boundary_contract(),
        boundary_contract_report=phase25_report(),
    )


def phase27_report() -> dict[str, object]:
    return build_flowweaver_stub_activity_implementation_design_report(
        boundary_contract_validation_descriptor=describe_flowweaver_stub_activity_boundary_contract_validation_contract(),
        boundary_contract_validation_report=phase26_report(),
    )


def phase27_error_report() -> dict[str, object]:
    return build_flowweaver_stub_activity_implementation_design_report(
        boundary_contract_validation_descriptor={"bad": RAW_PROMPT_VALUE},
        boundary_contract_validation_report=phase26_report(),
    )


def expected_error_report(error_code: str) -> dict[str, object]:
    return {
        "type": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_VERSION,
        "phase": "phase28",
        "ok": False,
        "operation": "validate_flowweaver_stub_activity_implementation_design",
        "error_code": error_code,
        "side_effects": [],
    }


def expected_success_report() -> dict[str, object]:
    return {
        "type": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_VERSION,
        "phase": "phase28",
        "ok": True,
        "verdict": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_SUCCESS_VERDICT,
        "operation": "validate_flowweaver_stub_activity_implementation_design",
        "phase27_verdict": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_DESIGN_SUCCESS_VERDICT,
        "activity_design_unit_names": EXPECTED_ACTIVITY_NAMES,
        "validation_summary": EXPECTED_VALIDATION_SUMMARY,
        "checks": {key: True for key in EXPECTED_CHECKS},
        "error_code": None,
        "side_effects": [],
    }


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
        "runtime_tx_phase28_1",
        "claim_ref_phase28_0",
        FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_DESIGN_REPORT_TYPE,
    ):
        assert marker not in rendered


def mutate_list(values: list[Any], mode: str) -> list[Any]:
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


def test_phase28_exposes_pure_synchronous_keyword_only_entrypoints() -> None:
    signature = inspect.signature(build_flowweaver_stub_activity_implementation_validation_report)
    assert list(signature.parameters) == ["implementation_design_contract_descriptor", "implementation_design_report"]
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())
    assert signature.return_annotation == "dict[str, object]"
    assert not inspect.iscoroutinefunction(build_flowweaver_stub_activity_implementation_validation_report)

    for helper in (
        describe_flowweaver_stub_activity_implementation_validation_contract,
        validate_flowweaver_stub_activity_implementation_validation_report,
    ):
        assert not inspect.iscoroutinefunction(helper)


def test_phase28_contract_descriptor_freezes_validation_scope_and_success_verdict() -> None:
    contract = describe_flowweaver_stub_activity_implementation_validation_contract()

    assert list(contract) == EXPECTED_CONTRACT_FIELDS
    assert contract["type"] == FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_CONTRACT_TYPE
    assert contract["version"] == FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_VERSION
    assert contract["phase"] == "phase28"
    assert contract["verdict"] == FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_SUCCESS_VERDICT
    assert contract["verdict"] == "ready_for_separately_approved_stub_activity_implementation"
    assert contract["scope"] == "stub_activity_implementation_validation"
    assert contract["consumes_contract"] == FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_DESIGN_CONTRACT_TYPE
    assert contract["consumes_report"] == FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_DESIGN_REPORT_TYPE
    assert contract["entrypoints"] == [
        "describe_flowweaver_stub_activity_implementation_validation_contract",
        "validate_flowweaver_stub_activity_implementation_validation_report",
        "build_flowweaver_stub_activity_implementation_validation_report",
    ]
    assert contract["report_fields"] == EXPECTED_REPORT_FIELDS
    assert contract["validation_summary"] == EXPECTED_VALIDATION_SUMMARY
    assert contract["checks"] == EXPECTED_CHECKS
    assert contract["separate_approvals"] == EXPECTED_SEPARATE_APPROVALS
    assert contract["forbidden_side_effects"] == EXPECTED_FORBIDDEN_SIDE_EFFECTS
    assert contract["side_effects"] == []


def test_phase28_happy_path_builds_safe_validation_report_from_phase27_design_report() -> None:
    report = build_flowweaver_stub_activity_implementation_validation_report(
        implementation_design_contract_descriptor=describe_flowweaver_stub_activity_implementation_design_contract(),
        implementation_design_report=phase27_report(),
    )

    assert report == expected_success_report()
    assert_no_raw_values(report)


def test_phase28_validator_returns_sanitized_deep_copy() -> None:
    report = expected_success_report()
    safe = validate_flowweaver_stub_activity_implementation_validation_report(report)
    safe["activity_design_unit_names"].append("mutated")  # type: ignore[union-attr]
    safe["validation_summary"]["implementation_mode"] = "mutated"  # type: ignore[index]
    safe["checks"]["phase27_contract_valid"] = False  # type: ignore[index]

    assert report == expected_success_report()


def test_phase28_rejects_invalid_phase27_contract_with_sanitized_error_report() -> None:
    result = build_flowweaver_stub_activity_implementation_validation_report(
        implementation_design_contract_descriptor={"type": RAW_PROMPT_VALUE},
        implementation_design_report=phase27_report(),
    )

    assert result == expected_error_report("invalid_phase27_stub_activity_implementation_design_contract")
    assert_no_raw_values(result)


def test_phase28_rejects_invalid_phase27_report_with_sanitized_error_report() -> None:
    report = copy.deepcopy(phase27_report())
    report["activity_design_units"][0]["name"] = RAW_PROMPT_VALUE  # type: ignore[index]

    result = build_flowweaver_stub_activity_implementation_validation_report(
        implementation_design_contract_descriptor=describe_flowweaver_stub_activity_implementation_design_contract(),
        implementation_design_report=report,
    )

    assert result == expected_error_report("invalid_phase27_stub_activity_implementation_design_report")
    assert_no_raw_values(result)


def test_phase28_rejects_phase27_error_report_with_sanitized_error_report() -> None:
    result = build_flowweaver_stub_activity_implementation_validation_report(
        implementation_design_contract_descriptor=describe_flowweaver_stub_activity_implementation_design_contract(),
        implementation_design_report=phase27_error_report(),
    )

    assert result == expected_error_report("invalid_phase27_stub_activity_implementation_design_report")
    assert_no_raw_values(result)


@pytest.mark.parametrize("mode", ["missing", "extra", "reordered", "bogus"])
def test_phase28_validator_rejects_report_field_mutations(mode: str) -> None:
    report = rebuilt_with_fields(expected_success_report(), mutate_list(EXPECTED_REPORT_FIELDS, mode))

    with pytest.raises(ValueError, match="invalid_stub_activity_implementation_validation_report"):
        validate_flowweaver_stub_activity_implementation_validation_report(report)


@pytest.mark.parametrize("mode", ["missing", "extra", "reordered", "duplicated", "bogus"])
def test_phase28_contract_descriptor_rejects_report_field_list_mutations(mode: str) -> None:
    contract = describe_flowweaver_stub_activity_implementation_validation_contract()
    contract["report_fields"] = mutate_list(EXPECTED_REPORT_FIELDS, mode)

    with pytest.raises(ValueError, match="invalid_stub_activity_implementation_validation_contract"):
        validate_flowweaver_stub_activity_implementation_validation_contract_descriptor_for_test(contract)


@pytest.mark.parametrize("mode", ["missing", "extra", "reordered", "duplicated", "bogus"])
def test_phase28_validator_rejects_activity_name_mutations(mode: str) -> None:
    report = expected_success_report()
    report["activity_design_unit_names"] = mutate_list(EXPECTED_ACTIVITY_NAMES, mode)

    with pytest.raises(ValueError, match="invalid_stub_activity_implementation_validation_report"):
        validate_flowweaver_stub_activity_implementation_validation_report(report)


@pytest.mark.parametrize("key", EXPECTED_CHECKS)
def test_phase28_validator_rejects_check_mutations(key: str) -> None:
    report = expected_success_report()
    report["checks"][key] = 1  # type: ignore[index]

    with pytest.raises(ValueError, match="invalid_stub_activity_implementation_validation_report"):
        validate_flowweaver_stub_activity_implementation_validation_report(report)


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("type",), SneakyStr(FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_REPORT_TYPE)),
        (("ok",), 1),
        (("phase27_verdict",), SneakyStr(FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_DESIGN_SUCCESS_VERDICT)),
        (("activity_design_unit_names",), SneakyList(EXPECTED_ACTIVITY_NAMES)),
        (("activity_design_unit_names", 0), SneakyStr("validate_claim_check_ref")),
        (("validation_summary",), SneakyDict(EXPECTED_VALIDATION_SUMMARY)),
        (("checks",), SneakyDict({key: True for key in EXPECTED_CHECKS})),
        (("side_effects",), SneakyList()),
    ],
)
def test_phase28_validator_rejects_hostile_subclass_and_bool_impersonation_values(
    path: tuple[str | int, ...], replacement: object
) -> None:
    report = expected_success_report()
    target: Any = report
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement

    with pytest.raises(ValueError, match="invalid_stub_activity_implementation_validation_report"):
        validate_flowweaver_stub_activity_implementation_validation_report(report)


def test_phase28_validator_rejects_hostile_top_level_and_nested_keys() -> None:
    report = {SneakyKeyStr(key): value for key, value in expected_success_report().items()}
    with pytest.raises(ValueError, match="invalid_stub_activity_implementation_validation_report"):
        validate_flowweaver_stub_activity_implementation_validation_report(report)

    report = {ExplodingKeyStr(key): value for key, value in expected_error_report("invalid_phase27_stub_activity_implementation_design_contract").items()}
    with pytest.raises(ValueError, match="invalid_stub_activity_implementation_validation_report"):
        validate_flowweaver_stub_activity_implementation_validation_report(report)

    report = expected_success_report()
    report["validation_summary"] = {SneakyKeyStr(key): value for key, value in EXPECTED_VALIDATION_SUMMARY.items()}
    with pytest.raises(ValueError, match="invalid_stub_activity_implementation_validation_report"):
        validate_flowweaver_stub_activity_implementation_validation_report(report)

    report = expected_success_report()
    report["checks"] = {SneakyKeyStr(key): True for key in EXPECTED_CHECKS}
    with pytest.raises(ValueError, match="invalid_stub_activity_implementation_validation_report"):
        validate_flowweaver_stub_activity_implementation_validation_report(report)


def test_phase28_builder_rejects_hostile_phase27_descriptor_and_report_keys() -> None:
    sneaky_descriptor = {
        SneakyKeyStr(key): value for key, value in describe_flowweaver_stub_activity_implementation_design_contract().items()
    }
    result = build_flowweaver_stub_activity_implementation_validation_report(
        implementation_design_contract_descriptor=sneaky_descriptor,
        implementation_design_report=phase27_report(),
    )
    assert result == expected_error_report("invalid_phase27_stub_activity_implementation_design_contract")

    sneaky_report = {SneakyKeyStr(key): value for key, value in phase27_report().items()}
    result = build_flowweaver_stub_activity_implementation_validation_report(
        implementation_design_contract_descriptor=describe_flowweaver_stub_activity_implementation_design_contract(),
        implementation_design_report=sneaky_report,
    )
    assert result == expected_error_report("invalid_phase27_stub_activity_implementation_design_report")


def test_phase28_builder_rejects_internally_inconsistent_phase27_activity_names() -> None:
    report = phase27_report()
    report["activity_design_units"][2]["name"] = "unexpected_activity"  # type: ignore[index]

    result = build_flowweaver_stub_activity_implementation_validation_report(
        implementation_design_contract_descriptor=describe_flowweaver_stub_activity_implementation_design_contract(),
        implementation_design_report=report,
    )

    assert result == expected_error_report("invalid_phase27_stub_activity_implementation_design_report")
    assert_no_raw_values(result)


def test_phase28_error_report_validator_accepts_only_sanitized_error_codes() -> None:
    safe = validate_flowweaver_stub_activity_implementation_validation_report(
        expected_error_report("invalid_phase27_stub_activity_implementation_design_contract")
    )
    assert safe == expected_error_report("invalid_phase27_stub_activity_implementation_design_contract")

    bad = expected_error_report(RAW_PROMPT_VALUE)
    with pytest.raises(ValueError, match="invalid_stub_activity_implementation_validation_report"):
        validate_flowweaver_stub_activity_implementation_validation_report(bad)


def test_phase28_source_has_no_runtime_builder_or_callable_activity_escape_hatches() -> None:
    source = MODULE_SOURCE.read_text()
    tree = ast.parse(source)

    forbidden_import_fragments = ("temporalio", "gateway.platforms", "prototypes")
    forbidden_modules = {
        "gateway.flowweaver_stub_activity_orchestration",
        "gateway.flowweaver_stub_activity_orchestration_validation",
        "gateway.flowweaver_stub_activity_boundary_contract",
        "gateway.flowweaver_stub_activity_boundary_contract_validation",
    }
    forbidden_function_names = {"validate_claim_check_ref", "execute_agent_turn", "deliver_artifact"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(fragment in alias.name for fragment in forbidden_import_fragments)
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not any(fragment in module for fragment in forbidden_import_fragments)
            assert module not in forbidden_modules
            imported = {alias.name for alias in node.names}
            assert "build_flowweaver_stub_activity_implementation_design_report" not in imported
            assert "build_flowweaver_stub_activity_boundary_contract_validation_report" not in imported
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in forbidden_function_names
        if isinstance(node, ast.Call):
            func = node.func
            called = ""
            if isinstance(func, ast.Name):
                called = func.id
            elif isinstance(func, ast.Attribute):
                called = func.attr
            assert called not in {
                "build_flowweaver_stub_activity_implementation_design_report",
                "build_flowweaver_stub_activity_boundary_contract_validation_report",
                "build_flowweaver_stub_activity_boundary_contract_report",
                "build_flowweaver_stub_activity_orchestration_validation_report",
                "orchestrate_flowweaver_stub_activities",
                "execute_activity",
                "send",
                "edit",
                "render",
                "print",
                "open",
            }
        if isinstance(node, ast.Name):
            assert node.id not in {"Client", "Worker", "WorkflowEnvironment"}


def test_phase28_changed_file_guard_allows_only_implementation_validation_files() -> None:
    changed = _changed_files()
    allowed = {
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
        "docs/plans/2026-05-11-flowweaver-pe1-controlled-sachima-shadow-observation.md",
        "docs/runbooks/flowweaver-pe1-controlled-sachima-shadow-observation.md",
        "docs/dev_log/2026-05-11-flowweaver-pe1-controlled-sachima-shadow-observation.md",
        "docs/plans/2026-05-11-flowweaver-pe1d-pe2-readiness-decision-packet.md",
        "docs/runbooks/flowweaver-pe1d-pe2-readiness-decision.md",
        "docs/dev_log/2026-05-11-flowweaver-pe1d-pe2-readiness-decision-packet.md",
        "AGENTS.md",
        "GOAL.md",
        "docs/sachima-final-goal-gap-analysis.md",
        "docs/dev_log/2026-05-11-sachima-project-goal-gap-analysis.md",
        "gateway/flowweaver_production_shadow_observation.py",
        "tests/gateway/test_flowweaver_pe1_controlled_sachima_shadow_observation.py",
        "tests/integration/test_flowweaver_phase21_production_shadow_observation.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation_design.py",
        "tests/gateway/test_flowweaver_stub_activity_boundary_contract_validation.py",
        "tests/gateway/test_flowweaver_stub_activity_boundary_contract.py",
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


def test_phase28_docs_record_verdict_boundaries_and_verification() -> None:
    for path in (PLAN_DOC, DEV_LOG, RUNBOOK):
        text = path.read_text()
        assert "ready_for_separately_approved_stub_activity_implementation" in text
        assert "No Temporal SDK" in text
        assert "No `Client`, `Worker`, `WorkflowEnvironment`" in text
        assert "No Gateway restart requirement" in text
        assert "No real agent or tool execution" in text
        assert "No real delivery ACK updates" in text
        assert "No callable implementation" in text
        assert "build_flowweaver_stub_activity_implementation_design_report" in text
        assert "orchestrate_flowweaver_stub_activities" in text
        assert "tests/gateway/test_flowweaver_stub_activity_implementation_validation.py" in text


def validate_flowweaver_stub_activity_implementation_validation_contract_descriptor_for_test(
    value: object,
) -> dict[str, object]:
    """Local test copy of the expected P28 descriptor strictness."""

    expected = describe_flowweaver_stub_activity_implementation_validation_contract()
    if type(value) is not dict or not _keys_match_exactly(value, EXPECTED_CONTRACT_FIELDS):
        raise ValueError("invalid_stub_activity_implementation_validation_contract")
    if value != expected:
        raise ValueError("invalid_stub_activity_implementation_validation_contract")
    return copy.deepcopy(value)


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _changed_files() -> set[str]:
    base = _git("merge-base", "HEAD", "origin/feature/sachima-channel")
    committed = set(_git("diff", "--name-only", f"{base}...HEAD").splitlines())
    worktree = set(_git("diff", "--name-only").splitlines())
    cached = set(_git("diff", "--cached", "--name-only").splitlines())
    untracked = set(_git("ls-files", "--others", "--exclude-standard").splitlines())
    return {name for name in committed | worktree | cached | untracked if name}


def _keys_match_exactly(value: dict[object, object], expected_keys: list[str]) -> bool:
    actual_keys = list(value.keys())
    if len(actual_keys) != len(expected_keys):
        return False
    for actual, expected in zip(actual_keys, expected_keys, strict=True):
        if type(actual) is not str or actual != expected:
            return False
    return True
