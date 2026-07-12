"""Tests for gateway transaction progress text rendering."""

import json

from gateway.progress.tracker import ProgressTracker


def test_text_renderer_includes_transaction_status_and_tools():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-1")
    tracker.record_tool_started("read_file", "gateway/run.py", {"path": "gateway/run.py"})

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="all")

    assert "📌" in text
    assert "tx-1" in text
    assert "Running" in text
    assert "Recent operations" in text
    assert "read_file" in text
    assert "gateway/run.py" in text


def test_text_renderer_hides_tools_when_progress_off():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-1")
    tracker.record_tool_started("terminal", "pytest", {"command": "pytest"})

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="off")

    assert "tx-1" in text
    assert "terminal" not in text
    assert "pytest" not in text


def test_text_renderer_marks_failed_and_completed_operations():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-1")
    tracker.record_tool_started("terminal", "pytest")
    tracker.record_tool_completed("terminal", duration=1.2, is_error=True)

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="all")

    assert "❌" in text
    assert "terminal" in text
    assert "1.20s" in text


def test_text_renderer_respects_new_mode_by_collapsing_repeated_tools():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-1")
    tracker.record_tool_started("read_file", "a.py")
    tracker.record_tool_started("read_file", "b.py")
    tracker.record_tool_started("search_files", "pattern")

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="new")

    assert text.count("read_file") == 1
    assert "search_files" in text


def test_text_renderer_sanitizes_and_caps_output():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-1")
    tracker.record_tool_started(
        "terminal",
        "curl https://example.invalid/?token=abc123&debug=true",
        {"api_key": "secret-value", "command": "x" * 400},
    )

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="verbose", max_length=220)

    assert len(text) <= 220
    assert "abc123" not in text
    assert "secret-value" not in text
    assert "[REDACTED]" in text


def test_text_renderer_handles_empty_operations():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-1")

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="all")

    assert "No operations yet" in text


def test_text_renderer_includes_safe_dashboard_progress_link_when_configured():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-1")

    text = render_text_panel(
        tracker.snapshot(),
        dashboard_url="https://dashboard.example.local:9119/base?session_token=***#secret",
    )

    assert "Dashboard" in text
    assert "https://dashboard.example.local:9119/base/progress" in text
    assert "session_token" not in text
    assert "abc123" not in text


def test_text_renderer_includes_context_usage_summary():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-context")
    tracker.update_context_usage(
        current_tokens=40_960,
        context_window=128_000,
        peak_tokens=65_536,
        compression_count=2,
    )

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="off")

    assert "Context" in text
    assert "40,960 / 128,000" in text
    assert "32.0%" in text
    assert "peak 65,536" in text
    assert "compressions 2" in text


def test_text_renderer_does_not_show_zero_ratio_for_partial_context_usage():
    from gateway.progress.renderers import render_text_panel

    peak_tracker = ProgressTracker(transaction_id="tx-peak-only")
    peak_tracker.update_context_usage(current_tokens=0, context_window=128_000, peak_tokens=65_536)
    compression_tracker = ProgressTracker(transaction_id="tx-compress-only")
    compression_tracker.update_context_usage(current_tokens=0, context_window=128_000, compression_count=2)

    peak_text = render_text_panel(peak_tracker.snapshot(), tool_progress_mode="off")
    compression_text = render_text_panel(compression_tracker.snapshot(), tool_progress_mode="off")

    assert "peak 65,536" in peak_text
    assert "compressions 2" in compression_text
    assert "0 / 128,000" not in peak_text
    assert "0 / 128,000" not in compression_text


def test_text_renderer_includes_work_rounds_when_present():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-rounds")
    tracker.update_iteration_usage(current_rounds=12, max_rounds=90)

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="off")

    assert "Rounds" in text
    assert "12 / 90" in text


def test_text_renderer_omits_work_rounds_without_meaningful_max():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-rounds-empty")
    tracker.update_iteration_usage(current_rounds=0, max_rounds=0)

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="off")

    assert "Rounds" not in text
    assert "0 / 0" not in text


def test_text_renderer_omits_unsafe_dashboard_link():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-1")

    text = render_text_panel(tracker.snapshot(), dashboard_url="javascript:alert('x')")

    assert "Dashboard" not in text
    assert "javascript:" not in text


def test_text_renderer_omits_dashboard_link_when_port_is_invalid():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-1")

    for dashboard_url in ("http://example.local:bad", "http://example.local:99999"):
        text = render_text_panel(tracker.snapshot(), dashboard_url=dashboard_url)

        assert "Dashboard" not in text
        assert dashboard_url not in text


def test_text_renderer_preserves_ipv6_dashboard_host_brackets():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-1")

    text = render_text_panel(tracker.snapshot(), dashboard_url="http://[::1]:9119/base")

    assert "Dashboard" in text
    assert "http://[::1]:9119/base/progress" in text


def test_text_renderer_renders_flat_todo_section_before_recent_operations():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-todo")
    tracker.record_tool_started("read_file", "a.py")
    tracker.update_todo_items([
        {"id": "1", "content": "Prepare plan", "status": "completed"},
        {"id": "2", "content": "Run tests", "status": "in_progress"},
        {"id": "3", "content": "Submit PR", "status": "pending"},
    ])

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="all")

    assert "To-dos" in text
    assert "Prepare plan" in text
    assert "Run tests" in text
    assert "Submit PR" in text
    # Completed items are struck through.
    assert "~~Prepare plan~~" in text
    # The todo block sits before the recent-operations section.
    assert text.index("To-dos") < text.index("Recent operations")


def test_text_renderer_omits_todo_section_when_empty():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-no-todo")

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="off")

    assert "To-dos" not in text


def test_text_renderer_renders_two_level_todo_grouping_without_infinite_tree():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-todo-2")
    tracker.update_todo_items([
        {"id": "pr", "content": "PR verification", "status": "in_progress"},
        {"id": "local", "content": "Local tests", "status": "completed", "parent_id": "pr"},
        {"id": "codex", "content": "Codex review", "status": "pending", "parent_id": "pr"},
        {"id": "deep", "content": "Too deep", "status": "pending", "parent_id": "local"},
    ])

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="off")

    # Group header carries a done/total over its direct children only.
    assert "▸ PR verification 1/2" in text
    lines = text.splitlines()
    child_lines = [ln for ln in lines if "Local tests" in ln or "Codex review" in ln]
    assert child_lines and all(ln.startswith("    -") for ln in child_lines)
    # A third-level item is clamped — it never renders deeper than one indent.
    assert "        -" not in text


def test_text_renderer_renders_executor_badge_before_content():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-todo-executor")
    tracker.update_todo_items([
        {"id": "pr", "content": "PR verification", "status": "in_progress", "executor": "claude"},
        {"id": "local", "content": "Local tests", "status": "completed", "parent_id": "pr", "executor": "codex"},
        {"id": "ci", "content": "CI wait", "status": "pending", "parent_id": "pr"},
        {"id": "run", "content": "Run tests", "status": "in_progress", "executor": "codex"},
        {"id": "ship", "content": "Ship", "status": "pending"},
    ])

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="off")

    # Badge sits between the status icon and the content; the badge stays
    # outside the strikethrough on completed items.
    assert "- ▶️ [codex] Run tests" in text
    assert "▸ [claude] PR verification 1/2" in text
    assert "    - ✅ [codex] ~~Local tests~~" in text
    # Unlabeled items render with no badge.
    assert "- ⏳ Ship" in text
    assert "    - ⏳ CI wait" in text
    # The legacy trailing ` · executor` suffix shape is gone.
    assert "· codex" not in text
    assert "· claude" not in text


def test_text_renderer_displays_hermes_agent_executor_as_hermes():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-todo-executor-alias")
    tracker.update_todo_items([
        {"id": "1", "content": "Check workbench display", "status": "in_progress", "executor": "hermes-agent"},
    ])

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="off")

    assert "- ▶️ [hermes] Check workbench display" in text
    assert "hermes-agent" not in text


def test_text_renderer_cancelled_todo_uses_forbidden_icon_without_strikethrough():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-todo-cancelled")
    tracker.update_todo_items([
        {"id": "1", "content": "Legacy suffix plan", "status": "cancelled", "executor": "other"},
        {"id": "2", "content": "Badge plan", "status": "in_progress"},
    ])

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="off")

    assert "- 🚫 [other] Legacy suffix plan" in text
    assert "~~Legacy suffix plan~~" not in text


def test_text_renderer_renders_failed_todo_icon_defensively():
    # Persistent todo statuses cannot produce ``failed`` today; the renderer
    # still maps it in case an upstream workbench source supplies one.
    from gateway.progress.events import TodoItemSnapshot, TransactionSnapshot
    from gateway.progress.renderers import render_text_panel

    snapshot = TransactionSnapshot(
        transaction_id="tx-todo-failed",
        status="running",
        started_at=1.0,
        updated_at=2.0,
        todo_items=(
            TodoItemSnapshot(id="1", content="Fix failed: chain unverified", status="failed", executor="claude"),
        ),
    )

    text = render_text_panel(snapshot, tool_progress_mode="off")

    assert "- ❌ [claude] Fix failed: chain unverified" in text
    assert "~~Fix failed: chain unverified~~" not in text


def test_text_renderer_never_renders_secret_shaped_executor():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-todo-executor-secret")
    bare_key = "sk-" + "test-" + ("h" * 32)
    tracker.update_todo_items([
        {"id": "1", "content": "Run tests", "status": "in_progress", "executor": bare_key},
    ])

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="off")

    assert bare_key not in text
    assert "- ▶️ Run tests" in text
    assert "] Run tests" not in text


def test_feishu_renders_suspended_hint_separately_from_main_todos():
    from gateway.progress.renderers import render_text_panel
    from gateway.progress.todo_lifecycle import make_owner_scope_ref

    owner = make_owner_scope_ref(
        profile="default",
        platform="feishu",
        conversation_id="raw-chat-id-a",
        user_id="raw-user-id-a",
    )
    fake_key = "sk-" + "test-" + ("c" * 32)
    tracker = ProgressTracker(transaction_id="tx-suspended")
    tracker.update_todo_items([
        {"id": "old", "content": f"Old task using {fake_key}", "status": "pending"},
    ])
    tracker.update_todo_lifecycle(
        {
            "state": "suspended",
            "suspension_reason": "waiting_external",
            "remaining_count": 1,
            "owner_scope_ref": owner,
        }
    )
    tracker.update_suspended_todo_hint(
        {
            "transaction_id": "tx-suspended",
            "title": "Wait for CI at /data/agents/workspace/report.md",
            "reason": "waiting_external",
            "remaining_count": 1,
            "next_action": "continue previous task via /api/progress",
            "owner_scope_ref": owner,
        }
    )

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="off")

    assert "To-dos" not in text
    assert "Old task" not in text
    assert "Suspended work" in text
    assert "Wait for CI" in text
    assert "/data/agents/workspace/report.md" in text
    assert "/api/progress" in text
    assert fake_key not in text


def test_text_renderer_shows_canonical_transaction_id():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="sess-text-task-id")

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="off")

    assert "**Transaction:** sess-text-task-id" in text
