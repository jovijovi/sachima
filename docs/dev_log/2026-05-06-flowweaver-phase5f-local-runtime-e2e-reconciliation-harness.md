# FlowWeaver Phase 5F — Local Runtime E2E Reconciliation Harness Dev Log

Timestamp: 2026-05-06 11:19:08 CST +0800

## User Ask

```text
执行 Phase 5F 实现。
```

## Process Decision

Phase 5F has no approved design/implementation plan yet. Per the established Sachima workflow, implementation code must not start until the design gate is written, reviewed, and explicitly approved.

This turn therefore starts Phase 5F by creating the worktree/branch and drafting the design gate only. No implementation code has been written in Phase 5F.

## Baseline Verification

- Canonical repo: `/home/ubuntu/workspace/hermes/repo/sachima`
- Canonical branch: `feature/sachima-channel`
- Canonical HEAD observed before Phase 5F worktree: `b3dd866363a4a2ecff3b6a72a575a18ffee611b1`
- PR #31 / Phase 5E: `MERGED`, merge commit `b3dd866363a4a2ecff3b6a72a575a18ffee611b1`
- New Phase 5F worktree: `/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5f-local-runtime-e2e-reconciliation-harness`
- New Phase 5F branch: `feat/flowweaver-phase5f-local-runtime-e2e-reconciliation-harness`
- Worktree HEAD: `b3dd866363a4a2ecff3b6a72a575a18ffee611b1`

Canonical untracked items observed before Phase 5F and not part of this phase:

```text
.hermes/
docs/plans/2026-04-24-sachima-channel.md
docs/superpowers/
```

Baseline focused tests in the Phase 5F worktree:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_shadow_publisher.py \
  tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  -q
```

Observed:

```text
28 passed in 0.57s
```

## Skills / Process Knowledge Loaded

- `software-development/superpowers/using-superpowers`
- `software-development/superpowers/brainstorming`
- `software-development/writing-plans`
- `software-development/test-driven-development`
- `software-development/hermes-workspace-worktrees`
- `devops/temporal-durable-orchestration`
- `software-development/subagent-driven-development`
- `software-development/requesting-code-review`

Use-driven validation applied: repo state, Phase 5E plan/dev log, current source files, and baseline tests were treated as higher-grade evidence than prior summaries.

## Context Inspected

- `AGENTS.md`
- `docs/plans/2026-05-06-flowweaver-phase5e-variable-runtime-ids-local-publish-adapter.md`
- `docs/dev_log/2026-05-06-flowweaver-phase5e-variable-runtime-ids-local-publish-adapter.md`
- `gateway/flowweaver_shadow_publisher.py`
- `gateway/flowweaver_runtime_identity.py`
- `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py`
- `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/publication_adapter.py`
- `tests/gateway/test_flowweaver_shadow_publisher.py`
- `tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py`
- `tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py`
- `tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py`

## Key Findings

1. Phase 5E is merged and current `feature/sachima-channel` includes variable synthetic runtime IDs plus the prototype-only local publication adapter.
2. Phase 5E proves safe publication into a caller-supplied fake runtime client, but does not query a resulting runtime snapshot or reconcile snapshot state back to the publication.
3. The Phase 5B workflow snapshot shape is sufficient for reconciliation: IDs, entry count, record counts, status maps, applied event count, and empty side effects.
4. Existing integration tests already cover a real Temporal test environment, but Phase 5F should not start one. This phase should stay fake-client/static/source-gate only.
5. The new harness should live under the existing prototype runtime-client package and must not be imported by production Gateway code.
6. No `AI_FLOW.md` exists in this repository worktree; `AGENTS.md` is the repo-local developer guide. The user’s established Sachima workflow still applies: design before code, TDD after approval, low-intrusion first.

## Planning Decision

Phase 5F should implement the recommended Option B from the plan:

```text
prototype-only fake runtime client + reconciliation harness
```

This stage should **not** add live Gateway → Temporal wiring. It should:

1. add a service-free in-memory runtime client matching the Phase 5C local runtime facade method shape;
2. add a safe reconciliation entrypoint that publishes a ready Phase 5D/5E summary, queries a runtime snapshot, and compares IDs/counts/ACK state;
3. drive realistic E2E tests from Gateway shadow helper output, but keep production/prototype source free of Gateway imports;
4. prove idempotent replay and mismatch detection;
5. keep all production Gateway/platform/tool/config surfaces unchanged.

## Draft Plan Saved

- `docs/plans/2026-05-06-flowweaver-phase5f-local-runtime-e2e-reconciliation-harness.md`

## Proposed Implementation Boundary

If approved, Phase 5F implementation covers only:

```text
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/__init__.py  # optional export only
tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py
docs/plans/2026-05-06-flowweaver-phase5f-local-runtime-e2e-reconciliation-harness.md
docs/dev_log/2026-05-06-flowweaver-phase5f-local-runtime-e2e-reconciliation-harness.md
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
~/.hermes/config.yaml
production Gateway service restart
Temporal service/test environment/Worker/Docker/CLI/daemon startup
live Gateway → Temporal wiring
MCP/global tool registry changes
platform adapter changes
base dependency changes
remote branch deletion
PR merge
```

## Planning Verification Log

Initial plan authored.

Initial doc gate:

- `git diff --check`: passed.
- planned file `git check-ignore`: passed.
- custom doc marker/scope/changed-file/sensitive/private-ID scan: passed.

Independent review pass 1:

- Plan/spec review: FAIL with two blockers.
  1. The planned happy-path test used final text plus a rich-card ACK, but the current Phase 5E start payload has one runtime delivery slot while the rich-card ACK targets `runtime_delivery_1`; that cannot reconcile while staying faithful to Phase 5B/5C semantics.
  2. The expected single-call reconciliation result mixed first-run and replay semantics by including `replay_idempotent` and duplicate ACK statuses even though the entrypoint was specified to publish only once.
- Security/low-intrusion review: FAIL with one blocker.
  1. The source-scan gate did not explicitly ban hidden runtime factories/construction, temporal addresses/task queues, generic connect helpers, `FlowWeaverRuntimeClient.connect`, `connect_local_temporal`, workflow imports, `start_workflow`, `get_workflow_handle`, and `execute_update`, including function-local imports/calls.

Plan/dev-log revisions made after review:

- Changed the happy-path reconciliation test to final-text-only so it matches the current one-entry runtime snapshot semantics.
- Added a separate negative reconciliation test for extra ACK surfaces without matching runtime delivery slots; this preserves evidence for a later delivery-cardinality phase without authorizing Gateway publisher changes in Phase 5F.
- Removed `replay_idempotent` from the single-call result shape and clarified that replay/idempotency is proven by calling the same entrypoint twice against the same in-memory runtime client.
- Strengthened source-scan gates to cover source text plus AST imports/calls/attributes and the hidden lifecycle terms named by the reviewer.

Blocker-only re-review results:

- Blocker-only plan/spec re-review: PASS, no new blockers.
- Blocker-only security/low-intrusion re-review: PASS, no new blockers.

Final doc gate after review evidence append: passed (`git diff --check` and custom doc marker/scope/changed-file/sensitive/private-ID scan).

## Implementation Log

Implementation approved by user at 2026-05-06 11:39 CST +0800 with:

```text
批准 Phase 5F 实现
```

TDD RED evidence:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py -q
```

Observed before implementation:

```text
6 failed
ModuleNotFoundError: No module named 'flowweaver_runtime_client.reconciliation_harness'
FileNotFoundError: .../reconciliation_harness.py
```

Implementation added:

- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py`
  - `InMemoryFlowWeaverRuntimeClient`
  - `reconcile_shadow_runtime_publication()`
- `tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py`
  - local E2E reconciliation
  - same-publication replay/idempotency
  - extra ACK surface mismatch detection
  - mismatched snapshot safe error
  - unsafe publication pre-query rejection
  - source AST/text lifecycle/wiring guard

No production Gateway entrypoint, platform adapter, runtime registry, dependency, config, service, Worker, Docker, or Temporal test-environment wiring was changed.

## Verification Log

Timestamp: 2026-05-06 11:48:33 CST +0800

Focused Phase 5F GREEN:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py -q
```

Observed:

```text
6 passed in 0.38s
```

Planned focused command before commit exposed one pre-existing local-diff guard interaction:

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py \
  tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py \
  tests/gateway/test_flowweaver_shadow_publisher.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  -q
```

Observed:

```text
33 passed, 1 failed
FAILED tests/gateway/test_flowweaver_shadow_publisher.py::test_shadow_runtime_publisher_changed_file_guard_allows_only_phase5e_files
```

Root cause: the Phase 5E local changed-file guard intentionally allows only Phase 5E uncommitted files. It fails in a Phase 5F worktree while Phase 5F files are uncommitted; this is not a runtime regression. A Phase 5F-specific changed-file allowlist custom gate was run instead, and the full planned focused command will be rerun after commit when the worktree diff is clean.

Focused regression command excluding only that Phase 5E local-diff guard:

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py \
  tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py \
  tests/gateway/test_flowweaver_shadow_publisher.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  -k 'not test_shadow_runtime_publisher_changed_file_guard_allows_only_phase5e_files' \
  -q
```

Observed:

```text
33 passed in 0.42s
```

Syntax/lint/diff gates:

```bash
python -m py_compile \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py

python -m ruff check \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py

git diff --check
```

Observed:

```text
py_compile: passed
ruff: All checks passed!
git diff --check: passed
```

Custom Phase 5F gates:

```text
changed-file allowlist: passed
source AST/text hidden lifecycle / Gateway wiring scan: passed
payload-carrying Signal scan: passed
sensitive/private-shaped literal scan: passed
no gateway/run.py or platform adapter diff: passed
no base dependency change: passed
```

Changed files observed by custom gate:

```text
docs/dev_log/2026-05-06-flowweaver-phase5f-local-runtime-e2e-reconciliation-harness.md
docs/plans/2026-05-06-flowweaver-phase5f-local-runtime-e2e-reconciliation-harness.md
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py
tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py
```

Independent reviews pass 1:

- Spec compliance review: FAIL with one blocker.
  1. Nested unsafe/mismatched publication material inside `runtime_identity` could pass through to runtime start/query because Phase 5F validated only top-level IDs before publish.
- Security/low-intrusion review: FAIL with one blocker.
  1. Sanitized query snapshots with extra status-map/count drift could still reconcile because Phase 5F compared `record_counts` but not `counts` and status-map key cardinality.

Blocker RED tests added and observed failing before fixes:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py -q
```

Observed:

```text
2 failed, 6 passed
FAILED test_phase5f_rejects_nested_unsafe_runtime_identity_before_starting_runtime
FAILED test_phase5f_reconciliation_detects_snapshot_record_count_status_map_drift
```

Blocker fixes:

- Validate the safe publication summary, runtime identity, top-level IDs, start payload transaction ID, and idempotency key before calling the publish adapter.
- Add snapshot parity checks for `counts` and exact intent/artifact/delivery status-map key cardinality.

Post-fix focused Phase 5F tests:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py -q
```

Observed:

```text
8 passed in 0.40s
```

Post-fix focused regression command excluding only the known Phase 5E local-diff guard:

```text
35 passed in 0.44s
```

Post-fix syntax/lint/diff/custom gates:

```text
py_compile: passed
ruff: All checks passed!
git diff --check: passed
custom Phase 5F gates: passed
```

Re-review pass 2:

- Snapshot count/status-map drift blocker-only re-review: PASS, no blockers.
- Nested unsafe runtime identity blocker-only re-review: FAIL with one remaining blocker.
  1. `runtime_identity.idempotency_key` and matching `start_payload.idempotency_key` containing generic `raw_` material could still reach the publish adapter and return `invalid_start_payload` instead of pre-publish `invalid_publication`.

Additional RED test added and observed failing before fix:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py::test_phase5f_rejects_raw_runtime_identity_event_id_before_publish -q
```

Observed:

```text
1 failed
expected error_code invalid_publication, got invalid_start_payload
```

Additional fix:

- Reject `raw_` markers in runtime event IDs during pre-publish publication identity validation.
- Convert forbidden-material validation failures in runtime identity checks into stable `invalid_publication` results.

Post-fix focused evidence:

```text
test_phase5f_rejects_raw_runtime_identity_event_id_before_publish: 1 passed in 0.38s
Phase 5F test file: 9 passed in 0.38s
Focused regression excluding known Phase 5E local-diff guard: 36 passed in 0.44s
py_compile: passed
ruff: All checks passed!
git diff --check: passed
custom Phase 5F gates: passed
```

Final re-review pass:

- Raw runtime identity event ID blocker-only spec re-review: PASS, no blockers.
- Final security/low-intrusion re-review after `raw_` validation fix: PASS, no blockers.

Reviewer evidence included:

```text
test_phase5f_rejects_raw_runtime_identity_event_id_before_publish: passed
Phase 5F reconciliation test file: passed
static lifecycle/security check: no hidden Docker/Temporal/Gateway/service lifecycle wiring
error outputs: stable/minimal
```

## Missed-Test Reflection

Missed tests caught by reviewers and added before finalizing:

1. I initially tested unsafe publication only at top-level IDs, missing nested `runtime_identity` drift/private marker material. Added `test_phase5f_rejects_nested_unsafe_runtime_identity_before_starting_runtime`.
2. I initially compared `record_counts` but missed `counts` and exact status-map key cardinality, which allowed sanitized snapshot drift to reconcile. Added `test_phase5f_reconciliation_detects_snapshot_record_count_status_map_drift`.
3. I initially rejected explicit private markers but missed generic `raw_` runtime event IDs when identity and start payload matched. Added `test_phase5f_rejects_raw_runtime_identity_event_id_before_publish`.

These were real gaps; the independent review loop paid for itself. Final implementation now rejects unsafe publication material before publish, detects sanitized runtime snapshot drift, and preserves stable minimal safe errors.
