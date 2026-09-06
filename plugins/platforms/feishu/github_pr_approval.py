"""Head-bound GitHub PR approval cards for the Feishu adapter.

The card is an authorization surface only. An approval creates an ordinary
inbound Hermes event that must run fresh provider/head/check/mergeability
checks; this module never invokes GitHub or performs a merge.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, Optional

from gateway.control_transaction import (
    begin_control_transaction,
    record_card_action,
)
from gateway.platforms.base import MessageEvent, MessageType, SendResult


logger = logging.getLogger(__name__)

_ACTIONS = frozenset({"approve", "reject", "ignore"})
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
_TEXT = {
    "zh-CN": {
        "title": "GitHub PR #{pr_number} 合并审批",
        "repo": "仓库",
        "pr_title": "标题",
        "author": "作者",
        "base": "目标分支",
        "head": "源分支",
        "head_sha": "Head SHA",
        "url": "URL",
        "notice": (
            "点击 **批准** 只会把审批送回 Hermes；Hermes 仍必须重新检查 "
            "PR 状态、head SHA、CI 和 mergeability 后才可合并。"
        ),
        "approve": "✅ 批准",
        "reject": "❌ 拒绝",
        "ignore": "忽略",
        "approved": "已批准",
        "rejected": "已拒绝",
        "ignored": "已忽略",
        "approved_detail": "已回传给 Hermes；Hermes 会先执行 fresh pre-merge checks。",
        "rejected_detail": "合并审批已拒绝。未触发合并请求。",
        "ignored_detail": "审批卡已忽略。未触发合并请求。",
        "operator": "操作人",
    },
    "en": {
        "title": "GitHub PR #{pr_number} merge approval",
        "repo": "Repo",
        "pr_title": "Title",
        "author": "Author",
        "base": "Base",
        "head": "Head",
        "head_sha": "Head SHA",
        "url": "URL",
        "notice": (
            "Clicking **Approve** only sends authorization back to Hermes. "
            "Hermes must still re-check PR state, the exact head SHA, CI, and "
            "mergeability before any merge."
        ),
        "approve": "✅ Approve",
        "reject": "❌ Reject",
        "ignore": "Ignore",
        "approved": "Approved for gated merge",
        "rejected": "Rejected",
        "ignored": "Ignored",
        "approved_detail": "Approval sent to Hermes for fresh pre-merge checks.",
        "rejected_detail": "Merge approval rejected. No merge request was routed.",
        "ignored_detail": "Approval card ignored. No merge request was routed.",
        "operator": "Operator",
    },
}


def normalize_locale(locale: Any = "auto") -> str:
    """Normalize a supported locale, defaulting auto/empty to Feishu Chinese."""
    return _LOCALE_ALIASES.get(str(locale or "auto").strip().lower(), "zh-CN")


class GitHubPrApprovalMixin:
    """Narrow Feishu mixin for GitHub PR approval presentation and routing."""

    def _init_github_pr_approval(self) -> None:
        self._github_pr_approval_state: Dict[int, Dict[str, str]] = {}
        self._github_pr_latest_approval_id_by_pr: Dict[tuple[str, str], int] = {}
        self._github_pr_approval_counter = itertools.count(1)

    @staticmethod
    def _github_pr_key(state: Dict[str, str]) -> tuple[str, str]:
        return (
            str(state.get("repo", "")).strip().lower(),
            str(state.get("pr_number", "")).strip(),
        )

    def _is_current_github_pr_approval(
        self, approval_id: Any, state: Dict[str, str]
    ) -> bool:
        try:
            normalized_id = int(approval_id)
        except (TypeError, ValueError):
            return False
        latest = self._github_pr_latest_approval_id_by_pr.get(
            self._github_pr_key(state)
        )
        return latest is None or latest == normalized_id

    @staticmethod
    def _build_github_pr_details(state: Dict[str, str], locale: str) -> str:
        text = _TEXT[normalize_locale(locale)]

        def line(label: str, value: str) -> str:
            return f"**{label}:** {value}" if value else ""

        values = (
            line(text["repo"], state.get("repo", "")),
            line(text["pr_title"], state.get("title", "")),
            line(text["author"], state.get("author", "")),
            line(text["base"], state.get("base_ref", "")),
            line(text["head"], state.get("head_ref", "")),
            line(text["head_sha"], state.get("head_sha", "")),
            line(text["url"], state.get("pr_url", "")),
        )
        return "\n".join(value for value in values if value)

    @classmethod
    def _build_github_pr_approval_card(
        cls,
        *,
        approval_id: int,
        repo: str,
        pr_number: str,
        title: str = "",
        pr_url: str = "",
        author: str = "",
        head_sha: str = "",
        base_ref: str = "",
        head_ref: str = "",
        locale: str = "auto",
    ) -> Dict[str, Any]:
        locale = normalize_locale(locale)
        text = _TEXT[locale]
        state = {
            "repo": repo,
            "title": title,
            "author": author,
            "base_ref": base_ref,
            "head_ref": head_ref,
            "head_sha": head_sha,
            "pr_url": pr_url,
        }
        details = cls._build_github_pr_details(state, locale)

        def button(label: str, action: str, style: str = "default") -> dict:
            return {
                "tag": "button",
                "text": {"tag": "plain_text", "content": label},
                "type": style,
                "value": {
                    "hermes_github_pr_action": action,
                    "github_pr_approval_id": approval_id,
                },
            }

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": text["title"].format(pr_number=pr_number),
                },
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": "\n\n".join(part for part in (details, text["notice"]) if part),
                },
                {
                    "tag": "action",
                    "actions": [
                        button(text["approve"], "approve", "primary"),
                        button(text["reject"], "reject", "danger"),
                        button(text["ignore"], "ignore"),
                    ],
                },
            ],
        }

    @classmethod
    def _build_resolved_github_pr_approval_card(
        cls, *, action: str, state: Dict[str, str], user_name: str
    ) -> Dict[str, Any]:
        locale = normalize_locale(state.get("locale", "auto"))
        text = _TEXT[locale]
        if action == "approve":
            icon, template, label, detail = (
                "✅", "green", text["approved"], text["approved_detail"]
            )
        elif action == "reject":
            icon, template, label, detail = (
                "❌", "red", text["rejected"], text["rejected_detail"]
            )
        else:
            icon, template, label, detail = (
                "⏭️", "grey", text["ignored"], text["ignored_detail"]
            )
        details = cls._build_github_pr_details(state, locale)
        content = [f"{icon} **{label}**\n\n{detail}"]
        if user_name:
            content.append(f"**{text['operator']}:** {user_name}")
        if details:
            content.append(details)
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"{icon} PR #{state.get('pr_number', '')} {label}",
                },
                "template": template,
            },
            "elements": [
                {"tag": "markdown", "content": "\n\n".join(content)}
            ],
        }

    async def send_github_pr_approval_card(
        self,
        chat_id: str,
        repo: str,
        pr_number: int | str,
        *,
        title: str = "",
        pr_url: str = "",
        author: str = "",
        head_sha: str = "",
        base_ref: str = "",
        head_ref: str = "",
        locale: str = "auto",
        session_key: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send one approval card and bind its callback to the supplied head."""
        if not getattr(self, "_client", None):
            return SendResult(success=False, error="Not connected")
        if not str(repo or "").strip() or not str(pr_number or "").strip():
            return SendResult(success=False, error="repo and pr_number are required")
        if not str(head_sha or "").strip():
            return SendResult(success=False, error="head_sha is required")

        approval_id = next(self._github_pr_approval_counter)
        state = {
            "chat_id": str(chat_id or "").strip(),
            "message_id": "",
            "repo": str(repo).strip(),
            "pr_number": str(pr_number).strip(),
            "title": str(title or ""),
            "pr_url": str(pr_url or ""),
            "author": str(author or ""),
            "head_sha": str(head_sha).strip(),
            "base_ref": str(base_ref or ""),
            "head_ref": str(head_ref or ""),
            "locale": normalize_locale(locale),
            "session_key": str(session_key or "").strip(),
        }
        approval_key = self._github_pr_key(state)
        self._github_pr_latest_approval_id_by_pr[approval_key] = approval_id
        card = self._build_github_pr_approval_card(
            approval_id=approval_id,
            repo=state["repo"],
            pr_number=state["pr_number"],
            title=state["title"],
            pr_url=state["pr_url"],
            author=state["author"],
            head_sha=state["head_sha"],
            base_ref=state["base_ref"],
            head_ref=state["head_ref"],
            locale=state["locale"],
        )
        result = await self.send_interactive_card(
            state["chat_id"], card, metadata=metadata
        )
        if not result.success:
            return result
        # An older in-flight send must never reactivate after a newer head was
        # issued for the same PR.
        if self._github_pr_latest_approval_id_by_pr.get(approval_key) != approval_id:
            return result

        state["message_id"] = str(result.message_id or "")
        for stored_id, stored in list(self._github_pr_approval_state.items()):
            if self._github_pr_key(stored) == approval_key:
                self._github_pr_approval_state.pop(stored_id, None)
        transaction_id = state["message_id"] or (
            f"github-pr-{approval_id}-{state['head_sha'][:12]}"
        )
        state["control_transaction_id"] = transaction_id
        self._github_pr_approval_state[approval_id] = state
        started = await asyncio.to_thread(
            begin_control_transaction,
            transaction_id=transaction_id,
            provider="github",
            resource_kind="pull_request",
            origin_session_key=state["session_key"],
            repo=state["repo"],
            change_id=state["pr_number"],
            bound_revision=state["head_sha"],
        )
        if not started:
            logger.warning(
                "[Feishu] Could not persist PR approval transaction %s",
                transaction_id,
            )
        return result

    def _empty_card_action_response(self) -> Any:
        from plugins.platforms.feishu import adapter as adapter_module

        response_type = adapter_module.P2CardActionTriggerResponse
        return response_type() if response_type is not None else None

    def _handle_github_pr_approval_card_action(
        self, *, event: Any, action_value: Dict[str, Any], loop: Any
    ) -> Any:
        """Validate a synchronous callback and schedule its guarded resolution."""
        response = self._empty_card_action_response()
        try:
            approval_id = int(action_value.get("github_pr_approval_id"))
        except (TypeError, ValueError):
            return response
        state = self._github_pr_approval_state.get(approval_id)
        if not state:
            return response
        action = str(action_value.get("hermes_github_pr_action") or "").lower()
        if action not in _ACTIONS:
            return response
        if not self._is_current_github_pr_approval(approval_id, state):
            self._github_pr_approval_state.pop(approval_id, None)
            return response

        operator = getattr(event, "operator", None)
        open_id = str(getattr(operator, "open_id", "") or "")
        if not self._is_interactive_operator_authorized(open_id):
            logger.warning("[Feishu] Unauthorized PR approval click by %s", open_id)
            return response
        callback_chat = str(
            getattr(getattr(event, "context", None), "open_chat_id", "") or ""
        )
        expected_chat = str(state.get("chat_id", "") or "")
        if expected_chat and (not callback_chat or callback_chat != expected_chat):
            logger.warning(
                "[Feishu] PR approval callback chat mismatch (expected=%s, got=%s)",
                expected_chat,
                callback_chat or "<missing>",
            )
            return response

        user_name = self._get_cached_sender_name(open_id) or open_id
        if not self._submit_on_loop(
            loop,
            self._resolve_github_pr_approval(
                approval_id,
                action,
                user_name,
                open_id=open_id,
                chat_id=callback_chat,
                token=str(getattr(event, "token", "") or ""),
            ),
        ):
            return response

        from plugins.platforms.feishu import adapter as adapter_module

        if response is not None and adapter_module.CallBackCard is not None:
            card = adapter_module.CallBackCard()
            card.type = "raw"
            card.data = self._build_resolved_github_pr_approval_card(
                action=action, state=state, user_name=user_name
            )
            response.card = card
        return response

    async def _resolve_github_pr_approval(
        self,
        approval_id: Any,
        action: str,
        user_name: str,
        *,
        open_id: str = "",
        chat_id: str = "",
        token: str = "",
    ) -> None:
        """Record the choice; only approval enters Hermes's guarded flow."""
        try:
            approval_id = int(approval_id)
        except (TypeError, ValueError):
            return
        state = self._github_pr_approval_state.get(approval_id)
        if not state or action not in _ACTIONS:
            return
        if not self._is_current_github_pr_approval(approval_id, state):
            self._github_pr_approval_state.pop(approval_id, None)
            return
        if not self._is_interactive_operator_authorized(open_id):
            return
        expected_chat = str(state.get("chat_id", "") or "")
        if expected_chat and (not chat_id or chat_id != expected_chat):
            return
        if action == "approve" and not str(state.get("head_sha", "")).strip():
            return

        state = self._github_pr_approval_state.pop(approval_id, None)
        if not state:
            return
        action_code = {
            "approve": "approved",
            "reject": "rejected",
            "ignore": "dismissed",
        }[action]
        await asyncio.to_thread(
            record_card_action,
            state.get("control_transaction_id", ""),
            action_code,
            actor=user_name,
            provider="github",
            resource_kind="pull_request",
            origin_session_key=state.get("session_key", ""),
            repo=state.get("repo", ""),
            change_id=state.get("pr_number", ""),
            bound_revision=state.get("head_sha", ""),
        )
        if action != "approve":
            return

        route_chat = expected_chat or chat_id
        sender = SimpleNamespace(open_id=open_id, user_id=None, union_id=None)
        profile = await self._resolve_sender_profile(sender)
        chat_info = await self.get_chat_info(route_chat)
        source = self.build_source(
            chat_id=route_chat,
            chat_name=chat_info.get("name") or route_chat or "Feishu Chat",
            chat_type=self._resolve_source_chat_type(
                chat_info=chat_info, event_chat_type="group"
            ),
            user_id=profile["user_id"],
            user_name=profile["user_name"],
            user_id_alt=profile["user_id_alt"],
        )
        repo = state.get("repo", "")
        number = state.get("pr_number", "")
        head_sha = state.get("head_sha", "")
        synthetic_text = (
            f"Approve GitHub PR {repo}#{number} from the Feishu approval card.\n"
            f"approved_head_sha: {head_sha}\n"
            "Before any merge, freshly read the PR and require that its current "
            "head still equals the approved head SHA above. Also require current "
            "CI/checks and mergeability to pass. If the head changed or any gate "
            "fails, do not merge; report the blocker and require a new approval card."
        )
        event = MessageEvent(
            text=synthetic_text,
            message_type=MessageType.TEXT,
            source=source,
            raw_message={
                "github_pr_approval": dict(state),
                "action": action,
                "token": token,
            },
            message_id=str(state.get("message_id") or "") or None,
            channel_prompt=self._resolve_channel_prompt(route_chat),
            timestamp=datetime.now(),
        )
        logger.info(
            "[Feishu] Routing head-bound PR approval for %s#%s through Hermes",
            repo,
            number,
        )
        await self._handle_message_with_guards(event)
