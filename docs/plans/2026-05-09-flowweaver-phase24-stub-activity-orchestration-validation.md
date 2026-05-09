# FlowWeaver Phase 24 — Stub Activity Orchestration Validation

## Goal

Implement a pure synchronous validation report builder for the Phase 23 stub Activity orchestration artifact.

## Architecture

Phase 24 consumes the Phase 23 contract descriptor and an already-built Phase 23 orchestration result. It validates exact prior-phase shapes, canonical stub sequence, a single `agent_input` claim-check input, empty side effects, and empty delivery ACK updates, then returns a sanitized high-level report only.

Phase 24 must not call the Phase 23 orchestrator internally. The caller provides the Phase 23 result. This keeps P24 as a validator/gate, not a runtime owner.

## Scope

Phase 24 creates only:

- `gateway/flowweaver_stub_activity_orchestration_validation.py`
- `tests/gateway/test_flowweaver_stub_activity_orchestration_validation.py`
- `docs/runbooks/flowweaver-stub-activity-orchestration-validation.md`
- this plan and the paired dev log
- changed-file allowlist maintenance in existing FlowWeaver guard tests only if needed

The strongest allowed verdict is:

```text
ready_for_stub_activity_boundary_contract_design
```

That verdict is weaker than production activation. It only means a later phase may design the next boundary contract. It does not enable Temporal activity execution, real agent/tool execution, Gateway delivery, ACK control, or production wiring.

## Entry Points

```python
def describe_flowweaver_stub_activity_orchestration_validation_contract() -> dict[str, object]: ...
def validate_flowweaver_stub_activity_orchestration_validation_report(value: object) -> dict[str, object]: ...
def build_flowweaver_stub_activity_orchestration_validation_report(*, contract_descriptor: object, orchestration_result: object) -> dict[str, object]: ...
```

## Validation Rules

P24 must verify:

- the Phase 23 contract descriptor is exact;
- the Phase 23 orchestration result is exact according to its validator;
- the activity sequence remains exactly:
  - `validate_claim_check_ref` / `stubbed`
  - `execute_agent_turn` / `stubbed`
  - `deliver_artifact` / `planned`
- the execution request has a single input ref with `kind == "agent_input"`;
- `delivery_ack_updates == []`;
- all nested `side_effects == []` where present;
- the report does not echo the full execution request, raw prompt, raw message text, tool output, card JSON, media path, platform/private ID, callback payload, credential-shaped value, raw exception text, or Phase 23 raw fixture values;
- errors fail closed to sanitized report codes.

## Boundary Rules

- No Temporal client construction.
- No Worker lifecycle.
- No `WorkflowEnvironment`.
- No Gateway hook changes.
- No Gateway adapter access or mutation.
- No production config writes.
- No Gateway restart requirement.
- No real Temporal Activity execution.
- No real agent or tool execution.
- No real delivery ACK updates.
- No real send/edit/render/callback control.
- No file, subprocess, socket, Docker, daemon, or service startup.
- No call to `orchestrate_flowweaver_stub_activities` from the P24 production module.
- No raw prompt/message/tool/card/media/platform/private id/callback/credential/raw exception material in outputs, logs, fixtures, reports, docs, or user-visible output.

## Acceptance

Phase 24 is accepted only if:

- RED/GREEN tests prove the validation module was absent before implementation and then passes;
- the report builder accepts a valid Phase 23 descriptor/result and returns only a high-level sanitized report;
- malformed Phase 23 descriptor/result inputs fail closed without echoing raw material;
- canonical sequence/input-kind/ACK/side-effect gates are covered by regression tests;
- source scans prove no runtime lifecycle, real execution, Gateway wiring, or orchestrator-call escape hatch;
- local FlowWeaver verification passes;
- Codex blocker review returns PASS;
- PR CI is green and merged.

## Verification

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_orchestration_validation.py -q
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```
