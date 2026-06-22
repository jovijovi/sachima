#!/usr/bin/env python3
"""Real GatewayRunner smoke test for Sachima without a real Sachima IM.

This is stronger than sachima_smoke.py: it starts GatewayRunner with only the
Sachima platform enabled, sends a signed webhook request, lets the real Hermes
agent/LLM answer it, and verifies the response is delivered to a fake send API.

To avoid disturbing the real running gateway, it creates a temporary HERMES_HOME
and copies only local Hermes config/auth files needed by the model runtime.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import shutil
import socket
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# Make worktree imports win over the installed Hermes checkout.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

REAL_HERMES_HOME = Path(os.environ.get("REAL_HERMES_HOME", "/home/ubuntu/.hermes")).expanduser()
SECRET = "dev-secret"
EXPECTED = "sachima-gateway-ok"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def copy_if_exists(src: Path, dst: Path) -> None:
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def prepare_temp_hermes_home(tmp_root: Path) -> Path:
    hermes_home = tmp_root / "hermes-home"
    hermes_home.mkdir(parents=True, exist_ok=True)

    # Copy runtime config/auth without printing secrets. Missing files are okay;
    # the model runtime will report auth errors if it truly needs them.
    for name in ("config.yaml", "auth.json", ".env", "SOUL.md", "USER.md", "MEMORY.md"):
        copy_if_exists(REAL_HERMES_HOME / name, hermes_home / name)

    # Keep sessions/logs local to the temporary home for this smoke run.
    (hermes_home / "sessions").mkdir(exist_ok=True)
    (hermes_home / "logs").mkdir(exist_ok=True)
    return hermes_home


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
    response_event = asyncio.Event()

    with tempfile.TemporaryDirectory(prefix="sachima-gateway-smoke-") as tmp:
        hermes_home = prepare_temp_hermes_home(Path(tmp))
        os.environ["HERMES_HOME"] = str(hermes_home)
        os.environ["SACHIMA_ALLOW_ALL_USERS"] = "true"
        os.environ["HERMES_HUMAN_DELAY_MODE"] = "off"
        os.environ["HERMES_ACCEPT_HOOKS"] = "1"
        os.environ.setdefault("TERMINAL_CWD", str(REPO_ROOT))

        # Import after HERMES_HOME is set so profile-aware paths use the temp home.
        from aiohttp import ClientSession, web
        from gateway.config import GatewayConfig, Platform, PlatformConfig
        from gateway.run import GatewayRunner

        async def fake_send(request: web.Request) -> web.Response:
            payload = await request.json()
            received_sends.append(payload)
            if EXPECTED in str(payload.get("text", "")):
                response_event.set()
            return web.json_response(
                {"ok": True, "received": len(received_sends)},
                headers={"X-Sachima-Message-Id": f"fake-send-{len(received_sends)}"},
            )

        send_app = web.Application()
        send_app.router.add_post("/send", fake_send)
        send_runner = web.AppRunner(send_app)
        await send_runner.setup()
        send_site = web.TCPSite(send_runner, "127.0.0.1", send_port)
        await send_site.start()

        gateway_config = GatewayConfig(
            platforms={
                Platform.SACHIMA: PlatformConfig(
                    enabled=True,
                    extra={
                        "webhook_host": "127.0.0.1",
                        "webhook_port": webhook_port,
                        "webhook_path": "/webhook/sachima",
                        "webhook_secret": SECRET,
                        "delivery_url": f"http://127.0.0.1:{send_port}/send",
                    },
                )
            },
            sessions_dir=hermes_home / "sessions",
        )
        runner = GatewayRunner(gateway_config)

        try:
            started = await runner.start()
            if not started:
                raise RuntimeError("GatewayRunner.start() returned False")

            webhook_url = f"http://127.0.0.1:{webhook_port}/webhook/sachima"
            prompt = f"请只回复：{EXPECTED}"
            body, headers = signed_body(
                {
                    "schema_version": "sachima.v1",
                    "message_id": "real-gateway-msg-1",
                    "chat_id": "sachima-lab-chat",
                    "user_id": "dog-bro",
                    "role": "user",
                    "text": prompt,
                    "chat_name": "Sachima Lab",
                    "chat_type": "dm",
                    "user_name": "狗哥",
                }
            )

            async with ClientSession() as session:
                async with session.post(webhook_url, data=body, headers=headers) as response:
                    webhook_status = response.status
                    webhook_body = await response.json()

            try:
                await asyncio.wait_for(response_event.wait(), timeout=180)
            except asyncio.TimeoutError as exc:
                raise TimeoutError(
                    f"Timed out waiting for Hermes response containing {EXPECTED!r}; "
                    f"received_sends={received_sends!r}"
                ) from exc

            report = {
                "temp_hermes_home": str(hermes_home),
                "platforms": [p.value for p in runner.adapters.keys()],
                "webhook_url": webhook_url,
                "fake_send_url": f"http://127.0.0.1:{send_port}/send",
                "webhook_response": {"status": webhook_status, "body": webhook_body},
                "received_sends": received_sends,
                "expected": EXPECTED,
                "matched": any(EXPECTED in str(msg.get("text", "")) for msg in received_sends),
            }
            print(json.dumps(report, ensure_ascii=False, indent=2))

            assert webhook_status == 200
            assert webhook_body == {"ok": True, "message_id": "real-gateway-msg-1"}
            assert report["matched"] is True
        finally:
            try:
                await runner.stop()
            finally:
                await send_runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
