"""S6 — semantic AGENT delegation end to end through the Gateway seams.

There is no delegation **command** any more, and the first thing proven here
is its absence: no ``CommandDef``, no help/catalog/menu line, no Gateway
route, no handler, and no bypass. A message that happens to begin with the old
word is ordinary text now — nothing intercepts it, translates it, or explains
it, because there is nothing left that knows the word.

What replaces it is the path the rest of this file proves: Hermes chooses a
canonical ``agent_id`` in conversation, the gated control tool admits it
against ``live roster ∩ execution preset``, and the coordinator owns
everything durable from there. The Gateway's remaining job is hosting —
trusted Session context in, delivery and the next turn's result context out.

What is proven here:

* the delegation command is gone from every shared surface, both Gateway
  routes, and the slash mixin — and no ``ars`` command was minted beside it;
* a created task resolves its durable Hermes Session from trusted Gateway
  context and reaches no ARS operation while doing so;
* the accepted receipt goes out through the injected adapter sender carrying
  exactly ``requested_agent`` / ``requested_model`` / ``requested_effort``;
* the terminal result reaches the adapter through ``send_plain_text_once`` as
  one visible body inside the platform bound, carrying the durable full-result
  ref — and Feishu sends it as one low-level ``msg_type="text"``, never a post
  or a chunk;
* continuation reuses the sealed task, Session, preset, and AGENT, and a
  switch creates a linked task under the exact ``agent_id``;
* the durable delivery factory keeps every platform's own call shape;
* the finished result is folded into the next ordinary turn exactly once, and
  the handoff latch settles once under interrupts, budget denials, proxy mode,
  and concurrency.

Everything is offline: no adapter connection, socket, daemon, network, or AGENT.
"""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import gateway.sachima_delegate as delegate_mod
from gateway.platforms.base import SendResult
from gateway.sachima_delegate_state import (
    DelegateOrigin,
    DelegateStateStore,
    delegate_state_root,
)
from gateway.sachima_delegate_summary import SUMMARY_REASON_SOURCE_INCOMPLETE
from hermes_cli.commands import (
    COMMAND_REGISTRY,
    COMMANDS,
    COMMANDS_BY_CATEGORY,
    GATEWAY_KNOWN_COMMANDS,
    gateway_help_lines,
    resolve_command,
    should_bypass_active_session,
    telegram_bot_commands,
)
from sachima_supervisor.runtime_spine.agent_run_supervisor_execution_binding import (
    bind_arsd_execution,
)
from sachima_supervisor.runtime_spine.arsd_run_binding_ledger import ArsdRunBindingLedger

from tests.gateway.test_sachima_delegate_coordinator import (
    CARD_TITLE_CANARY,
    FINAL_MESSAGE_CANARY,
    ROUND_TITLE_CANARY,
    TASK_TEXT_CANARY,
    _catalog,
    _Facade,
    _config,
)

#: The word that used to be a command. It is kept only so the absence tests
#: can name what must not exist.
RETIRED_COMMAND = "delegate"
#: The canonical AGENT these tests delegate to.
AGENT_ID = "codex"


# --------------------------------------------------------------------------- #
# A. The command is gone — from every surface, atomically
#
# Absence is asserted behaviorally (the registry, the resolver, the bypass
# predicate, the access gate, the mixin) as well as textually, because a
# removed word that still resolves somewhere is not removed. There is
# deliberately no test asserting what old ``/delegate ...`` text *does*: it is
# ordinary input now, and giving it a test would give it a behavior.
# --------------------------------------------------------------------------- #
def test_no_delegation_command_is_registered_any_more():
    assert [cmd for cmd in COMMAND_REGISTRY if cmd.name == RETIRED_COMMAND] == []
    for cmd in COMMAND_REGISTRY:
        assert RETIRED_COMMAND not in cmd.aliases
        assert RETIRED_COMMAND not in cmd.subcommands


def test_the_gateway_no_longer_knows_or_resolves_it():
    from hermes_cli.commands import is_gateway_known_command

    assert RETIRED_COMMAND not in GATEWAY_KNOWN_COMMANDS
    assert is_gateway_known_command(RETIRED_COMMAND) is False
    assert resolve_command(RETIRED_COMMAND) is None
    assert resolve_command("/delegate") is None
    assert should_bypass_active_session(RETIRED_COMMAND) is False


def test_no_ars_command_was_minted_in_its_place():
    assert resolve_command("ars") is None
    assert "ars" not in GATEWAY_KNOWN_COMMANDS
    assert [cmd for cmd in COMMAND_REGISTRY if cmd.name == "ars"] == []
    for cmd in COMMAND_REGISTRY:
        assert "ars" not in cmd.aliases


def test_it_is_absent_from_every_derived_surface():
    assert [line for line in gateway_help_lines() if "/delegate" in line] == []
    assert [
        name for name, _description in telegram_bot_commands()
        if name == RETIRED_COMMAND
    ] == []
    assert "/delegate" not in COMMANDS
    for category in COMMANDS_BY_CATEGORY.values():
        assert "/delegate" not in category


def test_neither_gateway_route_nor_the_slash_mixin_carries_a_handler():
    from gateway.slash_commands import GatewaySlashCommandsMixin

    assert not hasattr(GatewaySlashCommandsMixin, "_handle_delegate_command")
    assert not hasattr(GatewaySlashCommandsMixin, "_delegate_delivery_for")

    src = _run_source()
    assert "_handle_delegate_command" not in src
    assert 'canonical == "delegate"' not in src
    assert '_cmd_def_inner.name == "delegate"' not in src


def test_the_one_remaining_entry_point_is_the_gated_control_tool():
    """One surface, and it is not a command: the model-invoked control tool."""

    import tools.sachima_delegate_control_tool as control

    assert control.TOOL_NAME == "sachima_delegate_control"
    assert resolve_command(control.TOOL_NAME) is None
    assert control.TOOL_NAME not in GATEWAY_KNOWN_COMMANDS


# --------------------------------------------------------------------------- #
# B. The host harness
#
# The host is the real ``GatewayRunner`` seams a delegated task still touches:
# the Session store that supplies trusted context, the adapter registry, and
# the durable delivery factory rebuilt from an origin. There is no command
# handler to drive, so tasks are created the way the control tool creates
# them — admit one canonical ``agent_id``, then hand the coordinator the
# admitted preset and an origin built from the caller's own Session.
# --------------------------------------------------------------------------- #
class _Adapter:
    """A fake adapter that records both delivery surfaces separately."""

    MAX_MESSAGE_LENGTH = 300

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, Any]] = []
        self.plain_once: list[tuple[str, str, Any]] = []
        self.send_result: Any = SendResult(success=True, message_id="om_send")
        self.once_result: Any = SendResult(success=True, message_id=None)
        self.send_error: BaseException | None = None
        self.once_error: BaseException | None = None

    def single_message_text_limit(self) -> int:
        return self.MAX_MESSAGE_LENGTH

    def measure_text(self, text: str) -> int:
        return len(text or "")

    async def send(self, chat_id, text, reply_to=None, metadata=None):
        self.sent.append((chat_id, text, metadata))
        if self.send_error is not None:
            raise self.send_error
        return self.send_result

    async def send_plain_text_once(self, chat_id, text, reply_to=None, metadata=None):
        self.plain_once.append((chat_id, text, metadata))
        if self.once_error is not None:
            raise self.once_error
        return self.once_result


def _source(chat_id="chat-1", thread_id=None):
    from gateway.config import Platform
    from gateway.session import SessionSource

    return SessionSource(
        platform=Platform.TELEGRAM,
        chat_id=chat_id,
        chat_type="dm",
        user_id="user-1",
        thread_id=thread_id,
    )


class _Host:
    """The runner seams a delegated task's Session and delivery still need."""

    def __init__(self, tmp_path: Path):
        from gateway.config import GatewayConfig, Platform
        from gateway.run import GatewayRunner
        from gateway.session import SessionStore

        self.host = object.__new__(GatewayRunner)
        self.adapter = _Adapter()
        self.host.adapters = {Platform.TELEGRAM: self.adapter}
        self.host.session_store = SessionStore(tmp_path / "sessions", GatewayConfig())

    def __getattr__(self, name):
        return getattr(self.host, name)


@pytest.fixture(autouse=True)
def _unbind():
    delegate_mod.unbind_delegate_coordinator()
    yield
    delegate_mod.unbind_delegate_coordinator()


GATEWAY_SUMMARY_CANARY = "Sachima 的结论：外部 AGENT 的结果已就绪。"


class _SummaryProvider:
    """The host's injected no-tool summariser, as the Gateway composes one."""

    def __init__(self, *, text: str = GATEWAY_SUMMARY_CANARY) -> None:
        self.text = text
        self.calls = 0
        self.sources: list[str] = []
        self.generator_ref = "gateway-stub"

    async def summarize(self, request: Any) -> str:
        self.calls += 1
        self.sources.append(request.source_text)
        return self.text


def _bind(tmp_path: Path, *, facade=None, presets=None, config=None, summary_provider=None):
    facade = _Facade() if facade is None else facade
    config = _config(tmp_path) if config is None else config
    bundle = bind_arsd_execution(
        config,
        facade=facade,
        ledger=ArsdRunBindingLedger(config.binding_ledger_path),
        payload_resolver=delegate_mod.delegate_payload_resolver(),
    )
    coordinator = delegate_mod.SachimaDelegateCoordinator(
        bundle,
        config,
        presets=presets if presets is not None else _catalog(config),
        state=DelegateStateStore(delegate_state_root(config.binding_ledger_path)),
        observe_interval=0.01,
        summary_provider=(
            _SummaryProvider() if summary_provider is None else summary_provider
        ),
    )
    delegate_mod._coordinator = coordinator
    return coordinator, facade


def _origin_for(runner, *, chat_id="chat-1", thread_id=None, anchor="m-1"):
    """The trusted origin the control tool rebuilds from a caller's Session."""

    source = _source(chat_id=chat_id, thread_id=thread_id)
    session = runner.host.session_store.get_or_create_session(source)
    return DelegateOrigin(
        platform=source.platform.value,
        chat_id=source.chat_id,
        thread_id=str(source.thread_id) if source.thread_id else None,
        session_key=session.session_key,
        session_id=session.session_id,
        reply_anchor=anchor,
    )


async def _delegate(
    runner,
    coordinator,
    task_text: str = TASK_TEXT_CANARY,
    *,
    agent_id: str = AGENT_ID,
    chat_id: str = "chat-1",
    delivery=None,
):
    """Create one delegated task exactly the way the control tool does."""

    admission = coordinator.admit_agent(agent_id, task_text=task_text)
    assert admission.admitted, admission.refusal
    return await coordinator.create(
        task_text=task_text,
        preset=admission.preset,
        origin=_origin_for(runner, chat_id=chat_id),
        delivery=delivery,
    )


def _adapter_delivery(runner):
    """The surviving production delivery factory, bound to this host."""

    return runner.host._delegate_delivery_from_origin


async def _until(predicate, *, timeout=10.0):
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return False


async def _await_composed(coro, *, timeout=10.0):
    """Await composed threaded work while keeping the test loop observable."""

    task = asyncio.ensure_future(coro)
    assert await _until(task.done, timeout=timeout)
    return await task


def _run_source() -> str:
    import gateway.run

    return Path(gateway.run.__file__).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# C. Creation over the Gateway seams
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_created_task_carries_the_callers_own_durable_session(tmp_path):
    """The Session is the conversation's, resolved before any delegate write,
    and resolving it reaches no ARS operation of its own."""

    runner = _Host(tmp_path)
    facade = _Facade()
    facade.submit_gate = threading.Event()
    coordinator, _ = _bind(tmp_path, facade=facade)

    running = asyncio.create_task(
        _delegate(runner, coordinator, delivery=None)
    )
    assert await _until(lambda: facade.submit_count() == 1)

    sessions = runner.host.session_store.list_sessions()
    assert len(sessions) == 1
    (turn,) = coordinator.state.list_turns()
    assert turn.origin.session_id == sessions[0].session_id
    assert turn.origin.session_key == sessions[0].session_key
    assert facade.calls.count("session_status") == 0

    facade.submit_gate.set()
    await running
    facade.terminalize(0)


@pytest.mark.asyncio
async def test_the_accepted_receipt_names_the_requested_triple(tmp_path):
    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    coordinator._delivery_factory = _adapter_delivery(runner)

    await _delegate(runner, coordinator)

    assert len(runner.adapter.sent) == 1
    body = runner.adapter.sent[0][1]
    assert body.startswith("🤝 **委派任务已受理**")
    assert f"- 💡: {TASK_TEXT_CANARY}" in body
    assert AGENT_ID in body and "claude-opus-5" in body and "xhigh" in body
    facade.terminalize(0)


@pytest.mark.asyncio
async def test_a_second_task_in_the_same_chat_reuses_the_one_session(tmp_path):
    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    await _delegate(runner, coordinator, "first task")
    facade.terminalize(0)
    await _delegate(runner, coordinator, "second task")
    assert len(runner.host.session_store.list_sessions()) == 1
    session_ids = {turn.origin.session_id for turn in coordinator.state.list_turns()}
    assert len(session_ids) == 1
    facade.terminalize(1)


@pytest.mark.asyncio
async def test_the_task_is_sealed_under_the_exact_canonical_agent_id(tmp_path):
    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    await _delegate(runner, coordinator, "write the notes")
    (turn,) = coordinator.state.list_turns()
    assert turn.agent_id == AGENT_ID
    assert coordinator.state.read_payload(turn.payload_ref) == "write the notes"
    facade.terminalize(0)


# --------------------------------------------------------------------------- #
# E. Terminal delivery through the single-message capability (A16)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_the_terminal_result_is_one_bounded_plain_text_message(tmp_path):
    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    delegate_mod.set_delegate_delivery_factory(_adapter_delivery(runner))
    coordinator._delivery_factory = delegate_mod._delivery_factory_hook

    await _delegate(runner, coordinator)
    huge = "长" * 4000 + FINAL_MESSAGE_CANARY
    facade.terminalize(0, final_message=huge)
    assert await _until(lambda: len(runner.adapter.plain_once) == 1)

    # Exactly one visible body inside the platform's own bound; internal result
    # identity stays in the Hermes handoff, not in the user-facing message.
    (chat_id, body, _metadata) = runner.adapter.plain_once[0]
    assert chat_id == "chat-1"
    assert len(body) <= runner.adapter.MAX_MESSAGE_LENGTH
    (turn,) = coordinator.state.list_turns()
    event = coordinator.state.result_for_turn(turn.turn_key)
    assert event.full_result_ref not in body
    assert body.startswith("✅ **委派任务已完成**")
    assert f"- 💡: {TASK_TEXT_CANARY}" in body
    assert GATEWAY_SUMMARY_CANARY in body
    assert f"- 📄: {GATEWAY_SUMMARY_CANARY}" in body
    assert FINAL_MESSAGE_CANARY not in body
    assert coordinator.state.read_full_result(event.full_result_ref) == huge
    summary = coordinator.state.summary_for_event(event.event_id)
    assert summary.summary_status == "ready"
    assert summary.summary_text == GATEWAY_SUMMARY_CANARY
    # The receipt used ``send``; the terminal did not.
    assert len(runner.adapter.sent) == 1
    delegate_mod.set_delegate_delivery_factory(None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "once_result,once_error,expected",
    [
        (SendResult(success=True, message_id="om_1"), None, "confirmed"),
        (SendResult(success=True, message_id=None), None, "confirmed"),
        (SendResult(success=False, error="down"), None, "failed"),
        (None, RuntimeError("adapter blew up"), "uncertain"),
        ("not a send result", None, "uncertain"),
    ],
)
async def test_the_real_notifier_closure_settles_every_send_branch(
    tmp_path, once_result, once_error, expected
):
    runner = _Host(tmp_path)
    runner.adapter.once_result = once_result
    runner.adapter.once_error = once_error
    coordinator, facade = _bind(tmp_path)
    coordinator._delivery_factory = _adapter_delivery(runner)

    await _delegate(runner, coordinator)
    facade.terminalize(0)
    assert await _until(lambda: len(runner.adapter.plain_once) == 1)
    (turn,) = coordinator.state.list_turns()
    assert await _until(
        lambda: coordinator.state.result_for_turn(turn.turn_key).im_sink == expected
    )


@pytest.mark.asyncio
async def test_an_adapter_exception_on_the_receipt_is_uncertain_not_a_crash(tmp_path):
    runner = _Host(tmp_path)
    runner.adapter.send_error = RuntimeError("chat gone")
    coordinator, facade = _bind(tmp_path)
    coordinator._delivery_factory = _adapter_delivery(runner)

    await _delegate(runner, coordinator)
    (turn,) = coordinator.state.list_turns()
    assert coordinator.state.read_turn(turn.turn_key).receipt == "uncertain"
    assert coordinator.state.read_turn(turn.turn_key).lifecycle == "admitted"
    facade.terminalize(0)


# --------------------------------------------------------------------------- #
# F. Feishu wiring: one low-level text send (A16)
# --------------------------------------------------------------------------- #
def test_feishu_sends_one_low_level_text_frame_and_no_post_or_chunk():
    from plugins.platforms.feishu.adapter import FeishuAdapter

    adapter = FeishuAdapter.__new__(FeishuAdapter)
    adapter._client = object()
    calls: list[dict[str, Any]] = []

    async def _retry(*, chat_id, msg_type, payload, reply_to, metadata):
        calls.append(
            {
                "chat_id": chat_id,
                "msg_type": msg_type,
                "payload": payload,
                "metadata": metadata,
            }
        )
        return SimpleNamespace(code=0, data=SimpleNamespace(message_id="om_feishu"))

    adapter._feishu_send_with_retry = _retry
    adapter._response_succeeded = lambda response: True
    adapter._extract_response_field = lambda response, field: "om_feishu"

    body = "任务 dtask_x 已完成：\n\nresult body\n\n完整结果：dres_abc"
    result = asyncio.run(adapter.send_plain_text_once("oc_chat", body))

    assert result.success is True
    assert result.message_id == "om_feishu"
    assert len(calls) == 1
    assert calls[0]["msg_type"] == "text"
    assert json.loads(calls[0]["payload"]) == {"text": body}


def test_the_feishu_one_message_bound_is_the_platforms_own():
    from plugins.platforms.feishu.adapter import FeishuAdapter

    adapter = FeishuAdapter.__new__(FeishuAdapter)
    assert adapter.max_message_length_for_chat("oc_chat") == FeishuAdapter.MAX_MESSAGE_LENGTH
    assert adapter.message_len_fn_for_chat("oc_chat")("abc") == 3


# --------------------------------------------------------------------------- #
# G. Continuation through the Gateway seam (A14)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_continuation_reuses_the_sealed_task_session_and_agent(tmp_path):
    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    await _delegate(runner, coordinator)
    facade.terminalize(0)
    (turn,) = coordinator.state.list_turns()
    assert await _until(
        lambda: coordinator.state.read_turn(turn.turn_key).lifecycle == "terminal"
    )

    outcome = await coordinator.continue_task(turn.task_ref, "and then this")
    assert outcome.lifecycle == "admitted"
    binding = coordinator.state.read_task(turn.task_ref)
    later = coordinator.state.read_turn(outcome.turn_key)
    assert binding.task_id == later.task_id
    assert binding.spine_session_id == later.spine_session_id
    assert binding.agent_id == later.agent_id == AGENT_ID
    assert later.requested_agent == turn.requested_agent
    assert facade.submit_count() == 2
    assert facade.submitted[1]["request"]["session_id"] == "ARSSESSIONDELEGATE1"
    facade.terminalize(1)


@pytest.mark.asyncio
async def test_concurrent_continuations_nominate_only_one_new_turn(tmp_path):
    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    await _await_composed(_delegate(runner, coordinator))
    facade.terminalize(0)
    (first,) = coordinator.state.list_turns()
    assert await _until(
        lambda: coordinator.state.read_turn(first.turn_key).lifecycle == "terminal"
    )

    outcomes = await asyncio.gather(
        coordinator.continue_task(first.task_ref, "continuation one"),
        coordinator.continue_task(first.task_ref, "continuation two"),
    )

    admitted = [outcome for outcome in outcomes if outcome.lifecycle == "admitted"]
    refused = [
        outcome
        for outcome in outcomes
        if outcome.diagnostic == delegate_mod.SACHIMA_DELEGATE_NOT_CONTINUABLE
    ]
    binding = coordinator.state.read_task(first.task_ref)
    assert len(admitted) == len(refused) == 1
    assert len(binding.turn_keys) == 2
    assert binding.current_turn_key == admitted[0].turn_key
    assert facade.submit_count() == 2
    facade.terminalize(1)


# --------------------------------------------------------------------------- #
# H. Nothing routes on the retired word any more
# --------------------------------------------------------------------------- #
def test_the_slash_access_gate_no_longer_has_a_delegation_command_to_gate():
    """The gate itself is untouched; it simply has one fewer command.

    An unknown word is not admitted by the gate — it is not a command at all,
    so it never reaches the gate's question.
    """

    from gateway.slash_access import SlashAccessPolicy

    policy = SlashAccessPolicy(
        enabled=True,
        admin_user_ids=frozenset({"admin-1"}),
        user_allowed_commands=frozenset({"help"}),
    )
    # The gate still works for a command that still exists.
    assert policy.can_run("admin-1", "background") is True
    assert policy.can_run("user-1", "background") is False
    assert policy.can_run("user-1", "help") is True


def test_the_running_agent_fast_path_kept_every_other_bypass():
    """Removal was surgical: the neighbouring bypasses are still there.

    Asserted on the registry rather than on ``run.py``'s source, because
    upstream v2026.8.31 retired the per-command ``if`` chain this used to read:
    each command now declares its own ``busy_policy`` and the fast path
    dispatches every one of them through ``_dispatch_busy_slash_command``.
    ``/background`` is checked under ``/bg``, the canonical name the same
    upstream change promoted it to. The retired word is still asserted
    textually — a bypass for it must not reappear in either shape.
    """

    from hermes_cli.commands import ACTIVE_SESSION_BYPASS_COMMANDS

    for kept in ("approve", "deny", "agents", "bg", "kanban"):
        cmd = resolve_command(kept)
        assert cmd is not None, f"{kept} no longer resolves"
        assert cmd.busy_policy != "reject", kept
        assert cmd.name in ACTIVE_SESSION_BYPASS_COMMANDS, kept

    assert resolve_command(RETIRED_COMMAND) is None
    assert RETIRED_COMMAND not in ACTIVE_SESSION_BYPASS_COMMANDS
    assert f'_cmd_def_inner.name == "{RETIRED_COMMAND}"' not in _run_source()


# --------------------------------------------------------------------------- #
# I. Trusted Session context and the gated control tool (A5, §2.4)
# --------------------------------------------------------------------------- #
def test_the_gateway_forwards_both_trusted_session_values():
    src = _run_source()
    index = src.index("def _set_session_env(")
    # Bounded by the method's own extent, not by a fixed character budget:
    # upstream keeps growing this prologue, and a fixed window silently stops
    # covering the two kwargs this test exists to check (they sit past 1800
    # characters as of v2026.8.31) — which reads as "the gateway stopped
    # forwarding them" when nothing of the sort happened.
    block = src[index : src.index("\n    def ", index + 1)]
    assert "session_key=context.session_key" in block
    assert "session_id=context.session_id" in block


def test_the_control_tool_is_default_off_and_names_one_toolset(monkeypatch):
    import tools.sachima_delegate_control_tool as control

    monkeypatch.delenv(control.SACHIMA_LIVE_PROGRESS_SURFACE_ENV, raising=False)
    assert control.check_delegate_control_available() is False
    assert control.enabled_control_surface() is None

    monkeypatch.setenv(control.SACHIMA_LIVE_PROGRESS_SURFACE_ENV, "local_offline")
    assert control.check_delegate_control_available() is False

    monkeypatch.setenv(control.SACHIMA_LIVE_PROGRESS_SURFACE_ENV, "hermes_internal")
    assert control.check_delegate_control_available() is True

    from toolsets import _HERMES_CORE_TOOLS

    assert control.TOOL_NAME not in _HERMES_CORE_TOOLS


def test_the_control_tool_fails_closed_without_a_bound_coordinator(monkeypatch):
    import tools.sachima_delegate_control_tool as control

    monkeypatch.setenv(control.SACHIMA_LIVE_PROGRESS_SURFACE_ENV, "hermes_internal")
    delegate_mod.unbind_delegate_coordinator()
    answer = control._handle_delegate_control({"action": "status", "task_ref": "dtask_x"})
    assert control.SACHIMA_DELEGATE_CONTROL_UNBOUND in answer


@pytest.mark.asyncio
async def test_the_control_tool_refuses_a_task_from_another_session(
    tmp_path, monkeypatch
):
    import tools.sachima_delegate_control_tool as control

    monkeypatch.setenv(control.SACHIMA_LIVE_PROGRESS_SURFACE_ENV, "hermes_internal")
    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    await _delegate(runner, coordinator)
    (turn,) = coordinator.state.list_turns()

    control.bind_delegate_control_session_store(runner.host.session_store)
    other = runner.host.session_store.get_or_create_session(
        _source(chat_id="chat-2")
    )
    monkeypatch.setenv("HERMES_SESSION_ID", other.session_id)
    answer = control._handle_delegate_control(
        {"action": "status", "task_ref": turn.task_ref}
    )
    assert control.SACHIMA_DELEGATE_CONTROL_FORBIDDEN in answer
    facade.terminalize(0)


@pytest.mark.asyncio
async def test_the_control_tool_answers_about_its_own_session(tmp_path, monkeypatch):
    import tools.sachima_delegate_control_tool as control

    monkeypatch.setenv(control.SACHIMA_LIVE_PROGRESS_SURFACE_ENV, "hermes_internal")
    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    coordinator.bind_lifecycle_loop(asyncio.get_running_loop())
    await coordinator.restore()
    control.bind_delegate_control_session_store(runner.host.session_store)
    await _await_composed(_delegate(runner, coordinator))
    (turn,) = coordinator.state.list_turns()

    monkeypatch.setenv("HERMES_SESSION_ID", turn.origin.session_id)
    answer = await _await_composed(
        asyncio.to_thread(
            control._handle_delegate_control,
            {"action": "status", "task_ref": turn.task_ref},
        )
    )
    assert turn.task_ref in answer
    assert TASK_TEXT_CANARY not in answer
    facade.terminalize(0)


@pytest.mark.asyncio
async def test_gateway_start_awaits_delegate_restore_before_admissions(
    tmp_path, monkeypatch
):
    """The real startup path owns and awaits the delegate restore barrier."""

    from gateway.config import GatewayConfig
    from gateway.run import GatewayRunner

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    runner = GatewayRunner(
        GatewayConfig(platforms={}, sessions_dir=tmp_path / "sessions")
    )
    coordinator, facade = _bind(tmp_path)
    entered = asyncio.Event()
    release = asyncio.Event()
    original_restore = coordinator._restore_locked

    async def _gated_restore():
        entered.set()
        await release.wait()
        return await original_restore()

    # Gate the restoration scan itself rather than one entry point: startup
    # and every admission funnel through it under the same lock, which is what
    # makes it a barrier instead of a courtesy the caller may skip.
    coordinator._restore_locked = _gated_restore  # type: ignore[method-assign]
    starting = asyncio.create_task(runner.start())
    await asyncio.wait_for(entered.wait(), timeout=5)
    admission_host = _Host(tmp_path / "admission")
    admitted = coordinator.admit_agent(AGENT_ID, task_text=TASK_TEXT_CANARY)
    admission = asyncio.create_task(
        coordinator.create(
            task_text=TASK_TEXT_CANARY,
            preset=admitted.preset,
            origin=_origin_for(admission_host),
        )
    )
    await asyncio.sleep(0.05)

    assert starting.done() is False
    assert admission.done() is False
    assert runner._running is False
    # Eligibility read the roster; the admission itself is still barred.
    assert facade.calls == ["server_info", "agent_list"]

    release.set()
    assert await asyncio.wait_for(starting, timeout=10) is True
    assert (await _await_composed(admission)).lifecycle == "admitted"
    assert coordinator.lifecycle_loop is asyncio.get_running_loop()
    assert coordinator.restored is True
    assert facade.submit_count() == 1
    facade.terminalize(0)


@pytest.mark.asyncio
async def test_tool_continuation_observer_stays_on_the_gateway_owned_loop(
    tmp_path, monkeypatch
):
    """A sync tool return must not strand its newly armed observer."""

    import tools.sachima_delegate_control_tool as control
    from gateway.session_context import clear_session_vars, set_session_vars

    monkeypatch.setenv(control.SACHIMA_LIVE_PROGRESS_SURFACE_ENV, "hermes_internal")
    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    coordinator.bind_lifecycle_loop(asyncio.get_running_loop())
    await coordinator.restore()
    control.bind_delegate_control_session_store(runner.host.session_store)
    await _await_composed(_delegate(runner, coordinator))
    facade.terminalize(0)
    (first,) = coordinator.state.list_turns()
    assert await _until(
        lambda: coordinator.state.read_turn(first.turn_key).lifecycle == "terminal"
    )

    tokens = set_session_vars(
        platform="telegram",
        chat_id="chat-1",
        user_id="user-1",
        session_key=first.origin.session_key,
        session_id=first.origin.session_id,
        message_id="m-2",
    )
    try:
        answer = await _await_composed(
            asyncio.to_thread(
                control._handle_delegate_control,
                {
                    "action": "continue",
                    "task_ref": first.task_ref,
                    "task": "continue from the tool",
                    "round_title": "核对工具续跑这一轮",
                },
            )
        )
    finally:
        clear_session_vars(tokens)

    assert first.task_ref in answer
    assert facade.submit_count() == 2
    facade.terminalize(1)
    binding = coordinator.state.read_task(first.task_ref)
    second_key = binding.current_turn_key
    assert await _until(
        lambda: coordinator.state.read_turn(second_key).lifecycle == "terminal",
        timeout=2,
    )
    assert coordinator.state.result_for_turn(second_key) is not None


@pytest.mark.asyncio
async def test_natural_language_create_uses_the_hosts_trusted_origin(
    tmp_path, monkeypatch
):
    """The Session is context, never an argument: the model names the AGENT
    and the task, and the host supplies who is asking."""

    import tools.sachima_delegate_control_tool as control
    from gateway.session_context import clear_session_vars, set_session_vars

    monkeypatch.setenv(control.SACHIMA_LIVE_PROGRESS_SURFACE_ENV, "hermes_internal")
    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    coordinator.bind_lifecycle_loop(asyncio.get_running_loop())
    await coordinator.restore()
    control.bind_delegate_control_session_store(runner.host.session_store)
    session = runner.host.session_store.get_or_create_session(_source())
    coordinator._delivery_factory = _adapter_delivery(runner)
    tokens = set_session_vars(
        platform="telegram",
        chat_id="chat-1",
        user_id="user-1",
        session_key=session.session_key,
        session_id=session.session_id,
        message_id="m-natural",
    )
    try:
        raw = await _await_composed(
            asyncio.to_thread(
                control._handle_delegate_control,
                {
                    "action": "create",
                    "agent_id": AGENT_ID,
                    "task": TASK_TEXT_CANARY,
                    "task_title": CARD_TITLE_CANARY,
                    "round_title": ROUND_TITLE_CANARY,
                },
            )
        )
    finally:
        clear_session_vars(tokens)

    payload = json.loads(raw)
    (turn,) = coordinator.state.list_turns()
    assert payload["action"] == "create"
    assert payload["result"]["task_ref"] == turn.task_ref
    assert turn.agent_id == AGENT_ID
    assert turn.origin.session_id == session.session_id
    assert turn.origin.reply_anchor == "m-natural"
    assert facade.submit_count() == 1
    facade.terminalize(0)


@pytest.mark.asyncio
async def test_an_agent_switch_creates_a_linked_new_task(tmp_path, monkeypatch):
    """Switching AGENT never rewrites the old binding — it links a new task."""

    import tools.sachima_delegate_control_tool as control
    from gateway.session_context import clear_session_vars, set_session_vars

    monkeypatch.setenv(control.SACHIMA_LIVE_PROGRESS_SURFACE_ENV, "hermes_internal")
    config = _config(
        tmp_path,
        agent_by_policy_ref={"policy_codex": "codex", "policy_cursor": "cursor"},
        model_by_policy_ref={"policy_model": "claude-opus-5"},
        effort_by_policy_ref={"policy_effort": "xhigh"},
    )
    runner = _Host(tmp_path)
    coordinator, facade = _bind(
        tmp_path, config=config, presets=_catalog(config, "codex", "cursor")
    )
    coordinator.bind_lifecycle_loop(asyncio.get_running_loop())
    await coordinator.restore()
    control.bind_delegate_control_session_store(runner.host.session_store)
    session = runner.host.session_store.get_or_create_session(_source())
    coordinator._delivery_factory = _adapter_delivery(runner)
    tokens = set_session_vars(
        platform="telegram",
        chat_id="chat-1",
        user_id="user-1",
        session_key=session.session_key,
        session_id=session.session_id,
        message_id="m-switch",
    )
    try:
        created_raw = await _await_composed(
            asyncio.to_thread(
                control._handle_delegate_control,
                {
                    "action": "create",
                    "agent_id": "codex",
                    "task": TASK_TEXT_CANARY,
                    "task_title": CARD_TITLE_CANARY,
                    "round_title": ROUND_TITLE_CANARY,
                },
            )
        )
        created_ref = json.loads(created_raw)["result"]["task_ref"]
        facade.terminalize(0)
        first_binding = coordinator.state.read_task(created_ref)
        first_key = first_binding.current_turn_key
        assert await _until(
            lambda: coordinator.state.read_turn(first_key).lifecycle == "terminal"
        )
        first_event = coordinator.state.result_for_turn(first_key)

        switched_raw = await _await_composed(
            asyncio.to_thread(
                control._handle_delegate_control,
                {
                    "action": "continue",
                    "task_ref": created_ref,
                    "task": "review the completed work",
                    "agent_id": "cursor",
                    "round_title": "核对换 AGENT 这一轮",
                },
            )
        )
    finally:
        clear_session_vars(tokens)

    switched_ref = json.loads(switched_raw)["result"]["task_ref"]
    original = coordinator.state.read_task(created_ref)
    switched = coordinator.state.read_task(switched_ref)
    assert switched_ref != created_ref
    assert original.turn_keys == (first_key,)
    assert original.agent_id == "codex"
    assert switched.agent_id == "cursor"
    assert switched.task_id != original.task_id
    assert switched.spine_session_id != original.spine_session_id
    assert switched.linked_from == first_event.event_id
    assert switched.origin.session_id == original.origin.session_id
    assert facade.submit_count() == 2
    facade.terminalize(1)


# --------------------------------------------------------------------------- #
# J. Next-turn-only result context (§2.3)
# --------------------------------------------------------------------------- #
def _summary_is_settled(coordinator, turn_key: str) -> bool:
    event = coordinator.state.result_for_turn(turn_key)
    if event is None:
        return False
    summary = coordinator.state.summary_for_event(event.event_id)
    return summary is not None and summary.settled


@pytest.mark.asyncio
async def test_the_result_context_is_owed_to_the_next_turn_and_confirmed_after(
    tmp_path,
):
    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    await _delegate(runner, coordinator)
    facade.terminalize(0)
    (turn,) = coordinator.state.list_turns()
    assert await _until(
        lambda: _summary_is_settled(coordinator, turn.turn_key)
    )

    session_id = turn.origin.session_id
    lines = coordinator.pending_hermes_context(session_id)
    assert len(lines) == 1
    event = coordinator.state.result_for_turn(turn.turn_key)
    assert event.full_result_ref in lines[0]
    assert "summary_source=sachima summary_status=ready" in lines[0]
    assert GATEWAY_SUMMARY_CANARY in lines[0]
    assert FINAL_MESSAGE_CANARY not in lines[0]
    assert coordinator.state.read_result(event.event_id).hermes_sink == "in_flight"

    # Taking it twice does not duplicate it into a second turn.
    assert coordinator.pending_hermes_context(session_id) == ()
    assert coordinator.confirm_hermes_context(session_id) == 1
    assert coordinator.state.read_result(event.event_id).hermes_sink == "confirmed"


@pytest.mark.asyncio
async def test_an_interrupted_handoff_returns_to_pending(tmp_path):
    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    await _delegate(runner, coordinator)
    facade.terminalize(0)
    (turn,) = coordinator.state.list_turns()
    assert await _until(
        lambda: _summary_is_settled(coordinator, turn.turn_key)
    )
    session_id = turn.origin.session_id
    coordinator.pending_hermes_context(session_id)
    assert coordinator.release_hermes_context(session_id) == 1
    assert len(coordinator.pending_hermes_context(session_id)) == 1


HANDOFF_SESSION_KEY = "agent:main:telegram:dm:chat-1:user-1"


def _model_turn_result(**overrides) -> dict[str, Any]:
    result = {
        "final_response": "The delegate finished.",
        "messages": [
            {"role": "user", "content": "what happened?"},
            {"role": "assistant", "content": "The delegate finished."},
        ],
        "tools": [],
        "history_offset": 0,
        "last_prompt_tokens": 0,
        "api_calls": 0,
        "failed": False,
    }
    result.update(overrides)
    return result


def _mark_provider_attempt(kwargs: dict[str, Any]) -> None:
    """Fire what the real agent fires at the provider/model call boundary."""

    handoff = kwargs.get("delegate_handoff")
    if handoff is not None:
        handoff.mark_provider_attempt()


def _handoff_runner(monkeypatch, tmp_path, *, session_id):
    from gateway.config import GatewayConfig, Platform
    from gateway.run import GatewayRunner
    from gateway.session import SessionEntry

    runner = GatewayRunner(GatewayConfig())
    runner.adapters = {}
    runner._running_agents = {}
    runner._running_agents_ts = {}
    runner._pending_messages = {}
    runner._pending_approvals = {}
    runner._set_session_env = lambda _context: None
    runner._session_db = MagicMock()
    runner._recover_telegram_topic_thread_id = lambda _source: None
    runner._cache_session_source = lambda _key, _source: None
    runner._is_session_run_current = lambda _key, _generation: True
    runner._reply_anchor_for_event = lambda _event: None
    runner._get_guild_id = lambda _event: None
    runner._should_send_voice_reply = lambda *_args, **_kwargs: False
    runner.hooks = MagicMock()
    runner.hooks.emit = AsyncMock()
    runner.session_store = MagicMock()
    runner.session_store.get_or_create_session.return_value = SessionEntry(
        session_key="agent:main:telegram:dm:chat-1:user-1",
        session_id=session_id,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 2),
        platform=Platform.TELEGRAM,
        chat_type="dm",
    )
    runner.session_store.load_transcript.return_value = []
    runner.session_store.append_to_transcript = MagicMock()
    runner.session_store.update_session = MagicMock()
    monkeypatch.setattr("gateway.run._hermes_home", tmp_path)
    monkeypatch.setattr(
        "gateway.run._resolve_runtime_agent_kwargs", lambda: {"api_key": "fake"}
    )
    monkeypatch.setattr(
        "agent.model_metadata.get_model_context_length",
        lambda *_args, **_kwargs: 100_000,
    )
    return runner


@pytest.mark.asyncio
async def test_gateway_confirms_handoff_only_after_the_model_turn_consumes_it(
    tmp_path, monkeypatch
):
    """The real message path releases pre-model failure, then confirms success."""

    from gateway.config import Platform
    from gateway.platforms.base import MessageEvent
    from gateway.session import SessionSource

    host = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    await _await_composed(_delegate(host, coordinator))
    facade.terminalize(0)
    (turn,) = coordinator.state.list_turns()
    assert await _until(
        lambda: _summary_is_settled(coordinator, turn.turn_key)
    )
    event = coordinator.state.result_for_turn(turn.turn_key)
    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="chat-1",
        chat_type="dm",
        user_id="user-1",
    )
    message = MessageEvent(text="what happened?", source=source, message_id="m-2")
    runner = _handoff_runner(
        monkeypatch, tmp_path, session_id=turn.origin.session_id
    )
    delegate_mod._coordinator = coordinator

    async def _fail_before_model(name, *_args, **_kwargs):
        if name == "agent:start":
            raise RuntimeError("pre-model failure")

    runner.hooks.emit = AsyncMock(side_effect=_fail_before_model)
    runner._run_agent = AsyncMock()
    await runner._handle_message_with_agent(
        message, source, "agent:main:telegram:dm:chat-1:user-1", 1
    )
    assert runner._run_agent.await_count == 0
    assert coordinator.state.read_result(event.event_id).hermes_sink == "pending"

    # Release the first turn's lease exactly as ``_handle_message``'s finally
    # does. This test is the only one here that drives two turns through
    # ``_handle_message_with_agent`` directly, so it is also the only one that
    # has to do the caller's half of the lease protocol itself — without it the
    # second turn fails closed waiting on the first turn's still-held lease.
    runner._release_turn_lease(HANDOFF_SESSION_KEY, 1)

    runner.hooks.emit = AsyncMock()

    async def _reaches_the_model(**kwargs):
        _mark_provider_attempt(kwargs)
        return _model_turn_result(api_calls=1)

    runner._run_agent = AsyncMock(side_effect=_reaches_the_model)
    await runner._handle_message_with_agent(
        message, source, HANDOFF_SESSION_KEY, 2
    )
    assert "[New message]" in runner._run_agent.await_args.kwargs["message"]
    assert coordinator.state.read_result(event.event_id).hermes_sink == "confirmed"


# --------------------------------------------------------------------------- #
# H2. Settlement evidence: the provider-attempt signal, the claimed Session
# --------------------------------------------------------------------------- #
def test_the_handoff_latch_is_one_way_and_settles_once():
    from gateway.run import _DelegateResultHandoff

    handoff = _DelegateResultHandoff("session-1")
    assert handoff.consumed is False

    handoff.mark_provider_attempt()
    handoff.mark_provider_attempt()
    assert handoff.consumed is True

    assert handoff.take_for_settlement() is True
    assert handoff.take_for_settlement() is False


async def _claimed_handoff(tmp_path, monkeypatch):
    """A terminal delegate result waiting for the next ordinary turn."""

    from gateway.config import Platform
    from gateway.platforms.base import MessageEvent
    from gateway.session import SessionSource

    host = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    await _await_composed(_delegate(host, coordinator))
    facade.terminalize(0)
    (turn,) = coordinator.state.list_turns()
    assert await _until(
        lambda: _summary_is_settled(coordinator, turn.turn_key)
    )
    event = coordinator.state.result_for_turn(turn.turn_key)
    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="chat-1",
        chat_type="dm",
        user_id="user-1",
    )
    message = MessageEvent(text="what happened?", source=source, message_id="m-2")
    runner = _handoff_runner(
        monkeypatch, tmp_path, session_id=turn.origin.session_id
    )
    delegate_mod._coordinator = coordinator
    return runner, coordinator, event, message, source


@pytest.mark.asyncio
async def test_a_pre_provider_budget_denial_leaves_the_handoff_pending(
    tmp_path, monkeypatch
):
    """``api_calls`` counts the iteration, not the provider call.

    ``agent/conversation_loop.py`` increments the counter before the iteration
    budget is admitted, so a turn that exits there never spoke to a model yet
    still reports ``api_calls == 1``. Confirming on that shape loses the
    result; only a started provider attempt may confirm.
    """

    runner, coordinator, event, message, source = await _claimed_handoff(
        tmp_path, monkeypatch
    )

    async def _denied_before_the_provider(**_kwargs):
        return _model_turn_result(api_calls=1, final_response="")

    runner._run_agent = AsyncMock(side_effect=_denied_before_the_provider)
    await runner._handle_message_with_agent(message, source, HANDOFF_SESSION_KEY, 1)

    assert coordinator.state.read_result(event.event_id).hermes_sink == "pending"
    assert runner._run_agent.await_args.kwargs.get("delegate_handoff") is not None


@pytest.mark.asyncio
async def test_a_started_provider_attempt_confirms_through_a_zero_call_followup(
    tmp_path, monkeypatch
):
    """Interruption after the model saw the handoff cannot un-consume it.

    The attempt that carried the handoff reached the provider and was then
    interrupted; the recursive follow-up returns a zero-call result. The
    final result shape says "nothing happened" — the monotonic signal says
    otherwise, and it wins.
    """

    runner, coordinator, event, message, source = await _claimed_handoff(
        tmp_path, monkeypatch
    )

    async def _interrupted_then_zero_calls(**kwargs):
        _mark_provider_attempt(kwargs)
        return _model_turn_result(api_calls=0, interrupted=True)

    runner._run_agent = AsyncMock(side_effect=_interrupted_then_zero_calls)
    await runner._handle_message_with_agent(message, source, HANDOFF_SESSION_KEY, 1)

    session_id = event.session_id
    assert coordinator.state.read_result(event.event_id).hermes_sink == "confirmed"
    # Settled exactly once — nothing is left in flight to confirm or release.
    assert coordinator.confirm_hermes_context(session_id) == 0
    assert coordinator.release_hermes_context(session_id) == 0


@pytest.mark.asyncio
async def test_compression_replacing_the_session_id_still_settles_the_claimed_one(
    tmp_path, monkeypatch
):
    """The claim bound the event to the Session ID trusted at claim time.

    Compression can rotate the live session entry before the turn ends;
    settling against the rotated ID would leave the consumed event stuck
    ``in_flight`` forever.
    """

    runner, coordinator, event, message, source = await _claimed_handoff(
        tmp_path, monkeypatch
    )
    entry = runner.session_store.get_or_create_session.return_value
    claimed_session_id = entry.session_id

    settlements: list[tuple[str, bool, str | None, tuple[str, ...] | None]] = []
    _settle = runner._settle_delegate_result_context

    def _record(
        session_id,
        *,
        consumed,
        continuity=None,
        processing_id=None,
        event_ids=None,
    ):
        settlements.append((session_id, consumed, processing_id, event_ids))
        return _settle(
            session_id,
            consumed=consumed,
            continuity=continuity,
            processing_id=processing_id,
            event_ids=event_ids,
        )

    runner._settle_delegate_result_context = _record

    async def _compresses_mid_turn(**kwargs):
        _mark_provider_attempt(kwargs)
        entry.session_id = "session-after-compression"
        return _model_turn_result(api_calls=1)

    runner._run_agent = AsyncMock(side_effect=_compresses_mid_turn)
    await runner._handle_message_with_agent(message, source, HANDOFF_SESSION_KEY, 1)

    settled = coordinator.state.read_result(event.event_id)
    assert settlements
    assert all(item[0] == claimed_session_id for item in settlements)
    assert all(item[1] is True for item in settlements)
    assert all(item[2] == settled.processing_id for item in settlements)
    assert all(item[3] == (event.event_id,) for item in settlements)
    assert settled.hermes_sink == "confirmed"


class _InterruptThenProviderAgent:
    """A fake agent whose first attempt dies before reaching the provider.

    The interrupt follow-up is the attempt that actually calls the model, so
    the handoff must still be riding along when the recursion runs.
    """

    def __init__(self, **kwargs):
        self.session_id = kwargs["session_id"]
        self.model = kwargs["model"]
        self.tools = []
        self.provider_attempt_callback = None
        self.context_compressor = SimpleNamespace(
            last_prompt_tokens=0, context_length=200000
        )
        self.session_prompt_tokens = 0
        self.session_completion_tokens = 0
        self.turns: list[Any] = []

    def run_conversation(self, user_message, **_kwargs):
        self.turns.append(user_message)
        if len(self.turns) == 1:
            return {
                "final_response": "",
                "messages": [],
                "api_calls": 0,
                "interrupted": True,
                "interrupt_message": "actually, what about now?",
            }
        if self.provider_attempt_callback is not None:
            self.provider_attempt_callback()
        return {"final_response": "done", "messages": [], "api_calls": 1}

    def interrupt(self, *_args, **_kwargs):
        pass


class _RunAgentAdapter:
    SUPPORTS_MESSAGE_EDITING = False
    _pending_messages: dict[str, Any] = {}

    def get_pending_message(self, _session_key):
        return None

    async def send_typing(self, *_args, **_kwargs):
        return None

    async def stop_typing(self, *_args, **_kwargs):
        return None


def _run_agent_runner(session_id: str):
    """The runner seams ``_run_agent`` itself touches, and nothing else."""

    from gateway.config import Platform
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.adapters = {Platform.TELEGRAM: _RunAgentAdapter()}
    runner.config = SimpleNamespace(
        streaming=None,
        group_sessions_per_user=True,
        thread_sessions_per_user=False,
        multiplex_profiles=False,
    )
    runner.hooks = SimpleNamespace(loaded_hooks=False, emit=AsyncMock())
    runner.session_store = SimpleNamespace(
        _entries={}, _save=lambda: None
    )
    runner._session_db = MagicMock()
    runner._session_db.get_telegram_topic_binding_by_session.return_value = None
    runner._agent_cache = {}
    runner._agent_cache_lock = threading.Lock()
    runner._running_agents = {}
    runner._running_agents_ts = {}
    runner._session_run_generation = {}
    runner._session_model_overrides = {}
    runner._pending_model_notes = {}
    runner._pending_skills_reload_notes = {}
    runner._prefill_messages = []
    runner._ephemeral_system_prompt = ""
    runner._reasoning_config = None
    runner._provider_routing = {}
    runner._fallback_model = None
    runner._draining = False
    runner._get_proxy_url = lambda: None
    runner._resolve_session_agent_runtime = lambda **_kwargs: (
        "gpt-5.4",
        {"provider": "openai", "base_url": "https://api.openai.com/v1", "api_key": "token"},
    )
    runner._resolve_session_reasoning_config = lambda **_kwargs: None
    runner._resolve_turn_agent_config = lambda message, model, runtime: {
        "model": model,
        "runtime": runtime,
    }
    runner._load_service_tier = lambda: None
    runner._agent_config_signature = lambda *_args, **_kwargs: ("sig",)
    runner._extract_cache_busting_config = lambda _config: ()
    runner._thread_metadata_for_source = lambda *_args, **_kwargs: None
    runner._sync_telegram_topic_binding = MagicMock()
    runner._release_running_agent_state = MagicMock()
    # Keep the cached agent across the interrupt recursion: the fake model id
    # differs from the gateway config's, which would otherwise read as a
    # fallback switch and evict.
    runner._is_intentional_model_switch = lambda *_args, **_kwargs: True
    return runner


@pytest.mark.asyncio
async def test_the_handoff_rides_into_the_interrupt_followup_that_reaches_the_model(
    monkeypatch,
):
    """``_run_agent`` binds the marker onto the agent and keeps it across the
    interrupt recursion — otherwise the attempt that really called the model
    would leave no trace."""

    import sys
    import types

    from gateway.config import Platform
    from gateway.run import _DelegateResultHandoff
    from gateway.session import SessionSource

    fake_run_agent = types.ModuleType("run_agent")
    fake_run_agent.AIAgent = _InterruptThenProviderAgent
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)
    monkeypatch.setenv("HERMES_TOOL_PROGRESS_MODE", "off")
    monkeypatch.setenv("HERMES_AGENT_TIMEOUT", "0")
    monkeypatch.setattr("gateway.run._load_gateway_config", lambda: {})

    import hermes_cli.tools_config as tools_config

    monkeypatch.setattr(
        tools_config, "_get_platform_tools", lambda *_args, **_kwargs: {"core"}
    )

    runner = _run_agent_runner("session-1")
    source = SessionSource(
        platform=Platform.TELEGRAM, chat_id="12345", chat_type="dm", user_id="user-1"
    )
    handoff = _DelegateResultHandoff("session-1")

    await asyncio.wait_for(
        runner._run_agent(
            message="what happened?",
            context_prompt="",
            history=[],
            source=source,
            session_id="session-1",
            session_key="agent:main:telegram:dm:12345",
            delegate_handoff=handoff,
        ),
        timeout=10,
    )

    agent = runner._agent_cache["agent:main:telegram:dm:12345"][0]
    assert len(agent.turns) == 2
    assert handoff.consumed is True


def test_the_gateway_folds_the_result_into_the_next_user_turn_only():
    """A claim prefixes only the forthcoming user message and binds its IDs."""

    from gateway.platforms.base import MessageEvent
    from gateway.run import GatewayRunner, _DelegateClaimContext

    runner = object.__new__(GatewayRunner)
    claim = SimpleNamespace(
        processing_id="dprocess_folded",
        event_ids=("devt_folded",),
    )
    runner._consume_delegate_result_context = MagicMock(
        return_value=("[external-agent-result] exact result", claim)
    )
    runner._settle_delegate_result_context = MagicMock()
    runner._bind_delegate_processing_receipt = MagicMock()
    event = MessageEvent(
        text="what happened?",
        source=_source(),
        message_id="m-folded",
    )
    context = _DelegateClaimContext(
        session_id="session-folded",
        continuity=None,
        processing_event=event,
    )

    message, handoff = runner._claim_delegate_results_for_turn(
        "what happened?",
        context,
    )

    assert message == (
        "[external-agent-result] exact result\n\n"
        "[New message] what happened?"
    )
    assert handoff is not None
    assert handoff.processing_id == "dprocess_folded"
    assert handoff.event_ids == ("devt_folded",)
    runner._bind_delegate_processing_receipt.assert_called_once_with(
        event,
        ("devt_folded",),
    )


def test_the_handoff_latch_holds_under_concurrent_provider_attempts():
    """Real attempts arrive from worker threads; retries can arrive at once.

    Every attempt may call the latch — only the first transition counts, and
    exactly one caller may settle the claim.
    """

    from gateway.run import _DelegateResultHandoff

    handoff = _DelegateResultHandoff("session-1")
    workers = 16
    ready = threading.Barrier(workers)
    settled: list[bool] = []
    lock = threading.Lock()

    def _attempt():
        ready.wait()
        handoff.mark_provider_attempt()
        taken = handoff.take_for_settlement()
        with lock:
            settled.append(taken)

    threads = [threading.Thread(target=_attempt) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert handoff.consumed is True
    assert settled.count(True) == 1
    assert len(settled) == workers


@pytest.mark.asyncio
async def test_proxy_mode_leaves_the_claimed_handoff_pending():
    """No local agent runs in proxy mode, so nothing may consume the claim."""

    from gateway.config import Platform
    from gateway.run import GatewayRunner, _DelegateResultHandoff
    from gateway.session import SessionSource

    runner = object.__new__(GatewayRunner)
    runner.config = SimpleNamespace(multiplex_profiles=False)
    runner._get_proxy_url = lambda: "https://proxy.invalid"
    runner._run_agent_via_proxy = AsyncMock(
        return_value={"final_response": "from the proxy", "api_calls": 1}
    )
    handoff = _DelegateResultHandoff("session-1")

    result = await runner._run_agent(
        message="what happened?",
        context_prompt="",
        history=[],
        source=SessionSource(
            platform=Platform.TELEGRAM,
            chat_id="12345",
            chat_type="dm",
            user_id="user-1",
        ),
        session_id="session-1",
        session_key=HANDOFF_SESSION_KEY,
        delegate_handoff=handoff,
    )

    assert result["final_response"] == "from the proxy"
    assert runner._run_agent_via_proxy.await_count == 1
    assert handoff.consumed is False


# --------------------------------------------------------------------------- #
# I. Durable terminal delivery: the origin the adapter actually understands
# --------------------------------------------------------------------------- #
# Markdown-special on purpose: asserted byte-for-byte, so any formatting,
# rich-message promotion, chunking or fallback resend on the durable path
# shows up as a changed body or a second call.
TERMINAL_BODY = (
    "任务 dtask_x 已完成:\n\n**not bold** `not code` _not italic_ - a.b (1/2)\n\n"
    "完整结果: dres_abc"
)


def _delegate_origin(*, platform="telegram", chat_id="12345", thread_id=None, anchor="777"):
    from gateway.sachima_delegate_state import DelegateOrigin

    return DelegateOrigin(
        platform=platform,
        chat_id=chat_id,
        thread_id=thread_id,
        session_key="agent:main:telegram:dm:12345:user-1",
        session_id="20260820_000000_abcd1234",
        reply_anchor=anchor,
    )


def _telegram_origin_host():
    """A real Telegram adapter behind the runner's durable delivery factory."""

    from gateway.config import Platform, PlatformConfig
    from plugins.platforms.telegram.adapter import TelegramAdapter
    from gateway.run import GatewayRunner

    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="fake-token"))
    calls: list[dict[str, Any]] = []

    async def _send_message(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(message_id=str(len(calls)))

    adapter._bot = MagicMock()
    adapter._bot.send_message = _send_message

    runner = object.__new__(GatewayRunner)
    runner.adapters = {Platform.TELEGRAM: adapter}
    return runner, adapter, calls


class _OriginAdapter:
    """Records the exact low-level call shape a non-Telegram platform gets."""

    MAX_MESSAGE_LENGTH = 4000

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def single_message_text_limit(self) -> int:
        return self.MAX_MESSAGE_LENGTH

    def measure_text(self, text: str) -> int:
        return len(text or "")

    async def send(self, chat_id, text, reply_to=None, metadata=None):
        self.calls.append(
            {"kind": "send", "chat_id": chat_id, "text": text,
             "reply_to": reply_to, "metadata": metadata}
        )
        return SendResult(success=True, message_id="m_send")

    async def send_plain_text_once(self, chat_id, text, reply_to=None, metadata=None):
        self.calls.append(
            {"kind": "once", "chat_id": chat_id, "text": text,
             "reply_to": reply_to, "metadata": metadata}
        )
        return SendResult(success=True, message_id="m_once")


@pytest.mark.asyncio
async def test_durable_telegram_dm_terminal_replies_once_in_plain_text():
    """The durable anchor has to reach the adapter as an anchor it recognizes."""

    runner, _adapter, calls = _telegram_origin_host()

    delivery = runner._delegate_delivery_from_origin(_delegate_origin())
    result = await delivery.send_plain_text_once(TERMINAL_BODY)

    assert result.success is True
    assert len(calls) == 1
    assert calls[0]["chat_id"] == 12345
    assert calls[0]["text"] == TERMINAL_BODY
    assert calls[0]["parse_mode"] is None
    assert calls[0]["reply_to_message_id"] == 777


@pytest.mark.asyncio
async def test_durable_telegram_dm_topic_terminal_replies_once():
    """A private topic without a recognized anchor refuses before any send."""

    runner, _adapter, calls = _telegram_origin_host()

    delivery = runner._delegate_delivery_from_origin(
        _delegate_origin(thread_id="42")
    )
    result = await delivery.send_plain_text_once(TERMINAL_BODY)

    assert result.success is True
    assert len(calls) == 1
    assert calls[0]["message_thread_id"] == 42
    assert calls[0]["reply_to_message_id"] == 777
    assert calls[0]["text"] == TERMINAL_BODY
    assert calls[0]["parse_mode"] is None


@pytest.mark.asyncio
async def test_durable_telegram_topic_with_reply_mode_off_preserves_topic():
    """``reply_to_mode="off"`` drops the anchor — never the durable topic."""

    runner, adapter, calls = _telegram_origin_host()
    adapter._reply_to_mode = "off"

    delivery = runner._delegate_delivery_from_origin(
        _delegate_origin(thread_id="42")
    )
    result = await delivery.send_plain_text_once(TERMINAL_BODY)

    assert result.success is True
    assert len(calls) == 1
    assert calls[0]["message_thread_id"] == 42
    assert calls[0]["reply_to_message_id"] is None


@pytest.mark.asyncio
async def test_durable_telegram_dm_with_reply_mode_off_sends_without_the_anchor():
    """The ordinary DM honors the operator's setting, and still sends once."""

    runner, adapter, calls = _telegram_origin_host()
    adapter._reply_to_mode = "off"

    delivery = runner._delegate_delivery_from_origin(_delegate_origin())
    result = await delivery.send_plain_text_once(TERMINAL_BODY)

    assert result.success is True
    assert len(calls) == 1
    assert calls[0]["reply_to_message_id"] is None
    assert calls[0]["message_thread_id"] is None


@pytest.mark.asyncio
async def test_durable_telegram_topic_without_an_anchor_still_lands_in_the_topic():
    """An origin can outlive its anchor; the topic still routes the result.

    The lane is ``message_thread_id`` — the Hermes topic the session actually
    runs in. Upstream #87051 made that the preferred anchor-less lane because
    ``direct_messages_topic_id`` renders in a *different* chat lane than the
    topic the session runs in, so asserting the native DM-topic id here would
    be pinning the delivery to the bug that change fixed.
    """

    runner, _adapter, calls = _telegram_origin_host()

    delivery = runner._delegate_delivery_from_origin(
        _delegate_origin(thread_id="42", anchor=None)
    )
    result = await delivery.send_plain_text_once(TERMINAL_BODY)

    assert result.success is True
    assert len(calls) == 1
    assert calls[0]["message_thread_id"] == 42
    assert calls[0].get("direct_messages_topic_id") is None
    assert calls[0]["reply_to_message_id"] is None


@pytest.mark.asyncio
async def test_telegram_group_origin_is_not_promoted_to_private_reply():
    """Only a private chat gets the private-DM treatment. Groups are unchanged."""

    runner, _adapter, calls = _telegram_origin_host()

    delivery = runner._delegate_delivery_from_origin(
        _delegate_origin(chat_id="-1001234567890", thread_id="42")
    )
    result = await delivery.send_plain_text_once(TERMINAL_BODY)

    assert result.success is True
    assert len(calls) == 1
    assert calls[0]["chat_id"] == -1001234567890
    assert calls[0]["message_thread_id"] == 42
    assert calls[0]["reply_to_message_id"] is None
    assert "direct_messages_topic_id" not in calls[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "platform,chat_id",
    [("slack", "C123"), ("feishu", "oc_chat")],
)
async def test_delegate_origin_keeps_slack_and_feishu_call_shapes(platform, chat_id):
    """Generic metadata, no explicit ``reply_to`` — exactly as before."""

    from gateway.config import Platform
    from gateway.run import GatewayRunner

    adapter = _OriginAdapter()
    runner = object.__new__(GatewayRunner)
    runner.adapters = {Platform(platform): adapter}

    delivery = runner._delegate_delivery_from_origin(
        _delegate_origin(platform=platform, chat_id=chat_id, thread_id="t-1", anchor="a-1")
    )
    await delivery.send_plain_text_once(TERMINAL_BODY)
    await delivery.send_text("receipt")

    assert [call["kind"] for call in adapter.calls] == ["once", "send"]
    for call in adapter.calls:
        assert call["chat_id"] == chat_id
        assert call["reply_to"] is None
        assert call["metadata"] == {
            "thread_id": "t-1",
            "reply_to_message_id": "a-1",
        }


# --------------------------------------------------------------------------- #
# J. Turn ownership across cached-agent reuse (H2 continued)
# --------------------------------------------------------------------------- #
# The Gateway caches one ``AIAgent`` per session and rebinds its per-turn
# callbacks in place.  A worker the Gateway has already given up on is still a
# live daemon thread inside that same object, so "which turn does this request
# belong to?" cannot be answered by reading the agent — it has to be decided
# before the executor is scheduled and revoked when the executor is abandoned.


def _provider_agent():
    """A real ``AIAgent`` with a mocked client — no network, no tools."""

    from run_agent import AIAgent

    tool_defs = [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "web_search tool",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    with (
        patch("run_agent.get_tool_definitions", return_value=tool_defs),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("run_agent.OpenAI"),
    ):
        built = AIAgent(
            api_key="test-key-1234567890",
            base_url="https://openrouter.ai/api/v1",
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
        )
    built.client = MagicMock()
    built._cached_system_prompt = "You are helpful."
    built._use_prompt_caching = False
    built.tool_delay = 0
    built.compression_enabled = False
    built.save_trajectories = False
    return built


# --------------------------------------------------------------------------- #
# Production composition — a fresh runner really composes, or composes nothing
#
# Every test here starts from an UNBOUND process and never calls ``_bind``.
# That is the point: before this seam existed the only thing that ever bound a
# coordinator was a test helper, so resident delegation was unreachable in
# production no matter how the deployment was configured.
# --------------------------------------------------------------------------- #
def _composition_files(tmp_path: Path, config, *, agent_ids=(AGENT_ID,)):
    """The three host-owned documents a declared composition names."""

    from gateway.sachima_agent_execution_presets import AGENT_EXECUTION_PRESETS_TYPE
    from gateway.sachima_agent_role_policy import AGENT_ROLE_POLICY_TYPE
    from sachima_supervisor.runtime_spine.arsd_socket_contract import (
        ARSD_SUPERVISOR_CONFIG_TYPE,
    )

    private = tmp_path / "composition"
    private.mkdir(parents=True, exist_ok=True)

    document = {
        "type": ARSD_SUPERVISOR_CONFIG_TYPE,
        "approval_ref": config.approval_ref,
        "owner": config.owner,
        "namespace": config.namespace,
        "socket_path": config.socket_path,
        "binding_ledger_path": config.binding_ledger_path,
        "agent_by_policy_ref": dict(config.agent_by_policy_ref),
        "model_by_policy_ref": dict(config.model_by_policy_ref),
        "effort_by_policy_ref": dict(config.effort_by_policy_ref),
        "workspace_by_ref": dict(config.workspace_by_ref),
        "run_limits_by_policy_ref": {
            k: dict(v) for k, v in config.run_limits_by_policy_ref.items()
        },
        "grant_ref": config.grant_ref,
        "grant_hash": config.grant_hash,
        "grant_role_hash": config.grant_role_hash,
        "grant_capabilities": list(config.grant_capabilities),
        "grant_by_policy_ref": {
            k: list(v) for k, v in config.grant_by_policy_ref.items()
        },
        "mcp_snapshot_hashes": list(config.mcp_snapshot_hashes),
        "credential_refs": list(config.credential_refs),
        "evidence_policy_hash": config.evidence_policy_hash,
        "recovery_policy_hash": config.recovery_policy_hash,
        "enabled": True,
    }
    config_file = private / "arsd-config.json"
    config_file.write_text(json.dumps(document), encoding="utf-8")

    presets_file = private / "presets.json"
    presets_file.write_text(
        json.dumps(
            {
                "type": AGENT_EXECUTION_PRESETS_TYPE,
                "presets": [
                    {
                        "agent_id": agent_id,
                        "workspace_ref": "ws_delegate",
                        "agent_policy_ref": "policy_codex",
                        "model_policy_ref": "policy_model",
                        "effort_policy_ref": "policy_effort",
                        "run_limits_policy_ref": "policy_limits",
                        "permissions": list(config.grant_by_policy_ref["policy_codex"]),
                    }
                    for agent_id in agent_ids
                ],
            }
        ),
        encoding="utf-8",
    )

    policy_file = private / "roles.json"
    policy_file.write_text(
        json.dumps(
            {
                "type": AGENT_ROLE_POLICY_TYPE,
                "assignments": [
                    {
                        "agent_id": agent_id,
                        "division": "engineering",
                        "roles": ["code_review"],
                    }
                    for agent_id in agent_ids
                ],
            }
        ),
        encoding="utf-8",
    )
    return config_file, presets_file, policy_file


def _declare_composition(monkeypatch, config_file, presets_file, policy_file):
    monkeypatch.setenv(delegate_mod.SACHIMA_DELEGATE_COMPOSE_ENV, "1")
    monkeypatch.setenv(
        delegate_mod.SACHIMA_DELEGATE_CONFIG_FILE_ENV, str(config_file)
    )
    monkeypatch.setenv(
        delegate_mod.SACHIMA_DELEGATE_PRESETS_FILE_ENV, str(presets_file)
    )
    monkeypatch.setenv(
        delegate_mod.SACHIMA_DELEGATE_ROLE_POLICY_FILE_ENV, str(policy_file)
    )


@pytest.fixture
def _unbound():
    """Start and end every composition test with nothing bound."""

    delegate_mod.unbind_delegate_coordinator()
    try:
        yield
    finally:
        delegate_mod.unbind_delegate_coordinator()


@pytest.fixture
def _offline_arsd(monkeypatch):
    """Keep composition real but its transport offline.

    Only the daemon socket is substituted: the config document, the presets,
    the role policy, the bundle, and the bind are the production ones.
    """

    import sachima_supervisor.runtime_spine.agent_run_supervisor_execution_binding as binding_mod

    facade = _Facade()
    seen: dict[str, Any] = {}
    real = binding_mod.bind_arsd_execution

    def _offline(config, **kwargs):
        seen["config"] = config
        seen["payload_resolver"] = kwargs.get("payload_resolver")
        kwargs.setdefault("facade", facade)
        kwargs.setdefault("ledger", ArsdRunBindingLedger(config.binding_ledger_path))
        bundle = real(config, **kwargs)
        seen["bundle"] = bundle
        return bundle

    monkeypatch.setattr(binding_mod, "bind_arsd_execution", _offline)
    return SimpleNamespace(facade=facade, seen=seen)


def test_an_undeclared_host_composes_nothing_and_binds_nothing(_unbound, monkeypatch):
    """Default off: the switch absent means no coordinator and no daemon."""

    monkeypatch.delenv(delegate_mod.SACHIMA_DELEGATE_COMPOSE_ENV, raising=False)

    assert delegate_mod.delegate_composition_requested() is False
    assert delegate_mod.compose_delegate_coordinator() is None
    assert delegate_mod.bound_delegate_coordinator() is None


@pytest.mark.parametrize("declared", ["", "0", "true", "yes", "TRUE", " 1"])
def test_an_ambiguous_switch_is_not_a_declaration(_unbound, monkeypatch, declared):
    """A half-set switch on a permissioned execution path means no."""

    monkeypatch.setenv(delegate_mod.SACHIMA_DELEGATE_COMPOSE_ENV, declared)

    assert delegate_mod.delegate_composition_requested() is False
    assert delegate_mod.compose_delegate_coordinator() is None
    assert delegate_mod.bound_delegate_coordinator() is None


def test_a_declared_composition_really_builds_and_binds_the_coordinator(
    tmp_path, monkeypatch, _unbound, _offline_arsd
):
    """The positive case: configured deployment, real graph, bound coordinator."""

    config = _config(tmp_path)
    files = _composition_files(tmp_path, config)
    _declare_composition(monkeypatch, *files)

    assert delegate_mod.bound_delegate_coordinator() is None

    coordinator = delegate_mod.compose_delegate_coordinator()

    assert coordinator is not None
    assert delegate_mod.bound_delegate_coordinator() is coordinator
    # Composed against the declared config, not an invented one.
    assert _offline_arsd.seen["config"].socket_path == config.socket_path
    assert _offline_arsd.seen["config"].enabled is True
    # The claim-check resolver is wired, so a Run recovers its payload.
    assert callable(_offline_arsd.seen["payload_resolver"])
    # The presets and roles the host declared really reached the coordinator.
    assert coordinator.admit_agent(AGENT_ID, task_text=TASK_TEXT_CANARY).preset
    assert _offline_arsd.facade.calls[0] == "server_info"


@pytest.mark.parametrize(
    "missing",
    [
        "SACHIMA_DELEGATE_CONFIG_FILE_ENV",
        "SACHIMA_DELEGATE_PRESETS_FILE_ENV",
        "SACHIMA_DELEGATE_ROLE_POLICY_FILE_ENV",
    ],
)
def test_a_declared_composition_missing_a_document_fails_closed(
    tmp_path, monkeypatch, _unbound, _offline_arsd, missing
):
    """Declared but incomplete binds nothing — it never half-composes."""

    config = _config(tmp_path)
    _declare_composition(monkeypatch, *_composition_files(tmp_path, config))
    monkeypatch.delenv(getattr(delegate_mod, missing), raising=False)

    with pytest.raises(delegate_mod.DelegateCompositionError):
        delegate_mod.compose_delegate_coordinator()

    assert delegate_mod.bound_delegate_coordinator() is None


def test_a_disabled_arsd_config_is_a_declaration_that_composes_nothing(
    tmp_path, monkeypatch, _unbound, _offline_arsd
):
    """``enabled=False`` reaches no daemon, exactly as the contract promises."""

    config = _config(tmp_path)
    config_file, presets_file, policy_file = _composition_files(tmp_path, config)
    document = json.loads(config_file.read_text(encoding="utf-8"))
    document["enabled"] = False
    config_file.write_text(json.dumps(document), encoding="utf-8")
    _declare_composition(monkeypatch, config_file, presets_file, policy_file)

    with pytest.raises(delegate_mod.DelegateCompositionError):
        delegate_mod.compose_delegate_coordinator()

    assert delegate_mod.bound_delegate_coordinator() is None
    assert _offline_arsd.facade.calls == []


def test_a_malformed_config_document_never_becomes_a_coordinator(
    tmp_path, monkeypatch, _unbound, _offline_arsd
):
    """A forged or corrupt document fails the real allowlist, not a pre-check."""

    config = _config(tmp_path)
    config_file, presets_file, policy_file = _composition_files(tmp_path, config)
    document = json.loads(config_file.read_text(encoding="utf-8"))
    document["socket_path"] = "not/an/absolute/private/path"
    config_file.write_text(json.dumps(document), encoding="utf-8")
    _declare_composition(monkeypatch, config_file, presets_file, policy_file)

    with pytest.raises(delegate_mod.DelegateCompositionError) as excinfo:
        delegate_mod.compose_delegate_coordinator()

    # The code, never the rejected material.
    assert str(excinfo.value) == delegate_mod.SACHIMA_DELEGATE_COMPOSITION_INVALID
    assert "not/an/absolute" not in str(excinfo.value)
    assert delegate_mod.bound_delegate_coordinator() is None


@pytest.mark.asyncio
async def test_a_fresh_runner_composes_the_coordinator_during_startup(
    tmp_path, monkeypatch, _unbound, _offline_arsd
):
    """The seam the reviewer asked for: production startup, no manual bind.

    A fresh ``GatewayRunner`` starts with nothing bound. Startup must compose
    the declared graph and *then* restore it, so resident semantic delegation
    is available on the real path rather than only where a test bound it.
    """

    from gateway.config import GatewayConfig
    from gateway.run import GatewayRunner

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    config = _config(tmp_path)
    _declare_composition(monkeypatch, *_composition_files(tmp_path, config))

    runner = GatewayRunner(
        GatewayConfig(platforms={}, sessions_dir=tmp_path / "sessions")
    )
    assert delegate_mod.bound_delegate_coordinator() is None

    assert await asyncio.wait_for(runner.start(), timeout=30) is True

    coordinator = delegate_mod.bound_delegate_coordinator()
    assert coordinator is not None
    assert coordinator.restored is True
    assert coordinator.lifecycle_loop is asyncio.get_running_loop()
    assert runner._running is True


@pytest.mark.asyncio
async def test_an_undeclared_fresh_runner_starts_an_ordinary_gateway(
    tmp_path, monkeypatch, _unbound
):
    """The default deployment is untouched: it starts with nothing bound."""

    from gateway.config import GatewayConfig
    from gateway.run import GatewayRunner

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    monkeypatch.delenv(delegate_mod.SACHIMA_DELEGATE_COMPOSE_ENV, raising=False)

    runner = GatewayRunner(
        GatewayConfig(platforms={}, sessions_dir=tmp_path / "sessions")
    )

    assert await asyncio.wait_for(runner.start(), timeout=30) is True

    assert delegate_mod.bound_delegate_coordinator() is None
    assert runner._running is True


@pytest.mark.asyncio
async def test_a_broken_declaration_still_starts_the_gateway_with_nothing_bound(
    tmp_path, monkeypatch, _unbound, _offline_arsd
):
    """Fail closed, not fail loud: no coordinator, and no crashed Gateway."""

    from gateway.config import GatewayConfig
    from gateway.run import GatewayRunner

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    config = _config(tmp_path)
    config_file, presets_file, policy_file = _composition_files(tmp_path, config)
    config_file.write_text("{ not json", encoding="utf-8")
    _declare_composition(monkeypatch, config_file, presets_file, policy_file)

    runner = GatewayRunner(
        GatewayConfig(platforms={}, sessions_dir=tmp_path / "sessions")
    )

    assert await asyncio.wait_for(runner.start(), timeout=30) is True

    assert delegate_mod.bound_delegate_coordinator() is None
    assert runner._running is True


@pytest.mark.asyncio
async def test_stopping_the_gateway_retires_the_coordinator_it_composed(
    tmp_path, monkeypatch, _unbound, _offline_arsd
):
    """What a runner composes, that runner retires.

    A coordinator left bound after shutdown keeps observers scheduled on a
    loop that is going away and keeps delivery pointed at a stopped runner's
    adapters — and the next start in this process would find it and reuse it.
    """

    from gateway.config import GatewayConfig
    from gateway.run import GatewayRunner
    from tools import sachima_delegate_control_tool as control_tool

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    config = _config(tmp_path)
    _declare_composition(monkeypatch, *_composition_files(tmp_path, config))

    runner = GatewayRunner(
        GatewayConfig(platforms={}, sessions_dir=tmp_path / "sessions")
    )
    assert await asyncio.wait_for(runner.start(), timeout=30) is True

    composed = delegate_mod.bound_delegate_coordinator()
    assert composed is not None
    assert composed.closed is False
    assert control_tool._bound_session_store() is not None

    await asyncio.wait_for(runner.stop(), timeout=30)

    assert composed.closed is True
    assert delegate_mod.bound_delegate_coordinator() is None
    assert delegate_mod._delivery_factory_hook is None
    assert control_tool._bound_session_store() is None
    # Retirement is one-way and safe to repeat.
    await composed.close()
    assert composed.closed is True


@pytest.mark.asyncio
async def test_a_disabled_restart_cannot_reuse_the_previous_runs_coordinator(
    tmp_path, monkeypatch, _unbound, _offline_arsd
):
    """Enabled → stop → disabled must start an ordinary Gateway.

    The global bind is process-wide, so a coordinator that survived the first
    shutdown would still be there for the second start — a deployment that
    turned the feature off would keep serving it from a dead runner's graph.
    """

    from gateway.config import GatewayConfig
    from gateway.run import GatewayRunner

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    config = _config(tmp_path)
    _declare_composition(monkeypatch, *_composition_files(tmp_path, config))

    first = GatewayRunner(
        GatewayConfig(platforms={}, sessions_dir=tmp_path / "sessions")
    )
    assert await asyncio.wait_for(first.start(), timeout=30) is True
    composed = delegate_mod.bound_delegate_coordinator()
    assert composed is not None
    await asyncio.wait_for(first.stop(), timeout=30)

    # The operator turns it off and the process starts a second Gateway.
    monkeypatch.delenv(delegate_mod.SACHIMA_DELEGATE_COMPOSE_ENV, raising=False)
    second = GatewayRunner(
        GatewayConfig(platforms={}, sessions_dir=tmp_path / "sessions2")
    )
    assert await asyncio.wait_for(second.start(), timeout=30) is True

    assert delegate_mod.bound_delegate_coordinator() is None
    assert second._running is True
    assert composed.closed is True

    await asyncio.wait_for(second.stop(), timeout=30)


@pytest.mark.asyncio
async def test_stop_leaves_a_coordinator_this_runner_did_not_compose_alone(
    tmp_path, monkeypatch, _unbound
):
    """A borrowed coordinator is not this runner's to retire.

    An embedding application (or a test) that bound its own graph keeps it:
    tearing it down on an unrelated runner's shutdown would drop a bundle
    whose lifetime this runner never controlled.
    """

    from gateway.config import GatewayConfig
    from gateway.run import GatewayRunner

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    monkeypatch.delenv(delegate_mod.SACHIMA_DELEGATE_COMPOSE_ENV, raising=False)

    external, _facade = _bind(tmp_path)
    runner = GatewayRunner(
        GatewayConfig(platforms={}, sessions_dir=tmp_path / "sessions")
    )
    assert await asyncio.wait_for(runner.start(), timeout=30) is True
    assert delegate_mod.bound_delegate_coordinator() is external

    await asyncio.wait_for(runner.stop(), timeout=30)

    assert delegate_mod.bound_delegate_coordinator() is external
    assert external.closed is False


@pytest.mark.asyncio
async def test_a_retired_coordinator_arms_no_further_observer(
    tmp_path, monkeypatch, _unbound
):
    """Retirement stops observation, not just the tasks already running."""

    external, _facade = _bind(tmp_path)
    await external.close()

    assert external.closed is True
    external._arm_observer("turn-key-1")
    assert external._observers == {}


def _chat_response(content: str = "Final answer"):
    message = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="stop")],
        model="test/model",
        usage=None,
    )


def test_reusing_the_cached_agent_revokes_the_previous_turns_ownership():
    from agent.chat_completion_helpers import ProviderDispatchLease
    from gateway.run import GatewayRunner

    agent = _provider_agent()
    lease = ProviderDispatchLease(None)
    assert agent._activate_provider_dispatch_lease(lease) is True

    GatewayRunner._init_cached_agent_for_turn(agent, 0)

    assert lease.revoked is True


def test_a_stale_worker_cannot_dispatch_through_the_rebound_cached_agent(
    monkeypatch,
):
    """The reproduced production race, through the real reuse seam.

    The old turn is paused inside execution middleware; the Gateway reuses the
    cached agent and rebinds it to the next turn's claim.  When the abandoned
    worker wakes it must dispatch nothing and consume neither claim.
    """

    import hermes_cli.middleware as middleware

    from agent.chat_completion_helpers import ProviderDispatchLease
    from gateway.run import GatewayRunner, _DelegateResultHandoff

    agent = _provider_agent()
    old_claim = _DelegateResultHandoff("session-old")
    new_claim = _DelegateResultHandoff("session-new")
    lease = ProviderDispatchLease(old_claim.mark_provider_attempt)
    agent.provider_attempt_callback = old_claim.mark_provider_attempt
    agent.client.chat.completions.create.return_value = _chat_response()

    entered = threading.Event()
    release = threading.Event()

    def _paused(api_kwargs, next_call, **_kwargs):
        entered.set()
        release.wait(10)
        return next_call(api_kwargs)

    monkeypatch.setattr(middleware, "run_llm_execution_middleware", _paused)

    def _turn():
        with (
            patch.object(agent, "_persist_session"),
            patch.object(agent, "_save_trajectory"),
            patch.object(agent, "_cleanup_task_resources"),
        ):
            agent.run_conversation("hello", _provider_dispatch_lease=lease)

    worker = threading.Thread(target=_turn, daemon=True)
    worker.start()
    assert entered.wait(10) is True

    # The Gateway gave up on that executor and starts the next turn on the
    # same cached instance.
    GatewayRunner._init_cached_agent_for_turn(agent, 0)
    agent.provider_attempt_callback = new_claim.mark_provider_attempt

    release.set()
    worker.join(30)

    assert worker.is_alive() is False
    assert agent.client.chat.completions.create.called is False
    assert old_claim.consumed is False
    assert new_claim.consumed is False
    assert agent._provider_attempts == 0


def test_a_stale_worker_never_commits_the_successor_turns_lease(monkeypatch):
    """The decisive cross-turn race: rebound to a *new* lease, not to nothing.

    Revoking the abandoned turn's lease is not enough on its own. If the
    dispatch reads the lease off the shared cached agent, the successor turn
    has already replaced it by the time the stale worker wakes — so the worker
    finds a perfectly valid lease, dispatches, and confirms a claim belonging
    to a turn it has nothing to do with. The delegate result of the *new* turn
    is then consumed by a request the new turn never made.

    The worker must answer with its own turn's lease, which is revoked.
    """

    import hermes_cli.middleware as middleware

    from agent.chat_completion_helpers import ProviderDispatchLease
    from gateway.run import GatewayRunner, _DelegateResultHandoff

    agent = _provider_agent()
    old_claim = _DelegateResultHandoff("session-old")
    new_claim = _DelegateResultHandoff("session-new")
    old_lease = ProviderDispatchLease(old_claim.mark_provider_attempt)
    new_lease = ProviderDispatchLease(new_claim.mark_provider_attempt)
    agent.client.chat.completions.create.return_value = _chat_response()

    entered = threading.Event()
    release = threading.Event()

    def _paused(api_kwargs, next_call, **_kwargs):
        entered.set()
        release.wait(10)
        return next_call(api_kwargs)

    monkeypatch.setattr(middleware, "run_llm_execution_middleware", _paused)

    def _turn():
        with (
            patch.object(agent, "_persist_session"),
            patch.object(agent, "_save_trajectory"),
            patch.object(agent, "_cleanup_task_resources"),
        ):
            agent.run_conversation("hello", _provider_dispatch_lease=old_lease)

    worker = threading.Thread(target=_turn, daemon=True)
    worker.start()
    assert entered.wait(10) is True

    # The Gateway abandons that executor and binds the cached agent to the
    # NEXT turn's claim — the state the old worker wakes into.
    GatewayRunner._init_cached_agent_for_turn(agent, 0)
    agent._activate_provider_dispatch_lease(new_lease)

    release.set()
    worker.join(30)

    assert worker.is_alive() is False
    assert agent.client.chat.completions.create.called is False
    assert old_claim.consumed is False
    # The whole point: the successor's claim is untouched by its predecessor.
    assert new_claim.consumed is False
    assert new_lease.committed is False
    assert new_claim.take_for_settlement() is True


def test_a_rebind_with_no_lease_leaves_the_stale_worker_refusing(monkeypatch):
    """A successor that holds no lease must not hand the old worker freedom.

    Reading dispatch authority off the agent fails in this direction too: the
    successor is an ordinary un-claimed turn, so the shared attribute says
    "no lease, dispatch freely" — and the abandoned worker takes it.
    """

    import hermes_cli.middleware as middleware

    from agent.chat_completion_helpers import ProviderDispatchLease
    from gateway.run import _DelegateResultHandoff

    agent = _provider_agent()
    old_claim = _DelegateResultHandoff("session-old")
    old_lease = ProviderDispatchLease(old_claim.mark_provider_attempt)
    agent.client.chat.completions.create.return_value = _chat_response()

    entered = threading.Event()
    release = threading.Event()

    def _paused(api_kwargs, next_call, **_kwargs):
        entered.set()
        release.wait(10)
        return next_call(api_kwargs)

    monkeypatch.setattr(middleware, "run_llm_execution_middleware", _paused)

    def _turn():
        with (
            patch.object(agent, "_persist_session"),
            patch.object(agent, "_save_trajectory"),
            patch.object(agent, "_cleanup_task_resources"),
        ):
            agent.run_conversation("hello", _provider_dispatch_lease=old_lease)

    worker = threading.Thread(target=_turn, daemon=True)
    worker.start()
    assert entered.wait(10) is True

    agent._activate_provider_dispatch_lease(None)

    release.set()
    worker.join(30)

    assert worker.is_alive() is False
    assert agent.client.chat.completions.create.called is False
    assert old_claim.consumed is False
    assert old_claim.take_for_settlement() is True


def test_a_client_that_fails_to_build_is_not_a_provider_attempt():
    """Constructing a client is not reaching a model.

    Admitting before the client exists books an attempt for a request that
    never went out, so an interrupted turn's delegate result is consumed and
    lost while no provider ever saw it.
    """

    from agent.chat_completion_helpers import _dispatch_nonstreaming_api_request
    from gateway.run import _DelegateResultHandoff
    from agent.chat_completion_helpers import ProviderDispatchLease

    agent = _provider_agent()
    agent.api_mode = "chat_completions"
    agent.provider = "openrouter"
    claim = _DelegateResultHandoff("session-1")
    lease = ProviderDispatchLease(claim.mark_provider_attempt)

    def _make_client(reason, kind="openai"):
        raise RuntimeError("no socket for you")

    with pytest.raises(RuntimeError):
        _dispatch_nonstreaming_api_request(
            agent, {"model": "test/model"}, make_client=_make_client, lease=lease
        )

    assert claim.consumed is False
    assert lease.committed is False
    assert getattr(agent, "_provider_attempts", 0) == 0
    # Still settleable: nothing was spent, so the result returns to pending.
    assert claim.take_for_settlement() is True


def test_a_built_client_that_dispatches_does_book_the_attempt():
    """The GREEN half of the boundary: a real call still confirms the claim."""

    from agent.chat_completion_helpers import (
        ProviderDispatchLease,
        _dispatch_nonstreaming_api_request,
    )
    from gateway.run import _DelegateResultHandoff

    agent = _provider_agent()
    agent.api_mode = "chat_completions"
    agent.provider = "openrouter"
    claim = _DelegateResultHandoff("session-1")
    lease = ProviderDispatchLease(claim.mark_provider_attempt)

    client = MagicMock()
    client.chat.completions.create.return_value = _chat_response()

    _dispatch_nonstreaming_api_request(
        agent,
        {"model": "test/model"},
        make_client=lambda reason, kind="openai": client,
        lease=lease,
    )

    assert client.chat.completions.create.called is True
    assert claim.consumed is True
    assert agent._provider_attempts == 1


def test_a_revoked_lease_refuses_before_the_client_is_even_built():
    """A refused dispatch must not construct a client, let alone a request."""

    from agent.chat_completion_helpers import (
        ProviderDispatchLease,
        _dispatch_nonstreaming_api_request,
    )
    from gateway.run import _DelegateResultHandoff

    agent = _provider_agent()
    agent.api_mode = "chat_completions"
    agent.provider = "openrouter"
    claim = _DelegateResultHandoff("session-1")
    lease = ProviderDispatchLease(claim.mark_provider_attempt)
    lease.revoke()

    client = MagicMock()

    with pytest.raises(InterruptedError):
        _dispatch_nonstreaming_api_request(
            agent,
            {"model": "test/model"},
            make_client=lambda reason, kind="openai": client,
            lease=lease,
        )

    assert client.chat.completions.create.called is False
    assert claim.consumed is False


def test_no_lease_leaves_every_non_gateway_caller_dispatching_unchanged():
    """CLI / TUI / subagents / evals hold no lease and are not gated."""

    from agent.chat_completion_helpers import _dispatch_nonstreaming_api_request

    agent = _provider_agent()
    agent.api_mode = "chat_completions"
    agent.provider = "openrouter"
    client = MagicMock()
    client.chat.completions.create.return_value = _chat_response()

    _dispatch_nonstreaming_api_request(
        agent,
        {"model": "test/model"},
        make_client=lambda reason, kind="openai": client,
        lease=None,
    )

    assert client.chat.completions.create.called is True
    assert getattr(agent, "_provider_attempts", 0) == 0


def test_the_moa_branch_admits_at_its_own_provider_call():
    """Every api_mode is gated, including the one that builds no client."""

    from agent.chat_completion_helpers import (
        ProviderDispatchLease,
        _dispatch_nonstreaming_api_request,
    )
    from gateway.run import _DelegateResultHandoff

    agent = _provider_agent()
    agent.api_mode = "chat_completions"
    agent.provider = "moa"
    agent.client.chat.completions.create.return_value = _chat_response()
    claim = _DelegateResultHandoff("session-1")
    lease = ProviderDispatchLease(claim.mark_provider_attempt)
    lease.revoke()

    def _make_client(reason, kind="openai"):  # pragma: no cover - must not run
        raise AssertionError("MoA builds no request-local client")

    with pytest.raises(InterruptedError):
        _dispatch_nonstreaming_api_request(
            agent, {"model": "test/model"}, make_client=_make_client, lease=lease
        )

    assert agent.client.chat.completions.create.called is False
    assert claim.consumed is False


def test_a_streaming_turn_is_admitted_under_the_lease_of_its_own_context():
    """Streaming is the ordinary Gateway path and is gated the same way.

    Left ungated, the common path would dispatch without ever confirming the
    claim it folded in — the delegate result would be released back to pending
    and re-folded into a later turn, which is the failure the seam exists for.
    """

    from agent.chat_completion_helpers import (
        ProviderDispatchLease,
        bind_provider_dispatch_lease,
        capture_provider_dispatch_lease,
        active_provider_dispatch_gate,
    )
    from gateway.run import _DelegateResultHandoff

    agent = _provider_agent()
    claim = _DelegateResultHandoff("session-1")
    lease = ProviderDispatchLease(claim.mark_provider_attempt)

    captured: dict[str, object] = {}

    def _in_turn():
        bind_provider_dispatch_lease(lease)
        captured["lease"] = capture_provider_dispatch_lease()
        gate = active_provider_dispatch_gate(agent)
        sdk = MagicMock(return_value="stream")
        captured["result"] = gate.invoke(sdk, model="test/model")
        captured["sdk"] = sdk

    turn = threading.Thread(target=_in_turn, daemon=True)
    turn.start()
    turn.join(10)

    assert captured["lease"] is lease
    assert captured["result"] == "stream"
    assert captured["sdk"].call_count == 1
    assert claim.consumed is True


def test_a_lease_bound_in_one_turn_is_invisible_to_another_context():
    """Turn-locality itself: one turn's binding never leaks into another."""

    from agent.chat_completion_helpers import (
        ProviderDispatchLease,
        bind_provider_dispatch_lease,
        capture_provider_dispatch_lease,
    )

    lease = ProviderDispatchLease(None)
    seen: dict[str, object] = {}

    def _turn_a():
        bind_provider_dispatch_lease(lease)
        seen["a"] = capture_provider_dispatch_lease()

    def _turn_b():
        seen["b"] = capture_provider_dispatch_lease()

    a = threading.Thread(target=_turn_a, daemon=True)
    a.start()
    a.join(10)
    b = threading.Thread(target=_turn_b, daemon=True)
    b.start()
    b.join(10)

    assert seen["a"] is lease
    assert seen["b"] is None


def test_a_synchronous_dispatch_failure_does_not_consume_the_claim():
    """Establishment, not intent, is what the claim may be spent on.

    The client built fine; the SDK call itself refused on the way out. No
    provider saw the request, so consuming here would retire a delegate result
    that was never delivered to a model — and the turn could not settle it.
    """

    from agent.chat_completion_helpers import (
        ProviderDispatchLease,
        _dispatch_nonstreaming_api_request,
    )
    from gateway.run import _DelegateResultHandoff

    agent = _provider_agent()
    agent.api_mode = "chat_completions"
    agent.provider = "openrouter"
    claim = _DelegateResultHandoff("session-1")
    lease = ProviderDispatchLease(claim.mark_provider_attempt)

    client = MagicMock()
    client.chat.completions.create.side_effect = ConnectionError("refused")

    with pytest.raises(ConnectionError):
        _dispatch_nonstreaming_api_request(
            agent,
            {"model": "test/model"},
            make_client=lambda reason, kind="openai": client,
            lease=lease,
        )

    assert client.chat.completions.create.called is True
    assert claim.consumed is False
    assert lease.committed is False
    assert getattr(agent, "_provider_attempts", 0) == 0
    # The turn keeps the right to settle it back to pending.
    assert claim.take_for_settlement() is True


def test_a_failed_then_retried_dispatch_consumes_exactly_once():
    """A retry after a synchronous failure confirms the claim once, not twice."""

    from agent.chat_completion_helpers import (
        ProviderDispatchLease,
        _dispatch_nonstreaming_api_request,
    )
    from gateway.run import _DelegateResultHandoff

    agent = _provider_agent()
    agent.api_mode = "chat_completions"
    agent.provider = "openrouter"
    claim = _DelegateResultHandoff("session-1")
    lease = ProviderDispatchLease(claim.mark_provider_attempt)
    marks = []
    lease_with_counter = ProviderDispatchLease(lambda: marks.append(1))

    client = MagicMock()
    client.chat.completions.create.side_effect = [
        ConnectionError("refused"),
        _chat_response(),
        _chat_response(),
    ]

    def _dispatch():
        return _dispatch_nonstreaming_api_request(
            agent,
            {"model": "test/model"},
            make_client=lambda reason, kind="openai": client,
            lease=lease_with_counter,
        )

    with pytest.raises(ConnectionError):
        _dispatch()
    assert marks == []

    _dispatch()
    assert marks == [1]

    _dispatch()
    assert marks == [1]
    assert agent._provider_attempts == 1


def _anthropic_streaming_agent(monkeypatch, *, stream_error=None):
    """A production-shaped Anthropic streaming turn with an injected client.

    Only the client factory is substituted — the real Anthropic SDK is not
    installed here and building one is out of scope. Everything downstream of
    it (the streaming entry point, the relay attempt, and the establishment
    closure that the lease gates) is the production code path.
    """

    agent = _provider_agent()
    agent.api_mode = "anthropic_messages"
    agent.provider = "anthropic"
    agent._disable_streaming = False

    opened: dict[str, Any] = {"calls": 0}

    class _Manager:
        def __init__(self, raw):
            self._raw = raw

        def __enter__(self):
            return self._raw

        def __exit__(self, *exc):
            return False

    def _stream(**kwargs):
        opened["calls"] += 1
        opened["kwargs"] = kwargs
        if stream_error is not None:
            raise stream_error
        raw = MagicMock()
        raw.__iter__ = lambda self: iter(())
        raw.response = None
        return _Manager(raw)

    client = MagicMock()
    client.messages.stream.side_effect = _stream
    monkeypatch.setattr(
        agent, "_create_request_anthropic_client", lambda **_k: client, raising=False
    )
    return agent, client, opened


def test_an_abandoned_turn_cannot_open_an_anthropic_stream(monkeypatch):
    """The native Anthropic streaming branch answers to the same lease.

    Before this it opened ``messages.stream`` directly, so the one production
    path a Gateway turn most often takes could dispatch under a lease it no
    longer held.
    """

    from agent.chat_completion_helpers import (
        ProviderDispatchLease,
        bind_provider_dispatch_lease,
        interruptible_streaming_api_call,
    )
    from gateway.run import _DelegateResultHandoff

    agent, client, opened = _anthropic_streaming_agent(monkeypatch)
    claim = _DelegateResultHandoff("session-1")
    lease = ProviderDispatchLease(claim.mark_provider_attempt)
    lease.revoke()

    outcome: dict[str, Any] = {}

    def _turn():
        bind_provider_dispatch_lease(lease)
        try:
            interruptible_streaming_api_call(agent, {"model": "claude-opus-5"})
        except BaseException as exc:  # noqa: BLE001 - recorded, then asserted
            outcome["error"] = exc

    worker = threading.Thread(target=_turn, daemon=True)
    worker.start()
    worker.join(30)

    assert worker.is_alive() is False
    # Never opened: refused before the SDK was touched at all.
    assert opened["calls"] == 0
    assert client.messages.stream.called is False
    assert claim.consumed is False
    assert claim.take_for_settlement() is True


def test_a_live_anthropic_stream_establishment_consumes_exactly_once(monkeypatch):
    """The GREEN half: a real establishment confirms the turn's claim once."""

    from agent.chat_completion_helpers import (
        ProviderDispatchLease,
        bind_provider_dispatch_lease,
        interruptible_streaming_api_call,
    )
    from gateway.run import _DelegateResultHandoff

    agent, client, opened = _anthropic_streaming_agent(monkeypatch)
    claim = _DelegateResultHandoff("session-1")
    marks: list[int] = []
    lease = ProviderDispatchLease(lambda: (marks.append(1), claim.mark_provider_attempt())[0])

    def _turn():
        bind_provider_dispatch_lease(lease)
        try:
            interruptible_streaming_api_call(agent, {"model": "claude-opus-5"})
        except BaseException:  # noqa: BLE001 - establishment is what is asserted
            pass

    worker = threading.Thread(target=_turn, daemon=True)
    worker.start()
    worker.join(30)

    assert worker.is_alive() is False
    assert opened["calls"] >= 1
    assert claim.consumed is True
    # Confirmed once no matter how many attempts the relay opened.
    assert marks == [1]


def test_an_anthropic_stream_that_fails_to_open_does_not_consume(monkeypatch):
    """A stream that refused on the way out established nothing."""

    from agent.chat_completion_helpers import (
        ProviderDispatchLease,
        bind_provider_dispatch_lease,
        interruptible_streaming_api_call,
    )
    from gateway.run import _DelegateResultHandoff

    agent, client, opened = _anthropic_streaming_agent(
        monkeypatch, stream_error=ConnectionError("refused")
    )
    claim = _DelegateResultHandoff("session-1")
    lease = ProviderDispatchLease(claim.mark_provider_attempt)

    def _turn():
        bind_provider_dispatch_lease(lease)
        try:
            interruptible_streaming_api_call(agent, {"model": "claude-opus-5"})
        except BaseException:  # noqa: BLE001 - the refusal is expected
            pass

    worker = threading.Thread(target=_turn, daemon=True)
    worker.start()
    worker.join(30)

    assert worker.is_alive() is False
    assert opened["calls"] >= 1
    assert claim.consumed is False
    assert claim.take_for_settlement() is True


def test_abandoning_a_timed_out_turn_retires_its_lease_immediately(monkeypatch):
    """Settlement follows abandonment, so the lease must die with the turn.

    The worker may be parked just short of its provider call and has not
    observed the interrupt. Waiting for the next cached-agent reuse to revoke
    leaves it free to wake and confirm a claim already settled.
    """

    from agent.chat_completion_helpers import ProviderDispatchLease
    from gateway.run import _DelegateResultHandoff, _abandon_timed_out_gateway_turn

    agent = _provider_agent()
    claim = _DelegateResultHandoff("session-1")
    lease = ProviderDispatchLease(claim.mark_provider_attempt)
    agent._activate_provider_dispatch_lease(lease)

    monkeypatch.setattr(
        "gateway.run.request_hard_interrupt", lambda *a, **k: None, raising=False
    )
    monkeypatch.setattr(
        "gateway.run._dump_wedged_turn_stacks", lambda *a, **k: None, raising=False
    )
    monkeypatch.setattr(
        "gateway.run._reap_gateway_turn_processes", lambda *a, **k: None, raising=False
    )

    abandoned = _abandon_timed_out_gateway_turn(
        agent_holder=[agent],
        task_id="task-1",
        process_baseline=None,
        worker_done=threading.Event(),
        timeout_fired=threading.Event(),
        cleanup_lock=threading.Lock(),
        dispatch_lease=lease,
    )

    assert abandoned is True
    assert lease.cancelled is True

    # A delayed worker waking now dispatches nothing and confirms nothing.
    gate = lease.gate(agent)
    sdk = MagicMock()
    with pytest.raises(InterruptedError):
        gate.invoke(sdk, model="test/model")

    assert sdk.call_count == 0
    assert claim.consumed is False
    assert claim.take_for_settlement() is True


# --------------------------------------------------------------------------- #
# The execution lifecycle fence
#
# One invariant, four production paths: shutdown, abandonment and closure must
# fence every new provider dispatch and every coordinator-owned task *before*
# anything outside can observe the terminal, timed-out or restored state they
# publish. Each test below drives the real path and asserts the ordering or the
# identity that makes the fence real — never the source text.
# --------------------------------------------------------------------------- #
def _bedrock_streaming_agent(monkeypatch, *, stream_error, converse_result=None):
    """A production-shaped Bedrock streaming turn with an injected client."""

    import agent.bedrock_adapter as bedrock_adapter

    agent = _provider_agent()
    agent.api_mode = "bedrock_converse"
    agent.provider = "bedrock"
    agent._disable_streaming = False

    calls: list[str] = []
    client = MagicMock()

    def _converse_stream(**_kwargs):
        calls.append("converse_stream")
        raise stream_error

    def _converse(**_kwargs):
        calls.append("converse")
        return converse_result if converse_result is not None else {}

    client.converse_stream.side_effect = _converse_stream
    client.converse.side_effect = _converse
    monkeypatch.setattr(
        bedrock_adapter, "_get_bedrock_runtime_client", lambda _r: client
    )
    monkeypatch.setattr(
        bedrock_adapter, "is_streaming_access_denied_error", lambda _e: True
    )
    monkeypatch.setattr(
        bedrock_adapter, "normalize_converse_response", lambda raw: raw
    )
    monkeypatch.setattr(
        bedrock_adapter, "recover_from_cache_point_rejection", lambda _e, _k: None
    )
    return agent, client, calls


def test_a_revoked_turn_cannot_dispatch_through_the_bedrock_iam_fallback(
    monkeypatch,
):
    """The IAM fallback is a second real dispatch and answers to the lease.

    ``converse_stream`` is denied, so the branch falls back to a fresh
    non-streaming ``converse``. Ungated, an abandoned turn that was refused the
    stream would still put that fallback request on the wire.
    """

    from agent.chat_completion_helpers import (
        ProviderDispatchLease,
        bind_provider_dispatch_lease,
        interruptible_streaming_api_call,
    )
    from gateway.run import _DelegateResultHandoff

    agent, client, calls = _bedrock_streaming_agent(
        monkeypatch, stream_error=PermissionError("AccessDeniedException")
    )
    claim = _DelegateResultHandoff("session-1")
    lease = ProviderDispatchLease(claim.mark_provider_attempt)
    lease.revoke()

    def _turn():
        bind_provider_dispatch_lease(lease)
        try:
            interruptible_streaming_api_call(
                agent, {"model": "anthropic.claude", "__bedrock_region__": "us-east-1"}
            )
        except BaseException:  # noqa: BLE001 - the refusal is the assertion
            pass

    worker = threading.Thread(target=_turn, daemon=True)
    worker.start()
    worker.join(30)

    assert worker.is_alive() is False
    assert "converse" not in calls
    assert client.converse.called is False
    assert claim.consumed is False
    assert claim.take_for_settlement() is True


def test_a_bedrock_iam_fallback_that_establishes_consumes_exactly_once(monkeypatch):
    """The GREEN half: the fallback confirms the claim once, not twice.

    The refused stream established nothing, so the single commit must come
    from the fallback that actually reached the model.
    """

    from agent.chat_completion_helpers import (
        ProviderDispatchLease,
        bind_provider_dispatch_lease,
        interruptible_streaming_api_call,
    )
    from gateway.run import _DelegateResultHandoff

    agent, client, calls = _bedrock_streaming_agent(
        monkeypatch,
        stream_error=PermissionError("AccessDeniedException"),
        converse_result={"output": {"message": {"content": []}}},
    )
    claim = _DelegateResultHandoff("session-1")
    marks: list[int] = []
    lease = ProviderDispatchLease(
        lambda: (marks.append(1), claim.mark_provider_attempt())[0]
    )

    def _turn():
        bind_provider_dispatch_lease(lease)
        try:
            interruptible_streaming_api_call(
                agent, {"model": "anthropic.claude", "__bedrock_region__": "us-east-1"}
            )
        except BaseException:  # noqa: BLE001 - establishment is the assertion
            pass

    worker = threading.Thread(target=_turn, daemon=True)
    worker.start()
    worker.join(30)

    assert worker.is_alive() is False
    assert calls.count("converse") >= 1
    assert claim.consumed is True
    assert marks == [1]


def test_the_timeout_fence_closes_before_the_timeout_becomes_observable(
    monkeypatch,
):
    """Ordering, not merely eventual cancellation.

    Publishing ``timeout_fired`` is what releases settlement and lets the next
    turn rebind the cached agent. Any observer that sees the timeout must
    already find this turn's lease dead, or a worker can dispatch into a turn
    the Gateway is settling.
    """

    from agent.chat_completion_helpers import ProviderDispatchLease
    from gateway.run import _DelegateResultHandoff, _abandon_timed_out_gateway_turn

    agent = _provider_agent()
    agent._gateway_turn_process_task_id = "task-1"
    claim = _DelegateResultHandoff("session-1")
    lease = ProviderDispatchLease(claim.mark_provider_attempt)
    agent._activate_provider_dispatch_lease(lease)

    monkeypatch.setattr(
        "gateway.run.request_hard_interrupt", lambda *a, **k: None, raising=False
    )
    monkeypatch.setattr(
        "gateway.run._dump_wedged_turn_stacks", lambda *a, **k: None, raising=False
    )
    monkeypatch.setattr(
        "gateway.run._reap_gateway_turn_processes", lambda *a, **k: None, raising=False
    )

    timeout_fired = threading.Event()
    observed: dict[str, Any] = {}

    class _WitnessEvent(threading.Event):
        """Records the lease state at the instant the timeout is published."""

        def set(self) -> None:  # type: ignore[override]
            observed["cancelled_at_publication"] = lease.cancelled
            super().set()

    witness = _WitnessEvent()

    _abandon_timed_out_gateway_turn(
        agent_holder=[agent],
        task_id="task-1",
        process_baseline=None,
        worker_done=threading.Event(),
        timeout_fired=witness,
        cleanup_lock=threading.Lock(),
        dispatch_lease=lease,
    )

    assert witness.is_set() is True
    # The fence was already closed when the timeout became observable.
    assert observed["cancelled_at_publication"] is True
    assert lease.cancelled is True
    assert timeout_fired.is_set() is False


def test_abandonment_never_cancels_a_successor_turns_lease(monkeypatch):
    """Identity, not whatever the shared cached agent currently points at.

    The reaper runs on its own thread and can land after the cached agent has
    been rebound to the next turn. Cancelling the lease it finds there would
    kill a live turn instead of the abandoned one.
    """

    from agent.chat_completion_helpers import ProviderDispatchLease
    from gateway.run import _DelegateResultHandoff, _abandon_timed_out_gateway_turn

    agent = _provider_agent()
    abandoned_claim = _DelegateResultHandoff("session-abandoned")
    abandoned_lease = ProviderDispatchLease(abandoned_claim.mark_provider_attempt)
    successor_claim = _DelegateResultHandoff("session-successor")
    successor_lease = ProviderDispatchLease(successor_claim.mark_provider_attempt)

    # The cached agent already belongs to the NEXT turn by the time the
    # abandoned turn's reaper thread finally runs.
    agent._gateway_turn_process_task_id = "task-successor"
    agent._activate_provider_dispatch_lease(successor_lease)

    monkeypatch.setattr(
        "gateway.run.request_hard_interrupt", lambda *a, **k: None, raising=False
    )
    monkeypatch.setattr(
        "gateway.run._dump_wedged_turn_stacks", lambda *a, **k: None, raising=False
    )
    monkeypatch.setattr(
        "gateway.run._reap_gateway_turn_processes", lambda *a, **k: None, raising=False
    )

    _abandon_timed_out_gateway_turn(
        agent_holder=[agent],
        task_id="task-abandoned",
        process_baseline=None,
        worker_done=threading.Event(),
        timeout_fired=threading.Event(),
        cleanup_lock=threading.Lock(),
        dispatch_lease=abandoned_lease,
    )

    # The abandoned turn's own lease is fenced; the successor is untouched
    # and can still dispatch and confirm.
    assert abandoned_lease.cancelled is True
    assert successor_lease.cancelled is False
    gate = successor_lease.gate(agent)
    sdk = MagicMock(return_value="ok")
    assert gate.invoke(sdk, model="test/model") == "ok"
    assert successor_claim.consumed is True


def test_a_same_session_predecessor_reaper_fences_only_its_own_lease(monkeypatch):
    """Schedule 1: the reaper fences exactly the lease handed to it.

    Two turns of the *same* session share one cached agent and one
    session-scoped task id, so no ownership marker on the agent can tell the
    predecessor's reaper apart from the successor's live lease. The reaper
    must cancel L1 — the object it was constructed with — and never L2.
    """

    from agent.chat_completion_helpers import ProviderDispatchLease
    from gateway.run import (
        GatewayRunner,
        _DelegateResultHandoff,
        _abandon_timed_out_gateway_turn,
    )

    agent = _provider_agent()
    predecessor_claim = _DelegateResultHandoff("session-1")
    successor_claim = _DelegateResultHandoff("session-1")
    l1 = ProviderDispatchLease(predecessor_claim.mark_provider_attempt)
    l2 = ProviderDispatchLease(successor_claim.mark_provider_attempt)

    # Turn one binds L1; the Gateway then starts turn two of the same session
    # on the same cached agent, under the same session-scoped task id.
    agent._gateway_turn_process_task_id = "session-1"
    agent._activate_provider_dispatch_lease(l1)
    GatewayRunner._init_cached_agent_for_turn(agent, 0)
    agent._activate_provider_dispatch_lease(l2)

    monkeypatch.setattr(
        "gateway.run.request_hard_interrupt", lambda *a, **k: None, raising=False
    )
    monkeypatch.setattr(
        "gateway.run._dump_wedged_turn_stacks", lambda *a, **k: None, raising=False
    )
    monkeypatch.setattr(
        "gateway.run._reap_gateway_turn_processes", lambda *a, **k: None, raising=False
    )

    # Turn one's reaper finally fires, carrying turn one's lease.
    abandoned = _abandon_timed_out_gateway_turn(
        agent_holder=[agent],
        task_id="session-1",
        process_baseline=None,
        worker_done=threading.Event(),
        timeout_fired=threading.Event(),
        cleanup_lock=threading.Lock(),
        dispatch_lease=l1,
    )

    assert abandoned is True
    assert l1.cancelled is True
    assert l2.cancelled is False
    assert l2.revoked is False
    gate = l2.gate(agent)
    sdk = MagicMock(return_value="ok")
    assert gate.invoke(sdk, model="test/model") == "ok"
    assert successor_claim.consumed is True
    assert predecessor_claim.consumed is False


def test_a_lease_abandoned_before_worker_publication_binds_dead(monkeypatch):
    """Schedule 2: the lease exists before the worker is scheduled, so the
    reaper can fence it before the worker has published its agent at all.
    When the worker finally binds that lease it is already dead: the provider
    SDK is never called and the claim stays unconsumed for settlement."""

    from agent.chat_completion_helpers import ProviderDispatchLease
    from gateway.run import _DelegateResultHandoff, _abandon_timed_out_gateway_turn

    agent = _provider_agent()
    claim = _DelegateResultHandoff("session-1")
    lease = ProviderDispatchLease(claim.mark_provider_attempt)
    # Nothing published yet: the worker has not reached agent binding.
    agent_holder: list[Any] = [None]

    monkeypatch.setattr(
        "gateway.run.request_hard_interrupt", lambda *a, **k: None, raising=False
    )
    monkeypatch.setattr(
        "gateway.run._dump_wedged_turn_stacks", lambda *a, **k: None, raising=False
    )
    monkeypatch.setattr(
        "gateway.run._reap_gateway_turn_processes", lambda *a, **k: None, raising=False
    )

    abandoned = _abandon_timed_out_gateway_turn(
        agent_holder=agent_holder,
        task_id="session-1",
        process_baseline=None,
        worker_done=threading.Event(),
        timeout_fired=threading.Event(),
        cleanup_lock=threading.Lock(),
        dispatch_lease=lease,
    )
    assert abandoned is True
    assert lease.cancelled is True

    # The worker wakes late, publishes its agent and binds the turn's lease.
    agent_holder[0] = agent
    assert agent._activate_provider_dispatch_lease(lease) is True
    gate = lease.gate(agent)
    sdk = MagicMock()
    with pytest.raises(InterruptedError):
        gate.invoke(sdk, model="test/model")

    assert sdk.call_count == 0
    assert lease.committed is False
    assert claim.consumed is False
    assert claim.take_for_settlement() is True


class _LeaseWitnessAgent(_InterruptThenProviderAgent):
    """A fake agent that records the lease each turn was handed."""

    leases: list[Any] = []

    def run_conversation(self, user_message, **kwargs):
        type(self).leases.append(kwargs.get("_provider_dispatch_lease"))
        self.turns.append(user_message)
        lease = kwargs.get("_provider_dispatch_lease")
        if lease is not None:
            lease.gate(self).invoke(lambda: "ok")
        return {"final_response": "done", "messages": [], "api_calls": 1}


@pytest.mark.asyncio
async def test_the_turns_lease_is_built_before_scheduling_and_shared_with_the_reaper(
    monkeypatch,
):
    """The turn owns one lease: built beside the timeout machinery before the
    worker is scheduled, handed to the watchdog reaper explicitly, and the
    very object the worker dispatches under."""

    import sys
    import types

    from agent.chat_completion_helpers import ProviderDispatchLease
    from gateway.config import Platform
    from gateway.run import _DelegateResultHandoff
    from gateway.session import SessionSource

    _LeaseWitnessAgent.leases = []
    fake_run_agent = types.ModuleType("run_agent")
    fake_run_agent.AIAgent = _LeaseWitnessAgent
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)
    monkeypatch.setenv("HERMES_TOOL_PROGRESS_MODE", "off")
    monkeypatch.setenv("HERMES_AGENT_TIMEOUT", "1800")
    monkeypatch.setattr("gateway.run._load_gateway_config", lambda: {})

    import hermes_cli.tools_config as tools_config

    monkeypatch.setattr(
        tools_config, "_get_platform_tools", lambda *_args, **_kwargs: {"core"}
    )

    watchdog: dict[str, Any] = {}

    def _watchdog(**kwargs):
        watchdog.update(kwargs)

    monkeypatch.setattr("gateway.run._watch_gateway_turn_inactivity", _watchdog)

    runner = _run_agent_runner("session-1")
    source = SessionSource(
        platform=Platform.TELEGRAM, chat_id="12345", chat_type="dm", user_id="user-1"
    )
    handoff = _DelegateResultHandoff("session-1")

    await asyncio.wait_for(
        runner._run_agent(
            message="what happened?",
            context_prompt="",
            history=[],
            source=source,
            session_id="session-1",
            session_key="agent:main:telegram:dm:12345",
            delegate_handoff=handoff,
        ),
        timeout=10,
    )

    (lease,) = _LeaseWitnessAgent.leases
    assert isinstance(lease, ProviderDispatchLease)
    assert "dispatch_lease" in watchdog
    assert watchdog["dispatch_lease"] is lease
    assert lease.committed is True
    assert handoff.consumed is True


@pytest.mark.asyncio
async def test_closing_a_coordinator_fences_admission_and_owns_no_orphan(
    tmp_path, _unbound
):
    """The concurrent-admission canary.

    ``close`` and owner-task creation must not cross. Whichever order they
    race in, the outcome is one of exactly two: the task was registered and
    the drain cancelled and awaited it, or admission was refused and no task
    exists. A task created after the drain snapshot would survive retirement
    still holding its turn lock.
    """

    coordinator, _facade = _bind(tmp_path)
    coordinator.bind_lifecycle_loop(asyncio.get_running_loop())

    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow():
        started.set()
        await release.wait()
        return "done"

    admitted = asyncio.create_task(coordinator._exclusive("turn-1", _slow))
    await asyncio.wait_for(started.wait(), timeout=5)

    closing = asyncio.create_task(coordinator.close())
    await asyncio.sleep(0)
    release.set()
    await asyncio.wait_for(closing, timeout=10)

    assert coordinator.closed is True
    # The in-flight owner was drained, not orphaned.
    assert coordinator._lifecycle.tasks == frozenset()
    assert coordinator._observers == {}
    with pytest.raises((asyncio.CancelledError, RuntimeError)):
        await admitted

    # Every later admission is refused deterministically.
    for _ in range(8):
        with pytest.raises(RuntimeError):
            await coordinator._exclusive("turn-2", _slow)
    assert coordinator._lifecycle.tasks == frozenset()


@pytest.mark.asyncio
async def test_a_closed_coordinator_refuses_a_captured_thread_caller(
    tmp_path, _unbound
):
    """A worker thread holding a pre-retirement reference gets no new work."""

    coordinator, _facade = _bind(tmp_path)
    coordinator.bind_lifecycle_loop(asyncio.get_running_loop())
    await coordinator.close()

    outcome: dict[str, Any] = {}

    def _captured_caller():
        async def _factory():
            return "should not run"

        try:
            coordinator.run_on_lifecycle_loop(_factory)
        except BaseException as exc:  # noqa: BLE001 - recorded, then asserted
            outcome["error"] = exc

    worker = threading.Thread(target=_captured_caller, daemon=True)
    worker.start()
    await asyncio.get_running_loop().run_in_executor(None, worker.join, 10)

    assert isinstance(outcome.get("error"), RuntimeError)


@pytest.mark.asyncio
async def test_an_unreadable_turn_ledger_fails_restoration_closed(tmp_path, _unbound):
    """An unreadable ledger is not an empty one.

    Treating the error as "no turns" declares the startup barrier complete,
    so the coordinator starts admitting new work beside in-flight Runs it
    never observed.
    """

    from gateway.sachima_delegate_state import DelegateStateError

    coordinator, _facade = _bind(tmp_path)
    coordinator.bind_lifecycle_loop(asyncio.get_running_loop())

    def _unreadable():
        raise DelegateStateError("sachima_delegate_state_unreadable")

    coordinator._state.list_turns = _unreadable  # type: ignore[method-assign]

    with pytest.raises(DelegateStateError):
        await coordinator.restore()

    assert coordinator.restored is False


@pytest.mark.asyncio
async def test_a_partial_restore_failure_retires_the_composed_coordinator(
    tmp_path, monkeypatch, _unbound, _offline_arsd
):
    """The partial-restore cleanup canary.

    Restoration arms owned work as it goes, so a failure partway through can
    leave observers running. Unbinding alone hides the coordinator while those
    tasks keep driving a half-restored graph on the Gateway loop.
    """

    from gateway.config import GatewayConfig
    from gateway.run import GatewayRunner
    from gateway.sachima_delegate_state import DelegateStateError
    from tools import sachima_delegate_control_tool as control_tool

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    config = _config(tmp_path)
    _declare_composition(monkeypatch, *_composition_files(tmp_path, config))

    armed: dict[str, Any] = {}
    real_restore = delegate_mod.SachimaDelegateCoordinator._restore_locked

    async def _partial_restore(self):
        # Arm a real owned task, then fail — the half-restored shape.
        async def _parked():
            await asyncio.Event().wait()

        task = self._lifecycle.spawn(_parked)
        armed["task"] = task
        armed["coordinator"] = self
        raise DelegateStateError("sachima_delegate_state_unreadable")

    monkeypatch.setattr(
        delegate_mod.SachimaDelegateCoordinator,
        "_restore_locked",
        _partial_restore,
    )

    runner = GatewayRunner(
        GatewayConfig(platforms={}, sessions_dir=tmp_path / "sessions")
    )
    assert await asyncio.wait_for(runner.start(), timeout=30) is True

    composed = armed["coordinator"]
    assert composed.closed is True
    assert armed["task"].done() is True
    assert composed._lifecycle.tasks == frozenset()
    assert delegate_mod.bound_delegate_coordinator() is None
    assert delegate_mod._delivery_factory_hook is None
    assert control_tool._bound_session_store() is None
    # Ordinary Gateway startup is unaffected.
    assert runner._running is True
    assert real_restore is not None

    await asyncio.wait_for(runner.stop(), timeout=30)


@pytest.mark.asyncio
async def test_a_borrowed_coordinator_is_unbound_but_never_closed_on_restore_failure(
    tmp_path, monkeypatch, _unbound
):
    """A graph this runner did not compose is not its to retire."""

    from gateway.config import GatewayConfig
    from gateway.run import GatewayRunner
    from gateway.sachima_delegate_state import DelegateStateError

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    monkeypatch.delenv(delegate_mod.SACHIMA_DELEGATE_COMPOSE_ENV, raising=False)

    external, _facade = _bind(tmp_path)

    def _unreadable():
        raise DelegateStateError("sachima_delegate_state_unreadable")

    external._state.list_turns = _unreadable  # type: ignore[method-assign]

    runner = GatewayRunner(
        GatewayConfig(platforms={}, sessions_dir=tmp_path / "sessions")
    )
    assert await asyncio.wait_for(runner.start(), timeout=30) is True

    # Fail-closed: hidden from new callers, but still the owner's object.
    assert delegate_mod.bound_delegate_coordinator() is None
    assert external.closed is False
    assert runner._running is True

    await asyncio.wait_for(runner.stop(), timeout=30)


def test_cancel_first_leaves_the_claim_unconsumed_for_settlement():
    from agent.chat_completion_helpers import ProviderDispatchLease
    from gateway.run import _DelegateResultHandoff

    agent = _provider_agent()
    claim = _DelegateResultHandoff("session-1")
    lease = ProviderDispatchLease(claim.mark_provider_attempt)
    gate = lease.gate(agent)

    lease.cancel()
    sdk = MagicMock()
    with pytest.raises(InterruptedError):
        gate.invoke(sdk, model="test/model")

    assert sdk.call_count == 0
    assert claim.consumed is False
    assert claim.take_for_settlement() is True


def test_commit_first_confirms_the_claim_and_cancellation_cannot_revert_it():
    from agent.chat_completion_helpers import ProviderDispatchLease
    from gateway.run import _DelegateResultHandoff

    agent = _provider_agent()
    claim = _DelegateResultHandoff("session-1")
    lease = ProviderDispatchLease(claim.mark_provider_attempt)
    gate = lease.gate(agent)
    sdk = MagicMock(return_value="ok")

    assert gate.invoke(sdk, model="test/model") == "ok"
    assert claim.consumed is True

    lease.cancel()

    assert claim.consumed is True
    with pytest.raises(InterruptedError):
        gate.invoke(sdk, model="test/model")
    assert sdk.call_count == 1
    assert claim.take_for_settlement() is True


def test_a_legacy_run_conversation_double_is_never_handed_the_private_lease():
    """Old shims and suite doubles take the request and nothing else."""

    from agent.chat_completion_helpers import (
        ProviderDispatchLease,
        provider_dispatch_lease_kwargs,
    )
    from run_agent import AIAgent

    lease = ProviderDispatchLease(None)

    class _LegacyDouble:
        def run_conversation(self, message, conversation_history=None, task_id=None):
            return {}

    assert provider_dispatch_lease_kwargs(_LegacyDouble().run_conversation, lease) == {}
    assert provider_dispatch_lease_kwargs(AIAgent.run_conversation, lease) == {
        "_provider_dispatch_lease": lease
    }
    assert provider_dispatch_lease_kwargs(AIAgent.run_conversation, None) == {}


# --------------------------------------------------------------------------- #
# S3 — the host's card capability, per origin
#
# The delegation status card is a Feishu capability, so the host offers it only
# where the adapter can really send *and* patch one in place. Everywhere else
# the delivery is byte-for-byte the plain-text capability it already was.
# --------------------------------------------------------------------------- #
class _CardAdapter(_OriginAdapter):
    """A Feishu-shaped adapter: both interactive-card seams, recorded."""

    MAX_MESSAGE_LENGTH = 8000

    def __init__(self) -> None:
        super().__init__()
        self.cards: list[dict[str, Any]] = []
        self.patches: list[tuple[str, dict[str, Any]]] = []

    async def send_interactive_card(self, chat_id, card, *, reply_to=None, metadata=None):
        self.cards.append({"chat_id": chat_id, "card": card, "metadata": metadata})
        return SendResult(success=True, message_id="om_card")

    async def patch_interactive_card(self, chat_id, message_id, card, *, finalize=False):
        self.patches.append((message_id, card))
        return SendResult(success=True, message_id=message_id)


def _card_origin_host():
    from gateway.config import Platform
    from gateway.run import GatewayRunner

    adapter = _CardAdapter()
    runner = object.__new__(GatewayRunner)
    runner.adapters = {Platform.FEISHU: adapter}
    return runner, adapter


def _feishu_origin(thread_id: str | None = None) -> DelegateOrigin:
    return DelegateOrigin(
        platform="feishu",
        chat_id="oc_chat",
        thread_id=thread_id,
        session_key="feishu:oc_chat",
        session_id="20260826_000000_abcd1234",
        reply_anchor=None,
    )


@pytest.mark.asyncio
async def test_a_feishu_origin_is_card_capable_and_keeps_its_call_shape():
    runner, adapter = _card_origin_host()
    delivery = runner._delegate_delivery_from_origin(_feishu_origin(thread_id="th_1"))

    assert delivery.card_capable is True
    assert delivery.limit == _CardAdapter.MAX_MESSAGE_LENGTH

    card = {"config": {}, "header": {}, "elements": []}
    sent = await delivery.send_card(card)
    assert sent.message_id == "om_card"
    assert adapter.cards[0]["chat_id"] == "oc_chat"
    assert adapter.cards[0]["card"] is card
    assert adapter.cards[0]["metadata"]["thread_id"] == "th_1"

    patched = await delivery.patch_card("om_card", card)
    assert patched.success is True
    assert adapter.patches == [("om_card", card)]


@pytest.mark.asyncio
async def test_an_adapter_without_both_card_seams_stays_on_the_plain_path():
    from gateway.config import Platform
    from gateway.run import GatewayRunner

    adapter = _OriginAdapter()
    runner = object.__new__(GatewayRunner)
    runner.adapters = {Platform.FEISHU: adapter}
    delivery = runner._delegate_delivery_from_origin(_feishu_origin())

    assert delivery.card_capable is False
    assert delivery.send_card is None
    assert delivery.patch_card is None
    await delivery.send_plain_text_once("plain body")
    assert adapter.calls[0]["kind"] == "once"


@pytest.mark.asyncio
async def test_a_telegram_origin_is_never_offered_a_card():
    runner, _adapter, _calls = _telegram_origin_host()
    delivery = runner._delegate_delivery_from_origin(_delegate_origin())
    assert delivery.card_capable is False
