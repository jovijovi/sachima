# Runbook — agent-run-supervisor StatusProjection + task workbench view (PR4)

A deterministic, read-only workbench view layered on the PR1 `AgentRunSupervisorPort`
adapter and the PR3 persistent-lifecycle facts. Pure local/offline Python over the
deterministic in-memory `DefaultAgentRunSupervisorBackend`: importing or exercising
it starts no real agent, process, network, durable service, delivery, or listener,
and touches no Gateway/Temporal Worker. It adds **no** live UI/IM delivery — only the
safe refs-only surface a future Hermes/IM task workbench could render.

Module: `sachima_supervisor/runtime_spine/agent_run_supervisor_workbench.py`
Tests: `tests/sachima_supervisor/runtime_spine/test_agent_run_supervisor_workbench_view.py`

## What PR4 adds (refs-only, fail-closed)

- **Composition** — `build_agent_run_supervisor_workbench_view(registry, port, ref)`
  composes the R1 `TaskViewModel` Status Projection surface with the PR3
  `LifecycleSnapshot` persistent-lifecycle facts for one **locally tracked** session,
  reusing `build_task_view_model` and `AgentRunSupervisorPort.lifecycle_snapshot`
  (no duplicated event/projection logic). The `ref` is the trust anchor; the two
  sources are composed only if they agree.
- **Safe fields** — `AgentRunSupervisorWorkbenchView` is a frozen, byte-stably
  serializable dataclass carrying only: `task_id`, `session_id`, `status`,
  `terminal`, `alive`, `resumable`, `reapable`, `permission_state`,
  `requires_operator_decision`, `flags`, `refs`, `surfaces`, `resume_cursor`,
  `last_seq`, `event_count`, `attach_count`, and the stable `error_code`. No raw
  prompt/context/stdout/tool output/card JSON/platform id/private path/secret.
- **Permission wait** — a `permission_wait` task surfaces the `permission` surface
  and `requires_operator_decision=True` and stays `alive`/`resumable` — it is never
  auto-written terminal.
- **Resume determinism** — `resume_cursor == last_seq == event_count`, `attach_count`
  stays `1` across a lifecycle re-attach or a `close` + reconstruct, so no duplicate
  attach is ever shown. Building/serializing the view appends no event and makes no
  backend call, so it is a stable read even while the injected backend is unreachable.
- **Orphan / reapable (PR3 policy preserved)** — an optional, already-obtained
  `LivenessState` may be passed to surface `reapable`. An `orphaned` backend health
  signal is shown only as a `reapable` hint over the still-non-terminal projected
  lifecycle and is **never** auto-written as a terminal event into the canonical log;
  the default build supplies no liveness and fabricates no health signal.

## Fail-closed / no-leak boundary

An untracked/forged ref fails closed inside `lifecycle_snapshot` with the stable PR3
`runtime_invalid_session` code rather than fabricating state, and never echoes the
bad material. A directly-constructed, `object.__new__`-forged, or mutated view — or a
registry/port mismatch, a mismatched liveness, or any forbidden marker in a ref —
fails closed with the stable `runtime_invalid_workbench_view` code. `as_dict` and
`serialize_agent_run_supervisor_workbench_view` re-validate before emitting, so a
mutated forgery can never be serialized.

## How to run (host-local, read-only; execution is approval-gated to Hermes)

```
python -m pytest tests/sachima_supervisor/runtime_spine/test_agent_run_supervisor_workbench_view.py -q
python -m pytest tests/sachima_supervisor/runtime_spine -q
```

Programmatic evidence (no launch, no writes, no backend call):

```python
from sachima_supervisor.runtime_spine import (
    AgentRunSupervisorPort, DefaultAgentRunSupervisorBackend, TaskRegistry,
    build_agent_run_supervisor_workbench_view, build_launch_spec,
    serialize_agent_run_supervisor_workbench_view,
)
reg, backend = TaskRegistry(), DefaultAgentRunSupervisorBackend()
spec = build_launch_spec(task_id="task_alpha", agent_kind="local_agent",
                         mode_flags={"needs_agent": True}, roles=("read_only",),
                         refs=("ws_alpha", "policy_default"))
port = AgentRunSupervisorPort(reg, backend)
ref = port.create_or_attach("task_alpha", spec)
view = build_agent_run_supervisor_workbench_view(reg, port, ref)
view.as_dict()                                        # refs-only, leak-scanned
serialize_agent_run_supervisor_workbench_view(view)   # byte-stable JSON evidence
assert view.as_dict()["attach_count"] == 1            # no duplicate attach
```

## Boundaries preserved

No Gateway restart/reload/replace; no IM/Feishu/delivery API; no live UI/IM delivery;
no production-config writes; no public webhook; no default-on behavior; no
write-capable role; no Temporal Worker/service startup; no real external AGENT
process; no raw prompt/stdout/platform-id/private-path leakage; no git push / PR merge
by the tested agent. Building/serializing the view is read-only — it appends no event,
launches no work, and makes no backend/delivery call. Real-runtime / subprocess /
socket / `temporalio` / Gateway / IM tokens remain absent from the source (static
boundary scan in the focused suite).
