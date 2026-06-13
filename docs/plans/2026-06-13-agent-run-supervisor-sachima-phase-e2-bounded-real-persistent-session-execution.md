# Phase E-2 — Bounded Real Persistent-Session Execution (local/offline)

Date: 2026-06-13
Base branch: `release/sachima` (at `83db916e494a40d4511098a217806f23eea45931`)
Branch: `feature/phase-e2-bounded-real-session-execution`
Status: `implemented_real_smoke_and_codex_review_passed_pr_pending` (NOT committed, NOT merged)

## Approval

User-approved scope (exact):

> 批准 Phase E-2 bounded real persistent-session execution，本地/离线实现与一次最小真实 session smoke；不批准 Gateway/Feishu/live/production config/real delivery。

Approval token (exact, distinct from the Phase E lifecycle token):

```text
approve_agent_run_supervisor_sachima_phase_e2_bounded_real_persistent_session_execution_local_offline_smoke_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

## Goal

Wire the **existing** Phase E persistent-session lifecycle state machine
(`sachima_supervisor.activity_session_lifecycle`, merged in PR #125) to a *real*
`agent_run_supervisor.session_runtime.SessionRuntime` for a **bounded** local
lifecycle — open a persistent session, run one read-only turn, close it — while
keeping the committed source default-off, fail-closed, and CI-safe.

This is the smallest real-execution increment after the injected-fakes-only
lifecycle slice. It does not introduce any new lifecycle semantics: durability,
idempotency, leases, lock ordering, and the failure taxonomy all stay owned by
the merged state machine. This slice only supplies the injected work callables
and a fail-closed config gate around the real runtime, plus one minimal real
smoke path.

## In scope (approved)

- A new Sachima-owned bridge module
  `sachima_supervisor/activity_session_real_execution.py` that:
  - defines the exact Phase E-2 approval token and is **default-off**;
  - performs fail-closed config validation (gate token, role JSON path + digest,
    `session.strategy == persistent`, runner `type==acpx` / `acpx_version==0.10.0`
    / `adapter_agent==codex`, non-null absolute local `acpx_binary` whose basename
    is not a launcher, optional acpx sha256 match, caller-owned runtime/evidence/
    work dirs outside the tracked repo, no Gateway/Feishu/delivery surface markers);
  - lazily imports `agent_run_supervisor` only inside the default runtime backend
    so importing the module — and validating a config — is CI-safe without the
    external package installed;
  - exposes `open_real_persistent_session` / `run_real_persistent_session_turn` /
    `close_real_persistent_session`, `best_effort_close_real_session`, and the
    `bind_open_session` / `bind_run_turn` / `bind_close_session` adapters that
    produce the single-arg work callables the state machine consumes;
  - maps runtime outcomes to the state machine's `SessionWorkOutcome` carrying
    only stable codes, an opaque derived `session_binding` (a hash of the
    runtime/acpx session id), safe evidence refs/digests, and counts — never the
    final message, raw prompt/context, tool output, or raw exception text.
- A committed portable persistent role
  `sachima_supervisor/roles/session_worker_persistent_v1.json`
  (`acpx_binary: null`, `session.strategy: persistent`, read/search only,
  `allowed_roots_security_boundary: false`) — non-runnable by construction until
  an operator local overlay pins a verified local acpx.
- A reproducible smoke script
  `scripts/sachima_phase_e2_persistent_session_smoke.py` that drives exactly one
  `create -> send(one read-only turn) -> close` lifecycle, emits a compact JSON
  summary (execution-pipeline + business-task layers), and performs host-side
  post-verify (exactly one supervisor session, one turn, supervisor session.json
  closed state, exact business marker match from the external turn result, no
  npx/launcher runner, no forbidden surface). It has a `--self-test` mode that
  exercises the identical wiring with an in-process fake backend (no acpx, no
  `agent_run_supervisor`).
- Tests in `tests/sachima_supervisor/test_activity_session_real_execution.py`.

## Out of scope (explicitly NOT approved)

Cancellation **execution** (request-state only stays in the state machine;
`execute_real_cancellation` always fails closed with
`activity_cancel_not_approved`), Gateway, Feishu, IM delivery, live/default-on
behavior, public ingress, production config writes, service restart/reload,
platform adapter mutation, npx/npm/pnpm/yarn/bunx/shell runnable fallback, and
any real delivery.

## Cancellation

Not approved in this slice. Cancellation stays request-state only in
`activity_session_lifecycle.request_cancellation`. The bridge provides
`execute_real_cancellation`, which refuses unconditionally (before any runtime
load) with `activity_cancel_not_approved`.

## Runner pinning

`runner.acpx_binary` must be a non-null absolute local path whose basename is not
a launcher (`npx`/`npm`/`pnpm`/`yarn`/`bunx`/`bun`/`node`/`deno`/`sh`/`bash`/…).
The committed role keeps `acpx_binary: null`, so it is non-runnable by
construction. An operator local overlay (never committed) pins a verified local
acpx 0.10.0 executable; an optional `acpx_sha256` is checked when supplied. There
is no npx/network fallback path in source.

## Verification

- `uv run --extra dev python -m pytest tests/sachima_supervisor/test_activity_session_real_execution.py -q --tb=short`
- `uv run --extra dev python -m pytest tests/sachima_supervisor/test_activity_session_lifecycle.py -q --tb=short`
- `uv run --extra dev python -m pytest tests/sachima_supervisor -q --tb=short`
- `uv run --extra dev python -m compileall -q sachima_supervisor tests/sachima_supervisor scripts/sachima_phase_e2_persistent_session_smoke.py`
- `git diff --check`
- `codegraph sync && codegraph status`
- Smoke self-test: `uv run python scripts/sachima_phase_e2_persistent_session_smoke.py --self-test --sessions-dir <tmp>/sessions --evidence-dir <tmp>/evidence --work-dir <tmp>/work`

The single minimal **real** smoke was run by Hermes with a pinned local acpx
0.10.0 binary and local `agent_run_supervisor` source import. Evidence is outside
the repo under
`/data/agents/workspace/hermes/outputs/sachima/phase-e2-bounded-real-persistent-session-execution/20260613T063219Z/`.
It passed: create -> session_open, one turn -> completed, close ->
session_closed, supervisor session.json -> closed, exactly one supervisor session
and one supervisor turn, business marker verified, `final_message_persisted=false`,
no npx launcher, and all non-approvals held.

## Non-approval preservation

All prior non-approvals from the Phase E lifecycle slice and earlier remain in
force. This slice adds bounded real persistent-session execution and one minimal
real smoke path only.
