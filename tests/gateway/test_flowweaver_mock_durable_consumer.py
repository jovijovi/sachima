"""Tests for the FlowWeaver Phase 4G mock durable consumer."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator, Mapping
from pathlib import Path

from typing import Any

from gateway.flowweaver_mock_durable import (
    FLOWWEAVER_MOCK_DURABLE_ACCEPTED,
    FLOWWEAVER_MOCK_DURABLE_CONSUMER_TYPE,
    FLOWWEAVER_MOCK_DURABLE_REJECTED,
    consume_flowweaver_shadow_corpus_as_mock_durable_state,
)
from gateway.flowweaver_shadow import (
    FLOWWEAVER_SHADOW_CAPTURE_KEY,
    FLOWWEAVER_SHADOW_REPLAY_CORPUS_FAILED,
    FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED,
    FLOWWEAVER_SHADOW_REPLAY_CORPUS_REJECTED,
    FLOWWEAVER_SHADOW_SNAPSHOT_KEY,
    attach_flowweaver_shadow_snapshot,
    describe_flowweaver_shadow_consumer_contract,
    replay_flowweaver_shadow_corpus,
)
from gateway.progress.events import TransactionSnapshot


def make_snapshot(
    *,
    index: int = 0,
    transaction_id: str | None = None,
    status: str = "completed",
    title: str = "Mock durable consumer task",
) -> TransactionSnapshot:
    return TransactionSnapshot(
        transaction_id=transaction_id or f"session_corpus_mock_{index}",
        title=title,
        status=status,
        started_at=1000.0 + index,
        updated_at=1002.0 + index,
        completed_at=1002.0 + index if status in {"completed", "failed", "cancelled"} else None,
        recent_operations=(),
    )


def make_shadow_result(*, index: int = 0, final_text_sent: bool = True) -> dict[str, Any]:
    delivery_state: dict[str, Any] = {
        "final_text": {
            "sent": final_text_sent,
            "reason": "stream_final_response" if final_text_sent else None,
        },
        "rich_cards_sent": [],
    }
    agent_result: dict[str, Any] = {"delivery_state": delivery_state}
    attached = attach_flowweaver_shadow_snapshot(
        agent_result,
        make_snapshot(index=index),
        enabled=True,
        final_text="done" if final_text_sent else None,
    )
    assert attached is not None
    return agent_result


def shadow_result_from_fixture_case(case: dict[str, Any], *, index: int) -> dict[str, Any]:
    delivery_state: dict[str, Any] = {
        "final_text": {
            "sent": bool(case["final_text_sent"]),
            "reason": "stream_final_response" if case["final_text_sent"] else None,
        },
        "rich_cards_sent": [
            {"type": card_type, "message_id": f"om_corpus_{card_index}"}
            for card_index, card_type in enumerate(case["rich_card_types"], start=1)
        ],
    }
    agent_result: dict[str, Any] = {"delivery_state": delivery_state}
    attached = attach_flowweaver_shadow_snapshot(
        agent_result,
        make_snapshot(
            index=index,
            transaction_id=str(case["transaction_id"]),
            status=str(case["status"]),
            title=str(case["title"]),
        ),
        enabled=True,
        final_text="done" if case["final_text_sent"] else None,
    )
    assert attached is not None
    return agent_result


CORPUS_FIXTURE = Path(__file__).with_name("fixtures") / "flowweaver_shadow_replay_corpus.json"


def load_fixture_cases() -> list[dict[str, Any]]:
    loaded = json.loads(CORPUS_FIXTURE.read_text())
    assert isinstance(loaded, list)
    return loaded


class FlickeringMapping(Mapping[str, Any]):
    def __init__(self, base: dict[str, Any], unsafe_after_validation: dict[str, Any]) -> None:
        self._base = base
        self._unsafe_after_validation = unsafe_after_validation
        self._reads: dict[str, int] = {}

    def __iter__(self) -> Iterator[str]:
        return iter(self._base)

    def __len__(self) -> int:
        return len(self._base)

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        self._reads[key] = self._reads.get(key, 0) + 1
        if self._reads[key] > 1 and key in self._unsafe_after_validation:
            return self._unsafe_after_validation[key]
        return self._base.get(key, default)


def make_passed_corpus(*, count: int = 2) -> dict[str, Any]:
    agent_results = [make_shadow_result(index=index) for index in range(count)]
    corpus = replay_flowweaver_shadow_corpus(agent_results, attempts=2)
    assert corpus["verdict"] == FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED
    return corpus


def test_mock_durable_consumer_accepts_descriptor_and_passed_corpus() -> None:
    descriptor = describe_flowweaver_shadow_consumer_contract()
    corpus = make_passed_corpus(count=1)

    projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, corpus)

    assert projection["type"] == FLOWWEAVER_MOCK_DURABLE_CONSUMER_TYPE
    assert projection["verdict"] == FLOWWEAVER_MOCK_DURABLE_ACCEPTED
    assert projection["reason"] == "ok"
    assert projection["contract_type"] == descriptor["type"]
    assert projection["contract_version"] == "flowweaver.v0"
    assert projection["corpus_type"] == corpus["type"]
    assert projection["corpus_verdict"] == FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED
    assert projection["entry_count"] == 1
    assert projection["side_effects"] == []
    assert projection["checks"] == {
        "contract_descriptor_valid": True,
        "corpus_valid": True,
        "corpus_passed": True,
        "record_counts_match_entries": True,
        "payloads_absent": True,
        "side_effects_absent": True,
    }


def test_mock_durable_consumer_projects_synthetic_transaction_intent_artifact_delivery_records() -> None:
    descriptor = describe_flowweaver_shadow_consumer_contract()
    corpus = make_passed_corpus(count=3)

    projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, corpus)

    records = projection["records"]
    assert records["transaction"] == {
        "record_id": "mock_tx_replay_corpus",
        "status": "succeeded",
        "entry_count": 3,
    }
    assert len(records["intents"]) == 3
    assert len(records["artifacts"]) == 3
    assert len(records["deliveries"]) == 3
    for index, entry in enumerate(corpus["entries"]):
        intent = records["intents"][index]
        artifact = records["artifacts"][index]
        delivery = records["deliveries"][index]
        assert intent == {
            "intent_id": f"mock_intent_{index}",
            "source_entry_index": index,
            "status": "succeeded",
            "replay_verdict": entry["verdict"],
        }
        assert artifact == {
            "artifact_id": f"mock_artifact_{index}",
            "intent_id": f"mock_intent_{index}",
            "kind": "shadow_replay_verdict",
            "status": "available",
        }
        assert delivery == {
            "delivery_id": f"mock_delivery_{index}",
            "artifact_id": f"mock_artifact_{index}",
            "surface": "mock_consumer",
            "status": "observed",
        }


def test_mock_durable_consumer_rejects_flickering_descriptor_mapping_without_echo() -> None:
    descriptor = FlickeringMapping(
        describe_flowweaver_shadow_consumer_contract(),
        {
            "type": "oc_private_contract",
            "contract_version": "ou_private_version",
        },
    )
    corpus = make_passed_corpus(count=1)

    projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, corpus)

    rendered = repr(projection).lower()
    assert projection["verdict"] == FLOWWEAVER_MOCK_DURABLE_REJECTED
    assert projection["reason"] == "invalid_contract"
    assert "oc_private_contract" not in rendered
    assert "ou_private_version" not in rendered
    assert projection["side_effects"] == []


def test_mock_durable_consumer_rejects_flickering_corpus_mapping_without_echo() -> None:
    descriptor = describe_flowweaver_shadow_consumer_contract()
    safe_corpus = make_passed_corpus(count=1)
    unsafe_entries = copy.deepcopy(safe_corpus["entries"])
    unsafe_entries[0]["verdict"] = "om_private_message"
    corpus = FlickeringMapping(safe_corpus, {"entries": unsafe_entries})

    projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, corpus)

    rendered = repr(projection).lower()
    assert projection["verdict"] == FLOWWEAVER_MOCK_DURABLE_REJECTED
    assert projection["reason"] == "invalid_corpus"
    assert "om_private_message" not in rendered
    assert projection["side_effects"] == []


def test_mock_durable_consumer_rejects_mutating_entry_values_without_echo() -> None:
    descriptor = describe_flowweaver_shadow_consumer_contract()
    corpus = make_passed_corpus(count=1)

    class MutatingVerdict:
        def __eq__(self, other: object) -> bool:
            corpus["entries"][0]["verdict"] = "om_private_message"
            return other == "replayed"

        def __repr__(self) -> str:
            return "om_private_message"

    corpus["entries"][0]["verdict"] = MutatingVerdict()

    projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, corpus)

    rendered = repr(projection).lower()
    assert projection["verdict"] == FLOWWEAVER_MOCK_DURABLE_REJECTED
    assert projection["reason"] == "invalid_corpus"
    assert "om_private_message" not in rendered
    assert projection["side_effects"] == []


def test_mock_durable_consumer_rejects_mutating_envelope_values_without_input_mutation() -> None:
    descriptor = describe_flowweaver_shadow_consumer_contract()
    original_forbidden = copy.deepcopy(descriptor["forbidden_output_fields"])

    class MutatingDescriptorType:
        def __eq__(self, other: object) -> bool:
            descriptor["forbidden_output_fields"] = ["om_private_message"]
            return other == "flowweaver.gateway.shadow_consumer_contract.v0"

        def __repr__(self) -> str:
            return "om_private_message"

    descriptor["type"] = MutatingDescriptorType()
    corpus = make_passed_corpus(count=1)

    projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, corpus)

    rendered = repr(projection).lower()
    assert projection["verdict"] == FLOWWEAVER_MOCK_DURABLE_REJECTED
    assert projection["reason"] == "invalid_contract"
    assert descriptor["forbidden_output_fields"] == original_forbidden
    assert "om_private_message" not in rendered
    assert projection["side_effects"] == []


def test_mock_durable_consumer_rejects_mutating_corpus_envelope_without_reread() -> None:
    descriptor = describe_flowweaver_shadow_consumer_contract()
    corpus = make_passed_corpus(count=1)

    class MutatingCorpusReason:
        def __eq__(self, other: object) -> bool:
            corpus["entries"] = [
                {
                    "index": index,
                    "verdict": "replayed",
                    "reason": "ok",
                    "checks": corpus["entries"][0]["checks"],
                    "side_effects": [],
                    "capture": {"message_id": "om_private_message"},
                }
                for index in range(25)
            ]
            return other == "ok"

        def __repr__(self) -> str:
            return "om_private_message"

    corpus["reason"] = MutatingCorpusReason()

    projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, corpus)

    rendered = repr(projection).lower()
    assert projection["verdict"] == FLOWWEAVER_MOCK_DURABLE_REJECTED
    assert projection["reason"] == "invalid_corpus"
    assert projection["entry_count"] == 0
    assert "om_private_message" not in rendered
    assert projection["side_effects"] == []


def test_mock_durable_consumer_rejects_mutating_entry_key_objects_without_reread() -> None:
    descriptor = describe_flowweaver_shadow_consumer_contract()
    corpus = make_passed_corpus(count=1)
    safe_entry = copy.deepcopy(corpus["entries"][0])
    mutations: list[str] = []

    class MutatingEntryKey(str):
        def __eq__(self, other: object) -> bool:
            mutations.append("called")
            corpus["entries"] = [
                {
                    "index": index,
                    "verdict": "replayed",
                    "reason": "ok",
                    "checks": safe_entry["checks"],
                    "side_effects": [],
                    "capture": {"message_id": "om_private_message"},
                }
                for index in range(25)
            ]
            return super().__eq__(other)

        def __hash__(self) -> int:
            return super().__hash__()

        def __repr__(self) -> str:
            return "om_private_message"

    corpus["entries"] = [
        {MutatingEntryKey(key): value for key, value in safe_entry.items()}
    ]

    projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, corpus)

    rendered = repr(projection).lower()
    assert projection["verdict"] == FLOWWEAVER_MOCK_DURABLE_REJECTED
    assert projection["reason"] == "invalid_corpus"
    assert projection["entry_count"] == 0
    assert len(corpus["entries"]) == 1
    assert mutations == []
    assert "om_private_message" not in rendered
    assert projection["side_effects"] == []


def test_mock_durable_consumer_rejects_mutated_descriptor_contract_surface() -> None:
    descriptor = describe_flowweaver_shadow_consumer_contract()
    descriptor["allowed_consumer_inputs"] = ["raw_snapshot"]
    descriptor["forbidden_side_effects"] = []
    descriptor["bounds"] = {"max_corpus_entries": 999}
    corpus = make_passed_corpus(count=1)

    projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, corpus)

    rendered = repr(projection).lower()
    assert projection["verdict"] == FLOWWEAVER_MOCK_DURABLE_REJECTED
    assert projection["reason"] == "invalid_contract"
    assert "raw_snapshot" not in rendered
    assert projection["side_effects"] == []


def test_mock_durable_consumer_rejects_invalid_descriptor_without_echoing_values() -> None:
    descriptor = describe_flowweaver_shadow_consumer_contract()
    descriptor["type"] = "oc_private_descriptor"
    descriptor["raw_command"] = "run unsafe thing"
    corpus = make_passed_corpus(count=1)

    projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, corpus)

    rendered = repr(projection).lower()
    assert projection["verdict"] == FLOWWEAVER_MOCK_DURABLE_REJECTED
    assert projection["reason"] == "invalid_contract"
    assert "oc_private_descriptor" not in rendered
    assert "run unsafe thing" not in rendered
    assert projection["records"] == {
        "transaction": None,
        "intents": [],
        "artifacts": [],
        "deliveries": [],
    }
    assert projection["side_effects"] == []


def test_mock_durable_consumer_rejects_failed_or_rejected_corpus() -> None:
    descriptor = describe_flowweaver_shadow_consumer_contract()
    for verdict in (FLOWWEAVER_SHADOW_REPLAY_CORPUS_FAILED, FLOWWEAVER_SHADOW_REPLAY_CORPUS_REJECTED):
        corpus = make_passed_corpus(count=1)
        corpus["verdict"] = verdict
        corpus["reason"] = "entry_failed" if verdict == FLOWWEAVER_SHADOW_REPLAY_CORPUS_FAILED else "invalid_corpus"

        projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, corpus)

        assert projection["verdict"] == FLOWWEAVER_MOCK_DURABLE_REJECTED
        assert projection["reason"] == "corpus_not_passed"
        assert projection["corpus_verdict"] is None
        assert projection["entry_count"] == 0
        assert projection["side_effects"] == []


def test_mock_durable_consumer_rejects_raw_snapshot_or_capture_inputs() -> None:
    descriptor = describe_flowweaver_shadow_consumer_contract()
    raw_agent_result = make_shadow_result(index=0)

    for raw_input in (
        raw_agent_result,
        raw_agent_result[FLOWWEAVER_SHADOW_SNAPSHOT_KEY],
        raw_agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY],
    ):
        projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, raw_input)  # type: ignore[arg-type]
        rendered = repr(projection).lower()

        assert projection["verdict"] == FLOWWEAVER_MOCK_DURABLE_REJECTED
        assert projection["reason"] == "invalid_corpus"
        assert "session_corpus_mock" not in rendered
        assert "flowweaver_shadow_snapshot" not in rendered
        assert "flowweaver_shadow_capture" not in rendered
        assert projection["side_effects"] == []


def test_mock_durable_consumer_does_not_mutate_inputs() -> None:
    descriptor = describe_flowweaver_shadow_consumer_contract()
    corpus = make_passed_corpus(count=2)
    original_descriptor = copy.deepcopy(descriptor)
    original_corpus = copy.deepcopy(corpus)

    projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, corpus)

    assert projection["verdict"] == FLOWWEAVER_MOCK_DURABLE_ACCEPTED
    assert descriptor == original_descriptor
    assert corpus == original_corpus


def test_mock_durable_consumer_output_omits_payload_ids_and_sensitive_shapes() -> None:
    descriptor = describe_flowweaver_shadow_consumer_contract()
    corpus = make_passed_corpus(count=1)
    descriptor["stdout"] = "raw output"
    corpus["entries"][0]["snapshot_ref"] = {"transaction_id": "tx_private_123456789012"}
    corpus["entries"][0]["capture"] = {"message_id": "om_private_message"}
    corpus["entries"][0]["authorization"] = "Bearer " + "fake"

    projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, corpus)

    rendered = repr(projection).lower()
    assert projection["verdict"] == FLOWWEAVER_MOCK_DURABLE_REJECTED
    assert "raw output" not in rendered
    assert "tx_private_123456789012" not in rendered
    assert "om_private_message" not in rendered
    assert "bearer " + "fake" not in rendered
    assert "snapshot_ref" not in rendered
    assert "capture" not in rendered
    assert "authorization" not in rendered


def test_mock_durable_consumer_rejects_entries_with_failed_safety_checks() -> None:
    descriptor = describe_flowweaver_shadow_consumer_contract()
    corpus = make_passed_corpus(count=1)
    corpus["entries"][0]["checks"] = {
        **corpus["entries"][0]["checks"],
        "side_effects_absent": False,
    }

    projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, corpus)

    assert projection["verdict"] == FLOWWEAVER_MOCK_DURABLE_REJECTED
    assert projection["reason"] == "invalid_corpus"
    assert projection["checks"]["side_effects_absent"] is True


def test_mock_durable_consumer_consumes_phase4f_fixture_through_safe_corpus_only() -> None:
    cases = load_fixture_cases()
    agent_results = [
        shadow_result_from_fixture_case(case, index=index)
        for index, case in enumerate(cases)
    ]
    corpus = replay_flowweaver_shadow_corpus(agent_results, attempts=2)

    projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(
        describe_flowweaver_shadow_consumer_contract(),
        corpus,
    )

    rendered = repr(projection).lower()
    assert projection["verdict"] == FLOWWEAVER_MOCK_DURABLE_ACCEPTED
    assert projection["entry_count"] == len(cases)
    assert projection["records"]["transaction"]["entry_count"] == len(cases)
    assert [intent["source_entry_index"] for intent in projection["records"]["intents"]] == [0, 1, 2]
    assert "session_corpus" not in rendered
    assert "corpus final text task" not in rendered
    assert "weather.v1" not in rendered
    assert "om_corpus" not in rendered
    assert "snapshot" not in rendered
    assert "capture" not in rendered
    assert projection["side_effects"] == []
