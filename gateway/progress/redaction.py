"""Display-oriented redaction for gateway progress updates."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

REDACTION_TEXT = "[REDACTED]"
_DEFAULT_MAX_LEN = 1000

# Key matching is intentionally conservative from a display perspective: if a
# field name strongly suggests credential material, redact the value entirely.
_SENSITIVE_KEY_FRAGMENTS = (
    "apikey",
    "token",
    "secret",
    "password",
    "passwd",
    "authorization",
    "bearer",
    "webhook",
    "credential",
    "privatekey",
)

_SENSITIVE_NAME_PATTERN = (
    r"[A-Za-z0-9_.-]*(?:"
    r"api[-_]?key|private[-_]?key|secret[-_]?access[-_]?key|"
    r"access[-_]?token|client[-_]?secret|token|secret|password|passwd|"
    r"authorization|bearer|webhook|signature|credential"
    r")[A-Za-z0-9_.-]*"
)

# URL query values that commonly carry short-lived credentials/signatures.
_SENSITIVE_QUERY_VALUE_RE = re.compile(
    r"(?P<lead>[?&;](?:(?:key|sig)|" + _SENSITIVE_NAME_PATTERN + r")=)"
    r"(?P<value>[^&#\s;]*)",
    re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?P<lead>\b(?:" + _SENSITIVE_NAME_PATTERN + r")\s*=\s*)"
    r"(?:(?P<quote>['\"])(?P<qvalue>[^'\"]*)(?P=quote)|(?P<uvalue>[^\s&;,]+))",
    re.IGNORECASE,
)
_SENSITIVE_QUOTED_KEY_RE = re.compile(
    r"(?P<lead>(?P<keyquote>['\"])(?:(?:key|sig)|" + _SENSITIVE_NAME_PATTERN + r")(?P=keyquote)\s*:\s*)"
    r"(?P<quote>['\"])(?P<value>[^'\"]*)(?P=quote)",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(
    r"(?i)(\b(?:authorization\s*[:=]\s*)?bearer\s+)[A-Za-z0-9._~+/=-]+"
)
_AUTHORIZATION_QUOTED_HEADER_RE = re.compile(
    r"(?P<lead>\bauthorization\s*:\s*)(?P<quote>['\"])(?P<value>[^'\"]+)(?P=quote)",
    re.IGNORECASE,
)
_AUTHORIZATION_HEADER_RE = re.compile(
    r"(?P<lead>\bauthorization\s*:\s*(?:(?:bearer|basic|token|apikey|api-key)\s+)?)"
    r"(?P<quote>['\"]?)(?P<value>[^\s'\";,]+)(?P=quote)",
    re.IGNORECASE,
)
_SENSITIVE_COLON_RE = re.compile(
    r"(?P<lead>\b(?:x[-_]?api[-_]?key|api[-_]?key|token|secret|password|passwd|webhook|signature|sig|key|credential)\s*:\s*)"
    r"(?P<quote>['\"]?)(?P<value>[^\s'\";,]+)(?P=quote)",
    re.IGNORECASE,
)


def sanitize_for_progress(data: Any, max_len: int = _DEFAULT_MAX_LEN) -> str:
    """Return a safe, bounded string for user-facing progress displays.

    The sanitizer is best-effort and must never raise, even for objects whose
    repr/serialization is broken. It redacts credential-shaped mapping values
    and sensitive URL query values before rendering.
    """

    return sanitize_value_for_progress(data, max_len=max_len)


def sanitize_value_for_progress(
    data: Any,
    *,
    key: Any = None,
    max_len: int = _DEFAULT_MAX_LEN,
) -> str:
    """Return a safe display string, optionally applying key-aware redaction."""

    try:
        if max_len <= 0:
            return ""
    except Exception:
        max_len = _DEFAULT_MAX_LEN

    try:
        sanitized = _sanitize_value(data, key=key, seen=set())
        if isinstance(sanitized, str):
            rendered = sanitized
        else:
            rendered = json.dumps(
                sanitized,
                ensure_ascii=False,
                sort_keys=True,
                separators=(", ", ": "),
                default=lambda _value: "<unserializable>",
            )
    except Exception:
        rendered = "<unserializable>"

    rendered = _redact_text(rendered)
    return _cap(rendered, max_len)


def _sanitize_value(value: Any, *, key: Any = None, seen: set[int]) -> Any:
    if _is_sensitive_key(key):
        return REDACTION_TEXT

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        return _redact_text(value)

    value_id = id(value)
    if value_id in seen:
        return "<cycle>"

    if isinstance(value, Mapping):
        seen.add(value_id)
        try:
            return {
                _safe_key(item_key): _sanitize_value(item_value, key=item_key, seen=seen)
                for item_key, item_value in value.items()
            }
        finally:
            seen.discard(value_id)

    if isinstance(value, (list, tuple, set, frozenset)):
        seen.add(value_id)
        try:
            return [_sanitize_value(item, seen=seen) for item in value]
        finally:
            seen.discard(value_id)

    if is_dataclass(value) and not isinstance(value, type):
        seen.add(value_id)
        try:
            return _sanitize_value(asdict(value), seen=seen)
        except Exception:
            return _safe_repr(value)
        finally:
            seen.discard(value_id)

    return _redact_text(_safe_repr(value))


def _is_sensitive_key(key: Any) -> bool:
    if key is None:
        return False
    normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
    if not normalized:
        return False
    return any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS)


def _safe_key(key: Any) -> str:
    try:
        return str(key)
    except Exception:
        return "<unprintable-key>"


def _safe_repr(value: Any) -> str:
    try:
        return repr(value)
    except Exception:
        return f"<{type(value).__name__}>"


def _redact_text(text: str) -> str:
    text = _BEARER_RE.sub(r"\1" + REDACTION_TEXT, text)
    text = _AUTHORIZATION_QUOTED_HEADER_RE.sub(
        lambda match: f"{match.group('lead')}{match.group('quote')}{REDACTION_TEXT}{match.group('quote')}",
        text,
    )
    text = _AUTHORIZATION_HEADER_RE.sub(
        lambda match: f"{match.group('lead')}{match.group('quote')}{REDACTION_TEXT}{match.group('quote')}",
        text,
    )
    text = _SENSITIVE_QUOTED_KEY_RE.sub(
        lambda match: f"{match.group('lead')}{match.group('quote')}{REDACTION_TEXT}{match.group('quote')}",
        text,
    )
    text = _SENSITIVE_COLON_RE.sub(
        lambda match: f"{match.group('lead')}{match.group('quote')}{REDACTION_TEXT}{match.group('quote')}",
        text,
    )
    text = _SENSITIVE_QUERY_VALUE_RE.sub(r"\g<lead>" + REDACTION_TEXT, text)
    return _SENSITIVE_ASSIGNMENT_RE.sub(_redact_assignment_match, text)


def _redact_assignment_match(match: re.Match[str]) -> str:
    quote = match.group("quote") or ""
    return f"{match.group('lead')}{quote}{REDACTION_TEXT}{quote}"


def _cap(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    if max_len == 1:
        return "…"
    return text[: max_len - 1] + "…"
