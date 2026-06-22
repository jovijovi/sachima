# FlowWeaver Phase 29–33 Activity Execution Roadmap Dev Log

## Task Background

狗哥 asked to land the post-Phase-28 FlowWeaver planning as phase documentation after questioning whether the next work really needed seven separate blocks.

```text
Base branch: feature/sachima-channel
Base commit: aedd0d8978b5e5cd039b9270a0bea3850bcad733
Roadmap document: docs/plans/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md
Roadmap dev log: docs/dev_log/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md
```

This is a docs-only planning change. It does not implement callable Activities, Temporal wrappers, Gateway hooks, agent/tool execution, delivery ACKs, production config writes, service lifecycle, Gateway restart, platform adapter changes, send/edit/render/callback behavior, or production shadow enablement.

## Intent

Capture the compressed roadmap discussed with 狗哥:

```text
Phase 29: non-production callable stub Activities, including validation.
Phase 30: local Temporal orchestration of stub Activities.
Phase 31: controlled agent/tool execution Activity.
Phase 32: controlled artifact delivery and ACK Activity.
Phase 33: narrow AI FLOW pilot and production-enablement decision packet.
```

The key planning decision is to stop treating the seven work areas as seven pure gates. Phase 29 should be the next behavior-bearing step, but every phase still requires separate approval.

## Files Added

```text
docs/plans/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md
docs/dev_log/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md
```

## Context Inspected

```text
AGENTS.md
docs/plans/2026-05-09-flowweaver-phase19-21-temporal-integration-roadmap.md
docs/dev_log/2026-05-09-flowweaver-phase19-21-temporal-integration-roadmap.md
docs/plans/2026-05-09-flowweaver-phase22-delivery-agent-execution-contract-gate.md
docs/plans/2026-05-09-flowweaver-phase23-stub-activity-orchestration.md
docs/plans/2026-05-09-flowweaver-phase27-stub-activity-implementation-design.md
docs/plans/2026-05-09-flowweaver-phase28-stub-activity-implementation-validation.md
docs/dev_log/2026-05-09-flowweaver-phase28-stub-activity-implementation-validation.md
docs/runbooks/flowweaver-stub-activity-implementation-validation.md
Temporal durable orchestration skill guidance
FlowWeaver roadmap compression reference
```

`AI_FLOW.md` is not present in the `jovijovi/sachima` checkout; the repo-local guide inspected here is `AGENTS.md`.

## Roadmap Summary

```text
Phase 29 -> ready_for_local_temporal_stub_activity_orchestration
Phase 30 -> ready_for_controlled_agent_activity_implementation_request
Phase 31 -> ready_for_controlled_delivery_activity_request
Phase 32 -> ready_for_narrow_ai_flow_pilot_request
Phase 33 -> ready_for_separate_production_enablement_decision
```

Phase 29 is the next concrete phase:

```text
P28 validation artifact
  -> plain callable stub functions
  -> strict sanitized inputs/results
  -> no Temporal SDK
  -> no real agent/tool/Gateway/delivery effects
```

Phase 30 is the first phase that may use Temporal runtime behavior, but only in local/staging harnesses and tests. Gateway still does not own Worker/service lifecycle.

## Boundaries Preserved

```text
No code files changed in this docs-only roadmap task.
No gateway/run.py changes.
No run_agent.py changes.
No gateway/platforms/** changes.
No production config writes.
No production tool registry writes.
No Gateway restart.
No real send/edit/render/callback behavior.
No real delivery ACK updates.
No real agent/tool execution.
No production shadow enablement.
No Temporal client/Worker/service lifecycle changes in this docs-only task.
No raw prompt/tool/card/media/platform/Gateway/runtime/callback material in docs evidence.
```

The roadmap names future implementation files, but this task does not create those behavior files.

## Verification Plan

Docs-only verification for this roadmap task:

```text
1. git check-ignore for new docs paths.
2. git add -N for new docs paths so git diff can see untracked files.
3. git diff --check.
4. custom docs gate for required phase markers, changed-file scope, and forbidden production-enablement wording.
5. independent consistency review.
6. independent security/low-intrusion review.
7. final docs gate after any evidence append or review patch.
```

## Verification Results

Docs path ignore check:

```text
git check-ignore -v docs/plans/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md docs/dev_log/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md
# no output; files are not ignored
```

Whitespace / patch hygiene:

```text
git add -N docs/plans/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md docs/dev_log/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md
git diff --check -- docs/plans/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md docs/dev_log/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md
# PASS
```

Custom docs gate, first run:

```text
DOC_GATE: FAIL
- forbidden production-live verdict literal detected in the plan wording
- forbidden production-enabled verdict literal detected in the plan wording
```

Resolution:

```text
The literals appeared only in a sentence saying the P33 verdict is weaker than production-live enablement verdicts. The sentence was tightened to avoid introducing exact misleading production verdict labels into the roadmap artifact.
```

Custom docs gate, rerun:

```text
DOC_GATE: PASS
changed_files:
- docs/dev_log/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md
- docs/plans/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md
```

Independent consistency review:

```text
VERDICT: PASS
BLOCKERS:
- None found.
```

Independent security / low-intrusion review:

```text
VERDICT: PASS
BLOCKERS:
- None.
```

Final docs gate after this evidence append:

```text
FINAL_DOC_GATE: PASS
changed_files:
- docs/dev_log/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md
- docs/plans/2026-05-09-flowweaver-phase29-33-activity-execution-roadmap.md
```
