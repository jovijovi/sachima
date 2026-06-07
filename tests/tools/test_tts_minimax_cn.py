"""RED tests for a dedicated MiniMax-CN TTS provider.

Hermes already ships a global ``minimax`` TTS provider that talks to
``https://api.minimax.io`` using ``MINIMAX_API_KEY`` / ``MINIMAX_GROUP_ID``.
MiniMax also operates a China endpoint (``https://api.minimaxi.com``) with a
*separate* account, key, and GroupId. This module specifies a first-class
``minimax-cn`` provider that is fully isolated from the global one:

* ``minimax-cn`` is a built-in/native provider (never a plugin/command fallback)
* it POSTs to ``https://api.minimaxi.com/v1/t2a_v2`` by default
* it authenticates with ``MINIMAX_CN_API_KEY`` and scopes with
  ``MINIMAX_CN_GROUP_ID``, reading config from ``tts.minimax-cn.*``
* there is **no** fallback between the global and CN providers: neither may
  borrow the other's credentials, GroupId, endpoint, or config block.

These tests are written test-first and are EXPECTED TO FAIL against the
current code base, where ``minimax-cn`` is neither registered as a built-in
nor wired into the dispatcher (so it silently degrades to Edge TTS). Do not
weaken the assertions to make them pass — implement the provider instead.
"""

from __future__ import annotations

import json
from typing import Optional
from unittest.mock import MagicMock

import pytest

from agent import tts_registry
from agent.tts_provider import TTSProvider

# Endpoint defaults the two providers must use. ``api.minimax.io`` is the
# global service; ``api.minimaxi.com`` is the China service. The two hosts
# are deliberately easy to confuse, so the tests assert on both the positive
# and the negative.
GLOBAL_T2A_ENDPOINT = "https://api.minimax.io/v1/t2a_v2"
CN_T2A_ENDPOINT = "https://api.minimaxi.com/v1/t2a_v2"


class _FakeTTSProvider(TTSProvider):
    """Minimal plugin provider used to prove built-ins win over plugins."""

    def __init__(self, name: str):
        self._name = name
        self.last_call: Optional[dict] = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def voice_compatible(self) -> bool:
        return False

    def synthesize(self, text, output_path, **kw):
        self.last_call = {"text": text, "output_path": output_path, "kwargs": dict(kw)}
        return output_path


@pytest.fixture(autouse=True)
def _reset_registry():
    tts_registry._reset_for_tests()
    yield
    tts_registry._reset_for_tests()


def _run_tool(tmp_path, monkeypatch, *, provider, env, config):
    """Drive ``text_to_speech_tool`` with a controlled provider/env/config.

    Returns ``(result_dict, captured)`` where ``captured`` records the single
    expected ``requests.post`` (url / headers / json body / call count).

    Edge TTS is stubbed to *succeed* so that the CURRENT silent-fallback
    behavior (unknown provider -> Edge default) produces a clean success
    envelope instead of crashing — that makes the CN-specific assertions fail
    as honest assertion errors, not import/IO errors. Once ``minimax-cn`` is a
    real built-in with its own handler, none of the Edge stubs are exercised.
    """
    from tools import tts_tool

    captured: dict = {"calls": 0}

    def fake_post(url, **kwargs):
        captured["calls"] += 1
        captured["url"] = url
        captured["headers"] = kwargs.get("headers", {})
        captured["json"] = kwargs.get("json")
        response = MagicMock()
        response.json.return_value = {
            "data": {"audio": b"\x00\x01".hex()},
            "base_resp": {"status_code": 0},
        }
        response.headers = {"Content-Type": "audio/mpeg"}
        response.content = b"\x00\x01"
        response.raise_for_status = MagicMock()
        return response

    def fake_env(name, default=None):
        return env.get(name, default)

    async def fake_edge(text, output_path, cfg):
        with open(output_path, "wb") as fh:
            fh.write(b"edge-bytes")
        return output_path

    monkeypatch.setattr(tts_tool, "get_env_value", fake_env)
    monkeypatch.setattr(
        tts_tool, "_load_tts_config", lambda: {"provider": provider, **config}
    )
    # Skip real plugin discovery; harmless once minimax-cn short-circuits as a
    # built-in (the dispatcher is never reached for built-in names).
    monkeypatch.setattr(tts_tool, "_dispatch_to_plugin_provider", lambda *a, **k: None)
    monkeypatch.setattr(tts_tool, "_import_edge_tts", lambda: MagicMock())
    monkeypatch.setattr(tts_tool, "_generate_edge_tts", fake_edge)
    monkeypatch.setattr("requests.post", fake_post)

    out = str(tmp_path / "out.mp3")
    result = json.loads(tts_tool.text_to_speech_tool(text="hello", output_path=out))
    return result, captured


# ---------------------------------------------------------------------------
# 1. minimax-cn is a built-in/native provider (not plugin/command fallback)
# ---------------------------------------------------------------------------
class TestMinimaxCnIsBuiltin:
    def test_minimax_cn_in_builtin_set(self):
        from tools import tts_tool

        assert "minimax-cn" in tts_tool.BUILTIN_TTS_PROVIDERS, (
            "minimax-cn must be a first-class built-in provider so it is "
            "dispatched natively, not treated as a tts.providers.<name> "
            "command/plugin fallback."
        )

    def test_dispatcher_short_circuits_minimax_cn(self):
        """A built-in name must win even if a plugin registers under it.

        With minimax-cn recognized as a built-in, the plugin dispatcher must
        return ``None`` (so the native elif handles it). Today minimax-cn is
        unknown, so the dispatcher would hand the call to the registered
        plugin instead — exactly the precedence bug this guards against.
        """
        from tools import tts_tool

        tts_registry.register_provider(_FakeTTSProvider(name="minimax-cn"))
        result = tts_tool._dispatch_to_plugin_provider(
            text="hi",
            output_path="/tmp/out.mp3",
            provider="minimax-cn",
            tts_config={},
        )
        assert result is None


# ---------------------------------------------------------------------------
# 2. minimax-cn hits the CN endpoint and authenticates with the CN key
# ---------------------------------------------------------------------------
class TestMinimaxCnEndpointAndKey:
    def test_uses_cn_endpoint_and_cn_api_key(self, tmp_path, monkeypatch):
        result, captured = _run_tool(
            tmp_path,
            monkeypatch,
            provider="minimax-cn",
            # Both keys present: the CN provider must pick the CN one.
            env={"MINIMAX_CN_API_KEY": "cn-key", "MINIMAX_API_KEY": "global-key"},
            config={"minimax-cn": {}},
        )
        assert result["success"] is True
        # Discriminator: the CN HTTP backend must actually be called.
        assert captured["calls"] == 1, (
            "minimax-cn did not reach the MiniMax-CN HTTP backend — it most "
            "likely fell through to the Edge TTS default."
        )
        assert captured["url"].startswith(CN_T2A_ENDPOINT)
        assert "api.minimax.io" not in captured["url"]
        assert captured["headers"].get("Authorization") == "Bearer cn-key"


# ---------------------------------------------------------------------------
# 3. minimax-cn appends only MINIMAX_CN_GROUP_ID (never MINIMAX_GROUP_ID)
# ---------------------------------------------------------------------------
class TestMinimaxCnGroupId:
    def test_uses_cn_group_id_not_global(self, tmp_path, monkeypatch):
        result, captured = _run_tool(
            tmp_path,
            monkeypatch,
            provider="minimax-cn",
            env={
                "MINIMAX_CN_API_KEY": "cn-key",
                "MINIMAX_CN_GROUP_ID": "cn-group",
                "MINIMAX_API_KEY": "global-key",
                "MINIMAX_GROUP_ID": "global-group",
            },
            config={"minimax-cn": {}},
        )
        assert result["success"] is True
        assert captured["calls"] == 1
        assert "GroupId=cn-group" in captured["url"]
        assert "GroupId=global-group" not in captured["url"]

    def test_reads_minimax_cn_config_block_not_global(self, tmp_path, monkeypatch):
        """tts.minimax-cn.* drives the request — never the global tts.minimax.*."""
        result, captured = _run_tool(
            tmp_path,
            monkeypatch,
            provider="minimax-cn",
            env={"MINIMAX_CN_API_KEY": "cn-key"},
            config={
                "minimax-cn": {"voice_id": "cn-voice"},
                "minimax": {"voice_id": "global-voice"},
            },
        )
        assert result["success"] is True
        assert captured["calls"] == 1
        voice_setting = (captured["json"] or {}).get("voice_setting", {})
        assert voice_setting.get("voice_id") == "cn-voice"


# ---------------------------------------------------------------------------
# 4. Missing MINIMAX_CN_API_KEY fails loudly — no fallback to the global key
# ---------------------------------------------------------------------------
class TestMinimaxCnNoFallback:
    def test_missing_cn_key_fails_even_with_global_key(self, tmp_path, monkeypatch):
        result, captured = _run_tool(
            tmp_path,
            monkeypatch,
            provider="minimax-cn",
            # CN key absent on purpose; only the global key exists.
            env={"MINIMAX_API_KEY": "global-key"},
            config={"minimax-cn": {}},
        )
        # No silent fallback to Edge and no borrowing of the global key: the
        # call must fail and the error must name the CN-specific variable.
        assert result["success"] is False, (
            "minimax-cn with no MINIMAX_CN_API_KEY must fail loudly, not "
            "silently fall back to Edge or to the global MiniMax key."
        )
        assert "MINIMAX_CN_API_KEY" in result.get("error", "")
        assert captured["calls"] == 0


# ---------------------------------------------------------------------------
# 5. Regression guard: the existing global minimax stays global (passes today)
# ---------------------------------------------------------------------------
class TestGlobalMinimaxStaysGlobal:
    """The global ``minimax`` provider must keep using MINIMAX_* + the global
    endpoint and never borrow the CN key/GroupId/endpoint. Passes today and
    must keep passing after minimax-cn lands."""

    def test_global_minimax_uses_global_key_and_endpoint(self, tmp_path, monkeypatch):
        from tools import tts_tool

        captured: dict = {"calls": 0}

        def fake_post(url, **kwargs):
            captured["calls"] += 1
            captured["url"] = url
            captured["headers"] = kwargs.get("headers", {})
            response = MagicMock()
            response.json.return_value = {
                "data": {"audio": b"\x00\x01".hex()},
                "base_resp": {"status_code": 0},
            }
            response.raise_for_status = MagicMock()
            return response

        env = {
            "MINIMAX_API_KEY": "global-key",
            "MINIMAX_CN_API_KEY": "cn-key",
            "MINIMAX_GROUP_ID": "global-group",
            "MINIMAX_CN_GROUP_ID": "cn-group",
        }
        monkeypatch.setattr(
            tts_tool, "get_env_value", lambda n, d=None: env.get(n, d)
        )
        monkeypatch.setattr("requests.post", fake_post)

        tts_tool._generate_minimax_tts("hi", str(tmp_path / "out.mp3"), {})

        assert captured["headers"].get("Authorization") == "Bearer global-key"
        assert captured["url"].startswith(GLOBAL_T2A_ENDPOINT)
        assert "api.minimaxi.com" not in captured["url"]
        assert "GroupId=global-group" in captured["url"]
        assert "GroupId=cn-group" not in captured["url"]


# ---------------------------------------------------------------------------
# 6. Provider metadata: max-text-length table and availability gate
# ---------------------------------------------------------------------------
class TestMinimaxCnMetadata:
    def test_minimax_cn_has_max_text_length_entry(self):
        from tools.tts_tool import PROVIDER_MAX_TEXT_LENGTH

        assert PROVIDER_MAX_TEXT_LENGTH.get("minimax-cn") == 10000

    def test_resolve_max_text_length_for_minimax_cn(self):
        from tools.tts_tool import _resolve_max_text_length

        # Without an entry the resolver returns FALLBACK_MAX_TEXT_LENGTH (4000);
        # minimax-cn must resolve to the documented MiniMax 10k cap instead.
        assert _resolve_max_text_length("minimax-cn", {}) == 10000

    def test_only_cn_key_makes_tts_available(self, monkeypatch):
        """check_tts_requirements gates whether /voice can be offered. A user
        who only has MINIMAX_CN_API_KEY (China account) must count as having a
        working provider."""
        from tools import tts_tool

        env = {"MINIMAX_CN_API_KEY": "cn-key"}
        monkeypatch.setattr(tts_tool, "get_env_value", lambda n, d=None: env.get(n, d))
        monkeypatch.setattr(
            tts_tool, "_has_any_command_tts_provider", lambda *a, **k: False
        )
        monkeypatch.setattr(
            tts_tool, "_import_edge_tts", MagicMock(side_effect=ImportError)
        )
        monkeypatch.setattr(
            tts_tool, "_import_elevenlabs", MagicMock(side_effect=ImportError)
        )
        monkeypatch.setattr(
            tts_tool, "_import_openai_client", MagicMock(side_effect=ImportError)
        )
        monkeypatch.setattr(tts_tool, "_has_openai_audio_backend", lambda: False)
        monkeypatch.setattr(
            tts_tool, "_import_mistral_client", MagicMock(side_effect=ImportError)
        )
        monkeypatch.setattr(tts_tool, "_check_neutts_available", lambda: False)
        monkeypatch.setattr(tts_tool, "_check_kittentts_available", lambda: False)
        monkeypatch.setattr(tts_tool, "_check_piper_available", lambda: False)
        monkeypatch.setattr(
            "tools.xai_http.resolve_xai_http_credentials", lambda: {}
        )

        assert tts_tool.check_tts_requirements() is True
