# FlowWeaver Phase 1 — Rich Card / Final Text Delivery Surfaces

Started: 2026-05-03 19:42:06 CST +0800
Branch: `fix/flowweaver-delivery-surfaces`
Base: `origin/feature/sachima-channel` at `602092219`

## Goal

Fix the Gateway delivery semantic bug where a successful weather rich card marks the whole turn as `already_sent`, causing ordinary final text for mixed-intent requests to be skipped.

Core invariant:

```text
rich card sent != final text sent
```

## TDD Evidence

### RED

Command:

```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest \
  tests/gateway/test_run_rich_weather.py::test_gateway_weather_rich_result_records_feishu_card_without_marking_final_text_sent \
  tests/gateway/test_run_rich_weather.py::test_gateway_weather_rich_result_sends_card_for_direct_helper_without_format \
  tests/gateway/test_run_rich_weather.py::test_gateway_weather_rich_result_keeps_mixed_final_text_when_card_sent -q
```

Result before implementation:

```text
3 failed
```

Expected failure: `agent_result["already_sent"]` was `True` after weather card delivery.

### GREEN

Minimal change in `gateway/run.py`:

- no longer set `agent_result["already_sent"] = True` when a weather card is sent;
- record rich card delivery separately in `agent_result["rich_cards_sent"]`.

Command after implementation:

```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest \
  tests/gateway/test_run_rich_weather.py::test_gateway_weather_rich_result_records_feishu_card_without_marking_final_text_sent \
  tests/gateway/test_run_rich_weather.py::test_gateway_weather_rich_result_sends_card_for_direct_helper_without_format \
  tests/gateway/test_run_rich_weather.py::test_gateway_weather_rich_result_keeps_mixed_final_text_when_card_sent -q
```

Result:

```text
3 passed
```

Focused suite:

```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest tests/gateway/test_run_rich_weather.py -q
```

Result:

```text
8 passed
```

## Changed Files

- `gateway/run.py`
- `tests/gateway/test_run_rich_weather.py`
- `docs/dev_log/2026-05-03-flowweaver-delivery-surfaces.md`

## Additional Verification

Progress topic + syntax/check chain:

```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest tests/gateway/test_run_progress_topics.py -q
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m py_compile gateway/run.py gateway/rich_results.py tests/gateway/test_run_rich_weather.py
git diff --check
# added-line security/dangerous-code scan
```

Result:

```text
39 passed
verification_chain_passed
```

Broad gateway suite:

```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest tests/gateway -q
```

Result on this branch:

```text
5 failed, 3842 passed
```

The failures were outside this change area: API Server CORS default, WhatsApp connect/session guard tests, and agent cache teardown. A baseline run of the exact failing selectors against `/home/ubuntu/workspace/hermes/repo/sachima` on `feature/sachima-channel` also failed for existing unrelated selectors, confirming the broad gateway suite is not a clean gate in this environment.

## Review Evidence

Independent spec compliance review:

```text
PASS
```

Independent blocker/code-quality review:

```text
Verdict: APPROVED
Critical Issues: None
Important Issues: None
```

Non-blocking reviewer suggestions:

- optional malformed `rich_cards_sent` test;
- optional full background-delivery integration test.

Deferred rationale: Phase 1 intentionally keeps scope tiny and already proves the core bug at the seam that controls the downstream final-text skip path. These suggestions are good candidates for Phase 2 delivery-state hardening.

## Final Pre-Commit Verification

Command:

```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest \
  tests/gateway/test_run_rich_weather.py \
  tests/gateway/test_rich_weather_delivery.py \
  tests/gateway/test_run_progress_topics.py -q
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m py_compile \
  gateway/run.py gateway/rich_results.py tests/gateway/test_run_rich_weather.py
git diff --check
# added-line security/dangerous-code scan over unstaged diff
```

Result:

```text
52 passed
final_precommit_verification_passed
```

## PR

- URL: https://github.com/jovijovi/sachima/pull/15
- Base: `feature/sachima-channel`
- Head: `fix/flowweaver-delivery-surfaces`

## Remaining Verification

- none for Phase 1 PR creation

## Notes

This phase deliberately avoids Temporal and avoids a full DeliveryState class. The fix is intentionally low-intrusion: preserve the existing rich-result flow while separating rich-card delivery from final-text delivery.
