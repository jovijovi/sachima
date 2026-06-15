# WP3a — Cancellation request state + supervisor interrupt API (local/offline, injected fake only; NO real interrupt)

Date: 2026-06-15
Status: **Implementation candidate — PR-ready local branch.** Local gates and final Codex blocker-only re-review PASS; not merged. PR/CI state must be checked live in GitHub after PR creation.
Branch: `feature/ars-wp3a-cancellation-interrupt-api`
Base: `release/sachima` at `8c50110fe720ad4990b737d8604eb852bbbc409b`

## Scope

WP3a designs and implements the **cancellation request-state machine and the
supervisor interrupt API seam** for the existing local/offline persistent-session
lifecycle. It is the request-state-plus-API-seam step only.

Strongest meaning: a **local/offline, injected-fake interrupt API state machine
only**. It does **not** perform a real interrupt, does not execute real
cancellation, and adds no live/Gateway/Feishu/production/real-delivery behavior.
The bounded real cancellation execution slice (**WP3b**) remains separately gated.

WP3a builds directly on the Phase E lifecycle state machine
(`sachima_supervisor/activity_session_lifecycle.py`, merged in PR #125), which
already added `request_cancellation()` producing a durable `cancel_requested`
record. WP3a advances that request record toward a safe terminal state when a
caller supplies an **injected fake interrupt outcome**.

### Exact approval token

The new approval token in the code is request-state + API-seam scoped only and
explicitly does **not** approve a real interrupt:

```text
approve_agent_run_supervisor_sachima_cancellation_request_state_and_supervisor_interrupt_api_design_local_offline_no_real_interrupt_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

(Constant `SESSION_INTERRUPT_API_APPROVAL_TOKEN` in
`sachima_supervisor/activity_session_lifecycle.py`.)

## What changed (production: `sachima_supervisor/activity_session_lifecycle.py`)

1. **New approval token** `SESSION_INTERRUPT_API_APPROVAL_TOKEN` — exact-match
   gate for the interrupt API seam; approves caller-owned cancellation
   request-state transitions driven by an injected fake outcome only, never a
   real interrupt.
2. **New request/outcome dataclasses** (frozen):
   - `SessionInterruptRequest` — carries `cancel_id`, `activity_id`,
     `session_id`, transaction/operation refs, `idempotency_key`,
     `approval_token`, `enabled` (default `False`), session binding, lease
     fields, `turn_index`, `operator_gate`, etc.
   - `SessionInterruptOutcome` — the injected fake result:
     `interrupted: bool`, `cleanup_verified: bool = False`, `ambiguous: bool =
     False`, optional `supervisor_status`, `evidence_ref`, `evidence_digest`,
     `error_code`.
3. **New cancellation statuses** added to `_CANCEL_STATUSES`:
   `cancel_interrupting`, `cancelled`, `cancel_failed`, `cancel_ambiguous`
   (alongside the pre-existing `cancel_requested` / `rejected`). A new
   `_CANCEL_TERMINAL_STATUSES = {rejected, cancelled, cancel_failed,
   cancel_ambiguous}` set defines safe terminal states.
4. **New store field** `SessionLifecycleStore._interrupt_idem` — a dedicated
   idempotency map for interrupt applications, keyed by `idempotency_key` to a
   `(fingerprint, validated_state)` tuple.
5. **New public function**
   `apply_session_interrupt(request, *, store, apply_interrupt)` — applies a
   caller-approved interrupt result through an injected fake. There is **no
   default runner**; the module never signals a real process. The durable
   cancellation record advances to one of `cancelled`, `cancel_failed`, or
   `cancel_ambiguous` while the session lifecycle record stays authoritative and
   unmodified.
6. **Supporting helpers**: `_check_interrupt_enabled_and_approved`,
   `_interrupt_fingerprint`, `_cancel_with`, `_store_interrupt_cancel`,
   `_check_interrupt_cancel_target`, `_cancel_from_interrupt_outcome`,
   `_safe_interrupt_call`; `_new_cancel`, `_check_cancel_material`, and
   `_check_cancel_turn_scope` were generalized to accept
   `CancellationRequest | SessionInterruptRequest`. The cancel-projection
   validator (`_validate_cancel_projection`) was hardened to enforce
   per-status invariants (e.g. `ok`/`error_code`/evidence shape per status).

## State machine

Pre-state required: a prior `cancel_requested` record produced by
`request_cancellation()` for the same `cancel_id` **and the same interrupt
target** (`activity_id`, `session_id`, transaction/operation refs, turn scope,
and lease fields). If no matching prior cancel record exists,
`apply_session_interrupt` fails with `activity_not_found` **before** the fake is
ever called (zero fake invocations).

Gating order (fail-closed) inside `apply_session_interrupt`:

1. `_check_interrupt_enabled_and_approved` — `enabled is True` and exact
   `SESSION_INTERRUPT_API_APPROVAL_TOKEN`; else `activity_session_disabled` /
   `activity_session_approval_mismatch`.
2. `_check_operator_gate` — explicit operator gate required.
3. `_check_cancel_material` — required refs present and well-formed.
4. Under the store lock: cancellation-idempotency replay check, same-`cancel_id`
   durable record replay/conflict check, resident session lookup + `session_id`
   match (`activity_not_found` otherwise), session-binding guard, lease guard,
   turn-scope guard, then prior cancel record existence, target binding check,
   and status handling.
5. Claim transition to `cancel_interrupting` is persisted **before** the fake is
   called; the fake runs **outside** the lock; the lock is re-acquired and the
   resident cancel record is re-read before recording the terminal outcome, so
   a fail-closed in-flight replay cannot be overwritten by a stale claim.

Terminal outcome mapping (`_cancel_from_interrupt_outcome`):

| Injected fake outcome | Terminal status | `error_code` |
|---|---|---|
| `interrupted=True` **and** `cleanup_verified=True` (safe) | `cancelled` | none; `ok=True`, evidence carried |
| `interrupted=False` | `cancel_failed` | `activity_supervisor_failed` |
| `interrupted=True` but `cleanup_verified=False` | `cancel_ambiguous` | `activity_cancel_ambiguous` |
| `ambiguous=True` flag set | `cancel_ambiguous` | `activity_cancel_ambiguous` |
| unsafe/unsanitizable outcome fields | `cancel_ambiguous` | `activity_cancel_ambiguous` |
| fake raised an exception (`None` outcome via `_safe_interrupt_call`) | `cancel_ambiguous` | `activity_cancel_ambiguous` |

`cancel_ambiguous` is held **fail-closed**: the durable record is left explicitly
ambiguous (not silently cancelled, not rolled back) and `apply_session_interrupt`
raises `SessionLifecycleError("activity_cancel_ambiguous", ...)`.

Additional fail-closed edges:
- Idempotent replay returns the existing terminal state for the same fingerprint;
  a fingerprint mismatch raises `activity_idempotency_conflict`.
- A replay landing on a still-in-progress `cancel_interrupting` record is treated
  as ambiguous (`activity_cancel_ambiguous`), fail-closed.
- If the session lifecycle is already terminal, the record is recorded
  `cancel_failed` / `activity_supervisor_failed`.

## Injected-fake-only / no-real-interrupt posture

- `apply_session_interrupt` requires the caller to pass `apply_interrupt`; the
  module has no default real path and never signals a real process.
- The session lifecycle state machine itself remains unmodified by an interrupt;
  an interrupt only advances the **cancellation request** record.
- `execute_real_cancellation` still rejects with `activity_cancel_not_approved`.
  WP3a does not enable real cancellation execution.

## Tests (RED→GREEN; `tests/sachima_supervisor/test_activity_session_lifecycle.py`)

Nine new cancellation/interrupt behaviors plus reuse of existing cancel-gate
parametrizations:

- `test_apply_session_interrupt_stops_run_and_records_cancelled`
- `test_apply_session_interrupt_not_stopped_records_cancel_failed`
- `test_apply_session_interrupt_cleanup_unverified_is_ambiguous`
- `test_apply_session_interrupt_idempotent_replay_fires_fake_once`
- `test_apply_session_interrupt_replay_during_fake_keeps_ambiguous`
- `test_apply_session_interrupt_prior_cancel_must_match_target`
- `test_apply_session_interrupt_without_prior_cancel_record_fails_before_fake`
- `test_request_cancellation_same_cancel_id_cannot_reopen_cancelled_record`
- `test_request_cancellation_same_cancel_id_cannot_reopen_ambiguous_record`

## Verification (Hermes-verified, this working tree)

```text
uv run --frozen --extra dev pytest -q -o 'addopts=' \
  tests/sachima_supervisor/test_activity_session_lifecycle.py -k 'interrupt or cancel'
  => 22 passed, 93 deselected

uv run --frozen --extra dev pytest -q -o 'addopts=' \
  tests/sachima_supervisor/test_activity_session_lifecycle.py \
  tests/sachima_supervisor/test_activity_session_real_execution.py
  => 164 passed

uv run --frozen --extra dev ruff check \
  sachima_supervisor/activity_session_lifecycle.py \
  tests/sachima_supervisor/test_activity_session_lifecycle.py
  => All checks passed

uv run --frozen --extra dev python -m compileall -q sachima_supervisor tests/sachima_supervisor
  => exit 0

uv run --frozen --extra dev pytest -q -o 'addopts=' tests/sachima_supervisor
  => 518 passed

git diff --check                               => exit 0
added-line secret scan                         => 0
forbidden runtime surface scan (lifecycle)     => 0
codegraph status                               => up to date
```

## Explicit non-approvals (held)

WP3a holds all prior non-approvals and adds none of the following:
`real_interrupt`, `real_cancellation_execution` (WP3b),
`additional_real_local_smoke_execution`, `additional_real_agent_execution`,
`additional_acpx_invocation`, `npx_fallback_or_network_fetch`,
`write_capable_claude_or_codex_roles`, `satine_or_hermes_profile_acp_execution`,
`controlled_ai_flow_execution`, `gateway_involvement_or_mutation`,
`feishu_or_im_delivery`, `live_or_default_on_behavior`, `public_ingress`,
`production_config_write`, `real_delivery`. `execute_real_cancellation` still
rejects with `activity_cancel_not_approved`.

## Worker history (truthful record)

- Claude Code (Opus/max) produced the WP3a architecture packet.
- Claude Code produced the RED tests but stalled during GREEN.
- Codex CLI acted as a temporary substitute main programmer to complete GREEN and
  one narrow fix.
- Codex primary review round 1 returned `VERDICT: BLOCKED` on stale in-flight
  replay finalization and missing prior-cancel target binding.
- Two blocker regressions were added RED first, then the GREEN fix was applied.
- Final full-diff review round 2 returned `VERDICT: BLOCKED` on same-`cancel_id`
  / new-cancel-idempotency replay reopening terminal cancel records.
- Two blocker #3 regressions were added RED first, then the GREEN fix was applied.
- Final re-review is pending after the blocker #3 fix.

## Pending

- Commit, push, PR creation, CI.
- Roadmap status closure once a PR/merge exists.
- WP3b bounded real cancellation execution remains a separate later gate.
