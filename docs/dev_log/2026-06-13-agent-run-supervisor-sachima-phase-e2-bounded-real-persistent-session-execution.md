# Dev Log — Phase E-2 Bounded Real Persistent-Session Execution

Date: 2026-06-13
Branch: `feature/phase-e2-bounded-real-session-execution`
Base: `release/sachima` at `83db916e494a40d4511098a217806f23eea45931`
Worktree: `/data/agents/workspace/hermes/worktrees/sachima/phase-e2-bounded-real-session-execution`
Status: implemented and merged in PR #127 (merge commit `813c0eb051efd822d214b2cd8619b8a941536abb`); real smoke PASS; Codex blocker-only re-review PASS / BLOCKERS None.

## Boundary

Approved (exact): "批准 Phase E-2 bounded real persistent-session execution，本地/离线实现与一次最小真实 session smoke；不批准 Gateway/Feishu/live/production config/real delivery。"

This slice connects the merged Phase E lifecycle state machine to a real
`agent_run_supervisor.session_runtime.SessionRuntime` for a **bounded** local
lifecycle (create / one read-only turn / close) and adds one minimal real smoke
path. It holds all prior non-approvals:

- no cancellation execution (request-state only stays in the state machine);
- pinned local acpx only — no npx/npm/pnpm/yarn/bunx/shell runnable fallback in source;
- no Gateway, Feishu, IM delivery, live/default-on behavior, public ingress, production config write, service restart, platform adapter mutation, or real delivery.

Agent split for this branch: Hermes is PM/controller/verifier/repo operator;
Claude Code is main programmer + documentation engineer; Codex CLI is the
primary reviewer later. Claude Code did not commit, push, open a PR, merge,
restart services, write production config, or touch Gateway/Feishu/live/ingress.

## Design

The merged Phase E state machine (`activity_session_lifecycle`) already owns
durability, idempotency, leases, lock ordering, the lifecycle FSM, and the
failure taxonomy. Its work-starting operations take an **injected work
callable** (`open_session` / `run_turn` / `apply_close`) and finalize the
outcome under a CAS. Phase E-2 therefore does not add lifecycle semantics — it
supplies real work callables plus a fail-closed config gate around the real
runtime.

New module `sachima_supervisor/activity_session_real_execution.py`:

- `PHASE_E2_REAL_SESSION_APPROVAL_TOKEN` — exact, distinct from the lifecycle token.
- `RealPersistentSessionConfig` — caller-owned config (gate, role file + expected
  digest, sessions/evidence/work dirs, runtime session id/name, optional acpx
  sha256, repo-path escape hatch for tests).
- `validate_real_session_config` — stdlib-only, fail-closed validation:
  enabled+token, role file readable + digest match, no forbidden delivery/live
  surface markers in the role, `session.strategy == persistent`, runner
  `type==acpx` / `acpx_version==0.10.0` / `adapter_agent==codex`, non-null
  absolute local `acpx_binary` with a non-launcher basename, optional acpx sha256
  match, and caller-owned runtime/evidence/work dirs that live outside the
  tracked repo. It imports nothing from `agent_run_supervisor`.
- `_AgentRunSupervisorBackend` — the only place `agent_run_supervisor` is
  imported, and only lazily inside its methods. It builds a `SessionRuntime` and
  `load_role`, runs create/send/close, and returns *neutral* result shapes
  (`_RuntimeCreateResult` / `_RuntimeTurnResult` / `_RuntimeCloseResult`) that by
  construction cannot carry a final message, raw prompt, or tool output.
- `open_real_persistent_session` / `run_real_persistent_session_turn` /
  `close_real_persistent_session` — gate first (raise on misconfig), then call
  the backend, then map to the state machine's `SessionWorkOutcome`. The
  `session_binding` is an opaque `sbind_<hash>` derived from the runtime/acpx
  session id; evidence is safe refs + sha256 digests + counts only. A create-time
  backend failure triggers a best-effort close to avoid leaking a real session,
  then maps to a sanitized `ok=False` outcome.
- `best_effort_close_real_session` — leak guard for the smoke `finally` (gate
  enforced, then swallows close errors).
- `execute_real_cancellation` — always fails closed with
  `activity_cancel_not_approved`, before any runtime load.
- `bind_open_session` / `bind_run_turn` / `bind_close_session` — produce the
  single-arg work callables the state machine consumes.

Committed role `sachima_supervisor/roles/session_worker_persistent_v1.json`:
portable, read-only, `session.strategy: persistent`, `acpx_binary: null`,
`allowed_roots_security_boundary: false`. Non-runnable by construction; an
operator local overlay must pin a verified local acpx before any real smoke.

Smoke `scripts/sachima_phase_e2_persistent_session_smoke.py`: drives exactly one
`create -> send(one read-only turn) -> close` through the state machine + bridge,
emits a compact JSON summary (execution-pipeline + business-task layers), and
host-side post-verifies (closed state, one turn, exactly one supervisor session,
one supervisor turn dir, no npx/launcher runner, and in real mode the turn
artifact's final message must exactly match the smoke marker without persisting
that final message into Sachima durable state). `--self-test` runs the
identical wiring with an in-process fake backend (no acpx, no
`agent_run_supervisor`); real mode requires `--acpx-binary` and an importable
`agent_run_supervisor`.

## TDD notes

Tests were written first and confirmed RED (module missing) before
implementation. One ordering hazard surfaced and was fixed in the tests, not the
module: an early `importlib.reload` of the bridge mutated the module globals so
its functions raised a *new* `RealSessionExecutionError` class that the
test-file's imported class no longer matched — the import-safety test now uses a
clean subprocess check instead. Two further test-expectation fixes: the
committed role description originally contained the literal words
"Gateway/Feishu/webhook/ingress", which the module's own forbidden-surface
scanner correctly rejected (reworded the role to be surface-clean so the
null-binary path is what fails it); and the double-close test had no `send`, so
the close requests must expect `state_version == 1`.

## Local verification (all in this worktree)

```text
uv run --extra dev python -m pytest tests/sachima_supervisor/test_activity_session_real_execution.py -q --tb=short
44 passed

uv run --extra dev python -m pytest tests/sachima_supervisor/test_activity_session_lifecycle.py -q --tb=short
106 passed

uv run --extra dev python -m pytest tests/sachima_supervisor -q --tb=short
475 passed

uv run --extra dev python -m compileall -q sachima_supervisor tests/sachima_supervisor scripts/sachima_phase_e2_persistent_session_smoke.py
(clean)

git diff --check
(clean)

uv run python scripts/sachima_phase_e2_persistent_session_smoke.py --self-test \
  --sessions-dir /tmp/e2smoke/sessions --evidence-dir /tmp/e2smoke/evidence --work-dir /tmp/e2smoke/work
ok=true; create -> session_open; turn -> completed (final_message_persisted=false); close -> session_closed;
post_verify: closed=true, turn_count_state_machine=1, npx_in_runner=false
```

CodeGraph: `codegraph sync && codegraph status` to be (re)run by Hermes after
files settle.

## Real smoke status

Run by Hermes after host-local provisioning, with pinned local `acpx` 0.10.0 and
local `agent_run_supervisor` source imported via `PYTHONPATH`.

Evidence root:

```text
/data/agents/workspace/hermes/outputs/sachima/phase-e2-bounded-real-persistent-session-execution/20260613T063219Z/
```

Evidence files:

- `summary.json`
- `final_validation.json`
- `sessions/phase_e2_smoke_20260613T063219Z/session.json`
- `sessions/phase_e2_smoke_20260613T063219Z/turns/<turn>/result.json`
- `evidence/role.resolved.json`

Result: PASS.

Key invariants:

- `ok=true`, `mode=real`
- create -> `session_open`
- one turn -> `completed`
- close -> `session_closed`
- external supervisor `session.json.state == closed`
- exactly one supervisor session and one supervisor turn
- business marker verified: `SACHIMA_PHASE_E2_TURN_OK`
- Sachima durable state kept `final_message_persisted=false`
- runner basename `acpx`; `npx_in_runner=false`
- non-approvals held: no cancellation execution, no Gateway, no Feishu/IM delivery,
  no live/default-on, no production config write, no real delivery

## Next steps (operator / Hermes)

1. Commit / push / PR are operator decisions.
2. Merge remains a separate owner decision after PR/CI.
