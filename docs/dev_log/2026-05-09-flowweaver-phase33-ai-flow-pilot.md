# Dev Log — FlowWeaver Phase 33 Narrow AI FLOW Pilot

## Scope

Approved phase: Phase 33 only.

Implementation branch/worktree:

```text
feat/flowweaver-phase33-ai-flow-pilot
/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase33-ai-flow-pilot
```

Strongest allowed verdict:

```text
ready_for_separate_production_enablement_decision
```

## Guardrails

- No production Gateway wiring.
- No `gateway/run.py` changes.
- No platform adapter mutation/access.
- No production config writes.
- No Gateway restart.
- No hidden executor, delivery surface, runtime reconciler, or Gateway factory.
- No Gateway-owned Worker/service lifecycle in production code.
- No `Client.connect` factory.
- No production agent execution or production delivery enablement.
- Pilot success cannot imply production enablement.
- No raw prompt/tool/card/media/platform/private id/callback/credential/raw exception material in snapshots, history, reports, decision packets, docs evidence, or user-visible output.

## Codex Architecture Review

Read-only Codex architecture review returned:

```text
VERDICT: PASS
BLOCKERS: none
Recommended scope: add gateway/flowweaver_ai_flow_pilot.py, P33 unit/integration tests, runbook, plan, dev log, and narrow guard maintenance.
```

## RED Evidence

Initial RED command:

```bash
python -m pytest -q tests/gateway/test_flowweaver_ai_flow_pilot.py::test_phase33_exposes_contract_for_controlled_ai_flow_pilot_only tests/integration/test_flowweaver_phase33_ai_flow_pilot.py::test_phase33_local_temporal_worker_composes_agent_execution_delivery_and_decision_packet
```

Result:

```text
Phase 33 module import failed because the approved module did not exist yet.
```

This sanitized RED evidence proved the Phase 33 module was absent before implementation without recording raw exception text.

## GREEN Work Log

Implemented:

- `gateway/flowweaver_ai_flow_pilot.py`
- exact Phase 33 contract descriptor;
- safe pilot request builder/validator;
- local/staging `FlowWeaverAIFlowPilotWorkflow`;
- P31 claim validation and controlled agent execution Activity composition;
- P32 controlled delivery Activity composition;
- Phase 33 no-throw sanitized Activity wrappers so caller-supplied Activity failures become stable error-code results before Temporal history persistence;
- sanitized pilot snapshot validator;
- sanitized operator decision packet validator;
- sanitized report builder/validator;
- default-off no-op path;
- agent failure/cancel paths that skip delivery;
- ACK duplicate/idempotency evidence;
- no-leak integration tests for history JSON and event bytes.

Important design decisions:

```text
1. P33 composes P31 and P32 only through their approved Activity boundaries.
2. The new module owns no Worker/client/service lifecycle; tests supply the Worker.
3. Public validators stay exact-order strict. Integration tests canonicalize Temporal-decoded dicts before public validation.
4. Phase 33 registers no-throw wrappers rather than raw caller Activities, so raw exceptions cannot be persisted as Temporal Activity failures.
5. Decision packets can only request a later separate production-enablement decision; they cannot claim production readiness or activation.
```

## Verification Log

Focused unit command:

```bash
python -m pytest -q tests/gateway/test_flowweaver_ai_flow_pilot.py
```

Result:

```text
8 passed in 2.90s
```

Focused integration command:

```bash
python -m pytest -o addopts= -q tests/integration/test_flowweaver_phase33_ai_flow_pilot.py
```

Result:

```text
8 passed in 2.33s
```

P30/P31/P32/P33 integration command:

```bash
python -m pytest -o addopts= -n 4 tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py tests/integration/test_flowweaver_phase31_agent_execution_activity.py tests/integration/test_flowweaver_phase32_delivery_activity_ack_reconciliation.py tests/integration/test_flowweaver_phase33_ai_flow_pilot.py -q
```

Result:

```text
21 passed in 2.31s
```

FlowWeaver regression command:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase5*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```

Result:

```text
711 passed in 5.58s
```

Static checks:

```text
git diff --check: pass
custom changed-file/source/doc scan: STATIC_SCAN_PASS, changed_count=20, security_findings=0
```

## Review Status

Fresh Codex blocker review found one blocker: public report construction could accept forged `pilot_completed` snapshot/decision evidence when derived activity sequence and evidence disagreed.

Fix applied:

- added RED probe for forged success snapshot, false evidence flags, forged delivery count, known or unknown non-null success activity error codes, duplicate delivery refs, forged zero ACK totals, missing final-text delivery surface, and workflow-path claim success with unknown non-null error code;
- made snapshot semantics recompute activities/artifacts/deliveries from sanitized snapshot lists;
- made ACK totals recompute from applied/duplicate/rejected counts and require successful delivery ACK totals to match unique delivery refs;
- made decision evidence match sanitized activity sequence (`execute_agent_turn` executed and `deliver_artifact` delivered);
- made success snapshots require the exact validated/executed/delivered sequence, delivered intent state, final-text delivery evidence, and null activity error codes for all success statuses;
- made workflow activity recording reject unknown non-null error codes before they can be normalized away;
- made decision packets reject missing no-leak/progress evidence and impossible phase32-without-phase31 claims.

Fresh-context blocker review then found one additional blocker:

```text
Non-success pilot decision packets could still carry the ready-for-production-enablement-decision verdict, and public snapshot validation accepted forged non-success artifact/delivery refs not supported by the activity sequence.
```

Second fix applied:

- added RED probe proving non-completed decision packets must use `not_ready_for_production_enablement` and must reject the ready verdict;
- made generated and validated decision packets use `ready_for_separate_production_enablement_decision` only for `pilot_completed`;
- made all non-completed, disabled, running, failed, timed-out, cancelled, rejected, and partial packets use `not_ready_for_production_enablement`;
- strengthened snapshot semantics so artifact refs require executed agent activity and delivery refs require a delivery activity;
- made `agent_execution_failed` reject forged artifact/delivery refs and counts;
- updated running/disabled/timed-out/cancelled integration assertions to prove their decision packets stay non-ready.

Post-second-fix verification:

```text
P33 focused unit: 8 passed in 2.89s
P33 focused integration: 8 passed in 2.34s
P30/P31/P32/P33 integration: 21 passed in 2.28s
FlowWeaver regression: 711 passed in 5.53s
git diff --check: pass
```

Final blocker review found one additional blocker:

```text
Caller-supplied Temporal Activities could still throw uncaught raw exceptions; Temporal would persist those Activity failures before workflow-level sanitization could run.
```

Final fix applied:

- added `build_flowweaver_ai_flow_pilot_activity_wrappers(...)`;
- registered Phase 33 no-throw wrappers for `validate_claim_check_ref`, `execute_agent_turn`, and `deliver_artifact`;
- added a RED/GREEN integration test where a caller claim Activity raises raw exception material, and verified the workflow returns a sanitized non-ready snapshot without history leakage;
- updated plan/runbook/contract evidence to require wrapper registration instead of direct raw Activity registration.

Post-final-fix verification:

```text
P33 focused unit: 8 passed in 2.90s
P33 focused integration: 8 passed in 2.33s
P30/P31/P32/P33 integration: 21 passed in 2.31s
FlowWeaver regression: 711 passed in 5.58s
git diff --check: pass
custom changed-file/source/doc scan: STATIC_SCAN_PASS, changed_count=20, security_findings=0
```

Final fresh-context blocker re-review: PASS, blockers none.
