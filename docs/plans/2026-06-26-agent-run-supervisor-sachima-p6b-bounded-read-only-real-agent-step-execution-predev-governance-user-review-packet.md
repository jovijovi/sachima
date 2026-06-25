# P6-B bounded read-only real-agent step execution — User review packet

Date: 2026-06-26
Status: Ready for docs-only PR review; implementation and real smoke remain unapproved.

## What this PR is

Docs-only pre-development governance for P6-B, plus the PR #169 merged-state cleanup folded into this substantive planning branch.

It records the next mainline after merged P6-A:

```text
P6-B: bounded read-only real-agent planning/report step under the existing P6 control surface.
```

## Review result

- Claude Code architect teach-back / no-code solution: **PASS**, readiness **90/100**.
- Codex blocker review: **PASS**, score **91/100**, **BLOCKERS none**.
- Codex provenance: no-bwrap fallback used for read-only review because the host's Codex bwrap/read-only sandbox path is known unavailable; pre/post non-tmp worktree hash matched.

## What this PR does not do

It does not implement source code, run real agents, invoke acpx/npx/Claude/Codex as step bodies, enable write roles, touch Gateway/Feishu/live delivery, write production config, or approve a real smoke. In short: no write roles, no live/Gateway/Feishu, no production config, no real delivery.

## Important WATCH carried forward

A later P6-B implementation must prove concrete no-relaunch / crash-recovery behavior before any real smoke. Existing controlled-exec claim storage is in-process; if implementation cannot demonstrate crash-after-claim / restart / recover-without-relaunch evidence, it must fail closed and remain fake-only.

## Recommended next approval text after this PR

If this PR is reviewed and merged, the next narrow source-implementation approval would be:

```text
approve_agent_run_supervisor_sachima_p6b_bounded_read_only_real_agent_step_execution_implementation_default_off_single_read_only_planning_report_step_pinned_local_runner_only_no_write_roles_no_file_mutation_no_git_mutation_no_live_no_gateway_no_feishu_no_production_config_no_real_delivery_no_real_smoke_without_separate_approval
```

A later real-smoke approval must be separate and must name the exact runner, role, workflow, max turns/time, repo/workdir, and evidence destination.
