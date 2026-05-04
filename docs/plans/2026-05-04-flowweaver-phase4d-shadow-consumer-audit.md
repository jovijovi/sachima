# FlowWeaver Phase 4D Shadow Consumer Audit Implementation Plan

> **For Hermes:** Execute with strict TDD. The user approved Phase 4D execution on 2026-05-04 after PR #20 was merged and locally cleaned up.

**Goal:** Add a default-off, in-memory audit harness that proves the Phase 4C `snapshot_ref + capture` consumer seam can be safely consumed without re-exporting full snapshots, delivery ACKs, platform IDs, or runtime side effects.

**Architecture:** Phase 4D stays inside the Gateway shadow helper boundary. It does not mutate the public `flowweaver.v0` contract or `gateway/run.py`; it adds pure read-only audit functions to `gateway/flowweaver_shadow.py` and tests them through both pure helper cases and existing fake-agent Gateway lifecycle tests.

**Tech Stack:** Python, pytest, existing `gateway/flowweaver_shadow.py`, existing `gateway/flowweaver_contract.py`, existing `tests/gateway/test_flowweaver_shadow_tap.py`, existing `tests/gateway/test_run_progress_topics.py`.

---

## Current Context / Evidence

Timestamp: 2026-05-04 16:49:06 CST +0800

Branch/worktree:

```text
repo: /home/ubuntu/workspace/hermes/repo/sachima
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase4d-shadow-consumer-audit
branch: feat/flowweaver-phase4d-shadow-consumer-audit
base: origin/feature/sachima-channel @ 2090f68e645498019662ef56e786ae1bd4082c42
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
80 passed in 15.20s
```

Relevant surfaces:

```text
gateway/flowweaver_shadow.py                         # Phase 4B/4C shadow helper and consumer seam
gateway/flowweaver_contract.py                       # Pure flowweaver.v0 snapshot adapter; must remain public-schema compatible
tests/gateway/test_flowweaver_shadow_tap.py          # Pure helper + no-leak tests
tests/gateway/test_run_progress_topics.py            # Fake-agent Gateway lifecycle tests
prototypes/flowweaver_phase3/contracts/flowweaver.v0.schema.json
```

---

## Non-Goals / Hard Boundaries

Phase 4D must not do any of this:

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
no sends / edits / renders / persistence / logging from audit helpers
no remote branch deletion
```

Allowed paths for this PR:

```text
docs/plans/2026-05-04-flowweaver-phase4d-shadow-consumer-audit.md
docs/dev_log/2026-05-04-flowweaver-phase4d-shadow-consumer-audit.md
gateway/flowweaver_shadow.py
tests/gateway/test_flowweaver_shadow_tap.py
tests/gateway/test_run_progress_topics.py
```

`gateway/run.py` should remain untouched. If the Gateway lifecycle test cannot pass through the existing Phase 4B/4C helper seam, stop and redesign instead of adding runtime wiring.

---

## Design: Shadow Consumer Audit Harness

Keep Phase 4C consumer view behavior:

```python
get_flowweaver_shadow_capture(agent_result) -> {
    "snapshot_ref": {
        "snapshot_key": "flowweaver_shadow_snapshot",
        "transaction_id": "tx_...",
        "correlation_id": "turn_...",
        "snapshot_id": "snap_...",
    },
    "capture": {...},
} | None
```

Add a pure audit helper:

```python
FLOWWEAVER_SHADOW_AUDIT_TYPE = "flowweaver.gateway.shadow_audit.v0"
FLOWWEAVER_SHADOW_AUDIT_READY = "ready"
FLOWWEAVER_SHADOW_AUDIT_REJECTED = "rejected"
FLOWWEAVER_SHADOW_AUDIT_UNSAFE = "unsafe"
FLOWWEAVER_SHADOW_AUDIT_SCHEMA_MISMATCH = "schema_mismatch"


def audit_flowweaver_shadow_capture(agent_result: Mapping[str, Any]) -> dict[str, Any]: ...
```

Expected audit shape:

```python
{
    "type": "flowweaver.gateway.shadow_audit.v0",
    "verdict": "ready",
    "reason": "ok",
    "snapshot_ref": {
        "snapshot_key": "flowweaver_shadow_snapshot",
        "transaction_id": "tx_...",
        "correlation_id": "turn_...",
        "snapshot_id": "snap_...",
    },
    "checks": {
        "consumer_view_valid": True,
        "ids_match": True,
        "contract_version_valid": True,
        "snapshot_safe_to_render": True,
        "public_schema_unchanged": True,
        "source_not_exported": True,
        "side_effects_absent": True,
    },
    "side_effects": [],
}
```

Verdict rules:

```text
ready           = consumer view exists, IDs match, contract/type valid, snapshot.safe_to_render true, capture audit flags true.
rejected        = missing capture/snapshot pair, malformed pair, mismatched IDs, hostile Mapping, or disabled shadow.
unsafe          = public snapshot exists but snapshot.safe_to_render is false or capture audit says source exported / side effects present.
schema_mismatch = public snapshot type/contract_version or capture type/contract_version is wrong.
```

Output rules:

1. Audit output must be safe to return to tests/future runtime probes.
2. Audit output must not include the full snapshot, full transaction, deliveries, artifacts, operation payloads, platform, message ID, source object, raw command, stdout/stderr, card JSON, or secret-shaped strings.
3. Audit helper must fail closed and never raise on hostile `Mapping`/dict-like inputs.
4. Audit helper must not mutate `agent_result`.
5. Audit helper must not send, edit, render, persist, log, call Temporal, or enqueue progress.

---

## TDD Task Plan

### Task 0: Persist this approved plan and initial dev log

**Files:**

- Create: `docs/plans/2026-05-04-flowweaver-phase4d-shadow-consumer-audit.md`
- Create: `docs/dev_log/2026-05-04-flowweaver-phase4d-shadow-consumer-audit.md`

**Verification:**

```bash
git check-ignore -v docs/plans/2026-05-04-flowweaver-phase4d-shadow-consumer-audit.md docs/dev_log/2026-05-04-flowweaver-phase4d-shadow-consumer-audit.md || true
git diff --check
git add docs/plans/2026-05-04-flowweaver-phase4d-shadow-consumer-audit.md docs/dev_log/2026-05-04-flowweaver-phase4d-shadow-consumer-audit.md
git commit -m "docs: plan FlowWeaver phase 4D shadow consumer audit" \
  -m "Plan: docs/plans/2026-05-04-flowweaver-phase4d-shadow-consumer-audit.md"
```

### Task 1: RED — pure audit harness tests

**Files:**

- Modify: `tests/gateway/test_flowweaver_shadow_tap.py`

**Tests:**

```text
test_shadow_audit_ready_for_safe_consumer_view
test_shadow_audit_rejects_missing_or_mismatched_pair
test_shadow_audit_marks_unsafe_snapshot_as_unsafe
test_shadow_audit_marks_contract_or_capture_type_mismatch_as_schema_mismatch
test_shadow_audit_fails_closed_for_hostile_mapping
test_shadow_audit_output_omits_full_snapshot_delivery_payloads_and_secret_shapes
test_shadow_audit_accepts_failed_cancelled_blocked_and_pending_lifecycle_states
```

**Expected RED:**

```text
ImportError: cannot import name 'audit_flowweaver_shadow_capture'
```

**RED command:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_tap.py -q
```

### Task 2: GREEN — implement pure audit helper

**Files:**

- Modify: `gateway/flowweaver_shadow.py`

**Implementation notes:**

- Add audit constants and export them via `__all__`.
- Reuse `get_flowweaver_shadow_capture(...)` for the happy path.
- Inspect the full snapshot internally only to classify verdict; never copy full snapshot data into audit output.
- Return static, sanitized `reason` values such as `ok`, `missing_or_invalid_consumer_view`, `unsafe_snapshot`, `schema_mismatch`.
- Build `checks` from booleans only.
- Catch all unexpected mapping access errors and return `rejected`.
- Do not mutate `agent_result`.

**Verification:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_tap.py tests/gateway/test_flowweaver_contract_adapter.py -q
```

### Task 3: RED — Gateway lifecycle audit integration

**Files:**

- Modify: `tests/gateway/test_run_progress_topics.py`

**Test:**

```text
test_flowweaver_shadow_tap_audit_ready_without_visible_side_effects
```

**Expected RED:**

```text
ImportError or KeyError because Gateway tests cannot call the audit helper yet.
```

**RED command:**

```bash
scripts/run_tests.sh tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_tap_audit_ready_without_visible_side_effects -q
```

### Task 4: GREEN — minimal integration via existing helper seam

**Files:**

- Prefer: `gateway/flowweaver_shadow.py` only
- Modify test only: `tests/gateway/test_run_progress_topics.py`

**Implementation notes:**

- Existing Gateway `_run_agent` already attaches snapshot + capture through `attach_flowweaver_shadow_snapshot(...)`.
- The audit helper should operate on the returned in-memory `agent_result`; no Gateway wiring should be necessary.
- Assert no visible progress sends/edits when `tool_progress=off`, `task_tracker.enabled=false`, and `flowweaver_shadow=true`.

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
forbidden-surface scan: no run_agent.py/model_tools.py/toolsets.py/cli.py/hermes_cli/main.py/gateway/platforms/*/skills/*/optional-skills/*/schema changes
added-line/final-candidate secret scan: clean
```

Independent reviews:

```text
1. spec / low-intrusion review: default-off, no runtime side effects, no Gateway/run wiring, no public v0 schema mutation.
2. security / display / no-leak review: audit output cannot leak full snapshot, delivery ACK, platform/message IDs, source, raw command, stdout/stderr, card JSON, or secret-shaped strings; hostile mappings fail closed.
```

PR requirements:

```text
push branch: feat/flowweaver-phase4d-shadow-consumer-audit
open PR against: feature/sachima-channel
include: scope, boundaries, TDD evidence, focused gate output, review evidence, missed-test reflection
```

---

## Risks / Tradeoffs

- **Risk:** Audit helper quietly becomes a public runtime API.  
  **Mitigation:** Type it as Gateway shadow audit, keep it default-off/in-memory, and avoid persistence/rendering.

- **Risk:** Audit output leaks what consumer view intentionally withheld.  
  **Mitigation:** Output only `snapshot_ref`, verdict, static reason, boolean checks, and empty side-effect list.

- **Risk:** Audit classification relies on broad exception swallowing.  
  **Mitigation:** Fail closed to `rejected`; tests cover hostile mappings.

- **Risk:** Scenario matrix becomes too broad for this PR.  
  **Mitigation:** Cover consumer safety in pure tests and only one Gateway lifecycle integration path; do not modify runtime wiring.
