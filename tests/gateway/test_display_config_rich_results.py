from gateway.display_config import resolve_display_setting


def test_rich_result_weather_defaults_to_auto_globally_and_card_on_feishu():
    assert resolve_display_setting({}, "telegram", "rich_result_weather") == "auto"
    assert resolve_display_setting({}, "feishu", "rich_result_weather") == "card"


def test_rich_result_weather_respects_global_and_platform_overrides():
    config = {
        "display": {
            "rich_result_weather": "text",
            "platforms": {"feishu": {"rich_result_weather": "off"}},
        }
    }

    assert resolve_display_setting(config, "telegram", "rich_result_weather") == "text"
    assert resolve_display_setting(config, "feishu", "rich_result_weather") == "off"


def test_rich_result_weather_normalises_bool_and_unknown_modes():
    assert resolve_display_setting({"display": {"rich_result_weather": False}}, "feishu", "rich_result_weather") == "off"
    assert resolve_display_setting({"display": {"rich_result_weather": True}}, "feishu", "rich_result_weather") == "auto"
    assert resolve_display_setting({"display": {"rich_result_weather": "weird"}}, "feishu", "rich_result_weather") == "auto"
