# FlowWeaver Phase 4F Replay Corpus / Consumer Contract Hardening Implementation Plan

> **For Hermes:** Execute only after design approval. Use strict TDD: RED tests first, minimal implementation, focused verification, independent review, then PR.

**Goal:** Harden the Phase 4D/4E `snapshot_ref + capture + audit + replay` consumer seam with an explicit safe consumer contract descriptor and a replay corpus harness, still default-off, in-memory, read-only, and side-effect-free.

**Architecture:** Phase 4F stays in the existing `gateway/flowweaver_shadow.py` pure-helper boundary and test surfaces. It adds static contract metadata and a corpus-level replay aggregator that consumes already-built in-memory `agent_result` mappings through the Phase 4E replay helper; it does not add Temporal, persistence, runtime orchestration, Gateway production wiring, platform adapter behavior, sends, edits, renders, logs, or service restarts.

**Tech Stack:** Python, pytest, existing `gateway/flowweaver_shadow.py`, existing `gateway/flowweaver_contract.py`, existing `tests/gateway/test_flowweaver_shadow_tap.py`, existing `tests/gateway/test_run_progress_topics.py`, new sanitized test corpus fixture under `tests/gateway/fixtures/`.

---

## Current Context / Evidence

Timestamp: 2026-05-04 21:21:11 CST +0800

Branch/worktree:

```text
repo: /home/ubuntu/workspace/hermes/repo/sachima
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase4f-replay-corpus-contract
branch: feat/flowweaver-phase4f-replay-corpus-contract
base: origin/feature/sachima-channel @ 313852193cca71f9a4a4253fef9838fdd6b3426a
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
99 passed in 14.79s
```

Relevant existing surfaces:

```text
gateway/flowweaver_shadow.py                         # Phase 4B/4C/4D/4E shadow capture, audit, replay helpers
gateway/flowweaver_contract.py                       # Pure flowweaver.v0 snapshot adapter; public schema must remain compatible
tests/gateway/test_flowweaver_shadow_tap.py          # Pure helper + no-leak + replay tests
tests/gateway/test_run_progress_topics.py            # Fake-agent Gateway lifecycle tests
prototypes/flowweaver_phase3/contracts/flowweaver.v0.schema.json
```

---

## Non-Goals / Hard Boundaries

Phase 4F must not do any of this:

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
no sends / edits / renders / persistence / logging from corpus or contract helpers
no remote branch deletion
```

Allowed paths for the implementation PR:

```text
docs/plans/2026-05-04-flowweaver-phase4f-replay-corpus-consumer-contract.md
docs/dev_log/2026-05-04-flowweaver-phase4f-replay-corpus-consumer-contract.md
gateway/flowweaver_shadow.py
tests/gateway/test_flowweaver_shadow_tap.py
tests/gateway/test_run_progress_topics.py
tests/gateway/fixtures/flowweaver_shadow_replay_corpus.json
```

If any required behavior appears to need `gateway/run.py`, `gateway/platforms/*`, `run_agent.py`, external storage, or Temporal, stop and redesign before writing production code.

---

## Design: Explicit Safe Consumer Contract Descriptor

Add a pure static descriptor helper in `gateway/flowweaver_shadow.py`:

```python
FLOWWEAVER_SHADOW_CONSUMER_CONTRACT_TYPE = "flowweaver.gateway.shadow_consumer_contract.v0"
FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE = "flowweaver.gateway.shadow_replay_corpus.v0"
FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED = "passed"
FLOWWEAVER_SHADOW_REPLAY_CORPUS_FAILED = "failed"
FLOWWEAVER_SHADOW_REPLAY_CORPUS_REJECTED = "rejected"


def describe_flowweaver_shadow_consumer_contract() -> dict[str, Any]: ...
```

Expected descriptor shape:

```python
{
    "type": "flowweaver.gateway.shadow_consumer_contract.v0",
    "contract_version": "flowweaver.v0",
    "snapshot_key": "flowweaver_shadow_snapshot",
    "capture_key": "flowweaver_shadow_capture",
    "capture_type": "flowweaver.gateway.shadow_capture.v0",
    "audit_type": "flowweaver.gateway.shadow_audit.v0",
    "replay_type": "flowweaver.gateway.shadow_replay_probe.v0",
    "allowed_consumer_inputs": ["agent_result_mapping"],
    "allowed_consumers": ["in_memory_test_probe", "future_flowweaver_runtime"],
    "replay_verdicts": ["replayed", "rejected", "unsafe", "schema_mismatch", "drift_detected"],
    "forbidden_output_fields": [
        "snapshot",
        "capture",
        "transaction",
        "deliveries",
        "artifacts",
        "source",
        "raw_command",
        "raw_output",
        "stdout",
        "stderr",
        "card_json",
        "platform",
        "chat_id",
        "user_id",
        "message_id",
        "delivery_ack",
    ],
    "forbidden_side_effects": ["send", "edit", "render", "persist", "temporal", "log"],
    "bounds": {
        "default_replay_attempts": 2,
        "max_replay_attempts": 5,
        "max_corpus_entries": 20,
    },
    "side_effects": [],
}
```

Descriptor rules:

1. It must be deterministic and side-effect-free.
2. It must not read `agent_result` or any runtime state.
3. It must not include full snapshot/capture examples.
4. It must not include platform/chat/user/message IDs, delivery ACKs, raw commands, raw outputs, card JSON, or secret-shaped values.
5. It exists only to make the future consumer boundary explicit before Phase 5 durable orchestration design.

---

## Design: Replay Corpus Harness

Add a pure aggregate helper in `gateway/flowweaver_shadow.py`:

```python
def replay_flowweaver_shadow_corpus(
    agent_results: Sequence[Mapping[str, Any]],
    *,
    attempts: int = 2,
) -> dict[str, Any]: ...
```

Expected corpus output shape:

```python
{
    "type": "flowweaver.gateway.shadow_replay_corpus.v0",
    "verdict": "passed",  # passed | failed | rejected
    "reason": "ok",
    "entry_count": 3,
    "entries": [
        {
            "index": 0,
            "verdict": "replayed",
            "reason": "ok",
            "checks": {
                "audit_ready": True,
                "consumer_view_valid": True,
                "snapshot_ref_stable": True,
                "audit_stable": True,
                "input_not_mutated": True,
                "side_effects_absent": True,
            },
            "side_effects": [],
        },
    ],
    "side_effects": [],
}
```

Corpus verdict rules:

```text
passed   = every entry replays with verdict replayed and side_effects == []
failed   = at least one entry returns unsafe, schema_mismatch, drift_detected, or rejected
rejected = corpus input itself is invalid, too large, hostile, string/bytes, or attempts invalid
```

Corpus output rules:

1. Aggregate output must not include `snapshot_ref`; the per-entry replay helper already exposes a safe ref when needed, but corpus output should be even narrower.
2. Aggregate output must not include full snapshot, caller-owned capture object, transaction payload, deliveries, artifacts, platform/chat/user/message IDs, source object, raw command, stdout/stderr, card JSON, or secret-shaped strings.
3. The helper must not mutate corpus entries.
4. The helper must not call send/edit/render/persist/log/Temporal or enqueue progress.
5. Hostile or nondeterministic mappings must fail closed without leaking attacker-controlled values.
6. Public `flowweaver.v0` schema remains unchanged.

---

## Sanitized Replay Corpus Fixture

Create a scenario-definition fixture, not raw full snapshots:

```text
tests/gateway/fixtures/flowweaver_shadow_replay_corpus.json
```

The fixture should contain only safe scenario definitions used by tests to build in-memory `agent_result` values via the existing `attach_flowweaver_shadow_snapshot(...)` path. Do not store full snapshots, captures, deliveries, platform IDs, message IDs, card JSON, or raw tool output in the fixture.

Expected fixture shape:

```json
[
  {
    "case_id": "completed_final_text",
    "transaction_id": "session_corpus_final_text",
    "status": "completed",
    "title": "Corpus final text task",
    "final_text_sent": true,
    "rich_card_types": [],
    "expected_replay_verdict": "replayed"
  },
  {
    "case_id": "rich_card_only",
    "transaction_id": "session_corpus_rich_card",
    "status": "completed",
    "title": "Corpus rich card task",
    "final_text_sent": false,
    "rich_card_types": ["weather.v1"],
    "expected_replay_verdict": "replayed"
  },
  {
    "case_id": "blocked_pending_final_text",
    "transaction_id": "session_corpus_blocked",
    "status": "blocked",
    "title": "Corpus blocked task",
    "final_text_sent": false,
    "rich_card_types": [],
    "expected_replay_verdict": "replayed"
  }
]
```

Fixture safety rules:

1. `case_id`, `transaction_id`, and `title` must be synthetic and platform-neutral.
2. `rich_card_types` may include artifact type labels like `weather.v1`; it must not include message IDs.
3. Secret-shaped strings must be split or omitted entirely.
4. Store scenario definitions only; build snapshots/captures in tests.

---

## TDD Task Plan

### Task 0: Persist this approved plan and initial dev log

**Objective:** Record Phase 4F design and baseline before implementation.

**Files:**

- Create: `docs/plans/2026-05-04-flowweaver-phase4f-replay-corpus-consumer-contract.md`
- Create: `docs/dev_log/2026-05-04-flowweaver-phase4f-replay-corpus-consumer-contract.md`

**Verification:**

```bash
git check-ignore -v \
  docs/plans/2026-05-04-flowweaver-phase4f-replay-corpus-consumer-contract.md \
  docs/dev_log/2026-05-04-flowweaver-phase4f-replay-corpus-consumer-contract.md \
  tests/gateway/fixtures/flowweaver_shadow_replay_corpus.json || true
git diff --check
```

### Task 1: RED — consumer contract descriptor tests

**Objective:** Define the exact safe descriptor before writing implementation.

**Files:**

- Modify: `tests/gateway/test_flowweaver_shadow_tap.py`

**Tests to add before implementation:**

```text
test_shadow_consumer_contract_descriptor_is_static_safe_and_side_effect_free
test_shadow_consumer_contract_descriptor_omits_payloads_ids_and_secret_shapes
```

**Expected RED:**

```text
ImportError: cannot import name 'describe_flowweaver_shadow_consumer_contract'
```

**RED command:**

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_shadow_tap.py::test_shadow_consumer_contract_descriptor_is_static_safe_and_side_effect_free \
  tests/gateway/test_flowweaver_shadow_tap.py::test_shadow_consumer_contract_descriptor_omits_payloads_ids_and_secret_shapes \
  -q
```

### Task 2: GREEN — implement consumer contract descriptor

**Objective:** Add only static metadata and exports.

**Files:**

- Modify: `gateway/flowweaver_shadow.py`

**Minimal implementation:**

- Add constants:
  - `FLOWWEAVER_SHADOW_CONSUMER_CONTRACT_TYPE`
  - `FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE`
  - `FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED`
  - `FLOWWEAVER_SHADOW_REPLAY_CORPUS_FAILED`
  - `FLOWWEAVER_SHADOW_REPLAY_CORPUS_REJECTED`
- Add `describe_flowweaver_shadow_consumer_contract()`.
- Export all new public constants/helpers in `__all__`.

**GREEN command:**

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_shadow_tap.py::test_shadow_consumer_contract_descriptor_is_static_safe_and_side_effect_free \
  tests/gateway/test_flowweaver_shadow_tap.py::test_shadow_consumer_contract_descriptor_omits_payloads_ids_and_secret_shapes \
  -q
python -m py_compile gateway/flowweaver_shadow.py tests/gateway/test_flowweaver_shadow_tap.py
```

### Task 3: RED — replay corpus fixture and aggregate tests

**Objective:** Prove a sanitized corpus can be replayed through the existing Phase 4E helper without returning payloads.

**Files:**

- Create: `tests/gateway/fixtures/flowweaver_shadow_replay_corpus.json`
- Modify: `tests/gateway/test_flowweaver_shadow_tap.py`

**Tests to add before implementation:**

```text
test_shadow_replay_corpus_fixture_is_synthetic_and_platform_neutral
test_shadow_replay_corpus_replays_expected_safe_scenarios
test_shadow_replay_corpus_reports_entry_verdicts_without_refs_or_payloads
test_shadow_replay_corpus_rejects_invalid_or_too_large_inputs
test_shadow_replay_corpus_fails_closed_for_unsafe_schema_mismatch_and_hostile_entries
test_shadow_replay_corpus_does_not_mutate_entries
```

**Expected RED:**

```text
ImportError: cannot import name 'replay_flowweaver_shadow_corpus'
```

**RED command:**

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_shadow_tap.py::test_shadow_replay_corpus_fixture_is_synthetic_and_platform_neutral \
  tests/gateway/test_flowweaver_shadow_tap.py::test_shadow_replay_corpus_replays_expected_safe_scenarios \
  tests/gateway/test_flowweaver_shadow_tap.py::test_shadow_replay_corpus_reports_entry_verdicts_without_refs_or_payloads \
  tests/gateway/test_flowweaver_shadow_tap.py::test_shadow_replay_corpus_rejects_invalid_or_too_large_inputs \
  tests/gateway/test_flowweaver_shadow_tap.py::test_shadow_replay_corpus_fails_closed_for_unsafe_schema_mismatch_and_hostile_entries \
  tests/gateway/test_flowweaver_shadow_tap.py::test_shadow_replay_corpus_does_not_mutate_entries \
  -q
```

### Task 4: GREEN — implement replay corpus aggregate helper

**Objective:** Add the smallest pure aggregate around `replay_flowweaver_shadow_capture(...)`.

**Files:**

- Modify: `gateway/flowweaver_shadow.py`

**Implementation rules:**

1. Accept only a non-string `Sequence` of mappings.
2. Reject `attempts` using the existing replay bounds.
3. Reject corpus inputs larger than 20 entries.
4. For each entry, call `replay_flowweaver_shadow_capture(entry, attempts=attempts)`.
5. Copy only `index`, `verdict`, `reason`, `checks`, and `side_effects` into aggregate entry output.
6. Never copy `snapshot_ref`, `snapshot`, `capture`, `transaction`, `deliveries`, `artifacts`, source objects, or raw strings into the aggregate output.
7. Return `passed` only if every entry verdict is `replayed`; return `failed` for entry-level failures; return `rejected` for invalid corpus input.

**GREEN command:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_tap.py -q
python -m py_compile gateway/flowweaver_shadow.py tests/gateway/test_flowweaver_shadow_tap.py
```

### Task 5: RED/GREEN — Gateway lifecycle corpus integration regression

**Objective:** Verify corpus aggregation can consume a real Gateway-returned shadow result without visible side effects.

**Files:**

- Modify: `tests/gateway/test_run_progress_topics.py`

**Test to add before any integration code:**

```text
test_flowweaver_shadow_tap_replay_corpus_without_visible_side_effects
```

**Expected behavior:**

- Run existing fake-agent Gateway lifecycle with:
  - `display.tool_progress: off`
  - `display.task_tracker.enabled: false`
  - `display.task_tracker.flowweaver_shadow: true`
- Build corpus list as `[result]`.
- Call `replay_flowweaver_shadow_corpus([result], attempts=2)`.
- Assert aggregate verdict `passed`.
- Assert adapter `sent == []` and `edits == []`.
- Assert aggregate output omits `snapshot`, `capture`, `deliveries`, `artifacts`, `om_`, `oc_`, `ou_`, `chat`, `user`, `message`.

**Focused command:**

```bash
scripts/run_tests.sh \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_tap_replay_corpus_without_visible_side_effects \
  -q
```

### Task 6: Final focused gate and scans

**Objective:** Verify the Phase 4F implementation has no regressions or leakage.

**Files:**

- All changed files from allowed list only.

**Commands:**

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_shadow_tap.py \
  tests/gateway/test_flowweaver_contract_adapter.py \
  tests/gateway/test_delivery_state.py \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/test_rich_weather_delivery.py \
  -q
python -m py_compile \
  gateway/flowweaver_shadow.py \
  tests/gateway/test_flowweaver_shadow_tap.py \
  tests/gateway/test_run_progress_topics.py
git diff --check
```

Run changed-file, forbidden-surface, and secret scans over final diff:

```text
changed files must be exactly the allowed paths
forbidden surfaces must have no hits in production runtime files
secret-shaped values must have no hits in added lines or final candidate files
```

### Task 7: Independent reviews and PR

**Objective:** Catch contract or leakage problems before PR.

**Review passes:**

1. Spec / low-intrusion review:
   - Does Phase 4F remain default-off, pure, in-memory, and test-only/runtime-inert?
   - Does it avoid Gateway production behavior changes?
   - Does it avoid Temporal and persistence?
2. Security / no-leak review:
   - Does descriptor/corpus output omit raw snapshot/capture/transaction/deliveries/artifacts/source/platform IDs/message IDs/secrets?
   - Can hostile mappings or corpus entries leak attacker-controlled values?
   - Are fixture definitions synthetic and platform-neutral?

**If a reviewer reports a blocker:**

1. Add a RED regression test first.
2. Confirm failure.
3. Fix minimally.
4. Rerun focused test and final gate.
5. Update dev log.
6. Re-review the blocker.

**PR body must include:**

- summary
- plan path
- dev log path
- tests/verification
- low-intrusion proof
- no runtime impact
- no Gateway restart performed
- no Temporal / no persistence / no platform adapter changes

---

## Exit Criteria for Phase 4F

Phase 4F is complete only when all are true:

1. Consumer contract descriptor exists and is tested as safe/static.
2. Replay corpus aggregate helper exists and is tested across sanitized safe scenarios and unsafe/rejected scenarios.
3. Corpus output does not include `snapshot_ref`, full snapshot, capture, transaction, deliveries, artifacts, source, platform/chat/user/message IDs, raw command/output, card JSON, or secret-shaped values.
4. Gateway lifecycle corpus regression passes without visible sends/edits.
5. `flowweaver.v0` public schema is unchanged.
6. No Temporal, persistence, service startup, Gateway restart, or platform adapter changes are introduced.
7. Focused gate, `py_compile`, `git diff --check`, forbidden-surface scan, and secret scan pass.
8. Independent spec/low-intrusion and security/no-leak reviews pass.

---

## Why This Is the Right Step Before Phase 5

Phase 4E proves a single safe capture can be replayed repeatedly. Phase 4F turns that into a reusable evidence gate: a future durable consumer must satisfy a static contract descriptor and pass a corpus, not just one happy-path test.

This keeps Phase 5 honest. If the contract/corpus cannot stay clean, adding Temporal would only persist confusion. If Phase 4F passes, Phase 5 can start from a stronger, measurable boundary.

---

## Approval Gate

Stop here after saving this plan and initial dev log. Do not implement code from this plan until 狗哥 explicitly approves execution.

Recommended handoff prompt:

```text
Plan complete and saved. Ready to execute Phase 4F: Replay corpus / consumer contract hardening. Shall I proceed?
```
