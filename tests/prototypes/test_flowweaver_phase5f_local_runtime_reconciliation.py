"""Phase 5F local runtime reconciliation harness tests."""

from __future__ import annotations

import ast
import copy
import sys
from pathlib import Path
from typing import Any

import pytest

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

PRIVATE_MESSAGE_ID = "om_" + "private_message"
PRIVATE_CHAT_ID = "oc_" + "private_chat"
PRIVATE_USER_ID = "ou_" + "private_user"
CRED_SHAPED = "cred" + "ential=abc123"
_ALLOWED_RECONCILIATION_RESULT_FIELDS = {
    "ok",
    "operation",
    "workflow_id",
    "transaction_id",
    "status",
    "publication_status",
    "snapshot_status",
    "checks",
    "reconciliation",
    "side_effects",
    "error_code",
}


def make_shadow_agent_result(*, index: int = 0, rich_cards_sent: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    agent_result: dict[str, Any] = {
        "final_response": "done",
        "delivery_state": {
            "final_text": {"sent": True, "reason": "stream_final_response"},
            "rich_cards_sent": rich_cards_sent or [],
        },
    }
    snapshot = TransactionSnapshot(
        transaction_id=f"session_phase5f_reconcile_{index}",
        title="Phase 5F local runtime reconciliation task",
        status="completed",
        started_at=1000.0 + index,
        updated_at=1002.0 + index,
        completed_at=1002.0 + index,
        recent_operations=(),
    )
    attached = attach_flowweaver_shadow_snapshot(agent_result, snapshot, enabled=True, final_text="done")
    assert attached is not None
    dry_run = attach_flowweaver_gateway_shadow_dry_run(agent_result, enabled=True)
    assert dry_run is not None and dry_run["verdict"] == "passed"
    return agent_result


def ready_publication(*, index: int = 0, rich_cards_sent: list[dict[str, Any]] | None = None) -> dict[str, object]:
    publication = build_flowweaver_shadow_runtime_publication(
        make_shadow_agent_result(index=index, rich_cards_sent=rich_cards_sent)
    )
    assert publication["verdict"] == "ready"
    return publication


@pytest.mark.asyncio
async def test_phase5f_reconciles_shadow_publication_with_runtime_snapshot() -> None:
    from flowweaver_runtime_client.reconciliation_harness import (
        InMemoryFlowWeaverRuntimeClient,
        reconcile_shadow_runtime_publication,
    )

    publication = ready_publication(index=1)
    runtime_client = InMemoryFlowWeaverRuntimeClient()

    result = await reconcile_shadow_runtime_publication(publication, runtime_client=runtime_client)

    assert set(result) <= _ALLOWED_RECONCILIATION_RESULT_FIELDS
    assert result["ok"] is True
    assert result["operation"] == "reconcile_shadow_runtime_publication"
    assert result["workflow_id"] == publication["workflow_id"]
    assert result["transaction_id"] == publication["transaction_id"]
    assert result["status"] == "reconciled"
    assert result["publication_status"] == "published"
    assert result["snapshot_status"] == "running"
    assert result["checks"] == {
        "runtime_ids_match": True,
        "entry_count_matches": True,
        "record_counts_match": True,
        "delivery_ack_count_matches": True,
        "delivery_statuses_match": True,
        "side_effects_absent": True,
    }
    assert result["reconciliation"] == {
        "entry_count": 1,
        "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
        "ack_statuses": ["applied"],
        "applied_event_count": 1,
    }
    assert result["side_effects"] == []

    snapshot_result = await runtime_client.query_snapshot(publication["workflow_id"])
    assert snapshot_result["snapshot"]["delivery_statuses"] == {"runtime_delivery_0": "sent"}
    assert snapshot_result["snapshot"]["side_effects"] == []


@pytest.mark.asyncio
async def test_phase5f_replay_of_same_publication_is_idempotent() -> None:
    from flowweaver_runtime_client.reconciliation_harness import (
        InMemoryFlowWeaverRuntimeClient,
        reconcile_shadow_runtime_publication,
    )

    publication = ready_publication(index=2)
    runtime_client = InMemoryFlowWeaverRuntimeClient()

    first = await reconcile_shadow_runtime_publication(publication, runtime_client=runtime_client)
    second = await reconcile_shadow_runtime_publication(publication, runtime_client=runtime_client)
    snapshot_result = await runtime_client.query_snapshot(publication["workflow_id"])

    assert first["ok"] is True
    assert first["reconciliation"]["ack_statuses"] == ["applied"]
    assert first["reconciliation"]["applied_event_count"] == 1
    assert second["ok"] is True
    assert second["reconciliation"]["ack_statuses"] == ["duplicate"]
    assert second["reconciliation"]["applied_event_count"] == 1
    assert snapshot_result["snapshot"]["delivery_statuses"] == {"runtime_delivery_0": "sent"}
    assert list(snapshot_result["snapshot"]["delivery_statuses"]) == ["runtime_delivery_0"]


@pytest.mark.asyncio
async def test_phase5f_detects_extra_ack_surface_without_matching_runtime_delivery_slot() -> None:
    from flowweaver_runtime_client.reconciliation_harness import (
        InMemoryFlowWeaverRuntimeClient,
        reconcile_shadow_runtime_publication,
    )

    publication = ready_publication(index=3, rich_cards_sent=[{"type": "result_card", "message_id": PRIVATE_MESSAGE_ID}])
    tampered_publication = copy.deepcopy(publication)
    tampered_publication["start_request"]["start_payload"]["record_counts"]["deliveries"] = 1
    runtime_client = InMemoryFlowWeaverRuntimeClient()

    assert [update["target_id"] for update in publication["ack_bridge"]["updates"]] == [
        "runtime_delivery_0",
        "runtime_delivery_1",
    ]

    result = await reconcile_shadow_runtime_publication(tampered_publication, runtime_client=runtime_client)
    snapshot_result = await runtime_client.query_snapshot(tampered_publication["workflow_id"])

    assert result == {
        "ok": False,
        "operation": "reconcile_shadow_runtime_publication",
        "error_code": "reconciliation_mismatch",
    }
    assert "runtime_delivery_1" not in snapshot_result["snapshot"]["delivery_statuses"]


@pytest.mark.asyncio
async def test_phase5f_reconciliation_detects_mismatched_snapshot_without_echoing_raw_values() -> None:
    from flowweaver_runtime_client.reconciliation_harness import (
        InMemoryFlowWeaverRuntimeClient,
        reconcile_shadow_runtime_publication,
    )

    publication = ready_publication(index=4)
    mismatch_transaction_id = "runtime_tx_shadow_00000000000000000000"
    if mismatch_transaction_id == publication["transaction_id"]:
        mismatch_transaction_id = "runtime_tx_shadow_11111111111111111111"
    base_client = InMemoryFlowWeaverRuntimeClient()

    class MismatchedSnapshotRuntimeClient:
        async def start_transaction(self, payload: object, *, workflow_id: str) -> dict[str, object]:
            return await base_client.start_transaction(payload, workflow_id=workflow_id)

        async def record_delivery_ack(self, workflow_id: str, update: object) -> dict[str, object]:
            return await base_client.record_delivery_ack(workflow_id, update)

        async def query_snapshot(self, workflow_id: str) -> dict[str, object]:
            result = await base_client.query_snapshot(workflow_id)
            snapshot = dict(result["snapshot"])
            snapshot["transaction_id"] = mismatch_transaction_id
            return {
                "ok": True,
                "operation": "query_snapshot",
                "workflow_id": workflow_id,
                "transaction_id": mismatch_transaction_id,
                "status": "running",
                "snapshot": snapshot,
            }

    result = await reconcile_shadow_runtime_publication(publication, runtime_client=MismatchedSnapshotRuntimeClient())
    rendered = repr(result).lower()

    assert result == {
        "ok": False,
        "operation": "reconcile_shadow_runtime_publication",
        "error_code": "reconciliation_mismatch",
    }
    assert publication["workflow_id"] not in rendered
    assert mismatch_transaction_id not in rendered
    assert PRIVATE_MESSAGE_ID not in rendered
    assert PRIVATE_CHAT_ID not in rendered
    assert PRIVATE_USER_ID not in rendered
    assert CRED_SHAPED not in rendered


@pytest.mark.asyncio
async def test_phase5f_rejects_unsafe_publication_before_querying_runtime() -> None:
    from flowweaver_runtime_client.reconciliation_harness import (
        InMemoryFlowWeaverRuntimeClient,
        reconcile_shadow_runtime_publication,
    )

    class TrackingRuntimeClient(InMemoryFlowWeaverRuntimeClient):
        def __init__(self) -> None:
            super().__init__()
            self.start_count = 0
            self.query_count = 0

        async def start_transaction(self, payload: object, *, workflow_id: str) -> dict[str, object]:
            self.start_count += 1
            return await super().start_transaction(payload, workflow_id=workflow_id)

        async def query_snapshot(self, workflow_id: str) -> dict[str, object]:
            self.query_count += 1
            return await super().query_snapshot(workflow_id)

    unsafe_id = "runtime_tx_shadow_chatbad"
    publication = ready_publication(index=5)
    unsafe_publication = copy.deepcopy(publication)
    unsafe_publication["workflow_id"] = unsafe_id
    unsafe_publication["transaction_id"] = unsafe_id
    runtime_client = TrackingRuntimeClient()

    result = await reconcile_shadow_runtime_publication(unsafe_publication, runtime_client=runtime_client)
    rendered = repr(result).lower()

    assert result == {
        "ok": False,
        "operation": "reconcile_shadow_runtime_publication",
        "error_code": "invalid_publication",
    }
    assert runtime_client.start_count == 0
    assert runtime_client.query_count == 0
    assert unsafe_id not in rendered
    assert PRIVATE_MESSAGE_ID not in rendered


@pytest.mark.asyncio
async def test_phase5f_rejects_nested_unsafe_runtime_identity_before_starting_runtime() -> None:
    from flowweaver_runtime_client.reconciliation_harness import (
        InMemoryFlowWeaverRuntimeClient,
        reconcile_shadow_runtime_publication,
    )

    class TrackingRuntimeClient(InMemoryFlowWeaverRuntimeClient):
        def __init__(self) -> None:
            super().__init__()
            self.start_count = 0
            self.query_count = 0

        async def start_transaction(self, payload: object, *, workflow_id: str) -> dict[str, object]:
            self.start_count += 1
            return await super().start_transaction(payload, workflow_id=workflow_id)

        async def query_snapshot(self, workflow_id: str) -> dict[str, object]:
            self.query_count += 1
            return await super().query_snapshot(workflow_id)

    publication = ready_publication(index=6)
    unsafe_publication = copy.deepcopy(publication)
    unsafe_publication["runtime_identity"]["workflow_id"] = PRIVATE_USER_ID
    runtime_client = TrackingRuntimeClient()

    result = await reconcile_shadow_runtime_publication(unsafe_publication, runtime_client=runtime_client)
    rendered = repr(result).lower()

    assert result == {
        "ok": False,
        "operation": "reconcile_shadow_runtime_publication",
        "error_code": "invalid_publication",
    }
    assert runtime_client.start_count == 0
    assert runtime_client.query_count == 0
    assert PRIVATE_USER_ID not in rendered


@pytest.mark.asyncio
async def test_phase5f_rejects_raw_runtime_identity_event_id_before_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    import flowweaver_runtime_client.reconciliation_harness as harness

    publication = ready_publication(index=7)
    unsafe_publication = copy.deepcopy(publication)
    unsafe_event_id = "runtime_event_raw_foo"
    unsafe_publication["runtime_identity"]["idempotency_key"] = unsafe_event_id
    unsafe_publication["start_request"]["start_payload"]["idempotency_key"] = unsafe_event_id
    publish_calls = 0

    async def fake_publish(publication: object, *, runtime_client: object) -> dict[str, object]:
        nonlocal publish_calls
        publish_calls += 1
        return {
            "ok": False,
            "operation": "publish_shadow_runtime_publication",
            "error_code": "invalid_start_payload",
        }

    monkeypatch.setattr(harness, "publish_shadow_runtime_publication", fake_publish)

    result = await harness.reconcile_shadow_runtime_publication(
        unsafe_publication,
        runtime_client=object(),
    )

    assert result == {
        "ok": False,
        "operation": "reconcile_shadow_runtime_publication",
        "error_code": "invalid_publication",
    }
    assert publish_calls == 0


@pytest.mark.asyncio
async def test_phase5f_reconciliation_detects_snapshot_record_count_status_map_drift() -> None:
    from flowweaver_runtime_client.reconciliation_harness import (
        InMemoryFlowWeaverRuntimeClient,
        reconcile_shadow_runtime_publication,
    )

    publication = ready_publication(index=7)
    base_client = InMemoryFlowWeaverRuntimeClient()

    class DriftedSnapshotRuntimeClient:
        async def start_transaction(self, payload: object, *, workflow_id: str) -> dict[str, object]:
            return await base_client.start_transaction(payload, workflow_id=workflow_id)

        async def record_delivery_ack(self, workflow_id: str, update: object) -> dict[str, object]:
            return await base_client.record_delivery_ack(workflow_id, update)

        async def query_snapshot(self, workflow_id: str) -> dict[str, object]:
            result = await base_client.query_snapshot(workflow_id)
            snapshot = dict(result["snapshot"])
            snapshot["counts"] = {"intents": 1, "artifacts": 1, "deliveries": 2}
            snapshot["delivery_statuses"] = {
                "runtime_delivery_0": "sent",
                "runtime_delivery_1": "planned",
            }
            return {
                "ok": True,
                "operation": "query_snapshot",
                "workflow_id": workflow_id,
                "transaction_id": snapshot["transaction_id"],
                "status": "running",
                "snapshot": snapshot,
            }

    result = await reconcile_shadow_runtime_publication(publication, runtime_client=DriftedSnapshotRuntimeClient())

    assert result == {
        "ok": False,
        "operation": "reconcile_shadow_runtime_publication",
        "error_code": "reconciliation_mismatch",
    }


def test_phase5f_harness_source_has_no_service_lifecycle_or_gateway_wiring() -> None:
    source_path = PHASE5C_SRC / "flowweaver_runtime_client" / "reconciliation_harness.py"
    source = source_path.read_text(encoding="utf-8")
    lowered = source.lower()
    tree = ast.parse(source)

    forbidden_markers = (
        "temporalio",
        "flowweaver_runtime_client.runtime_client",
        "flowweaver_temporal_poc.workflows",
        "flowweaverruntimeclient.connect",
        "connect_local_temporal",
        "client.connect",
        "temporal_address",
        "task_queue",
        "start_workflow",
        "get_workflow_handle",
        "execute_update",
        "subprocess",
        "docker",
        "systemctl",
        "daemon",
        "config.yaml",
        "import gateway",
        "from gateway",
        "gateway.platforms",
        "tools.registry",
        "global registry",
    )
    assert not [marker for marker in forbidden_markers if marker in lowered]

    forbidden_modules = {"subprocess", "socket", "os", "temporalio", "mcp", "gateway", "tools"}
    forbidden_calls = {"open", "compile", "eval", "exec", "system", "popen", "run", "write_text", "write_bytes"}
    forbidden_attrs = {
        "connect",
        "connect_local_temporal",
        "start_workflow",
        "get_workflow_handle",
        "execute_update",
        "popen",
        "write_text",
        "write_bytes",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(alias.name.split(".")[0] in forbidden_modules for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in forbidden_modules
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_attrs
