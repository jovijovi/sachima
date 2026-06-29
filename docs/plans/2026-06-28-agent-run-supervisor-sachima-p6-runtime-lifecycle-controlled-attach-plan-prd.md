# P6 Runtime Lifecycle / Controlled Attach Plan — PRD

Date: 2026-06-28
Status: **Docs-only governance PRD draft** for the next safe mainline after PR #181/#182. This artifact is not source implementation approval and starts no runtime, Worker, Gateway, Feishu, service, or real agent execution.
Branch: `docs/runtime-lifecycle-controlled-attach-plan`
Base: `release/sachima` at `890ed3f89b2a995dc3bf910d4a4a4cc57f54e7c9` (after PR #182 status closure sync)

## Scope of this artifact

The operator approved proceeding with the recommended next step after PR #182:

```text
批准实施
```

In context, this authorizes **only** the post-merge cleanup plus this docs-only runtime lifecycle / controlled attach governance gate described in the prior plan. It explicitly does **not** authorize source implementation, runtime start, Worker start, additional real agent/acpx/npx execution, Gateway/Feishu/live behavior, production config writes, service restart, public ingress, production traffic, platform-adapter mutation, or real delivery.

This branch may create/update only documentation/status artifacts required to:

1. define the P6 runtime lifecycle / controlled attach problem and product goal;
2. settle ownership and attach semantics for the next implementation gate;
3. specify start/query/update/cancel/recover/close operator gates, health checks, rollback, leases, epochs, idempotency, and no-duplicate-relaunch requirements;
4. preserve WP3b active-run cancellation WATCH and P6-B bounded-smoke truth;
5. produce a user review packet and exact later implementation approval phrase;
6. run Claude architecture teach-back and Codex blocker review.

## Live baseline and authority

Fresh baseline checked before authoring:

```text
repository: jovijovi/sachima
base_branch: release/sachima
base_head: 890ed3f89b2a995dc3bf910d4a4a4cc57f54e7c9
open_prs_against_release_sachima: 0
pr181_state: MERGED
pr181_merge_commit: 42b2ec51aa3ecbf65fef2c0c192e6c31a045e904
pr182_state: MERGED
pr182_merge_commit: 7d8b635744ad2054ff1cbe9e986f24e7d1de548f
```

Authority inputs:

- `GOAL.md` — production-grade AI workbench target, low-intrusion runtime ownership, claim-check discipline, no-leak rules.
- `docs/roadmap/current-status.md` — current decision, P6 runtime lifecycle / controlled attach dashboard row, and explicit non-approvals.
- P5 design/readiness and Temporal Slice 1 docs — caller-owned Temporal/control-surface semantics.
- P6/P6-A docs and code — default-off controlled AI FLOW composition, control operations, WATCH propagation.
- P6-B docs and PR #181 evidence — one bounded read-only real-smoke PASS only, no broader execution approval.
- CodeGraph reconnaissance over `p5_temporal/*`, `p6_controlled_ai_flow.py`, `p6b_read_only_real_agent.py`, `activity_controlled_exec.py`, `ai_flow_*`.

## Product problem

P6-B proved that one bounded read-only real agent step can launch through pinned local `acpx@0.10.0`, produce `VERDICT: PASS`, replay/recover without duplicate relaunch, and leave no repo/live side effects. That is a valuable proof, but it is still a **single-step one-shot**.

The next product gap is not another smoke. The next gap is operational lifecycle:

- who owns runtime and Worker lifecycle;
- how a caller attaches to an already-running durable backend without the Gateway becoming an owner;
- how a run is started, queried, updated, cancelled, recovered, terminalized, and health-checked;
- how duplicate starts and crash/restart attach avoid relaunching uncertain work;
- how rollback and kill switches work;
- how raw prompts, model outputs, platform IDs, card JSON, paths, credentials, stdout/stderr, and raw exceptions stay out of durable history and user-visible evidence.

Without this plan, a later "real controlled AI FLOW" implementation could accidentally do the dumb thing: let a message path spawn workers, conflate Gateway delivery with runtime ownership, hide duplicate launches behind recovery, or treat a one-shot smoke as an always-on runtime. We are not doing that.

## Goal

Define the next **docs-only** gate that makes a later implementation obvious and reviewable:

```text
P6 runtime lifecycle / controlled attach plan
  -> caller-owned attach to a durable backend/control surface
  -> no Gateway-owned lifecycle
  -> default-off operator gates
  -> start/query/update/cancel/recover/close semantics
  -> health/rollback/drain/kill-switch rules
  -> duplicate-start / no-duplicate-relaunch / no-leak evidence
  -> separate implementation approval
```

The plan must prepare a later implementation slice that is production-shaped but still bounded: local/offline or hermetic/staging first, default-off, caller-owned, no live delivery, no production traffic, no write roles, and no additional real agent/acpx/npx execution unless separately approved.

## Non-goals / non-approvals

This docs-only PR approves none of:

```text
source implementation
runtime or Worker start
Temporal service start
Gateway restart/reload
Gateway-owned runtime lifecycle
Feishu/IM/live/default-on behavior
public ingress
production cluster or production traffic
production config writes
service restart or reload
platform adapter mutation
real delivery
additional real acpx/npx/agent execution beyond recorded bounded smokes
write-capable roles
additional or unbounded persistent-session execution
additional or unbounded cancellation execution
clean active-run cancellation claim beyond WATCH
```

## Actors and ownership

| Actor | Owns | Must not own in this gate |
|---|---|---|
| Sachima / FlowWeaver caller/controller | runtime choice, attach decision, control surface, durable records, idempotency, leases, operator gates, business verdict | Gateway rendering/delivery behavior |
| P5 Temporal/control-surface layer | no-throw sanitized start/query/update/cancel/recover/close adapter over caller-supplied client | platform delivery, business verdict, Gateway lifecycle |
| P6 controlled AI FLOW layer | default-off admission/composition/control operations over WP4 + P5 seam | runtime process lifecycle, real agent execution by implication |
| P6-B real-agent step seam | one approved bounded read-only one-shot evidence | additional real execution or persistent default-on behavior |
| Gateway / Feishu / IM surface | later rendering/delivery/ACK only when separately approved | Temporal/Worker/service/socket/subprocess ownership or auto-start |
| Ops/SRE | Worker/service lifecycle when separately approved; health/drain/rollback runbooks | app-level business verdict |

## Functional requirements for the later implementation gate

### FR1 — Explicit attach boundary

A later implementation must distinguish **attach to an existing caller-supplied runtime/control surface** from **start a runtime/Worker/service**.

- `attach` may validate a caller-supplied client/control surface and bind it to a P6 session.
- `attach` must not spawn a service, Worker, subprocess, Docker container, socket listener, CLI daemon, or Gateway-managed lifecycle.
- Missing or unsafe attach material fails closed before any workflow/activity/agent call.

### FR2 — Operation state machine

The later implementation must define and test this sanitized operation state machine:

```text
attach -> start -> query/update/cancel/recover* -> close/terminalize -> detach
```

Each operation returns stable codes and safe projections only.

### FR3 — Idempotency, lease, epoch, and state-version rules

Every mutating operation must bind:

- `run_id`, `workflow_id`, `step_id` where applicable;
- `idempotency_key` + request fingerprint;
- `lease_id`, `lease_epoch`, `state_version`;
- role binding digest and operator gate reference;
- durable backend/control-surface identity as a sanitized ref, never a connection string.

Identical replay returns the stored projection. Divergent replay fails closed before launch/mutation. Stale lease/epoch/state_version fails closed.

### FR4 — No duplicate relaunch under recovery

`recover` and `query` must never call a new step execution just to resolve ambiguity. They may only reattach/query existing durable state. Ambiguous recovery returns `recover_ambiguous` / WATCH and requires an operator gate.

### FR5 — Health, drain, kill switch, and rollback

The later implementation must specify health checks and rollback controls before any broader execution:

- control-surface health: attached/unattached, backend reachable, namespace/task-queue identity safe ref;
- Worker health: ops-owned poller/backlog/build-id where applicable;
- drain: stop accepting new starts, let in-flight deterministic work settle, mark ambiguous states WATCH;
- kill switch: disable P6 admission and detach caller-supplied runtime without killing Gateway;
- rollback: revert to local/offline adapter or deterministic/fake executor without touching delivery surfaces.

### FR6 — No-leak evidence across four surfaces

Evidence must cover:

1. P6 control snapshots;
2. WP4 store/query/evidence;
3. P5 Temporal/control-surface projections and event/history bytes where used;
4. user-visible dev log / review packet / future PR body.

Allowed material: safe refs, digests, stable codes, counts, schema versions, run/step ids, lease/epoch/state versions, WATCH markers, sanitized evidence refs.

Forbidden material: raw prompts, raw model output, stdout/stderr walls, raw exception text, tracebacks, platform IDs, card JSON, message IDs, media bytes/private paths, credentials, tokens, connection strings, signed URLs, delivery payloads.

### FR7 — WP3b cancellation WATCH preserved

Active-run cancellation remains WATCH unless a later separate implementation proves clean interruption and cleanup. The runtime lifecycle plan must not redefine WATCH as success.

### FR8 — P6-B bounded-smoke truth preserved

The PR #181 result is a prerequisite evidence item, not a general license. It proves exactly one bounded read-only real smoke; it does not approve additional real agent execution, write roles, persistent default-on behavior, live delivery, or production traffic.

### FR9 — Gateway/Feishu/live boundaries remain closed

The implementation plan must include static forbidden-surface gates against Gateway, Feishu/Lark, platform adapters, delivery APIs, public ingress, production config, service lifecycle, and runtime auto-start in request-handling paths.

### FR10 — Review and approval handoff

This docs-only gate must end by requesting a narrow later implementation approval, not by starting code.

## Acceptance criteria for this docs-only PR

- PRD, technical solution, manifest, user review packet, dev log exist.
- Roadmap/status/tail/phase/reference indexes point to this docs-only gate without implying implementation approval.
- Claude Code architecture teach-back is recorded and any P0/P1 misunderstandings are fixed.
- Codex blocker review is PASS on the final diff.
- Docs-only allowlist, YAML parse, `git diff --check`, `tools/sync_roadmap_status.py --check`, stale wording scan, and forbidden implementation-surface scan pass.

## Later implementation approval phrase

If this governance PR passes and the operator wants source implementation, the next approval should be no broader than:

```text
approve_agent_run_supervisor_sachima_p6_runtime_lifecycle_controlled_attach_implementation_default_off_caller_owned_attach_only_no_runtime_or_worker_start_no_additional_real_agent_execution_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

Read that phrase together with the non-goals list above: service restart, public ingress, production cluster/traffic, platform-adapter mutation, network-facing delivery, and broader controlled AI FLOW execution remain forbidden unless separately named. A future **real execution** approval after that implementation must still name the exact runner/backend/scope/run count/time budget/evidence root and must remain separate unless explicitly included.
