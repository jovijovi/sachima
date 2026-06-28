# P6 Runtime Lifecycle / Controlled Attach Plan — User review packet

Date: 2026-06-28
Status: Draft after Claude teach-back PASS and Codex blocker review PASS; pending PR and CI.

## What this PR does

This PR creates the docs-only governance packet for the next Sachima mainline after the P6-B bounded read-only smoke PASS.

It defines the future controlled attach layer that must exist before broader real controlled AI FLOW execution:

- caller-owned runtime/control-surface attach;
- no Gateway-owned Worker/service/runtime lifecycle;
- default-off operator gates;
- start/query/update/cancel/recover/close semantics;
- idempotency, leases, epochs, state_version, no duplicate relaunch;
- health, drain, kill switch, rollback;
- no-leak evidence over attach state, P6 snapshots, P5/WP4 evidence, and user-visible docs;
- WP3b active-run cancellation WATCH preservation.

## What this PR does not do

```text
no source implementation
no runtime start
no Worker start
no Gateway restart/reload
no Feishu/IM/live/default-on behavior
no public ingress
no production config writes
no production cluster or traffic
no service restart
no platform adapter mutation
no real delivery
no additional real acpx/npx/agent execution
no write roles
no production cluster or traffic
```

## Why this is the right next step

PR #181 proved a single bounded read-only real step. That proves the launch/replay/evidence pipeline, but not the operational runtime lifecycle. Before any broader real controlled AI FLOW execution, Sachima needs a controlled attach plan so recovery, health, rollback, and duplicate-start behavior are not improvised inside a live runtime path.

## Recommended later implementation scope

If this PR passes, the next implementation should be a narrow default-off local/offline or hermetic/staging attach layer, probably centered on a new module like:

```text
sachima_supervisor/p6_runtime_attach.py
```

It should attach to an already supplied caller-owned P5/P6 control surface. The first slice should bind only deterministic/injected-fake/local-offline execution surfaces; it must not bind the reusable P6-B real-agent runner without a separate real-execution approval. It must not start Temporal, start a Worker, spawn a subprocess, touch Gateway, or deliver anything.

## Exact future approval phrase

Use no broader than:

```text
approve_agent_run_supervisor_sachima_p6_runtime_lifecycle_controlled_attach_implementation_default_off_caller_owned_attach_only_no_runtime_or_worker_start_no_additional_real_agent_execution_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

## Review checklist before approval

- Claude teach-back: PASS / no P0/P1 misunderstanding.
- Codex blocker review: PASS / no blockers.
- Docs-only gate: pass.
- CI: pass on final PR head.
- No stale docs claiming implementation/live approval.
