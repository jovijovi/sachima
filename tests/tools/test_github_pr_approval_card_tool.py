"""Tests for the GitHub PR approval-card tool."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


def _run_async_immediately(coro):
    return asyncio.run(coro)


def test_sends_pr_approval_card_to_current_feishu_chat():
    from tools.github_pr_approval_card import github_pr_approval_card_tool

    adapter = SimpleNamespace(
        send_github_pr_approval_card=AsyncMock(
            return_value=SimpleNamespace(success=True, message_id="msg_pr_001", error=None)
        )
    )

    def fake_session_env(name, default=""):
        return {
            "HERMES_SESSION_PLATFORM": "feishu",
            "HERMES_SESSION_CHAT_ID": "oc_12345",
            "HERMES_SESSION_THREAD_ID": "th_1",
            "HERMES_SESSION_KEY": "agent:main:feishu:group:oc_12345",
        }.get(name, default)

    with (
        patch("tools.github_pr_approval_card.get_active_adapter", return_value=adapter),
        patch("gateway.session_context.get_session_env", side_effect=fake_session_env),
        patch("model_tools._run_async", side_effect=_run_async_immediately),
    ):
        result = json.loads(
            github_pr_approval_card_tool(
                {
                    "repo": "NousResearch/hermes-agent",
                    "pr_number": 123,
                    "title": "Add Feishu PR approval card",
                    "pr_url": "https://github.com/NousResearch/hermes-agent/pull/123",
                    "head_sha": "abc123def456",
                    "base_ref": "release/sachima",
                    "head_ref": "feature/feishu-pr-approval-card",
                }
            )
        )

    assert result == {
        "success": True,
        "platform": "feishu",
        "chat_id": "oc_12345",
        "message_id": "msg_pr_001",
    }
    adapter.send_github_pr_approval_card.assert_awaited_once_with(
        chat_id="oc_12345",
        repo="NousResearch/hermes-agent",
        pr_number=123,
        title="Add Feishu PR approval card",
        pr_url="https://github.com/NousResearch/hermes-agent/pull/123",
        author="",
        head_sha="abc123def456",
        base_ref="release/sachima",
        head_ref="feature/feishu-pr-approval-card",
        session_key="agent:main:feishu:group:oc_12345",
        metadata={"thread_id": "th_1"},
    )


def test_fails_fast_without_active_feishu_adapter():
    from tools.github_pr_approval_card import github_pr_approval_card_tool

    with patch("tools.github_pr_approval_card.get_active_adapter", return_value=None):
        result = json.loads(
            github_pr_approval_card_tool(
                {
                    "repo": "NousResearch/hermes-agent",
                    "pr_number": 123,
                    "chat_id": "oc_12345",
                    "head_sha": "abc123def456",
                }
            )
        )

    assert "error" in result
    assert "Feishu adapter is not running" in result["error"]


def test_requires_repo_and_pr_number():
    from tools.github_pr_approval_card import github_pr_approval_card_tool

    result = json.loads(github_pr_approval_card_tool({"repo": "NousResearch/hermes-agent"}))

    assert "error" in result
    assert "repo and pr_number are required" in result["error"]


def test_requires_head_sha():
    from tools.github_pr_approval_card import github_pr_approval_card_tool

    result = json.loads(
        github_pr_approval_card_tool({"repo": "NousResearch/hermes-agent", "pr_number": 123})
    )

    assert "error" in result
    assert "head_sha is required" in result["error"]
