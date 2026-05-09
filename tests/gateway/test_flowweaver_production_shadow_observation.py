"""RED gate tests for FlowWeaver Phase 21 production-shadow observation."""

from __future__ import annotations

import ast
import asyncio
import copy
import inspect
import subprocess
import sys
import time
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PHASE5B_SRC = ROOT / "prototypes" / "flowweaver_phase5b_temporal_poc" / "src"
PHASE5C_SRC = ROOT / "prototypes" / "flowweaver_phase5c_runtime_client" / "src"
for path in (PHASE5C_SRC, PHASE5B_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from gateway.delivery_state import should_skip_final_text  # noqa: E402
from gateway.flowweaver_production_shadow_observation import (  # noqa: E402
    FLOWWEAVER_PRODUCTION_SHADOW_OBSERVATION_VERSION,
    PRODUCTION_SHADOW_OBSERVATION_RESULT_TYPE,
    PRODUCTION_SHADOW_OBSERVATION_SUCCESS_VERDICT,
    observe_gateway_turn_for_flowweaver_production_shadow,
    production_shadow_observation_policy_from_config,
)
from gateway.run import GatewayRunner  # noqa: E402

MODULE_SOURCE = ROOT / "gateway" / "flowweaver_production_shadow_observation.py"
RUN_SOURCE = ROOT / "gateway" / "run.py"
PRIVATE_CHAT_ID = "oc_" + "phase21_private_chat"
PRIVATE_USER_ID = "ou_" + "phase21_private_user"
PRIVATE_MESSAGE_ID = "om_" + "phase21_private_message"
RAW_PROMPT_VALUE = "raw prompt phase21 value"
RAW_TOOL_OUTPUT_VALUE = "raw " + "tool output phase21 value"
CARD_JSON_VALUE = '{"type":"card_json"}'
MEDIA_PATH_VALUE = "/tmp/phase21-private.png"
CALLBACK_VALUE = "callback payload phase21 value"
RAW_EXCEPTION_VALUE = "ValueError: raw exception phase21 value"
SENSITIVE_SENTINEL = "unsafe-" + "token" + "-phase21"


class RecordingRuntimeControlSurface:
    def __init__(
        self,
        *,
        unsafe_query: bool = False,
        fail_query: bool = False,
        raise_query: bool = False,
        delay_seconds: float = 0.0,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self.unsafe_query = unsafe_query
        self.fail_query = fail_query
        self.raise_query = raise_query
        self.delay_seconds = delay_seconds
        self._payloads: dict[str, dict[str, object]] = {}

    async def handle(self, request: object) -> dict[str, object]:
        assert type(request) is dict
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        safe_request = copy.deepcopy(request)
        self.calls.append(safe_request)
        operation = safe_request["operation"]
        workflow_id = str(safe_request["workflow_id"])
        if operation == "start_transaction":
            start_payload = safe_request["start_payload"]
            assert type(start_payload) is dict
            self._payloads[workflow_id] = start_payload
            return {
                "ok": True,
                "operation": "start_transaction",
                "runtime_operation": "start_transaction",
                "workflow_id": workflow_id,
                "transaction_id": workflow_id,
                "status": "started",
            }
        if operation == "query_transaction":
            if self.raise_query:
                raise RuntimeError("raw exception phase21 value must not leak")
            if self.fail_query:
                return {"ok": False, "operation": "query_transaction", "runtime_operation": "query_snapshot", "error_code": "runtime_error"}
            if self.unsafe_query:
                return {
                    "ok": True,
                    "operation": "query_transaction",
                    "runtime_operation": "query_snapshot",
                    "workflow_id": workflow_id,
                    "snapshot": {"platform_payload": {"chat_id": PRIVATE_CHAT_ID}},
                }
            return {
                "ok": True,
                "operation": "query_transaction",
                "runtime_operation": "query_snapshot",
                "workflow_id": workflow_id,
                "transaction_id": workflow_id,
                "status": "running",
                "snapshot": snapshot_for(workflow_id, self._payloads[workflow_id]),
            }
        raise AssertionError(f"forbidden runtime operation: {operation}")


class Source:
    platform = type("PlatformValue", (), {"value": "feishu"})()


def snapshot_for(workflow_id: str, start_payload: dict[str, object]) -> dict[str, object]:
    entry_count = start_payload["entry_count"]
    record_counts = copy.deepcopy(start_payload["record_counts"])
    assert type(entry_count) is int
    assert type(record_counts) is dict
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


def config(enabled: bool, *, allowlist: list[str] | None = None, timeout_ms: int = 250) -> dict[str, object]:
    return {
        "flowweaver": {
            "production_shadow_observation": {
                "enabled": enabled,
                "platform_allowlist": list(allowlist or []),
                "timeout_ms": timeout_ms,
            }
        }
    }


def gateway_turn(**overrides: object) -> dict[str, object]:
    turn: dict[str, object] = {
        "platform": "feishu",
        "session_key": f"feishu:{PRIVATE_CHAT_ID}:{PRIVATE_USER_ID}",
        "session_id": "sess_phase21_private_source",
        "message_id": PRIVATE_MESSAGE_ID,
        "turn_started_at_ns": 1_777_777_777_000_001,
        "turn_sequence": 42,
        "history_length": 9,
        "api_call_count": 3,
        "final_text_present": True,
        "rich_card_count": 1,
        "media_count": 0,
    }
    turn.update(overrides)
    return turn


def assert_no_forbidden_output(value: object, *, allow_policy_metadata: bool = False) -> None:
    rendered = repr(value).lower()
    forbidden_values = [
        PRIVATE_CHAT_ID.lower(),
        PRIVATE_USER_ID.lower(),
        PRIVATE_MESSAGE_ID.lower(),
        RAW_PROMPT_VALUE,
        RAW_TOOL_OUTPUT_VALUE,
        CARD_JSON_VALUE.lower(),
        MEDIA_PATH_VALUE.lower(),
        CALLBACK_VALUE,
        RAW_EXCEPTION_VALUE.lower(),
        SENSITIVE_SENTINEL.lower(),
    ]
    if not allow_policy_metadata:
        forbidden_values.extend(["allowed_runtime_events", "claim_check_policy", "forbidden_material"])
    for marker in forbidden_values:
        assert marker not in rendered


def test_phase21_exposes_async_keyword_only_production_shadow_entrypoint() -> None:
    assert inspect.iscoroutinefunction(observe_gateway_turn_for_flowweaver_production_shadow)
    signature = inspect.signature(observe_gateway_turn_for_flowweaver_production_shadow)
    assert list(signature.parameters) == ["gateway_turn", "runtime_control_surface", "shadow_policy"]
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())
    assert signature.return_annotation == "dict[str, object]"


def test_phase21_policy_from_config_defaults_disabled_and_requires_allowlisted_platform() -> None:
    default_policy = production_shadow_observation_policy_from_config({}, platform="feishu")
    assert default_policy["enabled"] is False
    assert default_policy["mode"] == "default_off"
    assert default_policy["allow_platforms"] == []

    policy = production_shadow_observation_policy_from_config(config(True, allowlist=["feishu"], timeout_ms=125), platform="feishu")
    assert policy == {
        "type": "flowweaver.gateway.production_shadow_observation_policy.v0",
        "enabled": True,
        "mode": "production_shadow_observation",
        "allow_runtime_start": True,
        "allow_runtime_query": True,
        "allow_platforms": ["feishu"],
        "timeout_ms": 125,
        "side_effects": [],
    }


@pytest.mark.asyncio
async def test_phase21_default_off_returns_disabled_without_touching_runtime_or_raw_turn() -> None:
    control = RecordingRuntimeControlSurface()
    policy = production_shadow_observation_policy_from_config({}, platform="feishu")

    result = await observe_gateway_turn_for_flowweaver_production_shadow(
        gateway_turn=gateway_turn(raw_prompt=RAW_PROMPT_VALUE, platform_payload={"chat_id": PRIVATE_CHAT_ID}),
        runtime_control_surface=control,
        shadow_policy=policy,
    )

    assert result == {
        "type": PRODUCTION_SHADOW_OBSERVATION_RESULT_TYPE,
        "version": FLOWWEAVER_PRODUCTION_SHADOW_OBSERVATION_VERSION,
        "ok": False,
        "operation": "observe_gateway_turn_for_flowweaver_production_shadow",
        "status": "disabled",
        "error_code": "disabled",
        "counters": {"disabled": 1, "skipped": 0, "started": 0, "query_failed": 0, "unsafe_runtime_output": 0, "timeout": 0},
        "side_effects": [],
    }
    assert control.calls == []
    assert_no_forbidden_output(result)


@pytest.mark.asyncio
async def test_phase21_enabled_but_not_allowlisted_skips_without_touching_runtime() -> None:
    control = RecordingRuntimeControlSurface()
    policy = production_shadow_observation_policy_from_config(config(True, allowlist=["telegram"]), platform="feishu")

    result = await observe_gateway_turn_for_flowweaver_production_shadow(
        gateway_turn=gateway_turn(raw_prompt=RAW_PROMPT_VALUE, platform_payload={"chat_id": PRIVATE_CHAT_ID}),
        runtime_control_surface=control,
        shadow_policy=policy,
    )

    assert result["ok"] is False
    assert result["status"] == "skipped"
    assert result["error_code"] == "platform_not_allowlisted"
    assert result["counters"] == {"disabled": 0, "skipped": 1, "started": 0, "query_failed": 0, "unsafe_runtime_output": 0, "timeout": 0}
    assert control.calls == []
    assert_no_forbidden_output(result)


@pytest.mark.asyncio
async def test_phase21_enabled_path_reduces_real_gateway_turn_to_safe_start_query_only() -> None:
    control = RecordingRuntimeControlSurface()
    policy = production_shadow_observation_policy_from_config(config(True, allowlist=["feishu"]), platform="feishu")

    result = await observe_gateway_turn_for_flowweaver_production_shadow(
        gateway_turn=gateway_turn(
            raw_prompt=RAW_PROMPT_VALUE,
            tool_output=RAW_TOOL_OUTPUT_VALUE,
            card_json=CARD_JSON_VALUE,
            media_path=MEDIA_PATH_VALUE,
            callback_payload=CALLBACK_VALUE,
            raw_exception=RAW_EXCEPTION_VALUE,
            credential=SENSITIVE_SENTINEL,
        ),
        runtime_control_surface=control,
        shadow_policy=policy,
    )

    assert result["ok"] is True
    assert result["verdict"] == PRODUCTION_SHADOW_OBSERVATION_SUCCESS_VERDICT
    assert result["runtime_call_counts"] == {"start_transaction": 1, "query_transaction": 1}
    assert result["counters"] == {"disabled": 0, "skipped": 0, "started": 1, "query_failed": 0, "unsafe_runtime_output": 0, "timeout": 0}
    assert [call["operation"] for call in control.calls] == ["start_transaction", "query_transaction"]
    assert "reconcile_delivery_ack" not in [call["operation"] for call in control.calls]
    start_payload = control.calls[0]["start_payload"]
    assert type(start_payload) is dict
    assert start_payload["transaction_id"] == result["workflow_id"]
    assert start_payload["entry_count"] == 1
    assert start_payload["record_counts"] == {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 2}
    assert_no_forbidden_output(result)
    assert_no_forbidden_output(control.calls, allow_policy_metadata=True)


@pytest.mark.parametrize(
    ("case", "runtime", "expected_code"),
    [
        ("missing_runtime", None, "runtime_control_surface_required"),
        ("unsafe_query", RecordingRuntimeControlSurface(unsafe_query=True), "unsafe_runtime_output"),
        ("query_exception", RecordingRuntimeControlSurface(raise_query=True), "runtime_query_failed"),
    ],
)
@pytest.mark.asyncio
async def test_phase21_fail_closed_paths_are_sanitized(case: str, runtime: object, expected_code: str) -> None:
    policy = production_shadow_observation_policy_from_config(config(True, allowlist=["feishu"]), platform="feishu")

    result = await observe_gateway_turn_for_flowweaver_production_shadow(
        gateway_turn=gateway_turn(raw_exception=RAW_EXCEPTION_VALUE),
        runtime_control_surface=runtime,
        shadow_policy=policy,
    )

    assert case
    assert result["ok"] is False
    assert result["error_code"] == expected_code
    assert result["side_effects"] == []
    assert_no_forbidden_output(result)


@pytest.mark.asyncio
async def test_phase21_timeout_is_bounded_and_sanitized() -> None:
    control = RecordingRuntimeControlSurface(delay_seconds=0.1)
    policy = production_shadow_observation_policy_from_config(config(True, allowlist=["feishu"], timeout_ms=1), platform="feishu")
    started = time.monotonic()

    result = await observe_gateway_turn_for_flowweaver_production_shadow(
        gateway_turn=gateway_turn(),
        runtime_control_surface=control,
        shadow_policy=policy,
    )
    elapsed = time.monotonic() - started

    assert elapsed < 0.08
    assert result["ok"] is False
    assert result["error_code"] == "timeout"
    assert result["counters"] == {"disabled": 0, "skipped": 0, "started": 0, "query_failed": 0, "unsafe_runtime_output": 0, "timeout": 1}
    assert_no_forbidden_output(result)


@pytest.mark.asyncio
async def test_phase21_operator_kill_switch_stops_new_starts_but_existing_query_remains_safe() -> None:
    control = RecordingRuntimeControlSurface()
    enabled = production_shadow_observation_policy_from_config(config(True, allowlist=["feishu"]), platform="feishu")
    disabled = production_shadow_observation_policy_from_config(config(False, allowlist=["feishu"]), platform="feishu")

    first = await observe_gateway_turn_for_flowweaver_production_shadow(
        gateway_turn=gateway_turn(turn_sequence=1),
        runtime_control_surface=control,
        shadow_policy=enabled,
    )
    before_disable_count = len(control.calls)
    after_disable = await observe_gateway_turn_for_flowweaver_production_shadow(
        gateway_turn=gateway_turn(turn_sequence=2),
        runtime_control_surface=control,
        shadow_policy=disabled,
    )
    existing_query = await control.handle({"operation": "query_transaction", "workflow_id": first["workflow_id"]})

    assert first["ok"] is True
    assert after_disable["status"] == "disabled"
    assert len(control.calls) == before_disable_count + 1
    assert existing_query["operation"] == "query_transaction"
    assert existing_query["snapshot"]["transaction_id"] == first["workflow_id"]
    assert_no_forbidden_output(first)
    assert_no_forbidden_output(after_disable)
    assert_no_forbidden_output(existing_query)


@pytest.mark.asyncio
async def test_phase21_gateway_runner_hook_preserves_response_delivery_state_and_skip_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = GatewayRunner.__new__(GatewayRunner)
    runner._flowweaver_runtime_control_surface = RecordingRuntimeControlSurface()
    runner._flowweaver_production_shadow_observation_counters = {}
    monkeypatch.setattr(
        "gateway.run._load_gateway_config",
        lambda: config(True, allowlist=["feishu"], timeout_ms=50),
    )
    agent_result = {
        "final_response": "phase21 visible reply",
        "api_calls": 2,
        "delivery_state": {"final_text": {"sent": False, "reason": None}, "rich_cards_sent": [{"type": "weather.v1", "message_id": PRIVATE_MESSAGE_ID}], "media_sent": []},
    }
    before_delivery_state = copy.deepcopy(agent_result["delivery_state"])
    before_skip = should_skip_final_text(agent_result)

    result = await runner._maybe_observe_flowweaver_production_shadow(
        source=Source(),
        session_key=f"feishu:{PRIVATE_CHAT_ID}:{PRIVATE_USER_ID}",
        session_id="sess_phase21_private_source",
        history_length=5,
        agent_result=agent_result,
        response="phase21 visible reply",
        turn_started_at_ns=1_777_777_777_000_123,
    )

    assert result["ok"] is True
    assert agent_result["delivery_state"] == before_delivery_state
    assert should_skip_final_text(agent_result) is before_skip
    assert agent_result.get("already_sent") is None
    assert_no_forbidden_output(result)
    assert_no_forbidden_output(runner._flowweaver_runtime_control_surface.calls, allow_policy_metadata=True)


@pytest.mark.asyncio
async def test_phase21_gateway_runner_hook_timeout_preserves_delivery_state_and_skip_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = GatewayRunner.__new__(GatewayRunner)
    runner._flowweaver_runtime_control_surface = RecordingRuntimeControlSurface(delay_seconds=0.1)
    runner._flowweaver_production_shadow_observation_counters = {}
    monkeypatch.setattr(
        "gateway.run._load_gateway_config",
        lambda: config(True, allowlist=["feishu"], timeout_ms=1),
    )
    agent_result = {
        "final_response": "phase21 visible reply",
        "api_calls": 2,
        "delivery_state": {"final_text": {"sent": False, "reason": None}, "rich_cards_sent": [{"type": "weather.v1", "message_id": PRIVATE_MESSAGE_ID}], "media_sent": []},
    }
    before_delivery_state = copy.deepcopy(agent_result["delivery_state"])
    before_skip = should_skip_final_text(agent_result)

    result = await runner._maybe_observe_flowweaver_production_shadow(
        source=Source(),
        session_key=f"feishu:{PRIVATE_CHAT_ID}:{PRIVATE_USER_ID}",
        session_id="sess_phase21_private_source",
        history_length=5,
        agent_result=agent_result,
        response="phase21 visible reply",
        turn_started_at_ns=1_777_777_777_000_123,
    )

    assert result["ok"] is False
    assert result["error_code"] == "timeout"
    assert agent_result["delivery_state"] == before_delivery_state
    assert should_skip_final_text(agent_result) is before_skip
    assert agent_result.get("already_sent") is None
    assert_no_forbidden_output(result)


def test_phase21_source_does_not_own_temporal_lifecycle_or_delivery_side_effects() -> None:
    module_source = MODULE_SOURCE.read_text(encoding="utf-8")
    runner_method_source = inspect.getsource(GatewayRunner._maybe_observe_flowweaver_production_shadow)
    tree = ast.parse(module_source + "\n" + textwrap.dedent(runner_method_source))
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

    forbidden_import_roots = {"temporalio", "gateway.platforms", "tools", "socket", "subprocess"}
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
    forbidden_markers = (
        "Client.connect",
        "WorkflowEnvironment",
        "temporal_address",
        "namespace",
        "task_queue",
        "systemctl",
        "gateway restart",
        "config.yaml",
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

    assert sorted(root for root in imports if root in forbidden_import_roots) == []
    assert sorted(call for call in calls if call in forbidden_call_names) == []
    combined = (module_source + "\n" + textwrap.dedent(runner_method_source)).lower()
    assert {marker for marker in forbidden_markers if marker.lower() in combined} == set()


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


def test_phase21_diff_stays_inside_production_shadow_observation_allowlist() -> None:
    changed_files = _changed_files()
    allowed_changed_files = {
        "docs/plans/2026-05-11-flowweaver-phase21-production-shadow-observation-only.md",
        "docs/dev_log/2026-05-11-flowweaver-phase21-production-shadow-observation-only.md",
        "docs/runbooks/flowweaver-production-shadow-observation.md",
        "gateway/flowweaver_production_shadow_observation.py",
        "gateway/flowweaver_temporal_observation_bridge.py",
        "gateway/run.py",
        "tests/gateway/test_flowweaver_production_shadow_observation.py",
        "tests/integration/test_flowweaver_phase21_production_shadow_observation.py",
        "tests/gateway/test_flowweaver_shadow_publisher.py",
        "tests/gateway/test_flowweaver_temporal_observation_bridge.py",
        "tests/gateway/test_flowweaver_temporal_observation_validation_gate.py",
        "tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py",
        "tests/integration/test_flowweaver_phase5i_start_signature_parity.py",
        "tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py",
        "tests/integration/test_flowweaver_phase5k_runtime_control_surface.py",
        "tests/prototypes/test_flowweaver_phase5c_tool_surface.py",
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
    }
    forbidden_prefixes = ("gateway/platforms/", "tools/", "hermes_cli/")
    forbidden_exact = {"pyproject.toml", "run_agent.py", "model_tools.py", "toolsets.py"}

    assert sorted(changed_files - allowed_changed_files) == []
    assert not [path for path in changed_files if path in forbidden_exact or path.startswith(forbidden_prefixes)]
