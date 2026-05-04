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

Not started. This is a design-only step until 狗哥 explicitly approves execution.

Explicit status markers:

```text
no implementation code has been written in Phase 4F yet
no visible sends/edits are planned or allowed by this design
```
