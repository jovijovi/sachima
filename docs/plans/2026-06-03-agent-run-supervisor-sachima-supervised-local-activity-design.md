# agent-run-supervisor × Sachima Supervised Local Activity Design Packet

> **For Hermes:** This is a docs-only design packet. Do not implement runtime code from this document unless Dog Brother later gives the exact separate implementation approval named below. This packet does not approve live behavior, Gateway involvement, real external ingress, real IM/Feishu delivery, production config writes, Gateway restart/reload, automatic replies, worker auto-routing, or controlled AI FLOW execution.

**Goal:** Define the next caller-owned Sachima/FlowWeaver Activity layer that can drive the already-merged `sachima_supervisor` local/offline seam while preserving durable state, claim-check boundaries, role mapping, query/update semantics, sanitized evidence, and strict no-live/no-Gateway/no-real-delivery boundaries.

**Architecture:** Sachima owns the product/transaction Activity. `agent-run-supervisor` remains a local supervisor library/evidence layer. The Gateway is not a caller, not a lifecycle owner, and not a delivery surface in this phase.

---

## Status Markers

```text
DESIGN_ONLY
IMPLEMENTATION_NOT_APPROVED
LIVE_NOT_APPROVED
GATEWAY_NOT_APPROVED
REAL_DELIVERY_NOT_APPROVED
CONTROLLED_AI_FLOW_EXECUTION_NOT_APPROVED
```

Scoped markers:

```text
ARS_SACHIMA_SUPERVISED_LOCAL_ACTIVITY_DESIGN_ONLY
ARS_SACHIMA_SUPERVISED_LOCAL_ACTIVITY_IMPLEMENTATION_NOT_APPROVED
ARS_SACHIMA_SUPERVISED_LOCAL_ACTIVITY_LIVE_NOT_APPROVED
ARS_SACHIMA_SUPERVISED_LOCAL_ACTIVITY_GATEWAY_NOT_APPROVED
ARS_SACHIMA_SUPERVISED_LOCAL_ACTIVITY_REAL_DELIVERY_NOT_APPROVED
```

Strongest allowed outcome of this PR:

```text
agent_run_supervisor_sachima_supervised_local_activity_design_ready_for_separate_local_offline_implementation_request
```

That means a later implementation request may be asked for. It does **not** mean Activity implementation, live/default-on behavior, Gateway involvement, real external ingress, real IM/Feishu delivery, production config writes, or real controlled AI FLOW execution are approved.

## Approval and Boundary

User approval received in chat:

```text
清理 PR #97 分支/worktree，并批准开启 agent-run-supervisor × Sachima supervised local Activity design packet：no live, no Gateway, no real delivery
```

Interpretation:

- Approved: docs-only design packet for a supervised local Activity/controller layer in Sachima.
- Approved cleanup: PR #97 remote branch, local branch, and worktree cleanup.
- Not approved: runtime implementation, live behavior, Gateway involvement, real external ingress, real delivery, production config writes, platform adapter mutation, automatic replies, worker auto-routing, or default-on behavior.

## Goal Trace

```text
Goal: Sachima becomes Dog Brother's safe, durable, observable, recoverable IM AI workbench for long AI FLOW tasks.
Gap:  PR #96 designed a local/offline supervisor integration and PR #97 implemented the default-off seam, but Sachima still lacks
      a FlowWeaver Activity/controller contract for role mapping, start/query/update/retry/close semantics, durable state,
      claim-check inputs, and sanitized evidence around that seam.
Phase: Docs-only supervised local Activity design packet, after PR #97 local/offline seam implementation and before any
       behavior-bearing Activity implementation or controlled AI FLOW execution.
Task: Define Activity API, role/permission mapping, durable state shape, no-leak boundaries, retry/idempotency rules,
      view/evidence ownership, verification gates, and next approval text.
Test: Docs marker gate, manifest parse, changed-file allowlist, no-secret/no-leak scan, forbidden-surface scan, and Codex review.
Evidence: This packet, manifest, dev log, current-status update, PR #96/#97 merge evidence, and post-merge PR #97 test evidence.
Decision: May request a separate local/offline Activity implementation only. Live/Gateway/real-delivery/controlled-AI-FLOW remain blocked.
```

## Level Selection

**Level 3 — High Risk design.**

Even though this PR is docs-only, it designs an Activity around local AGENT supervision. Ambiguity here could later become hidden live execution, Gateway lifecycle coupling, or raw prompt/delivery leakage. Therefore the packet uses strict manifest, explicit non-approvals, no-leak gates, and independent blocker review.

## Existing Stable Base

| Evidence | Current state | Design impact |
|---|---|---|
| `GOAL.md` | Requires safety before live capability, low intrusion, explicit per-axis approvals, claim-check discipline, and delivery separation. | The Activity must be caller-owned, local/offline, default-off-by-design, and Gateway-free. |
| PR #96 | Merged local/offline integration design, merge `9305dd29b407cc2b8ddb1ba7ad6508abf5d619da`. | Established the caller is Sachima/FlowWeaver/Hermes controller, not Gateway. |
| PR #97 | Merged `sachima_supervisor` local/offline seam, merge `5affc2fbb68d483683cd61c0871cec528127388e`. | Activity can call the seam later but must still avoid live/Gateway/real delivery. |
| `sachima_supervisor.local_offline` | Default-off, exact approval token, mode allowlist, lazy `agent_run_supervisor` import, sanitized offline view/evidence. | This becomes the implementation target for a future Activity wrapper. |
| `agent_run_supervisor.caller` | `CallerInvocationSpec`, `CallerResult`, `invoke_caller`; `business_verdict` remains `None`. | Activity owns business verdict and product state; supervisor owns status/evidence only. |

## Core Design Decision

```text
The supervised local Activity is a Sachima/FlowWeaver caller wrapper around `sachima_supervisor`.
It is not Gateway code.
It is not a platform adapter.
It is not a Temporal/Gateway lifecycle owner.
It is not real delivery.
```

The Activity is the bridge between durable Sachima transaction state and the local/offline supervisor seam. The Activity may produce local evidence and caller-owned offline view models only. Any IM card, Feishu message, real callback, live worker, or Gateway presentation surface stays out of scope.

## Architecture Diagram

```text
[ sanitized Sachima transaction intent ]
            │
            │ claim-check refs + role id + mode + operator-approved local activity request
            ▼
[ FlowWeaver / Sachima supervised local Activity ]      OWNED BY SACHIMA
            │
            │ validate gates, idempotency, role allowlist, state lease, no-leak input
            │ build LocalOfflineSupervisorRequest
            ▼
[ sachima_supervisor.local_offline ]                    LOCAL/OFFLINE SEAM
            │
            │ exact approval token + enabled flag + safe mode + role source
            │ lazy build CallerInvocationSpec / invoke_caller
            ▼
[ agent-run-supervisor ]                                LOCAL LIBRARY
            │
            │ compile AgentRoleSpec, supervise exec/session, write redacted local evidence
            ▼
[ LocalOfflineSupervisorOutcome ]                       SANITIZED RESULT
            │
            │ status + mode + phase + artifact/evidence refs + digest + caller verdict
            ▼
[ FlowWeaver durable state + offline view model ]        SANITIZED ONLY
            │
            ✗ no Gateway   ✗ no IM send   ✗ no real delivery   ✗ no live/default-on
```

## Activity API Contract

The future implementation should introduce a narrow Activity/controller API. Names are design labels, not code approval.

### Request shape

```text
SupervisedLocalActivityRequest
- activity_id: stable local activity id; caller-owned, not a platform id
- transaction_ref: claim-check reference to the Sachima/FlowWeaver transaction
- operation_ref: claim-check reference to the operation/intention record
- idempotency_key: stable key for exactly-once local state transition attempts
- mode: exec_dry_run | exec | session_create | session_send | session_status | session_close
- role_ref: role allowlist key or role_file ref; no raw role JSON in durable history
- prompt_ref: optional claim-check ref to sanitized prompt material
- context_refs: zero or more claim-check refs to sanitized context material
- cwd_ref: allowlisted workspace reference, not an arbitrary path string from IM
- allowed_roots_ref: allowlisted root set reference
- runs_dir_ref / sessions_dir_ref / evidence_dir_ref: local artifact root refs
- session_ref: caller-owned session label for session modes
- approval_gate: explicit local/offline Activity implementation approval marker
- dry_run_first: boolean; true for the first implementation slice
```

### Response shape

```text
SupervisedLocalActivityResult
- ok: boolean
- status: stable caller status code
- supervisor_status: stable supervisor status code or null
- mode: copied allowed mode
- phase: dry_run | exec | session
- activity_id: caller-owned id
- transaction_ref / operation_ref: original refs
- session_ref: caller-owned session label or null
- evidence_ref: local evidence ref, never raw path unless already sanitized by the seam
- evidence_digest: sha256 digest
- artifact_ref_count: integer
- caller_verdict: caller-owned verdict code or null
- error_code: stable sanitized error code or null
- retryable: boolean
- view_model_ref: optional local offline view model ref
```

No response field may contain raw prompt, raw context, raw model text, platform id, card JSON, media path/bytes, raw tool output, raw exception text, traceback, token, credential, cookie, or signature.

## Role and Permission Mapping

The Activity owns the mapping from Sachima business intent to supervisor role reference. It must not accept an arbitrary `role_file` path from IM/user text.

| Sachima intent class | Proposed role key | Allowed first mode | Notes |
|---|---|---|---|
| `docs_design` | `sachima.docs_planner` | `exec_dry_run` | Produce/validate plans and docs-only packets; no live execution. |
| `code_implementation` | `sachima.coding_worker` | `exec_dry_run` then `exec` after separate approval | Local/offline only; no Gateway/tool expansion. |
| `code_review` | `sachima.primary_reviewer` | `exec_dry_run` then `exec` after separate approval | Reviewer produces blocker summary and evidence refs. |
| `status_audit` | `sachima.verifier` | `exec_dry_run` | Reads local refs and emits sanitized status/evidence. |
| `session_collaboration` | `sachima.session_worker` | `session_create` then `session_send/status/close` after separate approval | Persistent session semantics require stronger idempotency and stale-state gates. |

The role map should be a versioned local config/artifact in a future implementation, with tests proving unknown roles, path traversal, absolute paths, and platform-derived values fail closed.

## Activity Lifecycle Semantics

### `start`

- Validate exact Activity approval marker.
- Validate mode allowlist.
- Resolve role key through a local allowlist.
- Resolve claim-check refs to sanitized prompt/context only inside the local Activity boundary.
- Build `LocalOfflineSupervisorRequest` with `enabled=True` and exact implementation token.
- Call `invoke_local_offline_supervisor` only after idempotency and no-leak checks pass.
- Persist sanitized result state only.

### `query`

- Return durable sanitized Activity state by `activity_id` / `transaction_ref`.
- Never rehydrate raw prompt/context into the returned payload.
- Never call the supervisor library merely to query a user-visible card; query is local state only unless a separately approved session status mode exists.

### `update`

- For session modes only, accept a sanitized `prompt_ref`/`context_refs` update.
- Require the same role/session binding; a role/workspace drift must fail closed before mutation.
- Map supervisor errors into stable caller error codes.

### `retry`

- Retry only with the same `idempotency_key` and compatible stored state.
- If prior execution state is ambiguous, fail closed with `activity_retry_ambiguous` and require operator intervention.
- Never duplicate-launch a local AGENT run just to satisfy a retry.

### `close`

- Close only caller-owned local session state and local supervisor session state.
- Do not send final IM output; final delivery remains out of scope.

### `cancel`

Cancellation is **design-only** here and not part of the next implementation slice unless separately approved. Mid-run interruption, partial artifacts, lock release, and re-entry semantics require their own implementation design/gate.

## Durable State Rules

Durable Sachima/FlowWeaver state may store:

```text
stable status codes
mode / phase
caller-owned activity/session/transaction refs
role key, not raw role JSON
claim-check refs and digests, not raw prompt/context
artifact/evidence refs and sha256 digests
counts, timestamps, retry counters, lease/version numbers
stable error codes
```

It must not store:

```text
raw prompt/context/model output
platform private ids
card JSON
media paths or bytes
tool output
raw acpx stdout
raw exception text or traceback
credential-shaped values
```

## No-Leak and Log Rules

All future implementation tests must cover at least:

- request rejection for platform-id-shaped values (`oc_`, `ou_`, `om_`) in public Activity inputs;
- rejection of secret-shaped strings in prompt/context refs, caller verdict, and role labels;
- no raw exception text in returned result, evidence file, durable state, logs, or offline view model;
- no card JSON / media path / Feishu SDK / Gateway imports in the Activity module;
- public helper functions enforce the same no-leak boundary as the end-to-end Activity path.

## Failure and Error Taxonomy

Future implementation should use stable error codes such as:

| Error code | Meaning |
|---|---|
| `activity_disabled` | Activity gate is not enabled. |
| `activity_approval_mismatch` | Exact approval marker missing or wrong. |
| `activity_unsupported_mode` | Mode not in allowlist. |
| `activity_unknown_role` | Role key not in allowlist. |
| `activity_unsafe_material` | Input contains platform/private/secret/raw material. |
| `activity_idempotency_conflict` | Same key maps to incompatible request. |
| `activity_retry_ambiguous` | Prior local execution state cannot be safely retried. |
| `activity_supervisor_failed` | Supervisor invocation failed; raw exception suppressed. |
| `activity_evidence_write_failed` | Local evidence write failed; raw path/detail suppressed. |

## Explicit Non-Approvals

This design packet does **not** approve:

```text
runtime_code_implementation
real_external_sachima_ingress
real_external_delivery
production_delivery_control
production_agent_tool_execution_expansion
production_config_write
gateway_restart_or_reload
platform_adapter_mutation
gateway_owned_temporal_lifecycle
real_send_api_or_external_im_call
external_temporal_service_or_worker_startup
live_or_default_on_behavior
public_webhook_exposure
automatic_replies
worker_auto_routing
agent_to_agent_auto_routing
@all_fanout
trusted_markdown_html_rendering
controlled_ai_flow_execution
```

## Future Implementation Request

The next narrow approval text should be:

```text
approve_agent_run_supervisor_sachima_supervised_local_activity_implementation_no_live_no_gateway_no_real_delivery
```

That future implementation should still be local/offline only. Recommended first slice:

1. Add an Activity wrapper module around `sachima_supervisor.local_offline`.
2. Implement `exec_dry_run` only with injected/fake supervisor calls first.
3. Add role-map allowlist validation and claim-check ref validation.
4. Add sanitized durable-state/result mapping tests.
5. Add no-leak/forbidden-surface tests.
6. Do not start real AGENT execution, real sessions, Gateway code, IM delivery, or production runtime lifecycle.

A later, separately approved behavior-bearing slice may extend to real local `exec` / session operations, still no live/no real delivery, only after the dry-run Activity wrapper is proven.

## Acceptance Checklist

- [ ] Status markers present and unambiguous.
- [ ] Approval text quoted and scoped to docs-only design.
- [ ] Goal trace links final goal → gap → phase → task → tests → evidence → decision.
- [ ] PR #96/#97 base evidence recognized without implying live approval.
- [ ] Activity request/response contracts include only claim-check refs, stable codes, counts, digests, and local refs.
- [ ] Role mapping is caller-owned and allowlisted.
- [ ] Lifecycle covers start/query/update/retry/close/cancel with cancellation deferred.
- [ ] Durable state rules and no-leak/log rules are explicit.
- [ ] Explicit non-approvals include live, Gateway, real delivery, production config, worker auto-routing, automatic replies, and controlled AI FLOW execution.
- [ ] Next implementation approval text is narrower than live/real delivery.
- [ ] Changed-file allowlist is docs/status only.
- [ ] Secret/no-leak and forbidden-surface scans pass.
- [ ] Codex primary review returns no blockers.
