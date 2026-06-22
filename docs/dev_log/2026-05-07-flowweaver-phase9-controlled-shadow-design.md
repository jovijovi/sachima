# FlowWeaver Phase 9 — Controlled Shadow Design Gate Dev Log

## Task Background

狗哥 asked to start Phase 9 design on 2026-05-07 after:

```text
Phase 8 PR #40 was verified merged.
Local canonical repo was synchronized to affca9fea65fd5c7de2c6985be6fc9510c13e879.
Gateway restart was separately completed and verified active/running with a new PID before Phase 9 design began; this is historical context only, not a Phase 9 prerequisite or action.
```

Current merged context:

```text
Phase 5: Durable Runtime Foundation through 5K — merged
Phase 6: Gateway ACK Shadow Bridge — merged
Phase 7: Gateway Shadow E2E Loop — merged
Phase 8: Production Readiness Gate — merged
Current base: origin/feature/sachima-channel @ affca9fea65fd5c7de2c6985be6fc9510c13e879
```

Phase 9 target:

```text
Design a default-off controlled-shadow contract that consumes the Phase 8 readiness report and static control descriptors, then defines a future prototype-only plan builder for sanitized observation/replay. It must not enable production Gateway wiring or real IM side effects.
```

This phase remains design-first, docs-only, prototype-only, default-off, and production-zero until 狗哥 explicitly approves implementation.

## Problems Encountered

- The term “Shadow” can sound like live production mirroring. Phase 9 must define it precisely as controlled observation/replay, not production takeover.
- Phase 8 says only `ready_for_controlled_shadow_design`; it does not authorize controlled-shadow implementation, real Gateway wiring, or real delivery effects.
- The tempting shortcut is to wire the Gateway now. That remains out of scope and requires a separate future design/approval.
- Existing integration tests still require direct hermetic pytest; `scripts/run_tests.sh` intentionally ignores `tests/integration/**`.
- The Sachima worktree has both `origin` and `upstream`; GitHub CLI commands must use explicit `--repo jovijovi/sachima`.

## Root Cause Analysis

Phase 8 created a readiness report but not a controlled-shadow contract. Without Phase 9, future work could blur these separate concerns:

```text
1. readiness to design controlled shadow,
2. static controlled-shadow plan construction,
3. prototype shadow dry-run execution,
4. production Gateway integration.
```

Those concerns need hard phase boundaries. Phase 9 should design only the second item and keep the last two as separate future approvals.

## Solution

Plan saved:

```text
docs/plans/2026-05-07-flowweaver-phase9-controlled-shadow-design.md
```

Proposed design summary:

```text
Phase 8 readiness report
  + shadow scope descriptor
  + Gateway observation boundary
  + runtime execution boundary
  + artifact policy
  + rollback policy
  -> controlled-shadow plan
  -> verification matrix
  -> required separate approvals
```

Hard boundaries:

```text
No production Gateway/Feishu/Sachima integration.
No gateway/run.py or gateway/platforms/** behavior changes.
No run_agent.py, model_tools.py, toolsets.py, tools/**, hermes_cli/** changes.
No production tool registration, Gateway restart, Docker/daemon/service startup, global registry/config writes, or external simulator repo changes.
No Temporal client/Worker construction inside the future Phase 9 module.
No payload-carrying Temporal Signals.
All production actions require separate approval.
No raw platform/card/media/prompt/tool output/secret material in inputs, reports, fixtures, logs, or docs evidence.
```

## Alternatives Considered

- Direct production Gateway integration: rejected. Phase 8 only authorizes controlled-shadow design, not production activation.
- Implementing a live Gateway observer in Phase 9: rejected. Observation can be designed, but live Gateway behavior remains a later separately approved phase.
- External `sachima-im-simulator` repo changes: rejected for this repo phase. Simulator repo work needs its own plan/branch/PR.
- Starting Temporal Workers or service lifecycle in this phase: rejected. Future Phase 9 implementation should be pure and lifecycle-free; runtime/worker lifecycle remains separate.
- Returning production activation verdicts: rejected. Phase 9 must not emit or imply production enablement. The strongest allowed future prototype verdict is `ready_for_controlled_shadow_prototype`, and even that means prototype-only controlled-shadow planning, not production launch.

## Verification

Baseline repo/worktree state:

```text
canonical repo: /home/ubuntu/workspace/hermes/repo/sachima
Phase 9 worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase9-controlled-shadow-design
Phase 9 branch: feat/flowweaver-phase9-controlled-shadow-design
Base HEAD: affca9fea65fd5c7de2c6985be6fc9510c13e879
```

Design-gate verification current status:

```text
1. Relevant skills loaded: GitHub PR workflow, workspace worktree discipline, writing-plans, Temporal durable orchestration, native IM channel, local runtime reconciliation, Gateway simulator loop verification, Codex, verification-before-completion, requesting-code-review.
2. Canonical repo inspected and confirmed on feature/sachima-channel at Phase 8 merge commit.
3. Phase 8 plan/dev log/runbook/readiness module inspected.
4. Phase 7 shadow loop and Gateway shadow publisher surfaces inspected.
5. Phase 9 isolated worktree created from origin/feature/sachima-channel.
6. Phase 9 plan/dev log drafted.
7. Document gate and custom safety scan: PASS after adding exact hard-boundary markers.
8. Codex fresh-context design review: BLOCK on incomplete exact Phase 8 report contract.
9. Patch applied: `readiness_report` input contract now lists the actual merged Phase 8 success report top-level fields, candidate contract fields, required checks including `delivery_targets_match_snapshot`, required separate approvals, and `runbook_outline` handling.
10. Patch applied: Gateway restart mention clarified as historical context only, not a Phase 9 prerequisite or action.
11. Codex blocker-only re-review: PASS, blockers none.
12. Pending: final document gate after this evidence append, commit, push, PR.
```

## Follow-up Notes

- Phase 9 design approval will not equal implementation approval.
- If implementation is later approved, follow strict TDD: RED tests first, then minimal pure implementation, then focused/regression/static/custom gates.
- Reviewer blockers must be fixed by patching tests/docs first where applicable, then re-reviewed.
- Any future production action remains separate approval.
