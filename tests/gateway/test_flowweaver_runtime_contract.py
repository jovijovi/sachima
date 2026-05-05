"""Tests for the FlowWeaver Phase 5A runtime ingress contract."""

from __future__ import annotations

import copy
from collections.abc import Iterator, Mapping
from typing import Any

from gateway.flowweaver_mock_durable import (
    FLOWWEAVER_MOCK_DURABLE_ACCEPTED,
    consume_flowweaver_shadow_corpus_as_mock_durable_state,
)
from gateway.flowweaver_runtime_contract import (
    FLOWWEAVER_RUNTIME_ACCEPTED,
    FLOWWEAVER_RUNTIME_CONTRACT_TYPE,
    FLOWWEAVER_RUNTIME_ENVELOPE_TYPE,
    FLOWWEAVER_RUNTIME_MODEL_VERSION,
    FLOWWEAVER_RUNTIME_REJECTED,
    build_flowweaver_runtime_ingress_envelope,
    describe_flowweaver_runtime_ingress_contract,
)
from gateway.flowweaver_shadow import (
    attach_flowweaver_shadow_snapshot,
    describe_flowweaver_shadow_consumer_contract,
    replay_flowweaver_shadow_corpus,
)
from gateway.flowweaver_shadow_dry_run import (
    FLOWWEAVER_SHADOW_DRY_RUN_PASSED,
    run_flowweaver_gateway_shadow_dry_run,
)
from gateway.progress.events import TransactionSnapshot


EXPECTED_EVENTS = [
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

FORBIDDEN_MATERIAL = [
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
]

PRIVATE_MESSAGE_ID = "om_" + "private_message"
PRIVATE_CHAT_ID = "oc_" + "private_chat"


class FlickeringMapping(Mapping[str, Any]):
    def __init__(self, safe: dict[str, Any], unsafe: dict[str, Any]) -> None:
        self._safe = safe
        self._unsafe = unsafe
        self._reads: dict[str, int] = {}

    def __iter__(self) -> Iterator[str]:
        return iter(self._safe)

    def __len__(self) -> int:
        return len(self._safe)

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        self._reads[key] = self._reads.get(key, 0) + 1
        if self._reads[key] > 1 and key in self._unsafe:
            return self._unsafe[key]
        return self._safe.get(key, default)


def make_snapshot(*, index: int = 0) -> TransactionSnapshot:
    return TransactionSnapshot(
        transaction_id=f"session_runtime_contract_{index}",
        title="Runtime ingress contract task",
        status="completed",
        started_at=1000.0 + index,
        updated_at=1002.0 + index,
        completed_at=1002.0 + index,
        recent_operations=(),
    )


def make_shadow_agent_result(*, index: int = 0) -> dict[str, Any]:
    agent_result: dict[str, Any] = {
        "final_response": "done",
        "delivery_state": {
            "final_text": {"sent": True, "reason": "stream_final_response"},
            "rich_cards_sent": [],
        },
    }
    attached = attach_flowweaver_shadow_snapshot(
        agent_result,
        make_snapshot(index=index),
        enabled=True,
        final_text="done",
    )
    assert attached is not None
    return agent_result


def make_runtime_sources(*, count: int = 1, include_dry_run: bool = True) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any] | None,
]:
    agent_results = [make_shadow_agent_result(index=index) for index in range(count)]
    descriptor = describe_flowweaver_shadow_consumer_contract()
    corpus = replay_flowweaver_shadow_corpus(agent_results, attempts=2)
    assert corpus["verdict"] == "passed"
    projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, corpus)
    assert projection["verdict"] == FLOWWEAVER_MOCK_DURABLE_ACCEPTED
    dry_run_summary = None
    if include_dry_run:
        assert count == 1
        dry_run_summary = run_flowweaver_gateway_shadow_dry_run(agent_results[0])
        assert dry_run_summary["verdict"] == FLOWWEAVER_SHADOW_DRY_RUN_PASSED
    return descriptor, corpus, projection, dry_run_summary


def test_runtime_ingress_contract_describes_allowed_inputs_and_forbidden_side_effects() -> None:
    contract = describe_flowweaver_runtime_ingress_contract()

    assert contract["type"] == FLOWWEAVER_RUNTIME_CONTRACT_TYPE
    assert contract["contract_version"] == "flowweaver.v0"
    assert contract["runtime_model_version"] == FLOWWEAVER_RUNTIME_MODEL_VERSION
    assert contract["allowed_consumer_inputs"] == [
        "shadow_consumer_contract",
        "shadow_replay_corpus",
        "mock_durable_projection",
        "shadow_dry_run_summary_optional",
    ]
    assert contract["allowed_runtime_events"] == EXPECTED_EVENTS
    assert contract["claim_check_policy"] == {
        "mode": "references_only",
        "allowed_reference_fields": ["ref", "kind", "count", "size", "checksum_hint"],
        "forbidden_material": FORBIDDEN_MATERIAL,
    }
    assert contract["forbidden_side_effects"] == ["send", "edit", "render", "persist", "temporal", "log"]
    assert contract["side_effects"] == []


def test_runtime_ingress_envelope_accepts_descriptor_corpus_mock_projection_and_dry_run_summary() -> None:
    descriptor, corpus, projection, dry_run_summary = make_runtime_sources(count=1)

    envelope = build_flowweaver_runtime_ingress_envelope(
        descriptor,
        corpus,
        projection,
        dry_run_summary,
    )

    assert envelope["type"] == FLOWWEAVER_RUNTIME_ENVELOPE_TYPE
    assert envelope["verdict"] == FLOWWEAVER_RUNTIME_ACCEPTED
    assert envelope["reason"] == "ok"
    assert envelope["contract_type"] == FLOWWEAVER_RUNTIME_CONTRACT_TYPE
    assert envelope["contract_version"] == "flowweaver.v0"
    assert envelope["runtime_model_version"] == FLOWWEAVER_RUNTIME_MODEL_VERSION
    assert envelope["source_contract_type"] == descriptor["type"]
    assert envelope["source_corpus_type"] == corpus["type"]
    assert envelope["source_mock_durable_type"] == projection["type"]
    assert envelope["source_dry_run_type"] == dry_run_summary["type"]
    assert envelope["entry_count"] == 1
    assert envelope["record_counts"] == {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1}
    assert envelope["side_effects"] == []
    assert envelope["checks"] == {
        "runtime_contract_valid": True,
        "source_contract_valid": True,
        "replay_corpus_passed": True,
        "mock_durable_accepted": True,
        "dry_run_summary_valid": True,
        "record_counts_match_entries": True,
        "payloads_absent": True,
        "claim_check_references_only": True,
        "side_effects_absent": True,
    }


def test_runtime_ingress_envelope_projects_counts_events_and_claim_check_requirements_only() -> None:
    descriptor, corpus, projection, _dry_run_summary = make_runtime_sources(count=3, include_dry_run=False)

    envelope = build_flowweaver_runtime_ingress_envelope(descriptor, corpus, projection)
    rendered = repr(envelope).lower()

    assert envelope["verdict"] == FLOWWEAVER_RUNTIME_ACCEPTED
    assert envelope["entry_count"] == 3
    assert envelope["record_counts"] == {"transactions": 1, "intents": 3, "artifacts": 3, "deliveries": 3}
    assert envelope["allowed_runtime_events"] == EXPECTED_EVENTS
    assert envelope["claim_check_policy"]["mode"] == "references_only"
    assert envelope["claim_check_policy"]["forbidden_material"] == FORBIDDEN_MATERIAL
    assert envelope["idempotency"] == {
        "strategy": "synthetic_index_v0",
        "transaction_key": "runtime_tx_replay_corpus",
        "intent_key_prefix": "runtime_intent_",
        "artifact_key_prefix": "runtime_artifact_",
        "delivery_key_prefix": "runtime_delivery_",
    }
    assert "records" not in envelope
    assert "session_runtime_contract" not in rendered
    assert "flowweaver_shadow_snapshot" not in rendered
    assert "flowweaver_shadow_capture" not in rendered


def test_runtime_ingress_rejects_raw_snapshot_capture_or_agent_result_without_echoing_values() -> None:
    descriptor, corpus, projection, dry_run_summary = make_runtime_sources(count=1)
    raw_agent_result = make_shadow_agent_result(index=9)
    raw_agent_result["raw_command"] = "curl https://example.invalid --" + "token" + "=abc123"
    raw_agent_result["message_id"] = PRIVATE_MESSAGE_ID

    for raw_value in (
        raw_agent_result,
        raw_agent_result["flowweaver_shadow_snapshot"],
        raw_agent_result["flowweaver_shadow_capture"],
    ):
        envelope = build_flowweaver_runtime_ingress_envelope(raw_value, corpus, projection, dry_run_summary)
        rendered = repr(envelope).lower()
        assert envelope["verdict"] == FLOWWEAVER_RUNTIME_REJECTED
        assert envelope["reason"] == "invalid_contract"
        assert envelope["entry_count"] == 0
        assert envelope["side_effects"] == []
        assert "abc123" not in rendered
        assert PRIVATE_MESSAGE_ID not in rendered


def test_runtime_ingress_rejects_temporal_client_like_objects() -> None:
    descriptor, corpus, projection, dry_run_summary = make_runtime_sources(count=1)

    class TemporalClientLike:
        namespace = "default"
        task_queue = "unsafe-task-queue"

        def unsafe_runtime_entrypoint(self) -> None:
            raise AssertionError("must not be called")

        def __repr__(self) -> str:
            return "TemporalClient(unsafe_namespace)"

    envelope = build_flowweaver_runtime_ingress_envelope(
        descriptor,
        corpus,
        TemporalClientLike(),
        dry_run_summary,
    )
    rendered = repr(envelope).lower()

    assert envelope["verdict"] == FLOWWEAVER_RUNTIME_REJECTED
    assert envelope["reason"] == "mock_durable_rejected"
    assert "unsafe_namespace" not in rendered
    assert "unsafe-task-queue" not in rendered
    assert envelope["side_effects"] == []


def test_runtime_ingress_rejects_platform_ack_payloads_and_private_ids() -> None:
    descriptor, corpus, projection, _dry_run_summary = make_runtime_sources(count=1, include_dry_run=False)
    ack_summary = {
        "type": "flowweaver.gateway.shadow_dry_run.v0",
        "verdict": "passed",
        "reason": "ok",
        "entry_count": 1,
        "delivery_ack": {"message_id": PRIVATE_MESSAGE_ID, "chat_id": PRIVATE_CHAT_ID},
        "side_effects": [],
    }

    envelope = build_flowweaver_runtime_ingress_envelope(descriptor, corpus, projection, ack_summary)
    rendered = repr(envelope).lower()

    assert envelope["verdict"] == FLOWWEAVER_RUNTIME_REJECTED
    assert envelope["reason"] == "invalid_dry_run"
    assert PRIVATE_MESSAGE_ID not in rendered
    assert PRIVATE_CHAT_ID not in rendered
    assert envelope["side_effects"] == []


def test_runtime_ingress_rejects_hostile_mapping_and_mutating_keys() -> None:
    descriptor, corpus, projection, dry_run_summary = make_runtime_sources(count=1)
    hostile = FlickeringMapping(descriptor, {"type": PRIVATE_MESSAGE_ID})

    envelope = build_flowweaver_runtime_ingress_envelope(hostile, corpus, projection, dry_run_summary)
    rendered = repr(envelope).lower()

    assert envelope["verdict"] == FLOWWEAVER_RUNTIME_REJECTED
    assert envelope["reason"] == "invalid_contract"
    assert PRIVATE_MESSAGE_ID not in rendered

    mutations: list[str] = []

    class MutatingKey(str):
        def __eq__(self, other: object) -> bool:
            mutations.append("eq")
            return super().__eq__(other)

        def __hash__(self) -> int:
            return str.__hash__(self)

    keyed = dict(descriptor)
    keyed[MutatingKey("type")] = keyed.pop("type")
    envelope = build_flowweaver_runtime_ingress_envelope(keyed, corpus, projection, dry_run_summary)

    assert envelope["verdict"] == FLOWWEAVER_RUNTIME_REJECTED
    assert envelope["reason"] == "invalid_contract"
    assert mutations == []


def test_runtime_ingress_rejects_post_validation_reread_attacks() -> None:
    descriptor, corpus, projection, dry_run_summary = make_runtime_sources(count=1)
    unsafe_projection = copy.deepcopy(projection)
    unsafe_projection["records"]["deliveries"] = [
        {"delivery_id": PRIVATE_MESSAGE_ID, "artifact_id": "mock_artifact_0", "surface": "mock_consumer", "status": "observed"}
    ]
    flickering_projection = FlickeringMapping(projection, {"records": unsafe_projection["records"]})

    envelope = build_flowweaver_runtime_ingress_envelope(descriptor, corpus, flickering_projection, dry_run_summary)
    rendered = repr(envelope).lower()

    assert envelope["verdict"] == FLOWWEAVER_RUNTIME_REJECTED
    assert envelope["reason"] == "mock_durable_rejected"
    assert PRIVATE_MESSAGE_ID not in rendered
    assert envelope["side_effects"] == []


def test_runtime_ingress_output_omits_raw_command_stdout_card_json_and_secrets() -> None:
    descriptor, corpus, projection, dry_run_summary = make_runtime_sources(count=1)
    projection["records"]["transaction"]["raw_command"] = "run --" + "token" + "=abc123"
    projection["records"]["artifacts"][0]["stdout"] = "secret " + "sk-" + "123456789012"
    projection["records"]["deliveries"][0]["card_json"] = {"message_id": PRIVATE_MESSAGE_ID}

    envelope = build_flowweaver_runtime_ingress_envelope(descriptor, corpus, projection, dry_run_summary)
    rendered = repr(envelope).lower()

    assert envelope["verdict"] == FLOWWEAVER_RUNTIME_REJECTED
    assert envelope["reason"] == "mock_durable_rejected"
    assert "abc123" not in rendered
    assert "***" not in rendered
    assert PRIVATE_MESSAGE_ID not in rendered


def test_runtime_ingress_side_effects_are_always_empty() -> None:
    descriptor, corpus, projection, dry_run_summary = make_runtime_sources(count=1)
    accepted = build_flowweaver_runtime_ingress_envelope(descriptor, corpus, projection, dry_run_summary)
    rejected = build_flowweaver_runtime_ingress_envelope({}, {}, {}, {"message_id": PRIVATE_MESSAGE_ID})

    assert accepted["side_effects"] == []
    assert rejected["side_effects"] == []
