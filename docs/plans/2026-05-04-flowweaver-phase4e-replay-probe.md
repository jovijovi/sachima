# FlowWeaver Phase 4E Replay Probe / Consumer Contract Hardening Implementation Plan

> **For Hermes:** Execute only after design approval. Use strict TDD: RED tests first, minimal implementation, focused verification, independent review, then PR.

**Goal:** Add a default-off, in-memory replay probe that proves the Phase 4C/4D `snapshot_ref + capture + audit` consumer seam can be read repeatedly and safely without mutation, leakage, persistence, rendering, sends, edits, Temporal, or Gateway behavior changes.

**Architecture:** Phase 4E stays inside the existing `gateway/flowweaver_shadow.py` pure helper boundary. It adds a replay-probe envelope built from existing safe audit output and consumer-view validation. Gateway integration tests call the helper against the already-returned in-memory `agent_result`; no runtime wiring change is required.

**Tech Stack:** Python, pytest, existing `gateway/flowweaver_shadow.py`, existing `gateway/flowweaver_contract.py`, existing `tests/gateway/test_flowweaver_shadow_tap.py`, existing `tests/gateway/test_run_progress_topics.py`.

---

## Current Context / Evidence

Timestamp: 2026-05-04 18:31:29 CST +0800

Branch/worktree:

```text
repo: /home/ubuntu/workspace/hermes/repo/sachima
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase4e-replay-probe
branch: feat/flowweaver-phase4e-replay-probe
base: origin/feature/sachima-channel @ 12b9addd2ec04890150ee85259d7f8014e28b4da
canonical before branching: feature/sachima-channel, 0 ahead / 0 behind
open PRs before branching: none
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
90 passed in 15.29s
```

Relevant surfaces:

```text
gateway/flowweaver_shadow.py                         # Phase 4B/4C/4D shadow helper, capture, audit
gateway/flowweaver_contract.py                       # Pure flowweaver.v0 snapshot adapter; public schema must remain compatible
tests/gateway/test_flowweaver_shadow_tap.py          # Pure helper + no-leak tests
tests/gateway/test_run_progress_topics.py            # Fake-agent Gateway lifecycle tests
prototypes/flowweaver_phase3/contracts/flowweaver.v0.schema.json
```

---

## Non-Goals / Hard Boundaries

Phase 4E must not do any of this:

```text
no Temporal
no Docker
no daemon or service startup
no Gateway restart
no live IM behavior change by default
no public flowweaver.v0 schema mutation
no run_agent.py changes
no model_tools.py changes
no toolsets.py changes
no cli.py / hermes_cli changes
no gateway/run.py changes unless existing seam cannot support the integration test; if that happens, stop and redesign
no gateway/platforms/* changes
no Feishu SDK calls
no sends / edits / renders / persistence / logging from replay helpers
no remote branch deletion
```

Allowed paths for this PR:

```text
docs/plans/2026-05-04-flowweaver-phase4e-replay-probe.md
docs/dev_log/2026-05-04-flowweaver-phase4e-replay-probe.md
gateway/flowweaver_shadow.py
tests/gateway/test_flowweaver_shadow_tap.py
tests/gateway/test_run_progress_topics.py
```

---

## Design: Shadow Replay Probe

Keep Phase 4D audit behavior unchanged:

```python
audit_flowweaver_shadow_capture(agent_result) -> {
    "type": "flowweaver.gateway.shadow_audit.v0",
    "verdict": "ready" | "rejected" | "unsafe" | "schema_mismatch",
    "reason": "ok" | "missing_or_invalid_consumer_view" | "unsafe_snapshot" | "schema_mismatch",
    "snapshot_ref": {"snapshot_key": ..., "transaction_id": ..., "correlation_id": ..., "snapshot_id": ...} | None,
    "checks": {...booleans...},
    "side_effects": [],
}
```

Add a pure replay-probe helper:

```python
FLOWWEAVER_SHADOW_REPLAY_TYPE = "flowweaver.gateway.shadow_replay_probe.v0"
FLOWWEAVER_SHADOW_REPLAY_REPLAYED = "replayed"
FLOWWEAVER_SHADOW_REPLAY_REJECTED = "rejected"
FLOWWEAVER_SHADOW_REPLAY_UNSAFE = "unsafe"
FLOWWEAVER_SHADOW_REPLAY_SCHEMA_MISMATCH = "schema_mismatch"
FLOWWEAVER_SHADOW_REPLAY_DRIFT_DETECTED = "drift_detected"


def replay_flowweaver_shadow_capture(
    agent_result: Mapping[str, Any],
    *,
    attempts: int = 2,
) -> dict[str, Any]: ...
```

Expected replay-probe output shape:

```python
{
    "type": "flowweaver.gateway.shadow_replay_probe.v0",
    "verdict": "replayed",
    "reason": "ok",
    "snapshot_ref": {
        "snapshot_key": "flowweaver_shadow_snapshot",
        "transaction_id": "tx_...",
        "correlation_id": "turn_...",
        "snapshot_id": "snap_...",
    },
    "replay_count": 2,
    "checks": {
        "audit_ready": True,
        "consumer_view_valid": True,
        "snapshot_ref_stable": True,
        "audit_stable": True,
        "input_not_mutated": True,
        "side_effects_absent": True,
    },
    "side_effects": [],
}
```

Verdict rules:

```text
replayed        = every replay attempt audits ready, returns the same safe snapshot_ref, and exposes no side effects.
rejected        = missing capture/snapshot pair, invalid pair, disabled shadow, invalid attempts, hostile Mapping, or audit rejected.
unsafe          = audit classified unsafe.
schema_mismatch = audit classified schema_mismatch.
drift_detected  = repeated reads produce different safe audit envelopes or snapshot refs.
```

Output rules:

1. Replay output must not include full snapshot, caller-owned capture object, transaction payload, deliveries, artifacts, platform/chat/user/message IDs, source object, raw command, stdout/stderr, card JSON, or secret-shaped strings.
2. Replay helper must not mutate `agent_result`.
3. Replay helper must not call send/edit/render/persist/log/Temporal or enqueue progress.
4. Replay helper should depend on safe existing helpers (`audit_flowweaver_shadow_capture` and `get_flowweaver_shadow_capture`) instead of re-opening unsafe payloads unnecessarily.
5. Any hostile or nondeterministic mapping must fail closed to `rejected` or `drift_detected` without leaking attacker-controlled values.
6. The public `flowweaver.v0` schema remains unchanged.

---

## TDD Task Plan

### Task 0: Persist this approved plan and initial dev log

**Files:**

- Create: `docs/plans/2026-05-04-flowweaver-phase4e-replay-probe.md`
- Create: `docs/dev_log/2026-05-04-flowweaver-phase4e-replay-probe.md`

**Verification:**

```bash
git check-ignore -v docs/plans/2026-05-04-flowweaver-phase4e-replay-probe.md docs/dev_log/2026-05-04-flowweaver-phase4e-replay-probe.md || true
git diff --check
```

### Task 1: RED — pure replay probe tests

**Files:**

- Modify: `tests/gateway/test_flowweaver_shadow_tap.py`

**Tests to add before implementation:**

```text
test_shadow_replay_probe_replays_safe_capture_without_returning_capture_or_snapshot
test_shadow_replay_probe_rejects_missing_invalid_or_bad_attempt_counts
test_shadow_replay_probe_propagates_audit_unsafe_and_schema_mismatch
test_shadow_replay_probe_detects_unstable_snapshot_ref_or_audit_output
test_shadow_replay_probe_does_not_mutate_agent_result
test_shadow_replay_probe_fails_closed_for_hostile_mapping
test_shadow_replay_probe_output_omits_delivery_payloads_platform_ids_and_secret_shapes
```

**Expected RED:**

```text
ImportError: cannot import name 'replay_flowweaver_shadow_capture'
```

**RED command:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_tap.py -q
```

### Task 2: GREEN — implement pure replay probe

**Files:**

- Modify: `gateway/flowweaver_shadow.py`

**Implementation notes:**

- Add replay constants and export them via `__all__`.
- Add `replay_flowweaver_shadow_capture(agent_result, *, attempts=2)`.
- Clamp accepted attempts to a tiny safe range, e.g. integer `1 <= attempts <= 5`; invalid values return `rejected`.
- Run the existing audit helper on each attempt; never return the capture object.
- Compare only safe audit envelopes and safe snapshot refs.
- Map audit verdicts into replay verdicts without inventing success.
- Return static sanitized reasons: `ok`, `missing_or_invalid_consumer_view`, `unsafe_snapshot`, `schema_mismatch`, `drift_detected`.
- Catch all unexpected mapping access errors and return `rejected`.
- Do not mutate `agent_result`.

**Verification:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_tap.py tests/gateway/test_flowweaver_contract_adapter.py -q
python -m py_compile gateway/flowweaver_shadow.py tests/gateway/test_flowweaver_shadow_tap.py
```

### Task 3: RED — Gateway lifecycle replay integration

**Files:**

- Modify: `tests/gateway/test_run_progress_topics.py`

**Test:**

```text
test_flowweaver_shadow_tap_replay_probe_without_visible_side_effects
```

**Expected RED:**

```text
ImportError or assertion failure because Gateway tests cannot call replay helper yet.
```

**RED command:**

```bash
scripts/run_tests.sh tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_tap_replay_probe_without_visible_side_effects -q
```

### Task 4: GREEN — prove replay via existing Gateway seam

**Files:**

- Prefer: `gateway/flowweaver_shadow.py` only
- Modify test only: `tests/gateway/test_run_progress_topics.py`

**Implementation notes:**

- Existing Gateway `_run_agent` already returns `agent_result` with shadow snapshot/capture when `flowweaver_shadow=true`.
- Integration test should call replay helper on the returned `agent_result`.
- Assert replay verdict is `replayed`.
- Assert replay output has no `snapshot` or `capture` keys.
- Assert visible sends/edits remain empty when `tool_progress=off`, `task_tracker.enabled=false`, and `flowweaver_shadow=true`.
- Do not modify `gateway/run.py` unless this cannot be achieved through the existing seam; if that happens, stop and ask for redesign approval.

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
python -m py_compile \
  gateway/flowweaver_shadow.py \
  gateway/flowweaver_contract.py \
  gateway/run.py \
  tests/gateway/test_flowweaver_shadow_tap.py \
  tests/gateway/test_run_progress_topics.py

git diff --check
```

Deterministic scans:

```text
forbidden-surface scan: no run_agent.py/model_tools.py/toolsets.py/cli.py/hermes_cli/main.py/gateway/platforms/*/skills/*/optional-skills/*/schema changes
added-line/final-candidate secret scan: clean
```

Independent reviews:

```text
1. spec / low-intrusion review: default-off, no runtime side effects, no Gateway/run wiring, no public v0 schema mutation.
2. security / display / no-leak review: replay output cannot leak full snapshot, capture, delivery ACK, platform/message IDs, source, raw command, stdout/stderr, card JSON, or secret-shaped strings; hostile mappings fail closed.
```

PR requirements:

```text
push branch: feat/flowweaver-phase4e-replay-probe
open PR against: feature/sachima-channel
include: scope, boundaries, TDD evidence, focused gate output, review evidence, missed-test reflection
```

---

## Approval Gate

Stop after this plan is saved and verified. Implementation starts only after the user approves the Phase 4E design.
