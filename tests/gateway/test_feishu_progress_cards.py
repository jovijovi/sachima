"""Tests for pure Feishu progress card rendering."""

import json

import pytest

from gateway.progress.events import TransactionSnapshot
from gateway.progress.tracker import ProgressTracker


def _rendered(card: dict) -> str:
    return json.dumps(card, ensure_ascii=False, sort_keys=True)


def test_feishu_progress_card_running_shape_uses_safe_operation_labels():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-1", title="查一下三亚天气")
    tracker.record_tool_started(
        "terminal",
        "API_TOKEN=super-secret python3 /tmp/weather_query.py --location Sanya",
        {"command": "API_TOKEN=super-secret python3 /tmp/weather_query.py --location Sanya"},
        headers={"Authorization": "Bearer abc123"},
    )

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="all")
    rendered = _rendered(card)

    assert card["config"]["wide_screen_mode"] is True
    assert card["header"]["template"] == "blue"
    assert "小沙" in card["header"]["title"]["content"]
    assert "查一下三亚天气" in rendered
    assert "terminal" in rendered
    assert "weather_query.py" in rendered
    assert "--location" not in rendered
    assert "/tmp/" not in rendered
    assert "Sanya" not in rendered
    assert "API_TOKEN" not in rendered
    assert "super-secret" not in rendered
    assert "Authorization" not in rendered
    assert "abc123" not in rendered


@pytest.mark.parametrize(
    ("status", "expected_template"),
    [
        ("running", "blue"),
        ("pending", "blue"),
        ("completed", "green"),
        ("failed", "red"),
        ("cancelled", "grey"),
    ],
)
def test_feishu_progress_card_header_template_by_status(status, expected_template):
    from gateway.progress.renderers import render_feishu_progress_card

    snapshot = TransactionSnapshot(
        transaction_id="tx-status",
        title="Status task",
        status=status,
        started_at=10.0,
        updated_at=11.0,
        completed_at=12.5 if status in {"completed", "failed", "cancelled"} else None,
        recent_operations=(),
    )

    card = render_feishu_progress_card(snapshot)

    assert card["header"]["template"] == expected_template


def test_feishu_progress_card_completed_uses_lively_copy_and_duration():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-1", title="Run checks")
    tracker.record_tool_started("terminal", "python /tmp/checks.py")
    tracker.record_tool_completed("terminal", duration=1.234, is_error=False)
    tracker.mark_completed(is_error=False)

    card = render_feishu_progress_card(tracker.snapshot())
    rendered = _rendered(card)

    assert card["header"]["template"] == "green"
    assert "✅" in card["header"]["title"]["content"]
    assert "小沙" in card["header"]["title"]["content"]
    assert "完成" in rendered
    assert "1.23s" in rendered


def test_feishu_progress_card_failed_uses_warning_copy_without_raw_output():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-1", title="Run failing command")
    tracker.record_tool_started("terminal", "python /tmp/weather_query.py --location Sanya")
    tracker.record_tool_completed(
        "terminal",
        duration=0.5,
        is_error=True,
        preview="Traceback: request failed for token=super-secret",
        args={"command": "python /tmp/weather_query.py --location Sanya"},
    )
    tracker.mark_completed(is_error=True)

    card = render_feishu_progress_card(tracker.snapshot())
    rendered = _rendered(card)

    assert card["header"]["template"] in {"red", "orange"}
    assert "小沙" in card["header"]["title"]["content"]
    assert "详情已记录" in rendered
    assert "weather_query.py" in rendered
    assert "Traceback" not in rendered
    assert "super-secret" not in rendered
    assert "--location" not in rendered
    assert "/tmp/" not in rendered


def test_feishu_progress_card_sanitizes_dashboard_link():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-1", title="Dashboard task")

    card = render_feishu_progress_card(
        tracker.snapshot(),
        dashboard_url="https://dashboard.example.local:9119/base?session_token=secret#frag",
    )
    rendered = _rendered(card)

    assert "https://dashboard.example.local:9119/base/progress" in rendered
    assert "session_token" not in rendered
    assert "secret" not in rendered
    assert "frag" not in rendered


def test_feishu_progress_card_tool_progress_off_hides_operations():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-1", title="Quiet task")
    tracker.record_tool_started("terminal", "python /tmp/hidden.py --secret value")

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    assert "Quiet task" in rendered
    assert "terminal" not in rendered
    assert "hidden.py" not in rendered
    assert "--secret" not in rendered


def test_feishu_progress_card_displays_skill_view_skill_name_not_tool_name():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-skill", title="Use weather skill")
    tracker.record_tool_started("skill_view", "weather-query", {"name": "weather-query"})

    card = render_feishu_progress_card(tracker.snapshot())
    rendered = _rendered(card)

    assert "技能：weather-query" in rendered
    assert "skill_view" not in rendered


def test_feishu_progress_card_allows_categorized_skill_name_without_raw_args():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-skill-category", title="Load planning skill")
    tracker.record_tool_started(
        "skill_view",
        "software-development/plan",
        {"name": "software-development/plan", "file_path": "references/private.md?token=super-secret"},
    )

    card = render_feishu_progress_card(tracker.snapshot())
    rendered = _rendered(card)

    assert "技能：software-development/plan" in rendered
    assert "file_path" not in rendered
    assert "private.md" not in rendered
    assert "token" not in rendered
    assert "super-secret" not in rendered
    assert "skill_view" not in rendered


def test_feishu_progress_card_rejects_unsafe_skill_view_preview():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-skill-unsafe", title="Unsafe skill preview")
    tracker.record_tool_started(
        "skill_view",
        "[weather](https://evil.example/path?token=super-secret)",
        {"name": "[weather](https://evil.example/path?token=super-secret)"},
    )

    card = render_feishu_progress_card(tracker.snapshot())
    rendered = _rendered(card)

    assert "https://evil.example" not in rendered
    assert "super-secret" not in rendered
    assert "[weather]" not in rendered
    assert "weather](" not in rendered


def test_feishu_progress_card_rejects_path_shaped_skill_names():
    from gateway.progress.renderers import render_feishu_progress_card

    for unsafe_name in ("etc/passwd", "references/private", "C:/Users/Alice", "scripts/deploy"):
        tracker = ProgressTracker(transaction_id=f"tx-{unsafe_name}", title="Unsafe skill path")
        tracker.record_tool_started("skill_view", unsafe_name, {"name": unsafe_name})

        card = render_feishu_progress_card(tracker.snapshot())
        rendered = _rendered(card)

        assert f"技能：{unsafe_name}" not in rendered


def test_feishu_progress_card_rejects_token_shaped_skill_names():
    from gateway.progress.renderers import render_feishu_progress_card

    for unsafe_name in ("sk-live-supersecret", "ghp_supersecrettoken", "xoxb-supersecrettoken"):
        tracker = ProgressTracker(transaction_id=f"tx-{unsafe_name}", title="Unsafe token skill")
        tracker.record_tool_started("skill_view", unsafe_name, {"name": unsafe_name})

        card = render_feishu_progress_card(tracker.snapshot())
        rendered = _rendered(card)

        assert unsafe_name not in rendered


def test_feishu_progress_card_prefers_skill_args_over_preview():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-skill-args", title="Prefer args skill")
    tracker.record_tool_started("skill_view", "unsafe-preview", {"name": "weather-query"})

    card = render_feishu_progress_card(tracker.snapshot())
    rendered = _rendered(card)

    assert "技能：weather-query" in rendered
    assert "unsafe-preview" not in rendered


def test_feishu_progress_card_does_not_use_completed_skill_output_as_name():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-skill-completed", title="Completed skill")
    tracker.record_tool_started("skill_view", "weather-query", {"name": "weather-query"})
    tracker.record_tool_completed("skill_view", duration=0.25, preview="software-development/plan")

    card = render_feishu_progress_card(tracker.snapshot())
    rendered = _rendered(card)

    assert "技能：weather-query" in rendered
    assert "software-development/plan" not in rendered


def test_feishu_progress_card_extracts_completed_skill_name_from_json_args_preview_with_null():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-skill-json-null", title="Completed skill with optional file")
    tracker.record_tool_started("skill_view", "weather-query", {"name": "weather-query", "file_path": None})
    tracker.record_tool_completed("skill_view", duration=0.1)

    card = render_feishu_progress_card(tracker.snapshot())
    rendered = _rendered(card)

    assert "技能：weather-query" in rendered
    assert "skill_view" not in rendered
    assert "file_path" not in rendered


def test_feishu_progress_card_does_not_derive_command_name_from_raw_output_preview():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-raw-output", title="Failing command")
    tracker.record_tool_started("terminal", "python /tmp/safe_runner.py")
    tracker.record_tool_completed(
        "terminal",
        is_error=True,
        preview="Traceback wrote /tmp/customer_secret_dump.py token=super-secret",
    )

    card = render_feishu_progress_card(tracker.snapshot())
    rendered = _rendered(card)

    assert "customer_secret_dump.py" not in rendered
    assert "Traceback" not in rendered
    assert "super-secret" not in rendered


def test_feishu_progress_card_ignores_untrusted_command_name_metadata():
    from gateway.progress.events import ProgressOperation
    from gateway.progress.renderers import render_feishu_progress_card

    snapshot = TransactionSnapshot(
        transaction_id="tx-metadata",
        title="Metadata command task",
        status="running",
        started_at=1.0,
        updated_at=2.0,
        recent_operations=(
            ProgressOperation(
                id="op-metadata",
                event_type="tool.started",
                tool_name="terminal",
                status="running",
                metadata={"command_name": "fake_token_value"},
            ),
        ),
    )

    card = render_feishu_progress_card(snapshot)
    rendered = _rendered(card)

    assert "fake_token_value" not in rendered
    assert "terminal" in rendered


def test_feishu_progress_card_sanitizes_markdown_title_and_non_string_options():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(
        transaction_id="tx-title",
        title="[click me](https://evil.example/path?token=super-secret) <at id=ou_bad>Dog</at>",
    )

    card = render_feishu_progress_card(
        tracker.snapshot(),
        tool_progress_mode=object(),
        style=object(),
        dashboard_url="javascript:alert(1)",
    )
    rendered = _rendered(card)

    assert "https://evil.example" not in rendered
    assert "super-secret" not in rendered
    assert "<at" not in rendered
    assert "javascript:" not in rendered
    assert "click me" in rendered


def test_feishu_progress_card_does_not_scan_non_terminal_previews_for_scripts():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-subagent", title="Subagent task")
    tracker.record_callback_event(
        "subagent.progress",
        tool_name="subagent",
        preview="review mentioned /tmp/private_strategy.py but did not run it",
    )

    card = render_feishu_progress_card(tracker.snapshot())
    rendered = _rendered(card)

    assert "private_strategy.py" not in rendered
    assert "subagent" in rendered


def test_feishu_progress_card_does_not_scan_command_arguments_for_script_names():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-argument", title="Argument task")
    tracker.record_tool_started(
        "terminal",
        "grep needle /tmp/private_dump.py",
        {"command": "grep needle /tmp/private_dump.py"},
    )

    card = render_feishu_progress_card(tracker.snapshot())
    rendered = _rendered(card)

    assert "private_dump.py" not in rendered
    assert "grep" not in rendered
    assert "terminal" in rendered


def test_feishu_progress_card_does_not_parse_nested_command_fields_inside_arguments():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-nested-command", title="Nested command task")
    tracker.record_tool_started(
        "terminal",
        'echo {"command": "/tmp/private_dump.py"}',
        {"command": 'echo {"command": "/tmp/private_dump.py"}'},
    )

    card = render_feishu_progress_card(tracker.snapshot())
    rendered = _rendered(card)

    assert "private_dump.py" not in rendered
    assert "terminal" in rendered


def test_feishu_progress_card_does_not_treat_interpreter_option_values_as_scripts():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-interpreter-option", title="Interpreter option task")
    tracker.record_tool_started(
        "terminal",
        "node --require /tmp/customer_secret_hook.js /tmp/app.js",
        {"command": "node --require /tmp/customer_secret_hook.js /tmp/app.js"},
    )

    card = render_feishu_progress_card(tracker.snapshot())
    rendered = _rendered(card)

    assert "customer_secret_hook.js" not in rendered
    assert "app.js" not in rendered
    assert "node" in rendered
