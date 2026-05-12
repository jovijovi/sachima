from __future__ import annotations

from typing import Any

import pytest
from aiohttp import ClientSession

from gateway.sachima_fake_send_simulator import (
    FakeSachimaSendSimulator,
    create_fake_sachima_send_app,
    start_fake_sachima_send_server,
)


def _payload(surface: str = "final_text", delivery_ref: str = "runtime_delivery_0", key: str = "k1") -> dict[str, Any]:
    return {
        "chat_id": "phase-b-local-chat",
        "content": "任务：Phase B fake-send proof",
        "reply_to": "phase-b-local-message-1",
        "metadata": {
            "surface": surface,
            "delivery_ref": delivery_ref,
            "artifact_ref": "runtime_artifact_0",
            "intent_summary": "Phase B fake-send proof",
            "idempotency_key": key,
        },
    }


def test_fake_send_records_surfaces_and_returns_ack_from_received_request() -> None:
    simulator = FakeSachimaSendSimulator()

    response = simulator.record_send(_payload(surface="final_text", delivery_ref="runtime_delivery_1"))

    assert response["ok"] is True
    assert response["surface"] == "final_text"
    assert response["delivery_ref"] == "runtime_delivery_1"
    assert str(response["ack_ref"]).startswith("runtime_event_delivery_ack_")
    rows = simulator.transcript()
    assert rows[0]["surface"] == "final_text"
    assert rows[0]["status"] == "sent"
    assert rows[0]["content_digest"].startswith("sha256:")
    assert rows[0]["reply_to_present"] is True


def test_fake_send_duplicate_idempotency_key_reuses_ack_without_new_transcript_row() -> None:
    simulator = FakeSachimaSendSimulator()
    payload = _payload(surface="rich_card", delivery_ref="runtime_delivery_0", key="same-key")

    first = simulator.record_send(payload)
    second = simulator.record_send(payload)

    assert second["duplicate"] is True
    assert second["message_id"] == first["message_id"]
    assert second["ack_ref"] == first["ack_ref"]
    assert len(simulator.transcript()) == 1


def test_fake_send_rejects_raw_or_secret_shaped_material() -> None:
    simulator = FakeSachimaSendSimulator()

    response = simulator.record_send(
        {
            "chat_id": "oc_phase_b_private_chat",
            "content": "raw_" + "prompt phase b private value",
            "reply_to": "om_phase_b_private_message",
            "metadata": {
                "surface": "final_text",
                "delivery_ref": "runtime_delivery_0",
                "to" + "ken": "unsafe-" + "token-phase-b",
            },
        }
    )

    assert response == {"ok": False, "error_code": "unsafe_material", "retryable": False}
    assert simulator.transcript() == []


def test_fake_send_rejects_uninitialized_delivery_ref() -> None:
    simulator = FakeSachimaSendSimulator(initialized_delivery_refs={"runtime_delivery_0"})

    result = simulator.record_send(_payload(delivery_ref="runtime_delivery_99"))

    assert result["ok"] is False
    assert result["error_code"] == "uninitialized_delivery_ref"
    assert simulator.transcript() == []


def test_fake_send_default_initialized_refs_reject_unknown_delivery_ref() -> None:
    simulator = FakeSachimaSendSimulator()

    result = simulator.record_send(_payload(delivery_ref="runtime_delivery_99"))

    assert result["ok"] is False
    assert result["error_code"] == "uninitialized_delivery_ref"
    assert simulator.transcript() == []


def test_fake_send_rejects_media_path_content() -> None:
    simulator = FakeSachimaSendSimulator()

    result = simulator.record_send(
        _payload(surface="media", delivery_ref="runtime_delivery_3")
        | {"content": "MEDIA:" + "/tmp/private-phase-b.png"}
    )

    assert result == {"ok": False, "error_code": "unsafe_material", "retryable": False}
    assert simulator.transcript() == []


def test_fake_send_rejects_card_like_content_payload() -> None:
    simulator = FakeSachimaSendSimulator()

    result = simulator.record_send(
        _payload(surface="rich_card", delivery_ref="runtime_delivery_1")
        | {"content": {"type": "card", "body": "phase-b raw card payload"}}
    )

    assert result == {"ok": False, "error_code": "unsafe_material", "retryable": False}
    assert simulator.transcript() == []


def test_fake_send_duplicate_idempotency_key_rejects_mismatched_payload() -> None:
    simulator = FakeSachimaSendSimulator()
    first_payload = _payload(surface="final_text", delivery_ref="runtime_delivery_2", key="same-key")
    conflict_payload = _payload(surface="rich_card", delivery_ref="runtime_delivery_1", key="same-key")

    first = simulator.record_send(first_payload)
    conflict = simulator.record_send(conflict_payload)

    assert first["ok"] is True
    assert conflict == {"ok": False, "error_code": "idempotency_conflict", "retryable": False}
    assert len(simulator.transcript()) == 1


@pytest.mark.asyncio
async def test_fake_send_aiohttp_app_returns_ack_header(unused_tcp_port: int) -> None:
    simulator = FakeSachimaSendSimulator()
    runner, port = await start_fake_sachima_send_server(simulator, port=unused_tcp_port)
    try:
        async with ClientSession() as session:
            async with session.post(
                f"http://127.0.0.1:{port}/send",
                json=_payload(surface="final_text", delivery_ref="runtime_delivery_0", key="http-k1"),
            ) as response:
                body = await response.json()

        assert response.status == 200
        assert body["ok"] is True
        assert response.headers["X-Sachima-Message-Id"] == body["message_id"]
        assert simulator.transcript()[0]["surface"] == "final_text"
    finally:
        await runner.cleanup()


def test_create_fake_sachima_send_app_registers_send_route() -> None:
    simulator = FakeSachimaSendSimulator()

    app = create_fake_sachima_send_app(simulator)

    routes = [(route.method, route.resource.canonical) for route in app.router.routes()]
    assert ("POST", "/send") in routes
