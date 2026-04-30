"""Append-only persistence for sanitized gateway progress events."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Protocol

from gateway.progress.events import ProgressOperation, TransactionSnapshot
from gateway.progress.redaction import sanitize_value_for_progress
from hermes_constants import get_hermes_home


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

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_progress_events_path()
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
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)


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
    return JsonlProgressEventStore(config.get("event_store_path") or None)


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
    return {
        "id": _safe_text(snapshot.transaction_id, key="transaction_id", max_len=240),
        "title": _safe_text(snapshot.title, key="title", max_len=500),
        "status": _safe_text(snapshot.status, key="status", max_len=80),
        "started_at": _safe_scalar(snapshot.started_at),
        "updated_at": _safe_scalar(snapshot.updated_at),
        "completed_at": _safe_optional_scalar(snapshot.completed_at),
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
