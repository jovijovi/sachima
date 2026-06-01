"""Tests for pure in-memory gateway progress tracking."""

import threading
from dataclasses import is_dataclass

from gateway.progress.events import ProgressOperation, TransactionSnapshot
from gateway.progress.tracker import ProgressTracker


def test_tracker_snapshot_is_transaction_dataclass_with_timestamps():
    tracker = ProgressTracker("tx-1", "Answer the user", max_operations=5)

    snapshot = tracker.snapshot()

    assert isinstance(snapshot, TransactionSnapshot)
    assert is_dataclass(snapshot)
    assert snapshot.transaction_id == "tx-1"
    assert snapshot.title == "Answer the user"
    assert snapshot.status == "running"
    assert snapshot.started_at > 0
    assert snapshot.updated_at >= snapshot.started_at
    assert snapshot.completed_at is None
    assert snapshot.recent_operations == ()
    assert isinstance(tracker._lock, type(threading.Lock()))


def test_record_tool_started_and_completed_sanitizes_operation_details():
    tracker = ProgressTracker("tx-1", "Run tests")

    tracker.record_tool_started(
        "terminal",
        preview="curl https://example.invalid/?token=query-secret&ok=yes",
        args={"command": "pytest", "api_key": "sk-secret-value"},
    )
    running_snapshot = tracker.snapshot()

    assert len(running_snapshot.recent_operations) == 1
    operation = running_snapshot.recent_operations[0]
    assert isinstance(operation, ProgressOperation)
    assert is_dataclass(operation)
    assert operation.tool_name == "terminal"
    assert operation.event_type == "tool.started"
    assert operation.status == "running"
    assert "ok=yes" in operation.preview
    assert "query-secret" not in operation.preview
    assert "sk-secret-value" not in operation.args_preview

    tracker.record_tool_completed("terminal", duration=1.25, is_error=False)
    completed = tracker.snapshot().recent_operations[0]

    assert completed.status == "completed"
    assert completed.duration == 1.25
    assert completed.is_error is False
    assert completed.completed_at is not None


def test_record_tool_completed_marks_most_recent_matching_running_operation():
    tracker = ProgressTracker("tx-1", "Multiple terminals")
    tracker.record_tool_started("terminal", preview="first")
    tracker.record_tool_started("browser", preview="middle")
    tracker.record_tool_started("terminal", preview="second")

    tracker.record_tool_completed("terminal", duration=0.5, is_error=True)

    first, browser, second = tracker.snapshot().recent_operations
    assert first.preview == "first"
    assert first.status == "running"
    assert browser.status == "running"
    assert second.preview == "second"
    assert second.status == "failed"
    assert second.is_error is True


def test_max_operations_trims_older_operations():
    tracker = ProgressTracker("tx-1", "Trim", max_operations=3)

    for index in range(5):
        tracker.record_tool_started(f"tool-{index}", preview=f"op-{index}")

    snapshot = tracker.snapshot()

    assert [op.tool_name for op in snapshot.recent_operations] == ["tool-2", "tool-3", "tool-4"]


def test_record_callback_event_handles_agent_and_subagent_events():
    tracker = ProgressTracker("tx-1", "Callbacks")

    tracker.record_callback_event("tool.started", tool_name="terminal", preview="pytest", args={"token": "secret-token"})
    tracker.record_callback_event("tool.completed", tool_name="terminal", duration=2.0, is_error=False)
    tracker.record_callback_event("subagent.start", preview="Investigate bug")
    tracker.record_callback_event("subagent.thinking", preview="I might use token=thinking-secret")
    tracker.record_callback_event("subagent.progress", preview="Read 2 files")
    tracker.record_callback_event("subagent_progress", preview="Nested child update")
    tracker.record_callback_event("subagent.tool", tool_name="search", preview="query", args={"password": "secret-password"})
    tracker.record_callback_event("subagent.complete", preview="Done")

    snapshot = tracker.snapshot()

    assert len(snapshot.recent_operations) == 7
    assert snapshot.recent_operations[0].status == "completed"
    assert snapshot.recent_operations[0].duration == 2.0
    assert [op.event_type for op in snapshot.recent_operations[1:]] == [
        "subagent.start",
        "subagent.thinking",
        "subagent.progress",
        "subagent.progress",
        "subagent.tool",
        "subagent.complete",
    ]
    assert snapshot.recent_operations[1].status == "running"
    assert snapshot.recent_operations[-1].status == "completed"
    rendered = repr(snapshot)
    assert "secret-token" not in rendered
    assert "thinking-secret" not in rendered
    assert "secret-password" not in rendered


def test_record_callback_event_accepts_legacy_positional_name_argument():
    tracker = ProgressTracker("tx-1", "Legacy callback")

    tracker.record_callback_event("tool.started", "terminal", "pwd", {"authorization": "Bearer legacy-secret"})

    operation = tracker.snapshot().recent_operations[0]
    assert operation.tool_name == "terminal"
    assert operation.preview == "pwd"
    assert "legacy-secret" not in operation.args_preview


def test_tool_name_is_sanitized_before_rendering():
    tracker = ProgressTracker("tx-1", "Tool name redaction")

    tracker.record_callback_event("subagent_progress", "Authorization: Basic tool-name-secret")

    operation = tracker.snapshot().recent_operations[0]
    assert "tool-name-secret" not in operation.tool_name
    assert "[REDACTED]" in operation.tool_name


def test_metadata_values_are_sanitized_with_their_keys():
    tracker = ProgressTracker("tx-1", "Metadata redaction")
    sensitive_value = "metadata-" + "secret"

    tracker.record_callback_event("subagent.progress", preview="ok", api_key=sensitive_value)

    operation = tracker.snapshot().recent_operations[0]
    assert operation.metadata["api_key"] == "[REDACTED]"
    assert sensitive_value not in repr(operation)


def test_tracker_snapshot_carries_context_usage_without_raw_metadata():
    tracker = ProgressTracker("tx-context", "Context pressure")

    tracker.update_context_usage(
        current_tokens=40_960,
        context_window=128_000,
        peak_tokens=65_536,
        compression_count=2,
        threshold_tokens=102_400,
    )

    usage = tracker.snapshot().context_usage
    assert usage is not None
    assert usage.current_tokens == 40_960
    assert usage.context_window == 128_000
    assert usage.peak_tokens == 65_536
    assert usage.compression_count == 2
    assert usage.threshold_tokens == 102_400


def test_tracker_context_usage_peak_is_monotonic_and_values_are_bounded():
    tracker = ProgressTracker("tx-context-bounds", "Context pressure")

    tracker.update_context_usage(current_tokens=50_000, context_window=128_000, compression_count=1)
    tracker.update_context_usage(current_tokens=-1, context_window="bad", peak_tokens=10, compression_count=-5)

    usage = tracker.snapshot().context_usage
    assert usage is not None
    assert usage.current_tokens == 0
    assert usage.context_window == 0
    assert usage.peak_tokens == 50_000
    assert usage.compression_count == 0
