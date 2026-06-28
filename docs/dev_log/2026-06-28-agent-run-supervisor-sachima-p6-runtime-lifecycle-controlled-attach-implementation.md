# Dev log — P6 runtime lifecycle / controlled attach implementation

Status: In progress; local focused, relevant, full supervisor-suite, ruff, compile, diff, status, forbidden-surface, and stale scans passed; Codex review, PR, CI, and merge pending.

## Approval boundary

The implementation is authorized by the exact token:

```text
approve_agent_run_supervisor_sachima_p6_runtime_lifecycle_controlled_attach_implementation_default_off_caller_owned_attach_only_no_runtime_or_worker_start_no_additional_real_agent_execution_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

## Work performed

- Created branch `feat/p6-runtime-controlled-attach` from clean `release/sachima`.
- Synced CodeGraph for the worktree.
- Inspected P5/P6/P6-B seams:
  - `sachima_supervisor/p5_temporal/control_surface.py`
  - `sachima_supervisor/p5_temporal/runtime_client.py`
  - `sachima_supervisor/p5_temporal/step_executor.py`
  - `sachima_supervisor/p6_controlled_ai_flow.py`
  - `sachima_supervisor/ai_flow_executor.py`
  - PR #183 technical solution
- Added RED tests for attach admission, unsafe material, no-attach fail-closed behavior, duplicate start idempotency, no-relaunch recover, active-run cancellation WATCH preservation, close/detach, and public package exports.
- Implemented `sachima_supervisor/p6_runtime_attach.py` as a default-off caller-owned attach shell over an already supplied P6 session.
- Exported public API from `sachima_supervisor.__init__`.
- Added extra RED safety tests for unsafe health-probe material and raw control identifiers; fixed both before broader verification.

## Verification completed so far

```text
uv run --with pytest python -m pytest tests/sachima_supervisor/p6_runtime_attach/unit/test_runtime_attach.py -q
# 22 passed

uv run --with pytest python -m pytest   tests/sachima_supervisor/p6_runtime_attach/unit/test_runtime_attach.py   tests/sachima_supervisor/p6_controlled_ai_flow/unit/test_admission.py   tests/sachima_supervisor/p6_controlled_ai_flow/unit/test_control_path.py   tests/sachima_supervisor/p6_controlled_ai_flow/unit/test_composition_oracle.py   tests/sachima_supervisor/p6_controlled_ai_flow/unit/test_no_weakening.py   tests/sachima_supervisor/p6_controlled_ai_flow/unit/test_translation_reuse.py   -q
# 49 passed
```

## Completed gates

- focused runtime attach tests: 22 passed
- focused runtime attach + P6 control regression: 49 passed
- full `tests/sachima_supervisor`: 1045 passed
- ruff: passed
- compileall: passed
- `git diff --check`: passed
- `tools/sync_roadmap_status.py --check --base-remote sachima`: passed
- forbidden-surface/static scans: passed
- CodeGraph impact snapshot: captured

## Pending gates

- Codex exact-head blocker review
- PR and GitHub CI

## Boundary confirmation

No runtime, Worker, service, subprocess, socket, acpx, npx, real agent, Gateway, Feishu, IM, live/default-on, production config, platform adapter, public ingress, or delivery surface was started or invoked.


## Codex blocker fixes applied

Committed-head read-only Codex reviews returned blocker findings during hardening. The branch fixed all blockers before final review:

1. `start()` now records the idempotency fingerprint before delegation so a lost response after launch cannot cause duplicate relaunch on retry.
2. `attach()` now rejects broader real-runner-like/P6-B/acpx/npx/Codex/Claude executor surfaces and only accepts the approved P5 local/offline fake/injected executor token for this first slice.
3. `start()` now safe-ref validates run, step, digest, idempotency, and terminal-gate material before any P6 delegation.
4. Downstream `error_code` / `admission_code` values are now collapsed to stable, no-leak codes before appearing on public attach outcomes.
5. Duplicate-start claim check/set is protected by an in-process lock, with a concurrent identical-start regression proving only one launch.
6. Executor binding now positively requires a wrapped `P5LocalOfflineRuntimeAdapter`, so merely spoofing the local/offline approval token is rejected.
7. Unsafe downstream error codes now force a rejected attach outcome even if the delegate claims `ok=True`.
8. Attach state/result snapshots are deep-copied and re-scanned on read so caller mutation cannot poison internal sanitized state.
9. Start fingerprints now include all dataclass fields, including gate, lease, epoch, and state-version material; approval tokens are fingerprinted by digest, not raw text.
10. No-relaunch claim state can be caller-owned via an injected mapping, preserving duplicate-start protection across attach wrapper recreation without file/network writes.

Regression coverage added for all blocker fixes.
