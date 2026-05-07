# FlowWeaver Production Readiness Runbook

## Status

This runbook documents the Phase 8 readiness boundary for FlowWeaver（流织）. It is not a production activation guide.

Current approved scope:

```text
Phase 8 = prototype-only readiness gate
Default state = off
Production side effects = none
```

## What Phase 8 Proves

Phase 8 evaluates only sanitized artifacts from the already-merged Phase 7 shadow loop plus caller-supplied static boundary descriptors.

A passing Phase 8 report means only:

```text
ready_for_controlled_shadow_design
```

That verdict means a future phase may design a controlled shadow integration boundary. It does **not** mean production is enabled, production-ready, or safe to launch.

## What Phase 8 Does Not Enable

Phase 8 does not enable or perform:

```text
production Gateway wiring
real Feishu/Sachima send/edit/render/callback effects
Gateway restart
Docker / daemon / service startup
external Temporal service lifecycle
production config writes
production tool registry writes
raw platform payload ingestion
raw card/media payload ingestion
payload-carrying Temporal Signals
```

The Phase 8 evaluator must stay pure and lifecycle-free. It must not construct clients, factories, task queues, adapters, workers, sockets, subprocesses, or config writers.

## Required Separate Approvals

A Phase 8 report must list these as separate approvals before any later production-facing work:

```text
production_gateway_wiring
production_config_write
gateway_restart
external_temporal_service
real_send_edit_render_callback
production_tool_registry
remote_branch_or_worktree_cleanup
```

None of those actions are approved by this runbook or by a passing Phase 8 result.

## Future Controlled-Shadow Design Prerequisites

Before proposing a later controlled-shadow Gateway integration, verify:

1. Phase 5/6/7 regressions are still green.
2. Phase 8 readiness evaluator returns `ready_for_controlled_shadow_design` for a current sanitized Phase 7 result.
3. The proposed integration remains default-off and fail-closed.
4. Gateway/runtime boundaries do not carry raw prompts, tool output, card JSON, media bytes/paths, platform payloads, message IDs, user IDs, chat IDs, credentials, or connection strings.
5. External events remain validated Updates only; payload-carrying Signals stay forbidden.
6. Rollback plan exists before any production config or Gateway behavior change.

## Rollback Requirements

Any future production-facing PR must include a rollback path before merge:

```text
config disable path
safe fallback behavior
operator-visible failure code
no raw exception/user/platform payload leakage
no partial enablement that requires Gateway restart to recover
```

If rollback cannot be described in stable safe terms, the production-facing phase is not ready.

## No-Secrets / No-Raw-Payload Rule

Never place these in readiness reports, logs, docs evidence, Temporal history, or IM-visible artifacts:

```text
credentials or tokens
connection strings
raw prompt text
raw tool output
raw card JSON
raw media bytes or media paths
raw platform payloads
platform chat/user/message identifiers
raw exception text
```

Use safe refs, counts, digests, statuses, and stable error codes only.

## Verification Commands

Focused Phase 8 prototype gate:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py -q
```

Prototype regression gate:

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py \
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

Integration regression warning:

```text
scripts/run_tests.sh intentionally ignores tests/integration/**.
```

Use direct hermetic pytest for integration regression:

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
