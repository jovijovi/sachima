# Sachima AgentRunSupervisorPort Adapter Runbook

## Scope

This runbook covers the PR1 Sachima-side `AgentRunSupervisorPort` adapter. The
adapter implements the runtime-spine `ExecutionPort` contract over an injected
agent-run-supervisor-shaped backend surface.

## Approved boundary

- Default backend is a deterministic in-memory fake.
- Importing or constructing the adapter starts no OS process, agent runtime,
  Gateway, Temporal Worker/service, public webhook, Feishu/IM delivery, or
  network client.
- The adapter is default-off unless a caller explicitly instantiates it with a
  `TaskRegistry` and optional backend.
- Backend failures collapse to stable port-side codes only:
  - `runtime_supervisor_backend_failure`
  - `runtime_supervisor_policy_denied`
- Runtime-spine events remain refs-only; raw prompts, logs, stdout/stderr,
  platform IDs, and private paths must not enter the event log or projection.

## Policy gate

`create_or_attach()` fails closed before any backend call unless the launch spec:

1. is an exact `LaunchSpec`;
2. matches the requested `task_id`;
3. has `needs_agent=True`;
4. has exactly one role: `read_only`;
5. contains at least one workspace ref (`ws_*`) and one policy ref (`policy_*`).

No write-capable role is accepted. `signal()` never creates a session; it only
answers an existing `permission_wait` session with a decision ref.

## Verification

Run from the Sachima worktree:

```bash
scripts/run_tests.sh tests/sachima_supervisor/runtime_spine/test_agent_run_supervisor_port.py -- -q
scripts/run_tests.sh tests/sachima_supervisor/runtime_spine/test_execution_port.py tests/sachima_supervisor/runtime_spine/test_fake_supervisor_port.py -- -q
python3 -m compileall -q sachima_supervisor/runtime_spine tests/sachima_supervisor/runtime_spine
git diff --check
```

Forbidden-surface review for this PR must classify changed source/docs/tests for
Gateway restart/reload/replace, real IM/Feishu delivery, production config
writes, public webhook exposure, default-on behavior, write-capable roles,
Temporal Worker/service startup, raw prompt/stdout/platform-ID leakage, and any
git push/PR merge performed by the tested AGENT. None are allowed in PR1.
