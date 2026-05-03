# FlowWeaver Phase 2 — Gateway Delivery Surface State Dev Log

**Timestamp:** 2026-05-03 22:00:08 CST +0800

**Branch:** `feat/gateway-render-plan-delivery-surfaces`

**Base:** `feature/sachima-channel` at `04d583dca`

**Worktree:** `/home/ubuntu/workspace/hermes/worktrees/sachima/feat-gateway-render-plan-delivery-surfaces`

**Plan:** `/home/ubuntu/workspace/hermes/.hermes/plans/2026-05-03_204308-flowweaver-phase2-renderplan-artifact-delivery.md`

## Goal

Make Gateway output-surface delivery semantics explicit and testable while keeping the change low-intrusion.

Core invariant:

```text
rich card sent != final text sent
```

## Low-Intrusion Boundaries

Honored boundaries:

- Did not touch `run_agent.py`.
- Did not introduce Temporal.
- Did not introduce DAG / orchestrator / renderer registry.
- Did not rewrite `gateway/run.py`.
- Kept legacy compatibility fields:
  - `agent_result["already_sent"]`
  - `agent_result["rich_cards_sent"]`

## Files Changed

- Create: `gateway/delivery_state.py`
- Create: `tests/gateway/test_delivery_state.py`
- Modify: `gateway/run.py`
- Modify: `tests/gateway/test_run_rich_weather.py`
- Modify: `tests/gateway/test_run_progress_topics.py`

## Implementation Summary

### Task 1 — Delivery state helper

Added `gateway/delivery_state.py` with:

- `ensure_delivery_state(agent_result)`
- `record_rich_card_sent(agent_result, *, result_type, message_id)`
- `mark_final_text_sent(agent_result, *, reason)`
- `should_skip_final_text(agent_result)`

Semantics:

- `delivery_state.final_text.sent=True` is the explicit final-text suppression state.
- `record_rich_card_sent()` records rich-card delivery without suppressing final text.
- `mark_final_text_sent()` requires an explicit reason and preserves `already_sent=True` compatibility.
- `should_skip_final_text()` is the caller-facing helper for final-send suppression checks.

### Task 2 — Weather rich-card delivery state

Replaced ad hoc weather `rich_cards_sent` mutation in `gateway/run.py` with `record_rich_card_sent(...)`.

Preserved Phase 1 behavior:

- weather card delivery does not set `already_sent=True`
- top-level `rich_cards_sent` remains available
- duplicate same-card records are idempotent

### Task 3 — Final text reasoned suppression

Replaced direct `response["already_sent"] = True` in the final suppression block with:

```python
mark_final_text_sent(
    response,
    reason="stream_final_response" if _streamed else "response_previewed",
)
```

This preserves legacy behavior while recording why final text was already delivered.

### Task 4 — Caller seam uses helper

Updated `_handle_message_with_agent` caller seam so final-send skip decisions use:

```python
should_skip_final_text(agent_result)
```

This centralizes the meaning of final-text delivery state while keeping media fallback behavior unchanged.

## TDD Evidence

### Task 1 RED / GREEN

- RED: `tests/gateway/test_delivery_state.py` initially failed because `gateway.delivery_state` did not exist.
- GREEN: `tests/gateway/test_delivery_state.py` passed after adding helper.
- Reviewer loop found and fixed:
  - explicit `final_text.reason` being overwritten by legacy normalization
  - unsanitized `media_sent`
  - nested sensitive-key containers in `media_sent`
  - scalar subclass secret-shaped `repr`
  - cyclic containers / unprintable keys

Final Task 1 focused result:

```text
12 passed
```

### Task 2 RED / GREEN

- RED: `test_gateway_weather_rich_result_records_feishu_card_without_marking_final_text_sent` failed with missing `delivery_state`.
- GREEN: weather rich-card tests and delivery-state tests passed.

Focused result:

```text
21 passed
```

### Task 3 RED / GREEN

- RED: `test_run_agent_previewed_final_marks_already_sent` failed with missing `delivery_state` reason.
- GREEN: previewed and streaming final-text tests recorded explicit reasons.

Focused result:

```text
14 passed
```

### Task 4 RED / GREEN

- RED: seam contract test failed because caller still read legacy `already_sent` directly.
- GREEN: caller seam uses `should_skip_final_text(agent_result)`.

Focused result:

```text
24 passed
```

## Verification

Final focused gate run:

```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest \
  tests/gateway/test_delivery_state.py \
  tests/gateway/test_run_rich_weather.py \
  tests/gateway/test_rich_weather_delivery.py \
  tests/gateway/test_duplicate_reply_suppression.py \
  tests/gateway/test_run_progress_topics.py -q
```

Result:

```text
88 passed in 8.08s
```

Compile / whitespace gate:

```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m py_compile \
  gateway/delivery_state.py \
  gateway/run.py \
  gateway/rich_results.py \
  tests/gateway/test_delivery_state.py \
  tests/gateway/test_run_rich_weather.py \
  tests/gateway/test_duplicate_reply_suppression.py \
  tests/gateway/test_run_progress_topics.py

git diff --check
```

Result: passed.

## Review Evidence

Per-task independent reviews were run:

- Task 1 spec review: `PASS` after redaction/idempotency fixes.
- Task 1 code quality/security review: `PASS` after nested media/scalar/cycle fixes.
- Task 2 spec review: `PASS`.
- Task 2 code quality/security review: `PASS`.
- Task 3 spec review: `PASS`.
- Task 3 code quality/security review: no blocker-level issues.
- Task 4 spec review: `PASS`.
- Task 4 code quality/security review: no blocker-level issues; minor test brittleness note was addressed by loosening the seam assertion.

Final staged reviews:

- Final spec compliance review: `PASS`.
- Final blocker-focused code quality/security review: `PASS`.
- Staged added-line secret scan: passed.
- `git diff --cached --check`: passed.

## Security Notes

- Tests use fake secret-shaped values only.
- `delivery_state` sanitizes final-text reasons, rich-card records, and structured `media_sent` records.
- No real API keys, tokens, passwords, credentials, or connection strings were added.

## Remaining Work

- Run final staged added-line security scan.
- Run final integration review.
- Commit and open PR against `feature/sachima-channel`.
- Do not restart gateway after merge unless 狗哥 explicitly authorizes it.
