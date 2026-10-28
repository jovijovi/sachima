"""Sachima delegation Gateway seams with upstream usage-window plans (v0.22.5).

A Nous usage-window turn still dispatches through the turn's provider-dispatch
lease while upstream's non-streaming request captures the ``x-nous-credits-*``
headers, and the delivery that records the Sachima receipt marker still
schedules upstream's usage-limit offer. The harness helpers are the ones
``test_sachima_delegate_gateway`` builds, beside which these cases live.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import gateway.sachima_delegate as delegate_mod
from tests.gateway.test_sachima_delegate_gateway import (
    HANDOFF_SESSION_KEY,
    _chat_response,
    _handoff_runner,
    _model_turn_result,
    _provider_agent,
)


@pytest.fixture(autouse=True)
def _unbind_coordinator():
    delegate_mod.unbind_delegate_coordinator()
    yield
    delegate_mod.unbind_delegate_coordinator()


_USAGE_LIMIT = {"suggestions": [{"model": "model-b", "label": "Model B"}]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "completed", "offers"),
    [
        ({}, True, 0),
        (
            {
                "failed": True,
                "completed": False,
                "final_response": "You've hit your daily limit.",
                "usage_window_message": "You've hit your daily limit.",
                "usage_limit": _USAGE_LIMIT,
            },
            False,
            1,
        ),
    ],
    ids=["completed-turn", "usage-window-refusal"],
)
async def test_the_delivery_seam_records_the_receipt_marker_and_the_limit_offer(
    tmp_path, monkeypatch, overrides, completed, offers
):
    """The turn's business marker and upstream's limit offer share one delivery (v0.22.5 seam).

    Delivery now goes through ``_deliver_turn_response_then_limit_offer``; the
    Sachima receipt marker ``_gateway_model_turn_completed`` is written just
    before it. ``usage_limit`` only rides a failed usage-window refusal
    (``agent/conversation_loop.py::_billing_failure_result``), so both real turn
    shapes go through the one path: a completed turn is marked complete and
    offers nothing; a refusal is marked not complete and schedules one offer.
    """

    from gateway.config import Platform
    from gateway.platforms.base import MessageEvent
    from gateway.session import SessionSource

    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="chat-1",
        chat_type="dm",
        user_id="user-1",
    )
    message = MessageEvent(text="what happened?", source=source, message_id="m-2")
    runner = _handoff_runner(monkeypatch, tmp_path, session_id="session-1")
    runner._run_agent = AsyncMock(return_value=_model_turn_result(api_calls=1, **overrides))
    runner._schedule_usage_limit_offer = MagicMock()

    await runner._handle_message_with_agent(message, source, HANDOFF_SESSION_KEY, 1)

    assert message.metadata.get("_gateway_model_turn_completed") is completed
    assert runner._schedule_usage_limit_offer.call_count == offers
    if offers:
        runner._schedule_usage_limit_offer.assert_called_once_with(
            message, _USAGE_LIMIT, session_key=HANDOFF_SESSION_KEY, generation=1,
        )


def test_a_usage_window_dispatch_is_admitted_and_still_captures_headers():
    """The generic chat branch's header capture is the gated dispatch (v0.22.5 seam).

    Upstream hands the non-streaming request to ``_chat_completion_capturing_headers``
    so a Nous usage-window session observes its ``x-nous-credits-*`` headers. That
    call is still the one the turn's lease admits: on a single request the raw
    response's headers reach every capture AND the attempt is booked once.
    """

    from agent.chat_completion_helpers import (
        ProviderDispatchLease,
        _dispatch_nonstreaming_api_request,
    )
    from agent.credits_tracker import parse_credits_headers
    from gateway.run import _DelegateResultHandoff
    from tests.usage_window_fixtures import gauges

    headers = {
        "x-nous-credits-version": "1",
        "x-nous-credits-denominator-kind": "usage_window",
        "x-nous-credits-window-gauges": json.dumps(gauges(day_used_bp=1_200, week_used_bp=900)),
    }
    agent = _provider_agent()
    agent.api_mode = "chat_completions"
    agent.provider = "nous"
    agent._credits_state = parse_credits_headers(headers)
    assert agent._credits_state.is_usage_window is True
    captured = []
    agent._capture_rate_limits = lambda raw: captured.append(("rate_limits", raw))
    agent._capture_credits = lambda raw: captured.append(("credits", raw))
    agent._capture_nous_model_switch = lambda raw: captured.append(("model_switch", raw))
    agent._check_openrouter_cache_status = lambda raw: captured.append(("cache_status", raw))
    claim = _DelegateResultHandoff("session-1")
    lease = ProviderDispatchLease(claim.mark_provider_attempt)

    parsed = _chat_response()
    raw = SimpleNamespace(headers=headers, parse=lambda: parsed)
    client = MagicMock()
    client.chat.completions.with_raw_response.create.return_value = raw

    result = _dispatch_nonstreaming_api_request(
        agent,
        {"model": "test/model"},
        make_client=lambda reason, kind="openai": client,
        lease=lease,
    )

    assert client.chat.completions.with_raw_response.create.call_count == 1
    assert client.chat.completions.create.called is False
    assert [name for name, _ in captured] == [
        "rate_limits", "credits", "model_switch", "cache_status",
    ]
    assert all(seen is raw for _, seen in captured)
    assert result is parsed
    assert claim.consumed is True
    assert agent._provider_attempts == 1
