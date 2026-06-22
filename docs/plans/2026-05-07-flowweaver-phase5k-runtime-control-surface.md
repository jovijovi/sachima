# FlowWeaver Phase 5K Runtime Control Surface Implementation Plan

> **For Hermes:** User approved Phase 5K implementation on 2026-05-07 and reminded: use Codex when appropriate. This plan is the concrete design gate for the approved implementation. Keep the phase prototype-only/default-off. Do not touch production Gateway wiring, platform adapters, global tool registration, global config, base dependencies, Docker/daemon/service lifecycle, or remote branch deletion.

**Goal:** Add a narrow, versioned, prototype-only FlowWeaver runtime control surface that lets an Agent or local stdio MCP wrapper call the safe runtime facade through exact safe envelopes instead of ad-hoc shell/script calls.

**Phase position:** Phase 5J proved the local Temporal Workflow ↔ stub Activity / claim-check boundary. Phase 5K proves the Hermes/Agent ↔ Runtime control boundary. It does **not** connect production Gateway to Temporal.

**Baseline:**

```text
Timestamp: 2026-05-07 09:13:35 CST +0800
Repository: jovijovi/sachima
Base branch: origin/feature/sachima-channel
Base HEAD: ad170a22f
Phase 5K branch: feat/flowweaver-phase5k-runtime-control-surface
Phase 5K worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5k-runtime-control-surface
```

## Current Context

Existing Phase 5C already has:

- `FlowWeaverRuntimeClient` facade around a caller-supplied local Temporal client.
- `FlowWeaverRuntimeToolAdapter` dictionary adapter.
- `mcp_server.py` optional stdio MCP wrapper.
- Safe contracts for request/result/snapshot sanitization.

Existing Phase 5J added:

- Stub Activities: `validate_claim_check_ref`, `execute_agent_turn`, `deliver_artifact`.
- Activity payload/result validators.
- Safe `activity_boundary` snapshots.
- Real local Worker history no-leak coverage.

Therefore Phase 5K should **not** create a second runtime. It should harden and version the control surface above the existing facade.

## Design

Add a new prototype-only module:

```text
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/control_surface.py
```

Public control operations:

```text
start_transaction        -> runtime start_transaction
query_transaction        -> runtime query_snapshot
reconcile_delivery_ack   -> runtime record_delivery_ack
cancel_transaction       -> runtime cancel_transaction
```

Optional stdio wrapper:

```text
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/mcp_control_server.py
```

The wrapper exposes one tool only:

```text
flowweaver_runtime_control
```

It is local stdio only, import-safe, and default-off:

```text
AUTO_RUN_ON_IMPORT = False
server.run(transport="stdio") only inside explicit run_stdio_control_server/main
```

## Safe Envelope Rules

Control requests must be exact plain dictionaries.

### `start_transaction`

Required keys only:

```text
operation
workflow_id
start_payload
```

`start_payload` must pass existing `build_start_payload_from_safe_fields(...)`.

### `query_transaction`

Required keys only:

```text
operation
workflow_id
```

Maps internally to `query_snapshot`; public result keeps `operation=query_transaction` and records `runtime_operation=query_snapshot`.

### `reconcile_delivery_ack`

Required keys only:

```text
operation
workflow_id
update
```

`update` must pass existing `delivery_ack_from_tool_update(...)`.

### `cancel_transaction`

Required keys only:

```text
operation
workflow_id
update
```

`update` must pass existing `cancel_transaction_from_tool_update(...)`.

## Result Rules

Control results must be safe, bounded, and self-describing:

Allowed top-level fields:

```text
ok
operation
runtime_operation
workflow_id
transaction_id
status
snapshot
error_code
```

- `operation` is the public control operation.
- `runtime_operation` is the underlying existing runtime facade operation.
- `snapshot` is sanitized by existing Phase 5C sanitizers and may include safe Phase 5J `activity_boundary`.
- Error results use stable error codes only; no raw exception text.

## Out of Scope

- Production Gateway -> Temporal wiring.
- `gateway/platforms/**` changes.
- `gateway/run.py`, `run_agent.py`, `model_tools.py`, `toolsets.py`, `tools/**`, `hermes_cli/**` changes.
- Production Hermes tool registration.
- Global MCP registry/config writes.
- `~/.hermes/config.yaml` writes.
- Base dependency changes.
- Docker/systemctl/daemon/service startup.
- External Temporal service lifecycle.
- Payload-carrying Signals.
- Real LLM/tool/shell/filesystem/network/Gateway effects.

## TDD Plan

1. **RED: prototype contract tests**
   - Importing contracts/control surface does not import `temporalio`, `mcp`, workflow modules, or Gateway.
   - Closed-set public operation validation rejects unknown operations.
   - Exact-envelope sanitizer rejects extra safe-looking fields and unsafe raw/platform/secret-shaped fields.
   - Public aliases map to exact runtime operations.
   - Runtime errors become stable error codes without leaking exception text.
   - Fake runtime client works through the control surface.

2. **RED: MCP control wrapper tests**
   - Importing wrapper does not require MCP and does not auto-run.
   - `create_control_mcp_server(...)` exposes exactly `flowweaver_runtime_control` and no resources/prompts.
   - `run_stdio_control_server(...)` uses stdio only.
   - Source has no HTTP listener/config write/global registration markers.

3. **RED: local Temporal integration tests**
   - With a real local Temporal test Worker, control surface can start/query/reconcile ACK/cancel.
   - Duplicate start still maps safely.
   - Hostile control input is rejected before Temporal history can record it.
   - History JSON and serialized event bytes do not contain raw/platform/secret sentinels.

4. **GREEN: minimal implementation**
   - Add control contract helpers in `contracts.py` or a dedicated control module.
   - Add `FlowWeaverRuntimeControlSurface` and `invoke_flowweaver_runtime_control(...)`.
   - Add `mcp_control_server.py`.
   - Export version constants without importing optional dependencies.

5. **REFACTOR**
   - Reuse existing sanitizer/builders.
   - Keep exact operation mapping declarative.
   - Keep error/result translation small and auditable.

## Verification Plan

Focused Phase 5K tests:

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase5k_runtime_control_surface.py \
  tests/prototypes/test_flowweaver_phase5k_mcp_control_surface.py \
  -q

TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5k_runtime_control_surface.py \
  -q
```

Regression:

```bash
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5k_runtime_control_surface.py \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py \
  tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  -q

scripts/run_tests.sh \
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

Static/security:

```bash
python -m py_compile \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/control_surface.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/mcp_control_server.py \
  tests/prototypes/test_flowweaver_phase5k_runtime_control_surface.py \
  tests/prototypes/test_flowweaver_phase5k_mcp_control_surface.py \
  tests/integration/test_flowweaver_phase5k_runtime_control_surface.py

python -m ruff check \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/control_surface.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/mcp_control_server.py \
  tests/prototypes/test_flowweaver_phase5k_runtime_control_surface.py \
  tests/prototypes/test_flowweaver_phase5k_mcp_control_surface.py \
  tests/integration/test_flowweaver_phase5k_runtime_control_surface.py

git diff --check
```

Custom security gates:

- Changed-file allowlist.
- No production Gateway/tool/global config surface.
- No base dependency change.
- No payload-carrying Signals.
- No shell/network/filesystem/Gateway side effects in control modules.
- No raw exception text in returned results.
- No raw/platform/secret sentinels in tool-visible results or Temporal history.

## Acceptance Criteria

Phase 5K is complete only if:

1. A versioned local runtime control surface exists with exact safe envelopes.
2. Public operations map to existing runtime operations without exposing internal raw material.
3. Fake runtime and real local Temporal runtime both work through the control surface.
4. Optional stdio MCP control wrapper is import-safe, default-off, and exposes exactly one narrow tool.
5. Hostile raw/platform/secret input is rejected before Temporal history can record it.
6. Existing Phase 5B/5C/5H/5I/5J regressions stay green.
7. No production Gateway/tool/config/dependency/service lifecycle surfaces are touched.
8. Focused/regression/static/security gates and independent review pass before commit/PR.
