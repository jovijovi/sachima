# FlowWeaver Phase 4F — Replay Corpus / Consumer Contract Hardening Dev Log

Timestamp: 2026-05-04 21:21:11 CST +0800

## Scope

Plan a default-off, in-memory, read-only Phase 4F step that hardens the Phase 4D/4E `snapshot_ref + capture + audit + replay` consumer seam before any Phase 5 durable orchestration or Temporal design.

This phase should add an explicit safe consumer contract descriptor and a replay corpus aggregate harness. It must not start orchestration, call Temporal, render snapshots, send messages, edit messages, persist records, log replay output, restart Gateway, mutate platform adapters, or change visible Gateway behavior.

## Branch and worktree

```text
branch: feat/flowweaver-phase4f-replay-corpus-contract
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase4f-replay-corpus-contract
base: origin/feature/sachima-channel @ 313852193cca71f9a4a4253fef9838fdd6b3426a
```

Canonical repo before branching:

```text
path: /home/ubuntu/workspace/hermes/repo/sachima
branch: feature/sachima-channel
canonical/origin ahead-behind: 0 / 0
open PRs on base: []
```

Canonical had existing local untracked items outside this worktree:

```text
.hermes/
docs/plans/2026-04-24-sachima-channel.md
docs/superpowers/
```

These were not copied into the Phase 4F worktree and are not part of this phase.

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
99 passed in 14.79s
```

## Context inspected

Read and used these existing surfaces to constrain the design:

```text
gateway/flowweaver_shadow.py
gateway/flowweaver_contract.py
tests/gateway/test_flowweaver_shadow_tap.py
tests/gateway/test_run_progress_topics.py
docs/plans/2026-05-04-flowweaver-phase4e-replay-probe.md
docs/dev_log/2026-05-04-flowweaver-phase4e-replay-probe.md
.gitignore
```

Relevant existing Phase 4E state:

```text
replay_flowweaver_shadow_capture(agent_result, *, attempts=2)
FLOWWEAVER_SHADOW_REPLAY_TYPE = "flowweaver.gateway.shadow_replay_probe.v0"
Replay verdicts: replayed, rejected, unsafe, schema_mismatch, drift_detected
Existing replay output is safe and omits full snapshot/capture/deliveries/artifacts/platform IDs/message IDs/secret-shaped values.
Existing Gateway lifecycle test verifies replay against a fake-agent result without visible sends/edits.
```

## Planned files

Allowed implementation paths planned:

```text
docs/plans/2026-05-04-flowweaver-phase4f-replay-corpus-consumer-contract.md
docs/dev_log/2026-05-04-flowweaver-phase4f-replay-corpus-consumer-contract.md
gateway/flowweaver_shadow.py
tests/gateway/test_flowweaver_shadow_tap.py
tests/gateway/test_run_progress_topics.py
tests/gateway/fixtures/flowweaver_shadow_replay_corpus.json
```

Explicitly not planned:

```text
run_agent.py
model_tools.py
toolsets.py
cli.py
hermes_cli/*
gateway/run.py
gateway/platforms/*
prototypes/flowweaver_phase3/contracts/flowweaver.v0.schema.json
Temporal / Docker / daemon / service / persistence / runtime wiring
```

## Design status

Plan drafted:

```text
docs/plans/2026-05-04-flowweaver-phase4f-replay-corpus-consumer-contract.md
```

Planned public additions in `gateway/flowweaver_shadow.py` after approval:

```python
FLOWWEAVER_SHADOW_CONSUMER_CONTRACT_TYPE = "flowweaver.gateway.shadow_consumer_contract.v0"
FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE = "flowweaver.gateway.shadow_replay_corpus.v0"
FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED = "passed"
FLOWWEAVER_SHADOW_REPLAY_CORPUS_FAILED = "failed"
FLOWWEAVER_SHADOW_REPLAY_CORPUS_REJECTED = "rejected"

def describe_flowweaver_shadow_consumer_contract() -> dict[str, Any]: ...
def replay_flowweaver_shadow_corpus(agent_results, *, attempts=2) -> dict[str, Any]: ...
```

Planned fixture:

```text
tests/gateway/fixtures/flowweaver_shadow_replay_corpus.json
```

The fixture should store synthetic scenario definitions only, not full snapshots/captures/deliveries/platform IDs/message IDs/card JSON/raw tool output.

## Verification before design handoff

Plan-file ignore/whitespace/marker/secret-ish check:

```bash
git check-ignore -v planned files || true
git diff --check
basic doc markers passed
added-line secret-ish scan passed
```

Independent plan reviews:

```text
spec / low-intrusion review: PASS
security / no-leak review: PASS
```

Reviewer notes:

```text
No concrete blockers. The plan stays within allowed paths, remains default-off/pure/in-memory/read-only, avoids public flowweaver.v0 schema mutation and runtime Gateway/platform changes, and provides actionable RED/GREEN sequencing.
No concrete no-leak blockers. The fixture is scenario-only/synthetic, corpus output is narrower than replay output, sensitive payload/ID omissions are explicit, side effects are prohibited, and hostile/nondeterministic inputs fail closed.
```

## Implementation status

Approved by user after design handoff. Implementation proceeded under strict TDD.

### RED 1 — consumer contract descriptor absent

Added descriptor tests to `tests/gateway/test_flowweaver_shadow_tap.py`:

```text
test_shadow_consumer_contract_descriptor_is_static_safe_and_side_effect_free
test_shadow_consumer_contract_descriptor_omits_payloads_ids_and_secret_shapes
```

Command:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_shadow_tap.py::test_shadow_consumer_contract_descriptor_is_static_safe_and_side_effect_free \
  tests/gateway/test_flowweaver_shadow_tap.py::test_shadow_consumer_contract_descriptor_omits_payloads_ids_and_secret_shapes \
  -q
```

Observed expected RED:

```text
ImportError: cannot import name 'FLOWWEAVER_SHADOW_CONSUMER_CONTRACT_TYPE'
RED_EXIT_CODE=1
```

### GREEN 1 — static consumer contract descriptor

Added to `gateway/flowweaver_shadow.py`:

```text
FLOWWEAVER_SHADOW_CONSUMER_CONTRACT_TYPE
FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE
FLOWWEAVER_SHADOW_REPLAY_CORPUS_PASSED
FLOWWEAVER_SHADOW_REPLAY_CORPUS_FAILED
FLOWWEAVER_SHADOW_REPLAY_CORPUS_REJECTED
describe_flowweaver_shadow_consumer_contract()
```

Focused result:

```text
2 passed in 0.39s
py_compile passed
```

### RED 2 — replay corpus aggregate absent

Added scenario-only fixture:

```text
tests/gateway/fixtures/flowweaver_shadow_replay_corpus.json
```

Added corpus tests to `tests/gateway/test_flowweaver_shadow_tap.py`:

```text
test_shadow_replay_corpus_fixture_is_synthetic_and_platform_neutral
test_shadow_replay_corpus_replays_expected_safe_scenarios
test_shadow_replay_corpus_reports_entry_verdicts_without_refs_or_payloads
test_shadow_replay_corpus_rejects_invalid_or_too_large_inputs
test_shadow_replay_corpus_fails_closed_for_unsafe_schema_mismatch_and_hostile_entries
test_shadow_replay_corpus_does_not_mutate_entries
```

Command:

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

Observed expected RED:

```text
ImportError: cannot import name 'replay_flowweaver_shadow_corpus'
RED_EXIT_CODE=1
```

### GREEN 2 — replay corpus aggregate helper

Added `replay_flowweaver_shadow_corpus(agent_results, *, attempts=2)` to `gateway/flowweaver_shadow.py`.

The helper accepts only a bounded non-string sequence of mappings, calls the Phase 4E replay helper for each entry, returns only per-entry `index/verdict/reason/checks/side_effects`, omits `snapshot_ref`, and returns aggregate verdict `passed`, `failed`, or `rejected` without mutating inputs or exposing payloads.

Focused result:

```text
33 passed in 0.44s
py_compile passed
```

### Gateway lifecycle corpus regression

Added:

```text
test_flowweaver_shadow_tap_replay_corpus_without_visible_side_effects
```

This test consumes an actual fake-agent Gateway `agent_result` through `replay_flowweaver_shadow_corpus([result], attempts=2)` while visible progress is off and FlowWeaver shadow capture is enabled. It asserts no `send`/`edit` calls and no corpus payload leaks.

Focused result:

```text
1 passed in 1.80s
py_compile passed
```

### Initial full focused gate before dev log update

Command:

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

Observed:

```text
108 passed in 14.71s
py_compile passed
git diff --check passed
```

### Verification rerun after dev log update and synthetic-secret test-string split

The first scan correctly flagged literal fake secret-shaped assertion strings in the newly added tests. Those strings were split through string concatenation before the next gate.

Observed after the split:

```text
108 passed in 14.73s
py_compile passed
git diff --check passed
```

Scan result after the split:

```json
{
  "unplanned_changed_files": [],
  "forbidden_path_hits": [],
  "forbidden_runtime_call_hits": [],
  "added_line_secret_hits": [],
  "final_candidate_secret_hits": []
}
```

Independent implementation reviews:

```text
spec / low-intrusion review: PASS
security / no-leak review: PASS
```

Reviewer notes:

```text
No concrete blockers. Implementation stays confined to the pure gateway/flowweaver_shadow.py helper boundary plus tests/docs/fixture; no Gateway runtime wiring, platform adapter changes, public schema mutation, Temporal, persistence, or service changes were introduced.
No concrete no-leak blockers. Corpus output is narrowed to index/verdict/reason/checks/side_effects, does not copy snapshot_ref or payload objects, and fixture data is scenario-only/synthetic.
```

Because this dev log was updated after those checks, the final gate and scans must be rerun before commit.
