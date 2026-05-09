# FlowWeaver Phase 31 Controlled Agent Execution Activity Plan

## Scope

Approved phase: Phase 31 only.

Branch/worktree:

```text
feat/flowweaver-phase31-agent-execution-activity
/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase31-agent-execution-activity
```

Strongest allowed verdict:

```text
ready_for_controlled_delivery_activity_request
```

This phase adds a controlled, non-production agent/tool execution Activity boundary. It does not approve production agent execution, production Gateway wiring, production delivery, delivery ACK control, config writes, Gateway restart, platform adapter mutation, or service lifecycle ownership.

## Objective

Replace the Phase 29 fake `execute_agent_turn` proof with a Phase 31 boundary that can call a caller-injected executor in local/staging tests while keeping durable state sanitized.

Raw prompt/tool/model material may exist only inside the Activity process and only through the injected executor path. Workflow history, snapshots, reports, docs, tests, and user-visible output must contain only safe runtime ids, claim-check refs, counts, digests, statuses, and stable error codes.

## Allowed Behavior

Phase 31 may:

- define a safe execution request and result contract;
- define an explicit injected executor boundary;
- build a Temporal Activity wrapper from a caller-supplied executor;
- run a local/staging Workflow harness that validates a claim ref and executes the controlled Activity;
- convert executor output into sanitized artifact metadata;
- map executor exceptions, timeouts, cancellations, and auth/config failures to stable error codes;
- inspect local Temporal history for no-leak behavior.

## Forbidden Behavior

Phase 31 must not:

- instantiate global `AIAgent` objects;
- create hidden executor factories;
- import or call Gateway adapters;
- call Gateway rendering or delivery;
- update delivery ACKs;
- write production config;
- restart Gateway;
- mutate platform adapters;
- own Worker, service, daemon, Docker, socket, or subprocess lifecycle;
- persist or display raw prompt text, tool output, model bodies, card JSON, media paths, platform/private ids, callback payloads, credentials, or raw exception text.

## Planned Files

```text
gateway/flowweaver_agent_execution_activity.py
tests/gateway/test_flowweaver_agent_execution_activity.py
tests/integration/test_flowweaver_phase31_agent_execution_activity.py
docs/runbooks/flowweaver-agent-execution-activity.md
docs/plans/2026-05-09-flowweaver-phase31-agent-execution-activity.md
docs/dev_log/2026-05-09-flowweaver-phase31-agent-execution-activity.md
```

Guard maintenance only if required:

```text
tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py
```

## Public Entrypoints

```python
def describe_flowweaver_agent_execution_activity_contract() -> dict[str, object]: ...
def build_flowweaver_agent_execution_request(...) -> dict[str, object]: ...
def validate_flowweaver_agent_execution_request(value: object) -> dict[str, object]: ...
async def execute_controlled_agent_turn(..., executor: Callable) -> dict[str, object]: ...
def build_execute_agent_turn_activity(*, executor: Callable) -> Callable: ...
def validate_flowweaver_agent_execution_result(value: object) -> dict[str, object]: ...
def validate_flowweaver_agent_execution_snapshot(value: object) -> dict[str, object]: ...
def build_flowweaver_agent_execution_activity_report(...) -> dict[str, object]: ...
def validate_flowweaver_agent_execution_activity_report(value: object) -> dict[str, object]: ...
```

Local/staging Workflow harness:

```text
FlowWeaverAgentExecutionActivityWorkflow
```

## TDD Plan

1. RED: add focused tests importing the new module and asserting the executor boundary.
2. GREEN: implement the smallest explicit injected-executor boundary and validators.
3. Add fail-closed tests for unsafe claim refs and raw validated claim material.
4. Add executor success/failure/timeout/cancel tests proving stable sanitized outputs.
5. Add local Temporal Worker tests proving history bytes and JSON do not contain raw material.
6. Maintain prior phase changed-file guards with exact P31 paths only.
7. Run focused P31 tests, P30 integration regression, FlowWeaver regression, static scans, and independent blocker reviews.

## Verification Commands

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_agent_execution_activity.py -q
$HOME/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= tests/integration/test_flowweaver_phase31_agent_execution_activity.py -q
$HOME/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 tests/integration/test_flowweaver_phase31_agent_execution_activity.py -q
$HOME/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py tests/integration/test_flowweaver_phase31_agent_execution_activity.py -q
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase5*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```
