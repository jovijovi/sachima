# FlowWeaver Phase 4E — Replay Probe Dev Log

Timestamp: 2026-05-04 18:31:29 CST +0800

## Scope

Plan a default-off, in-memory replay probe for the Phase 4C/4D `snapshot_ref + capture + audit` consumer seam. The probe should prove repeated safe reads are stable and side-effect-free before any future durable consumer or Temporal wiring.

This phase remains shadow-only and read-only. It must not start orchestration, call Temporal, render snapshots, send messages, edit messages, persist records, log replay output, restart Gateway, mutate platform adapters, or change visible Gateway behavior.

## Branch and worktree

```text
branch: feat/flowweaver-phase4e-replay-probe
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase4e-replay-probe
base: origin/feature/sachima-channel @ 12b9addd2ec04890150ee85259d7f8014e28b4da
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
90 passed in 15.29s
```

## Low-intrusion boundary

Allowed paths planned:

```text
docs/plans/2026-05-04-flowweaver-phase4e-replay-probe.md
docs/dev_log/2026-05-04-flowweaver-phase4e-replay-probe.md
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
prototypes/flowweaver_phase3/contracts/flowweaver.v0.schema.json
```

## Design status

Plan drafted:

```text
docs/plans/2026-05-04-flowweaver-phase4e-replay-probe.md
```

Planned helper:

```python
replay_flowweaver_shadow_capture(agent_result, *, attempts=2)
```

Planned verdicts:

```text
replayed
rejected
unsafe
schema_mismatch
drift_detected
```

## Implementation status

Approved by user after design handoff. Implementation is in progress under strict TDD.

### RED 1 — pure replay helper absent

Added Phase 4E unit/security tests to `tests/gateway/test_flowweaver_shadow_tap.py` for:

```text
test_shadow_replay_probe_replays_safe_capture_without_returning_capture_or_snapshot
test_shadow_replay_probe_rejects_missing_invalid_or_bad_attempt_counts
test_shadow_replay_probe_propagates_audit_unsafe_and_schema_mismatch
test_shadow_replay_probe_detects_unstable_snapshot_ref_or_audit_output
test_shadow_replay_probe_does_not_mutate_agent_result
test_shadow_replay_probe_fails_closed_for_hostile_mapping
test_shadow_replay_probe_output_omits_delivery_payloads_platform_ids_and_secret_shapes
```

Command:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_tap.py -q
```

Observed expected RED:

```text
ImportError: cannot import name 'FLOWWEAVER_SHADOW_REPLAY_DRIFT_DETECTED' from 'gateway.flowweaver_shadow'
```

### GREEN 1 — pure replay probe

Added to `gateway/flowweaver_shadow.py`:

```python
FLOWWEAVER_SHADOW_REPLAY_TYPE = "flowweaver.gateway.shadow_replay_probe.v0"
FLOWWEAVER_SHADOW_REPLAY_REPLAYED = "replayed"
FLOWWEAVER_SHADOW_REPLAY_REJECTED = "rejected"
FLOWWEAVER_SHADOW_REPLAY_UNSAFE = "unsafe"
FLOWWEAVER_SHADOW_REPLAY_SCHEMA_MISMATCH = "schema_mismatch"
FLOWWEAVER_SHADOW_REPLAY_DRIFT_DETECTED = "drift_detected"
replay_flowweaver_shadow_capture(agent_result, *, attempts=2)
```

The helper repeatedly reads through the existing audit path, returns only a safe replay envelope, rejects invalid attempts, propagates unsafe/schema mismatch, detects stable-audit drift, and never returns full snapshot or caller-owned capture.

Focused result:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_tap.py tests/gateway/test_flowweaver_contract_adapter.py -q
34 passed in 0.42s
python -m py_compile gateway/flowweaver_shadow.py tests/gateway/test_flowweaver_shadow_tap.py
py_compile passed
```

### Gateway lifecycle replay integration

Added:

```text
test_flowweaver_shadow_tap_replay_probe_without_visible_side_effects
```

This calls the replay helper on the actual fake-agent Gateway-returned `agent_result` while `tool_progress=off`, `task_tracker.enabled=false`, and `flowweaver_shadow=true`; visible sends/edits remain empty.

Focused result:

```text
scripts/run_tests.sh tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_tap_replay_probe_without_visible_side_effects -q
1 passed in 1.81s
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_tap.py tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_tap_replay_probe_without_visible_side_effects -q
25 passed in 1.81s
```

Note: the lifecycle integration test is regression coverage through the existing seam; no additional Gateway production code was required after the pure helper GREEN.

### Security reviewer blocker and fix

Independent security/no-leak review found one blocker:

```text
Replay snapshot_ref validation still accepted opaque caller/source-derived platform IDs such as Slack-like `U123ABC` -> `tx_u123abc` and long numeric Discord/Telegram-like IDs -> `tx_transaction_123456789012345678`.
```

Regression added first:

```text
test_shadow_replay_probe_rejects_opaque_platform_like_refs_without_leaking_them
```

Expected RED:

```text
AssertionError: assert 'replayed' == 'schema_mismatch'
```

Fix:

```text
_shadow_ref validation now rejects opaque platform-like public refs matching Slack-style U/C/G/D IDs or long numeric transaction refs, in addition to explicit platform/chat/user/message/secret fragments.
```

Focused result after fix:

```text
2 passed in 0.39s
```

## Verification before design handoff

Plan-file ignore/whitespace check:

```bash
git check-ignore -v docs/plans/2026-05-04-flowweaver-phase4e-replay-probe.md docs/dev_log/2026-05-04-flowweaver-phase4e-replay-probe.md || true
git diff --check
```

Observed:

```text
no ignore hits
git diff --check passed
```

Independent plan reviews:

```text
spec / low-intrusion review: PASS
security / no-leak review: PASS
```

Implementation has started after design approval; final gate and independent implementation review are pending.

## Final verification before PR

Focused gate after implementation, reviewer fix, and dev-log update:

```text
99 passed
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
spec / low-intrusion review: PASS
security / no-leak review: REQUEST_CHANGES on first implementation pass; PASS after opaque-ref validation fix
```

Missed-test reflection:

```text
The first replay test set caught direct platform/chat/user/message fragments but missed opaque platform-like IDs that survive slugification, such as Slack-style U123ABC and long numeric chat/user IDs. I added a focused regression before tightening replay snapshot_ref validation.
```
