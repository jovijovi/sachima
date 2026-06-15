# WP3a — Cancellation Request State + Supervisor Interrupt API

**Date:** 2026-06-15
**Status:** Merged in PR #138 (`c74c2302129d2e9e1409910966c1075b4b19fabf`) on 2026-06-15. Local gates, final Codex blocker-only re-review, and PR CI passed before merge.
**Branch:** `feature/ars-wp3a-cancellation-interrupt-api`
**Base:** `release/sachima` at `8c50110fe720ad4990b737d8604eb852bbbc409b`

---

## Scope

Local/offline design + implementation of the **cancellation request-state machine
and supervisor interrupt API seam** on the existing Phase E persistent-session
lifecycle. Strongest meaning: a **local/offline injected-fake interrupt API
state machine only** — no real interrupt, no real cancellation execution, no
live/Gateway/Feishu/production/real-delivery behavior. The bounded real
cancellation execution slice (**WP3b**) stays separately gated.

---

## Files Touched

| File | Role |
|------|------|
| `sachima_supervisor/activity_session_lifecycle.py` | Adds `SESSION_INTERRUPT_API_APPROVAL_TOKEN`, `SessionInterruptRequest`/`SessionInterruptOutcome`, `_interrupt_idem` store map, `cancel_interrupting`/`cancelled`/`cancel_failed`/`cancel_ambiguous` statuses, and `apply_session_interrupt(...)` plus supporting helpers; hardens cancel-projection validation per status |
| `tests/sachima_supervisor/test_activity_session_lifecycle.py` | Nine new cancellation/interrupt tests, including Codex blocker regressions for stale in-flight replay finalization, prior-cancel target binding, and same-cancel-id terminal replay; reuse of existing cancel-gate parametrizations |

---

## Behavior Added

- `apply_session_interrupt(request, *, store, apply_interrupt)` advances a prior
  `cancel_requested` record (from `request_cancellation()`) toward a safe terminal
  state using an **injected fake** outcome only.
- Requires an existing prior cancel record **for the same interrupt target**. A
  missing or mismatched prior cancel record fails with `activity_not_found`
  **before** the fake runs (zero fake calls).
- Records `cancelled` only when the fake reports `interrupted=True` **and**
  `cleanup_verified=True`.
- `interrupted=False` ⇒ `cancel_failed` / `activity_supervisor_failed`.
- Unverified cleanup, an `ambiguous` flag, an unsafe/unsanitizable outcome, or a
  fake exception (`None` outcome) ⇒ `cancel_ambiguous` / `activity_cancel_ambiguous`,
  held **fail-closed** (durable record left explicitly ambiguous; raises).
- Dedicated `_interrupt_idem` idempotency: same-fingerprint replay returns the
  existing terminal state; fingerprint mismatch ⇒ `activity_idempotency_conflict`;
  replay on an in-progress `cancel_interrupting` record ⇒ `activity_cancel_ambiguous`.
- Finalization re-reads the resident cancel record before storing the fake outcome,
  so a fail-closed `cancel_ambiguous` written by an in-flight replay cannot be
  overwritten by the original caller's stale pre-fake claim.
- `request_cancellation()` replays an existing same-`cancel_id` record when the
  logical cancellation fingerprint matches, so a new cancellation idempotency key
  cannot reopen a terminal `cancelled`/`cancel_ambiguous` record.

---

## No-Real-Interrupt Posture

- No default real path: the caller must inject `apply_interrupt`; the module never
  signals a real process.
- The session lifecycle record stays authoritative and unmodified by an interrupt;
  only the cancellation request record advances.
- `execute_real_cancellation` still rejects with `activity_cancel_not_approved`.

---

## Evidence (Hermes-verified, this working tree)

| Check | Result |
|-------|--------|
| Focused interrupt/cancel tests (`-k 'interrupt or cancel'`) | 22 passed, 93 deselected |
| Lifecycle + real-execution tests | 164 passed |
| `ruff check` on changed Python files | All checks passed |
| `compileall` on `sachima_supervisor` + tests | exit 0 |
| Full `tests/sachima_supervisor` suite | 518 passed |
| `git diff --check` | exit 0 |
| Added-line secret scan | 0 |
| Forbidden runtime surface scan (lifecycle) | 0 |
| `codegraph status` | up to date |

---

## Worker History (truthful record)

- **Architecture packet:** Claude Code (Opus/max).
- **RED tests:** Claude Code, which then stalled during GREEN.
- **GREEN + one narrow fix:** Codex CLI, acting as a temporary substitute main
  programmer.
- **Codex primary review round 1:** `VERDICT: BLOCKED`; found stale in-flight
  replay finalization and missing prior-cancel target binding.
- **Blocker fixes:** two RED regressions added first, then GREEN fix applied.
- **Final full-diff review round 2:** `VERDICT: BLOCKED`; found same-cancel-id/new-idempotency replay could reopen terminal cancel records.
- **Blocker #3 fix:** two RED regressions added first, then GREEN fix applied.
- **Final re-review:** `VERDICT: PASS`; `BLOCKERS: None`.

---

## Closure

- PR #138 completed the commit/push/open/check/merge lifecycle.
- Roadmap status closure is handled by this post-merge docs-only cleanup.
- WP3b bounded real cancellation execution remains a separate later gate.
