# Transaction Intent Summary Dev Log

**Date:** 2026-05-02
**Branch:** `feature/transaction-intent-summary`
**Plan:** `docs/plans/2026-05-02-transaction-intent-summary.md`

## Requirement

狗哥指出 Feishu/Sachima 事务信息卡里的“任务”字段不应直接显示用户原文，而应显示用户意图摘要。后续补充要求：摘要文字长度不要限制过短，尤其多语言场景；核心目标是把事情说清楚、语义密度尽可能大、信息损失小、信息熵增小。

## Design

First slice intentionally keeps侵入性小：

- Add one small helper module: `gateway/progress/task_titles.py`.
- Change one title source line in `gateway/run.py` from raw first-line slicing to `summarize_task_intent(message)`.
- Leave progress tracker dataclasses and renderers structurally unchanged.
- No extra LLM call: progress titles are needed before the agent run completes, and adding a model call would add latency/cost/failure modes.

The helper is conservative and deterministic:

1. Convert message-like input to text.
2. Normalize whitespace.
3. Remove high-confidence conversational noise such as retry/greeting wrappers.
4. Apply narrow high-confidence intent rewrites for common weather queries and this transaction-summary UX requirement.
5. Preserve original sanitized text when uncertain instead of over-compressing.
6. Run existing `sanitize_for_progress` as the final user-facing safety gate.

## TDD Evidence

### RED

`python -m pytest tests/gateway/progress/test_task_titles.py -q`

Failed as expected because `gateway.progress.task_titles` did not exist.

Integration RED:

`python -m pytest tests/gateway/test_run_progress_topics.py::test_task_tracker_uses_intent_summary_instead_of_raw_user_text tests/gateway/test_run_progress_topics.py::test_feishu_task_tracker_card_uses_semantic_intent_title -q`

Failed on the text tracker because the rendered panel still contained raw `再试一次。今晚下雨吗？`.

### GREEN

After implementation:

- `tests/gateway/progress/test_task_titles.py`: passed.
- Two integration title tests: passed.
- Feishu renderer dense multilingual-title preservation test: passed without renderer code changes.

## Security / Hardening

Added coverage for URL query secret redaction in task titles using a concrete secret-shaped value. The title helper uses the same existing progress redaction stack, so it inherits structured/text redaction behavior and bounded output.

## Independent Review Fixes

An independent reviewer found concrete issues in the first pass:

- weather rewrites dropped explicit locations such as `上海` / `Paris`;
- weather rewrites added unrequested `出行建议`;
- leading-noise stripping corrupted `请假流程` by removing `请`;
- generic requests were too close to raw phrasing;
- Feishu/text renderers still had shorter title caps than the new summary budget.

Fixes added:

- preserve explicit Chinese and English weather locations;
- only include travel/advice wording when the user asks for advice/umbrella/travel/wear guidance;
- remove unsafe standalone `请` stripping and use safer phrases like `请问` / `请帮我`;
- add a conservative generic English compression for `fix X and add Y, but Z` style requests while preserving constraints;
- raise progress title renderer caps to 320 chars to match the summary helper's bounded display budget.

A second independent review found more weather-detection edge cases:

- English substring matching treated `train`/`Brainstorm` as `rain`;
- Chinese matching treated non-weather `雨` words such as `雨果` as weather;
- location-after-time phrasing such as `明天上海会下雨吗？` lost the location.

Second-pass fixes added word-boundary English weather matching, removed broad single-character `雨` detection, and added location extraction for both location-before-time and time-before-location Chinese patterns.

A third independent review found one remaining English weather edge case: once a message entered the English weather rewrite via `weather`, the inner rain branch still used substring matching, so `weather for my train in Paris tomorrow` became `Check rain...`. The fix now uses word-boundary rain/weather/advice predicates consistently inside the rewrite path, with a regression test for `train`.

A fourth independent review found the remaining core acceptance gap: generic non-weather/non-special-case requests could still return sanitized raw text unchanged. The fix adds a small deterministic generic fallback:

- English requests split common `and <action>` clauses and `but <constraint>` clauses into intent-style statements;
- Chinese requests strip only safe `请<known action>` prefixes, preserve words like `请假`, and split `不要/不能/避免/...` constraints into `约束：...`;
- otherwise the fallback adds a neutral intent wrapper instead of returning raw text exactly.

A final blocker review found that the `ok`/`okay` conversational-noise regex could corrupt legitimate English names/acronyms such as `Okta` and `OKR`. The noise stripping now requires standalone English tokens for `ok`/`okay`/`please`, with regression coverage for Okta SSO and OKR progress summaries.

## Invasiveness Review

Production changes are deliberately small:

- New module: `gateway/progress/task_titles.py`.
- One import + one helper call in `gateway/run.py`.
- No changes to core `AIAgent`, provider adapters, tool execution, progress event model, or Feishu adapter.
- No renderer behavior change unless tests later prove necessary.

## Reflection

The initial “8–20 Chinese chars” idea was wrong. It would have optimized for shortness instead of semantic fidelity. For multilingual, constraint-heavy requests, a task title should be a high-density task statement with enough room to preserve the user's constraints. Truncation is a display-safety fallback, not the product goal.
