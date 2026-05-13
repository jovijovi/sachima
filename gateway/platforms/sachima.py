"""Sachima custom IM platform adapter.

This adapter is intentionally small: it normalizes a generic Sachima webhook
payload into Hermes gateway events and can send replies either through a
configured HTTP send endpoint or a local in-memory fallback for development.
"""

from __future__ import annotations

import base64
import binascii
import logging
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
    cache_image_from_bytes,
    cache_image_from_url,
)

try:
    from aiohttp import web
    AIOHTTP_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only in minimal installs
    web = None  # type: ignore[assignment]
    AIOHTTP_AVAILABLE = False


logger = logging.getLogger(__name__)

DEFAULT_MAX_MESSAGE_LENGTH = 4000
MIN_MAX_MESSAGE_LENGTH = 50
DEFAULT_MAX_INBOUND_MEDIA_BYTES = 10 * 1024 * 1024
IMAGE_PLACEHOLDER_TEXT = "[Image]"
SACHIMA_SCHEMA_VERSION = "sachima.v1"
SACHIMA_ASSISTANT_USER_ID = "sachima-hermes"
MAX_ENVELOPE_ID_LENGTH = 256
SUPPORTED_IMAGE_MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
}


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

    @property
    def max_message_length(self) -> int:
        """Return configured outbound text chunk size, falling back safely."""
        raw_value = (self.config.extra or {}).get("max_message_length", DEFAULT_MAX_MESSAGE_LENGTH)
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return DEFAULT_MAX_MESSAGE_LENGTH
        if value < MIN_MAX_MESSAGE_LENGTH:
            return DEFAULT_MAX_MESSAGE_LENGTH
        return value

    @property
    def max_inbound_media_bytes(self) -> int:
        """Return maximum accepted decoded inbound media size in bytes."""
        raw_value = (self.config.extra or {}).get("max_inbound_media_bytes", DEFAULT_MAX_INBOUND_MEDIA_BYTES)
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return DEFAULT_MAX_INBOUND_MEDIA_BYTES
        if value <= 0:
            return DEFAULT_MAX_INBOUND_MEDIA_BYTES
        return value

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

        try:
            payload = self._normalize_ingress_payload(payload)
        except SachimaPayloadError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)

        if not self._is_allowed_ingress_user(payload):
            return web.json_response({"ok": False, "error": "forbidden"}, status=403)

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

    def _normalize_ingress_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize and validate Sachima Envelope v1 ingress payloads.

        Pre-v1 local/legacy payloads remain accepted for existing loopback tests.
        Once ``schema_version`` is present, v1 validation is fail-closed.
        """
        if payload.get("schema_version") in (None, ""):
            return payload

        normalized = dict(payload)
        if normalized.get("schema_version") != SACHIMA_SCHEMA_VERSION:
            raise SachimaPayloadError("Invalid Sachima v1 schema_version")
        if normalized.get("role") != "user":
            raise SachimaPayloadError("Invalid Sachima v1 ingress role")

        for field in ("message_id", "chat_id", "user_id"):
            value = normalized.get(field)
            if not isinstance(value, str) or not value or len(value) > MAX_ENVELOPE_ID_LENGTH:
                raise SachimaPayloadError(f"Invalid Sachima v1 ingress field: {field}")

        text = normalized.get("text")
        content = normalized.get("content")
        if text in (None, "") and content not in (None, ""):
            if not isinstance(content, str):
                raise SachimaPayloadError("Invalid Sachima v1 deprecated content alias")
            normalized["text"] = content
        elif text not in (None, "") and not isinstance(text, str):
            raise SachimaPayloadError("Invalid Sachima v1 text field")
        normalized.pop("content", None)

        attachments = normalized.get("attachments") or []
        if "attachments" in normalized and not isinstance(normalized["attachments"], list):
            raise SachimaPayloadError("Sachima attachments must be a list")
        if normalized.get("text") in (None, "") and not attachments:
            raise SachimaPayloadError("Missing required Sachima v1 ingress field: text")
        return normalized

    def _is_allowed_ingress_user(self, payload: Dict[str, Any]) -> bool:
        """Return whether an ingress sender is allowed by local Sachima config."""
        extra = self.config.extra or {}
        if extra.get("allow_all_users") is True:
            return True
        raw_allowed_users = extra.get("allowed_users") or []
        if isinstance(raw_allowed_users, str):
            allowed_users = [user.strip() for user in raw_allowed_users.split(",") if user.strip()]
        elif isinstance(raw_allowed_users, (list, tuple, set, frozenset)):
            allowed_users = list(raw_allowed_users)
        else:
            allowed_users = []
        if not allowed_users:
            return True
        allowed = {str(user).strip() for user in allowed_users if str(user).strip()}
        user_id = self._payload_value(payload, "user_id", "user", "id")
        return str(user_id) in allowed

    def build_event_from_payload(self, payload: Dict[str, Any]) -> MessageEvent:
        """Normalize a Sachima webhook payload into a Hermes MessageEvent."""
        payload = self._normalize_ingress_payload(payload)
        media_urls, media_types = self._extract_base64_image_media(payload, reject_urls=True)
        return self._message_event_from_payload(payload, media_urls, media_types)

    async def _build_event_from_payload_async(self, payload: Dict[str, Any]) -> MessageEvent:
        """Normalize payload, including URL-backed images that need async download."""
        payload = self._normalize_ingress_payload(payload)
        media_urls, media_types = self._extract_base64_image_media(payload, reject_urls=False)
        url_media_urls, url_media_types = await self._extract_url_image_media(payload)
        media_urls.extend(url_media_urls)
        media_types.extend(url_media_types)
        return self._message_event_from_payload(payload, media_urls, media_types)

    def _message_event_from_payload(
        self,
        payload: Dict[str, Any],
        media_urls: list[str],
        media_types: list[str],
    ) -> MessageEvent:
        """Build a MessageEvent after media has been normalized."""
        text = self._payload_value(payload, "text", "message", "text")
        chat_id = self._payload_value(payload, "chat_id", "chat", "id")
        user_id = self._payload_value(payload, "user_id", "user", "id")
        required_fields = (("chat_id", chat_id), ("user_id", user_id))
        if not media_urls:
            required_fields = (("text", text),) + required_fields
        for field, value in required_fields:
            if value in (None, ""):
                raise SachimaPayloadError(f"Missing required Sachima payload field: {field}")

        text = str(text) if text not in (None, "") else IMAGE_PLACEHOLDER_TEXT
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
            message_type=MessageType.PHOTO if media_urls else MessageType.TEXT,
            source=source,
            raw_message=payload,
            message_id=self._message_id_from_payload(payload),
            media_urls=media_urls,
            media_types=media_types,
            reply_to_message_id=(
                str(payload["reply_to_message_id"])
                if payload.get("reply_to_message_id")
                else None
            ),
            reply_to_text=payload.get("reply_to_text"),
        )

    def _extract_base64_image_media(
        self,
        payload: Dict[str, Any],
        *,
        reject_urls: bool,
    ) -> tuple[list[str], list[str]]:
        """Cache base64 image attachments and return local paths + MIME types."""
        media_urls: list[str] = []
        media_types: list[str] = []
        for attachment in self._image_attachments_from_payload(payload):
            if attachment.get("url") and reject_urls and not attachment.get("base64"):
                raise SachimaPayloadError("Sachima URL image attachments require async webhook handling")
            encoded = attachment.get("base64") or attachment.get("data")
            if encoded in (None, ""):
                continue
            mime_type, encoded = self._mime_and_base64_payload(attachment, str(encoded))
            ext = self._image_extension_for_mime(mime_type)
            image_bytes = self._decode_image_base64(encoded)
            try:
                media_urls.append(cache_image_from_bytes(image_bytes, ext))
            except ValueError as exc:
                raise SachimaPayloadError(str(exc)) from exc
            media_types.append(mime_type)
        return media_urls, media_types

    async def _extract_url_image_media(self, payload: Dict[str, Any]) -> tuple[list[str], list[str]]:
        """Download URL image attachments through the shared SSRF-safe cache helper."""
        media_urls: list[str] = []
        media_types: list[str] = []
        for attachment in self._image_attachments_from_payload(payload):
            if attachment.get("base64") or attachment.get("data"):
                continue
            url = attachment.get("url") or attachment.get("image_url")
            if url in (None, ""):
                continue
            mime_type = self._mime_type_for_attachment(attachment)
            ext = self._image_extension_for_mime(mime_type)
            try:
                media_urls.append(await cache_image_from_url(str(url), ext, max_bytes=self.max_inbound_media_bytes))
            except ValueError as exc:
                raise SachimaPayloadError(str(exc)) from exc
            media_types.append(mime_type)
        return media_urls, media_types

    def _image_attachments_from_payload(self, payload: Dict[str, Any]) -> list[dict[str, Any]]:
        """Return image attachments from canonical or top-level Sachima media fields."""
        raw_attachments = payload.get("attachments") or []
        if not isinstance(raw_attachments, list):
            raise SachimaPayloadError("Sachima attachments must be a list")

        attachments: list[dict[str, Any]] = []
        for attachment in raw_attachments:
            if not isinstance(attachment, dict):
                raise SachimaPayloadError("Sachima attachment entries must be objects")
            self._validate_image_attachment_shape(attachment)
            attachments.append(attachment)

        if payload.get("image_base64") or payload.get("image_url"):
            top_level = {
                "type": "image",
                "mime_type": payload.get("image_mime_type") or payload.get("mime_type"),
                "filename": payload.get("image_filename") or payload.get("filename"),
                "base64": payload.get("image_base64"),
                "url": payload.get("image_url"),
            }
            self._validate_image_attachment_shape(top_level)
            attachments.append(top_level)
        return attachments

    def _validate_image_attachment_shape(self, attachment: dict[str, Any]) -> None:
        """Reject unsupported Sachima attachment types before caching."""
        attachment_type = str(attachment.get("type") or "").strip().lower()
        mime_type = self._mime_type_for_attachment(attachment)
        is_image_type = attachment_type in ("", "image", "photo", "picture")
        if not is_image_type and not mime_type.startswith("image/"):
            raise SachimaPayloadError(f"Unsupported Sachima attachment type: {attachment_type}")
        self._image_extension_for_mime(mime_type)

    def _mime_and_base64_payload(self, attachment: dict[str, Any], encoded: str) -> tuple[str, str]:
        """Resolve MIME type and strip any data URL header from a base64 payload."""
        if encoded.startswith("data:"):
            header, separator, body = encoded.partition(",")
            if not separator:
                raise SachimaPayloadError("Invalid base64 image data URL")
            encoded = body
            header_mime = header[5:].split(";", 1)[0].strip().lower()
            if header_mime:
                attachment = {**attachment, "mime_type": header_mime}
        return self._mime_type_for_attachment(attachment), encoded

    def _mime_type_for_attachment(self, attachment: dict[str, Any]) -> str:
        """Return declared image MIME type, defaulting conservatively to PNG."""
        mime_type = str(
            attachment.get("mime_type")
            or attachment.get("content_type")
            or attachment.get("mime")
            or "image/png"
        ).strip().lower()
        return mime_type

    def _image_extension_for_mime(self, mime_type: str) -> str:
        """Return safe cache extension for a supported image MIME type."""
        ext = SUPPORTED_IMAGE_MIME_EXTENSIONS.get(mime_type)
        if ext is None:
            raise SachimaPayloadError(f"Unsupported Sachima image MIME type: {mime_type}")
        return ext

    def _decode_image_base64(self, encoded: str) -> bytes:
        """Decode base64 with an encoded-size guard to avoid unbounded allocation."""
        compact = "".join(encoded.split())
        stripped = compact.rstrip("=")
        padding = len(compact) - len(stripped)
        if len(compact) % 4 != 0 or padding > 2 or "=" in stripped:
            raise SachimaPayloadError("Invalid base64 image attachment")
        estimated_bytes = (len(compact) * 3) // 4 - padding
        if estimated_bytes > self.max_inbound_media_bytes:
            raise SachimaPayloadError(
                f"Sachima image attachment exceeds maximum size of {self.max_inbound_media_bytes} bytes"
            )
        try:
            decoded = base64.b64decode(compact, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise SachimaPayloadError("Invalid base64 image attachment") from exc
        if len(decoded) > self.max_inbound_media_bytes:
            raise SachimaPayloadError(
                f"Sachima image attachment exceeds maximum size of {self.max_inbound_media_bytes} bytes"
            )
        return decoded

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
        event = await self._build_event_from_payload_async(payload)
        await self.handle_message(event)
        return event

    def _delivery_url(self) -> str:
        """Return the canonical delivery URL, falling back to deprecated send_url."""
        extra = self.config.extra or {}
        return str(extra.get("delivery_url") or extra.get("send_url") or "").strip()

    def _delivery_payload(
        self,
        *,
        message_id: str,
        chat_id: str,
        text: str,
        reply_to: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> dict[str, Any]:
        """Build a canonical Sachima Envelope v1 delivery callback payload."""
        return {
            "schema_version": SACHIMA_SCHEMA_VERSION,
            "message_id": message_id,
            "chat_id": str(chat_id),
            "user_id": SACHIMA_ASSISTANT_USER_ID,
            "role": "assistant",
            "text": text,
            "reply_to_message_id": reply_to,
            "metadata": metadata or {},
        }

    def _json_body(self, payload: dict[str, Any]) -> bytes:
        """Serialize a v1 envelope once so HMAC signs the exact transmitted body."""
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def _signed_delivery_headers(self, raw_body: bytes) -> dict[str, str]:
        """Return JSON/HMAC headers for a delivery callback body."""
        headers = {"Content-Type": "application/json"}
        secret = str((self.config.extra or {}).get("webhook_secret") or "").strip()
        if secret:
            timestamp = str(int(time.time()))
            headers["X-Sachima-Timestamp"] = timestamp
            headers["X-Sachima-Signature"] = hmac.new(
                secret.encode("utf-8"),
                f"{timestamp}.".encode("utf-8") + raw_body,
                hashlib.sha256,
            ).hexdigest()
        api_key = str(self.config.api_key or (self.config.extra or {}).get("api_key") or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a Sachima Envelope v1 delivery callback or record it locally."""
        chunks = self.truncate_message(content, self.max_message_length)
        delivery_url = self._delivery_url()
        if not delivery_url:
            last_outbound: dict[str, Any] | None = None
            for chunk in chunks:
                self._local_message_counter += 1
                message_id = f"sachima-local-{self._local_message_counter}"
                outbound = self._delivery_payload(
                    message_id=message_id,
                    chat_id=chat_id,
                    text=chunk,
                    reply_to=reply_to,
                    metadata=metadata,
                )
                self.sent_messages.append(outbound)
                last_outbound = outbound
            return SendResult(
                success=True,
                message_id=f"sachima-local-{self._local_message_counter}",
                raw_response=last_outbound,
            )

        try:
            import aiohttp

            last_result: SendResult | None = None
            async with aiohttp.ClientSession() as session:
                for chunk in chunks:
                    self._local_message_counter += 1
                    message_id = f"sachima-delivery-{self._local_message_counter}"
                    outbound = self._delivery_payload(
                        message_id=message_id,
                        chat_id=chat_id,
                        text=chunk,
                        reply_to=reply_to,
                        metadata=metadata,
                    )
                    raw_body = self._json_body(outbound)
                    headers = self._signed_delivery_headers(raw_body)
                    async with session.post(delivery_url, data=raw_body, headers=headers) as response:
                        raw_response = await response.text()
                        if 200 <= response.status < 300:
                            accepted_message_id = response.headers.get("X-Sachima-Message-Id") or message_id
                            last_result = SendResult(
                                success=True,
                                message_id=accepted_message_id,
                                raw_response=raw_response,
                            )
                            continue
                        return SendResult(
                            success=False,
                            error=f"Sachima delivery callback returned HTTP {response.status}: {raw_response}",
                            raw_response=raw_response,
                            retryable=response.status == 429 or response.status >= 500,
                        )
            return last_result or SendResult(success=True)
        except Exception as exc:
            return SendResult(success=False, error=str(exc), retryable=True)

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Return minimal chat metadata for the Sachima channel."""
        return {"id": str(chat_id), "name": str(chat_id), "type": "dm"}
