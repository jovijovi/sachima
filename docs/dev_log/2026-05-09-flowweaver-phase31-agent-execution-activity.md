# Dev Log — FlowWeaver Phase 31 Controlled Agent Execution Activity

## Scope

Approved phase: Phase 31 only.

Implementation branch/worktree:

```text
feat/flowweaver-phase31-agent-execution-activity
/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase31-agent-execution-activity
```

Strongest allowed verdict:

```text
ready_for_controlled_delivery_activity_request
```

## Guardrails

- No production Gateway wiring.
- No production agent execution.
- No Gateway-owned Worker lifecycle.
- No hidden executor factory.
- No global `AIAgent` instance.
- No Gateway restart.
- No production config writes.
- No platform adapter mutation/access.
- No real delivery/render/send/edit/callback behavior.
- No delivery ACK updates.
- No subprocess, socket, daemon, service startup, or external lifecycle ownership.
- No raw prompt/message/tool/model/card/media/platform/private id/callback/credential/raw exception material in snapshots, history, reports, docs evidence, or user-visible output.

## Documentation Lookup

Current Temporal Python SDK docs were checked with Context7:

```text
ctx7 library temporalio python
selected: /temporalio/sdk-python

ctx7 docs /temporalio/sdk-python "Python SDK execute_activity activity.defn workflow update validator query ActivityEnvironment Worker WorkflowEnvironment"
evidence: Workflow definitions use @workflow.defn/@workflow.run; Activity functions use @activity.defn; local tests can use WorkflowEnvironment and Worker; workflow queries are supported; activity calls use workflow.execute_activity with timeout and retry policy; update validators exist but are not needed for this phase's terminal local harness.
```

## RED Evidence

Initial RED command:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_agent_execution_activity.py -q
```

Result:

```text
Phase 31 module import failed because the approved module did not exist yet.
```

This proved the Phase 31 module was absent before implementation.

## GREEN Work Log

Implemented:

- `gateway/flowweaver_agent_execution_activity.py`
- exact Phase 31 contract descriptor;
- safe execution request builder/validator;
- `execute_controlled_agent_turn(...)` with explicit executor injection;
- `build_execute_agent_turn_activity(...)` Activity factory;
- sanitized result/snapshot/report validators;
- local/staging `FlowWeaverAgentExecutionActivityWorkflow` harness;
- executor success/failure/timeout/cancel mappings;
- history/snapshot no-leak tests;
- exact changed-file guard maintenance for Phase 30.

Important design decision:

```text
Unsafe claim-check material must be rejected before Temporal workflow start whenever possible. Integration tests must not intentionally start a workflow with unsafe payload material, because the start payload itself is durable history input.
```

This kept unsafe-input tests at the plain function/Activity boundary and kept local Temporal history tests safe-only.

Bug found during GREEN:

```text
Retry classification for rejected results must use stable error_code, not only status. Otherwise executor_failed and invalid input both look like rejected but have different retry classes.
```

Fix:

```text
Result validation now derives retry_class from sanitized error_code.
```

## Verification Log

Focused unit command:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_agent_execution_activity.py -q
```

Result:

```text
10 passed in 1.44s
```

Focused integration command:

```bash
$HOME/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= tests/integration/test_flowweaver_phase31_agent_execution_activity.py -q
```

Initial result:

```text
One test failed because the timeout fixture expected one tool call while the fake executor safely reported two.
```

Resolution:

```text
Updated the test expectation to the fake executor's sanitized count; no production code change was required.
```

Focused integration rerun:

```text
2 passed in 1.24s
```

## Final Candidate Verification

```text
P31 focused unit: 10 passed in 1.28s
P31 focused integration xdist: 2 passed in 1.68s
P30 + P31 integration xdist: 11 passed in 1.85s
FlowWeaver non-integration regression: 684 passed in 5.30s
git diff --check: PASS
static forbidden-surface scan: PASS
docs raw exception scan: PASS
```

## Review Status

Codex read-only blocker review initially returned:

```text
VERDICT: BLOCK
BLOCKERS:
- Executor-raised asyncio.CancelledError could escape because it is not caught by Exception on this runtime.
- Tests covered cancellation as an executor result payload, not as an executor cancellation exception.
```

Fix applied:

```text
- Added a RED regression with an injected executor raising asyncio.CancelledError carrying raw-looking cancellation text.
- Updated execute_controlled_agent_turn to catch asyncio.CancelledError and return sanitized status=cancelled, error_code=executor_cancelled, retry_class=non_retryable.
- Focused cancellation regression: 1 passed.
```

Post-fix verification:

```text
P31 focused unit: 10 passed in 1.29s
P31 focused integration xdist: 2 passed in 1.64s
P30 + P31 integration xdist: 11 passed in 1.94s
FlowWeaver non-integration regression: 684 passed in 5.18s
git diff --check: PASS
static forbidden-surface scan: PASS
docs raw exception scan: PASS
```

Codex blocker-only re-review:

```text
VERDICT: PASS
BLOCKERS:
- None
```

Independent blocker review:

```text
VERDICT: PASS
BLOCKERS:
- None
```
