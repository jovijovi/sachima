# FlowWeaver Phase 19–21 Temporal Integration Roadmap Dev Log

## Task Background

狗哥 asked to land the Phase 19–21 development roadmap as documentation after Phase 18 was completed and merged.

```text
Base branch: feature/sachima-channel
Base commit: e6af3ade5faf5fddb0ddb7041db41516efb6b084
Roadmap branch: docs/flowweaver-phase19-21-temporal-roadmap
Roadmap worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/docs-flowweaver-phase19-21-temporal-roadmap
```

This is a docs-only planning PR. It does not implement Gateway behavior, Temporal wiring, config writes, service lifecycle, Gateway restart, platform adapter changes, send/edit/render/callback behavior, or production shadow enablement.

## Intent

Capture the compressed roadmap discussed with 狗哥:

```text
Phase 19: controlled Gateway observation bridge to Temporal.
Phase 20: guarded observation validation with local/staging Temporal evidence.
Phase 21: narrow production-shadow observation-only rollout.
```

The key planning decision is to stop adding more pure artifact-only phases unless a concrete blocker appears. Phase 19 should be the first behavior-bearing Temporal connection step.

## Files Added

```text
docs/plans/2026-05-09-flowweaver-phase19-21-temporal-integration-roadmap.md
docs/dev_log/2026-05-09-flowweaver-phase19-21-temporal-integration-roadmap.md
```

## Context Inspected

```text
docs/plans/2026-05-09-flowweaver-phase18-guarded-live-gateway-observation-validation.md
docs/dev_log/2026-05-09-flowweaver-phase18-guarded-live-gateway-observation-validation.md
docs/dev_log/2026-05-08-flowweaver-phase17-guarded-live-gateway-observation-enablement.md
docs/dev_log/2026-05-08-flowweaver-phase16-operator-live-gateway-observation-decision-gate.md
docs/dev_log/2026-05-07-flowweaver-phase8-production-readiness-gate.md
docs/dev_log/2026-05-07-flowweaver-phase7-gateway-shadow-e2e-loop.md
docs/dev_log/2026-05-06-flowweaver-phase5j-activity-claim-check-boundary.md
docs/dev_log/2026-05-05-flowweaver-phase5b-local-temporal-poc.md
Temporal durable orchestration skill guidance
Codex read-only sanity check from the preceding planning discussion
```

## Roadmap Summary

```text
Phase 19 -> ready_for_guarded_temporal_observation_validation
Phase 20 -> ready_for_production_shadow_observation_request
Phase 21 -> ready_for_separate_delivery_or_agent_execution_design
```

Phase 19 is the first controlled connection point:

```text
Gateway observation ingress
  -> sanitized observation envelope
  -> runtime control surface start/query
  -> Temporal runtime client
  -> safe workflow snapshot
```

It remains observation-only. No phase in this roadmap gives Temporal authority over delivery, rendering, callbacks, or agent/tool execution.

## Boundaries Preserved

```text
No gateway/run.py changes in this docs-only PR.
No run_agent.py changes.
No gateway/platforms/** changes.
No production config writes.
No production tool registry writes.
No Gateway restart.
No real send/edit/render/callback.
No production shadow enablement.
No Temporal client/Worker/service lifecycle changes in this docs-only PR.
No payload-carrying Temporal Signals.
No raw prompt/tool/card/media/platform/Gateway/runtime/callback material in docs evidence.
```

The roadmap itself names future implementation files, but this PR does not create those behavior files.

## Verification Plan

Docs-only verification for this roadmap PR:

```text
1. git check-ignore for new docs paths.
2. git diff --check.
3. custom docs gate for required phase markers, changed-file scope, and forbidden live-action wording.
4. Codex read-only planning review with PASS/BLOCK verdict.
5. final docs gate after any review patch.
```

## Initial Draft Notes

The plan intentionally allows Phase 19 to consider a narrow observation-only Gateway hook after separate Phase 19 approval. That is the point of the compression: stop proving only helper artifacts and start validating the real controlled seam.

At the same time, the plan keeps production operations split into separate approvals:

```text
config write
Gateway restart
Temporal service/Worker lifecycle
production-shadow enablement
platform adapter mutation
send/edit/render/callback behavior
agent/tool execution
```

## Verification Results

Docs path ignore check:

```text
git check-ignore -v docs/plans/2026-05-09-flowweaver-phase19-21-temporal-integration-roadmap.md docs/dev_log/2026-05-09-flowweaver-phase19-21-temporal-integration-roadmap.md
# no output; files are not ignored
```

Whitespace / patch hygiene:

```text
git add -N docs/plans/2026-05-09-flowweaver-phase19-21-temporal-integration-roadmap.md docs/dev_log/2026-05-09-flowweaver-phase19-21-temporal-integration-roadmap.md
git diff --check
# PASS
```

Custom docs gate:

```text
DOC_GATE: PASS
changed_files:
- docs/dev_log/2026-05-09-flowweaver-phase19-21-temporal-integration-roadmap.md
- docs/plans/2026-05-09-flowweaver-phase19-21-temporal-integration-roadmap.md
```

Codex read-only planning review:

```text
VERDICT: PASS
BLOCKERS: none
```

Codex notes confirmed:

```text
- Phase 19 is behavior-bearing: controlled Gateway observation bridge, default-off policy, caller-supplied runtime surface, and start/query-only tests.
- Production effects remain separately gated: config writes, restarts, platform adapter changes, production shadow, send/edit/render/callback, and agent execution.
- Temporal history protection is explicit.
- Worker/service lifecycle remains outside Gateway ownership.
- Worktree diff is docs-only for the two reviewed files.
```

Final gate rerun after this evidence append:

```text
FINAL_DOC_GATE: PASS
changed_files:
- docs/dev_log/2026-05-09-flowweaver-phase19-21-temporal-integration-roadmap.md
- docs/plans/2026-05-09-flowweaver-phase19-21-temporal-integration-roadmap.md
```
