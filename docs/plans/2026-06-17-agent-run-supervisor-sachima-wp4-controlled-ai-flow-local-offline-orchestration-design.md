# WP4 — Controlled AI FLOW local/offline orchestration design

Date: 2026-06-17
Status: **Candidate docs-only design packet** — PR pending. This document is not implementation approval.
Branch: `docs/ars-wp4-controlled-ai-flow-design`
Base: `release/sachima` at `6261303970e5bde05e0c5ed8db50c994c63f36af`

## Scope

WP4 defines the first **controlled AI FLOW** design for the existing
`agent-run-supervisor × Sachima` local/offline mainline: a caller-owned,
read-only, bounded multi-role / multi-step workflow executed over the existing
supervisor seam.

Strongest meaning: **design only**. It records the workflow contract, state
model, operator gates, claim-check artifact flow, idempotency rules, failure
semantics, cancellation posture, evidence format, and later implementation
gates. It does **not** add source code, does not start a supervisor or `acpx`,
does not execute a workflow, and does not approve live/Gateway/Feishu/public
ingress/production config/real delivery.

### Exact owner approval token for this design gate

```text
approve_agent_run_supervisor_sachima_controlled_ai_flow_local_offline_orchestration_design_docs_only_no_implementation_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

### Future implementation approval phrase, not granted by this PR

```text
approve_agent_run_supervisor_sachima_controlled_ai_flow_local_offline_orchestration_implementation_read_only_roles_only_bounded_steps_no_write_roles_no_auto_routing_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

## Current baseline

The supervisor → Sachima mainline has reached the end of Ring A's read-only
execution foundations:

- WP1a / WP1b added and proved the Claude Code read-only role path.
- WP2 added bounded multi-turn persistent-session hardening.
- WP3a added the cancellation request-state and supervisor interrupt API seam.
- WP3b merged in PR #140 as a bounded cancellation bridge with fail-closed
  semantics.

WP3b carries an explicit WATCH into WP4: deterministic self-test and fail-closed
cancellation behavior are verified, but real host/ACP `--cancel-during-turn` did
not reliably prove active-run cancellation. WP4 must therefore distinguish:

- **between-step cancellation** — deterministic: stop scheduling new steps,
  preserve terminal state, and run read-only cleanup/compensation bookkeeping;
- **active-run cancellation** — best-effort only until later evidence proves the
  host/ACP semantics. If not safely confirmed, the step is marked
  `indeterminate` / WATCH, not silently treated as cancelled.

## Non-goals and explicit non-approvals

This design does not approve any of the following:

```text
implementation
real_workflow_execution
additional_acpx_invocation
real_agent_execution
write_capable_roles
agent_to_agent_auto_routing
automatic_replies
worker_auto_routing
@all_fanout
satine_or_hermes_profile_acp_execution
durable_runtime_ownership_change
gateway_involvement_or_mutation
gateway_restart_or_reload
feishu_or_im_delivery
live_or_default_on_behavior
public_ingress
production_config_write
real_delivery
```

The first WP4 implementation slice, if later approved, remains local/offline,
read-only, bounded-step only, and caller-owned by Sachima/FlowWeaver.

## Design verdict

Use a **declarative, caller-owned, versioned workflow graph** executed by a
Sachima/FlowWeaver orchestrator over the existing supervisor seam.

"Controlled" means:

1. the caller supplies and validates the step graph before execution;
2. roles cannot dynamically choose the next step;
3. every step is bounded, idempotent, and operator-gated;
4. every artifact is passed by claim-check ref/digest, never raw body in durable
   state;
5. unknown, ambiguous, or over-budget states fail closed;
6. evidence is deterministic and sanitized.

## Architecture

### Workflow definition

A future implementation should define a schema-versioned workflow specification
owned by Sachima/FlowWeaver, not by the supervisor library:

```yaml
workflow_id: wf_<safe-id>
schema_version: sachima.ai_flow.local.v1
approval_ref: <operator-approved-scope-ref>
bounds:
  max_steps: 3
  max_retries_per_step: 1
  max_artifact_bytes: <bounded>
  max_runtime_seconds: <bounded>
roles:
  architect:
    role_key: sachima.claude.read_only_reviewer
    capabilities: [read, search]
  programmer_candidate:
    role_key: sachima.claude.read_only_reviewer
    capabilities: [read, search]
  reviewer:
    role_key: sachima.codex.primary_reviewer
    capabilities: [read, search]
steps:
  - step_id: architect
    role: architect
    input_refs: [request_summary]
    output_contract: architecture_packet_ref
  - step_id: programmer_candidate
    role: programmer_candidate
    input_refs: [architecture_packet_ref]
    output_contract: implementation_candidate_analysis_ref
  - step_id: reviewer
    role: reviewer
    input_refs: [architecture_packet_ref, implementation_candidate_analysis_ref]
    output_contract: blocker_review_ref
edges:
  - from: architect
    to: programmer_candidate
  - from: programmer_candidate
    to: reviewer
```

The first implementation target should be a small linear graph like the example
above. The spec may permit a DAG shape later, but the first slice should reject
cycles, dynamic edges, unbounded fan-out, and AI-selected successors.

### Step graph and scheduling

The orchestrator validates the graph before any step can run:

- exact safe step ids;
- acyclic graph;
- bounded step count;
- declared dependencies only;
- read-only role binding for every step;
- explicit input and output contracts;
- no implicit successor inference from model output.

Scheduling is topological and caller-owned. A step becomes runnable only when all
predecessor output refs are present, verified, and approved by the required
gate.

### Role binding and capability checks

Each logical role binds to an existing read-only role config and adapter gate.
The design intentionally reuses the WP1/WP2 role and session foundations rather
than creating a new execution path.

Required checks:

- bind-time role allowlist check;
- execution-time capability check;
- role-file digest/provenance binding where a real runner is involved;
- hard rejection for write, execute, terminal, fetch, network-runner, or
  mode-switch capabilities;
- no Satine/Hermes-profile ACP role registration in WP4.

Any unauthorized capability is a security failure, non-retryable, and terminal
for the workflow run.

### Operator gates

Gate types:

1. **workflow admission gate** — validates the approved scope and graph before a
   run can be created;
2. **pre-step gate** — operator authorizes a specific step attempt;
3. **post-step gate** — operator authorizes a produced artifact ref to flow to
   dependent steps;
4. **terminal gate** — operator accepts, rejects, or parks the final evidence
   packet.

All gates fail closed. Missing, expired, mismatched, or ambiguous gate material
halts the workflow; it never auto-continues.

### Claim-check artifact passing

Step outputs are stored in an out-of-band local/offline artifact store. Durable
workflow state stores only sanitized refs:

```yaml
artifact_ref:
  artifact_id: artifact_<safe-id>
  producer_step_id: architect
  content_digest: sha256:<hex>
  artifact_kind: architecture_packet
  byte_count: 1234
  created_at: <timestamp>
```

Downstream steps must resolve and re-hash refs before use. Digest mismatch,
missing artifact, wrong producer, wrong artifact kind, or oversized material is
non-retryable and fail-closed.

### Durable state and idempotency

A future implementation should keep a caller-owned workflow store with:

- workflow run record;
- step attempt records;
- gate decision records;
- artifact ref records;
- cancellation/abort records;
- final evidence projection.

Every state transition uses CAS over a sanitized version/epoch field. A step
idempotency fingerprint should bind at least:

```text
run_id
step_id
workflow_spec_digest
role_binding_digest
input_artifact_digests
approval_ref
attempt_index
```

Identical replay returns the existing in-progress or terminal projection without
launching another step. Conflicting replay fails before any supervisor call.

### Retry and compensation

Retry is bounded and only applies to explicitly retryable failure classes such as
transient local seam unavailability. Unknown failures are non-retryable.

Read-only WP4 compensation is mostly bookkeeping:

- release or park pending claims;
- mark unpropagated artifacts as orphaned/unused;
- record cancellation/abort terminal state;
- never apply or roll back file changes because write roles are not approved.

The compensation seam is still worth designing now so WP5 write-capable roles can
attach sandbox rollback later without changing the WP4 workflow contract.

### Failure taxonomy

| Failure class | Retryable | Required posture |
|---|---:|---|
| Spec validation / graph contract failure | No | fail closed before run creation |
| Capability or authorization failure | No | fail closed + security marker |
| Missing operator gate | No | halt / parked, no auto-proceed |
| Claim-check digest or artifact mismatch | No | fail closed + integrity marker |
| Bound exceeded | No | terminal fail closed |
| Transient local seam unavailable | Bounded | retry, then fail closed |
| Role execution failed or invalid artifact | Policy-bound | default non-retryable |
| Between-step cancellation | No | deterministic terminal cancellation |
| Active-run cancellation not confirmed | No | indeterminate WATCH, no artifact propagation |

### Cancellation and abort semantics

WP4 should model cancellation at two levels:

1. **workflow cancellation** — stop scheduling future steps and close the run as
   `cancelled`, `cancel_failed`, or `cancel_ambiguous` according to the existing
   cancellation state machine;
2. **step cancellation** — when a step is not running yet, deterministic; when a
   real step is in-flight, use WP3b's interrupt bridge but preserve the WATCH if
   the host/ACP cannot safely confirm active-run cancellation.

An indeterminate active step cannot publish artifacts downstream. The workflow may
be parked for operator inspection or moved to a fail-closed terminal state, but it
must not relaunch the same step automatically.

### Sanitized operator projection

Operator-facing projections may contain:

- workflow id and status;
- step ids, statuses, role keys, retry counts, and gate status;
- artifact refs/digests/counts;
- stable error codes;
- cancellation WATCH marker;
- evidence packet ref.

They must not contain raw prompts, raw model output, raw tool output, exception
strings, process ids, platform ids, card JSON, message ids, credentials, webhook
material, signed URLs, or raw artifact bodies.

### Evidence packet

A terminal WP4 run should produce a deterministic sanitized evidence packet with:

- workflow spec digest and version;
- ordered state-transition list;
- per-step idempotency fingerprints;
- role binding refs/digests;
- gate decisions and operator refs;
- artifact refs/digests only;
- retry and compensation summary;
- cancellation/abort summary, including active-run WATCH if applicable;
- final verdict: `succeeded`, `failed`, `cancelled`, `parked`, or
  `ambiguous_fail_closed`.

## Future implementation guidance only

The later implementation PR may introduce files like these, but this design gate
does not create them:

```text
sachima_supervisor/activity_ai_flow_orchestration.py
sachima_supervisor/ai_flow_artifacts.py
sachima_supervisor/ai_flow_gates.py
tests/sachima_supervisor/test_ai_flow_orchestration.py
scripts/sachima_ai_flow_local_smoke.py
```

Likely test matrix for the later implementation:

- graph schema accepts a valid bounded linear read-only flow;
- rejects cycles, dynamic successors, duplicate step ids, missing role bindings,
  and too many steps;
- rejects write/execute/terminal/fetch/network-runner capabilities;
- pre-step gate missing -> no supervisor call;
- post-step gate missing -> artifact not propagated;
- claim-check digest mismatch -> integrity failure;
- idempotent replay -> no duplicate step launch;
- concurrent step claim -> exactly one wins;
- bounded retry only for retryable seam failures;
- between-step cancel deterministic;
- active-run cancel not confirmed -> indeterminate WATCH and no artifact
  propagation;
- evidence packet contains refs/digests/codes only, not raw material.

## Acceptance criteria for the later WP4 implementation gate

A later WP4 implementation may be accepted only when all are true:

1. local/offline only;
2. read-only roles only;
3. bounded step count, retry count, runtime, and artifact size;
4. no auto-routing or AI-selected successor step;
5. operator gates fail closed;
6. per-step CAS and idempotency prevent duplicate launches;
7. claim-check artifact integrity is verified at every handoff;
8. failure taxonomy maps unknown/ambiguous cases to fail-closed terminal states;
9. WP3b active-run cancellation caveat is preserved;
10. sanitized evidence packet proves the flow without raw material leakage;
11. no Gateway/Feishu/live/public ingress/production config/real delivery;
12. Codex primary blocker review returns `BLOCKERS: None` before merge.

## Verification gates for this docs-only design PR

- `git diff --check`
- YAML parse of this gate's manifest
- docs/status stale-phrase scan for WP3b overclaim and implementation approval
- forbidden implementation-surface scan on changed files
- Codex primary blocker review on the docs-only design diff

## Closure rule

This design packet only makes WP4 implementation **eligible to request** after
review and merge. It does not authorize any source implementation, real smoke,
workflow execution, write role, durable-runtime change, or live delivery axis.
