"""Tests for the platform-generic interactive-card send/patch/fallback seam.

Three optional adapter entry points, declared once on ``BasePlatformAdapter``
so callers can drive any platform through the same names:

* ``send_interactive_card``  — post a card payload as its own message;
* ``patch_interactive_card`` — revise a card already on screen, in place;
* ``send_plain_text_once``   — deliver one already-bounded plain-text body as
  exactly one message, the fallback when a card cannot be used.

The base class supplies defaults; Feishu overrides all three.  Nothing here
reaches into the Gateway run loop — an adapter method is the whole seam.
"""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure the repo root is importable
# ---------------------------------------------------------------------------
_repo = str(Path(__file__).resolve().parents[2])
if _repo not in sys.path:
    sys.path.insert(0, _repo)

# The Feishu SDK is imported lazily at connect time, so the adapter module
# imports (and every test below runs) with or without lark-oapi installed.
from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import BasePlatformAdapter, SendResult
from plugins.platforms.feishu.adapter import FeishuAdapter


CARD = {
    "config": {"wide_screen_mode": True},
    "header": {"title": {"tag": "plain_text", "content": "Build"}, "template": "blue"},
    "elements": [{"tag": "markdown", "content": "**running**"}],
}


# ===========================================================================
# Base class — the generic contract every adapter inherits
# ===========================================================================

class _StubAdapter(BasePlatformAdapter):
    """Smallest concrete adapter: records what ``send`` was asked to do."""

    def __init__(self):
        super().__init__(PlatformConfig(), Platform.LOCAL)
        self.send_calls = []

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        return True

    async def disconnect(self) -> None:
        return None

    async def send(self, chat_id, content, reply_to=None, metadata=None) -> SendResult:
        self.send_calls.append((chat_id, content, reply_to, metadata))
        return SendResult(success=True, message_id="m_send")

    async def get_chat_info(self, chat_id):
        return {}


class TestBaseCardSeamDefaults:
    """A platform that knows nothing about cards must still answer."""

    @pytest.mark.asyncio
    async def test_send_interactive_card_defaults_to_not_supported(self):
        result = await _StubAdapter().send_interactive_card("c1", CARD)
        assert result.success is False
        assert result.error == "Not supported"

    @pytest.mark.asyncio
    async def test_patch_interactive_card_defaults_to_not_supported(self):
        result = await _StubAdapter().patch_interactive_card("c1", "m1", CARD)
        assert result.success is False
        assert result.error == "Not supported"

    @pytest.mark.asyncio
    async def test_send_plain_text_once_defaults_to_the_adapters_own_send(self):
        adapter = _StubAdapter()

        result = await adapter.send_plain_text_once(
            "c1", "one body", reply_to="m0", metadata={"k": "v"},
        )

        assert result.success is True
        assert result.message_id == "m_send"
        assert adapter.send_calls == [("c1", "one body", "m0", {"k": "v"})]


# ===========================================================================
# Feishu — send_interactive_card
# ===========================================================================

def _make_adapter() -> FeishuAdapter:
    adapter = FeishuAdapter(PlatformConfig(enabled=True))
    adapter._client = MagicMock()
    return adapter


class TestFeishuSendInteractiveCard:

    @pytest.mark.asyncio
    async def test_sends_one_interactive_frame_with_the_card_payload(self):
        adapter = _make_adapter()
        response = SimpleNamespace(
            success=lambda: True, data=SimpleNamespace(message_id="om_card"),
        )

        with patch.object(
            adapter, "_feishu_send_with_retry", new_callable=AsyncMock,
            return_value=response,
        ) as mock_send:
            result = await adapter.send_interactive_card(
                "oc_chat", CARD, reply_to="om_parent", metadata={"thread_id": "t1"},
            )

        assert result.success is True
        assert result.message_id == "om_card"
        mock_send.assert_called_once()
        kwargs = mock_send.call_args[1]
        assert kwargs["msg_type"] == "interactive"
        assert kwargs["chat_id"] == "oc_chat"
        assert kwargs["reply_to"] == "om_parent"
        assert kwargs["metadata"] == {"thread_id": "t1"}
        assert json.loads(kwargs["payload"]) == CARD

    @pytest.mark.asyncio
    async def test_reports_not_connected_without_sending(self):
        adapter = _make_adapter()
        adapter._client = None

        with patch.object(
            adapter, "_feishu_send_with_retry", new_callable=AsyncMock,
        ) as mock_send:
            result = await adapter.send_interactive_card("oc_chat", CARD)

        assert result.success is False
        assert result.error == "Not connected"
        mock_send.assert_not_called()


# ===========================================================================
# Feishu — patch_interactive_card
# ===========================================================================

class _PatchAPI:
    """Feishu message API double recording which endpoint was called."""

    def __init__(self, patch_responses):
        self._patch_responses = list(patch_responses)
        self.patch_calls = []
        self.update_calls = []

    def patch(self, request):
        self.patch_calls.append(request)
        outcome = self._patch_responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def update(self, request):
        self.update_calls.append(request)
        return SimpleNamespace(success=lambda: True)


def _install_message_api(adapter, api):
    adapter._client = SimpleNamespace(
        im=SimpleNamespace(v1=SimpleNamespace(message=api))
    )


def _ok(message_id="om_card"):
    return SimpleNamespace(success=lambda: True, data=SimpleNamespace(message_id=message_id))


def _transient():
    return SimpleNamespace(success=lambda: False, code=230020, msg="single messages too frequently")


def _permanent():
    return SimpleNamespace(success=lambda: False, code=230001, msg="message not found")


class TestFeishuPatchInteractiveCard:

    @pytest.mark.asyncio
    async def test_revises_the_card_through_message_patch_not_message_update(self):
        """Feishu rejects interactive-card revisions sent through message.update."""
        adapter = _make_adapter()
        api = _PatchAPI([_ok()])
        _install_message_api(adapter, api)

        result = await adapter.patch_interactive_card("oc_chat", "om_card", CARD)

        assert result.success is True
        assert result.message_id == "om_card"
        assert api.update_calls == []
        assert len(api.patch_calls) == 1
        assert json.loads(api.patch_calls[0].request_body.content) == CARD

    @pytest.mark.asyncio
    async def test_retries_a_rate_limited_response_and_then_succeeds(self):
        adapter = _make_adapter()
        api = _PatchAPI([_transient(), _ok()])
        _install_message_api(adapter, api)

        with patch("plugins.platforms.feishu.adapter.asyncio.sleep", new_callable=AsyncMock):
            result = await adapter.patch_interactive_card("oc_chat", "om_card", CARD)

        assert result.success is True
        assert len(api.patch_calls) == 2

    @pytest.mark.asyncio
    async def test_marks_the_result_retryable_when_transient_attempts_are_exhausted(self):
        adapter = _make_adapter()
        api = _PatchAPI([_transient(), _transient(), _transient()])
        _install_message_api(adapter, api)

        with patch("plugins.platforms.feishu.adapter.asyncio.sleep", new_callable=AsyncMock):
            result = await adapter.patch_interactive_card("oc_chat", "om_card", CARD)

        assert result.success is False
        assert result.retryable is True
        assert len(api.patch_calls) == 3

    @pytest.mark.asyncio
    async def test_gives_up_immediately_on_a_permanent_failure(self):
        adapter = _make_adapter()
        api = _PatchAPI([_permanent()])
        _install_message_api(adapter, api)

        result = await adapter.patch_interactive_card("oc_chat", "om_card", CARD)

        assert result.success is False
        assert result.retryable is False
        assert len(api.patch_calls) == 1

    @pytest.mark.asyncio
    async def test_retries_a_transient_exception_and_then_succeeds(self):
        adapter = _make_adapter()
        api = _PatchAPI([TimeoutError("read timed out"), _ok()])
        _install_message_api(adapter, api)

        with patch("plugins.platforms.feishu.adapter.asyncio.sleep", new_callable=AsyncMock):
            result = await adapter.patch_interactive_card("oc_chat", "om_card", CARD)

        assert result.success is True
        assert len(api.patch_calls) == 2

    @pytest.mark.asyncio
    async def test_does_not_retry_a_permanent_exception(self):
        adapter = _make_adapter()
        api = _PatchAPI([ValueError("card json is malformed")])
        _install_message_api(adapter, api)

        result = await adapter.patch_interactive_card("oc_chat", "om_card", CARD)

        assert result.success is False
        assert result.retryable is False
        assert len(api.patch_calls) == 1


# ===========================================================================
# Feishu — send_plain_text_once
# ===========================================================================

class TestFeishuSendPlainTextOnce:

    @pytest.mark.asyncio
    async def test_sends_one_text_frame_verbatim_without_chunking_or_markdown(self):
        """One terminal, one message: no split, no ``post`` promotion."""
        adapter = _make_adapter()
        body = "## Heading\n\n**bold** and a very long tail " + ("x" * 6000)
        response = SimpleNamespace(
            success=lambda: True, data=SimpleNamespace(message_id="om_text"),
        )

        with patch.object(
            adapter, "_feishu_send_with_retry", new_callable=AsyncMock,
            return_value=response,
        ) as mock_send:
            result = await adapter.send_plain_text_once(
                "oc_chat", body, reply_to="om_parent", metadata={"thread_id": "t1"},
            )

        assert result.success is True
        assert result.message_id == "om_text"
        mock_send.assert_called_once()
        kwargs = mock_send.call_args[1]
        assert kwargs["msg_type"] == "text"
        assert json.loads(kwargs["payload"]) == {"text": body}

    @pytest.mark.asyncio
    async def test_reports_not_connected_without_sending(self):
        adapter = _make_adapter()
        adapter._client = None

        with patch.object(
            adapter, "_feishu_send_with_retry", new_callable=AsyncMock,
        ) as mock_send:
            result = await adapter.send_plain_text_once("oc_chat", "body")

        assert result.success is False
        assert result.error == "Not connected"
        mock_send.assert_not_called()


# ===========================================================================
# The seam stays platform-generic
# ===========================================================================

def test_the_seam_is_declared_on_the_base_adapter_not_only_on_feishu():
    for name in (
        "send_interactive_card",
        "patch_interactive_card",
        "send_plain_text_once",
    ):
        assert hasattr(BasePlatformAdapter, name), (
            f"{name} must be declared on BasePlatformAdapter so every platform "
            "answers the same call"
        )
        assert asyncio.iscoroutinefunction(getattr(BasePlatformAdapter, name))
