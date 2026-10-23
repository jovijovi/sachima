"""Bedrock's in-attempt recovery resend answers to the turn's provider dispatch lease (Sachima C06).

v0.22.4 widened ``_bedrock_converse_call``'s single resend from a cachePoint rejection to a
replayed sealed-reasoning rejection as well. That resend is a second real request, so a turn
the Gateway abandoned between the two (its lease revoked) must not put it on the wire, and a
resend that does go out confirms the turn's delegate claim exactly once.
"""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest

from tests.agent.test_bedrock_adapter import CROSS_REGION_REJECTION, _ok_converse_response

_KWARGS = {
    "__bedrock_region__": "us-east-1",
    "modelId": "moonshot.kimi-k2-thinking",
    "messages": [
        {"role": "user", "content": [{"text": "hi"}]},
        {"role": "assistant", "content": [
            {"reasoningContent": {"redactedContent": b"sealed"}},
            {"text": "answer"},
        ]},
        {"role": "user", "content": [{"text": "and then?"}]},
    ],
}


def _client(*responses):
    """``converse`` answers each call in turn: an exception is raised, a callable is called."""
    answers = iter(responses)

    def converse(**kwargs):
        answer = next(answers)
        if isinstance(answer, BaseException):
            raise answer
        return answer(**kwargs) if callable(answer) else answer

    client = MagicMock()
    client.converse.side_effect = converse
    return client


def test_a_lease_revoked_after_the_rejection_blocks_the_recovery_resend():
    from agent.chat_completion_helpers import ProviderDispatchLease, _bedrock_converse_call
    from gateway.run import _DelegateResultHandoff

    claim = _DelegateResultHandoff("session-1")
    lease = ProviderDispatchLease(claim.mark_provider_attempt)

    def rejected_while_the_turn_is_abandoned(**_kwargs):
        lease.revoke()  # the Gateway rebinds the cached agent to a newer turn meanwhile
        raise RuntimeError(CROSS_REGION_REJECTION)

    client = _client(rejected_while_the_turn_is_abandoned, _ok_converse_response())
    with patch("agent.bedrock_adapter._get_bedrock_runtime_client", return_value=client):
        with pytest.raises(InterruptedError):
            _bedrock_converse_call(deepcopy(_KWARGS), stream=False, agent=MagicMock(), lease=lease)

    assert client.converse.call_count == 1, "the recovery resend reached the provider"
    assert claim.consumed is False


def test_a_recovery_resend_under_a_live_lease_confirms_the_claim_once():
    from agent.chat_completion_helpers import ProviderDispatchLease, _bedrock_converse_call
    from gateway.run import _DelegateResultHandoff

    claim = _DelegateResultHandoff("session-1")
    marks: list[int] = []
    lease = ProviderDispatchLease(lambda: (marks.append(1), claim.mark_provider_attempt()))
    client = _client(RuntimeError(CROSS_REGION_REJECTION), _ok_converse_response())
    with patch("agent.bedrock_adapter._get_bedrock_runtime_client", return_value=client):
        result = _bedrock_converse_call(deepcopy(_KWARGS), stream=False, agent=MagicMock(), lease=lease)

    assert result.choices[0].message.content == "done"
    assert client.converse.call_count == 2
    resent = client.converse.call_args_list[1].kwargs["messages"][1]["content"]
    assert {"reasoningContent": {"redactedContent": b"sealed"}} not in resent
    assert claim.consumed is True
    assert marks == [1]
