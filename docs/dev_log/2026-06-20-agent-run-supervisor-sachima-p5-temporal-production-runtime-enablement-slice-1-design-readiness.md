# Dev log — P5 Temporal production runtime enablement, Slice 1 design/readiness (PR A)

Date: 2026-06-20
Branch: `docs/p5-temporal-production-runtime-enablement-slice-1`
Base: `release/sachima` at `b92d259f3cb765f92b2250e06fd3ac9ba43ae5fe` (branch tip is a `[skip status-sync]` self-commit; latest non-status-sync base is PR #153 `1e84ed198340b1067d261f65381285181b4376b2`)
Status: PR A — docs-only design/readiness. No runtime started by this PR.

## Why the framing changed to production-facing

The prior P5 chain treated the durable runtime as a future, caller-supplied abstraction and explicitly held the external Temporal/Worker lifecycle token **ungranted** (P5 design/readiness, PR #147). That was the right posture while the evidence was still in-process and local-only.

That posture is now spent. The in-process and local/offline baseline is merged and green:

- WP4 `StepExecutor` Protocol seam + in-process CAS orchestrator (PR #145).
- P5 ownership / control-surface / no-leak / recovery contract (PR #147).
- P5 local/offline runtime adapter behind the seam (PR #149).
- P5 durable claim-store / restart-recovery with file-byte no-leak (PR #150, **MERGED** `21f8c1647ac9e6007183cc1f458af38bcc57fa7e`, mergedAt 2026-06-19T01:35:47Z).

Alongside it, the Temporal prototypes already prove the real-runtime contract end to end: a workflow/activity POC (`prototypes/flowweaver_phase5b_temporal_poc/`), a runtime client + control surface (`prototypes/flowweaver_phase5c_runtime_client/`), and a green integration harness running a **real Temporal Worker** that asserts no-leak across both the JSON history projection and the **serialized event-history bytes** (`tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py`). The host has a working Temporal toolchain (CLI 1.7.2 / Server 1.31.1 / UI 2.49.1) and `temporalio>=1.27.0,<2` is already declared as the `flowweaver-temporal` extra in `pyproject.toml`.

With the user's review of Hermes's recommendation, the decision is to stop treating Temporal as a hypothetical and commit to it as the production durable backend. The user **granted** the external lifecycle token, scoped to **hermetic-local + staging namespace only**. Production cluster and production traffic stay a separate future gate; P6 real agent execution inside the step body stays a separate future gate. This packet records that shift and specifies the implementation.

## Claude architect plan

The accepted direction comes from a local operator Claude Code architect plan artifact that is not committed to the repository. Its durable repo-facing conclusion is recorded here instead of storing private workstation paths in public docs.

Core direction (accepted): next stage is P5 Temporal production runtime enablement, Slice 1; promote the existing Temporal prototypes into first-class `sachima_supervisor/p5_temporal/` modules in PR B; PR A is docs-only design/readiness + manifest + status-drift cleanup; PR B implements `P5TemporalRuntimeClient`, `P5TemporalStepExecutor`, `StepWorkflow`, `step_activity`, an ops-owned `p5_temporal_worker.py`, and tests.

## What PR A changes

Docs only — four files:

- `docs/plans/2026-06-20-agent-run-supervisor-sachima-p5-temporal-production-runtime-enablement-slice-1-design-readiness.md` — the design/readiness packet: executive verdict (go directly to Temporal), the granted lifecycle token + scope, the production architecture, ops/Gateway ownership split, the PR B module map (prototype→first-class), the data/no-leak policy, Temporal semantics, the PR B tests/gates, the rollout plan, health/kill-switch/rollback, open decisions, the PR A exact scope, and the PR B ready-to-implement criteria.
- `docs/plans/2026-06-20-agent-run-supervisor-sachima-p5-temporal-production-runtime-enablement-slice-1-design-readiness-manifest.yaml` — the machine-readable manifest: approval token granted with scope, prerequisite PRs #147/#148/#149/#150 with states/merge commits, the proposed PR B files/modules, runtime-lifecycle ownership fields proving the Gateway owns neither Worker nor service, `non_approvals` all false, PR B tests/gates, and the PR #150 status-drift cleanup record.
- `docs/dev_log/2026-06-20-agent-run-supervisor-sachima-p5-temporal-production-runtime-enablement-slice-1-design-readiness.md` — this log.
- `docs/roadmap/current-status.md` — narrow prose/status-row update: record PR #150 as MERGED, retire the old open/candidate wording for that PR, and set the new current candidate to this Slice 1 design/readiness branch. The machine-owned status-sync block is left to the repo tool (it already lists #150 as merged).

PR A adds no runtime source, starts no Temporal service or Worker, runs no workflow/activity, invokes no `acpx`/`npx`/AGENT, and writes no Gateway/Feishu/production config.

## What PR B will implement

New first-class package `sachima_supervisor/p5_temporal/` (no `p5_temporal` symbols exist in the repo today, so no collisions):

- `contracts.py` — frozen sanitized dataclasses (start payload, update/activity I/O, query snapshot).
- `workflow.py` — `StepWorkflow` (`@workflow.defn`) with a `@workflow.query` snapshot and `@workflow.update` handlers carrying event-key idempotency (promoted from `FlowWeaverTransactionWorkflow`).
- `activities.py` — `step_activity` (`@activity.defn`) plus claim-check validate/deliver activities; **Slice 1 step body is controlled deterministic** (no real `acpx`); returns claim-check refs only.
- `runtime_client.py` — `P5TemporalRuntimeClient` wrapping a caller-supplied `temporalio` client (start/query/update/cancel/recover/close; duplicate-start reconcile via `WorkflowAlreadyStartedError` + query).
- `control_surface.py` — `P5TemporalControlSurface`, the safe public dispatcher with a sanitized result allowlist and no-throw wrappers.
- `step_executor.py` — `P5TemporalStepExecutor`, default-off, implementing the merged WP4 `StepExecutor` Protocol (`execute(request, *, role_binding, resolved_inputs) -> StepExecutionOutcome`) by delegating to the control surface.
- `p5_temporal_worker.py` — the **ops-owned** Worker launcher (`build_step_worker(...)` + `__main__`) that registers `StepWorkflow` + `step_activity` and polls the `sachima-p5-step-runtime` task queue; never imported by the Gateway.

Tests: `test_p5_temporal_runtime_client.py`, `test_p5_temporal_step_executor.py`, `test_p5_temporal_no_leak.py`, `test_p5_temporal_gateway_boundary.py` (static), `test_p5_temporal_determinism_replay.py`, and `tests/integration/test_p5_temporal_worker_hermetic_local.py` (promoting the phase5h real-Worker harness).

PR B gates that must pass to **merge**: hermetic-local Temporal suite (real Worker), no-leak SCAN 1 + SCAN 2, duplicate-start, recovery/restart-replay, Gateway-boundary static, determinism replay, WP3b WATCH preserved, full supervisor suite, `sync_roadmap_status --check`, forbidden-surface/secret/stale-status scans, and Codex primary blocker review `BLOCKERS: None`. Staging (`sachima-p5-staging`) is a parallel ops/canary track, not a merge blocker.

## Ownership boundary (recorded once)

Worker and Temporal service are **ops-owned** — started, scaled, and drained by ops/SRE, never by the Gateway and never by an inbound-message path. The Gateway may call the control surface only and cannot import or start the Worker/service/subprocess/socket; a Gateway-boundary static test enforces this in PR B. The caller holds a `temporalio` client (start/query/signal); ops holds the Worker (execute). The `P5TemporalStepExecutor` is default-off behind an approval-token + enable flag, so turning Temporal off falls back to the local/offline adapter and the Gateway cannot defeat the kill switch.

## Current evidence status

```text
PR #150 state: MERGED
PR #150 merge commit: 21f8c1647ac9e6007183cc1f458af38bcc57fa7e
PR #150 mergedAt: 2026-06-19T01:35:47Z
prerequisite chain: #147 (6c11a40d4de3e66981c3ff27905c1785b1709e0a),
                    #148 (eaf4e51ede1e44f4fe1af32807b5f787991b757c),
                    #149 (58d1b9b87f6f68bd8099a2d7695edbacdaf6716e),
                    #150 (21f8c1647ac9e6007183cc1f458af38bcc57fa7e) — all MERGED
open PRs in jovijovi/sachima before this branch: 0
temporal toolchain (host): CLI 1.7.2 / Server 1.31.1 / UI 2.49.1
temporalio SDK: >=1.27.0,<2 (flowweaver-temporal extra; pinned exclude-newer 2026-05-01)
no existing p5_temporal symbols in repo: confirmed
```

PR A verification is read-only and docs-only: `git diff --check`, manifest YAML parse, a stale-phrase scan proving PR #150 is recorded as MERGED with no old open/candidate residue, a forbidden implementation-surface scan on changed files, a secret/no-leak scan, `tools/sync_roadmap_status.py --check`, and Codex primary blocker review. Hermes runs the gates, commits, pushes, opens the PR, and arbitrates final evidence.

## Non-approvals (recorded once)

This packet and the granted lifecycle token do not approve: a production cluster (`sachima-p5-prod`), production traffic, P6 real `acpx`/agent execution inside `step_activity`, a Gateway-owned or auto-started Temporal/Worker/service/socket/subprocess lifecycle, write-capable roles, live Gateway/Feishu/IM behavior, real delivery, production config writes, Gateway restart/reload, platform adapter mutation, or public ingress. The WP3b active-run cancellation WATCH (PR #140) is preserved and must not be overclaimed: active-run cancellation stays best-effort, held `cancel_ambiguous` with the `active_run_watch` marker, never promoted to `cancelled` without confirmed interruption.
