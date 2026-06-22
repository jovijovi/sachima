# FlowWeaver Phase 30 Local Temporal Stub Activity Orchestration Plan

## Approval

Approved by 狗哥: implement Phase 30 only — local Temporal stub Activity orchestration.

## Objective

Wrap the Phase 29 plain callable stubs in local/staging Temporal Activity wrappers and prove a local workflow can execute the fixed sequence:

```text
validate_claim_check_ref -> execute_agent_turn -> deliver_artifact
```

Strongest allowed verdict:

```text
ready_for_controlled_agent_activity_implementation_request
```

This permits a later Phase 31 approval request. It does not approve production Gateway wiring, production delivery, production agent/tool execution, platform adapter mutation, config writes, Gateway restart, or broad enablement.

## Planned Files

Create:

- `gateway/flowweaver_temporal_stub_activity_orchestration.py`
- `tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py`
- `docs/runbooks/flowweaver-temporal-stub-activity-orchestration.md`
- `docs/plans/2026-05-09-flowweaver-phase30-temporal-stub-activity-orchestration.md`
- `docs/dev_log/2026-05-09-flowweaver-phase30-temporal-stub-activity-orchestration.md`

Possible guard maintenance only:

- prior FlowWeaver phase changed-file allowlists.

## Boundaries

Phase 30 may:

- define Temporal Activity wrappers for the three Phase 29 plain stubs;
- define a local/staging workflow that executes the wrappers in fixed order;
- expose a caller-supplied-client start/reconcile helper for local/staging tests;
- use `WorkflowEnvironment` and Worker construction only in integration tests;
- query sanitized snapshots;
- inspect history JSON and serialized event bytes for no-leak evidence;
- handle duplicate start by querying a sanitized existing snapshot before accepting it as idempotent.

Phase 30 must not:

- connect a Temporal client by address;
- construct or run a Worker outside the integration test harness;
- let Gateway own runtime lifecycle;
- write production config;
- restart Gateway;
- mutate platform adapters;
- call real agents/tools;
- render, send, edit, callback, or ACK delivery;
- persist raw prompt, tool output, card JSON, media path, platform/private ids, callback payload, credentials, or raw exception text.

## TDD Tasks

1. Write RED integration tests for missing Phase 30 module and entrypoints.
2. Add safe start payload, descriptor, snapshot, report, no-leak, duplicate-start, cancellation, and source-scope tests.
3. Implement minimal wrappers/workflow/facade to pass tests.
4. Add runbook/dev log.
5. Patch only changed-file guard allowlists needed by the new Phase 30 files.
6. Run focused integration verification directly because the canonical wrapper intentionally ignores `tests/integration`.
7. Run FlowWeaver gateway/prototype regression through `scripts/run_tests.sh`.
8. Run code review gates before commit/PR.

## Verification Commands

Focused integration, direct hermetic command because `scripts/run_tests.sh` excludes integration tests:

```bash
$HOME/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py -q
```

Non-integration regression:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase5*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```

If the wrapper reports `no tests ran` for integration selectors, treat that as verifier policy, not product evidence, and use the direct hermetic command above.
