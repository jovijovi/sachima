# WP2 Bounded Multi-Turn Persistent Session Hardening

**Date:** 2026-06-15
**Status:** Implementation candidate — branch only; not yet PR-reviewed, CI-validated, or merged.

---

## Scope

Local/offline hardening of the bounded multi-turn persistent session path. Specifically:

- **Read-only** persistent session smoke: no write roles, no cancellation execution, no controlled AI FLOW, no Gateway/Feishu integration, no live/production config, no real delivery.
- One session with a bounded N sequential turns (`run_lifecycle(turn_prompts=[...])`).
- CLI self-test via `--turn-count` flag.
- No raw prompt text or final AI message is persisted in durable Sachima state; any business marker reading happens host-side from out-of-repo runtime result files.

---

## Files Touched

| File | Role |
|------|------|
| `scripts/sachima_phase_e2_persistent_session_smoke.py` | Smoke driver: `run_lifecycle`, empty-prompt guard, `--turn-count` CLI flag |
| `tests/sachima_supervisor/test_activity_session_real_execution.py` | Post-verify: N-turn state-machine count, N real result marker checks |

---

## Behavior Added

- `run_lifecycle(turn_prompts=...)` — drives one session through N sequential turns.
- Empty prompt guard fires before any runtime/backend call; rejects blank turns early.
- `post_verify` checks two invariants after lifecycle completes:
  - `turn_count_state_machine == N` — state machine advanced exactly N times.
  - N real result markers present in runtime output — confirms each turn produced a real result, not a stub.
- `--turn-count <N>` CLI flag runs a self-contained offline self-test returning `{"ok": true, "post_verify": {"turn_count_state_machine": N}}`.

---

## Evidence (Hermes-verified, this branch)

| Check | Result |
|-------|--------|
| Focused WP2 tests | 7 passed |
| Focused lifecycle + real execution tests | 155 passed |
| `--turn-count 2` CLI self-test | `ok=true`, `post_verify.turn_count_state_machine=2` |
| `git diff --check` | Clean — no whitespace errors |
| `ruff check` on changed Python files | Passed |
| `compileall` on affected supervisor/script domain | Passed |
| `tests/sachima_supervisor` | 509 passed |
| Codex CLI primary blocker-only review | PASS — blockers none |

A broad local full-repo `pytest --all-extras` probe was attempted, but it is not used as this branch's readiness gate: it ran into unrelated repository-wide/baseline failures and timeout outside the touched Sachima supervisor surface. CI remains the authoritative broad-repo signal after PR creation.

No raw prompt text or final AI message appears in durable Sachima state. Business marker presence is verified host-side from out-of-repo runtime result files only.

---

## Pending

- Commit, push, PR creation, and CI.
