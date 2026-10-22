"""A delegation wake drained in-band on Feishu settles its report where its reply is sent (C02).

Plan §3.4/§3.5(2): a wake that arrives while a turn runs waits in the adapter's pending slot,
and when that turn ends the runner's own ``_run_agent`` drains it as the next turn of the same
chain (``_run_agent_queued_followup``). Feishu overrides the processing hooks, so the drained
wake is bracketed by the follow-up processing hooks, while its reply is sent afterwards by the
event that opened the chain. The staged report must stay ``report_pending`` until that send
really happens and then settle exactly once: ``reported`` only when the model turn completed and
the transport delivered.

Real ``GatewayRunner`` with its real recursive ``_run_agent`` and queue drain, real
``FeishuAdapter`` (only its outbound send, typing and reaction calls are recorded), real
``SessionAuthority`` over SQLite, real wake dispatcher and delegate coordinator over the offline
ARS facade. The model is an ``AIAgent`` stand-in that stages the exact report the way the
``sachima_delegate_control`` settle action does.
"""

from __future__ import annotations

import asyncio
import re
import sys
import threading
import types
from types import SimpleNamespace

import pytest

import gateway.sachima_delegate as delegate_mod
from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import SendResult
from gateway.platforms.event import MessageEvent
from gateway.sachima_delegate_state import DelegateOrigin
from tests.gateway.test_sachima_delegate_gateway import _bind
from tests.waiting import async_wait_until

CHAT = "oc_sachima_wake_chat"
USER = "ou_sachima_wake_user"
WAKE_HEADER = "[Sachima delegation terminal notification]"


@pytest.fixture(autouse=True)
def _unbind_coordinator():
    delegate_mod.unbind_delegate_coordinator()
    yield
    delegate_mod.unbind_delegate_coordinator()


def _label(message: str) -> str:
    latest = message.rsplit("[New message]", 1)[-1]
    if WAKE_HEADER in latest:
        return "wake"
    found = re.search(r"\bH\d\b", latest)
    return found.group(0) if found else "?"


class _Agent:
    """``AIAgent`` stand-in. A gated turn blocks in the executor until the test releases it."""

    scenario: SimpleNamespace

    def __init__(self, *args, **kwargs):
        from tools.todo_tool import TodoStore

        self.model = kwargs.get("model") or "test/model"
        self.provider = kwargs.get("provider")
        self.base_url = kwargs.get("base_url")
        self.session_id = kwargs.get("session_id")
        self.tools = []
        self.max_iterations = 20
        self.request_overrides = dict(kwargs.get("request_overrides") or {})
        self._primary_runtime = {"model": self.model, "provider": self.provider, "base_url": self.base_url}
        self._api_call_count = 0
        self._todo_store = TodoStore()
        self.provider_attempt_callback = None

    def run_conversation(self, user_message, conversation_history=None, task_id=None, **_kwargs):
        scenario = type(self).scenario
        label = _label(user_message)
        scenario.turns.append(label)
        if self.provider_attempt_callback is not None:
            self.provider_attempt_callback()  # what the real agent fires at the provider boundary
        gate = scenario.gates.pop(label, None)  # one-shot: a later turn with this label runs freely
        if gate is not None:
            gate.entered.set()
            assert gate.release.wait(30), f"turn {label} was never released"
        # Stage the report for every result this turn was handed (claimed under its processing id),
        # exactly as the control tool's settle action does.
        for created in scenario.delegated:
            event = scenario.coordinator.state.result_for_turn(created.turn_key)
            current = event and scenario.coordinator.state.read_result(event.event_id)
            if current is None or current.processing_id is None or current.business_state != "pending":
                continue
            staged = scenario.coordinator.settle_result(
                task_ref=current.task_ref, turn_key=current.turn_key, event_id=current.event_id,
                processing_id=current.processing_id, conclusion="reported",
                evidence_ref=current.full_result_ref,
            )
            assert staged.get("business_state") == "report_pending", staged
            scenario.staged.append(current.event_id)
        final = f"reply:{label}#{scenario.turns.count(label)}"
        messages = list(conversation_history or []) + [
            {"role": "user", "content": user_message}, {"role": "assistant", "content": final}]
        if label in scenario.failed_turns:
            return {"final_response": final, "messages": messages, "api_calls": 1,
                    "failed": True, "completed": False, "error": "controlled model failure"}
        return {"final_response": final, "messages": messages, "api_calls": 1}


class _Host:
    def __init__(self, runner, adapter, authority, coordinator, facade, dispatcher, source, scenario):
        self.runner, self.adapter, self.authority = runner, adapter, authority
        self.coordinator, self.facade, self.dispatcher = coordinator, facade, dispatcher
        self.source, self.scenario = source, scenario
        self.sent: list[str] = []
        self.sent_states: list[dict] = []  # per send: each result's business state as the transport was called
        self.failing_sends: set[str] = set()
        self.reactions: list[tuple] = []
        self.receipts: list[tuple] = []

    @property
    def key(self) -> str:
        return self.runner._session_key_for_source(self.source)

    def gate(self, label: str) -> SimpleNamespace:
        gate = SimpleNamespace(entered=threading.Event(), release=threading.Event())
        self.scenario.gates[label] = gate
        return gate

    async def human(self, text: str, message_id: str) -> MessageEvent:
        event = MessageEvent(text=text, source=self.source, message_id=message_id)
        await self.adapter.handle_message(event)
        return event

    async def delegate(self, text: str = "finish while the user is busy"):
        session_id = self.runner.session_store.peek_session_id(self.key)
        origin = DelegateOrigin(platform=Platform.FEISHU.value, chat_id=CHAT, thread_id=None,
                                session_key=self.key, session_id=session_id, reply_anchor="om_h0")
        admission = self.coordinator.admit_agent("codex", task_text=text)
        assert admission.admitted, admission.refusal
        created = await self.coordinator.create(task_text=text, preset=admission.preset, origin=origin)
        self.scenario.delegated.append(created)
        return created

    def read(self, created):
        event = self.coordinator.state.result_for_turn(created.turn_key)
        return None if event is None else self.coordinator.state.read_result(event.event_id)

    def business_state(self, created):
        current = self.read(created)
        return None if current is None else current.business_state

    def wakeup_state(self, created):
        current = self.read(created)
        return None if current is None else current.wakeup_state

    def sends_of(self, marker: str) -> list[str]:
        return [content for content in self.sent if marker in content]

    def state_at_send(self, marker: str, created):
        index = next(i for i, content in enumerate(self.sent) if marker in content)
        return self.sent_states[index][created.task_ref]

    def admissions(self) -> list[tuple[str, str]]:
        from hermes_state_runtime import list_session_admissions
        return [(row["request_id"], row["status"]) for sid in list(self.authority.sessions)
                for row in list_session_admissions(self.authority.db, session_id=sid, pending_only=False)]

    async def settle(self) -> None:
        await async_wait_until(
            lambda: not self.adapter._background_tasks and not self.adapter._session_tasks,
            timeout=30, what="adapter tasks to finish")

    async def close(self) -> None:
        for gate in self.scenario.gates.values():
            gate.release.set()
        await self.dispatcher.close()
        await self.coordinator.close()
        await asyncio.gather(*tuple(self.adapter._background_tasks), return_exceptions=True)
        await asyncio.gather(*tuple(self.adapter._session_tasks.values()), return_exceptions=True)
        self.authority.db.close()


async def _host(tmp_path, monkeypatch) -> _Host:
    import gateway.run as gr
    import hermes_yaml as yaml
    from gateway.sachima_delegate_wakeup import SachimaDelegateWakeupDispatcher
    from gateway.session_authority import initialize_session_authority
    from hermes_constants import get_hermes_home
    from plugins.platforms.feishu.adapter import FeishuAdapter

    (get_hermes_home() / "config.yaml").write_text(
        yaml.safe_dump({"display": {"tool_progress": "off"}}), encoding="utf-8")
    scenario = SimpleNamespace(turns=[], gates={}, delegated=[], staged=[], failed_turns=set(),
                               coordinator=None)
    fake_run_agent = types.ModuleType("run_agent")
    fake_run_agent.AIAgent = _Agent
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)
    monkeypatch.setattr(_Agent, "scenario", scenario, raising=False)
    monkeypatch.setenv("FEISHU_ALLOWED_USERS", USER)
    monkeypatch.setattr(gr, "_resolve_runtime_agent_kwargs", lambda: {"api_key": "fake"})

    runner = gr.GatewayRunner(GatewayConfig(
        sessions_dir=tmp_path / "sessions", sachima_completion_wakeup_enabled=True))
    adapter = FeishuAdapter(PlatformConfig(enabled=True))
    adapter._client = SimpleNamespace()
    adapter.gateway_runner, runner.adapters = runner, {Platform.FEISHU: adapter}
    authority = await initialize_session_authority(runner, profile_id="default", instance_id="r1-feishu")
    runner._wire_adapter_handlers(adapter)
    coordinator, facade = _bind(tmp_path)
    coordinator._configure_completion_wakeup(True)
    scenario.coordinator = coordinator
    dispatcher = SachimaDelegateWakeupDispatcher(
        coordinator, deliver=runner._deliver_sachima_delegate_wakeup, enabled=True)
    runner._sachima_delegate_wakeup = dispatcher
    coordinator._set_completion_wakeup_notifier(dispatcher.notify)
    source = adapter.build_source(chat_id=CHAT, chat_type="dm", user_id=USER)
    host = _Host(runner, adapter, authority, coordinator, facade, dispatcher, source, scenario)

    async def send(chat_id, content, reply_to=None, metadata=None, **_kwargs):
        host.sent.append(content)
        host.sent_states.append({created.task_ref: host.business_state(created) for created in scenario.delegated})
        if any(marker in content for marker in host.failing_sends):
            return SendResult(success=False, error="controlled transport failure", retryable=False)
        return SendResult(success=True, message_id=f"om_sent_{len(host.sent)}")

    async def add_reaction(message_id, emoji_type):
        host.reactions.append(("add", message_id, emoji_type))
        return f"rx_{len(host.reactions)}"

    async def remove_reaction(message_id, reaction_id):
        host.reactions.append(("remove", message_id, reaction_id))
        return True

    async def quiet(*_args, **_kwargs):
        return None

    # Only the outbound transport is recorded; Feishu's processing hooks and the Base receipt
    # boundary stay the real ones.
    for name, value in (("send", send), ("_add_reaction", add_reaction),
                        ("_remove_reaction", remove_reaction),
                        ("send_typing", quiet), ("stop_typing", quiet)):
        monkeypatch.setattr(adapter, name, value)

    complete = dispatcher.complete_report_delivery

    def record_receipt(event_ids, *, delivered):
        host.receipts.append((tuple(event_ids), delivered))
        return complete(event_ids, delivered=delivered)

    monkeypatch.setattr(dispatcher, "complete_report_delivery", record_receipt)

    # The conversation exists before any delegation, as in production.
    await host.human("H0 hello", "om_h0")
    await async_wait_until(lambda: host.sends_of("reply:H0"), timeout=30, what="the first reply")
    await host.settle()
    return host


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("send_ok", "model_ok", "expected"),
    [
        pytest.param(True, True, "reported", id="delivered"),
        pytest.param(False, True, "blocked", id="send-failed"),
        pytest.param(True, False, "blocked", id="model-failed"),
    ],
)
async def test_drained_wake_report_waits_for_its_real_send_and_settles_once(
    tmp_path, monkeypatch, send_ok, model_ok, expected,
):
    from gateway.session_authorities import active_authority

    host = await _host(tmp_path, monkeypatch)
    try:
        assert active_authority(host.runner) is host.authority
        if not send_ok:
            host.failing_sends.add("reply:wake")
        if not model_ok:
            host.scenario.failed_turns.add("wake")
        created = await host.delegate()
        h1 = host.gate("H1")
        await host.human("H1 long task", "om_h1")
        await async_wait_until(h1.entered.is_set, timeout=30, what="H1 running")
        host.facade.terminalize(0, final_message="exact answer while busy")
        await async_wait_until(lambda: host.wakeup_state(created) == "queued", timeout=30,
                               what="the wake accepted behind the running turn")
        wake = host.adapter._pending_messages.get(host.key)
        assert wake is not None and wake.internal is True
        assert wake.message_id.startswith("sachima-wakeup-")

        h1.release.set()
        await async_wait_until(lambda: host.sends_of("reply:wake"), timeout=30, what="the wake reply send")
        await host.settle()

        # One turn for the wake, drained in-band by H1's own ``_run_agent`` after H1's reply went out.
        assert host.scenario.turns == ["H0", "H1", "wake"]
        assert host.sent.index(host.sends_of("reply:H1")[0]) < host.sent.index(host.sends_of("reply:wake")[0])
        assert host.adapter._pending_messages.get(host.key) is None
        # Feishu's real follow-up processing hooks bracketed the drained wake (UI state unchanged).
        wake_reactions = [entry for entry in host.reactions if entry[1] == wake.message_id]
        assert wake_reactions and wake_reactions[0][0] == "add"
        assert ("remove", wake.message_id) in {entry[:2] for entry in wake_reactions}
        # The report was staged by the wake turn and was still pending when its reply hit the wire.
        event_id = host.read(created).event_id
        assert host.scenario.staged == [event_id]
        assert host.state_at_send("reply:wake", created) == "report_pending"
        # Settled exactly once, by the real send outcome and the real model outcome.
        assert host.receipts == [((event_id,), send_ok and model_ok)]
        assert host.business_state(created) == expected
        assert host.admissions() == [("om_h0", "terminal"), ("om_h1", "terminal")]
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_user_message_still_takes_over_the_queued_wake_on_the_real_drain(tmp_path, monkeypatch):
    """§3.5(4) on the same real path: the user's committed message owns the next turn."""
    host = await _host(tmp_path, monkeypatch)
    try:
        created = await host.delegate()
        h1 = host.gate("H1")
        await host.human("H1 long task", "om_h1")
        await async_wait_until(h1.entered.is_set, timeout=30, what="H1 running")
        host.facade.terminalize(0, final_message="exact answer before the correction")
        await async_wait_until(
            lambda: host.wakeup_state(created) == "queued" and host.adapter._pending_messages.get(host.key),
            timeout=30, what="the wake queued behind H1")
        human = await host.human("H2 only report the result", "om_h2")
        await async_wait_until(lambda: ("om_h2", "queued") in host.admissions(), timeout=30,
                               what="H2 committed")
        assert host.adapter._pending_messages.get(host.key) is None
        assert human.metadata["sachima_delegate_event_ids"] == [host.read(created).event_id]
        assert human.internal is False and human.allow_gateway_control is True

        h1.release.set()
        await async_wait_until(lambda: host.sends_of("reply:H2"), timeout=30, what="the user's reply")
        await host.settle()

        assert host.scenario.turns == ["H0", "H1", "H2"], "the wake ran before or beside the user"
        assert not host.sends_of("reply:wake")
        event_id = host.read(created).event_id
        assert host.scenario.staged == [event_id]
        assert host.state_at_send("reply:H2", created) == "report_pending"
        assert host.receipts == [((event_id,), True)]
        assert host.business_state(created) == "reported"
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_a_wake_drained_ahead_of_another_settles_at_the_drains_own_send(tmp_path, monkeypatch):
    """Two results finishing at different times: the first wake's reply is the drain's direct send."""
    host = await _host(tmp_path, monkeypatch)
    try:
        first = await host.delegate("first terminal")
        second = await host.delegate("second terminal")
        h1 = host.gate("H1")
        await host.human("H1 long task", "om_h1")
        await async_wait_until(h1.entered.is_set, timeout=30, what="H1 running")
        host.facade.terminalize(0, final_message="first exact answer")
        await async_wait_until(lambda: host.wakeup_state(first) == "queued", timeout=30,
                               what="the first wake queued behind H1")
        first_wake = host.gate("wake")
        h1.release.set()
        await async_wait_until(first_wake.entered.is_set, timeout=30, what="the first wake's turn running")
        host.facade.terminalize(1, final_message="second exact answer")
        await async_wait_until(lambda: host.wakeup_state(second) == "queued", timeout=30,
                               what="the second wake queued behind the first")
        first_wake.release.set()
        await async_wait_until(lambda: len(host.sends_of("reply:wake")) == 2, timeout=30,
                               what="both wake replies sent")
        await host.settle()

        assert host.scenario.turns == ["H0", "H1", "wake", "wake"]
        first_id, second_id = host.read(first).event_id, host.read(second).event_id
        assert host.scenario.staged == [first_id, second_id]
        # Each staged report waited for its own turn's reply and settled at that send, in order.
        assert host.state_at_send("reply:wake#1", first) == "report_pending"
        assert host.state_at_send("reply:wake#2", first) == "reported"
        assert host.state_at_send("reply:wake#2", second) == "report_pending"
        assert host.receipts == [((first_id,), True), ((second_id,), True)]
        assert (host.business_state(first), host.business_state(second)) == ("reported", "reported")
    finally:
        await host.close()
