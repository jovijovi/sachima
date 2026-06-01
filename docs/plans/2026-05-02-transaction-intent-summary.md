# Transaction Intent Summary Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Replace raw user-message titles in transaction/task progress cards with sanitized, high-density intent summaries that preserve meaning across multilingual inputs.

**Architecture:** Add a small deterministic title-normalization helper for task tracker titles, then wire it into `GatewayRunner._run_agent()` where `_tracker_title` is currently derived from the raw message. Keep the first slice non-LLM and low-risk: clean conversational noise, preserve objects/scope/constraints, apply domain-specific high-confidence rewrites (weather/rain and explicit optimization/change requests), sanitize/redact before display, and use display-fit truncation only as a final safety cap. Renderers continue to display `snapshot.title`; Feishu/text card behavior stays unchanged except for title content.

**Tech Stack:** Python, pytest, Hermes gateway progress tracker/renderers, Feishu progress-card tests.

**Worktree:** `/home/ubuntu/workspace/hermes/worktrees/sachima/feature-transaction-intent-summary`

**Branch:** `feature/transaction-intent-summary`

**Requirements from 狗哥:**
- “任务”字段 must not be raw user text; it should be a user-intent summary.
- Summary length must not be artificially too short, especially for multilingual scenarios.
- Core goal: say the thing clearly, maximize semantic density, minimize information loss, and avoid adding new inferred information.
- Maintain progress display hardening: no secret leaks, no raw command/URL-token leakage, bounded output.

---

## Design Notes

### What “intent summary” means here

A transaction summary is a faithful compressed task statement, not a short label.

Priority order:
1. **Clarity:** explain the task well enough that the card can stand alone.
2. **Low semantic loss:** preserve action, object, scope, constraints, and expected output.
3. **Low semantic entropy increase:** do not invent new details that the user did not provide.
4. **Noise removal:** remove greetings, retry phrases, “OK/开始吧”, redundant punctuation, and meta chatter when safe.
5. **Safety:** redact secrets before rendering and bound the result for platform limits.

### Non-goals for this slice

- Do not add an extra LLM/API call to summarize the task. The tracker title is needed before the main agent finishes; a separate summarization call adds cost, latency, and failure modes.
- Do not try to fully understand arbitrary natural language. Use conservative deterministic normalization; when uncertain, preserve the sanitized user request instead of over-compressing.
- Do not change Feishu card layout in this slice; only improve the `任务` field content.

### Proposed helper API

Create `gateway/progress/task_titles.py`:

```python
from __future__ import annotations

import re
from typing import Any

from gateway.progress.redaction import sanitize_for_progress

_DEFAULT_MAX_TITLE_LEN = 320


def summarize_task_intent(message: Any, *, max_len: int = _DEFAULT_MAX_TITLE_LEN) -> str:
    """Return a safe, high-density transaction title for user-facing progress cards."""
    text = _message_to_text(message)
    text = _normalize_whitespace(text)
    text = _strip_conversational_noise(text)
    text = _rewrite_high_confidence_intent(text)
    text = sanitize_for_progress(text or "Task", max_len=max_len)
    return text or "Task"
```

Important: this helper is **not** an aggressive summarizer. It is a safe intent-title normalizer.

### Expected examples

| Input | Expected title direction |
|---|---|
| `再试一次。今晚下雨吗？` | `查询今晚降雨情况与出行建议` or similar, not raw text |
| `明天下雨吗？` | `查询明天降雨情况与出行建议` |
| `事务信息显示的效果，还有一些优化点：1、“任务”字段中内容不是用户的原文，应该是用户意图的摘要。` | `优化事务信息显示：将“任务”字段从用户原文改为用户意图摘要` |
| `事务摘要的文字长度不要限制过短，尤其是多语言场景中。核心目标是把事情说清楚，语义密度尽可能大，信息损失小，信息墒增小。` | `调整事务摘要策略：避免过短限制，在多语言场景中优先清晰、高语义密度、低信息损失与低信息熵增` |
| `Please review PR #12 for auth regressions without changing code` | preserve as a clear English task, e.g. `Review PR #12 for auth regressions without changing code` |
| `帮我 curl https://x.test?a=1&token=fake-secret 查一下` | no token leakage; token must be redacted |

---

## Task 1: Add intent-title helper with RED tests

**Objective:** Create focused tests that define the desired high-density, low-loss transaction title behavior before production code exists.

**Files:**
- Create: `tests/gateway/progress/test_task_titles.py`
- Create after RED: `gateway/progress/task_titles.py`

**Step 1: Write failing tests**

Create `tests/gateway/progress/test_task_titles.py` with cases:

```python
from gateway.progress.task_titles import summarize_task_intent


def test_weather_retry_question_becomes_intent_summary_not_raw_text():
    title = summarize_task_intent("再试一次。今晚下雨吗？")

    assert title != "再试一次。今晚下雨吗？"
    assert "今晚" in title
    assert "降雨" in title or "下雨" in title
    assert "再试一次" not in title


def test_multilingual_summary_preserves_constraints_without_too_short_cap():
    message = (
        "事务摘要的文字长度不要限制过短，尤其是多语言场景中。"
        "核心目标是把事情说清楚，语义密度尽可能大，信息损失小，信息熵增小。"
    )

    title = summarize_task_intent(message)

    assert len(title) > 40
    assert "多语言" in title
    assert "语义密度" in title
    assert "信息损失" in title
    assert "熵增" in title


def test_optimization_request_is_rephrased_as_task_intent():
    title = summarize_task_intent(
        "事务信息显示的效果，还有一些优化点：1、“任务”字段中内容不是用户的原文，应该是用户意图的摘要。"
    )

    assert title.startswith("优化事务")
    assert "任务" in title
    assert "用户意图摘要" in title
    assert "1、" not in title


def test_english_review_request_is_preserved_without_semantic_loss():
    title = summarize_task_intent("Please review PR #12 for auth regressions without changing code")

    assert "Review PR #12" in title or "review PR #12" in title
    assert "auth regressions" in title
    assert "without changing code" in title


def test_title_redacts_secrets_and_preserves_safe_context():
    title = summarize_task_intent("帮我检查 https://api.example.test/path?token=fake-secret&ok=1 的问题")

    assert "fake-secret" not in title
    assert "[REDACTED]" in title
    assert "api.example.test" in title
```

**Step 2: Run RED**

Run:

```bash
python -m pytest tests/gateway/progress/test_task_titles.py -q
```

Expected: FAIL due to missing `gateway.progress.task_titles`.

**Step 3: Implement minimal helper**

Create `gateway/progress/task_titles.py` with conservative behavior:
- convert multimodal/list content to text similarly to `_summarize_user_message_for_log` where useful;
- normalize whitespace;
- strip obvious leading filler/retry fragments (`再试一次`, `帮我`, `请`, `please`, `ok`, etc.) without deleting meaningful content;
- high-confidence Chinese weather rewrites preserving time words (`今晚`, `明天`, `现在`) and topic (`降雨/天气/带伞`);
- high-confidence optimization rewrites for `优化点`, `应该`, `不要限制过短`, etc.;
- sanitize with `sanitize_for_progress(max_len=320)` by default.

**Step 4: Run GREEN**

Run:

```bash
python -m pytest tests/gateway/progress/test_task_titles.py -q
```

Expected: PASS.

---

## Task 2: Wire intent title into task tracker setup

**Objective:** Use the new helper where task tracker titles are created instead of raw first-line slicing.

**Files:**
- Modify: `gateway/run.py:9507-9516`
- Test: `tests/gateway/test_run_progress_topics.py`

**Step 1: Add integration tests first**

Add focused tests near the existing task tracker panel tests:

```python
@pytest.mark.asyncio
async def test_task_tracker_uses_intent_summary_instead_of_raw_user_text(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        TransactionPanelAgent,
        message="再试一次。今晚下雨吗？",
        session_id="sess-task-tracker-intent-title",
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {"enabled": True, "mode": "text", "max_operations": 8},
            },
        },
    )

    all_panels = "\n".join([call["content"] for call in adapter.sent] + [call["content"] for call in adapter.edits])
    assert "再试一次。今晚下雨吗？" not in all_panels
    assert "今晚" in all_panels
    assert "降雨" in all_panels or "下雨" in all_panels


@pytest.mark.asyncio
async def test_feishu_task_tracker_card_uses_semantic_intent_title(monkeypatch, tmp_path):
    adapter, result = await _run_with_agent(
        monkeypatch,
        tmp_path,
        TransactionPanelAgent,
        message="事务摘要的文字长度不要限制过短，尤其是多语言场景中。核心目标是把事情说清楚，语义密度尽可能大，信息损失小，信息熵增小。",
        session_id="sess-feishu-intent-title",
        platform=Platform.FEISHU,
        chat_id="oc_1",
        chat_type="dm",
        adapter_cls=FeishuProgressCardCaptureAdapter,
        config_data={
            "display": {
                "tool_progress": "all",
                "task_tracker": {"enabled": True, "mode": "feishu_card", "max_operations": 8},
            },
        },
    )

    final_card = adapter.cards_patched[-1]["card"]
    rendered = json.dumps(final_card, ensure_ascii=False)
    assert "多语言" in rendered
    assert "语义密度" in rendered
    assert "信息损失" in rendered
    assert "熵增" in rendered
```

If `_run_with_agent` currently lacks a `message=` parameter, add a tiny test-helper extension instead of hardcoding in product code.

**Step 2: Run RED**

Run:

```bash
python -m pytest tests/gateway/test_run_progress_topics.py::test_task_tracker_uses_intent_summary_instead_of_raw_user_text tests/gateway/test_run_progress_topics.py::test_feishu_task_tracker_card_uses_semantic_intent_title -q
```

Expected: FAIL because raw text is still used.

**Step 3: Implement minimal wiring**

Change `gateway/run.py` around line 9511:

```python
from gateway.progress.task_titles import summarize_task_intent
_tracker_title = summarize_task_intent(message)
```

Keep fallback behavior inside helper; do not duplicate title slicing in `run.py`.

**Step 4: Run GREEN**

Run the same two integration tests. Expected: PASS.

---

## Task 3: Preserve renderer safety and display fit

**Objective:** Verify renderer truncation/redaction still protects the visible surfaces without imposing an artificially short task title.

**Files:**
- Modify if needed: `gateway/progress/renderers.py`
- Test: `tests/gateway/progress/test_renderers.py` or existing renderer test file

**Step 1: Add/extend renderer tests**

Add tests that construct a `TransactionSnapshot` with a long multilingual title and confirm:
- Feishu card contains key semantic terms before cap;
- title is not cut to 120 if that causes loss (this may require raising Feishu title sanitizer max from 120 to a safer value, e.g. 240);
- secrets are still redacted.

Example:

```python
def test_feishu_progress_card_preserves_dense_multilingual_task_title():
    snapshot = TransactionSnapshot(
        transaction_id="txn-1",
        title="调整事务摘要策略：避免过短限制，在多语言场景中优先保证清晰、高语义密度、低信息损失与低信息熵增",
        status="running",
        started_at=1.0,
        updated_at=1.0,
        completed_at=None,
        recent_operations=(),
    )

    card = render_feishu_progress_card(snapshot)
    rendered = json.dumps(card, ensure_ascii=False)

    assert "多语言" in rendered
    assert "语义密度" in rendered
    assert "信息损失" in rendered
    assert "熵增" in rendered
```

**Step 2: Run RED/GREEN**

Run focused renderer tests. If existing renderer cap passes, no product change needed. If it fails, increase only the title-specific cap in `render_feishu_progress_card()` from 120 to a still-bounded value such as 240 or 320, and keep `sanitize_for_progress` active.

---

## Task 4: Documentation and dev log

**Objective:** Record the UX rule and verification evidence for future work.

**Files:**
- Create: `docs/dev_log/2026-05-02-transaction-intent-summary.md`
- Optionally update: `docs/plans/2026-05-02-transaction-intent-summary.md` with final evidence after implementation

**Dev log must include:**
- Requirement summary from 狗哥.
- Why no extra LLM summarization call was added in first slice.
- Tests added and RED/GREEN evidence.
- Security checks: sanitizer still redacts secrets and renderer bounds output.
- Reflection: old fixed-short-title thinking would have caused semantic loss in multilingual cases.

---

## Verification Gate

Run before review/PR:

```bash
python -m pytest \
  tests/gateway/progress/test_task_titles.py \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/progress/test_renderers.py \
  -q
python -m py_compile \
  gateway/progress/task_titles.py \
  gateway/progress/renderers.py \
  gateway/run.py
git diff --check
```

Then run an independent review focused on:
- Secret leakage in task summaries.
- Over-compression / semantic loss.
- Hallucinated extra meaning.
- Feishu card/title rendering regressions.
- Whether tests actually fail before implementation.

---

## Approval Gate

Plan saved. Do **not** implement production code until 狗哥 approves this plan.
