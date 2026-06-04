# agent-run-supervisor × Sachima Supervised Local Activity — Durable Runtime Ownership & Controlled Local Execution Design Packet

> **For Hermes:** This is a **docs-only design packet**. Do not implement runtime code, do not run any local execution, and do not start any service, Worker, CLI, Docker container, socket, or Gateway from this document. It does **not** approve implementation, real local `exec`, persistent sessions, cancellation execution, live/default-on behavior, Gateway involvement, real external ingress, real IM/Feishu delivery, production config writes, real AGENT execution, real AGENT auto-routing, or controlled AI FLOW execution. A later, separately named approval is required before any of those.

**Goal:** Define durable runtime ownership and controlled local execution semantics around the already-merged supervised local Activity wrapper (`sachima_supervisor.activity`) and its dry-run evidence, after PR #99 (wrapper), PR #100 (dry-run evidence), and PR #101 (status closure). This packet decides *who owns durable product/transaction state and what must be true before any future real local execution may even be requested* — it does not authorize that execution.

**Architecture:** Sachima/FlowWeaver owns the durable product/transaction runtime and the business decision to request a future local execution. `agent-run-supervisor` remains an independent local supervision library that owns local run/session internals and redacted evidence once invoked by an approved caller. The Gateway is not a caller, lifecycle owner, renderer, or delivery surface in this phase. A Temporal/durable runtime is at most a future *caller-supplied* abstraction; this design must not start or own any runtime, Worker, service, CLI, Docker, socket, or Gateway lifecycle.

---

## Status Markers

```text
DESIGN_ONLY
IMPLEMENTATION_NOT_APPROVED
LOCAL_EXECUTION_NOT_APPROVED
REAL_AGENT_EXECUTION_NOT_APPROVED
CONTROLLED_AI_FLOW_EXECUTION_NOT_APPROVED
NO_LIVE
NO_GATEWAY
NO_REAL_DELIVERY
```

Scoped markers (for grep / dashboard use):

```text
ARS_SACHIMA_DURABLE_RUNTIME_CONTROLLED_LOCAL_EXEC_DESIGN_ONLY
ARS_SACHIMA_DURABLE_RUNTIME_OWNERSHIP_DESIGN_ONLY
ARS_SACHIMA_CONTROLLED_LOCAL_EXECUTION_NOT_APPROVED
ARS_SACHIMA_DURABLE_RUNTIME_REAL_AGENT_EXECUTION_NOT_APPROVED
ARS_SACHIMA_DURABLE_RUNTIME_CONTROLLED_AI_FLOW_EXECUTION_NOT_APPROVED
ARS_SACHIMA_DURABLE_RUNTIME_LIVE_NOT_APPROVED
ARS_SACHIMA_DURABLE_RUNTIME_GATEWAY_NOT_APPROVED
ARS_SACHIMA_DURABLE_RUNTIME_REAL_DELIVERY_NOT_APPROVED
```

Strongest allowed outcome of this PR:

```text
agent_run_supervisor_sachima_supervised_local_activity_durable_runtime_ownership_controlled_local_execution_design_ready_for_separate_local_offline_durable_state_preflight_implementation_request
```

That means a later, narrower local/offline durable-state **preflight** implementation request *may be asked for* — still with no real AGENT execution and no controlled AI FLOW execution. It does **not** authorize durable-runtime implementation, real local `exec`, persistent sessions, cancellation execution, live/default-on behavior, Gateway involvement, real external ingress, real IM/Feishu delivery, production config writes, real AGENT execution, or controlled AI FLOW execution.

## Approval and Boundary

User approval received in chat (exact token):

```text
approve_agent_run_supervisor_sachima_supervised_local_activity_durable_runtime_ownership_controlled_local_execution_design_no_live_no_gateway_no_real_delivery_no_real_agent_execution_no_controlled_ai_flow_execution
```

Interpretation:

- **Approved:** a docs-only Sachima design gate for durable runtime ownership and controlled local execution semantics around the already-merged supervised local Activity wrapper (PR #99) and its dry-run evidence (PR #100), with the status closure from PR #101 as the current base.
- **Not approved:** implementation, runtime code changes, real local `exec`, persistent sessions, cancellation execution, live/default-on behavior, Gateway involvement, real external ingress, real IM/Feishu delivery, production config writes, real AGENT execution, real AGENT auto-routing, or controlled AI FLOW execution.

This packet is and stays **caller-owned by a Sachima/FlowWeaver controller**. It deliberately does **not** name the Gateway as a caller, runtime owner, renderer, or delivery surface. Any durable runtime / Temporal abstraction discussed below is a **design label** for a future *caller-supplied* component, never an approval to start or own one.

## Goal Trace

```text
Goal: Sachima becomes Dog Brother's safe, durable, observable, recoverable IM AI workbench that can run long AI FLOW
      tasks and deliver sanitized results, surviving restarts, retries, duplicates, partial failures, and rollback.
Gap:  PR #98 designed the supervised local Activity; PR #99 implemented an exec_dry_run wrapper with an injected
      supervisor; PR #100 produced deterministic local dry-run evidence; PR #101 closed the status. What is still
      undefined is WHO owns durable product/transaction/Activity state (records, leases, attempts, query projections,
      evidence refs, state transitions) and WHAT preconditions must hold before any future real local execution can
      even be requested. Without that ownership decision, a later implementation could silently leak durable state,
      couple a runtime/Worker/Gateway lifecycle, or drift into real AGENT / controlled AI FLOW execution.
Phase: Docs-only durable-runtime-ownership + controlled-local-execution design packet, positioned after the merged
       supervised local Activity wrapper + dry-run evidence (PR #99/#100/#101) and before any behavior-bearing
       durable-state preflight implementation, real local exec, or controlled AI FLOW execution.
Task: Define the durable runtime ownership model (records/leases/attempts/query projections/evidence refs/state
      transitions), the controlled local execution preconditions, start/query/update/retry/close/cancel semantics
      with cancellation execution deferred, idempotency/stale-state/TOCTOU/retry-ambiguity rules, no-leak/durable-state/
      log rules, a stable failure taxonomy, the docs-only verification gates, and the next (narrower) approval text.
Test: Docs marker gate, manifest parse, changed-file allowlist (docs/status only), no-secret/no-leak scan,
      forbidden-surface scan, and Codex primary review. No runtime tests are run by this PR.
Evidence: This packet, its manifest, this dev log, the current-status update, and the merge evidence of
      PR #96/#97/#98/#99/#100/#101, plus the factual code reference of sachima_supervisor/activity.py and
      sachima_supervisor/activity_evidence.py.
Decision: May request a separate local/offline durable-state preflight implementation only, still no real AGENT
      execution and no controlled AI FLOW execution. Implementation, real local exec, sessions, cancellation
      execution, live/Gateway/real-delivery, real AGENT execution, and controlled AI FLOW execution remain blocked.
```

## Level Selection

**Level 3 — High Risk design.**

Although this PR is docs-only, it touches **future durable runtime and execution semantics**: durable state ownership, leases/locks, retry/idempotency, and the preconditions for any future real local execution. Ambiguity here could later become hidden live execution, a Gateway-owned or Worker-owned runtime lifecycle, durable-state leakage of raw prompts/platform IDs, or drift into real AGENT / controlled AI FLOW execution. The packet is therefore held to strict manifest, explicit non-approvals, no-leak rules, a stable failure taxonomy, and independent blocker review — the same discipline as a production-adjacent design packet.

## Existing Stable Base

| Evidence | Current state | Design impact |
|---|---|---|
| `GOAL.md` | Safety before live capability; low intrusion (Gateway must not silently own Temporal/Worker/queue/daemon/Docker/socket/subprocess lifecycle); explicit per-axis approvals; claim-check discipline; delivery separation. | Durable runtime ownership must stay caller-owned by Sachima/FlowWeaver; the runtime must be caller-supplied; no lifecycle is started or owned here. |
| PR #96 — local/offline integration design | Merged `9305dd29b407cc2b8ddb1ba7ad6508abf5d619da`. | Established the caller is a Sachima/FlowWeaver/Hermes controller, never the Gateway. |
| PR #97 — local/offline supervisor seam | Merged `5affc2fbb68d483683cd61c0871cec528127388e`. | Default-off seam (`sachima_supervisor.local_offline`) that an Activity may later call; still no live/Gateway/real delivery. |
| PR #98 — supervised local Activity design | Merged `675853fd2db2b8f9df781ea46803fd0747ea78cb`. | Defined Activity request/response, role mapping, durable-state rules, and start/query/update/retry/close/cancel labels. |
| PR #99 — supervised local Activity wrapper | Merged `8152d09ee0f847d335a76e2ef90459642fb72e9d`. | Implemented `exec_dry_run` with an injected supervisor, role allowlist, idempotency fingerprinting, sanitized durable state, and an in-memory `ActivityStateStore`. |
| PR #100 — controlled local dry-run evidence | Merged `3fea6e2e8ee836e924c3e0eef1b3ff3a2b930c59`; fixture `tests/fixtures/sachima_supervisor/controlled_local_activity_dry_run_evidence.v1.json`. | Deterministic, injected/fake-only evidence across role mapping, idempotency replay/conflict, sanitized state/query, and unsafe-outcome collapse. Provides the **prior dry-run evidence digest** this design references. |
| PR #101 — status closure | Merged `3b917eeff1c782cea2075909061037816c4eff93` (current base). | Closed the dry-run evidence status; this packet is the recommended next mainline step. |
| `sachima_supervisor/activity.py` (factual reference) | `SupervisedLocalActivityRequest`, `SupervisedLocalActivityResult`, `ActivityStateStore` (idempotency index with request fingerprint), `start`/`query` only, default-off + exact token, role allowlist, sanitized `_build_durable_state`, `_state_from_supervisor_outcome` trust-boundary collapse. | The durable runtime model below generalizes this in-memory store into a design-level durable record/lease/attempt model — names only, not implementation approval. |
| `sachima_supervisor/activity_evidence.py` (factual reference) | Deterministic injected-fake evidence builder; never imports/calls `invoke_local_offline_supervisor`; self-verifies sanitization. | The controlled-local-execution preconditions require a prior dry-run evidence digest of exactly this kind before any future real exec may be requested. |

## Core Ownership Decision

```text
Sachima / FlowWeaver OWNS the durable product/transaction runtime:
  - product transaction state and Activity state
  - leases / locks
  - idempotency
  - retry / update / close policy
  - role mapping (intent -> allowlisted role key)
  - claim-check references
  - the business decision about WHETHER a future local execution may be requested

agent-run-supervisor REMAINS an independent local supervision library:
  - owns local run/session internals and redacted evidence artifacts
  - ONLY once invoked by an approved caller
  - never owns product/transaction state, leases, idempotency, or the business verdict

The Gateway is NOT a caller, NOT a lifecycle owner, NOT a renderer, NOT a delivery surface in this phase.

A Temporal / durable runtime is at most a FUTURE caller-supplied abstraction:
  - this design MUST NOT start or own a Worker, service, CLI, Docker container, socket, or Gateway lifecycle.
```

Rationale:

1. The supervisor library already owns execution mechanics and redacted evidence; Sachima already owns product intent and verdict. Durable runtime ownership is the *missing* decision, and it belongs to Sachima/FlowWeaver, not the supervisor and not the Gateway.
2. Keeping the runtime **caller-supplied** preserves the `GOAL.md` low-intrusion principle: no message-handling path silently acquires a Temporal/Worker/daemon/Docker/socket lifecycle.
3. Naming the runtime as a design label (record/lease/attempt/projection) lets a future implementation slot in a durable backend without this packet approving any specific service start-up.

## Durable Runtime Ownership Model

All names below are **design labels**, not implementation approval. They generalize the merged in-memory `ActivityStateStore` into a durable model that a future caller-supplied runtime could realize.

### Records

```text
ActivityRecord
- activity_id            caller-owned local id (never a platform id)
- transaction_ref        claim-check ref to the Sachima/FlowWeaver transaction
- operation_ref          claim-check ref to the operation/intention record
- role_key               allowlisted role key (never raw role JSON)
- mode / phase           allowlisted mode + caller-owned phase label
- status                 stable status code
- supervisor_status      stable supervisor status code or null
- evidence_ref / digest  sanitized evidence ref + sha256 digest, or null
- artifact_ref_count     non-negative integer
- caller_verdict         caller-owned verdict code or null (library never sets it)
- error_code             stable sanitized error code or null
- retryable              boolean
- view_model_ref         caller-owned local view-model ref
- lease_id / lease_epoch see Leases
- attempt_count          see Attempts
- state_version          monotonically increasing version for optimistic concurrency
```

### Leases

```text
A lease is a caller-owned, time-bounded ownership token over an ActivityRecord state transition.
- lease_id           opaque caller-owned token; not a platform id, not a secret
- lease_epoch        monotonic epoch; a renew/steal increments it
- lease_holder_ref   caller-owned worker/controller label (sanitized)
- lease_deadline     logical deadline marker (design label; no wall-clock leakage into durable history beyond a sanitized marker)
Rules:
- Only the current lease holder (matching lease_id AND lease_epoch) may apply a state transition.
- A stale lease (lower epoch) MUST fail closed; it may not overwrite a newer transition.
- Leases bound idempotency: a transition is the (idempotency_key, fingerprint, lease_epoch) tuple.
- Lease acquisition/renewal/steal is a DESIGN label here; no real lock service is started or owned.
```

### Attempts

```text
AttemptRecord (append-only, per ActivityRecord)
- attempt_index      monotonic, starts at 1
- idempotency_key    stable key for exactly-once local state transition attempts
- request_fingerprint digest of the sanitized request (as in activity.py _fingerprint)
- outcome_status     stable status code for this attempt
- error_code         stable error code or null
- evidence_ref       sanitized evidence ref for this attempt or null
Rules:
- A repeat (idempotency_key, fingerprint) replays the stored terminal attempt; it does NOT launch a new local run.
- A repeat key with a DIFFERENT fingerprint fails closed (idempotency conflict).
- Attempts never store raw material; only stable codes, refs, counts, digests.
```

### Query Projections

```text
A query projection is a sanitized, read-only view derived from the durable record + latest terminal attempt.
- Query NEVER re-invokes the supervisor and NEVER rehydrates raw prompt/context.
- Projection fields are a strict subset of the sanitized durable state (status, mode, phase, refs, counts, digests, codes).
- A "session status" projection that would require contacting a live session is OUT OF SCOPE here (sessions not approved).
```

### Evidence Refs

```text
- evidence_ref is a sanitized local reference (matches the merged ^[a-z][a-z0-9_:-]{0,127}$ shape), never a raw path.
- evidence_digest is sha256:<64 hex>, computed over canonical sanitized content.
- The durable record stores the ref + digest only; raw evidence files stay outside durable history and PR payloads.
```

### State Transitions

```text
created -> validated -> (dry_run_observed | failed)
validated -> idempotent_replay        (no new attempt; replay stored terminal state)
validated -> idempotency_conflict     (fail closed)
dry_run_observed -> queried           (read-only projection; no transition to the record)
any -> failed                         (stable error_code; raw exception suppressed)

NOT in this phase (design-only, separately approved later):
real_exec_requested, real_exec_running, session_open, session_turn, session_closed,
cancel_requested, cancelled, rolled_back
```

Every transition is guarded by: exact approval gate + mode allowlist + role allowlist + material screen + lease holder check + idempotency check + optimistic `state_version` check.

## Controlled Local Execution Preconditions

The following must **all** be true before any later real local execution or session may even be **requested** by a future, separately approved implementation. None of this is approved now; it is the design-level gate list.

```text
1.  exact future approval token present (narrower than implementation/live; see Future Next Approval).
2.  prior dry-run evidence digest: a committed, deterministic dry-run evidence document
    (as in PR #100, sha256 fixture_digest) for the same role/mode exists and matches.
3.  role allowlist: role_key resolves through the fixed caller-owned allowlist; no raw role JSON,
    no path traversal, no absolute path, no platform-derived value.
4.  workspace/root refs: cwd_ref and allowed_roots_ref are allowlisted references, not arbitrary
    path strings from IM/user text.
5.  state lease: the caller holds a current lease (matching lease_id AND lease_epoch) over the record.
6.  request fingerprint: the request fingerprint matches the recorded idempotency binding (no TOCTOU drift).
7.  operator gate: an explicit human operator gate marker is present for the transition.
8.  sanitized claim-check refs only: prompt_ref / context_refs / transaction_ref / operation_ref are
    claim-check refs screened for unsafe material; no raw prompt/context travels.
9.  budget limits: explicit caller-owned budget bounds (max attempts, max artifacts, max evidence size markers)
    are set and enforced before any execution request.
10. NO platform IDs / secrets / raw material anywhere in the request or durable state.
11. NO Gateway involvement and NO delivery surface in the path.
```

If any precondition is absent or ambiguous, the design requires fail-closed behavior — never an opportunistic real execution.

## Lifecycle Semantics

Names are design labels. Only `start` (dry-run), `query`, and idempotent `retry`/replay are realized in the merged wrapper; the rest are design-only and deferred.

### `start`

- Validate exact approval gate, mode allowlist, material screen, role allowlist (as in the merged wrapper).
- In this phase `start` is **dry-run only**; a real-exec `start` is design-only and requires the controlled-local-execution preconditions above plus a separate approval.
- Acquire/confirm a lease and bump `state_version` before persisting a transition.
- Persist a sanitized `ActivityRecord` + append-only `AttemptRecord`; never persist raw material.

### `query`

- Return a sanitized query projection by `activity_id` / `transaction_ref`.
- Never re-invoke the supervisor; never rehydrate raw prompt/context.
- A live "session status" query is out of scope (sessions not approved).

### `update`

- Design-only for session modes. Requires the same role/session/lease binding; any role/workspace/lease drift must fail closed **before** mutation.
- Map supervisor errors to stable caller error codes; never persist raw exception text.

### `retry`

- Retry only with the same `idempotency_key` and compatible stored fingerprint, under a current lease.
- A compatible repeat replays the stored terminal attempt without launching a new local run.
- If prior execution state is ambiguous (see Retry Ambiguity), fail closed with `activity_retry_ambiguous` and require operator intervention.

### `close`

- Close only caller-owned local record/session state. Release the lease.
- Do not send final IM output; final delivery remains out of scope.

### `cancel`

- **Cancellation execution is NOT approved.** Cancel is design-only here.
- Mid-run interruption, partial-artifact handling, lock release on cancel, and idempotent re-entry are future implementation concerns requiring their own design and a separate approval. This packet only records the labels and the fail-closed posture; it does not implement or authorize cancellation.

## Idempotency, Stale-State, TOCTOU, and Retry Ambiguity Rules

```text
Idempotency:
- The unit of exactly-once is (idempotency_key, request_fingerprint).
- A repeat with the same key + same fingerprint replays the stored terminal state (no second supervisor call).
- A repeat with the same key + different fingerprint fails closed: activity_idempotency_conflict.

Stale-state:
- Every durable transition checks state_version (optimistic concurrency) AND lease_epoch.
- A writer holding a stale lease_epoch or a stale state_version MUST fail closed: activity_stale_state.
- A stale reader is harmless (read-only projection), but must not be promoted into a write.

TOCTOU:
- Validation (approval/mode/role/material/preconditions) and the durable transition must be bound by the SAME
  lease_epoch + state_version. If the record changed between check and apply, the apply fails closed: activity_toctou_conflict.
- Workspace/root refs validated at check time must be re-confirmed identical at apply time; any drift fails closed.

Retry ambiguity:
- If a prior attempt's terminal state cannot be determined safely (e.g. an interrupted transition with no committed
  terminal AttemptRecord), retry MUST fail closed with activity_retry_ambiguous and require operator intervention.
- A future real-exec implementation MUST NOT duplicate-launch a local AGENT run merely to resolve ambiguity.
```

## No-Leak, Durable-State, and Log Rules

Durable Sachima/FlowWeaver state, query projections, attempts, evidence refs, and logs may store **only**:

```text
stable status / error codes
mode / phase
caller-owned activity / transaction / operation / session refs
role key (never raw role JSON)
claim-check refs and sha256 digests (never raw prompt/context)
artifact / evidence refs and sha256 digests
counts, retry counters, attempt indices
lease_id / lease_epoch / state_version (sanitized, opaque, non-secret)
caller verdict code (caller-owned; library never sets it)
view-model refs
```

They must **never** store or log:

```text
raw prompt / context / model output
platform private ids (oc_ / ou_ / om_ and similar)
card JSON
media bytes or media paths
tool output
raw acpx/ACP stdout
raw exception text or tracebacks
tokens / credentials / cookies / secrets / raw signatures
arbitrary absolute paths from IM/user text
```

Log rule: logs follow the same allow/forbid lists as durable state. A supervisor failure is logged as a stable code only; the raw exception is suppressed (mirrors the merged wrapper's `activity_supervisor_failed` collapse).

## Failure Taxonomy (Stable Codes)

| Error code | Meaning |
|---|---|
| `activity_disabled` | Activity gate not enabled. |
| `activity_approval_mismatch` | Exact approval marker missing or wrong. |
| `activity_unsupported_mode` | Mode not in the allowlist for the current phase. |
| `activity_unknown_role` | Role key not in the caller-owned allowlist. |
| `activity_unsafe_material` | Input contains platform/private/secret/raw/card/media material. |
| `activity_idempotency_conflict` | Same idempotency key maps to an incompatible request fingerprint. |
| `activity_stale_state` | Stale `state_version` or `lease_epoch` on a durable transition. |
| `activity_lease_lost` | Caller no longer holds a current lease over the record. |
| `activity_toctou_conflict` | Record/workspace drift between validation and durable apply. |
| `activity_retry_ambiguous` | Prior local execution/transition state cannot be safely retried. |
| `activity_precondition_unmet` | A controlled-local-execution precondition is absent or ambiguous. |
| `activity_budget_exceeded` | A caller-owned budget bound would be exceeded. |
| `activity_supervisor_failed` | Supervisor invocation failed/returned unsafe fields; raw detail suppressed. |
| `activity_evidence_write_failed` | Local evidence write failed; raw path/detail suppressed. |
| `activity_not_found` | No durable record for the given activity id. |

## Explicit Non-Approvals

This design packet does **not** approve:

```text
runtime_code_implementation
durable_runtime_code_implementation
real_local_exec
persistent_sessions
cancellation_execution
real_external_sachima_ingress
real_external_delivery
production_delivery_control
production_agent_tool_execution_expansion
production_config_write
gateway_restart_or_reload
platform_adapter_mutation
gateway_owned_temporal_lifecycle
gateway_as_caller_or_renderer_or_delivery_surface
external_temporal_service_or_worker_startup
real_send_api_or_external_im_call
live_or_default_on_behavior
public_webhook_exposure
automatic_replies
worker_auto_routing
agent_to_agent_auto_routing
@all_fanout
trusted_markdown_html_rendering
real_agent_execution
controlled_ai_flow_execution
```

## Verification Gates (Docs-Only PR)

This PR is docs/status only. The gates are documentation and governance gates; no runtime tests are run by this PR.

- [ ] Status markers present and unambiguous (`DESIGN_ONLY`, `IMPLEMENTATION_NOT_APPROVED`, `LOCAL_EXECUTION_NOT_APPROVED`, `REAL_AGENT_EXECUTION_NOT_APPROVED`, `CONTROLLED_AI_FLOW_EXECUTION_NOT_APPROVED`, `NO_LIVE`, `NO_GATEWAY`, `NO_REAL_DELIVERY`).
- [ ] Exact approval token quoted verbatim and scoped to docs-only design.
- [ ] Goal trace links final goal → gap → phase → task → test → evidence → decision.
- [ ] PR #96/#97/#98/#99/#100/#101 base evidence recognized without implying live or implementation approval.
- [ ] Core ownership decision present: Sachima/FlowWeaver owns the durable runtime + business decision; supervisor owns local internals/evidence only; Gateway excluded; runtime is caller-supplied, never started/owned here.
- [ ] Durable runtime model uses design labels only (records / leases / attempts / query projections / evidence refs / state transitions).
- [ ] Controlled-local-execution preconditions enumerated (approval, prior dry-run digest, role allowlist, workspace/root refs, state lease, request fingerprint, operator gate, sanitized refs, budget limits, no platform IDs/secrets/raw material, no Gateway/delivery).
- [ ] Lifecycle covers start/query/update/retry/close/cancel with cancellation execution not approved.
- [ ] Idempotency / stale-state / TOCTOU / retry-ambiguity rules explicit.
- [ ] No-leak / durable-state / log rules list allowed and forbidden data.
- [ ] Stable failure taxonomy present.
- [ ] Explicit non-approvals include implementation, real local exec, sessions, cancellation execution, live, Gateway, real delivery, production config, worker/agent auto-routing, real AGENT execution, and controlled AI FLOW execution.
- [ ] Manifest is YAML-parseable with the required keys and stable `created_at`.
- [ ] Changed-file allowlist is docs/status only (4 paths).
- [ ] Secret-shaped / no-leak scan and forbidden-surface scan pass.
- [ ] Codex primary review returns no blockers.

Hermes runs these gates and the Codex primary review; the author (Documentation Engineer) does not commit, push, merge, run tests, or touch runtime code.

## Future Next Approval

The next, **narrower** approval should be a separate local/offline durable-state **preflight** implementation — still with **no real AGENT execution** and **no controlled AI FLOW execution**:

```text
approve_agent_run_supervisor_sachima_supervised_local_activity_durable_state_preflight_implementation_no_live_no_gateway_no_real_delivery_no_real_agent_execution_no_controlled_ai_flow_execution
```

Recommended scope for that future preflight (each still local/offline, default-off, injected/fake only):

1. A durable-state preflight module that records sanitized `ActivityRecord` / `AttemptRecord` shapes (in-memory or a local store), with lease/epoch/`state_version` fields, **without** any real local execution.
2. Idempotency, stale-state, TOCTOU, and retry-ambiguity enforcement tests using injected/fake outcomes only.
3. Controlled-local-execution precondition checks implemented as *checks that can fail closed*, never as an execution path.
4. No real local `exec`, no sessions, no cancellation execution, no Gateway, no IM delivery, no real AGENT execution, no controlled AI FLOW execution.

This is the recommended mainline next step. **Do not recommend agentic-ui as the default next step**; the agentic-ui Sachima Envelope v1 conformance work remains an open side tail, not the default next move for this supervisor → Sachima mainline.

A later, separately named and separately threat-modeled approval — after the durable-state preflight evidence — would be required before any real local `exec`, persistent sessions, cancellation execution, real AGENT execution, controlled AI FLOW execution, live/default-on behavior, Gateway involvement, real ingress, or real delivery.
