# Dev Log — FlowWeaver Phase 30 Local Temporal Stub Activity Orchestration

## Scope

Approved phase: Phase 30 only.

Implementation branch/worktree:

```text
feat/flowweaver-phase30-temporal-stub-activity-orchestration
/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase30-temporal-stub-activity-orchestration
```

Strongest allowed verdict:

```text
ready_for_controlled_agent_activity_implementation_request
```

## Guardrails

- No production Gateway wiring.
- No Gateway-owned Worker lifecycle.
- No `Client.connect` helper or Temporal address ownership.
- No Gateway restart.
- No production config writes.
- No platform adapter mutation/access.
- No real agent/tool execution.
- No real delivery/render/send/edit/callback behavior.
- No delivery ACK updates.
- No subprocess, socket, daemon, service startup, or external lifecycle ownership.
- No raw prompt/message/tool/card/media/platform/private id/callback/credential/raw exception material in snapshots, history, reports, docs evidence, or user-visible output.

## Documentation Lookup

Current Temporal Python SDK docs were checked with Context7:

```text
npx -y ctx7@latest library temporalio "Python SDK WorkflowEnvironment Worker workflow.execute_activity activity.defn workflow query history retry policy cancellation"
selected: /temporalio/sdk-python

npx -y ctx7@latest docs /temporalio/sdk-python "Python SDK WorkflowEnvironment Worker workflow.execute_activity activity.defn workflow query history retry policy cancellation"
evidence: Workflow definitions use @workflow.defn/@workflow.run; Activity wrappers use @activity.defn; local tests can use WorkflowEnvironment and Worker; workflow queries are supported; activity calls use workflow.execute_activity with timeout and retry policy.
```

## RED Evidence

Initial RED command:

```bash
scripts/run_tests.sh tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py -q
```

Result:

```text
Phase 30 module import failed because the approved module did not exist yet.
```

This proved the Phase 30 module was absent before implementation.

## Verifier Note

The canonical `scripts/run_tests.sh` intentionally ignores `tests/integration` and applies `-m not integration`. After the missing-module RED, integration verification uses a direct hermetic pytest command without the integration ignore policy.

## GREEN Work Log

Implemented:

- Phase 30 contract descriptor and report validator/builder.
- Safe start-payload builder and validator.
- Temporal Activity wrappers for the Phase 29 plain callable stubs.
- `FlowWeaverTemporalStubActivityWorkflow` with the fixed Activity sequence.
- Caller-supplied-client start/reconcile helper.
- Duplicate-start reconciliation through sanitized snapshot comparison.
- Cancel update returning a sanitized final snapshot.
- No-leak history/snapshot tests.
- Source gate proving Worker/WorkflowEnvironment and live Gateway effects stay outside the module.

Implementation pitfall found during GREEN:

```text
Temporal payload conversion did not preserve the canonical dict key ordering required by the Phase 29 plain stubs. The Phase 30 Activity wrappers now validate Temporal-decoded payloads and rebuild canonical ordered dicts before calling Phase 29 stubs.
```

This preserves the stricter Phase 29 contract without weakening it for direct callers.

## Verification Log

Focused direct integration command:

```bash
$HOME/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py -q
```

Result:

```text
9 passed in 1.81s
```

Focused direct integration with xdist:

```bash
$HOME/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py -q
```

Result:

```text
9 passed in 1.86s
```

Non-integration regression command:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase5*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```

Result:

```text
674 passed in 6.24s
```

Patch hygiene:

```text
git diff --check: PASS
added-line static security scan: no output
```

## Review Status

Codex read-only blocker review:

```text
VERDICT: PASS
BLOCKERS:
- None
```

Independent blocker review initially returned:

```text
VERDICT: BLOCK
BLOCKERS:
- Phase 30 dev log RED evidence included raw missing-module exception text.
```

Fix applied:

```text
- Replaced raw exception evidence with a sanitized missing-module statement.
- Re-ran changed P30 docs added-line scan for raw exception markers: no output.
- Re-ran git diff --check: PASS.
```

Independent blocker-only re-review:

```text
VERDICT: PASS
BLOCKERS:
- None
```

## Final Candidate Verification

```text
P30 focused integration xdist: 9 passed in 1.83s
FlowWeaver non-integration regression: 674 passed in 5.32s
git diff --check: PASS
added-line static security scan: no output
changed P30 docs raw exception scan: no output
```
