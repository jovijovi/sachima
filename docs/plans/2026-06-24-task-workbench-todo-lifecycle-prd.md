# Task Workbench TODO Lifecycle PRD

> Status: PRD draft for pre-development governance. This document authorizes no implementation by itself.

Date: 2026-06-24
Branch: `docs/todo-lifecycle-prd`
Base: `release/sachima` at `9694f0577`

## 1. Product outcome

The Feishu/Sachima task workbench should show TODO items as the live task snapshot for the current user request, without leaking stale TODOs from completed or unrelated prior work. Completed TODOs should become historical evidence; unfinished TODOs should become explicit suspended/carryover state; new unrelated conversations should start with a clean current-task TODO area.

One-sentence rule:

> TODO main display follows the current task transaction; completed items archive; unfinished items suspend; unrelated new topics do not inherit old TODOs.

## 2. Problem statement

The current structured TODO/progress workbench makes task state visible, but a lifecycle policy is needed to avoid zombie TODOs:

- If all TODOs complete, showing the same checkmarked list in the next unrelated turn makes the workbench look stale.
- If some TODOs remain blocked, mixing them into a new unrelated task makes it look like the new task depends on old work.
- If readers infer state from “last seen TODO list” instead of an explicit empty/closed marker, stale TODOs can reappear after context compression, restarts, or event-log reads.
- If old unresolved work is hidden entirely, the user may lose important blockers or approval waits.

The product needs a durable but non-intrusive lifecycle model.

## 3. Authority and baseline

Authority and context checked before drafting:

- `AGENTS.md` — low-intrusion contribution rules and Sachima project references.
- `GOAL.md` — Sachima as a safe, durable, observable IM workbench.
- `docs/roadmap/current-status.md` — latest machine status shows PR #162 `Add structured TODOs to progress workbench` merged and open PR count `0`.

Non-repo authoring inputs used by Hermes, not repository authority:

- local Hermes skill `hardening-user-facing-progress-displays` — task workbench/progress display safety, structured TODO source, redaction, empty TODO clearing, event-log rotation, and Feishu display guidance;
- local Hermes skill `multi-intent-planning` — active-latest request routing and structured TODO creation for 3+ actionable intents.

Those local skills guide the authoring workflow only. Repository authority remains the checked repo files above.

### 3.1 Governance reconciliation

The human-authored roadmap prose in `docs/roadmap/current-status.md` still frames the mainline next governed step around P5 Temporal PR B pre-development governance. This Task Workbench TODO Lifecycle PRD is a **docs-only side PRD gate** for the already-merged progress/TODO workbench surface. It does not replace, advance, or reinterpret the P5 Temporal/P6 runtime roadmap.

This side PRD is allowed because it is limited to product semantics and review artifacts for the user-facing task workbench. It starts no implementation and grants no runtime authority. It does not approve Temporal/Worker lifecycle, controlled AI FLOW execution, agent/acpx/npx execution, Gateway or Feishu live behavior, production config writes, platform adapter mutation, service restart/reload, public ingress, or real delivery.

`docs/roadmap/current-status.md` does not need to be updated for this PRD-only side gate because the change does not alter the current roadmap phase, next approved runtime request, or mainline phase authority. If a later implementation PR materially changes user-facing progress/workbench behavior, that later PR may update status or dev-log surfaces within its own approved scope.

Relevant existing surfaces from PR #162 / task workbench work:

- TODO source: Hermes `todo` tool / `TodoStore`, and structured task plans/gates/delegation states where explicitly wired.
- Progress snapshots/events: `gateway/progress/*` modules.
- Feishu progress card renderer and Web progress API/page.
- Existing stale-clear principle: explicit `todo_items: []` means clear old TODO state; missing TODO state must not silently preserve stale state forever.

## 4. Actors

- User/operator: sends tasks, sees workbench state, may resume suspended work.
- Hermes controller: creates/updates structured TODO state, closes or suspends task transactions, reports lifecycle truth.
- Gateway/progress tracker: persists sanitized progress snapshots and renders Feishu/Web task workbench surfaces.
- Feishu/Sachima renderer: displays current task TODOs and optional suspended-task hints.
- Dashboard/API reader: reads current and historical progress state without resurrecting stale TODOs.
- Reviewer agents: Claude Code reviews PRD/product/design clarity; Codex CLI performs independent blocker review.

## 5. Core concepts

### 5.1 Transaction-scoped TODOs

Each TODO list belongs to a logical user-task transaction, not to the entire chat forever.

A renderer should only put TODOs in the main TODO area when:

```text
todo.transaction_id == current_task.transaction_id
```

or an equivalent current transaction/snapshot ownership condition holds.

### 5.2 Current task TODOs

The main TODO block shows the active task only:

```text
任务工作台
📌 任务：<current task>
🔄 状态：执行中
待办：
- ...current transaction items...
```

### 5.3 Archived completed TODOs

Completed transactions are historical evidence. They may appear in the final render of that task, dashboard history, logs, or explicit “show history” views, but not in the next unrelated task’s main workbench.

### 5.4 Suspended unfinished TODOs

Unfinished work that cannot proceed becomes a suspended/carryover task with explicit status and reason, for example:

- `blocked`
- `waiting_user`
- `waiting_external`
- `failed_recoverable`
- `paused`

Suspended tasks should not be mixed into a new unrelated task’s main TODO list. They may be shown as a compact “挂起事项” hint when useful.

### 5.5 Resume / isolation decision rule

A suspended transaction may re-enter the main TODO area only through an explicit, deterministic resume signal. The minimum approved signals are:

- an explicit resume command targeting the most recent suspended task, e.g. “继续上一任务” / “继续刚才那个”;
- an explicit reference resolvable to exactly one non-terminal transaction, e.g. transaction id, task id, PR number already bound to a suspended transaction, or a renderer-provided resume button/action;
- a current active transaction that is already in progress for this same logical user task.

All resume signals are evaluated only within the same safe owner scope defined in §5.6. A valid-looking resume signal from another user, chat/thread/topic, platform, or profile must not reveal or resume the original suspended task.

Natural-language similarity alone must not decide that old TODOs are current. If a user says something plausibly related but the signal does not resolve to exactly one suspended transaction, the system must fail closed: start a clean current task and/or show a compact clarification/hint, but do not merge old TODOs into the main block.

Definition: an unrelated new request is any request that lacks an explicit resume signal and is not already inside the current active transaction. “Unrelated” does not require semantic proof that topics differ; it is the safe default when no deterministic resume signal exists.

### 5.6 Safe owner scope

Suspended-work hints and resume candidate lookup are scoped to the original task owner boundary. The first implementation must treat a candidate as eligible only when all safe owner-scope components match:

- active Hermes profile;
- platform/channel kind;
- conversation or chat/thread/topic scope;
- initiating user/sender scope.

Raw platform IDs, chat IDs, thread IDs, topic IDs, user IDs, card JSON, or message payloads must not be stored in lifecycle summaries. Instead, persist a sanitized owner-scope reference such as:

```text
owner_scope_ref = {
  profile_label: safe profile label,
  platform_label: safe platform label,
  conversation_scope_digest: non-reversible digest or opaque safe ref,
  user_scope_digest: non-reversible digest or opaque safe ref
}
```

If a safe owner-scope reference is unavailable for an old record, that record may remain historical evidence but must not be used for cross-turn suspended-work hints or text-command resume. Renderer/dashboard explicit actions may carry a safe transaction reference only when the backend can verify the same owner scope before showing details or resuming.

## 6. User scenarios

### Scenario A — all TODOs complete

User asks for a multi-step operation. Hermes creates TODOs, completes all items, and finalizes the transaction.

Expected behavior:

1. During the task, the main workbench shows active TODOs.
2. The final render may show all completed TODOs once.
3. On the next new task, those completed TODOs are not shown in the main workbench.
4. Historical dashboard/event views can still show them as completed evidence.

### Scenario B — partially complete, user continues same topic

A task completes some TODOs but waits on CI, approval, remote service, or user decision. The next user turn continues the same topic.

Expected behavior:

1. The transaction remains resumable/suspended rather than archived as complete.
2. When resumed, the main workbench shows remaining blocked/pending items prominently.
3. Completed items from the same transaction may be collapsed, greyed, or summarized as a count.
4. The blocked reason and required next action are visible.

Recommended rendering:

```text
待办
✅ 已完成 3 项
⚠️ 待处理 2 项

未完成：
- 等待 CI 完成
- 等待用户批准合并
```

### Scenario C — partially complete, new unrelated topic

A previous task remains partially complete, but the user starts a completely unrelated new topic.

Expected behavior:

1. The new task workbench main TODO area shows only the new task’s TODOs, or no TODOs if the new task is simple.
2. The prior task’s unfinished TODOs do not appear as if they belong to the new task.
3. If a reminder is needed, render a separate compact suspended-work hint, not the old TODO list.
4. Low-importance suspended work may remain hidden until the user asks about it.

Recommended optional hint:

```text
挂起事项：上一任务仍有 1 项未完成：等待 CI。发送“继续上一任务”可恢复。
```

## 7. Functional requirements

### FR-1: Transaction ownership

TODO snapshots must carry or be derivable from a logical task/transaction identity sufficient to distinguish current, completed, suspended, and unrelated prior work.

Acceptance intent:

- A new unrelated transaction must not render TODOs from an older transaction in the main TODO area.
- A resumed transaction may render its own older unfinished TODOs.

### FR-2: Explicit lifecycle state and suspension reason

A transaction with TODOs must eventually move into one of these lifecycle states:

- `created`
- `active`
- `completed`
- `suspended`
- `resumed`
- `cancelled`
- `archived`

When lifecycle state is `suspended`, it must also carry a suspension reason such as:

- `blocked`
- `waiting_user`
- `waiting_external`
- `failed_recoverable`
- `paused`

The exact implementation may map these product states onto existing status fields if it preserves the distinction between lifecycle state and suspension reason. `blocked` / `waiting_*` / `failed_recoverable` are reasons for suspension, not separate terminal lifecycle states in this PRD.

### FR-3: Completed transaction clears current TODO area for future tasks

When a transaction completes successfully, the final same-transaction render may show completed items once, but future unrelated transactions must see a cleared current TODO area.

The implementation must distinguish:

- missing TODO field / old event shape;
- explicit empty TODO list;
- completed transaction with historical TODOs;
- suspended transaction with unfinished TODOs.

### FR-4: Suspended transaction state

When not all TODOs can complete, the system should persist enough sanitized state to resume or summarize:

- transaction/task title;
- suspended status;
- blocker/waiting reason;
- completed count;
- remaining item summaries;
- next action hint;
- last update time or ordering metadata if available;
- `owner_scope_ref` as defined in §5.6 when the transaction may be hinted or resumed across turns.

Raw prompts, raw tool outputs, credentials, platform IDs, card JSON, and unbounded logs must not be stored in this suspended summary.

### FR-5: Deterministic resume restores suspended TODOs

If the new user request carries an explicit resume signal that resolves to exactly one suspended transaction, that transaction becomes current and its unfinished TODOs return to the main TODO display.

Allowed resume signals for the first implementation are deterministic and narrow:

1. exact or near-exact command forms that mean “continue the most recent suspended task,” e.g. `继续上一任务` / `继续刚才那个`;
2. explicit references already bound to one suspended transaction, such as a transaction id, task id, or PR number associated with that suspended task;
3. a renderer/dashboard action carrying a transaction id.

Broad natural-language similarity, topic embedding, or LLM-only judgment must not promote a suspended transaction to current. Ambiguous or multi-match input must fail closed: keep the new task clean and ask for clarification or show a compact suspended-work hint.

### FR-6: New unrelated topic isolates old TODOs

If the user starts a new request without an explicit resume signal, the request is treated as a new transaction for display purposes. The renderer must not show suspended old TODOs in the main TODO list.

Optional suspended-work reminders must be visually separate from the main task TODO block and bounded:

- candidate set: only suspended transactions whose `owner_scope_ref` matches the current request owner scope;
- default reminder count: at most one suspended transaction;
- selection priority within that owner scope: user-action-required `waiting_user` first, then most recently updated suspended transaction;
- Feishu default: one line, target ≤80 Chinese characters or ≤120 Latin characters after sanitization;
- if more same-scope suspended tasks exist, show a count such as `另有 2 个挂起事项` and require dashboard/history or explicit command for details.

### FR-7: Display policy for completed items inside resumed transactions

When a suspended transaction is resumed, completed items may be visible only if they help orientation. The default should favor concise display:

- show completed count;
- show remaining items;
- optionally allow expanded completed details in dashboard/history, not always in Feishu card.

### FR-8: History and dashboard access

Historical completed TODOs and suspended transaction details should remain accessible through dashboard/history/event logs when requested, without polluting the next current task card.

### FR-9: Stale-context and restart safety

After context compression, gateway restart, event-log rotation, or reader fallback, the system must not resurrect a stale TODO list merely because it was the last non-empty list observed.

Reader logic should prefer explicit current transaction state and terminal/empty markers over stale last-known TODOs.

### FR-10: Safety and redaction compatibility

All lifecycle metadata and TODO content remain user-facing progress data. Existing sanitizer/redaction boundaries still apply:

- local file paths in TODO text are not gate-blocking leaks by themselves;
- independent credentials/secrets/provider-key-shaped values must be redacted;
- API routes like `/health` or `/metrics` must not be blanket-redacted;
- output must remain bounded and sanitized before persistence/rendering.

### FR-11: Agent TODO hydration and injection safety

Lifecycle correctness must cover the agent-side TODO store, not only the progress reader. A later implementation must define a deterministic lifecycle marker that lets hydration and prompt injection distinguish:

- current active transaction TODOs;
- suspended transaction TODOs eligible for same-owner scoped hint/resume;
- completed/archived historical TODOs;
- unrelated new-task clean state.

The design must explicitly cover these existing paths:

- `AIAgent._hydrate_todo_store()` reading prior `todo` tool responses from conversation history;
- cached/fresh agent `_todo_store` reuse when Gateway creates progress snapshots;
- `TodoStore.format_for_injection()` preserving pending/in-progress items across context compression.

If the lifecycle marker is absent, ambiguous, belongs to another owner scope, or belongs to a completed/archived transaction, hydration/re-injection must fail closed for the current main TODO block. It may provide at most the same scoped one-line suspended hint allowed by FR-6.

## 8. Non-functional requirements

- Low intrusion: prefer extending the existing progress/TODO snapshot model, reader, and renderers over adding a new core tool.
- Prompt-cache safe: do not mutate prior conversation state or tool schemas mid-session.
- Platform-neutral model first: Feishu and Web renderers consume the same lifecycle semantics.
- Backward compatible: existing events without lifecycle fields should degrade safely and not crash readers.
- Deterministic display: FR-5 is authoritative; no hidden LLM-only state, broad semantic similarity, or transcript inference may decide that old TODOs are current.
- Evidence-first: product behavior must be proven with tests for tracker/store/reader/renderers before implementation PR readiness.

## 8.1 Edge-case policy

### Multiple suspended transactions

The system may store multiple suspended transactions, but Feishu's current task workbench should display at most one compact suspended-work hint by default. Candidate selection is first filtered to the current request's matching `owner_scope_ref`; transactions from other users/chats/threads/topics/platforms/profiles are invisible to the hint/resume path. Same-scope selection order:

1. most recent `waiting_user` transaction;
2. otherwise most recently updated suspended transaction;
3. tie-break by stable transaction ordering.

Dashboard/history surfaces may show the full suspended list only through filters or labels that preserve owner-scope isolation, plus explicit resume actions that re-check owner scope before revealing details or resuming.

### Retention and expiry

Suspended transactions remain resumable while present in the configured recent progress/event retention window. The first implementation should not invent long-term project management storage. If a suspended transaction falls out of the reader's retained window, it is treated as archived history rather than current/resumable work unless a future durable task system explicitly owns it.

### New session with old suspended work

A new session or post-compression turn must start with an empty main TODO area unless there is an active current transaction or an explicit resume signal. The old suspended transaction may produce at most the compact `挂起事项` hint defined in FR-6.

### Cancelled mid-flight

Cancelled transactions may show a final cancellation render once, then archive. They must not be shown as suspended unless there is a separately actionable recovery item.

### TODO tree depth

The task workbench remains V1 single-level in display. The data schema may reserve up to two levels (`parent_id` from child to top-level parent), but renderers and APIs must not create or depend on infinite trees.

## 9. Out of scope / explicit non-approvals

This PRD does not approve:

- Source-code implementation before PRD review, Claude design/teach-back, Codex technical review, and explicit user approval.
- Gateway restart/reload, production config changes, live/default-on rollout, or platform adapter mutation.
- New model tool surfaces.
- Broad natural-language inference over historical transcripts to reconstruct TODOs.
- Infinite TODO trees or more than the already-discussed one-level / reserved-two-level model.
- Long-term project/task management beyond current transaction plus compact suspended-task hints.
- External storage/service introduction solely for TODO lifecycle.
- Displaying raw logs, raw prompts, raw tool outputs, credentials, platform IDs, or card JSON in lifecycle summaries.

## 10. Acceptance criteria for a later implementation

A future implementation PR can request review only when it proves:

1. A completed transaction renders completed TODOs in its final card but does not show them in the next unrelated task card.
2. An explicit empty TODO list clears prior TODOs.
3. A partially complete transaction can be marked suspended with blocker/waiting reason, remaining TODO summaries, and sanitized `owner_scope_ref` when cross-turn hint/resume is allowed.
4. Resuming the same suspended transaction shows remaining TODOs as current and summarizes completed items concisely.
5. Starting a request with no explicit resume signal starts a clean current task and does not put suspended old TODOs in the main TODO block.
6. Optional suspended-work hints are separate, labeled `挂起事项` / `Suspended work`, limited to one line and at most one selected suspended transaction by default, with overflow shown as a count.
7. Same-profile but different user/chat/thread/topic records cannot see, hint, or resume one another's suspended TODOs; tests must cover at least two users/chats/threads in the same profile.
8. Reader/store/tracker behavior survives missing lifecycle fields, malformed/old JSONL records, event-log rotation, and gateway restart without resurrecting zombie TODOs.
9. Agent hydration/re-injection behavior is covered: `AIAgent._hydrate_todo_store`, cached agent `_todo_store` reuse, and `TodoStore.format_for_injection` after context compression must not inject an old pending TODO list into a new unrelated main task.
10. A restart/compression scenario with an old pending TODO in transcript history and a new unrelated request produces an empty main TODO block and at most one same-owner scoped suspended hint.
11. Feishu renderer and Web/API surface follow the same lifecycle semantics and owner-scope isolation.
12. Existing redaction tests still pass, and new tests cover lifecycle summaries containing local paths, API routes, fake credential-shaped strings, and sanitized owner-scope references.
13. Focused tests cover tracker/store/reader/renderer/run-agent hydration integration, not only pure helper functions.
14. `git diff --check`, relevant pytest suites, and an independent blocker-only review pass before PR readiness.

## 11. Proposed lifecycle model

```text
created
→ active
→ completed
→ archived
```

Alternative paths:

```text
active
→ blocked / waiting_user / waiting_external / failed_recoverable
→ suspended
→ resumed
→ active
→ completed
→ archived
```

```text
active
→ cancelled
→ archived
```

Display mapping:

| Lifecycle state / reason | Main task TODO display | History/dashboard | Optional new-task reminder |
|---|---|---|---|
| `active` | Show current TODOs | Yes | No |
| `completed` final render | Show once in same transaction | Yes | No |
| `archived` | No | Yes | No |
| `active` or `suspended` with reason `blocked` / `waiting_*` | Show blocker + remaining TODOs when current/resumed | Yes | N/A |
| `suspended` same-owner unrelated topic | No | Yes | Maybe one compact `挂起事项` line |
| `resumed` | Show remaining TODOs as current | Yes | No |
| `cancelled` final render | Show cancellation once | Yes | No |

## 12. Risk register

| Risk | Mitigation |
|---|---|
| Ambiguous natural language accidentally resumes stale work | FR-5 explicit deterministic resume only; ambiguity fails closed. |
| Suspended reminders accumulate or leak across owner scopes | FR-6 and §8.1 filter candidates by `owner_scope_ref`, limit default reminders to one line / one selected transaction, and leave dashboard/history to owner-scoped detail views. |
| Reader or agent hydration resurrects last non-empty TODO after restart/compression/rotation | FR-3, FR-9, and FR-11 require explicit empty/terminal/current transaction semantics across reader, agent hydration, cached `_todo_store`, and prompt injection. |
| Lifecycle state model conflicts with existing status names | FR-2 separates lifecycle state from suspension reason and allows mapping only if product distinctions survive. |
| Redaction regresses while adding lifecycle summaries | FR-10 and AC #12 require fake credential/path/API-route regression tests. |

## 13. Open questions for architecture/design

1. Is existing `TransactionSnapshot.transaction_id` sufficient for task ownership, or is a coarser logical-task id needed for nested/recursive runs?
2. Should suspended transactions be stored in the existing progress JSONL stream, a compact current-state projection, or both?
3. Should explicit resume actions be implemented first as text commands only, renderer/dashboard buttons only, or both?
4. Should completed-item expansion be a renderer option, dashboard-only behavior, or future interaction affordance?
5. How should lifecycle state interact with existing `todo` tool state when a new session starts but the old transaction remains suspended, beyond the first-version default in §8.1?

## 14. Review gates for this PRD

This PRD is ready to become the basis for development only after:

1. Claude Code reviews it at `xhigh` effort and provides a PRD/design-readiness assessment.
2. Codex CLI independently performs a blocker-focused review.
3. Hermes resolves or explicitly carries any blockers.
4. Hermes produces a final user-facing solution packet with recommended implementation scope and non-approvals.
5. The user explicitly approves implementation scope.

## 15. Suggested implementation approval phrase (future, not yet granted)

```text
批准实现任务工作台 TODO 生命周期：当前任务主显示、已完成归档、未完成挂起、同 owner scope 的显式恢复、无关新话题隔离、agent TODO hydration/re-injection 防僵尸；允许修改 progress/workbench/TODO 生命周期相关代码与测试；保持现有结构化 TODO 来源、Feishu/Web 同源展示、secret redaction、无新增核心工具、无 Gateway 服务生命周期/重启/平台适配/live/config 变更。
```
