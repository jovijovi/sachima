# agent-run-supervisor × Sachima — Post-P5 status calibration and planning review

Date: 2026-06-25
Status: docs-only status calibration and planning review. This artifact does not approve implementation, execution, live behavior, Gateway/Feishu changes, production config, or real delivery.
Branch: `docs/ars-post-p5-status-calibration`
Base: `release/sachima` at `653511bb8b3b7fd9677d03b04009d15279f93ee8`

## Operator request

```text
先做状态校准。然后基于 sachima 当前最新的现状及项目进度，评估是否要优化/改进当前的规划。
```

## Fresh live truth

Checked before editing:

```text
repository: jovijovi/sachima
base_branch: release/sachima
base_head: 653511bb8b3b7fd9677d03b04009d15279f93ee8
open_prs_against_release_sachima: 0
canonical_checkout: clean
PR #166 state: MERGED
PR #166 head: fa91d148218ee4b7cc0064be754b96f2a08ef543
PR #166 merge_commit: 6c2a1447e512ccba38ea2dd9de4047a303f26706
PR #166 merged_at: 2026-06-25T06:48:07Z
latest machine status sync head: 653511bb8b3b7fd9677d03b04009d15279f93ee8
```

The machine-owned status block already records PR #166 as the latest merged phase-bearing PR and open PR count `0`. The human-authored roadmap prose lagged behind: it still described the code-bearing P5 Temporal PR B implementation as the current candidate.

## Status calibration decision

Calibrate `docs/roadmap/current-status.md` to the following truth:

1. **P5 Temporal PR B implementation is merged.** PR #166 landed the code-bearing Slice 1 under `sachima_supervisor/p5_temporal/`.
2. **P5 Temporal Slice 1 is now the latest durable-runtime implementation evidence.** It adds the Temporal contracts, runtime client, control surface, workflow/activity, StepExecutor bridge, ops-owned worker launcher, hermetic tests, no-leak scans, duplicate-start/recovery/determinism/Gateway-boundary gates, and the final workflow-id / bounded-query blocker fixes.
3. **The merge does not approve production/live expansion.** It still does not approve a production cluster (`sachima-p5-prod`), production traffic, Gateway-owned or auto-started runtime lifecycle, P6 real `acpx`/`npx`/agent execution, write roles, Feishu/IM/live/default-on behavior, production config writes, or real delivery.
4. **The next mainline step is not direct execution.** The safe next step is a P6 controlled AI FLOW execution **pre-development governance / PRD / technical-design gate**, because P6 must decide what the first execution slice actually means now that Temporal Slice 1 exists.
5. **WP3b active-run cancellation WATCH remains.** P6 must carry it explicitly instead of pretending active host/ACP cancellation is fully proven.

## Planning evaluation verdict

**Verdict: optimize the current planning, do not replace it.**

The existing roadmap is directionally right:

```text
local/offline supervisor seam -> supervised Activity -> controlled local execution -> sessions/cancellation -> WP4 controlled AI FLOW -> P5 durable runtime -> P6 controlled AI FLOW execution -> live delivery later
```

The issue is not strategy. The issue is that the plan must be recalibrated after P5 Temporal PR B:

- Old P5 prose says the code-bearing PR B implementation is current; it is now merged.
- P6 is currently too broad as a label (`Controlled AI FLOW execution`). Without a pre-development gate, future agents may jump from `Temporal runtime exists` to `real agents execute a workflow`, which is exactly the wrong shortcut.
- The project should reduce pure status churn, but keep the hard safety gates. This calibration folds status cleanup and planning review into one docs-only PR rather than opening a one-line bookkeeping PR.

## Recommended planning optimization

### 1. Reframe P6 as a staged gate, not one big execution leap

Recommended P6 ladder:

```text
P6-predev: PRD + architecture/technical solution + blocker review
P6-A: Temporal-backed controlled AI FLOW with controlled-deterministic / fake-injected steps only
P6-B: bounded read-only real-agent step execution under the same Temporal control surface
P6-C: later write-capable roles / rollback / sandbox gates, still local/offline
P7: Gateway / Feishu / IM / real delivery, separately approved
```

This keeps pressure toward behavior-bearing progress, but avoids mixing first durable execution, real agent launch, write roles, and delivery in one unsafe bundle.

### 2. Make the first P6 implementation slice behavior-bearing but still safe

P6-A should not be another purely fake report if the design can safely exercise the merged P5 Temporal Slice 1. The first implementation candidate should likely be:

```text
Temporal-backed controlled AI FLOW execution using the WP4 executor seam and P5TemporalStepExecutor,
with controlled-deterministic or injected/fake step bodies only,
default-off behind exact approval tokens,
no real acpx/npx/agent execution,
no write roles,
no Gateway/Feishu/live/default-on behavior,
no production cluster/traffic,
no real delivery.
```

That gives concrete forward motion while keeping real-agent execution for P6-B.

### 3. Preserve non-approvals as constraints, not fear language

The next PRD should turn the risks into testable constraints:

- workflow id / durable key trust boundary;
- no raw material in Temporal history or query snapshots;
- duplicate start / retry / replay idempotency;
- cancellation WATCH handling;
- operator gate semantics;
- exact role allowlist and read-only capability gate;
- no Gateway-owned lifecycle imports or startup helpers;
- no Feishu/platform delivery surfaces;
- staged hermetic/local/staging evidence before production talk.

### 4. Fold narrow stale-status repair into the next same-scope PR

This PR updates the major stale authority points created by PR #166. Future tiny wording drift should be folded into the next P6 PR unless it changes safety authority or user-visible phase truth.

## Recommended next approval request

If the operator agrees with this calibration, the next narrow request should be:

```text
approve_agent_run_supervisor_sachima_p6_controlled_ai_flow_execution_predev_governance_docs_only_no_implementation_no_real_agent_execution_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```

Strongest allowed outcome of that request:

```text
P6 PRD + PRD quality review + Claude architecture/teach-back + no-code technical solution + Codex blocker review + user review packet,
ready for a later separately approved P6-A implementation request.
```

## Non-approvals preserved by this calibration

```text
implementation
runtime_or_worker_start
workflow_or_activity_execution
controlled_ai_flow_execution
real_acpx_or_npx_or_agent_execution
additional_or_unbounded_persistent_session_execution
additional_or_unbounded_cancellation_execution
write_capable_roles
Gateway involvement or mutation
Gateway restart/reload
Feishu or IM delivery
public ingress
production cluster or production traffic
production config write
platform adapter mutation
real delivery
```
