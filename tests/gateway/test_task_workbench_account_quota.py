"""Account usage must reach the live Workbench, not just renderer fixtures."""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import queue
import threading
from types import SimpleNamespace

import pytest

from agent import account_usage
from agent.account_usage import AccountUsageSnapshot, AccountUsageWindow
from gateway.platforms.base import SendResult
from gateway.progress.runtime import TaskWorkbenchRuntime


def _runtime(language="zh"):
    return TaskWorkbenchRuntime(
        transaction_id="quota-test",
        progress_queue=queue.Queue(),
        config={"mode": "feishu_card", "language": language, "persist_events": False},
        platform="feishu",
        message="Check usage",
        history=[],
    )


def _agent(provider: str | None = "openai-codex"):
    return SimpleNamespace(
        model="test/model", provider=provider,
        base_url="https://usage.invalid", api_key="fixture-" + "credential",
    )


def _usage(provider="openai-codex"):
    return AccountUsageSnapshot(
        provider=provider, source="usage_api",
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        windows=(AccountUsageWindow(label="Session", used_percent=30),),
    )


class _CardCapture:
    def __init__(self):
        self.sent = []
        self.patched = []
        self.first_card = asyncio.Event()
        self.quota_card = asyncio.Event()

    async def send_interactive_card(self, chat_id, card, **kwargs):
        self.sent.append(card)
        self.first_card.set()
        return SendResult(success=True, message_id="quota-card")

    async def patch_interactive_card(self, chat_id, message_id, card, finalize=False):
        self.patched.append((message_id, card, finalize))
        if "💳" in json.dumps(card, ensure_ascii=False):
            self.quota_card.set()
        return SendResult(success=True, message_id=message_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai-codex", "anthropic", "openrouter"])
@pytest.mark.parametrize("language, heading", [("zh", "账户额度"), ("en", "Account Quota")])
async def test_quota_fetch_nonblocking_patches_same_card_once(
    monkeypatch, provider, language, heading,
):
    runtime = _runtime(language)
    runtime.edit_interval = 0
    agent = _agent(provider)
    adapter = _CardCapture()
    started, release = threading.Event(), threading.Event()
    workers, calls = [], []
    profile = ContextVar("quota_profile", default="wrong-profile")
    profile.set("test-profile")

    def fetch(selected, *, base_url=None, api_key=None):
        workers.append(threading.current_thread())
        calls.append((selected, base_url, api_key, profile.get()))
        started.set()
        assert release.wait(5), "test did not release quota provider"
        return _usage(provider)

    monkeypatch.setattr(account_usage, "fetch_account_usage", fetch)
    sender = asyncio.create_task(runtime.send_progress_messages(
        adapter=adapter, chat_id="chat", reply_to=None, metadata=None,
        cleanup_message_ids=[], is_current=lambda: True,
    ))
    try:
        # Gateway callbacks originate on a worker; no event loop is running there.
        await asyncio.wait_for(asyncio.to_thread(
            runtime.record_callback_event, agent, "tool.started", "terminal", "check", {},
        ), 3)
        assert await asyncio.to_thread(started.wait, 2), "quota query was never scheduled"
        await asyncio.wait_for(adapter.first_card.wait(), 3)
        assert "💳" not in json.dumps(adapter.sent[0], ensure_ascii=False)
        # Concurrent callbacks must not create duplicate account requests.
        await asyncio.gather(*(asyncio.to_thread(runtime.refresh_from_agent, agent) for _ in range(8)))
        release.set()
        await asyncio.wait_for(adapter.quota_card.wait(), 3)
        assert calls == [(provider, agent.base_url, agent.api_key, "test-profile")]
        assert len(adapter.sent) == 1
        assert {mid for mid, _, _ in adapter.patched} == {"quota-card"}
        rendered = json.dumps(adapter.patched[-1][1], ensure_ascii=False)
        assert heading in rendered
        assert "70% remaining" in rendered
        assert agent.api_key not in rendered
        assert agent.base_url not in rendered
        await runtime.finalize(agent, timeout=3)
        assert adapter.patched[-1][2] is True
        assert "💳" in json.dumps(adapter.patched[-1][1], ensure_ascii=False)
    finally:
        release.set()
        for worker in workers:
            await asyncio.to_thread(worker.join, 3)
            assert not worker.is_alive()
        sender.cancel()
        with pytest.raises(asyncio.CancelledError):
            await sender


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["none", "error", "late"])
async def test_quota_failure_or_late_result_does_not_block_or_reopen_final_card(
    monkeypatch, caplog, outcome,
):
    runtime, agent = _runtime(), _agent()
    started, release = threading.Event(), threading.Event()
    workers, calls = [], []
    private_error = "private-provider-error-detail"

    def fetch(*args, **kwargs):
        workers.append(threading.current_thread())
        calls.append(1)
        started.set()
        assert release.wait(5)
        if outcome == "error":
            raise RuntimeError(private_error)
        return _usage() if outcome == "late" else None

    monkeypatch.setattr(account_usage, "fetch_account_usage", fetch)
    try:
        runtime.refresh_from_agent(agent)
        assert await asyncio.to_thread(started.wait, 2), "quota query was never scheduled"
        if outcome != "late":
            release.set()
            await asyncio.to_thread(workers[0].join, 3)
        await asyncio.wait_for(runtime.finalize(agent, visible=False), 3)
        final = runtime.tracker.snapshot()
        queued = runtime.progress_queue.qsize()
        release.set()
        await asyncio.to_thread(workers[0].join, 3)
        runtime.refresh_from_agent(agent)
        assert calls == [1]
        assert runtime.tracker.snapshot().account_limit_lines == ()
        assert runtime.tracker.snapshot().status == final.status == "completed"
        assert runtime.progress_queue.qsize() == queued
        assert private_error not in caplog.text
    finally:
        release.set()
        for worker in workers:
            await asyncio.to_thread(worker.join, 3)
            assert not worker.is_alive()


@pytest.mark.parametrize("mode, platform", [
    ("text", "telegram"), ("text", "feishu"), ("feishu_card", "discord"),
])
def test_text_workbench_never_queries_invisible_account_quota(monkeypatch, mode, platform):
    from unittest.mock import Mock

    runtime = TaskWorkbenchRuntime(
        transaction_id="text-quota-test", progress_queue=queue.Queue(),
        config={"mode": mode, "persist_events": False},
        platform=platform, message="check", history=[],
    )
    fetch = Mock(return_value=None)
    threads = []
    real_thread = threading.Thread

    def capture_thread(*args, **kwargs):
        worker = real_thread(*args, **kwargs)
        threads.append(worker)
        return worker

    monkeypatch.setattr(account_usage, "fetch_account_usage", fetch)
    monkeypatch.setattr(threading, "Thread", capture_thread)
    runtime.refresh_from_agent(_agent())
    for worker in threads:
        worker.join(3)
        assert not worker.is_alive()
    fetch.assert_not_called()


def test_finalized_or_unsupported_workbench_does_not_fetch(monkeypatch):
    from unittest.mock import Mock

    fetch = Mock(return_value=_usage())
    monkeypatch.setattr(account_usage, "fetch_account_usage", fetch)
    for provider in (None, "custom", "unsupported"):
        runtime = _runtime()
        runtime.refresh_from_agent(_agent(provider))
        assert runtime.tracker.snapshot().account_limit_lines == ()
    runtime = _runtime()
    asyncio.run(runtime.finalize(_agent(), visible=False))
    runtime.refresh_from_agent(_agent())
    fetch.assert_not_called()
