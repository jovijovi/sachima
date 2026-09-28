"""Composed regressions for delegate claims across an in-band queue drain.

The adapter processing task, Gateway message entry, recursive ``_run_agent``
call, coordinator claim/confirm/settle state, and delivery receipt callback are
production code.  Only the provider, transport, and supervisor are local test
doubles.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import types
from types import SimpleNamespace

import pytest

import gateway.sachima_delegate as delegate_mod
from gateway.platforms.base import MessageEvent, SendResult
from gateway.run import GatewayRunner
from gateway.sachima_delegate_wakeup import SachimaDelegateWakeupDispatcher

from tests.gateway.test_sachima_delegate_gateway import (
    _Host,
    _bind,
    _origin_for,
    _source,
    _until,
)
from tests.gateway.test_sachima_delegate_wakeup import _wire_gateway_turn


A_REPORT = "A finished and launched its authorized follow-up."
B_REPORT = "B was verified and reported from the queued follow-up."


class _QueuedDelegationAgent:
    """Block turn A while the test completes B, then observe the queue drain."""

    scenario: SimpleNamespace

    def __init__(self, **kwargs):
        self.session_id = kwargs["session_id"]
        self.model = kwargs["model"]
        self.provider = kwargs.get("provider", "openai")
        self.tools = []
        self.provider_attempt_callback = None
        self.context_compressor = SimpleNamespace(
            last_prompt_tokens=0,
            context_length=200_000,
        )
        self.session_prompt_tokens = 0
        self.session_completion_tokens = 0

    def run_conversation(
        self,
        user_message,
        conversation_history=None,
        task_id=None,
        **_kwargs,
    ):
        scenario = type(self).scenario
        call_index = len(scenario.messages)
        scenario.messages.append(user_message)

        if self.provider_attempt_callback is not None:
            self.provider_attempt_callback()

        if call_index == 0:
            scenario.first_provider_reached.set()
            if not scenario.release_first_turn.wait(timeout=10):
                raise AssertionError("timed out waiting to release turn A")
            final_response = A_REPORT
        else:
            for turn_key in scenario.result_turn_keys:
                event = scenario.coordinator.state.result_for_turn(turn_key)
                claimed = scenario.coordinator.state.read_result(event.event_id)
                scenario.second_claims.append(
                    (event.event_id, claimed.processing_id, claimed.hermes_sink)
                )
                if claimed.processing_id is not None:
                    scenario.staged.append(
                        scenario.coordinator.settle_result(
                            task_ref=event.task_ref,
                            turn_key=event.turn_key,
                            event_id=event.event_id,
                            processing_id=claimed.processing_id,
                            conclusion="reported",
                            evidence_ref=event.full_result_ref,
                        )
                    )
            final_response = B_REPORT

        history = list(conversation_history or [])
        messages = history + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": final_response},
        ]
        scenario.returned_messages.append(messages)
        return {
            "final_response": final_response,
            "messages": messages,
            "tools": [],
            "history_offset": len(history),
            "last_prompt_tokens": 0,
            "api_calls": 1,
            "failed": False,
        }

    def interrupt(self, *_args, **_kwargs):
        return None


def _install_real_run_agent(monkeypatch, tmp_path, runner, scenario) -> None:
    fake_run_agent = types.ModuleType("run_agent")
    _QueuedDelegationAgent.scenario = scenario
    fake_run_agent.AIAgent = _QueuedDelegationAgent
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)
    monkeypatch.setenv("HERMES_TOOL_PROGRESS_MODE", "off")
    monkeypatch.setenv("HERMES_AGENT_TIMEOUT", "0")
    monkeypatch.setattr("gateway.run._load_gateway_config", lambda: {})
    monkeypatch.setattr("gateway.run._hermes_home", tmp_path)

    import hermes_cli.tools_config as tools_config

    monkeypatch.setattr(
        tools_config,
        "_get_platform_tools",
        lambda *_args, **_kwargs: {"core"},
    )
    async def _emit(*_args, **_kwargs):
        return None

    runner.hooks = SimpleNamespace(loaded_hooks=False, emit=_emit)
    runner._get_proxy_url = lambda: None
    runner._resolve_session_agent_runtime = lambda **_kwargs: (
        "gpt-5.4",
        {
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "test-token",
        },
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
    runner._sync_telegram_topic_binding = lambda *_args, **_kwargs: None
    runner._release_running_agent_state = lambda *_args, **_kwargs: None
    runner._is_intentional_model_switch = lambda *_args, **_kwargs: True
    runner._run_agent = GatewayRunner._run_agent.__get__(runner, GatewayRunner)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "report_send_success",
        "expected_business_state",
        "ordinary_interleave",
        "merged_result_count",
    ),
    [
        pytest.param(True, "reported", False, 1, id="queued-success"),
        pytest.param(False, "blocked", False, 1, id="queued-send-failure"),
        pytest.param(
            True,
            "reported",
            True,
            2,
            id="user-ahead-of-merged-wakes",
        ),
    ],
)
async def test_queued_b_claims_and_settles_on_its_own_actual_send(
    tmp_path,
    monkeypatch,
    report_send_success,
    expected_business_state,
    ordinary_interleave,
    merged_result_count,
):
    """B finishes behind A and the recursive turn owns its exact claim."""

    host = _Host(tmp_path)
    coordinator, facade = _bind(tmp_path)
    coordinator._configure_completion_wakeup(True)
    origin = _origin_for(host)
    admission = coordinator.admit_agent("codex", task_text="delegated task A")
    assert admission.admitted
    created_a = await coordinator.create(
        task_text="delegated task A",
        preset=admission.preset,
        origin=origin,
        authorization_ref=origin.reply_anchor,
        continuation_task="delegated task B",
        continuation_summary="Verify and report B.",
        continuation_plan_ref="queued-b-plan",
        continuation_round_title="Run B",
        continuation_stop_condition="Stop after reporting B.",
    )

    runner, adapter, seen_events = _wire_gateway_turn(
        monkeypatch,
        tmp_path,
        origin=origin,
    )
    runner.session_store.get_or_create_session.return_value.session_key = (
        origin.session_key
    )
    scenario = SimpleNamespace(
        coordinator=coordinator,
        first_provider_reached=threading.Event(),
        release_first_turn=threading.Event(),
        messages=[],
        returned_messages=[],
        result_turn_keys=[],
        second_claims=[],
        staged=[],
    )
    _install_real_run_agent(monkeypatch, tmp_path, runner, scenario)

    original_send = adapter.send

    async def _send(chat_id, content, reply_to=None, metadata=None):
        if B_REPORT in content and not report_send_success:
            adapter.sent.append(content)
            return SendResult(
                success=False,
                error="controlled report transport failure",
                retryable=False,
            )
        return await original_send(
            chat_id,
            content,
            reply_to=reply_to,
            metadata=metadata,
        )

    adapter.send = _send
    dispatcher = SachimaDelegateWakeupDispatcher(
        coordinator,
        deliver=runner._deliver_sachima_delegate_wakeup,
        enabled=True,
    )
    runner._sachima_delegate_wakeup = dispatcher
    coordinator._set_completion_wakeup_notifier(dispatcher.notify)

    try:
        # A's native wake owns the Base processing task. The first two cases
        # add no user input; the third deliberately queues one user turn before
        # B and C terminate to exercise that reachable FIFO ordering.
        facade.terminalize(0, final_message="exact result A")
        assert await _until(scenario.first_provider_reached.is_set)

        event_a = coordinator.state.result_for_turn(created_a.turn_key)
        claimed_a = coordinator.state.read_result(event_a.event_id)
        assert claimed_a.hermes_sink == "confirmed"
        assert claimed_a.processing_id is not None

        continued = await coordinator.continue_authorized(
            task_ref=event_a.task_ref,
            turn_key=event_a.turn_key,
            event_id=event_a.event_id,
            processing_id=claimed_a.processing_id,
            origin=origin,
        )
        assert "refusal" not in continued, continued
        scenario.result_turn_keys.append(continued["turn_key"])

        if ordinary_interleave:
            natural = MessageEvent(
                text="What completed while you were working?",
                source=_source(chat_id=origin.chat_id, thread_id=origin.thread_id),
                message_id="natural-followup-1",
            )
            await adapter.handle_message(natural)
            assert adapter._pending_messages[origin.session_key] is natural

        if merged_result_count == 2:
            admission_c = coordinator.admit_agent(
                "codex",
                task_text="independent delegated result C",
            )
            assert admission_c.admitted
            created_c = await coordinator.create(
                task_text="independent delegated result C",
                preset=admission_c.preset,
                origin=origin,
            )
            scenario.result_turn_keys.append(created_c.turn_key)

        for facade_index in range(1, merged_result_count + 1):
            facade.terminalize(
                facade_index,
                final_message=f"exact queued result {facade_index}",
            )

        assert await _until(
            lambda: all(
                coordinator.state.result_for_turn(turn_key) is not None
                for turn_key in scenario.result_turn_keys
            )
        )
        result_events = [
            coordinator.state.result_for_turn(turn_key)
            for turn_key in scenario.result_turn_keys
        ]
        expected_event_ids = {event.event_id for event in result_events}

        def _queued_delegate_ids():
            queued = []
            head = adapter._pending_messages.get(origin.session_key)
            if head is not None:
                queued.append(head)
            state = runner._peek_session_state(origin.session_key)
            if state is not None:
                queued.extend(state.conversation.queued_events)
            ids = set()
            for queued_event in queued:
                ids.update(
                    (queued_event.metadata or {}).get(
                        "sachima_delegate_event_ids", []
                    )
                )
            return ids

        assert await _until(
            lambda: expected_event_ids.issubset(_queued_delegate_ids())
        )
        assert all(
            coordinator.state.read_result(event.event_id).hermes_sink == "pending"
            for event in result_events
        )

        scenario.release_first_turn.set()
        assert await _until(lambda: B_REPORT in adapter.sent)
        assert len(scenario.messages) == 2

        assert await _until(
            lambda: all(
                coordinator.state.read_result(event.event_id).business_state
                == expected_business_state
                for event in result_events
            )
        )
        assert {item[0] for item in scenario.second_claims} == expected_event_ids
        processing_ids = {item[1] for item in scenario.second_claims}
        assert None not in processing_ids
        assert len(processing_ids) == 1
        assert claimed_a.processing_id not in processing_ids
        assert all(item[2] == "confirmed" for item in scenario.second_claims)
        assert all(
            event.task_ref in scenario.messages[1]
            and event.full_result_ref in scenario.messages[1]
            for event in result_events
        )
        assert len(scenario.staged) == merged_result_count
        assert all(
            staged["business_state"] == "report_pending"
            for staged in scenario.staged
        )
        for event in result_events:
            settled = coordinator.state.read_result(event.event_id)
            assert settled.business_state == expected_business_state
            assert settled.wakeup_state == (
                "settled" if report_send_success else "blocked"
            )

        assert len(seen_events) == 1
        root_event: MessageEvent = seen_events[0]
        assert set(root_event.metadata["sachima_delegate_event_ids"]) == (
            expected_event_ids
        )
        assert "_gateway_processing_outcome_callback" not in root_event.metadata
        assert [message["role"] for message in scenario.returned_messages[-1]] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]
        if ordinary_interleave:
            assert "What completed while you were working?" in scenario.messages[1]
        assert origin.session_key not in adapter._pending_messages
        queue_state = runner._peek_session_state(origin.session_key)
        assert queue_state is None or queue_state.conversation.queued_events == []
    finally:
        scenario.release_first_turn.set()
        await dispatcher.close()
        await coordinator.close()
        await asyncio.gather(
            *tuple(adapter._background_tasks),
            return_exceptions=True,
        )
        delegate_mod.unbind_delegate_coordinator()
