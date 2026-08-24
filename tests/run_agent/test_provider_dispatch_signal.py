"""The provider-dispatch signal — the last reliable local boundary.

A claimed delegated-result handoff is consumed **iff** the turn carrying it
commits at least one concrete local provider SDK invocation.  The conversation
loop cannot answer that from where it hands the request to an interruptible
helper: below that point the request can still stop at a pre-dispatch
interrupt, at client construction / credential refresh, or at a worker the main
thread already abandoned — and every provider family retries or falls back
*inside* the helper, so one outer mark can neither prove nor count the real
attempts.

So the signal lives at the call expression itself.  What is proven here:

* nothing signals before the SDK method is actually entered — pre-dispatch
  interruption, client construction failure and cancellation all leave the
  handoff untouched;
* the captured callback is a snapshot: a worker that outlives its turn can
  never fire the callback a later turn rebound onto the cached agent;
* each real attempt is counted once, including Chat retries, the Anthropic
  stream-entry → ``create()`` fallback, Bedrock's IAM stream denial → converse
  fallback, Codex connect retries, and the iteration-limit summary;
* paths that never speak to a local provider (codex app-server) signal nothing.

Everything is offline: no provider, socket, or network call.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from run_agent import AIAgent


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #
def _tool_defs(*names: str) -> list:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": f"{name} tool",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for name in names
    ]


@pytest.fixture()
def agent():
    """A real ``AIAgent`` with a mocked OpenAI client — no network, no tools."""

    with (
        patch("run_agent.get_tool_definitions", return_value=_tool_defs("web_search")),
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


def _attempts(agent) -> list:
    """Bind a handoff-shaped callback and return what it recorded."""

    recorded: list = []
    agent.provider_attempt_callback = lambda: recorded.append(1)
    return recorded


def _gate(agent):
    from agent.chat_completion_helpers import ProviderDispatchGate

    return ProviderDispatchGate(agent)


def _run_turn(agent, message: str = "hello"):
    with (
        patch.object(agent, "_persist_session"),
        patch.object(agent, "_save_trajectory"),
        patch.object(agent, "_cleanup_task_resources"),
    ):
        return agent.run_conversation(message)


def _response(content: str = "Final answer", finish_reason: str = "stop"):
    message = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
        model="test/model",
        usage=None,
    )


def _chunk(text: str, finish_reason: str | None = "stop"):
    delta = SimpleNamespace(content=text, tool_calls=None)
    return SimpleNamespace(
        choices=[SimpleNamespace(index=0, delta=delta, finish_reason=finish_reason)],
        model="test/model",
        usage=None,
    )


def _stub_middleware(monkeypatch, before_next_call):
    """Run the loop's execution middleware, doing something first."""

    import hermes_cli.middleware as middleware

    def _run(api_kwargs, next_call, **_kwargs):
        before_next_call()
        return next_call(api_kwargs)

    monkeypatch.setattr(middleware, "run_llm_execution_middleware", _run)


# --------------------------------------------------------------------------- #
# A. Nothing before the SDK call may signal
# --------------------------------------------------------------------------- #
def test_streaming_middleware_interrupt_before_next_call_does_not_dispatch(
    agent, monkeypatch
):
    """Middleware can interrupt between request build and dispatch.

    The streaming helper refuses to start, so no request ever left — a mark
    here would consume a handoff the model never saw.
    """

    agent.stream_delta_callback = lambda _text: None  # take the streaming path
    attempts = _attempts(agent)
    _stub_middleware(
        monkeypatch, lambda: setattr(agent, "_interrupt_requested", True)
    )

    _run_turn(agent)

    assert agent.client.chat.completions.create.called is False
    assert attempts == []
    assert agent._provider_attempts == 0


def test_client_construction_failure_does_not_signal(agent):
    """Credential/client construction is still local. It reached no provider."""

    attempts = _attempts(agent)
    agent._create_request_openai_client = MagicMock(
        side_effect=RuntimeError("no usable credential")
    )

    _run_turn(agent)

    assert agent.client.chat.completions.create.called is False
    assert attempts == []
    assert agent._provider_attempts == 0


def test_cancelled_old_worker_cannot_use_rebound_callback(agent):
    """A daemon worker can outlive its turn; the gateway caches the agent.

    Once the main thread abandoned the request, the stale worker may neither
    dispatch nor signal — and it must not see the callback the *next* turn
    rebound onto the same agent.
    """

    old = _attempts(agent)
    gate = _gate(agent)
    gate.cancel()

    new: list = []
    agent.provider_attempt_callback = lambda: new.append(1)
    sdk = MagicMock()

    with pytest.raises(InterruptedError):
        gate.invoke(sdk, model="test/model")

    assert sdk.call_count == 0
    assert old == [] and new == []
    assert agent._provider_attempts == 0


def test_the_gate_signals_the_callback_it_captured_not_the_rebound_one(agent):
    """The snapshot is taken when the request is prepared, by value."""

    old = _attempts(agent)
    gate = _gate(agent)

    new: list = []
    agent.provider_attempt_callback = lambda: new.append(1)
    sdk = MagicMock(return_value="ok")

    assert gate.invoke(sdk, model="test/model") == "ok"
    assert sdk.call_args.kwargs == {"model": "test/model"}
    assert old == [1] and new == []


# --------------------------------------------------------------------------- #
# B. Order: client ready → signal → SDK call
# --------------------------------------------------------------------------- #
def test_chat_dispatch_order_non_streaming(agent):
    order: list[str] = []
    build_client = agent._create_request_openai_client

    def _client(**kwargs):
        order.append("client")
        return build_client(**kwargs)

    agent._create_request_openai_client = _client
    agent.provider_attempt_callback = lambda: order.append("signal")
    agent.client.chat.completions.create.side_effect = lambda **_kw: (
        order.append("create") or _response()
    )

    _run_turn(agent)

    assert order == ["client", "signal", "create"]


def test_chat_dispatch_order_streaming(agent):
    order: list[str] = []
    build_client = agent._create_request_openai_client

    def _client(**kwargs):
        order.append("client")
        return build_client(**kwargs)

    agent._create_request_openai_client = _client
    agent.stream_delta_callback = lambda _text: None
    agent.provider_attempt_callback = lambda: order.append("signal")
    agent.client.chat.completions.create.side_effect = lambda **_kw: (
        order.append("create") or [_chunk("Final answer")]
    )

    _run_turn(agent)

    assert order == ["client", "signal", "create"]


# --------------------------------------------------------------------------- #
# C. Every real attempt is counted once
# --------------------------------------------------------------------------- #
def test_chat_stream_retry_marks_each_create(agent):
    """The streaming helper retries a dropped connection itself."""

    import httpx

    from agent.chat_completion_helpers import interruptible_streaming_api_call

    creates: list[dict] = []

    def _create(**kwargs):
        creates.append(kwargs)
        if len(creates) == 1:
            raise httpx.ReadTimeout("stream died before first byte")
        return [_chunk("Final answer")]

    agent.client.chat.completions.create.side_effect = _create
    agent.stream_delta_callback = lambda _text: None
    # The retry rebuilds the primary client pool; leave the mock in place so
    # the second attempt cannot reach a real endpoint.
    agent._replace_primary_openai_client = lambda *_args, **_kwargs: None
    attempts = _attempts(agent)

    response = interruptible_streaming_api_call(
        agent,
        {"model": "test/model", "messages": [{"role": "user", "content": "hi"}]},
        provider_dispatch=_gate(agent),
    )

    assert response.choices[0].message.content == "Final answer"
    assert len(creates) == 2
    assert len(attempts) == 2


def test_anthropic_manager_construction_is_pre_dispatch(agent):
    """``messages.stream(...)`` only builds a manager — no request yet."""

    from agent.anthropic_adapter import create_anthropic_message

    attempts = _attempts(agent)

    class _Messages:
        def stream(self, **_kwargs):
            raise RuntimeError("could not build the stream manager")

        def create(self, **_kwargs):
            raise AssertionError("the fallback must not run for this error")

    with pytest.raises(RuntimeError):
        create_anthropic_message(
            SimpleNamespace(messages=_Messages()),
            {"model": "claude-test", "messages": []},
            provider_dispatch=_gate(agent),
        )

    assert attempts == []
    assert agent._provider_attempts == 0


def test_anthropic_entry_and_create_fallback_are_real_attempts(agent):
    """Two requests really went out: the stream entry, then ``create()``."""

    from agent.anthropic_adapter import create_anthropic_message

    order: list[str] = []
    agent.provider_attempt_callback = lambda: order.append("signal")

    class _Manager:
        def __enter__(self):
            order.append("enter")
            raise RuntimeError("streaming is not supported for this model")

        def __exit__(self, *_exc):
            return False

    final = object()

    class _Messages:
        def stream(self, **_kwargs):
            order.append("manager")
            return _Manager()

        def create(self, **_kwargs):
            order.append("create")
            return final

    result = create_anthropic_message(
        SimpleNamespace(messages=_Messages()),
        {"model": "claude-test", "messages": []},
        provider_dispatch=_gate(agent),
    )

    assert result is final
    assert order == ["manager", "signal", "enter", "signal", "create"]
    assert agent._provider_attempts == 2


def test_bedrock_stream_denial_then_converse_marks_each_attempt(agent, monkeypatch):
    """An IAM denial is a real rejected attempt; the fallback is a second one."""

    from agent import bedrock_adapter
    from agent.chat_completion_helpers import interruptible_streaming_api_call

    calls: list[str] = []

    class _Denied(Exception):
        pass

    class _Client:
        def converse_stream(self, **_kwargs):
            calls.append("converse_stream")
            raise _Denied("bedrock:InvokeModelWithResponseStream is not authorized")

        def converse(self, **_kwargs):
            calls.append("converse")
            return {"output": {}}

    monkeypatch.setattr(
        bedrock_adapter, "_get_bedrock_runtime_client", lambda _region: _Client()
    )
    monkeypatch.setattr(
        bedrock_adapter,
        "is_streaming_access_denied_error",
        lambda exc: isinstance(exc, _Denied),
    )
    monkeypatch.setattr(
        bedrock_adapter, "normalize_converse_response", lambda _raw: _response()
    )
    agent.api_mode = "bedrock_converse"
    attempts = _attempts(agent)

    response = interruptible_streaming_api_call(
        agent,
        {"modelId": "anthropic.test", "messages": [], "__bedrock_region__": "us-east-1"},
        provider_dispatch=_gate(agent),
    )

    assert response.choices[0].message.content == "Final answer"
    assert calls == ["converse_stream", "converse"]
    assert len(attempts) == 2


def test_codex_responses_connect_retry_marks_each_create(agent):
    """``responses.create`` is retried inside the Codex runtime."""

    import httpx

    from agent.codex_runtime import run_codex_stream

    creates: list[dict] = []
    final = SimpleNamespace(
        output=[], output_text="done", status="completed", id="resp-1"
    )

    class _Responses:
        def create(self, **kwargs):
            creates.append(kwargs)
            if len(creates) == 1:
                raise httpx.ConnectError("connection refused")
            return final

    attempts = _attempts(agent)

    result = run_codex_stream(
        agent,
        {"model": "test/model", "input": []},
        client=SimpleNamespace(responses=_Responses()),
        provider_dispatch=_gate(agent),
    )

    assert result is final
    assert len(creates) == 2
    assert len(attempts) == 2


def test_iteration_limit_summary_marks_each_direct_create(agent):
    """The summary path calls ``chat.completions.create`` itself, twice here."""

    from agent.chat_completion_helpers import handle_max_iterations

    creates: list[dict] = []

    def _create(**kwargs):
        creates.append(kwargs)
        return _response(content="" if len(creates) == 1 else "the summary")

    agent.client.chat.completions.create.side_effect = _create
    attempts = _attempts(agent)

    final = handle_max_iterations(
        agent, [{"role": "user", "content": "hi"}], api_call_count=3
    )

    assert final == "the summary"
    assert len(creates) == 2
    assert len(attempts) == 2


# --------------------------------------------------------------------------- #
# D. Controls — a turn that never speaks to a local provider
# --------------------------------------------------------------------------- #
def test_the_codex_app_server_turn_does_not_confirm_local_dispatch(agent):
    """The app-server runtime owns the turn; Hermes dispatches nothing."""

    agent.api_mode = "codex_app_server"
    attempts = _attempts(agent)

    with patch.object(
        agent,
        "_run_codex_app_server_turn",
        return_value={"final_response": "done", "messages": [], "api_calls": 1},
    ) as app_server_turn:
        _run_turn(agent)

    assert app_server_turn.called is True
    assert attempts == []
    assert agent._provider_attempts == 0


# --------------------------------------------------------------------------- #
# E. Turn ownership — one immutable lease, created before execution middleware
# --------------------------------------------------------------------------- #
# The gate proves *where* a request commits.  It cannot, on its own, prove
# *whose* request it is: the loop used to build it inside ``_perform_api_call``,
# below execution middleware, so a turn the main thread had already abandoned
# still snapshotted whatever callback the *next* turn had rebound onto the
# cached agent by the time middleware released it.  Ownership therefore has to
# be captured one level up and be cancellable as a whole — that is the lease.


def _lease(callback=None):
    from agent.chat_completion_helpers import ProviderDispatchLease

    return ProviderDispatchLease(callback)


def _paused_middleware(monkeypatch):
    """Hold the turn inside execution middleware, before ``next_call``."""

    import hermes_cli.middleware as middleware

    entered = threading.Event()
    release = threading.Event()

    def _run(api_kwargs, next_call, **_kwargs):
        entered.set()
        release.wait(10)
        return next_call(api_kwargs)

    monkeypatch.setattr(middleware, "run_llm_execution_middleware", _run)
    return entered, release


def test_a_paused_turn_signals_the_owner_it_started_with(agent, monkeypatch):
    """The exact reproduced race, without abandonment.

    Middleware is held before ``next_call``; the cached agent is rebound to the
    next turn's callback meanwhile.  The released request is still *this*
    turn's, so it must signal the callback this turn started with.
    """

    old = _attempts(agent)
    new: list = []
    agent.client.chat.completions.create.return_value = _response()
    entered, release = _paused_middleware(monkeypatch)

    worker = threading.Thread(target=lambda: _run_turn(agent), daemon=True)
    worker.start()
    assert entered.wait(10) is True

    agent.provider_attempt_callback = lambda: new.append(1)
    release.set()
    worker.join(30)

    assert worker.is_alive() is False
    assert agent.client.chat.completions.create.call_count == 1
    assert old == [1]
    assert new == []


def test_the_turn_uses_the_lease_it_was_handed_not_the_bound_callback(agent):
    """The gateway captures ownership before it schedules the executor."""

    old: list = []
    new = _attempts(agent)
    lease = _lease(lambda: old.append(1))
    agent.client.chat.completions.create.return_value = _response()

    with (
        patch.object(agent, "_persist_session"),
        patch.object(agent, "_save_trajectory"),
        patch.object(agent, "_cleanup_task_resources"),
    ):
        result = agent.run_conversation("hello", _provider_dispatch_lease=lease)

    assert result["final_response"] == "Final answer"
    assert agent.client.chat.completions.create.call_count == 1
    assert old == [1]
    assert new == []


def test_a_lease_cancelled_before_its_gate_exists_bars_the_request(agent):
    """Abandonment can win before the worker ever prepared a request."""

    signals: list = []
    lease = _lease(lambda: signals.append(1))
    lease.cancel()

    gate = lease.gate(agent)
    sdk = MagicMock()

    with pytest.raises(InterruptedError):
        gate.invoke(sdk, model="test/model")

    assert sdk.call_count == 0
    assert signals == []
    assert agent._provider_attempts == 0


def test_cancel_first_leaves_zero_signal_and_zero_dispatch(agent):
    """Cancellation wins: nothing was consumed and nothing left."""

    signals: list = []
    lease = _lease(lambda: signals.append(1))
    gate = lease.gate(agent)
    lease.cancel()
    sdk = MagicMock()

    with pytest.raises(InterruptedError):
        gate.invoke(sdk, model="test/model")

    assert sdk.call_count == 0
    assert signals == []
    assert agent._provider_attempts == 0
    assert gate.cancelled is True


def test_commit_first_signals_once_then_bars_every_later_request(agent):
    """Commit wins: the signal completes before cancellation can return.

    The callback runs under the ownership lock, so a settlement that races the
    dispatch cannot observe an un-consumed handoff while the request is already
    irrevocable.  Everything *after* that one call is refused.
    """

    order: list[str] = []
    signalling = threading.Event()
    finish_signal = threading.Event()

    def _callback():
        order.append("signal")
        signalling.set()
        finish_signal.wait(10)

    lease = _lease(_callback)
    gate = lease.gate(agent)
    sdk = MagicMock(side_effect=lambda **_kw: order.append("sdk"))

    committing = threading.Thread(
        target=lambda: gate.invoke(sdk, model="test/model"), daemon=True
    )
    committing.start()
    assert signalling.wait(10) is True

    cancelled = threading.Event()
    canceller = threading.Thread(
        target=lambda: (lease.cancel(), cancelled.set()), daemon=True
    )
    canceller.start()
    # Cancellation cannot land while the winning commit still owns the lock.
    assert cancelled.wait(0.3) is False

    finish_signal.set()
    committing.join(10)
    canceller.join(10)

    assert order == ["signal", "sdk"]
    assert sdk.call_count == 1
    assert agent._provider_attempts == 1

    # Retries and later requests under a cancelled lease are refused.
    with pytest.raises(InterruptedError):
        gate.invoke(sdk, model="test/model")
    with pytest.raises(InterruptedError):
        lease.gate(agent).invoke(sdk, model="test/model")
    assert sdk.call_count == 1
    assert agent._provider_attempts == 1


def test_a_revoked_lease_cannot_displace_the_owner_that_replaced_it(agent):
    """A stale worker activating late must not touch the newer owner."""

    old: list = []
    new: list = []
    lease_a = _lease(lambda: old.append(1))
    lease_b = _lease(lambda: new.append(1))

    assert agent._activate_provider_dispatch_lease(lease_a) is True
    agent._cancel_active_provider_dispatch_lease()
    assert agent._activate_provider_dispatch_lease(lease_b) is True

    # Only now does the abandoned worker reach its own activation.
    assert agent._activate_provider_dispatch_lease(lease_a) is False
    assert agent._active_provider_lease is lease_b
    assert lease_b.revoked is False

    sdk = MagicMock(return_value="ok")
    assert lease_b.gate(agent).invoke(sdk, model="test/model") == "ok"
    assert new == [1]
    assert old == []


def test_an_old_turns_finalizer_leaves_the_new_owner_installed(agent):
    """Cleanup is identity-guarded: A's exit may not clear B's slot."""

    lease_a = _lease(lambda: None)
    lease_b = _lease(lambda: None)

    agent._activate_provider_dispatch_lease(lease_a)
    agent._activate_provider_dispatch_lease(lease_b)
    assert lease_a.revoked is True

    agent._retire_provider_dispatch_lease(lease_a)

    assert agent._active_provider_lease is lease_b
    assert lease_b.revoked is False


def test_the_iteration_summary_keeps_the_turns_owner_across_a_rebind(agent):
    """Both summary attempts belong to the turn whose budget ran out."""

    from agent.chat_completion_helpers import handle_max_iterations

    creates: list[dict] = []

    def _create(**kwargs):
        creates.append(kwargs)
        return _response(content="" if len(creates) == 1 else "the summary")

    agent.client.chat.completions.create.side_effect = _create

    old: list = []
    lease = _lease(lambda: old.append(1))
    new = _attempts(agent)

    final = handle_max_iterations(
        agent,
        [{"role": "user", "content": "hi"}],
        api_call_count=3,
        provider_dispatch_lease=lease,
    )

    assert final == "the summary"
    assert len(creates) == 2
    assert old == [1, 1]
    assert new == []


def test_a_callback_that_raises_is_contained_and_the_request_still_leaves(agent):
    """A broken owner must never cost the turn its provider call."""

    def _boom():
        raise RuntimeError("handoff latch exploded")

    lease = _lease(_boom)
    sdk = MagicMock(return_value="ok")

    assert lease.gate(agent).invoke(sdk, model="test/model") == "ok"
    assert sdk.call_count == 1
    assert agent._provider_attempts == 1


def test_stream_retries_signal_the_leases_owner_not_a_rebound_callback(agent):
    """Inner retries stay inside the same request and the same ownership."""

    import httpx

    from agent.chat_completion_helpers import interruptible_streaming_api_call

    creates: list[dict] = []

    def _create(**kwargs):
        creates.append(kwargs)
        if len(creates) == 1:
            raise httpx.ReadTimeout("stream died before first byte")
        return [_chunk("Final answer")]

    agent.client.chat.completions.create.side_effect = _create
    agent.stream_delta_callback = lambda _text: None
    agent._replace_primary_openai_client = lambda *_args, **_kwargs: None

    old: list = []
    lease = _lease(lambda: old.append(1))
    new = _attempts(agent)

    response = interruptible_streaming_api_call(
        agent,
        {"model": "test/model", "messages": [{"role": "user", "content": "hi"}]},
        provider_dispatch=lease.gate(agent),
    )

    assert response.choices[0].message.content == "Final answer"
    assert len(creates) == 2
    assert old == [1, 1]
    assert new == []


def test_a_middleware_that_never_dispatches_closes_the_request_gate(
    agent, monkeypatch
):
    """The request gate exists before middleware, so it must die with it."""

    import agent.chat_completion_helpers as helpers
    import hermes_cli.middleware as middleware

    made: list = []
    real_gate = helpers.ProviderDispatchGate

    def _record(agent_arg, lease=None):
        gate = real_gate(agent_arg, lease)
        made.append(gate)
        return gate

    monkeypatch.setattr(helpers, "ProviderDispatchGate", _record)
    monkeypatch.setattr(
        middleware,
        "run_llm_execution_middleware",
        lambda api_kwargs, next_call, **_kwargs: _response(),
    )
    attempts = _attempts(agent)

    _run_turn(agent)

    assert agent.client.chat.completions.create.called is False
    assert attempts == []
    assert made != []
    assert all(gate.cancelled for gate in made)


# --------------------------------------------------------------------------- #
# F. Controls — ordinary, ownerless turns are unchanged
# --------------------------------------------------------------------------- #
def test_an_ordinary_non_streaming_turn_without_an_owner_is_unchanged(agent):
    agent.provider_attempt_callback = None
    agent.client.chat.completions.create.return_value = _response()

    result = _run_turn(agent)

    assert result["final_response"] == "Final answer"
    assert agent.client.chat.completions.create.call_count == 1
    assert agent._provider_attempts == 1


def test_an_ordinary_streaming_turn_without_an_owner_is_unchanged(agent):
    agent.provider_attempt_callback = None
    agent.stream_delta_callback = lambda _text: None
    agent.client.chat.completions.create.return_value = [_chunk("Final answer")]

    result = _run_turn(agent)

    assert result["final_response"] == "Final answer"
    assert agent.client.chat.completions.create.call_count == 1
    assert agent._provider_attempts == 1
