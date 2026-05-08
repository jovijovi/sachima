# FlowWeaver Phase 10 Controlled Shadow Prototype Loop Design Plan

> **For Hermes:** This document is the Phase 10 design gate. 狗哥 asked to start Phase 10 design on 2026-05-07 after Phase 9 implementation PR #42 was verified merged and the local canonical `feature/sachima-channel` branch was fast-forward synchronized. Do not implement behavior-bearing code until this design gate passes review and 狗哥 explicitly approves execution.

**Goal:** Define a prototype-only controlled-shadow loop that consumes the exact Phase 9 plan-builder success report, runs only bounded sanitized shadow publication fixtures through caller-supplied prototype control surfaces, and emits safe evidence artifacts without production Gateway wiring or real IM side effects.

**Architecture:** Phase 10 should add a thin prototype harness above Phase 9 and Phase 7. Phase 9 remains the policy/plan authority; Phase 7 remains the safe publication-to-ACK loop primitive; Phase 10 only coordinates bounded fixture replay, validates every input/output boundary, and produces safe summaries suitable for review. The implementation must stay default-off, lifecycle-free, import-safe, and artifact-safe.

**Tech Stack:** Python, pytest, existing FlowWeaver Phase 5K control surface contract, Phase 7 `gateway_shadow_e2e_loop`, Phase 8 `production_readiness_gate`, Phase 9 `controlled_shadow_design`, docs-only design gates. Temporal remains optional and external; this phase must not construct Temporal clients, Workers, test environments, Docker, daemons, sockets, or service lifecycle.

---

## Baseline

```text
Timestamp: 2026-05-07 16:20:55 CST +0800
Repository: jovijovi/sachima
Base branch: origin/feature/sachima-channel
Base HEAD: 67a27449e8335565bcedfc0d6ecacd83aaa0ba35
Phase 10 branch: feat/flowweaver-phase10-controlled-shadow-prototype-loop-design
Phase 10 worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase10-controlled-shadow-prototype-loop-design
```

Current merged state:

- Phase 5 through 5K Durable Runtime Foundation: **merged**.
- Phase 6 Gateway ACK Shadow Bridge: **merged**.
- Phase 7 Gateway Shadow E2E Loop: **merged** via PR #39.
- Phase 8 Production Readiness Gate: **merged** via PR #40.
- Phase 9 Controlled Shadow Design: **merged** via PR #41.
- Phase 9 Controlled Shadow Plan Builder implementation: **merged** via PR #42.
- Phase 10 implementation: **not started**.
- Production Gateway wiring: **not designed and not approved**.

## Current Context

Phase 9 now proves this safe planning chain:

```text
exact Phase 8 readiness report
  + controlled-shadow scope descriptor
  + gateway observation boundary
  + runtime execution boundary
  + artifact policy
  + rollback policy
  -> Phase 9 controlled-shadow plan report
  -> verdict ready_for_controlled_shadow_prototype
```

Phase 10 should answer a narrower next question:

```text
Given a safe Phase 9 plan, can a bounded prototype loop replay sanitized shadow publication fixtures through a caller-supplied prototype control surface and produce only safe evidence?
```

Phase 10 should **not** answer by touching production Gateway integration, live Feishu/Sachima traffic, production config, production tool registry, external Temporal services, or Gateway restarts.

## Definition: Controlled Shadow Prototype Loop

Controlled shadow prototype loop means:

```text
exact Phase 9 safe plan report
  + bounded sanitized Phase 7-style publication fixtures
  + caller-supplied prototype control surface
  + default-off run policy
  -> Phase 7 loop replay per fixture
  -> safe Phase 10 evidence report
  -> no real platform delivery effects
```

Allowed meaning:

- Use already-safe synthetic IDs, counts, statuses, surfaces, digests, and stable error codes.
- Call only caller-supplied prototype/fake control-surface `handle(...)` methods in tests or local fixtures.
- Reuse the existing Phase 7 loop primitive only after validating Phase 9 policy and run bounds.
- Emit safe summaries that can be committed as docs evidence or asserted in tests.

Forbidden meaning:

- No production Gateway/Feishu/Sachima integration.
- No gateway/run.py changes.
- No run_agent.py changes.
- No gateway/platforms/** changes.
- No production config writes.
- No production tool registry writes.
- No Docker, daemon, Temporal service, or Gateway restart.
- No real send/edit/render/callback.
- No Temporal client or Worker construction.
- No payload-carrying Temporal Signals.
- No live Gateway observation.
- No raw prompts, raw tool output, raw card JSON, raw media bytes/paths, raw platform payloads, platform chat/user/message identifiers, raw exception text, credentials, or connection strings in reports, artifacts, logs, or docs evidence.

In plain language: Phase 10 is a supervised lab loop. It is still not a stage performance.

## Strongest Allowed Verdict

The strongest successful Phase 10 verdict should be:

```text
controlled_shadow_prototype_loop_verified
```

That verdict means only that a bounded prototype fixture loop produced safe evidence under the Phase 9 plan. It must not be named or interpreted as production readiness, production enablement, live Gateway observation, or permission to wire runtime behavior into the running Gateway.

Explicitly forbidden verdict strings in implementation outputs:

```text
production_ready
production_enabled
live_enabled
gateway_enabled
```

## Proposed Implementation Surface After Design Approval

Create a new prototype-only module:

```text
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_shadow_prototype_loop.py
```

Create focused tests:

```text
tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py
```

Create or update runbook:

```text
docs/runbooks/flowweaver-controlled-shadow-prototype-loop.md
```

Update only existing invariant changed-file allowlists if they fail closed on the new prototype files. Do not weaken forbidden-surface checks.

Do **not** modify:

```text
gateway/run.py
run_agent.py
gateway/platforms/**
production config files
production tool registry files
```

## Public Constants

The Phase 10 implementation should expose these constants:

```text
FLOWWEAVER_CONTROLLED_SHADOW_PROTOTYPE_LOOP_VERSION = "flowweaver.controlled_shadow_prototype_loop.v0"
CONTROLLED_SHADOW_PROTOTYPE_RUN_POLICY_TYPE = "flowweaver.controlled_shadow_prototype_run_policy.v0"
CONTROLLED_SHADOW_PROTOTYPE_LOOP_REPORT_TYPE = "flowweaver.controlled_shadow_prototype_loop_report.v0"
CONTROLLED_SHADOW_PROTOTYPE_ARTIFACT_TYPE = "flowweaver.controlled_shadow_prototype_artifact.v0"
```

It may import only safe prototype modules:

```text
flowweaver_runtime_client.controlled_shadow_design
flowweaver_runtime_client.gateway_shadow_e2e_loop
```

It must not import Gateway adapters, Temporal SDK modules, tool registries, production runtime modules, Docker/systemd helpers, sockets, subprocesses, or platform SDKs.

## Primary Entrypoint

```text
async def run_flowweaver_controlled_shadow_prototype_loop(
    *,
    controlled_shadow_plan_report: object,
    publication_fixtures: object,
    control_surface: object,
    run_policy: object,
) -> dict[str, object]
```

Why async: the existing Phase 7 shadow loop and control-surface contract are async. Phase 10 can be async while still not owning lifecycle.

This function must not accept or construct:

```text
Gateway adapters
send/edit/render/callback callables
Temporal clients or Workers
Temporal addresses, namespaces, or task queues
client factories or connect helpers
Docker/systemd/service handles
file paths for production config writes
registry writers
platform user/chat/message IDs
raw payloads or secrets
```

The only live object accepted is the already-created caller-supplied prototype `control_surface`. The function may call `await control_surface.handle(...)` only through the already-approved Phase 7 loop path and must never serialize the object or expose raw exception text from it.

## Input Contracts

### `controlled_shadow_plan_report`

Accept only an exact safe Phase 9 success report produced by `build_flowweaver_controlled_shadow_plan(...)`.

Allowed top-level success fields only:

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
```

Required top-level signals:

```text
type = flowweaver.controlled_shadow_plan.v0
version = flowweaver.controlled_shadow_design.v0
ok = True
verdict = ready_for_controlled_shadow_prototype
phase = phase9_controlled_shadow_design
workflow_id starts with runtime_tx_
transaction_id starts with runtime_tx_
workflow_id = transaction_id
side_effects = []
```

Allowed `controlled_shadow_plan` fields only:

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

Required `controlled_shadow_plan` signals:

```text
plan_version = flowweaver.controlled_shadow_design.v0
source_kind = phase7_result_replay | phase8_readiness_replay | simulator_fixture
mode = design_only | prototype_shadow_candidate
allowed_surfaces ordered subset of final_text, rich_card, progress_card, media
max_transactions integer 1..20
max_delivery_surfaces integer 0..20 and >= len(allowed_surfaces)
runtime_operations ordered subset of start_transaction, query_transaction, reconcile_delivery_ack
ack_source = phase6_shadow_bridge | simulator_ack_fixture
artifact_mode = safe_summary_only
approval_refs contains only synthetic approval_ref_ and feature_flag_ref_ values
rollback_hooks_required = True
kill_switch_required = True
forbidden_material exact Phase 9 forbidden-material list
fail_closed_errors exact sorted Phase 9 error-code list
```

Required `fail_closed_errors` exact list:

```text
artifact_policy_violation
invalid_artifact_policy
invalid_gateway_observation_boundary
invalid_readiness_report
invalid_rollback_policy
invalid_runtime_execution_boundary
invalid_shadow_scope
production_action_requested
registry_or_config_write_requested
runtime_lifecycle_requested
side_effects_not_absent
unsafe_material
workflow_id_mismatch
```

Required Phase 9 checks, all true:

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

Required `verification_matrix` exact list:

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

Required `runbook_outline` exact list:

```text
phase9_is_controlled_shadow_design_only
prototype_shadow_requires_explicit_implementation_approval
production_activation_requires_separate_design_and_approval
keep_default_off_until_explicit_enablement
rollback_and_kill_switch_required_before_any_wiring
no_raw_payloads_or_secrets_in_reports_or_artifacts
use_direct_pytest_for_integration_regression
```

Required Phase 9 artifact policy fields only:

```text
artifact_mode
allowed_fields
retention
log_policy
forbidden_material
```

Required artifact policy signals:

```text
artifact_mode = safe_summary_only
allowed_fields ordered subset of run_id, transaction_id, operation_counts, delivery_counts, statuses, digests, stable_error_codes, approvals, side_effects
retention = local_artifact_only | docs_evidence_only
log_policy = sanitized_codes_only
forbidden_material exact Phase 9 forbidden-material list
```

Required separate approvals, exact order:

```text
production_gateway_wiring
production_config_write
gateway_restart
external_temporal_service
real_send_edit_render_callback
production_tool_registry
remote_branch_or_worktree_cleanup
```

The Phase 10 implementation must reject:

```text
blocked Phase 9 reports
missing or extra Phase 9 success fields
wrong verdicts, especially live/production enablement strings
unknown nested plan fields
missing or duplicate required approvals
raw/card/media/platform/prompt/tool/secret material
workflow_id != transaction_id
artifact policy values that allow raw fields
side_effects not equal to []
```

### `publication_fixtures`

Accept a plain list of sanitized Phase 7-style publication fixtures. For Phase 10 v0, support one or more fixtures up to the smaller of:

```text
run_policy.max_publications
controlled_shadow_plan.max_transactions
```

Each fixture must satisfy the existing Phase 7 publication contract before it is passed into `run_shadow_gateway_e2e_loop(...)`.

Required fixture top-level fields, matching Phase 7 ready publication shape:

```text
type
verdict
reason
runtime_model_version
runtime_envelope_type
transaction_id
workflow_id
runtime_identity
start_request
ack_bridge
checks
side_effects
```

Required fixture signals:

```text
type = flowweaver.gateway.shadow_runtime_publication.v0
verdict = ready
reason = ok
runtime_model_version = flowweaver.runtime.v0
runtime_envelope_type = flowweaver.gateway.runtime_ingress_envelope.v0
workflow_id starts with runtime_tx_
transaction_id starts with runtime_tx_
workflow_id = transaction_id
side_effects = []
```

Each fixture must contain only safe synthetic runtime IDs. It must not contain raw Gateway payloads, real platform IDs, raw card/media/prompt/tool data, URLs, credentials, connection strings, or raw exception text.

Delivery ACK updates must remain a bounded subset/prefix of initialized runtime delivery slots. Do not invent ACK updates to force parity.

### `run_policy`

Allowed fields only:

```text
type
mode
source_kind
max_publications
max_delivery_updates_per_publication
control_surface_lifecycle
gateway_effects_allowed
temporal_lifecycle_allowed
payload_carrying_signals_allowed
artifact_mode
log_policy
side_effects
```

Required values:

```text
type = flowweaver.controlled_shadow_prototype_run_policy.v0
mode = prototype_loop_only
source_kind = sanitized_publication_fixture
max_publications integer 1..20 and <= controlled_shadow_plan.max_transactions
max_delivery_updates_per_publication integer 0..20 and <= controlled_shadow_plan.max_delivery_surfaces
control_surface_lifecycle = caller_supplied_only
gateway_effects_allowed = False
temporal_lifecycle_allowed = False
payload_carrying_signals_allowed = False
artifact_mode = safe_summary_only
log_policy = sanitized_codes_only
side_effects = []
```

Reject any run policy that mentions or implies:

```text
live_gateway_stream
production_gateway
real_feishu
real_sachima
send
edit
render
callback
Client.connect
Worker
task_queue
temporal_address
service_lifecycle
Docker
systemctl
registry_write
config_write
```

### `control_surface`

The implementation may accept an already-created caller-supplied object with an async `handle(request)` method because Phase 7 already uses that contract.

Rules:

- Do not construct it.
- Do not call connect/start/open/run methods.
- Do not accept factories, addresses, namespaces, task queues, subprocess commands, sockets, or config paths.
- Do not serialize it into reports or logs.
- Catch exceptions and map them to stable safe codes without raw exception text.
- Tests must use a fake/recording control surface, not a live Temporal client or Gateway adapter.

## Output Contract

A successful report should include exactly these top-level fields:

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

Required top-level values:

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

Each `loop_results` item should include safe summary fields only:

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

Allowed start statuses:

```text
started
running
```

Allowed ACK statuses should come from Phase 6/7 safe ACK status contracts only. Any mismatch should fail closed with a stable Phase 10 error code.

Artifact shape:

```text
type = flowweaver.controlled_shadow_prototype_artifact.v0
artifact_mode = safe_summary_only
run_id
plan_transaction_id
publication_count
operation_counts
delivery_counts
statuses
digests
stable_error_codes
approvals
side_effects = []
```

Do not include:

```text
raw publications
raw start payloads
raw snapshots
raw delivery plans
raw ack envelopes
raw exception text
raw tool output
raw prompts
raw card JSON
raw media data or paths
raw platform payloads
platform chat/user/message IDs
credentials or connection strings
```

A blocked report should include only safe fields:

```text
type
version
ok = False
verdict = blocked
phase = phase10_controlled_shadow_prototype_loop
error_code
side_effects = []
```

Allowed stable Phase 10 error codes:

```text
invalid_phase9_plan
invalid_run_policy
invalid_publication_fixture
publication_limit_exceeded
delivery_update_limit_exceeded
control_surface_contract_violation
phase7_loop_failed
unsafe_material
side_effects_not_absent
production_action_requested
runtime_lifecycle_requested
registry_or_config_write_requested
artifact_policy_violation
workflow_id_mismatch
```

## Verification Matrix

Successful Phase 10 reports must set all checks true:

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

## Implementation Tasks After Design Approval

### Task 1: Write RED import and surface tests

**Objective:** Prove the Phase 10 module does not exist yet and define import/lifecycle boundaries.

**Files:**

- Create: `tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py`

**Steps:**

1. Add an import test for `flowweaver_runtime_client.controlled_shadow_prototype_loop`.
2. Assert the public constants above.
3. Assert `run_flowweaver_controlled_shadow_prototype_loop` is async.
4. Remove `gateway`, `gateway.run`, `gateway.platforms.feishu`, `temporalio`, `tools.registry`, and related modules from `sys.modules` before import.
5. After import, assert those modules were not imported.
6. Run:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py -q
```

Expected RED: module missing, not `no tests ran`.

### Task 2: Add exact Phase 9 plan fixture and validator tests

**Objective:** Make Phase 10 consume the real Phase 9 output shape exactly.

**Files:**

- Modify: `tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py`

**Steps:**

1. Build a safe Phase 9 plan fixture by calling `build_flowweaver_controlled_shadow_plan(...)` or by copying the exact success shape from the merged implementation.
2. Add negative cases for extra top-level fields, missing fields, wrong verdict, duplicate approvals, missing checks, unsafe artifact policy, workflow/transaction mismatch, mutated `verification_matrix`, reordered `verification_matrix`, missing `verification_matrix` item, mutated `runbook_outline`, reordered `runbook_outline`, missing `runbook_outline` item, incomplete `controlled_shadow_plan.fail_closed_errors`, reordered `controlled_shadow_plan.fail_closed_errors`, duplicate fail-closed error code, and bogus fail-closed error code.
3. Require stable safe error code `invalid_phase9_plan` or `unsafe_material` as appropriate.
4. Run the focused test and confirm these cases fail before implementation.

### Task 3: Add sanitized publication fixture and fake control surface tests

**Objective:** Define the bounded prototype loop behavior without live services.

**Files:**

- Modify: `tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py`

**Steps:**

1. Reuse or copy the safe Phase 7 `RecordingControlSurface` test fixture.
2. Add one safe publication fixture matching Phase 7.
3. Add a safe run policy with `mode = prototype_loop_only`.
4. Assert happy-path output has `controlled_shadow_prototype_loop_verified`, one safe loop result, safe artifact, and `side_effects = []`.
5. Assert no raw publication, raw snapshot, raw start payload, raw ACK envelope, platform ID, or secret-shaped value appears anywhere in the result.
6. Add negative cases for publication count exceeding plan/policy bounds and delivery ACK count exceeding plan/policy bounds.

### Task 4: Implement minimal Phase 10 module

**Objective:** Make RED tests pass with a narrow wrapper over Phase 7.

**Files:**

- Create: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_shadow_prototype_loop.py`

**Implementation constraints:**

- Import only `controlled_shadow_design` constants/helpers if needed and `run_shadow_gateway_e2e_loop` from `gateway_shadow_e2e_loop`.
- Use plain dict/list copies and exact-key validation.
- Call the Phase 7 loop per publication after Phase 9/run-policy validation.
- Summarize Phase 7 results into safe counts, statuses, and digests.
- Never include raw publication, raw start payload, raw snapshot, raw ACK envelope, raw exception text, raw platform identifiers, or secrets in output.
- Catch all unexpected exceptions and return safe stable error codes.

### Task 5: Add runbook and integration allowlist updates

**Objective:** Document Phase 10 without expanding production scope.

**Files:**

- Create: `docs/runbooks/flowweaver-controlled-shadow-prototype-loop.md`
- Modify only existing integration changed-file allowlists if they fail closed on the new Phase 10 files.

Runbook must repeat the hard boundaries and state that Phase 10 proves only a bounded prototype loop, not production activation.

### Task 6: Verification and review

Run focused and regression tests:

```bash
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
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_shadow_prototype_loop.py \
  tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m ruff check \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_shadow_prototype_loop.py \
  tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py

git diff --check
```

Custom gates must scan added lines and new files for:

```text
Gateway production path changes
Temporal client/Worker construction
Docker/systemd/service lifecycle
payload-carrying Signals
config/registry writes
send/edit/render/callback calls
raw prompt/tool/card/media/platform material
platform chat/user/message identifiers
secret-shaped values
```

Run fresh-context Codex review before PR. Any blocker must be fixed by first adding or correcting a RED test, then patching implementation, rerunning verification, and doing blocker-only re-review.

## Design Review Checklist

- [ ] Phase 10 consumes exact Phase 9 success report shape.
- [ ] Phase 10 rejects blocked/wrong/production-like verdicts.
- [ ] Publication fixtures are bounded by plan and policy.
- [ ] Delivery ACK updates are bounded and tied to initialized delivery slots.
- [ ] Control surface is caller-supplied only; no factory/connect/address/task queue path exists.
- [ ] No Gateway production files are touched.
- [ ] No production config or registry writes are introduced.
- [ ] No Temporal client, Worker, WorkflowEnvironment, Docker, daemon, socket, or service startup is introduced.
- [ ] No payload-carrying Temporal Signals are introduced.
- [ ] No real send/edit/render/callback path exists.
- [ ] Reports and artifacts contain only safe summaries.
- [ ] Raw exception text is never logged, returned, or serialized.
- [ ] Integration allowlist updates are narrow and do not weaken safety gates.
- [ ] Docs and dev log pass docs-only gates after final evidence is appended.

## Out of Scope

These require separate later approval:

- Live Gateway observation.
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
docs/plans/2026-05-07-flowweaver-phase10-controlled-shadow-prototype-loop-design.md
docs/dev_log/2026-05-07-flowweaver-phase10-controlled-shadow-prototype-loop-design.md
```

No code, tests, Gateway files, production config, registry files, or service artifacts should change in the design PR.
