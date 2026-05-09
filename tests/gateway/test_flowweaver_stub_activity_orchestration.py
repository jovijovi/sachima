"""RED gate tests for FlowWeaver Phase 23 stub Activity orchestration."""

from __future__ import annotations

import ast
import copy
import inspect
import subprocess
from pathlib import Path
from typing import Any

import pytest

from gateway.flowweaver_delivery_agent_execution_contract import (
    FLOWWEAVER_DELIVERY_AGENT_EXECUTION_CONTRACT_TYPE,
    FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION,
    build_flowweaver_execution_request,
    describe_flowweaver_delivery_agent_execution_contract,
)
from gateway.flowweaver_stub_activity_orchestration import (
    FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_CONTRACT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_RESULT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT,
    FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VERSION,
    describe_flowweaver_stub_activity_orchestration_contract,
    orchestrate_flowweaver_stub_activities,
    validate_flowweaver_stub_activity_orchestration_result,
)

ROOT = Path(__file__).resolve().parents[2]
MODULE_SOURCE = ROOT / "gateway" / "flowweaver_stub_activity_orchestration.py"
PLAN_DOC = ROOT / "docs" / "plans" / "2026-05-09-flowweaver-phase23-stub-activity-orchestration.md"
DEV_LOG = ROOT / "docs" / "dev_log" / "2026-05-09-flowweaver-phase23-stub-activity-orchestration.md"
RUNBOOK = ROOT / "docs" / "runbooks" / "flowweaver-stub-activity-orchestration.md"

EXPECTED_CONTRACT_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "scope",
    "consumes_contract",
    "entrypoints",
    "activity_sequence",
    "result_fields",
    "checks",
    "separate_approvals",
    "forbidden_side_effects",
    "side_effects",
]
EXPECTED_RESULT_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "operation",
    "activity_sequence",
    "execution_request",
    "execution_result",
    "progress_snapshot",
    "delivery_ack_updates",
    "checks",
    "forbidden_side_effects",
    "side_effects",
]
EXPECTED_ACTIVITY_SEQUENCE = [
    "validate_claim_check_ref",
    "execute_agent_turn",
    "deliver_artifact",
]
EXPECTED_FORBIDDEN_SIDE_EFFECTS = [
    "temporal_client",
    "worker_lifecycle",
    "gateway_hook_change",
    "config_write",
    "file_write",
    "subprocess",
    "socket",
    "send",
    "edit",
    "render",
    "callback_control",
    "agent_execution",
    "tool_execution",
    "temporal_activity_execution",
]
SEPARATE_APPROVALS = [
    "live_config_writes",
    "gateway_restart",
    "production_enablement",
    "real_send_edit_render_callback_control",
    "real_agent_tool_execution",
]
PRIVATE_CHAT_ID = "oc_" + "phase23_private_chat"
PRIVATE_USER_ID = "ou_" + "phase23_private_user"
PRIVATE_MESSAGE_ID = "om_" + "phase23_private_message"
RAW_PROMPT_VALUE = "raw prompt phase23 private value"
RAW_TOOL_VALUE = "raw " + "tool output phase23 private value"
CARD_JSON_VALUE = '{"type":"card_json","body":"phase23"}'
MEDIA_PATH_VALUE = "/tmp/phase23-private.png"
CALLBACK_VALUE = "callback payload phase23 private value"
RAW_EXCEPTION_VALUE = "RuntimeError: raw phase23 exception value"
SENSITIVE_SENTINEL = "unsafe-" + "token" + "-phase23"
BEARER_VALUE = "Bearer " + "phase23-private"
OPENAI_KEY_VALUE = "sk-" + "phase23-private"


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
        "ref": f"claim_ref_phase23_{index}",
        "kind": "agent_input",
        "count": 1,
        "size": 128 + index,
        "checksum_hint": "sha256:" + ("a" * 64),
    }


def execution_request(**overrides: object) -> dict[str, object]:
    request: dict[str, object] = {
        "type": "FlowWeaverExecutionRequest",
        "version": FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION,
        "transaction_id": "runtime_tx_phase23_1",
        "workflow_id": "runtime_tx_phase23_1",
        "intent_id": "runtime_intent_0",
        "execution_mode": "stub_activity_orchestration",
        "input_refs": [claim_ref()],
        "delivery_refs": ["runtime_delivery_0"],
        "approval_gates": list(SEPARATE_APPROVALS),
        "side_effects": [],
    }
    request.update(overrides)
    return request


def validated_request(**overrides: object) -> dict[str, object]:
    return build_flowweaver_execution_request(execution_request(**overrides))


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


def test_phase23_exposes_pure_synchronous_keyword_only_entrypoints() -> None:
    assert not inspect.iscoroutinefunction(orchestrate_flowweaver_stub_activities)
    signature = inspect.signature(orchestrate_flowweaver_stub_activities)
    assert list(signature.parameters) == ["execution_request", "contract_descriptor"]
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())
    assert signature.return_annotation == "dict[str, object]"

    for helper in (
        describe_flowweaver_stub_activity_orchestration_contract,
        validate_flowweaver_stub_activity_orchestration_result,
    ):
        assert not inspect.iscoroutinefunction(helper)


def test_phase23_contract_descriptor_freezes_stub_orchestration_scope() -> None:
    contract = describe_flowweaver_stub_activity_orchestration_contract()

    assert list(contract) == EXPECTED_CONTRACT_FIELDS
    assert contract["type"] == FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_CONTRACT_TYPE
    assert contract["version"] == FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VERSION
    assert contract["phase"] == "phase23"
    assert contract["verdict"] == FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT
    assert contract["verdict"] == "ready_for_stub_activity_orchestration_validation"
    assert contract["scope"] == "stub_activity_orchestration"
    assert contract["consumes_contract"] == FLOWWEAVER_DELIVERY_AGENT_EXECUTION_CONTRACT_TYPE
    assert contract["entrypoints"] == [
        "describe_flowweaver_stub_activity_orchestration_contract",
        "validate_flowweaver_stub_activity_orchestration_result",
        "orchestrate_flowweaver_stub_activities",
    ]
    assert contract["activity_sequence"] == EXPECTED_ACTIVITY_SEQUENCE
    assert contract["result_fields"] == EXPECTED_RESULT_FIELDS
    assert contract["checks"] == [
        "phase22_contract_descriptor_valid",
        "execution_request_valid",
        "activity_sequence_stubbed",
        "delivery_ack_updates_absent",
        "side_effects_absent",
    ]
    assert contract["separate_approvals"] == SEPARATE_APPROVALS
    assert contract["forbidden_side_effects"] == EXPECTED_FORBIDDEN_SIDE_EFFECTS
    assert contract["side_effects"] == []


def test_phase23_happy_path_returns_p22_built_safe_result_without_real_ack_or_execution() -> None:
    request = validated_request()

    result = orchestrate_flowweaver_stub_activities(
        execution_request=copy.deepcopy(request),
        contract_descriptor=describe_flowweaver_delivery_agent_execution_contract(),
    )

    assert list(result) == EXPECTED_RESULT_FIELDS
    assert result["type"] == FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_RESULT_TYPE
    assert result["version"] == FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_VERSION
    assert result["phase"] == "phase23"
    assert result["verdict"] == FLOWWEAVER_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT
    assert result["operation"] == "orchestrate_flowweaver_stub_activities"
    assert [activity["name"] for activity in result["activity_sequence"]] == EXPECTED_ACTIVITY_SEQUENCE
    assert result["activity_sequence"] == [
        {
            "name": "validate_claim_check_ref",
            "status": "stubbed",
            "input_refs": ["claim_ref_phase23_0"],
            "side_effects": [],
        },
        {
            "name": "execute_agent_turn",
            "status": "stubbed",
            "intent_id": "runtime_intent_0",
            "side_effects": [],
        },
        {
            "name": "deliver_artifact",
            "status": "planned",
            "delivery_refs": ["runtime_delivery_0"],
            "side_effects": [],
        },
    ]
    assert result["execution_request"] == request
    assert result["execution_result"] == {
        "type": "FlowWeaverExecutionResult",
        "version": FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION,
        "transaction_id": "runtime_tx_phase23_1",
        "workflow_id": "runtime_tx_phase23_1",
        "intent_id": "runtime_intent_0",
        "status": "accepted",
        "artifact_refs": ["runtime_artifact_0"],
        "delivery_refs": ["runtime_delivery_0"],
        "error_code": None,
        "side_effects": [],
    }
    assert result["progress_snapshot"] == {
        "type": "FlowWeaverProgressSnapshot",
        "version": FLOWWEAVER_DELIVERY_AGENT_EXECUTION_VERSION,
        "transaction_id": "runtime_tx_phase23_1",
        "workflow_id": "runtime_tx_phase23_1",
        "status": "running",
        "intent_statuses": {"runtime_intent_0": "running"},
        "artifact_refs": ["runtime_artifact_0"],
        "delivery_statuses": {"runtime_delivery_0": "planned"},
        "counts": {"intents": 1, "artifacts": 1, "deliveries": 1},
        "side_effects": [],
    }
    assert result["delivery_ack_updates"] == []
    assert result["checks"] == {
        "phase22_contract_descriptor_valid": True,
        "execution_request_valid": True,
        "activity_sequence_stubbed": True,
        "delivery_ack_updates_absent": True,
        "side_effects_absent": True,
    }
    assert result["forbidden_side_effects"] == EXPECTED_FORBIDDEN_SIDE_EFFECTS
    assert result["side_effects"] == []
    assert_no_raw_values(result)

    validated = validate_flowweaver_stub_activity_orchestration_result(copy.deepcopy(result))
    assert validated == result
    assert validated is not result


@pytest.mark.parametrize("mode", ["missing", "extra", "reordered", "bogus"])
def test_phase23_validator_rejects_result_field_mutations(mode: str) -> None:
    result = orchestrate_flowweaver_stub_activities(
        execution_request=validated_request(),
        contract_descriptor=describe_flowweaver_delivery_agent_execution_contract(),
    )
    mutated = rebuilt_with_fields(result, mutate_list(EXPECTED_RESULT_FIELDS, mode))

    with pytest.raises(ValueError, match="invalid_stub_activity_orchestration_result"):
        validate_flowweaver_stub_activity_orchestration_result(mutated)


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("activity_sequence",), SneakyList()),
        (("execution_request",), SneakyDict()),
        (("execution_result", "status"), SneakyStr("accepted")),
        (("progress_snapshot", "counts", "intents"), True),
        (("delivery_ack_updates",), [{"delivery_id": "runtime_delivery_0"}]),
        (("checks", "side_effects_absent"), 1),
        (("side_effects",), ["file_write"]),
    ],
)
def test_phase23_validator_rejects_hostile_or_nonexact_values(path: tuple[str, ...], replacement: object) -> None:
    result = orchestrate_flowweaver_stub_activities(
        execution_request=validated_request(),
        contract_descriptor=describe_flowweaver_delivery_agent_execution_contract(),
    )
    mutated: dict[str, Any] = copy.deepcopy(result)
    current: dict[str, Any] = mutated
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = replacement

    with pytest.raises(ValueError, match="invalid_stub_activity_orchestration_result"):
        validate_flowweaver_stub_activity_orchestration_result(mutated)


@pytest.mark.parametrize(
    "request_overrides",
    [
        {"intent_id": "runtime_intent_1"},
        {"delivery_refs": ["runtime_delivery_0", "runtime_delivery_1"]},
        {"input_refs": [claim_ref(0), claim_ref(1)]},
        {"workflow_id": "runtime_tx_phase23_other"},
        {"side_effects": ["agent_execution"]},
    ],
)
def test_phase23_orchestration_rejects_noncanonical_or_unsupported_request_shapes(request_overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="invalid_(execution_request|stub_activity_orchestration_request)"):
        orchestrate_flowweaver_stub_activities(
            execution_request=execution_request(**request_overrides),
            contract_descriptor=describe_flowweaver_delivery_agent_execution_contract(),
        )


def test_phase23_orchestration_rejects_invalid_phase22_descriptor_without_fallback() -> None:
    descriptor = describe_flowweaver_delivery_agent_execution_contract()
    descriptor["verdict"] = "production_enabled"

    with pytest.raises(ValueError, match="invalid_contract"):
        orchestrate_flowweaver_stub_activities(
            execution_request=validated_request(),
            contract_descriptor=descriptor,
        )


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
def test_phase23_rejects_raw_material_without_echoing_values(unsafe_value: str) -> None:
    request = execution_request(input_refs=[{**claim_ref(), "kind": unsafe_value}])

    with pytest.raises(ValueError) as exc_info:
        orchestrate_flowweaver_stub_activities(
            execution_request=request,
            contract_descriptor=describe_flowweaver_delivery_agent_execution_contract(),
        )

    error_text = str(exc_info.value).lower()
    assert "phase23_private" not in error_text
    assert "raw prompt" not in error_text
    assert "tool output" not in error_text
    assert "card_json" not in error_text
    assert "/tmp/" not in error_text
    assert "callback payload" not in error_text
    assert "runtimeerror" not in error_text
    assert "unsafe-token" not in error_text
    assert "bearer" not in error_text
    assert "sk-" not in error_text


def test_phase23_rejects_p22_valid_noncanonical_claim_kind_without_echoing_value() -> None:
    request = execution_request(input_refs=[{**claim_ref(), "kind": "message text"}])

    with pytest.raises(ValueError) as exc_info:
        orchestrate_flowweaver_stub_activities(
            execution_request=request,
            contract_descriptor=describe_flowweaver_delivery_agent_execution_contract(),
        )

    error_text = str(exc_info.value).lower()
    assert "message text" not in error_text


def test_phase23_source_has_no_runtime_lifecycle_or_execution_escape_hatches() -> None:
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
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                assert func.id not in forbidden_call_names
                assert func.id not in forbidden_names
            if isinstance(func, ast.Attribute):
                assert func.attr not in forbidden_call_names
        if isinstance(node, ast.Name):
            assert node.id not in forbidden_names


def test_phase23_changed_file_guard_allows_only_stub_orchestration_files() -> None:
    changed = _changed_files()
    allowed = {
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


def test_phase23_docs_record_boundaries_and_verification() -> None:
    for path in (PLAN_DOC, DEV_LOG, RUNBOOK):
        text = path.read_text()
        assert "Phase 23" in text or "phase23" in text
        assert "ready_for_stub_activity_orchestration_validation" in text
        assert "validate_claim_check_ref" in text
        assert "execute_agent_turn" in text
        assert "deliver_artifact" in text
        assert "No Temporal client" in text
        assert "No Worker" in text
        assert "No real agent" in text
        assert "No real delivery ACK" in text
        assert "No Gateway hook" in text
        assert "delivery_ack_updates" in text
        assert "scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_orchestration.py -q" in text
