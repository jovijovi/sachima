# P6 Controlled AI FLOW execution — Pre-development governance PRD

Date: 2026-06-25
Status: **Docs-only pre-development governance PRD.** This artifact prepares P6; it is not implementation approval and starts no runtime/execution.
Branch: `docs/p6-controlled-ai-flow-predev-governance`
Base: `release/sachima` at `40c4ed562994c0d1a29ad92d9f7f2d6fb6e9c9cf`

## Scope of this artifact

The operator approved opening the P6 controlled AI FLOW execution pre-development governance gate:

```text
批准开 P6 controlled AI FLOW execution pre-development governance：PRD → Claude 架构/teach-back → 技术方案 → Codex blocker review → 再请求实现批准。
```

Therefore this branch may create or update only documentation/status artifacts required to:

1. write the P6 PRD;
2. obtain Claude Code architect teach-back and architecture/design interpretation;
3. produce a no-code technical solution for the later P6-A implementation request;
4. run a Codex blocker review and converge blockers;
5. update roadmap/status prose so PR #167 is no longer described as current work;
6. produce a user review packet and request later implementation approval.

This branch must not add or edit runtime source code, tests, scripts that start runtime behavior, dependency declarations, Gateway/Feishu/platform adapters, production config, or service lifecycle files.

## Authority and fresh baseline

Authority files and live truth checked before drafting:

- `GOAL.md` — Sachima final product compass.
- `AGENTS.md` — roadmap preflight, worktree, CodeGraph, and non-approval rules.
- `docs/roadmap/current-status.md` — living roadmap position, tails, and explicit non-approvals.
- `docs/plans/2026-06-17-agent-run-supervisor-sachima-wp4-controlled-ai-flow-local-offline-orchestration-design.md` — WP4 controlled AI FLOW design.
- `docs/plans/2026-06-25-agent-run-supervisor-sachima-post-p5-status-calibration-and-planning-review.md` — post-P5 calibration recommending this P6 gate.
- `docs/plans/2026-06-20-agent-run-supervisor-sachima-p5-temporal-pr-b-predev-governance-prd.md` and technical solution — P5 Temporal PR B governance basis.
- CodeGraph index initialized in this worktree; source reconnaissance covered `StepExecutor`, `StepExecutionOutcome`, `activity_ai_flow_orchestration`, `P5TemporalStepExecutor`, `P5TemporalControlSurface`, `P5TemporalRuntimeClient`, `StepWorkflow`, and the P5 local/offline adapter oracle.

Fresh repo/GitHub truth at authoring start:

```text
repository: jovijovi/sachima
base_branch: release/sachima
base_head: 40c4ed562994c0d1a29ad92d9f7f2d6fb6e9c9cf
open_prs_against_release_sachima: 0
pr167_state: MERGED
pr167_merge_commit: 936ebc9f19c98a19228968101060023ede2327f1
status_sync_head_after_pr167: 40c4ed562994c0d1a29ad92d9f7f2d6fb6e9c9cf
claude_code_exact_model_smoke: PASS for claude-opus-4-8[1m] / effort max
codex_cli_version: 0.142.1
```

## Product goal

Prepare a precise, reviewable, behavior-bearing but safe P6 implementation request for **Temporal-backed controlled AI FLOW execution**.

The later P6-A implementation, if approved, should prove that the merged WP4 controlled AI FLOW orchestrator can execute a bounded workflow through the merged P5 Temporal Slice 1 runtime surface using **controlled-deterministic or injected/fake step bodies only**.

The goal is meaningful forward motion, not another fake status loop:

```text
WP4 workflow graph + gates + artifacts
  -> P5TemporalStepExecutor / P5 Temporal control surface
  -> Temporal-backed run/query/cancel/recover evidence
  -> sanitized final workflow evidence
```

But P6-A must still stop short of real agent launch. It must not execute real `acpx`, `npx`, Claude Code, Codex CLI, write-capable roles, Gateway/Feishu delivery, production config, or production traffic.

## Actors and role split

| Actor / AGENT | Role in this governance PR | Writes code? |
|---|---|---:|
| Hermes | PM/controller, PRD author, scope owner, repo/worktree operator, deterministic doc gates, final evidence arbiter | No |
| Claude Code | Architect teach-back and no-code technical-solution author, exact model `claude-opus-4-8[1m]`, effort `max` for architecture | No |
| Codex CLI | Primary independent blocker reviewer of the final PRD/technical solution, GPT-5.5 / xhigh | No |
| Operator / user | Approves or rejects the later P6-A implementation request | No code in this PR |

If Claude Code becomes unavailable due quota, model access, CLI auth/config, network, or local runtime failure, any fallback must be recorded. A fallback authoring run never counts as the independent Codex review.

## Implementation slice being prepared

This governance PR prepares the later **P6-A implementation**. P6 should remain staged:

```text
P6-predev: PRD + Claude architecture/teach-back + technical solution + Codex blocker review
P6-A: Temporal-backed controlled AI FLOW execution with controlled-deterministic or injected/fake steps only
P6-B: later bounded read-only real-agent step execution under the same Temporal control surface
P6-C: later write-capable roles / rollback / sandbox gates, still local/offline first
P7: Gateway / Feishu / IM / real delivery, separately approved
```

This PRD intentionally prepares only P6-A. P6-B/P6-C/P7 are future approvals.

## Functional requirements for the later P6-A implementation

### FR1 — P6-A default-off admission and exact approval boundary

The later P6-A implementation must be default-off and require an exact operator approval reference before invoking the P5 Temporal StepExecutor path from the WP4 orchestrator.

With P6-A disabled, missing, stale, mismatched, or ambiguous approval material, the workflow must park or fail closed before any Temporal workflow/activity call.

Required stable failure family:

```text
p6_execution_disabled
p6_approval_mismatch
p6_precondition_unmet
p6_gate_blocked
```

### FR2 — Reuse the WP4 workflow contract without weakening it

P6-A must reuse the merged WP4 model:

- versioned static workflow graph;
- bounded step count;
- declared dependencies only;
- operator gates before workflow admission, before each step, after each step, and before terminal acceptance;
- claim-check artifacts only;
- no dynamic AI-selected successors;
- no business verdict inferred from executor success;
- active-run cancellation WATCH preserved.

P6-A may tighten the schema to the first Temporal-backed slice. It must not loosen WP4 validation to make Temporal easier to call.

### FR3 — Bind WP4 StepExecutor to P5TemporalStepExecutor safely

The first P6-A behavior-bearing path should connect WP4's existing `StepExecutor` seam to `P5TemporalStepExecutor`.

The bridge must preserve the exact shape:

```text
execute(request, *, role_binding, resolved_inputs) -> StepExecutionOutcome
```

Required bridge behavior:

- translate only sanitized refs, digests, role keys, step ids, run ids, and idempotency material into P5 `StartRequest`;
- reject raw prompt/context/model output, raw artifact bodies, platform ids, private paths, card JSON, media bytes, exception text, credentials, or signed URLs;
- map P5 stable result/error codes into WP4 step statuses without inventing success;
- expose query/cancel/recover/close through the caller-owned AI FLOW control path only;
- return `STEP_WATCH` / `STEP_CANCEL_AMBIGUOUS` when active-run cancellation is not proven clean.

### FR4 — Controlled-deterministic or injected/fake step bodies only

P6-A must exercise Temporal-backed workflow orchestration without launching real agents.

Allowed step bodies:

```text
controlled_deterministic
injected_fake_step_executor
static_claim_check_fixture
```

Forbidden step bodies:

```text
real_acpx
real_npx
real_claude_code
real_codex_cli
write_capable_role
network_fetch_runner
satine_or_hermes_profile_acp
```

This is the key compression: P6-A should be behavior-bearing at the orchestration/runtime layer, but fake or deterministic at the agent-execution layer.

### FR5 — Temporal-backed run/query/cancel/recover evidence

P6-A must prove the AI FLOW run is actually mediated through the P5 Temporal Slice 1 control surface, not merely through local in-memory fakes.

Required evidence families:

- start returns a sanitized run/step projection;
- query returns a sanitized in-flight and terminal snapshot;
- duplicate identical start is idempotent and does not run twice;
- duplicate divergent start fails closed;
- recover reattaches by workflow id and does not auto-relaunch uncertain work;
- cancel preserves active-run WATCH when clean interruption cannot be proven;
- close/terminalize returns sanitized terminal evidence only.

### FR6 — No-leak across AI FLOW state, Temporal history, and evidence

P6-A must run no-leak checks across three surfaces:

1. WP4 AI FLOW store/query/evidence projections;
2. P5 Temporal JSON projection and serialized history bytes;
3. final P6 evidence packet / dev log / user-review packet.

Allowed persistent material:

```text
safe refs, sha256 digests, stable codes, counts, indices, schema versions, role keys, step ids, workflow ids, lease/epoch/state versions, gate decision summaries, WATCH markers, sanitized evidence refs
```

Forbidden persistent or user-visible material:

```text
raw prompts, raw model outputs, raw acpx/ACP/agent stdout, raw exception text, tracebacks, PIDs, hostnames, platform private ids, card JSON, message ids, media bytes, private paths, tokens, credentials, secrets, connection strings, signed URLs, delivery payloads, IM bodies
```

Any leak is a critical blocker.

### FR7 — Gateway / Feishu / platform boundary remains closed

P6-A must not import, instantiate, call, start, stop, mutate, restart, or configure Gateway, Feishu, platform adapters, public ingress, or real delivery surfaces.

A static boundary gate must inspect the P6-A changed files and relevant import closure so no Gateway/Feishu/platform/delivery lifecycle enters the implementation.

### FR8 — Ops-owned Temporal lifecycle remains constrained

P6-A may use the already-approved P5 Temporal hermetic-local test harness and staging runbook boundaries. It must not add production cluster, production traffic, Gateway-owned Worker lifecycle, auto-started service lifecycle, Docker/systemd/socket listener behavior, or production config writes.

Temporal service/Worker startup, when needed for tests, remains hermetic-local or staging-namespace only, ops-owned, and explicitly bounded by the existing P5 grant.

### FR9 — Acceptance gates are visible to implementer and reviewer

The later P6-A implementation prompt and reviewer prompt must list the gate suite before work begins.

Required gate families:

- changed-file allowlist for P6-A source/test/docs surfaces;
- forbidden Gateway/Feishu/platform/delivery/import/lifecycle scan;
- no real `acpx`/`npx`/Claude/Codex launch scan;
- no-leak scan over added lines plus runtime/evidence surfaces;
- Temporal history SCAN 1 + SCAN 2 reuse or extension;
- duplicate-start / divergent-start / recover / cancel WATCH probes;
- WP4 oracle/conformance tests;
- P5TemporalStepExecutor integration tests;
- docs/status stale-phrase scan;
- Codex exact-head blocker review.

### FR10 — User review packet and implementation approval handoff

This governance PR must end by requesting a narrow P6-A implementation approval, not by starting code.

The user review packet must include:

- recommended implementation scope;
- exact allowed files/surfaces;
- tests/gates that block merge;
- non-approvals preserved;
- reviewer verdict and remaining tails;
- exact implementation approval phrase.

## Non-functional requirements

- Production-facing pressure is real; avoid another status-only loop after this governance gate.
- Safety gates remain concrete tests/scans, not fear language.
- Evidence before claims: every readiness claim must cite a local gate, CI/check, code/doc diff, or reviewer result.
- Local/offline/default-off first; staging remains ops-owned and bounded.
- No raw exception text in durable state, logs, user-visible reports, or review evidence.
- No new user-facing environment variables for non-secret behavior.
- No prompt-cache-breaking Hermes core change; this is Sachima-side governed planning only.

## Explicit non-approvals in this governance PR

```text
source_code_implementation
runtime_or_worker_start
workflow_or_activity_execution
controlled_ai_flow_execution
real_acpx_or_npx_or_agent_execution
additional_or_unbounded_persistent_session_execution
additional_or_unbounded_cancellation_execution
write_capable_roles
satine_or_hermes_profile_acp_execution
agent_to_agent_auto_routing
automatic_replies
worker_auto_routing
Gateway involvement or mutation
Gateway restart or reload
Feishu or IM delivery
platform adapter mutation
public ingress
production cluster or production traffic
production config write
service restart or reload
real delivery
```

## Open questions for Claude architect teach-back

Claude Code must answer these before producing the technical solution:

1. What is the minimal P6-A behavior-bearing path that proves Temporal-backed AI FLOW execution without real agent launch?
2. Should P6-A run through the existing `activity_ai_flow_orchestration` entrypoint, a new P6 wrapper around it, or a narrow test-only integration harness that becomes production code later?
3. Where should the P6-A approval/admission check live so it blocks before Temporal calls while preserving WP4/P5 boundaries?
4. How should P6-A express query/cancel/recover/close through the existing WP4 + P5 surfaces without adding a new broad control plane?
5. Which P5 Temporal tests can be reused as gates, and which new P6-specific tests are required?
6. How should P6-A prove no raw material appears in both WP4 evidence and Temporal history?
7. How does active-run cancellation WATCH flow through P6-A evidence without overclaiming clean cancellation?
8. What exact implementation tasks should be approved later, and what files should remain forbidden?
9. What is the smallest useful staging/canary story, if any, that does not become a merge blocker or production rollout?
10. What implementation approval phrase should be presented to the user after review?

## Acceptance criteria for this pre-development governance PR

This docs-only PR can be considered complete only when:

- PRD is written and internally consistent.
- Claude Code exact model path is recorded or any fallback is labeled.
- Claude architect teach-back has no P0/P1 misunderstanding.
- Claude no-code technical solution maps PRD FRs to files, tests, gates, and non-approvals.
- Codex blocker review of the final PRD + technical solution returns PASS or all blockers are fixed and re-reviewed.
- `docs/roadmap/current-status.md` no longer describes post-P5 calibration as current work.
- Manifest and dev log record verification evidence.
- Docs-only changed-file allowlist passes.
- Forbidden implementation-surface scan passes.
- Secret/no-leak added-line scan passes.
- `tools/sync_roadmap_status.py --check --base-remote sachima` passes.
- The final user review packet asks for later implementation approval and does not imply implementation is already approved.

## Suggested later implementation approval phrase

Claude/Codex may refine this phrase during review, but it must stay no broader than:

```text
approve_agent_run_supervisor_sachima_p6a_temporal_backed_controlled_ai_flow_execution_implementation_controlled_deterministic_or_injected_fake_steps_only_default_off_no_real_agent_execution_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```
