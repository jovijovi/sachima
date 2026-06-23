# Final Solution — Task Workbench TODO Lifecycle

Date: 2026-06-24
Branch: `docs/todo-lifecycle-prd`
Base: `release/sachima` at `9694f0577`
Status: final solution packet after PRD + Claude Code + Codex CLI review. This document authorizes no implementation by itself.

## 1. Review verdict

The Task Workbench TODO Lifecycle PRD is ready to become the basis for a later implementation plan, subject to explicit user approval.

Reviewed artifacts:

- PRD: `docs/plans/2026-06-24-task-workbench-todo-lifecycle-prd.md`
- Claude Code review: `docs/plans/2026-06-24-task-workbench-todo-lifecycle-claude-review.md`
- Codex CLI review: `docs/plans/2026-06-24-task-workbench-todo-lifecycle-codex-review.md`
- Dev log: `docs/dev_log/2026-06-24-task-workbench-todo-lifecycle-prd.md`

Final review results:

| Reviewer | Result | Score | Meaning |
|---|---:|---:|---|
| Claude Code | `VERDICT: PASS` | 95 / 100 | Final blocker-only re-review passed after Codex blocker fixes. |
| Codex CLI | `VERDICT: PASS` | 94 / 100 | Independent blocker re-review passed; prior blockers closed. |

No remaining PRD blocker is known.

## 2. Product decision

The task workbench TODO display is transaction-scoped:

1. Current task TODOs belong to the current logical transaction.
2. Completed TODOs can show once in the final same-task render and remain in history, but do not appear in the next unrelated main task card.
3. Partially complete tasks become suspended/carryover state with a reason and sanitized owner scope.
4. Resuming a suspended task requires an explicit deterministic same-owner signal.
5. Broad natural-language similarity, embeddings, or LLM-only judgment must not promote old TODOs to current.
6. A new request without an explicit resume signal starts a clean current task.
7. Old suspended work can appear only as a separate, bounded, same-owner `挂起事项` hint.

## 3. Final implementation scope recommendation

A later implementation PR should be narrow and behavior-bearing, not another broad planning loop.

Recommended scope:

### Slice A — Lifecycle metadata and owner scope

Add or derive lifecycle metadata around the existing `TransactionSnapshot` / TODO/progress state:

- lifecycle state: `created`, `active`, `completed`, `suspended`, `resumed`, `cancelled`, `archived`;
- suspension reason when suspended: `blocked`, `waiting_user`, `waiting_external`, `failed_recoverable`, `paused`;
- sanitized `owner_scope_ref` for cross-turn hint/resume eligibility;
- lifecycle marker that can be consumed by agent TODO hydration and prompt injection.

`owner_scope_ref` must be a safe ref/digest/label structure. It must not store raw platform IDs, chat IDs, thread IDs, topic IDs, user IDs, card JSON, or message payloads.

### Slice B — Current-task and suspended-task projection

Extend progress reader/store/tracker behavior so:

- explicit empty TODO state clears stale TODOs;
- completed transactions archive instead of staying current;
- suspended transactions remain resumable only within retained same-owner scope;
- old records missing owner scope are historical evidence only, not cross-turn hint/resume candidates;
- event-log rotation, gateway restart, and old JSONL shapes do not resurrect zombie TODOs.

### Slice C — Agent TODO hydration/re-injection safety

The implementation must cover the non-renderer zombie path:

- `AIAgent._hydrate_todo_store()`;
- cached/fresh agent `_todo_store` reuse in Gateway progress snapshots;
- `TodoStore.format_for_injection()` after context compression.

An old pending TODO in transcript history must not enter a new unrelated main TODO block after compression/restart. It may at most become one same-owner scoped suspended hint.

### Slice D — Feishu/Web/API display

Renderer behavior:

- main TODO block shows current transaction only;
- completed items may show once in final same-transaction render;
- resumed transactions show remaining items and summarize completed count;
- unrelated new tasks show no old TODOs in the main block;
- optional suspended hint is one line, one same-owner selected transaction by default, with overflow as count;
- Web/API and Feishu share the same lifecycle semantics.

### Slice E — Test-first gates

Required RED/GREEN coverage:

1. completed transaction -> final card may show completed TODOs -> next unrelated task main TODO is empty;
2. explicit empty TODO list clears stale state;
3. partial transaction -> suspended state with reason, remaining summary, owner scope;
4. same-owner explicit resume -> remaining TODOs return as current;
5. no explicit resume -> clean new transaction;
6. cross user/chat/thread/topic in same profile -> cannot see/hint/resume another scope's suspended work;
7. malformed/old JSONL and event-log rotation -> no zombie TODOs;
8. `_hydrate_todo_store`, cached `_todo_store`, and `format_for_injection` after compression -> old pending TODO not injected into unrelated task;
9. Feishu/Web/API renderer parity;
10. redaction compatibility for local paths, API routes, fake credential-shaped strings, and sanitized owner-scope refs.

## 4. Explicit non-approvals

This final solution does not approve:

- source-code implementation before user approval;
- Gateway restart/reload or service lifecycle change;
- platform adapter mutation;
- live/default-on behavior;
- production config writes;
- Temporal/Worker lifecycle or controlled AI FLOW execution;
- agent/acpx/npx real execution;
- new model tool surfaces;
- public ingress or real delivery;
- raw platform IDs, card JSON, raw prompts, raw logs, raw tool output, credentials, or unbounded history in lifecycle summaries.

It may later approve progress/workbench/TODO lifecycle code and tests only if the user explicitly grants that implementation scope.

## 5. Recommended development process after approval

If the user approves implementation, use the governed flow:

1. Create a new implementation worktree/branch from fresh `sachima/release/sachima`.
2. Write a technical implementation plan from this PRD and final solution.
3. Ask Claude Code to act as architect/main programmer with the final PRD, final solution, and both reviews as context.
4. Use TDD: write RED tests for each acceptance gate before implementation.
5. Run focused pytest suites for TODO/progress/run-agent hydration/renderers.
6. Run `git diff --check`, py_compile for touched Python, changed-line secret/static scan, and forbidden-surface scan.
7. Ask Codex CLI for final blocker-only review on the exact pushed head.
8. Open PR only after local gates and independent review pass.
9. Send Feishu approval card bound to the exact PR head SHA.
10. Merge only through the controlled approval path after explicit approval.

## 6. Suggested user approval phrase

If the user wants to start implementation, approve with a phrase like:

```text
批准实现任务工作台 TODO 生命周期：当前任务主显示、已完成归档、未完成挂起、同 owner scope 的显式恢复、无关新话题隔离、agent TODO hydration/re-injection 防僵尸；允许修改 progress/workbench/TODO 生命周期相关代码与测试；保持现有结构化 TODO 来源、Feishu/Web 同源展示、secret redaction、无新增核心工具、无 Gateway 服务生命周期/重启/平台适配/live/config 变更。
```

Without that explicit approval, stop at this final solution packet.

## 7. Open non-blocking design notes

These are not PRD blockers but should be resolved in technical design:

- pin the exact deterministic text/regex set for `继续上一任务`-style commands;
- normalize lifecycle transition diagrams so suspension reasons are not mistaken for lifecycle states;
- decide whether resume actions land first as text commands, renderer buttons, dashboard actions, or a combination;
- decide whether completed-item expansion is Feishu-supported, dashboard-only, or future work;
- define the exact safe digest/opaque-ref mechanism for `owner_scope_ref` without storing raw platform IDs.
