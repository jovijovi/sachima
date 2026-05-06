"""Phase 5E prototype-only local shadow publication adapter tests."""

from __future__ import annotations

import ast
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
SECRET_SHAPED = "sk" + "-" + "123456789012"
ALLOWED_ADAPTER_RESULT_FIELDS = {
    "ok",
    "operation",
    "workflow_id",
    "transaction_id",
    "status",
    "runtime_call_counts",
    "ack_statuses",
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
        transaction_id=f"session_phase5e_adapter_{index}",
        title="Phase 5E local publish adapter task",
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


def ready_publication(*, ack_count: int = 1) -> dict[str, object]:
    rich_cards = [{"type": "result_card", "message_id": "om_" + f"card_{index}"} for index in range(max(0, ack_count - 1))]
    publication = build_flowweaver_shadow_runtime_publication(
        make_shadow_agent_result(index=ack_count, rich_cards_sent=rich_cards)
    )
    assert publication["verdict"] == "ready"
    assert len(publication["ack_bridge"]["updates"]) == ack_count
    return publication


class FakeRuntimeClient:
    def __init__(self, statuses: list[str] | None = None) -> None:
        self.started: list[dict[str, object]] = []
        self.acks: list[dict[str, object]] = []
        self._statuses = statuses or ["applied"]

    async def start_transaction(self, payload: object, *, workflow_id: str) -> dict[str, object]:
        self.started.append({"payload": payload, "workflow_id": workflow_id})
        return {
            "ok": True,
            "operation": "start_transaction",
            "workflow_id": workflow_id,
            "transaction_id": getattr(payload, "transaction_id", None),
            "status": "started",
        }

    async def record_delivery_ack(self, workflow_id: str, update: object) -> dict[str, object]:
        self.acks.append({"workflow_id": workflow_id, "update": update})
        status = self._statuses[min(len(self.acks) - 1, len(self._statuses) - 1)]
        return {"ok": True, "operation": "record_delivery_ack", "workflow_id": workflow_id, "status": status}


class RuntimeClientThatLeaks:
    async def start_transaction(self, payload: object, *, workflow_id: str) -> dict[str, object]:
        raise RuntimeError(f"boom {workflow_id} {PRIVATE_MESSAGE_ID} {SECRET_SHAPED}")


@pytest.mark.asyncio
async def test_shadow_publication_adapter_starts_runtime_once_then_applies_acks_in_order() -> None:
    from flowweaver_runtime_client.publication_adapter import publish_shadow_runtime_publication

    publication = ready_publication(ack_count=2)
    runtime_client = FakeRuntimeClient(statuses=["applied", "duplicate"])

    result = await publish_shadow_runtime_publication(publication, runtime_client=runtime_client)

    assert set(result) <= ALLOWED_ADAPTER_RESULT_FIELDS
    assert result == {
        "ok": True,
        "operation": "publish_shadow_runtime_publication",
        "workflow_id": publication["workflow_id"],
        "transaction_id": publication["transaction_id"],
        "status": "published",
        "runtime_call_counts": {"start_transaction": 1, "record_delivery_ack": 2},
        "ack_statuses": ["applied", "duplicate"],
    }
    assert len(runtime_client.started) == 1
    assert runtime_client.started[0]["workflow_id"] == publication["workflow_id"]
    assert getattr(runtime_client.started[0]["payload"], "transaction_id") == publication["transaction_id"]
    assert [call["workflow_id"] for call in runtime_client.acks] == [publication["workflow_id"], publication["workflow_id"]]
    assert [getattr(call["update"], "target_id") for call in runtime_client.acks] == ["runtime_delivery_0", "runtime_delivery_1"]


@pytest.mark.asyncio
async def test_shadow_publication_adapter_returns_stable_safe_errors_for_invalid_inputs() -> None:
    from flowweaver_runtime_client.publication_adapter import publish_shadow_runtime_publication

    runtime_client = FakeRuntimeClient()
    publication = ready_publication(ack_count=1)

    invalid_publication = dict(publication)
    invalid_publication["verdict"] = "rejected"
    assert await publish_shadow_runtime_publication(invalid_publication, runtime_client=runtime_client) == {
        "ok": False,
        "operation": "publish_shadow_runtime_publication",
        "error_code": "invalid_publication",
    }

    invalid_start = dict(publication)
    invalid_start["start_request"] = {"operation": "start_transaction", "workflow_id": publication["workflow_id"]}
    assert await publish_shadow_runtime_publication(invalid_start, runtime_client=runtime_client) == {
        "ok": False,
        "operation": "publish_shadow_runtime_publication",
        "error_code": "invalid_start_payload",
    }

    invalid_ack = dict(publication)
    ack_bridge = dict(publication["ack_bridge"])
    ack_bridge["updates"] = [{"event_type": "record_delivery_ack", "delivery_key": "runtime_event_delivery_ack_bad"}]
    invalid_ack["ack_bridge"] = ack_bridge
    assert await publish_shadow_runtime_publication(invalid_ack, runtime_client=runtime_client) == {
        "ok": False,
        "operation": "publish_shadow_runtime_publication",
        "error_code": "invalid_delivery_ack_update",
    }


@pytest.mark.asyncio
async def test_shadow_publication_adapter_rejects_platform_marker_ids_without_echoing_them() -> None:
    from flowweaver_runtime_client.publication_adapter import publish_shadow_runtime_publication

    unsafe_id = "runtime_tx_shadow_chatbad"
    publication = ready_publication(ack_count=1)
    publication["workflow_id"] = unsafe_id
    publication["transaction_id"] = unsafe_id
    publication["runtime_identity"] = {
        "type": "flowweaver.gateway.runtime_identity.v0",
        "strategy": "shadow_ref_hash_v0",
        "transaction_id": unsafe_id,
        "workflow_id": unsafe_id,
        "idempotency_key": "runtime_event_start_shadow_chatbad",
    }
    start_request = dict(publication["start_request"])
    start_request["workflow_id"] = unsafe_id
    start_payload = dict(start_request["start_payload"])
    start_payload["transaction_id"] = unsafe_id
    start_payload["idempotency_key"] = "runtime_event_start_shadow_chatbad"
    start_request["start_payload"] = start_payload
    publication["start_request"] = start_request

    result = await publish_shadow_runtime_publication(publication, runtime_client=FakeRuntimeClient())

    assert result == {
        "ok": False,
        "operation": "publish_shadow_runtime_publication",
        "error_code": "invalid_publication",
    }
    assert unsafe_id not in repr(result)


@pytest.mark.asyncio
async def test_shadow_publication_adapter_runtime_errors_do_not_echo_raw_values() -> None:
    from flowweaver_runtime_client.publication_adapter import publish_shadow_runtime_publication

    publication = ready_publication(ack_count=1)

    result = await publish_shadow_runtime_publication(publication, runtime_client=RuntimeClientThatLeaks())
    rendered = repr(result).lower()

    assert result == {
        "ok": False,
        "operation": "publish_shadow_runtime_publication",
        "error_code": "runtime_error",
    }
    assert publication["workflow_id"] not in rendered
    assert PRIVATE_MESSAGE_ID not in rendered
    assert SECRET_SHAPED.lower() not in rendered
    assert "boom" not in rendered


def test_shadow_publication_adapter_source_has_no_runtime_lifecycle_or_gateway_wiring() -> None:
    source_path = PHASE5C_SRC / "flowweaver_runtime_client" / "publication_adapter.py"
    source = source_path.read_text(encoding="utf-8")
    lowered = source.lower()
    tree = ast.parse(source)

    forbidden_markers = (
        "temporalio",
        "import gateway",
        "from gateway",
        "gateway.platforms",
        "flowweaver_temporal_poc.workflows",
        "client.connect",
        "start_workflow",
        "execute_update",
        "subprocess",
        "docker",
        "worker",
        "factory",
        "address",
        "service lifecycle",
        "systemctl",
        "config.yaml",
    )
    assert not [marker for marker in forbidden_markers if marker in lowered]

    forbidden_modules = {"subprocess", "socket", "os", "temporalio", "mcp", "gateway"}
    forbidden_calls = {"open", "compile", "eval", "exec", "system", "popen", "run", "Popen", "write_text"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(alias.name.split(".")[0] in forbidden_modules for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in forbidden_modules
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_calls
