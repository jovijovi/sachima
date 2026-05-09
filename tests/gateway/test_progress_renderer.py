"""Tests for gateway transaction progress text rendering."""

import json

from gateway.progress.tracker import ProgressTracker


def test_text_renderer_includes_transaction_status_and_tools():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-1", title="Fix bug")
    tracker.record_tool_started("read_file", "gateway/run.py", {"path": "gateway/run.py"})

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="all")

    assert "📌" in text
    assert "Fix bug" in text
    assert "Running" in text
    assert "Recent operations" in text
    assert "read_file" in text
    assert "gateway/run.py" in text


def test_text_renderer_hides_tools_when_progress_off():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-1", title="Quiet task")
    tracker.record_tool_started("terminal", "pytest", {"command": "pytest"})

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="off")

    assert "Quiet task" in text
    assert "terminal" not in text
    assert "pytest" not in text


def test_text_renderer_marks_failed_and_completed_operations():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-1", title="Run checks")
    tracker.record_tool_started("terminal", "pytest")
    tracker.record_tool_completed("terminal", duration=1.2, is_error=True)

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="all")

    assert "❌" in text
    assert "terminal" in text
    assert "1.20s" in text


def test_text_renderer_respects_new_mode_by_collapsing_repeated_tools():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-1", title="Repeated reads")
    tracker.record_tool_started("read_file", "a.py")
    tracker.record_tool_started("read_file", "b.py")
    tracker.record_tool_started("search_files", "pattern")

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="new")

    assert text.count("read_file") == 1
    assert "search_files" in text


def test_text_renderer_sanitizes_and_caps_output():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-1", title="Secret task")
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

    tracker = ProgressTracker(transaction_id="tx-1", title="No tools yet")

    text = render_text_panel(tracker.snapshot(), tool_progress_mode="all")

    assert "No tools yet" in text
    assert "No operations yet" in text


def test_text_renderer_includes_safe_dashboard_progress_link_when_configured():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-1", title="Dashboard task")

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

    tracker = ProgressTracker(transaction_id="tx-context", title="Context task")
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

    peak_tracker = ProgressTracker(transaction_id="tx-peak-only", title="Peak only")
    peak_tracker.update_context_usage(current_tokens=0, context_window=128_000, peak_tokens=65_536)
    compression_tracker = ProgressTracker(transaction_id="tx-compress-only", title="Compression only")
    compression_tracker.update_context_usage(current_tokens=0, context_window=128_000, compression_count=2)

    peak_text = render_text_panel(peak_tracker.snapshot(), tool_progress_mode="off")
    compression_text = render_text_panel(compression_tracker.snapshot(), tool_progress_mode="off")

    assert "peak 65,536" in peak_text
    assert "compressions 2" in compression_text
    assert "0 / 128,000" not in peak_text
    assert "0 / 128,000" not in compression_text


def test_text_renderer_omits_unsafe_dashboard_link():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-1", title="No unsafe link")

    text = render_text_panel(tracker.snapshot(), dashboard_url="javascript:alert('x')")

    assert "Dashboard" not in text
    assert "javascript:" not in text


def test_text_renderer_omits_dashboard_link_when_port_is_invalid():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-1", title="Bad port")

    for dashboard_url in ("http://example.local:bad", "http://example.local:99999"):
        text = render_text_panel(tracker.snapshot(), dashboard_url=dashboard_url)

        assert "Dashboard" not in text
        assert dashboard_url not in text


def test_text_renderer_preserves_ipv6_dashboard_host_brackets():
    from gateway.progress.renderers import render_text_panel

    tracker = ProgressTracker(transaction_id="tx-1", title="IPv6 link")

    text = render_text_panel(tracker.snapshot(), dashboard_url="http://[::1]:9119/base")

    assert "Dashboard" in text
    assert "http://[::1]:9119/base/progress" in text


def test_feishu_progress_card_preserves_dense_multilingual_task_title():
    from gateway.progress.renderers import render_feishu_progress_card

    title = (
        "调整事务摘要策略：避免过短限制，在多语言场景中优先保证清晰表达；保留用户提出的动作、对象、范围、"
        "关键约束和预期产物；支持中文、English、日本語、한국어 等混合输入；在不引入额外推断的前提下提高语义密度，"
        "并明确控制信息损失与信息熵增"
    )
    tracker = ProgressTracker(transaction_id="tx-1", title=title)

    card = render_feishu_progress_card(tracker.snapshot())
    rendered = json.dumps(card, ensure_ascii=False)

    assert "多语言" in rendered
    assert "语义密度" in rendered
    assert "信息损失" in rendered
    assert "信息熵增" in rendered
