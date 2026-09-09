"""Source-isolated contracts for Sachima terminal continuation.

The ARS side is the existing in-memory facade used by the coordinator suite.
The wake side crosses the real Gateway notification source builder, a real
``BasePlatformAdapter`` session guard, and the real delegate-result handoff.
No socket, provider, or messaging service is contacted.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import gateway.sachima_delegate as delegate_mod
from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    SendResult,
)
from gateway.session import build_session_key

from tests.gateway.test_sachima_delegate_gateway import (
    _Host,
    _bind,
    _delegate,
    _handoff_runner,
    _mark_provider_attempt,
    _model_turn_result,
    _origin_for,
    _source,
    _until,
)


class _WakeAdapter(BasePlatformAdapter):
    """Small real adapter: Base owns ingress/guard/queue; this owns I/O."""

    def __init__(self) -> None:
        super().__init__(
            PlatformConfig(enabled=True, token="test", typing_indicator=False),
            Platform.TELEGRAM,
        )
        self._running = True
        self.sent: list[str] = []

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        self._running = True
        return True

    async def disconnect(self) -> None:
        self._mark_disconnected()

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        self.sent.append(content)
        return SendResult(success=True, message_id=f"wake-{len(self.sent)}")

    async def get_chat_info(self, chat_id):
        return {"id": chat_id, "type": "dm"}


def _wire_gateway_turn(monkeypatch, tmp_path, *, origin, model_side_effect=None):
    """Wire one real adapter ingress to the existing Gateway turn method."""

    from gateway.run import GatewayRunner

    runner = _handoff_runner(
        monkeypatch,
        tmp_path,
        session_id=origin.session_id,
    )
    runner.config = GatewayConfig(sachima_completion_wakeup_enabled=True)
    runner._queued_events = {}
    runner._draining = False
    runner._is_user_authorized = lambda _source: True
    runner._effective_busy_input_mode = lambda _source: "queue"
    runner._session_db = SimpleNamespace(
        get_session=AsyncMock(return_value={"ended_at": None})
    )

    source = _source(chat_id=origin.chat_id, thread_id=origin.thread_id)
    runner.session_store._ensure_loaded = lambda: None
    runner.session_store._entries = {
        origin.session_key: SimpleNamespace(
            origin=source,
            session_id=origin.session_id,
        )
    }

    adapter = _WakeAdapter()
    runner.adapters = {Platform.TELEGRAM: adapter}
    runner._set_session_env = GatewayRunner._set_session_env.__get__(
        runner,
        GatewayRunner,
    )
    seen_events: list[MessageEvent] = []
    generations = iter(range(1, 100))

    if model_side_effect is None:

        async def model_side_effect(**kwargs):
            _mark_provider_attempt(kwargs)
            return _model_turn_result(api_calls=1)

    runner._run_agent = AsyncMock(side_effect=model_side_effect)

    async def _gateway_turn(event: MessageEvent):
        seen_events.append(event)
        return await runner._handle_message_with_agent(
            event,
            event.source,
            origin.session_key,
            next(generations),
        )

    adapter.set_message_handler(_gateway_turn)
    adapter.set_busy_session_handler(runner._handle_active_session_busy_message)
    return runner, adapter, seen_events


@pytest.mark.asyncio
async def test_package_a_config_is_default_off_and_admission_not_first_enable_drives_wake(
    tmp_path,
):
    """Old/off tasks never become backlog merely because the flag turns on."""

    assert GatewayConfig().sachima_completion_wakeup_enabled is False
    enabled = GatewayConfig.from_dict({
        "sachima": {"delegation": {"completion_wakeup": {"enabled": True}}}
    })
    assert enabled.sachima_completion_wakeup_enabled is True

    host = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    coordinator._configure_completion_wakeup(False)
    old = await _delegate(host, coordinator, "task admitted while off")

    # Enabling before its terminal does not retroactively admit this task.
    coordinator._configure_completion_wakeup(True)
    facade.terminalize(0)
    assert await _until(
        lambda: coordinator.state.result_for_turn(old.turn_key) is not None
    )
    old_event = coordinator.state.result_for_turn(old.turn_key)
    assert old_event.wakeup_state == "not_admitted"

    new = await _delegate(host, coordinator, "task admitted after enable")
    facade.terminalize(1)
    assert await _until(
        lambda: coordinator.state.result_for_turn(new.turn_key) is not None
    )
    new_event = coordinator.state.result_for_turn(new.turn_key)
    assert new_event.wakeup_state == "pending"


@pytest.mark.asyncio
async def test_package_a_fake_ars_terminal_wakes_real_gateway_turn_without_user_input(
    tmp_path,
    monkeypatch,
):
    """Terminal truth alone causes one trusted internal main-model turn."""

    from gateway.sachima_delegate_wakeup import SachimaDelegateWakeupDispatcher

    host = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    coordinator._configure_completion_wakeup(True)
    created = await _delegate(host, coordinator, "finish while the user is away")
    origin = coordinator.state.read_turn(created.turn_key).origin
    runner, adapter, seen_events = _wire_gateway_turn(
        monkeypatch,
        tmp_path,
        origin=origin,
    )
    dispatcher = SachimaDelegateWakeupDispatcher(
        coordinator,
        deliver=runner._deliver_sachima_delegate_wakeup,
        enabled=True,
    )
    runner._sachima_delegate_wakeup = dispatcher
    coordinator._set_completion_wakeup_notifier(dispatcher.notify)

    # This is the only stimulus after task creation: no user MessageEvent.
    facade.terminalize(0, final_message="exact terminal answer A")
    assert await _until(lambda: runner._run_agent.await_count == 1)

    event = coordinator.state.result_for_turn(created.turn_key)
    assert len(seen_events) == 1
    assert seen_events[0].internal is True
    assert seen_events[0].allow_gateway_control is False
    assert seen_events[0].metadata["sachima_delegate_event_ids"] == [event.event_id]
    model_message = runner._run_agent.await_args.kwargs["message"]
    assert event.event_id in model_message
    assert event.full_result_ref in model_message
    assert "[New message]" in model_message
    assert (
        coordinator.state.read_result(event.event_id).wakeup_state == "provider_reached"
    )
    assert coordinator.state.read_result(event.event_id).business_state == "pending"

    await dispatcher.close()
    await coordinator.close()
    await asyncio.gather(*tuple(adapter._background_tasks), return_exceptions=True)


@pytest.mark.asyncio
async def test_package_a_busy_batch_queues_once_without_interrupt_or_lost_result_refs(
    tmp_path,
    monkeypatch,
):
    """Two terminals share the busy session's FIFO head and never run beside it."""

    from gateway.sachima_delegate_wakeup import SachimaDelegateWakeupDispatcher

    host = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    coordinator._configure_completion_wakeup(True)
    first = await _delegate(host, coordinator, "first concurrent terminal")
    second = await _delegate(host, coordinator, "second concurrent terminal")
    origin = coordinator.state.read_turn(first.turn_key).origin
    runner, adapter, _seen_events = _wire_gateway_turn(
        monkeypatch,
        tmp_path,
        origin=origin,
    )
    dispatcher = SachimaDelegateWakeupDispatcher(
        coordinator,
        deliver=runner._deliver_sachima_delegate_wakeup,
        enabled=True,
    )
    coordinator._set_completion_wakeup_notifier(dispatcher.notify)

    blocker = asyncio.Event()

    async def _busy_owner():
        await blocker.wait()

    owner_task = asyncio.create_task(_busy_owner())
    adapter._active_sessions[origin.session_key] = asyncio.Event()
    adapter._session_tasks[origin.session_key] = owner_task

    facade.terminalize(0, final_message="exact result one")
    facade.terminalize(1, final_message="exact result two")
    assert await _until(
        lambda: (
            origin.session_key in adapter._pending_messages
            and len(
                adapter._pending_messages[origin.session_key].metadata.get(
                    "sachima_delegate_event_ids", []
                )
            )
            == 2
        )
    )

    first_event = coordinator.state.result_for_turn(first.turn_key)
    second_event = coordinator.state.result_for_turn(second.turn_key)
    pending = adapter._pending_messages[origin.session_key]
    assert pending.internal is True
    assert pending.allow_gateway_control is False
    assert set(pending.metadata["sachima_delegate_event_ids"]) == {
        first_event.event_id,
        second_event.event_id,
    }
    assert runner._run_agent.await_count == 0
    assert adapter._active_sessions[origin.session_key].is_set() is False
    assert runner._queued_events.get(origin.session_key, []) == []

    blocker.set()
    await owner_task
    adapter._session_tasks.pop(origin.session_key, None)
    adapter._active_sessions.pop(origin.session_key, None)
    await dispatcher.close()
    await coordinator.close()


@pytest.mark.asyncio
async def test_package_a_restart_recovers_admitted_intent_without_resubmitting_agent(
    tmp_path,
):
    """A terminal result survives restart; only its wake delivery is retried."""

    from gateway.sachima_delegate_wakeup import SachimaDelegateWakeupDispatcher

    host = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    coordinator._configure_completion_wakeup(True)
    created = await _delegate(host, coordinator, "finish before gateway restart")
    facade.terminalize(0, final_message="durable answer before restart")
    assert await _until(
        lambda: coordinator.state.result_for_turn(created.turn_key) is not None
    )
    assert facade.submit_count() == 1
    await coordinator.close()

    restarted, _ = _bind(tmp_path, facade=facade)
    restarted._configure_completion_wakeup(True)
    delivered = []

    async def _deliver(batch):
        delivered.append(batch)
        return "accepted"

    dispatcher = SachimaDelegateWakeupDispatcher(
        restarted,
        deliver=_deliver,
        enabled=True,
    )
    restarted._set_completion_wakeup_notifier(dispatcher.notify)
    await restarted.restore()
    recovered = await dispatcher.recover()

    event = restarted.state.result_for_turn(created.turn_key)
    assert recovered["accepted"] == 1
    assert [item.event_ids for item in delivered] == [(event.event_id,)]
    assert restarted.state.read_full_result(event.full_result_ref) == (
        "durable answer before restart"
    )
    assert facade.submit_count() == 1
    assert restarted.state.read_result(event.event_id).wakeup_state == "queued"

    await dispatcher.close()
    await restarted.close()


def test_package_a_internal_wake_uses_the_exact_origin_session_key(tmp_path):
    """The batch carries host-bound routing; it never derives ownership from text."""

    from gateway.sachima_delegate_wakeup import DelegateWakeupBatch

    source = _source(chat_id="chat-1")
    session_key = build_session_key(source)
    batch = DelegateWakeupBatch(
        claim_id="dwclaim_12345678",
        event_ids=("devent_12345678",),
        task_refs=("dtask_12345678",),
        turn_keys=("dturn_12345678",),
        session_key=session_key,
        origin_session_id="20260909_010203_abcdef12",
        platform="telegram",
        chat_type="dm",
        chat_id="chat-1",
        thread_id=None,
        user_id="user-1",
    )
    event = batch.as_gateway_event()
    assert event["session_key"] == session_key
    assert event["parent_session_id"] == batch.origin_session_id
    assert event["gateway_session_key"] == session_key
    # Exact key + non-strict physical id lets the existing trusted
    # compression-lineage resolver move to a proven successor. /new is stopped
    # by the parent-session preflight before this event is injected.
    assert event["gateway_session_strict"] is False
    assert event["event_ids"] == ["devent_12345678"]
    assert "authorized" not in event


@pytest.mark.asyncio
async def test_package_b_idle_wake_reads_exact_result_and_settles_after_real_report_delivery(
    tmp_path,
    monkeypatch,
):
    """The business receipt follows exact read + explicit report + real send."""

    import tools.sachima_delegate_control_tool as control_mod
    from gateway.sachima_delegate_wakeup import SachimaDelegateWakeupDispatcher

    host = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    coordinator._configure_completion_wakeup(True)
    task_text = "report this exact finished result"
    origin = _origin_for(host)
    admission = coordinator.admit_agent("codex", task_text=task_text)
    assert admission.admitted
    created = await coordinator.create(
        task_text=task_text,
        preset=admission.preset,
        origin=origin,
        authorization_ref=origin.reply_anchor,
        continuation_task="private authorized follow-up task B",
        continuation_summary="One exact follow-up is authorized after verification.",
        continuation_plan_ref="plan-v1",
        continuation_round_title="执行已授权核验",
        continuation_stop_condition="Stop after reporting the follow-up result.",
    )
    binding = coordinator.state.read_task(created.task_ref)

    monkeypatch.setenv(control_mod.SACHIMA_LIVE_PROGRESS_SURFACE_ENV, "hermes_internal")
    monkeypatch.setattr(
        "gateway.session_context.get_session_env",
        lambda name, default="": {
            "HERMES_SESSION_ID": origin.session_id,
            "HERMES_SESSION_KEY": origin.session_key,
            "HERMES_SESSION_MESSAGE_ID": origin.reply_anchor or "",
        }.get(name, default),
    )
    control_calls: list[dict] = []

    async def _model(**kwargs):
        _mark_provider_attempt(kwargs)
        event = coordinator.state.result_for_turn(created.turn_key)
        confirmed = coordinator.state.read_result(event.event_id)
        exact = json.loads(
            control_mod._handle_delegate_control({
                "action": "result",
                "task_ref": created.task_ref,
                "turn_key": created.turn_key,
                "event_id": event.event_id,
            })
        )
        staged = json.loads(
            control_mod._handle_delegate_control({
                "action": "settle",
                "task_ref": created.task_ref,
                "turn_key": created.turn_key,
                "event_id": event.event_id,
                "processing_id": confirmed.processing_id,
                "conclusion": "reported",
                "evidence_ref": event.full_result_ref,
            })
        )
        control_calls.extend((exact, staged))
        assert "error" not in exact, exact
        assert "error" not in staged, staged
        assert exact["result"]["full_result"] == "exact terminal answer B"
        assert exact["result"]["continuation"] == {
            "disposition": "authorized",
            "authorization_ref": origin.reply_anchor,
            "context_ref": binding.continuation_payload_ref,
            "summary": "One exact follow-up is authorized after verification.",
            "plan_ref": "plan-v1",
            "round_title": "执行已授权核验",
            "stop_condition": "Stop after reporting the follow-up result.",
            "agent_id": "codex",
        }
        assert "private authorized follow-up task B" not in json.dumps(exact)
        assert staged["result"]["business_state"] == "report_pending"
        return _model_turn_result(final_response="Verified exact terminal answer B.")

    runner, adapter, seen_events = _wire_gateway_turn(
        monkeypatch,
        tmp_path,
        origin=origin,
        model_side_effect=_model,
    )
    # GatewayRunner construction installs its own host binding. This harness
    # then replaces that runner's SessionStore with a minimal turn mock, so
    # restore the real origin store after construction just as production's
    # one runner owns both sides.
    control_mod.bind_delegate_control_session_store(host.host.session_store)
    dispatcher = SachimaDelegateWakeupDispatcher(
        coordinator,
        deliver=runner._deliver_sachima_delegate_wakeup,
        enabled=True,
    )
    runner._sachima_delegate_wakeup = dispatcher
    coordinator._set_completion_wakeup_notifier(dispatcher.notify)

    try:
        facade.terminalize(0, final_message="exact terminal answer B")
        assert await _until(
            lambda: (
                (event := coordinator.state.result_for_turn(created.turn_key))
                is not None
                and coordinator.state.read_result(event.event_id).business_state
                == "reported"
            )
        )
        assert len(control_calls) == 2
        assert seen_events[0].metadata["sachima_delegate_continuation_refs"] == [
            binding.continuation_payload_ref
        ]
        assert adapter.sent.count("Verified exact terminal answer B.") == 1
    finally:
        control_mod.bind_delegate_control_session_store(None)
        await dispatcher.close()
        await coordinator.close()
        await asyncio.gather(*tuple(adapter._background_tasks), return_exceptions=True)


@pytest.mark.asyncio
async def test_package_b_natural_turn_claim_uses_the_same_real_report_receipt(
    tmp_path,
    monkeypatch,
):
    """A user turn that wins the claim closes through its own adapter send."""

    import tools.sachima_delegate_control_tool as control_mod
    from gateway.sachima_delegate_wakeup import SachimaDelegateWakeupDispatcher

    host = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    coordinator._configure_completion_wakeup(True)
    created = await _delegate(host, coordinator, "finish before the user's question")
    origin = coordinator.state.read_turn(created.turn_key).origin

    monkeypatch.setenv(control_mod.SACHIMA_LIVE_PROGRESS_SURFACE_ENV, "hermes_internal")
    monkeypatch.setattr(
        "gateway.session_context.get_session_env",
        lambda name, default="": {
            "HERMES_SESSION_ID": origin.session_id,
            "HERMES_SESSION_KEY": origin.session_key,
            "HERMES_SESSION_MESSAGE_ID": "natural-question-1",
        }.get(name, default),
    )

    async def _model(**kwargs):
        _mark_provider_attempt(kwargs)
        event = coordinator.state.result_for_turn(created.turn_key)
        confirmed = coordinator.state.read_result(event.event_id)
        exact = json.loads(
            control_mod._handle_delegate_control({
                "action": "result",
                "task_ref": created.task_ref,
                "turn_key": created.turn_key,
                "event_id": event.event_id,
            })
        )
        staged = json.loads(
            control_mod._handle_delegate_control({
                "action": "settle",
                "task_ref": created.task_ref,
                "turn_key": created.turn_key,
                "event_id": event.event_id,
                "processing_id": confirmed.processing_id,
                "conclusion": "reported",
                "evidence_ref": event.full_result_ref,
            })
        )
        assert exact["result"]["full_result"] == "natural-turn exact result"
        assert staged["result"]["business_state"] == "report_pending"
        return _model_turn_result(final_response="Reported from the natural turn.")

    runner, adapter, seen_events = _wire_gateway_turn(
        monkeypatch,
        tmp_path,
        origin=origin,
        model_side_effect=_model,
    )
    control_mod.bind_delegate_control_session_store(host.host.session_store)
    dispatcher = SachimaDelegateWakeupDispatcher(
        coordinator,
        deliver=runner._deliver_sachima_delegate_wakeup,
        enabled=True,
    )
    runner._sachima_delegate_wakeup = dispatcher

    try:
        facade.terminalize(0, final_message="natural-turn exact result")
        assert await _until(
            lambda: (
                (event := coordinator.state.result_for_turn(created.turn_key))
                is not None
                and (summary := coordinator.state.summary_for_event(event.event_id))
                is not None
                and summary.settled
            )
        )
        natural = MessageEvent(
            text="What did the delegated task return?",
            source=_source(chat_id=origin.chat_id, thread_id=origin.thread_id),
            message_id="natural-question-1",
        )
        await adapter.handle_message(natural)
        assert await _until(
            lambda: (
                coordinator.state.result_for_turn(created.turn_key).business_state
                == "reported"
            )
        )
        assert seen_events == [natural]
        assert natural.internal is False
        assert adapter.sent.count("Reported from the natural turn.") == 1
    finally:
        control_mod.bind_delegate_control_session_store(None)
        await dispatcher.close()
        await coordinator.close()
        await asyncio.gather(*tuple(adapter._background_tasks), return_exceptions=True)


@pytest.mark.asyncio
async def test_package_c_new_session_boundary_supersedes_stored_continuation(
    tmp_path,
    monkeypatch,
):
    """An explicit /new end reason blocks both wake and authorized next step."""

    from gateway.sachima_delegate_wakeup import SachimaDelegateWakeupDispatcher

    host = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    coordinator._configure_completion_wakeup(True)
    admission = coordinator.admit_agent("codex", task_text="finish before /new")
    origin = _origin_for(host)
    created = await coordinator.create(
        task_text="finish before /new",
        preset=admission.preset,
        origin=origin,
        authorization_ref=origin.reply_anchor,
        continuation_task="perform a now-stale authorized follow-up",
        continuation_round_title="执行旧会话的后续",
        continuation_summary="Only valid in the original logical conversation.",
    )
    runner, adapter, _seen_events = _wire_gateway_turn(
        monkeypatch,
        tmp_path,
        origin=origin,
    )
    runner._session_db = SimpleNamespace(
        get_session=AsyncMock(
            return_value={
                "id": origin.session_id,
                "ended_at": "2026-09-09T06:00:00+00:00",
                "end_reason": "session_reset",
            }
        )
    )
    dispatcher = SachimaDelegateWakeupDispatcher(
        coordinator,
        deliver=runner._deliver_sachima_delegate_wakeup,
        enabled=True,
    )
    coordinator._set_completion_wakeup_notifier(dispatcher.notify)

    facade.terminalize(0, final_message="result from the previous conversation")
    assert await _until(
        lambda: (
            (event := coordinator.state.result_for_turn(created.turn_key)) is not None
            and event.wakeup_state == "blocked"
        )
    )
    assert coordinator.state.read_task(created.task_ref).continuation_disposition == (
        "superseded"
    )
    assert runner._run_agent.await_count == 0

    await dispatcher.close()
    await coordinator.close()
    await asyncio.gather(*tuple(adapter._background_tasks), return_exceptions=True)


@pytest.mark.asyncio
async def test_package_c_new_user_correction_replaces_queued_wake_but_keeps_refs(
    tmp_path,
    monkeypatch,
):
    """The newest user input owns the next turn and inherits exact result refs."""

    from gateway.sachima_delegate_wakeup import SachimaDelegateWakeupDispatcher

    host = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    coordinator._configure_completion_wakeup(True)
    created = await _delegate(host, coordinator, "finish while current turn is busy")
    origin = coordinator.state.read_turn(created.turn_key).origin
    runner, adapter, _seen_events = _wire_gateway_turn(
        monkeypatch,
        tmp_path,
        origin=origin,
    )
    dispatcher = SachimaDelegateWakeupDispatcher(
        coordinator,
        deliver=runner._deliver_sachima_delegate_wakeup,
        enabled=True,
    )
    coordinator._set_completion_wakeup_notifier(dispatcher.notify)

    blocker = asyncio.Event()
    owner_task = asyncio.create_task(blocker.wait())
    adapter._active_sessions[origin.session_key] = asyncio.Event()
    adapter._session_tasks[origin.session_key] = owner_task
    facade.terminalize(0, final_message="exact result before correction")
    assert await _until(lambda: origin.session_key in adapter._pending_messages)
    event = coordinator.state.result_for_turn(created.turn_key)

    correction = MessageEvent(
        text="Stop the follow-up and only report the result.",
        source=_source(chat_id=origin.chat_id, thread_id=origin.thread_id),
        message_id="user-correction-1",
    )
    runner._queue_or_replace_pending_event(origin.session_key, correction)

    pending = adapter._pending_messages[origin.session_key]
    assert pending is correction
    assert pending.internal is False
    assert pending.metadata["sachima_delegate_event_ids"] == [event.event_id]
    assert callable(pending.metadata["_gateway_processing_outcome_callback"])
    assert runner._queue_depth(origin.session_key, adapter=adapter) == 1

    blocker.set()
    await owner_task
    adapter._session_tasks.pop(origin.session_key, None)
    adapter._active_sessions.pop(origin.session_key, None)
    await dispatcher.close()
    await coordinator.close()


@pytest.mark.asyncio
async def test_package_c_restart_marks_unreceipted_report_delivery_unknown(
    tmp_path,
):
    """A crash after report staging never guesses whether the send happened."""

    from gateway.sachima_delegate_wakeup import SachimaDelegateWakeupDispatcher

    host = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    coordinator._configure_completion_wakeup(True)
    created = await _delegate(host, coordinator, "stage a report before restart")
    facade.terminalize(0, final_message="durable report source")
    assert await _until(
        lambda: (
            (event := coordinator.state.result_for_turn(created.turn_key)) is not None
            and (summary := coordinator.state.summary_for_event(event.event_id))
            is not None
            and summary.settled
        )
    )
    event = coordinator.state.result_for_turn(created.turn_key)
    claim = coordinator.claim_hermes_context(event.session_id)
    coordinator.confirm_hermes_context(
        event.session_id,
        processing_id=claim.processing_id,
        event_ids=claim.event_ids,
    )
    coordinator.settle_result(
        task_ref=event.task_ref,
        turn_key=event.turn_key,
        event_id=event.event_id,
        processing_id=claim.processing_id,
        conclusion="reported",
        evidence_ref=event.full_result_ref,
    )
    assert coordinator.state.read_result(event.event_id).business_state == (
        "report_pending"
    )
    await coordinator.close()

    restarted, _ = _bind(tmp_path, facade=facade)
    restarted._configure_completion_wakeup(True)
    delivered = []

    async def _deliver(batch):
        delivered.append(batch)
        return "accepted"

    dispatcher = SachimaDelegateWakeupDispatcher(
        restarted,
        deliver=_deliver,
        enabled=True,
    )
    await restarted.restore()
    recovery = await dispatcher.recover()

    recovered = restarted.state.read_result(event.event_id)
    assert recovery["report_unknown"] == 1
    assert recovered.business_state == "blocked"
    assert recovered.business_diagnostic == "sachima_delegate_report_delivery_unknown"
    assert recovered.wakeup_state == "blocked"
    assert delivered == []

    await dispatcher.close()
    await restarted.close()


@pytest.mark.asyncio
async def test_package_c_restart_reconciles_accepted_operation_without_replay(
    tmp_path,
):
    """A durable operation Turn is the receipt source after a host crash."""

    from gateway.sachima_delegate_wakeup import SachimaDelegateWakeupDispatcher

    host = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    coordinator._configure_completion_wakeup(True)
    origin = _origin_for(host)
    admission = coordinator.admit_agent("codex", task_text="initial delegated work")
    created = await coordinator.create(
        task_text="initial delegated work",
        preset=admission.preset,
        origin=origin,
        authorization_ref=origin.reply_anchor,
        continuation_task="perform exactly one accepted follow-up",
        continuation_round_title="执行一次已批准的后续",
        continuation_summary="Exactly one follow-up is authorized.",
    )
    facade.terminalize(0, final_message="initial exact result")
    assert await _until(
        lambda: (
            (event := coordinator.state.result_for_turn(created.turn_key)) is not None
            and (summary := coordinator.state.summary_for_event(event.event_id))
            is not None
            and summary.settled
        )
    )
    event = coordinator.state.result_for_turn(created.turn_key)
    claim = coordinator.claim_hermes_context(origin.session_id)
    coordinator.confirm_hermes_context(
        origin.session_id,
        processing_id=claim.processing_id,
        event_ids=claim.event_ids,
    )
    binding = coordinator.state.read_task(created.task_ref)
    operation_id = coordinator._authorized_operation_id(event, binding)
    coordinator.state.update_result(
        event.event_id,
        operation_id=operation_id,
        operation_state="in_flight",
    )
    continuation_text = coordinator.state.read_payload(binding.continuation_payload_ref)
    next_admission = coordinator.admit_agent(
        binding.agent_id,
        task_text=continuation_text,
    )
    next_turn = await coordinator.continue_task(
        binding.task_ref,
        continuation_text,
        preset=next_admission.preset,
        origin=origin,
        operation_id=operation_id,
        authorized_event_id=event.event_id,
        round_title=binding.continuation_round_title,
    )
    assert next_turn.lifecycle == "admitted"
    assert facade.submit_count() == 2
    await coordinator.close()

    restarted, _ = _bind(tmp_path, facade=facade)
    restarted._configure_completion_wakeup(True)
    delivered = []

    async def _deliver(batch):
        delivered.append(batch)
        return "accepted"

    dispatcher = SachimaDelegateWakeupDispatcher(
        restarted,
        deliver=_deliver,
        enabled=True,
    )
    await restarted.restore()
    recovery = await dispatcher.recover()

    reconciled = restarted.state.read_result(event.event_id)
    assert recovery["operations_reconciled"] == 1
    assert reconciled.operation_state == "accepted"
    assert reconciled.operation_turn_key == next_turn.turn_key
    assert reconciled.business_state == "continued"
    assert restarted.state.read_task(created.task_ref).continuation_disposition == (
        "consumed"
    )
    assert facade.submit_count() == 2
    assert delivered == []

    await dispatcher.close()
    await restarted.close()


@pytest.mark.asyncio
async def test_package_c_restart_repairs_accepted_receipt_before_task_consumption(
    tmp_path,
):
    """An accepted event remains authoritative if task consumption was lost."""

    from gateway.sachima_delegate_wakeup import SachimaDelegateWakeupDispatcher

    host = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    coordinator._configure_completion_wakeup(True)
    origin = _origin_for(host)
    admission = coordinator.admit_agent("codex", task_text="initial delegated work")
    created = await coordinator.create(
        task_text="initial delegated work",
        preset=admission.preset,
        origin=origin,
        authorization_ref=origin.reply_anchor,
        continuation_task="perform exactly one accepted follow-up",
        continuation_round_title="执行一次已批准的后续",
        continuation_summary="Exactly one follow-up is authorized.",
    )
    facade.terminalize(0, final_message="initial exact result")
    assert await _until(
        lambda: (
            (event := coordinator.state.result_for_turn(created.turn_key)) is not None
            and (summary := coordinator.state.summary_for_event(event.event_id))
            is not None
            and summary.settled
        )
    )
    event = coordinator.state.result_for_turn(created.turn_key)
    claim = coordinator.claim_hermes_context(origin.session_id)
    coordinator.confirm_hermes_context(
        origin.session_id,
        processing_id=claim.processing_id,
        event_ids=claim.event_ids,
    )
    binding = coordinator.state.read_task(created.task_ref)
    operation_id = coordinator._authorized_operation_id(event, binding)
    continuation_text = coordinator.state.read_payload(binding.continuation_payload_ref)
    next_admission = coordinator.admit_agent(
        binding.agent_id,
        task_text=continuation_text,
    )
    next_turn = await coordinator.continue_task(
        binding.task_ref,
        continuation_text,
        preset=next_admission.preset,
        origin=origin,
        operation_id=operation_id,
        authorized_event_id=event.event_id,
        round_title=binding.continuation_round_title,
    )
    coordinator.state.update_result(
        event.event_id,
        operation_id=operation_id,
        operation_state="accepted",
        operation_task_ref=next_turn.task_ref,
        operation_turn_key=next_turn.turn_key,
        business_state="continued",
        business_processing_id=claim.processing_id,
        business_evidence_ref=next_turn.turn_key,
        wakeup_state="settled",
    )
    assert coordinator.state.read_task(created.task_ref).continuation_disposition == (
        "authorized"
    )
    await coordinator.close()

    restarted, _ = _bind(tmp_path, facade=facade)
    restarted._configure_completion_wakeup(True)
    deliveries = []

    async def _deliver(batch):
        deliveries.append(batch)
        return "accepted"

    dispatcher = SachimaDelegateWakeupDispatcher(
        restarted,
        deliver=_deliver,
        enabled=True,
    )
    await restarted.restore()
    recovery = await dispatcher.recover()

    assert recovery["operations_reconciled"] == 1
    assert (
        restarted.state.read_task(created.task_ref).continuation_disposition
        == "consumed"
    )
    assert facade.submit_count() == 2
    assert deliveries == []

    await dispatcher.close()
    await restarted.close()


@pytest.mark.asyncio
async def test_package_c_retryable_wake_recovery_is_durably_bounded(tmp_path):
    from gateway.sachima_delegate_wakeup import (
        MAX_WAKEUP_ATTEMPTS,
        SachimaDelegateWakeupDispatcher,
    )

    host = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    coordinator._configure_completion_wakeup(True)
    created = await _delegate(host, coordinator, "exercise bounded wake recovery")
    attempts = []

    async def _retry(batch):
        attempts.append(batch)
        return "retry"

    dispatcher = SachimaDelegateWakeupDispatcher(
        coordinator,
        deliver=_retry,
        enabled=True,
    )
    coordinator._set_completion_wakeup_notifier(dispatcher.notify)
    facade.terminalize(0)
    assert await _until(lambda: len(attempts) == 1)
    for _ in range(MAX_WAKEUP_ATTEMPTS + 2):
        await dispatcher.recover()

    event = coordinator.state.result_for_turn(created.turn_key)
    assert len(attempts) == MAX_WAKEUP_ATTEMPTS
    assert event.wakeup_attempts == MAX_WAKEUP_ATTEMPTS
    assert event.wakeup_state == "blocked"

    await dispatcher.close()
    await coordinator.close()


@pytest.mark.asyncio
async def test_package_c_disabled_before_terminal_never_creates_reenable_backlog(
    tmp_path,
):
    coordinator, facade = _bind(tmp_path)
    coordinator._configure_completion_wakeup(True)
    created = await _delegate(_Host(tmp_path), coordinator, "finish while off")

    coordinator._configure_completion_wakeup(False)
    facade.terminalize(0)
    assert await _until(
        lambda: coordinator.state.result_for_turn(created.turn_key) is not None
    )

    event = coordinator.state.result_for_turn(created.turn_key)
    assert event.wakeup_state == "not_admitted"
    assert coordinator.state.read_task(created.task_ref).completion_wakeup is True
    await coordinator.close()


@pytest.mark.asyncio
async def test_package_c_disable_moves_queued_intent_to_ordinary_turn_without_replay(
    tmp_path,
):
    from gateway.sachima_delegate_wakeup import SachimaDelegateWakeupDispatcher

    coordinator, facade = _bind(tmp_path)
    coordinator._configure_completion_wakeup(True)
    created = await _delegate(
        _Host(tmp_path),
        coordinator,
        "queue before rollback",
    )
    origin_session_id = coordinator.state.read_turn(created.turn_key).origin.session_id
    facade.terminalize(0)
    assert await _until(
        lambda: coordinator.state.result_for_turn(created.turn_key) is not None
    )
    event = coordinator.state.result_for_turn(created.turn_key)
    assert await _until(
        lambda: (
            (summary := coordinator.state.summary_for_event(event.event_id)) is not None
            and summary.settled
        )
    )
    coordinator.state.update_result(
        event.event_id,
        wakeup_state="queued",
        wakeup_claim_id=coordinator.state.new_wakeup_claim_id(),
    )

    deliveries = []

    async def deliver(batch):
        deliveries.append(batch)
        return "accepted"

    disabled = SachimaDelegateWakeupDispatcher(
        coordinator,
        deliver=deliver,
        enabled=False,
    )
    await disabled.recover()
    await disabled.close()

    rolled_back = coordinator.state.read_result(event.event_id)
    assert rolled_back.wakeup_state == "not_admitted"
    assert rolled_back.wakeup_claim_id is None

    reenabled = SachimaDelegateWakeupDispatcher(
        coordinator,
        deliver=deliver,
        enabled=True,
    )
    await reenabled.recover()
    assert deliveries == []

    ordinary_claim = coordinator.claim_hermes_context(origin_session_id)
    assert ordinary_claim is not None
    assert ordinary_claim.event_ids == (event.event_id,)
    await reenabled.close()
    await coordinator.close()


@pytest.mark.asyncio
async def test_package_c_gateway_marks_synthetic_turn_internal_in_tool_context(
    tmp_path,
    monkeypatch,
):
    from gateway.sachima_delegate_wakeup import SachimaDelegateWakeupDispatcher

    host = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    coordinator._configure_completion_wakeup(True)
    created = await _delegate(host, coordinator, "prove trusted input origin")
    origin = coordinator.state.read_turn(created.turn_key).origin
    observed: list[bool] = []

    async def _model(**kwargs):
        import gateway.session_context as session_context

        observed.append(
            getattr(
                session_context,
                "session_input_is_internal",
                lambda: False,
            )()
        )
        _mark_provider_attempt(kwargs)
        return _model_turn_result(api_calls=1)

    runner, adapter, _seen_events = _wire_gateway_turn(
        monkeypatch,
        tmp_path,
        origin=origin,
        model_side_effect=_model,
    )
    dispatcher = SachimaDelegateWakeupDispatcher(
        coordinator,
        deliver=runner._deliver_sachima_delegate_wakeup,
        enabled=True,
    )
    runner._sachima_delegate_wakeup = dispatcher
    coordinator._set_completion_wakeup_notifier(dispatcher.notify)

    facade.terminalize(0)
    assert await _until(lambda: bool(observed))
    assert observed == [True]

    await dispatcher.close()
    await coordinator.close()
    await asyncio.gather(*tuple(adapter._background_tasks), return_exceptions=True)


def test_package_c_config_yaml_is_authoritative_and_default_remains_false(
    tmp_path,
    monkeypatch,
):
    from gateway.config import load_gateway_config
    from hermes_cli.config_defaults import DEFAULT_CONFIG
    from hermes_cli.web_server import CONFIG_SCHEMA

    assert (
        DEFAULT_CONFIG["sachima"]["delegation"]["completion_wakeup"]["enabled"] is False
    )
    schema_entry = CONFIG_SCHEMA["sachima.delegation.completion_wakeup.enabled"]
    assert schema_entry["type"] == "boolean"
    assert schema_entry["category"] == "delegation"
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "sachima:\n  delegation:\n    completion_wakeup:\n      enabled: true\n",
        encoding="utf-8",
    )
    assert load_gateway_config().sachima_completion_wakeup_enabled is True
