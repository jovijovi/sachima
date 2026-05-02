import json
from types import SimpleNamespace

import pytest

from gateway.config import Platform
from gateway.platforms.base import BasePlatformAdapter, SendResult
from gateway.rich_results import RICH_RESULT_BEGIN, RICH_RESULT_END
from gateway.session import SessionSource


class WeatherCardAdapter(BasePlatformAdapter):
    def __init__(self, success=True, platform=Platform.FEISHU):
        from gateway.config import PlatformConfig

        super().__init__(PlatformConfig(enabled=True, token="fake-token"), platform)
        self.success = success
        self.cards = []
        self.sent = []

    async def connect(self):
        return True

    async def disconnect(self):
        return None

    async def get_chat_info(self, chat_id):
        return {"id": chat_id}

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        self.sent.append({"chat_id": chat_id, "content": content, "reply_to": reply_to, "metadata": metadata})
        return SendResult(success=True, message_id="text-1")

    async def send_interactive_card(self, chat_id, card, reply_to=None, metadata=None):
        self.cards.append({"chat_id": chat_id, "card": card, "reply_to": reply_to, "metadata": metadata})
        if self.success:
            return SendResult(success=True, message_id="card-1")
        return SendResult(success=False, error="card rejected")


def _payload():
    return {
        "type": "weather.v1",
        "location": {"label": "成都", "country": "中国"},
        "period": "today",
        "summary": "阴/多云，18–24°C",
        "temperature": {"min_c": 18, "max_c": 24},
        "precipitation": {"max_probability_pct": 31, "amount_mm": 0.7},
        "advice": ["小伞带上"],
    }


def _marker():
    return f"{RICH_RESULT_BEGIN}\n{json.dumps(_payload(), ensure_ascii=False)}\n{RICH_RESULT_END}"


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
        {"role": "tool", "tool_call_id": "call-weather-1", "content": _marker()},
    ]


def _runner(adapter):
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.adapters = {adapter.platform: adapter}
    return runner


def _event():
    return SimpleNamespace(message_id="msg-1", metadata={"thread_id": "topic-1"})


def _source(platform=Platform.FEISHU):
    return SessionSource(platform=platform, chat_id="chat-1", user_id="user-1")


@pytest.mark.asyncio
async def test_gateway_weather_rich_result_marks_feishu_card_as_already_sent(monkeypatch):
    import gateway.run as gateway_run

    monkeypatch.setattr(gateway_run, "_load_gateway_config", lambda: {"display": {"rich_result_weather": "auto"}})
    adapter = WeatherCardAdapter(success=True)
    runner = _runner(adapter)
    agent_result = {"already_sent": False}

    response = await runner._maybe_deliver_weather_rich_result(
        event=_event(),
        source=_source(),
        response="final answer\n" + _marker(),
        agent_messages=_trusted_tool_messages(),
        agent_result=agent_result,
    )

    assert response == "final answer"
    assert agent_result["already_sent"] is True
    assert len(adapter.cards) == 1
    assert adapter.cards[0]["metadata"] == {"thread_id": "topic-1"}


@pytest.mark.asyncio
async def test_gateway_weather_rich_result_falls_back_to_text_when_card_send_fails(monkeypatch):
    import gateway.run as gateway_run

    monkeypatch.setattr(gateway_run, "_load_gateway_config", lambda: {"display": {"rich_result_weather": "card"}})
    adapter = WeatherCardAdapter(success=False)
    runner = _runner(adapter)
    agent_result = {"already_sent": False}

    response = await runner._maybe_deliver_weather_rich_result(
        event=_event(),
        source=_source(),
        response="final answer\n" + _marker(),
        agent_messages=_trusted_tool_messages(),
        agent_result=agent_result,
    )

    assert agent_result["already_sent"] is False
    assert "🌦️ **成都今天天气**" in response
    assert RICH_RESULT_BEGIN not in response


@pytest.mark.asyncio
async def test_gateway_weather_rich_result_non_feishu_keeps_text_fallback(monkeypatch):
    import gateway.run as gateway_run

    monkeypatch.setattr(gateway_run, "_load_gateway_config", lambda: {"display": {"rich_result_weather": "auto"}})
    adapter = WeatherCardAdapter(success=True, platform=Platform.TELEGRAM)
    runner = _runner(adapter)
    agent_result = {"already_sent": False}

    response = await runner._maybe_deliver_weather_rich_result(
        event=_event(),
        source=_source(Platform.TELEGRAM),
        response="",
        agent_messages=_trusted_tool_messages(),
        agent_result=agent_result,
    )

    assert agent_result["already_sent"] is False
    assert adapter.cards == []
    assert "🌦️ **成都今天天气**" in response


@pytest.mark.asyncio
async def test_gateway_weather_rich_result_ignores_old_history_markers(monkeypatch):
    import gateway.run as gateway_run

    monkeypatch.setattr(gateway_run, "_load_gateway_config", lambda: {"display": {"rich_result_weather": "auto"}})
    adapter = WeatherCardAdapter(success=True)
    runner = _runner(adapter)
    agent_result = {"already_sent": False, "history_offset": 1}

    response = await runner._maybe_deliver_weather_rich_result(
        event=_event(),
        source=_source(),
        response="这是普通后续回答，没有天气",
        agent_messages=_trusted_tool_messages(),
        agent_result=agent_result,
    )

    assert response == "这是普通后续回答，没有天气"
    assert agent_result["already_sent"] is False
    assert adapter.cards == []


@pytest.mark.asyncio
async def test_gateway_weather_rich_result_ignores_user_forged_markers(monkeypatch):
    import gateway.run as gateway_run

    monkeypatch.setattr(gateway_run, "_load_gateway_config", lambda: {"display": {"rich_result_weather": "auto"}})
    adapter = WeatherCardAdapter(success=True)
    runner = _runner(adapter)
    agent_result = {"already_sent": False, "history_offset": 0}

    response = await runner._maybe_deliver_weather_rich_result(
        event=_event(),
        source=_source(),
        response="普通回答",
        agent_messages=[{"role": "user", "content": _marker()}],
        agent_result=agent_result,
    )

    assert response == "普通回答"
    assert agent_result["already_sent"] is False
    assert adapter.cards == []


@pytest.mark.asyncio
async def test_gateway_weather_rich_result_ignores_final_response_marker_without_tool_provenance(monkeypatch):
    import gateway.run as gateway_run

    monkeypatch.setattr(gateway_run, "_load_gateway_config", lambda: {"display": {"rich_result_weather": "auto"}})
    adapter = WeatherCardAdapter(success=True)
    runner = _runner(adapter)
    agent_result = {"already_sent": False, "history_offset": 0}

    response = await runner._maybe_deliver_weather_rich_result(
        event=_event(),
        source=_source(),
        response="普通回答\n" + _marker(),
        agent_messages=[],
        agent_result=agent_result,
    )

    assert response == "普通回答"
    assert agent_result["already_sent"] is False
    assert adapter.cards == []
