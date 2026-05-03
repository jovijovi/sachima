"""Tests for low-intrusion gateway delivery state helpers."""

import pytest

from gateway.delivery_state import (
    ensure_delivery_state,
    mark_final_text_sent,
    record_rich_card_sent,
    should_skip_final_text,
)


DEFAULT_DELIVERY_STATE = {
    "final_text": {"sent": False, "reason": None},
    "rich_cards_sent": [],
    "media_sent": [],
}


def test_ensure_delivery_state_creates_default_shape():
    agent_result = {}

    state = ensure_delivery_state(agent_result)

    assert state == DEFAULT_DELIVERY_STATE
    assert agent_result["delivery_state"] is state
    assert should_skip_final_text(agent_result) is False
    assert "already_sent" not in agent_result


def test_rich_card_record_does_not_mark_final_text_sent_or_set_already_sent():
    agent_result = {}

    record = record_rich_card_sent(
        agent_result,
        result_type="weather.v1",
        message_id="msg-123",
    )

    assert record == {"type": "weather.v1", "message_id": "msg-123"}
    assert agent_result["delivery_state"]["rich_cards_sent"] == [record]
    assert agent_result["rich_cards_sent"] == [record]
    assert agent_result["delivery_state"]["final_text"] == {"sent": False, "reason": None}
    assert agent_result.get("already_sent") is not True
    assert should_skip_final_text(agent_result) is False


def test_duplicate_same_rich_card_record_is_idempotent():
    agent_result = {}

    first = record_rich_card_sent(
        agent_result,
        result_type="weather.v1",
        message_id="msg-123",
    )
    second = record_rich_card_sent(
        agent_result,
        result_type="weather.v1",
        message_id="msg-123",
    )

    assert second == first
    assert agent_result["delivery_state"]["rich_cards_sent"] == [first]
    assert agent_result["rich_cards_sent"] == [first]


def test_mark_final_text_sent_requires_explicit_reason_and_sets_legacy_already_sent():
    agent_result = {}

    mark_final_text_sent(agent_result, reason="streaming_final_text")

    assert agent_result["delivery_state"]["final_text"] == {
        "sent": True,
        "reason": "streaming_final_text",
    }
    assert agent_result["already_sent"] is True
    assert should_skip_final_text(agent_result) is True
    assert agent_result["delivery_state"]["final_text"] == {
        "sent": True,
        "reason": "streaming_final_text",
    }


@pytest.mark.parametrize("reason", ["", " ", "\t\n"])
def test_mark_final_text_sent_blank_reason_raises_value_error(reason):
    agent_result = {}

    with pytest.raises(ValueError):
        mark_final_text_sent(agent_result, reason=reason)

    assert should_skip_final_text(agent_result) is False
    assert agent_result.get("already_sent") is not True


def test_legacy_already_sent_normalizes_to_final_text_sent():
    agent_result = {"already_sent": True}

    state = ensure_delivery_state(agent_result)

    assert state["final_text"] == {"sent": True, "reason": "legacy_already_sent"}
    assert should_skip_final_text(agent_result) is True


def test_existing_final_text_reason_is_sanitized_when_normalizing():
    agent_result = {
        "delivery_state": {
            "final_text": {
                "sent": True,
                "reason": "finished token=fake-token secret=fake-secret",
            }
        }
    }

    state = ensure_delivery_state(agent_result)

    assert state["final_text"]["sent"] is True
    assert "fake-token" not in state["final_text"]["reason"]
    assert "fake-secret" not in state["final_text"]["reason"]
    assert "[REDACTED]" in state["final_text"]["reason"]


def test_existing_media_sent_entries_are_sanitized_when_normalizing():
    class SecretRepr:
        def __repr__(self):
            return "SecretRepr(token=fake-object-token)"

    class SecretInt(int):
        def __repr__(self):
            return "SecretInt(token=fake-int-token)"

    agent_result = {
        "delivery_state": {
            "media_sent": [
                {
                    "type": "image",
                    "message_id": "media-1?access_token=fake-token",
                    "metadata": {
                        "secret": ["fake-secret"],
                        "access_token": {"value": "fake-nested-token"},
                        "safe": "ok",
                    },
                    "raw": b"password=fake-bytes-password",
                    "object": SecretRepr(),
                    "count": SecretInt(7),
                }
            ]
        }
    }

    state = ensure_delivery_state(agent_result)

    rendered = repr(state["media_sent"])
    assert "fake-token" not in rendered
    assert "fake-secret" not in rendered
    assert "fake-nested-token" not in rendered
    assert "fake-bytes-password" not in rendered
    assert "fake-object-token" not in rendered
    assert "fake-int-token" not in rendered
    assert "[REDACTED]" in rendered
    assert "ok" in rendered


def test_media_sent_normalization_never_raises_on_cycles_or_unprintable_keys():
    class BadKey:
        def __str__(self):
            raise RuntimeError("boom")

    cyclic = []
    cyclic.append(cyclic)
    agent_result = {
        "delivery_state": {
            "media_sent": [
                cyclic,
                {BadKey(): "safe", "token": {"value": "fake-token"}},
            ]
        }
    }

    state = ensure_delivery_state(agent_result)

    rendered = repr(state["media_sent"])
    assert "fake-token" not in rendered
    assert "[REDACTED]" in rendered
    assert "<cycle>" in rendered
    assert "<unprintable-key>" in rendered


def test_secret_shaped_values_are_redacted_in_card_records_and_reason():
    agent_result = {}

    record = record_rich_card_sent(
        agent_result,
        result_type="weather token=fake-token",
        message_id="msg secret=fake-secret",
    )
    mark_final_text_sent(
        agent_result,
        reason="complete token=fake-token secret=fake-secret",
    )

    assert record["type"] == "weather token=[REDACTED]"
    assert record["message_id"] == "msg secret=[REDACTED]"
    final_reason = agent_result["delivery_state"]["final_text"]["reason"]
    assert final_reason == "complete token=[REDACTED] secret=[REDACTED]"

    rendered = repr(agent_result)
    assert "fake-token" not in rendered
    assert "fake-secret" not in rendered
    assert "[REDACTED]" in rendered


def test_gateway_caller_final_send_skip_uses_delivery_state_helper():
    """Seam contract: final-send skip decisions go through delivery_state."""
    import inspect

    from gateway.run import GatewayRunner

    source = inspect.getsource(GatewayRunner._handle_message_with_agent)

    assert source.count("should_skip_final_text(agent_result)") >= 2
    assert (
        'agent_result.get("already_sent") and not agent_result.get("failed")'
        not in source
    )
