import json
from types import SimpleNamespace

import pytest

from gateway.config import Platform
from gateway.platforms.base import SendResult
from gateway.rich_results import RICH_RESULT_BEGIN, RICH_RESULT_END, maybe_deliver_weather_result


def _payload():
    return {
        "type": "weather.v1",
        "location": {"label": "成都", "country": "中国"},
        "period": "today",
        "summary": "阴/多云，18–24°C",
        "temperature": {"min_c": 18, "max_c": 24},
        "precipitation": {"max_probability_pct": 31, "amount_mm": 0.7},
        "hourly_highlights": [{"time": "10:00", "condition": "阴/多云", "temp_c": 18.6}],
        "advice": ["小伞带上"],
    }


def _marked_response():
    return (
        "模型文字 fallback\n"
        f"{RICH_RESULT_BEGIN}\n{json.dumps(_payload(), ensure_ascii=False)}\n{RICH_RESULT_END}\n"
    )


def _trusted_tool_messages():
    return [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call-weather-1",
                    "function": {
                        "name": "terminal",
                        "arguments": json.dumps(
                            {
                                "command": "python3 /home/ubuntu/workspace/hermes/skills/productivity/weather-query/scripts/weather_query.py --location 'Chengdu, Sichuan, China' --period today --format hermes-json"
                            }
                        ),
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call-weather-1", "content": _marked_response()},
    ]


def _trusted_native_weather_tool_messages():
    return [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call-weather-native-1",
                    "function": {
                        "name": "weather_query",
                        "arguments": json.dumps({"location": "成都", "period": "today"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call-weather-native-1",
            "content": json.dumps({"success": True, "output": _marked_response()}, ensure_ascii=False),
        },
    ]


class CardAdapter:
    def __init__(self, success=True):
        self.success = success
        self.cards = []
        self.sent = []

    async def send_interactive_card(self, chat_id, card, reply_to=None, metadata=None):
        self.cards.append({"chat_id": chat_id, "card": card, "reply_to": reply_to, "metadata": metadata})
        if self.success:
            return SendResult(success=True, message_id="om_weather_card_1")
        return SendResult(success=False, error="card rejected")

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        self.sent.append({"chat_id": chat_id, "content": content, "reply_to": reply_to, "metadata": metadata})
        return SendResult(success=True, message_id="text_1")


@pytest.mark.asyncio
async def test_feishu_weather_result_sends_card_and_suppresses_duplicate_text():
    adapter = CardAdapter(success=True)

    result = await maybe_deliver_weather_result(
        adapter=adapter,
        platform=Platform.FEISHU,
        chat_id="chat-1",
        response_text=_marked_response(),
        messages=_trusted_tool_messages(),
        mode="auto",
        metadata={"thread_id": "topic-1"},
    )

    assert result.card_sent is True
    assert result.response_text == "模型文字 fallback"
    assert len(adapter.cards) == 1
    assert adapter.cards[0]["metadata"] == {"thread_id": "topic-1"}
    rendered = json.dumps(adapter.cards[0]["card"], ensure_ascii=False)
    assert "成都今天天气" in rendered
    assert RICH_RESULT_BEGIN not in result.response_text


@pytest.mark.asyncio
async def test_feishu_native_weather_tool_result_sends_card():
    adapter = CardAdapter(success=True)

    result = await maybe_deliver_weather_result(
        adapter=adapter,
        platform=Platform.FEISHU,
        chat_id="chat-1",
        response_text="狗哥，天气见卡片。",
        messages=_trusted_native_weather_tool_messages(),
        mode="auto",
        metadata={"thread_id": "topic-1"},
    )

    assert result.card_sent is True
    assert result.response_text == "狗哥，天气见卡片。"
    assert len(adapter.cards) == 1
    rendered = json.dumps(adapter.cards[0]["card"], ensure_ascii=False)
    assert "成都今天天气" in rendered


@pytest.mark.asyncio
async def test_feishu_weather_card_failure_keeps_markdown_fallback_text():
    adapter = CardAdapter(success=False)

    result = await maybe_deliver_weather_result(
        adapter=adapter,
        platform=Platform.FEISHU,
        chat_id="chat-1",
        response_text=_marked_response(),
        messages=_trusted_tool_messages(),
        mode="card",
    )

    assert result.card_sent is False
    assert "🌦️ **成都今天天气**" in result.response_text
    assert RICH_RESULT_BEGIN not in result.response_text


@pytest.mark.asyncio
async def test_response_text_marker_alone_does_not_trigger_card_delivery():
    adapter = CardAdapter(success=True)

    result = await maybe_deliver_weather_result(
        adapter=adapter,
        platform=Platform.FEISHU,
        chat_id="chat-1",
        response_text=_marked_response(),
        messages=[],
        mode="card",
    )

    assert result.card_sent is False
    assert adapter.cards == []
    assert result.response_text == "模型文字 fallback"


@pytest.mark.asyncio
async def test_non_feishu_weather_result_uses_text_fallback_only():
    adapter = CardAdapter(success=True)

    result = await maybe_deliver_weather_result(
        adapter=adapter,
        platform=Platform.TELEGRAM,
        chat_id="chat-1",
        response_text="",
        messages=_trusted_tool_messages(),
        mode="auto",
    )

    assert result.card_sent is False
    assert adapter.cards == []
    assert "🌦️ **成都今天天气**" in result.response_text
    assert RICH_RESULT_BEGIN not in result.response_text


@pytest.mark.asyncio
async def test_long_diagnostic_mentioning_marker_is_not_truncated_to_prefix():
    """Regression for the live Feishu truncation: a ~1.6k-char final answer
    that merely mentions the BEGIN sentinel in prose must reach the platform
    in full, not as the ~500-char prefix before the mention."""
    adapter = CardAdapter(success=True)
    head = "诊断前缀。" * 100
    mention = f"日志里 `{RICH_RESULT_BEGIN}` 计数为 0。\n"
    tail = "诊断尾部。" * 220
    response_text = head + "\n" + mention + tail
    assert len(response_text) > 1500

    result = await maybe_deliver_weather_result(
        adapter=adapter,
        platform=Platform.FEISHU,
        chat_id="chat-1",
        response_text=response_text,
        messages=[],
        mode="auto",
    )

    assert result.card_sent is False
    assert adapter.cards == []
    assert "诊断尾部。" in result.response_text
    assert len(result.response_text) >= len(head) + len(tail)


@pytest.mark.asyncio
async def test_weather_result_mode_off_only_strips_marker_blocks():
    adapter = CardAdapter(success=True)

    result = await maybe_deliver_weather_result(
        adapter=adapter,
        platform=Platform.FEISHU,
        chat_id="chat-1",
        response_text=_marked_response(),
        messages=_trusted_tool_messages(),
        mode="off",
    )

    assert result.card_sent is False
    assert adapter.cards == []
    assert result.response_text == "模型文字 fallback"
