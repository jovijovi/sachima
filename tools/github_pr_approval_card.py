"""Send a head-bound GitHub PR approval card through an active Feishu adapter."""

from __future__ import annotations

import json
from typing import Any, Dict

from tools.registry import registry, tool_error


_LOCALES = {"auto", "zh-CN", "en"}

GITHUB_PR_APPROVAL_CARD_SCHEMA = {
    "name": "github_pr_approval_card",
    "description": (
        "Send a Feishu card requesting approval for an exact GitHub PR head. "
        "Approval enters Hermes's fresh pre-merge checks and never merges directly."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "Feishu open_chat_id; defaults to the current Feishu chat.",
            },
            "repo": {"type": "string", "description": "GitHub owner/repository."},
            "pr_number": {"type": "integer", "description": "Pull request number."},
            "title": {"type": "string", "description": "Pull request title."},
            "pr_url": {"type": "string", "description": "Pull request URL."},
            "author": {"type": "string", "description": "Pull request author."},
            "head_sha": {
                "type": "string",
                "description": "Exact reviewed head SHA to bind the approval to.",
            },
            "base_ref": {"type": "string", "description": "Target branch."},
            "head_ref": {"type": "string", "description": "Source branch."},
            "locale": {
                "type": "string",
                "enum": ["auto", "zh-CN", "en"],
                "description": "Card language; auto defaults to zh-CN.",
            },
        },
        "required": ["repo", "pr_number", "head_sha"],
    },
}


def _session_env(name: str) -> str:
    from gateway.session_context import get_session_env

    return get_session_env(name, "").strip()


def _validate(args: Dict[str, Any]) -> str:
    if not str(args.get("repo") or "").strip() or args.get("pr_number") in (None, ""):
        return "repo and pr_number are required"
    try:
        if int(args["pr_number"]) <= 0:
            return "pr_number must be a positive integer"
    except (TypeError, ValueError):
        return "pr_number must be a positive integer"
    if not str(args.get("head_sha") or "").strip():
        return "head_sha is required"
    if str(args.get("locale") or "auto") not in _LOCALES:
        return "locale must be one of: auto, zh-CN, en"
    return ""


def github_pr_approval_card_tool(args: Dict[str, Any], **_kwargs: Any) -> str:
    """Send a PR approval card using the adapter in the current profile."""
    error = _validate(args)
    if error:
        return tool_error(error)

    from plugins.platforms.feishu.runtime import get_active_adapter

    adapter = get_active_adapter()
    if adapter is None:
        return tool_error("Feishu adapter is not connected for the current profile")
    chat_id = str(args.get("chat_id") or "").strip()
    if not chat_id and _session_env("HERMES_SESSION_PLATFORM").lower() == "feishu":
        chat_id = _session_env("HERMES_SESSION_CHAT_ID")
    if not chat_id:
        return tool_error("chat_id is required outside a Feishu chat session")

    metadata = {}
    thread_id = _session_env("HERMES_SESSION_THREAD_ID")
    if thread_id:
        metadata["thread_id"] = thread_id
    from model_tools import _run_async

    try:
        result = _run_async(
            adapter.send_github_pr_approval_card(
                chat_id=chat_id,
                repo=str(args.get("repo") or "").strip(),
                pr_number=int(args["pr_number"]),
                title=str(args.get("title") or ""),
                pr_url=str(args.get("pr_url") or ""),
                author=str(args.get("author") or ""),
                head_sha=str(args.get("head_sha") or "").strip(),
                base_ref=str(args.get("base_ref") or ""),
                head_ref=str(args.get("head_ref") or ""),
                locale=str(args.get("locale") or "auto"),
                session_key=_session_env("HERMES_SESSION_KEY"),
                metadata=metadata,
            )
        )
    except Exception as exc:
        return tool_error(f"Failed to send Feishu PR approval card: {exc}")
    if not getattr(result, "success", False):
        return tool_error(getattr(result, "error", "") or "Feishu card send failed")
    return json.dumps(
        {
            "success": True,
            "platform": "feishu",
            "chat_id": chat_id,
            "message_id": getattr(result, "message_id", None),
        },
        ensure_ascii=False,
    )


registry.register(
    name="github_pr_approval_card",
    toolset="feishu_github_pr_approval",
    schema=GITHUB_PR_APPROVAL_CARD_SCHEMA,
    handler=github_pr_approval_card_tool,
    requires_env=[],
    is_async=False,
    description="Send a head-bound GitHub PR approval card in Feishu",
    emoji="✅",
)
