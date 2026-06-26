# Dev log — P6-B Stage-2 bounded real-smoke readiness/governance

Date: 2026-06-27
Branch: `docs/p6b-stage2-readiness-governance`
Status: Docs-only readiness packet in progress. No real smoke, no AGENT launch.

## Scope binding

The user approved moving to P6-B Stage-2 readiness/governance with the explicit instruction to first审死 the real read-only planning/report step command, role, evidence, and crash/recovery rules before any real-smoke execution approval is requested.

Hermes interpreted this as a docs/status-only governance branch. It does not authorize source implementation, host-local provisioning, acpx/npx invocation, real agent execution, Gateway/Feishu/live behavior, production config, service restart, write roles, or real delivery.

## Preflight evidence

- Isolated worktree created at `worktrees/sachima/p6b-stage2-readiness-governance` from `sachima/release/sachima` head `55070ad61c0b53dc75b4bbc5545788ae2dc363cd`.
- Repository authority read: `GOAL.md`, `AGENTS.md`, `docs/roadmap/current-status.md`, `tail-register.md`, `boundary-register.md`.
- P6-B Stage-1 source, prompt builder, tests, implementation plan, manifest, and dev log inspected.
- CodeGraph was not available for this fresh worktree; Hermes used direct file/source inspection instead and did not initialize a new index.

## Claude Code architect/docs review

Claude Code `2.1.193` was invoked in safe-mode read-only mode with `Read/Grep/Glob` tools only. It produced a report outside the repo, and Hermes verified the worktree git status/diff hash before and after the run stayed unchanged.

Claude verdict:

```text
readiness/governance packet: PASS_WITH_WATCH
real smoke execution: BLOCKED
```

Blockers before real smoke:

- B1: cross-process crash / recover-without-relaunch is unproven because the current controlled-exec claim store is in-process.
- B2: exact smoke parameters are not pinned: binary path/version/sha, role overlay digest, workflow/step/output contract, max bounds, out-of-repo workdir, evidence root, artifact sink behavior.

## Decision recorded by this branch

This branch writes the readiness PRD, technical solution, Claude architect review, manifest, user review packet, and roadmap/tail/boundary status updates. It intentionally does **not** ask the user to approve real smoke execution.

The next safe approval after merge is host-local DoR / crash-no-relaunch proof and parameter pinning, still with no real agent launch.

## Non-approvals preserved

No source implementation, no host-local provisioning, no real AGENT/acpx/npx launch, no real smoke, no write roles, no file/git/network mutation by the agent step, no Gateway/Feishu/IM/live/public ingress, no production config, no service restart, no real delivery, no broader controlled AI FLOW expansion, and no clean active-run cancellation claim.
