import json
from pathlib import Path


def _parse(result: str) -> dict:
    return json.loads(result)


def test_clock_now_returns_profile_safe_china_time_shape():
    from tools.companion_life_tools import clock_now

    result = _parse(clock_now(timezone="Asia/Shanghai"))

    assert result["success"] is True
    assert result["timezone"] == "Asia/Shanghai"
    assert result["date"]
    assert result["time"]
    assert result["weekday_zh"] in {"周一", "周二", "周三", "周四", "周五", "周六", "周日"}
    assert result["iso"]


def test_calendar_lookup_returns_chinese_lunar_and_western_holidays():
    from tools.companion_life_tools import calendar_lookup

    spring = _parse(calendar_lookup(date="2026-02-17", region="all"))
    christmas = _parse(calendar_lookup(date="2026-12-25", region="all"))
    thanksgiving = _parse(calendar_lookup(date="2026-11-26", region="all"))

    assert spring["success"] is True
    assert any(item["name"] == "春节" and item["calendar"] == "chinese_lunar" for item in spring["holidays"])
    assert spring["lunar"]["month"] == 1
    assert spring["lunar"]["day"] == 1
    assert any(item["name"] == "圣诞节" and item["calendar"] == "gregorian" for item in christmas["holidays"])
    assert any(item["name"] == "感恩节" and item["region"] == "US" for item in thanksgiving["holidays"])


def test_weather_query_emits_weather_v1_rich_result_without_generic_web(monkeypatch):
    from tools.companion_life_tools import weather_query

    def fake_http_json(url: str, timeout: float = 10.0):
        assert "api.open-meteo.com" in url
        return {
            "timezone": "Asia/Shanghai",
            "current": {
                "time": "2026-06-02T15:00",
                "temperature_2m": 24.2,
                "apparent_temperature": 25.1,
                "relative_humidity_2m": 67,
                "weather_code": 3,
                "wind_speed_10m": 9.5,
            },
            "hourly": {
                "time": ["2026-06-02T15:00", "2026-06-02T18:00", "2026-06-02T21:00"],
                "temperature_2m": [24.2, 23.1, 21.8],
                "precipitation_probability": [20, 45, 60],
                "precipitation": [0.0, 0.3, 1.2],
                "weather_code": [3, 61, 61],
                "wind_speed_10m": [9.5, 8.0, 6.0],
            },
            "daily": {
                "time": ["2026-06-02"],
                "temperature_2m_min": [19.0],
                "temperature_2m_max": [25.0],
                "precipitation_sum": [1.5],
                "precipitation_probability_max": [60],
            },
        }

    monkeypatch.setattr("tools.companion_life_tools._http_json", fake_http_json)

    result = _parse(weather_query(location="成都", period="today"))

    assert result["success"] is True
    assert result["weather"]["type"] == "weather.v1"
    assert result["weather"]["location"]["label"] == "成都"
    assert result["weather"]["period"] == "today"
    assert result["weather"]["precipitation"]["max_probability_pct"] == 60
    assert "HERMES_RICH_RESULT_JSON_BEGIN" in result["output"]
    assert "HERMES_RICH_RESULT_JSON_END" in result["output"]
    assert "api.open-meteo.com" not in result["output"]


def test_journal_write_appends_to_profile_palace_journal_and_blocks_sensitive_content(monkeypatch, tmp_path):
    profile_home = tmp_path / "profiles" / "samiya"
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    from tools.companion_life_tools import journal_write

    ok = _parse(journal_write(entry="今天狗哥说小沙很棒。", mood="开心", tags=["daily"], date="2026-06-02"))
    secret = _parse(journal_write(entry="OPENAI_API_KEY=sk-test-secret", date="2026-06-02"))

    target = profile_home / "memories" / "palace" / "journal" / "2026" / "2026-06.md"
    assert ok["success"] is True
    assert ok["path"] == "journal/2026/2026-06.md"
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "## 2026-06-02" in content
    assert "今天狗哥说小沙很棒。" in content
    assert "心情：开心" in content
    assert "标签：daily" in content
    assert secret["success"] is False
    assert "sk-test-secret" not in target.read_text(encoding="utf-8")


def test_journal_write_preserves_existing_content_beyond_read_pagination(monkeypatch, tmp_path):
    profile_home = tmp_path / "profiles" / "samiya"
    target = profile_home / "memories" / "palace" / "journal" / "2026" / "2026-06.md"
    target.parent.mkdir(parents=True)
    original_tail = "line-2105-preserve-me"
    target.write_text("# Journal 2026-06\n\n" + "\n".join(f"line-{i}" for i in range(1, 2105)) + f"\n{original_tail}\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    from tools.companion_life_tools import journal_write

    result = _parse(journal_write(entry="追加一条，不许截断旧内容。", date="2026-06-03"))

    content = target.read_text(encoding="utf-8")
    assert result["success"] is True
    assert original_tail in content
    assert "追加一条，不许截断旧内容。" in content


def test_companion_life_tools_work_through_registry_dispatch(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "profile"))

    from tools.registry import discover_builtin_tools, registry

    discover_builtin_tools()

    clock = _parse(registry.dispatch("clock_now", {"timezone": "Asia/Shanghai"}))
    holiday = _parse(registry.dispatch("calendar_lookup", {"date": "2026-12-25", "region": "all"}))
    journal = _parse(registry.dispatch("journal_write", {"entry": "registry dispatch smoke", "date": "2026-06-02"}))

    assert clock["success"] is True
    assert any(item["name"] == "圣诞节" for item in holiday["holidays"])
    assert journal["success"] is True


def test_companion_life_toolsets_are_registered_but_not_core(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "profile"))

    from tools.registry import discover_builtin_tools, registry
    from toolsets import _HERMES_CORE_TOOLS, resolve_toolset

    discover_builtin_tools()

    assert resolve_toolset("clock") == ["clock_now"]
    assert "calendar_lookup" in resolve_toolset("calendar")
    assert "weather_query" in resolve_toolset("weather")
    assert "journal_write" in resolve_toolset("journal")
    for name in ("clock_now", "calendar_lookup", "weather_query", "journal_write"):
        assert name not in _HERMES_CORE_TOOLS
        assert registry.get_entry(name) is not None
