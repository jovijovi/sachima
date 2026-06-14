"""Send Feishu GitHub PR approval cards.

The approve button deliberately routes back through Hermes as a synthetic user
merge approval request. It does not call GitHub or merge anything directly.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from gateway.platforms.feishu import get_active_adapter
from tools.registry import registry, tool_error


_LOCALE_ALIASES = {
    "": "zh-CN",
    "auto": "zh-CN",
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh_cn": "zh-CN",
    "cn": "zh-CN",
    "en": "en",
    "en-us": "en",
    "en_us": "en",
}


def _normalize_locale(locale: Any = "auto") -> str:
    return _LOCALE_ALIASES.get(str(locale or "auto").strip().lower(), "")


GITHUB_PR_APPROVAL_CARD_SCHEMA = {
    "name": "github_pr_approval_card",
    "description": (
        "Send a Feishu interactive card asking for GitHub PR merge approval. "
        "The Approve button routes back through Hermes' controlled pre-merge flow; "
        "it does not directly merge the PR. Works only inside a running Feishu gateway."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "Optional Feishu open_chat_id. Defaults to the current Feishu chat.",
            },
            "repo": {
                "type": "string",
                "description": "GitHub repository, e.g. NousResearch/hermes-agent.",
            },
            "pr_number": {
                "type": "integer",
                "description": "GitHub pull request number.",
            },
            "title": {"type": "string", "description": "PR title."},
            "pr_url": {"type": "string", "description": "PR URL."},
            "author": {"type": "string", "description": "PR author/login."},
            "head_sha": {"type": "string", "description": "Current PR head SHA to display and re-check."},
            "base_ref": {"type": "string", "description": "Target/base branch."},
            "head_ref": {"type": "string", "description": "Source/head branch."},
            "locale": {
                "type": "string",
                "enum": ["auto", "zh-CN", "en"],
                "description": "Card language. 'auto' defaults to Chinese in Feishu; use 'en' for English.",
            },
        },
        "required": ["repo", "pr_number", "head_sha"],
    },
}


def _session_metadata() -> Dict[str, str]:
    from gateway.session_context import get_session_env

    thread_id = get_session_env("HERMES_SESSION_THREAD_ID", "").strip()
    return {"thread_id": thread_id} if thread_id else {}


def _default_chat_id() -> str:
    from gateway.session_context import get_session_env

    platform = get_session_env("HERMES_SESSION_PLATFORM", "").strip().lower()
    if platform != "feishu":
        return ""
    return get_session_env("HERMES_SESSION_CHAT_ID", "").strip()


def _current_session_key() -> str:
    from gateway.session_context import get_session_env

    return get_session_env("HERMES_SESSION_KEY", "").strip()


def _validate_args(args: Dict[str, Any]) -> str:
    repo = str(args.get("repo") or "").strip()
    pr_number = args.get("pr_number")
    if not repo or pr_number in (None, ""):
        return "repo and pr_number are required"
    try:
        if int(pr_number) <= 0:
            return "pr_number must be a positive integer"
    except (TypeError, ValueError):
        return "pr_number must be a positive integer"
    if not str(args.get("head_sha") or "").strip():
        return "head_sha is required"
    if "locale" in args and not _normalize_locale(args.get("locale")):
        return "locale must be one of: auto, zh-CN, en"
    return ""


def github_pr_approval_card_tool(args, **_kwargs) -> str:
    """Tool handler for sending a Feishu GitHub PR approval card."""
    validation_error = _validate_args(args)
    if validation_error:
        return tool_error(validation_error)

    adapter = get_active_adapter()
    if adapter is None:
        return tool_error(
            "Feishu adapter is not running in this gateway process; cannot send an interactive PR approval card."
        )

    chat_id = str(args.get("chat_id") or "").strip() or _default_chat_id()
    if not chat_id:
        return tool_error("chat_id is required when not running from a Feishu chat session")

    from model_tools import _run_async

    try:
        result = _run_async(
            adapter.send_github_pr_approval_card(
                chat_id=chat_id,
                repo=str(args.get("repo") or "").strip(),
                pr_number=int(args.get("pr_number")),
                title=str(args.get("title") or ""),
                pr_url=str(args.get("pr_url") or ""),
                author=str(args.get("author") or ""),
                head_sha=str(args.get("head_sha") or ""),
                base_ref=str(args.get("base_ref") or ""),
                head_ref=str(args.get("head_ref") or ""),
                locale=_normalize_locale(args.get("locale", "auto")),
                session_key=_current_session_key(),
                metadata=_session_metadata(),
            )
        )
    except Exception as exc:
        return tool_error(f"Failed to send Feishu GitHub PR approval card: {exc}")

    if not getattr(result, "success", False):
        return tool_error(getattr(result, "error", None) or "send_github_pr_approval_card failed")

    return json.dumps(
        {
            "success": True,
            "platform": "feishu",
            "chat_id": chat_id,
            "message_id": getattr(result, "message_id", None),
        },
        ensure_ascii=False,
    )


def _check_github_pr_approval_card() -> bool:
    if get_active_adapter() is not None:
        return True
    try:
        from gateway.session_context import get_session_env

        return get_session_env("HERMES_SESSION_PLATFORM", "").strip().lower() == "feishu"
    except Exception:
        return False


registry.register(
    name="github_pr_approval_card",
    toolset="messaging",
    schema=GITHUB_PR_APPROVAL_CARD_SCHEMA,
    handler=github_pr_approval_card_tool,
    check_fn=_check_github_pr_approval_card,
    emoji="✅",
)
