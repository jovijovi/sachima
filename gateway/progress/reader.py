"""Read-only helpers for dashboard progress event history."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from gateway.progress.redaction import sanitize_value_for_progress

DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_LINES = 10_000
DEFAULT_TRANSACTION_LIMIT = 50
DEFAULT_EVENT_LIMIT = 200

# Display bounds for the structured todo snapshot, re-applied on read because the
# JSONL store is treated as untrusted user-facing data.
MAX_TODO_ITEMS = 20
MAX_TODO_CONTENT_CHARS = 240
MAX_TODO_ID_CHARS = 120
MAX_TODO_SOURCE_CHARS = 60
MAX_TODO_DEPTH = 1
_VALID_TODO_STATUSES = {"pending", "in_progress", "completed", "cancelled"}
# Read across the live ``events.jsonl`` plus up to this many rotated archives
# (``events.jsonl.1`` … ``events.jsonl.N``) so the dashboard keeps seeing recent
# history after a size-based rotation.
DEFAULT_MAX_ROTATED_FILES = 5


ProgressListResponse = dict[str, Any]
ProgressDetailResponse = dict[str, Any]


def list_progress_transactions(
    path: str | Path | None,
    *,
    limit: int = DEFAULT_TRANSACTION_LIMIT,
    status: str | None = "all",
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_lines: int = DEFAULT_MAX_LINES,
) -> ProgressListResponse:
    """Return recent transaction summaries from a JSONL progress event store.

    The reader is intentionally defensive: the JSONL file is local state, but it
    is still treated as untrusted user-facing data. Malformed lines are skipped,
    large files are bounded, and all response strings are sanitized again.
    """

    records, skipped_lines = _read_progress_records(path, max_bytes=max_bytes, max_lines=max_lines)
    summaries = _summarize_transactions(records)
    normalized_status = _safe_status_filter(status)
    if normalized_status != "all":
        summaries = [tx for tx in summaries if tx.get("status") == normalized_status]
    summaries.sort(key=lambda tx: _sort_value(tx.get("_sort_at")), reverse=True)
    limited = [_strip_private_fields(tx) for tx in summaries[: _safe_limit(limit, DEFAULT_TRANSACTION_LIMIT)]]
    return {"transactions": limited, "skipped_lines": skipped_lines}


def get_progress_transaction_events(
    path: str | Path | None,
    transaction_id: str,
    *,
    limit: int = DEFAULT_EVENT_LIMIT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_lines: int = DEFAULT_MAX_LINES,
) -> ProgressDetailResponse:
    """Return a bounded chronological event timeline for one transaction."""

    records, skipped_lines = _read_progress_records(path, max_bytes=max_bytes, max_lines=max_lines)
    safe_id = _safe_text(transaction_id, key="transaction_id", max_len=240)
    matching = [record for record in records if (record.get("transaction") or {}).get("id") == safe_id]
    matching.sort(key=lambda record: _sort_value(record.get("written_at")))
    event_limit = _safe_limit(limit, DEFAULT_EVENT_LIMIT)
    recent = matching[-event_limit:]
    transaction = None
    summaries = _summarize_transactions(matching)
    if summaries:
        summaries.sort(key=lambda tx: _sort_value(tx.get("_sort_at")), reverse=True)
        transaction = _strip_private_fields(summaries[0])
    return {
        "transaction": transaction,
        "events": [_strip_private_fields(record) for record in recent],
        "skipped_lines": skipped_lines,
    }


def _read_progress_records(
    path: str | Path | None,
    *,
    max_bytes: int,
    max_lines: int,
    max_files: int = DEFAULT_MAX_ROTATED_FILES,
) -> tuple[list[dict[str, Any]], int]:
    if path is None:
        return [], 0
    selected = _discover_progress_files(Path(path), max_files=max_files)
    if not selected:
        return [], 0

    records: list[dict[str, Any]] = []
    skipped = 0
    for line in _bounded_lines_across_files(selected, max_bytes=max_bytes, max_lines=max_lines):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except Exception:
            skipped += 1
            continue
        normalized = _normalize_record(raw)
        if normalized is None:
            skipped += 1
            continue
        records.append(normalized)
    return records, skipped


def _discover_progress_files(event_path: Path, *, max_files: int) -> list[Path]:
    """Return progress JSONL files newest-first: live file, then ``.1`` … ``.N``.

    Only exact numeric siblings of the configured path are considered, so
    unrelated files are never read. Missing archives are skipped; a single
    missing index does not stop discovery of later archives.
    """

    selected: list[Path] = []
    if event_path.exists() and event_path.is_file():
        selected.append(event_path)
    cap = max(0, int(max_files or 0))
    for index in range(1, cap + 1):
        rotated = event_path.with_name(f"{event_path.name}.{index}")
        if rotated.exists() and rotated.is_file():
            selected.append(rotated)
    return selected


def _bounded_lines_across_files(
    paths: list[Path],
    *,
    max_bytes: int,
    max_lines: int,
) -> list[str]:
    """Tail-read newest-first across files within global bounds, chronologically.

    ``paths`` arrives newest-first (live file then ``.1``, ``.2`` …). The most
    recent lines are collected up to the shared byte/line caps and then reversed
    so the aggregated stream is oldest-to-newest for the summarizers — preserving
    chronology across a rotation boundary while still bounding memory.
    """

    max_bytes = max(1, int(max_bytes or DEFAULT_MAX_BYTES))
    max_lines = max(1, int(max_lines or DEFAULT_MAX_LINES))
    remaining_bytes = max_bytes
    remaining_lines = max_lines
    chunks: list[list[str]] = []  # newest file first
    for path in paths:
        if remaining_lines <= 0 or remaining_bytes <= 0:
            break
        try:
            chunk = _bounded_lines(path, max_bytes=remaining_bytes, max_lines=remaining_lines)
        except OSError:
            # The event store rotates by renaming ``events.jsonl`` to
            # ``events.jsonl.1`` under a writer lock. Dashboard reads are
            # intentionally lock-free, so a path discovered milliseconds ago may
            # disappear before ``stat``/``open``. Treat that as a transient empty
            # file instead of surfacing a 500 to the workbench.
            continue
        if not chunk:
            continue
        chunks.append(chunk)
        remaining_lines -= len(chunk)
        remaining_bytes -= sum(len(line.encode("utf-8")) + 1 for line in chunk)
    chunks.reverse()  # oldest file first → chronological aggregate
    lines: list[str] = []
    for chunk in chunks:
        lines.extend(chunk)
    return lines


def _bounded_lines(path: Path, *, max_bytes: int, max_lines: int) -> list[str]:
    max_bytes = max(1, int(max_bytes or DEFAULT_MAX_BYTES))
    max_lines = max(1, int(max_lines or DEFAULT_MAX_LINES))
    size = path.stat().st_size
    with path.open("rb") as handle:
        truncated = size > max_bytes
        if truncated:
            handle.seek(size - max_bytes)
        data = handle.read(max_bytes + 1)
    lines = data.decode("utf-8", errors="replace").splitlines()
    if size > max_bytes and lines:
        # Drop the first partial line when reading from the tail of a large file.
        lines = lines[1:]
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return lines


def _normalize_record(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    record_type = _safe_text(raw.get("record_type"), key="record_type", max_len=80)
    if record_type not in {"progress.operation", "progress.snapshot"}:
        return None
    transaction = _normalize_transaction(raw.get("transaction"))
    if transaction is None:
        return None
    record: dict[str, Any] = {
        "schema_version": _safe_int(raw.get("schema_version"), default=1),
        "record_type": record_type,
        "written_at": _safe_number(raw.get("written_at")),
        "transaction": transaction,
    }
    if record_type == "progress.operation":
        operation = _normalize_operation(raw.get("operation"))
        if operation is None:
            return None
        record["operation"] = operation
    return record


def _normalize_transaction(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    tx_id = _safe_text(raw.get("id"), key="transaction_id", max_len=240)
    if not tx_id:
        return None
    transaction = {
        "id": tx_id,
        "title": _safe_text(raw.get("title"), key="title", max_len=500),
        "status": _safe_text(raw.get("status"), key="status", max_len=80),
        "started_at": _safe_number(raw.get("started_at")),
        "updated_at": _safe_number(raw.get("updated_at")),
        "completed_at": _safe_optional_number(raw.get("completed_at")),
    }
    context_usage = _safe_context_usage(raw.get("context_usage"))
    if context_usage is not None:
        transaction["context_usage"] = context_usage
    iteration_usage = _safe_iteration_usage(raw.get("iteration_usage"))
    if iteration_usage is not None:
        transaction["iteration_usage"] = iteration_usage
    if "todo_items" in raw:
        # Preserve an explicit empty list so a later snapshot can clear stale
        # todo state seen in earlier operation records. Legacy records that lack
        # the field still omit it and remain compatible.
        transaction["todo_items"] = _safe_todo_items(raw.get("todo_items"))
    return transaction


def _safe_todo_items(raw: Any) -> list[dict[str, Any]]:
    """Normalize a persisted ``todo_items`` array, dropping invalid entries.

    Old records without the field yield ``[]``. Each surviving item is
    re-sanitized and re-bounded: text is redacted/capped, status defaults to
    ``pending`` when unknown, depth is clamped to the two-level range, and
    ``parent_id`` is kept only when present and non-empty.
    """

    if not isinstance(raw, list):
        return []
    items: list[dict[str, Any]] = []
    for entry in raw[:MAX_TODO_ITEMS]:
        if not isinstance(entry, dict):
            continue
        item_id = _safe_text(entry.get("id"), key="todo_id", max_len=MAX_TODO_ID_CHARS)
        content = _safe_text(entry.get("content"), key="todo_content", max_len=MAX_TODO_CONTENT_CHARS)
        if not item_id and not content:
            continue
        status = _safe_text(entry.get("status"), key="todo_status", max_len=40).lower()
        if status not in _VALID_TODO_STATUSES:
            status = "pending"
        item: dict[str, Any] = {
            "id": item_id,
            "content": content,
            "status": status,
            "depth": min(MAX_TODO_DEPTH, _safe_nonnegative_int(entry.get("depth"))),
            "source": _safe_text(entry.get("source"), key="todo_source", max_len=MAX_TODO_SOURCE_CHARS) or "todo_tool",
        }
        parent_id = _safe_optional_text(entry.get("parent_id"), key="todo_parent_id", max_len=MAX_TODO_ID_CHARS)
        if parent_id:
            item["parent_id"] = parent_id
        items.append(item)
    return _normalize_todo_parent_links(items)


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


def _safe_context_usage(raw: Any) -> dict[str, int] | None:
    if not isinstance(raw, dict):
        return None
    usage = {
        "current_tokens": _safe_nonnegative_int(raw.get("current_tokens")),
        "context_window": _safe_nonnegative_int(raw.get("context_window")),
        "peak_tokens": _safe_nonnegative_int(raw.get("peak_tokens")),
        "compression_count": _safe_nonnegative_int(raw.get("compression_count")),
        "threshold_tokens": _safe_nonnegative_int(raw.get("threshold_tokens")),
    }
    if not any(usage.values()):
        return None
    return usage


def _safe_iteration_usage(raw: Any) -> dict[str, int] | None:
    if not isinstance(raw, dict):
        return None
    usage = {
        "current": _safe_nonnegative_int(raw.get("current")),
        "maximum": _safe_nonnegative_int(raw.get("maximum")),
    }
    # Without a meaningful budget there is nothing to render as ``current / max``,
    # so omit it (this also drops legacy records that never carried the field).
    if usage["maximum"] <= 0:
        return None
    return usage


def _normalize_operation(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    return {
        "id": _safe_text(raw.get("id"), key="operation_id", max_len=120),
        "event_type": _safe_text(raw.get("event_type"), key="event_type", max_len=120),
        "tool_name": _safe_optional_text(raw.get("tool_name"), key="tool_name", max_len=200),
        "status": _safe_text(raw.get("status"), key="status", max_len=80),
        "preview": _safe_optional_text(raw.get("preview"), key="preview", max_len=1000),
        "args_preview": _safe_optional_text(raw.get("args_preview"), key="args_preview", max_len=1000),
        "started_at": _safe_number(raw.get("started_at")),
        "updated_at": _safe_number(raw.get("updated_at")),
        "completed_at": _safe_optional_number(raw.get("completed_at")),
        "duration": _safe_optional_number(raw.get("duration")),
        "is_error": bool(raw.get("is_error")),
        "metadata": _safe_metadata(raw.get("metadata")),
    }


def _summarize_transactions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for record in records:
        transaction = record.get("transaction") or {}
        tx_id = transaction.get("id")
        if not tx_id:
            continue
        summary = summaries.setdefault(
            tx_id,
            {
                "id": tx_id,
                "title": transaction.get("title") or tx_id,
                "status": transaction.get("status") or "running",
                "started_at": transaction.get("started_at"),
                "updated_at": transaction.get("updated_at"),
                "completed_at": transaction.get("completed_at"),
                "context_usage": transaction.get("context_usage"),
                "iteration_usage": transaction.get("iteration_usage"),
                "todo_items": transaction.get("todo_items"),
                "operation_count": 0,
                "last_operation": None,
                "_sort_at": record.get("written_at"),
                "_last_operation_at": None,
            },
        )
        _merge_transaction(summary, transaction, record.get("written_at"))
        if record.get("record_type") == "progress.operation" and isinstance(record.get("operation"), dict):
            operation = record["operation"]
            summary["operation_count"] += 1
            op_sort = _first_number(operation.get("updated_at"), operation.get("completed_at"), record.get("written_at"))
            if summary.get("_last_operation_at") is None or _sort_value(op_sort) >= _sort_value(summary.get("_last_operation_at")):
                summary["_last_operation_at"] = op_sort
                summary["last_operation"] = _operation_summary(operation)
    return list(summaries.values())


def _merge_transaction(summary: dict[str, Any], transaction: dict[str, Any], written_at: Any) -> None:
    if transaction.get("title"):
        summary["title"] = transaction["title"]
    if transaction.get("status"):
        summary["status"] = transaction["status"]
    if summary.get("started_at") is None or _sort_value(transaction.get("started_at")) < _sort_value(summary.get("started_at")):
        summary["started_at"] = transaction.get("started_at")
    if transaction.get("updated_at") is not None:
        summary["updated_at"] = transaction.get("updated_at")
    if transaction.get("completed_at") is not None:
        summary["completed_at"] = transaction.get("completed_at")
    if transaction.get("context_usage") is not None:
        summary["context_usage"] = transaction.get("context_usage")
    if transaction.get("iteration_usage") is not None:
        summary["iteration_usage"] = transaction.get("iteration_usage")
    # Latest record with a todo snapshot wins; records without the field never
    # clobber an earlier snapshot (a transaction rarely clears its todo list).
    if transaction.get("todo_items") is not None:
        summary["todo_items"] = transaction.get("todo_items")
    summary["_sort_at"] = max(
        _sort_value(summary.get("_sort_at")),
        _sort_value(written_at),
        _sort_value(transaction.get("updated_at")),
    )


def _operation_summary(operation: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_type": operation.get("event_type"),
        "tool_name": operation.get("tool_name"),
        "status": operation.get("status"),
        "preview": operation.get("preview"),
        "duration": operation.get("duration"),
        "is_error": bool(operation.get("is_error")),
    }


def _strip_private_fields(value: Any) -> Any:
    if isinstance(value, list):
        return [_strip_private_fields(item) for item in value]
    if isinstance(value, dict):
        return {key: _strip_private_fields(item) for key, item in value.items() if not key.startswith("_")}
    return value


def _safe_metadata(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    safe: dict[str, str] = {}
    for key, value in raw.items():
        safe_key = _safe_text(key, key="metadata_key", max_len=160)
        if safe_key:
            safe[safe_key] = sanitize_value_for_progress(value, key=str(key), max_len=500)
    return safe


def _safe_status_filter(status: str | None) -> str:
    normalized = _safe_text(status or "all", key="status", max_len=80).lower()
    return normalized if normalized in {"running", "completed", "failed", "all"} else "all"


def _safe_limit(value: Any, default: int) -> int:
    try:
        limit = int(value)
    except Exception:
        return default
    return max(1, min(limit, 1000))


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_nonnegative_int(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except Exception:
        return 0
    return max(0, number)


def _safe_optional_text(value: Any, *, key: str, max_len: int) -> str | None:
    if value is None:
        return None
    return _safe_text(value, key=key, max_len=max_len)


def _safe_text(value: Any, *, key: str, max_len: int) -> str:
    if value is None:
        return ""
    return sanitize_value_for_progress(value, key=key, max_len=max_len)


def _safe_optional_number(value: Any) -> int | float | None:
    if value is None:
        return None
    return _safe_number(value)


def _safe_number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return value
    try:
        parsed = float(value)
    except Exception:
        return None
    return parsed if math.isfinite(parsed) else None


def _first_number(*values: Any) -> int | float | None:
    for value in values:
        if value is not None:
            return value
    return None


def _sort_value(value: Any) -> float:
    number = _safe_number(value)
    return float(number) if number is not None else 0.0
