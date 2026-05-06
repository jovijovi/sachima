# FlowWeaver Phase 5E — Variable Runtime IDs / Local Publish Adapter Dev Log

Timestamp: 2026-05-06 01:16:24 CST +0800

## User Ask

```text
开始下一个阶段
```

## Baseline Verification

- Canonical repo: `/home/ubuntu/workspace/hermes/repo/sachima`
- Canonical branch: `feature/sachima-channel`
- Canonical HEAD observed before Phase 5E worktree: `604995ce48acfb9610957ad5cd8cdd24b86db9b4`
- PR #30 / Phase 5D: `MERGED`, merge commit `604995ce48acfb9610957ad5cd8cdd24b86db9b4`
- New Phase 5E worktree: `/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5e-variable-runtime-ids-local-publish-adapter`
- New Phase 5E branch: `feat/flowweaver-phase5e-variable-runtime-ids-local-publish-adapter`
- Worktree HEAD: `604995ce48acfb9610957ad5cd8cdd24b86db9b4`

Canonical untracked items observed before Phase 5E and not part of this phase:

```text
.hermes/
docs/plans/2026-04-24-sachima-channel.md
docs/superpowers/
```

Baseline focused tests in the Phase 5E worktree:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_shadow_publisher.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  -q
```

Observed:

```text
16 passed in 0.54s
```

## Skills / Process Knowledge Loaded

- `software-development/superpowers/using-superpowers`
- `software-development/hermes-workspace-worktrees`
- `software-development/plan`
- `software-development/writing-plans`
- `software-development/superpowers/brainstorming`
- `devops/temporal-durable-orchestration`
- `software-development/test-driven-development`
- `software-development/requesting-code-review`
- `software-development/subagent-driven-development`
- `software-development/use-driven-skill-validation`

Use-driven validation applied: the current repo, Phase 5D plan/dev log, current source files, and baseline tests were treated as higher-grade evidence than prior summaries.

## Context Inspected

- `AGENTS.md`
- `docs/plans/2026-05-05-flowweaver-phase5-architecture-gate.md`
- `docs/plans/2026-05-05-flowweaver-phase5d-gateway-shadow-publisher-ack-bridge.md`
- `docs/dev_log/2026-05-05-flowweaver-phase5d-gateway-shadow-publisher-ack-bridge.md`
- `gateway/flowweaver_shadow.py`
- `gateway/flowweaver_runtime_contract.py`
- `gateway/flowweaver_shadow_publisher.py`
- `gateway/flowweaver_mock_durable.py`
- `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py`
- `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/workflows.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/runtime_client.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/tool_adapter.py`
- `tests/gateway/test_flowweaver_shadow_publisher.py`
- `tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py`
- `tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py`

## Key Findings

1. Phase 5D is merged and current `feature/sachima-channel` includes the default-off Gateway shadow publisher / ACK bridge.
2. Phase 5D still uses the fixed POC runtime ID `runtime_tx_replay_corpus` and start idempotency key `runtime_event_start_runtime_tx_replay_corpus`.
3. Phase 5B `validate_start_payload()` hard-requires `payload.transaction_id == RUNTIME_TRANSACTION_ID`, so a variable workflow ID alone would not make live per-turn publish safe.
4. Phase 5C `build_start_payload_from_safe_fields()` delegates into the Phase 5B validator and therefore inherits the fixed-payload limitation.
5. The Phase 5B workflow itself stores `payload.transaction_id` and can support variable IDs after validator changes.
6. Phase 5D plan explicitly left the open question that Phase 5E should probably be “variable synthetic runtime IDs + local runtime publish adapter” before any true Gateway → Temporal start.
7. No `AI_FLOW.md` exists in this repository worktree; `AGENTS.md` is the repo-local developer guide. The user’s established Sachima workflow still applies: design before code, TDD after approval, low-intrusion first.

## Planning Decision

Phase 5E should implement the recommended Option B from the plan:

```text
contract-first variable IDs + prototype-only local publish adapter
```

This stage should **not** add live Gateway → Temporal wiring. It should:

1. derive variable opaque runtime IDs from safe shadow refs;
2. propagate variable ID support through Phase 5A/5B/5C contracts;
3. update the Phase 5D publisher summary to emit variable IDs;
4. add a prototype-only adapter that consumes a Phase 5D summary through a caller-supplied local runtime client/fake runtime client;
5. keep all production Gateway/platform/tool/config surfaces unchanged.

## Draft Plan Saved

- `docs/plans/2026-05-06-flowweaver-phase5e-variable-runtime-ids-local-publish-adapter.md`

## Proposed Implementation Boundary

If approved, Phase 5E implementation covers only:

- `gateway/flowweaver_runtime_identity.py`
- `gateway/flowweaver_runtime_contract.py`
- `gateway/flowweaver_shadow_publisher.py`
- `tests/gateway/test_flowweaver_runtime_identity.py`
- `tests/gateway/test_flowweaver_shadow_publisher.py`
- `tests/gateway/test_flowweaver_runtime_contract.py` if needed
- `prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/publication_adapter.py`
- `prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/__init__.py` only if useful for export
- `tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py`
- `tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py`
- this dev log

Still not approved without separate explicit user instruction:

- live Gateway → Temporal publish from `gateway/run.py`
- any `gateway/run.py` change unless Phase 5E is revised and explicitly reapproved by the user
- importing Phase 5B/5C prototype runtime packages from Gateway production code
- Temporal test environment, workers/services/Docker/daemon/Temporal CLI
- Gateway restart
- platform adapter changes
- global tool registry/toolset changes
- production config writes
- new base dependency changes
- real secrets or credentials
- PR merge
- remote branch deletion

## Planning Verification Log

Initial plan authored.

Initial doc gate:

- `git diff --check`: passed.
- custom doc marker/scope/changed-file/ignored-file/sensitive/private-ID scan: passed after adding exact no-live-Gateway/Signals boundary markers.

Independent review pass 1:

- Plan/spec review: FAIL with two boundary consistency blockers.
  1. `tests/gateway/test_flowweaver_runtime_contract.py` appeared in Task 3/Task 10 but not in the plan modify allowlist.
  2. The plan conditionally allowed modifying `tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py`, but the dev log implementation boundary omitted it.
- Security/low-intrusion review: FAIL with four blockers.
  1. Optional Temporal test-environment integration effectively approved worker/test-server startup inside Phase 5E.
  2. `gateway/run.py` wording allowed a reviewer to approve a production Gateway entrypoint change without revised user approval.
  3. Local publish adapter wording allowed runtime client factories, which could hide connect/startup behavior.
  4. Adapter scan wording only covered module-import-time forbidden imports, not lazy/function-local imports or connect/startup terms.

Plan/dev-log revisions made after review:

- Added `tests/gateway/test_flowweaver_runtime_contract.py` to the plan/dev-log file boundary.
- Removed/deferred all optional Temporal integration files and commands from Phase 5E.
- Changed `gateway/run.py` from a soft no-change preference to a hard stop-and-reapprove boundary.
- Required the local publish adapter to consume only an already-created caller-supplied `runtime_client` object; no factories, addresses, connect helpers, or client construction.
- Tightened adapter source/diff scans to cover all added lines and function-local imports/connect/startup terms, not just module-import-time imports.

Final planning gate after blocker fixes:

- `git diff --check`: passed.
- custom doc marker/scope/changed-file/ignored-file/sensitive/private-ID scan: passed.
- blocker-only plan/spec re-review: PASS, no blockers.
- blocker-only security/low-intrusion re-review: PASS, no blockers.

Final doc gate after this evidence append: passed (`git diff --check` and custom doc marker/scope/changed-file/ignored-file/sensitive/private-ID scan).

## Implementation Log

Timestamp: 2026-05-06 09:36:05 CST +0800

User approval for implementation:

```text
开始执行下一个阶段
```

Implementation started from the existing Phase 5E worktree/branch:

```text
/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5e-variable-runtime-ids-local-publish-adapter
feat/flowweaver-phase5e-variable-runtime-ids-local-publish-adapter
```

Files created:

```text
gateway/flowweaver_runtime_identity.py
tests/gateway/test_flowweaver_runtime_identity.py
tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py
tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/publication_adapter.py
```

Files modified:

```text
gateway/flowweaver_contract.py
gateway/flowweaver_runtime_contract.py
gateway/flowweaver_shadow_publisher.py
prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py
tests/gateway/test_flowweaver_shadow_publisher.py
docs/plans/2026-05-06-flowweaver-phase5e-variable-runtime-ids-local-publish-adapter.md
docs/dev_log/2026-05-06-flowweaver-phase5e-variable-runtime-ids-local-publish-adapter.md
```

Implementation summary:

1. Added pure runtime identity derivation in `gateway/flowweaver_runtime_identity.py`.
   - Accepts exact plain safe shadow ref fields and optional safe `created_at` turn timestamp.
   - Returns only synthetic `runtime_tx_shadow_<20-hex>` / `runtime_event_start_shadow_<20-hex>` IDs.
   - Rejects private/platform/secret markers with stable safe reason codes.
2. Extended runtime ingress/start-payload contracts for variable IDs.
   - `build_flowweaver_runtime_ingress_envelope(..., runtime_identity=...)` emits `shadow_ref_hash_v0` idempotency.
   - Phase 5B and Phase 5C validators accept safe variable synthetic runtime IDs while preserving legacy `runtime_tx_replay_corpus` compatibility.
   - Bare embedded private/platform markers such as `chatbad`, `messagebad`, and `platformbad` are rejected.
3. Updated Gateway shadow publisher to use derived variable runtime identity.
   - Ready summaries no longer emit `runtime_tx_replay_corpus` on the live-shadow publication path.
   - Publisher passes safe `created_at` into identity derivation so same-session subsecond turns do not collide.
4. Added prototype-only local publish adapter.
   - `publish_shadow_runtime_publication(publication, *, runtime_client)` consumes only ready Phase 5D summaries.
   - Uses caller-supplied runtime client only; no factories, addresses, connect helpers, service lifecycle, Gateway imports, or Temporal worker/test-environment wiring.
   - Calls `start_transaction()` once, then `record_delivery_ack()` in order, and returns bounded safe results.
5. Adjusted `gateway/flowweaver_contract.py` timestamp precision.
   - `_safe_iso_time()` now preserves microseconds instead of truncating to seconds.
   - This is a blocker-driven minimal change required to make runtime identity truly per shadow turn for fast same-session turns.

RED evidence captured during implementation:

```text
Adapter RED:
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py -q
=> 4 failed: ModuleNotFoundError / FileNotFoundError for missing publication_adapter.py

Publisher variable-ID RED:
scripts/run_tests.sh tests/gateway/test_flowweaver_runtime_identity.py tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py tests/gateway/test_flowweaver_shadow_publisher.py -q
=> 2 failed: publisher still emitted runtime_tx_replay_corpus and reused the fixed ID

Reviewer-blocker RED / regression proof:
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py::test_shadow_publication_adapter_rejects_platform_marker_ids_without_echoing_them -q
=> failed because crafted runtime_tx_shadow_chatbad publication returned success

scripts/run_tests.sh tests/gateway/test_flowweaver_shadow_publisher.py::test_shadow_runtime_publication_uses_different_ids_for_same_session_across_turns -q
=> failed because updated_at=2001.1 and updated_at=2001.2 collided after second-precision truncation
```

Focused GREEN / regression evidence:

```text
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_runtime_identity.py \
  tests/gateway/test_flowweaver_runtime_contract.py \
  tests/gateway/test_flowweaver_shadow_publisher.py \
  tests/gateway/test_flowweaver_shadow_publisher_run_hook.py \
  tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5c_tool_adapter.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py \
  -q
=> 54 passed in 2.76s
```

Compile / lint / diff evidence before final doc append:

```text
python -m py_compile gateway/flowweaver_contract.py gateway/flowweaver_runtime_identity.py gateway/flowweaver_runtime_contract.py gateway/flowweaver_shadow_publisher.py prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/publication_adapter.py tests/gateway/test_flowweaver_runtime_identity.py tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py
=> PASS

ruff check gateway/flowweaver_contract.py gateway/flowweaver_runtime_identity.py gateway/flowweaver_runtime_contract.py gateway/flowweaver_shadow_publisher.py prototypes/flowweaver_phase5b_temporal_poc/src/flowweaver_temporal_poc/payloads.py prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/contracts.py prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/publication_adapter.py tests/gateway/test_flowweaver_runtime_identity.py tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py
=> All checks passed!

git diff --check
=> PASS
```

Independent reviews:

1. Initial plan/spec/code review: BLOCKER.
   - Same-session turns could still collide because identity derived only from snapshot refs.
2. Initial security/low-intrusion review: BLOCKER.
   - Bare `chatbad` / `messagebad` / `platformbad` markers were accepted by validators and adapter could return them.
3. Blocker-only marker/security re-review: PASS.
4. Blocker-only same-session subsecond identity re-review: first BLOCKER, then PASS after preserving microseconds.
5. Final low-intrusion/security re-review after microsecond timestamp change: PASS.

Boundary status:

- No `gateway/run.py` change.
- No `gateway/platforms/**`, `tools/**`, `run_agent.py`, `model_tools.py`, `toolsets.py`, `mcp_serve.py`, production config, global registry, or `pyproject.toml` change.
- No Gateway restart.
- No Docker, Temporal worker/test environment, daemon, service lifecycle, or live Gateway → Temporal wiring.
- No payload-carrying Temporal Signals introduced.

Final post-log gate after this append:

```text
focused tests: 54 passed in 2.77s
py_compile: PASS
ruff check: All checks passed!
git diff --check: PASS
custom changed-file / forbidden Gateway line / adapter source / secret-private-ID / Signal scan: PASS (13 changed files, no failures)
```
