# Dev log — Task Workbench TODO Lifecycle PRD

Date: 2026-06-24
Branch: `docs/todo-lifecycle-prd`
Base: `release/sachima` at `9694f0577`
Status: PRD/review gate in progress. No implementation started.

## Operator request

```text
我们讨论一下“TODO待办项”中的显示的待办条目的“生存周期”问题。... 你的这个方案非常好，直接落地为PRD文档。然后让 Claude Code 和 Codex CLI 评估一下，过审后输出最终方案，再走到正规开发流程。备注：Claude Code 推理强度开 xhigh 就可以了。
```

## Fresh preflight

```text
repo: jovijovi/sachima
base_branch: release/sachima
base_head: 9694f0577
canonical checkout clean: yes
open PRs before this branch: 0
worktree: /data/agents/workspace/hermes/worktrees/sachima/todo-lifecycle-prd
branch: docs/todo-lifecycle-prd
```

## Scope

This branch is docs/pre-development governance only. It may create:

- PRD artifact;
- Claude Code review/teach-back/design-readiness artifact;
- Codex CLI independent blocker review artifact;
- final user review packet / implementation-approval recommendation.

It must not add source-code implementation, tests that change runtime behavior, Gateway/Feishu/platform changes, production config writes, service restarts, live/default-on behavior, new model tools, or real delivery changes.

## Artifacts

- PRD: `docs/plans/2026-06-24-task-workbench-todo-lifecycle-prd.md`
- Claude review target: `docs/plans/2026-06-24-task-workbench-todo-lifecycle-claude-review.md`
- Codex review target: `docs/plans/2026-06-24-task-workbench-todo-lifecycle-codex-review.md`
- Final solution packet target: `docs/plans/2026-06-24-task-workbench-todo-lifecycle-final-solution.md`
- Dev log: `docs/dev_log/2026-06-24-task-workbench-todo-lifecycle-prd.md`

## Product decision captured

- Current task workbench TODOs are transaction-scoped.
- Completed TODOs show in final/historical surfaces, not in the next unrelated main task card.
- Partially complete tasks become suspended/carryover state.
- Resuming a suspended task restores its remaining TODOs as current.
- New unrelated topics do not inherit old TODOs in the main TODO block.
- Optional old-work reminders must be compact and separate as `挂起事项`.

## Non-approvals

No implementation, Gateway restart/reload, production config write, live/default-on rollout, platform adapter mutation, new model tool surface, broad transcript inference, or raw log/secret/platform data persistence is approved by this PRD/review gate.

## Current gate status

PRD drafted. Claude Code xhigh review returned `VERDICT: BLOCKED` / 83 due to one P0 product decision gap: natural-language resume was not reconciled with deterministic display. Hermes resolved the product decision in the PRD: resume now requires explicit deterministic signals; broad semantic/LLM-only similarity cannot promote old TODOs to current; ambiguity fails closed. PRD was also tightened for unrelated-topic definition, one-line suspended hint cap, multi-suspended selection, retention/expiry, new-session behavior, state model consistency, `TransactionSnapshot` terminology, and risk register.

Claude blocker-only re-review returned `VERDICT: PASS` / 94.

Codex independent blocker review returned `VERDICT: BLOCKED` / 84. Hermes applied targeted PRD repairs:

- governance reconciliation: this is a docs-only side PRD gate for the task workbench, not P5 Temporal PR B, and it does not update or change roadmap phase authority;
- owner-scope isolation: suspended hints/resume candidates require matching safe `owner_scope_ref` and must not store raw platform/chat/thread/user IDs;
- agent hydration safety: implementation acceptance must cover `AIAgent._hydrate_todo_store`, cached agent `_todo_store` reuse, and `TodoStore.format_for_injection` after compression/restart;
- display/approval wording cleanup: lifecycle state table now separates state/reason, and the future approval phrase allows progress/workbench code while still forbidding Gateway lifecycle/live/config/platform changes.

Codex blocker-only re-review returned `VERDICT: PASS` / 94.

Claude final blocker-only re-review returned `VERDICT: PASS` / 95 on the same final PRD after Codex repairs.

Final solution packet created: `docs/plans/2026-06-24-task-workbench-todo-lifecycle-final-solution.md`.

Next: wait for explicit user approval before implementation.
