---
name: result-artifact-output-policy
description: Use when mapping tool results or workflow steps into FlowWeaver artifacts, final text coverage, and delivery records while keeping artifacts separate from platform delivery ACKs.
version: 0.1.0
author: Sachima FlowWeaver Phase 3
license: MIT
metadata:
  hermes:
    tags: [flowweaver, artifacts, delivery, output-policy]
    phase: 3
---

# Result Artifact Output Policy

Use this skill when a multi-intent turn produces intermediate or final results that need to be represented as artifacts and user-visible coverage.

## Core Distinction

```text
Operation attempted != Artifact generated != Delivery sent != Intent covered
```

Keep these separate. This is the whole point; don't mush it into soup.

## Minimal Records

### Operation

An operation records work attempted for an intent. It must not include platform delivery fields.

```json
{
  "operation_id": "op_weather_today_lookup",
  "intent_id": "weather_today",
  "kind": "weather_lookup",
  "status": "succeeded",
  "attempted_at": "...",
  "summary": "Looked up bounded weather data.",
  "inputs_summary": "Location/date only; no raw secret-bearing args."
}
```

### Artifact

An artifact records generated result data or fallback text. It must not imply delivery.

```json
{
  "artifact_id": "artifact_weather_today",
  "intent_id": "weather_today",
  "kind": "rich_card",
  "status": "succeeded",
  "title": "成都今晚天气",
  "content_summary": "今晚降雨概率较低，适合普通出行。",
  "covers_intent_ids": ["weather_today"],
  "data": {"condition": "cloudy"}
}
```

### Delivery ACK

Delivery ACK belongs to Gateway/platform success paths only. A normal agent-facing tool or skill must not claim that Feishu/Telegram/etc. delivered a message.

```json
{
  "delivery_idempotency_key": "feishu:om_example:rich_card:weather_today",
  "surface": "rich_card",
  "platform": "feishu",
  "status": "sent",
  "message_id": "om_example",
  "target": {"kind": "artifact", "id": "artifact_weather_today"},
  "reason": null
}
```

Target kinds:

```text
artifact | snapshot | final_text | transaction | intent
```

## Coverage Rules

Every user intent needs one explicit coverage outcome:

```text
answered | delivered_artifact | failed | skipped | blocked_waiting_for_user
```

- Use `delivered_artifact` only when a rich/media/file artifact has a confirmed delivery ACK.
- Use `answered` when final text or fallback text covers the intent.
- Use `blocked_waiting_for_user` for approval gates or clarifying questions.
- Use `failed` for actual failures; include a sanitized reason.
- Use `skipped` only when intentionally skipped; include a sanitized reason.

## Sanitization Rules

Artifacts, operation summaries, fallback text, and delivery reasons are user-facing surfaces. Redact before storing and again before rendering:

- headers and auth strings;
- URL query secrets;
- password/token/api-key/secret fields;
- raw commands and raw output;
- Feishu card JSON;
- full tool arguments;
- huge logs/diffs/prompts.

Use Claim Check references for large data in later phases. In Phase 3 examples, keep everything compact and fake.

## Hard Boundaries

- Rich cards are rendered by Gateway/platform code, not by skills.
- Delivery ACK is Gateway-owned.
- Final text coverage is explicit; a rich card does not automatically cover ordinary text answers.
- Do not start Temporal or route normal short requests through orchestration while using this skill.
