# FlowWeaver Phase 4A — Gateway Contract Seam Dev Log

Timestamp: 2026-05-04 12:42:08 CST +0800

## Scope

Add the first production-adjacent FlowWeaver seam for Sachima/Hermes: a pure Gateway progress/delivery-state adapter that can emit a sanitized `flowweaver.v0` contract-shaped snapshot.

This phase intentionally stops short of runtime integration. It does not start orchestration or change live IM behavior.

## Branch and worktree

```text
branch: feat/flowweaver-phase4-gateway-contract-seam
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase4-gateway-contract-seam
base: origin/feature/sachima-channel @ 9a34910f2
plan commit: 417f987dd
```

## Low-intrusion boundary

Allowed paths used:

```text
docs/plans/2026-05-04-flowweaver-phase4-gateway-contract-seam.md
gateway/flowweaver_contract.py
tests/gateway/test_flowweaver_contract_adapter.py
docs/dev_log/2026-05-04-flowweaver-phase4-gateway-contract-seam.md
```

Explicitly not touched:

```text
run_agent.py
model_tools.py
toolsets.py
cli.py
hermes_cli/main.py
gateway/platforms/*
skills/*
optional-skills/*
root pyproject.toml
```

No Temporal, Docker, background daemon, service startup, live Gateway wiring, or Gateway restart was performed.

## Files changed

```text
Create: docs/plans/2026-05-04-flowweaver-phase4-gateway-contract-seam.md
Create: gateway/flowweaver_contract.py
Create: tests/gateway/test_flowweaver_contract_adapter.py
Create: docs/dev_log/2026-05-04-flowweaver-phase4-gateway-contract-seam.md
```

## TDD evidence

### Plan-first gate

The approved plan was first saved in local planning state, then persisted into repo docs and committed before production code:

```text
commit: 417f987dd docs: plan FlowWeaver phase 4 gateway contract seam
Plan: docs/plans/2026-05-04-flowweaver-phase4-gateway-contract-seam.md
```

### RED

Command:

```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest tests/gateway/test_flowweaver_contract_adapter.py -q
```

Observed expected RED before production module existed:

```text
ERROR tests/gateway/test_flowweaver_contract_adapter.py
ModuleNotFoundError: No module named 'gateway.flowweaver_contract'
```

### GREEN

Added `gateway/flowweaver_contract.py` with a pure function:

```python
build_flowweaver_v0_snapshot(progress_snapshot, *, source=None, delivery_state=None, final_text=None)
```

Focused result:

```text
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest tests/gateway/test_flowweaver_contract_adapter.py -q
7 passed in 1.89s
```

## Important implementation details

The adapter:

- maps one current Gateway `TransactionSnapshot` to one `flowweaver.handle.v0` document;
- emits one synthetic `task` intent for Phase 4A;
- translates Gateway statuses into FlowWeaver vocabulary;
- maps `ProgressOperation` entries to sanitized FlowWeaver operations;
- maps explicit `delivery_state.final_text.sent=True` to final-text coverage;
- maps `delivery_state.rich_cards_sent` records to rich-card artifacts and Feishu-shaped delivery ACKs;
- keeps `adapter: mock` for v0 compatibility;
- does not copy `source` into the public snapshot, avoiding chat/platform credential leakage;
- does not import from the Phase 3 prototype package and performs no platform I/O.

## Contract drift caught during implementation

A self-review caught a real contract drift before finalizing: the first test/implementation pair used `gateway:*` delivery IDs and `platform: gateway` for delivery ACKs. That contradicted the Phase 3 v0 schema, which requires Feishu-shaped ACKs:

```text
delivery_idempotency_key: ^feishu:om_[a-z0-9_]+:[a-z_]+:[a-z0-9_]+$
platform: feishu
message_id: ^om_[a-z0-9_]+$
```

The tests were tightened with `assert_v0_delivery_ack_shape(...)`, and the implementation now emits:

```text
feishu:om_final_text:final_text:task
feishu:om_weather:rich_card:artifact_weather_v1
```

This was the right kind of catch: not a cosmetic issue, a contract-semantics issue.

## Verification evidence so far

Baseline before feature code in the new worktree:

```text
scripts/run_tests.sh tests/flowweaver_phase3 -q
23 passed, 3 subtests passed in 0.48s

pytest tests/gateway/test_delivery_state.py tests/gateway/test_run_rich_weather.py tests/gateway/progress/test_task_titles.py -q
52 passed in 2.73s
```

Focused adapter verification:

```text
pytest tests/gateway/test_flowweaver_contract_adapter.py -q
7 passed in 1.89s
```

Seam + neighboring suites:

```text
pytest \
  tests/gateway/test_flowweaver_contract_adapter.py \
  tests/gateway/test_delivery_state.py \
  tests/gateway/test_progress_tracker.py \
  tests/gateway/test_progress_store.py \
  -q
36 passed in 2.48s
```

Syntax and whitespace gate:

```text
python -m py_compile gateway/flowweaver_contract.py tests/gateway/test_flowweaver_contract_adapter.py
git diff --check
passed
```

## Security notes

- No real tokens, credentials, API keys, cookies, webhook secrets, or private URLs were added.
- Tests use fake secret-shaped strings only.
- The adapter redacts secret-shaped text defensively after the existing progress redaction helpers.
- The public snapshot does not include raw command args, raw outputs, stdout/stderr, or Feishu card JSON.
- Delivery ACKs are translated only from explicit Gateway delivery state; the adapter does not claim or perform platform sends.

## Missed-test reflection

The initial RED tests proved behavior but missed one critical v0-schema invariant: delivery ACK IDs and platform values must remain Feishu-shaped. The implementation briefly followed the too-loose test, which is exactly how tests can encode the wrong contract if they are not checked against the source schema.

The fix was to add `assert_v0_delivery_ack_shape(...)` and make the expected values match the existing Phase 3 contract. Future FlowWeaver adapter tests should assert contract regexes, not just example strings.

## Independent review blocker fixes

Two independent reviews found real blockers before PR:

1. Non-`om_` rich-card message IDs could produce invalid v0 delivery ACKs.
2. Operation previews could leak raw commands, raw output, or card-shaped JSON into user-facing summaries/render text.
3. Public FlowWeaver IDs could leak platform/chat/user-looking transaction IDs.

Regression tests added:

```text
test_operation_preview_never_becomes_user_visible_summary_or_render_text
test_rich_card_delivery_skips_non_feishu_message_ids
test_public_ids_do_not_leak_platform_chat_or_user_identifiers
```

Fixes:

- `_operation_summary()` now always uses bounded tool/event/status labels instead of preview text.
- `_safe_message_id()` now only accepts exact Feishu-shaped raw `om_*` ids after separator stripping; non-conforming rich-card delivery records such as `msg-123` or `om-weather` are skipped.
- public transaction/correlation/snapshot/final-text IDs now hash platform/chat/user-looking transaction IDs into opaque `transaction_<digest>` base IDs.

Focused adapter result after blocker fixes:

```text
pytest tests/gateway/test_flowweaver_contract_adapter.py -q
10 passed in 1.89s
```

Final verification after all blocker fixes:

```text
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_contract_adapter.py \
  tests/gateway/test_delivery_state.py \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/test_rich_weather_delivery.py \
  -q
67 passed in 13.54s

py_compile: passed
git diff --check: passed
forbidden surface scan: clean
final-content secret scan: clean
```

Independent review outcomes:

```text
spec / low-intrusion review: PASS
security / display review: PASS after blocker fixes
narrow om-weather ACK re-review: PASS
```

## Remaining work before PR

- Commit code/test/dev-log changes.
- Push and open PR against `feature/sachima-channel`.
