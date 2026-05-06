"""Phase 5G delivery cardinality and ACK slot parity tests."""

from __future__ import annotations

import ast
import copy
import subprocess
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


SAFE_CLAIM_CHECK_POLICY = {
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
}
SAFE_ALLOWED_EVENTS = [
    "start_transaction",
    "record_operation",
    "publish_artifact",
    "plan_delivery",
    "record_delivery_ack",
    "approve_intent",
    "reject_intent",
    "cancel_transaction",
    "resume_after_user_input",
]


def make_shadow_agent_result(*, index: int = 0, rich_card_count: int = 0) -> dict[str, Any]:
    agent_result: dict[str, Any] = {
        "final_response": "done",
        "delivery_state": {
            "final_text": {"sent": True, "reason": "stream_final_response"},
            "rich_cards_sent": [
                {"type": "result_card", "message_id": "om_" + f"card_{item}"}
                for item in range(rich_card_count)
            ],
        },
    }
    snapshot = TransactionSnapshot(
        transaction_id=f"session_phase5g_delivery_{index}",
        title="Phase 5G delivery cardinality task",
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


def ready_publication(*, index: int = 0, rich_card_count: int = 1) -> dict[str, object]:
    publication = build_flowweaver_shadow_runtime_publication(
        make_shadow_agent_result(index=index, rich_card_count=rich_card_count)
    )
    assert publication["verdict"] == "ready"
    return publication


def assert_no_private_or_credential_material(value: object) -> None:
    rendered = repr(value).lower()
    for forbidden in (
        PRIVATE_MESSAGE_ID,
        PRIVATE_CHAT_ID,
        PRIVATE_USER_ID,
        CRED_SHAPED,
        "session_phase5g_delivery",
        "om_card",
        "adapter failed",
        "raw_payload",
    ):
        assert forbidden not in rendered


@pytest.mark.asyncio
async def test_phase5g_shadow_publication_sets_delivery_count_from_ack_surfaces() -> None:
    publication = ready_publication(index=1, rich_card_count=1)
    payload = publication["start_request"]["start_payload"]
    updates = publication["ack_bridge"]["updates"]

    assert payload["entry_count"] == 1
    assert payload["record_counts"] == {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 2}
    assert [update["target_id"] for update in updates] == ["runtime_delivery_0", "runtime_delivery_1"]
    assert [update["surface"] for update in updates] == ["final_text", "rich_card"]
    assert_no_private_or_credential_material(publication)


@pytest.mark.asyncio
async def test_phase5g_reconciles_rich_card_publication_with_runtime_snapshot() -> None:
    from flowweaver_runtime_client.reconciliation_harness import (
        InMemoryFlowWeaverRuntimeClient,
        reconcile_shadow_runtime_publication,
    )

    publication = ready_publication(index=2, rich_card_count=1)
    runtime_client = InMemoryFlowWeaverRuntimeClient()

    result = await reconcile_shadow_runtime_publication(publication, runtime_client=runtime_client)
    snapshot_result = await runtime_client.query_snapshot(publication["workflow_id"])

    assert result["ok"] is True
    assert result["status"] == "reconciled"
    assert result["reconciliation"]["record_counts"] == {
        "transactions": 1,
        "intents": 1,
        "artifacts": 1,
        "deliveries": 2,
    }
    assert result["reconciliation"]["ack_statuses"] == ["applied", "applied"]
    assert result["reconciliation"]["applied_event_count"] == 2
    assert snapshot_result["snapshot"]["counts"] == {"intents": 1, "artifacts": 1, "deliveries": 2}
    assert snapshot_result["snapshot"]["delivery_statuses"] == {
        "runtime_delivery_0": "sent",
        "runtime_delivery_1": "sent",
    }
    assert_no_private_or_credential_material(result)


@pytest.mark.asyncio
async def test_phase5g_replay_of_rich_card_publication_is_idempotent() -> None:
    from flowweaver_runtime_client.reconciliation_harness import (
        InMemoryFlowWeaverRuntimeClient,
        reconcile_shadow_runtime_publication,
    )

    publication = ready_publication(index=3, rich_card_count=1)
    runtime_client = InMemoryFlowWeaverRuntimeClient()

    first = await reconcile_shadow_runtime_publication(publication, runtime_client=runtime_client)
    second = await reconcile_shadow_runtime_publication(publication, runtime_client=runtime_client)
    snapshot_result = await runtime_client.query_snapshot(publication["workflow_id"])

    assert first["ok"] is True
    assert first["reconciliation"]["ack_statuses"] == ["applied", "applied"]
    assert first["reconciliation"]["applied_event_count"] == 2
    assert second["ok"] is True
    assert second["reconciliation"]["ack_statuses"] == ["duplicate", "duplicate"]
    assert second["reconciliation"]["applied_event_count"] == 2
    assert snapshot_result["snapshot"]["applied_event_count"] == 2
    assert list(snapshot_result["snapshot"]["delivery_statuses"]) == ["runtime_delivery_0", "runtime_delivery_1"]


def test_phase5g_delivery_ack_projection_caps_total_updates_at_twenty() -> None:
    publication = ready_publication(index=4, rich_card_count=25)
    payload = publication["start_request"]["start_payload"]
    updates = publication["ack_bridge"]["updates"]

    assert len(updates) == 20
    assert [update["target_id"] for update in updates] == [f"runtime_delivery_{index}" for index in range(20)]
    assert [update["surface"] for update in updates] == ["final_text", *("rich_card" for _ in range(19))]
    assert payload["record_counts"] == {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 20}
    assert_no_private_or_credential_material(publication)


def test_phase5g_start_payload_validation_allows_extra_delivery_slots_but_rejects_invalid_counts() -> None:
    from flowweaver_temporal_poc.payloads import build_runtime_start_payload, validate_start_payload

    valid = build_runtime_start_payload(
        transaction_id="runtime_tx_shadow_11111111111111111111",
        idempotency_key="runtime_event_start_shadow_11111111111111111111",
        entry_count=1,
        record_counts={"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 2},
        allowed_runtime_events=tuple(SAFE_ALLOWED_EVENTS),
        claim_check_policy=copy.deepcopy(SAFE_CLAIM_CHECK_POLICY),
    )
    validate_start_payload(valid)

    invalid_counts = (
        {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 0},
        {"transactions": 1, "intents": 2, "artifacts": 2, "deliveries": 1},
        {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 21},
    )
    for counts in invalid_counts:
        with pytest.raises(ValueError, match="invalid_start_payload") as excinfo:
            build_runtime_start_payload(
                transaction_id="runtime_tx_shadow_22222222222222222222",
                idempotency_key="runtime_event_start_shadow_22222222222222222222",
                entry_count=1,
                record_counts=counts,
                allowed_runtime_events=tuple(SAFE_ALLOWED_EVENTS),
                claim_check_policy=copy.deepcopy(SAFE_CLAIM_CHECK_POLICY),
            )
        assert str(excinfo.value) == "invalid_start_payload"
        assert_no_private_or_credential_material(excinfo.value)


def test_phase5g_workflow_source_initializes_delivery_statuses_from_record_count() -> None:
    source_path = PHASE5B_SRC / "flowweaver_temporal_poc" / "workflows.py"
    source = source_path.read_text(encoding="utf-8")

    assert 'payload.record_counts["deliveries"]' in source
    assert 'range(payload.entry_count)}' not in source.split("self._delivery_statuses", maxsplit=1)[1].split("\n", maxsplit=1)[0]


def test_phase5g_source_has_no_gateway_runtime_lifecycle_or_platform_wiring() -> None:
    implementation_paths = [
        "gateway/flowweaver_shadow_publisher.py",
        "prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py",
        "prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py",
        "prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py",
    ]
    base = subprocess.check_output(
        ["git", "merge-base", "HEAD", "origin/feature/sachima-channel"], cwd=ROOT, text=True
    ).strip()
    diff = subprocess.check_output(["git", "diff", "--unified=0", base, "--", *implementation_paths], cwd=ROOT, text=True)
    added_lines = [line[1:].strip() for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]
    joined = "\n".join(added_lines).lower()

    forbidden_markers = (
        "importlib",
        "__import__",
        "getattr(",
        "client.connect",
        "connect_local_temporal",
        "testworkflowenvironment",
        "start_workflow",
        "get_workflow_handle",
        "execute_update",
        "workflow.signal",
        "@workflow.signal",
        "subprocess",
        "docker",
        "systemctl",
        "daemon",
        "socket.",
        "httpserver",
        "write_text",
        "write_bytes",
        "gateway.run",
        "gateway.platforms",
        "tools.registry",
        "global registry",
        "print(",
        "logger.",
        "logging.",
        "repr(agent_result",
        "repr(delivery_state",
    )
    assert not [marker for marker in forbidden_markers if marker in joined]

    for relative_path in implementation_paths:
        source_path = ROOT / relative_path
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = {alias.name.split(".")[0] for alias in node.names}
                if relative_path.endswith("workflows.py"):
                    imported.discard("temporalio")
                assert not (imported & {"subprocess", "socket", "docker", "tools"})
            elif isinstance(node, ast.ImportFrom) and node.module:
                module_root = node.module.split(".")[0]
                if not relative_path.endswith("workflows.py"):
                    assert module_root != "temporalio"
                assert not node.module.startswith(("gateway.platforms", "gateway.run", "tools.registry"))
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id not in {"eval", "exec", "compile", "open", "print", "__import__"}
                elif isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in {
                        "connect",
                        "start_workflow",
                        "get_workflow_handle",
                        "execute_update",
                        "write_text",
                        "write_bytes",
                        "system",
                        "popen",
                    }
