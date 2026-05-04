---
name: progress-feedback-policy
description: Use when deciding how FlowWeaver-style transactions should expose sanitized progress snapshots, partial failures, approval waits, and user-visible ordering.
version: 0.1.0
author: Sachima FlowWeaver Phase 3
license: MIT
metadata:
  hermes:
    tags: [flowweaver, progress, snapshots, user-facing]
    phase: 3
---

# Progress Feedback Policy

Use this skill when a task is long, multi-intent, approval-gated, or produces multiple visible surfaces.

## Display Principle

A progress snapshot is a user-facing surface. It must be useful, ordered, bounded, and sanitized.

```text
safe snapshot != backend log
```

## When To Show Progress

Show a progress snapshot when at least one is true:

1. The turn has multiple intents and may deliver mixed surfaces.
2. One intent depends on another.
3. The task has an approval wait or clarifying-question wait.
4. The task may be long-running, multi-step, or PR/workflow-like.
5. Partial success/failure needs to remain visible.

Skip progress snapshots for simple one-shot requests unless the platform already emits a lightweight task tracker.

## Snapshot Shape

A FlowWeaver snapshot should include:

```json
{
  "snapshot_id": "snap_...",
  "transaction_id": "tx_...",
  "status": "running",
  "safe_to_render": true,
  "ordered_intent_ids": ["weather_today", "current_time"],
  "progress": [
    {"intent_id": "weather_today", "status": "succeeded", "summary": "Weather card delivered."},
    {"intent_id": "current_time", "status": "running", "summary": "Checking current time."}
  ],
  "render_text": "1 of 2 intents complete.",
  "bounds": {"max_progress_items": 10, "max_render_text_chars": 1200}
}
```

## Rendering Rules

1. Preserve the user's intent order in visible progress.
2. Show dependencies only when they affect what is waiting.
3. Distinguish `blocked` from `failed`; blocked means waiting for user/approval/clarification.
4. Partial failure should not erase successes.
5. Completion requires explicit final state; do not leave a snapshot at `running`.
6. Display-fit truncation is the last line of defense, not the summarization strategy.
7. Titles/summaries should be faithful intent summaries, not raw user text.

## Redaction Rules

Never render raw:

- authorization headers;
- tokens/API keys/passwords/secrets;
- URL query secrets;
- full shell commands with secret-bearing args;
- raw command output/logs/diffs;
- Feishu interactive card JSON;
- unbounded model transcripts.

If something is necessary for debugging but unsafe for IM, store it in backend logs or a later Claim Check reference, not in the progress snapshot.

## Failure/Blocked Examples

Partial failure:

```text
✅ 查询当前时间
❌ 查询磁盘空间失败：权限不足
✅ 查询天气完成
```

Approval wait:

```text
✅ 分析代码问题
✅ 生成执行计划
⏳ 等待用户批准后再改代码
```

Ambiguity wait:

```text
⏳ 等待澄清：需要确认目标仓库或部署环境
```

## Gateway Boundary

Gateway owns platform rendering and delivery ACK. Skills and mock orchestrators may prepare sanitized snapshots, but they must not call Feishu SDKs or claim delivery success.
