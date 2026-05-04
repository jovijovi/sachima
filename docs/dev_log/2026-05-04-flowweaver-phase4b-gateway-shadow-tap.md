# FlowWeaver Phase 4B — Gateway Shadow Tap Dev Log

Timestamp: 2026-05-04 14:36:45 CST +0800

## Scope

Add a default-off Gateway shadow tap that captures the existing sanitized progress tracker and delivery-state boundary as a `flowweaver.v0` snapshot.

This phase intentionally remains shadow-only. It does not start orchestration, does not call Temporal, and does not change live IM behavior unless the explicit shadow flag is enabled for tests/future observability.

## Branch and worktree

```text
branch: feat/flowweaver-phase4b-gateway-shadow-tap
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase4b-gateway-shadow-tap
base: origin/feature/sachima-channel @ 3344a37f7a
plan commit: 453fa45908
```

## Low-intrusion boundary

Allowed paths used:

```text
docs/plans/2026-05-04-flowweaver-phase4b-gateway-shadow-tap.md
docs/dev_log/2026-05-04-flowweaver-phase4b-gateway-shadow-tap.md
gateway/flowweaver_shadow.py
gateway/run.py
tests/gateway/test_flowweaver_shadow_tap.py
tests/gateway/test_run_progress_topics.py
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

No Temporal, Docker, background daemon, service startup, live Gateway restart, or platform SDK integration was performed.

## Files changed

```text
Create: docs/plans/2026-05-04-flowweaver-phase4b-gateway-shadow-tap.md
Create: docs/dev_log/2026-05-04-flowweaver-phase4b-gateway-shadow-tap.md
Create: gateway/flowweaver_shadow.py
Create: tests/gateway/test_flowweaver_shadow_tap.py
Modify: gateway/run.py
Modify: tests/gateway/test_run_progress_topics.py
```

## TDD evidence

### Baseline in new worktree

Command:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_contract_adapter.py \
  tests/gateway/test_delivery_state.py \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/test_rich_weather_delivery.py \
  -q
```

Observed:

```text
67 passed in 13.70s
```

### Plan-first gate

The plan was persisted before code:

```text
commit: 453fa45908 docs: plan FlowWeaver phase 4B gateway shadow tap
Plan: docs/plans/2026-05-04-flowweaver-phase4b-gateway-shadow-tap.md
```

### RED 1 — pure helper absent

Command:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_tap.py -q
```

Observed expected RED:

```text
ModuleNotFoundError: No module named 'gateway.flowweaver_shadow'
```

### GREEN 1 — pure helper

Added `gateway/flowweaver_shadow.py` with:

```python
is_flowweaver_shadow_enabled(task_tracker_config)
attach_flowweaver_shadow_snapshot(agent_result, progress_snapshot, *, enabled, source=None, final_text=None)
```

Focused result:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_tap.py tests/gateway/test_flowweaver_contract_adapter.py -q
14 passed in 0.41s
```

### RED 2 — Gateway lifecycle not wired

Added Gateway lifecycle tests for the explicit shadow flag. Expected failures before wiring:

```text
KeyError: 'flowweaver_shadow_snapshot'
```

A first draft of the lifecycle tests used a fake agent that assumed `tool_progress_callback` was always present; that failed with `TypeError: 'NoneType' object is not callable`, which was a bad RED. The test agent was corrected to tolerate a missing callback so the RED reflected the actual missing feature.

### GREEN 2 — minimal Gateway wiring

Implemented the default-off seam in `gateway/run.py`:

- `display.task_tracker.flowweaver_shadow` is the only enable flag.
- Shadow tracking can collect progress when visible `tool_progress` is off.
- Shadow tracking does not create a visible progress queue.
- Streamed/previewed final text delivery is reflected after `mark_final_text_sent(...)` runs.
- The attached snapshot is stored only in the in-memory `agent_result` under `flowweaver_shadow_snapshot`.

Focused lifecycle result:

```text
3 passed in 1.26s
```

### Regression caught during self-review

Self-review found a real behavior-change bug: when `flowweaver_shadow=true` and ordinary `tool_progress=all`, the shadow `ProgressTracker` caused the visible legacy progress stream to be rendered as the transaction panel even though `task_tracker.enabled=false`.

Regression test added first:

```text
test_flowweaver_shadow_tap_preserves_legacy_tool_progress_when_progress_is_visible
```

Expected RED:

```text
AssertionError: 'Transaction' is contained here: 📌 **Transaction:** ...
```

Fix:

- Only render task-tracker panels when `task_tracker_enabled` is true.
- Shadow-only tracking records to the FlowWeaver snapshot but falls through to the legacy progress renderer when legacy progress is visible.
- Final task-tracker flush is only queued for real task-tracker rendering, not shadow-only tracking.

Focused result after fix:

```text
4 passed in 1.76s
```

### Current focused suite

Command:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_shadow_tap.py \
  tests/gateway/test_flowweaver_contract_adapter.py \
  tests/gateway/test_run_progress_topics.py \
  -q
```

Observed:

```text
57 passed in 13.90s
```

Syntax and whitespace gate so far:

```text
python -m py_compile gateway/flowweaver_shadow.py gateway/flowweaver_contract.py gateway/run.py tests/gateway/test_flowweaver_shadow_tap.py tests/gateway/test_run_progress_topics.py
passed

git diff --check
passed
```

## Important implementation details

The new helper:

- reuses Phase 4A `build_flowweaver_v0_snapshot(...)`;
- normalizes `agent_result['delivery_state']` via `ensure_delivery_state(...)` before snapshotting;
- stores the snapshot under `flowweaver_shadow_snapshot` only when explicitly enabled;
- fail-closes by returning `None` and removing partial snapshot state if capture fails;
- passes only coarse source shape to the adapter, and the adapter still discards public source details.

The Gateway seam:

- uses `display.task_tracker.flowweaver_shadow` as the default-off flag;
- creates `progress_tracker` for either visible task tracker rendering or shadow capture;
- keeps `progress_queue` tied only to visible progress;
- keeps legacy progress rendering when task tracker is not enabled;
- attaches the shadow snapshot after streamed/previewed final delivery has been marked.

## Security notes

- No real credentials, tokens, API keys, cookies, webhook secrets, or private URLs were added.
- Tests split fake secret-shaped values so static scans do not carry complete fake credential strings as ordinary literals.
- Shadow snapshots reuse the Phase 4A no-leak adapter invariants: no raw command previews, stdout/stderr, raw card JSON, platform/chat/user-like transaction IDs, or secret-shaped values.
- The shadow tap does not send, edit, persist, render, or log the snapshot as user-visible output.

## Missed-test reflection

The initial lifecycle tests covered `tool_progress=off` but missed the mixed mode where `flowweaver_shadow=true` coexists with visible legacy `tool_progress=all`. That gap allowed a shadow-only tracker to accidentally replace legacy progress with transaction-panel rendering.

The fix was to add a regression proving legacy progress stays legacy unless `task_tracker.enabled=true`. Future Gateway shadow-mode work should always test the cross-product of:

```text
shadow on/off × task_tracker on/off × tool_progress off/all
```

## Final verification before commit

Focused gate after implementation and dev-log write:

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
75 passed in 14.38s
```

Syntax and whitespace:

```text
python -m py_compile gateway/flowweaver_shadow.py gateway/flowweaver_contract.py gateway/run.py tests/gateway/test_flowweaver_shadow_tap.py tests/gateway/test_run_progress_topics.py
passed

git diff --check
passed
```

Deterministic scans:

```text
changed files:
  docs/dev_log/2026-05-04-flowweaver-phase4b-gateway-shadow-tap.md
  docs/plans/2026-05-04-flowweaver-phase4b-gateway-shadow-tap.md
  gateway/flowweaver_shadow.py
  gateway/run.py
  tests/gateway/test_flowweaver_shadow_tap.py
  tests/gateway/test_run_progress_topics.py

forbidden surface scan: clean
added-line/untracked final-candidate secret scan: clean
candidate lines scanned: 1034
```

Scan methodology note: a broad whole-file scan of all modified files flagged an old pre-existing fake token-shaped concatenation in `tests/gateway/test_run_progress_topics.py`. The clean scan above used the intended final-candidate method for this branch: added lines from the full working-tree diff plus full untracked new files.

Independent reviews:

```text
spec / low-intrusion review: PASS — no blockers
security / display / no-leak review: PASS — no blockers
```

## Remaining work before PR

- Rerun the focused gate/scans after this final dev-log update.
- Commit, push, open PR, then verify local/remote/PR heads.
