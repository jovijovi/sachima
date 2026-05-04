# FlowWeaver Phase 4G — Mock Durable Consumer Dev Log

Timestamp: 2026-05-04 23:15:41 CST +0800

## Scope

Plan a default-off, pure, in-memory Phase 4G step that validates the Phase 4F consumer descriptor and replay corpus can be projected into future durable `Transaction / Intent / Artifact / Delivery` record shapes.

This phase should add a mock durable consumer after approval. It must consume only safe Phase 4F descriptor/corpus aggregate outputs, not raw snapshots, captures, agent results, platform payloads, card JSON, raw command/output, delivery ACKs, or platform identifiers.

Phase 4G design-only status: no implementation code has been written in Phase 4G yet.

No Temporal/runtime wiring is planned.
No visible sends/edits are planned.
No persistence, service startup, Docker, daemon startup, or Gateway restart is planned.

## Branch and worktree

```text
branch: feat/flowweaver-phase4g-mock-durable-consumer
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase4g-mock-durable-consumer
base: origin/feature/sachima-channel @ dbb27c05a8628266056b702b7a53e97bb4ca3524
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

These were not copied into the Phase 4G worktree and are not part of this phase.

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
108 passed in 14.94s
```

## Context inspected

Read and used these existing surfaces to constrain the design:

```text
AGENTS.md
gateway/flowweaver_shadow.py
gateway/flowweaver_contract.py
tests/gateway/test_flowweaver_shadow_tap.py
tests/gateway/fixtures/flowweaver_shadow_replay_corpus.json
tests/gateway/test_run_progress_topics.py
docs/plans/2026-05-04-flowweaver-phase4f-replay-corpus-consumer-contract.md
docs/dev_log/2026-05-04-flowweaver-phase4f-replay-corpus-consumer-contract.md
```

Relevant existing Phase 4F state:

```text
describe_flowweaver_shadow_consumer_contract()
replay_flowweaver_shadow_corpus(agent_results, *, attempts=2)
FLOWWEAVER_SHADOW_CONSUMER_CONTRACT_TYPE = "flowweaver.gateway.shadow_consumer_contract.v0"
FLOWWEAVER_SHADOW_REPLAY_CORPUS_TYPE = "flowweaver.gateway.shadow_replay_corpus.v0"
Replay corpus verdicts: passed, failed, rejected
Replay entry verdicts: replayed, rejected, unsafe, schema_mismatch, drift_detected
Corpus output intentionally omits snapshot_ref, full snapshot, capture, transaction payload, deliveries, artifacts, platform identifiers, raw output, card JSON, and sensitive value shapes.
```

## Planned files

Allowed implementation paths planned after approval:

```text
docs/plans/2026-05-04-flowweaver-phase4g-mock-durable-consumer.md
docs/dev_log/2026-05-04-flowweaver-phase4g-mock-durable-consumer.md
gateway/flowweaver_mock_durable.py
tests/gateway/test_flowweaver_mock_durable_consumer.py
tests/gateway/test_run_progress_topics.py
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
Temporal / Docker / daemon / service / persistence / runtime wiring / Gateway restart
```

## Design status

Plan drafted:

```text
docs/plans/2026-05-04-flowweaver-phase4g-mock-durable-consumer.md
```

Planned public additions after approval:

```python
FLOWWEAVER_MOCK_DURABLE_CONSUMER_TYPE = "flowweaver.gateway.mock_durable_consumer.v0"
FLOWWEAVER_MOCK_DURABLE_ACCEPTED = "accepted"
FLOWWEAVER_MOCK_DURABLE_REJECTED = "rejected"

def consume_flowweaver_shadow_corpus_as_mock_durable_state(contract_descriptor, replay_corpus) -> dict: ...
```

The future implementation should create synthetic deterministic durable records from safe corpus entry indexes only. It should not read or copy raw snapshot/capture/agent-result payloads.

## Verification before design handoff

Plan-file ignore/whitespace/marker/sensitive-scan check:

```bash
git check-ignore -v planned files || true
git add -N docs/plans/2026-05-04-flowweaver-phase4g-mock-durable-consumer.md docs/dev_log/2026-05-04-flowweaver-phase4g-mock-durable-consumer.md
git diff --check -- docs/plans/2026-05-04-flowweaver-phase4g-mock-durable-consumer.md docs/dev_log/2026-05-04-flowweaver-phase4g-mock-durable-consumer.md
python doc marker and scan script
```

Observed:

```json
{
  "missing_markers": [],
  "changed_files": [
    "docs/dev_log/2026-05-04-flowweaver-phase4g-mock-durable-consumer.md",
    "docs/plans/2026-05-04-flowweaver-phase4g-mock-durable-consumer.md"
  ],
  "unplanned_changed_files": [],
  "added_line_secret_hits": [],
  "forbidden_path_hits": [],
  "forbidden_runtime_call_hits": []
}
```

Independent plan reviews:

```text
spec / low-intrusion review: PASS
security / no-leak review: PASS
```

Reviewer notes:

```text
No concrete blockers. The design is coherent, testable, design-only, and stays inside the pure in-memory helper boundary with descriptor + safe corpus aggregate inputs only.
No concrete no-leak blockers. The plan explicitly avoids raw snapshots/captures/agent results/platform payloads and treats durable record labels as synthetic mock records only.
```

Because this dev log was updated after those checks, the final plan checks must be rerun before commit.

## Implementation status

Not started. Design-only phase is in progress.

No implementation code has been written in Phase 4G yet.
No implementation tests have been written in Phase 4G yet.
No production runtime files have been changed in Phase 4G yet.
