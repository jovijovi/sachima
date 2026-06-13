# Dev Log - Phase E Persistent Session Lifecycle State Machine Implementation

Date: 2026-06-13
Branch: `feature/phase-e-persistent-session-lifecycle`
Worktree: `/home/ecs-user/workspace/hermes/worktrees/sachima/phase-e-persistent-session-lifecycle`
Status: candidate/open branch; no PR number, merge, CI, or commit claimed.

## Boundary

This is the local/offline Phase E lifecycle preflight/state-machine implementation slice:

- injected fakes only;
- no real persistent session launch;
- no cancellation execution;
- no real AGENT execution;
- no `acpx` or `npx`;
- no Gateway, Feishu, IM, live/public ingress, production config, service restart, platform adapter mutation, or real delivery.

Claude Code had partially implemented the module/tests and then hung/failed to converge. Codex CLI acted only as a temporary substitute worker for implementation/fix, not as the independent primary review. A separate fresh Codex review remains required later.

## Roadmap Preflight

Read before editing:

- `docs/roadmap/current-status.md`
- canonical roadmap: `docs/plans/2026-05-11-sachima-final-goal-phase-development-plan.md`
- Phase E design packet: `docs/plans/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-sessions-cancellation-design.md`
- Phase E design dev log and manifest
- `GOAL.md`
- `docs/roadmap/README.md`

Preflight state:

- Current position: Phase E persistent sessions / cancellation design merged in PR #123 as docs-only; implementation and execution remained separately gated.
- Next allowed request: the local/offline persistent-session lifecycle preflight/state-machine implementation gate with injected fakes only.
- Explicit non-approvals: persistent session execution, cancellation execution, additional real AGENT/acpx, write-capable roles, Satine/Hermes-profile ACP, controlled AI FLOW, Gateway/Feishu/live/public ingress, production config, service restart, platform adapter mutation, and real delivery.
- Open tails: `ROADMAP-WATCH-8788`, `ROADMAP-WATCH-STATUS-DASHBOARD`, `ROADMAP-NEXT-P4-ENV-V1-CONFORMANCE`, `ROADMAP-NEXT-ARS-CONTROLLED-AI-FLOW`.
- Requested task status: allowed as a candidate/open local/offline implementation branch only.

Hermes loaded the current governance workflow guidance, including the persistent-session lifecycle phase-gate reference, before starting this implementation branch.

## Implementation Candidate

Files added in this branch:

```text
sachima_supervisor/activity_session_lifecycle.py
tests/sachima_supervisor/test_activity_session_lifecycle.py
docs/plans/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-session-lifecycle-state-machine-implementation.md
docs/plans/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-session-lifecycle-state-machine-implementation-manifest.yaml
docs/dev_log/2026-06-13-agent-run-supervisor-sachima-phase-e-persistent-session-lifecycle-state-machine-implementation.md
docs/roadmap/current-status.md
```

Implemented behavior:

- `SessionLifecycleStore` with durable in-process session/turn/cancel state, idempotency records, lease records, and a single lock.
- `create_session`, `send_session_turn`, `query_session`, `list_sessions`, `list_session_turns`, `close_session`, `abort_session`, and `request_cancellation`.
- Exact approval token and default-off gate.
- Operator gate, caller-owned role allowlist, lease/epoch/state-version/session-binding guards.
- Claim outside fake invocation and finalize-time CAS/drift checks.
- Idempotent replay and conflict detection.
- Single in-flight turn rule.
- Abort from `session_turn` with an in-flight turn; the in-flight send finalize then fails closed/ambiguous and does not duplicate launch.
- Cancellation request-state only; `execute=True` fails closed with `activity_cancel_not_approved`.
- Query/list projections from durable state only.
- Validate-on-read hardening and no-leak scans.

## Substitute Fix Pass

Reproduced starting failure:

```text
uv run --extra dev python -m pytest tests/sachima_supervisor/test_activity_session_lifecycle.py -q --tb=short
2 failed, 97 passed
```

Failures:

- `test_abort_is_valid_from_session_turn_in_flight` returned `activity_unsafe_material` instead of `activity_session_toctou_conflict` or `activity_session_turn_ambiguous`.
- `test_send_finalize_lease_drift_fails_closed_and_holds_turn_ambiguous` returned `activity_unsafe_material` instead of `activity_session_toctou_conflict`.

Root cause:

- The module had `_is_safe_stored_error_code()`, but resident projection validators still validated durable `error_code` with `_safe_code()` and then scanned every string with the generic platform-id/secret detector.
- Legitimate stable taxonomy values such as `activity_session_toctou_conflict` contain an `ou_` substring in `toctou_conflict`, so the generic platform-id heuristic false-positively rejected the resident durable state as unsafe material.

Fix:

- Added a focused regression test proving exact stored `error_code` taxonomy values are accepted while platform-id-shaped strings in other fields are still rejected.
- Expanded `_STORED_ERROR_CODES` to the stable stored taxonomy.
- Changed session/turn/cancel resident projection validators to use exact membership for `error_code`.
- Changed `_assert_all_strings_safe()` to bypass the generic string scan only for the `error_code` field after exact taxonomy membership has passed.
- Left all request fields, refs, supervisor statuses, reason codes, evidence refs, prompt refs, view refs, and other durable strings on the existing unsafe-material scan path.

Focused RED/GREEN evidence:

```text
uv run --extra dev python -m pytest tests/sachima_supervisor/test_activity_session_lifecycle.py::test_query_accepts_exact_stored_error_code_without_weakening_string_scan -q --tb=short
RED before fix: 1 failed
GREEN after fix: 1 passed
```

Focused file verification after the fix:

```text
uv run --extra dev python -m pytest tests/sachima_supervisor/test_activity_session_lifecycle.py -q --tb=short
100 passed
```

## Pending Review

The first fresh Codex primary review returned `VERDICT: BLOCKERS` and found three real implementation gaps:

1. lifecycle finalize drift for create/close/abort raised `activity_session_toctou_conflict` but left opening/closing/aborting records queryable with `error_code: null`;
2. failed turns were not append-only and did not consume turn budget, allowing later sends to overwrite turn index 1 and bypass `max_turns`;
3. `max_artifacts_per_turn` was recorded on the session but not enforced against turn outcomes.

Narrow fixes now applied:

- finalize drift now marks still-claimed lifecycle records as `session_failed` with `activity_session_toctou_conflict` before raising;
- terminal failed turns now consume turn budget, later turns get new append-only indexes, and `_store_turn()` rejects attempts to overwrite finalized turns;
- turn outcome materialization rejects artifact counts above the session's `max_artifacts_per_turn`.

Added regression tests for all three blocker classes.

Blocker-only Codex re-review then returned:

```text
VERDICT: PASS
BLOCKERS:
- None
```

Codex reported that it re-ran focused lifecycle tests, the full `tests/sachima_supervisor` suite, compileall, `git diff --cached --check`, CodeGraph status, manifest YAML parsing, and a forbidden runtime surface scan. This dev log still does not claim PR, CI, merge, or commit completion.
