# FlowWeaver Phase 4D — Shadow Consumer Audit Dev Log

Timestamp: 2026-05-04 16:49:06 CST +0800

## Scope

Add a default-off, in-memory audit harness that proves the Phase 4C `snapshot_ref + capture` consumer seam can be safely consumed without re-exporting full snapshots, delivery ACKs, platform IDs, or runtime side effects.

This phase remains shadow-only and read-only. It does not start orchestration, call Temporal, render snapshots, send messages, edit messages, persist records, log audit output, restart Gateway, or mutate platform adapters.

## Branch and worktree

```text
branch: feat/flowweaver-phase4d-shadow-consumer-audit
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase4d-shadow-consumer-audit
base: origin/feature/sachima-channel @ 2090f68e645498019662ef56e786ae1bd4082c42
```

## Baseline verification

Command:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_shadow_tap.py \
  tests/gateway/test_flowweaver_contract_adapter.py \
  tests/gateway/test_delivery_state.py \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/test_rich_weather_delivery.py \
  -q
```

Observed:

```text
80 passed in 15.20s
```

## Low-intrusion boundary

Allowed paths planned:

```text
docs/plans/2026-05-04-flowweaver-phase4d-shadow-consumer-audit.md
docs/dev_log/2026-05-04-flowweaver-phase4d-shadow-consumer-audit.md
gateway/flowweaver_shadow.py
tests/gateway/test_flowweaver_shadow_tap.py
tests/gateway/test_run_progress_topics.py
```

Explicitly not planned:

```text
run_agent.py
model_tools.py
toolsets.py
cli.py
hermes_cli/main.py
gateway/run.py
gateway/platforms/*
skills/*
optional-skills/*
root pyproject.toml
prototypes/flowweaver_phase3/contracts/flowweaver.v0.schema.json
```

## TDD evidence

### Plan-first gate

The Phase 4D plan was written and committed before implementation code:

```text
commit: 22a89b43e docs: plan FlowWeaver phase 4D shadow consumer audit
Plan: docs/plans/2026-05-04-flowweaver-phase4d-shadow-consumer-audit.md
```

### RED 1 — pure audit helper absent

Added tests to `tests/gateway/test_flowweaver_shadow_tap.py` for:

```text
test_shadow_audit_ready_for_safe_consumer_view
test_shadow_audit_rejects_missing_or_mismatched_pair
test_shadow_audit_marks_unsafe_snapshot_as_unsafe
test_shadow_audit_marks_contract_or_capture_type_mismatch_as_schema_mismatch
test_shadow_audit_fails_closed_for_hostile_mapping
test_shadow_audit_output_omits_full_snapshot_delivery_payloads_and_secret_shapes
test_shadow_audit_accepts_failed_cancelled_blocked_and_pending_lifecycle_states
```

Command:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_tap.py -q
```

Observed expected RED:

```text
ImportError: cannot import name 'FLOWWEAVER_SHADOW_AUDIT_READY' from 'gateway.flowweaver_shadow'
```

### GREEN 1 — pure audit harness

Added to `gateway/flowweaver_shadow.py`:

```python
FLOWWEAVER_SHADOW_AUDIT_TYPE = "flowweaver.gateway.shadow_audit.v0"
FLOWWEAVER_SHADOW_AUDIT_READY = "ready"
FLOWWEAVER_SHADOW_AUDIT_REJECTED = "rejected"
FLOWWEAVER_SHADOW_AUDIT_UNSAFE = "unsafe"
FLOWWEAVER_SHADOW_AUDIT_SCHEMA_MISMATCH = "schema_mismatch"
audit_flowweaver_shadow_capture(agent_result)
```

The helper returns only a safe verdict envelope: `snapshot_ref`, static `reason`, boolean `checks`, empty `side_effects`, and the already-safe capture record. It never returns the full snapshot/transaction/deliveries.

Focused result:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_tap.py tests/gateway/test_flowweaver_contract_adapter.py -q
25 passed in 0.42s
```

### Gateway lifecycle audit integration

Added:

```text
test_flowweaver_shadow_tap_audit_ready_without_visible_side_effects
```

This proves the audit helper can consume the actual Gateway-returned `agent_result` from the existing shadow tap while visible sends/edits stay empty for `tool_progress=off`, `task_tracker.enabled=false`, and `flowweaver_shadow=true`.

Focused result:

```text
scripts/run_tests.sh tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_tap_audit_ready_without_visible_side_effects -q
1 passed in 1.80s
```

### Current focused suite

Command:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_shadow_tap.py \
  tests/gateway/test_flowweaver_contract_adapter.py \
  tests/gateway/test_delivery_state.py \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/test_rich_weather_delivery.py \
  -q
```

Observed before reviewer fixes:

```text
88 passed in 14.07s
```

### Reviewer blockers and regression fix

Independent reviews found concrete blockers:

```text
1. `source_exported=True` and visible side effects were classified as `rejected` before audit checks could mark them `unsafe`.
2. Audit output included the caller-owned `capture` object, contradicting the safe audit shape and creating a possible hostile Mapping/repr leak path.
3. A forged matching snapshot/capture pair could return caller-controlled platform/chat/user/message-like IDs through `snapshot_ref`.
```

Regression tests added first:

```text
test_shadow_audit_marks_source_export_or_side_effects_as_unsafe
test_shadow_audit_ready_for_safe_consumer_view  # now asserts no `capture` field in audit output
test_flowweaver_shadow_tap_audit_ready_without_visible_side_effects  # now asserts no `capture` field
test_shadow_audit_rejects_platform_like_snapshot_ref_ids_without_leaking_them
```

Expected RED:

```text
AssertionError: 'rejected' == 'unsafe'
AssertionError: 'capture' not in audit
AssertionError: assert 'ready' == 'schema_mismatch'
```

Fix:

```text
audit_flowweaver_shadow_capture(...) now checks schema and ID match first, then classifies unsafe audit flags/side effects before exact expected-capture equality.
Audit output now contains only type, verdict, reason, snapshot_ref, boolean checks, and side_effects; it does not return the capture object.
Snapshot refs are returned only when tx_/turn_/snap_ IDs match the sanitized public-ref pattern and contain no platform/chat/user/message/secret-like fragments.
```

Focused results after fixes:

```text
3 passed in 1.77s
1 passed in 0.39s
18 passed in 1.80s
```

## Implementation details

- Public `flowweaver.v0` snapshot schema was not changed.
- `gateway/run.py` was not changed; Phase 4D consumes the existing in-memory `agent_result` seam.
- `audit_flowweaver_shadow_capture(...)` classifies `ready`, `rejected`, `unsafe`, and `schema_mismatch`.
- Audit output does not include full snapshot, capture object, transaction, deliveries, artifacts, platform/message IDs, source objects, raw commands, stdout/stderr, card JSON, or secret-shaped values.
- Hostile `Mapping` objects fail closed to `rejected`.
- No sends, edits, renders, persistence, logging, Temporal calls, service starts, or Gateway restarts were added.

## Missed-test reflection

The initial Phase 4D audit tests caught the basic verdict classes but missed three important reviewer cases: unsafe capture audit flags were being rejected too early, audit output was still returning the original capture object, and forged caller-owned IDs could flow through `snapshot_ref`. I added regressions for those before fixing them.

## Final verification before PR

Focused gate after implementation, reviewer fixes, and dev-log update:

```text
90 passed in 15.16s
py_compile passed
git diff --check passed
```

Deterministic scans:

```text
forbidden-surface hits: []
unplanned changed files: []
added-line secret hits: []
final-candidate secret hits: []
```

Independent reviews:

```text
spec / low-intrusion review: REQUEST_CHANGES on first pass; PASS after unsafe-order/capture-output fixes
security / display review: REQUEST_CHANGES on first pass; REQUEST_CHANGES on second pass for forged snapshot_ref leak; PASS after snapshot_ref validation
narrow re-review after fixes: PASS
```
