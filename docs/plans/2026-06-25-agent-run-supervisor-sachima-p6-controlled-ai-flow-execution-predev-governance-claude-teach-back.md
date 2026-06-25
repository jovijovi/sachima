# P6 Controlled AI FLOW execution — Claude architect teach-back

## 0. Status and non-approval boundary

This teach-back is **docs-only pre-development governance**. It is not implementation approval and starts nothing. I (Claude Code, `claude-opus-4-8[1m]`, architecture effort `max`) author teach-back and a no-code technical solution only. No source code, no runtime, no Temporal service/Worker, no workflow/activity execution, no acpx/npx/Claude/Codex as a nested runner, no Gateway/Feishu, no production config, no service restart, no delivery. WP3b active-run cancellation WATCH is carried explicitly and never overclaimed. Public digests/checksums are treated as evidence, not trust boundaries. Gateway/Feishu/platform/delivery boundaries stay closed.

## 1. Current baseline (repo truth as of this branch)

- Base `release/sachima` @ `40c4ed562…`; PR #166 (code-bearing P5 Temporal Slice 1) and PR #167 (post-P5 calibration) are **MERGED**; 0 open PRs. PR #167 is no longer "current work" — current work is this P6 governance branch.
- A default-off, caller-owned **Temporal Slice 1** is live under `sachima_supervisor/p5_temporal/`:
  - `P5TemporalStepExecutor` (`step_executor.py:122`) — WP4 StepExecutor over a Temporal control surface; default-off (`enabled=False`), exact-token admission, zero Temporal calls when off/mismatched. `execute()` / `aexecute()` plus caller-owned control methods `query/recover/cancel/close` and `history_projection()/serialized_history_bytes()`.
  - `P5TemporalControlSurface` (`control_surface.py:26`) — no-throw async dispatcher (`start/query/cancel/recover/close/handle`) returning sanitized envelopes; SCAN-1 leak guard before return.
  - `P5TemporalRuntimeClient` (`runtime_client.py:72`) — no-throw facade over a **caller-supplied connected** Temporal client; owns **no lifecycle** (never connects, never starts a Worker, never closes the caller's client); `REJECT_DUPLICATE` + `FAIL` conflict policies; duplicate-start reconciliation with query-first; SCAN-2 `serialized_event_history_bytes`/`event_history_json`.
  - `StepWorkflow` (`workflow.py:31`) — deterministic Slice-1 body; pinned updates `("resume","request_cancel")`; query snapshot allowlist-only; cooperative cancel sets `_active_run_watch=True`.
  - `contracts.py` — `StartRequest`, `ClaimCheckRef`, `UpdatePayload`, allowlists, and the stable code family (`runtime_disabled`, `runtime_approval_mismatch`, `runtime_precondition_unmet`, `runtime_idempotency_conflict`, `invalid_start_payload`, `runtime_history_leak_detected`, `runtime_unsafe_material`, `runtime_cancel_scope_unsupported`, `runtime_not_found`, `runtime_error`, `active_run_cancellation_watch`, `cancel_ambiguous`), plus `scan_projection_for_leak()` (SCAN 1) and `scan_bytes_for_leak()` (SCAN 2). Approval token `P5_TEMPORAL_RUNTIME_IMPLEMENTATION_APPROVAL_TOKEN`.
  - Tests under `tests/sachima_supervisor/p5_temporal/{unit,hermetic}/` covering admission, duplicate/divergent start, recovery, cancel-WATCH, SCAN 1/2, determinism-replay, Gateway-boundary, oracle conformance.
- The merged **WP4 controlled AI FLOW** orchestrator is local/offline, default-off, injected-fakes:
  - `StepExecutor` Protocol + `StepExecutionOutcome` (`ai_flow_executor.py:22-53`) with fields `ok, step_status, artifact_refs, evidence_ref, evidence_digest, error_code, retryable, interrupted, cleanup_verified, ambiguous`.
  - Entrypoints in `activity_ai_flow_orchestration.py`: `create_workflow_run` (admission gate), `step_workflow_run(request, *, spec, store, executor)` (pre/post-step gates + executor call + mid-step race check), `query_workflow_run`, `list_workflow_steps`, `request_workflow_cancellation(request, *, store, interrupt_outcome=None)`, `summarize_workflow_run` (terminal gate + verdict). Token `AI_FLOW_APPROVAL_TOKEN`. WATCH code `_WATCH_CODE="active_run_cancellation_watch"` with no-downgrade lock-in.
  - Four operator gates via `ai_flow_gates.check_gate("admission"|"pre_step"|"post_step"|"terminal", …)`; claim-check artifacts via `ai_flow_artifacts.verify_artifact_ref`/`artifact_ref_projection`; sanitized evidence via `ai_flow_evidence.build_workflow_evidence` (verdicts `succeeded|failed|cancelled|parked|ambiguous_fail_closed`; non-approval flag block).
  - `P5LocalOfflineRuntimeAdapter` (`p5_runtime_adapter.py:705`) — fake/injected StepExecutor with the **same control-method shapes** (`execute/query/cancel/recover/close`) as the Temporal executor; already drives the WP4 orchestrator in tests. This is the working precedent and the natural in-process **oracle**.
- WP3b WATCH still open: real host/ACP `--cancel-during-turn` never reliably proved clean active-run cancellation.

## 2. P6-A goal (one paragraph)

P6-A should prove — behavior-bearing at the orchestration/runtime layer but **fake/deterministic at the agent-execution layer** — that the merged WP4 controlled-AI-FLOW orchestrator can run a small bounded workflow whose steps are executed through the merged P5 Temporal Slice-1 control surface (a real hermetic-local Temporal Worker), producing sanitized run/query/duplicate/divergent/recover/cancel/close evidence and a sanitized terminal evidence packet, with **no real agent launch** (no acpx/npx/Claude/Codex), **no write roles**, **no Gateway/Feishu/live/default-on/production config/real delivery**, default-off behind an exact P6-A approval token, and with WP3b active-run cancellation kept explicitly as WATCH rather than claimed clean.

## 3. Requirement-by-requirement interpretation

- **FR1 — Default-off admission + exact token.** P6-A introduces a **new outer admission layer** with its own stable failure family `p6_execution_disabled | p6_approval_mismatch | p6_precondition_unmet | p6_gate_blocked`, evaluated **before any Temporal/executor call**. Interpretation: these p6_* codes WRAP, they do not replace, the inner executor `runtime_*` codes (FR2 forbids weakening). With P6-A disabled / token missing/stale/mismatched/ambiguous, or preconditions unmet (no caller-supplied Temporal control surface / spec / store), the run parks or fails closed with a p6_* code and emits zero Temporal workflow/activity calls.
- **FR2 — Reuse WP4 contract without weakening.** P6-A reuses `ai_flow_spec` / `activity_ai_flow_orchestration` **unmodified**: versioned static graph, bounded steps (`MAX_STEPS_CEILING=16`, first slice small/linear), declared dependencies only, four operator gates, claim-check-only artifacts, no dynamic AI-selected successors, no business verdict from executor success, WATCH preserved. P6-A may *tighten* (e.g. pin the first Temporal slice to a 1–3 step linear graph, `controlled_deterministic` mode) but must not loosen any WP4 validation. A "no-weakening" conformance assertion is a gate.
- **FR3 — Bind WP4 StepExecutor → P5TemporalStepExecutor.** Interpretation (important): the seam shape already matches, so P6-A **injects** `P5TemporalStepExecutor` as the `executor` argument to `step_workflow_run`; it does **not** build a second adapter. The WP4 `request` → P5 `StartRequest` translation already lives inside the executor (`test_step_executor_translation.py`); P6-A reuses it. Sanitized-ref-only translation, rejection of raw material, P5→WP4 status mapping without inventing success, caller-owned control path, and `cancel_ambiguous`/`active_run_cancellation_watch` on unproven cancellation are all already implemented in the executor and must be preserved, not re-implemented.
- **FR4 — Controlled/fake step bodies only.** Allowed: `controlled_deterministic`, `injected_fake_step_executor`, `static_claim_check_fixture`. Forbidden: `real_acpx`, `real_npx`, `real_claude_code`, `real_codex_cli`, `write_capable_role`, `network_fetch_runner`, `satine_or_hermes_profile_acp`. The Temporal workflow body stays `MODE_CONTROLLED_DETERMINISTIC` / `PHASE_SLICE_1`. Enforced by a forbidden-runner static scan + the hermetic body asserting controlled-deterministic mode.
- **FR5 — Temporal-backed run/query/cancel/recover evidence.** P6-A must prove mediation through real Temporal (hermetic-local Worker), not in-memory fakes: sanitized start projection; sanitized in-flight + terminal snapshots; idempotent duplicate-identical start (one launch, `replayed=True`); divergent duplicate fails closed (`runtime_idempotency_conflict`); recover reattaches by workflow id without auto-relaunch; cancel preserves WATCH when clean interruption is unproven; close returns sanitized terminal evidence only.
- **FR6 — No-leak across three surfaces.** (1) WP4 store/query/evidence; (2) P5 Temporal JSON projection + serialized history bytes; (3) final P6 evidence packet / dev log / user-review packet. Allowed: safe refs, sha256 digests, stable codes, counts, indices, schema versions, role keys, step/workflow/run ids, lease/epoch/state versions, gate-decision summaries, WATCH markers, sanitized evidence refs. Forbidden: raw prompts/outputs/stdout, exception text/tracebacks, PIDs/hostnames, platform ids/card JSON/message ids, media bytes/private paths, tokens/credentials/secrets/connection strings/signed URLs/delivery payloads/IM bodies. Any leak is a critical blocker. Strategy = reuse SCAN 1 + SCAN 2 + WP4 evidence no-leak, **add** a P6 three-surface scan + a canary-injection end-to-end test.
- **FR7 — Gateway/Feishu/platform boundary closed.** P6-A imports/instantiates/calls/starts/stops/mutates none of Gateway, Feishu, platform adapters, public ingress, or delivery. A static boundary gate scans P6-A changed files + import closure (extends `p5_temporal/unit/test_gateway_boundary.py`).
- **FR8 — Ops-owned Temporal lifecycle constrained.** Real Temporal runs only in the **already-granted** P5 hermetic-local test harness / staging namespace, ops-owned, never Gateway-owned, never auto-started; no production cluster/traffic, no Docker/systemd/socket listener, no production config writes. Production-reachable P6 code must never start a Worker.
- **FR9 — Visible gate suite.** The later implementation prompt and reviewer prompt list the full gate suite up front (changed-file allowlist; Gateway/Feishu/platform/delivery boundary scan; no-real-runner scan; no-leak scan over added lines + runtime/evidence; Temporal SCAN 1 + SCAN 2 reuse/extension; duplicate/divergent/recover/cancel-WATCH probes; WP4 oracle/conformance; P5TemporalStepExecutor integration; docs/status stale-phrase scan; Codex exact-head blocker review).
- **FR10 — User review packet + approval handoff.** This PR ends by requesting a narrow P6-A implementation approval — recommended scope, exact allowed files/surfaces, blocking tests/gates, preserved non-approvals, reviewer verdict + tails, exact approval phrase — not by starting code.

## 4. Assumptions

1. P6-A is a **new, narrow, production-shaped composition module** (default-off), not a test-only harness later promoted, and it reuses WP4 + P5 surfaces unmodified (answers open Q2).
2. The caller (test harness / ops, never Gateway) supplies the connected Temporal client; P6-A wires `client → P5TemporalRuntimeClient → P5TemporalControlSurface → P5TemporalStepExecutor` and never owns lifecycle.
3. The in-process `P5LocalOfflineRuntimeAdapter` is the substitutability **oracle** for the no-Temporal composition tests; the Temporal executor is the behavior-bearing path proven hermetically.
4. The P5 hermetic harness (`temporalio` + ephemeral local dev server) and its CI gating are reusable for P6 end-to-end tests; CI without a Temporal dev server skips/guards hermetic tests exactly as P5 did.
5. First Temporal slice graph is small/linear (1–3 steps), `controlled_deterministic`, claim-check fixtures only.
6. Workflow ids are deterministic, sanitized `p5wf_<48hex>` derived from safe run/step refs via `validate_workflow_id`.
7. p6_* codes are an additive outer family; inner `runtime_*`, WP4 step statuses, and WATCH codes are unchanged.
8. No new user-facing env vars; default-off via exact token + explicit `enabled` flag, mirroring P5/WP4.

## 5. Risks / open questions

**P0 (block implementation if unresolved) — none.** The PRD is sufficient for a sound no-code solution; the seams already align. (Two items below are flagged at the P0/P1 boundary and are resolved inside the technical solution; none require PRD rewrite.)

**P1 (resolve in the technical solution; called out to the implementer):**
- **P1-a — p6_* vs runtime_* relationship.** The PRD mandates a new p6_* family but doesn't state how it relates to the executor's `runtime_*`. Resolution: p6_* is the **outer admission** layer (before any Temporal call); `runtime_*` stays the **inner executor** family; both appear in evidence; neither is renamed/collapsed (preserves FR2). The implementer must not "unify" them.
- **P1-b — FR3 over-build risk.** Because `P5TemporalStepExecutor` already *is* a `StepExecutor`, the danger is building a redundant bridge class. Resolution: FR3 = **injection + reuse of existing translation**, plus composition glue only. No new adapter.
- **P1-c — Hermetic dependency for FR5/FR8.** The behavior-bearing proof *requires* a real hermetic-local Worker; this is the only place Temporal runs. The implementer must reuse the P5 ops-owned worker + hermetic harness under the existing P5 grant, keep it CI-guarded, and never make production-reachable code start a Worker.
- **P1-d — Control-path WATCH composition (open Q4/Q7).** WP4 cancellation (`request_workflow_cancellation(..., interrupt_outcome=…)`) must consume the executor's `cancel()` outcome; the composition must never manufacture a clean `cancelled`. If the executor returns `cancel_ambiguous`/`active_run_cancellation_watch`, the P6 verdict is `ambiguous_fail_closed`/parked with no artifact propagation and no auto-relaunch.

**P2 (smaller / deferrable):**
- **P2-a — Staging/canary scope (open Q9):** keep it a parallel ops/canary track, safe-after-merge, **not** a merge blocker (mirror P5 FR9).
- **P2-b — Approval-phrase wording (open Q10):** the PRD's suggested phrase is acceptable as-is; keep it no broader.
- **P2-c — Digests-as-evidence:** duplicate-start reconciliation must re-verify (already does) and P6 evidence must label digests as evidence, not trust roots.
- **P2-d — Module granularity:** one module vs. module + evidence helper; minimize new surface.

## 6. Readiness score: **90 / 100**

| Dimension | Score |
|---|---|
| Scope clarity & P6-A/B/C/P7 staging | 19/20 |
| FR precision & testability | 18/20 |
| Boundary / non-approval rigor | 19/20 |
| Codebase alignment (seams already exist) | 19/20 |
| Design questions left open (p6_*↔runtime_*, FR3 over-build, hermetic dependency) | 15/20 |

The −10 is entirely items resolvable in the technical solution (P1-a…P1-d); none are PRD defects requiring revision.

## 7. Verdict: **PASS**

The PRD is internally consistent, names exact FRs / non-approvals / failure families / staging, and lands precisely on seams that already exist in the merged code. It is sufficient for a no-code technical solution. Proceed to the technical solution, then Codex blocker review, then a separate narrow P6-A implementation-approval request.
