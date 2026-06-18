# P5 local/offline runtime adapter implementation

Date: 2026-06-18
Branch: `feat/p5-local-offline-runtime-adapter`
Status: candidate implementation branch; PR not opened yet.

## Scope

This slice implements the first P5 **local/offline, caller-owned runtime adapter** behind the existing WP4 `StepExecutor` Protocol seam.

It adds:

- `sachima_supervisor/p5_runtime_adapter.py`
- `P5_RUNTIME_ADAPTER_IMPLEMENTATION_APPROVAL_TOKEN`
- `P5LocalOfflineRuntimeAdapter`
- package exports from `sachima_supervisor/__init__.py`
- TDD coverage in `tests/sachima_supervisor/test_p5_runtime_adapter.py`

The adapter is deliberately small: it is a deterministic fake/injected adapter that can be passed to the WP4 orchestrator as a `StepExecutor`. It returns sanitized `StepExecutionOutcome` projections, maintains local in-memory idempotency state, exposes no-throw `query` / `cancel` / `recover` / `close`-style controls, and provides sanitized JSON/history-byte projections for no-leak checks.

## Strongest current meaning

This implementation proves a **drop-in local/offline adapter seam**, not a production durable runtime.

The strongest approved claim is:

> a caller can inject a default-off P5 fake/local adapter into the existing WP4 `step_workflow_run(...)` path, run deterministic fake steps, replay identical step starts without duplicate fake launches, reject incompatible replays fail-closed, query sanitized snapshots without reinvocation, preserve active-run cancellation WATCH semantics, and scan sanitized history JSON plus serialized bytes for unsafe raw material.

## Boundaries preserved

This PR must not be interpreted as approval for:

- real runtime or Worker start
- external Temporal/Worker lifecycle
- P6 controlled AI FLOW execution
- write-capable roles
- Gateway-owned or auto-started lifecycle
- Feishu/IM/live behavior
- production config writes
- public ingress
- real delivery

The adapter is default-off and requires the exact P5 implementation approval token before it returns a successful fake step outcome. Missing/wrong token and disabled requests are no-throw, fail-closed `StepExecutionOutcome` values.

## Implementation details

`P5LocalOfflineRuntimeAdapter`:

- implements `execute(request, *, role_binding, resolved_inputs) -> StepExecutionOutcome`
- stores only sanitized local records keyed by idempotency key and `(run_id, step_id)`
- uses a request fingerprint over run/step/spec/role/input/idempotency fields to detect incompatible replay
- increments `launch_count` only for a new compatible fake start
- returns one claim-check-style artifact projection with safe keys only:
  - `artifact_id`
  - `producer_step_id`
  - `content_digest`
  - `artifact_kind`
  - `byte_count`
  - `created_at_ref`
- maps canonical WP4 step IDs to their expected output contracts so the adapter can pass the WP4 orchestrator's artifact verifier
- exposes `history_projection()` and `serialized_history_bytes()` for JSON and byte-level no-leak checks
- exposes `cancel(..., scope="active_run")` that preserves the WP3b WATCH on unconfirmed active-run cancellation: `cancel_ambiguous` + `active_run_cancellation_watch`, no artifact propagation and no relaunch

## TDD evidence

RED was confirmed before implementation:

```text
/home/ecs-user/.local/bin/pytest tests/sachima_supervisor/test_p5_runtime_adapter.py -q
13 failed, 1 skipped in 0.21s
Failure reason: ModuleNotFoundError: No module named 'sachima_supervisor.p5_runtime_adapter'
```

GREEN focused test result after implementation and Codex-blocker fixes:

```text
/home/ecs-user/.local/bin/pytest tests/sachima_supervisor/test_p5_runtime_adapter.py -q
25 passed in 0.18s
```

Focused compatibility/regression result:

```text
/home/ecs-user/.local/bin/pytest tests/sachima_supervisor/test_p5_runtime_adapter.py tests/sachima_supervisor/test_ai_flow_orchestration.py tests/sachima_supervisor/test_ai_flow_store.py -q
61 passed in 0.27s
```

## Tests added

`tests/sachima_supervisor/test_p5_runtime_adapter.py` covers:

1. exact implementation approval token
2. disabled/wrong-token no-throw failure with zero fake launches
3. duplicate execute replay converging to one launch and identical sanitized artifact projection
4. adapter used as a real WP4 `StepExecutor` in the create → step → summarize orchestrator path
5. incompatible replay failing closed with `runtime_adapter_idempotency_conflict`
6. query snapshot consistency without runtime reinvocation
7. unsafe input material rejection and no leakage into JSON projection or serialized history bytes
8. unsafe request identifier rejection across exact and alternate delimiter marker forms (`raw_prompt`, `raw-prompt`, `raw prompt`, `raw/prompt`) without projection leakage
9. malformed request/resolved-input no-throw `execute(...)` failures with `runtime_adapter_invalid_request`
10. unconfirmed active-run cancellation preserving `cancel_ambiguous` / `active_run_cancellation_watch`
11. static source scan against forbidden runtime surface tokens in the new adapter module

## Review evidence

Codex repo-aware read-only blocker re-review on the current live diff returned `VERDICT: PASS` / `BLOCKERS: None` after the malformed resolved-input no-throw fix. The review was read-only and did not claim live/runtime behavior.

## Known limits / next gates

This is still an in-process local adapter. It does **not** satisfy the full P5 durable runtime gate's cross-process transactional claim-store requirement, restart/replay proof, or external durable-history reconciliation.

If this PR passes review and merges, the next P5 request should be a separately scoped durable-claim-store / restart-recovery implementation gate, still local/offline first. P6 controlled AI FLOW execution remains blocked until durable runtime evidence is substantially stronger.
