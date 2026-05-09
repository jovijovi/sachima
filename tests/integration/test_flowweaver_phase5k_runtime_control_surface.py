"""RED integration/source tests for FlowWeaver Phase 5K runtime control surface."""

from __future__ import annotations

import ast
import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

ROOT = Path(__file__).resolve().parents[2]
PHASE5B_SRC = ROOT / "prototypes" / "flowweaver_phase5b_temporal_poc" / "src"
PHASE5C_SRC = ROOT / "prototypes" / "flowweaver_phase5c_runtime_client" / "src"
CONTROL_SOURCE = PHASE5C_SRC / "flowweaver_runtime_client" / "control_surface.py"
MCP_CONTROL_SOURCE = PHASE5C_SRC / "flowweaver_runtime_client" / "mcp_control_server.py"
WORKFLOW_SOURCE = PHASE5B_SRC / "flowweaver_temporal_poc" / "workflows.py"
for path in (PHASE5C_SRC, PHASE5B_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from flowweaver_temporal_poc import FLOWWEAVER_TEMPORAL_TASK_QUEUE  # noqa: E402
from flowweaver_temporal_poc.activities import deliver_artifact, execute_agent_turn, validate_claim_check_ref  # noqa: E402
from flowweaver_temporal_poc.workflows import FlowWeaverTransactionWorkflow  # noqa: E402
from flowweaver_runtime_client.runtime_client import FlowWeaverRuntimeClient  # noqa: E402

pytestmark = pytest.mark.integration

PRIVATE_CHAT_ID = "oc_" + "phase5k_private_chat"
PRIVATE_USER_ID = "ou_" + "phase5k_private_user"
SENSITIVE_SENTINEL = "unsafe-" + "token" + "-phase5k"
FORBIDDEN_SENTINELS = (PRIVATE_CHAT_ID, PRIVATE_USER_ID, SENSITIVE_SENTINEL)


def make_start_fields(*, workflow_id: str, count: int = 1) -> dict[str, object]:
    suffix = workflow_id.removeprefix("runtime_tx_")
    return {
        "transaction_id": workflow_id,
        "idempotency_key": "runtime_event_start_" + suffix,
        "entry_count": count,
        "record_counts": {"transactions": 1, "intents": count, "artifacts": count, "deliveries": count},
        "allowed_runtime_events": [
            "start_transaction",
            "record_operation",
            "publish_artifact",
            "plan_delivery",
            "record_delivery_ack",
            "approve_intent",
            "reject_intent",
            "cancel_transaction",
            "resume_after_user_input",
        ],
        "claim_check_policy": {
            "mode": "references_only",
            "allowed_reference_fields": ["ref", "kind", "count", "size", "checksum_hint"],
            "forbidden_material": [
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
                "token",
                "secret",
            ],
        },
    }


async def open_real_worker() -> tuple[WorkflowEnvironment, Worker, FlowWeaverRuntimeClient]:
    env = await WorkflowEnvironment.start_time_skipping()
    worker = Worker(
        env.client,
        task_queue=FLOWWEAVER_TEMPORAL_TASK_QUEUE,
        workflows=[FlowWeaverTransactionWorkflow],
        activities=[validate_claim_check_ref, execute_agent_turn, deliver_artifact],
    )
    await env.__aenter__()
    await worker.__aenter__()
    return env, worker, FlowWeaverRuntimeClient(env.client, temporal_address="localhost:7233")


async def close_real_worker(env: WorkflowEnvironment, worker: Worker) -> None:
    await worker.__aexit__(None, None, None)
    await env.__aexit__(None, None, None)


async def query_until_running(
    control: Any, workflow_id: str, *, require_activity_boundary: bool = False
) -> dict[str, object]:
    last: dict[str, object] | None = None
    for _ in range(40):
        result = await control.handle({"operation": "query_transaction", "workflow_id": workflow_id})
        if result.get("ok") is True:
            snapshot = result.get("snapshot")
            if type(snapshot) is dict and snapshot.get("status") == "running":
                activity_boundary = snapshot.get("activity_boundary")
                if not require_activity_boundary or (
                    type(activity_boundary) is dict and activity_boundary.get("status") == "completed"
                ):
                    return result
        last = result
        await asyncio.sleep(0.05)
    raise AssertionError(f"workflow did not reach running through control surface: {last!r}")


def history_text_and_bytes(history: Any) -> tuple[str, bytes]:
    rendered = history.to_json() if hasattr(history, "to_json") else repr(history.to_json_dict())
    raw_events = b"".join(event.SerializeToString() for event in history.events)
    return rendered, raw_events


def assert_no_forbidden_material(value: object) -> None:
    rendered = repr(value).lower()
    for forbidden in FORBIDDEN_SENTINELS:
        assert forbidden.lower() not in rendered
    assert "raw_prompt" not in rendered
    assert "platform_payload" not in rendered
    assert "workflowalreadystartederror" not in rendered


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _changed_files() -> set[str]:
    base = _phase_diff_base()
    committed = set(_git("diff", "--name-only", f"{base}..HEAD").splitlines())
    worktree = set(_git("diff", "--name-only").splitlines())
    cached = set(_git("diff", "--cached", "--name-only").splitlines())
    untracked = set(_git("ls-files", "--others", "--exclude-standard").splitlines())
    return {name for name in committed | worktree | cached | untracked if name}


def _phase_diff_base() -> str:
    parents = _git("rev-list", "--parents", "-n", "1", "HEAD").split()
    if len(parents) > 2:
        return "HEAD"
    return _git("merge-base", "HEAD", "origin/feature/sachima-channel")


@pytest.mark.asyncio
async def test_phase5k_control_surface_drives_real_local_temporal_worker_without_history_leaks() -> None:
    from flowweaver_runtime_client.control_surface import FlowWeaverRuntimeControlSurface

    env, worker, facade = await open_real_worker()
    workflow_id = "runtime_tx_phase5k_integration"
    control = FlowWeaverRuntimeControlSurface(facade)
    try:
        started = await control.handle(
            {"operation": "start_transaction", "workflow_id": workflow_id, "start_payload": make_start_fields(workflow_id=workflow_id)}
        )
        duplicate = await control.handle(
            {"operation": "start_transaction", "workflow_id": workflow_id, "start_payload": make_start_fields(workflow_id=workflow_id)}
        )
        snapshot_result = await query_until_running(control, workflow_id, require_activity_boundary=True)
        ack = await control.handle(
            {
                "operation": "reconcile_delivery_ack",
                "workflow_id": workflow_id,
                "update": {
                    "event_type": "record_delivery_ack",
                    "delivery_key": "runtime_event_delivery_ack_phase5k_integration",
                    "surface": "final_text",
                    "target_kind": "delivery",
                    "target_id": "runtime_delivery_0",
                    "status": "sent",
                },
            }
        )
        canceled = await control.handle(
            {
                "operation": "cancel_transaction",
                "workflow_id": workflow_id,
                "update": {"event_type": "cancel_transaction", "event_id": "runtime_event_cancel_phase5k_integration"},
            }
        )
        result = await env.client.get_workflow_handle(workflow_id).result()
        history = await env.client.get_workflow_handle(workflow_id).fetch_history()
        rendered, raw_events = history_text_and_bytes(history)

        assert started["operation"] == "start_transaction"
        assert started["runtime_operation"] == "start_transaction"
        assert duplicate["ok"] is True
        assert duplicate["runtime_operation"] == "start_transaction"
        assert duplicate["status"] == "running"
        assert snapshot_result["operation"] == "query_transaction"
        assert snapshot_result["runtime_operation"] == "query_snapshot"
        assert snapshot_result["snapshot"]["activity_boundary"]["status"] == "completed"
        assert ack["operation"] == "reconcile_delivery_ack"
        assert ack["runtime_operation"] == "record_delivery_ack"
        assert ack["status"] == "applied"
        assert canceled["snapshot"]["status"] == "canceled"
        assert result["status"] == "canceled"
        for value in (started, duplicate, snapshot_result, ack, canceled, result):
            assert_no_forbidden_material(value)
        for forbidden in FORBIDDEN_SENTINELS:
            assert forbidden not in rendered
            assert forbidden.encode() not in raw_events
    finally:
        await close_real_worker(env, worker)


@pytest.mark.asyncio
async def test_phase5k_hostile_control_input_is_rejected_before_temporal_history_can_record_it() -> None:
    from flowweaver_runtime_client.control_surface import FlowWeaverRuntimeControlSurface

    env, worker, facade = await open_real_worker()
    workflow_id = "runtime_tx_phase5k_negative"
    control = FlowWeaverRuntimeControlSurface(facade)
    try:
        await control.handle(
            {"operation": "start_transaction", "workflow_id": workflow_id, "start_payload": make_start_fields(workflow_id=workflow_id)}
        )
        await query_until_running(control, workflow_id)
        rejected = await control.handle(
            {
                "operation": "reconcile_delivery_ack",
                "workflow_id": workflow_id,
                "update": {
                    "event_type": "record_delivery_ack",
                    "delivery_key": "runtime_event_delivery_ack_phase5k_negative",
                    "surface": "final_text",
                    "target_kind": "delivery",
                    "target_id": "runtime_delivery_0",
                    "status": "sent",
                    "platform_payload": {"chat_id": PRIVATE_CHAT_ID, "user_id": PRIVATE_USER_ID},
                    "note": SENSITIVE_SENTINEL,
                },
            }
        )
        canceled = await control.handle(
            {
                "operation": "cancel_transaction",
                "workflow_id": workflow_id,
                "update": {"event_type": "cancel_transaction", "event_id": "runtime_event_cancel_phase5k_negative"},
            }
        )
        await env.client.get_workflow_handle(workflow_id).result()
        history = await env.client.get_workflow_handle(workflow_id).fetch_history()
        rendered, raw_events = history_text_and_bytes(history)

        assert rejected == {
            "ok": False,
            "operation": "reconcile_delivery_ack",
            "runtime_operation": "record_delivery_ack",
            "error_code": "unsafe_request",
        }
        assert canceled["snapshot"]["status"] == "canceled"
        assert_no_forbidden_material(rejected)
        for forbidden in FORBIDDEN_SENTINELS:
            assert forbidden not in rendered
            assert forbidden.encode() not in raw_events
    finally:
        await close_real_worker(env, worker)


def test_phase5k_diff_stays_inside_runtime_control_surface_allowlist() -> None:
    changed_files = _changed_files()
    allowed_changed_files = {
        "docs/plans/2026-05-07-flowweaver-phase5k-runtime-control-surface.md",
        "docs/dev_log/2026-05-07-flowweaver-phase5k-runtime-control-surface.md",
        "docs/plans/2026-05-07-flowweaver-phase6-gateway-ack-shadow-bridge.md",
        "docs/dev_log/2026-05-07-flowweaver-phase6-gateway-ack-shadow-bridge.md",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/__init__.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/control_surface.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/mcp_control_server.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/gateway_ack_shadow_bridge.py",
        "tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py",
        "tests/integration/test_flowweaver_phase5i_start_signature_parity.py",
        "tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py",
        "tests/integration/test_flowweaver_phase5k_runtime_control_surface.py",
        "tests/integration/test_flowweaver_phase6_gateway_ack_shadow_bridge.py",
        "tests/prototypes/test_flowweaver_phase5k_runtime_control_surface.py",
        "tests/prototypes/test_flowweaver_phase5k_mcp_control_surface.py",
        "tests/prototypes/test_flowweaver_phase6_gateway_ack_shadow_bridge.py",
        "docs/dev_log/2026-05-07-flowweaver-phase7-gateway-shadow-e2e-loop.md",
        "docs/plans/2026-05-07-flowweaver-phase7-gateway-shadow-e2e-loop.md",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/gateway_shadow_e2e_loop.py",
        "tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py",
        "tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py",
        "docs/dev_log/2026-05-07-flowweaver-phase8-production-readiness-gate.md",
        "docs/plans/2026-05-07-flowweaver-phase8-production-readiness-gate.md",
        "docs/runbooks/flowweaver-production-readiness.md",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/production_readiness_gate.py",
        "tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py",
        "docs/dev_log/2026-05-07-flowweaver-phase9-controlled-shadow-implementation.md",
        "docs/runbooks/flowweaver-controlled-shadow-plan-builder.md",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_shadow_design.py",
        "tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py",
        "docs/dev_log/2026-05-07-flowweaver-phase10-controlled-shadow-prototype-loop-implementation.md",
        "docs/runbooks/flowweaver-controlled-shadow-prototype-loop.md",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_shadow_prototype_loop.py",
        "tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py",
        "docs/dev_log/2026-05-07-flowweaver-phase11-controlled-gateway-observation-implementation.md",
            "docs/runbooks/flowweaver-controlled-gateway-observation-design.md",
            "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_gateway_observation_design.py",
            "tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py",
            "docs/dev_log/2026-05-07-flowweaver-phase12-controlled-gateway-observation-hook.md",
            "docs/runbooks/flowweaver-controlled-gateway-observation-hook.md",
            "gateway/flowweaver_controlled_gateway_observation.py",
            "tests/gateway/test_flowweaver_controlled_gateway_observation.py",
            "docs/plans/2026-05-07-flowweaver-phase13-live-gateway-observation-enablement-design.md",
            "docs/dev_log/2026-05-07-flowweaver-phase13-live-gateway-observation-enablement-design.md",
            "docs/runbooks/flowweaver-live-gateway-observation-enablement-design.md",
            "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/live_gateway_observation_enablement_design.py",
            "tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py",
            "docs/plans/2026-05-08-flowweaver-phase14-live-gateway-observation-enablement-implementation.md",
            "docs/dev_log/2026-05-08-flowweaver-phase14-live-gateway-observation-enablement-implementation.md",
            "docs/runbooks/flowweaver-live-gateway-observation-enablement-implementation.md",
            "gateway/flowweaver_live_gateway_observation_enablement.py",
            "tests/gateway/test_flowweaver_live_gateway_observation_enablement.py",
            "docs/plans/2026-05-08-flowweaver-phase15-manual-live-gateway-observation-review-gate.md",
            "docs/dev_log/2026-05-08-flowweaver-phase15-manual-live-gateway-observation-review-gate.md",
            "docs/runbooks/flowweaver-live-gateway-observation-manual-review.md",
            "gateway/flowweaver_live_gateway_observation_manual_review.py",
            "tests/gateway/test_flowweaver_live_gateway_observation_manual_review.py",
            "docs/plans/2026-05-08-flowweaver-phase16-operator-live-gateway-observation-decision-gate.md",
            "docs/dev_log/2026-05-08-flowweaver-phase16-operator-live-gateway-observation-decision-gate.md",
            "docs/runbooks/flowweaver-live-gateway-observation-operator-decision.md",
            "gateway/flowweaver_live_gateway_observation_operator_decision.py",
            "tests/gateway/test_flowweaver_live_gateway_observation_operator_decision.py",
            "docs/plans/2026-05-08-flowweaver-phase17-guarded-live-gateway-observation-enablement.md",
            "docs/dev_log/2026-05-08-flowweaver-phase17-guarded-live-gateway-observation-enablement.md",
            "docs/runbooks/flowweaver-live-gateway-observation-guarded-enablement.md",
            "gateway/flowweaver_live_gateway_observation_guarded_enablement.py",
            "tests/gateway/test_flowweaver_live_gateway_observation_guarded_enablement.py",
            "docs/plans/2026-05-09-flowweaver-phase18-guarded-live-gateway-observation-validation.md",
            "docs/dev_log/2026-05-09-flowweaver-phase18-guarded-live-gateway-observation-validation.md",
            "docs/runbooks/flowweaver-live-gateway-observation-guarded-validation.md",
            "gateway/flowweaver_live_gateway_observation_guarded_validation.py",
            "tests/gateway/test_flowweaver_live_gateway_observation_guarded_validation.py",
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
        }
    forbidden_prefixes = (
        "gateway/run.py",
        "gateway/platforms/",
        "tools/",
        "hermes_cli/",
    )
    forbidden_exact = {"pyproject.toml", "run_agent.py", "model_tools.py", "toolsets.py"}

    assert sorted(changed_files - allowed_changed_files) == []
    assert not [path for path in changed_files if path in forbidden_exact or path.startswith(forbidden_prefixes)]
    assert CONTROL_SOURCE.exists(), "Phase 5K must add control_surface.py"
    assert MCP_CONTROL_SOURCE.exists(), "Phase 5K must add mcp_control_server.py"


def test_phase5k_control_sources_do_not_add_gateway_wiring_or_runtime_lifecycle() -> None:
    assert CONTROL_SOURCE.exists(), "Phase 5K must add control_surface.py"
    assert MCP_CONTROL_SOURCE.exists(), "Phase 5K must add mcp_control_server.py"
    sources = {
        "control_surface.py": CONTROL_SOURCE.read_text(encoding="utf-8"),
        "mcp_control_server.py": MCP_CONTROL_SOURCE.read_text(encoding="utf-8"),
    }
    tree = ast.parse("\n".join(sources.values()))

    forbidden_import_roots = {
        "gateway",
        "tools",
        "model_tools",
        "toolsets",
        "run_agent",
        "socket",
        "subprocess",
        "requests",
        "httpx",
        "aiohttp",
        "logging",
        "os",
    }
    forbidden_call_names = {
        "open",
        "write_text",
        "system",
        "popen",
        "Popen",
        "run",
        "start_worker",
        "signal",
        "signal_with_start",
    }
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

    assert sorted(root for root in imports if root in forbidden_import_roots) == []
    assert sorted(call for call in calls if call in forbidden_call_names) == []

    lowered = "\n".join(sources.values()).lower()
    forbidden_markers = (
        "@workflow.signal",
        ".signal(",
        "signal_with_start",
        "docker",
        "systemctl",
        "gateway restart",
        "config.yaml",
        "mcp_servers",
        "register_mcp_servers",
        "streamable-http",
        "transport=\"sse\"",
        "transport='sse'",
    )
    assert {marker for marker in forbidden_markers if marker in lowered} == set()
    assert "workflow.execute_activity" not in lowered
    assert "start_workflow" not in lowered
    assert "execute_update" not in lowered
