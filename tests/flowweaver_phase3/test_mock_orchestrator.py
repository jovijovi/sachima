from __future__ import annotations

import pytest

from flowweaver_mock.orchestrator import FlowWeaverMockOrchestrator
from flowweaver_mock.models import STATUS_BLOCKED, STATUS_CANCELLED, STATUS_PENDING, STATUS_SUCCEEDED, sanitize_text, sanitize_value


def test_create_transaction_returns_sanitized_pending_snapshot() -> None:
    orchestrator = FlowWeaverMockOrchestrator()

    tx_id = orchestrator.create_transaction(
        source={"platform": "feishu", "chat_id": "oc_safe"},
        title="Check weather with access_token=fake-secret and summarize it",
    )
    snapshot = orchestrator.query_snapshot(tx_id)

    assert tx_id.startswith("tx_")
    assert snapshot["type"] == "flowweaver.handle.v0"
    assert snapshot["transaction_id"] == tx_id
    assert snapshot["adapter"] == "mock"
    assert snapshot["transaction"]["status"] == STATUS_PENDING
    assert "fake-secret" not in repr(snapshot)
    assert "[REDACTED]" in snapshot["transaction"]["user_request_summary"]
    assert snapshot["snapshot"]["safe_to_render"] is True


def test_submit_intent_plan_preserves_order_and_rejects_forward_dependencies() -> None:
    orchestrator = FlowWeaverMockOrchestrator()
    tx_id = orchestrator.create_transaction(source={"platform": "feishu"}, title="Compare weather")

    snapshot = orchestrator.submit_intent_plan(
        tx_id,
        [
            {"intent_id": "weather_today", "title": "Weather today"},
            {"intent_id": "weather_tomorrow", "title": "Weather tomorrow"},
            {
                "intent_id": "weather_compare",
                "title": "Compare weather",
                "dependencies": ["weather_today", "weather_tomorrow"],
            },
        ],
    )

    intents = snapshot["transaction"]["intents"]
    assert [intent["intent_id"] for intent in intents] == [
        "weather_today",
        "weather_tomorrow",
        "weather_compare",
    ]
    assert [intent["order_index"] for intent in intents] == [0, 1, 2]
    assert intents[2]["dependencies"] == ["weather_today", "weather_tomorrow"]

    with pytest.raises(ValueError, match="earlier"):
        orchestrator.submit_intent_plan(
            tx_id,
            [
                {"intent_id": "bad_synthesis", "title": "Bad", "dependencies": ["later"]},
                {"intent_id": "later", "title": "Later"},
            ],
        )


def test_record_artifact_does_not_imply_delivery_or_user_visible_coverage() -> None:
    orchestrator = FlowWeaverMockOrchestrator()
    tx_id = orchestrator.create_transaction(source={"platform": "feishu"}, title="Weather card")
    orchestrator.submit_intent_plan(tx_id, [{"intent_id": "weather_today", "title": "Weather today"}])

    snapshot = orchestrator.record_artifact(
        tx_id,
        "weather_today",
        {
            "artifact_id": "artifact_weather_today",
            "kind": "rich_card",
            "status": STATUS_SUCCEEDED,
            "title": "Weather card",
            "content_summary": "Sunny and safe to render.",
            "data": {"url": "https://example.test/weather?token=fake-token"},
        },
    )

    tx = snapshot["transaction"]
    assert tx["artifacts"][0]["artifact_id"] == "artifact_weather_today"
    assert tx["deliveries"] == []
    assert tx["intents"][0]["status"] == STATUS_PENDING
    assert tx["intent_coverage"][0]["mode"] == "blocked_waiting_for_user"
    assert tx["intent_coverage"][0]["delivery_idempotency_key"] is None
    assert "fake-token" not in repr(snapshot)


def test_ack_delivery_is_idempotent_and_requires_sent_status() -> None:
    orchestrator = FlowWeaverMockOrchestrator()
    tx_id = orchestrator.create_transaction(source={"platform": "feishu"}, title="Weather card")
    orchestrator.submit_intent_plan(tx_id, [{"intent_id": "weather_today", "title": "Weather today"}])
    orchestrator.record_artifact(
        tx_id,
        "weather_today",
        {
            "artifact_id": "artifact_weather_today",
            "kind": "rich_card",
            "status": STATUS_SUCCEEDED,
            "title": "Weather card",
            "content_summary": "Sunny.",
        },
    )

    delivery = {
        "delivery_idempotency_key": "feishu:om_weather:rich_card:weather_today",
        "surface": "rich_card",
        "platform": "feishu",
        "status": "sent",
        "message_id": "om_weather",
        "target": {"kind": "artifact", "id": "artifact_weather_today"},
        "reason": None,
    }
    snapshot = orchestrator.ack_delivery(tx_id, delivery)
    snapshot = orchestrator.ack_delivery(tx_id, dict(delivery))

    deliveries = snapshot["transaction"]["deliveries"]
    assert len(deliveries) == 1
    coverage = snapshot["transaction"]["intent_coverage"][0]
    assert coverage["mode"] == "delivered_artifact"
    assert coverage["delivery_idempotency_key"] == "feishu:om_weather:rich_card:weather_today"

    bad_delivery = dict(delivery, delivery_idempotency_key="feishu:om_weather:rich_card:bad", status="failed")
    with pytest.raises(ValueError, match="sent"):
        orchestrator.ack_delivery(tx_id, bad_delivery)

    with pytest.raises(ValueError, match="platform"):
        orchestrator.ack_delivery(tx_id, dict(delivery, delivery_idempotency_key="feishu:om_weather:rich_card:bad_platform", platform="telegram"))
    with pytest.raises(ValueError, match="idempotency"):
        orchestrator.ack_delivery(tx_id, dict(delivery, delivery_idempotency_key="bad-key"))
    with pytest.raises(ValueError, match="message_id"):
        orchestrator.ack_delivery(tx_id, dict(delivery, delivery_idempotency_key="feishu:om_weather:rich_card:bad_message", message_id=""))
    with pytest.raises(ValueError, match="reason"):
        orchestrator.ack_delivery(tx_id, dict(delivery, delivery_idempotency_key="feishu:om_weather:rich_card:bad_reason", reason="already sent"))
    with pytest.raises(ValueError, match="match"):
        orchestrator.ack_delivery(tx_id, dict(delivery, delivery_idempotency_key="feishu:om_other:rich_card:weather_today"))
    with pytest.raises(ValueError, match="match"):
        orchestrator.ack_delivery(tx_id, dict(delivery, delivery_idempotency_key="feishu:om_weather:final_text:weather_today"))
    with pytest.raises(ValueError, match="target hint"):
        orchestrator.ack_delivery(tx_id, dict(delivery, delivery_idempotency_key="feishu:om_weather:rich_card:day"))


def test_artifact_ack_target_hint_requires_unique_validated_alias() -> None:
    orchestrator = FlowWeaverMockOrchestrator()
    tx_id = orchestrator.create_transaction(source={"platform": "feishu"}, title="Weather cards")
    orchestrator.submit_intent_plan(tx_id, [{"intent_id": "weather_today", "title": "Weather today"}])
    orchestrator.record_artifact(
        tx_id,
        "weather_today",
        {
            "artifact_id": "artifact_weather_today_summary",
            "kind": "rich_card",
            "status": STATUS_SUCCEEDED,
            "title": "Weather summary",
            "content_summary": "Sunny.",
            "covers_intent_ids": ["weather_today"],
        },
    )
    orchestrator.record_artifact(
        tx_id,
        "weather_today",
        {
            "artifact_id": "artifact_weather_today_detail",
            "kind": "rich_card",
            "status": STATUS_SUCCEEDED,
            "title": "Weather detail",
            "content_summary": "Sunny with details.",
            "covers_intent_ids": ["weather_today"],
        },
    )

    delivery = {
        "delivery_idempotency_key": "feishu:om_weather:rich_card:weather_today",
        "surface": "rich_card",
        "platform": "feishu",
        "status": "sent",
        "message_id": "om_weather",
        "target": {"kind": "artifact", "id": "artifact_weather_today_summary"},
        "reason": None,
    }
    with pytest.raises(ValueError, match="target hint"):
        orchestrator.ack_delivery(tx_id, delivery)

    snapshot = orchestrator.ack_delivery(
        tx_id,
        dict(delivery, delivery_idempotency_key="feishu:om_weather:rich_card:weather_today_summary"),
    )
    assert snapshot["transaction"]["deliveries"][0]["target"]["id"] == "artifact_weather_today_summary"


def test_final_text_delivery_ack_is_required_for_answered_coverage() -> None:
    orchestrator = FlowWeaverMockOrchestrator()
    tx_id = orchestrator.create_transaction(source={"platform": "feishu"}, title="Current time")
    orchestrator.submit_intent_plan(tx_id, [{"intent_id": "current_time", "title": "Current time"}])

    snapshot = orchestrator.record_final_text(tx_id, "It is 00:20 in the mock clock.", covers_intent_ids=["current_time"])
    assert snapshot["transaction"]["intent_coverage"][0]["mode"] == "blocked_waiting_for_user"

    snapshot = orchestrator.ack_delivery(
        tx_id,
        {
            "delivery_idempotency_key": "feishu:om_time:final_text:current_time",
            "surface": "final_text",
            "platform": "feishu",
            "status": "sent",
            "message_id": "om_time",
            "target": {"kind": "final_text", "id": snapshot["transaction"]["final_text"]["final_text_id"]},
            "reason": None,
        },
    )

    coverage = snapshot["transaction"]["intent_coverage"][0]
    assert coverage["mode"] == "answered"
    assert coverage["delivery_idempotency_key"] == "feishu:om_time:final_text:current_time"
    assert snapshot["transaction"]["status"] == STATUS_SUCCEEDED


def test_final_text_coverage_takes_precedence_over_undelivered_non_rich_artifact() -> None:
    orchestrator = FlowWeaverMockOrchestrator()
    tx_id = orchestrator.create_transaction(source={"platform": "feishu"}, title="Disk status")
    orchestrator.submit_intent_plan(tx_id, [{"intent_id": "disk_status", "title": "Disk status"}])
    orchestrator.record_artifact(
        tx_id,
        "disk_status",
        {
            "artifact_id": "artifact_disk_status",
            "kind": "fallback_text",
            "status": STATUS_SUCCEEDED,
            "title": "Disk fallback",
            "content_summary": "Disk result prepared.",
            "fallback_text": "Disk has enough space.",
        },
    )
    snapshot = orchestrator.record_final_text(tx_id, "Disk has enough space.", covers_intent_ids=["disk_status"])
    snapshot = orchestrator.ack_delivery(
        tx_id,
        {
            "delivery_idempotency_key": "feishu:om_disk:final_text:disk_status",
            "surface": "final_text",
            "platform": "feishu",
            "status": "sent",
            "message_id": "om_disk",
            "target": {"kind": "final_text", "id": snapshot["transaction"]["final_text"]["final_text_id"]},
            "reason": None,
        },
    )

    coverage = snapshot["transaction"]["intent_coverage"][0]
    assert coverage["mode"] == "answered"
    assert coverage["delivery_idempotency_key"] == "feishu:om_disk:final_text:disk_status"


def test_fallback_text_artifact_delivery_counts_as_answered_not_rich_delivery() -> None:
    orchestrator = FlowWeaverMockOrchestrator()
    tx_id = orchestrator.create_transaction(source={"platform": "feishu"}, title="Disk status")
    orchestrator.submit_intent_plan(tx_id, [{"intent_id": "disk_status", "title": "Disk status"}])
    orchestrator.record_artifact(
        tx_id,
        "disk_status",
        {
            "artifact_id": "artifact_disk_status",
            "kind": "fallback_text",
            "status": STATUS_SUCCEEDED,
            "title": "Disk fallback",
            "content_summary": "Disk result prepared.",
            "fallback_text": "Disk has enough space.",
        },
    )
    snapshot = orchestrator.ack_delivery(
        tx_id,
        {
            "delivery_idempotency_key": "feishu:om_disk:fallback_text:disk_status",
            "surface": "fallback_text",
            "platform": "feishu",
            "status": "sent",
            "message_id": "om_disk",
            "target": {"kind": "artifact", "id": "artifact_disk_status"},
            "reason": None,
        },
    )
    coverage = snapshot["transaction"]["intent_coverage"][0]
    assert coverage["mode"] == "answered"
    assert coverage["delivery_idempotency_key"] == "feishu:om_disk:fallback_text:disk_status"


def test_sensitive_key_and_colon_value_variants_are_redacted() -> None:
    text = sanitize_text("password: fake-password and Authorization: Bearer fake-token")
    assert "fake-password" not in text
    assert "fake-token" not in text
    cleaned = sanitize_value({"api-key": "fake-api-key", "apikey": "fake-api-key-2", "access_key": "fake-access-key"})
    serialized = repr(cleaned)
    assert "fake-api-key" not in serialized
    assert "fake-api-key-2" not in serialized
    assert "fake-access-key" not in serialized


def test_duplicate_ack_without_sent_at_remains_idempotent_when_clock_ticks(monkeypatch: pytest.MonkeyPatch) -> None:
    orchestrator = FlowWeaverMockOrchestrator()
    tx_id = orchestrator.create_transaction(source={"platform": "feishu"}, title="Weather card")
    orchestrator.submit_intent_plan(tx_id, [{"intent_id": "weather_today", "title": "Weather today"}])
    orchestrator.record_artifact(tx_id, "weather_today", {"artifact_id": "artifact_weather_today", "kind": "rich_card", "status": STATUS_SUCCEEDED, "title": "Weather", "content_summary": "Sunny."})
    delivery = {
        "delivery_idempotency_key": "feishu:om_weather:rich_card:weather_today",
        "surface": "rich_card",
        "platform": "feishu",
        "status": "sent",
        "message_id": "om_weather",
        "target": {"kind": "artifact", "id": "artifact_weather_today"},
        "reason": None,
    }

    monkeypatch.setattr("flowweaver_mock.orchestrator.utc_now", lambda: "2026-05-04T00:00:00Z")
    orchestrator.ack_delivery(tx_id, delivery)
    monkeypatch.setattr("flowweaver_mock.orchestrator.utc_now", lambda: "2026-05-04T00:00:05Z")
    snapshot = orchestrator.ack_delivery(tx_id, dict(delivery))

    assert len(snapshot["transaction"]["deliveries"]) == 1


def test_delivered_aggregate_rich_artifact_covers_intents_even_after_intermediate_artifacts() -> None:
    orchestrator = FlowWeaverMockOrchestrator()
    tx_id = orchestrator.create_transaction(source={"platform": "feishu"}, title="Compare weather")
    orchestrator.submit_intent_plan(
        tx_id,
        [
            {"intent_id": "weather_today", "title": "Weather today"},
            {"intent_id": "weather_tomorrow", "title": "Weather tomorrow"},
            {"intent_id": "weather_compare", "title": "Compare", "dependencies": ["weather_today", "weather_tomorrow"]},
        ],
    )
    orchestrator.record_artifact(tx_id, "weather_today", {"artifact_id": "artifact_weather_today", "kind": "text_result", "status": STATUS_SUCCEEDED, "title": "Today", "content_summary": "Today facts."})
    orchestrator.record_artifact(tx_id, "weather_tomorrow", {"artifact_id": "artifact_weather_tomorrow", "kind": "text_result", "status": STATUS_SUCCEEDED, "title": "Tomorrow", "content_summary": "Tomorrow facts."})
    orchestrator.record_artifact(
        tx_id,
        "weather_compare",
        {
            "artifact_id": "artifact_weather_compare",
            "kind": "rich_card",
            "status": STATUS_SUCCEEDED,
            "title": "Comparison",
            "content_summary": "Comparison card covers all weather intents.",
            "covers_intent_ids": ["weather_today", "weather_tomorrow", "weather_compare"],
        },
    )
    snapshot = orchestrator.ack_delivery(
        tx_id,
        {
            "delivery_idempotency_key": "feishu:om_compare:rich_card:weather_compare",
            "surface": "rich_card",
            "platform": "feishu",
            "status": "sent",
            "message_id": "om_compare",
            "target": {"kind": "artifact", "id": "artifact_weather_compare"},
            "reason": None,
        },
    )

    assert {item["intent_id"]: item["mode"] for item in snapshot["transaction"]["intent_coverage"]} == {
        "weather_today": "delivered_artifact",
        "weather_tomorrow": "delivered_artifact",
        "weather_compare": "delivered_artifact",
    }


def test_failed_artifact_cannot_be_acknowledged_as_successful_delivery() -> None:
    orchestrator = FlowWeaverMockOrchestrator()
    tx_id = orchestrator.create_transaction(source={"platform": "feishu"}, title="Weather card")
    orchestrator.submit_intent_plan(tx_id, [{"intent_id": "weather_today", "title": "Weather today"}])
    orchestrator.record_artifact(tx_id, "weather_today", {"artifact_id": "artifact_weather_today", "kind": "rich_card", "status": "failed", "title": "Weather", "content_summary": "Failed."})

    with pytest.raises(ValueError, match="succeeded"):
        orchestrator.ack_delivery(
            tx_id,
            {
                "delivery_idempotency_key": "feishu:om_weather:rich_card:weather_today",
                "surface": "rich_card",
                "platform": "feishu",
                "status": "sent",
                "message_id": "om_weather",
                "target": {"kind": "artifact", "id": "artifact_weather_today"},
                "reason": None,
            },
        )


def test_render_summary_counts_total_intents_even_when_progress_is_truncated() -> None:
    orchestrator = FlowWeaverMockOrchestrator()
    tx_id = orchestrator.create_transaction(source={"platform": "feishu"}, title="Many intents")
    intent_ids = [f"intent_{index}" for index in range(11)]
    orchestrator.submit_intent_plan(tx_id, [{"intent_id": intent_id, "title": f"Intent {index}"} for index, intent_id in enumerate(intent_ids)])
    snapshot = orchestrator.record_final_text(tx_id, "All done.", covers_intent_ids=intent_ids)
    snapshot = orchestrator.ack_delivery(
        tx_id,
        {
            "delivery_idempotency_key": "feishu:om_many:final_text:intent_0",
            "surface": "final_text",
            "platform": "feishu",
            "status": "sent",
            "message_id": "om_many",
            "target": {"kind": "final_text", "id": snapshot["transaction"]["final_text"]["final_text_id"]},
            "reason": None,
        },
    )

    assert len(snapshot["snapshot"]["progress"]) == 10
    assert "11 of 11 intents complete" in snapshot["snapshot"]["render_text"]


def test_delivered_blocked_final_text_keeps_wait_state_and_delivery_key() -> None:
    orchestrator = FlowWeaverMockOrchestrator()
    tx_id = orchestrator.create_transaction(source={"platform": "feishu"}, title="Approval wait")
    orchestrator.submit_intent_plan(tx_id, [{"intent_id": "approval_wait", "title": "Await approval", "status": STATUS_BLOCKED}])
    snapshot = orchestrator.record_final_text(tx_id, "Reply approve or reject.", covers_intent_ids=["approval_wait"], status=STATUS_BLOCKED)
    snapshot = orchestrator.ack_delivery(
        tx_id,
        {
            "delivery_idempotency_key": "feishu:om_approval:final_text:approval_wait",
            "surface": "final_text",
            "platform": "feishu",
            "status": "sent",
            "message_id": "om_approval",
            "target": {"kind": "final_text", "id": snapshot["transaction"]["final_text"]["final_text_id"]},
            "reason": None,
        },
    )

    assert snapshot["transaction"]["status"] == STATUS_BLOCKED
    assert snapshot["transaction"]["final_text"]["status"] == STATUS_BLOCKED
    coverage = snapshot["transaction"]["intent_coverage"][0]
    assert coverage["mode"] == "blocked_waiting_for_user"
    assert coverage["delivery_idempotency_key"] == "feishu:om_approval:final_text:approval_wait"


def test_artifact_kind_and_render_snapshot_are_strictly_bounded_and_sanitized() -> None:
    orchestrator = FlowWeaverMockOrchestrator()
    tx_id = orchestrator.create_transaction(source={"platform": "feishu"}, title="Many intents")
    orchestrator.submit_intent_plan(
        tx_id,
        [{"intent_id": f"intent_{index}", "title": f"Intent {index}"} for index in range(11)],
    )

    with pytest.raises(ValueError, match="artifact kind"):
        orchestrator.record_artifact(
            tx_id,
            "intent_0",
            {"artifact_id": "artifact_bad", "kind": "unknown_kind", "title": "Bad", "content_summary": "Bad"},
        )

    snapshot = orchestrator.record_artifact(
        tx_id,
        "intent_0",
        {
            "artifact_id": "artifact_intent_0",
            "kind": "text_result",
            "status": STATUS_SUCCEEDED,
            "title": "Safe artifact",
            "content_summary": "Bounded summary.",
            "data": {
                "raw_command": "curl https://example.test?access_token=fake-token",
                "stdout": "secret-ish output",
                "nested": [{"full_tool_args": "password=fake-password"} for _ in range(30)],
            },
        },
    )

    rendered = snapshot["snapshot"]
    assert len(rendered["progress"]) == rendered["bounds"]["max_progress_items"] == 10
    serialized = repr(snapshot)
    assert "raw_command" not in serialized
    assert "full_tool_args" not in serialized
    assert "stdout" not in serialized
    assert "fake-token" not in serialized
    assert "fake-password" not in serialized


def test_blocked_and_cancelled_states_are_queryable_and_sanitized() -> None:
    orchestrator = FlowWeaverMockOrchestrator()
    tx_id = orchestrator.create_transaction(source={"platform": "feishu"}, title="Plan then wait")
    orchestrator.submit_intent_plan(
        tx_id,
        [
            {"intent_id": "plan", "title": "Prepare plan"},
            {"intent_id": "approval", "title": "Await approval", "dependencies": ["plan"], "status": STATUS_BLOCKED},
        ],
    )

    blocked = orchestrator.query_snapshot(tx_id)
    assert blocked["transaction"]["status"] == STATUS_BLOCKED
    assert blocked["transaction"]["intent_coverage"][1]["mode"] == "blocked_waiting_for_user"

    cancelled = orchestrator.cancel_transaction(tx_id, "User cancelled because password=fake-password")
    assert cancelled["transaction"]["status"] == STATUS_CANCELLED
    assert cancelled["snapshot"]["status"] == STATUS_CANCELLED
    assert "fake-password" not in repr(cancelled)
    assert "[REDACTED]" in repr(cancelled)
