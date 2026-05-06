"""Phase 5I real local Temporal Worker start-signature parity coverage."""

from __future__ import annotations

import asyncio
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
for path in (PHASE5C_SRC, PHASE5B_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from flowweaver_runtime_client.contracts import build_start_payload_from_safe_fields  # noqa: E402
from flowweaver_runtime_client.reconciliation_harness import reconcile_shadow_runtime_publication  # noqa: E402
from flowweaver_runtime_client.runtime_client import FlowWeaverRuntimeClient  # noqa: E402
from flowweaver_temporal_poc import FLOWWEAVER_TEMPORAL_TASK_QUEUE  # noqa: E402
from flowweaver_temporal_poc.payloads import CancelTransactionUpdate  # noqa: E402
from flowweaver_temporal_poc.workflows import FlowWeaverTransactionWorkflow  # noqa: E402

pytestmark = pytest.mark.integration

PRIVATE_MESSAGE_ID = "om_" + "phase5i_private_message"
SENSITIVE_SENTINEL = "unsafe-" + "to" + "ken" + "-phase5i"
RAW_HISTORY_MARKERS = (
    "allowed_runtime_events",
    "claim_check_policy",
    "forbidden_material",
    "raw_snapshot",
    "raw_capture",
    "credential",
    "to" + "ken",
    "se" + "cret",
)
RESULT_FORBIDDEN_MARKERS = (PRIVATE_MESSAGE_ID, SENSITIVE_SENTINEL, "workflowalreadystartederror")


async def open_real_worker() -> tuple[WorkflowEnvironment, Worker, FlowWeaverRuntimeClient]:
    env = await WorkflowEnvironment.start_time_skipping()
    worker = Worker(env.client, task_queue=FLOWWEAVER_TEMPORAL_TASK_QUEUE, workflows=[FlowWeaverTransactionWorkflow])
    await env.__aenter__()
    await worker.__aenter__()
    return env, worker, FlowWeaverRuntimeClient(env.client, temporal_address="localhost:7233")


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
        except Exception as exc:
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


def make_shadow_agent_result(*, index: int, include_forbidden_sentinels: bool = False) -> dict[str, Any]:
    card_message_id = PRIVATE_MESSAGE_ID if include_forbidden_sentinels else "om_" + f"phase5i_card_{index}"
    agent_result: dict[str, Any] = {
        "final_response": "done",
        "delivery_state": {
            "final_text": {"sent": True, "reason": "stream_final_response"},
            "rich_cards_sent": [{"type": "result_card", "message_id": card_message_id}],
        },
    }
    if include_forbidden_sentinels:
        agent_result["delivery_state"]["rich_cards_sent"].append(
            {"type": "result_card", "message_id": SENSITIVE_SENTINEL}
        )
    snapshot = TransactionSnapshot(
        transaction_id=f"session_phase5i_signature_{index}",
        title="Phase 5I start signature parity task",
        status="completed",
        started_at=3000.0 + index,
        updated_at=3002.0 + index,
        completed_at=3002.0 + index,
        recent_operations=(),
    )
    attached = attach_flowweaver_shadow_snapshot(agent_result, snapshot, enabled=True, final_text="done")
    assert attached is not None
    dry_run = attach_flowweaver_gateway_shadow_dry_run(agent_result, enabled=True)
    assert dry_run is not None and dry_run["verdict"] == "passed"
    return agent_result


def ready_publication(*, index: int, include_forbidden_sentinels: bool = False) -> dict[str, object]:
    publication = build_flowweaver_shadow_runtime_publication(
        make_shadow_agent_result(index=index, include_forbidden_sentinels=include_forbidden_sentinels)
    )
    assert publication["verdict"] == "ready"
    return publication


class StartForbiddenTemporalClient:
    async def start_workflow(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("start_workflow_called")


def assert_no_forbidden_result_material(value: object) -> None:
    rendered = repr(value).lower()
    for marker in RESULT_FORBIDDEN_MARKERS:
        assert marker.lower() not in rendered
    assert "invalid delivery ack update" not in rendered


def assert_history_omits_raw_start_policy(rendered: str, raw_events: bytes) -> None:
    rendered_lower = rendered.lower()
    raw_lower = raw_events.lower()
    for marker in RAW_HISTORY_MARKERS:
        assert marker not in rendered_lower
        assert marker.encode() not in raw_lower


@pytest.mark.asyncio
async def test_phase5i_temporal_history_omits_raw_start_policy_after_start_duplicate_and_cancel() -> None:
    publication = ready_publication(index=1, include_forbidden_sentinels=True)
    env, worker, facade = await open_real_worker()
    workflow_id = str(publication["workflow_id"])
    payload = build_start_payload_from_safe_fields(publication["start_request"]["start_payload"])
    try:
        started = await facade.start_transaction(payload, workflow_id=workflow_id)
        duplicate = await facade.start_transaction(payload, workflow_id=workflow_id)
        await query_until_running(facade, workflow_id)
        assert started["status"] == "started"
        assert duplicate["status"] == "running"
        assert_no_forbidden_result_material(started)
        assert_no_forbidden_result_material(duplicate)

        await facade.cancel_transaction(
            workflow_id,
            CancelTransactionUpdate(event_id="runtime_event_cancel_phase5i_history", reason_ref=None),
        )
        handle = env.client.get_workflow_handle(workflow_id)
        await handle.result()
        history = await handle.fetch_history()
        rendered, raw_events = history_text_and_bytes(history)

        assert_history_omits_raw_start_policy(rendered, raw_events)
        for marker in RESULT_FORBIDDEN_MARKERS:
            assert marker.lower() not in rendered.lower()
            assert marker.lower().encode() not in raw_events.lower()
    finally:
        await cancel_if_running(env, facade, workflow_id=workflow_id, event_id="runtime_event_cancel_phase5i_history_cleanup")
        await close_real_worker(env, worker)


@pytest.mark.asyncio
async def test_phase5i_duplicate_start_with_same_observable_counts_but_different_idempotency_is_rejected() -> None:
    publication = ready_publication(index=2)
    payload = build_start_payload_from_safe_fields(publication["start_request"]["start_payload"])
    mismatched_payload = replace(payload, idempotency_key="runtime_event_phase5i_alt_start")
    env, worker, facade = await open_real_worker()
    workflow_id = str(publication["workflow_id"])
    try:
        started = await facade.start_transaction(payload, workflow_id=workflow_id)
        assert started["status"] == "started"
        await query_until_running(facade, workflow_id)

        result = await facade.start_transaction(mismatched_payload, workflow_id=workflow_id)

        assert result == {"ok": False, "operation": "start_transaction", "error_code": "invalid_start_payload"}
        assert workflow_id not in repr(result)
        assert_no_forbidden_result_material(result)
    finally:
        await cancel_if_running(env, facade, workflow_id=workflow_id, event_id="runtime_event_cancel_phase5i_mismatch")
        await close_real_worker(env, worker)


@pytest.mark.asyncio
async def test_phase5i_matching_duplicate_start_still_returns_running_and_replay_duplicate_acks() -> None:
    publication = ready_publication(index=3)
    env, worker, facade = await open_real_worker()
    workflow_id = str(publication["workflow_id"])
    try:
        first = await reconcile_shadow_runtime_publication(publication, runtime_client=facade)
        second = await reconcile_shadow_runtime_publication(publication, runtime_client=facade)
        snapshot = (await query_until_running(facade, workflow_id))["snapshot"]

        assert first["ok"] is True
        assert first["reconciliation"]["ack_statuses"] == ["applied", "applied"]
        assert second["ok"] is True
        assert second["reconciliation"]["ack_statuses"] == ["duplicate", "duplicate"]
        assert second["reconciliation"]["applied_event_count"] == 2
        assert snapshot["applied_event_count"] == 2
        assert_no_forbidden_result_material(second)
    finally:
        await cancel_if_running(env, facade, workflow_id=workflow_id, event_id="runtime_event_cancel_phase5i_replay")
        await close_real_worker(env, worker)


@pytest.mark.asyncio
async def test_phase5i_runtime_facade_rejects_forged_non_hex_start_signature_before_start() -> None:
    publication = ready_publication(index=4)
    payload = build_start_payload_from_safe_fields(publication["start_request"]["start_payload"])
    forged_payload = replace(
        payload,
        event_contract_digest="runtime_sig_allowed_runtime_events",
        claim_policy_digest="runtime_sig_claim_check_policy",
    )
    env, worker, facade = await open_real_worker()
    workflow_id = str(publication["workflow_id"])
    try:
        with pytest.raises(ValueError, match="invalid_start_payload"):
            await facade.start_transaction(forged_payload, workflow_id=workflow_id)
    finally:
        await cancel_if_running(env, facade, workflow_id=workflow_id, event_id="runtime_event_cancel_phase5i_forged_digest")
        await close_real_worker(env, worker)


@pytest.mark.asyncio
async def test_phase5i_runtime_facade_rejects_forged_policy_marker_synthetic_ids_before_start() -> None:
    publication = ready_publication(index=5)
    payload = build_start_payload_from_safe_fields(publication["start_request"]["start_payload"])
    forged_payload = replace(
        payload,
        transaction_id="runtime_tx_claim_check_policy",
        idempotency_key="runtime_event_allowed_runtime_events",
    )
    facade = FlowWeaverRuntimeClient(StartForbiddenTemporalClient(), temporal_address="localhost:7233")
    workflow_id = forged_payload.transaction_id

    with pytest.raises(ValueError, match="invalid_start_payload"):
        await facade.start_transaction(forged_payload, workflow_id=workflow_id)


def test_phase5i_diff_does_not_add_gateway_wiring_or_runtime_lifecycle_outside_approved_files() -> None:
    base = _git("merge-base", "HEAD", "origin/feature/sachima-channel")
    changed_files = _changed_files(base)
    allowed_changed_files = {
        "docs/plans/2026-05-06-flowweaver-phase5i-start-signature-parity.md",
        "docs/dev_log/2026-05-06-flowweaver-phase5i-start-signature-parity.md",
        "prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py",
        "prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py",
        "tests/integration/test_flowweaver_phase5i_start_signature_parity.py",
        "tests/integration/test_flowweaver_phase5b_temporal_workflow.py",
        "tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py",
        "tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py",
        "tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py",
        "tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py",
        "tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py",
        "tests/prototypes/test_flowweaver_phase5c_tool_adapter.py",
        "tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py",
        "tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py",
    }

    assert changed_files <= allowed_changed_files
    assert not {path for path in changed_files if path in {"pyproject.toml", "gateway/run.py", "run_agent.py", "model_tools.py", "toolsets.py"}}
    assert not {path for path in changed_files if path.startswith(("gateway/platforms/", "tools/", "hermes_cli/"))}

    runtime_scanned_paths = (
        "prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py",
        "prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py",
    )
    added_text = "\n".join(line for path in runtime_scanned_paths for line in _added_lines_for(base, path)).lower()
    forbidden_markers = (
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
        "@workflow.signal",
        ".signal(",
        "signal_with_start",
    )
    assert not [marker for marker in forbidden_markers if marker in added_text]


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


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


def _added_lines_for(base: str, relative_path: str) -> list[str]:
    commands = (
        ("diff", "--unified=0", base, "HEAD", "--", relative_path),
        ("diff", "--unified=0", "--", relative_path),
        ("diff", "--cached", "--unified=0", "--", relative_path),
    )
    added: list[str] = []
    for command in commands:
        diff = _git(*command)
        added.extend(line[1:].strip() for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    return added
