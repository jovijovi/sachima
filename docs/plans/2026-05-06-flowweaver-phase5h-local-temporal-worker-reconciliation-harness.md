# FlowWeaver Phase 5H Local Temporal Worker Reconciliation Harness Implementation Plan

> **For Hermes:** This document is the Phase 5H design gate. Do not write implementation code until the user explicitly approves this plan. After approval, implement with strict TDD, focused gates, and independent review.

**Goal:** Prove that the default-off FlowWeaver shadow publication + reconciliation path works against a real local Temporal test Worker, not only the Phase 5F in-memory fake runtime, while preserving safe output, replay/idempotency, and no production Gateway wiring.

**Architecture:** Keep production Gateway, platform adapters, tool registry, global config, and service lifecycle untouched. Add a Phase 5H integration test harness around `WorkflowEnvironment.start_time_skipping()` and `Worker` in tests only, using the existing caller-supplied `FlowWeaverRuntimeClient` facade and the Phase 5F/5G reconciliation entrypoint. Harden the runtime facade only where real Temporal behavior currently diverges from the fake contract: duplicate start/replay and validator-rejected delivery ACKs must return stable safe statuses instead of collapsing into opaque runtime errors.

**Tech Stack:** Python, pytest via `scripts/run_tests.sh`, Temporal Python SDK test environment, existing FlowWeaver Phase 5B workflow/payload contracts, Phase 5C runtime facade, Phase 5F reconciliation harness, Phase 5G delivery cardinality contract. Temporal remains an optional dependency via `flowweaver-temporal`; no base dependency, Docker, daemon, external Temporal service, Gateway restart, or production Gateway→Temporal wiring.

---

## Current Baseline

Timestamp: 2026-05-06 14:25:49 CST +0800

Repository / branch state observed before this Phase 5H design gate:

```text
canonical repo: /home/ubuntu/workspace/hermes/repo/sachima
canonical branch: feature/sachima-channel
canonical HEAD: a73446a9114a85d5b82b7e198f5ac15b2ae4ad32
origin/feature/sachima-channel: a73446a9114a85d5b82b7e198f5ac15b2ae4ad32
PR #33 / Phase 5G: MERGED, merge commit a73446a9114a85d5b82b7e198f5ac15b2ae4ad32
Phase 5H worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5h-local-temporal-worker-reconciliation-harness
Phase 5H branch: feat/flowweaver-phase5h-local-temporal-worker-reconciliation-harness
Phase 5H base: origin/feature/sachima-channel @ a73446a9114a85d5b82b7e198f5ac15b2ae4ad32
```

Canonical untracked items observed before Phase 5H and not part of this phase:

```text
.hermes/
docs/plans/2026-04-24-sachima-channel.md
docs/superpowers/
```

Baseline focused gate in the new Phase 5H worktree:

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py \
  -q
```

Observed:

```text
41 passed in 0.71s
```

Additional exploratory evidence before implementation:

```text
Duplicate real Temporal start through FlowWeaverRuntimeClient:
  first_start_ok=True first_status=started
  duplicate_start_exception=WorkflowAlreadyStartedError

Tampered final-text + rich-card publication with deliveries forced back to 1:
  fake runtime Phase 5F/5G expectation: reconciliation_mismatch
  current real Temporal worker result: {"ok": False, "operation": "reconcile_shadow_runtime_publication", "error_code": "runtime_error"}
```

These probes show Phase 5H has real contract work to do: the current fake runtime has the desired replay/mismatch behavior, but the real Temporal facade does not yet preserve that behavior when the Worker/Update validator is involved. Holy shit, this is exactly why Phase 5H exists.

## Context Inspected

```text
AGENTS.md
pyproject.toml
prototypes/flowweaver_phase5b_temporal_poc/pyproject.toml
prototypes/flowweaver_phase5c_runtime_client/pyproject.toml
docs/plans/2026-05-06-flowweaver-phase5f-local-runtime-e2e-reconciliation-harness.md
docs/dev_log/2026-05-06-flowweaver-phase5f-local-runtime-e2e-reconciliation-harness.md
docs/plans/2026-05-06-flowweaver-phase5g-delivery-cardinality-ack-slot-parity.md
docs/dev_log/2026-05-06-flowweaver-phase5g-delivery-cardinality-ack-slot-parity.md
gateway/flowweaver_shadow_publisher.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/publication_adapter.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py
tests/integration/test_flowweaver_phase5b_temporal_workflow.py
tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py
tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py
tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py
```

Current Temporal docs checked through Context7:

```text
ctx7 library temporalio "Python SDK testing WorkflowEnvironment Worker workflow update validator execute_update query start_workflow"
  selected: /temporalio/sdk-python

ctx7 docs /temporalio/sdk-python "Python SDK testing WorkflowEnvironment Worker start_time_skipping start_workflow execute_update query workflow history"
  evidence: tests use WorkflowEnvironment.start_time_skipping(), Worker(...), env.client.start_workflow(...), handle.query(...)

ctx7 docs /temporalio/sdk-python "Python SDK Workflow Update validator execute_update start_update update validator"
  evidence: @workflow.update supports validators; validators reject invalid input before update history is written; handle.execute_update(...) returns the update result

ctx7 docs /temporalio/sdk-python "WorkflowAlreadyStartedError start_workflow id reuse get_workflow_handle Python SDK"
  evidence: get_workflow_handle(...) is the supported path for interacting with an existing workflow handle
```

## Why Phase 5H

Phase 5F proved the local reconciliation contract with a fake in-memory runtime. Phase 5G fixed the delivery cardinality mismatch so final text + rich card can reconcile. The next useful proof is no longer another fake-client assertion; it is whether the same Gateway-generated safe publication behaves the same through a real local Temporal Worker.

The desired Phase 5H loop is:

```text
Gateway shadow final result
  -> safe FlowWeaver runtime publication
  -> FlowWeaverRuntimeClient backed by WorkflowEnvironment client
  -> real FlowWeaverTransactionWorkflow Worker
  -> validated Workflow Updates
  -> query_snapshot
  -> Phase 5F/5G reconciliation checks
  -> history no-leak scan
```

Phase 5H must not become live Gateway→Temporal. The Worker/test environment belongs in tests only. The runtime facade may be hardened because it is already the narrow prototype runtime boundary from Phase 5C.

## Approach Options

### Option A — Add only a one-shot integration test

Pros:
- Smallest diff.
- Likely proves the happy path for a single final-text + rich-card publication.

Cons:
- Does not address duplicate start/replay divergence: real Temporal raises `WorkflowAlreadyStartedError`, while fake runtime returns an idempotent start success.
- Does not address validator-rejected missing delivery slot divergence: real Temporal currently collapses into `runtime_error`, while fake runtime yields a stable reconciliation mismatch.
- Gives false confidence for exactly the replay/idempotency semantics durable runtimes are supposed to nail.

Verdict: **Reject.** A happy path only is a cute demo, not a durable-runtime proof.

### Option B — Connect Gateway shadow publisher directly to a local Temporal runtime

Pros:
- Closer to production integration.

Cons:
- Touches production-adjacent Gateway behavior too early.
- Risks service lifecycle/config side effects.
- Would make debugging harder before real-worker contract parity is proven.

Verdict: **Reject hard.** That shortcut is how you preserve bugs in amber.

### Option C — Add a real local Temporal Worker reconciliation test harness and minimally harden the runtime facade

Pros:
- Tests actual Temporal Worker/Update/Query behavior while keeping lifecycle in tests only.
- Reuses the existing safe publication adapter and reconciliation harness.
- Makes fake-client and real-worker semantics converge for replay and mismatch handling.
- Keeps Temporal optional and prototype-local.
- Leaves Gateway production wiring untouched.

Cons:
- Requires careful source gates so `Worker` / `WorkflowEnvironment` do not leak into runtime source or Gateway.
- Requires catching/mapping Temporal duplicate/rejected-update behavior without leaking raw exception strings.

Verdict: **Recommended.** This is the narrowest real-runtime proof worth landing.

## Recommended Design

### 1. Real local Temporal Worker reconciliation test harness

Create:

```text
tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
```

The test file may import and use:

```python
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
```

Rules:
- `WorkflowEnvironment.start_time_skipping()` and `Worker(...)` are used **only in this integration test file**.
- The Worker uses `FLOWWEAVER_TEMPORAL_TASK_QUEUE` and `FlowWeaverTransactionWorkflow`.
- Publications are built from existing Gateway shadow helper functions, not handwritten runtime payloads only.
- Every started workflow is canceled in `finally` with a safe `CancelTransactionUpdate`, then awaited via `handle.result()` when possible.
- History is fetched only from the test handle and scanned for forbidden sentinels in both rendered JSON/text and serialized protobuf bytes.
- No production service, Docker, Temporal CLI, external daemon, Gateway restart, config write, or platform adapter is touched.

Recommended helper functions inside the test file:

```python
def make_shadow_agent_result(*, index: int, rich_card_count: int = 1) -> dict[str, Any]: ...
def ready_publication(*, index: int, rich_card_count: int = 1) -> dict[str, object]: ...
async def query_until_running(facade: FlowWeaverRuntimeClient, workflow_id: str) -> dict[str, object]: ...
def history_text_and_bytes(history: Any) -> tuple[str, bytes]: ...
```

### 2. Harden real runtime duplicate-start idempotency

Modify:

```text
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py
```

Current problem:

```text
FlowWeaverRuntimeClient.start_transaction(payload, workflow_id=X)
  first call: ok/started
  replay call with the same workflow_id + same payload: raises WorkflowAlreadyStartedError
  publication adapter maps it to runtime_error
```

Target behavior:

```text
first call: {ok: True, operation: start_transaction, workflow_id: X, transaction_id: X, status: started}
replay with same workflow_id + same payload while workflow is running:
  {ok: True, operation: start_transaction, workflow_id: X, transaction_id: X, status: running}
replay with same workflow_id + mismatched workflow-observable payload fields:
  {ok: False, operation: start_transaction, error_code: invalid_start_payload}

Phase 5H deliberately limits duplicate-start mismatch detection to fields visible in the current safe workflow snapshot. The workflow does not currently persist `idempotency_key`, `allowed_runtime_events`, or `claim_check_policy`, while the Phase 5F fake runtime does keep a full payload signature. Persisting a full safe start signature in the workflow snapshot is a separate schema-expansion decision and is out of scope for this narrow real-worker reconciliation phase.
```

Implementation sketch:

```python
from temporalio.exceptions import WorkflowAlreadyStartedError

try:
    handle = await self._temporal_client.start_workflow(...)
except WorkflowAlreadyStartedError:
    handle = self._temporal_client.get_workflow_handle(safe_workflow_id)
    snapshot = await handle.query(FlowWeaverTransactionWorkflow.query_snapshot)
    safe_snapshot = sanitize_snapshot(snapshot_to_safe_dict(snapshot))
    if not _snapshot_matches_start_payload(safe_snapshot, payload):
        return make_error_result(operation="start_transaction", error_code="invalid_start_payload")
    return make_success_result(
        operation="start_transaction",
        workflow_id=safe_workflow_id,
        transaction_id=payload.transaction_id,
        status="running",  # Normalize any accepted active duplicate snapshot to an adapter-accepted start status.
    )
```

The helper `_snapshot_matches_start_payload(...)` must compare only safe workflow-observable deterministic fields:
- transaction ID
- entry count
- `record_counts`
- `counts`
- initialized intent/artifact/delivery key sets
- side effects absent
- acceptable non-terminal snapshot status (`running` or `waiting_for_user` for this phase), while duplicate-start success always returns adapter-accepted status `running`

Do not inspect, log, or return raw exception text.

### 3. Preserve missing-slot mismatch semantics through real Temporal validators

Current problem:

```text
Publication emits runtime_delivery_0 and runtime_delivery_1
Tampered start payload initializes only runtime_delivery_0
Fake runtime: ACK 1 rejected -> reconciliation_mismatch
Real Temporal Worker: workflow update validator rejects -> facade exception -> runtime_error
```

Target behavior for Phase 5H:

```text
Real Temporal Worker missing-slot ACK:
  record_delivery_ack returns safe status rejected with current sanitized snapshot
  reconciliation detects delivery_statuses_match=False
  final result: {ok: False, operation: reconcile_shadow_runtime_publication, error_code: reconciliation_mismatch}
```

Implementation sketch:

```python
async def record_delivery_ack(self, workflow_id: str, update: Any) -> dict[str, object]:
    validate_delivery_ack_update(update)
    safe_workflow_id = validate_workflow_id(workflow_id)
    rejected = await self._rejected_ack_result_if_target_missing(safe_workflow_id, update)
    if rejected is not None:
        return rejected
    return await self._execute_update(...)
```

The preflight should:
- query the current workflow snapshot with the existing handle;
- sanitize the snapshot through `snapshot_to_safe_dict(...)` + `sanitize_snapshot(...)`;
- if `update.target_id` is absent from `snapshot["delivery_statuses"]`, return a safe `make_update_success_result(...)` with `update_status="rejected"` and the sanitized snapshot;
- never call the Workflow Update for the missing-target case, so unsafe validator exception text cannot enter logs/results;
- return `runtime_error` only when the workflow cannot be queried or the snapshot is unsafe.

This is intentionally narrow to delivery ACK target parity. It does not generalize all Temporal validator failures yet.

### 4. TDD test plan

Create RED tests before modifying `runtime_client.py`.

#### Test 1 — real worker reconciles Gateway final text + rich card

```text
test_phase5h_reconciles_gateway_shadow_publication_through_real_temporal_worker
```

Arrange:
- Build a ready Gateway shadow runtime publication with final text + one rich card.
- Start `WorkflowEnvironment.start_time_skipping()` and `Worker(...)`.
- Use `FlowWeaverRuntimeClient(env.client, temporal_address="localhost:7233")`.
- Call `reconcile_shadow_runtime_publication(publication, runtime_client=facade)`.

Assert:
- result `ok is True`, status `reconciled`;
- `record_counts.deliveries == 2`;
- ACK statuses are `applied/applied`;
- real query snapshot has `runtime_delivery_0` and `runtime_delivery_1` set to `sent`;
- no private IDs / raw platform markers / credential-shaped strings appear in result or snapshot.

This may already pass; keep it as the happy-path real-worker proof.

#### Test 2 — replay is idempotent through real Temporal Worker

```text
test_phase5h_replay_against_real_temporal_worker_returns_duplicate_acks_without_extra_state
```

Arrange:
- Same publication and same real Worker/facade.
- Call `reconcile_shadow_runtime_publication(...)` twice against the same running workflow.

Expected RED before implementation:
- second call fails with `runtime_error` due `WorkflowAlreadyStartedError` from duplicate start.

Assert after implementation:
- first result `ack_statuses == ["applied", "applied"]`;
- second result `ack_statuses == ["duplicate", "duplicate"]`;
- `applied_event_count` remains `2`;
- snapshot delivery statuses remain exactly two delivery slots, both `sent`.

#### Test 3 — duplicate workflow ID with mismatched observable start fields is rejected safely

```text
test_phase5h_duplicate_start_with_mismatched_observable_payload_returns_invalid_start_payload
```

Arrange:
- Start a real workflow with a valid publication whose start payload has two delivery slots.
- Build a second start payload for the same workflow ID but change a workflow-observable safe field, for example `record_counts.deliveries` or `entry_count`.
- Call `FlowWeaverRuntimeClient.start_transaction(...)` directly with the mismatched payload.

Expected RED before implementation:
- duplicate start raises or maps to `runtime_error` instead of a stable safe start result.

Assert after implementation:
- result is `{"ok": False, "operation": "start_transaction", "error_code": "invalid_start_payload"}` or an equivalent safe error-result shape with no raw exception text;
- the mismatch test is explicitly limited to fields represented in the current safe workflow snapshot;
- no raw workflow ID/private fixture/credential-shaped material is echoed.

#### Test 4 — real Worker missing-slot negative maps to reconciliation mismatch

```text
test_phase5h_real_temporal_worker_preserves_missing_delivery_slot_mismatch_code
```

Arrange:
- Build final text + rich card publication.
- Tamper only `start_request.start_payload.record_counts.deliveries` back to `1`.
- Reconcile through real Worker/facade.

Expected RED before implementation:
- result is `runtime_error` due validator exception propagation.

Assert after implementation:
- result is exactly `{"ok": False, "operation": "reconcile_shadow_runtime_publication", "error_code": "reconciliation_mismatch"}`;
- result does not echo workflow ID, private fixture IDs, raw message IDs, raw exception text, or credential-shaped strings;
- real snapshot does not invent `runtime_delivery_1`.

#### Test 5 — Temporal history omits forbidden material after Gateway publication replay

```text
test_phase5h_real_temporal_history_omits_gateway_private_ids_and_credentials_after_replay
```

Arrange:
- Use a publication fixture containing raw-ish private message IDs only inside the original Gateway delivery state fixture.
- Reconcile twice to exercise duplicate/replay path.
- Cancel and await workflow result.
- Fetch history via `handle.fetch_history()`.

Assert:
- forbidden sentinels are absent from:
  - reconciliation results;
  - query snapshots;
  - rendered history (`history.to_json()` or fallback text);
  - serialized event bytes (`b"".join(event.SerializeToString() for event in history.events)`).

#### Test 6 — Phase 5H source boundary gate

```text
test_phase5h_diff_does_not_add_gateway_wiring_or_runtime_lifecycle_outside_integration_tests
```

Gate all changed files from unstaged, staged, untracked, and committed `merge-base..HEAD` surfaces.

Allowed changed files:

```text
docs/plans/2026-05-06-flowweaver-phase5h-local-temporal-worker-reconciliation-harness.md
docs/dev_log/2026-05-06-flowweaver-phase5h-local-temporal-worker-reconciliation-harness.md
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py
tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
```

Rules:
- `WorkflowEnvironment` and `Worker` may appear only in the new integration test.
- Added runtime source may import `WorkflowAlreadyStartedError`, but must not import or construct `Worker`, `WorkflowEnvironment`, Docker, system service controls, Gateway adapters, tool registry, or config writers.
- No added file may touch `gateway/run.py`, `gateway/platforms/**`, `run_agent.py`, `model_tools.py`, `toolsets.py`, `tools/**`, `hermes_cli/**`, `~/.hermes/config.yaml`, or production service files.
- No added runtime source may call `Client.connect`, `connect_local_temporal`, subprocess, Docker, systemctl, daemon management, socket/listener startup, `open`, `Path.write_*`, `eval`, `exec`, dynamic `importlib`, or `__import__`.
- No added runtime source may introduce `print`, `logger.*`, `logging.*`, `str(exc)`, `repr(exc)`, or raw exception interpolation; the Phase 5H integration tests should use `caplog` or source scanning if any logging path is added.
- No payload-carrying Signals: `@workflow.signal`, `.signal(`, and `signal_with_start` remain absent in changed FlowWeaver runtime/workflow source.
- No base dependency change: `temporalio` remains only under `flowweaver-temporal` optional dependency and prototype `temporal` extra.

### 5. Implementation tasks after approval

#### Task 1 — Add Phase 5H integration RED tests

Files:

```text
Create: tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
```

Steps:
1. Add test helpers and Tests 1–5 above.
2. Run only the new Phase 5H integration test file.
3. Expected RED: at least replay idempotency and missing-slot mismatch tests fail for the observed reasons (`WorkflowAlreadyStartedError`/`runtime_error`), not harness setup errors.
4. If a test errors due selector/import/setup rather than the intended behavior, fix the test harness and rerun RED until the failure proves the intended missing behavior.

#### Task 2 — Harden duplicate start replay in `FlowWeaverRuntimeClient`

Files:

```text
Modify: prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py
```

Steps:
1. Add a local import of `WorkflowAlreadyStartedError` inside `start_transaction()`.
2. Catch duplicate-start, get existing handle, query snapshot, sanitize it, compare safe fields to the incoming start payload.
3. Return `started` for first call and adapter-accepted `running` for any matching active duplicate (`running` or `waiting_for_user` snapshot).
4. Return safe `invalid_start_payload` for duplicate workflow ID with mismatched workflow-observable payload fields; full idempotency-key/claim-policy signature persistence is deferred.
5. Run the replay, mismatched-observable duplicate-start, and Phase 5C integration facade tests.

#### Task 3 — Map missing delivery ACK target to safe rejected status before Update history

Files:

```text
Modify: prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py
```

Steps:
1. Add a narrow delivery ACK target preflight before `execute_update`.
2. Query and sanitize current snapshot.
3. If target delivery slot is absent, return a safe update result with `update_status="rejected"` and the current snapshot.
4. Do not call the Workflow Update in this missing-target case.
5. Run the missing-slot mismatch test and the existing Phase 5F/5G mismatch tests.

#### Task 4 — Run focused and integration gates

Implementation note: the current `scripts/run_tests.sh` in this checkout hard-codes `--ignore=tests/integration` and `-m "not integration"`. For Phase 5H execution, run real Temporal integration selectors with the same shared venv and deterministic env flags, then use the project script for prototype regressions.

Run integration selectors:

```bash
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py \
  -q
```

Run prototype selectors:

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  -q
```

Expected final result: all pass.

#### Task 5 — Syntax/lint/static/security gates

Run:

```bash
python -m py_compile \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
python -m ruff check \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
git diff --check
```

Custom gates:
- changed-file allowlist across unstaged, staged, untracked, and committed `merge-base..HEAD` changes;
- added-line forbidden lifecycle scan with test-file exception for `WorkflowEnvironment`/`Worker`;
- no production Gateway/platform/tool/global registry/config writes;
- no base dependency change for `temporalio`;
- no raw private/platform IDs or credential-shaped values in returned results, snapshots, logs, or history fixtures;
- no raw exception text interpolation in new/changed runtime source (`print`, `logger.*`, `logging.*`, `str(exc)`, `repr(exc)`, and raw exception formatting are forbidden unless a test proves sanitized output).

#### Task 6 — Independent implementation review and PR

After green gates:
1. Run independent spec compliance review.
2. Run independent security/low-intrusion review.
3. Fix blockers with RED tests first.
4. Rerun focused gates after any fix.
5. Commit, push branch, and open PR against `feature/sachima-channel` only after verification passes.

## Out of Scope

Phase 5H does **not** approve:

```text
gateway/run.py changes
gateway/platforms/** changes
run_agent.py changes
model_tools.py changes
toolsets.py changes
tools/** changes
hermes_cli/** changes
MCP/global tool registry changes
production Gateway service restart
production Gateway → Temporal wiring
Docker / temporal server daemon / Temporal CLI startup
external Temporal service dependency
~/.hermes/config.yaml writes
base dependency changes that install temporalio outside optional extras
payload-carrying Signals
Activities / LLM calls / shell commands inside Workflow code
remote branch deletion
PR merge
```

## Acceptance Criteria

Phase 5H is complete only if:

1. A real local Temporal test Worker reconciles a Gateway-built final-text + rich-card shadow publication successfully.
2. The same publication replayed against the same real Worker returns duplicate ACK statuses and does not mutate applied event count.
3. A tampered missing delivery slot publication produces stable `reconciliation_mismatch`, not raw `runtime_error`, and does not leak IDs or exception text.
4. Temporal history after safe Gateway publication replay omits forbidden private/platform/credential sentinels in both rendered history and serialized event bytes.
5. Runtime facade duplicate-start behavior is safe and idempotent for matching active snapshots, normalizes duplicate success to adapter-accepted status `running`, and rejects mismatched workflow-observable start fields with a stable safe error. Full hidden start-signature persistence is explicitly deferred.
6. No production Gateway, platform adapter, tool registry, global config, base dependency, Docker, daemon, or service lifecycle code is touched.
7. `temporalio` remains optional under `flowweaver-temporal` / prototype temporal extras only.
8. All focused tests, syntax/lint gates, diff checks, custom safety gates, and independent reviews pass.

## Handoff

This plan is the design gate, not implementation permission. The user message said “批准 Phase 5H 阶段实现”, but there was no Phase 5H plan yet, so this turn deliberately creates and reviews the plan first. After this plan passes doc gates and independent review, implementation still needs explicit approval of this concrete Phase 5H plan.
