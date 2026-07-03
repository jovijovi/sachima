# Roadmap Status Tracking

This directory contains the lean roadmap status surface for long-running Sachima work.

## Files

- `current-status.md` — current project dashboard: phase, feature/task implementation state, active blockers, explicit non-approvals, and next allowed work.
- `reference-index.md` — stable canonical references and side capability pointers.
- `boundary-register.md` — stable non-approval / drift-guard boundary notes when a boundary needs more detail than the dashboard.
- `superseded-plans.md` — historical roadmap categories that are superseded as active roadmap but retained as support foundation.
- `status-metadata-legacy.md` — extracted legacy metadata kept for archaeology, not current decision-making.

Do **not** recreate routine PR-history ledgers, tail registers, or evidence indexes for Sachima status maintenance. GitHub is the authority for PRs, commits, merge history, CI, and PR review metadata. External evidence paths should be referenced only when they materially support a current stage decision and are not already represented by GitHub/CI/PR metadata.

## Relationship to other project documents

```text
GOAL.md = final goal, north-star principles, and durable product direction
docs/architecture/ = durable architecture authority and diagrams for the current runtime-spine mainline
current-status.md = current phase/task dashboard and next decision surface
reference-index.md = stable references and canonical external links
superseded-plans.md = historical plan categories superseded as active roadmap, retained as support foundation
boundary-register.md = stable boundary detail when the dashboard needs a pointer
GitHub = PR/commit/CI/merge history authority
outputs/ = runtime evidence artifacts, not a roadmap ledger
```

`current-status.md` should answer: where is the project now, what is done, what is not started, what is blocked, and what can be requested next. It should not duplicate GitHub history.

## Agent preflight rule

Before any roadmap, phase-gate, PR, CI, merge, review, or next-phase-readiness work, agents must read `current-status.md` plus the specific plan/runbook/source files relevant to the requested task.

Before changing files, the agent must identify:

- the current phase position;
- relevant feature/task status;
- explicit non-approvals;
- active blockers/gates that affect the requested work;
- whether the requested task is allowed by the current dashboard.

If `current-status.md` is missing, stale, or contradicts live GitHub/repo truth, stop and report the drift risk before making changes.

## Dynamic status policy

`current-status.md` intentionally has no machine-owned dynamic status block. Live GitHub/CI truth stays outside the dashboard and must be checked fresh for PR, merge, and runtime decisions.

Older status-sync tooling may still exist for guard tests, but agents should not recreate a machine-owned PR/head/check ledger in `current-status.md`. If a future automation change is needed, it must preserve the lean dashboard policy.

## Update rule

Update `current-status.md` when the current phase, feature/task state, blocker/gate state, explicit non-approval summary, or next allowed work changes.

Do not update it merely because a PR merged. GitHub already records that. If a PR changes the project phase/task state, update the relevant row and cite the feature/task outcome, not a PR ledger.
