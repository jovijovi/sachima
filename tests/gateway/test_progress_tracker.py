"""Tests for pure in-memory gateway progress tracking."""

import threading
from dataclasses import is_dataclass

from gateway.progress.events import ProgressOperation, TodoItemSnapshot, TransactionSnapshot
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
    assert snapshot.model_display is None
    assert snapshot.account_limit_lines == ()
    assert snapshot.todo_items == ()
    assert isinstance(tracker._lock, type(threading.Lock()))


def test_update_display_metadata_sanitizes_model_and_account_limit_lines():
    tracker = ProgressTracker("tx-1", "Metadata display")
    unsafe_key = "api_" + "key"
    unsafe_value = "sk-" + "synthetic"
    unsafe_token_param = "to" + "ken"
    unsafe_secret_value = "sec" + "ret"

    tracker.update_display_metadata(
        model_display=(
            "openrouter/anthropic/claude-sonnet-4.6-20260514 (2025-04-14) "
            f"knowledge cutoff: 2026-01-01 {unsafe_key}={unsafe_value}"
        ),
        account_limit_lines=[
            "📈 **Account limits**",
            "Provider: openrouter",
            "Session: 74% remaining (26% used)",
            f"https://billing.example.invalid/account?{unsafe_token_param}={unsafe_secret_value}",
            f"{unsafe_key}={unsafe_value}",
        ],
    )

    snapshot = tracker.snapshot()

    assert snapshot.model_display == "openrouter/anthropic/claude-sonnet-4.6"
    assert snapshot.account_limit_lines == (
        "Provider: openrouter",
        "Session: 74% remaining (26% used)",
    )
    rendered = repr(snapshot)
    assert "20260514" not in rendered
    assert "2026-01-01" not in rendered
    assert unsafe_key not in rendered
    assert unsafe_value not in rendered
    assert "billing.example.invalid" not in rendered


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


def test_tracker_snapshot_defaults_iteration_usage_to_none():
    tracker = ProgressTracker("tx-rounds-none", "No rounds yet")

    assert tracker.snapshot().iteration_usage is None


def test_tracker_snapshot_carries_iteration_usage():
    tracker = ProgressTracker("tx-rounds", "Work rounds")

    tracker.update_iteration_usage(current_rounds=12, max_rounds=90)

    usage = tracker.snapshot().iteration_usage
    assert usage is not None
    assert usage.current == 12
    assert usage.maximum == 90


def test_tracker_iteration_usage_clamps_negative_and_bad_values():
    tracker = ProgressTracker("tx-rounds-bad", "Work rounds")

    tracker.update_iteration_usage(current_rounds=-5, max_rounds="bad")

    usage = tracker.snapshot().iteration_usage
    assert usage is not None
    assert usage.current == 0
    assert usage.maximum == 0


def test_tracker_iteration_usage_partial_update_preserves_previous_values():
    tracker = ProgressTracker("tx-rounds-partial", "Work rounds")

    tracker.update_iteration_usage(current_rounds=3, max_rounds=90)
    tracker.update_iteration_usage(current_rounds=7)

    usage = tracker.snapshot().iteration_usage
    assert usage is not None
    assert usage.current == 7
    assert usage.maximum == 90


def test_update_todo_items_carries_flat_list():
    tracker = ProgressTracker("tx-todo-flat", "Flat todos")

    returned = tracker.update_todo_items([
        {"id": "1", "content": "Prepare plan", "status": "completed"},
        {"id": "2", "content": "Run tests", "status": "in_progress"},
        {"id": "3", "content": "Submit PR", "status": "pending"},
    ])

    items = tracker.snapshot().todo_items
    assert returned == items
    assert all(isinstance(it, TodoItemSnapshot) for it in items)
    assert [it.content for it in items] == ["Prepare plan", "Run tests", "Submit PR"]
    assert [it.status for it in items] == ["completed", "in_progress", "pending"]
    assert all(it.depth == 0 and it.parent_id is None for it in items)
    assert all(it.source == "todo_tool" for it in items)


def test_update_todo_items_carries_two_level_grouping():
    tracker = ProgressTracker("tx-todo-2level", "Grouped todos")

    tracker.update_todo_items([
        {"id": "pr", "content": "PR verification", "status": "in_progress"},
        {"id": "local", "content": "Local tests", "status": "completed", "parent_id": "pr"},
        {"id": "codex", "content": "Codex review", "status": "pending", "parent_id": "pr"},
        {"id": "ship", "content": "Ship", "status": "pending"},
    ])

    items = {it.id: it for it in tracker.snapshot().todo_items}
    assert items["pr"].depth == 0 and items["pr"].parent_id is None
    assert items["local"].depth == 1 and items["local"].parent_id == "pr"
    assert items["codex"].depth == 1 and items["codex"].parent_id == "pr"
    assert items["ship"].depth == 0 and items["ship"].parent_id is None


def test_update_todo_items_clamps_depth_to_one_for_deep_chains():
    tracker = ProgressTracker("tx-todo-deep", "Deep chain")

    tracker.update_todo_items([
        {"id": "a", "content": "Root", "status": "pending"},
        {"id": "b", "content": "Child", "status": "pending", "parent_id": "a"},
        {"id": "c", "content": "Grandchild", "status": "pending", "parent_id": "b"},
    ])

    items = tracker.snapshot().todo_items
    assert max(it.depth for it in items) == 1  # never depth 2, even for a 3-deep chain
    by_id = {it.id: it for it in items}
    assert by_id["b"].parent_id == "a"
    # c originally pointed to b, but b is already a child. Persisted/API todo
    # parent links must point only at top-level items, so c falls back to top level.
    assert by_id["c"].depth == 0
    assert by_id["c"].parent_id is None


def test_update_todo_items_sanitizes_secret_shaped_fields():
    tracker = ProgressTracker("tx-todo-secret", "Secret todos")
    leak = "leak-" + "value"

    tracker.update_todo_items(
        [
            {
                "id": "api_key=" + leak,
                "content": "Authorization: Bearer " + leak,
                "status": "in_progress",
                "parent_id": "token=" + leak,
                "source": "password=" + leak,
            }
        ],
    )

    snapshot = tracker.snapshot()
    rendered = repr(snapshot)
    assert leak not in rendered
    assert "[REDACTED]" in rendered


def test_update_todo_items_preserves_local_paths_without_independent_secrets():
    tracker = ProgressTracker("tx-todo-path", "Path todos")

    tracker.update_todo_items(
        [
            {
                "id": "/tmp/private_dump.py",
                "content": "Inspect /home/ecs-user/.hermes/config.yaml before /data/agents/private.json",
                "status": "pending",
                # Unknown parents are still pruned, independent of path policy.
                "parent_id": "/home/ecs-user/parent-id",
                "source": "~/workspace/private-source.md",
            }
        ],
    )

    rendered = repr(tracker.snapshot())
    assert "/tmp/private_dump.py" in rendered
    assert "/home/ecs-user/.hermes/config.yaml" in rendered
    assert "/data/agents/private.json" in rendered
    assert "~/workspace/private-source.md" in rendered
    assert "[REDACTED]" not in rendered


def test_update_todo_items_caps_count_and_text_length():
    from gateway.progress.tracker import MAX_TODO_CONTENT_CHARS, MAX_TODO_ITEMS

    tracker = ProgressTracker("tx-todo-caps", "Capped todos")
    tracker.update_todo_items(
        [{"id": str(i), "content": "x" * 500, "status": "pending"} for i in range(MAX_TODO_ITEMS + 25)]
    )

    items = tracker.snapshot().todo_items
    assert len(items) == MAX_TODO_ITEMS
    assert all(len(it.content) <= MAX_TODO_CONTENT_CHARS for it in items)


def test_update_todo_items_coerces_unknown_status_to_pending_and_survives_bad_shapes():
    tracker = ProgressTracker("tx-todo-bad", "Bad shapes")

    tracker.update_todo_items([
        {"id": "1", "content": "Known", "status": "weird-status"},
        "not-a-dict",
        None,
        {"id": "2", "content": "", "status": "completed"},
    ])

    items = tracker.snapshot().todo_items
    by_id = {it.id: it for it in items}
    assert by_id["1"].status == "pending"  # unknown status falls back to pending
    assert by_id["2"].content == "(no description)"
    # The non-dict / None entries are dropped, not fatal.
    assert set(by_id) == {"1", "2"}


def test_update_todo_items_empty_resets_to_tuple():
    tracker = ProgressTracker("tx-todo-empty", "Empty todos")
    tracker.update_todo_items([{"id": "1", "content": "x", "status": "pending"}])

    assert tracker.update_todo_items([]) == ()
    assert tracker.snapshot().todo_items == ()
