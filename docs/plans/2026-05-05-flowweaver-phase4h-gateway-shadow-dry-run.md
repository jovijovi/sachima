# FlowWeaver Phase 4H Gateway Shadow Dry-Run Implementation Plan

> **For Hermes:** Execute implementation only after design approval. This document is the design handoff for Phase 4H; do not write implementation code until the user explicitly approves the execution gate.

**Goal:** Add a default-off Gateway shadow dry-run that runs the already-safe Phase 4F replay corpus plus Phase 4G mock durable consumer inside the Gateway lifecycle without changing visible IM behavior.

**Architecture:** Phase 4H introduces a narrow dry-run seam at the existing FlowWeaver shadow-capture point in `gateway/run.py`. When explicitly enabled by config, the Gateway attaches the safe shadow snapshot/capture, runs a pure in-memory dry-run helper over the current response, and stores only a narrow safe dry-run summary on the in-memory `agent_result` dict. It does not send, edit, render, persist, log raw payloads, start services, or integrate Temporal.

**Tech Stack:** Python, pytest, existing `gateway/flowweaver_shadow.py`, `gateway/flowweaver_mock_durable.py`, focused Gateway fake-agent lifecycle tests in `tests/gateway/test_run_progress_topics.py`.

---

## Current Context / Evidence

Timestamp: 2026-05-05 01:33:35 CST +0800

Branch/worktree:

```text
repo: /home/ubuntu/workspace/hermes/repo/sachima
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase4h-gateway-shadow-dry-run
branch: feat/flowweaver-phase4h-gateway-shadow-dry-run
base: origin/feature/sachima-channel @ 083bf8d3f95da43669aba1ac084d48466f9caa75
canonical before branching: feature/sachima-channel, 0 ahead / 0 behind
open PRs before branching: none
```

Baseline verification in the Phase 4H worktree:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_mock_durable_consumer.py \
  tests/gateway/test_flowweaver_shadow_tap.py \
  tests/gateway/test_flowweaver_contract_adapter.py \
  tests/gateway/test_delivery_state.py \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/test_rich_weather_delivery.py \
  -q
```

Observed:

```text
125 passed in 15.55s
```

Relevant existing state inspected before this plan:

```text
gateway/run.py
  existing FlowWeaver shadow config gate reads display.task_tracker.flowweaver_shadow
  existing progress tracking can be enabled for shadow collection without visible progress_queue
  existing attach_flowweaver_shadow_snapshot call is near the final response return path

gateway/flowweaver_shadow.py
  describe_flowweaver_shadow_consumer_contract()
  replay_flowweaver_shadow_corpus(agent_results, *, attempts=2)
  safe audit/replay/corpus outputs omit raw snapshots, captures, platform IDs, payloads, card JSON, output, ACKs

gateway/flowweaver_mock_durable.py
  consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, replay_corpus)
  exact-shape descriptor/corpus validation and synthetic durable records only

tests/gateway/test_run_progress_topics.py
  fake-agent Gateway lifecycle tests for shadow tap, replay corpus, and mock durable consumer with no visible sends/edits
```

---

## Non-Goals / Hard Boundaries

Phase 4H must not do any of this:

```text
no Temporal integration
no Docker
no daemon or service startup
no Gateway restart
no live IM behavior change by default
no public flowweaver.v0 schema mutation
no run_agent.py changes
no model_tools.py changes
no toolsets.py changes
no cli.py / hermes_cli changes
no gateway/platforms/* changes
no Feishu SDK calls
no visible sends / edits / renders from the dry-run seam
no persistence from the dry-run seam
no logging of dry-run payloads or raw values
no remote branch deletion
```

Phase 4H explicitly allows only these production code surfaces after approval:

```text
gateway/flowweaver_shadow_dry_run.py   # new pure helper module
gateway/run.py                         # existing file; narrow seam only
```

`gateway/run.py` is the only existing production file reopened by this phase, and only at the existing FlowWeaver shadow-capture seam near the final response return path. If implementation pressure requires platform adapters, service startup, external storage, Temporal, or broader Gateway control-flow changes, stop and redesign before writing code.

---

## Design: Gateway Shadow Dry-Run

Create a pure helper module:

```text
gateway/flowweaver_shadow_dry_run.py
```

Planned public surface:

```python
FLOWWEAVER_SHADOW_DRY_RUN_CONFIG_KEY = "flowweaver_shadow_dry_run"
FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY = "flowweaver_shadow_dry_run"
FLOWWEAVER_SHADOW_DRY_RUN_TYPE = "flowweaver.gateway.shadow_dry_run.v0"
FLOWWEAVER_SHADOW_DRY_RUN_PASSED = "passed"
FLOWWEAVER_SHADOW_DRY_RUN_REJECTED = "rejected"

def is_flowweaver_shadow_dry_run_enabled(task_tracker_config: object) -> bool: ...

def run_flowweaver_gateway_shadow_dry_run(agent_result: Mapping[str, Any]) -> dict[str, Any]: ...

def attach_flowweaver_gateway_shadow_dry_run(agent_result: dict[str, Any], *, enabled: bool) -> dict[str, Any] | None: ...
```

The helper is still pure and local. `attach_*` may write only the safe summary under `FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY` on the caller-owned `agent_result` dict when enabled and accepted. Rejection must remove or avoid writing the key.

### Config gate

New config key under existing task-tracker config:

```yaml
display:
  task_tracker:
    flowweaver_shadow: true
    flowweaver_shadow_dry_run: true
```

Rules:

1. `flowweaver_shadow_dry_run` defaults to false.
2. Dry-run cannot run unless the existing `flowweaver_shadow` gate is also true.
3. Dry-run must not create a visible `progress_queue`.
4. Dry-run must not make task tracker visible when `task_tracker.enabled` is false.
5. Dry-run must not replace legacy `tool_progress=all` output.

### Gateway seam

After the existing call to `attach_flowweaver_shadow_snapshot(...)` succeeds or no-throws, the approved implementation may add a narrow default-off call:

```python
if flowweaver_shadow_dry_run_enabled and isinstance(response, dict):
    attach_flowweaver_gateway_shadow_dry_run(response, enabled=True)
```

The exact variable naming can change during RED test writing, but the call must stay near the existing shadow capture block and must be wrapped fail-closed so no exception escapes the Gateway response path.

### Dry-run input rules

Accepted input is only the current in-memory `agent_result` after the existing shadow tap has attached the safe shadow snapshot/capture. The helper must internally call only these safe Phase 4F/4G surfaces:

```python
describe_flowweaver_shadow_consumer_contract()
replay_flowweaver_shadow_corpus([agent_result], attempts=2)
consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, corpus)
```

Rejected input includes:

```text
agent_result without a valid FlowWeaver shadow capture
full FlowWeaver snapshot mappings passed directly to the dry-run helper
shadow capture mappings passed directly to the dry-run helper
Gateway source/event/platform adapter objects
hostile Mapping or dict-like inputs that mutate during reads
failed/rejected replay corpus output
rejected mock durable projection
```

### Output shape

Expected accepted dry-run summary shape:

```python
{
    "type": "flowweaver.gateway.shadow_dry_run.v0",
    "verdict": "passed",
    "reason": "ok",
    "entry_count": 1,
    "replay_corpus_verdict": "passed",
    "mock_durable_verdict": "accepted",
    "record_counts": {
        "intents": 1,
        "artifacts": 1,
        "deliveries": 1,
    },
    "checks": {
        "shadow_capture_present": True,
        "consumer_contract_valid": True,
        "replay_corpus_passed": True,
        "mock_durable_accepted": True,
        "record_counts_match_entries": True,
        "payloads_absent": True,
        "visible_side_effects_absent": True,
    },
    "side_effects": [],
}
```

Rejected output must be closed and narrow:

```python
{
    "type": "flowweaver.gateway.shadow_dry_run.v0",
    "verdict": "rejected",
    "reason": "disabled" | "invalid_shadow" | "replay_failed" | "mock_durable_rejected",
    "entry_count": 0,
    "replay_corpus_verdict": None,
    "mock_durable_verdict": None,
    "record_counts": {"intents": 0, "artifacts": 0, "deliveries": 0},
    "checks": {...False/True safe booleans...},
    "side_effects": [],
}
```

Rejection output must not echo attacker-controlled values or unexpected fields.

### Important distinction

The Gateway dry-run summary may mention synthetic durable record counts, but it must not copy the full mock durable `records` object into the Gateway result unless a later design explicitly asks for it. Phase 4G already validates durable record shape; Phase 4H validates that the Gateway lifecycle can execute the safe consumer chain without visible behavior changes.

---

## Safety Invariants

1. Default-off: no new key, no new callback, and no behavior change unless `flowweaver_shadow_dry_run` is explicitly true together with `flowweaver_shadow`.
2. No visible sends, edits, renders, Feishu card patches, or fallback messages caused by dry-run.
3. No persistence: no JSONL writes, DB writes, files, event stores, or dashboard output caused by dry-run.
4. No Temporal, Docker, daemon, service startup, or Gateway restart.
5. No platform adapter imports/calls and no Feishu SDK calls.
6. No raw snapshot/capture/full mock durable record object in the dry-run summary.
7. No raw command/output/stdout/stderr/card JSON/platform/chat/user/message IDs/delivery ACKs/secrets in accepted or rejected output.
8. Hostile Mapping, equality/key-mutation tricks, and post-validation re-read attacks must fail closed without mutating caller input.
9. `side_effects` must always be `[]`.
10. `tool_progress=all` legacy output must remain legacy output; shadow dry-run must not convert it into a task panel.
11. Existing task tracker visible behavior must remain governed only by `task_tracker.enabled`, not by dry-run.
12. Feishu interactive-card surfaces must not be sent or patched by dry-run when task tracker is disabled, and dry-run must not add extra card sends/patches when task tracker is enabled.
13. Added dry-run lines in both `gateway/flowweaver_shadow_dry_run.py` and `gateway/run.py` must not add `logger`, `logging`, `print`, or exception-string logging for dry-run payloads.

---

## TDD Task Plan

### Task 0: Persist approved design plan and initial dev log

**Objective:** Record Phase 4H design, baseline, context, and approval gate before implementation.

**Files:**

- Create: `docs/plans/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md`
- Create: `docs/dev_log/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md`

**Verification:**

```bash
git check-ignore -v \
  docs/plans/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md \
  docs/dev_log/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md \
  gateway/flowweaver_shadow_dry_run.py \
  tests/gateway/test_flowweaver_shadow_dry_run.py || true
git add -N docs/plans/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md docs/dev_log/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md
git diff --check -- docs/plans/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md docs/dev_log/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md
```

### Task 1: RED — dry-run helper is absent and default-off contract is defined

**Objective:** Define the dry-run helper surface and default-off config behavior before implementation.

**Files:**

- Create: `tests/gateway/test_flowweaver_shadow_dry_run.py`

**Tests to add before implementation:**

```text
test_flowweaver_shadow_dry_run_is_disabled_by_default
test_flowweaver_shadow_dry_run_requires_existing_shadow_gate
test_flowweaver_shadow_dry_run_accepts_shadow_agent_result_summary
```

**Expected RED:**

```text
ModuleNotFoundError: No module named 'gateway.flowweaver_shadow_dry_run'
```

**RED command:**

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_shadow_dry_run.py::test_flowweaver_shadow_dry_run_is_disabled_by_default \
  tests/gateway/test_flowweaver_shadow_dry_run.py::test_flowweaver_shadow_dry_run_requires_existing_shadow_gate \
  tests/gateway/test_flowweaver_shadow_dry_run.py::test_flowweaver_shadow_dry_run_accepts_shadow_agent_result_summary \
  -q
```

### Task 2: GREEN — implement pure dry-run helper

**Objective:** Add the smallest pure helper that chains Phase 4F replay corpus and Phase 4G mock durable consumer into a safe summary.

**Files:**

- Create: `gateway/flowweaver_shadow_dry_run.py`

**Implementation rules:**

1. Import only safe helper surfaces from `gateway.flowweaver_shadow` and `gateway.flowweaver_mock_durable`.
2. Accept only exact plain dict inputs for attach writes; reject hostile Mapping inputs for summary generation.
3. Return only summary fields, counts, checks, verdicts, and `side_effects: []`.
4. Do not return/copy raw snapshot, capture, agent_result, replay corpus entries, or full mock durable records.
5. Mutate only by adding/removing `FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY` in `attach_*` when explicitly enabled.

**GREEN command:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_dry_run.py -q
python -m py_compile gateway/flowweaver_shadow_dry_run.py tests/gateway/test_flowweaver_shadow_dry_run.py
```

### Task 3: RED/GREEN — harden rejection and no-leak behavior

**Objective:** Fail closed for unsafe input and prove dry-run output never echoes raw fields.

**Files:**

- Modify: `tests/gateway/test_flowweaver_shadow_dry_run.py`
- Modify: `gateway/flowweaver_shadow_dry_run.py`

**Tests to add before implementation:**

```text
test_shadow_dry_run_rejects_missing_shadow_capture_without_echoing_values
test_shadow_dry_run_rejects_raw_snapshot_or_capture_inputs
test_shadow_dry_run_output_omits_payload_ids_and_sensitive_shapes
test_shadow_dry_run_does_not_mutate_inputs_on_summary_rejection
test_shadow_dry_run_rejects_hostile_mapping_and_mutating_keys
test_shadow_dry_run_rejects_flickering_inputs_without_post_validation_reread
test_shadow_dry_run_builds_summary_from_sanitized_counts_only
```

**GREEN command:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_dry_run.py -q
python -m py_compile gateway/flowweaver_shadow_dry_run.py tests/gateway/test_flowweaver_shadow_dry_run.py
```

### Task 4: RED/GREEN — Gateway lifecycle dry-run wiring

**Objective:** Wire the dry-run helper into the existing Gateway shadow seam under an explicit default-off config gate.

**Files:**

- Modify: `gateway/run.py` only near the existing FlowWeaver shadow capture block
- Modify: `tests/gateway/test_run_progress_topics.py`

**Tests to add before implementation:**

```text
test_flowweaver_shadow_dry_run_default_off_no_result_key
test_flowweaver_shadow_dry_run_requires_explicit_dry_run_gate
test_flowweaver_shadow_dry_run_runs_without_visible_side_effects
test_flowweaver_shadow_dry_run_preserves_legacy_tool_progress_when_visible
test_flowweaver_shadow_dry_run_feishu_card_mode_does_not_send_or_patch_when_tracker_disabled
```

**Expected assertions:**

```text
adapter.sent == [] when tool_progress=off and task_tracker.enabled=false
adapter.edits == [] when tool_progress=off and task_tracker.enabled=false
for Feishu card-mode with task_tracker.enabled=false: adapter.cards_sent == [] and adapter.cards_patched == []
result[FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY]["verdict"] == "passed" only when both gates are true
no snapshot/capture/platform/message identifiers in dry-run summary repr
visible legacy tool_progress=all still contains tool names and does not become a Transaction panel
```

**GREEN command:**

```bash
scripts/run_tests.sh \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_dry_run_default_off_no_result_key \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_dry_run_requires_explicit_dry_run_gate \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_dry_run_runs_without_visible_side_effects \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_dry_run_preserves_legacy_tool_progress_when_visible \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_dry_run_feishu_card_mode_does_not_send_or_patch_when_tracker_disabled \
  -q
python -m py_compile gateway/run.py tests/gateway/test_run_progress_topics.py
```

### Task 5: RED/GREEN — cross-product regression guard

**Objective:** Prove dry-run does not change visible behavior across shadow on/off, dry-run on/off, task tracker on/off, and tool progress off/all.

**Files:**

- Modify: `tests/gateway/test_run_progress_topics.py`

**Tests to add before implementation:**

```text
test_flowweaver_shadow_dry_run_config_matrix_preserves_visibility_boundaries
```

Matrix minimum:

```text
flowweaver_shadow=false, flowweaver_shadow_dry_run=true -> no dry-run key, no visible side effects
flowweaver_shadow=true, flowweaver_shadow_dry_run=false -> shadow key only, no dry-run key
task_tracker.enabled=false, tool_progress=off, both gates true -> dry-run key, no sends/edits
task_tracker.enabled=false, tool_progress=all, both gates true -> legacy tool-progress surface only
task_tracker.enabled=true, both gates true -> existing visible task tracker behavior remains governed by task_tracker.enabled
Feishu card-mode with task_tracker.enabled=false and both gates true -> no cards_sent, no cards_patched, no sent/edits
Feishu card-mode with task_tracker.enabled=true and both gates true -> dry-run adds no extra cards beyond existing tracker send/patch behavior
```

**GREEN command:**

```bash
scripts/run_tests.sh tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_dry_run_config_matrix_preserves_visibility_boundaries -q
```

### Task 6: Full focused gate, scans, and reviews

**Objective:** Prove implementation remains default-off, low-intrusion, deterministic, and clean before PR.

**Commands:**

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_shadow_dry_run.py \
  tests/gateway/test_flowweaver_mock_durable_consumer.py \
  tests/gateway/test_flowweaver_shadow_tap.py \
  tests/gateway/test_flowweaver_contract_adapter.py \
  tests/gateway/test_delivery_state.py \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/test_rich_weather_delivery.py \
  -q
python -m py_compile \
  gateway/flowweaver_shadow_dry_run.py \
  gateway/flowweaver_mock_durable.py \
  gateway/flowweaver_shadow.py \
  gateway/run.py \
  tests/gateway/test_flowweaver_shadow_dry_run.py \
  tests/gateway/test_flowweaver_mock_durable_consumer.py \
  tests/gateway/test_run_progress_topics.py
git diff --check
```

Additional scans before commit/PR:

```text
forbidden path scan: no run_agent.py, model_tools.py, toolsets.py, cli.py, hermes_cli, gateway/platforms
forbidden runtime surface scan: no Temporal/Docker/service/Gateway restart/platform SDK/send/edit/render/persist/log calls in dry-run helper or added gateway/run.py dry-run lines
forbidden logging scan: no logger/logging/print or exception-string logging in added dry-run helper or gateway/run.py dry-run lines
sensitive added-line scan: no credential-shaped values or raw private identifiers
final candidate scan: no real credentials or platform-private IDs in modified production files
```

Independent implementation reviews after code is written:

```text
spec / low-intrusion review: required
security / no-leak review: required
```

---

## Approval Gate

This plan records the design only. No implementation code should be written until the user explicitly approves Phase 4H execution after this plan/dev-log commit.

After design approval, implementation should proceed with strict RED -> GREEN -> regression -> scan -> review -> commit -> PR discipline.
