# WP4 — Controlled AI FLOW local/offline implementation-gate architecture packet

Date: 2026-06-17
Status: **Docs-only architecture / implementation-plan packet.** This document is
**not implementation approval** and **not** a workflow-execution request.
Branch: `docs/wp4-controlled-ai-flow-implementation-gate`
Base: `release/sachima` at `187e41ff1ab00ec8c403e3e24e47120ad19595d4`

## 0. What this packet is (and is not)

This packet turns the merged WP4 docs-only design (PR #142) and the gate-preparation
PRD into a precise, reviewable **implementation plan** that the operator can later
approve or reject. It is produced under the operator's approval to *prepare* the WP4
implementation gate.

It is docs-only. It adds **no** source code, **no** tests, **no** scripts. It does not
start a supervisor, `acpx`, `npx`, a workflow, a network call, a Gateway, Feishu,
Temporal, or any service. Authoring this packet grants **none** of the following:

```text
implementation                       real_workflow_execution
additional_acpx_invocation           additional_real_agent_execution
write_capable_roles                  agent_to_agent_auto_routing
worker_auto_routing / @all_fanout    satine_or_hermes_profile_acp_execution
durable_runtime_ownership_change     gateway_involvement_or_mutation
gateway_restart_or_reload            feishu_or_im_delivery
live_or_default_on_behavior          public_ingress
production_config_write              real_delivery
external_temporal_service_or_worker_startup
```

The implementation plan in §8 becomes executable **only** if and when the operator
grants the exact approval phrase in §11. Until then it is a design artifact.

## Authority and inputs reviewed

- `GOAL.md` — Sachima final-product compass and non-negotiable principles.
- `AGENTS.md` — roadmap preflight, worktree, and non-approval rules.
- `docs/roadmap/current-status.md` — current phase, tails, non-approvals, next allowed request.
- `docs/plans/2026-06-17-...-wp4-...-orchestration-design.md` — merged WP4 design (PR #142).
- `docs/plans/2026-06-17-...-wp4-...-orchestration-design-manifest.yaml` — merged design manifest.
- `docs/plans/2026-06-17-...-wp4-...-implementation-gate-prd.md` — gate-preparation PRD (this branch).
- Code read for context only: `sachima_supervisor/activity_controlled_exec.py`,
  `activity_session_lifecycle.py`, `activity_session_real_execution.py`,
  `activity_preflight.py`, `activity_evidence.py`, `__init__.py`;
  `scripts/sachima_phase_e2_persistent_session_smoke.py`; tests under `tests/sachima_supervisor/`.

## Governance position (compact)

- **Current phase:** WP4 controlled AI FLOW *design* merged docs-only (PR #142,
  `bb5e5d9bf707fde7934939cc473544511bd65ffd`). The implementation is a separate, not-yet-granted gate.
- **Next allowed request:** the WP4 local/offline **read-only implementation gate** —
  injected fakes first, no real workflow execution. That is the gate this packet plans.
- **Open tails preserved:** `ROADMAP-NEXT-ARS-CONTROLLED-AI-FLOW` (open); active-run
  cancellation **WATCH** from WP3b (PR #140) — between-step cancel deterministic,
  active-run cancel best-effort/indeterminate; `ROADMAP-WATCH-STATUS-DASHBOARD`;
  `ROADMAP-WATCH-8788` (unrelated default-port watch, untouched here).
- **Is this task allowed?** Yes. The operator approved preparing the gate; a no-code
  architecture/plan packet is in scope. It approves nothing executable.

---

## 1. Recommended module layout

### 1.1 Verdict: split by responsibility, do not put it in one module

The WP4 design sketched three future files (`activity_ai_flow_orchestration.py`,
`ai_flow_artifacts.py`, `ai_flow_gates.py`). The first implementation slice should go
**slightly further** and split along the seven functional requirements, for one concrete
reason grounded in this repo: the two closest predecessors grew large and dense —
`activity_session_lifecycle.py` is **2344 LOC** and `activity_controlled_exec.py` is
**1481 LOC**. A single `activity_workflow.py` that carried spec validation + CAS store +
gates + artifacts + executor seam + evidence would land in that same unreviewable size
class on day one. Splitting keeps each file holdable in one reading and lets a reviewer
reject one FR's module without re-reviewing the others.

Each module owns exactly one FR-area, mirrors an existing single-responsibility module,
and keeps its own boundary validators (the established convention — see §1.3):

| New module (future) | Responsibility | FR | Mirrors existing |
|---|---|---|---|
| `sachima_supervisor/ai_flow_spec.py` | Workflow-spec dataclasses + `validate_workflow_spec()` (graph/bounds/role/contract validation) | FR1 | spec-shaped half of `activity_preflight.py` |
| `sachima_supervisor/ai_flow_artifacts.py` | `ArtifactRef` dataclass + claim-check verify/re-hash | FR3 | sanitization half of `activity_evidence.py` |
| `sachima_supervisor/ai_flow_gates.py` | Gate-decision records + 4 fail-closed gate checks | FR2/FR6 | `_check_operator_gate` family |
| `sachima_supervisor/ai_flow_store.py` | `AiFlowRunStore` lock-guarded CAS over run/step/gate/artifact/cancel records | FR4 | `ControlledLocalExecClaimStore` (`activity_controlled_exec.py:455`) |
| `sachima_supervisor/ai_flow_executor.py` | `StepExecutor` Protocol + injected-fake seam; **no** real runner in slice 1 | FR5 | `SessionWorkOutcome` + binder seam (`activity_session_real_execution.py`) |
| `sachima_supervisor/ai_flow_evidence.py` | Deterministic sanitized evidence projection | FR7 | `activity_evidence.py` builder |
| `sachima_supervisor/activity_ai_flow_orchestration.py` | Public orchestrator API wiring spec→gate→claim→execute→artifact→evidence; cancellation posture | FR2/FR6 | `start_/query_` shape of `activity_controlled_exec.py` |

`scripts/sachima_ai_flow_local_smoke.py` — committed `--self-test` harness only
(injected fakes), mirroring `scripts/sachima_phase_e2_persistent_session_smoke.py`. It
must **not** be runnable against a real agent in slice 1.

### 1.2 Only one existing file is modified: `__init__.py`

Add the new public names to `sachima_supervisor/__init__.py` `__all__`, exactly as every
prior slice did. **Blast radius:** import surface only — no behavior change to any existing
module. **Tests that must stay green:** the full `tests/sachima_supervisor` import path and
`test_supervisor_library.py`/`test_activity*.py` collection. No edits to
`activity_controlled_exec.py`, `activity_session_lifecycle.py`,
`activity_session_real_execution.py`, `activity_preflight.py`, or `activity_evidence.py`
are required or recommended; doing so would inherit their large test suites
(`test_activity_controlled_exec.py` ~69 KB, `test_activity_session_lifecycle.py` ~69 KB,
`test_activity_session_real_execution.py` ~67 KB) as blast radius for no benefit.

### 1.3 Reuse-vs-copy decision (PRD open question 2)

The established convention in this package is that **sanitization primitives are
duplicated per module on purpose** — every one of `activity_controlled_exec.py`,
`activity_session_lifecycle.py`, and `activity_preflight.py` defines its own private
`_is_safe_ref`, `_digest_hex`, `_safe_code`, `_REF_RE`, `_FINGERPRINT_RE`,
`_UNSAFE_MARKERS = ("media_path", "raw_prompt", "prompt_body")`, etc. This avoids a
cross-module dependency tangle where a change to one slice's validator silently alters
another's security boundary.

The WP4 implementation should follow that convention:

- **Copy/adapt (do not import private helpers):** the `_safe_*` / `_is_safe_*` helpers,
  the four regexes, `_UNSAFE_MARKERS`, the `_digest_hex` idiom, and the `_validate_*_projection`
  validate-on-read pattern. Each new module keeps its own copies.
- **Import/reuse (do not re-declare):** the **public** role-binding constants, because they
  must stay in lockstep with the runnable allowlist:
  - `CONTROLLED_EXEC_ROLE_ALLOWLIST` (`activity_controlled_exec.py:119`)
  - `CONTROLLED_EXEC_ROLE_ADAPTER_AGENT` (`:129`)
  - `CONTROLLED_EXEC_FUTURE_ROLE_KEYS` (`:137`) — explicitly **not** runnable
  - `FORBIDDEN_RUNNER_BASENAMES` (`:182`)
  - `verify_pinned_local_acpx_binary` / `PinnedLocalAcpxProvenance` (`:871` / `:856`) —
    referenced only by a **later** real-executor gate, not slice 1.
- **Mirror by structure (do not import):** `ControlledLocalExecClaimStore`'s lock-guarded
  `claim`/`finalize` CAS — re-implement the same shape in `AiFlowRunStore` for step-level
  claims (§3). Importing the controlled-exec store would couple workflow steps to the
  one-shot exec record schema.

---

## 2. Public data structures and function seams

All inputs are **claim-check refs, digests, and caller-owned ids** — never raw
prompt/context, platform ids, role JSON bodies, or arbitrary paths. All request dataclasses
are `@dataclass(frozen=True)` with `enabled: bool = False` and `approval_token: str = ""`
so the slice is **default-off by construction**, exactly like
`ControlledLocalExecRequest` (`activity_controlled_exec.py:298`) and the session requests
(`activity_session_lifecycle.py:337`).

The shapes below are **seam definitions for review**, not implementations. Bodies are
intentionally omitted; logic is specified by the FRs and tests in §8.

### 2.1 Spec types (`ai_flow_spec.py`)

```text
SCHEMA_VERSION = "sachima.ai_flow.local.v1"

RoleBinding(frozen):          logical_role: str
                              role_key: str                      # must be in CONTROLLED_EXEC_ROLE_ALLOWLIST
                              capabilities: tuple[str, ...]       # subset of ("read", "search")

StepSpec(frozen):             step_id: str
                              logical_role: str
                              input_refs: tuple[str, ...]
                              output_contract: str                # artifact_kind the step must produce
                              depends_on: tuple[str, ...]

WorkflowBounds(frozen):       max_steps: int
                              max_retries_per_step: int
                              max_artifact_bytes: int
                              max_runtime_seconds: int

WorkflowSpec(frozen):         schema_version: str
                              workflow_id: str
                              approval_ref: str
                              bounds: WorkflowBounds
                              roles: tuple[RoleBinding, ...]
                              steps: tuple[StepSpec, ...]
                              edges: tuple[tuple[str, str], ...]  # (from_step_id, to_step_id)

validate_workflow_spec(raw: Mapping[str, Any]) -> WorkflowSpec     # raises AiFlowSpecError, fail-closed
workflow_spec_digest(spec: WorkflowSpec) -> str                    # sha256 over canonical projection
role_binding_digest(spec: WorkflowSpec) -> str
```

### 2.2 Orchestration request/result types (`activity_ai_flow_orchestration.py`)

```text
WorkflowRunRequest(frozen):   run_id, workflow_id, workflow_spec_digest,
                              transaction_ref, operation_ref, idempotency_key,
                              admission_gate_ref: str | None,
                              approval_token: str = "", enabled: bool = False,
                              operator_gate: bool = False,
                              lease_id, lease_epoch=0, lease_holder_ref,
                              expected_state_version: int = 0

StepAttemptRequest(frozen):   run_id, step_id, attempt_index: int,
                              workflow_spec_digest, role_binding_digest,
                              input_artifact_digests: tuple[str, ...],
                              pre_step_gate_ref: str | None,
                              transaction_ref, operation_ref, idempotency_key,
                              approval_token: str = "", enabled: bool = False,
                              operator_gate: bool = False,
                              lease_id, lease_epoch=0, lease_holder_ref,
                              expected_state_version: int = 0

WorkflowCancellationRequest(frozen):  cancel_id, run_id, step_id: str | None,
                              scope: str,                          # "between_step" | "active_run"
                              transaction_ref, operation_ref, idempotency_key,
                              reason_code: str | None,
                              approval_token: str = "", enabled: bool = False,
                              operator_gate: bool = False, lease fields...

WorkflowRunResult / StepRecordResult / CancellationRecordResult / GateDecisionResult
      # read-only property views over a validated _state dict + to_durable_state()
      # exactly the ControlledLocalExecResult / _RecordResult pattern
      # (activity_controlled_exec.py:330, activity_session_lifecycle.py:468)
```

Public orchestrator functions (all keyword-only store/executor injection):

```text
create_workflow_run(request, *, spec, store) -> WorkflowRunResult
step_workflow_run(request, *, spec, store, executor) -> StepRecordResult
query_workflow_run(store, *, run_id) -> WorkflowRunResult
list_workflow_steps(store, *, run_id) -> tuple[StepRecordResult, ...]
request_workflow_cancellation(request, *, store) -> CancellationRecordResult
summarize_workflow_run(store, *, run_id) -> WorkflowEvidence      # sanitized, deterministic
```

### 2.3 Executor seam (`ai_flow_executor.py`) — injected fakes first

Mirror `SessionWorkOutcome` (`activity_session_lifecycle.py:318`) and
`SessionInterruptOutcome` (`:437`) so the orchestrator is identical whether the executor
is a test fake or, in a **later** gate, a real binder.

```text
StepExecutionOutcome(frozen):  ok: bool
                               step_status: str | None            # "completed" | "failed_*" | "indeterminate"
                               artifact_refs: tuple[Mapping, ...]  # sanitized ArtifactRef projections
                               evidence_ref: str | None
                               evidence_digest: str | None
                               error_code: str | None
                               retryable: bool = False
                               # cancellation/interrupt channel (WP3b WATCH-aligned):
                               interrupted: bool = False
                               cleanup_verified: bool = False
                               ambiguous: bool = False

class StepExecutor(Protocol):
    def execute(self, request: StepAttemptRequest, *, role_binding: RoleBinding,
                resolved_inputs: tuple[Mapping, ...]) -> StepExecutionOutcome: ...
```

Slice 1 ships **only** the Protocol and the test-side fakes. A real `StepExecutor` that
binds `start_controlled_local_exec` is a separately approved later gate; the orchestrator
never imports a real runner in slice 1.

### 2.4 Artifact + gate + evidence types

```text
# ai_flow_artifacts.py
ArtifactRef(frozen):          artifact_id, producer_step_id,
                              content_digest: str,                # "sha256:<64 hex>"
                              artifact_kind: str, byte_count: int, created_at_ref: str
verify_artifact_ref(ref, *, expected_kind, expected_producer, max_bytes) -> ArtifactRef   # fail-closed re-hash check

# ai_flow_gates.py
GateDecision(frozen):         gate_type: str,                     # "admission"|"pre_step"|"post_step"|"terminal"
                              gate_ref: str | None, status: str,  # "granted"|"missing"|"mismatch"|"ambiguous"
                              step_id: str | None
check_gate(gate_type, *, request) -> GateDecision                 # fail-closed; never auto-grant

# ai_flow_evidence.py
WorkflowEvidence  # read-only view, .to_durable_state(); sanitized fields only (see §5.3)
```

---

## 3. Store / CAS / idempotency strategy

### 3.1 Mirror the approved first-slice CAS exactly

Slice 1 uses a **caller-owned, in-process, lock-guarded** store — the approved first-slice
shape, not a cross-process durable store (that remains a later, separately approved gate,
as called out at `activity_controlled_exec.py:466`). `AiFlowRunStore` is a `@dataclass`
that re-implements the `ControlledLocalExecClaimStore` contract
(`activity_controlled_exec.py:455`) at **step granularity**:

```text
AiFlowRunStore(@dataclass):
    _runs:        dict[run_id, dict]                      # validated run records
    _by_step_idem: dict[idempotency_key, (fingerprint, dict)]   # step claims
    _steps:       dict[(run_id, step_id), dict]
    _gates:       dict[(run_id, gate_type, step_id|None), dict]
    _artifacts:   dict[artifact_id, dict]
    _cancels:     dict[cancel_id, dict]
    _lock:        threading.RLock                          # reentrant, like the claim store

    get_run / get_step / get_step_idempotent                      # validate-on-read every time
    claim_step(*, run_id, step_id, idempotency_key, fingerprint, state) -> (disposition, state)
    finalize_step(*, run_id, step_id, idempotency_key, fingerprint, state) -> None
    record_gate / record_artifact / record_cancellation           # CAS over version/epoch
```

`claim_step` is the single atomic pre-execute boundary, byte-for-byte in spirit with
`ControlledLocalExecClaimStore.claim` (`:495`):

- whole read→check→write sequence holds `self._lock`;
- identical fingerprint already resident → return `("replayed", state)`, **no executor call**;
- same idempotency key, different fingerprint → `AiFlowError("activity_idempotency_conflict")`, fail closed;
- same `(run_id, step_id)` already claimed under a different key → `"activity_claim_conflict"`, fail closed;
- resident state is revalidated via `_validate_step_projection` on **every** read so hostile
  resident material can never be projected (mirror `:481`/`:493`).

`finalize_step` transitions `claimed_in_progress` → terminal under the same mutex, matching
fingerprint + activity binding (mirror `:545`).

### 3.2 Step idempotency fingerprint (FR4 — exact binding)

Mirror `_fingerprint` (`activity_controlled_exec.py:943`): a `_digest_hex` over a fixed
payload. The payload binds **exactly** the FR4 set, no more, no less:

```text
_step_fingerprint payload = {
    "run_id":                request.run_id,
    "step_id":               request.step_id,
    "workflow_spec_digest":  request.workflow_spec_digest,
    "role_binding_digest":   request.role_binding_digest,
    "input_artifact_digests": list(request.input_artifact_digests),
    "approval_ref":          request.pre_step_gate_ref or _APPROVAL_REF,
    "attempt_index":         request.attempt_index,
}
```

Two attempts that differ in any bound field are different claims; identical replay returns
the resident projection with no second executor call. Run-creation has its own
`_run_fingerprint` over `(run_id, workflow_spec_digest, approval_ref, admission_gate_ref)`.

### 3.3 Concurrency proof obligation

Like the Phase C slice (which added true-concurrency claim/CAS tests), slice 1 must prove
with **real threads** that N concurrent identical `step_workflow_run` calls produce exactly
one executor invocation and one terminal record, and that N concurrent conflicting calls
yield exactly one winner with the rest failing closed pre-execute. A test that asserts "the
fake executor's call counter == 1" after a thread barrier is the canonical proof.

### 3.4 State types and view refs

Durable record `type` fields follow the established `sachima.supervisor.<thing>.v1`
convention:

```text
sachima.supervisor.ai_flow_run_record.v1
sachima.supervisor.ai_flow_step_record.v1
sachima.supervisor.ai_flow_gate_record.v1
sachima.supervisor.ai_flow_artifact_ref.v1
sachima.supervisor.ai_flow_cancel_record.v1
sachima.supervisor.ai_flow_evidence.v1
```

View-model refs are `<prefix>_<digest[:16]>` (mirror `_VIEW_MODEL_REF_PREFIX` usage at
`activity_controlled_exec.py:1011`).

---

## 4. Workflow spec validation strategy (FR1)

`validate_workflow_spec(raw: Mapping[str, Any]) -> WorkflowSpec` is fail-closed and
**exact-typed**. It rejects hostile container subclasses the way `_check_material` does
(`type(request.context_refs) is not tuple`, `activity_controlled_exec.py:624`). Concretely,
validation rejects before any run can be created when:

1. **Type/shape:** `schema_version != "sachima.ai_flow.local.v1"`; any field whose exact
   type is wrong (`type(x) is not dict/list/str/int`); `str`/`dict`/`list`/mapping
   subclasses where exact primitives are required.
2. **Ids:** any `workflow_id`/`step_id`/`role_key`/`*_ref` failing the safe-ref regex
   (`^[a-z][a-z0-9_.:-]{0,127}$`, mirror `_REF_RE`).
3. **Bounds:** non-positive or over-ceiling `max_steps`, `max_retries_per_step`,
   `max_artifact_bytes`, `max_runtime_seconds`; `len(steps) > bounds.max_steps`.
4. **Graph contract:** duplicate `step_id`; an edge endpoint not in `steps`; a cycle
   (topological sort fails); a step whose `depends_on` is not covered by inbound edges;
   **any** node with out-degree implying fan-out beyond the slice-1 linear shape; an
   `edges` set that is not derivable from declared dependencies (no implicit/dynamic edges).
5. **Roles:** a `logical_role` used by a step but not declared in `roles`; a `role_key` not
   in `CONTROLLED_EXEC_ROLE_ALLOWLIST`; a `role_key` in `CONTROLLED_EXEC_FUTURE_ROLE_KEYS`
   (documented-but-not-runnable) → fail closed; any `capabilities` value outside
   `("read", "search")` → capability/security failure (terminal, non-retryable).
6. **Contracts:** a step with empty `output_contract`; an `input_refs` entry that names no
   upstream `output_contract` and no declared workflow input.

The first accepted shape is the design's bounded linear flow
`architect → programmer_candidate(read-only) → reviewer`, all bound to read-only role keys
(`sachima.claude.read_only_reviewer`, `sachima.codex.primary_reviewer`). A DAG generalization
is explicitly deferred; slice 1 rejects anything that is not a bounded acyclic linear/tree
graph with statically declared edges.

**No model output ever influences validation or successor choice** — the graph is fixed
before any step runs, and `step_workflow_run` only schedules a step whose predecessors'
output refs are present, verified, and post-step-gated.

---

## 5. Artifact claim-check and sanitized evidence strategy

### 5.1 Claim-check passing (FR3)

Step outputs live in an **out-of-band, caller-owned, local/offline** artifact store.
Durable workflow state stores only the `ArtifactRef` projection — `artifact_id`,
`producer_step_id`, `content_digest` (`sha256:<hex>`), `artifact_kind`, `byte_count`,
`created_at_ref`. Raw bodies never enter the run/step/gate/evidence records.

`verify_artifact_ref(...)` is called at **every** handoff before a downstream step is
scheduled and re-checks: digest format, `byte_count <= bounds.max_artifact_bytes`,
`artifact_kind == expected output_contract`, `producer_step_id == declared producer`, and a
re-hash match against the resolved body. Digest mismatch, missing artifact, wrong producer,
wrong kind, or oversized material is **non-retryable, fail-closed** (integrity marker), and
the artifact is **not** propagated.

### 5.2 Validate-on-read sanitization (FR3 + NFRs)

Every record carries a fixed key allowlist (`_AI_FLOW_*_STATE_KEYS`, mirror
`_CLAIM_STATE_KEYS` at `activity_controlled_exec.py:252`) and a `_validate_*_projection`
that runs on **every** store read and rejects:

- any string failing `_state_string_is_safe`;
- any `_UNSAFE_MARKERS` substring (`media_path`, `raw_prompt`, `prompt_body`) — plus WP4
  additions `card_json`, `signed_url`, `tool_output`;
- a stable error code outside the allowed set (mirror `_STORED_ERROR_CODES`,
  `activity_session_lifecycle.py:177`);
- a ref/fingerprint/digest failing its regex.

### 5.3 Sanitized evidence packet (FR7)

`summarize_workflow_run` returns a deterministic `WorkflowEvidence` containing **only**:
workflow spec digest + `schema_version`; ordered state-transition list; per-step idempotency
fingerprints; role-binding refs/digests; gate decisions by safe ref/status; artifact
refs/digests/counts/kinds; retry + compensation summary; cancellation/abort summary
including the **active-run WATCH marker** when applicable; stable error codes; explicit
non-approval flags; and a `final_verdict` ∈ `{succeeded, failed, cancelled, parked,
ambiguous_fail_closed}`.

It must **never** contain raw prompts, raw/model/tool output, exception strings, process
ids, platform ids, card JSON, message ids, credentials, webhook material, signed URLs, or
raw artifact bodies. The evidence builder mirrors `activity_evidence.py`'s deterministic
fixture approach and is provable leak-free with `_walk_strings` (`activity_evidence.py:82`).

---

## 6. Operator gate model (FR2)

Four gate types, all fail-closed, mirroring `_check_operator_gate`
(`activity_controlled_exec.py:675`, `activity_session_lifecycle.py:629`) where the boolean
must be **exactly** `True` and the approval token must match exactly:

| Gate | Enforced in | Fails closed when | Effect of failure |
|---|---|---|---|
| **Admission** | `create_workflow_run` | `enabled is not True`, `approval_token != AI_FLOW_APPROVAL_TOKEN`, `operator_gate is not True`, or `admission_gate_ref` missing/malformed | run not created |
| **Pre-step** | `step_workflow_run`, **before** `executor.execute` | `operator_gate is not True` or `pre_step_gate_ref` missing/mismatched/expired/ambiguous | **no executor call**; step recorded as gate-blocked |
| **Post-step** | after executor returns, before propagation | post-step gate missing/ambiguous for the produced artifact | artifact **not propagated**; downstream not scheduled |
| **Terminal** | `summarize_workflow_run` finalization | terminal gate missing | run parked, not accepted |

Each decision is persisted as a sanitized `GateDecision` record. Missing/expired/mismatched/
ambiguous material always halts; the workflow **never auto-continues**. There is no
auto-routing and no AI-selected successor at any gate.

---

## 7. Cancellation model preserving WP3b active-run WATCH (FR6)

WP4 distinguishes two cancellation levels and must **not** overclaim interruption.

### 7.1 Between-step cancellation — deterministic

When no step is mid-execution, `request_workflow_cancellation(scope="between_step")` is
fully deterministic at the **scheduler** level: it sets the run to a terminal `cancelled`
state, stops scheduling future steps, parks/releases pending step claims, marks
unpropagated artifacts `orphaned/unused` (read-only compensation bookkeeping — never a file
rollback, since write roles are unapproved), and produces a sanitized terminal projection.
This requires no active-run interruption and carries no WATCH.

### 7.2 Active-run cancellation — best-effort, inherits the WP3b WATCH

If a cancellation arrives while a step is in-flight, WP4 reuses the WP3b/WP3a outcome
semantics rather than inventing new ones. The executor's `StepExecutionOutcome` exposes
`interrupted` / `cleanup_verified` / `ambiguous`, mirroring `SessionInterruptOutcome`
(`activity_session_lifecycle.py:437`). The orchestrator records:

- `cancelled` **only** when `interrupted is True and cleanup_verified is True`
  (the exact rule at `activity_session_real_execution.py:778`);
- `cancel_ambiguous` / `active_run_cancellation_watch` when the executor raises, reports
  `ambiguous`, or reports `interrupted=False` without verified cleanup — i.e. the
  `cancel_not_confirmed` posture (`:786`);
- in the WATCH case: **no artifact propagation**, **no automatic relaunch** of the step, and
  the run is parked for operator inspection or moved to `ambiguous_fail_closed`.

Slice 1 uses injected fakes only, so no real interruption occurs; the fake simulates both a
verified-safe-interrupt branch and an unconfirmed branch so both code paths are tested. The
real WP3b bridge (`execute_real_cancellation`, `activity_session_real_execution.py:686`)
stays fail-closed and is **not** wired into WP4 in this slice — its public entrypoint still
raises, and only the lifecycle-guarded `_BoundRealCancellation` path (`:735`) can reach a
real abort, which WP4 does not register.

The evidence packet always surfaces the active-run WATCH marker when it applied, so the
WP3b caveat is never silently dropped.

---

## 8. TDD task breakdown (executable only after §11 approval)

> **For future implementers:** REQUIRED SUB-SKILL once approved — use
> `superpowers:subagent-driven-development` or `superpowers:executing-plans`, one task =
> one RED→GREEN→commit cycle. Injected fakes only; **no** real `acpx`/`npx`/agent/network/
> Gateway/Feishu/Temporal in any task. The code blocks below are **test intents and seam
> signatures for review**, not source to paste — implementation bodies are written test-first
> by the implementer.

**Global constraints (every task):** local/offline; default-off (`enabled=False`,
`approval_token=""` defaults); exact-type validation, reject hostile `str`/`dict`/`list`/
mapping subclasses; no shell interpolation; no raw exception text in durable/user-visible
state; read-only role keys only; forbidden-surface scan must pass.

**Verification commands (used throughout — repo conventions):**

```bash
# focused module run (probes .venv then venv then shared venv)
scripts/run_tests.sh tests/sachima_supervisor/test_ai_flow_spec.py -q
# single test
scripts/run_tests.sh tests/sachima_supervisor/test_ai_flow_orchestration.py::test_name -v
# full relevant suite (must stay green)
scripts/run_tests.sh tests/sachima_supervisor -q
# lint + bytecode + whitespace on touched files
ruff check sachima_supervisor/ai_flow_*.py sachima_supervisor/activity_ai_flow_orchestration.py scripts/sachima_ai_flow_local_smoke.py
python3 -m compileall sachima_supervisor/ai_flow_spec.py sachima_supervisor/ai_flow_store.py sachima_supervisor/ai_flow_gates.py sachima_supervisor/ai_flow_artifacts.py sachima_supervisor/ai_flow_executor.py sachima_supervisor/ai_flow_evidence.py sachima_supervisor/activity_ai_flow_orchestration.py
git diff --check
```

### Task T1 — Spec validation (FR1)

- **Create:** `sachima_supervisor/ai_flow_spec.py` · **Test:** `tests/sachima_supervisor/test_ai_flow_spec.py`
- **Produces:** `WorkflowSpec`, `validate_workflow_spec`, `workflow_spec_digest`, `role_binding_digest`, `SCHEMA_VERSION`, `AiFlowSpecError`.
- RED tests (one assertion family each): accepts the canonical bounded linear read-only flow;
  rejects wrong `schema_version`; rejects cycle; rejects duplicate `step_id`; rejects edge to
  unknown node; rejects `len(steps) > max_steps`; rejects fan-out beyond linear; rejects
  missing role binding; rejects `role_key` not in allowlist; rejects future role key; rejects
  capability outside `("read","search")`; rejects `str`/`dict` subclass inputs.
- Verify: `scripts/run_tests.sh tests/sachima_supervisor/test_ai_flow_spec.py -q` → all pass; RED first proves each raises `AiFlowSpecError`.

### Task T2 — Artifact claim-check (FR3)

- **Create:** `sachima_supervisor/ai_flow_artifacts.py` · **Test:** `test_ai_flow_artifacts.py`
- **Consumes:** `WorkflowBounds`. **Produces:** `ArtifactRef`, `verify_artifact_ref`.
- RED tests: accepts a valid ref + re-hash; rejects digest-format error; rejects oversized
  `byte_count`; rejects wrong `artifact_kind`; rejects wrong `producer_step_id`; rejects
  re-hash mismatch; `_walk_strings` over the ref projection contains no `_UNSAFE_MARKERS`.

### Task T3 — Gate model (FR2)

- **Create:** `sachima_supervisor/ai_flow_gates.py` · **Test:** `test_ai_flow_gates.py`
- **Produces:** `GateDecision`, `check_gate`.
- RED tests: each gate type grants on exact `operator_gate=True` + matching ref; fails closed
  on `operator_gate` not `True`; fails closed on missing/mismatched/ambiguous ref; decision
  record is sanitized.

### Task T4 — CAS step store (FR4)

- **Create:** `sachima_supervisor/ai_flow_store.py` · **Test:** `test_ai_flow_store.py`
- **Produces:** `AiFlowRunStore` with `claim_step`/`finalize_step`/`get_*`, `_step_fingerprint`,
  `_validate_*_projection`.
- RED tests: fresh claim → `"acquired"`; identical replay → `"replayed"`, counter unchanged;
  same key/different fingerprint → `activity_idempotency_conflict`; same `(run_id,step_id)`/
  different key → `activity_claim_conflict`; resident unsafe state rejected on read;
  **threaded** concurrency: N identical claims → exactly one acquisition (mirror Phase C
  true-concurrency tests).

### Task T5 — Executor seam + fakes (FR5)

- **Create:** `sachima_supervisor/ai_flow_executor.py` · **Test:** `test_ai_flow_executor.py`
- **Produces:** `StepExecutionOutcome`, `StepExecutor` Protocol; test-side `FakeStepExecutor`
  (configurable: success-with-artifact, retryable failure, terminal failure, interrupted+clean,
  interrupted-unconfirmed).
- RED tests: a clean subprocess import of `ai_flow_executor` (and the orchestrator) **never**
  transitively imports `subprocess`, `socket`, `acpx`, `npx`, or a real runner (mirror the
  import-isolation test at `tests/sachima_supervisor/test_activity_session_real_execution.py:561`).

### Task T6 — Evidence projection (FR7)

- **Create:** `sachima_supervisor/ai_flow_evidence.py` · **Test:** `test_ai_flow_evidence.py`
- **Produces:** `WorkflowEvidence`, `summarize` helper.
- RED tests: evidence contains refs/digests/codes only; `_walk_strings` finds no forbidden
  markers; deterministic for identical input; carries non-approval flags and (when set) the
  active-run WATCH marker; `final_verdict` ∈ the allowed set.

### Task T7 — Orchestrator happy path + replay (FR2/FR4/FR5)

- **Create:** `sachima_supervisor/activity_ai_flow_orchestration.py` · **Test:** `test_ai_flow_orchestration.py`
- **Consumes:** T1–T6. **Produces:** `create_workflow_run`, `step_workflow_run`,
  `query_workflow_run`, `list_workflow_steps`, `request_workflow_cancellation`,
  `summarize_workflow_run`, `AI_FLOW_APPROVAL_TOKEN`.
- RED tests: end-to-end with `FakeStepExecutor` over the 3-step linear flow → `succeeded`,
  exactly 3 executor calls; admission gate missing → run not created; pre-step gate missing →
  **zero** executor calls; post-step gate missing → artifact not propagated, downstream not
  scheduled; idempotent replay of a step → no second executor call; conflicting replay → fail
  closed pre-execute.

### Task T8 — Cancellation posture incl. WP3b WATCH (FR6)

- **Modify:** `test_ai_flow_orchestration.py` (add cancellation cases).
- RED tests: between-step cancel → deterministic terminal `cancelled`, no executor relaunch;
  active-run cancel with `interrupted=True, cleanup_verified=True` → `cancelled`; active-run
  cancel unconfirmed/ambiguous/raising → `active_run_cancellation_watch`/`cancel_ambiguous`,
  **no** artifact propagation, **no** relaunch, evidence surfaces the WATCH marker.

### Task T9 — Self-test smoke + public exports + scans

- **Create:** `scripts/sachima_ai_flow_local_smoke.py` (mirror
  `scripts/sachima_phase_e2_persistent_session_smoke.py`: `--self-test` injected-fakes only,
  post-verify counts, **no** real run). **Modify:** `sachima_supervisor/__init__.py` (`__all__`).
- RED/verify: `python3 scripts/sachima_ai_flow_local_smoke.py --self-test` exits 0 with a
  sanitized summary; `from sachima_supervisor import create_workflow_run, ...` resolves; full
  `scripts/run_tests.sh tests/sachima_supervisor -q` green; §9 scans clean.

### Self-review (writing-plans discipline)

After T1–T9, re-read the PRD FR1–FR7 and design acceptance criteria 1–12; confirm each maps
to a named task and test; confirm type/name consistency (e.g. `step_status` not `status` in
the executor outcome; `workflow_spec_digest` spelled identically in spec, request, fingerprint,
and evidence). Fix inline.

---

## 9. Forbidden surfaces and static scans (acceptance gate 8)

Two scan layers, both required before the implementation PR is review-ready.

### 9.1 Behavioral no-leak (runtime)

`_walk_strings(payload)` over **every** durable record, query projection, and the evidence
packet; assert none of these substrings appear (mirror
`tests/sachima_supervisor/test_activity_controlled_dry_run_evidence.py:35` and
`_assert_no_leaks` at `test_activity_session_real_execution.py:427`):

```text
raw_prompt  prompt_body  media_path  card_json  signed_url  tool_output
<credentials/token markers>  <platform-id markers>  <process-id markers>  <exception-text markers>
```

### 9.2 Source/diff forbidden-surface scan (static)

Scan the new/changed source the way the existing suites scan themselves
(`REPO_ROOT.read_text()` token + statement asserts, e.g.
`test_activity_durable_state_preflight.py:475`). Descriptor-only **prose** in docs is allowed;
**source imports/calls** are blockers. Forbidden in slice-1 source:

```text
acpx   npx   subprocess  socket  requests/httpx/urllib  asyncio network
Gateway/feishu/platform adapter imports   Temporal worker/service startup
Docker/systemctl   production config writes   public ingress/webhook
real send_message/delivery   os.system/exec*   shell=True
```

Command sketch (run on changed files only):

```bash
git diff --name-only release/sachima... -- 'sachima_supervisor/ai_flow_*.py' \
  'sachima_supervisor/activity_ai_flow_orchestration.py' 'scripts/sachima_ai_flow_local_smoke.py' \
  | xargs grep -nE '\b(acpx|npx|subprocess|socket|systemctl|docker|shell=True|os\.system)\b' && echo "BLOCKER: forbidden surface" || echo "scan clean"
```

### 9.3 Other required gates (from PRD §"Acceptance gates")

`ruff check` on touched files · `python3 -m compileall` on touched modules ·
`git diff --check` · changed-file allowlist proving **no** Gateway/Feishu/platform/production
config/live changes · secret/static scan over changed lines and new files · Codex primary
repo-aware blocker review after PR+CI exist · post-merge verification + **compact** status
update if merged.

---

## 10. Open risks and blocker questions

Phrased as constraints + the test that retires each, not as fear-language.

| # | Risk / question | Constraint that contains it | Retiring test / decision |
|---|---|---|---|
| R1 | In-process store is not crash-durable | Slice 1 is explicitly the approved in-process CAS shape; cross-process durable store is a later gate (`activity_controlled_exec.py:466`) | Documented non-goal; T4 proves CAS correctness in-process |
| R2 | Active-run cancellation could be overclaimed | `cancelled` only on `interrupted and cleanup_verified`; else WATCH; no real bridge wired | T8 asserts both branches + WATCH marker |
| R3 | Artifact body could leak via refs | Claim-check only; validate-on-read; `_walk_strings` scans | T2/T6 + §9.1 |
| R4 | Hostile spec/container subclasses | Exact-type checks (`type(x) is not ...`) | T1 subclass-rejection tests |
| R5 | Module fan-out increases review surface | 7 focused modules, each ≤ one FR, one test file each | reviewer-per-module; justified in §1.1 |
| R6 | Reusing private helpers across modules creates tangles | Copy sanitizers per module; import only public role constants | §1.3 decision |
| **Q1 (operator)** | Should slice 1 include **any** real workflow smoke? | Default recommendation: **injected fakes only, real smoke later** | Operator decides at §11; if yes, a **second** explicit clause with exact runner/role/step-count/evidence-root/one-run rules |
| **Q2 (operator)** | Is the 7-module split acceptable vs the design's 3 files? | Either works; split recommended for reviewability | Operator/Codex confirm at review |
| **Q3 (architecture)** | Artifact store backend for slice 1 | Caller-owned in-memory/tempdir, local/offline, byte-bounded | Confirm in implementation PR; no network/object-store |

No item in this table is a **blocker to the implementation gate itself**; R1–R6 are bounded
by design, and Q1–Q3 are operator/review confirmations, not unknowns.

---

## 11. Recommended exact implementation approval phrase

The implementation plan in §8 is **not approved by this packet**. If the operator chooses to
proceed, the recommended exact phrase (the PRD's, which is stricter than the design doc's and
adds `injected_fakes_first` / `no_real_workflow_execution` / `no_additional_acpx_invocation`)
is:

```text
approve_agent_run_supervisor_sachima_controlled_ai_flow_local_offline_orchestration_implementation_read_only_roles_only_bounded_steps_injected_fakes_first_no_real_workflow_execution_no_additional_acpx_invocation_no_write_roles_no_auto_routing_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

A real local workflow smoke remains **out of scope** of this phrase. If wanted, it must be a
**separate second clause** naming the exact runner, role, step count, evidence root, and
one-run/no-replay rules — consistent with how Phase D / E-2 / WP1b real smokes were each
gated separately. Default recommendation: **implementation first with injected fakes only;
real smoke later.**

---

## Status governance (compact — no broad churn)

If the §8 implementation later lands, update status **compactly**, consistent with the
"safety evidence over status churn" rule in `current-status.md`:

- one WP4-implementation row in the phase map;
- close/append `ROADMAP-NEXT-ARS-CONTROLLED-AI-FLOW` with the merge evidence;
- preserve (do **not** close) the active-run cancellation **WATCH**;
- one dev log + one manifest; PR body and manifest point to the same evidence rather than
  repeating long synonym blocks.

This architecture packet itself changes **no** roadmap state; it is a planning artifact on a
preparation branch.

## Document control

- **Adds:** this file only — `docs/plans/2026-06-17-agent-run-supervisor-sachima-wp4-controlled-ai-flow-local-offline-implementation-gate-architecture.md`.
- **Source/tests/scripts changed:** none.
- **Approvals granted:** none. Live / Gateway / Feishu / production config / real delivery
  remain explicitly non-approved.
