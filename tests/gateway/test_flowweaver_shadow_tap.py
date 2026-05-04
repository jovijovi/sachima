"""Tests for the default-off FlowWeaver Gateway shadow tap."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
import copy
import json
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any

from gateway.flowweaver_shadow import (
    FLOWWEAVER_SHADOW_AUDIT_READY,
    FLOWWEAVER_SHADOW_AUDIT_REJECTED,
    FLOWWEAVER_SHADOW_AUDIT_SCHEMA_MISMATCH,
    FLOWWEAVER_SHADOW_AUDIT_TYPE,
    FLOWWEAVER_SHADOW_AUDIT_UNSAFE,
    FLOWWEAVER_SHADOW_CAPTURE_KEY,
    FLOWWEAVER_SHADOW_CAPTURE_TYPE,
    FLOWWEAVER_SHADOW_CONSUMER_CONTRACT_TYPE,
    FLOWWEAVER_SHADOW_REPLAY_CORPUS_FAILED,
    FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED,
    FLOWWEAVER_SHADOW_REPLAY_CORPUS_REJECTED,
    FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE,
    FLOWWEAVER_SHADOW_REPLAY_DRIFT_DETECTED,
    FLOWWEAVER_SHADOW_REPLAY_REJECTED,
    FLOWWEAVER_SHADOW_REPLAY_REPLAYED,
    FLOWWEAVER_SHADOW_REPLAY_SCHEMA_MISMATCH,
    FLOWWEAVER_SHADOW_REPLAY_TYPE,
    FLOWWEAVER_SHADOW_REPLAY_UNSAFE,
    FLOWWEAVER_SHADOW_SNAPSHOT_KEY,
    attach_flowweaver_shadow_snapshot,
    audit_flowweaver_shadow_capture,
    describe_flowweaver_shadow_consumer_contract,
    get_flowweaver_shadow_capture,
    is_flowweaver_shadow_enabled,
    replay_flowweaver_shadow_capture,
    replay_flowweaver_shadow_corpus,
)
from gateway.progress.events import ProgressOperation, TransactionSnapshot


FORBIDDEN_VALUE_PATTERNS = (
    re.compile("Bearer" + r"\s+[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile("sk-" + r"[A-Za-z0-9]{12,}"),
    re.compile(r"fake-[A-Za-z0-9_-]*(?:token|secret|password)", re.IGNORECASE),
)


def make_snapshot(
    *,
    transaction_id: str = "session-123",
    status: str = "completed",
    title: str = "验证 FlowWeaver 影子快照",
    operations: tuple[ProgressOperation, ...] = (),
) -> TransactionSnapshot:
    return TransactionSnapshot(
        transaction_id=transaction_id,
        title=title,
        status=status,
        started_at=1000.0,
        updated_at=1002.0,
        completed_at=1002.0 if status in {"completed", "failed", "cancelled"} else None,
        recent_operations=operations,
    )


def make_operation(
    *,
    operation_id: str = "op-1",
    tool_name: str | None = "terminal",
    event_type: str = "tool.completed",
    status: str = "completed",
    preview: str | None = None,
    args_preview: str | None = None,
) -> ProgressOperation:
    return ProgressOperation(
        id=operation_id,
        event_type=event_type,
        tool_name=tool_name,
        status=status,
        preview=preview,
        args_preview=args_preview,
        started_at=1000.0,
        updated_at=1001.0,
        completed_at=1001.0,
        duration=0.1,
        is_error=status == "failed",
        metadata={},
    )


def assert_no_sensitive_material(obj: Any) -> None:
    rendered = repr(obj)
    for pattern in FORBIDDEN_VALUE_PATTERNS:
        assert pattern.search(rendered) is None
    for forbidden in (
        "raw_command",
        "raw_output",
        "stdout",
        "stderr",
        "feishu_card_json",
        "oc_private",
        "ou_private",
    ):
        assert forbidden not in rendered


def test_shadow_tap_is_disabled_by_default() -> None:
    assert is_flowweaver_shadow_enabled({}) is False
    assert is_flowweaver_shadow_enabled({"enabled": True}) is False
    assert is_flowweaver_shadow_enabled({"flowweaver_shadow": False}) is False
    assert is_flowweaver_shadow_enabled({"flowweaver_shadow": "true"}) is True

    agent_result: dict[str, Any] = {}
    attached = attach_flowweaver_shadow_snapshot(
        agent_result,
        make_snapshot(),
        enabled=False,
        final_text="done",
    )

    assert attached is None
    assert FLOWWEAVER_SHADOW_SNAPSHOT_KEY not in agent_result


def test_shadow_tap_attaches_sanitized_v0_snapshot_when_enabled() -> None:
    agent_result: dict[str, Any] = {
        "delivery_state": {
            "final_text": {"sent": True, "reason": "stream_final_response"},
            "rich_cards_sent": [{"type": "weather.v1", "message_id": "om_weather"}],
        }
    }

    attached = attach_flowweaver_shadow_snapshot(
        agent_result,
        make_snapshot(),
        enabled=True,
        final_text="最终回答 token=" + "fake-" + "final-token",
    )

    assert attached is agent_result[FLOWWEAVER_SHADOW_SNAPSHOT_KEY]
    assert attached["type"] == "flowweaver.handle.v0"
    assert attached["contract_version"] == "flowweaver.v0"
    assert attached["transaction"]["status"] == "succeeded"
    assert attached["transaction"]["final_text"]["status"] == "succeeded"
    assert attached["transaction"]["intent_coverage"][0]["mode"] == "answered"
    assert attached["transaction"]["artifacts"][0]["kind"] == "rich_card"
    assert_no_sensitive_material(attached)


def test_shadow_tap_does_not_claim_unsent_normal_final_text() -> None:
    agent_result: dict[str, Any] = {
        "delivery_state": {
            "final_text": {"sent": False, "reason": None},
            "rich_cards_sent": [],
        }
    }

    attached = attach_flowweaver_shadow_snapshot(
        agent_result,
        make_snapshot(),
        enabled=True,
        final_text="This normal final text has not been delivered yet.",
    )

    assert attached is not None
    assert attached["transaction"]["final_text"]["status"] == "pending"
    assert attached["transaction"]["final_text"]["covers_intent_ids"] == []
    assert attached["transaction"]["deliveries"] == []
    assert attached["transaction"]["intent_coverage"][0]["mode"] == "blocked_waiting_for_user"
    assert_no_sensitive_material(attached)


def test_shadow_tap_never_raises_or_leaks_sensitive_source_fields() -> None:
    bearer = "Bearer " + "fake-" + "source-token"
    openai_like = "sk-" + "12345678901234567890"
    agent_result: dict[str, Any] = {
        "delivery_state": {"final_text": {"sent": True, "reason": "authorization=" + bearer}},
    }
    source = SimpleNamespace(
        platform="feishu",
        chat_id="oc_private_chat",
        user_id="ou_private_user",
        authorization=bearer,
    )

    attached = attach_flowweaver_shadow_snapshot(
        agent_result,
        make_snapshot(
            transaction_id="feishu:oc_private_chat:ou_private_user",
            title="Debug " + bearer,
            operations=(
                make_operation(
                    preview="python script.py --api-key " + openai_like,
                    args_preview="raw_command=export TOKEN=" + "fake-" + "args-token",
                ),
            ),
        ),
        enabled=True,
        source=source,
        final_text="done password=" + "fake-" + "password",
    )

    assert attached is not None
    assert attached["transaction_id"].startswith("tx_transaction_")
    assert_no_sensitive_material(attached)


def test_shadow_tap_attaches_lifecycle_capture_for_consumers() -> None:
    agent_result: dict[str, Any] = {
        "delivery_state": {
            "final_text": {"sent": True, "reason": "stream_final_response"},
            "rich_cards_sent": [{"type": "weather.v1", "message_id": "om_weather"}],
        }
    }

    attached = attach_flowweaver_shadow_snapshot(
        agent_result,
        make_snapshot(transaction_id="session-4c", title="审计 FlowWeaver 影子快照"),
        enabled=True,
        final_text="done",
    )

    assert attached is not None
    capture = agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY]
    assert capture["type"] == FLOWWEAVER_SHADOW_CAPTURE_TYPE
    assert capture["contract_version"] == "flowweaver.v0"
    assert capture["snapshot_key"] == FLOWWEAVER_SHADOW_SNAPSHOT_KEY
    assert capture["transaction_id"] == attached["transaction_id"]
    assert capture["correlation_id"] == attached["correlation_id"]
    assert capture["snapshot_id"] == attached["snapshot_id"]
    assert capture["lifecycle"] == {
        "stage": "gateway_shadow_capture",
        "state": "captured",
        "default_enabled": False,
        "visible_side_effects": [],
    }
    assert capture["consumer"]["status"] == "ready"
    assert "future_flowweaver_runtime" in capture["consumer"]["allowed"]
    assert capture["consumer"]["forbidden_side_effects"] == [
        "send",
        "edit",
        "render",
        "persist",
        "temporal",
    ]
    assert capture["audit"] == {
        "snapshot_safe_to_render": True,
        "public_schema_unchanged": True,
        "source_exported": False,
    }
    view = get_flowweaver_shadow_capture(agent_result)
    assert view is not None
    assert view["snapshot_ref"] == {
        "snapshot_key": FLOWWEAVER_SHADOW_SNAPSHOT_KEY,
        "transaction_id": attached["transaction_id"],
        "correlation_id": attached["correlation_id"],
        "snapshot_id": attached["snapshot_id"],
    }
    assert view["capture"] is capture
    assert "feishu" not in repr(view)
    assert "om_weather" not in repr(view)
    assert_no_sensitive_material(capture)


def test_shadow_consumer_view_requires_matching_snapshot_and_capture_ids() -> None:
    agent_result: dict[str, Any] = {}
    attached = attach_flowweaver_shadow_snapshot(
        agent_result,
        make_snapshot(transaction_id="session-consumer-view"),
        enabled=True,
        final_text="done",
    )

    assert attached is not None
    assert get_flowweaver_shadow_capture(agent_result) is not None

    original_capture = dict(agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY])
    agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY] = {
        **original_capture,
        "snapshot_id": "snap_other_transaction",
    }
    assert get_flowweaver_shadow_capture(agent_result) is None

    agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY] = original_capture
    original_snapshot = dict(agent_result[FLOWWEAVER_SHADOW_SNAPSHOT_KEY])
    agent_result[FLOWWEAVER_SHADOW_SNAPSHOT_KEY] = {
        **original_snapshot,
        "transaction_id": "tx_other_transaction",
    }
    assert get_flowweaver_shadow_capture(agent_result) is None

    assert get_flowweaver_shadow_capture({}) is None
    assert get_flowweaver_shadow_capture({FLOWWEAVER_SHADOW_CAPTURE_KEY: original_capture}) is None
    assert get_flowweaver_shadow_capture({FLOWWEAVER_SHADOW_SNAPSHOT_KEY: original_snapshot}) is None


class ExplodingMapping(Mapping[str, Any]):
    def __getitem__(self, key: str) -> Any:
        raise RuntimeError("hostile mapping access")

    def __iter__(self) -> Iterator[str]:
        raise RuntimeError("hostile mapping iter")

    def __len__(self) -> int:
        return 1

    def get(self, key: str, default: Any = None) -> Any:
        raise RuntimeError("hostile mapping get")


def test_shadow_consumer_view_fails_closed_for_hostile_mapping() -> None:
    assert get_flowweaver_shadow_capture(ExplodingMapping()) is None


def test_shadow_capture_omits_source_delivery_payloads_and_secret_shapes() -> None:
    bearer = "Bearer " + "fake-" + "capture-token"
    agent_result: dict[str, Any] = {
        "delivery_state": {
            "final_text": {"sent": True, "reason": "authorization=" + bearer},
            "rich_cards_sent": [
                {
                    "type": "weather.v1",
                    "message_id": "om_private_weather",
                    "raw_card_json": {"token": "***" + "card-token"},
                }
            ],
        }
    }
    source = SimpleNamespace(
        platform="feishu",
        chat_id="oc_private_chat",
        user_id="ou_private_user",
        message_id="om_private_message",
        feishu_card_json={"authorization": bearer},
    )

    attached = attach_flowweaver_shadow_snapshot(
        agent_result,
        make_snapshot(
            transaction_id="feishu:oc_private_chat:ou_private_user",
            title="Lifecycle " + bearer,
        ),
        enabled=True,
        source=source,
        final_text="done secret=" + "fake-" + "final-secret",
    )

    assert attached is not None
    capture = agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY]
    rendered = repr(capture)
    assert "feishu" not in rendered
    assert "oc_private" not in rendered
    assert "ou_private" not in rendered
    assert "om_private" not in rendered
    assert "raw_card_json" not in rendered
    assert "feishu_card_json" not in rendered
    assert "authorization" not in rendered.lower()
    assert_no_sensitive_material(capture)


def attach_shadow_result(
    *,
    status: str = "completed",
    delivery_state: dict[str, Any] | None = None,
    final_text: str | None = "done",
    transaction_id: str = "session-audit",
) -> dict[str, Any]:
    agent_result: dict[str, Any] = {"delivery_state": delivery_state or {}}
    attached = attach_flowweaver_shadow_snapshot(
        agent_result,
        make_snapshot(transaction_id=transaction_id, status=status),
        enabled=True,
        final_text=final_text,
    )
    assert attached is not None
    return agent_result


def test_shadow_audit_ready_for_safe_consumer_view() -> None:
    agent_result = attach_shadow_result(
        delivery_state={
            "final_text": {"sent": True, "reason": "stream_final_response"},
            "rich_cards_sent": [{"type": "weather.v1", "message_id": "om_weather"}],
        }
    )

    audit = audit_flowweaver_shadow_capture(agent_result)

    snapshot = agent_result[FLOWWEAVER_SHADOW_SNAPSHOT_KEY]
    capture = agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY]
    assert audit["type"] == FLOWWEAVER_SHADOW_AUDIT_TYPE
    assert audit["verdict"] == FLOWWEAVER_SHADOW_AUDIT_READY
    assert audit["reason"] == "ok"
    assert audit["snapshot_ref"] == {
        "snapshot_key": FLOWWEAVER_SHADOW_SNAPSHOT_KEY,
        "transaction_id": snapshot["transaction_id"],
        "correlation_id": snapshot["correlation_id"],
        "snapshot_id": snapshot["snapshot_id"],
    }
    assert audit["checks"] == {
        "consumer_view_valid": True,
        "ids_match": True,
        "contract_version_valid": True,
        "snapshot_safe_to_render": True,
        "public_schema_unchanged": True,
        "source_not_exported": True,
        "side_effects_absent": True,
    }
    assert audit["side_effects"] == []
    assert "capture" not in audit


def test_shadow_audit_rejects_missing_or_mismatched_pair() -> None:
    assert audit_flowweaver_shadow_capture({})["verdict"] == FLOWWEAVER_SHADOW_AUDIT_REJECTED

    agent_result = attach_shadow_result()
    original_capture = dict(agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY])
    agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY] = {
        **original_capture,
        "snapshot_id": "snap_wrong",
    }

    audit = audit_flowweaver_shadow_capture(agent_result)

    assert audit["verdict"] == FLOWWEAVER_SHADOW_AUDIT_REJECTED
    assert audit["reason"] == "missing_or_invalid_consumer_view"
    assert audit["snapshot_ref"] is None
    assert audit["side_effects"] == []


def test_shadow_audit_marks_unsafe_snapshot_as_unsafe() -> None:
    agent_result = attach_shadow_result()
    agent_result[FLOWWEAVER_SHADOW_SNAPSHOT_KEY]["snapshot"] = {
        **agent_result[FLOWWEAVER_SHADOW_SNAPSHOT_KEY]["snapshot"],
        "safe_to_render": False,
    }
    agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY] = {
        **agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY],
        "audit": {
            **agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY]["audit"],
            "snapshot_safe_to_render": False,
        },
    }

    audit = audit_flowweaver_shadow_capture(agent_result)

    assert audit["verdict"] == FLOWWEAVER_SHADOW_AUDIT_UNSAFE
    assert audit["reason"] == "unsafe_snapshot"
    assert audit["checks"]["snapshot_safe_to_render"] is False


def test_shadow_audit_marks_source_export_or_side_effects_as_unsafe() -> None:
    agent_result = attach_shadow_result()
    agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY] = {
        **agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY],
        "audit": {
            **agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY]["audit"],
            "source_exported": True,
        },
    }

    source_audit = audit_flowweaver_shadow_capture(agent_result)

    assert source_audit["verdict"] == FLOWWEAVER_SHADOW_AUDIT_UNSAFE
    assert source_audit["reason"] == "unsafe_snapshot"
    assert source_audit["checks"]["source_not_exported"] is False

    agent_result = attach_shadow_result()
    agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY] = {
        **agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY],
        "lifecycle": {
            **agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY]["lifecycle"],
            "visible_side_effects": ["send"],
        },
    }

    side_effect_audit = audit_flowweaver_shadow_capture(agent_result)

    assert side_effect_audit["verdict"] == FLOWWEAVER_SHADOW_AUDIT_UNSAFE
    assert side_effect_audit["reason"] == "unsafe_snapshot"
    assert side_effect_audit["checks"]["side_effects_absent"] is False


def test_shadow_audit_marks_contract_or_capture_type_mismatch_as_schema_mismatch() -> None:
    agent_result = attach_shadow_result()
    agent_result[FLOWWEAVER_SHADOW_SNAPSHOT_KEY] = {
        **agent_result[FLOWWEAVER_SHADOW_SNAPSHOT_KEY],
        "contract_version": "flowweaver.v9",
    }

    audit = audit_flowweaver_shadow_capture(agent_result)

    assert audit["verdict"] == FLOWWEAVER_SHADOW_AUDIT_SCHEMA_MISMATCH
    assert audit["reason"] == "schema_mismatch"

    agent_result = attach_shadow_result()
    agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY] = {
        **agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY],
        "type": "flowweaver.gateway.shadow_capture.v9",
    }

    audit = audit_flowweaver_shadow_capture(agent_result)

    assert audit["verdict"] == FLOWWEAVER_SHADOW_AUDIT_SCHEMA_MISMATCH
    assert audit["reason"] == "schema_mismatch"


def test_shadow_audit_fails_closed_for_hostile_mapping() -> None:
    audit = audit_flowweaver_shadow_capture(ExplodingMapping())

    assert audit["verdict"] == FLOWWEAVER_SHADOW_AUDIT_REJECTED
    assert audit["reason"] == "missing_or_invalid_consumer_view"
    assert audit["snapshot_ref"] is None
    assert audit["side_effects"] == []


def test_shadow_audit_output_omits_full_snapshot_delivery_payloads_and_secret_shapes() -> None:
    bearer = "Bearer " + "fake-" + "audit-token"
    agent_result = attach_shadow_result(
        transaction_id="feishu:oc_private_chat:ou_private_user",
        delivery_state={
            "final_text": {"sent": True, "reason": "authorization=" + bearer},
            "rich_cards_sent": [
                {
                    "type": "weather.v1",
                    "message_id": "om_private_weather",
                    "raw_card_json": {"authorization": bearer},
                }
            ],
        },
        final_text="done token=" + "fake-" + "audit-secret",
    )

    audit = audit_flowweaver_shadow_capture(agent_result)

    rendered = repr(audit)
    assert audit["verdict"] == FLOWWEAVER_SHADOW_AUDIT_READY
    assert "transaction" not in audit
    assert "snapshot" not in audit
    assert "capture" not in audit
    assert "deliveries" not in rendered
    assert "artifacts" not in rendered
    assert "feishu" not in rendered
    assert "om_private" not in rendered
    assert "oc_private" not in rendered
    assert "ou_private" not in rendered
    assert "raw_card_json" not in rendered
    assert "authorization" not in rendered.lower()
    assert_no_sensitive_material(audit)


def test_shadow_audit_rejects_platform_like_snapshot_ref_ids_without_leaking_them() -> None:
    agent_result = attach_shadow_result()
    snapshot = {
        **agent_result[FLOWWEAVER_SHADOW_SNAPSHOT_KEY],
        "transaction_id": "feishu:oc_private_chat:ou_private_user",
        "correlation_id": "turn_oc_private_chat",
        "snapshot_id": "snap_om_private_message",
    }
    agent_result[FLOWWEAVER_SHADOW_SNAPSHOT_KEY] = snapshot
    agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY] = {
        **agent_result[FLOWWEAVER_SHADOW_CAPTURE_KEY],
        "transaction_id": snapshot["transaction_id"],
        "correlation_id": snapshot["correlation_id"],
        "snapshot_id": snapshot["snapshot_id"],
    }

    audit = audit_flowweaver_shadow_capture(agent_result)

    rendered = repr(audit)
    assert audit["verdict"] == FLOWWEAVER_SHADOW_AUDIT_SCHEMA_MISMATCH
    assert audit["snapshot_ref"] is None
    assert "feishu" not in rendered
    assert "oc_private" not in rendered
    assert "ou_private" not in rendered
    assert "om_private" not in rendered


def test_shadow_audit_accepts_failed_cancelled_blocked_and_pending_lifecycle_states() -> None:
    for status, expected_transaction_status in (
        ("failed", "failed"),
        ("cancelled", "cancelled"),
        ("blocked", "blocked"),
        ("running", "running"),
    ):
        agent_result = attach_shadow_result(status=status, final_text=None, transaction_id=f"session-{status}")
        audit = audit_flowweaver_shadow_capture(agent_result)

        assert audit["verdict"] == FLOWWEAVER_SHADOW_AUDIT_READY
        assert agent_result[FLOWWEAVER_SHADOW_SNAPSHOT_KEY]["transaction"]["status"] == expected_transaction_status


def test_shadow_replay_probe_replays_safe_capture_without_returning_capture_or_snapshot() -> None:
    agent_result = attach_shadow_result(
        delivery_state={
            "final_text": {"sent": True, "reason": "stream_final_response"},
            "rich_cards_sent": [{"type": "weather.v1", "message_id": "om_weather"}],
        },
    )

    replay = replay_flowweaver_shadow_capture(agent_result, attempts=3)

    snapshot = agent_result[FLOWWEAVER_SHADOW_SNAPSHOT_KEY]
    assert replay["type"] == FLOWWEAVER_SHADOW_REPLAY_TYPE
    assert replay["verdict"] == FLOWWEAVER_SHADOW_REPLAY_REPLAYED
    assert replay["reason"] == "ok"
    assert replay["snapshot_ref"] == {
        "snapshot_key": FLOWWEAVER_SHADOW_SNAPSHOT_KEY,
        "transaction_id": snapshot["transaction_id"],
        "correlation_id": snapshot["correlation_id"],
        "snapshot_id": snapshot["snapshot_id"],
    }
    assert replay["replay_count"] == 3
    assert replay["checks"] == {
        "audit_ready": True,
        "consumer_view_valid": True,
        "snapshot_ref_stable": True,
        "audit_stable": True,
        "input_not_mutated": True,
        "side_effects_absent": True,
    }
    assert replay["side_effects"] == []
    assert "snapshot" not in replay
    assert "capture" not in replay
    assert_no_sensitive_material(replay)


def test_shadow_replay_probe_rejects_missing_invalid_or_bad_attempt_counts() -> None:
    for agent_result, attempts in (
        ({}, 2),
        (attach_shadow_result(), 0),
        (attach_shadow_result(), 6),
        (attach_shadow_result(), "2"),
    ):
        replay = replay_flowweaver_shadow_capture(agent_result, attempts=attempts)  # type: ignore[arg-type]

        assert replay["type"] == FLOWWEAVER_SHADOW_REPLAY_TYPE
        assert replay["verdict"] == FLOWWEAVER_SHADOW_REPLAY_REJECTED
        assert replay["reason"] == "missing_or_invalid_consumer_view"
        assert replay["snapshot_ref"] is None
        assert replay["replay_count"] == 0
        assert replay["side_effects"] == []


def test_shadow_replay_probe_propagates_audit_unsafe_and_schema_mismatch() -> None:
    unsafe_result = attach_shadow_result()
    unsafe_result[FLOWWEAVER_SHADOW_CAPTURE_KEY] = {
        **unsafe_result[FLOWWEAVER_SHADOW_CAPTURE_KEY],
        "lifecycle": {
            **unsafe_result[FLOWWEAVER_SHADOW_CAPTURE_KEY]["lifecycle"],
            "visible_side_effects": ["send"],
        },
    }

    unsafe_replay = replay_flowweaver_shadow_capture(unsafe_result)

    assert unsafe_replay["verdict"] == FLOWWEAVER_SHADOW_REPLAY_UNSAFE
    assert unsafe_replay["reason"] == "unsafe_snapshot"
    assert unsafe_replay["checks"]["side_effects_absent"] is False
    assert unsafe_replay["side_effects"] == []

    mismatch_result = attach_shadow_result()
    mismatch_result[FLOWWEAVER_SHADOW_CAPTURE_KEY] = {
        **mismatch_result[FLOWWEAVER_SHADOW_CAPTURE_KEY],
        "type": "flowweaver.gateway.shadow_capture.v9",
    }

    mismatch_replay = replay_flowweaver_shadow_capture(mismatch_result)

    assert mismatch_replay["verdict"] == FLOWWEAVER_SHADOW_REPLAY_SCHEMA_MISMATCH
    assert mismatch_replay["reason"] == "schema_mismatch"
    assert mismatch_replay["snapshot_ref"] is None
    assert mismatch_replay["side_effects"] == []


def test_shadow_replay_probe_detects_unstable_snapshot_ref_or_audit_output() -> None:
    first_result = attach_shadow_result(transaction_id="session-replay-first")
    second_result = attach_shadow_result(transaction_id="session-replay-second")

    class FlappingShadowMapping(Mapping[str, Any]):
        def __init__(self) -> None:
            self._pairs = (
                (
                    first_result[FLOWWEAVER_SHADOW_SNAPSHOT_KEY],
                    first_result[FLOWWEAVER_SHADOW_CAPTURE_KEY],
                ),
                (
                    second_result[FLOWWEAVER_SHADOW_SNAPSHOT_KEY],
                    second_result[FLOWWEAVER_SHADOW_CAPTURE_KEY],
                ),
            )
            self._snapshot_reads = -1
            self._active_index = 0

        def __getitem__(self, key: str) -> Any:
            value = self.get(key)
            if value is None:
                raise KeyError(key)
            return value

        def __iter__(self) -> Iterator[str]:
            return iter((FLOWWEAVER_SHADOW_SNAPSHOT_KEY, FLOWWEAVER_SHADOW_CAPTURE_KEY))

        def __len__(self) -> int:
            return 2

        def get(self, key: str, default: Any = None) -> Any:
            if key == FLOWWEAVER_SHADOW_SNAPSHOT_KEY:
                self._snapshot_reads += 1
                self._active_index = min(self._snapshot_reads, len(self._pairs) - 1)
                return self._pairs[self._active_index][0]
            if key == FLOWWEAVER_SHADOW_CAPTURE_KEY:
                return self._pairs[self._active_index][1]
            return default

    replay = replay_flowweaver_shadow_capture(FlappingShadowMapping(), attempts=2)

    assert replay["verdict"] == FLOWWEAVER_SHADOW_REPLAY_DRIFT_DETECTED
    assert replay["reason"] == "drift_detected"
    assert replay["snapshot_ref"] is None
    assert replay["checks"]["snapshot_ref_stable"] is False
    assert replay["side_effects"] == []


def test_shadow_replay_probe_does_not_mutate_agent_result() -> None:
    agent_result = attach_shadow_result(
        delivery_state={"final_text": {"sent": True, "reason": "stream_final_response"}},
    )
    before = copy.deepcopy(agent_result)

    replay = replay_flowweaver_shadow_capture(agent_result, attempts=3)

    assert replay["verdict"] == FLOWWEAVER_SHADOW_REPLAY_REPLAYED
    assert agent_result == before


def test_shadow_replay_probe_fails_closed_for_hostile_mapping() -> None:
    replay = replay_flowweaver_shadow_capture(ExplodingMapping())

    assert replay["verdict"] == FLOWWEAVER_SHADOW_REPLAY_REJECTED
    assert replay["reason"] == "missing_or_invalid_consumer_view"
    assert replay["snapshot_ref"] is None
    assert replay["side_effects"] == []


def test_shadow_replay_probe_output_omits_delivery_payloads_platform_ids_and_secret_shapes() -> None:
    bearer = "Bearer " + "fake-" + "replay-token"
    agent_result = attach_shadow_result(
        transaction_id="feishu:oc_private_chat:ou_private_user",
        delivery_state={
            "final_text": {"sent": True, "reason": "authorization=" + bearer},
            "rich_cards_sent": [
                {
                    "type": "weather.v1",
                    "message_id": "om_private_weather",
                    "raw_card_json": {"authorization": bearer},
                }
            ],
        },
        final_text="done token=" + "fake-" + "replay-secret",
    )

    replay = replay_flowweaver_shadow_capture(agent_result, attempts=2)

    rendered = repr(replay)
    assert replay["verdict"] == FLOWWEAVER_SHADOW_REPLAY_REPLAYED
    assert "transaction" not in replay
    assert "snapshot" not in replay
    assert "capture" not in replay
    assert "deliveries" not in rendered
    assert "artifacts" not in rendered
    assert "feishu" not in rendered
    assert "om_private" not in rendered
    assert "oc_private" not in rendered
    assert "ou_private" not in rendered
    assert "raw_card_json" not in rendered
    assert "authorization" not in rendered.lower()
    assert_no_sensitive_material(replay)


def test_shadow_replay_probe_rejects_opaque_platform_like_refs_without_leaking_them() -> None:
    for transaction_id, forbidden_fragment in (
        ("U123ABC", "u123abc"),
        ("123456789012345678", "123456789012345678"),
    ):
        agent_result = attach_shadow_result(transaction_id=transaction_id)

        replay = replay_flowweaver_shadow_capture(agent_result, attempts=2)

        rendered = repr(replay).lower()
        assert replay["verdict"] == FLOWWEAVER_SHADOW_REPLAY_SCHEMA_MISMATCH
        assert replay["reason"] == "schema_mismatch"
        assert replay["snapshot_ref"] is None
        assert forbidden_fragment not in rendered
        assert "transaction_123456789012345678" not in rendered


def test_shadow_consumer_contract_descriptor_is_static_safe_and_side_effect_free() -> None:
    first = describe_flowweaver_shadow_consumer_contract()
    second = describe_flowweaver_shadow_consumer_contract()

    assert first == second
    assert first["type"] == FLOWWEAVER_SHADOW_CONSUMER_CONTRACT_TYPE
    assert first["contract_version"] == "flowweaver.v0"
    assert first["snapshot_key"] == FLOWWEAVER_SHADOW_SNAPSHOT_KEY
    assert first["capture_key"] == FLOWWEAVER_SHADOW_CAPTURE_KEY
    assert first["capture_type"] == FLOWWEAVER_SHADOW_CAPTURE_TYPE
    assert first["audit_type"] == FLOWWEAVER_SHADOW_AUDIT_TYPE
    assert first["replay_type"] == FLOWWEAVER_SHADOW_REPLAY_TYPE
    assert first["allowed_consumer_inputs"] == ["agent_result_mapping"]
    assert first["allowed_consumers"] == ["in_memory_test_probe", "future_flowweaver_runtime"]
    assert first["replay_verdicts"] == [
        FLOWWEAVER_SHADOW_REPLAY_REPLAYED,
        FLOWWEAVER_SHADOW_REPLAY_REJECTED,
        FLOWWEAVER_SHADOW_REPLAY_UNSAFE,
        FLOWWEAVER_SHADOW_REPLAY_SCHEMA_MISMATCH,
        FLOWWEAVER_SHADOW_REPLAY_DRIFT_DETECTED,
    ]
    assert first["forbidden_side_effects"] == [
        "send",
        "edit",
        "render",
        "persist",
        "temporal",
        "log",
    ]
    assert first["bounds"] == {
        "default_replay_attempts": 2,
        "max_replay_attempts": 5,
        "max_corpus_entries": 20,
    }
    assert first["side_effects"] == []
    assert "snapshot" in first["forbidden_output_fields"]
    assert "capture" in first["forbidden_output_fields"]
    assert "delivery_ack" in first["forbidden_output_fields"]


def test_shadow_consumer_contract_descriptor_omits_payloads_ids_and_secret_shapes() -> None:
    descriptor = describe_flowweaver_shadow_consumer_contract()
    rendered = repr(descriptor).lower()

    assert "examples" not in descriptor
    assert "snapshot_ref" not in descriptor
    assert "om_private" not in rendered
    assert "oc_private" not in rendered
    assert "ou_private" not in rendered
    assert "u123abc" not in rendered
    assert "123456789012345678" not in rendered
    assert "raw_card_json" not in rendered
    assert "feishu_card_json" not in rendered
    assert "bearer " + "fake" not in rendered
    assert "sk-" + "123456789012" not in rendered
    assert "fake-" + "token" not in rendered
    assert "fake-" + "secret" not in rendered


CORPUS_FIXTURE = Path(__file__).with_name("fixtures") / "flowweaver_shadow_replay_corpus.json"


def load_corpus_cases() -> list[dict[str, Any]]:
    loaded = json.loads(CORPUS_FIXTURE.read_text())
    assert isinstance(loaded, list)
    return loaded


def shadow_result_from_corpus_case(case: Mapping[str, Any]) -> dict[str, Any]:
    delivery_state: dict[str, Any] = {
        "final_text": {"sent": bool(case["final_text_sent"]), "reason": None},
        "rich_cards_sent": [],
    }
    if case["final_text_sent"]:
        delivery_state["final_text"]["reason"] = "stream_final_response"
    for index, card_type in enumerate(case["rich_card_types"], start=1):
        delivery_state["rich_cards_sent"].append(
            {"type": card_type, "message_id": f"om_corpus_{index}"}
        )
    agent_result: dict[str, Any] = {"delivery_state": delivery_state}
    attached = attach_flowweaver_shadow_snapshot(
        agent_result,
        make_snapshot(
            transaction_id=str(case["transaction_id"]),
            status=str(case["status"]),
            title=str(case["title"]),
        ),
        enabled=True,
        final_text="done" if case["final_text_sent"] else None,
    )
    assert attached is not None
    return agent_result


def test_shadow_replay_corpus_fixture_is_synthetic_and_platform_neutral() -> None:
    cases = load_corpus_cases()

    assert len(cases) == 3
    for case in cases:
        assert set(case) == {
            "case_id",
            "transaction_id",
            "status",
            "title",
            "final_text_sent",
            "rich_card_types",
            "expected_replay_verdict",
        }
    rendered = repr(cases).lower()
    for forbidden in (
        "feishu",
        "telegram",
        "discord",
        "slack",
        "chat",
        "user",
        "message_id",
        "om_",
        "oc_",
        "ou_",
        "raw_card_json",
        "authorization",
        "bearer",
        "sk-",
        "token",
        "secret",
        "password",
    ):
        assert forbidden not in rendered


def test_shadow_replay_corpus_replays_expected_safe_scenarios() -> None:
    cases = load_corpus_cases()
    agent_results = [shadow_result_from_corpus_case(case) for case in cases]

    corpus = replay_flowweaver_shadow_corpus(agent_results, attempts=2)

    assert corpus["type"] == FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE
    assert corpus["verdict"] == FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED
    assert corpus["reason"] == "ok"
    assert corpus["entry_count"] == len(cases)
    assert len(corpus["entries"]) == len(cases)
    for index, (entry, case) in enumerate(zip(corpus["entries"], cases, strict=True)):
        assert entry["index"] == index
        assert entry["verdict"] == case["expected_replay_verdict"]
        assert entry["reason"] == "ok"
        assert entry["side_effects"] == []
        assert entry["checks"]["audit_ready"] is True
        assert entry["checks"]["consumer_view_valid"] is True
        assert entry["checks"]["snapshot_ref_stable"] is True
        assert entry["checks"]["audit_stable"] is True
        assert entry["checks"]["input_not_mutated"] is True
        assert entry["checks"]["side_effects_absent"] is True


def test_shadow_replay_corpus_reports_entry_verdicts_without_refs_or_payloads() -> None:
    agent_results = [shadow_result_from_corpus_case(case) for case in load_corpus_cases()]

    corpus = replay_flowweaver_shadow_corpus(agent_results, attempts=3)

    rendered = repr(corpus).lower()
    assert corpus["verdict"] == FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED
    assert corpus["side_effects"] == []
    for entry in corpus["entries"]:
        assert "snapshot_ref" not in entry
        assert "snapshot" not in entry
        assert "capture" not in entry
        assert "transaction" not in entry
    for forbidden in (
        "deliveries",
        "artifacts",
        "om_corpus",
        "om_",
        "oc_",
        "ou_",
        "raw_card_json",
        "authorization",
        "bearer",
        "fake-" + "token",
        "fake-" + "secret",
    ):
        assert forbidden not in rendered


def test_shadow_replay_corpus_rejects_invalid_or_too_large_inputs() -> None:
    valid_result = shadow_result_from_corpus_case(load_corpus_cases()[0])
    for invalid in (
        [],
        (),
        "not-a-corpus",
        b"not-a-corpus",
        [valid_result] * 21,
    ):
        corpus = replay_flowweaver_shadow_corpus(invalid, attempts=2)  # type: ignore[arg-type]

        assert corpus["type"] == FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE
        assert corpus["verdict"] == FLOWWEAVER_SHADOW_REPLAY_CORPUS_REJECTED
        assert corpus["reason"] == "invalid_corpus"
        assert corpus["entry_count"] == 0
        assert corpus["entries"] == []
        assert corpus["side_effects"] == []

    bad_attempts = replay_flowweaver_shadow_corpus([valid_result], attempts=0)
    assert bad_attempts["verdict"] == FLOWWEAVER_SHADOW_REPLAY_CORPUS_REJECTED
    assert bad_attempts["reason"] == "invalid_corpus"


def test_shadow_replay_corpus_fails_closed_for_unsafe_schema_mismatch_and_hostile_entries() -> None:
    unsafe_result = attach_shadow_result()
    unsafe_result[FLOWWEAVER_SHADOW_CAPTURE_KEY] = {
        **unsafe_result[FLOWWEAVER_SHADOW_CAPTURE_KEY],
        "lifecycle": {
            **unsafe_result[FLOWWEAVER_SHADOW_CAPTURE_KEY]["lifecycle"],
            "visible_side_effects": ["send"],
        },
    }
    mismatch_result = attach_shadow_result()
    mismatch_result[FLOWWEAVER_SHADOW_CAPTURE_KEY] = {
        **mismatch_result[FLOWWEAVER_SHADOW_CAPTURE_KEY],
        "type": "flowweaver.gateway.shadow_capture.v9",
    }

    corpus = replay_flowweaver_shadow_corpus(
        [unsafe_result, mismatch_result, ExplodingMapping()],
        attempts=2,
    )

    rendered = repr(corpus).lower()
    assert corpus["verdict"] == FLOWWEAVER_SHADOW_REPLAY_CORPUS_FAILED
    assert corpus["reason"] == "entry_failed"
    assert [entry["verdict"] for entry in corpus["entries"]] == [
        FLOWWEAVER_SHADOW_REPLAY_UNSAFE,
        FLOWWEAVER_SHADOW_REPLAY_SCHEMA_MISMATCH,
        FLOWWEAVER_SHADOW_REPLAY_REJECTED,
    ]
    assert corpus["side_effects"] == []
    assert "send" not in rendered
    assert "snapshot_ref':" not in rendered
    assert "snapshot':" not in rendered
    assert "capture':" not in rendered
    assert "flowweaver.gateway.shadow_capture.v9" not in rendered


def test_shadow_replay_corpus_does_not_mutate_entries() -> None:
    agent_results = [shadow_result_from_corpus_case(case) for case in load_corpus_cases()]
    before = copy.deepcopy(agent_results)

    corpus = replay_flowweaver_shadow_corpus(agent_results, attempts=2)

    assert corpus["verdict"] == FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED
    assert agent_results == before
