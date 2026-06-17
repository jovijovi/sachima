# WP4 — Controlled AI FLOW local/offline implementation (slice 1) dev log

Date: 2026-06-17
Branch: `feat/wp4-controlled-ai-flow-local-offline-implementation`
Base: `release/sachima`
Status: **Implementation PR candidate on this branch — NOT merged.**

## Scope and approval

Implements the first WP4 controlled AI FLOW slice under the exact operator token:

```text
approve_agent_run_supervisor_sachima_controlled_ai_flow_local_offline_orchestration_implementation_read_only_roles_only_bounded_steps_injected_fakes_first_no_real_workflow_execution_no_additional_acpx_invocation_no_write_roles_no_auto_routing_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

Strictly local/offline, default-off, injected fakes only. No real workflow
execution, no additional acpx/npx, no write roles, no auto-routing, no
Gateway/Feishu/live/production config/real delivery. The architecture packet
§8 TDD plan (T1–T9) was executed RED→GREEN task by task.

## What landed

A caller-owned local/offline workflow orchestrator split by FR-area (per the
architecture packet's reviewability decision), each module owning its own copied
sanitization primitives and importing only the **public** role-binding constants
from `activity_controlled_exec`:

| Module | FR | Responsibility |
|---|---|---|
| `ai_flow_spec.py` | FR1 | `validate_workflow_spec` — exact-typed, fail-closed; accepts the canonical bounded linear read-only flow (`architect → programmer_candidate → reviewer`); rejects wrong schema, cycles, duplicate/unknown steps, undeclared edges, fan-out beyond linear, missing/unknown/future role keys, non-read/search capabilities, and hostile `str`/`dict`/`list` subclasses. Plus `workflow_spec_digest`, `role_binding_digest`, `canonical_read_only_workflow_mapping`. |
| `ai_flow_artifacts.py` | FR3 | `ArtifactRef` + `verify_artifact_ref` claim-check: digest format, byte bound, kind, producer, optional body re-hash; sanitized projection. |
| `ai_flow_gates.py` | FR2/FR6 | 4 fail-closed gate types; granted only on exact `operator_gate=True` + safe (and matching) ref; unsafe refs dropped from the record. |
| `ai_flow_store.py` | FR4 | `AiFlowRunStore` lock-guarded CAS over run/step/gate/artifact/cancel records; `claim_step`/`finalize_step`; `step_fingerprint` binds exactly the FR4 set; validate-on-read on every read. |
| `ai_flow_executor.py` | FR5 | `StepExecutor` Protocol + `StepExecutionOutcome` dataclass only; no real runner; cancellation channel mirrors `SessionInterruptOutcome`. |
| `ai_flow_evidence.py` | FR7 | Deterministic sanitized `WorkflowEvidence`; non-approval flags; active-run WATCH marker; `final_verdict ∈ {succeeded, failed, cancelled, parked, ambiguous_fail_closed}`. |
| `activity_ai_flow_orchestration.py` | FR2/FR4/FR5/FR6 | Public API: `create_workflow_run`, `step_workflow_run`, `query_workflow_run`, `list_workflow_steps`, `request_workflow_cancellation`, `summarize_workflow_run`; `AI_FLOW_APPROVAL_TOKEN`. |

`scripts/sachima_ai_flow_local_smoke.py` is `--self-test` (injected fakes) only;
without the flag it exits `2` because real execution is unapproved.
`sachima_supervisor/__init__.py` adds the new public names to `__all__`.

## TDD RED/GREEN by task

Each task wrote the focused test first, confirmed RED for the missing module/
behavior, then implemented minimal code to GREEN.

- **T1** spec — RED: `ModuleNotFoundError`; GREEN: 21 passed.
- **T2** artifacts — RED: module missing; GREEN: 10 passed.
- **T3** gates — RED: module missing; GREEN: 8 passed.
- **T4** store — RED: module missing; GREEN: 8 passed, incl. a 32-thread
  concurrency proof that identical concurrent `claim_step` calls acquire exactly
  once and the rest replay.
- **T5** executor — RED: module missing; GREEN: 3 passed. The import-isolation
  test measures the *delta* the seam introduces beyond the existing package
  baseline (the package already loads stdlib `socket` transitively via
  `importlib.metadata` in the pre-existing `supervisor_library`, which WP4 does
  not touch) and asserts `agent_run_supervisor`/`acpx`/`npx` never load.
- **T6** evidence — RED: module missing; GREEN: 6 passed.
- **T7+T8** orchestration — RED: module missing; GREEN: 22 passed (happy path +
  exactly 3 executor calls; admission/pre-step/post-step gate failures;
  idempotent replay = no second call; conflicting replay fails closed
  pre-execute; between-step cancel deterministic; active-run cancel confirmed vs
  WATCH; reviewer blocker regressions for mid-step cancellation, cancel-id
  conflict downgrade prevention, and post-recheck/pre-artifact cancellation).
- **T9** smoke + exports — `--self-test` exits `0` with 5/5 checks; no-arg exits
  `2`; package exports resolve.

## Cancellation posture (WP3b WATCH preserved)

- **Between-step** cancellation is deterministic: run → terminal `cancelled`, no
  relaunch, `active_run_cancellation_watch` stays `False`.
- **Active-run** cancellation claims `cancelled` **only** when the injected
  interrupt outcome reports `interrupted=True and cleanup_verified=True`;
  otherwise it records `cancel_ambiguous` / `active_run_cancellation_watch`, with
  no artifact propagation and no relaunch, and the evidence packet surfaces the
  WATCH marker. A later same-`cancel_id` request cannot downgrade that WATCH to
  a clean cancellation. The real WP3b cancellation bridge is **not** wired in.
- Final blocker repair: cancellation record + run-status transition now happens
  in one store lock, and artifact finalization also treats any resident
  cancellation record for the run as non-schedulable, so a lagging run-status
  projection cannot leak artifacts.
- Final status repair: `tools/sync_roadmap_status.py` resolves the repository
  remote before reading `base_head`, so local Sachima worktrees whose `origin`
  points at upstream Hermes Agent no longer fall back to the PR head.

## Verification (all from repo root)

- `scripts/run_tests.sh tests/sachima_supervisor` → **17 files, 622 tests passed, 0 failed**.
- `python3 scripts/sachima_ai_flow_local_smoke.py --self-test` → exit `0`, 5/5 checks; no-arg → exit `2`.
- `ruff check` (all WP4 source + script + `__init__.py`) → clean.
- `python3 -m compileall` (all WP4 modules + script) → clean.
- `git diff --check` → clean.
- Forbidden-surface static scan → clean (no `subprocess`/`socket`/`acpx`/`npx`/
  `requests`/`httpx`/`urllib`/Gateway/Feishu/Temporal imports or calls;
  `agent_run_supervisor` appears only inside the approval-token string; the
  remaining hits are docstring prose).
- Changed-file allowlist → only `sachima_supervisor/ai_flow_*.py`,
  `activity_ai_flow_orchestration.py`, `__init__.py`, the self-test script,
  tests, and docs. No Gateway/Feishu/platform/production-config/live surface.

## Non-approvals / tails

- This slice approves no real workflow execution, no additional acpx/npx, no
  write roles, no auto-routing, and no Gateway/Feishu/live/production config/real
  delivery.
- The WP3b active-run cancellation **WATCH** is carried forward, not closed.
- Hermes owns git commit, PR, CI, blocker review, and the Feishu approval card.
  This branch is an implementation PR candidate; it is **not** merged.
