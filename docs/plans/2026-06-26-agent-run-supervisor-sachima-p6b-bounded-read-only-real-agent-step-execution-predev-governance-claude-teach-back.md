# P6-B bounded read-only real-agent step execution — Claude architect teach-back

## Verdict and readiness

- **Verdict: PASS — architecture work may proceed.** This is a docs-only governance pass; producing the no-code technical solution (below) is the work, and it is sound to author. **Implementation and real smoke remain NO-GO** behind separate named approvals.
- **Readiness score: 90 / 100** for "architecture-may-proceed."
  - +60 The PRD is exact, scoped, and fail-closed; non-approvals are enumerated; the candidate first workflow matches the roadmap (P6 task 2: "preferably planning/report generation before code mutation").
  - +30 The hard parts are already built and proven. P6-B is a *bridge*, not a new runtime: the real read-only one-shot exec path (`start_controlled_local_exec`) already has the pinned-local-acpx provenance gate, the atomic pre-launch claim store, the prompt-materialization seam, the read-only capability gate, and sanitized projections — and was real-smoked under WP1b. The WP4 `StepExecutor` Protocol and the P6-A `P6ControlledAiFlowSession` already accept an injected executor.
  - −10 held against four genuine open questions (read-only *enforcement* proof of a non-deterministic nested agent; prompt materialized from claim-checked inputs without leak; turning the agent's report into exactly one claim-check artifact ref without persisting bytes; launch-claim durability across a crash between WP4 claim and finalize). These are resolvable in the technical solution and verifiable at implementation/smoke time — not blockers to architecture.

## My understanding of the goal

Define — in docs only — the governance and no-code architecture for a *later* implementation that runs **exactly one bounded, read-only, real-agent AI FLOW step** behind the existing P6 control surface.

Concretely, P6-A today composes the unmodified WP4 orchestrator (`create_workflow_run → step_workflow_run(executor=…) → summarize_workflow_run`) with an injected `StepExecutor`, but the only executors wired are controlled-deterministic / injected-fake bodies (the P5 local oracle and `P5TemporalStepExecutor` with a controlled body). P6-B's product step is to let the injected executor be a **real** pinned-local read-only Codex/Claude/acpx run — starting with a planning/report step (`bounded_read_only_planning_report`), not code mutation — while every existing boundary holds:

- default-off behind a **new, distinct** P6-B exact approval token + `enabled` flag + operator gate;
- the WP4 CAS claim / gates / input re-verification / mid-step race recheck / single-output claim-check / WATCH-no-downgrade all stay in WP4, unmodified (StepExecutor semantics not weakened);
- pinned-local runner provenance only — **no `npx`, no network fetch, no shell interpolation**;
- read-only role/capability only — no write/execute/fetch, no file/git mutation, no delivery;
- claim-check-only durable state and sanitized progress/evidence (refs / digests / counts / stable codes), no raw prompt, platform IDs, tool output, card JSON, media bytes/paths, credentials, or raw exception text;
- active-run cancellation stays WP3b WATCH; no clean-cancel overclaim;
- no Gateway/Feishu/platform/delivery/production-config/production-Temporal reach.

The architecturally important realization: the cleanest P6-B is a **thin bridge `StepExecutor`** that adapts the already-merged, already-real-smoked one-shot controlled exec (`activity_controlled_exec.start_controlled_local_exec`, with its injected `prompt_materializer`) into the WP4 seam, injected into the **unmodified** P6-A session. New attack surface is minimized to (a) the WP4↔controlled-exec translation, (b) one injected output-artifact claim-check seam, and (c) WATCH-preserving control methods.

## Non-goals / non-approvals (this packet approves none of these)

- Source implementation of any P6-B module, role, or test.
- Any real agent execution; any real `acpx`/`npx`/Claude/Codex invocation; any real smoke.
- Write-capable roles; file writes; git commit/push/PR create/merge by an agent step; external API/tool side effects.
- Gateway involvement/mutation/restart/reload; Feishu/IM/live/default-on behavior; platform-adapter mutation; public ingress; real delivery.
- Production config writes; production Temporal cluster/traffic.
- Additional/unbounded persistent sessions; additional/unbounded cancellation execution; any clean active-run cancellation claim beyond the existing WATCH.
- Multi-step or non-planning/report workflows; auto-routing; agent-chosen successors.

## Assumptions

1. **No WP4 / P6-A / P5 source changes.** P6-B is additive and injected, exactly as P6-A was additive over WP4. The executor exposes `.enabled` + `.execute(...)` so `evaluate_p6_admission` / `_executor_is_armed` admit it unchanged, and `query/cancel/recover/close` so the P6-A control ops bind unchanged.
2. **The authoritative pre-launch claim is WP4's `store.claim_step` CAS.** It runs before `executor.execute`; `disposition == "replayed"` never calls the executor → no real launch on replay. The real backend (`start_controlled_local_exec`) layers a second, in-process atomic claim (`ControlledLocalExecClaimStore`) under it for crash-safety.
3. **The first step is read-only one-shot `exec` strategy** (single turn), so P6-B reuses the Phase C/D one-shot controlled-exec real path — not the persistent-session path — which is the most-proven and lowest-surface real runner.
4. **Raw external input is claim-checked upstream** into a high-density sanitized summary artifact (per GOAL.md "high-density intent summaries, never raw-text fallback") before the run; P6-B consumes only refs/digests.
5. **The report body never enters Sachima durable state or the repo tree.** It is written to a caller-owned out-of-repo artifact sink that returns a sanitized `ArtifactRef`; only that ref/digest crosses into WP4.
6. **Local/offline first; hermetic/staging Temporal only via the existing ops-owned P5 grant.** No production cluster, no Gateway-owned lifecycle.
7. **Committed role config stays `acpx_binary: null`** (non-runnable by construction); a real run needs an operator local overlay that pins a verified local acpx — never satisfiable by `npx`/network.

## Open questions (resolve in the technical solution / at smoke)

- **Q1 — read-only *enforcement* vs. *declaration*.** A read-only role declares `permissions.write/execute/fetch=false`, but a non-deterministic nested agent could still attempt a side effect. What is the binding enforcement (sandbox + workspace `allowed_roots` + redaction + post-run proof: clean `git status`, no files written outside the out-of-repo scratch, no network) and how is it asserted in smoke evidence? → addressed in §Read-only role/runner provenance.
- **Q2 — prompt materialization no-leak.** The prompt must be deterministic and repo-controlled, derived only from sanitized claim-check refs/digests of the seeded summary + a committed template (the `smoke_prompt.py` pattern), never from raw IM/user text. Where is the screen and bound? → §Prompt materialization.
- **Q3 — output → exactly one claim-check artifact ref.** WP4 `_verify_single_output` requires exactly one `ArtifactRef` matching the step's `output_contract`. Who digests the report bytes, where do they live, and how do we prove the bytes never persist? → §Progress/evidence + injected `artifact_sink` seam.
- **Q4 — launch-claim durability across crash.** Between WP4 claim and WP4 finalize, a real launch is a heavyweight side effect that can survive a crash. Confirm reattach-by-deterministic-id (no relaunch) and the in-process claim's crash semantics; decide what (if anything) the durable cross-process path needs beyond the existing P5 deterministic workflow id + durable claim store. → §Pre-launch claim/replay/lease/idempotency.

## Critical risks

| # | Risk | Severity | Mitigation (architecture) |
|---|---|---|---|
| R1 | Nested real agent performs an unapproved side effect (write/git/network) despite a read-only role | **Critical** | Read-only capability re-check at the executor (`permissions` write/execute/fetch=false; capabilities ⊆ `read,search`); sandbox + `allowed_roots`; out-of-repo workdir (`_REPO_ROOT` exclusion); smoke evidence asserts clean git status + no out-of-scratch writes + no network. Real smoke is separately gated. |
| R2 | Raw material leaks via prompt, output artifact, progress, or evidence | **Critical** | Three reused no-leak walls + the report-bytes seam that emits digest/count only, all SCAN-1/SCAN-2 guarded; canary test seeds forbidden material at every boundary and asserts it appears in none of WP4 store/Temporal history/P6 evidence and fails closed. |
| R3 | `npx`/network/shell re-enters via runner provenance | High | Reuse `FORBIDDEN_RUNNER_BASENAMES`; absolute pinned `acpx_binary` + sha256; null committed binary non-runnable; static added-line scan for `npx`/`network_fetch`/`shell=True`/`os.system`/command interpolation. |
| R4 | StepExecutor semantics weakened (verdict inferred from agent success, gate/claim bypass, relaunch on recover, clean-cancel overclaim) | High | Executor returns only a sanitized `StepExecutionOutcome`; never writes the store; never infers `business_verdict`; WP4 keeps CAS/gates/re-verify/WATCH; cancel mirrors `P5TemporalStepExecutor.acancel` (clean only when `interrupted ∧ cleanup_verified`); recover reattaches, never relaunches. |
| R5 | Double real launch on replay/crash | High | WP4 CAS claim (replayed ⇒ no execute) + in-process `ControlledLocalExecClaimStore` + deterministic launch/reattach id. |
| R6 | Scope creep (write role, multi-step, persistent session, delivery) sneaks in | Med | Distinct P6-B token encoding non-approvals; changed-file allowlist; `CONTROLLED_EXEC_FUTURE_ROLE_KEYS` fail closed; forbidden-surface scans; single-step planning/report only. |
| R7 | Non-deterministic agent breaks deterministic gates | Med | All local/hermetic gates run with an **injected fake** read-only runner; determinism-replay reuse stays on the controlled-deterministic body; the real runner runs only under the separate real-smoke approval. |
| R8 | Provenance/governance drift (stale P6-A wording, status authority confusion) | Low | Docs/status gates: YAML parse, `sync_roadmap_status.py --check`, stale-P6-A scan, docs-only changed-file allowlist; live merge state stays GitHub-authoritative. |

## Pass/fail decision

**PASS — architecture work may proceed.** The PRD is well-formed with no P0/P1 misunderstanding; the design reuses proven, real-smoked machinery; boundaries are enforceable with existing walls. The technical solution that follows defines exact surfaces, gates, tests, and a two-stage approval split. **It does not approve implementation or real smoke**, and it keeps Gateway/Feishu/live/production/write-roles/real-delivery closed. The residual 10 points (Q1–Q4) are design details fixed below and proven at the separately approved implementation and smoke gates.
