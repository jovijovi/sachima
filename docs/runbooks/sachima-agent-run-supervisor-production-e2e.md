# Runbook — agent-run-supervisor single-user production-shaped E2E (PR5)

A bounded, single-user, **default-off, local/offline** E2E proof that the merged
PR1–PR4 pieces compose safely behind a deterministic fixture. It is **not** a
production rollout: it starts no real agent/process/network/durable service, opens no
listener, touches no committed repo file, writes no production config, and calls no
Gateway/IM/delivery surface. Importing or exercising it starts nothing.

Module: `sachima_supervisor/runtime_spine/agent_run_supervisor_production_e2e.py`
Tests: `tests/sachima_supervisor/runtime_spine/test_agent_run_supervisor_production_e2e.py`

## What PR5 proves (refs-only, fail-closed)

`run_single_user_production_e2e(...)` drives the *real* PR1 `AgentRunSupervisorPort`
over the deterministic in-memory `DefaultAgentRunSupervisorBackend`, reusing the R1
`TaskRegistry`/projection helpers, the R4 `WorkspaceLeaseStore`, and the PR4
`build_agent_run_supervisor_workbench_view` — no logic is duplicated. Over one bounded
single-user fixture it proves, and records in a sanitized report:

- **one live session / no duplicate attach** — `create_or_attach` twice *and* a port
  reconstructed over the same registry + backend (a supervisor restart) return the
  same `SessionRef`; the backend holds one session and the log holds exactly one
  `agent_attached` event (`single_session`, `duplicate_attach_suppressed`).
- **optional permission path** — when the fixture asks, a deterministic
  `permission_wait` surfaces the operator-decision on the workbench view and a refs-only
  `signal` decision resumes the session (`permission_path_included`,
  `operator_decision_applied`); default fixtures skip it.
- **workbench renderable before cleanup** — the PR4 view builds and serializes through
  safe refs-only fields with `attach_count == 1` and no leak (`workbench_renderable`).
- **deterministic cleanup** — `kill` drives a terminal, orphan-free state (never
  `orphaned`/reapable) and the single-writer lease is released
  (`cleanup_terminal`, `orphan_free`, `lease_released`).
- **rollback-safe restart** — after cleanup a reconstructed port re-attaches to the
  already-terminal session with no respawn / no new event and no session/lease leak
  (`rollback_safe`).
- **no raw material in state** — the fixture seeds raw prompt / agent output / platform
  id canaries the E2E never forwards; the whole event/projection/view/stream state
  passes the R1 no-leak scan with those canaries seeded (`no_leak`).

The runner never fakes a pass: an invariant miss is a recorded `failed` report, and a
raising/mismatched backend, an unavailable lease, or a forged/unsafe fixture collapses
to a stable `blocked`/`failed` report with a stable code only — no half-written state
and no echoed material.

## Report — fail-closed, byte-stable, no-leak

`ProductionE2EReport` is a frozen, refs-only value object carrying only status / role /
task & session refs / booleans / counts / terminal-state / projected-status / artifact
refs / `checks` / stable `blockers` — never raw prompt/context/stdout/tool output/card
JSON/platform id/private path/secret. `__post_init__` re-runs the full fail-closed
allowlist and normalizes `checks`/`artifact_refs`/`blockers` to immutable tuples; a
`pass` with any blocker or missing safety flag, a non-`pass` with no blocker, an
operator decision without the permission path, or any forbidden marker fails closed with
the stable `e2e_invalid_report` code. `ProductionE2EFixture` likewise validates its
forwarded refs (exact type, safe-id allowlist, `ws_`/`policy_` prefixes) while carrying
the raw canaries separately (never forwarded, never leak-scanned as safe fields).
`validate_production_e2e_report` / `validate_production_e2e_fixture` re-validate at trust
boundaries against `object.__new__` forgery; `serialize_production_e2e_report` is
byte-stable and re-validates before emitting; `to_projection` is a never-raising
observable surface that falls back to a leak-safe shape.

## How to run (host-local, read-only; execution is approval-gated to Hermes)

```
python -m pytest tests/sachima_supervisor/runtime_spine/test_agent_run_supervisor_production_e2e.py -q
python -m pytest tests/sachima_supervisor/runtime_spine -q
```

Programmatic evidence (no launch, no writes, no real backend):

```python
from sachima_supervisor.runtime_spine import (
    ProductionE2EFixture, run_single_user_production_e2e,
    serialize_production_e2e_report,
)
report = run_single_user_production_e2e()                 # default deterministic fake
assert report.status == "pass", report.blockers
assert report.single_session and report.rollback_safe and report.no_leak
serialize_production_e2e_report(report)                   # byte-stable JSON evidence

# Optional deterministic operator-decision path:
run_single_user_production_e2e(fixture=ProductionE2EFixture(include_permission_wait=True))
```

## Boundaries preserved / explicit non-approvals

This proof does **not** authorize production上线, real external Sachima ingress, real or
production delivery, Gateway behavior/restart/reload, Temporal Worker/service/subprocess
startup, production config writes, public webhook exposure, default-on behavior,
write-capable agent roles, or real acpx/npx/Codex/Claude external AGENT processes. No
Gateway/IM/Feishu/delivery API is called; no live UI/IM delivery; no raw
prompt/stdout/platform-id/private-path leakage; no git push / PR merge by the tested
agent. Real-runtime / subprocess / socket / `temporalio` / Gateway / IM tokens remain
absent from the source (static boundary scan in the focused suite). CI / merge gates and
external review remain separate quality-control layers.
