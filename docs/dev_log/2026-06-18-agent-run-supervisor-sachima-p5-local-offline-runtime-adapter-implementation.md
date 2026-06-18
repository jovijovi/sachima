# Dev log — P5 local/offline runtime adapter implementation

Date: 2026-06-18
Branch: `feat/p5-local-offline-runtime-adapter`
Status: merged in PR #149 (`58d1b9b87f6f68bd8099a2d7695edbacdaf6716e`, mergedAt 2026-06-18T08:11:31Z); live GitHub PR metadata remains authoritative.

## User approval

User approved opening the implementation PR for the P5 local/offline runtime adapter slice.

Approved scope: local/offline, caller-owned, fake/injected runtime adapter behind the existing WP4 `StepExecutor` Protocol seam, default-off, with no real runtime/Worker start and no live/Gateway/Feishu/production/real-delivery behavior.

## Preflight

Live truth before implementation:

- `release/sachima` already contained PR #148 merge commit `eaf4e51ede1e44f4fe1af32807b5f787991b757c`.
- Open PR count was 0 before this branch.
- The next eligible request after PR #148 was a separately approved local/offline, caller-owned fake/injected runtime-adapter implementation behind the WP4 executor Protocol seam.

Worktree created:

```text
/home/ecs-user/workspace/hermes/worktrees/sachima/feat-p5-local-offline-runtime-adapter
branch: feat/p5-local-offline-runtime-adapter
base: sachima/release/sachima
```

CodeGraph was initialized and reported the index up to date for the worktree.

## TDD RED

Claude Code was used as main programmer for RED test creation only, with the exact model string `claude-opus-4-8[1m]`, max effort, and an explicit RED-only instruction.

Focused RED command:

```text
/home/ecs-user/.local/bin/pytest tests/sachima_supervisor/test_p5_runtime_adapter.py -q
```

Observed RED result:

```text
13 failed, 1 skipped in 0.21s
```

Expected failure class:

```text
ModuleNotFoundError: No module named 'sachima_supervisor.p5_runtime_adapter'
```

The test file collected cleanly; the failures were missing API/module behavior, not harness syntax failure.

## GREEN implementation

Implemented:

- `sachima_supervisor/p5_runtime_adapter.py`
- exports in `sachima_supervisor/__init__.py`

Core behavior:

- `P5LocalOfflineRuntimeAdapter.execute(...)` implements the existing `StepExecutor` seam.
- Exact approval token and `enabled=True` are required for successful fake outcomes.
- Disabled or wrong-token requests return no-throw fail-closed `StepExecutionOutcome` values.
- Identical starts replay the stored sanitized outcome and do not increment `launch_count`.
- Incompatible idempotency replay returns `runtime_adapter_idempotency_conflict` and does not launch again.
- `query(...)` returns a stable sanitized snapshot and never reinvokes the fake runtime.
- `cancel(..., scope="active_run")` preserves unconfirmed active-run WATCH with `cancel_ambiguous` / `active_run_cancellation_watch`.
- `history_projection()` and `serialized_history_bytes()` expose sanitized local history for JSON and byte no-leak checks.
- Canonical WP4 step IDs map to the expected output contracts so the adapter can drive the existing WP4 orchestrator path.

## GREEN verification so far

Focused P5 test:

```text
/home/ecs-user/.local/bin/pytest tests/sachima_supervisor/test_p5_runtime_adapter.py -q
25 passed in 0.18s
```

Focused compatibility/regression test:

```text
/home/ecs-user/.local/bin/pytest tests/sachima_supervisor/test_p5_runtime_adapter.py tests/sachima_supervisor/test_ai_flow_orchestration.py tests/sachima_supervisor/test_ai_flow_store.py -q
61 passed in 0.27s
```

## Safety notes

This is still an in-process fake/local adapter. It intentionally does not claim:

- cross-process transactional claim-store durability
- restart/replay across process death
- real runtime/Worker start
- external lifecycle ownership
- P6 controlled AI FLOW execution
- write-role execution
- live/Gateway/Feishu/production config
- real delivery

Those remain future gates.

## Full local gates

```text
python3 tools/sync_roadmap_status.py --check
# docs/roadmap/current-status.md: machine status block is up to date

/home/ecs-user/.local/bin/pytest tests/sachima_supervisor -q
# 652 passed in 2.94s

/home/ecs-user/.local/bin/uv run --extra dev ruff check sachima_supervisor/p5_runtime_adapter.py tests/sachima_supervisor/test_p5_runtime_adapter.py sachima_supervisor/__init__.py
# All checks passed!

python3 -m compileall -q sachima_supervisor tests/sachima_supervisor
# PASS

git diff --check
# PASS

custom forbidden runtime surface scan
# forbidden_runtime_surface_scan=PASS

custom secret marker scan
# secret_marker_scan=PASS

codegraph sync/status
# index up to date
```

## PR metadata

- Codex repo-aware read-only blocker re-review returned `VERDICT: PASS` / `BLOCKERS: None` on the current live diff after the malformed resolved-input no-throw fix.
- PR #149 merged at `https://github.com/jovijovi/sachima/pull/149` (`58d1b9b87f6f68bd8099a2d7695edbacdaf6716e`, mergedAt 2026-06-18T08:11:31Z).
- PR #149 CI/review/merge completed; the follow-on P5 durable claim-store / restart-recovery gate is tracked separately in PR #150.
