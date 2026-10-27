"""Feishu approvals and the Task Workbench card on turns the session authority executes (C04).

v0.22.4 commits every Feishu chat message to the authority's durable FIFO and runs it on a
restored copy. Two Sachima surfaces must keep working on such a turn: an approval answered
from the Feishu card must reach the blocked turn without becoming a queued FIFO input behind
it (which would deadlock until the approval timed out), and the opt-in Task Workbench must
still send and revise its one progress card. Real GatewayRunner, FeishuAdapter (only its
outbound calls are recorded), SessionAuthority over SQLite and the real ``_run_agent``.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import types
from types import SimpleNamespace

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import SendResult
from gateway.platforms.event import MessageEvent
from tests.waiting import async_wait_until

CHAT = "oc_sachima_chat"
USER = "ou_sachima_user"


async def _feishu_host(tmp_path, monkeypatch):
    import gateway.run as gr
    from gateway.session_authority import initialize_session_authority
    from plugins.platforms.feishu.adapter import FeishuAdapter

    monkeypatch.setenv("FEISHU_ALLOWED_USERS", USER)
    monkeypatch.setattr(gr, "_resolve_runtime_agent_kwargs", lambda: {"api_key": "fake"})
    runner = gr.GatewayRunner(GatewayConfig(sessions_dir=tmp_path / "sessions"))
    adapter = FeishuAdapter(PlatformConfig(enabled=True))
    adapter._client = SimpleNamespace()
    adapter.gateway_runner, runner.adapters = runner, {Platform.FEISHU: adapter}
    authority = await initialize_session_authority(runner, profile_id="default", instance_id="c04")
    runner._wire_adapter_handlers(adapter)
    record = SimpleNamespace(sent=[], cards=[], patches=[], card_sent=threading.Event())

    async def send(chat_id, content, reply_to=None, metadata=None, **_kwargs):
        record.sent.append(content)
        return SendResult(success=True, message_id=f"om_{len(record.sent)}")

    async def send_interactive_card(chat_id, card, *, reply_to=None, metadata=None):
        record.cards.append(card)
        record.card_sent.set()
        return SendResult(success=True, message_id="om_workbench_card")

    async def patch_interactive_card(chat_id, message_id, card, *, finalize=False):
        record.patches.append((message_id, finalize, card))
        return SendResult(success=True, message_id=message_id)

    async def quiet(*_args, **_kwargs):
        return None

    for name, value in (("send", send), ("send_interactive_card", send_interactive_card),
                        ("patch_interactive_card", patch_interactive_card),
                        ("on_processing_start", quiet), ("on_processing_complete", quiet),
                        ("send_typing", quiet), ("stop_typing", quiet)):
        monkeypatch.setattr(adapter, name, value)
    source = adapter.build_source(chat_id=CHAT, chat_type="dm", user_id=USER)
    return runner, adapter, authority, source, record


def _admissions(authority):
    from hermes_state_runtime import list_session_admissions
    return [(row["request_id"], row["status"]) for sid in list(authority.sessions)
            for row in list_session_admissions(authority.db, session_id=sid, pending_only=False)]


@pytest.mark.asyncio
async def test_feishu_card_approval_reaches_the_blocked_fifo_turn_without_admission(tmp_path, monkeypatch):
    from tools.approval import _gateway_queues
    from tools.approval_gateway_wait import _ApprovalEntry

    runner, adapter, authority, source, record = await _feishu_host(tmp_path, monkeypatch)
    key = runner._session_key_for_source(source)
    entry = _ApprovalEntry({"command": "rm -rf build"})
    waiting = asyncio.Event()

    async def blocked_turn(**kwargs):
        # What a dangerous terminal command does inside the turn: register, prompt, wait.
        _gateway_queues.setdefault(key, []).append(entry)
        adapter._approval_state[7] = {"session_key": key, "chat_id": CHAT, "message_id": "om_prompt"}
        waiting.set()
        answered = await asyncio.to_thread(entry.event.wait, 30)
        return {"final_response": f"approved={answered}:{entry.result}", "messages": [], "api_calls": 1}

    runner._run_agent = blocked_turn
    adapter._loop = asyncio.get_running_loop()
    try:
        await adapter.handle_message(MessageEvent(text="clean the build", source=source, message_id="om_h1"))
        await asyncio.wait_for(waiting.wait(), 30)
        click = SimpleNamespace(event=SimpleNamespace(
            token="tok", context=SimpleNamespace(open_chat_id=CHAT),
            operator=SimpleNamespace(open_id=USER, user_id=""),
            action=SimpleNamespace(value={"hermes_action": "approve_once", "approval_id": 7})))
        adapter._on_card_action_trigger(click)
        await async_wait_until(lambda: "approved=True:once" in record.sent, timeout=30,
                               what="the approved turn to finish")
        assert _admissions(authority) == [("om_h1", "terminal")], "the approval became a FIFO input"
    finally:
        _gateway_queues.pop(key, None)
        entry.event.set()
        await asyncio.gather(*tuple(adapter._background_tasks), return_exceptions=True)
        authority.db.close()


class _WorkbenchAgent:
    """``AIAgent`` stand-in: one TODO and one tool round, revised after the card is on screen."""

    card_sent: threading.Event | None = None

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

    def _todo(self, status: str) -> None:
        self._todo_store.write([{"id": "release", "content": "Release candidate", "status": status,
                                 "executor": "codex"}])

    def run_conversation(self, user_message, conversation_history=None, task_id=None, **_kwargs):
        self._todo_store.bind_transaction(self._todo_transaction_id)
        self._todo("in_progress")
        self.tool_progress_callback("tool.started", "terminal", "run release checks", {"command": "tests"})
        assert type(self).card_sent.wait(30), "no Workbench card while the FIFO turn ran"
        self._api_call_count = 2
        self._todo("completed")
        self.tool_progress_callback("tool.completed", "terminal", "checks passed", {}, duration=0.1)
        return {"final_response": "release checked", "api_calls": 2, "messages": (conversation_history or []) + [
            {"role": "user", "content": user_message}, {"role": "assistant", "content": "release checked"}]}


@pytest.mark.asyncio
async def test_workbench_card_is_sent_and_revised_during_a_durable_fifo_turn(tmp_path, monkeypatch):
    import json

    import hermes_yaml as yaml
    from hermes_constants import get_hermes_home

    # The authority executes the turn in the owning profile's scope, so the turn reads that
    # home's config.yaml (the isolated test HERMES_HOME).
    (get_hermes_home() / "config.yaml").write_text(yaml.safe_dump({"display": {
        "tool_progress": "off", "task_tracker": {"enabled": True, "mode": "feishu_card", "language": "en"}}}),
        encoding="utf-8")
    fake_run_agent = types.ModuleType("run_agent")
    fake_run_agent.AIAgent = _WorkbenchAgent
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)
    _runner, adapter, authority, source, record = await _feishu_host(tmp_path, monkeypatch)
    monkeypatch.setattr(_WorkbenchAgent, "card_sent", record.card_sent)
    try:
        await adapter.handle_message(MessageEvent(text="check the release", source=source, message_id="om_h1"))
        await async_wait_until(lambda: "release checked" in record.sent, timeout=60,
                               what="the FIFO turn's final reply")
        await async_wait_until(lambda: any(finalize for _id, finalize, _card in record.patches),
                               timeout=30, what="the Workbench card's final revision")
        assert _admissions(authority) == [("om_h1", "terminal")]
        assert len(record.cards) == 1
        assert {message_id for message_id, _finalize, _card in record.patches} == {"om_workbench_card"}
        final = json.dumps(record.patches[-1][2], ensure_ascii=False)
        assert "Release candidate" in final and "Completed" in final
    finally:
        record.card_sent.set()
        await asyncio.gather(*tuple(adapter._background_tasks), return_exceptions=True)
        authority.db.close()
