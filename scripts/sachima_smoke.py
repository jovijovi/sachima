#!/usr/bin/env python3
"""Local smoke test for the Sachima adapter without a real Sachima IM service.

This starts:
- a fake Sachima send API that records outbound Hermes messages
- a SachimaAdapter-owned webhook listener

It then exercises:
- unsigned request rejection when a secret is configured
- signed v1 payload dispatch
- message_id dedupe
- signed legacy nested payload dispatch
- outbound v1 delivery callback behavior
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import socket
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiohttp import ClientSession, web

from gateway.config import PlatformConfig
from gateway.platforms.sachima import SachimaAdapter


SECRET = "dev-secret"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def signed_body(payload: dict[str, Any]) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(time.time()))
    signature = hmac.new(
        SECRET.encode("utf-8"),
        f"{timestamp}.".encode("utf-8") + body,
        hashlib.sha256,
    ).hexdigest()
    return body, {
        "Content-Type": "application/json",
        "X-Sachima-Timestamp": timestamp,
        "X-Sachima-Signature": signature,
    }


async def main() -> None:
    webhook_port = free_port()
    send_port = free_port()
    received_sends: list[dict[str, Any]] = []
    dispatched_events: list[dict[str, Any]] = []

    async def fake_send(request: web.Request) -> web.Response:
        received_sends.append(await request.json())
        return web.json_response({"ok": True}, headers={"X-Sachima-Message-Id": "fake-send-1"})

    send_app = web.Application()
    send_app.router.add_post("/send", fake_send)
    send_runner = web.AppRunner(send_app)
    await send_runner.setup()
    send_site = web.TCPSite(send_runner, "127.0.0.1", send_port)
    await send_site.start()

    adapter = SachimaAdapter(
        PlatformConfig(
            enabled=True,
            extra={
                "webhook_host": "127.0.0.1",
                "webhook_port": webhook_port,
                "webhook_path": "/webhook/sachima",
                "webhook_secret": SECRET,
                "delivery_url": f"http://127.0.0.1:{send_port}/send",
            },
        )
    )

    async def fake_handle_webhook_payload(payload: dict[str, Any]):
        event = adapter.build_event_from_payload(payload)
        dispatched_events.append(
            {
                "text": event.text,
                "message_id": event.message_id,
                "chat_id": event.source.chat_id,
                "user_id": event.source.user_id,
                "chat_type": event.source.chat_type,
            }
        )
        return event

    adapter.handle_webhook_payload = fake_handle_webhook_payload  # type: ignore[method-assign]
    await adapter.connect()

    try:
        webhook_url = f"http://127.0.0.1:{webhook_port}/webhook/sachima"
        async with ClientSession() as session:
            # 1. Unsigned request should fail closed.
            async with session.post(
                webhook_url,
                json={"message_id": "msg-unsigned", "text": "unsigned", "chat_id": "chat-1", "user_id": "user-1"},
            ) as response:
                unsigned = {"status": response.status, "body": await response.json()}

            # 2. Signed v1 payload should dispatch.
            flat_payload = {
                "schema_version": "sachima.v1",
                "message_id": "msg-1",
                "chat_id": "chat-1",
                "user_id": "user-1",
                "role": "user",
                "text": "hello flat",
            }
            body, headers = signed_body(flat_payload)
            async with session.post(webhook_url, data=body, headers=headers) as response:
                flat = {"status": response.status, "body": await response.json()}

            # 3. Duplicate message should be acknowledged but not dispatched again.
            body, headers = signed_body(flat_payload)
            async with session.post(webhook_url, data=body, headers=headers) as response:
                duplicate = {"status": response.status, "body": await response.json()}

            # 4. Signed nested payload should normalize correctly.
            nested_payload = {
                "text": "hello nested",
                "chat": {"id": "group-1", "name": "Group One", "type": "group"},
                "user": {"id": "user-2", "name": "Alice"},
                "message": {"id": "msg-2"},
            }
            body, headers = signed_body(nested_payload)
            async with session.post(webhook_url, data=body, headers=headers) as response:
                nested = {"status": response.status, "body": await response.json()}

        # 5. Outbound send_url should POST to fake send API.
        send_result = await adapter.send("chat-1", "hello from Hermes", reply_to="msg-1", metadata={"thread_id": "thread-1"})

        report = {
            "webhook_url": webhook_url,
            "fake_send_url": f"http://127.0.0.1:{send_port}/send",
            "unsigned_request": unsigned,
            "signed_flat_request": flat,
            "duplicate_request": duplicate,
            "signed_nested_request": nested,
            "dispatched_events": dispatched_events,
            "send_result": {
                "success": send_result.success,
                "message_id": send_result.message_id,
                "retryable": send_result.retryable,
                "error": send_result.error,
            },
            "received_sends": received_sends,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))

        assert unsigned["status"] == 401
        assert flat == {"status": 200, "body": {"ok": True, "message_id": "msg-1"}}
        assert duplicate == {"status": 200, "body": {"ok": True, "duplicate": True, "message_id": "msg-1"}}
        assert nested == {"status": 200, "body": {"ok": True, "message_id": "msg-2"}}
        assert [event["message_id"] for event in dispatched_events] == ["msg-1", "msg-2"]
        assert send_result.success is True
        assert send_result.message_id == "fake-send-1"
        assert received_sends == [
            {
                "schema_version": "sachima.v1",
                "message_id": "sachima-delivery-1",
                "chat_id": "chat-1",
                "user_id": "sachima-hermes",
                "role": "assistant",
                "text": "hello from Hermes",
                "reply_to_message_id": "msg-1",
                "metadata": {"thread_id": "thread-1"},
            }
        ]
    finally:
        await adapter.disconnect()
        await send_runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
