# Task Workbench TODO Lifecycle Implementation Plan

> **For Hermes:** This is a docs-only implementation plan. Do not start source-code implementation until the user explicitly approves the scope. When implementation is approved, use Claude Code as main programmer and enforce strict TDD task by task.

**Goal:** Implement transaction-scoped TODO lifecycle semantics so the task workbench shows only current-task TODOs, archives completed TODOs, suspends unfinished work safely, and prevents zombie TODOs after context compression, restarts, and new unrelated turns.

**Architecture:** Add a small lifecycle layer around the existing structured TODO/progress pipeline instead of adding a new tool. The lifecycle layer stamps TODO snapshots with transaction/lifecycle/owner-scope metadata, serializes it through progress store/reader/API, renders current TODOs and suspended hints separately, and gates agent-side TODO hydration/re-injection on deterministic resume signals.

**Tech Stack:** Python dataclasses + existing `gateway.progress.*` modules, `tools.todo_tool.TodoStore`, run-agent hydration paths, Feishu renderer, Web progress API/React page, pytest, py_compile, git diff checks, changed-line safety scans.

---

## 1. Authority, reviewed inputs, and scope

### 1.1 Repo authority and reviewed artifacts

Use these files as the authoritative task inputs:

- PRD: `docs/plans/2026-06-24-task-workbench-todo-lifecycle-prd.md`
- Final solution packet: `docs/plans/2026-06-24-task-workbench-todo-lifecycle-final-solution.md`
- Claude review: `docs/plans/2026-06-24-task-workbench-todo-lifecycle-claude-review.md`
- Codex review: `docs/plans/2026-06-24-task-workbench-todo-lifecycle-codex-review.md`
- Dev log: `docs/dev_log/2026-06-24-task-workbench-todo-lifecycle-prd.md`
- Current repo rules: `AGENTS.md`, `GOAL.md`, `docs/roadmap/current-status.md`

Current PRD/review state:

- Claude Code final PRD re-review: `VERDICT: PASS`, 95 / 100.
- Codex CLI PRD re-review: `VERDICT: PASS`, 94 / 100.
- Remaining PRD blockers: none.
- This implementation plan still grants no source-code implementation by itself.

### 1.2 Approved implementation boundary to request

When the user approves, the implementation scope should match the PRD approval phrase:

```text
任务工作台 TODO 生命周期：当前任务主显示、已完成归档、未完成挂起、同 owner scope 的显式恢复、无关新话题隔离、agent TODO hydration/re-injection 防僵尸；允许修改 progress/workbench/TODO 生命周期相关代码与测试；保持现有结构化 TODO 来源、Feishu/Web 同源展示、secret redaction、无新增核心工具、无 Gateway 服务生命周期/重启/平台适配/live/config 变更。
```

### 1.3 Explicit non-approvals

Do **not** do any of these in the implementation PR:

- no Gateway restart/reload or service lifecycle change;
- no production config write;
- no live/default-on rollout;
- no platform adapter mutation;
- no Temporal/Worker lifecycle or controlled AI FLOW execution;
- no agent/acpx/npx real execution;
- no new model tool surface;
- no public ingress or real delivery;
- no raw platform IDs, chat IDs, thread IDs, topic IDs, user IDs, card JSON, raw prompts, raw logs, raw tool output, credentials, or unbounded history in lifecycle summaries.

---

## 2. Existing code anchors

These anchors were checked in the current worktree and must guide the implementation:

| Area | Current file / symbol | Current behavior |
|---|---|---|
| TODO item schema | `gateway/progress/events.py:38` `TodoItemSnapshot`; `TransactionSnapshot.todo_items` | TODO snapshot is a tuple of sanitized display items; no lifecycle metadata yet. |
| Tracker ingestion | `gateway/progress/tracker.py:303` `ProgressTracker.update_todo_items()` | Replaces sanitized TODO snapshot and flattens parent links. |
| Store persistence | `gateway/progress/store.py:220` `_safe_transaction()` | Always emits `transaction.todo_items`, including explicit `[]` to clear stale reader state. |
| Reader aggregation | `gateway/progress/reader.py:358` `_summarize_transactions()` / `_merge_transaction()` | Latest record with `todo_items` wins; no lifecycle-state distinction yet. |
| Feishu/text rendering | `gateway/progress/renderers.py:398` `_feishu_todo_element()` and `:438` `_todo_text_lines()` | Renders every snapshot TODO in the main TODO block if non-empty. |
| Gateway snapshot copy | `gateway/run.py:14815` `_refresh_progress_todo_items()` | Copies `agent._todo_store.read()` into every progress tracker snapshot. |
| Agent hydration | `run_agent.py:3355` `AIAgent._hydrate_todo_store()` | Restores the most recent tool response containing `todos`, regardless of new-turn relation. This is the main zombie path. |
| Turn hydration trigger | `agent/turn_context.py:200` | Hydrates TODO store from conversation history before adding the current user turn. |
| Compression injection | `agent/conversation_compression.py:501` | Injects `TodoStore.format_for_injection()` into compressed history when active items exist. |
| TODO store/tool | `tools/todo_tool.py:36` `TodoStore`; `:251` `todo_tool()` | Stores only items; tool output has `todos` + `summary`, no lifecycle envelope. |
| Current tests | `tests/gateway/test_progress_tracker.py`, `tests/gateway/test_progress_reader.py`, `tests/gateway/test_progress_renderer.py`, `tests/run_agent/test_run_agent.py`, `tests/tools/test_todo_tool.py` | Cover item sanitization, explicit empty TODOs, renderer placement, and basic hydration; no lifecycle/zombie gate yet. |

---

## 3. Proposed low-intrusion design

### 3.1 Add one small lifecycle helper module

Create:

- `gateway/progress/todo_lifecycle.py`

This module owns constants, sanitization, deterministic resume recognition, owner-scope digest helpers, and small dataclasses. Keep it platform-neutral and dependency-light.

Expected public shapes:

```python
@dataclass(frozen=True)
class OwnerScopeRef:
    profile: str
    platform: str
    conversation: str
    user: str

@dataclass(frozen=True)
class TodoLifecycleSnapshot:
    state: str                     # created|active|completed|suspended|resumed|cancelled|archived
    suspension_reason: str | None = None
    completed_count: int = 0
    remaining_count: int = 0
    next_action: str | None = None
    owner_scope_ref: OwnerScopeRef | None = None

@dataclass(frozen=True)
class SuspendedTodoHint:
    transaction_id: str
    title: str
    reason: str
    remaining_count: int
    next_action: str | None = None
    overflow_count: int = 0
```

Design rules:

- sanitize every text field through existing progress redaction helpers;
- cap display text and counts;
- normalize unknown lifecycle states to fail-closed values;
- never store raw owner identifiers;
- expose deterministic resume helpers only for exact/near-exact command forms, not semantic similarity.

Initial deterministic resume forms:

```text
继续
继续上一任务
继续刚才那个
接着处理上一任务
继续上一个任务
resume previous task
continue previous task
```

Implementation detail: treat bare `继续` as resume only when exactly one same-owner suspended transaction candidate exists. If none or more than one exists, do not hydrate old TODOs into the main block.

### 3.2 Extend snapshots without changing the core tool surface

Modify:

- `gateway/progress/events.py`
- `gateway/progress/tracker.py`
- `gateway/progress/store.py`
- `gateway/progress/reader.py`
- `gateway/progress/renderers.py`

Add lifecycle fields to `TransactionSnapshot`, not a new model tool:

```python
@dataclass
class TransactionSnapshot:
    ...
    todo_items: tuple[TodoItemSnapshot, ...] = ()
    todo_lifecycle: TodoLifecycleSnapshot | None = None
    suspended_todo_hint: SuspendedTodoHint | None = None
```

Tracker methods:

```python
def update_todo_lifecycle(self, lifecycle: Any) -> TodoLifecycleSnapshot | None: ...
def update_suspended_todo_hint(self, hint: Any) -> SuspendedTodoHint | None: ...
```

Persistence:

- `progress_snapshot_to_record()` writes `todo_lifecycle` and `suspended_todo_hint` when present;
- reader normalizes both fields on read;
- malformed lifecycle records never raise;
- missing lifecycle fields are legacy records and must not be promoted to current/resumable state by themselves.

### 3.3 Teach `TodoStore` lifecycle ownership, but keep tool schema narrow

Modify:

- `tools/todo_tool.py`
- `agent/agent_runtime_helpers.py`
- `agent/tool_executor.py`

Add lifecycle metadata inside `TodoStore`, not as user/model-facing required tool arguments:

```python
class TodoStore:
    def bind_transaction(self, transaction_id: str | None, owner_scope_ref: dict | None = None) -> None: ...
    def mark_lifecycle(self, state: str, reason: str | None = None, next_action: str | None = None) -> None: ...
    def clear_for_new_transaction(self) -> None: ...
    def read_lifecycle(self) -> dict[str, Any] | None: ...
    def read_snapshot(self) -> dict[str, Any]: ...  # items + lifecycle + summary
```

The `todo` tool can keep returning existing `todos` and `summary`, plus optional backward-compatible metadata:

```json
{
  "todos": [...],
  "summary": {...},
  "todo_lifecycle": {...}
}
```

Backwards compatibility: existing callers that read only `todos` keep working.

### 3.4 Gate hydration and compression injection

Modify:

- `run_agent.py`
- `agent/turn_context.py`
- `agent/conversation_compression.py`

Required behavior:

1. `AIAgent._hydrate_todo_store()` must not restore the last old non-empty `todos` blindly.
2. The method should accept the current user message and a safe owner scope when available.
3. Hydration should only restore current/resumable TODOs when a lifecycle marker and deterministic resume decision allow it.
4. Legacy tool outputs that contain only `todos` but no lifecycle marker should fail closed for a new unrelated request.
5. `TodoStore.format_for_injection()` should inject active/resumed current items only; completed/archived/cancelled/suspended-without-current-resume must not be injected into the main prompt as active task state.

Expected skeleton:

```python
def _hydrate_todo_store(self, history, *, current_user_message: str = "", owner_scope_ref: dict | None = None) -> None:
    decision = select_todo_hydration_candidate(
        history,
        current_user_message=current_user_message,
        owner_scope_ref=owner_scope_ref,
    )
    if decision.restore_items:
        self._todo_store.write(decision.items, merge=False)
        self._todo_store.mark_lifecycle("resumed" if decision.was_suspended else "active")
    else:
        self._todo_store.clear_for_new_transaction()
```

Do not use LLM judgment, embeddings, or broad transcript inference here.

### 3.5 Render current TODOs and suspended hints separately

Modify:

- `gateway/progress/renderers.py`
- `hermes_cli/web_server.py`
- `web/src/lib/api.ts`
- `web/src/pages/ProgressPage.tsx`

Rules:

- main TODO block renders only when lifecycle says the snapshot is current (`active`, `resumed`, or final same-transaction `completed` / `cancelled` render);
- suspended hints render as a separate one-line `挂起事项` / `Suspended work` block;
- hint limit: one selected transaction by default; overflow is a count;
- Feishu and Web/API must use the same lifecycle semantics;
- local paths remain visible unless mixed with independent secret-shaped text;
- fake credential-shaped text is redacted.

---

## 4. Acceptance traceability matrix

| PRD AC | Implementation evidence required | Primary tests |
|---|---|---|
| AC-1 completed final render then next unrelated empty | tracker/store/renderer + run-agent hydration scenario | `tests/gateway/test_progress_renderer.py`, `tests/run_agent/test_run_agent.py` |
| AC-2 explicit empty TODO clears stale state | store/reader regression remains green and adds lifecycle variant | `tests/gateway/test_progress_store.py`, `tests/gateway/test_progress_reader.py` |
| AC-3 suspended state with reason/summary/owner | lifecycle helper + store serialization | `tests/gateway/test_todo_lifecycle.py`, `tests/gateway/test_progress_store.py` |
| AC-4 explicit same-owner resume restores remaining TODOs | hydration decision + renderer display | `tests/run_agent/test_run_agent.py`, `tests/gateway/test_progress_renderer.py` |
| AC-5 no explicit resume starts clean | hydration fail-closed | `tests/run_agent/test_run_agent.py` |
| AC-6 compact suspended hint separate from main TODO | renderer and API tests | `tests/gateway/test_progress_renderer.py`, `tests/gateway/test_feishu_progress_cards.py`, Web tests/typecheck |
| AC-7 same profile but different user/chat/thread cannot see/hint/resume | owner-scope digest + selection tests | `tests/gateway/test_todo_lifecycle.py`, `tests/run_agent/test_run_agent.py` |
| AC-8 missing fields/malformed JSONL/rotation/restart no zombie | reader/store tests | `tests/gateway/test_progress_reader.py`, `tests/gateway/test_progress_store.py` |
| AC-9 hydrate/cached store/format_for_injection no old pending injection | run-agent + TodoStore tests | `tests/run_agent/test_run_agent.py`, `tests/tools/test_todo_tool.py` |
| AC-10 restart/compression old pending + unrelated request -> empty main block | integration-style hydration test | `tests/run_agent/test_run_agent.py`, `tests/tools/test_todo_tool.py` |
| AC-11 Feishu/Web/API parity | Feishu card + API type/render tests | `tests/gateway/test_feishu_progress_cards.py`, `web` typecheck/build |
| AC-12 redaction compatibility | fake secrets redacted, paths/routes preserved | `tests/gateway/test_progress_redaction.py`, tracker/store/renderer tests |
| AC-13 focused integration coverage | full focused pytest command | See §6.2 |
| AC-14 diff/check/review pass | local gates + Codex exact-head review | See §6.4 |

---

## 5. Task-by-task implementation plan

### Task 0: Fresh implementation preflight

**Objective:** Start from live repo truth and preserve the PRD branch as docs-only evidence.

**Files:** none.

**Steps:**

1. Fetch and check state.

```bash
git fetch sachima release/sachima
git status --short --branch
git rev-list --left-right --count sachima/release/sachima...HEAD
```

Expected: clean worktree. If the implementation branch still includes only docs artifacts, decide whether to continue on it or create a new code-bearing branch from `sachima/release/sachima` and cherry-pick the docs artifacts.

2. Confirm no PRD-only branch is accidentally treated as runtime approval.

Expected: report branch name, base SHA, and non-approvals before code.

---

### Task 1: Add RED tests for lifecycle helper and owner-scope isolation

**Objective:** Prove the lifecycle helper does not exist yet and pin deterministic behavior before production code.

**Files:**

- Create: `tests/gateway/test_todo_lifecycle.py`
- Later create: `gateway/progress/todo_lifecycle.py`

**Step 1: Write failing tests**

Test cases:

- `test_normalize_lifecycle_rejects_unknown_state`
- `test_owner_scope_ref_hashes_raw_ids_and_does_not_render_raw_values`
- `test_resume_signal_requires_single_same_owner_candidate`
- `test_resume_signal_rejects_cross_owner_candidate`
- `test_bare_continue_is_ambiguous_with_multiple_candidates`

Example test shape:

```python
def test_resume_signal_requires_single_same_owner_candidate():
    from gateway.progress.todo_lifecycle import (
        make_owner_scope_ref,
        select_resume_candidate,
        SuspendedTodoHint,
    )

    owner = make_owner_scope_ref(
        profile="default",
        platform="feishu",
        conversation_id="raw-chat-id-a",
        user_id="raw-user-id-a",
    )
    hint = SuspendedTodoHint(
        transaction_id="tx-old",
        title="等待 CI",
        reason="waiting_external",
        remaining_count=1,
        owner_scope_ref=owner,
    )

    assert select_resume_candidate("继续", [hint], owner).transaction_id == "tx-old"
```

**Step 2: Run RED**

```bash
uv run --extra dev python -m pytest tests/gateway/test_todo_lifecycle.py -q -o 'addopts='
```

Expected: FAIL because `gateway.progress.todo_lifecycle` does not exist.

---

### Task 2: Implement lifecycle helper minimally

**Objective:** Add deterministic lifecycle/state/owner-scope primitives with no renderer or agent integration yet.

**Files:**

- Create: `gateway/progress/todo_lifecycle.py`
- Test: `tests/gateway/test_todo_lifecycle.py`

**Implementation notes:**

- states: `created`, `active`, `completed`, `suspended`, `resumed`, `cancelled`, `archived`;
- reasons: `blocked`, `waiting_user`, `waiting_external`, `failed_recoverable`, `paused`;
- owner scope fields: safe labels plus digest/opaque refs, never raw IDs;
- deterministic resume: literal/regex only, no model/embedding similarity;
- output text bounded and sanitized.

**Run GREEN**

```bash
uv run --extra dev python -m pytest tests/gateway/test_todo_lifecycle.py -q -o 'addopts='
```

Expected: PASS.

---

### Task 3: Add RED tests for snapshot lifecycle serialization

**Objective:** Prove tracker/store/reader cannot yet carry lifecycle metadata and hints.

**Files:**

- Modify tests: `tests/gateway/test_progress_tracker.py`
- Modify tests: `tests/gateway/test_progress_store.py`
- Modify tests: `tests/gateway/test_progress_reader.py`

**Step 1: Write failing tests**

Add tests for:

- `ProgressTracker.update_todo_lifecycle(...)` stores sanitized `TodoLifecycleSnapshot`;
- JSONL record includes `transaction.todo_lifecycle` and `transaction.suspended_todo_hint`;
- reader normalizes lifecycle/hint and drops malformed owner scope;
- legacy records with no lifecycle field do not become resumable.

**Step 2: Run RED**

```bash
uv run --extra dev python -m pytest \
  tests/gateway/test_progress_tracker.py::test_update_todo_lifecycle_carries_sanitized_state \
  tests/gateway/test_progress_store.py::test_progress_records_include_todo_lifecycle_and_hint \
  tests/gateway/test_progress_reader.py::test_progress_reader_normalizes_todo_lifecycle_and_rejects_malformed_scope \
  -q -o 'addopts='
```

Expected: FAIL because tracker/events/store/reader do not expose lifecycle fields.

---

### Task 4: Implement snapshot lifecycle serialization

**Objective:** Thread lifecycle metadata through events, tracker, JSONL store, and reader.

**Files:**

- Modify: `gateway/progress/events.py`
- Modify: `gateway/progress/tracker.py`
- Modify: `gateway/progress/store.py`
- Modify: `gateway/progress/reader.py`
- Test: files from Task 3

**Implementation notes:**

- add dataclass fields to `TransactionSnapshot`;
- add tracker update methods;
- persist fields through `_safe_transaction()`;
- reader should sanitize/normalize and keep old JSONL backwards compatible;
- no field should contain raw IDs or fake secret-shaped text;
- explicit `todo_items: []` behavior must remain unchanged.

**Run GREEN**

```bash
uv run --extra dev python -m pytest \
  tests/gateway/test_progress_tracker.py \
  tests/gateway/test_progress_store.py \
  tests/gateway/test_progress_reader.py \
  tests/gateway/test_todo_lifecycle.py \
  -q -o 'addopts='
```

Expected: PASS.

---

### Task 5: Add RED renderer/API tests for current TODO vs suspended hint

**Objective:** Prove existing renderers always show TODOs in the main block and cannot render a separate suspended hint.

**Files:**

- Modify: `tests/gateway/test_progress_renderer.py`
- Modify: `tests/gateway/test_feishu_progress_cards.py`
- Modify or add Web/API tests if present near `web/src` test setup

**Test cases:**

1. completed final snapshot may show completed TODOs;
2. archived/completed historical snapshot used for a new task does not render main TODOs;
3. suspended hint renders under `挂起事项` and not under `待办`;
4. Feishu hint is one line and bounded;
5. text renderer and Feishu renderer redact fake credentials but preserve local paths and API routes.

**Run RED**

```bash
uv run --extra dev --extra messaging --extra feishu python -m pytest \
  tests/gateway/test_progress_renderer.py::test_feishu_renders_suspended_hint_separately_from_main_todos \
  tests/gateway/test_feishu_progress_cards.py::test_task_card_hides_archived_todos_and_shows_suspended_hint \
  -q --tb=short -o 'addopts='
```

Expected: FAIL before renderer changes.

---

### Task 6: Implement renderer/API lifecycle display

**Objective:** Render main TODOs only for current lifecycle states and render suspended hints separately.

**Files:**

- Modify: `gateway/progress/renderers.py`
- Modify: `hermes_cli/web_server.py`
- Modify: `web/src/lib/api.ts`
- Modify: `web/src/pages/ProgressPage.tsx`
- Test: renderer and Web/API gates

**Implementation notes:**

- Introduce helper predicates such as `should_render_main_todos(snapshot)` and `should_render_suspended_hint(snapshot)` in Python, mirrored in Web if needed.
- Main TODO states: `active`, `resumed`, and final same-transaction `completed` / `cancelled` when the snapshot itself is terminal.
- `archived` should not show main TODOs.
- Suspended hints are visually separate, one selected transaction by default, overflow count only.

**Run GREEN**

```bash
uv run --extra dev --extra messaging --extra feishu python -m pytest \
  tests/gateway/test_progress_renderer.py \
  tests/gateway/test_feishu_progress_cards.py \
  -q --tb=short -o 'addopts='

npm run --workspace web typecheck
```

Expected: PASS.

---

### Task 7: Add RED tests for TodoStore lifecycle and compression injection

**Objective:** Pin the agent-side zombie path before changing hydration behavior.

**Files:**

- Modify: `tests/tools/test_todo_tool.py`
- Modify: `tests/tools/test_read_loop_detection.py` if its injection tests are the better home

**Test cases:**

- active TODOs still inject after compression;
- completed/archived TODOs do not inject;
- suspended TODOs do not inject as main active state;
- resumed TODOs inject only after deterministic resume;
- tool output remains backward-compatible with `todos` + `summary`.

**Run RED**

```bash
uv run --extra dev python -m pytest \
  tests/tools/test_todo_tool.py::TestTodoLifecycleInjection \
  -q -o 'addopts='
```

Expected: FAIL because `TodoStore` has no lifecycle metadata.

---

### Task 8: Implement TodoStore lifecycle metadata

**Objective:** Keep existing `todo` tool behavior while adding lifecycle awareness for compression and progress snapshots.

**Files:**

- Modify: `tools/todo_tool.py`
- Modify: `agent/agent_runtime_helpers.py`
- Modify: `agent/tool_executor.py`
- Test: `tests/tools/test_todo_tool.py`, display tests if affected

**Implementation notes:**

- `TodoStore.write()` should preserve existing item validation, capping, and parent pruning.
- Add metadata methods; do not require model-facing new schema fields for the first implementation.
- `todo_tool()` can include optional `todo_lifecycle` in output, but must keep `todos` and `summary` exactly usable by old callers.
- Tool executor can bind the current effective task/transaction id when available; if unavailable, leave lifecycle unset and fail closed in hydration.

**Run GREEN**

```bash
uv run --extra dev python -m pytest \
  tests/tools/test_todo_tool.py \
  tests/agent/test_display_todo_progress.py \
  -q -o 'addopts='
```

Expected: PASS.

---

### Task 9: Add RED tests for run-agent hydration and unrelated new turns

**Objective:** Prove old pending TODOs currently resurrect from transcript history and pin the corrected behavior.

**Files:**

- Modify: `tests/run_agent/test_run_agent.py`
- Modify: `tests/agent/test_turn_context.py` if needed

**Test cases:**

1. legacy old `{"todos": [...]}` history + new unrelated message does **not** hydrate;
2. old lifecycle `suspended` + exact same-owner `继续` hydrates remaining items;
3. old lifecycle `suspended` + cross-owner scope does not hydrate;
4. ambiguous bare `继续` with two candidates does not hydrate;
5. completed/archived lifecycle does not hydrate;
6. `_set_interrupt(False)` behavior remains unchanged.

**Run RED**

```bash
uv run --extra dev python -m pytest \
  tests/run_agent/test_run_agent.py::TestHydrateTodoStore \
  tests/agent/test_turn_context.py \
  -q -o 'addopts='
```

Expected: at least new hydration lifecycle tests FAIL before code changes.

---

### Task 10: Implement hydration fail-closed behavior

**Objective:** Stop zombie TODO resurrection in `_hydrate_todo_store()` and turn-start hydration.

**Files:**

- Modify: `run_agent.py`
- Modify: `agent/turn_context.py`
- Modify: `agent/conversation_compression.py`
- Test: hydration and TodoStore tests

**Implementation notes:**

- Pass the current `user_message` into `_hydrate_todo_store()`.
- Parse lifecycle-aware todo tool responses from history; treat legacy `todos`-only responses as history, not current state, for new unrelated turns.
- Restore only when deterministic resume + same owner scope + exactly one candidate passes.
- On fail-closed, leave `_todo_store` empty for the new current task.
- Compression injection should call a lifecycle-aware `format_for_injection()` that excludes completed/archived/suspended-not-current items.

**Run GREEN**

```bash
uv run --extra dev python -m pytest \
  tests/run_agent/test_run_agent.py::TestHydrateTodoStore \
  tests/tools/test_todo_tool.py \
  tests/agent/test_turn_context.py \
  -q -o 'addopts='
```

Expected: PASS.

---

### Task 11: Wire Gateway progress snapshots to lifecycle state and owner scope

**Objective:** Ensure visible workbench snapshots carry lifecycle/hint state consistently.

**Files:**

- Modify: `gateway/run.py`
- Modify: existing Gateway/task-tracker tests near `tests/gateway/test_run_progress_topics.py` and `tests/gateway/test_feishu_progress_cards.py`

**Implementation notes:**

- `_refresh_progress_todo_items()` should copy both items and lifecycle metadata from `TodoStore`.
- When the store is empty or lifecycle says archived/not-current, tracker should get explicit empty TODOs for the main block.
- Owner scope must be derived from safe runtime context and stored as digest/label only. If scope cannot be built, do not enable cross-turn hint/resume for that record.
- Do not start/restart Gateway. This is code/test only.

**Run GREEN**

```bash
uv run --extra dev --extra messaging --extra feishu python -m pytest \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/test_feishu_progress_cards.py \
  -q --tb=short -o 'addopts='
```

Expected: PASS.

---

### Task 12: Web/API parity and type/build gates

**Objective:** Keep dashboard/API and Feishu semantics aligned.

**Files:**

- Modify: `hermes_cli/web_server.py`
- Modify: `web/src/lib/api.ts`
- Modify: `web/src/pages/ProgressPage.tsx`

**Steps:**

1. Add API response fields for `todo_lifecycle` and `suspended_todo_hint`.
2. Make Web current TODO display honor the lifecycle predicate.
3. Render a separate suspended-work hint / count.
4. Run type/build gates.

```bash
npm run --workspace web typecheck
npm run --workspace web build
```

Expected: exit 0. Existing chunk-size warnings are acceptable only if they are pre-existing and unrelated.

---

### Task 13: Redaction and forbidden-surface gates

**Objective:** Prove lifecycle metadata does not introduce leaks or unapproved runtime surfaces.

**Files:** tests and changed code only.

**Required checks:**

```bash
uv run --extra dev python -m pytest \
  tests/gateway/test_progress_redaction.py \
  tests/gateway/test_progress_tracker.py \
  tests/gateway/test_progress_store.py \
  tests/gateway/test_progress_reader.py \
  tests/gateway/test_progress_renderer.py \
  tests/gateway/test_feishu_progress_cards.py \
  tests/run_agent/test_run_agent.py::TestHydrateTodoStore \
  tests/tools/test_todo_tool.py \
  -q -o 'addopts='

uv run --extra dev --extra messaging --extra feishu python -m pytest \
  tests/gateway/test_feishu.py \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/test_feishu_progress_cards.py \
  -q --tb=short -o 'addopts='

uv run --extra dev python -m py_compile \
  gateway/progress/todo_lifecycle.py \
  gateway/progress/events.py \
  gateway/progress/tracker.py \
  gateway/progress/store.py \
  gateway/progress/reader.py \
  gateway/progress/renderers.py \
  tools/todo_tool.py \
  run_agent.py \
  agent/turn_context.py \
  agent/conversation_compression.py \
  gateway/run.py

git diff --check
```

Add a changed-line scan that fails on newly added forbidden surfaces:

- `systemctl`, `systemd-run`, service restart/reload calls;
- Temporal Worker/test-environment/Docker/subprocess/socket listener additions;
- platform adapter mutation outside approved files;
- raw platform/chat/user ID persistence keys;
- fake credential-shaped strings not built from fragments;
- shell interpolation of owner/lifecycle values.

---

### Task 14: Commit, independent review, PR, and approval card

**Objective:** Only after local gates pass, prepare the implementation PR through governed review.

**Steps:**

1. Inspect changed files and ensure no unrelated work.

```bash
git status --short --branch
git diff --stat sachima/release/sachima...HEAD
git diff --name-only sachima/release/sachima...HEAD
```

2. Commit with a narrow message after green gates.

```bash
git add <changed files>
git commit -m "Add TODO lifecycle to task workbench"
```

3. Run Codex CLI exact-head blocker review in read-only mode, bound to current head SHA.

Review prompt must ask for:

- zombie TODO paths: reader/store/renderer and agent hydration/compression;
- owner-scope leakage/resume isolation;
- redaction compatibility;
- Gateway/service lifecycle forbidden surfaces;
- Feishu/Web parity;
- tests that actually exercise RED/GREEN behavior.

4. Push to `sachima` remote and open PR against `release/sachima` only after Codex PASS and local gates pass.

```bash
git push sachima HEAD:<branch-name>
gh pr create --repo jovijovi/sachima --base release/sachima --head jovijovi:<branch-name> --title "Add TODO lifecycle to task workbench" --body-file <body-file>
```

5. Wait for CI on the exact PR head, then send a Feishu approval card bound to `headRefOid`.

Do not merge without explicit user approval.

---

## 6. Claude Code implementation prompt skeleton

Use this only after explicit user approval.

```text
You are Claude Code acting as main programmer for a governed Sachima implementation.
Model/effort: claude-opus-4-8[1m], effort xhigh, safe-mode, enough turn budget.

Repo/worktree: /data/agents/workspace/hermes/worktrees/sachima/todo-lifecycle-implementation
Branch/base: fresh implementation branch from sachima/release/sachima, with PRD artifacts available.

Goal: Implement Task Workbench TODO Lifecycle per:
- docs/plans/2026-06-24-task-workbench-todo-lifecycle-prd.md
- docs/plans/2026-06-24-task-workbench-todo-lifecycle-final-solution.md
- docs/plans/2026-06-24-task-workbench-todo-lifecycle-implementation-plan.md
- Claude/Codex PRD review files in docs/plans/

Hard scope:
- Modify only progress/workbench/TODO lifecycle code and tests needed for the plan.
- No Gateway restart/reload, no production config, no platform adapter mutation, no Temporal/Worker/acpx/npx/agent real execution, no new model tool, no live/default-on behavior, no real delivery.
- Use strict TDD: write RED tests first, run them, implement minimal code, rerun GREEN.
- Preserve existing TODO structured source, parent-depth normalization, explicit empty TODO clearing, Feishu/Web parity, and secret redaction. Local file paths are not leaks by themselves; fake credential-shaped text must be redacted.

Return:
- files changed;
- RED/GREEN tests run and outputs;
- final diff summary;
- any blockers or exact non-goal boundary risk.
Do not push or merge.
```

---

## 7. Completion definition

The implementation is not ready for PR until all are true:

- every PRD AC #1-#14 has a test or explicit evidence row;
- new behavior has RED evidence before GREEN;
- focused TODO/progress/run-agent/Feishu/Web gates pass;
- py_compile, `git diff --check`, changed-line secret/static scan, and forbidden-surface scan pass;
- Codex CLI exact-head blocker review returns PASS / no blockers;
- PR is opened against `jovijovi/sachima:release/sachima` with current head SHA;
- Feishu approval card is sent for that exact head;
- merge waits for explicit user approval.
