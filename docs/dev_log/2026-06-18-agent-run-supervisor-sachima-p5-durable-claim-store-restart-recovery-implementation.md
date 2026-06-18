# Dev log — P5 durable claim-store / restart-recovery local/offline implementation

Date: 2026-06-18
Branch: `feat/p5-durable-claim-store-restart-recovery`
Status: local candidate; PR not opened yet.

## User approval

User approved implementing the P5 follow-on gate: durable claim-store / restart-recovery local/offline gate.

Approved scope: local/offline, caller-owned durable claim-store and restart-recovery proof for the existing fake/injected P5 runtime adapter. The gate still forbids real runtime/Worker start, external Temporal/Worker lifecycle, P6 controlled AI FLOW execution, write roles, live/Gateway/Feishu/production config, public ingress, and real delivery.

## Preflight

Fresh live truth before implementation:

```text
PR #149 state: MERGED
PR #149 merge commit: 58d1b9b87f6f68bd8099a2d7695edbacdaf6716e
PR #149 mergedAt: 2026-06-18T08:11:31Z
release/sachima contains PR #149 merge commit: yes
current release/sachima head: 18258c81417cc3be1c55b18e7f5488c7fa94b7c1
open PR count before this branch: 0
```

Worktree:

```text
/home/ecs-user/workspace/hermes/worktrees/sachima/feat-p5-durable-claim-store-restart-recovery
branch: feat/p5-durable-claim-store-restart-recovery
base: sachima/release/sachima
```

## TDD RED

Focused RED command:

```text
/home/ecs-user/.local/bin/pytest tests/sachima_supervisor/test_p5_runtime_adapter.py -q -k 'durable_claim_store'
```

Observed RED result:

```text
5 failed, 25 deselected in 0.26s
```

Expected failure class:

```text
AttributeError: module 'sachima_supervisor.p5_runtime_adapter' has no attribute 'P5LocalOfflineDurableClaimStore'
```

The failures were the missing durable claim-store API, not a test harness error.

## GREEN implementation

Implemented:

- `P5LocalOfflineDurableClaimStore`
- optional `claim_store=` injection for `P5LocalOfflineRuntimeAdapter`
- sanitized restore/persist projections for `_Record`, `StepExecutionOutcome`, and history events
- dirty resident store validation and fail-closed `runtime_adapter_store_invalid`
- restart replay behavior that returns the stored sanitized outcome without incrementing the restarted adapter's `launch_count`
- package export in `sachima_supervisor/__init__.py`

## GREEN verification so far

Durable focused tests:

```text
/home/ecs-user/.local/bin/pytest tests/sachima_supervisor/test_p5_runtime_adapter.py -q -k 'durable_claim_store'
9 passed, 25 deselected in 0.14s
```

Full P5 adapter tests:

```text
/home/ecs-user/.local/bin/pytest tests/sachima_supervisor/test_p5_runtime_adapter.py -q
34 passed in 0.20s
```

Compatibility/regression tests:

```text
/home/ecs-user/.local/bin/pytest tests/sachima_supervisor/test_p5_runtime_adapter.py tests/sachima_supervisor/test_ai_flow_orchestration.py tests/sachima_supervisor/test_ai_flow_store.py -q
70 passed in 0.31s
```

Static/compile gates:

```text
uv run --extra dev ruff check sachima_supervisor/p5_runtime_adapter.py tests/sachima_supervisor/test_p5_runtime_adapter.py sachima_supervisor/__init__.py
All checks passed!

python3 -m compileall -q sachima_supervisor tests/sachima_supervisor
PASS
```

## Safety notes

This slice persists only sanitized local claim-store projections and history events. It does not persist raw prompt/body/material, does not expose runtime launch surfaces, and does not introduce subprocess/socket/network/Temporal/Worker/Gateway/Feishu execution paths.

Full local gates now passed:

```text
python3 tools/sync_roadmap_status.py --check --base-remote sachima
# docs/roadmap/current-status.md: machine status block is up to date

/home/ecs-user/.local/bin/pytest tests/sachima_supervisor -q
# 661 passed in 3.00s

git diff --check
# PASS

custom forbidden runtime surface / secret / stale-status scans
# PASS

codegraph sync/status
# index up to date
```

Remaining gates before approval-ready:

- Codex repo-aware read-only blocker review
- commit, push to `sachima`, open PR, wait CI, send head-SHA-bound approval card only if final head is green and review-clean

## Codex blocker round 1

Codex repo-aware read-only blocker review returned BLOCKED before PR creation. Blockers:

1. durable store write failure could still return a successful outcome and increment launch count;
2. duplicate `(run_id, step_id)` records with different idempotency keys could make `query()` and replay disagree after restart;
3. `docs/roadmap/current-status.md` next-allowed-request prose still referenced the old PR #149 branch.

Fixes applied:

- added RED regressions for write-failure fail-closed, duplicate step records, and dirty history events;
- changed successful new execution to increment `launch_count` only after durable persist succeeds;
- changed failed persist to return `runtime_adapter_store_write_failed` and fail closed;
- changed store load to reject duplicate `(run_id, step_id)` records;
- tightened history event safe-ref validation;
- updated next-allowed-request wording to this branch.

Regression command:

```text
/home/ecs-user/.local/bin/pytest tests/sachima_supervisor/test_p5_runtime_adapter.py -q -k 'write_failure or duplicate_step_records or dirty_history_event'
3 passed, 30 deselected in 0.11s
```

## Codex blocker round 2

Codex re-review found one remaining blocker: after restart, the same `(run_id, step_id)` with a different idempotency key could bypass restored idempotency lookup, relaunch, and write duplicate step records.

Fix applied:

- added RED regression `test_durable_claim_store_same_step_new_idempotency_after_restart_fails_closed`;
- added restored step-key conflict detection in `execute(...)`;
- returned `runtime_adapter_step_conflict` before fake launch and without dirtying the store.

Regression command:

```text
/home/ecs-user/.local/bin/pytest tests/sachima_supervisor/test_p5_runtime_adapter.py -q -k 'same_step_new_idempotency'
1 passed, 33 deselected in 0.11s
```

## Final Codex blocker re-review

Codex repo-aware read-only final re-review returned:

```text
VERDICT: PASS
BLOCKERS:
- none
```

Codex reran focused P5 adapter tests, full `tests/sachima_supervisor`, ruff, diff/status checks, and forbidden-source scan before the PASS.
