# FlowWeaver Phase 4C — Snapshot Lifecycle Dev Log

Timestamp: 2026-05-04 15:21:57 CST +0800

## Scope

Make the Phase 4B Gateway shadow snapshot explicitly consumable and auditable without changing production behavior.

This phase remains default-off and in-memory only. It does not start orchestration, call Temporal, render snapshots, send messages, edit messages, persist records, restart Gateway, or mutate platform adapters.

## Branch and worktree

```text
branch: feat/flowweaver-phase4c-snapshot-lifecycle
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase4c-snapshot-lifecycle
base: origin/feature/sachima-channel @ e907afb763165db9c7b49e51e6a15e7887938e8d
```

## Repo hygiene before Phase 4C

Before creating this worktree, the merged historical local worktrees/branches were cleaned:

```text
feature/feishu-progress-card-rendering-pr1
feature/sachima-media-phase1
feature/skill-name-display-fix
feature/weather-rich-cards
fix/progress-explicit-final-flush
fix/progress-final-panel-flush
fix/weather-rich-auto-hermes-json
```

Three local-only `.hermes/` folders in old worktrees were backed up before forced worktree removal:

```text
/home/ubuntu/workspace/hermes/logs/sachima-worktree-cleanup-20260504-151915
```

Remote PR branches were intentionally not deleted.

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
75 passed in 14.59s
```

## Low-intrusion boundary

Allowed paths planned:

```text
docs/plans/2026-05-04-flowweaver-phase4c-snapshot-lifecycle.md
docs/dev_log/2026-05-04-flowweaver-phase4c-snapshot-lifecycle.md
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
gateway/platforms/*
skills/*
optional-skills/*
root pyproject.toml
prototypes/flowweaver_phase3/contracts/flowweaver.v0.schema.json
```

## TDD evidence

### Plan-first gate

The Phase 4C plan was written and committed before implementation code:

```text
commit: 026b8d99f docs: plan FlowWeaver phase 4C snapshot lifecycle
Plan: docs/plans/2026-05-04-flowweaver-phase4c-snapshot-lifecycle.md
```

### RED 1 — pure capture contract absent

Added tests to `tests/gateway/test_flowweaver_shadow_tap.py` for:

```text
test_shadow_tap_attaches_lifecycle_capture_for_consumers
test_shadow_consumer_view_requires_matching_snapshot_and_capture_ids
test_shadow_capture_omits_source_delivery_payloads_and_secret_shapes
```

Command:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_tap.py -q
```

Observed expected RED:

```text
ImportError: cannot import name 'FLOWWEAVER_SHADOW_CAPTURE_KEY' from 'gateway.flowweaver_shadow'
```

### GREEN 1 — pure capture seam

Added to `gateway/flowweaver_shadow.py`:

```python
FLOWWEAVER_SHADOW_CAPTURE_KEY = "flowweaver_shadow_capture"
FLOWWEAVER_SHADOW_CAPTURE_TYPE = "flowweaver.gateway.shadow_capture.v0"
get_flowweaver_shadow_capture(agent_result)
```

The helper now attaches a sibling in-memory capture record only after the sanitized `flowweaver.v0` snapshot succeeds. Consumer view access fails closed unless snapshot and capture IDs match exactly.

Focused result:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_tap.py tests/gateway/test_flowweaver_contract_adapter.py -q
17 passed in 0.41s
```

### Gateway lifecycle capture integration

Added:

```text
test_flowweaver_shadow_tap_attaches_consumer_capture_without_visible_side_effects
```

This proves Gateway shadow mode exposes a matching capture record while still producing no visible progress sends/edits when `tool_progress=off` and `task_tracker.enabled=false`.

Focused result:

```text
scripts/run_tests.sh tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_tap_attaches_consumer_capture_without_visible_side_effects -q
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
79 passed in 15.01s
```

### Security reviewer blockers and regression fix

Independent security/display review found two blockers:

```text
1. get_flowweaver_shadow_capture(...) returned the full snapshot, which can contain delivery ACK fields such as platform/message IDs.
2. get_flowweaver_shadow_capture(...) could raise for a hostile Mapping whose get()/iteration methods throw.
```

Regression tests added first:

```text
test_shadow_tap_attaches_lifecycle_capture_for_consumers  # now requires snapshot_ref, not full snapshot
test_shadow_consumer_view_fails_closed_for_hostile_mapping
test_flowweaver_shadow_tap_attaches_consumer_capture_without_visible_side_effects  # Gateway view uses snapshot_ref
```

Expected RED:

```text
KeyError: 'snapshot_ref'
RuntimeError: hostile mapping get
```

Fix:

```text
get_flowweaver_shadow_capture(...) now returns only {"snapshot_ref": ..., "capture": ...}; it does not re-export the full snapshot or delivery ACK payloads.
get_flowweaver_shadow_capture(...) and _build_flowweaver_shadow_capture(...) catch unexpected Mapping errors and return None.
```

Focused result after fix:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_tap.py::test_shadow_tap_attaches_lifecycle_capture_for_consumers tests/gateway/test_flowweaver_shadow_tap.py::test_shadow_consumer_view_fails_closed_for_hostile_mapping tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_tap_attaches_consumer_capture_without_visible_side_effects -q
3 passed in 1.81s
```

## Implementation details

- Public `flowweaver.v0` snapshot schema was not changed.
- Capture metadata is internal Gateway shadow metadata under `agent_result["flowweaver_shadow_capture"]`.
- Capture is built only from the already-sanitized snapshot and static lifecycle constants.
- Consumer view returns a safe `snapshot_ref` plus capture metadata; it deliberately does not re-export full snapshot delivery ACK payloads.
- Capture and consumer view omit source/platform/chat/user/message identifiers, delivery payload records, raw commands, stdout/stderr, card JSON, and secret-shaped strings.
- Existing Gateway wiring remains unchanged; Phase 4C rides on the Phase 4B helper call from `gateway/run.py`.
- No sends, edits, renders, persistence, logging, Temporal calls, service starts, or Gateway restarts were added.

## Missed-test reflection

The first pure capture tests covered the helper boundary but could have missed whether the real Gateway call path surfaced the capture without visible side effects. I added the fake-agent Gateway integration test before final verification so the actual `_run_agent` seam is covered, not just the pure helper.

## Final verification before PR

Focused gate after implementation, reviewer fixes, and dev-log update:

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
80 passed
```

Syntax and whitespace:

```text
python -m py_compile gateway/flowweaver_shadow.py gateway/flowweaver_contract.py gateway/run.py tests/gateway/test_flowweaver_shadow_tap.py tests/gateway/test_run_progress_topics.py
py_compile passed

git diff --check
git diff --check passed
```

Deterministic scans:

```text
changed files:
- docs/dev_log/2026-05-04-flowweaver-phase4c-snapshot-lifecycle.md
- gateway/flowweaver_shadow.py
- tests/gateway/test_flowweaver_shadow_tap.py
- tests/gateway/test_run_progress_topics.py

forbidden-surface hits: []
unplanned changed files: []
added-line secret hits: []
final-candidate secret hits: []
```

Independent reviews:

```text
spec / low-intrusion review: PASS
security / display review: REQUEST_CHANGES on first pass
security / display narrow re-review after fixes: PASS
```

Security reviewer blockers fixed:

```text
1. Consumer view no longer returns the full snapshot; it returns snapshot_ref + capture.
2. Hostile Mapping access now fails closed with None.
```
