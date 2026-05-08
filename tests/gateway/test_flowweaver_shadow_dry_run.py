"""Tests for the FlowWeaver Phase 4H Gateway shadow dry-run helper."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

import gateway.flowweaver_shadow_dry_run as dry_run_module
from gateway.flowweaver_shadow import attach_flowweaver_shadow_snapshot
from gateway.flowweaver_shadow_dry_run import (
    FLOWWEAVER_SHADOW_DRY_RUN_PASSED,
    FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY,
    FLOWWEAVER_SHADOW_DRY_RUN_TYPE,
    is_flowweaver_shadow_dry_run_enabled,
    run_flowweaver_gateway_shadow_dry_run,
)
from gateway.progress.events import TransactionSnapshot


def make_snapshot(*, index: int = 0) -> TransactionSnapshot:
    return TransactionSnapshot(
        transaction_id=f"session_shadow_dry_run_{index}",
        title="Gateway shadow dry-run task",
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


def test_flowweaver_shadow_dry_run_is_disabled_by_default() -> None:
    assert is_flowweaver_shadow_dry_run_enabled({}) is False
    assert is_flowweaver_shadow_dry_run_enabled({"flowweaver_shadow": True}) is False
    assert is_flowweaver_shadow_dry_run_enabled({"flowweaver_shadow_dry_run": True}) is False


def test_flowweaver_shadow_dry_run_requires_existing_shadow_gate() -> None:
    assert (
        is_flowweaver_shadow_dry_run_enabled(
            {"flowweaver_shadow": True, "flowweaver_shadow_dry_run": True}
        )
        is True
    )
    assert (
        is_flowweaver_shadow_dry_run_enabled(
            {"flowweaver_shadow": False, "flowweaver_shadow_dry_run": True}
        )
        is False
    )


def test_flowweaver_shadow_dry_run_accepts_shadow_agent_result_summary() -> None:
    summary = run_flowweaver_gateway_shadow_dry_run(make_shadow_agent_result())

    assert summary["type"] == FLOWWEAVER_SHADOW_DRY_RUN_TYPE
    assert summary["verdict"] == FLOWWEAVER_SHADOW_DRY_RUN_PASSED
    assert summary["reason"] == "ok"
    assert summary["entry_count"] == 1
    assert summary["replay_corpus_verdict"] == "passed"
    assert summary["mock_durable_verdict"] == "accepted"
    assert summary["record_counts"] == {"intents": 1, "artifacts": 1, "deliveries": 1}
    assert summary["checks"] == {
        "shadow_capture_present": True,
        "consumer_contract_valid": True,
        "replay_corpus_passed": True,
        "mock_durable_accepted": True,
        "record_counts_match_entries": True,
        "payloads_absent": True,
        "visible_side_effects_absent": True,
    }
    assert summary["side_effects"] == []
    assert FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY not in make_shadow_agent_result(index=1)


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


def test_shadow_dry_run_rejects_missing_shadow_capture_without_echoing_values() -> None:
    agent_result = {
        "final_response": "done",
        "raw_command": "curl https://example.invalid/?" + "access_" + "token=abc123",
        "authorization": "Bearer " + "abc123",
        "message_id": "om_private_message",
    }

    summary = run_flowweaver_gateway_shadow_dry_run(agent_result)
    rendered = repr(summary).lower()

    assert summary["verdict"] == "rejected"
    assert summary["reason"] == "invalid_shadow"
    assert summary["side_effects"] == []
    assert "abc123" not in rendered
    assert "om_private_message" not in rendered
    assert "access_token" not in rendered


def test_shadow_dry_run_rejects_raw_snapshot_or_capture_inputs() -> None:
    agent_result = make_shadow_agent_result()

    for raw_value in (
        agent_result["flowweaver_shadow_snapshot"],
        agent_result["flowweaver_shadow_capture"],
    ):
        summary = run_flowweaver_gateway_shadow_dry_run(raw_value)
        assert summary["verdict"] == "rejected"
        assert summary["reason"] == "invalid_shadow"
        assert summary["entry_count"] == 0
        assert summary["side_effects"] == []


def test_shadow_dry_run_output_omits_payload_ids_and_sensitive_shapes() -> None:
    agent_result = make_shadow_agent_result()
    agent_result["raw_output"] = "stdout with " + "sk-" + "123456789012"
    agent_result["card_json"] = {"message_id": "om_private_message"}
    agent_result["delivery_ack"] = {"chat_id": "oc_private_chat", "user_id": "ou_private_user"}

    summary = run_flowweaver_gateway_shadow_dry_run(agent_result)
    rendered = repr(summary).lower()

    assert summary["verdict"] == FLOWWEAVER_SHADOW_DRY_RUN_PASSED
    assert "sk-123456789012" not in rendered
    assert "om_private_message" not in rendered
    assert "oc_private_chat" not in rendered
    assert "ou_private_user" not in rendered
    assert "raw_output" not in rendered
    assert "card_json" not in rendered
    assert "delivery_ack" not in rendered


def test_shadow_dry_run_does_not_mutate_inputs_on_summary_rejection() -> None:
    agent_result = {"final_response": "done", "unexpected": {"message_id": "om_private_message"}}
    before = repr(agent_result)

    summary = run_flowweaver_gateway_shadow_dry_run(agent_result)

    assert summary["verdict"] == "rejected"
    assert repr(agent_result) == before
    assert FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY not in agent_result


def test_shadow_dry_run_rejects_hostile_mapping_and_mutating_keys() -> None:
    safe = make_shadow_agent_result()
    hostile = FlickeringMapping(safe, {"final_response": "om_private_message"})

    summary = run_flowweaver_gateway_shadow_dry_run(hostile)

    assert summary["verdict"] == "rejected"
    assert summary["reason"] == "invalid_shadow"
    assert "om_private_message" not in repr(summary).lower()

    mutations: list[str] = []

    class MutatingKey(str):
        def __eq__(self, other: object) -> bool:
            mutations.append("eq")
            return super().__eq__(other)

        def __hash__(self) -> int:
            return str.__hash__(self)

    keyed = dict(safe)
    keyed[MutatingKey("flowweaver_shadow_snapshot")] = keyed.pop("flowweaver_shadow_snapshot")

    summary = run_flowweaver_gateway_shadow_dry_run(keyed)

    assert summary["verdict"] == "rejected"
    assert summary["reason"] == "invalid_shadow"
    assert mutations == []


def test_shadow_dry_run_rejects_flickering_inputs_without_post_validation_reread() -> None:
    safe = make_shadow_agent_result()
    unsafe = dict(safe)
    unsafe["flowweaver_shadow_capture"] = {"message_id": "om_private_message"}
    hostile = FlickeringMapping(safe, unsafe)

    summary = run_flowweaver_gateway_shadow_dry_run(hostile)

    rendered = repr(summary).lower()
    assert summary["verdict"] == "rejected"
    assert summary["reason"] == "invalid_shadow"
    assert "om_private_message" not in rendered


def test_shadow_dry_run_builds_summary_from_sanitized_counts_only(monkeypatch) -> None:
    def unsafe_projection(_descriptor: object, _corpus: object) -> dict[str, Any]:
        return {
            "verdict": "accepted",
            "entry_count": 1,
            "records": {
                "transaction": {"record_id": "om_private_message"},
                "intents": [{"intent_id": "oc_private_chat"}],
                "artifacts": [{"artifact_id": "ou_private_user"}],
                "deliveries": [{"delivery_id": "sk-" + "123456789012"}],
            },
        }

    monkeypatch.setattr(
        dry_run_module,
        "consume_flowweaver_shadow_corpus_as_mock_durable_state",
        unsafe_projection,
    )

    summary = run_flowweaver_gateway_shadow_dry_run(make_shadow_agent_result())
    rendered = repr(summary).lower()

    assert summary["verdict"] == FLOWWEAVER_SHADOW_DRY_RUN_PASSED
    assert summary["record_counts"] == {"intents": 1, "artifacts": 1, "deliveries": 1}
    assert "om_private_message" not in rendered
    assert "oc_private_chat" not in rendered
    assert "ou_private_user" not in rendered
    assert "sk-123456789012" not in rendered


def test_shadow_dry_run_rejects_mock_durable_count_mismatch_without_records(monkeypatch) -> None:
    def mismatched_projection(_descriptor: object, _corpus: object) -> dict[str, Any]:
        return {
            "verdict": "accepted",
            "entry_count": 2,
            "records": {
                "transaction": {"record_id": "om_private_message"},
                "intents": [{"intent_id": "oc_private_chat"}],
                "artifacts": [{"artifact_id": "ou_private_user"}],
                "deliveries": [{"delivery_id": "om_private_delivery"}],
            },
        }

    monkeypatch.setattr(
        dry_run_module,
        "consume_flowweaver_shadow_corpus_as_mock_durable_state",
        mismatched_projection,
    )

    summary = run_flowweaver_gateway_shadow_dry_run(make_shadow_agent_result())
    rendered = repr(summary).lower()

    assert summary["verdict"] == "rejected"
    assert summary["reason"] == "mock_durable_rejected"
    assert "om_private_message" not in rendered
    assert "oc_private_chat" not in rendered
    assert "ou_private_user" not in rendered
