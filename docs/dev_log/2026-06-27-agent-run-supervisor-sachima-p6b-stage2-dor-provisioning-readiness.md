# Dev log — P6-B Stage-2 DoR provisioning/readiness packet

Date: 2026-06-27
Branch: `docs/p6b-stage2-dor-provisioning`
Status: Docs/status packet in progress. No real smoke, no real agent, no `acpx` invocation.

## Scope binding

The user approved starting the recommended next step after PR #177: a small P6-B Stage-2 DoR provisioning/readiness PR before any real-smoke request.

Hermes interpreted this as a docs/status-only gate: fix the exact future DoR validation command, role overlay, evidence sink/root, and crash/recovery/no-relaunch rules. It does not authorize installing `acpx`, invoking `acpx`, running a real agent step, real smoke, write roles, Gateway/Feishu/live behavior, production config writes, service restarts, or real delivery.

## Preflight evidence

- `release/sachima` local head matched `sachima/release/sachima`.
- Open PR list was empty.
- `acpx` was not found on PATH.
- `codex` and `claude` CLIs were present, but they are not sufficient for P6-B because the DoR requires a pinned local `acpx@0.10.0` binary and out-of-repo role overlay.
- Worktree created at `worktrees/sachima/p6b-stage2-dor-provisioning` from `sachima/release/sachima` head `3c4dcca4c17a87435b9404de60a663097bbbb28a`.
- CodeGraph was not indexed for this worktree; Hermes used direct source/doc inspection and did not initialize a new index.

## Authority inspected

- `GOAL.md`
- `AGENTS.md`
- `docs/roadmap/current-status.md`
- `docs/roadmap/tail-register.md`
- `docs/roadmap/boundary-register.md`
- P6-B Stage-2 readiness packet and technical solution
- PR #175 host-local DoR proof manifest and dev log
- `sachima_supervisor/p6b_host_local_dor.py`
- `tools/p6b_host_local_dor.py`
- `sachima_supervisor/p6b_read_only_real_agent.py`
- committed null-binary read-only role configs

## Blocked DoR evidence run

Hermes ran the existing DoR CLI with no runner params and an out-of-repo evidence root. This is an assessment/proof command only; it did not invoke `acpx`, `npx`, Codex, Claude, or a real agent step.

Result:

```text
status: blocked
runner_pinning_status: blocked
crash_proof_status: pass
blockers: [p6b_dor_runner_params_missing]
query_state: not_found
recover_state: not_found
recovery_marker: reattached_no_relaunch
supervisor_launch_count: 0
execute_after_store_loss: not_approved_not_attempted
```

Evidence reference class: `p6b-stage2-dor-provisioning-readiness/20260627T093824Z/`.

## Decision recorded by this branch

At authoring time, this branch recorded that the next safe operational step was not real smoke. It was either:

1. Option-A durable cross-process claim-store implementation; or
2. Option-B operator-supplied pinned `acpx@0.10.0` + out-of-repo read-only role overlay + artifact sink + evidence root, followed by `tools/p6b_host_local_dor.py --probe` as DoR validation only.

Post-PR #179 status: Option A is now closed by the durable controlled-exec claim-store implementation. The remaining next safe gate is Option B host-local DoR validation only, still with no real agent step launch and no real smoke.

## Non-approvals preserved

No source implementation, no test code change, no `acpx` install/fetch, no real `acpx`/`npx`/agent invocation, no real smoke, no write roles, no file/git mutation by an agent step, no network by the agent step, no Gateway/Feishu/IM/live/public ingress, no production config, no service restart, no real delivery, no broader controlled AI FLOW expansion, and no clean active-run cancellation claim.
