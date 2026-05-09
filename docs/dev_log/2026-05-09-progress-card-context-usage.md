# 2026-05-09 — Progress card context usage

## Summary

Added sanitized context-usage telemetry to gateway transaction progress snapshots and Feishu/text renderers:

- ProgressTracker snapshots can carry current prompt tokens, model context window, peak prompt tokens, compression count, and compression threshold.
- Feishu task-tracker cards and text fallback show compact context usage when current token usage is known.
- Peak-only or compression-only states do not render a misleading `0 / window` current-usage ratio.
- Jsonl progress event persistence and dashboard reader preserve sanitized context_usage.
- ContextCompressor tracks a monotonic peak_prompt_tokens counter per session.
- Gateway final progress flush refreshes context usage from the live agent before rendering the completed card.

## User-facing behavior

When available, the Feishu transaction card shows a compact line like:

```text
上下文：40,960 / 128,000（32.0%） · 峰值 65,536 · 压缩 2 次
```

The "完整调用链已记录，飞书只显示摘要。" footer refers to sanitized progress event persistence when `display.task_tracker.persist_events=true`. With the current default JSONL store and no explicit path override, that file is:

```text
~/.hermes/progress/events.jsonl
```

## Verification

```text
scripts/run_tests.sh \
  tests/gateway/test_progress_tracker.py \
  tests/gateway/test_progress_renderer.py \
  tests/gateway/test_feishu_progress_cards.py \
  tests/gateway/test_progress_store.py \
  tests/gateway/test_progress_reader.py \
  tests/gateway/test_run_progress_topics.py \
  tests/run_agent/test_context_token_tracking.py -q
# 131 passed

python -m py_compile \
  gateway/progress/events.py \
  gateway/progress/tracker.py \
  gateway/progress/renderers.py \
  gateway/progress/store.py \
  gateway/progress/reader.py \
  gateway/run.py \
  agent/context_compressor.py \
  tests/gateway/test_progress_tracker.py \
  tests/gateway/test_progress_renderer.py \
  tests/gateway/test_feishu_progress_cards.py \
  tests/gateway/test_progress_store.py \
  tests/gateway/test_progress_reader.py \
  tests/gateway/test_run_progress_topics.py \
  tests/run_agent/test_context_token_tracking.py
# passed

git diff --check
# passed

added-line static scan
# findings=[]
```

Independent blocker review passed after fixing the partial-context rendering issue.
