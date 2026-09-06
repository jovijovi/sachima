"""Compatibility tests for the legacy MiniMax-CN TTS selection."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from tools import tts_tool


@pytest.fixture
def minimax_env(monkeypatch):
    values: dict[str, str] = {}
    monkeypatch.setattr(
        tts_tool,
        "get_env_value",
        lambda name, default=None: values.get(name, default),
    )
    return values


def test_legacy_provider_selects_cn_region_and_key(minimax_env):
    minimax_env.update(
        {
            "MINIMAX_API_KEY": "global-key",
            "MINIMAX_CN_API_KEY": "cn-key",
        }
    )

    runtime = tts_tool._resolve_minimax_tts_runtime(
        {"provider": "minimax-cn", "minimax-cn": {}}
    )

    assert runtime.region == "cn"
    assert runtime.endpoint == tts_tool.DEFAULT_MINIMAX_CN_BASE_URL
    assert runtime.credential_source == "MINIMAX_CN_API_KEY"
    assert runtime.api_key == "cn-key"


def test_legacy_provider_rejects_conflicting_canonical_global_region(minimax_env):
    minimax_env["MINIMAX_CN_API_KEY"] = "cn-key"

    with pytest.raises(ValueError, match="conflicts"):
        tts_tool._resolve_minimax_tts_runtime(
            {
                "provider": "minimax-cn",
                "minimax": {"region": "global"},
                "minimax-cn": {},
            }
        )


def test_legacy_provider_does_not_borrow_global_key(minimax_env):
    minimax_env["MINIMAX_API_KEY"] = "global-key"

    with pytest.raises(ValueError, match="MINIMAX_CN_API_KEY"):
        tts_tool._resolve_minimax_tts_runtime(
            {"provider": "minimax-cn", "minimax-cn": {}}
        )


def test_legacy_config_drives_request_and_uses_only_cn_group_id(
    tmp_path, monkeypatch, minimax_env
):
    minimax_env.update(
        {
            "MINIMAX_API_KEY": "global-key",
            "MINIMAX_GROUP_ID": "global-group",
            "MINIMAX_CN_API_KEY": "cn-key",
            "MINIMAX_CN_GROUP_ID": "cn-group",
        }
    )
    captured: dict[str, object] = {}

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        response = MagicMock()
        response.json.return_value = {
            "data": {"audio": b"audio".hex()},
            "base_resp": {"status_code": 0},
        }
        response.raise_for_status = MagicMock()
        return response

    monkeypatch.setattr("requests.post", fake_post)
    output = tmp_path / "cn.mp3"

    tts_tool._generate_minimax_tts(
        "hello",
        str(output),
        {
            "provider": "minimax-cn",
            "minimax": {"voice_id": "global-voice"},
            "minimax-cn": {"voice_id": "cn-voice"},
        },
    )

    assert output.read_bytes() == b"audio"
    assert str(captured["url"]).startswith(tts_tool.DEFAULT_MINIMAX_CN_BASE_URL)
    assert "GroupId=cn-group" in str(captured["url"])
    assert "global-group" not in str(captured["url"])
    assert captured["headers"]["Authorization"] == "Bearer cn-key"
    assert captured["json"]["voice_setting"]["voice_id"] == "cn-voice"


def test_legacy_provider_dispatches_through_unified_minimax_backend(
    tmp_path, monkeypatch, minimax_env
):
    minimax_env["MINIMAX_CN_API_KEY"] = "cn-key"
    monkeypatch.setattr(
        tts_tool,
        "_load_tts_config",
        lambda: {"provider": "minimax-cn", "minimax-cn": {}},
    )
    generated: dict[str, object] = {}

    def fake_generate(text, output_path, config):
        generated.update(text=text, config=config)
        with open(output_path, "wb") as stream:
            stream.write(b"audio")
        return output_path

    monkeypatch.setattr(tts_tool, "_generate_minimax_tts", fake_generate)

    result = json.loads(
        tts_tool.text_to_speech_tool(
            text="hello",
            output_path=str(tmp_path / "legacy.mp3"),
        )
    )

    assert result["success"] is True
    assert result["provider"] == "minimax-cn"
    assert generated["text"] == "hello"
    assert tts_tool._resolve_max_text_length("minimax-cn", {}) == 10000
