# FlowWeaver Phase 5J Activity / Claim-Check Boundary Implementation Plan

> **For Hermes:** User approved Phase 5J execution after Phase 5I merge. This document is the concrete design gate. Do not write implementation code until this plan and dev log are saved, doc-gated, and independently reviewed. If reviewers keep the scope inside this plan, proceed under the user's Phase 5J approval; stop only for scope expansion, production wiring, service lifecycle, destructive cleanup, or security blockers.

**Goal:** Add a prototype-only Temporal Activity / claim-check execution boundary to the FlowWeaver local runtime POC so a real local Worker can call safe stub Activities without leaking raw prompts, tool output, card JSON, platform IDs, or credentials into Workflow history or tool-visible snapshots.

**Architecture:** Keep production Gateway, platform adapters, tool registry, global config, base dependencies, Docker, daemons, and external Temporal services untouched. Phase 5J modifies only the existing Phase 5B/5C prototype boundary: add safe Activity dataclasses and validators, add local stub Activities, make `FlowWeaverTransactionWorkflow` execute those stubs through `workflow.execute_activity(...)`, expose a sanitized `activity_boundary` snapshot summary, and keep the in-memory fake runtime schema-compatible. Activities remain fake/stub only and perform no model/tool/filesystem/network/Gateway effects.

**Tech Stack:** Python, pytest, Temporal Python SDK local test environment, existing Phase 5B workflow/payload contracts, existing Phase 5C runtime facade/sanitizer, Phase 5F/5H/5I reconciliation tests. Temporal remains optional through the existing `flowweaver-temporal` extra only.

---

## Current Baseline

Timestamp: 2026-05-06 22:12:50 CST +0800

Repository state at Phase 5J start:

```text
canonical repo: /home/ubuntu/workspace/hermes/repo/sachima
canonical branch: feature/sachima-channel
canonical HEAD: 37752bc4e0841182677246285f3176c9a18573c2
origin/feature/sachima-channel: 37752bc4e0841182677246285f3176c9a18573c2
Phase 5J worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5j-activity-claim-check-boundary
Phase 5J branch: feat/flowweaver-phase5j-activity-claim-check-boundary
Phase 5J base: origin/feature/sachima-channel @ 37752bc4e0841182677246285f3176c9a18573c2
Phase 5I / PR #35: MERGED
```

Canonical untracked items are pre-existing and not part of Phase 5J:

```text
.hermes/
docs/plans/2026-04-24-sachima-channel.md
docs/superpowers/
```

Baseline verification before Phase 5J code:

```text
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py \
  tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  -q
# 24 passed in 1.39s

scripts/run_tests.sh \
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
# 88 passed in 0.63s
```

Context7 evidence checked before design:

```text
npx ctx7@latest library temporalio "Python SDK workflow execute_activity activity definitions ActivityEnvironment testing"
# selected /temporalio/sdk-python

npx ctx7@latest docs /temporalio/sdk-python "Python SDK execute_activity activity.defn ActivityEnvironment testing workflow history"
# confirmed ActivityEnvironment for activity unit tests, WorkflowEnvironment + Worker for integration tests

npx ctx7@latest docs /temporalio/sdk-python "workflow.execute_activity start_to_close_timeout activity.defn workflow unsafe imports passed through dataclass payloads"
# confirmed workflow.execute_activity(..., start_to_close_timeout=...), @activity.defn, and workflow.unsafe.imports_passed_through() patterns
```

## Why Phase 5J

Phase 5I closed the start-payload/signature leak and duplicate-start parity gaps. The real local Worker can now safely start, query, reconcile, replay ACKs, reject mismatched duplicate starts, and keep raw start policy material out of Temporal history.

The next useful proof is not live Gateway wiring. The next useful proof is the **side-effect boundary**:

```text
Workflow: deterministic state, safe refs, statuses, digests, timers, query snapshots
Activities: future LLM/tool/filesystem/network/Gateway effects
```

Right now the POC has a state machine, but no Activity boundary. That means the project still has not proven how long-running AI work will cross from durable state into side-effecting execution without stuffing raw prompts, tool output, card JSON, media paths, platform payloads, platform IDs, raw delivery ACK payloads, exception text, credentials, or secret-shaped values into Temporal history.

Phase 5J creates the prototype seam for that. Still fake. Still local. Still default-off. But now the seam exists and can be tested.

## Design Decision: Stub Activities Only

Phase 5J should add three Activity stubs:

```text
validate_claim_check_ref
execute_agent_turn
deliver_artifact
```

They are deliberately fake:

- `validate_claim_check_ref` validates an opaque claim-check reference shape and returns a safe validation result.
- `execute_agent_turn` accepts only synthetic IDs and claim refs and returns a safe artifact ref/status. It does not call an LLM, shell, tool, filesystem, or network.
- `deliver_artifact` accepts only synthetic delivery/artifact IDs and claim refs and returns a safe delivery planning/result summary. It does not call Gateway, platform SDKs, send/edit/render, or persist.

The existing `FlowWeaverTransactionWorkflow.run(...)` should execute the stubs after initializing the safe transaction state:

```text
start payload
  -> initialize transaction/intent/artifact/delivery slots
  -> execute validate_claim_check_ref activity with safe ref metadata only
  -> execute execute_agent_turn activity with safe refs only
  -> execute deliver_artifact activity with safe refs only
  -> expose activity_boundary summary in query snapshot
  -> wait for normal updates/cancel
```

The Activity result summary must be derived from safe dataclass fields and must not include raw Activity exception text. Activity validators must reject unsafe values before execution.

## Safe Activity Contract Shape

Naming can adjust during RED tests, but the public prototype surface should stay narrow:

```python
ACTIVITY_BOUNDARY_TYPE = "flowweaver.temporal_poc.activity_boundary.v0"
ACTIVITY_RESULT_TYPE = "flowweaver.temporal_poc.activity_result.v0"

@dataclass(frozen=True)
class ClaimCheckRefValidationInput:
    ref: str
    kind: str
    count: int
    size: int
    checksum_hint: str

@dataclass(frozen=True)
class ClaimCheckRefValidationResult:
    activity_type: str
    ref: str
    kind: str
    status: str
    checksum_hint: str

@dataclass(frozen=True)
class AgentTurnActivityInput:
    event_id: str
    intent_id: str
    input_ref: str
    output_artifact_id: str
    output_artifact_ref: str

@dataclass(frozen=True)
class AgentTurnActivityResult:
    activity_type: str
    event_id: str
    intent_id: str
    artifact_id: str
    artifact_ref: str
    status: str

@dataclass(frozen=True)
class DeliverArtifactActivityInput:
    event_id: str
    artifact_id: str
    artifact_ref: str
    delivery_id: str
    delivery_ref: str
    surface: str

@dataclass(frozen=True)
class DeliverArtifactActivityResult:
    activity_type: str
    event_id: str
    artifact_id: str
    delivery_id: str
    delivery_ref: str
    surface: str
    status: str
```

Allowed strings:

```text
claim ref prefix: claim_ref_
event id prefix: runtime_event_
intent id prefix: runtime_intent_
artifact id prefix: runtime_artifact_
delivery id prefix: runtime_delivery_
surface: progress_card, rich_card, final_text, media, prototype
claim-check kinds: input, artifact, delivery
activity names: validate_claim_check_ref, execute_agent_turn, deliver_artifact
activity boundary statuses: pending, completed, rejected
activity result statuses: validated, completed, planned, rejected
count: exact int, bool rejected, 0 <= count <= 20
size: exact int, bool rejected, 0 <= size <= 1048576
checksum_hint: runtime_sig_ + exactly 64 lowercase sha256 hex
error codes/messages: invalid_activity_input, invalid_activity_result, unsafe_tool_output; never interpolate raw values
```

Temporal history safety rule:

```text
The Workflow must construct Activity inputs only through safe factory/validator helpers and must call validate_*_activity_input(...) immediately before every workflow.execute_activity(...). If validation fails, the Activity is not scheduled. Activity-side validation is defense-in-depth only.

Activities must validate/sanitize their result dataclass before returning, because Activity results are also recorded in Temporal history. Workflow-side validation after Activity completion is useful for state integrity, but it is too late to prevent Activity result payload leaks.
```

The Workflow snapshot should add a deterministic safe summary:

```python
"activity_boundary": {
    "type": ACTIVITY_BOUNDARY_TYPE,
    "version": FLOWWEAVER_TEMPORAL_POC_VERSION,
    "status": "completed",
    "activities": {
        "validate_claim_check_ref": "validated",
        "execute_agent_turn": "completed",
        "deliver_artifact": "planned",
    },
    "refs": {
        "input_ref": "claim_ref_phase5j_start",
        "artifact_ref": "claim_ref_phase5j_artifact_0",
        "delivery_ref": "claim_ref_phase5j_delivery_0",
    },
    "side_effects": [],
}
```

The exact ref suffixes may change, but they must stay synthetic, deterministic, and raw-material-free.

The sanitizer contract for `activity_boundary` is exact-shape:

```text
required keys exactly: type, version, status, activities, refs, side_effects
type: flowweaver.temporal_poc.activity_boundary.v0
version: flowweaver.temporal_poc.v0
status: pending, completed, or rejected
activities keys exactly: validate_claim_check_ref, execute_agent_turn, deliver_artifact
activity values: pending, validated, completed, planned, or rejected according to the documented activity
refs keys exactly: input_ref, artifact_ref, delivery_ref
refs: claim_ref_ values only
side_effects: [] exactly
unknown nested keys: reject, do not strip-and-pass
rendered sanitized snapshot: must omit raw prompt/tool/card/media/platform/private/credential-shaped material
```

Lifecycle rule:

```text
Initialize a safe pending activity_boundary before the first Activity await, so queries and duplicate-start recovery have a schema-compatible safe snapshot even while Activities are still pending. Existing query helpers should wait for activity_boundary.status == completed when a test needs post-Activity proof; duplicate-start recovery may accept pending or completed as long as the start signature and other observable fields match.
```

## Scope Boundary

### In scope

1. Add Phase 5B safe Activity payload/result dataclasses and validators.
2. Add Phase 5B local stub Activities with `@activity.defn`.
3. Update `FlowWeaverTransactionWorkflow` to import Activities through `workflow.unsafe.imports_passed_through()` and call them with `workflow.execute_activity(...)` plus explicit timeouts.
4. Store a safe `activity_boundary` summary in the workflow state and query/update snapshots.
5. Update Phase 5C snapshot sanitizer/result shape to accept and validate the safe `activity_boundary` only.
6. Update Phase 5F in-memory fake runtime snapshot to expose schema-compatible `activity_boundary` without starting workers or services.
7. Update existing Phase 5B/5C/5H/5I integration tests so Workers register the new stub Activities.
8. Add RED tests proving Activity contracts are absent before implementation.
9. Add history no-leak tests for Activity inputs/results and snapshot output.
10. Add source/diff gates preventing production wiring, real side effects, logging leaks, payload-carrying Signals, base dependency changes, and service lifecycle changes.
11. Update docs/dev log and run focused gates + independent reviews before commit/PR.

### Out of scope

Phase 5J does **not** approve:

```text
gateway/run.py changes
gateway/platforms/** changes
run_agent.py changes
model_tools.py changes
toolsets.py changes
tools/** changes
hermes_cli/** changes
production Hermes tool registration
MCP/global registry changes
production Gateway service restart
production Gateway -> Temporal wiring
Docker / Temporal CLI / daemon / external Temporal service startup
~/.hermes/config.yaml writes
base dependency changes that install temporalio outside optional extras
payload-carrying Signals
real LLM/tool/shell/filesystem/network calls inside Activities
Gateway send/edit/render calls inside Activities
raw exception text in returned results, snapshots, logs, or docs
remote branch deletion
PR merge
```

## Planned Files

Create:

```text
docs/plans/2026-05-06-flowweaver-phase5j-activity-claim-check-boundary.md
docs/dev_log/2026-05-06-flowweaver-phase5j-activity-claim-check-boundary.md
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/activities.py
tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py
tests/prototypes/test_flowweaver_phase5j_activity_contract.py
```

Modify:

```text
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py
tests/integration/test_flowweaver_phase5b_temporal_workflow.py
tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py
tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
tests/integration/test_flowweaver_phase5i_start_signature_parity.py
tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py
tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py
```

Potential test-only maintenance if direct snapshot shapes or allowlists require it:

```text
tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py
tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py
```

## TDD Task Plan

### Task 1: RED — Activity contract module is absent

**Objective:** Define safe Activity payload/result contracts before implementation.

**Files:**

- Create: `tests/prototypes/test_flowweaver_phase5j_activity_contract.py`

Tests to add before implementation:

```text
test_phase5j_activity_contract_defines_safe_stub_inputs_results_and_summary
test_phase5j_activity_contract_rejects_raw_prompt_tool_output_card_json_platform_ids_and_secret_values
test_phase5j_activity_contract_rejects_invalid_kind_activity_type_count_and_size_values
test_phase5j_activity_contract_requires_runtime_sig_digest_for_checksum_hint
test_phase5j_activity_contract_rejects_unknown_nested_activity_boundary_fields
test_phase5j_activity_summary_is_schema_compatible_with_snapshot_sanitizer
```

Expected RED before implementation:

```text
ImportError or AttributeError: Phase 5J activity dataclasses/validators do not exist.
```

RED command:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5j_activity_contract.py -q
```

Do not count syntax errors, no tests collected, or fixture failures as valid RED.

### Task 2: GREEN — Add minimal Activity payload/result validators

**Objective:** Add only the dataclasses and validators required by Task 1.

**Files:**

- Modify: `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py`
- Modify: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py`

Implementation rules:

1. Reuse existing `_synthetic_id`, `_claim_ref`, `_optional_claim_ref`, `_closed_string`, and `validate_runtime_signature_digest` patterns.
2. Use exact primitive types, not `str` subclasses or hostile mappings.
3. Reject any rendered result containing raw markers such as raw prompt, raw command/stdout/stderr/tool output, card JSON, media path/bytes, platform payloads, platform/chat/user/message identifiers, credential-shaped strings, and forbidden policy marker smuggling.
4. Add `activity_boundary` snapshot sanitizer support in Phase 5C only after prototype tests prove the desired shape.

GREEN command:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5j_activity_contract.py -q
python -m py_compile \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py \
  tests/prototypes/test_flowweaver_phase5j_activity_contract.py
```

### Task 3: RED — Stub Activities and Workflow execution boundary are absent

**Objective:** Prove the current real local Worker does not yet call stub Activities or expose an `activity_boundary` snapshot.

**Files:**

- Create: `tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py`
- Modify: `tests/integration/test_flowweaver_phase5b_temporal_workflow.py` only if a source gate must be updated for Phase 5J activity scheduling.

Tests to add before implementation:

```text
test_phase5j_real_worker_executes_stub_activity_boundary_and_exposes_safe_snapshot_summary
test_phase5j_real_worker_history_omits_raw_activity_material_after_activity_boundary_and_cancel
test_phase5j_activity_input_validators_reject_raw_markers_before_scheduling
# contract/source proof for pre-schedule validation; no raw marker is intentionally scheduled into history
test_phase5j_workflow_source_uses_execute_activity_but_not_gateway_tools_filesystem_network_or_logging
test_phase5j_workflow_source_validates_activity_inputs_immediately_before_execute_activity
```

Expected RED before implementation:

```text
activity_boundary missing from snapshot, activity module missing, or Worker cannot register Phase 5J activities.
```

RED command:

```bash
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py -q
```

### Task 4: GREEN — Add local stub Activities and call them from Workflow

**Objective:** Execute fake Activity stubs from the workflow and expose safe activity-boundary state.

**Files:**

- Create: `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/activities.py`
- Modify: `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py`
- Modify: existing integration Worker fixtures to register the new Activities.

Implementation rules:

1. `activities.py` may import `temporalio.activity` and Phase 5B payload validators only.
2. `activities.py` must not import Gateway, platform adapters, tools, runtime client, subprocess, socket, requests/httpx/aiohttp, pathlib, logging, or config modules.
3. Workflow imports Activities via `with workflow.unsafe.imports_passed_through():`.
4. Workflow calls each Activity with explicit `start_to_close_timeout`.
5. Workflow validates every Activity input immediately before scheduling. The source gate must prove each `workflow.execute_activity(...)` argument was produced by an approved safe factory/validator helper.
6. Activities validate their input again on entry and validate/sanitize their result before returning.
7. Workflow catches no raw Activity exception text into snapshots/results; validator failures should surface as safe test failures, not user-visible raw payload echoes.
8. The new snapshot field must be deterministic and schema-compatible between real Worker and fake runtime.
9. All existing Phase 5B/5C/5H/5I Worker constructions must register the three stub Activities in `activities=[validate_claim_check_ref, execute_agent_turn, deliver_artifact]`.

GREEN command:

```bash
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py -q
python -m py_compile \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/activities.py \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py
```

### Task 5: RED/GREEN — Fake/real snapshot parity and existing regression maintenance

**Objective:** Keep Phase 5F fake runtime and Phase 5H/5I real runtime semantics aligned after adding `activity_boundary`.

**Files:**

- Modify: `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py`
- Modify: `tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py`
- Modify: `tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py`
- Modify: `tests/integration/test_flowweaver_phase5i_start_signature_parity.py`

Tests to add/update:

```text
test_phase5f_fake_runtime_snapshot_includes_phase5j_activity_boundary_summary
test_phase5h_reconciles_gateway_shadow_publication_through_real_temporal_worker includes activity_boundary parity
test_phase5i matching duplicate/replay still passes with activity_boundary present
```

Commands:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py -q
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py \
  -q
```

### Task 6: Static/security source gates

**Objective:** Prove Phase 5J did not sneak in production wiring, real side effects, base dependency changes, unsafe logging, payload-carrying Signals, or raw material leaks.

**Files:**

- Add source/diff gate in `tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py`.

Gate requirements:

1. Changed files must be exactly the approved Phase 5J files, plus explicitly listed test maintenance if needed.
2. No changes to `pyproject.toml`, `gateway/run.py`, `gateway/platforms/**`, `run_agent.py`, `model_tools.py`, `toolsets.py`, `tools/**`, `hermes_cli/**`, or `~/.hermes/config.yaml`.
3. No base dependency addition for `temporalio`; existing optional extras remain unchanged.
4. No `@workflow.signal`, `.signal(`, `signal_with_start`, payload-carrying Signal pattern, Docker/systemctl/daemon/service startup, Gateway restart, platform adapter imports, tool registry imports, global MCP registry writes, subprocess/socket/HTTP listener startup, or config writes.
5. Activity source must have no model calls, tool calls, shell execution, filesystem/network IO, Gateway send/edit/render, logging/print, raw exception interpolation, or raw payload serialization.
6. Workflow source may contain `workflow.execute_activity` only for the approved stub Activities.
7. Added lines and final candidate files must not contain credential-shaped values or private platform IDs. Synthetic negative-test strings must be split to avoid poisoning secret scans.

Commands:

```bash
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py::test_phase5j_diff_does_not_add_gateway_wiring_or_real_activity_side_effects \
  -q
git diff --check
```

## Verification Plan Before Commit

Focused integration regression:

```bash
TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py \
  tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  -q
```

Prototype regression:

```bash
scripts/run_tests.sh \
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

Static gates:

```bash
python -m py_compile \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/activities.py \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py \
  tests/prototypes/test_flowweaver_phase5j_activity_contract.py
python -m ruff check \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/activities.py \
  prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/reconciliation_harness.py \
  prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py \
  tests/prototypes/test_flowweaver_phase5j_activity_contract.py
git diff --check
```

Custom security gates:

```text
changed-file allowlist
forbidden production/runtime surface scan
no base dependency change
no payload-carrying Signals
Activity source no real side effects
Workflow source only approved execute_activity calls
history no-leak raw bytes scan
result/snapshot/log no raw exception text or forbidden material
secret-shaped added-line/final-candidate scan
```

Independent reviews before commit:

```text
implementation/spec/TDD review: required
security/low-intrusion/no-leak review: required
Temporal Activity boundary review: required
```

## Acceptance Criteria

Phase 5J is complete only if:

1. Stub Activity payload/result validators reject raw prompts, tool outputs, card JSON, media paths/bytes, platform payloads, platform/chat/user/message IDs, raw delivery ACK payloads, credentials, and secret-shaped values.
2. A real local Temporal Worker executes the three stub Activities and query snapshots expose only safe `activity_boundary` fields.
3. Temporal history rendered JSON and serialized event bytes omit raw Activity material and forbidden sentinels after start/activity execution/cancel.
4. Fake runtime snapshots and real runtime snapshots expose schema-compatible `activity_boundary` summaries through the Phase 5C sanitizer.
5. Existing Phase 5H/5I duplicate-start/replay/reconciliation behavior stays green.
6. No production Gateway, platform adapter, tool registry, global config, base dependency, Docker, daemon, external service, or Gateway restart code is touched.
7. All focused/regression/static/security gates and independent reviews pass.

## Handoff

This plan keeps Phase 5J strictly prototype-only/default-off and makes the next durable runtime proof about Activity/claim-check boundaries, not live Gateway wiring. Under the user's Phase 5J execution approval, implementation may proceed after this plan/dev log pass doc gates and blocker-only plan reviews.
