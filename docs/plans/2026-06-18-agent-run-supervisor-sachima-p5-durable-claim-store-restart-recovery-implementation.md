# P5 durable claim-store / restart-recovery local/offline implementation

Date: 2026-06-18
Branch: `feat/p5-durable-claim-store-restart-recovery`
Status: PR #150 open (https://github.com/jovijovi/sachima/pull/150); live GitHub PR metadata, checks, and mergeability are authoritative.

## Scope

This slice extends the merged P5 local/offline runtime adapter with a caller-supplied durable claim-store and restart-recovery proof while preserving the same fake/injected, default-off, local/offline boundary.

It adds:

- `P5LocalOfflineDurableClaimStore` in `sachima_supervisor/p5_runtime_adapter.py`
- optional `claim_store=` injection on `P5LocalOfflineRuntimeAdapter`
- package export from `sachima_supervisor/__init__.py`
- TDD coverage in `tests/sachima_supervisor/test_p5_runtime_adapter.py`

## Strongest current meaning

The strongest approved claim is:

> A caller can provide a local JSON claim store, execute a deterministic fake step once, construct a fresh adapter against the same store path, and replay/query/recover the prior sanitized completed step without relaunching the fake runtime. Conflicting replay after restart fails closed before launch. Dirty resident store state fails closed before launch. Rejected unsafe input values are not persisted to history bytes or claim-store file bytes.

This is still a local/offline implementation gate. It proves restart/replay semantics for the adapter seam; it does not approve or start a real runtime, Worker, Temporal service, Gateway lifecycle, live IM behavior, production config, or real delivery.

## Implementation details

`P5LocalOfflineDurableClaimStore`:

- is constructed explicitly by the caller with a local file path
- persists sanitized projections only:
  - idempotency key
  - run id
  - step id
  - fingerprint
  - state
  - snapshot version
  - sanitized `StepExecutionOutcome`
  - sanitized history events
- restores `_records_by_idem`, `_records_by_step`, and sanitized history when a fresh adapter is constructed
- writes through a temporary file plus atomic replace for a deterministic local file update
- fail-closes with `runtime_adapter_store_invalid` when an existing store projection is malformed, unsafe, duplicate, wrong schema, wrong type, or otherwise not accepted
- never connects to or starts an external runtime surface

`P5LocalOfflineRuntimeAdapter`:

- keeps existing default-off exact-token behavior
- keeps in-memory operation unchanged when no claim store is supplied
- treats claim-store load errors as no-throw fail-closed `StepExecutionOutcome` results
- persists each sanitized event after state changes when a claim store is supplied
- replays recovered idempotent outcomes without incrementing `launch_count`

## TDD evidence

RED was confirmed before implementation:

```text
/home/ecs-user/.local/bin/pytest tests/sachima_supervisor/test_p5_runtime_adapter.py -q -k 'durable_claim_store'
5 failed, 25 deselected in 0.26s
Failure reason: AttributeError: module 'sachima_supervisor.p5_runtime_adapter' has no attribute 'P5LocalOfflineDurableClaimStore'
```

GREEN focused durable tests:

```text
/home/ecs-user/.local/bin/pytest tests/sachima_supervisor/test_p5_runtime_adapter.py -q -k 'durable_claim_store'
9 passed, 25 deselected in 0.14s
```

Full focused adapter tests:

```text
/home/ecs-user/.local/bin/pytest tests/sachima_supervisor/test_p5_runtime_adapter.py -q
34 passed in 0.20s
```

Focused compatibility/regression tests:

```text
/home/ecs-user/.local/bin/pytest tests/sachima_supervisor/test_p5_runtime_adapter.py tests/sachima_supervisor/test_ai_flow_orchestration.py tests/sachima_supervisor/test_ai_flow_store.py -q
70 passed in 0.31s
```

Static/compile gates at this point:

```text
uv run --extra dev ruff check sachima_supervisor/p5_runtime_adapter.py tests/sachima_supervisor/test_p5_runtime_adapter.py sachima_supervisor/__init__.py
All checks passed!

python3 -m compileall -q sachima_supervisor tests/sachima_supervisor
PASS
```

## Tests added

The durable/restart-recovery tests cover:

1. replay after fresh adapter construction from the same local claim-store path, with no fake relaunch
2. conflict after restart fail-closing with `runtime_adapter_idempotency_conflict` and zero relaunch
3. `recover(...)` after restart returning the sanitized completed snapshot without relaunch
4. dirty resident store projection fail-closing with `runtime_adapter_store_invalid` and zero launch
5. unsafe rejected input values absent from both serialized history bytes and claim-store file bytes

Existing P5 adapter tests still cover default-off exact token behavior, idempotency, WP4 `StepExecutor` compatibility, no-throw malformed inputs, no-leak marker variants, query snapshot stability, active-run cancellation WATCH, and forbidden runtime-surface static guards.

## Boundaries preserved

This slice does **not** approve:

- real runtime or Worker start
- external Temporal/Worker lifecycle
- P6 controlled AI FLOW execution
- write-capable roles
- Gateway-owned or auto-started lifecycle
- Feishu/IM/live behavior
- production config writes
- public ingress
- real delivery

## Known limits / next gates

This is a local JSON claim-store implementation for the fake/injected adapter seam. It is not a production database adapter, not a distributed lock, and not an external runtime history bridge. Any external durable backend attachment, real Worker/Temporal lifecycle, controlled AI FLOW execution, or live delivery remains a separate future approval.

## Full local gates

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

## Blocker review fix notes

Codex blocker review found three issues before PR creation: durable write failure returned success, duplicate `(run_id, step_id)` resident records were not rejected, and the roadmap next-allowed-request prose still pointed at the old PR #149 branch. The fix added regression tests for write failure, duplicate step records, and dirty history events, then changed the adapter/store to fail closed before launch and tightened the roadmap wording.

Regression proof:

```text
/home/ecs-user/.local/bin/pytest tests/sachima_supervisor/test_p5_runtime_adapter.py -q -k 'write_failure or duplicate_step_records or dirty_history_event'
3 passed, 30 deselected in 0.11s
```

A second Codex re-review found one more restart conflict blocker: after restart, the same `(run_id, step_id)` with a different idempotency key could relaunch and create a dirty duplicate-step store. The fix adds a regression and rejects restored step conflicts with `runtime_adapter_step_conflict` before launch.

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
