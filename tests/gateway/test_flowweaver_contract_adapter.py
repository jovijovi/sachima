"""Tests for the low-intrusion Gateway -> FlowWeaver v0 contract adapter."""

from __future__ import annotations

import re
from typing import Any

from gateway.flowweaver_contract import build_flowweaver_v0_snapshot
from gateway.progress.events import ProgressOperation, TransactionSnapshot
from gateway.progress.tracker import ProgressTracker


FLOWWEAVER_STATUSES = {
    "pending",
    "running",
    "succeeded",
    "failed",
    "blocked",
    "cancelled",
    "skipped",
}
FLOWWEAVER_DELIVERY_KEY_RE = re.compile(r"^feishu:om_[a-z0-9_]+:[a-z_]+:[a-z0-9_]+$")
FLOWWEAVER_MESSAGE_ID_RE = re.compile(r"^om_[a-z0-9_]+$")
FORBIDDEN_KEY_FRAGMENTS = (
    "authorization",
    "api_key",
    "secret",
    "token",
    "raw_args",
    "raw_command",
    "raw_output",
    "stdout",
    "stderr",
    "feishu_card_json",
)
BEARER_PREFIX = "Bearer "
OPENAI_LIKE_SECRET = "sk-" + "12345678901234567890"
FORBIDDEN_VALUE_PATTERNS = (
    re.compile("Bearer" + r"\s+[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile("sk-" + r"[A-Za-z0-9]{12,}"),
    re.compile(r"fake-[A-Za-z0-9_-]*(?:token|secret|password)", re.IGNORECASE),
)


def make_snapshot(
    *,
    transaction_id: str = "session-123",
    status: str = "running",
    title: str = "说明当前模型与思考强度配置",
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
    event_type: str = "tool.completed",
    tool_name: str | None = "terminal",
    status: str = "completed",
    preview: str | None = "python weather_query.py --token fake-token produced stdout=fake-secret",
    args_preview: str | None = "raw args should not leak token=fake-args-token",
    metadata: dict[str, Any] | None = None,
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
        duration=0.42,
        is_error=status == "failed",
        metadata=metadata or {},
    )


def assert_no_sensitive_material(obj: Any, path: str = "$." ) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            lower_key = str(key).lower()
            for fragment in FORBIDDEN_KEY_FRAGMENTS:
                assert fragment not in lower_key, f"forbidden key fragment at {path}{key}"
            assert_no_sensitive_material(value, f"{path}{key}.")
    elif isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            assert_no_sensitive_material(value, f"{path}[{index}].")
    elif isinstance(obj, str):
        for pattern in FORBIDDEN_VALUE_PATTERNS:
            assert pattern.search(obj) is None, f"forbidden value pattern at {path}: {obj!r}"


def assert_v0_delivery_ack_shape(doc: dict[str, Any]) -> None:
    deliveries_by_key = {item["delivery_idempotency_key"]: item for item in doc["transaction"]["deliveries"]}
    assert len(deliveries_by_key) == len(doc["transaction"]["deliveries"])
    for delivery in deliveries_by_key.values():
        assert FLOWWEAVER_DELIVERY_KEY_RE.fullmatch(delivery["delivery_idempotency_key"])
        assert delivery["platform"] == "feishu"
        assert delivery["status"] == "sent"
        assert FLOWWEAVER_MESSAGE_ID_RE.fullmatch(delivery["message_id"])
        assert delivery["reason"] is None
    for coverage in doc["transaction"]["intent_coverage"]:
        delivery_key = coverage.get("delivery_idempotency_key")
        if delivery_key is not None:
            assert FLOWWEAVER_DELIVERY_KEY_RE.fullmatch(delivery_key)
            assert delivery_key in deliveries_by_key


def test_builds_single_intent_snapshot_from_progress_tracker_state() -> None:
    doc = build_flowweaver_v0_snapshot(
        make_snapshot(),
        source={"platform": "feishu", "chat_id": "oc_123", "access_token": "fake-source-token"},
    )

    assert doc["type"] == "flowweaver.handle.v0"
    assert doc["contract_version"] == "flowweaver.v0"
    assert doc["adapter"] == "mock"
    assert doc["transaction_id"] == "tx_session_123"
    assert doc["workflow_id"] is None
    assert doc["run_id"] is None
    assert doc["correlation_id"] == "turn_session_123"
    assert doc["snapshot_id"] == "snap_session_123"
    assert doc["transaction"]["user_request_summary"] == "说明当前模型与思考强度配置"
    assert doc["transaction"]["intents"] == [
        {
            "intent_id": "task",
            "order_index": 0,
            "title": "说明当前模型与思考强度配置",
            "status": "running",
            "dependencies": [],
        }
    ]
    assert doc["snapshot"]["safe_to_render"] is True
    assert doc["snapshot"]["ordered_intent_ids"] == ["task"]
    assert_no_sensitive_material(doc)


def test_translates_gateway_status_vocabulary_to_flowweaver_v0_statuses() -> None:
    expected = {
        "pending": "pending",
        "running": "running",
        "completed": "succeeded",
        "failed": "failed",
        "blocked": "blocked",
        "cancelled": "cancelled",
        "unknown": "pending",
    }

    for gateway_status, flowweaver_status in expected.items():
        doc = build_flowweaver_v0_snapshot(make_snapshot(status=gateway_status))
        assert doc["transaction"]["status"] == flowweaver_status
        assert doc["transaction"]["intents"][0]["status"] == flowweaver_status
        assert doc["snapshot"]["status"] == flowweaver_status
        assert flowweaver_status in FLOWWEAVER_STATUSES


def test_maps_progress_operations_without_raw_args_or_outputs() -> None:
    doc = build_flowweaver_v0_snapshot(
        make_snapshot(operations=(make_operation(metadata={"raw_output": "fake-output-secret", "safe": "kept"}),))
    )

    operations = doc["transaction"]["operations"]
    assert len(operations) == 1
    assert operations[0]["operation_id"] == "op_1"
    assert operations[0]["intent_id"] == "task"
    assert operations[0]["kind"] == "terminal_tool_completed"
    assert operations[0]["status"] == "succeeded"
    assert "summary" in operations[0]
    assert "raw_args" not in operations[0]
    assert "raw_output" not in operations[0]
    assert "stdout" not in operations[0]
    assert "stderr" not in operations[0]
    assert "fake-token" not in repr(doc)
    assert "fake-output-secret" not in repr(doc)
    assert "fake-args-token" not in repr(doc)
    assert_no_sensitive_material(doc)


def test_final_text_delivery_state_counts_as_answered_coverage() -> None:
    doc = build_flowweaver_v0_snapshot(
        make_snapshot(status="completed"),
        delivery_state={"final_text": {"sent": True, "reason": "stream_final_response"}},
        final_text="当前模型是 GPT，思考强度按当前配置执行。 token=fake-final-token",
    )

    coverage = doc["transaction"]["intent_coverage"][0]
    assert coverage["intent_id"] == "task"
    assert coverage["mode"] == "answered"
    assert coverage["delivery_idempotency_key"] == "feishu:om_final_text:final_text:task"
    assert doc["transaction"]["final_text"]["status"] == "succeeded"
    assert doc["transaction"]["deliveries"] == [
        {
            "delivery_idempotency_key": "feishu:om_final_text:final_text:task",
            "surface": "final_text",
            "platform": "feishu",
            "status": "sent",
            "message_id": "om_final_text",
            "target": {"kind": "final_text", "id": doc["transaction"]["final_text"]["final_text_id"]},
            "reason": None,
        }
    ]
    assert "fake-final-token" not in repr(doc)
    assert_no_sensitive_material(doc)
    assert_v0_delivery_ack_shape(doc)


def test_rich_card_delivery_state_creates_artifact_and_delivery_without_suppressing_final_text() -> None:
    doc = build_flowweaver_v0_snapshot(
        make_snapshot(status="completed"),
        delivery_state={
            "final_text": {"sent": False, "reason": None},
            "rich_cards_sent": [{"type": "weather.v1", "message_id": "om_weather"}],
        },
    )

    artifacts = doc["transaction"]["artifacts"]
    deliveries = doc["transaction"]["deliveries"]
    coverage = doc["transaction"]["intent_coverage"][0]

    assert artifacts == [
        {
            "artifact_id": "artifact_weather_v1",
            "intent_id": "task",
            "kind": "rich_card",
            "status": "succeeded",
            "title": "weather.v1",
            "content_summary": "Rich card delivered: weather.v1",
            "covers_intent_ids": ["task"],
        }
    ]
    assert deliveries == [
        {
            "delivery_idempotency_key": "feishu:om_weather:rich_card:artifact_weather_v1",
            "surface": "rich_card",
            "platform": "feishu",
            "status": "sent",
            "message_id": "om_weather",
            "target": {"kind": "artifact", "id": "artifact_weather_v1"},
            "reason": None,
        }
    ]
    assert coverage["mode"] == "delivered_artifact"
    assert coverage["delivery_idempotency_key"] == "feishu:om_weather:rich_card:artifact_weather_v1"
    assert doc["transaction"]["final_text"]["status"] == "pending"
    assert_no_sensitive_material(doc)
    assert_v0_delivery_ack_shape(doc)


def test_secret_shaped_values_are_redacted_in_snapshot_repr() -> None:
    doc = build_flowweaver_v0_snapshot(
        make_snapshot(
            title="Debug Authorization: " + BEARER_PREFIX + "fake-title-token",
            operations=(make_operation(preview=OPENAI_LIKE_SECRET, args_preview="password=fake-password"),),
        ),
        source={"authorization": BEARER_PREFIX + "fake-source-token", "safe": "ok"},
        delivery_state={
            "final_text": {"sent": True, "reason": "token=fake-reason-token"},
            "rich_cards_sent": [{"type": "weather.v1", "message_id": "om_weather?token=fake-message-token"}],
        },
        final_text="done secret=fake-final-secret",
    )

    rendered = repr(doc)
    assert "fake-title-token" not in rendered
    assert "fake-source-token" not in rendered
    assert "fake-reason-token" not in rendered
    assert "fake-message-token" not in rendered
    assert "fake-final-secret" not in rendered
    assert OPENAI_LIKE_SECRET not in rendered
    assert "fake-password" not in rendered
    assert_no_sensitive_material(doc)
    assert_v0_delivery_ack_shape(doc)


def test_adapter_consumes_real_progress_tracker_without_platform_side_effects() -> None:
    tracker = ProgressTracker(transaction_id="session-123", title="说明当前模型与思考强度配置")
    tracker.record_tool_started("terminal", preview="python script.py --token fake-token")
    tracker.record_tool_completed("terminal", duration=0.42, preview="done token=fake-token")

    doc = build_flowweaver_v0_snapshot(tracker.snapshot())

    assert doc["transaction_id"] == "tx_session_123"
    assert doc["transaction"]["intents"][0]["title"] == "说明当前模型与思考强度配置"
    assert doc["transaction"]["operations"]
    assert "fake-token" not in repr(doc)
    assert "python script.py --token" not in repr(doc)
    assert_no_sensitive_material(doc)


def test_operation_preview_never_becomes_user_visible_summary_or_render_text() -> None:
    raw_command = "python export_report.py customers.csv results.csv"
    raw_output = "user@example.com\ninternal record id 42\nall tests passed"
    raw_card_json = '{"config":{"wide_screen_mode":true},"elements":[{"tag":"markdown","content":"hello"}]}'

    doc = build_flowweaver_v0_snapshot(
        make_snapshot(
            operations=(
                make_operation(operation_id="op-command", preview=raw_command),
                make_operation(operation_id="op-output", preview=raw_output),
                make_operation(operation_id="op-card", preview=raw_card_json),
            )
        )
    )

    rendered = repr(doc)
    assert raw_command not in rendered
    assert raw_output not in rendered
    assert raw_card_json not in rendered
    assert doc["transaction"]["operations"][-1]["summary"] == "terminal tool.completed succeeded."
    assert doc["snapshot"]["render_text"] == "running: terminal tool.completed succeeded."
    assert_no_sensitive_material(doc)


def test_rich_card_delivery_skips_non_feishu_message_ids() -> None:
    for message_id in ("msg-123", "om-weather"):
        doc = build_flowweaver_v0_snapshot(
            make_snapshot(status="completed"),
            delivery_state={"rich_cards_sent": [{"type": "weather.v1", "message_id": message_id}]},
        )

        assert doc["transaction"]["artifacts"] == []
        assert doc["transaction"]["deliveries"] == []
        assert doc["transaction"]["intent_coverage"][0]["delivery_idempotency_key"] is None
        assert message_id not in repr(doc)
        assert_no_sensitive_material(doc)


def test_public_ids_do_not_leak_platform_chat_or_user_identifiers() -> None:
    doc = build_flowweaver_v0_snapshot(
        make_snapshot(transaction_id="feishu:oc_private_chat:ou_private_user", status="running")
    )

    rendered = repr(doc)
    assert "oc_private_chat" not in rendered
    assert "ou_private_user" not in rendered
    assert doc["transaction_id"].startswith("tx_transaction_")
    assert doc["correlation_id"].startswith("turn_transaction_")
    assert doc["snapshot_id"].startswith("snap_transaction_")
    assert doc["transaction"]["transaction_id"] == doc["transaction_id"]
    assert_no_sensitive_material(doc)
