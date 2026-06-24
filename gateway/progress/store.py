"""Append-only persistence for sanitized gateway progress events."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Protocol

from gateway.progress.events import (
    ContextUsageSnapshot,
    IterationUsageSnapshot,
    ProgressOperation,
    TodoItemSnapshot,
    TransactionSnapshot,
)
from gateway.progress.redaction import sanitize_value_for_progress
from gateway.progress.todo_lifecycle import (
    lifecycle_to_dict,
    normalize_suspended_todo_hint,
    normalize_todo_lifecycle,
    suspended_hint_to_dict,
)
from hermes_constants import get_hermes_home

# Persistence bounds for the structured todo snapshot. These mirror the tracker
# caps; disk is a second exfiltration surface, so the values are re-sanitized and
# re-bounded here rather than trusted from the in-memory snapshot.
MAX_TODO_ITEMS = 20
MAX_TODO_CONTENT_CHARS = 240
MAX_TODO_ID_CHARS = 120
MAX_TODO_SOURCE_CHARS = 60
MAX_TODO_DEPTH = 1

# Size-based JSONL rotation defaults. ``events.jsonl`` is rotated to
# ``events.jsonl.1`` (and existing archives shift up) once the next append
# would push the live file past ``DEFAULT_EVENT_STORE_MAX_BYTES``; at most
# ``DEFAULT_EVENT_STORE_MAX_FILES`` numbered archives are retained. A
# ``max_bytes`` of 0 disables rotation (legacy unbounded append).
DEFAULT_EVENT_STORE_MAX_BYTES = 50 * 1024 * 1024  # 50 MiB
DEFAULT_EVENT_STORE_MAX_FILES = 5


class ProgressEventStore(Protocol):
    """Minimal sink interface for dashboard-ready progress history."""

    def append_operation(self, snapshot: TransactionSnapshot, operation: ProgressOperation) -> None:
        """Append one sanitized operation record."""

    def append_snapshot(self, snapshot: TransactionSnapshot) -> None:
        """Append one sanitized transaction snapshot record."""

class JsonlProgressEventStore:
    """Append sanitized progress operation records as JSON Lines."""

    _lock_registry: dict[str, threading.Lock] = {}
    _lock_registry_guard = threading.Lock()

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        max_bytes: int | None = None,
        max_files: int | None = None,
    ):
        self.path = Path(path) if path is not None else default_progress_events_path()
        self.max_bytes = _normalize_event_store_max_bytes(max_bytes)
        self.max_files = _normalize_event_store_max_files(max_files)
        self._lock = self._lock_for_path(self.path)

    @classmethod
    def _lock_for_path(cls, path: Path) -> threading.Lock:
        key = str(path.expanduser().resolve(strict=False))
        with cls._lock_registry_guard:
            lock = cls._lock_registry.get(key)
            if lock is None:
                lock = threading.Lock()
                cls._lock_registry[key] = lock
            return lock

    def append_operation(self, snapshot: TransactionSnapshot, operation: ProgressOperation) -> None:
        record = progress_operation_to_record(snapshot, operation)
        self._append_record(record)

    def append_snapshot(self, snapshot: TransactionSnapshot) -> None:
        record = progress_snapshot_to_record(snapshot)
        self._append_record(record)

    def _append_record(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str) + "\n"
        incoming_bytes = len(line.encode("utf-8"))
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._maybe_rotate_locked(incoming_bytes)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)

    def _maybe_rotate_locked(self, incoming_bytes: int) -> None:
        """Rotate the live JSONL file when the next append would exceed the cap.

        The caller must hold ``self._lock`` so rotation is atomic with respect to
        concurrent in-process writers sharing this path. Rotation is best-effort:
        any OS error is swallowed and the record is still appended to the current
        file rather than being dropped.
        """

        if self.max_bytes <= 0:
            return
        try:
            current_size = self.path.stat().st_size
        except OSError:
            return
        if current_size <= 0:
            # Never rotate an empty/just-created file: a single record larger
            # than the cap would otherwise rotate empty files indefinitely.
            return
        if current_size + incoming_bytes <= self.max_bytes:
            return
        try:
            self._rotate_locked()
        except OSError:
            return

    def _rotate_locked(self) -> None:
        # Drop the oldest archive (the one at the retention cap), shift every
        # remaining archive up one numeric suffix, then move the live file to
        # ``.1``. The next append re-creates ``events.jsonl`` in append mode.
        self._rotated_path(self.max_files).unlink(missing_ok=True)
        for index in range(self.max_files - 1, 0, -1):
            source = self._rotated_path(index)
            if source.exists():
                source.replace(self._rotated_path(index + 1))
        self.path.replace(self._rotated_path(1))

    def _rotated_path(self, index: int) -> Path:
        return self.path.with_name(f"{self.path.name}.{index}")


def default_progress_events_path() -> Path:
    """Return the default profile-aware progress JSONL path."""

    return get_hermes_home() / "progress" / "events.jsonl"


def build_progress_event_store(config: dict[str, Any] | None) -> ProgressEventStore | None:
    """Build an optional event store from ``display.task_tracker`` config."""

    if not isinstance(config, dict):
        return None
    if not _is_truthy(config.get("persist_events"), default=False):
        return None
    store_type = str(config.get("event_store", "jsonl") or "jsonl").strip().lower()
    if store_type != "jsonl":
        return None
    return JsonlProgressEventStore(
        config.get("event_store_path") or None,
        max_bytes=config.get("event_store_max_bytes"),
        max_files=config.get("event_store_max_files"),
    )


def _normalize_event_store_max_bytes(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return DEFAULT_EVENT_STORE_MAX_BYTES
    try:
        number = int(value)
    except Exception:
        return DEFAULT_EVENT_STORE_MAX_BYTES
    return max(0, number)  # 0 disables rotation (legacy unbounded append)


def _normalize_event_store_max_files(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return DEFAULT_EVENT_STORE_MAX_FILES
    try:
        number = int(value)
    except Exception:
        return DEFAULT_EVENT_STORE_MAX_FILES
    return max(1, number)  # always retain at least one archive when rotating


def progress_snapshot_to_record(snapshot: TransactionSnapshot) -> dict[str, Any]:
    """Convert a sanitized transaction snapshot into a JSON-serializable record."""

    return {
        "schema_version": 1,
        "record_type": "progress.snapshot",
        "written_at": time.time(),
        "transaction": _safe_transaction(snapshot),
    }


def progress_operation_to_record(
    snapshot: TransactionSnapshot,
    operation: ProgressOperation,
) -> dict[str, Any]:
    """Convert a sanitized snapshot + operation into a JSON-serializable record.

    The tracker already sanitizes user-facing values. This boundary sanitizes
    again because disk persistence is a second exfiltration surface.
    """

    return {
        "schema_version": 1,
        "record_type": "progress.operation",
        "written_at": time.time(),
        "transaction": _safe_transaction(snapshot),
        "operation": {
            "id": _safe_text(operation.id, key="operation_id", max_len=120),
            "event_type": _safe_text(operation.event_type, key="event_type", max_len=120),
            "tool_name": _safe_optional_text(operation.tool_name, key="tool_name", max_len=200),
            "status": _safe_text(operation.status, key="status", max_len=80),
            "preview": _safe_optional_text(operation.preview, key="preview", max_len=1000),
            "args_preview": _safe_optional_text(operation.args_preview, key="args_preview", max_len=1000),
            "started_at": _safe_scalar(operation.started_at),
            "updated_at": _safe_scalar(operation.updated_at),
            "completed_at": _safe_optional_scalar(operation.completed_at),
            "duration": _safe_optional_scalar(operation.duration),
            "is_error": bool(operation.is_error),
            "metadata": _safe_metadata(operation.metadata),
        },
    }


def _safe_transaction(snapshot: TransactionSnapshot) -> dict[str, Any]:
    transaction = {
        "id": _safe_text(snapshot.transaction_id, key="transaction_id", max_len=240),
        "title": _safe_text(snapshot.title, key="title", max_len=500),
        "status": _safe_text(snapshot.status, key="status", max_len=80),
        "started_at": _safe_scalar(snapshot.started_at),
        "updated_at": _safe_scalar(snapshot.updated_at),
        "completed_at": _safe_optional_scalar(snapshot.completed_at),
    }
    if snapshot.context_usage is not None:
        transaction["context_usage"] = _safe_context_usage(snapshot.context_usage)
    if snapshot.iteration_usage is not None:
        transaction["iteration_usage"] = _safe_iteration_usage(snapshot.iteration_usage)
    todo_items = _safe_todo_items(getattr(snapshot, "todo_items", ()))
    # Emit an explicit empty list too. Without this, a transaction that clears
    # its todos later in the run would leave reader summaries showing stale
    # earlier todo state from prior operation records.
    transaction["todo_items"] = todo_items
    todo_lifecycle = _safe_todo_lifecycle(getattr(snapshot, "todo_lifecycle", None))
    transaction["todo_lifecycle"] = todo_lifecycle
    suspended_hint = _safe_suspended_todo_hint(getattr(snapshot, "suspended_todo_hint", None))
    transaction["suspended_todo_hint"] = suspended_hint
    return transaction


def _safe_todo_lifecycle(raw: Any) -> dict[str, Any] | None:
    lifecycle = normalize_todo_lifecycle(raw)
    if lifecycle is None:
        return None
    return lifecycle_to_dict(lifecycle)


def _safe_suspended_todo_hint(raw: Any) -> dict[str, Any] | None:
    hint = normalize_suspended_todo_hint(raw)
    if hint is None:
        return None
    return suspended_hint_to_dict(hint)


def _safe_todo_items(items: Any) -> list[dict[str, Any]]:
    """Re-sanitize the structured todo snapshot for persistence.

    Only the first ``MAX_TODO_ITEMS`` survive; each item's text is redacted and
    bounded again, depth is clamped to the two-level display range, and
    ``parent_id`` is emitted only when present so legacy readers see the same
    shape they always have.
    """

    if not items:
        return []
    safe: list[dict[str, Any]] = []
    for item in list(items)[:MAX_TODO_ITEMS]:
        record = {
            "id": _safe_text(getattr(item, "id", ""), key="todo_id", max_len=MAX_TODO_ID_CHARS),
            "content": _safe_text(getattr(item, "content", ""), key="todo_content", max_len=MAX_TODO_CONTENT_CHARS),
            "status": _safe_text(getattr(item, "status", ""), key="todo_status", max_len=40),
            "depth": min(MAX_TODO_DEPTH, _safe_nonnegative_int(getattr(item, "depth", 0))),
            "source": _safe_text(getattr(item, "source", ""), key="todo_source", max_len=MAX_TODO_SOURCE_CHARS)
            or "todo_tool",
        }
        parent_id = _safe_optional_text(getattr(item, "parent_id", None), key="todo_parent_id", max_len=MAX_TODO_ID_CHARS)
        if parent_id:
            record["parent_id"] = parent_id
        safe.append(record)
    return _normalize_todo_parent_links(safe)


def _normalize_todo_parent_links(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    known_ids = {item.get("id") for item in items if item.get("id")}
    valid_parent_by_id: dict[str, str | None] = {}
    for item in items:
        item_id = str(item.get("id") or "")
        parent_id = item.get("parent_id")
        valid_parent_by_id[item_id] = (
            str(parent_id)
            if parent_id and parent_id != item_id and parent_id in known_ids
            else None
        )

    for item in items:
        item_id = str(item.get("id") or "")
        parent_id = valid_parent_by_id.get(item_id)
        if parent_id and valid_parent_by_id.get(parent_id) is None:
            item["parent_id"] = parent_id
            item["depth"] = MAX_TODO_DEPTH
        else:
            item.pop("parent_id", None)
            item["depth"] = 0
    return items


def _safe_context_usage(usage: ContextUsageSnapshot) -> dict[str, int]:
    return {
        "current_tokens": _safe_nonnegative_int(usage.current_tokens),
        "context_window": _safe_nonnegative_int(usage.context_window),
        "peak_tokens": _safe_nonnegative_int(usage.peak_tokens),
        "compression_count": _safe_nonnegative_int(usage.compression_count),
        "threshold_tokens": _safe_nonnegative_int(usage.threshold_tokens),
    }


def _safe_iteration_usage(usage: IterationUsageSnapshot) -> dict[str, int]:
    return {
        "current": _safe_nonnegative_int(usage.current),
        "maximum": _safe_nonnegative_int(usage.maximum),
    }


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(metadata, dict):
        return {}
    safe: dict[str, str] = {}
    for key, value in metadata.items():
        safe_key = _safe_text(key, key="metadata_key", max_len=160)
        safe[safe_key] = sanitize_value_for_progress(value, key=key, max_len=500)
    return safe


def _safe_optional_text(value: Any, *, key: str, max_len: int) -> str | None:
    if value is None:
        return None
    return _safe_text(value, key=key, max_len=max_len)


def _safe_text(value: Any, *, key: str, max_len: int) -> str:
    return sanitize_value_for_progress(value, key=key, max_len=max_len)


def _safe_optional_scalar(value: Any) -> int | float | None:
    if value is None:
        return None
    return _safe_scalar(value)


def _safe_scalar(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except Exception:
        return None


def _safe_nonnegative_int(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except Exception:
        return 0
    return max(0, number)


def _is_truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "enabled"}:
            return True
        if normalized in {"0", "false", "no", "off", "disabled", ""}:
            return False
    return bool(value)
