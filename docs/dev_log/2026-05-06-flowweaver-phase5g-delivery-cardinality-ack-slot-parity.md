# FlowWeaver Phase 5G — Delivery Cardinality / ACK Slot Parity Dev Log

Timestamp: 2026-05-06 13:01:37 CST +0800

## User Ask

```text
执行 Phase 5 实现
```

## Interpretation

The previous phase completed through Phase 5F and PR #32 is merged. The immediately proposed next implementation stage was Phase 5G: Delivery Cardinality Hardening / ACK Slot Parity. I am treating “Phase 5 实现” as approval to start the next Phase 5-series workstream setup, but not as permission to skip the established Sachima design gate.

## Process Decision

Phase 5G has no approved detailed implementation plan yet. Per the established Sachima workflow, implementation code must not start until the design gate is written, reviewed, and explicitly approved.

This turn therefore starts Phase 5G by creating the worktree/branch and drafting the design gate only. No implementation code has been written in Phase 5G.

## Baseline Verification

- Canonical repo: `/home/ubuntu/workspace/hermes/repo/sachima`
- Canonical branch: `feature/sachima-channel`
- Canonical HEAD: `0e84502862158f61bc72c68636aff889128814de`
- `origin/feature/sachima-channel`: `0e84502862158f61bc72c68636aff889128814de`
- PR #32 / Phase 5F: merged at `0e84502862158f61bc72c68636aff889128814de`
- New Phase 5G worktree: `/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5g-delivery-cardinality-ack-slot-parity`
- New Phase 5G branch: `feat/flowweaver-phase5g-delivery-cardinality-ack-slot-parity`
- Worktree HEAD: `0e84502862158f61bc72c68636aff889128814de`

Canonical untracked items observed before Phase 5G and not part of this phase:

```text
.hermes/
docs/plans/2026-04-24-sachima-channel.md
docs/superpowers/
```

Baseline focused tests in the Phase 5G worktree:

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
37 passed in 0.49s
```

## Skills / Process Knowledge Loaded

- `software-development/superpowers/using-superpowers`
- `software-development/hermes-workspace-worktrees`
- `software-development/writing-plans`
- `software-development/test-driven-development`
- `software-development/subagent-driven-development`
- `software-development/requesting-code-review`
- `github/github-pr-workflow`
- `devops/temporal-durable-orchestration`

Use-driven validation applied: repo state, AGENTS.md, Phase 5F plan/dev log, current source files, and baseline tests were treated as higher-grade evidence than prior summaries.

## Context Inspected

- `AGENTS.md`
- `docs/plans/2026-05-06-flowweaver-phase5f-local-runtime-e2e-reconciliation-harness.md`
- `docs/dev_log/2026-05-06-flowweaver-phase5f-local-runtime-e2e-reconciliation-harness.md`
- `gateway/flowweaver_shadow_publisher.py`
- `gateway/flowweaver_runtime_contract.py`
- `gateway/flowweaver_mock_durable.py`
- `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py`
- `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/publication_adapter.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py`
- `tests/gateway/test_flowweaver_shadow_publisher.py`
- `tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py`
- `tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py`
- `tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py`
- `tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py`

## Key Findings

1. Phase 5F is merged and current `feature/sachima-channel` includes the local reconciliation harness.
2. Current local reconciliation succeeds for final-text-only publication.
3. Current local reconciliation intentionally mismatches when a publication emits an extra rich-card ACK surface but the start payload initializes only one delivery slot.
4. The publisher emits ACK targets in sequence (`runtime_delivery_0`, `runtime_delivery_1`, ...), but the start payload derives `record_counts.deliveries` from replay corpus entry count.
5. The Phase 5B payload validator currently requires `deliveries == entry_count`.
6. The Phase 5B workflow source and Phase 5F fake runtime initialize delivery statuses with `range(entry_count)` rather than `range(record_counts["deliveries"])`.
7. The ACK update builder can currently emit 21 total updates when final text plus 20 rich cards are present, but the local publication adapter bounds updates at 20.
8. Phase 5G should harden this contract before any real local Temporal Worker reconciliation phase.

## Planning Decision

Phase 5G should implement the recommended plan:

```text
delivery_slot_count = max(mock_durable_record_counts.deliveries, len(ack_bridge.updates))
```

This stage should **not** add live Gateway → Temporal wiring. It should:

1. keep production Gateway/platform behavior unchanged;
2. cap ACK updates at 20 total;
3. set start payload delivery count from actual ACK surface cardinality;
4. allow bounded extra delivery slots in the prototype runtime payload contract;
5. initialize fake runtime and POC workflow delivery status maps from delivery count;
6. preserve mismatch detection for tampered publications where ACK targets do not have matching runtime delivery slots.

## Draft Plan Saved

- `docs/plans/2026-05-06-flowweaver-phase5g-delivery-cardinality-ack-slot-parity.md`

## Proposed Implementation Boundary

If approved, Phase 5G implementation covers only:

```text
docs/plans/2026-05-06-flowweaver-phase5g-delivery-cardinality-ack-slot-parity.md
docs/dev_log/2026-05-06-flowweaver-phase5g-delivery-cardinality-ack-slot-parity.md
gateway/flowweaver_shadow_publisher.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py
tests/gateway/test_flowweaver_shadow_publisher.py
tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py
tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py
tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py
tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py
tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py
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
- custom doc marker/changed-file/sensitive/private-ID scan: passed.

Independent plan review pass 1:

- Plan/spec review: FAIL with two blockers.
  1. The cardinality rule wording said ACK target IDs must exactly cover all initialized delivery slots, which conflicts with cases where `deliveries > len(ack_updates)` and would imply invented ACKs.
  2. The plan required `workflows.py` to initialize delivery statuses from `record_counts["deliveries"]`, but did not require a test that would fail if the workflow source stayed on `range(payload.entry_count)`.
- Security/low-intrusion review: FAIL with four blockers.
  1. Changed-file allowlist gates did not explicitly include committed `merge-base..HEAD` changes before PR.
  2. Static/source scans were not concrete enough for dynamic hidden imports/factories, connect aliases, Temporal Worker/test-environment terms, Signals, listener startup, config writes, and registry/platform imports.
  3. Safe-output/log leakage gates did not explicitly cover new print/logging/raw exception interpolation or repr/serialization leaks in changed source.
  4. ACK target parity wording could authorize invented ACKs when initialized delivery slots exceed actual ACKs.

Plan/dev-log revisions after review:

- Clarified that initialized delivery slots are the closed set while emitted ACK targets are only a deterministic prefix/subset for actual ACK updates; no ACKs may be invented to fill unused slots.
- Added `test_phase5g_workflow_source_initializes_delivery_statuses_from_record_count` as an explicit RED test for the POC workflow source.
- Expanded changed-file allowlist gates to cover unstaged, staged, untracked, and committed `merge-base..HEAD` surfaces.
- Expanded source/static gates to name dynamic hidden imports/factories, connect aliases, Temporal Worker/test-environment imports/classes, Signals, subprocess/Docker/service/listener startup, config writes, platform imports, and registry/tool wiring.
- Added explicit safe-output/log leakage gates for new print/logging/raw exception interpolation and repr/serialization of agent results, delivery state, card/message payloads, platform IDs, or credential-shaped values.
- Added safe error-code and no-invented-ACK acceptance wording.

Blocker-only re-review results:

- Blocker-only plan/spec re-review: PASS, no blockers.
- Blocker-only security/low-intrusion re-review: PASS, no blockers.

Final doc gate after review evidence append: passed (`git diff --check` and custom doc marker/changed-file/sensitive/private-ID scan).

## Implementation Log

Implementation approved by user at 2026-05-06 13:18 CST +0800 with:

```text
批准 Phase 5G 阶段实现
```

Pre-implementation focused command after docs were added exposed the known Phase 5E local-diff guard interaction:

```text
36 passed, 1 failed
FAILED tests/gateway/test_flowweaver_shadow_publisher.py::test_shadow_runtime_publisher_changed_file_guard_allows_only_phase5e_files
```

Root cause: the Phase 5E changed-file guard intentionally allows only Phase 5E uncommitted files. It fails while Phase 5G files are uncommitted. The guard will be rerun after commit when the worktree diff is clean; Phase 5G focused checks exclude only this local-diff guard before commit.

TDD RED evidence:

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py::test_phase5f_detects_extra_ack_surface_without_matching_runtime_delivery_slot \
  tests/gateway/test_flowweaver_shadow_publisher.py::test_shadow_runtime_publication_ack_targets_remain_bounded_synthetic_delivery_ids \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py::test_shadow_publication_adapter_starts_runtime_once_then_applies_acks_in_order \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  -q
```

Observed before implementation:

```text
8 failed, 16 passed
```

Expected RED failures included:

- rich-card publication still had `record_counts.deliveries == 1` instead of `2`;
- rich-card reconciliation returned `ok=False`;
- `RuntimeStartPayload(entry_count=1, deliveries=2)` raised `invalid_start_payload`;
- final text plus 25 rich cards emitted 21 ACK updates instead of 20;
- workflow source still initialized delivery statuses from `payload.entry_count`.

Implementation added:

- `tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py`
  - rich-card publication delivery-count parity;
  - rich-card local reconciliation success;
  - rich-card replay/idempotency;
  - total ACK cap at 20;
  - bounded extra delivery slot payload validation;
  - workflow-source delivery-count guard;
  - source/lifecycle/wiring guard.
- `gateway/flowweaver_shadow_publisher.py`
  - ACK updates are derived before start payload finalization;
  - total ACK updates are capped at 20;
  - start payload `record_counts.deliveries` becomes `max(existing_deliveries, len(ack_updates))` within safe bounds.
- `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py`
  - payload validation now allows `entry_count <= deliveries <= 20` while preserving transaction/intent/artifact checks.
- `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py`
  - POC workflow delivery slots initialize from `payload.record_counts["deliveries"]`.
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py`
  - in-memory runtime delivery slots and snapshot counts initialize from delivery count;
  - reconciliation parity compares delivery status-map keys against `record_counts.deliveries`.
- Existing Phase 5F/5E/Gateway tests were updated to preserve tampered missing-slot negative coverage and assert normal multi-ACK publications start with matching delivery counts.

No production Gateway entrypoint, platform adapter, runtime registry, dependency, config, service, Worker, Docker, Temporal test environment, or Gateway restart was changed.

## Verification Log

Timestamp: 2026-05-06 13:32:40 CST +0800

Focused Phase 5G + Phase 5F reconciliation GREEN:

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  -q
```

Observed:

```text
16 passed in 0.40s
```

Publisher focused GREEN excluding only known Phase 5E local-diff guard:

```text
14 passed in 0.40s
```

Payload/contract focused GREEN:

```text
21 passed in 0.56s
```

Phase 5E local adapter focused GREEN:

```text
1 passed in 0.38s
```

Full focused pre-commit command excluding only known Phase 5E local-diff guard:

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py \
  tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py \
  tests/gateway/test_flowweaver_shadow_publisher.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  -k 'not test_shadow_runtime_publisher_changed_file_guard_allows_only_phase5e_files' \
  -q
```

Observed:

```text
57 passed in 0.60s
```

Post-commit full focused command with the Phase 5E local-diff guard included:

```text
58 passed in 0.60s
```

Syntax/lint/diff gates:

```text
py_compile: passed
ruff: All checks passed!
git diff --check: passed
```

Custom Phase 5G gates:

```text
changed-file allowlist including unstaged/staged/untracked/merge-base..HEAD: passed
forbidden production path/dependency/config diff: passed
source/diff hidden lifecycle and production wiring scan: passed
payload-carrying Signal scan: passed
print/logging/raw exception/repr leakage scan: passed
secret/private-shaped added-line scan: passed
ACK parity and total cap runtime probe: passed
```

Changed files observed by custom gate:

```text
docs/dev_log/2026-05-06-flowweaver-phase5g-delivery-cardinality-ack-slot-parity.md
docs/plans/2026-05-06-flowweaver-phase5g-delivery-cardinality-ack-slot-parity.md
gateway/flowweaver_shadow_publisher.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py
tests/gateway/test_flowweaver_shadow_publisher.py
tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py
tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py
tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py
```

Independent review results:

- Spec compliance review: PASS, no blockers.
- Security/low-intrusion review: PASS, no blockers.

Reviewer evidence included focused tests, diff inspection, changed-file allowlist checks, source/lifecycle scan, py_compile, ruff, and diff-check. No files were modified by reviewers.

## Missed-Test Reflection

Initial implementation followed the reviewed Phase 5G plan. One test-side correction was needed: the first safe-output helper treated `card_json` / `platform_payload` field names inside the existing claim-check forbidden-material policy as leaks. That was too broad; policy metadata may name forbidden fields. The helper now checks raw/private/source values and keeps the existing policy-metadata distinction intact.
