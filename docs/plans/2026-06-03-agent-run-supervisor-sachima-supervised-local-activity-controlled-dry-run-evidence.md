# agent-run-supervisor × Sachima Supervised Local Activity — Controlled Local Dry-Run Evidence

> **For Hermes:** This phase is local/offline only. It adds a deterministic, fixture-backed evidence document built from the already-merged `exec_dry_run` Activity wrapper using **injected/fake supervisor outcomes only**. It does not approve live behavior, Gateway involvement, real external ingress, real IM/Feishu delivery, production config writes, Gateway restart/reload, real AGENT execution, or controlled AI FLOW execution.

## Approval

Status markers:

```text
marker_note: no live / no gateway / no real delivery / no real agent execution / no controlled ai flow execution
LOCAL_OFFLINE_ONLY
EXEC_DRY_RUN_ONLY
INJECTED_SUPERVISOR_ONLY
NO_LIVE
NO_GATEWAY
NO_REAL_DELIVERY
NO_REAL_AGENT_EXECUTION
CONTROLLED_AI_FLOW_EXECUTION_NOT_APPROVED
```

User approval received in chat:

```text
approve_agent_run_supervisor_sachima_supervised_local_activity_controlled_local_dry_run_evidence_no_live_no_gateway_no_real_delivery_no_real_agent_execution
```

## Goal

Produce a deterministic local dry-run evidence document that proves the merged `sachima_supervisor.activity` wrapper (PR #99) behaves correctly across role mapping, idempotency replay/conflict, sanitized durable state/query, and unsafe lower-outcome collapse — without ever invoking a real supervisor, real AGENT, Gateway, or delivery surface. The evidence is built from injected/fake supervisor outcomes only and is backed by a committed fixture so any drift is caught in CI.

## Scope

Allowed changed areas:

- `sachima_supervisor/activity_evidence.py` — deterministic evidence builder and writer.
- `sachima_supervisor/__init__.py` — public exports for the evidence helper API.
- `tests/sachima_supervisor/test_activity_controlled_dry_run_evidence.py` — RED/GREEN tests (authored by Hermes).
- `tests/fixtures/sachima_supervisor/controlled_local_activity_dry_run_evidence.v1.json` — committed deterministic fixture.
- roadmap / plan / manifest / dev-log docs for status and evidence.

## Evidence Document

`build_controlled_local_dry_run_evidence()` returns a deterministic dict:

```text
type:           sachima.supervisor.controlled_local_activity_dry_run_evidence.v1
approval_marker: the exact approval string above
scope:          local_offline_only / exec_dry_run_only / injected_supervisor_only = True;
                live / gateway / real_delivery / real_agent_execution /
                controlled_ai_flow_execution = False
summary:        scenario_count 5; real_supervisor_invocations 0;
                injected_supervisor_invocations 5; all_durable_states_sanitized True;
                idempotency_replay_without_second_call True;
                unsafe_lower_outcome_collapsed True
scenarios:      docs_planner_success, verifier_success, idempotency_replay,
                idempotency_conflict, unsafe_supervisor_outcome
fixture_digest: sha256:<canonical digest of the document body>
```

Each scenario records `mode = exec_dry_run` and `supervisor_source = injected_fake`, plus a sanitized `durable_state` (or, for the conflict scenario, the stable `error_code`).

`write_controlled_local_dry_run_evidence(path)` serializes the same document to a JSON file and returns the `Path`. The committed fixture equals `build_controlled_local_dry_run_evidence()`.

## Scenarios

```text
docs_planner_success      role docs_planner; successful injected config-preview; query == start
verifier_success          role verifier; successful injected config-preview (role-map breadth)
idempotency_replay        identical request + key replays stored state, no second supervisor call
idempotency_conflict      same key + incompatible request fails closed (activity_idempotency_conflict)
unsafe_supervisor_outcome unsafe/malformed injected outcome collapses to activity_supervisor_failed
```

## Safety Invariants

- No real supervisor runtime path is imported or called; `invoke_local_offline_supervisor` is never referenced.
- Every scenario runs only `exec_dry_run` against an in-memory `ActivityStateStore` with an injected fake supervisor callable.
- Durable states carry only sanitized stable codes, caller-owned refs, counts, and digests. The builder self-verifies each durable state against the same no-leak markers asserted by the tests.
- The document is deterministic: stable strings, no timestamps, no randomness; repeated builds are byte-identical and equal to the committed fixture.

## Acceptance Gates

- [x] RED evidence for missing `sachima_supervisor.activity_evidence` module (2 failed, ModuleNotFoundError).
- [x] GREEN focused tests: `python3 -m pytest tests/sachima_supervisor/test_activity_controlled_dry_run_evidence.py tests/sachima_supervisor/test_activity.py tests/sachima_supervisor/test_local_offline.py -q` → 68 passed.
- [x] Compile check: `python3 -m py_compile sachima_supervisor/*.py tests/sachima_supervisor/test_activity_controlled_dry_run_evidence.py tests/sachima_supervisor/test_activity.py tests/sachima_supervisor/test_local_offline.py`.
- [x] `python3 -m ruff check sachima_supervisor tests/sachima_supervisor/test_activity_controlled_dry_run_evidence.py tests/sachima_supervisor/test_activity.py` → all checks passed.
- [x] `git diff --check`.
- [x] Changed-file allowlist (Hermes verification) → 8 changed paths, 0 extra.
- [x] Secret/no-leak/static forbidden-surface scan (Hermes verification) → 0 findings / pass.
- [x] Codex primary review after implementation candidate is ready → `VERDICT: PASS`, blockers none.
- [x] PR CI green before merge; record final merge status → PR #100 merged at `3fea6e2e8ee836e924c3e0eef1b3ff3a2b930c59`.

## Still Not Approved

```text
real_external_sachima_ingress
real_external_delivery
production_delivery_control
production_agent_tool_execution_expansion
production_config_write
gateway_restart_or_reload
platform_adapter_mutation
gateway_owned_temporal_lifecycle
real_send_api_or_external_im_call
external_temporal_service_or_worker_startup
live_or_default_on_behavior
public_webhook_exposure
automatic_replies
worker_auto_routing
agent_to_agent_auto_routing
@all_fanout
trusted_markdown_html_rendering
real_agent_execution
controlled_ai_flow_execution
```

## Next Decision After This PR

PR #100 merged, and the supervised local Activity now has deterministic local dry-run evidence. The next request should stay on the supervisor → Sachima mainline and remain design-only unless separately approved: durable runtime ownership and controlled local execution semantics around the Activity. Real local `exec`, persistent sessions, cancellation, live Gateway behavior, public ingress, real delivery, real AGENT execution, and controlled AI FLOW execution all remain separate approvals after durable-runtime ownership gates.
