"""RED/GREEN tests for FlowWeaver Phase 31 controlled agent execution Activity."""

from __future__ import annotations

import ast
import asyncio
import copy
import inspect
import subprocess
from pathlib import Path
from typing import Any

import pytest

from gateway.flowweaver_agent_execution_activity import (
    FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_CONTRACT_TYPE,
    FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_REPORT_TYPE,
    FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_REQUEST_TYPE,
    FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_RESULT_TYPE,
    FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT,
    FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION,
    build_execute_agent_turn_activity,
    build_flowweaver_agent_execution_activity_report,
    build_flowweaver_agent_execution_request,
    describe_flowweaver_agent_execution_activity_contract,
    execute_controlled_agent_turn,
    validate_flowweaver_agent_execution_activity_report,
    validate_flowweaver_agent_execution_request,
    validate_flowweaver_agent_execution_result,
)
from gateway.flowweaver_temporal_stub_activity_orchestration import (
    FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT,
    FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_VERSION,
    validate_claim_check_ref_activity,
)

ROOT = Path(__file__).resolve().parents[2]
MODULE_SOURCE = ROOT / "gateway" / "flowweaver_agent_execution_activity.py"
PLAN_DOC = ROOT / "docs" / "plans" / "2026-05-09-flowweaver-phase31-agent-execution-activity.md"
DEV_LOG = ROOT / "docs" / "dev_log" / "2026-05-09-flowweaver-phase31-agent-execution-activity.md"
RUNBOOK = ROOT / "docs" / "runbooks" / "flowweaver-agent-execution-activity.md"

EXPECTED_CONTRACT_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "scope",
    "consumes_verdict",
    "entrypoints",
    "request_fields",
    "result_fields",
    "report_fields",
    "executor_boundary",
    "runtime_policy",
    "retry_policy",
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
    "claim_check_ref",
    "claim_policy",
    "artifact_ref",
    "execution_mode",
    "executor_policy",
    "execution_digest",
    "side_effects",
]
EXPECTED_RESULT_FIELDS = [
    "type",
    "version",
    "phase",
    "activity",
    "status",
    "artifact_ref",
    "artifact_kind",
    "counts",
    "output_digest",
    "error_code",
    "retry_class",
    "side_effects",
]
EXPECTED_REPORT_FIELDS = [
    "type",
    "version",
    "phase",
    "ok",
    "verdict",
    "operation",
    "phase30_verdict",
    "controlled_executor_verified",
    "history_no_leak_checked",
    "result_no_leak_checked",
    "checks",
    "error_code",
    "side_effects",
]
EXPECTED_EXECUTOR_BOUNDARY = {
    "mode": "injected_executor_only",
    "executor_input": "safe_claim_ref_and_runtime_ids_only",
    "raw_material_access": "activity_boundary_only",
    "executor_output": "sanitized_artifact_ref_counts_digest_only",
    "global_agent_factory": "forbidden",
    "side_effects": [],
}
EXPECTED_RUNTIME_POLICY = {
    "mode": "controlled_non_production_agent_execution_activity",
    "temporal_runtime": "local_staging_only",
    "gateway_delivery_ack": "forbidden_until_phase32",
    "production_agent_execution": "forbidden",
    "executor_injection": "required",
    "raw_material_policy": "claim_check_refs_in_history_executor_raw_local_only",
    "side_effects": [],
}
EXPECTED_RETRY_POLICY = {
    "start_to_close_timeout_seconds": 15,
    "maximum_attempts": 2,
    "non_retryable_error_types": [
        "invalid_agent_execution_request",
        "invalid_claim_ref",
        "unsafe_material",
        "executor_auth_config_failure",
        "executor_cancelled",
    ],
    "transient_error_types": ["executor_failed", "executor_timeout"],
}
EXPECTED_CHECKS = [
    "phase30_verdict_valid",
    "executor_injected_and_observable",
    "unsafe_claims_fail_before_executor",
    "executor_success_sanitized",
    "executor_failure_sanitized",
    "timeout_cancel_sanitized",
    "history_no_leak_verified",
    "delivery_surfaces_absent",
    "side_effects_absent",
]
EXPECTED_SEPARATE_APPROVALS = [
    "controlled_delivery_activity",
    "production_gateway_wiring",
    "production_agent_execution",
    "production_config_write",
    "gateway_restart",
    "platform_adapter_mutation",
    "real_send_edit_render_callback_control",
    "delivery_ack_updates",
]
EXPECTED_FORBIDDEN_SIDE_EFFECTS = [
    "global_aiagent_instance",
    "hidden_executor_factory",
    "gateway_hook_change",
    "gateway_adapter_access",
    "platform_adapter_mutation",
    "production_config_write",
    "gateway_restart",
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
    "raw_material_persistence",
]

PRIVATE_CHAT_ID = "oc_" + "phase31_private_chat"
PRIVATE_USER_ID = "ou_" + "phase31_private_user"
PRIVATE_MESSAGE_ID = "om_" + "phase31_private_message"
RAW_PROMPT_VALUE = "raw prompt phase31 private value"
RAW_TOOL_VALUE = "raw " + "tool output phase31 private value"
CARD_JSON_VALUE = '{"type":"card_json","body":"phase31"}'
MEDIA_PATH_VALUE = "/tmp/phase31-private.png"
CALLBACK_VALUE = "callback payload phase31 private value"
RAW_EXCEPTION_VALUE = "RuntimeError: raw phase31 exception value"
SENSITIVE_SENTINEL = "unsafe-" + "token" + "-phase31"
BEARER_VALUE = "Bearer " + "phase31-private"
OPENAI_KEY_VALUE = "sk-" + "phase31-private"
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


class RecordingExecutor:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def __call__(self, request: dict[str, object]) -> dict[str, object]:
        self.calls.append(copy.deepcopy(request))
        return copy.deepcopy(self.response)


class RaisingExecutor:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def __call__(self, request: dict[str, object]) -> dict[str, object]:
        self.calls.append(copy.deepcopy(request))
        raise RuntimeError(RAW_EXCEPTION_VALUE)


class CancelledExecutor:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def __call__(self, request: dict[str, object]) -> dict[str, object]:
        self.calls.append(copy.deepcopy(request))
        raise asyncio.CancelledError("raw phase31 cancellation value")


def claim_ref(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "ref": "claim_ref_phase31_0",
        "kind": "agent_input",
        "count": 1,
        "size": 128,
        "checksum_hint": "sha256:" + ("a" * 64),
    }
    value.update(overrides)
    return value


def claim_policy() -> dict[str, object]:
    return {
        "mode": "claim_check_refs_only",
        "allowed_kinds": ["agent_input"],
        "checksum_hint": "sha256_64_lower_hex",
        "side_effects": [],
    }


def execution_request(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "transaction_id": "runtime_tx_phase31_1",
        "workflow_id": "runtime_tx_phase31_1",
        "intent_id": "runtime_intent_0",
        "claim_check_ref": claim_ref(),
        "artifact_ref": "runtime_artifact_0",
    }
    kwargs.update(overrides)
    return build_flowweaver_agent_execution_request(**kwargs)  # type: ignore[arg-type]


def validated_claim(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "activity": "validate_claim_check_ref",
        "status": "validated",
        "claim_ref": "claim_ref_phase31_0",
        "error_code": None,
        "side_effects": [],
    }
    value.update(overrides)
    return value


def executor_success(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "status": "completed",
        "artifact_ref": "runtime_artifact_0",
        "raw_output": RAW_TOOL_VALUE,
        "tool_call_count": 2,
        "output_item_count": 1,
    }
    value.update(overrides)
    return value


def assert_no_raw_values(value: object) -> None:
    rendered = repr(value).lower()
    for marker in FORBIDDEN_SENTINELS:
        assert marker.lower() not in rendered
    assert "traceback" not in rendered
    assert "runtimeerror" not in rendered
    assert "temporalio.exceptions" not in rendered


@pytest.mark.asyncio
async def test_phase31_exposes_contract_and_explicit_executor_injection_boundary() -> None:
    contract = describe_flowweaver_agent_execution_activity_contract()

    assert list(contract) == EXPECTED_CONTRACT_FIELDS
    assert contract["type"] == FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_CONTRACT_TYPE
    assert contract["version"] == FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION
    assert contract["phase"] == "phase31"
    assert contract["verdict"] == FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT
    assert contract["verdict"] == "ready_for_controlled_delivery_activity_request"
    assert contract["scope"] == "controlled_agent_execution_activity"
    assert contract["consumes_verdict"] == FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT
    assert contract["request_fields"] == EXPECTED_REQUEST_FIELDS
    assert contract["result_fields"] == EXPECTED_RESULT_FIELDS
    assert contract["report_fields"] == EXPECTED_REPORT_FIELDS
    assert contract["executor_boundary"] == EXPECTED_EXECUTOR_BOUNDARY
    assert contract["runtime_policy"] == EXPECTED_RUNTIME_POLICY
    assert contract["retry_policy"] == EXPECTED_RETRY_POLICY
    assert contract["checks"] == EXPECTED_CHECKS
    assert contract["separate_approvals"] == EXPECTED_SEPARATE_APPROVALS
    assert contract["forbidden_side_effects"] == EXPECTED_FORBIDDEN_SIDE_EFFECTS
    assert contract["side_effects"] == []

    assert not inspect.iscoroutinefunction(describe_flowweaver_agent_execution_activity_contract)
    assert not inspect.iscoroutinefunction(validate_flowweaver_agent_execution_request)
    assert inspect.iscoroutinefunction(execute_controlled_agent_turn)
    built = build_execute_agent_turn_activity(executor=RecordingExecutor(executor_success()))
    assert inspect.iscoroutinefunction(built)


@pytest.mark.asyncio
async def test_phase31_success_calls_injected_executor_once_and_returns_only_sanitized_artifact_metadata() -> None:
    request = execution_request()
    executor = RecordingExecutor(executor_success())

    result = await execute_controlled_agent_turn(
        execution_request=request,
        validated_claim=validated_claim(),
        executor=executor,
    )

    assert len(executor.calls) == 1
    assert list(executor.calls[0]) == [
        "transaction_id",
        "workflow_id",
        "intent_id",
        "claim_check_ref",
        "artifact_ref",
        "execution_mode",
        "executor_policy",
        "execution_digest",
    ]
    assert executor.calls[0]["claim_check_ref"] == "claim_ref_phase31_0"
    assert executor.calls[0]["execution_mode"] == "controlled_non_production_agent_activity"
    assert_no_raw_values(executor.calls[0])

    assert list(result) == EXPECTED_RESULT_FIELDS
    assert result["type"] == FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_RESULT_TYPE
    assert result["version"] == FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_VERSION
    assert result["phase"] == "phase31"
    assert result["activity"] == "execute_agent_turn"
    assert result["status"] == "executed"
    assert result["artifact_ref"] == "runtime_artifact_0"
    assert result["artifact_kind"] == "controlled_agent_result"
    assert result["counts"] == {"executor_calls": 1, "tool_calls": 2, "output_items": 1}
    assert str(result["output_digest"]).startswith("sha256:")
    assert len(str(result["output_digest"]).removeprefix("sha256:")) == 64
    assert result["error_code"] is None
    assert result["retry_class"] == "none"
    assert result["side_effects"] == []
    assert validate_flowweaver_agent_execution_result(copy.deepcopy(result)) == result
    assert_no_raw_values(result)


@pytest.mark.asyncio
async def test_phase31_missing_or_unsafe_claim_fails_closed_before_executor_call() -> None:
    executor = RecordingExecutor(executor_success())
    unsafe_request = execution_request()
    unsafe_request["claim_check_ref"] = claim_ref(ref="claim_ref_oc_private")

    result = await execute_controlled_agent_turn(
        execution_request=unsafe_request,
        validated_claim=validated_claim(),
        executor=executor,
    )

    assert executor.calls == []
    assert result["status"] == "rejected"
    assert result["artifact_ref"] is None
    assert result["error_code"] == "invalid_agent_execution_request"
    assert result["retry_class"] == "non_retryable"
    assert result["side_effects"] == []
    assert_no_raw_values(result)

    raw_claim_result = await execute_controlled_agent_turn(
        execution_request=execution_request(),
        validated_claim=validated_claim(claim_ref=RAW_PROMPT_VALUE),
        executor=executor,
    )
    assert executor.calls == []
    assert raw_claim_result["status"] == "rejected"
    assert raw_claim_result["error_code"] == "unsafe_material"
    assert_no_raw_values(raw_claim_result)


@pytest.mark.asyncio
async def test_phase31_executor_failure_timeout_and_cancel_paths_are_stable_and_sanitized() -> None:
    failed = await execute_controlled_agent_turn(
        execution_request=execution_request(),
        validated_claim=validated_claim(),
        executor=RaisingExecutor(),
    )
    assert failed["status"] == "rejected"
    assert failed["artifact_ref"] is None
    assert failed["error_code"] == "executor_failed"
    assert failed["retry_class"] == "transient"
    assert_no_raw_values(failed)

    timed_out = await execute_controlled_agent_turn(
        execution_request=execution_request(),
        validated_claim=validated_claim(),
        executor=RecordingExecutor(executor_success(status="timed_out", output_item_count=0)),
    )
    assert timed_out["status"] == "timed_out"
    assert timed_out["artifact_ref"] is None
    assert timed_out["error_code"] == "executor_timeout"
    assert timed_out["retry_class"] == "transient"
    assert_no_raw_values(timed_out)

    cancelled_exception = await execute_controlled_agent_turn(
        execution_request=execution_request(),
        validated_claim=validated_claim(),
        executor=CancelledExecutor(),
    )
    assert cancelled_exception["status"] == "cancelled"
    assert cancelled_exception["artifact_ref"] is None
    assert cancelled_exception["error_code"] == "executor_cancelled"
    assert cancelled_exception["retry_class"] == "non_retryable"
    assert_no_raw_values(cancelled_exception)

    cancelled = await execute_controlled_agent_turn(
        execution_request=execution_request(),
        validated_claim=validated_claim(),
        executor=RecordingExecutor(executor_success(status="cancelled", output_item_count=0)),
    )
    assert cancelled["status"] == "cancelled"
    assert cancelled["artifact_ref"] is None
    assert cancelled["error_code"] == "executor_cancelled"
    assert cancelled["retry_class"] == "non_retryable"
    assert_no_raw_values(cancelled)


@pytest.mark.asyncio
async def test_phase31_activity_factory_rejects_unsafe_payload_before_executor_call() -> None:
    executor = RecordingExecutor(executor_success())
    activity_func = build_execute_agent_turn_activity(executor=executor)

    result = await activity_func({"bad": RAW_PROMPT_VALUE})

    assert executor.calls == []
    assert result["status"] == "rejected"
    assert result["error_code"] == "unsafe_material"
    assert result["side_effects"] == []
    assert_no_raw_values(result)


@pytest.mark.asyncio
async def test_phase31_report_builder_consumes_phase30_verdict_and_sanitized_result() -> None:
    result = await execute_controlled_agent_turn(
        execution_request=execution_request(),
        validated_claim=validated_claim(),
        executor=RecordingExecutor(executor_success()),
    )

    report = build_flowweaver_agent_execution_activity_report(
        temporal_stub_activity_version=FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_VERSION,
        temporal_stub_activity_verdict=FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT,
        controlled_execution_result=result,
        history_no_leak_checked=True,
    )

    assert list(report) == EXPECTED_REPORT_FIELDS
    assert report["type"] == FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_REPORT_TYPE
    assert report["verdict"] == FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_SUCCESS_VERDICT
    assert report["phase30_verdict"] == FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT
    assert report["controlled_executor_verified"] is True
    assert report["history_no_leak_checked"] is True
    assert report["result_no_leak_checked"] is True
    assert report["checks"] == {key: True for key in EXPECTED_CHECKS}
    assert report["error_code"] is None
    assert report["side_effects"] == []
    assert validate_flowweaver_agent_execution_activity_report(copy.deepcopy(report)) == report
    assert_no_raw_values(report)


def test_phase31_request_builder_accepts_only_safe_refs_and_recomputes_digest() -> None:
    request = execution_request()

    assert list(request) == EXPECTED_REQUEST_FIELDS
    assert request["type"] == FLOWWEAVER_AGENT_EXECUTION_ACTIVITY_REQUEST_TYPE
    assert request["phase"] == "phase31"
    assert request["transaction_id"] == "runtime_tx_phase31_1"
    assert request["workflow_id"] == "runtime_tx_phase31_1"
    assert request["claim_check_ref"] == claim_ref()
    assert request["claim_policy"] == claim_policy()
    assert request["artifact_ref"] == "runtime_artifact_0"
    assert request["execution_mode"] == "controlled_non_production_agent_activity"
    assert request["executor_policy"] == EXPECTED_EXECUTOR_BOUNDARY
    assert str(request["execution_digest"]).startswith("sha256:")
    assert len(str(request["execution_digest"]).removeprefix("sha256:")) == 64
    assert request["side_effects"] == []
    assert validate_flowweaver_agent_execution_request(copy.deepcopy(request)) == request
    assert_no_raw_values(request)


def test_phase31_source_forbids_global_agents_gateway_delivery_ack_and_hidden_lifecycle() -> None:
    source = MODULE_SOURCE.read_text()
    tree = ast.parse(source)

    assert "run_agent" not in source
    assert "AIAgent" not in source
    assert "model_tools" not in source
    assert "toolsets" not in source
    assert "gateway.run" not in source
    assert "gateway.platforms" not in source
    assert "Client.connect" not in source
    assert "WorkflowEnvironment" not in source
    assert "from temporalio.worker import Worker" not in source
    assert "Worker(" not in source

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
        "open",
        "write",
        "write_text",
        "Popen",
        "run",
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


def test_phase31_changed_file_guard_allows_only_agent_execution_activity_files_and_guard_maintenance() -> None:
    changed = _changed_files()
    allowed = {
        "gateway/flowweaver_agent_execution_activity.py",
        "tests/gateway/test_flowweaver_agent_execution_activity.py",
        "tests/integration/test_flowweaver_phase31_agent_execution_activity.py",
        "docs/runbooks/flowweaver-agent-execution-activity.md",
        "docs/plans/2026-05-09-flowweaver-phase31-agent-execution-activity.md",
        "docs/dev_log/2026-05-09-flowweaver-phase31-agent-execution-activity.md",
        "tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation_validation.py",
        "tests/gateway/test_flowweaver_stub_activity_orchestration.py",
        "tests/gateway/test_flowweaver_stub_activity_orchestration_validation.py",
        "tests/gateway/test_flowweaver_stub_activity_boundary_contract.py",
        "tests/gateway/test_flowweaver_stub_activity_boundary_contract_validation.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation_design.py",
        "tests/gateway/test_flowweaver_production_shadow_observation.py",
        "tests/gateway/test_flowweaver_shadow_publisher.py",
        "tests/gateway/test_flowweaver_temporal_observation_bridge.py",
        "tests/gateway/test_flowweaver_temporal_observation_validation_gate.py",
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
        "gateway/flowweaver_production_shadow_observation.py",
        "tests/gateway/test_flowweaver_pe1_controlled_sachima_shadow_observation.py",
        "tests/integration/test_flowweaver_phase21_production_shadow_observation.py",
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


@pytest.mark.asyncio
async def test_phase31_reuses_phase30_claim_validation_without_leaking_raw_values() -> None:
    claim_result = await validate_claim_check_ref_activity(
        {"claim_check_ref": claim_ref(), "policy_descriptor": claim_policy()}
    )
    result = await execute_controlled_agent_turn(
        execution_request=execution_request(),
        validated_claim=claim_result,
        executor=RecordingExecutor(executor_success()),
    )

    assert claim_result["status"] == "validated"
    assert result["status"] == "executed"
    assert_no_raw_values(claim_result)
    assert_no_raw_values(result)
