# FlowWeaver Phase 23 — Stub Activity Orchestration

## Goal

Implement the first pure stub Activity orchestration helper after the Phase 22 delivery / agent execution contract gate.

## Scope

Phase 23 creates only:

- `gateway/flowweaver_stub_activity_orchestration.py`
- `tests/gateway/test_flowweaver_stub_activity_orchestration.py`
- `docs/runbooks/flowweaver-stub-activity-orchestration.md`
- this plan and the paired dev log
- changed-file allowlist maintenance in existing FlowWeaver guard tests

The strongest allowed verdict is:

```text
ready_for_stub_activity_orchestration_validation
```

That verdict is weaker than production activation. It only means a later phase may validate the stub orchestration boundary. It does not enable production behavior.

## Stub Sequence

The fixed planned/stubbed sequence is:

```text
validate_claim_check_ref
execute_agent_turn
deliver_artifact
```

This sequence is metadata only. Phase 23 does not run Temporal Activities, execute an agent, call tools, deliver artifacts, or create delivery acknowledgements.

## Entry Points

```python
def describe_flowweaver_stub_activity_orchestration_contract() -> dict[str, object]: ...
def validate_flowweaver_stub_activity_orchestration_result(value: object) -> dict[str, object]: ...
def orchestrate_flowweaver_stub_activities(*, execution_request: object, contract_descriptor: object) -> dict[str, object]: ...
```

## Boundary Rules

- No Temporal client construction.
- No Worker lifecycle.
- No Gateway hook changes.
- No Gateway adapter mutation.
- No production config writes.
- No Gateway restart requirement.
- No real agent or tool execution.
- No real delivery ACK updates; `delivery_ack_updates` must remain `[]`.
- No real send/edit/render/callback control.
- No file, subprocess, socket, Docker, daemon, or service startup.
- No raw prompt, message text, tool output, card JSON, media path, platform/private id, callback payload, credential-shaped value, or raw exception text in outputs, logs, fixtures, reports, docs, or user-visible output.

## Acceptance

Phase 23 is accepted only if:

- RED/GREEN tests prove the module was absent before implementation and then passes;
- the helper validates the Phase 22 contract descriptor before consuming requests;
- the helper accepts only the canonical single claim-check input kind `agent_input` before echoing request metadata;
- the helper returns P22-built execution result and progress snapshot objects;
- `delivery_ack_updates` stays empty;
- source scans prove no runtime lifecycle or execution escape hatch;
- local FlowWeaver verification passes;
- Codex blocker review returns PASS;
- PR CI is green and merged.

## Verification

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_orchestration.py -q
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```
