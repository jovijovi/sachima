"""Dataclasses used by pure gateway progress tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProgressOperation:
    """A sanitized, display-ready progress operation snapshot."""

    id: str
    event_type: str
    tool_name: str | None
    status: str
    preview: str | None = None
    args_preview: str | None = None
    started_at: float = 0.0
    updated_at: float = 0.0
    completed_at: float | None = None
    duration: float | None = None
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextUsageSnapshot:
    """Sanitized context-pressure counters for one transaction."""

    current_tokens: int = 0
    context_window: int = 0
    peak_tokens: int = 0
    compression_count: int = 0
    threshold_tokens: int = 0


@dataclass
class IterationUsageSnapshot:
    """Sanitized agent work-round counters for one transaction.

    ``current`` is the number of agent API calls (work rounds) used this user
    turn; ``maximum`` is the configured iteration budget (``max_iterations``).
    Both are non-negative; a ``maximum`` of 0 means "no meaningful budget" and
    callers should omit display rather than render ``0 / 0``.
    """

    current: int = 0
    maximum: int = 0


@dataclass
class TransactionSnapshot:
    """A sanitized, display-ready snapshot of one running transaction."""

    transaction_id: str
    title: str
    status: str
    started_at: float
    updated_at: float
    completed_at: float | None = None
    recent_operations: tuple[ProgressOperation, ...] = ()
    context_usage: ContextUsageSnapshot | None = None
    iteration_usage: IterationUsageSnapshot | None = None
    model_display: str | None = None
    account_limit_lines: tuple[str, ...] = ()
