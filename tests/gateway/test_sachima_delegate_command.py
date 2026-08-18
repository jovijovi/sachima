"""``/delegate <task>`` — the one new command, and the two routes to it.

Milestone A, tasks 1 and 9 (A3). What is proven here:

* **exactly one** delegate ``CommandDef`` exists, it is gateway-only, its
  argument hint is ``<task>``, the Gateway knows it — and no ``ars`` command,
  alias, or subcommand was minted beside it;
* empty text answers with the usage line **and creates nothing** — no task, no
  session, no payload, no background work;
* both Gateway paths — the cold slash path and the running-agent fast path —
  reach the *same* handler, so a delegated task behaves identically whether or
  not an agent happens to be busy;
* the running-agent path neither interrupts the active turn nor enters one:
  ``/delegate`` is parallel work, not a steer, a queue item, or a new prompt;
* the existing per-platform slash access policy still gates it on both paths.

Everything is pure local/offline: no Gateway process, adapter connection,
socket, daemon, or AGENT is started. Forbidden terms in this prose are no-leak
boundary canaries only, never behavior.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Any

import pytest

import gateway.sachima_delegate as delegate_mod
from hermes_cli.commands import (
    COMMAND_REGISTRY,
    GATEWAY_KNOWN_COMMANDS,
    gateway_help_lines,
    resolve_command,
    should_bypass_active_session,
    telegram_bot_commands,
)

DELEGATE = "delegate"


# --------------------------------------------------------------------------- #
# A. Registration (task 1)
# --------------------------------------------------------------------------- #
def test_exactly_one_delegate_command_is_registered():
    matches = [cmd for cmd in COMMAND_REGISTRY if cmd.name == DELEGATE]
    assert len(matches) == 1
    (delegate,) = matches
    assert delegate.args_hint == "<task>"
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
    """The plan admits one new command. ``/ars`` is not a second name for it."""

    assert resolve_command("ars") is None
    assert "ars" not in GATEWAY_KNOWN_COMMANDS
    assert [cmd for cmd in COMMAND_REGISTRY if cmd.name == "ars"] == []
    for cmd in COMMAND_REGISTRY:
        assert "ars" not in cmd.aliases


def test_delegate_appears_once_in_every_gateway_surface():
    help_lines = [line for line in gateway_help_lines() if "/delegate" in line]
    assert len(help_lines) == 1
    assert "`/delegate <task>`" in help_lines[0]

    menu = [name for name, _description in telegram_bot_commands() if name == DELEGATE]
    assert menu == [DELEGATE]


def test_delegate_stays_out_of_the_cli_surfaces():
    """Gateway-only means gateway-only: the CLI has no delegate seam."""

    from hermes_cli.commands import COMMANDS, COMMANDS_BY_CATEGORY

    assert "/delegate" not in COMMANDS
    for category in COMMANDS_BY_CATEGORY.values():
        assert "/delegate" not in category


# --------------------------------------------------------------------------- #
# B. The handler (task 9)
# --------------------------------------------------------------------------- #
class _Event:
    """The minimum of a ``MessageEvent`` the delegate handler reads."""

    def __init__(self, args: str, *, chat_id="chat-1", thread_id=None):
        from gateway.config import Platform
        from gateway.session import SessionSource

        self._args = args
        self.text = f"/delegate {args}".strip()
        self.source = SessionSource(
            platform=Platform.TELEGRAM,
            chat_id=chat_id,
            chat_type="dm",
            user_id="user-1",
            thread_id=thread_id,
        )
        self.message_id = "m-1"

    def get_command(self) -> str:
        return DELEGATE

    def get_command_args(self) -> str:
        return self._args


class _Runner:
    """A bare host carrying only the mixin the handler lives on."""

    def __init__(self):
        from gateway.slash_commands import GatewaySlashCommandsMixin

        class _Host(GatewaySlashCommandsMixin):
            """The mixin plus the two runner seams a delegate reply needs."""

            @staticmethod
            def _reply_anchor_for_event(event):
                return event.message_id

            @staticmethod
            def _thread_metadata_for_source(source, anchor=None):
                return {"thread_id": source.thread_id, "reply_to": anchor}

        self.host = _Host()
        self.sent: list[tuple[str, str, Any]] = []

        class _Adapter:
            async def send(_self, chat_id, text, **kwargs):
                self.sent.append((chat_id, text, kwargs))

        from gateway.config import Platform

        self.host.adapters = {Platform.TELEGRAM: _Adapter()}

    def __getattr__(self, name):
        return getattr(self.host, name)


@pytest.fixture(autouse=True)
def _no_bound_coordinator():
    delegate_mod.unbind_delegate_coordinator()
    yield
    delegate_mod.unbind_delegate_coordinator()


@pytest.mark.asyncio
async def test_empty_text_returns_the_usage_line_and_creates_nothing():
    runner = _Runner()
    reply = await runner.host._handle_delegate_command(_Event(""))
    assert reply == "用法：/delegate <任务>"
    assert reply == delegate_mod.DELEGATE_USAGE
    assert delegate_mod.delegate_payload_store().count() == 0
    assert delegate_mod.bound_delegate_coordinator() is None
    assert runner.sent == []


@pytest.mark.asyncio
@pytest.mark.parametrize("blank", ["   ", "\n", "\t "])
async def test_whitespace_only_text_is_also_empty(blank):
    runner = _Runner()
    reply = await runner.host._handle_delegate_command(_Event(blank))
    assert reply == delegate_mod.DELEGATE_USAGE
    assert delegate_mod.delegate_payload_store().count() == 0


@pytest.mark.asyncio
async def test_an_unbound_host_refuses_without_creating_anything():
    """No composed ``arsd`` bundle means no external AGENT path exists. The
    command says so; it never invents a local fallback."""

    runner = _Runner()
    reply = await runner.host._handle_delegate_command(_Event("do the thing"))
    assert reply == delegate_mod.DELEGATE_UNAVAILABLE
    assert reply != delegate_mod.DELEGATE_USAGE
    assert delegate_mod.delegate_payload_store().count() == 0
    assert runner.sent == []


class _StubCoordinator:
    """Records exactly what the handler asked for, and starts nothing."""

    def __init__(self):
        self.submissions: list[tuple[str, Any]] = []
        self.notifiers: list[Any] = []

    def submit_new(self, task_text, *, target, notifier):
        self.submissions.append((task_text, target))
        self.notifiers.append(notifier)
        return delegate_mod.DelegateSubmission(
            task_id="delegate_abc123abc123",
            session_id="sess_delegate_1",
            payload_ref="dlg_" + "a" * 32,
        )


@pytest.mark.asyncio
async def test_the_handler_returns_the_acceptance_and_submits_the_exact_text(
    monkeypatch,
):
    runner = _Runner()
    stub = _StubCoordinator()
    monkeypatch.setattr(delegate_mod, "_coordinator", stub)

    text = "read the changelog and 总结 the last three releases"
    reply = await runner.host._handle_delegate_command(_Event(text, thread_id="t-9"))

    assert stub.submissions == [(text, delegate_mod.DelegateTarget(
        platform="telegram", chat_id="chat-1", thread_id="t-9"
    ))]
    assert reply == delegate_mod.DELEGATE_ACCEPTED_TEMPLATE.format(
        task_ref="delegate_abc123abc123"
    )
    # Accepted comes back from the handler itself: nothing was pushed.
    assert runner.sent == []


@pytest.mark.asyncio
async def test_the_notifier_delivers_back_to_the_same_chat_and_thread(monkeypatch):
    runner = _Runner()
    stub = _StubCoordinator()
    monkeypatch.setattr(delegate_mod, "_coordinator", stub)

    await runner.host._handle_delegate_command(_Event("task", thread_id="t-9"))
    (notifier,) = stub.notifiers
    await notifier(stub.submissions[0][1], "任务 delegate_abc123abc123 已完成：\nok")

    assert len(runner.sent) == 1
    chat_id, text, _kwargs = runner.sent[0]
    assert chat_id == "chat-1"
    assert "已完成" in text


# --------------------------------------------------------------------------- #
# C. Both Gateway routes reach the same handler (task 9)
# --------------------------------------------------------------------------- #
def _run_source() -> str:
    import gateway.run

    return Path(gateway.run.__file__).read_text(encoding="utf-8")


def test_both_gateway_routes_call_the_one_handler():
    """The cold path and the running-agent fast path are two call sites of one
    handler, not two implementations that have to be kept in step."""

    src = _run_source()
    assert src.count("_handle_delegate_command(event)") == 2
    # The cold path dispatches on the canonical name; the fast path on the
    # resolved CommandDef, exactly as every other command on that path does.
    assert 'if canonical == "delegate"' in src
    assert '_cmd_def_inner.name == "delegate"' in src


def test_the_active_agent_route_neither_interrupts_nor_enters_the_turn():
    """A ``/delegate`` fired mid-run must return the acceptance directly.

    The two failure modes this guards are the ones the fast path exists for: an
    interrupt (which kills the conversation the user is having) and a fall
    through to the agent turn (which turns the delegation into a prompt the
    local agent answers itself).
    """

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
    """Same policy on both paths: an agent being busy is not an access grant."""

    from hermes_cli.commands import is_gateway_known_command
    from gateway.slash_access import SlashAccessPolicy

    # The cold-path gate only runs for a command the Gateway recognizes, so
    # being known is what puts /delegate under the existing policy at all.
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
