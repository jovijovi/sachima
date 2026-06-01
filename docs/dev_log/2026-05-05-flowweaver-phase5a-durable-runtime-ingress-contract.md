# FlowWeaver Phase 5A — Durable Runtime Ingress Contract Dev Log

Timestamp: 2026-05-05 12:21:44 CST +0800

## Scope

Implement Phase 5A: a pure, in-memory durable runtime ingress contract helper that consumes only safe Phase 4F/4G/4H outputs and returns a versioned runtime envelope for future durable orchestration.

This phase must not connect Temporal, import `temporalio`, start workers, start services, persist events, wire Gateway runtime behavior, mutate platform adapters, or change visible IM behavior.

## User approval

User approved entering Phase 5A in Feishu:

```text
OK，先做5A阶段
```

## Branch and worktree

```text
branch: feat/flowweaver-phase5a-durable-runtime-ingress-contract
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase5a-durable-runtime-ingress-contract
base: origin/feature/sachima-channel @ a3227b4b68f6fe289249fdf01a6708089836009f
```

Canonical repo before branching:

```text
path: /home/ubuntu/workspace/hermes/repo/sachima
branch: feature/sachima-channel
canonical/origin ahead-behind: 0 / 0
open PRs on base: []
```

Canonical had existing local untracked items outside this worktree:

```text
.hermes/
docs/plans/2026-04-24-sachima-channel.md
docs/superpowers/
```

These were not copied into the Phase 5A worktree and are not part of this phase.

## Baseline verification

Command:

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
142 passed in 18.38s
```

## Context inspected

```text
AGENTS.md
docs/plans/2026-05-05-flowweaver-phase5-architecture-gate.md
gateway/flowweaver_mock_durable.py
gateway/flowweaver_shadow_dry_run.py
tests/gateway/test_flowweaver_mock_durable_consumer.py
tests/gateway/test_flowweaver_shadow_dry_run.py
```

## Planned files

Allowed files:

```text
docs/plans/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md
docs/dev_log/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md
gateway/flowweaver_runtime_contract.py
tests/gateway/test_flowweaver_runtime_contract.py
```

Explicitly not planned:

```text
run_agent.py
model_tools.py
toolsets.py
cli.py
hermes_cli/*
gateway/run.py
gateway/platforms/*
Temporal / temporalio / workflow / worker / client / Docker / daemon / service / persistence / Gateway restart
```

## Design status

Plan drafted:

```text
docs/plans/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md
```

Planned helper:

```text
gateway/flowweaver_runtime_contract.py
```

Planned public surface:

```python
FLOWWEAVER_RUNTIME_CONTRACT_TYPE = "flowweaver.gateway.runtime_ingress_contract.v0"
FLOWWEAVER_RUNTIME_ENVELOPE_TYPE = "flowweaver.gateway.runtime_ingress_envelope.v0"
FLOWWEAVER_RUNTIME_ACCEPTED = "accepted"
FLOWWEAVER_RUNTIME_REJECTED = "rejected"
FLOWWEAVER_RUNTIME_MODEL_VERSION = "flowweaver.runtime.v0"

def describe_flowweaver_runtime_ingress_contract() -> dict[str, object]: ...
def build_flowweaver_runtime_ingress_envelope(contract_descriptor, replay_corpus, mock_durable_projection, dry_run_summary=None) -> dict[str, object]: ...
```

## Verification before implementation

Planned checks for docs before code:

```bash
git check-ignore -v planned files || true
git add -N docs/plans/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md docs/dev_log/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md
git diff --check -- docs/plans/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md docs/dev_log/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md
python doc marker / allowlist / forbidden-runtime / sensitive scan
```

Initial doc-only check result:

```text
git diff --check: passed
doc marker scan: passed
allowed-file scan: passed
forbidden-runtime scan: passed
sensitive/private-id scan: passed
```

## TDD RED

Added `tests/gateway/test_flowweaver_runtime_contract.py` before production code.

First focused RED command:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_runtime_contract.py::test_runtime_ingress_contract_describes_allowed_inputs_and_forbidden_side_effects \
  tests/gateway/test_flowweaver_runtime_contract.py::test_runtime_ingress_envelope_accepts_descriptor_corpus_mock_projection_and_dry_run_summary \
  tests/gateway/test_flowweaver_runtime_contract.py::test_runtime_ingress_envelope_projects_counts_events_and_claim_check_requirements_only \
  -q
```

Observed expected failure because the new helper did not exist yet:

```text
ModuleNotFoundError: No module named 'gateway.flowweaver_runtime_contract'
```

This confirmed the tests were RED for the intended missing Phase 5A surface.

## GREEN implementation

Implemented `gateway/flowweaver_runtime_contract.py` as a pure in-memory helper.

Key behavior:

- `describe_flowweaver_runtime_ingress_contract()` returns a static, versioned runtime ingress contract descriptor.
- `build_flowweaver_runtime_ingress_envelope(...)` accepts only plain built-in `dict`/`list`/primitive Phase 4F/4G/4H outputs.
- Outputs contain only envelope metadata, counts, event names, idempotency strategy, claim-check policy, checks, and `side_effects: []`.
- Rejected outputs never echo raw input values.
- Hostile `Mapping`, non-plain keys, temporal-client-like objects, platform ACK payloads, private IDs, and post-validation re-read attacks are rejected.

Focused GREEN command:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_runtime_contract.py -q
python -m py_compile gateway/flowweaver_runtime_contract.py tests/gateway/test_flowweaver_runtime_contract.py
```

Observed:

```text
10 passed in 0.39s
py_compile: passed
```

A first regression verification chain used one stale test selector and failed with `no tests ran` / exit 5. Treated as verifier failure, rediscovered node IDs with `--collect-only`, corrected the selector list, and reran the full focused chain.

Corrected focused regression command:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_runtime_contract.py \
  tests/gateway/test_flowweaver_shadow_dry_run.py \
  tests/gateway/test_flowweaver_mock_durable_consumer.py \
  tests/gateway/test_flowweaver_shadow_tap.py \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_tap_collects_progress_when_visible_progress_is_off \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_tap_attaches_consumer_capture_without_visible_side_effects \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_tap_audit_ready_without_visible_side_effects \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_tap_replay_probe_without_visible_side_effects \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_tap_replay_corpus_without_visible_side_effects \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_mock_durable_consumer_without_visible_side_effects \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_dry_run_default_off_no_result_key \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_dry_run_requires_explicit_dry_run_gate \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_dry_run_runs_without_visible_side_effects \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_dry_run_preserves_legacy_tool_progress_when_visible \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_dry_run_feishu_card_mode_does_not_send_or_patch_when_tracker_disabled \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_dry_run_config_matrix_preserves_visibility_boundaries \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_tap_default_off_preserves_existing_no_progress_behavior \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_tap_streamed_final_text_counts_as_answered_coverage \
  tests/gateway/test_run_progress_topics.py::test_flowweaver_shadow_tap_preserves_legacy_tool_progress_when_progress_is_visible
python -m py_compile \
  gateway/flowweaver_runtime_contract.py \
  tests/gateway/test_flowweaver_runtime_contract.py \
  gateway/flowweaver_shadow.py \
  gateway/flowweaver_mock_durable.py \
  gateway/flowweaver_shadow_dry_run.py
```

Observed:

```text
85 passed in 10.63s
py_compile: passed
```

## Pre-PR verification

Pre-review gate after implementation and test fixture cleanup:

```text
focused FlowWeaver regression: 85 passed in 10.58s
py_compile: passed
git diff --check: passed
allowed-file scan: passed
forbidden-path scan: passed
runtime side-effect/import scan: passed
secret/private-id scan: passed
static security scan: passed
marker scan: passed
changed files:
  docs/dev_log/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md
  docs/plans/2026-05-05-flowweaver-phase5a-durable-runtime-ingress-contract.md
  gateway/flowweaver_runtime_contract.py
  tests/gateway/test_flowweaver_runtime_contract.py
```

Independent review result:

```text
spec / low-intrusion reviewer: PASS, no blockers
security / no-leak / TOCTOU reviewer: PASS, no blockers
```

Non-blocking suggestions handled before final gate:

- Removed unused `Sequence` import from `gateway/flowweaver_runtime_contract.py`.
- Aligned Phase 5A plan/dev log allowed-file lists to the actual four-file scope; existing `tests/gateway/test_run_progress_topics.py` remains regression-only and is not modified.

Non-blocking suggestions intentionally deferred:

- Extra nested-value/alias regression cases are useful future hardening, but the current Phase 5A helper already rejects non-exact shapes and this phase should not expand beyond the approved pure ingress-contract landing.

Final pre-PR gate rerun after these review-log updates:

```text
focused FlowWeaver regression: 85 passed in 10.70s
py_compile: passed
git diff --check: passed
changed-file allowlist scan: passed
forbidden-path scan: passed
runtime side-effect/import scan: passed
secret/private-id scan: passed
static security scan: passed
marker scan: passed
```
