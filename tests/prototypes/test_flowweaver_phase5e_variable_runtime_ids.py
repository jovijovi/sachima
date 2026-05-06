"""Phase 5E variable synthetic runtime ID contract tests."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest

from gateway.flowweaver_mock_durable import consume_flowweaver_shadow_corpus_as_mock_durable_state
from gateway.flowweaver_runtime_contract import build_flowweaver_runtime_ingress_envelope
from gateway.flowweaver_runtime_identity import derive_flowweaver_runtime_identity
from gateway.flowweaver_shadow import (
    attach_flowweaver_shadow_snapshot,
    describe_flowweaver_shadow_consumer_contract,
    get_flowweaver_shadow_capture,
    replay_flowweaver_shadow_corpus,
)
from gateway.flowweaver_shadow_dry_run import attach_flowweaver_gateway_shadow_dry_run
from gateway.progress.events import TransactionSnapshot

ROOT = Path(__file__).resolve().parents[2]
PHASE5B_SRC = ROOT / "prototypes" / "flowweaver_phase5b_temporal_poc" / "src"
PHASE5C_SRC = ROOT / "prototypes" / "flowweaver_phase5c_runtime_client" / "src"
for path in (PHASE5C_SRC, PHASE5B_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from flowweaver_runtime_client.contracts import build_start_payload_from_safe_fields  # noqa: E402
from flowweaver_temporal_poc.payloads import (  # noqa: E402
    ALLOWED_RUNTIME_EVENTS,
    RUNTIME_START_IDEMPOTENCY_KEY,
    RUNTIME_TRANSACTION_ID,
    RuntimeStartPayload,
    build_start_payload_from_ingress_envelope,
    validate_start_payload,
)

_VARIABLE_SUFFIX = "0123456789abcdefabcd"
_VARIABLE_TRANSACTION_ID = f"runtime_tx_shadow_{_VARIABLE_SUFFIX}"
_VARIABLE_START_EVENT_KEY = f"runtime_event_start_shadow_{_VARIABLE_SUFFIX}"


CLAIM_CHECK_POLICY = {
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


def make_snapshot(*, index: int = 0) -> TransactionSnapshot:
    return TransactionSnapshot(
        transaction_id=f"session_phase5e_variable_{index}",
        title="Phase 5E variable runtime identity task",
        status="completed",
        started_at=1000.0 + index,
        updated_at=1002.0 + index,
        completed_at=1002.0 + index,
        recent_operations=(),
    )


def make_shadow_agent_result(*, index: int = 0) -> dict[str, Any]:
    agent_result: dict[str, Any] = {
        "final_response": "done",
        "delivery_state": {"final_text": {"sent": True}, "rich_cards_sent": []},
    }
    attached = attach_flowweaver_shadow_snapshot(agent_result, make_snapshot(index=index), enabled=True, final_text="done")
    assert attached is not None
    dry_run = attach_flowweaver_gateway_shadow_dry_run(agent_result, enabled=True)
    assert dry_run is not None and dry_run["verdict"] == "passed"
    return agent_result


def make_runtime_sources(*, index: int = 0) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, object]]:
    agent_result = make_shadow_agent_result(index=index)
    capture = get_flowweaver_shadow_capture(agent_result)
    assert capture is not None
    identity = derive_flowweaver_runtime_identity(capture["snapshot_ref"])
    assert identity["verdict"] == "accepted"
    descriptor = describe_flowweaver_shadow_consumer_contract()
    corpus = replay_flowweaver_shadow_corpus([agent_result], attempts=2)
    assert corpus["verdict"] == "passed"
    projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, corpus)
    assert projection["verdict"] == "accepted"
    dry_run = agent_result["flowweaver_shadow_dry_run"]
    return descriptor, corpus, projection, dry_run, identity


def safe_start_fields(*, transaction_id: str = _VARIABLE_TRANSACTION_ID, idempotency_key: str = _VARIABLE_START_EVENT_KEY) -> dict[str, object]:
    return {
        "transaction_id": transaction_id,
        "idempotency_key": idempotency_key,
        "entry_count": 1,
        "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
        "allowed_runtime_events": list(ALLOWED_RUNTIME_EVENTS),
        "claim_check_policy": copy.deepcopy(CLAIM_CHECK_POLICY),
    }


def test_runtime_ingress_envelope_uses_supplied_variable_runtime_identity() -> None:
    descriptor, corpus, projection, dry_run, identity = make_runtime_sources(index=1)

    envelope = build_flowweaver_runtime_ingress_envelope(
        descriptor,
        corpus,
        projection,
        dry_run,
        runtime_identity=identity,
    )

    assert envelope["verdict"] == "accepted"
    assert envelope["idempotency"] == {
        "strategy": "shadow_ref_hash_v0",
        "transaction_key": identity["transaction_id"],
        "start_event_key": identity["idempotency_key"],
        "intent_key_prefix": "runtime_intent_",
        "artifact_key_prefix": "runtime_artifact_",
        "delivery_key_prefix": "runtime_delivery_",
    }
    rendered = repr(envelope)
    assert "runtime_tx_replay_corpus" not in rendered
    assert "session_phase5e_variable" not in rendered
    assert "flowweaver_shadow_snapshot" not in rendered


def test_phase5b_and_phase5c_accept_variable_runtime_start_payloads_and_legacy_fixture() -> None:
    variable_payload = RuntimeStartPayload(
        transaction_id=_VARIABLE_TRANSACTION_ID,
        idempotency_key=_VARIABLE_START_EVENT_KEY,
        entry_count=1,
        record_counts={"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
        allowed_runtime_events=ALLOWED_RUNTIME_EVENTS,
        claim_check_policy=copy.deepcopy(CLAIM_CHECK_POLICY),
    )

    validate_start_payload(variable_payload)
    built = build_start_payload_from_safe_fields(safe_start_fields())

    assert built.transaction_id == _VARIABLE_TRANSACTION_ID
    assert built.idempotency_key == _VARIABLE_START_EVENT_KEY

    legacy_payload = RuntimeStartPayload(
        transaction_id=RUNTIME_TRANSACTION_ID,
        idempotency_key=RUNTIME_START_IDEMPOTENCY_KEY,
        entry_count=1,
        record_counts={"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
        allowed_runtime_events=ALLOWED_RUNTIME_EVENTS,
        claim_check_policy=copy.deepcopy(CLAIM_CHECK_POLICY),
    )
    validate_start_payload(legacy_payload)


def test_variable_runtime_contracts_reject_embedded_private_platform_and_secret_markers() -> None:
    markers = (
        "oc_",
        "ou_",
        "chat",
        "chatbad",
        "message",
        "messagebad",
        "platform",
        "platformbad",
        "feishu",
        "lark",
        "telegram",
        "private",
        "tok" + "en",
        "sec" + "ret",
        "pass" + "word",
        "api" + "_key",
    )

    for marker in markers:
        with pytest.raises(ValueError, match="invalid_start_payload"):
            validate_start_payload(
                RuntimeStartPayload(
                    transaction_id=f"runtime_tx_shadow_{marker}_bad",
                    idempotency_key=_VARIABLE_START_EVENT_KEY,
                    entry_count=1,
                    record_counts={"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
                    allowed_runtime_events=ALLOWED_RUNTIME_EVENTS,
                    claim_check_policy=copy.deepcopy(CLAIM_CHECK_POLICY),
                )
            )
        bad_fields = safe_start_fields(idempotency_key=f"runtime_event_start_shadow_{marker}_bad")
        with pytest.raises(ValueError, match="invalid_start_payload"):
            build_start_payload_from_safe_fields(bad_fields)


def test_start_payload_from_ingress_envelope_returns_variable_identity_from_envelope() -> None:
    descriptor, corpus, projection, dry_run, identity = make_runtime_sources(index=2)
    envelope = build_flowweaver_runtime_ingress_envelope(
        descriptor,
        corpus,
        projection,
        dry_run,
        runtime_identity=identity,
    )

    payload = build_start_payload_from_ingress_envelope(envelope)

    assert payload.transaction_id == identity["transaction_id"]
    assert payload.idempotency_key == identity["idempotency_key"]
    assert payload.transaction_id != RUNTIME_TRANSACTION_ID
    assert payload.idempotency_key != RUNTIME_START_IDEMPOTENCY_KEY
