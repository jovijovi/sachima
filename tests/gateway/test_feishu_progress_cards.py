"""Tests for pure Feishu progress card rendering."""

import json
import re
from datetime import datetime

import pytest

from gateway.progress.events import TransactionSnapshot
from gateway.progress.tracker import ProgressTracker


def _rendered(card: dict) -> str:
    return json.dumps(card, ensure_ascii=False, sort_keys=True)


def test_feishu_progress_card_renders_flat_todo_block_before_operations():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo", title="查看任务清单")
    tracker.record_tool_started("read_file", "a.py")
    tracker.update_todo_items([
        {"id": "1", "content": "准备实现方案", "status": "completed"},
        {"id": "2", "content": "修改代码", "status": "completed"},
        {"id": "3", "content": "跑测试", "status": "in_progress"},
        {"id": "4", "content": "Codex 复审", "status": "pending"},
        {"id": "5", "content": "提交 PR", "status": "pending"},
    ])

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="all")
    rendered = _rendered(card)

    assert "待办 5" in rendered
    assert "✅ ~~准备实现方案~~" in rendered  # completed → strikethrough
    assert "➡️ 跑测试" in rendered  # in_progress → arrow
    assert "○ 提交 PR" in rendered  # pending → hollow circle
    # The todo block precedes the recent-operations block.
    assert rendered.index("待办") < rendered.index("最近操作")


def test_feishu_progress_card_renders_todo_block_english_labels():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-en", title="Show todos")
    tracker.update_todo_items([
        {"id": "1", "content": "Prepare plan", "status": "completed"},
        {"id": "2", "content": "Run tests", "status": "in_progress"},
    ])

    card = render_feishu_progress_card(tracker.snapshot(), language="en", tool_progress_mode="off")
    rendered = _rendered(card)

    assert "To-dos 2" in rendered
    assert "✅ ~~Prepare plan~~" in rendered
    assert "➡️ Run tests" in rendered
    assert "待办" not in rendered


def test_feishu_progress_card_renders_two_level_todo_groups():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-2level", title="分组任务")
    tracker.update_todo_items([
        {"id": "pr", "content": "PR 验证", "status": "in_progress"},
        {"id": "local", "content": "本地测试", "status": "completed", "parent_id": "pr"},
        {"id": "codex", "content": "Codex 复审", "status": "in_progress", "parent_id": "pr"},
        {"id": "ci", "content": "CI 等待", "status": "pending", "parent_id": "pr"},
        {"id": "card", "content": "提审卡", "status": "pending", "parent_id": "pr"},
        {"id": "release", "content": "发布", "status": "pending"},
        {"id": "merge", "content": "合并", "status": "pending", "parent_id": "release"},
    ])

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    assert "待办 7" in rendered
    assert "▸ PR 验证 1/4" in rendered  # one of four children completed
    assert "▸ 发布 0/1" in rendered
    # Children render indented under their parent group.
    assert "  ✅ ~~本地测试~~" in rendered
    assert "  ➡️ Codex 复审" in rendered


def test_feishu_progress_card_omits_todo_block_when_empty():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-empty", title="空任务")

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    # "待办" must not appear when the todo list is empty (block omitted entirely).
    assert "待办" not in rendered


def test_feishu_progress_card_todo_block_does_not_leak_secrets():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-secret", title="敏感任务")
    leak = "card-todo-" + "secret"
    tracker.update_todo_items([
        {"id": "1", "content": "Authorization: Bearer " + leak, "status": "pending"},
    ])

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    assert leak not in rendered
    assert "待办 1" in rendered


def test_feishu_progress_card_todo_block_caps_lines_with_overflow_note():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-overflow", title="超量任务")
    tracker.update_todo_items([
        {"id": str(i), "content": f"任务 {i}", "status": "pending"} for i in range(15)
    ])

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    assert "待办 15" in rendered
    assert "还有" in rendered  # overflow note covers the hidden items


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
    assert "任务工作台" in card["header"]["title"]["content"]
    assert "小沙" not in rendered
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


def test_feishu_progress_card_uses_task_workbench_copy_and_operation_timing():
    from gateway.progress.events import ContextUsageSnapshot, ProgressOperation, TransactionSnapshot
    from gateway.progress.renderers import render_feishu_progress_card

    snapshot = TransactionSnapshot(
        transaction_id="tx-workbench",
        title="评估飞书任务工作台卡片实现方案",
        status="running",
        started_at=10.0,
        updated_at=30.0,
        recent_operations=(
            ProgressOperation(
                id="op-read",
                event_type="tool.completed",
                tool_name="read_file",
                status="completed",
                started_at=10.0,
                updated_at=12.5,
                completed_at=12.5,
                duration=2.5,
            ),
            ProgressOperation(
                id="op-render",
                event_type="tool.started",
                tool_name="browser_vision",
                status="running",
                started_at=20.0,
                updated_at=30.0,
            ),
        ),
        context_usage=ContextUsageSnapshot(
            current_tokens=200_796,
            context_window=400_000,
            peak_tokens=271_345,
            compression_count=4,
        ),
    )

    card = render_feishu_progress_card(snapshot, tool_progress_mode="all")
    rendered = _rendered(card)

    assert "任务工作台" in card["header"]["title"]["content"]
    assert "任务：" in rendered
    assert "状态：" in rendered
    assert "耗时：" in rendered
    assert "上下文：" in rendered
    assert "自动压缩 4 次" in rendered
    assert "最近操作：" in rendered
    assert "最近动作" not in rendered
    read_start = datetime.fromtimestamp(10.0).strftime("%H:%M:%S")
    read_end = datetime.fromtimestamp(12.5).strftime("%H:%M:%S")
    render_start = datetime.fromtimestamp(20.0).strftime("%H:%M:%S")
    assert f"{read_start} - {read_end}" in rendered
    assert f"{render_start} - 进行中" in rendered
    assert "开始" not in rendered
    assert "结束" not in rendered
    assert "2秒" in rendered
    assert "2.50s" not in rendered
    assert "进行中" in rendered
    assert "完整调用链" not in rendered
    assert "飞书只显示摘要" not in rendered


def test_feishu_progress_card_supports_english_labels():
    from gateway.progress.renderers import detect_feishu_progress_card_language, render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-en", title="Review Feishu card layout")
    tracker.record_tool_started("read_file", "gateway/progress/renderers.py")

    assert detect_feishu_progress_card_language("Review Feishu card layout", configured="auto") == "en"
    assert detect_feishu_progress_card_language("评估飞书卡片", configured="auto") == "zh"
    assert detect_feishu_progress_card_language("评估飞书卡片", configured="en") == "en"

    card = render_feishu_progress_card(tracker.snapshot(), language="en")
    rendered = _rendered(card)

    assert "Task Workbench" in card["header"]["title"]["content"]
    assert "Task:" in rendered
    assert "Status:" in rendered
    assert "Recent operations:" in rendered
    assert "任务工作台" not in rendered
    assert "最近操作" not in rendered


def test_feishu_progress_card_replaces_unsafe_command_shaped_task_title():
    from gateway.progress.renderers import render_feishu_progress_card

    unsafe_titles = [
        'please review curl -H "Authorization: Bearer abc123" https://example.test/path?token=x',
        '-H "X-Api-Key: x" https://example.test/path?token=x',
        '--header "Cookie: session=abc123" https://example.test/path?token=x',
    ]
    for title in unsafe_titles:
        snapshot = TransactionSnapshot(
            transaction_id="tx-unsafe-title",
            title=title,
            status="running",
            started_at=1.0,
            updated_at=2.0,
        )

        card = render_feishu_progress_card(snapshot, language="en", tool_progress_mode="off")
        rendered = _rendered(card)

        assert "Handle user request safely" in rendered
        assert "curl" not in rendered
        assert "Authorization" not in rendered
        assert "X-Api-Key" not in rendered
        assert "Cookie" not in rendered
        assert "Bearer" not in rendered
        assert "example.test" not in rendered
        assert "token" not in rendered


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
    assert "任务工作台" in card["header"]["title"]["content"]
    assert "完成" in rendered
    assert "1秒" in rendered
    assert "1.23s" not in rendered


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
    assert "任务工作台" in card["header"]["title"]["content"]
    assert "原始输出不在飞书展示" not in rendered
    assert "weather_query.py" in rendered
    assert "Traceback" not in rendered
    assert "super-secret" not in rendered
    assert "--location" not in rendered
    assert "/tmp/" not in rendered


def test_feishu_progress_card_includes_compact_context_usage_summary():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-context", title="上下文压力观察")
    tracker.update_context_usage(
        current_tokens=40_960,
        context_window=128_000,
        peak_tokens=65_536,
        compression_count=2,
    )

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    assert "上下文" in rendered
    assert "40,960 / 128,000" in rendered
    assert "32.0%" in rendered
    assert "峰值 65,536" in rendered
    assert "自动压缩 2 次" in rendered


def test_feishu_progress_card_includes_execution_rounds_in_zh_and_en():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-rounds", title="执行轮次展示")
    tracker.update_iteration_usage(current_rounds=12, max_rounds=90)

    zh = _rendered(render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off"))
    en = _rendered(render_feishu_progress_card(tracker.snapshot(), language="en", tool_progress_mode="off"))

    assert "执行轮次" in zh
    assert "工作轮数" not in zh
    assert "12 / 90" in zh
    assert "Rounds" in en
    assert "12 / 90" in en


def test_feishu_progress_card_omits_work_rounds_without_meaningful_max():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-rounds-empty", title="无有效轮数")
    tracker.update_iteration_usage(current_rounds=0, max_rounds=0)

    rendered = _rendered(render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off"))

    assert "执行轮次" not in rendered
    assert "工作轮数" not in rendered
    assert "0 / 0" not in rendered


def test_feishu_progress_card_includes_sanitized_model_and_account_limits_in_order():
    from gateway.progress.events import ContextUsageSnapshot, TransactionSnapshot
    from gateway.progress.renderers import render_feishu_progress_card

    snapshot = TransactionSnapshot(
        transaction_id="tx-metadata",
        title="展示任务元数据",
        status="running",
        started_at=10.0,
        updated_at=75.0,
        model_display="openrouter/anthropic/claude-sonnet-4.6",
        context_usage=ContextUsageSnapshot(
            current_tokens=40_960,
            context_window=128_000,
            peak_tokens=65_536,
            compression_count=2,
        ),
        account_limit_lines=(
            "Provider: openrouter",
            "Session: 74% remaining (26% used)",
        ),
    )

    card = render_feishu_progress_card(snapshot, tool_progress_mode="off")
    details = card["elements"][0]["content"]
    rendered = _rendered(card)

    assert "模型：" in rendered
    assert "账户限额：" in rendered
    assert "(Account limits)" not in rendered
    assert details.index("任务") < details.index("状态")
    assert details.index("状态") < details.index("耗时")
    assert details.index("耗时") < details.index("模型")
    assert details.index("模型") < details.index("上下文")
    assert details.index("上下文") < details.index("账户限额")
    assert "Provider: openrouter" in rendered
    assert "Session: 74% remaining" in rendered
    assert "**💳 账户限额：**\n- Provider: openrouter\n- Session: 74% remaining" in details
    assert "账户限额：** Provider" not in details
    assert "Provider: openrouter · Session" not in details


def test_feishu_progress_card_omits_absent_model_and_account_limits():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-no-metadata", title="无可用元数据")

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    assert "模型" not in rendered
    assert "账户限额" not in rendered


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    [
        (1, "1秒"),
        (75, "1分15秒"),
        (3661, "1小时1分1秒"),
        (90_061, "1日1小时1分1秒"),
        ((365 + 30 + 5) * 24 * 60 * 60, "1年1月5日"),
    ],
)
def test_feishu_progress_card_detail_duration_uses_chinese_units(elapsed, expected):
    from gateway.progress.renderers import render_feishu_progress_card

    snapshot = TransactionSnapshot(
        transaction_id="tx-duration",
        title="展示中文耗时",
        status="running",
        started_at=10.0,
        updated_at=10.0 + elapsed,
    )

    card = render_feishu_progress_card(snapshot, tool_progress_mode="off")
    rendered = _rendered(card)

    assert expected in rendered
    assert not re.search(r"\d+\.\d+s", rendered)


def test_feishu_progress_card_hides_context_usage_until_tokens_are_known():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-context-empty", title="等待首次用量")
    tracker.update_context_usage(
        current_tokens=0,
        context_window=128_000,
        peak_tokens=0,
        compression_count=0,
        threshold_tokens=102_400,
    )

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    assert "上下文" not in rendered
    assert "0 / 128,000" not in rendered


def test_feishu_progress_card_does_not_show_zero_ratio_for_partial_context_usage():
    from gateway.progress.renderers import render_feishu_progress_card

    peak_tracker = ProgressTracker(transaction_id="tx-peak-only", title="只有峰值")
    peak_tracker.update_context_usage(current_tokens=0, context_window=128_000, peak_tokens=65_536)
    compression_tracker = ProgressTracker(transaction_id="tx-compress-only", title="只有压缩次数")
    compression_tracker.update_context_usage(current_tokens=0, context_window=128_000, compression_count=2)

    peak_rendered = _rendered(render_feishu_progress_card(peak_tracker.snapshot(), tool_progress_mode="off"))
    compression_rendered = _rendered(render_feishu_progress_card(compression_tracker.snapshot(), tool_progress_mode="off"))

    assert "峰值 65,536" in peak_rendered
    assert "压缩 2 次" in compression_rendered
    assert "0 / 128,000" not in peak_rendered
    assert "0 / 128,000" not in compression_rendered


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


def test_feishu_progress_card_omits_footer_safety_copy():
    from gateway.progress.renderers import render_feishu_progress_card

    for language in ("zh", "en"):
        for status in ("running", "completed", "failed"):
            snapshot = TransactionSnapshot(
                transaction_id=f"tx-footer-{language}-{status}",
                title="检查事务卡底部安全文案",
                status=status,
                started_at=10.0,
                updated_at=12.0,
                completed_at=12.0 if status in {"completed", "failed"} else None,
            )

            card = render_feishu_progress_card(snapshot, language=language, tool_progress_mode="off")
            rendered = _rendered(card)

            assert "仅展示安全摘要" not in rendered
            assert "Safe summary only" not in rendered
            assert "原始输出不在飞书展示" not in rendered


def test_feishu_progress_card_uses_emoji_prefixed_metric_labels():
    from gateway.progress.events import ContextUsageSnapshot
    from gateway.progress.renderers import render_feishu_progress_card

    snapshot = TransactionSnapshot(
        transaction_id="tx-emoji-labels",
        title="评估事务卡指标标签",
        status="running",
        started_at=10.0,
        updated_at=30.0,
        context_usage=ContextUsageSnapshot(
            current_tokens=200_796,
            context_window=400_000,
            peak_tokens=271_345,
            compression_count=4,
        ),
    )

    card = render_feishu_progress_card(snapshot, tool_progress_mode="off")
    rendered = _rendered(card)

    assert "📌 任务" in rendered
    assert "🔄 状态" in rendered
    assert "⏱️ 耗时" in rendered
    assert "🧠 上下文" in rendered


@pytest.mark.parametrize(
    ("status", "expected_status_label"),
    [
        ("running", "🔄 状态"),
        ("completed", "✅ 状态"),
        ("failed", "⚠️ 状态"),
    ],
)
def test_feishu_progress_card_status_label_uses_state_icon(status, expected_status_label):
    from gateway.progress.renderers import render_feishu_progress_card

    snapshot = TransactionSnapshot(
        transaction_id=f"tx-status-icon-{status}",
        title="状态图标标签",
        status=status,
        started_at=10.0,
        updated_at=12.0,
        completed_at=12.0 if status in {"completed", "failed"} else None,
    )

    card = render_feishu_progress_card(snapshot, tool_progress_mode="off")
    rendered = _rendered(card)

    assert expected_status_label in rendered


def test_feishu_progress_card_supports_english_emoji_metric_labels():
    from gateway.progress.events import ContextUsageSnapshot
    from gateway.progress.renderers import render_feishu_progress_card

    snapshot = TransactionSnapshot(
        transaction_id="tx-emoji-labels-en",
        title="Review task workbench metric labels",
        status="running",
        started_at=10.0,
        updated_at=30.0,
        context_usage=ContextUsageSnapshot(
            current_tokens=200_796,
            context_window=400_000,
            peak_tokens=271_345,
            compression_count=4,
        ),
    )

    card = render_feishu_progress_card(snapshot, language="en", tool_progress_mode="off")
    rendered = _rendered(card)

    assert "📌 Task" in rendered
    assert "🔄 Status" in rendered
    assert "⏱️ Duration" in rendered
    assert "🧠 Context" in rendered


def test_feishu_recent_operation_timing_uses_interval_for_completed_operation():
    from gateway.progress.events import ProgressOperation
    from gateway.progress.renderers import render_feishu_progress_card

    started_at = 1_700_000_791.0
    completed_at = 1_700_000_793.06
    snapshot = TransactionSnapshot(
        transaction_id="tx-op-interval",
        title="排查会话检索耗时",
        status="running",
        started_at=started_at,
        updated_at=completed_at,
        recent_operations=(
            ProgressOperation(
                id="op-search",
                event_type="tool.completed",
                tool_name="session_search",
                status="completed",
                started_at=started_at,
                updated_at=completed_at,
                completed_at=completed_at,
                duration=2.06,
            ),
        ),
    )

    card = render_feishu_progress_card(snapshot, tool_progress_mode="all")
    rendered = _rendered(card)

    start_str = datetime.fromtimestamp(started_at).strftime("%H:%M:%S")
    end_str = datetime.fromtimestamp(completed_at).strftime("%H:%M:%S")

    assert f"{start_str} - {end_str}" in rendered
    assert "耗时 2秒" in rendered
    assert "耗时 2.06s" not in rendered
    assert not re.search(r"\d+\.\d+s", rendered)
    assert "开始" not in rendered
    assert "结束" not in rendered


def test_feishu_recent_operation_timing_uses_interval_for_running_operation():
    from gateway.progress.events import ProgressOperation
    from gateway.progress.renderers import render_feishu_progress_card

    started_at = 1_700_000_791.0
    snapshot = TransactionSnapshot(
        transaction_id="tx-op-running-interval",
        title="排查会话检索进度",
        status="running",
        started_at=started_at,
        updated_at=started_at,
        recent_operations=(
            ProgressOperation(
                id="op-running",
                event_type="tool.started",
                tool_name="session_search",
                status="running",
                started_at=started_at,
                updated_at=started_at,
            ),
        ),
    )

    card = render_feishu_progress_card(snapshot, tool_progress_mode="all")
    rendered = _rendered(card)

    start_str = datetime.fromtimestamp(started_at).strftime("%H:%M:%S")

    assert f"{start_str} - 进行中" in rendered
    assert "开始" not in rendered
    assert "结束" not in rendered
