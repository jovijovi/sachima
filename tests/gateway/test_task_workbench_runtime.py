"""Focused contracts for the gateway Task Workbench runtime seam."""

from __future__ import annotations

import asyncio
import json
import queue
from types import SimpleNamespace

import pytest

from gateway.platforms.base import SendResult
from gateway.progress.tracker import ProgressTracker
from tools.todo_tool import TodoStore


class _TextAdapter:
    name = "capture"

    def __init__(self, *, fail_final_edit: bool = False):
        self.sent: list[dict] = []
        self.edits: list[dict] = []
        self.fail_final_edit = fail_final_edit

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        self.sent.append(
            {
                "chat_id": chat_id,
                "content": content,
                "reply_to": reply_to,
                "metadata": metadata,
            }
        )
        return SendResult(success=True, message_id=f"message-{len(self.sent)}")

    async def edit_message(self, chat_id, message_id, content, **kwargs):
        self.edits.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "content": content,
                **kwargs,
            }
        )
        if self.fail_final_edit and "**Status:** Completed" in content:
            return SendResult(success=False, error="final edit rejected")
        return SendResult(success=True, message_id=message_id)

    async def send_typing(self, chat_id, metadata=None):
        return None


class _FeishuAdapter(_TextAdapter):
    name = "feishu-capture"

    def __init__(self):
        super().__init__()
        self.cards_sent: list[dict] = []
        self.cards_patched: list[dict] = []

    async def send_interactive_card(
        self, chat_id, card, reply_to=None, metadata=None
    ):
        self.cards_sent.append(
            {
                "chat_id": chat_id,
                "card": card,
                "reply_to": reply_to,
                "metadata": metadata,
            }
        )
        return SendResult(success=True, message_id="card-1")

    async def patch_interactive_card(
        self, chat_id, message_id, card, finalize=False
    ):
        self.cards_patched.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "card": card,
                "finalize": finalize,
            }
        )
        return SendResult(success=True, message_id=message_id)


def _agent(transaction_id: str):
    store = TodoStore()
    store.bind_transaction(transaction_id)
    store.write(
        [
            {
                "id": "ship",
                "content": "Ship the candidate",
                "status": "in_progress",
                "executor": "codex",
            }
        ]
    )
    return SimpleNamespace(
        _todo_store=store,
        _todo_transaction_id=transaction_id,
        _current_task_id="persistent-session",
        model="test/model",
        max_iterations=20,
        _api_call_count=1,
        context_compressor=SimpleNamespace(
            last_prompt_tokens=100,
            context_length=1000,
            peak_prompt_tokens=120,
            compression_count=0,
            threshold_tokens=850,
        ),
    )


def test_workbench_uses_platform_safe_edit_intervals():
    from gateway.progress.runtime import TaskWorkbenchRuntime

    text_runtime = TaskWorkbenchRuntime(
        transaction_id="task-text",
        progress_queue=queue.Queue(),
        config={"mode": "text"},
        platform="telegram",
        message="run",
        history=[],
    )
    card_runtime = TaskWorkbenchRuntime(
        transaction_id="task-card",
        progress_queue=queue.Queue(),
        config={"mode": "feishu_card"},
        platform="feishu",
        message="继续",
        history=[],
    )

    assert text_runtime.edit_interval == 1.5
    assert card_runtime.edit_interval == 2.0


async def _finish(runtime, sender, agent, *, failed=False):
    await runtime.finalize(
        agent,
        result={"api_calls": 2, "failed": failed},
        is_error=failed,
        visible=True,
        timeout=1.0,
    )
    sender.cancel()
    with pytest.raises(asyncio.CancelledError):
        await sender


@pytest.mark.asyncio
async def test_text_workbench_updates_one_panel_and_flushes_completed_state():
    from gateway.progress.runtime import TaskWorkbenchRuntime

    transaction = {"transaction_id": "task-one", "queue": queue.Queue()}
    runtime = TaskWorkbenchRuntime.get_or_create(
        transaction,
        {"enabled": True, "mode": "text", "max_length": 3500},
        platform="telegram",
        message="Run the release checks",
        history=[],
    )
    adapter = _TextAdapter()
    agent = _agent("task-one")
    sender = asyncio.create_task(
        runtime.send_progress_messages(
            adapter=adapter,
            chat_id="chat-1",
            reply_to="source-1",
            metadata={"thread_id": "thread-1"},
            cleanup_message_ids=[],
            is_current=lambda: True,
        )
    )

    runtime.record_callback_event(
        agent, "tool.started", "terminal", "run checks", {"command": "tests"}
    )
    await asyncio.sleep(0.05)
    await _finish(runtime, sender, agent)

    assert len(adapter.sent) == 1
    assert adapter.edits
    assert {entry["message_id"] for entry in adapter.edits} == {"message-1"}
    assert "**Status:** Completed" in adapter.edits[-1]["content"]
    assert "task-one" in adapter.edits[-1]["content"]


@pytest.mark.asyncio
async def test_feishu_workbench_sends_then_patches_one_stable_card():
    from gateway.progress.runtime import TaskWorkbenchRuntime

    transaction = {"transaction_id": "task-feishu", "queue": queue.Queue()}
    runtime = TaskWorkbenchRuntime.get_or_create(
        transaction,
        {"enabled": True, "mode": "feishu_card", "language": "zh"},
        platform="feishu",
        message="继续发布检查",
        history=[],
    )
    adapter = _FeishuAdapter()
    agent = _agent("task-feishu")
    sender = asyncio.create_task(
        runtime.send_progress_messages(
            adapter=adapter,
            chat_id="chat-f",
            reply_to=None,
            metadata=None,
            cleanup_message_ids=[],
            is_current=lambda: True,
        )
    )

    runtime.record_callback_event(agent, "tool.started", "terminal", "pwd", {})
    await asyncio.sleep(0.05)
    await _finish(runtime, sender, agent)

    assert len(adapter.cards_sent) == 1
    assert adapter.cards_patched
    assert {entry["message_id"] for entry in adapter.cards_patched} == {"card-1"}
    assert adapter.cards_patched[-1]["finalize"] is True
    rendered = json.dumps(adapter.cards_patched[-1]["card"], ensure_ascii=False)
    # Feishu markdown escapes the hyphen in the visible canonical id.
    assert "task\\\\-feishu" in rendered
    assert "已完成" in rendered


@pytest.mark.asyncio
async def test_final_text_edit_failure_sends_completed_fallback_panel():
    from gateway.progress.runtime import TaskWorkbenchRuntime

    transaction = {"transaction_id": "task-fallback", "queue": queue.Queue()}
    runtime = TaskWorkbenchRuntime.get_or_create(
        transaction,
        {"enabled": True, "mode": "text"},
        platform="telegram",
        message="run",
        history=[],
    )
    adapter = _TextAdapter(fail_final_edit=True)
    agent = _agent("task-fallback")
    sender = asyncio.create_task(
        runtime.send_progress_messages(
            adapter=adapter,
            chat_id="chat-2",
            reply_to=None,
            metadata=None,
            cleanup_message_ids=[],
            is_current=lambda: True,
        )
    )

    runtime.record_callback_event(agent, "tool.started", "terminal", "pwd", {})
    await asyncio.sleep(0.05)
    await _finish(runtime, sender, agent)

    assert len(adapter.sent) == 2
    assert "**Status:** Completed" in adapter.sent[-1]["content"]


@pytest.mark.asyncio
async def test_workbench_persists_operation_and_final_snapshot(tmp_path):
    from gateway.progress.runtime import TaskWorkbenchRuntime

    event_path = tmp_path / "progress" / "events.jsonl"
    transaction = {"transaction_id": "task-persist", "queue": queue.Queue()}
    runtime = TaskWorkbenchRuntime.get_or_create(
        transaction,
        {
            "enabled": True,
            "mode": "text",
            "persist_events": True,
            "event_store": "jsonl",
            "event_store_path": str(event_path),
        },
        platform="telegram",
        message="run",
        history=[],
    )
    adapter = _TextAdapter()
    agent = _agent("task-persist")
    sender = asyncio.create_task(
        runtime.send_progress_messages(
            adapter=adapter,
            chat_id="chat-3",
            reply_to=None,
            metadata=None,
            cleanup_message_ids=[],
            is_current=lambda: True,
        )
    )

    runtime.record_callback_event(agent, "tool.started", "terminal", "pwd", {})
    await _finish(runtime, sender, agent)

    records = [
        json.loads(line)
        for line in event_path.read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["record_type"] == "progress.operation"
    assert records[-1]["record_type"] == "progress.snapshot"
    assert records[-1]["transaction"]["status"] == "completed"


def test_todo_projection_preserves_parent_group_and_executor():
    from gateway.run import _copy_agent_todo_progress

    store = TodoStore()
    store.bind_transaction("task-tree")
    store.write(
        [
            {"id": "release", "content": "Release", "status": "in_progress"},
            {
                "id": "review",
                "content": "Review",
                "status": "pending",
                "parent": "release",
                "executor": "codex",
            },
        ]
    )
    tracker = ProgressTracker("task-tree")
    agent = SimpleNamespace(
        _todo_store=store,
        _todo_transaction_id="task-tree",
    )

    _copy_agent_todo_progress(tracker, agent)

    snapshot = tracker.snapshot()
    assert snapshot.todo_items[1].parent_id == "release"
    assert snapshot.todo_items[1].executor == "codex"


def test_todo_projection_archives_terminal_state_from_another_transaction():
    from gateway.run import _copy_agent_todo_progress

    store = TodoStore()
    store.bind_transaction("task-old")
    store.write(
        [{"id": "old", "content": "Old work", "status": "completed"}]
    )
    store.mark_lifecycle("completed")
    tracker = ProgressTracker("task-new")
    agent = SimpleNamespace(
        _todo_store=store,
        _todo_transaction_id="task-new",
    )

    _copy_agent_todo_progress(tracker, agent)

    snapshot = tracker.snapshot()
    assert snapshot.todo_items == ()
    assert snapshot.todo_lifecycle is not None
    assert snapshot.todo_lifecycle.state == "archived"
