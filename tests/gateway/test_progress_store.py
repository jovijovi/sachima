"""Tests for append-only gateway progress event persistence."""

import json
import threading
import time
from pathlib import Path

from gateway.progress.events import ProgressOperation, TransactionSnapshot
from gateway.progress.store import (
    JsonlProgressEventStore,
    build_progress_event_store,
    default_progress_events_path,
    progress_operation_to_record,
    progress_snapshot_to_record,
)
from gateway.progress.tracker import ProgressTracker


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_jsonl_store_appends_transaction_operation_records(tmp_path):
    store_path = tmp_path / "nested" / "events.jsonl"
    store = JsonlProgressEventStore(store_path)
    tracker = ProgressTracker("tx-1", "Persist progress")

    first = tracker.record_callback_event("tool.started", tool_name="terminal", preview="pytest")
    second = tracker.record_callback_event("tool.completed", tool_name="terminal", duration=1.25)

    store.append_operation(tracker.snapshot(), first)
    store.append_operation(tracker.snapshot(), second)

    records = _read_jsonl(store_path)
    assert len(records) == 2
    assert records[0]["transaction"]["id"] == "tx-1"
    assert records[0]["transaction"]["title"] == "Persist progress"
    assert records[0]["operation"]["event_type"] == "tool.started"
    assert records[0]["operation"]["tool_name"] == "terminal"
    assert records[0]["operation"]["preview"] == "pytest"
    assert records[1]["operation"]["event_type"] == "tool.completed"
    assert records[1]["operation"]["duration"] == 1.25


def test_jsonl_store_appends_final_transaction_snapshot_record(tmp_path):
    store_path = tmp_path / "events.jsonl"
    store = JsonlProgressEventStore(store_path)
    tracker = ProgressTracker("tx-final", "Persist final state")
    tracker.record_callback_event("tool.started", tool_name="terminal", preview="pytest")
    tracker.mark_completed(is_error=False)

    store.append_snapshot(tracker.snapshot())

    records = _read_jsonl(store_path)
    assert records == [
        {
            "schema_version": 1,
            "record_type": "progress.snapshot",
            "transaction": records[0]["transaction"],
            "written_at": records[0]["written_at"],
        }
    ]
    assert records[0]["transaction"]["id"] == "tx-final"
    assert records[0]["transaction"]["status"] == "completed"
    assert records[0]["transaction"]["completed_at"] is not None


def test_progress_records_include_sanitized_context_usage(tmp_path):
    store_path = tmp_path / "events.jsonl"
    store = JsonlProgressEventStore(store_path)
    tracker = ProgressTracker("tx-context", "Persist context usage")
    tracker.update_context_usage(
        current_tokens=40_960,
        context_window=128_000,
        peak_tokens=65_536,
        compression_count=2,
        threshold_tokens=102_400,
    )

    store.append_snapshot(tracker.snapshot())

    record = _read_jsonl(store_path)[0]
    assert record["transaction"]["context_usage"] == {
        "current_tokens": 40_960,
        "context_window": 128_000,
        "peak_tokens": 65_536,
        "compression_count": 2,
        "threshold_tokens": 102_400,
    }


def test_jsonl_store_serializes_concurrent_writes(monkeypatch, tmp_path):
    store_path = tmp_path / "events.jsonl"
    store = JsonlProgressEventStore(store_path)
    snapshot = TransactionSnapshot(
        transaction_id="tx-concurrent",
        title="Concurrent progress",
        status="running",
        started_at=1.0,
        updated_at=2.0,
    )
    operation = ProgressOperation(
        id="op-concurrent",
        event_type="tool.started",
        tool_name="terminal",
        status="running",
        preview="x" * 1000,
        started_at=1.0,
        updated_at=2.0,
    )
    active_writers = 0
    max_active_writers = 0
    write_lock = threading.Lock()
    start = threading.Barrier(8)

    class SlowHandle:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def write(self, chunk):
            nonlocal active_writers, max_active_writers
            with write_lock:
                active_writers += 1
                max_active_writers = max(max_active_writers, active_writers)
            time.sleep(0.01)
            with write_lock:
                active_writers -= 1
            return len(chunk)

    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: SlowHandle())

    def append_one():
        start.wait(timeout=2)
        store.append_operation(snapshot, operation)

    threads = [threading.Thread(target=append_one) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive()

    assert max_active_writers == 1


def test_jsonl_store_serializes_concurrent_writes_across_instances(monkeypatch, tmp_path):
    store_path = tmp_path / "events.jsonl"
    stores = [JsonlProgressEventStore(store_path) for _ in range(8)]
    snapshot = TransactionSnapshot(
        transaction_id="tx-cross-instance",
        title="Concurrent progress",
        status="running",
        started_at=1.0,
        updated_at=2.0,
    )
    operation = ProgressOperation(
        id="op-cross-instance",
        event_type="tool.started",
        tool_name="terminal",
        status="running",
        preview="x" * 1000,
        started_at=1.0,
        updated_at=2.0,
    )
    active_writers = 0
    max_active_writers = 0
    write_lock = threading.Lock()
    start = threading.Barrier(len(stores))

    class SlowHandle:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def write(self, chunk):
            nonlocal active_writers, max_active_writers
            with write_lock:
                active_writers += 1
                max_active_writers = max(max_active_writers, active_writers)
            time.sleep(0.01)
            with write_lock:
                active_writers -= 1
            return len(chunk)

    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: SlowHandle())

    def append_one(store):
        start.wait(timeout=2)
        store.append_operation(snapshot, operation)

    threads = [threading.Thread(target=append_one, args=(store,)) for store in stores]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive()

    assert max_active_writers == 1


def test_progress_operation_to_record_sanitizes_again_at_serialization_boundary():
    sensitive_value = "store-" + "secret"
    snapshot = TransactionSnapshot(
        transaction_id="tx-2",
        title="Authorization: Bearer " + sensitive_value,
        status="running",
        started_at=1.0,
        updated_at=2.0,
    )
    operation = ProgressOperation(
        id="op-1",
        event_type="tool.started",
        tool_name="X-API-Key: " + sensitive_value,
        status="running",
        preview="curl https://example.invalid/?access_token=" + sensitive_value + "&ok=yes",
        args_preview='{"password": "' + sensitive_value + '"}',
        started_at=1.0,
        updated_at=2.0,
        metadata={"api_key": sensitive_value, "safe": "visible"},
    )

    record = progress_operation_to_record(snapshot, operation)
    rendered = json.dumps(record, ensure_ascii=False)

    assert sensitive_value not in rendered
    assert "[REDACTED]" in rendered
    assert "ok=yes" in rendered
    assert record["operation"]["metadata"]["safe"] == "visible"


def test_build_progress_event_store_is_disabled_by_default(tmp_path):
    assert build_progress_event_store({}) is None
    assert build_progress_event_store({"persist_events": False, "event_store_path": str(tmp_path / "events.jsonl")}) is None
    assert build_progress_event_store({"persist_events": True, "event_store": "sqlite"}) is None


def test_build_progress_event_store_uses_explicit_jsonl_path(tmp_path):
    path = tmp_path / "events.jsonl"

    store = build_progress_event_store(
        {"persist_events": True, "event_store": "jsonl", "event_store_path": str(path)}
    )

    assert isinstance(store, JsonlProgressEventStore)
    assert store.path == path


def test_default_progress_events_path_uses_hermes_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    assert default_progress_events_path() == tmp_path / "progress" / "events.jsonl"
