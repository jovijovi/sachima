# FlowWeaver Phase 7 Gateway Shadow E2E Loop / IM Simulator Harness Implementation Plan

> **For Hermes:** 狗哥 approved moving into Phase 7 on 2026-05-07 and explicitly allowed Codex as a temporary system architect/reviewer/coder when given enough context and concrete deliverables. This document is the Phase 7 design gate. Do not implement behavior-bearing code until the design gate has passed review and 狗哥 approves execution.

**Goal:** Prove a full shadow-only Gateway publication-to-ACK reconciliation loop: start/query a runtime transaction, build a sanitized simulated Gateway publication envelope, simulate delivery ACKs, feed those ACKs through the Phase 6 bridge, and verify the final runtime snapshot without touching production Gateway or real Feishu.

**Architecture:** Add a prototype-only, default-off E2E harness in the FlowWeaver runtime-client prototype. It consumes an already-safe Phase 5D/5G runtime publication summary, uses only caller-supplied control surfaces, builds a new sanitized shadow publication envelope, and delegates ACK reconciliation to Phase 6. It must never import platform adapters, start services, register tools, or handle raw platform payloads.

**Tech Stack:** Python, pytest, existing FlowWeaver Phase 5B/5C/5F/5G/5K runtime prototypes, existing Phase 6 `gateway_ack_shadow_bridge`, optional Temporal test worker only inside existing integration pytest gates.

---

## Baseline

```text
Timestamp: 2026-05-07 11:19:52 CST +0800
Repository: jovijovi/sachima
Base branch: origin/feature/sachima-channel
Base HEAD: 654b4bafd79da394dc6f23ce5ce430b733c90533
Phase 7 branch: feat/flowweaver-phase7-gateway-shadow-e2e-loop
Phase 7 worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase7-gateway-shadow-e2e-loop
```

Fresh baseline verification before Phase 7 docs/code:

```text
Prototype regression: 110 passed in 0.79s
Integration regression: 36 passed in 1.70s
```

`/home/ubuntu/workspace/hermes/repo/sachima-im-simulator` was inspected as context only. It is a separate private repo and its main checkout currently has unrelated local doc changes, so Phase 7 should not modify that repository in this Sachima PR. This Phase 7 slice may model the simulator as an in-repo fake/shadow harness; cross-repo simulator changes require a separate plan/PR.

## Current Context

Already merged:

- **Phase 5 / Durable Runtime Foundation through 5K**
  - Runtime start/query/update contracts.
  - `FlowWeaverRuntimeControlSurface` maps safe control requests to runtime methods.
  - Fake runtime and local Temporal parity for safe snapshots and delivery ACKs.
- **Phase 6 / Gateway ACK Shadow Bridge**
  - `flowweaver_runtime_client.gateway_ack_shadow_bridge.reconcile_shadow_gateway_ack()` accepts only exact safe ACK envelopes.
  - Bridge preflights `query_transaction`, verifies `target_id` exists in `snapshot.delivery_statuses`, then calls `reconcile_delivery_ack`.
  - ACK statuses are limited to `sent`, `failed`, `acknowledged`; `skipped` is intentionally rejected.

Existing publication/runtime helpers:

- `gateway.flowweaver_shadow_publisher.build_flowweaver_shadow_runtime_publication()` builds a safe ready publication summary with:
  - `start_request` for `start_transaction`.
  - `ack_bridge.updates` with synthetic delivery ACK updates.
  - `side_effects: []`.
- `flowweaver_runtime_client.publication_adapter.publish_shadow_runtime_publication()` can start a runtime and apply ACK updates directly. Phase 7 must **not** rely on that direct ACK path for the new E2E proof; it should route simulated ACKs through Phase 6.
- `flowweaver_runtime_client.reconciliation_harness.InMemoryFlowWeaverRuntimeClient` is useful for fake runtime parity, but Phase 7 should prefer `FlowWeaverRuntimeControlSurface` because Phase 6 works through that boundary.

## Proposed Approach

Create a new prototype-only module:

```text
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/gateway_shadow_e2e_loop.py
```

Public constants:

```text
FLOWWEAVER_GATEWAY_SHADOW_E2E_LOOP_VERSION = "flowweaver.gateway_shadow_e2e_loop.v0"
SHADOW_PUBLICATION_ENVELOPE_TYPE = "flowweaver.gateway_shadow_publication.v0"
```

Primary entrypoint:

```text
async def run_shadow_gateway_e2e_loop(control_surface, publication) -> dict[str, object]
```

The entrypoint must:

1. Validate `publication` is the exact safe ready publication shape already emitted by Phase 5D/5G.
2. Extract and validate `workflow_id`, `transaction_id`, `start_request`, and `ack_bridge.updates` before any runtime call.
3. Call `control_surface.handle({"operation": "start_transaction", ...})` with the validated start request.
4. Perform a bounded async readiness query/poll through `query_transaction` until a sanitized running snapshot is available, or return stable `snapshot_unavailable` without raw exception text.
5. Build a Phase 7 shadow publication envelope from the safe publication plus snapshot delivery slots.
6. Validate every simulated delivery target exists in the snapshot before ACK simulation.
7. Convert each simulated delivery into a Phase 6 ACK envelope and call `reconcile_shadow_gateway_ack(control_surface, ack_envelope)`.
8. Query a final sanitized snapshot.
9. Return a compact safe result with counts, ACK statuses, checks, and final snapshot.

Phase 7 must be a **caller-supplied-client harness** only. No factories, no connection helpers, no lazy Temporal client construction, and no service lifecycle. The module may use bounded `await`/async polling, but it must not own the event loop: no `asyncio.run`, no event-loop creation, no background tasks, no task groups, and no hidden process/service lifecycle.

## Safe Shadow Publication Envelope

The new shadow publication envelope is an internal, sanitized simulation artifact. It is not a production Gateway payload.

Allowed top-level fields only:

```text
type
loop_version
workflow_id
transaction_id
surface_counts
delivery_plan
side_effects
```

Allowed values:

```text
type = flowweaver.gateway_shadow_publication.v0
loop_version = flowweaver.gateway_shadow_e2e_loop.v0
workflow_id = runtime_tx_*
transaction_id = same as workflow_id
surface_counts = {final_text: int, rich_card: int, progress_card: int, media: int}
delivery_plan[] = exact safe delivery descriptors
side_effects = []
```

Each delivery descriptor contains only:

```text
delivery_key = runtime_event_*
surface = final_text | rich_card | progress_card | media
target_kind = delivery
target_id = runtime_delivery_*
status = sent | failed | acknowledged
```

Explicitly forbidden anywhere in input, publication envelope, ACK envelopes, returned results, logs, snapshots, and docs evidence:

```text
raw prompt/tool output
raw card JSON
media bytes or media path
raw platform payload
raw chat/user/message identifiers
credentials, tokens, secrets, connection strings
raw exception text
```

## Result Shape

Allowed top-level fields only:

```text
ok
loop_version
operation
workflow_id
transaction_id
start_status
publication
ack_results
final_snapshot
checks
side_effects
error_code
```

Rules:

- `operation` is always `gateway_shadow_e2e_loop`.
- `publication` is the Phase 7 safe shadow publication envelope, never the raw input publication.
- `ack_results` contains only per-target safe summaries: `target_id`, `surface`, `status`, `ack_status`, `error_code`.
- `checks` must include:
  - `start_accepted`
  - `initial_snapshot_safe`
  - `publication_envelope_safe`
  - `delivery_targets_initialized`
  - `ack_count_matches_publication`
  - `final_snapshot_safe`
  - `side_effects_absent`
- Error results use stable error codes only and must not include offending values.

Stable error codes:

```text
invalid_publication
invalid_start_payload
invalid_delivery_plan
start_failed
snapshot_unavailable
workflow_id_mismatch
delivery_target_mismatch
ack_reconciliation_failed
runtime_error
unsafe_output
```

## Out of Scope

```text
Production Gateway/Feishu integration
gateway/run.py changes
gateway/platforms/** changes
run_agent.py changes
model_tools.py changes
toolsets.py changes
tools/** changes
hermes_cli/** changes
production Hermes tool registration
real send/edit/render/callback effects
platform adapter imports
raw platform payload ingestion
raw card/media payload ingestion
Docker / Temporal CLI / daemon / service startup
Gateway restart
global registry/config writes
~/.hermes/config.yaml writes
base dependency changes
payload-carrying Temporal Signals
external sachima-im-simulator repo changes
remote branch deletion
```

Integration tests may use the existing local Temporal pytest test environment exactly like Phase 6, but no external daemon, Docker, Gateway restart, or production service lifecycle is allowed.

## Step-by-step Plan

### Task 1: RED prototype import and API contract

**Objective:** Prove the new module/API does not exist yet and define default-off/import-safe boundaries.

**Files:**

- Create test: `tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py`
- Future implementation: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/gateway_shadow_e2e_loop.py`

**Test requirements:**

- Import fails before implementation because `flowweaver_runtime_client.gateway_shadow_e2e_loop` does not exist.
- After implementation, importing the module must not import:
  - `gateway.run`
  - `gateway.platforms.*`
  - `temporalio`
  - `mcp`
  - `tools.registry`
- Public API exposes only the two constants and `run_shadow_gateway_e2e_loop`.

**RED command:**

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py -q
```

Expected RED: failures caused by missing `flowweaver_runtime_client.gateway_shadow_e2e_loop`, not syntax or fixture errors.

### Task 2: RED prototype happy path through Phase 6 bridge

**Objective:** Define the safe fake-control-surface E2E loop: start, query, simulate publication, ACK through Phase 6, final query.

**Files:**

- Modify test: `tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py`

**Test requirements:**

- Build a ready safe publication using the existing Phase 5D/5G helper path or a minimal exact publication fixture.
- Use a recording control surface that supports `start_transaction`, `query_transaction`, and `reconcile_delivery_ack`.
- Assert call order begins with the loop-owned start and readiness query, then routes ACKs through Phase 6, then performs a final query:

```text
start_transaction
query_transaction [one or more bounded readiness checks]
reconcile_delivery_ack
query_transaction
```

- Assert the `reconcile_delivery_ack` call comes only from Phase 6 ACK bridge-shaped sanitized updates.
- Assert returned `publication` is `flowweaver.gateway_shadow_publication.v0` and contains only safe delivery descriptors.
- Assert final snapshot delivery statuses reflect the simulated ACKs.

### Task 3: RED prototype delivery cardinality and duplicate replay

**Objective:** Lock down the most important Phase 7 invariant: simulator ACKs are a bounded subset of initialized runtime delivery slots.

**Files:**

- Modify test: `tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py`

**Test requirements:**

- A publication with `runtime_delivery_0` and `runtime_delivery_1` succeeds only when the initial snapshot has both slots.
- A publication that tries to ACK `runtime_delivery_1` when the snapshot only initialized `runtime_delivery_0` returns `delivery_target_mismatch` before calling Phase 6 bridge/reconcile.
- Replaying the same publication returns duplicate ACK statuses without increasing `applied_event_count`.
- No invented ACKs are created to satisfy parity.

### Task 4: RED prototype no-leak and hostile material rejection

**Objective:** Prove raw platform/card/media/secret-shaped material cannot enter the E2E harness.

**Files:**

- Modify test: `tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py`

**Test requirements:**

- Reject extra fields such as `card_json`, `platform_payload`, `media_path`, raw chat/user/message identifiers, and credential-shaped values before runtime calls.
- Reject `skipped` status.
- Reject non-plain dictionaries and hostile mapping/value shapes if feasible within the existing helper pattern.
- Error results contain only stable `error_code` values, never offending IDs, raw exception text, or payload fragments.

### Task 5: RED integration parity through local Temporal test worker

**Objective:** Prove the same safe loop works against the real local runtime-control surface inside pytest.

**Files:**

- Create test: `tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py`

**Test requirements:**

- Create a local Temporal pytest environment/worker exactly like Phase 6 integration tests, but do not pre-start the workflow for the happy-path proof.
- Build a safe publication for a fresh `workflow_id` that has no existing workflow.
- Call `async def run_shadow_gateway_e2e_loop(control_surface, publication)` against that fresh unstarted workflow.
- Assert the entrypoint itself performs start -> bounded readiness query/poll -> Phase 6 ACK bridge -> final query.
- Assert delivery statuses / `applied_event_count` from the final snapshot.
- Replay the same publication after the first successful loop and assert duplicate/no-op behavior. This replay may exercise duplicate-start behavior, but it must not be the only happy-path proof.
- Try a missing-target ACK and assert no invented slot appears in final snapshot or Temporal history.
- Fetch history and assert no raw/platform/secret sentinels appear in JSON or serialized bytes.

**Integration command:**

```bash
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py \
  -q
```

Do not use `scripts/run_tests.sh` for `tests/integration/**`; it intentionally ignores integration tests.

### Task 6: GREEN implementation with Codex assist if RED is valid

**Objective:** Implement the minimal Phase 7 module to satisfy the RED tests without scope creep.

**Files:**

- Create: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/gateway_shadow_e2e_loop.py`

**Implementation constraints:**

- Implement `run_shadow_gateway_e2e_loop` as `async def`.
- Use caller-supplied `control_surface` only.
- Use Phase 6 `reconcile_shadow_gateway_ack` for all ACK reconciliation.
- Do not import production Gateway runtime or platform adapters.
- Do not import Temporal client/worker/workflows in the module.
- Do not own the event loop: no `asyncio.run`, no event-loop creation, no background tasks, no task groups.
- Do not start services, subprocesses, sockets, HTTP servers, Docker, or Gateway.
- Do not return or log raw exception text.
- Keep result sanitizers local and auditable.

### Task 7: Regression, static gates, and independent review

**Objective:** Verify Phase 7 plus previous FlowWeaver phases remain safe.

Focused prototype:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py -q
```

Focused integration:

```bash
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py \
  -q
```

Regression prototype:

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py \
  tests/prototypes/test_flowweaver_phase6_gateway_ack_shadow_bridge.py \
  tests/prototypes/test_flowweaver_phase5k_runtime_control_surface.py \
  tests/prototypes/test_flowweaver_phase5k_mcp_control_surface.py \
  tests/prototypes/test_flowweaver_phase5j_activity_contract.py \
  tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py \
  tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5c_tool_adapter.py \
  tests/prototypes/test_flowweaver_phase5c_mcp_server_surface.py \
  tests/prototypes/test_flowweaver_phase5c_tool_surface.py \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  -q
```

Regression integration:

```bash
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py \
  tests/integration/test_flowweaver_phase6_gateway_ack_shadow_bridge.py \
  tests/integration/test_flowweaver_phase5k_runtime_control_surface.py \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py \
  tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  -q
```

Static/security:

```bash
python -m py_compile \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/gateway_shadow_e2e_loop.py \
  tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py \
  tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py

python -m ruff check \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/gateway_shadow_e2e_loop.py \
  tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py \
  tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py

git diff --check
```

Custom gates:

- Changed-file allowlist covers committed, staged, unstaged, intent-to-add, and untracked files.
- No production Gateway/tool/global config/dependency/service lifecycle surface.
- No `gateway/platforms/**`, `gateway/run.py`, `run_agent.py`, `model_tools.py`, `toolsets.py`, `tools/**`, `hermes_cli/**`, or external simulator repo changes.
- No platform adapter imports, send/edit/render/callback calls, sockets, HTTP listeners, Docker/systemctl/subprocess lifecycle, global registry writes, or config writes.
- No payload-carrying Temporal Signals.
- No raw exception interpolation in returned results/logs.
- No raw/platform/card/media/secret sentinels in harness results, ACK envelopes, runtime snapshots, Temporal history JSON, or serialized event bytes.

Codex gates:

1. Fresh-context design review before implementation: `PASS` or `BLOCK` with concrete blockers.
2. If design blockers appear, patch this plan/dev log and run blocker-only Codex re-review.
3. After implementation, independent Codex implementation review: `PASS` or `BLOCK` with concrete blockers.
4. Any implementation blocker must first get a focused RED regression test before code fix.

## Acceptance Criteria

Phase 7 is complete only if:

1. A versioned prototype-only/default-off Gateway shadow E2E loop module exists.
2. The loop starts/query runtime through the control surface and ACKs only through the Phase 6 bridge.
3. A sanitized shadow publication envelope is generated and returned without raw payloads.
4. Simulator delivery ACKs are limited to initialized delivery slots; missing targets fail safely before ACK reconciliation.
5. Duplicate publication replay is idempotent and does not increase applied events.
6. Final snapshots and Temporal histories contain no raw prompt/tool/card/media/platform/secret material.
7. Existing Phase 5/6 regression suites remain green.
8. No production Gateway/platform/tool/config/dependency/service lifecycle surfaces are touched.
9. Codex design and implementation reviews have no blockers.
10. Final gates are rerun after any docs/dev-log evidence append.
