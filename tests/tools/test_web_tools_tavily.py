"""Contracts for the bundled Tavily search/extract provider plugin."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _isolated_web_registry():
    from agent.web_search_registry import _reset_for_tests

    _reset_for_tests()
    yield
    _reset_for_tests()


def test_provider_advertises_search_extract_and_setup() -> None:
    from plugins.web.tavily.provider import TavilyWebSearchProvider

    provider = TavilyWebSearchProvider()

    assert provider.name == "tavily"
    assert provider.display_name == "Tavily"
    assert provider.supports_search() is True
    assert provider.supports_extract() is True
    assert provider.get_setup_schema()["env_vars"][0]["key"] == "TAVILY_API_KEY"


def test_request_uses_config_aware_key_and_bearer_auth(monkeypatch) -> None:
    from plugins.web.tavily import provider as tavily

    values = {
        "TAVILY_API_KEY": "tvly-config-key",
        "TAVILY_BASE_URL": "https://proxy.example.test/tavily/",
    }
    monkeypatch.setattr(tavily, "get_provider_env", lambda name: values.get(name, ""))
    response = MagicMock()
    response.json.return_value = {"results": []}
    monkeypatch.setattr("httpx.post", MagicMock(return_value=response))

    payload = {"query": "Hermes"}
    assert tavily._tavily_request("search", payload) == {"results": []}

    call = tavily.httpx.post.call_args
    assert call.args[0] == "https://proxy.example.test/tavily/search"
    assert call.kwargs["headers"] == {
        "Authorization": "Bearer tvly-config-key",
    }
    assert call.kwargs["json"] == {"query": "Hermes"}
    assert payload == {"query": "Hermes"}
    response.raise_for_status.assert_called_once_with()


def test_request_rejects_missing_key(monkeypatch) -> None:
    from plugins.web.tavily.provider import _tavily_request

    monkeypatch.setattr(
        "plugins.web.tavily.provider.get_provider_env", lambda _name: ""
    )

    with pytest.raises(ValueError, match="TAVILY_API_KEY"):
        _tavily_request("search", {"query": "Hermes"})


def test_search_and_extract_normalize_vendor_responses(monkeypatch) -> None:
    from plugins.web.tavily.provider import TavilyWebSearchProvider

    provider = TavilyWebSearchProvider()
    responses = {
        "search": {
            "results": [
                {
                    "title": "Hermes",
                    "url": "https://example.test/hermes",
                    "content": "Agent documentation",
                }
            ]
        },
        "extract": {
            "results": [
                {
                    "url": "https://example.test/hermes",
                    "title": "Hermes",
                    "raw_content": "Full content",
                }
            ],
            "failed_results": [
                {"url": "https://example.test/missing", "error": "not found"}
            ],
        },
    }
    monkeypatch.setattr(
        "plugins.web.tavily.provider._tavily_request",
        lambda endpoint, _payload: responses[endpoint],
    )
    monkeypatch.setattr("tools.interrupt.is_interrupted", lambda: False)

    search = provider.search("Hermes", limit=3)
    extracted = provider.extract(
        ["https://example.test/hermes", "https://example.test/missing"]
    )

    assert search == {
        "success": True,
        "data": {
            "web": [
                {
                    "title": "Hermes",
                    "url": "https://example.test/hermes",
                    "description": "Agent documentation",
                    "position": 1,
                }
            ]
        },
    }
    assert extracted[0]["content"] == "Full content"
    assert extracted[0]["metadata"]["sourceURL"] == "https://example.test/hermes"
    assert extracted[1]["error"] == "not found"


def test_explicit_backend_routes_tool_through_registered_tavily(monkeypatch) -> None:
    from agent.web_search_registry import register_provider
    from plugins.web.tavily.provider import TavilyWebSearchProvider
    from tools.web_tools import web_search_tool

    provider = TavilyWebSearchProvider()
    provider.search = MagicMock(
        return_value={
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Result",
                        "url": "https://example.test",
                        "description": "Found",
                        "position": 1,
                    }
                ]
            },
        }
    )
    register_provider(provider)
    monkeypatch.setattr("tools.web_tools._ensure_web_plugins_loaded", lambda: None)
    monkeypatch.setattr("tools.web_tools._get_search_backend", lambda: "tavily")
    monkeypatch.setattr("tools.interrupt.is_interrupted", lambda: False)

    result = json.loads(web_search_tool("Hermes", limit=3))

    assert result["success"] is True
    assert result["data"]["web"][0]["title"] == "Result"
    provider.search.assert_called_once()


def test_plugin_registers_provider() -> None:
    from agent.web_search_registry import get_provider
    from plugins.web import tavily

    class Context:
        @staticmethod
        def register_web_search_provider(provider):
            from agent.web_search_registry import register_provider

            register_provider(provider)

    tavily.register(Context())

    assert get_provider("tavily") is not None
