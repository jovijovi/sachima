"""Tests for pure Feishu progress card rendering."""

import json
import re
from datetime import datetime

import pytest

from gateway.progress.events import TransactionSnapshot
from gateway.progress.tracker import ProgressTracker


def _rendered(card: dict) -> str:
    return json.dumps(card, ensure_ascii=False, sort_keys=True)


def _todo_lines(card: dict) -> list[str]:
    """Return the todo block's rendered lines, title line excluded."""

    for element in card.get("elements", []):
        content = str(element.get("content", ""))
        if content.startswith("**🧾"):
            return content.splitlines()[1:]
    return []


def _todo_title(card: dict) -> str:
    for element in card.get("elements", []):
        content = str(element.get("content", ""))
        if content.startswith("**🧾"):
            return content.splitlines()[0]
    return ""


def _group_line(card: dict, name: str) -> str:
    matches = [line for line in _todo_lines(card) if line.startswith("📂") and name in line]
    assert len(matches) == 1, f"expected one group line for {name!r}, got {matches}"
    return matches[0]


def _leaf_lines(card: dict) -> list[str]:
    return [line for line in _todo_lines(card) if not line.lstrip().startswith(("📂", "…"))]


def test_feishu_progress_card_renders_flat_todo_block_before_operations():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo")
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

    assert "待办 - 2 / 5（40%）" in rendered
    assert "✅ ~~准备实现方案~~" in rendered  # completed → strikethrough
    assert "▶️ 跑测试" in rendered  # in_progress → play arrow
    assert "⏳ 提交 PR" in rendered  # pending → hourglass
    # The todo block precedes the recent-operations block.
    assert rendered.index("待办") < rendered.index("最近操作")
    assert [element["tag"] for element in card["elements"]] == [
        "markdown",
        "hr",
        "markdown",
        "hr",
        "markdown",
    ]


def test_feishu_progress_card_separates_only_present_sections():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-sections")
    tracker.record_tool_started("read_file", "a.py")

    without_todos = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="all")
    assert [element["tag"] for element in without_todos["elements"]] == ["markdown", "hr", "markdown"]

    tracker.update_todo_items([{"id": "1", "content": "跑测试", "status": "in_progress"}])
    without_operations = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    assert [element["tag"] for element in without_operations["elements"]] == ["markdown", "hr", "markdown"]


def test_feishu_progress_card_renders_todo_block_english_labels():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-en")
    tracker.update_todo_items([
        {"id": "1", "content": "Prepare plan", "status": "completed"},
        {"id": "2", "content": "Run tests", "status": "in_progress"},
    ])

    card = render_feishu_progress_card(tracker.snapshot(), language="en", tool_progress_mode="off")
    rendered = _rendered(card)

    assert "TODO - 1 / 2 (50%)" in rendered
    assert "✅ ~~Prepare plan~~" in rendered
    assert "▶️ Run tests" in rendered
    assert "待办" not in rendered


def test_feishu_progress_card_renders_two_level_todo_groups():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-2level")
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

    # Group rows are summary nodes: only the five leaf tasks are counted.
    assert "待办 - 1 / 5（20%）" in rendered
    assert "📂 PR 验证 1/4" in rendered  # one of four children completed
    assert "📂 发布 0/1" in rendered
    # Children render indented under their parent group.
    assert "  ✅ ~~本地测试~~" in rendered
    assert "  ▶️ Codex 复审" in rendered


def test_feishu_progress_card_renders_executor_badge_before_content_on_flat_items():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-executor")
    tracker.update_todo_items([
        {"id": "1", "content": "准备实现方案", "status": "completed", "executor": "claude"},
        {"id": "2", "content": "跑测试", "status": "in_progress", "executor": "codex"},
        {"id": "3", "content": "提交 PR", "status": "pending"},
    ])

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    # Badge sits between the status icon and the content (brackets are
    # markdown-escaped inside the card; JSON doubles the backslashes).
    assert "▶️ \\\\[codex\\\\] 跑测试" in rendered
    # Badge stays outside the strikethrough so the label stays legible.
    assert "✅ \\\\[claude\\\\] ~~准备实现方案~~" in rendered
    # Unlabeled items render with no badge.
    assert "⏳ 提交 PR" in rendered
    # The legacy trailing-suffix shape is gone.
    assert "· codex" not in rendered
    assert "· claude" not in rendered


def test_feishu_progress_card_escapes_executor_label_markdown():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-executor-escape")
    tracker.update_todo_items([
        {"id": "1", "content": "跑测试", "status": "in_progress", "executor": "gemini-cli"},
    ])

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    # The hyphen is markdown-escaped inside the badge (JSON doubles the backslashes).
    assert "▶️ \\\\[gemini\\\\-cli\\\\] 跑测试" in rendered


def test_feishu_progress_card_displays_hermes_agent_executor_as_hermes():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-executor-alias")
    tracker.update_todo_items([
        {"id": "1", "content": "检查任务工作台展示", "status": "in_progress", "executor": "hermes-agent"},
    ])

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    assert "▶️ \\\\[hermes\\\\] 检查任务工作台展示" in rendered
    assert "hermes-agent" not in rendered
    assert "hermes\\\\-agent" not in rendered


def test_feishu_progress_card_renders_executor_badges_on_leaves_only():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-executor-2level")
    tracker.update_todo_items([
        {"id": "pr", "content": "PR 验证", "status": "in_progress", "executor": "claude"},
        {"id": "local", "content": "本地测试", "status": "completed", "parent_id": "pr", "executor": "codex"},
        {"id": "ci", "content": "CI 等待", "status": "pending", "parent_id": "pr"},
    ])

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    # Group header: name plus the aggregate over direct children, nothing else.
    assert _group_line(card, "PR 验证") == "📂 PR 验证 1/2"
    # Leaves keep their own single executor badge.
    assert "  ✅ \\\\[codex\\\\] ~~本地测试~~" in rendered
    assert "  ⏳ CI 等待" in rendered
    assert "· claude" not in rendered
    assert "· codex" not in rendered


def test_feishu_progress_card_group_row_omits_child_executor_summary():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-parallel-participants")
    tracker.update_todo_items([
        {"id": "goal", "content": "并行验证", "status": "in_progress"},
        {"id": "fix", "content": "实现修复", "status": "completed", "parent_id": "goal", "executor": "claude"},
        {"id": "review", "content": "独立复审", "status": "in_progress", "parent_id": "goal", "executor": "codex"},
        {"id": "report", "content": "整理报告", "status": "in_progress", "parent_id": "goal"},
    ])

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    # The group row aggregates completion only; it never summarizes which
    # agents participate.
    assert _group_line(card, "并行验证") == "📂 并行验证 1/3"
    # Sibling leaves keep their own single-executor badge and status; two
    # siblings render as in_progress concurrently.
    assert "  ✅ \\\\[claude\\\\] ~~实现修复~~" in rendered
    assert "  ▶️ \\\\[codex\\\\] 独立复审" in rendered
    assert "  ▶️ 整理报告" in rendered


def test_feishu_progress_card_group_row_english_shape_stays_agent_free():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-parallel-participants-en")
    tracker.update_todo_items([
        {"id": "goal", "content": "Parallel verification", "status": "in_progress"},
        {"id": "fix", "content": "Author fix", "status": "completed", "parent_id": "goal", "executor": "claude"},
        {"id": "review", "content": "Independent review", "status": "in_progress", "parent_id": "goal", "executor": "codex"},
    ])

    card = render_feishu_progress_card(tracker.snapshot(), language="en", tool_progress_mode="off")
    rendered = _rendered(card)

    assert _group_line(card, "Parallel verification") == "📂 Parallel verification 1/2"
    assert "(claude" not in rendered
    assert "（claude" not in rendered
    # Leaves still carry their own badge in English cards.
    assert "  ▶️ \\\\[codex\\\\] Independent review" in rendered


def test_feishu_progress_card_group_row_hides_wide_fan_out_agents():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-parallel-bound")
    tracker.update_todo_items([
        {"id": "goal", "content": "多执行者并行", "status": "in_progress"},
        {"id": "1", "content": "任务一", "status": "in_progress", "parent_id": "goal", "executor": "codex"},
        {"id": "2", "content": "任务二", "status": "in_progress", "parent_id": "goal", "executor": "claude"},
        {"id": "3", "content": "任务三", "status": "pending", "parent_id": "goal", "executor": "codex"},
        {"id": "4", "content": "任务四", "status": "pending", "parent_id": "goal", "executor": "gemini-cli"},
        {"id": "5", "content": "任务五", "status": "pending", "parent_id": "goal", "executor": "opencode"},
        {"id": "6", "content": "任务六", "status": "pending", "parent_id": "goal", "executor": "kimi"},
    ])

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    # A wide fan-out cannot grow the group row: no labels, no overflow count.
    assert _group_line(card, "多执行者并行") == "📂 多执行者并行 0/6"
    # Each child still shows its own executor.
    assert "  ▶️ \\\\[codex\\\\] 任务一" in rendered
    assert "  ⏳ \\\\[gemini\\\\-cli\\\\] 任务四" in rendered


def test_feishu_progress_card_revalidates_executor_labels_at_display_boundary():
    from gateway.progress.events import TodoItemSnapshot
    from gateway.progress.renderers import render_feishu_progress_card

    snapshot = TransactionSnapshot(
        transaction_id="tx-todo-parallel-boundary",
        status="running",
        started_at=1.0,
        updated_at=2.0,
        todo_items=(
            TodoItemSnapshot(id="goal", content="边界复核", status="in_progress"),
            TodoItemSnapshot(
                id="a", content="任务A", status="in_progress",
                parent_id="goal", depth=1, executor="Bearer abc123",
            ),
            TodoItemSnapshot(
                id="b", content="任务B", status="in_progress",
                parent_id="goal", depth=1, executor="codex",
            ),
        ),
    )

    card = render_feishu_progress_card(snapshot, tool_progress_mode="off")
    rendered = _rendered(card)

    # The unsafe label is re-dropped at the renderer boundary; the item itself
    # still renders, and the group row stays a plain aggregate.
    assert _group_line(card, "边界复核") == "📂 边界复核 0/2"
    assert "  ▶️ 任务A" in rendered
    assert "  ▶️ \\\\[codex\\\\] 任务B" in rendered
    assert "abc123" not in rendered


def test_feishu_progress_card_group_row_is_name_and_counter_only():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-parallel-unlabeled")
    tracker.update_todo_items([
        {"id": "goal", "content": "常规分组", "status": "in_progress"},
        {"id": "a", "content": "子项一", "status": "completed", "parent_id": "goal"},
        {"id": "b", "content": "子项二", "status": "pending", "parent_id": "goal"},
    ])

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")

    assert _group_line(card, "常规分组") == "📂 常规分组 1/2"


def test_feishu_progress_card_group_row_drops_parent_executor_badge():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-parallel-parent-badge")
    tracker.update_todo_items([
        {"id": "pr", "content": "PR 验证", "status": "in_progress", "executor": "claude"},
        {"id": "local", "content": "本地测试", "status": "completed", "parent_id": "pr", "executor": "codex"},
        {"id": "ci", "content": "CI 等待", "status": "pending", "parent_id": "pr"},
    ])

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    # The parent's own executor is a group attribute, not work assignment: it
    # never reaches the card. Only the child's badge survives.
    assert _group_line(card, "PR 验证") == "📂 PR 验证 1/2"
    assert "claude" not in rendered
    assert "  ✅ \\\\[codex\\\\] ~~本地测试~~" in rendered


def test_feishu_progress_card_group_row_uses_non_interactive_marker():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-group-marker")
    tracker.update_todo_items([
        {"id": "goal", "content": "分组标识", "status": "in_progress"},
        {"id": "a", "content": "子项一", "status": "pending", "parent_id": "goal"},
    ])

    for language, name in (("zh", "分组标识"), ("en", "分组标识")):
        card = render_feishu_progress_card(
            tracker.snapshot(), tool_progress_mode="off", language=language
        )
        rendered = _rendered(card)
        # ``▸`` reads as a clickable collapse control (the TUI uses it that
        # way); groups use a plain, non-interactive folder marker instead.
        assert "▸" not in rendered
        assert _group_line(card, name).startswith("📂 ")


def test_feishu_progress_card_never_renders_secret_shaped_executor():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-executor-secret")
    bare_key = "sk-" + "test-" + ("g" * 32)
    tracker.update_todo_items([
        {"id": "1", "content": "跑测试", "status": "in_progress", "executor": bare_key},
        {"id": "2", "content": "提交 PR", "status": "pending", "executor": "Bearer abc123"},
    ])

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    assert bare_key not in rendered
    assert "abc123" not in rendered
    # Lines render without any badge when the label is dropped.
    assert "▶️ 跑测试" in rendered
    assert "⏳ 提交 PR" in rendered
    assert "\\\\[" not in rendered


def test_feishu_progress_card_shows_every_leaf_up_to_the_shared_limit():
    from gateway.progress.renderers import render_feishu_progress_card
    from gateway.progress.todo_display import MAX_VISIBLE_TODO_LEAVES

    tracker = ProgressTracker(transaction_id="tx-todo-executor-overflow")
    tracker.update_todo_items([
        {"id": str(i), "content": f"任务 {i}", "status": "pending", "executor": "codex"}
        for i in range(MAX_VISIBLE_TODO_LEAVES)
    ])

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    assert f"待办 - 0 / {MAX_VISIBLE_TODO_LEAVES}（0%）" in rendered
    assert len(_leaf_lines(card)) == MAX_VISIBLE_TODO_LEAVES
    assert f"任务 {MAX_VISIBLE_TODO_LEAVES - 1}" in rendered
    # Exactly at the limit there is nothing left to announce.
    assert "未展示" not in rendered


def test_feishu_progress_card_cancelled_todo_uses_forbidden_icon_without_strikethrough():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-cancelled")
    tracker.update_todo_items([
        {"id": "1", "content": "旧版尾缀展示方案", "status": "cancelled", "executor": "other"},
        {"id": "2", "content": "新版徽标展示方案", "status": "in_progress"},
    ])

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    # Cancelled signals through the 🚫 icon only; content stays legible.
    assert "🚫 \\\\[other\\\\] 旧版尾缀展示方案" in rendered
    assert "~~旧版尾缀展示方案~~" not in rendered


def test_feishu_progress_card_renders_failed_todo_icon_defensively():
    # Persistent todo statuses cannot produce ``failed`` today, but the
    # renderer accepts untyped snapshots and must map it if an upstream
    # workbench/progress source ever supplies one.
    from gateway.progress.events import TodoItemSnapshot
    from gateway.progress.renderers import render_feishu_progress_card

    snapshot = TransactionSnapshot(
        transaction_id="tx-todo-failed",
        status="running",
        started_at=1.0,
        updated_at=2.0,
        todo_items=(
            TodoItemSnapshot(id="1", content="修复失败：验证链未通过", status="failed", executor="claude"),
        ),
    )

    card = render_feishu_progress_card(snapshot, tool_progress_mode="off")
    rendered = _rendered(card)

    assert "❌ \\\\[claude\\\\] 修复失败：验证链未通过" in rendered
    assert "~~修复失败：验证链未通过~~" not in rendered


def test_feishu_progress_card_omits_todo_block_when_empty():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-empty")

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    # "待办" must not appear when the todo list is empty (block omitted entirely).
    assert "待办" not in rendered


def test_feishu_progress_card_todo_block_does_not_leak_secrets():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-secret")
    leak = "card-todo-" + "secret"
    tracker.update_todo_items([
        {"id": "1", "content": "Authorization: Bearer " + leak, "status": "pending"},
    ])

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    assert leak not in rendered
    assert "待办 - 0 / 1（0%）" in rendered


def test_feishu_progress_card_todo_block_reports_global_leaf_overflow():
    from gateway.progress.renderers import render_feishu_progress_card
    from gateway.progress.todo_display import MAX_VISIBLE_TODO_LEAVES

    total = MAX_VISIBLE_TODO_LEAVES + 1
    tracker = ProgressTracker(transaction_id="tx-todo-overflow")
    tracker.update_todo_items([
        {"id": str(i), "content": f"任务 {i}", "status": "pending"} for i in range(total)
    ])

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    # The title counts every leaf, not just the displayed ones.
    assert f"待办 - 0 / {total}（0%）" in rendered
    assert len(_leaf_lines(card)) == MAX_VISIBLE_TODO_LEAVES
    assert "… 还有 1 个任务未展示" in _todo_lines(card)
    assert f"任务 {total - 1}" not in rendered


def test_feishu_progress_card_todo_title_counts_only_leaf_tasks():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-leaf-count")
    tracker.update_todo_items(
        [{"id": "goal", "content": "交付目标", "status": "in_progress"}]
        + [
            {"id": f"c{i}", "content": f"子任务 {i}", "status": "pending", "parent_id": "goal"}
            for i in range(6)
        ]
    )

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    # The group node is a summary row: six leaves, none of them done.
    assert "待办 - 0 / 6（0%）" in rendered
    assert "0 / 7" not in rendered
    assert _group_line(card, "交付目标") == "📂 交付目标 0/6"


def test_feishu_progress_card_group_headers_do_not_consume_leaf_budget():
    from gateway.progress.renderers import render_feishu_progress_card
    from gateway.progress.todo_display import MAX_VISIBLE_TODO_LEAVES

    per_group = 5
    groups = MAX_VISIBLE_TODO_LEAVES // per_group
    items = []
    for group in range(groups):
        items.append({"id": f"g{group}", "content": f"任务组 {group}", "status": "in_progress"})
        items += [
            {
                "id": f"g{group}-c{child}",
                "content": f"任务 {group}-{child}",
                "status": "pending",
                "parent_id": f"g{group}",
            }
            for child in range(per_group)
        ]

    tracker = ProgressTracker(transaction_id="tx-todo-group-budget")
    tracker.update_todo_items(items)

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    # 20 leaves + 4 group headers: the headers are free, so nothing is hidden.
    assert f"待办 - 0 / {MAX_VISIBLE_TODO_LEAVES}（0%）" in rendered
    assert len([line for line in _todo_lines(card) if line.startswith("📂")]) == groups
    assert len(_leaf_lines(card)) == MAX_VISIBLE_TODO_LEAVES
    assert "未展示" not in rendered


def test_feishu_progress_card_truncated_group_keeps_header_and_reports_group_overflow():
    from gateway.progress.renderers import render_feishu_progress_card
    from gateway.progress.todo_display import MAX_VISIBLE_TODO_LEAVES

    hidden = 5
    total = MAX_VISIBLE_TODO_LEAVES + hidden
    tracker = ProgressTracker(transaction_id="tx-todo-group-truncated")
    tracker.update_todo_items(
        [{"id": "big", "content": "大任务组", "status": "in_progress"}]
        + [
            {"id": f"c{i}", "content": f"子任务 {i}", "status": "pending", "parent_id": "big"}
            for i in range(total)
        ]
    )

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    lines = _todo_lines(card)
    rendered = _rendered(card)

    # The header keeps the true aggregate over every direct child.
    assert _group_line(card, "大任务组") == f"📂 大任务组 0/{total}"
    assert len(_leaf_lines(card)) == MAX_VISIBLE_TODO_LEAVES
    # Both the in-group note and the global note are exact.
    assert f"  … 本组还有 {hidden} 个任务未展示" in lines
    assert f"… 还有 {hidden} 个任务未展示" in lines
    assert f"待办 - 0 / {total}（0%）" in rendered


def test_feishu_progress_card_never_renders_group_header_without_visible_children():
    from gateway.progress.renderers import render_feishu_progress_card
    from gateway.progress.todo_display import MAX_VISIBLE_TODO_LEAVES

    tail = 3
    tracker = ProgressTracker(transaction_id="tx-todo-group-orphan")
    tracker.update_todo_items(
        [{"id": "first", "content": "首个任务组", "status": "in_progress"}]
        + [
            {"id": f"a{i}", "content": f"首组任务 {i}", "status": "pending", "parent_id": "first"}
            for i in range(MAX_VISIBLE_TODO_LEAVES)
        ]
        + [{"id": "second", "content": "次个任务组", "status": "pending"}]
        + [
            {"id": f"b{i}", "content": f"次组任务 {i}", "status": "pending", "parent_id": "second"}
            for i in range(tail)
        ]
    )

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    lines = _todo_lines(card)
    rendered = _rendered(card)

    # The budget is spent on the first group; the second group is dropped whole
    # rather than leaving a header with no children under it.
    assert _group_line(card, "首个任务组") == f"📂 首个任务组 0/{MAX_VISIBLE_TODO_LEAVES}"
    assert "次个任务组" not in rendered
    assert "次组任务" not in rendered
    assert f"… 还有 {tail} 个任务未展示" in lines
    assert f"待办 - 0 / {MAX_VISIBLE_TODO_LEAVES + tail}（0%）" in rendered


def test_feishu_progress_card_renders_multiple_groups_with_independent_aggregates():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-multi-group")
    tracker.update_todo_items([
        {"id": "impl", "content": "实现组", "status": "in_progress"},
        {"id": "impl-a", "content": "写实现", "status": "completed", "parent_id": "impl"},
        {"id": "impl-b", "content": "补测试", "status": "in_progress", "parent_id": "impl"},
        {"id": "verify", "content": "验证组", "status": "pending"},
        {"id": "verify-a", "content": "跑回归", "status": "pending", "parent_id": "verify"},
        {"id": "verify-b", "content": "复审", "status": "pending", "parent_id": "verify"},
        {"id": "verify-c", "content": "出报告", "status": "completed", "parent_id": "verify"},
        {"id": "ship", "content": "独立收尾任务", "status": "pending"},
    ])

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    assert _group_line(card, "实现组") == "📂 实现组 1/2"
    assert _group_line(card, "验证组") == "📂 验证组 1/3"
    # Six leaves (2 + 3 + one standalone task), two of them completed.
    assert "待办 - 2 / 6（33%）" in rendered
    assert "⏳ 独立收尾任务" in rendered


def test_feishu_progress_card_allows_parallel_in_progress_leaves_across_groups():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-cross-group-parallel")
    tracker.update_todo_items([
        {"id": "impl", "content": "实现组", "status": "in_progress"},
        {"id": "impl-a", "content": "写实现", "status": "in_progress", "parent_id": "impl", "executor": "claude"},
        {"id": "impl-b", "content": "补测试", "status": "pending", "parent_id": "impl"},
        {"id": "review", "content": "复审组", "status": "in_progress"},
        {"id": "review-a", "content": "独立复审", "status": "in_progress", "parent_id": "review", "executor": "codex"},
        {"id": "solo", "content": "并行巡检", "status": "in_progress", "executor": "hermes"},
    ])

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    lines = _todo_lines(card)
    rendered = _rendered(card)

    # parent_id only expresses membership: leaves in different groups (and a
    # standalone leaf) run in_progress at the same time.
    running = [line for line in lines if "▶️" in line]
    assert len(running) == 3
    assert "  ▶️ \\\\[claude\\\\] 写实现" in rendered
    assert "  ▶️ \\\\[codex\\\\] 独立复审" in rendered
    assert "▶️ \\\\[hermes\\\\] 并行巡检" in rendered
    assert _group_line(card, "实现组") == "📂 实现组 0/2"
    assert _group_line(card, "复审组") == "📂 复审组 0/1"


def test_feishu_progress_card_group_row_matches_child_aggregate_without_parent_status():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-todo-parent-status")
    tracker.update_todo_items([
        # The stored parent status lags behind its children; the card must not
        # show a status that contradicts the aggregate.
        {"id": "wrap", "content": "收尾组", "status": "pending"},
        {"id": "wrap-a", "content": "收尾一", "status": "completed", "parent_id": "wrap"},
        {"id": "wrap-b", "content": "收尾二", "status": "completed", "parent_id": "wrap"},
    ])

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    group_line = _group_line(card, "收尾组")
    assert group_line == "📂 收尾组 2/2"
    assert not any(glyph in group_line for glyph in ("⏳", "▶️", "✅", "🚫", "❌"))
    assert "待办 - 2 / 2（100%）" in rendered


def test_feishu_progress_card_english_overflow_and_group_copy():
    from gateway.progress.renderers import render_feishu_progress_card
    from gateway.progress.todo_display import MAX_VISIBLE_TODO_LEAVES

    hidden = 3
    total = MAX_VISIBLE_TODO_LEAVES + hidden
    tracker = ProgressTracker(transaction_id="tx-todo-overflow-en")
    tracker.update_todo_items(
        [{"id": "group", "content": "Release gate", "status": "in_progress"}]
        + [
            {"id": f"c{i}", "content": f"Task {i}", "status": "pending", "parent_id": "group"}
            for i in range(total)
        ]
    )

    card = render_feishu_progress_card(tracker.snapshot(), language="en", tool_progress_mode="off")
    lines = _todo_lines(card)
    rendered = _rendered(card)

    assert f"TODO - 0 / {total} (0%)" in rendered
    assert _group_line(card, "Release gate") == f"📂 Release gate 0/{total}"
    assert f"  … {hidden} more in this group" in lines
    assert f"… {hidden} more tasks not shown" in lines
    assert "未展示" not in rendered


def test_feishu_progress_card_english_overflow_uses_singular_copy():
    from gateway.progress.renderers import render_feishu_progress_card
    from gateway.progress.todo_display import MAX_VISIBLE_TODO_LEAVES

    tracker = ProgressTracker(transaction_id="tx-todo-overflow-en-one")
    tracker.update_todo_items([
        {"id": str(i), "content": f"Task {i}", "status": "pending"}
        for i in range(MAX_VISIBLE_TODO_LEAVES + 1)
    ])

    card = render_feishu_progress_card(tracker.snapshot(), language="en", tool_progress_mode="off")

    assert "… 1 more task not shown" in _todo_lines(card)


def test_task_card_hides_archived_todos_and_shows_suspended_hint():
    from gateway.progress.renderers import render_feishu_progress_card
    from gateway.progress.todo_lifecycle import make_owner_scope_ref

    owner = make_owner_scope_ref(
        profile="default",
        platform="feishu",
        conversation_id="raw-chat-id-a",
        user_id="raw-user-id-a",
    )
    fake_key = "sk-" + "test-" + ("d" * 32)
    tracker = ProgressTracker(transaction_id="tx-archived")
    tracker.update_todo_items([
        {"id": "old", "content": f"旧待办 {fake_key}", "status": "pending"},
    ])
    tracker.update_todo_lifecycle(
        {
            "state": "archived",
            "completed_count": 1,
            "remaining_count": 0,
            "owner_scope_ref": owner,
        }
    )
    tracker.update_suspended_todo_hint(
        {
            "transaction_id": "tx-suspended",
            "title": "等待 CI：/data/agents/workspace/report.md",
            "reason": "waiting_external",
            "remaining_count": 1,
            "next_action": "继续上一任务 via /api/progress",
            "owner_scope_ref": owner,
        }
    )

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    assert "待办" not in rendered
    assert "旧待办" not in rendered
    assert "挂起事项" in rendered
    assert "等待 CI" in rendered
    assert "/data/agents/workspace/report.md" in rendered
    assert "/api/progress" in rendered
    assert fake_key not in rendered


def test_feishu_progress_card_running_shape_uses_safe_operation_labels():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-1")
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
    assert "任务 ID" in rendered
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
    assert "任务 ID：" in rendered
    assert "状态：" in rendered
    assert "耗时：" in rendered
    assert "上下文：" in rendered
    assert "自动压缩 4 次" in rendered
    assert "**最近操作**" in rendered
    assert "最近操作：" not in rendered
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

    tracker = ProgressTracker(transaction_id="tx-en")
    tracker.record_tool_started("read_file", "gateway/progress/renderers.py")

    assert detect_feishu_progress_card_language("Review Feishu card layout", configured="auto") == "en"
    assert detect_feishu_progress_card_language("评估飞书卡片", configured="auto") == "zh"
    assert detect_feishu_progress_card_language("评估飞书卡片", configured="en") == "en"
    assert (
        detect_feishu_progress_card_language(
            "OK",
            configured="auto",
            context_messages=[{"role": "user", "content": "继续优化飞书任务工作台卡片"}],
        )
        == "zh"
    )
    assert (
        detect_feishu_progress_card_language(
            "OK",
            configured="auto",
            context_messages=[{"role": "user", "content": "Review Feishu card layout"}],
        )
        == "en"
    )
    assert (
        detect_feishu_progress_card_language(
            "批准",
            configured="auto",
            context_messages=[{"role": "user", "content": "Review Feishu card layout"}],
        )
        == "en"
    )

    card = render_feishu_progress_card(tracker.snapshot(), language="en")
    rendered = _rendered(card)

    assert "Task Workbench" in card["header"]["title"]["content"]
    assert "Task ID:" in rendered
    assert "Status:" in rendered
    assert "**Recent operations**" in rendered
    assert "Recent operations:" not in rendered
    assert "任务工作台" not in rendered
    assert "最近操作" not in rendered


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

    tracker = ProgressTracker(transaction_id="tx-1")
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

    tracker = ProgressTracker(transaction_id="tx-1")
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

    tracker = ProgressTracker(transaction_id="tx-context")
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

    tracker = ProgressTracker(transaction_id="tx-rounds")
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

    tracker = ProgressTracker(transaction_id="tx-rounds-empty")
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


@pytest.mark.parametrize(
    ("reasoning_effort", "service_tier", "expected"),
    [
        ("xhigh", "fast", "gpt-5.6-terra · xhigh · fast"),
        ("xhigh", "default", "gpt-5.6-terra · xhigh"),
        ("custom-effort", "", "gpt-5.6-terra · custom-effort"),
        (None, None, "gpt-5.6-terra"),
    ],
)
def test_feishu_progress_card_appends_configured_reasoning_and_fast_mode(
    reasoning_effort,
    service_tier,
    expected,
):
    from gateway.progress.events import TransactionSnapshot
    from gateway.progress.renderers import render_feishu_progress_card

    snapshot = TransactionSnapshot(
        transaction_id="tx-model-config",
        status="running",
        started_at=10.0,
        updated_at=11.0,
        model_display="gpt-5.6-terra",
        reasoning_effort_display=reasoning_effort,
        service_tier_display=service_tier,
    )

    card = render_feishu_progress_card(snapshot, tool_progress_mode="off")
    details = card["elements"][0]["content"].replace("\\", "")

    assert expected in details


def test_feishu_progress_card_omits_absent_model_and_account_limits():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-no-metadata")

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

    tracker = ProgressTracker(transaction_id="tx-context-empty")
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

    peak_tracker = ProgressTracker(transaction_id="tx-peak-only")
    peak_tracker.update_context_usage(current_tokens=0, context_window=128_000, peak_tokens=65_536)
    compression_tracker = ProgressTracker(transaction_id="tx-compress-only")
    compression_tracker.update_context_usage(current_tokens=0, context_window=128_000, compression_count=2)

    peak_rendered = _rendered(render_feishu_progress_card(peak_tracker.snapshot(), tool_progress_mode="off"))
    compression_rendered = _rendered(render_feishu_progress_card(compression_tracker.snapshot(), tool_progress_mode="off"))

    assert "峰值 65,536" in peak_rendered
    assert "压缩 2 次" in compression_rendered
    assert "0 / 128,000" not in peak_rendered
    assert "0 / 128,000" not in compression_rendered


def test_feishu_progress_card_sanitizes_dashboard_link():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-1")

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

    tracker = ProgressTracker(transaction_id="tx-1")
    tracker.record_tool_started("terminal", "python /tmp/hidden.py --secret value")

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    rendered = _rendered(card)

    assert "任务 ID" in rendered
    assert "terminal" not in rendered
    assert "hidden.py" not in rendered
    assert "--secret" not in rendered


def test_feishu_progress_card_displays_skill_view_skill_name_not_tool_name():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-skill")
    tracker.record_tool_started("skill_view", "weather-query", {"name": "weather-query"})

    card = render_feishu_progress_card(tracker.snapshot())
    rendered = _rendered(card)

    assert "技能：weather-query" in rendered
    assert "skill_view" not in rendered


def test_feishu_progress_card_allows_categorized_skill_name_without_raw_args():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-skill-category")
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

    tracker = ProgressTracker(transaction_id="tx-skill-unsafe")
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
        tracker = ProgressTracker(transaction_id=f"tx-{unsafe_name}")
        tracker.record_tool_started("skill_view", unsafe_name, {"name": unsafe_name})

        card = render_feishu_progress_card(tracker.snapshot())
        rendered = _rendered(card)

        assert f"技能：{unsafe_name}" not in rendered


def test_feishu_progress_card_rejects_token_shaped_skill_names():
    from gateway.progress.renderers import render_feishu_progress_card

    for unsafe_name in ("sk-live-supersecret", "ghp_supersecrettoken", "xoxb-supersecrettoken"):
        tracker = ProgressTracker(transaction_id=f"tx-{unsafe_name}")
        tracker.record_tool_started("skill_view", unsafe_name, {"name": unsafe_name})

        card = render_feishu_progress_card(tracker.snapshot())
        rendered = _rendered(card)

        assert unsafe_name not in rendered


def test_feishu_progress_card_prefers_skill_args_over_preview():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-skill-args")
    tracker.record_tool_started("skill_view", "unsafe-preview", {"name": "weather-query"})

    card = render_feishu_progress_card(tracker.snapshot())
    rendered = _rendered(card)

    assert "技能：weather-query" in rendered
    assert "unsafe-preview" not in rendered


def test_feishu_progress_card_does_not_use_completed_skill_output_as_name():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-skill-completed")
    tracker.record_tool_started("skill_view", "weather-query", {"name": "weather-query"})
    tracker.record_tool_completed("skill_view", duration=0.25, preview="software-development/plan")

    card = render_feishu_progress_card(tracker.snapshot())
    rendered = _rendered(card)

    assert "技能：weather-query" in rendered
    assert "software-development/plan" not in rendered


def test_feishu_progress_card_extracts_completed_skill_name_from_json_args_preview_with_null():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-skill-json-null")
    tracker.record_tool_started("skill_view", "weather-query", {"name": "weather-query", "file_path": None})
    tracker.record_tool_completed("skill_view", duration=0.1)

    card = render_feishu_progress_card(tracker.snapshot())
    rendered = _rendered(card)

    assert "技能：weather-query" in rendered
    assert "skill_view" not in rendered
    assert "file_path" not in rendered


def test_feishu_progress_card_does_not_derive_command_name_from_raw_output_preview():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-raw-output")
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


def test_feishu_progress_card_sanitizes_non_string_options():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-options")

    card = render_feishu_progress_card(
        tracker.snapshot(),
        tool_progress_mode=object(),
        style=object(),
        dashboard_url="javascript:alert(1)",
    )
    rendered = _rendered(card)

    assert "javascript:" not in rendered
    assert "任务 ID" in rendered


def test_feishu_progress_card_does_not_scan_non_terminal_previews_for_scripts():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="tx-subagent")
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

    tracker = ProgressTracker(transaction_id="tx-argument")
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

    tracker = ProgressTracker(transaction_id="tx-nested-command")
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

    tracker = ProgressTracker(transaction_id="tx-interpreter-option")
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

    assert "🆔 任务 ID" in rendered
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

    assert "🆔 Task ID" in rendered
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


def test_feishu_progress_card_shows_canonical_task_id_without_task_summary():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="sess-feishu-task-id-1")

    card = render_feishu_progress_card(tracker.snapshot(), tool_progress_mode="off")
    details = card["elements"][0]["content"]
    rendered = _rendered(card)

    assert "**🆔 任务 ID：**" in details
    # Full canonical transaction id, feishu-markdown-escaped.
    assert "sess\\-feishu\\-task\\-id\\-1" in details
    assert "📌" not in rendered


def test_feishu_progress_card_shows_canonical_task_id_with_english_label():
    from gateway.progress.renderers import render_feishu_progress_card

    tracker = ProgressTracker(transaction_id="sess-feishu-task-id-en")

    card = render_feishu_progress_card(tracker.snapshot(), language="en", tool_progress_mode="off")
    details = card["elements"][0]["content"]
    rendered = _rendered(card)

    assert "**🆔 Task ID:**" in details
    assert "sess\\-feishu\\-task\\-id\\-en" in details
    assert "📌" not in rendered
    assert "任务 ID" not in rendered
