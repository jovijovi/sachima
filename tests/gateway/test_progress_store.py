"""Tests for append-only gateway progress event persistence."""

import json
import threading
import time
from pathlib import Path

from gateway.progress.events import ProgressOperation, TodoItemSnapshot, TransactionSnapshot
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


def test_progress_records_include_sanitized_iteration_usage(tmp_path):
    store_path = tmp_path / "events.jsonl"
    store = JsonlProgressEventStore(store_path)
    tracker = ProgressTracker("tx-rounds", "Persist iteration usage")
    tracker.update_iteration_usage(current_rounds=12, max_rounds=90)

    store.append_snapshot(tracker.snapshot())

    record = _read_jsonl(store_path)[0]
    assert record["transaction"]["iteration_usage"] == {"current": 12, "maximum": 90}


def test_progress_records_include_sanitized_todo_items(tmp_path):
    store_path = tmp_path / "events.jsonl"
    store = JsonlProgressEventStore(store_path)
    tracker = ProgressTracker("tx-todo", "Persist todo items")
    tracker.update_todo_items([
        {"id": "pr", "content": "PR verification", "status": "in_progress"},
        {"id": "local", "content": "Local tests", "status": "completed", "parent_id": "pr"},
    ])

    store.append_snapshot(tracker.snapshot())

    record = _read_jsonl(store_path)[0]
    todo_items = record["transaction"]["todo_items"]
    assert todo_items == [
        {"id": "pr", "content": "PR verification", "status": "in_progress", "depth": 0, "source": "todo_tool"},
        {
            "id": "local",
            "content": "Local tests",
            "status": "completed",
            "depth": 1,
            "source": "todo_tool",
            "parent_id": "pr",
        },
    ]


def test_progress_records_redact_secret_shaped_todo_items(tmp_path):
    store_path = tmp_path / "events.jsonl"
    store = JsonlProgressEventStore(store_path)
    leak = "store-todo-" + "secret"
    snapshot = TransactionSnapshot(
        transaction_id="tx-todo-secret",
        title="Persist secret todo",
        status="running",
        started_at=1.0,
        updated_at=2.0,
        todo_items=(
            TodoItemSnapshot(
                id="1",
                content="Auth" "orization: " + "Bearer " + leak,
                status="pending",
                source="token=" + leak,
            ),
        ),
    )

    store.append_snapshot(snapshot)

    rendered = store_path.read_text(encoding="utf-8")
    assert leak not in rendered
    assert "[REDACTED]" in rendered


def test_progress_records_redact_bare_provider_key_shapes_in_todo_items(tmp_path):
    store_path = tmp_path / "events.jsonl"
    store = JsonlProgressEventStore(store_path)
    bare_key = "sk-" + "test-" + ("a" * 32)
    route = "/health"
    path = "/data/agents/workspace/config.yaml"
    snapshot = TransactionSnapshot(
        transaction_id="tx-todo-bare-secret",
        title="Persist bare secret todo",
        status="running",
        started_at=1.0,
        updated_at=2.0,
        todo_items=(
            TodoItemSnapshot(
                id="1",
                content=f"Implement {route} with {bare_key}; inspect {path}",
                status="pending",
            ),
        ),
    )

    store.append_snapshot(snapshot)

    rendered = store_path.read_text(encoding="utf-8")
    assert bare_key not in rendered
    assert route in rendered
    assert path in rendered
    assert "[REDACTED]" in rendered



def test_progress_records_preserve_local_paths_in_todo_items(tmp_path):
    store_path = tmp_path / "events.jsonl"
    store = JsonlProgressEventStore(store_path)
    snapshot = TransactionSnapshot(
        transaction_id="tx-todo-path",
        title="Persist path todo",
        status="running",
        started_at=1.0,
        updated_at=2.0,
        todo_items=(
            TodoItemSnapshot(
                id="/tmp/private_dump.py",
                content="Inspect /home/ecs-user/.hermes/config.yaml and /data/agents/private.json",
                status="pending",
                source="~/workspace/private-source.md",
            ),
        ),
    )

    store.append_snapshot(snapshot)

    rendered = store_path.read_text(encoding="utf-8")
    assert "/tmp/private_dump.py" in rendered
    assert "/home/ecs-user/.hermes/config.yaml" in rendered
    assert "/data/agents/private.json" in rendered
    assert "~/workspace/private-source.md" in rendered
    assert "[REDACTED]" not in rendered


def test_progress_records_normalize_todo_parent_links_to_top_level(tmp_path):
    store_path = tmp_path / "events.jsonl"
    store = JsonlProgressEventStore(store_path)
    snapshot = TransactionSnapshot(
        transaction_id="tx-todo-deep",
        title="Persist deep todo",
        status="running",
        started_at=1.0,
        updated_at=2.0,
        todo_items=(
            TodoItemSnapshot(id="a", content="Root", status="pending"),
            TodoItemSnapshot(id="b", content="Child", status="pending", parent_id="a", depth=1),
            TodoItemSnapshot(id="c", content="Grandchild", status="pending", parent_id="b", depth=1),
        ),
    )

    store.append_snapshot(snapshot)

    todo_items = _read_jsonl(store_path)[0]["transaction"]["todo_items"]
    by_id = {item["id"]: item for item in todo_items}
    assert by_id["b"]["parent_id"] == "a"
    assert by_id["b"]["depth"] == 1
    assert "parent_id" not in by_id["c"]
    assert by_id["c"]["depth"] == 0


def test_progress_records_include_empty_todo_items_to_clear_stale_state(tmp_path):
    store_path = tmp_path / "events.jsonl"
    store = JsonlProgressEventStore(store_path)
    tracker = ProgressTracker("tx-no-todo", "No todos")

    store.append_snapshot(tracker.snapshot())

    record = _read_jsonl(store_path)[0]
    assert record["transaction"]["todo_items"] == []


def test_progress_records_include_todo_lifecycle_and_hint(tmp_path):
    from gateway.progress.todo_lifecycle import make_owner_scope_ref

    store_path = tmp_path / "events.jsonl"
    store = JsonlProgressEventStore(store_path)
    tracker = ProgressTracker("tx-lifecycle", "Persist lifecycle")
    owner = make_owner_scope_ref(
        profile="default",
        platform="feishu",
        conversation_id="raw-chat-id-a",
        user_id="raw-user-id-a",
    )
    fake_key = "sk-" + "test-" + ("b" * 32)
    tracker.update_todo_lifecycle(
        {
            "state": "suspended",
            "suspension_reason": "waiting_external",
            "completed_count": 3,
            "remaining_count": 1,
            "next_action": f"Check /api/progress without leaking {fake_key}",
            "owner_scope_ref": owner,
        }
    )
    tracker.update_suspended_todo_hint(
        {
            "transaction_id": "tx-lifecycle",
            "title": "Wait for CI",
            "reason": "waiting_external",
            "remaining_count": 1,
            "next_action": "continue previous task",
            "owner_scope_ref": owner,
        }
    )

    store.append_snapshot(tracker.snapshot())
    record = _read_jsonl(store_path)[0]
    transaction = record["transaction"]
    assert transaction["todo_lifecycle"]["state"] == "suspended"
    assert transaction["todo_lifecycle"]["suspension_reason"] == "waiting_external"
    assert transaction["todo_lifecycle"]["completed_count"] == 3
    assert transaction["todo_lifecycle"]["remaining_count"] == 1
    assert transaction["todo_lifecycle"]["owner_scope_ref"] == {
        "profile": owner.profile,
        "platform": owner.platform,
        "conversation": owner.conversation,
        "user": owner.user,
    }
    assert transaction["suspended_todo_hint"]["transaction_id"] == "tx-lifecycle"
    rendered = json.dumps(record, ensure_ascii=False)
    assert "/api/progress" in rendered
    assert fake_key not in rendered
    assert "raw-chat-id-a" not in rendered
    assert "raw-user-id-a" not in rendered


def test_progress_records_include_null_lifecycle_and_hint_to_clear_stale_state(tmp_path):
    from gateway.progress.todo_lifecycle import make_owner_scope_ref

    store_path = tmp_path / "events.jsonl"
    store = JsonlProgressEventStore(store_path)
    owner = make_owner_scope_ref(
        profile="default",
        platform="feishu",
        conversation_id="raw-chat-id-a",
        user_id="raw-user-id-a",
    )
    tracker = ProgressTracker("tx-lifecycle-clear", "Clear lifecycle")
    tracker.update_todo_lifecycle({"state": "suspended", "owner_scope_ref": owner})
    tracker.update_suspended_todo_hint(
        {
            "transaction_id": "tx-lifecycle-clear",
            "title": "Old hint",
            "reason": "paused",
            "remaining_count": 1,
            "owner_scope_ref": owner,
        }
    )
    store.append_snapshot(tracker.snapshot())
    tracker.update_todo_lifecycle(None)
    tracker.update_suspended_todo_hint(None)

    store.append_snapshot(tracker.snapshot())

    transaction = _read_jsonl(store_path)[-1]["transaction"]
    assert "todo_lifecycle" in transaction
    assert "suspended_todo_hint" in transaction
    assert transaction["todo_lifecycle"] is None
    assert transaction["suspended_todo_hint"] is None


def _rotation_snapshot() -> TransactionSnapshot:

    return TransactionSnapshot(
        transaction_id="tx-rotate",
        title="Rotate progress",
        status="running",
        started_at=1.0,
        updated_at=2.0,
    )


def _rotation_operation() -> ProgressOperation:
    # A 200-char preview guarantees each serialized record is far larger than the
    # tiny ``max_bytes`` the rotation tests use, so every append after the first
    # forces a rotation regardless of the exact record framing.
    return ProgressOperation(
        id="op-rotate",
        event_type="tool.started",
        tool_name="terminal",
        status="running",
        preview="x" * 200,
        started_at=1.0,
        updated_at=2.0,
    )


def test_jsonl_store_rotates_when_append_would_exceed_max_bytes(tmp_path):
    store_path = tmp_path / "events.jsonl"
    store = JsonlProgressEventStore(store_path, max_bytes=100, max_files=3)
    snapshot = _rotation_snapshot()
    operation = _rotation_operation()

    for _ in range(6):
        store.append_operation(snapshot, operation)

    # The live file is preserved for new writes and at least one archive exists.
    assert store_path.exists()
    assert (tmp_path / "events.jsonl.1").exists()
    # Rotation keeps the live file small: it must not still hold every record.
    assert len(_read_jsonl(store_path)) < 6


def test_jsonl_store_rotation_preserves_current_and_first_archive_and_caps_archives(tmp_path):
    store_path = tmp_path / "events.jsonl"
    store = JsonlProgressEventStore(store_path, max_bytes=100, max_files=2)
    snapshot = _rotation_snapshot()
    operation = _rotation_operation()

    for _ in range(12):
        store.append_operation(snapshot, operation)

    assert store_path.exists()
    assert (tmp_path / "events.jsonl.1").exists()
    assert (tmp_path / "events.jsonl.2").exists()
    # Never retain more numbered archives than ``max_files``.
    assert not (tmp_path / "events.jsonl.3").exists()


def test_jsonl_store_does_not_rotate_when_rotation_disabled(tmp_path):
    store_path = tmp_path / "events.jsonl"
    store = JsonlProgressEventStore(store_path, max_bytes=0)
    snapshot = _rotation_snapshot()
    operation = _rotation_operation()

    for _ in range(6):
        store.append_operation(snapshot, operation)

    assert not (tmp_path / "events.jsonl.1").exists()
    assert len(_read_jsonl(store_path)) == 6


def test_build_progress_event_store_accepts_rotation_options(tmp_path):
    path = tmp_path / "events.jsonl"

    store = build_progress_event_store(
        {
            "persist_events": True,
            "event_store": "jsonl",
            "event_store_path": str(path),
            "event_store_max_bytes": 1234,
            "event_store_max_files": 4,
        }
    )

    assert isinstance(store, JsonlProgressEventStore)
    assert store.max_bytes == 1234
    assert store.max_files == 4


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
