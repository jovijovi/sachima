# FlowWeaver Phase 8 Production Readiness Gate / Controlled Gateway Boundary Implementation Plan

> **For Hermes:** This document is the Phase 8 design gate. 狗哥 asked to start Phase 8 design on 2026-05-07. Do not implement behavior-bearing code until the design gate passes review and 狗哥 explicitly approves execution.

**Goal:** Convert the merged Phase 7 shadow E2E proof into a default-off production-readiness gate that can say whether a future controlled Gateway integration is safe to design, without enabling production Gateway wiring or real IM side effects.

**Architecture:** Add a prototype-only readiness module that consumes only already-sanitized Phase 7 loop results plus caller-supplied static boundary descriptors. It emits a safe go/no-go readiness report, a future-integration contract, and a checklist of separately approved production actions. It must not import Gateway runtime/platform adapters, start services, construct Temporal clients, write config, register tools, or send/edit/render real messages.

**Tech Stack:** Python, pytest, existing FlowWeaver Phase 5K control surface, Phase 6 ACK shadow bridge, Phase 7 Gateway shadow E2E loop, documentation gates. Optional Temporal remains an optional extra and is used only by existing regression tests, not by the Phase 8 module.

---

## Baseline

```text
Timestamp: 2026-05-07 12:51:58 CST +0800
Repository: jovijovi/sachima
Base branch: origin/feature/sachima-channel
Base HEAD: a5b68a43b4a8f5297077eeff7b5268ec149578d7
Phase 8 branch: feat/flowweaver-phase8-production-readiness-gate
Phase 8 worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase8-production-readiness-gate
GitHub open PRs at design start: none observed earlier in canonical status check
```

Current merged state:

- Phase 5 / Durable Runtime Foundation through 5K: **merged**.
- Phase 6 / Gateway ACK Shadow Bridge: **merged**.
- Phase 7 / Gateway Shadow E2E Loop: **merged** via PR #39.
- Production Gateway wiring: **not designed and not approved**.
- External `sachima-im-simulator` repo changes: **not in this Sachima phase**.

## Current Context

Phase 7 proves this local shadow-only loop:

```text
safe publication summary
  -> start_transaction
  -> bounded query_transaction
  -> sanitized shadow publication envelope
  -> simulated delivery ACK envelopes
  -> Phase 6 reconcile_shadow_gateway_ack()
  -> final query_transaction
```

The next risky leap would be real Gateway integration. Do **not** make that leap in Phase 8. Phase 8 should be a readiness gate that makes a later production design safer and less ambiguous.

Important existing files:

```text
gateway/flowweaver_shadow_publisher.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/control_surface.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/gateway_ack_shadow_bridge.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/gateway_shadow_e2e_loop.py
tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py
tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py
```

Known trap:

```text
scripts/run_tests.sh intentionally ignores tests/integration/**.
Do not use it as proof for integration tests.
```

## Phase 8 Positioning

Phase 8 is a **readiness and boundary phase**, not production activation.

It should answer:

1. Is the Phase 7 loop output safe enough to be considered a future Gateway integration candidate?
2. Are all required Gateway/runtime boundaries explicit, versioned, and fail-closed?
3. Does the proposed boundary forbid raw platform/card/media/tool/secret material before any future production side effect?
4. Are production actions clearly listed as separate approvals, not silently enabled by this code?
5. Can static and prototype tests detect accidental imports, lifecycle startup, registry writes, config writes, or send/edit/render calls?

It must **not** answer by starting the real Gateway, changing Feishu/Sachima adapters, writing production config, registering tools, or launching external services.

## Proposed Implementation Surface

Create a new prototype-only module:

```text
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/production_readiness_gate.py
```

Public constants:

```text
FLOWWEAVER_PRODUCTION_READINESS_GATE_VERSION = "flowweaver.production_readiness_gate.v0"
GATEWAY_BOUNDARY_DESCRIPTOR_TYPE = "flowweaver.gateway_boundary_descriptor.v0"
READINESS_REPORT_TYPE = "flowweaver.production_readiness_report.v0"
```

Primary entrypoint:

```text
def evaluate_flowweaver_production_readiness(
    *,
    phase7_result: object,
    gateway_boundary: object,
    runtime_boundary: object,
    operational_policy: object,
) -> dict[str, object]
```

This function is intentionally synchronous and pure. It must not accept factories, clients, addresses, task queues, callbacks, platform adapters, config paths, or secrets.

## Input Contracts

### `phase7_result`

Accept only the exact safe Phase 7 result shape already returned by `run_shadow_gateway_e2e_loop()`:

Required safe signals:

```text
ok = True
operation = gateway_shadow_e2e_loop
loop_version = flowweaver.gateway_shadow_e2e_loop.v0
start_status in started | running
publication.type = flowweaver.gateway_shadow_publication.v0
side_effects = []
checks.start_accepted = True
checks.initial_snapshot_safe = True
checks.publication_envelope_safe = True
checks.delivery_targets_initialized = True
checks.ack_count_matches_publication = True
checks.final_snapshot_safe = True
checks.side_effects_absent = True
```

Rejected examples:

```text
ok = False
missing checks
extra fields containing raw/card/platform/media/secret material
side_effects not empty
workflow_id != transaction_id
publication envelope not Phase 7 type
ack target not present in final snapshot.delivery_statuses
```

### `gateway_boundary`

Static caller-supplied descriptor only. No adapter objects.

Allowed fields only:

```text
type
mode
surfaces
ack_source
delivery_effects
adapter_imports_allowed
platform_payloads_allowed
raw_card_payloads_allowed
message_identifiers_allowed
side_effects
```

Allowed values:

```text
type = flowweaver.gateway_boundary_descriptor.v0
mode = shadow_only | controlled_shadow_candidate
delivery_effects = none
ack_source = phase6_shadow_bridge
adapter_imports_allowed = false
platform_payloads_allowed = false
raw_card_payloads_allowed = false
message_identifiers_allowed = false
side_effects = []
surfaces subset/order-preserving from final_text, rich_card, progress_card, media
```

Forbidden values:

```text
mode = production | live | enabled
send/edit/render/callback effect claims
chat_id/user_id/message_id/platform payloads
adapter class/module/object references
Feishu/Lark/Sachima webhook secrets
production URLs or connection strings
```

### `runtime_boundary`

Allowed fields only:

```text
type
control_surface
temporal_dependency
client_lifecycle
event_ingress
claim_check_policy
side_effects
```

Allowed values:

```text
type = flowweaver.runtime_boundary_descriptor.v0
control_surface = phase5k_control_surface
client_lifecycle = caller_supplied_only
temporal_dependency = optional_extra_only
event_ingress = validated_updates_only
claim_check_policy = refs_only
side_effects = []
```

Forbidden values:

```text
payload_carrying_signals
client_factory
connect_helper
Temporal address/task queue
Worker/WorkflowEnvironment ownership
Docker/daemon/service lifecycle
base dependency requirement
```

### `operational_policy`

Allowed fields only:

```text
type
default_state
production_actions_require_separate_approval
rollback_required
observability_required
config_write_allowed
registry_write_allowed
service_lifecycle_allowed
gateway_restart_allowed
side_effects
```

Allowed values:

```text
type = flowweaver.operational_policy.v0
default_state = off
production_actions_require_separate_approval = true
rollback_required = true
observability_required = true
config_write_allowed = false
registry_write_allowed = false
service_lifecycle_allowed = false
gateway_restart_allowed = false
side_effects = []
```

## Readiness Report Shape

Allowed top-level fields only:

```text
type
version
ok
verdict
phase
workflow_id
transaction_id
candidate_contract
checks
required_separate_approvals
runbook_outline
side_effects
error_code
```

Allowed verdicts:

```text
ready_for_controlled_shadow_design
blocked
not_applicable
```

`ready_for_controlled_shadow_design` does **not** mean production enabled. It only means the next design phase may propose a controlled shadow integration boundary.

`candidate_contract` allowed fields only:

```text
contract_version
runtime_operations
ack_bridge_version
shadow_loop_version
allowed_surfaces
forbidden_material
fail_closed_errors
rollback_hooks_required
```

`required_separate_approvals` must include these labels when the report is ready:

```text
production_gateway_wiring
production_config_write
gateway_restart
external_temporal_service
real_send_edit_render_callback
production_tool_registry
remote_branch_or_worktree_cleanup
```

## Stable Error Codes

```text
invalid_phase7_result
invalid_gateway_boundary
invalid_runtime_boundary
invalid_operational_policy
unsafe_material
side_effects_not_absent
production_action_requested
workflow_id_mismatch
delivery_target_mismatch
not_shadow_only
runtime_lifecycle_requested
registry_or_config_write_requested
```

Errors must return stable codes only. Never echo offending values, raw exception text, platform IDs, URLs, prompts, tool outputs, card JSON, media paths, credentials, or connection strings.

## Out of Scope

```text
Production Gateway/Feishu/Sachima integration
gateway/run.py behavior changes
gateway/platforms/** changes
run_agent.py changes
model_tools.py changes
toolsets.py changes
tools/** changes
hermes_cli/** changes
production Hermes tool registration
real send/edit/render/callback effects
platform adapter imports or adapter object references
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

## Step-by-step Plan

### Task 1: RED import/API/default-off contract

**Objective:** Define the Phase 8 module as pure, prototype-only, and import-safe.

**Files:**

- Create test: `tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py`
- Future implementation: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/production_readiness_gate.py`

**Test requirements:**

- Import fails before implementation because module does not exist.
- After implementation, importing the module must not import:
  - `gateway.run`
  - `gateway.platforms.*`
  - `temporalio`
  - `mcp`
  - `tools.registry`
  - `hermes_cli.platforms`
  - `toolsets`
- Public API exposes only constants plus `evaluate_flowweaver_production_readiness`.
- No factories, clients, addresses, task queues, callbacks, adapter objects, or lifecycle helpers appear in the public signature.

**RED command:**

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py -q
```

Expected RED: missing module/API only, not syntax or fixture failure.

### Task 2: RED happy-path readiness report from safe Phase 7 result

**Objective:** Prove a safe Phase 7 result plus strict shadow-only descriptors yields `ready_for_controlled_shadow_design`.

**Files:**

- Modify test: `tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py`

**Test requirements:**

- Build a minimal exact Phase 7 result fixture using current Phase 7 result shape.
- Build exact `gateway_boundary`, `runtime_boundary`, and `operational_policy` fixtures.
- Assert output:
  - `ok is True`
  - `type == flowweaver.production_readiness_report.v0`
  - `verdict == ready_for_controlled_shadow_design`
  - `side_effects == []`
  - required separate approvals list contains every production action label.
  - `candidate_contract.runtime_operations == [start_transaction, query_transaction, reconcile_delivery_ack]`
  - `candidate_contract.ack_bridge_version` references Phase 6.
  - `candidate_contract.shadow_loop_version` references Phase 7.
- Assert the report never contains `production_enabled`, `live_enabled`, or equivalent activation language.

### Task 3: RED Phase 7 result validation and delivery target parity

**Objective:** Ensure the readiness gate trusts only the proven Phase 7 artifact, not arbitrary green-looking data.

**Files:**

- Modify test: `tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py`

**Test requirements:**

- Reject `phase7_result.ok = False` with `invalid_phase7_result`.
- Reject missing or false required checks.
- Reject `side_effects != []` with `side_effects_not_absent`.
- Reject `workflow_id != transaction_id` with `workflow_id_mismatch`.
- Reject publication/ACK targets that are not present in `final_snapshot.delivery_statuses` with `delivery_target_mismatch`.
- Reject unknown top-level fields or nested fields in Phase 7 result.

### Task 4: RED boundary descriptors reject production/lifecycle intent

**Objective:** Fail closed if a caller tries to smuggle production activation or runtime lifecycle into a readiness report.

**Files:**

- Modify test: `tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py`

**Test requirements:**

Reject with stable codes before building a candidate contract when any descriptor requests:

```text
mode = production/live/enabled
send/edit/render/callback side effects
adapter imports or adapter object references
platform payloads/raw card payloads/message IDs
Temporal connect helper/address/task queue/client factory
Worker/WorkflowEnvironment/test server ownership
payload-carrying Signals
config writes or registry writes
Gateway restart
Docker/subprocess/systemctl/service/daemon lifecycle
base dependency changes
```

### Task 5: RED hostile material and safe-output gates

**Objective:** Prove no raw IDs, card/media payloads, prompts, tool output, exception text, or secret-shaped material can appear in inputs or outputs.

**Files:**

- Modify test: `tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py`

**Test requirements:**

- Reject keys containing raw/platform/card/media/credential markers.
- Reject values containing platform/private ID prefixes, credential-shaped markers, raw exception text sentinels, URLs with query credentials, or connection-string-shaped material.
- Result contains only stable codes and allowed fields.
- Monkeypatch a descriptor object with hostile mapping behavior if feasible; unsafe non-plain mappings must be rejected.
- Add safe-output assertion that recursively scans returned reports for forbidden markers.

### Task 6: GREEN implementation

**Objective:** Implement the minimal pure readiness evaluator.

**Files:**

- Create: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/production_readiness_gate.py`

**Implementation constraints:**

- Pure Python, no IO.
- No `asyncio`, no background tasks, no subprocesses, no sockets, no HTTP servers.
- No Gateway/platform/tool/config imports.
- No Temporal imports or client construction.
- No `importlib`, `__import__`, dynamic adapter lookup, `getattr(..., "connect")`, or hidden lifecycle helpers.
- Use exact key sets, closed enums, explicit validators, stable error codes.
- Return only safe reports; never log or return raw exception text/offending values.

### Task 7: Documentation runbook outline

**Objective:** Preserve the production-readiness boundary for future humans before anyone asks to wire production.

**Files:**

- Create or modify after approval: `docs/runbooks/flowweaver-production-readiness.md`
- Modify: `docs/dev_log/2026-05-07-flowweaver-phase8-production-readiness-gate.md`

Runbook must include:

- What Phase 8 proves.
- What Phase 8 explicitly does not enable.
- Required separate approvals.
- Future controlled-shadow design prerequisites.
- Rollback requirements.
- No-secrets/no-raw-payload rule.
- Correct integration pytest command warning.

### Task 8: Regression, static gates, and independent review

**Objective:** Verify Phase 8 plus prior FlowWeaver phases remain safe.

Focused prototype:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py -q
```

Regression prototype:

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

Regression integration, using direct pytest only:

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
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/production_readiness_gate.py \
  tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py

python -m ruff check \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/production_readiness_gate.py \
  tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py

git diff --check
```

Custom gates:

- Changed-file allowlist covers committed, staged, unstaged, intent-to-add, and untracked files.
- No production Gateway/platform/tool/global config/dependency/service lifecycle surface.
- No `gateway/platforms/**`, `gateway/run.py`, `run_agent.py`, `model_tools.py`, `toolsets.py`, `tools/**`, `hermes_cli/**`, or external simulator repo changes unless a later approved task explicitly changes docs/runbooks only.
- No platform adapter imports, send/edit/render/callback calls, sockets, HTTP listeners, Docker/systemctl/subprocess lifecycle, global registry writes, config writes, Temporal client/Worker construction, or payload-carrying Signals.
- No raw exception interpolation in returned results/logs.
- No raw/platform/card/media/secret sentinels in readiness reports, fixtures, or docs evidence.

Codex gates:

1. Fresh-context design review before implementation: `PASS` or `BLOCK` with concrete blockers.
2. If design blockers appear, patch this plan/dev log and run blocker-only Codex re-review.
3. After implementation, independent Codex implementation review: `PASS` or `BLOCK` with concrete blockers.
4. Any implementation blocker must first get a focused RED regression test before code fix.

## Acceptance Criteria

Phase 8 design is ready for 狗哥 approval only if:

1. The design keeps Phase 8 default-off, prototype-only, and side-effect-free.
2. The proposed module is pure and cannot construct Gateway, Temporal, MCP, tool registry, config, or service lifecycle objects.
3. The readiness report can say `ready_for_controlled_shadow_design` but cannot enable production.
4. All production actions are listed as separate approvals.
5. Raw platform/card/media/tool/prompt/secret material is rejected at input and absent from output.
6. Gateway delivery targets remain tied to Phase 7 final snapshots; no invented ACK slots.
7. Existing Phase 5/6/7 regression suites remain part of the gate.
8. Codex design review has no blockers.
9. Final document gates are rerun after any review/evidence append.

Phase 8 implementation is complete only if the future approved implementation satisfies every task above and opens a PR. Until then, this plan is **not** approval to write behavior code.
