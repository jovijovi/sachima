# P6 Controlled AI FLOW execution — User review packet

Date: 2026-06-25
Status: Ready to ask for separate P6-A implementation approval after this docs-only governance PR is reviewed/merged.

## What this governance PR does

This PR is docs-only pre-development governance for P6 controlled AI FLOW execution. It adds:

- P6 PRD.
- Claude Code architect teach-back: PASS, readiness 90/100, no P0 blockers.
- Claude no-code technical solution.
- Codex blocker review: PASS, score 92/100, blockers none.
- Roadmap/current-status update: post-P5 calibration is merged PR #167; this P6 governance branch is the current candidate.
- Manifest/dev log for review evidence.

It does **not** implement P6-A and does **not** execute any runtime/workflow/agent behavior.

## Recommended later implementation scope

Approve a later P6-A implementation PR only for:

```text
Temporal-backed controlled AI FLOW execution through the existing WP4 orchestrator and P5TemporalStepExecutor, with controlled-deterministic or injected/fake step bodies only, default-off behind exact approval tokens, and hermetic-local evidence.
```

The later implementation should be behavior-bearing at the orchestration/runtime layer but fake/deterministic at the agent-execution layer.

## Recommended later implementation surface

Allowed later P6-A files/surfaces should be no broader than:

```text
sachima_supervisor/p6_controlled_ai_flow.py
optional sachima_supervisor/p6_controlled_ai_flow_evidence.py only if projection size requires it
tests/sachima_supervisor/p6_controlled_ai_flow/**
docs/** for plan/dev-log/status/runbook evidence
```

Reused surfaces should remain unmodified by default:

```text
sachima_supervisor/activity_ai_flow_orchestration.py
sachima_supervisor/ai_flow_*.py
sachima_supervisor/p5_temporal/*
sachima_supervisor/p5_runtime_adapter.py
```

Any change outside the allowed surface must be treated as a scope expansion and re-reviewed.

## Required later implementation gates

The later P6-A implementation PR should list and pass these gate families:

- changed-file allowlist for P6-A source/test/docs surfaces;
- forbidden Gateway/Feishu/platform/delivery/import/lifecycle scan;
- no real `acpx`/`npx`/Claude/Codex launch scan;
- no-leak scan over added lines plus WP4 store/query/evidence, P5 Temporal history, and final P6 evidence;
- Temporal SCAN 1 + SCAN 2 reuse/extension;
- duplicate-start / divergent-start / recover / cancel WATCH probes;
- WP4 oracle/conformance tests;
- P5TemporalStepExecutor integration tests;
- hermetic-local Worker end-to-end proof only under ops-owned P5 Temporal lifecycle grant;
- docs/status stale-phrase scan;
- Codex exact-head blocker review.

## Non-approvals that remain in force

```text
real acpx/npx/agent execution
real Claude Code / Codex CLI as P6-A step bodies
write-capable roles
additional or unbounded persistent-session execution
additional or unbounded cancellation execution
clean active-run cancellation claims beyond existing WATCH evidence
Gateway involvement or mutation
Gateway restart/reload
Feishu or IM delivery
platform adapter mutation
public ingress
production cluster or production traffic
production config write
service restart or reload
real delivery
```

WP3b active-run cancellation WATCH remains open; P6-A may propagate WATCH but must not claim clean active-run cancellation.

## Later implementation approval phrase

If approved, use this exact phrase:

```text
approve_agent_run_supervisor_sachima_p6a_temporal_backed_controlled_ai_flow_execution_implementation_controlled_deterministic_or_injected_fake_steps_only_default_off_no_real_agent_execution_no_write_roles_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery
```
