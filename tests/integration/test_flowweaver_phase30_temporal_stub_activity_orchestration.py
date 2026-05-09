"""RED/GREEN tests for FlowWeaver Phase 30 local Temporal stub Activity orchestration."""

from __future__ import annotations

import ast
import asyncio
import copy
import inspect
import subprocess
from pathlib import Path
from typing import Any

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from gateway.flowweaver_stub_activity_implementation import (
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_REPORT_TYPE,
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_SUCCESS_VERDICT,
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VERSION,
    describe_flowweaver_stub_activity_implementation_contract,
    validate_flowweaver_stub_activity_implementation_report,
)
from gateway.flowweaver_stub_activity_implementation_validation import (
    FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_SUCCESS_VERDICT,
)
from gateway.flowweaver_temporal_stub_activity_orchestration import (
    FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_CONTRACT_TYPE,
    FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_REPORT_TYPE,
    FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SNAPSHOT_TYPE,
    FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_START_PAYLOAD_TYPE,
    FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT,
    FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_VERSION,
    FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_TASK_QUEUE,
    FlowWeaverTemporalStubActivityWorkflow,
    build_flowweaver_temporal_stub_activity_orchestration_report,
    build_flowweaver_temporal_stub_activity_start_payload,
    cancel_stub_activity_orchestration,
    deliver_artifact_activity,
    describe_flowweaver_temporal_stub_activity_orchestration_contract,
    execute_agent_turn_activity,
    start_or_reconcile_flowweaver_temporal_stub_activity_workflow,
    validate_claim_check_ref_activity,
    validate_flowweaver_temporal_stub_activity_orchestration_report,
    validate_flowweaver_temporal_stub_activity_snapshot,
    validate_flowweaver_temporal_stub_activity_start_payload,
)

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
MODULE_SOURCE = ROOT / "gateway" / "flowweaver_temporal_stub_activity_orchestration.py"
PLAN_DOC = ROOT / "docs" / "plans" / "2026-05-09-flowweaver-phase30-temporal-stub-activity-orchestration.md"
DEV_LOG = ROOT / "docs" / "dev_log" / "2026-05-09-flowweaver-phase30-temporal-stub-activity-orchestration.md"
RUNBOOK = ROOT / "docs" / "runbooks" / "flowweaver-temporal-stub-activity-orchestration.md"

EXPECTED_ACTIVITY_SEQUENCE = ["validate_claim_check_ref", "execute_agent_turn", "deliver_artifact"]
EXPECTED_CONTRACT_FIELDS = [
    "type",
    "version",
    "phase",
    "verdict",
    "scope",
    "consumes_contract",
    "consumes_report",
    "entrypoints",
    "workflow",
    "activity_wrappers",
    "start_payload_fields",
    "snapshot_fields",
    "report_fields",
    "activity_sequence",
    "runtime_policy",
    "retry_policy",
    "checks",
    "separate_approvals",
    "forbidden_side_effects",
    "side_effects",
]
EXPECTED_START_PAYLOAD_FIELDS = [
    "type",
    "version",
    "phase",
    "transaction_id",
    "workflow_id",
    "intent_id",
    "claim_check_ref",
    "claim_policy",
    "artifact_ref",
    "delivery_ref",
    "execution_mode",
    "execution_digest",
    "activity_sequence",
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
    "activity_sequence",
    "counts",
    "execution_digest",
    "retry_policy",
    "error_code",
    "side_effects",
]
EXPECTED_REPORT_FIELDS = [
    "type",
    "version",
    "phase",
    "ok",
    "verdict",
    "operation",
    "phase29_verdict",
    "workflow",
    "activity_sequence",
    "local_run_status",
    "history_no_leak_checked",
    "snapshot_no_leak_checked",
    "duplicate_start_reconciled",
    "checks",
    "error_code",
    "side_effects",
]
EXPECTED_RUNTIME_POLICY = {
    "mode": "local_staging_temporal_stub_activity_orchestration_only",
    "gateway_worker_lifecycle": "forbidden",
    "client_connection_ownership": "caller_supplied_only",
    "worker_environment_ownership": "tests_only",
    "agent_tool_execution": "forbidden_until_phase31",
    "delivery_execution_ack": "forbidden_until_phase32",
    "raw_material_policy": "claim_check_refs_and_safe_ids_only",
    "side_effects": [],
}
EXPECTED_RETRY_POLICY = {
    "start_to_close_timeout_seconds": 5,
    "maximum_attempts": 2,
    "non_retryable_error_types": [
        "invalid_start_payload",
        "invalid_claim_ref",
        "invalid_agent_activity_input",
        "invalid_delivery_activity_input",
        "unsafe_material",
    ],
}
EXPECTED_CHECKS = [
    "phase29_contract_valid",
    "phase29_report_valid",
    "temporal_activity_wrappers_defined",
    "workflow_executes_fixed_activity_sequence",
    "local_worker_harness_verified",
    "history_no_leak_verified",
    "snapshot_no_leak_verified",
    "duplicate_start_reconciliation_verified",
    "gateway_worker_lifecycle_absent",
    "side_effects_absent",
]
EXPECTED_SEPARATE_APPROVALS = [
    "controlled_agent_activity_implementation",
    "controlled_delivery_activity",
    "production_gateway_wiring",
    "production_config_write",
    "gateway_restart",
    "platform_adapter_mutation",
    "real_agent_tool_execution",
    "real_send_edit_render_callback_control",
    "delivery_ack_updates",
]
EXPECTED_FORBIDDEN_SIDE_EFFECTS = [
    "gateway_owned_worker_lifecycle",
    "client_connect_factory",
    "workflow_environment_factory",
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
    "agent_execution",
    "tool_execution",
    "send",
    "edit",
    "render",
    "callback_control",
    "delivery_ack_update",
    "raw_material_persistence",
]

PRIVATE_CHAT_ID = "oc_" + "phase30_private_chat"
PRIVATE_USER_ID = "ou_" + "phase30_private_user"
PRIVATE_MESSAGE_ID = "om_" + "phase30_private_message"
RAW_PROMPT_VALUE = "raw prompt phase30 private value"
RAW_TOOL_VALUE = "raw " + "tool output phase30 private value"
CARD_JSON_VALUE = '{"type":"card_json","body":"phase30"}'
MEDIA_PATH_VALUE = "/tmp/phase30-private.png"
CALLBACK_VALUE = "callback payload phase30 private value"
RAW_EXCEPTION_VALUE = "RuntimeError: raw phase30 exception value"
SENSITIVE_SENTINEL = "unsafe-" + "token" + "-phase30"
BEARER_VALUE = "Bearer " + "phase30-private"
OPENAI_KEY_VALUE = "sk-" + "phase30-private"
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
FORBIDDEN_HISTORY_KEY_PATTERNS = (
    b'"raw_prompt"',
    b'"tool_output"',
    b'"card_json"',
    b'"media_path"',
    b'"callback_payload"',
    b'"platform_id"',
    b'"chat_id"',
    b'"user_id"',
    b'"message_id"',
    b'"credential"',
    b'"secret"',
)


class FakeTemporalClient:
    def __init__(self) -> None:
        self.started = False
        self.handles: list[str] = []

    async def start_workflow(self, *args: object, **kwargs: object) -> object:  # pragma: no cover - failure trap
        self.started = True
        raise AssertionError("invalid payload should not call Temporal")

    def get_workflow_handle(self, workflow_id: str) -> object:  # pragma: no cover - failure trap
        self.handles.append(workflow_id)
        raise AssertionError("invalid payload should not query Temporal")


def claim_ref(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "ref": "claim_ref_phase30_0",
        "kind": "agent_input",
        "count": 1,
        "size": 128,
        "checksum_hint": "sha256:" + ("a" * 64),
    }
    value.update(overrides)
    return value


def p29_report() -> dict[str, object]:
    descriptor = describe_flowweaver_stub_activity_implementation_contract()
    report = {
        "type": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_REPORT_TYPE,
        "version": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VERSION,
        "phase": "phase29",
        "ok": True,
        "verdict": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_SUCCESS_VERDICT,
        "operation": "implement_flowweaver_stub_activities",
        "phase28_verdict": FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_VALIDATION_SUCCESS_VERDICT,
        "activity_function_names": ["validate_claim_check_ref", "execute_agent_turn", "deliver_artifact"],
        "implementation_policy": copy.deepcopy(descriptor["implementation_policy"]),
        "validation_policy": copy.deepcopy(descriptor["validation_policy"]),
        "checks": {key: True for key in descriptor["checks"]},
        "error_code": None,
        "side_effects": [],
    }
    return validate_flowweaver_stub_activity_implementation_report(report)


def start_payload(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "transaction_id": "runtime_tx_phase30_1",
        "workflow_id": "runtime_tx_phase30_1",
        "intent_id": "runtime_intent_0",
        "claim_check_ref": claim_ref(),
        "artifact_ref": "runtime_artifact_0",
        "delivery_ref": "runtime_delivery_0",
    }
    kwargs.update(overrides)
    return build_flowweaver_temporal_stub_activity_start_payload(**kwargs)  # type: ignore[arg-type]


def assert_no_raw_values(value: object) -> None:
    rendered = repr(value).lower()
    for marker in FORBIDDEN_SENTINELS:
        assert marker.lower() not in rendered
    assert "workflowalreadystartederror" not in rendered
    assert "traceback" not in rendered
    assert "temporalio.exceptions" not in rendered


def history_text_and_bytes(history: Any) -> tuple[str, bytes]:
    rendered = history.to_json() if hasattr(history, "to_json") else repr(history.to_json_dict())
    raw_events = b"".join(event.SerializeToString() for event in history.events)
    return rendered, raw_events


def assert_history_has_no_raw_material(history: Any) -> None:
    rendered, raw_events = history_text_and_bytes(history)
    rendered_bytes = rendered.encode("utf-8", "ignore")
    for marker in FORBIDDEN_SENTINELS:
        assert marker not in rendered
        assert marker.encode() not in raw_events
    for pattern in FORBIDDEN_HISTORY_KEY_PATTERNS:
        assert pattern not in rendered_bytes
        assert pattern not in raw_events


async def open_worker(task_queue: str = FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_TASK_QUEUE) -> tuple[WorkflowEnvironment, Worker]:
    env = await WorkflowEnvironment.start_time_skipping()
    worker = Worker(
        env.client,
        task_queue=task_queue,
        workflows=[FlowWeaverTemporalStubActivityWorkflow],
        activities=[validate_claim_check_ref_activity, execute_agent_turn_activity, deliver_artifact_activity],
    )
    await env.__aenter__()
    await worker.__aenter__()
    return env, worker


async def close_worker(env: WorkflowEnvironment, worker: Worker) -> None:
    await worker.__aexit__(None, None, None)
    await env.__aexit__(None, None, None)


async def query_until_status(handle: Any, status: str) -> dict[str, object]:
    last_error: Exception | None = None
    for _ in range(30):
        try:
            snapshot = await handle.query(FlowWeaverTemporalStubActivityWorkflow.query_snapshot)
        except Exception as exc:  # Temporal can reject queries before first workflow task completion.
            last_error = exc
            await asyncio.sleep(0.05)
            continue
        if snapshot.get("status") == status:
            return validate_flowweaver_temporal_stub_activity_snapshot(snapshot)
        await asyncio.sleep(0.05)
    if last_error is not None:
        raise last_error
    raise AssertionError(f"workflow did not reach {status}")


async def cancel_if_running(handle: Any, event_id: str) -> None:
    with pytest.MonkeyPatch.context():
        try:
            await handle.execute_update(FlowWeaverTemporalStubActivityWorkflow.cancel, event_id)
        except Exception:
            return
        with pytest.raises(Exception):
            await asyncio.wait_for(handle.result(), timeout=0.01)


def test_phase30_exposes_temporal_workflow_activity_wrappers_and_safe_entrypoints() -> None:
    contract = describe_flowweaver_temporal_stub_activity_orchestration_contract()
    assert list(contract) == EXPECTED_CONTRACT_FIELDS
    assert contract["type"] == FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_CONTRACT_TYPE
    assert contract["version"] == FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_VERSION
    assert contract["phase"] == "phase30"
    assert contract["verdict"] == FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT
    assert contract["verdict"] == "ready_for_controlled_agent_activity_implementation_request"
    assert contract["scope"] == "local_temporal_stub_activity_orchestration"
    assert contract["consumes_contract"] == describe_flowweaver_stub_activity_implementation_contract()["type"]
    assert contract["consumes_report"] == FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_REPORT_TYPE
    assert contract["activity_sequence"] == EXPECTED_ACTIVITY_SEQUENCE
    assert contract["runtime_policy"] == EXPECTED_RUNTIME_POLICY
    assert contract["retry_policy"] == EXPECTED_RETRY_POLICY
    assert contract["checks"] == EXPECTED_CHECKS
    assert contract["separate_approvals"] == EXPECTED_SEPARATE_APPROVALS
    assert contract["forbidden_side_effects"] == EXPECTED_FORBIDDEN_SIDE_EFFECTS
    assert contract["side_effects"] == []

    for helper in (
        describe_flowweaver_temporal_stub_activity_orchestration_contract,
        validate_flowweaver_temporal_stub_activity_start_payload,
        validate_flowweaver_temporal_stub_activity_snapshot,
        validate_flowweaver_temporal_stub_activity_orchestration_report,
    ):
        assert not inspect.iscoroutinefunction(helper)

    for activity_func in (validate_claim_check_ref_activity, execute_agent_turn_activity, deliver_artifact_activity):
        assert inspect.iscoroutinefunction(activity_func)


def test_phase30_start_payload_builder_accepts_only_safe_refs_counts_statuses_and_digest() -> None:
    payload = start_payload()

    assert list(payload) == EXPECTED_START_PAYLOAD_FIELDS
    assert payload["type"] == FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_START_PAYLOAD_TYPE
    assert payload["phase"] == "phase30"
    assert payload["transaction_id"] == "runtime_tx_phase30_1"
    assert payload["workflow_id"] == "runtime_tx_phase30_1"
    assert payload["claim_check_ref"] == claim_ref()
    assert payload["artifact_ref"] == "runtime_artifact_0"
    assert payload["delivery_ref"] == "runtime_delivery_0"
    assert payload["execution_mode"] == "local_temporal_stub_activity_orchestration"
    assert payload["execution_digest"].startswith("sha256:")
    assert len(str(payload["execution_digest"]).removeprefix("sha256:")) == 64
    assert payload["activity_sequence"] == EXPECTED_ACTIVITY_SEQUENCE
    assert payload["side_effects"] == []
    assert validate_flowweaver_temporal_stub_activity_start_payload(copy.deepcopy(payload)) == payload
    assert_no_raw_values(payload)


@pytest.mark.asyncio
async def test_phase30_invalid_start_payload_fails_closed_before_temporal_calls() -> None:
    fake_client = FakeTemporalClient()
    result = await start_or_reconcile_flowweaver_temporal_stub_activity_workflow(
        temporal_client=fake_client,
        start_payload={"bad": RAW_PROMPT_VALUE},
        task_queue=FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_TASK_QUEUE,
    )

    assert result == {
        "ok": False,
        "operation": "start_or_reconcile_flowweaver_temporal_stub_activity_workflow",
        "status": "rejected",
        "workflow_id": None,
        "snapshot": None,
        "error_code": "invalid_start_payload",
        "side_effects": [],
    }
    assert fake_client.started is False
    assert fake_client.handles == []
    assert_no_raw_values(result)


@pytest.mark.asyncio
async def test_phase30_local_worker_executes_stub_activities_in_order_and_queries_safe_snapshot() -> None:
    payload = start_payload(transaction_id="runtime_tx_phase30_happy", workflow_id="runtime_tx_phase30_happy")
    env, worker = await open_worker()
    handle = None
    try:
        result = await start_or_reconcile_flowweaver_temporal_stub_activity_workflow(
            temporal_client=env.client,
            start_payload=payload,
            task_queue=FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_TASK_QUEUE,
        )
        assert result["ok"] is True
        assert result["status"] == "started"
        handle = env.client.get_workflow_handle(str(payload["workflow_id"]))
        snapshot = await query_until_status(handle, "stub_sequence_completed")

        assert list(snapshot) == EXPECTED_SNAPSHOT_FIELDS
        assert snapshot["type"] == FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SNAPSHOT_TYPE
        assert snapshot["transaction_id"] == payload["transaction_id"]
        assert snapshot["workflow_id"] == payload["workflow_id"]
        assert snapshot["artifact_refs"] == ["runtime_artifact_0"]
        assert snapshot["delivery_refs"] == ["runtime_delivery_0"]
        assert snapshot["counts"] == {"activities": 3, "artifacts": 1, "deliveries": 1}
        assert snapshot["retry_policy"] == EXPECTED_RETRY_POLICY
        assert snapshot["error_code"] is None
        assert [item["name"] for item in snapshot["activity_sequence"]] == EXPECTED_ACTIVITY_SEQUENCE
        assert [item["status"] for item in snapshot["activity_sequence"]] == ["validated", "stubbed", "planned"]
        assert all(item["side_effects"] == [] for item in snapshot["activity_sequence"])
        assert_no_raw_values(result)
        assert_no_raw_values(snapshot)

        history = await handle.fetch_history()
        history_json, _ = history_text_and_bytes(history)
        assert history_json.index("validate_claim_check_ref") < history_json.index("execute_agent_turn")
        assert history_json.index("execute_agent_turn") < history_json.index("deliver_artifact")
        assert_history_has_no_raw_material(history)
    finally:
        if handle is not None:
            await handle.execute_update(FlowWeaverTemporalStubActivityWorkflow.cancel, "runtime_event_cancel_phase30_happy")
            await handle.result()
        await close_worker(env, worker)


@pytest.mark.asyncio
async def test_phase30_duplicate_start_reconciles_only_after_safe_snapshot_match() -> None:
    payload = start_payload(transaction_id="runtime_tx_phase30_duplicate", workflow_id="runtime_tx_phase30_duplicate")
    env, worker = await open_worker()
    handle = None
    try:
        first = await start_or_reconcile_flowweaver_temporal_stub_activity_workflow(
            temporal_client=env.client,
            start_payload=payload,
            task_queue=FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_TASK_QUEUE,
        )
        second = await start_or_reconcile_flowweaver_temporal_stub_activity_workflow(
            temporal_client=env.client,
            start_payload=copy.deepcopy(payload),
            task_queue=FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_TASK_QUEUE,
        )
        mismatched = start_payload(
            transaction_id="runtime_tx_phase30_duplicate",
            workflow_id="runtime_tx_phase30_duplicate",
            artifact_ref="runtime_artifact_1",
        )
        rejected = await start_or_reconcile_flowweaver_temporal_stub_activity_workflow(
            temporal_client=env.client,
            start_payload=mismatched,
            task_queue=FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_TASK_QUEUE,
        )
        handle = env.client.get_workflow_handle(str(payload["workflow_id"]))
        snapshot = await query_until_status(handle, "stub_sequence_completed")

        assert first["ok"] is True
        assert first["status"] == "started"
        assert second["ok"] is True
        assert second["status"] == "duplicate"
        assert second["snapshot"]["execution_digest"] == payload["execution_digest"]
        assert rejected == {
            "ok": False,
            "operation": "start_or_reconcile_flowweaver_temporal_stub_activity_workflow",
            "status": "rejected",
            "workflow_id": "runtime_tx_phase30_duplicate",
            "snapshot": None,
            "error_code": "duplicate_start_payload_mismatch",
            "side_effects": [],
        }
        assert snapshot["execution_digest"] == payload["execution_digest"]
        assert_no_raw_values(second)
        assert_no_raw_values(rejected)
    finally:
        if handle is not None:
            await handle.execute_update(FlowWeaverTemporalStubActivityWorkflow.cancel, "runtime_event_cancel_phase30_duplicate")
            await handle.result()
        await close_worker(env, worker)


@pytest.mark.asyncio
async def test_phase30_cancel_update_returns_stable_sanitized_snapshot_without_delivery_ack() -> None:
    payload = start_payload(transaction_id="runtime_tx_phase30_cancel", workflow_id="runtime_tx_phase30_cancel")
    env, worker = await open_worker()
    handle = None
    try:
        result = await start_or_reconcile_flowweaver_temporal_stub_activity_workflow(
            temporal_client=env.client,
            start_payload=payload,
            task_queue=FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_TASK_QUEUE,
        )
        assert result["status"] == "started"
        handle = env.client.get_workflow_handle(str(payload["workflow_id"]))
        await query_until_status(handle, "stub_sequence_completed")

        cancelled = await handle.execute_update(
            FlowWeaverTemporalStubActivityWorkflow.cancel,
            "runtime_event_cancel_phase30_cancel",
        )
        final_snapshot = await handle.result()

        assert cancelled["status"] == "cancelled"
        assert final_snapshot["status"] == "cancelled"
        assert final_snapshot["side_effects"] == []
        assert "delivery_ack_updates" not in final_snapshot
        assert_no_raw_values(cancelled)
        assert_no_raw_values(final_snapshot)
        handle = None
    finally:
        if handle is not None:
            await handle.execute_update(FlowWeaverTemporalStubActivityWorkflow.cancel, "runtime_event_cancel_phase30_cleanup")
            await handle.result()
        await close_worker(env, worker)


def test_phase30_report_builder_consumes_phase29_artifacts_and_sanitized_local_run_result() -> None:
    local_result = {
        "ok": True,
        "operation": "start_or_reconcile_flowweaver_temporal_stub_activity_workflow",
        "status": "duplicate",
        "workflow_id": "runtime_tx_phase30_report",
        "snapshot": {
            "type": FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SNAPSHOT_TYPE,
            "version": FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_VERSION,
            "phase": "phase30",
            "transaction_id": "runtime_tx_phase30_report",
            "workflow_id": "runtime_tx_phase30_report",
            "status": "stub_sequence_completed",
            "intent_statuses": {"runtime_intent_0": "stubbed"},
            "artifact_refs": ["runtime_artifact_0"],
            "delivery_refs": ["runtime_delivery_0"],
            "activity_sequence": [
                {"name": "validate_claim_check_ref", "status": "validated", "error_code": None, "side_effects": []},
                {"name": "execute_agent_turn", "status": "stubbed", "error_code": None, "side_effects": []},
                {"name": "deliver_artifact", "status": "planned", "error_code": None, "side_effects": []},
            ],
            "counts": {"activities": 3, "artifacts": 1, "deliveries": 1},
            "execution_digest": "sha256:" + ("b" * 64),
            "retry_policy": EXPECTED_RETRY_POLICY,
            "error_code": None,
            "side_effects": [],
        },
        "error_code": None,
        "side_effects": [],
    }

    report = build_flowweaver_temporal_stub_activity_orchestration_report(
        implementation_descriptor=describe_flowweaver_stub_activity_implementation_contract(),
        implementation_report=p29_report(),
        local_run_result=local_result,
    )

    assert list(report) == EXPECTED_REPORT_FIELDS
    assert report["type"] == FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_REPORT_TYPE
    assert report["verdict"] == FLOWWEAVER_TEMPORAL_STUB_ACTIVITY_ORCHESTRATION_SUCCESS_VERDICT
    assert report["phase29_verdict"] == FLOWWEAVER_STUB_ACTIVITY_IMPLEMENTATION_SUCCESS_VERDICT
    assert report["workflow"] == "FlowWeaverTemporalStubActivityWorkflow"
    assert report["activity_sequence"] == EXPECTED_ACTIVITY_SEQUENCE
    assert report["local_run_status"] == "duplicate"
    assert report["history_no_leak_checked"] is True
    assert report["snapshot_no_leak_checked"] is True
    assert report["duplicate_start_reconciled"] is True
    assert report["checks"] == {key: True for key in EXPECTED_CHECKS}
    assert report["error_code"] is None
    assert report["side_effects"] == []
    assert validate_flowweaver_temporal_stub_activity_orchestration_report(copy.deepcopy(report)) == report


def test_phase30_source_allows_temporal_wrappers_but_not_gateway_worker_lifecycle_or_live_effects() -> None:
    source = MODULE_SOURCE.read_text()
    tree = ast.parse(source)

    assert source.count("@activity.defn") == 3
    assert source.count("workflow.execute_activity") == 3
    assert "@workflow.defn" in source
    assert "@workflow.query" in source
    assert "@workflow.update" in source
    assert "WorkflowEnvironment" not in source
    assert "from temporalio.worker import Worker" not in source
    assert "Worker(" not in source
    assert "Client.connect" not in source
    assert "gateway.run" not in source
    assert "gateway.platforms" not in source
    assert "run_agent" not in source
    assert "AIAgent" not in source
    assert "model_tools" not in source
    assert "toolsets" not in source
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


def test_phase30_changed_file_guard_allows_only_temporal_stub_orchestration_files_and_guard_maintenance() -> None:
    changed = _changed_files()
    allowed = {
        "gateway/flowweaver_temporal_stub_activity_orchestration.py",
        "tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py",
        "docs/runbooks/flowweaver-temporal-stub-activity-orchestration.md",
        "docs/plans/2026-05-09-flowweaver-phase30-temporal-stub-activity-orchestration.md",
        "docs/dev_log/2026-05-09-flowweaver-phase30-temporal-stub-activity-orchestration.md",
        "tests/gateway/test_flowweaver_stub_activity_orchestration.py",
        "tests/gateway/test_flowweaver_stub_activity_orchestration_validation.py",
        "tests/gateway/test_flowweaver_stub_activity_boundary_contract.py",
        "tests/gateway/test_flowweaver_stub_activity_boundary_contract_validation.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation_design.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation_validation.py",
        "tests/gateway/test_flowweaver_stub_activity_implementation.py",
        "tests/gateway/test_flowweaver_temporal_observation_bridge.py",
        "tests/gateway/test_flowweaver_temporal_observation_validation_gate.py",
        "tests/gateway/test_flowweaver_production_shadow_observation.py",
        "tests/gateway/test_flowweaver_shadow_publisher.py",
        "gateway/flowweaver_agent_execution_activity.py",
        "tests/gateway/test_flowweaver_agent_execution_activity.py",
        "tests/integration/test_flowweaver_phase31_agent_execution_activity.py",
        "docs/runbooks/flowweaver-agent-execution-activity.md",
        "docs/plans/2026-05-09-flowweaver-phase31-agent-execution-activity.md",
        "docs/dev_log/2026-05-09-flowweaver-phase31-agent-execution-activity.md",
        "gateway/flowweaver_delivery_activity.py",
        "tests/gateway/test_flowweaver_delivery_activity.py",
        "tests/integration/test_flowweaver_phase32_delivery_activity_ack_reconciliation.py",
        "docs/runbooks/flowweaver-delivery-activity-ack-reconciliation.md",
        "docs/plans/2026-05-09-flowweaver-phase32-delivery-activity-ack-reconciliation.md",
        "docs/dev_log/2026-05-09-flowweaver-phase32-delivery-activity-ack-reconciliation.md",
    }
    forbidden_exact = {"run_agent.py", "model_tools.py", "toolsets.py", "mcp_serve.py", "gateway/run.py"}
    forbidden_prefixes = ("gateway/platforms/", "tools/", "hermes_cli/", "prototypes/")

    assert changed <= allowed
    assert not (changed & forbidden_exact)
    assert not any(path.startswith(forbidden_prefixes) for path in changed)
    assert PLAN_DOC.exists()
    assert DEV_LOG.exists()
    assert RUNBOOK.exists()
