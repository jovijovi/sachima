# P5 — Temporal production runtime enablement, Slice 1 design & readiness packet

Date: 2026-06-20
PR: [#154](https://github.com/jovijovi/sachima/pull/154) — MERGED (`f465186cc96bc182eab00b1de039ed8258f06ac8`, mergedAt 2026-06-20T05:48:26Z)
Status: **MERGED PR A — docs-only design / readiness packet.** Production-facing. This packet selects Temporal as the durable backend, records the **granted** external Temporal service / Worker lifecycle approval (scoped to **hermetic-local + staging namespace only**), and specifies the PR B implementation. PR A writes documentation only: it starts no Temporal service or Worker, runs no workflow, and touches no Gateway/Feishu/production config.
Branch: `docs/p5-temporal-production-runtime-enablement-slice-1`
Base: `release/sachima` at `b92d259f3cb765f92b2250e06fd3ac9ba43ae5fe` (branch tip; this is a `[skip status-sync]` self-commit — the latest non-status-sync first-parent base is PR #153 `1e84ed198340b1067d261f65381285181b4376b2`)

> **For Hermes:** PR A is **docs-only** — exactly the three new design/readiness artifacts plus the narrow `docs/roadmap/current-status.md` update. It starts **no** Temporal service, **no** Worker, **no** CLI/Docker/socket/subprocess, runs **no** workflow or activity, invokes **no** `acpx`/`npx`/AGENT, and writes **no** Gateway/Feishu/production config. The granted lifecycle token authorizes **PR B** to stand up a **hermetic-local** and **staging-namespace** Temporal service plus an **ops-owned** Worker — it does **not** authorize a production cluster, production traffic, P6 real agent execution, or anything in this PR A.

## Executive verdict

**Yes — go directly to Temporal as the durable runtime backend. This is production-facing work.**

The prototype evidence is already strong enough to commit: a Temporal workflow/activity proof-of-concept (`prototypes/flowweaver_phase5b_temporal_poc/`), a runtime client + control surface (`prototypes/flowweaver_phase5c_runtime_client/`), and a green integration harness that runs a **real Temporal Worker** and asserts no-leak across **both** the JSON history projection and the **serialized event-history bytes** (`tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py`). The merged WP4 controlled AI FLOW orchestrator (PR #145) already defines the `StepExecutor` Protocol seam that Temporal will plug into without redesigning the caller. The durable-runtime ownership/control-surface/no-leak/recovery contract is already specified and merged (P5 design/readiness, PR #147). The host has a working Temporal toolchain (`temporal` CLI `1.7.2`, Server `1.31.1`, UI `2.49.1`) and the `temporalio>=1.27.0,<2` SDK is already declared as the `flowweaver-temporal` extra in `pyproject.toml`.

There is no remaining reason to build an interim bespoke durable runtime. Temporal supplies exactly the primitives the goal requires — durable workflow state, retries, queries, updates, cancellation, replay-based recovery, and an auditable history — behind a caller-supplied control surface that keeps the Gateway out of the runtime lifecycle. Slice 1 promotes the proven prototypes into first-class `sachima_supervisor/p5_temporal/` modules, attaches them to the real Temporal SDK, and proves the production contract under a **hermetic-local** Temporal gate, with **staging** as a parallel ops/canary track.

The only thing held deliberately deterministic in Slice 1 is the **step body**: the `step_activity` runs a **controlled deterministic** workload, not real `acpx`/agent execution. Real agent execution inside the activity is **P6** and remains separately gated. Production cluster and production traffic remain a later, separate approval. Everything else — the durable backend choice, the real Worker, the real control surface, the hermetic-local and staging namespaces — is approved and built now.

## Granted approval and boundary

The user reviewed Hermes's recommendation and **granted** the external lifecycle token. The scope is explicit and limited:

```text
GRANTED: approve_external_temporal_service_or_worker_lifecycle_for_sachima_p5_runtime
  scope:               hermetic-local + staging namespace only
  production_cluster:  NOT approved (separate future gate)
  production_traffic:  NOT approved (separate future gate)
```

This is the central delta from the merged P5 design/readiness packet (PR #147), where that same token was recorded as **not granted**. It is now granted for hermetic-local and staging only. Under it, PR B may:

- run a hermetic-local Temporal dev server and a real Temporal Worker in CI and local dev (namespace `sachima-p5-local`);
- run an **ops-owned** Worker against a **staging** Temporal namespace (`sachima-p5-staging`) on a parallel ops/canary track.

It does **not** authorize a production cluster (`sachima-p5-prod`), production traffic, Gateway-owned/auto-started lifecycle, P6 real agent execution, write roles, live Gateway/Feishu/IM behavior, real delivery, or production config writes. Those each remain separate, named future gates (see **Open decisions** and **Explicit non-approvals**).

The other two relevant tokens, for grep/traceability:

```text
NOT GRANTED (future, separate): approve_sachima_p5_temporal_production_cluster_and_production_traffic_enablement
NOT GRANTED (future, separate): approve_sachima_p6_controlled_ai_flow_real_agent_execution_in_step_activity
```

## Status markers

```text
DESIGN_READINESS_ONLY            # this PR A
PRODUCTION_FACING
TEMPORAL_SELECTED_AS_DURABLE_BACKEND
EXTERNAL_TEMPORAL_WORKER_LIFECYCLE_GRANTED_HERMETIC_LOCAL_AND_STAGING_ONLY
WORKER_AND_SERVICE_OPS_OWNED
GATEWAY_NEVER_OWNS_WORKER_OR_SERVICE_LIFECYCLE
SLICE1_STEP_BODY_CONTROLLED_DETERMINISTIC
P6_REAL_AGENT_EXECUTION_NOT_APPROVED
PRODUCTION_CLUSTER_NOT_APPROVED
PRODUCTION_TRAFFIC_NOT_APPROVED
WRITE_ROLES_NOT_APPROVED
NO_LIVE_GATEWAY_FEISHU
NO_PRODUCTION_CONFIG_WRITE
NO_REAL_DELIVERY
PR_A_DOCS_ONLY_NO_CODE_NO_WORKER_START
WP3B_ACTIVE_RUN_CANCELLATION_WATCH_PRESERVED
```

Scoped markers (for grep / dashboard use):

```text
ARS_SACHIMA_P5_TEMPORAL_PRODUCTION_RUNTIME_ENABLEMENT_SLICE1_DESIGN_READINESS
ARS_SACHIMA_P5_TEMPORAL_BACKEND_SELECTED
ARS_SACHIMA_P5_TEMPORAL_LIFECYCLE_HERMETIC_LOCAL_AND_STAGING_ONLY
ARS_SACHIMA_P5_TEMPORAL_WORKER_OPS_OWNED
ARS_SACHIMA_P5_TEMPORAL_GATEWAY_NEVER_OWNS_LIFECYCLE
ARS_SACHIMA_P5_TEMPORAL_HISTORY_NO_LEAK_SCAN1_AND_SCAN2
ARS_SACHIMA_P5_TEMPORAL_DETERMINISM_REPLAY_REQUIRED
ARS_SACHIMA_P5_TEMPORAL_DUPLICATE_START_IDEMPOTENT
ARS_SACHIMA_P5_TEMPORAL_PRODUCTION_CLUSTER_AND_TRAFFIC_SEPARATE_GATE
ARS_SACHIMA_P6_REAL_AGENT_EXECUTION_SEPARATE_GATE
```

## Goal trace

```text
Goal: Sachima becomes Dog Brother's safe, durable, observable, recoverable IM AI workbench that runs long AI FLOW
      tasks and delivers sanitized results, surviving restarts, retries, duplicates, partial failures, and recovery.
Gap:  WP4 (PR #145) merged a caller-owned, in-process controlled AI FLOW orchestrator over a lock-guarded CAS store
      with a StepExecutor Protocol seam that has NO real runner. The P5 local/offline adapter (PR #149) and durable
      claim-store / restart-recovery slice (PR #150, MERGED) proved the seam and a caller-supplied JSON claim store,
      but in-process / local only. None of it survives a real process crash mid-run, reattaches to an in-flight run
      across processes, or provides a cross-process duplicate-start guard or a durable query/recovery surface backed
      by a real runtime. The missing capability is a real durable runtime. Temporal is selected.
Phase: P5 Temporal production runtime enablement, Slice 1. PR A = this docs-only design/readiness packet. PR B =
       first-class sachima_supervisor/p5_temporal/ modules on the real temporalio SDK, proven under a hermetic-local
       Temporal gate, with staging as a parallel ops/canary track.
Task: Promote the phase5b/phase5c prototypes into P5TemporalRuntimeClient, P5TemporalStepExecutor (implements the WP4
      StepExecutor Protocol), StepWorkflow, step_activity, a P5TemporalControlSurface, sanitized contracts, and an
      ops-owned p5_temporal_worker.py launcher; bind the no-throw control surface (start/query/update/cancel/recover/
      close) to Temporal; enforce claim-check-by-construction so only sanitized refs/digests/counts/codes enter
      Temporal history; and prove it with unit/static/integration tests, SCAN 1 + SCAN 2 no-leak, duplicate-start,
      recovery/restart-replay, a Gateway-boundary static test, and a determinism replay gate.
Test: PR A is gated by docs markers, manifest YAML parse, changed-file allowlist (docs/status only), no-secret/no-leak
      scan, forbidden implementation-surface scan, and Codex primary blocker review. PR B is gated by the hermetic-
      local Temporal suite (real Worker) plus the no-leak / duplicate-start / recovery / determinism / Gateway-boundary
      gates; staging runs in parallel as ops/canary and is not a PR B merge blocker.
Evidence: This packet + manifest + dev log + the narrow current-status update; plus the merged prerequisite chain
      PR #147 (P5 design/readiness), #148 (adapter prep), #149 (local/offline adapter), #150 (durable claim store,
      MERGED 21f8c1647ac9e6007183cc1f458af38bcc57fa7e); plus the prototype + phase5h harness referenced factually.
Decision: PR A grants the hermetic-local + staging-only Temporal lifecycle token for a later PR B implementation request,
      but PR B implementation still requires separate user approval after PR B pre-development governance. Production
      cluster/traffic and P6 real agent execution stay separately gated.
```

## Production architecture

The target runtime topology for long Sachima / FlowWeaver AI FLOW tasks:

```text
        IM surface (Sachima)                         ops / SRE
              │                                          │ owns + starts + drains
              ▼                                          ▼
  ┌─────────────────────────┐                 ┌─────────────────────────────┐
  │ Hermes Gateway          │   control-      │ Temporal service            │
  │ (render / deliver / ACK)│   surface call  │ (server 1.31.x; namespaces  │
  │  NEVER owns runtime      │   only, never   │  sachima-p5-{local,staging, │
  └───────────┬─────────────┘   lifecycle     │  prod})                     │
              │                                └───────────┬─────────────────┘
              ▼                                            │ task queue:
  ┌─────────────────────────────────────────┐             │ sachima-p5-step-runtime
  │ Sachima / FlowWeaver caller / controller │             │
  │  - owns durable-runtime choice/lifecycle │  start/query/update/cancel/recover/close
  │  - P5TemporalControlSurface (no-throw)    │◄───────────┤
  │  - P5TemporalRuntimeClient (SDK wrapper)  │            │
  │  - P5TemporalStepExecutor (WP4 seam)      │            ▼
  └───────────┬──────────────────────────────┘   ┌──────────────────────────┐
              │ delegates step execution         │ Temporal Worker          │
              ▼                                   │ (ops-owned process)      │
  ┌─────────────────────────────────────────┐    │  - StepWorkflow          │
  │ agent-run-supervisor library             │    │  - step_activity         │
  │  (sachima_supervisor/*; read-only roles, │◄───│  polls task queue,       │
  │   claim-check refs, sanitized evidence)  │    │  runs deterministic body │
  └───────────┬──────────────────────────────┘    └──────────────────────────┘
              │ refs only (never raw bytes in history)
              ▼
  ┌─────────────────────────────────────────┐
  │ Claim-check / evidence store             │
  │  (caller-owned; raw material + artifacts │
  │   keyed by sanitized ArtifactRef/digest) │
  └─────────────────────────────────────────┘
```

Component responsibilities:

- **Hermes Gateway** — renders, delivers, and reconciles ACKs in the IM surface. It may *call* the caller-owned control surface (e.g. to start or query a transaction) but it **never** owns, hosts, starts, drains, or auto-starts the Temporal service, the Worker, the task queue, a CLI, a Docker container, a socket, or a subprocess. The Gateway is a client of a control surface, never a runtime owner.
- **Sachima / FlowWeaver caller / controller** — owns the durable-runtime choice and lifecycle decision, the `P5TemporalControlSurface` (no-throw, sanitized), the `P5TemporalRuntimeClient` (a thin wrapper over a caller-supplied `temporalio` client), and the `P5TemporalStepExecutor` that satisfies the merged WP4 `StepExecutor` Protocol. It owns durable records, leases/epochs/state_version, idempotency, retry/update/cancel/recover/close policy, role mapping, and the business verdict.
- **Temporal service** — the durable backend (server `1.31.x`). Namespaces `sachima-p5-local` (hermetic/CI/dev), `sachima-p5-staging` (ops/canary), `sachima-p5-prod` (defined but **not enabled**; production traffic is a separate gate). Default retention 30 days for staging and prod.
- **Temporal Worker** — an **ops-owned** process (`p5_temporal_worker.py` launcher) that registers `StepWorkflow` and `step_activity` and polls the `sachima-p5-step-runtime` task queue. Started, scaled, and drained by ops/SRE, never by the Gateway or by a message-handling path.
- **agent-run-supervisor library** (`sachima_supervisor/*`) — the read-only role layer the activity delegates to. It produces claim-check refs and sanitized evidence; it never owns the runtime lifecycle, the claim store, or the verdict, and in Slice 1 it is exercised with a controlled deterministic step body (no real `acpx`).
- **Claim-check / evidence store** — caller-owned storage for raw material and artifacts, addressed only by sanitized `ArtifactRef`/content digest. Temporal history references these by ref; raw bytes never enter history.

## Ownership and lifecycle

This is the non-negotiable boundary, stated once:

- The **Worker** and the **Temporal service** are **ops-owned**. They are started, stopped, scaled, and drained by ops/SRE tooling (systemd/container/CLI run by an operator), never by the Gateway and never by an inbound-message code path.
- The **Gateway** may call the **control surface** only (`start`/`query`/`update`/`cancel`/`recover`/`close`). It receives sanitized, no-throw results. It cannot — by construction and by a static test (see Tests/gates) — import, start, or hold a handle to the Worker process, the Temporal service lifecycle, the task queue admin, or any subprocess/socket that would let it own runtime lifecycle.
- The **caller** (Sachima / FlowWeaver controller) owns the *decision* to attach Temporal and *which* namespace to target, but it still delegates the *process* lifecycle of the Worker to ops. The caller holds a `temporalio` **client** (to start/query/signal workflows); ops holds the **Worker** (to execute them). These are deliberately split so that no request-handling path can spawn an executor.
- **Kill switch by construction:** the `P5TemporalStepExecutor` is **default-off** behind an explicit approval-token + enable flag, exactly like `P5LocalOfflineRuntimeAdapter`. With it off, the WP4 orchestrator falls back to the in-process/local adapter and no Temporal call is made. Turning Temporal on is a caller-config decision; turning the Worker on is an ops decision. Neither is the Gateway's.

## PR B implementation target — modules and prototype→module mapping

PR B creates a new first-class package `sachima_supervisor/p5_temporal/`. No `p5_temporal*` symbols exist in the repo today (verified), so there are no naming collisions. Mapping from the proven prototypes to the production modules:

| PR B module (new) | First-class symbol | Promoted from prototype | Role |
|---|---|---|---|
| `sachima_supervisor/p5_temporal/contracts.py` | frozen sanitized dataclasses (`RuntimeStartPayload`, update/activity I/O, `QuerySnapshot`) | `flowweaver_temporal_poc/payloads.py`, `flowweaver_runtime_client/contracts.py` | sanitized wire/records contracts (refs/counts/digests/codes only) |
| `sachima_supervisor/p5_temporal/workflow.py` | `StepWorkflow` (`@workflow.defn`) | `flowweaver_temporal_poc/workflows.py` (`FlowWeaverTransactionWorkflow`) | deterministic durable workflow; `@workflow.query` snapshot; `@workflow.update` handlers with event-key idempotency |
| `sachima_supervisor/p5_temporal/activities.py` | `step_activity` (`@activity.defn`) + claim-check validate/deliver activities | `flowweaver_temporal_poc/activities.py` | the step boundary; **Slice 1 body is controlled deterministic**; returns claim-check refs only |
| `sachima_supervisor/p5_temporal/runtime_client.py` | `P5TemporalRuntimeClient` | `flowweaver_runtime_client/runtime_client.py` (`FlowWeaverRuntimeClient`) | wraps a caller-supplied `temporalio` client; `start`/`query`/`update`/`cancel`/`recover`/`close`; duplicate-start reconcile |
| `sachima_supervisor/p5_temporal/control_surface.py` | `P5TemporalControlSurface` | `flowweaver_runtime_client/control_surface.py` (`FlowWeaverRuntimeControlSurface`) | safe public dispatcher; sanitized result allowlist; no-throw wrappers |
| `sachima_supervisor/p5_temporal/step_executor.py` | `P5TemporalStepExecutor` | **new** (bridge to WP4 `StepExecutor` Protocol in `sachima_supervisor/ai_flow_executor.py`) | default-off executor implementing `execute(request, *, role_binding, resolved_inputs) -> StepExecutionOutcome` by delegating to the control surface |
| `sachima_supervisor/p5_temporal/p5_temporal_worker.py` | `build_step_worker(...)` + `__main__` launcher | `flowweaver_temporal_poc/client.py` + phase5h `open_real_worker()` harness | **ops-owned** Worker entrypoint; registers `StepWorkflow` + `step_activity`; polls `sachima-p5-step-runtime`; never imported by Gateway |
| `sachima_supervisor/p5_temporal/__init__.py` | package exports + `P5_TEMPORAL_*_APPROVAL_TOKEN` | — | explicit exports; default-off token guard |
| `sachima_supervisor/__init__.py` (modify) | re-export the new public symbols | — | keep the supervisor package surface coherent |

Tests (PR B): `tests/sachima_supervisor/test_p5_temporal_runtime_client.py`, `tests/sachima_supervisor/test_p5_temporal_step_executor.py`, `tests/sachima_supervisor/test_p5_temporal_no_leak.py`, `tests/sachima_supervisor/test_p5_temporal_gateway_boundary.py` (static), `tests/sachima_supervisor/test_p5_temporal_determinism_replay.py`, and an integration suite `tests/integration/test_p5_temporal_worker_hermetic_local.py` promoting the phase5h real-Worker reconciliation harness.

Dependency: PR B uses the existing `temporalio>=1.27.0,<2` `flowweaver-temporal` extra (already in `pyproject.toml`, pinned via `exclude-newer-package` to 2026-05-01). Python `>=3.11,<3.14`. PR B should mark the real-Worker integration tests `@pytest.mark.integration` so they are selectable for the hermetic-local gate and skippable where Temporal is absent.

## Data and no-leak policy

Temporal persists workflow inputs, activity inputs/outputs, signal/update/query payloads, and workflow state into a durable **event history**. The no-leak property is therefore enforced **by construction at the contract boundary**, not by post-hoc redaction:

- **May enter Temporal history:** stable status/error codes; mode/phase; caller-owned run/workflow/activity/step refs; role keys; claim-check refs + sha256 content digests; artifact/evidence refs + digests; counts/indices/versions; sanitized `lease_id`/`lease_epoch`; the caller verdict code; cancellation/recovery markers including the WP3b `active_run_watch` marker.
- **Must NOT enter Temporal history:** raw prompt/context/model output; raw `acpx`/ACP/agent stdout; exception text/tracebacks; PIDs/thread ids/host names; platform private ids / card JSON / message ids; media bytes / private paths; tokens / credentials / secrets / connection strings / signed URLs; delivery payloads / IM bodies.
- **Claim-check by construction:** the workflow input (`RuntimeStartPayload`) and every activity input/output carry only sanitized refs/digests/counts/codes. Raw material and artifacts live in the caller-owned claim-check/evidence store, keyed by `ArtifactRef`/digest. In P6, when `step_activity` runs real work, the role executor fetches inputs from the ref *inside* the activity and returns only a new ref + digest — the raw bytes never round-trip through history.
- **Two enforced scans (both required to pass in PR B):**
  - **SCAN 1 — JSON projection:** sanitized durable records / query snapshots / evidence JSON contain only allowed fields.
  - **SCAN 2 — serialized event-history bytes:** the real Temporal history, scanned as `history.to_json()` **and** as each event's `SerializeToString()` bytes, contains no forbidden sentinel/material. A hit is `runtime_history_leak_detected` and a kill criterion. The phase5h harness already demonstrates exactly this dual scan against a real Worker.

## Temporal runtime semantics

The control surface maps to Temporal operations as follows. Every operation is no-throw and returns a sanitized result with a stable code.

- **start** — `runtime_client.start_transaction(payload, workflow_id)` calls Temporal `start_workflow` with a deterministic `workflow_id` bound to `(run_id, step idempotency key)`. On `WorkflowAlreadyStartedError`, it queries the running workflow snapshot and reconciles: identical observable payload → `idempotent_replay` (no second execution); divergent payload → `start_conflict` / `invalid_start_payload`. Workflow ID reuse policy is set so a duplicate start is detected, not silently re-run.
- **query** — `query_snapshot(workflow_id)` calls the workflow's `@workflow.query` handler. Read-only, deterministic, returns the sanitized `QuerySnapshot` (run/step statuses, counts, refs+digests, cancellation/recovery markers). On a missing/unreachable workflow → `not_found` / `query_unavailable`.
- **update** — strongly-consistent `@workflow.update` handlers (`record_delivery_ack`, `approve_intent`, `reject_intent`, `resume_after_user_input`) carry event-key idempotency so a replayed update returns `duplicate` without mutating state again. Stale/invalid → `stale` / `update_rejected`.
- **cancel** — *between-step* cancellation may be deterministic (a `cancel_transaction` update flips a terminal flag the workflow checks before launching the next step). *Active-run* cancellation of an in-flight activity is **best-effort / WATCH** (WP3b): an unconfirmed interruption is held `cancel_ambiguous` with the `active_run_watch` marker, never promoted to `cancelled`, never propagates artifacts, never relaunches. This honesty is preserved in records, probes, and evidence.
- **recover** — after a Worker or caller process restart, the in-flight workflow continues from its durable history on the next Worker poll; the caller reattaches by `workflow_id` and reconciles via `query_snapshot`. Ambiguous reattach → `recover_ambiguous`. No reattach causes a second real execution.
- **close / terminalize** — a terminal workflow yields `closed`; a re-close is `already_terminal`. Terminal state is sanitized and append-only in records.
- **duplicate start** — covered by the `WorkflowAlreadyStartedError` reconcile above; proven by a dedicated probe (mismatched observable payload → `invalid_start_payload`, no double-launch). phase5h already asserts this against a real Worker.
- **restart / recovery** — proven by a restart-replay probe: start a workflow, drop the Worker mid-run, bring a fresh Worker up on the same task queue, and assert the run resumes from history with no duplicate execution and a consistent snapshot.

## Tests and gates for PR B

PR B merge is **blocked** by the hermetic-local Temporal gate; staging is a parallel ops/canary track (below) and is **not** a merge blocker.

1. **Unit** — `P5TemporalRuntimeClient`, `P5TemporalControlSurface`, and `P5TemporalStepExecutor` behavior with an injected fake/time-skipping Temporal client: no-throw boundary, stable codes, default-off guard.
2. **Static** — `ruff check`, `python3 -m compileall`, `git diff --check`.
3. **Integration (hermetic-local, real Worker)** — promote the phase5h harness: run a real Temporal Worker (`WorkflowEnvironment.start_time_skipping()` for CI hermeticity, and/or a `temporal server start-dev` namespace `sachima-p5-local`), drive `StepWorkflow` + `step_activity`, and assert reconciliation and snapshot consistency.
4. **No-leak SCAN 1 + SCAN 2** — sanitized JSON projection scan **and** serialized event-history-bytes scan against the real history; any forbidden material is `runtime_history_leak_detected`.
5. **Duplicate start** — mismatched observable payload returns `invalid_start_payload` with no second execution; identical payload returns `idempotent_replay`.
6. **Recovery / restart-replay** — Worker drop + fresh Worker resumes from history with no double-launch; reattach-by-id snapshot is consistent.
7. **Gateway-boundary static test** — an AST/import scan asserting that no Gateway module (and no inbound-message path) imports or references `p5_temporal_worker`, the Worker builder, the Temporal service lifecycle, or any subprocess/socket that would let it own runtime lifecycle. Kill criterion if violated.
8. **Determinism replay** — record a workflow history and replay it with Temporal's `Replayer`/`replay_workflow_history`; any non-determinism (workflow code doing I/O, time, or randomness outside activities) fails the gate.
9. **WP3b WATCH preserved** — a cancellation probe asserting active-run cancel is held `cancel_ambiguous` + `active_run_watch`, never `cancelled` without confirmed interruption.
10. **Local gates + Codex primary blocker review** — full supervisor suite, `tools/sync_roadmap_status.py --check`, forbidden-surface + secret + stale-status scans, and Codex repo-aware read-only blocker review `BLOCKERS: None`, before approval-ready.

## Rollout plan

```text
Stage 0  PR A (this packet)         docs-only design/readiness; no runtime.
Stage 1  local dev + CI (hermetic)  namespace sachima-p5-local; WorkflowEnvironment / temporal server start-dev;
                                     real Worker; controlled deterministic step body; ALL PR B gates must pass.
                                     >>> hermetic-local Temporal gates BLOCK PR B merge. <<<
Stage 2  staging namespace          namespace sachima-p5-staging; ops-owned Worker; 30-day retention; parallel
                                     ops/canary track; bounded controlled deterministic runs; observed for
                                     history-size, no-leak, recovery, duplicate-start, Worker health. NOT a PR B
                                     merge blocker; runs alongside/after merge as an ops promotion step.
Stage 3  production shadow/canary    namespace sachima-p5-prod; SEPARATE approval (production cluster + traffic);
                                     shadow first, then canary. Not enabled by this work.
Stage 4  limited enablement          SEPARATE approval; bounded real traffic; P6 real agent execution is its own gate.
```

Slice 1 delivers Stage 0 (PR A) and authorizes Stage 1 (hermetic-local, PR B merge gate) and Stage 2 (staging, parallel ops/canary). Stages 3–4 are out of scope and separately gated.

## Health, kill switch, and rollback

- **Worker health (ops):** task-queue poller presence and backlog via `temporal task-queue describe --task-queue sachima-p5-step-runtime`; workflow/activity poll-success and latency; sticky-cache hit rate; Worker build-id/identity; pending-activity and pending-workflow-task counts; open-vs-closed workflow counts per namespace.
- **Kill switch:** (1) default-off `P5TemporalStepExecutor` enable flag — turning it off makes the WP4 orchestrator fall back to `P5LocalOfflineRuntimeAdapter` and stops all Temporal calls from the caller; (2) ops stops/drains the Worker so nothing executes even if a workflow is started. Because the Gateway cannot start the Worker, it cannot defeat the kill switch.
- **Rollback (ops commands, staging only):** drain the Worker (`SIGTERM` to the `p5_temporal_worker.py` launcher → graceful poll stop); repoint the caller executor to the local/offline adapter; if needed, `temporal workflow list`/`terminate`/`cancel` scoped to `--namespace sachima-p5-staging`; redeploy the prior Worker build-id. Production is never touched (the prod namespace is defined but not enabled).
- **Stable failure classes (no-throw taxonomy, reused from the merged P5 contract):** `runtime_disabled`, `runtime_approval_mismatch`, `runtime_backend_unavailable`, `runtime_operation_timeout`, `runtime_query_unavailable`, `runtime_idempotency_conflict`, `runtime_claim_conflict`, `runtime_stale_state`, `runtime_lease_lost`, `runtime_toctou_conflict`, `runtime_retry_ambiguous`, `runtime_recover_ambiguous`, `runtime_cancel_not_confirmed`, `runtime_precondition_unmet`, `runtime_budget_exceeded`, `runtime_history_leak_detected`, `runtime_not_found`, `runtime_terminalized`. Every control-surface error collapses raw backend detail into one of these codes; no exception/traceback/PID/connection string crosses the boundary.

## Open decisions

Most decisions were settled by the granted defaults. Only these remain, and each is a clearly named, separate future gate — not a blocker for PR B:

1. **Production cluster + production traffic** (`sachima-p5-prod`): topology/HA, persistence store (Cassandra/PostgreSQL/Elasticsearch), mTLS/cert management, and traffic shaping. Deferred to `approve_sachima_p5_temporal_production_cluster_and_production_traffic_enablement`.
2. **P6 real agent execution in `step_activity`**: replacing the Slice 1 controlled deterministic body with real `acpx`/agent execution. Deferred to `approve_sachima_p6_controlled_ai_flow_real_agent_execution_in_step_activity`.
3. **Staging canary traffic shaping**: how much bounded controlled-deterministic load to run in `sachima-p5-staging`. This is an ops/SRE track decision, parallel to PR B, not a code-merge gate.

## PR A exact scope

PR A is **docs-only**. It changes exactly:

```text
docs/plans/2026-06-20-...-p5-temporal-production-runtime-enablement-slice-1-design-readiness.md       (new; this file)
docs/plans/2026-06-20-...-p5-temporal-production-runtime-enablement-slice-1-design-readiness-manifest.yaml (new)
docs/dev_log/2026-06-20-...-p5-temporal-production-runtime-enablement-slice-1-design-readiness.md      (new)
docs/roadmap/current-status.md                                                                         (narrow update)
```

PR A adds **no** runtime source files, starts **no** Temporal service or Worker, runs **no** workflow/activity, invokes **no** `acpx`/`npx`/AGENT, and writes **no** Gateway/Feishu/production config. After PR open/merge, the machine-owned status-sync block in `current-status.md` records PR #154 as merged; all other changes are human prose/status rows.

## PR B ready-to-implement criteria

PR B may begin when all of the following hold (they do, except where noted as the PR B author's responsibility):

- [x] Durable backend selected: **Temporal**.
- [x] External lifecycle token **granted** for hermetic-local + staging only.
- [x] Module names + prototype→module mapping fixed (above); no `p5_temporal` symbol collisions in the repo.
- [x] `temporalio>=1.27.0,<2` available via the `flowweaver-temporal` extra; host Temporal toolchain present.
- [x] WP4 `StepExecutor` Protocol seam merged and stable (`sachima_supervisor/ai_flow_executor.py`); P5 local/offline adapter (#149) + durable claim store (#150) merged as the in-process baseline.
- [x] No-leak SCAN 1 + SCAN 2, duplicate-start, recovery/restart-replay, Gateway-boundary static, and determinism-replay gates specified.
- [x] Hermetic-local Temporal gate designated as the PR B **merge** blocker; staging designated as a **parallel ops/canary** track.
- [x] WP3b active-run cancellation WATCH preserved in the contract.
- [ ] (PR B) Default-off `P5TemporalStepExecutor` enable flag + approval-token guard implemented, mirroring `P5LocalOfflineRuntimeAdapter`.
- [ ] (PR B) Ops-owned `p5_temporal_worker.py` launcher with graceful drain; Gateway-boundary static test green.
- [ ] (PR B) Full local gates + Codex primary blocker review `BLOCKERS: None`; `current-status.md` updated on merge.

## Explicit non-approvals

Stated once. This packet and the granted lifecycle token do **not** approve, now or by implication:

```text
production_cluster_enablement          # sachima-p5-prod cluster stand-up
production_traffic                      # real production traffic on any namespace
p6_real_agent_execution_in_activity     # real acpx/agent execution inside step_activity (Slice 1 body is deterministic)
gateway_owned_or_auto_started_lifecycle # Gateway/message-path owning/starting Temporal/Worker/service/socket/subprocess
write_capable_roles                     # all P5 roles remain read-only
live_gateway_feishu_or_im_behavior
real_external_delivery
production_config_write
service_restart_or_reload_of_gateway
platform_adapter_mutation
public_ingress
```

## Verification gates for this PR A (docs-only)

```text
git diff --check
YAML parse of the new manifest
docs/status stale-phrase scan (PR #150 recorded MERGED; no old open/candidate residue left)
forbidden implementation-surface scan on changed files (no runtime code added)
secret-shaped / no-leak scan
tools/sync_roadmap_status.py --check  (machine status block regenerated after PR open and current)
Codex primary blocker review
```

## Closure rule

PR A is complete only when this packet, its manifest, and the dev log are merged, and `docs/roadmap/current-status.md` records (a) PR #150 as **MERGED** (merge commit `21f8c1647ac9e6007183cc1f458af38bcc57fa7e`, mergedAt 2026-06-19T01:35:47Z) and (b) this Slice 1 design/readiness packet as **merged in PR #154** (merge commit `f465186cc96bc182eab00b1de039ed8258f06ac8`, mergedAt 2026-06-20T05:48:26Z), with the production-cluster, production-traffic, and P6 boundaries preserved. The post-merge current candidate is the separate docs-only **P5 Temporal PR B pre-development governance** branch; PR B implementation remains a separate, code-bearing PR under the granted lifecycle token.
