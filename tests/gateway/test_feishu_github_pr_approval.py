"""Feishu GitHub PR approval cards stay bound to a reviewed head revision."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway.config import PlatformConfig
from gateway.platforms.base import MessageType
import plugins.platforms.feishu.adapter as feishu_module
from plugins.platforms.feishu.adapter import FeishuAdapter


def _adapter() -> FeishuAdapter:
    adapter = FeishuAdapter(PlatformConfig(enabled=True))
    adapter._client = MagicMock()
    return adapter


def _success(message_id: str = "msg-pr-1") -> SimpleNamespace:
    return SimpleNamespace(success=True, message_id=message_id, error=None)


@pytest.mark.asyncio
async def test_card_contains_bound_head_and_stores_only_successful_send():
    adapter = _adapter()
    with (
        patch.object(
            adapter,
            "send_interactive_card",
            new_callable=AsyncMock,
            return_value=_success(),
        ) as send,
        patch(
            "plugins.platforms.feishu.github_pr_approval.begin_control_transaction",
            return_value=True,
        ),
    ):
        result = await adapter.send_github_pr_approval_card(
            "oc-review",
            "NousResearch/hermes-agent",
            123,
            title="Approval card",
            head_sha="abc123def456",
            base_ref="release/sachima",
            head_ref="feature/card",
            locale="en",
            session_key="feishu-session",
        )

    assert result.success is True
    card = send.await_args.args[1]
    assert "abc123def456" in card["elements"][0]["content"]
    assert [
        button["value"]["hermes_github_pr_action"]
        for button in card["elements"][1]["actions"]
    ] == ["approve", "reject", "ignore"]
    approval_id = card["elements"][1]["actions"][0]["value"][
        "github_pr_approval_id"
    ]
    assert adapter._github_pr_approval_state[approval_id]["head_sha"] == "abc123def456"


@pytest.mark.asyncio
async def test_card_requires_head_revision():
    adapter = _adapter()
    with patch.object(
        adapter, "send_interactive_card", new_callable=AsyncMock
    ) as send:
        result = await adapter.send_github_pr_approval_card(
            "oc-review", "NousResearch/hermes-agent", 123, head_sha=""
        )

    assert result.success is False
    assert "head_sha" in (result.error or "")
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_card_for_same_pr_invalidates_old_head():
    adapter = _adapter()
    with (
        patch.object(
            adapter,
            "send_interactive_card",
            new_callable=AsyncMock,
            side_effect=[_success("old-card"), _success("new-card")],
        ),
        patch(
            "plugins.platforms.feishu.github_pr_approval.begin_control_transaction",
            return_value=True,
        ),
    ):
        await adapter.send_github_pr_approval_card(
            "oc-review", "org/repo", 7, head_sha="old111"
        )
        await adapter.send_github_pr_approval_card(
            "oc-review", "org/repo", 7, head_sha="new222"
        )

    assert len(adapter._github_pr_approval_state) == 1
    assert next(iter(adapter._github_pr_approval_state.values()))["head_sha"] == "new222"


@pytest.mark.asyncio
async def test_approve_routes_head_bound_request_through_gateway_guards():
    adapter = _adapter()
    adapter._github_pr_approval_state[1] = {
        "chat_id": "oc-review",
        "message_id": "msg-pr-1",
        "repo": "NousResearch/hermes-agent",
        "pr_number": "123",
        "head_sha": "abc123def456",
        "pr_url": "https://github.com/NousResearch/hermes-agent/pull/123",
        "session_key": "feishu-session",
        "control_transaction_id": "msg-pr-1",
    }
    adapter._github_pr_latest_approval_id_by_pr[("nousresearch/hermes-agent", "123")] = 1
    with (
        patch.object(
            adapter,
            "_resolve_sender_profile",
            new_callable=AsyncMock,
            return_value={"user_id": "ou-bob", "user_name": "Bob", "user_id_alt": None},
        ),
        patch.object(
            adapter,
            "get_chat_info",
            new_callable=AsyncMock,
            return_value={"name": "Review"},
        ),
        patch.object(
            adapter, "_handle_message_with_guards", new_callable=AsyncMock
        ) as handle,
        patch(
            "plugins.platforms.feishu.github_pr_approval.record_card_action",
            return_value=True,
        ) as record,
    ):
        await adapter._resolve_github_pr_approval(
            1,
            "approve",
            "Bob",
            open_id="ou-bob",
            chat_id="oc-review",
            token="callback-token",
        )

    handle.assert_awaited_once()
    event = handle.await_args.args[0]
    assert event.message_type is MessageType.TEXT
    assert event.message_id == "msg-pr-1"
    assert "abc123def456" in event.text
    assert "still equals the approved head SHA" in event.text
    assert "CI" in event.text and "mergeability" in event.text
    assert event.raw_message["github_pr_approval"]["head_sha"] == "abc123def456"
    record.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["reject", "ignore"])
async def test_nonapproval_choice_never_routes_merge_request(action):
    adapter = _adapter()
    adapter._github_pr_approval_state[2] = {
        "chat_id": "oc-review",
        "message_id": "msg-pr-2",
        "repo": "org/repo",
        "pr_number": "8",
        "head_sha": "abc123",
        "control_transaction_id": "msg-pr-2",
    }
    adapter._github_pr_latest_approval_id_by_pr[("org/repo", "8")] = 2
    with (
        patch.object(
            adapter, "_handle_message_with_guards", new_callable=AsyncMock
        ) as handle,
        patch(
            "plugins.platforms.feishu.github_pr_approval.record_card_action",
            return_value=True,
        ),
    ):
        await adapter._resolve_github_pr_approval(
            2, action, "Alice", open_id="ou-alice", chat_id="oc-review"
        )

    handle.assert_not_awaited()
    assert 2 not in adapter._github_pr_approval_state


class _CallbackCard:
    def __init__(self):
        self.type = None
        self.data = None


class _CallbackResponse:
    def __init__(self):
        self.card = None


def test_callback_rejects_wrong_chat_without_scheduling(monkeypatch):
    monkeypatch.setattr(feishu_module, "CallBackCard", _CallbackCard)
    monkeypatch.setattr(feishu_module, "P2CardActionTriggerResponse", _CallbackResponse)
    adapter = _adapter()
    adapter._loop = MagicMock(is_closed=MagicMock(return_value=False))
    adapter._allowed_group_users = {"ou-bob"}
    adapter._github_pr_approval_state[3] = {
        "chat_id": "oc-expected",
        "repo": "org/repo",
        "pr_number": "9",
        "head_sha": "abc123",
    }
    adapter._github_pr_latest_approval_id_by_pr[("org/repo", "9")] = 3
    data = SimpleNamespace(
        event=SimpleNamespace(
            token="tok",
            context=SimpleNamespace(open_chat_id="oc-other"),
            operator=SimpleNamespace(open_id="ou-bob", user_id=""),
            action=SimpleNamespace(
                value={
                    "hermes_github_pr_action": "approve",
                    "github_pr_approval_id": 3,
                }
            ),
        )
    )

    with patch("asyncio.run_coroutine_threadsafe") as submit:
        response = adapter._on_card_action_trigger(data)

    assert response.card is None
    submit.assert_not_called()


def test_card_payload_contains_no_direct_github_operation():
    card = FeishuAdapter._build_github_pr_approval_card(
        approval_id=1,
        repo="org/repo",
        pr_number="10",
        head_sha="abc123",
        locale="en",
    )

    serialized = json.dumps(card)
    assert "github.com/" not in serialized
    assert "merge" in serialized.lower()
    assert set(card["elements"][1]["actions"][0]["value"]) == {
        "hermes_github_pr_action",
        "github_pr_approval_id",
    }
