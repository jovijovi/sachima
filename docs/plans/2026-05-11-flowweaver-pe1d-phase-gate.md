# FlowWeaver PE-1D Phase Gate — Phase Gate Drift Control Validation

> **For Hermes:** This document applies the `phase-gate-drift-control` skill to the next Sachima phase. It is a phase-gate / readiness artifact plus exact changed-file guard allowlist maintenance only. It does not run PE-1D, write production config, restart/reload Gateway, mutate platform adapters, start Temporal services or Workers, enable PE-2, enable live/default-on behavior, enable real external ingress, enable production delivery, or expand production agent/tool execution.

## Phase Identity

- Phase ID: `flowweaver-pe1d-longer-controlled-local-observation`
- Skill validation level: **Level 3 — High Risk**
- Owner / DRI: `Hermes operator with Dog Brother approval`
- Parent goal document: `GOAL.md`
- Gap / capability addressed: `docs/sachima-final-goal-gap-analysis.md` — Phase A / P1 longer controlled local observation
- Prior evidence required:
  - `docs/plans/2026-05-11-flowweaver-pe1d-pe2-readiness-decision-packet.md`
  - PE-1A local ingress smoke PASS
  - PE-1B short-window observation PASS
  - PE-1C evidence packet and rollback drill PASS

## Goal Trace

```text
Goal: Sachima becomes a safe, durable, observable, recoverable AI workbench inside a custom IM channel.
Gap: PE-1 has short local observation evidence, but not longer-window observation confidence.
Phase: P1 / PE-1D longer controlled local observation.
Task: Prepare a Level 3 phase gate before requesting or running PE-1D.
Test: Validate gate manifest, changed-file guard, no-leak/approval wording, and fresh reviews.
Evidence: This gate, manifest, tail register, dev log, validator output, PR/CI if merged.
Decision: Ready to request PE-1D only after exact approval text; not approval to execute PE-1D.
```

## Scope

### In Scope

- Apply the `phase-gate-drift-control` skill to a real Sachima next-phase candidate.
- Create a Level 3 phase gate for PE-1D.
- Create a machine-readable manifest.
- Create a Tail Register.
- Add AGENTS.md trigger guidance so future Sachima phase work loads the skill.
- Maintain existing FlowWeaver changed-file guards with exact allowlist entries for these new docs only.
- Validate that the skill's templates and validator catch machine-checkable readiness facts.

### Explicit Non-Goals / Non-Approvals

This validation does **not** approve:

```text
pe1d_execution
pe2_implementation
pe2_live_default_on
real_external_sachima_ingress
production_delivery_control
production_agent_tool_execution_expansion
production_config_write
gateway_restart_or_reload
platform_adapter_mutation
gateway_owned_temporal_lifecycle
real_send_url_configuration
Temporal_service_or_Worker_startup
```

## Risk Axes Changed

This docs-only validation changes no runtime axis. The future PE-1D phase would touch only controlled observation volume.

- [x] Documentation / phase governance
- [ ] Ingress expansion
- [ ] Delivery expansion
- [ ] Runtime lifecycle expansion
- [ ] Agent/tool execution expansion
- [ ] Data access / retention expansion
- [ ] Permissions / auth expansion
- [ ] External APIs
- [ ] Config writes / service restart
- [ ] Irreversible operation

## Definition of Ready for PE-1D Request

PE-1D may be requested only when all of these are true:

- [x] `GOAL.md` and gap analysis point to PE-1D as the next safe behavior-bearing phase.
- [x] PE-1D / PE-2 readiness packet says PE-1D is conditional GO for separate approval.
- [x] Exact approval text is known: `approve_pe1d_longer_controlled_sachima_local_observation_window`.
- [x] Non-goals / non-approvals are explicit.
- [x] Risk axes are listed.
- [x] Blast radius is bounded to loopback/local controlled observation.
- [x] Kill criteria are defined.
- [x] Manifest and Tail Register exist.
- [ ] Dog Brother gives the exact PE-1D approval text.

## PE-1D Execution Tasks Once Separately Approved

1. Confirm Gateway/Sachima listener baseline without changing config.
2. Capture baseline observation/workflow counts.
3. Run a longer loopback-only signed allowlisted turn set.
4. Run unsigned, bad-signature, non-allowlisted, duplicate, replay, disabled-policy, and restore probes.
5. Verify observation/workflow deltas match only accepted allowlisted turns.
6. Verify runtime operations remain exactly `start_transaction` / `query_transaction`.
7. Verify no Temporal service/Worker startup.
8. Verify no send URL / real outbound delivery.
9. Run no-leak scan over shadow files, evidence packet, docs, and logs.
10. Produce PE-1D evidence packet and score.
11. Run two fresh reviews: goal consistency and boundary/security.
12. Decide whether P2 fake-send/simulator can be requested.

## Acceptance Standards for This Skill Validation

- `phase-gate-drift-control` chooses Level 3 for PE-1D and explains why.
- The phase gate records the full Goal -> Gap -> Phase -> Task -> Test -> Evidence -> Decision chain.
- The manifest is machine-validated by `validate_phase_gate.py`.
- The Tail Register has no naked TODOs.
- Non-goals prevent accidental PE-1D execution or PE-2/live implication.
- Drift checks distinguish this docs-only validation from actual PE-1D execution.
- Fresh review finds no blocker in the skill application.

## Acceptance Checklist

- [x] Skill loaded and applied.
- [x] Level selected: Level 3.
- [x] Phase gate created.
- [x] Manifest created.
- [x] Tail Register created.
- [x] Non-goals / non-approvals listed.
- [x] Kill criteria listed.
- [x] Blast radius listed.
- [x] Manifest validator passes.
- [x] Project guard/doc verification passes.
- [x] Fresh-context reviews report blockers = 0 after blocker fixes.
- [x] Dev log captures evidence and skill findings.

## Kill Criteria for Future PE-1D Execution

Stop PE-1D immediately if any of these happen:

- raw message text, platform ID, credential-shaped value, card JSON, media path, tool output, or raw exception text appears in evidence/logs/shadow state;
- unsigned, bad-signature, non-allowlisted, duplicate, replay, or disabled-policy probe creates observation/workflow delta;
- runtime operation other than `start_transaction` / `query_transaction` appears;
- Temporal service/Worker starts;
- any real send URL or outbound delivery path is used;
- Gateway restart/reload or production config write becomes necessary without separate approval;
- rollback/disable cannot stop new observation starts;
- fresh review reports a blocker.

## Blast Radius for Future PE-1D Execution

```text
environments: local loopback Sachima Gateway only
max_users: 1 narrow test user
max_requests: defined by PE-1D execution plan before run
max_runtime_minutes: bounded short observation window, not continuous production monitoring
max_delivery_attempts: 0
allowed_data_categories: synthetic/sanitized metadata only
rollback_authority: Dog Brother-approved Hermes operator
rollback_method: disable observation config / remove runtime hook / restore backup as applicable
```

## Scoring Rubric for This Skill Validation

| Category | Points | Evidence |
|---|---:|---|
| Correct level selection | 15 | Level 3 justified by production-adjacent observation and rollback/no-leak risk. |
| Trace-chain completeness | 15 | Goal, gap, phase, task, test, evidence, decision recorded. |
| Non-goal containment | 20 | Explicit non-approvals block PE-1D execution and PE-2/live drift. |
| Manifest validation usefulness | 20 | Validator checks machine-verifiable gate fields. |
| Tail Register usefulness | 10 | Tail items are classified; no naked TODOs. |
| Reviewability / operator handoff | 20 | Artifacts are concise enough for fresh reviewers and future operators. |

Total readiness score for skill validation before fresh review: **90/100**.

## Tail Closure

- Tail Register path: `docs/plans/2026-05-11-flowweaver-pe1d-tail-register.md`
- BLOCKER items open: none for this docs-only skill validation
- NEXT_PHASE items carried: exact PE-1D execution approval and evidence run
- WATCH items: validator dependency/false-positive behavior under real PE-1D evidence
- PARKED items: PE-2/live/real delivery/external ingress

## Decision

- Approved now: docs-only skill validation artifacts and exact changed-file guard allowlist maintenance.
- Still not approved: PE-1D execution, PE-2 implementation, live/default-on, real external ingress, production delivery, production agent/tool execution, config writes, Gateway restart/reload, platform adapter mutation, Temporal service/Worker startup.
- Next allowed request: `approve_pe1d_longer_controlled_sachima_local_observation_window`.
