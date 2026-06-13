# agent-run-supervisor x Sachima Phase E Persistent Session Lifecycle State Machine Implementation

> **Status: PR #125 open, awaiting CI / merge decision.** This implementation slice is local/offline only and uses injected fakes only. It does not open a real persistent session, send a real session turn, execute cancellation, invoke `agent-run-supervisor`, invoke `acpx` or `npx`, start a process, touch Gateway/Feishu/IM/live/public surfaces, write production config, restart services, or deliver anything.

## Scope

This slice implements Option A from the merged Phase E design packet:

```text
local/offline persistent-session lifecycle preflight / state-machine slice
injected fakes only
no real session launch
no cancellation execution
no real AGENT execution
no live / Gateway / Feishu / production config / real delivery
```

Branch and worktree:

```text
branch: feature/phase-e-persistent-session-lifecycle
worktree: /home/ecs-user/workspace/hermes/worktrees/sachima/phase-e-persistent-session-lifecycle
status: PR #125 open; head commit 79864934c15527cc86965ccee915d508c3834055; CI pending/in progress; no merge claimed
```

## Approval Boundary

The implementation boundary is the next allowed request recorded in `docs/roadmap/current-status.md` after the Phase E design merge:

```text
approve_agent_run_supervisor_sachima_phase_e_persistent_session_lifecycle_preflight_state_machine_local_offline_implementation_no_real_session_launch_no_cancellation_execution_no_real_agent_execution_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

That phrase is deliberately narrower than persistent-session rollout. It approves only a fail-closed caller-owned state machine exercised with injected fakes.

Explicitly not approved:

```text
persistent_session_execution
cancellation_execution
real_agent_execution
additional_acpx_invocation
npx_fallback_or_network_fetch_evidence
write_capable_claude_or_codex_roles
satine_or_hermes_profile_acp_execution
controlled_ai_flow_execution
gateway_involvement_or_mutation
feishu_or_im_delivery
live_or_default_on_behavior
public_ingress
production_config_write
service_restart_or_reload
platform_adapter_mutation
real_delivery
```

## Implemented Surface

New module:

```text
sachima_supervisor/activity_session_lifecycle.py
```

The module adds a caller-owned durable in-process state machine:

- `SessionLifecycleStore` with a single `RLock`, in-memory session/turn/cancel tables, idempotency tables, and lease records.
- Request and result dataclasses for `SessionCreateRequest`, `SessionSendRequest`, `SessionCloseRequest`, `SessionAbortRequest`, `CancellationRequest`, and their sanitized result projections.
- `create_session(...)`, `send_session_turn(...)`, `query_session(...)`, `list_sessions(...)`, `list_session_turns(...)`, `close_session(...)`, `abort_session(...)`, and `request_cancellation(...)`.
- Exact default-off approval token gate, operator gate, role allowlist reuse, lease/epoch/state-version checks, session-binding checks, request fingerprints, idempotency replay/conflict checks, budget checks, and no-leak projection validation.

All work-like operations require an injected fake callback:

```text
create_session(..., open_session=<fake>)
send_session_turn(..., run_turn=<fake>)
close_session(..., apply_close=<fake>)
abort_session(..., apply_abort=<fake>)
```

There is no default runner and no import/call path to a supervisor, shell, process, Gateway, Feishu, IM adapter, service, socket, Docker, Temporal worker, or delivery surface.

## State Machine

Implemented session states:

```text
session_opening
session_open
session_turn
session_closing
session_closed
session_aborting
session_aborted
session_failed
```

Implemented turn states:

```text
claimed_in_progress
completed
failed_retryable
failed_terminal
turn_ambiguous
```

Implemented cancellation request states:

```text
cancel_requested
rejected
```

Cancellation remains request-state only. `request_cancellation(..., execute=True)` always fails closed with `activity_cancel_not_approved` and records nothing.

## Concurrency And Fail-Closed Rules

The implementation follows the Phase E design discipline:

- Claim under the store lock, release the lock, invoke the injected fake, then finalize under the lock.
- The store lock is never held across the injected fake.
- `session_send` re-reads the durable session under the lock and requires `session_open` plus no `open_turn_index` before claiming a turn.
- Close is valid only from an open session with no in-flight turn.
- Abort is valid from `session_open` or `session_turn`, including an in-flight turn.
- Finalize-time lease or state drift fails closed with `activity_session_toctou_conflict`.
- A turn whose finalize loses the session/lease race is held as `turn_ambiguous`; no duplicate turn launch is attempted.
- Query and list are durable-state projections only and never call a fake or runtime surface.

## Sanitization And No-Leak Rules

Durable records and projections store only stable status/error codes, caller-owned ids/refs, digests, counts, lease fields, state versions, session binding, role key, and sanitized evidence refs.

They reject raw prompts/context, model/tool output, card/media material, platform-private ids, secrets, arbitrary paths, raw exceptions/tracebacks, live process identifiers, and unknown projection keys.

Resident durable state is validated on every read. A poisoned resident projection fails closed as `activity_unsafe_material`.

The candidate also fixes a sanitizer false positive found during this substitute pass: durable `error_code` fields now accept only exact members of the stored stable taxonomy, bypassing the generic platform-id scan for that one field only. This preserves platform-id/secret rejection for every other string field while allowing legitimate taxonomy values such as `activity_session_toctou_conflict`.

## Test Coverage

New test file:

```text
tests/sachima_supervisor/test_activity_session_lifecycle.py
```

Coverage includes:

- exact approval token and default-off gate;
- create happy path, fake failure, unsafe outcome collapse, role allowlist, unsafe material rejection, budget validation, lease/state binding, replay and conflict idempotency;
- send happy path, claim-before-fake, sequential turns, missing/closed session failures, binding/lease/gate failures, replay and conflict idempotency, budget exhaustion, fake failure/unsafe collapse;
- query/list projection-only behavior;
- close idempotency, close during in-flight turn conflict, close of aborted session conflict;
- abort idempotency, operator gate, abort from in-flight `session_turn`;
- finalize-time lease drift to `activity_session_toctou_conflict` and held `turn_ambiguous`;
- true-concurrency create/send/close/abort races;
- cancellation request-state only, execute-not-approved, idempotency, terminal-session rejection record, missing target and unsafe material gates;
- validate-on-read hardening and exact stored `error_code` allowlist behavior without weakening other string scans;
- no default runner and source scan for forbidden runtime/delivery surfaces.

## Current Candidate Verification Gates

Required local gates for this branch:

```text
uv run --extra dev python -m pytest tests/sachima_supervisor/test_activity_session_lifecycle.py -q --tb=short
uv run --extra dev python -m pytest tests/sachima_supervisor -q --tb=short
uv run --extra dev python -m compileall -q sachima_supervisor tests/sachima_supervisor
git diff --check
```

This document does not claim PR, merge, CI, commit, production readiness, real session execution, or cancellation execution.

## Next Decision

Before this can close as a phase slice, a fresh independent Codex review should run in review mode, then Hermes/operator-owned repo actions can decide whether to open a PR. Any later bounded real persistent session, cancellation execution, write-capable role, Satine/Hermes-profile ACP, controlled AI FLOW, Gateway/Feishu/live/public ingress, production config, service restart, or real delivery remains a separate approval gate.
