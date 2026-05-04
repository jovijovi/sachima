---
name: multi-intent-planning
description: Use when a user message contains multiple requests, dependent subrequests, approval waits, or long workflow intent planning. Produces ordered FlowWeaver-style intent plans without starting orchestration.
version: 0.1.0
author: Sachima FlowWeaver Phase 3
license: MIT
metadata:
  hermes:
    tags: [flowweaver, multi-intent, planning, skills]
    phase: 3
---

# Multi-Intent Planning

Use this skill when one user turn contains more than one actionable request, a dependent synthesis request, or an explicit approval/wait instruction.

## Goal

Turn the user message into an ordered, low-loss intent plan:

```text
Transaction -> ordered Intent[] -> dependencies -> coverage expectation
```

Do not execute tools merely because you are planning. Planning identifies work; execution happens through the normal Hermes tool process and AI FLOW approval rules.

## Core Rules

1. Preserve user order unless a dependency requires later synthesis.
2. Do not over-split greetings, politeness, or filler.
3. Split independent actionable asks: time, weather, disk, code inspection, summary, send, compare, generate, etc.
4. Identify dependent synthesis as its own intent only when the user asks for comparison, recommendation, combined judgment, or final decision based on prior results.
5. Preserve constraints and output requirements in the intent title/notes.
6. Do not invent new goals, locations, formats, tools, or side effects.
7. If the user says “先计划/等我批准/不要改代码”, create a blocked approval/wait intent and do not proceed to implementation.
8. Ambiguity that changes which tool or side effect would run should become a clarifying-question intent, not a guessed plan.

## Intent Shape

Use this minimal shape when writing or validating plans:

```json
{
  "intent_id": "weather_today",
  "order_index": 0,
  "title": "查询今天的天气",
  "status": "pending",
  "dependencies": [],
  "notes": "Preserve requested location/date if provided."
}
```

Status vocabulary:

```text
pending | running | succeeded | failed | blocked | cancelled | skipped
```

## Examples

### Independent asks

User:

```text
现在几点了？今天天气怎样？当前磁盘空间剩余多少？明天天气怎样？
```

Plan:

```text
0 current_time — 查询当前时间
1 weather_today — 查询今天天气
2 disk_status — 查询当前磁盘剩余空间
3 weather_tomorrow — 查询明天天气
```

### Dependent synthesis

User:

```text
查今天和明天天气，比较哪天适合出门。
```

Plan:

```text
0 weather_today — 查询今天天气
1 weather_tomorrow — 查询明天天气
2 weather_compare — 比较两天天气并判断哪天更适合出门；depends on weather_today, weather_tomorrow
```

### Approval wait

User:

```text
先分析代码问题，给计划，等我批准后再改。
```

Plan:

```text
0 code_inspect — 分析代码问题
1 implementation_plan — 给出执行计划；depends on code_inspect
2 approval_wait — 等待用户批准后再改代码；blocked; depends on implementation_plan
```

## What Not To Do

- Do not start Temporal, Docker, services, Gateway restarts, commits, pushes, or PRs while only planning.
- Do not hide correlation IDs or contract markers in final user-visible text.
- Do not treat rich-card delivery as final-text coverage.
- Do not collapse partial failures into fake success.
