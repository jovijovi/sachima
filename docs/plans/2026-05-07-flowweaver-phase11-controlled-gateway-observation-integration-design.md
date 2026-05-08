# FlowWeaver Phase 11 Controlled Gateway Observation / Integration Design Gate Plan

> **For Hermes:** This document is the Phase 11 design gate. 狗哥 approved starting Phase 11 design on 2026-05-07 after Phase 10 implementation PR #44 was verified merged and local canonical `feature/sachima-channel` was fast-forward synchronized. Do not implement behavior-bearing code until this design gate passes review and 狗哥 explicitly approves execution.

**Goal:** Define a safe, default-off design gate for a future controlled Gateway observation/integration seam that consumes exact Phase 10 prototype evidence, describes the minimal allowed Gateway touchpoints, and keeps real production effects behind separate approvals.

**Architecture:** Phase 11 should sit above Phase 10 as a pure contract/design layer. Phase 10 remains the bounded prototype evidence source; existing Gateway shadow tap and shadow runtime publication modules remain observed source material only; Phase 11 emits an integration design report and checklist for a later implementation phase. This design PR is docs-only, and a later Phase 11 implementation should still be pure/prototype-only and must not wire live Gateway behavior.

**Tech Stack:** Python, pytest, existing FlowWeaver Phase 4 shadow tap, Phase 5D/5E shadow runtime publication, Phase 7 loop, Phase 8 readiness gate, Phase 9 controlled-shadow plan, Phase 10 controlled-shadow prototype loop, docs-only design gates. Temporal remains optional/external and must not be constructed, connected, or owned by this phase.

---

## Baseline

```text
Timestamp: 2026-05-07 18:11:54 CST +0800
Repository: jovijovi/sachima
Base branch: origin/feature/sachima-channel
Base HEAD: ec0b8dd73d02467df610fc5fa918c5438623fbdb
Phase 11 branch: feat/flowweaver-phase11-controlled-gateway-observation-integration-design
Phase 11 worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase11-controlled-gateway-observation-integration-design
Open PRs against feature/sachima-channel at design start: none
```

Current merged state:

- Phase 5 through 5K Durable Runtime Foundation: **merged**.
- Phase 6 Gateway ACK Shadow Bridge: **merged**.
- Phase 7 Gateway Shadow E2E Loop: **merged** via PR #39.
- Phase 8 Production Readiness Gate: **merged** via PR #40.
- Phase 9 Controlled Shadow Design: **merged** via PR #41.
- Phase 9 Controlled Shadow Plan Builder implementation: **merged** via PR #42.
- Phase 10 Controlled Shadow Prototype Loop design: **merged** via PR #43.
- Phase 10 Controlled Shadow Prototype Loop implementation: **merged** via PR #44.
- Production Gateway wiring: **not implemented and not approved**.
- Live Gateway observation enablement: **not implemented and not approved**.
- External `sachima-im-simulator` changes: **not in this Sachima repo phase**.

## Current Context

Phase 10 now proves this lab-only chain:

```text
exact Phase 9 controlled-shadow plan report
  + bounded sanitized Phase 7-style publication fixtures
  + caller-supplied prototype control surface
  + default-off run policy
  -> safe Phase 10 prototype loop report
  -> verdict controlled_shadow_prototype_loop_verified
```

Phase 10 deliberately does **not** authorize:

```text
live Gateway observation
production Gateway wiring
production config writes
production tool registry writes
Gateway restart
external Temporal service lifecycle
real send/edit/render/callback effects
```

Phase 11 should answer a narrower next question:

```text
Given exact Phase 10 prototype evidence, what default-off Gateway observation/integration contract could a future implementation safely build without enabling live production effects?
```

Phase 11 should **not** answer by modifying the running Gateway, enabling a feature flag in production config, starting Temporal services, registering tools, sending messages, editing messages, rendering cards, handling callbacks, or restarting the Gateway.

## Definition: Controlled Gateway Observation / Integration Design Gate

Controlled Gateway Observation / Integration Design Gate means:

```text
exact Phase 10 prototype loop report
  + static Gateway observation boundary descriptor
  + static integration policy descriptor
  + static runtime handoff boundary descriptor
  + artifact/log/redaction policy
  + rollback/kill-switch policy
  -> safe Phase 11 design report
  -> verdict ready_for_controlled_gateway_observation_implementation
  -> no live observation and no production side effects
```

Allowed meaning:

- Define the exact safe Phase 10 report shape that may feed a future Gateway observation design.
- Define allowed future Gateway observation touchpoints as labels and file paths, not as live calls.
- Define a default-off config gate and a staged rollout checklist for later approval.
- Define how future code must project already-sanitized Gateway shadow artifacts into Phase 10-style fixtures.
- Define what tests and source gates must prove before any future implementation PR is accepted.
- Emit only safe design summaries, approval labels, counts, checks, and stable error codes.

Forbidden meaning:

- No production Gateway behavior changes in this design PR.
- No `gateway/run.py` changes in this design PR.
- No `run_agent.py` changes in this design PR.
- No `gateway/platforms/**` changes in this design PR.
- No production config writes.
- No production tool registry writes.
- No Gateway restart.
- No real send/edit/render/callback.
- No live Gateway observation.
- No Temporal client, Worker, WorkflowEnvironment, Docker, daemon, socket, subprocess, task queue, namespace, address, or service lifecycle.
- No payload-carrying Temporal Signals.
- No raw prompts, raw tool output, raw card JSON, raw media bytes/paths, raw platform payloads, platform chat/user/message identifiers, raw exception text, credentials, or connection strings in reports, artifacts, logs, or docs evidence.

In plain language: Phase 11 writes the safety choreography for approaching the stage. It still does not step on stage.

## Strongest Allowed Verdict

The strongest successful Phase 11 verdict should be:

```text
ready_for_controlled_gateway_observation_implementation
```

That verdict means only that a default-off controlled Gateway observation/integration implementation can be planned next. It must not be named or interpreted as production readiness, production enablement, live Gateway observation, or permission to alter the running Gateway.

Explicitly forbidden verdict strings in implementation outputs:

```text
production_ready
production_enabled
live_enabled
gateway_enabled
observation_enabled
integration_enabled
```

## Proposed Implementation Surface After Design Approval

Create a new prototype-only module in a later implementation PR:

```text
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_gateway_observation_design.py
```

Create focused tests:

```text
tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py
```

Create or update runbook:

```text
docs/runbooks/flowweaver-controlled-gateway-observation-design.md
```

Update only existing invariant changed-file allowlists if they fail closed on the new prototype files. Do not weaken forbidden-surface checks.

Do **not** modify in this design PR:

```text
gateway/run.py
run_agent.py
gateway/platforms/**
production config files
production tool registry files
```

Do **not** modify in the later Phase 11 implementation PR unless a separate design amendment explicitly approves it:

```text
gateway/run.py
run_agent.py
gateway/platforms/**
production config files
production tool registry files
```

Actual default-off Gateway hook code, if approved later, should be a later Phase 12 implementation. Phase 11 should produce the exact contract Phase 12 must satisfy.

## Existing Source Anchors Considered

Phase 11 design should inspect and reference these as existing context only:

```text
gateway/flowweaver_shadow.py
gateway/flowweaver_shadow_publisher.py
gateway/flowweaver_contract.py
gateway/flowweaver_shadow_dry_run.py
gateway/run.py around task_tracker / flowweaver_shadow gates
gateway/delivery_state.py
gateway/progress/events.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_shadow_prototype_loop.py
tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py
tests/gateway/test_flowweaver_shadow_tap.py
tests/gateway/test_flowweaver_shadow_publisher.py
tests/gateway/test_flowweaver_shadow_publisher_run_hook.py
```

Important current facts:

- Existing Gateway shadow collection is already config-gated under `display.task_tracker.flowweaver_shadow`.
- Existing shadow runtime publication is only attached under the full shadow + dry-run + publish gate.
- Existing run-loop tests assert default-off behavior and no adapter send/edit side effects.
- Existing failure tests assert sanitized logs and no raw exception text/private IDs in results or logs.
- Existing Phase 10 evidence consumes sanitized publication fixtures through caller-supplied fake/prototype control surfaces.

Phase 11 should use those facts to write a future contract; it should not treat those existing hooks as production enablement.

## Public Constants

The Phase 11 implementation should expose these constants:

```text
FLOWWEAVER_CONTROLLED_GATEWAY_OBSERVATION_DESIGN_VERSION = "flowweaver.controlled_gateway_observation_design.v0"
CONTROLLED_GATEWAY_OBSERVATION_BOUNDARY_TYPE = "flowweaver.controlled_gateway_observation_boundary.v0"
CONTROLLED_GATEWAY_INTEGRATION_POLICY_TYPE = "flowweaver.controlled_gateway_integration_policy.v0"
CONTROLLED_GATEWAY_RUNTIME_HANDOFF_BOUNDARY_TYPE = "flowweaver.controlled_gateway_runtime_handoff_boundary.v0"
CONTROLLED_GATEWAY_ARTIFACT_POLICY_TYPE = "flowweaver.controlled_gateway_artifact_policy.v0"
CONTROLLED_GATEWAY_ROLLBACK_POLICY_TYPE = "flowweaver.controlled_gateway_rollback_policy.v0"
CONTROLLED_GATEWAY_OBSERVATION_DESIGN_REPORT_TYPE = "flowweaver.controlled_gateway_observation_design_report.v0"
```

It may import only safe prototype modules:

```text
flowweaver_runtime_client.controlled_shadow_prototype_loop
```

It must not import Gateway runtime modules, Gateway platform adapters, Temporal SDK modules, tool registries, production runtime modules, Docker/systemd helpers, sockets, subprocesses, or platform SDKs.

## Primary Entrypoint

```text
def design_flowweaver_controlled_gateway_observation(
    *,
    phase10_prototype_loop_report: object,
    gateway_observation_boundary: object,
    integration_policy: object,
    runtime_handoff_boundary: object,
    artifact_policy: object,
    rollback_policy: object,
) -> dict[str, object]
```

This function must be synchronous and pure. It must not accept or construct clients, factories, addresses, task queues, callbacks, platform adapters, config paths, sockets, subprocesses, secrets, or live runtime handles.

## Input Contracts

### `phase10_prototype_loop_report`

Accept only an exact safe Phase 10 success report produced by `run_flowweaver_controlled_shadow_prototype_loop(...)`.

Allowed top-level success fields only:

```text
type
version
ok
verdict
phase
run_id
plan_transaction_id
publication_count
loop_results
artifact
checks
required_separate_approvals
verification_matrix
runbook_outline
side_effects
```

Required top-level signals:

```text
type = flowweaver.controlled_shadow_prototype_loop_report.v0
version = flowweaver.controlled_shadow_prototype_loop.v0
ok = True
verdict = controlled_shadow_prototype_loop_verified
phase = phase10_controlled_shadow_prototype_loop
run_id starts with controlled_shadow_run_
plan_transaction_id starts with runtime_tx_
publication_count equals len(loop_results)
side_effects = []
```

Required `loop_results` item fields only:

```text
workflow_id
transaction_id
start_status
ack_count
surfaces
status_counts
delivery_counts
stable_error_codes
safe_digest
side_effects
```

Required `loop_results` signals:

```text
workflow_id starts with runtime_tx_
transaction_id starts with runtime_tx_
workflow_id = transaction_id
start_status in started | running
ack_count integer 0..20
surfaces ordered subset of final_text, rich_card, progress_card, media
status_counts is safe counts only
delivery_counts is safe counts only
stable_error_codes is a list of stable code strings
safe_digest is a non-empty digest string
side_effects = []
```

Required Phase 10 artifact fields only:

```text
type
artifact_mode
run_id
plan_transaction_id
publication_count
operation_counts
delivery_counts
statuses
digests
stable_error_codes
approvals
side_effects
```

Required Phase 10 artifact signals:

```text
type = flowweaver.controlled_shadow_prototype_artifact.v0
artifact_mode = safe_summary_only
run_id equals top-level run_id
plan_transaction_id equals top-level plan_transaction_id
publication_count equals top-level publication_count
approvals equals required separate approvals
side_effects = []
```

Required Phase 10 checks, all true:

```text
phase9_plan_exact_shape
plan_default_off
run_policy_default_off
publication_fixtures_bounded
publication_fixtures_safe
caller_supplied_control_surface_only
gateway_effects_absent
runtime_lifecycle_absent
validated_updates_only
phase7_loop_results_safe
artifact_safe_summary_only
production_actions_separate
side_effects_absent
```

Required Phase 10 `verification_matrix` exact list:

```text
phase9_plan_exact_shape
plan_default_off
run_policy_default_off
publication_fixtures_bounded
publication_fixtures_safe
caller_supplied_control_surface_only
gateway_effects_absent
runtime_lifecycle_absent
validated_updates_only
phase7_loop_results_safe
artifact_safe_summary_only
production_actions_separate
side_effects_absent
```

Required Phase 10 `runbook_outline` exact list:

```text
phase10_proves_bounded_prototype_loop_only
production_activation_requires_separate_design_and_approval
keep_default_off_until_explicit_enablement
caller_supplied_control_surface_only
no_gateway_adapter_or_platform_payloads
no_temporal_client_worker_docker_or_service_lifecycle
no_raw_payloads_or_secrets_in_reports_or_artifacts
use_direct_pytest_for_integration_regression
```

Required inherited approvals exact order:

```text
production_gateway_wiring
production_config_write
gateway_restart
external_temporal_service
real_send_edit_render_callback
production_tool_registry
remote_branch_or_worktree_cleanup
```

The Phase 11 implementation must reject:

```text
blocked Phase 10 reports
missing or extra Phase 10 success fields
wrong verdicts, especially live/production enablement strings
unknown nested loop-result or artifact fields
missing or duplicate inherited approvals
raw/card/media/platform/prompt/tool/secret material
workflow_id != transaction_id
artifact policy values that allow raw fields
side_effects not equal to []
```

### `gateway_observation_boundary`

This is a static descriptor only. No adapter objects, MessageEvent objects, platform SDK objects, callbacks, config paths, loggers, or live Gateway state.

Allowed fields only:

```text
type
mode
source_kind
candidate_touchpoints
allowed_existing_modules
allowed_future_files
allowed_surfaces
observation_inputs
observation_outputs
adapter_imports_allowed
platform_payloads_allowed
message_identifiers_allowed
raw_content_allowed
send_edit_render_callback_allowed
logs_allowed
side_effects
```

Required values:

```text
type = flowweaver.controlled_gateway_observation_boundary.v0
mode = design_only | future_default_off_observation_candidate
source_kind = phase10_evidence_replay | gateway_shadow_publication_summary | simulator_fixture
candidate_touchpoints ordered subset of task_tracker_snapshot, flowweaver_shadow_snapshot, flowweaver_shadow_runtime_publication, delivery_state_summary
allowed_existing_modules ordered subset of gateway/flowweaver_shadow.py, gateway/flowweaver_shadow_publisher.py, gateway/flowweaver_contract.py, gateway/delivery_state.py, gateway/progress/events.py
allowed_future_files ordered subset of gateway/flowweaver_controlled_gateway_observation.py, tests/gateway/test_flowweaver_controlled_gateway_observation.py
allowed_surfaces ordered subset of final_text, rich_card, progress_card, media
observation_inputs ordered subset of phase10_report, shadow_runtime_publication_summary, delivery_state_summary, progress_snapshot_summary
observation_outputs ordered subset of safe_summary, fixture_projection, readiness_checks, stable_error_codes
adapter_imports_allowed = False
platform_payloads_allowed = False
message_identifiers_allowed = False
raw_content_allowed = False
send_edit_render_callback_allowed = False
logs_allowed = sanitized_codes_only | false
side_effects = []
```

Rejected examples:

```text
mode = live | production | enabled
source_kind = real_feishu | real_sachima | live_gateway_stream
candidate_touchpoints that include adapter.send, edit_message, render_card, callback_handler, platform_payload, MessageEvent, MessageSource
allowed_existing_modules containing gateway/platforms/**, run_agent.py, tool registry files, production config files
allowed_future_files containing production config, registry files, platform adapters, run_agent.py
adapter_imports_allowed = True
platform_payloads_allowed = True
message_identifiers_allowed = True
raw_content_allowed = True
send_edit_render_callback_allowed = True
side_effects not equal to []
```

### `integration_policy`

Allowed fields only:

```text
type
mode
feature_flag_ref
default_enabled
implementation_stage
allowed_config_scope
config_write_allowed
gateway_restart_allowed
runtime_effects_allowed
temporal_lifecycle_allowed
payload_carrying_signals_allowed
registry_write_allowed
operator_approval_ref
rollout_steps
rollback_required
kill_switch_required
side_effects
```

Required values:

```text
type = flowweaver.controlled_gateway_integration_policy.v0
mode = design_gate_only | implementation_contract_only
feature_flag_ref starts with feature_flag_ref_
default_enabled = False
implementation_stage = design_only | future_pr_only
allowed_config_scope = static_docs_only | test_fixture_only
config_write_allowed = False
gateway_restart_allowed = False
runtime_effects_allowed = False
temporal_lifecycle_allowed = False
payload_carrying_signals_allowed = False
registry_write_allowed = False
operator_approval_ref starts with approval_ref_
rollout_steps is an ordered safe label list, not commands
rollback_required = True
kill_switch_required = True
side_effects = []
```

The rollout labels may include only:

```text
design_review
implementation_pr
focused_tests
integration_regression
fresh_context_review
manual_enablement_request
separate_gateway_restart_request
post_enablement_observation_only_verification
rollback_review
```

Rejected examples:

```text
feature flags set to enabled/on/true
config paths
config write commands
Gateway restart commands
systemd/systemctl/service commands
Temporal addresses, namespaces, task queues, clients, Workers, test environments
send/edit/render/callback effects
tool registry writes
shell commands
side_effects not equal to []
```

### `runtime_handoff_boundary`

Allowed fields only:

```text
type
mode
control_surface_lifecycle
runtime_operations
runtime_client_construction_allowed
temporal_client_allowed
temporal_worker_allowed
workflow_environment_allowed
payload_carrying_signals_allowed
fixture_projection
ack_source
ack_target_validation
side_effects
```

Required values:

```text
type = flowweaver.controlled_gateway_runtime_handoff_boundary.v0
mode = no_live_handoff | future_caller_supplied_only
control_surface_lifecycle = none | caller_supplied_only
runtime_operations ordered subset of start_transaction, query_transaction, reconcile_delivery_ack
runtime_client_construction_allowed = False
temporal_client_allowed = False
temporal_worker_allowed = False
workflow_environment_allowed = False
payload_carrying_signals_allowed = False
fixture_projection = phase10_publication_fixture_shape
ack_source = phase6_shadow_bridge | shadow_runtime_publication_summary
ack_target_validation = exact_initialized_delivery_slot
side_effects = []
```

Rejected examples:

```text
client_factory
connect_helper
Temporal address or namespace
task queue
Worker
WorkflowEnvironment
signal_with_start
payload-carrying Signal
subprocess/socket/HTTP listener
side_effects not equal to []
```

### `artifact_policy`

Allowed fields only:

```text
type
artifact_mode
allowed_fields
retention
log_policy
forbidden_material
side_effects
```

Required values:

```text
type = flowweaver.controlled_gateway_artifact_policy.v0
artifact_mode = safe_summary_only
allowed_fields ordered subset of design_id, phase10_run_id, plan_transaction_id, candidate_touchpoints, allowed_surfaces, checks, stable_error_codes, approvals, side_effects
retention = docs_evidence_only | local_artifact_only
log_policy = sanitized_codes_only | no_logs
forbidden_material exact Phase 11 forbidden-material list
side_effects = []
```

Required forbidden-material list:

```text
raw_prompt
raw_tool_output
raw_card_json
raw_media_payload
raw_platform_payload
platform_message_identifiers
credentials_or_connection_strings
raw_exception_text
raw_gateway_event
raw_adapter_object
raw_callback_payload
raw_runtime_history
```

Policy metadata may name forbidden material; actual reports, artifacts, logs, and user-visible outputs must never contain raw values.

### `rollback_policy`

Allowed fields only:

```text
type
rollback_mode
kill_switch_required
rollback_hooks_required
config_revert_required
gateway_restart_requires_separate_approval
production_enablement_requires_separate_approval
side_effects
```

Required values:

```text
type = flowweaver.controlled_gateway_rollback_policy.v0
rollback_mode = design_only | feature_flag_off_first
kill_switch_required = True
rollback_hooks_required = True
config_revert_required = True
gateway_restart_requires_separate_approval = True
production_enablement_requires_separate_approval = True
side_effects = []
```

## Output Contract

A successful Phase 11 report should include exactly these top-level fields:

```text
type
version
ok
verdict
phase
design_id
phase10_run_id
plan_transaction_id
controlled_gateway_observation_plan
checks
artifact_policy
rollback_policy
required_separate_approvals
verification_matrix
runbook_outline
side_effects
```

Required top-level values:

```text
type = flowweaver.controlled_gateway_observation_design_report.v0
version = flowweaver.controlled_gateway_observation_design.v0
ok = True
verdict = ready_for_controlled_gateway_observation_implementation
phase = phase11_controlled_gateway_observation_integration_design
design_id starts with controlled_gateway_observation_design_
phase10_run_id starts with controlled_shadow_run_
plan_transaction_id starts with runtime_tx_
side_effects = []
```

Allowed `controlled_gateway_observation_plan` fields only:

```text
plan_version
source_kind
mode
candidate_touchpoints
allowed_existing_modules
allowed_future_files
allowed_surfaces
observation_inputs
observation_outputs
feature_flag_ref
operator_approval_ref
runtime_operations
runtime_handoff_mode
artifact_mode
approval_refs
rollback_hooks_required
kill_switch_required
forbidden_material
fail_closed_errors
```

Required `controlled_gateway_observation_plan` values:

```text
plan_version = flowweaver.controlled_gateway_observation_design.v0
source_kind = phase10_evidence_replay | gateway_shadow_publication_summary | simulator_fixture
mode = design_only | future_default_off_observation_candidate
candidate_touchpoints subset of task_tracker_snapshot, flowweaver_shadow_snapshot, flowweaver_shadow_runtime_publication, delivery_state_summary
allowed_existing_modules subset of approved Gateway shadow modules only
allowed_future_files subset of new Gateway observation helper/test files only
allowed_surfaces subset of final_text, rich_card, progress_card, media
observation_inputs subset of phase10_report, shadow_runtime_publication_summary, delivery_state_summary, progress_snapshot_summary
observation_outputs subset of safe_summary, fixture_projection, readiness_checks, stable_error_codes
feature_flag_ref starts with feature_flag_ref_
operator_approval_ref starts with approval_ref_
runtime_operations ordered subset of start_transaction, query_transaction, reconcile_delivery_ack
runtime_handoff_mode = no_live_handoff | future_caller_supplied_only
artifact_mode = safe_summary_only
approval_refs contains only synthetic approval_ref_ and feature_flag_ref_ values
rollback_hooks_required = True
kill_switch_required = True
forbidden_material exact Phase 11 forbidden-material list
fail_closed_errors exact sorted Phase 11 error-code list
```

Allowed stable Phase 11 error codes:

```text
artifact_policy_violation
invalid_artifact_policy
invalid_gateway_observation_boundary
invalid_integration_policy
invalid_phase10_report
invalid_rollback_policy
invalid_runtime_handoff_boundary
production_action_requested
registry_or_config_write_requested
runtime_lifecycle_requested
side_effects_not_absent
unsafe_material
workflow_id_mismatch
```

Successful reports must set all checks true:

```text
phase10_report_exact_shape
phase10_evidence_not_live_enablement
gateway_observation_boundary_static
integration_policy_default_off
runtime_handoff_lifecycle_free
allowed_touchpoints_bounded
artifact_safe_summary_only
rollback_and_kill_switch_present
production_actions_separate
side_effects_absent
```

Required `verification_matrix` exact list:

```text
phase10_report_exact_shape
phase10_evidence_not_live_enablement
gateway_observation_boundary_static
integration_policy_default_off
runtime_handoff_lifecycle_free
allowed_touchpoints_bounded
artifact_safe_summary_only
rollback_and_kill_switch_present
production_actions_separate
side_effects_absent
```

Required `runbook_outline` exact list:

```text
phase11_is_design_gate_only
controlled_gateway_observation_implementation_requires_separate_approval
live_gateway_observation_enablement_requires_separate_approval
production_activation_requires_separate_design_and_approval
keep_default_off_until_explicit_enablement
rollback_and_kill_switch_required_before_any_wiring
no_raw_payloads_or_secrets_in_reports_or_artifacts
use_direct_pytest_for_integration_regression
```

Required separate approvals, exact order:

```text
controlled_gateway_observation_implementation
live_gateway_observation_enablement
production_gateway_wiring
production_config_write
gateway_restart
external_temporal_service
real_send_edit_render_callback
production_tool_registry
remote_branch_or_worktree_cleanup
```

A blocked report should include only safe fields:

```text
type
version
ok = False
verdict = blocked
phase = phase11_controlled_gateway_observation_integration_design
error_code
side_effects = []
```

Do not include:

```text
raw Phase 10 loop results beyond safe summaries
raw Gateway progress snapshots
raw agent_result
raw delivery state
raw shadow snapshots or captures
raw runtime publications
raw platform payloads
raw callback payloads
raw prompts
raw tool output
raw card JSON
raw media data or paths
platform chat/user/message IDs
credentials or connection strings
raw exception text
Temporal history
```

## Implementation Tasks After Design Approval

### Task 1: Write RED import and surface tests

**Objective:** Prove the Phase 11 module does not exist yet and define import/lifecycle boundaries.

**Files:**

- Create: `tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py`

**Steps:**

1. Add an import test for `flowweaver_runtime_client.controlled_gateway_observation_design`.
2. Assert the public constants above.
3. Assert `design_flowweaver_controlled_gateway_observation` is synchronous.
4. Remove `gateway`, `gateway.run`, `gateway.platforms.feishu`, `temporalio`, `tools.registry`, and related modules from `sys.modules` before import.
5. After import, assert those modules were not imported.
6. Run:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py -q
```

Expected RED: module missing, not `no tests ran`.

### Task 2: Add exact Phase 10 report fixture and validator tests

**Objective:** Make Phase 11 consume the real Phase 10 success output shape exactly.

**Files:**

- Modify: `tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py`

**Steps:**

1. Build a safe Phase 10 report fixture by calling `run_flowweaver_controlled_shadow_prototype_loop(...)` with safe fixtures or by copying the exact success shape from the merged implementation.
2. Add negative cases for extra top-level fields, missing top-level fields, wrong verdict, blocked report, duplicate inherited approvals, reordered inherited approvals, missing inherited approvals, missing checks, false checks, mutated `verification_matrix`, reordered `verification_matrix`, missing `verification_matrix` item, mutated `runbook_outline`, reordered `runbook_outline`, missing `runbook_outline` item, unsafe artifact fields, workflow/transaction mismatch in loop results, and `side_effects` not equal to `[]`.
3. Require stable safe error code `invalid_phase10_report` or `unsafe_material` as appropriate.
4. Confirm RED failures before implementation.

### Task 3: Add Gateway observation boundary descriptor tests

**Objective:** Define the allowed future Gateway observation touchpoints without live Gateway behavior.

**Files:**

- Modify: `tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py`

**Steps:**

1. Add a safe `gateway_observation_boundary` fixture with `mode = future_default_off_observation_candidate`.
2. Include candidate touchpoints: `task_tracker_snapshot`, `flowweaver_shadow_snapshot`, `flowweaver_shadow_runtime_publication`, `delivery_state_summary`.
3. Include only approved existing modules: `gateway/flowweaver_shadow.py`, `gateway/flowweaver_shadow_publisher.py`, `gateway/flowweaver_contract.py`, `gateway/delivery_state.py`, `gateway/progress/events.py`.
4. Add negative cases for `gateway/run.py` as a direct implementation file in Phase 11, `gateway/platforms/**`, `run_agent.py`, production config, registry files, adapter import allowance, platform payload allowance, message identifier allowance, raw content allowance, and send/edit/render/callback allowance.
5. Assert all failures return stable safe error code `invalid_gateway_observation_boundary` or `production_action_requested`.

### Task 4: Add integration policy and runtime handoff tests

**Objective:** Keep future implementation default-off and lifecycle-free.

**Files:**

- Modify: `tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py`

**Steps:**

1. Add safe `integration_policy`, `runtime_handoff_boundary`, `artifact_policy`, and `rollback_policy` fixtures.
2. Assert happy-path output has `ready_for_controlled_gateway_observation_implementation`, exact checks, exact approvals, exact verification matrix, exact runbook outline, and `side_effects = []`.
3. Add negative cases for enabled feature flags, config path writes, Gateway restart commands, systemd/service lifecycle, Temporal address/namespace/task queue/client/Worker/test-environment fields, runtime client factory/connect helper, payload-carrying Signal hints, tool registry writes, shell/subprocess/socket hints, raw log policy, and missing kill switch.
4. Assert no raw Gateway/adapter/Temporal/private material appears in success or blocked outputs.

### Task 5: Implement minimal Phase 11 design module

**Objective:** Make RED tests pass with a pure contract builder.

**Files:**

- Create: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_gateway_observation_design.py`

**Implementation constraints:**

- Import only safe Phase 10 constants/helpers if needed.
- Use plain dict/list copies and exact-key validation.
- Validate exact Phase 10 report shape before any descriptor validation.
- Validate all descriptors with exact fields, allowed values, ordered lists, and stable error codes.
- Build only a safe design report and no live objects.
- Never include raw Gateway snapshots, raw agent results, raw delivery state, raw runtime publications, raw exception text, raw platform identifiers, or secret-shaped values in output.
- Catch unexpected exceptions and map them to stable safe codes without raw exception text.

### Task 6: Add runbook and narrow invariant allowlist updates

**Objective:** Document Phase 11 without expanding production scope.

**Files:**

- Create: `docs/runbooks/flowweaver-controlled-gateway-observation-design.md`
- Modify only existing integration changed-file allowlists if they fail closed on the new Phase 11 files.

Runbook must repeat:

- Phase 11 is a design gate only.
- A passing Phase 11 report does not authorize live Gateway observation.
- Actual Gateway hook implementation requires a later explicit approval.
- Production config write and Gateway restart remain separately approved actions.
- All artifacts/logs/reports remain safe-summary-only.

### Task 7: Verification and review

Run focused and regression tests:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py -q
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py -q
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py -q
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py -q
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py -q
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase*.py -q
```

Run integration regression directly, not through `scripts/run_tests.sh`:

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

Run static and safety gates:

```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m py_compile \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_gateway_observation_design.py \
  tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m ruff check \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_gateway_observation_design.py \
  tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py

git diff --check
```

Custom gates must scan committed, staged, unstaged, and untracked changes for:

```text
production Gateway path changes outside explicitly approved Phase 11 files
Temporal client/Worker/test-environment construction
Docker/systemd/service/subprocess/socket lifecycle
payload-carrying Signals
config/registry writes
send/edit/render/callback calls
Gateway platform adapter imports
raw prompt/tool/card/media/platform material
platform chat/user/message identifiers
secret-shaped values
raw exception logging or serialization
```

Run fresh-context Codex review before PR. Any blocker must be fixed by first adding or correcting RED tests, then patching implementation, rerunning verification, and doing blocker-only re-review.

## Design Review Checklist

- [ ] Phase 11 consumes exact Phase 10 success report shape.
- [ ] Phase 11 rejects blocked/wrong/production-like Phase 10 reports.
- [ ] Gateway observation boundary is static and does not accept live Gateway objects.
- [ ] Candidate touchpoints are bounded and tied to existing sanitized shadow modules.
- [ ] Phase 11 does not authorize direct `gateway/run.py` or platform adapter changes.
- [ ] Future Gateway hook implementation is deferred to a later separately approved phase.
- [ ] Integration policy is default-off and does not write config.
- [ ] Gateway restart remains separately approved.
- [ ] Runtime handoff remains lifecycle-free and caller-supplied-only if ever used.
- [ ] No Temporal client, Worker, WorkflowEnvironment, Docker, daemon, socket, or service startup is introduced.
- [ ] No payload-carrying Temporal Signals are introduced.
- [ ] No real send/edit/render/callback path exists.
- [ ] Reports and artifacts contain only safe summaries.
- [ ] Raw exception text is never logged, returned, or serialized.
- [ ] Integration allowlist updates are narrow and do not weaken safety gates.
- [ ] Docs and dev log pass docs-only gates after final evidence is appended.

## Out of Scope

These require separate later approval:

- Phase 11 implementation work.
- Actual Gateway observation hook implementation.
- Live Gateway observation enablement.
- Production Gateway wiring.
- Gateway restart as part of FlowWeaver rollout.
- External Temporal service lifecycle.
- Real Temporal client/Worker construction.
- Real Feishu/Sachima send/edit/render/callback.
- Production config writes.
- Production tool registry writes.
- Remote branch or worktree cleanup.
- Changes to the external `sachima-im-simulator` repo.

## PR Scope for This Design Gate

This design PR should be docs-only:

```text
docs/plans/2026-05-07-flowweaver-phase11-controlled-gateway-observation-integration-design.md
docs/dev_log/2026-05-07-flowweaver-phase11-controlled-gateway-observation-integration-design.md
```

No code, tests, Gateway files, production config, registry files, or service artifacts should change in the design PR.
