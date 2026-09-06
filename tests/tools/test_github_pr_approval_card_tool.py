"""Tool contract for sending a PR approval card in the active Feishu session."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tools.github_pr_approval_card import github_pr_approval_card_tool


def test_uses_current_feishu_chat_and_preserves_bound_head():
    adapter = SimpleNamespace(
        send_github_pr_approval_card=AsyncMock(
            return_value=SimpleNamespace(success=True, message_id="msg-pr", error=None)
        )
    )
    session = {
        "HERMES_SESSION_PLATFORM": "feishu",
        "HERMES_SESSION_CHAT_ID": "oc-review",
        "HERMES_SESSION_THREAD_ID": "thread-1",
        "HERMES_SESSION_KEY": "feishu-session",
    }
    with (
        patch(
            "plugins.platforms.feishu.runtime.get_active_adapter",
            return_value=adapter,
        ),
        patch(
            "gateway.session_context.get_session_env",
            side_effect=lambda name, default="": session.get(name, default),
        ),
        patch("model_tools._run_async", side_effect=asyncio.run),
    ):
        result = json.loads(
            github_pr_approval_card_tool(
                {
                    "repo": "NousResearch/hermes-agent",
                    "pr_number": 123,
                    "head_sha": "abc123def456",
                    "locale": "en",
                }
            )
        )

    assert result == {
        "success": True,
        "platform": "feishu",
        "chat_id": "oc-review",
        "message_id": "msg-pr",
    }
    assert adapter.send_github_pr_approval_card.await_args.kwargs["head_sha"] == "abc123def456"


def test_requires_head_sha():
    result = json.loads(
        github_pr_approval_card_tool({"repo": "org/repo", "pr_number": 1})
    )

    assert "head_sha is required" in result["error"]
