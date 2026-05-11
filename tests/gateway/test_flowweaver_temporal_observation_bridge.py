"""RED contract tests for FlowWeaver Phase 19 Temporal observation bridge."""

from __future__ import annotations

import ast
import copy
import inspect
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
PHASE5B_SRC = ROOT / "prototypes" / "flowweaver_phase5b_temporal_poc" / "src"
PHASE5C_SRC = ROOT / "prototypes" / "flowweaver_phase5c_runtime_client" / "src"
for path in (PHASE5C_SRC, PHASE5B_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from gateway.flowweaver_temporal_observation_bridge import observe_gateway_turn_for_flowweaver_temporal
from flowweaver_runtime_client.contracts import build_start_payload_from_safe_fields

MODULE_SOURCE = ROOT / "gateway" / "flowweaver_temporal_observation_bridge.py"
SUCCESS_VERDICT = "ready_for_guarded_temporal_observation_validation"
RESULT_TYPE = "flowweaver.gateway.temporal_observation_bridge_result.v0"
RESULT_VERSION = "flowweaver.temporal_observation_bridge.v0"
OBSERVATION_TYPE = "flowweaver.gateway.temporal_observation.v0"
OBSERVATION_VERSION = "flowweaver.gateway.temporal_observation.v0"
SENSITIVE_SENTINEL = "unsafe-" + "to" + "ken" + "-phase19"
PRIVATE_CHAT_ID = "oc_" + "phase19_private_chat"
PRIVATE_USER_ID = "ou_" + "phase19_private_user"
RAW_PROMPT_VALUE = "raw prompt phase19 value"
RAW_TOOL_OUTPUT_VALUE = "raw tool output phase19 value"
CARD_JSON_VALUE = '{"type":"card_json"}'
MEDIA_PATH_VALUE = "/tmp/phase19-private.png"
CALLBACK_VALUE = "callback payload phase19 value"
RAW_EXCEPTION_VALUE = "ValueError: raw exception phase19 value"


class RecordingRuntimeControlSurface:
    def __init__(self, *, fail_start: bool = False, unsafe_query: bool = False) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail_start = fail_start
        self.unsafe_query = unsafe_query
        self._start_payloads: dict[str, dict[str, object]] = {}

    async def handle(self, request: object) -> dict[str, object]:
        assert type(request) is dict
        safe_request = copy.deepcopy(request)
        self.calls.append(safe_request)
        operation = safe_request["operation"]
        workflow_id = str(safe_request["workflow_id"])
        if operation == "start_transaction":
            if self.fail_start:
                return {"ok": False, "operation": "start_transaction", "error_code": "runtime_error"}
            start_payload = safe_request["start_payload"]
            assert type(start_payload) is dict
            self._start_payloads[workflow_id] = start_payload
            return {
                "ok": True,
                "operation": "start_transaction",
                "runtime_operation": "start_transaction",
                "workflow_id": workflow_id,
                "transaction_id": workflow_id,
                "status": "started",
            }
        if operation == "query_transaction":
            if self.unsafe_query:
                return {
                    "ok": True,
                    "operation": "query_transaction",
                    "runtime_operation": "query_snapshot",
                    "workflow_id": workflow_id,
                    "snapshot": {"platform_payload": {"chat_id": PRIVATE_CHAT_ID}},
                }
            start_payload = self._start_payloads[workflow_id]
            return {
                "ok": True,
                "operation": "query_transaction",
                "runtime_operation": "query_snapshot",
                "workflow_id": workflow_id,
                "transaction_id": workflow_id,
                "status": "running",
                "snapshot": snapshot_for(workflow_id, start_payload),
            }
        raise AssertionError(f"forbidden runtime operation: {operation}")


def snapshot_for(workflow_id: str, start_payload: dict[str, object]) -> dict[str, object]:
    record_counts = copy.deepcopy(start_payload["record_counts"])
    entry_count = start_payload["entry_count"]
    assert type(record_counts) is dict
    assert type(entry_count) is int
    return {
        "type": "flowweaver.temporal_poc.snapshot.v0",
        "version": "flowweaver.temporal_poc.v0",
        "transaction_id": workflow_id,
        "status": "running",
        "entry_count": entry_count,
        "record_counts": record_counts,
        "start_signature": {
            "type": "flowweaver.temporal_poc.start_signature.v0",
            "version": "flowweaver.temporal_poc.v0",
            "idempotency_key": start_payload["idempotency_key"],
            "event_contract_digest": "runtime_sig_" + "a" * 64,
            "claim_policy_digest": "runtime_sig_" + "b" * 64,
        },
        "counts": {"intents": entry_count, "artifacts": entry_count, "deliveries": record_counts["deliveries"]},
        "intent_statuses": {"runtime_intent_0": "pending"},
        "artifact_statuses": {"runtime_artifact_0": "planned"},
        "delivery_statuses": {"runtime_delivery_0": "planned"},
        "applied_event_count": 0,
        "resume_count": 0,
        "side_effects": [],
    }


def enabled_policy() -> dict[str, object]:
    return {
        "type": "flowweaver.gateway.temporal_observation_bridge_policy.v0",
        "enabled": True,
        "mode": "controlled_observation",
        "allow_runtime_start": True,
        "allow_runtime_query": True,
        "side_effects": [],
    }


def disabled_policy() -> dict[str, object]:
    policy = enabled_policy()
    policy.update(
        {
            "enabled": False,
            "mode": "default_off",
            "allow_runtime_start": False,
            "allow_runtime_query": False,
        }
    )
    return policy


def safe_observation(**overrides: object) -> dict[str, object]:
    observation: dict[str, object] = {
        "type": OBSERVATION_TYPE,
        "version": OBSERVATION_VERSION,
        "source": "controlled_gateway_observation",
        "session_label": "safe_session_alpha",
        "turn_label": "safe_turn_alpha",
        "turn_discriminator": "safe_discriminator_000001_000001",
        "entry_count": 1,
        "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
        "claim_refs": {
            "input_ref": "claim_ref_gateway_observation_input_alpha",
            "artifact_ref": "claim_ref_gateway_observation_artifact_alpha",
            "delivery_ref": "claim_ref_gateway_observation_delivery_alpha",
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
    for key, value in overrides.items():
        observation[key] = value
    return observation


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
        "allowed_runtime_events",
        "claim_check_policy",
        "forbidden_material",
    )
    for marker in forbidden_values:
        assert marker not in rendered


@pytest.mark.asyncio
async def test_phase19_exposes_async_keyword_only_observation_bridge_entrypoint() -> None:
    assert inspect.iscoroutinefunction(observe_gateway_turn_for_flowweaver_temporal)
    signature = inspect.signature(observe_gateway_turn_for_flowweaver_temporal)
    assert list(signature.parameters) == ["observation", "runtime_control_surface", "bridge_policy"]
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())
    assert signature.return_annotation == "dict[str, object]"


@pytest.mark.asyncio
async def test_phase19_default_off_returns_disabled_without_touching_runtime() -> None:
    control = RecordingRuntimeControlSurface()
    observation = safe_observation(raw_prompt=RAW_PROMPT_VALUE, platform_payload={"chat_id": PRIVATE_CHAT_ID})

    result = await observe_gateway_turn_for_flowweaver_temporal(
        observation=observation,
        runtime_control_surface=control,
        bridge_policy=disabled_policy(),
    )

    assert result == {
        "type": RESULT_TYPE,
        "version": RESULT_VERSION,
        "ok": False,
        "operation": "observe_gateway_turn_for_flowweaver_temporal",
        "status": "disabled",
        "error_code": "disabled",
        "side_effects": [],
    }
    assert control.calls == []
    assert_no_forbidden_output(result)


@pytest.mark.parametrize(
    ("case", "observation"),
    [
        ("raw_prompt_key", safe_observation(raw_prompt=RAW_PROMPT_VALUE)),
        ("raw_tool_output_key", safe_observation(tool_output=RAW_TOOL_OUTPUT_VALUE)),
        ("card_json_key", safe_observation(card_json=CARD_JSON_VALUE)),
        ("media_path_value", safe_observation(turn_label=MEDIA_PATH_VALUE)),
        ("private_platform_id", safe_observation(session_label=PRIVATE_CHAT_ID)),
        ("callback_payload_key", safe_observation(callback_payload=CALLBACK_VALUE)),
        ("raw_exception_text", safe_observation(turn_label=RAW_EXCEPTION_VALUE)),
        ("credential_shaped_value", safe_observation(turn_label=SENSITIVE_SENTINEL)),
        (
            "integer_bool_impersonator",
            safe_observation(
                checks={
                    "payloads_absent": 1,
                    "claim_check_refs_only": True,
                    "side_effects_absent": True,
                    "source_ids_sanitized": True,
                }
            ),
        ),
    ],
)
@pytest.mark.asyncio
async def test_phase19_rejects_unsafe_observation_before_runtime_calls(case: str, observation: object) -> None:
    control = RecordingRuntimeControlSurface()

    result = await observe_gateway_turn_for_flowweaver_temporal(
        observation=observation,
        runtime_control_surface=control,
        bridge_policy=enabled_policy(),
    )

    assert case
    assert result == {
        "type": RESULT_TYPE,
        "version": RESULT_VERSION,
        "ok": False,
        "operation": "observe_gateway_turn_for_flowweaver_temporal",
        "error_code": "invalid_observation",
        "side_effects": [],
    }
    assert control.calls == []
    assert_no_forbidden_output(result)


@pytest.mark.asyncio
async def test_phase19_rejects_hostile_plain_type_subclasses_before_runtime_calls() -> None:
    class HostileDict(dict):
        pass

    class HostileList(list):
        pass

    class HostileStr(str):
        pass

    observations: list[object] = [
        HostileDict(safe_observation()),
        safe_observation(surfaces=HostileList(["final_text"])),
        safe_observation(session_label=HostileStr("safe_session_alpha")),
    ]
    for observation in observations:
        control = RecordingRuntimeControlSurface()
        result = await observe_gateway_turn_for_flowweaver_temporal(
            observation=observation,
            runtime_control_surface=control,
            bridge_policy=enabled_policy(),
        )
        assert result["ok"] is False
        assert result["error_code"] == "invalid_observation"
        assert control.calls == []
        assert_no_forbidden_output(result)


@pytest.mark.asyncio
async def test_phase19_rejects_integer_bool_policy_before_runtime_calls() -> None:
    policy = enabled_policy()
    policy["enabled"] = 1
    control = RecordingRuntimeControlSurface()

    result = await observe_gateway_turn_for_flowweaver_temporal(
        observation=safe_observation(),
        runtime_control_surface=control,
        bridge_policy=policy,
    )

    assert result["ok"] is False
    assert result["error_code"] == "invalid_bridge_policy"
    assert control.calls == []
    assert_no_forbidden_output(result)


@pytest.mark.asyncio
async def test_phase19_enabled_bridge_calls_runtime_start_then_query_only_with_phase5c_safe_start_payload() -> None:
    control = RecordingRuntimeControlSurface()

    result = await observe_gateway_turn_for_flowweaver_temporal(
        observation=safe_observation(),
        runtime_control_surface=control,
        bridge_policy=enabled_policy(),
    )

    assert result["ok"] is True
    assert result["verdict"] == SUCCESS_VERDICT
    assert result["runtime_call_counts"] == {"start_transaction": 1, "query_transaction": 1}
    assert [call["operation"] for call in control.calls] == ["start_transaction", "query_transaction"]
    start_request = control.calls[0]
    query_request = control.calls[1]
    payload = build_start_payload_from_safe_fields(start_request["start_payload"])
    assert start_request["workflow_id"] == payload.transaction_id
    assert query_request == {"operation": "query_transaction", "workflow_id": payload.transaction_id}
    assert result["workflow_id"] == payload.transaction_id
    assert result["transaction_id"] == payload.transaction_id
    assert result["snapshot_summary"] == {
        "status": "running",
        "entry_count": 1,
        "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
        "counts": {"intents": 1, "artifacts": 1, "deliveries": 1},
        "side_effects": [],
    }
    assert_no_forbidden_output(result)


@pytest.mark.asyncio
async def test_phase19_same_session_consecutive_turns_use_distinct_safe_runtime_identities() -> None:
    control = RecordingRuntimeControlSurface()
    first = safe_observation(turn_discriminator="safe_discriminator_000001_000001")
    second = safe_observation(turn_discriminator="safe_discriminator_000001_000002")

    first_result = await observe_gateway_turn_for_flowweaver_temporal(
        observation=first,
        runtime_control_surface=control,
        bridge_policy=enabled_policy(),
    )
    second_result = await observe_gateway_turn_for_flowweaver_temporal(
        observation=second,
        runtime_control_surface=control,
        bridge_policy=enabled_policy(),
    )

    assert first_result["ok"] is True
    assert second_result["ok"] is True
    assert first_result["workflow_id"] != second_result["workflow_id"]
    assert str(first["turn_discriminator"]) not in repr(first_result)
    assert str(second["turn_discriminator"]) not in repr(second_result)
    assert_no_forbidden_output(first_result)
    assert_no_forbidden_output(second_result)


@pytest.mark.asyncio
async def test_phase19_runtime_failures_are_stable_and_sanitized() -> None:
    control = RecordingRuntimeControlSurface(fail_start=True)

    result = await observe_gateway_turn_for_flowweaver_temporal(
        observation=safe_observation(),
        runtime_control_surface=control,
        bridge_policy=enabled_policy(),
    )

    assert result == {
        "type": RESULT_TYPE,
        "version": RESULT_VERSION,
        "ok": False,
        "operation": "observe_gateway_turn_for_flowweaver_temporal",
        "error_code": "runtime_start_failed",
        "side_effects": [],
    }
    assert [call["operation"] for call in control.calls] == ["start_transaction"]
    assert_no_forbidden_output(result)


@pytest.mark.asyncio
async def test_phase19_unsafe_runtime_query_output_is_rejected_without_echoing_raw_material() -> None:
    control = RecordingRuntimeControlSurface(unsafe_query=True)

    result = await observe_gateway_turn_for_flowweaver_temporal(
        observation=safe_observation(),
        runtime_control_surface=control,
        bridge_policy=enabled_policy(),
    )

    assert result == {
        "type": RESULT_TYPE,
        "version": RESULT_VERSION,
        "ok": False,
        "operation": "observe_gateway_turn_for_flowweaver_temporal",
        "error_code": "unsafe_runtime_output",
        "side_effects": [],
    }
    assert [call["operation"] for call in control.calls] == ["start_transaction", "query_transaction"]
    assert_no_forbidden_output(result)


def test_phase19_bridge_source_does_not_own_temporal_lifecycle_or_gateway_side_effects() -> None:
    source = MODULE_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_import_roots = {
        "temporalio",
        "subprocess",
        "socket",
        "os",
        "logging",
        "importlib",
        "gateway.platforms",
        "run_agent",
        "toolsets",
        "model_tools",
    }
    forbidden_call_names = {
        "connect",
        "Client",
        "Worker",
        "WorkflowEnvironment",
        "Popen",
        "run",
        "system",
        "open",
        "write_text",
        "send_message",
        "edit_message",
        "render",
        "callback",
        "__import__",
    }
    imports: list[str] = []
    calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)

    assert sorted(item for item in imports if item.split(".")[0] in forbidden_import_roots or item in forbidden_import_roots) == []
    assert sorted(call for call in calls if call in forbidden_call_names) == []
    forbidden_markers = (
        "Client.connect",
        "WorkflowEnvironment",
        "temporal server",
        "Docker",
        "systemctl",
        "gateway restart",
        "config.yaml",
        "gateway.platforms",
        "send_message",
        "edit_message",
        ".send(",
        ".edit(",
        ".render(",
        ".callback(",
        "repr(raw",
        "print(raw",
        "__import__",
    )
    assert {marker for marker in forbidden_markers if marker.lower() in source.lower()} == set()


def test_phase19_diff_stays_inside_temporal_observation_bridge_allowlist() -> None:
    changed_files = _changed_files()
    allowed_changed_files = {
        "docs/plans/2026-05-09-flowweaver-phase19-controlled-gateway-temporal-observation-bridge.md",
        "docs/dev_log/2026-05-09-flowweaver-phase19-controlled-gateway-temporal-observation-bridge.md",
        "docs/runbooks/flowweaver-temporal-observation-bridge.md",
        "gateway/flowweaver_temporal_observation_bridge.py",
        "tests/gateway/test_flowweaver_temporal_observation_bridge.py",
        "docs/plans/2026-05-10-flowweaver-phase20-guarded-temporal-observation-validation.md",
        "docs/dev_log/2026-05-10-flowweaver-phase20-guarded-temporal-observation-validation.md",
        "docs/runbooks/flowweaver-temporal-observation-validation.md",
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
        "tests/gateway/test_flowweaver_pe1_controlled_sachima_shadow_observation.py",
    }
    assert sorted(changed_files - allowed_changed_files) == []


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _changed_files() -> set[str]:
    base = _git("merge-base", "HEAD", "origin/feature/sachima-channel")
    commands = (
        ("diff", "--name-only", base, "HEAD"),
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    )
    changed: set[str] = set()
    for command in commands:
        output = _git(*command)
        changed.update(line for line in output.splitlines() if line)
    return changed
