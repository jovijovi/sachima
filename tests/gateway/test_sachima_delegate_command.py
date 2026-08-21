"""S6 — ``/delegate [@AGENT] <task>`` end to end through the Gateway seams.

What is proven here:

* **exactly one** delegate ``CommandDef`` exists, it is gateway-only, its
  argument hint is ``[@AGENT] <task>``, the Gateway knows it — and no ``ars``
  command, alias, or subcommand was minted beside it;
* both Gateway paths — the cold slash path and the running-agent fast path —
  reach the *same* handler, and the running-agent path neither interrupts the
  active turn nor enters one;
* empty text answers with the usage line and creates **nothing**; a raw typed
  ``@name`` refuses with no Session, no durable write, and no auto-route;
* a valid routed request resolves exactly one durable Hermes Session **before**
  the first delegate write, and no ARS operation happens during that resolution;
* the accepted receipt goes out through the injected adapter sender and carries
  exactly ``requested_agent`` / ``requested_model`` / ``requested_effort``; the
  handler then returns empty so no second copy is sent;
* the terminal result reaches the adapter through ``send_plain_text_once`` as one
  visible body inside the platform bound, carrying the durable full-result ref —
  and Feishu sends it as one low-level ``msg_type="text"``, never a post or a
  chunk;
* continuation reuses the sealed task, Session, profile, and AGENT;
* the real handler closure settles every ``SendResult`` branch, adapter
  exceptions included.

Everything is offline: no adapter connection, socket, daemon, network, or AGENT.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import threading
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import gateway.sachima_delegate as delegate_mod
from gateway.platforms.base import MentionOccurrence, SendResult
from gateway.sachima_delegate_policy import (
    DELEGATE_POLICY_TYPE,
    build_delegate_policy,
    synthesize_legacy_policy,
)
from gateway.sachima_delegate_state import DelegateStateStore, delegate_state_root
from hermes_cli.commands import (
    COMMAND_REGISTRY,
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
    FINAL_MESSAGE_CANARY,
    TASK_TEXT_CANARY,
    _Facade,
    _config,
)

DELEGATE = "delegate"


# --------------------------------------------------------------------------- #
# A. Registration (A1)
# --------------------------------------------------------------------------- #
def test_exactly_one_delegate_command_is_registered():
    matches = [cmd for cmd in COMMAND_REGISTRY if cmd.name == DELEGATE]
    assert len(matches) == 1
    (delegate,) = matches
    assert delegate.args_hint == "[@AGENT] <task>"
    assert delegate.gateway_only is True
    assert delegate.cli_only is False
    assert delegate.aliases == ()
    assert delegate.subcommands == ()
    assert delegate.gateway_config_gate is None


def test_the_gateway_knows_delegate_and_resolves_it_to_itself():
    assert DELEGATE in GATEWAY_KNOWN_COMMANDS
    resolved = resolve_command(DELEGATE)
    assert resolved is not None and resolved.name == DELEGATE
    assert resolve_command("/delegate").name == DELEGATE
    assert should_bypass_active_session(DELEGATE) is True


def test_no_ars_command_was_minted_beside_it():
    assert resolve_command("ars") is None
    assert "ars" not in GATEWAY_KNOWN_COMMANDS
    assert [cmd for cmd in COMMAND_REGISTRY if cmd.name == "ars"] == []
    for cmd in COMMAND_REGISTRY:
        assert "ars" not in cmd.aliases


def test_delegate_appears_once_in_every_gateway_surface():
    help_lines = [line for line in gateway_help_lines() if "/delegate" in line]
    assert len(help_lines) == 1
    assert "`/delegate [@AGENT] <task>`" in help_lines[0]

    menu = [name for name, _description in telegram_bot_commands() if name == DELEGATE]
    assert menu == [DELEGATE]


def test_delegate_stays_out_of_the_cli_surfaces():
    from hermes_cli.commands import COMMANDS, COMMANDS_BY_CATEGORY

    assert "/delegate" not in COMMANDS
    for category in COMMANDS_BY_CATEGORY.values():
        assert "/delegate" not in category


# --------------------------------------------------------------------------- #
# B. The host harness
# --------------------------------------------------------------------------- #
class _Event:
    """The minimum of a ``MessageEvent`` the delegate handler reads."""

    def __init__(self, args: str, *, chat_id="chat-1", thread_id=None, occurrences=()):
        from gateway.config import Platform
        from gateway.session import SessionSource

        self._args = args
        self.text = f"/delegate {args}".rstrip() if args else "/delegate"
        self.source = SessionSource(
            platform=Platform.TELEGRAM,
            chat_id=chat_id,
            chat_type="dm",
            user_id="user-1",
            thread_id=thread_id,
        )
        self.message_id = "m-1"
        self.mention_occurrences = tuple(occurrences)

    def get_command(self) -> str:
        return DELEGATE

    def get_command_args(self) -> str:
        return self._args


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


class _Host:
    """The slash mixin plus the four runner seams a delegate reply needs."""

    def __init__(self, tmp_path: Path):
        from gateway.config import GatewayConfig, Platform
        from gateway.session import SessionStore
        from gateway.slash_commands import GatewaySlashCommandsMixin

        class _Concrete(GatewaySlashCommandsMixin):
            @staticmethod
            def _reply_anchor_for_event(event):
                return event.message_id

            @staticmethod
            def _thread_metadata_for_source(source, anchor=None):
                return {"thread_id": source.thread_id, "reply_to_message_id": anchor}

        self.host = _Concrete()
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


def _bind(tmp_path: Path, *, facade=None, policy=None, config=None):
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
        policy=policy or synthesize_legacy_policy(config),
        state=DelegateStateStore(delegate_state_root(config.binding_ledger_path)),
        observe_interval=0.01,
    )
    delegate_mod._coordinator = coordinator
    return coordinator, facade


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


# --------------------------------------------------------------------------- #
# C. Refusals create nothing (A2, A5)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_empty_text_returns_the_usage_line_and_creates_nothing(tmp_path):
    runner = _Host(tmp_path)
    reply = await runner.host._handle_delegate_command(_Event(""))
    assert reply == delegate_mod.DELEGATE_USAGE
    assert delegate_mod.bound_delegate_coordinator() is None
    assert runner.adapter.sent == []
    assert runner.host.session_store.list_sessions() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("blank", ["   ", "\n", "\t "])
async def test_whitespace_only_text_is_also_empty(tmp_path, blank):
    runner = _Host(tmp_path)
    reply = await runner.host._handle_delegate_command(_Event(blank))
    assert reply == delegate_mod.DELEGATE_USAGE
    assert runner.host.session_store.list_sessions() == []


@pytest.mark.asyncio
async def test_a_raw_typed_selector_refuses_before_any_session_exists(tmp_path):
    """A2: an unverifiable selector never falls through to automatic routing."""

    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    reply = await runner.host._handle_delegate_command(_Event("@Alice do the thing"))
    assert reply == delegate_mod.DELEGATE_UNVERIFIED_SELECTOR
    assert runner.host.session_store.list_sessions() == []
    assert coordinator.state.list_turns() == ()
    assert facade.submit_count() == 0
    assert runner.adapter.sent == []


@pytest.mark.asyncio
async def test_an_unmapped_structured_selector_refuses_with_the_choices(tmp_path):
    runner = _Host(tmp_path)
    config = _config(tmp_path)
    policy = build_delegate_policy(
        {
            "type": DELEGATE_POLICY_TYPE,
            "profiles": [
                {
                    "profile_id": "author",
                    "workspace_ref": "ws_delegate",
                    "agent_policy_ref": "policy_author",
                    "model_policy_ref": "policy_model",
                    "effort_policy_ref": "policy_effort",
                    "run_limits_policy_ref": "policy_limits",
                    "summary": "writes things",
                }
            ],
        },
        config,
    )
    coordinator, facade = _bind(tmp_path, policy=policy)
    event = _Event(
        "@Bob do the thing",
        occurrences=(
            MentionOccurrence(
                platform_user_id="tg_bob", start=10, end=14, rendered="@Bob"
            ),
        ),
    )
    reply = await runner.host._handle_delegate_command(event)
    assert "author" in reply
    assert runner.host.session_store.list_sessions() == []
    assert facade.submit_count() == 0


@pytest.mark.asyncio
async def test_an_unbound_host_refuses_without_creating_anything(tmp_path):
    runner = _Host(tmp_path)
    reply = await runner.host._handle_delegate_command(_Event("do the thing"))
    assert reply == delegate_mod.DELEGATE_UNAVAILABLE
    assert reply != delegate_mod.DELEGATE_USAGE
    assert runner.adapter.sent == []
    assert runner.host.session_store.list_sessions() == []


# --------------------------------------------------------------------------- #
# D. The accepted path (A5, A11)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_valid_request_creates_one_session_before_the_first_write(tmp_path):
    runner = _Host(tmp_path)
    facade = _Facade()
    facade.submit_gate = threading.Event()
    coordinator, _ = _bind(tmp_path, facade=facade)

    running = asyncio.create_task(
        runner.host._handle_delegate_command(_Event(TASK_TEXT_CANARY))
    )
    assert await _until(lambda: facade.submit_count() == 1)

    sessions = runner.host.session_store.list_sessions()
    assert len(sessions) == 1
    (turn,) = coordinator.state.list_turns()
    assert turn.origin.session_id == sessions[0].session_id
    assert turn.origin.session_key == sessions[0].session_key
    # Session resolution reached no ARS operation of its own.
    assert facade.calls.count("session_status") == 0

    facade.submit_gate.set()
    reply = await running
    # The receipt was delivered here; the handler adds no second copy.
    assert reply == ""
    assert len(runner.adapter.sent) == 1
    body = runner.adapter.sent[0][1]
    assert "author-agent" in body and "claude-opus-5" in body and "xhigh" in body
    assert TASK_TEXT_CANARY not in body
    facade.terminalize(0)


@pytest.mark.asyncio
async def test_a_second_delegate_in_the_same_chat_reuses_the_one_session(tmp_path):
    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    await runner.host._handle_delegate_command(_Event("first task"))
    facade.terminalize(0)
    await runner.host._handle_delegate_command(_Event("second task"))
    assert len(runner.host.session_store.list_sessions()) == 1
    session_ids = {turn.origin.session_id for turn in coordinator.state.list_turns()}
    assert len(session_ids) == 1
    facade.terminalize(1)


@pytest.mark.asyncio
async def test_a_verified_structured_selector_routes_to_its_profile(tmp_path):
    runner = _Host(tmp_path)
    config = _config(tmp_path)
    policy = build_delegate_policy(
        {
            "type": DELEGATE_POLICY_TYPE,
            "profiles": [
                {
                    "profile_id": "author",
                    "workspace_ref": "ws_delegate",
                    "agent_policy_ref": "policy_author",
                    "model_policy_ref": "policy_model",
                    "effort_policy_ref": "policy_effort",
                    "run_limits_policy_ref": "policy_limits",
                    "mentions": [
                        {"platform": "telegram", "platform_user_id": "tg_author"}
                    ],
                }
            ],
        },
        config,
    )
    coordinator, facade = _bind(tmp_path, policy=policy)
    event = _Event(
        "@Author write the notes",
        occurrences=(
            MentionOccurrence(
                platform_user_id="tg_author", start=10, end=17, rendered="@Author"
            ),
        ),
    )
    reply = await runner.host._handle_delegate_command(event)
    assert reply == ""
    (turn,) = coordinator.state.list_turns()
    assert turn.profile_id == "author"
    # Only the qualifying occurrence was removed from the task.
    assert coordinator.state.read_payload(turn.payload_ref) == "write the notes"
    facade.terminalize(0)


# --------------------------------------------------------------------------- #
# E. Terminal delivery through the single-message capability (A16)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_the_terminal_result_is_one_bounded_plain_text_message(tmp_path):
    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    delegate_mod.set_delegate_delivery_factory(
        lambda origin: runner.host._delegate_delivery_for(
            SimpleNamespace(
                platform=__import__(
                    "gateway.config", fromlist=["Platform"]
                ).Platform.TELEGRAM,
                chat_id=origin.chat_id,
                thread_id=origin.thread_id,
            ),
            origin.reply_anchor,
        )
    )
    coordinator._delivery_factory = delegate_mod._delivery_factory_hook

    await runner.host._handle_delegate_command(_Event(TASK_TEXT_CANARY))
    huge = "长" * 4000 + FINAL_MESSAGE_CANARY
    facade.terminalize(0, final_message=huge)
    assert await _until(lambda: len(runner.adapter.plain_once) == 1)

    # Exactly one visible body, inside the platform's own bound, carrying the
    # durable ref — and nothing went through the ordinary chunking send.
    (chat_id, body, _metadata) = runner.adapter.plain_once[0]
    assert chat_id == "chat-1"
    assert len(body) <= runner.adapter.MAX_MESSAGE_LENGTH
    (turn,) = coordinator.state.list_turns()
    event = coordinator.state.result_for_turn(turn.turn_key)
    assert event.full_result_ref in body
    assert coordinator.state.read_full_result(event.full_result_ref) == huge
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

    from gateway.config import Platform

    coordinator._delivery_factory = lambda origin: runner.host._delegate_delivery_for(
        SimpleNamespace(
            platform=Platform.TELEGRAM,
            chat_id=origin.chat_id,
            thread_id=origin.thread_id,
        ),
        origin.reply_anchor,
    )
    await runner.host._handle_delegate_command(_Event(TASK_TEXT_CANARY))
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
    reply = await runner.host._handle_delegate_command(_Event(TASK_TEXT_CANARY))
    assert reply == ""
    (turn,) = coordinator.state.list_turns()
    assert coordinator.state.read_turn(turn.turn_key).receipt == "uncertain"
    assert coordinator.state.read_turn(turn.turn_key).lifecycle == "admitted"
    facade.terminalize(0)


# --------------------------------------------------------------------------- #
# F. Feishu wiring: one low-level text send (A16)
# --------------------------------------------------------------------------- #
def test_feishu_sends_one_low_level_text_frame_and_no_post_or_chunk():
    from gateway.platforms.feishu import FeishuAdapter

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
    from gateway.platforms.feishu import FeishuAdapter

    adapter = FeishuAdapter.__new__(FeishuAdapter)
    assert adapter.single_message_text_limit() == FeishuAdapter.MAX_MESSAGE_LENGTH
    assert adapter.measure_text("abc") == 3


# --------------------------------------------------------------------------- #
# G. Continuation through the Gateway seam (A14)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_continuation_reuses_the_sealed_task_session_and_agent(tmp_path):
    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    await runner.host._handle_delegate_command(_Event(TASK_TEXT_CANARY))
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
    assert binding.profile_id == later.profile_id
    assert later.requested_agent == turn.requested_agent
    assert facade.submit_count() == 2
    assert facade.submitted[1]["request"]["session_id"] == "ARSSESSIONDELEGATE1"
    facade.terminalize(1)


@pytest.mark.asyncio
async def test_concurrent_continuations_nominate_only_one_new_turn(tmp_path):
    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    await _await_composed(
        runner.host._handle_delegate_command(_Event(TASK_TEXT_CANARY))
    )
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
# H. Both Gateway routes reach the same handler (A1)
# --------------------------------------------------------------------------- #
def _run_source() -> str:
    import gateway.run

    return Path(gateway.run.__file__).read_text(encoding="utf-8")


def test_both_gateway_routes_call_the_one_handler():
    src = _run_source()
    assert src.count("_handle_delegate_command(event)") == 2
    assert 'if canonical == "delegate"' in src
    assert '_cmd_def_inner.name == "delegate"' in src


def test_the_active_agent_route_neither_interrupts_nor_enters_the_turn():
    src = _run_source()
    marker = '_cmd_def_inner.name == "delegate"'
    index = src.index(marker)
    branch = src[index : index + 400]
    assert "return await self._handle_delegate_command(event)" in branch
    assert "_interrupt_and_clear_session" not in branch
    assert "interrupt(" not in branch
    assert "_enqueue_fifo" not in branch
    assert "_pending_messages" not in branch


def test_the_running_agent_route_sits_under_the_existing_slash_access_gate():
    from hermes_cli.commands import is_gateway_known_command
    from gateway.slash_access import SlashAccessPolicy

    assert is_gateway_known_command(DELEGATE) is True
    policy = SlashAccessPolicy(
        enabled=True,
        admin_user_ids=frozenset({"admin-1"}),
        user_allowed_commands=frozenset({"help"}),
    )
    assert policy.can_run("admin-1", DELEGATE) is True
    assert policy.can_run("user-1", DELEGATE) is False

    src = _run_source()
    gate = src.index("_denied = self._check_slash_access(source, _cmd_def_inner.name)")
    delegate_branch = src.index('_cmd_def_inner.name == "delegate"')
    assert gate < delegate_branch

    cold_gate = src.index("_denied = self._check_slash_access(source, canonical)")
    cold_branch = src.index('if canonical == "delegate"')
    assert cold_gate < cold_branch


def test_the_handler_is_async_and_lives_on_the_slash_commands_mixin():
    from gateway.slash_commands import GatewaySlashCommandsMixin

    handler = GatewaySlashCommandsMixin._handle_delegate_command
    assert asyncio.iscoroutinefunction(handler)
    signature = inspect.signature(handler)
    assert list(signature.parameters) == ["self", "event"]


# --------------------------------------------------------------------------- #
# I. Trusted Session context and the gated control tool (A5, §2.4)
# --------------------------------------------------------------------------- #
def test_the_gateway_forwards_both_trusted_session_values():
    src = _run_source()
    index = src.index("def _set_session_env(")
    block = src[index : index + 1800]
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
    await runner.host._handle_delegate_command(_Event(TASK_TEXT_CANARY))
    (turn,) = coordinator.state.list_turns()

    control.bind_delegate_control_session_store(runner.host.session_store)
    other = runner.host.session_store.get_or_create_session(
        _Event("", chat_id="chat-2").source
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
    await _await_composed(
        runner.host._handle_delegate_command(_Event(TASK_TEXT_CANARY))
    )
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
    original_restore = coordinator.restore

    async def _gated_restore():
        entered.set()
        await release.wait()
        return await original_restore()

    coordinator.restore = _gated_restore  # type: ignore[method-assign]
    starting = asyncio.create_task(runner.start())
    await asyncio.wait_for(entered.wait(), timeout=5)
    admission_host = _Host(tmp_path / "admission")
    admission = asyncio.create_task(
        admission_host.host._handle_delegate_command(_Event(TASK_TEXT_CANARY))
    )
    await asyncio.sleep(0.05)

    assert starting.done() is False
    assert admission.done() is False
    assert runner._running is False
    assert facade.calls == ["server_info"]
    assert admission_host.host.session_store.list_sessions() == []

    release.set()
    assert await asyncio.wait_for(starting, timeout=10) is True
    assert await _await_composed(admission) == ""
    assert coordinator.lifecycle_loop is asyncio.get_running_loop()
    assert coordinator._restored is True
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
    await _await_composed(
        runner.host._handle_delegate_command(_Event(TASK_TEXT_CANARY))
    )
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
async def test_natural_language_create_uses_the_slash_routes_trusted_origin(
    tmp_path, monkeypatch
):
    import tools.sachima_delegate_control_tool as control
    from gateway.session_context import clear_session_vars, set_session_vars

    monkeypatch.setenv(control.SACHIMA_LIVE_PROGRESS_SURFACE_ENV, "hermes_internal")
    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    coordinator.bind_lifecycle_loop(asyncio.get_running_loop())
    await coordinator.restore()
    control.bind_delegate_control_session_store(runner.host.session_store)
    source = _Event(TASK_TEXT_CANARY).source
    session = runner.host.session_store.get_or_create_session(source)
    coordinator._delivery_factory = lambda _origin: runner.host._delegate_delivery_for(
        source, "m-natural"
    )
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
                {"action": "create", "task": TASK_TEXT_CANARY},
            )
        )
    finally:
        clear_session_vars(tokens)

    payload = json.loads(raw)
    (turn,) = coordinator.state.list_turns()
    assert payload["action"] == "create"
    assert payload["result"]["task_ref"] == turn.task_ref
    assert turn.profile_id == coordinator.policy.profiles[0].profile_id
    assert turn.origin.session_id == session.session_id
    assert turn.origin.reply_anchor == "m-natural"
    assert facade.submit_count() == 1
    facade.terminalize(0)


@pytest.mark.asyncio
async def test_requested_agent_switch_creates_a_linked_new_task(tmp_path, monkeypatch):
    import tools.sachima_delegate_control_tool as control
    from gateway.session_context import clear_session_vars, set_session_vars

    monkeypatch.setenv(control.SACHIMA_LIVE_PROGRESS_SURFACE_ENV, "hermes_internal")
    config = _config(
        tmp_path,
        agent_by_policy_ref={
            "policy_author": "author-agent",
            "policy_reviewer": "review-agent",
        },
        model_by_policy_ref={
            "policy_model": "claude-opus-5",
            "policy_review_model": "claude-sonnet-5",
        },
        effort_by_policy_ref={
            "policy_effort": "xhigh",
            "policy_review_effort": "high",
        },
    )
    policy = build_delegate_policy(
        {
            "type": DELEGATE_POLICY_TYPE,
            "profiles": [
                {
                    "profile_id": "author",
                    "workspace_ref": "ws_delegate",
                    "agent_policy_ref": "policy_author",
                    "model_policy_ref": "policy_model",
                    "effort_policy_ref": "policy_effort",
                    "run_limits_policy_ref": "policy_limits",
                    "priority": 10,
                },
                {
                    "profile_id": "reviewer",
                    "workspace_ref": "ws_delegate",
                    "agent_policy_ref": "policy_reviewer",
                    "model_policy_ref": "policy_review_model",
                    "effort_policy_ref": "policy_review_effort",
                    "run_limits_policy_ref": "policy_limits",
                    "auto_selectable": False,
                },
            ],
        },
        config,
    )
    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path, config=config, policy=policy)
    coordinator.bind_lifecycle_loop(asyncio.get_running_loop())
    await coordinator.restore()
    control.bind_delegate_control_session_store(runner.host.session_store)
    source = _Event(TASK_TEXT_CANARY).source
    session = runner.host.session_store.get_or_create_session(source)
    coordinator._delivery_factory = lambda _origin: runner.host._delegate_delivery_for(
        source, "m-switch"
    )
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
                    "task": TASK_TEXT_CANARY,
                    "requested_profile_id": "author",
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
                    "requested_profile_id": "reviewer",
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
    assert original.profile_id == "author"
    assert switched.profile_id == "reviewer"
    assert switched.task_id != original.task_id
    assert switched.spine_session_id != original.spine_session_id
    assert switched.linked_from == first_event.event_id
    assert switched.origin.session_id == original.origin.session_id
    assert facade.submit_count() == 2
    facade.terminalize(1)


# --------------------------------------------------------------------------- #
# J. Next-turn-only result context (§2.3)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_the_result_context_is_owed_to_the_next_turn_and_confirmed_after(
    tmp_path,
):
    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    await runner.host._handle_delegate_command(_Event(TASK_TEXT_CANARY))
    facade.terminalize(0)
    (turn,) = coordinator.state.list_turns()
    assert await _until(
        lambda: coordinator.state.result_for_turn(turn.turn_key) is not None
    )

    session_id = turn.origin.session_id
    lines = coordinator.pending_hermes_context(session_id)
    assert len(lines) == 1
    event = coordinator.state.result_for_turn(turn.turn_key)
    assert event.full_result_ref in lines[0]
    assert coordinator.state.read_result(event.event_id).hermes_sink == "in_flight"

    # Taking it twice does not duplicate it into a second turn.
    assert coordinator.pending_hermes_context(session_id) == ()
    assert coordinator.confirm_hermes_context(session_id) == 1
    assert coordinator.state.read_result(event.event_id).hermes_sink == "confirmed"


@pytest.mark.asyncio
async def test_an_interrupted_handoff_returns_to_pending(tmp_path):
    runner = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    await runner.host._handle_delegate_command(_Event(TASK_TEXT_CANARY))
    facade.terminalize(0)
    (turn,) = coordinator.state.list_turns()
    assert await _until(
        lambda: coordinator.state.result_for_turn(turn.turn_key) is not None
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
    await _await_composed(
        host.host._handle_delegate_command(_Event(TASK_TEXT_CANARY))
    )
    facade.terminalize(0)
    (turn,) = coordinator.state.list_turns()
    assert await _until(
        lambda: coordinator.state.result_for_turn(turn.turn_key) is not None
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
    await _await_composed(
        host.host._handle_delegate_command(_Event(TASK_TEXT_CANARY))
    )
    facade.terminalize(0)
    (turn,) = coordinator.state.list_turns()
    assert await _until(
        lambda: coordinator.state.result_for_turn(turn.turn_key) is not None
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

    settlements: list[tuple[str, bool]] = []
    _settle = runner._settle_delegate_result_context

    def _record(session_id, *, consumed):
        settlements.append((session_id, consumed))
        return _settle(session_id, consumed=consumed)

    runner._settle_delegate_result_context = _record

    async def _compresses_mid_turn(**kwargs):
        _mark_provider_attempt(kwargs)
        entry.session_id = "session-after-compression"
        return _model_turn_result(api_calls=1)

    runner._run_agent = AsyncMock(side_effect=_compresses_mid_turn)
    await runner._handle_message_with_agent(message, source, HANDOFF_SESSION_KEY, 1)

    assert settlements == [(claimed_session_id, True)]
    assert coordinator.state.read_result(event.event_id).hermes_sink == "confirmed"


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
    """It rides the next user message — never the system prompt, never a
    synthetic user turn, and never a mutation of a running one."""

    src = _run_source()
    # The call site, not the definition.
    index = src.rindex("self._consume_delegate_result_context(")
    block = src[index : index + 700]
    assert "[New message]" in block
    assert "message_text" in block
    assert "system_prompt" not in block
    assert "conversation_history" not in block
    assert "_settle_delegate_result_context" in src


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
    from gateway.platforms.telegram import TelegramAdapter
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
    """An origin can outlive its anchor; the topic id still routes the result."""

    runner, _adapter, calls = _telegram_origin_host()

    delivery = runner._delegate_delivery_from_origin(
        _delegate_origin(thread_id="42", anchor=None)
    )
    result = await delivery.send_plain_text_once(TERMINAL_BODY)

    assert result.success is True
    assert len(calls) == 1
    assert calls[0]["direct_messages_topic_id"] == 42
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
