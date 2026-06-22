# FlowWeaver Phase 5F Local Runtime E2E Reconciliation Harness Implementation Plan

> **For Hermes:** This document is the Phase 5F design gate. Do not write implementation code until the user explicitly approves this plan. After approval, implement with strict TDD, focused gates, and independent review.

**Goal:** Prove the Phase 5D/5E shadow publication path can complete a local end-to-end runtime loop and reconcile runtime query snapshots against the original safe publication, without wiring production Gateway to Temporal.

**Architecture:** Keep production Gateway and platform behavior unchanged. Add prototype-only, service-free reconciliation utilities around the existing Phase 5C local publication adapter: an in-memory fake runtime client that exposes the same narrow runtime-client methods, plus a safe reconciliation harness that publishes a ready shadow runtime publication, queries the resulting snapshot, and compares IDs/counts/delivery ACK state with the original publication. Tests build realistic shadow publications through the existing Gateway shadow helpers, but no production Gateway entrypoint imports the harness.

**Tech Stack:** Python, pytest, existing Gateway FlowWeaver shadow helpers, existing Phase 5B payload/snapshot contracts, existing Phase 5C `publication_adapter`. Phase 5F verification uses fake-client/static/source gates only; Temporal test environments, Workers, Docker, CLIs, daemons, and production service changes are deferred.

---

## Current Baseline

Timestamp: 2026-05-06 11:19:08 CST +0800

Repository / branch state observed before this Phase 5F design gate:

```text
canonical repo: /home/ubuntu/workspace/hermes/repo/sachima
canonical branch: feature/sachima-channel
canonical HEAD: b3dd866363a4a2ecff3b6a72a575a18ffee611b1
PR #31 / Phase 5E: MERGED, merge commit b3dd866363a4a2ecff3b6a72a575a18ffee611b1
Phase 5F worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5f-local-runtime-e2e-reconciliation-harness
Phase 5F branch: feat/flowweaver-phase5f-local-runtime-e2e-reconciliation-harness
Phase 5F base: origin/feature/sachima-channel @ b3dd866363a4a2ecff3b6a72a575a18ffee611b1
```

Baseline focused gate in the new Phase 5F worktree:

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

## Context Inspected

```text
AGENTS.md
docs/plans/2026-05-06-flowweaver-phase5e-variable-runtime-ids-local-publish-adapter.md
docs/dev_log/2026-05-06-flowweaver-phase5e-variable-runtime-ids-local-publish-adapter.md
gateway/flowweaver_shadow_publisher.py
gateway/flowweaver_runtime_identity.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/publication_adapter.py
tests/gateway/test_flowweaver_shadow_publisher.py
tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py
tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py
tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py
```

Important current facts:

1. Phase 5E now emits per-shadow-turn synthetic IDs like `runtime_tx_shadow_<20-hex>` and `runtime_event_start_shadow_<20-hex>`.
2. Phase 5E added `publish_shadow_runtime_publication(publication, *, runtime_client)`, but it only verifies start + ACK calls against an injected fake client; it does not query a resulting snapshot or compare it with the source publication.
3. The Phase 5B workflow snapshot shape already includes the reconciliation fields we need: `transaction_id`, `entry_count`, `record_counts`, `counts`, `intent_statuses`, `artifact_statuses`, `delivery_statuses`, `applied_event_count`, and `side_effects`.
4. Existing integration tests start a Temporal test environment and Worker. Phase 5F should not do that; it should prove the contract locally with a fake runtime client and source/static gates.
5. `gateway/run.py`, `gateway/platforms/**`, tool registry, production config, and service lifecycle remain out of scope.
6. No `AI_FLOW.md` exists in this repository worktree; `AGENTS.md` is the repo-local developer guide. The user’s established Sachima workflow still applies: design before code, TDD after approval, low-intrusion first.

## Why Phase 5F

Phase 5E proved safe IDs and a local publication adapter, but the proof stops at “the adapter called `start_transaction()` and `record_delivery_ack()`.” Durable orchestration needs a stronger invariant: after publication and ACK replay, a runtime query snapshot must reconcile with the shadow publication that produced it.

Phase 5F should therefore prove the whole local loop:

```text
shadow turn → synthetic runtime ID → ready publication → local publish adapter → fake runtime state → delivery ACK updates → query snapshot → reconciliation result
```

This is not live Gateway → Temporal. It is a service-free contract harness that catches state drift before any real runtime worker or dashboard work.

## Approach Options

### Option A — Add more assertions to existing Phase 5E adapter tests

Pros:
- Smallest diff.
- No new source module.

Cons:
- Keeps the proof scattered inside test fixtures.
- Does not give later phases a reusable local reconciliation entrypoint.
- Makes it harder to run the same contract against a real local runtime later.

Verdict: **Reject.** Useful as a regression, not enough as a phase boundary.

### Option B — Add prototype-only fake runtime client + reconciliation harness

Pros:
- Builds a reusable, explicit local E2E proof without service lifecycle.
- Keeps runtime-facing logic under the existing prototype runtime-client package.
- Lets tests validate idempotency, duplicate ACKs, query parity, and safe output in one place.
- Can later be reused as the comparison harness for a real local Temporal worker in a separately approved phase.

Cons:
- Adds a small fake runtime implementation that must stay clearly prototype-only.
- Needs strict source scans so it does not become a hidden runtime factory or Gateway bridge.

Verdict: **Recommended.** This is the narrowest useful next proof.

### Option C — Run a real Temporal test environment for E2E

Pros:
- Closer to the final durable runtime.

Cons:
- Starts a test server/worker lifecycle, which this safety-constrained phase should avoid.
- Reintroduces operational concerns before local contract parity is proven.
- Overlaps with existing Phase 5C integration coverage instead of hardening the new Phase 5D/5E bridge.

Verdict: **Reject for Phase 5F.** Save it for a later explicitly approved runtime-worker phase.

## Recommended Design

### 1. Prototype-only in-memory runtime client

Create:

```text
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py
```

Add a class such as:

```python
class InMemoryFlowWeaverRuntimeClient:
    async def start_transaction(self, payload: object, *, workflow_id: str) -> dict[str, object]: ...
    async def record_delivery_ack(self, workflow_id: str, update: object) -> dict[str, object]: ...
    async def query_snapshot(self, workflow_id: str) -> dict[str, object]: ...
```

Rules:

- Use the same safe Phase 5B/5C validators as the real runtime client.
- Store only synthetic runtime IDs, bounded counts, synthetic `runtime_intent_*`, `runtime_artifact_*`, `runtime_delivery_*`, ACK fingerprints, and closed statuses.
- Return snapshots through the existing Phase 5C safe result helpers so the output whitelist stays identical to the runtime facade.
- `start_transaction()` is idempotent for the exact same workflow/payload and rejects mismatched reuse with a stable safe code.
- `record_delivery_ack()` returns `applied` for a first matching update, `duplicate` for the same event fingerprint, and `rejected` for conflicting reuse or invalid target state.
- No imports from `temporalio`, no `Client.connect`, no Worker/test environment, no subprocess/Docker/system service calls, no Gateway/platform imports, and no filesystem writes.

### 2. Safe reconciliation entrypoint

In the same module, add:

```python
async def reconcile_shadow_runtime_publication(publication: object, *, runtime_client: object) -> dict[str, object]: ...
```

Expected successful result shape:

```python
{
    "ok": True,
    "operation": "reconcile_shadow_runtime_publication",
    "workflow_id": "runtime_tx_shadow_<20-hex>",
    "transaction_id": "runtime_tx_shadow_<20-hex>",
    "status": "reconciled",
    "publication_status": "published",
    "snapshot_status": "running",
    "checks": {
        "runtime_ids_match": True,
        "entry_count_matches": True,
        "record_counts_match": True,
        "delivery_ack_count_matches": True,
        "delivery_statuses_match": True,
        "side_effects_absent": True,
    },
    "reconciliation": {
        "entry_count": 1,
        "record_counts": {"transactions": 1, "intents": 1, "artifacts": 1, "deliveries": 1},
        "ack_statuses": ["applied"],
        "applied_event_count": 1,
    },
    "side_effects": [],
}
```

Error result shape:

```python
{"ok": False, "operation": "reconcile_shadow_runtime_publication", "error_code": "<stable_safe_code>"}
```

Allowed error codes:

```text
invalid_publication
invalid_start_payload
invalid_delivery_ack_update
unsafe_snapshot
reconciliation_mismatch
runtime_error
```

The entrypoint should:

1. call the existing `publish_shadow_runtime_publication()` adapter once;
2. if publish fails, return only its stable safe error code mapped to the reconciliation operation;
3. query the runtime snapshot by workflow ID;
4. sanitize the snapshot using existing Phase 5C contracts;
5. compare publication IDs, start payload counts, ACK count, delivery statuses, and side-effect emptiness;
6. return only bounded safe summary fields.

Replay/idempotency is verified by calling this same entrypoint repeatedly in tests against the same in-memory runtime client. A single reconciliation result should report only the statuses observed during that call; the first call should normally report `applied`, and a replay call should report `duplicate` without mutating snapshot state.

### 3. Gateway-driven local E2E test fixture

Add tests that build a realistic publication through existing Gateway shadow helpers:

```text
tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py
```

The tests may import Gateway helper modules because they are test-only; production/prototype source modules should not import Gateway.

Core tests:

1. `test_phase5f_reconciles_shadow_publication_with_runtime_snapshot`
   - Build a shadow agent result with final text sent and no extra rich-card ACK surfaces.
   - Attach shadow snapshot and dry-run.
   - Build ready runtime publication.
   - Run reconciliation through `InMemoryFlowWeaverRuntimeClient`.
   - Assert workflow ID, transaction ID, entry counts, record counts, first-call ACK status, delivery status for `runtime_delivery_0`, and `side_effects == []` reconcile.

2. `test_phase5f_replay_of_same_publication_is_idempotent`
   - Run the same final-text-only publication twice against the same in-memory client.
   - Assert the first pass reports `ack_statuses == ["applied"]`.
   - Assert the second pass reports `ack_statuses == ["duplicate"]` without increasing `applied_event_count` or creating additional delivery keys.

3. `test_phase5f_detects_extra_ack_surface_without_matching_runtime_delivery_slot`
   - Build a publication with final text plus one rich-card ACK surface.
   - Keep the start payload at the current one-entry Phase 5E shape.
   - Assert reconciliation returns `reconciliation_mismatch` or a stable safe invalid-ACK code, and does not silently pretend `runtime_delivery_1` exists.
   - This is Phase 5F evidence for a later delivery-cardinality hardening phase, not permission to modify Gateway publisher behavior in Phase 5F.

4. `test_phase5f_reconciliation_detects_mismatched_snapshot_without_echoing_raw_values`
   - Use a fake runtime client that returns a safe but mismatched snapshot.
   - Assert `reconciliation_mismatch` and no workflow/raw/private/credential-shaped material is echoed.

5. `test_phase5f_rejects_unsafe_publication_before_querying_runtime`
   - Mutate publication IDs or ACK updates with platform/private marker text.
   - Assert stable safe error and `query_snapshot()` is never called.

6. `test_phase5f_harness_source_has_no_service_lifecycle_or_gateway_wiring`
   - AST/static scan the new source module.
   - Fail on `temporalio`, real runtime-client factories/construction, temporal addresses/task queues, generic connect helpers, `FlowWeaverRuntimeClient.connect`, `connect_local_temporal`, workflow imports, `start_workflow`, `get_workflow_handle`, `execute_update`, subprocess/Docker/system service terms, Gateway imports, platform adapter imports, file writes, config writes, and global registry/toolset imports.
   - The scan must inspect all source text plus AST imports/calls/attributes so function-local imports and calls are covered.

### 4. Boundary and changed-file allowlist

Allowed Phase 5F files:

```text
docs/plans/2026-05-06-flowweaver-phase5f-local-runtime-e2e-reconciliation-harness.md
docs/dev_log/2026-05-06-flowweaver-phase5f-local-runtime-e2e-reconciliation-harness.md
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/__init__.py  # only if exporting a version marker is useful
tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py
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

### 5. Verification plan

After implementation, run focused tests:

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py \
  tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py \
  tests/gateway/test_flowweaver_shadow_publisher.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  -q
```

Run syntax/static gates:

```bash
python -m py_compile \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py

python -m ruff check \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py

git diff --check
```

Run custom gates:

- changed-file allowlist covering worktree diff, staged diff, and untracked files;
- source AST scan for hidden service lifecycle / Gateway wiring / config write / registry write;
  - scan all new source text plus AST imports/calls/attributes;
  - explicitly fail hidden factories, temporal addresses/task queues, generic connect helpers, `FlowWeaverRuntimeClient.connect`, `connect_local_temporal`, workflow imports, `start_workflow`, `get_workflow_handle`, `execute_update`, `Client.connect`, Worker/test environment, subprocess/Docker/system service terms, Gateway/platform imports, file writes, config writes, and registry/toolset imports;
- no payload-carrying Signal scan on changed runtime-related files;
- no private/platform/credential-shaped literal leakage in returned results, logs, docs, or test fixtures;
- no `gateway/run.py` or platform adapter diff;
- no base dependency change.

Run independent reviews before commit/PR:

1. spec compliance review against this plan;
2. security/low-intrusion review focused on hidden lifecycle, Gateway wiring, unsafe output, replay/idempotency, and reconciliation correctness.

If reviewers find blockers, add RED regression tests first, fix minimally, rerun focused gates and blocker-only review.

## Out of Scope

- Real Temporal test-environment integration.
- Worker/service lifecycle management.
- Gateway restart.
- Production configuration writes.
- Any production Gateway → runtime publish path.
- UI/dashboard/Feishu card changes.
- Long-task AI FLOW orchestration.
- PR merge or remote branch deletion.

## Acceptance Criteria

Phase 5F is complete only if:

1. a realistic final-text Gateway shadow publication reconciles with a local runtime query snapshot;
2. same-publication replay is idempotent and does not create duplicate dirty state;
3. extra ACK surfaces that do not have matching runtime delivery slots are detected instead of silently reconciled;
4. mismatched snapshots produce `reconciliation_mismatch` without leaking raw values;
5. unsafe publication material is rejected before runtime query;
6. new source has no Temporal/service/Gateway wiring lifecycle behavior;
7. all focused tests, compile, lint, diff, and custom scans pass;
8. independent reviewers return PASS after any blocker fixes;
9. the final dev log records RED/GREEN evidence, verification output, review results, and missed-test reflection.
