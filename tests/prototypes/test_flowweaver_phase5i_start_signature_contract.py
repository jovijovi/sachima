"""Phase 5I reduced start payload and safe signature contract tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
PHASE5B_SRC = ROOT / "prototypes" / "flowweaver_phase5b_temporal_poc" / "src"
PHASE5C_SRC = ROOT / "prototypes" / "flowweaver_phase5c_runtime_client" / "src"
for path in (PHASE5C_SRC, PHASE5B_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

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
SAFE_CLAIM_POLICY = {
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
        "to" + "ken",
        "se" + "cret",
    ],
}
RAW_POLICY_MARKERS = (
    "allowed_runtime_events",
    "claim_check_policy",
    "forbidden_material",
    "raw_snapshot",
    "credential",
    "to" + "ken",
    "se" + "cret",
)
SYNTHETIC_ID_POLICY_MARKERS = (
    "allowed_runtime_events",
    "claim_check_policy",
    "forbidden_material",
)


def build_payload(**overrides: object):
    from flowweaver_temporal_poc.payloads import build_runtime_start_payload

    fields = {
        "transaction_id": "runtime_tx_phase5i_contract",
        "idempotency_key": "runtime_event_phase5i_contract_start",
        "entry_count": 1,
        "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 2},
        "allowed_runtime_events": list(SAFE_ALLOWED_EVENTS),
        "claim_check_policy": dict(SAFE_CLAIM_POLICY),
    }
    fields.update(overrides)
    return build_runtime_start_payload(**fields)


def assert_digest(value: object) -> None:
    assert type(value) is str
    assert value.startswith("runtime_sig_")
    body = value.removeprefix("runtime_sig_")
    assert len(body) == 64
    assert all(char in "0123456789abcdef" for char in body)


def safe_snapshot_from_signature(signature: dict[str, object]) -> dict[str, object]:
    return {
        "type": "flowweaver.temporal_poc.snapshot.v0",
        "version": "flowweaver.temporal_poc.v0",
        "transaction_id": "runtime_tx_phase5i_contract",
        "status": "running",
        "entry_count": 1,
        "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 2},
        "counts": {"intents": 1, "artifacts": 1, "deliveries": 2},
        "intent_statuses": {"runtime_intent_0": "pending"},
        "artifact_statuses": {"runtime_artifact_0": "available"},
        "delivery_statuses": {"runtime_delivery_0": "planned", "runtime_delivery_1": "planned"},
        "applied_event_count": 0,
        "resume_count": 0,
        "start_signature": signature,
        "side_effects": [],
    }


def test_phase5i_runtime_start_payload_reduces_raw_policy_to_safe_digests() -> None:
    payload = build_payload()
    rendered = repr(payload).lower()

    assert payload.transaction_id == "runtime_tx_phase5i_contract"
    assert payload.idempotency_key == "runtime_event_phase5i_contract_start"
    assert payload.record_counts["deliveries"] == 2
    assert_digest(payload.event_contract_digest)
    assert_digest(payload.claim_policy_digest)
    assert not hasattr(payload, "allowed_runtime_events")
    assert not hasattr(payload, "claim_check_policy")
    for marker in RAW_POLICY_MARKERS:
        assert marker not in rendered


def test_phase5i_start_signature_contains_idempotency_and_safe_digests_only() -> None:
    from flowweaver_temporal_poc.payloads import START_SIGNATURE_TYPE, start_signature_from_payload

    payload = build_payload()
    signature = start_signature_from_payload(payload)

    assert signature == {
        "type": START_SIGNATURE_TYPE,
        "version": "flowweaver.temporal_poc.v0",
        "idempotency_key": "runtime_event_phase5i_contract_start",
        "event_contract_digest": payload.event_contract_digest,
        "claim_policy_digest": payload.claim_policy_digest,
    }
    rendered = repr(signature).lower()
    for marker in RAW_POLICY_MARKERS:
        assert marker not in rendered


def test_phase5i_signature_changes_when_reduced_start_identity_changes() -> None:
    from flowweaver_temporal_poc.payloads import start_signature_from_payload

    payload = build_payload()
    changed_idempotency = replace(payload, idempotency_key="runtime_event_phase5i_contract_replay")
    changed_event_contract = replace(payload, event_contract_digest="runtime_sig_" + "1" * 64)
    changed_policy = replace(payload, claim_policy_digest="runtime_sig_" + "2" * 64)

    assert start_signature_from_payload(payload) != start_signature_from_payload(changed_idempotency)
    assert start_signature_from_payload(payload) != start_signature_from_payload(changed_event_contract)
    assert start_signature_from_payload(payload) != start_signature_from_payload(changed_policy)


@pytest.mark.parametrize(
    ("field", "bad_digest"),
    [
        ("event_contract_digest", "runtime_sig_allowed_runtime_events"),
        ("claim_policy_digest", "runtime_sig_claim_check_policy"),
        ("event_contract_digest", "runtime_sig_" + "g" * 64),
        ("claim_policy_digest", "runtime_sig_" + "1" * 63),
        ("claim_policy_digest", "runtime_sig_" + "1" * 65),
    ],
)
def test_phase5i_validate_start_payload_rejects_forged_non_hex_or_raw_marker_digests(
    field: str, bad_digest: str
) -> None:
    from flowweaver_temporal_poc.payloads import validate_start_payload

    forged = replace(build_payload(), **{field: bad_digest})

    with pytest.raises(ValueError, match="invalid_start_payload"):
        validate_start_payload(forged)


@pytest.mark.parametrize(
    ("field", "prefix"),
    [
        ("transaction_id", "runtime_tx_"),
        ("idempotency_key", "runtime_event_"),
    ],
)
@pytest.mark.parametrize("marker", SYNTHETIC_ID_POLICY_MARKERS)
def test_phase5i_validate_start_payload_rejects_forged_policy_markers_in_synthetic_ids(
    field: str, prefix: str, marker: str
) -> None:
    from flowweaver_temporal_poc.payloads import validate_start_payload

    forged = replace(build_payload(), **{field: prefix + marker})

    with pytest.raises(ValueError, match="invalid_start_payload"):
        validate_start_payload(forged)


@pytest.mark.parametrize("marker", SYNTHETIC_ID_POLICY_MARKERS)
def test_phase5i_runtime_contract_rejects_policy_markers_in_workflow_id(marker: str) -> None:
    from flowweaver_runtime_client.contracts import validate_workflow_id

    with pytest.raises(ValueError, match="invalid_workflow_id"):
        validate_workflow_id("runtime_tx_" + marker)


@pytest.mark.parametrize(
    ("field", "bad_digest"),
    [
        ("event_contract_digest", "runtime_sig_allowed_runtime_events"),
        ("claim_policy_digest", "runtime_sig_claim_check_policy"),
        ("event_contract_digest", "runtime_sig_" + "g" * 64),
        ("claim_policy_digest", "runtime_sig_" + "1" * 63),
        ("claim_policy_digest", "runtime_sig_" + "1" * 65),
    ],
)
def test_phase5i_snapshot_sanitizer_rejects_forged_non_hex_or_raw_marker_digests(
    field: str, bad_digest: str
) -> None:
    from flowweaver_runtime_client.contracts import sanitize_snapshot
    from flowweaver_temporal_poc.payloads import start_signature_from_payload

    signature = start_signature_from_payload(build_payload())
    forged_signature = {**signature, field: bad_digest}

    with pytest.raises(ValueError, match="unsafe_tool_output"):
        sanitize_snapshot(safe_snapshot_from_signature(forged_signature))


@pytest.mark.parametrize("marker", SYNTHETIC_ID_POLICY_MARKERS)
def test_phase5i_snapshot_sanitizer_rejects_policy_markers_in_start_signature_idempotency_key(
    marker: str,
) -> None:
    from flowweaver_runtime_client.contracts import sanitize_snapshot
    from flowweaver_temporal_poc.payloads import start_signature_from_payload

    signature = start_signature_from_payload(build_payload())
    forged_signature = {**signature, "idempotency_key": "runtime_event_" + marker}

    with pytest.raises(ValueError, match="unsafe_tool_output"):
        sanitize_snapshot(safe_snapshot_from_signature(forged_signature))


def test_phase5i_snapshot_sanitizer_accepts_safe_start_signature() -> None:
    from flowweaver_runtime_client.contracts import sanitize_snapshot
    from flowweaver_temporal_poc.payloads import start_signature_from_payload

    payload = build_payload()
    signature = start_signature_from_payload(payload)
    sanitized = sanitize_snapshot(safe_snapshot_from_signature(signature))

    assert sanitized["start_signature"] == signature


def test_phase5i_snapshot_sanitizer_rejects_raw_claim_policy_or_private_markers_in_signature() -> None:
    from flowweaver_runtime_client.contracts import sanitize_snapshot
    from flowweaver_temporal_poc.payloads import start_signature_from_payload

    payload = build_payload()
    signature = start_signature_from_payload(payload)
    raw_policy_signature = {
        **signature,
        "claim_check_policy": SAFE_CLAIM_POLICY,
    }
    private_marker_signature = {
        **signature,
        "idempotency_key": "runtime_event_om_private_marker",
    }

    with pytest.raises(ValueError, match="unsafe_tool_output"):
        sanitize_snapshot(safe_snapshot_from_signature(raw_policy_signature))
    with pytest.raises(ValueError, match="unsafe_tool_output"):
        sanitize_snapshot(safe_snapshot_from_signature(private_marker_signature))


@pytest.mark.asyncio
async def test_phase5i_in_memory_runtime_snapshot_exposes_same_safe_start_signature() -> None:
    from flowweaver_runtime_client.reconciliation_harness import InMemoryFlowWeaverRuntimeClient
    from flowweaver_temporal_poc.payloads import start_signature_from_payload

    payload = build_payload()
    runtime = InMemoryFlowWeaverRuntimeClient()

    started = await runtime.start_transaction(payload, workflow_id=payload.transaction_id)
    snapshot_result = await runtime.query_snapshot(payload.transaction_id)

    assert started["ok"] is True
    assert snapshot_result["snapshot"]["start_signature"] == start_signature_from_payload(payload)
