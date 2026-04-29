"""Sachima custom IM platform adapter.

This adapter is intentionally small: it normalizes a generic Sachima webhook
payload into Hermes gateway events and can send replies either through a
configured HTTP send endpoint or a local in-memory fallback for development.
"""

from __future__ import annotations

import logging
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType, SendResult

try:
    from aiohttp import web
    AIOHTTP_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only in minimal installs
    web = None  # type: ignore[assignment]
    AIOHTTP_AVAILABLE = False


logger = logging.getLogger(__name__)


class SachimaPayloadError(ValueError):
    """Raised when an inbound Sachima webhook payload is malformed."""


def check_sachima_requirements() -> bool:
    """Return whether Sachima's webhook transport dependency is available."""
    return AIOHTTP_AVAILABLE


class SachimaAdapter(BasePlatformAdapter):
    """Native Hermes adapter for the custom Sachima IM channel."""

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform.SACHIMA)
        self.sent_messages: list[dict[str, Any]] = []
        self._local_message_counter = 0
        self._web_app: Optional["web.Application"] = None
        self._web_runner: Optional["web.AppRunner"] = None
        self._web_site: Optional["web.TCPSite"] = None
        self._seen_messages: dict[str, float] = {}

    async def connect(self) -> bool:
        """Start the Sachima webhook listener and mark the adapter connected."""
        if not AIOHTTP_AVAILABLE:
            message = "Sachima startup failed: aiohttp not installed"
            self._set_fatal_error("sachima_missing_dependency", message, retryable=False)
            logger.warning("[%s] %s. Run: pip install aiohttp", self.name, message)
            return False

        host, port, path = self._webhook_settings()
        self._web_app = web.Application()
        self._web_app.router.add_post(path, self._handle_http_webhook)
        self._web_runner = web.AppRunner(self._web_app)
        await self._web_runner.setup()
        self._web_site = web.TCPSite(self._web_runner, host, port)
        try:
            await self._web_site.start()
        except Exception:
            await self._cleanup_webhook_server()
            raise
        self._mark_connected()
        return True

    async def disconnect(self) -> None:
        """Stop the Sachima webhook listener and mark the adapter disconnected."""
        await self._cleanup_webhook_server()
        self._mark_disconnected()

    def _webhook_settings(self) -> tuple[str, int, str]:
        """Return normalized webhook host, port, and path settings."""
        extra = self.config.extra or {}
        host = str(extra.get("webhook_host") or "127.0.0.1").strip() or "127.0.0.1"
        port = int(extra.get("webhook_port") or 8788)
        path = str(extra.get("webhook_path") or "/webhook/sachima").strip()
        if not path.startswith("/"):
            path = f"/{path}"
        return host, port, path

    async def _cleanup_webhook_server(self) -> None:
        """Release aiohttp listener resources if they were created."""
        if self._web_site is not None:
            await self._web_site.stop()
            self._web_site = None
        if self._web_runner is not None:
            await self._web_runner.cleanup()
            self._web_runner = None
        self._web_app = None

    async def _handle_http_webhook(self, request: "web.Request") -> "web.Response":
        """Handle inbound Sachima webhook HTTP requests."""
        raw_body = await request.read()
        signature_error = self._validate_webhook_signature(request, raw_body)
        if signature_error is not None:
            error, status = signature_error
            return web.json_response({"ok": False, "error": error}, status=status)

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON body"}, status=400)

        if not isinstance(payload, dict):
            return web.json_response({"ok": False, "error": "JSON body must be an object"}, status=400)

        duplicate_key = self._dedupe_key_from_payload(payload)
        if duplicate_key and self._is_duplicate(duplicate_key):
            return web.json_response(
                {"ok": True, "duplicate": True, "message_id": self._message_id_from_payload(payload)}
            )

        try:
            event = await self.handle_webhook_payload(payload)
        except SachimaPayloadError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:
            logger.exception("[%s] Sachima webhook dispatch failed", self.name)
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

        if duplicate_key:
            self._remember_message(duplicate_key)
        return web.json_response({"ok": True, "message_id": event.message_id})

    def _validate_webhook_signature(
        self, request: "web.Request", raw_body: bytes
    ) -> Optional[tuple[str, int]]:
        """Validate optional HMAC webhook signature headers."""
        secret = str((self.config.extra or {}).get("webhook_secret") or "").strip()
        if not secret:
            return None

        timestamp = request.headers.get("X-Sachima-Timestamp", "").strip()
        signature = request.headers.get("X-Sachima-Signature", "").strip()
        if not timestamp or not signature:
            return "Missing Sachima signature headers", 401
        try:
            timestamp_int = int(timestamp)
        except ValueError:
            return "Invalid Sachima signature timestamp", 401

        tolerance = int((self.config.extra or {}).get("webhook_signature_tolerance_seconds") or 300)
        if abs(time.time() - timestamp_int) > tolerance:
            return "Sachima signature timestamp is outside the allowed window", 401

        expected = hmac.new(
            secret.encode("utf-8"),
            f"{timestamp}.".encode("utf-8") + raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return "Invalid Sachima signature", 401
        return None

    def _dedupe_key_from_payload(self, payload: Dict[str, Any]) -> Optional[str]:
        """Build a stable dedupe key for webhook retries when message_id exists."""
        message_id = self._message_id_from_payload(payload)
        if not message_id:
            return None
        chat_id = self._payload_value(payload, "chat_id", "chat", "id") or ""
        user_id = self._payload_value(payload, "user_id", "user", "id") or ""
        return f"{chat_id}:{user_id}:{message_id}"

    def _is_duplicate(self, key: str) -> bool:
        now = time.time()
        self._purge_seen_messages(now)
        return key in self._seen_messages

    def _remember_message(self, key: str) -> None:
        now = time.time()
        self._purge_seen_messages(now)
        self._seen_messages[key] = now
        max_size = int((self.config.extra or {}).get("dedupe_max_size") or 10000)
        while len(self._seen_messages) > max_size:
            oldest_key = min(self._seen_messages, key=self._seen_messages.get)
            self._seen_messages.pop(oldest_key, None)

    def _purge_seen_messages(self, now: float) -> None:
        ttl = int((self.config.extra or {}).get("dedupe_ttl_seconds") or 600)
        expired = [key for key, seen_at in self._seen_messages.items() if now - seen_at > ttl]
        for key in expired:
            self._seen_messages.pop(key, None)

    def build_event_from_payload(self, payload: Dict[str, Any]) -> MessageEvent:
        """Normalize a Sachima webhook payload into a Hermes MessageEvent."""
        text = self._payload_value(payload, "text", "message", "text")
        chat_id = self._payload_value(payload, "chat_id", "chat", "id")
        user_id = self._payload_value(payload, "user_id", "user", "id")
        for field, value in (("text", text), ("chat_id", chat_id), ("user_id", user_id)):
            if value in (None, ""):
                raise SachimaPayloadError(f"Missing required Sachima payload field: {field}")

        text = str(text)
        source = self.build_source(
            chat_id=str(chat_id),
            chat_name=self._payload_value(payload, "chat_name", "chat", "name"),
            chat_type=str(self._payload_value(payload, "chat_type", "chat", "type") or "dm"),
            user_id=str(user_id),
            user_name=self._payload_value(payload, "user_name", "user", "name"),
            thread_id=payload.get("thread_id"),
            chat_topic=payload.get("chat_topic"),
        )

        return MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            source=source,
            raw_message=payload,
            message_id=self._message_id_from_payload(payload),
            reply_to_message_id=(
                str(payload["reply_to_message_id"])
                if payload.get("reply_to_message_id")
                else None
            ),
            reply_to_text=payload.get("reply_to_text"),
        )

    @staticmethod
    def _payload_value(payload: Dict[str, Any], flat_key: str, nested_obj: str, nested_key: str) -> Any:
        """Read a flat value or a nested object value from a Sachima payload."""
        value = payload.get(flat_key)
        if value not in (None, ""):
            return value
        nested = payload.get(nested_obj)
        if isinstance(nested, dict):
            return nested.get(nested_key)
        return None

    def _message_id_from_payload(self, payload: Dict[str, Any]) -> Optional[str]:
        """Read message_id from supported flat or nested payload shapes."""
        value = payload.get("message_id") or payload.get("id")
        if value in (None, ""):
            message = payload.get("message")
            if isinstance(message, dict):
                value = message.get("id")
        return str(value) if value not in (None, "") else None

    async def handle_webhook_payload(self, payload: Dict[str, Any]) -> MessageEvent:
        """Build and dispatch a MessageEvent for embedding/webhook callers."""
        event = self.build_event_from_payload(payload)
        await self.handle_message(event)
        return event

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a Sachima message or record it locally when no send URL exists."""
        outbound = {
            "chat_id": str(chat_id),
            "content": content,
            "reply_to": reply_to,
            "metadata": metadata or {},
        }
        send_url = str(self.config.extra.get("send_url") or "").strip()
        if not send_url:
            self._local_message_counter += 1
            self.sent_messages.append(outbound)
            return SendResult(
                success=True,
                message_id=f"sachima-local-{self._local_message_counter}",
                raw_response=outbound,
            )

        try:
            import aiohttp

            headers = {}
            api_key = str(self.config.api_key or self.config.extra.get("api_key") or "").strip()
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            async with aiohttp.ClientSession() as session:
                async with session.post(send_url, json=outbound, headers=headers) as response:
                    raw_response = await response.text()
                    if 200 <= response.status < 300:
                        message_id = response.headers.get("X-Sachima-Message-Id")
                        return SendResult(
                            success=True,
                            message_id=message_id,
                            raw_response=raw_response,
                        )
                    return SendResult(
                        success=False,
                        error=f"Sachima send API returned HTTP {response.status}: {raw_response}",
                        raw_response=raw_response,
                        retryable=response.status == 429 or response.status >= 500,
                    )
        except Exception as exc:
            return SendResult(success=False, error=str(exc), retryable=True)

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Return minimal chat metadata for the Sachima channel."""
        return {"id": str(chat_id), "name": str(chat_id), "type": "dm"}
