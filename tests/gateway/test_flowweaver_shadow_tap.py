"""Tests for the default-off FlowWeaver Gateway shadow tap."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
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
    FLOWWEAVER_SHADOW_SNAPSHOT_KEY,
    attach_flowweaver_shadow_snapshot,
    audit_flowweaver_shadow_capture,
    get_flowweaver_shadow_capture,
    is_flowweaver_shadow_enabled,
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
