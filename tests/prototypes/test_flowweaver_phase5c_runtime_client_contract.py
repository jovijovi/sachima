"""Safe request/result contract tests for FlowWeaver Phase 5C runtime client."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PHASE5B_SRC = ROOT / "prototypes" / "flowweaver_phase5b_temporal_poc" / "src"
PHASE5C_SRC = ROOT / "prototypes" / "flowweaver_phase5c_runtime_client" / "src"
for path in (PHASE5C_SRC, PHASE5B_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from flowweaver_temporal_poc.payloads import build_runtime_start_payload, start_signature_from_payload  # noqa: E402


SAFE_START_FIELDS = {
    "transaction_id": "runtime_tx_replay_corpus",
    "idempotency_key": "runtime_event_start_runtime_tx_replay_corpus",
    "entry_count": 1,
    "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
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

SAFE_START_PAYLOAD = build_runtime_start_payload(**SAFE_START_FIELDS)

SAFE_SNAPSHOT = {
    "type": "flowweaver.temporal_poc.snapshot.v0",
    "version": "flowweaver.temporal_poc.v0",
    "transaction_id": "runtime_tx_replay_corpus",
    "status": "running",
    "entry_count": 1,
    "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
    "start_signature": start_signature_from_payload(SAFE_START_PAYLOAD),
    "counts": {"intents": 1, "artifacts": 1, "deliveries": 1},
    "intent_statuses": {"runtime_intent_0": "pending"},
    "artifact_statuses": {"runtime_artifact_0": "available"},
    "delivery_statuses": {"runtime_delivery_0": "planned"},
    "applied_event_count": 0,
    "resume_count": 0,
    "side_effects": [],
}


class HostileMapping(Mapping[str, object]):
    def __iter__(self) -> Iterator[str]:
        return iter(SAFE_START_FIELDS)

    def __len__(self) -> int:
        return len(SAFE_START_FIELDS)

    def __getitem__(self, key: str) -> object:
        return SAFE_START_FIELDS[key]


class MutatingString(str):
    def __new__(cls, value: str, touched: list[str]):
        obj = str.__new__(cls, value)
        obj.touched = touched
        return obj

    def __eq__(self, other: object) -> bool:  # pragma: no cover - test fails if called
        self.touched.append("eq-called")
        return super().__eq__(other)


def test_general_contract_import_does_not_import_temporalio_mcp_or_workflow_modules() -> None:
    for module_name in (
        "flowweaver_runtime_client",
        "flowweaver_runtime_client.contracts",
        "mcp",
        "flowweaver_temporal_poc.client",
        "flowweaver_temporal_poc.workflows",
    ):
        sys.modules.pop(module_name, None)
    for module_name in list(sys.modules):
        if module_name == "temporalio" or module_name.startswith("temporalio."):
            sys.modules.pop(module_name, None)

    package = importlib.import_module("flowweaver_runtime_client")
    contracts = importlib.import_module("flowweaver_runtime_client.contracts")

    assert package.FLOWWEAVER_RUNTIME_CLIENT_VERSION == "flowweaver.runtime_client.v0"
    assert contracts.ALLOWED_OPERATIONS == (
        "start_transaction",
        "query_snapshot",
        "record_delivery_ack",
        "approve_intent",
        "reject_intent",
        "cancel_transaction",
        "resume_after_user_input",
    )
    assert "temporalio" not in sys.modules
    assert "mcp" not in sys.modules
    assert "flowweaver_temporal_poc.client" not in sys.modules
    assert "flowweaver_temporal_poc.workflows" not in sys.modules


def test_closed_set_operation_validation_rejects_unknown_operation() -> None:
    from flowweaver_runtime_client.contracts import validate_operation

    assert validate_operation("query_snapshot") == "query_snapshot"
    with pytest.raises(ValueError, match="invalid_operation"):
        validate_operation("record_operation")
    with pytest.raises(ValueError, match="invalid_operation"):
        validate_operation(MutatingString("query_snapshot", []))


def test_safe_start_payload_rejects_hostile_mapping_and_mutating_string_values_without_equality_side_effects() -> None:
    from flowweaver_runtime_client.contracts import build_start_payload_from_safe_fields

    with pytest.raises(ValueError, match="invalid_start_payload"):
        build_start_payload_from_safe_fields(HostileMapping())

    touched: list[str] = []
    hostile = dict(SAFE_START_FIELDS)
    hostile["transaction_id"] = MutatingString("runtime_tx_replay_corpus", touched)
    with pytest.raises(ValueError, match="invalid_start_payload"):
        build_start_payload_from_safe_fields(hostile)
    assert touched == []


def test_private_markers_and_raw_fields_are_rejected_at_request_boundary() -> None:
    from flowweaver_runtime_client.contracts import sanitize_tool_request, validate_claim_ref, validate_workflow_id

    with pytest.raises(ValueError, match="invalid_workflow_id"):
        validate_workflow_id("runtime_tx_ou_private_marker")
    with pytest.raises(ValueError, match="invalid_claim_ref"):
        validate_claim_ref("claim_ref_chat_private_marker")
    with pytest.raises(ValueError, match="unsafe_request"):
        sanitize_tool_request(
            {
                "operation": "query_snapshot",
                "workflow_id": "runtime_tx_safe_query",
                "raw_payload": "private material must be rejected",
            }
        )


def test_result_envelope_uses_only_allowed_top_level_fields_and_sanitizes_nested_snapshot() -> None:
    from flowweaver_runtime_client.contracts import make_success_result

    hostile_snapshot = dict(SAFE_SNAPSHOT)
    hostile_snapshot.update(
        {
            "raw_payload": "drop me",
            "tool_output": "drop me too",
            "platform_payload": {"chat_id": "oc_" + "private"},
            "chat_id": "oc_" + "private",
            "user_id": "ou_" + "private",
        }
    )

    result = make_success_result(
        operation="query_snapshot",
        workflow_id="runtime_tx_safe_query",
        snapshot=hostile_snapshot,
    )

    assert set(result) <= {"ok", "operation", "workflow_id", "transaction_id", "status", "snapshot", "error_code"}
    assert result["ok"] is True
    assert result["operation"] == "query_snapshot"
    assert result["snapshot"]["transaction_id"] == "runtime_tx_replay_corpus"
    rendered = repr(result)
    for forbidden in ("raw_payload", "tool_output", "platform_payload", "chat_id", "user_id", "oc_private", "ou_private"):
        assert forbidden not in rendered


def test_malicious_nested_status_maps_are_rejected_not_passed_through() -> None:
    from flowweaver_runtime_client.contracts import make_success_result

    snapshot = dict(SAFE_SNAPSHOT)
    snapshot["delivery_statuses"] = {"runtime_delivery_0": "planned", "runtime_delivery_oc_private": "sent"}

    with pytest.raises(ValueError, match="unsafe_tool_output"):
        make_success_result(operation="query_snapshot", workflow_id="runtime_tx_safe_query", snapshot=snapshot)
