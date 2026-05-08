"""Tests for the Sachima custom IM platform adapter."""

import base64
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock

import pytest

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import MessageType
from gateway.platforms.sachima import (
    SachimaAdapter,
    SachimaPayloadError,
    check_sachima_requirements,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\n fake png data"


def _base_payload(**overrides):
    payload = {
        "message_id": "msg-1",
        "text": "狗哥来了",
        "chat_id": "chat-1",
        "user_id": "user-1",
    }
    payload.update(overrides)
    return payload


def test_check_sachima_requirements_has_no_optional_dependencies():
    """Sachima's first slice should run with stdlib plus core Hermes deps."""
    assert check_sachima_requirements() is True


def test_build_event_from_payload_maps_text_message_to_hermes_event():
    """Webhook payloads should normalize into MessageEvent + SessionSource."""
    adapter = SachimaAdapter(PlatformConfig(enabled=True))

    event = adapter.build_event_from_payload(
        {
            "message_id": "msg-1",
            "text": "狗哥来了",
            "chat_id": "chat-1",
            "chat_name": "Sachima Lab",
            "chat_type": "group",
            "user_id": "user-1",
            "user_name": "狗哥",
            "thread_id": "thread-1",
        }
    )

    assert event.text == "狗哥来了"
    assert event.message_type is MessageType.TEXT
    assert event.message_id == "msg-1"
    assert event.raw_message["message_id"] == "msg-1"
    assert event.source.platform is Platform.SACHIMA
    assert event.source.chat_id == "chat-1"
    assert event.source.chat_name == "Sachima Lab"
    assert event.source.chat_type == "group"
    assert event.source.user_id == "user-1"
    assert event.source.user_name == "狗哥"
    assert event.source.thread_id == "thread-1"


def test_build_event_from_payload_supports_nested_chat_user_and_message_fields():
    """Realistic Sachima payloads may nest chat, user, and message identity."""
    adapter = SachimaAdapter(PlatformConfig(enabled=True))

    event = adapter.build_event_from_payload(
        {
            "text": "nested hello",
            "chat": {"id": "group-1", "name": "Group One", "type": "group"},
            "user": {"id": "user-2", "name": "Alice"},
            "message": {"id": "msg-2"},
            "thread_id": "thread-9",
        }
    )

    assert event.text == "nested hello"
    assert event.message_id == "msg-2"
    assert event.source.chat_id == "group-1"
    assert event.source.chat_name == "Group One"
    assert event.source.chat_type == "group"
    assert event.source.user_id == "user-2"
    assert event.source.user_name == "Alice"
    assert event.source.thread_id == "thread-9"


@pytest.mark.parametrize("missing_field", ["text", "chat_id", "user_id"])
def test_build_event_from_payload_rejects_missing_required_fields(missing_field):
    """Bad webhook payloads should fail before entering Hermes session code."""
    adapter = SachimaAdapter(PlatformConfig(enabled=True))
    payload = {
        "message_id": "msg-1",
        "text": "hi",
        "chat_id": "chat-1",
        "user_id": "user-1",
    }
    payload.pop(missing_field)

    with pytest.raises(SachimaPayloadError, match=missing_field):
        adapter.build_event_from_payload(payload)


def test_build_event_from_payload_maps_base64_png_attachment_to_photo_event(monkeypatch):
    """Base64 image attachments should become cached PHOTO media on MessageEvent."""
    cached_calls = []

    def fake_cache(data, ext):
        cached_calls.append((data, ext))
        return "/tmp/sachima-photo.png"

    monkeypatch.setattr("gateway.platforms.sachima.cache_image_from_bytes", fake_cache)
    adapter = SachimaAdapter(PlatformConfig(enabled=True))

    event = adapter.build_event_from_payload(
        _base_payload(
            attachments=[
                {
                    "id": "att-1",
                    "type": "image",
                    "mime_type": "image/png",
                    "filename": "photo.png",
                    "base64": base64.b64encode(PNG_BYTES).decode("ascii"),
                }
            ]
        )
    )

    assert event.text == "狗哥来了"
    assert event.message_type is MessageType.PHOTO
    assert event.media_urls == ["/tmp/sachima-photo.png"]
    assert event.media_types == ["image/png"]
    assert cached_calls == [(PNG_BYTES, ".png")]


def test_build_event_from_payload_uses_placeholder_text_for_image_without_text(monkeypatch):
    """Image-only payloads should still enter Hermes with non-empty text."""
    monkeypatch.setattr("gateway.platforms.sachima.cache_image_from_bytes", lambda data, ext: "/tmp/image.png")
    adapter = SachimaAdapter(PlatformConfig(enabled=True))

    event = adapter.build_event_from_payload(
        _base_payload(
            text="",
            attachments=[{"type": "image", "mime_type": "image/png", "base64": base64.b64encode(PNG_BYTES).decode("ascii")}],
        )
    )

    assert event.text == "[Image]"
    assert event.message_type is MessageType.PHOTO


def test_build_event_from_payload_rejects_invalid_base64_image():
    """Malformed base64 image data should fail with a clear payload error."""
    adapter = SachimaAdapter(PlatformConfig(enabled=True))

    with pytest.raises(SachimaPayloadError, match="Invalid base64"):
        adapter.build_event_from_payload(
            _base_payload(attachments=[{"type": "image", "mime_type": "image/png", "base64": "not valid base64"}])
        )


def test_build_event_from_payload_rejects_oversized_base64_before_decoding(monkeypatch):
    """Oversized base64 should be rejected from encoded length before allocating decoded bytes."""
    adapter = SachimaAdapter(PlatformConfig(enabled=True, extra={"max_inbound_media_bytes": 4}))

    def fail_decode(*args, **kwargs):
        raise AssertionError("oversized payload should not be decoded")

    monkeypatch.setattr("gateway.platforms.sachima.base64.b64decode", fail_decode)

    with pytest.raises(SachimaPayloadError, match="exceeds maximum"):
        adapter.build_event_from_payload(
            _base_payload(
                attachments=[{"type": "image", "mime_type": "image/png", "base64": base64.b64encode(PNG_BYTES).decode("ascii")}]
            )
        )


def test_build_event_from_payload_rejects_excessive_base64_padding_before_decoding(monkeypatch):
    """Excess padding must not shrink the pre-decode size estimate."""
    adapter = SachimaAdapter(PlatformConfig(enabled=True, extra={"max_inbound_media_bytes": 4}))

    def fail_decode(*args, **kwargs):
        raise AssertionError("invalid/excessively padded payload should not be decoded")

    monkeypatch.setattr("gateway.platforms.sachima.base64.b64decode", fail_decode)

    with pytest.raises(SachimaPayloadError, match="Invalid base64"):
        adapter.build_event_from_payload(
            _base_payload(attachments=[{"type": "image", "mime_type": "image/png", "base64": "A" * 8 + "=" * 24}])
        )



def test_build_event_from_payload_accepts_exact_decoded_size_limit(monkeypatch):
    """Base64 padding should not make an exactly-at-limit image look oversized."""
    monkeypatch.setattr("gateway.platforms.sachima.cache_image_from_bytes", lambda data, ext: "/tmp/exact.png")
    adapter = SachimaAdapter(PlatformConfig(enabled=True, extra={"max_inbound_media_bytes": len(PNG_BYTES)}))

    event = adapter.build_event_from_payload(
        _base_payload(attachments=[{"type": "image", "mime_type": "image/png", "base64": base64.b64encode(PNG_BYTES).decode("ascii")}])
    )

    assert event.media_urls == ["/tmp/exact.png"]
    assert event.media_types == ["image/png"]


def test_build_event_from_payload_rejects_unsupported_image_mime():
    """Sachima phase 1 should accept images only, not arbitrary binary attachments."""
    adapter = SachimaAdapter(PlatformConfig(enabled=True))

    with pytest.raises(SachimaPayloadError, match="Unsupported Sachima image MIME type"):
        adapter.build_event_from_payload(
            _base_payload(
                attachments=[{"type": "image", "mime_type": "application/pdf", "base64": base64.b64encode(PNG_BYTES).decode("ascii")}]
            )
        )


def test_build_event_from_payload_rejects_declared_image_with_non_image_bytes():
    """Declared image payloads should still pass through image magic-byte validation."""
    adapter = SachimaAdapter(PlatformConfig(enabled=True))

    with pytest.raises(SachimaPayloadError, match="non-image"):
        adapter.build_event_from_payload(
            _base_payload(
                attachments=[
                    {
                        "type": "image",
                        "mime_type": "image/png",
                        "base64": base64.b64encode(b"this is not an image").decode("ascii"),
                    }
                ]
            )
        )


def test_build_event_from_payload_ignores_path_traversal_image_filename(monkeypatch):
    """Attachment filenames may suggest extensions but must never control cache paths."""
    cached_exts = []

    def fake_cache(data, ext):
        cached_exts.append(ext)
        return "/safe/cache/img.png"

    monkeypatch.setattr("gateway.platforms.sachima.cache_image_from_bytes", fake_cache)
    adapter = SachimaAdapter(PlatformConfig(enabled=True))

    event = adapter.build_event_from_payload(
        _base_payload(
            attachments=[
                {
                    "type": "image",
                    "mime_type": "image/png",
                    "filename": "../../evil.png",
                    "base64": base64.b64encode(PNG_BYTES).decode("ascii"),
                }
            ]
        )
    )

    assert event.media_urls == ["/safe/cache/img.png"]
    assert cached_exts == [".png"]


@pytest.mark.asyncio
async def test_handle_webhook_payload_rejects_private_image_url():
    """URL image attachments should go through SSRF-safe downloading."""
    adapter = SachimaAdapter(PlatformConfig(enabled=True))

    with pytest.raises(SachimaPayloadError, match="unsafe URL|SSRF|Blocked"):
        await adapter.handle_webhook_payload(
            _base_payload(attachments=[{"type": "image", "mime_type": "image/png", "url": "http://127.0.0.1/image.png"}])
        )


@pytest.mark.asyncio
async def test_handle_webhook_payload_downloads_safe_image_url(monkeypatch):
    """Safe image URLs should be cached before dispatching the Hermes message."""
    async def fake_cache_url(url, ext, *, max_bytes=None):
        assert url == "https://example.com/image.png"
        assert ext == ".png"
        assert max_bytes == 1234
        return "/tmp/url-image.png"

    monkeypatch.setattr("gateway.platforms.sachima.cache_image_from_url", fake_cache_url)
    adapter = SachimaAdapter(PlatformConfig(enabled=True, extra={"max_inbound_media_bytes": 1234}))
    adapter.handle_message = AsyncMock()

    event = await adapter.handle_webhook_payload(
        _base_payload(attachments=[{"type": "image", "mime_type": "image/png", "url": "https://example.com/image.png"}])
    )

    assert event.message_type is MessageType.PHOTO
    assert event.media_urls == ["/tmp/url-image.png"]
    assert event.media_types == ["image/png"]
    adapter.handle_message.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_handle_webhook_payload_prefers_base64_when_attachment_also_has_url(monkeypatch):
    """Ambiguous base64+URL images should not be double-counted or fetched."""
    def fake_cache_bytes(data, ext):
        assert data == PNG_BYTES
        assert ext == ".png"
        return "/tmp/base64-image.png"

    async def fail_cache_url(*args, **kwargs):
        raise AssertionError("URL fetch should be skipped when base64 data is present")

    monkeypatch.setattr("gateway.platforms.sachima.cache_image_from_bytes", fake_cache_bytes)
    monkeypatch.setattr("gateway.platforms.sachima.cache_image_from_url", fail_cache_url)
    adapter = SachimaAdapter(PlatformConfig(enabled=True))
    adapter.handle_message = AsyncMock()

    event = await adapter.handle_webhook_payload(
        _base_payload(
            attachments=[
                {
                    "type": "image",
                    "mime_type": "image/png",
                    "base64": base64.b64encode(PNG_BYTES).decode("ascii"),
                    "url": "https://example.com/should-not-fetch.png",
                }
            ]
        )
    )

    assert event.media_urls == ["/tmp/base64-image.png"]
    assert event.media_types == ["image/png"]
    adapter.handle_message.assert_awaited_once_with(event)


def test_max_message_length_defaults_to_safe_im_sized_limit():
    """Sachima should chunk outbound text even when no platform limit is configured."""
    adapter = SachimaAdapter(PlatformConfig(enabled=True))

    assert adapter.max_message_length == 4000


def test_max_message_length_can_be_configured_from_platform_extra():
    """Deployments should tune Sachima chunk size through config.yaml extra settings."""
    adapter = SachimaAdapter(PlatformConfig(enabled=True, extra={"max_message_length": 8000}))

    assert adapter.max_message_length == 8000


@pytest.mark.parametrize("value", [0, -1, "not-a-number", None])
def test_invalid_max_message_length_falls_back_to_default(value):
    """Bad config should fail safe instead of disabling message chunking."""
    adapter = SachimaAdapter(PlatformConfig(enabled=True, extra={"max_message_length": value}))

    assert adapter.max_message_length == 4000


@pytest.mark.asyncio
async def test_send_without_send_url_records_local_outbound_message():
    """Local fallback should make early channel testing possible without an IM API."""
    adapter = SachimaAdapter(PlatformConfig(enabled=True))

    result = await adapter.send(
        "chat-1",
        "hello from Hermes",
        reply_to="msg-1",
        metadata={"thread_id": "thread-1"},
    )

    assert result.success is True
    assert result.message_id == "sachima-local-1"
    assert adapter.sent_messages == [
        {
            "chat_id": "chat-1",
            "content": "hello from Hermes",
            "reply_to": "msg-1",
            "metadata": {"thread_id": "thread-1"},
        }
    ]


@pytest.mark.asyncio
async def test_send_without_send_url_chunks_long_outbound_message():
    """Local fallback should record one outbound JSON message per configured chunk."""
    adapter = SachimaAdapter(PlatformConfig(enabled=True, extra={"max_message_length": 80}))
    long_content = "0123456789 " * 20

    result = await adapter.send("chat-1", long_content, reply_to="msg-1", metadata={"thread_id": "thread-1"})

    assert result.success is True
    assert result.message_id == f"sachima-local-{len(adapter.sent_messages)}"
    assert len(adapter.sent_messages) > 1
    assert all(message["chat_id"] == "chat-1" for message in adapter.sent_messages)
    assert all(message["reply_to"] == "msg-1" for message in adapter.sent_messages)
    assert all(message["metadata"] == {"thread_id": "thread-1"} for message in adapter.sent_messages)
    assert all(len(message["content"]) <= adapter.max_message_length for message in adapter.sent_messages)


@pytest.mark.asyncio
async def test_connect_starts_webhook_listener_and_dispatches_json_payload(unused_tcp_port):
    """Adapter-owned webhook listener should accept JSON and dispatch payloads."""
    aiohttp = pytest.importorskip("aiohttp")
    adapter = SachimaAdapter(
        PlatformConfig(
            enabled=True,
            extra={
                "webhook_host": "127.0.0.1",
                "webhook_port": unused_tcp_port,
                "webhook_path": "/webhook/sachima",
            },
        )
    )
    dispatched_payloads = []

    async def fake_handle_webhook_payload(payload):
        dispatched_payloads.append(payload)
        return adapter.build_event_from_payload(payload)

    adapter.handle_webhook_payload = fake_handle_webhook_payload

    assert await adapter.connect() is True
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"http://127.0.0.1:{unused_tcp_port}/webhook/sachima",
                json={
                    "message_id": "msg-1",
                    "text": "hello webhook",
                    "chat_id": "chat-1",
                    "user_id": "user-1",
                },
            ) as response:
                body = await response.json()

        assert response.status == 200
        assert body == {"ok": True, "message_id": "msg-1"}
        assert dispatched_payloads == [
            {
                "message_id": "msg-1",
                "text": "hello webhook",
                "chat_id": "chat-1",
                "user_id": "user-1",
            }
        ]
    finally:
        await adapter.disconnect()

    assert adapter.is_connected is False


@pytest.mark.asyncio
async def test_webhook_listener_rejects_malformed_json(unused_tcp_port):
    """Malformed webhook bodies should fail before reaching Hermes session code."""
    aiohttp = pytest.importorskip("aiohttp")
    adapter = SachimaAdapter(
        PlatformConfig(
            enabled=True,
            extra={
                "webhook_host": "127.0.0.1",
                "webhook_port": unused_tcp_port,
                "webhook_path": "/webhook/sachima",
            },
        )
    )
    adapter.handle_webhook_payload = AsyncMock()

    assert await adapter.connect() is True
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"http://127.0.0.1:{unused_tcp_port}/webhook/sachima",
                data="not-json",
            ) as response:
                body = await response.json()

        assert response.status == 400
        assert body["ok"] is False
        assert "invalid json" in body["error"].lower()
        adapter.handle_webhook_payload.assert_not_called()
    finally:
        await adapter.disconnect()


def _signed_sachima_request(payload: dict, secret: str) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(time.time()))
    signature = hmac.new(
        secret.encode("utf-8"), f"{timestamp}.".encode("utf-8") + body, hashlib.sha256
    ).hexdigest()
    return body, {
        "Content-Type": "application/json",
        "X-Sachima-Timestamp": timestamp,
        "X-Sachima-Signature": signature,
    }


@pytest.mark.asyncio
async def test_webhook_listener_accepts_valid_hmac_signature(unused_tcp_port):
    """When a webhook secret is configured, valid HMAC headers should authenticate."""
    aiohttp = pytest.importorskip("aiohttp")
    secret = "dev-secret"
    payload = {"message_id": "msg-1", "text": "signed", "chat_id": "chat-1", "user_id": "user-1"}
    body, headers = _signed_sachima_request(payload, secret)
    adapter = SachimaAdapter(
        PlatformConfig(
            enabled=True,
            extra={
                "webhook_host": "127.0.0.1",
                "webhook_port": unused_tcp_port,
                "webhook_path": "/webhook/sachima",
                "webhook_secret": secret,
            },
        )
    )
    adapter.handle_webhook_payload = AsyncMock(return_value=adapter.build_event_from_payload(payload))

    assert await adapter.connect() is True
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"http://127.0.0.1:{unused_tcp_port}/webhook/sachima",
                data=body,
                headers=headers,
            ) as response:
                response_body = await response.json()

        assert response.status == 200
        assert response_body == {"ok": True, "message_id": "msg-1"}
        adapter.handle_webhook_payload.assert_awaited_once()
    finally:
        await adapter.disconnect()


@pytest.mark.asyncio
async def test_webhook_listener_rejects_missing_signature_when_secret_configured(unused_tcp_port):
    """Configured webhook secrets should make unsigned requests fail closed."""
    aiohttp = pytest.importorskip("aiohttp")
    adapter = SachimaAdapter(
        PlatformConfig(
            enabled=True,
            extra={
                "webhook_host": "127.0.0.1",
                "webhook_port": unused_tcp_port,
                "webhook_path": "/webhook/sachima",
                "webhook_secret": "dev-secret",
            },
        )
    )
    adapter.handle_webhook_payload = AsyncMock()

    assert await adapter.connect() is True
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"http://127.0.0.1:{unused_tcp_port}/webhook/sachima",
                json={"message_id": "msg-1", "text": "unsigned", "chat_id": "chat-1", "user_id": "user-1"},
            ) as response:
                body = await response.json()

        assert response.status == 401
        assert body["ok"] is False
        assert "signature" in body["error"].lower()
        adapter.handle_webhook_payload.assert_not_called()
    finally:
        await adapter.disconnect()


@pytest.mark.asyncio
async def test_webhook_listener_deduplicates_message_ids(unused_tcp_port):
    """Webhook retries with the same message_id should be acknowledged but not reprocessed."""
    aiohttp = pytest.importorskip("aiohttp")
    payload = {"message_id": "msg-1", "text": "dedupe", "chat_id": "chat-1", "user_id": "user-1"}
    adapter = SachimaAdapter(
        PlatformConfig(
            enabled=True,
            extra={
                "webhook_host": "127.0.0.1",
                "webhook_port": unused_tcp_port,
                "webhook_path": "/webhook/sachima",
            },
        )
    )
    adapter.handle_webhook_payload = AsyncMock(return_value=adapter.build_event_from_payload(payload))

    assert await adapter.connect() is True
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"http://127.0.0.1:{unused_tcp_port}/webhook/sachima", json=payload) as first:
                first_body = await first.json()
            async with session.post(f"http://127.0.0.1:{unused_tcp_port}/webhook/sachima", json=payload) as second:
                second_body = await second.json()

        assert first.status == 200
        assert first_body == {"ok": True, "message_id": "msg-1"}
        assert second.status == 200
        assert second_body == {"ok": True, "duplicate": True, "message_id": "msg-1"}
        adapter.handle_webhook_payload.assert_awaited_once()
    finally:
        await adapter.disconnect()


@pytest.mark.asyncio
async def test_send_with_send_url_posts_json_to_external_endpoint(unused_tcp_port):
    """Configured send_url should receive Hermes outbound messages as JSON."""
    aiohttp = pytest.importorskip("aiohttp")
    web = pytest.importorskip("aiohttp.web")
    received = []

    async def handle_send(request):
        received.append(await request.json())
        return web.json_response({"ok": True}, headers={"X-Sachima-Message-Id": f"sent-{len(received)}"})

    app = web.Application()
    app.router.add_post("/send", handle_send)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()
    try:
        adapter = SachimaAdapter(
            PlatformConfig(enabled=True, extra={"send_url": f"http://127.0.0.1:{unused_tcp_port}/send"})
        )

        result = await adapter.send(
            "chat-1", "hello from Hermes", reply_to="msg-1", metadata={"thread_id": "thread-1"}
        )

        assert result.success is True
        assert result.message_id == "sent-1"
        assert received == [
            {
                "chat_id": "chat-1",
                "content": "hello from Hermes",
                "reply_to": "msg-1",
                "metadata": {"thread_id": "thread-1"},
            }
        ]
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_send_with_send_url_chunks_long_outbound_message(unused_tcp_port):
    """Configured send_url should receive one HTTP POST per outbound chunk."""
    web = pytest.importorskip("aiohttp.web")
    received = []

    async def handle_send(request):
        received.append(await request.json())
        return web.json_response({"ok": True}, headers={"X-Sachima-Message-Id": f"sent-{len(received)}"})

    app = web.Application()
    app.router.add_post("/send", handle_send)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()
    try:
        adapter = SachimaAdapter(
            PlatformConfig(
                enabled=True,
                extra={"send_url": f"http://127.0.0.1:{unused_tcp_port}/send", "max_message_length": 80},
            )
        )
        long_content = "0123456789 " * 20

        result = await adapter.send("chat-1", long_content, reply_to="msg-1", metadata={"thread_id": "thread-1"})

        assert result.success is True
        assert result.message_id == f"sent-{len(received)}"
        assert len(received) > 1
        assert all(message["chat_id"] == "chat-1" for message in received)
        assert all(message["reply_to"] == "msg-1" for message in received)
        assert all(message["metadata"] == {"thread_id": "thread-1"} for message in received)
        assert all(len(message["content"]) <= adapter.max_message_length for message in received)
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_send_with_send_url_treats_429_as_retryable(unused_tcp_port):
    """Rate-limited send API responses should be retryable."""
    web = pytest.importorskip("aiohttp.web")

    async def handle_send(request):
        return web.Response(status=429, text="rate limited")

    app = web.Application()
    app.router.add_post("/send", handle_send)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()
    try:
        adapter = SachimaAdapter(
            PlatformConfig(enabled=True, extra={"send_url": f"http://127.0.0.1:{unused_tcp_port}/send"})
        )

        result = await adapter.send("chat-1", "hello")

        assert result.success is False
        assert result.retryable is True
        assert "HTTP 429" in result.error
    finally:
        await runner.cleanup()
