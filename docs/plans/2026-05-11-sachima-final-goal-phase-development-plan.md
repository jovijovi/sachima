# Sachima Final Goal Phase Development Plan

> **For Hermes:** This is a planning document, not implementation approval. Use `GOAL.md` as the product compass and `docs/sachima-final-goal-gap-analysis.md` as the gap basis. Each implementation phase below still requires separate explicit approval before code, config, Gateway restart/reload, real external ingress, real delivery, production agent/tool execution, platform adapter mutation, or durable runtime lifecycle work.

**Goal:** Convert the final Sachima goal into an executable multi-phase development roadmap with concrete dependencies, task lists, constraints, acceptance gates, checklists, and scoring rubrics.

**Architecture:** Move from proven PE-1 Sachima-only shadow observation toward a full IM AI workbench by changing one production axis at a time: observation volume, fake delivery, design contract, external ingress, durable runtime, controlled AI execution, real delivery/ACK closure, and operational product hardening.

**Tech Stack:** Sachima Gateway adapter, FlowWeaver transaction model, Hermes Agent execution engine, injected runtime control surfaces, Temporal or equivalent durable runtime when separately approved, pytest/CI gates, evidence packets, and fresh-context reviews.

---

## 1. Current Baseline

```text
Repository: jovijovi/sachima
Base branch: feature/sachima-channel
Baseline after project goal/gap landing: b2f1d8af9
Canonical goal: GOAL.md
Gap analysis: docs/sachima-final-goal-gap-analysis.md
Latest readiness boundary: docs/plans/2026-05-11-flowweaver-pe1d-pe2-readiness-decision-packet.md
```

Current proven state:

- PE-1 controlled Sachima shadow observation is implemented and merged.
- PE-1A local ingress smoke passed.
- PE-1B short-window observation passed.
- PE-1C evidence packet and rollback drill passed.
- PE-1D / PE-2 readiness packet is merged.
- Current PE-1 runtime hook is file-based, low-intrusion, and only exposes `start_transaction` / `query_transaction`.
- Temporal service / Worker, production delivery control, and production agent/tool execution remain off.
- `SACHIMA_SEND_URL` remains absent in the approved PE-1 observation path.

Current strategic status:

| Area | Approximate progress | Meaning |
|---|---:|---|
| Architecture direction | 80% | The target layering and boundaries are coherent. |
| Safety boundary discipline | 75% | PE-1 fail-closed/no-leak/rollback proofs are strong. |
| Sachima base channel | 60% | Adapter and loopback ingress exist; real ingress/delivery pending. |
| Production FlowWeaver readiness | 40% | Local proofs exist; production durable runtime/execution pending. |
| Final AI workbench UX | 25% | Product surface, simulator, cards, approvals, and operator loop need buildout. |

This plan does **not** raise the overall final-goal estimate by itself. It makes the remaining work measurable.

---

## 2. Global Development Principles

1. **One production axis per phase.** Do not combine external ingress, delivery, runtime, agent execution, and UI expansion in one PR.
2. **Behavior-bearing over pure report inertia.** A design-only phase is allowed only when it gates real risk; otherwise the phase should produce controlled evidence.
3. **Default-off and fail-closed.** Any missing, duplicated, forged, hostile-subclass, or out-of-scope policy input fails closed.
4. **Claim-check everything raw.** Raw prompts, platform IDs, card JSON, media bytes/paths, tool output, credentials, callbacks, and raw exception text must not enter durable history, evidence packets, logs, or user-visible cards.
5. **Gateway does not secretly own lifecycle.** Gateway must not silently create Temporal clients, Workers, task queues, services, daemons, Docker containers, sockets, or subprocess lifecycles.
6. **Delivery surfaces stay separate.** Final text, rich cards, progress cards, media, artifacts, and ACKs are separate surfaces and must not suppress each other.
7. **Operator control is first-class.** Every production-adjacent phase needs start, pause/stop, rollback, restore, evidence, and no-leak proof.
8. **Every phase produces a decision artifact.** The artifact must list what is approved, what remains blocked, and which approval text unlocks the next phase.

---

## 3. Approval Boundary Matrix

| Boundary | Current state | Can this plan approve it? | Required future approval |
|---|---|---:|---|
| PE-1D longer controlled local observation | Eligible | No | `approve_pe1d_longer_controlled_sachima_local_observation_window` |
| Fake-send / simulator target | Eligible for separate scoped work | No | `approve_fake_send_or_simulator_target` |
| PE-2 design packet only | Eligible | No | `approve_pe2_design_packet_only_no_implementation` |
| PE-2 implementation | NO-GO | No | Later explicit implementation approval after evidence gates |
| Real external Sachima ingress | NO-GO | No | `approve_real_external_sachima_ingress` |
| Production config write | NO-GO unless named | No | `approve_production_config_write` |
| Gateway restart/reload | NO-GO unless named | No | `approve_gateway_restart_or_reload` |
| Production delivery control | NO-GO | No | Later explicit delivery approval after fake-send evidence |
| Production agent/tool execution expansion | NO-GO | No | Later explicit AI FLOW execution approval after runtime/safety gates |
| Gateway-owned durable runtime lifecycle | NO-GO | No | Prefer never; if proposed, requires architecture exception approval |

---

## 4. Program-Level Dependencies

### 4.1 Proven Inputs

- `GOAL.md` — final goal and non-negotiable principles.
- `docs/sachima-final-goal-gap-analysis.md` — gap summary and recommended sequence.
- PE-1A / PE-1B / PE-1C evidence packets and scripts.
- PE-1D / PE-2 readiness packet.
- Existing Sachima adapter smoke scripts.
- Existing FlowWeaver tests and changed-file guards.

### 4.2 External Dependencies

These are not all needed immediately, but each must be resolved before its phase:

- Controlled Sachima local webhook listener and HMAC secret in service env.
- A fake-send local endpoint or simulator process for delivery loop phases.
- A separately owned durable runtime service if Temporal production/staging execution is approved.
- A reverse proxy / TLS / exposure mechanism for real external ingress, if approved.
- Operator policy for allowed users/groups and side-effect approvals.
- CI access, GitHub CLI auth, and stable branch protection checks.

### 4.3 Documentation Dependencies

Every phase must update or create:

- `docs/plans/YYYY-MM-DD-<phase>.md`
- `docs/runbooks/<phase>.md` when an operator action exists
- `docs/dev_log/YYYY-MM-DD-<phase>.md`
- exact changed-file guard allowlists, if the repo guards the changed paths
- evidence packet under `outputs/` or a docs-safe summary, if the phase runs probes

---

## 5. Master Phase Sequence

| Phase | Name | Primary goal | Strongest allowed outcome |
|---|---|---|---|
| P1 | PE-1D longer controlled local observation | Raise confidence in observation-only Sachima loopback behavior | Ready for fake-send/simulator or PE-2 design request |
| P2 | Fake-send / simulator delivery loop | Prove delivery semantics without real external sends | Ready for PE-2 design and controlled delivery contract request |
| P3 | PE-2 design packet only | Define smallest behavior-bearing PE-2 implementation slice | Ready for separately approved PE-2 implementation request |
| P4 | Controlled external ingress | Expose Sachima ingress beyond loopback without delivery/execution expansion | Ready for external-ingress observation/simulator evidence review |
| P5 | Production durable runtime integration | Attach caller-supplied durable runtime safely | Ready for controlled AI FLOW execution request |
| P6 | Controlled AI FLOW execution | Run selected long workflows from Sachima with approvals | Ready for real delivery/ACK closure request |
| P7 | Real delivery and ACK closure | Connect real outbound delivery and ACK reconciliation | Ready for limited live pilot request |
| P8 | Product/ops hardening | Turn the system into an operator-grade AI workbench | Ready for broader rollout decision |

Recommended next move: **P1 first**. It is the highest confidence behavior-bearing step and does not expand live risk.

---

## 6. Phase P1 — PE-1D Longer Controlled Local Observation

### Goal

Run a longer controlled local Sachima observation window to prove PE-1 behavior over more turns, negative probes, duplicate/replay cases, and rollback checks without expanding scope.

### Dependencies

- PE-1A, PE-1B, PE-1C PASS evidence.
- Current PE-1 config shape: `enabled=true`, exact `platform_allowlist=[sachima]`, bounded timeout.
- Local Sachima listener on loopback.
- HMAC signing helper.
- PE-1 file runtime hook exposing only `start_transaction` and `query_transaction`.
- No configured send URL.

### Task List

1. Create P1 plan/dev log/runbook for the longer observation window.
2. Define observation window size: minimum accepted signed turns, negative probes, duplicate probes, disabled-policy probe, and restore probe.
3. Add or extend an automation script for the longer window.
4. Capture baseline observation/workflow counts.
5. Run signed allowlisted turns through loopback only.
6. Run unsigned, bad-signature, non-allowlisted, duplicate, and disabled probes.
7. Verify only allowlisted accepted turns create observation/workflow deltas.
8. Verify duplicate/replay turns create no extra observation state.
9. Verify no raw material appears in shadow files, evidence, logs, or user-visible summaries.
10. Verify runtime operations remain exactly `start_transaction` and `query_transaction`.
11. Verify Temporal service/Worker remains absent.
12. Produce evidence packet and next-phase decision.
13. Run fresh-context blocker review.
14. Commit/PR/CI/merge if docs or scripts change.

### Constraints

- Loopback-only ingress.
- Observation-only.
- No real external ingress.
- No send URL.
- No production delivery control.
- No production agent/tool execution.
- No Temporal service or Worker startup.
- No platform adapter mutation unless separately approved.
- No Gateway restart/reload unless separately approved.

### Acceptance Standards

- Accepted signed allowlisted turns produce exact expected observation/workflow deltas.
- Negative probes produce zero observation/workflow deltas.
- Duplicate/replay probes are idempotent.
- Evidence packet contains sanitized metadata only.
- Rollback/disable still prevents runtime calls.
- Restore resumes observation precisely.
- Fresh review reports zero blockers.

### Acceptance Checklist

- [ ] Scope approval text captured.
- [ ] Baseline counts captured.
- [ ] Positive-turn count meets plan threshold.
- [ ] Unsigned probe rejected.
- [ ] Bad-signature probe rejected.
- [ ] Non-allowlisted probe rejected.
- [ ] Duplicate/replay probe produces no new state.
- [ ] Disabled-policy probe produces no runtime call.
- [ ] Restore probe creates exactly one valid observation.
- [ ] No-leak scan covers shadow files, evidence packet, logs, and summaries.
- [ ] Runtime operations are exactly start/query.
- [ ] Temporal service/Worker absent.
- [ ] Evidence packet written.
- [ ] Fresh-context review blockers = 0.

### Scoring Rubric

| Category | Points |
|---|---:|
| Positive observation correctness | 20 |
| Negative/fail-closed probes | 20 |
| Duplicate/replay/idempotency | 15 |
| No-leak evidence | 20 |
| Rollback/restore proof | 15 |
| Review/docs completeness | 10 |

Pass threshold: **90/100**, with no zero in any category and no critical boundary violation.

---

## 7. Phase P2 — Fake-Send / Simulator Delivery Loop

### Goal

Prove assistant response delivery semantics against a local fake-send target or simulator UI before any real external delivery is configured.

### Dependencies

- P1 evidence packet with no blockers.
- Existing Sachima adapter local response recording behavior.
- A local fake-send endpoint or simulator process approved for the phase.
- Delivery/ACK reconciliation contracts from prior FlowWeaver phases.
- High-density task-summary card rules.

### Task List

1. Draft P2 plan/dev log/runbook.
2. Define fake-send endpoint contract: request shape, response shape, ACK shape, failure shape.
3. Implement simulator/fake target in a local-only test harness.
4. Route Sachima outbound delivery to fake target only under explicit local config/test env.
5. Prove final text delivery is not suppressed by rich/progress cards.
6. Prove progress cards, rich cards, final text, artifacts, and media are separate slots.
7. Prove ACKs are derived only from fake-send responses, never invented.
8. Prove duplicate send attempts are idempotent.
9. Render or record simulator transcript with sanitized surfaces.
10. Add no-leak scans over fake-send requests/responses/transcripts/evidence/logs.
11. Add failure probes: fake-send timeout, rejected delivery, malformed ACK, duplicate ACK, partial surface failure.
12. Produce evidence packet and decision for PE-2 design or delivery contract work.
13. Run fresh review focused on accidental real-send paths.

### Constraints

- Fake/local send target only.
- No real `SACHIMA_SEND_URL` pointing to an external IM service.
- No live/default-on behavior.
- No production config write unless separately approved.
- No raw message/card/media/tool output in transcripts or evidence.
- No invented ACKs.
- No change to real delivery adapters unless explicitly scoped.

### Acceptance Standards

- Every emitted delivery slot has a deterministic fake-send response or stable failure code.
- Final text appears even when rich cards or progress cards exist.
- ACK state matches fake-send responses exactly.
- Duplicate sends do not create duplicate final deliveries.
- Simulator transcript is safe to paste into IM.
- Fresh review finds no accidental real delivery path.

### Acceptance Checklist

- [ ] Fake target approval captured.
- [ ] Fake endpoint contract documented.
- [ ] Positive final text delivery passes.
- [ ] Rich/progress/final/media/artifact surfaces separated.
- [ ] ACK derived from fake response only.
- [ ] Duplicate send idempotency verified.
- [ ] Timeout/failure stable codes verified.
- [ ] Transcript/evidence/log no-leak scan passes.
- [ ] No external send URL used.
- [ ] Fresh review blockers = 0.

### Scoring Rubric

| Category | Points |
|---|---:|
| Surface separation | 20 |
| ACK derivation correctness | 20 |
| Idempotency and replay handling | 15 |
| Failure handling/stable codes | 15 |
| No-leak transcript/evidence | 20 |
| Simulator usability/docs | 10 |

Pass threshold: **88/100**, with automatic fail on any real external send.

---

## 8. Phase P3 — PE-2 Design Packet Only

### Goal

Define the smallest PE-2 implementation slice using P1/P2 evidence, without implementing PE-2 or enabling live behavior.

### Dependencies

- P1 evidence packet.
- Preferably P2 fake-send evidence. If P3 is drafted before P2, it remains design-only and must mark P2 fake-send evidence as a hard blocker for any PE-2 implementation, real delivery, or delivery-facing behavior.
- Current goal/gap/phase plan docs.
- Prior Phase 29–33 implementation evidence and readiness packet.

### Task List

1. Create PE-2 design packet.
2. Define exact PE-2 behavior-bearing slice: what changes, what remains unchanged.
3. List all required approvals separately.
4. Define contracts for ingress, runtime, execution, delivery, evidence, and rollback.
5. Define explicit non-approvals: live/default-on, real delivery, production agent/tool expansion, config writes, restarts, adapter mutation, Gateway-owned runtime lifecycle.
6. Define RED tests required by PE-2 implementation.
7. Define no-leak and side-effect scans.
8. Define exact changed-file guard strategy.
9. Run independent consistency and security reviews.
10. Produce decision outcome: ready/not-ready for implementation request.

### Constraints

- Docs/design only.
- No implementation.
- No runtime lifecycle startup.
- No Gateway restart/reload.
- No production config write.
- No real external ingress/delivery.
- No production agent/tool execution expansion.

### Acceptance Standards

- The design can be handed to a fresh implementer without hidden assumptions.
- PE-2 implementation scope is minimal and behavior-bearing.
- All required approvals are named separately.
- No wording implies live/default-on approval.
- Fresh review blockers are zero.

### Acceptance Checklist

- [ ] Design-only scope stated in header.
- [ ] Required approvals separated.
- [ ] Explicit non-approvals listed.
- [ ] P1/P2 evidence dependencies referenced accurately.
- [ ] PE-2 implementation task list is RED/GREEN testable.
- [ ] No live/default-on implication.
- [ ] Fresh consistency review blockers = 0.
- [ ] Fresh security/low-intrusion review blockers = 0.

### Scoring Rubric

| Category | Points |
|---|---:|
| Scope clarity | 20 |
| Evidence dependency accuracy | 20 |
| Testability of future implementation plan | 20 |
| Approval/non-approval separation | 20 |
| Reviewability and handoff quality | 20 |

Pass threshold: **92/100**, because design ambiguity here becomes implementation risk.

---

## 9. Phase P4 — Controlled External Sachima Ingress

### Goal

Expose Sachima ingress beyond loopback under a narrow, reversible, observation-only or simulator-only boundary.

### Dependencies

- P1 pass.
- P2 simulator/fake-send pass if simulator responses will be rendered.
- P3 design approval or a dedicated external ingress design approval that accurately records fake-send evidence status and keeps real delivery blocked unless separately approved.
- Approved exposure path: reverse proxy/TLS/host/path/rate limits/body limits.
- Operator/user/group allowlist model.

### Task List

1. Draft external ingress design and threat model.
2. Define host/path/TLS/proxy/body-size/rate-limit policy.
3. Define HMAC timestamp/replay policy under real network conditions.
4. Define user/group allowlist and deny behavior.
5. Define media/image URL SSRF and size controls.
6. Implement external ingress only after explicit approval.
7. Run positive signed external request probes.
8. Run negative probes: missing signature, bad signature, stale timestamp, replay, oversized body, disallowed user/group, malformed media.
9. Verify observation-only or simulator-only behavior.
10. Verify rollback can stop ingress without touching raw payloads.
11. Produce evidence packet and review.

### Constraints

- No real outbound delivery unless separately approved.
- No production agent/tool execution expansion.
- No broad allow-all user policy.
- No raw request body or platform IDs in durable evidence.
- No open public endpoint without HMAC/replay controls.

### Acceptance Standards

- External signed request path works only for approved users/groups.
- Negative probes fail closed with stable codes.
- Rate/body/media limits are enforced.
- Rollback stops ingress quickly.
- No delivery/execution expansion occurs.

### Acceptance Checklist

- [ ] Exposure approval captured.
- [ ] Threat model complete.
- [ ] TLS/proxy/path/body/rate controls documented.
- [ ] HMAC timestamp/replay probes pass.
- [ ] User/group allowlist probes pass.
- [ ] Media/SSRF probes pass if media accepted.
- [ ] Observation/simulator-only boundary verified.
- [ ] Rollback verified.
- [ ] Evidence no-leak scan passes.
- [ ] Fresh review blockers = 0.

### Scoring Rubric

| Category | Points |
|---|---:|
| Auth/replay/fail-closed behavior | 25 |
| Exposure/rate/body/media controls | 20 |
| Scope containment | 20 |
| Rollback proof | 15 |
| No-leak evidence | 15 |
| Documentation/review | 5 |

Pass threshold: **90/100**, with automatic fail on unauthenticated external access.

---

## 10. Phase P5 — Production Durable Runtime Integration

### Goal

Attach a real durable runtime behind a caller-supplied control surface so long Sachima workflows can survive retries, restarts, queries, updates, cancellations, and recovery.

### Dependencies

- P3 design approval.
- Runtime owner and deployment model approved.
- Future approval text before implementation: `approve_external_runtime_control_surface` plus `approve_external_temporal_service_or_worker_if_used` if Temporal service/Worker lifecycle is part of the phase.
- Namespace/task queue naming approved.
- No-throw Activity wrapper discipline from Phase 33.
- Claim-check storage policy.
- Runtime history no-leak scanner.

### Task List

1. Draft runtime integration design and runbook.
2. Define runtime owner: service, Worker, namespace, task queue, deployment, monitoring.
3. Define caller-supplied control surface contract; Gateway does not create lifecycle implicitly.
4. Define start/query/update/cancel/recover operations and stable error codes.
5. Implement fake/runtime adapter tests first.
6. Implement staging/local runtime integration only after approval.
7. Wrap all caller-provided Activities with no-throw sanitizers.
8. Add history no-leak checks over JSON and serialized event bytes.
9. Add duplicate-start, retry, timeout, cancellation, and recovery probes.
10. Add query snapshot consistency tests after each major phase.
11. Produce evidence packet and readiness decision for AI FLOW execution.

### Constraints

- No Gateway-owned hidden Temporal lifecycle.
- No production execution without explicit runtime approval.
- No raw material in runtime history, snapshots, logs, or evidence.
- No function-local imports or dynamic connect/start bypasses.
- No Worker/service startup inside message handling.

### Acceptance Standards

- Runtime control surface is explicit and caller-supplied.
- Restart/retry/replay evidence is clean.
- Query/update/cancel/recover semantics are stable.
- Activity raw failures are sanitized before entering history.
- History bytes no-leak scan passes.

### Acceptance Checklist

- [ ] Runtime owner approved.
- [ ] Task queue/namespace documented.
- [ ] Gateway lifecycle non-ownership verified by source scan.
- [ ] No-throw Activity wrapper tests pass.
- [ ] Duplicate-start test passes.
- [ ] Retry/timeout test passes.
- [ ] Cancel/recover test passes.
- [ ] Query snapshot consistency passes.
- [ ] JSON and bytes history no-leak scans pass.
- [ ] Fresh review blockers = 0.

### Scoring Rubric

| Category | Points |
|---|---:|
| Runtime ownership clarity | 20 |
| Durable behavior correctness | 25 |
| No-throw/no-leak enforcement | 25 |
| Query/update/cancel/recover contract | 20 |
| Runbook/review completeness | 10 |

Pass threshold: **90/100**, with automatic fail on hidden Gateway runtime lifecycle.

---

## 11. Phase P6 — Controlled AI FLOW Execution

### Goal

Allow selected long AI workflows from Sachima requests with claim-checked inputs, explicit side-effect approvals, sanitized progress, and recovery semantics.

### Dependencies

- P5 runtime evidence.
- Tool allowlist and side-effect policy.
- Claim-check input storage policy.
- Approval UI/command policy.
- Progress card schema.
- Artifact safe-ref schema.
- Recommended future approval text: `approve_controlled_sachima_ai_flow_execution` with named toolsets, side-effect classes, and operator approvals.

### Task List

1. Draft AI FLOW execution plan and approval matrix.
2. Select first workflow: preferably planning/report generation before code mutation.
3. Define allowed tools/toolsets and forbidden side effects.
4. Implement claim-check input references for raw user/platform material.
5. Add approval gates for file writes, git pushes, PR creation/merge, external API calls, media generation, and messaging.
6. Add sanitized progress snapshots and high-density task summaries.
7. Add pause/cancel/recover behavior.
8. Add no raw exception text tests for logs/history/cards.
9. Run a controlled end-to-end workflow through Sachima simulator or approved ingress.
10. Produce evidence packet and decision for delivery/ACK closure.

### Constraints

- No broad unrestricted tool execution.
- No unapproved file writes, git pushes, PR merges, messaging, external APIs, or production changes.
- No raw prompts/tool output/log dumps in cards or durable state.
- No direct live/default-on behavior.
- No accidental recursion into cron/scheduled job creation unless separately approved.

### Acceptance Standards

- Selected workflow completes with sanitized progress and final evidence.
- Side effects require explicit approval and are auditably recorded.
- Operator can pause/cancel/recover.
- Tool outputs become artifacts or summaries, not raw durable payloads.
- Fresh review finds no privilege expansion.

### Acceptance Checklist

- [ ] Workflow selection approved.
- [ ] Tool allowlist documented.
- [ ] Side-effect approvals enforced.
- [ ] Claim-check references used for raw inputs.
- [ ] Progress snapshots sanitized.
- [ ] Artifact refs safe and inspectable.
- [ ] Pause/cancel/recover passes.
- [ ] Raw exception/log no-leak tests pass.
- [ ] End-to-end controlled workflow passes.
- [ ] Fresh review blockers = 0.

### Scoring Rubric

| Category | Points |
|---|---:|
| Tool/side-effect containment | 25 |
| Claim-check and no-leak discipline | 25 |
| Workflow completion correctness | 20 |
| Operator controls | 15 |
| Product quality of progress/artifacts | 10 |
| Review/docs completeness | 5 |

Pass threshold: **88/100**, with automatic fail on unapproved side effect.

---

## 12. Phase P7 — Real Delivery and ACK Closure

### Goal

Connect real outbound delivery and ACK reconciliation after fake-send, runtime, and controlled execution evidence are clean.

### Dependencies

- P2 fake-send evidence.
- P5 runtime evidence.
- P6 controlled execution evidence if AI FLOW final results will be delivered.
- Approved real send API endpoint and credentials in service env.
- Delivery slot schema and ACK reconciliation contract.
- Operator rollback for disabling send path.
- Recommended future approval text: `approve_real_sachima_delivery_ack_closure` plus a separately named bounded-recipient send approval before any real send URL is used.

### Task List

1. Draft real delivery/ACK design and runbook.
2. Define delivery slot initialization before sends.
3. Define final text/card/progress/media/artifact delivery surfaces.
4. Define ACK event mapping, duplicate ACK policy, retry policy, and stable failures.
5. Implement real send in the narrowest approved adapter path.
6. Add canary send with bounded test recipient/group.
7. Verify final text is not suppressed by rich/progress cards.
8. Verify ACKs map to initialized slots only.
9. Verify media and card failures do not corrupt final text state.
10. Verify rollback disables delivery without stopping safe observation.
11. Produce evidence and limited-live decision.

### Constraints

- Real send API only after explicit approval.
- Bounded test recipient/group only.
- No broad group/live/default-on rollout.
- No invented ACKs.
- No raw platform payloads, private IDs, credentials, or card JSON in durable state/evidence.

### Acceptance Standards

- Real messages deliver correctly to bounded target.
- Delivery and ACK state matches initialized slots exactly.
- Duplicate ACKs and retries are idempotent.
- Failures use stable codes only.
- Rollback disables send path quickly.

### Acceptance Checklist

- [ ] Real send approval captured.
- [ ] Credentials/service-env handling documented without values.
- [ ] Bounded recipient/group approved.
- [ ] Delivery slot initialization passes.
- [ ] Final text delivery passes.
- [ ] Rich/progress/media separation passes.
- [ ] ACK exact mapping passes.
- [ ] Retry/duplicate idempotency passes.
- [ ] Failure stable-code tests pass.
- [ ] Rollback disables sends.
- [ ] Evidence no-leak scan passes.
- [ ] Fresh review blockers = 0.

### Scoring Rubric

| Category | Points |
|---|---:|
| Real delivery correctness | 20 |
| ACK exactness/idempotency | 25 |
| Surface separation | 20 |
| Failure/rollback behavior | 20 |
| Secret/platform no-leak | 10 |
| Review/docs completeness | 5 |

Pass threshold: **92/100**, with automatic fail on send to unapproved target.

---

## 13. Phase P8 — Product and Operations Hardening

### Goal

Turn the proven system into an operator-grade IM AI workbench with high-density task cards, approvals, artifact browsing, metrics, alerts, evidence packets, and incident response.

### Dependencies

- P6/P7 evidence depending on which product surfaces are exposed.
- Stable card schema.
- Operator command vocabulary.
- Metrics/evidence extraction hooks.
- Incident/rollback template.

### Task List

1. Define final Sachima workbench UX: task card, progress card, approval prompt, artifact list, final report, error recovery.
2. Implement simulator-first UX tests.
3. Implement real IM UX only after delivery is proven.
4. Add operator commands: status, pause, resume, cancel, rollback, evidence export.
5. Add metrics for starts, completions, failures, retries, duplicate probes, delivery results, rollback state, and no-leak scanner status.
6. Add alert thresholds and safe alert summaries.
7. Add evidence packet generator per workflow.
8. Add staged rollout runbook and incident review template.
9. Run a limited live pilot decision packet.

### Constraints

- Product cards must summarize state, not dump logs or raw payloads.
- Approval controls must not bypass side-effect policy or changed-file/runtime guards.
- Metrics and alerts must not leak raw material.
- Rollback commands must be safe, explicit, and auditable.

### Acceptance Standards

- Operator can understand and control a long workflow from IM.
- Cards are concise, high-density, and safe.
- Evidence packets are repeatable.
- Metrics/alerts detect failure without leaking sensitive material.
- Incident/rollback process is documented and practiced.

### Acceptance Checklist

- [ ] UX schema approved.
- [ ] Simulator UX passes.
- [ ] Approval controls enforce policy.
- [ ] Artifact safe refs render correctly.
- [ ] Status/pause/resume/cancel/rollback commands pass.
- [ ] Metrics emitted without raw material.
- [ ] Alert summaries are sanitized.
- [ ] Evidence generator passes.
- [ ] Incident drill passes.
- [ ] Limited live pilot decision packet created.

### Scoring Rubric

| Category | Points |
|---|---:|
| Operator UX clarity | 20 |
| Approval/control correctness | 20 |
| Evidence/observability quality | 20 |
| Rollback/incident readiness | 20 |
| No-leak product surfaces | 15 |
| Documentation/review | 5 |

Pass threshold: **85/100**, with automatic fail on unsafe card/log exposure.

---

## 14. Cross-Phase Verification Pipeline

Every code-bearing phase should run the narrowest focused tests first, then the shared regression chain:

```bash
scripts/run_tests.sh <focused-tests> -q
scripts/run_tests.sh <phase-integration-tests> -q
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase5*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
git diff --check
python -m compileall gateway tests scripts
```

Every docs/design-only phase should run:

```bash
git diff --check
python - <<'PY'
from pathlib import Path
plan = Path("docs/plans/2026-05-11-sachima-final-goal-phase-development-plan.md")
required = [
    "### Goal",
    "### Dependencies",
    "### Task List",
    "### Constraints",
    "### Acceptance Standards",
    "### Acceptance Checklist",
    "### Scoring Rubric",
]
text = plan.read_text()
missing = [marker for marker in required if marker not in text]
raise SystemExit("missing required roadmap markers: " + ", ".join(missing) if missing else 0)
PY
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase5*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```

Fresh-context review requirements:

- one reviewer for spec/goal consistency;
- one reviewer for security, low intrusion, and side-effect boundaries;
- blocker-only re-review after any blocker fix;
- final review evidence appended to dev log, followed by another doc gate if the dev log changes.

---

## 15. Global Acceptance Checklist

A phase is not complete until all applicable items are true:

- [ ] Scope approval is captured in exact text.
- [ ] Phase plan names goals, dependencies, constraints, tasks, acceptance, checklist, and scoring.
- [ ] Required evidence packets are generated and no-leak scanned.
- [ ] Runtime/delivery/execution boundaries are verified by deterministic tests or source scans.
- [ ] Fresh-context blocker reviews report zero blockers.
- [ ] Guard allowlists are exact, not broadened.
- [ ] CI is green before merge.
- [ ] Post-merge canonical checkout is synchronized.
- [ ] Final report states phase progress separately from final-goal progress.

---

## 16. Program-Level Scorecard

Use this as a quarterly or milestone-level health score. It is separate from individual phase scoring.

| Dimension | Weight | Scoring question |
|---|---:|---|
| Safety/no-leak/fail-closed | 25 | Can hostile, duplicate, forged, malformed, and raw-material probes fail closed without leakage? |
| Durable execution/recovery | 20 | Can long workflows survive retry, restart, query, cancel, recover, and evidence extraction? |
| Delivery/ACK correctness | 20 | Can the system prove exactly what was delivered, acknowledged, retried, or failed? |
| Product/operator experience | 15 | Can Dog Brother run and control work from IM without reading logs? |
| Low-intrusion architecture | 10 | Are lifecycle owners explicit and separated from Gateway message handling? |
| Documentation/review discipline | 10 | Can a fresh agent safely continue from docs without hidden context? |

Program maturity bands:

| Score | Meaning |
|---:|---|
| 0–49 | Foundation / prototype; not live-ready. |
| 50–69 | Controlled local/staging capability; production axes still isolated. |
| 70–84 | Limited pilot candidate; live behavior possible only with tight runbook and rollback. |
| 85–94 | Production beta candidate; core risk gates proven. |
| 95–100 | Mature operator-grade AI workbench. |

Current estimate after goal/gap planning: **45–50**. P1/P2 can raise confidence but should not be counted as production live readiness.

---

## 17. My Recommendation

Do **not** jump to PE-2 implementation.

Recommended next approval:

```text
approve_pe1d_longer_controlled_sachima_local_observation_window
```

After P1 passes, I recommend P2 fake-send/simulator before any real delivery or external ingress. The reason is blunt: the next dangerous bug class is not “can we receive a message?” anymore; it is “can we deliver the right response on the right surface without inventing ACKs, suppressing final text, or leaking raw material?” Fake-send catches that without risking the real channel.

Recommended near-term sequence:

```text
P1 PE-1D longer local observation
P2 fake-send / simulator delivery loop
P3 PE-2 design packet only
P4 controlled external ingress
P5 durable runtime integration
P6 controlled AI FLOW execution
P7 real delivery / ACK closure
P8 product and ops hardening
```

That is the fastest safe route. Slower on paper, faster in reality — because it avoids the classic “one heroic live jump, three days of cleaning glass off the floor” problem.
