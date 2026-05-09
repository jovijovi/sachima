# FlowWeaver Phase 29–33 Activity Execution Roadmap Implementation Plan

> **For Hermes:** Use subagent-driven-development for each implementation phase only after 狗哥 explicitly approves that phase. This roadmap is docs-only. Do not treat this document as approval to implement code, enable production behavior, write config, restart Gateway, mutate platform adapters, run Temporal services, deliver real messages, or execute real agent/tools.

**Goal:** Convert Phase 28's `ready_for_separately_approved_stub_activity_implementation` verdict into a compressed, behavior-bearing execution path for FlowWeaver Activities.

**Architecture:** Phase 29 implements and validates plain non-production callable stub functions. Phase 30 wraps those stubs in a local Temporal Activity orchestration harness. Phase 31 adds controlled agent/tool execution behind claim-check and executor boundaries. Phase 32 adds controlled artifact delivery and ACK reconciliation behind injected delivery surfaces. Phase 33 runs a narrow AI FLOW pilot and produces the production-enablement decision packet.

**Tech Stack:** Python, pytest, existing FlowWeaver Gateway contract modules, Temporal Python SDK only in phases that explicitly allow local/staging Temporal runtime behavior, existing GitHub PR/CI gates.

---

## Baseline

```text
Repository: jovijovi/sachima
Base branch: feature/sachima-channel
Base HEAD when roadmap was drafted: aedd0d8978b5e5cd039b9270a0bea3850bcad733
Latest completed phase: Phase 28 — stub Activity implementation validation
Roadmap document: docs/plans/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md
Roadmap dev log: docs/dev_log/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md
```

Current Phase 28 verdict:

```text
ready_for_separately_approved_stub_activity_implementation
```

This means Phase 29 may request separate approval to implement non-production stub Activity functions. It does not approve Temporal SDK wiring, Worker lifecycle, real agent/tool execution, Gateway delivery, ACK control, production config writes, service lifecycle, Gateway restart, or production behavior.

## Compression Decision

The seven work areas discussed after Phase 28 are not seven separate gates. Treating them that way would recreate pure-report inertia.

Compress them into five approval phases:

```text
Phase 29: non-production callable stub Activities, including their validation.
Phase 30: local Temporal orchestration of those stub Activities.
Phase 31: controlled agent/tool execution Activity.
Phase 32: controlled artifact delivery and ACK Activity.
Phase 33: narrow AI FLOW pilot and production-enablement decision packet.
```

Mapping from the seven work areas:

```text
stub implementation + stub validation                -> Phase 29
Temporal Activity wrapper + local Worker parity       -> Phase 30
real agent/tool execution boundary                    -> Phase 31
artifact delivery + ACK reconciliation                -> Phase 32
production-shadow enablement + end-to-end AI FLOW use -> Phase 33
```

After Phase 28, avoid new pure report-only phases unless a concrete blocker appears, such as missing no-leak coverage, unsafe runtime ownership, unclear side-effect authority, unresolved delivery semantics, or a prior contract mismatch.

## Global Boundaries for All Five Phases

All phases require separate, explicit approval before implementation.

Unless 狗哥 gives separate approval naming the action, the roadmap does not approve:

- production config writes;
- Gateway restart or reload;
- Gateway-owned Temporal Worker, service, daemon, Docker, or test-server lifecycle;
- platform adapter mutation;
- production-shadow enablement;
- production send/edit/render/callback behavior;
- Temporal-backed production delivery control;
- Temporal-backed production agent/tool execution;
- deletion of remote branches;
- raw prompt, message text, tool output, card JSON, media path, platform/private id, callback payload, credential value, or raw exception text in Temporal history, snapshots, logs, reports, fixtures, docs evidence, or user-visible output.

Gateway may learn how to observe, call safe Activities, and report sanitized state. It must not silently gain authority over live delivery or production agent execution.

## Approval Matrix

| Phase | Behavior-bearing? | Requires Temporal runtime? | Real agent/tools? | Real delivery? | Strongest allowed verdict |
|---|---:|---:|---:|---:|---|
| 29 | yes, plain callable stubs | no | no | no | `ready_for_local_temporal_stub_activity_orchestration` |
| 30 | yes, local/staging stub Activity orchestration | local/staging only | no | no | `ready_for_controlled_agent_activity_implementation_request` |
| 31 | yes, controlled agent/tool execution | local/staging only | controlled non-production only | no | `ready_for_controlled_delivery_activity_request` |
| 32 | yes, controlled delivery/ACK | local/staging only | no new agent scope | controlled non-production/staging only | `ready_for_narrow_ai_flow_pilot_request` |
| 33 | yes, narrow AI FLOW pilot | staging or explicitly approved shadow only | only as approved by Phase 31 evidence | only as approved by Phase 32 evidence | `ready_for_separate_production_enablement_decision` |

`ready_for_separate_production_enablement_decision` is still weaker than any production-live, default-on, or broad enablement verdict.

---

## Phase 29 — Non-Production Stub Activity Implementation

### Objective

Implement the three future Activity units as ordinary callable Python functions with fake/non-production behavior and strict sanitized contracts.

### Strongest Allowed Verdict

```text
ready_for_local_temporal_stub_activity_orchestration
```

This means Phase 30 may request approval to wrap the stubs in local Temporal Activity orchestration. It does not approve Temporal SDK wiring in Phase 29.

### Allowed Behavior

Phase 29 may:

- create plain callable functions for `validate_claim_check_ref`, `execute_agent_turn`, and `deliver_artifact`;
- validate exact caller-provided Phase 28 descriptor/report before exposing implementation metadata;
- return deterministic fake/stub results with stable statuses and error codes;
- preserve `side_effects: []`;
- reject malformed, hostile-subclass, raw-material, credential-shaped, callback-shaped, platform-id-shaped, and exception-shaped input;
- provide a contract descriptor and report validator for the implementation module;
- maintain changed-file allowlists in existing FlowWeaver guard tests if required.

Phase 29 must not:

- import Temporal SDK APIs;
- define `@activity.defn` functions;
- call `workflow.execute_activity`;
- construct `Client`, `Worker`, `WorkflowEnvironment`, retry objects, timeout SDK objects, or task queues;
- execute a real agent or tool;
- render, send, edit, callback, or acknowledge real delivery;
- access or mutate Gateway adapters;
- write config or require Gateway restart;
- read/write claim-check storage, files, sockets, subprocesses, Docker, daemons, or external services;
- log or print raw material.

### Planned Files

Create:

- `gateway/flowweaver_stub_activity_implementation.py`
- `tests/gateway/test_flowweaver_stub_activity_implementation.py`
- `docs/runbooks/flowweaver-stub-activity-implementation.md`
- `docs/plans/2026-05-09-flowweaver-phase29-stub-activity-implementation.md`
- `docs/dev_log/2026-05-09-flowweaver-phase29-stub-activity-implementation.md`

Possible guard maintenance only if required:

- existing FlowWeaver guard tests that maintain changed-file allowlists.

### Candidate Entrypoints

```python
def describe_flowweaver_stub_activity_implementation_contract() -> dict[str, object]: ...
def validate_flowweaver_stub_activity_implementation_report(value: object) -> dict[str, object]: ...
def build_flowweaver_stub_activity_implementation_report(*, implementation_validation_descriptor: object, implementation_validation_report: object) -> dict[str, object]: ...

def validate_claim_check_ref(*, claim_check_ref: object, policy_descriptor: object) -> dict[str, object]: ...
def execute_agent_turn(*, execution_request: object, validated_claim: object) -> dict[str, object]: ...
def deliver_artifact(*, artifact: object, delivery_plan: object) -> dict[str, object]: ...
```

Entrypoint rules:

- functions accept only exact plain dict/list/str/bool/int shapes where allowed by prior contracts;
- bool fields require exact `bool`, not integer impersonators;
- raw-material-looking strings fail closed;
- no function returns full prior reports, raw request bodies, raw tool outputs, card JSON, media paths, platform/private ids, callback payloads, credentials, or raw exception text;
- `execute_agent_turn` returns a stub artifact/result only;
- `deliver_artifact` returns a stub delivery result only and does not emit ACK updates.

### TDD Tasks

1. Write RED import tests for the new module and six public entrypoints.
2. Add descriptor/report exact-key tests that consume the Phase 28 validation artifact shape.
3. Add success tests for each stub function using canonical safe refs and bounded metadata.
4. Add fail-closed tests for malformed keys, reordered contract lists, extra fields, hostile subclasses, integer booleans, raw-material strings, credential-shaped values, callback-shaped values, and platform/private id-shaped values.
5. Add no-escape tests proving outputs do not contain raw prompts, tool outputs, cards, media paths, ids, callbacks, credentials, or raw exception text.
6. Add source-scan tests proving no Temporal SDK, Worker lifecycle, Gateway adapter access, real agent/tool execution, real delivery, file/subprocess/socket/Docker/daemon/service startup, logs, or prints.
7. Run focused and FlowWeaver regression verification.
8. Get blocker review before PR.

### Verification

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_implementation.py -q
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```

---

## Phase 30 — Local Temporal Stub Activity Orchestration

### Objective

Wrap the Phase 29 plain stubs in local/staging Temporal Activity orchestration and prove safe history/snapshot behavior through a local Worker harness.

### Strongest Allowed Verdict

```text
ready_for_controlled_agent_activity_implementation_request
```

This means Phase 31 may request approval to implement controlled non-production agent/tool execution. It does not approve production Gateway wiring or production delivery.

### Allowed Behavior

Phase 30 may:

- introduce Temporal Activity wrappers for the Phase 29 stubs;
- introduce a local/staging test Workflow that executes the fixed sequence `validate_claim_check_ref -> execute_agent_turn -> deliver_artifact`;
- use `WorkflowEnvironment`, `Worker`, and Temporal SDK APIs only inside the approved local/staging harness and tests;
- query snapshots and inspect workflow history;
- verify serialized protobuf event bytes and JSON history for no-leak behavior;
- test duplicate-start, retry/timeout policy shape, cancellation, and safe failure codes where relevant.

Phase 30 must not:

- let Gateway own Worker/service lifecycle;
- write production config;
- restart Gateway;
- mutate platform adapters;
- execute a real agent or tool;
- perform real delivery, render, send, edit, callback, or ACK updates;
- persist raw prompts, tool outputs, card JSON, media paths, platform/private ids, callbacks, credentials, or raw exception text in history/snapshots/logs.

### Planned Files

Create or modify only after Phase 30 approval:

- `gateway/flowweaver_temporal_stub_activity_orchestration.py`
- `tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py`
- `docs/runbooks/flowweaver-temporal-stub-activity-orchestration.md`
- `docs/plans/2026-05-09-flowweaver-phase30-temporal-stub-activity-orchestration.md`
- `docs/dev_log/2026-05-09-flowweaver-phase30-temporal-stub-activity-orchestration.md`

Possible guard maintenance only if required:

- existing FlowWeaver guard tests and local Temporal integration allowlists.

### Required Tests

- RED/GREEN import and harness tests.
- Safe start payload contains claim-check refs, counts, statuses, artifact refs, delivery refs, and digests only.
- Activity calls happen in exact order.
- Activity retry/timeout/cancel behavior returns stable sanitized codes.
- Duplicate-start reconciliation maps to an idempotent safe result only after sanitized snapshot comparison.
- History JSON and serialized event bytes contain no raw material key/value leak.
- Gateway modules do not instantiate or run a Worker.

### Verification

```bash
scripts/run_tests.sh tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py -q
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase5*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```

---

## Phase 31 — Controlled Agent / Tool Execution Activity

### Objective

Replace the Phase 29 fake `execute_agent_turn` result with a controlled non-production Activity boundary that can call an injected executor while keeping raw material out of durable state and user-visible reports.

### Strongest Allowed Verdict

```text
ready_for_controlled_delivery_activity_request
```

This means Phase 32 may request approval to implement controlled delivery/ACK behavior. It does not approve production agent execution or production delivery.

### Allowed Behavior

Phase 31 may:

- define an executor boundary for agent/tool execution;
- call a controlled executor in tests or staging only;
- load raw prompt/tool material only through claim-check references inside the Activity boundary;
- convert executor output into sanitized artifact refs, safe status, counts, digests, and stable error codes;
- use heartbeats/cancellation if the approved Temporal Activity harness requires them;
- prove retry policy separates transient failures from non-retryable unsafe input or auth/config failures.

Phase 31 must not:

- expose raw prompt text, tool output, model response body, card JSON, media path, platform/private id, callback payload, credentials, or raw exception text in history, snapshots, logs, fixtures, docs evidence, or user-visible output;
- create global `AIAgent` instances or hidden executor factories unless explicitly approved in the Phase 31 design;
- call Gateway rendering or delivery;
- update delivery ACKs;
- write production config, restart Gateway, mutate platform adapters, or own service lifecycle.

### Planned Files

Create or modify only after Phase 31 approval:

- `gateway/flowweaver_agent_execution_activity.py`
- `tests/gateway/test_flowweaver_agent_execution_activity.py`
- `tests/integration/test_flowweaver_phase31_agent_execution_activity.py`
- `docs/runbooks/flowweaver-agent-execution-activity.md`
- `docs/plans/2026-05-09-flowweaver-phase31-agent-execution-activity.md`
- `docs/dev_log/2026-05-09-flowweaver-phase31-agent-execution-activity.md`

### Required Tests

- Executor is injected, observable, and bounded.
- Missing or unsafe claim-check refs fail closed before executor calls.
- Executor success returns sanitized artifact refs and safe metadata only.
- Executor failures produce stable error codes without raw exception leakage.
- Cancellation/timeout paths return safe partial progress.
- History JSON and serialized event bytes remain no-leak.
- Delivery surfaces remain untouched.

### Verification

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_agent_execution_activity.py -q
scripts/run_tests.sh tests/integration/test_flowweaver_phase31_agent_execution_activity.py -q
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py -q
```

---

## Phase 32 — Controlled Artifact Delivery and ACK Activity

### Objective

Implement controlled delivery and ACK reconciliation as a separate Activity boundary after agent execution is proven safe.

### Strongest Allowed Verdict

```text
ready_for_narrow_ai_flow_pilot_request
```

This means Phase 33 may request approval to run a narrow AI FLOW pilot. It does not approve broad production rollout.

### Allowed Behavior

Phase 32 may:

- define a delivery surface boundary for artifact rendering/sending in non-production or explicitly approved staging/shadow contexts;
- emit delivery ACK updates only for initialized runtime delivery slots;
- reconcile ACKs through the existing runtime control surface;
- preserve separate delivery surfaces such as `progress_card_sent`, `rich_cards_sent`, `final_text_sent`, and `media_sent`;
- prove rich-card delivery never suppresses required final text delivery;
- support duplicate/replay ACK idempotency.

Phase 32 must not:

- assume production adapters are safe by default;
- mutate platform adapters without explicit approval;
- write config or restart Gateway;
- invent ACK targets that were not initialized;
- merge rich-card status with final text status;
- expose raw platform ids, callback payloads, card JSON, media paths, credentials, or raw exception text.

### Planned Files

Create or modify only after Phase 32 approval:

- `gateway/flowweaver_delivery_activity.py`
- `tests/gateway/test_flowweaver_delivery_activity.py`
- `tests/integration/test_flowweaver_phase32_delivery_activity_ack_reconciliation.py`
- `docs/runbooks/flowweaver-delivery-activity-ack-reconciliation.md`
- `docs/plans/2026-05-09-flowweaver-phase32-delivery-activity-ack-reconciliation.md`
- `docs/dev_log/2026-05-09-flowweaver-phase32-delivery-activity-ack-reconciliation.md`

Possible narrow Gateway hook touch only with explicit approval:

- `gateway/run.py` observation/delivery hook point behind default-off policy.

### Required Tests

- Delivery surface is injected and default-off.
- Disabled policy makes zero delivery calls.
- Emitted ACK targets are a deterministic bounded subset/prefix of initialized delivery slots.
- Extra ACK target fails closed as mismatch.
- Duplicate ACK replay is idempotent.
- Rich-card sent state does not set or imply final text sent.
- Failure and timeout paths preserve delivery state and do not suppress final text.
- No raw platform/card/callback/media/credential material leaks.

### Verification

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_delivery_activity.py -q
scripts/run_tests.sh tests/integration/test_flowweaver_phase32_delivery_activity_ack_reconciliation.py -q
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase31_agent_execution_activity.py -q
```

---

## Phase 33 — Narrow AI FLOW Pilot and Production-Enablement Decision Packet

### Objective

Run FlowWeaver against a narrow AI FLOW scenario and produce a decision packet for whether production enablement should be requested separately.

### Strongest Allowed Verdict

```text
ready_for_separate_production_enablement_decision
```

This is not production readiness. It only means the project has enough pilot evidence for 狗哥 to decide whether to authorize a separately scoped production enablement phase.

### Allowed Behavior

Phase 33 may:

- run one or more explicitly approved AI FLOW pilot scenarios, such as repo planning, implementation, verification, review, PR, CI wait, merge cleanup, and post-merge sync;
- use the Phase 31 and Phase 32 boundaries only in the modes previously approved and verified;
- record durable transaction, intent, operation, artifact, and delivery state;
- produce sanitized progress snapshots and final artifacts;
- produce a rollback/kill-switch checklist and operator decision packet.

Phase 33 must not:

- silently enable broad production shadow;
- enable production delivery or production agent execution beyond the approved pilot surface;
- write production config without separate approval;
- restart Gateway without separate approval;
- mutate platform adapters without separate approval;
- skip no-leak history/snapshot/log verification;
- treat a successful pilot as automatic production enablement.

### Planned Files

Create or modify only after Phase 33 approval:

- `tests/integration/test_flowweaver_phase33_ai_flow_pilot.py`
- `docs/runbooks/flowweaver-ai-flow-pilot.md`
- `docs/plans/2026-05-09-flowweaver-phase33-ai-flow-pilot.md`
- `docs/dev_log/2026-05-09-flowweaver-phase33-ai-flow-pilot.md`
- optional pilot fixtures under a non-ignored, sanitized fixtures path approved by `git check-ignore`.

Possible code touch only if approved by the Phase 33 plan:

- narrow orchestration glue that connects already-approved Phase 31 and Phase 32 surfaces for the pilot.

### Required Tests and Evidence

- End-to-end pilot produces deterministic transaction/intent/operation/artifact/delivery snapshots.
- Progress updates are compact, meaningful, and not raw logs.
- Artifact and delivery state remain separated.
- ACK replay is idempotent.
- Cancellation and rollback paths are proven.
- Gateway disabled/off-policy path is a no-op.
- History JSON, serialized event bytes, logs, fixtures, docs evidence, and user-visible outputs pass no-leak scans.
- Operator decision packet names unresolved risks, measured evidence, rollback path, and exact separate approvals needed.

### Verification

```bash
scripts/run_tests.sh tests/integration/test_flowweaver_phase33_ai_flow_pilot.py -q
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase3*.py -q
```

---

## Post-Roadmap Actions Not Approved Here

The following actions remain outside Phase 29–33 and require a separate explicit production-enablement plan:

- production config writes;
- Gateway restart/reload;
- production-shadow or production-live broad rollout;
- platform adapter mutation outside the approved hook surface;
- Temporal Worker/service deployment ownership;
- production send/edit/render/callback control;
- production agent/tool execution;
- user-facing feature announcement or default-on behavior.

## Roadmap Acceptance

This roadmap document is accepted only if:

- it is docs-only;
- it creates exactly this plan and the paired dev log;
- it compresses the post-P28 path into named phases instead of seven loose work blocks;
- it identifies Phase 29 as the next behavior-bearing step;
- it keeps all production and live-effect actions behind separate approvals;
- `git check-ignore` confirms the docs paths are not ignored;
- `git diff --check` passes after making untracked docs visible;
- a custom docs gate confirms required phase markers and docs-only changed-file scope;
- independent consistency and security/low-intrusion reviews return no blockers.

## Roadmap Docs Verification

```bash
git check-ignore -v docs/plans/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md docs/dev_log/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md

git add -N docs/plans/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md docs/dev_log/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md
git diff --check
```

## Execution Handoff

Plan complete and saved. Implementation must stop here until 狗哥 explicitly approves the next phase.

Recommended next approval request:

```text
Approve Phase 29 only: non-production callable stub Activity implementation.
```

Do not batch approve Phase 29–33. Each phase should land with its own plan, dev log, verification, review, PR, and merge gate.
