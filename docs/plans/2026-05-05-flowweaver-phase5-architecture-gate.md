# FlowWeaver Phase 5 Architecture Gate Plan

> **For Hermes:** This is a design-gate plan only. Do not write implementation code until the user explicitly approves the next execution gate.

**Goal:** Decide the safe durable-orchestration landing path after Phase 4A-4H, and define how FlowWeaver can move toward durable runtime / Temporal without changing production IM behavior by accident.

**Architecture:** Phase 5 is an architecture gate, not a runtime integration. It summarizes the verified Gateway shadow evidence, selects the next low-intrusion implementation seam, and keeps Temporal behind a later prototype boundary. The recommended path is contract-first: define a pure durable runtime ingress envelope from already-safe shadow/corpus/mock-durable outputs before starting any worker, service, or Gateway-to-Temporal wiring.

**Tech Stack:** Python, pytest, existing Gateway FlowWeaver helpers, Temporal Python SDK / Temporal docs checked through Context7, GitHub PR review.

---

## Current Context / Evidence

Timestamp: 2026-05-05 11:48:13 CST +0800

Branch/worktree:

```text
repo: /home/ubuntu/workspace/hermes/repo/sachima
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5-architecture-gate
branch: feat/flowweaver-phase5-architecture-gate
base: origin/feature/sachima-channel @ de1ed6b85206cbcaa6ff223ef7fce764669b915a
open PRs on base before branching: []
canonical before branching: feature/sachima-channel, local untracked docs/.hermes items left untouched
```

Baseline verification in the Phase 5 worktree:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_shadow_dry_run.py \
  tests/gateway/test_flowweaver_mock_durable_consumer.py \
  tests/gateway/test_flowweaver_shadow_tap.py \
  tests/gateway/test_flowweaver_contract_adapter.py \
  tests/gateway/test_delivery_state.py \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/test_rich_weather_delivery.py \
  -q
```

Observed:

```text
142 passed in 18.32s
```

Context inspected:

```text
AGENTS.md
docs/plans/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md
docs/dev_log/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md
gateway/flowweaver_contract.py
gateway/flowweaver_shadow.py
gateway/flowweaver_mock_durable.py
gateway/flowweaver_shadow_dry_run.py
gateway/progress/events.py
gateway/progress/store.py
gateway/run.py shadow capture seam
Temporal Python SDK docs via Context7: /temporalio/sdk-python
Temporal docs via Context7: /temporalio/documentation
```

Important current seam evidence:

```text
gateway/run.py
  display.task_tracker.flowweaver_shadow remains default-off
  display.task_tracker.flowweaver_shadow_dry_run remains default-off and requires flowweaver_shadow
  progress_tracking_enabled can create an internal tracker for shadow capture without visible progress queue
  attach_flowweaver_shadow_snapshot(...) runs only near the final response return path
  attach_flowweaver_gateway_shadow_dry_run(...) runs only after shadow capture and only when both gates are true

gateway/flowweaver_shadow.py
  produces sanitized flowweaver.v0 shadow snapshot/capture
  exposes descriptor/audit/replay/corpus helpers
  forbids send/edit/render/persist/temporal/log side effects in consumer contract

gateway/flowweaver_mock_durable.py
  consumes only safe descriptor + safe replay corpus
  produces synthetic Transaction / Intent / Artifact / Delivery record shapes
  does not read raw snapshot/capture/agent_result/platform payloads

gateway/flowweaver_shadow_dry_run.py
  chains descriptor + replay corpus + mock durable projection inside Gateway lifecycle
  attaches only narrow safe verdict/count/check summary to agent_result
  does not attach full mock durable records
```

Phase 4A-4H evidence matrix:

| Phase | Status | Evidence for Phase 5 |
|---|---:|---|
| 4A Gateway contract seam | merged | sanitized `flowweaver.handle.v0` snapshot exists as pure helper |
| 4B default-off shadow tap | merged | Gateway can collect shadow material without visible behavior change |
| 4C snapshot lifecycle / safe capture | merged | consumer sees `snapshot_ref + capture`, not full raw Gateway state |
| 4D audit harness | merged | no-send/no-edit/no-render/no-persist/no-log invariants can be asserted |
| 4E replay probe | merged | capture can be read repeatedly and drift-detected safely |
| 4F consumer descriptor + corpus | merged | future consumers have explicit allowed inputs and forbidden outputs |
| 4G mock durable consumer | merged | safe corpus can project into durable record shapes in memory |
| 4H Gateway shadow dry-run | merged | Gateway lifecycle can run the safe consumer chain with no visible side effects |

---

## Phase 5 Gate Verdict

**Recommendation:** Do not connect Temporal directly to the live Gateway yet. That would be the tempting move, and it would be a trap.

The next executable phase should be **Phase 5A: Durable Runtime Ingress Contract**, a pure local contract/envelope helper that consumes only already-safe Phase 4F/4G/4H outputs and states exactly what a future runtime is allowed to persist, query, signal, or deliver.

Temporal should enter after Phase 5A as a **local prototype boundary**, not as production Gateway wiring:

```text
Phase 5A: durable runtime ingress contract, pure helper, no Temporal import
Phase 5B: local Temporal POC under prototypes/, no Gateway wiring, no service auto-start
Phase 5C: narrow native tool or MCP-facing runtime client, still default-off
Phase 5D: Gateway shadow publisher / ACK bridge, default-off and no visible behavior change
```

This keeps the order sane:

```text
contract clarity -> pure local projection -> Temporal POC -> tool/MCP client -> Gateway wiring
```

Not this cursed shortcut:

```text
Gateway -> Temporal -> find out later what state meant
```

---

## Durable Architecture Decisions

### Decision 1: Keep Gateway out of orchestration ownership

Gateway owns:

```text
platform ingress
safe progress capture
rendering / delivery surfaces
platform delivery ACK observation
final text / media / rich-card send state
```

FlowWeaver runtime owns:

```text
Transaction state
Intent ordering and dependencies
Operation lifecycle
Artifact availability
Delivery plans and delivery outcomes
approval / cancellation / resume state
```

Gateway may report facts to the runtime, but it should not become the workflow engine.

### Decision 2: Treat Temporal as runtime implementation, not the public contract

The public internal contract should remain FlowWeaver-shaped:

```text
Transaction
Intent
Operation
Artifact
Delivery
```

Temporal is an implementation option for durable execution. If the project later swaps the runtime or keeps a local runtime for some flows, Gateway and tests should not care.

### Decision 3: Workflow code is deterministic state; Activities own side effects

Temporal design boundary, when Phase 5B starts:

```text
Workflow:
  deterministic transaction state machine
  intent dependency state
  durable timers
  cancellation / approval waiting
  queryable progress snapshots
  signal/update handlers for approval, cancellation, delivery ACK

Activities:
  agent turn execution
  tool execution
  filesystem / network / model calls
  Gateway delivery calls
  platform ACK writes
```

No LLM call, shell command, filesystem write, platform send, or Gateway adapter call belongs inside Workflow code.

### Decision 4: Only claim-check references may cross durable boundaries

Temporal event history must not receive raw prompts, raw tool stdout/stderr, card JSON, media bytes, platform IDs, delivery ACK payloads, or secrets. Large or sensitive material must be kept outside the durable boundary; only opaque sanitized claim-check references plus safe metadata may appear in any signal/update/start payload that reaches a Workflow.

Phase 5A should therefore distinguish:

```text
safe durable envelope fields: synthetic ids, statuses, counts, versions, summaries, checks, sanitized refs
claim-check-reference-only fields: opaque sanitized refs plus non-sensitive kind/count/size/check metadata
forbidden material: raw snapshot/capture/full agent_result, raw prompts, raw command/stdout/stderr/tool outputs, card JSON, media bytes/paths, platform payloads, platform/chat/user/message IDs, raw delivery ACK payloads/IDs, credentials, tokens, secrets
```

### Decision 5: Runtime IDs must be synthetic and idempotent

The future runtime envelope must carry only safe deterministic IDs and idempotency keys derived from sanitized refs/indexes, not platform IDs.

Good:

```text
tx_<safe_ref>
intent_0
artifact_0
delivery_final_text_0
```

Bad:

```text
om_...
ou_...
oc_...
chat_...
message_...
raw Gateway session IDs
```

### Decision 6: Human-in-the-loop must be explicit

Approvals, cancellations, and resume events should map to Temporal Signals or Updates later. Phase 5A should define the abstract event names first, for example:

```text
approve_intent
reject_intent
cancel_transaction
record_delivery_ack
resume_after_user_input
```

Whether those become Temporal Signals or Updates is a Phase 5B implementation choice, but the contract should already make them explicit and idempotent.

---

## Phase 5A Proposed Implementation Gate

This section is not approval to implement. It is the proposed next execution gate after this architecture plan is reviewed.

### Goal

Create a pure, in-memory durable runtime ingress contract helper that validates Phase 4F/4G/4H safe outputs and returns a versioned envelope a future runtime may consume.

### Allowed files after explicit Phase 5A approval

```text
docs/plans/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md
docs/dev_log/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md
gateway/flowweaver_runtime_contract.py
tests/gateway/test_flowweaver_runtime_contract.py
tests/gateway/test_run_progress_topics.py  # only if a Gateway lifecycle regression is needed, not runtime wiring
```

### Still forbidden in Phase 5A

```text
no Temporal imports
no Temporal service / worker / client
no Docker
no daemon or service startup
no Gateway restart
no live Gateway runtime wiring
no platform adapter changes
no public flowweaver.v0 schema mutation
no run_agent.py / model_tools.py / toolsets.py / cli.py / hermes_cli changes
no send / edit / render / persist / log calls
no remote branch deletion
```

### Candidate public surface

Naming can change during RED tests, but the shape should be this narrow:

```python
FLOWWEAVER_RUNTIME_CONTRACT_TYPE = "flowweaver.gateway.runtime_ingress_contract.v0"
FLOWWEAVER_RUNTIME_ENVELOPE_TYPE = "flowweaver.gateway.runtime_ingress_envelope.v0"
FLOWWEAVER_RUNTIME_ACCEPTED = "accepted"
FLOWWEAVER_RUNTIME_REJECTED = "rejected"

def describe_flowweaver_runtime_ingress_contract() -> dict[str, object]: ...

def build_flowweaver_runtime_ingress_envelope(
    contract_descriptor: Mapping[str, object],
    replay_corpus: Mapping[str, object],
    mock_durable_projection: Mapping[str, object],
    dry_run_summary: Mapping[str, object] | None = None,
) -> dict[str, object]: ...
```

Accepted inputs:

```text
describe_flowweaver_shadow_consumer_contract() output
replay_flowweaver_shadow_corpus(...) output
consume_flowweaver_shadow_corpus_as_mock_durable_state(...) output
run_flowweaver_gateway_shadow_dry_run(...) output, optional and summary-only
```

Rejected inputs:

```text
full FlowWeaver snapshots
shadow capture mappings
agent_result mappings
Gateway source/event/platform adapter objects
raw user/tool payload objects
Temporal client/workflow handles
platform delivery ACK payloads
any hostile Mapping / post-validation re-read trick
```

Envelope output should include only:

```text
type / contract_version / verdict / reason
runtime_model_version
entry_count
safe transaction/intent/artifact/delivery record counts
allowed_runtime_events
required_claim_checks
idempotency_key strategy
checks
side_effects: []
```

It must not include full mock durable records unless the test proves they are synthetic-only and exact-shape safe. Start narrower: counts + event schema first.

---

## TDD Task Plan for Phase 5A After Approval

### Task 0: Persist Phase 5A plan and dev log

**Objective:** Record the approved Phase 5A design and baseline before code.

**Files:**

- Create: `docs/plans/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md`
- Create: `docs/dev_log/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md`

**Verification:**

```bash
git check-ignore -v \
  docs/plans/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md \
  docs/dev_log/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md \
  gateway/flowweaver_runtime_contract.py \
  tests/gateway/test_flowweaver_runtime_contract.py || true
git add -N docs/plans/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md docs/dev_log/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md
git diff --check -- docs/plans/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md docs/dev_log/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md
```

### Task 1: RED — runtime ingress contract helper is absent

**Objective:** Define the contract descriptor and accepted envelope before implementation.

**Files:**

- Create: `tests/gateway/test_flowweaver_runtime_contract.py`

**Tests to add before implementation:**

```text
test_runtime_ingress_contract_describes_allowed_inputs_and_forbidden_side_effects
test_runtime_ingress_envelope_accepts_descriptor_corpus_mock_projection_and_dry_run_summary
test_runtime_ingress_envelope_projects_counts_events_and_claim_check_requirements_only
```

**Expected RED:**

```text
ModuleNotFoundError: No module named 'gateway.flowweaver_runtime_contract'
```

**RED command:**

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_runtime_contract.py::test_runtime_ingress_contract_describes_allowed_inputs_and_forbidden_side_effects \
  tests/gateway/test_flowweaver_runtime_contract.py::test_runtime_ingress_envelope_accepts_descriptor_corpus_mock_projection_and_dry_run_summary \
  tests/gateway/test_flowweaver_runtime_contract.py::test_runtime_ingress_envelope_projects_counts_events_and_claim_check_requirements_only \
  -q
```

### Task 2: GREEN — implement minimal pure runtime contract helper

**Objective:** Add the smallest helper that validates Phase 4F/4G/4H safe outputs and returns a narrow envelope.

**Files:**

- Create: `gateway/flowweaver_runtime_contract.py`

**Implementation rules:**

1. Import only safe constants/helpers from `gateway.flowweaver_shadow`, `gateway.flowweaver_mock_durable`, and `gateway.flowweaver_shadow_dry_run`.
2. Accept only exact plain dict inputs where exact-shape validation is required.
3. Derive output from safe verdicts, versions, counts, and fixed event schemas only.
4. Do not read `agent_result`, raw snapshot, raw capture, source/event objects, platform adapters, or Temporal handles.
5. Do not send, edit, render, persist, log, start services, or import Temporal.

**GREEN command:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_runtime_contract.py -q
python -m py_compile gateway/flowweaver_runtime_contract.py tests/gateway/test_flowweaver_runtime_contract.py
```

### Task 3: RED/GREEN — rejection and no-leak hardening

**Objective:** Fail closed for unsafe input without echoing hostile values.

**Files:**

- Modify: `tests/gateway/test_flowweaver_runtime_contract.py`
- Modify: `gateway/flowweaver_runtime_contract.py`

**Tests to add before implementation:**

```text
test_runtime_ingress_rejects_raw_snapshot_capture_or_agent_result_without_echoing_values
test_runtime_ingress_rejects_temporal_client_like_objects
test_runtime_ingress_rejects_platform_ack_payloads_and_private_ids
test_runtime_ingress_rejects_hostile_mapping_and_mutating_keys
test_runtime_ingress_rejects_post_validation_reread_attacks
test_runtime_ingress_output_omits_raw_command_stdout_card_json_and_secrets
test_runtime_ingress_side_effects_are_always_empty
```

**GREEN command:**

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_runtime_contract.py -q
python -m py_compile gateway/flowweaver_runtime_contract.py tests/gateway/test_flowweaver_runtime_contract.py
```

### Task 4: RED/GREEN — Gateway lifecycle regression without runtime wiring

**Objective:** Prove the accepted runtime envelope can be built from a fake-agent Gateway shadow dry-run output in tests without changing Gateway behavior.

**Files:**

- Modify: `tests/gateway/test_run_progress_topics.py`

**Test to add before implementation:**

```text
test_flowweaver_runtime_ingress_contract_can_consume_gateway_shadow_dry_run_without_visible_side_effects
```

**Expected assertions:**

```text
adapter.sent == [] when tool_progress=off and task_tracker.enabled=false
adapter.edits == [] when tool_progress=off and task_tracker.enabled=false
no cards_sent/cards_patched in Feishu card mode when task tracker disabled
envelope["verdict"] == "accepted"
envelope["side_effects"] == []
no raw snapshot/capture/platform/message identifiers in envelope repr
```

**GREEN command:**

```bash
scripts/run_tests.sh \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_runtime_ingress_contract_can_consume_gateway_shadow_dry_run_without_visible_side_effects \
  -q
python -m py_compile tests/gateway/test_run_progress_topics.py
```

### Task 5: Focused gate, scans, and independent reviews

**Objective:** Prove Phase 5A remains contract-only and safe before PR.

**Commands:**

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_runtime_contract.py \
  tests/gateway/test_flowweaver_shadow_dry_run.py \
  tests/gateway/test_flowweaver_mock_durable_consumer.py \
  tests/gateway/test_flowweaver_shadow_tap.py \
  tests/gateway/test_flowweaver_contract_adapter.py \
  tests/gateway/test_delivery_state.py \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/test_rich_weather_delivery.py \
  -q
python -m py_compile \
  gateway/flowweaver_runtime_contract.py \
  gateway/flowweaver_shadow_dry_run.py \
  gateway/flowweaver_mock_durable.py \
  gateway/flowweaver_shadow.py \
  tests/gateway/test_flowweaver_runtime_contract.py \
  tests/gateway/test_flowweaver_shadow_dry_run.py \
  tests/gateway/test_flowweaver_mock_durable_consumer.py \
  tests/gateway/test_run_progress_topics.py
git diff --check
```

Additional scans before commit/PR:

```text
forbidden path scan: no run_agent.py, model_tools.py, toolsets.py, cli.py, hermes_cli, gateway/platforms
Temporal scan: no temporalio import, no Client.connect, no Workflow/Worker in production files
service scan: no Docker, no daemon, no service-manager commands, no Gateway restart
side-effect scan: no send/edit/render/persist/log calls in runtime contract helper
sensitive scan: no credential-shaped values or private platform IDs in added lines
ignored-file scan: planned files are not ignored
```

Independent reviews after code is written:

```text
spec / low-intrusion review: required
security / no-leak review: required
Temporal boundary review: required before any Phase 5B prototype
```

---

## Phase 5B Temporal POC Gate — Not Yet Approved

Phase 5B should be a prototype-only PR, probably under:

```text
prototypes/flowweaver_phase5_temporal_poc/
```

It should not touch Gateway runtime wiring.

The POC should model:

```text
FlowWeaverTransactionWorkflow.run(envelope)
Query: get_snapshot
Signal or Update: record_delivery_ack
Signal or Update: approve_intent / reject_intent
Signal: cancel_transaction
Activity stubs: execute_agent_turn, deliver_artifact, validate_claim_check_ref
```

Temporal rules to verify before Phase 5B implementation:

```text
Workflow code is deterministic and side-effect-free
Activities contain network/filesystem/model/Gateway effects
Signals/Updates carry already-sanitized envelopes or claim-check references only
Queries return safe progress snapshots only
Event history size is bounded; Continue-As-New strategy exists for long flows
Replay tests exist before changing workflow definitions
```

---

## Approval Gate

This document approves only the Phase 5 architecture-gate documentation work.

After this plan is reviewed, the next code-bearing step is **Phase 5A Durable Runtime Ingress Contract**, but it must wait for explicit user approval. No Temporal, no worker, no service, no Gateway runtime wiring, and no platform adapter changes should be implemented from this plan alone.
