# P5 — Production durable runtime integration design & readiness packet

Date: 2026-06-18
Status: **Merged docs-only design / readiness packet** — merged in PR #147 (merge commit `6c11a40d4de3e66981c3ff27905c1785b1709e0a`, mergedAt 2026-06-18T03:36:51Z). This document is not implementation approval and starts no runtime. The next, narrower step is prepared in `docs/plans/2026-06-18-agent-run-supervisor-sachima-p5-local-offline-runtime-adapter-implementation-prep.md`.
Branch: `docs/p5-durable-runtime-readiness`
Base: `release/sachima` at `41e645189aa4de889c95b97a61a6d4fbb76783cd` (latest non-status-sync base; branch tip is the status-sync self-commit `68a058dd3`)

> **For Hermes:** This is a **docs-only design / readiness packet**. Do not implement runtime code, do not start or attach any Temporal/durable runtime, Worker, service, CLI, Docker container, socket, or subprocess, do not run any AGENT/`acpx`/`npx`, and do not touch Gateway/Feishu/production config. It does **not** approve implementation, runtime start, Worker start, controlled AI FLOW execution, live/default-on behavior, Gateway involvement, Feishu/IM delivery, production config writes, or real delivery. A later, separately named approval is required before any of those.

## Goal

Attach a **real durable runtime behind a caller-supplied control surface** so that long Sachima / FlowWeaver workflows survive **retries, process restarts, queries, updates, cancellations, and recovery** without leaking raw material and without the Gateway ever owning a runtime lifecycle.

Concretely, P5 defines *what must be designed and proven* before any production durable runtime (Temporal or equivalent) may be attached under the merged WP4 controlled AI FLOW orchestrator (PR #145):

- the caller-owned **control surface** and its operations;
- the durable **records** (runtime run / workflow / activity / session / step attempt, lease/epoch/state_version, idempotency key, query snapshot, cancellation/recovery records, artifact refs);
- the **cross-process transactional claim store** that must replace the current in-process CAS;
- the **no-throw** boundary and **stable failure taxonomy**;
- the **runtime-history no-leak** rules and the scans that prove them;
- the **probes** that must pass (duplicate start, retry, timeout, cancellation, recovery, restart/replay, query snapshot consistency);
- the acceptance checklist, scoring rubric, kill criteria, and implementation gates that gate the later implementation.

Strongest meaning: **design + readiness only**. It records the contract and the evidence bar; it does **not** add source code, attach a runtime, start a Worker, execute a workflow, or approve any live/Gateway/Feishu/production/real-delivery axis.

## Naming clarification (read this before drift)

This packet is for the **current roadmap `P5 — Production durable runtime integration`** row in `docs/roadmap/current-status.md`. It is **not** the older remaining-goals plan's `WP5 — write-capable roles`.

```text
roadmap P5  == production durable runtime integration   (this packet; topically the remaining-goals plan's WP6 durable-runtime content)
remaining-goals WP5 == write-capable roles + sandbox/rollback   (NOT this packet; write roles remain UNAPPROVED)
roadmap P6  == controlled AI FLOW execution   (BLOCKED until P5 durable runtime evidence passes)
```

P5 does **not** introduce, design-approve, or imply write-capable roles. All P5 roles remain **read-only** and bind only to the existing capability-gated read-only role keys.

## Status markers

```text
DESIGN_ONLY
READINESS_ONLY
IMPLEMENTATION_NOT_APPROVED
RUNTIME_START_NOT_APPROVED
WORKER_START_NOT_APPROVED
CROSS_PROCESS_CLAIM_STORE_DESIGN_ONLY
CONTROLLED_AI_FLOW_EXECUTION_NOT_APPROVED
WRITE_ROLES_NOT_APPROVED
NO_LIVE
NO_GATEWAY
NO_FEISHU
NO_PRODUCTION_CONFIG
NO_REAL_DELIVERY
```

Scoped markers (for grep / dashboard use):

```text
ARS_SACHIMA_P5_PRODUCTION_DURABLE_RUNTIME_DESIGN_READINESS_ONLY
ARS_SACHIMA_P5_RUNTIME_OWNERSHIP_CALLER_OWNED
ARS_SACHIMA_P5_GATEWAY_NEVER_OWNS_RUNTIME
ARS_SACHIMA_P5_RUNTIME_START_NOT_APPROVED
ARS_SACHIMA_P5_WORKER_START_NOT_APPROVED
ARS_SACHIMA_P5_CROSS_PROCESS_CLAIM_STORE_REQUIRED
ARS_SACHIMA_P5_RUNTIME_HISTORY_NO_LEAK
ARS_SACHIMA_P5_CONTROLLED_AI_FLOW_EXECUTION_BLOCKED_UNTIL_P5_EVIDENCE
ARS_SACHIMA_P5_WP3B_ACTIVE_RUN_CANCELLATION_WATCH_PRESERVED
```

Strongest allowed outcome of this PR:

```text
agent_run_supervisor_sachima_p5_production_durable_runtime_integration_design_readiness_ready_for_separate_local_caller_owned_runtime_adapter_implementation_request
```

That means a later, narrower **local caller-owned runtime adapter** implementation request *may be asked for* — still with no Gateway-owned lifecycle, no Worker auto-start, no controlled AI FLOW execution, and no live/Feishu/production/real delivery. It does **not** authorize durable-runtime implementation, runtime start, Worker start, controlled AI FLOW execution, or any external Temporal/Worker service lifecycle.

## Approval and boundary

User approved the exact design-scope token (docs only; no implementation; no runtime/Worker start; no controlled AI FLOW execution; no live/Gateway/Feishu/production config/real delivery):

```text
approve_agent_run_supervisor_sachima_p5_production_durable_runtime_integration_design_readiness_docs_only_no_implementation_no_runtime_start_no_worker_start_no_controlled_ai_flow_execution_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

The future **implementation** approval phrase is **not granted by this PR** (it would still be local, caller-owned, no Gateway-owned lifecycle, no Worker auto-start, no controlled AI FLOW execution, no live/Feishu/production/real delivery):

```text
approve_agent_run_supervisor_sachima_p5_production_durable_runtime_integration_local_caller_owned_runtime_adapter_implementation_no_gateway_owned_lifecycle_no_worker_auto_start_no_controlled_ai_flow_execution_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

Any **external Temporal service or Worker process lifecycle**, if ever proposed, needs its **own separate** token (not granted, and not implied by the implementation token above):

```text
approve_external_temporal_service_or_worker_lifecycle_for_sachima_p5_runtime
```

Interpretation used by Hermes:

- **Approved:** a docs-only P5 design / readiness gate that records durable-runtime ownership, the caller-supplied control surface, durable records, the cross-process transactional claim store requirement, the no-throw boundary and failure taxonomy, the runtime-history no-leak rules and scans, the required probes, and the acceptance/scoring/kill/implementation gates.
- **Not approved:** implementation, runtime/durable-backend attachment, Worker start, controlled AI FLOW execution, write roles, additional AGENT/`acpx`/`npx`, live/default-on behavior, Gateway involvement or mutation, Feishu/IM delivery, public ingress, production config writes, service restarts, platform adapter mutation, or real delivery.

This packet is and stays **caller-owned by a Sachima / FlowWeaver controller**. It deliberately does **not** name the Gateway as a caller, runtime owner, lifecycle owner, renderer, or delivery surface. Any durable runtime / Temporal abstraction below is a **design label** for a future *caller-supplied* component, never an approval to start or own one.

## Goal trace

```text
Goal: Sachima becomes Dog Brother's safe, durable, observable, recoverable IM AI workbench that can run long AI FLOW
      tasks and deliver sanitized results, surviving restarts, retries, duplicates, partial failures, and recovery.
Gap:  WP4 merged a caller-owned, local/offline, read-only, bounded controlled AI FLOW orchestrator (PR #142 design,
      PR #145 implementation). That orchestrator runs over an in-process, lock-guarded CAS store with an executor
      Protocol seam that has NO real runner. It does not yet survive process restarts, cannot reattach to an
      in-flight run after a crash, has no cross-process duplicate-start protection, and has no durable query/recovery
      surface. Attaching a real durable runtime (Temporal or equivalent) is the missing capability — and without an
      explicit ownership/control-surface/no-leak/recovery design, an implementation could leak raw material into a
      durable event history, let the Gateway or a Worker silently own a runtime lifecycle, or overclaim active-run
      cancellation.
Phase: Docs-only P5 production durable runtime integration design / readiness packet, positioned AFTER the merged WP4
       orchestrator and BEFORE any durable-runtime implementation, runtime/Worker start, or controlled AI FLOW
       execution (roadmap P6).
Task: Define durable-runtime ownership; the caller-supplied control surface (start/query/update/cancel/recover/
      close-terminalize) with stable sanitized result/error codes; durable records (runtime run/workflow/activity/
      session/step attempt, lease/epoch/state_version, idempotency key, query snapshot, cancellation/recovery
      records, artifact refs); the cross-process transactional claim store requirement; no-throw wrappers and a
      stable failure taxonomy; runtime-history no-leak rules plus JSON and serialized event/history-bytes scans;
      the required probes; and the acceptance checklist, scoring rubric, kill criteria, and implementation gates.
Test: Docs marker gate, manifest YAML parse, changed-file allowlist (docs/status only), no-secret/no-leak scan,
      forbidden implementation-surface scan, and Codex primary blocker review. No runtime tests are run by this PR.
Evidence: This packet, its manifest, this dev log, the narrow current-status update, and the merge evidence of the
      WP4 design (PR #142, `bb5e5d9bf707fde7934939cc473544511bd65ffd`) and WP4 implementation slice
      (PR #145, `c4ce77ce52020015f37710025d601a9ecf021a13`), plus the WP3b cancellation WATCH (PR #140,
      `3fe18ab9451d290a70036697da118351d604be27`). Code is referenced factually only (no edits).
Decision: May request a separate local, caller-owned runtime-adapter implementation only, still no Gateway-owned
      lifecycle, no Worker auto-start, no controlled AI FLOW execution, and no live/Feishu/production/real delivery.
      Controlled AI FLOW execution (P6) stays blocked until P5 durable-runtime evidence passes.
```

## Level selection

**Level 3 — High Risk design.**

Although this PR is docs-only, it governs **future production durable-runtime semantics**: durable state ownership, cross-process leases/claims, recovery after restart, durable event-history content, and the preconditions for any later durable-runtime attachment. Ambiguity here could later become a Gateway-owned or Worker-owned runtime lifecycle, raw-material leakage into a durable backend's persisted event history, duplicate execution on restart, or an overclaimed active-run cancellation. The packet is therefore held to strict manifest, explicit non-approvals, runtime-history no-leak rules, a stable failure taxonomy, a scoring rubric, kill criteria, and independent blocker review — the same discipline as a production-adjacent design packet.

## Existing stable base

| Evidence | Current state | Design impact |
|---|---|---|
| `GOAL.md` | Safety before live capability; **low intrusion** — the Gateway must not silently own Temporal/Worker/queue/daemon/Docker/socket/subprocess lifecycle; explicit per-axis approvals; claim-check discipline; delivery separation. | Durable-runtime ownership must stay caller-owned by Sachima/FlowWeaver; the runtime must be caller-supplied; no lifecycle is started or owned here, and the Gateway is excluded as a runtime owner. |
| WP4 design — PR #142 `bb5e5d9bf707fde7934939cc473544511bd65ffd` | Docs-only controlled AI FLOW orchestration design: caller-owned static graph, read-only roles, bounded steps, operator gates, claim-check artifacts, per-step idempotency/CAS, failure taxonomy, sanitized evidence. | P5 attaches a durable runtime *under* this contract without changing the workflow contract; the durable records below generalize the WP4 store. |
| WP4 implementation slice 1 — PR #145 `c4ce77ce52020015f37710025d601a9ecf021a13` | Local/offline, **injected-fakes-only** orchestrator: `ai_flow_spec.py` / `ai_flow_artifacts.py` / `ai_flow_gates.py` / `ai_flow_store.py` (lock-guarded **in-process** CAS) / `ai_flow_executor.py` (Protocol seam, **no real runner**) / `ai_flow_evidence.py` / `activity_ai_flow_orchestration.py`. 627 supervisor tests + self-test, CI, Codex blocker review PASS. | The in-process CAS store is single-process only; P5 requires a **cross-process transactional claim store**. The executor Protocol seam is the attach point for a future caller-supplied runtime — but P5 only designs it. |
| WP3b — PR #140 `3fe18ab9451d290a70036697da118351d604be27` | Bounded cancellation bridge; deterministic self-test / fail-closed verified, but real host/ACP `--cancel-during-turn` did **not** reliably prove active-run cancellation → **WATCH**. | P5 must preserve the active-run cancellation WATCH; between-step cancel can be deterministic, active-run cancel stays best-effort/WATCH and must not be overclaimed in durable records or evidence. |
| `sachima_supervisor/ai_flow_store.py` (factual reference) | Lock-guarded in-process CAS over a sanitized version field; single mutex; single process. | Generalized below into a design-level **cross-process transactional claim store** requirement; the in-process store is insufficient evidence for durable claims. |
| Prior durable-runtime ownership design — PR #102 `e49709d6e960b8e11f8e220fa087488132f64f93` | Established Sachima/FlowWeaver owns durable product/transaction/Activity state, leases, idempotency; runtime is caller-supplied; Gateway excluded. | P5 inherits that ownership model and extends it to a real durable runtime with recovery and a cross-process claim store. |

## Core ownership decision

```text
Sachima / FlowWeaver (the caller) OWNS:
  - the durable runtime CHOICE and lifecycle (start/stop/connect of any Temporal-or-equivalent backend)
  - the caller-supplied CONTROL SURFACE that the supervisor/orchestrator calls
  - durable product/transaction/workflow/activity/session/step state, leases, epochs, state_version
  - idempotency, the cross-process transactional claim store, retry/update/cancel/recover/close policy
  - role mapping (intent -> allowlisted READ-ONLY role key) and the business verdict

agent-run-supervisor / the WP4 orchestrator REMAINS a local library:
  - calls the caller-supplied control surface through the existing executor Protocol seam
  - owns local run/session internals and redacted evidence ONLY once invoked by an approved caller
  - never owns the durable runtime lifecycle, the claim store, leases, idempotency, or the business verdict

The Gateway is NEVER:
  - a caller, a runtime owner, a lifecycle owner, a Worker host, a renderer, or a delivery surface in P5
  - allowed to own or AUTO-START a Temporal service, a Worker, a system service, a socket, or a subprocess

A Temporal / durable runtime is at most a FUTURE caller-supplied abstraction:
  - this design MUST NOT start or own a runtime, Worker, service, CLI, Docker container, socket, or subprocess.
```

Rationale:

1. The orchestrator already owns step mechanics and redacted evidence; Sachima already owns product intent and verdict. Durable-runtime ownership and the control surface belong to Sachima/FlowWeaver — never the supervisor library, and never the Gateway.
2. Keeping the runtime **caller-supplied** preserves the `GOAL.md` low-intrusion principle: no message-handling or Gateway path silently acquires a Temporal/Worker/daemon/Docker/socket/subprocess lifecycle.
3. A control surface (rather than direct backend coupling) lets a future implementation slot in a durable backend behind a stable, sanitized, no-throw boundary without this packet approving any specific service start-up.

## Caller-supplied control surface

The caller supplies a control surface that the orchestrator invokes through the existing executor Protocol seam. All operations are **design labels**; none is implemented or invoked here. Every operation is **no-throw** (see No-throw boundary) and returns a stable, sanitized result with a stable `status_code` and optional stable `error_code`.

| Operation | Purpose | Primary stable result codes | Notes |
|---|---|---|---|
| `start` | Begin (or idempotently re-attach to) a durable run for a validated workflow spec | `started`, `idempotent_replay`, `start_conflict` | Atomic cross-process claim required; identical replay returns the existing run handle; conflicting concurrent start fails closed pre-launch |
| `query` | Return a sanitized, read-only **query snapshot** of a run/step | `query_ok`, `not_found`, `query_unavailable` | Never re-invokes the runtime/executor; never rehydrates raw prompt/context; snapshot is internally consistent (no torn read) |
| `update` | Apply a caller-authorized signal/update to a durable run | `update_applied`, `update_rejected`, `stale`, `not_found` | Requires same role/lease/epoch binding; role/lease/state drift fails closed **before** mutation |
| `cancel` | Request cancellation of a run/step | `cancel_requested`, `cancelled`, `cancel_failed`, `cancel_ambiguous` | Between-step cancel deterministic; **active-run cancel best-effort/WATCH** (see WP3b); ambiguous → fail-closed, no artifact propagation, no relaunch |
| `recover` | Reattach to an existing durable run after a process restart/crash and reconcile state | `recovered`, `recover_ambiguous`, `not_found` | Reconciles durable state under lease/epoch; divergence → fail-closed `recover_ambiguous`, operator gate; never duplicate-launches to resolve ambiguity |
| `close` / `terminalize` | Finalize a terminal state and release the lease | `closed`, `already_terminal` | Releases lease only after the terminal durable write; does not send final IM output (delivery out of scope) |

Cross-cutting control-surface rules:

- every operation validates the **exact P5 approval gate** (for any future real attach), the operation allowlist, the read-only role allowlist, and a material screen before touching durable state;
- every state-changing operation is bound by the **same `lease_epoch` + `state_version`** between validation and durable apply (TOCTOU-safe);
- every operation is **idempotent** by `(idempotency_key, request_fingerprint)`; a compatible repeat replays the stored terminal projection, an incompatible repeat fails closed;
- no operation returns raw material; results carry only stable codes, refs, digests, and counts.

## Durable records

All names are **design labels**, not implementation approval. They generalize the merged WP4 in-process store into durable records a future caller-supplied runtime could realize.

### RuntimeRunRecord (durable run handle)

```text
- run_id                 caller-owned local id (never a platform id, never a backend secret)
- runtime_kind           design label for the caller-supplied backend (e.g. temporal-like); never a connection string
- workflow_type_ref      claim-check ref to the validated WP4 workflow spec (with workflow_spec_digest)
- run_ref                opaque, sanitized handle to the durable run (NOT a backend token/URL/secret)
- status                 stable status code
- state_version          monotonically increasing version for optimistic concurrency
- lease                  { lease_id, lease_epoch, lease_holder_ref (sanitized), lease_deadline_marker }
- idempotency_key        stable key for exactly-once start/transition
- attempt_count          non-negative integer
- artifact_ref_count     non-negative integer
- evidence_ref / digest  sanitized evidence ref + sha256 digest, or null
- caller_verdict         caller-owned verdict code or null (library never sets it)
- error_code             stable sanitized error code or null
- retryable              boolean
- created_at_marker      sanitized logical marker (no wall-clock leakage beyond a sanitized marker)
```

### WorkflowRecord / ActivityRecord / SessionRecord / StepAttemptRecord

```text
WorkflowRecord   maps the WP4 static graph onto the durable run: run_id, workflow_spec_digest, step ids/edges (refs),
                 bounds, status; NO raw spec body in durable history (claim-check ref + digest only).
ActivityRecord   per durable activity: activity_id, role_key (allowlisted), mode/phase, status, lease/epoch,
                 idempotency binding, evidence_ref/digest, error_code; sanitized as in PR #102.
SessionRecord    (design label only; persistent-session execution remains separately gated) session_id, activity_ref,
                 role_key, role_file_digest, session_binding, lifecycle_state, lease, state_version, turn_count.
StepAttemptRecord (append-only, per step):
  - step_id, attempt_index (monotonic, starts at 1)
  - idempotency_key, request_fingerprint
  - role_binding_digest, input_artifact_digests
  - outcome_status (stable code), error_code (stable or null)
  - evidence_ref (sanitized or null), lease_epoch_at_launch
Rules:
  - a repeat (idempotency_key, fingerprint) replays the stored terminal attempt; it does NOT launch a new run/step;
  - a repeat key with a DIFFERENT fingerprint fails closed (idempotency conflict);
  - attempts never store raw material; only stable codes, refs, counts, digests.
```

### Lease / epoch / state_version

```text
- A lease is a caller-owned, time-bounded ownership token over a durable transition, valid ACROSS PROCESSES.
- Only the holder matching lease_id AND lease_epoch may apply a transition; a stale (lower) epoch fails closed.
- Every durable transition checks state_version (optimistic concurrency) AND lease_epoch; stale writers fail closed.
- Lease acquire/renew/steal/release are design labels; no real lock/lease service is started or owned here.
- Across a process restart, recovery (below) re-establishes lease/epoch before any further transition.
```

### IdempotencyKey

```text
- The unit of exactly-once is (idempotency_key, request_fingerprint) bound to (run_id, workflow_spec_digest,
  role_binding_digest, input_artifact_digests, approval_ref, attempt_index).
- Cross-process duplicate starts MUST converge to exactly one durable run via the cross-process claim store.
```

### QuerySnapshotRecord

```text
- A query snapshot is a deterministic, sanitized, read-only view derived from durable records at a snapshot_version.
- snapshot_id, snapshot_version (monotonic), run_status, per-step statuses, counts, artifact refs/digests,
  cancellation/recovery markers, active-run cancellation WATCH marker, stable codes.
- Query NEVER re-invokes the runtime/executor and NEVER rehydrates raw prompt/context/output.
- Snapshots are internally consistent: a query during a transition returns a coherent pre- or post-transition view,
  never a torn read.
```

### CancellationRecord

```text
- cancel_id, target (run_id/step_id), operator_gate_ref, lease binding, idempotency, reason_code (stable)
- status: cancel_requested | cancelled | cancel_failed | cancel_ambiguous
- active_run_watch marker: set when active-run interruption could not be safely confirmed (WP3b WATCH)
- cancelled is recorded ONLY when cancellation is deterministically/cleanly confirmed; unconfirmed active-run
  interruption is held cancel_ambiguous, never silently promoted to cancelled.
```

### RecoveryRecord

```text
- recovery_id, run_ref, recovered_state_version, epoch_at_recovery
- reconciliation_outcome: recovered | recover_ambiguous
- divergence_code (stable) when durable state and reconstructed state disagree
- operator_gate_ref when recovery requires human adjudication
- recovery NEVER duplicate-launches a run/step to resolve ambiguity; recover_ambiguous fails closed.
```

### ArtifactRef (claim-check)

```text
- artifact_id, producer_step_id, content_digest (sha256:<hex>), artifact_kind, byte_count, created_at_marker
- durable state stores refs/digests only; raw artifact bodies stay OUT of durable state, durable history, and
  operator projections (claim-check discipline, identical to WP4).
```

## Cross-process transactional claim store (required)

The merged WP4 claim store (`ai_flow_store.py`) is a **single-process, in-process, lock-guarded CAS**. It is correct for one process but is **insufficient** for a durable runtime that:

- survives and reattaches across **process restarts**;
- may admit **multiple Workers / processes** racing on the same run;
- must resolve **duplicate start**, **retry**, and **recovery** races **across processes**, not just across threads.

Therefore any later P5 production implementation **MUST** use a **cross-process transactional claim store** with:

```text
- atomic claim / check-and-set across processes (not a thread mutex);
- durability across process restart (the claim survives a crash);
- isolation sufficient to serialize conflicting claims (no two processes both believe they hold the claim);
- a stable claim record bound to (run_id, idempotency_key, request_fingerprint, lease_epoch);
- fail-closed on conflict: concurrent identical starts launch exactly once; conflicting starts fail closed pre-launch;
- recovery-safe reads: a restarted process reads the durable claim before deciding to start/replay/recover.
```

Design rule: **the in-process CAS may not be presented as evidence of durable, cross-process claim correctness.** A P5 implementation candidate that reuses only the in-process mutex store for durable claims is a **kill-criterion failure** (see Kill criteria). The cross-process store stays **caller-owned and local** until a separate live gate; it is not a Gateway-owned or Worker-owned service.

## No-throw boundary

Every control-surface operation is a **no-throw wrapper**: it catches all backend/runtime exceptions at the boundary and returns a structured, sanitized result; it never raises across the boundary, and it never leaks a traceback, exception string, PID, or backend detail.

```text
result := {
  status_code,            # stable code (e.g. started, query_ok, recovered, cancel_ambiguous)
  error_code,             # stable code or null (see Failure taxonomy)
  run_ref,                # opaque sanitized handle or null
  snapshot_ref,           # sanitized query-snapshot ref or null
  retryable,              # boolean
}
```

Rules:

- a backend exception collapses to a stable `error_code` (e.g. `runtime_backend_unavailable`), raw detail suppressed;
- a timeout collapses to a stable code with `retryable` set per the failure taxonomy, never a partial/torn result;
- unknown/ambiguous states map to fail-closed terminal codes, never an optimistic success;
- logs follow the same allow/forbid lists as durable state (stable codes only; raw exception suppressed).

## Stable failure taxonomy

| Error code | Meaning | Retryable |
|---|---|---:|
| `runtime_disabled` | Durable-runtime control surface gate not enabled. | No |
| `runtime_approval_mismatch` | Exact P5 approval marker missing or wrong. | No |
| `runtime_unsupported_op` | Operation not in the allowlist for the current phase. | No |
| `runtime_unknown_role` | Role key not in the caller-owned read-only allowlist. | No |
| `runtime_unsafe_material` | Input contains platform/private/secret/raw/card/media material. | No |
| `runtime_idempotency_conflict` | Same idempotency key maps to an incompatible request fingerprint. | No |
| `runtime_stale_state` | Stale `state_version` or `lease_epoch` on a durable transition. | No |
| `runtime_lease_lost` | Caller no longer holds a current lease over the run. | No |
| `runtime_toctou_conflict` | Run/workspace drift between validation and durable apply. | No |
| `runtime_claim_conflict` | Cross-process claim already held by a conflicting starter. | No |
| `runtime_retry_ambiguous` | Prior attempt/transition state cannot be safely retried. | No |
| `runtime_recover_ambiguous` | Durable and reconstructed state diverge on recovery; operator gate required. | No |
| `runtime_cancel_not_confirmed` | Active-run cancellation could not be safely confirmed (WP3b WATCH). | No |
| `runtime_precondition_unmet` | A durable-runtime precondition is absent or ambiguous. | No |
| `runtime_budget_exceeded` | A caller-owned budget bound would be exceeded. | No |
| `runtime_backend_unavailable` | Caller-supplied runtime/backend unreachable; raw detail suppressed. | Bounded |
| `runtime_operation_timeout` | A bounded control-surface operation timed out. | Bounded |
| `runtime_query_unavailable` | Query snapshot could not be produced safely. | Bounded |
| `runtime_history_leak_detected` | A no-leak scan found forbidden material in JSON or serialized history bytes. | No |
| `runtime_not_found` | No durable record for the given id. | No |
| `runtime_terminalized` | Operation attempted on an already-terminal run. | No |

## Runtime-history no-leak rules

Durable records, query snapshots, attempts, evidence refs, operator projections, **and the caller-supplied runtime's own serialized event history / workflow state** may store **only**:

```text
stable status / error codes
mode / phase
caller-owned run / workflow / activity / session / step / artifact refs
role key (never raw role JSON)
claim-check refs and sha256 digests (never raw prompt/context)
artifact / evidence refs and sha256 digests
counts, retry counters, attempt indices, snapshot_version, state_version
lease_id / lease_epoch (sanitized, opaque, non-secret)
caller verdict code (caller-owned; library never sets it)
recovery / cancellation markers, including the active-run cancellation WATCH marker
```

They must **never** store or log:

```text
raw prompt / context / model output
raw tool output / raw acpx/ACP stdout
raw exception text or tracebacks
process ids (PIDs), thread ids, host names
platform private ids (oc_ / ou_ / om_ and similar), card JSON, message ids
media bytes or media/private absolute paths
tokens / credentials / cookies / secrets / raw signatures / connection strings / signed URLs
delivery payloads / IM message bodies
```

Critical P5 addition — **two no-leak scan surfaces are required**, because a durable backend persists workflow inputs/outputs in its **own event history**, which the sanitized JSON projection scan alone will not catch:

```text
SCAN 1 (JSON projection scan): the sanitized durable records, query snapshots, and evidence packet JSON
        contain only the allowed fields above.
SCAN 2 (serialized event/history-bytes scan): the caller-supplied runtime's serialized event history /
        workflow-state bytes (the durable payloads the backend persists and replays) contain no forbidden
        material. A leak in SCAN 2 is `runtime_history_leak_detected` and is a kill-criterion failure.
```

A future implementation must therefore pass payloads to the runtime by **claim-check ref/digest**, never by raw body, so that what the durable backend persists and replays is already sanitized.

## Required probes (design-level evidence bar; not run by this PR)

A later P5 implementation must produce passing evidence for **all** of the following. None is run here.

| Probe | What it proves | Required posture |
|---|---|---|
| **Duplicate start** | Two identical concurrent/sequential starts across processes converge to exactly one durable run | second start → `idempotent_replay`; cross-process claim store, not in-process mutex |
| **Retry** | Bounded retry only for retryable backend-unavailable/timeout classes; replays stored attempt | no duplicate run/step launch; unknown failures non-retryable |
| **Timeout** | A bounded operation timeout collapses to a stable code, fail-closed | no partial/torn result; no raw detail leak |
| **Cancellation** | Between-step cancel deterministic; active-run cancel honest | active-run unconfirmed → `cancel_ambiguous` + WATCH marker, no artifact propagation, no relaunch |
| **Recovery** | Kill + `recover` reattaches and reconciles durable state | no duplicate side effects; divergence → `recover_ambiguous` fail-closed |
| **Restart / replay** | Process restart then replay reaches a deterministic terminal state | no double execution; durable claim consulted before start/replay |
| **Query snapshot consistency** | `query` during/after transitions returns a monotonic, internally consistent snapshot | no torn read; `snapshot_version` monotonic; never re-invokes the runtime |

Every probe's evidence must additionally pass **SCAN 1 + SCAN 2** (JSON projection scan and serialized event/history-bytes scan) and must surface the WP3b active-run cancellation **WATCH** marker where relevant.

## Relationship to WP4 (merged) and P6 (blocked)

```text
WP4 (merged):  local/offline, injected-fakes-only controlled AI FLOW orchestrator
               - PR #142 design (bb5e5d9bf707fde7934939cc473544511bd65ffd)
               - PR #145 implementation slice 1 (c4ce77ce52020015f37710025d601a9ecf021a13)
               - in-process CAS store; executor Protocol seam with NO real runner.

P5 (this gate, then a later implementation): production durable runtime integration
               - design/readiness NOW (this packet);
               - later: attach a caller-supplied durable runtime behind the control surface,
                 add the cross-process transactional claim store, and PRODUCE DURABLE RUNTIME EVIDENCE
                 (the probes above), still local, caller-owned, no Gateway-owned lifecycle, no Worker auto-start,
                 no controlled AI FLOW execution, no live/Feishu/production/real delivery.

P6 (controlled AI FLOW execution): BLOCKED until P5 durable runtime evidence passes.
               - P6 (real workflow execution through the orchestrator) may not be requested until the P5 probes
                 pass and the P5 implementation evidence is accepted. P5 produces durable runtime evidence;
                 it does NOT itself execute a controlled AI FLOW.
```

P5 attaching a durable runtime does **not** approve P6 controlled AI FLOW execution; the two are separate gates, and P6 stays blocked behind passing P5 evidence.

## WP3b active-run cancellation WATCH (preserved, not overclaimed)

WP3b (PR #140) merged a bounded cancellation bridge with verified deterministic self-test and fail-closed semantics, but **real host/ACP `--cancel-during-turn` did not reliably prove active-run cancellation**. P5 preserves that WATCH:

- **between-step cancellation** in the durable runtime may be deterministic (stop scheduling, close the run, run read-only bookkeeping);
- **active-run cancellation** of an in-flight real step remains **best-effort / WATCH** until separate evidence proves the host/ACP semantics;
- when active-run interruption cannot be safely confirmed, the durable `CancellationRecord` is held `cancel_ambiguous` with the `active_run_watch` marker, **never** promoted to `cancelled`, and no artifact is propagated and no step is relaunched;
- P5 design, records, probes, and evidence **must not overclaim** reliable active-run cancellation, and the WATCH marker must appear wherever active-run cancellation is involved.

## Acceptance checklist

### For this docs-only design / readiness PR

- [ ] Status markers present and unambiguous (`DESIGN_ONLY`, `READINESS_ONLY`, `IMPLEMENTATION_NOT_APPROVED`, `RUNTIME_START_NOT_APPROVED`, `WORKER_START_NOT_APPROVED`, `CONTROLLED_AI_FLOW_EXECUTION_NOT_APPROVED`, `WRITE_ROLES_NOT_APPROVED`, `NO_LIVE`, `NO_GATEWAY`, `NO_FEISHU`, `NO_PRODUCTION_CONFIG`, `NO_REAL_DELIVERY`).
- [ ] Naming clarification present: roadmap P5 (durable runtime) ≠ remaining-goals WP5 (write roles); write roles unapproved; P6 blocked until P5 evidence.
- [ ] Exact approved design-scope token quoted verbatim; future implementation token and external Temporal/Worker lifecycle token quoted and marked **not granted**.
- [ ] Goal trace links final goal → gap → phase → task → test → evidence → decision.
- [ ] Core ownership decision present: Sachima/FlowWeaver owns runtime/control surface/state; supervisor library calls the control surface only; **Gateway never owns or auto-starts** a Temporal/Worker/service/socket/subprocess lifecycle; runtime is caller-supplied.
- [ ] Control surface defines `start` / `query` / `update` / `cancel` / `recover` / `close`(terminalize) with stable sanitized result/error codes.
- [ ] Durable records defined: runtime run / workflow / activity / session / step attempt, lease/epoch/state_version, idempotency key, query snapshot, cancellation record, recovery record, artifact refs.
- [ ] Cross-process transactional claim store required; the in-process CAS is explicitly called insufficient for durable claims.
- [ ] No-throw boundary and a stable failure taxonomy present.
- [ ] Runtime-history no-leak rules list allowed/forbidden data and require **both** the JSON projection scan and the **serialized event/history-bytes scan**.
- [ ] Required probes enumerated: duplicate start, retry, timeout, cancellation, recovery, restart/replay, query snapshot consistency.
- [ ] WP3b active-run cancellation WATCH preserved and not overclaimed.
- [ ] Scoring rubric, kill criteria, and implementation gates present.
- [ ] Explicit non-approvals include implementation, runtime start, Worker start, controlled AI FLOW execution, write roles, Gateway-owned/auto-started lifecycle, external Temporal/Worker lifecycle, live, Feishu, production config, and real delivery.
- [ ] Manifest is YAML-parseable with the required keys, false booleans for implementation/runtime start/controlled AI FLOW/Gateway/Feishu/live/production config/real delivery, `codex_primary_review` records PASS / BLOCKERS None, and PR #147 number/URL/head SHA/merge commit/mergedAt are recorded from live GitHub truth.
- [ ] Changed-file allowlist is docs/status only (3 new docs + this roadmap update).
- [ ] Secret-shaped / no-leak scan and forbidden implementation-surface scan pass.
- [ ] Codex primary blocker review returns `BLOCKERS: None`.

### For the later P5 implementation gate (informational; not approved here)

- [ ] Local, caller-owned runtime adapter only; no Gateway-owned lifecycle; no Worker auto-start.
- [ ] Cross-process transactional claim store backs all durable claims.
- [ ] All control-surface operations are no-throw and return stable sanitized codes.
- [ ] Both no-leak scans (JSON + serialized event/history bytes) pass.
- [ ] All seven probes pass with deterministic, sanitized evidence.
- [ ] WP3b active-run cancellation WATCH preserved in records, probes, and evidence.
- [ ] No controlled AI FLOW execution (P6), no write roles, no live/Gateway/Feishu/production config/real delivery.
- [ ] Codex primary blocker review returns `BLOCKERS: None`.

## Scoring rubric (for a later P5 implementation candidate)

Each dimension scores **0 = absent/unsafe**, **1 = partial**, **2 = complete & proven**. A candidate **passes only with ≥ 18/20 AND no dimension at 0 AND no kill-criterion triggered**.

| # | Dimension | 2 = complete & proven |
|---|---|---|
| 1 | Runtime ownership boundary | Sachima/FlowWeaver owns runtime/control surface/state; Gateway proven not an owner/auto-starter; runtime caller-supplied |
| 2 | Control-surface completeness | `start`/`query`/`update`/`cancel`/`recover`/`close` all present with stable sanitized result/error codes |
| 3 | Cross-process claim correctness | Durable, atomic, isolated cross-process claim store; duplicate-start converges to one run across processes |
| 4 | Idempotency & replay | `(idempotency_key, fingerprint)` exactly-once; compatible replay returns stored projection; incompatible fails closed |
| 5 | Recovery / restart | Kill + `recover` reconciles with no duplicate side effects; divergence → `recover_ambiguous` fail-closed |
| 6 | Query snapshot consistency | Monotonic `snapshot_version`; no torn reads; query never re-invokes the runtime |
| 7 | Cancellation honesty (WP3b) | Between-step deterministic; active-run unconfirmed → `cancel_ambiguous` + WATCH; never overclaimed |
| 8 | No-throw & failure taxonomy | No exception crosses the boundary; every failure maps to a stable code; unknown → fail-closed |
| 9 | Runtime-history no-leak | **Both** scans pass: JSON projection scan **and** serialized event/history-bytes scan |
| 10 | Evidence determinism | Probes produce deterministic, sanitized, reproducible evidence outside the repo |

## Kill criteria (automatic fail regardless of score)

A P5 implementation candidate is **rejected outright** if any of the following is true:

```text
K1  The Gateway (or a Worker, or any message-handling path) OWNS or AUTO-STARTS a Temporal service, Worker,
    system service, socket, or subprocess runtime lifecycle.
K2  The durable claim relies on the in-process mutex CAS instead of a cross-process transactional claim store.
K3  Raw material (prompt/context/model/tool output, exception text, PID, private path, platform id, token,
    delivery payload, card JSON) appears in durable records, query snapshots, evidence, OR the serialized
    event/history bytes (SCAN 2 fails) -> runtime_history_leak_detected.
K4  Active-run cancellation is recorded as clean `cancelled` without confirmed interruption (WP3b WATCH overclaimed).
K5  A process restart / replay / duplicate start causes a SECOND real execution (double-launch).
K6  A control-surface operation raises across the boundary or leaks a backend exception/traceback.
K7  Controlled AI FLOW real execution (P6), write-capable roles, additional AGENT/acpx/npx, live/default-on,
    Gateway involvement/mutation, Feishu/IM delivery, public ingress, production config writes, or real delivery
    is introduced under cover of P5.
K8  An external Temporal/Worker service lifecycle is started without its own separate approval token.
```

## Implementation gates (ordered; for the later, separately approved implementation)

```text
G0  Separate exact implementation approval token present (the local caller-owned runtime-adapter token above);
    external Temporal/Worker service lifecycle, if ever proposed, requires its own separate token.
G1  Local, caller-owned runtime adapter behind the existing executor Protocol seam; default-off; Gateway excluded.
G2  Cross-process transactional claim store implemented and proven (atomic/durable/isolated); in-process CAS retired
    for durable claims.
G3  Control surface (start/query/update/cancel/recover/close) implemented as no-throw wrappers with the stable
    failure taxonomy.
G4  Durable records + lease/epoch/state_version + idempotency + claim-check artifact refs persisted sanitized.
G5  Runtime-history no-leak enforced by construction (claim-check inputs) and verified by SCAN 1 + SCAN 2.
G6  All seven probes pass (duplicate start, retry, timeout, cancellation, recovery, restart/replay, query snapshot
    consistency) with deterministic sanitized evidence outside the repo.
G7  WP3b active-run cancellation WATCH preserved in records, probes, and evidence.
G8  Local verification (focused + full supervisor suite, ruff/compileall, git diff --check, secret-shaped scan,
    forbidden-surface scan) + Codex primary blocker review `BLOCKERS: None`; roadmap dashboard updated.
```

P6 (controlled AI FLOW execution) remains blocked until G0–G8 evidence is accepted.

## Explicit non-approvals

This design / readiness packet does **not** approve:

```text
implementation_of_any_kind
production_durable_runtime_code_implementation
runtime_start_or_attach
worker_start_or_auto_start
cross_process_claim_store_implementation
controlled_ai_flow_execution
real_workflow_execution
write_capable_claude_or_codex_roles
additional_real_agent_execution
additional_acpx_invocation
npx_fallback_or_network_fetch
real_local_exec
persistent_session_execution
additional_or_unbounded_cancellation_execution
satine_or_hermes_profile_acp_execution
gateway_owned_temporal_lifecycle
gateway_owned_or_auto_started_worker_or_service_or_socket_or_subprocess
external_temporal_service_or_worker_startup
gateway_involvement_or_mutation
gateway_restart_or_reload
platform_adapter_mutation
real_external_sachima_ingress
public_webhook_exposure
feishu_or_im_delivery
real_external_delivery
production_delivery_control
production_config_write
service_restart_or_reload
live_or_default_on_behavior
automatic_replies
worker_auto_routing
agent_to_agent_auto_routing
@all_fanout
trusted_markdown_html_rendering
```

## Verification gates (docs-only PR)

This PR is docs/status only. The gates are documentation and governance gates; no runtime tests are run by this PR.

- [ ] Status markers present and unambiguous.
- [ ] Naming clarification (P5 durable runtime ≠ remaining-goals WP5 write roles) present.
- [ ] Approved design-scope token quoted verbatim; future implementation token + external Temporal/Worker lifecycle token quoted and marked not granted.
- [ ] Goal trace complete; ownership decision excludes the Gateway as runtime owner/auto-starter.
- [ ] Control surface, durable records, cross-process claim store, no-throw boundary, failure taxonomy, no-leak rules (incl. serialized history scan), probes, WP3b WATCH, acceptance checklist, scoring rubric, kill criteria, and implementation gates all present.
- [ ] Manifest is YAML-parseable; false booleans for implementation/runtime start/controlled AI FLOW/Gateway/Feishu/live/production config/real delivery; `codex_primary_review` records PASS / BLOCKERS None; PR #147 number/URL/head SHA/merge commit/mergedAt are recorded from live GitHub truth.
- [ ] Changed-file allowlist is docs/status only.
- [ ] Secret-shaped / no-leak scan and forbidden implementation-surface scan pass.
- [ ] Codex primary blocker review returns `BLOCKERS: None`.

Hermes runs these gates and the Codex primary review; the author (Documentation Engineer) does not commit, push, merge, run tests, attach a runtime, start a Worker, or touch runtime/Gateway/Feishu/production config.

## Future next approval

The next, **narrower** approval should be a separate local, caller-owned runtime-adapter implementation — still **no Gateway-owned lifecycle**, **no Worker auto-start**, **no controlled AI FLOW execution**, and **no live/Feishu/production/real delivery**:

```text
approve_agent_run_supervisor_sachima_p5_production_durable_runtime_integration_local_caller_owned_runtime_adapter_implementation_no_gateway_owned_lifecycle_no_worker_auto_start_no_controlled_ai_flow_execution_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

Any external Temporal service or Worker process lifecycle, if ever proposed, requires its own separate token:

```text
approve_external_temporal_service_or_worker_lifecycle_for_sachima_p5_runtime
```

This is the recommended mainline next step after this packet merges. **Do not recommend agentic-ui as the default next step**; the agentic-ui Sachima Envelope v1 conformance work remains an open side tail. A later, separately named approval — after the P5 durable-runtime evidence (probes) passes — would be required before any controlled AI FLOW execution (P6), write roles, live/default-on behavior, Gateway involvement, Feishu/IM delivery, production config writes, or real delivery.

## Closure rule

This design / readiness packet only makes a P5 **local caller-owned runtime-adapter implementation eligible to request** after review and merge. It does not authorize any source implementation, runtime start, Worker start, durable-backend attachment, controlled AI FLOW execution, external Temporal/Worker lifecycle, or any live/Gateway/Feishu/production/real-delivery axis.
