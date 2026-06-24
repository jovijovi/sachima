"""TODO lifecycle helpers for transaction-scoped progress workbench state."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import re
from typing import Any, Iterable

from gateway.progress.redaction import sanitize_for_progress, sanitize_value_for_progress

TODO_LIFECYCLE_STATES = {
    "created",
    "active",
    "completed",
    "suspended",
    "resumed",
    "cancelled",
    "archived",
}
TODO_SUSPENSION_REASONS = {
    "blocked",
    "waiting_user",
    "waiting_external",
    "failed_recoverable",
    "paused",
}

MAX_OWNER_LABEL_CHARS = 80
MAX_LIFECYCLE_TEXT_CHARS = 240
MAX_HINT_TITLE_CHARS = 240
MAX_HINT_NEXT_ACTION_CHARS = 240

_RESUME_COMMANDS = {
    "继续",
    "继续上一任务",
    "继续刚才那个",
    "接着处理上一任务",
    "继续上一个任务",
    "resume previous task",
    "continue previous task",
}


@dataclass(frozen=True)
class OwnerScopeRef:
    """Sanitized owner boundary for cross-turn suspended TODO eligibility."""

    profile: str
    platform: str
    conversation: str
    user: str


@dataclass(frozen=True)
class TodoLifecycleSnapshot:
    """Lifecycle metadata for one transaction's structured TODO snapshot."""

    state: str
    suspension_reason: str | None = None
    completed_count: int = 0
    remaining_count: int = 0
    next_action: str | None = None
    owner_scope_ref: OwnerScopeRef | None = None


@dataclass(frozen=True)
class SuspendedTodoHint:
    """Compact same-owner suspended-work hint for renderer surfaces."""

    transaction_id: str
    title: str
    reason: str
    remaining_count: int
    next_action: str | None = None
    overflow_count: int = 0
    owner_scope_ref: OwnerScopeRef | None = None


def make_owner_scope_ref(
    *,
    profile: Any,
    platform: Any,
    conversation_id: Any = None,
    user_id: Any = None,
    thread_id: Any = None,
    topic_id: Any = None,
) -> OwnerScopeRef:
    """Build a safe owner scope from raw runtime identifiers.

    Raw conversation/user/thread/topic ids are never retained. Labels are safe
    display labels; scope components are non-reversible digests.
    """

    profile_label = _safe_label(profile, default="default")
    platform_label = _safe_label(platform, default="unknown")
    conversation_digest = _digest_parts("conversation", conversation_id, thread_id, topic_id)
    user_digest = _digest_parts("user", user_id)
    return OwnerScopeRef(
        profile=profile_label,
        platform=platform_label,
        conversation=conversation_digest,
        user=user_digest,
    )


def normalize_owner_scope_ref(raw: Any) -> OwnerScopeRef | None:
    """Normalize a persisted owner scope; malformed or incomplete scopes drop."""

    if isinstance(raw, OwnerScopeRef):
        return raw
    data = _as_mapping(raw)
    if data is None:
        return None
    profile = _safe_label(data.get("profile") or data.get("profile_label"), default="")
    platform = _safe_label(data.get("platform") or data.get("platform_label"), default="")
    conversation = _safe_digest_ref(
        data.get("conversation")
        or data.get("conversation_scope")
        or data.get("conversation_scope_digest")
    )
    user = _safe_digest_ref(data.get("user") or data.get("user_scope") or data.get("user_scope_digest"))
    if not (profile and platform and conversation and user):
        return None
    return OwnerScopeRef(profile=profile, platform=platform, conversation=conversation, user=user)


def normalize_todo_lifecycle(raw: Any) -> TodoLifecycleSnapshot | None:
    """Normalize lifecycle metadata, failing closed on unknown states."""

    if isinstance(raw, TodoLifecycleSnapshot):
        return raw if raw.state in TODO_LIFECYCLE_STATES else None
    data = _as_mapping(raw)
    if data is None:
        return None
    state = str(data.get("state") or "").strip().lower()
    if state not in TODO_LIFECYCLE_STATES:
        return None
    reason = _normalize_reason(data.get("suspension_reason") or data.get("reason"))
    owner = normalize_owner_scope_ref(data.get("owner_scope_ref"))
    return TodoLifecycleSnapshot(
        state=state,
        suspension_reason=reason,
        completed_count=_safe_count(data.get("completed_count")),
        remaining_count=_safe_count(data.get("remaining_count")),
        next_action=_safe_optional_text(data.get("next_action"), max_len=MAX_LIFECYCLE_TEXT_CHARS),
        owner_scope_ref=owner,
    )


def normalize_suspended_todo_hint(raw: Any) -> SuspendedTodoHint | None:
    """Normalize a compact suspended hint; malformed records are ignored."""

    if isinstance(raw, SuspendedTodoHint):
        return raw if raw.transaction_id and raw.owner_scope_ref is not None else None
    data = _as_mapping(raw)
    if data is None:
        return None
    transaction_id = _safe_optional_text(data.get("transaction_id"), max_len=160)
    owner = normalize_owner_scope_ref(data.get("owner_scope_ref"))
    if not transaction_id or owner is None:
        return None
    reason = _normalize_reason(data.get("reason") or data.get("suspension_reason")) or "paused"
    return SuspendedTodoHint(
        transaction_id=transaction_id,
        title=_safe_optional_text(data.get("title"), max_len=MAX_HINT_TITLE_CHARS) or transaction_id,
        reason=reason,
        remaining_count=_safe_count(data.get("remaining_count")),
        next_action=_safe_optional_text(data.get("next_action"), max_len=MAX_HINT_NEXT_ACTION_CHARS),
        overflow_count=_safe_count(data.get("overflow_count")),
        owner_scope_ref=owner,
    )


def owner_scope_matches(left: Any, right: Any) -> bool:
    """Return true only when both safe owner scopes normalize and match exactly."""

    left_scope = normalize_owner_scope_ref(left)
    right_scope = normalize_owner_scope_ref(right)
    return left_scope is not None and left_scope == right_scope


def is_resume_signal(message: Any) -> bool:
    """Recognize only deterministic literal resume command forms."""

    normalized = _normalize_resume_text(message)
    return normalized in _RESUME_COMMANDS


def select_resume_candidate(
    message: Any,
    candidates: Iterable[Any],
    owner_scope_ref: Any,
) -> SuspendedTodoHint | None:
    """Select exactly one same-owner suspended candidate for a resume message."""

    owner = normalize_owner_scope_ref(owner_scope_ref)
    if owner is None:
        return None
    same_owner = [
        hint
        for hint in (normalize_suspended_todo_hint(candidate) for candidate in candidates or ())
        if hint is not None and hint.owner_scope_ref == owner
    ]
    text = _normalize_resume_text(message)

    explicit_matches = [
        hint for hint in same_owner if hint.transaction_id and _contains_ref(text, hint.transaction_id)
    ]
    if len(explicit_matches) == 1:
        return explicit_matches[0]
    if explicit_matches:
        return None

    if text not in _RESUME_COMMANDS:
        return None
    if len(same_owner) != 1:
        return None
    return same_owner[0]


def lifecycle_to_dict(lifecycle: TodoLifecycleSnapshot | None) -> dict[str, Any] | None:
    if lifecycle is None:
        return None
    data = asdict(lifecycle)
    return data


def suspended_hint_to_dict(hint: SuspendedTodoHint | None) -> dict[str, Any] | None:
    if hint is None:
        return None
    return asdict(hint)


def _safe_label(value: Any, *, default: str) -> str:
    text = sanitize_for_progress(value, max_len=MAX_OWNER_LABEL_CHARS).strip()
    return text or default


def _digest_parts(prefix: str, *parts: Any) -> str:
    material = "\x1f".join(str(part) for part in parts if part not in (None, ""))
    digest = hashlib.sha256(f"{prefix}\x1f{material}".encode("utf-8", errors="replace")).hexdigest()
    return f"{prefix}:{digest[:24]}"


def _safe_digest_ref(value: Any) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"[a-z]+:[0-9a-f]{12,64}", text):
        return text[:80]
    return ""


def _as_mapping(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if is_dataclass(raw):
        raw = asdict(raw)
    if not isinstance(raw, dict):
        return None
    return raw


def _normalize_reason(value: Any) -> str | None:
    reason = str(value or "").strip().lower()
    return reason if reason in TODO_SUSPENSION_REASONS else None


def _safe_count(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except Exception:
        return 0


def _safe_optional_text(value: Any, *, max_len: int) -> str | None:
    if value is None:
        return None
    text = sanitize_value_for_progress(value, key="todo_lifecycle", max_len=max_len).strip()
    return text or None


def _normalize_resume_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _contains_ref(message: str, ref: str) -> bool:
    ref_text = str(ref or "").strip().lower()
    if not ref_text:
        return False
    return ref_text in message
