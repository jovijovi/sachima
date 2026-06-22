# FlowWeaver Phase 5H — Local Temporal Worker Reconciliation Harness Dev Log

Timestamp: 2026-05-06 14:25:49 CST +0800

## User Ask

```text
批准 Phase 5H 阶段实现
```

## Interpretation

Phase 5G / PR #33 is merged and the next natural stage is Phase 5H: real Local Temporal Worker Reconciliation Harness.

There is no approved detailed Phase 5H plan yet. Per the established Sachima workflow, design approval comes before code. I am treating the user message as authorization to start the Phase 5H workstream setup and design gate, **not** as permission to skip plan/review and immediately edit runtime code.

## Process Decision

This turn creates the Phase 5H branch/worktree, verifies current state, inspects Phase 5B/5C/5F/5G contracts plus current Temporal docs, runs baseline tests, and drafts the Phase 5H design gate. No Phase 5H implementation code has been written yet.

## Baseline Verification

Canonical repo:

```text
repo: /home/ubuntu/workspace/hermes/repo/sachima
branch: feature/sachima-channel
canonical HEAD: a73446a9114a85d5b82b7e198f5ac15b2ae4ad32
origin/feature/sachima-channel: a73446a9114a85d5b82b7e198f5ac15b2ae4ad32
merge-base: a73446a9114a85d5b82b7e198f5ac15b2ae4ad32
```

Current latest commits:

```text
a73446a91 Merge pull request #33 from jovijovi/feat/flowweaver-phase5g-delivery-cardinality-ack-slot-parity
efb78b089 feat(flowweaver): harden delivery cardinality parity
0e8450286 Merge pull request #32 from jovijovi/feat/flowweaver-phase5f-local-runtime-e2e-reconciliation-harness
fdea54e64 feat(flowweaver): add phase 5f local reconciliation harness
b3dd86636 Merge pull request #31 from jovijovi/feat/flowweaver-phase5e-variable-runtime-ids-local-publish-adapter
f0118ed33 feat(flowweaver): add variable runtime ids and local publish adapter
604995ce4 Merge pull request #30 from jovijovi/feat/flowweaver-phase5d-gateway-shadow-publisher-ack-bridge
c7f9d49da feat(flowweaver): add phase 5d shadow publisher ack bridge
```

Canonical untracked items observed before Phase 5H and not part of this phase:

```text
.hermes/
docs/plans/2026-04-24-sachima-channel.md
docs/superpowers/
```

New Phase 5H worktree / branch:

```text
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5h-local-temporal-worker-reconciliation-harness
branch: feat/flowweaver-phase5h-local-temporal-worker-reconciliation-harness
head: a73446a9114a85d5b82b7e198f5ac15b2ae4ad32
tracking: origin/feature/sachima-channel
```

Baseline focused tests in Phase 5H worktree:

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

## Skills / Process Knowledge Loaded

- `software-development/superpowers/using-superpowers`
- `software-development/plan`
- `software-development/writing-plans`
- `software-development/test-driven-development`
- `software-development/hermes-workspace-worktrees`
- `software-development/subagent-driven-development`
- `software-development/requesting-code-review`
- `github/github-pr-workflow`
- `devops/temporal-durable-orchestration`
- `software-development/context7-cli`
- `software-development/find-docs`
- `software-development/handling-failed-verification-chains`

Use-driven validation applied: repo state, AGENTS.md, merged Phase 5F/5G plans/dev logs, source files, existing integration tests, baseline tests, Context7 docs, and live probes were treated as higher-grade evidence than summaries.

## Context Inspected

- `AGENTS.md`
- `pyproject.toml`
- `prototypes/flowweaver_phase5b_temporal_poc/pyproject.toml`
- `prototypes/flowweaver_phase5c_runtime_client/pyproject.toml`
- `docs/plans/2026-05-06-flowweaver-phase5f-local-runtime-e2e-reconciliation-harness.md`
- `docs/dev_log/2026-05-06-flowweaver-phase5f-local-runtime-e2e-reconciliation-harness.md`
- `docs/plans/2026-05-06-flowweaver-phase5g-delivery-cardinality-ack-slot-parity.md`
- `docs/dev_log/2026-05-06-flowweaver-phase5g-delivery-cardinality-ack-slot-parity.md`
- `gateway/flowweaver_shadow_publisher.py`
- `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py`
- `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/publication_adapter.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py`
- `tests/integration/test_flowweaver_phase5b_temporal_workflow.py`
- `tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py`
- `tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py`
- `tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py`

## Current Temporal Docs Checked

Context7 lookup:

```text
ctx7 library temporalio "Python SDK testing WorkflowEnvironment Worker workflow update validator execute_update query start_workflow"
```

Selected library:

```text
/temporalio/sdk-python
```

Docs queries:

```text
ctx7 docs /temporalio/sdk-python "Python SDK testing WorkflowEnvironment Worker start_time_skipping start_workflow execute_update query workflow history"
ctx7 docs /temporalio/sdk-python "Python SDK Workflow Update validator execute_update start_update update validator"
ctx7 docs /temporalio/sdk-python "WorkflowAlreadyStartedError start_workflow id reuse get_workflow_handle Python SDK"
```

Relevant current-doc findings:

1. Python SDK tests use `WorkflowEnvironment.start_time_skipping()` and `Worker(env.client, task_queue=..., workflows=[...])`.
2. Clients start workflows with `client.start_workflow(..., id=..., task_queue=...)` and query existing workflows via `handle.query(...)`.
3. Workflow Updates support validators; validators can reject before accepted Update history is written.
4. `get_workflow_handle(...)` is the supported way to interact with an existing workflow.

## Key Findings

1. Phase 5F fake runtime reconciliation now supports final-text-only, replay idempotency, safe mismatch, and safe output.
2. Phase 5G fixed delivery cardinality so final text + rich card initializes `runtime_delivery_0` and `runtime_delivery_1` and reconciles against the fake runtime.
3. Existing integration tests cover direct Phase 5B workflow and Phase 5C facade behavior, but they do not yet reconcile a Gateway-built shadow publication through a real local Temporal Worker.
4. Existing real Temporal facade duplicate start diverges from fake-runtime replay semantics:

   ```text
   duplicate_start_exception=WorkflowAlreadyStartedError
   first_start_ok=True first_status=started
   ```

5. Existing real Temporal facade missing delivery slot mismatch diverges from fake-runtime mismatch semantics:

   ```text
   tampered_real_result={'ok': False, 'operation': 'reconcile_shadow_runtime_publication', 'error_code': 'runtime_error'}
   ```

6. These divergences should be fixed before any Gateway shadow-to-real-runtime bridge phase.

## Planning Decision

Phase 5H should implement Option C from the plan:

```text
real local Temporal Worker reconciliation test harness
+ minimal FlowWeaverRuntimeClient hardening for duplicate start replay
+ safe rejected delivery ACK mapping for missing delivery slots
```

It should **not** connect production Gateway to Temporal. It should:

1. use `WorkflowEnvironment` and `Worker` only in `tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py`;
2. keep Temporal optional (`flowweaver-temporal` / prototype temporal extra only);
3. preserve fake-runtime and real-worker parity for replay and mismatch cases;
4. keep safe history checks for rendered JSON/text and serialized event bytes;
5. keep all raw/private/platform/credential material out of returned results, snapshots, logs, and Temporal history.

## Draft Plan Saved

- `docs/plans/2026-05-06-flowweaver-phase5h-local-temporal-worker-reconciliation-harness.md`

## Proposed Implementation Boundary

If approved, Phase 5H implementation covers only:

```text
docs/plans/2026-05-06-flowweaver-phase5h-local-temporal-worker-reconciliation-harness.md
docs/dev_log/2026-05-06-flowweaver-phase5h-local-temporal-worker-reconciliation-harness.md
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py
tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
```

Still not approved without separate explicit user instruction:

```text
gateway/run.py
gateway/platforms/**
run_agent.py
model_tools.py
toolsets.py
tools/**
hermes_cli/**
~/.hermes/config.yaml writes
production Gateway service restart
production Gateway → Temporal wiring
MCP/global tool registry changes
platform adapter changes
base dependency changes
Docker / temporal server daemon / Temporal CLI startup
external Temporal service dependency
payload-carrying Signals
remote branch deletion
PR merge
```

## Planning Verification Log

Draft plan authored.

Initial doc gate:

- `git diff --check`: passed.
- planned file `git check-ignore`: passed.
- custom doc marker/changed-file/sensitive/private-ID/config-write boundary scan: passed after one dev-log boundary wording fix (`~/.hermes/config.yaml writes`).

Independent plan review pass 1:

- Plan/spec review: FAIL with two blockers.
  1. Replay/idempotency parity was under-specified for duplicate `workflow_id` with mismatched start fields. The plan said mismatched payload returns `invalid_start_payload`, but the workflow snapshot does not currently expose `idempotency_key`, `allowed_runtime_events`, or `claim_check_policy`, while the fake runtime stores the full payload signature.
  2. Duplicate active-status handling could return `waiting_for_user` from the snapshot, but `publish_shadow_runtime_publication()` only accepts start statuses `started`, `running`, or `published`, and `publication_adapter.py` is not in Phase 5H scope.
- Security/low-intrusion review: PASS, no blockers.
  - Non-blocking suggestions: make async-context cleanup explicit, tighten no-log/no-exception-leak gates, and ensure credential-shaped sentinels are in history no-leak fixtures.

Plan revisions after review:

- Narrowed duplicate-start mismatch target to workflow-observable safe fields represented in the current snapshot; full hidden start-signature persistence is explicitly deferred.
- Added a RED test for duplicate `workflow_id` with mismatched workflow-observable start fields.
- Changed duplicate-start success sketch to normalize any accepted active duplicate snapshot to adapter-accepted status `running`.
- Expanded source gates to forbid new `print`, `logger.*`, `logging.*`, `str(exc)`, `repr(exc)`, and raw exception interpolation unless sanitized by tests.

Blocker-only re-review results:

- Blocker-only plan/spec re-review: PASS, no blockers.
- Blocker-only security sanity re-review: PASS, no blockers.

Final doc gate after re-review evidence append: passed (`git diff --check` and custom doc marker/sensitive/private-ID scan).

## Implementation Verification Log

Timestamp: 2026-05-06 15:24:15 CST +0800

User approved the concrete Phase 5H plan with:

```text
OK，批准执行 Phase 5H
```

Execution notes:

1. Loaded and applied Phase 5H execution skills: TDD, executing plans, Temporal durable orchestration, local runtime reconciliation validation, code review, GitHub PR workflow, and verification-before-completion.
2. Re-verified live worktree state before implementation:
   - branch: `feat/flowweaver-phase5h-local-temporal-worker-reconciliation-harness`
   - base: `origin/feature/sachima-channel @ a73446a9114a85d5b82b7e198f5ac15b2ae4ad32`
   - pre-existing Phase 5H changes: this plan + this dev log only.
3. Current `scripts/run_tests.sh` hard-codes `--ignore=tests/integration` and `-m "not integration"`; running it against the new integration file produced `no tests ran` / exit 5. Per failed-verification-chain discipline, that was treated as verifier failure, not RED evidence. Integration selectors were rerun with the same venv and deterministic env flags via `python -m pytest -o addopts= -n 4 ...`.

RED evidence after fixing one test-harness sentinel assertion:

```text
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py -q

Result: 4 failed, 2 passed in 0.99s
Expected target failures:
- replay against real Worker returned non-ok because duplicate start still collapsed through runtime_error;
- duplicate direct start raised WorkflowAlreadyStartedError instead of returning invalid_start_payload for observable mismatch;
- missing delivery slot through real Worker returned runtime_error instead of reconciliation_mismatch;
- history replay case failed on the same duplicate-start divergence.
```

Implementation landed:

1. Added `tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py` with:
   - real `WorkflowEnvironment.start_time_skipping()` + `Worker` harness;
   - Gateway-built final-text + rich-card publication reconciliation proof;
   - replay idempotency proof against the same real Worker;
   - duplicate workflow ID + mismatched observable start fields negative proof;
   - missing delivery slot negative proof preserving `reconciliation_mismatch`;
   - rendered history + serialized event bytes no-leak proof;
   - changed-file/source-boundary gate.
2. Hardened `FlowWeaverRuntimeClient.start_transaction()`:
   - catches `WorkflowAlreadyStartedError`;
   - queries/sanitizes existing workflow snapshot;
   - compares only workflow-observable safe fields;
   - returns safe `running` for matching active duplicate starts;
   - returns safe `invalid_start_payload` for mismatched observable fields.
3. Hardened `FlowWeaverRuntimeClient.record_delivery_ack()`:
   - preflights current sanitized snapshot before executing the Update;
   - returns safe `rejected` update result when the delivery target slot is missing;
   - avoids sending the missing-target case into the Workflow Update validator/history.

GREEN / focused verification:

```text
# Phase 5H file after implementation
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py -q

6 passed in 0.96s
```

```text
# Temporal integration regression
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py \
  -q

18 passed in 1.23s
```

```text
# Prototype regression via project script
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  -q

41 passed in 0.59s
```

Gate results before independent review:

```text
python -m py_compile \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
# exit 0

python -m ruff check \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
# All checks passed!

git diff --check
# exit 0

custom allowlist / secret-shaped added-line / forbidden runtime lifecycle / signal / optional-dependency gates
# custom gates passed
```

Independent implementation review:

Timestamp: 2026-05-06 15:30:12 CST +0800

1. Spec compliance reviewer: PASS.
   - Re-ran focused Phase 5H integration, Phase 5B/5C/5H integration regression, prototype regression, ruff, in-memory compile, `git diff --check`, and custom allowlist/forbidden-runtime-source scan.
   - Verified the real local Worker harness, replay duplicate ACKs, mismatched duplicate-start safe error, missing-slot mismatch mapping, history no-leak, and changed-file allowlist.
   - No files modified by reviewer.
2. Security / low-intrusion reviewer: PASS.
   - Re-ran `git diff --check`, Phase 5H integration, custom allowlist/security/lifecycle/signal/history scan, and `ruff check --no-cache`.
   - Verified no Gateway/platform adapter/tool registry/config/base dependency changes, no runtime Worker/WorkflowEnvironment lifecycle construction, no raw exception interpolation/logging, no payload-carrying Signals, and no leak in rendered/serialized history checks.
   - No files modified by reviewer.

No reviewer blockers found.
