# FlowWeaver Phase 9 Controlled Shadow Design Gate Implementation Plan

> **For Hermes:** This document is the Phase 9 design gate. 狗哥 asked to start Phase 9 design on 2026-05-07 after Phase 8 PR #40 was verified merged, the local canonical repo was synchronized, and the Gateway restart was separately completed and verified as historical context only. Phase 9 itself must not require or perform a Gateway restart. Do not implement behavior-bearing code until the design gate passes review and 狗哥 explicitly approves execution.

**Goal:** Convert the merged Phase 8 readiness report into a safe, default-off controlled-shadow design contract that can describe how a future prototype shadow run may observe sanitized Gateway/runtime boundaries without enabling production Gateway wiring or real IM side effects.

**Architecture:** Add a prototype-only controlled-shadow design layer that consumes an exact Phase 8 readiness report plus caller-supplied static control descriptors. It emits a safe controlled-shadow plan, artifact policy, approval checklist, and verification matrix. The future implementation must stay pure, synchronous, import-safe, lifecycle-free, and side-effect-free; it must not import Gateway platform adapters, construct Temporal clients or Workers, write config, register tools, restart services, or send/edit/render/callback real messages.

**Tech Stack:** Python, pytest, existing FlowWeaver Phase 5K control surface, Phase 6 ACK shadow bridge, Phase 7 shadow E2E loop, Phase 8 production-readiness gate, documentation gates. Optional Temporal remains an optional extra and is not introduced into base dependencies or owned by this phase.

---

## Baseline

```text
Timestamp: 2026-05-07 14:19:25 CST +0800
Repository: jovijovi/sachima
Base branch: origin/feature/sachima-channel
Base HEAD: affca9fea65fd5c7de2c6985be6fc9510c13e879
Phase 9 branch: feat/flowweaver-phase9-controlled-shadow-design
Phase 9 worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase9-controlled-shadow-design
```

Current merged state:

- Phase 5 / Durable Runtime Foundation through 5K: **merged**.
- Phase 6 / Gateway ACK Shadow Bridge: **merged**.
- Phase 7 / Gateway Shadow E2E Loop: **merged** via PR #39.
- Phase 8 / Production Readiness Gate: **merged** via PR #40.
- Production Gateway wiring: **not designed and not approved**.
- External `sachima-im-simulator` repo changes: **not in this Sachima phase**.

## Current Context

Phase 8 proves this gate:

```text
safe Phase 7 result
  + gateway boundary descriptor
  + runtime boundary descriptor
  + operational policy
  -> readiness report with verdict ready_for_controlled_shadow_design
  -> candidate contract
  -> required separate approvals
```

The Phase 8 report deliberately does **not** mean production is enabled, production-ready, or safe to launch. It only allows a next design phase to define a controlled-shadow boundary.

Phase 9 should answer:

1. What exact sanitized Phase 8 report shape may feed a controlled-shadow plan?
2. What static descriptors define a controlled-shadow scope without real Gateway side effects?
3. What artifact and observability outputs are allowed, and what raw material remains forbidden?
4. What approval, rollback, kill-switch, and verification conditions must exist before any later shadow prototype run?
5. What file surfaces can a future Phase 9 implementation touch without slipping into production Gateway wiring?

Phase 9 should **not** answer by changing production Gateway behavior.

## Definition: Controlled Shadow

Controlled shadow means a future prototype can evaluate a sanitized, bounded imitation of Gateway/runtime behavior while the existing Gateway remains the only production path.

Allowed meaning:

```text
sanitized input/ref fixtures or already-safe Phase 7/8 artifacts
  -> prototype-only control contract
  -> safe controlled-shadow plan
  -> safe artifact/observability policy
  -> no real platform delivery effects
```

Forbidden meaning:

```text
turn on production Gateway integration
send/edit/render/callback real IM messages
consume raw platform payloads, raw cards, raw media, raw prompts, or raw tool output
write production config or tool registry
construct runtime clients, Workers, daemons, sockets, or service lifecycle
```

In plain language: Phase 9 designs the rehearsal rules. It does not put FlowWeaver on stage.

## Proposed Implementation Surface After Design Approval

Create a new prototype-only module in a later implementation PR:

```text
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_shadow_design.py
```

Create focused tests:

```text
tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py
```

Create or update runbook:

```text
docs/runbooks/flowweaver-controlled-shadow.md
```

Update only phase-specific integration changed-file allowlists if implementation adds the files above and existing guards require it. Do not weaken forbidden-surface rules.

## Public Constants

```text
FLOWWEAVER_CONTROLLED_SHADOW_DESIGN_VERSION = "flowweaver.controlled_shadow_design.v0"
CONTROLLED_SHADOW_SCOPE_DESCRIPTOR_TYPE = "flowweaver.controlled_shadow_scope.v0"
GATEWAY_OBSERVATION_BOUNDARY_TYPE = "flowweaver.gateway_observation_boundary.v0"
RUNTIME_EXECUTION_BOUNDARY_TYPE = "flowweaver.runtime_execution_boundary.v0"
CONTROLLED_SHADOW_ARTIFACT_POLICY_TYPE = "flowweaver.controlled_shadow_artifact_policy.v0"
CONTROLLED_SHADOW_ROLLBACK_POLICY_TYPE = "flowweaver.controlled_shadow_rollback_policy.v0"
CONTROLLED_SHADOW_PLAN_TYPE = "flowweaver.controlled_shadow_plan.v0"
```

## Primary Entrypoint

```text
def build_flowweaver_controlled_shadow_plan(
    *,
    readiness_report: object,
    shadow_scope: object,
    gateway_observation_boundary: object,
    runtime_execution_boundary: object,
    artifact_policy: object,
    rollback_policy: object,
) -> dict[str, object]
```

This function must be synchronous and pure. It must not accept or construct clients, factories, addresses, task queues, callbacks, platform adapters, config paths, sockets, subprocesses, secrets, or live runtime handles.

## Input Contracts

### `readiness_report`

Accept only an exact safe Phase 8 success report matching the merged `production_readiness_gate.py` output shape.

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
```

Required top-level signals:

```text
type = flowweaver.production_readiness_report.v0
version = flowweaver.production_readiness_gate.v0
ok = True
verdict = ready_for_controlled_shadow_design
phase = phase8_production_readiness_gate
workflow_id starts with runtime_tx_
transaction_id starts with runtime_tx_
workflow_id = transaction_id
side_effects = []
```

Allowed `candidate_contract` fields only:

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

Required `candidate_contract` signals:

```text
contract_version = flowweaver.controlled_shadow_candidate.v0
runtime_operations = [start_transaction, query_transaction, reconcile_delivery_ack]
ack_bridge_version = flowweaver.gateway_ack_shadow_bridge.v0
shadow_loop_version = flowweaver.gateway_shadow_e2e_loop.v0
allowed_surfaces subset/order-preserving from final_text, rich_card, progress_card, media
forbidden_material includes raw_prompt, raw_tool_output, raw_card_json, raw_media_payload, raw_platform_payload, platform_message_identifiers, credentials_or_connection_strings
fail_closed_errors contains only stable Phase 8 error codes
rollback_hooks_required = True
```

Required `checks` signals:

```text
phase7_result_safe = True
gateway_boundary_shadow_only = True
runtime_boundary_lifecycle_free = True
operational_policy_default_off = True
delivery_targets_match_snapshot = True
production_actions_separate = True
side_effects_absent = True
```

Required `required_separate_approvals` exact set:

```text
production_gateway_wiring
production_config_write
gateway_restart
external_temporal_service
real_send_edit_render_callback
production_tool_registry
remote_branch_or_worktree_cleanup
```

`runbook_outline` must be a non-empty list of safe stable labels from Phase 8, not raw text or operator secrets.

The Phase 9 implementation must reject:

```text
blocked reports
missing candidate_contract
unknown report fields
production activation verdicts or enablement strings
raw/card/media/platform/prompt/tool/secret material
workflow_id != transaction_id
missing required separate approvals
```

### `shadow_scope`

Static descriptor only. No live platform IDs and no user cohort IDs.

Allowed fields only:

```text
type
mode
source_kind
max_transactions
max_delivery_surfaces
allowed_surfaces
operator_approval_ref
feature_flag_ref
side_effects
```

Allowed values:

```text
type = flowweaver.controlled_shadow_scope.v0
mode = design_only | prototype_shadow_candidate
source_kind = phase7_result_replay | phase8_readiness_replay | simulator_fixture
max_transactions = integer from 1 through 20
max_delivery_surfaces = integer from 0 through 20
allowed_surfaces subset/order-preserving from final_text, rich_card, progress_card, media
operator_approval_ref starts with approval_ref_
feature_flag_ref starts with feature_flag_ref_
side_effects = []
```

Rejected examples:

```text
mode = production | live | enabled
source_kind = live_gateway_stream | real_feishu | real_sachima
chat_id / user_id / message_id / platform identifiers
webhook URLs, callback URLs, connection strings, credentials
feature flag names that imply config writes or current production enablement
```

### `gateway_observation_boundary`

Static descriptor for observation only. It is not an adapter or transport.

Allowed fields only:

```text
type
observation_mode
inbound_material
outbound_effects
adapter_imports_allowed
platform_payloads_allowed
message_identifiers_allowed
ack_source
side_effects
```

Allowed values:

```text
type = flowweaver.gateway_observation_boundary.v0
observation_mode = sanitized_replay_only | simulator_fixture_only
inbound_material = sanitized_refs_only
outbound_effects = none
adapter_imports_allowed = false
platform_payloads_allowed = false
message_identifiers_allowed = false
ack_source = phase6_shadow_bridge | simulator_ack_fixture
side_effects = []
```

Forbidden values:

```text
observe_live_gateway
mirror_live_gateway
send/edit/render/callback effects
Gateway adapter classes or modules
Feishu/Lark/Sachima raw payloads
raw card JSON or media bytes/paths
real platform message identifiers
```

### `runtime_execution_boundary`

Allowed fields only:

```text
type
control_surface
client_lifecycle
temporal_dependency
event_ingress
allowed_operations
worker_lifecycle
side_effects
```

Allowed values:

```text
type = flowweaver.runtime_execution_boundary.v0
control_surface = phase5k_control_surface
client_lifecycle = caller_supplied_only
temporal_dependency = optional_extra_only
event_ingress = validated_updates_only
allowed_operations subset/order-preserving from start_transaction, query_transaction, reconcile_delivery_ack
worker_lifecycle = none
side_effects = []
```

Forbidden values:

```text
payload-carrying Temporal Signals
client_factory
connect_helper
Temporal address/task queue
Worker ownership
WorkflowEnvironment ownership
Docker / daemon / service lifecycle
base dependency requirement
```

### `artifact_policy`

Allowed fields only:

```text
type
artifact_mode
allowed_fields
forbidden_material
retention
log_policy
side_effects
```

Allowed values:

```text
type = flowweaver.controlled_shadow_artifact_policy.v0
artifact_mode = safe_summary_only
allowed_fields subset/order-preserving from run_id, transaction_id, operation_counts, delivery_counts, statuses, digests, stable_error_codes, approvals, side_effects
forbidden_material includes raw_prompt, raw_tool_output, raw_card_json, raw_media_payload, raw_platform_payload, platform_message_identifiers, credentials_or_connection_strings, raw_exception_text
retention = local_artifact_only | docs_evidence_only
log_policy = sanitized_codes_only
side_effects = []
```

The implementation must never include raw values in reports, logs, docs evidence, or test fixtures.

### `rollback_policy`

Allowed fields only:

```text
type
default_state
kill_switch_required
rollback_plan_required
production_actions_require_separate_approval
config_write_allowed
registry_write_allowed
gateway_restart_allowed
service_lifecycle_allowed
side_effects
```

Allowed values:

```text
type = flowweaver.controlled_shadow_rollback_policy.v0
default_state = off
kill_switch_required = true
rollback_plan_required = true
production_actions_require_separate_approval = true
config_write_allowed = false
registry_write_allowed = false
gateway_restart_allowed = false
service_lifecycle_allowed = false
side_effects = []
```

## Output Contract

Allowed top-level fields only:

```text
type
version
ok
verdict
phase
workflow_id
transaction_id
controlled_shadow_plan
checks
artifact_policy
required_separate_approvals
verification_matrix
runbook_outline
side_effects
error_code
```

Allowed verdicts:

```text
ready_for_controlled_shadow_prototype
blocked
not_applicable
```

`ready_for_controlled_shadow_prototype` means only that a future prototype can be implemented and tested under this static design contract. It must not mean production is enabled, production-ready, or safe to launch.

`controlled_shadow_plan` allowed fields only:

```text
plan_version
source_kind
mode
allowed_surfaces
max_transactions
max_delivery_surfaces
runtime_operations
ack_source
artifact_mode
approval_refs
rollback_hooks_required
kill_switch_required
forbidden_material
fail_closed_errors
```

`verification_matrix` allowed entries:

```text
phase8_report_exact_shape
scope_default_off
gateway_observation_only
runtime_lifecycle_free
validated_updates_only
artifact_safe_summary_only
rollback_and_kill_switch_present
production_actions_separate
side_effects_absent
```

Stable error codes:

```text
invalid_readiness_report
invalid_shadow_scope
invalid_gateway_observation_boundary
invalid_runtime_execution_boundary
invalid_artifact_policy
invalid_rollback_policy
unsafe_material
side_effects_not_absent
production_action_requested
workflow_id_mismatch
runtime_lifecycle_requested
registry_or_config_write_requested
artifact_policy_violation
```

Errors must return stable codes only. Never echo offending values, raw exception text, platform IDs, URLs, prompts, tool outputs, card JSON, media paths, credentials, or connection strings.

## Hard Boundary Markers

These exact markers are intentional so document gates can mechanically detect the Phase 9 safety boundary:

```text
No production Gateway/Feishu/Sachima integration.
No gateway/run.py or gateway/platforms/** behavior changes.
No Temporal client/Worker construction inside the future Phase 9 module.
No payload-carrying Temporal Signals.
All production actions require separate approval.
No raw platform/card/media/prompt/tool output/secret material in inputs, reports, fixtures, logs, or docs evidence.
```

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

**Objective:** Define the Phase 9 module as pure, prototype-only, and import-safe.

**Files:**

- Create test: `tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py`
- Future implementation: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_shadow_design.py`

**Test requirements:**

- Import fails before implementation because the module does not exist.
- After implementation, importing the module must not import:
  - `gateway.run`
  - `gateway.platforms.*`
  - `temporalio`
  - `mcp`
  - `tools.registry`
  - `hermes_cli.platforms`
  - `toolsets`
- Public API exposes only constants plus `build_flowweaver_controlled_shadow_plan`.
- Public signature accepts descriptors only, not clients, factories, adapters, addresses, task queues, callbacks, config paths, sockets, or secrets.

**RED command:**

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py -q
```

Expected RED: missing module/API only, not syntax or fixture failure.

### Task 2: RED happy path from exact Phase 8 report

**Objective:** Prove an exact Phase 8 success report plus strict descriptors yields a safe controlled-shadow plan.

**Files:**

- Modify test: `tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py`

**Test requirements:**

- Build a minimal exact Phase 8 readiness report fixture using the current Phase 8 report shape.
- Build exact `shadow_scope`, `gateway_observation_boundary`, `runtime_execution_boundary`, `artifact_policy`, and `rollback_policy` fixtures.
- Assert output:
  - `ok is True`
  - `type == flowweaver.controlled_shadow_plan.v0`
  - `verdict == ready_for_controlled_shadow_prototype`
  - `side_effects == []`
  - plan uses only allowed surfaces and operation names from the Phase 8 candidate contract.
  - `required_separate_approvals` still includes production Gateway wiring, production config write, Gateway restart, external Temporal service, real send/edit/render/callback, production tool registry, and remote cleanup.
  - report contains no activation wording such as production enabled or live enabled.

### Task 3: RED readiness report validation

**Objective:** Ensure Phase 9 trusts only the proven Phase 8 readiness artifact, not arbitrary green-looking data.

**Files:**

- Modify test: `tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py`

**Test requirements:**

- Reject `ok = False` with `invalid_readiness_report`.
- Reject any verdict other than `ready_for_controlled_shadow_design`.
- Reject missing required checks.
- Reject `side_effects != []` with `side_effects_not_absent`.
- Reject `workflow_id != transaction_id` with `workflow_id_mismatch`.
- Reject missing candidate contract fields or broadened runtime operations.
- Reject unknown report fields or nested raw/secret/platform material.

### Task 4: RED scope and Gateway observation boundaries reject production intent

**Objective:** Fail closed if a caller tries to smuggle live Gateway behavior into a controlled-shadow plan.

**Files:**

- Modify test: `tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py`

**Test requirements:**

- Reject `shadow_scope.mode = production | live | enabled`.
- Reject `source_kind = live_gateway_stream | real_feishu | real_sachima`.
- Reject Gateway observation modes that imply live mirroring.
- Reject outbound effects such as send/edit/render/callback.
- Reject adapter imports, platform payloads, or message identifiers.
- Assert returned errors contain only stable codes and do not echo offending values.

### Task 5: RED runtime lifecycle and event-ingress boundaries

**Objective:** Keep Phase 9 lifecycle-free and Update-only.

**Files:**

- Modify test: `tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py`

**Test requirements:**

- Reject `client_lifecycle = client_factory`.
- Reject Temporal addresses, task queues, Worker ownership, WorkflowEnvironment ownership, subprocesses, Docker, daemon, or service startup markers.
- Reject payload-carrying Temporal Signals.
- Reject base dependency requirements for Temporal.
- Assert no runtime client/control-surface method is called while validating invalid descriptors.

### Task 6: RED artifact and observability safety

**Objective:** Guarantee controlled-shadow outputs are audit-friendly but raw-material-free.

**Files:**

- Modify test: `tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py`

**Test requirements:**

- Happy path includes safe artifact fields only: run IDs, synthetic transaction IDs, counts, statuses, digests, stable error codes, approvals, side effects.
- Reject artifact policies that allow raw prompts, raw tool output, raw card JSON, raw media, raw platform payloads, platform message identifiers, credentials, connection strings, or raw exception text.
- Include hostile mapping / non-plain mapping probes so validation copies and checks before projection.
- Assert safe reports, `repr(report)`, logs if any, and docs evidence do not contain hostile values.

### Task 7: RED rollback, kill-switch, and approval boundaries

**Objective:** Ensure the controlled-shadow plan remains default-off and operator-controlled.

**Files:**

- Modify test: `tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py`

**Test requirements:**

- Reject default-on policies.
- Reject missing kill switch or rollback plan requirement.
- Reject config writes, registry writes, Gateway restart allowance, and service lifecycle allowance.
- Require separate approvals for every production-facing action carried forward from Phase 8.

### Task 8: Implement the minimum pure plan builder

**Objective:** Make Tasks 1-7 pass with the smallest lifecycle-free implementation.

**Files:**

- Create: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_shadow_design.py`

**Implementation constraints:**

- Use only stdlib and local pure validation helpers.
- No imports from Gateway runtime, platform adapters, Temporal SDK, CLI, tool registry, or production config modules.
- Exact type checks for mappings/lists/strings before projection.
- Build outputs from sanitized constants and validated descriptors only.
- Return stable error codes; never expose raw exception text.

### Task 9: Add controlled-shadow runbook

**Objective:** Document operator meaning, non-goals, approvals, rollback, and verification commands.

**Files:**

- Create: `docs/runbooks/flowweaver-controlled-shadow.md`

**Content requirements:**

- Phase 9 is not production activation.
- Current approved scope is design/prototype-only/default-off.
- Define controlled shadow as observation/replay, not real delivery.
- List required separate approvals.
- Include no-secrets/no-raw-payload rule.
- Include direct integration pytest warning: `scripts/run_tests.sh` ignores `tests/integration/**`.

### Task 10: Integration guard allowlists, only if implementation requires them

**Objective:** Keep old invariant tests aware of Phase 9 files without weakening forbidden surfaces.

**Files likely to modify:**

```text
tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
tests/integration/test_flowweaver_phase5i_start_signature_parity.py
tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py
tests/integration/test_flowweaver_phase5k_runtime_control_surface.py
```

**Rules:**

- Add only Phase 9 docs/module/test/runbook paths and the modified guard files themselves.
- Do not add Gateway production paths.
- Do not relax forbidden imports/calls/markers.

### Task 11: Verification gates before commit and PR

Focused Phase 9 gate:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py -q
```

Prototype regression gate:

```bash
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py \
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

Static gates:

```bash
python -m py_compile \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_shadow_design.py \
  tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py
python -m ruff check \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_shadow_design.py \
  tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py
git diff --check origin/feature/sachima-channel..HEAD
```

Custom gates:

- changed-file allowlist covers only Phase 9 docs/module/test/runbook and any required integration guard allowlists.
- forbidden path scan rejects production Gateway/platform/agent/tool/CLI/config surfaces.
- added-line scan rejects Gateway/platform imports, Temporal lifecycle imports/calls, client factories, connect helpers, Worker/WorkflowEnvironment ownership, subprocess/service/Docker markers, config writes, registry writes, payload-carrying Signals, and real send/edit/render/callback effects.
- added-line secret scan rejects credential-shaped strings and connection strings.
- safe-output scan checks report shapes, `repr(report)`, docs evidence, and any logs for raw platform IDs, raw payloads, raw prompts, raw tool output, raw card JSON, raw media values, credentials, and raw exception text.

## Design Review Requirements

Before committing the design PR:

1. Run the document gate on untracked docs using `git add -N` or an equivalent scanner that includes untracked files.
2. Run a fresh-context Codex architecture review in read-only mode with exact repo/worktree, phase history, forbidden surfaces, and required PASS/BLOCK verdict.
3. If Codex finds blockers, patch the plan/dev log and run blocker-only re-review.
4. If dev log evidence is appended after a passing gate, rerun the document gate.

## Acceptance Criteria for This Design PR

- Adds only Phase 9 docs/dev-log artifacts.
- No behavior-bearing Python, Gateway, Temporal, config, registry, or simulator repo changes.
- Design explicitly says Phase 9 is controlled-shadow design/prototype preparation only.
- The proposed future implementation has exact input/output contracts, stable errors, test tasks, verification commands, and forbidden surfaces.
- The design keeps production activation, Gateway restart, external service lifecycle, production config writes, real send/edit/render/callback, production tool registration, and remote cleanup as separate approvals.
- Codex fresh-context design review is PASS or all blockers are patched and re-reviewed.

## Future Candidate Phases After Phase 9

These are candidates only; they are not approved by this design PR.

1. Phase 9 implementation: prototype-only controlled-shadow plan builder and tests.
2. Phase 10: isolated controlled-shadow dry-run loop using simulator/replay fixtures only.
3. Phase 11: observability/artifact persistence for controlled shadow, still safe-summary-only.
4. Later separate production design: real Gateway boundary and rollback/kill-switch design.

Do not skip from Phase 9 directly to production Gateway integration. That would be speedrunning into a wall, and not the fun kind.
