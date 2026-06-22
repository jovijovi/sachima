# WP4 — Controlled AI FLOW local/offline implementation gate PRD

Date: 2026-06-17
Status: **Docs-only gate-preparation PRD** — preparation approved by operator; implementation is not approved.
Branch: `docs/wp4-controlled-ai-flow-implementation-gate`
Base: `release/sachima` at `187e41ff1ab00ec8c403e3e24e47120ad19595d4`

## Scope of this artifact

This PRD prepares the next approval decision for WP4 implementation. It is a product/control artifact, not implementation approval and not a workflow execution request.

The operator approved **preparing** the WP4 implementation gate. That means this branch may create docs-only planning, architecture, manifest, and review artifacts that let the operator decide whether to approve implementation later.

It does **not** authorize source-code implementation, tests that launch real agents, `acpx` invocation, workflow execution, Gateway/Feishu work, production config writes, service restarts, live/default-on behavior, public ingress, or real delivery.

## Authority and baseline

Authority files and live truth checked before drafting:

- `GOAL.md` — Sachima final product compass.
- `AGENTS.md` — roadmap preflight, worktree, and non-approval rules.
- `docs/roadmap/current-status.md` — current phase and next allowed request.
- `docs/plans/2026-06-17-agent-run-supervisor-sachima-wp4-controlled-ai-flow-local-offline-orchestration-design.md` — merged WP4 design packet.
- `docs/plans/2026-06-17-agent-run-supervisor-sachima-wp4-controlled-ai-flow-local-offline-orchestration-design-manifest.yaml` — merged design manifest; its candidate transport fields are historical to the design branch and do not override live PR truth.

Fresh repo state at preparation start:

- `release/sachima` head: `187e41ff1ab00ec8c403e3e24e47120ad19595d4`.
- PR #142 merged WP4 design: merge commit `bb5e5d9bf707fde7934939cc473544511bd65ffd`.
- PR #143 merged WP4 status sync: merge commit `6c045d26f936cf048dcf427f3e3a753c77c8147a`.
- Open PRs against `release/sachima`: `0` at preflight.
- CodeGraph status for this worktree: initialized with CodeGraph 1.0.1, node-sqlite/WAL, pending changes 0/0/0.

## Product goal

Prepare a narrow, reviewable implementation gate for the first WP4 controlled AI FLOW slice:

> a caller-owned, local/offline, read-only, bounded, static multi-step workflow orchestrator over the existing Sachima supervisor seam, with explicit operator gates, claim-check artifacts, per-step idempotency/CAS, sanitized evidence, and fail-closed behavior.

## Implementation gate being prepared

The future implementation gate, if later approved, should be narrower than the full WP4 design:

1. Implement the **minimum local/offline workflow state machine** required to validate, create, step, query, cancel-between-steps, and summarize one static bounded read-only graph.
2. Use injected/fake step executors for deterministic tests in the implementation PR unless the later approval explicitly includes a bounded real run clause.
3. Bind only existing read-only role keys and capability gates already present in the Sachima supervisor seam.
4. Persist only sanitized workflow records and artifact refs/digests; raw prompt/context/artifact bodies stay out of durable state.
5. Preserve WP3b's active-run cancellation WATCH: between-step cancellation is deterministic; active-run cancellation remains best-effort/indeterminate unless separately proven.

## Proposed future implementation approval phrase

The phrase below is proposed for a later operator decision. It is **not granted by this preparation PR**:

```text
approve_agent_run_supervisor_sachima_controlled_ai_flow_local_offline_orchestration_implementation_read_only_roles_only_bounded_steps_injected_fakes_first_no_real_workflow_execution_no_additional_acpx_invocation_no_write_roles_no_auto_routing_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

If the operator wants the implementation PR to include a real local workflow smoke, that must be a second explicit clause with exact runner, role, step count, evidence root, and one-run/no-replay rules. The default recommendation is **implementation first with injected fakes only; real smoke later**.

## In scope for the future implementation PR

- New local/offline workflow module(s) under `sachima_supervisor/`, using public supervisor boundaries and existing local/offline patterns.
- Data classes or exact validators for:
  - workflow spec;
  - workflow run record;
  - step record / attempt record;
  - gate decision record;
  - artifact ref record;
  - cancellation/abort record;
  - final sanitized evidence projection.
- In-memory caller-owned store for the first slice, with lock-guarded CAS semantics mirroring the approved first-slice pattern in `ControlledLocalExecClaimStore`.
- Deterministic injected executor interface for tests; no real agent/acpx launch in the implementation PR unless separately approved later.
- Tests for graph validation, bounded step execution with injected fakes, idempotent replay, conflict rejection, gate failures, artifact ref validation, between-step cancellation, active-run cancellation WATCH projection, sanitized query/evidence, and forbidden live surfaces.
- Docs/dev-log/manifest updates that record the implementation scope and non-approvals compactly.

## Out of scope / explicit non-approvals

```text
real_workflow_execution
additional_acpx_invocation
additional_real_agent_execution
write_capable_roles
agent_to_agent_auto_routing
automatic_replies
worker_auto_routing
satine_or_hermes_profile_acp_execution
gateway_involvement_or_mutation
gateway_restart_or_reload
feishu_or_im_delivery
live_or_default_on_behavior
public_ingress
production_config_write
real_delivery
unbounded_or_additional_persistent_session_execution
additional_or_unbounded_cancellation_execution
production_durable_runtime_code_implementation
external_temporal_service_or_worker_startup
```

## Functional requirements for the future implementation

### FR1 — Workflow spec validation

The implementation must accept only exact, plain, schema-versioned workflow specs with:

- safe workflow/run/step ids;
- bounded `max_steps`, `max_retries_per_step`, artifact bytes, and runtime budget values;
- a static directed acyclic graph;
- declared roles bound to read-only allowed role keys;
- declared input/output artifact contracts;
- no dynamic edges, AI-selected successors, fan-out beyond bounds, or cycles.

### FR2 — Caller-owned admission and operator gates

The state machine must require exact approval material for:

- workflow admission;
- pre-step attempt;
- post-step artifact propagation;
- terminal accept/reject/park.

Missing, expired, ambiguous, or mismatched gate material fails closed before a step executor is called.

### FR3 — Artifact claim-check discipline

Durable workflow state stores only artifact refs, digests, byte counts, kinds, producer step ids, and safe metadata. Raw body text, prompt text, platform IDs, card JSON, file paths outside safe refs, tool output, exceptions, and credentials must not enter durable state, query projections, logs, or evidence packets.

### FR4 — Per-step idempotency/CAS

A step attempt fingerprint must bind at least:

```text
run_id
step_id
workflow_spec_digest
role_binding_digest
input_artifact_digests
approval_ref
attempt_index
```

Identical replay returns the resident in-progress or terminal projection without a second executor call. Conflicting replay fails closed before any executor call.

### FR5 — Injected executor first

The implementation must define an executor seam that can be driven by injected fakes in tests. The implementation PR should not call real `acpx`, `npx`, Claude, Codex, Gateway, Feishu, network, or production services unless the later approval explicitly includes a real-smoke clause.

### FR6 — Cancellation posture

Between-step cancellation must deterministically stop future scheduling, park/release pending claims as appropriate, and produce a sanitized terminal or parked projection.

Active-run cancellation must preserve the WP3b WATCH caveat. A cancellation request while an injected or real step is in progress must not claim reliable interruption unless the executor reports a verified safe interruption with cleanup. Otherwise it must produce `indeterminate` / `active_run_cancellation_watch` style evidence.

### FR7 — Sanitized evidence

The final evidence projection must include only:

- workflow spec digest and version;
- sanitized step transition summaries;
- gate decisions by safe ref/status;
- artifact refs/digests/counts/kinds;
- retry/cancellation/compensation summaries;
- stable error codes;
- explicit non-approval flags.

## Non-functional requirements

- Local/offline only.
- Default-off by construction.
- No shell interpolation; if future subprocess calls are later approved, use argv lists and pinned local executables only.
- No raw exception text in user-visible or durable evidence.
- No platform IDs, card JSON, media bytes/paths, raw prompts, raw artifacts, tool output, credentials, or signed URLs in durable state.
- Exact type validation for external/spec/store inputs; reject hostile `str`, `dict`, `list`, and mapping subclasses where exact primitives are required.
- Tests must prove forbidden surfaces stay absent from source/diff and behavior.

## Acceptance gates for the future implementation PR

A later implementation PR is not ready for merge until it has:

1. RED/GREEN focused tests for every FR above.
2. Full relevant `tests/sachima_supervisor` pass.
3. `ruff check` on touched Python files or repo-configured equivalent.
4. `python3 -m compileall` on touched Python modules/scripts.
5. `git diff --check`.
6. Changed-file allowlist proving no Gateway/Feishu/platform/production config/live surface changes.
7. Secret/static scan over changed lines and new files.
8. Forbidden-surface scan for `acpx`, `npx`, network, Gateway, Feishu, Temporal Worker/service startup, subprocess, Docker/systemctl, production config writes, platform adapter mutation, and public ingress. Descriptor-only non-approval prose may appear in docs, but source/runtime calls/imports are blockers.
9. Codex primary repo-aware blocker review after PR + CI exist.
10. Post-merge verification and compact status update if merged.

## Open design questions for Claude architect

1. Should the first implementation module be a new `sachima_supervisor/activity_workflow.py`, or should it split store/spec/executor/evidence across smaller modules?
2. Which existing exact validators from `activity_controlled_exec.py` and `activity_session_lifecycle.py` should be reused vs copied/adapted to avoid unsafe dependency tangles?
3. What is the smallest TDD slice that proves controlled AI FLOW behavior without real execution?
4. How should the implementation model active-run cancellation WATCH without overclaiming interruption?
5. Which tests best prove no raw artifact/prompt/result leakage through query/evidence/log surfaces?

## Gate-preparation success criteria

This preparation task is complete when:

- this PRD is file-backed;
- Claude Code has produced a no-code architecture / implementation-plan packet;
- Codex has performed a blocker-only review of the PRD + architecture packet;
- blockers are fixed or explicitly carried as non-approved tails;
- Hermes reports a clear approval point to the operator.
