# FlowWeaver Phase 6 Gateway ACK Shadow Bridge Implementation Plan

> **For Hermes:** 狗哥 approved continuing into Phase 6 on 2026-05-07 and reminded: slow work produces quality; use Codex when appropriate. This plan is the concrete design gate. Keep Phase 6 shadow/simulator-only, prototype-only, default-off, and production-zero.

**Goal:** Prove that Gateway-like delivery ACK events can be converted into safe FlowWeaver runtime reconciliation calls without leaking raw platform payloads or touching production Gateway wiring.

**Phase position:** Phase 5 is closed as **Durable Runtime Foundation**. Phase 5J proved Workflow ↔ stub Activity / claim-check safety. Phase 5K proved Agent/MCP ↔ runtime control-surface safety. Phase 6 proves the next outer boundary: shadow Gateway delivery ACK ↔ runtime reconciliation.

**Baseline:**

```text
Timestamp: 2026-05-07 10:26:13 CST +0800
Repository: jovijovi/sachima
Base branch: origin/feature/sachima-channel
Base HEAD: 1bbb134d6
Phase 6 branch: feat/flowweaver-phase6-gateway-ack-shadow-bridge
Phase 6 worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase6-gateway-ack-shadow-bridge
```

## Current Context

Existing Phase 5K provides:

- `FlowWeaverRuntimeControlSurface` in `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/control_surface.py`.
- Public operation `reconcile_delivery_ack` mapped to runtime `record_delivery_ack`.
- Safe exact envelopes and identity binding: `workflow_id == start_payload.transaction_id`.
- Fake-runtime and real local Temporal parity tests.

Existing Phase 5B/5C runtime behavior provides:

- Runtime snapshots with initialized `delivery_statuses`, such as `runtime_delivery_0`.
- Validated Updates for `record_delivery_ack`.
- Workflow validator rejecting ACK targets not present in initialized delivery slots.
- Idempotent ACK replay behavior through duplicate `delivery_key` / event-key semantics.

Phase 6 should not create a production Gateway adapter. It should add a narrow **shadow bridge** that accepts only sanitized Gateway-like ACK envelopes, preflights against a sanitized runtime snapshot, and then calls the Phase 5K control surface.

## Design

Add a prototype-only module:

```text
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/gateway_ack_shadow_bridge.py
```

Public version constant:

```text
FLOWWEAVER_GATEWAY_ACK_SHADOW_BRIDGE_VERSION = "flowweaver.gateway_ack_shadow_bridge.v0"
```

Primary entrypoint:

```text
reconcile_shadow_gateway_ack(control_surface, ack_envelope) -> dict[str, object]
```

The entrypoint must:

1. Validate `ack_envelope` is an exact plain dictionary.
2. Validate safe synthetic IDs and closed enums before querying/calling runtime.
3. Query the Phase 5K control surface using `query_transaction`.
4. Validate the returned snapshot is safe and belongs to the same `workflow_id`.
5. Validate `ack_envelope.target_id` exists in `snapshot.delivery_statuses`.
6. Build a Phase 5K `reconcile_delivery_ack` control request.
7. Return only stable, sanitized bridge results.

### Safe ACK envelope

Required keys only:

```text
type
workflow_id
delivery_key
surface
target_kind
target_id
status
```

Allowed values:

```text
type = flowweaver.gateway_ack_shadow.v0
workflow_id = runtime_tx_*
delivery_key = runtime_event_*
surface = final_text | rich_card | media | progress_card
target_kind = delivery
target_id = runtime_delivery_*
status = sent | failed | acknowledged
```

Notes:

- `skipped` is **not** a Phase 6 ACK status. If a future publication policy wants to represent skipped delivery, it must remain bridge-local and must never be forwarded to Phase 5K/Temporal as a `record_delivery_ack` status unless a later phase explicitly adds and tests that mapping.
- The bridge may use the same delivery ACK dataclass builder already used by Phase 5K after the envelope is reduced to the runtime update shape.
- The bridge must not accept platform-specific names such as `chat_id`, `message_id`, `card_json`, `platform_payload`, `media_path`, or raw callback payloads.
- The bridge must not log or return raw exception text.

### Result shape

Allowed top-level fields:

```text
ok
bridge_version
operation
runtime_operation
workflow_id
target_id
status
snapshot
error_code
```

Rules:

- `operation` is always `gateway_ack_shadow_bridge`.
- `runtime_operation` is `record_delivery_ack` when reconciliation is attempted.
- Error results use stable safe error codes only.
- Because bridge-specific error codes are outside Phase 5K `make_error_result()` today, Phase 6 must use a bridge-local result sanitizer unless the shared safe-error allowlist is deliberately extended with tests.
- Successful results may include the sanitized runtime snapshot returned by Phase 5K.

### Stable error codes

```text
unsafe_ack_envelope
snapshot_unavailable
workflow_id_mismatch
delivery_target_mismatch
runtime_reconciliation_failed
runtime_error
```

## Out of Scope

```text
gateway/run.py changes
gateway/platforms/** changes
run_agent.py changes
model_tools.py changes
toolsets.py changes
tools/** changes
hermes_cli/** changes
production Hermes tool registration
production Gateway -> Temporal wiring
real Feishu/Slack/Telegram/etc. send/edit/render/callback effects
platform adapter imports
raw platform payload ingestion
card JSON/media path ingestion
Docker / Temporal CLI / daemon / service startup
global MCP registry/config writes
~/.hermes/config.yaml writes
base dependency changes
payload-carrying Signals
remote branch deletion
Gateway restart
```

## TDD Plan

### 1. RED: prototype bridge contract tests

Create:

```text
tests/prototypes/test_flowweaver_phase6_gateway_ack_shadow_bridge.py
```

Cover:

- Importing the module does not import `gateway`, platform adapters, `temporalio`, `mcp`, or workflow modules.
- The bridge exposes the exact version constant and narrow public API.
- A safe ACK envelope queries the control surface first, then calls `reconcile_delivery_ack` with a sanitized runtime update.
- ACK target must exist in the queried snapshot `delivery_statuses` before runtime reconciliation is attempted.
- Repeating the same ACK returns safe duplicate/no-op semantics from the runtime without extra raw data.
- Extra fields and raw/platform/secret-shaped material are rejected before runtime calls.
- Runtime exceptions return stable error codes without raw exception text.

Expected RED before implementation:

```text
ModuleNotFoundError: flowweaver_runtime_client.gateway_ack_shadow_bridge
```

### 2. RED: local Temporal integration parity tests

Create:

```text
tests/integration/test_flowweaver_phase6_gateway_ack_shadow_bridge.py
```

Cover with real local Temporal test Worker only inside pytest:

- Start a transaction through Phase 5K control surface.
- Wait for sanitized running snapshot / activity boundary when needed.
- Reconcile a safe shadow ACK through Phase 6 bridge.
- Reconcile the same ACK again and assert duplicate/no-op semantics.
- Try an ACK for `runtime_delivery_1` when only `runtime_delivery_0` exists; assert safe `delivery_target_mismatch`, assert no `reconcile_delivery_ack` runtime/control call is made, and assert no invented delivery slot appears.
- Confirm snapshots and history JSON/serialized event bytes contain no raw/platform/secret sentinels.

### 3. GREEN: minimal implementation

Use Codex for the first GREEN implementation if RED tests are correct and specific. Prompt Codex with:

- This plan.
- Phase 5K control-surface contract.
- Strict TDD rule: do not broaden scope beyond failing tests.
- No production Gateway/platform imports or side effects.
- Do not use `notify_on_complete` in Hermes background mode.

Hermes must then verify Codex output manually:

- Review diff.
- Confirm no production surfaces touched.
- Rerun focused tests from Hermes terminal.
- Treat Codex Temporal sandbox failures as inconclusive until Hermes reruns them.

### 4. REFACTOR

Keep refactor small:

- Reuse existing validators/builders where safe.
- Keep bridge result sanitizer auditable.
- Keep preflight query separate from runtime reconciliation.
- Preserve single-call vs replay semantics.

## Verification Plan

Baseline already verified before Phase 6 changes:

```text
Prototype baseline: 104 passed in 0.81s
Integration baseline: 34 passed in 1.63s
```

Focused Phase 6 tests:

Use `scripts/run_tests.sh` for prototype/non-integration tests. Do **not** use it for `tests/integration/**`: the current script passes `--ignore=tests/integration` and `-m "not integration"`, so integration tests require the explicit hermetic pytest command below.

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase6_gateway_ack_shadow_bridge.py \
  -q

TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase6_gateway_ack_shadow_bridge.py \
  -q
```

Regression:

Again, use direct hermetic pytest for integration because `scripts/run_tests.sh` intentionally ignores `tests/integration/**`.

```bash
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase6_gateway_ack_shadow_bridge.py \
  tests/integration/test_flowweaver_phase5k_runtime_control_surface.py \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py \
  tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  -q

scripts/run_tests.sh \
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

Static/security:

```bash
python -m py_compile \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/gateway_ack_shadow_bridge.py \
  tests/prototypes/test_flowweaver_phase6_gateway_ack_shadow_bridge.py \
  tests/integration/test_flowweaver_phase6_gateway_ack_shadow_bridge.py

python -m ruff check \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/gateway_ack_shadow_bridge.py \
  tests/prototypes/test_flowweaver_phase6_gateway_ack_shadow_bridge.py \
  tests/integration/test_flowweaver_phase6_gateway_ack_shadow_bridge.py

git diff --check
```

Custom gates:

- Changed-file allowlist covers committed, staged, unstaged, and untracked files.
- No production Gateway/tool/global config/dependency/service lifecycle surface.
- No platform adapter imports, SDK calls, send/edit/render/callback methods, HTTP listeners, socket servers, Docker/systemctl/subprocess lifecycle, or registry writes.
- No payload-carrying Signals.
- No raw exception interpolation in returned results/logs.
- No raw/platform/secret sentinels in bridge results, runtime snapshots, Temporal history JSON, or serialized event bytes.

## Acceptance Criteria

Phase 6 is complete only if:

1. A versioned shadow Gateway ACK bridge exists and is import-safe/default-off.
2. The bridge only accepts exact safe ACK envelopes.
3. The bridge preflights target delivery slots from sanitized runtime snapshots before reconciliation.
4. Missing/mismatched targets are rejected safely and do not create runtime delivery slots.
5. Duplicate ACK behavior is idempotent and safe.
6. Fake/prototype and real local Temporal paths have compatible safe result shapes.
7. Existing Phase 5B/5C/5H/5I/5J/5K regressions remain green.
8. No production Gateway/platform/tool/config/dependency/service lifecycle surfaces are touched.
9. Codex independent review has no blockers, and final gates pass after any dev-log/doc updates.
