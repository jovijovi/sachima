"""Tests for topic-aware gateway progress updates."""

import asyncio
import importlib
import json
import sys
import time
import types
from types import SimpleNamespace

import pytest

from gateway.config import Platform, PlatformConfig, StreamingConfig
from gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType, SendResult
from gateway.session import SessionSource


class ProgressCaptureAdapter(BasePlatformAdapter):
    def __init__(self, platform=Platform.TELEGRAM):
        super().__init__(PlatformConfig(enabled=True, token="***"), platform)
        self.sent = []
        self.edits = []
        self.typing = []

    async def connect(self) -> bool:
        return True

    async def disconnect(self) -> None:
        return None

    async def send(self, chat_id, content, reply_to=None, metadata=None) -> SendResult:
        self.sent.append(
            {
                "chat_id": chat_id,
                "content": content,
                "reply_to": reply_to,
                "metadata": metadata,
            }
        )
        return SendResult(success=True, message_id="progress-1")

    async def edit_message(self, chat_id, message_id, content) -> SendResult:
        self.edits.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "content": content,
            }
        )
        return SendResult(success=True, message_id=message_id)

    async def send_typing(self, chat_id, metadata=None) -> None:
        self.typing.append({"chat_id": chat_id, "metadata": metadata})

    async def stop_typing(self, chat_id) -> None:
        self.typing.append({"chat_id": chat_id, "metadata": {"stopped": True}})

    async def get_chat_info(self, chat_id: str):
        return {"id": chat_id}


class SmallLimitProgressAdapter(ProgressCaptureAdapter):
    """Adapter with a tiny platform limit to exercise progress rollover."""

    MAX_MESSAGE_LENGTH = 180

    def __init__(self, platform=Platform.TELEGRAM):
        super().__init__(platform=platform)
        self._next_id = 0
        self.oversized_edits = []
        self.oversized_sends = []

    def _mint_id(self):
        self._next_id += 1
        return f"progress-{self._next_id}"

    async def send(self, chat_id, content, reply_to=None, metadata=None) -> SendResult:
        if len(content) > self.MAX_MESSAGE_LENGTH:
            self.oversized_sends.append(content)
        self.sent.append(
            {
                "chat_id": chat_id,
                "content": content,
                "reply_to": reply_to,
                "metadata": metadata,
            }
        )
        return SendResult(success=True, message_id=self._mint_id())

    async def edit_message(self, chat_id, message_id, content) -> SendResult:
        if len(content) > self.MAX_MESSAGE_LENGTH:
            self.oversized_edits.append(content)
        self.edits.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "content": content,
            }
        )
        return SendResult(success=True, message_id=message_id)


class MetadataEditProgressCaptureAdapter(ProgressCaptureAdapter):
    async def edit_message(
        self, chat_id, message_id, content, *, finalize: bool = False, metadata=None
    ) -> SendResult:
        self.edits.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "content": content,
                "metadata": metadata,
            }
        )
        return SendResult(success=True, message_id=message_id)


class NonEditingProgressCaptureAdapter(ProgressCaptureAdapter):
    SUPPORTS_MESSAGE_EDITING = False

    async def edit_message(self, chat_id, message_id, content) -> SendResult:
        raise AssertionError("non-editable adapters should not receive edit_message calls")


class FinalProgressEditFailureAdapter(ProgressCaptureAdapter):
    """Adapter that rejects the final Completed task-tracker edit."""

    async def edit_message(self, chat_id, message_id, content) -> SendResult:
        self.edits.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "content": content,
            }
        )
        if "**Status:** Completed" in content:
            return SendResult(success=False, error="update failed")
        return SendResult(success=True, message_id=message_id)


class CancellingTaskDropsFinalAdapter(ProgressCaptureAdapter):
    """Adapter where edits from a cancelling progress task are not visibly applied."""

    def __init__(self, platform=Platform.TELEGRAM):
        super().__init__(platform=platform)
        self.visible_completed_updates = []
        self.dropped_completed_updates = []

    async def edit_message(self, chat_id, message_id, content) -> SendResult:
        self.edits.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "content": content,
            }
        )
        if "**Status:** Completed" in content:
            task = asyncio.current_task()
            if task is not None and task.cancelling():
                self.dropped_completed_updates.append(content)
                return SendResult(success=True, message_id=message_id)
            self.visible_completed_updates.append(content)
        return SendResult(success=True, message_id=message_id)


class SlowInFlightRunningUpdateAdapter(CancellingTaskDropsFinalAdapter):
    """Adapter with a slow pre-completion Running update in flight during cleanup."""

    def __init__(self, platform=Platform.TELEGRAM):
        super().__init__(platform=platform)
        self.delayed_running_send = False
        self.delayed_running_edit = False

    async def send(self, chat_id, content, reply_to=None, metadata=None) -> SendResult:
        if "**Status:** Running" in content and not self.delayed_running_send:
            self.delayed_running_send = True
            await asyncio.sleep(1.0)
        return await super().send(chat_id, content, reply_to=reply_to, metadata=metadata)

    async def edit_message(self, chat_id, message_id, content) -> SendResult:
        if "**Status:** Running" in content and not self.delayed_running_edit:
            self.delayed_running_edit = True
            await asyncio.sleep(0.5)
        return await super().edit_message(chat_id, message_id, content)


class FeishuProgressCardCaptureAdapter(ProgressCaptureAdapter):
    def __init__(self, platform=Platform.FEISHU):
        super().__init__(platform=platform)
        self.cards_sent = []
        self.cards_patched = []

    async def send_interactive_card(self, chat_id, card, reply_to=None, metadata=None) -> SendResult:
        self.cards_sent.append({"chat_id": chat_id, "card": card, "reply_to": reply_to, "metadata": metadata})
        return SendResult(success=True, message_id="om_card_1")

    async def patch_interactive_card(self, chat_id, message_id, card, finalize=False) -> SendResult:
        self.cards_patched.append(
            {"chat_id": chat_id, "message_id": message_id, "card": card, "finalize": finalize}
        )
        return SendResult(success=True, message_id=message_id)


class FeishuFinalPatchFailureAdapter(FeishuProgressCardCaptureAdapter):
    async def patch_interactive_card(self, chat_id, message_id, card, finalize=False) -> SendResult:
        self.cards_patched.append(
            {"chat_id": chat_id, "message_id": message_id, "card": card, "finalize": finalize}
        )
        if finalize:
            return SendResult(success=False, error="patch failed")
        return SendResult(success=True, message_id=message_id)


class FeishuInitialCardFailureAdapter(FeishuProgressCardCaptureAdapter):
    async def send_interactive_card(self, chat_id, card, reply_to=None, metadata=None) -> SendResult:
        self.cards_sent.append({"chat_id": chat_id, "card": card, "reply_to": reply_to, "metadata": metadata})
        return SendResult(success=False, error="temporary card send failure")

    async def patch_interactive_card(self, chat_id, message_id, card, finalize=False) -> SendResult:
        raise AssertionError("initial card send failure must not patch a missing card")


class FeishuPatchFailureAdapter(FeishuProgressCardCaptureAdapter):
    async def patch_interactive_card(self, chat_id, message_id, card, finalize=False) -> SendResult:
        self.cards_patched.append(
            {"chat_id": chat_id, "message_id": message_id, "card": card, "finalize": finalize}
        )
        return SendResult(success=False, error="temporary card patch failure")


class FeishuRetryableIntermediatePatchFailureAdapter(FeishuProgressCardCaptureAdapter):
    async def patch_interactive_card(self, chat_id, message_id, card, finalize=False) -> SendResult:
        self.cards_patched.append(
            {"chat_id": chat_id, "message_id": message_id, "card": card, "finalize": finalize}
        )
        if not finalize and not any(not call["finalize"] for call in self.cards_patched[:-1]):
            return SendResult(
                success=False,
                error="[230020] update the single messages too frequently",
                retryable=True,
            )
        return SendResult(success=True, message_id=message_id)


def _assert_compact_card_failure_notice_only(text: str) -> None:
    assert "任务卡片更新失败" in text
    assert "Transaction" not in text
    assert "Recent operations" not in text
    assert "Context" not in text
    assert "read_file" not in text
    assert "search_files" not in text
    assert "gateway/run.py" not in text
    assert "tool_progress" not in text


class FakeAgent:
    def __init__(self, **kwargs):
        # Capture anything passed via kwargs (older code path) but don't
        # freeze it — production now assigns tool_progress_callback after
        # construction (see gateway/run.py around the agent-cache hit),
        # so we must read it at call time, not at init.
        self.tool_progress_callback = kwargs.get("tool_progress_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None):
        cb = self.tool_progress_callback
        if cb is not None:
            cb("tool.started", "terminal", "pwd", {})
            time.sleep(0.35)
            cb("tool.started", "browser_navigate", "https://example.com", {})
            time.sleep(0.35)
        return {
            "final_response": "done",
            "messages": [],
            "api_calls": 1,
        }


class LongPreviewAgent:
    """Agent that emits a tool call with a very long preview string."""
    LONG_CMD = "cd /home/teknium/.hermes/hermes-agent/.worktrees/hermes-d8860339 && source .venv/bin/activate && python -m pytest tests/gateway/test_run_progress_topics.py -n0 -q"

    def __init__(self, **kwargs):
        self.tool_progress_callback = kwargs.get("tool_progress_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None):
        self.tool_progress_callback("tool.started", "terminal", self.LONG_CMD, {})
        time.sleep(0.35)
        return {
            "final_response": "done",
            "messages": [],
            "api_calls": 1,
        }


class DelayedProgressAgent:
    def __init__(self, **kwargs):
        self.tool_progress_callback = kwargs.get("tool_progress_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None):
        self.tool_progress_callback("tool.started", "terminal", "first command", {})
        time.sleep(0.45)
        self.tool_progress_callback("tool.started", "terminal", "second command", {})
        time.sleep(0.1)
        return {
            "final_response": "done",
            "messages": [],
            "api_calls": 1,
        }


class ManyProgressLinesAgent:
    """Emits enough tool-progress lines to exceed a single platform bubble."""

    def __init__(self, **kwargs):
        self.tool_progress_callback = kwargs.get("tool_progress_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None):
        cb = self.tool_progress_callback
        assert cb is not None
        cb("tool.started", "terminal", "first-short", {})
        # Let the progress task create the first editable bubble, then enqueue
        # the rest quickly.  The cancellation drain must roll them into fresh
        # editable bubbles instead of trying to edit the first one past limit.
        time.sleep(0.35)
        for idx in range(1, 8):
            cb("tool.started", "terminal", f"overflow-line-{idx}-" + "x" * 45, {})
        time.sleep(0.1)
        return {
            "final_response": "done",
            "messages": [],
            "api_calls": 1,
        }


class DelayedInterimAgent:
    def __init__(self, **kwargs):
        self.interim_assistant_callback = kwargs.get("interim_assistant_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None):
        self.interim_assistant_callback("first interim")
        time.sleep(0.45)
        self.interim_assistant_callback("second interim")
        time.sleep(0.1)
        return {
            "final_response": "done",
            "messages": [],
            "api_calls": 1,
        }


def _make_runner(adapter):
    gateway_run = importlib.import_module("gateway.run")
    GatewayRunner = gateway_run.GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.adapters = {adapter.platform: adapter}
    runner._voice_mode = {}
    runner._prefill_messages = []
    runner._ephemeral_system_prompt = ""
    runner._reasoning_config = None
    runner._provider_routing = {}
    runner._fallback_model = None
    runner._session_db = None
    runner._running_agents = {}
    runner._session_run_generation = {}
    runner.hooks = SimpleNamespace(loaded_hooks=False)
    runner.config = SimpleNamespace(
        thread_sessions_per_user=False,
        group_sessions_per_user=False,
        stt_enabled=False,
    )
    return runner


@pytest.mark.asyncio
async def test_run_agent_progress_stays_in_originating_topic(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_TOOL_PROGRESS_MODE", "all")

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)

    fake_run_agent = types.ModuleType("run_agent")
    fake_run_agent.AIAgent = FakeAgent
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)
    import tools.terminal_tool  # noqa: F401 - register terminal emoji for this fake-agent test

    adapter = ProgressCaptureAdapter()
    runner = _make_runner(adapter)
    gateway_run = importlib.import_module("gateway.run")
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    monkeypatch.setattr(gateway_run, "_resolve_runtime_agent_kwargs", lambda: {"api_key": "fake"})
    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="-1001",
        chat_type="group",
        thread_id="17585",
    )

    result = await runner._run_agent(
        message="hello",
        context_prompt="",
        history=[],
        source=source,
        session_id="sess-1",
        session_key="agent:main:telegram:group:-1001:17585",
    )

    assert result["final_response"] == "done"
    assert adapter.sent == [
        {
            "chat_id": "-1001",
            "content": '💻 terminal: "pwd"',
            "reply_to": None,
            "metadata": {"thread_id": "17585"},
        }
    ]
    assert adapter.edits
    assert all(call["metadata"] == {"thread_id": "17585"} for call in adapter.typing)


@pytest.mark.asyncio
async def test_run_agent_progress_edits_keep_originating_topic_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_TOOL_PROGRESS_MODE", "all")

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)

    fake_run_agent = types.ModuleType("run_agent")
    fake_run_agent.AIAgent = FakeAgent
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)

    adapter = MetadataEditProgressCaptureAdapter()
    runner = _make_runner(adapter)
    gateway_run = importlib.import_module("gateway.run")
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    monkeypatch.setattr(gateway_run, "_resolve_runtime_agent_kwargs", lambda: {"api_key": "fake"})
    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="-1001",
        chat_type="group",
        thread_id="17585",
    )

    result = await runner._run_agent(
        message="hello",
        context_prompt="",
        history=[],
        source=source,
        session_id="sess-progress-edit-topic",
        session_key="agent:main:telegram:group:-1001:17585",
    )

    assert result["final_response"] == "done"
    assert adapter.edits
    assert all(call["metadata"] == {"thread_id": "17585"} for call in adapter.edits)


@pytest.mark.asyncio
async def test_run_agent_progress_does_not_use_event_message_id_for_telegram_dm(monkeypatch, tmp_path):
    """Telegram DM progress must not reuse event message id as thread metadata."""
    monkeypatch.setenv("HERMES_TOOL_PROGRESS_MODE", "all")

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)

    fake_run_agent = types.ModuleType("run_agent")
    fake_run_agent.AIAgent = FakeAgent
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)

    adapter = ProgressCaptureAdapter(platform=Platform.TELEGRAM)
    runner = _make_runner(adapter)
    gateway_run = importlib.import_module("gateway.run")
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    monkeypatch.setattr(gateway_run, "_resolve_runtime_agent_kwargs", lambda: {"api_key": "***"})

    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="12345",
        chat_type="dm",
        thread_id=None,
    )

    result = await runner._run_agent(
        message="hello",
        context_prompt="",
        history=[],
        source=source,
        session_id="sess-2",
        session_key="agent:main:telegram:dm:12345",
        event_message_id="777",
    )

    assert result["final_response"] == "done"
    assert adapter.sent
    assert adapter.sent[0]["metadata"] is None
    assert all(call["metadata"] is None for call in adapter.typing)


@pytest.mark.asyncio
async def test_run_agent_progress_uses_event_message_id_for_slack_dm(monkeypatch, tmp_path):
    """Slack DM progress should keep event ts fallback threading."""
    monkeypatch.setenv("HERMES_TOOL_PROGRESS_MODE", "all")
    # Since PR #8006, Slack's built-in display tier sets tool_progress="off"
    # by default. Override via config so this test still exercises the
    # progress-callback path the Slack DM event_message_id threading depends on.
    import yaml
    (tmp_path / "config.yaml").write_text(
        yaml.dump({"display": {"platforms": {"slack": {"tool_progress": "all"}}}}),
        encoding="utf-8",
    )

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)

    fake_run_agent = types.ModuleType("run_agent")
    fake_run_agent.AIAgent = FakeAgent
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)

    adapter = ProgressCaptureAdapter(platform=Platform.SLACK)
    runner = _make_runner(adapter)
    gateway_run = importlib.import_module("gateway.run")
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    monkeypatch.setattr(gateway_run, "_resolve_runtime_agent_kwargs", lambda: {"api_key": "***"})

    source = SessionSource(
        platform=Platform.SLACK,
        chat_id="D123",
        chat_type="dm",
        thread_id=None,
    )

    result = await runner._run_agent(
        message="hello",
        context_prompt="",
        history=[],
        source=source,
        session_id="sess-3",
        session_key="agent:main:slack:dm:D123",
        event_message_id="1234567890.000001",
    )

    assert result["final_response"] == "done"
    assert adapter.sent
    assert adapter.sent[0]["metadata"] == {"thread_id": "1234567890.000001"}
    assert all(call["metadata"] == {"thread_id": "1234567890.000001"} for call in adapter.typing)


@pytest.mark.asyncio
async def test_run_agent_feishu_progress_replies_inside_existing_thread(monkeypatch, tmp_path):
    """Feishu needs reply_to plus reply_in_thread metadata for topic-scoped progress."""
    monkeypatch.setenv("HERMES_TOOL_PROGRESS_MODE", "all")

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)

    fake_run_agent = types.ModuleType("run_agent")
    fake_run_agent.AIAgent = FakeAgent
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)

    adapter = ProgressCaptureAdapter(platform=Platform.FEISHU)
    runner = _make_runner(adapter)
    gateway_run = importlib.import_module("gateway.run")
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    monkeypatch.setattr(gateway_run, "_resolve_runtime_agent_kwargs", lambda: {"api_key": "***"})

    source = SessionSource(
        platform=Platform.FEISHU,
        chat_id="oc_chat",
        chat_type="group",
        thread_id="topic_17585",
    )

    result = await runner._run_agent(
        message="hello",
        context_prompt="",
        history=[],
        source=source,
        session_id="sess-feishu-progress",
        session_key="agent:main:feishu:group:oc_chat:topic_17585",
        event_message_id="om_triggering_user_message",
    )

    assert result["final_response"] == "done"
    assert adapter.sent
    assert adapter.sent[0]["reply_to"] == "om_triggering_user_message"
    assert adapter.sent[0]["metadata"] == {"thread_id": "topic_17585"}
    assert adapter.edits
    assert adapter.edits[0]["message_id"] == "progress-1"


# ---------------------------------------------------------------------------
# Preview truncation tests (all/new mode respects tool_preview_length)
# ---------------------------------------------------------------------------


def _run_long_preview_helper(monkeypatch, tmp_path, preview_length=0):
    """Shared setup for long-preview truncation tests.

    Returns (adapter, result) after running the agent with LongPreviewAgent.
    ``preview_length`` controls display.tool_preview_length in the config file
    that _run_agent reads — so the gateway picks it up the same way production does.
    """
    import asyncio
    import yaml

    monkeypatch.setenv("HERMES_TOOL_PROGRESS_MODE", "all")

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)

    fake_run_agent = types.ModuleType("run_agent")
    fake_run_agent.AIAgent = LongPreviewAgent
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)

    # Write config.yaml so _run_agent picks up tool_preview_length
    config = {"display": {"tool_preview_length": preview_length}}
    (tmp_path / "config.yaml").write_text(yaml.dump(config), encoding="utf-8")

    adapter = ProgressCaptureAdapter()
    runner = _make_runner(adapter)
    gateway_run = importlib.import_module("gateway.run")
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    monkeypatch.setattr(gateway_run, "_resolve_runtime_agent_kwargs", lambda: {"api_key": "***"})

    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="12345",
        chat_type="dm",
        thread_id=None,
    )

    result = asyncio.get_event_loop().run_until_complete(
        runner._run_agent(
            message="hello",
            context_prompt="",
            history=[],
            source=source,
            session_id="sess-trunc",
            session_key="agent:main:telegram:dm:12345",
        )
    )
    return adapter, result


def test_all_mode_default_truncation_40_chars(monkeypatch, tmp_path):
    """When tool_preview_length is 0 (default), all/new mode truncates to 40 chars."""
    adapter, result = _run_long_preview_helper(monkeypatch, tmp_path, preview_length=0)
    assert result["final_response"] == "done"
    assert adapter.sent
    content = adapter.sent[0]["content"]
    # The long command should be truncated — total preview <= 40 chars
    assert "..." in content
    # Extract the preview part between quotes
    import re
    match = re.search(r'"(.+)"', content)
    assert match, f"No quoted preview found in: {content}"
    preview_text = match.group(1)
    assert len(preview_text) <= 40, f"Preview too long ({len(preview_text)}): {preview_text}"


def test_all_mode_respects_custom_preview_length(monkeypatch, tmp_path):
    """When tool_preview_length is explicitly set (e.g. 120), all/new mode uses that."""
    adapter, result = _run_long_preview_helper(monkeypatch, tmp_path, preview_length=120)
    assert result["final_response"] == "done"
    assert adapter.sent
    content = adapter.sent[0]["content"]
    # With 120-char cap, the command (165 chars) should still be truncated but longer
    import re
    match = re.search(r'"(.+)"', content)
    assert match, f"No quoted preview found in: {content}"
    preview_text = match.group(1)
    # Should be longer than the 40-char default
    assert len(preview_text) > 40, f"Preview suspiciously short ({len(preview_text)}): {preview_text}"
    # But still capped at 120
    assert len(preview_text) <= 120, f"Preview too long ({len(preview_text)}): {preview_text}"


def test_all_mode_no_truncation_when_preview_fits(monkeypatch, tmp_path):
    """Short previews (under the cap) are not truncated."""
    # Set a generous cap — the LongPreviewAgent's command is ~165 chars
    adapter, result = _run_long_preview_helper(monkeypatch, tmp_path, preview_length=200)
    assert result["final_response"] == "done"
    assert adapter.sent
    content = adapter.sent[0]["content"]
    # With a 200-char cap, the 165-char command should NOT be truncated
    assert "..." not in content, f"Preview was truncated when it shouldn't be: {content}"


class CommentaryAgent:
    def __init__(self, **kwargs):
        self.tool_progress_callback = kwargs.get("tool_progress_callback")
        self.interim_assistant_callback = kwargs.get("interim_assistant_callback")
        self.stream_delta_callback = kwargs.get("stream_delta_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None):
        if self.interim_assistant_callback:
            self.interim_assistant_callback("I'll inspect the repo first.", already_streamed=False)
        time.sleep(0.1)
        if self.stream_delta_callback:
            self.stream_delta_callback("done")
        return {
            "final_response": "done",
            "messages": [],
            "api_calls": 1,
        }


class PreviewedResponseAgent:
    def __init__(self, **kwargs):
        self.interim_assistant_callback = kwargs.get("interim_assistant_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None):
        if self.interim_assistant_callback:
            self.interim_assistant_callback("You're welcome.", already_streamed=False)
        return {
            "final_response": "You're welcome.",
            "response_previewed": True,
            "messages": [],
            "api_calls": 1,
        }


class StreamingRefineAgent:
    def __init__(self, **kwargs):
        self.stream_delta_callback = kwargs.get("stream_delta_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None):
        if self.stream_delta_callback:
            self.stream_delta_callback("Continuing to refine:")
        time.sleep(0.1)
        if self.stream_delta_callback:
            self.stream_delta_callback(" Final answer.")
        return {
            "final_response": "Continuing to refine: Final answer.",
            "response_previewed": True,
            "messages": [],
            "api_calls": 1,
        }


class QueuedCommentaryAgent:
    calls = 0

    def __init__(self, **kwargs):
        self.interim_assistant_callback = kwargs.get("interim_assistant_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None):
        type(self).calls += 1
        if type(self).calls == 1 and self.interim_assistant_callback:
            self.interim_assistant_callback("I'll inspect the repo first.", already_streamed=False)
        return {
            "final_response": f"final response {type(self).calls}",
            "messages": [],
            "api_calls": 1,
        }


class BackgroundReviewAgent:
    def __init__(self, **kwargs):
        self.background_review_callback = kwargs.get("background_review_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None):
        if self.background_review_callback:
            self.background_review_callback("💾 Skill 'prospect-scanner' created.")
        return {
            "final_response": "done",
            "messages": [],
            "api_calls": 1,
        }


class VerboseAgent:
    """Agent that emits a tool call with args whose JSON exceeds 200 chars."""
    LONG_CODE = "x" * 300

    def __init__(self, **kwargs):
        self.tool_progress_callback = kwargs.get("tool_progress_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None):
        self.tool_progress_callback(
            "tool.started", "execute_code", None,
            {"code": self.LONG_CODE},
        )
        time.sleep(0.35)
        return {
            "final_response": "done",
            "messages": [],
            "api_calls": 1,
        }


class TransactionPanelAgent:
    def __init__(self, **kwargs):
        self.tool_progress_callback = kwargs.get("tool_progress_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None):
        self.tool_progress_callback("tool.started", "read_file", "gateway/run.py", {"path": "gateway/run.py"})
        time.sleep(0.35)
        self.tool_progress_callback("tool.started", "search_files", "tool_progress", {"pattern": "tool_progress"})
        time.sleep(0.35)
        return {
            "final_response": "done",
            "messages": [],
            "api_calls": 1,
        }


class BurstTaskTrackerProgressAgent:
    def __init__(self, **kwargs):
        self.tool_progress_callback = kwargs.get("tool_progress_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None):
        for idx in range(12):
            self.tool_progress_callback(
                "tool.started",
                "read_file",
                f"gateway/run.py:{idx}",
                {"path": "gateway/run.py", "idx": idx},
            )
        time.sleep(2.3)
        return {
            "final_response": "done",
            "messages": [],
            "api_calls": 1,
        }


class RetryablePatchCatchupAgent:
    def __init__(self, **kwargs):
        self.tool_progress_callback = kwargs.get("tool_progress_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None):
        self.tool_progress_callback("tool.started", "read_file", "gateway/run.py", {"path": "gateway/run.py"})
        time.sleep(2.3)
        self.tool_progress_callback("tool.started", "search_files", "tool_progress", {"pattern": "tool_progress"})
        time.sleep(0.2)
        return {
            "final_response": "done",
            "messages": [],
            "api_calls": 1,
        }


class ContextUsagePanelAgent(TransactionPanelAgent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.context_compressor = SimpleNamespace(
            last_prompt_tokens=40_960,
            peak_prompt_tokens=65_536,
            context_length=128_000,
            threshold_tokens=102_400,
            compression_count=2,
        )


class SingleProgressFastReturnAgent:
    def __init__(self, **kwargs):
        self.tool_progress_callback = kwargs.get("tool_progress_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None):
        self.tool_progress_callback("tool.started", "read_file", "gateway/run.py", {"path": "gateway/run.py"})
        time.sleep(0.4)
        return {
            "final_response": "done",
            "messages": [],
            "api_calls": 1,
        }


class OptionalProgressAgent:
    def __init__(self, **kwargs):
        self.tool_progress_callback = kwargs.get("tool_progress_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None):
        if self.tool_progress_callback:
            self.tool_progress_callback("tool.started", "read_file", "gateway/run.py", {"path": "gateway/run.py"})
            time.sleep(0.35)
            self.tool_progress_callback("tool.started", "search_files", "tool_progress", {"pattern": "tool_progress"})
        time.sleep(0.35)
        return {
            "final_response": "done",
            "messages": [],
            "api_calls": 1,
        }


class PersistentProgressAgent:
    def __init__(self, **kwargs):
        self.tool_progress_callback = kwargs.get("tool_progress_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None):
        sensitive_value = "persist-" + "secret"
        self.tool_progress_callback(
            "tool.started",
            "terminal",
            "curl https://example.invalid/?access_token=" + sensitive_value + "&ok=yes",
            {"api_key": sensitive_value, "command": "pytest"},
        )
        time.sleep(0.2)
        self.tool_progress_callback(
            "tool.completed",
            "terminal",
            "done",
            {},
            duration=0.25,
            is_error=False,
        )
        time.sleep(0.2)
        return {
            "final_response": "done",
            "messages": [],
            "api_calls": 1,
        }


class SubagentProgressAgent:
    def __init__(self, **kwargs):
        self.tool_progress_callback = kwargs.get("tool_progress_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None):
        self.tool_progress_callback("subagent.start", preview="Inspect progress tests", subagent_id="sub-1")
        time.sleep(0.2)
        self.tool_progress_callback(
            "subagent.tool",
            "search_files",
            "test_progress",
            {"pattern": "test_progress"},
            subagent_id="sub-1",
            goal="Inspect progress tests",
        )
        time.sleep(0.2)
        self.tool_progress_callback("subagent.complete", preview="Done", subagent_id="sub-1")
        time.sleep(0.2)
        return {
            "final_response": "done",
            "messages": [],
            "api_calls": 1,
        }


async def _run_with_agent(
    monkeypatch,
    tmp_path,
    agent_cls,
    *,
    session_id,
    pending_text=None,
    message="hello",
    config_data=None,
    platform=Platform.TELEGRAM,
    chat_id="-1001",
    chat_type="group",
    thread_id="17585",
    adapter_cls=ProgressCaptureAdapter,
):
    if config_data:
        import yaml

        (tmp_path / "config.yaml").write_text(yaml.dump(config_data), encoding="utf-8")

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)

    fake_run_agent = types.ModuleType("run_agent")
    fake_run_agent.AIAgent = agent_cls
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)

    adapter = adapter_cls(platform=platform)
    runner = _make_runner(adapter)
    gateway_run = importlib.import_module("gateway.run")
    if config_data and "streaming" in config_data:
        runner.config.streaming = StreamingConfig.from_dict(config_data["streaming"])
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    monkeypatch.setattr(gateway_run, "_resolve_runtime_agent_kwargs", lambda: {"api_key": "***"})
    source = SessionSource(
        platform=platform,
        chat_id=chat_id,
        chat_type=chat_type,
        thread_id=thread_id,
    )
    session_key = f"agent:main:{platform.value}:{chat_type}:{chat_id}"
    if thread_id:
        session_key = f"{session_key}:{thread_id}"
    if pending_text is not None:
        adapter._pending_messages[session_key] = MessageEvent(
            text=pending_text,
            message_type=MessageType.TEXT,
            source=source,
            message_id="queued-1",
        )

    result = await runner._run_agent(
        message=message,
        context_prompt="",
        history=[],
        source=source,
        session_id=session_id,
        session_key=session_key,
    )
    return adapter, result


@pytest.mark.asyncio
async def test_run_agent_rolls_progress_bubble_before_platform_limit(monkeypatch, tmp_path):
    """Tool progress should start a second editable bubble before Telegram's limit.

    Regression: once the first progress bubble grew past the platform limit,
    the gateway kept trying to edit that same oversized full transcript.  The
    Telegram adapter then split-and-sent a fresh continuation on every update,
    causing a noisy trail of one-line messages instead of a new editable bubble.
    """
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        ManyProgressLinesAgent,
        session_id="sess-progress-overflow-rollover",
        config_data={
            "display": {
                "tool_progress": "all",
                "interim_assistant_messages": False,
                "tool_preview_length": 60,
            }
        },
        adapter_cls=SmallLimitProgressAdapter,
    )

    assert result["final_response"] == "done"
    assert isinstance(adapter, SmallLimitProgressAdapter)
    assert len(adapter.sent) >= 2, "expected a fresh progress bubble after the first filled"
    assert adapter.oversized_sends == []
    assert adapter.oversized_edits == []
    all_bubbles = [call["content"] for call in adapter.sent + adapter.edits]
    assert all(len(text) <= adapter.MAX_MESSAGE_LENGTH for text in all_bubbles)


@pytest.mark.asyncio
async def test_run_agent_surfaces_real_interim_commentary(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        CommentaryAgent,
        session_id="sess-commentary",
        config_data={"display": {"interim_assistant_messages": True}},
    )

    assert result.get("already_sent") is not True
    assert any(call["content"] == "I'll inspect the repo first." for call in adapter.sent)


@pytest.mark.asyncio
async def test_run_agent_surfaces_interim_commentary_by_default(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        CommentaryAgent,
        session_id="sess-commentary-default-on",
    )

    assert any(call["content"] == "I'll inspect the repo first." for call in adapter.sent)


@pytest.mark.asyncio
async def test_run_agent_suppresses_interim_commentary_when_disabled(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        CommentaryAgent,
        session_id="sess-commentary-disabled",
        config_data={"display": {"interim_assistant_messages": False}},
    )

    assert result.get("already_sent") is not True
    assert not any(call["content"] == "I'll inspect the repo first." for call in adapter.sent)


@pytest.mark.asyncio
async def test_run_agent_tool_progress_does_not_control_interim_commentary(monkeypatch, tmp_path):
    """tool_progress=all with interim_assistant_messages=false should not surface commentary."""
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        CommentaryAgent,
        session_id="sess-commentary-tool-progress",
        config_data={"display": {"tool_progress": "all", "interim_assistant_messages": False}},
    )

    assert result.get("already_sent") is not True
    assert not any(call["content"] == "I'll inspect the repo first." for call in adapter.sent)


@pytest.mark.asyncio
async def test_run_agent_streaming_does_not_enable_completed_interim_commentary(
    monkeypatch, tmp_path
):
    """Streaming alone with interim_assistant_messages=false should not surface commentary."""
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        CommentaryAgent,
        session_id="sess-commentary-streaming",
        config_data={
            "display": {"tool_progress": "off", "interim_assistant_messages": False},
            "streaming": {"enabled": True},
        },
    )

    assert result.get("already_sent") is True
    assert not any(call["content"] == "I'll inspect the repo first." for call in adapter.sent)


@pytest.mark.asyncio
async def test_display_streaming_does_not_enable_gateway_streaming(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        CommentaryAgent,
        session_id="sess-display-streaming-cli-only",
        config_data={
            "display": {
                "streaming": True,
                "interim_assistant_messages": True,
            },
            "streaming": {"enabled": False},
        },
    )

    assert result.get("already_sent") is not True
    assert adapter.edits == []
    assert [call["content"] for call in adapter.sent] == ["I'll inspect the repo first."]


@pytest.mark.asyncio
async def test_run_agent_interim_commentary_works_with_tool_progress_off(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        CommentaryAgent,
        session_id="sess-commentary-explicit-on",
        config_data={
            "display": {
                "tool_progress": "off",
                "interim_assistant_messages": True,
            },
        },
    )

    assert result.get("already_sent") is not True
    assert any(call["content"] == "I'll inspect the repo first." for call in adapter.sent)


@pytest.mark.asyncio
async def test_run_agent_bluebubbles_uses_commentary_send_path_for_quick_replies(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        CommentaryAgent,
        session_id="sess-bluebubbles-commentary",
        config_data={"display": {"interim_assistant_messages": True}},
        platform=Platform.BLUEBUBBLES,
        chat_id="iMessage;-;user@example.com",
        chat_type="dm",
        thread_id=None,
        adapter_cls=NonEditingProgressCaptureAdapter,
    )

    assert result.get("already_sent") is not True
    assert [call["content"] for call in adapter.sent] == ["I'll inspect the repo first."]
    assert adapter.edits == []


@pytest.mark.asyncio
async def test_run_agent_previewed_final_marks_already_sent(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        PreviewedResponseAgent,
        session_id="sess-previewed",
        config_data={"display": {"interim_assistant_messages": True}},
    )

    assert result.get("already_sent") is True
    assert result["delivery_state"]["final_text"] == {"sent": True, "reason": "response_previewed"}
    assert [call["content"] for call in adapter.sent] == ["You're welcome."]


@pytest.mark.asyncio
async def test_run_agent_matrix_streaming_omits_cursor(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        StreamingRefineAgent,
        session_id="sess-matrix-streaming",
        config_data={
            "display": {"tool_progress": "off", "interim_assistant_messages": False},
            "streaming": {"enabled": True, "edit_interval": 0.01, "buffer_threshold": 1},
        },
        platform=Platform.MATRIX,
        chat_id="!room:matrix.example.org",
        chat_type="group",
        thread_id="$thread",
    )

    assert result.get("already_sent") is True
    assert result["delivery_state"]["final_text"] == {"sent": True, "reason": "stream_final_response"}
    all_text = [call["content"] for call in adapter.sent] + [call["content"] for call in adapter.edits]
    assert all_text, "expected streamed Matrix content to be sent or edited"
    assert all("▉" not in text for text in all_text)
    assert any("Continuing to refine:" in text for text in all_text)


class TransformedStreamAgent:
    """Streams a response, then signals the gateway that a plugin hook
    (``transform_llm_output``) modified the final text after streaming
    finished. ``run_conversation`` returns ``response_transformed=True``
    plus a ``final_response`` that diverges from what was streamed.
    """

    def __init__(self, **kwargs):
        self.stream_delta_callback = kwargs.get("stream_delta_callback")
        self.tools = []

    def run_conversation(self, message, conversation_history=None, task_id=None):
        if self.stream_delta_callback:
            self.stream_delta_callback("original answer")
        return {
            "final_response": "original answer\n\n[plugin appended this]",
            "response_previewed": True,
            "response_transformed": True,
            "messages": [],
            "api_calls": 1,
        }


@pytest.mark.asyncio
async def test_transformed_response_edits_streamed_message_in_place(monkeypatch, tmp_path):
    """When a transform_llm_output hook modifies the response after streaming,
    the gateway must edit the existing streamed message in place with the full
    transformed content (so plugins like content filters / appenders reach the
    user) and still mark already_sent=True (no duplicate send).
    """
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        TransformedStreamAgent,
        session_id="sess-transformed-stream",
        config_data={
            "display": {"tool_progress": "off", "interim_assistant_messages": False},
            "streaming": {"enabled": True, "edit_interval": 0.01, "buffer_threshold": 1},
        },
        platform=Platform.MATRIX,
        chat_id="!room:matrix.example.org",
        chat_type="group",
        thread_id="$thread",
        adapter_cls=MetadataEditProgressCaptureAdapter,
    )

    # Final delivery happened (no duplicate send fallback).
    assert result.get("already_sent") is True
    # The transformed final text reached the user — appended portion is present
    # in an edit_message call (not just in the streamed sends).
    edited_texts = [e["content"] for e in adapter.edits]
    assert any("[plugin appended this]" in text for text in edited_texts), (
        f"expected transformed text in adapter.edits, got: {edited_texts!r}"
    )


@pytest.mark.asyncio
async def test_run_agent_queued_message_does_not_treat_commentary_as_final(monkeypatch, tmp_path):
    QueuedCommentaryAgent.calls = 0
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        QueuedCommentaryAgent,
        session_id="sess-queued-commentary",
        pending_text="queued follow-up",
        config_data={"display": {"interim_assistant_messages": True}},
    )

    sent_texts = [call["content"] for call in adapter.sent]
    assert result["final_response"] == "final response 2"
    assert "I'll inspect the repo first." in sent_texts
    assert "final response 1" in sent_texts


@pytest.mark.asyncio
async def test_run_agent_defers_background_review_notification_until_release(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        BackgroundReviewAgent,
        session_id="sess-bg-review-order",
        config_data={"display": {"interim_assistant_messages": True}},
    )

    assert result["final_response"] == "done"
    assert adapter.sent == []


@pytest.mark.asyncio
async def test_base_processing_releases_post_delivery_callback_after_main_send():
    """Post-delivery callbacks on the adapter fire after the main response."""
    adapter = ProgressCaptureAdapter()

    async def _handler(event):
        return "done"

    adapter.set_message_handler(_handler)

    released = []

    def _post_delivery_cb():
        released.append(True)
        adapter.sent.append(
            {
                "chat_id": "bg-review",
                "content": "💾 Skill 'prospect-scanner' created.",
                "reply_to": None,
                "metadata": None,
            }
        )

    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="-1001",
        chat_type="group",
        thread_id="17585",
    )
    event = MessageEvent(
        text="hello",
        message_type=MessageType.TEXT,
        source=source,
        message_id="msg-1",
    )
    session_key = "agent:main:telegram:group:-1001:17585"
    adapter._active_sessions[session_key] = asyncio.Event()
    adapter._post_delivery_callbacks[session_key] = _post_delivery_cb

    await adapter._process_message_background(event, session_key)

    sent_texts = [call["content"] for call in adapter.sent]
    assert sent_texts == ["done", "💾 Skill 'prospect-scanner' created."]
    assert released == [True]


@pytest.mark.asyncio
async def test_run_agent_drops_tool_progress_after_generation_invalidation(monkeypatch, tmp_path):
    import yaml

    (tmp_path / "config.yaml").write_text(
        yaml.dump({"display": {"tool_progress": "all"}}),
        encoding="utf-8",
    )

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)

    fake_run_agent = types.ModuleType("run_agent")
    fake_run_agent.AIAgent = DelayedProgressAgent
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)
    import tools.terminal_tool  # noqa: F401 - register terminal tool metadata

    adapter = ProgressCaptureAdapter(platform=Platform.DISCORD)
    runner = _make_runner(adapter)
    gateway_run = importlib.import_module("gateway.run")
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    monkeypatch.setattr(gateway_run, "_resolve_runtime_agent_kwargs", lambda: {"api_key": "***"})

    source = SessionSource(
        platform=Platform.DISCORD,
        chat_id="dm-1",
        chat_type="dm",
        thread_id=None,
    )
    session_key = "agent:main:discord:dm:dm-1"
    runner._session_run_generation[session_key] = 1

    original_send = adapter.send
    invalidated = {"done": False}

    async def send_and_invalidate(chat_id, content, reply_to=None, metadata=None):
        result = await original_send(chat_id, content, reply_to=reply_to, metadata=metadata)
        if "first command" in content and not invalidated["done"]:
            invalidated["done"] = True
            runner._invalidate_session_run_generation(session_key, reason="test_stop")
        return result

    adapter.send = send_and_invalidate

    result = await runner._run_agent(
        message="hello",
        context_prompt="",
        history=[],
        source=source,
        session_id="sess-progress-stop",
        session_key=session_key,
        run_generation=1,
    )

    all_progress_text = " ".join(call["content"] for call in adapter.sent)
    all_progress_text += " ".join(call["content"] for call in adapter.edits)
    assert result["final_response"] == "done"
    assert 'first command' in all_progress_text
    assert 'second command' not in all_progress_text


@pytest.mark.asyncio
async def test_run_agent_drops_interim_commentary_after_generation_invalidation(monkeypatch, tmp_path):
    import yaml

    (tmp_path / "config.yaml").write_text(
        yaml.dump({"display": {"tool_progress": "off", "interim_assistant_messages": True}}),
        encoding="utf-8",
    )

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)

    fake_run_agent = types.ModuleType("run_agent")
    fake_run_agent.AIAgent = DelayedInterimAgent
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)

    adapter = ProgressCaptureAdapter(platform=Platform.DISCORD)
    runner = _make_runner(adapter)
    gateway_run = importlib.import_module("gateway.run")
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    monkeypatch.setattr(gateway_run, "_resolve_runtime_agent_kwargs", lambda: {"api_key": "***"})

    source = SessionSource(
        platform=Platform.DISCORD,
        chat_id="dm-2",
        chat_type="dm",
        thread_id=None,
    )
    session_key = "agent:main:discord:dm:dm-2"
    runner._session_run_generation[session_key] = 1

    original_send = adapter.send
    invalidated = {"done": False}

    async def send_and_invalidate(chat_id, content, reply_to=None, metadata=None):
        result = await original_send(chat_id, content, reply_to=reply_to, metadata=metadata)
        if content == "first interim" and not invalidated["done"]:
            invalidated["done"] = True
            runner._invalidate_session_run_generation(session_key, reason="test_stop")
        return result

    adapter.send = send_and_invalidate

    result = await runner._run_agent(
        message="hello",
        context_prompt="",
        history=[],
        source=source,
        session_id="sess-commentary-stop",
        session_key=session_key,
        run_generation=1,
    )

    sent_texts = [call["content"] for call in adapter.sent]
    assert result["final_response"] == "done"
    assert "first interim" in sent_texts
    assert "second interim" not in sent_texts


@pytest.mark.asyncio
async def test_keep_typing_stops_immediately_when_interrupt_event_is_set():
    adapter = ProgressCaptureAdapter(platform=Platform.DISCORD)
    stop_event = asyncio.Event()

    task = asyncio.create_task(
        adapter._keep_typing(
            "dm-typing-stop",
            interval=30.0,
            stop_event=stop_event,
        )
    )
    await asyncio.sleep(0.05)
    stop_event.set()
    await asyncio.wait_for(task, timeout=0.5)

    normal_typing_calls = [
        call for call in adapter.typing if call.get("metadata") != {"stopped": True}
    ]
    stopped_calls = [
        call for call in adapter.typing if call.get("metadata") == {"stopped": True}
    ]
    assert len(normal_typing_calls) == 1
    assert len(stopped_calls) == 1


@pytest.mark.asyncio
async def test_verbose_mode_does_not_truncate_args_by_default(monkeypatch, tmp_path):
    """Verbose mode with default tool_preview_length (0) should NOT truncate args.

    Previously, verbose mode capped args at 200 chars when tool_preview_length
    was 0 (default).  The user explicitly opted into verbose — show full detail.
    """
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        VerboseAgent,
        session_id="sess-verbose-no-truncate",
        config_data={"display": {"tool_progress": "verbose", "tool_preview_length": 0}},
    )

    assert result["final_response"] == "done"
    # The full 300-char 'x' string should be present, not truncated to 200
    all_content = " ".join(call["content"] for call in adapter.sent)
    all_content += " ".join(call["content"] for call in adapter.edits)
    assert VerboseAgent.LONG_CODE in all_content


@pytest.mark.asyncio
async def test_verbose_mode_respects_explicit_tool_preview_length(monkeypatch, tmp_path):
    """When tool_preview_length is set to a positive value, verbose truncates to that."""
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        VerboseAgent,
        session_id="sess-verbose-explicit-cap",
        config_data={"display": {"tool_progress": "verbose", "tool_preview_length": 50}},
    )

    assert result["final_response"] == "done"
    all_content = " ".join(call["content"] for call in adapter.sent)
    all_content += " ".join(call["content"] for call in adapter.edits)
    # Should be truncated — full 300-char string NOT present
    assert VerboseAgent.LONG_CODE not in all_content
    # But should still contain the truncated portion with "..."
    assert "..." in all_content


@pytest.mark.asyncio
async def test_feishu_task_tracker_card_mode_sends_and_patches_one_card(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        TransactionPanelAgent,
        session_id="sess-feishu-progress-card",
        platform=Platform.FEISHU,
        chat_id="oc_1",
        chat_type="dm",
        thread_id=None,
        adapter_cls=FeishuProgressCardCaptureAdapter,
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {"enabled": True, "mode": "feishu_card", "max_operations": 8},
            },
        },
    )

    assert result["final_response"] == "done"
    assert len(adapter.cards_sent) == 1
    assert adapter.cards_patched
    final_card = adapter.cards_patched[-1]["card"]
    rendered = json.dumps(final_card, ensure_ascii=False)
    assert adapter.cards_patched[-1]["finalize"] is True
    assert "Task Workbench" in rendered
    assert "Completed" in rendered
    assert "read_file" in rendered
    assert "search_files" in rendered
    assert adapter.edits == []


@pytest.mark.asyncio
async def test_feishu_task_tracker_card_mode_reuses_one_card_for_queued_followup(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        TransactionPanelAgent,
        session_id="sess-feishu-progress-card-queued-followup",
        pending_text="continue the same task",
        platform=Platform.FEISHU,
        chat_id="oc_1",
        chat_type="dm",
        thread_id=None,
        adapter_cls=FeishuProgressCardCaptureAdapter,
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {"enabled": True, "mode": "feishu_card", "max_operations": 8},
            },
        },
    )

    assert result["final_response"] == "done"
    assert len(adapter.cards_sent) == 1
    assert adapter.cards_patched
    assert [call["message_id"] for call in adapter.cards_patched] == ["om_card_1"] * len(adapter.cards_patched)
    assert sum(1 for call in adapter.cards_patched if call["finalize"]) == 1
    final_card = adapter.cards_patched[-1]["card"]
    rendered = json.dumps(final_card, ensure_ascii=False)
    assert "Completed" in rendered
    assert "Running" not in rendered
    assert adapter.edits == []


@pytest.mark.asyncio
async def test_feishu_task_tracker_card_mode_final_card_includes_context_usage(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        ContextUsagePanelAgent,
        session_id="sess-feishu-progress-card-context",
        platform=Platform.FEISHU,
        chat_id="oc_1",
        chat_type="dm",
        thread_id=None,
        adapter_cls=FeishuProgressCardCaptureAdapter,
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {"enabled": True, "mode": "feishu_card", "max_operations": 8},
            },
        },
    )

    assert result["final_response"] == "done"
    final_card = adapter.cards_patched[-1]["card"]
    rendered = json.dumps(final_card, ensure_ascii=False)
    assert "Context" in rendered
    assert "40,960 / 128,000" in rendered
    assert "peak 65,536" in rendered
    assert "compressions 2" in rendered


@pytest.mark.asyncio
async def test_feishu_task_tracker_card_mode_final_patch_failure_sends_compact_notice(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        TransactionPanelAgent,
        session_id="sess-feishu-progress-card-fallback",
        platform=Platform.FEISHU,
        chat_id="oc_1",
        chat_type="dm",
        thread_id=None,
        adapter_cls=FeishuFinalPatchFailureAdapter,
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {"enabled": True, "mode": "feishu_card", "max_operations": 8},
            },
        },
    )

    assert result["final_response"] == "done"
    assert adapter.cards_sent
    assert any(call["finalize"] for call in adapter.cards_patched)
    assert len(adapter.sent) == 1
    _assert_compact_card_failure_notice_only(adapter.sent[0]["content"])


@pytest.mark.asyncio
async def test_feishu_task_tracker_card_mode_initial_send_failure_sends_only_compact_notice(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        TransactionPanelAgent,
        session_id="sess-feishu-progress-card-initial-send-fallback",
        platform=Platform.FEISHU,
        chat_id="oc_1",
        chat_type="dm",
        thread_id=None,
        adapter_cls=FeishuInitialCardFailureAdapter,
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {"enabled": True, "mode": "feishu_card", "max_operations": 8},
            },
        },
    )

    assert result["final_response"] == "done"
    assert len(adapter.cards_sent) == 1
    assert len(adapter.sent) == 1
    _assert_compact_card_failure_notice_only(adapter.sent[0]["content"])


@pytest.mark.asyncio
async def test_feishu_task_tracker_card_mode_patch_failure_does_not_spam_chat(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        TransactionPanelAgent,
        session_id="sess-feishu-progress-card-patch-fallback-once",
        platform=Platform.FEISHU,
        chat_id="oc_1",
        chat_type="dm",
        thread_id=None,
        adapter_cls=FeishuPatchFailureAdapter,
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {"enabled": True, "mode": "feishu_card", "max_operations": 8},
            },
        },
    )

    assert result["final_response"] == "done"
    assert adapter.cards_sent
    assert adapter.cards_patched
    assert len(adapter.sent) == 1
    _assert_compact_card_failure_notice_only(adapter.sent[0]["content"])


@pytest.mark.asyncio
async def test_feishu_task_tracker_card_mode_retryable_patch_failure_catches_up_at_final(
    monkeypatch, tmp_path
):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        RetryablePatchCatchupAgent,
        session_id="sess-feishu-progress-card-retryable-patch-catchup",
        platform=Platform.FEISHU,
        chat_id="oc_1",
        chat_type="dm",
        thread_id=None,
        adapter_cls=FeishuRetryableIntermediatePatchFailureAdapter,
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {"enabled": True, "mode": "feishu_card", "max_operations": 8},
            },
        },
    )

    assert result["final_response"] == "done"
    assert len(adapter.cards_sent) == 1
    assert any(not call["finalize"] for call in adapter.cards_patched)
    assert adapter.cards_patched[-1]["finalize"] is True
    assert adapter.sent == []
    rendered = json.dumps(adapter.cards_patched[-1]["card"], ensure_ascii=False)
    assert "Completed" in rendered
    assert "search_files" in rendered


@pytest.mark.asyncio
async def test_feishu_task_tracker_card_mode_coalesces_burst_render_signals(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        BurstTaskTrackerProgressAgent,
        session_id="sess-feishu-progress-card-coalesce-burst",
        platform=Platform.FEISHU,
        chat_id="oc_1",
        chat_type="dm",
        thread_id=None,
        adapter_cls=FeishuProgressCardCaptureAdapter,
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {"enabled": True, "mode": "feishu_card", "max_operations": 8},
            },
        },
    )

    assert result["final_response"] == "done"
    assert len(adapter.cards_sent) == 1
    non_final_patches = [call for call in adapter.cards_patched if not call["finalize"]]
    assert len(non_final_patches) <= 1
    assert len(non_final_patches) < 12
    assert adapter.cards_patched[-1]["finalize"] is True
    rendered = json.dumps(adapter.cards_patched[-1]["card"], ensure_ascii=False)
    assert "Completed" in rendered


@pytest.mark.asyncio
async def test_non_feishu_feishu_card_mode_falls_back_to_text_progress(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        TransactionPanelAgent,
        session_id="sess-non-feishu-card-mode-text-fallback",
        platform=Platform.TELEGRAM,
        chat_id="12345",
        chat_type="dm",
        thread_id=None,
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {"enabled": True, "mode": "feishu_card", "max_operations": 8},
            },
        },
    )

    assert result["final_response"] == "done"
    all_panels = "\n".join([call["content"] for call in adapter.sent] + [call["content"] for call in adapter.edits])
    assert "Transaction" in all_panels
    assert "Completed" in all_panels
    assert "read_file" in all_panels


@pytest.mark.asyncio
async def test_flowweaver_shadow_tap_collects_progress_when_visible_progress_is_off(monkeypatch, tmp_path):
    from gateway.flowweaver_shadow import FLOWWEAVER_SHADOW_SNAPSHOT_KEY

    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        OptionalProgressAgent,
        session_id="sess-flowweaver-shadow-progress-off",
        config_data={
            "display": {
                "tool_progress": "off",
                "task_tracker": {
                    "enabled": False,
                    "flowweaver_shadow": True,
                    "max_operations": 8,
                },
            },
        },
    )

    assert result["final_response"] == "done"
    assert adapter.sent == []
    assert adapter.edits == []
    shadow = result[FLOWWEAVER_SHADOW_SNAPSHOT_KEY]
    assert shadow["type"] == "flowweaver.handle.v0"
    assert shadow["transaction"]["status"] == "succeeded"
    assert shadow["snapshot"]["status"] == "succeeded"
    assert len(shadow["transaction"]["operations"]) == 2
    assert "gateway/run.py" not in repr(shadow)
    assert "tool_progress" not in repr(shadow)


@pytest.mark.asyncio
async def test_flowweaver_shadow_tap_attaches_consumer_capture_without_visible_side_effects(monkeypatch, tmp_path):
    from gateway.flowweaver_shadow import (
        FLOWWEAVER_SHADOW_CAPTURE_KEY,
        FLOWWEAVER_SHADOW_SNAPSHOT_KEY,
        get_flowweaver_shadow_capture,
    )

    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        OptionalProgressAgent,
        session_id="sess-flowweaver-shadow-capture",
        config_data={
            "display": {
                "tool_progress": "off",
                "task_tracker": {
                    "enabled": False,
                    "flowweaver_shadow": True,
                    "max_operations": 8,
                },
            },
        },
    )

    assert result["final_response"] == "done"
    assert adapter.sent == []
    assert adapter.edits == []
    snapshot = result[FLOWWEAVER_SHADOW_SNAPSHOT_KEY]
    capture = result[FLOWWEAVER_SHADOW_CAPTURE_KEY]
    assert capture["transaction_id"] == snapshot["transaction_id"]
    assert capture["correlation_id"] == snapshot["correlation_id"]
    assert capture["snapshot_id"] == snapshot["snapshot_id"]
    assert capture["lifecycle"]["visible_side_effects"] == []
    assert capture["consumer"]["forbidden_side_effects"] == [
        "send",
        "edit",
        "render",
        "persist",
        "temporal",
    ]
    view = get_flowweaver_shadow_capture(result)
    assert view is not None
    assert view["snapshot_ref"] == {
        "snapshot_key": FLOWWEAVER_SHADOW_SNAPSHOT_KEY,
        "transaction_id": snapshot["transaction_id"],
        "correlation_id": snapshot["correlation_id"],
        "snapshot_id": snapshot["snapshot_id"],
    }
    assert view["capture"] is capture


@pytest.mark.asyncio
async def test_flowweaver_shadow_tap_audit_ready_without_visible_side_effects(monkeypatch, tmp_path):
    from gateway.flowweaver_shadow import (
        FLOWWEAVER_SHADOW_AUDIT_READY,
        audit_flowweaver_shadow_capture,
    )

    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        OptionalProgressAgent,
        session_id="sess-flowweaver-shadow-audit",
        config_data={
            "display": {
                "tool_progress": "off",
                "task_tracker": {
                    "enabled": False,
                    "flowweaver_shadow": True,
                    "max_operations": 8,
                },
            },
        },
    )

    audit = audit_flowweaver_shadow_capture(result)

    assert result["final_response"] == "done"
    assert adapter.sent == []
    assert adapter.edits == []
    assert audit["verdict"] == FLOWWEAVER_SHADOW_AUDIT_READY
    assert audit["reason"] == "ok"
    assert audit["side_effects"] == []
    assert "snapshot" not in audit
    assert "capture" not in audit
    assert "deliveries" not in repr(audit)
    assert "om_" not in repr(audit)


@pytest.mark.asyncio
async def test_flowweaver_shadow_tap_replay_probe_without_visible_side_effects(monkeypatch, tmp_path):
    from gateway.flowweaver_shadow import (
        FLOWWEAVER_SHADOW_REPLAY_REPLAYED,
        replay_flowweaver_shadow_capture,
    )

    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        OptionalProgressAgent,
        session_id="sess-flowweaver-shadow-replay",
        config_data={
            "display": {
                "tool_progress": "off",
                "task_tracker": {
                    "enabled": False,
                    "flowweaver_shadow": True,
                    "max_operations": 8,
                },
            },
        },
    )

    replay = replay_flowweaver_shadow_capture(result, attempts=3)

    assert result["final_response"] == "done"
    assert adapter.sent == []
    assert adapter.edits == []
    assert replay["verdict"] == FLOWWEAVER_SHADOW_REPLAY_REPLAYED
    assert replay["reason"] == "ok"
    assert replay["replay_count"] == 3
    assert replay["side_effects"] == []
    assert "snapshot" not in replay
    assert "capture" not in replay
    assert "deliveries" not in repr(replay)
    assert "om_" not in repr(replay)


@pytest.mark.asyncio
async def test_flowweaver_shadow_tap_replay_corpus_without_visible_side_effects(monkeypatch, tmp_path):
    from gateway.flowweaver_shadow import (
        FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED,
        replay_flowweaver_shadow_corpus,
    )

    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        OptionalProgressAgent,
        session_id="sess-flowweaver-shadow-replay-corpus",
        config_data={
            "display": {
                "tool_progress": "off",
                "task_tracker": {
                    "enabled": False,
                    "flowweaver_shadow": True,
                    "max_operations": 8,
                },
            },
        },
    )

    corpus = replay_flowweaver_shadow_corpus([result], attempts=2)

    rendered = repr(corpus).lower()
    assert result["final_response"] == "done"
    assert adapter.sent == []
    assert adapter.edits == []
    assert corpus["verdict"] == FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED
    assert corpus["reason"] == "ok"
    assert corpus["entry_count"] == 1
    assert corpus["entries"][0]["verdict"] == "replayed"
    assert corpus["side_effects"] == []
    assert "snapshot_ref" not in corpus["entries"][0]
    assert "snapshot" not in corpus["entries"][0]
    assert "capture" not in corpus["entries"][0]
    assert "transaction" not in corpus["entries"][0]
    assert "deliveries" not in rendered
    assert "artifacts" not in rendered
    assert "om_" not in rendered
    assert "oc_" not in rendered
    assert "ou_" not in rendered
    assert "chat" not in rendered
    assert "user" not in rendered
    assert "message" not in rendered


@pytest.mark.asyncio
async def test_flowweaver_mock_durable_consumer_without_visible_side_effects(monkeypatch, tmp_path):
    from gateway.flowweaver_mock_durable import (
        FLOWWEAVER_MOCK_DURABLE_ACCEPTED,
        consume_flowweaver_shadow_corpus_as_mock_durable_state,
    )
    from gateway.flowweaver_shadow import (
        describe_flowweaver_shadow_consumer_contract,
        replay_flowweaver_shadow_corpus,
    )

    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        OptionalProgressAgent,
        session_id="sess-flowweaver-mock-durable-consumer",
        config_data={
            "display": {
                "tool_progress": "off",
                "task_tracker": {
                    "enabled": False,
                    "flowweaver_shadow": True,
                    "max_operations": 8,
                },
            },
        },
    )

    corpus = replay_flowweaver_shadow_corpus([result], attempts=2)
    projection = consume_flowweaver_shadow_corpus_as_mock_durable_state(
        describe_flowweaver_shadow_consumer_contract(),
        corpus,
    )

    rendered = repr(projection).lower()
    assert result["final_response"] == "done"
    assert adapter.sent == []
    assert adapter.edits == []
    assert projection["verdict"] == FLOWWEAVER_MOCK_DURABLE_ACCEPTED
    assert projection["entry_count"] == 1
    assert projection["side_effects"] == []
    assert projection["checks"]["side_effects_absent"] is True
    assert "snapshot" not in rendered
    assert "capture" not in rendered
    assert "om_" not in rendered
    assert "oc_" not in rendered
    assert "ou_" not in rendered
    assert "chat" not in rendered
    assert "user" not in rendered
    assert "message" not in rendered


@pytest.mark.asyncio
async def test_flowweaver_shadow_dry_run_default_off_no_result_key(monkeypatch, tmp_path):
    from gateway.flowweaver_shadow import FLOWWEAVER_SHADOW_SNAPSHOT_KEY
    from gateway.flowweaver_shadow_dry_run import FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY

    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        OptionalProgressAgent,
        session_id="sess-flowweaver-shadow-dry-run-default-off",
        config_data={
            "display": {
                "tool_progress": "off",
                "task_tracker": {
                    "enabled": False,
                    "flowweaver_shadow": True,
                    "max_operations": 8,
                },
            },
        },
    )

    assert result["final_response"] == "done"
    assert adapter.sent == []
    assert adapter.edits == []
    assert FLOWWEAVER_SHADOW_SNAPSHOT_KEY in result
    assert FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY not in result


@pytest.mark.asyncio
async def test_flowweaver_shadow_dry_run_requires_explicit_dry_run_gate(monkeypatch, tmp_path):
    from gateway.flowweaver_shadow import FLOWWEAVER_SHADOW_SNAPSHOT_KEY
    from gateway.flowweaver_shadow_dry_run import FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY

    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        OptionalProgressAgent,
        session_id="sess-flowweaver-shadow-dry-run-shadow-missing",
        config_data={
            "display": {
                "tool_progress": "off",
                "task_tracker": {
                    "enabled": False,
                    "flowweaver_shadow": False,
                    "flowweaver_shadow_dry_run": True,
                    "max_operations": 8,
                },
            },
        },
    )

    assert result["final_response"] == "done"
    assert adapter.sent == []
    assert adapter.edits == []
    assert FLOWWEAVER_SHADOW_SNAPSHOT_KEY not in result
    assert FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY not in result


@pytest.mark.asyncio
async def test_flowweaver_shadow_dry_run_runs_without_visible_side_effects(monkeypatch, tmp_path):
    from gateway.flowweaver_shadow_dry_run import (
        FLOWWEAVER_SHADOW_DRY_RUN_PASSED,
        FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY,
    )

    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        OptionalProgressAgent,
        session_id="sess-flowweaver-shadow-dry-run-side-effects",
        config_data={
            "display": {
                "tool_progress": "off",
                "task_tracker": {
                    "enabled": False,
                    "flowweaver_shadow": True,
                    "flowweaver_shadow_dry_run": True,
                    "max_operations": 8,
                },
            },
        },
    )

    dry_run = result[FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY]
    rendered = repr(dry_run).lower()
    assert result["final_response"] == "done"
    assert adapter.sent == []
    assert adapter.edits == []
    assert dry_run["verdict"] == FLOWWEAVER_SHADOW_DRY_RUN_PASSED
    assert dry_run["entry_count"] == 1
    assert dry_run["record_counts"] == {"intents": 1, "artifacts": 1, "deliveries": 1}
    assert dry_run["side_effects"] == []
    assert "snapshot" not in rendered
    assert "flowweaver_shadow_capture" not in rendered
    assert "om_" not in rendered
    assert "oc_" not in rendered
    assert "ou_" not in rendered
    assert "chat" not in rendered
    assert "user" not in rendered
    assert "message" not in rendered


@pytest.mark.asyncio
async def test_flowweaver_shadow_dry_run_preserves_legacy_tool_progress_when_visible(monkeypatch, tmp_path):
    from gateway.flowweaver_shadow_dry_run import FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY

    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        OptionalProgressAgent,
        session_id="sess-flowweaver-shadow-dry-run-visible-progress",
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {
                    "enabled": False,
                    "flowweaver_shadow": True,
                    "flowweaver_shadow_dry_run": True,
                },
            },
        },
    )

    visible_progress = "\n".join(
        [call["content"] for call in adapter.sent]
        + [call["content"] for call in adapter.edits]
    )
    assert result["final_response"] == "done"
    assert FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY in result
    assert "read_file" in visible_progress
    assert "search_files" in visible_progress
    assert "Transaction" not in visible_progress
    assert "**Status:**" not in visible_progress


@pytest.mark.asyncio
async def test_flowweaver_shadow_dry_run_feishu_card_mode_does_not_send_or_patch_when_tracker_disabled(monkeypatch, tmp_path):
    from gateway.flowweaver_shadow_dry_run import (
        FLOWWEAVER_SHADOW_DRY_RUN_PASSED,
        FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY,
    )

    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        OptionalProgressAgent,
        session_id="sess-flowweaver-shadow-dry-run-feishu-card-off",
        platform=Platform.FEISHU,
        chat_id="oc_1",
        chat_type="dm",
        thread_id=None,
        adapter_cls=FeishuProgressCardCaptureAdapter,
        config_data={
            "display": {
                "tool_progress": "off",
                "task_tracker": {
                    "enabled": False,
                    "mode": "feishu_card",
                    "flowweaver_shadow": True,
                    "flowweaver_shadow_dry_run": True,
                    "max_operations": 8,
                },
            },
        },
    )

    dry_run = result[FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY]
    assert result["final_response"] == "done"
    assert adapter.sent == []
    assert adapter.edits == []
    assert adapter.cards_sent == []
    assert adapter.cards_patched == []
    assert dry_run["verdict"] == FLOWWEAVER_SHADOW_DRY_RUN_PASSED
    assert dry_run["side_effects"] == []


@pytest.mark.asyncio
async def test_flowweaver_shadow_dry_run_config_matrix_preserves_visibility_boundaries(monkeypatch, tmp_path):
    from gateway.flowweaver_shadow import FLOWWEAVER_SHADOW_SNAPSHOT_KEY
    from gateway.flowweaver_shadow_dry_run import FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY

    cases = [
        (
            "shadow-off-dry-run-on",
            {"tool_progress": "off", "task_tracker": {"enabled": False, "flowweaver_shadow": False, "flowweaver_shadow_dry_run": True}},
            {"shadow": False, "dry_run": False, "visible": False, "tracker": False},
        ),
        (
            "shadow-on-dry-run-off",
            {"tool_progress": "off", "task_tracker": {"enabled": False, "flowweaver_shadow": True, "flowweaver_shadow_dry_run": False}},
            {"shadow": True, "dry_run": False, "visible": False, "tracker": False},
        ),
        (
            "both-on-progress-off-tracker-off",
            {"tool_progress": "off", "task_tracker": {"enabled": False, "flowweaver_shadow": True, "flowweaver_shadow_dry_run": True}},
            {"shadow": True, "dry_run": True, "visible": False, "tracker": False},
        ),
        (
            "both-on-progress-all-tracker-off",
            {"tool_progress": "all", "task_tracker": {"enabled": False, "flowweaver_shadow": True, "flowweaver_shadow_dry_run": True}},
            {"shadow": True, "dry_run": True, "visible": True, "tracker": False},
        ),
        (
            "both-on-tracker-on",
            {"tool_progress": "off", "task_tracker": {"enabled": True, "mode": "text", "flowweaver_shadow": True, "flowweaver_shadow_dry_run": True, "max_operations": 8}},
            {"shadow": True, "dry_run": True, "visible": True, "tracker": True},
        ),
    ]

    for name, display_config, expected in cases:
        case_tmp = tmp_path / name
        case_tmp.mkdir()
        adapter, result = await _run_with_agent(
            monkeypatch,
            case_tmp,
            OptionalProgressAgent,
            session_id=f"sess-flowweaver-shadow-dry-run-matrix-{name}",
            config_data={"display": display_config},
        )
        visible = "\n".join([call["content"] for call in adapter.sent] + [call["content"] for call in adapter.edits])

        assert (FLOWWEAVER_SHADOW_SNAPSHOT_KEY in result) is expected["shadow"], name
        assert (FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY in result) is expected["dry_run"], name
        assert bool(adapter.sent or adapter.edits) is expected["visible"], name
        if expected["dry_run"]:
            assert result[FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY]["verdict"] == "passed", name
        if expected["tracker"]:
            assert "Transaction" in visible, name
        elif display_config["tool_progress"] == "all":
            assert "read_file" in visible, name
            assert "Transaction" not in visible, name
        else:
            assert "Transaction" not in visible, name

    feishu_base = {
        "display": {
            "tool_progress": "off",
            "task_tracker": {
                "enabled": True,
                "mode": "feishu_card",
                "flowweaver_shadow": True,
                "max_operations": 8,
            },
        },
    }
    feishu_without_tmp = tmp_path / "feishu-without-dry-run"
    feishu_without_tmp.mkdir()
    adapter_without_dry_run, result_without_dry_run = await _run_with_agent(
        monkeypatch,
        feishu_without_tmp,
        OptionalProgressAgent,
        session_id="sess-flowweaver-shadow-dry-run-feishu-base",
        platform=Platform.FEISHU,
        chat_id="oc_1",
        chat_type="dm",
        thread_id=None,
        adapter_cls=FeishuProgressCardCaptureAdapter,
        config_data=feishu_base,
    )
    feishu_with_dry_run = json.loads(json.dumps(feishu_base))
    feishu_with_dry_run["display"]["task_tracker"]["flowweaver_shadow_dry_run"] = True
    feishu_with_tmp = tmp_path / "feishu-with-dry-run"
    feishu_with_tmp.mkdir()
    adapter_with_dry_run, result_with_dry_run = await _run_with_agent(
        monkeypatch,
        feishu_with_tmp,
        OptionalProgressAgent,
        session_id="sess-flowweaver-shadow-dry-run-feishu-enabled",
        platform=Platform.FEISHU,
        chat_id="oc_1",
        chat_type="dm",
        thread_id=None,
        adapter_cls=FeishuProgressCardCaptureAdapter,
        config_data=feishu_with_dry_run,
    )

    assert FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY not in result_without_dry_run
    assert FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY in result_with_dry_run
    assert len(adapter_with_dry_run.cards_sent) == len(adapter_without_dry_run.cards_sent)
    assert len(adapter_with_dry_run.cards_patched) == len(adapter_without_dry_run.cards_patched)
    assert adapter_with_dry_run.sent == adapter_without_dry_run.sent == []
    assert adapter_with_dry_run.edits == adapter_without_dry_run.edits == []


@pytest.mark.asyncio
async def test_flowweaver_shadow_tap_default_off_preserves_existing_no_progress_behavior(monkeypatch, tmp_path):
    from gateway.flowweaver_shadow import FLOWWEAVER_SHADOW_SNAPSHOT_KEY

    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        OptionalProgressAgent,
        session_id="sess-flowweaver-shadow-default-off",
        config_data={
            "display": {
                "tool_progress": "off",
                "task_tracker": {"enabled": False},
            },
        },
    )

    assert result["final_response"] == "done"
    assert adapter.sent == []
    assert adapter.edits == []
    assert FLOWWEAVER_SHADOW_SNAPSHOT_KEY not in result


@pytest.mark.asyncio
async def test_flowweaver_shadow_tap_streamed_final_text_counts_as_answered_coverage(monkeypatch, tmp_path):
    from gateway.flowweaver_shadow import FLOWWEAVER_SHADOW_SNAPSHOT_KEY

    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        StreamingRefineAgent,
        session_id="sess-flowweaver-shadow-streamed-final",
        config_data={
            "display": {
                "tool_progress": "off",
                "interim_assistant_messages": False,
                "task_tracker": {
                    "enabled": False,
                    "flowweaver_shadow": True,
                },
            },
            "streaming": {"enabled": True, "edit_interval": 0.01, "buffer_threshold": 1},
        },
        platform=Platform.MATRIX,
        chat_id="!room:matrix.example.org",
        chat_type="group",
        thread_id="$thread",
    )

    assert result.get("already_sent") is True
    assert result["delivery_state"]["final_text"] == {"sent": True, "reason": "stream_final_response"}
    shadow = result[FLOWWEAVER_SHADOW_SNAPSHOT_KEY]
    assert shadow["transaction"]["final_text"]["status"] == "succeeded"
    assert shadow["transaction"]["intent_coverage"][0]["mode"] == "answered"
    assert shadow["transaction"]["deliveries"][0]["surface"] == "final_text"
    assert any(
        "Continuing to refine:" in call["content"]
        for call in adapter.sent + adapter.edits
    )


@pytest.mark.asyncio
async def test_flowweaver_shadow_tap_preserves_legacy_tool_progress_when_progress_is_visible(monkeypatch, tmp_path):
    from gateway.flowweaver_shadow import FLOWWEAVER_SHADOW_SNAPSHOT_KEY

    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        OptionalProgressAgent,
        session_id="sess-flowweaver-shadow-visible-progress",
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {
                    "enabled": False,
                    "flowweaver_shadow": True,
                },
            },
        },
    )

    visible_progress = "\n".join(
        [call["content"] for call in adapter.sent]
        + [call["content"] for call in adapter.edits]
    )
    assert result["final_response"] == "done"
    assert FLOWWEAVER_SHADOW_SNAPSHOT_KEY in result
    assert "read_file" in visible_progress
    assert "Transaction" not in visible_progress
    assert "**Status:**" not in visible_progress


@pytest.mark.asyncio
async def test_task_tracker_uses_intent_summary_instead_of_raw_user_text(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        TransactionPanelAgent,
        message="再试一次。今晚下雨吗？",
        session_id="sess-task-tracker-intent-title",
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {"enabled": True, "mode": "text", "max_operations": 8},
            },
        },
    )

    assert result["final_response"] == "done"
    all_panels = "\n".join([call["content"] for call in adapter.sent] + [call["content"] for call in adapter.edits])
    assert "再试一次。今晚下雨吗？" not in all_panels
    assert "今晚" in all_panels
    assert "降雨" in all_panels or "下雨" in all_panels


@pytest.mark.asyncio
async def test_feishu_task_tracker_card_uses_semantic_intent_title(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        TransactionPanelAgent,
        message="事务摘要的文字长度不要限制过短，尤其是多语言场景中。核心目标是把事情说清楚，语义密度尽可能大，信息损失小，信息熵增小。",
        session_id="sess-feishu-intent-title",
        platform=Platform.FEISHU,
        chat_id="oc_1",
        chat_type="dm",
        thread_id=None,
        adapter_cls=FeishuProgressCardCaptureAdapter,
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {"enabled": True, "mode": "feishu_card", "max_operations": 8},
            },
        },
    )

    assert result["final_response"] == "done"
    final_card = adapter.cards_patched[-1]["card"]
    rendered = json.dumps(final_card, ensure_ascii=False)
    assert "调整事务摘要策略" in rendered
    assert "核心目标是把事情说清楚" not in rendered
    assert "多语言" in rendered
    assert "语义密度" in rendered
    assert "信息损失" in rendered
    assert "熵增" in rendered


@pytest.mark.asyncio
async def test_task_tracker_panel_replaces_raw_tool_progress_when_enabled(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        TransactionPanelAgent,
        session_id="sess-task-tracker-panel",
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {"enabled": True, "mode": "text", "max_operations": 8},
            },
        },
    )

    assert result["final_response"] == "done"
    assert adapter.sent
    first_panel = adapter.sent[0]["content"]
    all_panels = "\n".join([call["content"] for call in adapter.sent] + [call["content"] for call in adapter.edits])
    assert "📌" in first_panel
    assert "Transaction" in first_panel
    assert "Summarize user intent" in first_panel
    assert "hello" not in first_panel
    assert "read_file" in all_panels
    assert "search_files" in all_panels
    assert "Completed" in all_panels
    assert '📖 read_file: "gateway/run.py"' not in all_panels


@pytest.mark.asyncio
async def test_task_tracker_falls_back_when_final_completed_edit_fails(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        TransactionPanelAgent,
        session_id="sess-task-tracker-final-edit-fallback",
        adapter_cls=FinalProgressEditFailureAdapter,
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {"enabled": True, "mode": "text", "max_operations": 8},
            },
        },
    )

    assert result["final_response"] == "done"
    assert any("**Status:** Running" in call["content"] for call in adapter.sent)
    assert any("**Status:** Completed" in call["content"] for call in adapter.edits)
    assert any("**Status:** Completed" in call["content"] for call in adapter.sent[1:])


@pytest.mark.asyncio
async def test_task_tracker_final_completed_panel_is_flushed_before_progress_task_cancel(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        TransactionPanelAgent,
        session_id="sess-task-tracker-explicit-final-flush",
        adapter_cls=CancellingTaskDropsFinalAdapter,
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {"enabled": True, "mode": "text", "max_operations": 8},
            },
        },
    )

    assert result["final_response"] == "done"
    assert adapter.dropped_completed_updates == []
    assert adapter.visible_completed_updates
    assert "**Status:** Completed" in adapter.visible_completed_updates[-1]


@pytest.mark.asyncio
async def test_task_tracker_final_flush_ignores_stale_running_update_ack(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        TransactionPanelAgent,
        session_id="sess-task-tracker-ignore-stale-running-ack",
        adapter_cls=SlowInFlightRunningUpdateAdapter,
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {"enabled": True, "mode": "text", "max_operations": 8},
            },
        },
    )

    assert result["final_response"] == "done"
    assert adapter.delayed_running_send
    assert adapter.visible_completed_updates
    assert "**Status:** Completed" in adapter.visible_completed_updates[-1]


@pytest.mark.asyncio
async def test_task_tracker_final_flush_bypasses_progress_edit_throttle(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        SingleProgressFastReturnAgent,
        session_id="sess-task-tracker-final-flush-throttle",
        adapter_cls=CancellingTaskDropsFinalAdapter,
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {"enabled": True, "mode": "text", "max_operations": 8},
            },
        },
    )

    assert result["final_response"] == "done"
    assert adapter.visible_completed_updates
    assert "**Status:** Completed" in adapter.visible_completed_updates[-1]


@pytest.mark.asyncio
async def test_task_tracker_panel_includes_configured_dashboard_link_without_secrets(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        TransactionPanelAgent,
        session_id="sess-task-tracker-dashboard-link",
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {
                    "enabled": True,
                    "mode": "text",
                    "max_operations": 8,
                    "dashboard_url": (
                        "https://dashboard.example.local:9119/app?session_"
                        + "token=abc"
                        + "123#sec"
                        + "ret"
                    ),
                },
            },
        },
    )

    assert result["final_response"] == "done"
    all_panels = "\n".join([call["content"] for call in adapter.sent] + [call["content"] for call in adapter.edits])
    assert "Dashboard" in all_panels
    assert "https://dashboard.example.local:9119/app/progress" in all_panels
    assert "session_token" not in all_panels
    assert "abc123" not in all_panels
    assert "#secret" not in all_panels


@pytest.mark.asyncio
async def test_task_tracker_panel_omits_unsafe_dashboard_link(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        TransactionPanelAgent,
        session_id="sess-task-tracker-unsafe-dashboard-link",
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {
                    "enabled": True,
                    "mode": "text",
                    "max_operations": 8,
                    "dashboard_url": "javascript:alert('x')",
                },
            },
        },
    )

    assert result["final_response"] == "done"
    all_panels = "\n".join([call["content"] for call in adapter.sent] + [call["content"] for call in adapter.edits])
    assert "Dashboard" not in all_panels
    assert "javascript:" not in all_panels


@pytest.mark.asyncio
async def test_task_tracker_panel_respects_tool_progress_off(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        TransactionPanelAgent,
        session_id="sess-task-tracker-off",
        config_data={
            "display": {
                "tool_progress": "off",
                "task_tracker": {"enabled": True, "mode": "text", "max_operations": 8},
            },
        },
    )

    assert result["final_response"] == "done"
    all_panels = "\n".join([call["content"] for call in adapter.sent] + [call["content"] for call in adapter.edits])
    assert "Transaction" in all_panels
    assert "read_file" not in all_panels
    assert "search_files" not in all_panels


@pytest.mark.asyncio
async def test_task_tracker_panel_renders_subagent_progress_events(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        SubagentProgressAgent,
        session_id="sess-task-tracker-subagent",
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {"enabled": True, "mode": "text", "max_operations": 8},
            },
        },
    )

    assert result["final_response"] == "done"
    all_panels = "\n".join([call["content"] for call in adapter.sent] + [call["content"] for call in adapter.edits])
    assert "subagent start" in all_panels
    assert "subagent tool: search_files" in all_panels
    assert "subagent complete" in all_panels


@pytest.mark.asyncio
async def test_task_tracker_persists_progress_events_when_enabled(monkeypatch, tmp_path):
    store_path = tmp_path / "progress" / "events.jsonl"

    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        PersistentProgressAgent,
        session_id="sess-task-tracker-persist",
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {
                    "enabled": True,
                    "mode": "text",
                    "persist_events": True,
                    "event_store": "jsonl",
                    "event_store_path": str(store_path),
                },
            },
        },
    )

    assert result["final_response"] == "done"
    assert store_path.exists()
    records = [json.loads(line) for line in store_path.read_text(encoding="utf-8").splitlines()]
    rendered = json.dumps(records, ensure_ascii=False)
    assert len(records) >= 2
    assert records[-1]["record_type"] == "progress.snapshot"
    assert records[-1]["transaction"]["status"] == "completed"
    assert records[0]["transaction"]["id"] == "sess-task-tracker-persist"
    assert records[0]["operation"]["event_type"] == "tool.started"
    assert any(record.get("operation", {}).get("event_type") == "tool.completed" for record in records)
    assert "terminal" in rendered
    assert "ok=yes" in rendered
    assert "persist-secret" not in rendered
    assert "[REDACTED]" in rendered


@pytest.mark.asyncio
async def test_task_tracker_does_not_persist_progress_events_when_disabled(monkeypatch, tmp_path):
    store_path = tmp_path / "progress" / "events.jsonl"

    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        PersistentProgressAgent,
        session_id="sess-task-tracker-no-persist",
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {
                    "enabled": True,
                    "mode": "text",
                    "persist_events": False,
                    "event_store": "jsonl",
                    "event_store_path": str(store_path),
                },
            },
        },
    )

    assert result["final_response"] == "done"
    assert adapter.sent
    assert not store_path.exists()
