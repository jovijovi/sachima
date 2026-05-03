# Task Title No Raw Fallback Dev Log

## Timestamp

- Started: 2026-05-03 09:53:04 CST +0800

## Goal

Ensure user-facing progress/transaction card `任务` titles never fall back to raw user text with a cosmetic prefix such as `处理请求：...` or `Handle request: ...`.

## Root Cause

`gateway/progress/task_titles.py` had generic fallbacks that returned:

- `处理请求：{stripped}` for Chinese requests with no high-confidence rewrite.
- `Handle request: {main}` for English requests with no high-confidence rewrite.

That preserved the raw user sentence almost verbatim and violated the intended transaction-title contract: high-density intent summary, not raw input.

## TDD Evidence

RED command:

```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest tests/gateway/progress/test_task_titles.py -q
```

Expected RED result observed:

```text
4 failed, 15 passed
```

Failures covered:

- `需要更新代码吗？还是怎么着？` -> should become `评估是否需要更新代码并给出处理建议`.
- `现在你在使用什么模型？思考强度是多少？` -> should become `说明当前模型与思考强度配置`.
- Bug report about raw task fields -> should become a fix-oriented summary preserving multilingual/semantic-density constraints.
- English `Handle request:` fallback should not remain for Okta/OKR-style inputs.

GREEN command:

```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest tests/gateway/progress/test_task_titles.py -q
```

GREEN result:

```text
19 passed
```

## Implementation

Low-intrusion changes only:

- `gateway/progress/task_titles.py`
  - Adds high-confidence Chinese rewrites for model/reasoning questions, update-code decision questions, workflow-writing questions, and task-field bug reports.
  - Replaces raw Chinese fallback with `提炼并处理用户意图` when no safer semantic summary exists.
  - Replaces English `Handle request:` fallback with lightweight intent rewrites such as investigation/failure summaries and progress summaries; unknown English falls back to `Summarize user intent`.
- `tests/gateway/progress/test_task_titles.py`
  - Adds regressions for raw-with-prefix fallback leakage.
- `tests/gateway/test_run_progress_topics.py`
  - Updates a legacy assertion that expected the raw `hello` message in a progress panel.

No changes to:

- `gateway/run.py`
- Hermes core conversation loop
- platform adapters
- rich-result/weather paths

## Verification

Related progress suite command:

```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest \
  tests/gateway/progress/test_task_titles.py \
  tests/gateway/test_progress_tracker.py \
  tests/gateway/test_progress_renderer.py \
  tests/gateway/test_progress_redaction.py \
  tests/gateway/test_progress_reader.py \
  tests/gateway/test_progress_store.py \
  tests/gateway/test_feishu_progress_cards.py \
  tests/gateway/test_run_progress_topics.py \
  -q
```

Result after reviewer-blocker fixes:

```text
138 passed
```

Additional gates:

```text
py_compile: passed
git diff --check: passed
added-line security scan: security_scan_clean
```

## Reviewer Blocker Loop

Independent reviewer #1 found one real blocker: the first implementation rewrote `需要更新代码吗？不要修改账单代码` as `评估是否需要更新代码并给出处理建议`, dropping the negative constraint.

Added RED regression:

```text
test_generic_chinese_question_preserves_negative_constraint
```

Observed RED:

```text
1 failed
```

Fix: handle Chinese negative constraints before fallback rewrites, then apply the best base intent summary to the main clause and append `；约束：...`.

Independent reviewer #2 found the same class of issue for English question-style fallbacks: `Do we need to update code? Do not touch billing code` collapsed to `Summarize user intent`.

Added RED regression:

```text
test_generic_english_question_preserves_negative_constraint
```

Observed RED:

```text
1 failed
```

Fix: split English sentence-level constraints (`Do not...`, `without...`, etc.) before fallback rewriting and summarize `Do we need to update code?` as `Assess whether code updates are needed`.

Independent reviewer #3 found two remaining blockers:

- simple action requests could still return exact raw text, e.g. `Fix bug` -> `Fix bug`, `检查数据库连接超时问题` -> `检查数据库连接超时问题`;
- inline English `without` constraints could still be lost, e.g. `Do we need to update code without changing billing code`.

Added RED regressions:

```text
test_generic_english_question_preserves_inline_without_constraint
test_simple_english_action_request_is_not_exact_raw_text
test_simple_chinese_action_request_is_not_exact_raw_text
```

Observed RED:

```text
3 failed
```

Fix: rewrite simple action-led Chinese and English requests by extracting the action/object and using an intent verb (`检查...` -> `排查...`, `Fix bug` -> `Resolve bug`), and split inline English `without` constraints before base-intent rewriting.

Self-probe found one additional regression before the final review loop: product terms like `天气卡` were still treated as weather queries because Chinese weather detection matched the substring `天气`.

Added RED regression:

```text
test_chinese_weather_detection_does_not_match_weather_card_product_terms
```

Observed RED:

```text
1 failed
```

Fix: exclude known weather-card product/display terms (`天气卡`, `天气信息卡`, `天气富卡`, `天气交互卡`) from weather-query rewriting, letting the generic intent/constraint path summarize them.

Independent reviewer #4 found two more blockers:

- non-Chinese/non-ASCII scripts could still fall through to exact raw text, e.g. Russian/Arabic prompts;
- English modal wrappers and inline constraints could lose action/object or remain raw-ish, e.g. `Can you fix the login bug without changing billing code?`.

Added RED regressions:

```text
test_generic_english_modal_request_preserves_action_object_and_constraint
test_generic_english_modal_multi_action_request_rewrites_modal_wrapper
test_non_latin_multilingual_request_never_returns_raw_text
```

Observed RED:

```text
3 failed
```

Fix: strip English modal wrappers (`can/could/would/will you`), route changed English mains through action rewriting instead of returning them directly, strip inline constraint punctuation, and replace final unknown-script fallback with a non-raw multilingual summary.

Independent reviewer #5 found one remaining exact-raw path in the `优化点` + `任务` progress-summary branch, e.g. `这个任务还有优化点` returned exact raw text.

Added RED regressions:

```text
test_generic_task_optimization_point_is_not_exact_raw_text
test_generic_task_optimization_point_preserves_specific_content
```

Observed RED:

```text
2 failed
```

Fix: make the generic task-optimization branch return `梳理任务优化点` or `梳理任务优化点：<detail>` when trimming does not materially rewrite the user input.

Focused GREEN after fixes:

```text
30 passed
```

## Reflection: Missed Coverage

PR #12 tested complex multilingual summaries and several domain-specific rewrites, but it did not include short generic user questions where the generic fallback was effectively raw text with a prefix. This PR adds those exact regressions, updates the legacy progress-panel test that still expected `hello` in the task title, and adds reviewer-discovered coverage for constraint preservation in question-style fallbacks.
