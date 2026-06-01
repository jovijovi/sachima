# FlowWeaver Phase 4H — Gateway Shadow Dry-Run Dev Log

Timestamp: 2026-05-05 01:33:35 CST +0800

## Scope

Plan a default-off Gateway shadow dry-run that executes the safe Phase 4F replay corpus plus Phase 4G mock durable consumer chain inside the Gateway lifecycle without changing visible IM behavior.

This phase should add a dry-run helper and a narrow Gateway seam after approval. It must consume only the current in-memory agent result after the existing FlowWeaver shadow capture has attached safe shadow material, then return/store only a safe dry-run summary. It must not expose raw snapshots, captures, agent results, platform payloads, card JSON, raw command/output, delivery ACKs, or platform identifiers.

Phase 4H implementation status: completed in this worktree after explicit user approval.

No Temporal integration is planned.
No persistence, service startup, Docker, daemon startup, or Gateway restart is planned.
No visible sends/edits/renders are planned.
A default-off Gateway dry-run seam is planned, but only after approval and only under explicit config gates.

## Branch and worktree

```text
branch: feat/flowweaver-phase4h-gateway-shadow-dry-run
worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase4h-gateway-shadow-dry-run
base: origin/feature/sachima-channel @ 083bf8d3f95da43669aba1ac084d48466f9caa75
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

These were not copied into the Phase 4H worktree and are not part of this phase.

## Baseline verification

Command:

```bash
scripts/run_tests.sh \
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
125 passed in 15.55s
```

## Context inspected

Read and used these existing surfaces to constrain the design:

```text
AGENTS.md
gateway/run.py
gateway/flowweaver_shadow.py
gateway/flowweaver_mock_durable.py
tests/gateway/test_run_progress_topics.py
tests/gateway/test_flowweaver_mock_durable_consumer.py
docs/plans/2026-05-04-flowweaver-phase4g-mock-durable-consumer.md
docs/dev_log/2026-05-04-flowweaver-phase4g-mock-durable-consumer.md
```

Relevant existing state:

```text
gateway/run.py
  flowweaver_shadow_enabled is already default-off under display.task_tracker.flowweaver_shadow
  tool_progress_enabled may be true for shadow collection while progress_display_enabled stays false
  progress_tracking_enabled can create a tracker without visible queue for shadow-only collection
  attach_flowweaver_shadow_snapshot(...) runs near the final response return path

gateway/flowweaver_shadow.py
  describe_flowweaver_shadow_consumer_contract()
  replay_flowweaver_shadow_corpus(agent_results, *, attempts=2)
  audit/replay/corpus outputs intentionally omit raw snapshot/capture/payload/platform details

gateway/flowweaver_mock_durable.py
  consume_flowweaver_shadow_corpus_as_mock_durable_state(descriptor, replay_corpus)
  exact-shape descriptor/corpus validation
  synthetic record counts and IDs only
```

## Planned files

Allowed implementation paths planned after approval:

```text
docs/plans/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md
docs/dev_log/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md
gateway/flowweaver_shadow_dry_run.py
gateway/run.py
tests/gateway/test_flowweaver_shadow_dry_run.py
tests/gateway/test_run_progress_topics.py
```

Explicitly not planned:

```text
run_agent.py
model_tools.py
toolsets.py
cli.py
hermes_cli/*
gateway/platforms/*
prototypes/flowweaver_phase3/contracts/flowweaver.v0.schema.json
Temporal / Docker / daemon / service / persistence / Gateway restart
```

## Design status

Plan drafted:

```text
docs/plans/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md
```

Planned public additions after approval:

```python
FLOWWEAVER_SHADOW_DRY_RUN_CONFIG_KEY = "flowweaver_shadow_dry_run"
FLOWWEAVER_SHADOW_DRY_RUN_RESULT_KEY = "flowweaver_shadow_dry_run"
FLOWWEAVER_SHADOW_DRY_RUN_TYPE = "flowweaver.gateway.shadow_dry_run.v0"
FLOWWEAVER_SHADOW_DRY_RUN_PASSED = "passed"
FLOWWEAVER_SHADOW_DRY_RUN_REJECTED = "rejected"

def is_flowweaver_shadow_dry_run_enabled(task_tracker_config) -> bool: ...
def run_flowweaver_gateway_shadow_dry_run(agent_result) -> dict: ...
def attach_flowweaver_gateway_shadow_dry_run(agent_result, *, enabled) -> dict | None: ...
```

The future implementation should attach only a safe dry-run summary under an explicit config gate. It should not copy full mock durable records, raw snapshots, captures, or caller-owned payloads into the dry-run summary.

## Verification before design handoff

Plan-file ignore/whitespace/marker/sensitive-scan check:

```bash
git check-ignore -v planned files || true
git add -N docs/plans/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md docs/dev_log/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md
git diff --check -- docs/plans/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md docs/dev_log/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md
python doc marker and scan script
```

Observed after plan-review blocker patches:

```json
{
  "changed_files": [
    "docs/dev_log/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md",
    "docs/plans/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md"
  ],
  "missing_markers": [],
  "unplanned_changed_files": [],
  "added_line_secret_hits": [],
  "forbidden_path_hits": [],
  "forbidden_runtime_call_hits": []
}
```

Independent plan reviews:

```text
spec / low-intrusion review: PASS
security / no-leak review: PASS
```

Reviewer blockers found and patched before final review:

```text
- clarified that Phase 4H allows a new pure helper module plus only one reopened existing production file, gateway/run.py
- added explicit post-validation re-read regression requirements
- added dry-run logging scan requirements for both helper and gateway/run.py added lines
- added Feishu card-mode no-send/no-patch assertions
```

Final reviewer notes:

```text
No concrete spec-coherence or low-intrusion blockers. The boundary patch is coherent: production code is limited to new pure helper gateway/flowweaver_shadow_dry_run.py plus narrow gateway/run.py wiring at the existing shadow-capture seam.
No concrete no-leak/display-safety blockers. The plan covers post-validation re-read/hostile mapping rejection, no raw payload/ID/card/ACK/secret output, no dry-run logging/print/exception-string logging scans, and Feishu card-mode no-send/no-patch assertions.
```

The design log was updated after those checks; final implementation verification is recorded below.

## Implementation status

Completed after user approval at 2026-05-05 11:13:16 CST +0800.

Changed files:

```text
gateway/flowweaver_shadow_dry_run.py
gateway/run.py
tests/gateway/test_flowweaver_shadow_dry_run.py
tests/gateway/test_run_progress_topics.py
docs/dev_log/2026-05-05-flowweaver-phase4h-gateway-shadow-dry-run.md
```

Implementation summary:

```text
- Added pure in-memory Gateway shadow dry-run helper.
- Added explicit config helper requiring both flowweaver_shadow and flowweaver_shadow_dry_run.
- Added safe dry-run summary only: verdicts, counts, checks, side_effects [].
- Added narrow gateway/run.py seam immediately after existing FlowWeaver shadow capture.
- Added RED/GREEN helper tests, Gateway lifecycle tests, hostile input/no-leak tests, and visibility matrix regressions.
- No Temporal, persistence, platform adapter changes, service startup, Gateway restart, or visible dry-run send/edit/render path.
```

RED/GREEN evidence:

```text
RED helper import: ModuleNotFoundError: No module named 'gateway.flowweaver_shadow_dry_run'
GREEN helper focused: 3 passed
RED Gateway seam: 3 failed / 2 passed because flowweaver_shadow_dry_run key was absent when both gates were enabled
GREEN Gateway seam: 5 passed
Hardening RED: 3 failed / 8 passed for missing-shadow reason, raw snapshot/capture rejection, and mock durable count mismatch
Hardening GREEN: 11 passed
Focused helper + Gateway dry-run set: 17 passed
Visibility matrix: 1 passed
```

Final verification before this dev-log edit:

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
python -m py_compile \
  gateway/flowweaver_shadow_dry_run.py \
  gateway/flowweaver_mock_durable.py \
  gateway/flowweaver_shadow.py \
  gateway/run.py \
  tests/gateway/test_flowweaver_shadow_dry_run.py \
  tests/gateway/test_flowweaver_mock_durable_consumer.py \
  tests/gateway/test_run_progress_topics.py
git diff --check
```

Observed before dev-log edit:

```text
142 passed in 18.12s
py_compile passed
git diff --check passed
```

Static scans before dev-log edit:

```json
{
  "changed_files": [
    "gateway/flowweaver_shadow_dry_run.py",
    "gateway/run.py",
    "tests/gateway/test_flowweaver_shadow_dry_run.py",
    "tests/gateway/test_run_progress_topics.py"
  ],
  "forbidden_paths": [],
  "sensitive_added_line_hits": [],
  "forbidden_runtime_hits": [],
  "forbidden_logging_hits": [],
  "forbidden_send_render_persist_hits": [],
  "production_private_id_hits": []
}
```

Independent implementation reviews:

```text
spec / low-intrusion review: PASS — no concrete blockers
security / no-leak review: PASS — no concrete blockers
```

Reviewer notes:

```text
Implementation stays within allowed production surfaces: new pure helper plus narrow gateway/run.py seam.
Dry-run is default-off and gated behind existing flowweaver_shadow.
No Temporal/persistence/service restart/platform adapter changes found.
Dry-run output is limited to sanitized verdict/count/check metadata.
No visible send/edit/render/Feishu card patch/persistence/logging paths introduced.
```

Final verification after this dev-log edit was rerun before commit:

```text
142 passed in 18.12s
py_compile passed
git diff --check passed
sensitive / forbidden runtime / forbidden logging / send-render-persist / production private-id scans clean
```
