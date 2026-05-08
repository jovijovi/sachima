"""Thread-safe in-memory progress tracker for gateway transactions."""

from __future__ import annotations

import threading
import time
from dataclasses import replace
from typing import Any

from gateway.progress.events import ProgressOperation, TransactionSnapshot
from gateway.progress.redaction import sanitize_for_progress, sanitize_value_for_progress

TRANSACTION_RUNNING = "running"
TRANSACTION_COMPLETED = "completed"
TRANSACTION_FAILED = "failed"

OPERATION_RUNNING = "running"
OPERATION_COMPLETED = "completed"
OPERATION_FAILED = "failed"

_EVENT_TYPES = {
    "tool.started",
    "tool.completed",
    "subagent.tool",
    "subagent.progress",
    "subagent.thinking",
    "subagent.start",
    "subagent.complete",
}


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
            return TransactionSnapshot(
                transaction_id=self.transaction_id,
                title=self.title,
                status=self._status,
                started_at=self._started_at,
                updated_at=self._updated_at,
                completed_at=self._completed_at,
                recent_operations=operations,
            )

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
