"""Composed regressions for native delegation report delivery on Feishu.

The wakeup producer, gateway injection, shared reply selection, Feishu request
construction/fallback, processing callback, and delegate settlement are real.
Only the external Feishu client and state/session persistence are replaced.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import MessageEvent, _reply_anchor_for_event
from gateway.run import GatewayRunner
from gateway.sachima_delegate import SachimaDelegateCoordinator
from gateway.sachima_delegate_state import DelegateResultEvent
from gateway.sachima_delegate_wakeup import (
    WAKEUP_DELIVERY_ACCEPTED,
    DelegateWakeupBatch,
)
from gateway.session import SessionSource, build_session_key
from plugins.platforms.feishu.adapter import FeishuAdapter


FINAL_REPORT = "Verified native delegation report."
SYNTHETIC_ID_PREFIX = "sachima-wakeup-"


class _MemoryResultState:
    def __init__(self) -> None:
        self.event = DelegateResultEvent(
            event_id="devt_report_anchor",
            turn_key="dturn_report_anchor",
            task_ref="dtask_report_anchor",
            session_id="session-original",
            terminal="completed",
            full_result_ref="dres_report_anchor",
            hermes_sink="confirmed",
            wakeup_state="provider_reached",
            wakeup_claim_id="dwclaim_report_anchor",
            wakeup_attempts=1,
            processing_id="dproc_report_anchor",
            processing_session_id="session-original",
        )

    def read_result(self, event_id: str) -> DelegateResultEvent:
        assert event_id == self.event.event_id
        return self.event

    def update_result(self, event_id: str, **changes) -> DelegateResultEvent:
        assert event_id == self.event.event_id
        self.event = replace(self.event, **changes)
        return self.event


def _response(*, success: bool, code: int = 0, message: str = "success"):
    return SimpleNamespace(
        success=lambda: success,
        code=code,
        msg=message,
        data=SimpleNamespace(message_id="om_delivered" if success else None),
    )


def _request_body(request):
    body = getattr(request, "body", None) or getattr(request, "request_body", None)
    assert body is not None, "Feishu request has no body"
    return body


class _FeishuMessageAPI:
    def __init__(self, *, create_succeeds: bool = True) -> None:
        self.create_succeeds = create_succeeds
        self.calls: list[dict[str, object]] = []

    def reply(self, request):
        body = _request_body(request)
        target = str(request.message_id)
        self.calls.append(
            {
                "method": "reply",
                "message_id": target,
                "msg_type": body.msg_type,
                "content": body.content,
                "reply_in_thread": body.reply_in_thread,
            }
        )
        if target.startswith(SYNTHETIC_ID_PREFIX):
            return _response(
                success=False,
                code=99992354,
                message=f"invalid open_message_id: {target}",
            )
        return _response(success=True)

    def create(self, request):
        body = _request_body(request)
        self.calls.append(
            {
                "method": "create",
                "receive_id_type": request.receive_id_type,
                "receive_id": body.receive_id,
                "msg_type": body.msg_type,
                "content": body.content,
            }
        )
        if not self.create_succeeds:
            return _response(
                success=False,
                code=230006,
                message="permission denied",
            )
        return _response(success=True)


def _feishu_adapter(*, create_succeeds: bool = True):
    adapter = FeishuAdapter(
        PlatformConfig(enabled=True, token="offline-only", typing_indicator=False)
    )
    message_api = _FeishuMessageAPI(create_succeeds=create_succeeds)
    adapter._client = SimpleNamespace(
        im=SimpleNamespace(v1=SimpleNamespace(message=message_api))
    )

    async def _run_blocking_direct(func, *args):
        return func(*args)

    adapter._run_blocking = _run_blocking_direct
    adapter._reactions_enabled = lambda: False
    adapter._running = True
    return adapter, message_api


def _coordinator_for(state: _MemoryResultState):
    coordinator = SimpleNamespace(_state=state)

    def _exact_result_event(task_ref: str, turn_key: str, event_id: str):
        event = state.read_result(event_id)
        assert (task_ref, turn_key) == (event.task_ref, event.turn_key)
        return SimpleNamespace(), event

    coordinator._exact_result_event = _exact_result_event
    return coordinator


async def _await_single_processing_task(adapter: FeishuAdapter) -> None:
    tasks = tuple(adapter._background_tasks)
    assert len(tasks) == 1
    await asyncio.gather(*tasks)


async def _run_native_wakeup(
    monkeypatch,
    tmp_path,
    *,
    thread_id: str | None = None,
    create_succeeds: bool = True,
):
    import gateway.delivery_ledger as delivery_ledger

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(delivery_ledger, "ledger_enabled", lambda: False)

    state = _MemoryResultState()
    source = SessionSource(
        platform=Platform.FEISHU,
        chat_id="oc_original",
        chat_type="group" if thread_id else "dm",
        user_id="ou_original",
        thread_id=thread_id,
        message_id="om_original_authorization",
    )
    session_key = build_session_key(source)
    event = state.event
    batch = DelegateWakeupBatch(
        claim_id=event.wakeup_claim_id,
        event_ids=(event.event_id,),
        task_refs=(event.task_ref,),
        turn_keys=(event.turn_key,),
        session_key=session_key,
        origin_session_id=event.session_id,
        platform="feishu",
        chat_type=source.chat_type,
        chat_id=source.chat_id,
        thread_id=thread_id,
        user_id=source.user_id,
    )

    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig()
    runner._session_db = SimpleNamespace(
        get_session=AsyncMock(return_value={"ended_at": None})
    )
    runner.session_store = SimpleNamespace(
        _ensure_loaded=lambda: None,
        _entries={
            session_key: SimpleNamespace(
                origin=source,
                session_id=event.session_id,
            )
        },
    )
    adapter, message_api = _feishu_adapter(create_succeeds=create_succeeds)
    runner.adapters = {Platform.FEISHU: adapter}

    coordinator = _coordinator_for(state)

    def _complete(event_ids, *, delivered):
        return SachimaDelegateCoordinator.complete_report_delivery.__wrapped__(
            coordinator,
            event_ids,
            delivered=delivered,
        )

    runner._sachima_delegate_wakeup = SimpleNamespace(
        complete_report_delivery=_complete
    )
    captured: list[MessageEvent] = []

    async def _handle(event: MessageEvent) -> str:
        captured.append(event)
        staged = SachimaDelegateCoordinator.settle_result.__wrapped__(
            coordinator,
            task_ref=state.event.task_ref,
            turn_key=state.event.turn_key,
            event_id=state.event.event_id,
            processing_id=state.event.processing_id,
            conclusion="reported",
            evidence_ref=state.event.full_result_ref,
        )
        assert staged["business_state"] == "report_pending"
        event.metadata["_gateway_model_turn_completed"] = True
        return FINAL_REPORT

    adapter.set_message_handler(_handle)

    accepted = await runner._deliver_sachima_delegate_wakeup(batch)
    assert accepted == WAKEUP_DELIVERY_ACCEPTED
    await _await_single_processing_task(adapter)
    assert len(captured) == 1
    return state.event, captured[0], source, message_api.calls


@pytest.mark.asyncio
async def test_native_wakeup_report_creates_in_original_feishu_chat_and_settles(
    monkeypatch,
    tmp_path,
):
    result, event, source, calls = await _run_native_wakeup(monkeypatch, tmp_path)

    assert event.internal is True
    assert event.message_id.startswith(SYNTHETIC_ID_PREFIX)
    assert event.source is source
    assert _reply_anchor_for_event(event) is None
    assert calls == [
        {
            "method": "create",
            "receive_id_type": "chat_id",
            "receive_id": "oc_original",
            "msg_type": "text",
            "content": '{"text": "Verified native delegation report."}',
        }
    ]
    assert result.business_state == "reported"
    assert result.business_diagnostic is None
    assert result.wakeup_state == "settled"


@pytest.mark.asyncio
async def test_native_wakeup_report_preserves_original_feishu_thread_routing(
    monkeypatch,
    tmp_path,
):
    result, event, source, calls = await _run_native_wakeup(
        monkeypatch,
        tmp_path,
        thread_id="omt_original",
    )

    assert event.source is source
    assert _reply_anchor_for_event(event) is None
    assert calls == [
        {
            "method": "create",
            "receive_id_type": "thread_id",
            "receive_id": "omt_original",
            "msg_type": "text",
            "content": '{"text": "Verified native delegation report."}',
        }
    ]
    assert result.business_state == "reported"
    assert result.wakeup_state == "settled"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("thread_id", "reply_to_message_id", "expected_anchor", "reply_in_thread"),
    [
        (None, None, "om_external", False),
        ("omt_external", "om_parent", "om_parent", True),
    ],
)
async def test_external_feishu_events_keep_native_reply_anchors(
    monkeypatch,
    tmp_path,
    thread_id,
    reply_to_message_id,
    expected_anchor,
    reply_in_thread,
):
    import gateway.delivery_ledger as delivery_ledger

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(delivery_ledger, "ledger_enabled", lambda: False)
    adapter, message_api = _feishu_adapter()
    source = SessionSource(
        platform=Platform.FEISHU,
        chat_id="oc_external",
        chat_type="group" if thread_id else "dm",
        user_id="ou_external",
        thread_id=thread_id,
        message_id="om_external",
    )
    event = MessageEvent(
        text="ordinary inbound",
        source=source,
        message_id="om_external",
        reply_to_message_id=reply_to_message_id,
    )
    adapter.set_message_handler(AsyncMock(return_value="Ordinary response."))

    await adapter.handle_message(event)
    await _await_single_processing_task(adapter)

    assert _reply_anchor_for_event(event) == expected_anchor
    assert len(message_api.calls) == 1
    assert message_api.calls[0]["method"] == "reply"
    assert message_api.calls[0]["message_id"] == expected_anchor
    assert message_api.calls[0]["reply_in_thread"] is reply_in_thread


@pytest.mark.asyncio
async def test_native_wakeup_report_transport_failure_blocks_settlement(
    monkeypatch,
    tmp_path,
):
    result, event, source, calls = await _run_native_wakeup(
        monkeypatch,
        tmp_path,
        create_succeeds=False,
    )

    assert event.source is source
    assert _reply_anchor_for_event(event) is None
    assert [call["method"] for call in calls] == ["create", "create"]
    assert all(call["receive_id"] == "oc_original" for call in calls)
    assert all(call["receive_id_type"] == "chat_id" for call in calls)
    assert result.business_state == "blocked"
    assert result.business_diagnostic == "sachima_delegate_report_delivery_failed"
    assert result.wakeup_state == "blocked"
    assert result.wakeup_diagnostic == "sachima_delegate_report_delivery_failed"
