from __future__ import annotations

import pytest

from gateway.config import PlatformConfig
from gateway.delivery_state import record_rich_card_sent, should_skip_final_text
from gateway.platforms.sachima import SachimaAdapter
from gateway.sachima_fake_send_simulator import FakeSachimaSendSimulator, start_fake_sachima_send_server


@pytest.mark.asyncio
async def test_sachima_adapter_fake_send_surfaces_remain_separate(unused_tcp_port: int) -> None:
    simulator = FakeSachimaSendSimulator(
        initialized_delivery_refs={
            "runtime_delivery_0",
            "runtime_delivery_1",
            "runtime_delivery_2",
            "runtime_delivery_3",
            "runtime_delivery_4",
        }
    )
    runner, port = await start_fake_sachima_send_server(simulator, port=unused_tcp_port)
    adapter = SachimaAdapter(
        PlatformConfig(enabled=True, extra={"send_url": f"http://127.0.0.1:{port}/send"})
    )
    try:
        await adapter.send(
            "phase-b-local-chat",
            "任务：安全摘要",
            metadata={
                "surface": "progress_card",
                "delivery_ref": "runtime_delivery_0",
                "idempotency_key": "progress",
            },
        )
        await adapter.send(
            "phase-b-local-chat",
            "卡片：安全摘要",
            metadata={
                "surface": "rich_card",
                "delivery_ref": "runtime_delivery_1",
                "idempotency_key": "rich",
            },
        )
        final_result = await adapter.send(
            "phase-b-local-chat",
            "最终回复：安全摘要",
            metadata={
                "surface": "final_text",
                "delivery_ref": "runtime_delivery_2",
                "idempotency_key": "final",
            },
        )
        await adapter.send(
            "phase-b-local-chat",
            "媒体占位：phase-b-safe-media-ref",
            metadata={
                "surface": "media",
                "delivery_ref": "runtime_delivery_3",
                "idempotency_key": "media",
            },
        )
        await adapter.send(
            "phase-b-local-chat",
            "产物引用：runtime_artifact_0",
            metadata={
                "surface": "artifact",
                "delivery_ref": "runtime_delivery_4",
                "artifact_ref": "runtime_artifact_0",
                "idempotency_key": "artifact",
            },
        )

        rows = simulator.transcript()
        assert [row["surface"] for row in rows] == [
            "progress_card",
            "rich_card",
            "final_text",
            "media",
            "artifact",
        ]
        assert rows[2]["surface"] == "final_text"
        assert final_result.success is True
        assert final_result.message_id == rows[2]["message_id"]
    finally:
        await runner.cleanup()


def test_rich_card_fake_send_does_not_mark_final_text_sent() -> None:
    result = {"final_response": "visible", "delivery_state": {}}

    record_rich_card_sent(
        result,
        result_type="sachima.rich_card.v0",
        message_id="fake-sachima-send-0001",
    )

    assert should_skip_final_text(result) is False


@pytest.mark.asyncio
async def test_sachima_adapter_duplicate_replay_does_not_append_transcript_row(unused_tcp_port: int) -> None:
    simulator = FakeSachimaSendSimulator(initialized_delivery_refs={"runtime_delivery_0"})
    runner, port = await start_fake_sachima_send_server(simulator, port=unused_tcp_port)
    adapter = SachimaAdapter(
        PlatformConfig(enabled=True, extra={"send_url": f"http://127.0.0.1:{port}/send"})
    )
    try:
        metadata = {
            "surface": "final_text",
            "delivery_ref": "runtime_delivery_0",
            "idempotency_key": "same-turn-final",
        }

        first = await adapter.send("phase-b-local-chat", "最终回复：安全摘要", metadata=metadata)
        second = await adapter.send("phase-b-local-chat", "最终回复：安全摘要", metadata=metadata)

        assert first.success is True
        assert second.success is True
        assert second.message_id == first.message_id
        assert len(simulator.transcript()) == 1
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_sachima_adapter_uninitialized_delivery_ref_fails_without_transcript_row(
    unused_tcp_port: int,
) -> None:
    simulator = FakeSachimaSendSimulator(initialized_delivery_refs={"runtime_delivery_0"})
    runner, port = await start_fake_sachima_send_server(simulator, port=unused_tcp_port)
    adapter = SachimaAdapter(
        PlatformConfig(enabled=True, extra={"send_url": f"http://127.0.0.1:{port}/send"})
    )
    try:
        result = await adapter.send(
            "phase-b-local-chat",
            "最终回复：安全摘要",
            metadata={
                "surface": "final_text",
                "delivery_ref": "runtime_delivery_99",
                "idempotency_key": "bad-ref",
            },
        )

        assert result.success is False
        assert result.retryable is False
        assert simulator.transcript() == []
    finally:
        await runner.cleanup()
