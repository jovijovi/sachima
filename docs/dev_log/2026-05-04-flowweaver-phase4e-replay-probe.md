# FlowWeaver Phase 4E — Replay Probe Dev Log

Timestamp: 2026-05-04 18:31:29 CST +0800

## Scope

Plan a default-off, in-memory replay probe for the Phase 4C/4D `snapshot_ref + capture + audit` consumer seam. The probe should prove repeated safe reads are stable and side-effect-free before any future durable consumer or Temporal wiring.

This phase remains shadow-only and read-only. It must not start orchestration, call Temporal, render snapshots, send messages, edit messages, persist records, log replay output, restart Gateway, mutate platform adapters, or change visible Gateway behavior.

## Branch and worktree

```text
branch: feat/flowweaver-phase4e-replay-probe
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase4e-replay-probe
base: origin/feature/sachima-channel @ 12b9addd2ec04890150ee85259d7f8014e28b4da
```

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
90 passed in 15.29s
```

## Low-intrusion boundary

Allowed paths planned:

```text
docs/plans/2026-05-04-flowweaver-phase4e-replay-probe.md
docs/dev_log/2026-05-04-flowweaver-phase4e-replay-probe.md
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
gateway/run.py
gateway/platforms/*
skills/*
optional-skills/*
prototypes/flowweaver_phase3/contracts/flowweaver.v0.schema.json
```

## Design status

Plan drafted:

```text
docs/plans/2026-05-04-flowweaver-phase4e-replay-probe.md
```

Planned helper:

```python
replay_flowweaver_shadow_capture(agent_result, *, attempts=2)
```

Planned verdicts:

```text
replayed
rejected
unsafe
schema_mismatch
drift_detected
```

## Implementation status

Pending design approval. No production code or tests have been changed yet.

## Verification before design handoff

Plan-file ignore/whitespace check:

```bash
git check-ignore -v docs/plans/2026-05-04-flowweaver-phase4e-replay-probe.md docs/dev_log/2026-05-04-flowweaver-phase4e-replay-probe.md || true
git diff --check
```

Observed:

```text
no ignore hits
git diff --check passed
```

Independent plan reviews:

```text
spec / low-intrusion review: PASS
security / no-leak review: PASS
```

Implementation remains pending design approval. No production code or tests have been changed yet.
