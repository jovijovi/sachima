# Runbook — agent-run-supervisor host-local read-only smoke (PR2)

Host-local, read-only smoke harness around the PR1 `AgentRunSupervisorPort`
adapter, plus a fail-closed real-supervisor readiness probe.

Module: `sachima_supervisor/runtime_spine/agent_run_supervisor_readonly_smoke.py`
Tests: `tests/sachima_supervisor/runtime_spine/test_agent_run_supervisor_readonly_smoke.py`

## What it is

Two surfaces, both pure local/offline Python — importing or running either starts
no real agent, process, network, durable service, delivery, or listener:

- `run_read_only_smoke(...) -> ReadOnlySmokeReport` — drives the **real** PR1
  adapter through a bounded, read-only, deterministic in-memory backend
  (`DefaultAgentRunSupervisorBackend` by default) over one deterministic fixture
  task. It binds exactly one read-only role/policy, a single-writer safe-cwd lease,
  and a deterministic artifact ref, runs one launch + one idempotent re-attach +
  cleanup, and returns a sanitized refs/counts/statuses-only report.
- `assess_read_only_smoke_readiness(request) -> ReadOnlySmokeReadinessReport` — a
  default-off, exact-token, default-deny gate for a *real* supervisor-backed smoke.
  It never launches; it reports `blocked` / `failed` / `ready`.

## What the smoke proves (refs-only, fail-closed)

- **One run / no duplicate launch** — a second `create_or_attach` with the same
  spec attaches to the same `SessionRef`; the backend holds exactly one session and
  the event log holds exactly one `agent_attached` event.
- **Sanitized artifact refs** — every ref in Sachima state is a safe id; the
  deterministic artifact ref (`ref_planning_report`) is present and sanitized.
- **No raw prompt / stdout / platform id in state or projection** — the fixture
  carries raw-material canaries that the harness never forwards; the whole
  event/projection state passes the R1 no-leak scan with those canaries seeded.
  Smuggling raw material as a launch ref fails closed with a stable code and no
  half-written state.
- **Cleanup / no orphan** — after `kill` the session is terminal (`cancelled`,
  never `orphaned`/reapable) and the safe-cwd lease is released.

## How to run (host-local, read-only)

Focused suite (Hermes-run; execution is approval-gated in governed worktrees):

```
python -m pytest tests/sachima_supervisor/runtime_spine/test_agent_run_supervisor_readonly_smoke.py -q
```

Runtime-spine regression:

```
python -m pytest tests/sachima_supervisor/runtime_spine -q
```

Programmatic evidence (no launch, no writes):

```python
from sachima_supervisor.runtime_spine import run_read_only_smoke
report = run_read_only_smoke()
assert report.status == "pass"
report.to_projection()   # sanitized, leak-scanned evidence
```

## Real supervisor-backed smoke: readiness gate

`assess_read_only_smoke_readiness` admits a real run only when **all** hold:
default-off flag flipped on with the exact PR2 approval token; no widened `allow_*`
scope; the read-only role bound; out-of-repo cwd/artifact roots; and a pinned local
runner (version `0_10_0` + local runner path + matching `sha256:` binary digest).
Absent/unpinned parameters →
`blocked`; present-but-invalid → `failed`. Raw host paths are digest-projected, so
reports never carry raw paths.

Under a controlled, local, default-deny host (no live durable service, no network,
no reachable external supervisor) the probe stays **blocked** until a caller supplies
a real local runner path whose bytes match the pinned digest, and records the
limitation on `ReadOnlySmokeReadinessReport.limitation`. This is intentional: the
harness proves fail-closed readiness gating, never a fabricated real smoke.

## Boundaries preserved

No Gateway restart/reload/replace; no IM/delivery API; no production-config writes;
no public webhook; no default-on behavior; no write-capable role; no Temporal
Worker/service startup; no raw prompt/stdout/platform-id leakage; no git push / PR
merge by the tested agent. The tested agent is read-only. Real-runner / IM /
platform / `temporalio` tokens are absent from the source (static boundary scan in
the focused suite).
