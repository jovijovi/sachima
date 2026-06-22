# FlowWeaver Phase 5G Delivery Cardinality / ACK Slot Parity Implementation Plan

> **For Hermes:** This document is the Phase 5G design gate. Do not write implementation code until the user explicitly approves this plan. After approval, implement with strict TDD, focused gates, and independent review.

**Goal:** Make FlowWeaver shadow runtime publications initialize one safe runtime delivery slot for every emitted ACK surface, so final-text-only and final-text-plus-rich-card publications reconcile locally without silently dropping or inventing delivery state.

**Architecture:** Keep production Gateway, platform adapters, and real Temporal lifecycle untouched. Harden the existing default-off shadow publisher and prototype runtime contracts so `record_counts.deliveries`, runtime snapshot delivery slots, ACK bridge targets, and reconciliation checks share the same bounded cardinality model. The model is: durable corpus entries still define transaction/intent/artifact counts, while delivery slots are `max(mock_durable_delivery_records, emitted_ack_surface_count)` capped by the existing ACK bridge bound.

**Tech Stack:** Python, pytest via `scripts/run_tests.sh`, existing Gateway FlowWeaver shadow helpers, Phase 5B payload/workflow contract source, Phase 5C publication adapter, and Phase 5F local reconciliation harness. Phase 5G verification remains fake-client/static/source-gate only; no Temporal test environment, Worker, Docker, CLI, daemon, Gateway restart, or production Gateway→runtime wiring.

---

## Current Baseline

Timestamp: 2026-05-06 13:01:37 CST +0800

Repository / branch state observed before this Phase 5G design gate:

```text
canonical repo: /home/ubuntu/workspace/hermes/repo/sachima
canonical branch: feature/sachima-channel
canonical HEAD: 0e84502862158f61bc72c68636aff889128814de
origin/feature/sachima-channel: 0e84502862158f61bc72c68636aff889128814de
PR #32 / Phase 5F: MERGED, merge commit 0e84502862158f61bc72c68636aff889128814de
Phase 5G worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5g-delivery-cardinality-ack-slot-parity
Phase 5G branch: feat/flowweaver-phase5g-delivery-cardinality-ack-slot-parity
Phase 5G base: origin/feature/sachima-channel @ 0e84502862158f61bc72c68636aff889128814de
```

Canonical untracked items observed before Phase 5G and not part of this phase:

```text
.hermes/
docs/plans/2026-04-24-sachima-channel.md
docs/superpowers/
```

Baseline focused gate in the new Phase 5G worktree:

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

## Context Inspected

```text
AGENTS.md
docs/plans/2026-05-06-flowweaver-phase5f-local-runtime-e2e-reconciliation-harness.md
docs/dev_log/2026-05-06-flowweaver-phase5f-local-runtime-e2e-reconciliation-harness.md
gateway/flowweaver_shadow_publisher.py
gateway/flowweaver_runtime_contract.py
gateway/flowweaver_mock_durable.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/publication_adapter.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py
tests/gateway/test_flowweaver_shadow_publisher.py
tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py
tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py
tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py
tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py
```

Important current facts:

1. Phase 5F intentionally proves final-text-only local reconciliation and keeps final text + rich-card ACK surfaces as a mismatch because the start payload initializes only one delivery slot.
2. `build_flowweaver_delivery_ack_updates()` can emit multiple ACK targets (`runtime_delivery_0`, `runtime_delivery_1`, ...), but `_start_request_from_envelope()` currently keeps `record_counts.deliveries` equal to the replay corpus entry count.
3. `RuntimeStartPayload` validation currently requires `deliveries == entry_count`, and both the real POC workflow source and Phase 5F fake runtime initialize delivery statuses using `entry_count` instead of `record_counts["deliveries"]`.
4. `publish_shadow_runtime_publication()` already replays every ACK update in order, but its fake tests do not validate that the start payload planned matching delivery slots.
5. `build_flowweaver_delivery_ack_updates()` bounds rich cards with `rich_cards[:20]`, which can still produce 21 total ACKs when final text is also sent; the local adapter rejects more than 20 ACK updates.
6. No `AI_FLOW.md` exists in this repository worktree; `AGENTS.md` is the repo-local developer guide. The user’s established Sachima workflow still applies: design before code, TDD after approval, low-intrusion first.

## Why Phase 5G

Phase 5F proved that local runtime reconciliation catches ACK/publication/runtime drift. Its most useful negative case is now the next obvious contract hardening step:

```text
publication emits: runtime_delivery_0 + runtime_delivery_1
start payload initializes: runtime_delivery_0 only
result today: reconciliation_mismatch
```

Before running a real local Temporal Worker reconciliation phase, the durable ingress contract must know how many delivery slots exist. Otherwise real runtime testing will just make an already-known cardinality bug slower to debug.

## Approach Options

### Option A — Keep Phase 5F behavior and defer rich-card ACK parity to real Temporal

Pros:
- No new diff.
- Maintains the current negative test exactly.

Cons:
- Carries a known contract mismatch into the next runtime phase.
- Makes real Temporal validation noisier and less valuable.
- Leaves publication ACK targets ahead of start payload delivery slots.

Verdict: **Reject.** This is knowingly dragging mud into the house.

### Option B — Hardcode one extra rich-card slot

Pros:
- Tiny change for the immediate final-text + one rich-card case.

Cons:
- Breaks as soon as there are multiple rich cards or other surfaces.
- Encodes surface-specific behavior in the runtime slot count.
- Does not align with the existing bounded ACK list model.

Verdict: **Reject.** Too brittle.

### Option C — Derive delivery slot count from emitted ACK surfaces, bounded by contract

Pros:
- Generalizes final text, rich cards, progress cards, media, and prototype surfaces.
- Preserves existing corpus entry count semantics for intents/artifacts.
- Keeps Gateway/platform production behavior unchanged and default-off.
- Lets Phase 5F reconciliation become a positive proof for rich-card publications.
- Gives a clean contract to reuse in Phase 5H real local Temporal Worker validation.

Cons:
- Requires coordinated prototype contract updates across publisher, payload validation, fake runtime snapshot, and workflow source.
- Existing tests that assumed `deliveries == entry_count` need to become more precise.

Verdict: **Recommended.** It fixes the actual contract instead of wallpapering the symptom.

## Recommended Design

### 1. Delivery slot cardinality rule

Define one helper-level rule in the shadow publisher:

```text
delivery_slot_count = max(mock_durable_record_counts.deliveries, len(ack_bridge.updates))
```

Boundaries:

- `transactions == 1` remains unchanged.
- `intents == entry_count` remains unchanged.
- `artifacts == entry_count` remains unchanged.
- `deliveries >= entry_count` and `deliveries <= 20`.
- ACK bridge emits at most 20 updates total, not “20 rich cards plus final text”.
- Initialized runtime delivery slots are the exact closed set `runtime_delivery_0..runtime_delivery_{deliveries-1}`.
- Emitted ACK target IDs must be a deterministic contiguous prefix/subset of initialized slots for actual ACK updates only; never invent ACK updates just to cover unused delivery slots.
- No raw platform IDs, chat/user/message IDs, card payloads, credential-shaped values, or raw exception text enter the publication, payload, snapshot, logs, or returned results.

### 2. Publisher changes

Modify:

```text
gateway/flowweaver_shadow_publisher.py
```

Planned minimal changes:

1. Build `ack_updates` before finalizing `start_request`, because the start payload needs the ACK count.
2. Cap total ACK updates to 20 in `build_flowweaver_delivery_ack_updates()`.
3. Add a small helper such as `_start_request_with_delivery_cardinality(start_request, ack_updates)` or extend `_start_request_from_envelope(envelope, *, ack_update_count)`.
4. Copy the start payload and record counts; do not mutate envelope or caller input.
5. Set `record_counts["deliveries"] = max(existing_deliveries, len(ack_updates))` when the value is safe and within bounds.
6. Return rejected publication if the derived count is invalid instead of emitting an unsafe or self-contradictory start request.

### 3. Runtime payload and snapshot changes

Modify:

```text
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py
```

Planned minimal changes:

1. Relax `RuntimeStartPayload` record count validation only for deliveries:
   - `transactions == 1`
   - `intents == entry_count`
   - `artifacts == entry_count`
   - `entry_count <= deliveries <= 20`
2. Keep ID and claim-check validation unchanged.
3. In the POC workflow source, initialize delivery statuses from `payload.record_counts["deliveries"]`, not `payload.entry_count`.
4. In `InMemoryFlowWeaverRuntimeClient`, initialize `delivery_statuses` and snapshot `counts["deliveries"]` from `payload.record_counts["deliveries"]`, not `payload.entry_count`.
5. In reconciliation parity checks, compare intent/artifact status-map cardinality to `entry_count`, but delivery status-map cardinality to `record_counts["deliveries"]`.
6. Keep Phase 5F’s tampered/mismatched snapshot tests: a publication whose ACK target lacks a matching runtime delivery slot must still return `reconciliation_mismatch`.

### 4. Tests

Create:

```text
tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py
```

Core RED tests before implementation:

1. `test_phase5g_shadow_publication_sets_delivery_count_from_ack_surfaces`
   - Build final-text + one rich-card shadow publication.
   - Assert ACK targets are `runtime_delivery_0` and `runtime_delivery_1`.
   - Assert `start_request.start_payload.record_counts.deliveries == 2` while `entry_count == 1`.
   - Assert no raw/private/platform values are rendered.

2. `test_phase5g_reconciles_rich_card_publication_with_runtime_snapshot`
   - Build final-text + one rich-card publication.
   - Reconcile through `InMemoryFlowWeaverRuntimeClient`.
   - Assert success, ACK statuses `applied/applied`, `applied_event_count == 2`, and snapshot delivery statuses for both delivery slots are `sent`.

3. `test_phase5g_replay_of_rich_card_publication_is_idempotent`
   - Reconcile the same rich-card publication twice.
   - Assert first call applies both ACKs; second call reports duplicates without increasing state.

4. `test_phase5g_delivery_ack_projection_caps_total_updates_at_twenty`
   - Build final text plus more than 19 rich-card records.
   - Assert exactly 20 ACK updates total, target IDs `runtime_delivery_0..runtime_delivery_19`, and `record_counts.deliveries == 20`.
   - Assert raw card/message material is absent.

5. `test_phase5g_start_payload_validation_allows_extra_delivery_slots_but_rejects_invalid_counts`
   - `RuntimeStartPayload(entry_count=1, deliveries=2)` validates.
   - `deliveries < entry_count`, `deliveries == 0`, and `deliveries > 20` reject with stable safe errors.

6. `test_phase5g_workflow_source_initializes_delivery_statuses_from_record_count`
   - AST/source scan `flowweaver_temporal_poc/workflows.py`.
   - Fail while delivery statuses are initialized with `range(payload.entry_count)`.
   - Pass only when delivery statuses are initialized from a safe delivery-count value derived from `payload.record_counts["deliveries"]`.

7. `test_phase5g_source_has_no_gateway_runtime_lifecycle_or_platform_wiring`
   - Static/AST scan changed prototype source and publisher added lines.
   - Fail on new `gateway/run.py`, platform adapter imports, runtime client factories, `Client.connect`, Worker/test environment, `start_workflow`, `execute_update`, subprocess, Docker, service lifecycle, config writes, and tool/global registry wiring.

Update existing tests only where they encode the old mismatch as normal behavior:

- Change the Phase 5F extra-ACK negative test to tamper the start payload delivery count down to one, so mismatch detection remains covered.
- Add assertions to existing publisher/adapter tests that multi-ACK publications start with matching delivery count.
- Do not weaken existing safe-output, synthetic-ID, idempotency, and no-lifecycle tests.

### 5. Boundary and changed-file allowlist

Allowed Phase 5G files:

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

Forbidden without separate explicit user approval:

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

### 6. Implementation Tasks

#### Task 1: Add Phase 5G RED tests

**Objective:** Prove current code fails the rich-card delivery cardinality contract before touching implementation.

**Files:**
- Create: `tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py`
- Modify: `tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py`
- Modify: `tests/gateway/test_flowweaver_shadow_publisher.py`
- Modify: `tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py`
- Modify: `tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py`

**Step 1: Write failing tests**

Add tests for final text + rich card publication delivery count, local reconciliation success, replay idempotency, 20-update cap, payload validation for deliveries > entry count, and preserved tampered mismatch detection.

**Step 2: Verify RED**

Run:

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py::test_phase5f_detects_extra_ack_surface_without_matching_runtime_delivery_slot \
  tests/gateway/test_flowweaver_shadow_publisher.py::test_shadow_runtime_publication_ack_targets_remain_bounded_synthetic_delivery_ids \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py::test_shadow_publication_adapter_starts_runtime_once_then_applies_acks_in_order \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  -q
```

Expected before implementation: Phase 5G tests fail because deliveries still equal entry count, rich-card reconciliation still mismatches, and workflow source still initializes delivery slots from `payload.entry_count`.

#### Task 2: Align publisher delivery count with ACK surfaces

**Objective:** Make shadow publications initialize enough runtime delivery slots for emitted ACK updates while staying bounded and side-effect-free.

**Files:**
- Modify: `gateway/flowweaver_shadow_publisher.py`
- Test: `tests/gateway/test_flowweaver_shadow_publisher.py`
- Test: `tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py`

**Step 1: Implement minimal publisher change**

Compute ACK updates before final start request output, cap total ACK updates at 20, and write `record_counts.deliveries` to the safe derived delivery slot count.

**Step 2: Verify GREEN for publisher tests**

Run:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_shadow_publisher.py \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py::test_phase5g_shadow_publication_sets_delivery_count_from_ack_surfaces \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py::test_phase5g_delivery_ack_projection_caps_total_updates_at_twenty \
  -q
```

Expected after implementation: targeted tests pass.

#### Task 3: Relax runtime payload delivery count contract safely

**Objective:** Allow extra delivery slots without weakening transaction/intent/artifact or safety validation.

**Files:**
- Modify: `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py`
- Test: `tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py`
- Test: `tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py`

**Step 1: Implement minimal payload validation change**

Permit `entry_count <= deliveries <= 20` while keeping all other count and safety rules unchanged.

**Step 2: Verify GREEN for payload/contract tests**

Run:

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py::test_phase5g_start_payload_validation_allows_extra_delivery_slots_but_rejects_invalid_counts \
  -q
```

Expected after implementation: targeted tests pass.

#### Task 4: Align local runtime snapshots with delivery counts

**Objective:** Make both prototype workflow source and fake runtime snapshot initialize delivery status maps from the delivery count, not the entry count.

**Files:**
- Modify: `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py`
- Modify: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py`
- Test: `tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py`
- Test: `tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py`

**Step 1: Implement minimal snapshot cardinality change**

Use `payload.record_counts["deliveries"]` for delivery status map initialization. Keep intent/artifact maps tied to `entry_count`.

**Step 2: Verify GREEN for reconciliation and workflow-source tests**

Run:

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  -q
```

Expected after implementation: rich-card publication reconciles, replay is idempotent, workflow source initializes delivery slots from `record_counts["deliveries"]`, and tampered missing-slot publications still mismatch.

#### Task 5: Full focused gate, static scans, review, commit, PR

**Objective:** Prove Phase 5G did not introduce production wiring, unsafe output, dependency drift, or test regressions.

**Files:**
- All allowed Phase 5G files.

**Step 1: Run focused tests**

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py \
  tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py \
  tests/gateway/test_flowweaver_shadow_publisher.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  -q
```

**Step 2: Run syntax/lint/diff gates**

```bash
python -m py_compile \
  gateway/flowweaver_shadow_publisher.py \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py

python -m ruff check \
  gateway/flowweaver_shadow_publisher.py \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py

git diff --check
```

**Step 3: Run custom gates**

- changed-file allowlist covering worktree diff, staged diff, untracked files, and committed `merge-base..HEAD` changes before PR;
- no `gateway/run.py`, `gateway/platforms/**`, production config, global registry, or base dependency diff across unstaged, staged, untracked, and committed `merge-base..HEAD` surfaces;
- source/diff scan for new runtime lifecycle or production wiring across all changed source, added diff hunks, staged diff, and committed `merge-base..HEAD` hunks;
  - explicitly fail dynamic hidden imports/factories such as `importlib`, `__import__`, `getattr(..., "connect")`, aliased `.connect` calls, runtime client construction helpers, `Client.connect`, Temporal `Worker`, Temporal testing environment imports/classes, `start_workflow`, `get_workflow_handle`, `execute_update`, `workflow.signal` / `@workflow.signal`, subprocess variants, Docker/systemctl/daemon terms, socket/HTTP listener startup, config writes via `open` or `Path.write_*`, `gateway.platforms`, `gateway.run`, and tool/global registry imports;
- no payload-carrying Signal additions in changed runtime-related files;
- no new `print`, `logging`/`logger.*`, raw exception interpolation, or `repr`/serialization of `agent_result`, `delivery_state`, card/message payloads, platform IDs, or credential-shaped values in changed source;
- stable safe error-code tests for all new rejection paths;
- no raw/private/platform/credential-shaped material in returned results, docs, test fixtures, logs, or source literals outside existing forbidden-material policy metadata;
- ACK target parity scan: every emitted publication ACK target has a corresponding initialized runtime delivery slot; emitted ACK targets may be a prefix/subset when initialized delivery slots exceed actual ACKs, and tests must prove no invented ACKs are emitted;
- bounded total ACK update count scan: no publication emits more than 20 ACK updates.

**Step 4: Independent reviews**

Run two independent reviews before commit/PR:

1. spec compliance review against this plan;
2. security/low-intrusion review focused on Gateway production isolation, runtime lifecycle absence, safe output, ACK cardinality, and snapshot parity.

If reviewers find blockers, add RED regression tests first, fix minimally, rerun focused gates and blocker-only review.

**Step 5: Commit and open PR**

Commit with a conventional message and open a PR against `feature/sachima-channel`. Do not merge the PR or delete the remote branch without explicit user instruction.

## Out of Scope

- Real Temporal test-environment integration.
- Worker/service lifecycle management.
- Gateway restart.
- Production configuration writes.
- Any production Gateway → runtime publish path.
- UI/dashboard/Feishu card changes.
- Full long-task AI FLOW orchestration.
- PR merge or remote branch deletion.

## Acceptance Criteria

Phase 5G is complete only if:

1. final-text-only publication behavior remains green;
2. final-text + rich-card publication initializes matching delivery slots and reconciles successfully;
3. same rich-card publication replay is idempotent and does not create duplicate dirty state;
4. ACK bridge total update count is bounded at 20, emitted target IDs are deterministic synthetic delivery IDs within initialized slots, and no ACKs are invented for unused slots;
5. tampered/mismatched ACK target publications still return `reconciliation_mismatch` without leaking raw values;
6. payload validation allows extra delivery slots only within the safe bounded rule;
7. fake runtime and POC workflow source initialize delivery maps from delivery count, not entry count;
8. no production Gateway/platform/runtime lifecycle/dependency/config/global-registry surface changes are introduced;
9. all focused tests, compile, lint, diff, and custom scans pass;
10. independent reviewers return PASS after any blocker fixes;
11. the final dev log records RED/GREEN evidence, verification output, review results, and missed-test reflection.
