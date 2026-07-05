# Runbook — agent-run-supervisor persistent session lifecycle (PR3)

Persistent session lifecycle hardening layered on the PR1 `AgentRunSupervisorPort`
adapter. Pure local/offline Python over the deterministic in-memory
`DefaultAgentRunSupervisorBackend`: importing or exercising it starts no real
agent, process, network, durable service, delivery, or listener, and touches no
Gateway/Temporal Worker.

Module: `sachima_supervisor/runtime_spine/agent_run_supervisor_port.py`
Tests: `tests/sachima_supervisor/runtime_spine/test_agent_run_supervisor_persistent_lifecycle.py`

## What PR3 adds (refs-only, fail-closed)

- **Persistent create/attach** — a port reconstructed over the **same**
  `TaskRegistry` + backend re-attaches an existing session (running or
  `permission_wait`) with **no duplicate `agent_attached`** event and the same
  `SessionRef`. Reconstruction over a **fresh/missing** backend fails closed
  (`runtime_invalid_session`) and never respawns. A `task_id` keeps ≤1 live session.
- **Stream cursor / resume** — `stream(ref, since_seq=<last-seen seq>)` returns only
  events with `seq > since_seq`, so a caller resumes exactly the tail it has not seen
  with **no duplicate replay**. A lifecycle re-attach appends no events, so resuming
  from the pre-attach `last_seq` yields nothing.
- **Lifecycle snapshot** — `lifecycle_snapshot(ref) -> LifecycleSnapshot` reads
  **persisted Sachima state only** (Status Projection + log; no backend call, no
  mutation) and exposes refs-only safe resume data: `last_seq` (the cursor),
  `event_count` (== `last_seq` for a gap-free 1..N log), and `attach_count`
  (`agent_attached` count, which stays `1` across a re-attach). `to_projection()` is
  deterministic and leak-scanned.
- **close / cleanup** — `close(ref) -> LifecycleSnapshot` is an **adapter-local,
  default-off** port handoff: it drops *this* port's in-memory tracking only —
  killing no backend session, appending no event, mutating no registry state — so a
  reconstructed port re-attaches the still-live session. It is never invoked
  automatically and fails closed on an untracked/forged ref (no resurrection).

## Status / liveness backend read-failure policy (Codex WATCH, now explicit)

A **later** `status` / `liveness` backend read failure on an existing session
collapses to the stable `runtime_supervisor_backend_failure` code **before anything
is appended** and never marks, kills, orphans, or otherwise mutates that persisted
session/log — it is a transient read fault, and a subsequent successful read resumes
the preserved session. An `orphaned` backend state is surfaced as `reapable` via
`liveness` but is deliberately **not** auto-written as a terminal event into the
canonical log; that reap decision belongs to a reaper. `lifecycle_snapshot` makes no
backend call, so it stays a stable resume-data read even while the backend is
unreachable.

## Lease / task binding

Persistent re-attach preserves the read-only role and the workspace/policy refs
binding: a reconstructed port that supplies a drifted workspace ref fails closed
(`runtime_invalid_launch_spec`) and a drifted/extra role fails closed
(`runtime_supervisor_policy_denied`), both **before** any backend attach and with the
existing session untouched. No role or workspace drift can attach to an existing
session.

## How to run (host-local, read-only; execution is approval-gated to Hermes)

```
python -m pytest tests/sachima_supervisor/runtime_spine/test_agent_run_supervisor_persistent_lifecycle.py -q
python -m pytest tests/sachima_supervisor/runtime_spine -q
```

Programmatic evidence (no launch, no writes):

```python
from sachima_supervisor.runtime_spine import (
    AgentRunSupervisorPort, DefaultAgentRunSupervisorBackend, TaskRegistry, build_launch_spec,
)
reg, backend = TaskRegistry(), DefaultAgentRunSupervisorBackend()
spec = build_launch_spec(task_id="task_alpha", agent_kind="local_agent",
                         mode_flags={"needs_agent": True}, roles=("read_only",),
                         refs=("ws_alpha", "policy_default"))
first = AgentRunSupervisorPort(reg, backend)
ref = first.create_or_attach("task_alpha", spec)
# Reconstruct over the same registry + backend → re-attach, no duplicate event.
second = AgentRunSupervisorPort(reg, backend)
ref2 = second.create_or_attach("task_alpha", spec)
assert ref2 == ref
snap = second.lifecycle_snapshot(ref2)
assert snap.attach_count == 1                 # no duplicate attach replay
snap.to_projection()                          # refs-only, leak-scanned evidence
```

## Boundaries preserved

No Gateway restart/reload/replace; no IM/Feishu/delivery API; no production-config
writes; no public webhook; no default-on behavior; no write-capable role; no Temporal
Worker/service startup; no real external AGENT process (adapter lifecycle semantics
only); no raw prompt/stdout/platform-id/private-path leakage; no git push / PR merge
by the tested agent. `close` stays adapter-local and default-off. Real-runtime /
subprocess / socket / `temporalio` / Gateway / IM tokens remain absent from the source
(static boundary scan in the focused suite).
