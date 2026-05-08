"""Phase 5H real local Temporal Worker reconciliation coverage."""

from __future__ import annotations

import ast
import asyncio
import copy
import subprocess
import sys
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from gateway.flowweaver_shadow import attach_flowweaver_shadow_snapshot
from gateway.flowweaver_shadow_dry_run import attach_flowweaver_gateway_shadow_dry_run
from gateway.flowweaver_shadow_publisher import build_flowweaver_shadow_runtime_publication
from gateway.progress.events import TransactionSnapshot

ROOT = Path(__file__).resolve().parents[2]
PHASE5B_SRC = ROOT / "prototypes" / "flowweaver_phase5b_temporal_poc" / "src"
PHASE5C_SRC = ROOT / "prototypes" / "flowweaver_phase5c_runtime_client" / "src"
RUNTIME_CLIENT_SOURCE = PHASE5C_SRC / "flowweaver_runtime_client" / "runtime_client.py"
WORKFLOW_SOURCE = PHASE5B_SRC / "flowweaver_temporal_poc" / "workflows.py"
for path in (PHASE5C_SRC, PHASE5B_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from flowweaver_runtime_client.contracts import build_start_payload_from_safe_fields  # noqa: E402
from flowweaver_runtime_client.reconciliation_harness import reconcile_shadow_runtime_publication  # noqa: E402
from flowweaver_runtime_client.runtime_client import FlowWeaverRuntimeClient  # noqa: E402
from flowweaver_temporal_poc import FLOWWEAVER_TEMPORAL_TASK_QUEUE  # noqa: E402
from flowweaver_temporal_poc.payloads import CancelTransactionUpdate  # noqa: E402
from flowweaver_temporal_poc.workflows import FlowWeaverTransactionWorkflow  # noqa: E402
from flowweaver_temporal_poc.activities import deliver_artifact, execute_agent_turn, validate_claim_check_ref  # noqa: E402

pytestmark = pytest.mark.integration

PRIVATE_MESSAGE_ID = "om_" + "phase5h_private_message"
SENSITIVE_SENTINEL = "unsafe-" + "token" + "-phase5h"
FORBIDDEN_SENTINELS = (PRIVATE_MESSAGE_ID, SENSITIVE_SENTINEL)


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


class RecordingRuntimeClient:
    def __init__(self, inner: FlowWeaverRuntimeClient) -> None:
        self.inner = inner
        self.calls: list[dict[str, object]] = []

    @staticmethod
    def _compact(operation: str, result: dict[str, object]) -> dict[str, object]:
        return {
            "call": operation,
            "ok": result.get("ok"),
            "operation": result.get("operation"),
            "status": result.get("status"),
            "error_code": result.get("error_code"),
        }

    async def start_transaction(self, payload: object, *, workflow_id: str) -> dict[str, object]:
        result = await self.inner.start_transaction(payload, workflow_id=workflow_id)
        self.calls.append(self._compact("start_transaction", result))
        return result

    async def record_delivery_ack(self, workflow_id: str, update: object) -> dict[str, object]:
        result = await self.inner.record_delivery_ack(workflow_id, update)
        self.calls.append(self._compact("record_delivery_ack", result))
        return result

    async def query_snapshot(self, workflow_id: str) -> dict[str, object]:
        result = await self.inner.query_snapshot(workflow_id)
        self.calls.append(self._compact("query_snapshot", result))
        return result

    async def cancel_transaction(self, workflow_id: str, update: object) -> dict[str, object]:
        return await self.inner.cancel_transaction(workflow_id, update)


async def close_real_worker(env: WorkflowEnvironment, worker: Worker) -> None:
    await worker.__aexit__(None, None, None)
    await env.__aexit__(None, None, None)


async def cancel_if_running(
    env: WorkflowEnvironment,
    facade: FlowWeaverRuntimeClient,
    *,
    workflow_id: str,
    event_id: str,
) -> None:
    with suppress(Exception):
        await facade.cancel_transaction(workflow_id, CancelTransactionUpdate(event_id=event_id, reason_ref=None))
    with suppress(Exception):
        await env.client.get_workflow_handle(workflow_id).result()


async def query_until_running(facade: FlowWeaverRuntimeClient, workflow_id: str) -> dict[str, object]:
    last_error: Exception | None = None
    for _ in range(20):
        try:
            result = await facade.query_snapshot(workflow_id)
        except Exception as exc:  # Temporal can reject queries before the first workflow task completes.
            last_error = exc
            await asyncio.sleep(0.05)
            continue
        snapshot = result["snapshot"]
        if type(snapshot) is dict and snapshot.get("status") == "running":
            return result
        await asyncio.sleep(0.05)
    if last_error is not None:
        raise last_error
    raise AssertionError("workflow did not reach running state")


def history_text_and_bytes(history: Any) -> tuple[str, bytes]:
    rendered = history.to_json() if hasattr(history, "to_json") else repr(history.to_json_dict())
    raw_events = b"".join(event.SerializeToString() for event in history.events)
    return rendered, raw_events


def make_shadow_agent_result(
    *,
    index: int,
    rich_card_count: int = 1,
    include_forbidden_sentinels: bool = False,
) -> dict[str, Any]:
    rich_cards: list[dict[str, str]] = []
    for item in range(rich_card_count):
        card = {
            "type": "result_card",
            "message_id": PRIVATE_MESSAGE_ID if include_forbidden_sentinels and item == 0 else "om_" + f"phase5h_card_{index}_{item}",
        }
        if include_forbidden_sentinels:
            if item == 0:
                card["message_id"] = PRIVATE_MESSAGE_ID
            elif item == 1:
                card["message_id"] = SENSITIVE_SENTINEL
        rich_cards.append(card)

    agent_result: dict[str, Any] = {
        "final_response": "done",
        "delivery_state": {
            "final_text": {"sent": True, "reason": "stream_final_response"},
            "rich_cards_sent": rich_cards,
        },
    }
    snapshot = TransactionSnapshot(
        transaction_id=f"session_phase5h_reconcile_{index}",
        title="Phase 5H real Temporal worker reconciliation task",
        status="completed",
        started_at=2000.0 + index,
        updated_at=2002.0 + index,
        completed_at=2002.0 + index,
        recent_operations=(),
    )
    attached = attach_flowweaver_shadow_snapshot(agent_result, snapshot, enabled=True, final_text="done")
    assert attached is not None
    dry_run = attach_flowweaver_gateway_shadow_dry_run(agent_result, enabled=True)
    assert dry_run is not None and dry_run["verdict"] == "passed"
    return agent_result


def ready_publication(
    *,
    index: int,
    rich_card_count: int = 1,
    include_forbidden_sentinels: bool = False,
) -> dict[str, object]:
    publication = build_flowweaver_shadow_runtime_publication(
        make_shadow_agent_result(
            index=index,
            rich_card_count=rich_card_count,
            include_forbidden_sentinels=include_forbidden_sentinels,
        )
    )
    assert publication["verdict"] == "ready"
    return publication


def assert_no_forbidden_material(value: object) -> None:
    rendered = repr(value).lower()
    for forbidden in FORBIDDEN_SENTINELS:
        assert forbidden.lower() not in rendered
    assert "workflowalreadystartederror" not in rendered
    assert "invalid delivery ack update" not in rendered


@pytest.mark.asyncio
async def test_phase5h_reconciles_gateway_shadow_publication_through_real_temporal_worker() -> None:
    publication = ready_publication(index=1, rich_card_count=1)
    env, worker, facade = await open_real_worker()
    workflow_id = str(publication["workflow_id"])
    try:
        result = await reconcile_shadow_runtime_publication(publication, runtime_client=facade)
        snapshot_result = await query_until_running(facade, workflow_id)
        snapshot = snapshot_result["snapshot"]

        assert result["ok"] is True
        assert result["status"] == "reconciled"
        assert result["reconciliation"]["record_counts"] == {
            "transactions": 1,
            "intents": 1,
            "artifacts": 1,
            "deliveries": 2,
        }
        assert result["reconciliation"]["ack_statuses"] == ["applied", "applied"]
        assert snapshot["delivery_statuses"] == {"runtime_delivery_0": "sent", "runtime_delivery_1": "sent"}
        assert snapshot["applied_event_count"] == 2
        assert_no_forbidden_material(result)
        assert_no_forbidden_material(snapshot)
    finally:
        await cancel_if_running(env, facade, workflow_id=workflow_id, event_id="runtime_event_cancel_phase5h_happy")
        await close_real_worker(env, worker)


@pytest.mark.asyncio
async def test_phase5h_replay_against_real_temporal_worker_returns_duplicate_acks_without_extra_state() -> None:
    publication = ready_publication(index=2, rich_card_count=1)
    env, worker, facade = await open_real_worker()
    workflow_id = str(publication["workflow_id"])
    try:
        first = await reconcile_shadow_runtime_publication(publication, runtime_client=facade)
        second = await reconcile_shadow_runtime_publication(publication, runtime_client=facade)
        snapshot_result = await query_until_running(facade, workflow_id)
        snapshot = snapshot_result["snapshot"]

        assert first["ok"] is True
        assert first["reconciliation"]["ack_statuses"] == ["applied", "applied"]
        assert first["reconciliation"]["applied_event_count"] == 2
        assert second["ok"] is True
        assert second["reconciliation"]["ack_statuses"] == ["duplicate", "duplicate"]
        assert second["reconciliation"]["applied_event_count"] == 2
        assert snapshot["applied_event_count"] == 2
        assert snapshot["delivery_statuses"] == {"runtime_delivery_0": "sent", "runtime_delivery_1": "sent"}
        assert_no_forbidden_material(second)
    finally:
        await cancel_if_running(env, facade, workflow_id=workflow_id, event_id="runtime_event_cancel_phase5h_replay")
        await close_real_worker(env, worker)


@pytest.mark.asyncio
async def test_phase5h_duplicate_start_with_mismatched_observable_payload_returns_invalid_start_payload() -> None:
    publication = ready_publication(index=3, rich_card_count=1)
    payload = build_start_payload_from_safe_fields(publication["start_request"]["start_payload"])
    mismatched_payload = replace(payload, record_counts={**payload.record_counts, "deliveries": 1})
    env, worker, facade = await open_real_worker()
    workflow_id = str(publication["workflow_id"])
    try:
        started = await facade.start_transaction(payload, workflow_id=workflow_id)
        assert started["status"] == "started"
        await query_until_running(facade, workflow_id)

        result = await facade.start_transaction(mismatched_payload, workflow_id=workflow_id)

        assert result == {"ok": False, "operation": "start_transaction", "error_code": "invalid_start_payload"}
        assert workflow_id not in repr(result)
        assert_no_forbidden_material(result)
    finally:
        await cancel_if_running(env, facade, workflow_id=workflow_id, event_id="runtime_event_cancel_phase5h_mismatch")
        await close_real_worker(env, worker)


@pytest.mark.asyncio
async def test_phase5h_real_temporal_worker_preserves_missing_delivery_slot_mismatch_code() -> None:
    publication = ready_publication(index=4, rich_card_count=1)
    tampered_publication = copy.deepcopy(publication)
    tampered_publication["start_request"]["start_payload"]["record_counts"]["deliveries"] = 1
    env, worker, facade = await open_real_worker()
    workflow_id = str(tampered_publication["workflow_id"])
    try:
        result = await reconcile_shadow_runtime_publication(tampered_publication, runtime_client=facade)
        snapshot_result = await query_until_running(facade, workflow_id)
        snapshot = snapshot_result["snapshot"]

        assert result == {
            "ok": False,
            "operation": "reconcile_shadow_runtime_publication",
            "error_code": "reconciliation_mismatch",
        }
        assert "runtime_delivery_1" not in snapshot["delivery_statuses"]
        assert_no_forbidden_material(result)
        assert_no_forbidden_material(snapshot)
    finally:
        await cancel_if_running(env, facade, workflow_id=workflow_id, event_id="runtime_event_cancel_phase5h_missing_slot")
        await close_real_worker(env, worker)


@pytest.mark.asyncio
async def test_phase5h_real_temporal_history_omits_gateway_private_ids_and_credentials_after_replay() -> None:
    agent_result = make_shadow_agent_result(index=5, rich_card_count=2, include_forbidden_sentinels=True)
    source_rendered = repr(agent_result)
    for forbidden in FORBIDDEN_SENTINELS:
        assert forbidden in source_rendered
    publication = build_flowweaver_shadow_runtime_publication(agent_result)
    assert publication["verdict"] == "ready"
    assert_no_forbidden_material(publication)

    env, worker, raw_facade = await open_real_worker()
    facade = RecordingRuntimeClient(raw_facade)
    workflow_id = str(publication["workflow_id"])
    try:
        first = await reconcile_shadow_runtime_publication(publication, runtime_client=facade)
        second = await reconcile_shadow_runtime_publication(publication, runtime_client=facade)
        snapshot_result = await query_until_running(facade, workflow_id)
        snapshot = snapshot_result["snapshot"]

        assert first["ok"] is True, repr((first, facade.calls[-8:]))
        assert second["ok"] is True, repr((second, facade.calls[-8:]))
        assert_no_forbidden_material(first)
        assert_no_forbidden_material(second)
        assert_no_forbidden_material(snapshot)

        await facade.cancel_transaction(
            workflow_id,
            CancelTransactionUpdate(event_id="runtime_event_cancel_phase5h_history", reason_ref=None),
        )
        handle = env.client.get_workflow_handle(workflow_id)
        await handle.result()
        history = await handle.fetch_history()
        rendered, raw_events = history_text_and_bytes(history)

        for forbidden in FORBIDDEN_SENTINELS:
            assert forbidden not in rendered
            assert forbidden.encode() not in raw_events
    finally:
        await cancel_if_running(env, facade, workflow_id=workflow_id, event_id="runtime_event_cancel_phase5h_history_cleanup")
        await close_real_worker(env, worker)


def test_phase5h_diff_does_not_add_gateway_wiring_or_runtime_lifecycle_outside_integration_tests() -> None:
    base = _phase_diff_base()
    changed_files = _changed_files(base)
    allowed_changed_files = {
        "docs/plans/2026-05-06-flowweaver-phase5h-local-temporal-worker-reconciliation-harness.md",
        "docs/dev_log/2026-05-06-flowweaver-phase5h-local-temporal-worker-reconciliation-harness.md",
        "docs/plans/2026-05-06-flowweaver-phase5i-start-signature-parity.md",
        "docs/dev_log/2026-05-06-flowweaver-phase5i-start-signature-parity.md",
        "docs/plans/2026-05-06-flowweaver-phase5j-activity-claim-check-boundary.md",
        "docs/dev_log/2026-05-06-flowweaver-phase5j-activity-claim-check-boundary.md",
        "docs/plans/2026-05-07-flowweaver-phase5k-runtime-control-surface.md",
        "docs/dev_log/2026-05-07-flowweaver-phase5k-runtime-control-surface.md",
        "docs/plans/2026-05-07-flowweaver-phase6-gateway-ack-shadow-bridge.md",
        "docs/dev_log/2026-05-07-flowweaver-phase6-gateway-ack-shadow-bridge.md",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/control_surface.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/mcp_control_server.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/gateway_ack_shadow_bridge.py",
        "tests/integration/test_flowweaver_phase5k_runtime_control_surface.py",
        "tests/integration/test_flowweaver_phase6_gateway_ack_shadow_bridge.py",
        "tests/prototypes/test_flowweaver_phase5k_runtime_control_surface.py",
        "tests/prototypes/test_flowweaver_phase5k_mcp_control_surface.py",
        "tests/prototypes/test_flowweaver_phase6_gateway_ack_shadow_bridge.py",
        "prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/activities.py",
        "tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py",
        "tests/prototypes/test_flowweaver_phase5j_activity_contract.py",
        "prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py",
        "prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py",
        "tests/integration/test_flowweaver_phase5b_temporal_workflow.py",
        "tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py",
        "tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py",
        "tests/integration/test_flowweaver_phase5i_start_signature_parity.py",
        "tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py",
        "tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py",
        "tests/prototypes/test_flowweaver_phase5c_tool_adapter.py",
        "tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py",
        "tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py",
        "tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py",
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
        }

    assert changed_files <= allowed_changed_files
    assert not {path for path in changed_files if path in {"pyproject.toml", "gateway/run.py", "run_agent.py", "model_tools.py", "toolsets.py"}}
    assert not {path for path in changed_files if path.startswith(("gateway/platforms/", "tools/", "hermes_cli/"))}

    runtime_source = RUNTIME_CLIENT_SOURCE.read_text(encoding="utf-8")
    runtime_tree = ast.parse(runtime_source)
    imports: list[tuple[str, tuple[str, ...]]] = []
    for node in ast.walk(runtime_tree):
        if isinstance(node, ast.Import):
            imports.extend((alias.name, ()) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append((node.module, tuple(alias.name for alias in node.names)))
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "compile", "open", "print", "__import__"}
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"write_text", "write_bytes", "system", "popen"}

    for module, names in imports:
        assert not module.startswith(("gateway", "gateway.platforms", "gateway.run", "tools", "hermes_cli"))
        if module.startswith("temporalio"):
            assert module == "temporalio.exceptions"
            assert set(names) == {"WorkflowAlreadyStartedError"}

    runtime_added = _added_lines(base, "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py")
    runtime_added_text = "\n".join(runtime_added).lower()
    forbidden_added_runtime_markers = (
        "workflowenvironment",
        "worker(",
        "docker",
        "systemctl",
        "daemon",
        "subprocess",
        "socket.",
        "gateway.run",
        "gateway.platforms",
        "tools.registry",
        "global registry",
        "config.yaml",
        "print(",
        "logger.",
        "logging.",
        "str(exc",
        "repr(exc",
        "format(exc",
        "{exc",
    )
    assert not [marker for marker in forbidden_added_runtime_markers if marker in runtime_added_text]

    combined_source = runtime_source + "\n" + WORKFLOW_SOURCE.read_text(encoding="utf-8")
    assert "@workflow.signal" not in combined_source
    assert ".signal(" not in combined_source
    assert "signal_with_start" not in combined_source


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _phase_diff_base() -> str:
    parents = _git("rev-list", "--parents", "-n", "1", "HEAD").split()
    if len(parents) > 2:
        return "HEAD"
    return _git("merge-base", "HEAD", "origin/feature/sachima-channel")


def _changed_files(base: str) -> set[str]:
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


def _added_lines(base: str, relative_path: str) -> list[str]:
    diff = subprocess.check_output(
        ["git", "diff", "--unified=0", base, "--", relative_path],
        cwd=ROOT,
        text=True,
    )
    return [line[1:].strip() for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]
