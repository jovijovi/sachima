# Dev Log — FlowWeaver Phase 32 Controlled Delivery Activity and ACK Reconciliation

## Scope

Approved phase: Phase 32 only.

Implementation branch/worktree:

```text
feat/flowweaver-phase32-delivery-ack-activity
/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase32-delivery-ack-activity
```

Strongest allowed verdict:

```text
ready_for_narrow_ai_flow_pilot_request
```

## Guardrails

- No production Gateway wiring.
- No Gateway-owned Worker lifecycle.
- No `gateway/run.py` changes.
- No platform adapter mutation/access.
- No production config writes.
- No Gateway restart.
- No hidden delivery-surface factory.
- No `Client.connect` factory.
- No new agent/tool execution scope.
- No modification of the Phase 31 workflow.
- ACK updates only target initialized runtime delivery slots.
- Rich-card delivery state remains separate from final-text delivery state.
- No raw prompt/message/tool/card/media/platform/private id/callback/credential/raw exception material in snapshots, history, reports, docs evidence, or user-visible output.

## Documentation Lookup

Current Temporal Python SDK usage follows the already validated Phase 31 local/staging pattern:

```text
Workflow definitions use @workflow.defn/@workflow.run.
Activity functions use @activity.defn.
Local tests can use WorkflowEnvironment and Worker.
Workflow queries are supported.
Activity calls use workflow.execute_activity with timeout and retry policy.
Worker/WorkflowEnvironment construction remains test-only.
```

Codex read-only scope review returned:

```text
VERDICT: PASS
BLOCKERS: None
Key recommendation: keep P32 as a separate local/staging harness that consumes sanitized P31 result metadata. Compose P31 and P32 only in Phase 33.
```

## RED Evidence

Initial RED command:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_delivery_activity.py -q
```

Result:

```text
Phase 32 module import failed because the approved module did not exist yet.
```

This proved the Phase 32 module was absent before implementation.

## GREEN Work Log

Implemented:

- `gateway/flowweaver_delivery_activity.py`
- exact Phase 32 contract descriptor;
- safe delivery Activity request builder/validator;
- `deliver_controlled_artifact(...)` with explicit delivery-surface and runtime-control-surface injection;
- `build_deliver_artifact_activity(...)` Activity factory;
- sanitized result/snapshot/report validators;
- local/staging `FlowWeaverDeliveryActivityWorkflow` harness;
- disabled/default-off zero-call path;
- initialized-slot-only ACK update validation;
- deterministic bounded prefix ACK target validation;
- duplicate ACK replay handling;
- rich-card/final-text surface separation;
- delivery surface failure, timeout, and cancellation mappings;
- history/snapshot no-leak tests.

Important design decisions:

```text
1. P32 remains separate from the Phase 31 workflow. Phase 33 is the first place to compose the controlled execution and delivery seams.
2. Unsafe payload material must not be placed in Temporal workflow start inputs. Unsafe negative tests stay at the plain function/Activity boundary.
3. Delivery ACK updates are sanitized runtime refs only and must match initialized delivery slots in prefix order.
4. Rich-card ACKs never mark final text as sent. Final text has its own slot and surface state.
5. Temporal may reorder dict keys in history payload conversion. Public validators keep canonical field-order strictness; Workflow/Activity-internal validators accept exact key sets at Temporal boundaries and rebuild canonical sanitized objects before downstream validation.
```

## Verification Log

Focused P32 unit+integration command:

```bash
python -m pytest -q tests/gateway/test_flowweaver_delivery_activity.py tests/integration/test_flowweaver_phase32_delivery_activity_ack_reconciliation.py
```

Result:

```text
19 passed in 3.16s
```

P30/P31/P32 integration command:

```bash
python -m pytest -o addopts= -n 4 tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py tests/integration/test_flowweaver_phase31_agent_execution_activity.py tests/integration/test_flowweaver_phase32_delivery_activity_ack_reconciliation.py -q
```

Result:

```text
13 passed in 1.94s
```

FlowWeaver regression command:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase5*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```

Result:

```text
703 passed in 5.28s
```

Static checks:

```text
git diff --check: pass
custom changed-file/source/doc scan: STATIC_SCAN_PASS, changed_count=19, security_findings=0
```

## Review Status

Codex full review initially returned BLOCK for two issues:

```text
1. Delivered-result validation accepted forged final_text surface state without a matching final_text ACK.
2. Public snapshot validation accepted reordered nested fixed fields for counts/activity_sequence.
```

Regression probes were added and verified RED before the fix:

```text
2 failed: reordered nested snapshot fields and forged final_text surface state were accepted.
```

Fixes applied:

```text
1. Result validation now recomputes surface_state from sanitized ack_updates.
2. Public snapshot validation now propagates exact_order into counts and activity_sequence; key-set tolerance remains internal-only for Temporal boundary validation.
```

Post-fix review:

```text
Codex blocker-only re-review: PASS, blockers none.
Independent fresh-context review: passed=true, security_concerns=[], logic_errors=[]; reviewer also reran focused tests, git diff --check, and blocker probes.
```
