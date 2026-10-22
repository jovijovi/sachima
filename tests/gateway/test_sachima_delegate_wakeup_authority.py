"""Sachima delegation result wakes under an active session authority (plan R1, §3.5).

Upstream v0.22.4 builds the session authority before ``runner.start()``, so every resident
turn below runs with ``active_authority()`` set: human messages are committed to the durable
FIFO and executed on a ``restore_native`` copy, while internal events stay on the in-process
path. These cases drive a real ``GatewayRunner``, a real ``WhatsAppAdapter`` (only ``send`` is
recorded), a real ``SessionAuthority`` over SQLite, the real wake dispatcher and the real
delegate coordinator over the offline ARS facade. Only the model call (``_run_agent``) is a
stand-in: it fires the provider-boundary latch and stages the exact report, which is what the
real agent and the ``sachima_delegate_control`` settle action do.
"""

from __future__ import annotations

import asyncio

import pytest

import gateway.sachima_delegate as delegate_mod
from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import SendResult
from gateway.platforms.event import MessageEvent
from gateway.sachima_delegate_state import DelegateOrigin
from tests.gateway.test_sachima_delegate_gateway import _bind, _model_turn_result
from tests.waiting import async_wait_until

CHAT = "15551234567@s.whatsapp.net"
WAKE_HEADER = "[Sachima delegation terminal notification]"


@pytest.fixture(autouse=True)
def _unbind_coordinator():
    delegate_mod.unbind_delegate_coordinator()
    yield
    delegate_mod.unbind_delegate_coordinator()


class _Model:
    """``_run_agent`` stand-in. A turn whose message carries a gated marker waits on it."""

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.turns: list[dict] = []
        self.gates: dict[str, asyncio.Event] = {}
        self.entered: dict[str, asyncio.Event] = {}

    @staticmethod
    def label(message: str) -> str:
        if WAKE_HEADER in message.rsplit("[New message]", 1)[-1]:
            return "wake"
        return message.rsplit("[New message]", 1)[-1].strip().split()[0]

    def gate(self, label: str) -> asyncio.Event:
        self.entered[label] = asyncio.Event()
        return self.gates.setdefault(label, asyncio.Event())

    async def __call__(self, **kwargs):
        label = self.label(kwargs["message"])
        self.turns.append({"label": label, **kwargs})
        if label in self.entered:
            self.entered[label].set()
        if label in self.gates:
            await self.gates[label].wait()
        handoff = kwargs.get("delegate_handoff")
        if handoff is not None:
            handoff.mark_provider_attempt()
            for event_id in handoff.event_ids:
                current = self.coordinator.state.read_result(event_id)
                staged = self.coordinator.settle_result(
                    task_ref=current.task_ref, turn_key=current.turn_key, event_id=event_id,
                    processing_id=current.processing_id, conclusion="reported",
                    evidence_ref=current.full_result_ref,
                )
                assert "refusal" not in staged, staged
        return _model_turn_result(final_response=f"reply:{label}", api_calls=1)

    def labels(self) -> list[str]:
        return [turn["label"] for turn in self.turns]


class _Host:
    """One resident Gateway: runner + authority + adapter + coordinator + wake dispatcher."""

    def __init__(self, runner, adapter, authority, coordinator, facade, model, source):
        self.runner, self.adapter, self.authority = runner, adapter, authority
        self.coordinator, self.facade, self.model, self.source = coordinator, facade, model, source
        self.sent: list[str] = []
        self.send_gates: dict[str, asyncio.Event] = {}
        self.dispatcher = None
        self.task = None

    @property
    def key(self) -> str:
        return self.runner._session_key_for_source(self.source)

    def replies(self, label: str) -> int:
        return self.sent.count(f"reply:{label}")

    async def human(self, text: str, message_id: str) -> MessageEvent:
        event = MessageEvent(text=text, source=self.source, message_id=message_id)
        await self.adapter.handle_message(event)
        return event

    async def settle(self) -> None:
        await async_wait_until(
            lambda: not self.adapter._background_tasks and not self.adapter._session_tasks,
            timeout=30, what="adapter tasks to finish",
        )

    async def delegate(self, text: str = "finish while the user is away"):
        session_id = self.runner.session_store.peek_session_id(self.key)
        origin = DelegateOrigin(
            platform=Platform.WHATSAPP.value, chat_id=CHAT, thread_id=None,
            session_key=self.key, session_id=session_id, reply_anchor="h0",
        )
        admission = self.coordinator.admit_agent("codex", task_text=text)
        assert admission.admitted, admission.refusal
        return await self.coordinator.create(task_text=text, preset=admission.preset, origin=origin)

    def result_for(self, created):
        return self.coordinator.state.result_for_turn(created.turn_key)

    def read(self, created):
        event = self.result_for(created)
        return None if event is None else self.coordinator.state.read_result(event.event_id)

    def business_state(self, created) -> str | None:
        current = self.read(created)
        return None if current is None else current.business_state

    def wakeup_state(self, created) -> str | None:
        current = self.read(created)
        return None if current is None else current.wakeup_state

    def dispatched(self, created) -> bool:
        """One delivery attempt finished (accepted, retried or blocked), whatever its verdict."""
        current = self.read(created)
        return (current is not None and current.wakeup_attempts >= 1
                and current.wakeup_state != "in_flight" and not self.dispatcher._lock.locked())

    def slot(self):
        return self.adapter._pending_messages.get(self.key)

    def queued_rows(self) -> int:
        return sum(1 for _request, status in self.admissions() if status == "queued")

    async def summary_settled(self, created) -> None:
        def settled():
            event = self.result_for(created)
            summary = event and self.coordinator.state.summary_for_event(event.event_id)
            return bool(summary and summary.settled)
        await async_wait_until(settled, timeout=30, what="the terminal result summary")

    def admissions(self) -> list[tuple[str, str]]:
        from hermes_state_runtime import list_session_admissions
        return [(row["request_id"], row["status"])
                for sid in list(self.authority.sessions)
                for row in list_session_admissions(self.authority.db, session_id=sid, pending_only=False)]

    async def close(self) -> None:
        if self.dispatcher is not None:
            await self.dispatcher.close()
        await self.coordinator.close()
        for gate in list(self.model.gates.values()) + list(self.send_gates.values()):
            gate.set()
        await asyncio.gather(*tuple(self.adapter._background_tasks), return_exceptions=True)
        await asyncio.gather(*tuple(self.adapter._session_tasks.values()), return_exceptions=True)
        self.authority.db.close()


async def _host(tmp_path, monkeypatch, *, wakeup: bool = True) -> _Host:
    import gateway.run as gr
    from gateway.sachima_delegate_wakeup import SachimaDelegateWakeupDispatcher
    from gateway.session_authority import initialize_session_authority
    from plugins.platforms.whatsapp.adapter import WhatsAppAdapter

    monkeypatch.setenv("WHATSAPP_ALLOWED_USERS", "15551234567")
    monkeypatch.setattr(gr, "_resolve_runtime_agent_kwargs", lambda: {"api_key": "fake"})
    runner = gr.GatewayRunner(GatewayConfig(
        sessions_dir=tmp_path / "sessions", sachima_completion_wakeup_enabled=wakeup))
    adapter = WhatsAppAdapter(PlatformConfig(enabled=True, extra={
        "text_batch_delay_seconds": 0, "session_path": str(tmp_path / "wa")}))
    adapter.gateway_runner, runner.adapters = runner, {Platform.WHATSAPP: adapter}
    authority = await initialize_session_authority(runner, profile_id="default", instance_id="r1")
    runner._wire_adapter_handlers(adapter)
    coordinator, facade = _bind(tmp_path)
    coordinator._configure_completion_wakeup(wakeup)
    model = _Model(coordinator)
    runner._run_agent = model
    host = _Host(runner, adapter, authority, coordinator, facade, model,
                 adapter.build_source(chat_id=CHAT, user_id=CHAT, chat_type="dm"))

    async def send(chat_id, content, reply_to=None, metadata=None, **_kwargs):
        gate = host.send_gates.get(content)
        if gate is not None:
            await gate.wait()
        host.sent.append(content)
        return SendResult(success=True, message_id=f"s{len(host.sent)}")
    monkeypatch.setattr(adapter, "send", send)

    if wakeup:
        host.dispatcher = SachimaDelegateWakeupDispatcher(
            coordinator, deliver=runner._deliver_sachima_delegate_wakeup, enabled=True)
        runner._sachima_delegate_wakeup = host.dispatcher
        coordinator._set_completion_wakeup_notifier(host.dispatcher.notify)
    else:
        # Wake off: the ordinary human turn is the only result path, but its receipt still
        # settles through the same dispatcher boundary.
        host.dispatcher = SachimaDelegateWakeupDispatcher(
            coordinator, deliver=runner._deliver_sachima_delegate_wakeup, enabled=False)
        runner._sachima_delegate_wakeup = host.dispatcher
    # The conversation exists before any delegation, as in production.
    await host.human("H0 hello", "h0")
    await async_wait_until(lambda: host.replies("H0") == 1, timeout=30, what="the first human reply")
    await host.settle()
    return host


@pytest.mark.asyncio
async def test_1_idle_route_wake_runs_one_turn_and_reports(tmp_path, monkeypatch):
    from gateway.session_authorities import active_authority

    host = await _host(tmp_path, monkeypatch)
    try:
        assert active_authority(host.runner) is host.authority
        created = await host.delegate()
        host.facade.terminalize(0, final_message="exact terminal answer")
        await async_wait_until(lambda: host.business_state(created) == "reported", timeout=30,
                               what="the wake turn's report receipt")
        await host.settle()
        assert host.model.labels() == ["H0", "wake"]
        event = host.result_for(created)
        assert event.event_id in host.model.turns[1]["message"]
        assert host.replies("wake") == 1
        # The wake used the in-process internal path: no durable admission was written for it.
        assert host.admissions() == [("h0", "terminal")]
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_10_non_sachima_notice_still_uses_durable_process_admission(tmp_path, monkeypatch):
    import gateway.session_automation as automation
    from gateway.sachima_delegate_wakeup import DelegateWakeupBatch

    host = await _host(tmp_path, monkeypatch)
    try:
        admitted: list[str] = []

        async def spy(runner, authority, adapter, event, evt):
            admitted.append(evt.get("type"))
        monkeypatch.setattr(automation, "admit_process_notice", spy)
        routing = {"session_key": host.key, "platform": "whatsapp", "chat_type": "dm",
                   "chat_id": CHAT, "user_id": CHAT}
        completion = {"type": "completion", "session_id": "proc_r1", **routing}
        assert await host.runner._inject_watch_notification("process finished", completion) is True
        assert admitted == ["completion"]

        sid = host.runner.session_store.peek_session_id(host.key)
        batch = DelegateWakeupBatch(
            claim_id="dwclaim_00000001", event_ids=("devent_00000001",), task_refs=("dtask_00000001",),
            turn_keys=("dturn_00000001",), session_key=host.key, origin_session_id=sid,
            platform="whatsapp", chat_type="dm", chat_id=CHAT, thread_id=None, user_id=CHAT)
        await host.runner._inject_watch_notification(batch.message_text(), batch.as_gateway_event())
        assert admitted == ["completion"], "a Sachima wake reached the durable automation admission"
        await host.settle()
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_2_busy_runner_queues_the_wake_and_drains_it_after_the_turn(tmp_path, monkeypatch):
    host = await _host(tmp_path, monkeypatch)
    try:
        created = await host.delegate()
        release = host.model.gate("H1")
        await host.human("H1 long task", "h1")
        await asyncio.wait_for(host.model.entered["H1"].wait(), 30)
        host.facade.terminalize(0, final_message="exact answer while busy")
        await async_wait_until(lambda: host.wakeup_state(created) == "queued", timeout=30,
                               what="the wake to be accepted behind the running turn")
        pending = host.slot()
        assert pending is not None and pending.internal is True
        assert pending.metadata["sachima_delegate_event_ids"] == [host.result_for(created).event_id]
        assert host.model.labels() == ["H0", "H1"], "the wake ran beside or interrupted the turn"
        release.set()
        await async_wait_until(lambda: host.business_state(created) == "reported", timeout=30,
                               what="the drained wake's report receipt")
        await host.settle()
        assert host.model.labels() == ["H0", "H1", "wake"]
        assert host.replies("H1") == 1 and host.replies("wake") == 1
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_3_guard_held_by_an_idle_human_delivery_never_runs_the_wake_in_the_observer(
    tmp_path, monkeypatch,
):
    """The human row already finished; its reply send still holds the adapter's route guard."""
    host = await _host(tmp_path, monkeypatch)
    try:
        created = await host.delegate()
        sending = host.send_gates["reply:H1"] = asyncio.Event()
        await host.human("H1 question", "h1")
        await async_wait_until(
            lambda: (host.model.labels() == ["H0", "H1"] and ("h1", "terminal") in host.admissions()
                     and not host.runner._is_session_running(host.key)
                     and host.key in host.adapter._active_sessions),
            timeout=30, what="an idle runner behind a held route guard")
        host.facade.terminalize(0, final_message="exact answer behind a held guard")
        await async_wait_until(lambda: host.dispatched(created) or "wake" in host.model.labels(),
                               timeout=30, what="the wake dispatch to finish")
        assert host.model.labels() == ["H0", "H1"], "the wake turn ran inside the busy observer"
        assert host.wakeup_state(created) == "queued"
        assert host.slot() is not None and host.slot().internal is True
        sending.set()
        await async_wait_until(lambda: host.business_state(created) == "reported", timeout=30,
                               what="the guard owner to drain the wake")
        await host.settle()
        assert host.model.labels() == ["H0", "H1", "wake"]
        assert host.replies("wake") == 1
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_6_two_wakes_merge_into_one_turn_with_every_identity(tmp_path, monkeypatch):
    host = await _host(tmp_path, monkeypatch)
    try:
        first = await host.delegate("first concurrent terminal")
        second = await host.delegate("second concurrent terminal")
        release = host.model.gate("H1")
        await host.human("H1 long task", "h1")
        await asyncio.wait_for(host.model.entered["H1"].wait(), 30)
        host.facade.terminalize(0, final_message="result one")
        host.facade.terminalize(1, final_message="result two")
        await async_wait_until(
            lambda: host.wakeup_state(first) == "queued" and host.wakeup_state(second) == "queued",
            timeout=30, what="both wakes accepted")
        ids = {host.result_for(first).event_id, host.result_for(second).event_id}
        assert set(host.slot().metadata["sachima_delegate_event_ids"]) == ids
        assert host.runner._queue_depth(host.key, adapter=host.adapter) == 1
        release.set()
        await async_wait_until(
            lambda: host.business_state(first) == "reported" and host.business_state(second) == "reported",
            timeout=30, what="both results reported by one turn")
        await host.settle()
        assert host.model.labels() == ["H0", "H1", "wake"]
        assert host.replies("wake") == 1
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_7_unaccepted_wake_retries_and_counts_the_attempt(tmp_path, monkeypatch):
    from gateway.sachima_delegate_wakeup import SACHIMA_WAKEUP_RETRYABLE

    host = await _host(tmp_path, monkeypatch)
    try:
        created = await host.delegate()
        adapters, host.runner.adapters = host.runner.adapters, {}
        host.facade.terminalize(0, final_message="answer while the adapter is gone")
        await async_wait_until(
            lambda: (current := host.read(created)) is not None
            and current.wakeup_diagnostic == SACHIMA_WAKEUP_RETRYABLE,
            timeout=30, what="a retryable refusal")
        current = host.read(created)
        assert (current.wakeup_state, current.wakeup_attempts) == ("pending", 1)
        assert host.model.labels() == ["H0"]
        host.runner.adapters = adapters
        recovered = await host.dispatcher.recover()
        assert recovered["accepted"] == 1
        await async_wait_until(lambda: host.business_state(created) == "reported", timeout=30,
                               what="the retried wake to report")
        await host.settle()
        assert host.read(created).wakeup_attempts == 2
        assert host.model.labels() == ["H0", "wake"]
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_7_only_a_gone_pin_supersedes_the_wake(tmp_path, monkeypatch):
    host = await _host(tmp_path, monkeypatch)
    try:
        created = await host.delegate()
        # /new over chat asks for confirmation first; the reset itself is the user boundary.
        await host.runner._handle_reset_command(MessageEvent(text="/new", source=host.source))
        await host.settle()
        assert host.runner.session_store.peek_session_id(host.key) != (
            host.coordinator.state.read_turn(created.turn_key).origin.session_id)
        host.facade.terminalize(0, final_message="answer for the closed conversation")
        await async_wait_until(lambda: host.dispatched(created), timeout=30, what="the wake dispatch")
        current = host.read(created)
        origin = host.coordinator.state.read_turn(created.turn_key).origin
        closed = await host.runner._session_db.get_session(origin.session_id)
        assert current.wakeup_state == "blocked" and "superseded" in current.wakeup_diagnostic, (
            current.wakeup_state, current.wakeup_diagnostic, dict(closed or {}).get("end_reason"))
        assert "wake" not in host.model.labels()
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_8_restart_recovers_in_flight_queued_and_report_pending(tmp_path, monkeypatch):
    from gateway.sachima_delegate_wakeup import SachimaDelegateWakeupDispatcher

    host = await _host(tmp_path, monkeypatch)
    try:
        host.coordinator._set_completion_wakeup_notifier(None)  # the terminals land before the "crash"
        tasks = [await host.delegate(text) for text in ("in flight", "queued", "report pending")]
        for index in range(3):
            host.facade.terminalize(index, final_message=f"durable answer {index}")
        for created in tasks:
            await host.summary_settled(created)
        state = host.coordinator.state
        a, b, c = (host.result_for(created) for created in tasks)
        session_id = host.runner.session_store.peek_session_id(host.key)
        claim = host.coordinator.claim_hermes_context(session_id)
        host.coordinator.confirm_hermes_context(session_id, processing_id=claim.processing_id,
                                                event_ids=(c.event_id,))
        host.coordinator.release_hermes_context(session_id, processing_id=claim.processing_id,
                                                event_ids=(a.event_id, b.event_id))
        assert "refusal" not in host.coordinator.settle_result(
            task_ref=c.task_ref, turn_key=c.turn_key, event_id=c.event_id,
            processing_id=claim.processing_id, conclusion="reported", evidence_ref=c.full_result_ref)
        state.update_result(a.event_id, wakeup_state="in_flight",
                            wakeup_claim_id=state.new_wakeup_claim_id(), wakeup_attempts=1)
        state.update_result(b.event_id, wakeup_state="queued",
                            wakeup_claim_id=state.new_wakeup_claim_id(), wakeup_attempts=1)
        await host.dispatcher.close()
        submits = host.facade.submit_count()

        host.dispatcher = SachimaDelegateWakeupDispatcher(
            host.coordinator, deliver=host.runner._deliver_sachima_delegate_wakeup, enabled=True)
        host.runner._sachima_delegate_wakeup = host.dispatcher
        recovered = await host.dispatcher.recover()
        assert (recovered["report_unknown"], recovered["recovered"], recovered["accepted"]) == (1, 2, 2)
        await async_wait_until(
            lambda: host.business_state(tasks[0]) == "reported" and host.business_state(tasks[1]) == "reported",
            timeout=30, what="the recovered wake to report both results")
        await host.settle()
        assert host.read(tasks[2]).business_state == "blocked"
        assert host.read(tasks[2]).business_diagnostic == "sachima_delegate_report_delivery_unknown"
        assert host.model.labels() == ["H0", "wake"]
        assert host.facade.submit_count() == submits
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_9_a_wake_after_drain_is_retried_not_run(tmp_path, monkeypatch):
    from gateway.run_runtime import drain_gateway_runtime
    from gateway.sachima_delegate_wakeup import SACHIMA_WAKEUP_RETRYABLE

    host = await _host(tmp_path, monkeypatch)
    try:
        created = await host.delegate()
        if getattr(host.runner, "session_runtime_descriptor", None) is None:
            host.runner.session_runtime_descriptor = {"state": "running", "capabilities": []}
        await drain_gateway_runtime(host.runner)
        host.facade.terminalize(0, final_message="answer during shutdown")
        await async_wait_until(
            lambda: (current := host.read(created)) is not None
            and current.wakeup_diagnostic == SACHIMA_WAKEUP_RETRYABLE,
            timeout=30, what="the drained wake to be refused retryably")
        assert (host.wakeup_state(created), host.read(created).wakeup_attempts) == ("pending", 1)
        assert host.model.labels() == ["H0"]
    finally:
        await host.close()


# --------------------------------------------------------------------------- #
# §3.5(5): an ordinary human turn claims the result. Under the authority the turn runs on a
# ``restore_native`` copy of the admitted message, so the receipt it binds must still settle at
# the boundary that really sends the reply: the waiting adapter lifecycle, the busy observer,
# or the recovered no-waiter ``deliver_settled`` send.
# --------------------------------------------------------------------------- #


async def _finished_result(host, text: str):
    created = await host.delegate(text)
    host.facade.terminalize(0, final_message=f"exact result: {text}")
    await host.summary_settled(created)
    assert host.wakeup_state(created) == "not_admitted"  # wake is off: the human turn owns it
    return created


@pytest.mark.asyncio
async def test_5_idle_waiter_human_turn_reports_through_its_own_send(tmp_path, monkeypatch):
    host = await _host(tmp_path, monkeypatch, wakeup=False)
    try:
        created = await _finished_result(host, "result before the question")
        await host.human("H1 what did the delegate return?", "h1")
        await async_wait_until(lambda: host.replies("H1") == 1, timeout=30, what="the human reply")
        await host.settle()
        assert host.model.labels() == ["H0", "H1"]
        assert host.result_for(created).full_result_ref in host.model.turns[1]["message"]
        assert host.business_state(created) == "reported"
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_5_busy_observer_human_turn_reports_through_its_own_send(tmp_path, monkeypatch):
    host = await _host(tmp_path, monkeypatch, wakeup=False)
    try:
        release = host.model.gate("H1")
        await host.human("H1 long task", "h1")
        await asyncio.wait_for(host.model.entered["H1"].wait(), 30)
        created = await _finished_result(host, "result during a busy turn")
        await host.human("H2 and the delegate?", "h2")  # the guard is held: the busy observer owns it
        await async_wait_until(lambda: ("h2", "queued") in host.admissions(), timeout=30,
                               what="H2 committed behind H1")
        release.set()
        await async_wait_until(lambda: host.replies("H2") == 1, timeout=30, what="the observed reply")
        await host.settle()
        assert host.model.labels() == ["H0", "H1", "H2"]
        assert host.result_for(created).full_result_ref in host.model.turns[2]["message"]
        assert host.business_state(created) == "reported"
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_5_recovered_no_waiter_turn_reports_through_deliver_settled(tmp_path, monkeypatch):
    from gateway.session_ingress_context import native_callback
    from hermes_constants import get_hermes_home

    host = await _host(tmp_path, monkeypatch, wakeup=False)
    try:
        created = await _finished_result(host, "result for a replayed admission")
        # Recovery replays a committed row with no live delivery waiter: the drain sends the reply
        # itself after the terminal commit.
        replayed = MessageEvent(text="H1 replayed question", source=host.source, message_id="h1")
        with native_callback(host.runner, replayed, get_hermes_home()):
            await host.authority.admit_native(replayed)
        await async_wait_until(lambda: host.business_state(created) == "reported", timeout=30,
                               what="the settled send's report receipt")
        assert ("h1", "terminal") in host.admissions()
        assert host.model.labels() == ["H0", "H1"] and host.replies("H1") == 1
    finally:
        await host.close()


# --------------------------------------------------------------------------- #
# §3.5(4): the user's next message takes over a queued wake. Under the authority the message is
# committed to the durable FIFO instead of replacing the wake in the adapter slot, so without the
# takeover the wake ran first and took its own turn. Both arrival orders are covered.
# --------------------------------------------------------------------------- #


async def _wake_queued_behind_h1(host, created) -> asyncio.Event:
    release = host.model.gate("H1")
    await host.human("H1 long task", "h1")
    await asyncio.wait_for(host.model.entered["H1"].wait(), 30)
    host.facade.terminalize(0, final_message="exact result before the correction")
    await async_wait_until(lambda: host.wakeup_state(created) == "queued" and host.slot() is not None,
                           timeout=30, what="the wake queued behind H1")
    return release


def _assert_human_owns_the_wake(host, human, created) -> None:
    metadata = human.metadata
    assert metadata["sachima_delegate_event_ids"] == [host.result_for(created).event_id]
    assert metadata["sachima_delegate_task_refs"] == [created.task_ref]
    assert metadata["sachima_delegate_turn_keys"] == [created.turn_key]
    assert metadata["sachima_delegate_continuation_refs"] == []
    assert callable(metadata["_gateway_processing_outcome_callback"])
    assert human._gateway_accepted is True
    # The text, the user identity and gateway-control authority remain the user's.
    assert human.internal is False and human.allow_gateway_control is True
    assert human.source.user_id == CHAT and human.text.startswith("H2")
    # One pending turn for the route: the committed human row, no separate wake.
    assert host.slot() is None and host.queued_rows() == 1


@pytest.mark.asyncio
async def test_4_user_message_after_a_queued_wake_owns_the_next_turn(tmp_path, monkeypatch):
    host = await _host(tmp_path, monkeypatch)
    try:
        created = await host.delegate()
        release = await _wake_queued_behind_h1(host, created)
        human = await host.human("H2 stop the follow-up and only report the result", "h2")
        await async_wait_until(lambda: ("h2", "queued") in host.admissions(), timeout=30,
                               what="H2 committed")
        _assert_human_owns_the_wake(host, human, created)
        release.set()
        await async_wait_until(lambda: host.business_state(created) == "reported", timeout=30,
                               what="the user's turn to report the result")
        await host.settle()
        assert host.model.labels() == ["H0", "H1", "H2"], "the wake ran before or beside the user"
        assert host.result_for(created).full_result_ref in host.model.turns[2]["message"]
        assert host.replies("H2") == 1 and host.replies("wake") == 0
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_4_wake_after_a_committed_user_message_joins_that_turn(tmp_path, monkeypatch):
    host = await _host(tmp_path, monkeypatch)
    try:
        created = await host.delegate()
        release = host.model.gate("H1")
        await host.human("H1 long task", "h1")
        await asyncio.wait_for(host.model.entered["H1"].wait(), 30)
        human = await host.human("H2 next question", "h2")
        await async_wait_until(lambda: ("h2", "queued") in host.admissions(), timeout=30,
                               what="H2 committed")
        host.facade.terminalize(0, final_message="exact result after the user's message")
        await async_wait_until(lambda: host.dispatched(created), timeout=30, what="the wake dispatch")
        assert host.wakeup_state(created) == "queued"
        _assert_human_owns_the_wake(host, human, created)
        release.set()
        await async_wait_until(lambda: host.business_state(created) == "reported", timeout=30,
                               what="the user's turn to report the result")
        await host.settle()
        assert host.model.labels() == ["H0", "H1", "H2"]
        assert host.replies("H2") == 1 and host.replies("wake") == 0
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_4_a_stopped_user_message_returns_the_wake_identity(tmp_path, monkeypatch):
    host = await _host(tmp_path, monkeypatch)
    try:
        created = await host.delegate()
        release = await _wake_queued_behind_h1(host, created)
        human = await host.human("H2 correction", "h2")
        await async_wait_until(lambda: ("h2", "queued") in host.admissions(), timeout=30,
                               what="H2 committed")
        assert host.slot() is None
        await host.human("/stop", "stop-1")
        await async_wait_until(lambda: ("h2", "terminal") in host.admissions(), timeout=30,
                               what="/stop to cancel H2")
        release.set()
        await async_wait_until(lambda: host.business_state(created) == "reported", timeout=30,
                               what="the returned wake to report the result")
        await host.settle()
        assert "H2" not in host.model.labels()
        assert host.model.labels().count("wake") == 1 and host.replies("wake") == 1
        assert "sachima_delegate_event_ids" not in human.metadata
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_4_a_refused_user_message_leaves_the_queued_wake_alone(tmp_path, monkeypatch):
    from hermes_state_runtime import RuntimeStoreError

    host = await _host(tmp_path, monkeypatch)
    try:
        created = await host.delegate()
        release = await _wake_queued_behind_h1(host, created)
        admit = host.authority.admit_native

        async def refuse_h2(event):
            if event.message_id == "h2":
                raise RuntimeStoreError("invalid_params", field="text")
            return await admit(event)
        monkeypatch.setattr(host.authority, "admit_native", refuse_h2)
        human = await host.human("H2 refused", "h2")
        await async_wait_until(lambda: any("refused this message" in sent for sent in host.sent),
                               timeout=30, what="the refusal notice")
        assert host.slot() is not None and host.slot().internal is True
        assert "sachima_delegate_event_ids" not in human.metadata
        release.set()
        await async_wait_until(lambda: host.business_state(created) == "reported", timeout=30,
                               what="the untouched wake to report the result")
        await host.settle()
        assert host.model.labels() == ["H0", "H1", "wake"]
    finally:
        await host.close()
