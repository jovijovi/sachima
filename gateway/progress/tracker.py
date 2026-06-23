"""Thread-safe in-memory progress tracker for gateway transactions."""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass, replace
from typing import Any

from gateway.progress.events import (
    ContextUsageSnapshot,
    IterationUsageSnapshot,
    ProgressOperation,
    TodoItemSnapshot,
    TransactionSnapshot,
)
from gateway.progress.redaction import sanitize_for_progress, sanitize_value_for_progress

TRANSACTION_RUNNING = "running"
TRANSACTION_COMPLETED = "completed"
TRANSACTION_FAILED = "failed"

OPERATION_RUNNING = "running"
OPERATION_COMPLETED = "completed"
OPERATION_FAILED = "failed"

# Display-safety bounds for the structured todo snapshot carried on each
# transaction. The workbench renders a compact, redacted preview of the model's
# todo list, not the whole plan — these caps keep one oversized or adversarial
# list from bloating progress snapshots, cards, or JSONL records.
MAX_TODO_ITEMS = 20  # items kept per snapshot (head of the priority-ordered list)
MAX_TODO_CONTENT_CHARS = 240  # per-item description length after redaction
MAX_TODO_ID_CHARS = 120  # per-item id / parent_id length
MAX_TODO_SOURCE_CHARS = 60  # provenance label length
MAX_TODO_DEPTH = 1  # display supports two levels only: parent (0) + child (1)

_VALID_TODO_STATUSES = {"pending", "in_progress", "completed", "cancelled"}

_EVENT_TYPES = {
    "tool.started",
    "tool.completed",
    "subagent.tool",
    "subagent.progress",
    "subagent.thinking",
    "subagent.start",
    "subagent.complete",
}

_MODEL_METADATA_SUFFIX_RE = re.compile(
    r"(?i)\s+(?:knowledge\s+cutoff|cutoff|release(?:d)?(?:\s+date)?|"
    r"api[-_]?key|token|secret|password|authorization|bearer|base[_-]?url|https?://).*$"
)
_MODEL_PAREN_METADATA_RE = re.compile(
    r"(?i)\s*\([^)]*(?:knowledge\s+cutoff|cutoff|release(?:d)?(?:\s+date)?|"
    r"20\d{2}[-_]?\d{2}[-_]?\d{2}|20\d{6}|\d{8})[^)]*\)\s*$"
)
_MODEL_DATE_SUFFIX_RE = re.compile(
    r"(?:[-_/ ](?:20\d{2}[-_]?\d{2}[-_]?\d{2}|20\d{6}|\d{8}))+$"
)
_DISPLAY_UNSAFE_LINE_RE = re.compile(
    r"(?i)(https?://|\b(?:api[-_]?key|token|secret|password|authorization|bearer|base[_-]?url)\b)"
)
_ACCOUNT_LIMIT_HEADER_RE = re.compile(r"(?i)^\s*(?:📈\s*)?\*{0,2}account limits\*{0,2}\s*$")


class ProgressTracker:
    """Maintain recent sanitized progress operations for one transaction.

    The tracker is intentionally pure/in-memory. Methods acquire a
    ``threading.Lock`` because tool progress callbacks can arrive from worker
    threads while the gateway reads snapshots from the event loop thread.
    """

    def __init__(self, transaction_id: str, title: str, max_operations: int = 20):
        self.transaction_id = transaction_id
        self.title = title
        self.max_operations = max(0, int(max_operations))
        now = time.time()
        self._started_at = now
        self._updated_at = now
        self._completed_at: float | None = None
        self._status = TRANSACTION_RUNNING
        self._operations: list[ProgressOperation] = []
        self._context_usage: ContextUsageSnapshot | None = None
        self._iteration_usage: IterationUsageSnapshot | None = None
        self._model_display: str | None = None
        self._account_limit_lines: tuple[str, ...] = ()
        self._todo_items: tuple[TodoItemSnapshot, ...] = ()
        self._next_operation_id = 1
        self._lock = threading.Lock()

    def record_tool_started(
        self,
        tool_name: str | None,
        preview: Any = None,
        args: Any = None,
        **metadata: Any,
    ) -> ProgressOperation:
        """Record that a tool operation started."""

        with self._lock:
            operation = self._new_operation(
                event_type="tool.started",
                tool_name=tool_name,
                status=OPERATION_RUNNING,
                preview=preview,
                args=args,
                metadata=metadata,
            )
            self._append_operation(operation)
            return replace(operation, metadata=dict(operation.metadata))

    def record_tool_completed(
        self,
        tool_name: str | None,
        duration: float | None = None,
        is_error: bool = False,
        preview: Any = None,
        args: Any = None,
        **metadata: Any,
    ) -> ProgressOperation:
        """Mark the most recent matching running operation completed/failed."""

        with self._lock:
            now = time.time()
            status = OPERATION_FAILED if is_error else OPERATION_COMPLETED
            operation = self._find_latest_running(tool_name)

            if operation is None:
                operation = self._new_operation(
                    event_type="tool.completed",
                    tool_name=tool_name,
                    status=status,
                    preview=preview,
                    args=args,
                    metadata=metadata,
                    now=now,
                )
                operation.completed_at = now
                operation.duration = duration
                operation.is_error = bool(is_error)
                self._append_operation(operation, now=now)
                return replace(operation, metadata=dict(operation.metadata))

            operation.status = status
            operation.event_type = "tool.completed"
            operation.updated_at = now
            operation.completed_at = now
            operation.duration = duration
            operation.is_error = bool(is_error)
            if preview is not None:
                operation.preview = sanitize_for_progress(preview)
            if args is not None:
                operation.args_preview = sanitize_for_progress(args)
            if metadata:
                operation.metadata.update(_sanitize_metadata(metadata))
            self._touch(now)
            return replace(operation, metadata=dict(operation.metadata))

    def record_callback_event(
        self,
        event_type: str,
        tool_name: str | None = None,
        preview: Any = None,
        args: Any = None,
        **kwargs: Any,
    ) -> ProgressOperation | None:
        """Record a progress callback event emitted by an agent/subagent."""

        normalized_event = str(event_type or "")
        if normalized_event == "subagent_progress":
            normalized_event = "subagent.progress"
        normalized_tool_name = tool_name or kwargs.pop("name", None)

        if normalized_event == "tool.started":
            return self.record_tool_started(normalized_tool_name, preview=preview, args=args, **kwargs)

        if normalized_event == "tool.completed":
            duration = kwargs.pop("duration", None)
            is_error = bool(kwargs.pop("is_error", kwargs.pop("error", False)))
            return self.record_tool_completed(
                normalized_tool_name,
                duration=duration,
                is_error=is_error,
                preview=preview,
                args=args,
                **kwargs,
            )

        if normalized_event in _EVENT_TYPES:
            status = OPERATION_RUNNING if normalized_event == "subagent.start" else OPERATION_COMPLETED
            event_tool_name = normalized_tool_name or "subagent"
            return self._record_event_operation(
                event_type=normalized_event,
                tool_name=event_tool_name,
                status=status,
                preview=preview,
                args=args,
                **kwargs,
            )

        # Unknown callback events are deliberately ignored for Phase 1: callers
        # can emit extra events without breaking progress tracking.
        return None

    def snapshot(self) -> TransactionSnapshot:
        """Return a sanitized dataclass snapshot of this transaction."""

        with self._lock:
            operations = tuple(replace(op, metadata=dict(op.metadata)) for op in self._operations)
            context_usage = replace(self._context_usage) if self._context_usage is not None else None
            iteration_usage = (
                replace(self._iteration_usage) if self._iteration_usage is not None else None
            )
            return TransactionSnapshot(
                transaction_id=self.transaction_id,
                title=self.title,
                status=self._status,
                started_at=self._started_at,
                updated_at=self._updated_at,
                completed_at=self._completed_at,
                recent_operations=operations,
                context_usage=context_usage,
                iteration_usage=iteration_usage,
                model_display=self._model_display,
                account_limit_lines=self._account_limit_lines,
                todo_items=self._todo_items,
            )

    def update_display_metadata(
        self,
        *,
        model_display: Any = None,
        account_limit_lines: Any = None,
    ) -> None:
        """Update optional, sanitized display-only metadata for this transaction."""

        with self._lock:
            if model_display is not None:
                self._model_display = _sanitize_model_display(model_display)
            if account_limit_lines is not None:
                self._account_limit_lines = _sanitize_account_limit_lines(account_limit_lines)
            self._touch()

    def update_context_usage(
        self,
        *,
        current_tokens: Any = None,
        context_window: Any = None,
        peak_tokens: Any = None,
        compression_count: Any = None,
        threshold_tokens: Any = None,
    ) -> ContextUsageSnapshot:
        """Update sanitized context-pressure counters for the transaction."""

        with self._lock:
            previous_peak = self._context_usage.peak_tokens if self._context_usage is not None else 0
            current = _safe_nonnegative_int(current_tokens)
            explicit_peak = _safe_nonnegative_int(peak_tokens)
            usage = ContextUsageSnapshot(
                current_tokens=current,
                context_window=_safe_nonnegative_int(context_window),
                peak_tokens=max(previous_peak, current, explicit_peak),
                compression_count=_safe_nonnegative_int(compression_count),
                threshold_tokens=_safe_nonnegative_int(threshold_tokens),
            )
            self._context_usage = usage
            self._touch()
            return replace(usage)

    def update_iteration_usage(
        self,
        current_rounds: Any = None,
        max_rounds: Any = None,
    ) -> IterationUsageSnapshot:
        """Update sanitized agent work-round counters for the transaction.

        ``current_rounds`` is the agent's ``api_calls`` count for this turn and
        ``max_rounds`` the configured ``max_iterations`` budget. Either argument
        may be ``None`` to preserve the previously recorded value, so callers can
        seed ``max_rounds`` early and refine ``current_rounds`` as the turn runs.
        """

        with self._lock:
            previous = self._iteration_usage
            current = (
                _safe_nonnegative_int(current_rounds)
                if current_rounds is not None
                else (previous.current if previous is not None else 0)
            )
            maximum = (
                _safe_nonnegative_int(max_rounds)
                if max_rounds is not None
                else (previous.maximum if previous is not None else 0)
            )
            usage = IterationUsageSnapshot(current=current, maximum=maximum)
            self._iteration_usage = usage
            self._touch()
            return replace(usage)

    def update_todo_items(
        self,
        items: Any,
        source: str = "todo_tool",
    ) -> tuple[TodoItemSnapshot, ...]:
        """Replace the transaction's structured todo snapshot.

        ``items`` is the raw list returned by :meth:`tools.todo_tool.TodoStore.read`
        (dicts of ``id``/``content``/``status`` plus optional ``parent_id``). The
        list is sanitized, redacted, capped, and flattened to at most two display
        levels here so the snapshot, cards, and JSONL records all stay compact and
        secret-free. Malformed input never raises — it is dropped item by item.
        """

        with self._lock:
            self._todo_items = _sanitize_todo_items(items, source=source)
            self._touch()
            return self._todo_items

    def mark_completed(self, is_error: bool = False) -> None:
        """Mark the transaction itself complete/failed."""

        with self._lock:
            now = time.time()
            self._status = TRANSACTION_FAILED if is_error else TRANSACTION_COMPLETED
            self._completed_at = now
            self._touch(now)

    def _record_event_operation(
        self,
        event_type: str,
        tool_name: str | None,
        status: str,
        preview: Any = None,
        args: Any = None,
        **metadata: Any,
    ) -> ProgressOperation:
        with self._lock:
            now = time.time()
            operation = self._new_operation(
                event_type=event_type,
                tool_name=tool_name,
                status=status,
                preview=preview,
                args=args,
                metadata=metadata,
                now=now,
            )
            if status != OPERATION_RUNNING:
                operation.completed_at = now
            self._append_operation(operation, now=now)
            return replace(operation, metadata=dict(operation.metadata))

    def _new_operation(
        self,
        *,
        event_type: str,
        tool_name: str | None,
        status: str,
        preview: Any = None,
        args: Any = None,
        metadata: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> ProgressOperation:
        now = time.time() if now is None else now
        operation_id = f"op-{self._next_operation_id}"
        self._next_operation_id += 1
        return ProgressOperation(
            id=operation_id,
            event_type=event_type,
            tool_name=sanitize_for_progress(tool_name, max_len=160) if tool_name is not None else None,
            status=status,
            preview=sanitize_for_progress(preview) if preview is not None else None,
            args_preview=sanitize_for_progress(args) if args is not None else None,
            started_at=now,
            updated_at=now,
            metadata=_sanitize_metadata(metadata or {}),
        )

    def _append_operation(self, operation: ProgressOperation, now: float | None = None) -> None:
        self._operations.append(operation)
        self._trim_operations()
        self._touch(time.time() if now is None else now)

    def _find_latest_running(self, tool_name: str | None) -> ProgressOperation | None:
        tool_name_text = str(tool_name) if tool_name is not None else None
        for operation in reversed(self._operations):
            if operation.status == OPERATION_RUNNING and operation.tool_name == tool_name_text:
                return operation
        return None

    def _trim_operations(self) -> None:
        if self.max_operations and len(self._operations) > self.max_operations:
            del self._operations[: len(self._operations) - self.max_operations]
        elif self.max_operations == 0:
            self._operations.clear()

    def _touch(self, now: float | None = None) -> None:
        self._updated_at = time.time() if now is None else now


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {str(key): sanitize_value_for_progress(value, key=key) for key, value in metadata.items()}


def _sanitize_todo_items(items: Any, *, source: str) -> tuple[TodoItemSnapshot, ...]:
    """Sanitize raw todo state into a bounded, two-level display snapshot.

    Order is priority (matching ``TodoStore``); only the first ``MAX_TODO_ITEMS``
    survive. Each item's text is redacted and length-capped, status is coerced to
    a known value (unknown → ``pending``), and depth is clamped so a child always
    points at a top-level sibling. Parent links to dropped/unknown ids are severed
    so the item falls back to top level.
    """

    try:
        raw_list = list(items) if items is not None else []
    except Exception:
        return ()

    default_source = _sanitize_todo_field(source, key="todo_source", max_len=MAX_TODO_SOURCE_CHARS) or "todo_tool"

    prelim: list[dict[str, Any]] = []
    known_ids: set[str] = set()
    for index, entry in enumerate(raw_list[:MAX_TODO_ITEMS]):
        data = _coerce_todo_mapping(entry)
        if data is None:
            continue
        item_id = _sanitize_todo_field(data.get("id"), key="todo_id", max_len=MAX_TODO_ID_CHARS)
        if not item_id:
            item_id = f"todo-{index + 1}"
        prelim.append(
            {
                "id": item_id,
                "content": _sanitize_todo_content(data.get("content")),
                "status": _sanitize_todo_status(data.get("status")),
                "parent_raw": _sanitize_todo_field(data.get("parent_id"), key="todo_parent_id", max_len=MAX_TODO_ID_CHARS),
                "source": _sanitize_todo_field(data.get("source"), key="todo_source", max_len=MAX_TODO_SOURCE_CHARS)
                or default_source,
            }
        )
        known_ids.add(item_id)

    valid_parent_by_id: dict[str, str | None] = {}
    for item in prelim:
        parent_raw = item["parent_raw"]
        valid_parent_by_id[item["id"]] = (
            parent_raw
            if parent_raw and parent_raw != item["id"] and parent_raw in known_ids
            else None
        )

    results: list[TodoItemSnapshot] = []
    for item in prelim:
        parent_id = valid_parent_by_id[item["id"]]
        # Keep only one display level: children may point at top-level siblings,
        # never at another child. Cycles therefore fall back to top-level too.
        effective_parent_id = parent_id if parent_id and valid_parent_by_id.get(parent_id) is None else None
        results.append(
            TodoItemSnapshot(
                id=item["id"],
                content=item["content"],
                status=item["status"],
                parent_id=effective_parent_id,
                depth=MAX_TODO_DEPTH if effective_parent_id else 0,
                source=item["source"],
            )
        )
    return tuple(results)


def _coerce_todo_mapping(entry: Any) -> Mapping[str, Any] | dict[str, Any] | None:
    if isinstance(entry, Mapping):
        return entry
    if is_dataclass(entry) and not isinstance(entry, type):
        try:
            return asdict(entry)
        except Exception:
            return None
    if entry is None or isinstance(entry, (str, bytes, int, float, bool)):
        return None
    # Generic object: pull only the known todo attributes, never its whole repr.
    data: dict[str, Any] = {}
    for field_name in ("id", "content", "status", "parent_id", "source"):
        if hasattr(entry, field_name):
            data[field_name] = getattr(entry, field_name)
    return data or None


def _sanitize_todo_field(value: Any, *, key: str, max_len: int) -> str:
    if value is None:
        return ""
    text = sanitize_value_for_progress(value, key=key, max_len=max_len)
    return text.replace("\n", " ").strip()


def _sanitize_todo_content(value: Any) -> str:
    text = sanitize_value_for_progress(value, key="todo_content", max_len=MAX_TODO_CONTENT_CHARS)
    text = text.replace("\n", " ").strip()
    return text or "(no description)"


def _sanitize_todo_status(value: Any) -> str:
    text = sanitize_value_for_progress(value, key="todo_status", max_len=40).strip().lower()
    return text if text in _VALID_TODO_STATUSES else "pending"


def _sanitize_model_display(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = _MODEL_METADATA_SUFFIX_RE.sub("", text)
    previous = None
    while previous != text:
        previous = text
        text = _MODEL_PAREN_METADATA_RE.sub("", text)
        text = _MODEL_DATE_SUFFIX_RE.sub("", text).strip(" -_/")
    if not text or _DISPLAY_UNSAFE_LINE_RE.search(text):
        return None
    safe = sanitize_for_progress(text, max_len=160).replace("\n", " ").strip()
    if not safe or "[REDACTED]" in safe or _DISPLAY_UNSAFE_LINE_RE.search(safe):
        return None
    return safe


def _sanitize_account_limit_lines(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raw_lines = value.splitlines()
    else:
        try:
            raw_lines = list(value)
        except Exception:
            raw_lines = [value]

    lines: list[str] = []
    for raw in raw_lines:
        text = str(raw or "").strip()
        if not text or _ACCOUNT_LIMIT_HEADER_RE.match(text):
            continue
        if _DISPLAY_UNSAFE_LINE_RE.search(text):
            continue
        safe = sanitize_for_progress(text, max_len=180).replace("\n", " ").strip()
        if not safe or "[REDACTED]" in safe or _DISPLAY_UNSAFE_LINE_RE.search(safe):
            continue
        lines.append(safe)
        if len(lines) >= 4:
            break
    return tuple(lines)


def _safe_nonnegative_int(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except Exception:
        return 0
    return max(0, number)
