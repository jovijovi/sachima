#!/usr/bin/env python3
"""Tests for xAI image generation provider."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fake_api_key(monkeypatch):
    """Ensure XAI_API_KEY is set for all tests."""
    monkeypatch.setenv("XAI_API_KEY", "test-key-12345")


# ---------------------------------------------------------------------------
# Provider class tests
# ---------------------------------------------------------------------------


class TestXAIImageGenProvider:
    def test_name(self):
        from plugins.image_gen.xai import XAIImageGenProvider

        provider = XAIImageGenProvider()
        assert provider.name == "xai"

    def test_display_name(self):
        from plugins.image_gen.xai import XAIImageGenProvider

        provider = XAIImageGenProvider()
        assert provider.display_name == "xAI (Grok)"

    def test_is_available_with_key(self, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "sk-xxx")
        from plugins.image_gen.xai import XAIImageGenProvider

        provider = XAIImageGenProvider()
        assert provider.is_available() is True

    def test_is_available_without_key(self, monkeypatch):
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        from plugins.image_gen.xai import XAIImageGenProvider

        provider = XAIImageGenProvider()
        assert provider.is_available() is False

    def test_list_models(self):
        from plugins.image_gen.xai import XAIImageGenProvider

        provider = XAIImageGenProvider()
        models = provider.list_models()
        assert len(models) >= 1
        assert models[0]["id"] == "grok-imagine-image"

    def test_default_model(self):
        from plugins.image_gen.xai import XAIImageGenProvider

        provider = XAIImageGenProvider()
        assert provider.default_model() == "grok-imagine-image"

    def test_get_setup_schema(self):
        from plugins.image_gen.xai import XAIImageGenProvider

        provider = XAIImageGenProvider()
        schema = provider.get_setup_schema()
        assert schema["name"] == "xAI Grok Imagine (image)"
        assert schema["badge"] == "paid"
        # Auth resolution is delegated to the shared "xai_grok" post_setup
        # hook so the picker doesn't blindly prompt for XAI_API_KEY when the
        # user is already signed in via xAI Grok OAuth.
        assert schema["env_vars"] == []
        assert schema["post_setup"] == "xai_grok"


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestConfig:
    def test_default_model(self):
        from plugins.image_gen.xai import _resolve_model

        model_id, meta = _resolve_model()
        assert model_id == "grok-imagine-image"

    def test_default_resolution(self):
        from plugins.image_gen.xai import _resolve_resolution

        assert _resolve_resolution() == "1k"

    def test_custom_model(self, monkeypatch):
        monkeypatch.setenv("XAI_IMAGE_MODEL", "grok-imagine-image")
        from plugins.image_gen.xai import _resolve_model

        model_id, _ = _resolve_model()
        assert model_id == "grok-imagine-image"


# ---------------------------------------------------------------------------
# Generate tests
# ---------------------------------------------------------------------------


class TestGenerate:
    def test_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        from plugins.image_gen.xai import XAIImageGenProvider

        provider = XAIImageGenProvider()
        result = provider.generate(prompt="test")
        assert result["success"] is False
        assert "XAI_API_KEY" in result["error"]

    def test_successful_generation(self):
        from plugins.image_gen.xai import XAIImageGenProvider

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": [{"b64_json": "dGVzdC1pbWFnZS1kYXRh"}],  # base64 "test-image-data"
        }

        with patch("plugins.image_gen.xai.requests.post", return_value=mock_resp):
            with patch("plugins.image_gen.xai.save_b64_image", return_value="/tmp/test.png"):
                provider = XAIImageGenProvider()
                result = provider.generate(prompt="A cat playing piano")

        assert result["success"] is True
        assert result["image"] == "/tmp/test.png"
        assert result["provider"] == "xai"
        assert result["model"] == "grok-imagine-image"

    def test_successful_url_response(self):
        """xAI URL response is cached locally — #26942 contract.

        Pre-fix this asserted ``result["image"] == "<the bare URL>"``, which
        was exactly the bug: xAI's ``imgen.x.ai/xai-tmp-*`` URLs expire fast
        and the gateway 404'd by ``send_photo`` time.  Post-fix the URL
        bytes are downloaded at tool-completion and the result carries an
        absolute filesystem path the gateway can upload from.
        """
        from plugins.image_gen.xai import XAIImageGenProvider

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": [{"url": "https://imgen.x.ai/xai-tmp-imgen-test.jpeg"}],
        }

        with patch("plugins.image_gen.xai.requests.post", return_value=mock_resp), \
             patch(
                 "plugins.image_gen.xai.save_url_image",
                 return_value=Path("/tmp/xai_grok-imagine-image_20260524_000000_deadbeef.jpg"),
             ) as mock_save_url:
            provider = XAIImageGenProvider()
            result = provider.generate(prompt="A cat playing piano")

        assert result["success"] is True
        assert result["image"].startswith("/"), (
            f"URL response must be cached to an absolute path, got {result['image']!r}"
        )
        assert "imgen.x.ai" not in result["image"], (
            "ephemeral xAI URL must not leak into result.image — caller will 404"
        )
        # The downloader should have been called exactly once with the URL
        # and an xai-prefixed cache filename.
        mock_save_url.assert_called_once()
        call_args, call_kwargs = mock_save_url.call_args
        assert call_args[0] == "https://imgen.x.ai/xai-tmp-imgen-test.jpeg"
        assert call_kwargs.get("prefix", "").startswith("xai_")

    def test_url_response_falls_back_to_bare_url_when_download_fails(self):
        """If caching the URL fails (network blip, 404 in-flight), the
        provider must NOT hard-error — fall through to returning the bare
        URL so the agent surface at least sees *something*.  The gateway's
        existing URL-send fallback then has a chance to succeed; if it
        too 404s, the user gets the original (now legible) error rather
        than an opaque "image generation failed" tool result.
        """
        import requests as req_lib
        from plugins.image_gen.xai import XAIImageGenProvider

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": [{"url": "https://imgen.x.ai/xai-tmp-imgen-already-404.jpeg"}],
        }

        with patch("plugins.image_gen.xai.requests.post", return_value=mock_resp), \
             patch(
                 "plugins.image_gen.xai.save_url_image",
                 side_effect=req_lib.HTTPError("404 from CDN"),
             ):
            provider = XAIImageGenProvider()
            result = provider.generate(prompt="A cat playing piano")

        assert result["success"] is True, (
            "Cache failure must not turn into a tool error — gateway gets a chance to retry"
        )
        assert result["image"] == "https://imgen.x.ai/xai-tmp-imgen-already-404.jpeg"

    def test_api_error(self):
        import requests as req_lib
        from plugins.image_gen.xai import XAIImageGenProvider

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        mock_resp.json.return_value = {"error": {"message": "Invalid API key"}}
        mock_resp.raise_for_status.side_effect = req_lib.HTTPError(response=mock_resp)

        with patch("plugins.image_gen.xai.requests.post", return_value=mock_resp):
            provider = XAIImageGenProvider()
            result = provider.generate(prompt="test")

        assert result["success"] is False
        assert result["error_type"] == "api_error"

    def test_api_error_preserves_real_response_status(self):
        import requests as req_lib
        from plugins.image_gen.xai import XAIImageGenProvider

        response = req_lib.Response()
        response.status_code = 401
        response._content = json.dumps({"error": {"message": "Invalid API key"}}).encode()
        response.headers["Content-Type"] = "application/json"

        response.raise_for_status = MagicMock(
            side_effect=req_lib.HTTPError(response=response)
        )

        with patch("plugins.image_gen.xai.requests.post", return_value=response):
            provider = XAIImageGenProvider()
            result = provider.generate(prompt="test")

        assert result["success"] is False
        assert result["error_type"] == "api_error"
        assert "xAI image generation failed (401): Invalid API key" in result["error"]

    def test_timeout(self):
        import requests as req_lib

        from plugins.image_gen.xai import XAIImageGenProvider

        with patch("plugins.image_gen.xai.requests.post", side_effect=req_lib.Timeout()):
            provider = XAIImageGenProvider()
            result = provider.generate(prompt="test")

        assert result["success"] is False
        assert result["error_type"] == "timeout"

    def test_empty_response(self):
        from plugins.image_gen.xai import XAIImageGenProvider

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": []}

        with patch("plugins.image_gen.xai.requests.post", return_value=mock_resp):
            provider = XAIImageGenProvider()
            result = provider.generate(prompt="test")

        assert result["success"] is False
        assert result["error_type"] == "empty_response"

    def test_auth_header(self):
        from plugins.image_gen.xai import XAIImageGenProvider

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": [{"url": "https://xai.image/test.png"}],
        }

        with patch("plugins.image_gen.xai.requests.post", return_value=mock_resp) as mock_post:
            provider = XAIImageGenProvider()
            provider.generate(prompt="test")

        call_args = mock_post.call_args
        headers = call_args.kwargs.get("headers") or call_args[1].get("headers")
        assert "Bearer test-key-12345" in headers["Authorization"]
        assert "Hermes-Agent" in headers["User-Agent"]

    def test_payload_resolution_is_literal_1k_or_2k(self):
        """Regression: xAI API rejects numeric resolutions ("1024"/"2048") with 422.

        The endpoint expects the literal strings "1k" or "2k". Ensure the wire
        payload carries that literal — not a numeric mapping. See PR #18678.
        """
        from plugins.image_gen.xai import XAIImageGenProvider

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": [{"url": "https://xai.image/test.png"}]}

        with patch("plugins.image_gen.xai.requests.post", return_value=mock_resp) as mock_post:
            provider = XAIImageGenProvider()
            provider.generate(prompt="test")

        payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert payload["resolution"] in {"1k", "2k"}, (
            f"resolution must be the literal '1k' or '2k', got {payload['resolution']!r}"
        )

    def test_payload_requests_base64_response(self):
        """xAI image gen should request b64_json so Hermes never depends on imgen.x.ai temp URLs."""
        from plugins.image_gen.xai import XAIImageGenProvider

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": [{"b64_json": "dGVzdC1pbWFnZS1kYXRh"}]}

        with patch("plugins.image_gen.xai.requests.post", return_value=mock_resp) as mock_post, \
             patch("plugins.image_gen.xai.save_b64_image", return_value="/tmp/test.png"):
            provider = XAIImageGenProvider()
            provider.generate(prompt="test")

        payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert payload["response_format"] == "b64_json"


# ---------------------------------------------------------------------------
# Edit / image-to-image tests
# ---------------------------------------------------------------------------


# Smallest byte sequence that passes the PNG magic-byte sniff.
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class TestEdit:
    def test_supports_edit_is_true(self):
        from plugins.image_gen.xai import XAIImageGenProvider

        assert XAIImageGenProvider().supports_edit() is True

    def test_edit_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        from plugins.image_gen.xai import XAIImageGenProvider

        provider = XAIImageGenProvider()
        result = provider.edit(prompt="make it blue", image="https://x/a.png")
        assert result["success"] is False
        assert result["error_type"] == "missing_api_key"

    def test_edit_requires_prompt(self):
        from plugins.image_gen.xai import XAIImageGenProvider

        provider = XAIImageGenProvider()
        result = provider.edit(prompt="   ", image="https://x/a.png")
        assert result["success"] is False
        assert result["error_type"] == "invalid_input"

    def test_edit_requires_image(self):
        from plugins.image_gen.xai import XAIImageGenProvider

        provider = XAIImageGenProvider()
        result = provider.edit(prompt="make it blue", image="")
        assert result["success"] is False
        assert result["error_type"] == "invalid_input"

    def test_edit_calls_images_edits_endpoint(self):
        from plugins.image_gen.xai import XAIImageGenProvider

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": [{"b64_json": "dGVzdA=="}]}

        with patch("plugins.image_gen.xai.requests.post", return_value=mock_resp) as mock_post, \
             patch("plugins.image_gen.xai.save_b64_image", return_value="/tmp/edited.png"):
            provider = XAIImageGenProvider()
            provider.edit(prompt="make it blue", image="https://x/a.png")

        url = mock_post.call_args.args[0] if mock_post.call_args.args else mock_post.call_args[0][0]
        assert url.endswith("/images/edits"), f"edit must POST /v1/images/edits, got {url!r}"

    def test_edit_url_input_uses_image_object(self):
        """http(s) URLs go in the official ``image`` object shape.

        xAI's ``/v1/images/edits`` request JSON wraps the source image in an
        object: ``"image": {"url": "<url-or-data-uri>", "type": "image_url"}``
        (https://docs.x.ai/developers/model-capabilities/images/editing). The
        earlier top-level ``image_url`` / raw-string ``image`` shapes were
        wrong and are rejected by the endpoint.
        """
        from plugins.image_gen.xai import XAIImageGenProvider

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": [{"b64_json": "dGVzdA=="}]}

        with patch("plugins.image_gen.xai.requests.post", return_value=mock_resp) as mock_post, \
             patch("plugins.image_gen.xai.save_b64_image", return_value="/tmp/edited.png"):
            provider = XAIImageGenProvider()
            result = provider.edit(prompt="make it blue", image="https://imgen.x.ai/a.png")

        payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert payload["model"] == "grok-imagine-image"
        assert payload["prompt"] == "make it blue"
        assert payload["response_format"] == "b64_json"
        assert payload["image"] == {
            "url": "https://imgen.x.ai/a.png",
            "type": "image_url",
        }, "http URLs must be wrapped in the {url, type:image_url} object"
        assert "image_url" not in payload, "no top-level image_url field — use image.url"
        assert result["success"] is True
        assert result["image"] == "/tmp/edited.png"
        assert result["provider"] == "xai"

    def test_edit_local_path_becomes_data_uri(self, tmp_path):
        """Local files are inlined as a base64 data URI inside the image object.

        Per the docs the ``url`` field accepts a public URL *or* a
        base64-encoded data URI, so a validated local file rides the same
        ``{"url": ..., "type": "image_url"}`` object shape.
        """
        from plugins.image_gen.xai import XAIImageGenProvider

        src = tmp_path / "input.png"
        src.write_bytes(_PNG_BYTES)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": [{"b64_json": "dGVzdA=="}]}

        with patch("plugins.image_gen.xai.requests.post", return_value=mock_resp) as mock_post, \
             patch("plugins.image_gen.xai.save_b64_image", return_value="/tmp/edited.png"):
            provider = XAIImageGenProvider()
            result = provider.edit(prompt="make it blue", image=str(src))

        payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert isinstance(payload["image"], dict)
        assert payload["image"]["type"] == "image_url"
        assert payload["image"]["url"].startswith("data:image/png;base64,")
        assert "image_url" not in payload, "local files must be inlined as a data URI in image.url"
        assert result["success"] is True

    def test_edit_data_uri_passthrough(self):
        """A data URI is passed verbatim as the image object's ``url``."""
        from plugins.image_gen.xai import XAIImageGenProvider

        data_uri = "data:image/png;base64,dGVzdA=="
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": [{"b64_json": "dGVzdA=="}]}

        with patch("plugins.image_gen.xai.requests.post", return_value=mock_resp) as mock_post, \
             patch("plugins.image_gen.xai.save_b64_image", return_value="/tmp/edited.png"):
            provider = XAIImageGenProvider()
            provider.edit(prompt="make it blue", image=data_uri)

        payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert payload["image"] == {"url": data_uri, "type": "image_url"}

    def test_edit_local_path_missing_is_invalid_input(self, tmp_path):
        from plugins.image_gen.xai import XAIImageGenProvider

        provider = XAIImageGenProvider()
        result = provider.edit(prompt="x", image=str(tmp_path / "nope.png"))
        assert result["success"] is False
        assert result["error_type"] == "invalid_input"

    def test_edit_local_path_non_image_is_invalid_input(self, tmp_path):
        from plugins.image_gen.xai import XAIImageGenProvider

        bad = tmp_path / "fake.png"
        bad.write_bytes(b"definitely not an image")
        provider = XAIImageGenProvider()
        result = provider.edit(prompt="x", image=str(bad))
        assert result["success"] is False
        assert result["error_type"] == "invalid_input"

    def test_edit_url_response_is_cached(self):
        from plugins.image_gen.xai import XAIImageGenProvider

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": [{"url": "https://imgen.x.ai/xai-tmp-edit.jpeg"}],
        }

        with patch("plugins.image_gen.xai.requests.post", return_value=mock_resp), \
             patch(
                 "plugins.image_gen.xai.save_url_image",
                 return_value=Path("/tmp/xai_edit_20260607_000000_deadbeef.jpg"),
             ) as mock_save_url:
            provider = XAIImageGenProvider()
            result = provider.edit(prompt="x", image="https://x/a.png")

        assert result["success"] is True
        assert result["image"].startswith("/")
        assert "imgen.x.ai" not in result["image"]
        mock_save_url.assert_called_once()

    def test_edit_api_error(self):
        import requests as req_lib
        from plugins.image_gen.xai import XAIImageGenProvider

        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.text = "Unprocessable"
        mock_resp.json.return_value = {"error": {"message": "bad image"}}
        mock_resp.raise_for_status.side_effect = req_lib.HTTPError(response=mock_resp)

        with patch("plugins.image_gen.xai.requests.post", return_value=mock_resp):
            provider = XAIImageGenProvider()
            result = provider.edit(prompt="x", image="https://x/a.png")

        assert result["success"] is False
        assert result["error_type"] == "api_error"
        assert "edit" in result["error"].lower()

    def test_edit_timeout(self):
        import requests as req_lib
        from plugins.image_gen.xai import XAIImageGenProvider

        with patch("plugins.image_gen.xai.requests.post", side_effect=req_lib.Timeout()):
            provider = XAIImageGenProvider()
            result = provider.edit(prompt="x", image="https://x/a.png")

        assert result["success"] is False
        assert result["error_type"] == "timeout"

    def test_edit_requests_base64_response(self):
        from plugins.image_gen.xai import XAIImageGenProvider

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": [{"b64_json": "dGVzdA=="}]}

        with patch("plugins.image_gen.xai.requests.post", return_value=mock_resp) as mock_post, \
             patch("plugins.image_gen.xai.save_b64_image", return_value="/tmp/edited.png"):
            provider = XAIImageGenProvider()
            provider.edit(prompt="x", image="https://x/a.png")

        payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
        assert payload["response_format"] == "b64_json"


# ---------------------------------------------------------------------------
# Registration test
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register(self):
        from plugins.image_gen.xai import XAIImageGenProvider, register

        mock_ctx = MagicMock()
        register(mock_ctx)
        mock_ctx.register_image_gen_provider.assert_called_once()
        provider = mock_ctx.register_image_gen_provider.call_args[0][0]
        assert isinstance(provider, XAIImageGenProvider)
        assert provider.name == "xai"
