# P6 Controlled AI FLOW execution — No-code technical solution

## 0. Status and non-approval boundary

Docs-only design. No code, no runtime, no Temporal service/Worker, no workflow/activity execution, no acpx/npx/Claude/Codex nested runner, no Gateway/Feishu, no production config, no service restart, no delivery. Everything below is a proposal for a **later, separately approved** P6-A implementation PR. WP3b active-run cancellation stays WATCH. Digests are evidence, not trust. Gateway/Feishu/platform/delivery stay closed.

## 1. Architecture verdict

**Sufficient — build P6-A as a thin, default-off composition + admission module plus a hermetic-local end-to-end proof. Do not build a new bridge/adapter.**

Rationale: `P5TemporalStepExecutor.execute(self, request, *, role_binding, resolved_inputs) -> StepExecutionOutcome` is already the WP4 `StepExecutor` Protocol, and `step_workflow_run(..., executor=…)` already accepts an injected executor. `P5LocalOfflineRuntimeAdapter` already proves a StepExecutor drives the WP4 orchestrator end-to-end. Therefore the minimal behavior-bearing path (open Q1) is: **inject the Temporal executor into the unmodified WP4 entrypoints behind a new p6_* default-off admission, run it through a real hermetic-local Temporal Worker, and assert no-leak + WATCH across all three surfaces.** Answer to open Q2: a **new narrow production-shaped P6-A module** that reuses `activity_ai_flow_orchestration` unmodified — not a wrapper that mutates WP4, not a throwaway test harness.

## 2. Traceability matrix (FR → future files → future tests → gates)

| FR | Future file(s) (P6-A) | Future test(s) | Merge gate |
|---|---|---|---|
| FR1 default-off + p6_* token | `sachima_supervisor/p6_controlled_ai_flow.py` (NEW: token, p6_* codes, admission, composition session) | `…/p6_controlled_ai_flow/unit/test_admission.py` | P6 admission gate — **zero Temporal calls when off/mismatched** |
| FR2 reuse WP4, no weakening | reuse (unmodified) `activity_ai_flow_orchestration.py`, `ai_flow_spec.py`, `ai_flow_gates.py`, `ai_flow_artifacts.py`, `ai_flow_evidence.py`, `ai_flow_store.py` | `…/unit/test_no_weakening.py` + reuse `tests/sachima_supervisor/test_ai_flow_orchestration.py` | WP4 conformance/oracle gate |
| FR3 bind WP4→Temporal executor | NEW module injects `P5TemporalStepExecutor`; reuse `p5_temporal/step_executor.py` translation | `…/unit/test_composition_oracle.py`, `…/unit/test_translation_reuse.py` | Composition + translation gate |
| FR4 controlled/fake bodies only | NEW module pins `MODE_CONTROLLED_DETERMINISTIC`; reuse `p5_temporal/workflow.py`, `activity.py` | `…/unit/test_boundary_scan.py` (forbidden-runner) + hermetic body assertion | No-real-runner gate |
| FR5 run/query/dup/divergent/recover/cancel/close | reuse `p5_temporal/{control_surface,runtime_client,workflow}.py`; NEW control-path mapping | `…/hermetic/test_end_to_end_temporal.py`, `…/hermetic/test_dup_divergent_recover_cancel.py` | **Hermetic real-Worker gate (merge-blocking)** |
| FR6 no-leak ×3 surfaces | reuse `contracts.scan_projection_for_leak`(SCAN1)/`scan_bytes_for_leak`(SCAN2) + `ai_flow_evidence._assert_no_leak`; NEW P6 evidence projection | `…/hermetic/test_no_leak_end_to_end.py` (+ canary) | **No-leak gate (merge-blocking)** |
| FR7 Gateway/Feishu/platform closed | NEW boundary test extending `p5_temporal/unit/test_gateway_boundary.py` | `…/unit/test_boundary_scan.py` | **Boundary gate (merge-blocking)** |
| FR8 ops-owned lifecycle constrained | reuse ops-owned `p5_temporal/p5_temporal_worker.py` (hermetic/staging only) | `…/hermetic/*` reuse harness; boundary scan asserts no prod Worker auto-start | Ops-lifecycle gate |
| FR9 visible gate suite | this technical solution §11–§12 | n/a (process) | Governance gate |
| FR10 review packet + approval | this solution §13 + user-review packet | n/a (process) | Handoff gate |

## 3. Proposed implementation surface and changed-file allowlist (later P6-A)

**New (P6-A code):**
- `sachima_supervisor/p6_controlled_ai_flow.py` — the only new production module: `P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN`; p6_* stable codes; an admission/precondition gate; a `P6ControlledAiFlowSession` (or pure functions) composing `create_workflow_run → step_workflow_run(executor=…) → control ops → summarize_workflow_run`; a sanitized P6 evidence projection. (Optional `sachima_supervisor/p6_controlled_ai_flow_evidence.py` only if the projection grows; prefer one module.)

**New (P6-A tests):**
- `tests/sachima_supervisor/p6_controlled_ai_flow/unit/test_admission.py`
- `…/unit/test_no_weakening.py`
- `…/unit/test_composition_oracle.py` (drives WP4 via `P5LocalOfflineRuntimeAdapter` — **no Temporal**)
- `…/unit/test_translation_reuse.py`
- `…/unit/test_control_path.py`
- `…/unit/test_boundary_scan.py`
- `…/hermetic/test_end_to_end_temporal.py`
- `…/hermetic/test_dup_divergent_recover_cancel.py`
- `…/hermetic/test_no_leak_end_to_end.py`
- reuse `tests/sachima_supervisor/p5_temporal/hermetic/test_determinism_replay.py`

**Reused unmodified:** all `sachima_supervisor/ai_flow_*.py`, all `sachima_supervisor/p5_temporal/*` (incl. ops-owned `p5_temporal_worker.py`).

**Changed-file allowlist (P6-A implementation PR), expect empty residue:**
```
git diff --name-only release/sachima...HEAD \
  | rg -v '^(sachima_supervisor/p6_controlled_ai_flow(_evidence)?\.py$|tests/sachima_supervisor/p6_controlled_ai_flow/|docs/)'
```
**Forbidden-surface residue (must be empty):** any diff touching `gateway/`, `*/platforms/*`, Feishu/Lark, production config, `pyproject.toml`/lockfiles (no new deps; `temporalio` already present from P5), or service-lifecycle files.

## 4. Admission / default-off design (FR1)

Outer p6_* admission, evaluated in order **before any executor/Temporal call**, emitting zero Temporal workflow/activity calls on any failure:
1. `enabled is not True` → `p6_execution_disabled`.
2. `approval_token != P6_CONTROLLED_AI_FLOW_EXECUTION_APPROVAL_TOKEN` (exact) → `p6_approval_mismatch`.
3. caller-supplied Temporal control surface / `spec` / `store` missing or malformed, or WP4/P5 tokens absent → `p6_precondition_unmet`.
4. any required WP4 operator gate (`admission/pre_step/post_step/terminal`) not granted → surfaced as `p6_gate_blocked` (composed from WP4 `check_gate`/`STEP_GATE_BLOCKED`).

p6_* **wraps** but never replaces the inner `runtime_*` codes (`runtime_disabled`, `runtime_approval_mismatch`, `runtime_precondition_unmet`, …) emitted by `P5TemporalStepExecutor`; both families appear in evidence. Resolves P1-a. Mirrors the proven default-off shape of `AI_FLOW_APPROVAL_TOKEN` and `P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN` (exact token + explicit `enabled` flag, no new env var).

## 5. WP4 → P5TemporalStepExecutor binding design (FR3)

No new adapter. Wiring (caller/ops, never Gateway):
```
connected Temporal client  (caller-supplied)
  -> P5TemporalRuntimeClient(temporal_client, task_queue=…)
  -> P5TemporalControlSurface(runtime_client)
  -> P5TemporalStepExecutor(control_surface, enabled=True, approval_token=P5_…_TOKEN)
  -> injected as `executor=` into step_workflow_run(request, *, spec, store, executor)
```
- Seam preserved verbatim: `execute(request, *, role_binding, resolved_inputs) -> StepExecutionOutcome`.
- WP4 `request` → P5 `StartRequest` translation is the executor's existing job (covered by `test_step_executor_translation.py`): only sanitized refs/digests/role keys/step ids/run ids/idempotency material cross; raw prompt/context/output/bytes/platform ids/paths/cards/credentials/signed URLs are rejected before any Temporal call. P6-A reuses this and re-asserts it at the composition boundary; WP4's own input re-verification (`_resolve_inputs` + digest match) is the second wall.
- P5→WP4 status mapping never invents success: executor returns `StepExecutionOutcome(ok, step_status, …)`; WP4 records `STEP_COMPLETED` only on verified claim-check output; `cancel_ambiguous`/`active_run_cancellation_watch` flow straight through. Resolves P1-b.
- Deterministic, sanitized `p5wf_<48hex>` workflow id from safe run/step refs (`validate_workflow_id`).

## 6. Query / cancel / recover / close design (FR3/FR5, open Q4)

No new broad control plane — map P6 control ops onto the **caller-owned** executor control methods + the WP4 entrypoints:
- **query** → `executor.query(run_id=, step_id=)` (sanitized snapshot) reconciled with `query_workflow_run(store, run_id=)` + `list_workflow_steps(store, run_id=)`. Read-only; no relaunch.
- **cancel (active_run)** → `out = executor.cancel(run_id=, step_id=, scope="active_run", idempotency_key=, interrupt_outcome=None)`; then `request_workflow_cancellation(cancel_req, *, store, interrupt_outcome=out)`. The executor's `StepExecutionOutcome` (`interrupted`/`cleanup_verified`/`ambiguous`) is the sole source of truth for whether cancellation was clean; the composition adds nothing.
- **recover** → `executor.recover(run_id=, step_id=)` (reattach by workflow id, no auto-relaunch) reconciled with `query_workflow_run`; P6-A never re-invokes `step_workflow_run` for an uncertain step.
- **close** → `executor.close()` (sanitized marker; **does not** disconnect the caller-supplied client) + `summarize_workflow_run(store, *, run_id=, spec=, operator_gate=, terminal_gate_ref=)` for sanitized terminal evidence only.

## 7. No-leak strategy across WP4, Temporal history, and final evidence (FR6)

Three surfaces, three reused walls + one new scan + a canary:
1. **WP4 store/query/evidence** — `ai_flow_evidence._assert_no_leak`, `gate_decision_projection`, `artifact_ref_projection`, claim-check-only durable state.
2. **Temporal JSON + serialized bytes** — SCAN 1 `contracts.scan_projection_for_leak()` over `history_projection()`/control envelopes; SCAN 2 `contracts.scan_bytes_for_leak()` over `serialized_event_history_bytes()`.
3. **Final P6 evidence packet / dev log / user-review packet** — NEW P6 evidence projection built from allowlisted fields only (safe refs, sha256 digests, stable codes incl. both p6_* and runtime_*, counts/indices/versions, role/step/workflow/run ids, lease/epoch/state versions, gate-decision summaries, WATCH markers, sanitized evidence refs), scanned with the same SCAN-1 detector before it is written anywhere durable or user-visible.
- **Canary test:** seed forbidden material (`raw_prompt`, `signed_url`, `Traceback`, `bearer …`, `/home/…`, card JSON, media bytes) at the WP4 input boundary; assert it appears in **none** of the three surfaces and that the run fails closed with the correct stable code (`runtime_unsafe_material` / `runtime_history_leak_detected` / WP4 fail-closed). Any leak = critical blocker.

## 8. Cancellation WATCH propagation (FR3/FR5; WP3b kept explicit)

WATCH is preserved on both sides and never upgraded by the composition:
- **Executor:** unproven active-run cancellation → `_failure(C.ACTIVE_RUN_CANCELLATION_WATCH, ambiguous=True)`, `step_status="cancel_ambiguous"` (`step_executor.py:374-376`); clean only when `interrupt_outcome.interrupted is True and cleanup_verified is True`.
- **WP4:** `_WATCH_CODE="active_run_cancellation_watch"` no-downgrade lock-in — once WATCH/ambiguous, later cancellations cannot become clean `cancelled`; clean active-run cancel requires a resident in-flight `STEP_CLAIMED` step **and** a confirmed interrupt outcome.
- **P6-A:** if the executor returns ambiguous/WATCH, the run verdict is `ambiguous_fail_closed` or `parked` — **no** artifact propagation, **no** auto-relaunch — and the P6 evidence carries the `active_run_watch` marker. The user-review packet states plainly: **P6-A does not prove clean active-run cancellation; this remains WATCH.** Resolves P1-d.

## 9. Gateway / Feishu / platform / production boundary design (FR7/FR8)

- **Static boundary gate** (extends `p5_temporal/unit/test_gateway_boundary.py`): P6 module + its import closure must not import/reference Gateway, Feishu/Lark, platform adapters, public ingress, or delivery; and must contain no Worker/service auto-start in production-reachable code.
- **Lifecycle:** real Temporal runs **only** in hermetic-local tests or the staging namespace, via the ops-owned `p5_temporal_worker.py`, under the existing P5 grant `approve_external_temporal_service_or_worker_lifecycle_for_sachima_p5_runtime` (hermetic-local + staging only, never Gateway-owned). No production cluster/traffic, no Docker/systemd/socket listener, no production config writes, no auto-started service.
- **Dependencies:** none added (`temporalio` already present); no `pyproject.toml`/lockfile change.

## 10. Controlled/fake step-body design (FR4)

The Temporal step body stays `MODE_CONTROLLED_DETERMINISTIC` / `PHASE_SLICE_1`; step inputs/outputs are `static_claim_check_fixture`s; the only executor variants used are the Temporal controlled-deterministic body and the in-process `P5LocalOfflineRuntimeAdapter` oracle. A forbidden-runner static scan over the P6 changed files asserts none of `acpx`, `npx`, `claude`, `codex`, subprocess/exec, `network_fetch`, write-capable role, or satine/hermes-profile ACP appears.

## 11. TDD task plan (later P6-A implementation)

Each task is red→green and maps to a gate; tasks 1–4 use **no Temporal**, 5–9 are hermetic ops-owned.
1. **p6 admission unit** — default-off, exact token, precondition, gate-blocked → zero Temporal calls. (Gate: P6 admission.)
2. **Composition-oracle unit** — drive unmodified WP4 entrypoints with `P5LocalOfflineRuntimeAdapter`; assert end-to-end `succeeded` on a small linear graph and substitutable outcomes. (Gate: composition.)
3. **Translation-reuse unit** — assert sanitized `request → StartRequest` rejects raw/unsafe refs before any Temporal call. (Gate: translation.)
4. **Control-path unit** — query/cancel/recover/close composition + WATCH no-upgrade. (Gate: control-path.)
5. **Hermetic end-to-end** — real Worker, controlled-deterministic, claim-check-only happy path; sanitized start/terminal evidence. (Gate: hermetic real-Worker.)
6. **Hermetic dup/divergent/recover/cancel** — duplicate-identical replays once; divergent fails closed; recover reattaches without relaunch; cancel preserves WATCH. (Gate: hermetic probes.)
7. **SCAN 1 + SCAN 2 reuse/extend** over the P6 run. (Gate: no-leak.)
8. **P6 three-surface no-leak + canary**. (Gate: no-leak, merge-blocking.)
9. **Determinism replay** reuse. (Gate: determinism.)
10. **Boundary + forbidden-runner scan** extended to P6. (Gate: boundary, merge-blocking.)
11. **Docs/status stale-phrase scan** + `tools/sync_roadmap_status.py --check`. (Gate: docs.)
12. **Codex exact-head blocker review** at the implementation PR head. (Gate: review.)

## 12. Exact future P6-A verification commands / scans

```
# Behavior-bearing hermetic, ops-owned, isolated namespace (FR5/FR8)
python -m pytest tests/sachima_supervisor/p6_controlled_ai_flow/hermetic/ -q
python -m pytest tests/sachima_supervisor/p5_temporal/hermetic/test_determinism_replay.py -q   # FR3/FR8 replay reuse

# No-Temporal composition / admission / control-path / boundary (FR1/FR2/FR3/FR4/FR7)
python -m pytest tests/sachima_supervisor/p6_controlled_ai_flow/unit/ -q
python -m pytest tests/sachima_supervisor/test_ai_flow_orchestration.py tests/sachima_supervisor/test_p5_runtime_adapter.py -q  # WP4 + oracle reuse

# No-leak SCAN 1 + SCAN 2 + P6 three-surface (FR6)
python -m pytest tests/sachima_supervisor/p6_controlled_ai_flow/hermetic/test_no_leak_end_to_end.py \
                 tests/sachima_supervisor/p5_temporal/hermetic/test_no_leak_scan1.py \
                 tests/sachima_supervisor/p5_temporal/hermetic/test_no_leak_scan2.py -q

# Gateway/Feishu/platform boundary (FR7)
python -m pytest tests/sachima_supervisor/p6_controlled_ai_flow/unit/test_boundary_scan.py \
                 tests/sachima_supervisor/p5_temporal/unit/test_gateway_boundary.py -q

# Changed-file allowlist (P6-A code/test/docs only — expect empty)
git diff --name-only release/sachima...HEAD \
  | rg -v '^(sachima_supervisor/p6_controlled_ai_flow(_evidence)?\.py$|tests/sachima_supervisor/p6_controlled_ai_flow/|docs/)'

# Forbidden implementation-surface scan (expect empty)
git diff --name-only release/sachima...HEAD | rg '^(gateway/|.*/platforms/|pyproject\.toml$|uv\.lock$)'

# Forbidden-runner scan over added lines (expect empty)
git diff release/sachima...HEAD -- sachima_supervisor/p6_controlled_ai_flow.py \
  | rg '^\+' | rg -i '\b(acpx|npx|claude|codex|subprocess|os\.exec|network_fetch|write_role)\b'

# Docs/status gates
git diff --check
python tools/sync_roadmap_status.py --check --base-remote sachima
```
(Hermetic suites run only where a Temporal dev server is available, guarded/skipped otherwise — same posture as P5.)

## 13. User implementation approval phrase (FR10)

No broader than:
```
approve_agent_run_supervisor_sachima_p6a_temporal_backed_controlled_ai_flow_execution_implementation_controlled_deterministic_or_injected_fake_steps_only_default_off_no_real_agent_execution_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

## 14. Explicit non-approvals preserved

```
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
WP3b active-run cancellation WATCH remains open and is not claimed clean by P6-A.
