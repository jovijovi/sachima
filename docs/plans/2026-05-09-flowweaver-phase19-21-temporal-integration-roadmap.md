# FlowWeaver Phase 19–21 Temporal Integration Roadmap Implementation Plan

> **For Hermes:** Use subagent-driven-development for each implementation phase after 狗哥 explicitly approves that phase. This document is the compressed roadmap that replaces more pure report-only phases. Do not treat this plan itself as approval to enable production Gateway behavior.

**Goal:** Land the next three FlowWeaver phases as a short, implementation-oriented Temporal integration path: controlled observation bridge, guarded validation, then narrow production-shadow observation.

**Architecture:** Phase 19 introduces the first controlled Gateway observation path into the existing Temporal runtime control surface, default-off and observation-only. Phase 20 validates real/synthetic Gateway observation events against a local or staging Temporal Worker with no-leak and rollback drills. Phase 21 permits a narrow production-shadow rollout for observation state only; delivery, agent execution, and production send/edit/render remain separately gated.

**Tech Stack:** Python, pytest, Temporal Python SDK, existing FlowWeaver runtime client/control surface, existing Gateway helper/test patterns, GitHub PR gates.

---

## Baseline

```text
Repository: jovijovi/sachima
Base branch: feature/sachima-channel
Base HEAD when roadmap was drafted: e6af3ade5faf5fddb0ddb7041db41516efb6b084
Latest completed phase: Phase 18 — guarded live Gateway observation validation
Roadmap branch: docs/flowweaver-phase19-21-temporal-roadmap
Roadmap worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/docs-flowweaver-phase19-21-temporal-roadmap
```

Existing evidence this roadmap relies on:

```text
Phase 5B: local Temporal POC with safe start payloads and workflow snapshots.
Phase 5J: stub Activity / claim-check boundary with real local Worker evidence.
Phase 5K: runtime control surface for start/query/reconcile/cancel operations.
Phase 6: Gateway ACK shadow bridge.
Phase 7: shadow Gateway E2E loop using start -> query -> ACK bridge -> final query.
Phase 8: production-readiness gate proving a weaker controlled-shadow design verdict.
Phase 14–18: approval-chain hygiene for guarded live observation enablement and validation.
```

## Compression Decision

Phase 14–18 were useful because independent review found real contract bugs: hostile subclass equality, noncanonical upstream ids, and integer boolean impersonators. Continuing with more pure/default-off artifact-only reports would now be over-cautious.

The roadmap is therefore compressed to three behavior-bearing phases:

```text
Phase 19: controlled Gateway observation bridge to Temporal.
Phase 20: guarded observation validation against real Gateway-style events and local/staging Temporal.
Phase 21: narrow production-shadow observation-only rollout.
```

## Global Boundaries for All Three Phases

All phases must preserve these boundaries unless 狗哥 gives a separate, explicit approval naming the action:

- no production send/edit/render/callback behavior;
- no Temporal-backed agent execution;
- no Gateway-owned Temporal Worker, test server, daemon, Docker process, or service lifecycle;
- no production config writes;
- no Gateway restart;
- no platform adapter mutation except a separately approved observation-only hook;
- no payload-carrying Temporal Signals;
- no raw prompt, tool output, card JSON, media path, platform identifier, callback payload, credential value, or raw exception text in Temporal history, snapshots, logs, reports, fixtures, or user-visible output;
- no deletion of remote branches.

Gateway may learn how to observe and report safe state. It must not use Temporal to control message delivery or agent execution in this roadmap.

## Shared Temporal Boundary

Use the existing split:

```text
Gateway observation ingress
  -> reduce to sanitized observation envelope / claim-check refs only
  -> build start/query/update request for runtime control surface
  -> FlowWeaverRuntimeControlSurface.handle(...)
  -> FlowWeaverRuntimeClient.start_transaction / query_transaction / reconcile_delivery_ack
  -> Temporal Workflow stores only safe refs, counts, digests, statuses, and delivery/artifact ids
```

Gateway must not instantiate or run a Temporal Worker. Worker lifecycle belongs to the operator/deployment environment. Gateway may only use an explicit caller-supplied client or explicitly configured runtime client after separate approval.

## Phase 19 — Controlled Gateway Observation Bridge to Temporal

### Objective

Add the first controlled, default-off connection from Gateway observation ingress to the FlowWeaver Temporal runtime control surface.

### Strongest Allowed Verdict

```text
ready_for_guarded_temporal_observation_validation
```

This means the bridge is ready for Phase 20 validation. It does not mean production shadow is enabled.

### Allowed Behavior

Phase 19 may:

- add a small Gateway-side observation bridge module;
- add a narrow default-off observation hook design for `gateway/run.py` if implementation approval explicitly includes it;
- consume a reduced observation envelope, not raw platform payloads;
- call the runtime control surface with start/query only through caller-supplied dependencies;
- return sanitized result summaries and stable error codes;
- prove feature-flag-off behavior is a no-op.

Phase 19 must not:

- call platform adapters;
- send/edit/render/callback;
- reconcile real delivery ACKs from production Gateway;
- start or own Temporal Worker/service lifecycle;
- write config or registry files;
- restart Gateway;
- accept raw platform payloads as durable input.

### Planned Files

Create:

- `docs/plans/2026-05-09-flowweaver-phase19-controlled-gateway-temporal-observation-bridge.md`
- `docs/dev_log/2026-05-09-flowweaver-phase19-controlled-gateway-temporal-observation-bridge.md`
- `docs/runbooks/flowweaver-temporal-observation-bridge.md`
- `gateway/flowweaver_temporal_observation_bridge.py`
- `tests/gateway/test_flowweaver_temporal_observation_bridge.py`

Possible narrow implementation touch, only with explicit Phase 19 approval:

- `gateway/run.py` — observation-only hook point behind a default-off policy, with no send/edit/render changes.

Possible test/guard maintenance:

- `tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py`
- `tests/integration/test_flowweaver_phase5i_start_signature_parity.py`
- `tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py`
- `tests/integration/test_flowweaver_phase5k_runtime_control_surface.py`

### Candidate Entrypoint

```python
async def observe_gateway_turn_for_flowweaver_temporal(
    *,
    observation: object,
    runtime_control_surface: object,
    bridge_policy: object,
) -> dict[str, object]:
    ...
```

Entrypoint rules:

- `observation` must be an exact plain dict containing only safe ids, safe refs, counts, booleans, bounded labels, and digest fields.
- `runtime_control_surface` must be caller-supplied; no factories, connect helpers, addresses, lazy clients, or Worker construction.
- `bridge_policy` must be exact/default-off unless the phase-specific test enables a controlled observation path.
- Return values must be sanitized and fail closed with stable error codes.

### Phase 19 TDD Tasks

#### Task 1: Write import/API RED test

**Objective:** Lock the bridge module and entrypoint shape before implementation.

**Files:**

- Create: `tests/gateway/test_flowweaver_temporal_observation_bridge.py`
- Later create: `gateway/flowweaver_temporal_observation_bridge.py`

**Steps:**

1. Add RED test importing `observe_gateway_turn_for_flowweaver_temporal`.
2. Run:

   ```bash
   scripts/run_tests.sh tests/gateway/test_flowweaver_temporal_observation_bridge.py -q
   ```

3. Expected: FAIL with missing module/import.
4. Implement empty fail-closed module only after RED is confirmed.

#### Task 2: Prove default-off no-op behavior

**Objective:** The bridge must not call runtime when policy is disabled.

**Test requirements:**

- disabled/default policy returns `ok = False` or `status = disabled` with `side_effects = []`;
- fake runtime control surface records zero calls;
- no platform/runtime raw material appears in output.

#### Task 3: Validate sanitized observation envelopes

**Objective:** Reject raw or platform-adjacent material before runtime calls.

RED cases must include:

- raw prompt/body text;
- card JSON-like keys;
- media path-like values;
- platform/private id prefixes;
- callback payloads;
- raw exception-like strings;
- credential-shaped values;
- integer boolean impersonators (`1` / `0`) where exact bool is required;
- hostile `dict`, `list`, `str`, and `bool`-adjacent subclasses.

#### Task 4: Prove start/query-only runtime calls

**Objective:** When enabled in test policy, the bridge may only call start/query through the supplied surface.

Expected call sequence:

```text
start_transaction
query_transaction
```

Forbidden:

```text
reconcile_delivery_ack
cancel_transaction
send/edit/render/callback
Client.connect
Worker
WorkflowEnvironment
subprocess/Docker/service startup
```

#### Task 5: Prove consecutive-turn identity safety

**Objective:** Same session, fast consecutive turns must not collide.

Tests:

- two observations with same safe session label and close timestamps produce distinct safe transaction ids;
- microsecond or monotonic safe discriminator is included in the hash input;
- raw timestamps/source refs are not exported.

#### Task 6: Add source/diff safety gate

**Objective:** Prevent hidden runtime ownership and raw logging.

Scan added lines and new files for:

```text
Client.connect, Worker, WorkflowEnvironment, temporal server, Docker, subprocess,
systemctl, daemon, socket listener startup, gateway platform imports,
send_message, edit_message, render, callback, Path.write_text to config,
logger.* raw exception interpolation, print(raw...), repr(raw...), importlib/__import__ dynamic bypasses
```

### Phase 19 Verification Commands

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_temporal_observation_bridge.py -q

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

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m py_compile \
  gateway/flowweaver_temporal_observation_bridge.py \
  tests/gateway/test_flowweaver_temporal_observation_bridge.py

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m ruff check \
  gateway/flowweaver_temporal_observation_bridge.py \
  tests/gateway/test_flowweaver_temporal_observation_bridge.py

git diff --check
```

### Phase 19 Review Gate

Run Codex read-only with explicit verdict format:

```text
VERDICT: PASS | BLOCK
BLOCKERS:
- concrete blockers only
CHECKED:
- raw material / Temporal history boundary
- caller-supplied runtime dependency only
- default-off behavior
- start/query-only control surface
- no send/edit/render/callback
- no Worker/service lifecycle
```

## Phase 20 — Guarded Temporal Observation Validation

### Objective

Validate the Phase 19 bridge with real Gateway-style event shapes and a local or staging Temporal Worker, while proving history no-leak, rollback, duplicate-start, and kill-switch behavior.

### Strongest Allowed Verdict

```text
ready_for_production_shadow_observation_request
```

This means a separate Phase 21 production-shadow request can be prepared. It does not enable production shadow.

### Allowed Behavior

Phase 20 may:

- run local Temporal test environments and Workers in tests only;
- run against a staging/caller-supplied Temporal client in manual validation only;
- use sanitized captured observation fixtures;
- validate Temporal history bytes and snapshots;
- test duplicate-start, query retry, rollback, and disabled-policy paths.

Phase 20 must not:

- restart production Gateway;
- write production config;
- send/edit/render/callback real messages;
- add production platform adapter behavior;
- let Gateway own Worker/service lifecycle;
- store raw material in workflow history, snapshots, logs, docs, or fixtures.

### Planned Files

Create:

- `docs/plans/2026-05-10-flowweaver-phase20-guarded-temporal-observation-validation.md`
- `docs/dev_log/2026-05-10-flowweaver-phase20-guarded-temporal-observation-validation.md`
- `docs/runbooks/flowweaver-temporal-observation-validation.md`
- `tests/integration/test_flowweaver_phase20_temporal_observation_validation.py`
- `tests/gateway/test_flowweaver_temporal_observation_validation_gate.py`

Possible implementation files:

- `gateway/flowweaver_temporal_observation_validation.py`
- narrow additions to `gateway/flowweaver_temporal_observation_bridge.py`

### Phase 20 TDD Tasks

#### Task 1: Integration RED for local Worker validation

**Objective:** The validation harness must call the Phase 19 bridge against a real local Temporal Worker or test environment.

Expected flow:

```text
safe observation fixture
  -> Phase 19 bridge
  -> runtime control surface start/query
  -> Temporal workflow snapshot
  -> history no-leak scan
  -> sanitized validation report
```

#### Task 2: History no-leak tests

**Objective:** Inspect both JSON rendering and serialized event bytes.

Required checks:

- no raw prompt/card/media/platform/callback markers;
- no private source ids;
- no credential-shaped values;
- no raw exception strings;
- only safe refs, counts, digests, statuses, artifact ids, and delivery ids.

#### Task 3: Duplicate-start and consecutive-turn validation

**Objective:** Confirm Phase 19 identity behavior holds with real Temporal duplicate-start semantics.

Tests:

- duplicate start maps to a stable idempotent result only after sanitized query comparison;
- distinct consecutive observations produce distinct transactions;
- query retry is bounded and returns stable fail-closed code if unavailable.

#### Task 4: Kill-switch and rollback drill

**Objective:** Turning the observation policy off must stop new starts without corrupting existing query/read paths.

Tests:

- enabled observation creates safe transaction;
- disabled policy after enablement produces no new runtime mutation;
- existing transaction query remains safe;
- rollback report lists operator action labels only, not raw config values.

#### Task 5: Gateway-style fixture validation

**Objective:** Use realistic but sanitized Gateway observation shapes.

Fixtures must be synthetic or reduced. They must not copy real Feishu/Telegram/Slack payloads, message ids, card JSON, media paths, or user text.

### Phase 20 Verification Commands

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_temporal_observation_validation_gate.py -q

TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase20_temporal_observation_validation.py \
  tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  -q

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m py_compile \
  gateway/flowweaver_temporal_observation_validation.py \
  tests/gateway/test_flowweaver_temporal_observation_validation_gate.py \
  tests/integration/test_flowweaver_phase20_temporal_observation_validation.py

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m ruff check \
  gateway/flowweaver_temporal_observation_validation.py \
  tests/gateway/test_flowweaver_temporal_observation_validation_gate.py \
  tests/integration/test_flowweaver_phase20_temporal_observation_validation.py

git diff --check
```

### Phase 20 Review Gate

Codex must specifically check:

- JSON and serialized protobuf event bytes are both scanned;
- duplicate-start handling is stable and sanitized;
- Worker/test-environment lifecycle exists only in tests/manual validation;
- rollback/kill-switch is real behavior, not just documentation;
- no production Gateway enablement sneaks in.

## Phase 21 — Narrow Production-Shadow Observation-Only Rollout

### Objective

Add the smallest production-shadow observation path: real Gateway turns can be observed and mirrored into Temporal state only when explicitly enabled, with no delivery control and no agent execution.

### Strongest Allowed Verdict

```text
ready_for_separate_delivery_or_agent_execution_design
```

This is intentionally weaker than production enablement for delivery or agent execution.

### Required Separate Approvals Before Phase 21 Execution

Phase 21 must not start until 狗哥 approves all of these explicitly:

```text
1. production-shadow observation-only scope;
2. exact Gateway hook path;
3. exact config key or runtime flag, if any;
4. Temporal address/namespace/task queue handling approach;
5. Gateway restart or reload method, if needed;
6. rollback/kill-switch operation;
7. observability/logging shape.
```

Approval for Phase 21 does not approve remote branch deletion, production send/edit/render/callback, or Temporal-backed agent execution.

### Allowed Behavior

Phase 21 may:

- enable observation-only shadow for a narrow allowlisted scope;
- use externally managed Temporal service/Worker;
- start/query observation transactions from real Gateway turns after ingress reduction;
- emit sanitized progress/health counters;
- provide operator runbook steps for disable/rollback.

Phase 21 must not:

- alter message delivery behavior;
- suppress final text because a card or progress surface exists;
- execute agent/tool calls inside Temporal Activities;
- call real platform send/edit/render/callback from Temporal;
- auto-start Worker/service lifecycle from Gateway;
- write config without explicit approval;
- restart Gateway without explicit approval.

### Planned Files

Create:

- `docs/plans/2026-05-11-flowweaver-phase21-production-shadow-observation-only.md`
- `docs/dev_log/2026-05-11-flowweaver-phase21-production-shadow-observation-only.md`
- `docs/runbooks/flowweaver-production-shadow-observation.md`
- `tests/gateway/test_flowweaver_production_shadow_observation.py`
- `tests/integration/test_flowweaver_phase21_production_shadow_observation.py`

Likely implementation touch points, only after explicit Phase 21 approval:

- `gateway/run.py` — minimal observation hook behind explicit flag/config;
- `gateway/flowweaver_temporal_observation_bridge.py` — production-shadow policy adapter;
- maybe `gateway/config.py` or equivalent config reader, only if a config flag is approved.

### Phase 21 TDD Tasks

#### Task 1: RED for feature-flag-off production behavior

**Objective:** With default config, Gateway behavior is byte-for-byte equivalent for send/edit/render decisions.

Tests must prove:

- no observation transaction starts by default;
- final text behavior is unchanged;
- rich card/progress/media delivery state remains separate;
- no platform adapter call changes.

#### Task 2: RED for explicit observation-only enablement

**Objective:** When enabled by test policy, a sanitized observation transaction starts but delivery stays untouched.

Tests must prove:

- exactly one safe start/query path for each observed turn;
- no delivery ACK is invented;
- no send/edit/render/callback functions are called;
- no raw material appears in runtime requests or logs.

#### Task 3: Operator kill-switch test

**Objective:** Runtime disable must stop new observation starts immediately.

Tests:

- enabled -> one safe observation;
- disable -> no further start;
- query existing observation remains safe;
- rollback report contains only safe labels and stable codes.

#### Task 4: Production-shadow integration test

**Objective:** Verify observation-only shadow against an externally supplied or test-managed Temporal client.

The test must distinguish:

```text
initialized runtime state
actual observation start/query calls
actual Gateway delivery behavior
```

No invented ACKs are allowed to satisfy parity.

#### Task 5: Documentation and operator runbook

**Objective:** Operators need exact safe steps.

Runbook must include:

- enablement prerequisites;
- how to confirm Gateway flag state;
- how to confirm Temporal worker availability without Gateway owning it;
- how to disable observation;
- rollback steps;
- known failure modes and stable error codes;
- explicit non-goals: no delivery control and no Temporal agent execution.

### Phase 21 Verification Commands

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_production_shadow_observation.py -q

TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase21_production_shadow_observation.py \
  tests/integration/test_flowweaver_phase20_temporal_observation_validation.py \
  tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py \
  -q

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m py_compile \
  gateway/flowweaver_temporal_observation_bridge.py \
  tests/gateway/test_flowweaver_production_shadow_observation.py \
  tests/integration/test_flowweaver_phase21_production_shadow_observation.py

/home/ubuntu/.hermes/hermes-agent/venv/bin/python -m ruff check \
  gateway/flowweaver_temporal_observation_bridge.py \
  tests/gateway/test_flowweaver_production_shadow_observation.py \
  tests/integration/test_flowweaver_phase21_production_shadow_observation.py

git diff --check
```

### Phase 21 Review Gate

Codex and Hermes verification must both pass:

```text
VERDICT: PASS | BLOCK
Required checks:
- default-off production behavior unchanged;
- enabled path is observation-only;
- no Gateway-owned Worker/service lifecycle;
- no raw material in history/logs/snapshots;
- delivery surfaces remain separate;
- kill-switch/rollback is behaviorally tested;
- production config/restart steps are documented as separate approvals.
```

## Cross-Phase Acceptance Criteria

This roadmap is complete only when all three implementation PRs have proven:

```text
Phase 19 -> ready_for_guarded_temporal_observation_validation
Phase 20 -> ready_for_production_shadow_observation_request
Phase 21 -> ready_for_separate_delivery_or_agent_execution_design
```

The roadmap deliberately does not include:

- Temporal-backed delivery execution;
- Temporal-backed agent/tool execution;
- production ACK reconciliation from real send/edit/render outcomes;
- broad DAG scheduling;
- platform-specific rich-card rendering changes;
- service deployment automation.

Those are separate future designs after observation-only shadow is boring and stable.

## PR / CI Discipline

For each phase:

1. create an isolated worktree under `/home/ubuntu/workspace/hermes/worktrees/sachima/`;
2. write/patch the phase plan and dev log before code;
3. get explicit phase approval before behavior-bearing code;
4. use TDD for implementation;
5. run focused tests, integration tests, static checks, `git diff --check`, and a custom forbidden-surface scan;
6. run Codex read-only review with concrete PASS/BLOCK verdict;
7. patch blockers RED-first;
8. open PR against `feature/sachima-channel`;
9. wait for CI green;
10. squash merge, fast-forward local canonical, and clean local worktree/branch while preserving remote feature branches unless separately approved.

## Human Decision Points

Dog Brother should be asked only at meaningful gates:

```text
1. Approve Phase 19 behavior implementation.
2. Approve Phase 20 guarded validation with local/staging Temporal Worker.
3. Approve Phase 21 production-shadow observation-only scope and operational controls.
4. Separately approve any config write, Gateway restart, production service action, or platform-adapter behavior change.
5. Separately approve any move from observation-only to delivery or agent execution.
```

No more pure report-only phase should be inserted unless a reviewer finds a concrete blocker that genuinely prevents safe implementation.
