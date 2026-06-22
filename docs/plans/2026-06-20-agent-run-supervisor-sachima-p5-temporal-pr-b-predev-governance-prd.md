# P5 Temporal PR B — Pre-development governance PRD

Date: 2026-06-20
Status: **Docs-only pre-development governance PRD.** This artifact prepares PR B; it is not implementation approval.
Branch: `docs/p5-temporal-pr-b-predev-governance`
Base: `release/sachima` at `d6499e92106d47ec9c0ffe9232682c21acb0e8cf`
Prerequisite PR A: [#154](https://github.com/jovijovi/sachima/pull/154) — **MERGED** (`f465186cc96bc182eab00b1de039ed8258f06ac8`, mergedAt 2026-06-20T05:48:26Z)

## Scope of this artifact

This PRD is the product/control contract for the **P5 Temporal PR B pre-development governance PR**.

The operator approved this exact preparation scope:

```text
批准开始 Sachima P5 Temporal PR B 开发前治理 PR：先写 PRD、做 PRD 质量评审、Claude teach-back、技术方案评审，并顺带修复 PR #154 合并后的文档尾巴；不开始代码实现。
```

Therefore this branch may create or update only documentation/status artifacts required to:

1. write the PR B PRD;
2. review the PRD quality before architecture;
3. obtain a Claude architect teach-back of the requirements;
4. produce a no-code technical solution / implementation-plan packet;
5. run an independent technical-solution blocker review;
6. fix the post-merge status/documentation tail left by PR #154.

This branch must not add or edit runtime source code, tests, scripts that start runtime behavior, dependency declarations, Gateway/Feishu/platform adapters, production config, or service lifecycle files.

## Authority and fresh baseline

Authority files and live truth checked before drafting:

- `GOAL.md` — Sachima final product compass.
- `AGENTS.md` — roadmap preflight, worktree, CodeGraph, and non-approval rules.
- `docs/roadmap/current-status.md` — living roadmap position, tails, and explicit non-approvals.
- `docs/plans/2026-06-20-agent-run-supervisor-sachima-p5-temporal-production-runtime-enablement-slice-1-design-readiness.md` — merged PR A design/readiness packet.
- `docs/plans/2026-06-20-agent-run-supervisor-sachima-p5-temporal-production-runtime-enablement-slice-1-design-readiness-manifest.yaml` — merged PR A manifest.
- `docs/dev_log/2026-06-20-agent-run-supervisor-sachima-p5-temporal-production-runtime-enablement-slice-1-design-readiness.md` — merged PR A dev log.
- CodeGraph index in this worktree — initialized with CodeGraph 1.0.1 and current at authoring start.

Fresh repo/GitHub truth at authoring start:

```text
repository: jovijovi/sachima
base_branch: release/sachima
base_head: d6499e92106d47ec9c0ffe9232682c21acb0e8cf
open_prs_against_release_sachima: 0
pr154_state: MERGED
pr154_head: d16afbc5f5e4af139b8752747b81b540a8c65930
pr154_merge_commit: f465186cc96bc182eab00b1de039ed8258f06ac8
pr154_merged_at: 2026-06-20T05:48:26Z
```

## Product goal

Prepare a precise, reviewable, high-pressure but safe implementation gate for **PR B**, the first code-bearing Temporal runtime slice for Sachima/FlowWeaver.

PR B's intended product outcome, if later approved, is:

> Promote the proven FlowWeaver Temporal prototypes into first-class `sachima_supervisor/p5_temporal/` modules that attach the WP4 controlled AI FLOW `StepExecutor` seam to a real Temporal durable backend under a hermetic-local merge gate, while keeping the step body controlled deterministic, the Worker/service ops-owned, and production traffic / P6 real agent execution separately gated.

This governance PR exists so implementation starts with aligned requirements, Claude architect understanding, and reviewed technical design — not vibes, not cargo-culted prototype copy-paste. Cute, but deadly serious. nya.

## Actors and role split

| Actor / AGENT | Role in this governance PR | Writes code? |
|---|---|---:|
| Hermes | PM/controller, PRD author, scope owner, repo/worktree operator, deterministic doc gates, final evidence arbiter | No |
| PRD quality reviewer | Fresh-context reviewer of this PRD for clarity, completeness, measurability, contradictions, hidden approvals | No |
| Claude Code | Architect teach-back and later no-code technical-solution author | No |
| Codex CLI | Primary independent technical-solution reviewer, blocker-only re-review after fixes | No |
| Operator / user | Approves or rejects the later implementation request | No code in this PR |

If Claude Code is unavailable due quota, model access, CLI auth/config, network, or local runtime failure, Codex may temporarily substitute for architecture/docs authoring only if the downgrade is recorded; that authoring substitution never counts as the independent Codex review.

## Implementation PR B being prepared

PR B is expected to create a first-class package:

```text
sachima_supervisor/p5_temporal/
```

The PR A design fixed this prototype-to-module mapping. The PRD keeps it as the initial contract but allows Claude's technical solution to refine internal helper names while preserving public behavior and gates:

| Future PR B module | Required public responsibility |
|---|---|
| `contracts.py` | Frozen sanitized dataclasses / exact validators for start payload, update payloads, activity I/O, query snapshots, and stable result/error codes. |
| `workflow.py` | `StepWorkflow` with deterministic `@workflow.run`, `@workflow.query`, and `@workflow.update` handlers; no raw I/O in workflow code. |
| `activities.py` | `step_activity` and supporting claim-check validation/delivery activities; Slice 1 body is controlled deterministic, not real `acpx` / agent execution. |
| `runtime_client.py` | `P5TemporalRuntimeClient` over a caller-supplied `temporalio` client; no factory that hides service startup in request-handling code. |
| `control_surface.py` | `P5TemporalControlSurface`; no-throw public dispatcher for start/query/update/cancel/recover/close with sanitized results only. |
| `step_executor.py` | `P5TemporalStepExecutor` implementing the merged WP4 `StepExecutor` Protocol; default-off with exact approval token and enable flag. |
| `p5_temporal_worker.py` | Ops-owned Worker launcher / builder; never imported by Gateway or inbound-message paths. |
| `__init__.py` | Narrow package exports and approval-token constants. |
| `sachima_supervisor/__init__.py` | Re-export only stable public names if needed. |

## Functional requirements for PR B

### FR1 — Default-off admission and exact approval token

PR B must add Temporal execution behind an exact token and explicit enable flag. With the flag off or token missing, no Temporal call is made and the caller remains on the local/offline baseline.

Required failure shape:

```text
runtime_disabled
runtime_approval_mismatch
runtime_precondition_unmet
```

### FR2 — Sanitized contracts and exact validation

All data crossing into Temporal history must be exact, plain, schema-versioned, and sanitized. PR B must reject hostile subclasses, missing/extra fields, malformed refs, unsafe digests, raw prompt/output fields, private paths, platform ids, card JSON, media bytes, raw exception text, credentials, connection strings, signed URLs, and delivery payloads.

Allowed in Temporal history:

```text
stable codes; mode/phase; run/workflow/activity/step refs; role keys; claim-check refs + sha256 digests; artifact/evidence refs + digests; counts/indices/versions; sanitized lease_id/lease_epoch; caller verdict code; cancellation/recovery markers including active_run_watch
```

Forbidden in Temporal history:

```text
raw prompt/context/model output; raw acpx/ACP/agent stdout; exception text/tracebacks; PIDs/thread ids/host names; platform private ids/card JSON/message ids; media bytes/private paths; tokens/credentials/secrets/connection strings/signed URLs; delivery payloads/IM bodies
```

### FR3 — Deterministic workflow semantics

`StepWorkflow` must keep workflow code deterministic. It may maintain sanitized state, query snapshots, and update handlers; it must not perform file/network/subprocess/Gateway/Temporal-client operations from workflow code. Non-determinism belongs in activities or outside the workflow.

Required operations:

- `start` / run with a deterministic workflow id bound to caller refs and step idempotency material;
- query snapshot;
- update handlers for delivery/approval/rejection/resume/cancel-style events as applicable to PR B;
- close/terminalize;
- event-key idempotency for updates;
- duplicate-start reconciliation.

### FR4 — Runtime client duplicate-start and recovery behavior

`P5TemporalRuntimeClient` must be caller-supplied-client only. It must not own Temporal service/Worker lifecycle, hide `Client.connect(...)` behind Gateway request paths, or start subprocesses/servers.

Required behavior:

- identical duplicate start returns an idempotent/replayed projection and launches nothing twice;
- divergent duplicate start fails closed with `runtime_idempotency_conflict` or `invalid_start_payload`-style stable code;
- query/update/cancel/recover/close all return no-throw sanitized results;
- restart/recovery reattaches by workflow id and never auto-relaunches uncertain work.

### FR5 — StepExecutor bridge to WP4

`P5TemporalStepExecutor` must implement the exact merged WP4 `StepExecutor` Protocol shape:

```text
execute(request, *, role_binding, resolved_inputs) -> StepExecutionOutcome
```

It must preserve WP4 semantics:

- caller-owned workflow/orchestration decision;
- claim-check artifact refs only;
- no business verdict inferred from executor success;
- active-run cancellation WATCH preserved;
- controlled deterministic step body in Slice 1;
- no P6 real agent/acpx execution.

### FR6 — Ops-owned Worker and Gateway boundary

`p5_temporal_worker.py` may define an ops-owned Worker launcher/builder. Gateway, inbound-message paths, platform adapters, and Feishu code must not import, instantiate, start, stop, scale, drain, or hold a handle to the Worker, Temporal service lifecycle, task-queue admin, subprocesses, sockets, Docker, or systemd.

A static Gateway-boundary test is required and must fail if Gateway/runtime message paths import or reference the Worker/service lifecycle surface.

### FR7 — No-leak SCAN 1 + SCAN 2

PR B must prove both:

1. **SCAN 1 — JSON projection:** durable records/query snapshots/evidence JSON contain only allowed fields and values.
2. **SCAN 2 — serialized event-history bytes:** real Temporal history scanned as JSON and serialized event bytes contains no forbidden sentinel/material.

Any hit is a blocker and maps to `runtime_history_leak_detected`.

### FR8 — Hermetic-local Temporal gate blocks PR B merge

PR B must include a hermetic-local real-Worker test gate that blocks merge. It may use `WorkflowEnvironment.start_time_skipping()` and/or `temporal server start-dev` under an isolated namespace, but it must not depend on production cluster state.

Required probes:

- real Worker starts only inside the test harness / explicit hermetic gate;
- step body controlled deterministic;
- duplicate-start idempotency/conflict;
- Worker restart / replay / recovery without duplicate execution;
- determinism replay via Temporal Replayer or equivalent Temporal SDK replay gate;
- active-run cancellation WATCH preserved.

### FR9 — Staging is a parallel ops/canary track, not a merge blocker

PR B may include staging runbooks and ops-owned Worker wiring for `sachima-p5-staging` only under the PR A grant. Staging evidence is not required to merge PR B, but the design must make staging safe to run after merge:

- ops-owned lifecycle;
- 30-day retention default;
- bounded controlled deterministic runs only;
- health checks and rollback commands scoped to staging;
- no production namespace/traffic.

### FR10 — Reviewable implementation decomposition

The technical solution must break PR B into small TDD-friendly tasks with exact files, tests, and gates. It must say which prototype code is copied/adapted, which helpers are duplicated for boundary safety, and which public constants/protocols are reused.

It must explicitly avoid modifying broad unrelated surfaces such as Gateway, Feishu, platform adapters, production config, or existing large supervisor modules unless necessary and reviewed.

## Non-functional requirements

- Production-facing, but still docs-first before code.
- Local/hermetic/staging only under PR A's grant; production cluster and production traffic are separate gates.
- Default-off by construction.
- No shell interpolation; if subprocess use is ever approved in ops/runbooks, argv list only and never from Gateway request paths.
- No raw exception text in user-visible, durable, or review evidence.
- No raw prompt/output/platform IDs/card JSON/media/private paths/credentials/signed URLs in Temporal history or docs examples.
- Determinism before convenience: workflow code is replay-safe, and tests prove it.
- Evidence before claims: no implementation-ready claim until PRD review, teach-back, architecture packet, technical review, local doc gates, and user approval point exist.

## Explicit non-approvals for this governance PR

This governance PR does **not** approve or perform:

```text
source_code_implementation
runtime_tests_that_start_temporal
Temporal service startup
Temporal Worker startup
workflow_or_activity_execution
acpx_invocation
npx_invocation_or_network_fetch_evidence
real_agent_execution
controlled_ai_flow_execution
P6 real step activity execution
write_capable_roles
Gateway involvement or mutation
Gateway restart or reload
Feishu / IM delivery or send API calls
platform adapter mutation
public ingress
production cluster enablement
production traffic
production config writes
real delivery
```

The PR A lifecycle token remains granted only for the later PR B implementation scope of **hermetic-local + staging namespace** and ops-owned Worker/service lifecycle. It does not authorize production cluster, production traffic, P6 real agent execution, or Gateway-owned lifecycle.

## Acceptance criteria for this governance PR

This PR is complete only when all are true:

1. PRD exists and cites fresh PR #154 merge truth.
2. PRD quality review is performed from fresh context with score >=90 and no critical blockers.
3. Claude architect teach-back exists, scores >=90 under Hermes arbitration, and has no P0/P1 misunderstanding.
4. Claude no-code technical solution / implementation-plan packet exists.
5. Codex primary technical-solution review returns no blockers, or blockers are fixed and re-reviewed.
6. PR #154 post-merge documentation tails are corrected: PR A plan, PR A manifest, PR A dev log, and current-status no longer describe PR #154 as open/current candidate.
7. `docs/roadmap/current-status.md` records this governance PR as the current candidate and preserves PR B implementation as a future separately approved step.
8. Changed-file allowlist proves this branch is docs/status only.
9. `tools/sync_roadmap_status.py --check` passes.
10. Manifest YAML parses.
11. `git diff --check`, stale-status scan, forbidden implementation-surface scan, and secret/no-leak scan pass.
12. No code implementation starts.

## Recommended later implementation approval text

If this governance PR passes and the user accepts the review packet, the next approval should be narrow and explicit:

```text
批准开始 Sachima P5 Temporal PR B 实现：仅按已评审通过的 PRD 与技术方案实现 `sachima_supervisor/p5_temporal/` 第一片；允许 hermetic-local Temporal gate 和 staging namespace ops-owned Worker 轨道；Slice 1 step body 保持 controlled deterministic；不启用 production cluster/traffic，不执行 P6 real acpx/agent，不接入 Gateway/Feishu/live，不写生产配置，不做 real delivery。Hermes 总控，Claude Code 主程/架构/文档，Codex 主审，完成后提交 PR 申请。
```

This phrase is **not granted by this PRD**. It is the recommended next human approval after the governance PR is reviewed.

## Open questions for Claude teach-back and technical solution

Claude must answer these before designing:

1. Which existing prototype behavior is stable enough to promote directly, and which must be rewritten around exact validators for production-facing history safety?
2. How should `StepWorkflow` map WP4 run/step state without importing WP4 implementation details into Temporal workflow code?
3. What is the exact caller-supplied Temporal client boundary that prevents Gateway or request paths from owning runtime lifecycle?
4. How should duplicate-start reconciliation bind sanitized observable payloads so public digests are not treated as trust boundaries?
5. How will the implementation preserve WP3b active-run cancellation WATCH without overclaiming cancellation success?
6. What test harness shape proves real Worker, event-history bytes no-leak, restart/recovery, and determinism replay while staying hermetic/local?
7. Which fields belong in staging runbooks versus merge-blocking PR B tests?
8. What is the smallest implementation task order that avoids a huge unreviewable module dump?

## Governance handoff

This PRD is ready for PRD quality review. Architecture work must wait until the PRD review has no critical blockers. Implementation must wait for a separate user approval after the full governance packet is complete.
