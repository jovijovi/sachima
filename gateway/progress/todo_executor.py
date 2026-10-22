"""Shared validation for the optional per-item TODO executor label.

``executor`` names the agent a delegated todo item runs on (for example
``claude`` or ``codex``). It is a display label only — never an
authorization, routing, or lifecycle signal — and it comes exclusively
from the structured field, never from natural-language content.

Every sanitization boundary (todo tool, tracker, JSONL store, reader,
renderers) calls :func:`normalize_todo_executor` itself, preserving the
fail-closed defense-in-depth pattern while keeping the rules in one place.
"""

from __future__ import annotations

import re
from typing import Any

from gateway.progress.redaction import sanitize_value_for_progress

MAX_TODO_EXECUTOR_CHARS = 32

# Lowercase compact token: starts alphanumeric; then a-z 0-9 . _ - only.
# The charset cannot form URLs, markdown links, Feishu <at> mentions,
# key:value pairs, or shell-meaningful strings.
_SAFE_TODO_EXECUTOR_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")

# Mirror renderers._TOKEN_LIKE_SKILL_PREFIXES: credential-shaped values must
# never render as an "executor", even if they fit the charset.
_TOKEN_LIKE_EXECUTOR_PREFIXES = (
    "sk-", "sk_", "ghp_", "gho_", "github_pat_", "xox", "hf_", "hf-", "pat_",
)

# Canonical short forms for known long labels. Applied only after full
# validation, so an alias can never bypass the charset/credential defenses,
# and legacy stored values (``hermes-agent``) display in the short form.
_TODO_EXECUTOR_ALIASES = {"hermes-agent": "hermes"}


def normalize_todo_executor(value: Any) -> str | None:
    """Return a safe lowercase executor token, or ``None`` (drop the field).

    Invalid input never raises and never truncates: an over-long or unsafe
    label is dropped entirely — a truncated identity is a wrong identity,
    worse than none.
    """
    if not isinstance(value, str):
        return None
    text = sanitize_value_for_progress(
        value, key="todo_executor", max_len=MAX_TODO_EXECUTOR_CHARS + 8
    )
    text = text.strip().lower()
    if not text or "[redacted]" in text:
        return None
    if text.startswith(_TOKEN_LIKE_EXECUTOR_PREFIXES):
        return None
    if not _SAFE_TODO_EXECUTOR_RE.match(text):
        return None
    return _TODO_EXECUTOR_ALIASES.get(text, text)
