# Dev Log — Feishu Task Card Retry + Compact Fallback Hotfix

Date: 2026-05-14
Branch: `fix/feishu-task-card-compact-fallback`
Base: `origin/feature/sachima-channel @ 7d93cfd74d15590e2c327f327a42b606d032c2b5`
Scope: Gateway Feishu task tracker card send/patch retry and compact fallback behavior.

## Approval

Dog Brother approved:

```text
approve_sachima_gateway_feishu_task_card_retry_compact_fallback_fix_allow_feishu_adapter_code_change_no_gateway_restart_no_prod_config_no_public_no_real_delivery
```

Approved scope:

- modify Sachima Gateway Feishu task tracker card fallback behavior;
- modify Feishu adapter code for retry/idempotency behavior;
- add regression tests for card-mode fallback and retry behavior;
- open a PR after local verification.

Still not approved:

```text
gateway_restart_or_reload
production_config_write
public_webhook_exposure
real_external_sachima_ingress
real_external_delivery
production_delivery_control
live_or_default_on_behavior
```

## Preflight

Read before changes:

- `GOAL.md`
- `AGENTS.md`
- `docs/roadmap/current-status.md`
- `docs/plans/2026-05-11-sachima-final-goal-phase-development-plan.md`
- `docs/dev_log/2026-05-13-sachima-envelope-v1-local-conformance-implementation.md`
- `docs/dev_log/2026-05-12-flowweaver-pe2a-controlled-runtime-fake-delivery.md`
- `docs/sachima-channel.md`

Current roadmap position at start:

```text
current_position: P4 Sachima-side local conformance implemented; agentic-ui/cross-repo conformance pending; live/public/real delivery not approved
```

This hotfix does not change roadmap phase state. `docs/roadmap/current-status.md` should remain unchanged unless later review finds the visible-progress hotfix must be tracked as a roadmap tail.

## TDD Log

RED command:

```text
./scripts/run_tests.sh \
  tests/gateway/test_run_progress_topics.py::test_feishu_task_tracker_card_mode_final_patch_failure_sends_compact_notice \
  tests/gateway/test_run_progress_topics.py::test_feishu_task_tracker_card_mode_initial_send_failure_sends_only_compact_notice \
  tests/gateway/test_run_progress_topics.py::test_feishu_task_tracker_card_mode_patch_failure_does_not_spam_chat \
  tests/gateway/test_feishu.py::TestFeishuAdapterMessaging::test_patch_interactive_card_retries_transient_failure \
  tests/gateway/test_feishu.py::TestAdapterBehavior::test_send_retries_transient_failure_with_stable_uuid \
  tests/gateway/test_feishu.py::TestAdapterBehavior::test_send_interactive_card_retry_uses_stable_uuid \
  -q
```

RED result:

```text
6 failed
```

Expected failures confirmed existing behavior:

- Feishu card-mode fallback sent the full text progress panel into ordinary chat;
- initial card-send failure produced multiple full text panel messages;
- patch failure sent full text panel content;
- `patch_interactive_card()` did not retry transient exceptions;
- send retry generated a fresh UUID per attempt.

Focused GREEN command:

```text
./scripts/run_tests.sh \
  tests/gateway/test_run_progress_topics.py::test_feishu_task_tracker_card_mode_final_patch_failure_sends_compact_notice \
  tests/gateway/test_run_progress_topics.py::test_feishu_task_tracker_card_mode_initial_send_failure_sends_only_compact_notice \
  tests/gateway/test_run_progress_topics.py::test_feishu_task_tracker_card_mode_patch_failure_does_not_spam_chat \
  tests/gateway/test_feishu.py::TestFeishuAdapterMessaging::test_patch_interactive_card_retries_transient_failure \
  tests/gateway/test_feishu.py::TestFeishuAdapterMessaging::test_patch_interactive_card_does_not_retry_structural_failure \
  tests/gateway/test_feishu.py::TestAdapterBehavior::test_send_retries_transient_failure_with_stable_uuid \
  tests/gateway/test_feishu.py::TestAdapterBehavior::test_send_interactive_card_retry_uses_stable_uuid \
  -q
```

Focused GREEN result:

```text
7 passed
```

## Implementation Summary

Current implementation candidate:

- `gateway/run.py`
  - Feishu `feishu_card` mode no longer falls back to full `render_text_panel()` content after card send/patch failure.
  - Card-mode fallback sends at most one compact notice: `⚠️ 任务卡片更新失败，后台进度仍已记录。`
  - Further card progress updates are suppressed after card failure; final flush is marked handled so cleanup does not re-dump the panel.
  - Text-mode progress behavior remains unchanged.

- `gateway/platforms/feishu.py`
  - Feishu send retry now uses one stable UUID across attempts for a single logical send.
  - Interactive card send inherits that stable UUID behavior.
  - Interactive card patch now retries transient exceptions/responses and still avoids retrying structural failures.

- `tests/gateway/test_run_progress_topics.py`
  - Added regressions for final patch failure, initial send failure, and patch failure spam suppression.

- `tests/gateway/test_feishu.py`
  - Added adapter-level regressions for patch retry, structural no-retry, stable UUID send retry, and stable UUID interactive-card retry.

## Verification Status

Focused regression gate:

```text
7 passed
```

Relevant Gateway/Feishu gate:

```text
./scripts/run_tests.sh tests/gateway/test_feishu.py tests/gateway/test_run_progress_topics.py tests/gateway/test_feishu_progress_cards.py -q
291 passed, 8 warnings
```

Syntax / lint / whitespace:

```text
python -m py_compile gateway/run.py gateway/platforms/feishu.py tests/gateway/test_feishu.py tests/gateway/test_run_progress_topics.py
python -m ruff check gateway/run.py gateway/platforms/feishu.py tests/gateway/test_feishu.py tests/gateway/test_run_progress_topics.py
git diff --check
PASS
```

Added-line safety scans:

```text
CODE_SECRET_SCAN_PASS
CODE_BOUNDARY_SCAN_PASS
```

Note: a naive whole-diff boundary scan flags this dev log's explicit `not approved` prose for real delivery. The code/test added-line scan is clean; the prose hit is a boundary declaration, not an execution surface.

Remaining before PR:

```text
commit / push / PR / GitHub CI
```

## Independent Review

Security/display review:

```text
PASS — no blockers.
Feishu card mode no longer dumps Transaction/Context/Recent operations/tool previews into ordinary chat on card failure; compact notice only; no Gateway restart/config/public/real-delivery boundary expansion found.
```

Logic/retry review:

```text
PASS — no blockers.
Stable send UUID across retries, patch retry behavior, structural no-retry behavior, card-progress suppression, final flush handling, and no-spam behavior reviewed. Reviewer also ran a focused test subset with 263 passed.
```

## Rollout Boundary

This PR must not restart or reload the running Gateway. Runtime rollout is a separate approval and should use a delayed restart/post-restart verification plan if requested later.
