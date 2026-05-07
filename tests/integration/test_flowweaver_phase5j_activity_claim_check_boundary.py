"""RED integration/source tests for FlowWeaver Phase 5J Activity boundaries."""

from __future__ import annotations

import ast
import asyncio
import importlib
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker


ROOT = Path(__file__).resolve().parents[2]
PHASE5B_SRC = ROOT / "prototypes" / "flowweaver_phase5b_temporal_poc" / "src"
PHASE5C_SRC = ROOT / "prototypes" / "flowweaver_phase5c_runtime_client" / "src"
WORKFLOW_SOURCE = PHASE5B_SRC / "flowweaver_temporal_poc" / "workflows.py"
ACTIVITY_SOURCE = PHASE5B_SRC / "flowweaver_temporal_poc" / "activities.py"
for path in (PHASE5C_SRC, PHASE5B_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from flowweaver_temporal_poc import FLOWWEAVER_TEMPORAL_TASK_QUEUE  # noqa: E402
from flowweaver_temporal_poc.payloads import (  # noqa: E402
    CancelTransactionUpdate,
    RuntimeStartPayload,
    build_runtime_start_payload,
)
from flowweaver_temporal_poc.workflows import FlowWeaverTransactionWorkflow  # noqa: E402


pytestmark = pytest.mark.integration

ACTIVITY_BOUNDARY_TYPE = "flowweaver.temporal_poc.activity_boundary.v0"
EXPECTED_ACTIVITY_NAMES = ("validate_claim_check_ref", "execute_agent_turn", "deliver_artifact")
EXPECTED_ACTIVITY_BOUNDARY = {
    "type": ACTIVITY_BOUNDARY_TYPE,
    "version": "flowweaver.temporal_poc.v0",
    "status": "completed",
    "activities": {
        "validate_claim_check_ref": "validated",
        "execute_agent_turn": "completed",
        "deliver_artifact": "planned",
    },
    "refs": {
        "input_ref": "claim_ref_phase5j_start",
        "artifact_ref": "claim_ref_phase5j_artifact_0",
        "delivery_ref": "claim_ref_phase5j_delivery_0",
    },
    "side_effects": [],
}
FORBIDDEN_ACTIVITY_MATERIAL = (
    "raw_snapshot",
    "raw_capture",
    "full_agent_result",
    "raw_" + "prompt",
    "raw_" + "command",
    "stdout",
    "stderr",
    "tool_" + "output",
    "card_" + "json",
    "media_" + "bytes",
    "media_" + "path",
    "platform_" + "payload",
    "platform_" + "id",
    "chat_" + "id",
    "user_" + "id",
    "message_" + "id",
    "delivery_ack_" + "payload",
    "credential",
    "to" + "ken",
    "se" + "cret",
    "om_" + "phase5j_private_message",
    "oc_" + "phase5j_private_chat",
    "ou_" + "phase5j_private_user",
    "unsafe-" + "to" + "ken" + "-phase5j",
)


def make_start_payload(*, transaction_id: str, count: int = 1) -> RuntimeStartPayload:
    idempotency_suffix = transaction_id.removeprefix("runtime_tx_")
    return build_runtime_start_payload(
        transaction_id=transaction_id,
        idempotency_key="runtime_event_start_" + idempotency_suffix,
        entry_count=count,
        record_counts={"transactions": 1, "intents": count, "artifacts": count, "deliveries": count},
        allowed_runtime_events=(
            "start_transaction",
            "record_operation",
            "publish_artifact",
            "plan_delivery",
            "record_delivery_ack",
            "approve_intent",
            "reject_intent",
            "cancel_transaction",
            "resume_after_user_input",
        ),
        claim_check_policy={
            "mode": "references_only",
            "allowed_reference_fields": ("ref", "kind", "count", "size", "checksum_hint"),
            "forbidden_material": (
                "raw_snapshot",
                "raw_capture",
                "full_agent_result",
                "raw_prompt",
                "raw_command",
                "stdout",
                "stderr",
                "tool_output",
                "card_json",
                "media_bytes",
                "media_path",
                "platform_payload",
                "platform_id",
                "chat_id",
                "user_id",
                "message_id",
                "delivery_ack_payload",
                "credential",
                "to" + "ken",
                "se" + "cret",
            ),
        },
    )


def phase5j_activity_functions() -> list[object]:
    activities = importlib.import_module("flowweaver_temporal_poc.activities")
    return [getattr(activities, name) for name in EXPECTED_ACTIVITY_NAMES]


async def open_phase5j_worker() -> tuple[WorkflowEnvironment, Worker]:
    activities = phase5j_activity_functions()
    env = await WorkflowEnvironment.start_time_skipping()
    worker = Worker(
        env.client,
        task_queue=FLOWWEAVER_TEMPORAL_TASK_QUEUE,
        workflows=[FlowWeaverTransactionWorkflow],
        activities=activities,
    )
    await env.__aenter__()
    await worker.__aenter__()
    return env, worker


async def close_phase5j_worker(env: WorkflowEnvironment, worker: Worker) -> None:
    await worker.__aexit__(None, None, None)
    await env.__aexit__(None, None, None)


async def start_phase5j_workflow(env: WorkflowEnvironment, *, workflow_id: str):
    return await env.client.start_workflow(
        FlowWeaverTransactionWorkflow.run,
        make_start_payload(transaction_id=workflow_id, count=1),
        id=workflow_id,
        task_queue=FLOWWEAVER_TEMPORAL_TASK_QUEUE,
    )


async def query_until_activity_boundary_completed(handle: Any) -> dict[str, object]:
    last_error: Exception | None = None
    last_snapshot: dict[str, object] | None = None
    for _ in range(40):
        try:
            snapshot = await handle.query(FlowWeaverTransactionWorkflow.query_snapshot)
        except Exception as exc:  # Temporal can reject queries before the first workflow task completes.
            last_error = exc
            await asyncio.sleep(0.05)
            continue
        if type(snapshot) is dict:
            last_snapshot = snapshot
            activity_boundary = snapshot.get("activity_boundary")
            if type(activity_boundary) is dict and activity_boundary.get("status") == "completed":
                return snapshot
        await asyncio.sleep(0.05)
    if last_error is not None and last_snapshot is None:
        raise last_error
    raise AssertionError(f"workflow did not expose completed Phase 5J activity_boundary: {last_snapshot!r}")


async def cancel_if_running(handle: Any, *, event_id: str) -> None:
    with suppress(Exception):
        await handle.execute_update(
            FlowWeaverTransactionWorkflow.cancel_transaction,
            CancelTransactionUpdate(event_id=event_id, reason_ref=None),
        )
    with suppress(Exception):
        await handle.result()


def history_text_and_bytes(history: Any) -> tuple[str, bytes]:
    rendered = history.to_json() if hasattr(history, "to_json") else repr(history.to_json_dict())
    raw_events = b"".join(event.SerializeToString() for event in history.events)
    return rendered, raw_events


def assert_no_forbidden_activity_material(value: object) -> None:
    rendered = repr(value).lower()
    for marker in FORBIDDEN_ACTIVITY_MATERIAL:
        assert marker.lower() not in rendered


def test_phase5j_diff_does_not_add_gateway_wiring_or_real_activity_side_effects() -> None:
    changed_files = _changed_files()
    allowed_changed_files = {
        "docs/dev_log/2026-05-06-flowweaver-phase5j-activity-claim-check-boundary.md",
        "docs/plans/2026-05-06-flowweaver-phase5j-activity-claim-check-boundary.md",
        "docs/dev_log/2026-05-07-flowweaver-phase5k-runtime-control-surface.md",
        "docs/plans/2026-05-07-flowweaver-phase5k-runtime-control-surface.md",
        "docs/dev_log/2026-05-07-flowweaver-phase6-gateway-ack-shadow-bridge.md",
        "docs/plans/2026-05-07-flowweaver-phase6-gateway-ack-shadow-bridge.md",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/control_surface.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/mcp_control_server.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/gateway_ack_shadow_bridge.py",
        "tests/integration/test_flowweaver_phase5k_runtime_control_surface.py",
        "tests/integration/test_flowweaver_phase6_gateway_ack_shadow_bridge.py",
        "tests/prototypes/test_flowweaver_phase5k_runtime_control_surface.py",
        "tests/prototypes/test_flowweaver_phase5k_mcp_control_surface.py",
        "tests/prototypes/test_flowweaver_phase6_gateway_ack_shadow_bridge.py",
        "prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/activities.py",
        "prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py",
        "prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py",
        "tests/integration/test_flowweaver_phase5b_temporal_workflow.py",
        "tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py",
        "tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py",
        "tests/integration/test_flowweaver_phase5i_start_signature_parity.py",
        "tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py",
        "tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py",
        "tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py",
        "tests/prototypes/test_flowweaver_phase5j_activity_contract.py",
        "docs/dev_log/2026-05-07-flowweaver-phase7-gateway-shadow-e2e-loop.md",
        "docs/plans/2026-05-07-flowweaver-phase7-gateway-shadow-e2e-loop.md",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/gateway_shadow_e2e_loop.py",
        "tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py",
        "tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py",
    }
    forbidden_prefixes = (
        "gateway/run.py",
        "gateway/platforms/",
        "tools/",
        "hermes_cli/",
    )
    forbidden_exact = {"pyproject.toml", "run_agent.py", "model_tools.py", "toolsets.py"}

    unexpected = sorted(changed_files - allowed_changed_files)
    assert unexpected == []
    assert not [path for path in changed_files if path in forbidden_exact or path.startswith(forbidden_prefixes)]

    assert ACTIVITY_SOURCE.exists(), "Phase 5J must add prototype-only stub Activities"
    activity_source = ACTIVITY_SOURCE.read_text(encoding="utf-8")
    activity_tree = ast.parse(activity_source)

    forbidden_activity_import_roots = {
        "gateway",
        "tools",
        "model_tools",
        "toolsets",
        "run_agent",
        "pathlib",
        "os",
        "socket",
        "subprocess",
        "requests",
        "httpx",
        "aiohttp",
        "logging",
    }
    forbidden_activity_call_names = {
        "open",
        "print",
        "read_text",
        "read_bytes",
        "write_text",
        "write_bytes",
        "system",
        "popen",
        "run",
        "check_call",
        "check_output",
        "getLogger",
        "debug",
        "info",
        "warning",
        "error",
        "exception",
    }
    for node in ast.walk(activity_tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden_activity_import_roots
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in forbidden_activity_import_roots
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_activity_call_names
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_activity_call_names

    forbidden_activity_source_markers = (
        "gateway.",
        "gateway.run",
        "gateway.platforms",
        "tools.registry",
        "logger.",
        "logging.",
        "requests.",
        "httpx.",
        "aiohttp.",
        "socket.",
        "subprocess.",
        "open(",
        "print(",
        "raise ValueError(f",
        "raise RuntimeError(f",
        "str(exc)",
        "repr(exc)",
    )
    lowered_activity_source = activity_source.lower()
    assert not [marker for marker in forbidden_activity_source_markers if marker.lower() in lowered_activity_source]

    implementation_changed_files = [
        path for path in changed_files if path.startswith("prototypes/flowweaver_phase5") and path.endswith(".py")
    ]
    forbidden_lifecycle_markers = (
        "@workflow.signal",
        ".signal(",
        "signal_with_start",
        "docker",
        "systemctl",
        "daemon",
        "~/.hermes/config.yaml",
        "config.yaml",
    )
    forbidden_added_patterns = (
        "sk-",
        "api_key=",
        "api_key =",
        "password=",
        "password =",
        "secret=",
        "secret =",
        "token=",
        "token =",
        "om_phase5",
        "oc_phase5",
        "ou_phase5",
        "om_9",
        "oc_4",
        "ou_9",
    )
    added_lines = _added_lines_for_files(implementation_changed_files)
    for line in added_lines:
        lowered = line.lower()
        assert not [marker for marker in forbidden_lifecycle_markers if marker in lowered]
        assert not [marker for marker in forbidden_added_patterns if marker in lowered]


@pytest.mark.asyncio
async def test_phase5j_real_worker_executes_stub_activity_boundary_and_exposes_safe_snapshot_summary() -> None:
    env, worker = await open_phase5j_worker()
    handle = await start_phase5j_workflow(env, workflow_id="runtime_tx_phase5j_worker_boundary")
    try:
        snapshot = await query_until_activity_boundary_completed(handle)

        assert snapshot["activity_boundary"] == EXPECTED_ACTIVITY_BOUNDARY
        assert snapshot["side_effects"] == []
        assert_no_forbidden_activity_material(snapshot)
    finally:
        await cancel_if_running(handle, event_id="runtime_event_cancel_phase5j_worker_boundary")
        await close_phase5j_worker(env, worker)


@pytest.mark.asyncio
async def test_phase5j_real_worker_history_omits_raw_activity_material_after_activity_boundary_and_cancel() -> None:
    env, worker = await open_phase5j_worker()
    workflow_id = "runtime_tx_phase5j_history_boundary"
    handle = await start_phase5j_workflow(env, workflow_id=workflow_id)
    try:
        snapshot = await query_until_activity_boundary_completed(handle)
        await cancel_if_running(handle, event_id="runtime_event_cancel_phase5j_history_boundary")
        history = await handle.fetch_history()
        rendered, raw_events = history_text_and_bytes(history)

        assert snapshot["activity_boundary"] == EXPECTED_ACTIVITY_BOUNDARY
        assert "activity_boundary" in rendered
        for activity_name in EXPECTED_ACTIVITY_NAMES:
            assert activity_name in rendered
        for marker in FORBIDDEN_ACTIVITY_MATERIAL:
            assert marker.lower() not in rendered.lower()
            assert marker.lower().encode() not in raw_events.lower()
    finally:
        await cancel_if_running(handle, event_id="runtime_event_cancel_phase5j_history_boundary_cleanup")
        await close_phase5j_worker(env, worker)


def test_phase5j_activity_input_validators_reject_raw_markers_before_scheduling() -> None:
    from flowweaver_temporal_poc.payloads import (  # noqa: PLC0415
        AgentTurnActivityInput,
        validate_agent_turn_activity_input,
    )

    unsafe_input = AgentTurnActivityInput(
        event_id="runtime_event_phase5j_" + "raw_" + "prompt",
        intent_id="runtime_intent_0",
        input_ref="claim_ref_phase5j_start",
        output_artifact_id="runtime_artifact_0",
        output_artifact_ref="claim_ref_phase5j_artifact_0",
    )

    with pytest.raises(ValueError) as exc_info:
        validate_agent_turn_activity_input(unsafe_input)
    assert str(exc_info.value) in {"invalid_activity_input", "unsafe_tool_output"}
    assert_no_forbidden_activity_material(str(exc_info.value))


def test_phase5j_workflow_source_uses_execute_activity_but_not_gateway_tools_filesystem_network_or_logging() -> None:
    source = WORKFLOW_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    execute_calls = _execute_activity_calls(tree)

    assert [_activity_name_from_execute_call(call) for call in execute_calls] == list(EXPECTED_ACTIVITY_NAMES)
    assert all(any(keyword.arg == "start_to_close_timeout" for keyword in call.keywords) for call in execute_calls)

    forbidden_import_roots = {
        "gateway",
        "tools",
        "model_tools",
        "toolsets",
        "run_agent",
        "pathlib",
        "os",
        "socket",
        "subprocess",
        "requests",
        "httpx",
        "aiohttp",
        "logging",
    }
    forbidden_call_names = {
        "open",
        "print",
        "read_text",
        "read_bytes",
        "write_text",
        "write_bytes",
        "system",
        "popen",
        "getLogger",
        "debug",
        "info",
        "warning",
        "error",
        "exception",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden_import_roots
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in forbidden_import_roots
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_call_names
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_call_names

    forbidden_source_markers = (
        "gateway.",
        "gateway.run",
        "gateway.platforms",
        "tools.registry",
        "logger.",
        "logging.",
        "requests.",
        "httpx.",
        "aiohttp.",
        "socket.",
        "subprocess.",
        "open(",
        "print(",
    )
    lowered_source = source.lower()
    assert not [marker for marker in forbidden_source_markers if marker in lowered_source]


def test_phase5j_workflow_source_validates_activity_inputs_immediately_before_execute_activity() -> None:
    tree = ast.parse(WORKFLOW_SOURCE.read_text(encoding="utf-8"))
    execute_statements = _workflow_execute_activity_statement_contexts(tree)

    assert execute_statements, "FlowWeaverTransactionWorkflow must call workflow.execute_activity for Phase 5J stubs"
    assert [_activity_name_from_execute_call(call) for _, _, call, _ in execute_statements] == list(EXPECTED_ACTIVITY_NAMES)

    expected_validators = {
        "validate_claim_check_ref": {"validate_claim_check_ref_validation_input", "validate_claim_check_ref_activity_input"},
        "execute_agent_turn": {"validate_agent_turn_activity_input"},
        "deliver_artifact": {"validate_deliver_artifact_activity_input"},
    }
    expected_payload_builders = {
        "validate_claim_check_ref": {"ClaimCheckRefValidationInput", "build_claim_check_ref_validation_input"},
        "execute_agent_turn": {"AgentTurnActivityInput", "build_agent_turn_activity_input"},
        "deliver_artifact": {"DeliverArtifactActivityInput", "build_deliver_artifact_activity_input"},
    }
    for method_name, statement_index, call, sibling_statements in execute_statements:
        activity_name = _activity_name_from_execute_call(call)
        assert activity_name in expected_validators
        assert statement_index > 0, f"{activity_name} in {method_name} must be validated before scheduling"
        previous_statement = sibling_statements[statement_index - 1]
        previous_statement_calls = _called_function_names(previous_statement)
        matched_validators = previous_statement_calls & expected_validators[activity_name]
        assert matched_validators, (
            f"{activity_name} in {method_name} must call one of {sorted(expected_validators[activity_name])} "
            "in the statement immediately before workflow.execute_activity"
        )

        activity_payload = _activity_payload_argument(call)
        assert activity_payload is not None, f"{activity_name} must schedule exactly one validated payload object"
        validator_payloads = _validator_payload_arguments(previous_statement, expected_validators[activity_name])
        assert ast.dump(activity_payload) in {ast.dump(payload) for payload in validator_payloads}, (
            f"{activity_name} in {method_name} must validate the same payload object it schedules"
        )

        if isinstance(activity_payload, ast.Name):
            builder_names = _assignment_builder_names(
                sibling_statements[:statement_index],
                target_name=activity_payload.id,
            )
            assert builder_names & expected_payload_builders[activity_name], (
                f"{activity_name} in {method_name} must schedule payloads built by one of "
                f"{sorted(expected_payload_builders[activity_name])}"
            )


def _execute_activity_calls(tree: ast.AST) -> list[ast.Call]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call) and _is_execute_activity_call(node)]


def _is_execute_activity_call(call: ast.Call) -> bool:
    return (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "execute_activity"
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "workflow"
    )


def _activity_name_from_execute_call(call: ast.Call) -> str | None:
    activity_node = call.args[0] if call.args else next(
        (keyword.value for keyword in call.keywords if keyword.arg == "activity"),
        None,
    )
    if isinstance(activity_node, ast.Name):
        return activity_node.id
    if isinstance(activity_node, ast.Attribute):
        return activity_node.attr
    if isinstance(activity_node, ast.Constant) and type(activity_node.value) is str:
        return activity_node.value
    return None


def _workflow_execute_activity_statement_contexts(tree: ast.AST) -> list[tuple[str, int, ast.Call, list[ast.stmt]]]:
    class_node = _workflow_class(tree)
    parent_by_id: dict[int, ast.AST] = {}
    for node in ast.walk(class_node):
        for child in ast.iter_child_nodes(node):
            parent_by_id[id(child)] = node

    statement_context_by_id: dict[int, tuple[str, int, list[ast.stmt]]] = {}
    for node in class_node.body:
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
            _collect_statement_contexts(node.body, method_name=node.name, contexts=statement_context_by_id)

    contexts: list[tuple[str, int, ast.Call, list[ast.stmt]]] = []
    for call in ast.walk(class_node):
        if not isinstance(call, ast.Call) or not _is_execute_activity_call(call):
            continue
        ancestor: ast.AST | None = call
        while ancestor is not None and id(ancestor) not in statement_context_by_id:
            ancestor = parent_by_id.get(id(ancestor))
        if ancestor is None:
            raise AssertionError("workflow.execute_activity call is not enclosed by a workflow statement")
        method_name, statement_index, sibling_statements = statement_context_by_id[id(ancestor)]
        contexts.append((method_name, statement_index, call, sibling_statements))
    return contexts


def _workflow_class(tree: ast.AST) -> ast.ClassDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "FlowWeaverTransactionWorkflow":
            return node
    raise AssertionError("FlowWeaverTransactionWorkflow was not found")


def _collect_statement_contexts(
    statements: list[ast.stmt],
    *,
    method_name: str,
    contexts: dict[int, tuple[str, int, list[ast.stmt]]],
) -> None:
    for index, statement in enumerate(statements):
        contexts[id(statement)] = (method_name, index, statements)
        for _field_name, value in ast.iter_fields(statement):
            if isinstance(value, list):
                if all(isinstance(item, ast.stmt) for item in value):
                    _collect_statement_contexts(value, method_name=method_name, contexts=contexts)
                else:
                    for item in value:
                        if isinstance(item, ast.AST):
                            _collect_nested_statement_contexts(item, method_name=method_name, contexts=contexts)
            elif isinstance(value, ast.AST):
                _collect_nested_statement_contexts(value, method_name=method_name, contexts=contexts)


def _collect_nested_statement_contexts(
    node: ast.AST,
    *,
    method_name: str,
    contexts: dict[int, tuple[str, int, list[ast.stmt]]],
) -> None:
    for _field_name, value in ast.iter_fields(node):
        if isinstance(value, list):
            if all(isinstance(item, ast.stmt) for item in value):
                _collect_statement_contexts(value, method_name=method_name, contexts=contexts)
            else:
                for item in value:
                    if isinstance(item, ast.AST):
                        _collect_nested_statement_contexts(item, method_name=method_name, contexts=contexts)
        elif isinstance(value, ast.AST):
            _collect_nested_statement_contexts(value, method_name=method_name, contexts=contexts)


def _changed_files() -> set[str]:
    changed: set[str] = set()
    base = _phase5j_merge_base()
    diff_commands: list[tuple[str, ...]] = []
    if base:
        diff_commands.append(("diff", "--name-only", base, "HEAD"))
    diff_commands.extend(
        (
            ("diff", "--name-only"),
            ("diff", "--cached", "--name-only"),
            ("ls-files", "--others", "--exclude-standard"),
        )
    )
    for args in diff_commands:
        completed = subprocess.run(
            ("git", *args),
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        changed.update(line for line in completed.stdout.splitlines() if line)
    return changed


def _phase5j_merge_base() -> str | None:
    for base_ref in ("@{upstream}", "origin/feature/sachima-channel"):
        completed = subprocess.run(
            ("git", "merge-base", "HEAD", base_ref),
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            return completed.stdout.strip()
    return None


def _added_lines_for_files(relative_paths: list[str]) -> list[str]:
    if not relative_paths:
        return []

    tracked_paths = [path for path in relative_paths if (ROOT / path).exists()]
    added: list[str] = []
    base = _phase5j_merge_base()
    diff_commands: list[tuple[str, ...]] = []
    if base:
        diff_commands.append(("diff", "--unified=0", base, "HEAD", "--", *tracked_paths))
    diff_commands.extend(
        (
            ("diff", "--unified=0", "--", *tracked_paths),
            ("diff", "--cached", "--unified=0", "--", *tracked_paths),
        )
    )
    for args in diff_commands:
        completed = subprocess.run(
            ("git", *args),
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        added.extend(_parse_added_diff_lines(completed.stdout))

    untracked = _git_lines(("ls-files", "--others", "--exclude-standard", "--", *tracked_paths))
    for relative_path in untracked:
        added.extend((ROOT / relative_path).read_text(encoding="utf-8").splitlines())
    return added


def _git_lines(args: tuple[str, ...]) -> list[str]:
    completed = subprocess.run(
        ("git", *args),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in completed.stdout.splitlines() if line]


def _parse_added_diff_lines(diff_text: str) -> list[str]:
    return [
        line[1:]
        for line in diff_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]


def _activity_payload_argument(call: ast.Call) -> ast.AST | None:
    if len(call.args) >= 2:
        return call.args[1]
    for keyword in call.keywords:
        if keyword.arg == "arg":
            return keyword.value
        if keyword.arg == "args" and isinstance(keyword.value, ast.List) and keyword.value.elts:
            return keyword.value.elts[0]
    return None


def _validator_payload_arguments(statement: ast.stmt, validator_names: set[str]) -> list[ast.AST]:
    payloads: list[ast.AST] = []
    for node in ast.walk(statement):
        if not isinstance(node, ast.Call):
            continue
        call_name = _call_name(node)
        if call_name not in validator_names:
            continue
        if node.args:
            payloads.append(node.args[0])
        else:
            payloads.extend(keyword.value for keyword in node.keywords if keyword.arg in {"payload", "value"})
    return payloads


def _assignment_builder_names(statements: list[ast.stmt], *, target_name: str) -> set[str]:
    builder_names: set[str] = set()
    for statement in statements:
        for node in ast.walk(statement):
            if isinstance(node, ast.Assign) and any(_target_has_name(target, target_name) for target in node.targets):
                builder_names.update(_called_function_names(node))
            elif isinstance(node, ast.AnnAssign) and _target_has_name(node.target, target_name):
                builder_names.update(_called_function_names(node))
    return builder_names


def _target_has_name(target: ast.AST, expected: str) -> bool:
    return isinstance(target, ast.Name) and target.id == expected


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _called_function_names(statement: ast.stmt) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(statement):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


