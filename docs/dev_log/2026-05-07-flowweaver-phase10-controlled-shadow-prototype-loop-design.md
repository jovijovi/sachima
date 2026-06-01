# FlowWeaver Phase 10 — Controlled Shadow Prototype Loop Design Dev Log

## Task Background

狗哥 asked to start Phase 10 design after Phase 9 implementation PR #42 was merged and local canonical `feature/sachima-channel` was synchronized.

```text
Base branch: feature/sachima-channel
Base merge commit: 67a27449e8335565bcedfc0d6ecacd83aaa0ba35
Design branch: feat/flowweaver-phase10-controlled-shadow-prototype-loop-design
Design worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase10-controlled-shadow-prototype-loop-design
Started at: 2026-05-07 16:20:55 CST +0800
```

## Design Target

Phase 10 design defines the next prototype-only step:

```text
exact Phase 9 controlled-shadow plan report
  + bounded sanitized Phase 7-style publication fixtures
  + caller-supplied prototype control surface
  + default-off run policy
  -> safe controlled-shadow prototype loop report
```

The strongest proposed Phase 10 success verdict is:

```text
controlled_shadow_prototype_loop_verified
```

That verdict means only bounded prototype evidence exists. It does not authorize live Gateway observation, production Gateway wiring, production config/tool-registry writes, external Temporal lifecycle, Gateway restart, or real IM effects.

## Hard Boundaries

```text
No production Gateway/Feishu/Sachima integration.
No gateway/run.py changes.
No run_agent.py changes.
No gateway/platforms/** changes.
No production config writes.
No production tool registry writes.
No Docker, daemon, Temporal service, or Gateway restart.
No real send/edit/render/callback.
No Temporal client or Worker construction.
No payload-carrying Temporal Signals.
No live Gateway observation.
```

## Context Inspected

Read and used as source material:

```text
docs/plans/2026-05-07-flowweaver-phase9-controlled-shadow-design.md
docs/dev_log/2026-05-07-flowweaver-phase9-controlled-shadow-implementation.md
docs/runbooks/flowweaver-controlled-shadow-plan-builder.md
docs/runbooks/flowweaver-production-readiness.md
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_shadow_design.py
tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/gateway_shadow_e2e_loop.py
tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py
```

Key findings:

- Phase 9 output shape is a controlled-shadow plan report with `ready_for_controlled_shadow_prototype`.
- Phase 9 implementation returns safe summaries only and no lifecycle objects.
- Phase 7 already provides an async prototype publication-to-ACK loop over a caller-supplied control surface.
- Phase 10 should compose Phase 9 policy + Phase 7 loop, not bypass either.
- Integration tests intentionally fail closed on new FlowWeaver prototype files, so future implementation may need narrow allowlist updates.
- `scripts/run_tests.sh` intentionally ignores `tests/integration/**`; integration regression must use direct hermetic pytest.

## Files Added in This Design PR

```text
docs/plans/2026-05-07-flowweaver-phase10-controlled-shadow-prototype-loop-design.md
docs/dev_log/2026-05-07-flowweaver-phase10-controlled-shadow-prototype-loop-design.md
```

## Docs Gate Plan

Before commit/PR, run:

```bash
git add -N docs/plans/2026-05-07-flowweaver-phase10-controlled-shadow-prototype-loop-design.md docs/dev_log/2026-05-07-flowweaver-phase10-controlled-shadow-prototype-loop-design.md
git diff --check
```

Then run a custom docs-only guard that verifies:

- only the two Phase 10 docs files are changed/untracked,
- required hard boundary markers are present,
- no production Gateway/code/config/registry paths changed,
- no secret-shaped values are added,
- no raw payload/material examples are introduced outside forbidden-material policy labels,
- design says Phase 10 is prototype-only/default-off and not production activation.

## Review Plan

Run fresh-context Codex design review with this scope:

- Does the design consume exact Phase 9 output shape?
- Does it avoid production Gateway wiring and live observation?
- Does it avoid Temporal client/Worker/service lifecycle?
- Does it keep control-surface ownership caller-supplied only?
- Are publication and delivery ACK bounds clear enough for implementation?
- Are artifact/log/report no-leak requirements testable?
- Are docs-only PR gates sufficient?

If Codex finds a blocker:

1. Patch the plan/dev log.
2. Rerun docs gates.
3. Run blocker-only Codex re-review.
4. Only then commit/push/open PR.

## Current Status

Draft created; docs gates and Codex review still pending.

## Codex Fresh-Context Review

Initial Codex design review returned `BLOCK` with one blocker:

```text
Phase 10 said it consumes an exact Phase 9 success report, but the plan under-specified exact validation for verification_matrix, runbook_outline, and controlled_shadow_plan.fail_closed_errors.
```

Patch applied:

- Added the exact Phase 9 `controlled_shadow_plan.fail_closed_errors` sorted list.
- Added exact Phase 9 `verification_matrix` list.
- Added exact Phase 9 `runbook_outline` list.
- Expanded Task 2 RED cases to cover mutated/reordered/missing `verification_matrix`, mutated/reordered/missing `runbook_outline`, incomplete/reordered/duplicate/bogus `controlled_shadow_plan.fail_closed_errors`.

Pending after patch:

- Rerun docs gates.
- Run Codex blocker-only re-review.

Post-patch verification:

```text
POST_BLOCKER_DIFF_CHECK: PASS
POST_BLOCKER_CUSTOM_DOCS_ONLY_GUARD: PASS
```

Codex blocker-only re-review result:

```text
VERDICT: PASS
BLOCKERS: none
NON_BLOCKING_NOTES:
- Working tree diff contains only the two Phase 10 docs additions.
VERIFICATION_COMMENT:
- Phase 10 exact fail_closed_errors, verification_matrix, and runbook_outline blocks match current controlled_shadow_design.py.
- Hard prototype-only boundaries remain present.
- No forbidden path changes or secret-shaped matches found.
```

Pending final action:

- Rerun docs gate after this dev-log evidence append.
- Commit, push, and open the Phase 10 design PR.
