# FlowWeaver Phase 4B Gateway Shadow Tap Implementation Plan

> **For Hermes:** Execute with strict TDD. The user approved the Phase 4B scope on 2026-05-04; routine in-scope operations may proceed without step-by-step approval.

**Goal:** Add a default-off Gateway shadow tap that captures the existing sanitized progress tracker and delivery-state boundary as a `flowweaver.v0` snapshot without changing live IM behavior.

**Architecture:** Phase 4B stays production-adjacent but inert by default. It reuses the Phase 4A pure adapter (`gateway/flowweaver_contract.py`) and adds a tiny shadow tap seam that can be enabled by config for tests or future observability. The tap records no platform I/O, starts no services, does not call Temporal, and does not render or deliver FlowWeaver snapshots to users.

**Tech Stack:** Python, pytest, existing `gateway.progress.*`, existing `gateway.delivery_state`, `gateway.run.GatewayRunner._run_agent`, Phase 4A `flowweaver.v0` adapter.

---

## Current Context / Evidence

Timestamp: 2026-05-04 14:22:53 CST +0800

Branch/worktree created from the clean integration branch:

```text
repo: /home/ubuntu/workspace/hermes/repo/sachima
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase4b-gateway-shadow-tap
branch: feat/flowweaver-phase4b-gateway-shadow-tap
base: origin/feature/sachima-channel @ 3344a37f7a
remote sync before branching: 0 ahead / 0 behind
open PRs before branching: none
```

Baseline verification in the new worktree:

```text
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_contract_adapter.py \
  tests/gateway/test_delivery_state.py \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/test_rich_weather_delivery.py \
  -q
67 passed in 13.70s
```

Relevant existing surfaces:

```text
gateway/flowweaver_contract.py                       # Phase 4A pure v0 adapter
tests/gateway/test_flowweaver_contract_adapter.py    # Phase 4A contract + safety invariants
gateway/progress/tracker.py                          # sanitized progress tracker
gateway/progress/events.py                           # TransactionSnapshot / ProgressOperation
gateway/delivery_state.py                            # explicit delivery_state helpers
gateway/run.py                                       # Gateway lifecycle boundary
tests/gateway/test_run_progress_topics.py            # fake-agent Gateway lifecycle tests
tests/gateway/test_run_rich_weather.py               # rich card delivery-state mutation tests
```

---

## Non-Goals / Hard Boundaries

Phase 4B must not do any of this:

```text
no Temporal
no Docker
no background daemons
no service startup
no Gateway restart
no live IM behavior change by default
no model/tool-loop rewrite
no changes to run_agent.py
no changes to model_tools.py
no changes to toolsets.py
no default skill activation
no Feishu SDK calls from FlowWeaver code
no gateway/platforms/* changes
```

Allowed paths for this PR:

```text
docs/plans/2026-05-04-flowweaver-phase4b-gateway-shadow-tap.md
docs/dev_log/2026-05-04-flowweaver-phase4b-gateway-shadow-tap.md
gateway/flowweaver_shadow.py
gateway/run.py
tests/gateway/test_flowweaver_shadow_tap.py
tests/gateway/test_run_progress_topics.py
```

`gateway/run.py` is allowed only for the smallest config-gated lifecycle hook. If implementation pressure grows beyond a few localized lines, stop and split the seam into a separate helper module instead of spreading FlowWeaver logic through the Gateway.

---

## Design: Default-Off Shadow Tap

Add a small helper module:

```python
# gateway/flowweaver_shadow.py
FLOWWEAVER_SHADOW_KEY = "flowweaver_shadow_snapshot"
FLOWWEAVER_SHADOW_CONFIG_KEY = "flowweaver_shadow"


def is_flowweaver_shadow_enabled(task_tracker_config: object) -> bool:
    """Return True only when display.task_tracker.flowweaver_shadow is truthy."""


def attach_flowweaver_shadow_snapshot(
    agent_result: dict,
    progress_snapshot: TransactionSnapshot,
    *,
    source: object | None = None,
    final_text: str | None = None,
) -> dict | None:
    """Attach a sanitized FlowWeaver v0 snapshot to agent_result for shadow observation."""
```

Expected behavior:

1. Default config: no `flowweaver_shadow_snapshot` key, no extra progress collection, no visible messages.
2. With `display.task_tracker.flowweaver_shadow: true`:
   - Gateway records sanitized progress events even when visible `task_tracker.enabled` is false and `tool_progress` is off.
   - At the end of `_run_agent`, Gateway attaches one sanitized `flowweaver.v0` snapshot to `agent_result`.
   - The snapshot uses existing `delivery_state`; streamed/previewed final text is reflected when already marked by `mark_final_text_sent`.
   - Normal final text delivery remains outside the shadow tap; the tap must not claim a normal send that has not yet happened.
3. Existing visible progress card/text behavior remains unchanged when only the shadow flag is enabled.
4. Snapshot output must pass the Phase 4A no-leak rules: no raw commands, stdout/stderr, raw card JSON, chat/user/platform-ish IDs, token/API-key/secret shapes.

Config gate choice:

```yaml
display:
  task_tracker:
    flowweaver_shadow: true
```

No default config value is added in this PR. Absence means false.

---

## TDD Task Plan

### Task 0: Persist this approved plan

**Files:**

- Create: `docs/plans/2026-05-04-flowweaver-phase4b-gateway-shadow-tap.md`

**Verification:**

```bash
git check-ignore -v docs/plans/2026-05-04-flowweaver-phase4b-gateway-shadow-tap.md || true
git add docs/plans/2026-05-04-flowweaver-phase4b-gateway-shadow-tap.md
git commit -m "docs: plan FlowWeaver phase 4B gateway shadow tap" \
  -m "Plan: docs/plans/2026-05-04-flowweaver-phase4b-gateway-shadow-tap.md"
```

### Task 1: RED — pure shadow helper tests

**Files:**

- Create: `tests/gateway/test_flowweaver_shadow_tap.py`
- Production file intentionally absent before RED: `gateway/flowweaver_shadow.py`

**Tests:**

```text
test_shadow_tap_is_disabled_by_default
test_shadow_tap_attaches_sanitized_v0_snapshot_when_enabled
test_shadow_tap_does_not_claim_unsent_normal_final_text
test_shadow_tap_never_raises_or_leaks_sensitive_source_fields
```

**RED command:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_tap.py -q
```

Expected: fail because `gateway.flowweaver_shadow` does not exist.

### Task 2: GREEN — implement pure shadow helper

**Files:**

- Create: `gateway/flowweaver_shadow.py`

**Implementation notes:**

- Delegate contract construction to `build_flowweaver_v0_snapshot(...)`.
- Normalize delivery state via `ensure_delivery_state(agent_result)` before building.
- Do not include `source` in the public snapshot; pass only as future seam context to the Phase 4A adapter, which already discards it.
- Return `None` when disabled or invalid input makes capture impossible.
- Never raise from the tap path.

**Verification:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_tap.py tests/gateway/test_flowweaver_contract_adapter.py -q
```

### Task 3: RED — Gateway lifecycle shadow-mode tests

**Files:**

- Modify: `tests/gateway/test_run_progress_topics.py`

**Tests:**

```text
test_flowweaver_shadow_tap_collects_progress_when_visible_progress_is_off
test_flowweaver_shadow_tap_default_off_preserves_existing_no_progress_behavior
test_flowweaver_shadow_tap_streamed_final_text_counts_as_answered_coverage
```

**Expected RED:**

- With config `tool_progress: off`, `task_tracker.enabled: false`, `task_tracker.flowweaver_shadow: true`, fake agent emits progress events but no visible progress messages/cards are sent.
- Current code will not attach `flowweaver_shadow_snapshot`, because progress callbacks are disabled when visible progress is off.

### Task 4: GREEN — minimal Gateway wiring

**Files:**

- Modify: `gateway/run.py`

**Implementation notes:**

- Compute `flowweaver_shadow_enabled` from `display.task_tracker.flowweaver_shadow` only.
- Distinguish visible progress from tracking:
  - `progress_queue` exists only for visible progress.
  - `tool_progress_enabled` becomes true for visible progress or shadow tracking.
  - `progress_tracker` is created for visible task tracker or shadow tracking.
- In `progress_callback`, record to `progress_tracker` even if there is no `progress_queue`; only queue renders when visible progress exists.
- Start `send_progress_messages()` only when `progress_queue` exists.
- After final stream/preview delivery marking, attach `flowweaver_shadow_snapshot` to the returned `agent_result`.
- Do not send, edit, persist, or log the snapshot as user-visible output.

### Task 5: Verification, review, and PR

Focused gate:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_shadow_tap.py \
  tests/gateway/test_flowweaver_contract_adapter.py \
  tests/gateway/test_delivery_state.py \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/test_rich_weather_delivery.py \
  -q
```

Extra gate:

```bash
python -m py_compile gateway/flowweaver_shadow.py gateway/flowweaver_contract.py gateway/run.py tests/gateway/test_flowweaver_shadow_tap.py tests/gateway/test_run_progress_topics.py
git diff --check
```

Deterministic scans:

```text
forbidden-surface scan: no run_agent.py/model_tools.py/toolsets.py/cli.py/hermes_cli/main.py/gateway/platforms/*/skills/*/optional-skills/* changes
final-content secret scan: scan final candidate content and added lines; do not scan stale removed lines from intermediate commits
```

Independent reviews:

```text
1. spec / low-intrusion blocker review
2. security / display / no-leak blocker review
```

Dev log:

```text
docs/dev_log/2026-05-04-flowweaver-phase4b-gateway-shadow-tap.md
```

PR target:

```text
base: feature/sachima-channel
branch: feat/flowweaver-phase4b-gateway-shadow-tap
```
