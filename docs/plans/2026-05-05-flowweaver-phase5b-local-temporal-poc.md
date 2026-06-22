# FlowWeaver Phase 5B Local Temporal POC Implementation Plan

> **For Hermes:** User asked to execute the next phase after Phase 5A. This document is the Phase 5B design gate. Do not write implementation code until the user approves this plan.

**Goal:** Build a local-only Temporal proof of concept for FlowWeaver durable orchestration using the Phase 5A safe runtime ingress envelope.

**Architecture:** Phase 5B stays under `prototypes/` plus tests and dependency metadata. It proves a Temporal Workflow can own deterministic transaction state, expose query snapshots, and accept idempotent approval/cancellation/resume/delivery-ACK **Updates** from safe FlowWeaver envelopes. It does not use payload-carrying Signals. It does not wire Gateway to Temporal, does not start a service from production code, does not change visible IM behavior, and does not touch platform adapters.

**Tech Stack:** Python 3.11+, pytest, pytest-asyncio, Temporal Python SDK (`temporalio`), Temporal CLI for optional manual local smoke, existing FlowWeaver Phase 5A contract helper.

---

## Current Context / Evidence

Timestamp: 2026-05-05 13:49:11 CST +0800

Branch/worktree:

```text
repo: /home/ubuntu/workspace/hermes/repo/sachima
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5b-local-temporal-poc
branch: feat/flowweaver-phase5b-local-temporal-poc
base: origin/feature/sachima-channel @ f16391681c19f10c99bf5d8e1fd5dc3484fa1409
open PRs on base before branching: []
canonical ahead/behind before branching: 0 / 0
```

Gateway status observed during Phase 5B discovery:

```text
hermes-gateway.service: active/running
MainPID: 3480137
ExecMainStartTimestamp: Tue 2026-05-05 13:35:33 CST
WorkingDirectory: /home/ubuntu/workspace/hermes/repo/sachima
```

Temporal tooling observed:

```text
Temporal CLI: temporal version 1.7.0 (Server 1.31.0, UI 2.49.1)
Temporal Python SDK in current gateway venv: missing before Phase 5B
PyPI temporalio latest observed: 1.27.0
Context7 docs checked: /temporalio/sdk-python, /temporalio/cli
```

Baseline verification in the Phase 5B worktree:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_runtime_contract.py \
  tests/gateway/test_flowweaver_shadow_dry_run.py \
  tests/gateway/test_flowweaver_mock_durable_consumer.py \
  tests/gateway/test_flowweaver_shadow_tap.py \
  tests/gateway/test_flowweaver_contract_adapter.py \
  tests/gateway/test_delivery_state.py \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/test_rich_weather_delivery.py \
  -q
python -m py_compile \
  gateway/flowweaver_runtime_contract.py \
  gateway/flowweaver_shadow.py \
  gateway/flowweaver_mock_durable.py \
  gateway/flowweaver_shadow_dry_run.py
```

Observed:

```text
152 passed in 21.85s
py_compile: passed
```

Authoritative upstream gates:

```text
docs/plans/2026-05-05-flowweaver-phase5-architecture-gate.md
docs/plans/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md
docs/dev_log/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md
gateway/flowweaver_runtime_contract.py
tests/gateway/test_flowweaver_runtime_contract.py
```

Relevant Phase 5 architecture decision:

```text
Phase 5A: durable runtime ingress contract, pure helper, no Temporal import
Phase 5B: local Temporal POC under prototypes/, no Gateway wiring, no service auto-start
Phase 5C: narrow native tool or MCP-facing runtime client, still default-off
Phase 5D: Gateway shadow publisher / ACK bridge, default-off and no visible behavior change
```

---

## Scope

Phase 5B should prove these things only:

1. A safe Phase 5A runtime ingress envelope can be converted into a Temporal-safe start payload.
2. A local Temporal Workflow can own deterministic FlowWeaver transaction state.
3. Query snapshots can expose safe transaction/intent/artifact/delivery counts and statuses.
4. Validated **Updates only** can model payload-carrying external events:
   - `record_delivery_ack`
   - `approve_intent`
   - `reject_intent`
   - `cancel_transaction`
   - `resume_after_user_input`
5. Every external Update has a typed safe payload builder plus a Workflow Update validator.
6. ACK and human-in-the-loop events are idempotent and exact-targeted.
7. No raw prompt, raw command output, card JSON, platform payload, platform/chat/user/message identifier, delivery ACK payload, credential-shaped value, or raw Gateway object enters the Temporal boundary or Workflow history.

Phase 5B should not build a scheduler, DAG engine, MCP tool, Gateway publisher, dashboard, or production worker. That comes later.

---

## Non-Goals / Hard Boundaries

Forbidden in Phase 5B:

```text
no Gateway runtime wiring
no gateway/run.py changes
no gateway/platforms/* changes
no run_agent.py changes
no model_tools.py changes
no toolsets.py changes
no cli.py / hermes_cli changes
no production service or daemon auto-start
no Docker
no Gateway restart
no platform send/edit/render calls
no production persistence
no Workflow-side filesystem/network/subprocess/LLM/tool calls
no raw snapshot/capture/full agent_result in Temporal start/signal/update payloads
no raw command/stdout/stderr/card JSON/media bytes or paths/platform payloads/raw delivery ACK payloads
no platform/chat/user/message IDs or credential-shaped values in workflow history
no remote branch deletion
```

Allowed after explicit Phase 5B implementation approval:

```text
docs/plans/2026-05-05-flowweaver-phase5b-local-temporal-poc.md
docs/dev_log/2026-05-05-flowweaver-phase5b-local-temporal-poc.md
pyproject.toml
uv.lock
prototypes/flowweaver_phase5b_temporal_poc/pyproject.toml
prototypes/flowweaver_phase5b_temporal_poc/README.md
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/__init__.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/client.py  # only a narrow manual/local helper, no auto-start
tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py
tests/integration/test_flowweaver_phase5b_temporal_workflow.py
```

If implementation discovers a need to edit anything outside this list, stop and ask for approval before touching it.

---

## Design

### Dependency strategy

Add Temporal as an optional dependency, not a base dependency:

```toml
[project.optional-dependencies]
flowweaver-temporal = ["temporalio>=1.27.0,<2"]
all = [
  "hermes-agent[flowweaver-temporal]",
  # existing extras...
]
```

Rationale:

- Base Hermes install remains unchanged.
- CI currently installs `.[all,dev]`, so non-integration Phase 5B tests can import `temporalio` without skip churn.
- The prototype package can declare the same dependency for local-only POC usage.
- `uv.lock` must be updated with the exact resolver output.
- Because the repo pins `[tool.uv].exclude-newer = "7 days"`, `temporalio>=1.27.0` may need a package-specific `exclude-newer-package` override if the approved SDK release is newer than the global cutoff; keep that override scoped to `temporalio` only.

### Prototype package

Create:

```text
prototypes/flowweaver_phase5b_temporal_poc/
```

This is deliberately separate from `gateway/` so the prototype cannot become production Gateway behavior by accident.

### Payload boundary

Create `payloads.py` with plain dataclasses and dict projection helpers. The payload module is responsible for refusing unsafe input before anything reaches Workflow history.

Planned public surface:

```python
FLOWWEAVER_TEMPORAL_POC_VERSION = "flowweaver.temporal_poc.v0"
FLOWWEAVER_TEMPORAL_TASK_QUEUE = "flowweaver-phase5b-local-poc"

@dataclass(frozen=True)
class RuntimeStartPayload:
    transaction_id: str
    idempotency_key: str
    entry_count: int
    record_counts: dict[str, int]
    allowed_runtime_events: tuple[str, ...]
    claim_check_policy: dict[str, object]

@dataclass(frozen=True)
class DeliveryAckUpdate:
    delivery_key: str
    surface: str
    target_kind: str
    target_id: str
    status: str

@dataclass(frozen=True)
class HumanDecisionUpdate:
    event_id: str
    intent_id: str
    decision: str
    reason_ref: str | None = None

@dataclass(frozen=True)
class CancelTransactionUpdate:
    event_id: str
    reason_ref: str | None = None

@dataclass(frozen=True)
class ResumeUserInputUpdate:
    event_id: str
    input_ref: str

def build_start_payload_from_ingress_envelope(envelope: Mapping[str, object]) -> RuntimeStartPayload: ...
def delivery_ack_from_safe_update(update: Mapping[str, object]) -> DeliveryAckUpdate: ...
def human_decision_from_safe_update(update: Mapping[str, object]) -> HumanDecisionUpdate: ...
def cancel_transaction_from_safe_update(update: Mapping[str, object]) -> CancelTransactionUpdate: ...
def resume_user_input_from_safe_update(update: Mapping[str, object]) -> ResumeUserInputUpdate: ...
def snapshot_to_safe_dict(snapshot: Mapping[str, object]) -> dict[str, object]: ...
```

Input rules:

- Accept only exact plain `dict` / `list` / primitive values where exact shape matters.
- Start payload must come from an accepted `flowweaver.gateway.runtime_ingress_envelope.v0` envelope.
- Payload-carrying external events must be Updates, not Signals, so validators can reject unsafe payloads before they are accepted.
- Event IDs and target IDs must be synthetic FlowWeaver IDs, never platform IDs.
- Closed string rules are required:
  - synthetic IDs only: `runtime_tx_*`, `runtime_intent_*`, `runtime_artifact_*`, `runtime_delivery_*`, `runtime_event_*`
  - claim-check refs only for `reason_ref` and `input_ref`
  - closed enums for `status`, `decision`, `surface`, and `target_kind`
  - explicit rejection for platform-flavored prefixes such as Feishu/Lark message/chat/user IDs, generic chat/message/user IDs, delivery ACK payloads, and credential-shaped values
- Rejection errors must be safe constants, not echoes of attacker-controlled values.
- Tests must prove unsafe start/update payloads are rejected before Temporal client calls are made.

### Workflow boundary

Create `workflows.py` with one local POC Workflow:

```python
@workflow.defn
class FlowWeaverTransactionWorkflow:
    @workflow.run
    async def run(self, payload: RuntimeStartPayload) -> dict[str, object]: ...

    @workflow.query
    def query_snapshot(self) -> dict[str, object]: ...

    @workflow.update
    async def record_delivery_ack(self, update: DeliveryAckUpdate) -> dict[str, object]: ...

    @record_delivery_ack.validator
    def validate_record_delivery_ack(self, update: DeliveryAckUpdate) -> None: ...

    @workflow.update
    async def approve_intent(self, update: HumanDecisionUpdate) -> dict[str, object]: ...

    @approve_intent.validator
    def validate_approve_intent(self, update: HumanDecisionUpdate) -> None: ...

    @workflow.update
    async def reject_intent(self, update: HumanDecisionUpdate) -> dict[str, object]: ...

    @reject_intent.validator
    def validate_reject_intent(self, update: HumanDecisionUpdate) -> None: ...

    @workflow.update
    async def cancel_transaction(self, update: CancelTransactionUpdate) -> dict[str, object]: ...

    @cancel_transaction.validator
    def validate_cancel_transaction(self, update: CancelTransactionUpdate) -> None: ...

    @workflow.update
    async def resume_after_user_input(self, update: ResumeUserInputUpdate) -> dict[str, object]: ...

    @resume_after_user_input.validator
    def validate_resume_after_user_input(self, update: ResumeUserInputUpdate) -> None: ...
```

Workflow rules:

- Workflow owns deterministic state only.
- Workflow returns and queries safe snapshots only.
- Workflow does not import Gateway modules.
- Workflow does not call filesystem, network, subprocess, LLM, tools, or platform adapters.
- Workflow does not schedule Activities in Phase 5B. Activity boundaries are documented conceptually and deferred until a later phase.
- All payload-carrying external events are Updates with validators; Phase 5B has no payload-carrying Signals.
- Static/AST tests must fail on common nondeterminism sources: `open`, path modules, environment access, sockets, HTTP clients, subprocess, wall-clock time helpers, sleep helpers, randomness, UUID generation, Gateway/platform imports, and payload logging.

### Client helper boundary

`client.py` is optional and must remain manual/local:

```python
async def connect_local_temporal(address: str) -> Client: ...
async def start_local_poc_workflow(client: Client, payload: RuntimeStartPayload, workflow_id: str) -> str: ...
```

Rules:

- No service start.
- No subprocess.
- No Gateway import.
- No use from production code.
- If no local Temporal server exists, fail with a safe local-only error.

---

## TDD Task Plan

### Task 0: Persist plan and dev log

**Objective:** Record Phase 5B scope, evidence, allowed files, and verification plan.

**Files:**

- Create: `docs/plans/2026-05-05-flowweaver-phase5b-local-temporal-poc.md`
- Create: `docs/dev_log/2026-05-05-flowweaver-phase5b-local-temporal-poc.md`

**Verification:**

```bash
git check-ignore -v \
  docs/plans/2026-05-05-flowweaver-phase5b-local-temporal-poc.md \
  docs/dev_log/2026-05-05-flowweaver-phase5b-local-temporal-poc.md \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py || true
git add -N docs/plans/2026-05-05-flowweaver-phase5b-local-temporal-poc.md docs/dev_log/2026-05-05-flowweaver-phase5b-local-temporal-poc.md
git diff --check -- docs/plans/2026-05-05-flowweaver-phase5b-local-temporal-poc.md docs/dev_log/2026-05-05-flowweaver-phase5b-local-temporal-poc.md
```

### Task 1: RED — optional Temporal dependency and prototype package are absent

**Objective:** Define Phase 5B import/dependency expectations before implementation.

**Files:**

- Create: `tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py`

**Tests to add first:**

```text
test_temporal_poc_extra_is_declared_without_base_dependency
test_temporal_poc_package_imports_are_isolated_under_prototypes
```

**Expected RED:**

```text
AssertionError: flowweaver-temporal extra missing
ModuleNotFoundError: No module named 'flowweaver_temporal_poc'
```

**Command:**

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py -q
```

### Task 2: GREEN — add optional dependency metadata and empty prototype package

**Objective:** Make the RED dependency/package tests pass with minimal changes.

**Files:**

- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `prototypes/flowweaver_phase5b_temporal_poc/pyproject.toml`
- Create: `prototypes/flowweaver_phase5b_temporal_poc/README.md`
- Create: `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/__init__.py`

**Implementation notes:**

- Add `flowweaver-temporal = ["temporalio>=1.27.0,<2"]`.
- Include the extra in `all` so CI's existing `.[all,dev]` install has the SDK.
- Update lock with `/home/linuxbrew/.linuxbrew/bin/uv lock` or the repo-approved equivalent.

**Verification:**

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py -q
python -m py_compile prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/__init__.py
```

### Task 3: RED — safe start payload projection from Phase 5A envelope

**Objective:** Define exactly what crosses the Temporal start boundary.

**Files:**

- Modify: `tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py`

**Tests to add first:**

```text
test_start_payload_is_built_from_accepted_phase5a_envelope
test_start_payload_rejects_raw_snapshot_capture_agent_result_and_platform_ids
test_start_payload_rejection_never_echoes_attacker_values
test_start_payload_uses_synthetic_idempotency_key
test_delivery_ack_update_requires_closed_surface_target_status_and_synthetic_ids
test_human_cancel_resume_updates_require_claim_check_refs_and_safe_event_ids
test_unsafe_update_payloads_are_rejected_before_temporal_client_calls
```

**Expected RED:** missing `payloads.py` or missing functions.

### Task 4: GREEN — implement minimal safe payload projection

**Objective:** Add `payloads.py` with exact plain-data validation and safe rejection.

**Files:**

- Create: `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py`

**Implementation notes:**

- Reuse Phase 5A accepted envelope constants where safe.
- Do not pass raw envelope through; project into narrow dataclasses.
- Keep exceptions generic and safe, e.g. `ValueError("invalid_runtime_envelope")`.

**Verification:**

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py -q
python -m py_compile prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py
```

### Task 5: RED — Temporal workflow query/update behavior

**Objective:** Define local Temporal behavior before implementing Workflow code.

**Files:**

- Create: `tests/integration/test_flowweaver_phase5b_temporal_workflow.py`

**Tests to add first:**

```text
test_temporal_workflow_starts_from_safe_payload_and_queries_snapshot
test_temporal_workflow_records_delivery_ack_idempotently
test_temporal_workflow_handles_approval_rejection_resume_and_cancel_updates
test_temporal_workflow_rejects_payload_carrying_signals_in_phase5b
test_temporal_workflow_snapshot_omits_forbidden_material_and_platform_ids
test_temporal_workflow_history_omits_forbidden_sentinels_after_safe_updates
test_temporal_workflow_code_does_not_import_gateway_runtime_or_platform_adapters
test_temporal_workflow_code_has_no_activity_schedule_or_nondeterministic_calls
```

**Expected RED:** missing `workflows.py` or missing workflow class.

**Integration command:**

```bash
python -m pytest tests/integration/test_flowweaver_phase5b_temporal_workflow.py -q -m integration -o 'addopts='
```

### Task 6: GREEN — implement local Temporal Workflow

**Objective:** Add a deterministic Workflow with safe Query/Update/Signal handlers.

**Files:**

- Create: `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py`

**Implementation notes:**

- Use `@workflow.defn`, `@workflow.run`, `@workflow.query`, and `@workflow.update` according to current Temporal Python SDK docs.
- Every payload-carrying external event is an Update with a validator. No payload-carrying Signals in Phase 5B.
- Validators must reject unsafe payloads with safe constant errors before updates are accepted.
- Keep run open until transaction reaches terminal state or receives cancellation.
- Do not schedule Activities in Phase 5B.

**Verification:**

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py -q
python -m pytest tests/integration/test_flowweaver_phase5b_temporal_workflow.py -q -m integration -o 'addopts='
python -m py_compile \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py
```

### Task 7: RED/GREEN — manual local client helper remains narrow

**Objective:** Provide a local helper for later Phase 5C without making Gateway shell out to Temporal.

**Files:**

- Create: `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/client.py`
- Modify: `tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py`

**Tests:**

```text
test_client_helper_connects_only_when_called_and_never_starts_service
test_client_helper_requires_explicit_address_and_workflow_id
test_client_helper_module_has_no_gateway_or_platform_imports
```

**Verification:**

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py -q
python -m py_compile prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/client.py
```

### Task 8: Focused gate, scans, and independent reviews

**Objective:** Prove Phase 5B remains prototype-only and safe before PR.

**Focused tests:**

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  tests/gateway/test_flowweaver_runtime_contract.py \
  tests/gateway/test_flowweaver_shadow_dry_run.py \
  tests/gateway/test_flowweaver_mock_durable_consumer.py \
  tests/gateway/test_flowweaver_shadow_tap.py \
  tests/gateway/test_run_progress_topics.py \
  -q
python -m pytest tests/integration/test_flowweaver_phase5b_temporal_workflow.py -q -m integration -o 'addopts='
```

**Compile:**

```bash
python -m py_compile \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/__init__.py \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/client.py \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py
```

**Diff/scan gates:**

```bash
git diff --check
python - <<'PY'
from pathlib import Path
allowed = {
    'docs/plans/2026-05-05-flowweaver-phase5b-local-temporal-poc.md',
    'docs/dev_log/2026-05-05-flowweaver-phase5b-local-temporal-poc.md',
    'pyproject.toml',
    'uv.lock',
    'prototypes/flowweaver_phase5b_temporal_poc/pyproject.toml',
    'prototypes/flowweaver_phase5b_temporal_poc/README.md',
    'prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/__init__.py',
    'prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py',
    'prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py',
    'prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/client.py',
    'tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py',
    'tests/integration/test_flowweaver_phase5b_temporal_workflow.py',
}
changed = set(Path(p).as_posix() for p in __import__('subprocess').check_output(['git', 'diff', '--name-only']).decode().splitlines())
changed |= set(Path(p).as_posix() for p in __import__('subprocess').check_output(['git', 'ls-files', '--others', '--exclude-standard']).decode().splitlines())
unexpected = sorted(p for p in changed if p not in allowed)
if unexpected:
    raise SystemExit('unexpected changed files: ' + ', '.join(unexpected))
PY
```

Additional deterministic scans:

- Fail if `gateway/run.py`, `gateway/platforms/*`, `run_agent.py`, `model_tools.py`, `toolsets.py`, `cli.py`, or `hermes_cli/*` changes.
- Fail if `temporalio` is imported outside `prototypes/flowweaver_phase5b_temporal_poc/**` or `tests/integration/**`.
- Fail if prototype code contains callable send/edit/render/persist/log/service-start/subprocess patterns.
- Fail if workflow code imports `gateway.run` or `gateway.platforms`.
- Fail if workflow code schedules Activities in Phase 5B.
- Fail if workflow code contains nondeterministic calls/imports: `open`, path modules, environment access, sockets, HTTP clients, subprocess, wall-clock time helpers, sleep helpers, randomness, UUID generation, or payload logging.
- Fail if changed code contains secret-shaped literals or private platform ID fixture strings.
- Integration gate must assert safe workflow query/result/history representations do not contain forbidden sentinel material after start and safe Updates.

Independent reviews:

1. Spec / low-intrusion reviewer: verify Phase 5B stays under prototype boundary and does not wire Gateway.
2. Security / no-leak / Temporal-determinism reviewer: verify Workflow history payloads are safe, claim-check-only, deterministic, and side-effect-free.

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Temporal POC quietly becomes production wiring | Keep all code under `prototypes/`; scan forbidden Gateway/platform paths; no Gateway imports. |
| Workflow history receives raw material | Payload projector accepts only Phase 5A safe envelope fields; no raw object pass-through; no echo on rejection. |
| Temporal SDK test starts services unexpectedly | Production/prototype code never starts services; integration test uses Temporal SDK test environment only when explicitly run. |
| Dependency bloats base install | Put `temporalio` behind optional `flowweaver-temporal`; base dependencies unchanged. |
| Payload-carrying event enters history before validation | Use validated Updates only for external payloads; no payload-carrying Signals in Phase 5B. |
| Update/Signal semantics become fuzzy | Use exact synthetic IDs, closed enums, claim-check refs, and idempotency keys; validators reject ambiguous or platform-flavored IDs. |
| Workflow code performs side effects | Keep side effects out; static scan for filesystem/network/subprocess/Gateway/platform calls. |

---

## Approval Gate

After this plan passes document checks and independent plan review, ask the user before implementation.

Implementation approval should explicitly cover:

```text
Phase 5B implementation only:
- optional Temporal Python SDK dependency metadata
- local prototype package under prototypes/
- unit tests plus explicit local Temporal integration test
- validated Updates only for payload-carrying external events; no payload-carrying Signals
- no Gateway wiring
- no Gateway restart
- no Docker
- no production service auto-start
- no platform adapter changes
```

Do not start Phase 5C until Phase 5B PR is reviewed, merged, canonical is synced, and local worktree/branch cleanup is complete.
