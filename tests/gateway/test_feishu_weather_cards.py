import json

from gateway.renderers.weather import format_weather_markdown, render_feishu_weather_card


def _report(**overrides):
    report = {
        "type": "weather.v1",
        "location": {"label": "成都", "country": "中国", "timezone": "Asia/Shanghai"},
        "period": "today",
        "generated_at": "2026-05-02T10:29:09+08:00",
        "summary": "阴/多云，18–24°C",
        "temperature": {"current_c": 18.6, "min_c": 18, "max_c": 24, "feels_like_c": 17.5},
        "precipitation": {"max_probability_pct": 31, "amount_mm": 0.7},
        "wind": {"speed_kmh": 10, "direction_deg": 80},
        "humidity_pct": 60,
        "hourly_highlights": [
            {"time": "10:00", "condition": "阴/多云", "temp_c": 18.6, "precip_probability_pct": 19},
            {"time": "17:00", "condition": "阴/多云", "temp_c": 23.5, "precip_probability_pct": 0},
        ],
        "advice": ["小伞带上", "薄外套看体感"],
    }
    report.update(overrides)
    return report


def _rendered(card):
    return json.dumps(card, ensure_ascii=False)


def test_render_feishu_weather_card_contains_core_weather_decisions():
    card = render_feishu_weather_card(_report())
    rendered = _rendered(card)

    assert card["config"]["wide_screen_mode"] is True
    assert card["header"]["title"]["content"] == "🌦️ 成都今天天气"
    assert "阴/多云，18–24°C" in rendered
    assert "18–24°C" in rendered
    assert "最高 31%" in rendered
    assert "0.7 mm" in rendered
    assert "10:00" in rendered
    assert "小伞带上" in rendered


def test_weather_markdown_fallback_is_compact_and_human_readable():
    text = format_weather_markdown(_report())

    assert text.startswith("🌦️ **成都今天天气**")
    assert "阴/多云，18–24°C" in text
    assert "最高 31%" in text
    assert "小伞带上" in text


def test_weather_card_gracefully_handles_missing_optional_fields():
    card = render_feishu_weather_card(
        _report(temperature={}, precipitation={}, wind={}, humidity_pct=None, hourly_highlights=[], advice=[])
    )
    rendered = _rendered(card)

    assert "成都今天天气" in rendered
    assert "阴/多云" in rendered
    assert "None" not in rendered


def test_weather_card_does_not_render_unknown_or_secret_shaped_fields():
    report = _report(
        summary="阴/多云 token=fake-super-secret-token",
        unknown_debug="Authorization: Bearer fake-super-secret-token",
        location={"label": "[成都](https://evil.example/?token=fake-super-secret-token)"},
        advice=["Authorization: Bearer fake-super-secret-token", "小伞带上"],
    )

    rendered = _rendered(render_feishu_weather_card(report))

    assert "fake-super-secret-token" not in rendered
    assert "Authorization" not in rendered
    assert "evil.example" not in rendered
    assert "unknown_debug" not in rendered
    assert "小伞带上" in rendered
