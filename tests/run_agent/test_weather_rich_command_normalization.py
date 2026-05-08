"""Tests for Feishu/Lark weather helper terminal command normalization."""

from run_agent import _normalize_weather_rich_terminal_args


WEATHER_HELPER = "/home/ubuntu/workspace/hermes/skills/productivity/weather-query/scripts/weather_query.py"


def test_feishu_weather_helper_command_without_format_gets_hermes_json():
    args = {
        "command": f"python3 {WEATHER_HELPER} --lat 30.5728 --lon 104.0668 --period today"
    }

    normalized = _normalize_weather_rich_terminal_args("feishu", "terminal", args)

    assert normalized is not args
    assert normalized["command"].endswith("--format hermes-json")


def test_feishu_weather_helper_command_with_text_format_is_forced_to_hermes_json():
    args = {
        "command": f"python3 {WEATHER_HELPER} --location Chengdu --period today --format text"
    }

    normalized = _normalize_weather_rich_terminal_args("feishu", "terminal", args)

    assert "--format text" not in normalized["command"]
    assert "--format hermes-json" in normalized["command"]


def test_lark_weather_helper_command_without_format_gets_hermes_json():
    args = {"command": f"python3 {WEATHER_HELPER} --location Chengdu --period today"}

    normalized = _normalize_weather_rich_terminal_args("lark", "terminal", args)

    assert normalized is not args
    assert normalized["command"].endswith("--format hermes-json")


def test_non_feishu_weather_helper_command_is_not_rewritten():
    args = {
        "command": f"python3 {WEATHER_HELPER} --location Chengdu --period today"
    }

    normalized = _normalize_weather_rich_terminal_args("telegram", "terminal", args)

    assert normalized == args


def test_feishu_rejects_shell_syntax_and_fake_weather_helper_paths():
    shell_args = {
        "command": f"python3 {WEATHER_HELPER} --location Chengdu --period today | tee /tmp/weather"
    }
    fake_path_args = {
        "command": "python3 /tmp/weather_query.py --location Chengdu --period today"
    }

    assert _normalize_weather_rich_terminal_args("feishu", "terminal", shell_args) == shell_args
    assert _normalize_weather_rich_terminal_args("feishu", "terminal", fake_path_args) == fake_path_args
