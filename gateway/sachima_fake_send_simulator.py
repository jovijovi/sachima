"""Local-only fake Sachima send simulator for Phase B evidence.

This module is intentionally test/runtime-local. It records sanitized fake send
transcripts and returns ACKs only after a local fake ``/send`` request is
received. It does not read user config, restart Gateway, or contact external IM
services.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from aiohttp import web

ALLOWED_SURFACES = frozenset({"progress_card", "rich_card", "final_text", "media", "artifact"})
DEFAULT_INITIALIZED_DELIVERY_REFS = frozenset(
    f"runtime_delivery_{index}" for index in range(len(ALLOWED_SURFACES))
)
UNSAFE_MARKERS = (
    "raw_prompt",
    "raw prompt",
    "tool_output",
    "tool output",
    "card_json",
    "media_path",
    "media_bytes",
    "platform_payload",
    "callback_payload",
    "traceback",
    "runtimeerror:",
    "unsafe-token",
    "token",
    "api_key",
    "secret",
    "bearer ",
    "sk-",
    "media:",
    "/tmp/",
    "/home/",
    "oc_",
    "ou_",
    "om_",
)
DELIVERY_REF_RE = re.compile(r"^runtime_delivery_(0|[1-9][0-9]*)$")
ARTIFACT_REF_RE = re.compile(r"^runtime_artifact_(0|[1-9][0-9]*)$")


class FakeSachimaSendSimulator:
    """In-memory fake-send sink with sanitized transcript and ACK semantics."""

    def __init__(self, initialized_delivery_refs: set[str] | None = None) -> None:
        self.initialized_delivery_refs = (
            set(DEFAULT_INITIALIZED_DELIVERY_REFS)
            if initialized_delivery_refs is None
            else set(initialized_delivery_refs)
        )
        self._rows: list[dict[str, object]] = []
        self._by_idempotency: dict[str, dict[str, object]] = {}
        self._idempotency_signatures: dict[str, tuple[str, str, str | None, str]] = {}
        self._counter = 0

    def record_send(self, payload: object) -> dict[str, object]:
        """Record one fake send request and return a deterministic fake ACK."""

        if not isinstance(payload, dict):
            return self._error("invalid_payload")
        content = payload.get("text") if "text" in payload else payload.get("content")
        reply_to = payload.get("reply_to_message_id") or payload.get("reply_to")
        if self._unsafe(payload) or self._unsafe_content(content):
            return self._error("unsafe_material")

        raw_metadata = payload.get("metadata")
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        surface = str(metadata.get("surface") or "final_text")
        if surface not in ALLOWED_SURFACES:
            return self._error("invalid_surface")

        delivery_ref = str(metadata.get("delivery_ref") or "")
        if DELIVERY_REF_RE.fullmatch(delivery_ref) is None:
            return self._error("invalid_delivery_ref")
        if delivery_ref not in self.initialized_delivery_refs:
            return self._error("uninitialized_delivery_ref")

        artifact_ref = self._safe_artifact_ref(metadata.get("artifact_ref"))
        if artifact_ref is False:
            return self._error("invalid_artifact_ref")

        key = str(metadata.get("idempotency_key") or "")
        signature = self._idempotency_signature(
            surface=surface,
            delivery_ref=delivery_ref,
            artifact_ref=artifact_ref,
            content=content,
        )
        if key and key in self._by_idempotency:
            if self._idempotency_signatures.get(key) != signature:
                return self._error("idempotency_conflict")
            prior = dict(self._by_idempotency[key])
            prior["duplicate"] = True
            return prior

        self._counter += 1
        message_id = f"fake-sachima-send-{self._counter:04d}"
        ack_ref = f"runtime_event_delivery_ack_{self._counter:04d}"
        row: dict[str, object] = {
            "sequence": self._counter,
            "surface": surface,
            "message_id": message_id,
            "delivery_ref": delivery_ref,
            "artifact_ref": artifact_ref,
            "reply_to_present": bool(reply_to),
            "content_digest": self._digest(content),
            "content_preview": self._preview(content),
            "ack_ref": ack_ref,
            "status": "sent",
        }
        self._rows.append(row)

        response: dict[str, object] = {
            "ok": True,
            "message_id": message_id,
            "delivery_ref": delivery_ref,
            "surface": surface,
            "ack_ref": ack_ref,
            "duplicate": False,
        }
        if key:
            self._by_idempotency[key] = dict(response)
            self._idempotency_signatures[key] = signature
        return response

    def transcript(self) -> list[dict[str, object]]:
        """Return sanitized transcript rows without exposing mutable internals."""

        return [dict(row) for row in self._rows]

    @staticmethod
    def _error(code: str) -> dict[str, object]:
        return {"ok": False, "error_code": code, "retryable": False}

    @classmethod
    def _unsafe(cls, value: object) -> bool:
        if isinstance(value, Mapping):
            return any(cls._unsafe(key) or cls._unsafe(item) for key, item in value.items())
        if isinstance(value, (list, tuple, set, frozenset)):
            return any(cls._unsafe(item) for item in value)
        try:
            rendered = str(value).lower()
        except Exception:
            return True
        return any(marker in rendered for marker in UNSAFE_MARKERS)

    @classmethod
    def _unsafe_content(cls, value: object) -> bool:
        if not isinstance(value, str):
            return True
        rendered = value.strip().lower()
        if any(marker in rendered for marker in ("media:", "/tmp/", "/home/", "file://")):
            return True
        if rendered.startswith(("{", "[")) and any(
            marker in rendered for marker in ('"type"', '"body"', '"elements"', '"schema"', 'card')
        ):
            return True
        return False

    @staticmethod
    def _safe_artifact_ref(value: object) -> str | None | bool:
        if value in (None, ""):
            return None
        rendered = str(value)
        if ARTIFACT_REF_RE.fullmatch(rendered) is None:
            return False
        return rendered

    @staticmethod
    def _digest(value: object) -> str:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        return "sha256:" + hashlib.sha256(rendered.encode("utf-8")).hexdigest()

    @classmethod
    def _idempotency_signature(
        cls,
        *,
        surface: str,
        delivery_ref: str,
        artifact_ref: str | None,
        content: object,
    ) -> tuple[str, str, str | None, str]:
        return (surface, delivery_ref, artifact_ref, cls._digest(content))

    @staticmethod
    def _preview(value: object, *, max_len: int = 80) -> str:
        if value is None:
            return ""
        rendered = " ".join(str(value).split())
        if len(rendered) <= max_len:
            return rendered
        return rendered[: max_len - 1] + "…"


def create_fake_sachima_send_app(simulator: FakeSachimaSendSimulator) -> web.Application:
    """Create a loopback-only aiohttp app exposing a fake ``/send`` endpoint."""

    async def handle_send(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except Exception:
            return web.json_response(
                {"ok": False, "error_code": "invalid_json", "retryable": False},
                status=400,
            )
        result = simulator.record_send(payload)
        status = 200 if result.get("ok") else 400
        headers = {}
        if result.get("message_id"):
            headers["X-Sachima-Message-Id"] = str(result["message_id"])
        return web.json_response(result, status=status, headers=headers)

    app = web.Application()
    app.router.add_post("/send", handle_send)
    return app


async def start_fake_sachima_send_server(
    simulator: FakeSachimaSendSimulator,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
) -> tuple[web.AppRunner, int]:
    """Start the fake send app on loopback and return its runner and port."""

    if host != "127.0.0.1":
        raise ValueError("fake Sachima send simulator is loopback-only")
    runner = web.AppRunner(create_fake_sachima_send_app(simulator))
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    try:
        await site.start()
    except Exception:
        await runner.cleanup()
        raise
    resolved_port = _runner_port(runner)
    return runner, resolved_port


def _runner_port(runner: web.AppRunner) -> int:
    for site in runner.sites:
        server = getattr(site, "_server", None)
        sockets = getattr(server, "sockets", None) or []
        for sock in sockets:
            host, port = sock.getsockname()[:2]
            if host == "127.0.0.1":
                return int(port)
    raise RuntimeError("fake Sachima send simulator port unavailable")
