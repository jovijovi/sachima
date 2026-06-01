from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

CONTRACT_VERSION = "flowweaver.v0"
HANDLE_TYPE = "flowweaver.handle.v0"

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked"
STATUS_CANCELLED = "cancelled"
STATUS_SKIPPED = "skipped"

STATUS_VOCABULARY = {
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    STATUS_FAILED,
    STATUS_BLOCKED,
    STATUS_CANCELLED,
    STATUS_SKIPPED,
}

DELIVERY_SURFACES = {
    "progress_card",
    "rich_card",
    "final_text",
    "media",
    "file",
    "voice",
    "fallback_text",
}

TARGET_KINDS = {"artifact", "snapshot", "final_text", "transaction", "intent"}
SENSITIVE_KEY_FRAGMENTS = (
    "access_key",
    "authorization",
    "api_key",
    "app_secret",
    "card_json",
    "client_secret",
    "credential",
    "feishu_card_json",
    "full_tool_args",
    "lark_card_json",
    "password",
    "private_key",
    "raw_args",
    "raw_command",
    "raw_output",
    "secret",
    "sig",
    "signature",
    "stderr",
    "stdout",
    "token",
)

ALLOWED_ARTIFACT_KINDS = {"rich_card", "text_result", "fallback_text", "media", "file", "voice"}

_SECRET_KEY_RE = r"(?:[a-z0-9]+[_-])*(?:access[_-]?key|access[_-]?token|api[_-]?key|apikey|app[_-]?secret|card[_-]?json|client[_-]?secret|credential|feishu[_-]?card[_-]?json|full[_-]?tool[_-]?args|lark[_-]?card[_-]?json|password|private[_-]?key|raw[_-]?args|raw[_-]?command|raw[_-]?output|secret|sig|signature|stderr|stdout|token)"
_SECRET_VALUE_RE = r"(?:\"[^\"]*\"|'[^']*'|[^\s&;,}]+)"
_TEXT_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer|basic|token)?\s*[^\s,;]+"),
    re.compile(rf"(?i)\b({_SECRET_KEY_RE}\s*[:=]\s*){_SECRET_VALUE_RE}"),
    re.compile(rf"(?i)([\"']?{_SECRET_KEY_RE}[\"']?\s*:\s*){_SECRET_VALUE_RE}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._-]+"),
    re.compile(r"sk-[A-Za-z0-9]{12,}"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str, *, default: str = "item", max_len: int = 48) -> str:
    text = sanitize_text(value, max_len=160).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if not text:
        text = default
    if text[0].isdigit():
        text = f"{default}_{text}"
    return text[:max_len].strip("_") or default


def is_sensitive_key(key: Any) -> bool:
    key_text = str(key).lower()
    normalized_key = re.sub(r"[^a-z0-9]", "", key_text)
    for fragment in SENSITIVE_KEY_FRAGMENTS:
        normalized_fragment = re.sub(r"[^a-z0-9]", "", fragment.lower())
        if fragment in key_text or normalized_fragment in normalized_key:
            return True
    return False


def sanitize_url_query(text: str) -> str:
    try:
        parts = urlsplit(text)
    except ValueError:
        return text
    if not parts.scheme or not parts.netloc or not parts.query:
        return text
    changed = False
    cleaned_query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if is_sensitive_key(key):
            cleaned_query.append((key, "[REDACTED]"))
            changed = True
        else:
            cleaned_query.append((key, value))
    if not changed:
        return text
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(cleaned_query), ""))


def sanitize_text(value: Any, *, max_len: int = 1200) -> str:
    text = str(value)
    if "://" in text and "?" in text and not any(ch.isspace() for ch in text):
        text = sanitize_url_query(text)
    for pattern in _TEXT_SECRET_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]" if match.lastindex else "[REDACTED]", text)
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


def sanitize_value(value: Any, *, key: Any | None = None, max_len: int = 1200, max_depth: int = 4, max_items: int = 20) -> Any:
    if key is not None and is_sensitive_key(key):
        return "[REDACTED]"
    if isinstance(value, str):
        return sanitize_text(value, max_len=max_len)
    if not isinstance(value, (dict, list, tuple)):
        return value
    if max_depth < 0:
        return "[REDACTED:depth]"
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for index, (raw_key, raw_value) in enumerate(value.items()):
            if index >= max_items:
                cleaned["truncated_fields"] = "[REDACTED:too_many_items]"
                break
            if is_sensitive_key(raw_key):
                cleaned.setdefault("redacted_fields", "[REDACTED]")
                continue
            clean_key = sanitize_text(raw_key, max_len=80)
            cleaned[clean_key] = sanitize_value(raw_value, key=raw_key, max_len=max_len, max_depth=max_depth - 1, max_items=max_items)
        return cleaned
    if isinstance(value, list):
        cleaned_items = [sanitize_value(item, max_len=max_len, max_depth=max_depth - 1, max_items=max_items) for item in value[:max_items]]
        if len(value) > max_items:
            cleaned_items.append("[REDACTED:too_many_items]")
        return cleaned_items
    if isinstance(value, tuple):
        return sanitize_value(list(value), max_len=max_len, max_depth=max_depth, max_items=max_items)
    return value


@dataclass
class TransactionRecord:
    transaction_id: str
    correlation_id: str
    snapshot_id: str
    title: str
    source: dict[str, Any]
    created_at: str
    status: str = STATUS_PENDING
    intents: list[dict[str, Any]] = field(default_factory=list)
    operations: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    deliveries: list[dict[str, Any]] = field(default_factory=list)
    final_text: dict[str, Any] = field(default_factory=dict)
    cancellation_reason: str | None = None

    def clone(self) -> "TransactionRecord":
        return copy.deepcopy(self)
