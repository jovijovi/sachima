# P6 runtime lifecycle / controlled attach implementation

Status: Candidate implementation branch; local focused, relevant, full supervisor-suite, ruff, compile, diff, status, forbidden-surface, and stale scans passed; Codex review, PR, CI, and merge pending.

## Scope

This implementation adds the first code-bearing P6 runtime lifecycle / controlled attach slice after the merged docs-only plan in PR #183.

Approved implementation token:

```text
approve_agent_run_supervisor_sachima_p6_runtime_lifecycle_controlled_attach_implementation_default_off_caller_owned_attach_only_no_runtime_or_worker_start_no_additional_real_agent_execution_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

## Strongest meaning

The branch adds a default-off, caller-owned attach/control shell over an already supplied P6 session:

- `RuntimeAttachRequest`
- `P6RuntimeAttachOutcome`
- `P6RuntimeAttachSession`
- public package exports from `sachima_supervisor.__init__`

The shell can attach to a caller-supplied P6 control surface, expose sanitized attach state, and gate `start`, `query`, `recover`, `cancel`, and `close` calls. It does not own or start the runtime.

## Explicit non-goals

This branch does not approve or perform:

```text
runtime or Worker start
Temporal service start
service restart
subprocess/socket/acpx/npx launch
additional real agent execution
write roles
Gateway / Feishu / IM / live / default-on behavior
public ingress
production config write
platform adapter mutation
real delivery
broader real controlled AI FLOW execution
```

## Implementation surface

```text
sachima_supervisor/p6_runtime_attach.py
tests/sachima_supervisor/p6_runtime_attach/unit/test_runtime_attach.py
sachima_supervisor/__init__.py
```

## Behavior gates

The implementation is intentionally narrow:

1. Disabled, approval-mismatch, and operator-gate-blocked attach requests fail closed and make zero executor calls.
2. Unsafe attach material, unsafe health probe material, and raw control identifiers fail closed without echoing raw input.
3. `query`, `recover`, `cancel`, and `close` are rejected before attach.
4. `start` delegates only after attach.
5. Duplicate identical `start` returns a no-relaunch recovery projection and does not execute steps again.
6. Divergent duplicate `start` fails closed before executor calls.
7. `recover` is read-only and never relaunches.
8. WP3b active-run cancellation WATCH is preserved through the attach shell.
9. `close(detach=True)` detaches local attach state without adding runtime disconnect or delivery semantics.

## Verification so far

Local focused verification completed on this branch; after Codex blocker fixes the focused runtime attach suite is 15 tests:

```text
uv run --with pytest python -m pytest tests/sachima_supervisor/p6_runtime_attach/unit/test_runtime_attach.py -q
# 22 passed

uv run --with pytest python -m pytest   tests/sachima_supervisor/p6_runtime_attach/unit/test_runtime_attach.py   tests/sachima_supervisor/p6_controlled_ai_flow/unit/test_admission.py   tests/sachima_supervisor/p6_controlled_ai_flow/unit/test_control_path.py   tests/sachima_supervisor/p6_controlled_ai_flow/unit/test_composition_oracle.py   tests/sachima_supervisor/p6_controlled_ai_flow/unit/test_no_weakening.py   tests/sachima_supervisor/p6_controlled_ai_flow/unit/test_translation_reuse.py   -q
# 49 passed
```

Completed before review:

- full `tests/sachima_supervisor` suite: 1045 passed
- ruff: passed
- compileall: passed
- git diff --check: passed
- sync_roadmap_status --check: passed
- forbidden-surface/stale scans: passed
- CodeGraph impact snapshot: captured

Pending before merge:

- Codex exact-head blocker review
- GitHub PR CI

## Boundary note

This is an attach/control shell implementation, not a live runtime. The caller supplies the P6 session and any control surface. The module imports no Gateway/Feishu/platform adapter, starts no runtime, starts no Worker, launches no subprocess, and performs no delivery.


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
