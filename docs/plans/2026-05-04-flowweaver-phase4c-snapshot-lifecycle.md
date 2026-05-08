# FlowWeaver Phase 4C Snapshot Lifecycle Implementation Plan

> **For Hermes:** Execute with strict TDD. The user approved the Phase 4C direction on 2026-05-04: clean local repo hygiene first, then advance FlowWeaver shadow snapshots without production takeover.

**Goal:** Make the Phase 4B Gateway shadow snapshot explicitly consumable and auditable by adding a default-off, in-memory lifecycle capture boundary around the existing sanitized `flowweaver.v0` snapshot.

**Architecture:** Phase 4C keeps the public `flowweaver.v0` snapshot schema unchanged and adds a small Gateway-side shadow capture record beside the snapshot in `agent_result`. The capture record is not rendered, sent, persisted, logged, or delivered; it only documents lifecycle state, allowed future consumers, forbidden side effects, and ID correlation for tests and later FlowWeaver runtime wiring.

**Tech Stack:** Python, pytest, existing `gateway/flowweaver_contract.py`, existing `gateway/flowweaver_shadow.py`, existing Gateway fake-agent tests in `tests/gateway/test_run_progress_topics.py`.

---

## Current Context / Evidence

Timestamp: 2026-05-04 15:21:57 CST +0800

Branch/worktree:

```text
repo: /home/ubuntu/workspace/hermes/repo/sachima
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase4c-snapshot-lifecycle
branch: feat/flowweaver-phase4c-snapshot-lifecycle
base: origin/feature/sachima-channel @ e907afb763165db9c7b49e51e6a15e7887938e8d
canonical before branching: feature/sachima-channel, 0 ahead / 0 behind
```

Baseline verification in the new worktree:

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

Relevant existing surfaces:

```text
gateway/flowweaver_contract.py                       # Pure v0 snapshot adapter; public schema must stay unchanged
gateway/flowweaver_shadow.py                         # Default-off shadow tap; attaches in-memory snapshot
gateway/run.py                                       # Gateway lifecycle boundary; currently calls attach_flowweaver_shadow_snapshot(...)
tests/gateway/test_flowweaver_shadow_tap.py          # Pure helper tests and no-leak invariants
tests/gateway/test_run_progress_topics.py            # Fake-agent Gateway lifecycle tests
prototypes/flowweaver_phase3/contracts/flowweaver.v0.schema.json
```

---

## Non-Goals / Hard Boundaries

Phase 4C must not do any of this:

```text
no Temporal
no Docker
no background daemon
no service startup
no Gateway restart
no live IM behavior change by default
no model/tool-loop rewrite
no public flowweaver.v0 schema mutation
no run_agent.py changes
no model_tools.py changes
no toolsets.py changes
no cli.py / hermes_cli changes
no default skill activation
no gateway/platforms/* changes
no Feishu SDK calls from FlowWeaver code
no remote branch deletion
```

Allowed paths for this PR:

```text
docs/plans/2026-05-04-flowweaver-phase4c-snapshot-lifecycle.md
docs/dev_log/2026-05-04-flowweaver-phase4c-snapshot-lifecycle.md
gateway/flowweaver_shadow.py
tests/gateway/test_flowweaver_shadow_tap.py
tests/gateway/test_run_progress_topics.py
```

`gateway/run.py` should remain untouched unless tests prove the existing Phase 4B attach seam cannot carry the new capture metadata. Prefer extending `gateway/flowweaver_shadow.py` over spreading FlowWeaver logic through the Gateway.

---

## Design: In-Memory Shadow Capture Record

Keep the existing snapshot under:

```python
FLOWWEAVER_SHADOW_SNAPSHOT_KEY = "flowweaver_shadow_snapshot"
```

Add a sibling capture record under:

```python
FLOWWEAVER_SHADOW_CAPTURE_KEY = "flowweaver_shadow_capture"
FLOWWEAVER_SHADOW_CAPTURE_TYPE = "flowweaver.gateway.shadow_capture.v0"
```

Expected capture shape:

```python
{
    "type": "flowweaver.gateway.shadow_capture.v0",
    "contract_version": "flowweaver.v0",
    "snapshot_key": "flowweaver_shadow_snapshot",
    "transaction_id": "tx_...",
    "correlation_id": "turn_...",
    "snapshot_id": "snap_...",
    "created_at": "...Z",
    "lifecycle": {
        "stage": "gateway_shadow_capture",
        "state": "captured",
        "default_enabled": False,
        "visible_side_effects": [],
    },
    "consumer": {
        "status": "ready",
        "allowed": ["in_memory_test_probe", "future_flowweaver_runtime"],
        "forbidden_side_effects": ["send", "edit", "render", "persist", "temporal"],
    },
    "audit": {
        "snapshot_safe_to_render": True,
        "public_schema_unchanged": True,
        "source_exported": False,
    },
}
```

Rules:

1. The public `flowweaver.v0` snapshot stays schema-compatible and unchanged.
2. The capture record is internal Gateway shadow metadata, not a user-facing artifact.
3. Capture IDs must exactly match the attached snapshot IDs.
4. Consumer access must fail closed when the snapshot/capture pair is missing, malformed, or mismatched.
5. The capture record must not include platform, chat, user, message IDs, raw command text, stdout/stderr, card JSON, source objects, delivery payloads, or secret-shaped strings.
6. Existing visible render behavior remains unchanged: shadow capture must not enqueue progress panels, alter legacy progress lines, send messages, edit messages, persist events, or log the capture.

---

## TDD Task Plan

### Task 0: Persist this approved plan and initial dev log

**Files:**

- Create: `docs/plans/2026-05-04-flowweaver-phase4c-snapshot-lifecycle.md`
- Create: `docs/dev_log/2026-05-04-flowweaver-phase4c-snapshot-lifecycle.md`

**Verification:**

```bash
git check-ignore -v docs/plans/2026-05-04-flowweaver-phase4c-snapshot-lifecycle.md docs/dev_log/2026-05-04-flowweaver-phase4c-snapshot-lifecycle.md || true
git diff --check
git add docs/plans/2026-05-04-flowweaver-phase4c-snapshot-lifecycle.md docs/dev_log/2026-05-04-flowweaver-phase4c-snapshot-lifecycle.md
git commit -m "docs: plan FlowWeaver phase 4C snapshot lifecycle" \
  -m "Plan: docs/plans/2026-05-04-flowweaver-phase4c-snapshot-lifecycle.md"
```

### Task 1: RED — pure shadow capture lifecycle tests

**Files:**

- Modify: `tests/gateway/test_flowweaver_shadow_tap.py`

**Tests:**

```text
test_shadow_tap_attaches_lifecycle_capture_for_consumers
test_shadow_consumer_view_requires_matching_snapshot_and_capture_ids
test_shadow_capture_omits_source_delivery_payloads_and_secret_shapes
```

**Expected RED:**

```text
ImportError or AssertionError because FLOWWEAVER_SHADOW_CAPTURE_KEY / get_flowweaver_shadow_capture do not exist yet.
```

**RED command:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_tap.py -q
```

### Task 2: GREEN — implement pure capture seam

**Files:**

- Modify: `gateway/flowweaver_shadow.py`

**Implementation notes:**

- Add `FLOWWEAVER_SHADOW_CAPTURE_KEY` and `FLOWWEAVER_SHADOW_CAPTURE_TYPE`.
- Build capture metadata only from the already-sanitized snapshot, never from `source`, delivery payload records, or raw progress fields.
- Attach capture only after snapshot construction succeeds.
- Remove both snapshot and capture on capture failure.
- Add `get_flowweaver_shadow_capture(agent_result)` that returns a small consumer view only when snapshot/capture IDs match exactly; otherwise return `None`.
- Keep fail-closed behavior: helper paths must never raise into Gateway runtime.

**Verification:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_tap.py tests/gateway/test_flowweaver_contract_adapter.py -q
```

### Task 3: RED — Gateway lifecycle capture integration test

**Files:**

- Modify: `tests/gateway/test_run_progress_topics.py`

**Test:**

```text
test_flowweaver_shadow_tap_attaches_consumer_capture_without_visible_side_effects
```

**Expected RED:**

```text
KeyError or AssertionError because Gateway shadow results currently only expose flowweaver_shadow_snapshot.
```

**RED command:**

```bash
scripts/run_tests.sh tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_tap_attaches_consumer_capture_without_visible_side_effects -q
```

### Task 4: GREEN — minimal integration

**Files:**

- Prefer: `gateway/flowweaver_shadow.py` only
- Avoid unless necessary: `gateway/run.py`

**Implementation notes:**

- If `attach_flowweaver_shadow_snapshot(...)` attaches capture in the helper, Gateway wiring should not need changes.
- Verify visible progress remains unaffected for `shadow on/off × task_tracker on/off × tool_progress off/all` surfaces already covered by Phase 4B tests.

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
final-candidate secret scan: scan final candidate content and added lines; do not scan stale removed lines from intermediate commits
```

Independent reviews:

```text
1. spec / low-intrusion review: verify default-off behavior, no public schema mutation, no Gateway runtime takeover, no Temporal/service work.
2. security / display / no-leak review: verify capture metadata cannot leak source IDs, raw commands, stdout/stderr, card JSON, delivery payloads, or secret-shaped strings.
```

PR requirements:

```text
push branch: feat/flowweaver-phase4c-snapshot-lifecycle
open PR against: feature/sachima-channel
include: scope, boundaries, TDD evidence, focused gate output, review evidence, missed-test reflection
```

---

## Risks / Tradeoffs

- **Risk:** Capture metadata becomes a second public contract by accident.
  **Mitigation:** Keep it internal, explicitly typed as Gateway shadow capture, and do not mutate `flowweaver.v0`.

- **Risk:** IDs or delivery ACKs leak platform/chat/user details.
  **Mitigation:** Build capture only from sanitized public snapshot IDs and static lifecycle constants; add no-leak regressions.

- **Risk:** Gateway wiring expands.
  **Mitigation:** Prefer helper-only implementation; stop if `gateway/run.py` changes become necessary beyond the existing call seam.

- **Risk:** Future consumers treat capture as permission to send/render.
  **Mitigation:** Include explicit forbidden side effects in capture and enforce a consumer-view helper that is read-only/fail-closed.
